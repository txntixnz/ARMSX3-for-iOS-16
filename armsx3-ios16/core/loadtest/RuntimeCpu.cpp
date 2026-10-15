// SPDX-License-Identifier: GPL-2.0-only
#include "Runtime.h"
#include "HostCpuUsage.h"
#include "StartupLog.h"
#include <mach/mach.h>
#include <mach/thread_info.h>
#include <chrono>
#include <cstdio>
#include <cstring>

namespace ios_runtime
{
namespace
{
HostCpuWindow cpu_window;
struct ThreadPorts
{
    thread_act_array_t ports = nullptr;
    mach_msg_type_number_t count = 0;
    ~ThreadPorts()
    {
        if (!ports) return;
        for (mach_msg_type_number_t i = 0; i < count; ++i)
            mach_port_deallocate(mach_task_self(), ports[i]);
        vm_deallocate(mach_task_self(), reinterpret_cast<vm_address_t>(ports),
            static_cast<vm_size_t>(count) * sizeof(*ports));
    }
};
std::uint64_t microseconds(time_value_t value)
{
    return static_cast<std::uint64_t>(value.seconds) * 1000000 + value.microseconds;
}
}
void reset_host_cpu_observation() noexcept { cpu_window.reset(); }
void sample_host_cpu() noexcept
{
    try
    {
        ThreadPorts list;
        const auto status = task_threads(mach_task_self(), &list.ports, &list.count);
        if (status != KERN_SUCCESS)
        {
            cpu_window.reset();
            ARMSX3StartupLog("HOST CPU: kernel thread snapshot unavailable");
            return;
        }
        std::vector<HostCpuSample> samples;
        samples.reserve(list.count);
        for (mach_msg_type_number_t i = 0; i < list.count; ++i)
        {
            thread_identifier_info_data_t identity{};
            auto count = static_cast<mach_msg_type_number_t>(THREAD_IDENTIFIER_INFO_COUNT);
            if (thread_info(list.ports[i], THREAD_IDENTIFIER_INFO,
                reinterpret_cast<thread_info_t>(&identity), &count) != KERN_SUCCESS) continue;
            thread_basic_info_data_t basic{};
            count = THREAD_BASIC_INFO_COUNT;
            if (thread_info(list.ports[i], THREAD_BASIC_INFO,
                reinterpret_cast<thread_info_t>(&basic), &count) != KERN_SUCCESS) continue;
            thread_extended_info_data_t extended{};
            count = THREAD_EXTENDED_INFO_COUNT;
            const auto named = thread_info(list.ports[i], THREAD_EXTENDED_INFO,
                reinterpret_cast<thread_info_t>(&extended), &count) == KERN_SUCCESS;
            const auto length = named ? strnlen(extended.pth_name, sizeof(extended.pth_name)) : 0;
            samples.push_back({identity.thread_id, microseconds(basic.user_time),
                microseconds(basic.system_time), length ? std::string(extended.pth_name, length) : "unnamed"});
        }
        const auto now = std::chrono::steady_clock::now().time_since_epoch();
        const auto usage = cpu_window.update(
            std::chrono::duration_cast<std::chrono::nanoseconds>(now).count(), samples);
        if (usage.empty()) return; // Initial baseline or no comparable live threads.
        double total = 0;
        for (const auto& entry : usage) total += entry.total();
        char line[384];
        std::snprintf(line, sizeof(line), "HOST CPU: sampled live threads=%.1f%%; 100%%=one core; threads=%zu", total, samples.size());
        ARMSX3StartupLog(line);
        for (std::size_t i = 0; i < std::min<std::size_t>(8, usage.size()); ++i)
        {
            const auto& entry = usage[i];
            std::snprintf(line, sizeof(line), "HOST CPU thread: id=%llu; cpu=%.1f%%; user=%.1f%%; system=%.1f%%; name=%s",
                static_cast<unsigned long long>(entry.thread.id), entry.total(), entry.user_percent,
                entry.system_percent, entry.thread.name.c_str());
            ARMSX3StartupLog(line);
        }
    }
    catch (...)
    {
        cpu_window.reset();
        ARMSX3StartupLog("HOST CPU: observation failed; game execution continues");
    }
}
}

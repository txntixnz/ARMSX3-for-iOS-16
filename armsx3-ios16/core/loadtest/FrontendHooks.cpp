// SPDX-License-Identifier: GPL-2.0-only
#include "Emu/Io/pad_config.h"
#include "Emu/Io/mouse_config.h"
#include "StartupLog.h"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <functional>
#include <cstdio>
#include <cstdint>
#include <dlfcn.h>
#include <execinfo.h>
#include <string>
#include <string_view>
#include <thread>

// Normally owned by the desktop frontend. Keep real configuration objects.
std::string g_input_config_override;
cfg_input_configurations g_cfg_input_configs;
mouse_config g_cfg_mouse;

[[noreturn]] void report_fatal_error(std::string_view text, bool is_html, bool include_help_text)
{
    (void)is_html;
    (void)include_help_text;
    ARMSX3StartupLog("P2 fatal core error follows");
    std::string message(text);
    ARMSX3StartupLog(message.c_str());
    std::abort();
}

// Headless frontend wait: evaluate the operation until completion. This load
// test never starts emulation; future UIKit lifecycle calls must run off-main.
void qt_events_aware_op(int repeat_duration_ms, std::function<bool()> operation)
{
    if (!operation) report_fatal_error("Missing wait operation", false, false);
    while (!operation())
        std::this_thread::sleep_for(std::chrono::milliseconds(std::max(1, repeat_duration_ms)));
}

// Persist the deliberate JIT boundary failure before abort(), including image
// offsets that can be symbolicated against the matching workflow dSYM.
extern "C" void armsx3_record_jit_failure(const char* message)
{
    ARMSX3StartupLog(message);
    void* frames[24];
    const int count = backtrace(frames, 24);
    for (int i = 0; i < count; ++i)
    {
        Dl_info info{};
        char line[1024];
        if (dladdr(frames[i], &info) && info.dli_fbase)
        {
            const auto offset = reinterpret_cast<std::uintptr_t>(frames[i]) -
                reinterpret_cast<std::uintptr_t>(info.dli_fbase);
            std::snprintf(line, sizeof(line), "P2 JIT frame %d: %s + 0x%llx (%s)",
                i, info.dli_fname ? info.dli_fname : "?",
                static_cast<unsigned long long>(offset),
                info.dli_sname ? info.dli_sname : "?");
        }
        else
            std::snprintf(line, sizeof(line), "P2 JIT frame %d: %p", i, frames[i]);
        ARMSX3StartupLog(line);
    }
}

extern "C" void armsx3_record_immutable_jit(size_t bytes)
{
    char line[160];
    std::snprintf(line, sizeof(line), "P2 immutable JIT published: %zu code bytes, isolated RX pages", bytes);
    ARMSX3StartupLog(line);
}

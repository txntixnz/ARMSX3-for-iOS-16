// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <algorithm>
#include <cstdint>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace ios_runtime
{
struct HostCpuSample
{
    std::uint64_t id, user_us, system_us;
    std::string name;
};
struct HostCpuUsage
{
    HostCpuSample thread;
    double user_percent, system_percent;
    double total() const { return user_percent + system_percent; }
};
// Owned by the serialized runtime worker. IDs are kernel thread identities,
// never pthread pointers or port names, which may be reused between snapshots.
class HostCpuWindow
{
    std::map<std::uint64_t, HostCpuSample> previous;
    std::uint64_t previous_ns = 0;
public:
    void reset() { previous.clear(); previous_ns = 0; }
    std::vector<HostCpuUsage> update(std::uint64_t now_ns, const std::vector<HostCpuSample>& samples)
    {
        std::vector<HostCpuUsage> result;
        const auto elapsed = now_ns > previous_ns ? now_ns - previous_ns : 0;
        std::map<std::uint64_t, HostCpuSample> next;
        for (const auto& sample : samples)
        {
            const auto old = previous.find(sample.id);
            if (previous_ns && elapsed && old != previous.end() &&
                sample.user_us >= old->second.user_us && sample.system_us >= old->second.system_us)
            {
                // One fully occupied CPU core is 100%; sums can exceed 100%.
                const double scale = 100000.0 / elapsed;
                result.push_back({sample, (sample.user_us - old->second.user_us) * scale,
                    (sample.system_us - old->second.system_us) * scale});
            }
            next.emplace(sample.id, sample);
        }
        previous = std::move(next);
        previous_ns = now_ns;
        std::sort(result.begin(), result.end(), [](const auto& a, const auto& b) {
            return a.total() > b.total();
        });
        return result;
    }
};
}

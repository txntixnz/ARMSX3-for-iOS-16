// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <atomic>
#include <cstdint>
#include <cstring>

class ARMSX3LogSyncPolicy
{
    std::atomic<std::uint64_t> next_core_sync{0};
public:
    bool should_sync(const char* message, std::uint64_t monotonic_us)
    {
        // Every line is written immediately. Core chatter shares a one-second
        // disk-sync interval; explicit startup/input/result markers still sync.
        if (std::strncmp(message, "P4 core: ", 9) != 0) return true;
        auto next = next_core_sync.load(std::memory_order_relaxed);
        while (monotonic_us >= next)
        {
            if (next_core_sync.compare_exchange_weak(next, monotonic_us + 1'000'000,
                std::memory_order_relaxed)) return true;
        }
        return false;
    }
};

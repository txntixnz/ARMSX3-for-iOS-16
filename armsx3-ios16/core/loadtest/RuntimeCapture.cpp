// SPDX-License-Identifier: GPL-2.0-only
#include "Runtime.h"
#include "StartupLog.h"
#include "Emu/IdManager.h"
#include "Emu/Cell/PPUThread.h"
#include "Emu/Cell/SPUThread.h"
#include "Utilities/Thread.h"
#include <algorithm>
#include <atomic>
#include <mutex>
#include <string>

namespace ios_runtime
{
namespace
{
std::atomic<bool> observation_armed{false};
std::mutex observation_mutex;
ExecutionProgress progress;
void log_capture(const std::string& text) { ARMSX3StartupLog(text.c_str()); }
}
void begin_execution_observation()
{
    std::lock_guard lock(observation_mutex);
    progress = {};
    observation_armed.store(true);
}
ExecutionProgress execution_progress()
{
    std::lock_guard lock(observation_mutex);
    return progress;
}
}

// Called by patch0051 between native thread joins and context destruction.
// Register/counter/history fields are read only here, never while CPUs run.
extern "C" void armsx3_ios_runtime_capture_stopped() noexcept
{
    using namespace ios_runtime;
    if (!observation_armed.exchange(false)) return;
    std::lock_guard lock(observation_mutex);
    try
    {
        idm::select<named_thread<ppu_thread>>([](u32 id, ppu_thread& ppu)
        {
            ++progress.ppu_contexts;
            progress.instructions += ppu.exec_bytes / 4;
            progress.calls += ppu.syscall_history.index;
            if (progress.ppu_contexts > 16) return;
            log_capture("EXECUTION joined PPU id=" + std::to_string(id) + " pc=" + std::to_string(ppu.cia) +
                " native exec_bytes/4=" + std::to_string(ppu.exec_bytes / 4) + " completed HLE/LV2 calls=" +
                std::to_string(ppu.syscall_history.index) + " last=" + (ppu.last_function ? ppu.last_function : "none"));
            const auto& history = ppu.syscall_history;
            const u64 count = std::min<u64>({8, history.index, history.data.size()});
            for (u64 i = count; i > 0; --i)
            {
                const auto& call = history.data[(history.index - i) % history.data.size()];
                log_capture("EXECUTION recent call pc=" + std::to_string(call.cia) + " function=" +
                    (call.func_name ? call.func_name : "unknown") + " result=" + std::to_string(call.error));
            }
        });
        idm::select<named_thread<spu_thread>>([](u32 id, spu_thread& spu)
        {
            ++progress.spu_contexts;
            progress.spu_blocks += spu.block_counter;
            if (progress.spu_contexts <= 8) log_capture("EXECUTION joined SPU id=" + std::to_string(id) +
                " pc=" + std::to_string(spu.pc) + " native blocks=" + std::to_string(spu.block_counter));
        });
        progress.captured = true;
        log_capture("EXECUTION joined snapshot: PPU contexts=" + std::to_string(progress.ppu_contexts) +
            " native exec_bytes/4=" + std::to_string(progress.instructions) + " completed calls=" + std::to_string(progress.calls) +
            " SPU contexts=" + std::to_string(progress.spu_contexts) + " blocks=" + std::to_string(progress.spu_blocks));
    }
    catch (...) { progress.failed = true; ARMSX3StartupLog("EXECUTION stopped-context observation failed"); }
}

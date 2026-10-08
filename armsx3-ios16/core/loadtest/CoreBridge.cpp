// SPDX-License-Identifier: GPL-2.0-only
#include "Emu/System.h"
#include "Utilities/JIT.h"
#include "StartupLog.h"
#include <atomic>
#include <thread>
#include <vector>
// Read-only state inspection after dyld has run the real core constructors.
// This does not initialize a title, allocate a JIT, or start emulation threads.
extern "C" __attribute__((visibility("default"))) int armsx3_core_state()
{
    return static_cast<int>(Emu.GetStatus(false));
}

// Execute only synthetic return-value functions; never enter guest code or
// mutate published pages. Called off the UIKit main thread after core loading.
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_immutable_jit()
{
    ARMSX3StartupLog("P3 BEFORE generate and execute core immutable JIT function");
    const auto generate = [](unsigned value)
    {
        return build_function_asm<unsigned (*)()>("ios_execution_probe",
            [value](native_asm& c, auto& args)
            {
                (void)args;
                c.mov(asmjit::a64::w0, asmjit::Imm(value));
                c.ret(asmjit::a64::x30);
            });
    };
    const auto first = generate(42);
    if (!first || first() != 42)
    {
        ARMSX3StartupLog("P3 FAIL: initial generated function result");
        return -1;
    }
    ARMSX3StartupLog("P3 first core generated function returned 42");
    std::atomic<bool> correct{true};
    std::vector<std::thread> workers;
    for (unsigned worker = 0; worker < 4; ++worker)
    {
        workers.emplace_back([&, worker]
        {
            for (unsigned iteration = 0; iteration < 16; ++iteration)
            {
                const unsigned expected = 84 + worker * 16 + iteration;
                const auto next = generate(expected);
                if (!next || next() != expected || first() != 42)
                    correct.store(false, std::memory_order_relaxed);
            }
        });
    }
    for (auto& worker : workers) worker.join();
    if (!correct.load(std::memory_order_relaxed))
    {
        ARMSX3StartupLog("P3 FAIL: concurrent immutable publication/execution result");
        return -2;
    }
    ARMSX3StartupLog("P3 PASS: 65 generated core functions executed; four workers; original function remains 42");
    return 0;
}

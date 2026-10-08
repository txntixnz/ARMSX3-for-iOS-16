// SPDX-License-Identifier: GPL-2.0-only
#include "Emu/System.h"
#include "Utilities/JIT.h"
#include "StartupLog.h"
#include "Utilities/File.h"
#include "Emu/system_config_types.h"
#include "Emu/Memory/vm.h"
#include <cstdio>
#include "util/logs.hpp"
#include <exception>
#include <stdexcept>
#include <string>
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

namespace
{
class InitLog final : public logs::listener
{
public:
    std::atomic<unsigned> errors{0};
    void log(u64 stamp, const logs::message& message, std::string_view prefix, std::string_view text) override
    {
        (void)stamp;
        const logs::level level = message;
        if (level == logs::level::fatal || level == logs::level::error)
            errors.fetch_add(1, std::memory_order_relaxed);
        std::string line = "P4 core: ";
        line.append(prefix);
        line.append(text);
        ARMSX3StartupLog(line.c_str());
    }
};
}

extern "C" __attribute__((visibility("default"))) int armsx3_core_initialize()
{
    // Keep this listener alive as long as the core. Never unregister it while
    // core threads might log; the dylib is retained for process lifetime.
    static InitLog* log = []
    {
        auto* listener = new InitLog;
        logs::listener::add(listener);
        return listener;
    }();
    log->errors.store(0, std::memory_order_relaxed);
    ARMSX3StartupLog("P4 BEFORE emulator initialization; no game requested");
    try
    {
        ARMSX3StartupLog(("P4 config directory: " + fs::get_config_dir()).c_str());
        ARMSX3StartupLog(("P4 cache directory: " + fs::get_cache_dir()).c_str());
        Emu.SetHasGui(false);
        Emu.SetHeadless(true);
        Emu.SetSupportedRenderers({video_renderer::null});
        Emu.SetDefaultRenderer(video_renderer::null);
        Emu.Init();
        ARMSX3StartupLog("P4 AFTER Emu.Init returned");
        // Init can report filesystem errors without throwing; do not mistake
        // a return for complete storage initialization.
        if (log->errors.load(std::memory_order_relaxed))
        {
            ARMSX3StartupLog("P4 initialization reported core errors; inspect preceding messages");
            return -2;
        }
        if (!fs::is_file(fs::get_config_dir() + "config.yml"))
        {
            ARMSX3StartupLog("P4 FAIL: expected config.yml was not created");
            return -3;
        }
        ARMSX3StartupLog("P4 PASS: emulator initialization returned without core errors; config.yml exists");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        return -1;
    }
    catch (...)
    {
        ARMSX3StartupLog("P4 initialization threw an unknown exception");
        return -1;
    }
}

extern "C" __attribute__((visibility("default"))) int armsx3_core_test_guest_memory()
{
    ARMSX3StartupLog("P5 BEFORE vm::init; no PS3 program requested");
    bool initialized = false;
    try
    {
        vm::init();
        initialized = true;
        ARMSX3StartupLog("P5 AFTER vm::init; guest allocator setup pending");
        // Reserve a small test region through the real core API. No guest
        // threads run, and no compiled guest instructions are entered.
        if (!vm::reserve_map(vm::main, 0x10000, 0x20000))
            throw std::runtime_error("P5 could not reserve test guest region");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address)
            throw std::runtime_error("P5 guest allocation returned zero");
        char message[128];
        std::snprintf(message, sizeof(message), "P5 allocated 64 KiB at guest address 0x%08x", address);
        ARMSX3StartupLog(message);
        if (!vm::check_addr(address, vm::page_readable | vm::page_writable, 0x10000))
            throw std::runtime_error("P5 guest page flags are not readable/writable");
        auto* normal = static_cast<volatile unsigned char*>(vm::base(address));
        auto* alias = reinterpret_cast<volatile unsigned char*>(vm::g_sudo_addr + address);
        // Exercise every 4 KiB guest boundary, including the four subpages of
        // each 16 KiB iPhone host page, in both directions through shared aliases.
        for (unsigned offset = 0; offset < 0x10000; ++offset)
            normal[offset] = static_cast<unsigned char>((offset * 17 + 42) & 255);
        for (unsigned offset = 0; offset < 0x10000; ++offset)
            if (alias[offset] != static_cast<unsigned char>((offset * 17 + 42) & 255))
                throw std::runtime_error("P5 normal-to-alias data mismatch");
        for (unsigned offset = 0; offset < 0x10000; ++offset)
            alias[offset] = static_cast<unsigned char>((offset * 29 + 84) & 255);
        for (unsigned offset = 0; offset < 0x10000; ++offset)
            if (normal[offset] != static_cast<unsigned char>((offset * 29 + 84) & 255))
                throw std::runtime_error("P5 alias-to-normal data mismatch");
        ARMSX3StartupLog("P5 PASS: 64 KiB guest allocation shares data through both core aliases");
        if (vm::dealloc(address, vm::main) != 0x10000)
            throw std::runtime_error("P5 deallocation returned unexpected size");
        if (vm::check_addr(address, vm::page_readable))
            throw std::runtime_error("P5 guest page remains logically allocated after free");
        ARMSX3StartupLog("P5 AFTER guest deallocation; BEFORE vm::close");
        vm::close();
        initialized = false;
        ARMSX3StartupLog("P5 PASS: guest allocation, shared data, deallocation and VM cleanup completed");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        if (initialized)
        {
            ARMSX3StartupLog("P5 cleaning up VM after failed memory test");
            vm::close();
        }
        return -1;
    }
}

// SPDX-License-Identifier: GPL-2.0-only
#include "Emu/System.h"
#include "Utilities/JIT.h"
#include "StartupLog.h"
#include "Utilities/File.h"
#include "Emu/system_config_types.h"
#include "Emu/Memory/vm.h"
#include "Emu/Cell/PPUThread.h"
#include "Emu/Cell/PPUInterpreter.h"
#include "Emu/IdManager.h"
#include <array>
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


// Real core PPU decoder/handlers, bounded straight-line instruction chain.
// No firmware, scheduler, guest syscalls, renderer or mutable JIT is entered.
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_ppu_instructions()
{
    ARMSX3StartupLog("P6 BEFORE guest VM setup for PPU instruction test");
    bool initialized = false;
    try
    {
        vm::init();
        initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x20000))
            throw std::runtime_error("P6 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P6 guest allocation failed");
        ARMSX3StartupLog("P6 AFTER guest allocation; BEFORE PPU context construction");
        {
            const ppu_thread_params params{static_cast<vm::addr_t>(address + 0x1000), 0x8000, 0, {}, 0, 0};
            // The production registry already owns named_thread<ppu_thread>.
            // Registering raw ppu_thread creates conflicting savestate metadata
            // during dlopen. This isolated probe needs only a CPU register state.
            struct ContextDeleter
            {
                void operator()(ppu_thread* context) const
                {
                    delete context;
                    // Direct execution never enters cpu_task's cleanup wrapper.
                    cpu_thread::g_threads_deleted++;
                }
            };
            std::unique_ptr<ppu_thread, ContextDeleter> ppu;
            {
                // Constructor expects IDM's thread-local construction ID. Supply
                // a valid PPU class ID only while constructing this private state;
                // restore the worker's previous value even if construction throws.
                struct ConstructionID
                {
                    u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; }
                } construction_id;
                ppu.reset(new ppu_thread(params, "iOS PPU instruction probe", 1000));
            }
            ARMSX3StartupLog("P6 AFTER PPU context; BEFORE core interpreter decoder");
            // The decoder table is about 1 MiB: keep it off the GCD worker stack.
            auto interpreter = std::make_unique<ppu_interpreter_rt>();
            const auto dform = [](u32 primary, u32 reg, u32 base, u32 immediate)
            {
                return (primary << 26) | (reg << 21) | (base << 16) | (immediate & 0xffff);
            };
            const std::array<u32, 11> program{
                dform(14, 3, 0, 42),        // addi r3,r0,42
                dform(14, 4, 0, 0xfff9),    // addi r4,r0,-7
                (31u << 26) | (5u << 21) | (3u << 16) | (4u << 11) | (266u << 1), // add r5,r3,r4
                dform(36, 5, 6, 0),         // stw r5,0(r6)
                dform(32, 7, 6, 0),         // lwz r7,0(r6)
                dform(24, 7, 8, 0x100),     // ori r8,r7,0x100
                dform(14, 11, 0, 0xffff),   // addi r11,r0,-1
                dform(15, 9, 0, 0x8000),    // addis r9,r0,0x8000
                dform(24, 9, 9, 1),         // ori r9,r9,1
                dform(36, 9, 6, 4),         // stw r9,4(r6)
                dform(32, 10, 6, 4),        // lwz r10,4(r6)
            };
            // One readable padding opcode is consumed when the last handler
            // advances to our terminating callback; it is never executed.
            auto* code = reinterpret_cast<be_t<u32>*>(vm::base(address));
            std::array<ppu_intrp_func, program.size() + 1> functions{};
            for (std::size_t index = 0; index < program.size(); ++index)
            {
                code[index] = program[index];
                functions[index].fn = interpreter->decode(program[index]);
                if (!functions[index].fn) throw std::runtime_error("P6 instruction decode failed");
            }
            code[program.size()] = 0;
            functions.back().fn = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*)
            {
                // Dedicated unused register records that the bounded chain ended.
                context.gpr[31] = 0x5036494f53ull;
            };
            ppu->gpr[6] = address + 0x100;
            ppu->gpr[31] = 0;
            ppu->cia = address;
            ARMSX3StartupLog("P6 BEFORE executing 11 guest PowerPC instructions via core PPU interpreter");
            functions[0].fn(*ppu, {program[0]}, code, functions.data() + 1);
            ARMSX3StartupLog("P6 AFTER core PPU instruction chain returned");
            if (ppu->gpr[3] != 42 || ppu->gpr[4] != 0xfffffffffffffff9ull ||
                ppu->gpr[5] != 35 || ppu->gpr[7] != 35 || ppu->gpr[8] != 0x123 ||
                ppu->gpr[11] != 0xffffffffffffffffull || ppu->gpr[9] != 0xffffffff80000001ull ||
                ppu->gpr[10] != 0x80000001ull || ppu->gpr[31] != 0x5036494f53ull)
                throw std::runtime_error("P6 guest register result mismatch");
            const auto* data = static_cast<const unsigned char*>(vm::base(address + 0x100));
            const std::array<unsigned char, 8> expected{0, 0, 0, 35, 0x80, 0, 0, 1};
            for (std::size_t index = 0; index < expected.size(); ++index)
                if (data[index] != expected[index]) throw std::runtime_error("P6 big-endian guest store mismatch");
            ARMSX3StartupLog("P6 PASS: arithmetic, sign extension, logical operations, guest stores and zero-extending loads");
        }
        ARMSX3StartupLog("P6 AFTER PPU context cleanup; BEFORE guest VM cleanup");
        if (vm::dealloc(address, vm::main) != 0x10000)
            throw std::runtime_error("P6 guest deallocation failed");
        vm::close();
        initialized = false;
        ARMSX3StartupLog("P6 PASS: 11 real PPU instructions and VM cleanup completed; no game boot tested");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        if (initialized) vm::close();
        return -1;
    }
}


// Test actual branch handlers with a bounded diagnostic dispatch loop.
// The normal scheduler, syscalls and mutable JIT are still outside this probe.
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_ppu_control_flow()
{
    ARMSX3StartupLog("P7 BEFORE guest VM setup for PPU branches and loops");
    bool initialized = false;
    try
    {
        vm::init();
        initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x20000))
            throw std::runtime_error("P7 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P7 guest allocation failed");
        ARMSX3StartupLog("P7 AFTER guest allocation; BEFORE private PPU context");
        {
            const ppu_thread_params params{static_cast<vm::addr_t>(address + 0x1000), 0x8000, 0, {}, 0, 0};
            // The production registry already owns named_thread<ppu_thread>.
            // Registering raw ppu_thread creates conflicting savestate metadata
            // during dlopen. This isolated probe needs only a CPU register state.
            struct ContextDeleter
            {
                void operator()(ppu_thread* context) const
                {
                    delete context;
                    // Direct execution never enters cpu_task's cleanup wrapper.
                    cpu_thread::g_threads_deleted++;
                }
            };
            std::unique_ptr<ppu_thread, ContextDeleter> ppu;
            {
                // Constructor expects IDM's thread-local construction ID. Supply
                // a valid PPU class ID only while constructing this private state;
                // restore the worker's previous value even if construction throws.
                struct ConstructionID
                {
                    u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; }
                } construction_id;
                ppu.reset(new ppu_thread(params, "iOS PPU instruction probe", 1000));
            }

            auto interpreter = std::make_unique<ppu_interpreter_rt>();
            using namespace ppu_instructions;
            using namespace ppu_instructions::implicts;
            for (const u32 count : {1u, 10u, 64u})
            {
                const std::array<u32, 18> program{
                    LI(3, 0),                       // 0 accumulator = 0
                    MTCTR(4),                       // 1 CTR = supplied loop count
                    ADDI(3, 3, 1),                  // 2 accumulator++
                    BC(16, 0, -4),                  // 3 bdnz back to 2
                    CMPWI(3, count),                // 4 loop result
                    BNE(40),                        // 5 fail at 15 if wrong
                    B(24, false, true),             // 6 bl subroutine at 12
                    STW(3, 6, 0),                   // 7 store returned value
                    LWZ(7, 6, 0),                   // 8 reload
                    CMPWI(7, count + 5),            // 9 memory result
                    BEQ(32),                        // 10 success exit at 18
                    B(16),                          // 11 fail at 15
                    ADDI(3, 3, 5),                  // 12 subroutine
                    BLR(),                          // 13 return to 7
                    LI(12, 0xdead),                 // 14 must be skipped
                    LI(12, 0xbad),                  // 15 failure marker
                    B(8),                           // 16 exit at 18
                    NOP(),                          // 17 must be skipped
                };
                auto* code = reinterpret_cast<be_t<u32>*>(vm::base(address));
                for (std::size_t index = 0; index < program.size(); ++index)
                    code[index] = program[index];
                code[program.size()] = 0; // readable padding for handler transition
                ppu_intrp_func boundary{+[](ppu_thread& context, ppu_opcode_t, be_t<u32>* next, ppu_intrp_func*)
                {
                    // Ordinary handlers tail-call this after one instruction.
                    // Taken branch handlers return directly with their target CIA.
                    context.cia = vm::get_addr(next);
                }};
                ppu->gpr[4] = count;
                ppu->gpr[6] = address + 0x100;
                ppu->gpr[12] = 0;
                ppu->ctr = 0;
                ppu->lr = 0;
                ppu->cia = address;
                u32 steps = 0;
                char stage[180];
                std::snprintf(stage, sizeof(stage), "P7 BEFORE core branch program: loop count=%u, instruction budget=512", count);
                ARMSX3StartupLog(stage);
                while (ppu->cia != address + program.size() * 4)
                {
                    const u32 offset = ppu->cia - address;
                    if (offset % 4 || offset >= program.size() * 4)
                        throw std::runtime_error("P7 branch target outside diagnostic program");
                    if (++steps > 512) throw std::runtime_error("P7 instruction budget exceeded");
                    auto* instruction = code + offset / 4;
                    const u32 opcode = *instruction;
                    const auto handler = interpreter->decode(opcode);
                    if (!handler) throw std::runtime_error("P7 instruction decode failed");
                    handler(*ppu, {opcode}, instruction, &boundary);
                }
                if (ppu->gpr[3] != count + 5 || ppu->gpr[7] != count + 5 ||
                    ppu->gpr[12] != 0 || ppu->ctr != 0 || ppu->lr != address + 7 * 4 ||
                    steps != count * 2 + 11)
                    throw std::runtime_error("P7 branch, counter, return address or result mismatch");
                const auto* data = static_cast<const unsigned char*>(vm::base(address + 0x100));
                if (data[0] || data[1] || data[2] || data[3] != count + 5)
                    throw std::runtime_error("P7 big-endian result mismatch");
                std::snprintf(stage, sizeof(stage), "P7 PASS: loop count=%u, executed=%u, result=%u, CTR=0, link/return correct", count, steps, count + 5);
                ARMSX3StartupLog(stage);
            }
        }
        if (vm::dealloc(address, vm::main) != 0x10000)
            throw std::runtime_error("P7 guest deallocation failed");
        vm::close();
        initialized = false;
        ARMSX3StartupLog("P7 PASS: core PPU loops, conditional branches, call/return and cleanup; no game boot tested");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        if (initialized) vm::close();
        return -1;
    }
}

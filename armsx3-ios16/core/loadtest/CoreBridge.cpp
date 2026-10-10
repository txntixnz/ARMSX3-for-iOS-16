// SPDX-License-Identifier: GPL-2.0-only
#include "Emu/System.h"
#include "Utilities/JIT.h"
#include "StartupLog.h"
#include "Utilities/File.h"
#include "Emu/system_config_types.h"
#include "Emu/Memory/vm.h"
#include "Emu/Memory/vm_locking.h"
#include "Emu/Cell/PPUThread.h"
#include "Emu/Cell/PPUInterpreter.h"
#include "Emu/Cell/SPUThread.h"
#include "Emu/Cell/SPUInterpreter.h"
#include "Emu/system_config.h"
#include "Emu/IdManager.h"
#include <array>
#include <cstdio>
#include <cstring>
#include "util/logs.hpp"
#include <exception>
#include <stdexcept>
#include <string>
#include <atomic>
#include <thread>
#include <vector>
#include <utility>
#include "Utilities/Thread.h"
#include "Utilities/sync.h"
#include "util/vm.hpp"
#include "Loader/ELF.h"
#include "Emu/Cell/PPUAnalyser.h"
#include "Emu/Cell/PPUFunction.h"
#include "Emu/Cell/lv2/sys_sync.h"
#include <chrono>
#include <cerrno>
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


extern "C" __attribute__((visibility("default"))) int armsx3_core_test_spu_instructions()
{
    ARMSX3StartupLog("P8 BEFORE guest VM setup for SPU instructions");
    bool initialized = false;
    try
    {
        vm::init();
        initialized = true;
        {
            struct ContextDeleter
            {
                void operator()(spu_thread* context) const
                {
                    // cleanup() assumes a production named_thread and an LV2
                    // local-store allocation; neither exists in this private probe.
                    vm::free_range_lock(context->range_lock);
                    delete context; // unmaps all LS mirrors and releases reservation
                    cpu_thread::g_threads_deleted++;
                }
            };
            std::unique_ptr<spu_thread, ContextDeleter> spu;
            {
                struct ConstructionSettings
                {
                    u32 previous_id = id_manager::g_id;
                    spu_decoder_type previous_decoder = g_cfg.core.spu_decoder.get();
                    ConstructionSettings()
                    {
                        id_manager::g_id = spu_thread::id_base;
                        g_cfg.core.spu_decoder.set(spu_decoder_type::_static);
                    }
                    ~ConstructionSettings()
                    {
                        g_cfg.core.spu_decoder.set(previous_decoder);
                        id_manager::g_id = previous_id;
                    }
                } settings;
                ARMSX3StartupLog("P8 BEFORE private SPU context construction; interpreter selected");
                spu.reset(new spu_thread(nullptr, 0, "iOS SPU instruction probe", 0));
            }
            ARMSX3StartupLog("P8 AFTER SPU context; BEFORE local-store mirror mappings");
            spu_thread::map_ls(*spu->shm, spu->ls);
            ARMSX3StartupLog("P8 AFTER 256 KiB SPU local store and five shared views mapped");
            auto interpreter = std::make_unique<spu_interpreter_rt>();
            const auto il = [](u32 reg, s32 value)
            {
                spu_opcode_t op{0x81u << 23};
                op.rt = reg;
                op.si16 = value;
                return op.opcode;
            };
            const auto ri10 = [](u32 primary, u32 target, u32 base, s32 immediate)
            {
                spu_opcode_t op{primary << 24};
                op.rt = target;
                op.ra = base;
                op.si10 = immediate;
                return op.opcode;
            };
            spu_opcode_t add{0xc0u << 21};
            add.rt = 4;
            add.ra = 2;
            add.rb = 3;
            const std::array<u32, 8> program{
                il(2, 42), il(3, -7), add.opcode,
                ri10(0x1c, 5, 4, -3),       // AI -> four lanes of 32
                il(6, 0x100),
                ri10(0x24, 5, 6, 0),        // STQD to local store
                ri10(0x34, 7, 6, 0),        // LQD from local store
                ri10(0x44, 8, 7, -1),       // XORI -> four lanes of ~32
            };
            auto* code = spu->_ptr<u32>(0);
            for (std::size_t index = 0; index < program.size(); ++index)
                code[index] = program[index];
            ARMSX3StartupLog("P8 BEFORE executing eight real SPU instructions via core interpreter");
            spu->pc = 0;
            for (std::size_t index = 0; index < program.size(); ++index)
            {
                const u32 opcode = code[index];
                const auto handler = interpreter->decode(opcode);
                if (!handler || !handler(*spu, {opcode}))
                    throw std::runtime_error("P8 SPU instruction did not complete");
                spu->pc += 4;
            }
            ARMSX3StartupLog("P8 AFTER SPU instruction sequence returned");
            for (unsigned lane = 0; lane < 4; ++lane)
            {
                if (spu->gpr[2]._u32[lane] != 42 || spu->gpr[3]._u32[lane] != 0xfffffff9u ||
                    spu->gpr[4]._u32[lane] != 35 || spu->gpr[5]._u32[lane] != 32 ||
                    spu->gpr[7]._u32[lane] != 32 || spu->gpr[8]._u32[lane] != 0xffffffdfu)
                    throw std::runtime_error("P8 SPU SIMD lane result mismatch");
                const auto* data = spu->ls + 0x100 + lane * 4;
                if (data[0] || data[1] || data[2] || data[3] != 32)
                    throw std::runtime_error("P8 big-endian SPU quadword store mismatch");
            }
            // Exercise the real mirror mappings at the end of local storage.
            spu->_ref<u32>(SPU_LS_SIZE - 16) = 0x12345678;
            for (const s64 mirror : {-2ll, -1ll, 0ll, 1ll, 2ll})
            {
                const auto* word = reinterpret_cast<const be_t<u32>*>(spu->ls + mirror * SPU_LS_SIZE + SPU_LS_SIZE - 16);
                if (*word != 0x12345678) throw std::runtime_error("P8 SPU local-store mirror mismatch");
            }
            ARMSX3StartupLog("P8 PASS: eight SPU instructions, four SIMD lanes, big-endian local-store data and five mirrors");
        }
        ARMSX3StartupLog("P8 AFTER private SPU cleanup; BEFORE vm::close");
        vm::close();
        initialized = false;
        ARMSX3StartupLog("P8 PASS: SPU instructions, local memory and cleanup completed; no game boot tested");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        if (initialized) vm::close();
        return -1;
    }
}

extern "C" __attribute__((visibility("default"))) int armsx3_core_test_spu_dma()
{
    ARMSX3StartupLog("P9 BEFORE guest VM setup for SPU DMA");
    bool initialized = false;
    try
    {
        vm::init();
        initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x30000))
            throw std::runtime_error("P9 could not reserve DMA guest region");
        constexpr u32 guest_size = 0x20000;
        const u32 address = vm::alloc(guest_size, vm::main, 0x10000);
        if (!address || !vm::check_addr(address, vm::page_readable | vm::page_writable, guest_size))
            throw std::runtime_error("P9 guest DMA allocation failed");
        {
            // Baseline transfers only: no active RSX or competing guest CPUs.
            // Restore every setting before returning, including exception paths.
            struct DMASettings
            {
                bool accurate = g_cfg.core.spu_accurate_dma.get();
                bool strict = g_cfg.video.strict_rendering_mode.get();
                rsx_fifo_mode fifo = g_cfg.core.rsx_fifo_accuracy.get();
                DMASettings()
                {
                    g_cfg.core.spu_accurate_dma.set(false);
                    g_cfg.video.strict_rendering_mode.set(false);
                    g_cfg.core.rsx_fifo_accuracy.set(rsx_fifo_mode::fast);
                }
                ~DMASettings()
                {
                    g_cfg.core.rsx_fifo_accuracy.set(fifo);
                    g_cfg.video.strict_rendering_mode.set(strict);
                    g_cfg.core.spu_accurate_dma.set(accurate);
                }
            } dma_settings;
            struct ContextDeleter
            {
                void operator()(spu_thread* context) const
                {
                    // cleanup() assumes a production named_thread and an LV2
                    // local-store allocation; neither exists in this private probe.
                    vm::free_range_lock(context->range_lock);
                    delete context; // unmaps all LS mirrors and releases reservation
                    cpu_thread::g_threads_deleted++;
                }
            };
            std::unique_ptr<spu_thread, ContextDeleter> spu;
            {
                struct ConstructionSettings
                {
                    u32 previous_id = id_manager::g_id;
                    spu_decoder_type previous_decoder = g_cfg.core.spu_decoder.get();
                    ConstructionSettings()
                    {
                        id_manager::g_id = spu_thread::id_base;
                        g_cfg.core.spu_decoder.set(spu_decoder_type::_static);
                    }
                    ~ConstructionSettings()
                    {
                        g_cfg.core.spu_decoder.set(previous_decoder);
                        id_manager::g_id = previous_id;
                    }
                } settings;
                ARMSX3StartupLog("P9 BEFORE private SPU context construction; interpreter selected");
                spu.reset(new spu_thread(nullptr, 0, "iOS SPU DMA probe", 0));
            }
            ARMSX3StartupLog("P9 AFTER SPU context; BEFORE local-store mirror mappings");
            spu_thread::map_ls(*spu->shm, spu->ls);
            ARMSX3StartupLog("P9 AFTER 256 KiB SPU local store and five shared views mapped");
            auto* guest = vm::_ptr<u8>(address);
            auto* alias = reinterpret_cast<const u8*>(vm::g_sudo_addr + address);
            struct Transfer { u16 size; u32 offset; u32 lsa; };
            const std::array<Transfer, 8> transfers{{
                {1, 3, 3}, {2, 6, 6}, {4, 12, 12}, {8, 24, 24},
                {16, 0xff0, 0x1000}, {128, 0x3fc0, 0x2000},
                {256, 0xff80, SPU_LS_SIZE - 256},
                {16384, 0x3ff0, 0x8000},
            }};
            // Repeated passes also check that PUT range locks are released.
            for (u32 round = 0; round < 2; ++round)
            {
                for (const auto& transfer : transfers)
                {
                    if (transfer.offset + transfer.size > guest_size ||
                        transfer.lsa + transfer.size > SPU_LS_SIZE)
                        throw std::runtime_error("P9 DMA test span out of bounds");
                    std::memset(guest, 0xa5, guest_size);
                    std::memset(spu->ls, 0x5a, SPU_LS_SIZE);
                    const auto pattern = [round](u32 index) -> u8
                    {
                        return static_cast<u8>((index * 37 + 11 + round * 53) & 255);
                    };
                    for (u32 i = 0; i < transfer.size; ++i)
                        guest[transfer.offset + i] = pattern(i);
                    spu_mfc_cmd command{};
                    command.cmd = MFC_GET_CMD;
                    command.size = transfer.size;
                    command.lsa = transfer.lsa;
                    command.eal = address + transfer.offset;
                    char message[180];
                    std::snprintf(message, sizeof(message),
                        "P9 BEFORE core DMA GET: round=%u size=%u EA=0x%08x LS=0x%05x",
                        round + 1, unsigned(transfer.size), command.eal, command.lsa);
                    ARMSX3StartupLog(message);
                    spu_thread::do_dma_transfer(spu.get(), command, spu->ls);
                    for (u32 i = 0; i < SPU_LS_SIZE; ++i)
                    {
                        const bool inside = i >= transfer.lsa && i < transfer.lsa + transfer.size;
                        const u8 expected = inside ? pattern(i - transfer.lsa) : 0x5a;
                        if (spu->ls[i] != expected)
                            throw std::runtime_error("P9 GET data or local-store guard mismatch");
                    }
                    for (u32 i = 0; i < guest_size; ++i)
                    {
                        const bool inside = i >= transfer.offset && i < transfer.offset + transfer.size;
                        const u8 expected = inside ? pattern(i - transfer.offset) : 0xa5;
                        if (guest[i] != expected || alias[i] != expected)
                            throw std::runtime_error("P9 GET changed guest source or alias");
                    }
                    for (u32 i = 0; i < transfer.size; ++i)
                        spu->ls[transfer.lsa + i] = pattern(i) ^ 0xff;
                    command.cmd = MFC_PUT_CMD;
                    ARMSX3StartupLog("P9 BEFORE core DMA PUT of transformed local-store data");
                    spu_thread::do_dma_transfer(spu.get(), command, spu->ls);
                    for (u32 i = 0; i < guest_size; ++i)
                    {
                        const bool inside = i >= transfer.offset && i < transfer.offset + transfer.size;
                        const u8 expected = inside ? (pattern(i - transfer.offset) ^ 0xff) : 0xa5;
                        if (guest[i] != expected || alias[i] != expected)
                            throw std::runtime_error("P9 PUT data, guest guard or alias mismatch");
                    }
                    for (const s64 mirror : {-2ll, -1ll, 0ll, 1ll, 2ll})
                    {
                        const auto* view = spu->ls + mirror * SPU_LS_SIZE;
                        for (u32 i = 0; i < SPU_LS_SIZE; ++i)
                        {
                            const bool inside = i >= transfer.lsa && i < transfer.lsa + transfer.size;
                            const u8 expected = inside ? (pattern(i - transfer.lsa) ^ 0xff) : 0x5a;
                            if (view[i] != expected)
                                throw std::runtime_error("P9 PUT changed local store or shared mirror");
                        }
                    }
                    if (spu->range_lock->load() != 0)
                        throw std::runtime_error("P9 PUT left a guest range lock held");
                    std::snprintf(message, sizeof(message),
                        "P9 PASS: round=%u size=%u GET/PUT data, guards, guest aliases, LS mirrors and lock release",
                        round + 1, unsigned(transfer.size));
                    ARMSX3StartupLog(message);
                }
            }
        }
        ARMSX3StartupLog("P9 AFTER private SPU cleanup; BEFORE guest deallocation");
        if (vm::dealloc(address, vm::main) != guest_size)
            throw std::runtime_error("P9 guest deallocation size mismatch");
        if (vm::check_addr(address))
            throw std::runtime_error("P9 guest region still accessible after deallocation");
        vm::close();
        initialized = false;
        ARMSX3StartupLog("P9 PASS: 32 baseline DMA transfers and cleanup; channels, scheduling and game boot remain untested");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        if (initialized) vm::close();
        return -1;
    }
}

extern "C" __attribute__((visibility("default"))) int armsx3_core_test_spu_channels()
{
    ARMSX3StartupLog("P10 BEFORE guest VM setup for SPU DMA channels");
    bool initialized = false;
    try
    {
        vm::init();
        initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x30000))
            throw std::runtime_error("P10 could not reserve DMA guest region");
        constexpr u32 guest_size = 0x20000;
        const u32 address = vm::alloc(guest_size, vm::main, 0x10000);
        if (!address || !vm::check_addr(address, vm::page_readable | vm::page_writable, guest_size))
            throw std::runtime_error("P10 guest DMA allocation failed");
        {
            // Baseline transfers only: no active RSX or competing guest CPUs.
            // Restore every setting before returning, including exception paths.
            struct DMASettings
            {
                u32 shuffle = g_cfg.core.mfc_transfers_shuffling.get();
                u32 preferred = g_cfg.core.preferred_spu_threads.get();
                bool accurate = g_cfg.core.spu_accurate_dma.get();
                bool strict = g_cfg.video.strict_rendering_mode.get();
                rsx_fifo_mode fifo = g_cfg.core.rsx_fifo_accuracy.get();
                DMASettings()
                {
                    g_cfg.core.mfc_transfers_shuffling.set(0);
                    g_cfg.core.preferred_spu_threads.set(0);
                    g_cfg.core.spu_accurate_dma.set(false);
                    g_cfg.video.strict_rendering_mode.set(false);
                    g_cfg.core.rsx_fifo_accuracy.set(rsx_fifo_mode::fast);
                }
                ~DMASettings()
                {
                    g_cfg.core.rsx_fifo_accuracy.set(fifo);
                    g_cfg.video.strict_rendering_mode.set(strict);
                    g_cfg.core.spu_accurate_dma.set(accurate);
                    g_cfg.core.preferred_spu_threads.set(preferred);
                    g_cfg.core.mfc_transfers_shuffling.set(shuffle);
                }
            } dma_settings;
            struct ContextDeleter
            {
                void operator()(spu_thread* context) const
                {
                    // cleanup() assumes a production named_thread and an LV2
                    // local-store allocation; neither exists in this private probe.
                    vm::free_range_lock(context->range_lock);
                    delete context; // unmaps all LS mirrors and releases reservation
                    cpu_thread::g_threads_deleted++;
                }
            };
            std::unique_ptr<spu_thread, ContextDeleter> spu;
            {
                struct ConstructionSettings
                {
                    u32 previous_id = id_manager::g_id;
                    spu_decoder_type previous_decoder = g_cfg.core.spu_decoder.get();
                    ConstructionSettings()
                    {
                        id_manager::g_id = spu_thread::id_base;
                        g_cfg.core.spu_decoder.set(spu_decoder_type::_static);
                    }
                    ~ConstructionSettings()
                    {
                        g_cfg.core.spu_decoder.set(previous_decoder);
                        id_manager::g_id = previous_id;
                    }
                } settings;
                ARMSX3StartupLog("P10 BEFORE private SPU context construction; interpreter selected");
                spu.reset(new spu_thread(nullptr, 0, "iOS SPU channel probe", 0));
            }
            ARMSX3StartupLog("P10 AFTER SPU context; BEFORE local-store mirror mappings");
            spu_thread::map_ls(*spu->shm, spu->ls);
            ARMSX3StartupLog("P10 AFTER 256 KiB SPU local store and five shared views mapped");
            ARMSX3StartupLog("P10 BEFORE cpu_init to reset SPU channels and DMA fence masks");
            spu->cpu_init();
            ARMSX3StartupLog("P10 AFTER cpu_init; channel transfer sequence pending");
            const auto write_channel = [&](u32 channel, u32 value)
            {
                if (!spu->set_ch_value(channel, value))
                    throw std::runtime_error("P10 channel write did not complete");
            };
            // Never read an empty channel: that enters the production wait path.
            const auto read_ready = [&](u32 channel) -> u32
            {
                if (spu->get_ch_count(channel) != 1)
                    throw std::runtime_error("P10 channel was not ready before read");
                const s64 value = spu->get_ch_value(channel);
                if (value < 0 || static_cast<u64>(value) > 0xffffffffull)
                    throw std::runtime_error("P10 channel read did not return a 32-bit result");
                return static_cast<u32>(value);
            };
            const auto completion = [&](u32 mask, u32 mode)
            {
                if (spu->get_ch_count(MFC_RdTagStat) != 0)
                    throw std::runtime_error("P10 stale completion status before request");
                write_channel(MFC_WrTagMask, mask);
                if (read_ready(MFC_RdTagMask) != mask)
                    throw std::runtime_error("P10 tag mask readback mismatch");
                write_channel(MFC_WrTagUpdate, mode);
                if (read_ready(MFC_RdTagStat) != mask)
                    throw std::runtime_error("P10 completion mask mismatch");
                if (spu->get_ch_count(MFC_RdTagStat) != 0)
                    throw std::runtime_error("P10 tag status read did not consume result");
            };
            const auto submit = [&](const spu_mfc_cmd& command)
            {
                if (spu->get_ch_count(MFC_Cmd) != 16 || spu->mfc_size != 0)
                    throw std::runtime_error("P10 MFC capacity mismatch before submission");
                write_channel(MFC_LSA, command.lsa);
                write_channel(MFC_EAH, command.eah);
                write_channel(MFC_EAL, command.eal);
                write_channel(MFC_Size, command.size);
                write_channel(MFC_TagID, command.tag);
                // Writing the command invokes the production process_mfc_cmd.
                write_channel(MFC_Cmd, command.cmd);
                if (spu->mfc_size || spu->mfc_fence || spu->mfc_barrier ||
                    spu->get_ch_count(MFC_Cmd) != 16)
                    throw std::runtime_error("P10 synchronous command did not complete");
                const u32 mask = 1u << command.tag;
                for (const u32 mode : {u32(MFC_TAG_UPDATE_IMMEDIATE), u32(MFC_TAG_UPDATE_ANY), u32(MFC_TAG_UPDATE_ALL)})
                    completion(mask, mode);
            };
            completion(0, MFC_TAG_UPDATE_IMMEDIATE);
            auto* guest = vm::_ptr<u8>(address);
            auto* alias = reinterpret_cast<const u8*>(vm::g_sudo_addr + address);
            struct Transfer { u16 size; u32 offset; u32 lsa; };
            const std::array<Transfer, 8> transfers{{
                {1, 3, 3}, {2, 6, 6}, {4, 12, 12}, {8, 24, 24},
                {16, 0xff0, 0x1000}, {128, 0x3fc0, 0x2000},
                {256, 0xff80, SPU_LS_SIZE - 256},
                {16384, 0x3ff0, 0x8000},
            }};
            // Repeated passes also check that PUT range locks are released.
            u32 transfer_index = 0;
            for (u32 round = 0; round < 2; ++round)
            {
                for (const auto& transfer : transfers)
                {
                    if (transfer.offset + transfer.size > guest_size ||
                        transfer.lsa + transfer.size > SPU_LS_SIZE)
                        throw std::runtime_error("P10 DMA test span out of bounds");
                    std::memset(guest, 0xa5, guest_size);
                    std::memset(spu->ls, 0x5a, SPU_LS_SIZE);
                    const auto pattern = [round](u32 index) -> u8
                    {
                        return static_cast<u8>((index * 37 + 11 + round * 53) & 255);
                    };
                    for (u32 i = 0; i < transfer.size; ++i)
                        guest[transfer.offset + i] = pattern(i);
                    spu_mfc_cmd command{};
                    command.cmd = MFC_GET_CMD;
                    constexpr std::array<u8, 3> tags{0, 7, 31};
                    command.tag = tags[transfer_index++ % tags.size()];
                    command.size = transfer.size;
                    command.lsa = transfer.lsa;
                    command.eal = address + transfer.offset;
                    char message[180];
                    std::snprintf(message, sizeof(message),
                        "P10 BEFORE channel DMA GET: round=%u size=%u EA=0x%08x LS=0x%05x",
                        round + 1, unsigned(transfer.size), command.eal, command.lsa);
                    ARMSX3StartupLog(message);
                    submit(command);
                    for (u32 i = 0; i < SPU_LS_SIZE; ++i)
                    {
                        const bool inside = i >= transfer.lsa && i < transfer.lsa + transfer.size;
                        const u8 expected = inside ? pattern(i - transfer.lsa) : 0x5a;
                        if (spu->ls[i] != expected)
                            throw std::runtime_error("P10 GET data or local-store guard mismatch");
                    }
                    for (u32 i = 0; i < guest_size; ++i)
                    {
                        const bool inside = i >= transfer.offset && i < transfer.offset + transfer.size;
                        const u8 expected = inside ? pattern(i - transfer.offset) : 0xa5;
                        if (guest[i] != expected || alias[i] != expected)
                            throw std::runtime_error("P10 GET changed guest source or alias");
                    }
                    for (u32 i = 0; i < transfer.size; ++i)
                        spu->ls[transfer.lsa + i] = pattern(i) ^ 0xff;
                    command.cmd = MFC_PUT_CMD;
                    ARMSX3StartupLog("P10 BEFORE channel DMA PUT of transformed local-store data");
                    submit(command);
                    for (u32 i = 0; i < guest_size; ++i)
                    {
                        const bool inside = i >= transfer.offset && i < transfer.offset + transfer.size;
                        const u8 expected = inside ? (pattern(i - transfer.offset) ^ 0xff) : 0xa5;
                        if (guest[i] != expected || alias[i] != expected)
                            throw std::runtime_error("P10 PUT data, guest guard or alias mismatch");
                    }
                    for (const s64 mirror : {-2ll, -1ll, 0ll, 1ll, 2ll})
                    {
                        const auto* view = spu->ls + mirror * SPU_LS_SIZE;
                        for (u32 i = 0; i < SPU_LS_SIZE; ++i)
                        {
                            const bool inside = i >= transfer.lsa && i < transfer.lsa + transfer.size;
                            const u8 expected = inside ? (pattern(i - transfer.lsa) ^ 0xff) : 0x5a;
                            if (view[i] != expected)
                                throw std::runtime_error("P10 PUT changed local store or shared mirror");
                        }
                    }
                    if (spu->range_lock->load() != 0)
                        throw std::runtime_error("P10 PUT left a guest range lock held");
                    std::snprintf(message, sizeof(message),
                        "P10 PASS: round=%u size=%u channel GET/PUT, all completion modes, guards, aliases and lock release",
                        round + 1, unsigned(transfer.size));
                    ARMSX3StartupLog(message);
                }
            }
            completion((1u << 0) | (1u << 7) | (1u << 31), MFC_TAG_UPDATE_ALL);
        }
        ARMSX3StartupLog("P10 AFTER private SPU cleanup; BEFORE guest deallocation");
        if (vm::dealloc(address, vm::main) != guest_size)
            throw std::runtime_error("P10 guest deallocation size mismatch");
        if (vm::check_addr(address))
            throw std::runtime_error("P10 guest region still accessible after deallocation");
        vm::close();
        initialized = false;
        ARMSX3StartupLog("P10 PASS: 32 channel DMA transfers, completion tags and cleanup; queued DMA, scheduling and game boot remain untested");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        if (initialized) vm::close();
        return -1;
    }
}

extern "C" __attribute__((visibility("default"))) int armsx3_core_test_spu_queue()
{
    ARMSX3StartupLog("P11 BEFORE guest VM setup for queued SPU DMA");
    bool initialized = false;
    try
    {
        vm::init();
        initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x30000))
            throw std::runtime_error("P11 could not reserve DMA guest region");
        constexpr u32 guest_size = 0x20000;
        const u32 address = vm::alloc(guest_size, vm::main, 0x10000);
        if (!address || !vm::check_addr(address, vm::page_readable | vm::page_writable, guest_size))
            throw std::runtime_error("P11 guest DMA allocation failed");
        {
            // Baseline transfers only: no active RSX or competing guest CPUs.
            // Restore every setting before returning, including exception paths.
            struct DMASettings
            {
                bool steps = g_cfg.core.mfc_shuffling_in_steps.get();
                u32 shuffle = g_cfg.core.mfc_transfers_shuffling.get();
                u32 preferred = g_cfg.core.preferred_spu_threads.get();
                bool accurate = g_cfg.core.spu_accurate_dma.get();
                bool strict = g_cfg.video.strict_rendering_mode.get();
                rsx_fifo_mode fifo = g_cfg.core.rsx_fifo_accuracy.get();
                DMASettings()
                {
                    g_cfg.core.mfc_transfers_shuffling.set(16);
                    g_cfg.core.mfc_shuffling_in_steps.set(true);
                    g_cfg.core.preferred_spu_threads.set(0);
                    g_cfg.core.spu_accurate_dma.set(false);
                    g_cfg.video.strict_rendering_mode.set(false);
                    g_cfg.core.rsx_fifo_accuracy.set(rsx_fifo_mode::fast);
                }
                ~DMASettings()
                {
                    g_cfg.core.rsx_fifo_accuracy.set(fifo);
                    g_cfg.video.strict_rendering_mode.set(strict);
                    g_cfg.core.spu_accurate_dma.set(accurate);
                    g_cfg.core.preferred_spu_threads.set(preferred);
                    g_cfg.core.mfc_transfers_shuffling.set(shuffle);
                    g_cfg.core.mfc_shuffling_in_steps.set(steps);
                }
            } dma_settings;
            struct ContextDeleter
            {
                void operator()(spu_thread* context) const
                {
                    // cleanup() assumes a production named_thread and an LV2
                    // local-store allocation; neither exists in this private probe.
                    vm::free_range_lock(context->range_lock);
                    delete context; // unmaps all LS mirrors and releases reservation
                    cpu_thread::g_threads_deleted++;
                }
            };
            std::unique_ptr<spu_thread, ContextDeleter> spu;
            {
                struct ConstructionSettings
                {
                    u32 previous_id = id_manager::g_id;
                    spu_decoder_type previous_decoder = g_cfg.core.spu_decoder.get();
                    ConstructionSettings()
                    {
                        id_manager::g_id = spu_thread::id_base;
                        g_cfg.core.spu_decoder.set(spu_decoder_type::_static);
                    }
                    ~ConstructionSettings()
                    {
                        g_cfg.core.spu_decoder.set(previous_decoder);
                        id_manager::g_id = previous_id;
                    }
                } settings;
                ARMSX3StartupLog("P11 BEFORE private SPU context construction; interpreter selected");
                spu.reset(new spu_thread(nullptr, 0, "iOS SPU queue probe", 0));
            }
            ARMSX3StartupLog("P11 AFTER SPU context; BEFORE local-store mirror mappings");
            spu_thread::map_ls(*spu->shm, spu->ls);
            ARMSX3StartupLog("P11 AFTER 256 KiB SPU local store and five shared views mapped");
            ARMSX3StartupLog("P11 BEFORE cpu_init to reset SPU channels and DMA fence masks");
            spu->cpu_init();
            ARMSX3StartupLog("P11 AFTER cpu_init; channel transfer sequence pending");
            const auto write = [&](u32 channel, u32 value)
            {
                if (!spu->set_ch_value(channel, value))
                    throw std::runtime_error("P11 channel write failed");
            };
            const auto enqueue = [&](MFC cmd, u8 tag, u32 ea, u32 lsa, u16 size)
            {
                const u32 before = spu->mfc_size;
                if (before >= 16 || spu->get_ch_count(MFC_Cmd) != 16 - before)
                    throw std::runtime_error("P11 command queue capacity mismatch");
                write(MFC_LSA, lsa); write(MFC_EAH, 0); write(MFC_EAL, ea);
                write(MFC_Size, size); write(MFC_TagID, tag); write(MFC_Cmd, cmd);
                if (spu->mfc_size != before + 1 || spu->get_ch_count(MFC_Cmd) != 15 - before)
                    throw std::runtime_error("P11 command did not remain queued");
            };
            const auto drain = [&](u32 mask)
            {
                write(MFC_WrTagMask, mask);
                if (spu->get_mfc_completed() != 0)
                    throw std::runtime_error("P11 pending tags reported completion too early");
                // Do not read RdTagStat here: its production read path drains
                // pending DMA automatically. Check count without blocking.
                for (const u32 mode : {u32(MFC_TAG_UPDATE_ANY), u32(MFC_TAG_UPDATE_ALL)})
                {
                    write(MFC_WrTagUpdate, mode);
                    if (spu->get_ch_count(MFC_RdTagStat))
                        throw std::runtime_error("P11 tag status ready before queued DMA");
                }
                g_cfg.core.mfc_transfers_shuffling.set(2);
                u32 passes = 0;
                while (spu->mfc_size && passes < 256)
                {
                    // One shuffled pass per call; never enter the scheduler or
                    // the unbounded must_finish loop, and never escape to JIT.
                    spu->do_mfc(false, false);
                    ++passes;
                }
                g_cfg.core.mfc_transfers_shuffling.set(16);
                if (spu->mfc_size || spu->mfc_fence || spu->mfc_barrier ||
                    spu->get_ch_count(MFC_Cmd) != 16 || spu->range_lock->load())
                    throw std::runtime_error("P11 queue did not drain within pass budget");
                if (spu->get_ch_count(MFC_RdTagStat) != 1 || spu->get_mfc_completed() != mask)
                    throw std::runtime_error("P11 queued ALL completion was not published");
                const s64 result = spu->get_ch_value(MFC_RdTagStat);
                if (result != mask || spu->get_ch_count(MFC_RdTagStat))
                    throw std::runtime_error("P11 queued completion read/consume mismatch");
                char message[128];
                std::snprintf(message, sizeof(message), "P11 queue drained: passes=%u completed tags=0x%08x", passes, mask);
                ARMSX3StartupLog(message);
            };
            auto* guest = vm::_ptr<u8>(address);
            auto* alias = reinterpret_cast<const u8*>(vm::g_sudo_addr + address);
            constexpr u32 source_offset = 0x1000, destination_offset = 0x8000;
            constexpr u32 first_ls = 0x1000, result_ls = 0x2000;
            constexpr u16 size = 128;
            for (u32 round = 0; round < 8; ++round)
            {
                for (u32 kind = 0; kind < 3; ++kind)
                {
                    spu->cpu_init();
                    std::memset(guest, 0xa5, guest_size);
                    std::memset(spu->ls, 0x5a, SPU_LS_SIZE);
                    const auto pattern = [round, kind](u32 i) -> u8
                    { return static_cast<u8>((i * 37 + round * 53 + kind * 19 + 11) & 255); };
                    for (u32 i = 0; i < size; ++i) guest[source_offset + i] = pattern(i);
                    char message[160];
                    std::snprintf(message, sizeof(message), "P11 BEFORE enqueue: round=%u ordering=%s",
                        round + 1, kind == 0 ? "same-tag fence" : kind == 1 ? "global barrier" : "per-tag barrier");
                    ARMSX3StartupLog(message);
                    const u8 tag = round % 2 ? 31 : 0;
                    enqueue(kind == 2 ? MFC_GETB_CMD : MFC_GET_CMD, tag, address + source_offset, first_ls, size);
                    if (kind == 1) enqueue(MFC_BARRIER_CMD, 7, 0, 0, 0);
                    enqueue(kind == 0 ? MFC_PUTF_CMD : MFC_PUT_CMD,
                        kind == 1 ? 31 : tag, address + destination_offset, first_ls, size);
                    if (kind == 1) enqueue(MFC_BARRIER_CMD, 7, 0, 0, 0);
                    enqueue(kind == 1 ? MFC_GET_CMD : MFC_GETF_CMD, tag,
                        address + destination_offset, result_ls, size);
                    // No command has run yet: the queued PUT must not change memory.
                    for (u32 i = 0; i < size; ++i)
                        if (guest[destination_offset + i] != 0xa5 || spu->ls[first_ls + i] != 0x5a)
                            throw std::runtime_error("P11 DMA executed before queue drain");
                    drain(kind == 1 ? ((1u << tag) | (1u << 7) | (1u << 31)) : (1u << tag));
                    for (u32 i = 0; i < guest_size; ++i)
                    {
                        u8 expected = 0xa5;
                        if (i >= source_offset && i < source_offset + size) expected = pattern(i - source_offset);
                        if (i >= destination_offset && i < destination_offset + size) expected = pattern(i - destination_offset);
                        if (guest[i] != expected || alias[i] != expected)
                            throw std::runtime_error("P11 ordered guest data, guards or alias mismatch");
                    }
                    for (const s64 mirror : {-2ll, -1ll, 0ll, 1ll, 2ll})
                    {
                        const auto* view = spu->ls + mirror * SPU_LS_SIZE;
                        for (u32 i = 0; i < SPU_LS_SIZE; ++i)
                        {
                            u8 expected = 0x5a;
                            if (i >= first_ls && i < first_ls + size) expected = pattern(i - first_ls);
                            if (i >= result_ls && i < result_ls + size) expected = pattern(i - result_ls);
                            if (view[i] != expected)
                                throw std::runtime_error("P11 ordered LS data, guards or mirror mismatch");
                        }
                    }
                    ARMSX3StartupLog("P11 PASS: queued dependency order, delayed tags, data, guards and aliases");
                }
            }
            spu->cpu_init();
            std::memset(guest, 0xa5, guest_size);
            std::memset(spu->ls, 0x5a, SPU_LS_SIZE);
            for (u32 i = 0; i < size; ++i) guest[source_offset + i] = static_cast<u8>(i * 13 + 7);
            ARMSX3StartupLog("P11 BEFORE filling all 16 MFC queue slots");
            for (u8 tag = 0; tag < 16; ++tag)
                enqueue(MFC_GET_CMD, tag, address + source_offset, 0x4000 + tag * size, size);
            if (spu->get_ch_count(MFC_Cmd) != 0)
                throw std::runtime_error("P11 full queue did not report zero writable slots");
            drain(0xffff);
            for (u32 i = 0; i < guest_size; ++i)
            {
                const u8 expected = i >= source_offset && i < source_offset + size ? static_cast<u8>((i - source_offset) * 13 + 7) : 0xa5;
                if (guest[i] != expected || alias[i] != expected)
                    throw std::runtime_error("P11 full-queue GET altered guest source");
            }
            for (const s64 mirror : {-2ll, -1ll, 0ll, 1ll, 2ll})
            {
                const auto* view = spu->ls + mirror * SPU_LS_SIZE;
                for (u32 i = 0; i < SPU_LS_SIZE; ++i)
                {
                    const u8 expected = i >= 0x4000 && i < 0x4000 + 16 * size ? static_cast<u8>(((i - 0x4000) % size) * 13 + 7) : 0x5a;
                    if (view[i] != expected) throw std::runtime_error("P11 full-queue LS data or guard mismatch");
                }
            }
            ARMSX3StartupLog("P11 PASS: full 16-slot queue, capacity recovery and all completion tags");
        }
        ARMSX3StartupLog("P11 AFTER private SPU cleanup; BEFORE guest deallocation");
        if (vm::dealloc(address, vm::main) != guest_size || vm::check_addr(address))
            throw std::runtime_error("P11 guest deallocation failed");
        vm::close();
        initialized = false;
        ARMSX3StartupLog("P11 PASS: 88 queued DMA transfers, fences/barriers, completion and cleanup; scheduling and game boot remain untested");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        if (initialized) vm::close();
        return -1;
    }
}

extern "C" __attribute__((visibility("default"))) int armsx3_core_test_spu_channel_instructions()
{
    ARMSX3StartupLog("P12 BEFORE guest VM setup for SPU channel instructions");
    bool initialized = false;
    try
    {
        vm::init();
        initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x30000))
            throw std::runtime_error("P12 could not reserve DMA guest region");
        constexpr u32 guest_size = 0x20000;
        const u32 address = vm::alloc(guest_size, vm::main, 0x10000);
        if (!address || !vm::check_addr(address, vm::page_readable | vm::page_writable, guest_size))
            throw std::runtime_error("P12 guest DMA allocation failed");
        {
            // Baseline transfers only: no active RSX or competing guest CPUs.
            // Restore every setting before returning, including exception paths.
            struct DMASettings
            {
                u32 shuffle = g_cfg.core.mfc_transfers_shuffling.get();
                u32 preferred = g_cfg.core.preferred_spu_threads.get();
                bool accurate = g_cfg.core.spu_accurate_dma.get();
                bool strict = g_cfg.video.strict_rendering_mode.get();
                rsx_fifo_mode fifo = g_cfg.core.rsx_fifo_accuracy.get();
                DMASettings()
                {
                    g_cfg.core.mfc_transfers_shuffling.set(0);
                    g_cfg.core.preferred_spu_threads.set(0);
                    g_cfg.core.spu_accurate_dma.set(false);
                    g_cfg.video.strict_rendering_mode.set(false);
                    g_cfg.core.rsx_fifo_accuracy.set(rsx_fifo_mode::fast);
                }
                ~DMASettings()
                {
                    g_cfg.core.rsx_fifo_accuracy.set(fifo);
                    g_cfg.video.strict_rendering_mode.set(strict);
                    g_cfg.core.spu_accurate_dma.set(accurate);
                    g_cfg.core.preferred_spu_threads.set(preferred);
                    g_cfg.core.mfc_transfers_shuffling.set(shuffle);
                }
            } dma_settings;
            struct ContextDeleter
            {
                void operator()(spu_thread* context) const
                {
                    // cleanup() assumes a production named_thread and an LV2
                    // local-store allocation; neither exists in this private probe.
                    vm::free_range_lock(context->range_lock);
                    delete context; // unmaps all LS mirrors and releases reservation
                    cpu_thread::g_threads_deleted++;
                }
            };
            std::unique_ptr<spu_thread, ContextDeleter> spu;
            {
                struct ConstructionSettings
                {
                    u32 previous_id = id_manager::g_id;
                    spu_decoder_type previous_decoder = g_cfg.core.spu_decoder.get();
                    ConstructionSettings()
                    {
                        id_manager::g_id = spu_thread::id_base;
                        g_cfg.core.spu_decoder.set(spu_decoder_type::_static);
                    }
                    ~ConstructionSettings()
                    {
                        g_cfg.core.spu_decoder.set(previous_decoder);
                        id_manager::g_id = previous_id;
                    }
                } settings;
                ARMSX3StartupLog("P12 BEFORE private SPU context construction; interpreter selected");
                spu.reset(new spu_thread(nullptr, 0, "iOS SPU channel instruction probe", 0));
            }
            ARMSX3StartupLog("P12 AFTER SPU context; BEFORE local-store mirror mappings");
            spu_thread::map_ls(*spu->shm, spu->ls);
            ARMSX3StartupLog("P12 AFTER 256 KiB SPU local store and five shared views mapped");
            ARMSX3StartupLog("P12 BEFORE cpu_init to reset SPU channels and DMA fence masks");
            spu->cpu_init();
            ARMSX3StartupLog("P12 AFTER cpu_init; channel transfer sequence pending");
            // These handlers check CPU state after channel access. Clear only
            // this unregistered private context while running bounded probes;
            // restore constructor state before its normal private destruction.
            struct ExecutionState
            {
                spu_thread& context;
                decltype(std::declval<spu_thread&>().state.load()) previous;
                explicit ExecutionState(spu_thread& value) : context(value), previous(value.state.load())
                { context.state.store(bs_t<cpu_flag>{}); }
                ~ExecutionState() { context.state.store(previous); }
            } execution_state(*spu);
            auto interpreter = std::make_unique<spu_interpreter_rt>();
            u32 executed = 0;
            const auto instruction = [&](u32 primary, u32 channel, u32 reg)
            {
                if (++executed > 4096 || spu->state)
                    throw std::runtime_error("P12 instruction budget or private CPU state mismatch");
                spu_opcode_t op{primary << 21};
                op.ra = channel; op.rt = reg;
                // Fetch the encoded instruction through the real big-endian LS.
                // Restore the scratch word so existing full-LS guard checks apply.
                struct InstructionSlot
                {
                    be_t<u32>* word;
                    be_t<u32> previous;
                    ~InstructionSlot() { *word = previous; }
                } slot{spu->_ptr<u32>(0x30000), spu->_ref<u32>(0x30000)};
                *slot.word = op.opcode;
                spu->pc = 0x30000;
                const u32 fetched = spu->_ref<u32>(spu->pc);
                const auto handler = interpreter->decode(fetched);
                if (!handler || !handler(*spu, {fetched}))
                    throw std::runtime_error("P12 SPU channel instruction did not complete");
                spu->pc += 4;
            };
            const auto count = [&](u32 channel) -> u32
            {
                spu->gpr[3] = v128::from32p(0xdeadbeef);
                instruction(0x0f, channel, 3); // RCHCNT
                for (unsigned lane = 0; lane < 3; ++lane)
                    if (spu->gpr[3]._u32[lane])
                        throw std::runtime_error("P12 RCHCNT did not clear nonpreferred lanes");
                return spu->gpr[3]._u32[3];
            };
            const auto write_channel = [&](u32 channel, u32 value)
            {
                // Host-provided operands; the actual WRCH handler performs all
                // channel writes, including the MFC command and tag requests.
                spu->gpr[2] = v128::from32r(value);
                instruction(0x10d, channel, 2); // WRCH
                if (spu->gpr[2]._u32[3] != value)
                    throw std::runtime_error("P12 WRCH changed its source register");
            };
            const auto read_ready = [&](u32 channel) -> u32
            {
                if (count(channel) != 1)
                    throw std::runtime_error("P12 RDCH guarded against an empty channel");
                spu->gpr[4] = v128::from32p(0xdeadbeef);
                instruction(0x0d, channel, 4); // RDCH
                for (unsigned lane = 0; lane < 3; ++lane)
                    if (spu->gpr[4]._u32[lane])
                        throw std::runtime_error("P12 RDCH did not clear nonpreferred lanes");
                return spu->gpr[4]._u32[3];
            };
            const auto completion = [&](u32 mask, u32 mode)
            {
                if (count(MFC_RdTagStat) != 0)
                    throw std::runtime_error("P12 stale completion status before request");
                write_channel(MFC_WrTagMask, mask);
                if (read_ready(MFC_RdTagMask) != mask)
                    throw std::runtime_error("P12 tag mask readback mismatch");
                write_channel(MFC_WrTagUpdate, mode);
                if (read_ready(MFC_RdTagStat) != mask)
                    throw std::runtime_error("P12 completion mask mismatch");
                if (count(MFC_RdTagStat) != 0)
                    throw std::runtime_error("P12 tag status read did not consume result");
            };
            const auto submit = [&](const spu_mfc_cmd& command)
            {
                if (count(MFC_Cmd) != 16 || spu->mfc_size != 0)
                    throw std::runtime_error("P12 MFC capacity mismatch before submission");
                write_channel(MFC_LSA, command.lsa);
                write_channel(MFC_EAH, command.eah);
                write_channel(MFC_EAL, command.eal);
                write_channel(MFC_Size, command.size);
                write_channel(MFC_TagID, command.tag);
                // Writing the command invokes the production process_mfc_cmd.
                write_channel(MFC_Cmd, command.cmd);
                if (spu->mfc_size || spu->mfc_fence || spu->mfc_barrier ||
                    count(MFC_Cmd) != 16)
                    throw std::runtime_error("P12 synchronous command did not complete");
                const u32 mask = 1u << command.tag;
                for (const u32 mode : {u32(MFC_TAG_UPDATE_IMMEDIATE), u32(MFC_TAG_UPDATE_ANY), u32(MFC_TAG_UPDATE_ALL)})
                    completion(mask, mode);
            };
            completion(0, MFC_TAG_UPDATE_IMMEDIATE);
            auto* guest = vm::_ptr<u8>(address);
            auto* alias = reinterpret_cast<const u8*>(vm::g_sudo_addr + address);
            struct Transfer { u16 size; u32 offset; u32 lsa; };
            const std::array<Transfer, 8> transfers{{
                {1, 3, 3}, {2, 6, 6}, {4, 12, 12}, {8, 24, 24},
                {16, 0xff0, 0x1000}, {128, 0x3fc0, 0x2000},
                {256, 0xff80, SPU_LS_SIZE - 256},
                {16384, 0x3ff0, 0x8000},
            }};
            // Repeated passes also check that PUT range locks are released.
            u32 transfer_index = 0;
            for (u32 round = 0; round < 2; ++round)
            {
                for (const auto& transfer : transfers)
                {
                    if (transfer.offset + transfer.size > guest_size ||
                        transfer.lsa + transfer.size > SPU_LS_SIZE)
                        throw std::runtime_error("P12 DMA test span out of bounds");
                    std::memset(guest, 0xa5, guest_size);
                    std::memset(spu->ls, 0x5a, SPU_LS_SIZE);
                    const auto pattern = [round](u32 index) -> u8
                    {
                        return static_cast<u8>((index * 37 + 11 + round * 53) & 255);
                    };
                    for (u32 i = 0; i < transfer.size; ++i)
                        guest[transfer.offset + i] = pattern(i);
                    spu_mfc_cmd command{};
                    command.cmd = MFC_GET_CMD;
                    constexpr std::array<u8, 3> tags{0, 7, 31};
                    command.tag = tags[transfer_index++ % tags.size()];
                    command.size = transfer.size;
                    command.lsa = transfer.lsa;
                    command.eal = address + transfer.offset;
                    char message[180];
                    std::snprintf(message, sizeof(message),
                        "P12 BEFORE instruction DMA GET: round=%u size=%u EA=0x%08x LS=0x%05x",
                        round + 1, unsigned(transfer.size), command.eal, command.lsa);
                    ARMSX3StartupLog(message);
                    submit(command);
                    for (u32 i = 0; i < SPU_LS_SIZE; ++i)
                    {
                        const bool inside = i >= transfer.lsa && i < transfer.lsa + transfer.size;
                        const u8 expected = inside ? pattern(i - transfer.lsa) : 0x5a;
                        if (spu->ls[i] != expected)
                            throw std::runtime_error("P12 GET data or local-store guard mismatch");
                    }
                    for (u32 i = 0; i < guest_size; ++i)
                    {
                        const bool inside = i >= transfer.offset && i < transfer.offset + transfer.size;
                        const u8 expected = inside ? pattern(i - transfer.offset) : 0xa5;
                        if (guest[i] != expected || alias[i] != expected)
                            throw std::runtime_error("P12 GET changed guest source or alias");
                    }
                    for (u32 i = 0; i < transfer.size; ++i)
                        spu->ls[transfer.lsa + i] = pattern(i) ^ 0xff;
                    command.cmd = MFC_PUT_CMD;
                    ARMSX3StartupLog("P12 BEFORE instruction DMA PUT of transformed local-store data");
                    submit(command);
                    for (u32 i = 0; i < guest_size; ++i)
                    {
                        const bool inside = i >= transfer.offset && i < transfer.offset + transfer.size;
                        const u8 expected = inside ? (pattern(i - transfer.offset) ^ 0xff) : 0xa5;
                        if (guest[i] != expected || alias[i] != expected)
                            throw std::runtime_error("P12 PUT data, guest guard or alias mismatch");
                    }
                    for (const s64 mirror : {-2ll, -1ll, 0ll, 1ll, 2ll})
                    {
                        const auto* view = spu->ls + mirror * SPU_LS_SIZE;
                        for (u32 i = 0; i < SPU_LS_SIZE; ++i)
                        {
                            const bool inside = i >= transfer.lsa && i < transfer.lsa + transfer.size;
                            const u8 expected = inside ? (pattern(i - transfer.lsa) ^ 0xff) : 0x5a;
                            if (view[i] != expected)
                                throw std::runtime_error("P12 PUT changed local store or shared mirror");
                        }
                    }
                    if (spu->range_lock->load() != 0)
                        throw std::runtime_error("P12 PUT left a guest range lock held");
                    std::snprintf(message, sizeof(message),
                        "P12 PASS: round=%u size=%u WRCH/RDCH/RCHCNT GET/PUT, all completion modes, guards, aliases and lock release",
                        round + 1, unsigned(transfer.size));
                    ARMSX3StartupLog(message);
                }
            }
            completion((1u << 0) | (1u << 7) | (1u << 31), MFC_TAG_UPDATE_ALL);
            char summary[160];
            std::snprintf(summary, sizeof(summary), "P12 PASS: executed %u real SPU channel instructions for 32 DMA transfers", executed);
            ARMSX3StartupLog(summary);
        }
        ARMSX3StartupLog("P12 AFTER private SPU cleanup; BEFORE guest deallocation");
        if (vm::dealloc(address, vm::main) != guest_size)
            throw std::runtime_error("P12 guest deallocation size mismatch");
        if (vm::check_addr(address))
            throw std::runtime_error("P12 guest region still accessible after deallocation");
        vm::close();
        initialized = false;
        ARMSX3StartupLog("P12 PASS: SPU WRCH/RDCH/RCHCNT, 32 DMA transfers, completion and cleanup; scheduling and game boot remain untested");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        if (initialized) vm::close();
        return -1;
    }
}


extern "C" __attribute__((visibility("default"))) int armsx3_core_test_thread_waits()
{
    ARMSX3StartupLog("P13 BEFORE bounded host wait/wake and core named-thread tests");
    try
    {
        alignas(8) unsigned word = 0;
        const timespec short_timeout{0, 1000000};
        errno = 0;
        if (futex(&word, FUTEX_WAIT_PRIVATE, 1, &short_timeout) != -1 || errno != EAGAIN)
            throw std::runtime_error("P13 wait mismatch must return EAGAIN");
        for (unsigned round = 0; round < 32; ++round)
        {
            errno = 0;
            if (futex(&word, FUTEX_WAIT_PRIVATE, 0, &short_timeout) != -1 || errno != ETIMEDOUT)
                throw std::runtime_error("P13 timed wait must return ETIMEDOUT");
            if (futex(&word, FUTEX_WAKE_PRIVATE, 1) != 0)
                throw std::runtime_error("P13 timed-out waiter was not removed");
        }
        ARMSX3StartupLog("P13 PASS: mismatch, 32 timeouts and address reuse");
        for (unsigned mode = 0; mode < 2; ++mode)
        {
            std::atomic<unsigned> entered{0}, finished{0}, failures{0};
            std::vector<std::thread> workers;
            // Join all started workers even if thread creation throws.
            struct JoinAll { std::vector<std::thread>& workers; ~JoinAll()
                { for (auto& worker : workers) if (worker.joinable()) worker.join(); } } join{workers};
            for (unsigned i = 0; i < 4; ++i)
                workers.emplace_back([&] {
                    entered.fetch_add(1);
                    const timespec timeout{0, 500000000};
                    if (futex(&word, FUTEX_WAIT_PRIVATE, 0, &timeout) != 0) failures.fetch_add(1);
                    finished.fetch_add(1);
                });
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
            while (entered.load() != 4 && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
            unsigned woken = 0;
            while (woken < 4 && std::chrono::steady_clock::now() < deadline)
            {
                const int count = futex(&word, FUTEX_WAKE_PRIVATE, mode ? INT32_MAX : 1);
                if (count < 0 || (!mode && count > 1))
                    throw std::runtime_error("P13 wake count invalid");
                woken += unsigned(count);
                std::this_thread::yield();
            }
            for (auto& worker : workers) worker.join();
            if (woken != 4 || finished.load() != 4 || failures.load())
                throw std::runtime_error("P13 waiter wake/join mismatch");
            ARMSX3StartupLog(mode ? "P13 PASS: wake-all four host waiters" : "P13 PASS: wake-one four host waiters");
        }
        for (unsigned round = 0; round < 4; ++round)
        {
            std::atomic<bool> entered{false};
            ARMSX3StartupLog("P13 BEFORE core named_thread construction");
            named_thread worker("iOS wait lifecycle probe", [&]() -> int {
                const bool registered = thread_ctrl::get_current() != nullptr;
                entered.store(true);
                thread_ctrl::wait_for(200000);
                return registered ? 42 : -1;
            });
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
            while (!entered.load() && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            thread_ctrl::notify(worker);
            if (worker() != 42)
                throw std::runtime_error("P13 core named-thread TLS/result mismatch");
            ARMSX3StartupLog("P13 PASS: core named_thread wait, notify, result and join");
        }
        ARMSX3StartupLog("P13 PASS: host wait/wake and core thread lifecycle; guest CPU scheduling and game boot remain untested");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        return -1;
    }
}


extern "C" u64 armsx3_ios_live_cpu_threads();
extern "C" u64 armsx3_ios_stopped_cpu_waits();
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_ppu_lifecycle()
{
    ARMSX3StartupLog("P14 BEFORE stopped PPU CPU-thread lifecycle test");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P14 requires stopped emulator");
        struct Configuration
        {
            bool ppu = g_cfg.core.ppu_prof.get(), spu = g_cfg.core.spu_prof.get(), debug = g_cfg.core.spu_debug.get();
            thread_scheduler_mode scheduler = g_cfg.core.thread_scheduler.get();
            Configuration() { g_cfg.core.ppu_prof.set(false); g_cfg.core.spu_prof.set(false);
                g_cfg.core.spu_debug.set(false); g_cfg.core.thread_scheduler.set(thread_scheduler_mode::os); }
            ~Configuration() { g_cfg.core.ppu_prof.set(ppu); g_cfg.core.spu_prof.set(spu);
                g_cfg.core.spu_debug.set(debug); g_cfg.core.thread_scheduler.set(scheduler); }
        } configuration;
        vm::init();
        initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x20000))
            throw std::runtime_error("P14 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P14 guest stack allocation failed");
        for (unsigned round = 0; round < 4; ++round)
        {
            const u64 live = armsx3_ios_live_cpu_threads();
            const u64 waits = armsx3_ios_stopped_cpu_waits();
            const auto created = cpu_thread::g_threads_created.load();
            const auto deleted = cpu_thread::g_threads_deleted.load();
            const ppu_thread_params params{static_cast<vm::addr_t>(address + 0x1000), 0x8000, 0, {}, 0, 0};
            ARMSX3StartupLog("P14 BEFORE private standby named_thread<ppu_thread> construction");
            {
                std::unique_ptr<named_thread<ppu_thread>> worker;
                {
                    struct ConstructionID
                    {
                        u32 previous = id_manager::g_id;
                        ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                        ~ConstructionID() { id_manager::g_id = previous; }
                    } construction_id;
                    worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS stopped PPU probe", 1000);
                }
                // Keep stop/wait/suspend/memory intact. Never enter cpu_task or guest instructions.
                worker->state -= cpu_flag::exit;
                if (!(worker->state & cpu_flag::stop))
                    throw std::runtime_error("P14 standby context lost stop flag");
                *worker = thread_state::created;
                ARMSX3StartupLog("P14 AFTER start; waiting for real CPU stopped-wait entry");
                const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
                while (armsx3_ios_stopped_cpu_waits() == waits && std::chrono::steady_clock::now() < deadline)
                    std::this_thread::yield();
                if (armsx3_ios_stopped_cpu_waits() == waits || armsx3_ios_live_cpu_threads() != live + 1)
                    throw std::runtime_error("P14 CPU thread did not enter stopped wait");
                if (!(worker->state & cpu_flag::stop) || worker->gpr[1] != address + 0x9000 - ppu_stack_start_offset)
                    throw std::runtime_error("P14 stopped context or stack changed");
                ARMSX3StartupLog("P14 BEFORE request exit and notify stopped CPU state");
                worker->state += cpu_flag::exit;
                worker->state.notify_one();
                (*worker)();
                ARMSX3StartupLog("P14 AFTER CPU thread join");
            }
            if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 1 ||
                cpu_thread::g_threads_deleted.load() != deleted + 1)
                throw std::runtime_error("P14 CPU lifecycle counters did not balance");
            ARMSX3StartupLog("P14 PASS: real PPU thread start, stopped wait, exit, join and balanced cleanup");
        }
        if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
            throw std::runtime_error("P14 guest stack deallocation failed");
        vm::close();
        initialized = false;
        ARMSX3StartupLog("P14 PASS: four stopped PPU CPU-thread lifecycles; runnable scheduling and game boot remain untested");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        if (initialized) vm::close();
        return -1;
    }
}


// A bounded instruction chain is dispatched by the real PPU cpu_task command queue.
// This does not invoke fast_call, firmware syscalls or an autonomous guest program.
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_ppu_worker_instructions()
{
    ARMSX3StartupLog("P15 BEFORE PPU worker command queue and guest instruction test");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P15 requires stopped emulator");
        struct Configuration
        {
            bool ppu = g_cfg.core.ppu_prof.get(), spu = g_cfg.core.spu_prof.get(), debug = g_cfg.core.spu_debug.get();
            thread_scheduler_mode scheduler = g_cfg.core.thread_scheduler.get();
            Configuration() { g_cfg.core.ppu_prof.set(false); g_cfg.core.spu_prof.set(false);
                g_cfg.core.spu_debug.set(false); g_cfg.core.thread_scheduler.set(thread_scheduler_mode::os); }
            ~Configuration() { g_cfg.core.ppu_prof.set(ppu); g_cfg.core.spu_prof.set(spu);
                g_cfg.core.spu_debug.set(debug); g_cfg.core.thread_scheduler.set(scheduler); }
        } configuration;
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x20000))
            throw std::runtime_error("P15 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P15 guest allocation failed");
        auto interpreter = std::make_unique<ppu_interpreter_rt>();
        struct Program
        {
            std::array<ppu_intrp_func, 7> functions{};
            be_t<u32>* code = nullptr;
            std::atomic<bool> completed{false};
            bool tls = false;
        };
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        for (u32 round = 0; round < 4; ++round)
        {
            const u64 live = armsx3_ios_live_cpu_threads();
            const auto created = cpu_thread::g_threads_created.load();
            const auto deleted = cpu_thread::g_threads_deleted.load();
            Program program;
            program.code = reinterpret_cast<be_t<u32>*>(vm::base(address));
            const u32 seed = 42 + round * 11;
            const std::array<u32, 6> opcodes{
                dform(14, 3, 0, seed), dform(14, 4, 0, 0xfff9),
                (31u << 26) | (5u << 21) | (3u << 16) | (4u << 11) | (266u << 1),
                dform(36, 5, 6, 0), dform(32, 7, 6, 0), dform(24, 7, 8, 0x100)
            };
            for (u32 i = 0; i < opcodes.size(); ++i)
            {
                program.code[i] = opcodes[i];
                program.functions[i].fn = interpreter->decode(opcodes[i]);
                if (!program.functions[i].fn) throw std::runtime_error("P15 decoder returned null");
            }
            program.code[6] = 0;
            program.functions.back().fn = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                context.gpr[31] = 0x503135494f53ull;
            };
            auto* output = static_cast<u8*>(vm::base(address + 0x100));
            std::memset(output - 16, 0xa5, 36);
            const ppu_thread_params params{static_cast<vm::addr_t>(address + 0x1000), 0x8000, 0, {}, 0, 0};
            {
                std::unique_ptr<named_thread<ppu_thread>> worker;
                {
                    struct ConstructionID { u32 previous = id_manager::g_id;
                        ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                        ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                    worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS PPU worker instructions", 1000);
                }
                const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                    auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                    program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                    program.functions[0].fn(context, {u32(program.code[0])}, program.code, program.functions.data() + 1);
                    context.state += cpu_flag::exit;
                    program.completed.store(true, std::memory_order_release);
                };
                // Production queue processing supplies both registers before dispatching the callback.
                worker->cmd_list({{ppu_cmd::set_gpr, 6}, u64(address + 0x100),
                    {ppu_cmd::set_gpr, 30}, u64(reinterpret_cast<uintptr_t>(&program)),
                    {ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
                worker->cia = address;
                worker->gpr[31] = 0;
                // Private context only: bypass LV2 admission, then enter normal CPU cpu_task.
                worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
                ARMSX3StartupLog("P15 BEFORE starting runnable PPU worker with bounded queued callback");
                *worker = thread_state::created;
                const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
                while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                    std::this_thread::yield();
                if (!program.completed.load(std::memory_order_acquire))
                    throw std::runtime_error("P15 PPU worker instruction deadline exceeded");
                (*worker)();
                ARMSX3StartupLog("P15 AFTER bounded queued instruction chain and PPU worker join");
                if (!program.tls || worker->gpr[3] != seed || worker->gpr[4] != 0xfffffffffffffff9ull ||
                    worker->gpr[5] != seed - 7 || worker->gpr[7] != seed - 7 ||
                    worker->gpr[8] != ((seed - 7) | 0x100) || worker->gpr[31] != 0x503135494f53ull)
                    throw std::runtime_error("P15 PPU worker TLS, queue or instruction result mismatch");
            }
            const u32 value = seed - 7;
            for (u32 i = 0; i < 4; ++i)
                if (output[i] != u8(value >> (24 - i * 8)) ||
                    static_cast<const u8*>(vm::get_super_ptr(address + 0x100))[i] != output[i])
                    throw std::runtime_error("P15 guest big-endian store or alias mismatch");
            for (int i = -16; i < 20; ++i)
                if ((i < 0 || i >= 4) && output[i] != 0xa5)
                    throw std::runtime_error("P15 guest output guard modified");
            if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 1 ||
                cpu_thread::g_threads_deleted.load() != deleted + 1)
                throw std::runtime_error("P15 CPU lifecycle counters did not balance");
            ARMSX3StartupLog("P15 PASS: queued registers, six PowerPC instructions on real PPU worker, TLS, guards, aliases and cleanup");
        }
        if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
            throw std::runtime_error("P15 guest deallocation failed");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P15 PASS: 24 PowerPC instructions across four real PPU workers; full LV2 scheduling and game boot remain untested");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        if (initialized) vm::close();
        return -1;
    }
}


extern "C" u64 armsx3_ios_ppu_command_waits();
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_ppu_queue_wake()
{
    ARMSX3StartupLog("P16 BEFORE persistent PPU command queue wait/wake test");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P16 requires stopped emulator");
        struct Configuration
        {
            bool ppu = g_cfg.core.ppu_prof.get(), spu = g_cfg.core.spu_prof.get(), debug = g_cfg.core.spu_debug.get();
            thread_scheduler_mode scheduler = g_cfg.core.thread_scheduler.get();
            Configuration() { g_cfg.core.ppu_prof.set(false); g_cfg.core.spu_prof.set(false);
                g_cfg.core.spu_debug.set(false); g_cfg.core.thread_scheduler.set(thread_scheduler_mode::os); }
            ~Configuration() { g_cfg.core.ppu_prof.set(ppu); g_cfg.core.spu_prof.set(spu);
                g_cfg.core.spu_debug.set(debug); g_cfg.core.thread_scheduler.set(scheduler); }
        } configuration;
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x20000))
            throw std::runtime_error("P16 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P16 guest allocation failed");
        auto interpreter = std::make_unique<ppu_interpreter_rt>();
        struct Program
        {
            std::array<ppu_intrp_func, 7> functions{};
            be_t<u32>* code = nullptr;
            std::array<u64, 7> result{};
            std::atomic<u32> completed{0};
            bool tls = false;
        } program;
        program.code = reinterpret_cast<be_t<u32>*>(vm::base(address));
        program.functions.back().fn = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
            context.gpr[31] = 0x503136494f53ull;
        };
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        const u64 live = armsx3_ios_live_cpu_threads();
        const auto created = cpu_thread::g_threads_created.load();
        const auto deleted = cpu_thread::g_threads_deleted.load();
        {
            std::unique_ptr<named_thread<ppu_thread>> worker;
            {
                struct ConstructionID { u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                const ppu_thread_params params{static_cast<vm::addr_t>(address + 0x1000), 0x8000, 0, {}, 0, 0};
                worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS persistent PPU queue", 1000);
            }
            // Wake the actual command wait as well as CPU state on every unwind.
            // Guard is destroyed before worker/program/decoder/VM storage.
            struct StopWorker
            {
                named_thread<ppu_thread>& worker;
                ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                    worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); }
            } stop{*worker};
            const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                context.gpr[31] = 0;
                program.functions[0].fn(context, {u32(program.code[0])}, program.code, program.functions.data() + 1);
                program.result = {context.gpr[3], context.gpr[4], context.gpr[5], context.gpr[6],
                    context.gpr[7], context.gpr[8], context.gpr[31]};
                program.completed.fetch_add(1, std::memory_order_release);
            };
            const ppu_intrp_func_t exit = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                context.state += cpu_flag::exit;
            };
            worker->cia = address;
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            u64 waits = armsx3_ios_ppu_command_waits();
            *worker = thread_state::created;
            const auto waitForQueue = [&] {
                const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
                while (armsx3_ios_ppu_command_waits() == waits && std::chrono::steady_clock::now() < deadline)
                    std::this_thread::yield();
                if (armsx3_ios_ppu_command_waits() == waits || armsx3_ios_live_cpu_threads() != live + 1)
                    throw std::runtime_error("P16 worker did not return to live empty-queue wait");
                waits = armsx3_ios_ppu_command_waits();
            };
            waitForQueue();
            for (u32 round = 0; round < 32; ++round)
            {
                const u32 seed = 42 + round * 11;
                const std::array<u32, 6> opcodes{
                    dform(14, 3, 0, seed), dform(14, 4, 0, 0xfff9),
                    (31u << 26) | (5u << 21) | (3u << 16) | (4u << 11) | (266u << 1),
                    dform(36, 5, 6, 0), dform(32, 7, 6, 0), dform(24, 7, 8, 0x100)
                };
                for (u32 i = 0; i < opcodes.size(); ++i)
                {
                    program.code[i] = opcodes[i];
                    program.functions[i].fn = interpreter->decode(opcodes[i]);
                    if (!program.functions[i].fn) throw std::runtime_error("P16 decoder returned null");
                }
                program.code[6] = 0;
                auto* output = static_cast<u8*>(vm::base(address + 0x100));
                std::memset(output - 16, 0xa5, 36);
                // Alternate immediate publication with a brief opportunity to park.
                if (round % 4 == 0) std::this_thread::sleep_for(std::chrono::milliseconds(1));
                worker->cmd_list({{ppu_cmd::set_gpr, 6}, u64(address + 0x100),
                    {ppu_cmd::set_gpr, 30}, u64(reinterpret_cast<uintptr_t>(&program)),
                    {ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
                worker->cmd_notify.store(1);
                worker->cmd_notify.notify_one();
                const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
                while (program.completed.load(std::memory_order_acquire) < round + 1 && std::chrono::steady_clock::now() < deadline)
                    std::this_thread::yield();
                if (program.completed.load(std::memory_order_acquire) != round + 1)
                    throw std::runtime_error("P16 queued batch deadline or completion count mismatch");
                waitForQueue(); // The worker no longer accesses program or guest output.
                const u32 value = seed - 7;
                const std::array<u64, 7> expected{seed, 0xfffffffffffffff9ull, value,
                    address + 0x100, value, value | 0x100u, 0x503136494f53ull};
                if (!program.tls || program.result != expected)
                    throw std::runtime_error("P16 queued batch TLS or register mismatch");
                for (int i = -16; i < 20; ++i)
                {
                    const u8 expectedByte = i >= 0 && i < 4 ? u8(value >> (24 - i * 8)) : 0xa5;
                    if (output[i] != expectedByte ||
                        static_cast<const u8*>(vm::get_super_ptr(address + 0x100))[i] != expectedByte)
                        throw std::runtime_error("P16 guest store, guard or alias mismatch");
                }
                char message[160];
                std::snprintf(message, sizeof(message), "P16 PASS: batch=%u value=%u six instructions, queue notify, TLS, guards and live wait", round + 1, value);
                ARMSX3StartupLog(message);
            }
            ARMSX3StartupLog("P16 BEFORE queued exit and persistent PPU join");
            worker->cmd_list({{ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(exit)});
            worker->cmd_notify.store(1); worker->cmd_notify.notify_one();
            (*worker)();
            ARMSX3StartupLog("P16 AFTER persistent PPU worker join");
        }
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 1 ||
            cpu_thread::g_threads_deleted.load() != deleted + 1)
            throw std::runtime_error("P16 persistent worker counters did not balance");
        if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
            throw std::runtime_error("P16 guest deallocation failed");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P16 PASS: one persistent PPU worker, 32 notified batches, 192 instructions and cleanup; full LV2 scheduling and game boot remain untested");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        if (initialized) vm::close();
        return -1;
    }
}


extern "C" int armsx3_ios_ppu_exec_bounded(ppu_thread*, u32, u32, u32);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_ppu_dispatch()
{
    ARMSX3StartupLog("P17 BEFORE bounded normal PPU interpreter dispatch");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P17 requires stopped emulator");
        struct Configuration
        {
            bool ppu = g_cfg.core.ppu_prof.get(), spu = g_cfg.core.spu_prof.get(), debug = g_cfg.core.spu_debug.get();
            thread_scheduler_mode scheduler = g_cfg.core.thread_scheduler.get();
            ppu_decoder_type decoder = g_cfg.core.ppu_decoder.get();
            Configuration() { g_cfg.core.ppu_prof.set(false); g_cfg.core.spu_prof.set(false);
                g_cfg.core.spu_debug.set(false); g_cfg.core.thread_scheduler.set(thread_scheduler_mode::os);
                g_cfg.core.ppu_decoder.set(ppu_decoder_type::_static); }
            ~Configuration() { g_cfg.core.ppu_prof.set(ppu); g_cfg.core.spu_prof.set(spu);
                g_cfg.core.spu_debug.set(debug); g_cfg.core.thread_scheduler.set(scheduler);
                g_cfg.core.ppu_decoder.set(decoder); }
        } configuration;
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x20000))
            throw std::runtime_error("P17 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P17 guest allocation failed");
        auto interpreter = std::make_unique<ppu_interpreter_rt>();
        // This core cache stores handler pointers, not executable native machine code.
        // Commit only the diagnostic allocation's corresponding cache region.
        utils::memory_commit(vm::g_exec_addr + u64(address) * 2, 0x20000, utils::protection::rw);
        auto* cache = reinterpret_cast<ppu_intrp_func*>(vm::g_exec_addr + u64(address) * 2);
        struct Program { u32 begin, end, budget; int result = -99; bool tls = false;
            std::atomic<bool> completed{false}; };
        using namespace ppu_instructions;
        using namespace ppu_instructions::implicts;
        for (u32 test = 0; test < 5; ++test)
        {
            const u32 count = test == 0 ? 1 : test == 1 ? 10 : 64;
            const std::array<u32, 18> instructions{
                LI(3, 0), MTCTR(4), ADDI(3, 3, 1), BC(16, 0, -4),
                CMPWI(3, count), BNE(40), B(24, false, true),
                STW(3, 6, 0), LWZ(7, 6, 0), CMPWI(7, count + 5), BEQ(32), B(16),
                ADDI(3, 3, 5), BLR(), LI(12, 0xdead), LI(12, 0xbad), B(8), NOP()
            };
            auto* code = reinterpret_cast<be_t<u32>*>(vm::base(address));
            for (u32 i = 0; i < instructions.size(); ++i)
            {
                code[i] = instructions[i];
                cache[i].fn = interpreter->decode(instructions[i]);
                if (!cache[i].fn) throw std::runtime_error("P17 interpreter cache decode failed");
            }
            code[instructions.size()] = 0;
            auto* output = static_cast<u8*>(vm::base(address + 0x100));
            std::memset(output - 16, 0xa5, 36);
            Program program{address, address + u32(instructions.size()) * 4, test == 3 ? 8u : 512u};
            const auto created = cpu_thread::g_threads_created.load();
            const auto deleted = cpu_thread::g_threads_deleted.load();
            const u64 live = armsx3_ios_live_cpu_threads();
            {
                std::unique_ptr<named_thread<ppu_thread>> worker;
                {
                    struct ConstructionID { u32 previous = id_manager::g_id;
                        ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                        ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                    const ppu_thread_params params{static_cast<vm::addr_t>(address + 0x1000), 0x8000, 0, {}, 0, 0};
                    worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS normal PPU dispatch", 1000);
                }
                struct StopWorker { named_thread<ppu_thread>& worker;
                    ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                        worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); } } stop{*worker};
                const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                    auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                    program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                    program.result = armsx3_ios_ppu_exec_bounded(&context, program.begin, program.end, program.budget);
                    context.state += cpu_flag::exit;
                    program.completed.store(true, std::memory_order_release);
                };
                worker->cmd_list({{ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
                worker->gpr[4] = count; worker->gpr[6] = address + 0x100;
                worker->gpr[12] = 0; worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
                worker->ctr = 0; worker->lr = 0;
                worker->cia = test == 4 ? program.end + 4 : address;
                worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
                ARMSX3StartupLog("P17 BEFORE actual exec_task guest fetch/cache dispatch on PPU worker");
                *worker = thread_state::created;
                const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
                while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                    std::this_thread::yield();
                if (!program.completed.load(std::memory_order_acquire))
                    throw std::runtime_error("P17 normal PPU dispatch deadline exceeded");
                (*worker)();
                if (!program.tls) throw std::runtime_error("P17 CPU TLS mismatch");
                if (test < 3)
                {
                    if (program.result != int(count * 2 + 11) || worker->gpr[3] != count + 5 ||
                        worker->gpr[7] != count + 5 || worker->gpr[12] != 0 || worker->ctr != 0 ||
                        worker->lr != address + 7 * 4 || worker->cia != program.end)
                        throw std::runtime_error("P17 normal dispatch branch/return/result mismatch");
                }
                else if (program.result != (test == 3 ? -2 : -1))
                    throw std::runtime_error("P17 budget or range guard did not stop dispatch");
            }
            for (int i = -16; i < 20; ++i)
            {
                const u8 expected = test < 3 && i >= 0 && i < 4 ? u8((count + 5) >> (24 - i * 8)) : 0xa5;
                if (output[i] != expected || static_cast<const u8*>(vm::get_super_ptr(address + 0x100))[i] != expected)
                    throw std::runtime_error("P17 guest store, alias or guard mismatch");
            }
            if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 1 ||
                cpu_thread::g_threads_deleted.load() != deleted + 1)
                throw std::runtime_error("P17 CPU lifecycle counters did not balance");
            char message[180];
            std::snprintf(message, sizeof(message), "P17 PASS: case=%u loop=%u dispatch_result=%d normal core fetch/cache, range/budget guard and cleanup", test + 1, count, program.result);
            ARMSX3StartupLog(message);
        }
        if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
            throw std::runtime_error("P17 guest deallocation failed");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P17 PASS: normal static interpreter exec_task, branches/call/return, budget/range guards and cleanup; full LV2 scheduling and game boot remain untested");
        return 0;
    }
    catch (const std::exception& error)
    {
        ARMSX3StartupLog(error.what());
        if (initialized) vm::close();
        return -1;
    }
}


extern "C" __attribute__((visibility("default"))) int armsx3_core_test_elf_execution()
{
    ARMSX3StartupLog("P18 BEFORE core ELF reader, segment mapping and PPU execution");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P18 requires stopped emulator");
        struct Configuration
        {
            bool ppu = g_cfg.core.ppu_prof.get(), spu = g_cfg.core.spu_prof.get(), debug = g_cfg.core.spu_debug.get();
            thread_scheduler_mode scheduler = g_cfg.core.thread_scheduler.get();
            ppu_decoder_type decoder = g_cfg.core.ppu_decoder.get();
            Configuration() { g_cfg.core.ppu_prof.set(false); g_cfg.core.spu_prof.set(false);
                g_cfg.core.spu_debug.set(false); g_cfg.core.thread_scheduler.set(thread_scheduler_mode::os);
                g_cfg.core.ppu_decoder.set(ppu_decoder_type::_static); }
            ~Configuration() { g_cfg.core.ppu_prof.set(ppu); g_cfg.core.spu_prof.set(spu);
                g_cfg.core.spu_debug.set(debug); g_cfg.core.thread_scheduler.set(scheduler);
                g_cfg.core.ppu_decoder.set(decoder); }
        } configuration;
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x20000))
            throw std::runtime_error("P18 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P18 guest allocation failed");
        const u32 codeAddress = address + 0x100, dataAddress = address + 0x400;
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        const std::array<u32, 7> opcodes{dform(14, 3, 0, 42), dform(14, 4, 0, 0xfff9),
            (31u << 26) | (5u << 21) | (3u << 16) | (4u << 11) | (266u << 1),
            dform(36, 5, 6, 0), dform(32, 7, 6, 0), dform(24, 7, 8, 0x100), 0};
        ppu_exec_object::ehdr_t header{};
        header.e_magic = "\177ELF"_u32; header.e_class = 2; header.e_data = 2;
        header.e_curver = 1; header.e_os_abi = elf_os::lv2; header.e_type = elf_type::exec;
        header.e_machine = elf_machine::ppc64; header.e_version = 1;
        header.e_entry = dataAddress; header.e_phoff = sizeof(header);
        header.e_ehsize = sizeof(header); header.e_phentsize = sizeof(ppu_exec_object::phdr_t); header.e_phnum = 2;
        std::array<ppu_exec_object::phdr_t, 2> segments{};
        segments[0].p_type = 1; segments[0].p_flags = 5; segments[0].p_offset = 0x100;
        segments[0].p_vaddr = codeAddress; segments[0].p_filesz = sizeof(opcodes);
        segments[0].p_memsz = sizeof(opcodes); segments[0].p_align = 16;
        segments[1].p_type = 1; segments[1].p_flags = 6; segments[1].p_offset = 0x200;
        segments[1].p_vaddr = dataAddress; segments[1].p_filesz = 8;
        segments[1].p_memsz = 64; segments[1].p_align = 16;
        std::vector<u8> fixture(0x208, 0);
        std::memcpy(fixture.data(), &header, sizeof(header));
        std::memcpy(fixture.data() + sizeof(header), segments.data(), sizeof(segments));
        for (u32 i = 0; i < opcodes.size(); ++i) {
            const be_t<u32> word = opcodes[i]; std::memcpy(fixture.data() + 0x100 + i * 4, &word, 4);
        }
        const std::array<be_t<u32>, 2> descriptor{codeAddress, dataAddress};
        std::memcpy(fixture.data() + 0x200, descriptor.data(), sizeof(descriptor));
        // Reject malformed header/short payload with the actual core reader.
        for (unsigned test = 0; test < 5; ++test) {
            auto malformed = fixture;
            if (test == 0) malformed[0] = 0;
            if (test == 1) malformed[4] = 1;
            if (test == 2) malformed[5] = 1;
            if (test == 3) malformed[19] = 0x17;
            if (test == 4) malformed.resize(0x204);
            const auto stream = fs::make_stream(std::move(malformed));
            ppu_exec_object rejected(stream);
            const std::array<elf_error, 5> errors{elf_error::header_magic, elf_error::header_class,
                elf_error::header_endianness, elf_error::header_machine, elf_error::stream_data};
            if (rejected.get_error() != errors[test]) throw std::runtime_error("P18 malformed ELF was not rejected correctly");
        }
        ARMSX3StartupLog("P18 PASS: core ELF reader rejects bad magic/class/endian/machine and truncated data");
        const auto validSegment = [&](const ppu_exec_object::prog_t& segment) {
            const u64 base = segment.p_vaddr, length = segment.p_memsz, fileSize = segment.p_filesz;
            return segment.p_type == 1u && base >= address && base < u64(address) + 0x10000 &&
                length <= 0x10000 - (base - address) && fileSize <= length && fileSize == segment.bin.size();
        };
        // ELF parsing does not imply safe mapping; independently bound segment sizes.
        auto oversized = fixture; auto huge = segments[1]; huge.p_memsz = ~u64{0};
        std::memcpy(oversized.data() + sizeof(header) + sizeof(huge), &huge, sizeof(huge));
        const auto oversizedStream = fs::make_stream(std::move(oversized));
        ppu_exec_object badMapping(oversizedStream);
        if (badMapping.get_error() != elf_error::ok || validSegment(badMapping.progs.at(1)))
            throw std::runtime_error("P18 segment mapping bounds guard failed");
        const std::string path = fs::get_cache_dir() + "ARMSX3-P18-diagnostic.elf";
        struct RemoveFixture { std::string path; ~RemoveFixture() { fs::remove_file(path); } } remove{path};
        {
            fs::file file(path, fs::rewrite);
            if (!file || file.write(fixture.data(), fixture.size()) != fixture.size())
                throw std::runtime_error("P18 ELF file write failed");
        }
        const fs::file file(path, fs::read);
        ppu_exec_object elf(file);
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 2 || elf.header.e_entry != dataAddress)
            throw std::runtime_error("P18 on-disk ELF header or segment parse failed");
        for (const auto& segment : elf.progs) if (!validSegment(segment))
            throw std::runtime_error("P18 ELF segment outside diagnostic allocation");
        auto* guest = static_cast<u8*>(vm::base(address)); std::memset(guest, 0xa5, 0x10000);
        for (const auto& segment : elf.progs) {
            auto* target = vm::base(u32(segment.p_vaddr));
            std::memset(target, 0, u64(segment.p_memsz));
            std::memcpy(target, segment.bin.data(), segment.bin.size());
        }
        const auto* opd = static_cast<const be_t<u32>*>(vm::base(u32(elf.header.e_entry)));
        if (opd[0] != codeAddress || opd[1] != dataAddress)
            throw std::runtime_error("P18 loaded entry descriptor mismatch");
        for (u32 i = 8; i < 64; ++i) if (guest[0x400 + i] != 0)
            throw std::runtime_error("P18 data segment BSS was not zero-filled");
        auto interpreter = std::make_unique<ppu_interpreter_rt>();
        utils::memory_commit(vm::g_exec_addr + u64(address) * 2, 0x20000, utils::protection::rw);
        auto* cache = reinterpret_cast<ppu_intrp_func*>(vm::g_exec_addr + u64(codeAddress) * 2);
        const auto* loadedCode = static_cast<const be_t<u32>*>(vm::base(codeAddress));
        for (u32 i = 0; i < 6; ++i) { cache[i].fn = interpreter->decode(loadedCode[i]);
            if (!cache[i].fn) throw std::runtime_error("P18 loaded instruction decode failed"); }
        struct Program { u32 begin, end; int result = -99; bool tls = false; std::atomic<bool> completed{false}; }
            program{u32(opd[0]), codeAddress + 24};
        const auto created = cpu_thread::g_threads_created.load(), deleted = cpu_thread::g_threads_deleted.load();
        const u64 live = armsx3_ios_live_cpu_threads();
        {
            std::unique_ptr<named_thread<ppu_thread>> worker;
            {
                struct ConstructionID { u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                const ppu_thread_params params{static_cast<vm::addr_t>(address + 0x1000), 0x8000, 0, {}, 0, 0};
                worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS loaded ELF probe", 1000);
            }
            struct StopWorker { named_thread<ppu_thread>& worker;
                ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                    worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); } } stop{*worker};
            const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                program.result = armsx3_ios_ppu_exec_bounded(&context, program.begin, program.end, 64);
                context.state += cpu_flag::exit; program.completed.store(true, std::memory_order_release);
            };
            worker->cmd_list({{ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
            worker->cia = program.begin; worker->gpr[2] = opd[1]; worker->gpr[6] = dataAddress + 32;
            worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            ARMSX3StartupLog("P18 BEFORE executing code loaded from on-disk ELF through core reader");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire)) throw std::runtime_error("P18 loaded ELF execution deadline exceeded");
            (*worker)();
            if (!program.tls || program.result != 6 || worker->gpr[5] != 35 || worker->gpr[7] != 35 ||
                worker->gpr[8] != 0x123 || worker->gpr[2] != dataAddress || worker->cia != program.end)
                throw std::runtime_error("P18 loaded ELF execution result mismatch");
        }
        for (u32 i = 0; i < 0x10000; ++i) {
            u8 expected = 0xa5;
            if (i >= 0x100 && i < 0x100 + sizeof(opcodes)) expected = fixture[i];
            if (i >= 0x400 && i < 0x440) expected = i < 0x408 ? fixture[0x200 + i - 0x400] : 0;
            if (i >= 0x420 && i < 0x424) expected = i == 0x423 ? 35 : 0;
            if (guest[i] != expected || static_cast<const u8*>(vm::get_super_ptr(address))[i] != expected)
                throw std::runtime_error("P18 loaded segment, BSS, guest guard or alias mismatch");
        }
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 1 ||
            cpu_thread::g_threads_deleted.load() != deleted + 1)
            throw std::runtime_error("P18 worker counters did not balance");
        if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
            throw std::runtime_error("P18 guest deallocation failed");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P18 PASS: on-disk ELF core parsing, bounded segment mapping, OPD/BSS, six loaded PPU instructions and cleanup; full module loading/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}

extern void ppu_register_range(u32, u32);
extern void ppu_register_function_at(u32, u32, ppu_intrp_func_t);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_registered_elf()
{
    ARMSX3StartupLog("P19 BEFORE core ELF reader, segment mapping and PPU execution");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P19 requires stopped emulator");
        struct Configuration
        {
            bool debugPPU = g_cfg.core.ppu_debug.get();
            bool ppu = g_cfg.core.ppu_prof.get(), spu = g_cfg.core.spu_prof.get(), debug = g_cfg.core.spu_debug.get();
            thread_scheduler_mode scheduler = g_cfg.core.thread_scheduler.get();
            ppu_decoder_type decoder = g_cfg.core.ppu_decoder.get();
            Configuration() { g_cfg.core.ppu_debug.set(false); g_cfg.core.ppu_prof.set(false); g_cfg.core.spu_prof.set(false);
                g_cfg.core.spu_debug.set(false); g_cfg.core.thread_scheduler.set(thread_scheduler_mode::os);
                g_cfg.core.ppu_decoder.set(ppu_decoder_type::_static); }
            ~Configuration() { g_cfg.core.ppu_debug.set(debugPPU); g_cfg.core.ppu_prof.set(ppu); g_cfg.core.spu_prof.set(spu);
                g_cfg.core.spu_debug.set(debug); g_cfg.core.thread_scheduler.set(scheduler);
                g_cfg.core.ppu_decoder.set(decoder); }
        } configuration;
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x20000))
            throw std::runtime_error("P19 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P19 guest allocation failed");
        const u32 codeAddress = address + 0x100, dataAddress = address + 0x400;
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        const std::array<u32, 7> opcodes{dform(14, 3, 0, 42), dform(14, 4, 0, 0xfff9),
            (31u << 26) | (5u << 21) | (3u << 16) | (4u << 11) | (266u << 1),
            dform(36, 5, 6, 0), dform(32, 7, 6, 0), dform(24, 7, 8, 0x100), 0};
        ppu_exec_object::ehdr_t header{};
        header.e_magic = "\177ELF"_u32; header.e_class = 2; header.e_data = 2;
        header.e_curver = 1; header.e_os_abi = elf_os::lv2; header.e_type = elf_type::exec;
        header.e_machine = elf_machine::ppc64; header.e_version = 1;
        header.e_entry = dataAddress; header.e_phoff = sizeof(header);
        header.e_ehsize = sizeof(header); header.e_phentsize = sizeof(ppu_exec_object::phdr_t); header.e_phnum = 2;
        std::array<ppu_exec_object::phdr_t, 2> segments{};
        segments[0].p_type = 1; segments[0].p_flags = 5; segments[0].p_offset = 0x100;
        segments[0].p_vaddr = codeAddress; segments[0].p_filesz = sizeof(opcodes);
        segments[0].p_memsz = sizeof(opcodes); segments[0].p_align = 16;
        segments[1].p_type = 1; segments[1].p_flags = 6; segments[1].p_offset = 0x200;
        segments[1].p_vaddr = dataAddress; segments[1].p_filesz = 8;
        segments[1].p_memsz = 64; segments[1].p_align = 16;
        std::vector<u8> fixture(0x208, 0);
        std::memcpy(fixture.data(), &header, sizeof(header));
        std::memcpy(fixture.data() + sizeof(header), segments.data(), sizeof(segments));
        for (u32 i = 0; i < opcodes.size(); ++i) {
            const be_t<u32> word = opcodes[i]; std::memcpy(fixture.data() + 0x100 + i * 4, &word, 4);
        }
        const std::array<be_t<u32>, 2> descriptor{codeAddress, dataAddress};
        std::memcpy(fixture.data() + 0x200, descriptor.data(), sizeof(descriptor));
        // Reject malformed header/short payload with the actual core reader.
        for (unsigned test = 0; test < 5; ++test) {
            auto malformed = fixture;
            if (test == 0) malformed[0] = 0;
            if (test == 1) malformed[4] = 1;
            if (test == 2) malformed[5] = 1;
            if (test == 3) malformed[19] = 0x17;
            if (test == 4) malformed.resize(0x204);
            const auto stream = fs::make_stream(std::move(malformed));
            ppu_exec_object rejected(stream);
            const std::array<elf_error, 5> errors{elf_error::header_magic, elf_error::header_class,
                elf_error::header_endianness, elf_error::header_machine, elf_error::stream_data};
            if (rejected.get_error() != errors[test]) throw std::runtime_error("P19 malformed ELF was not rejected correctly");
        }
        ARMSX3StartupLog("P19 PASS: core ELF reader rejects bad magic/class/endian/machine and truncated data");
        const auto validSegment = [&](const ppu_exec_object::prog_t& segment) {
            const u64 base = segment.p_vaddr, length = segment.p_memsz, fileSize = segment.p_filesz;
            return segment.p_type == 1u && base >= address && base < u64(address) + 0x10000 &&
                length <= 0x10000 - (base - address) && fileSize <= length && fileSize == segment.bin.size();
        };
        // ELF parsing does not imply safe mapping; independently bound segment sizes.
        auto oversized = fixture; auto huge = segments[1]; huge.p_memsz = ~u64{0};
        std::memcpy(oversized.data() + sizeof(header) + sizeof(huge), &huge, sizeof(huge));
        const auto oversizedStream = fs::make_stream(std::move(oversized));
        ppu_exec_object badMapping(oversizedStream);
        if (badMapping.get_error() != elf_error::ok || validSegment(badMapping.progs.at(1)))
            throw std::runtime_error("P19 segment mapping bounds guard failed");
        const std::string path = fs::get_cache_dir() + "ARMSX3-P19-diagnostic.elf";
        struct RemoveFixture { std::string path; ~RemoveFixture() { fs::remove_file(path); } } remove{path};
        {
            fs::file file(path, fs::rewrite);
            if (!file || file.write(fixture.data(), fixture.size()) != fixture.size())
                throw std::runtime_error("P19 ELF file write failed");
        }
        const fs::file file(path, fs::read);
        ppu_exec_object elf(file);
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 2 || elf.header.e_entry != dataAddress)
            throw std::runtime_error("P19 on-disk ELF header or segment parse failed");
        for (const auto& segment : elf.progs) if (!validSegment(segment))
            throw std::runtime_error("P19 ELF segment outside diagnostic allocation");
        auto* guest = static_cast<u8*>(vm::base(address)); std::memset(guest, 0xa5, 0x10000);
        for (const auto& segment : elf.progs) {
            auto* target = vm::base(u32(segment.p_vaddr));
            std::memset(target, 0, u64(segment.p_memsz));
            std::memcpy(target, segment.bin.data(), segment.bin.size());
        }
        const auto* opd = static_cast<const be_t<u32>*>(vm::base(u32(elf.header.e_entry)));
        if (opd[0] != codeAddress || opd[1] != dataAddress)
            throw std::runtime_error("P19 loaded entry descriptor mismatch");
        for (u32 i = 8; i < 64; ++i) if (guest[0x400 + i] != 0)
            throw std::runtime_error("P19 data segment BSS was not zero-filled");
        // Use the core-owned decoder and the loader's real registration routines.
        // Retain the fixed object until the core resets its object table on next boot.
        if (!g_fxo->is_init()) throw std::runtime_error("P19 fixed object table unavailable");
        if (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>())
            throw std::runtime_error("P19 core interpreter initialization failed");
        auto& interpreter = g_fxo->get<ppu_interpreter_rt>();
        auto* cache = reinterpret_cast<ppu_intrp_func*>(vm::g_exec_addr + u64(codeAddress) * 2);
        const auto* loadedCode = static_cast<const be_t<u32>*>(vm::base(codeAddress));
        struct SegmentCacheCleanup {
            u8* pointer; bool active = false;
            void release() { if (active) { utils::memory_decommit(pointer, 0x8000); active = false; } }
            ~SegmentCacheCleanup() { release(); }
        } segmentCleanup{vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1)};
        for (unsigned pass = 0; pass < 2; ++pass)
        {
            segmentCleanup.active = true;
            ppu_register_range(codeAddress, 24);
            if (!vm::check_addr(address, vm::page_executable, 0x10000))
                throw std::runtime_error("P19 production executable page flags missing");
            const auto fallback = cache[0].fn;
            if (!fallback) throw std::runtime_error("P19 registration fallback missing");
            const auto* allCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(address) * 2);
            const auto* segmentCache = reinterpret_cast<const u16*>(vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1));
            for (u32 i = 0; i < 0x10000 / 4; ++i)
                if (allCache[i].fn != fallback || segmentCache[i] != 0)
                    throw std::runtime_error("P19 production range cache initialization mismatch");
            for (u32 i = 0; i < 6; ++i)
                if (interpreter.decode(loadedCode[i]) == fallback)
                    throw std::runtime_error("P19 fallback unexpectedly matches decoded instruction");
            if (pass == 1) ppu_register_function_at(codeAddress, 24, nullptr);
            for (u32 i = 0; i < 6; ++i)
                if (cache[i].fn != (pass == 0 ? fallback : interpreter.decode(loadedCode[i])))
                    throw std::runtime_error("P19 lazy/eager cache preparation mismatch");
            std::memset(guest + 0x420, 0, 4);
        struct Program { u32 begin, end; int result = -99; bool tls = false; std::atomic<bool> completed{false}; }
            program{u32(opd[0]), codeAddress + 24};
        const auto created = cpu_thread::g_threads_created.load(), deleted = cpu_thread::g_threads_deleted.load();
        const u64 live = armsx3_ios_live_cpu_threads();
        {
            std::unique_ptr<named_thread<ppu_thread>> worker;
            {
                struct ConstructionID { u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                const ppu_thread_params params{static_cast<vm::addr_t>(address + 0x1000), 0x8000, 0, {}, 0, 0};
                worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS loaded ELF probe", 1000);
            }
            struct StopWorker { named_thread<ppu_thread>& worker;
                ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                    worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); } } stop{*worker};
            const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                program.result = armsx3_ios_ppu_exec_bounded(&context, program.begin, program.end, 64);
                context.state += cpu_flag::exit; program.completed.store(true, std::memory_order_release);
            };
            worker->cmd_list({{ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
            worker->cia = program.begin; worker->gpr[2] = opd[1]; worker->gpr[6] = dataAddress + 32;
            worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            ARMSX3StartupLog("P19 BEFORE executing code loaded from on-disk ELF through core reader");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire)) throw std::runtime_error("P19 loaded ELF execution deadline exceeded");
            (*worker)();
            if (!program.tls || program.result != 6 || worker->gpr[5] != 35 || worker->gpr[7] != 35 ||
                worker->gpr[8] != 0x123 || worker->gpr[2] != dataAddress || worker->cia != program.end)
                throw std::runtime_error("P19 loaded ELF execution result mismatch");
        }
        for (u32 i = 0; i < 0x10000; ++i) {
            u8 expected = 0xa5;
            if (i >= 0x100 && i < 0x100 + sizeof(opcodes)) expected = fixture[i];
            if (i >= 0x400 && i < 0x440) expected = i < 0x408 ? fixture[0x200 + i - 0x400] : 0;
            if (i >= 0x420 && i < 0x424) expected = i == 0x423 ? 35 : 0;
            if (guest[i] != expected || static_cast<const u8*>(vm::get_super_ptr(address))[i] != expected)
                throw std::runtime_error("P19 loaded segment, BSS, guest guard or alias mismatch");
        }
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 1 ||
            cpu_thread::g_threads_deleted.load() != deleted + 1)
            throw std::runtime_error("P19 worker counters did not balance");
        for (u32 i = 0; i < 6; ++i)
            if (cache[i].fn != interpreter.decode(loadedCode[i]))
                throw std::runtime_error("P19 executed cache did not contain core decoded handlers");
        for (u32 i = 0; i < 0x10000 / 4; ++i)
            if ((i < 0x100 / 4 || i >= 0x100 / 4 + 6) && allCache[i].fn != fallback)
                throw std::runtime_error("P19 dispatch changed handler outside loaded code");
        ARMSX3StartupLog(pass == 0 ? "P19 PASS: production range registration and lazy fallback decode, six loaded instructions" :
            "P19 PASS: production range re-registration and eager function registration, six loaded instructions");
        }
        segmentCleanup.release();
        if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
            throw std::runtime_error("P19 guest deallocation failed");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P19 PASS: loader production registration, core-owned decoder, lazy/eager cache dispatch, twelve loaded PPU instructions and cleanup; full module loading/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}

extern "C" int armsx3_ios_ppu_prepare_module(const ppu_module<lv2_obj>*);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_analyzed_elf()
{
    ARMSX3StartupLog("P20 BEFORE core ELF reader, segment mapping and PPU execution");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P20 requires stopped emulator");
        struct Configuration
        {
            bool debugPPU = g_cfg.core.ppu_debug.get();
            bool ppu = g_cfg.core.ppu_prof.get(), spu = g_cfg.core.spu_prof.get(), debug = g_cfg.core.spu_debug.get();
            thread_scheduler_mode scheduler = g_cfg.core.thread_scheduler.get();
            ppu_decoder_type decoder = g_cfg.core.ppu_decoder.get();
            Configuration() { g_cfg.core.ppu_debug.set(false); g_cfg.core.ppu_prof.set(false); g_cfg.core.spu_prof.set(false);
                g_cfg.core.spu_debug.set(false); g_cfg.core.thread_scheduler.set(thread_scheduler_mode::os);
                g_cfg.core.ppu_decoder.set(ppu_decoder_type::_static); }
            ~Configuration() { g_cfg.core.ppu_debug.set(debugPPU); g_cfg.core.ppu_prof.set(ppu); g_cfg.core.spu_prof.set(spu);
                g_cfg.core.spu_debug.set(debug); g_cfg.core.thread_scheduler.set(scheduler);
                g_cfg.core.ppu_decoder.set(decoder); }
        } configuration;
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x20000))
            throw std::runtime_error("P20 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P20 guest allocation failed");
        const u32 codeAddress = address + 0x100, dataAddress = address + 0x400;
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        const std::array<u32, 8> opcodes{dform(14, 3, 0, 42), dform(14, 4, 0, 0xfff9),
            (31u << 26) | (5u << 21) | (3u << 16) | (4u << 11) | (266u << 1),
            dform(36, 5, 6, 0), dform(32, 7, 6, 0), dform(24, 7, 8, 0x100), 0x4e800020u, 0};
        ppu_exec_object::ehdr_t header{};
        header.e_magic = "\177ELF"_u32; header.e_class = 2; header.e_data = 2;
        header.e_curver = 1; header.e_os_abi = elf_os::lv2; header.e_type = elf_type::exec;
        header.e_machine = elf_machine::ppc64; header.e_version = 1;
        header.e_entry = dataAddress; header.e_phoff = sizeof(header);
        header.e_ehsize = sizeof(header); header.e_phentsize = sizeof(ppu_exec_object::phdr_t); header.e_phnum = 2;
        std::array<ppu_exec_object::phdr_t, 2> segments{};
        segments[0].p_type = 1; segments[0].p_flags = 5; segments[0].p_offset = 0x100;
        segments[0].p_vaddr = codeAddress; segments[0].p_filesz = sizeof(opcodes);
        segments[0].p_memsz = sizeof(opcodes); segments[0].p_align = 16;
        segments[1].p_type = 1; segments[1].p_flags = 6; segments[1].p_offset = 0x200;
        segments[1].p_vaddr = dataAddress; segments[1].p_filesz = 8;
        segments[1].p_memsz = 64; segments[1].p_align = 16;
        std::vector<u8> fixture(0x208, 0);
        std::memcpy(fixture.data(), &header, sizeof(header));
        std::memcpy(fixture.data() + sizeof(header), segments.data(), sizeof(segments));
        for (u32 i = 0; i < opcodes.size(); ++i) {
            const be_t<u32> word = opcodes[i]; std::memcpy(fixture.data() + 0x100 + i * 4, &word, 4);
        }
        const std::array<be_t<u32>, 2> descriptor{codeAddress, dataAddress};
        std::memcpy(fixture.data() + 0x200, descriptor.data(), sizeof(descriptor));
        // Reject malformed header/short payload with the actual core reader.
        for (unsigned test = 0; test < 5; ++test) {
            auto malformed = fixture;
            if (test == 0) malformed[0] = 0;
            if (test == 1) malformed[4] = 1;
            if (test == 2) malformed[5] = 1;
            if (test == 3) malformed[19] = 0x17;
            if (test == 4) malformed.resize(0x204);
            const auto stream = fs::make_stream(std::move(malformed));
            ppu_exec_object rejected(stream);
            const std::array<elf_error, 5> errors{elf_error::header_magic, elf_error::header_class,
                elf_error::header_endianness, elf_error::header_machine, elf_error::stream_data};
            if (rejected.get_error() != errors[test]) throw std::runtime_error("P20 malformed ELF was not rejected correctly");
        }
        ARMSX3StartupLog("P20 PASS: core ELF reader rejects bad magic/class/endian/machine and truncated data");
        const auto validSegment = [&](const ppu_exec_object::prog_t& segment) {
            const u64 base = segment.p_vaddr, length = segment.p_memsz, fileSize = segment.p_filesz;
            return segment.p_type == 1u && base >= address && base < u64(address) + 0x10000 &&
                length <= 0x10000 - (base - address) && fileSize <= length && fileSize == segment.bin.size();
        };
        // ELF parsing does not imply safe mapping; independently bound segment sizes.
        auto oversized = fixture; auto huge = segments[1]; huge.p_memsz = ~u64{0};
        std::memcpy(oversized.data() + sizeof(header) + sizeof(huge), &huge, sizeof(huge));
        const auto oversizedStream = fs::make_stream(std::move(oversized));
        ppu_exec_object badMapping(oversizedStream);
        if (badMapping.get_error() != elf_error::ok || validSegment(badMapping.progs.at(1)))
            throw std::runtime_error("P20 segment mapping bounds guard failed");
        const std::string path = fs::get_cache_dir() + "ARMSX3-P20-diagnostic.elf";
        struct RemoveFixture { std::string path; ~RemoveFixture() { fs::remove_file(path); } } remove{path};
        {
            fs::file file(path, fs::rewrite);
            if (!file || file.write(fixture.data(), fixture.size()) != fixture.size())
                throw std::runtime_error("P20 ELF file write failed");
        }
        const fs::file file(path, fs::read);
        ppu_exec_object elf(file);
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 2 || elf.header.e_entry != dataAddress)
            throw std::runtime_error("P20 on-disk ELF header or segment parse failed");
        for (const auto& segment : elf.progs) if (!validSegment(segment))
            throw std::runtime_error("P20 ELF segment outside diagnostic allocation");
        auto* guest = static_cast<u8*>(vm::base(address)); std::memset(guest, 0xa5, 0x10000);
        for (const auto& segment : elf.progs) {
            auto* target = vm::base(u32(segment.p_vaddr));
            std::memset(target, 0, u64(segment.p_memsz));
            std::memcpy(target, segment.bin.data(), segment.bin.size());
        }
        const auto* opd = static_cast<const be_t<u32>*>(vm::base(u32(elf.header.e_entry)));
        if (opd[0] != codeAddress || opd[1] != dataAddress)
            throw std::runtime_error("P20 loaded entry descriptor mismatch");
        for (u32 i = 8; i < 64; ++i) if (guest[0x400 + i] != 0)
            throw std::runtime_error("P20 data segment BSS was not zero-filled");
        // Use the core-owned decoder and the loader's real registration routines.
        // Retain the fixed object until the core resets its object table on next boot.
        if (!g_fxo->is_init()) throw std::runtime_error("P20 fixed object table unavailable");
        if (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>())
            throw std::runtime_error("P20 core interpreter initialization failed");
        auto& interpreter = g_fxo->get<ppu_interpreter_rt>();
        auto* cache = reinterpret_cast<ppu_intrp_func*>(vm::g_exec_addr + u64(codeAddress) * 2);
        const auto* loadedCode = static_cast<const be_t<u32>*>(vm::base(codeAddress));
        struct SegmentCacheCleanup {
            u8* pointer; bool active = false;
            void release() { if (active) { utils::memory_decommit(pointer, 0x8000); active = false; } }
            ~SegmentCacheCleanup() { release(); }
        } segmentCleanup{vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1)};
        ppu_module<lv2_obj> module;
        module.name = "iOS analyzed ELF probe"; module.path = path;
        for (const auto& segment : elf.progs) {
            module.addr_to_seg_index.emplace(u32(segment.p_vaddr), u32(module.segs.size()));
            module.segs.push_back({u32(segment.p_vaddr), u32(segment.p_memsz), u32(segment.p_type),
                u32(segment.p_flags), u32(segment.p_filesz), vm::base(u32(segment.p_vaddr))});
        }
        // A descriptor section gives the analyser an explicit OPD boundary.
        module.secs.push_back({dataAddress, 8, 1, 2, 8, vm::base(dataAddress)});
        const auto analysisDeadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
        ARMSX3StartupLog("P20 BEFORE actual executable analysis from loaded ELF segments and OPD");
        if (!module.analyse(0, dataAddress, codeAddress + 28, {}, {}, [&] {
                return std::chrono::steady_clock::now() >= analysisDeadline; }))
            throw std::runtime_error("P20 core executable analysis failed or timed out");
        if (module.funcs.empty()) throw std::runtime_error("P20 analysis found no functions");
        bool entryFound = false;
        for (const auto& function : module.funcs) {
            if (function.addr == codeAddress) entryFound = true;
            if (function.addr < codeAddress || function.addr >= codeAddress + 28 ||
                function.addr % 4 || function.size > codeAddress + 28 - function.addr)
                throw std::runtime_error("P20 analysed function outside loaded executable");
            for (const auto& block : function.blocks)
                if (block.first < codeAddress || block.first >= codeAddress + 28 || block.first % 4 ||
                    block.second % 4 || block.second > codeAddress + 28 - block.first)
                    throw std::runtime_error("P20 analysed block outside loaded executable");
        }
        if (!entryFound) throw std::runtime_error("P20 analyser missed entry function");
        segmentCleanup.active = true;
        ppu_register_range(codeAddress, 28);
        if (!vm::check_addr(address, vm::page_executable, 0x10000))
            throw std::runtime_error("P20 executable page flags missing");
        const auto fallback = cache[0].fn;
        const auto* allCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(address) * 2);
        ARMSX3StartupLog("P20 BEFORE production static module initialization of analysed functions");
        if (armsx3_ios_ppu_prepare_module(&module) != 0)
            throw std::runtime_error("P20 static module preparation failed");
        for (u32 i = 0; i < 7; ++i)
            if (!cache[i].fn || cache[i].fn != interpreter.decode(loadedCode[i]) || cache[i].fn == fallback)
                throw std::runtime_error("P20 module initialization did not decode analysed code");
        char analysisMessage[160];
        std::snprintf(analysisMessage, sizeof(analysisMessage), "P20 PASS: actual analyser found %zu functions; static module initialization decoded seven instructions", module.funcs.size());
        ARMSX3StartupLog(analysisMessage);
        struct Program { u32 begin, end; int result = -99; bool tls = false; std::atomic<bool> completed{false}; }
            program{u32(opd[0]), codeAddress + 28};
        const auto created = cpu_thread::g_threads_created.load(), deleted = cpu_thread::g_threads_deleted.load();
        const u64 live = armsx3_ios_live_cpu_threads();
        {
            std::unique_ptr<named_thread<ppu_thread>> worker;
            {
                struct ConstructionID { u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                const ppu_thread_params params{static_cast<vm::addr_t>(address + 0x1000), 0x8000, 0, {}, 0, 0};
                worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS loaded ELF probe", 1000);
            }
            struct StopWorker { named_thread<ppu_thread>& worker;
                ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                    worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); } } stop{*worker};
            const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                program.result = armsx3_ios_ppu_exec_bounded(&context, program.begin, program.end, 64);
                context.state += cpu_flag::exit; program.completed.store(true, std::memory_order_release);
            };
            worker->cmd_list({{ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
            worker->cia = program.begin; worker->lr = program.end; worker->gpr[2] = opd[1]; worker->gpr[6] = dataAddress + 32;
            worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            ARMSX3StartupLog("P20 BEFORE executing code loaded from on-disk ELF through core reader");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire)) throw std::runtime_error("P20 loaded ELF execution deadline exceeded");
            (*worker)();
            if (!program.tls || program.result != 7 || worker->gpr[5] != 35 || worker->gpr[7] != 35 ||
                worker->gpr[8] != 0x123 || worker->gpr[2] != dataAddress || worker->cia != program.end)
                throw std::runtime_error("P20 loaded ELF execution result mismatch");
        }
        for (u32 i = 0; i < 0x10000; ++i) {
            u8 expected = 0xa5;
            if (i >= 0x100 && i < 0x100 + sizeof(opcodes)) expected = fixture[i];
            if (i >= 0x400 && i < 0x440) expected = i < 0x408 ? fixture[0x200 + i - 0x400] : 0;
            if (i >= 0x420 && i < 0x424) expected = i == 0x423 ? 35 : 0;
            if (guest[i] != expected || static_cast<const u8*>(vm::get_super_ptr(address))[i] != expected)
                throw std::runtime_error("P20 loaded segment, BSS, guest guard or alias mismatch");
        }
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 1 ||
            cpu_thread::g_threads_deleted.load() != deleted + 1)
            throw std::runtime_error("P20 worker counters did not balance");
        for (u32 i = 0; i < 7; ++i)
            if (cache[i].fn != interpreter.decode(loadedCode[i]))
                throw std::runtime_error("P20 executed cache did not contain core decoded handlers");
        for (u32 i = 0; i < 0x10000 / 4; ++i)
            if ((i < 0x100 / 4 || i >= 0x100 / 4 + 7) && allCache[i].fn != fallback)
                throw std::runtime_error("P20 dispatch changed handler outside loaded code");
        segmentCleanup.release();
        if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
            throw std::runtime_error("P20 guest deallocation failed");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P20 PASS: core executable analysis, production static module preparation, seven loaded PPU instructions with return and cleanup; full executable loader/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}

extern "C" int armsx3_ios_ppu_call_bounded(ppu_thread*, u32, u32, u64, u32, u32);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_elf_call()
{
    ARMSX3StartupLog("P21 BEFORE core ELF reader, segment mapping and PPU execution");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P21 requires stopped emulator");
        struct Configuration
        {
            bool debugPPU = g_cfg.core.ppu_debug.get();
            bool ppu = g_cfg.core.ppu_prof.get(), spu = g_cfg.core.spu_prof.get(), debug = g_cfg.core.spu_debug.get();
            thread_scheduler_mode scheduler = g_cfg.core.thread_scheduler.get();
            ppu_decoder_type decoder = g_cfg.core.ppu_decoder.get();
            Configuration() { g_cfg.core.ppu_debug.set(false); g_cfg.core.ppu_prof.set(false); g_cfg.core.spu_prof.set(false);
                g_cfg.core.spu_debug.set(false); g_cfg.core.thread_scheduler.set(thread_scheduler_mode::os);
                g_cfg.core.ppu_decoder.set(ppu_decoder_type::_static); }
            ~Configuration() { g_cfg.core.ppu_debug.set(debugPPU); g_cfg.core.ppu_prof.set(ppu); g_cfg.core.spu_prof.set(spu);
                g_cfg.core.spu_debug.set(debug); g_cfg.core.thread_scheduler.set(scheduler);
                g_cfg.core.ppu_decoder.set(decoder); }
        } configuration;
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x20000))
            throw std::runtime_error("P21 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P21 guest allocation failed");
        const u32 codeAddress = address + 0x100, dataAddress = address + 0x400;
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        using namespace ppu_instructions;
        using namespace ppu_instructions::implicts;
        const std::array<u32, 15> opcodes{MFLR(0), STDU(1, 1, -128), STD(0, 1, 16), dform(24, 2, 9, 0),
            dform(14, 3, 0, 42), dform(14, 4, 0, 0xfff9),
            (31u << 26) | (5u << 21) | (3u << 16) | (4u << 11) | (266u << 1),
            dform(36, 5, 6, 0), dform(32, 7, 6, 0), dform(24, 7, 8, 0x100),
            LD(0, 1, 16), ADDI(1, 1, 128), MTLR(0), BLR(), 0};
        ppu_exec_object::ehdr_t header{};
        header.e_magic = "\177ELF"_u32; header.e_class = 2; header.e_data = 2;
        header.e_curver = 1; header.e_os_abi = elf_os::lv2; header.e_type = elf_type::exec;
        header.e_machine = elf_machine::ppc64; header.e_version = 1;
        header.e_entry = dataAddress; header.e_phoff = sizeof(header);
        header.e_ehsize = sizeof(header); header.e_phentsize = sizeof(ppu_exec_object::phdr_t); header.e_phnum = 2;
        std::array<ppu_exec_object::phdr_t, 2> segments{};
        segments[0].p_type = 1; segments[0].p_flags = 5; segments[0].p_offset = 0x100;
        segments[0].p_vaddr = codeAddress; segments[0].p_filesz = sizeof(opcodes);
        segments[0].p_memsz = sizeof(opcodes); segments[0].p_align = 16;
        segments[1].p_type = 1; segments[1].p_flags = 6; segments[1].p_offset = 0x200;
        segments[1].p_vaddr = dataAddress; segments[1].p_filesz = 8;
        segments[1].p_memsz = 64; segments[1].p_align = 16;
        std::vector<u8> fixture(0x208, 0);
        std::memcpy(fixture.data(), &header, sizeof(header));
        std::memcpy(fixture.data() + sizeof(header), segments.data(), sizeof(segments));
        for (u32 i = 0; i < opcodes.size(); ++i) {
            const be_t<u32> word = opcodes[i]; std::memcpy(fixture.data() + 0x100 + i * 4, &word, 4);
        }
        const std::array<be_t<u32>, 2> descriptor{codeAddress, dataAddress};
        std::memcpy(fixture.data() + 0x200, descriptor.data(), sizeof(descriptor));
        // Reject malformed header/short payload with the actual core reader.
        for (unsigned test = 0; test < 5; ++test) {
            auto malformed = fixture;
            if (test == 0) malformed[0] = 0;
            if (test == 1) malformed[4] = 1;
            if (test == 2) malformed[5] = 1;
            if (test == 3) malformed[19] = 0x17;
            if (test == 4) malformed.resize(0x204);
            const auto stream = fs::make_stream(std::move(malformed));
            ppu_exec_object rejected(stream);
            const std::array<elf_error, 5> errors{elf_error::header_magic, elf_error::header_class,
                elf_error::header_endianness, elf_error::header_machine, elf_error::stream_data};
            if (rejected.get_error() != errors[test]) throw std::runtime_error("P21 malformed ELF was not rejected correctly");
        }
        ARMSX3StartupLog("P21 PASS: core ELF reader rejects bad magic/class/endian/machine and truncated data");
        const auto validSegment = [&](const ppu_exec_object::prog_t& segment) {
            const u64 base = segment.p_vaddr, length = segment.p_memsz, fileSize = segment.p_filesz;
            return segment.p_type == 1u && base >= address && base < u64(address) + 0x10000 &&
                length <= 0x10000 - (base - address) && fileSize <= length && fileSize == segment.bin.size();
        };
        // ELF parsing does not imply safe mapping; independently bound segment sizes.
        auto oversized = fixture; auto huge = segments[1]; huge.p_memsz = ~u64{0};
        std::memcpy(oversized.data() + sizeof(header) + sizeof(huge), &huge, sizeof(huge));
        const auto oversizedStream = fs::make_stream(std::move(oversized));
        ppu_exec_object badMapping(oversizedStream);
        if (badMapping.get_error() != elf_error::ok || validSegment(badMapping.progs.at(1)))
            throw std::runtime_error("P21 segment mapping bounds guard failed");
        const std::string path = fs::get_cache_dir() + "ARMSX3-P21-diagnostic.elf";
        struct RemoveFixture { std::string path; ~RemoveFixture() { fs::remove_file(path); } } remove{path};
        {
            fs::file file(path, fs::rewrite);
            if (!file || file.write(fixture.data(), fixture.size()) != fixture.size())
                throw std::runtime_error("P21 ELF file write failed");
        }
        const fs::file file(path, fs::read);
        ppu_exec_object elf(file);
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 2 || elf.header.e_entry != dataAddress)
            throw std::runtime_error("P21 on-disk ELF header or segment parse failed");
        for (const auto& segment : elf.progs) if (!validSegment(segment))
            throw std::runtime_error("P21 ELF segment outside diagnostic allocation");
        auto* guest = static_cast<u8*>(vm::base(address)); std::memset(guest, 0xa5, 0x10000);
        for (const auto& segment : elf.progs) {
            auto* target = vm::base(u32(segment.p_vaddr));
            std::memset(target, 0, u64(segment.p_memsz));
            std::memcpy(target, segment.bin.data(), segment.bin.size());
        }
        const auto* opd = static_cast<const be_t<u32>*>(vm::base(u32(elf.header.e_entry)));
        if (opd[0] != codeAddress || opd[1] != dataAddress)
            throw std::runtime_error("P21 loaded entry descriptor mismatch");
        for (u32 i = 8; i < 64; ++i) if (guest[0x400 + i] != 0)
            throw std::runtime_error("P21 data segment BSS was not zero-filled");
        // Use the core-owned decoder and the loader's real registration routines.
        // Retain the fixed object until the core resets its object table on next boot.
        if (!g_fxo->is_init()) throw std::runtime_error("P21 fixed object table unavailable");
        if (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>())
            throw std::runtime_error("P21 core interpreter initialization failed");
        auto& interpreter = g_fxo->get<ppu_interpreter_rt>();
        auto* cache = reinterpret_cast<ppu_intrp_func*>(vm::g_exec_addr + u64(codeAddress) * 2);
        const auto* loadedCode = static_cast<const be_t<u32>*>(vm::base(codeAddress));
        struct SegmentCacheCleanup {
            u8* pointer; bool active = false;
            void release() { if (active) { utils::memory_decommit(pointer, 0x8000); active = false; } }
            ~SegmentCacheCleanup() { release(); }
        } segmentCleanup{vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1)};
        ppu_module<lv2_obj> module;
        module.name = "iOS analyzed ELF probe"; module.path = path;
        for (const auto& segment : elf.progs) {
            module.addr_to_seg_index.emplace(u32(segment.p_vaddr), u32(module.segs.size()));
            module.segs.push_back({u32(segment.p_vaddr), u32(segment.p_memsz), u32(segment.p_type),
                u32(segment.p_flags), u32(segment.p_filesz), vm::base(u32(segment.p_vaddr))});
        }
        // A descriptor section gives the analyser an explicit OPD boundary.
        module.secs.push_back({dataAddress, 8, 1, 2, 8, vm::base(dataAddress)});
        const auto analysisDeadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
        ARMSX3StartupLog("P21 BEFORE actual executable analysis from loaded ELF segments and OPD");
        if (!module.analyse(0, dataAddress, codeAddress + 56, {}, {}, [&] {
                return std::chrono::steady_clock::now() >= analysisDeadline; }))
            throw std::runtime_error("P21 core executable analysis failed or timed out");
        if (module.funcs.empty()) throw std::runtime_error("P21 analysis found no functions");
        bool entryFound = false;
        for (const auto& function : module.funcs) {
            if (function.addr == codeAddress) entryFound = true;
            if (function.addr < codeAddress || function.addr >= codeAddress + 56 ||
                function.addr % 4 || function.size > codeAddress + 56 - function.addr)
                throw std::runtime_error("P21 analysed function outside loaded executable");
            for (const auto& block : function.blocks)
                if (block.first < codeAddress || block.first >= codeAddress + 56 || block.first % 4 ||
                    block.second % 4 || block.second > codeAddress + 56 - block.first)
                    throw std::runtime_error("P21 analysed block outside loaded executable");
        }
        if (!entryFound) throw std::runtime_error("P21 analyser missed entry function");
        segmentCleanup.active = true;
        ppu_register_range(codeAddress, 56);
        if (!vm::check_addr(address, vm::page_executable, 0x10000))
            throw std::runtime_error("P21 executable page flags missing");
        const auto fallback = cache[0].fn;
        const auto* allCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(address) * 2);
        ARMSX3StartupLog("P21 BEFORE production static module initialization of analysed functions");
        if (armsx3_ios_ppu_prepare_module(&module) != 0)
            throw std::runtime_error("P21 static module preparation failed");
        for (u32 i = 0; i < 14; ++i)
            if (!cache[i].fn || cache[i].fn != interpreter.decode(loadedCode[i]) || cache[i].fn == fallback)
                throw std::runtime_error("P21 module initialization did not decode analysed code");
        char analysisMessage[160];
        std::snprintf(analysisMessage, sizeof(analysisMessage), "P21 PASS: actual analyser found %zu functions; static module initialization decoded fourteen instructions", module.funcs.size());
        ARMSX3StartupLog(analysisMessage);
        if (!g_fxo->is_init<ppu_function_manager>() && !g_fxo->init<ppu_function_manager>())
            throw std::runtime_error("P21 function manager initialization failed");
        auto& manager = g_fxo->get<ppu_function_manager>();
        if (manager.addr) throw std::runtime_error("P21 requires unused function manager address");
        const u32 managerAddress = address + 0x800, returnAddress = managerAddress + 12;
        struct ManagerAddress { ppu_function_manager& manager; u32 previous;
            ~ManagerAddress() { manager.addr = previous; } } managerScope{manager, manager.addr};
        manager.addr = managerAddress;
        const auto& hleFunctions = ppu_function_manager::get();
        if (hleFunctions.size() < 2 || !hleFunctions[1] || manager.func_addr(1, true) != returnAddress)
            throw std::runtime_error("P21 core HLE return handler unavailable");
        vm::write32(managerAddress + 8, returnAddress); vm::write32(returnAddress, 0);
        ppu_register_function_at(returnAddress, 4, hleFunctions[1]);
        const u32 initialStack = address + 0x8000, frameAddress = initialStack - 128;
        struct Program { u32 begin, end, returnAddress; u64 toc; int result = -99; bool tls = false;
            std::atomic<bool> completed{false}; } program{u32(opd[0]), codeAddress + 56, returnAddress, u64(opd[1])};
        const auto created = cpu_thread::g_threads_created.load(), deleted = cpu_thread::g_threads_deleted.load();
        const u64 live = armsx3_ios_live_cpu_threads();
        {
            std::unique_ptr<named_thread<ppu_thread>> worker;
            {
                struct ConstructionID { u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                const ppu_thread_params params{static_cast<vm::addr_t>(address + 0x1000), 0x8000, 0, {}, 0, 0};
                worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS loaded ELF probe", 1000);
            }
            struct StopWorker { named_thread<ppu_thread>& worker;
                ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                    worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); } } stop{*worker};
            const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                program.result = armsx3_ios_ppu_call_bounded(&context, program.begin, program.end, program.toc, program.returnAddress, 64);
                context.state += cpu_flag::exit; program.completed.store(true, std::memory_order_release);
            };
            worker->cmd_list({{ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
            worker->cia = address + 0x900; worker->lr = address + 0x904;
            worker->gpr[1] = initialStack; worker->gpr[2] = 0x13579; worker->gpr[6] = dataAddress + 32;
            worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            ARMSX3StartupLog("P21 BEFORE actual fast_call, guest stack frame and core HLE return handler");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire)) throw std::runtime_error("P21 loaded ELF execution deadline exceeded");
            (*worker)();
            if (!program.tls || program.result != 15 || worker->gpr[5] != 35 || worker->gpr[7] != 35 ||
                worker->gpr[8] != 0x123 || worker->gpr[9] != dataAddress || worker->gpr[2] != 0x13579 || worker->cia != address + 0x900 ||
                worker->lr != address + 0x904 || worker->gpr[1] != initialStack || worker->state & cpu_flag::ret)
                throw std::runtime_error("P21 loaded ELF execution result mismatch");
        }
        for (u32 i = 0; i < 0x10000; ++i) {
            u8 expected = 0xa5;
            if (i >= 0x100 && i < 0x100 + sizeof(opcodes)) expected = fixture[i];
            if (i >= 0x400 && i < 0x440) expected = i < 0x408 ? fixture[0x200 + i - 0x400] : 0;
            if (i >= 0x420 && i < 0x424) expected = i == 0x423 ? 35 : 0;
            if (i >= 0x808 && i < 0x80c) expected = u8(returnAddress >> (24 - (i - 0x808) * 8));
            if (i >= 0x80c && i < 0x810) expected = 0;
            const u32 frameOffset = frameAddress - address;
            if (i >= frameOffset && i < frameOffset + 8) expected = u8(u64(initialStack) >> (56 - (i - frameOffset) * 8));
            if (i >= frameOffset + 16 && i < frameOffset + 24) expected = u8(u64(returnAddress) >> (56 - (i - frameOffset - 16) * 8));
            if (guest[i] != expected || static_cast<const u8*>(vm::get_super_ptr(address))[i] != expected)
                throw std::runtime_error("P21 loaded segment, BSS, guest guard or alias mismatch");
        }
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 1 ||
            cpu_thread::g_threads_deleted.load() != deleted + 1)
            throw std::runtime_error("P21 worker counters did not balance");
        for (u32 i = 0; i < 14; ++i)
            if (cache[i].fn != interpreter.decode(loadedCode[i]))
                throw std::runtime_error("P21 executed cache did not contain core decoded handlers");
        for (u32 i = 0; i < 0x10000 / 4; ++i)
            if ((i < 0x100 / 4 || i >= 0x100 / 4 + 14) && i != (returnAddress - address) / 4 && allCache[i].fn != fallback)
                throw std::runtime_error("P21 dispatch changed handler outside loaded code");
        manager.addr = managerScope.previous;
        segmentCleanup.release();
        if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
            throw std::runtime_error("P21 guest deallocation failed");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P21 PASS: analysed ELF fast_call, fourteen guest instructions, stack/LR save and restore, actual HLE return and caller context cleanup; full executable loader/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}


// Exercise the allocator used by ppu_load_exec with separate 64 KiB pages.
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_elf_fixed_segments()
{
    ARMSX3StartupLog("P22 BEFORE fixed-address ELF segment allocation");
    bool initialized = false;
    try {
        if (!Emu.IsStopped()) throw std::runtime_error("P22 requires stopped emulator");
        vm::init(); initialized = true;
        const auto area = vm::reserve_map(vm::main, 0x10000, 0x40000, vm::block_size_64k);
        if (!area || area->addr != 0x10000 || (area->flags & 0xf00) != vm::block_size_64k)
            throw std::runtime_error("P22 main allocation area mismatch");
        constexpr u32 codeAddress = 0x10100, dataAddress = 0x30400;
        ppu_exec_object::ehdr_t header{};
        header.e_magic = "\177ELF"_u32; header.e_class = 2; header.e_data = 2;
        header.e_curver = 1; header.e_os_abi = elf_os::lv2; header.e_type = elf_type::exec;
        header.e_machine = elf_machine::ppc64; header.e_version = 1;
        header.e_entry = dataAddress; header.e_phoff = sizeof(header);
        header.e_ehsize = sizeof(header); header.e_phentsize = sizeof(ppu_exec_object::phdr_t); header.e_phnum = 2;
        std::array<ppu_exec_object::phdr_t, 2> segments{};
        segments[0].p_type = 1; segments[0].p_flags = 5; segments[0].p_offset = 0x100;
        segments[0].p_vaddr = codeAddress; segments[0].p_filesz = 8; segments[0].p_memsz = 64; segments[0].p_align = 16;
        segments[1].p_type = 1; segments[1].p_flags = 6; segments[1].p_offset = 0x200;
        segments[1].p_vaddr = dataAddress; segments[1].p_filesz = 8; segments[1].p_memsz = 128; segments[1].p_align = 16;
        std::vector<u8> fixture(0x208, 0);
        std::memcpy(fixture.data(), &header, sizeof(header));
        std::memcpy(fixture.data() + sizeof(header), segments.data(), sizeof(segments));
        const std::array<be_t<u32>, 2> instructions{0x3860002au, 0x4e800020u};
        const std::array<be_t<u32>, 2> descriptor{codeAddress, dataAddress};
        std::memcpy(fixture.data() + 0x100, instructions.data(), 8);
        std::memcpy(fixture.data() + 0x200, descriptor.data(), 8);
        const std::string path = fs::get_cache_dir() + "ARMSX3-P22-diagnostic.elf";
        struct RemoveFixture { std::string path; ~RemoveFixture() { fs::remove_file(path); } } remove{path};
        { fs::file file(path, fs::rewrite);
          if (!file || file.write(fixture.data(), fixture.size()) != fixture.size())
              throw std::runtime_error("P22 fixture write failed"); }
        const fs::file file(path, fs::read); const ppu_exec_object elf(file);
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 2)
            throw std::runtime_error("P22 ELF parse failed");
        const auto validSegment = [](const ppu_exec_object::prog_t& p) {
            const u64 address = p.p_vaddr, size = p.p_memsz;
            return p.p_type == 1 && address >= 0x10000 && address < 0x50000 && size &&
                size <= 0x50000 - address && u64(p.p_filesz) <= size && p.bin.size() == p.p_filesz;
        };
        for (const auto& p : elf.progs) if (!validSegment(p))
            throw std::runtime_error("P22 segment bounds invalid");
        // Failure after the first allocation must release that allocation.
        // The second segment deliberately collides with the first 64 KiB page.
        if (!area->falloc(codeAddress, 64)) throw std::runtime_error("P22 initial fixed allocation failed");
        if (area->falloc(codeAddress + 32, 128)) throw std::runtime_error("P22 overlapping allocation accepted");
        if (area->dealloc(0x10000) != 0x10000 || vm::check_addr(0x10000))
            throw std::runtime_error("P22 partial allocation rollback failed");
        if (area->falloc(0x4fff0, 32) || area->falloc(0x8000, 64))
            throw std::runtime_error("P22 allocation outside reserved area accepted");
        ARMSX3StartupLog("P22 PASS: actual fixed allocator rejects overlap and area boundaries; partial allocation rollback");
        for (const auto& p : elf.progs) {
            // Same reserve/flag/falloc operations used by the production loader.
            const u32 address = u32(p.p_vaddr), size = u32(p.p_memsz);
            const auto targetArea = vm::reserve_map(vm::any, 0x10000, 0x10000000, vm::block_size_64k);
            if (targetArea != area || !targetArea->falloc(address, size))
                throw std::runtime_error("P22 loader-style fixed allocation failed");
            const auto* before = static_cast<const u8*>(vm::base(address));
            for (u32 i = 0; i < size; ++i) if (before[i])
                throw std::runtime_error("P22 new segment was not zero-filled");
            std::memcpy(vm::base(address), p.bin.data(), p.bin.size());
        }
        if (vm::check_addr(0x20000) || vm::check_addr(0x40000))
            throw std::runtime_error("P22 unmapped segment gaps became allocated");
        // Verify every byte of both backing pages, including alignment padding,
        // untouched BSS and both guest aliases; do not write either gap page.
        for (u32 page : {0x10000u, 0x30000u}) {
            if (!vm::check_addr(page, vm::page_readable | vm::page_writable, 0x10000))
                throw std::runtime_error("P22 mapped page permissions missing");
            const auto* normal = static_cast<const u8*>(vm::base(page));
            const auto* privileged = static_cast<const u8*>(vm::get_super_ptr(page));
            const u32 offset = page == 0x10000 ? 0x100 : 0x400;
            const u32 fileOffset = page == 0x10000 ? 0x100 : 0x200;
            for (u32 i = 0; i < 0x10000; ++i) {
                const u8 expected = i >= offset && i < offset + 8 ? fixture[fileOffset + i - offset] : 0;
                if (normal[i] != expected || privileged[i] != expected)
                    throw std::runtime_error("P22 segment payload/BSS/padding/alias mismatch");
            }
        }
        if (area->dealloc(0x30000) != 0x10000 || area->dealloc(0x10000) != 0x10000 ||
            vm::check_addr(0x10000) || vm::check_addr(0x30000))
            throw std::runtime_error("P22 fixed segment cleanup failed");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P22 PASS: on-disk ELF, separate fixed code/data allocations, zero-filled BSS/padding, aliases, conflict rejection and rollback; full executable loader/firmware/game boot remain untested");
        return 0;
    } catch (const std::exception& error) {
        ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1;
    }
}

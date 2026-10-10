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
        auto area = vm::reserve_map(vm::main, 0x10000, 0x40000, vm::block_size_64k);
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
        // vm::close requires the VM table to own the only block reference.
        ARMSX3StartupLog("P22 BEFORE releasing block reference and closing guest VM");
        area.reset();
        vm::close(); initialized = false;
        ARMSX3StartupLog("P22 PASS: on-disk ELF, separate fixed code/data allocations, zero-filled BSS/padding, aliases, conflict rejection and rollback; full executable loader/firmware/game boot remain untested");
        return 0;
    } catch (const std::exception& error) {
        ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1;
    }
}
// Exercise the allocator used by ppu_load_exec with separate 64 KiB pages.
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_elf_protected_code()
{
    ARMSX3StartupLog("P23 BEFORE fixed-address ELF segment allocation");
    bool initialized = false;
    try {
        if (!Emu.IsStopped()) throw std::runtime_error("P23 requires stopped emulator");
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
        auto area = vm::reserve_map(vm::main, 0x10000, 0x40000, vm::block_size_64k);
        if (!area || area->addr != 0x10000 || (area->flags & 0xf00) != vm::block_size_64k)
            throw std::runtime_error("P23 main allocation area mismatch");
        constexpr u32 codeAddress = 0x10000, dataAddress = 0x30400;
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
        const std::array<be_t<u32>, 2> instructions{0x3860002au, 0x90660000u};
        const std::array<be_t<u32>, 2> descriptor{codeAddress, dataAddress};
        std::memcpy(fixture.data() + 0x100, instructions.data(), 8);
        std::memcpy(fixture.data() + 0x200, descriptor.data(), 8);
        const std::string path = fs::get_cache_dir() + "ARMSX3-P23-diagnostic.elf";
        struct RemoveFixture { std::string path; ~RemoveFixture() { fs::remove_file(path); } } remove{path};
        { fs::file file(path, fs::rewrite);
          if (!file || file.write(fixture.data(), fixture.size()) != fixture.size())
              throw std::runtime_error("P23 fixture write failed"); }
        const fs::file file(path, fs::read); const ppu_exec_object elf(file);
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 2)
            throw std::runtime_error("P23 ELF parse failed");
        const auto validSegment = [](const ppu_exec_object::prog_t& p) {
            const u64 address = p.p_vaddr, size = p.p_memsz;
            return p.p_type == 1 && address >= 0x10000 && address < 0x50000 && size &&
                size <= 0x50000 - address && u64(p.p_filesz) <= size && p.bin.size() == p.p_filesz;
        };
        for (const auto& p : elf.progs) if (!validSegment(p))
            throw std::runtime_error("P23 segment bounds invalid");
        // Failure after the first allocation must release that allocation.
        // The second segment deliberately collides with the first 64 KiB page.
        if (!area->falloc(codeAddress, 64)) throw std::runtime_error("P23 initial fixed allocation failed");
        if (area->falloc(codeAddress + 32, 128)) throw std::runtime_error("P23 overlapping allocation accepted");
        if (area->dealloc(0x10000) != 0x10000 || vm::check_addr(0x10000))
            throw std::runtime_error("P23 partial allocation rollback failed");
        if (area->falloc(0x4fff0, 32) || area->falloc(0x8000, 64))
            throw std::runtime_error("P23 allocation outside reserved area accepted");
        ARMSX3StartupLog("P23 PASS: actual fixed allocator rejects overlap and area boundaries; partial allocation rollback");
        for (const auto& p : elf.progs) {
            // Same reserve/flag/falloc operations used by the production loader.
            const u32 address = u32(p.p_vaddr), size = u32(p.p_memsz);
            const auto targetArea = vm::reserve_map(vm::any, 0x10000, 0x10000000, vm::block_size_64k);
            if (targetArea != area || !targetArea->falloc(address, size))
                throw std::runtime_error("P23 loader-style fixed allocation failed");
            const auto* before = static_cast<const u8*>(vm::base(address));
            for (u32 i = 0; i < size; ++i) if (before[i])
                throw std::runtime_error("P23 new segment was not zero-filled");
            std::memcpy(vm::base(address), p.bin.data(), p.bin.size());
        }
        if (vm::check_addr(0x20000) || vm::check_addr(0x40000))
            throw std::runtime_error("P23 unmapped segment gaps became allocated");
        // Verify every byte of both backing pages, including alignment padding,
        // untouched BSS and both guest aliases; do not write either gap page.
        for (u32 page : {0x10000u, 0x30000u}) {
            if (!vm::check_addr(page, vm::page_readable | vm::page_writable, 0x10000))
                throw std::runtime_error("P23 mapped page permissions missing");
            const auto* normal = static_cast<const u8*>(vm::base(page));
            const auto* privileged = static_cast<const u8*>(vm::get_super_ptr(page));
            const u32 offset = page == 0x10000 ? 0 : 0x400;
            const u32 fileOffset = page == 0x10000 ? 0x100 : 0x200;
            for (u32 i = 0; i < 0x10000; ++i) {
                const u8 expected = i >= offset && i < offset + 8 ? fixture[fileOffset + i - offset] : 0;
                if (normal[i] != expected || privileged[i] != expected)
                    throw std::runtime_error("P23 segment payload/BSS/padding/alias mismatch");
            }
        }

        if (vm::page_protect(0x20000, 0x10000, 0, 0, vm::page_writable))
            throw std::runtime_error("P23 protection accepted unmapped gap");
        if (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>())
            throw std::runtime_error("P23 interpreter unavailable");
        auto& interpreter = g_fxo->get<ppu_interpreter_rt>();
        struct SegmentCacheCleanup {
            u8* pointer; bool active = false;
            void release() { if (active) { utils::memory_decommit(pointer, 0x8000); active = false; } }
            ~SegmentCacheCleanup() { release(); }
        } segmentCleanup{vm::g_exec_addr + vm::g_exec_addr_seg_offset + (codeAddress >> 1)};
        segmentCleanup.active = true;
        ppu_register_range(codeAddress, 8);
        const auto* code = static_cast<const be_t<u32>*>(vm::base(codeAddress));
        for (u32 i = 0; i < 2; ++i) ppu_register_function_at(codeAddress + i * 4, 4, interpreter.decode(code[i]));
        // Same loader operation: clear guest write permission. 64 KiB backing
        // pages expand the aligned 4 KiB request to the whole allocation.
        ARMSX3StartupLog("P23 BEFORE core page protection of fixed executable segment");
        if (!vm::page_protect(codeAddress, 0x1000, 0, 0, vm::page_writable) ||
            !vm::check_addr(codeAddress, vm::page_readable | vm::page_executable, 0x10000))
            throw std::runtime_error("P23 read-only executable protection failed");
        for (u32 page = 0; page < 0x10000; page += 0x1000)
            if (vm::check_addr(codeAddress + page, vm::page_writable))
                throw std::runtime_error("P23 code page still marked writable");
        if (!vm::check_addr(0x30000, vm::page_readable | vm::page_writable, 0x10000))
            throw std::runtime_error("P23 data lost write permission");
        // Exercise reversible permission transitions before returning to RO.
        if (!vm::page_protect(codeAddress, 0x10000, vm::page_readable, vm::page_writable, 0) ||
            !vm::check_addr(codeAddress, vm::page_writable, 0x10000) ||
            !vm::page_protect(codeAddress, 0x10000, vm::page_writable, 0, vm::page_writable))
            throw std::runtime_error("P23 permission restore/reapply failed");
        struct Program { int result = -99; bool tls = false; std::atomic<bool> completed{false}; } program;
        const auto created = cpu_thread::g_threads_created.load(), deleted = cpu_thread::g_threads_deleted.load();
        const u64 live = armsx3_ios_live_cpu_threads();
        {
            std::unique_ptr<named_thread<ppu_thread>> worker;
            {
                struct ConstructionID { u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                const ppu_thread_params params{static_cast<vm::addr_t>(0x31000), 0x8000, 0, {}, 0, 0};
                worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS protected ELF probe", 1000);
            }
            struct StopWorker { named_thread<ppu_thread>& worker;
                ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                    worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); } } stop{*worker};
            const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                program.result = armsx3_ios_ppu_exec_bounded(&context, 0x10000, 0x10008, 8);
                context.state += cpu_flag::exit; program.completed.store(true, std::memory_order_release);
            };
            worker->cmd_list({{ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
            worker->cia = codeAddress; worker->gpr[6] = dataAddress + 32;
            worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            ARMSX3StartupLog("P23 BEFORE normal PPU fetch from read-only code and store to separate data segment");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire)) throw std::runtime_error("P23 execution deadline exceeded");
            (*worker)();
            if (!program.tls || program.result != 2 || worker->gpr[3] != 42 || worker->cia != codeAddress + 8)
                throw std::runtime_error("P23 protected code execution result mismatch");
        }
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 1 ||
            cpu_thread::g_threads_deleted.load() != deleted + 1)
            throw std::runtime_error("P23 worker counters unbalanced");
        for (u32 page : {0x10000u, 0x30000u}) {
            const auto* normal = static_cast<const u8*>(vm::base(page));
            const auto* privileged = static_cast<const u8*>(vm::get_super_ptr(page));
            const u32 offset = page == 0x10000 ? 0 : 0x400;
            const u32 fileOffset = page == 0x10000 ? 0x100 : 0x200;
            for (u32 i = 0; i < 0x10000; ++i) {
                u8 expected = i >= offset && i < offset + 8 ? fixture[fileOffset + i - offset] : 0;
                if (page == 0x30000 && i >= 0x420 && i < 0x424) expected = i == 0x423 ? 42 : 0;
                if (normal[i] != expected || privileged[i] != expected)
                    throw std::runtime_error("P23 protected code, data store or guard mismatch");
            }
        }
        for (u32 page = 0; page < 0x10000; page += 0x1000)
            if (vm::check_addr(codeAddress + page, vm::page_writable))
                throw std::runtime_error("P23 execution changed code write permission");
        if (!vm::check_addr(0x30000, vm::page_writable, 0x10000) ||
            vm::check_addr(0x20000) || vm::check_addr(0x40000))
            throw std::runtime_error("P23 execution changed data/gap permissions");
        ARMSX3StartupLog("P23 PASS: read-only code fetch, two actual PPU instructions and writable data store; permissions/aliases/guards unchanged");
        segmentCleanup.release();
        if (area->dealloc(0x30000) != 0x10000 || area->dealloc(0x10000) != 0x10000 ||
            vm::check_addr(0x10000) || vm::check_addr(0x30000))
            throw std::runtime_error("P23 fixed segment cleanup failed");
        // vm::close requires the VM table to own the only block reference.
        ARMSX3StartupLog("P23 BEFORE releasing block reference and closing guest VM");
        area.reset();
        vm::close(); initialized = false;
        ARMSX3StartupLog("P23 PASS: fixed ELF pages, core read-only protection/restore, normal PPU fetch and data store, aliases, guards and cleanup; full executable loader/firmware/game boot remain untested");
        return 0;
    } catch (const std::exception& error) {
        ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1;
    }
}

extern "C" int armsx3_ios_ppu_prepare_hle_table();
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_elf_hle_table()
{
    ARMSX3StartupLog("P24 BEFORE core ELF reader, segment mapping and PPU execution");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P24 requires stopped emulator");
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
        if (!vm::reserve_map(vm::main, 0x10000, 0x30000))
            throw std::runtime_error("P24 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P24 guest allocation failed");
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
            if (rejected.get_error() != errors[test]) throw std::runtime_error("P24 malformed ELF was not rejected correctly");
        }
        ARMSX3StartupLog("P24 PASS: core ELF reader rejects bad magic/class/endian/machine and truncated data");
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
            throw std::runtime_error("P24 segment mapping bounds guard failed");
        const std::string path = fs::get_cache_dir() + "ARMSX3-P24-diagnostic.elf";
        struct RemoveFixture { std::string path; ~RemoveFixture() { fs::remove_file(path); } } remove{path};
        {
            fs::file file(path, fs::rewrite);
            if (!file || file.write(fixture.data(), fixture.size()) != fixture.size())
                throw std::runtime_error("P24 ELF file write failed");
        }
        const fs::file file(path, fs::read);
        ppu_exec_object elf(file);
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 2 || elf.header.e_entry != dataAddress)
            throw std::runtime_error("P24 on-disk ELF header or segment parse failed");
        for (const auto& segment : elf.progs) if (!validSegment(segment))
            throw std::runtime_error("P24 ELF segment outside diagnostic allocation");
        auto* guest = static_cast<u8*>(vm::base(address)); std::memset(guest, 0xa5, 0x10000);
        for (const auto& segment : elf.progs) {
            auto* target = vm::base(u32(segment.p_vaddr));
            std::memset(target, 0, u64(segment.p_memsz));
            std::memcpy(target, segment.bin.data(), segment.bin.size());
        }
        const auto* opd = static_cast<const be_t<u32>*>(vm::base(u32(elf.header.e_entry)));
        if (opd[0] != codeAddress || opd[1] != dataAddress)
            throw std::runtime_error("P24 loaded entry descriptor mismatch");
        for (u32 i = 8; i < 64; ++i) if (guest[0x400 + i] != 0)
            throw std::runtime_error("P24 data segment BSS was not zero-filled");
        // Use the core-owned decoder and the loader's real registration routines.
        // Retain the fixed object until the core resets its object table on next boot.
        if (!g_fxo->is_init()) throw std::runtime_error("P24 fixed object table unavailable");
        if (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>())
            throw std::runtime_error("P24 core interpreter initialization failed");
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
        ARMSX3StartupLog("P24 BEFORE actual executable analysis from loaded ELF segments and OPD");
        if (!module.analyse(0, dataAddress, codeAddress + 56, {}, {}, [&] {
                return std::chrono::steady_clock::now() >= analysisDeadline; }))
            throw std::runtime_error("P24 core executable analysis failed or timed out");
        if (module.funcs.empty()) throw std::runtime_error("P24 analysis found no functions");
        bool entryFound = false;
        for (const auto& function : module.funcs) {
            if (function.addr == codeAddress) entryFound = true;
            if (function.addr < codeAddress || function.addr >= codeAddress + 56 ||
                function.addr % 4 || function.size > codeAddress + 56 - function.addr)
                throw std::runtime_error("P24 analysed function outside loaded executable");
            for (const auto& block : function.blocks)
                if (block.first < codeAddress || block.first >= codeAddress + 56 || block.first % 4 ||
                    block.second % 4 || block.second > codeAddress + 56 - block.first)
                    throw std::runtime_error("P24 analysed block outside loaded executable");
        }
        if (!entryFound) throw std::runtime_error("P24 analyser missed entry function");
        segmentCleanup.active = true;
        ppu_register_range(codeAddress, 56);
        if (!vm::check_addr(address, vm::page_executable, 0x10000))
            throw std::runtime_error("P24 executable page flags missing");
        const auto fallback = cache[0].fn;
        const auto* allCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(address) * 2);
        ARMSX3StartupLog("P24 BEFORE production static module initialization of analysed functions");
        if (armsx3_ios_ppu_prepare_module(&module) != 0)
            throw std::runtime_error("P24 static module preparation failed");
        for (u32 i = 0; i < 14; ++i)
            if (!cache[i].fn || cache[i].fn != interpreter.decode(loadedCode[i]) || cache[i].fn == fallback)
                throw std::runtime_error("P24 module initialization did not decode analysed code");
        char analysisMessage[160];
        std::snprintf(analysisMessage, sizeof(analysisMessage), "P24 PASS: actual analyser found %zu functions; static module initialization decoded fourteen instructions", module.funcs.size());
        ARMSX3StartupLog(analysisMessage);
        if (!g_fxo->is_init<ppu_function_manager>() && !g_fxo->init<ppu_function_manager>())
            throw std::runtime_error("P24 function manager initialization failed");
        auto& manager = g_fxo->get<ppu_function_manager>();
        if (manager.addr) throw std::runtime_error("P24 requires unused function manager address");

        struct TableCleanup {
            ppu_function_manager& manager;
            void release() {
                if (!manager.addr) return;
                const u32 address = manager.addr; manager.addr = 0;
                utils::memory_decommit(vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1), 0x8000);
            }
            ~TableCleanup() { release(); }
        } tableCleanup{manager};
        ARMSX3StartupLog("P24 BEFORE production HLE descriptor table allocation, registration and read-only protection");
        if (armsx3_ios_ppu_prepare_hle_table() != 0)
            throw std::runtime_error("P24 production HLE table preparation failed");
        const auto& hleFunctions = ppu_function_manager::get();
        const u32 tableAddress = manager.addr, returnAddress = manager.func_addr(1, true);
        if (tableAddress < address + 0x10000 || tableAddress >= address + 0x30000 || tableAddress % 0x10000 ||
            hleFunctions.size() < 2 || hleFunctions.size() > 8192 || returnAddress != tableAddress + 12 ||
            !vm::check_addr(tableAddress, vm::page_readable | vm::page_executable, 0x10000))
            throw std::runtime_error("P24 HLE table allocation or flags mismatch");
        for (u32 offset = 0; offset < 0x10000; offset += 0x1000)
            if (vm::check_addr(tableAddress + offset, vm::page_writable))
                throw std::runtime_error("P24 HLE table is writable");
        const auto* descriptors = static_cast<const be_t<u32>*>(vm::base(tableAddress));
        const auto* hleCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(tableAddress) * 2);
        const auto hleFallback = hleCache[0].fn;
        for (u32 i = 0; i < hleFunctions.size(); ++i) {
            if (!hleFunctions[i] || descriptors[i * 2] != tableAddress + i * 8 + 4 || descriptors[i * 2 + 1] != 0 ||
                hleCache[i * 2].fn != hleFallback || hleCache[i * 2 + 1].fn != hleFunctions[i] ||
                manager.func_addr(i) != tableAddress + i * 8 || manager.func_addr(i, true) != tableAddress + i * 8 + 4)
                throw std::runtime_error("P24 HLE descriptor or dispatch handler mismatch");
        }
        char tableMessage[160];
        std::snprintf(tableMessage, sizeof(tableMessage), "P24 PASS: production HLE table prepared %zu descriptors and handlers with read-only guest pages", hleFunctions.size());
        ARMSX3StartupLog(tableMessage);
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
            ARMSX3StartupLog("P24 BEFORE actual fast_call, guest stack frame and core HLE return handler");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire)) throw std::runtime_error("P24 loaded ELF execution deadline exceeded");
            (*worker)();
            if (!program.tls || program.result != 15 || worker->gpr[5] != 35 || worker->gpr[7] != 35 ||
                worker->gpr[8] != 0x123 || worker->gpr[9] != dataAddress || worker->gpr[2] != 0x13579 || worker->cia != address + 0x900 ||
                worker->lr != address + 0x904 || worker->gpr[1] != initialStack || worker->state & cpu_flag::ret)
                throw std::runtime_error("P24 loaded ELF execution result mismatch");
        }
        for (u32 i = 0; i < 0x10000; ++i) {
            u8 expected = 0xa5;
            if (i >= 0x100 && i < 0x100 + sizeof(opcodes)) expected = fixture[i];
            if (i >= 0x400 && i < 0x440) expected = i < 0x408 ? fixture[0x200 + i - 0x400] : 0;
            if (i >= 0x420 && i < 0x424) expected = i == 0x423 ? 35 : 0;
            const u32 frameOffset = frameAddress - address;
            if (i >= frameOffset && i < frameOffset + 8) expected = u8(u64(initialStack) >> (56 - (i - frameOffset) * 8));
            if (i >= frameOffset + 16 && i < frameOffset + 24) expected = u8(u64(returnAddress) >> (56 - (i - frameOffset - 16) * 8));
            if (guest[i] != expected || static_cast<const u8*>(vm::get_super_ptr(address))[i] != expected)
                throw std::runtime_error("P24 loaded segment, BSS, guest guard or alias mismatch");
        }
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 1 ||
            cpu_thread::g_threads_deleted.load() != deleted + 1)
            throw std::runtime_error("P24 worker counters did not balance");
        for (u32 i = 0; i < 14; ++i)
            if (cache[i].fn != interpreter.decode(loadedCode[i]))
                throw std::runtime_error("P24 executed cache did not contain core decoded handlers");
        for (u32 i = 0; i < 0x10000 / 4; ++i)
            if ((i < 0x100 / 4 || i >= 0x100 / 4 + 14) && allCache[i].fn != fallback)
                throw std::runtime_error("P24 dispatch changed handler outside loaded code");

        // Verify execution did not mutate the complete descriptor page or handlers.
        const auto* tableBytes = static_cast<const u8*>(vm::base(tableAddress));
        const auto* privilegedTable = static_cast<const u8*>(vm::get_super_ptr(tableAddress));
        for (u32 i = 0; i < 0x10000; ++i) {
            u8 expected = 0;
            if (i < hleFunctions.size() * 8 && i % 8 < 4)
                expected = u8((tableAddress + (i / 8) * 8 + 4) >> (24 - (i % 8) * 8));
            if (tableBytes[i] != expected || privilegedTable[i] != expected)
                throw std::runtime_error("P24 HLE table/alias changed during guest call");
        }
        for (u32 i = 0; i < 0x10000 / 4; ++i) {
            const auto expected = i < hleFunctions.size() * 2 && i % 2 ? hleFunctions[i / 2] : hleFallback;
            if (hleCache[i].fn != expected) throw std::runtime_error("P24 HLE dispatch table changed during guest call");
        }
        tableCleanup.release();
        if (vm::dealloc(tableAddress, vm::main) != 0x10000 || vm::check_addr(tableAddress))
            throw std::runtime_error("P24 HLE table deallocation failed");
        segmentCleanup.release();
        if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
            throw std::runtime_error("P24 guest deallocation failed");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P24 PASS: production complete HLE table, analysed ELF fast_call, fourteen guest instructions, stack/LR restore, real table return and cleanup; full executable loader/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}



extern "C" int armsx3_ios_ppu_link_probe_imports(const ppu_module<lv2_obj>*, u32);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_elf_import_linkage()
{
    ARMSX3StartupLog("P25 BEFORE core ELF reader, segment mapping and PPU execution");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P25 requires stopped emulator");
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
        if (!vm::reserve_map(vm::main, 0x10000, 0x30000))
            throw std::runtime_error("P25 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P25 guest allocation failed");
        const u32 codeAddress = address + 0x100, dataAddress = address + 0x400;
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        using namespace ppu_instructions;
        using namespace ppu_instructions::implicts;
        const std::array<u32, 18> opcodes{MFLR(0), STDU(1, 1, -128), STD(0, 1, 16), dform(24, 2, 9, 0),
            dform(14, 3, 0, 42), dform(14, 4, 0, 0xfff9),
            (31u << 26) | (5u << 21) | (3u << 16) | (4u << 11) | (266u << 1),
            dform(36, 5, 6, 0), dform(32, 7, 6, 0), dform(24, 7, 8, 0x100),
            LD(0, 1, 16), ADDI(1, 1, 128), MTLR(0), dform(32, 11, 10, 0), dform(32, 12, 11, 0), MTLR(12), BLR(), 0};
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
        segments[1].p_vaddr = dataAddress; segments[1].p_filesz = 192;
        segments[1].p_memsz = 256; segments[1].p_align = 16;
        std::vector<u8> fixture(0x2c0, 0);
        std::memcpy(fixture.data(), &header, sizeof(header));
        std::memcpy(fixture.data() + sizeof(header), segments.data(), sizeof(segments));
        for (u32 i = 0; i < opcodes.size(); ++i) {
            const be_t<u32> word = opcodes[i]; std::memcpy(fixture.data() + 0x100 + i * 4, &word, 4);
        }
        const std::array<be_t<u32>, 2> descriptor{codeAddress, dataAddress};
        std::memcpy(fixture.data() + 0x200, descriptor.data(), sizeof(descriptor));
        // ppu_prx_module_info: 44 bytes, two function imports, no variables or refs.
        fixture[0x240] = 44; fixture[0x247] = 2;
        const auto writeWord = [&](u32 offset, u32 value) { const be_t<u32> word = value;
            std::memcpy(fixture.data() + offset, &word, 4); };
        writeWord(0x250, dataAddress + 128); writeWord(0x254, dataAddress + 160); writeWord(0x258, dataAddress + 176);
        std::memcpy(fixture.data() + 0x280, "iOSProbe", 9);
        writeWord(0x2a0, 0x49524e31); writeWord(0x2a4, 0x49524e32);
        writeWord(0x2b0, codeAddress); writeWord(0x2b4, codeAddress);

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
            if (rejected.get_error() != errors[test]) throw std::runtime_error("P25 malformed ELF was not rejected correctly");
        }
        ARMSX3StartupLog("P25 PASS: core ELF reader rejects bad magic/class/endian/machine and truncated data");
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
            throw std::runtime_error("P25 segment mapping bounds guard failed");
        const std::string path = fs::get_cache_dir() + "ARMSX3-P25-diagnostic.elf";
        struct RemoveFixture { std::string path; ~RemoveFixture() { fs::remove_file(path); } } remove{path};
        {
            fs::file file(path, fs::rewrite);
            if (!file || file.write(fixture.data(), fixture.size()) != fixture.size())
                throw std::runtime_error("P25 ELF file write failed");
        }
        const fs::file file(path, fs::read);
        ppu_exec_object elf(file);
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 2 || elf.header.e_entry != dataAddress)
            throw std::runtime_error("P25 on-disk ELF header or segment parse failed");
        for (const auto& segment : elf.progs) if (!validSegment(segment))
            throw std::runtime_error("P25 ELF segment outside diagnostic allocation");
        auto* guest = static_cast<u8*>(vm::base(address)); std::memset(guest, 0xa5, 0x10000);
        for (const auto& segment : elf.progs) {
            auto* target = vm::base(u32(segment.p_vaddr));
            std::memset(target, 0, u64(segment.p_memsz));
            std::memcpy(target, segment.bin.data(), segment.bin.size());
        }
        const auto* opd = static_cast<const be_t<u32>*>(vm::base(u32(elf.header.e_entry)));
        if (opd[0] != codeAddress || opd[1] != dataAddress)
            throw std::runtime_error("P25 loaded entry descriptor mismatch");
        for (u32 i = 192; i < 256; ++i) if (guest[0x400 + i] != 0)
            throw std::runtime_error("P25 data segment BSS was not zero-filled");
        // Use the core-owned decoder and the loader's real registration routines.
        // Retain the fixed object until the core resets its object table on next boot.
        if (!g_fxo->is_init()) throw std::runtime_error("P25 fixed object table unavailable");
        if (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>())
            throw std::runtime_error("P25 core interpreter initialization failed");
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
        ARMSX3StartupLog("P25 BEFORE actual executable analysis from loaded ELF segments and OPD");
        if (!module.analyse(0, dataAddress, codeAddress + 68, {}, {}, [&] {
                return std::chrono::steady_clock::now() >= analysisDeadline; }))
            throw std::runtime_error("P25 core executable analysis failed or timed out");
        if (module.funcs.empty()) throw std::runtime_error("P25 analysis found no functions");
        bool entryFound = false;
        for (const auto& function : module.funcs) {
            if (function.addr == codeAddress) entryFound = true;
            if (function.addr < codeAddress || function.addr >= codeAddress + 68 ||
                function.addr % 4 || function.size > codeAddress + 68 - function.addr)
                throw std::runtime_error("P25 analysed function outside loaded executable");
            for (const auto& block : function.blocks)
                if (block.first < codeAddress || block.first >= codeAddress + 68 || block.first % 4 ||
                    block.second % 4 || block.second > codeAddress + 68 - block.first)
                    throw std::runtime_error("P25 analysed block outside loaded executable");
        }
        if (!entryFound) throw std::runtime_error("P25 analyser missed entry function");
        segmentCleanup.active = true;
        ppu_register_range(codeAddress, 68);
        if (!vm::check_addr(address, vm::page_executable, 0x10000))
            throw std::runtime_error("P25 executable page flags missing");
        const auto fallback = cache[0].fn;
        const auto* allCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(address) * 2);
        ARMSX3StartupLog("P25 BEFORE production static module initialization of analysed functions");
        if (armsx3_ios_ppu_prepare_module(&module) != 0)
            throw std::runtime_error("P25 static module preparation failed");
        for (u32 i = 0; i < 17; ++i)
            if (!cache[i].fn || cache[i].fn != interpreter.decode(loadedCode[i]) || cache[i].fn == fallback)
                throw std::runtime_error("P25 module initialization did not decode analysed code");
        char analysisMessage[160];
        std::snprintf(analysisMessage, sizeof(analysisMessage), "P25 PASS: actual analyser found %zu functions; static module initialization decoded seventeen instructions", module.funcs.size());
        ARMSX3StartupLog(analysisMessage);
        if (!g_fxo->is_init<ppu_function_manager>() && !g_fxo->init<ppu_function_manager>())
            throw std::runtime_error("P25 function manager initialization failed");
        auto& manager = g_fxo->get<ppu_function_manager>();
        if (manager.addr) throw std::runtime_error("P25 requires unused function manager address");

        struct TableCleanup {
            ppu_function_manager& manager;
            void release() {
                if (!manager.addr) return;
                const u32 address = manager.addr; manager.addr = 0;
                utils::memory_decommit(vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1), 0x8000);
            }
            ~TableCleanup() { release(); }
        } tableCleanup{manager};
        ARMSX3StartupLog("P25 BEFORE production HLE descriptor table allocation, registration and read-only protection");
        if (armsx3_ios_ppu_prepare_hle_table() != 0)
            throw std::runtime_error("P25 production HLE table preparation failed");
        const auto& hleFunctions = ppu_function_manager::get();
        const u32 tableAddress = manager.addr, returnAddress = manager.func_addr(1, true);
        if (tableAddress < address + 0x10000 || tableAddress >= address + 0x30000 || tableAddress % 0x10000 ||
            hleFunctions.size() < 2 || hleFunctions.size() > 8192 || returnAddress != tableAddress + 12 ||
            !vm::check_addr(tableAddress, vm::page_readable | vm::page_executable, 0x10000))
            throw std::runtime_error("P25 HLE table allocation or flags mismatch");
        for (u32 offset = 0; offset < 0x10000; offset += 0x1000)
            if (vm::check_addr(tableAddress + offset, vm::page_writable))
                throw std::runtime_error("P25 HLE table is writable");
        const auto* descriptors = static_cast<const be_t<u32>*>(vm::base(tableAddress));
        const auto* hleCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(tableAddress) * 2);
        const auto hleFallback = hleCache[0].fn;
        for (u32 i = 0; i < hleFunctions.size(); ++i) {
            if (!hleFunctions[i] || descriptors[i * 2] != tableAddress + i * 8 + 4 || descriptors[i * 2 + 1] != 0 ||
                hleCache[i * 2].fn != hleFallback || hleCache[i * 2 + 1].fn != hleFunctions[i] ||
                manager.func_addr(i) != tableAddress + i * 8 || manager.func_addr(i, true) != tableAddress + i * 8 + 4)
                throw std::runtime_error("P25 HLE descriptor or dispatch handler mismatch");
        }
        char tableMessage[160];
        std::snprintf(tableMessage, sizeof(tableMessage), "P25 PASS: production HLE table prepared %zu descriptors and handlers with read-only guest pages", hleFunctions.size());
        ARMSX3StartupLog(tableMessage);

        ARMSX3StartupLog("P25 BEFORE actual loader import linking for known and unresolved function IDs");
        if (armsx3_ios_ppu_link_probe_imports(&module, dataAddress + 64) != 0 ||
            vm::read32(dataAddress + 176) != manager.func_addr(1) || vm::read32(dataAddress + 180) != tableAddress ||
            vm::read32(vm::read32(dataAddress + 176)) != returnAddress)
            throw std::runtime_error("P25 production import linkage failed");
        ARMSX3StartupLog("P25 PASS: known import resolves to HLE RETURN descriptor; unresolved import resolves to INVALID descriptor");
        const u32 initialStack = address + 0x8000, frameAddress = initialStack - 128;
        struct Program { u32 begin, end, returnAddress; u64 toc; int result = -99; bool tls = false;
            std::atomic<bool> completed{false}; } program{u32(opd[0]), codeAddress + 68, returnAddress, u64(opd[1])};
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
            worker->gpr[10] = dataAddress + 176;
            worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            ARMSX3StartupLog("P25 BEFORE guest reads linked import descriptor and branches through production HLE return");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire)) throw std::runtime_error("P25 loaded ELF execution deadline exceeded");
            (*worker)();
            if (!program.tls || program.result != 18 || worker->gpr[5] != 35 || worker->gpr[7] != 35 ||
                worker->gpr[11] != manager.func_addr(1) || worker->gpr[12] != returnAddress || worker->gpr[8] != 0x123 || worker->gpr[9] != dataAddress || worker->gpr[2] != 0x13579 || worker->cia != address + 0x900 ||
                worker->lr != address + 0x904 || worker->gpr[1] != initialStack || worker->state & cpu_flag::ret)
                throw std::runtime_error("P25 loaded ELF execution result mismatch");
        }
        for (u32 i = 0; i < 0x10000; ++i) {
            u8 expected = 0xa5;
            if (i >= 0x100 && i < 0x100 + sizeof(opcodes)) expected = fixture[i];
            if (i >= 0x400 && i < 0x500) expected = i < 0x4c0 ? fixture[0x200 + i - 0x400] : 0;
            if (i >= 0x4b0 && i < 0x4b4) expected = u8(manager.func_addr(1) >> (24 - (i - 0x4b0) * 8));
            if (i >= 0x4b4 && i < 0x4b8) expected = u8(tableAddress >> (24 - (i - 0x4b4) * 8));
            if (i >= 0x420 && i < 0x424) expected = i == 0x423 ? 35 : 0;
            const u32 frameOffset = frameAddress - address;
            if (i >= frameOffset && i < frameOffset + 8) expected = u8(u64(initialStack) >> (56 - (i - frameOffset) * 8));
            if (i >= frameOffset + 16 && i < frameOffset + 24) expected = u8(u64(returnAddress) >> (56 - (i - frameOffset - 16) * 8));
            if (guest[i] != expected || static_cast<const u8*>(vm::get_super_ptr(address))[i] != expected)
                throw std::runtime_error("P25 loaded segment, BSS, guest guard or alias mismatch");
        }
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 1 ||
            cpu_thread::g_threads_deleted.load() != deleted + 1)
            throw std::runtime_error("P25 worker counters did not balance");
        for (u32 i = 0; i < 17; ++i)
            if (cache[i].fn != interpreter.decode(loadedCode[i]))
                throw std::runtime_error("P25 executed cache did not contain core decoded handlers");
        for (u32 i = 0; i < 0x10000 / 4; ++i)
            if ((i < 0x100 / 4 || i >= 0x100 / 4 + 17) && allCache[i].fn != fallback)
                throw std::runtime_error("P25 dispatch changed handler outside loaded code");

        // Verify execution did not mutate the complete descriptor page or handlers.
        const auto* tableBytes = static_cast<const u8*>(vm::base(tableAddress));
        const auto* privilegedTable = static_cast<const u8*>(vm::get_super_ptr(tableAddress));
        for (u32 i = 0; i < 0x10000; ++i) {
            u8 expected = 0;
            if (i < hleFunctions.size() * 8 && i % 8 < 4)
                expected = u8((tableAddress + (i / 8) * 8 + 4) >> (24 - (i % 8) * 8));
            if (tableBytes[i] != expected || privilegedTable[i] != expected)
                throw std::runtime_error("P25 HLE table/alias changed during guest call");
        }
        for (u32 i = 0; i < 0x10000 / 4; ++i) {
            const auto expected = i < hleFunctions.size() * 2 && i % 2 ? hleFunctions[i / 2] : hleFallback;
            if (hleCache[i].fn != expected) throw std::runtime_error("P25 HLE dispatch table changed during guest call");
        }
        tableCleanup.release();
        if (vm::dealloc(tableAddress, vm::main) != 0x10000 || vm::check_addr(tableAddress))
            throw std::runtime_error("P25 HLE table deallocation failed");
        segmentCleanup.release();
        if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
            throw std::runtime_error("P25 guest deallocation failed");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P25 PASS: production import linker, known/unresolved NIDs, seventeen guest instructions, descriptor fetch/branch to HLE table and cleanup; full executable loader/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}

extern "C" int armsx3_ios_ppu_observe_probe_exports(const ppu_module<lv2_obj>*, u32);
extern "C" int armsx3_ios_ppu_link_probe_imports(const ppu_module<lv2_obj>*, u32);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_elf_export_discovery()
{
    ARMSX3StartupLog("P26 BEFORE core ELF reader, segment mapping and PPU execution");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P26 requires stopped emulator");
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
        if (!vm::reserve_map(vm::main, 0x10000, 0x30000))
            throw std::runtime_error("P26 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P26 guest allocation failed");
        const u32 codeAddress = address + 0x100, dataAddress = address + 0x400;
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        using namespace ppu_instructions;
        using namespace ppu_instructions::implicts;
        const std::array<u32, 18> opcodes{MFLR(0), STDU(1, 1, -128), STD(0, 1, 16), dform(24, 2, 9, 0),
            dform(14, 3, 0, 42), dform(14, 4, 0, 0xfff9),
            (31u << 26) | (5u << 21) | (3u << 16) | (4u << 11) | (266u << 1),
            dform(36, 5, 6, 0), dform(32, 7, 6, 0), dform(24, 7, 8, 0x100),
            LD(0, 1, 16), ADDI(1, 1, 128), MTLR(0), dform(32, 11, 10, 0), dform(32, 12, 11, 0), MTLR(12), BLR(), 0};
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
        segments[1].p_vaddr = dataAddress; segments[1].p_filesz = 192;
        segments[1].p_memsz = 256; segments[1].p_align = 16;
        std::vector<u8> fixture(0x2c0, 0);
        std::memcpy(fixture.data(), &header, sizeof(header));
        std::memcpy(fixture.data() + sizeof(header), segments.data(), sizeof(segments));
        for (u32 i = 0; i < opcodes.size(); ++i) {
            const be_t<u32> word = opcodes[i]; std::memcpy(fixture.data() + 0x100 + i * 4, &word, 4);
        }
        const std::array<be_t<u32>, 2> descriptor{codeAddress, dataAddress};
        std::memcpy(fixture.data() + 0x200, descriptor.data(), sizeof(descriptor));
        // ppu_prx_module_info: 44 bytes, two function imports, no variables or refs.
        fixture[0x240] = 44; fixture[0x247] = 2;
        const auto writeWord = [&](u32 offset, u32 value) { const be_t<u32> word = value;
            std::memcpy(fixture.data() + offset, &word, 4); };
        writeWord(0x250, dataAddress + 128); writeWord(0x254, dataAddress + 160); writeWord(0x258, dataAddress + 176);
        std::memcpy(fixture.data() + 0x280, "iOSProbe", 9);
        writeWord(0x2a0, 0x49524e31); writeWord(0x2a4, 0x49524e32);
        writeWord(0x2b0, codeAddress); writeWord(0x2b4, codeAddress);

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
            if (rejected.get_error() != errors[test]) throw std::runtime_error("P26 malformed ELF was not rejected correctly");
        }
        ARMSX3StartupLog("P26 PASS: core ELF reader rejects bad magic/class/endian/machine and truncated data");
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
            throw std::runtime_error("P26 segment mapping bounds guard failed");
        const std::string path = fs::get_cache_dir() + "ARMSX3-P26-diagnostic.elf";
        struct RemoveFixture { std::string path; ~RemoveFixture() { fs::remove_file(path); } } remove{path};
        {
            fs::file file(path, fs::rewrite);
            if (!file || file.write(fixture.data(), fixture.size()) != fixture.size())
                throw std::runtime_error("P26 ELF file write failed");
        }
        const fs::file file(path, fs::read);
        ppu_exec_object elf(file);
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 2 || elf.header.e_entry != dataAddress)
            throw std::runtime_error("P26 on-disk ELF header or segment parse failed");
        for (const auto& segment : elf.progs) if (!validSegment(segment))
            throw std::runtime_error("P26 ELF segment outside diagnostic allocation");
        auto* guest = static_cast<u8*>(vm::base(address)); std::memset(guest, 0xa5, 0x10000);
        for (const auto& segment : elf.progs) {
            auto* target = vm::base(u32(segment.p_vaddr));
            std::memset(target, 0, u64(segment.p_memsz));
            std::memcpy(target, segment.bin.data(), segment.bin.size());
        }
        const auto* opd = static_cast<const be_t<u32>*>(vm::base(u32(elf.header.e_entry)));
        if (opd[0] != codeAddress || opd[1] != dataAddress)
            throw std::runtime_error("P26 loaded entry descriptor mismatch");
        for (u32 i = 192; i < 256; ++i) if (guest[0x400 + i] != 0)
            throw std::runtime_error("P26 data segment BSS was not zero-filled");
        // Use the core-owned decoder and the loader's real registration routines.
        // Retain the fixed object until the core resets its object table on next boot.
        if (!g_fxo->is_init()) throw std::runtime_error("P26 fixed object table unavailable");
        if (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>())
            throw std::runtime_error("P26 core interpreter initialization failed");
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
        ARMSX3StartupLog("P26 BEFORE actual executable analysis from loaded ELF segments and OPD");
        if (!module.analyse(0, dataAddress, codeAddress + 68, {}, {}, [&] {
                return std::chrono::steady_clock::now() >= analysisDeadline; }))
            throw std::runtime_error("P26 core executable analysis failed or timed out");
        if (module.funcs.empty()) throw std::runtime_error("P26 analysis found no functions");
        bool entryFound = false;
        for (const auto& function : module.funcs) {
            if (function.addr == codeAddress) entryFound = true;
            if (function.addr < codeAddress || function.addr >= codeAddress + 68 ||
                function.addr % 4 || function.size > codeAddress + 68 - function.addr)
                throw std::runtime_error("P26 analysed function outside loaded executable");
            for (const auto& block : function.blocks)
                if (block.first < codeAddress || block.first >= codeAddress + 68 || block.first % 4 ||
                    block.second % 4 || block.second > codeAddress + 68 - block.first)
                    throw std::runtime_error("P26 analysed block outside loaded executable");
        }
        if (!entryFound) throw std::runtime_error("P26 analyser missed entry function");
        segmentCleanup.active = true;
        ppu_register_range(codeAddress, 68);
        if (!vm::check_addr(address, vm::page_executable, 0x10000))
            throw std::runtime_error("P26 executable page flags missing");
        const auto fallback = cache[0].fn;
        const auto* allCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(address) * 2);
        ARMSX3StartupLog("P26 BEFORE production static module initialization of analysed functions");
        if (armsx3_ios_ppu_prepare_module(&module) != 0)
            throw std::runtime_error("P26 static module preparation failed");
        for (u32 i = 0; i < 17; ++i)
            if (!cache[i].fn || cache[i].fn != interpreter.decode(loadedCode[i]) || cache[i].fn == fallback)
                throw std::runtime_error("P26 module initialization did not decode analysed code");
        char analysisMessage[160];
        std::snprintf(analysisMessage, sizeof(analysisMessage), "P26 PASS: actual analyser found %zu functions; static module initialization decoded seventeen instructions", module.funcs.size());
        ARMSX3StartupLog(analysisMessage);
        if (!g_fxo->is_init<ppu_function_manager>() && !g_fxo->init<ppu_function_manager>())
            throw std::runtime_error("P26 function manager initialization failed");
        auto& manager = g_fxo->get<ppu_function_manager>();
        if (manager.addr) throw std::runtime_error("P26 requires unused function manager address");

        struct TableCleanup {
            ppu_function_manager& manager;
            void release() {
                if (!manager.addr) return;
                const u32 address = manager.addr; manager.addr = 0;
                utils::memory_decommit(vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1), 0x8000);
            }
            ~TableCleanup() { release(); }
        } tableCleanup{manager};
        ARMSX3StartupLog("P26 BEFORE production HLE descriptor table allocation, registration and read-only protection");
        if (armsx3_ios_ppu_prepare_hle_table() != 0)
            throw std::runtime_error("P26 production HLE table preparation failed");
        const auto& hleFunctions = ppu_function_manager::get();
        const u32 tableAddress = manager.addr, returnAddress = manager.func_addr(1, true);
        if (tableAddress < address + 0x10000 || tableAddress >= address + 0x30000 || tableAddress % 0x10000 ||
            hleFunctions.size() < 2 || hleFunctions.size() > 8192 || returnAddress != tableAddress + 12 ||
            !vm::check_addr(tableAddress, vm::page_readable | vm::page_executable, 0x10000))
            throw std::runtime_error("P26 HLE table allocation or flags mismatch");
        for (u32 offset = 0; offset < 0x10000; offset += 0x1000)
            if (vm::check_addr(tableAddress + offset, vm::page_writable))
                throw std::runtime_error("P26 HLE table is writable");
        const auto* descriptors = static_cast<const be_t<u32>*>(vm::base(tableAddress));
        const auto* hleCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(tableAddress) * 2);
        const auto hleFallback = hleCache[0].fn;
        for (u32 i = 0; i < hleFunctions.size(); ++i) {
            if (!hleFunctions[i] || descriptors[i * 2] != tableAddress + i * 8 + 4 || descriptors[i * 2 + 1] != 0 ||
                hleCache[i * 2].fn != hleFallback || hleCache[i * 2 + 1].fn != hleFunctions[i] ||
                manager.func_addr(i) != tableAddress + i * 8 || manager.func_addr(i, true) != tableAddress + i * 8 + 4)
                throw std::runtime_error("P26 HLE descriptor or dispatch handler mismatch");
        }
        char tableMessage[160];
        std::snprintf(tableMessage, sizeof(tableMessage), "P26 PASS: production HLE table prepared %zu descriptors and handlers with read-only guest pages", hleFunctions.size());
        ARMSX3StartupLog(tableMessage);

        ARMSX3StartupLog("P26 BEFORE actual loader import linking for known and unresolved function IDs");
        if (armsx3_ios_ppu_link_probe_imports(&module, dataAddress + 64) != 0 ||
            vm::read32(dataAddress + 176) != manager.func_addr(1) || vm::read32(dataAddress + 180) != tableAddress ||
            vm::read32(vm::read32(dataAddress + 176)) != returnAddress)
            throw std::runtime_error("P26 production import linkage failed");
        ARMSX3StartupLog("P26 PASS: known import resolves to HLE RETURN descriptor; unresolved import resolves to INVALID descriptor");
        const u32 initialStack = address + 0x8000, frameAddress = initialStack - 128;
        struct Program { u32 begin, end, returnAddress; u64 toc; int result = -99; bool tls = false;
            std::atomic<bool> completed{false}; } program{u32(opd[0]), codeAddress + 68, returnAddress, u64(opd[1])};
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
            worker->gpr[10] = dataAddress + 176;
            worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            ARMSX3StartupLog("P26 BEFORE guest reads linked import descriptor and branches through production HLE return");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire)) throw std::runtime_error("P26 loaded ELF execution deadline exceeded");
            (*worker)();
            if (!program.tls || program.result != 18 || worker->gpr[5] != 35 || worker->gpr[7] != 35 ||
                worker->gpr[11] != manager.func_addr(1) || worker->gpr[12] != returnAddress || worker->gpr[8] != 0x123 || worker->gpr[9] != dataAddress || worker->gpr[2] != 0x13579 || worker->cia != address + 0x900 ||
                worker->lr != address + 0x904 || worker->gpr[1] != initialStack || worker->state & cpu_flag::ret)
                throw std::runtime_error("P26 loaded ELF execution result mismatch");
        }
        for (u32 i = 0; i < 0x10000; ++i) {
            u8 expected = 0xa5;
            if (i >= 0x100 && i < 0x100 + sizeof(opcodes)) expected = fixture[i];
            if (i >= 0x400 && i < 0x500) expected = i < 0x4c0 ? fixture[0x200 + i - 0x400] : 0;
            if (i >= 0x4b0 && i < 0x4b4) expected = u8(manager.func_addr(1) >> (24 - (i - 0x4b0) * 8));
            if (i >= 0x4b4 && i < 0x4b8) expected = u8(tableAddress >> (24 - (i - 0x4b4) * 8));
            if (i >= 0x420 && i < 0x424) expected = i == 0x423 ? 35 : 0;
            const u32 frameOffset = frameAddress - address;
            if (i >= frameOffset && i < frameOffset + 8) expected = u8(u64(initialStack) >> (56 - (i - frameOffset) * 8));
            if (i >= frameOffset + 16 && i < frameOffset + 24) expected = u8(u64(returnAddress) >> (56 - (i - frameOffset - 16) * 8));
            if (guest[i] != expected || static_cast<const u8*>(vm::get_super_ptr(address))[i] != expected)
                throw std::runtime_error("P26 loaded segment, BSS, guest guard or alias mismatch");
        }
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 1 ||
            cpu_thread::g_threads_deleted.load() != deleted + 1)
            throw std::runtime_error("P26 worker counters did not balance");
        for (u32 i = 0; i < 17; ++i)
            if (cache[i].fn != interpreter.decode(loadedCode[i]))
                throw std::runtime_error("P26 executed cache did not contain core decoded handlers");
        for (u32 i = 0; i < 0x10000 / 4; ++i)
            if ((i < 0x100 / 4 || i >= 0x100 / 4 + 17) && allCache[i].fn != fallback)
                throw std::runtime_error("P26 dispatch changed handler outside loaded code");

        // Verify execution did not mutate the complete descriptor page or handlers.
        const auto* tableBytes = static_cast<const u8*>(vm::base(tableAddress));
        const auto* privilegedTable = static_cast<const u8*>(vm::get_super_ptr(tableAddress));
        for (u32 i = 0; i < 0x10000; ++i) {
            u8 expected = 0;
            if (i < hleFunctions.size() * 8 && i % 8 < 4)
                expected = u8((tableAddress + (i / 8) * 8 + 4) >> (24 - (i % 8) * 8));
            if (tableBytes[i] != expected || privilegedTable[i] != expected)
                throw std::runtime_error("P26 HLE table/alias changed during guest call");
        }
        for (u32 i = 0; i < 0x10000 / 4; ++i) {
            const auto expected = i < hleFunctions.size() * 2 && i % 2 ? hleFunctions[i / 2] : hleFallback;
            if (hleCache[i].fn != expected) throw std::runtime_error("P26 HLE dispatch table changed during guest call");
        }
        // An additional PRX export record occupies only the P25 fixture's
        // already-allocated 64-byte BSS tail. Test real export discovery after
        // completing all import/guest execution memory and alias assertions.
        ARMSX3StartupLog("P26 BEFORE production PRX export observation");
        u8* exportRecord = static_cast<u8*>(vm::base(dataAddress + 192));
        std::memset(exportRecord, 0, 64);
        exportRecord[0] = 44; // sizeof(ppu_prx_module_info)
        exportRecord[5] = 1;  // PRX_EXPORT_LIBRARY_FLAG, BE u16
        exportRecord[7] = 1;  // num_func = 1, BE u16
        const auto writeExportWord = [&](u32 offset, u32 value) {
            const be_t<u32> word = value;
            std::memcpy(exportRecord + offset, &word, sizeof(word));
        };
        writeExportWord(16, dataAddress + 128); // existing NUL-terminated iOSProbe name
        writeExportWord(20, dataAddress + 160); // known function NID
        writeExportWord(24, dataAddress + 236); // export address table in BSS tail
        writeExportWord(44, dataAddress);       // real OPD (entry + TOC)
        const int exportResult = armsx3_ios_ppu_observe_probe_exports(&module, dataAddress + 192);
        if (exportResult != 0) {
            char error[160];
            std::snprintf(error, sizeof(error), "P26 production export observation failed (wrapper result %d)", exportResult);
            throw std::runtime_error(error);
        }
        if (armsx3_ios_ppu_observe_probe_exports(&module, dataAddress + 188) != -1)
            throw std::runtime_error("P26 production export wrapper accepted invalid record start");
        ARMSX3StartupLog("P26 PASS: production PRX export scan found guest entry descriptor and function NID; no global exports registered");
        tableCleanup.release();
        if (vm::dealloc(tableAddress, vm::main) != 0x10000 || vm::check_addr(tableAddress))
            throw std::runtime_error("P26 HLE table deallocation failed");
        segmentCleanup.release();
        if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
            throw std::runtime_error("P26 guest deallocation failed");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P26 PASS: production import/HLE call and bounded PRX export discovery; original guest execution, memory/table guards and cleanup passed; full executable loader/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}

extern "C" int armsx3_ios_ppu_register_probe_exports(const ppu_module<lv2_obj>*, u32);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_elf_export_registration()
{
    ARMSX3StartupLog("P27 BEFORE production PRX export registration and deferred import backpatch");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P27 requires stopped emulator");
        struct Configuration {
            ppu_decoder_type decoder = g_cfg.core.ppu_decoder.get();
            Configuration() { g_cfg.core.ppu_decoder.set(ppu_decoder_type::_static); }
            ~Configuration() { g_cfg.core.ppu_decoder.set(decoder); }
        } configuration;
        if (!g_fxo->is_init() ||
            (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>()))
            throw std::runtime_error("P27 fixed objects/interpreter unavailable");
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x30000))
            throw std::runtime_error("P27 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P27 guest allocation failed");
        const u32 codeAddress = address + 0x100, dataAddress = address + 0x400;
        auto* guest = static_cast<u8*>(vm::base(address));
        std::memset(guest, 0xa5, 0x10000);
        std::memset(vm::base(dataAddress), 0, 256);
        vm::write32(codeAddress, 0x4e800020); // BLR: a valid exported entry, not executed by P27.
        vm::write32(dataAddress, codeAddress); vm::write32(dataAddress + 4, dataAddress);
        auto* data = static_cast<u8*>(vm::base(dataAddress));
        data[64] = 44; data[71] = 2;
        vm::write32(dataAddress + 80, dataAddress + 128);
        vm::write32(dataAddress + 84, dataAddress + 160);
        vm::write32(dataAddress + 88, dataAddress + 176);
        std::memcpy(data + 128, "iOSProbe", 9);
        vm::write32(dataAddress + 160, 0x49524e31); vm::write32(dataAddress + 164, 0x49524e32);
        vm::write32(dataAddress + 176, codeAddress); vm::write32(dataAddress + 180, codeAddress);
        data[192] = 44; data[197] = 1; data[199] = 1;
        vm::write32(dataAddress + 208, dataAddress + 128);
        vm::write32(dataAddress + 212, dataAddress + 160);
        vm::write32(dataAddress + 216, dataAddress + 236);
        vm::write32(dataAddress + 236, dataAddress);
        ppu_module<lv2_obj> module;
        module.name = "iOS PRX registration probe";
        module.addr_to_seg_index.emplace(codeAddress, 0);
        module.addr_to_seg_index.emplace(dataAddress, 1);
        module.segs.push_back({codeAddress, 4, 1, 5, 4, vm::base(codeAddress)});
        module.segs.push_back({dataAddress, 256, 1, 6, 256, vm::base(dataAddress)});
        const std::vector<u8> before(guest, guest + 0x10000);
        if (!g_fxo->is_init<ppu_function_manager>() && !g_fxo->init<ppu_function_manager>())
            throw std::runtime_error("P27 function manager initialization failed");
        auto& manager = g_fxo->get<ppu_function_manager>();
        if (manager.addr) throw std::runtime_error("P27 requires unused function manager address");
        struct TableCleanup {
            ppu_function_manager& manager;
            void release() {
                if (!manager.addr) return;
                const u32 address = manager.addr; manager.addr = 0;
                utils::memory_decommit(vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1), 0x8000);
            }
            ~TableCleanup() { release(); }
        } tableCleanup{manager};
        if (armsx3_ios_ppu_prepare_hle_table() != 0)
            throw std::runtime_error("P27 production HLE table preparation failed");
        const u32 tableAddress = manager.addr;
        if (tableAddress < address + 0x10000 || tableAddress >= address + 0x30000 || tableAddress % 0x10000 ||
            !vm::check_addr(tableAddress, vm::page_readable | vm::page_executable, 0x10000))
            throw std::runtime_error("P27 HLE table allocation or flags mismatch");
        const auto* table = static_cast<const u8*>(vm::base(tableAddress));
        const std::vector<u8> tableBefore(table, table + 0x10000);
        const auto* cache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(tableAddress) * 2);
        std::vector<ppu_intrp_func_t> handlers;
        for (u32 i = 0; i < 0x10000 / 4; ++i) handlers.push_back(cache[i].fn);
        const auto created = cpu_thread::g_threads_created.load(), deleted = cpu_thread::g_threads_deleted.load();
        const u64 live = armsx3_ios_live_cpu_threads();
        for (unsigned repeat = 0; repeat < 2; ++repeat) {
            const int result = armsx3_ios_ppu_register_probe_exports(&module, dataAddress + 192);
            if (result != 0) {
                char error[160];
                std::snprintf(error, sizeof(error), "P27 production export registration failed (wrapper result %d, iteration %u)", result, repeat + 1);
                throw std::runtime_error(error);
            }
            if (std::memcmp(guest, before.data(), before.size()) ||
                std::memcmp(vm::get_super_ptr(address), before.data(), before.size()))
                throw std::runtime_error("P27 import restoration, guest guard or alias mismatch");
        }
        if (armsx3_ios_ppu_register_probe_exports(&module, dataAddress + 188) != -1)
            throw std::runtime_error("P27 export registration accepted invalid record start");
        if (std::memcmp(table, tableBefore.data(), tableBefore.size()) ||
            std::memcmp(vm::get_super_ptr(tableAddress), tableBefore.data(), tableBefore.size()))
            throw std::runtime_error("P27 registration mutated HLE descriptors/aliases");
        for (u32 i = 0; i < handlers.size(); ++i)
            if (cache[i].fn != handlers[i]) throw std::runtime_error("P27 registration mutated HLE dispatch");
        for (u32 offset = 0; offset < 0x10000; offset += 0x1000)
            if (vm::check_addr(tableAddress + offset, vm::page_writable))
                throw std::runtime_error("P27 HLE descriptor page became writable");
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created ||
            cpu_thread::g_threads_deleted.load() != deleted)
            throw std::runtime_error("P27 registration changed CPU thread counters");
        tableCleanup.release();
        if (vm::dealloc(tableAddress, vm::main) != 0x10000 || vm::check_addr(tableAddress))
            throw std::runtime_error("P27 HLE table deallocation failed");
        if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
            throw std::runtime_error("P27 guest deallocation failed");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P27 PASS: production export registration, deferred known import backpatch, unresolved INVALID import, library unload and repeated cleanup; guest-to-guest calls/full executable loader/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}

extern "C" int armsx3_ios_ppu_register_probe_exports_and_call(const ppu_module<lv2_obj>*, u32, int (*)(void*, u32, u32), void*);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_linked_guest_call()
{
    ARMSX3StartupLog("P28 BEFORE linked guest-to-guest call and return");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P28 requires stopped emulator");
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
        if (!g_fxo->is_init() ||
            (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>()))
            throw std::runtime_error("P28 fixed objects/interpreter unavailable");
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x30000))
            throw std::runtime_error("P28 main memory block unavailable");
        const u32 address = vm::alloc(0x10000, vm::main, 0x10000);
        if (!address) throw std::runtime_error("P28 guest allocation failed");
        const u32 codeAddress = address + 0x100, dataAddress = address + 0x400;
        auto* guest = static_cast<u8*>(vm::base(address));
        std::memset(guest, 0xa5, 0x10000);
        std::memset(vm::base(dataAddress), 0, 256);
        using namespace ppu_instructions;
        using namespace ppu_instructions::implicts;
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        std::array<u32, 27> opcodes; opcodes.fill(0x60000000); // padding NOPs
        const std::array<u32, 17> caller{MFLR(0), STDU(1, 1, -128), STD(0, 1, 16), STD(2, 1, 24),
            ADDI(3, 0, 35), dform(32, 11, 10, 0), dform(32, 12, 11, 0), dform(32, 2, 11, 4),
            MTCTR(12), BCTRL(), LD(2, 1, 24), dform(24, 2, 9, 0), STD(3, 6, 0),
            LD(0, 1, 16), ADDI(1, 1, 128), MTLR(0), BLR()};
        for (u32 i = 0; i < caller.size(); ++i) opcodes[i] = caller[i];
        opcodes[24] = ADDI(3, 3, 7); opcodes[25] = dform(24, 2, 8, 0); opcodes[26] = BLR();
        for (u32 i = 0; i < opcodes.size(); ++i) vm::write32(codeAddress + i * 4, opcodes[i]);
        vm::write32(dataAddress, codeAddress + 96); vm::write32(dataAddress + 4, dataAddress);
        auto* data = static_cast<u8*>(vm::base(dataAddress));
        data[64] = 44; data[71] = 2;
        vm::write32(dataAddress + 80, dataAddress + 128);
        vm::write32(dataAddress + 84, dataAddress + 160);
        vm::write32(dataAddress + 88, dataAddress + 176);
        std::memcpy(data + 128, "iOSProbe", 9);
        vm::write32(dataAddress + 160, 0x49524e31); vm::write32(dataAddress + 164, 0x49524e32);
        vm::write32(dataAddress + 176, codeAddress); vm::write32(dataAddress + 180, codeAddress);
        data[192] = 44; data[197] = 1; data[199] = 1;
        vm::write32(dataAddress + 208, dataAddress + 128);
        vm::write32(dataAddress + 212, dataAddress + 160);
        vm::write32(dataAddress + 216, dataAddress + 236);
        vm::write32(dataAddress + 236, dataAddress);
        ppu_module<lv2_obj> module;
        module.name = "iOS linked guest call probe";
        module.addr_to_seg_index.emplace(codeAddress, 0);
        module.addr_to_seg_index.emplace(dataAddress, 1);
        module.segs.push_back({codeAddress, u32(sizeof(opcodes)), 1, 5, u32(sizeof(opcodes)), vm::base(codeAddress)});
        module.segs.push_back({dataAddress, 256, 1, 6, 256, vm::base(dataAddress)});
        // Declare the exact synthetic caller/callee blocks, then use the normal
        // production static-module decoder. Complete ELF loading is still pending.
        ppu_function callerFunction{};
        callerFunction.addr = codeAddress; callerFunction.toc = dataAddress + 32; callerFunction.size = 68;
        callerFunction.blocks.emplace(codeAddress, 68);
        ppu_function calleeFunction{};
        calleeFunction.addr = codeAddress + 96; calleeFunction.toc = dataAddress; calleeFunction.size = 12;
        calleeFunction.blocks.emplace(codeAddress + 96, 12);
        module.funcs.push_back(std::move(callerFunction)); module.funcs.push_back(std::move(calleeFunction));
        struct SegmentCacheCleanup {
            u8* pointer; bool active = false;
            void release() { if (active) { utils::memory_decommit(pointer, 0x8000); active = false; } }
            ~SegmentCacheCleanup() { release(); }
        } segmentCleanup{vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1)};
        segmentCleanup.active = true;
        ppu_register_range(codeAddress, sizeof(opcodes));
        auto& interpreter = g_fxo->get<ppu_interpreter_rt>();
        const auto* codeCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(codeAddress) * 2);
        const auto fallback = codeCache[0].fn;
        if (armsx3_ios_ppu_prepare_module(&module) != 0)
            throw std::runtime_error("P28 static caller/callee module preparation failed");
        for (u32 i = 0; i < opcodes.size(); ++i) {
            const auto expected = i < 17 || i >= 24 ? interpreter.decode(opcodes[i]) : fallback;
            if (codeCache[i].fn != expected || ((i < 17 || i >= 24) && codeCache[i].fn == fallback))
                throw std::runtime_error("P28 caller/callee instruction decoding mismatch");
        }
        const auto* pageCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(address) * 2);
        std::vector<ppu_intrp_func_t> codeHandlers;
        for (u32 i = 0; i < 0x10000 / 4; ++i) codeHandlers.push_back(pageCache[i].fn);
        const std::vector<u8> before(guest, guest + 0x10000);
        if (!g_fxo->is_init<ppu_function_manager>() && !g_fxo->init<ppu_function_manager>())
            throw std::runtime_error("P28 function manager initialization failed");
        auto& manager = g_fxo->get<ppu_function_manager>();
        if (manager.addr) throw std::runtime_error("P28 requires unused function manager address");
        struct TableCleanup {
            ppu_function_manager& manager;
            void release() {
                if (!manager.addr) return;
                const u32 address = manager.addr; manager.addr = 0;
                utils::memory_decommit(vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1), 0x8000);
            }
            ~TableCleanup() { release(); }
        } tableCleanup{manager};
        if (armsx3_ios_ppu_prepare_hle_table() != 0)
            throw std::runtime_error("P28 production HLE table preparation failed");
        const u32 tableAddress = manager.addr;
        if (tableAddress < address + 0x10000 || tableAddress >= address + 0x30000 || tableAddress % 0x10000 ||
            !vm::check_addr(tableAddress, vm::page_readable | vm::page_executable, 0x10000))
            throw std::runtime_error("P28 HLE table allocation or flags mismatch");
        const auto* table = static_cast<const u8*>(vm::base(tableAddress));
        const std::vector<u8> tableBefore(table, table + 0x10000);
        const auto* cache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(tableAddress) * 2);
        std::vector<ppu_intrp_func_t> handlers;
        for (u32 i = 0; i < 0x10000 / 4; ++i) handlers.push_back(cache[i].fn);
        const auto created = cpu_thread::g_threads_created.load(), deleted = cpu_thread::g_threads_deleted.load();
        const u64 live = armsx3_ios_live_cpu_threads();
        const u32 initialStack = address + 0x8000, frameAddress = initialStack - 128;
        struct Program {
            u32 begin, end, returnAddress, dataAddress, initialStack;
            int result = -99; bool tls = false; std::atomic<bool> completed{false};
        } program{codeAddress, codeAddress + u32(sizeof(opcodes)), manager.func_addr(1, true), dataAddress, initialStack};
        const auto executeLinked = +[](void* user, u32 descriptor, u32 invalidDescriptor) -> int {
            auto& program = *static_cast<Program*>(user);
            if (descriptor != program.dataAddress || vm::read32(descriptor) != program.begin + 96 ||
                vm::read32(program.dataAddress + 176) != descriptor ||
                vm::read32(program.dataAddress + 180) != invalidDescriptor)
                throw std::runtime_error("P28 callback did not receive active backpatched guest descriptor");
            program.result = -99; program.tls = false; program.completed.store(false, std::memory_order_release);
            std::unique_ptr<named_thread<ppu_thread>> worker;
            {
                struct ConstructionID { u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                const ppu_thread_params params{static_cast<vm::addr_t>(program.begin - 0x100 + 0x1000), 0x8000, 0, {}, 0, 0};
                worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS linked guest call probe", 1000);
            }
            struct StopWorker { named_thread<ppu_thread>& worker;
                ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                    worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); } } stop{*worker};
            const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                program.result = armsx3_ios_ppu_call_bounded(&context, program.begin, program.end,
                    program.dataAddress + 32, program.returnAddress, 64);
                context.state += cpu_flag::exit; program.completed.store(true, std::memory_order_release);
            };
            worker->cmd_list({{ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
            const u32 address = program.begin - 0x100;
            worker->cia = address + 0x900; worker->lr = address + 0x904;
            worker->gpr[1] = program.initialStack; worker->gpr[2] = 0x13579;
            worker->gpr[6] = program.dataAddress + 32; worker->gpr[8] = 0; worker->gpr[9] = 0;
            worker->gpr[10] = program.dataAddress + 176;
            worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            ARMSX3StartupLog("P28 BEFORE guest import fetch, BCTRL to exported callee and BLR back to caller");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire))
                throw std::runtime_error("P28 linked guest execution deadline exceeded");
            (*worker)();
            if (!program.tls || program.result != 21 || worker->gpr[3] != 42 ||
                worker->gpr[8] != program.dataAddress || worker->gpr[9] != program.dataAddress + 32 ||
                worker->gpr[11] != descriptor || worker->gpr[12] != program.begin + 96 ||
                worker->gpr[2] != 0x13579 || worker->gpr[1] != program.initialStack ||
                worker->cia != address + 0x900 || worker->lr != address + 0x904 || worker->state & cpu_flag::ret)
                throw std::runtime_error("P28 linked guest call result, TOC, stack or caller context mismatch");
            return 0;
        };
        std::vector<u8> expectedGuest = before;
        const auto expect64 = [&](u32 guestAddress, u64 value) {
            const be_t<u64> word = value;
            std::memcpy(expectedGuest.data() + guestAddress - address, &word, sizeof(word));
        };
        expect64(dataAddress + 32, 42); expect64(frameAddress, initialStack);
        expect64(frameAddress + 16, program.returnAddress); expect64(frameAddress + 24, dataAddress + 32);
        for (unsigned repeat = 0; repeat < 2; ++repeat) {
            const int result = armsx3_ios_ppu_register_probe_exports_and_call(&module, dataAddress + 192, executeLinked, &program);
            if (result != 0) {
                char error[160];
                std::snprintf(error, sizeof(error), "P28 production export registration failed (wrapper result %d, iteration %u)", result, repeat + 1);
                throw std::runtime_error(error);
            }
            if (std::memcmp(guest, expectedGuest.data(), expectedGuest.size()) ||
                std::memcmp(vm::get_super_ptr(address), expectedGuest.data(), expectedGuest.size()))
                throw std::runtime_error("P28 import restoration, guest guard or alias mismatch");
        }
        if (armsx3_ios_ppu_register_probe_exports_and_call(&module, dataAddress + 188, executeLinked, &program) != -1)
            throw std::runtime_error("P28 export registration accepted invalid record start");
        if (std::memcmp(table, tableBefore.data(), tableBefore.size()) ||
            std::memcmp(vm::get_super_ptr(tableAddress), tableBefore.data(), tableBefore.size()))
            throw std::runtime_error("P28 registration mutated HLE descriptors/aliases");
        for (u32 i = 0; i < handlers.size(); ++i)
            if (cache[i].fn != handlers[i]) throw std::runtime_error("P28 registration mutated HLE dispatch");
        for (u32 offset = 0; offset < 0x10000; offset += 0x1000)
            if (vm::check_addr(tableAddress + offset, vm::page_writable))
                throw std::runtime_error("P28 HLE descriptor page became writable");
        for (u32 i = 0; i < codeHandlers.size(); ++i)
            if (pageCache[i].fn != codeHandlers[i]) throw std::runtime_error("P28 guest execution mutated decoded code cache");
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 2 ||
            cpu_thread::g_threads_deleted.load() != deleted + 2)
            throw std::runtime_error("P28 registration changed CPU thread counters");
        tableCleanup.release();
        if (vm::dealloc(tableAddress, vm::main) != 0x10000 || vm::check_addr(tableAddress))
            throw std::runtime_error("P28 HLE table deallocation failed");
        segmentCleanup.release();
        if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
            throw std::runtime_error("P28 guest deallocation failed");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P28 PASS: actual linked guest-to-guest BCTRL/BLR call, callee result42, separate caller/callee TOCs, stack/LR/HLE return, repeated registration/unload and cleanup; full executable loader/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}

extern "C" int armsx3_ios_ppu_load_probe_segments(const ppu_exec_object*, ppu_module<lv2_obj>*);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_production_elf_segments()
{
    ARMSX3StartupLog("P29 BEFORE production executable segment allocation/copy/hash/registration");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P29 requires stopped emulator");
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
        if (!g_fxo->is_init() ||
            (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>()))
            throw std::runtime_error("P29 fixed objects/interpreter unavailable");
        const u32 codeAddress = 0x10000, dataAddress = 0x20000, stackAddress = 0x30000;
        using namespace ppu_instructions;
        using namespace ppu_instructions::implicts;
        const std::array<u32, 2> opcodes{ADDI(3, 0, 42), BLR()};
        ppu_exec_object::ehdr_t header{};
        header.e_magic = "\177ELF"_u32; header.e_class = 2; header.e_data = 2;
        header.e_curver = 1; header.e_os_abi = elf_os::lv2; header.e_type = elf_type::exec;
        header.e_machine = elf_machine::ppc64; header.e_version = 1;
        header.e_entry = dataAddress; header.e_phoff = sizeof(header);
        header.e_ehsize = sizeof(header); header.e_phentsize = sizeof(ppu_exec_object::phdr_t); header.e_phnum = 2;
        std::array<ppu_exec_object::phdr_t, 2> segments{};
        segments[0].p_type = 1; segments[0].p_flags = 5; segments[0].p_offset = 0x100;
        segments[0].p_vaddr = codeAddress; segments[0].p_filesz = sizeof(opcodes);
        segments[0].p_memsz = 0x10000; segments[0].p_align = 0x100;
        segments[1].p_type = 1; segments[1].p_flags = 6; segments[1].p_offset = 0x200;
        segments[1].p_vaddr = dataAddress; segments[1].p_filesz = 32;
        segments[1].p_memsz = 0x10000; segments[1].p_align = 0x100;
        std::vector<u8> fixture(0x220, 0);
        std::memcpy(fixture.data(), &header, sizeof(header));
        std::memcpy(fixture.data() + sizeof(header), segments.data(), sizeof(segments));
        for (u32 i = 0; i < opcodes.size(); ++i) {
            const be_t<u32> word = opcodes[i]; std::memcpy(fixture.data() + 0x100 + i * 4, &word, 4);
        }
        const std::array<be_t<u32>, 2> descriptor{codeAddress, dataAddress};
        std::memcpy(fixture.data() + 0x200, descriptor.data(), sizeof(descriptor));
        for (u32 i = 8; i < 32; ++i) fixture[0x200 + i] = u8(0xa0 + i);
        const auto stream = fs::make_stream(fixture);
        ppu_exec_object elf(stream);
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 2)
            throw std::runtime_error("P29 fixture reader failed");
        const auto created = cpu_thread::g_threads_created.load(), deleted = cpu_thread::g_threads_deleted.load();
        const u64 live = armsx3_ios_live_cpu_threads();
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, codeAddress, 0x10000))
            throw std::runtime_error("P29 rollback memory block unavailable");
        {
            ppu_module<lv2_obj> partial;
            if (armsx3_ios_ppu_load_probe_segments(&elf, &partial) != -3 || !partial.segs.empty() ||
                !partial.addr_to_seg_index.empty() || vm::check_addr(codeAddress) || vm::check_addr(dataAddress))
                throw std::runtime_error("P29 failed second allocation did not roll back first segment");
        }
        ARMSX3StartupLog("P29 PASS: production second-segment allocation failure rolls back first segment and metadata");
        vm::close(); initialized = false;
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, codeAddress, 0x50000))
            throw std::runtime_error("P29 main memory block unavailable");
        // Invalid metadata must be rejected before any production allocation.
        for (unsigned test = 0; test < 5; ++test) {
            auto malformed = fixture; auto bad = segments;
            if (test == 0) bad[1].p_vaddr = codeAddress;
            if (test == 1) bad[1].p_memsz = ~u64{0};
            if (test == 2) bad[0].p_flags = 7;
            if (test == 3) bad[1].p_type = 7;
            if (test == 4) bad[1].p_filesz = 257;
            std::memcpy(malformed.data() + sizeof(header), bad.data(), sizeof(bad));
            if (test == 4) malformed.resize(0x301);
            const auto badStream = fs::make_stream(std::move(malformed));
            ppu_exec_object rejected(badStream); ppu_module<lv2_obj> empty;
            if (rejected.get_error() != elf_error::ok || armsx3_ios_ppu_load_probe_segments(&rejected, &empty) != -2 ||
                !empty.segs.empty() || vm::check_addr(codeAddress) || vm::check_addr(dataAddress))
                throw std::runtime_error("P29 bounded loader accepted invalid metadata or allocated memory");
        }
        if (armsx3_ios_ppu_load_probe_segments(nullptr, nullptr) != -1)
            throw std::runtime_error("P29 null loader inputs were accepted");
        std::array<std::vector<u8>, 2> expected{std::vector<u8>(0x10000, 0), std::vector<u8>(0x10000, 0)};
        std::memcpy(expected[0].data(), fixture.data() + 0x100, sizeof(opcodes));
        std::memcpy(expected[1].data(), fixture.data() + 0x200, 32);
        for (unsigned repeat = 0; repeat < 2; ++repeat) {
            ppu_module<lv2_obj> module;
            struct SegmentCleanup {
                void release() {
                    utils::memory_decommit(vm::g_exec_addr + vm::g_exec_addr_seg_offset + (0x10000 >> 1), 0x8000);
                }
                ~SegmentCleanup() { release(); }
            } segmentCleanup;
            if (armsx3_ios_ppu_load_probe_segments(&elf, &module) != 0 || module.segs.size() != 2 ||
                module.addr_to_seg_index.at(codeAddress) != 0 || module.addr_to_seg_index.at(dataAddress) != 1)
                throw std::runtime_error("P29 production segment loading failed");
            for (u32 index = 0; index < 2; ++index) {
                const auto& seg = module.segs[index];
                const u32 address = codeAddress + index * 0x10000;
                if (seg.addr != address || seg.size != 0x10000 || seg.type != 1 || seg.flags != (index ? 6u : 5u) ||
                    seg.filesz != (index ? 32u : 8u) || seg.ptr != vm::base(address) ||
                    std::memcmp(vm::base(address), expected[index].data(), 0x10000) ||
                    std::memcmp(vm::get_super_ptr(address), expected[index].data(), 0x10000))
                    throw std::runtime_error("P29 segment metadata, copied bytes, zero BSS or alias mismatch");
            }
            const std::array<u8, 20> expectedHash{0x9a, 0xb8, 0x51, 0x3a, 0x9f, 0xbc, 0xe4, 0x23, 0x40, 0x74, 0x12, 0xa3, 0xec, 0x41, 0x76, 0x48, 0x5a, 0x18, 0x7e, 0x94};
            if (std::memcmp(module.sha1, expectedHash.data(), expectedHash.size()))
                throw std::runtime_error("P29 production executable segment hash mismatch");
            ppu_module<lv2_obj> occupied;
            if (armsx3_ios_ppu_load_probe_segments(&elf, &occupied) != -2 || !occupied.segs.empty())
                throw std::runtime_error("P29 loader overwrote an occupied guest page");
            ppu_function function{}; function.addr = codeAddress; function.toc = dataAddress; function.size = sizeof(opcodes);
            function.blocks.emplace(codeAddress, sizeof(opcodes)); module.funcs.push_back(std::move(function));
            auto& interpreter = g_fxo->get<ppu_interpreter_rt>();
            const auto* codeCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(codeAddress) * 2);
            const auto fallback = codeCache[0].fn;
            if (armsx3_ios_ppu_prepare_module(&module) != 0 || codeCache[0].fn == fallback || codeCache[1].fn == fallback ||
                codeCache[0].fn != interpreter.decode(opcodes[0]) || codeCache[1].fn != interpreter.decode(opcodes[1]))
                throw std::runtime_error("P29 loaded code preparation failed");
            std::vector<ppu_intrp_func_t> codeHandlers;
            for (u32 i = 0; i < 0x10000 / 4; ++i) codeHandlers.push_back(codeCache[i].fn);
            if (vm::alloc(0x10000, vm::main, 0x10000) != stackAddress)
                throw std::runtime_error("P29 worker stack allocation failed");
            const auto* stack = static_cast<const u8*>(vm::base(stackAddress));
            const std::vector<u8> stackBefore(stack, stack + 0x10000);
            if (!g_fxo->is_init<ppu_function_manager>() && !g_fxo->init<ppu_function_manager>())
                throw std::runtime_error("P29 function manager initialization failed");
            auto& manager = g_fxo->get<ppu_function_manager>();
            if (manager.addr) throw std::runtime_error("P29 requires unused function manager address");
            struct TableCleanup {
                ppu_function_manager& manager;
                void release() {
                    if (!manager.addr) return;
                    const u32 address = manager.addr; manager.addr = 0;
                    utils::memory_decommit(vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1), 0x8000);
                }
                ~TableCleanup() { release(); }
            } tableCleanup{manager};
            if (armsx3_ios_ppu_prepare_hle_table() != 0 || manager.addr != 0x40000)
                throw std::runtime_error("P29 HLE return table preparation failed");
            const u32 tableAddress = manager.addr;
            const auto* table = static_cast<const u8*>(vm::base(tableAddress));
            const std::vector<u8> tableBefore(table, table + 0x10000);
            const auto* tableCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(tableAddress) * 2);
            std::vector<ppu_intrp_func_t> tableHandlers;
            for (u32 i = 0; i < 0x10000 / 4; ++i) tableHandlers.push_back(tableCache[i].fn);
            struct Program { u32 begin, end, toc, returnAddress;
                int result = -99; bool tls = false; std::atomic<bool> completed{false};
            } program{codeAddress, codeAddress + u32(sizeof(opcodes)), dataAddress, manager.func_addr(1, true)};
            {
                std::unique_ptr<named_thread<ppu_thread>> worker;
                {
                    struct ConstructionID { u32 previous = id_manager::g_id;
                        ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                        ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                    const ppu_thread_params params{static_cast<vm::addr_t>(stackAddress), 0x8000, 0, {}, 0, 0};
                    worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS production ELF segment probe", 1000);
                }
                struct StopWorker { named_thread<ppu_thread>& worker;
                    ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                        worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); } } stop{*worker};
                const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                    auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                    program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                    program.result = armsx3_ios_ppu_call_bounded(&context, program.begin, program.end, program.toc, program.returnAddress, 16);
                    context.state += cpu_flag::exit; program.completed.store(true, std::memory_order_release);
                };
                worker->cmd_list({{ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
                worker->cia = codeAddress + 0x900; worker->lr = codeAddress + 0x904;
                worker->gpr[1] = stackAddress + 0x8000; worker->gpr[2] = 0x13579;
                worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
                worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
                ARMSX3StartupLog("P29 BEFORE bounded execution from production-loaded ELF code page");
                *worker = thread_state::created;
                const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
                while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                    std::this_thread::yield();
                if (!program.completed.load(std::memory_order_acquire)) throw std::runtime_error("P29 loaded guest execution deadline exceeded");
                (*worker)();
                if (!program.tls || program.result != 3 || worker->gpr[3] != 42 || worker->gpr[2] != 0x13579 ||
                    worker->gpr[1] != stackAddress + 0x8000 || worker->cia != codeAddress + 0x900 ||
                    worker->lr != codeAddress + 0x904 || worker->state & cpu_flag::ret)
                    throw std::runtime_error("P29 loaded guest result or restored caller context mismatch");
            }
            for (u32 index = 0; index < 2; ++index)
                if (std::memcmp(vm::base(codeAddress + index * 0x10000), expected[index].data(), 0x10000) ||
                    std::memcmp(vm::get_super_ptr(codeAddress + index * 0x10000), expected[index].data(), 0x10000))
                    throw std::runtime_error("P29 loader rejection/execution mutated code, data or BSS");
            if (std::memcmp(stack, stackBefore.data(), 0x10000) ||
                std::memcmp(vm::get_super_ptr(stackAddress), stackBefore.data(), 0x10000) ||
                std::memcmp(table, tableBefore.data(), 0x10000) ||
                std::memcmp(vm::get_super_ptr(tableAddress), tableBefore.data(), 0x10000))
                throw std::runtime_error("P29 execution mutated stack/HLE memory or aliases");
            for (u32 i = 0; i < codeHandlers.size(); ++i)
                if (codeCache[i].fn != codeHandlers[i] || tableCache[i].fn != tableHandlers[i])
                    throw std::runtime_error("P29 execution mutated code/HLE dispatch handlers");
            for (u32 offset = 0; offset < 0x10000; offset += 0x1000)
                if (!vm::check_addr(tableAddress + offset, vm::page_readable | vm::page_executable) ||
                    vm::check_addr(tableAddress + offset, vm::page_writable))
                    throw std::runtime_error("P29 HLE page protection mismatch");
            tableCleanup.release(); segmentCleanup.release();
            for (u32 address : {tableAddress, stackAddress, dataAddress, codeAddress})
                if (vm::dealloc(address, vm::main) != 0x10000 || vm::check_addr(address))
                    throw std::runtime_error("P29 guest allocation cleanup failed");
            module.segs.clear(); module.addr_to_seg_index.clear();
        }
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 2 ||
            cpu_thread::g_threads_deleted.load() != deleted + 2)
            throw std::runtime_error("P29 worker lifecycle did not balance");
        vm::close(); initialized = false;
        ARMSX3StartupLog("P29 PASS: shared production ELF segment allocation/copy/BSS/hash/code-registration, second-allocation rollback, malformed/occupied input rejection, repeated loaded guest result42/HLE return and cleanup; complete process/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}

extern "C" int armsx3_ios_ppu_load_probe_image_segments(const ppu_exec_object*, ppu_module<lv2_obj>*);
extern "C" int armsx3_ios_ppu_link_probe_image_and_call(ppu_module<lv2_obj>*, const ppu_exec_object::prog_t*, int (*)(void*, u32, u32), void*);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_loaded_elf_linkage()
{
    ARMSX3StartupLog("P30 BEFORE production-loaded ELF PRX parameter linking and guest call");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P30 requires stopped emulator");
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
        if (!g_fxo->is_init() ||
            (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>()))
            throw std::runtime_error("P30 fixed objects/interpreter unavailable");
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x50000))
            throw std::runtime_error("P30 main memory block unavailable");
        const u32 address = 0x10000, codeAddress = address, dataAddress = 0x20000, stackAddress = 0x30000;
        using namespace ppu_instructions;
        using namespace ppu_instructions::implicts;
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        std::array<u32, 27> opcodes; opcodes.fill(0x60000000); // padding NOPs
        const std::array<u32, 17> caller{MFLR(0), STDU(1, 1, -128), STD(0, 1, 16), STD(2, 1, 24),
            ADDI(3, 0, 35), dform(32, 11, 10, 0), dform(32, 12, 11, 0), dform(32, 2, 11, 4),
            MTCTR(12), BCTRL(), LD(2, 1, 24), dform(24, 2, 9, 0), STD(3, 6, 0),
            LD(0, 1, 16), ADDI(1, 1, 128), MTLR(0), BLR()};
        for (u32 i = 0; i < caller.size(); ++i) opcodes[i] = caller[i];
        opcodes[24] = ADDI(3, 3, 7); opcodes[25] = dform(24, 2, 8, 0); opcodes[26] = BLR();
        ppu_exec_object::ehdr_t header{};
        header.e_magic = "\177ELF"_u32; header.e_class = 2; header.e_data = 2;
        header.e_curver = 1; header.e_os_abi = elf_os::lv2; header.e_type = elf_type::exec;
        header.e_machine = elf_machine::ppc64; header.e_version = 1;
        header.e_entry = dataAddress + 8; header.e_phoff = sizeof(header);
        header.e_ehsize = sizeof(header); header.e_phentsize = sizeof(ppu_exec_object::phdr_t); header.e_phnum = 3;
        std::array<ppu_exec_object::phdr_t, 3> segments{};
        segments[0].p_type = 1; segments[0].p_flags = 5; segments[0].p_offset = 0x100;
        segments[0].p_vaddr = codeAddress; segments[0].p_filesz = sizeof(opcodes);
        segments[0].p_memsz = 0x10000; segments[0].p_align = 0x100;
        segments[1].p_type = 1; segments[1].p_flags = 6; segments[1].p_offset = 0x200;
        segments[1].p_vaddr = dataAddress; segments[1].p_filesz = 296;
        segments[1].p_memsz = 0x10000; segments[1].p_align = 0x100;
        segments[2].p_type = 0x60000002; segments[2].p_offset = 0x300;
        segments[2].p_vaddr = dataAddress + 256; segments[2].p_filesz = 40;
        segments[2].p_memsz = 40; segments[2].p_align = 4;
        std::vector<u8> fixture(0x328, 0);
        std::memcpy(fixture.data(), &header, sizeof(header));
        std::memcpy(fixture.data() + sizeof(header), segments.data(), sizeof(segments));
        const auto fileWord = [&](u32 offset, u32 value) { const be_t<u32> word = value;
            std::memcpy(fixture.data() + offset, &word, 4); };
        for (u32 i = 0; i < opcodes.size(); ++i) fileWord(0x100 + i * 4, opcodes[i]);
        fileWord(0x200, codeAddress + 96); fileWord(0x204, dataAddress);
        fileWord(0x208, codeAddress); fileWord(0x20c, dataAddress + 32);
        fixture[0x240] = 44; fixture[0x247] = 2;
        fileWord(0x250, dataAddress + 128); fileWord(0x254, dataAddress + 160); fileWord(0x258, dataAddress + 176);
        std::memcpy(fixture.data() + 0x280, "iOSProbe", 9);
        fileWord(0x2a0, 0x49524e31); fileWord(0x2a4, 0x49524e32);
        fileWord(0x2b0, codeAddress); fileWord(0x2b4, codeAddress);
        fixture[0x2c0] = 44; fixture[0x2c5] = 1; fixture[0x2c7] = 1;
        fileWord(0x2d0, dataAddress + 128); fileWord(0x2d4, dataAddress + 160);
        fileWord(0x2d8, dataAddress + 236); fileWord(0x2ec, dataAddress);
        const std::array<u32, 10> control{40, 0x1b434cec, 0, 0, dataAddress + 192,
            dataAddress + 236, dataAddress + 64, dataAddress + 108, 0, 0};
        for (u32 i = 0; i < control.size(); ++i) fileWord(0x300 + i * 4, control[i]);
        const auto stream = fs::make_stream(fixture);
        ppu_exec_object elf(stream);
        ppu_module<lv2_obj> module;
        module.name = "iOS loaded ELF linkage probe";
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 3 ||
            armsx3_ios_ppu_load_probe_image_segments(&elf, &module) != 0)
            throw std::runtime_error("P30 production ELF segment loading failed");
        const std::array<u8, 20> expectedHash{0x5e, 0x78, 0x82, 0x98, 0x94, 0x84, 0xd8, 0x48, 0x9b, 0x01, 0x1b, 0x0f, 0xa5, 0xf7, 0x48, 0xdf, 0x34, 0xbe, 0x50, 0xfc};
        if (std::memcmp(module.sha1, expectedHash.data(), expectedHash.size()))
            throw std::runtime_error("P30 production ELF hash mismatch");
        std::vector<u8> expectedCode(0x10000, 0), expectedData(0x10000, 0);
        std::memcpy(expectedCode.data(), fixture.data() + 0x100, sizeof(opcodes));
        std::memcpy(expectedData.data(), fixture.data() + 0x200, 296);
        auto* guest = static_cast<u8*>(vm::base(codeAddress));
        auto* data = static_cast<u8*>(vm::base(dataAddress));
        if (std::memcmp(guest, expectedCode.data(), 0x10000) || std::memcmp(data, expectedData.data(), 0x10000) ||
            module.segs.size() != 2 || module.addr_to_seg_index.at(codeAddress) != 0 ||
            module.addr_to_seg_index.at(dataAddress) != 1)
            throw std::runtime_error("P30 loaded ELF contents/BSS/metadata mismatch");
        // Prepare exact fixture blocks from the production-loaded ELF segments.
        // Global process initialization and main-thread admission remain pending.
        ppu_function callerFunction{};
        callerFunction.addr = codeAddress; callerFunction.toc = dataAddress + 32; callerFunction.size = 68;
        callerFunction.blocks.emplace(codeAddress, 68);
        ppu_function calleeFunction{};
        calleeFunction.addr = codeAddress + 96; calleeFunction.toc = dataAddress; calleeFunction.size = 12;
        calleeFunction.blocks.emplace(codeAddress + 96, 12);
        module.funcs.push_back(std::move(callerFunction)); module.funcs.push_back(std::move(calleeFunction));
        struct SegmentCacheCleanup {
            u8* pointer; bool active = false;
            void release() { if (active) { utils::memory_decommit(pointer, 0x8000); active = false; } }
            ~SegmentCacheCleanup() { release(); }
        } segmentCleanup{vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1)};
        segmentCleanup.active = true;
        auto& interpreter = g_fxo->get<ppu_interpreter_rt>();
        const auto* codeCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(codeAddress) * 2);
        const auto fallback = codeCache[0].fn;
        if (armsx3_ios_ppu_prepare_module(&module) != 0)
            throw std::runtime_error("P30 static caller/callee module preparation failed");
        for (u32 i = 0; i < opcodes.size(); ++i) {
            const auto expected = i < 17 || i >= 24 ? interpreter.decode(opcodes[i]) : fallback;
            if (codeCache[i].fn != expected || ((i < 17 || i >= 24) && codeCache[i].fn == fallback))
                throw std::runtime_error("P30 caller/callee instruction decoding mismatch");
        }
        const auto* pageCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(address) * 2);
        std::vector<ppu_intrp_func_t> codeHandlers;
        for (u32 i = 0; i < 0x10000 / 4; ++i) codeHandlers.push_back(pageCache[i].fn);
        if (vm::alloc(0x10000, vm::main, 0x10000) != stackAddress)
            throw std::runtime_error("P30 worker stack allocation failed");
        const auto* stack = static_cast<const u8*>(vm::base(stackAddress));
        std::vector<u8> expectedStack(stack, stack + 0x10000);
        if (!g_fxo->is_init<ppu_function_manager>() && !g_fxo->init<ppu_function_manager>())
            throw std::runtime_error("P30 function manager initialization failed");
        auto& manager = g_fxo->get<ppu_function_manager>();
        if (manager.addr) throw std::runtime_error("P30 requires unused function manager address");
        struct TableCleanup {
            ppu_function_manager& manager;
            void release() {
                if (!manager.addr) return;
                const u32 address = manager.addr; manager.addr = 0;
                utils::memory_decommit(vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1), 0x8000);
            }
            ~TableCleanup() { release(); }
        } tableCleanup{manager};
        if (armsx3_ios_ppu_prepare_hle_table() != 0)
            throw std::runtime_error("P30 production HLE table preparation failed");
        const u32 tableAddress = manager.addr;
        if (tableAddress != 0x40000 ||
            !vm::check_addr(tableAddress, vm::page_readable | vm::page_executable, 0x10000))
            throw std::runtime_error("P30 HLE table allocation or flags mismatch");
        const auto* table = static_cast<const u8*>(vm::base(tableAddress));
        const std::vector<u8> tableBefore(table, table + 0x10000);
        const auto* cache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(tableAddress) * 2);
        std::vector<ppu_intrp_func_t> handlers;
        for (u32 i = 0; i < 0x10000 / 4; ++i) handlers.push_back(cache[i].fn);
        const auto created = cpu_thread::g_threads_created.load(), deleted = cpu_thread::g_threads_deleted.load();
        const u64 live = armsx3_ios_live_cpu_threads();
        const u32 initialStack = stackAddress + 0x8000, frameAddress = initialStack - 128;
        struct Program {
            u32 begin, end, returnAddress, dataAddress, initialStack;
            int result = -99; bool tls = false; std::atomic<bool> completed{false};
        } program{vm::read32(u32(elf.header.e_entry)), codeAddress + u32(sizeof(opcodes)), manager.func_addr(1, true), dataAddress, initialStack};
        const auto executeLinked = +[](void* user, u32 descriptor, u32 invalidDescriptor) -> int {
            auto& program = *static_cast<Program*>(user);
            if (descriptor != program.dataAddress || vm::read32(descriptor) != program.begin + 96 ||
                vm::read32(program.dataAddress + 176) != descriptor ||
                vm::read32(program.dataAddress + 180) != invalidDescriptor)
                throw std::runtime_error("P30 callback did not receive active backpatched guest descriptor");
            program.result = -99; program.tls = false; program.completed.store(false, std::memory_order_release);
            std::unique_ptr<named_thread<ppu_thread>> worker;
            {
                struct ConstructionID { u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                const ppu_thread_params params{static_cast<vm::addr_t>(program.initialStack - 0x8000), 0x8000, 0, {}, 0, 0};
                worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS linked guest call probe", 1000);
            }
            struct StopWorker { named_thread<ppu_thread>& worker;
                ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                    worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); } } stop{*worker};
            const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                program.result = armsx3_ios_ppu_call_bounded(&context, program.begin, program.end,
                    program.dataAddress + 32, program.returnAddress, 64);
                context.state += cpu_flag::exit; program.completed.store(true, std::memory_order_release);
            };
            worker->cmd_list({{ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
            const u32 address = program.begin;
            worker->cia = address + 0x900; worker->lr = address + 0x904;
            worker->gpr[1] = program.initialStack; worker->gpr[2] = 0x13579;
            worker->gpr[6] = program.dataAddress + 32; worker->gpr[8] = 0; worker->gpr[9] = 0;
            worker->gpr[10] = program.dataAddress + 176;
            worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            ARMSX3StartupLog("P30 BEFORE guest BCTRL/BLR call through executable-loader PRX linkage");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire))
                throw std::runtime_error("P30 linked guest execution deadline exceeded");
            (*worker)();
            if (!program.tls || program.result != 21 || worker->gpr[3] != 42 ||
                worker->gpr[8] != program.dataAddress || worker->gpr[9] != program.dataAddress + 32 ||
                worker->gpr[11] != descriptor || worker->gpr[12] != program.begin + 96 ||
                worker->gpr[2] != 0x13579 || worker->gpr[1] != program.initialStack ||
                worker->cia != address + 0x900 || worker->lr != address + 0x904 || worker->state & cpu_flag::ret)
                throw std::runtime_error("P30 linked guest call result, TOC, stack or caller context mismatch");
            return 0;
        };
        const auto expect64 = [](std::vector<u8>& bytes, u32 offset, u64 value) {
            const be_t<u64> word = value; std::memcpy(bytes.data() + offset, &word, sizeof(word));
        };
        // The production parameter handler itself rejects bad magic before linking.
        vm::write32(dataAddress + 260, 0);
        if (armsx3_ios_ppu_link_probe_image_and_call(&module, &elf.progs[2], executeLinked, &program) != -6)
            throw std::runtime_error("P30 production PRX parameter handler accepted bad magic");
        vm::write32(dataAddress + 260, control[1]);
        if (std::memcmp(data, expectedData.data(), 0x10000))
            throw std::runtime_error("P30 rejected PRX parameters mutated guest image");
        ARMSX3StartupLog("P30 PASS: executable PRX parameter handler rejects bad magic before linking");
        expect64(expectedData, 32, 42); expect64(expectedStack, frameAddress - stackAddress, initialStack);
        expect64(expectedStack, frameAddress - stackAddress + 16, program.returnAddress);
        expect64(expectedStack, frameAddress - stackAddress + 24, dataAddress + 32);
        for (unsigned repeat = 0; repeat < 2; ++repeat) {
            const int result = armsx3_ios_ppu_link_probe_image_and_call(&module, &elf.progs[2], executeLinked, &program);
            if (result != 0) {
                char error[160];
                std::snprintf(error, sizeof(error), "P30 executable PRX parameter linkage failed (wrapper result %d, iteration %u)", result, repeat + 1);
                throw std::runtime_error(error);
            }
            for (const auto& region : std::array<std::pair<u32, const std::vector<u8>*>, 3>{
                std::pair{codeAddress, &expectedCode}, std::pair{dataAddress, &expectedData}, std::pair{stackAddress, &expectedStack}})
                if (std::memcmp(vm::base(region.first), region.second->data(), 0x10000) ||
                    std::memcmp(vm::get_super_ptr(region.first), region.second->data(), 0x10000))
                    throw std::runtime_error("P30 loaded ELF/code/BSS/stack/import restoration or alias mismatch");
        }
        if (std::memcmp(table, tableBefore.data(), tableBefore.size()) ||
            std::memcmp(vm::get_super_ptr(tableAddress), tableBefore.data(), tableBefore.size()))
            throw std::runtime_error("P30 registration mutated HLE descriptors/aliases");
        for (u32 i = 0; i < handlers.size(); ++i)
            if (cache[i].fn != handlers[i]) throw std::runtime_error("P30 registration mutated HLE dispatch");
        for (u32 offset = 0; offset < 0x10000; offset += 0x1000)
            if (vm::check_addr(tableAddress + offset, vm::page_writable))
                throw std::runtime_error("P30 HLE descriptor page became writable");
        for (u32 i = 0; i < codeHandlers.size(); ++i)
            if (pageCache[i].fn != codeHandlers[i]) throw std::runtime_error("P30 guest execution mutated decoded code cache");
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 2 ||
            cpu_thread::g_threads_deleted.load() != deleted + 2)
            throw std::runtime_error("P30 registration changed CPU thread counters");
        tableCleanup.release();
        if (vm::dealloc(tableAddress, vm::main) != 0x10000 || vm::check_addr(tableAddress))
            throw std::runtime_error("P30 HLE table deallocation failed");
        segmentCleanup.release();
        for (u32 allocated : {stackAddress, dataAddress, codeAddress})
            if (vm::dealloc(allocated, vm::main) != 0x10000 || vm::check_addr(allocated))
                throw std::runtime_error("P30 guest deallocation failed");
        module.segs.clear(); module.addr_to_seg_index.clear();
        vm::close(); initialized = false;
        ARMSX3StartupLog("P30 PASS: production ELF segments and executable PRX parameters drive export/import linking, bad-magic rejection, actual BCTRL/BLR result42, separate TOCs, stack/LR/HLE return, repeated unload and cleanup; global process/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}

extern "C" int armsx3_ios_ppu_prepare_probe_arguments(ppu_thread*, u32*, u32*);
extern "C" int armsx3_ios_ppu_load_probe_image_segments(const ppu_exec_object*, ppu_module<lv2_obj>*);
extern "C" int armsx3_ios_ppu_link_probe_image_and_call(ppu_module<lv2_obj>*, const ppu_exec_object::prog_t*, int (*)(void*, u32, u32), void*);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_executable_arguments()
{
    ARMSX3StartupLog("P31 BEFORE production process arguments, entry register commands and loaded ELF guest call");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P31 requires stopped emulator");
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
        if (!g_fxo->is_init() ||
            (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>()))
            throw std::runtime_error("P31 fixed objects/interpreter unavailable");
        struct Arguments {
            std::vector<std::string> argv = Emu.argv, envp = Emu.envp;
            std::vector<u8> data = Emu.data;
            ~Arguments() { Emu.argv = std::move(argv); Emu.envp = std::move(envp); Emu.data = std::move(data); }
        } arguments;
        Emu.argv = {"probe", "123456789012345", "1234567890123456"};
        Emu.envp = {"LANG=C", ""};
        Emu.data.resize(17);
        for (u32 i = 0; i < Emu.data.size(); ++i) Emu.data[i] = u8(0xa0 + i);
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x50000))
            throw std::runtime_error("P31 main memory block unavailable");
        const u32 address = 0x10000, codeAddress = address, dataAddress = 0x20000, stackAddress = 0x30000;
        using namespace ppu_instructions;
        using namespace ppu_instructions::implicts;
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        std::array<u32, 27> opcodes; opcodes.fill(0x60000000); // padding NOPs
        const std::array<u32, 17> caller{MFLR(0), STDU(1, 1, -128), STD(0, 1, 16), STD(2, 1, 24),
            ADDI(3, 0, 35), dform(32, 11, 10, 0), dform(32, 12, 11, 0), dform(32, 2, 11, 4),
            MTCTR(12), BCTRL(), LD(2, 1, 24), dform(24, 2, 9, 0), STD(3, 6, 0),
            LD(0, 1, 16), ADDI(1, 1, 128), MTLR(0), BLR()};
        for (u32 i = 0; i < caller.size(); ++i) opcodes[i] = caller[i];
        opcodes[24] = ADDI(3, 3, 7); opcodes[25] = dform(24, 2, 8, 0); opcodes[26] = BLR();
        ppu_exec_object::ehdr_t header{};
        header.e_magic = "\177ELF"_u32; header.e_class = 2; header.e_data = 2;
        header.e_curver = 1; header.e_os_abi = elf_os::lv2; header.e_type = elf_type::exec;
        header.e_machine = elf_machine::ppc64; header.e_version = 1;
        header.e_entry = dataAddress + 8; header.e_phoff = sizeof(header);
        header.e_ehsize = sizeof(header); header.e_phentsize = sizeof(ppu_exec_object::phdr_t); header.e_phnum = 3;
        std::array<ppu_exec_object::phdr_t, 3> segments{};
        segments[0].p_type = 1; segments[0].p_flags = 5; segments[0].p_offset = 0x100;
        segments[0].p_vaddr = codeAddress; segments[0].p_filesz = sizeof(opcodes);
        segments[0].p_memsz = 0x10000; segments[0].p_align = 0x100;
        segments[1].p_type = 1; segments[1].p_flags = 6; segments[1].p_offset = 0x200;
        segments[1].p_vaddr = dataAddress; segments[1].p_filesz = 296;
        segments[1].p_memsz = 0x10000; segments[1].p_align = 0x100;
        segments[2].p_type = 0x60000002; segments[2].p_offset = 0x300;
        segments[2].p_vaddr = dataAddress + 256; segments[2].p_filesz = 40;
        segments[2].p_memsz = 40; segments[2].p_align = 4;
        std::vector<u8> fixture(0x328, 0);
        std::memcpy(fixture.data(), &header, sizeof(header));
        std::memcpy(fixture.data() + sizeof(header), segments.data(), sizeof(segments));
        const auto fileWord = [&](u32 offset, u32 value) { const be_t<u32> word = value;
            std::memcpy(fixture.data() + offset, &word, 4); };
        for (u32 i = 0; i < opcodes.size(); ++i) fileWord(0x100 + i * 4, opcodes[i]);
        fileWord(0x200, codeAddress + 96); fileWord(0x204, dataAddress);
        fileWord(0x208, codeAddress); fileWord(0x20c, dataAddress + 32);
        fixture[0x240] = 44; fixture[0x247] = 2;
        fileWord(0x250, dataAddress + 128); fileWord(0x254, dataAddress + 160); fileWord(0x258, dataAddress + 176);
        std::memcpy(fixture.data() + 0x280, "iOSProbe", 9);
        fileWord(0x2a0, 0x49524e31); fileWord(0x2a4, 0x49524e32);
        fileWord(0x2b0, codeAddress); fileWord(0x2b4, codeAddress);
        fixture[0x2c0] = 44; fixture[0x2c5] = 1; fixture[0x2c7] = 1;
        fileWord(0x2d0, dataAddress + 128); fileWord(0x2d4, dataAddress + 160);
        fileWord(0x2d8, dataAddress + 236); fileWord(0x2ec, dataAddress);
        const std::array<u32, 10> control{40, 0x1b434cec, 0, 0, dataAddress + 192,
            dataAddress + 236, dataAddress + 64, dataAddress + 108, 0, 0};
        for (u32 i = 0; i < control.size(); ++i) fileWord(0x300 + i * 4, control[i]);
        const auto stream = fs::make_stream(fixture);
        ppu_exec_object elf(stream);
        ppu_module<lv2_obj> module;
        module.name = "iOS loaded ELF linkage probe";
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 3 ||
            armsx3_ios_ppu_load_probe_image_segments(&elf, &module) != 0)
            throw std::runtime_error("P31 production ELF segment loading failed");
        const std::array<u8, 20> expectedHash{0x5e, 0x78, 0x82, 0x98, 0x94, 0x84, 0xd8, 0x48, 0x9b, 0x01, 0x1b, 0x0f, 0xa5, 0xf7, 0x48, 0xdf, 0x34, 0xbe, 0x50, 0xfc};
        if (std::memcmp(module.sha1, expectedHash.data(), expectedHash.size()))
            throw std::runtime_error("P31 production ELF hash mismatch");
        std::vector<u8> expectedCode(0x10000, 0), expectedData(0x10000, 0);
        std::memcpy(expectedCode.data(), fixture.data() + 0x100, sizeof(opcodes));
        std::memcpy(expectedData.data(), fixture.data() + 0x200, 296);
        auto* guest = static_cast<u8*>(vm::base(codeAddress));
        auto* data = static_cast<u8*>(vm::base(dataAddress));
        if (std::memcmp(guest, expectedCode.data(), 0x10000) || std::memcmp(data, expectedData.data(), 0x10000) ||
            module.segs.size() != 2 || module.addr_to_seg_index.at(codeAddress) != 0 ||
            module.addr_to_seg_index.at(dataAddress) != 1)
            throw std::runtime_error("P31 loaded ELF contents/BSS/metadata mismatch");
        // Prepare exact fixture blocks from the production-loaded ELF segments.
        // Global process initialization and main-thread admission remain pending.
        ppu_function callerFunction{};
        callerFunction.addr = codeAddress; callerFunction.toc = dataAddress + 32; callerFunction.size = 68;
        callerFunction.blocks.emplace(codeAddress, 68);
        ppu_function calleeFunction{};
        calleeFunction.addr = codeAddress + 96; calleeFunction.toc = dataAddress; calleeFunction.size = 12;
        calleeFunction.blocks.emplace(codeAddress + 96, 12);
        module.funcs.push_back(std::move(callerFunction)); module.funcs.push_back(std::move(calleeFunction));
        struct SegmentCacheCleanup {
            u8* pointer; bool active = false;
            void release() { if (active) { utils::memory_decommit(pointer, 0x8000); active = false; } }
            ~SegmentCacheCleanup() { release(); }
        } segmentCleanup{vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1)};
        segmentCleanup.active = true;
        auto& interpreter = g_fxo->get<ppu_interpreter_rt>();
        const auto* codeCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(codeAddress) * 2);
        const auto fallback = codeCache[0].fn;
        if (armsx3_ios_ppu_prepare_module(&module) != 0)
            throw std::runtime_error("P31 static caller/callee module preparation failed");
        for (u32 i = 0; i < opcodes.size(); ++i) {
            const auto expected = i < 17 || i >= 24 ? interpreter.decode(opcodes[i]) : fallback;
            if (codeCache[i].fn != expected || ((i < 17 || i >= 24) && codeCache[i].fn == fallback))
                throw std::runtime_error("P31 caller/callee instruction decoding mismatch");
        }
        const auto* pageCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(address) * 2);
        std::vector<ppu_intrp_func_t> codeHandlers;
        for (u32 i = 0; i < 0x10000 / 4; ++i) codeHandlers.push_back(pageCache[i].fn);
        if (vm::alloc(0x10000, vm::main, 0x10000) != stackAddress)
            throw std::runtime_error("P31 worker stack allocation failed");
        const auto* stack = static_cast<const u8*>(vm::base(stackAddress));
        std::vector<u8> expectedStack(stack, stack + 0x10000);
        if (!g_fxo->is_init<ppu_function_manager>() && !g_fxo->init<ppu_function_manager>())
            throw std::runtime_error("P31 function manager initialization failed");
        auto& manager = g_fxo->get<ppu_function_manager>();
        if (manager.addr) throw std::runtime_error("P31 requires unused function manager address");
        struct TableCleanup {
            ppu_function_manager& manager;
            void release() {
                if (!manager.addr) return;
                const u32 address = manager.addr; manager.addr = 0;
                utils::memory_decommit(vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1), 0x8000);
            }
            ~TableCleanup() { release(); }
        } tableCleanup{manager};
        if (armsx3_ios_ppu_prepare_hle_table() != 0)
            throw std::runtime_error("P31 production HLE table preparation failed");
        const u32 tableAddress = manager.addr;
        if (tableAddress != 0x40000 ||
            !vm::check_addr(tableAddress, vm::page_readable | vm::page_executable, 0x10000))
            throw std::runtime_error("P31 HLE table allocation or flags mismatch");
        const auto* table = static_cast<const u8*>(vm::base(tableAddress));
        const std::vector<u8> tableBefore(table, table + 0x10000);
        const auto* cache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(tableAddress) * 2);
        std::vector<ppu_intrp_func_t> handlers;
        for (u32 i = 0; i < 0x10000 / 4; ++i) handlers.push_back(cache[i].fn);
        const auto created = cpu_thread::g_threads_created.load(), deleted = cpu_thread::g_threads_deleted.load();
        const u64 live = armsx3_ios_live_cpu_threads();
        // Independent golden layout: 64 bytes of pointer storage, 96 bytes
        // of aligned strings, and 32 bytes reserved for 17 exitspawn bytes.
        const u32 argvAddress = stackAddress + 0x7f40, envpAddress = argvAddress + 32;
        const u32 initialStack = stackAddress + 0x8000 - ppu_stack_start_offset - 192;
        const u32 frameAddress = initialStack - 128;
        struct Program {
            u32 begin, end, returnAddress, dataAddress, initialStack, stackAddress, entryOPD, argvAddress, envpAddress;
            u32 id = 0;
            int result = -99; bool tls = false, abi = false; std::atomic<bool> completed{false};
        } program{vm::read32(u32(elf.header.e_entry)), codeAddress + u32(sizeof(opcodes)), manager.func_addr(1, true), dataAddress, initialStack, stackAddress, u32(elf.header.e_entry), argvAddress, envpAddress};
        const auto executeLinked = +[](void* user, u32 descriptor, u32 invalidDescriptor) -> int {
            auto& program = *static_cast<Program*>(user);
            if (descriptor != program.dataAddress || vm::read32(descriptor) != program.begin + 96 ||
                vm::read32(program.dataAddress + 176) != descriptor ||
                vm::read32(program.dataAddress + 180) != invalidDescriptor)
                throw std::runtime_error("P31 callback did not receive active backpatched guest descriptor");
            program.result = -99; program.tls = false; program.abi = false; program.completed.store(false, std::memory_order_release);
            std::unique_ptr<named_thread<ppu_thread>> worker;
            {
                struct ConstructionID { u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                const ppu_thread_params params{static_cast<vm::addr_t>(program.stackAddress), 0x8000, 0, vm::_ref<ppu_func_opd_t>(program.entryOPD), 0, 0};
                worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS linked guest call probe", 1000);
            }
            struct StopWorker { named_thread<ppu_thread>& worker;
                ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                    worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); } } stop{*worker};
            if (worker->gpr[1] != program.stackAddress + 0x8000 - ppu_stack_start_offset ||
                worker->entry_func.addr != program.begin || worker->entry_func.rtoc != program.dataAddress + 32)
                throw std::runtime_error("P31 real worker constructor entry/stack mismatch");
            u32 argv = 0xaaaaaaaa, envp = 0xbbbbbbbb;
            const auto* stack = static_cast<const u8*>(vm::base(program.stackAddress));
            const std::vector<u8> beforeArguments(stack, stack + 0x10000);
            const auto firstArgument = Emu.argv[0];
            Emu.argv[0] = std::string(129, 'x');
            const int rejected = armsx3_ios_ppu_prepare_probe_arguments(worker.get(), &argv, &envp);
            Emu.argv[0] = firstArgument;
            if (rejected != -2 || argv != 0xaaaaaaaa || envp != 0xbbbbbbbb ||
                worker->gpr[1] != program.stackAddress + 0x8000 - ppu_stack_start_offset ||
                std::memcmp(stack, beforeArguments.data(), 0x10000))
                throw std::runtime_error("P31 oversized arguments were not rejected without mutation");
            if (armsx3_ios_ppu_prepare_probe_arguments(worker.get(), &argv, &envp) != 0 ||
                argv != program.argvAddress || envp != program.envpAddress || worker->gpr[1] != program.initialStack)
                throw std::runtime_error("P31 production executable argument packing failed");
            const std::vector<u8> packedArguments(stack, stack + 0x10000);
            u32 secondArgv = 0xaaaaaaaa, secondEnvp = 0xbbbbbbbb;
            if (armsx3_ios_ppu_prepare_probe_arguments(worker.get(), &secondArgv, &secondEnvp) != -1 ||
                secondArgv != 0xaaaaaaaa || secondEnvp != 0xbbbbbbbb ||
                worker->gpr[1] != program.initialStack || std::memcmp(stack, packedArguments.data(), 0x10000))
                throw std::runtime_error("P31 already prepared worker was not rejected without mutation");
            program.id = worker->id;
            const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                program.abi = context.gpr[3] == 3 && context.gpr[4] == program.argvAddress &&
                    context.gpr[5] == program.envpAddress && context.gpr[6] == 2 && context.gpr[7] == program.id &&
                    context.gpr[8] == 0 && context.gpr[9] == 0 && context.gpr[10] == 0 &&
                    context.gpr[11] == program.entryOPD && context.gpr[12] == 0x10000 && context.gpr[13] == 0 &&
                    context.gpr[1] == program.initialStack && context.entry_func.addr == program.begin &&
                    context.entry_func.rtoc == program.dataAddress + 32;
                if (!program.abi) {
                    program.result = -98; context.state += cpu_flag::exit;
                    program.completed.store(true, std::memory_order_release); return;
                }
                // Check the executable entry ABI first; the linked fixture then
                // uses r6/r10 as its result pointer and guest import slot.
                context.gpr[6] = program.dataAddress + 32;
                context.gpr[10] = program.dataAddress + 176;
                program.result = armsx3_ios_ppu_call_bounded(&context, program.begin, program.end,
                    program.dataAddress + 32, program.returnAddress, 64);
                context.state += cpu_flag::exit; program.completed.store(true, std::memory_order_release);
            };
            worker->cmd_list({
                {ppu_cmd::set_args, 8}, u64{Emu.argv.size()}, u64{argv}, u64{envp}, u64{Emu.envp.size()},
                u64{worker->id}, u64{0}, u64{0}, u64{0},
                {ppu_cmd::set_gpr, 11}, u64{program.entryOPD},
                {ppu_cmd::set_gpr, 12}, u64{0x10000},
                {ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
            const u32 address = program.begin;
            worker->cia = address + 0x900; worker->lr = address + 0x904;
            worker->gpr[2] = 0x13579;
            worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            ARMSX3StartupLog("P31 BEFORE executable entry register commands and linked guest BCTRL/BLR call");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire))
                throw std::runtime_error("P31 linked guest execution deadline exceeded");
            (*worker)();
            if (!program.tls || !program.abi || program.result != 21 || worker->gpr[3] != 42 ||
                worker->gpr[8] != program.dataAddress || worker->gpr[9] != program.dataAddress + 32 ||
                worker->gpr[11] != descriptor || worker->gpr[12] != program.begin + 96 ||
                worker->gpr[2] != 0x13579 || worker->gpr[1] != program.initialStack ||
                worker->cia != address + 0x900 || worker->lr != address + 0x904 || worker->state & cpu_flag::ret)
                throw std::runtime_error("P31 linked guest call result, TOC, stack or caller context mismatch");
            return 0;
        };
        const auto expect64 = [](std::vector<u8>& bytes, u32 offset, u64 value) {
            const be_t<u64> word = value; std::memcpy(bytes.data() + offset, &word, sizeof(word));
        };
        // Build expected bytes independently of the production packer.
        const std::array<u64, 8> pointers{stackAddress + 0x7f80, stackAddress + 0x7f90,
            stackAddress + 0x7fa0, 0, stackAddress + 0x7fc0, stackAddress + 0x7fd0, 0, 0};
        for (u32 i = 0; i < pointers.size(); ++i) expect64(expectedStack, 0x7f40 + i * 8, pointers[i]);
        std::memcpy(expectedStack.data() + 0x7f80, "probe", 6);
        std::memcpy(expectedStack.data() + 0x7f90, "123456789012345", 16);
        std::memcpy(expectedStack.data() + 0x7fa0, "1234567890123456", 17);
        std::memcpy(expectedStack.data() + 0x7fc0, "LANG=C", 7);
        expectedStack[0x7fd0] = 0;
        for (u32 i = 0; i < 17; ++i) expectedStack[0x7fef + i] = u8(0xa0 + i);
        // The production parameter handler itself rejects bad magic before linking.
        vm::write32(dataAddress + 260, 0);
        if (armsx3_ios_ppu_link_probe_image_and_call(&module, &elf.progs[2], executeLinked, &program) != -6)
            throw std::runtime_error("P31 production PRX parameter handler accepted bad magic");
        vm::write32(dataAddress + 260, control[1]);
        if (std::memcmp(data, expectedData.data(), 0x10000))
            throw std::runtime_error("P31 rejected PRX parameters mutated guest image");
        ARMSX3StartupLog("P31 PASS: executable PRX parameter handler rejects bad magic before linking");
        expect64(expectedData, 32, 42); expect64(expectedStack, frameAddress - stackAddress, initialStack);
        expect64(expectedStack, frameAddress - stackAddress + 16, program.returnAddress);
        expect64(expectedStack, frameAddress - stackAddress + 24, dataAddress + 32);
        for (unsigned repeat = 0; repeat < 2; ++repeat) {
            const int result = armsx3_ios_ppu_link_probe_image_and_call(&module, &elf.progs[2], executeLinked, &program);
            if (result != 0) {
                char error[160];
                std::snprintf(error, sizeof(error), "P31 executable PRX parameter linkage failed (wrapper result %d, iteration %u)", result, repeat + 1);
                throw std::runtime_error(error);
            }
            for (const auto& region : std::array<std::pair<u32, const std::vector<u8>*>, 3>{
                std::pair{codeAddress, &expectedCode}, std::pair{dataAddress, &expectedData}, std::pair{stackAddress, &expectedStack}})
                if (std::memcmp(vm::base(region.first), region.second->data(), 0x10000) ||
                    std::memcmp(vm::get_super_ptr(region.first), region.second->data(), 0x10000))
                    throw std::runtime_error("P31 loaded ELF/code/BSS/stack/import restoration or alias mismatch");
        }
        if (std::memcmp(table, tableBefore.data(), tableBefore.size()) ||
            std::memcmp(vm::get_super_ptr(tableAddress), tableBefore.data(), tableBefore.size()))
            throw std::runtime_error("P31 registration mutated HLE descriptors/aliases");
        for (u32 i = 0; i < handlers.size(); ++i)
            if (cache[i].fn != handlers[i]) throw std::runtime_error("P31 registration mutated HLE dispatch");
        for (u32 offset = 0; offset < 0x10000; offset += 0x1000)
            if (vm::check_addr(tableAddress + offset, vm::page_writable))
                throw std::runtime_error("P31 HLE descriptor page became writable");
        for (u32 i = 0; i < codeHandlers.size(); ++i)
            if (pageCache[i].fn != codeHandlers[i]) throw std::runtime_error("P31 guest execution mutated decoded code cache");
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 2 ||
            cpu_thread::g_threads_deleted.load() != deleted + 2)
            throw std::runtime_error("P31 registration changed CPU thread counters");
        tableCleanup.release();
        if (vm::dealloc(tableAddress, vm::main) != 0x10000 || vm::check_addr(tableAddress))
            throw std::runtime_error("P31 HLE table deallocation failed");
        segmentCleanup.release();
        for (u32 allocated : {stackAddress, dataAddress, codeAddress})
            if (vm::dealloc(allocated, vm::main) != 0x10000 || vm::check_addr(allocated))
                throw std::runtime_error("P31 guest deallocation failed");
        module.segs.clear(); module.addr_to_seg_index.clear();
        vm::close(); initialized = false;
        ARMSX3StartupLog("P31 PASS: production executable argv/envp/exitspawn packing, constructor entry OPD/stack, actual queued entry ABI registers, rejection without mutation, linked BCTRL/BLR result42, exact stack/aliases and repeated cleanup; global process/TLS initialization/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}

extern "C" int armsx3_ios_ppu_probe_tls_and_call(ppu_thread*, u32, u32, u32, int (*)(ppu_thread*, u32, void*), void*);
extern "C" int armsx3_ios_ppu_prepare_probe_arguments(ppu_thread*, u32*, u32*);
extern "C" int armsx3_ios_ppu_load_probe_image_segments(const ppu_exec_object*, ppu_module<lv2_obj>*);
extern "C" int armsx3_ios_ppu_link_probe_image_and_call(ppu_module<lv2_obj>*, const ppu_exec_object::prog_t*, int (*)(void*, u32, u32), void*);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_tls_bootstrap()
{
    ARMSX3StartupLog("P32 BEFORE production TLS memory bootstrap and linked guest TLS read");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P32 requires stopped emulator");
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
        if (!g_fxo->is_init() ||
            (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>()))
            throw std::runtime_error("P32 fixed objects/interpreter unavailable");
        struct Arguments {
            std::vector<std::string> argv = Emu.argv, envp = Emu.envp;
            std::vector<u8> data = Emu.data;
            ~Arguments() { Emu.argv = std::move(argv); Emu.envp = std::move(envp); Emu.data = std::move(data); }
        } arguments;
        Emu.argv = {"probe", "123456789012345", "1234567890123456"};
        Emu.envp = {"LANG=C", ""};
        Emu.data.resize(17);
        for (u32 i = 0; i < Emu.data.size(); ++i) Emu.data[i] = u8(0xa0 + i);
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x90000))
            throw std::runtime_error("P32 main memory block unavailable");
        const u32 address = 0x10000, codeAddress = address, dataAddress = 0x20000, stackAddress = 0x30000;
        using namespace ppu_instructions;
        using namespace ppu_instructions::implicts;
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        std::array<u32, 27> opcodes; opcodes.fill(0x60000000); // padding NOPs
        const std::array<u32, 17> caller{MFLR(0), STDU(1, 1, -128), STD(0, 1, 16), STD(2, 1, 24),
            ADDI(3, 0, 35), dform(32, 11, 10, 0), dform(32, 12, 11, 0), dform(32, 2, 11, 4),
            MTCTR(12), BCTRL(), LD(2, 1, 24), dform(24, 2, 9, 0), STD(3, 6, 0),
            LD(0, 1, 16), ADDI(1, 1, 128), MTLR(0), BLR()};
        for (u32 i = 0; i < caller.size(); ++i) opcodes[i] = caller[i];
        opcodes[24] = dform(34, 3, 13, -0x7000); opcodes[25] = ADDI(3, 3, -63); opcodes[26] = BLR();
        ppu_exec_object::ehdr_t header{};
        header.e_magic = "\177ELF"_u32; header.e_class = 2; header.e_data = 2;
        header.e_curver = 1; header.e_os_abi = elf_os::lv2; header.e_type = elf_type::exec;
        header.e_machine = elf_machine::ppc64; header.e_version = 1;
        header.e_entry = dataAddress + 8; header.e_phoff = sizeof(header);
        header.e_ehsize = sizeof(header); header.e_phentsize = sizeof(ppu_exec_object::phdr_t); header.e_phnum = 3;
        std::array<ppu_exec_object::phdr_t, 3> segments{};
        segments[0].p_type = 1; segments[0].p_flags = 5; segments[0].p_offset = 0x100;
        segments[0].p_vaddr = codeAddress; segments[0].p_filesz = sizeof(opcodes);
        segments[0].p_memsz = 0x10000; segments[0].p_align = 0x100;
        segments[1].p_type = 1; segments[1].p_flags = 6; segments[1].p_offset = 0x200;
        segments[1].p_vaddr = dataAddress; segments[1].p_filesz = 296;
        segments[1].p_memsz = 0x10000; segments[1].p_align = 0x100;
        segments[2].p_type = 0x60000002; segments[2].p_offset = 0x300;
        segments[2].p_vaddr = dataAddress + 256; segments[2].p_filesz = 40;
        segments[2].p_memsz = 40; segments[2].p_align = 4;
        std::vector<u8> fixture(0x328, 0);
        std::memcpy(fixture.data(), &header, sizeof(header));
        std::memcpy(fixture.data() + sizeof(header), segments.data(), sizeof(segments));
        const auto fileWord = [&](u32 offset, u32 value) { const be_t<u32> word = value;
            std::memcpy(fixture.data() + offset, &word, 4); };
        for (u32 i = 0; i < opcodes.size(); ++i) fileWord(0x100 + i * 4, opcodes[i]);
        fileWord(0x200, codeAddress + 96); fileWord(0x204, dataAddress);
        fileWord(0x208, codeAddress); fileWord(0x20c, dataAddress + 32);
        fixture[0x240] = 44; fixture[0x247] = 2;
        fileWord(0x250, dataAddress + 128); fileWord(0x254, dataAddress + 160); fileWord(0x258, dataAddress + 176);
        std::memcpy(fixture.data() + 0x280, "iOSProbe", 9);
        fileWord(0x2a0, 0x49524e31); fileWord(0x2a4, 0x49524e32);
        fileWord(0x2b0, codeAddress); fileWord(0x2b4, codeAddress);
        fixture[0x2c0] = 44; fixture[0x2c5] = 1; fixture[0x2c7] = 1;
        fileWord(0x2d0, dataAddress + 128); fileWord(0x2d4, dataAddress + 160);
        fileWord(0x2d8, dataAddress + 236); fileWord(0x2ec, dataAddress);
        const std::array<u32, 10> control{40, 0x1b434cec, 0, 0, dataAddress + 192,
            dataAddress + 236, dataAddress + 64, dataAddress + 108, 0, 0};
        for (u32 i = 0; i < control.size(); ++i) fileWord(0x300 + i * 4, control[i]);
        const auto stream = fs::make_stream(fixture);
        ppu_exec_object elf(stream);
        ppu_module<lv2_obj> module;
        module.name = "iOS loaded ELF linkage probe";
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 3 ||
            armsx3_ios_ppu_load_probe_image_segments(&elf, &module) != 0)
            throw std::runtime_error("P32 production ELF segment loading failed");
        const std::array<u8, 20> expectedHash{0x42, 0x57, 0x93, 0xd5, 0x02, 0xcd, 0x9f, 0x87, 0x3d, 0x85, 0x9a, 0xe7, 0x52, 0xc1, 0xdd, 0x2f, 0x99, 0xd0, 0x40, 0xc3};
        if (std::memcmp(module.sha1, expectedHash.data(), expectedHash.size()))
            throw std::runtime_error("P32 production ELF hash mismatch");
        std::vector<u8> expectedCode(0x10000, 0), expectedData(0x10000, 0);
        std::memcpy(expectedCode.data(), fixture.data() + 0x100, sizeof(opcodes));
        std::memcpy(expectedData.data(), fixture.data() + 0x200, 296);
        auto* guest = static_cast<u8*>(vm::base(codeAddress));
        auto* data = static_cast<u8*>(vm::base(dataAddress));
        if (std::memcmp(guest, expectedCode.data(), 0x10000) || std::memcmp(data, expectedData.data(), 0x10000) ||
            module.segs.size() != 2 || module.addr_to_seg_index.at(codeAddress) != 0 ||
            module.addr_to_seg_index.at(dataAddress) != 1)
            throw std::runtime_error("P32 loaded ELF contents/BSS/metadata mismatch");
        // Prepare exact fixture blocks from the production-loaded ELF segments.
        // Global process initialization and main-thread admission remain pending.
        ppu_function callerFunction{};
        callerFunction.addr = codeAddress; callerFunction.toc = dataAddress + 32; callerFunction.size = 68;
        callerFunction.blocks.emplace(codeAddress, 68);
        ppu_function calleeFunction{};
        calleeFunction.addr = codeAddress + 96; calleeFunction.toc = dataAddress; calleeFunction.size = 12;
        calleeFunction.blocks.emplace(codeAddress + 96, 12);
        module.funcs.push_back(std::move(callerFunction)); module.funcs.push_back(std::move(calleeFunction));
        struct SegmentCacheCleanup {
            u8* pointer; bool active = false;
            void release() { if (active) { utils::memory_decommit(pointer, 0x8000); active = false; } }
            ~SegmentCacheCleanup() { release(); }
        } segmentCleanup{vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1)};
        segmentCleanup.active = true;
        auto& interpreter = g_fxo->get<ppu_interpreter_rt>();
        const auto* codeCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(codeAddress) * 2);
        const auto fallback = codeCache[0].fn;
        if (armsx3_ios_ppu_prepare_module(&module) != 0)
            throw std::runtime_error("P32 static caller/callee module preparation failed");
        for (u32 i = 0; i < opcodes.size(); ++i) {
            const auto expected = i < 17 || i >= 24 ? interpreter.decode(opcodes[i]) : fallback;
            if (codeCache[i].fn != expected || ((i < 17 || i >= 24) && codeCache[i].fn == fallback))
                throw std::runtime_error("P32 caller/callee instruction decoding mismatch");
        }
        const auto* pageCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(address) * 2);
        std::vector<ppu_intrp_func_t> codeHandlers;
        for (u32 i = 0; i < 0x10000 / 4; ++i) codeHandlers.push_back(pageCache[i].fn);
        if (vm::alloc(0x10000, vm::main, 0x10000) != stackAddress)
            throw std::runtime_error("P32 worker stack allocation failed");
        const auto* stack = static_cast<const u8*>(vm::base(stackAddress));
        std::vector<u8> expectedStack(stack, stack + 0x10000);
        if (!g_fxo->is_init<ppu_function_manager>() && !g_fxo->init<ppu_function_manager>())
            throw std::runtime_error("P32 function manager initialization failed");
        auto& manager = g_fxo->get<ppu_function_manager>();
        if (manager.addr) throw std::runtime_error("P32 requires unused function manager address");
        struct TableCleanup {
            ppu_function_manager& manager;
            void release() {
                if (!manager.addr) return;
                const u32 address = manager.addr; manager.addr = 0;
                utils::memory_decommit(vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1), 0x8000);
            }
            ~TableCleanup() { release(); }
        } tableCleanup{manager};
        if (armsx3_ios_ppu_prepare_hle_table() != 0)
            throw std::runtime_error("P32 production HLE table preparation failed");
        const u32 tableAddress = manager.addr;
        if (tableAddress != 0x40000 ||
            !vm::check_addr(tableAddress, vm::page_readable | vm::page_executable, 0x10000))
            throw std::runtime_error("P32 HLE table allocation or flags mismatch");
        const auto* table = static_cast<const u8*>(vm::base(tableAddress));
        const std::vector<u8> tableBefore(table, table + 0x10000);
        const auto* cache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(tableAddress) * 2);
        std::vector<ppu_intrp_func_t> handlers;
        for (u32 i = 0; i < 0x10000 / 4; ++i) handlers.push_back(cache[i].fn);
        const auto created = cpu_thread::g_threads_created.load(), deleted = cpu_thread::g_threads_deleted.load();
        const u64 live = armsx3_ios_live_cpu_threads();
        // Independent golden layout: 64 bytes of pointer storage, 96 bytes
        // of aligned strings, and 32 bytes reserved for 17 exitspawn bytes.
        const u32 argvAddress = stackAddress + 0x7f40, envpAddress = argvAddress + 32;
        const u32 initialStack = stackAddress + 0x8000 - ppu_stack_start_offset - 192;
        const u32 frameAddress = initialStack - 128;
        struct Program {
            u32 begin, end, returnAddress, dataAddress, initialStack, stackAddress, entryOPD, argvAddress, envpAddress;
            u32 id = 0;
            int result = -99; bool tls = false, abi = false, tlsMemory = false; std::atomic<bool> completed{false};
        } program{vm::read32(u32(elf.header.e_entry)), codeAddress + u32(sizeof(opcodes)), manager.func_addr(1, true), dataAddress, initialStack, stackAddress, u32(elf.header.e_entry), argvAddress, envpAddress};
        const auto executeLinked = +[](void* user, u32 descriptor, u32 invalidDescriptor) -> int {
            auto& program = *static_cast<Program*>(user);
            if (descriptor != program.dataAddress || vm::read32(descriptor) != program.begin + 96 ||
                vm::read32(program.dataAddress + 176) != descriptor ||
                vm::read32(program.dataAddress + 180) != invalidDescriptor)
                throw std::runtime_error("P32 callback did not receive active backpatched guest descriptor");
            program.result = -99; program.tls = false; program.abi = false; program.tlsMemory = false; program.completed.store(false, std::memory_order_release);
            std::unique_ptr<named_thread<ppu_thread>> worker;
            {
                struct ConstructionID { u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                const ppu_thread_params params{static_cast<vm::addr_t>(program.stackAddress), 0x8000, 0, vm::_ref<ppu_func_opd_t>(program.entryOPD), 0, 0};
                worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS linked guest call probe", 1000);
            }
            struct StopWorker { named_thread<ppu_thread>& worker;
                ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                    worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); } } stop{*worker};
            if (worker->gpr[1] != program.stackAddress + 0x8000 - ppu_stack_start_offset ||
                worker->entry_func.addr != program.begin || worker->entry_func.rtoc != program.dataAddress + 32)
                throw std::runtime_error("P32 real worker constructor entry/stack mismatch");
            u32 argv = 0xaaaaaaaa, envp = 0xbbbbbbbb;
            const auto* stack = static_cast<const u8*>(vm::base(program.stackAddress));
            const std::vector<u8> beforeArguments(stack, stack + 0x10000);
            const auto firstArgument = Emu.argv[0];
            Emu.argv[0] = std::string(129, 'x');
            const int rejected = armsx3_ios_ppu_prepare_probe_arguments(worker.get(), &argv, &envp);
            Emu.argv[0] = firstArgument;
            if (rejected != -2 || argv != 0xaaaaaaaa || envp != 0xbbbbbbbb ||
                worker->gpr[1] != program.stackAddress + 0x8000 - ppu_stack_start_offset ||
                std::memcmp(stack, beforeArguments.data(), 0x10000))
                throw std::runtime_error("P32 oversized arguments were not rejected without mutation");
            if (armsx3_ios_ppu_prepare_probe_arguments(worker.get(), &argv, &envp) != 0 ||
                argv != program.argvAddress || envp != program.envpAddress || worker->gpr[1] != program.initialStack)
                throw std::runtime_error("P32 production executable argument packing failed");
            const std::vector<u8> packedArguments(stack, stack + 0x10000);
            u32 secondArgv = 0xaaaaaaaa, secondEnvp = 0xbbbbbbbb;
            if (armsx3_ios_ppu_prepare_probe_arguments(worker.get(), &secondArgv, &secondEnvp) != -1 ||
                secondArgv != 0xaaaaaaaa || secondEnvp != 0xbbbbbbbb ||
                worker->gpr[1] != program.initialStack || std::memcmp(stack, packedArguments.data(), 0x10000))
                throw std::runtime_error("P32 already prepared worker was not rejected without mutation");
            program.id = worker->id;
            const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                program.abi = context.gpr[3] == 3 && context.gpr[4] == program.argvAddress &&
                    context.gpr[5] == program.envpAddress && context.gpr[6] == 2 && context.gpr[7] == program.id &&
                    context.gpr[8] == program.dataAddress + 128 && context.gpr[9] == 9 && context.gpr[10] == 64 &&
                    context.gpr[11] == program.entryOPD && context.gpr[12] == 0x10000 && context.gpr[13] == 0 &&
                    context.gpr[1] == program.initialStack && context.entry_func.addr == program.begin &&
                    context.entry_func.rtoc == program.dataAddress + 32;
                if (!program.abi) {
                    program.result = -98; context.state += cpu_flag::exit;
                    program.completed.store(true, std::memory_order_release); return;
                }
                const auto callWithTLS = +[](ppu_thread* worker, u32 pool, void* user) -> int {
                    auto& program = *static_cast<Program*>(user);
                    std::vector<u8> expected(0x40000, 0);
                    for (u32 i = 0; i < 3; ++i)
                        std::memcpy(expected.data() + 0x60 + i * 0x70, "iOSProbe", 9);
                    if (pool != 0x50000 || worker->gpr[13] != pool + 0x7060 ||
                        std::memcmp(vm::base(pool), expected.data(), expected.size()) ||
                        std::memcmp(vm::get_super_ptr(pool), expected.data(), expected.size()))
                        throw std::runtime_error("P32 TLS image/system area/BSS/slot reuse mismatch");
                    // The callee reads byte 'i' through r13-0x7000 and adds -63
                    // to return42. This uses the production-initialized TLS.
                    worker->gpr[6] = program.dataAddress + 32;
                    worker->gpr[10] = program.dataAddress + 176;
                    const int result = armsx3_ios_ppu_call_bounded(worker, program.begin, program.end,
                        program.dataAddress + 32, program.returnAddress, 64);
                    if (worker->gpr[13] != pool + 0x7060 ||
                        std::memcmp(vm::base(pool), expected.data(), expected.size()) ||
                        std::memcmp(vm::get_super_ptr(pool), expected.data(), expected.size()))
                        throw std::runtime_error("P32 linked guest execution changed TLS image/BSS/aliases");
                    program.tlsMemory = true;
                    return result;
                };
                // Invalid TLS image sizes must be rejected before allocation.
                if (armsx3_ios_ppu_probe_tls_and_call(&context, program.dataAddress + 128, 10, 64, callWithTLS, &program) != -1 ||
                    context.gpr[13] || vm::check_addr(0x50000)) {
                    program.result = -97; context.state += cpu_flag::exit;
                    program.completed.store(true, std::memory_order_release); return;
                }
                program.result = armsx3_ios_ppu_probe_tls_and_call(&context,
                    program.dataAddress + 128, 9, 64, callWithTLS, &program);
                if (context.gpr[13] || vm::check_addr(0x50000)) program.result = -96;
                context.state += cpu_flag::exit; program.completed.store(true, std::memory_order_release);
            };
            worker->cmd_list({
                {ppu_cmd::set_args, 8}, u64{Emu.argv.size()}, u64{argv}, u64{envp}, u64{Emu.envp.size()},
                u64{worker->id}, u64{program.dataAddress + 128}, u64{9}, u64{64},
                {ppu_cmd::set_gpr, 11}, u64{program.entryOPD},
                {ppu_cmd::set_gpr, 12}, u64{0x10000},
                {ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
            const u32 address = program.begin;
            worker->cia = address + 0x900; worker->lr = address + 0x904;
            worker->gpr[2] = 0x13579;
            worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            ARMSX3StartupLog("P32 BEFORE production TLS pool/copy/zero/slot reuse and guest r13-relative read");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire))
                throw std::runtime_error("P32 linked guest execution deadline exceeded");
            (*worker)();
            if (!program.tls || !program.abi || !program.tlsMemory || program.result != 21 || worker->gpr[3] != 42 ||
                worker->gpr[8] != program.dataAddress + 128 || worker->gpr[9] != program.dataAddress + 32 ||
                worker->gpr[11] != descriptor || worker->gpr[12] != program.begin + 96 ||
                worker->gpr[2] != 0x13579 || worker->gpr[1] != program.initialStack ||
                worker->gpr[13] || worker->cia != address + 0x900 || worker->lr != address + 0x904 || worker->state & cpu_flag::ret)
            {
                char error[180];
                std::snprintf(error, sizeof(error), "P32 TLS-linked execution mismatch (wrapper result %d, worker TLS %d, entry ABI %d, TLS memory %d)",
                    program.result, program.tls, program.abi, program.tlsMemory);
                throw std::runtime_error(error);
            }
            return 0;
        };
        const auto expect64 = [](std::vector<u8>& bytes, u32 offset, u64 value) {
            const be_t<u64> word = value; std::memcpy(bytes.data() + offset, &word, sizeof(word));
        };
        // Build expected bytes independently of the production packer.
        const std::array<u64, 8> pointers{stackAddress + 0x7f80, stackAddress + 0x7f90,
            stackAddress + 0x7fa0, 0, stackAddress + 0x7fc0, stackAddress + 0x7fd0, 0, 0};
        for (u32 i = 0; i < pointers.size(); ++i) expect64(expectedStack, 0x7f40 + i * 8, pointers[i]);
        std::memcpy(expectedStack.data() + 0x7f80, "probe", 6);
        std::memcpy(expectedStack.data() + 0x7f90, "123456789012345", 16);
        std::memcpy(expectedStack.data() + 0x7fa0, "1234567890123456", 17);
        std::memcpy(expectedStack.data() + 0x7fc0, "LANG=C", 7);
        expectedStack[0x7fd0] = 0;
        for (u32 i = 0; i < 17; ++i) expectedStack[0x7fef + i] = u8(0xa0 + i);
        // The production parameter handler itself rejects bad magic before linking.
        vm::write32(dataAddress + 260, 0);
        if (armsx3_ios_ppu_link_probe_image_and_call(&module, &elf.progs[2], executeLinked, &program) != -6)
            throw std::runtime_error("P32 production PRX parameter handler accepted bad magic");
        vm::write32(dataAddress + 260, control[1]);
        if (std::memcmp(data, expectedData.data(), 0x10000))
            throw std::runtime_error("P32 rejected PRX parameters mutated guest image");
        ARMSX3StartupLog("P32 PASS: executable PRX parameter handler rejects bad magic before linking");
        expect64(expectedData, 32, 42); expect64(expectedStack, frameAddress - stackAddress, initialStack);
        expect64(expectedStack, frameAddress - stackAddress + 16, program.returnAddress);
        expect64(expectedStack, frameAddress - stackAddress + 24, dataAddress + 32);
        for (unsigned repeat = 0; repeat < 2; ++repeat) {
            const int result = armsx3_ios_ppu_link_probe_image_and_call(&module, &elf.progs[2], executeLinked, &program);
            if (result != 0) {
                char error[160];
                std::snprintf(error, sizeof(error), "P32 executable PRX parameter linkage failed (wrapper result %d, iteration %u)", result, repeat + 1);
                throw std::runtime_error(error);
            }
            for (u32 address = 0x50000; address < 0x90000; address += 0x1000)
                if (vm::check_addr(address)) throw std::runtime_error("P32 TLS pool remains mapped after worker cleanup");
            for (const auto& region : std::array<std::pair<u32, const std::vector<u8>*>, 3>{
                std::pair{codeAddress, &expectedCode}, std::pair{dataAddress, &expectedData}, std::pair{stackAddress, &expectedStack}})
                if (std::memcmp(vm::base(region.first), region.second->data(), 0x10000) ||
                    std::memcmp(vm::get_super_ptr(region.first), region.second->data(), 0x10000))
                    throw std::runtime_error("P32 loaded ELF/code/BSS/stack/import restoration or alias mismatch");
        }
        if (std::memcmp(table, tableBefore.data(), tableBefore.size()) ||
            std::memcmp(vm::get_super_ptr(tableAddress), tableBefore.data(), tableBefore.size()))
            throw std::runtime_error("P32 registration mutated HLE descriptors/aliases");
        for (u32 i = 0; i < handlers.size(); ++i)
            if (cache[i].fn != handlers[i]) throw std::runtime_error("P32 registration mutated HLE dispatch");
        for (u32 offset = 0; offset < 0x10000; offset += 0x1000)
            if (vm::check_addr(tableAddress + offset, vm::page_writable))
                throw std::runtime_error("P32 HLE descriptor page became writable");
        for (u32 i = 0; i < codeHandlers.size(); ++i)
            if (pageCache[i].fn != codeHandlers[i]) throw std::runtime_error("P32 guest execution mutated decoded code cache");
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 2 ||
            cpu_thread::g_threads_deleted.load() != deleted + 2)
            throw std::runtime_error("P32 registration changed CPU thread counters");
        tableCleanup.release();
        if (vm::dealloc(tableAddress, vm::main) != 0x10000 || vm::check_addr(tableAddress))
            throw std::runtime_error("P32 HLE table deallocation failed");
        segmentCleanup.release();
        for (u32 allocated : {stackAddress, dataAddress, codeAddress})
            if (vm::dealloc(allocated, vm::main) != 0x10000 || vm::check_addr(allocated))
                throw std::runtime_error("P32 guest deallocation failed");
        module.segs.clear(); module.addr_to_seg_index.clear();
        vm::close(); initialized = false;
        ARMSX3StartupLog("P32 PASS: shared production TLS memory bootstrap, main-thread r13, copied image/zero BSS/system areas, dirty slot clearing/free/reuse, actual guest TLS byte load/result42, exact arguments/stack/aliases and repeated pool cleanup; full process mutex/TLS HLE initialization/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}

extern "C" int armsx3_ios_ppu_probe_tls_and_call(ppu_thread*, u32, u32, u32, int (*)(ppu_thread*, u32, void*), void*);
extern "C" int armsx3_ios_ppu_prepare_probe_arguments(ppu_thread*, u32*, u32*);
extern "C" int armsx3_ios_ppu_load_probe_tls_image_segments(const ppu_exec_object*, ppu_module<lv2_obj>*, u32*, u32*, u32*);
extern "C" int armsx3_ios_ppu_read_probe_tls_header(const ppu_exec_object::prog_t*, u32*, u32*, u32*);
extern "C" int armsx3_ios_ppu_link_probe_image_and_call(ppu_module<lv2_obj>*, const ppu_exec_object::prog_t*, int (*)(void*, u32, u32), void*);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_elf_tls_header()
{
    ARMSX3StartupLog("P33 BEFORE production ELF TLS header, queued metadata and linked guest TLS read");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P33 requires stopped emulator");
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
        if (!g_fxo->is_init() ||
            (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>()))
            throw std::runtime_error("P33 fixed objects/interpreter unavailable");
        struct Arguments {
            std::vector<std::string> argv = Emu.argv, envp = Emu.envp;
            std::vector<u8> data = Emu.data;
            ~Arguments() { Emu.argv = std::move(argv); Emu.envp = std::move(envp); Emu.data = std::move(data); }
        } arguments;
        Emu.argv = {"probe", "123456789012345", "1234567890123456"};
        Emu.envp = {"LANG=C", ""};
        Emu.data.resize(17);
        for (u32 i = 0; i < Emu.data.size(); ++i) Emu.data[i] = u8(0xa0 + i);
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x90000))
            throw std::runtime_error("P33 main memory block unavailable");
        const u32 address = 0x10000, codeAddress = address, dataAddress = 0x20000, stackAddress = 0x30000;
        using namespace ppu_instructions;
        using namespace ppu_instructions::implicts;
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        std::array<u32, 27> opcodes; opcodes.fill(0x60000000); // padding NOPs
        const std::array<u32, 17> caller{MFLR(0), STDU(1, 1, -128), STD(0, 1, 16), STD(2, 1, 24),
            ADDI(3, 0, 35), dform(32, 11, 10, 0), dform(32, 12, 11, 0), dform(32, 2, 11, 4),
            MTCTR(12), BCTRL(), LD(2, 1, 24), dform(24, 2, 9, 0), STD(3, 6, 0),
            LD(0, 1, 16), ADDI(1, 1, 128), MTLR(0), BLR()};
        for (u32 i = 0; i < caller.size(); ++i) opcodes[i] = caller[i];
        opcodes[24] = dform(34, 3, 13, -0x7000); opcodes[25] = ADDI(3, 3, -63); opcodes[26] = BLR();
        ppu_exec_object::ehdr_t header{};
        header.e_magic = "\177ELF"_u32; header.e_class = 2; header.e_data = 2;
        header.e_curver = 1; header.e_os_abi = elf_os::lv2; header.e_type = elf_type::exec;
        header.e_machine = elf_machine::ppc64; header.e_version = 1;
        header.e_entry = dataAddress + 8; header.e_phoff = sizeof(header);
        header.e_ehsize = sizeof(header); header.e_phentsize = sizeof(ppu_exec_object::phdr_t); header.e_phnum = 4;
        std::array<ppu_exec_object::phdr_t, 4> segments{};
        segments[0].p_type = 1; segments[0].p_flags = 5; segments[0].p_offset = 0x200;
        segments[0].p_vaddr = codeAddress; segments[0].p_filesz = sizeof(opcodes);
        segments[0].p_memsz = 0x10000; segments[0].p_align = 0x100;
        segments[1].p_type = 1; segments[1].p_flags = 6; segments[1].p_offset = 0x300;
        segments[1].p_vaddr = dataAddress; segments[1].p_filesz = 296;
        segments[1].p_memsz = 0x10000; segments[1].p_align = 0x100;
        segments[2].p_type = 0x60000002; segments[2].p_offset = 0x400;
        segments[2].p_vaddr = dataAddress + 256; segments[2].p_filesz = 40;
        segments[2].p_memsz = 40; segments[2].p_align = 4;
        segments[3].p_type = 7; segments[3].p_flags = 4; segments[3].p_offset = 0x380;
        segments[3].p_vaddr = dataAddress + 128; segments[3].p_filesz = 9;
        segments[3].p_memsz = 64; segments[3].p_align = 16;
        static_assert(sizeof(header) + sizeof(segments) <= 0x200);
        std::vector<u8> fixture(0x428, 0);
        std::memcpy(fixture.data(), &header, sizeof(header));
        std::memcpy(fixture.data() + sizeof(header), segments.data(), sizeof(segments));
        const auto fileWord = [&](u32 offset, u32 value) { const be_t<u32> word = value;
            std::memcpy(fixture.data() + offset, &word, 4); };
        for (u32 i = 0; i < opcodes.size(); ++i) fileWord(0x200 + i * 4, opcodes[i]);
        fileWord(0x300, codeAddress + 96); fileWord(0x304, dataAddress);
        fileWord(0x308, codeAddress); fileWord(0x30c, dataAddress + 32);
        fixture[0x340] = 44; fixture[0x347] = 2;
        fileWord(0x350, dataAddress + 128); fileWord(0x354, dataAddress + 160); fileWord(0x358, dataAddress + 176);
        std::memcpy(fixture.data() + 0x380, "iOSProbe", 9);
        fileWord(0x3a0, 0x49524e31); fileWord(0x3a4, 0x49524e32);
        fileWord(0x3b0, codeAddress); fileWord(0x3b4, codeAddress);
        fixture[0x3c0] = 44; fixture[0x3c5] = 1; fixture[0x3c7] = 1;
        fileWord(0x3d0, dataAddress + 128); fileWord(0x3d4, dataAddress + 160);
        fileWord(0x3d8, dataAddress + 236); fileWord(0x3ec, dataAddress);
        const std::array<u32, 10> control{40, 0x1b434cec, 0, 0, dataAddress + 192,
            dataAddress + 236, dataAddress + 64, dataAddress + 108, 0, 0};
        for (u32 i = 0; i < control.size(); ++i) fileWord(0x400 + i * 4, control[i]);
        const auto stream = fs::make_stream(fixture);
        ppu_exec_object elf(stream);
        ppu_module<lv2_obj> module;
        module.name = "iOS loaded ELF linkage probe";
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 4)
            throw std::runtime_error("P33 four-header ELF parsing failed");
        const auto tlsHeader = elf.progs[3];
        // Production 64-bit overflow rejection must leave all outputs untouched.
        for (u32 field = 0; field < 7; ++field) {
            auto invalid = tlsHeader;
            if (field == 0) invalid.p_vaddr = u64{1} << 32;
            if (field == 1) invalid.p_filesz = u64{1} << 32;
            if (field == 2) invalid.p_memsz = u64{1} << 32;
            if (field == 3) invalid.p_filesz = 65;
            if (field == 4) invalid.p_memsz = 8;
            if (field == 5) invalid.p_vaddr = dataAddress + 129;
            if (field == 6) invalid.p_type = 1;
            u32 image = 0xaaaaaaaa, file = 0xbbbbbbbb, memory = 0xcccccccc;
            const int result = armsx3_ios_ppu_read_probe_tls_header(&invalid, &image, &file, &memory);
            if (result != (field < 3 ? -2 : field == 6 ? -1 : -3) ||
                image != 0xaaaaaaaa || file != 0xbbbbbbbb || memory != 0xcccccccc)
                throw std::runtime_error("P33 TLS header rejection changed metadata outputs");
        }
        u32 tlsImage = 0xaaaaaaaa, tlsFile = 0xbbbbbbbb, tlsMemory = 0xcccccccc;
        // Reject malformed TLS metadata/file bytes before mapping any LOAD page.
        for (u32 field = 0; field < 4; ++field) {
            if (field == 0) elf.progs[3].p_filesz = 65;
            if (field == 1) elf.progs[3].p_flags = 6;
            if (field == 2) elf.progs[3].bin.clear();
            if (field == 3) elf.progs[3].bin[0] ^= 1;
            const int result = armsx3_ios_ppu_load_probe_tls_image_segments(&elf, &module, &tlsImage, &tlsFile, &tlsMemory);
            elf.progs[3] = tlsHeader;
            if (result != -5 || !module.segs.empty() || !module.addr_to_seg_index.empty() ||
                vm::check_addr(codeAddress) || vm::check_addr(dataAddress) ||
                tlsImage != 0xaaaaaaaa || tlsFile != 0xbbbbbbbb || tlsMemory != 0xcccccccc)
                throw std::runtime_error("P33 malformed TLS program allocated memory or changed outputs");
        }
        if (armsx3_ios_ppu_load_probe_tls_image_segments(&elf, &module, &tlsImage, &tlsFile, &tlsMemory) != 0 ||
            tlsImage != dataAddress + 128 || tlsFile != 9 || tlsMemory != 64)
            throw std::runtime_error("P33 production ELF segment loading/TLS metadata failed");
        ARMSX3StartupLog("P33 PASS: ELF PT_TLS metadata and overflow/malformed rejection before allocation");
        const std::array<u8, 20> expectedHash{0xce, 0x2f, 0x30, 0x1a, 0x03, 0x4b, 0x0a, 0x56, 0xfe, 0x44, 0xa3, 0xda, 0xc2, 0x2d, 0xd5, 0x74, 0x99, 0x3c, 0xf8, 0xc8};
        if (std::memcmp(module.sha1, expectedHash.data(), expectedHash.size()))
            throw std::runtime_error("P33 production ELF hash mismatch");
        std::vector<u8> expectedCode(0x10000, 0), expectedData(0x10000, 0);
        std::memcpy(expectedCode.data(), fixture.data() + 0x200, sizeof(opcodes));
        std::memcpy(expectedData.data(), fixture.data() + 0x300, 296);
        auto* guest = static_cast<u8*>(vm::base(codeAddress));
        auto* data = static_cast<u8*>(vm::base(dataAddress));
        if (std::memcmp(guest, expectedCode.data(), 0x10000) || std::memcmp(data, expectedData.data(), 0x10000) ||
            module.segs.size() != 2 || module.addr_to_seg_index.at(codeAddress) != 0 ||
            module.addr_to_seg_index.at(dataAddress) != 1)
            throw std::runtime_error("P33 loaded ELF contents/BSS/metadata mismatch");
        // Prepare exact fixture blocks from the production-loaded ELF segments.
        // Global process initialization and main-thread admission remain pending.
        ppu_function callerFunction{};
        callerFunction.addr = codeAddress; callerFunction.toc = dataAddress + 32; callerFunction.size = 68;
        callerFunction.blocks.emplace(codeAddress, 68);
        ppu_function calleeFunction{};
        calleeFunction.addr = codeAddress + 96; calleeFunction.toc = dataAddress; calleeFunction.size = 12;
        calleeFunction.blocks.emplace(codeAddress + 96, 12);
        module.funcs.push_back(std::move(callerFunction)); module.funcs.push_back(std::move(calleeFunction));
        struct SegmentCacheCleanup {
            u8* pointer; bool active = false;
            void release() { if (active) { utils::memory_decommit(pointer, 0x8000); active = false; } }
            ~SegmentCacheCleanup() { release(); }
        } segmentCleanup{vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1)};
        segmentCleanup.active = true;
        auto& interpreter = g_fxo->get<ppu_interpreter_rt>();
        const auto* codeCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(codeAddress) * 2);
        const auto fallback = codeCache[0].fn;
        if (armsx3_ios_ppu_prepare_module(&module) != 0)
            throw std::runtime_error("P33 static caller/callee module preparation failed");
        for (u32 i = 0; i < opcodes.size(); ++i) {
            const auto expected = i < 17 || i >= 24 ? interpreter.decode(opcodes[i]) : fallback;
            if (codeCache[i].fn != expected || ((i < 17 || i >= 24) && codeCache[i].fn == fallback))
                throw std::runtime_error("P33 caller/callee instruction decoding mismatch");
        }
        const auto* pageCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(address) * 2);
        std::vector<ppu_intrp_func_t> codeHandlers;
        for (u32 i = 0; i < 0x10000 / 4; ++i) codeHandlers.push_back(pageCache[i].fn);
        if (vm::alloc(0x10000, vm::main, 0x10000) != stackAddress)
            throw std::runtime_error("P33 worker stack allocation failed");
        const auto* stack = static_cast<const u8*>(vm::base(stackAddress));
        std::vector<u8> expectedStack(stack, stack + 0x10000);
        if (!g_fxo->is_init<ppu_function_manager>() && !g_fxo->init<ppu_function_manager>())
            throw std::runtime_error("P33 function manager initialization failed");
        auto& manager = g_fxo->get<ppu_function_manager>();
        if (manager.addr) throw std::runtime_error("P33 requires unused function manager address");
        struct TableCleanup {
            ppu_function_manager& manager;
            void release() {
                if (!manager.addr) return;
                const u32 address = manager.addr; manager.addr = 0;
                utils::memory_decommit(vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1), 0x8000);
            }
            ~TableCleanup() { release(); }
        } tableCleanup{manager};
        if (armsx3_ios_ppu_prepare_hle_table() != 0)
            throw std::runtime_error("P33 production HLE table preparation failed");
        const u32 tableAddress = manager.addr;
        if (tableAddress != 0x40000 ||
            !vm::check_addr(tableAddress, vm::page_readable | vm::page_executable, 0x10000))
            throw std::runtime_error("P33 HLE table allocation or flags mismatch");
        const auto* table = static_cast<const u8*>(vm::base(tableAddress));
        const std::vector<u8> tableBefore(table, table + 0x10000);
        const auto* cache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(tableAddress) * 2);
        std::vector<ppu_intrp_func_t> handlers;
        for (u32 i = 0; i < 0x10000 / 4; ++i) handlers.push_back(cache[i].fn);
        const auto created = cpu_thread::g_threads_created.load(), deleted = cpu_thread::g_threads_deleted.load();
        const u64 live = armsx3_ios_live_cpu_threads();
        // Independent golden layout: 64 bytes of pointer storage, 96 bytes
        // of aligned strings, and 32 bytes reserved for 17 exitspawn bytes.
        const u32 argvAddress = stackAddress + 0x7f40, envpAddress = argvAddress + 32;
        const u32 initialStack = stackAddress + 0x8000 - ppu_stack_start_offset - 192;
        const u32 frameAddress = initialStack - 128;
        struct Program {
            u32 begin, end, returnAddress, dataAddress, initialStack, stackAddress, entryOPD, argvAddress, envpAddress;
            u32 tlsImage, tlsFileSize, tlsMemorySize;
            u32 id = 0;
            int result = -99; bool tls = false, abi = false, tlsMemory = false; std::atomic<bool> completed{false};
        } program{vm::read32(u32(elf.header.e_entry)), codeAddress + u32(sizeof(opcodes)), manager.func_addr(1, true), dataAddress, initialStack, stackAddress, u32(elf.header.e_entry), argvAddress, envpAddress, tlsImage, tlsFile, tlsMemory};
        const auto executeLinked = +[](void* user, u32 descriptor, u32 invalidDescriptor) -> int {
            auto& program = *static_cast<Program*>(user);
            if (descriptor != program.dataAddress || vm::read32(descriptor) != program.begin + 96 ||
                vm::read32(program.dataAddress + 176) != descriptor ||
                vm::read32(program.dataAddress + 180) != invalidDescriptor)
                throw std::runtime_error("P33 callback did not receive active backpatched guest descriptor");
            program.result = -99; program.tls = false; program.abi = false; program.tlsMemory = false; program.completed.store(false, std::memory_order_release);
            std::unique_ptr<named_thread<ppu_thread>> worker;
            {
                struct ConstructionID { u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                const ppu_thread_params params{static_cast<vm::addr_t>(program.stackAddress), 0x8000, 0, vm::_ref<ppu_func_opd_t>(program.entryOPD), 0, 0};
                worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS linked guest call probe", 1000);
            }
            struct StopWorker { named_thread<ppu_thread>& worker;
                ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                    worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); } } stop{*worker};
            if (worker->gpr[1] != program.stackAddress + 0x8000 - ppu_stack_start_offset ||
                worker->entry_func.addr != program.begin || worker->entry_func.rtoc != program.dataAddress + 32)
                throw std::runtime_error("P33 real worker constructor entry/stack mismatch");
            u32 argv = 0xaaaaaaaa, envp = 0xbbbbbbbb;
            const auto* stack = static_cast<const u8*>(vm::base(program.stackAddress));
            const std::vector<u8> beforeArguments(stack, stack + 0x10000);
            const auto firstArgument = Emu.argv[0];
            Emu.argv[0] = std::string(129, 'x');
            const int rejected = armsx3_ios_ppu_prepare_probe_arguments(worker.get(), &argv, &envp);
            Emu.argv[0] = firstArgument;
            if (rejected != -2 || argv != 0xaaaaaaaa || envp != 0xbbbbbbbb ||
                worker->gpr[1] != program.stackAddress + 0x8000 - ppu_stack_start_offset ||
                std::memcmp(stack, beforeArguments.data(), 0x10000))
                throw std::runtime_error("P33 oversized arguments were not rejected without mutation");
            if (armsx3_ios_ppu_prepare_probe_arguments(worker.get(), &argv, &envp) != 0 ||
                argv != program.argvAddress || envp != program.envpAddress || worker->gpr[1] != program.initialStack)
                throw std::runtime_error("P33 production executable argument packing failed");
            const std::vector<u8> packedArguments(stack, stack + 0x10000);
            u32 secondArgv = 0xaaaaaaaa, secondEnvp = 0xbbbbbbbb;
            if (armsx3_ios_ppu_prepare_probe_arguments(worker.get(), &secondArgv, &secondEnvp) != -1 ||
                secondArgv != 0xaaaaaaaa || secondEnvp != 0xbbbbbbbb ||
                worker->gpr[1] != program.initialStack || std::memcmp(stack, packedArguments.data(), 0x10000))
                throw std::runtime_error("P33 already prepared worker was not rejected without mutation");
            program.id = worker->id;
            const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                program.abi = context.gpr[3] == 3 && context.gpr[4] == program.argvAddress &&
                    context.gpr[5] == program.envpAddress && context.gpr[6] == 2 && context.gpr[7] == program.id &&
                    context.gpr[8] == program.tlsImage && context.gpr[9] == program.tlsFileSize && context.gpr[10] == program.tlsMemorySize &&
                    context.gpr[11] == program.entryOPD && context.gpr[12] == 0x10000 && context.gpr[13] == 0 &&
                    context.gpr[1] == program.initialStack && context.entry_func.addr == program.begin &&
                    context.entry_func.rtoc == program.dataAddress + 32;
                if (!program.abi) {
                    program.result = -98; context.state += cpu_flag::exit;
                    program.completed.store(true, std::memory_order_release); return;
                }
                const auto callWithTLS = +[](ppu_thread* worker, u32 pool, void* user) -> int {
                    auto& program = *static_cast<Program*>(user);
                    std::vector<u8> expected(0x40000, 0);
                    for (u32 i = 0; i < 3; ++i)
                        std::memcpy(expected.data() + 0x60 + i * 0x70, "iOSProbe", 9);
                    if (pool != 0x50000 || worker->gpr[13] != pool + 0x7060 ||
                        std::memcmp(vm::base(pool), expected.data(), expected.size()) ||
                        std::memcmp(vm::get_super_ptr(pool), expected.data(), expected.size()))
                        throw std::runtime_error("P33 TLS image/system area/BSS/slot reuse mismatch");
                    // The callee reads byte 'i' through r13-0x7000 and adds -63
                    // to return42. This uses the production-initialized TLS.
                    worker->gpr[6] = program.dataAddress + 32;
                    worker->gpr[10] = program.dataAddress + 176;
                    const int result = armsx3_ios_ppu_call_bounded(worker, program.begin, program.end,
                        program.dataAddress + 32, program.returnAddress, 64);
                    if (worker->gpr[13] != pool + 0x7060 ||
                        std::memcmp(vm::base(pool), expected.data(), expected.size()) ||
                        std::memcmp(vm::get_super_ptr(pool), expected.data(), expected.size()))
                        throw std::runtime_error("P33 linked guest execution changed TLS image/BSS/aliases");
                    program.tlsMemory = true;
                    return result;
                };
                // Invalid TLS image sizes must be rejected before allocation.
                if (armsx3_ios_ppu_probe_tls_and_call(&context, program.dataAddress + 128, 10, 64, callWithTLS, &program) != -1 ||
                    context.gpr[13] || vm::check_addr(0x50000)) {
                    program.result = -97; context.state += cpu_flag::exit;
                    program.completed.store(true, std::memory_order_release); return;
                }
                program.result = armsx3_ios_ppu_probe_tls_and_call(&context,
                    u32(context.gpr[8]), u32(context.gpr[9]), u32(context.gpr[10]), callWithTLS, &program);
                if (context.gpr[13] || vm::check_addr(0x50000)) program.result = -96;
                context.state += cpu_flag::exit; program.completed.store(true, std::memory_order_release);
            };
            worker->cmd_list({
                {ppu_cmd::set_args, 8}, u64{Emu.argv.size()}, u64{argv}, u64{envp}, u64{Emu.envp.size()},
                u64{worker->id}, u64{program.tlsImage}, u64{program.tlsFileSize}, u64{program.tlsMemorySize},
                {ppu_cmd::set_gpr, 11}, u64{program.entryOPD},
                {ppu_cmd::set_gpr, 12}, u64{0x10000},
                {ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
            const u32 address = program.begin;
            worker->cia = address + 0x900; worker->lr = address + 0x904;
            worker->gpr[2] = 0x13579;
            worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            ARMSX3StartupLog("P33 BEFORE production TLS pool/copy/zero/slot reuse and guest r13-relative read");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire))
                throw std::runtime_error("P33 linked guest execution deadline exceeded");
            (*worker)();
            if (!program.tls || !program.abi || !program.tlsMemory || program.result != 21 || worker->gpr[3] != 42 ||
                worker->gpr[8] != program.tlsImage || worker->gpr[9] != program.dataAddress + 32 ||
                worker->gpr[11] != descriptor || worker->gpr[12] != program.begin + 96 ||
                worker->gpr[2] != 0x13579 || worker->gpr[1] != program.initialStack ||
                worker->gpr[13] || worker->cia != address + 0x900 || worker->lr != address + 0x904 || worker->state & cpu_flag::ret)
            {
                char error[180];
                std::snprintf(error, sizeof(error), "P33 TLS-linked execution mismatch (wrapper result %d, worker TLS %d, entry ABI %d, TLS memory %d)",
                    program.result, program.tls, program.abi, program.tlsMemory);
                throw std::runtime_error(error);
            }
            return 0;
        };
        const auto expect64 = [](std::vector<u8>& bytes, u32 offset, u64 value) {
            const be_t<u64> word = value; std::memcpy(bytes.data() + offset, &word, sizeof(word));
        };
        // Build expected bytes independently of the production packer.
        const std::array<u64, 8> pointers{stackAddress + 0x7f80, stackAddress + 0x7f90,
            stackAddress + 0x7fa0, 0, stackAddress + 0x7fc0, stackAddress + 0x7fd0, 0, 0};
        for (u32 i = 0; i < pointers.size(); ++i) expect64(expectedStack, 0x7f40 + i * 8, pointers[i]);
        std::memcpy(expectedStack.data() + 0x7f80, "probe", 6);
        std::memcpy(expectedStack.data() + 0x7f90, "123456789012345", 16);
        std::memcpy(expectedStack.data() + 0x7fa0, "1234567890123456", 17);
        std::memcpy(expectedStack.data() + 0x7fc0, "LANG=C", 7);
        expectedStack[0x7fd0] = 0;
        for (u32 i = 0; i < 17; ++i) expectedStack[0x7fef + i] = u8(0xa0 + i);
        // The production parameter handler itself rejects bad magic before linking.
        vm::write32(dataAddress + 260, 0);
        if (armsx3_ios_ppu_link_probe_image_and_call(&module, &elf.progs[2], executeLinked, &program) != -6)
            throw std::runtime_error("P33 production PRX parameter handler accepted bad magic");
        vm::write32(dataAddress + 260, control[1]);
        if (std::memcmp(data, expectedData.data(), 0x10000))
            throw std::runtime_error("P33 rejected PRX parameters mutated guest image");
        ARMSX3StartupLog("P33 PASS: executable PRX parameter handler rejects bad magic before linking");
        expect64(expectedData, 32, 42); expect64(expectedStack, frameAddress - stackAddress, initialStack);
        expect64(expectedStack, frameAddress - stackAddress + 16, program.returnAddress);
        expect64(expectedStack, frameAddress - stackAddress + 24, dataAddress + 32);
        for (unsigned repeat = 0; repeat < 2; ++repeat) {
            const int result = armsx3_ios_ppu_link_probe_image_and_call(&module, &elf.progs[2], executeLinked, &program);
            if (result != 0) {
                char error[160];
                std::snprintf(error, sizeof(error), "P33 executable PRX parameter linkage failed (wrapper result %d, iteration %u)", result, repeat + 1);
                throw std::runtime_error(error);
            }
            for (u32 address = 0x50000; address < 0x90000; address += 0x1000)
                if (vm::check_addr(address)) throw std::runtime_error("P33 TLS pool remains mapped after worker cleanup");
            for (const auto& region : std::array<std::pair<u32, const std::vector<u8>*>, 3>{
                std::pair{codeAddress, &expectedCode}, std::pair{dataAddress, &expectedData}, std::pair{stackAddress, &expectedStack}})
                if (std::memcmp(vm::base(region.first), region.second->data(), 0x10000) ||
                    std::memcmp(vm::get_super_ptr(region.first), region.second->data(), 0x10000))
                    throw std::runtime_error("P33 loaded ELF/code/BSS/stack/import restoration or alias mismatch");
        }
        if (std::memcmp(table, tableBefore.data(), tableBefore.size()) ||
            std::memcmp(vm::get_super_ptr(tableAddress), tableBefore.data(), tableBefore.size()))
            throw std::runtime_error("P33 registration mutated HLE descriptors/aliases");
        for (u32 i = 0; i < handlers.size(); ++i)
            if (cache[i].fn != handlers[i]) throw std::runtime_error("P33 registration mutated HLE dispatch");
        for (u32 offset = 0; offset < 0x10000; offset += 0x1000)
            if (vm::check_addr(tableAddress + offset, vm::page_writable))
                throw std::runtime_error("P33 HLE descriptor page became writable");
        for (u32 i = 0; i < codeHandlers.size(); ++i)
            if (pageCache[i].fn != codeHandlers[i]) throw std::runtime_error("P33 guest execution mutated decoded code cache");
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 2 ||
            cpu_thread::g_threads_deleted.load() != deleted + 2)
            throw std::runtime_error("P33 registration changed CPU thread counters");
        tableCleanup.release();
        if (vm::dealloc(tableAddress, vm::main) != 0x10000 || vm::check_addr(tableAddress))
            throw std::runtime_error("P33 HLE table deallocation failed");
        segmentCleanup.release();
        for (u32 allocated : {stackAddress, dataAddress, codeAddress})
            if (vm::dealloc(allocated, vm::main) != 0x10000 || vm::check_addr(allocated))
                throw std::runtime_error("P33 guest deallocation failed");
        module.segs.clear(); module.addr_to_seg_index.clear();
        vm::close(); initialized = false;
        ARMSX3StartupLog("P33 PASS: shared production ELF PT_TLS parsing/overflow rejection, metadata from loaded header through queued registers into real TLS bootstrap, main-thread r13, copied image/zero BSS/system areas, dirty slot clearing/free/reuse, actual guest TLS byte load/result42, exact arguments/stack/aliases and repeated pool cleanup; full process mutex/TLS HLE initialization/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}

#include <algorithm>
extern "C" int armsx3_ios_ppu_probe_tls_and_call(ppu_thread*, u32, u32, u32, int (*)(ppu_thread*, u32, void*), void*);
extern "C" int armsx3_ios_ppu_prepare_probe_arguments(ppu_thread*, u32*, u32*);
extern "C" int armsx3_ios_ppu_load_probe_process_image_segments(const ppu_exec_object*, ppu_module<lv2_obj>*, u32*);
extern "C" int armsx3_ios_ppu_read_probe_process_parameters(const ppu_exec_object::prog_t*, u32*);
extern "C" int armsx3_ios_ppu_read_probe_tls_header(const ppu_exec_object::prog_t*, u32*, u32*, u32*);
extern "C" int armsx3_ios_ppu_link_probe_image_and_call(ppu_module<lv2_obj>*, const ppu_exec_object::prog_t*, int (*)(void*, u32, u32), void*);
extern "C" __attribute__((visibility("default"))) int armsx3_core_test_process_parameters()
{
    ARMSX3StartupLog("P34 BEFORE production executable process parameters, worker configuration and TLS guest call");
    bool initialized = false;
    try
    {
        if (!Emu.IsStopped()) throw std::runtime_error("P34 requires stopped emulator");
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
        if (!g_fxo->is_init() ||
            (!g_fxo->is_init<ppu_interpreter_rt>() && !g_fxo->init<ppu_interpreter_rt>()))
            throw std::runtime_error("P34 fixed objects/interpreter unavailable");
        struct Arguments {
            std::vector<std::string> argv = Emu.argv, envp = Emu.envp;
            std::vector<u8> data = Emu.data;
            ~Arguments() { Emu.argv = std::move(argv); Emu.envp = std::move(envp); Emu.data = std::move(data); }
        } arguments;
        Emu.argv = {"probe", "123456789012345", "1234567890123456"};
        Emu.envp = {"LANG=C", ""};
        Emu.data.resize(17);
        for (u32 i = 0; i < Emu.data.size(); ++i) Emu.data[i] = u8(0xa0 + i);
        vm::init(); initialized = true;
        if (!vm::reserve_map(vm::main, 0x10000, 0x90000))
            throw std::runtime_error("P34 main memory block unavailable");
        const u32 address = 0x10000, codeAddress = address, dataAddress = 0x20000, stackAddress = 0x30000;
        using namespace ppu_instructions;
        using namespace ppu_instructions::implicts;
        const auto dform = [](u32 op, u32 reg, u32 base, u32 imm) {
            return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff);
        };
        std::array<u32, 27> opcodes; opcodes.fill(0x60000000); // padding NOPs
        const std::array<u32, 17> caller{MFLR(0), STDU(1, 1, -128), STD(0, 1, 16), STD(2, 1, 24),
            ADDI(3, 0, 35), dform(32, 11, 10, 0), dform(32, 12, 11, 0), dform(32, 2, 11, 4),
            MTCTR(12), BCTRL(), LD(2, 1, 24), dform(24, 2, 9, 0), STD(3, 6, 0),
            LD(0, 1, 16), ADDI(1, 1, 128), MTLR(0), BLR()};
        for (u32 i = 0; i < caller.size(); ++i) opcodes[i] = caller[i];
        opcodes[24] = dform(34, 3, 13, -0x7000); opcodes[25] = ADDI(3, 3, -63); opcodes[26] = BLR();
        ppu_exec_object::ehdr_t header{};
        header.e_magic = "\177ELF"_u32; header.e_class = 2; header.e_data = 2;
        header.e_curver = 1; header.e_os_abi = elf_os::lv2; header.e_type = elf_type::exec;
        header.e_machine = elf_machine::ppc64; header.e_version = 1;
        header.e_entry = dataAddress + 8; header.e_phoff = sizeof(header);
        header.e_ehsize = sizeof(header); header.e_phentsize = sizeof(ppu_exec_object::phdr_t); header.e_phnum = 5;
        std::array<ppu_exec_object::phdr_t, 5> segments{};
        segments[0].p_type = 1; segments[0].p_flags = 5; segments[0].p_offset = 0x200;
        segments[0].p_vaddr = codeAddress; segments[0].p_filesz = sizeof(opcodes);
        segments[0].p_memsz = 0x10000; segments[0].p_align = 0x100;
        segments[1].p_type = 1; segments[1].p_flags = 6; segments[1].p_offset = 0x300;
        segments[1].p_vaddr = dataAddress; segments[1].p_filesz = 352;
        segments[1].p_memsz = 0x10000; segments[1].p_align = 0x100;
        segments[2].p_type = 0x60000002; segments[2].p_offset = 0x400;
        segments[2].p_vaddr = dataAddress + 256; segments[2].p_filesz = 40;
        segments[2].p_memsz = 40; segments[2].p_align = 4;
        segments[3].p_type = 7; segments[3].p_flags = 4; segments[3].p_offset = 0x380;
        segments[3].p_vaddr = dataAddress + 128; segments[3].p_filesz = 9;
        segments[3].p_memsz = 64; segments[3].p_align = 16;
        segments[4].p_type = 0x60000001; segments[4].p_offset = 0x440;
        segments[4].p_vaddr = dataAddress + 320; segments[4].p_filesz = 32;
        segments[4].p_memsz = 32; segments[4].p_align = 4;
        static_assert(sizeof(header) + sizeof(segments) <= 0x200);
        std::vector<u8> fixture(0x460, 0);
        std::memcpy(fixture.data(), &header, sizeof(header));
        std::memcpy(fixture.data() + sizeof(header), segments.data(), sizeof(segments));
        const auto fileWord = [&](u32 offset, u32 value) { const be_t<u32> word = value;
            std::memcpy(fixture.data() + offset, &word, 4); };
        for (u32 i = 0; i < opcodes.size(); ++i) fileWord(0x200 + i * 4, opcodes[i]);
        fileWord(0x300, codeAddress + 96); fileWord(0x304, dataAddress);
        fileWord(0x308, codeAddress); fileWord(0x30c, dataAddress + 32);
        fixture[0x340] = 44; fixture[0x347] = 2;
        fileWord(0x350, dataAddress + 128); fileWord(0x354, dataAddress + 160); fileWord(0x358, dataAddress + 176);
        std::memcpy(fixture.data() + 0x380, "iOSProbe", 9);
        fileWord(0x3a0, 0x49524e31); fileWord(0x3a4, 0x49524e32);
        fileWord(0x3b0, codeAddress); fileWord(0x3b4, codeAddress);
        fixture[0x3c0] = 44; fixture[0x3c5] = 1; fixture[0x3c7] = 1;
        fileWord(0x3d0, dataAddress + 128); fileWord(0x3d4, dataAddress + 160);
        fileWord(0x3d8, dataAddress + 236); fileWord(0x3ec, dataAddress);
        const std::array<u32, 10> control{40, 0x1b434cec, 0, 0, dataAddress + 192,
            dataAddress + 236, dataAddress + 64, dataAddress + 108, 0, 0};
        for (u32 i = 0; i < control.size(); ++i) fileWord(0x400 + i * 4, control[i]);
        const std::array<u32, 8> processWords{32, 0x13bcc5f6, 0x00330000, 0x00360001, 1100, 0x8000, 0x10000, 0};
        for (u32 i = 0; i < processWords.size(); ++i) fileWord(0x440 + i * 4, processWords[i]);
        const auto stream = fs::make_stream(fixture);
        ppu_exec_object elf(stream);
        ppu_module<lv2_obj> module;
        module.name = "iOS loaded ELF linkage probe";
        if (elf.get_error() != elf_error::ok || elf.progs.size() != 5)
            throw std::runtime_error("P34 five-header ELF parsing failed");
        const auto tlsHeader = elf.progs[3];
        // Production 64-bit overflow rejection must leave all outputs untouched.
        for (u32 field = 0; field < 7; ++field) {
            auto invalid = tlsHeader;
            if (field == 0) invalid.p_vaddr = u64{1} << 32;
            if (field == 1) invalid.p_filesz = u64{1} << 32;
            if (field == 2) invalid.p_memsz = u64{1} << 32;
            if (field == 3) invalid.p_filesz = 65;
            if (field == 4) invalid.p_memsz = 8;
            if (field == 5) invalid.p_vaddr = dataAddress + 129;
            if (field == 6) invalid.p_type = 1;
            u32 image = 0xaaaaaaaa, file = 0xbbbbbbbb, memory = 0xcccccccc;
            const int result = armsx3_ios_ppu_read_probe_tls_header(&invalid, &image, &file, &memory);
            if (result != (field < 3 ? -2 : field == 6 ? -1 : -3) ||
                image != 0xaaaaaaaa || file != 0xbbbbbbbb || memory != 0xcccccccc)
                throw std::runtime_error("P34 TLS header rejection changed metadata outputs");
        }
        std::array<u32, 8> processParameters; processParameters.fill(0xaaaaaaaa);
        const auto parametersUntouched = [&] { return std::all_of(processParameters.begin(), processParameters.end(),
            [](u32 value) { return value == 0xaaaaaaaau; }); };
        for (u32 field = 0; field < 4; ++field) {
            if (field == 0) elf.progs[3].p_filesz = 65;
            if (field == 1) elf.progs[3].p_flags = 6;
            if (field == 2) elf.progs[3].bin.clear();
            if (field == 3) elf.progs[3].bin[0] ^= 1;
            const int result = armsx3_ios_ppu_load_probe_process_image_segments(&elf, &module, processParameters.data());
            elf.progs[3] = tlsHeader;
            if (result != -5 || !module.segs.empty() || !module.addr_to_seg_index.empty() ||
                vm::check_addr(codeAddress) || vm::check_addr(dataAddress) || !parametersUntouched())
                throw std::runtime_error("P34 malformed TLS program allocated memory or changed outputs");
        }
        const auto processHeader = elf.progs[4];
        const auto processWord = [](ppu_exec_object::prog_t& prog, u32 index, u32 value) {
            const be_t<u32> word = value; std::memcpy(prog.bin.data() + index * 4, &word, 4);
        };
        // The production parser preserves defaults on bad magic/priority;
        // this bounded wrapper rejects any result outside its private shape.
        for (u32 field = 0; field < 8; ++field) {
            auto invalid = processHeader;
            if (field == 0) processWord(invalid, 1, 0);
            if (field == 1) processWord(invalid, 0, 8);
            if (field == 2) processWord(invalid, 3, 0x00360002);
            if (field == 3) processWord(invalid, 4, 3072);
            if (field == 4) processWord(invalid, 5, 0x100000);
            if (field == 5) processWord(invalid, 6, 0x100000);
            if (field == 6) processWord(invalid, 7, 1);
            if (field == 7) invalid.bin.resize(31);
            std::array<u32, 5> output; output.fill(0xbbbbbbbb);
            if (armsx3_ios_ppu_read_probe_process_parameters(&invalid, output.data()) != (field == 7 ? -1 : -3) ||
                !std::all_of(output.begin(), output.end(), [](u32 value) { return value == 0xbbbbbbbbu; }))
                throw std::runtime_error("P34 invalid process parameters changed outputs");
        }
        for (u32 field = 0; field < 3; ++field) {
            if (field == 0) processWord(elf.progs[4], 1, 0);
            if (field == 1) elf.progs[4].bin.resize(31);
            if (field == 2) processWord(elf.progs[4], 2, 1); // Valid parser fields, but inconsistent file bytes.
            const int result = armsx3_ios_ppu_load_probe_process_image_segments(&elf, &module, processParameters.data());
            elf.progs[4] = processHeader;
            if (result != -6 || !module.segs.empty() || !module.addr_to_seg_index.empty() ||
                vm::check_addr(codeAddress) || vm::check_addr(dataAddress) || !parametersUntouched())
                throw std::runtime_error("P34 malformed process program allocated memory or changed outputs");
        }
        if (armsx3_ios_ppu_load_probe_process_image_segments(&elf, &module, processParameters.data()) != 0 ||
            processParameters != std::array<u32, 8>{0x00360001, 1100, 0x8000, 0x10000, 0, dataAddress + 128, 9, 64})
            throw std::runtime_error("P34 production ELF process/TLS metadata and loading failed");
        const u32 tlsImage = processParameters[5], tlsFile = processParameters[6], tlsMemory = processParameters[7];
        ARMSX3StartupLog("P34 PASS: executable process parameters and TLS metadata, defaults/shape rejection before allocation");
        const std::array<u8, 20> expectedHash{0xd6, 0xf4, 0x5b, 0x20, 0xa4, 0xee, 0x9f, 0x75, 0x68, 0xd8, 0xd3, 0xfe, 0xad, 0x07, 0x7b, 0x85, 0x45, 0xff, 0x9d, 0x8d};
        if (std::memcmp(module.sha1, expectedHash.data(), expectedHash.size()))
            throw std::runtime_error("P34 production ELF hash mismatch");
        std::vector<u8> expectedCode(0x10000, 0), expectedData(0x10000, 0);
        std::memcpy(expectedCode.data(), fixture.data() + 0x200, sizeof(opcodes));
        std::memcpy(expectedData.data(), fixture.data() + 0x300, 352);
        auto* guest = static_cast<u8*>(vm::base(codeAddress));
        auto* data = static_cast<u8*>(vm::base(dataAddress));
        if (std::memcmp(guest, expectedCode.data(), 0x10000) || std::memcmp(data, expectedData.data(), 0x10000) ||
            module.segs.size() != 2 || module.addr_to_seg_index.at(codeAddress) != 0 ||
            module.addr_to_seg_index.at(dataAddress) != 1)
            throw std::runtime_error("P34 loaded ELF contents/BSS/metadata mismatch");
        // Prepare exact fixture blocks from the production-loaded ELF segments.
        // Global process initialization and main-thread admission remain pending.
        ppu_function callerFunction{};
        callerFunction.addr = codeAddress; callerFunction.toc = dataAddress + 32; callerFunction.size = 68;
        callerFunction.blocks.emplace(codeAddress, 68);
        ppu_function calleeFunction{};
        calleeFunction.addr = codeAddress + 96; calleeFunction.toc = dataAddress; calleeFunction.size = 12;
        calleeFunction.blocks.emplace(codeAddress + 96, 12);
        module.funcs.push_back(std::move(callerFunction)); module.funcs.push_back(std::move(calleeFunction));
        struct SegmentCacheCleanup {
            u8* pointer; bool active = false;
            void release() { if (active) { utils::memory_decommit(pointer, 0x8000); active = false; } }
            ~SegmentCacheCleanup() { release(); }
        } segmentCleanup{vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1)};
        segmentCleanup.active = true;
        auto& interpreter = g_fxo->get<ppu_interpreter_rt>();
        const auto* codeCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(codeAddress) * 2);
        const auto fallback = codeCache[0].fn;
        if (armsx3_ios_ppu_prepare_module(&module) != 0)
            throw std::runtime_error("P34 static caller/callee module preparation failed");
        for (u32 i = 0; i < opcodes.size(); ++i) {
            const auto expected = i < 17 || i >= 24 ? interpreter.decode(opcodes[i]) : fallback;
            if (codeCache[i].fn != expected || ((i < 17 || i >= 24) && codeCache[i].fn == fallback))
                throw std::runtime_error("P34 caller/callee instruction decoding mismatch");
        }
        const auto* pageCache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(address) * 2);
        std::vector<ppu_intrp_func_t> codeHandlers;
        for (u32 i = 0; i < 0x10000 / 4; ++i) codeHandlers.push_back(pageCache[i].fn);
        if (vm::alloc(0x10000, vm::main, 0x10000) != stackAddress)
            throw std::runtime_error("P34 worker stack allocation failed");
        const auto* stack = static_cast<const u8*>(vm::base(stackAddress));
        std::vector<u8> expectedStack(stack, stack + 0x10000);
        if (!g_fxo->is_init<ppu_function_manager>() && !g_fxo->init<ppu_function_manager>())
            throw std::runtime_error("P34 function manager initialization failed");
        auto& manager = g_fxo->get<ppu_function_manager>();
        if (manager.addr) throw std::runtime_error("P34 requires unused function manager address");
        struct TableCleanup {
            ppu_function_manager& manager;
            void release() {
                if (!manager.addr) return;
                const u32 address = manager.addr; manager.addr = 0;
                utils::memory_decommit(vm::g_exec_addr + vm::g_exec_addr_seg_offset + (address >> 1), 0x8000);
            }
            ~TableCleanup() { release(); }
        } tableCleanup{manager};
        if (armsx3_ios_ppu_prepare_hle_table() != 0)
            throw std::runtime_error("P34 production HLE table preparation failed");
        const u32 tableAddress = manager.addr;
        if (tableAddress != 0x40000 ||
            !vm::check_addr(tableAddress, vm::page_readable | vm::page_executable, 0x10000))
            throw std::runtime_error("P34 HLE table allocation or flags mismatch");
        const auto* table = static_cast<const u8*>(vm::base(tableAddress));
        const std::vector<u8> tableBefore(table, table + 0x10000);
        const auto* cache = reinterpret_cast<const ppu_intrp_func*>(vm::g_exec_addr + u64(tableAddress) * 2);
        std::vector<ppu_intrp_func_t> handlers;
        for (u32 i = 0; i < 0x10000 / 4; ++i) handlers.push_back(cache[i].fn);
        const auto created = cpu_thread::g_threads_created.load(), deleted = cpu_thread::g_threads_deleted.load();
        const u64 live = armsx3_ios_live_cpu_threads();
        // Independent golden layout: 64 bytes of pointer storage, 96 bytes
        // of aligned strings, and 32 bytes reserved for 17 exitspawn bytes.
        const u32 argvAddress = stackAddress + 0x7f40, envpAddress = argvAddress + 32;
        const u32 initialStack = stackAddress + processParameters[2] - ppu_stack_start_offset - 192;
        const u32 frameAddress = initialStack - 128;
        struct Program {
            u32 begin, end, returnAddress, dataAddress, initialStack, stackAddress, entryOPD, argvAddress, envpAddress;
            u32 tlsImage, tlsFileSize, tlsMemorySize, primaryPriority, primaryStackSize, mallocPageSize;
            u32 id = 0;
            int result = -99; bool tls = false, abi = false, tlsMemory = false; std::atomic<bool> completed{false};
        } program{vm::read32(u32(elf.header.e_entry)), codeAddress + u32(sizeof(opcodes)), manager.func_addr(1, true), dataAddress, initialStack, stackAddress, u32(elf.header.e_entry), argvAddress, envpAddress, tlsImage, tlsFile, tlsMemory, processParameters[1], processParameters[2], processParameters[3]};
        const auto executeLinked = +[](void* user, u32 descriptor, u32 invalidDescriptor) -> int {
            auto& program = *static_cast<Program*>(user);
            if (descriptor != program.dataAddress || vm::read32(descriptor) != program.begin + 96 ||
                vm::read32(program.dataAddress + 176) != descriptor ||
                vm::read32(program.dataAddress + 180) != invalidDescriptor)
                throw std::runtime_error("P34 callback did not receive active backpatched guest descriptor");
            program.result = -99; program.tls = false; program.abi = false; program.tlsMemory = false; program.completed.store(false, std::memory_order_release);
            std::unique_ptr<named_thread<ppu_thread>> worker;
            {
                struct ConstructionID { u32 previous = id_manager::g_id;
                    ConstructionID() { id_manager::g_id = ppu_thread::id_base; }
                    ~ConstructionID() { id_manager::g_id = previous; } } construction_id;
                const ppu_thread_params params{static_cast<vm::addr_t>(program.stackAddress), program.primaryStackSize, 0, vm::_ref<ppu_func_opd_t>(program.entryOPD), 0, 0};
                worker = std::make_unique<named_thread<ppu_thread>>(stx::launch_retainer{}, params, "iOS process metadata probe", program.primaryPriority);
            }
            struct StopWorker { named_thread<ppu_thread>& worker;
                ~StopWorker() { worker.state += cpu_flag::exit; worker.state.notify_one();
                    worker.cmd_notify.store(1); worker.cmd_notify.notify_one(); } } stop{*worker};
            if (worker->stack_size != program.primaryStackSize ||
                static_cast<s64>(worker->prio.load().prio) != program.primaryPriority || worker->gpr[1] != program.stackAddress + 0x8000 - ppu_stack_start_offset ||
                worker->entry_func.addr != program.begin || worker->entry_func.rtoc != program.dataAddress + 32)
                throw std::runtime_error("P34 real worker constructor entry/stack mismatch");
            u32 argv = 0xaaaaaaaa, envp = 0xbbbbbbbb;
            const auto* stack = static_cast<const u8*>(vm::base(program.stackAddress));
            const std::vector<u8> beforeArguments(stack, stack + 0x10000);
            const auto firstArgument = Emu.argv[0];
            Emu.argv[0] = std::string(129, 'x');
            const int rejected = armsx3_ios_ppu_prepare_probe_arguments(worker.get(), &argv, &envp);
            Emu.argv[0] = firstArgument;
            if (rejected != -2 || argv != 0xaaaaaaaa || envp != 0xbbbbbbbb ||
                worker->gpr[1] != program.stackAddress + 0x8000 - ppu_stack_start_offset ||
                std::memcmp(stack, beforeArguments.data(), 0x10000))
                throw std::runtime_error("P34 oversized arguments were not rejected without mutation");
            if (armsx3_ios_ppu_prepare_probe_arguments(worker.get(), &argv, &envp) != 0 ||
                argv != program.argvAddress || envp != program.envpAddress || worker->gpr[1] != program.initialStack)
                throw std::runtime_error("P34 production executable argument packing failed");
            const std::vector<u8> packedArguments(stack, stack + 0x10000);
            u32 secondArgv = 0xaaaaaaaa, secondEnvp = 0xbbbbbbbb;
            if (armsx3_ios_ppu_prepare_probe_arguments(worker.get(), &secondArgv, &secondEnvp) != -1 ||
                secondArgv != 0xaaaaaaaa || secondEnvp != 0xbbbbbbbb ||
                worker->gpr[1] != program.initialStack || std::memcmp(stack, packedArguments.data(), 0x10000))
                throw std::runtime_error("P34 already prepared worker was not rejected without mutation");
            program.id = worker->id;
            const ppu_intrp_func_t execute = +[](ppu_thread& context, ppu_opcode_t, be_t<u32>*, ppu_intrp_func*) {
                auto& program = *reinterpret_cast<Program*>(context.gpr[30]);
                program.tls = get_current_cpu_thread() == &context && thread_ctrl::get_current() != nullptr;
                program.abi = context.stack_size == program.primaryStackSize &&
                    static_cast<s64>(context.prio.load().prio) == program.primaryPriority && context.gpr[3] == 3 && context.gpr[4] == program.argvAddress &&
                    context.gpr[5] == program.envpAddress && context.gpr[6] == 2 && context.gpr[7] == program.id &&
                    context.gpr[8] == program.tlsImage && context.gpr[9] == program.tlsFileSize && context.gpr[10] == program.tlsMemorySize &&
                    context.gpr[11] == program.entryOPD && context.gpr[12] == program.mallocPageSize && context.gpr[13] == 0 &&
                    context.gpr[1] == program.initialStack && context.entry_func.addr == program.begin &&
                    context.entry_func.rtoc == program.dataAddress + 32;
                if (!program.abi) {
                    program.result = -98; context.state += cpu_flag::exit;
                    program.completed.store(true, std::memory_order_release); return;
                }
                const auto callWithTLS = +[](ppu_thread* worker, u32 pool, void* user) -> int {
                    auto& program = *static_cast<Program*>(user);
                    std::vector<u8> expected(0x40000, 0);
                    for (u32 i = 0; i < 3; ++i)
                        std::memcpy(expected.data() + 0x60 + i * 0x70, "iOSProbe", 9);
                    if (pool != 0x50000 || worker->gpr[13] != pool + 0x7060 ||
                        std::memcmp(vm::base(pool), expected.data(), expected.size()) ||
                        std::memcmp(vm::get_super_ptr(pool), expected.data(), expected.size()))
                        throw std::runtime_error("P34 TLS image/system area/BSS/slot reuse mismatch");
                    // The callee reads byte 'i' through r13-0x7000 and adds -63
                    // to return42. This uses the production-initialized TLS.
                    worker->gpr[6] = program.dataAddress + 32;
                    worker->gpr[10] = program.dataAddress + 176;
                    const int result = armsx3_ios_ppu_call_bounded(worker, program.begin, program.end,
                        program.dataAddress + 32, program.returnAddress, 64);
                    if (worker->gpr[13] != pool + 0x7060 ||
                        std::memcmp(vm::base(pool), expected.data(), expected.size()) ||
                        std::memcmp(vm::get_super_ptr(pool), expected.data(), expected.size()))
                        throw std::runtime_error("P34 linked guest execution changed TLS image/BSS/aliases");
                    program.tlsMemory = true;
                    return result;
                };
                // Invalid TLS image sizes must be rejected before allocation.
                if (armsx3_ios_ppu_probe_tls_and_call(&context, program.dataAddress + 128, 10, 64, callWithTLS, &program) != -1 ||
                    context.gpr[13] || vm::check_addr(0x50000)) {
                    program.result = -97; context.state += cpu_flag::exit;
                    program.completed.store(true, std::memory_order_release); return;
                }
                program.result = armsx3_ios_ppu_probe_tls_and_call(&context,
                    u32(context.gpr[8]), u32(context.gpr[9]), u32(context.gpr[10]), callWithTLS, &program);
                if (context.gpr[13] || vm::check_addr(0x50000)) program.result = -96;
                context.state += cpu_flag::exit; program.completed.store(true, std::memory_order_release);
            };
            worker->cmd_list({
                {ppu_cmd::set_args, 8}, u64{Emu.argv.size()}, u64{argv}, u64{envp}, u64{Emu.envp.size()},
                u64{worker->id}, u64{program.tlsImage}, u64{program.tlsFileSize}, u64{program.tlsMemorySize},
                {ppu_cmd::set_gpr, 11}, u64{program.entryOPD},
                {ppu_cmd::set_gpr, 12}, u64{program.mallocPageSize},
                {ppu_cmd::ptr_call, 0}, std::bit_cast<u64>(execute)});
            const u32 address = program.begin;
            worker->cia = address + 0x900; worker->lr = address + 0x904;
            worker->gpr[2] = 0x13579;
            worker->gpr[30] = u64(reinterpret_cast<uintptr_t>(&program));
            worker->state -= cpu_flag::stop + cpu_flag::exit + cpu_flag::suspend + cpu_flag::memory + cpu_flag::wait;
            ARMSX3StartupLog("P34 BEFORE production TLS pool/copy/zero/slot reuse and guest r13-relative read");
            *worker = thread_state::created;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (!program.completed.load(std::memory_order_acquire) && std::chrono::steady_clock::now() < deadline)
                std::this_thread::yield();
            if (!program.completed.load(std::memory_order_acquire))
                throw std::runtime_error("P34 linked guest execution deadline exceeded");
            (*worker)();
            if (!program.tls || !program.abi || !program.tlsMemory || program.result != 21 || worker->gpr[3] != 42 ||
                worker->gpr[8] != program.tlsImage || worker->gpr[9] != program.dataAddress + 32 ||
                worker->gpr[11] != descriptor || worker->gpr[12] != program.begin + 96 ||
                worker->gpr[2] != 0x13579 || worker->gpr[1] != program.initialStack ||
                worker->gpr[13] || worker->cia != address + 0x900 || worker->lr != address + 0x904 || worker->state & cpu_flag::ret)
            {
                char error[180];
                std::snprintf(error, sizeof(error), "P34 TLS-linked execution mismatch (wrapper result %d, worker TLS %d, entry ABI %d, TLS memory %d)",
                    program.result, program.tls, program.abi, program.tlsMemory);
                throw std::runtime_error(error);
            }
            return 0;
        };
        const auto expect64 = [](std::vector<u8>& bytes, u32 offset, u64 value) {
            const be_t<u64> word = value; std::memcpy(bytes.data() + offset, &word, sizeof(word));
        };
        // Build expected bytes independently of the production packer.
        const std::array<u64, 8> pointers{stackAddress + 0x7f80, stackAddress + 0x7f90,
            stackAddress + 0x7fa0, 0, stackAddress + 0x7fc0, stackAddress + 0x7fd0, 0, 0};
        for (u32 i = 0; i < pointers.size(); ++i) expect64(expectedStack, 0x7f40 + i * 8, pointers[i]);
        std::memcpy(expectedStack.data() + 0x7f80, "probe", 6);
        std::memcpy(expectedStack.data() + 0x7f90, "123456789012345", 16);
        std::memcpy(expectedStack.data() + 0x7fa0, "1234567890123456", 17);
        std::memcpy(expectedStack.data() + 0x7fc0, "LANG=C", 7);
        expectedStack[0x7fd0] = 0;
        for (u32 i = 0; i < 17; ++i) expectedStack[0x7fef + i] = u8(0xa0 + i);
        // The production parameter handler itself rejects bad magic before linking.
        vm::write32(dataAddress + 260, 0);
        if (armsx3_ios_ppu_link_probe_image_and_call(&module, &elf.progs[2], executeLinked, &program) != -6)
            throw std::runtime_error("P34 production PRX parameter handler accepted bad magic");
        vm::write32(dataAddress + 260, control[1]);
        if (std::memcmp(data, expectedData.data(), 0x10000))
            throw std::runtime_error("P34 rejected PRX parameters mutated guest image");
        ARMSX3StartupLog("P34 PASS: executable PRX parameter handler rejects bad magic before linking");
        expect64(expectedData, 32, 42); expect64(expectedStack, frameAddress - stackAddress, initialStack);
        expect64(expectedStack, frameAddress - stackAddress + 16, program.returnAddress);
        expect64(expectedStack, frameAddress - stackAddress + 24, dataAddress + 32);
        for (unsigned repeat = 0; repeat < 2; ++repeat) {
            const int result = armsx3_ios_ppu_link_probe_image_and_call(&module, &elf.progs[2], executeLinked, &program);
            if (result != 0) {
                char error[160];
                std::snprintf(error, sizeof(error), "P34 executable PRX parameter linkage failed (wrapper result %d, iteration %u)", result, repeat + 1);
                throw std::runtime_error(error);
            }
            for (u32 address = 0x50000; address < 0x90000; address += 0x1000)
                if (vm::check_addr(address)) throw std::runtime_error("P34 TLS pool remains mapped after worker cleanup");
            for (const auto& region : std::array<std::pair<u32, const std::vector<u8>*>, 3>{
                std::pair{codeAddress, &expectedCode}, std::pair{dataAddress, &expectedData}, std::pair{stackAddress, &expectedStack}})
                if (std::memcmp(vm::base(region.first), region.second->data(), 0x10000) ||
                    std::memcmp(vm::get_super_ptr(region.first), region.second->data(), 0x10000))
                    throw std::runtime_error("P34 loaded ELF/code/BSS/stack/import restoration or alias mismatch");
        }
        if (std::memcmp(table, tableBefore.data(), tableBefore.size()) ||
            std::memcmp(vm::get_super_ptr(tableAddress), tableBefore.data(), tableBefore.size()))
            throw std::runtime_error("P34 registration mutated HLE descriptors/aliases");
        for (u32 i = 0; i < handlers.size(); ++i)
            if (cache[i].fn != handlers[i]) throw std::runtime_error("P34 registration mutated HLE dispatch");
        for (u32 offset = 0; offset < 0x10000; offset += 0x1000)
            if (vm::check_addr(tableAddress + offset, vm::page_writable))
                throw std::runtime_error("P34 HLE descriptor page became writable");
        for (u32 i = 0; i < codeHandlers.size(); ++i)
            if (pageCache[i].fn != codeHandlers[i]) throw std::runtime_error("P34 guest execution mutated decoded code cache");
        if (armsx3_ios_live_cpu_threads() != live || cpu_thread::g_threads_created.load() != created + 2 ||
            cpu_thread::g_threads_deleted.load() != deleted + 2)
            throw std::runtime_error("P34 registration changed CPU thread counters");
        tableCleanup.release();
        if (vm::dealloc(tableAddress, vm::main) != 0x10000 || vm::check_addr(tableAddress))
            throw std::runtime_error("P34 HLE table deallocation failed");
        segmentCleanup.release();
        for (u32 allocated : {stackAddress, dataAddress, codeAddress})
            if (vm::dealloc(allocated, vm::main) != 0x10000 || vm::check_addr(allocated))
                throw std::runtime_error("P34 guest deallocation failed");
        module.segs.clear(); module.addr_to_seg_index.clear();
        vm::close(); initialized = false;
        ARMSX3StartupLog("P34 PASS: shared production executable process parameter parsing, ELF-derived worker priority/stack/malloc page register and TLS metadata, defaults/malformed rejection before allocation, main-thread r13, copied image/zero BSS/system areas, dirty slot clearing/free/reuse, actual guest TLS byte load/result42, exact arguments/stack/aliases and repeated pool cleanup; full process mutex/TLS HLE initialization/firmware/game boot remain untested");
        return 0;
    }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); if (initialized) vm::close(); return -1; }
}

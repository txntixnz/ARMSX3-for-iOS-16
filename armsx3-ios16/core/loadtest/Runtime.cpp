// SPDX-License-Identifier: GPL-2.0-only
#include "Runtime.h"
#include "Intake.h"
#include "GameImport.h"
#include "StartupLog.h"
#include "Emu/System.h"
#include "Emu/system_config.h"
#include "Emu/system_utils.hpp"
#include "Emu/vfs_config.h"
#include "Emu/IdManager.h"
#include "Emu/VFS.h"
#include "Emu/Cell/PPUAnalyser.h"
#include "Emu/Cell/PPUThread.h"
#include "Emu/Cell/lv2/sys_prx.h"
#include "Emu/Memory/vm.h"
#include "Loader/ELF.h"
#include "Utilities/File.h"
#include "Utilities/Thread.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <stdexcept>
#include <thread>

extern "C" u64 armsx3_ios_live_cpu_threads();
namespace ios_runtime
{
namespace
{
void log(const std::string& text) { ARMSX3StartupLog(text.c_str()); }
void require(bool value, const char* text) { if (!value) throw std::runtime_error(text); }
struct TemporaryConfig
{
    std::filesystem::path path;
    ~TemporaryConfig() { std::error_code error; std::filesystem::remove(path, error); }
};
bool stopped() { return Emu.IsStopped(true) && !armsx3_ios_live_cpu_threads(); }
bool teardown()
{
    log("RUNTIME BEFORE native Kill(false) and thread/VM cleanup");
    invoke_main([] { Emu.Kill(false); });
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(30);
    while (!stopped())
    {
        if (std::chrono::steady_clock::now() >= deadline)
        {
            log("RUNTIME FAIL: cleanup did not finish in 30 seconds; reopen the app");
            return false;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    // on_stop runs before Kill's final main-queue callback returns. Drain that
    // callback before restoring configuration or permitting another operation.
    drain_main_queue();
    require(stopped(), "Runtime changed state during teardown");
    log("RUNTIME AFTER cleanup: fully stopped, zero live CPU threads");
    return true;
}
void run_window()
{
    begin_execution_observation();
    permit_guest_start(true);
    log("EXECUTION BEFORE native Run(false); native RSX startup will release the PPU queue");
    try { invoke_main([] { Emu.Run(false); }); }
    catch (...) { permit_guest_start(false); throw; }
    permit_guest_start(false);
    const auto startup_deadline = std::chrono::steady_clock::now() + std::chrono::seconds(15);
    while (!Emu.IsRunning())
    {
        require(!frontend_failed(), "Guest startup reported a frontend error");
        require(!Emu.IsStopped(), "Guest stopped before reaching the running state; inspect the log");
        require(std::chrono::steady_clock::now() < startup_deadline, "Guest startup did not reach running state within 15 seconds");
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    log("EXECUTION native running state reached; three-second guest window started");
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    auto heartbeat = std::chrono::steady_clock::now();
    while (std::chrono::steady_clock::now() < deadline)
    {
        require(!frontend_failed(), "Guest execution reported a frontend error");
        if (Emu.IsStopped()) { log("EXECUTION guest requested an early stop"); break; }
        require(Emu.IsRunning(), "Guest left the running state during the execution window");
        if (std::chrono::steady_clock::now() >= heartbeat)
        {
            log("EXECUTION heartbeat: running; live native CPU objects=" + std::to_string(armsx3_ios_live_cpu_threads()));
            heartbeat = std::chrono::steady_clock::now() + std::chrono::seconds(1);
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    log("EXECUTION window ended; stopping before collecting joined CPU counters");
}
}

int check(std::string& detail, bool game = false, bool execute = false)
{
    require(!execute || game, "Guest execution requires an imported game folder");
    require(!is_main_thread(), "Runtime loading must run off the UIKit main thread");
    require(stopped(), "Stop emulator activity before checking runtime loading");
    const auto disc = game ? ios_game::installed() : ios_game::Disc{};
    const auto prepared = game ? disc.root / "PS3_GAME/USRDIR/EBOOT.BIN" :
        std::filesystem::path(fs::get_cache_dir()) / "ARMSX3-prepared-executable.elf";
    require(fs::is_file(prepared.string()), "Inspect your EBOOT / ELF first to prepare its executable");
    require(fs::is_file(g_cfg_vfs.get_dev_flash() + "sys/external/liblv2.sprx"), "Install PS3 firmware first");
    auto file = ios_intake::read_executable(prepared.c_str());
    require(bool(file) && file.size() > 0 && file.size() <= 0x40000000ull, "Prepared executable is unavailable or too large");
    ppu_exec_object elf(file);
    require(elf.get_error() == elf_error::ok, "Prepared executable is not a valid PPU ELF; inspect your EBOOT again");
    unsigned expected_segments = 0;
    for (const auto& segment : elf.progs) if (segment.p_type == 1 && segment.p_memsz) ++expected_segments;
    require(expected_segments > 0, "Prepared executable has no loadable memory");

    const std::string previous = g_cfg.to_string();
    const std::string previous_backup = g_backup_cfg.to_string();
    cfg_root configuration;
    require(configuration.from_string(previous), "Could not copy runtime configuration");
    configuration.core.ppu_decoder.set(ppu_decoder_type::_static);
    configuration.core.spu_decoder.set(spu_decoder_type::_static);
    configuration.core.llvm_precompilation.set(false);
    if (execute)
    {
        configuration.core.ppu_call_history.set(true);
        // Keep warnings/errors and explicit startup markers without tracing
        // every guest call through the synchronous diagnostic log writer.
        configuration.log.set_map({{".*", logs::level::warning}});
    }
    configuration.core.libraries_control.set_set({"liblv2.sprx:lle"});
    configuration.video.renderer.set(video_renderer::null);
    configuration.audio.renderer.set(audio_renderer::null);
    configuration.io.keyboard.set(keyboard_handler::null);
    configuration.io.mouse.set(mouse_handler::null);
    configuration.misc.autostart.set(false);
    configuration.misc.autoexit.set(false);
    configuration.misc.start_big_picture_mode.set(false);
    configuration.misc.enable_gamemode.set(false);
    configuration.misc.prevent_display_sleep.set(false);
    configuration.net.net_active.set(np_internet_status::disabled);
    configuration.net.psn_status.set(np_psn_status::disabled);
    static std::atomic<unsigned> sequence{0};
    TemporaryConfig temporary{std::filesystem::path(fs::get_cache_dir()) /
        ("ARMSX3-runtime-check-" + std::to_string(++sequence) + ".yml")};
    const auto text = configuration.to_string();
    fs::file config(temporary.path.string(), fs::rewrite);
    require(bool(config) && config.write(text.data(), text.size()) == text.size(), "Could not write runtime configuration");
    config.sync(); config.close();

    install_frontend();
    Emu.SetForceBoot(false);
    std::string error;
    unsigned loaded_segments = 0, firmware_modules = 0;
    bool attempted = false;
    try
    {
        log(game ? "RUNTIME BEFORE native BootGame: imported game EBOOT, static decoders, null video/audio, autostart OFF" :
            "RUNTIME BEFORE native BootGame: prepared ELF, static decoders, null video/audio, autostart OFF");
        if (game) log("GAME runtime BEFORE BootGame title=" + disc.title + " id=" + disc.id + " original EBOOT and full disc folder");
        attempted = true;
        const auto result = Emu.BootGame(prepared.string(), "", true, cfg_mode::config_override, temporary.path.string());
        log("RUNTIME AFTER BootGame: result=" + std::to_string(static_cast<unsigned>(result)) +
            " state=" + std::to_string(static_cast<unsigned>(Emu.GetStatus(false))));
        require(result == game_boot_result::no_errors && Emu.IsReady(), "Native runtime loader did not reach the ready state; inspect the log");
        require(!g_cfg.misc.autostart.get() && g_cfg.core.ppu_decoder.get() == ppu_decoder_type::_static &&
            g_cfg.core.spu_decoder.get() == spu_decoder_type::_static && g_cfg.video.renderer.get() == video_renderer::null &&
            g_cfg.audio.renderer.get() == audio_renderer::null, "Runtime configuration differs from the load-only request");
        if (game)
        {
            require(Emu.GetTitleID() == disc.id && Emu.GetTitle() == disc.title && Emu.GetCat() == disc.category,
                "Native game identity differs from the imported PARAM.SFO");
            const auto same = [](const std::string& actual, const std::filesystem::path& expected)
            {
                return !actual.empty() && std::filesystem::canonical(actual) == std::filesystem::canonical(expected);
            };
            require(same(Emu.GetBoot(), prepared), "Native loader selected a different executable");
            require(same(vfs::get("/dev_bdvd"), disc.root) &&
                same(vfs::get("/dev_bdvd/PS3_GAME"), disc.root / "PS3_GAME") &&
                same(vfs::get("/dev_bdvd/PS3_GAME/PARAM.SFO"), disc.root / "PS3_GAME/PARAM.SFO") &&
                same(vfs::get("/dev_bdvd/PS3_GAME/USRDIR/EBOOT.BIN"), prepared),
                "Native disc mounts differ from the imported game folder");
            if (!disc.asset.empty()) require(same(vfs::get("/dev_bdvd/PS3_GAME/USRDIR/" + disc.asset.generic_string()),
                disc.root / "PS3_GAME/USRDIR" / disc.asset), "Native disc asset path is unavailable");
            log("GAME runtime PASS title=" + Emu.GetTitle() + " id=" + Emu.GetTitleID() + " category=" + Emu.GetCat() +
                " native disc, SFO, executable and asset mounts verified; asset=" + disc.asset.generic_string());
        }
        const auto* main = g_fxo->try_get<main_ppu_module<lv2_obj>>();
        require(main && main->elf_entry == elf.header.e_entry, "Native main executable registration differs");
        for (const auto& segment : main->segs) if (segment.type == 1 && segment.size)
        {
            require(vm::check_addr(segment.addr, vm::page_readable, segment.size), "Loaded executable segment is not readable in guest memory");
            ++loaded_segments;
        }
        require(loaded_segments == expected_segments, "Native executable segment count differs");
        bool liblv2 = false;
        idm::select<lv2_obj, lv2_prx>([&](u32 id, lv2_prx& module)
        {
            if (!module.path.starts_with(g_cfg_vfs.get_dev_flash())) return;
            ++firmware_modules;
            log("RUNTIME firmware module id=" + std::to_string(id) + " path=" + module.path +
                " segments=" + std::to_string(module.segs.size()) + " functions=" + std::to_string(module.funcs.size()));
            if (module.path.ends_with("/liblv2.sprx") && module.state == PRX_STATE_STARTED && !module.segs.empty()) liblv2 = true;
        });
        require(liblv2, "Native liblv2 firmware loading failed; HLE fallback is not a successful firmware load");
        unsigned ppu_workers = 0;
        idm::select<named_thread<ppu_thread>>([&](u32, ppu_thread& ppu)
        {
            require(bool(ppu.state & cpu_flag::stop), "A PPU context started during the load-only check");
            ++ppu_workers;
        });
        require(ppu_workers > 0, "Runtime loader created no main PPU context");
        require(!frontend_failed(), "Runtime frontend reported an error; inspect the log");
        log("RUNTIME PASS native ready state: mapped segments=" + std::to_string(loaded_segments) +
            " firmware modules=" + std::to_string(firmware_modules) + " stopped PPU contexts=" + std::to_string(ppu_workers) +
            "; guest entry has not been started");
        if (execute) run_window();
    }
    catch (const std::exception& failure) { error = failure.what(); log("RUNTIME load failed: " + error); }
    catch (...) { error = "Native runtime loader threw an unknown exception"; log(error); }

    if (attempted)
    {
        try
        {
            if (!teardown()) { detail = "Runtime cleanup is incomplete. Reopen the app and share the log."; return -2; }
            require(g_cfg.from_string(previous) && g_backup_cfg.from_string(previous_backup), "Could not restore runtime configuration");
            if (execute) rpcs3::utils::configure_logs();
            require(!frontend_failed(), "Runtime frontend reported an error during cleanup");
        }
        catch (const std::exception& failure)
        {
            log(failure.what()); detail = "Runtime cleanup failed. Reopen the app and share the log."; return -2;
        }
        catch (...) { detail = "Runtime cleanup threw an unknown exception. Reopen the app."; return -2; }
    }
    if (execute && error.empty())
    {
        const auto progress = execution_progress();
        if (!progress.captured || progress.failed || !(progress.instructions || progress.calls))
            error = "Joined CPU counters did not confirm guest execution; inspect the startup log";
        else
        {
            detail = "Guest run completed: " + disc.title + " [" + disc.id + "]. Native PPU instruction estimate=" +
                std::to_string(progress.instructions) + ", completed HLE/LV2 calls=" + std::to_string(progress.calls) +
                ", SPU blocks=" + std::to_string(progress.spu_blocks) + ". Clean stop completed. Display and audio are pending.";
            log("EXECUTION PASS: " + detail);
            return 0;
        }
    }
    if (!error.empty()) { detail = error + ". Cleanup completed; share the log."; return -1; }
    detail = (game ? "Game load passed: " + disc.title + " [" + disc.id + "]. " : std::string("Native runtime load passed: ")) +
        std::to_string(loaded_segments) + " executable segments and " +
        std::to_string(firmware_modules) + " firmware modules. Cleanup completed. Game execution and display are next.";
    return 0;
}
}

extern "C" __attribute__((visibility("default"))) int armsx3_core_run_game(char* detail, std::size_t capacity)
{
    if (!detail || capacity < 2) return -1;
    std::string text; int result = -1;
    try { result = ios_runtime::check(text, true, true); }
    catch (const std::exception& error) { text = error.what(); ARMSX3StartupLog(text.c_str()); }
    catch (...) { text = "Game execution threw an unknown exception"; ARMSX3StartupLog(text.c_str()); }
    const auto length = std::min(capacity - 1, text.size());
    std::memcpy(detail, text.data(), length); detail[length] = '\0'; return result;
}

extern "C" __attribute__((visibility("default"))) int armsx3_core_check_game(char* detail, std::size_t capacity)
{
    if (!detail || capacity < 2) return -1;
    std::string text; int result = -1;
    try { result = ios_runtime::check(text, true); }
    catch (const std::exception& error) { text = error.what(); ARMSX3StartupLog(text.c_str()); }
    catch (...) { text = "Game load check threw an unknown exception"; ARMSX3StartupLog(text.c_str()); }
    const auto length = std::min(capacity - 1, text.size());
    std::memcpy(detail, text.data(), length); detail[length] = '\0'; return result;
}

extern "C" __attribute__((visibility("default"))) int armsx3_core_check_runtime(char* detail, std::size_t capacity)
{
    if (!detail || capacity < 2) return -1;
    std::string text; int result = -1;
    try { result = ios_runtime::check(text); }
    catch (const std::exception& error) { text = error.what(); ARMSX3StartupLog(text.c_str()); }
    catch (...) { text = "Runtime check threw an unknown exception"; ARMSX3StartupLog(text.c_str()); }
    const auto length = std::min(capacity - 1, text.size());
    std::memcpy(detail, text.data(), length); detail[length] = '\0'; return result;
}

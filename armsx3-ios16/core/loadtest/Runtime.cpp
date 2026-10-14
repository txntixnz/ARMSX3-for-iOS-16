// SPDX-License-Identifier: GPL-2.0-only
#include "Runtime.h"
#include "StartupLog.h"
#include "Emu/System.h"
#include "Emu/system_config.h"
#include "Emu/vfs_config.h"
#include "Emu/IdManager.h"
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
    Emu.Kill(false);
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
}

int check(std::string& detail)
{
    require(!is_main_thread(), "Runtime loading must run off the UIKit main thread");
    require(stopped(), "Stop emulator activity before checking runtime loading");
    const auto prepared = std::filesystem::path(fs::get_cache_dir()) / "ARMSX3-prepared-executable.elf";
    require(fs::is_file(prepared.string()), "Inspect your EBOOT / ELF first to prepare its executable");
    require(fs::is_file(g_cfg_vfs.get_dev_flash() + "sys/external/liblv2.sprx"), "Install PS3 firmware first");
    fs::file file(prepared.string(), fs::read);
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
        log("RUNTIME BEFORE native BootGame: prepared ELF, static decoders, null video/audio, autostart OFF");
        attempted = true;
        const auto result = Emu.BootGame(prepared.string(), "", true, cfg_mode::config_override, temporary.path.string());
        log("RUNTIME AFTER BootGame: result=" + std::to_string(static_cast<unsigned>(result)) +
            " state=" + std::to_string(static_cast<unsigned>(Emu.GetStatus(false))));
        require(result == game_boot_result::no_errors && Emu.IsReady(), "Native runtime loader did not reach the ready state; inspect the log");
        require(!g_cfg.misc.autostart.get() && g_cfg.core.ppu_decoder.get() == ppu_decoder_type::_static &&
            g_cfg.core.spu_decoder.get() == spu_decoder_type::_static && g_cfg.video.renderer.get() == video_renderer::null &&
            g_cfg.audio.renderer.get() == audio_renderer::null, "Runtime configuration differs from the load-only request");
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
    }
    catch (const std::exception& failure) { error = failure.what(); log("RUNTIME load failed: " + error); }
    catch (...) { error = "Native runtime loader threw an unknown exception"; log(error); }

    if (attempted)
    {
        try
        {
            if (!teardown()) { detail = "Runtime cleanup is incomplete. Reopen the app and share the log."; return -2; }
            require(g_cfg.from_string(previous) && g_backup_cfg.from_string(previous_backup), "Could not restore runtime configuration");
            require(!frontend_failed(), "Runtime frontend reported an error during cleanup");
        }
        catch (const std::exception& failure)
        {
            log(failure.what()); detail = "Runtime cleanup failed. Reopen the app and share the log."; return -2;
        }
        catch (...) { detail = "Runtime cleanup threw an unknown exception. Reopen the app."; return -2; }
    }
    if (!error.empty()) { detail = error + ". Cleanup completed; share the log."; return -1; }
    detail = "Native runtime load passed: " + std::to_string(loaded_segments) + " executable segments and " +
        std::to_string(firmware_modules) + " firmware modules. Cleanup completed. Game execution and display are next.";
    return 0;
}
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

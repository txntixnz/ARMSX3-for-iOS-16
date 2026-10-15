// SPDX-License-Identifier: GPL-2.0-only
#include "Runtime.h"
#include "StartupLog.h"
#include "Emu/System.h"
#include "Emu/emu_callbacks.h"
#include "Emu/IdManager.h"
#include "Utilities/Thread.h"
#include "Emu/RSX/Null/NullGSRender.h"
#include "Emu/Audio/Null/NullAudioBackend.h"
#include "Emu/Audio/Null/null_enumerator.h"
#include "Emu/Io/Null/NullKeyboardHandler.h"
#include "Emu/Io/Null/NullMouseHandler.h"
#include "Emu/Io/Null/null_camera_handler.h"
#include "Emu/Io/Null/null_music_handler.h"
#include "Input/pad_thread.h"
#include "Emu/Cell/Modules/cellMsgDialog.h"
#include "Emu/Cell/Modules/cellSaveData.h"
#include "Emu/Cell/Modules/sceNpTrophy.h"
#include "util/video_source.h"
#include <atomic>
#include <filesystem>
#include <stdexcept>

namespace ios_runtime
{
void dispatch_main(std::function<void()> operation, atomic_t<u32>* wake_up);
namespace
{
std::atomic<bool> failed{false};
std::atomic<bool> start_permitted{false};
void log(const char* text) { ARMSX3StartupLog(text); }
std::string resolve(std::string_view value)
{
    if (value.empty()) return {};
    std::error_code error;
    const auto path = std::filesystem::weakly_canonical(std::filesystem::path(value), error);
    return error ? std::string(value) : path.string();
}
class RuntimeDialog final : public MsgDialogBase
{
public:
    void Create(const std::string& message, const std::string&) override { log(message.c_str()); state = MsgDialogState::Open; }
    void Close(bool) override { state = MsgDialogState::Close; }
    void SetMsg(const std::string& message) override { log(message.c_str()); }
    void ProgressBarSetMsg(u32, const std::string& message) override { log(message.c_str()); }
    void ProgressBarReset(u32) override {}
    void ProgressBarInc(u32, u32) override {}
    void ProgressBarSetValue(u32, u32) override {}
    void ProgressBarSetLimit(u32, u32) override {}
};
}
void record_frontend_failure(const char* message) { failed.store(true); log(message); }
bool frontend_failed() { return failed.load(); }
void permit_guest_start(bool allowed) { start_permitted.store(allowed); }
void install_frontend()
{
    // These callbacks remain installed for the process lifetime. Runtime checks
    // are serialized by UIKit and finish teardown before any intake can resume.
    failed.store(false);
    start_permitted.store(false);
    static bool installed = false;
    if (installed) return;
    g_emu_callbacks.call_from_main_thread = dispatch_main;
    g_emu_callbacks.on_run = [](bool) {
        if (start_permitted.exchange(false))
        {
            log("EXECUTION callback: explicit guest start accepted");
            return;
        }
        record_frontend_failure("RUNTIME FAIL: unexpected request to execute the guest");
        throw std::runtime_error("Guest execution is disabled during runtime load checks");
    };
    g_emu_callbacks.on_pause = [] { log("RUNTIME callback: pause"); };
    g_emu_callbacks.on_resume = [] { record_frontend_failure("RUNTIME FAIL: unexpected resume request"); };
    g_emu_callbacks.on_stop = [] { log("RUNTIME callback: stop completed"); };
    g_emu_callbacks.on_ready = [] { log("RUNTIME callback: ready; initializing native executable"); };
    g_emu_callbacks.on_missing_fw = [] { record_frontend_failure("RUNTIME FAIL: firmware missing"); };
    g_emu_callbacks.on_emulation_stop_no_response = [](std::shared_ptr<atomic_t<bool>> done, int seconds) {
        if (done && *done) return;
        record_frontend_failure(("RUNTIME stop watchdog: still waiting after " + std::to_string(seconds) + " seconds").c_str());
    };
    g_emu_callbacks.on_save_state_progress = [](auto...) { record_frontend_failure("RUNTIME FAIL: unexpected savestate request"); };
    g_emu_callbacks.enable_disc_eject = [](bool) {};
    g_emu_callbacks.enable_disc_insert = [](bool) {};
    g_emu_callbacks.try_to_quit = [](bool, std::function<void()>) { return false; };
    g_emu_callbacks.handle_taskbar_progress = [](s32, s32) {};
    g_emu_callbacks.init_kb_handler = [] {
        log("RUNTIME frontend: native null keyboard");
        ensure(g_fxo->init<KeyboardHandlerBase, NullKeyboardHandler>(Emu.DeserialManager()));
    };
    g_emu_callbacks.init_mouse_handler = [] {
        log("RUNTIME frontend: native null mouse");
        ensure(g_fxo->init<MouseHandlerBase, NullMouseHandler>(Emu.DeserialManager()));
    };
    g_emu_callbacks.init_pad_handler = [](std::string_view title) {
        log("RUNTIME frontend: native pad thread (iOS null handlers)");
        ensure(g_fxo->init<named_thread<pad_thread>>(nullptr, nullptr, title));
    };
    g_emu_callbacks.update_emu_settings = [] {};
    g_emu_callbacks.save_emu_settings = [] { log("RUNTIME settings retained in the temporary load configuration"); };
    g_emu_callbacks.close_gs_frame = [] {};
    g_emu_callbacks.get_gs_frame = [] { return std::unique_ptr<GSFrameBase>{}; };
    g_emu_callbacks.get_camera_handler = [] { return std::make_shared<null_camera_handler>(); };
    g_emu_callbacks.get_music_handler = [] { return std::make_shared<null_music_handler>(); };
    g_emu_callbacks.init_gs_render = [](utils::serial* ar) {
        log("RUNTIME frontend BEFORE native null RSX thread");
        ensure(g_fxo->init<rsx::thread, named_thread<NullGSRender>>(ar));
        log("RUNTIME frontend AFTER native null RSX thread");
    };
    g_emu_callbacks.get_audio = [] { return std::make_shared<NullAudioBackend>(); };
    g_emu_callbacks.get_audio_enumerator = [](u64) { return std::make_shared<null_enumerator>(); };
    g_emu_callbacks.get_msg_dialog = [] { return std::make_shared<RuntimeDialog>(); };
    g_emu_callbacks.get_osk_dialog = [] { return std::shared_ptr<OskDialogBase>{}; };
    g_emu_callbacks.get_save_dialog = [] { return std::unique_ptr<SaveDialogBase>{}; };
    g_emu_callbacks.get_sendmessage_dialog = [] { return std::shared_ptr<SendMessageDialogBase>{}; };
    g_emu_callbacks.get_recvmessage_dialog = [] { return std::shared_ptr<RecvMessageDialogBase>{}; };
    g_emu_callbacks.get_trophy_notification_dialog = [] { return std::unique_ptr<TrophyNotificationBase>{}; };
    g_emu_callbacks.get_localized_string = [](localized_string_id, const char* args) { return std::string(args ? args : ""); };
    g_emu_callbacks.get_localized_u32string = [](localized_string_id, const char*) { return std::u32string{}; };
    g_emu_callbacks.get_localized_setting = [](const cfg::_base*, u32) { return std::string{}; };
    g_emu_callbacks.get_photo_path = [](std::string_view) { return std::string{}; };
    g_emu_callbacks.play_sound = [](const std::string&, std::optional<f32>) {};
    g_emu_callbacks.get_image_info = [](auto...) { return false; };
    g_emu_callbacks.get_scaled_image = [](auto...) { return false; };
    g_emu_callbacks.resolve_path = resolve;
    g_emu_callbacks.resolve_path_may_not_exist = resolve;
    g_emu_callbacks.get_font_dirs = [] { return std::vector<std::string>{}; };
    g_emu_callbacks.on_install_pkgs = [](const std::vector<std::string>&, bool) {
        record_frontend_failure("RUNTIME FAIL: package installation requested during a single-executable load check"); return false;
    };
    g_emu_callbacks.add_breakpoint = [](u32) {};
    g_emu_callbacks.display_sleep_control_supported = [] { return false; };
    g_emu_callbacks.enable_display_sleep = [](bool) {};
    g_emu_callbacks.check_microphone_permissions = [] {};
    g_emu_callbacks.make_video_source = [] { return std::unique_ptr<video_source>{}; };
    g_emu_callbacks.enable_gamemode = [](bool) {};
    g_emu_callbacks.get_database_config = [](const std::string&) { return std::string{}; };
    installed = true;
    log("RUNTIME frontend callbacks installed; UIKit main-queue dispatch, native null devices");
}
}

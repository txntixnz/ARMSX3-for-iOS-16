// SPDX-License-Identifier: GPL-2.0-only
#include "Emu/Io/pad_config.h"
#include "Emu/Io/mouse_config.h"
#include "StartupLog.h"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <functional>
#include <string>
#include <string_view>
#include <thread>

// Normally owned by the desktop frontend. Keep real configuration objects.
std::string g_input_config_override;
cfg_input_configurations g_cfg_input_configs;
mouse_config g_cfg_mouse;

[[noreturn]] void report_fatal_error(std::string_view text, bool is_html, bool include_help_text)
{
    (void)is_html;
    (void)include_help_text;
    ARMSX3StartupLog("P2 fatal core error follows");
    std::string message(text);
    ARMSX3StartupLog(message.c_str());
    std::abort();
}

// Headless frontend wait: evaluate the operation until completion. This load
// test never starts emulation; future UIKit lifecycle calls must run off-main.
void qt_events_aware_op(int repeat_duration_ms, std::function<bool()> operation)
{
    if (!operation) report_fatal_error("Missing wait operation", false, false);
    while (!operation())
        std::this_thread::sleep_for(std::chrono::milliseconds(std::max(1, repeat_duration_ms)));
}

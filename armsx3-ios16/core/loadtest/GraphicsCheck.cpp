// SPDX-License-Identifier: GPL-2.0-only
#include "GraphicsDevice.h"
#include "Runtime.h"
#include "StartupLog.h"
#include "Emu/System.h"
#include <cstdio>
#include <exception>
extern "C" std::uint64_t armsx3_ios_live_cpu_threads();
extern "C" int armsx3_core_check_graphics(char* detail, std::size_t capacity)
{
    if (!detail || !capacity) return -1;
    try
    {
        if (ios_runtime::is_main_thread() || !Emu.IsStopped(true) || armsx3_ios_live_cpu_threads())
        {
            std::snprintf(detail, capacity, "Graphics check requires an idle core and background worker");
            return -1;
        }
        ARMSX3StartupLog("GRAPHICS BEFORE MoltenVK device and offscreen GPU readback; no guest execution");
        const auto result = ios_graphics::check_device(ARMSX3StartupLog);
        std::snprintf(detail, capacity, "%s", result.detail.c_str());
        ARMSX3StartupLog(result.detail.c_str());
        return result.status;
    }
    catch (const std::exception& error) { std::snprintf(detail, capacity, "%s", error.what()); return -1; }
    catch (...) { std::snprintf(detail, capacity, "Graphics check threw an unknown exception"); return -1; }
}

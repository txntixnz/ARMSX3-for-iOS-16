// SPDX-License-Identifier: GPL-2.0-only
#pragma once
// Call before UIApplicationMain, then at startup checkpoints. Does not require
// Foundation initialization. Logs cannot capture OS rejection before main().
void ARMSX3StartupLog(const char* message);
void ARMSX3InstallExceptionLogger();

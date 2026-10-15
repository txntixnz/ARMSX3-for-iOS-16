// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <string>
namespace ios_graphics
{
struct Result { int status; std::string detail; };
// Offscreen driver check, independent of native RSX and presentation.
Result check_device(void (*log)(const char*));
}

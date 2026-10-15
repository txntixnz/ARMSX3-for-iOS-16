// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace ios_input
{
// PS3 digital1 in the low byte, digital2 in the next byte.
enum Button : std::uint32_t
{
    select = 0x0001, l3 = 0x0002, r3 = 0x0004, start = 0x0008,
    up = 0x0010, right = 0x0020, down = 0x0040, left = 0x0080,
    l2 = 0x0100, r2 = 0x0200, l1 = 0x0400, r1 = 0x0800,
    triangle = 0x1000, circle = 0x2000, cross = 0x4000, square = 0x8000
};
constexpr std::uint32_t neutral_axes = 0x80808080;
constexpr std::uint64_t neutral_state = std::uint64_t{neutral_axes} << 16;
constexpr std::uint64_t active_bit = std::uint64_t{1} << 48;
inline std::uint8_t axis(float value, bool invert = false)
{
    if (!std::isfinite(value) || std::abs(value) < 0.12f) return 128;
    value = std::clamp(invert ? -value : value, -1.0f, 1.0f);
    return static_cast<std::uint8_t>(std::lround((value + 1.0f) * 127.5f));
}
inline std::uint32_t axes(float lx, float ly, float rx, float ry)
{
    return std::uint32_t{axis(lx)} | (std::uint32_t{axis(ly, true)} << 8) |
        (std::uint32_t{axis(rx)} << 16) | (std::uint32_t{axis(ry, true)} << 24);
}
using StateWriter = void (*)(std::uint32_t buttons, std::uint32_t axes);
using EnableWriter = void (*)(int enabled);
}
extern "C" void armsx3_core_set_pad_state(std::uint32_t buttons, std::uint32_t axes) noexcept;
extern "C" void armsx3_core_enable_pad(int enabled) noexcept;
extern "C" std::uint64_t armsx3_ios_pad_state() noexcept;

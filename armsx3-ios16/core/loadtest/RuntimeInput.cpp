// SPDX-License-Identifier: GPL-2.0-only
#include "PadInput.h"
#include "Runtime.h"
#include <atomic>

namespace
{
std::atomic<std::uint64_t> input_state{ios_input::neutral_state};
static_assert(decltype(input_state)::is_always_lock_free);
}
extern "C" __attribute__((visibility("default"))) void armsx3_core_enable_pad(int enabled) noexcept
{
    input_state.store(ios_input::neutral_state | (enabled ? ios_input::active_bit : 0));
    ios_runtime::set_input_focus(enabled != 0);
}
extern "C" __attribute__((visibility("default"))) void armsx3_core_set_pad_state(
    std::uint32_t buttons, std::uint32_t axes) noexcept
{
    const auto value = (std::uint64_t{axes} << 16) | (buttons & 0xffffu) | ios_input::active_bit;
    auto previous = input_state.load();
    while (previous & ios_input::active_bit)
    {
        // Stop/reset wins over a writer that was already in flight.
        if (input_state.compare_exchange_weak(previous, value)) return;
    }
}
extern "C" std::uint64_t armsx3_ios_pad_state() noexcept
{
    return input_state.load() & ~ios_input::active_bit;
}

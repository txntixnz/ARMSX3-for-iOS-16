// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <cstdint>
#include <memory>
class GSFrameBase;
namespace ios_runtime
{
// The caller retains the main-thread-created CAMetalLayer until full teardown.
void prepare_renderer_frame(void* layer, unsigned width, unsigned height);
std::unique_ptr<GSFrameBase> take_renderer_frame();
bool renderer_frame_ready();
void finish_renderer_frame();
struct PresentationProgress { std::uint64_t accepted = 0, errors = 0; int last_result = 0; };
PresentationProgress presentation_progress();
}
extern "C" void armsx3_ios_runtime_note_present(int result) noexcept;

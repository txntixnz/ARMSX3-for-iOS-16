// SPDX-License-Identifier: GPL-2.0-only
#include "RuntimeFrame.h"
#include "StartupLog.h"
#include "Emu/RSX/GSFrameBase.h"
#include <atomic>
#include <mutex>
#include <stdexcept>

namespace ios_runtime
{
namespace
{
std::mutex frame_mutex;
std::atomic<unsigned> live_frames{0};
std::atomic<bool> observing{false};
std::atomic<std::uint64_t> accepted{0}, errors{0};
std::atomic<int> last_result{0};
class RuntimeFrame final : public GSFrameBase
{
    void* const layer;
    const unsigned width, height;
    std::atomic<bool> visible{true};
public:
    RuntimeFrame(void* value, unsigned w, unsigned h) : layer(value), width(w), height(h) { ++live_frames; }
    ~RuntimeFrame() override { --live_frames; }
    // Native GSRender releases its unique_ptr and closes the raw frame exactly
    // once in its destructor, after VKGSRender has released its GPU resources.
    void close() override { visible.store(false); delete this; }
    void reset() override {}
    bool shown() override { return visible.load(); }
    void hide() override { visible.store(false); }
    void show() override { visible.store(true); }
    void toggle_fullscreen() override {}
    void delete_context(draw_context_t) override {}
    draw_context_t make_context() override { return nullptr; }
    void set_current(draw_context_t) override {}
    void flip(draw_context_t, bool) override {} // Vulkan owns actual presentation.
    int client_width() override { return static_cast<int>(width); }
    int client_height() override { return static_cast<int>(height); }
    f64 client_display_rate() override { return 60.; }
    bool has_alpha() override { return false; }
    display_handle_t handle() const override { return layer; }
    bool can_consume_frame() const override { return false; }
    void present_frame(std::vector<u8>&&, u32, u32, u32, bool) const override {}
    void take_screenshot(std::vector<u8>&&, u32, u32, bool) override {}
    void update_title(double) override {}
};
std::unique_ptr<GSFrameBase> pending_frame;
}
void prepare_renderer_frame(void* layer, unsigned width, unsigned height)
{
    if (!layer || !width || !height || width > 1280 || height > 720)
        throw std::runtime_error("A retained Metal layer and bounded drawable size are required");
    std::lock_guard lock(frame_mutex);
    if (pending_frame || live_frames.load() || observing.load())
        throw std::runtime_error("Previous renderer frame has not been released; reopen the app");
    pending_frame = std::make_unique<RuntimeFrame>(layer, width, height);
    accepted.store(0); errors.store(0); last_result.store(0); observing.store(true);
}
std::unique_ptr<GSFrameBase> take_renderer_frame()
{
    std::lock_guard lock(frame_mutex);
    return std::move(pending_frame);
}
bool renderer_frame_ready() { std::lock_guard lock(frame_mutex); return bool(pending_frame); }
void finish_renderer_frame()
{
    std::lock_guard lock(frame_mutex);
    pending_frame.reset();
    if (live_frames.load()) throw std::runtime_error("Native renderer still owns its frame; reopen the app");
    observing.store(false);
}
PresentationProgress presentation_progress() { return {accepted.load(), errors.load(), last_result.load()}; }
}
extern "C" void armsx3_ios_runtime_note_present(int result) noexcept
{
    using namespace ios_runtime;
    if (!observing.load()) return;
    last_result.store(result);
    // VK_SUCCESS and VK_SUBOPTIMAL_KHR both accept the presentation request.
    if (result == 0 || result == 1000001003)
    {
        if (accepted.fetch_add(1) == 0) ARMSX3StartupLog("RENDER first native Vulkan queue presentation accepted");
    }
    else ++errors;
}

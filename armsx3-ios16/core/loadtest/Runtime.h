// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <cstddef>
#include <cstdint>
#include <functional>
namespace ios_runtime
{
void install_frontend();
bool frontend_failed();
void drain_main_queue();
void invoke_main(std::function<void()> operation);
bool is_main_thread();
void record_frontend_failure(const char* message);
void permit_guest_start(bool allowed);
struct ExecutionProgress
{
    std::uint64_t instructions = 0, calls = 0, spu_blocks = 0;
    unsigned ppu_contexts = 0, spu_contexts = 0;
    bool captured = false, failed = false;
};
void begin_execution_observation();
ExecutionProgress execution_progress();
}
extern "C" int armsx3_core_check_runtime(char* detail, std::size_t capacity);
extern "C" int armsx3_core_check_game(char* detail, std::size_t capacity);
extern "C" int armsx3_core_run_game(char* detail, std::size_t capacity);
// CAMetalLayer is borrowed; retain it through full shutdown. On -2 retain until process exit.
extern "C" int armsx3_core_render_game(void* layer, unsigned width, unsigned height, char* detail, std::size_t capacity);

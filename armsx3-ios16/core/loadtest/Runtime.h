// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <cstddef>
namespace ios_runtime
{
void install_frontend();
bool frontend_failed();
void drain_main_queue();
bool is_main_thread();
void record_frontend_failure(const char* message);
}
extern "C" int armsx3_core_check_runtime(char* detail, std::size_t capacity);
extern "C" int armsx3_core_check_game(char* detail, std::size_t capacity);

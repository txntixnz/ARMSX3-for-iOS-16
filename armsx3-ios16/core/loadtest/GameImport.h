// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <cstddef>
#include <filesystem>
#include <string>

namespace ios_game
{
struct Disc
{
    std::filesystem::path root;
    std::string title, id, category;
    std::filesystem::path asset; // Relative to PS3_GAME/USRDIR; empty if none.
};
Disc installed();
}
extern "C" int armsx3_core_import_game(const char* path, char* detail, std::size_t capacity);

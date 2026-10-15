// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <cstddef>
#include <string>
namespace fs { class file; }
namespace ios_intake
{
int probe(unsigned index);
fs::file read_executable(const char* selected);
std::string inspect(const char* selected, bool persist);
}
extern "C" int armsx3_core_import_firmware(const char* path, char* detail, std::size_t capacity);
extern "C" int armsx3_core_inspect_executable(const char* path, char* detail, std::size_t capacity);

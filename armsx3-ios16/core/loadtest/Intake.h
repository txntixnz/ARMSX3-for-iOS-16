// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <cstddef>
namespace ios_intake { int probe(unsigned index); }
extern "C" int armsx3_core_import_firmware(const char* path, char* detail, std::size_t capacity);
extern "C" int armsx3_core_inspect_executable(const char* path, char* detail, std::size_t capacity);

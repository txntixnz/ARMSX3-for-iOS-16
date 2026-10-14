// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <string_view>

namespace ios_intake
{
inline bool bounded_pup(std::uint64_t size, std::uint64_t count,
    std::uint64_t header, std::uint64_t data)
{
    return size >= 48 && size <= 0x80000000ull && count > 0 && count <= 256 &&
        header >= 48 + count * 64 && header <= size && data <= size - header;
}
inline bool bounded_entry(std::uint64_t size, std::uint64_t header,
    std::uint64_t offset, std::uint64_t length)
{
    return offset >= header && offset <= size && length <= size - offset && length <= 0x20000000ull;
}
inline bool archive_name(std::string_view name, bool flash)
{
    if (name.empty() || name.front() == '/' || name.find('\\') != name.npos ||
        name.find(':') != name.npos || name.find('\0') != name.npos) return false;
    if (flash && name != "dev_flash" && !name.starts_with("dev_flash/")) return false;
    for (std::size_t pos = 0; pos < name.size();)
    {
        const auto end = name.find('/', pos);
        const auto part = name.substr(pos, end == name.npos ? name.size() - pos : end - pos);
        if (part.empty() || part == "." || part == "..") return false;
        if (end == name.npos) break;
        pos = end + 1;
    }
    return true;
}
inline bool firmware_version(std::string_view value)
{
    while (!value.empty() && (value.back() == '\n' || value.back() == '\r' || value.back() == '\0')) value.remove_suffix(1);
    if (value.empty() || value.size() > 16) return false;
    bool dot = false;
    for (const char c : value)
        if (c == '.' && !dot) dot = true;
        else if (c < '0' || c > '9') return false;
    return dot && value.front() != '.' && value.back() != '.';
}

// Rename within one volume. An extraction/decryption error never touches the
// installed tree; a failed publication restores the previous destination.
template<class Rename>
inline void publish(const std::filesystem::path& staged, const std::filesystem::path& destination,
    const std::filesystem::path& backup, Rename rename)
{
    if (!std::filesystem::is_directory(staged) || std::filesystem::exists(backup))
        throw std::runtime_error("Firmware staging/backup state differs");
    const bool had_old = std::filesystem::exists(destination);
    if (had_old) rename(destination, backup);
    try { rename(staged, destination); }
    catch (...)
    {
        if (had_old) rename(backup, destination);
        throw;
    }
}
inline void publish(const std::filesystem::path& staged, const std::filesystem::path& destination,
    const std::filesystem::path& backup)
{
    publish(staged, destination, backup, [](const auto& from, const auto& to) { std::filesystem::rename(from, to); });
}
}

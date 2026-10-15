// SPDX-License-Identifier: GPL-2.0-only
#include "GameImport.h"
#include "Intake.h"
#include "IntakePolicy.h"
#include "StartupLog.h"
#include "Emu/System.h"
#include "Emu/vfs_config.h"
#include "Loader/PSF.h"
#include "Utilities/File.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <limits>
#include <vector>

extern "C" u64 armsx3_ios_live_cpu_threads();
namespace ios_game
{
namespace
{
namespace disk = std::filesystem;
void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
void log(const std::string& text) { ARMSX3StartupLog(text.c_str()); }
disk::path storage()
{
    auto flash = disk::path(g_cfg_vfs.get_dev_flash()).lexically_normal();
    while (flash.filename().empty() && flash != flash.root_path()) flash = flash.parent_path();
    require(flash.is_absolute() && !flash.filename().empty(), "Game storage is unavailable");
    return flash.parent_path() / "ios-games";
}
bool within(const disk::path& child, const disk::path& parent)
{
    auto a = child.begin();
    for (auto b = parent.begin(); b != parent.end(); ++b, ++a)
        if (a == child.end() || *a != *b) return false;
    return true;
}
void directory(const disk::path& path)
{
    require(disk::is_directory(disk::symlink_status(path)), "Select the disc folder containing PS3_GAME and PS3_DISC.SFB");
}
void regular(const disk::path& path)
{
    require(disk::is_regular_file(disk::symlink_status(path)), "Game folder is missing a required file or contains a link");
}
void preflight_sfo(const fs::file& file)
{
    // Bound the native parser's table allocation and NUL-terminated key reads.
    require(bool(file) && file.size() >= 20 && file.size() <= 0x100000, "PARAM.SFO size is invalid");
    const auto data = file.to_vector<u8>();
    const auto word = [&](std::size_t at, unsigned size = 4) -> u32
    {
        require(at <= data.size() && size <= data.size() - at, "PARAM.SFO table is truncated");
        u32 value = 0;
        for (unsigned i = 0; i < size; ++i) value |= u32(data[at + i]) << (i * 8);
        return value;
    };
    require(word(0) == 0x46535000 && word(4) == 0x101, "PARAM.SFO header is invalid");
    const u32 keys = word(8), values = word(12), count = word(16);
    require(count > 0 && count <= 4096 && keys >= 20 + u64(count) * 16 &&
        keys < values && values <= data.size(), "PARAM.SFO table bounds are invalid");
    for (u32 i = 0; i < count; ++i)
    {
        const auto entry = 20 + std::size_t(i) * 16;
        const u32 key = word(entry, 2), format = word(entry + 2, 2);
        const u32 length = word(entry + 4), maximum = word(entry + 8), offset = word(entry + 12);
        require(key < values - keys && std::find(data.begin() + keys + key, data.begin() + values, u8{0}) != data.begin() + values,
            "PARAM.SFO key is unterminated");
        require(length <= maximum && offset <= data.size() - values && maximum <= data.size() - values - offset,
            "PARAM.SFO value is outside the file");
        require((format == 0x404 && length == 4 && maximum == 4) ||
            (format == 0x204 && maximum > 1) || (format == 4 && maximum > 0), "PARAM.SFO entry format is invalid");
    }
}
Disc inspect_disc(const disk::path& root)
{
    directory(root); directory(root / "PS3_GAME"); directory(root / "PS3_GAME/USRDIR");
    regular(root / "PS3_DISC.SFB"); regular(root / "PS3_GAME/PARAM.SFO"); regular(root / "PS3_GAME/USRDIR/EBOOT.BIN");
    require(Emulator::IsValidSfb((root / "PS3_DISC.SFB").string()), "PS3_DISC.SFB is invalid; select the complete disc folder");
    const auto sfo_path = (root / "PS3_GAME/PARAM.SFO").string();
    fs::file sfo(sfo_path, fs::read); preflight_sfo(sfo);
    const auto metadata = psf::load(sfo, sfo_path);
    require(metadata.errc == psf::error::ok && !metadata.sfo.empty(), "Native PARAM.SFO parsing failed");
    Disc disc{root, std::string(psf::get_string(metadata.sfo, "TITLE")),
        std::string(psf::get_string(metadata.sfo, "TITLE_ID")), std::string(psf::get_string(metadata.sfo, "CATEGORY")), {}};
    require(disc.id.size() == 9 && std::all_of(disc.id.begin(), disc.id.begin() + 4, [](char c) { return c >= 'A' && c <= 'Z'; }) &&
        std::all_of(disc.id.begin() + 4, disc.id.end(), [](char c) { return c >= '0' && c <= '9'; }), "PARAM.SFO title ID is invalid");
    require(!disc.title.empty() && disc.title.size() <= 512 && std::none_of(disc.title.begin(), disc.title.end(),
        [](unsigned char c) { return c < 32 || c == 127; }), "PARAM.SFO title is missing or invalid");
    require(disc.category == "DG", "Select a PS3 disc game folder; installed games and update folders are not supported here");
    const auto usrdir = root / "PS3_GAME/USRDIR";
    for (const auto& entry : disk::recursive_directory_iterator(usrdir))
    {
        const auto status = entry.symlink_status();
        require(disk::is_directory(status) || disk::is_regular_file(status), "Game folder contains a link or unsupported file");
        if (disc.asset.empty() && disk::is_regular_file(status) && entry.path().filename() != "EBOOT.BIN")
            disc.asset = entry.path().lexically_relative(usrdir);
    }
    return disc;
}
struct Entry
{
    disk::path relative; bool directory; u64 size; disk::file_time_type modified;
    bool operator==(const Entry&) const = default;
};
struct Inventory { std::vector<Entry> entries; u64 bytes = 0, files = 0; };
Inventory inventory(const disk::path& source)
{
    Inventory result;
    for (const auto& entry : disk::recursive_directory_iterator(source))
    {
        require(result.entries.size() < 1000000, "Game folder contains too many entries");
        const auto status = entry.symlink_status();
        const bool is_directory = disk::is_directory(status);
        require(is_directory || disk::is_regular_file(status), "Game folder contains a link or unsupported file");
        const u64 size = is_directory ? 0 : entry.file_size();
        require(size <= std::numeric_limits<u64>::max() - result.bytes, "Game folder byte count overflow");
        result.bytes += size; result.files += !is_directory;
        result.entries.push_back({entry.path().lexically_relative(source), is_directory, size, entry.last_write_time()});
    }
    std::sort(result.entries.begin(), result.entries.end(), [](const Entry& a, const Entry& b) { return a.relative < b.relative; });
    return result;
}
struct Cleanup
{
    disk::path path;
    ~Cleanup() { std::error_code error; disk::remove_all(path, error); }
};
}

Disc installed()
{
    return inspect_disc(storage() / "active-disc");
}

std::string import_disc(const char* selected)
{
    require(Emu.IsStopped(true) && !armsx3_ios_live_cpu_threads(), "Stop emulator activity before importing a game");
    require(selected && *selected, "No game folder selected");
    directory(selected);
    const auto source = disk::canonical(selected), base = disk::weakly_canonical(storage());
    require(!within(source, base) && !within(base, source), "Select a game folder outside the app's game storage");
    const auto disc = inspect_disc(source);
    log("GAME import title=" + disc.title + " id=" + disc.id + " category=" + disc.category);
    const auto snapshot = inventory(source);
    const auto& entries = snapshot.entries;
    const u64 bytes = snapshot.bytes, files = snapshot.files;
    require(files > 0, "Game folder has no files");
    disk::create_directories(base);
    const auto available = disk::space(base).available;
    require(bytes <= available && available - bytes >= 0x10000000, "Not enough free space to copy the game and keep 256 MiB free");
    // Check the executable before copying large asset files; do not alter the
    // independent prepared-ELF cache or any firmware/game state on rejection.
    ios_intake::inspect((source / "PS3_GAME/USRDIR/EBOOT.BIN").c_str(), false);
    static std::atomic<unsigned> sequence{0};
    const auto tag = std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + "-" + std::to_string(++sequence);
    const auto stage = base / (".stage-" + tag), backup = base / (".backup-" + tag);
    require(disk::create_directory(stage), "Could not create game staging directory");
    Cleanup cleanup{stage};
    log("GAME BEFORE copy files=" + std::to_string(files) + " bytes=" + std::to_string(bytes));
    u64 copied = 0, completed = 0, reported = 0;
    for (const auto& entry : entries)
    {
        const auto from = source / entry.relative, to = stage / entry.relative;
        const auto status = disk::symlink_status(from);
        require(entry.directory ? disk::is_directory(status) : disk::is_regular_file(status), "Game source changed while importing");
        if (entry.directory) { require(disk::create_directory(to), "Could not create a game directory"); continue; }
        require(disk::file_size(from) == entry.size && disk::last_write_time(from) == entry.modified, "Game source changed while importing");
        require(disk::copy_file(from, to), "Could not copy a game file");
        require(disk::file_size(to) == entry.size && disk::file_size(from) == entry.size && disk::last_write_time(from) == entry.modified,
            "Game source changed or copied file is incomplete");
        copied += entry.size; ++completed;
        if (copied - reported >= 0x10000000 || completed == files)
        {
            log("GAME copied files=" + std::to_string(completed) + "/" + std::to_string(files) + " bytes=" + std::to_string(copied) + "/" + std::to_string(bytes));
            reported = copied;
        }
    }
    require(inventory(source).entries == entries, "Game folder changed while importing; retry when its files are ready");
    const auto staged = inspect_disc(stage);
    require(staged.id == disc.id && staged.title == disc.title && copied == bytes && completed == files, "Staged game validation differs");
    ios_intake::inspect((stage / "PS3_GAME/USRDIR/EBOOT.BIN").c_str(), false);
    log("GAME BEFORE transactional publication title=" + disc.id);
    ios_intake::publish(stage, base / "active-disc", backup);
    std::error_code error; disk::remove_all(backup, error);
    if (error) log("GAME previous game backup retained at " + backup.string());
    log("GAME PASS imported title=" + disc.title + " id=" + disc.id + " files=" + std::to_string(files) + " bytes=" + std::to_string(bytes));
    return "Imported " + disc.title + " [" + disc.id + "]: " + std::to_string(files) + " files. Tap Check game load.";
}
}

extern "C" __attribute__((visibility("default"))) int armsx3_core_import_game(const char* path, char* detail, std::size_t capacity)
{
    if (!detail || capacity < 2) return -1;
    std::string text; int result = -1;
    try { text = ios_game::import_disc(path); result = 0; }
    catch (const std::exception& error) { text = error.what(); }
    catch (...) { text = "Game import threw an unknown exception"; }
    const auto length = std::min(capacity - 1, text.size());
    std::memcpy(detail, text.data(), length); detail[length] = '\0';
    ARMSX3StartupLog(text.c_str()); return result;
}

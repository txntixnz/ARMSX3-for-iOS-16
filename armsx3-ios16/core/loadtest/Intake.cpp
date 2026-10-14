// SPDX-License-Identifier: GPL-2.0-only
#include "Intake.h"
#include "IntakePolicy.h"
#include "StartupLog.h"
#include "Emu/System.h"
#include "Emu/vfs_config.h"
#include "Loader/PUP.h"
#include "Loader/TAR.h"
#include "Loader/ELF.h"
#include "Crypto/sha1.h"
#include "Crypto/key_vault.h"
#include "Crypto/unself.h"
#include "util/serialization_ext.hpp"
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <vector>

extern "C" u64 armsx3_ios_live_cpu_threads();
namespace ios_intake
{
namespace
{
void log(const std::string& value) { ARMSX3StartupLog(value.c_str()); }
void require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
void idle() { require(Emu.IsStopped(true) && !armsx3_ios_live_cpu_threads(), "Stop emulator activity before importing files"); }
std::string unique_tag()
{
    static std::atomic<unsigned> sequence{0};
    return std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + "-" + std::to_string(++sequence);
}
struct Cleanup
{
    std::filesystem::path path;
    ~Cleanup() { std::error_code error; std::filesystem::remove_all(path, error); }
};
void write_file(const std::filesystem::path& path, const std::vector<u8>& bytes)
{
    fs::file file(path.string(), fs::rewrite);
    require(bool(file) && file.write(bytes.data(), bytes.size()) == bytes.size(), "Could not write imported data");
    file.sync();
}
std::vector<PUPFileEntry> preflight_pup(const fs::file& file)
{
    PUPHeader header{}; file.seek(0);
    require(file.read(header), "Firmware file is too short");
    require(header.magic == "SCEUF\0\0\0"_u64, "Select a PS3UPDAT.PUP firmware file");
    require(bounded_pup(file.size(), header.file_count, header.header_length, header.data_length), "Firmware header/table size is invalid");
    std::vector<PUPFileEntry> entries;
    require(file.read(entries, +header.file_count), "Firmware entry table is incomplete");
    std::vector<u64> ids;
    for (const auto& entry : entries)
    {
        require(bounded_entry(file.size(), header.header_length, entry.data_offset, entry.data_length), "Firmware entry is outside the file");
        require(std::find(ids.begin(), ids.end(), +entry.entry_id) == ids.end(), "Firmware contains duplicate entry IDs");
        ids.push_back(entry.entry_id);
        if (entry.entry_id == 0x100) require(entry.data_length > 0 && entry.data_length <= 64, "Firmware version entry is invalid");
    }
    file.seek(0);
    return entries;
}
u64 octal(std::string_view text)
{
    u64 value = 0; bool digit = false;
    for (const char c : text)
    {
        if (c == '\0' || c == ' ') { if (digit) break; else continue; }
        require(c >= '0' && c <= '7' && value <= (UINT64_MAX - 7) / 8, "Invalid firmware TAR size/checksum");
        value = value * 8 + unsigned(c - '0'); digit = true;
    }
    require(digit, "Missing firmware TAR size/checksum");
    return value;
}
void validate_tar(const fs::file& file, bool flash)
{
    u64 offset = 0; unsigned entries = 0;
    while (offset <= file.size() && file.size() - offset >= 512)
    {
        TARHeader header{}; file.seek(offset);
        require(file.read(header), "Firmware TAR header is truncated");
        const auto* bytes = reinterpret_cast<const u8*>(&header);
        if (std::all_of(bytes, bytes + 512, [](u8 byte) { return byte == 0; })) break;
        require(std::memcmp(header.magic, "ustar", 5) == 0, "Firmware TAR format is unsupported");
        const std::string name = std::string(header.prefix, strnlen(header.prefix, sizeof(header.prefix))) +
            std::string(header.name, strnlen(header.name, sizeof(header.name)));
        require(archive_name(name, flash), "Firmware archive path is invalid");
        require(header.filetype == '0' || header.filetype == '\0' || header.filetype == '5', "Firmware archive entry type is unsupported");
        u64 checksum = 0;
        for (unsigned i = 0; i < 512; ++i) checksum += i >= 148 && i < 156 ? unsigned(' ') : bytes[i];
        require(checksum == octal({header.chksum, sizeof(header.chksum)}), "Firmware TAR checksum differs");
        const u64 size = octal({header.size, sizeof(header.size)});
        offset += 512;
        require(size <= file.size() - offset && size <= UINT64_MAX - 511, "Firmware TAR entry is truncated");
        const u64 aligned = (size + 511) & ~u64{511};
        require(aligned <= file.size() - offset, "Firmware TAR padding is truncated");
        offset += aligned; ++entries;
    }
    require(entries > 0, "Firmware archive has no files");
    file.seek(0);
}
std::vector<u8> tar_fixture()
{
    TARHeader header{};
    const std::string name = "dev_flash/sys/external/probe.txt", payload = "ARMSX3 staged firmware probe\n";
    std::memcpy(header.name, name.c_str(), name.size());
    std::snprintf(header.size, sizeof(header.size), "%011o", unsigned(payload.size()));
    std::snprintf(header.mtime, sizeof(header.mtime), "%011o", 1u);
    std::memset(header.chksum, ' ', sizeof(header.chksum)); header.filetype = '0';
    std::memcpy(header.magic, "ustar", 5);
    unsigned sum = 0; for (u8 byte : std::bit_cast<std::array<u8, 512>>(header)) sum += byte;
    std::snprintf(header.chksum, sizeof(header.chksum), "%06o", sum); header.chksum[7] = ' ';
    std::vector<u8> bytes(2048, 0); std::memcpy(bytes.data(), &header, sizeof(header));
    std::memcpy(bytes.data() + 512, payload.data(), payload.size());
    return bytes;
}
std::vector<u8> pup_fixture()
{
    const std::vector<u8> version{'4','.','9','3','\n'};
    const auto tar = tar_fixture();
    constexpr u64 header_size = sizeof(PUPHeader) + 2 * (sizeof(PUPFileEntry) + sizeof(PUPHashEntry));
    PUPHeader header{}; header.magic = "SCEUF\0\0\0"_u64; header.package_version = 1;
    header.image_version = 1; header.file_count = 2; header.header_length = header_size;
    header.data_length = version.size() + tar.size();
    std::array<PUPFileEntry, 2> files{};
    files[0].entry_id = 0x100; files[0].data_offset = header_size; files[0].data_length = version.size();
    files[1].entry_id = 0x300; files[1].data_offset = header_size + version.size(); files[1].data_length = tar.size();
    std::array<PUPHashEntry, 2> hashes{}; hashes[0].entry_id = 0x100; hashes[1].entry_id = 0x300;
    sha1_hmac(PUP_KEY, sizeof(PUP_KEY), version.data(), version.size(), hashes[0].hash);
    sha1_hmac(PUP_KEY, sizeof(PUP_KEY), tar.data(), tar.size(), hashes[1].hash);
    std::vector<u8> bytes(header_size + version.size() + tar.size());
    std::memcpy(bytes.data(), &header, sizeof(header)); std::memcpy(bytes.data() + sizeof(header), files.data(), sizeof(files));
    std::memcpy(bytes.data() + sizeof(header) + sizeof(files), hashes.data(), sizeof(hashes));
    std::memcpy(bytes.data() + header_size, version.data(), version.size());
    std::memcpy(bytes.data() + header_size + version.size(), tar.data(), tar.size());
    return bytes;
}
std::vector<u8> elf_fixture()
{
    ppu_exec_object::ehdr_t header{}; header.e_magic = "\177ELF"_u32;
    header.e_class = 2; header.e_data = 2; header.e_curver = 1; header.e_os_abi = elf_os::lv2;
    header.e_type = elf_type::exec; header.e_machine = elf_machine::ppc64; header.e_version = 1;
    header.e_entry = 0x20000; header.e_phoff = sizeof(header); header.e_ehsize = sizeof(header);
    header.e_phentsize = sizeof(ppu_exec_object::phdr_t); header.e_phnum = 2;
    std::array<ppu_exec_object::phdr_t, 2> segments{};
    segments[0].p_type = 1; segments[0].p_flags = 5; segments[0].p_offset = 0x100;
    segments[0].p_vaddr = 0x10000; segments[0].p_filesz = 8; segments[0].p_memsz = 64; segments[0].p_align = 16;
    segments[1].p_type = 1; segments[1].p_flags = 6; segments[1].p_offset = 0x200;
    segments[1].p_vaddr = 0x20000; segments[1].p_filesz = 8; segments[1].p_memsz = 128; segments[1].p_align = 16;
    std::vector<u8> bytes(0x208, 0); std::memcpy(bytes.data(), &header, sizeof(header));
    std::memcpy(bytes.data() + sizeof(header), segments.data(), sizeof(segments));
    const std::array<be_t<u32>, 2> code{0x3860002au, 0x4e800020u}, descriptor{0x10000u, 0x20000u};
    std::memcpy(bytes.data() + 0x100, code.data(), sizeof(code)); std::memcpy(bytes.data() + 0x200, descriptor.data(), sizeof(descriptor));
    return bytes;
}
}

std::string install(const char* selected)
{
    idle(); require(selected && *selected, "No firmware file selected");
    fs::file file(selected, fs::read); require(bool(file), "Could not open selected firmware");
    log("INTAKE firmware BEFORE bounded PUP validation and native hashes");
    const auto entries = preflight_pup(file); (void)entries;
    pup_object pup(std::move(file)); require(pup_error(pup) == pup_error::ok, "Firmware PUP verification failed; inspect log");
    fs::file version_file = pup.get_file(0x100), update_file = pup.get_file(0x300);
    require(bool(version_file) && bool(update_file), "Firmware version/update archive is missing");
    const std::string version = version_file.to_string(); require(firmware_version(version), "Firmware version text is invalid");
    validate_tar(update_file, false); tar_object update(update_file);
    auto names = update.get_filenames();
    std::erase_if(names, [](const std::string& name) { return name.find("dev_flash_") == name.npos; });
    require(!names.empty(), "Firmware contains no dev_flash packages");
    std::filesystem::path destination(g_cfg_vfs.get_dev_flash());
    while (destination.filename().empty() && destination != destination.root_path()) destination = destination.parent_path();
    require(destination.is_absolute() && !destination.filename().empty(), "Firmware destination is invalid");
    const std::string tag = unique_tag();
    const auto stage = destination.parent_path() / (".ios-firmware-stage-" + tag);
    const auto backup = destination.parent_path() / (".ios-firmware-backup-" + tag);
    require(std::filesystem::create_directory(stage), "Could not create firmware staging directory");
    Cleanup cleanup{stage};
    for (std::size_t index = 0; index < names.size(); ++index)
    {
        log("INTAKE firmware package " + std::to_string(index + 1) + "/" + std::to_string(names.size()) + ": " + names[index]);
        auto stream = update.get_file(names[index]); require(bool(stream), "Firmware package is missing");
        if (stream->m_file_handler) stream->m_file_handler->handle_file_op(*stream, 0, stream->get_size(UINT64_MAX), nullptr);
        fs::file encrypted = fs::make_stream(std::move(stream->data));
        SCEDecrypter decoder(encrypted);
        require(decoder.LoadHeaders() && decoder.LoadMetadata(SCEPKG_ERK, SCEPKG_RIV) && decoder.DecryptData(), "Firmware package decryption failed");
        auto parts = decoder.MakeFile(); require(parts.size() >= 3 && bool(parts[2]), "Firmware package decompression failed");
        validate_tar(parts[2], true); tar_object contents(parts[2]);
        require(contents.extract(stage.string(), false), "Could not extract staged firmware package");
    }
    const auto staged_flash = stage / "dev_flash";
    require(std::filesystem::is_regular_file(staged_flash / "sys/external/liblv2.sprx") &&
        std::filesystem::is_regular_file(staged_flash / "vsh/etc/version.txt"), "Extracted firmware is missing required files");
    log("INTAKE firmware BEFORE transactional dev_flash publication");
    publish(staged_flash, destination, backup);
    std::error_code remove_error; std::filesystem::remove_all(backup, remove_error);
    if (remove_error) log("INTAKE old firmware backup retained: " + backup.string());
    log("INTAKE firmware PASS installed verified packages at " + destination.string());
    std::string clean_version = version; while (!clean_version.empty() && (clean_version.back() == '\n' || clean_version.back() == '\r' || clean_version.back() == '\0')) clean_version.pop_back();
    return "PS3 firmware " + clean_version + " installed. Next: inspect your EBOOT.BIN or ELF.";
}

std::string inspect(const char* selected, bool persist)
{
    idle(); require(selected && *selected, "No executable selected");
    fs::file input(selected, fs::read); require(bool(input) && input.size() > 0 && input.size() <= 0x40000000ull, "Executable is empty, unavailable or too large");
    u32 magic = 0;
    require(input.read_at(0, &magic, sizeof(magic)) == sizeof(magic), "Executable header is truncated");
    fs::file executable;
    if (magic == "SCE\0"_u32)
    {
        log("INTAKE executable BEFORE native SELF decryption");
        executable = decrypt_self(input);
        require(bool(executable), "Could not decrypt this SELF executable; inspect the startup log");
    }
    else
    {
        require(magic == "\177ELF"_u32, "Selected file has no PS3 SELF or ELF header");
        // Like Emulator::Load, decrypt SELF only. Raw ELF must not depend on Emu.GetBoot().
        log("INTAKE executable raw ELF accepted; passing selected file to native parser");
        executable = std::move(input);
    }
    executable.seek(0);
    log("INTAKE executable BEFORE native PPU ELF parsing");
    ppu_exec_object elf(executable); require(elf.get_error() == elf_error::ok, "This file is not a supported PS3 PPU executable");
    unsigned loadable = 0;
    for (const auto& segment : elf.progs) if (segment.p_type == 1)
    {
        const u64 address = segment.p_vaddr, length = segment.p_memsz;
        require(address <= 0xffffffffull && length <= 0x100000000ull - address && segment.p_filesz <= length,
            "Executable segment cannot fit PS3 guest memory");
        ++loadable;
    }
    require(loadable > 0, "Executable has no loadable segments");
    log("INTAKE executable PASS: entry descriptor=" + std::to_string(+elf.header.e_entry) + " loadable segments=" + std::to_string(loadable));
    if (persist)
    {
        const auto target = std::filesystem::path(fs::get_cache_dir()) / "ARMSX3-prepared-executable.elf";
        const auto temporary = target.string() + "." + unique_tag(); Cleanup cleanup{temporary};
        write_file(temporary, executable.to_vector<u8>());
        std::filesystem::rename(temporary, target);
        log("INTAKE prepared executable saved at " + target.string());
    }
    const bool firmware = fs::is_file(g_cfg_vfs.get_dev_flash() + "sys/external/liblv2.sprx");
    return "PS3 executable accepted and prepared (" + std::to_string(loadable) + " segments). " +
        (firmware ? "Firmware is installed. " : "Install firmware next. ") + "Game execution is the next milestone.";
}

int probe(unsigned index)
{
    try
    {
        idle(); require(index < 8, "Unknown intake probe");
        const auto root = std::filesystem::path(fs::get_cache_dir()) / ("ARMSX3-intake-probe-" + unique_tag());
        require(std::filesystem::create_directory(root), "Could not create intake probe directory"); Cleanup cleanup{root};
        if (index == 0)
        {
            const auto source = root / "source", renamed = root / "renamed"; write_file(source, {1,2,3,4});
            std::filesystem::rename(source, renamed); fs::file check(renamed.string(), fs::read);
            require(check.to_vector<u8>() == std::vector<u8>{1,2,3,4} && !std::filesystem::exists(source), "Native file write/read/rename differs");
        }
        else if (index == 1)
        {
            pup_object missing(fs::file{}); require(pup_error(missing) == pup_error::stream, "Missing PUP accepted");
            pup_object short_file(fs::make_stream(std::vector<u8>(8,0))); require(pup_error(short_file) == pup_error::header_read, "Short PUP accepted");
            pup_object magic(fs::make_stream(std::vector<u8>(48,0))); require(pup_error(magic) == pup_error::header_magic, "Bad PUP magic accepted");
        }
        else if (index == 2)
        {
            require(!bounded_pup(176, UINT64_MAX, 176, 0) && !bounded_pup(176, 0, 176, 0) &&
                !bounded_pup(176, 2, 175, 0) && !bounded_entry(200,176,201,0) && !bounded_entry(200,176,176,25), "PUP bound guards differ");
            auto bytes = pup_fixture(); auto* header = reinterpret_cast<PUPHeader*>(bytes.data()); header->header_length = UINT64_MAX;
            pup_object bad(fs::make_stream(std::move(bytes))); require(pup_error(bad) == pup_error::expected_size, "Native PUP size overflow accepted");
        }
        else if (index == 3)
        {
            auto bytes = pup_fixture(); fs::file file = fs::make_stream(std::move(bytes)); preflight_pup(file);
            pup_object pup(std::move(file)); require(pup_error(pup) == pup_error::ok, "Valid authenticated PUP rejected");
            require(pup.get_file(0x100).to_string() == "4.93\n" && pup.get_file(0x300).to_vector<u8>() == tar_fixture() && !pup.get_file(0x999), "Native PUP entry retrieval differs");
        }
        else if (index == 4)
        {
            auto bytes = pup_fixture(); bytes.back() ^= 1;
            pup_object altered(fs::make_stream(std::move(bytes))); require(pup_error(altered) == pup_error::hash_mismatch && !altered.get_file(0x300), "Tampered PUP hash accepted");
        }
        else if (index == 5)
        {
            fs::file file = fs::make_stream(tar_fixture()); validate_tar(file, true); tar_object tar(file);
            require(tar.get_filenames() == std::vector<std::string>{"dev_flash/sys/external/probe.txt"}, "Native TAR names differ");
            require(tar.extract(root.string(), false), "Native staged TAR extraction failed");
            fs::file result((root / "dev_flash/sys/external/probe.txt").string(), fs::read);
            require(result.to_string() == "ARMSX3 staged firmware probe\n" && !archive_name("dev_flash/../../outside",true) &&
                !archive_name("/dev_flash/file",true) && !archive_name("dev_hdd0/file",true), "Staged TAR payload/path guard differs");
        }
        else if (index == 6)
        {
            const auto bytes = elf_fixture();
            const auto path = root / "probe.elf"; write_file(path, bytes);
            const auto result = inspect(path.c_str(), false); require(result.starts_with("PS3 executable accepted"), "Shared executable intake failed");
            const auto renamed = root / "EBOOT.BIN"; write_file(renamed, bytes);
            require(inspect(renamed.c_str(), false).starts_with("PS3 executable accepted"), "Raw ELF intake depends on filename");
            for (const u16 key_version : {u16{0x80}, u16{0xc0}})
            {
                std::vector<u8> debug(0x20 + bytes.size());
                std::memcpy(debug.data(), "SCE\0", 4); debug[8] = static_cast<u8>(key_version);
                if (key_version == 0x80) debug[0x17] = 0x20; else debug[0x10] = 0x20;
                std::memcpy(debug.data() + 0x20, bytes.data(), bytes.size()); write_file(renamed, debug);
                require(inspect(renamed.c_str(), false).starts_with("PS3 executable accepted"), "Native debug SELF intake failed");
            }
            for (const auto& invalid : std::vector<std::vector<u8>>{{0,1,2,3}, {0x7f,'E','L'}, {0x7f,'E','L','F'}})
            {
                write_file(path, invalid); bool rejected = false;
                try { inspect(path.c_str(), false); } catch (const std::exception&) { rejected = true; }
                require(rejected, "Invalid or truncated executable accepted");
            }
        }
        else
        {
            const auto staged = root / "staged", destination = root / "installed", backup = root / "backup";
            std::filesystem::create_directory(staged); std::filesystem::create_directory(destination);
            write_file(staged / "new",{2}); write_file(destination / "old",{1});
            unsigned renames = 0; bool rejected = false;
            try { publish(staged,destination,backup,[&](const auto& from,const auto& to) {
                if (++renames == 2) throw std::runtime_error("Injected publication failure");
                std::filesystem::rename(from,to);
            }); } catch (const std::exception&) { rejected = true; }
            require(rejected && std::filesystem::is_regular_file(destination / "old") &&
                std::filesystem::is_regular_file(staged / "new") && !std::filesystem::exists(backup), "Firmware publication rollback differs");
            publish(staged,destination,backup);
            require(std::filesystem::is_regular_file(destination / "new") && std::filesystem::is_regular_file(backup / "old"), "Firmware publication differs");
        }
        log("INTAKE readiness PASS " + std::to_string(index) + "; no firmware/game execution requested"); return 0;
    }
    catch (const std::exception& error) { log(error.what()); return -1; }
}
}

namespace
{
template<class Operation> int intake_call(char* detail, std::size_t capacity, Operation operation)
{
    if (!detail || capacity < 2) return -1;
    try { const auto text = operation(); std::snprintf(detail, capacity, "%s", text.c_str()); return 0; }
    catch (const std::exception& error) { ARMSX3StartupLog(error.what()); std::snprintf(detail, capacity, "%s", error.what()); return -1; }
}
}
extern "C" __attribute__((visibility("default"))) int armsx3_core_import_firmware(const char* path, char* detail, std::size_t capacity)
{ return intake_call(detail, capacity, [&] { return ios_intake::install(path); }); }
extern "C" __attribute__((visibility("default"))) int armsx3_core_inspect_executable(const char* path, char* detail, std::size_t capacity)
{ return intake_call(detail, capacity, [&] { return ios_intake::inspect(path, true); }); }

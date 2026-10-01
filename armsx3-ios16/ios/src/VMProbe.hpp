// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <sys/mman.h>
#include <unistd.h>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace armsx3::ios {
struct Reservation {
    void* address = nullptr;
    size_t size = 0;
    Reservation(void* p, size_t n) : address(p), size(n) {}
    ~Reservation() { if (address) munmap(address, size); }
    Reservation(const Reservation&) = delete;
    Reservation& operator=(const Reservation&) = delete;
    Reservation(Reservation&& other) noexcept : address(other.address), size(other.size) {
        other.address = nullptr;
    }
};
struct RegionResult {
    std::string name;
    uint64_t size = 0;
    uintptr_t address = 0;
    unsigned attempts = 0;
    int error = 0;
};
struct VMResult {
    std::vector<RegionResult> regions;
    bool complete = false;
};
// Mirrors vm.cpp's hint-only, exact-address reservations. Never MAP_FIXED:
// a hint may overlap an existing mapping, which must not be overwritten.
// The bounded scan differs from upstream's 32768-slot loop to avoid long
// device hangs when extended virtual addressing is unavailable.
inline VMResult probeCoreLayout(unsigned maxAttempts = 256, int protection = PROT_READ | PROT_WRITE, bool omitUnusedHooks = false) {
    constexpr uint64_t GiB = uint64_t{1} << 30;
    const char* names[] = {"base+sudo", "exec", "hook", "stat"};
    const uint64_t sizes[] = {8*GiB, 12*GiB, 32*GiB, 4*GiB};
    VMResult result;
    std::vector<Reservation> held;
    uintptr_t previous = 8*GiB;
    for (unsigned i = 0; i != 4; ++i) {
        if (omitUnusedHooks && i == 2) continue;
        RegionResult row{names[i], sizes[i]};
        uintptr_t candidate = previous + 4*GiB;
        for (unsigned attempt = 0; attempt < maxAttempts; ++attempt, candidate += 4*GiB) {
            ++row.attempts;
            errno = 0;
            void* wanted = reinterpret_cast<void*>(candidate);
            // Apple ARM64 upstream reserves RW, with no physical pages touched.
            void* p = mmap(wanted, sizes[i], protection,
                          MAP_PRIVATE | MAP_ANON, -1, 0);
            if (p == MAP_FAILED) { row.error = errno; continue; }
            if (p != wanted) { munmap(p, sizes[i]); row.error = EADDRNOTAVAIL; continue; }
            row.address = candidate;
            row.error = 0;
            held.emplace_back(p, sizes[i]);
            break;
        }
        result.regions.push_back(row);
        if (!row.address) return result; // Held regions are released on every exit.
        previous = row.address + (i == 0 ? 4*GiB : 0);
    }
    result.complete = true;
    return result;
}
// Exercise commit/reset inside an allocation owned by this probe. MAP_FIXED
// is used only for a page already reserved by us; adjacent pages stay mapped.
struct LifecycleResult { bool passed = false; int error = 0; const char* stage = "reserve"; };
inline LifecycleResult probePageLifecycle() {
    const size_t page = static_cast<size_t>(getpagesize());
    void* allocation = mmap(nullptr, page * 4, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (allocation == MAP_FAILED) return {false, errno, "reserve"};
    Reservation owned(allocation, page * 4);
    auto* base = static_cast<unsigned char*>(allocation);
    if (mprotect(base, page * 4, PROT_READ | PROT_WRITE) != 0)
        return {false, errno, "commit"};
    *reinterpret_cast<volatile uint32_t*>(base) = 0x12345678;
    *reinterpret_cast<volatile uint32_t*>(base + page) = 0xabcdef12;
    *reinterpret_cast<volatile uint32_t*>(base + page * 3) = 0x87654321;
    if (mmap(base + page, page, PROT_NONE, MAP_FIXED | MAP_PRIVATE | MAP_ANON, -1, 0) == MAP_FAILED)
        return {false, errno, "reset"};
    if (mprotect(base + page, page, PROT_READ | PROT_WRITE) != 0)
        return {false, errno, "recommit"};
    bool valid = *reinterpret_cast<volatile uint32_t*>(base + page) == 0 &&
                 *reinterpret_cast<volatile uint32_t*>(base) == 0x12345678 &&
                 *reinterpret_cast<volatile uint32_t*>(base + page * 3) == 0x87654321;
    return {valid, 0, "verified"};
}
struct MirrorResult { bool passed = false; int error = 0; };
// Two shared views of one host page, exercising the basic aliasing requirement.
// This does not validate the core's fixed aliases, 4 KiB tracking or fault handler.
inline MirrorResult probeSharedMirror() {
    const size_t page = static_cast<size_t>(sysconf(_SC_PAGESIZE));
    FILE* file = tmpfile();
    if (!file) return {false, errno};
    if (ftruncate(fileno(file), page) != 0) {
        int error = errno; fclose(file); return {false, error};
    }
    void* a = mmap(nullptr, page, PROT_READ | PROT_WRITE, MAP_SHARED, fileno(file), 0);
    if (a == MAP_FAILED) { int error = errno; fclose(file); return {false, error}; }
    Reservation first(a, page);
    void* b = mmap(nullptr, page, PROT_READ | PROT_WRITE, MAP_SHARED, fileno(file), 0);
    if (b == MAP_FAILED) { int error = errno; fclose(file); return {false, error}; }
    Reservation second(b, page);
    fclose(file);
    *static_cast<volatile uint32_t*>(a) = 0x41524d53;
    return {*static_cast<volatile uint32_t*>(b) == 0x41524d53, 0};
}
}

// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <sys/mman.h>
#include <unistd.h>
#include <cerrno>
#include <cstddef>
#include <cstring>
#if defined(__APPLE__)
#include <libkern/OSCacheControl.h>
#endif

namespace armsx3::ios {
// A small W^X backend candidate, independently testable before core integration.
// The caller MUST stop/join all execution users before publish() or destruction.
// This is not safe for concurrent patching of live emulator code or a drop-in
// implementation of RPCS3's thread-local jit_write_guard.
class ExecutablePage {
    void* memory_ = nullptr;
    size_t size_ = 0;
    bool executable_ = false;
    int error_ = 0;
public:
    ExecutablePage() {
        size_ = static_cast<size_t>(getpagesize());
        void* p = mmap(nullptr, size_, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
        if (p == MAP_FAILED) error_ = errno;
        else memory_ = p;
    }
    ~ExecutablePage() { if (memory_) munmap(memory_, size_); }
    ExecutablePage(const ExecutablePage&) = delete;
    ExecutablePage& operator=(const ExecutablePage&) = delete;
    size_t capacity() const { return size_; }
    int error() const { return error_; }
    const void* entry() const { return executable_ ? memory_ : nullptr; }
    bool publish(const void* code, size_t length) {
        if (!memory_) return false;
        if (!code || !length || length > size_) { error_ = EINVAL; return false; }
        if (mprotect(memory_, size_, PROT_READ | PROT_WRITE) != 0) {
            error_ = errno; return false;
        }
        executable_ = false;
        std::memcpy(memory_, code, length);
#if defined(__APPLE__)
        sys_icache_invalidate(memory_, length);
#else
        __builtin___clear_cache(static_cast<char*>(memory_), static_cast<char*>(memory_) + length);
#endif
        if (mprotect(memory_, size_, PROT_READ | PROT_EXEC) != 0) {
            error_ = errno; return false;
        }
        executable_ = true;
        error_ = 0;
        return true;
    }
};
}

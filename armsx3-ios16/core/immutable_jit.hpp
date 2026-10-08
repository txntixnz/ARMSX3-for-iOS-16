// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <cerrno>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <sys/mman.h>
#include <unistd.h>

extern "C" void armsx3_record_immutable_jit(size_t bytes);

// Only for completed asmjit functions with no custom runtime. Every function
// owns fresh pages; RX mappings live until process exit and are never reopened
// for writing. This is not an implementation of mutable emulator JIT arenas.
namespace utils
{
[[noreturn]] inline void immutable_jit_failure(const char* stage)
{
    char message[256];
    std::snprintf(message, sizeof(message), "P2 immutable JIT failure: %s (errno=%d)", stage, errno);
    armsx3_record_jit_failure(message);
    std::abort();
}
inline void* publish_immutable_jit(asmjit::CodeHolder& code, size_t align)
{
    if (code.flatten() || code.resolveUnresolvedLinks())
        immutable_jit_failure("resolve code");
    const size_t code_size = code.codeSize();
    if (!code_size) immutable_jit_failure("empty code");
    const long page_result = sysconf(_SC_PAGESIZE);
    if (page_result <= 0) immutable_jit_failure("host page size");
    const size_t page = static_cast<size_t>(page_result);
    if (!align || align > page || (align & (align - 1)))
        immutable_jit_failure("unsupported alignment");
    if (code_size > std::numeric_limits<size_t>::max() - (page - 1))
        immutable_jit_failure("code size overflow");
    const size_t mapped_size = (code_size + page - 1) / page * page;
    void* memory = mmap(nullptr, mapped_size, PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANON, -1, 0);
    if (memory == MAP_FAILED) immutable_jit_failure("mmap RW");
    if (code.relocateToBase(reinterpret_cast<uintptr_t>(memory)))
    {
        munmap(memory, mapped_size);
        immutable_jit_failure("relocate code");
    }
    // Match the core's section-copy semantics, validating before each copy.
    for (asmjit::Section* section : code._sections)
    {
        if (section->offset() > mapped_size || section->bufferSize() > mapped_size - section->offset())
        {
            munmap(memory, mapped_size);
            immutable_jit_failure("section exceeds mapping");
        }
        if (section->bufferSize())
            std::memcpy(static_cast<unsigned char*>(memory) + section->offset(),
                section->data(), section->bufferSize());
    }
    asmjit::VirtMem::flushInstructionCache(memory, code_size);
    if (mprotect(memory, mapped_size, PROT_READ | PROT_EXEC) != 0)
    {
        const int saved_errno = errno;
        munmap(memory, mapped_size);
        errno = saved_errno;
        immutable_jit_failure("mprotect RX");
    }
    armsx3_record_immutable_jit(code_size);
    // Publish only after all bytes are copied and the pages are executable.
    return memory;
}
}

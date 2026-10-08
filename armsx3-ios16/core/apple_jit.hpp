// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#if defined(__APPLE__)
#include <TargetConditionals.h>
#include <pthread.h>
#if TARGET_OS_IOS
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>
// Implemented by the iOS frontend; safe to call during dylib constructors.
extern "C" void armsx3_record_jit_failure(const char* message);
#endif

namespace utils
{
inline void apple_jit_write_protect(bool enabled)
{
#if TARGET_OS_IOS
    // Compile-time portability boundary, NOT an iOS JIT implementation.
    // Dopamine device reports show this symbol absent. Fail closed if core
    // execution reaches here: mprotect of live shared pages is not equivalent
    // to macOS's per-thread write protection. A quiescence/alias design is needed.
    using protect_fn = void (*)(int);
    static const auto protect = reinterpret_cast<protect_fn>(
        dlsym(RTLD_DEFAULT, "pthread_jit_write_protect_np"));
    if (!protect)
    {
        constexpr const char* reason = "P2 JIT boundary: pthread_jit_write_protect_np is absent; iOS core JIT backend is not implemented";
        armsx3_record_jit_failure(reason);
        std::fputs(reason, stderr);
        std::abort();
    }
    protect(enabled ? 1 : 0);
#else
    pthread_jit_write_protect_np(enabled);
#endif
}
}
#endif

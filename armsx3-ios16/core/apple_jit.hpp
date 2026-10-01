// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#if defined(__APPLE__)
#include <TargetConditionals.h>
#include <pthread.h>
#if TARGET_OS_IOS
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>
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
        std::fputs("ARMSX3: iOS core JIT backend is not implemented; refusing unsafe execution.\n", stderr);
        std::abort();
    }
    protect(enabled ? 1 : 0);
#else
    pthread_jit_write_protect_np(enabled);
#endif
}
}
#endif

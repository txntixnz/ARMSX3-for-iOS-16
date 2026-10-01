// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include "ExecutablePage.hpp"
#include <cstdint>
#include <cstdlib>
#include <pthread.h>
namespace armsx3::ios {
struct JITResult {
    bool passed = false;
    int error = 0;
    unsigned iterations = 0;
    int returned = 0;
    const char* stage = "allocate";
};
struct JITCall { const void* entry; int returned = 0; };
inline void* executeOnWorker(void* context) {
    auto* call = static_cast<JITCall*>(context);
    call->returned = reinterpret_cast<int(*)()>(const_cast<void*>(call->entry))();
    return nullptr;
}
inline JITResult probeJITRewrites() {
    ExecutablePage page;
    JITResult result;
    if (page.error()) { result.error = page.error(); return result; }
    for (unsigned i = 0; i < 32; ++i) {
        const uint32_t expected = i % 2 ? 84 : 42;
#if defined(__aarch64__) || defined(__arm64__)
        const uint32_t code[] = {0x52800000u | (expected << 5), 0xd65f03c0u};
#elif defined(__x86_64__)
        const unsigned char code[] = {0xb8, static_cast<unsigned char>(expected), 0, 0, 0, 0xc3};
#else
        result.stage = "unsupported_architecture"; return result;
#endif
        if (!page.publish(code, sizeof(code))) {
            result.error = page.error(); result.stage = "publish"; return result;
        }
        JITCall call{page.entry()};
        pthread_t worker{};
        int error = pthread_create(&worker, nullptr, executeOnWorker, &call);
        if (error) { result.error = error; result.stage = "pthread_create"; return result; }
        // Every worker is joined before any page rewrite. No simultaneous
        // execution and mprotect transitions are claimed or attempted.
        error = pthread_join(worker, nullptr);
        if (error) {
            // An unexpected failure leaves lifetime uncertain; never unmap
            // code under a possibly live worker or free its stack context.
            std::abort();
        }
        result.returned = call.returned;
        if (call.returned != static_cast<int>(expected)) {
            result.stage = "wrong_result"; return result;
        }
        ++result.iterations;
    }
    result.passed = true;
    result.stage = "rewrites_verified";
    return result;
}
}

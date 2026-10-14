// SPDX-License-Identifier: GPL-2.0-only
#import <Foundation/Foundation.h>
#include "Runtime.h"
#include "util/atomic.hpp"
#include <exception>
#include <functional>
#include <memory>

namespace ios_runtime
{
bool is_main_thread() { return NSThread.isMainThread; }
void drain_main_queue()
{
    if (!is_main_thread()) dispatch_sync(dispatch_get_main_queue(), ^{});
}
void dispatch_main(std::function<void()> operation, atomic_t<u32>* wake_up)
{
    auto callback = std::make_shared<std::function<void()>>(std::move(operation));
    void (^invoke)() = ^{
        @autoreleasepool {
            try { (*callback)(); }
            catch (const std::exception& error) { record_frontend_failure(error.what()); }
            catch (...) { record_frontend_failure("RUNTIME main-queue callback threw an unknown exception"); }
            if (wake_up) { *wake_up = 1; wake_up->notify_one(); }
        }
    };
    if (is_main_thread()) invoke();
    else dispatch_async(dispatch_get_main_queue(), invoke);
}
}

// SPDX-License-Identifier: GPL-2.0-only
#include "StartupLog.h"
#import <Foundation/Foundation.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <limits.h>
#include <cstdio>
#include <cstdlib>
#include <cerrno>

void ARMSX3StartupLog(const char* message) {
    const char* home = getenv("HOME");
    if (!home || !message) return;
    char path[PATH_MAX];
    int count = snprintf(path, sizeof(path), "%s/Documents", home);
    if (count < 0 || static_cast<size_t>(count) >= sizeof(path)) return;
    if (mkdir(path, 0700) != 0 && errno != EEXIST) return;
    count = snprintf(path, sizeof(path), "%s/Documents/ARMSX3-startup.log", home);
    if (count < 0 || static_cast<size_t>(count) >= sizeof(path)) return;
    int fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
    if (fd < 0) return;
    struct timeval now{};
    gettimeofday(&now, nullptr);
    char line[2048];
    count = snprintf(line, sizeof(line), "%lld.%06d pid=%d %s\n",
        static_cast<long long>(now.tv_sec), static_cast<int>(now.tv_usec), getpid(), message);
    if (count > 0) {
        size_t bytes = static_cast<size_t>(count);
        if (bytes >= sizeof(line)) bytes = sizeof(line) - 1;
        size_t offset = 0;
        while (offset < bytes) {
            ssize_t written = write(fd, line + offset, bytes - offset);
            if (written < 0 && errno == EINTR) continue;
            if (written <= 0) break;
            offset += static_cast<size_t>(written);
        }
        fsync(fd);
    }
    close(fd);
}
static NSUncaughtExceptionHandler* previousHandler = nullptr;
static void RecordException(NSException* exception) {
    ARMSX3StartupLog("Uncaught Objective-C exception");
    ARMSX3StartupLog(exception.name.UTF8String);
    ARMSX3StartupLog(exception.reason.UTF8String);
    // This is an Objective-C exception callback, not a POSIX signal handler.
    ARMSX3StartupLog([[exception callStackSymbols] componentsJoinedByString:@" | "].UTF8String);
    if (previousHandler) previousHandler(exception);
}
void ARMSX3InstallExceptionLogger() {
    previousHandler = NSGetUncaughtExceptionHandler();
    NSSetUncaughtExceptionHandler(RecordException);
}

// SPDX-License-Identifier: GPL-2.0-only
#import "Diagnostics.h"
#include "StartupLog.h"
#import <Metal/Metal.h>
#import <UIKit/UIKit.h>
#import <sys/utsname.h>
#import <sys/mman.h>
#import <libkern/OSCacheControl.h>
#import <dlfcn.h>
#include <cstring>
#include "VMProbe.hpp"

static NSDictionary* MetalProbe() {
    ARMSX3StartupLog("Platform test: Metal clear/readback");
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (!device) return @{ @"passed": @NO, @"error": @"No Metal device" };
    MTLTextureDescriptor* descriptor = [MTLTextureDescriptor
        texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm width:1 height:1 mipmapped:NO];
    descriptor.usage = MTLTextureUsageRenderTarget;
    descriptor.storageMode = MTLStorageModePrivate;
    id<MTLTexture> texture = [device newTextureWithDescriptor:descriptor];
    id<MTLBuffer> readback = [device newBufferWithLength:256 options:MTLResourceStorageModeShared];
    id<MTLCommandQueue> queue = [device newCommandQueue];
    id<MTLCommandBuffer> command = [queue commandBuffer];
    if (!texture || !readback || !command)
        return @{ @"passed": @NO, @"error": @"Metal resource allocation failed" };
    MTLRenderPassDescriptor* pass = [MTLRenderPassDescriptor renderPassDescriptor];
    pass.colorAttachments[0].texture = texture;
    pass.colorAttachments[0].loadAction = MTLLoadActionClear;
    pass.colorAttachments[0].storeAction = MTLStoreActionStore;
    pass.colorAttachments[0].clearColor = MTLClearColorMake(0, 1, 0, 1);
    id<MTLRenderCommandEncoder> render = [command renderCommandEncoderWithDescriptor:pass];
    if (!render) return @{ @"passed": @NO, @"error": @"Render encoder failed" };
    [render endEncoding];
    id<MTLBlitCommandEncoder> blit = [command blitCommandEncoder];
    if (!blit) return @{ @"passed": @NO, @"error": @"Blit encoder failed" };
    [blit copyFromTexture:texture sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0)
              sourceSize:MTLSizeMake(1,1,1) toBuffer:readback destinationOffset:0
              destinationBytesPerRow:256 destinationBytesPerImage:256];
    [blit endEncoding];
    [command commit];
    [command waitUntilCompleted];
    const uint8_t* bytes = static_cast<const uint8_t*>(readback.contents);
    bool passed = command.status == MTLCommandBufferStatusCompleted && bytes &&
                  bytes[0] == 0 && bytes[1] == 255 && bytes[2] == 0 && bytes[3] == 255;
    return @{ @"passed": @(passed), @"device": device.name,
              @"apple7": @([device supportsFamily:MTLGPUFamilyApple7]),
              @"error": command.error.localizedDescription ?: @"",
              @"scope": @"Native Metal clear and GPU readback; does not test Vulkan/RSX" };
}

NSDictionary* ARMSX3RunPlatformDiagnostics() {
    struct utsname machine{};
    uname(&machine);
    ARMSX3StartupLog("Platform test: reserving core address layout");
    auto layout = armsx3::ios::probeCoreLayout();
    NSMutableArray* regions = [NSMutableArray array];
    for (const auto& row : layout.regions) {
        [regions addObject:@{ @"name": @(row.name.c_str()), @"bytes": @(row.size),
            @"address": [NSString stringWithFormat:@"0x%llx", (unsigned long long)row.address],
            @"attempts": @(row.attempts), @"errno": @(row.error),
            @"error": row.error ? @(strerror(row.error)) : @"" }];
    }
    ARMSX3StartupLog("Platform test: shared memory aliases");
    auto mirror = armsx3::ios::probeSharedMirror();
    const size_t page = static_cast<size_t>(getpagesize());
    errno = 0;
    ARMSX3StartupLog("Platform test: MAP_JIT allocation");
    void* mapping = mmap(nullptr, page, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANON | MAP_JIT, -1, 0);
    int jitError = mapping == MAP_FAILED ? errno : 0;
    if (mapping != MAP_FAILED) munmap(mapping, page);
    return @{ @"schema": @1, @"build": @"ARMSX3 iOS16 P0.1",
        @"source_commit": @ARMSX3_SOURCE_COMMIT,
        @"emulator_core_linked": @NO, @"game_boot_supported": @NO,
        @"timestamp": [[NSISO8601DateFormatter new] stringFromDate:[NSDate date]],
        @"machine": @(machine.machine), @"os": NSProcessInfo.processInfo.operatingSystemVersionString,
        @"physical_memory_bytes": @(NSProcessInfo.processInfo.physicalMemory),
        @"host_page_bytes": @(page),
        @"layout": @{ @"passed": @(layout.complete), @"regions": regions,
             @"scan_limit_per_region": @256, @"total_requested_GiB": @56,
             @"scope": @"Untouched concurrent virtual reservations; not physical RAM or full core initialization" },
        @"shared_alias": @{ @"passed": @(mirror.passed), @"errno": @(mirror.error) },
        @"jit_mapping": @{ @"map_jit_rw_passed": @(jitError == 0), @"errno": @(jitError),
             @"write_protect_symbol_present": @(dlsym(RTLD_DEFAULT, "pthread_jit_write_protect_np") != nullptr),
             @"scope": @"Mapping only; successful allocation does not prove code execution" },
        @"metal": MetalProbe(),
        @"jit_execution": @{ @"status": @"not_run" } };
}

NSDictionary* ARMSX3RunJITExecutionTest() {
    ARMSX3StartupLog("JIT execution test entered");
#if defined(__aarch64__) || defined(__arm64__)
    // Test a separate RW -> RX allocation without MAP_JIT. This is a baseline
    // for the device's actual signing/JIT state, NOT a replacement for the
    // upstream multi-threaded MAP_JIT allocator and write-protection protocol.
    const size_t page = static_cast<size_t>(getpagesize());
    void* memory = mmap(nullptr, page, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (memory == MAP_FAILED)
        return @{ @"passed": @NO, @"stage": @"mmap_rw", @"errno": @(errno) };
    // mov w0, #42; ret
    const uint32_t code[] = {0x52800540u, 0xd65f03c0u};
    std::memcpy(memory, code, sizeof(code));
    sys_icache_invalidate(memory, sizeof(code));
    if (mprotect(memory, page, PROT_READ | PROT_EXEC) != 0) {
        int error = errno; munmap(memory, page);
        return @{ @"passed": @NO, @"stage": @"mprotect_rx", @"errno": @(error) };
    }
    ARMSX3StartupLog("JIT test: invoking generated ARM64 code");
    int returned = reinterpret_cast<int(*)()>(memory)();
    munmap(memory, page);
    ARMSX3StartupLog("JIT test: returned from generated code");
    return @{ @"passed": @(returned == 42), @"stage": @"executed",
              @"returned": @(returned), @"scope": @"One RW-to-RX code page, not RPCS3 JIT compatibility" };
#else
    return @{ @"passed": @NO, @"stage": @"unsupported_architecture" };
#endif
}

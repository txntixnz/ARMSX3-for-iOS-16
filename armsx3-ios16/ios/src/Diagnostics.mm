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
#include "JITProbe.hpp"

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

static NSDictionary* LayoutResult(const armsx3::ios::VMResult& layout, unsigned gib, NSString* protection) {
    NSMutableArray* regions = [NSMutableArray array];
    for (const auto& row : layout.regions) {
        [regions addObject:@{ @"name": @(row.name.c_str()), @"bytes": @(row.size),
            @"address": [NSString stringWithFormat:@"0x%llx", (unsigned long long)row.address],
            @"attempts": @(row.attempts), @"errno": @(row.error),
            @"error": row.error ? @(strerror(row.error)) : @"" }];
    }
    return @{ @"passed": @(layout.complete), @"regions": regions,
              @"total_requested_GiB": @(gib), @"protection": protection,
              @"scope": @"Concurrent untouched virtual reservations; released after each variant" };
}

NSDictionary* ARMSX3RunPlatformDiagnostics() {
    struct utsname machine{};
    uname(&machine);
    ARMSX3StartupLog("Layout test: 24 GiB without unused hook arena, RW");
    auto compactRW = armsx3::ios::probeCoreLayout(256, PROT_READ | PROT_WRITE, true);
    ARMSX3StartupLog("Layout test: 24 GiB without unused hook arena, PROT_NONE");
    auto compactNone = armsx3::ios::probeCoreLayout(256, PROT_NONE, true);
    ARMSX3StartupLog("Layout test: original 56 GiB, PROT_NONE comparison");
    auto fullNone = armsx3::ios::probeCoreLayout(256, PROT_NONE, false);
    ARMSX3StartupLog("Host-page test: commit, reset, recommit, adjacent canaries");
    auto lifecycle = armsx3::ios::probePageLifecycle();
    ARMSX3StartupLog("Platform test: shared memory aliases");
    auto mirror = armsx3::ios::probeSharedMirror();
    const size_t page = static_cast<size_t>(getpagesize());
    errno = 0;
    ARMSX3StartupLog("Platform test: MAP_JIT allocation");
    void* mapping = mmap(nullptr, page, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANON | MAP_JIT, -1, 0);
    int jitError = mapping == MAP_FAILED ? errno : 0;
    if (mapping != MAP_FAILED) munmap(mapping, page);
    return @{ @"schema": @2, @"build": @"ARMSX3 iOS16 P0.2",
        @"source_commit": @ARMSX3_SOURCE_COMMIT,
        @"emulator_core_linked": @NO, @"game_boot_supported": @NO,
        @"timestamp": [[NSISO8601DateFormatter new] stringFromDate:[NSDate date]],
        @"machine": @(machine.machine), @"os": NSProcessInfo.processInfo.operatingSystemVersionString,
        @"physical_memory_bytes": @(NSProcessInfo.processInfo.physicalMemory),
        @"host_page_bytes": @(page),
        @"layouts": @{ @"ios_24GiB_rw": LayoutResult(compactRW, 24, @"RW"),
                       @"ios_24GiB_none": LayoutResult(compactNone, 24, @"NONE"),
                       @"upstream_56GiB_none": LayoutResult(fullNone, 56, @"NONE") },
        @"page_lifecycle": @{ @"passed": @(lifecycle.passed), @"errno": @(lifecycle.error),
                             @"stage": @(lifecycle.stage),
                             @"scope": @"Host-page commit/reset with adjacent canaries; not guest 4 KiB fault handling" },
        @"shared_alias": @{ @"passed": @(mirror.passed), @"errno": @(mirror.error) },
        @"jit_mapping": @{ @"map_jit_rw_passed": @(jitError == 0), @"errno": @(jitError),
             @"write_protect_symbol_present": @(dlsym(RTLD_DEFAULT, "pthread_jit_write_protect_np") != nullptr),
             @"scope": @"Mapping only; successful allocation does not prove code execution" },
        @"metal": MetalProbe(),
        @"jit_execution": @{ @"status": @"not_run" } };
}

NSDictionary* ARMSX3RunJITExecutionTest() {
    ARMSX3StartupLog("JIT rewrite test: 32 publications and joined execution workers");
    const auto result = armsx3::ios::probeJITRewrites();
    ARMSX3StartupLog(result.passed ? "JIT rewrite test passed" : "JIT rewrite test failed");
    return @{ @"passed": @(result.passed), @"stage": @(result.stage),
              @"errno": @(result.error), @"iterations": @(result.iterations),
              @"expected_iterations": @32, @"last_returned": @(result.returned),
              @"scope": @"Same code page rewritten 32 times and executed on joined workers; no concurrent live patching or core integration" };
}

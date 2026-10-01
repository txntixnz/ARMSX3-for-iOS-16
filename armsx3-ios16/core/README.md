# P1: actual emulator core compilation

This separate workflow cross-compiles upstream **rpcs3_emu**, including CPU,
RSX common code, PS3 modules, loaders and utilities, for arm64 iPhoneOS 16.0.
It does not build another diagnostic replacement, link a runnable emulator,
or package an IPA. The working P0.2 app remains available separately.

The workflow builds FFmpeg 8.0 from pinned source for iOS, applies the UIKit
and unused hook-arena patches, excludes the Qt desktop frontend and uses
libusb's null backend (physical USB passthrough unavailable). It does not
use Android defines or link macOS FFmpeg prebuilts. LLVM, Vulkan, SDL, FAudio,
OpenAL and OpenCV are disabled for this initial core compilation pass.
Other core dependencies are compiled from the pinned upstream submodules.

The archive verification checks every object for arm64, iPhoneOS platform
metadata and a deployment target no newer than iOS 16.0. Static archive
creation does not resolve all external symbols. The artifact is **not a
standalone SDK or a link-complete emulator**; transitive libraries are not
bundled in it. Build logs and compile commands are uploaded on failure.

## Runtime work still required

- Implement the actual iOS JIT allocation/publication and concurrent patching
  protocol. Existing macOS thread-local JIT protection calls now go through
  one Apple adapter. On iOS, absent support aborts explicitly; it never
  silently substitutes a no-op. The tested single-page RW/RX helper is not
  installed into the emulator as if it were a concurrent JIT backend.
- Adapt core MAP_JIT mappings, memory reset and 4 KiB guest protection to
  16 KiB host pages, and validate the real signal/fault handlers on device.
- Build and integrate LLVM and iOS MoltenVK, then link a UIKit frontend with
  explicit startup, firmware/title loading, input and audio lifecycles.
- Run device validation before any PS3 boot or compatibility claim.

## Device evidence before P1

P0.2 on iPhone14,3 / A15 / iOS 16.0: Metal clear/readback, shared aliases,
page lifecycle and simultaneous 8+12+4 GiB reservations passed. All 32 code
rewrites with joined worker execution passed. MAP_JIT returned EINVAL and
pthread_jit_write_protect_np was absent. These are platform-helper results,
not evidence that the full emulator memory or JIT subsystem works.

Run **ARMSX3 iOS 16 - P1 core compilation** in Actions. Report completion or
failure; the agent does not poll the workflow after enqueueing it.

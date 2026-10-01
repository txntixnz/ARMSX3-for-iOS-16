# ARMSX3 iOS 16 handoff — 2026-09-30 UTC

User target: iPhone 13 Pro Max / A15 / iOS 16.0 / Dopamine, existing TrollStore.
User explicitly requests using GitHub to compile and says not to monitor the build;
they will report completion. Keep responses concise.

Source: https://github.com/ARMSX2/ARMSX3
Pinned base: 92b931b9fb5eef7f1317cb482917dfc19aceebd9
Build host: txntixnz/ARMSX3-for-iOS-16, main branch.
An empty armsx3-ios16 branch was created in RPCS3-iOS-Releases before the user
created this dedicated repository; no port files or workflows were pushed there.
Workflow: .github/workflows/build-armsx3-ios16.yml
Port overlay: armsx3-ios16/ios; upstream patch: armsx3-ios16/patches.

This checkpoint is P0: native platform diagnostics and a real UIKit patch to the
upstream Metal layer bridge. It is NOT a working emulator; the core is not linked.
Do not claim PS3 firmware installation, game boot or performance is implemented.
Do not confuse the standalone probe target with a full rpcs3_emu build.

Local verification in Linux:
- Compiled/executed ios/tests/vm_probe_test.cpp using g++ C++20 with warnings as errors.
- Tested shared aliases, bounded allocation failure, preservation of an occupied
  hint address, simultaneous 56 GiB layout with PROT_NONE, and cleanup via mincore.
- Apple-style RW reservations fail on this Linux environment at the 12 GiB region;
  this is recorded as an environment result, not a prediction of iPhone behavior.
- Shell syntax and plist/JSON/workflow checks performed before upload.
- Objective-C++/Mach-O compilation requires the Actions Xcode job; no local iOS SDK.

Core findings:
- android/CMakeLists.txt builds rpcsx-android against rpcs3_emu, adding Input sources.
- rpcs3/CMakeLists.txt only excludes desktop Qt when ANDROID is set.
- 3rdparty/CMakeLists.txt assumes desktop MoltenVK paths on APPLE.
- 3rdparty/hidapi/CMakeLists.txt links IOKit on APPLE.
- rpcs3/Emu/Memory/vm.cpp reserves 8+12+32+4 GiB before game boot.
- Utilities/JITASM.cpp, Utilities/JIT.h, Utilities/JITLLVM.cpp and Thread.cpp
  use Apple JIT write-protection APIs; vm_native.cpp has Apple-specific mapping paths.
- Upstream metal_layer.mm used NSView/AppKit; supplied patch supports UIView on iOS.

Next: user reports workflow result; inspect log and fix actual compiler failures,
or inspect on-device diagnostic JSON if build succeeds. Then wire the actual core
and cross-compiled dependencies. A passing JIT test executes only mov w0,#42;ret
through RW->RX memory; it does not establish full RPCS3 JIT compatibility.
Do not shrink guest reservations blindly to fit a small address window.


## P0.1 update
- User confirmed the third Actions run succeeded, then reported instant launch exit
  on iPhone with no Analytics log.
- Removed dynamic-codesigning from signing entitlements (documented TrollStore
  launch-crash risk), plus irrelevant macOS JIT entitlement keys.
- Added final signed-entitlement validation, build number 2, persistent startup
  checkpoints from main(), uncaught Objective-C exception logging, and log sharing
  before any tests. No pre-main or SIGKILL logging claim.
- Removed unused sysinfo_darwin.mm from probe: it had a global Foundation initializer.
- Cause is a strong signing hypothesis, not proven from a device crash report.
- Next: user checks new workflow result and installs build 2, sends startup log.


## P0.2 / build 3
User said continue after P0.1 device report. No need to poll Actions after enqueue.
P0.1 evidence: native Metal and shared aliases passed; iPhone host pages 16 KiB;
RW->RX ARM64 execution returned 42; MAP_JIT EINVAL and pthread JIT symbol absent;
8+12 GiB reservations passed, 32 GiB hook failed ENOMEM.

Source-wide audit at pinned upstream finds g_hook_addr/s_hook only in vm.cpp:
reservation, backing object, logging, mapping and cleanup. Added iOS-only source
patch omitting those lifecycle operations and anchoring stat search after exec.
The patch is applied and audited by CI but vm.cpp is NOT compiled by the probe.
Do not claim an integrated or compiled full emulator memory patch yet.

P0.2 device tests: 24 GiB RW, 24 GiB NONE, original 56 GiB NONE, host-page
reset with neighboring canaries, 32 sequential RW->RX rewrites on the same page
with a fresh joined execution worker for each. ExecutablePage/JITProbe are new
reusable/test helpers; not wired into RPCS3's JIT machinery. No concurrent live
patching is attempted. Tested native host versions with g++ warnings as errors.

Local patch checks: clean pinned checkout accepts both patches; diff --check;
source consumer audit; plist/schema and workflow parse. iOS device results pending.
Next analyze build 3 JSON, then implement the actual core build/dependencies and
JIT integration strategy rather than assuming W^X publication solves live patching.

## P1 core compilation bring-up

User authorized real core integration after successful P0.2 device logs:
24 GiB RW and PROT_NONE layouts, 16 KiB page lifecycle, shared aliases, Metal,
and 32 joined-thread JIT rewrites all passed. MAP_JIT EINVAL, pthread JIT
symbol absent. No concurrent patching or game execution established.

Added separate build-armsx3-ios16-core.yml. It builds iOS FFmpeg from pinned
8.0 source and targets the actual rpcs3_emu archive with LLVM/Vulkan disabled
initially. Patch 0003 separates iOS from desktop Qt/host deps and routes Apple
JIT protection calls through util/apple_jit.hpp, which fails closed if the
symbol is absent on iOS. This is NOT the eventual JIT implementation.
No core IPA yet, no link/boot claim. macOS compilation can only be checked in
Actions; Linux local checks cover patch application, scripts and metadata
validation. Inspect the user's reported workflow result next; do not poll.
See core/README.md for remaining integration requirements.

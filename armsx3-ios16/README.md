# Current checkpoint — Build147

Fixes the older byte-shift regression test to isolate patch0076 from the new
bit-count patch. Production code matches Build146; iOS build pending.

## Previous checkpoint — Build146

Build145 graphics were confirmed OK. Build146 preserves that renderer and
uses iOS ARM64 vector operations for SPU byte population count and word
leading-zero count. Host correctness tests pass; iOS compilation and phone
performance remain unconfirmed. No FPS gain promised.

Once green, install ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start game,
repeat the same menu/car for about60seconds, Stop and share the log.

## Previous checkpoint — Build145

Build144 produced very glitchy graphics on the phone with roughly unchanged
FPS. Its bounded texture eviction is reverted. Build145 restores Build143's
production renderer patches while retaining the existing CPU optimizations.
The exact corruption mechanism is unconfirmed; clean shutdown is not proof
of correct graphics. iOS compilation and phone visual validation are pending.

Once ready, install ARMSX3_iOS16_INSTALL_THIS_IPA, use Quick start -> Start game,
test the same menu for about60seconds, then Stop and share the log and whether
graphics are restored. This recovery build does not promise an FPS gain.

## Previous checkpoint — Build144

Build143 reached the menu, then slowed to about1.12FPS across four complete
slow windows. Its61 texture-cache purges and462 completed upload batches moved
14.66GiB of pixels. Repeated purges dropped roughly288MiB to37–41MiB, discarding
useful scene content. The CPU/wakeups reports took no termination action. Stop
completed cleanly with1900 accepted presents after about9seconds of cleanup.

Build144 changes soft-budget eviction to select older texture bindings until
enough actual GPU allocation bytes are recovered. It keeps the288MiB quota,
uses a256MiB target, releases completed idle images first, and preserves active
fragment/vertex texture addresses. Shared protected pages, framebuffers, dirty
and borrowed images are excluded. GPU completion, native page-unprotect logic,
deferred destruction and driver drain protect every released allocation. Real
allocation failures retain the existing emergency recovery path.

All77 patches apply and the new patch reverses to the exact previous sources.
The current native selection, view tagging, quota, idle trim and preflight pass
host sanitizer tests: a warm scene keeps its pixels across120frames where the
old policy reloads160MiB; an8GiB modeled stream peaks at304MiB including the
existing check hysteresis. Shared-page/active-binding protection, cache-lock
refusal, both GPU-wait failures, pinned sets, deferred GC and desktop behavior
are covered. Historical reuse, upload retirement, runtime/Stop and Quick start
checks pass. Full Xcode compilation and actual phone improvement remain pending.
Scenes larger than the available cache may still require frequent uploads.

Install `ARMSX3_iOS16_INSTALL_THIS_IPA`, **Quick start -> Start game**, and try
the same menu/car screen for about60seconds. Finish with **Stop game** and share
the log/responsiveness. Imported state persists; full120 checks remain optional.
Graphics, SPU vector optimizations and input remain; audio is null; driving is
unconfirmed. Historical checkpoints follow.

# ARMSX3 for iOS 16 — P0 port checkpoint

Target: iPhone 13 Pro Max, Apple A15, iOS 16.0, Dopamine / TrollStore.
This is a source-built **platform diagnostic**, not a working PS3 emulator.
The emulator core is not linked; there is no firmware installer or game launcher yet.

Repository: `txntixnz/ARMSX3-for-iOS-16`, branch `main`.
The workflow fetches ARMSX3 at the exact commit in `ios/UPSTREAM_COMMIT`, applies
`patches/0001-uikit-metal-surface.patch`, and builds the UIKit app from `ios/`.
No Android binary or prebuilt iOS emulator is repackaged.

## First device test

1. Open the **ARMSX3 iOS 16 - P0 platform probe** Actions run for this branch.
2. Download the `ARMSX3_iOS16_P0_PLATFORM_PROBE` artifact and extract the IPA.
3. Install with your existing TrollStore setup. This is an ad-hoc-signed test
   package, not an App Store or ordinary development-provisioned app.
4. Open **ARMSX3 Port Probe**, tap **Run platform checks**, then **Test generated code (JIT)**.
5. Tap **Share diagnostic report** and send `ARMSX3-iOS16-diagnostic.json`.
   It is also saved in the app's Documents directory and exposed to Files.
   If JIT execution closes the app, reopen and share the existing report before
   rerunning checks. A pending result alone cannot identify the crash cause.

A jailbreak enables the intended JIT deployment path, but the selected installer,
process signing state and memory APIs still have to work together. The entitlement
file requests extended virtual addressing and get-task-allow; including
an entitlement does not itself prove that iOS grants it. Tests report observations.

## Implemented

- UIKit app with minimum deployment target iOS 16.0 and `-mcpu=apple-a15`.
- Actual upstream `GetCAMetalLayerFromMetalView` adapted from AppKit to UIKit.
  The app compiles that upstream file and checks its borrowed layer pointer.
- Native Metal clear + GPU readback and a visible CAMetalLayer surface.
- Four simultaneous, untouched virtual reservations matching `vm.cpp`:
  8 + 12 + 32 + 4 = **56 GiB virtual address space**, not physical RAM.
- Shared file-backed host-page alias check.
- MAP_JIT RW allocation check and optional, separate RW-to-RX ARM64 execution test.
- Persistent JSON with pending markers before device tests, share/export UI.
- Xcode/IPA build, ad-hoc signing, Mach-O arm64/iOS 16 and dependency-path checks.

The VM scan is bounded to 256 candidate addresses per region. Failure may mean
address fragmentation, an address-space/process limit or a protection policy;
it is not by itself proof that this phone cannot support the emulator.
The alias check does not exercise fixed remapping, 4 KiB guest protections or
RPCS3's exception handler. Native Metal success does not validate MoltenVK/RSX.
The tiny JIT execution test does not validate the upstream MAP_JIT allocator,
multi-threaded write protection, recompilers or memory invalidation.

## Local build

On macOS with Xcode, CMake >= 3.28 and the iPhoneOS SDK:

```bash
git clone https://github.com/ARMSX2/ARMSX3.git core
git -C core checkout 92b931b9fb5eef7f1317cb482917dfc19aceebd9
git -C core apply ../armsx3-ios16/patches/0001-uikit-metal-surface.patch
python3 armsx3-ios16/ios/scripts/audit-hook-consumers.py core
git -C core apply ../armsx3-ios16/patches/0002-ios-omit-unused-hook-arena.patch
cp -R armsx3-ios16/ios core/ios
bash core/ios/scripts/build-probe.sh
```

Submodules are intentionally not fetched for P0 because these sources do not use
them. A later full-core build needs the pinned submodules and iOS builds of its
native dependencies. Do not turn on Android macros to bypass missing dependencies.

## Remaining emulator-port work

- Native iOS core target and frontend callbacks replacing Android JNI and Qt.
- iPhoneOS builds of LLVM/JIT dependencies, FFmpeg, MoltenVK and the other libraries.
  Existing Apple build paths include macOS libraries (not valid substitutes).
- Replace desktop HID/USB assumptions with GameController input; choose audio backend.
- Connect the UIKit frame to GSFrameBase and Vulkan surface / swapchain lifecycle.
- Validate upstream JIT write protection, fault recovery, 16 KiB host pages,
  4 KiB guest tracking, shared mirrors and address reservations on-device.
- Firmware/game installation, boot lifecycle, pause/resume, configuration and logging.
- Then game-specific rendering, timing, sound, compatibility and performance tests.

ARMSX3/RPCS3 license: GPL-2.0-only; source patch and new code are supplied under
that license. Upstream has individually licensed dependencies; preserve their terms.
No PS3 firmware, games or proprietary drivers are included.

## P0.1 startup repair (build 2)

The first on-device build was reported to exit instantly with no Analytics log.
The initial entitlement template incorrectly included `dynamic-codesigning`.
TrollStore's [banned entitlement documentation](https://github.com/opa334/TrollStore#banned-entitlements)
identifies this as a launch-crash risk on A12+ devices. P0.1 removes it, also removes
irrelevant macOS JIT entitlements, and checks the final signed app for all three
TrollStore-banned keys. Device confirmation is still needed; no crash report was available.

Startup checkpoints now append to **Documents/ARMSX3-startup.log**, beginning in
`main()` before UIKit startup. The **Share logs / report** button works before running
any tests. Uncaught Objective-C exceptions are logged; OS termination before `main()`,
SIGKILL and arbitrary memory faults are not caught by that handler. No log is guaranteed
if signing or dynamic loading prevents the app from entering `main()`.
The unused upstream process-info translation unit was removed from the probe target
so its global Foundation initializer does not run before the new startup logger.

Install the new IPA over the old app in TrollStore. First check that it opens and
share the startup log. There is no need to repeat the JIT or large-memory tests until
the initial screen appears. The PS3 core is still not linked.

## P0.2 memory and JIT adaptation (build 3)

P0.1 ran on the target phone. Metal clear/readback, the UIKit surface, shared
aliases and one RW-to-RX generated ARM64 function passed. MAP_JIT returned EINVAL;
the macOS JIT write-protection symbol was absent. The original layout failed at
the 32 GiB hook arena, after the 8 and 12 GiB reservations succeeded.

This revision introduces:

- `0002-ios-omit-unused-hook-arena.patch`: an **iOS-only core source candidate**
  omitting the unused hook reservation, backing object, mapping and cleanup.
  The other regions remain 8 + 12 + 4 = 24 GiB. It is applied to the pinned
  checkout, but `vm.cpp` is **not compiled or linked by the probe target** yet.
- A pinned-source audit that rejects external uses of `g_hook_addr` or `s_hook`.
  Desktop/Android retain the original arena. Re-audit before changing upstream.
- Device comparisons of 24 GiB RW, 24 GiB PROT_NONE and original 56 GiB PROT_NONE.
  Each variant holds its regions concurrently, then releases them before the next.
- Host-page commit/reset/recommit testing with adjacent-page canaries.
- A reusable `ExecutablePage` candidate that uses RW → RX publication, never MAP_JIT
  or the absent pthread API. It is exercised by 32 alternating code rewrites and
  execution on a joined worker after each publication.
- Linux helper tests as a CI gate before building the iOS IPA.

**Next device procedure:** install build 3, tap **Run platform checks**, then
**Test JIT rewrites**, then **Share logs / report**. If it closes, share existing
logs before rerunning. Reports now use schema 2 and include `layouts` and
`page_lifecycle` fields. Passing tests establish only these primitives, not a
working PS3 core. RW→RX is process-wide protection: callers must quiesce all
executors before writing; this is not a drop-in replacement for RPCS3's live
multi-threaded code patching. That integration remains to be designed and tested.

The existing 16 KiB host page size versus 4 KiB guest tracking also remains a
separate integration issue. No firmware, guest memory sizes or game behavior have
been changed by these standalone tests.

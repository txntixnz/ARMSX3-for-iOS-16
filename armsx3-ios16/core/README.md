# ARMSX3 iOS 16 core — Build 123

Target: iPhone 13 Pro Max/A15, iOS 16.0, Dopamine and TrollStore.

Build122 passed all 36 host jobs, native compilation and the complete
ARMSX3Core dylib link. The final app executable link then failed on
CGRectGetMidX, CGRectGetMidY and CGRectGetMaxY used by the new render view.
CoreGraphics was linked by the core target but missing from the separate app
target. Build123 adds CoreGraphics to ARMSX3CoreLoadTest's explicit framework
list. Native code, all56 patches, renderer actions and GPU/CPU ownership remain
unchanged. App linking, IPA packaging and phone presentation still need CI/device
validation; use Build123 for the next Render game (10 seconds) test.

Build121 passed all 36 host jobs, compiled the full native Vulkan core and UIKit
app, and verified 522 arm64 iPhoneOS archive objects with minimum OS <=16.0.
The final dylib link then found one unresolved native function:
capture_presented_frame's non-Android fallback still had six arguments, while its
public header and VKPresent caller used eight. Build122 patch0056 corrects only
that existing fallback signature. Its disabled return behavior and Android
implementation remain unchanged. Build122 subsequently passed the full core dylib
link; Build123 corrects the app framework dependency described above.

The new graphics-host regression compiles the entire native non-Android
VKFrameGen.cpp and unchanged public header with real Vulkan ABI types and explicit
unused RSX/config include interfaces. A separate consumer retains the exact native
VKPresent capture call and exercises all frame-generation fallback APIs. It
reproduces Build121's undefined eight-argument function at link, then links and
runs the corrected iOS/macOS/Linux branches under ASAN+UBSAN. This test is an ABI
and disabled-path check; it submits no GPU work. First55 patches remain unchanged;
56 patches total. Native Vulkan rendering remains enabled and frame generation
remains off.

Build120 passed all 36 host jobs but failed the native iOS archive compile.
The renderer referenced five frame-generation settings that upstream declared
only under __ANDROID__. This caused 83 missing-member errors across swapchain,
presentation and frame-generation translation units. Build121 adds patch0055:
explicit Apple platform detection and iOS visibility for that exact settings
block. The production render action still forces frame generation off. Native
Vulkan rendering remains enabled. Build121 subsequently passed iOS compilation;
Build122 corrects the final link failure described above.

The regression compiles the complete native system_config.h and
system_config_types.h plus actual FrameGenConfig helpers against modeled config
storage interfaces. It reproduces the old iOS failure, verifies all five settings
and off/default helper behavior after patch0055, preserves Android visibility and
verifies the existing macOS/Linux field absence and adjacent Android-only shader
preset. The original first54 patches remain unchanged;55 patches total.
Build119 passed all 120 diagnostics, native firmware/disc loading and another
three-second Midnight Club: Los Angeles [BLUS30442] execution/clean stop.
Its graphics check reached **Apple A15 GPU** and passed both 1,024-pixel offscreen
clear/copy/fence/readback tests. The directly linked driver omitted the loader-only
portability enumeration extension; the optional extension/flag policy worked.
The run retained 20 joined PPU contexts, six SPUs and 49,092 completed HLE/LV2
calls. The exec_bytes/4 aggregate is a backend estimate, not measured throughput/FPS.

Build120 compiles the real native RSX Vulkan backend against the same digest-verified
MoltenVK v1.4.2 iOS static archive. **Render game (10 seconds)** creates a retained
UIKit CAMetalLayer, lends it to the native VKGSRender/Metal surface/swapchain, starts
the imported game through the existing native boot/run path, and stops after a
ten-second running window. Drawable size is bounded at 1280×720 and letterboxed
in the available viewport. Static PPU/SPU decoders, null audio, MSAA off, async
shader recompilation with two compiler threads, frame generation off and a
1,024 MiB native VRAM allocation limit are used for this first renderer attempt.
This is a renderer integration attempt; visible game content remains unverified.

Install the workflow's **ARMSX3_iOS16_INSTALL_THIS_IPA** using TrollStore. Reopen,
run all 120 tests, then tap **Render game (10 seconds)** with the retained firmware
and imported game. Keep the app open. After automatic shutdown, share the startup
log and describe what appeared on screen. If firmware/disc is missing, reuse
Install firmware / Import game folder; select the folder containing PS3_GAME and
PS3_DISC.SFB. The original Run game (3 seconds), load checks and independent
Check graphics device remain available.

Rendering success requires joined CPU execution evidence, at least one accepted
native vkQueuePresentKHR result, no presentation errors and complete GPU/CPU
teardown/config restoration. VK_SUCCESS and VK_SUBOPTIMAL_KHR are accepted; those
results do not establish meaningful game pixels or FPS. The first accepted present
is logged directly after the native queue call. No synthesized frames are counted.
The UIKit view/layer stays attached through native shutdown; the GSFrameBase
adapter has immutable dimensions and never queries UIKit from RSX threads. If
cleanup is incomplete (-2), retain the attached view/layer, close/reopen the app,
then share the previous run's log. A native crash needs that log and matching .ips.
Audio output and controller input remain pending.

The new run first performs the validated native game/title/disc/segment/firmware
checks. Only then does it grant one start and invoke native Emulator::Run(false)
on UIKit's main queue. Native RSX startup calls RunPPU; iOS ignores a stale
startup callback after a stop request. The monitor reads atomic emulator state
and CPU object counts while guest threads run. At the end, native Kill(false)
runs on the same main queue, joins threads and completes the validated teardown.
PPU registers/counters/history and SPU counters are captured only after native
joins and before context destruction. The log includes native PPU instruction
counters, completed HLE/LV2 call counts, last eight retained calls and SPU block
counters. These describe contexts still registered at shutdown; retired threads
can be absent. SPU blocks are backend-dependent and may be zero.

A successful run requires joined evidence of actual PPU instructions or completed
HLE/LV2 calls and clean teardown/config restoration. Startup timeout, paused/error
state, absent progress or incomplete cleanup reports failure. Fatal native CPU
errors can still abort the app and retain the pending-run marker. The original three-second
run uses null video/audio; Build120 has a separate native Vulkan rendering action.
Sound and controller integration remain pending. It does not establish game compatibility, menu progress or playable FPS.
Warnings/errors remain enabled while verbose native notice/trace output is
suppressed during this short run; explicit startup/execution markers remain.
PPU call history is enabled temporarily, and configuration plus channel levels
are restored after complete cleanup. Load-only checks keep guest start disabled.

Only one imported disc is retained as the active game. A successful replacement
removes the previous imported copy; rejected or incomplete imports preserve it.
The source folder is opened under its security scope with NSFileCoordinator and
copied once into staging, without a second temporary copy of the whole game.
The importer reads title/category/ID through native PARAM.SFO parsing, validates
the disc marker and executable, checks available space, copies all selected
files/directories, and rechecks source inventory and staged identity before
publication. It rejects links, unsupported node types, malformed metadata and
source changes. Free space must cover the new copy plus 256 MiB while the old
copy remains available. Copy progress is recorded in the startup log.

**Check game load** boots the imported original EBOOT.BIN through native
Emulator::BootGame, with autostart off and null video/audio. It verifies the
actual native title, title ID and category against PARAM.SFO, the selected
executable, /dev_bdvd and /dev_bdvd/PS3_GAME mounts, SFO/EBOOT paths, and a
representative asset path when present. Segment/entry/real-firmware/stopped-PPU
checks and fully-stopped cleanup/configuration restoration are shared with the
validated cached-ELF check. The separate Run game action advances guest execution; Render game adds the native Vulkan display attempt.

**Inspect EBOOT / ELF** and **Check runtime load** remain available for the
independent cached-executable path. They are optional when importing a disc
folder. The existing prepared executable is preserved during game import.

Firmware import uses native PUP authentication, SCE package decryption and TAR
extraction. Files are extracted into a fresh staging directory. Required firmware
files are verified before the existing dev_flash directory is replaced; a failed
publication restores the prior directory. Failure detail is included in the log.

Executable inspection reads the header and sends SELF to native decryption or
plain ELF directly to native PPU parsing, independent of filename or boot state.
It checks loadable segment bounds and stores the prepared ELF in the core cache.
Only the selected executable is imported; a complete game's assets are not
imported here. P120 also checks both native debug SELF header encodings and
rejects unknown or truncated ELF headers.

Runtime loading calls native Emulator::BootGame with a temporary config override:
static PPU/SPU decoders, null video/audio devices, and autostart disabled. Native
frontend callbacks dispatch to UIKit's main queue and create the real null RSX,
input and audio objects. The check requires the ready state, readable mapped
executable segments, the registered entry descriptor, a loaded liblv2 firmware
module and stopped PPU contexts. HLE fallback does not count as a firmware load.
It then calls native Kill(false), waits for a fully stopped emulator with zero
live CPU threads, drains final main-queue cleanup, and restores configuration.
Incomplete cleanup disables further actions until the app is reopened.

The cached-executable check loads without game metadata/assets. The imported
game check adds those paths and validates native title/disc loading. Neither
check starts the guest entry or produces picture/audio.

The production core still uses the validated interpreter/immutable JIT path.
LLVM remains disabled. The native RSX Vulkan/MoltenVK backend is enabled for
the separate Render game action; the original Run game keeps null video/audio.
Native presentation on the phone, device audio and controller input remain
unverified or pending. Successful
readiness checks and executable inspection are not a playable-game result.

The workflow keeps pinned dependencies and the original 49 production patches,
plus patch0050 for unused JIT-arena finalization and patch0051 for joined-context
observation and the iOS RSX startup/stop guard, plus patch0052 for static SPU
startup and patch0053 for static SPU thread entry, plus patch0054 for the native
Vulkan importer, optional Apple portability policy, borrowed iOS layer and present
observer plus patch0055 for iOS visibility of shared Vulkan configuration settings
plus patch0056 for the non-Android frame-generation capture signature
(56 patches total).
34 synchronization host profiles plus the intake and graphics host checks gate the iOS
compile, full link, signed bundle validation and one installable IPA. Matching
core symbols and build logs remain available as separate artifacts.
Build113's workflow produced the tested installable IPA. The historical patch
validator remains scoped to its exact first 49 patches while preparation applies
all 56. The host job also checks native PSF parsing and complete game
import. Local sanitizer
checks use `ASAN_OPTIONS=detect_leaks=0` because LeakSanitizer cannot inspect
processes in this environment.

Local intake validation uses actual native PUP/SHA1 code, SELF routing/debug
header removal and real filesystem rename/rollback. It reproduces the Build 109
failure and verifies that rejected inputs preserve the last prepared ELF.
TAR/retail crypto/ELF/backend interfaces are modeled in the host harness; device
probes use the original native implementations. Real firmware installation and
real EBOOT decryption were verified in Build 110's device logs.

The runtime host check compiles production runtime/frontend code against all 49
native callback signatures and the actual BootGame wrapper. It tests temporary
configuration, prerequisites, mapped-segment/firmware/context checks, partial
failure, delayed cleanup, timeout, queue/wake behavior and restoration. Native
Load/VM/FXO/device/config backends are modeled there. The host cleanup now also
executes the native JIT finalizer and actual Apple portability boundary. A
separate regression reproduces Build 111's abort, checks 64 empty-arena lifecycle
cycles with a real immutable executable page, retains rejection of six nonempty
counter/snapshot cases, and preserves macOS/Linux reset/restore branches with
modeled arena operations. Cached-executable loading and complete cleanup passed
on the Build113 phone.
Host game scenarios additionally reject wrong title/category/executable/disc
mounts and missing asset mappings. Native game-folder loading, coordinated import and original SELF loading passed
on the Build114 phone. Build116 reached running state and actual game startup
including guest-created SPURS groups, PPU handler threads, firmware module loads
and game-content calls. It aborted at SPU thread entry before completing the
three-second window or joined capture/cleanup. Build117 completed that window and clean teardown on the phone.
Actions compiles for iOS.

The game import host check compiles production GameImport.cpp with the pinned
native PSF reader, entry types and SFB validation. An independently encoded SFO
fixture drives actual disk copy/replacement and title identity. Negative cases
cover bounded/unterminated metadata, category/ID/title errors, insufficient space,
links, overlapping roots, idle guards, source changes and corrupted staged
executables; the previous game and stage cleanup are checked. Its executable
validator is an interface model, separately covered by the native intake tests.

The runtime host suite also compiles actual native Run/RunPPU and the patched
RSX callback with production frontend, capture and execution-window code. Guest
work, RSX scheduling, VM/FXO/device backends and UIKit dispatch are host models.
It covers single-use start permission, startup timeout, zero-progress/paused
results, clean stop/config/log-level restoration, late startup callbacks, and
one-shot joined capture that never reads an active context. The patch validator
reconstructs pinned source plus the exact first50 patches, applies0051, verifies
the capture follows native thread joins/precedes context destruction and checks
that the remaining native source is unchanged. These host results do not replace
the device guest-run test.

The SPU startup regression reconstructs the exact pinned source plus all prior
patches, reproduces the Build115 missing-API abort, and compiles the actual native
startup prefix and write guard with the real Apple portability boundary. Static
iOS startup fills all heap dispatcher slots and retains an immutable executable
page across repeated setup; dynamic/asmjit/LLVM paths still reject the absent API.
macOS guard pairing and Linux behavior are retained. The runtime host suite now
also crosses that actual prefix during modeled PPU initialization. Cache-file I/O
and compiler work after the prefix are explicit host interfaces; source checks
verify that the patch leaves that entire continuation byte-for-byte unchanged.
These sanitizer checks do not establish full native cache-backend or device game
execution success.

The SPU entry regression reconstructs pinned native source plus the exact first52
patches, applies0053 and verifies that the entire remaining SPUThread.cpp is
unchanged. It compiles the complete actual cpu_task and old_interpreter bodies,
reproduces Build116's missing-API abort and passes the patched iOS static/no-JIT
path through repeated six-thread groups and raw/isolated pre-stop entries. It
checks native PC/interrupt setup, interpreter routing, stop/flag cleanup and
immutable RX-byte preservation. Dynamic/asmjit/LLVM and static-with-JIT entries
still reject the missing API; macOS protection and Linux behavior remain. CPU
state, local storage, instruction-table handlers, group/logging/platform interfaces
and JIT gateway are host models. This checks native loops, not the full native
SPU ISA, scheduler, ARM gateway or a successful phone execution window.

The graphics library is MoltenVK v1.4.2, fetched from the Khronos release with an
exact SHA256. The package verifier parses its XCFramework and Mach-O archive
members, requiring arm64 device-iOS objects with deployment target <=16.0 and
rejecting simulator/macOS slices. The build links the static archive plus the
required iOS frameworks, and includes its license and runtime guide in the app.
Build120 changes the native core backend to USE_VULKAN=ON using that same verified archive.

A separate graphics-host job compiles production GraphicsDevice/GraphicsCheck
with ASAN+UBSAN against real Vulkan/lavapipe and Khronos synchronization validation.
It verifies repeated two-color GPU clear/copy/fence/readback, idle/thread guards,
concurrent rejection and injected instance/device/map/pixel/device-loss/submission/timeout
failures. Failure return values and core-idle interfaces are modeled; Vulkan
commands execute through the real software driver. A timeout preserves the whole
owner and blocks reuse, avoiding destruction while work might still be queued.
Linux results do not verify Apple's driver or iOS linking. The existing 35 host
jobs plus this graphics job gate the IPA build. Build118 did not reach graphics device creation; Build119 passed both readbacks
on the A15 phone. Build120 integrates native RSX rendering and UIKit presentation;
that full backend still needs CI compilation and phone validation.

The graphics regression now also compiles the production Apple preprocessor path.
A filtered instance-extension list models directly linked MoltenVK while keeping
actual lavapipe GPU commands. Reinstating Build118's exact Apple-only rejection
reproduces its failure before instance creation. Build119 passes both advertised
loader-extension and absent direct-driver-extension cases, preserving correct
flag/extension pairing. The original cleanup/concurrency/failure cases remain.
This is a host regression for instance setup, not an Apple GPU success claim.

Build120 host coverage also compiles the production frame adapter against the
actual native GSFrameBase interface and native GSRender constructor/destructor,
context and exit methods, covering 64 ownership cycles and failed/incomplete
releases. Render flow tests inject success/no-present/error/suboptimal queue
outcomes with modeled guest/device backends and verify clean teardown/config
restoration. A separate exact-patch54 check compiles the real native present
method plus both Apple instance extension policies against host interfaces,
checks hook order/return values and configures the actual iOS CMake import branch
across sibling scopes/repeated includes. These do not compile the full native
Vulkan renderer or prove iOS presentation; the full-link CI gate and phone log
remain required.

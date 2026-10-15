# ARMSX3 iOS 16 core — Build 118

Target: iPhone 13 Pro Max/A15, iOS 16.0, Dopamine and TrollStore.
The installable app links the actual pinned rpcs3_emu core. Build117 passed all
120 diagnostics, real firmware/game loading, and the complete three-second
**Midnight Club: Los Angeles [BLUS30442]** run. Native running state, real PPU/SPU
work, 20 joined PPU contexts, six SPUs, 51,678 completed HLE/LV2 calls and fully
stopped cleanup were recorded. The game set up RSX memory/context/display buffers,
created render/streamer/audio threads and performed SPU DMA. Static SPU block
counters remained zero, as expected for this backend. Native exec_bytes/4 is a
backend counter estimate, not a measured instruction rate or FPS.

Build118 adds **Check graphics device** using a pinned iOS MoltenVK static library.
It creates a real Vulkan/Metal graphics device and queue, clears an offscreen
RGBA8 image red then blue, copies each result to host-visible memory, waits on
GPU fences and verifies all 1,024 pixels per pass. It logs device/API/driver and
selected capabilities, then destroys the device and resources. This establishes
the driver path; native RSX Vulkan rendering, shaders, UIKit swapchain presentation,
audio output and controller input remain pending. No game picture is expected.

After the workflow succeeds, download **ARMSX3_iOS16_INSTALL_THIS_IPA** and
install its IPA through TrollStore. Reopen and tap **Run all tests**. Once all
120 pass:

1. Tap **Check graphics device** and share the startup log with its result.
   This check needs neither firmware nor a new game import.
2. Optionally repeat **Run game (3 seconds)** with the retained firmware/disc
   to verify execution after adding the graphics library. Keep the app open.
3. If firmware/game is reported missing, reuse **Install firmware** and/or
   **Import game folder**. Select the folder containing PS3_GAME and PS3_DISC.SFB.
4. A graphics timeout retains its GPU resources and requires reopening the app.
   If any action crashes, share its unfinished log and matching .ips report.

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
errors can still abort the app and retain the pending-run marker. This initial
run uses null video/audio; display, sound and controller integration remain
pending. It does not establish game compatibility, menu progress or playable FPS.
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
validated cached-ELF check. The separate Run game action advances guest execution; display remains pending.

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
LLVM and the native RSX Vulkan/MoltenVK renderer are disabled. The separate
MoltenVK device check does not enable that renderer. The Run game action requests native
guest execution; renderer presentation, device audio and controller input remain
future integration work. Successful
readiness checks and executable inspection are not a playable-game result.

The workflow keeps pinned dependencies and the original 49 production patches,
plus patch0050 for unused JIT-arena finalization and patch0051 for joined-context
observation and the iOS RSX startup/stop guard, plus patch0052 for static SPU
startup and patch0053 for static SPU thread entry (53 patches total).
34 synchronization host profiles plus the intake and graphics host checks gate the iOS
compile, full link, signed bundle validation and one installable IPA. Matching
core symbols and build logs remain available as separate artifacts.
Build113's workflow produced the tested installable IPA. The historical patch
validator remains scoped to its exact first 49 patches while preparation applies
all 53. The host job also checks native PSF parsing and complete game
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
The native core backend remains compiled with USE_VULKAN=OFF.

A separate graphics-host job compiles production GraphicsDevice/GraphicsCheck
with ASAN+UBSAN against real Vulkan/lavapipe and Khronos synchronization validation.
It verifies repeated two-color GPU clear/copy/fence/readback, idle/thread guards,
concurrent rejection and injected instance/device/map/pixel/device-loss/submission/timeout
failures. Failure return values and core-idle interfaces are modeled; Vulkan
commands execute through the real software driver. A timeout preserves the whole
owner and blocks reuse, avoiding destruction while work might still be queued.
Linux results do not verify Apple's driver or iOS linking. The existing 35 host
jobs plus this graphics job gate the IPA build. Phone graphics success remains
pending. Native RSX rendering and UIKit presentation are the next integration.

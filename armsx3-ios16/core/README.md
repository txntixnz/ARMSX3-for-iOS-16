# ARMSX3 iOS 16 core — Build 115

Target: iPhone 13 Pro Max/A15, iOS 16.0, Dopamine and TrollStore.
The installable app links the actual pinned rpcs3_emu core. Build114 passed all
120 diagnostics, imported19 files/5,668,431,532 bytes, and natively loaded
**Midnight Club: Los Angeles [BLUS30442]**. Its real title/category, original
EBOOT, PARAM.SFO, disc roots and carchive_audio.rpf asset path matched. Native
loading mapped two nonempty executable segments, loaded liblv2 firmware and
completed thread/VM/JIT cleanup. The guest entry remained stopped.
Build115 adds **Run game (3 seconds)** with an explicit native guest start,
automatic stop and execution evidence captured from joined CPU contexts.

After the workflow succeeds, download **ARMSX3_iOS16_INSTALL_THIS_IPA** and
install its IPA through TrollStore. Reopen and tap **Run all tests**. Once all
120 pass:

1. Reuse the installed firmware and imported game if retained after updating.
2. If either is missing, **Install firmware** with PS3UPDAT.PUP and/or
   **Import game folder** with the folder containing both PS3_GAME and
   PS3_DISC.SFB (including PARAM.SFO, USRDIR/EBOOT.BIN and all assets).
3. Tap **Run game (3 seconds)** and keep the app open. Native startup has a
   15-second budget; the three-second window begins when running state is reached.
4. Share the startup log after automatic stop/cleanup. If it crashes, share the
   log from that unfinished run plus the matching .ips crash report.

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
LLVM and Vulkan/MoltenVK are disabled. The short interpreter run begins real
guest execution; renderer presentation, device audio and controller input remain
future integration work. Successful
readiness checks and executable inspection are not a playable-game result.

The workflow keeps pinned dependencies and the original 49 production patches,
plus patch0050 for unused JIT-arena finalization and patch0051 for joined-context
observation and the iOS RSX startup/stop guard (51 patches total).
34 synchronization host profiles plus the new intake host check gate the iOS
compile, full link, signed bundle validation and one installable IPA. Matching
core symbols and build logs remain available as separate artifacts.
Build113's workflow produced the tested installable IPA. The historical patch
validator remains scoped to its exact first 49 patches while preparation applies
all 51. The host job also checks native PSF parsing and complete game
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
on the Build114 phone. Device guest execution awaits Build115. Actions
compiles for iOS.

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

# ARMSX3 iOS 16 core — Build 114

Target: iPhone 13 Pro Max/A15, iOS 16.0, Dopamine and TrollStore.
The installable app links the actual pinned rpcs3_emu core. Build113 passed all
120 diagnostics on the phone, loaded the user's executable and real liblv2
firmware module, then completed native thread/VM/JIT cleanup without a crash.
The executable mapped two nonempty segments, liblv2 registered two segments and
3635 functions, and the PPU context remained stopped throughout.
Build114 adds complete disc-folder import and **Check game load**, retaining
**Check runtime load** and the same 120 readiness checks.

After the workflow succeeds, download **ARMSX3_iOS16_INSTALL_THIS_IPA** and
install its IPA through TrollStore. Reopen and tap **Run all tests**. Once all
120 pass:

1. Reuse installed firmware 4.93. If missing, **Install firmware** with PS3UPDAT.PUP.
2. Tap **Import game folder** and select the folder containing both
   **PS3_GAME** and **PS3_DISC.SFB**. Select the folder itself, not EBOOT.BIN or
   PS3_DISC.SFB. The selected tree must include PS3_GAME/PARAM.SFO and
   PS3_GAME/USRDIR/EBOOT.BIN plus the game's assets.
3. Keep the app open while the files are copied, then tap **Check game load**.
4. Share the startup log after loading and cleanup finish.

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
validated cached-ELF check. Guest execution and display remain subsequent work.

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
LLVM and Vulkan/MoltenVK are disabled. Real game execution, renderer presentation,
device audio and controller input remain future integration work. Successful
readiness checks and executable inspection are not a playable-game result.

The workflow keeps pinned dependencies and the original 49 production patches,
plus patch 0050 for unused JIT-arena finalization.
34 synchronization host profiles plus the new intake host check gate the iOS
compile, full link, signed bundle validation and one installable IPA. Matching
core symbols and build logs remain available as separate artifacts.
Build113's workflow produced the tested installable IPA. The historical patch
validator remains scoped to its exact first 49 patches while preparation applies
all 50. Build114's host job also checks native PSF parsing and complete game
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
mounts and missing asset mappings. Native game-folder loading, iOS file-provider
coordination and original SELF loading await the Build114 device run. Actions
compiles for iOS.

The game import host check compiles production GameImport.cpp with the pinned
native PSF reader, entry types and SFB validation. An independently encoded SFO
fixture drives actual disk copy/replacement and title identity. Negative cases
cover bounded/unterminated metadata, category/ID/title errors, insufficient space,
links, overlapping roots, idle guards, source changes and corrupted staged
executables; the previous game and stage cleanup are checked. Its executable
validator is an interface model, separately covered by the native intake tests.

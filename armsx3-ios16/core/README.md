# ARMSX3 iOS 16 core — Build 113

Target: iPhone 13 Pro Max/A15, iOS 16.0, Dopamine and TrollStore.
The installable app links the actual pinned rpcs3_emu core. Build 110 passed
all 120 device diagnostics, installed the user's firmware 4.93 (23 packages),
and decrypted/parsed their EBOOT.BIN with five loadable segments. Build 111
reached native runtime ready state with two nonempty mapped segments, loaded
liblv2.sprx (two segments, 3635 functions), and one stopped PPU context, then
aborted during JIT cleanup. Build 112 repairs that unused-arena finalization
but its workflow stopped before compilation at an outdated patch-count check.
Build 113 corrects that historical validator and keeps the cleanup repair,
**Check runtime load** and the same 120 readiness checks.

After the workflow succeeds, download **ARMSX3_iOS16_INSTALL_THIS_IPA** and
install its IPA through TrollStore. Reopen the app and tap **Run all tests**.
The sequence stops at the first failed stage; share the startup log if it fails.

Once all 120 tests pass:

1. If firmware is missing, tap **Install firmware** and choose **PS3UPDAT.PUP**.
2. **Inspect EBOOT / ELF** decrypts and prepares your selected executable.
3. Tap **Check runtime load**. Keep the app open until loading and cleanup
   finish, then share the startup log. The prepared ELF and installed firmware
   from Build 110 can be reused if they remain available after the update.

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

This loads the cached executable without the game's folder, PARAM.SFO or assets.
Title identity, disc mounting and complete game import are subsequent work.
The guest entry is not run and no picture or audio is produced by this check.

The production core still uses the validated interpreter/immutable JIT path.
LLVM and Vulkan/MoltenVK are disabled. Real game execution, renderer presentation,
device audio and controller input remain future integration work. Successful
readiness checks and executable inspection are not a playable-game result.

The workflow keeps pinned dependencies and the original 49 production patches,
plus patch 0050 for unused JIT-arena finalization.
34 synchronization host profiles plus the new intake host check gate the iOS
compile, full link, signed bundle validation and one installable IPA. Matching
core symbols and build logs remain available as separate artifacts.
Build 112 passed all 35 host jobs. Build 113's complete core preparation step
passed locally against the pristine pinned source, including all historical
checks, all 50 patch applications and the core/iOS overlays. Local sanitizer
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
modeled arena operations. Runtime loading reached ready state on the phone;
complete cleanup must still be verified in Build 113. Actions compiles for iOS.

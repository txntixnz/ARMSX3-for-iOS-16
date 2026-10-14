# ARMSX3 iOS 16 core — Build 109

Target: iPhone 13 Pro Max/A15, iOS 16.0, Dopamine and TrollStore.
The installable app links the actual pinned rpcs3_emu core. Build 108 passed
all 112 device diagnostics. Build 109 adds firmware installation and selected
executable inspection, plus eight focused readiness checks (120 total).

After the workflow succeeds, download **ARMSX3_iOS16_INSTALL_THIS_IPA** and
install its IPA through TrollStore. Reopen the app and tap **Run all tests**.
The sequence stops at the first failed stage; share the startup log if it fails.

Once all 120 tests pass:

1. Tap **Install firmware** and choose your **PS3UPDAT.PUP** in Files.
2. Keep the app open until installation finishes, then share the startup log.
3. **Inspect EBOOT / ELF** can validate your own executable and prepare its
   decrypted ELF for the next runtime milestone. It does not start the game.

Firmware import uses native PUP authentication, SCE package decryption and TAR
extraction. Files are extracted into a fresh staging directory. Required firmware
files are verified before the existing dev_flash directory is replaced; a failed
publication restores the prior directory. Failure detail is included in the log.

Executable inspection uses native SELF decryption and PPU ELF parsing. It checks
loadable segment bounds and stores the prepared ELF in the core cache. Only the
selected executable is imported; a complete game's assets are not imported here.

The production core still uses the validated interpreter/immutable JIT path.
LLVM and Vulkan/MoltenVK are disabled. Real game execution, renderer presentation,
device audio and controller input remain future integration work. Successful
readiness checks and executable inspection are not a playable-game result.

The workflow keeps pinned dependencies and all 49 existing production patches.
34 synchronization host profiles plus the new intake host check gate the iOS
compile, full link, signed bundle validation and one installable IPA. Matching
core symbols and build logs remain available as separate artifacts.

Local intake validation uses the actual native PUP/SHA1 code and real filesystem
rename/rollback. TAR/SCE/ELF/backend interfaces are modeled in that host harness;
the app and its device probes link the original native implementations. Native
firmware installation must be verified using the user's PUP on the phone.

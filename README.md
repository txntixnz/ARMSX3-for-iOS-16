# ARMSX3 for iOS 16

Experimental ARMSX3 port targeting **iPhone 13 Pro Max · A15 · iOS 16 · Dopamine**.

**Current stage: P0.2 memory/JIT adaptation tests. PS3 game boot is not implemented yet.**

The GitHub Actions workflow builds a native iOS test app to check Metal, virtual
memory and JIT behavior before integrating the emulator core.

- [Builds and IPA artifacts](https://github.com/txntixnz/ARMSX3-for-iOS-16/actions/workflows/build-armsx3-ios16.yml)
- [Installation, tests and port status](armsx3-ios16/README.md)
- [Development handoff](armsx3-ios16/HANDOFF_TO_NEW_CHAT.md)
- [Upstream ARMSX3](https://github.com/ARMSX2/ARMSX3)

GPL-2.0-only. No firmware or games included. Not an official ARMSX3 or RPCS3 release.

A separate **P1 core compilation** workflow now targets the actual upstream
`rpcs3_emu` library for iOS 16 arm64. This is compilation bring-up, not a
playable IPA. See [core build scope](armsx3-ios16/core/README.md).

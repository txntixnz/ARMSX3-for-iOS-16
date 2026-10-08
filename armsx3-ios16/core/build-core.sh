#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd "$1" && pwd)"
ffmpeg_dir="$(cd "$2" && pwd)"
build_dir="$source_dir/build-ios-core"
sdk="$(xcrun --sdk iphoneos --show-sdk-path)"
# Avoid host pkg-config/Homebrew libraries being mistaken for device libraries.
export PKG_CONFIG_LIBDIR="$ffmpeg_dir/lib/pkgconfig"
export PKG_CONFIG_PATH=""
cmake -S "$source_dir" -B "$build_dir" -G Ninja \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_SYSTEM_PROCESSOR=arm64 \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_SYSROOT="$sdk" \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=16.0 -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER="$(xcrun --sdk iphoneos --find clang)" \
  -DCMAKE_CXX_COMPILER="$(xcrun --sdk iphoneos --find clang++)" \
  -DCMAKE_OBJCXX_COMPILER="$(xcrun --sdk iphoneos --find clang++)" \
  -DCMAKE_C_FLAGS="-mcpu=apple-a15 -gline-tables-only" -DCMAKE_CXX_FLAGS="-mcpu=apple-a15 -gline-tables-only" \
  -DCMAKE_OBJCXX_FLAGS="-mcpu=apple-a15 -gline-tables-only" \
  -DCMAKE_FIND_ROOT_PATH="$sdk;$ffmpeg_dir" \
  -DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY \
  -DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY \
  -DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY \
  -DCMAKE_FIND_ROOT_PATH_MODE_PROGRAM=NEVER \
  -DARMSX3_FFMPEG_ROOT="$ffmpeg_dir" \
  -DWITH_LLVM=OFF -DUSE_VULKAN=OFF -DUSE_NATIVE_INSTRUCTIONS=OFF \
  -DUSE_LTO=OFF -DUSE_PRECOMPILED_HEADERS=OFF \
  -DUSE_SDL=OFF -DUSE_FAUDIO=OFF -DUSE_LIBEVDEV=OFF \
  -DUSE_DISCORD_RPC=OFF -DUSE_GAMEMODE=OFF \
  -DUSE_SYSTEM_CURL=OFF -DUSE_SYSTEM_ZLIB=OFF -DUSE_SYSTEM_OPENCV=OFF \
  -Dprotobuf_FORCE_FETCH_DEPENDENCIES=ON \
  -DBUILD_RPCS3_TESTS=OFF -DARMSX3_BUILD_LOADTEST=ON
# Keep going across independent units to collect useful compiler diagnostics,
# but preserve a failing exit status. No placeholder implementations are added.
cmake --build "$build_dir" --target rpcs3_emu --parallel 3 -- -k 0

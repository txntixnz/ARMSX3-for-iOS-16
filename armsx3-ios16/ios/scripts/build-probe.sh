#!/bin/bash
set -euo pipefail
PORT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PORT_BUILD="${PORT_BUILD_DIR:-$PORT_ROOT/build-ios-probe}"
PORT_DIST="${PORT_DIST_DIR:-$PORT_ROOT/dist-ios}"
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Requires macOS and Xcode with the iPhoneOS SDK.' >&2
  exit 2
fi
xcrun --sdk iphoneos --show-sdk-path
cmake -S "$PORT_ROOT/ios" -B "$PORT_BUILD" -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=16.0
cmake --build "$PORT_BUILD" --config Release --parallel 3
PORT_APP="$PORT_BUILD/Release-iphoneos/ARMSX3iOSProbe.app"
if [[ ! -d "$PORT_APP" ]]; then
  echo "Expected app missing: $PORT_APP" >&2
  exit 3
fi
# Ad-hoc signing preserves the requested entitlement blob for installers which
# support it. The operating system / installer still decides what is granted.
# This is NOT an App Store/development-provisioned installable application.
codesign --force --sign - --entitlements "$PORT_ROOT/ios/Entitlements.plist" "$PORT_APP"
codesign --verify --strict --verbose=2 "$PORT_APP"
python3 "$PORT_ROOT/ios/scripts/verify-bundle.py" "$PORT_APP"
mkdir -p "$PORT_DIST"
PORT_STAGE="$(mktemp -d)"
trap 'rm -rf "$PORT_STAGE"' EXIT
mkdir -p "$PORT_STAGE/Payload"
ditto "$PORT_APP" "$PORT_STAGE/Payload/ARMSX3iOSProbe.app"
ditto -c -k --keepParent "$PORT_STAGE/Payload" "$PORT_DIST/ARMSX3_iOS16_P0_PLATFORM_PROBE.ipa"
shasum -a 256 "$PORT_DIST/ARMSX3_iOS16_P0_PLATFORM_PROBE.ipa" > "$PORT_DIST/SHA256SUMS.txt"
echo "Built $PORT_DIST/ARMSX3_iOS16_P0_PLATFORM_PROBE.ipa"

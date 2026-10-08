#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd "$1" && pwd)"
build_dir="$source_dir/build-ios-core"
cmake --build "$build_dir" --target ARMSX3CoreLoadTest --parallel 3 -- -k 0
app="$build_dir/ios-core/loadtest/ARMSX3CoreLoadTest.app"
core="$app/Frameworks/libARMSX3Core.dylib"
test -f "$core"
test "$(xcrun lipo -archs "$core")" = arm64
xcrun vtool -show-build "$core" > "$build_dir/core-platform.txt"
xcrun otool -L "$core" > "$build_dir/core-libraries.txt"
python3 - "$build_dir" <<'PY'
import pathlib,re,sys
root=pathlib.Path(sys.argv[1])
s=(root/'core-platform.txt').read_text()
assert re.search(r'platform\s+IOS\s',s),s
assert re.search(r'minos\s+16\.0(?:\.0)?\s',s),s
s=(root/'core-libraries.txt').read_text()
for bad in ['AppKit.framework','/opt/homebrew/','/usr/local/','.so']:
    assert bad not in s,s
print('PASS: embedded core targets arm64 iOS 16.0 without host dependency paths')
PY
mkdir -p "$source_dir/core-symbols"
xcrun dsymutil "$core" -o "$source_dir/core-symbols/libARMSX3Core.dylib.dSYM"
xcrun dwarfdump --uuid "$core" > "$source_dir/core-symbols/UUIDS.txt"
xcrun dwarfdump --uuid "$source_dir/core-symbols/libARMSX3Core.dylib.dSYM" >> "$source_dir/core-symbols/UUIDS.txt"
# Keep an exact unsigned Mach-O for offline address-to-source inspection.
cp "$core" "$source_dir/core-symbols/"
codesign --force --sign - "$core"
codesign --force --sign - --entitlements "$source_dir/ios/Entitlements.plist" "$app"
codesign --verify --deep --strict "$app"
python3 "$source_dir/ios/scripts/verify-bundle.py" "$app"
mkdir -p "$source_dir/dist-ios-core"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/Payload"
ditto "$app" "$stage/Payload/ARMSX3CoreLoadTest.app"
ditto -c -k --keepParent "$stage/Payload" "$source_dir/dist-ios-core/ARMSX3_iOS16_P2_CORE_LOAD_TEST.ipa"
shasum -a 256 "$source_dir/dist-ios-core/ARMSX3_iOS16_P2_CORE_LOAD_TEST.ipa" > "$source_dir/dist-ios-core/SHA256SUMS.txt"

#!/usr/bin/env bash
set -euo pipefail
destination="$1"
test ! -e "$destination"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
curl --fail --location --retry 3 --output "$stage/MoltenVK-ios.tar" \
  https://github.com/KhronosGroup/MoltenVK/releases/download/v1.4.2/MoltenVK-ios.tar
python3 - "$stage/MoltenVK-ios.tar" "$stage/unpacked" <<'PY'
import hashlib,pathlib,sys,tarfile
p=pathlib.Path(sys.argv[1])
assert hashlib.sha256(p.read_bytes()).hexdigest()=='b5d947b1660e6e9fed40b9cd2387e160aaab9e80b775c0cef7e14059405178c1','MoltenVK archive digest mismatch'
with tarfile.open(p) as archive: archive.extractall(sys.argv[2],filter='data')
PY
python3 "$(dirname "$0")/verify-moltenvk.py" "$stage/unpacked/MoltenVK/MoltenVK"
mkdir -p "$(dirname "$destination")"
mv "$stage/unpacked/MoltenVK/MoltenVK" "$destination"
mkdir -p "$destination/licenses"
cp "$stage/unpacked/MoltenVK/LICENSE" "$destination/licenses/MoltenVK-LICENSE"
cp "$stage/unpacked/MoltenVK/Docs/MoltenVK_Runtime_UserGuide.md" "$destination/licenses/"

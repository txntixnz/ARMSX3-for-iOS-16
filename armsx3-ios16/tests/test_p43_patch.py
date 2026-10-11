"""Check memory patch against byte-exact pinned source, including EOF.

Usage: python test_p43_patch.py upstream-armsx3/rpcs3/Emu/Cell/lv2/sys_memory.cpp
Run before applying patches. The source blob must match the workflow pin.
"""
from pathlib import Path
import hashlib
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent
source = Path(sys.argv[1]) if len(sys.argv) == 2 else root / 'sys_memory.build60.cpp'
baseline = source.read_bytes()
blob = b'blob ' + str(len(baseline)).encode() + b'\0' + baseline
assert hashlib.sha1(blob).hexdigest() == 'c3ac2a007c78791b3bbf3de81f78549dc5115f6d', 'Use byte-exact pinned source; do not append newlines'
patch_path = root / 'patches/0041-ios-guest-memory-syscalls-probe.patch'
if not patch_path.exists():
    patch_path = root.parent / 'patches/0041-ios-guest-memory-syscalls-probe.patch'
patch = patch_path.read_bytes()
target = 'rpcs3/Emu/Cell/lv2/sys_memory.cpp'
section = patch[patch.index(('--- a/' + target).encode()):]
with tempfile.TemporaryDirectory() as temp:
    work = Path(temp)
    file = work / target
    file.parent.mkdir(parents=True)
    file.write_bytes(baseline)
    args = ['git', 'apply', '--include=' + target]
    subprocess.run(args + ['--check', '-'], input=patch, cwd=work, check=True)
    subprocess.run(args + ['-'], input=patch, cwd=work, check=True)
    updated = file.read_bytes()
    assert b'armsx3_ios_memory_probe_and_call' in updated
    marker = b'\n\n#if defined(__APPLE__) && TARGET_OS_IPHONE\n// Stopped diagnostic only.'
    unchanged = updated.split(marker, 1)[0]
    unchanged = unchanged.replace(b'#if defined(__APPLE__)\n#include <TargetConditionals.h>\n#endif\n#include "Emu/System.h"\n', b'', 1)
    assert unchanged == baseline, 'Production services changed'
    subprocess.run(args + ['--reverse', '--check', '-'], input=patch, cwd=work, check=True)
    subprocess.run(args + ['--reverse', '-'], input=patch, cwd=work, check=True)
    assert file.read_bytes() == baseline
    # Recreate build61's erroneous trailing-blank context. Exact source rejects it.
    broken = section.replace(b'@@ -537,3 +541,43 @@\n \t// Simply destroy parent\n \treturn sys_memory_container_destroy(cpu, cid);\n }\n+\n', b'@@ -538,3 +542,42 @@\n \treturn sys_memory_container_destroy(cpu, cid);\n }\n \n', 1)
    assert broken != section
    result = subprocess.run(args + ['--check', '-'], input=broken, cwd=work, capture_output=True)
    assert result.returncode != 0 and b'patch does not apply' in result.stderr
print('PASS: exact pinned blob, corrected apply/reverse, unchanged services; build61 EOF mismatch reproduced')

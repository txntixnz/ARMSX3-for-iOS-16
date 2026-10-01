#!/usr/bin/env python3
"""Reject new hook-arena consumers before applying the iOS omission patch."""
from pathlib import Path
import re
import subprocess
import sys
root = Path(sys.argv[1])
expected = (Path(__file__).resolve().parents[1] / 'UPSTREAM_COMMIT').read_text().strip()
actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
if actual != expected:
    raise SystemExit('Upstream revision changed: re-audit hook arena before porting')
vm = Path('rpcs3/Emu/Memory/vm.cpp')
consumers = []
# Search tracked sources, headers, assembly and scripts, not just C++ files.
tracked = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z']).split(b'\0')
for raw in tracked:
    if not raw:
        continue
    relative = Path(raw.decode())
    path = root / relative
    if relative == vm or not path.is_file():
        continue
    data = path.read_bytes()
    if re.search(rb'\b(?:g_hook_addr|s_hook)\b', data):
        consumers.append(str(relative))
if consumers:
    raise SystemExit('Hook arena now has external consumers: ' + ', '.join(consumers))
print('Pinned-source audit passed: hook-arena symbols have no consumers outside vm.cpp')

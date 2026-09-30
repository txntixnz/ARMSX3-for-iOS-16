#!/usr/bin/env python3
"""Fail packaging if the produced Mach-O does not target arm64 / iOS 16."""
import pathlib
import plistlib
import re
import subprocess
import sys
app = pathlib.Path(sys.argv[1])
with (app / 'Info.plist').open('rb') as stream:
    info = plistlib.load(stream)
assert info['MinimumOSVersion'] == '16.0', info
binary = app / info['CFBundleExecutable']
arch = subprocess.check_output(['xcrun', 'lipo', '-archs', str(binary)], text=True).strip()
assert arch == 'arm64', arch
load_commands = subprocess.check_output(['xcrun', 'vtool', '-show-build', str(binary)], text=True)
assert re.search(r'platform\s+IOS\s', load_commands), load_commands
assert re.search(r'minos\s+16\.0(?:\.0)?\s', load_commands), load_commands
libraries = subprocess.check_output(['xcrun', 'otool', '-L', str(binary)], text=True)
for forbidden in ('AppKit.framework', '/opt/homebrew/', '/usr/local/', '.so'):
    assert forbidden not in libraries, libraries
print(load_commands)
print(libraries)
print('Bundle checks passed: arm64, iOS 16.0, no macOS-only dependency paths.')

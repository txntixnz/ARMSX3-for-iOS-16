#!/usr/bin/env python3
"""Reject non-arm64/non-iPhoneOS objects in the compile-only core archive."""
import pathlib
import struct
import sys


def verify(path):
    data = pathlib.Path(path).read_bytes()
    if not data.startswith(b'!<arch>\n'):
        raise ValueError('Not a static ar archive')
    offset = 8
    objects = 0
    while offset < len(data):
        header = data[offset:offset + 60]
        if len(header) != 60 or header[58:] != b'`\n':
            raise ValueError('Malformed archive member')
        size = int(header[48:58])
        body = data[offset + 60:offset + 60 + size]
        if len(body) != size:
            raise ValueError('Truncated member')
        name = header[:16].decode().strip()
        if name.startswith('#1/'):
            length = int(name[3:])
            name = body[:length].rstrip(b'\0').decode()
            body = body[length:]
        offset += 60 + size + (size & 1)
        if name.startswith('__.SYMDEF') or name in ('/', '//', '/SYM64/'):
            continue
        if len(body) < 32:
            raise ValueError(f'{name}: missing Mach-O header')
        magic, cpu, _, kind, ncmds, cmdsize, _, _ = struct.unpack_from('<8I', body)
        if magic != 0xfeedfacf or cpu != 0x100000c or kind != 1:
            raise ValueError(f'{name}: expected arm64 Mach-O object (no host objects or bitcode)')
        cursor = 32
        platform_seen = False
        for _ in range(ncmds):
            cmd, length = struct.unpack_from('<II', body, cursor)
            if length < 8 or cursor + length > 32 + cmdsize or cursor + length > len(body):
                raise ValueError(f'{name}: invalid load command')
            if cmd == 0x32:  # LC_BUILD_VERSION
                platform, minimum = struct.unpack_from('<II', body, cursor + 8)
                if platform != 2 or minimum > (16 << 16):
                    raise ValueError(f'{name}: not iPhoneOS with deployment target <= 16.0')
                platform_seen = True
            elif cmd == 0x25:  # LC_VERSION_MIN_IPHONEOS
                minimum, = struct.unpack_from('<I', body, cursor + 8)
                if minimum > (16 << 16):
                    raise ValueError(f'{name}: minimum iOS exceeds 16.0')
                platform_seen = True
            cursor += length
        if not platform_seen:
            raise ValueError(f'{name}: missing iPhoneOS platform metadata')
        objects += 1
    if not objects:
        raise ValueError('Archive has no verified objects')
    print(f'PASS: {objects} arm64 iPhoneOS objects; minimum OS <= 16.0')
    print('Compile-only archive: does not establish linkability or runtime correctness.')


if __name__ == '__main__':
    verify(sys.argv[1])

from pathlib import Path
import ast
import hashlib
import re
import struct

r = Path(__file__).resolve().parent


def dform(op, reg, base, imm):
    return (op << 26) | (reg << 21) | (base << 16) | (imm & 0xffff)


def encode(name, args):
    if name == 'mftb':
        reg,tbr=args
        return (31 << 26) | (reg << 21) | ((tbr & 31) << 16) | ((tbr >> 5) << 11) | (371 << 1)
    if name == 'dform':
        return dform(*args)
    if name == 'ADDI':
        return dform(14, *args)
    if name in ('LD', 'STD', 'STDU'):
        rt, ra, disp = args
        return dform(58 if name == 'LD' else 62, rt, ra, disp & ~3) | (name == 'STDU')
    if name in ('MFLR', 'MTLR', 'MTCTR'):
        return (31 << 26) | (args[0] << 21) | ((9 if name == 'MTCTR' else 8) << 16) | ((339 if name == 'MFLR' else 467) << 1)
    if name == 'BCTRL':
        return 0x4e800421
    if name == 'BLR':
        return 0x4e800020
    if name == 'SC':
        assert args == [0]
        return 0x44000002
    raise AssertionError(name)


def instructions(text):
    return [encode(name, [ast.literal_eval(x.strip()) for x in args.split(',') if x.strip()])
            for name, args in re.findall(r'\b(MFLR|STDU|STD|LD|ADDI|MTLR|MTCTR|BCTRL|BLR|SC|dform|mftb)\(([^()]*)\)', text)]


def fixture(stage):
    caller_start = stage.index('const std::array<u32, 24> caller{')
    caller_end = stage.index('};', caller_start)
    caller = instructions(stage[caller_start:caller_end])
    if re.search(r'const std::array<u32, \d+> callee\{',stage):
        start = re.search(r'const std::array<u32, \d+> callee\{',stage).start()
        end = stage.index('};', start)
        callee = instructions(stage[start:end])
    else:
        start = stage.index('opcodes[24] =')
        end = stage.index('ppu_exec_object::ehdr_t', start)
        callee = instructions(stage[start:end])
    code = b''.join(struct.pack('>I', x) for x in caller + callee)
    data = bytearray(352)

    def word(offset, value):
        struct.pack_into('>I', data, offset, value)

    for offset, value in [(0, 0x10060), (4, 0x20000), (8, 0x10000), (12, 0x20020),
                          (80, 0x20080), (84, 0x200a0), (88, 0x200b0),
                          (160, 0x49524e31), (164, 0x49524e32), (176, 0x10000), (180, 0x10000),
                          (208, 0x20080), (212, 0x200a0), (216, 0x200ec), (236, 0x20000)]:
        word(offset, value)
    data[64] = 44
    data[71] = 2
    data[128:137] = b'iOSProbe\0'
    data[192] = 44
    data[197] = 1
    data[199] = 1
    for i, value in enumerate([40, 0x1b434cec, 0, 0, 0x200c0, 0x200ec, 0x20040, 0x2006c, 0, 0]):
        word(256 + i * 4, value)
    for i, value in enumerate([32, 0x13bcc5f6, 0x00330000, 0x00360001, 1100, 0x8000, 0x10000, 0]):
        word(320 + i * 4, value)
    digest = hashlib.sha1()
    digest.update(struct.pack('>IIQQ', 1, 5, 0x10000, 0x10000))
    digest.update(code)
    digest.update(struct.pack('>IIQQ', 1, 6, 0x20000, 0x10000))
    digest.update(data)
    for ptype, flags in [(0x60000002, 0), (7, 4), (0x60000001, 0)]:
        digest.update(struct.pack('>II', ptype, flags))
    return caller + callee, data, digest.digest()


import sys
bridge = Path(sys.argv[1]) if len(sys.argv)>1 else (r/'CoreBridge.cpp' if (r/'CoreBridge.cpp').exists() else r.parent/'core/loadtest/CoreBridge.cpp')
source = bridge.read_text()
old = source.split('int armsx3_core_test_guest_time()',1)[1].split('int armsx3_core_test_guest_timebase()',1)[0]
stage = source.split('int armsx3_core_test_guest_timebase()',1)[1]
old_ops,old_data,old_hash = fixture(old)
ops,data,digest = fixture(stage)
assert old_hash.hex() == '35e335c137465f30906b2020757022063602cf7f'
assert len(ops)==49 and len(old_ops)==43 and old_data==data
assert ops[:38]==old_ops[:38] and ops[44:]==old_ops[38:]
assert ops[38]==ops[42]==0x7cac42e6 and ops[40]==0x7cad42e6
assert ops[39]==0xf8a10040 and ops[41]==0xf8a10048 and ops[43]==0xf8a10050
assert [i for i,x in enumerate(ops) if x==0x44000002]==[15,25,28,33,36,47]
expected_line=next(x for x in stage.splitlines() if 'const std::array<u8, 20> expectedHash' in x)
expected='        const std::array<u8, 20> expectedHash{'+', '.join(f'0x{x:02x}' for x in digest)+'};'
assert expected_line==expected, (digest.hex(),expected)
print('PASS: P41 golden SHA1 preserved, 49 P42 words/196 bytes, three split-TBR encodings, golden SHA1',digest.hex())

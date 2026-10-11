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
old = source.split('int armsx3_core_test_guest_timebase()',1)[1].split('int armsx3_core_test_memory_syscalls()',1)[0]
stage = source.split('int armsx3_core_test_memory_syscalls()',1)[1]
old_ops,old_data,old_hash = fixture(old)
ops,data,digest = fixture(stage)
assert old_hash.hex() == 'b792c49b4f4717bfbcae80c1e54acb1d1b92c56b'
assert len(ops)==63 and len(old_ops)==49 and old_data==data
assert ops[:44]==old_ops[:44] and ops[58:]==old_ops[44:]
assert len(ops)*4==252 and 0x200+len(ops)*4<=0x300
assert ops[44]==0x3c600001 and ops[45]==0x38800200 and ops[46]==0x38a10058
assert ops[47]==0x3960015c and ops[51]==ops[55]==0x3960015d
assert [i for i,x in enumerate(ops) if x==0x44000002]==[15,25,28,33,36,48,52,56,61]
expected_line=next(x for x in stage.splitlines() if 'const std::array<u8, 20> expectedHash' in x)
expected='        const std::array<u8, 20> expectedHash{'+', '.join(f'0x{x:02x}' for x in digest)+'};'
assert expected_line==expected, (digest.hex(),expected)
print('PASS: P42 digest/data preserved, 63 P43 words/252 bytes fit before ELF DATA, SC348/349 and stores, golden SHA1',digest.hex())

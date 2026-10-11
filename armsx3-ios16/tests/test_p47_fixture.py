"""Independent live/freed page-attribute fixture; also runs P43-P46 checks.

Usage: python test_p47_fixture.py [CoreBridge.cpp]
"""
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent
helpers = runpy.run_path(str(root / 'test_p46_fixture.py'))
fixture = helpers['fixture']
bridge = Path(sys.argv[1]) if len(sys.argv) > 1 else root.parent / 'core/loadtest/CoreBridge.cpp'
source = bridge.read_text()
old = source.split('int armsx3_core_test_memory_1m()', 1)[1].split('int armsx3_core_test_page_attributes()', 1)[0]
stage = source.split('int armsx3_core_test_page_attributes()', 1)[1]
old_ops, old_data, old_hash = fixture(old)
ops, data, digest = fixture(stage)
assert old_hash.hex() == 'c8da24be12d80e9c20442d28885eebed3d7c6288'
assert len(old_ops) == 93 and len(ops) == 103 and old_data == data
assert ops[:72] == old_ops[:72] and ops[77:89] == old_ops[72:84] and ops[94:] == old_ops[84:]
assert ops[72:77] == [0x80610058, 0x388201c0, 0x3960015f, 0x44000002, 0x906201d8]
assert ops[89:94] == [0x80610058, 0x388201e0, 0x3960015f, 0x44000002, 0x906201f8]
assert ops[55] == 0x40820044 and 55 * 4 + (ops[55] & 0xfffc) == 72 * 4
assert [i for i, x in enumerate(ops) if x == 0x44000002] == [15, 25, 28, 33, 36, 46, 52, 75, 79, 83, 87, 92, 96, 101]
assert digest.hex() == 'c8cfa90edc95d79ef5c28e293942c461ca6867a0'
expected = '        const std::array<u8, 20> expectedHash{' + ', '.join(f'0x{x:02x}' for x in digest) + '};'
assert next(x for x in stage.splitlines() if 'const std::array<u8, 20> expectedHash' in x) == expected
assert 'std::vector<u8> fixture(0x800, 0);' in stage
assert 'segments[0].p_offset = 0x600;' in stage and 'segments[1].p_offset = 0x300;' in stage
assert 0x300 + len(data) == 0x460 <= 0x600 and 0x600 + len(ops) * 4 == 0x79c <= 0x800
assert 'calleeFunction.size = 316' in stage and 'blocks.emplace(codeAddress + 96, 316)' in stage
assert 'program.returnAddress, 104)' in stage
assert 'ppu_get_syscall_name(351) != "sys_memory_get_page_attribute"' in stage
assert '{384, 408, 15, 184}, {392, 412, 18, 316}, {400, 416, 22, 384}' in stage
for offset, value in [(448, '0x40000ull'), (456, '0xfull')]:
    assert f'vm::read64(program.dataAddress + {offset}) == {value}' in stage
    assert f'expect64(expectedData, {offset}, {value});' in stage
for offset, value in [(464, '0x100000u'), (468, '0'), (472, '0'), (504, 'u32(CELL_EINVAL)')]:
    assert f'vm::read32(program.dataAddress + {offset}) == {value}' in stage
    assert f'expect32(expectedData, {offset}, {value});' in stage
for offset in [480, 488]:
    assert f'vm::read64(program.dataAddress + {offset}) == 0' in stage
for offset in [496, 500]:
    assert f'vm::read32(program.dataAddress + {offset}) == 0' in stage
assert 448 >= 352 and 504 + 4 <= 0x10000
print('PASS: P46 preserved; P47 SC351 live/freed structs, BSS bounds, unchanged failure guard, syscall PCs, 104-step budget and golden SHA1', digest.hex())

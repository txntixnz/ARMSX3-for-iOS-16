"""Independent P45 SC352 accounting fixture and previous-fixture regression.

Usage: python test_p45_fixture.py [CoreBridge.cpp]
"""
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent
helpers = runpy.run_path(str(root / 'test_p44_fixture.py'))
bridge = Path(sys.argv[1]) if len(sys.argv) > 1 else (root / 'CoreBridge.cpp' if (root / 'CoreBridge.cpp').exists() else root.parent / 'core/loadtest/CoreBridge.cpp')
source = bridge.read_text()
old = source.split('int armsx3_core_test_heap_access()', 1)[1].split('int armsx3_core_test_memory_stats()', 1)[0]
stage = source.split('int armsx3_core_test_memory_stats()', 1)[1]
old_ops, old_data, old_hash = helpers['fixture'](old)
ops, data, digest = helpers['fixture'](stage)
assert old_hash.hex() == 'a7481cbe5f25eae73bf267878f5f4d5a5f5d87de'
assert len(old_ops) == 81 and len(ops) == 93 and data == old_data
assert ops[:44] == old_ops[:44] and ops[48:72] == old_ops[44:68]
assert ops[76:84] == old_ops[68:76] and ops[88:] == old_ops[76:]
assert ops[44:48] == [0x38620180, 0x39600160, 0x44000002, 0x90620198]
assert ops[72:76] == [0x38620188, 0x39600160, 0x44000002, 0x9062019c]
assert ops[84:88] == [0x38620190, 0x39600160, 0x44000002, 0x906201a0]
assert ops[54:56] == [0x2c030000, 0x40820044]
assert 55 * 4 + (ops[55] & 0xfffc) == 72 * 4  # Failed allocation skips heap block.
assert [i for i, x in enumerate(ops) if x == 0x44000002] == [15, 25, 28, 33, 36, 46, 52, 74, 78, 82, 86, 91]
assert len(ops) * 4 == 372 and len(ops) + 1 == 94
assert digest.hex() == '399427cd45771d16d0e8c6a24e670900237e1c91'
expected = '        const std::array<u8, 20> expectedHash{' + ', '.join(f'0x{x:02x}' for x in digest) + '};'
assert next(x for x in stage.splitlines() if 'const std::array<u8, 20> expectedHash' in x) == expected
assert 'segments[0].p_offset = 0x600;' in stage and 'segments[1].p_offset = 0x300;' in stage
assert 'std::vector<u8> fixture(0x780, 0);' in stage
assert 'fileWord(0x600 + i * 4, opcodes[i])' in stage
assert 'fixture.data() + 0x600, sizeof(opcodes)' in stage
assert 0x600 + len(ops) * 4 == 0x774 <= 0x780
assert 'calleeFunction.size = 276' in stage and 'blocks.emplace(codeAddress + 96, 276)' in stage
assert 'program.returnAddress, 94)' in stage
assert '{384, 408, 15, 184}, {392, 412, 17, 296}, {400, 416, 20, 344}' in stage
for offset, value in [(384, '0x100000u'), (388, '0x100000u'), (392, '0x100000u'), (396, '0xf0000u'), (400, '0x100000u'), (404, '0x100000u'), (408, '0'), (412, '0'), (416, '0')]:
    assert f'expect32(expectedData, {offset}, {value});' in stage
assert 352 <= 384 and 416 + 4 <= 0x10000  # Reports occupy DATA BSS.
print('PASS: P44 fixture preserved; P45 three SC352 reports, allocation guard, SC PCs, 94-step budget, separate file regions and golden SHA1', digest.hex())

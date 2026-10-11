"""Independent P44 opcode, branch, ELF layout and digest checks.

Usage: python test_p44_fixture.py [CoreBridge.cpp]
Also runs the P43 fixture regression using its shared independent encoder.
"""
from pathlib import Path
import re
import runpy
import sys

root = Path(__file__).resolve().parent
helpers = runpy.run_path(str(root / 'test_p43_fixture.py'))
bridge = Path(sys.argv[1]) if len(sys.argv) > 1 else (root / 'CoreBridge.cpp' if (root / 'CoreBridge.cpp').exists() else root.parent / 'core/loadtest/CoreBridge.cpp')
source = bridge.read_text()
old = source.split('int armsx3_core_test_memory_syscalls()', 1)[1].split('int armsx3_core_test_heap_access()', 1)[0]
stage = source.split('int armsx3_core_test_heap_access()', 1)[1]
fixture = helpers['fixture']
old_ops, old_data, old_hash = fixture(old)
ops, data, digest = fixture(stage)
assert old_hash.hex() == 'b7696c23538699040aec282e8bc66686a87cf44c'
assert len(old_ops) == 63 and len(ops) == 81 and data == old_data
assert ops[:50] == old_ops[:50] and ops[68:] == old_ops[50:]
assert ops[50:68] == [
    0x2c030000, 0x40820044, 0x80c10058, 0x3ca01234, 0x60a55678,
    0x90a60000, 0x80660000, 0x90610060, 0x3d460001, 0x3ca089ab,
    0x60a5cdef, 0x90aafffc, 0x806afffc, 0x9061006c, 0x88660000,
    0x90610070, 0xa06afffc, 0x90610074]
assert 51 * 4 + (ops[51] & 0xfffc) == 68 * 4  # BNE lands at free setup.
assert [i for i, x in enumerate(ops) if x == 0x44000002] == [15, 25, 28, 33, 36, 48, 70, 74, 79]
assert len(ops) * 4 == 324 and len(ops) + 1 == 82
assert digest.hex() == 'a7481cbe5f25eae73bf267878f5f4d5a5f5d87de'
expected = '        const std::array<u8, 20> expectedHash{' + ', '.join(f'0x{x:02x}' for x in digest) + '};'
assert next(x for x in stage.splitlines() if 'const std::array<u8, 20> expectedHash' in x) == expected
assert re.search(r'segments\[0\].p_offset = 0x600;', stage)
assert re.search(r'segments\[1\].p_offset = 0x300;', stage)
assert 'std::vector<u8> fixture(0x760, 0);' in stage
assert 'fileWord(0x600 + i * 4, opcodes[i])' in stage
assert 'fixture.data() + 0x600, sizeof(opcodes)' in stage
assert 0x300 + len(data) == 0x460 <= 0x600
assert 0x600 + len(ops) * 4 == 0x744 <= 0x760
assert 'calleeFunction.size = 228' in stage
assert 'blocks.emplace(codeAddress + 96, 228)' in stage
assert 'program.returnAddress, 82)' in stage
for offset, value in [(96, '0x12345678u'), (108, '0x89abcdefu'), (112, '0x12u'), (116, '0x89abu')]:
    assert f'vm::read32(frame + {offset}) == {value}' in stage
    assert f'expect32(expectedStack, frameAddress - stackAddress + {offset}, {value});' in stage
print('PASS: P43 fixture preserved; P44 heap opcodes, allocation guard, SC PCs, 82-step budget, separate ELF CODE/DATA and golden SHA1', digest.hex())

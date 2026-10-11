"""Independent P46 1 MiB page fixture, plus P43-P45 regressions.

Usage: python test_p46_fixture.py [CoreBridge.cpp]
"""
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent
helpers = runpy.run_path(str(root / 'test_p45_fixture.py'))
fixture = helpers['helpers']['fixture']
bridge = Path(sys.argv[1]) if len(sys.argv) > 1 else root.parent / 'core/loadtest/CoreBridge.cpp'
source = bridge.read_text()
old = source.split('int armsx3_core_test_memory_stats()', 1)[1].split('int armsx3_core_test_memory_1m()', 1)[0]
stage = source.split('int armsx3_core_test_memory_1m()', 1)[1]
old_ops, old_data, old_hash = fixture(old)
ops, data, digest = fixture(stage)
assert old_hash.hex() == '399427cd45771d16d0e8c6a24e670900237e1c91'
assert len(ops) == len(old_ops) == 93 and data == old_data
assert [i for i, (a, b) in enumerate(zip(old_ops, ops)) if a != b] == [48, 49, 62]
assert ops[48] == 0x3c600010  # ADDIS r3,0,16 => allocation size 1 MiB.
assert ops[49] == 0x38800400  # SYS_MEMORY_PAGE_SIZE_1M.
assert ops[62] == 0x3d460010  # ADDIS r10,r6,16 => one past the heap end.
assert ops[65] == 0x90aafffc and ops[66] == 0x806afffc  # Last-word store/load.
assert ops[70] == 0xa06afffc  # Last halfword load.
assert ops[55] == 0x40820044 and 55 * 4 + (ops[55] & 0xfffc) == 72 * 4
assert [i for i, x in enumerate(ops) if x == 0x44000002] == [15, 25, 28, 33, 36, 46, 52, 74, 78, 82, 86, 91]
assert digest.hex() == 'c8da24be12d80e9c20442d28885eebed3d7c6288'
expected = '        const std::array<u8, 20> expectedHash{' + ', '.join(f'0x{x:02x}' for x in digest) + '};'
assert next(x for x in stage.splitlines() if 'const std::array<u8, 20> expectedHash' in x) == expected
assert 'std::vector<u8> fixture(0x780, 0);' in stage
assert 'segments[0].p_offset = 0x600;' in stage and 'segments[1].p_offset = 0x300;' in stage
assert 0x300 + len(data) == 0x460 <= 0x600 and 0x600 + len(ops) * 4 == 0x774 <= 0x780
assert 'calleeFunction.size = 276' in stage and 'blocks.emplace(codeAddress + 96, 276)' in stage
assert 'program.returnAddress, 94)' in stage
assert 'program.allocatedAddress & 0xfffffu' in stage
assert '!vm::check_addr(program.allocatedAddress + 0xffffcu)' in stage
assert 'snapshot[0] == 392 ? 0u : 0x100000u' in stage
assert '{0xfffff, 0x400, program.dataAddress + 16, u32(CELL_EALIGN)}' in stage
assert '{0x200000, 0x400, program.dataAddress + 16, u32(CELL_ENOMEM)}' in stage
assert '{0x100000, 0x400, 0, u32(CELL_EFAULT)}' in stage
for offset, value in [(384, '0x100000u'), (388, '0x100000u'), (392, '0x100000u'), (396, '0u'), (400, '0x100000u'), (404, '0x100000u'), (408, '0'), (412, '0'), (416, '0')]:
    assert f'expect32(expectedData, {offset}, {value});' in stage
print('PASS: P45 preserved; P46 1 MiB size/flag/end address, guard, unchanged syscall PCs/94 steps, availability 1 MiB/0/1 MiB and golden SHA1', digest.hex())

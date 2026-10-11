"""Independent P48 guest null/partial-output fixture; runs P43-P47 regressions."""
from pathlib import Path
import runpy, sys
root=Path(__file__).resolve().parent
helpers=runpy.run_path(str(root/'test_p47_fixture.py'))
fixture=helpers['fixture']
bridge=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent/'core/loadtest/CoreBridge.cpp'
source=bridge.read_text()
old=source.split('int armsx3_core_test_page_attributes()',1)[1].split('int armsx3_core_test_page_attribute_errors()',1)[0]
stage=source.split('int armsx3_core_test_page_attribute_errors()',1)[1]
old_ops,old_data,old_hash=fixture(old)
ops,data,digest=fixture(stage)
assert old_hash.hex()=='c8cfa90edc95d79ef5c28e293942c461ca6867a0'
assert len(old_ops)==103 and len(ops)==114 and old_data==data
assert ops[:77]==old_ops[:77] and ops[88:]==old_ops[77:]
assert ops[77:82]==[0x80610058,0x38800000,0x3960015f,0x44000002,0x906201fc]
assert ops[82:88]==[0x80610058,0x3c80000a,0x3884fff8,0x3960015f,0x44000002,0x90620200]
assert ops[55]==0x40820044 and 55*4+(ops[55]&0xfffc)==72*4
assert [i*4 for i,x in enumerate(ops) if x==0x44000002]==[60,100,112,132,144,184,208,300,320,344,360,376,392,412,428,448]
assert digest.hex()=='acdc835b5c0163e1bd8f534e74aca9117e9d2184'
expected='        const std::array<u8, 20> expectedHash{'+', '.join(f'0x{x:02x}' for x in digest)+'};'
assert next(x for x in stage.splitlines() if 'const std::array<u8, 20> expectedHash' in x)==expected
assert 'std::vector<u8> fixture(0x800, 0);' in stage
assert 0x300+len(data)==0x460<=0x600 and 0x600+len(ops)*4==0x7c8<=0x800
assert 'calleeFunction.size = 360' in stage and 'blocks.emplace(codeAddress + 96, 360)' in stage
assert 'program.returnAddress, 115)' in stage and 'program.result != 115' in stage
assert '{384, 408, 15, 184}, {392, 412, 20, 360}, {400, 416, 24, 428}' in stage
assert '{{{508, 18, 320}, {512, 19, 344}}}' in stage
for offset in [508,512]:
    assert f'expect32(expectedData, {offset}, u32(CELL_EFAULT));' in stage
assert 'vm::check_addr(peerStackAddress + 0xfff8, vm::page_readable, 24)' in stage
assert 'vm::read64(program.peerStackAddress + 0xfff8) == 0x5aa55aa5deadbeefull' in stage
assert 'historyStart + 27 &&' in stage and 'historyStart + 29 &&' in stage
assert 'data.size() < 29' in stage
assert 512+4<=0x10000
print('PASS: P47 preserved; P48 null/partial guest outputs, SC PCs/errors/history, sentinel/guard, 115 steps, ELF bounds and golden SHA1',digest.hex())

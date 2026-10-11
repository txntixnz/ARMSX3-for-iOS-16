"""Independent P49 process PID/SDK fixture; runs P43-P48 regressions."""
from pathlib import Path
import runpy,sys
root=Path(__file__).resolve().parent
helpers=runpy.run_path(str(root/'test_p48_fixture.py'))
fixture=helpers['fixture']
bridge=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent/'core/loadtest/CoreBridge.cpp'
source=bridge.read_text()
old=source.split('int armsx3_core_test_page_attribute_errors()',1)[1].split('int armsx3_core_test_process_sdk()',1)[0]
stage=source.split('int armsx3_core_test_process_sdk()',1)[1]
old_ops,old_data,old_hash=fixture(old)
ops,data,digest=fixture(stage)
assert old_hash.hex()=='acdc835b5c0163e1bd8f534e74aca9117e9d2184'
assert len(old_ops)==114 and len(ops)==121 and old_data==data
assert ops[:109]==old_ops[:109] and ops[116:]==old_ops[109:]
assert ops[109:116]==[0x39600001,0x44000002,0x90620220,0x38820224,0x39600019,0x44000002,0x90620228]
assert ops[55]==0x40820044 and 55*4+(ops[55]&0xfffc)==72*4
assert [i*4 for i,x in enumerate(ops) if x==0x44000002]==[60,100,112,132,144,184,208,300,320,344,360,376,392,412,428,440,456,476]
assert digest.hex()=='4c9d73c848817ee4a40eb2aafdd50d4686e23a70'
expected='        const std::array<u8, 20> expectedHash{'+', '.join(f'0x{x:02x}' for x in digest)+'};'
assert next(x for x in stage.splitlines() if 'const std::array<u8, 20> expectedHash' in x)==expected
assert 'std::vector<u8> fixture(0x800, 0);' in stage
assert 0x300+len(data)==0x460<=0x600 and 0x600+len(ops)*4==0x7e4<=0x800
assert 'calleeFunction.size = 388' in stage and 'blocks.emplace(codeAddress + 96, 388)' in stage
assert 'program.returnAddress, 122)' in stage and 'program.result != 122' in stage
assert 'processParameters[3], processParameters[0]};' in stage
assert 'program.sdkVersion}' in stage
assert 'armsx3_ios_process_sdk_probe_and_call(context, call.sdk, underSDK, user)' in stage
assert 'g_ps3_process_info.sdk_ver != previousSDK' in stage
assert 'vm::read32(program.dataAddress + 544) == 1' in stage
assert 'vm::read32(program.dataAddress + 548) == program.sdkVersion' in stage
assert 'vm::read32(program.dataAddress + 552) == 0' in stage
assert 'pidEvent.cia == program.begin + 440' in stage and 'sdkEvent.cia == program.begin + 456' in stage
assert 'expect32(expectedData, 544, 1); expect32(expectedData, 548, processParameters[0]); expect32(expectedData, 552, 0);' in stage
assert 'historyStart + 29 &&' in stage and 'historyStart + 31 &&' in stage and 'data.size() < 31' in stage
assert 552+4<=0x10000 and 544>=512+4
print('PASS: P48 preserved; P49 SC1 PID retained in r3 for SC25, metadata publication/restoration, exact outputs/SC PCs/history, 122steps/ELF bounds and SHA1',digest.hex())

"""Build109 intake, native header contracts, UI gating and prior-core freeze."""
from pathlib import Path
import hashlib,plistlib,re
here=Path(__file__).resolve().parent
parent=(here/'test_p106_fixture.py').read_text()
exec(compile(parent[:parent.rindex('\napp=')],str(here/'test_p106_fixture.py'),'exec'))
marker=b'// Build109 advances firmware import and actual executable intake.'
assert bridge.count(marker)==1
old,new=bridge.split(b'\n'+marker,1)
assert hashlib.sha1(b'blob '+str(len(old)).encode()+b'\0'+old).hexdigest()=='ec4bb6ac7c2d47c52dc55256a08a87e7fb4b03bc'
profiles=['storage','pup_headers','pup_bounds','pup_authenticated','pup_tamper','tar_staging','executable_intake','firmware_publication']
assert re.findall(r'ios_intake::probe\((\d+)\)',new.decode())==list(map(str,range(8)))
app=(here.parent/'core/loadtest/App.mm').read_text();stages=re.findall(r'\{(\d+), "[^"]+", "(armsx3_core_[^"]+)"\}',app)
assert [int(n) for n,_ in stages]==list(range(2,122)) and len({f for _,f in stages})==120
assert [f for _,f in stages[-8:]]==['armsx3_core_test_intake_'+x for x in profiles]
intake=(here.parent/'core/loadtest/Intake.cpp').read_text()
for token in ['preflight_pup(file)', 'pup_object pup(std::move(file))', 'decoder.LoadHeaders() && decoder.LoadMetadata(SCEPKG_ERK, SCEPKG_RIV) && decoder.DecryptData()',
 'validate_tar(parts[2], true)', 'contents.extract(stage.string(), false)', 'publish(staged_flash, destination, backup)',
 'sys/external/liblv2.sprx', 'vsh/etc/version.txt', 'decrypt_self(input)', 'ppu_exec_object elf(executable)',
 'ARMSX3-prepared-executable.elf', 'Game execution is the next milestone.']:
 assert token in intake,token
for token in ['UIDocumentPickerDelegate', 'initForOpeningContentTypes:@[UTTypeData] asCopy:YES', 'startAccessingSecurityScopedResource',
 'stopAccessingSecurityScopedResource', 'self.nextStage == stageCount', '!self.intakeBusy', 'copyItemAtURL:source',
 'armsx3_core_import_firmware', 'armsx3_core_inspect_executable', 'char buffer[4096]']:
 assert token in app,token
cmake=(here.parent/'core/loadtest/CMakeLists.txt').read_text()
assert 'FrontendHooks.cpp Intake.cpp' in cmake and '-framework UniformTypeIdentifiers' in cmake
assert 'Emu.BootGame(' not in intake and 'Emu.Run(' not in intake # inspection does not launch uncontrolled guest workers
info=plistlib.loads((here.parent/'core/loadtest/Info.plist.in').read_bytes())
assert info['CFBundleVersion']=='109' and info['MinimumOSVersion']=='16.0'
workflow=(here.parent.parent/'.github/workflows/build-armsx3-ios16-core.yml').read_text()
assert 'needs: [synchronization-host, intake-host]' in workflow
assert len(re.findall(r'^\s+- script: test_p\d+_pair.py$',workflow,re.M))==34
assert re.search(r'^  intake-host:$',workflow,re.M) and 'python3 armsx3-ios16/tests/test_p114_intake.py upstream-armsx3' in workflow
print('PASS: full Build108 bridge freeze;120 ordered device stages/8 intake probes; native firmware/SELF/ELF paths, UIKit scoped file intake/gating, staged publication, Build109/iOS16/host dependencies; real PUP/iOS install pending')

"""Build125 intake/runtime contracts, UI gating and prior-core freeze."""
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
 'sys/external/liblv2.sprx', 'vsh/etc/version.txt', 'if (magic == "SCE\\0"_u32)', 'executable = decrypt_self(input)',
 'executable = std::move(input)', 'executable.seek(0)', 'ppu_exec_object elf(executable)',
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
assert info['CFBundleVersion']=='125' and info['MinimumOSVersion']=='16.0'
workflow=(here.parent.parent/'.github/workflows/build-armsx3-ios16-core.yml').read_text()
assert 'needs: [synchronization-host, intake-host, graphics-host]' in workflow
assert len(re.findall(r'^\s+- script: test_p\d+_pair.py$',workflow,re.M))==34
assert re.search(r'^  intake-host:$',workflow,re.M) and 'python3 armsx3-ios16/tests/test_p114_intake.py upstream-armsx3' in workflow
runtime=(here.parent/'core/loadtest/Runtime.cpp').read_text()
assert 'Emu.BootGame(prepared.string(), "", true, cfg_mode::config_override, temporary.path.string())' in runtime
assert 'configuration.misc.autostart.set(false)' in runtime and 'Emu.SetForceBoot(false)' in runtime
assert runtime.count('Emu.Run(false)')==1 and 'Emu.Resume(' not in runtime
assert 'if (execute) executed = run_window(render, should_stop)' in runtime and 'permit_guest_start(true)' in runtime
assert 'armsx3_core_run_game' in app and 'Run game (3 seconds)' in app
assert 'RuntimeCapture.cpp' in cmake and 'begin_execution_observation()' in runtime
assert 'Emu.IsStopped(true)' in runtime and 'drain_main_queue()' in runtime
assert 'liblv2 firmware loading failed' in runtime and 'g_cfg.from_string(previous)' in runtime
assert 'Runtime.cpp RuntimeFrontend.cpp RuntimeDispatch.mm' in cmake
assert 'armsx3_core_check_runtime' in app and 'self.runtimeButton.enabled = intakeReady' in app
assert 'self.failed = result == -2' in app and 'Runtime load check' in app
assert 'python3 armsx3-ios16/tests/test_runtime.py upstream-armsx3' in workflow
assert 'python3 armsx3-ios16/tests/test_jit_lifecycle.py upstream-armsx3' in workflow
assert 'python3 armsx3-ios16/tests/test_spu_cache_startup.py upstream-armsx3' in workflow
assert 'python3 armsx3-ios16/tests/test_spu_thread_entry.py upstream-armsx3' in workflow
assert 'python3 armsx3-ios16/tests/test_game_import.py upstream-armsx3' in workflow
for token in ['UTTypeFolder] asCopy:NO', 'NSFileCoordinator', 'armsx3_core_import_game', 'armsx3_core_check_game']:
 assert token in app,token
assert 'GameImport.cpp' in cmake

assert 'graphics-host:' in workflow and 'test_graphics_device.py' in workflow
assert 'GraphicsDevice.cpp GraphicsCheck.cpp' in cmake and 'armsx3_ios_moltenvk' in cmake
assert 'self.graphicsButton.enabled = intakeReady' in app and 'armsx3_core_check_graphics' in app
print('PASS: prior bridge freeze;120 ordered stages; native intake, load-only BootGame gates and explicit bounded guest start; scoped UIKit actions; Build125/iOS16;34+2 host dependencies')

# Quick start retains the real stage cursor and unlocks intake only after all
# four foundation stages pass. Full diagnostics still resume at that cursor.
assert [f for _,f in stages[:4]]==['armsx3_core_state','armsx3_core_test_immutable_jit','armsx3_core_initialize','armsx3_core_test_guest_memory']
assert 'if (self.quickMode && self.nextStage == 4)' in app
assert 'self.foundationReady = YES;' in app and 'remaining diagnostics were not run' in app
assert '(self.foundationReady || self.nextStage == stageCount)' in app
assert app.count('(!self.foundationReady && self.nextStage != stageCount)')==4
assert 'self.nextStage = stageCount' not in app
print('PASS: Quick start uses four real foundation stages; separate readiness; full120 diagnostic cursor retained')

for token in ['armsx3_core_render_session','renderShouldStop,&renderStopRequested','UIApplicationWillResignActiveNotification','Stop game']:
 assert token in app,token
assert 'if (self.stopAction) self.stopAction();' in app
assert 'self.stopGameButton.enabled = NO' in app
assert 'while (should_stop || std::chrono::steady_clock::now() < deadline)' in runtime
assert 'executed && error.empty()' in runtime
print('PASS: cancellable session frontend/C ABI and continued cleanup ownership contracts')

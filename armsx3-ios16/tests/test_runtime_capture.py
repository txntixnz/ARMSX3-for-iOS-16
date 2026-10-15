"""Materialize and check the joined-thread-only iOS execution observer patch."""
from pathlib import Path
import re,subprocess,tempfile
PIN='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
DECL='''#if defined(__APPLE__) && TARGET_OS_IOS
// Snapshot execution diagnostics only after native emulation threads join.
extern "C" void armsx3_ios_runtime_capture_stopped() noexcept;
#endif
'''
HOOK='''
#if defined(__APPLE__) && TARGET_OS_IOS
		armsx3_ios_runtime_capture_stopped();
#endif
'''
RSX_INCLUDE='#ifdef __APPLE__\n#include <TargetConditionals.h>\n#endif\n'
RSX_GUARD="#if defined(__APPLE__) && TARGET_OS_IOS\n\t\t\t\t// Stop and startup callbacks share UIKit's main queue. Ignore a\n\t\t\t\t// start posted before an already completed stop request.\n\t\t\t\tif (!Emu.IsStarting()) return;\n#endif\n"
def patched_system(native):
 root=Path(__file__).resolve().parent.parent
 patches=sorted(p for p in (root/'patches').glob('*.patch') if int(p.name[:4])<=51)
 assert [p.name[:4] for p in patches]==[f'{n:04d}' for n in range(1,52)]
 source=subprocess.check_output(['git','-C',str(native),'show',PIN+':rpcs3/Emu/System.cpp'],text=True)
 with tempfile.TemporaryDirectory(prefix='armsx3-joined-hook-') as temp:
  temp=Path(temp);target=temp/'rpcs3/Emu/System.cpp';target.parent.mkdir(parents=True);target.write_text(source)
  for patch in patches[:-1]:subprocess.run(['git','apply','--include=rpcs3/Emu/System.cpp',str(patch)],cwd=temp,check=True)
  before=target.read_text()
  rsx=temp/'rpcs3/Emu/RSX/RSXThread.cpp';rsx.parent.mkdir(parents=True,exist_ok=True)
  rsx.write_text(subprocess.check_output(['git','-C',str(native),'show',PIN+':rpcs3/Emu/RSX/RSXThread.cpp'],text=True))
  for patch in patches[:-1]:subprocess.run(['git','apply','--include=rpcs3/Emu/RSX/RSXThread.cpp',str(patch)],cwd=temp,check=True)
  rsx_before=rsx.read_text()
  subprocess.run(['git','apply','--check',str(patches[-1])],cwd=temp,check=True)
  subprocess.run(['git','apply',str(patches[-1])],cwd=temp,check=True)
  after=target.read_text();rsx_after=rsx.read_text()
 assert rsx_after.replace(RSX_INCLUDE,'').replace(RSX_GUARD,'')==rsx_before
 callback=re.search(r'Emu.CallFromMainThread\(\[\]\n\t\t\t\{\n('+re.escape(RSX_GUARD)+r'.*?)\n\t\t\t\}\);',rsx_after,re.S).group(1)
 assert after.count(DECL)==1 and after.count(HOOK)==1
 assert after.replace(DECL,'').replace(HOOK,'')==before,'native join/cleanup behavior changed'
 hook=after.index(HOOK);kill=after.rindex('void Emulator::Kill(',0,hook)
 join=after.index('type.thread_op(data, thread_state::finished);',kill)
 destroy=after.index('type.thread_op(data, thread_state::destroying_context);',join)
 assert join<hook<destroy
 assert 'All threads have been stopped.' in after[join:hook]
 print('PASS: patch0051 applies after exact first50; iOS-only read observer follows native thread joins and precedes context destruction; original System.cpp behavior retained')
 return after,callback
if __name__=='__main__':
 import sys
 patched_system(Path(sys.argv[1]).resolve())

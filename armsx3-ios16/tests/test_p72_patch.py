"""Validate isolated scheduler patch after the frozen47 patches on pinned LV2.
Usage: python test_p72_patch.py upstream-armsx3
"""
from pathlib import Path
import subprocess,sys,tempfile
if len(sys.argv)!=2:raise SystemExit(__doc__)
root=Path(sys.argv[1]);patches=Path(__file__).resolve().parent.parent/'patches'
paths=['rpcs3/Emu/Cell/lv2/lv2.cpp','rpcs3/Emu/Cell/lv2/sys_sync.h']
all_patches=sorted(patches.glob('*.patch'));assert len(all_patches)==48
last=all_patches[-1];assert last.name=='0048-ios-lv2-mutex-sleep-wake-probe.patch'
with tempfile.TemporaryDirectory(prefix='p72-patch-') as tmp:
 stage=Path(tmp)
 for rel in paths:
  target=stage/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((root/rel).read_bytes())
 args=['git','apply',*[f'--include={p}' for p in paths]]
 for patch in all_patches[:-1]:subprocess.run(args+[str(patch)],cwd=stage,check=True)
 before=(stage/paths[0]).read_text();header_before=(stage/paths[1]).read_text()
 subprocess.run(args+['--check',str(last)],cwd=stage,check=True)
 subprocess.run(args+[str(last)],cwd=stage,check=True)
 after=(stage/paths[0]).read_text();header=(stage/paths[1]).read_text()
 assert after.startswith(before),'prior native service/scheduler implementations changed'
 added=after[len(before):]
 for text in ['!Emu.IsStopped()', 'cpu_thread::get_current() != context',
  'g_ppu || g_scheduler_ready || !quiet()', 'if (!awake(context) || !awake(peer))',
  'make_scheduler_ready();', 'const int result = execute(user);', 'restore.finish();',
  'lv2_obj::unqueue(g_ppu, context', 'lv2_obj::unqueue(g_ppu, peer',
  'g_scheduler_ready.release(false)', 'context->prio.load().all != prior.all',
  'g_priority_order_tag.load() != tag', 'context->start_time != restore.start',
  'context->end_time != restore.end', 'g_ppu == holder && !holder->next_ppu',
  'waiter->state.all_of(cpu_flag::wait + cpu_flag::suspend)',
  'armsx3_ios_ppu_probe_mutex_scheduler_and_call', 'armsx3_ios_ppu_probe_mutex_sleep_state']:
  assert text in added,text
 assert 'sys_mutex_lock(' not in added and 'g_ppu_syscall_table' not in added
 declarations='\n#if defined(__APPLE__) && TARGET_OS_IPHONE\n    static int ios_probe_mutex_scheduler_and_call(ppu_thread*, ppu_thread*, int (*)(void*), void*);\n    static int ios_probe_mutex_sleep_state(ppu_thread*, ppu_thread*);\n#endif'
 assert header.replace(declarations,'')==header_before
print('PASS: patch48 applies after frozen47 on pinned LV2; prior native services/scheduler unchanged; narrow iOS scope guards/actual awake-ready calls/restore and atomic queue observation declarations verified')

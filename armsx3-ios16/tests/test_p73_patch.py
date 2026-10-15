"""Validate read-only timeout observers after frozen48 patches on pinned LV2.
Usage: python test_p73_patch.py upstream-armsx3
"""
from pathlib import Path
import subprocess,sys,tempfile
if len(sys.argv)!=2:raise SystemExit(__doc__)
root=Path(sys.argv[1]);patches=Path(__file__).resolve().parent.parent/'patches'
paths=['rpcs3/Emu/Cell/lv2/lv2.cpp','rpcs3/Emu/Cell/lv2/sys_sync.h']
# This test validates the historical patch49 observer against its first48
# predecessors. Later port patches have their own checks and must not move it.
observer_series=[p for p in sorted(patches.glob('*.patch')) if p.name[:4].isdigit() and int(p.name[:4])<=49]
assert [p.name[:4] for p in observer_series]==[f'{n:04d}' for n in range(1,50)]
last=observer_series[-1];assert last.name=='0049-ios-lv2-mutex-timeout-observation.patch'
with tempfile.TemporaryDirectory(prefix='p73-patch-') as tmp:
 stage=Path(tmp)
 for rel in paths:
  target=stage/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((root/rel).read_bytes())
 args=['git','apply',*[f'--include={p}' for p in paths]]
 for patch in observer_series[:-1]:subprocess.run(args+[str(patch)],cwd=stage,check=True)
 before=(stage/paths[0]).read_text();header_before=(stage/paths[1]).read_text()
 subprocess.run(args+['--check',str(last)],cwd=stage,check=True)
 subprocess.run(args+[str(last)],cwd=stage,check=True)
 after=(stage/paths[0]).read_text();header=(stage/paths[1]).read_text()
 assert after.startswith(before),'prior native services/scheduler/probes changed'
 added=after[len(before):]
 for text in ['!Emu.IsStopped()', 'std::lock_guard lock(g_mutex);',
  'g_waiting.size() == 1', 'g_waiting.front().second == waiter',
  'g_waiting.front().first == waiter->end_time', 'waiter->end_time != umax',
  'waiter->end_time - waiter->start_time == timeout',
  'g_ppu == holder && !holder->next_ppu',
  'waiter->state.all_of(cpu_flag::wait + cpu_flag::suspend)',
  'g_waiting.empty() && g_to_sleep.empty() && pair',
  'cpu_flag::exit + cpu_flag::notify',
  'armsx3_ios_ppu_probe_mutex_timeout_state', 'armsx3_ios_ppu_probe_mutex_timeout_finished']:
  assert text in added,text
 assert 'sys_mutex_lock(' not in added and 'g_ppu_syscall_table' not in added
 assert '->gpr' not in added and '.release(' not in added and '->state +=' not in added
 declarations='\n    static int ios_probe_mutex_timeout_state(ppu_thread*, ppu_thread*, u64);\n    static int ios_probe_mutex_timeout_finished(ppu_thread*, ppu_thread*);'
 assert header.replace(declarations,'')==header_before
print('PASS: patch49 applies after frozen48 on pinned LV2; prior services/scheduler/probes unchanged; read-only deadline/queue/finished-state observers and declarations verified')

"""Build102 batched FIFO/priority surplus semaphore guest workloads.
Usage: test_p80_pair.py PPUThread.cpp CoreBridge.cpp sys_ppu_thread_.cpp [fifo|priority]
Native services/queue/probes/binder run on explicit CPU/VM/scheduler host models.
"""
from pathlib import Path
import sys
profile=sys.argv.pop() if len(sys.argv)==5 else 'fifo'
assert profile in ('fifo','priority'),profile
symbol='armsx3_core_test_semaphore_'+profile+'_surplus'
parent=Path(__file__).with_name('test_p79_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
def replace(a,b):
 global source
 assert a in source,a
 source=source.replace(a,b)
replace('P79','P80/P81')
replace('armsx3_core_test_semaphore_timeout_then_wake',symbol)
needle='phase=function(bridge,\'extern "C" __attribute__((visibility("default"))) int '+symbol+'(\')'
replace(needle, 'phase=function(bridge,\'static int armsx3_core_test_semaphore_surplus_batch(\')+"\\n"+function(bridge,\'extern "C" __attribute__((visibility("default"))) int armsx3_core_test_semaphore_fifo_surplus(\')+"\\n"+function(bridge,\'extern "C" __attribute__((visibility("default"))) int armsx3_core_test_semaphore_priority_surplus(\')')
replace('==119','==128')
replace('executed==936 && tls_stores==78 && output_stores==156','executed==1008 && tls_stores==84 && output_stores==168')
replace('stat[94]==21 && syscall_usage.stat[114]==18','stat[94]==24 && syscall_usage.stat[114]==21')
for old,new in [(13,14),(26,28),(39,42)]:replace(f'TLS={old}/{old}',f'TLS={new}/{new}')
replace('260,261,262,263,264,265,266};','260,261,262,263,264,265,266,267,268,269'+(',270' if profile=='priority' else '')+'};')
# Fault267 loses the surplus permit while still waking the queued worker.
# Fault268/269 falsely succeed on positive/negative signed count extremes.
replace("services=services.replace('return sema.val.try_dec(0);'", """services=services.replace('val += count;', 'val += fault==267 && val<0 ? count-1 : count;')
services=services.replace('if (count <= 0)', 'if(fault==268 && count==0x7fffffff){return CELL_OK;}if(fault==269 && count==s32(0x80000000u)){return CELL_OK;}\\n\\tif (count <= 0)')
services=services.replace('const u32 protocol = _attr.protocol;', 'const u32 protocol = fault==270?SYS_SYNC_FIFO:u32(_attr.protocol);')
services=services.replace('return sema.val.try_dec(0);'""")
replace('all78SC','all84SC')
replace('queued waits and posted wakes each','queued waits and post2 wakes retaining one spare permit each')
replace('stale timer266 detected','stale timer266/lost surplus267/false INT_MAX success268/false INT_MIN success269'+('/wrong priority protocol270' if profile=='priority' else '')+' detected')
source=source.replace('PASS: P80/P81 extracted','PASS: '+profile+' P80/P81 extracted')
source=source.replace("str(binary)],check=True)", "str(binary)],check=True,timeout=180)")
source=source.replace("[str(binary)],check=True)", "[str(binary)],check=True,timeout=180)")
exec(compile(source,str(Path(__file__).resolve()),'exec'))

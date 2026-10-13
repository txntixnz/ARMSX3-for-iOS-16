"""P79 extracted semaphore timeout -> requeue -> posted wake workload.
Run with pinned patched PPUThread.cpp, CoreBridge.cpp and sys_ppu_thread_.cpp.
Native semaphore/queue/probe/binder code runs on explicit host scheduler models.
"""
from pathlib import Path
parent=Path(__file__).with_name('test_p78_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
def replace(a,b):
 global source
 assert a in source,a
 source=source.replace(a,b)
replace('P78','P79')
replace('armsx3_core_test_semaphore_timeout_recovery','armsx3_core_test_semaphore_timeout_then_wake')
replace('timeout!=100000)', 'timeout!=100000 && timeout!=1000000)')
# A canceled timer must never manufacture a later successful reschedule.
# This is a host-model consistency guard, not a native latency assertion.
replace(' awake(cpu);return true;', ' {std::lock_guard lock(g_mutex);if(std::none_of(g_waiting.begin(),g_waiting.end(),[&](const auto&p){return p.second==cpu;}))throw std::runtime_error("host timer expired after cancellation without wake signal");}awake(cpu);return true;')
replace('==110','==119')
replace('executed==864 && tls_stores==72 && output_stores==144','executed==936 && tls_stores==78 && output_stores==156')
replace('sleep_count==3 && wake_count==3','sleep_count==6 && wake_count==6')
replace('semaphore_timeout_observations==12','semaphore_timeout_observations==15')
replace('stat[92]==12','stat[92]==15');replace('stat[94]==18','stat[94]==21')
for old,new in [(12,13),(24,26),(36,39)]:replace(f'TLS={old}/{old}',f'TLS={new}/{new}')
replace('260,261,263,264,265,266};','260,261,262,263,264,265,266};')
replace('8runs with three100000us timed FIFO expiries and same-object permit reuse each','8runs with three100000us expiries followed by same-worker/object1000000us queued waits and posted wakes each')
replace('all72SC','all78SC')
replace('queue observation261/false timeout', 'queue observation261/canceled-timer model guard262/false timeout')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

"""P75 real timed mutex API bodies on modeled timeout-to-wake reuse.
Usage: python test_p75_pair.py PPUThread.cpp CoreBridge.cpp Modules/sys_ppu_thread_.cpp
Native API/method/binder/SC/TLS/scope/observer bodies are extracted. Real guest
clock/wait_timeout/CPU check_state/CPU sleep/awake/atomic control remain models.
"""
from pathlib import Path
parent=Path(__file__).with_name('test_p74_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
def replace(before,after):
 global source
 assert before in source,before
 source=source.replace(before,after)
replace('P74','P75');replace('armsx3_core_test_mutex_timed_wake','armsx3_core_test_mutex_timeout_then_wake')
replace('stat[101]==15 && syscall_usage.stat[102]==18 && syscall_usage.stat[103]==15', 'stat[101]==18 && syscall_usage.stat[102]==18 && syscall_usage.stat[103]==12')
replace('222,223,224,225,226,227,228,229,230,231,234,236,237,238,239};','222,223,224,225,226,227,228,229,230,231,232,233,234,235,236,237,238,239,240,241};')
replace('timeout!=1000000', 'timeout!=100000 && timeout!=1000000')
replace('timer_cancel_count','timer_remove_count')
replace('assert(sleep_count==3 && wake_count==3 && queue_observations>=3 && timer_remove_count==3 && timeout_expiries==0);', 'assert(sleep_count==6 && wake_count==6 && queue_observations>=6 && timer_remove_count==6 && timeout_expiries==3);')
# Model-only second-request faults. Native observer must reject an old timeout
# duration or a missing fresh registration on the same waiter/object.
replace('cpu.end_time=cpu.start_time+timeout+(fault==234?1:0);', 'cpu.end_time=cpu.start_time+(fault==240 && timeout==1000000?100000:timeout)+(fault==234?1:0);')
replace('g_waiting.emplace_back(cpu.end_time,fault==238?g_ppu:&cpu);', 'if(!(fault==241 && timeout==1000000)){g_waiting.emplace_back(cpu.end_time,fault==238?g_ppu:&cpu);}')
replace('/deadline234/timer removal236/false expiry237/wrong timer waiter238/stale CPU link239 detected', '/timed result232/unqueue233/deadline234/holder ownership235/timer removal236/false expiry237/wrong timer waiter238/stale CPU link239/reused old duration240/missing new timer241 detected')
replace(';3registered1000000us waits/3timers cancelled by modeled awake/zero modeled expiries/3successful native lock returns/', ';6registered waits on3mutex handles/same waiter and handle expire100000us then wake1000000us/6modeled timer removals/3modeled expiries/3successful native wake returns/')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

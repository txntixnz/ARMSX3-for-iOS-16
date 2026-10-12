"""P74 extracted timed mutex unlock/wake path on explicit scheduler/timer models.
Usage: python test_p74_pair.py PPUThread.cpp CoreBridge.cpp Modules/sys_ppu_thread_.cpp
Native API/method/binder/SC/TLS/scope/observer bodies are extracted. Real guest
clock/wait_timeout/CPU check_state/CPU sleep/awake/atomic control remain models.
"""
from pathlib import Path
parent=Path(__file__).with_name('test_p73_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
def replace(before,after):
 global source
 assert before in source,before
 source=source.replace(before,after)
replace('P73','P74');replace('armsx3_core_test_mutex_timeout_expiry','armsx3_core_test_mutex_timed_wake')
replace('stat[101]==18 && syscall_usage.stat[102]==18 && syscall_usage.stat[103]==12', 'stat[101]==15 && syscall_usage.stat[102]==18 && syscall_usage.stat[103]==15')
replace('222,223,224,225,226,227,229,230,231,232,233,234,235,236};','222,223,224,225,226,227,228,229,230,231,234,236,237,238,239};')
replace("extras=extras.replace('template<class T>static bool wait_timeout", "extras='extern std::atomic<u32>timeout_expiries;\\n'+extras\nextras=extras.replace('template<class T>static bool wait_timeout")
# P73 expiry-return faults232/233/235 are inapplicable: this workload must be
# released by guest unlock and successfully consume a native signal instead.
# Same host scheduler/clock model, now with a1s request and explicit counters.
replace('timeout!=100000', 'timeout!=1000000')
replace('std::atomic<u32>sleep_count{0},wake_count{0},queue_observations{0};', 'std::atomic<u32>sleep_count{0},wake_count{0},queue_observations{0},timer_cancel_count{0},timeout_expiries{0};')
replace('g_waiting.emplace_back(cpu.end_time,&cpu);', 'g_waiting.emplace_back(cpu.end_time,fault==238?g_ppu:&cpu);')
replace('if(fault!=236){g_waiting.erase(', 'if(fault!=236){const auto timed=g_waiting.size();g_waiting.erase(')
replace('),g_waiting.end());}if(!found)', '),g_waiting.end());if(g_waiting.size()<timed)++timer_cancel_count;}if(!found)')
replace('std::this_thread::sleep_for(std::chrono::milliseconds(1));}return true;', 'std::this_thread::sleep_for(std::chrono::milliseconds(1));}++timeout_expiries;return true;')
replace('assert(sleep_count==3 && wake_count==3 && queue_observations>=3);', 'assert(sleep_count==3 && wake_count==3 && queue_observations>=3 && timer_cancel_count==3 && timeout_expiries==0);')
replace('queue_publications=0;sleep_count=0;', 'queue_publications=0;timer_cancel_count=0;timeout_expiries=0;sleep_count=0;')
replace("services=services.replace('ppu.gpr[3] = CELL_ETIMEDOUT;'", "services=services.replace('return not_an_error(ppu.gpr[3]);','if(timeout==1000000 && fault==237){ppu.gpr[3]=CELL_ETIMEDOUT;}if(timeout==1000000 && fault==239){ppu.next_cpu=&ppu;}return not_an_error(ppu.gpr[3]);')\nservices=services.replace('ppu.gpr[3] = CELL_ETIMEDOUT;'")
replace('+applicable queue225..227/229/', '+queue225..229/')
replace('/timed result232/unqueue233/deadline234/holder ownership235/timer removal236 detected', '/deadline234/timer removal236/false expiry237/wrong timer waiter238/stale CPU link239 detected')
replace(';3mutexlifecycles/all ownership', ';3registered1000000us waits/3timers cancelled by modeled awake/zero modeled expiries/3successful native lock returns/3mutexlifecycles/all ownership')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

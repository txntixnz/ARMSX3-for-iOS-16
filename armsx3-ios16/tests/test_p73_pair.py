"""P73 native timed mutex body/unqueue/scopes on explicit timer/scheduler models.
Usage: python test_p73_pair.py PPUThread.cpp CoreBridge.cpp Modules/sys_ppu_thread_.cpp
Native API/method/binder/SC/TLS/scope/observer bodies are extracted. Real guest
clock/wait_timeout/CPU check_state/CPU sleep/awake/atomic control remain models.
"""
from pathlib import Path
parent=Path(__file__).with_name('test_p72_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
def replace(before,after):
 global source
 assert before in source,before
 source=source.replace(before,after)
replace('P72','P73');replace('armsx3_core_test_mutex_sleep_wake','armsx3_core_test_mutex_timeout_expiry')
replace('stat[101]==15 && syscall_usage.stat[102]==18 && syscall_usage.stat[103]==15', 'stat[101]==18 && syscall_usage.stat[102]==18 && syscall_usage.stat[103]==12')
replace('222,223,224,225,226,227,228,229,230,231};','222,223,224,225,226,227,229,230,231,232,233,234,235,236};') # Reown228 is no longer used.
replace('mutex_header=', r'''shims=shims.replace('signal=128}', 'signal=128,notify=256}')
shims=shims.replace('struct PPUPrio{', 'void modeled_timeout_reschedule(ppu_thread&);\nstruct PPUPrio{')
shims=shims.replace('bool check_state(){state-=u32(cpu_flag::wait);return test_stopped();}', 'bool check_state(){if(state & cpu_flag::suspend)modeled_timeout_reschedule(*this);state-=u32(cpu_flag::wait)|u32(cpu_flag::signal);return test_stopped();}')
mutex_header=''' )
replace("services='\\n'.join", r'''# Deterministic host clock/storage/scheduler interface models exercise the
# actual native timeout return/unqueue branch. iOS runs original kernel waits.
extras=extras.replace('template<class T>static bool wait_timeout(u64,T*){throw std::runtime_error("timeout path not modeled");}', 'template<class T>static bool wait_timeout(u64 timeout,T*cpu){if(timeout!=100000){throw std::runtime_error("unexpected mutated timeout");}while(std::chrono::steady_clock::now().time_since_epoch()/std::chrono::microseconds(1)<s64(cpu->end_time)){if(cpu->state & cpu_flag::exit)return false;if(cpu->state & cpu_flag::signal)return false;std::this_thread::sleep_for(std::chrono::milliseconds(1));}return true;}')
extras=extras.replace('assert(!timeout);std::lock_guard lock(g_mutex);cpu.cancel_sleep=0;', 'if(timeout!=100000){throw std::runtime_error("unexpected mutated timeout");}std::lock_guard lock(g_mutex);cpu.cancel_sleep=0;')
extras=extras.replace('cpu.start_time=1;cpu.end_time=~u64{};++sleep_count;', 'cpu.start_time=u64(std::chrono::steady_clock::now().time_since_epoch()/std::chrono::microseconds(1));cpu.end_time=cpu.start_time+timeout+(fault==234?1:0);g_waiting.emplace_back(cpu.end_time,&cpu);++sleep_count;')
extras=extras.replace('if(!found){auto**last=', 'if(fault!=236){g_waiting.erase(std::remove_if(g_waiting.begin(),g_waiting.end(),[&](const auto&p){return p.second==base;}),g_waiting.end());}if(!found){auto**last=')
extras=extras.replace('static T* unqueue(T*& first, T* object, T* T::* mem_ptr = &T::next_cpu)\n\t{', 'static T* unqueue(T*& first, T* object, T* T::* mem_ptr = &T::next_cpu)\n\t{if constexpr(!ModifyNode){if(fault==233)return {};}')
extras+=r"""
constexpr u64 umax=~u64{};
void modeled_timeout_reschedule(ppu_thread&cpu){
 lv2_obj::awake(&cpu);
 if(!(cpu.state & cpu_flag::signal))throw std::runtime_error("missing timed scheduler signal");
}
"""
extras=extras.replace('static int ios_probe_mutex_sleep_state(ppu_thread*,ppu_thread*);', 'static int ios_probe_mutex_sleep_state(ppu_thread*,ppu_thread*);static int ios_probe_mutex_timeout_state(ppu_thread*,ppu_thread*,u64);static int ios_probe_mutex_timeout_finished(ppu_thread*,ppu_thread*);')
patch49=Path(__file__).resolve().parent.parent/'patches/0049-ios-lv2-mutex-timeout-observation.patch'
helper49='\n'.join(line[1:] for line in patch49.read_text().split('--- a/rpcs3/Emu/Cell/lv2/sys_sync.h')[0].splitlines() if line.startswith('+') and not line.startswith('+++'))
for signature in ['int lv2_obj::ios_probe_mutex_timeout_state(', 'int lv2_obj::ios_probe_mutex_timeout_finished(', 'extern "C" int armsx3_ios_ppu_probe_mutex_timeout_state(', 'extern "C" int armsx3_ios_ppu_probe_mutex_timeout_finished(']:
 body=function(helper49,signature)
 body=body.replace('waiter->state.all_of(cpu_flag::wait + cpu_flag::suspend)', '(queue_observations.fetch_add(1),waiter->state.all_of(cpu_flag::wait + cpu_flag::suspend))')
 extras+=body+'\n'
services='\n'.join''')
replace("services=services.replace('CellError result = mutex.try_lock(ppu);'", "services=services.replace('ppu.gpr[3] = CELL_ETIMEDOUT;','ppu.gpr[3] = fault==232?u64(CELL_OK):u64(CELL_ETIMEDOUT);')\nservices=services.replace('data.sq = sq;','if(fault==235){data.owner=0;}data.sq = sq;')\nservices=services.replace('CellError result = mutex.try_lock(ppu);'")
replace('scope restoration230..231 detected','scope restoration230..231/timed result232/unqueue233/deadline234/holder ownership235/timer removal236 detected')
replace('+queue225..229/','+applicable queue225..227/229/')
replace('actual sleep-awake scheduler/notify/registry remain host models','actual guest clock/wait_timeout/CPU check_state/sleep-awake scheduler/notify/registry remain host models')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

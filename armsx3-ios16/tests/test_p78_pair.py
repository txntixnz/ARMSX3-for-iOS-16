"""P78 extracted semaphore timeout/unqueue/permit recovery and guest workload.
Usage: python test_p78_pair.py PPUThread.cpp CoreBridge.cpp Modules/sys_ppu_thread_.cpp
Native semaphore bodies, queue methods, diagnostic scope/observers and guest
SC/binder/TLS run on explicit CPU/VM/ID/atomic/clock/scheduler host models.
"""
from pathlib import Path
parent=Path(__file__).with_name('test_p77_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
def replace(a,b):
 global source
 assert a in source,a
 source=source.replace(a,b)
replace('P77','P78')
replace('armsx3_core_test_semaphore_blocking_wake','armsx3_core_test_semaphore_timeout_recovery')
source=re.sub(r'(?<![a-zA-Z0-9_])2000000(?![a-zA-Z0-9_])','100000',source)
replace('stat[94]==21 && syscall_usage.stat[114]==15','stat[94]==18 && syscall_usage.stat[114]==18')
replace('260,261,262};','260,261,263,264,265,266};')
replace("shims=shims.replace('signal=128}'", "shims=shims.replace('bool check_state(){state-=u32(cpu_flag::wait);return test_stopped();}', 'bool check_state(){state-=u32(cpu_flag::wait)|u32(cpu_flag::signal);return test_stopped();}')\nshims=shims.replace('signal=128}'")
replace("'extern \"C\" int armsx3_ios_ppu_probe_mutex_timeout_state('])", "'extern \"C\" int armsx3_ios_ppu_probe_mutex_timeout_state(', 'extern \"C\" int armsx3_ios_ppu_probe_mutex_timeout_finished('])")
replace('g_waiting.erase(std::remove_if(g_waiting.begin(),g_waiting.end(),[&](const auto&p){return p.second==base;}),g_waiting.end());', 'if(fault!=266){g_waiting.erase(std::remove_if(g_waiting.begin(),g_waiting.end(),[&](const auto&p){return p.second==base;}),g_waiting.end());}')
replace("services=services.replace('return sema.val.try_dec(0);'", """services=services.replace('ppu.gpr[3] = CELL_ETIMEDOUT;', 'ppu.gpr[3] = fault==263?u64(CELL_OK):u64(CELL_ETIMEDOUT);')
services=services.replace('val++;', 'if(fault!=264){val++;}')
extras=extras.replace('static T* unqueue(T*& first, T* object, T* T::* mem_ptr = &T::next_cpu)\\n\\t{', 'static T* unqueue(T*& first, T* object, T* T::* mem_ptr = &T::next_cpu)\\n\\t{if(fault==265 && mem_ptr==&T::next_cpu){return {};}')
services=services.replace('return sema.val.try_dec(0);'""")
replace('8runs with three timed FIFO wake handoffs each', '8runs with three100000us timed FIFO expiries and same-object permit reuse each')
replace('missing scheduler scope260, rejected queue observation261 and missing wake signal262 detected', 'missing scope260/queue observation261/false timeout success263/lost permit recovery264/missing unqueue265/stale timer266 detected')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

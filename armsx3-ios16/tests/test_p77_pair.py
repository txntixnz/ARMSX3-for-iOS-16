"""P77 native semaphore slow wait/post + actual guarded scheduler scope.
Usage: python test_p77_pair.py PPUThread.cpp CoreBridge.cpp Modules/sys_ppu_thread_.cpp
Native services, queue algorithms, scope, observer, SC/binder/TLS/bounded bodies
are extracted. CPU/VM/ID/atomic storage/clock/scheduler remain host models.
"""
from pathlib import Path
parent=Path(__file__).with_name('test_p76_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
def replace(a,b):
 global source
 assert a in source,a
 source=source.replace(a,b)
replace('P76','P77');replace('armsx3_core_test_semaphore_lifecycle','armsx3_core_test_semaphore_blocking_wake')
replace('assert(semaphore_timeout_observations==9);', 'assert(sleep_count==3 && wake_count==3);assert(semaphore_timeout_observations==12);')
replace('stat[92]==9 && syscall_usage.stat[93]==12 && syscall_usage.stat[94]==18 && syscall_usage.stat[114]==18','stat[92]==12 && syscall_usage.stat[93]==9 && syscall_usage.stat[94]==21 && syscall_usage.stat[114]==15')
replace('semaphore_timeout_observations=0;', 'sleep_count=0;wake_count=0;semaphore_timeout_observations=0;')
# Leave older immediate-service and ABI negatives in place; add missing-scope,
# queued-wait observation and wake mutations below.
replace('248,250,252,253};', '248,250,252,253,260,261,262};')
replace("services='\\n'.join", r'''
shims=shims.replace('void notify_one(){}','void notify_one(){bits.notify_all();}void operator+=(u32 f){bits.fetch_or(f);}bool all_of(u32 f)const{return (bits.load()&f)==f;}bool none_of(u32 f)const{return !(bits.load()&f);}')
shims=shims.replace('void wait(u32){throw std::runtime_error("unexpected LV2 sleep");}', 'void wait(u32 s){bits.wait(s);}')
shims=shims.replace('void busy_wait(u32){throw std::runtime_error("unexpected mutex busy-wait");}', 'void busy_wait(u32){std::this_thread::yield();}')
shims=shims.replace('virtual~cpu_thread()=default;', 'static cpu_thread*get_current(){return current;}virtual~cpu_thread()=default;')
shims=shims.replace('signal=128}', 'signal=128,notify=256}')
shims=shims.replace('struct ppu_thread:cpu_thread {', 'struct PPUPrio{u64 all=1000;s64 prio=1000,order=0;bool preserve_bit=false;};struct Priority{PPUPrio value{};PPUPrio load()const{return value;}void operator=(PPUPrio p){value=p;}template<class F>void atomic_op(F f){f(value);value.all=u64(value.prio)|(u64(value.order)<<16);}};namespace std{template<>struct common_type<Priority>{using type=PPUPrio;};}\nstruct ppu_thread:cpu_thread{using ppu_prio_t=PPUPrio;Priority prio;ppu_thread*next_ppu=nullptr;bool ack_suspend=false;u64 start_time=0,end_time=0;u32 hw_sleep_time=0;')
sync=(native/'lv2/sys_sync.h').read_text()
a=extras.index(' struct notify_all_t{');b=extras.index('\n};\nstruct lv2_sema',a)
extras=extras[:a]+r"""
 static inline shared_mutex g_mutex;static inline atomic_t<u64>g_priority_order_tag{0};static inline ppu_thread*g_ppu=nullptr;
 static inline u32 g_pending=0;static inline thread_local std::vector<cpu_thread*>g_to_awake;
 static inline thread_local const void*g_to_notify[4]{};static inline thread_local bool g_postpone_notify_barrier=false;
 struct notify_all_t{notify_all_t(){g_postpone_notify_barrier=true;}~notify_all_t(){g_postpone_notify_barrier=false;}static void enqueue_on_top(const void*){}static void cleanup(){}};
 template<class T>static void prepare_for_sleep(T&){}
 static bool wait_timeout(u64,ppu_thread*);
 static bool awake(cpu_thread*);static void make_scheduler_ready();template<class T>static bool sleep(T&,u64);
 static int ios_probe_mutex_scheduler_and_call(ppu_thread*,ppu_thread*,int(*)(void*),void*);
 static int ios_probe_mutex_timeout_state(ppu_thread*,ppu_thread*,u64);
 static int ios_probe_mutex_timeout_finished(ppu_thread*,ppu_thread*);
 static void append(cpu_thread*cpu){g_to_awake.push_back(cpu);}
 static void awake_all(){for(auto*cpu:g_to_awake)awake(cpu);g_to_awake.clear();}
"""+function(sync,'static T* unqueue(T*& first')+'\n'+function(sync,'static E* schedule(T& first')+'\n'+function(sync,'static void emplace(T& first')+extras[b:]
extras=extras.replace('static T* unqueue(T*& first','template<bool ModifyNode=true,class T>static T* unqueue(T*& first')
extras=extras.replace('static E* schedule(T& first','template<class E,class T>static E* schedule(T& first')
extras=extras.replace('static void emplace(T& first','template<class T>static void emplace(T& first')
extras=extras.replace('static T load(const T&v){return v;}', 'static T load(const T&v){return v;}static void release(T&v,T x){v=x;}')
extras+=r"""
struct Ready{std::atomic<bool>value{false};operator bool()const{return value.load();}void release(bool x){value.store(x);}}g_scheduler_ready;
std::deque<std::pair<u64,cpu_thread*>>g_waiting;std::deque<cpu_thread*>g_to_sleep;u64 s_yield_frequency=0;
constexpr u64 umax=~u64{};std::atomic<u32>sleep_count{0},wake_count{0};
u64 model_now(){return u64(std::chrono::steady_clock::now().time_since_epoch()/std::chrono::microseconds(1));}
template<class T>bool lv2_obj::sleep(T&cpu,u64 timeout){
 if(timeout!=2000000)throw std::runtime_error("unexpected semaphore timeout ABI");
 std::lock_guard lock(g_mutex);cpu.cancel_sleep=0;
 if(!g_scheduler_ready || !unqueue(g_ppu,&cpu,&ppu_thread::next_ppu))throw std::runtime_error("sleeping unregistered worker");
 cpu.state+=u32(cpu_flag::wait)|u32(cpu_flag::suspend);
 cpu.start_time=model_now();cpu.end_time=cpu.start_time+timeout;g_waiting.emplace_back(cpu.end_time,&cpu);++sleep_count;return true;
}
bool lv2_obj::awake(cpu_thread*base){
 auto*cpu=static_cast<ppu_thread*>(base);std::lock_guard lock(g_mutex);bool found=false;
 for(auto*p=g_ppu;p;p=p->next_ppu)if(p==cpu)found=true;
 g_waiting.erase(std::remove_if(g_waiting.begin(),g_waiting.end(),[&](const auto&p){return p.second==base;}),g_waiting.end());
 if(!found){auto**last=&g_ppu;while(*last)last=&(*last)->next_ppu;*last=cpu;cpu->next_ppu=nullptr;}
 if(g_scheduler_ready && (cpu->state & cpu_flag::suspend)){
  cpu->state-=u32(cpu_flag::suspend);if(fault!=262)cpu->state+=cpu_flag::signal;cpu->start_time=0;cpu->state.notify_one();++wake_count;
 }
 return !found;
}
void lv2_obj::make_scheduler_ready(){g_scheduler_ready.release(true);}
bool lv2_obj::wait_timeout(u64 timeout,ppu_thread*cpu){
 if(timeout!=2000000)throw std::runtime_error("unexpected semaphore timeout ABI");
 while(model_now()<cpu->end_time){if(cpu->state & cpu_flag::exit)return false;if(cpu->state & cpu_flag::signal)return false;std::this_thread::sleep_for(std::chrono::milliseconds(1));}
 // Explicit host rescheduling model, not the native timer implementation.
 awake(cpu);return true;
}
"""
for patch_name,signatures in [
 ('0048-ios-lv2-mutex-sleep-wake-probe.patch',['int lv2_obj::ios_probe_mutex_scheduler_and_call(', 'extern "C" int armsx3_ios_ppu_probe_mutex_scheduler_and_call(']),
 ('0049-ios-lv2-mutex-timeout-observation.patch',['int lv2_obj::ios_probe_mutex_timeout_state(', 'int lv2_obj::ios_probe_mutex_timeout_finished(', 'extern "C" int armsx3_ios_ppu_probe_mutex_timeout_state('])]:
 patch=Path(__file__).resolve().parent.parent/'patches'/patch_name
 helper='\n'.join(line[1:] for line in patch.read_text().split('--- a/rpcs3/Emu/Cell/lv2/sys_sync.h')[0].splitlines() if line.startswith('+') and not line.startswith('+++'))
 for signature in signatures:extras+=function(helper,signature)+'\n'
extras=extras.replace('return lv2_obj::ios_probe_mutex_scheduler_and_call(context, peer, execute, user);','if(fault==260){return execute(user);}return lv2_obj::ios_probe_mutex_scheduler_and_call(context, peer, execute, user);')
extras=extras.replace('return lv2_obj::ios_probe_mutex_timeout_state(waiter, holder, timeout);','if(fault==261){return 0;}return lv2_obj::ios_probe_mutex_timeout_state(waiter, holder, timeout);')
services='\n'.join''')
# End-state restores native scope fields; missing-scope must fail, not false-pass.
replace('assert(id_manager::g_id==0 && idm::objects.empty());', 'assert(id_manager::g_id==0 && idm::objects.empty() && !lv2_obj::g_ppu && !g_scheduler_ready && !lv2_obj::g_priority_order_tag.load());')
a=source.index(' std::puts("PASS: P77/');b=source.index("''' +checks[b:]",a)
source=source[:a]+''' std::puts("PASS: P77 extracted native semaphore wait/post/queue algorithms/scheduler scope/deadline observer/SC/binder/TLS;8runs with three timed FIFO wake handoffs each, alternating worker roles, all72SC/context/DATA/TLS checks;missing scheduler scope260, rejected queue observation261 and missing wake signal262 detected;CPU/VM/ID/atomic storage/clock/scheduler remain host models;native iOS pending.");''' +source[b:]
exec(compile(source,str(Path(__file__).resolve()),'exec'))

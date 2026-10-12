"""P72 extracted mutex lock/queue methods + native diagnostic scheduler scope.
Usage: python test_p72_pair.py PPUThread.cpp CoreBridge.cpp Modules/sys_ppu_thread_.cpp
CPU/VM/ID storage/atomic control/priority/actual scheduler/notification/decoder
remain host models. Native five services, try_own/reown/FIFO/unqueue and native
scope/observation bodies are extracted. This is not an iOS compile.
"""
from pathlib import Path
parent=Path(__file__).with_name('test_p71_pair.py').read_text()
exec(compile(parent[:parent.index('exec(compile(source,')],str(Path(__file__).resolve()),'exec'))
def replace(before,after):
 global source
 assert before in source,before
 source=source.replace(before,after)
replace('P71','P72');replace('armsx3_core_test_mutex_lock_fast_paths','armsx3_core_test_mutex_sleep_wake')
# Add CPU/flag/priority interfaces before constructing the model objects.
replace('mutex_header=', r'''shims=shims.replace('void notify_one(){}','void notify_one(){bits.notify_all();}void operator+=(u32 f){bits.fetch_or(f);}bool all_of(u32 f)const{return (bits.load()&f)==f;}bool none_of(u32 f)const{return !(bits.load()&f);}')
shims=shims.replace('void wait(u32){throw std::runtime_error("unexpected LV2 sleep");}', 'void wait(u32 s){bits.wait(s);}')
shims=shims.replace('void busy_wait(u32){throw std::runtime_error("unexpected mutex busy-wait");}', 'void busy_wait(u32){std::this_thread::yield();}')
shims=shims.replace('virtual~cpu_thread()=default;', 'static cpu_thread*get_current(){return current;}virtual~cpu_thread()=default;')
shims=shims.replace('struct ppu_thread:cpu_thread {', 'struct PPUPrio{u64 all=1000;s64 prio=1000,order=0;bool preserve_bit=false;};struct Priority{PPUPrio value{};PPUPrio load()const{return value;}void operator=(PPUPrio p){value=p;}template<class F>void atomic_op(F f){f(value);value.all=u64(value.prio)|(u64(value.order)<<16);}};namespace std{template<>struct common_type<Priority>{using type=PPUPrio;};}\nstruct ppu_thread:cpu_thread{using ppu_prio_t=PPUPrio;Priority prio;ppu_thread*next_ppu=nullptr;bool ack_suspend=false;u64 start_time=0,end_time=0;u32 hw_sleep_time=0;')
mutex_header=''' )
# Replace compile-only P71 queue stubs with native queue methods and explicit
# host scheduler/atomic models. Scope guards/restoration themselves are native.
replace("services='\\n'.join", r'''sync=(native/'lv2/sys_sync.h').read_text()
patch=Path(__file__).resolve().parent.parent/'patches/0048-ios-lv2-mutex-sleep-wake-probe.patch'
helper='\n'.join(line[1:] for line in patch.read_text().split('--- a/rpcs3/Emu/Cell/lv2/sys_sync.h')[0].splitlines() if line.startswith('+') and not line.startswith('+++'))
extras=extras.replace('namespace id_manager{struct{bool is_lockable(){throw std::runtime_error("unexpected mutex contention");}}g_mutex;}', 'namespace id_manager{struct{bool is_lockable(){return true;}}g_mutex;}')
extras=extras.replace('template<class T>void awake(T*){assert(false);}', '')
a=extras.index('static bool has_ppus_in_running_state()');b=extras.index(' atomic_t<u32>exists',a)
extras=extras[:a]+r"""
 static inline shared_mutex g_mutex;static inline atomic_t<u64>g_priority_order_tag{0};static inline ppu_thread*g_ppu=nullptr;
 static inline u32 g_pending=0;static inline thread_local std::vector<cpu_thread*>g_to_awake;
 static inline thread_local const void*g_to_notify[4]{};static inline thread_local bool g_postpone_notify_barrier=false;
 static bool has_ppus_in_running_state(){return false;}template<class T>static void prepare_for_sleep(T&){}
 template<class T>static bool wait_timeout(u64,T*){throw std::runtime_error("timeout path not modeled");}
 static bool awake(cpu_thread*);static void make_scheduler_ready();template<class T>static bool sleep(T&,u64);
 static int ios_probe_mutex_scheduler_and_call(ppu_thread*,ppu_thread*,int(*)(void*),void*);
 static int ios_probe_mutex_sleep_state(ppu_thread*,ppu_thread*);
"""+function(sync,'static T* unqueue(T*& first')+'\n'+function(sync,'static E* schedule(T& first')+'\n'+extras[b:]
# These class templates need their original template headers too.
extras=extras.replace('static T* unqueue(T*& first','template<bool ModifyNode=true,class T>static T* unqueue(T*& first')
extras=extras.replace('static E* schedule(T& first','template<class E,class T>static E* schedule(T& first')
a=extras.index('template<class T>bool try_own(T&)');b=extras.index('struct Control{',a)
extras=extras[:a]+'template<class T>'+function(mutex_header,'bool try_own(T& cpu)')+'\n'+extras[b:]
extras=extras.replace('bool try_own(T& cpu)\n\t{', 'bool try_own(T& cpu)\n\t{if(fault==225)return false;')
# The earlier shim reown was deliberately unreachable. Extract actual method.
extras=extras.replace('template<class T>T*reown(){assert(false);return nullptr;}', 'template<class T>'+function(mutex_header,'T* reown()'))
extras=extras.replace('data.owner = res->id;', 'data.owner = fault==228?0:res->id;')
# Scalar control atomic operations are a serialized host model. Actual native
# queue algorithms above operate on it; no claim about ARM16-byte CAS is made.
a=extras.index('struct Control{');b=extras.index(' }control;',a)+len(' }control;')
extras=extras[:a]+r"""struct Control{
 mutable std::mutex guard;control_data_t value{};
 control_data_t load()const{std::lock_guard lock(guard);return value;}control_data_t&raw(){return value;}
 bool compare_and_swap_test(control_data_t a,control_data_t b){std::lock_guard lock(guard);if(a.owner!=value.owner||a.sq!=value.sq)return false;if(fault==207 && b.owner){b.owner++;}value=b;return true;}
 template<class F>auto atomic_op(F f){std::lock_guard lock(guard);return f(value);}
 template<class F>void fetch_op(F f){std::lock_guard lock(guard);auto data=value;if(f(data))value=data;}
 }control;"""+extras[b:]
extras=extras.replace('static T load(const T&v){return v;}', 'static T load(const T&v){return v;}static void release(T&v,T x){v=x;}')
extras+=r"""
struct Ready{std::atomic<bool>value{false};operator bool()const{return value.load();}void release(bool x){value.store(x);}}g_scheduler_ready;
std::deque<std::pair<u64,cpu_thread*>>g_waiting;std::deque<cpu_thread*>g_to_sleep;u64 s_yield_frequency=0;
std::atomic<u32>sleep_count{0},wake_count{0},queue_observations{0};
template<class T>bool lv2_obj::sleep(T&cpu,u64 timeout){
 assert(!timeout);std::lock_guard lock(g_mutex);cpu.cancel_sleep=0;
 cpu.state+=u32(cpu_flag::wait)|u32(cpu_flag::suspend);
 if(fault!=226 && !unqueue(g_ppu,&cpu,&ppu_thread::next_ppu))throw std::runtime_error("sleeping unregistered worker");
 if(fault==229)vm::write32(u32(cpu.gpr[6]),0);
 cpu.start_time=1;cpu.end_time=~u64{};++sleep_count;return true;
}
bool lv2_obj::awake(cpu_thread*base){
 auto*cpu=static_cast<ppu_thread*>(base);std::lock_guard lock(g_mutex);bool found=false;
 for(auto*p=g_ppu;p;p=p->next_ppu)if(p==cpu)found=true;
 if(!found){auto**last=&g_ppu;while(*last)last=&(*last)->next_ppu;*last=cpu;cpu->next_ppu=nullptr;}
 if(g_scheduler_ready && (cpu->state & cpu_flag::suspend)){
  cpu->state-=u32(cpu_flag::suspend);if(fault!=227){cpu->state+=cpu_flag::signal;}cpu->start_time=0;cpu->state.notify_one();++wake_count;
 }
 return !found;
}
void lv2_obj::make_scheduler_ready(){g_scheduler_ready.release(true);}
"""
# Patch declarations and full native helper implementations are extracted.
extras+=function(helper,'int lv2_obj::ios_probe_mutex_scheduler_and_call(')+'\n'
extras=extras.replace('context->prio = prior; peer->prio = peerPrior;', 'context->prio = prior; peer->prio = peerPrior;if(fault==230){context->prio.atomic_op([](auto&p){p.order++;});}')
extras=extras.replace('context->end_time = end; peer->end_time = peerEnd;', 'context->end_time = end+(fault==231?1:0); peer->end_time = peerEnd;')
extras+=function(helper,'int lv2_obj::ios_probe_mutex_sleep_state(')+'\n'
extras=extras.replace('waiter->state.all_of(cpu_flag::wait + cpu_flag::suspend)', '(queue_observations.fetch_add(1),waiter->state.all_of(cpu_flag::wait + cpu_flag::suspend))')
extras+=function(helper,'extern "C" int armsx3_ios_ppu_probe_mutex_scheduler_and_call(')+'\n'
extras+=function(helper,'extern "C" int armsx3_ios_ppu_probe_mutex_sleep_state(')+'\n'
services='\n'.join''')
# Full bound API workload retains72syscalls; it now sleeps/wakes exactly3 times.
replace('assert(lock_timeout_observations==18);', 'assert(sleep_count==3 && wake_count==3 && queue_observations>=3);assert(lock_timeout_observations==18);')
replace('queue_publications=0;lock_timeout_observations=0;', 'queue_publications=0;sleep_count=0;wake_count=0;queue_observations=0;lock_timeout_observations=0;')
replace('assert(id_manager::g_id==0 && idm::objects.empty());', 'assert(id_manager::g_id==0 && idm::objects.empty() && !lv2_obj::g_ppu && !g_scheduler_ready && !lv2_obj::g_priority_order_tag.load());')
replace(' const u32 priorID=0x8500ff01;', ' g_scheduler_ready.release(true);assert(armsx3_core_test_mutex_sleep_wake()==-1);assert(g_scheduler_ready && !lv2_obj::g_ppu);g_scheduler_ready.release(false);restored();\n const u32 priorID=0x8500ff01;')
replace('222,223,224};','222,223,224,225,226,227,228,229,230,231};')
replace('first construction/reuse/failed init/omitted init detected','first construction/reuse/failed init/omitted init/prior scheduler-ready preserved +queue225..229/scope restoration230..231 detected')
replace(' + try_lock/try_unlock + SC handler',' + try_lock/try_unlock/try_own/reown/FIFO/unqueue + native scheduler scope/blocked observation + SC handler')
replace('CPU/VM/ID allocator/atomic control/notify/registry remain host models','CPU/VM/ID allocator/atomic control/priority/actual sleep-awake scheduler/notify/registry remain host models')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

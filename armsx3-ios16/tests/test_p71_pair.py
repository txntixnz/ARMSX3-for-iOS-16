"""P71 actual sys_mutex_lock immediate paths and full64 timeout native ABI.

Usage: python test_p71_pair.py PPUThread.cpp CoreBridge.cpp Modules/sys_ppu_thread_.cpp
Native five services/lock methods/SC/binder/dispatcher/TLS/bounded bodies are
extracted. CPU/VM/ID/atomic control/registry/notify remain explicit host models.
Unused sleep/queue branches reject entry; this does not test LV2 scheduling.
"""
from pathlib import Path
source=Path(__file__).with_name('test_p69_pair.py').read_text()
def replace(before,after):
 global source
 assert before in source,before
 source=source.replace(before,after)
replace('P69','P71')
replace('armsx3_core_test_lv2_mutex_ownership','armsx3_core_test_mutex_lock_fast_paths')
replace('==92','==110')
replace('executed==600 && tls_stores==60 && output_stores==120','executed==720 && tls_stores==72 && output_stores==144')
replace('stat[101]==12 && syscall_usage.stat[103]==30 && syscall_usage.stat[104]==12','stat[101]==15 && syscall_usage.stat[102]==18 && syscall_usage.stat[103]==15 && syscall_usage.stat[104]==18')
replace('TLS=10/10','TLS=12/12');replace('TLS=20/20','TLS=24/24');replace('TLS=30/30','TLS=36/36')
replace('207,208,209,210','207,208,210')
replace('215,216,217};','215,216,217,22,220,221,222,223,224};')
replace("extras+='template<class T>'+lock", """lock=lock.replace('lock_count++;','if(fault==222){return CELL_EDEADLK;}if(fault!=220){lock_count++;}')
unlock=unlock.replace('lock_count--;','if(fault!=221){lock_count--;}')
extras+='template<class T>'+lock""")
replace('mutex_header=', r'''# The inherited decoder already has LD. Unify its simplified GPR cast shim
# to support u64 arguments without the older pair of ambiguous overloads.
a=shims.index('template<class T>u64 ppu_gpr_cast(');b=shims.index('namespace utils{',a)
shims=shims[:a]+'template<class T=u64,class S>T ppu_gpr_cast(const S&value){if constexpr(std::is_same_v<S,error_code>){if(fault==213)return T(u32(s32(value)));return T(s64(s32(value)));}else if constexpr(std::is_same_v<T,vm::ptr<atomic_be_t<u32>>>)return T{u32(value)};else{if constexpr(std::is_same_v<T,u64>){if(fault==224)return T(u32(value));}return T(value);}}\n'+shims[b:]
shims=shims.replace('again=64}', 'again=64,signal=128}')
shims=shims.replace('void notify_one(){}', 'void notify_one(){}u32 operator+()const{return bits.load();}bool test_and_reset(cpu_flag f){return bits.fetch_and(~u32(f))&u32(f);}void wait(u32){throw std::runtime_error("unexpected LV2 sleep");}')
shims=shims.replace('struct ppu_thread;', 'u32 operator&(u32 s,cpu_flag f){return s&u32(f);}using usz=std::size_t;bool is_stopped(u32 s){return s&3u;}void busy_wait(u32){throw std::runtime_error("unexpected mutex busy-wait");}\nstruct ppu_thread;')
shims=shims.replace('u32 res_notify=0;', 'ppu_thread*next_cpu=nullptr;u32 cancel_sleep=0;u32 res_notify=0;')
mutex_header=''' )
replace("[(100,'create'),(101,'destroy'),(103,'trylock'),(104,'unlock')]", "[(100,'create'),(101,'destroy'),(102,'lock'),(103,'trylock'),(104,'unlock')]")
replace("services='\\n'.join", r'''# Unused branches of the complete native lock body need interfaces to compile.
# They deliberately fail if called: only immediate/recursive/invalid lock is
# supported by this host model. Native iOS compiles the actual scheduler APIs.
extras=extras.replace('CELL_ESRCH=0x80010005,','CELL_ETIMEDOUT=0x8001000b,CELL_ESRCH=0x80010005,')
extras=extras.replace('using shared_mutex=std::mutex;', 'struct shared_mutex:std::mutex{void lock_unlock(){throw std::runtime_error("unexpected reschedule");}};')
extras=extras.replace('struct lv2_obj{', 'namespace id_manager{struct{bool is_lockable(){throw std::runtime_error("unexpected mutex contention");}}g_mutex;}\nstruct lv2_obj{\nstatic bool has_ppus_in_running_state(){throw std::runtime_error("unexpected scheduler");}template<class T>static void prepare_for_sleep(T&){throw std::runtime_error("unexpected prepare sleep");}template<class T>static bool wait_timeout(u64,T*){throw std::runtime_error("unexpected timeout wait");}')
extras=extras.replace('struct Control{', 'template<class T>bool try_own(T&){throw std::runtime_error("unexpected queue entry");}template<class T>bool sleep(T&,u64){throw std::runtime_error("unexpected mutex sleep");}template<bool B,class T>bool unqueue(T&,ppu_thread*){throw std::runtime_error("unexpected unqueue");}\nstruct Control{')
extras=extras.replace('control_data_t value{};', 'template<class F>void fetch_op(F){throw std::runtime_error("unexpected queue mutation");}control_data_t value{};')
# Logger overload observes the actual u64 parameter inside the extracted native
# service. This catches binder truncation even if r4/history remain unchanged.
extras=extras.replace('struct {template<class...T>void trace', 'std::atomic<u32>lock_timeout_observations{0};\nstruct {void trace(const char*text,u32,u64 timeout){if(std::string_view(text).starts_with("sys_mutex_lock(")){auto*c=static_cast<ppu_thread*>(get_current_cpu_thread());if(!c||timeout!=c->gpr[4])throw std::runtime_error("native timeout parameter truncated");++lock_timeout_observations;}}template<class...T>void trace')
services='\n'.join''')
replace("'error_code sys_mutex_destroy(', 'error_code sys_mutex_trylock('", "'error_code sys_mutex_destroy(', 'error_code sys_mutex_lock(', 'error_code sys_mutex_trylock('")
replace("services=services.replace('return CELL_EBUSY;'", "services=services.replace('CellError result = mutex.try_lock(ppu);','CellError result = fault==223?CellError{}:mutex.try_lock(ppu);')\nservices=services.replace('return CELL_EBUSY;'")
replace('table[103]={BIND_FUNC(sys_mutex_trylock)', 'table[102]={BIND_FUNC(sys_mutex_lock),"sys_mutex_lock"};table[103]={BIND_FUNC(sys_mutex_trylock)')
replace('assert(syscall_usage.stat[100]==6', 'assert(lock_timeout_observations==18);assert(syscall_usage.stat[100]==6')
replace('queue_publications=0;for(auto&v:', 'queue_publications=0;lock_timeout_observations=0;for(auto&v:')
replace('8runs/16workers/1440slices/60SC each/600instructions/92pubs','8runs/16workers/1728slices/72SC each/18native lock timeout observations/720instructions/110pubs')
replace('memory/TLS30/30','memory/TLS36/36')
replace('native mutex create/destroy/trylock/unlock','native mutex create/destroy/lock/trylock/unlock')
replace('foundational and207..219','foundational/applicable207..219/recursive220..222/lock223/timeout224')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

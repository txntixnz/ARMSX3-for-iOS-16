"""P86-P89 extracted native mutex and condition wait/reacquisition workload.
Usage: test_p86_pair.py PPUThread.cpp CoreBridge.cpp sys_ppu_thread_.cpp [fifo|recursive|broadcast|recursive_broadcast]
CPU/VM/ID/storage atomics/scheduler/clock/savestate interfaces are host models.
"""
from pathlib import Path
import re,sys
profile=sys.argv.pop() if len(sys.argv)==5 else 'fifo'
assert profile in ('fifo','recursive','broadcast','recursive_broadcast'),profile
symbol='armsx3_core_test_cond_'+profile
parent=Path(__file__).with_name('test_p79_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
def replace(a,b):
 global source
 assert a in source,a
 source=source.replace(a,b)
replace('P79','P86-P89');replace('armsx3_core_test_semaphore_timeout_then_wake',symbol)
replace("lv2_sema',a)", "lv2_mutex',a)")
# Fault260 skips scheduler admission while retaining priority cleanup; native
# cond_wait queues (and assigns an order tag) before calling sleep.
replace('if(fault==260){return execute(user);}', 'if(fault==260){struct NoAdmissionCleanup{ppu_thread*c,*p;PPUPrio a,b;u64 tag;~NoAdmissionCleanup(){c->prio=a;p->prio=b;lv2_obj::g_priority_order_tag=tag;}}cleanup{context,peer,context->prio.load(),peer->prio.load(),lv2_obj::g_priority_order_tag.load()};return execute(user);}')
replace('==119','==164')
replace('template<class T>static bool sleep(T&,u64);','template<class T>static bool sleep(T&,u64=0);')
replace('using std::atomic<T>::atomic;', 'using std::atomic<T>::atomic;void release(T x){this->store(x,std::memory_order_release);}')
replace('using shared_mutex=std::mutex;', 'struct shared_mutex:std::mutex{void lock_unlock(){std::lock_guard lock(*this);}};')
replace('constexpr u32 SYS_SYNC_FIFO=1,SYS_SYNC_PRIORITY=2,SYS_SYNC_NOT_PROCESS_SHARED=0x200;', 'constexpr u32 SYS_SYNC_FIFO=1,SYS_SYNC_PRIORITY=2,SYS_SYNC_PRIORITY_INHERIT=3,SYS_SYNC_RECURSIVE=0x10,SYS_SYNC_NOT_RECURSIVE=0x20,SYS_SYNC_NOT_PROCESS_SHARED=0x200,SYS_SYNC_NOT_ADAPTIVE=0x2000;')
# Cond wait only reads zero savestate data during normal execution. Writes are
# modeled for bounded abort cleanup; no serialized-state restoration is tested.
replace("shims=shims.replace('signal=128}'", """shims=shims.replace('struct ppu_thread:cpu_thread {', 'struct CondState{template<class T>std::pair<bool,T>try_read(){return {false,0};}void clear(){}template<class T>void operator()(T){}};\\nstruct ppu_thread:cpu_thread {bool loaded_from_savestate=false;std::unique_ptr<CondState>optional_savestate_state=std::make_unique<CondState>();')
shims=shims.replace('state.bits=u32(cpu_flag::stop);', 'state.bits=u32(cpu_flag::stop);if(fault==309)optional_savestate_state.reset();if(fault==310)loaded_from_savestate=true;')
shims=shims.replace('signal=128}'""")
# Native on_id_create contains deferred savestate code; its branch is excluded.
replace('semaphore_source=(native/', 'mutex_header=(native/\'lv2/sys_mutex.h\').read_text();mutex_source=(native/\'lv2/sys_mutex.cpp\').read_text();cond_header=(native/\'lv2/sys_cond.h\').read_text();cond_source=(native/\'lv2/sys_cond.cpp\').read_text()\nsemaphore_source=(native/')
# Replace API-table source assertions with the condition/mutex family.
a=source.index('for code,name in [(90,');b=source.index('# Atomic storage',a)
source=source[:a]+'''for code,name in [(100,'sys_mutex_create'),(101,'sys_mutex_destroy'),(103,'sys_mutex_trylock'),(104,'sys_mutex_unlock'),(105,'sys_cond_create'),(106,'sys_cond_destroy'),(107,'sys_cond_wait'),(108,'sys_cond_signal'),(109,'sys_cond_signal_all'),(110,'sys_cond_signal_to')]:
 assert re.search(r'BIND_SYSC\\('+name+r'\\),\\s*//'+str(code)+r'\\s+\\(0x'+f'{code:03x}'+r'\\)',lv2,re.I)
assert 'id_base = 0x86000000' in cond_header
'''+source[b:]
replace('"sys_semaphore_wait("', '"sys_cond_wait("')
replace('}sys_semaphore,ppu_log;', '}sys_mutex,sys_cond,ppu_log;')
a=source.index('struct sys_semaphore_attribute_t');b=source.index('struct lv2_obj{',a)
source=source[:a]+'''struct sys_mutex_attribute_t{be_t<u32>protocol,recursive,pshared,adaptive;be_t<u64>ipc_key;be_t<s32>flags;be_t<u32>pad;union{u64 name_u64;char name[8];};};
struct sys_cond_attribute_t{be_t<u32>pshared;be_t<s32>flags;be_t<u64>ipc_key;union{u64 name_u64;char name[8];};};
'''+source[b:]
replace('struct lv2_obj{', 'struct lv2_obj{virtual~lv2_obj()=default;template<class T>static bool check(T*obj){return obj && obj->exists.load()==1;}')
a=source.index('struct lv2_sema:lv2_obj{');b=source.index('class idm{',a)
source=source[:a]+'''struct lv2_mutex:lv2_obj{
 static constexpr u32 id_base=0x85000000;
 const u32 protocol,recursive,adaptive;const u64 key,name;
 u32 cond_count=0;shared_mutex mutex;atomic_t<u32>lock_count{0};
 struct control_data_t{u32 owner=0,reserved=0;ppu_thread*sq=nullptr;};
 struct Control{mutable std::mutex guard;control_data_t value{};
  control_data_t load()const{std::lock_guard lock(guard);return value;}control_data_t&raw(){return value;}
  bool compare_and_swap_test(control_data_t a,control_data_t b){std::lock_guard lock(guard);if(a.owner!=value.owner||a.sq!=value.sq)return false;value=b;return true;}
  template<class F>auto atomic_op(F f){std::lock_guard lock(guard);return f(value);}
  template<class F>void fetch_op(F f){std::lock_guard lock(guard);auto data=value;if(f(data))value=data;}
 }control;
 lv2_mutex(u32 p,u32 r,u32 a,u64 k,u64 n):protocol(p),recursive(r),adaptive(a),key(k),name(n){}
 template<class T>CellError try_lock(T&);template<class T>CellError try_unlock(T&);template<class T>bool try_own(T&);template<class T>T*reown();
};
struct lv2_cond:lv2_obj{
 static constexpr u32 id_base=0x86000000;
 const u64 key,name;const u32 mtx_id;lv2_mutex*mutex;shared_ptr<lv2_obj>_mutex;ppu_thread*sq=nullptr;
 atomic_t<u64>dbg_last_signal_us{0},dbg_signal_count{0};atomic_t<u32>dbg_last_signaller{0};
 lv2_cond(u64,u64,u32,shared_ptr<lv2_obj>)noexcept;CellError on_id_create();
};
'''+source[b:]
a=source.index('class idm{');b=source.index('atomic_t<u64>g_sema_wait_us',a)
source=source[:a]+'''class idm{public:
 static inline std::recursive_mutex guard;static inline std::map<u32,shared_ptr<lv2_obj>>objects;static inline u32 cookie=0;
 template<class T>static u32 last_id(){return fault==214?0xdeadbeef:id_manager::g_id;}
 template<class B,class T>static shared_ptr<T>get_unlocked(u32 id){std::lock_guard lock(guard);auto it=objects.find(id);if(it==objects.end()||(id&0xff000000u)!=T::id_base)return {};return std::static_pointer_cast<T>(it->second);}
 template<class B,class T>static shared_ptr<T>check_unlocked(u32 id){return get_unlocked<B,T>(id);}
 template<class T>static T*check_unlocked(u32 id){if(id)throw std::runtime_error("registered targeted thread is outside host workload");return nullptr;}
 template<class B,class T,class F>static u32 import(F make){
  std::lock_guard lock(guard);if(!fxo.mutexRegistryReady)return 0;
  const u32 id=T::id_base+0x800+(++cookie&255);auto object=make();if(!object)return 0;
  if constexpr(std::is_same_v<T,lv2_cond>){if(object->on_id_create())return 0;}else object->exists=1;
  if(fault==216)object->exists=2;
  objects[id]=object;id_manager::g_id=id;return id;
 }
 template<class T,class R>struct Pair{shared_ptr<T>ptr;R ret{};explicit operator bool()const{return bool(ptr);}T*operator->()const{return ptr.get();}};
 template<class B,class T,class F>static auto get(u32 id,F f){
  std::lock_guard lock(guard);auto ptr=get_unlocked<B,T>(id);using R=std::invoke_result_t<F,T&>;
  if constexpr(std::is_void_v<R>){if(!ptr)return shared_ptr<T>{};f(*ptr);return ptr;}
  else{if(!ptr)return Pair<T,R>{};return Pair<T,R>{ptr,f(*ptr)};}
 }
 template<class B,class T,class F>static auto check(u32 id,F f){return get<B,T>(id,std::move(f));}
 template<class B,class T,class F>static Pair<T,CellError>withdraw(u32 id,F f){
  std::lock_guard lock(guard);auto ptr=get_unlocked<B,T>(id);if(!ptr)return {};
  const CellError error=f(*ptr);if(!error && !(fault==212 && ptr->exists==0 && get_current_cpu_thread()!=nullptr))objects.erase(id);return {ptr,error};
 }
 template<class B,class T,class F>static u32 select(F f){std::lock_guard lock(guard);u32 n=0;for(auto&entry:objects)if((entry.first&0xff000000u)==T::id_base){f(entry.first,*entry.second);++n;}return n;}
};
template<class T,class F>error_code lv2_obj::create(u32 shared,u64 key,s32,F make){
 assert(shared==SYS_SYNC_NOT_PROCESS_SHARED && !key);return idm::import<lv2_obj,T>(make)?CELL_OK:s32(0x80010001);
}
template<class T,class...A>auto make_single(A&&...a){return std::make_shared<T>(std::forward<A>(a)...);}
''' +source[b:]
# Preserve complete native scheduler/probe bodies and append mutex/cond methods.
a=source.index("services='\\n'.join");b=source.index('table=r"""',a)
source=source[:a]+r'''
for sig in ['CellError try_lock(T& cpu)', 'CellError try_unlock(T& cpu)', 'bool try_own(T& cpu)', 'T* reown()']:
 body=function(mutex_header,sig)
 body=body.replace('CellError try_', 'CellError lv2_mutex::try_',1).replace('bool try_own(', 'bool lv2_mutex::try_own(',1).replace('T* reown(', 'T* lv2_mutex::reown(',1)
 extras+='template<class T>'+body+'\n'
constructor=function(cond_source,'lv2_cond::lv2_cond(u64 key,')
extras+=constructor+'\n'
on_create=function(cond_source,'CellError lv2_cond::on_id_create()')
a=on_create.index('\n\tensure(!!Emu.DeserialManager())');on_create=on_create[:a]+'\n throw std::runtime_error("serialized cond creation is outside host workload");\n}'
on_create=on_create.replace('_this->mutex->cond_count++;','if(fault!=301){_this->mutex->cond_count++;}')
extras+=on_create+'\n'
extras=extras.replace('static T* unqueue(T*& first, T* object, T* T::* mem_ptr = &T::next_cpu)\n\t{', 'static T* unqueue(T*& first, T* object, T* T::* mem_ptr = &T::next_cpu)\n\t{if(fault==265 && mem_ptr==&T::next_cpu){return {};}')
services='\n'.join(function(mutex_source,'error_code sys_mutex_'+n+'(') for n in ['create','destroy','trylock','unlock'])+'\n'
services+='\n'.join(function(cond_source,'error_code sys_cond_'+n+'(') for n in ['create','destroy','wait','signal','signal_all','signal_to'])
services=services.replace('ppu.gpr[3] = CELL_ETIMEDOUT;', 'ppu.gpr[3] = fault==263?u64(CELL_OK):u64(CELL_ETIMEDOUT);')
services=services.replace('if (mutex.cond_count)', 'if (fault!=302 && mutex.cond_count)')
services=services.replace('if (atomic_storage<ppu_thread*>::load(cond.sq))\n\t\t{\n\t\t\treturn CELL_EBUSY;', 'if (atomic_storage<ppu_thread*>::load(cond.sq))\n\t\t{\n\t\t\treturn fault==303?CellError{}:CELL_EBUSY;')
services=services.replace('cond.mutex->cond_count--;', 'if(fault!=304){cond.mutex->cond_count--;}')
services=services.replace('const u32 count = cond.mutex->lock_count.exchange(0);', 'const u32 count = fault==305?u32(cond.mutex->lock_count.load()):cond.mutex->lock_count.exchange(0);')
services=services.replace('cond->mutex->lock_count.release(static_cast<u32>(cond.ret));', 'cond->mutex->lock_count.release(fault==306?0u:static_cast<u32>(cond.ret));')
services=services.replace('c->dbg_signal_count++;', 'if(fault!=307){c->dbg_signal_count++;}')
services=services.replace('return CELL_EPERM;', 'return fault==308?CellError{}:CELL_EPERM;')
services=services.replace('const u32 protocol = _attr.protocol;', 'const u32 protocol = _attr.protocol;')
''' +source[b:]
a=source.index(' table[90]=');b=source.index('return table;}();',a)
entries=[(100,'sys_mutex_create'),(101,'sys_mutex_destroy'),(103,'sys_mutex_trylock'),(104,'sys_mutex_unlock'),(105,'sys_cond_create'),(106,'sys_cond_destroy'),(107,'sys_cond_wait'),(108,'sys_cond_signal'),(109,'sys_cond_signal_all'),(110,'sys_cond_signal_to')]
source=source[:a]+''.join(f' table[{code}]={{BIND_FUNC({name}),"{name}"}};\n' for code,name in entries)+source[b:]
needle='phase=function(bridge,\'extern "C" __attribute__((visibility("default"))) int '+symbol+'(\')'
replace(needle, 'phase=function(bridge,\'static int armsx3_core_test_cond_batch(\')+"\\n"+function(bridge,\'extern "C" __attribute__((visibility("default"))) int '+symbol+'(\')')
replace('executed==936 && tls_stores==78 && output_stores==156','executed==1296 && tls_stores==108 && output_stores==216')
a=source.index('assert(syscall_usage.stat[90]');b=source.index("\n''' +checks[b:]",a)
first=[100,105,101,103,103,107,107,104,104,107,109,103,103,103,104,101,106,105]
second=[100,105,107,104,108,106,109 if 'broadcast' in profile else 108,103,103,103,110,104,104,106,108,107,104,109]
from collections import Counter
counts=Counter(first+second)
source=source[:a]+'assert('+ ' && '.join(f'syscall_usage.stat[{c}]=={n*3}' for c,n in sorted(counts.items()))+');'+source[b:]
for old,new in [(13,18),(26,36),(39,54)]:replace(f'TLS={old}/{old}',f'TLS={new}/{new}')
faults=[2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,26,27,36,37,38,39,40,41,60,173,174,175,176,177,179,180,22,212,213,214,216,224,260,261,262,263,265,266,301,302,303,304,307,308,309,310]
if 'recursive' in profile:faults.extend([305,306])
source=re.sub(r'const std::vector<int> faults\{[0-9,]+\};','const std::vector<int> faults{'+','.join(map(str,faults))+'};',source)
replace('const u32 priorID=0x9600ff01;', 'const u32 priorID=0x8500ff01;')
replace('std::make_shared<lv2_sema>(1,0,0,3,2)', 'std::make_shared<lv2_mutex>(1,SYS_SYNC_NOT_RECURSIVE,SYS_SYNC_NOT_ADAPTIVE,0,0)')
a=source.index(' std::puts("PASS: P86-P89');b=source.index("''' +checks[b:]",a)
source=source[:a]+' std::puts("PASS: '+profile+' P86-P89 native mutex/cond APIs/methods/constructor/link creation/binder/SC/TLS/bounded/scheduler scope;8runs/16workers/108SC each/three timeout then signal-reacquire lifecycles/full context/link/count/metadata/cleanup;applicable setup/ABI/registry/queue/link/permission/recursive-count mutations detected;CPU/VM/ID/atomic control/clock/scheduler/savestate interfaces are host models;native iOS pending.");'+source[b:]
instrument=r"""checks=checks.replace('void restored(){', 'void restored(){if(!(id_manager::g_id==0 && idm::objects.empty() && !lv2_obj::g_ppu && !g_scheduler_ready && !lv2_obj::g_priority_order_tag.load())){std::fprintf(stderr,"restore fault=%u objects=%zu ready=%u priority=%llu",fault,idm::objects.size(),unsigned(bool(g_scheduler_ready)),(unsigned long long)lv2_obj::g_priority_order_tag.load());std::fputc(10,stderr);}')"""
source=source.replace('\nwith tempfile.TemporaryDirectory', '\n'+instrument+'\nwith tempfile.TemporaryDirectory')
source=source.replace('str(binary)],check=True)', 'str(binary)],check=True,timeout=180)')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

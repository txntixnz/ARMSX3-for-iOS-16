"""Extract six native semaphore services + guest SC/binder/dispatcher/TLS/bounded.
Usage: python test_p76_pair.py PPUThread.cpp CoreBridge.cpp Modules/sys_ppu_thread_.cpp
CPU/VM/ID/atomic storage/notification/clock/profiler remain host models.
All sleep/queue stubs reject entry: only immediate semaphore waits are tested.
"""
from pathlib import Path
import re
parent=Path(__file__).with_name('test_p71_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
def replace(a,b):
 global source
 assert a in source,a
 source=source.replace(a,b)
replace('P71','P76');replace('armsx3_core_test_mutex_lock_fast_paths','armsx3_core_test_semaphore_lifecycle')
replace('size==40','size==48');replace('executed==720','executed==864')
a=source.index('mutex_header=');b=source.index('# General vm::ptr<> ABI',a)
source=source[:a]+r'''
semaphore_source=(native/'lv2/sys_semaphore.cpp').read_text();header=(native/'lv2/sys_semaphore.h').read_text();lv2=(native/'lv2/lv2.cpp').read_text()
for code,name in [(90,'create'),(91,'destroy'),(92,'wait'),(93,'trywait'),(94,'post'),(114,'get_value')]:
 assert re.search(r'BIND_SYSC\(sys_semaphore_'+name+r'\),\s*//'+str(code)+r'\s+\(0x'+f'{code:03x}'+r'\)',lv2,re.I)
assert 'id_base = 0x96000000' in header
# Atomic storage is a std::atomic model of the interface, not ARM atomics.
shims=shims.replace('template<class T>using atomic_t=std::atomic<T>;',r"""
template<class T>struct ModelAtomic:std::atomic<T>{
 using std::atomic<T>::atomic;using std::atomic<T>::operator=;
 bool compare_and_swap_test(T old,T value){return this->compare_exchange_strong(old,value);}
 bool try_dec(T limit){T old=this->load();while(old>limit){if(this->compare_exchange_weak(old,old-1))return true;}return false;}
 template<class F>auto fetch_op(F f){T old=this->load();for(;;){T value=old;
  if constexpr(std::is_void_v<std::invoke_result_t<F,T&>>){f(value);if(this->compare_exchange_weak(old,value))return old;}
  else{const bool ok=f(value);if(!ok)return std::pair<T,bool>{old,false};if(this->compare_exchange_weak(old,value))return std::pair<T,bool>{old,true};}
 }}
};template<class T>using atomic_t=ModelAtomic<T>;
""")
extras=r"""
#include <map>
#include <functional>
#include <string_view>
#undef ensure
template<class T>T checked(T value){if(!value)throw std::runtime_error("failed native ensure");return value;}
#define ensure(x) checked(x)
enum CellError:u32{CELL_ESRCH=0x80010005,CELL_EDEADLK=0x80010008,CELL_EPERM=0x80010009,CELL_EFAULT=0x8001000d,
 CELL_EINVAL=0x80010002,CELL_EKRESOURCE=0x80010011,CELL_EBUSY=0x8001000a,CELL_ETIMEDOUT=0x8001000b};
constexpr u32 SYS_SYNC_FIFO=1,SYS_SYNC_PRIORITY=2,SYS_SYNC_NOT_PROCESS_SHARED=0x200;
using shared_mutex=std::mutex;template<class T>using shared_ptr=std::shared_ptr<T>;using std::make_shared;
std::atomic<u32>semaphore_timeout_observations{0};
struct Logger{
 void trace(const char*text,u32,u64 timeout){if(std::string_view(text).starts_with("sys_semaphore_wait(")){
  auto*c=static_cast<ppu_thread*>(get_current_cpu_thread());if(!c||timeout!=c->gpr[4])throw std::runtime_error("native wait timeout truncated");++semaphore_timeout_observations;
 }}
 template<class...T>void trace(const char*,T...){}template<class...T>void error(const char*,T...){}
 template<class...T>void warning(const char*,T...){}template<class...T>void todo(const char*,T...){}
}sys_semaphore,ppu_log;
namespace fmt{template<class...T>[[noreturn]]void throw_exception(const char*,T...){throw std::runtime_error("native invalid SC");}}
template<class T>struct atomic_storage{static T load(const T&v){return v;}};
namespace vm{template<class T>auto*_ptr(u32 addr){return &*ptr<T>{addr};}const void*reservation_notifier_notify(u32,u64,bool){return nullptr;}}
namespace rsx::prof{bool enabled(){return false;}}
namespace utils{u64 get_tsc(){return 1000;}u64 get_tsc_freq(){return 1000000;}}
u64 get_system_time(){return 123456;}
struct sys_semaphore_attribute_t{be_t<u32>protocol,pshared;be_t<u64>ipc_key;be_t<s32>flags;be_t<u32>pad;union{u64 name_u64;char name[8];};};
struct lv2_obj{
 atomic_t<u32>exists{0};
 template<class T>static u64 get_key(const T&){return 0;}
 template<class T,class F>static error_code create(u32,u64,s32,F);
 template<class T>static void on_id_destroy(T&obj,u64 key){assert(!key);obj.exists--;}
 struct notify_all_t{~notify_all_t(){}static void enqueue_on_top(const void*){}static void cleanup(){}};
 template<class T>static void prepare_for_sleep(T&){throw std::runtime_error("unexpected semaphore sleep preparation");}
 template<class T>static bool wait_timeout(u64,T*){throw std::runtime_error("unexpected semaphore timeout");}
 template<class T>static void emplace(T&,ppu_thread*){throw std::runtime_error("unexpected semaphore queue");}
 template<class T>static T unqueue(T&,ppu_thread*){throw std::runtime_error("unexpected semaphore unqueue");}
 template<class T,class S>static T*schedule(S&,u32){throw std::runtime_error("unexpected semaphore schedule");}
 void append(ppu_thread*){throw std::runtime_error("unexpected semaphore append");}
 static void awake_all(){throw std::runtime_error("unexpected semaphore wake");}
 template<class T>bool sleep(T&,u64){throw std::runtime_error("unexpected semaphore sleep");}
};
struct lv2_sema:lv2_obj{
 static constexpr u32 id_base=0x96000000;
 const u32 protocol;const u64 key,name;const s32 max;shared_mutex mutex;atomic_t<s32>val;
 atomic_t<u64>dbg_last_post_us{0};atomic_t<u32>dbg_last_poster{0};atomic_t<u64>dbg_post_count{0};atomic_t<u32>dbg_last_post_lr{0};ppu_thread*sq=nullptr;
 lv2_sema(u32 p,u64 k,u64 n,s32 m,s32 v):protocol(p),key(k),name(n),max(fault==250?m+1:m),val(v){}
};
class idm{public:
 static inline std::recursive_mutex guard;static inline std::map<u32,shared_ptr<lv2_sema>>objects;static inline u32 cookie=0;
 template<class T>static u32 last_id(){return fault==214?0xdeadbeef:id_manager::g_id;}
 template<class B,class T,class F>static u32 import(F make){
  std::lock_guard lock(guard);if(!fxo.mutexRegistryReady)return 0;
  const u32 id=lv2_sema::id_base+0x800+(++cookie&255);
  auto object=make();if(!object)return 0;object->exists=fault==216?2:1;objects[id]=object;id_manager::g_id=id;return id;
 }
 template<class T,class R>struct Pair{shared_ptr<T>ptr;R ret{};explicit operator bool()const{return bool(ptr);}T*operator->()const{return ptr.get();}};
 template<class B,class T,class F>static auto get(u32 id,F f){
  std::lock_guard lock(guard);auto it=objects.find(id);using R=std::invoke_result_t<F,T&>;
  if constexpr(std::is_void_v<R>){if(it==objects.end())return shared_ptr<T>{};f(*it->second);return it->second;}
  else{if(it==objects.end())return Pair<T,R>{};return Pair<T,R>{it->second,f(*it->second)};}
 }
 template<class B,class T,class F>static auto check(u32 id,F f){return get<B,T>(id,std::move(f));}
 template<class B,class T,class F>static Pair<T,CellError>withdraw(u32 id,F f){
  std::lock_guard lock(guard);auto it=objects.find(id);if(it==objects.end())return {};
  auto ptr=it->second;const CellError error=f(*ptr);if(!error && !(fault==212 && ptr->exists==0))objects.erase(it);return {ptr,error};
 }
 template<class B,class T,class F>static u32 select(F f){std::lock_guard lock(guard);for(auto&entry:objects)f(entry.first,*entry.second);return objects.size();}
};
template<class T,class F>error_code lv2_obj::create(u32 shared,u64 key,s32,F make){
 assert(shared==SYS_SYNC_NOT_PROCESS_SHARED && !key);return idm::import<lv2_obj,T>(make)?CELL_OK:s32(0x80010001);
}
atomic_t<u64>g_sema_wait_us{0},g_sema_wait_count{0},g_sema_wait_max_us{0},g_sema_hist[6]{};
"""
''' +source[b:]
a=source.index("# Unused branches of the complete native lock body");b=source.index("table=r'''",a)
source=source[:a]+r'''
services='\n'.join(function(semaphore_source,'error_code sys_semaphore_'+name+'(') for name in ['create','destroy','wait','trywait','post','get_value'])
# Host-only fault mutations. The extracted baseline APIs remain unchanged.
services=services.replace('return sema.val.try_dec(0);','return fault==242?true:sema.val.try_dec(0);')
services=services.replace('sema.val.compare_and_swap_test(val, val - 1)','(fault==243 || sema.val.compare_and_swap_test(val, val - 1))')
services=services.replace('return not_an_error(CELL_EBUSY);','return fault==244?u32(CELL_OK):u32(not_an_error(CELL_EBUSY));')
services=services.replace('sema.val.compare_and_swap_test(val, val + count)','sema.val.compare_and_swap_test(val, fault==245?val:val + count)')
services=services.replace('return std::max<s32>(0, sema.val);','return std::max<s32>(0, sema.val)+(fault==246?1:0);')
# Only get-value has this variable; NULL must return an error before writing.
services=services.replace('if (!count)\n\t{\n\t\treturn CELL_EFAULT;', 'if (!count)\n\t{\n\t\treturn fault==247?u32(CELL_OK):u32(CELL_EFAULT);')
services=services.replace('if (max_val <= 0 || initial_val > max_val || initial_val < 0)','if (fault!=248 && (max_val <= 0 || initial_val > max_val || initial_val < 0))')
services=services.replace('sem->dbg_post_count++;','if(fault!=252){sem->dbg_post_count++;}')
services=services.replace('*count = sema.ret;','if(fault!=253){*count = sema.ret;}')
''' +source[b:]
a=source.index("table=r'''");b=source.index("table+=function(lv2,",a)
source=source[:a]+r'''table=r"""
const auto g_ppu_syscall_table=[]{std::array<std::pair<ppu_intrp_func_t,std::string_view>,1024>table{};
 table[90]={BIND_FUNC(sys_semaphore_create),"sys_semaphore_create"};table[91]={BIND_FUNC(sys_semaphore_destroy),"sys_semaphore_destroy"};
 table[92]={BIND_FUNC(sys_semaphore_wait),"sys_semaphore_wait"};table[93]={BIND_FUNC(sys_semaphore_trywait),"sys_semaphore_trywait"};
 table[94]={BIND_FUNC(sys_semaphore_post),"sys_semaphore_post"};table[114]={BIND_FUNC(sys_semaphore_get_value),"sys_semaphore_get_value"};return table;}();
const char*ppu_syscall_code(u64 code){return g_ppu_syscall_table[code].second.data();}
"""
''' +source[b:]
replace('assert(lock_timeout_observations==18);assert(syscall_usage.stat[100]==6 && syscall_usage.stat[101]==15 && syscall_usage.stat[102]==18 && syscall_usage.stat[103]==15 && syscall_usage.stat[104]==18);', 'assert(semaphore_timeout_observations==9);assert(syscall_usage.stat[90]==9 && syscall_usage.stat[91]==6 && syscall_usage.stat[92]==9 && syscall_usage.stat[93]==12 && syscall_usage.stat[94]==18 && syscall_usage.stat[114]==18);')
replace('lock_timeout_observations=0;','semaphore_timeout_observations=0;')
replace('std::make_shared<lv2_mutex>(1,0x20,0x2000,0,0)','std::make_shared<lv2_sema>(1,0,0,3,2)')
replace('priorID=0x8500ff01','priorID=0x9600ff01')
source=re.sub(r'const std::vector<int> faults\{[0-9,]+\};', 'const std::vector<int> faults{2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,26,27,36,37,38,39,40,41,60,173,174,175,176,177,179,180,22,212,213,214,216,224,242,243,244,245,246,247,248,250,252,253};',source)
a=source.index(' std::puts("PASS: P76/');b=source.index("''' +checks[b:]",a)
source=source[:a]+''' std::puts("PASS: P76/extracted six native semaphore APIs/create4args/wait full64/native signed errors/SC/binder/dispatcher/bounded/TLS;8runs/16workers/1728slices/72SC each/9wait ABI observations/864instructions/110pubs plus fresh registry recovery;3permit lifecycles/all counts/max/empty queues/post metadata/native output and error canaries/full contexts/memory/TLS36/36/ID cleanup;applicable foundational/history/LD22/ID212/213/214/216/registry218..219/ABI224 and semaphore fault242..248/250/252..253 detected;CPU/VM/ID allocator/atomic storage/clock/profiler/notify/registry remain host models;blocking branches reject entry;native iOS pending.");''' +source[b:]
exec(compile(source,str(Path(__file__).resolve()),'exec'))

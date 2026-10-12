"""P69 plus extracted native mutex methods/services/binder/SC/dispatcher/CPU/TLS.
Usage: python test_p69_pair.py PPUThread.cpp CoreBridge.cpp Modules/sys_ppu_thread_.cpp
CPU/VM/ID storage/atomic control/notification/registry are explicit host models.
Four native mutex service bodies and try_lock/try_unlock execute on those models.
Host-only mutations check rejected requests and object-state errors.
"""
from pathlib import Path
import subprocess,sys,tempfile
if len(sys.argv)!=4:raise SystemExit(__doc__)
old=Path(__file__).with_name('test_p66_pair.py').read_text()
exec(compile(old[:old.index('\nproduction=function(core,')],str(Path(__file__).with_name('test_p66_pair.py')),'exec'))
shims=shims.replace('queue_publications==38','queue_publications==92').replace('size==272','size==40')
shims=shims.replace('constexpr u32 CELL_EBUSY=0x8001000a;','')
shims=shims.replace('void instruction(ppu_thread&c,','void executeGuestSC(ppu_thread&,ppu_opcode_t,be_t<u32>*,ppu_intrp_func*);\nvoid instruction(ppu_thread&c,')
shims=shims.replace('switch(type){','switch(type){case 17:c.cia=pc;executeGuestSC(c,op,reinterpret_cast<be_t<u32>*>(vm::base(pc)),nullptr);break;')
shims=shims.replace('u64 gpr[32]{},ctr=0,lr=0;','u32 res_notify=0;u64 res_notify_time=0,exec_bytes=0;u64 gpr[32]{},ctr=0,lr=0;')
shims=shims.replace('bool check_state(){return test_stopped();}', 'bool check_state(){state-=u32(cpu_flag::wait);return test_stopped();}')
shims=shims.replace('T&operator*()const{return *reinterpret_cast<T*>(base(address));}T*operator->()const{return &**this;}',
 'ptr(u32 a):address(a){}explicit operator bool()const{return address!=0;}auto&operator*()const{if constexpr(std::is_integral_v<T>)return *reinterpret_cast<be_t<T>*>(base(address));else return *reinterpret_cast<T*>(base(address));}auto*operator->()const{return &**this;}')
shims=shims.replace('struct Fxo{','struct ppu_syscall_usage{std::array<std::atomic<u64>,1024>stat{};};ppu_syscall_usage syscall_usage;\nstruct Fxo{')
shims=shims.replace('template<class T>T&get(){return interpreter;}','template<class T>auto&get(){if constexpr(std::is_same_v<T,ppu_interpreter_rt>)return interpreter;else return syscall_usage;}')
shims=shims.replace('namespace ppu_instructions{\n u32 B(', 'namespace ppu_instructions{\n u32 SC(u32 lev){return 0x44000002|(lev<<5);}\n u32 B(')
assert 'u32 SC(u32 lev)' in shims
mutex_header=(native/'lv2/sys_mutex.h').read_text();mutex_source=(native/'lv2/sys_mutex.cpp').read_text();lv2=(native/'lv2/lv2.cpp').read_text()
for code,name in [(100,'create'),(101,'destroy'),(103,'trylock'),(104,'unlock')]:
 assert f'BIND_SYSC(sys_mutex_{name})' in lv2
 assert f'//{code} (0x{code:03x})' in lv2
extras=r'''
#include <map>
#include <functional>
#include <string_view>
enum CellError:u32{CELL_ESRCH=0x80010005,CELL_EDEADLK=0x80010008,CELL_EPERM=0x80010009,CELL_EFAULT=0x8001000d,
 CELL_EINVAL=0x80010002,CELL_EKRESOURCE=0x80010011,CELL_EBUSY=0x8001000a};
constexpr u32 SYS_SYNC_FIFO=1,SYS_SYNC_PRIORITY=2,SYS_SYNC_PRIORITY_INHERIT=3,SYS_SYNC_RECURSIVE=0x10,
 SYS_SYNC_NOT_RECURSIVE=0x20,SYS_SYNC_NOT_PROCESS_SHARED=0x200,SYS_SYNC_NOT_ADAPTIVE=0x2000;
using shared_mutex=std::mutex;template<class T>using shared_ptr=std::shared_ptr<T>;using std::make_shared;
struct {template<class...T>void trace(const char*,T...){}template<class...T>void error(const char*,T...){}
 template<class...T>void warning(const char*,T...){}template<class...T>void todo(const char*,T...){} }sys_mutex,ppu_log;
namespace fmt{template<class...T>[[noreturn]]void throw_exception(const char*,T...){throw std::runtime_error("native invalid SC");}}
template<class T>struct atomic_storage{static T load(const T&v){return v;}};
namespace vm{template<class T>auto*_ptr(u32 addr){return &*ptr<T>{addr};}const void*reservation_notifier_notify(u32,u64,bool){return nullptr;}}
struct sys_mutex_attribute_t{be_t<u32>protocol,recursive,pshared,adaptive;be_t<u64>ipc_key;be_t<s32>flags;be_t<u32>pad;union{u64 name_u64;char name[8];};};
struct lv2_obj{
 atomic_t<u32>exists{0};
 template<class T>static u64 get_key(const T&){return 0;}
 template<class T,class F>static error_code create(u32,u64,s32,F);
 template<class T>static void on_id_destroy(T&obj,u64 key){assert(!key);obj.exists--;}
 struct notify_all_t{static void enqueue_on_top(const void*){}static void cleanup(){}};
 template<class T>void awake(T*){assert(false);}
};
struct lv2_mutex:lv2_obj{
 static constexpr u32 id_base=0x85000000;
 const u32 protocol,recursive,adaptive;const u64 key,name;
 u32 cond_count=0;shared_mutex mutex;atomic_t<u32>lock_count{0};
 struct control_data_t{u32 owner=0,reserved=0;ppu_thread*sq=nullptr;};
 struct Control{control_data_t value{};control_data_t load()const{return value;}control_data_t&raw(){return value;}
  bool compare_and_swap_test(const control_data_t&a,control_data_t b){
   if(a.owner!=value.owner||a.sq!=value.sq)return false;
   if(fault==207 && b.owner){b.owner++;}value=b;return true;
  }
 }control;
 lv2_mutex(u32 p,u32 r,u32 a,u64 k,u64 n):protocol(fault==215?99:p),recursive(r),adaptive(a),key(k),name(n){}
 template<class T>T*reown(){assert(false);return nullptr;}
'''
lock=function(mutex_header,'CellError try_lock(T& cpu)')
unlock=function(mutex_header,'CellError try_unlock(T& cpu)')
lock=lock.replace('return CELL_EBUSY;','return fault==208?CellError{}:CELL_EBUSY;').replace('return CELL_EDEADLK;','return fault==209?CellError{}:CELL_EDEADLK;')
unlock=unlock.replace('return CELL_EPERM;','return fault==210?CellError{}:CELL_EPERM;').replace('auto it = control.load();','if(fault==217){lock_count=1;}auto it = control.load();')
extras+='template<class T>'+lock+'\ntemplate<class T>'+unlock+'\n};\n'
extras+=r'''
class idm{public:
 static inline std::recursive_mutex guard;static inline std::map<u32,shared_ptr<lv2_mutex>>objects;static inline u32 cookie=0;
 template<class T>static u32 last_id(){return fault==214?0xdeadbeef:id_manager::g_id;}
 template<class B,class T,class F>static u32 import(F make){
  std::lock_guard lock(guard);const u32 id=lv2_mutex::id_base+0x800+(++cookie&255);
  auto object=make();if(!object)return 0;object->exists=fault==216?2:1;objects[id]=object;id_manager::g_id=id;return id;
 }
 template<class T>struct Pair{shared_ptr<T>ptr;CellError ret{};explicit operator bool()const{return bool(ptr);}T*operator->()const{return ptr.get();}};
 template<class B,class T,class F>static auto get(u32 id,F f){
  std::lock_guard lock(guard);auto it=objects.find(id);
  if constexpr(std::is_void_v<std::invoke_result_t<F,T&>>){if(it==objects.end())return shared_ptr<T>{};f(*it->second);return it->second;}
  else{if(it==objects.end())return Pair<T>{};return Pair<T>{it->second,f(*it->second)};}
 }
 template<class B,class T,class F>static auto check(u32 id,F f){return get<B,T>(id,std::move(f));}
 template<class B,class T,class F>static Pair<T> withdraw(u32 id,F f){
  std::lock_guard lock(guard);auto it=objects.find(id);if(it==objects.end())return {};
  auto ptr=it->second;const CellError error=f(*ptr);
  if(!error && !(fault==212 && ptr->exists==0)){objects.erase(it);}return {ptr,error};
 }
 template<class B,class T,class F>static u32 select(F f){
  std::lock_guard lock(guard);for(auto&entry:objects)f(entry.first,*entry.second);return objects.size();
 }
};
template<class T,class F>error_code lv2_obj::create(u32 shared,u64 key,s32,F make){
 assert(shared==SYS_SYNC_NOT_PROCESS_SHARED && !key);
 return idm::import<lv2_obj,T>(make)?CELL_OK:s32(0x80010001);
}
'''
# General vm::ptr<> ABI conversion is a host shim; native bind templates retained.
shims=shims.replace('template<class T>u64 ppu_gpr_cast(const T&value){return u64(value);}', 'template<class T>u64 ppu_gpr_cast(const T&value){if constexpr(std::is_same_v<T,error_code>){if(fault==213)return u32(s32(value));}return u64(value);}')
services='\n'.join(function(mutex_source,sig) for sig in ['error_code sys_mutex_create(', 'error_code sys_mutex_destroy(', 'error_code sys_mutex_trylock(', 'error_code sys_mutex_unlock('])
services=services.replace('return CELL_EBUSY;', 'return fault==211?CellError{}:CELL_EBUSY;',1)
table=r'''
const auto g_ppu_syscall_table=[]{
 std::array<std::pair<ppu_intrp_func_t,std::string_view>,1024>table{};
 table[100]={BIND_FUNC(sys_mutex_create),"sys_mutex_create"};table[101]={BIND_FUNC(sys_mutex_destroy),"sys_mutex_destroy"};
 table[103]={BIND_FUNC(sys_mutex_trylock),"sys_mutex_trylock"};table[104]={BIND_FUNC(sys_mutex_unlock),"sys_mutex_unlock"};return table;
}();
const char*ppu_syscall_code(u64 code){return g_ppu_syscall_table[code].second.data();}
'''
table+=function(lv2,'extern void ppu_execute_syscall(')+'\n'+function(lv2,'extern ppu_intrp_func_t ppu_get_syscall(')+'\n'+function(lv2,'std::string ppu_get_syscall_name(u64 code)\n')+'\n'
# ppu_get_syscall_name's unused fallback needs a format shim.
extras+='namespace fmt{template<class...T>std::string format(const char*,T...){return "fallback";}}\n'
interpreter=(native/'PPUInterpreter.cpp').read_text()
sc=function(interpreter,'auto SC()');a=sc.index('return +[]');b=sc.index('\n\t\t};',a)+len('\n\t\t};')
sc_lambda=sc[a:b].removeprefix('return ').removesuffix(';')
table+='void executeGuestSC(ppu_thread& ppu,ppu_opcode_t op,be_t<u32>*word,ppu_intrp_func*next){const ppu_intrp_func_t fn='+sc_lambda+';fn(ppu,op,word,next);}\n'
production=function(core,'struct ios_ppu_dispatch_probe')+';\nstatic thread_local ios_ppu_dispatch_probe* s_ios_ppu_dispatch_probe=nullptr;\n'
production+=function(core,'void ppu_thread::exec_task(')+'\n'+function(core,'extern "C" int armsx3_ios_ppu_exec_bounded(')+'\n'
production+='void assert_dispatch_clear(){assert(!s_ios_ppu_dispatch_probe);assert(cpu_thread::current);assert(id_manager::g_id==0);}\n'
tls=Path(sys.argv[3]).read_text()
production+=tls[tls.index('static u32 s_tls_addr'):tls.index('static u32 ppu_alloc_tls()')]+'\n'
for sig in ['static u32 ppu_alloc_tls(', 'static void ppu_free_tls(', 'static void ppu_initialize_tls_memory(', 'extern "C" int armsx3_ios_ppu_probe_tls_and_call(', 'static bool ios_probe_tls_pair_owner(', 'extern "C" u32 armsx3_ios_ppu_probe_alloc_peer_tls(', 'extern "C" int armsx3_ios_ppu_probe_free_peer_tls(']:
 production+=function(tls,sig)+'\n'
phase=function(bridge,'extern "C" __attribute__((visibility("default"))) int armsx3_core_test_lv2_mutex_ownership(')
checks=template[template.index("checks=r'''")+len("checks=r'''"):template.index("\n'''\nwith tempfile.TemporaryDirectory")]
checks=checks.replace('armsx3_core_test_guest_spinlock_handoff','armsx3_core_test_lv2_mutex_ownership')
checks=checks.replace('assert(id_manager::g_id==0);','assert(id_manager::g_id==0 && idm::objects.empty());')
checks=checks.replace('callback_calls==50','callback_calls==92').replace('queue_publications==50','queue_publications==92')
a=checks.index('  assert(lock_compares==18');b=checks.index('  for(const char* values:',a)
checks=checks[:a]+'''  assert(executed==600 && tls_stores==60 && output_stores==120 && calls==0 && stack_stores==0);
  assert(syscall_usage.stat[100]==6 && syscall_usage.stat[101]==12 && syscall_usage.stat[103]==30 && syscall_usage.stat[104]==12);
''' +checks[b:]
checks=checks.replace('queue_publications=0;executed=0;','queue_publications=0;for(auto&v:syscall_usage.stat)v=0;executed=0;')
checks=checks.replace('"counter=2 checksum=3 TLS=1/1 results=1/1", "counter=4 checksum=10 TLS=2/2 results=1/1", "counter=6 checksum=21 TLS=3/3 results=1/1"','"TLS=10/10 results=6/6", "TLS=20/20 results=6/6", "TLS=30/30 results=6/6"')
a=checks.index(' const std::vector<int> faults');b=checks.index('\n for(int value:faults)',a)
checks=checks[:a]+''' const std::vector<int> faults{2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,26,27,36,37,38,39,40,41,60,173,174,175,176,177,179,180,207,208,209,210,211,212,213,214,215,216,217};''' +checks[b:]
a=checks.index(' std::puts(');b=checks.index('\n}',a)
checks=checks[:a]+''' const u32 priorID=0x8500ff01;
 auto prior=std::make_shared<lv2_mutex>(1,0x20,0x2000,0,0);prior->exists=1;idm::objects[priorID]=prior;
 const auto before=cpu_thread::g_threads_created.load();
 assert(armsx3_core_test_lv2_mutex_ownership()==-1);
 assert(idm::objects.size()==1 && idm::objects[priorID]==prior && prior->exists==1 && cpu_thread::g_threads_created==before);
 idm::objects.clear();restored();
 std::puts("PASS: P69/extracted native mutex create/destroy/trylock/unlock + try_lock/try_unlock + SC handler/syscall dispatcher/binder/bounded/TLS;8runs/16workers/1440slices/60SC each/600instructions/92pubs,3mutexlifecycles/all ownership and signed errors/full contexts/memory/TLS30/30/ID cleanup; foundational and207..217 fault models/mutations/all allocation/setup/TLS guards/nonempty mutex namespace guard detected;CPU/VM/ID allocator/atomic control/notify/registry remain host models;native iOS execution pending.");''' +checks[b:]
with tempfile.TemporaryDirectory(prefix='p69-pair-') as temp:
 source=Path(temp)/'test.cpp';binary=Path(temp)/'test';source.write_text(shims+extras+binding+services+table+production+phase+checks)
 subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(binary)],check=True)
 subprocess.run([str(binary)],check=True)

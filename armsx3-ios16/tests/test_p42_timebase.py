"""Compile production scheduler/service bodies and the exact P42 callback.

Locks/atomics/VM/SC transport/guest instruction execution use host shims.
Full awake/awake_unlocked/schedule_all/fast_call, priorities, service handlers,
queue bookkeeping and the diagnostic callback/wrappers are unchanged bodies.
"""
from pathlib import Path
import subprocess
import tempfile
import sys

r = Path(__file__).resolve().parent


def function(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


# Optional args: staged rpcs3 root, CoreBridge.cpp. Sources include all iOS patches.
core = Path(sys.argv[1]) if len(sys.argv)>1 else r
bridge_path = Path(sys.argv[2]) if len(sys.argv)>2 else r/'CoreBridge.cpp'
def read_core(path, scratch):
    return (core/path if len(sys.argv)>1 else r/scratch).read_text()
lv2 = read_core('Emu/Cell/lv2/lv2.cpp','staged/rpcs3/Emu/Cell/lv2/lv2.cpp')
sync = read_core('Emu/Cell/lv2/sys_sync.h','staged/rpcs3/Emu/Cell/lv2/sys_sync.h')
ppu = read_core('Emu/Cell/PPUThread.cpp','PPUThread.cpp')
service = read_core('Emu/Cell/lv2/sys_ppu_thread.cpp','sys_ppu_thread.cpp')
time = read_core('Emu/Cell/lv2/sys_time.cpp','sys_time.cpp')
interpreter = read_core('Emu/Cell/PPUInterpreter.cpp','PPUInterpreter.cpp')
bridge = bridge_path.read_text().split('int armsx3_core_test_guest_timebase()', 1)[1]
callback = function(bridge, 'const auto performSyscalls =') + ';'
call_tls = function(bridge, 'const auto callWithTLS =') + ';'
program = function(bridge, 'struct Program') + ';'
unqueue = function(sync, 'template <bool ModifyNode = true, typename T>')
set_priority = function(sync, 'static void set_priority(')
shims = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <ctime>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <functional>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>
using u8=uint8_t; using u32=uint32_t; using u64=uint64_t;
using s32=int32_t; using s64=int64_t; using usz=size_t;
constexpr u32 umax=UINT32_MAX; constexpr s32 smin=INT32_MIN,smax=INT32_MAX;
template<class T> using shared_ptr=std::shared_ptr<T>;
template<class T> T swap_be(T v) {if constexpr(sizeof(T)==4) return T(__builtin_bswap32(u32(v))); else return T(__builtin_bswap64(u64(v)));}
template<class T> struct be_t {T value{}; operator T() const {return swap_be(value);} be_t& operator=(T x) {value=swap_be(x);return *this;}};
enum class cpu_flag : unsigned {stop=1,again=2,ret=4,suspend=8,wait=16,signal=32,yield=64,preempt=128,notify=256};
unsigned operator+(cpu_flag a,cpu_flag b) {return unsigned(a)|unsigned(b);}
unsigned operator+(unsigned a,cpu_flag b) {return a|unsigned(b);}
unsigned operator+(cpu_flag a) {return unsigned(a);}
bool operator!=(unsigned a,cpu_flag b) {return a!=unsigned(b);}
unsigned notifications=0;
struct flags {
 unsigned bits=0;
 explicit operator bool() const {return bits;}
 bool all_of(cpu_flag f) const {return (bits&unsigned(f))==unsigned(f);}
 bool none_of(cpu_flag f) const {return !(bits&unsigned(f));}
 bool none_of(unsigned f) const {return !(bits&f);}
 unsigned operator&(cpu_flag f) const {return bits&unsigned(f);}
 unsigned operator&(unsigned f) const {return bits&f;}
 flags operator-(cpu_flag f) const {return {bits&~unsigned(f)};}
 void operator+=(cpu_flag f) {bits|=unsigned(f);}
 void operator-=(cpu_flag f) {bits&=~unsigned(f);}
 void operator-=(unsigned f) {bits&=~f;}
 bool test_and_set(cpu_flag f) {bool old=bits&unsigned(f);bits|=unsigned(f);return old;}
 void notify_one() {notifications++;}
 template<class F> flags fetch_op(F f) {auto old=*this;f(*this);return old;}
};
bool operator-(cpu_flag f,const flags& s) {return !(s.bits&unsigned(f));}
template<class> using bs_t=unsigned;
#define AOFN(...) [&](flags& x) {__VA_ARGS__;}
#define AUDIT(x) assert(x)
inline bool ensure(bool v) {if(!v) throw std::runtime_error("ensure");return v;}
template<class T> T& ensure(T& v) {if(!static_cast<bool>(v)) throw std::runtime_error("ensure");return v;}
template<class T> struct atomic_t {
 T value{};
 atomic_t()=default; atomic_t(T v):value(v) {}
 operator T() const {return value;} T load() const {return value;}
 void release(T v) {value=v;} atomic_t& operator=(T v) {value=v;return *this;}
 T operator++() {return ++value;} T operator++(int) {return value++;}
 T operator--(int) {return value--;}
 template<class F> auto atomic_op(F f) {return f(value);}
};
template<class T> struct atomic_storage {static T load(T v) {return v;} static void release(T& a,T v) {a=v;}};
enum class thread_class {ppu,spu};
enum class ppu_decoder_type {_static,llvm};
enum class sleep_timers_accuracy_level {_host,_all_timers};
enum class ppu_join_status {joinable,detached,zombie,exited};
enum ppu_thread_status {PPU_THREAD_STATUS_IDLE,PPU_THREAD_STATUS_RUNNABLE,PPU_THREAD_STATUS_ONPROC,
 PPU_THREAD_STATUS_SLEEP,PPU_THREAD_STATUS_STOP,PPU_THREAD_STATUS_ZOMBIE,PPU_THREAD_STATUS_DELETED};
struct reader_lock {explicit reader_lock(std::mutex&) {}};
namespace id_manager {std::mutex g_mutex;}
struct {bool stopped=true,ready=false; bool IsStopped() const {return stopped;} bool IsReady() const {return ready;}} Emu;
struct {struct {unsigned ppu_threads=2; ppu_decoder_type ppu_decoder=ppu_decoder_type::_static;
 sleep_timers_accuracy_level sleep_timers_accuracy=sleep_timers_accuracy_level::_host; u32 clocks_scale=100;} core;struct {s64 console_time_offset=0;} sys;} g_cfg;
struct cpu_thread {
 u32 id=0x1000000; flags state;
 static inline cpu_thread* current=nullptr;
 static cpu_thread* get_current() {return current;}
 template<class T> T* try_get() {return static_cast<T*>(this);}
 template<class T> static T* get_current() {return static_cast<T*>(current);}
 thread_class get_class() const {return thread_class::ppu;}
 bool is_paused() const {return state.bits&unsigned(cpu_flag::suspend);}
};
bool is_paused(flags state) {return state.bits&unsigned(cpu_flag::stop);}
void* get_current_cpu_thread() {return cpu_thread::current;}
struct name_wrapper {
 shared_ptr<std::string> value=std::make_shared<std::string>("worker");
 bool is_equal(const shared_ptr<std::string>& p) const {return p==value;}
 template<class F> void peek_op(F f) const {f(value);}
};
struct ppu_thread : cpu_thread {
 union ppu_prio_t {u64 all; struct {s64 prio:13; s64 order:50; u64 preserve_bit:1;};};
 atomic_t<ppu_prio_t> prio;
 u32 stack_addr=0x30000,stack_size=0x8000,cia=0x10900;
 u64 start_time=951053532566ull,hw_sleep_time=0,gpr[32]{},lr=0x10904,syscall_args[8]{};
 u32 raddr=0; u64 ctr=0; unsigned guest_steps=0;
 u32 res_notify=0,res_notify_postpone_streak=0; u64 res_notify_time=0;
 bool ack_suspend=false; unsigned cancel_sleep=0;
 bool interrupt_thread_executing=false,loaded_from_savestate=false,stop_flag_removal_protection=false;
 ppu_join_status joiner=ppu_join_status::joinable;
 ppu_thread* next_ppu=nullptr;
 struct {u32 addr=0x10000,rtoc=0x20020;} entry_func;
 const char* current_function="saved function";
 name_wrapper ppu_tname;
 struct event {u32 cia=0; const char* func_name=nullptr; u64 error=0;};
 struct {u64 index=0; std::array<event,32> data{};} syscall_history;
 std::function<void(ppu_thread&)> exec;
 void dump_all(std::string&) {}
 void exec_task() {exec(*this);}
 void fast_call(u32,u64,bool);
 bool is_stopped() const {return state.bits&unsigned(cpu_flag::stop);}
 void check_state() {state-=cpu_flag::wait;}
};
template<class T> struct named_thread : T {};
namespace idm {template<class T,class F> bool check(u32,F) {return false;}}
struct {bool debug_or_root() const {return false;}} g_ps3_process_info;
struct logger {template<class... T> void trace(const char*,T...) {}
 template<class... T> void error(const char*,T...) {} template<class... T> void notice(const char*,T...) {}} ppu_log,sys_ppu_thread,sys_time;
using error_code=s32;
constexpr s32 CELL_CANCEL=1,CELL_OK=0,CELL_EINVAL=s32(0x80010002),CELL_EFAULT=s32(0x8001000d),CELL_ESRCH=s32(0x80010005),CELL_ENOSYS=s32(0x80010003);
namespace vm {
 std::vector<u8> memory(0xa0000);
 void* base(u32 addr) {return memory.data()+addr;}
 void* get_super_ptr(u32 addr) {return base(addr);}
 template<class T> be_t<T>* _ptr(u32 addr) {return reinterpret_cast<be_t<T>*>(base(addr));}
 template<class T> struct ptr {u32 addr=0; explicit operator bool() const {return addr!=0;} be_t<T>& operator*() const {return *_ptr<T>(addr);}};
 u32 read32(u32 a) {return *_ptr<u32>(a);} u64 read64(u32 a) {return *_ptr<u64>(a);}
 void write32(u32 a,u32 v) {*_ptr<u32>(a)=v;} void write64(u32 a,u64 v) {*_ptr<u64>(a)=v;}
 void temporary_unlock() {}
 const void* reservation_notifier_notify(u32,u64,bool=false) {return nullptr;}
}
struct ppu_opcode_t {u32 value,rd,spr; ppu_opcode_t(u32 v):value(v),rd((v>>21)&31),spr((v>>11)&1023) {}};
using ppu_intrp_func_t=void(*)(ppu_thread&,ppu_opcode_t,be_t<u32>*,void*);
void run_sc(ppu_thread&,ppu_opcode_t,be_t<u32>*,void*);
namespace ppu_instructions {u32 SC(unsigned) {return 0x44000002;}}
struct ppu_interpreter_rt {ppu_intrp_func_t decode(u32) {return run_sc;}};
struct ppu_function_manager {u32 func_addr(unsigned,bool) {return 0x4000c;} bool is_func(u32) {return false;}};
struct fxo {ppu_interpreter_rt interpreter; ppu_function_manager manager;
 template<class T> T& get() {if constexpr(std::is_same_v<T,ppu_interpreter_rt>) return interpreter; else return manager;}} fxo_instance;
auto* g_fxo=&fxo_instance;
namespace fmt {template<class... T> [[noreturn]] void throw_exception(const char*,T...) {throw std::runtime_error("invalid timebase selector");} template<class... T> std::string format(const char*,T...) {return {};}}
const char* get_prx_name_by_cia(u32) {return nullptr;}
std::function<std::string()> g_tls_log_prefix=[]{return "prefix";};
u64 get_guest_system_time() {return 951053533599ull;}
std::vector<std::string> logs;
void ARMSX3StartupLog(const char* text) {logs.emplace_back(text);}
std::deque<std::pair<u64,cpu_thread*>> g_waiting;
std::deque<cpu_thread*> g_to_sleep;
atomic_t<bool> g_scheduler_ready=false;
atomic_t<u64> s_yield_frequency=0;
atomic_t<u64> s_max_allowed_yield_tsc=0;
u64 s_last_yield_tsc=0;
atomic_t<u32> g_lv2_preempts_taken=0;
namespace utils {u64 test_freq=0,test_tsc=1;u64 get_tsc_freq() {return test_freq;}u64 get_tsc() {return test_tsc;}}
namespace rsx {void set_rsx_yield_flag() {throw std::runtime_error("unexpected RSX call");}}
struct ppu_non_sleeping_count_t {usz onproc_count=0; bool has_running=false;};
struct lv2_obj {
 static inline ppu_thread* g_ppu=nullptr;
 static inline std::mutex g_mutex;
 static inline atomic_t<u32> g_pending=0;
 static inline atomic_t<u64> g_priority_order_tag=35;
 static inline const void* g_to_notify[8]{};
 static inline bool g_postpone_notify_barrier=false;
 static inline std::vector<cpu_thread*> g_to_awake;
 static constexpr s32 yield_cmd=smin,enqueue_cmd=smin+1;
 static bool yield(cpu_thread&);
 static bool awake(cpu_thread*,s32=enqueue_cmd);
 static bool awake_unlocked(cpu_thread*,s32=enqueue_cmd);
 static void schedule_all(u64=0);
 static ppu_non_sleeping_count_t count_non_sleeping_threads();
 static std::pair<ppu_thread_status,u32> ppu_state(ppu_thread*,bool=true,bool=true);
 static ppu_thread* get_running_ppu(u32);
 static void notify_all() {assert(std::all_of(std::begin(g_to_notify),std::end(g_to_notify),[](const void* p){return !p;})); g_postpone_notify_barrier=false;}
 static void sleep(ppu_thread&) {}
 struct notify_all_t {~notify_all_t() {lv2_obj::notify_all();}};
 static int ios_probe_scheduler_time_and_call(ppu_thread*,ppu_thread*,int(*)(ppu_thread*,void*),void*);
 static int ios_probe_scheduler_queue_and_call(ppu_thread*,int(*)(ppu_thread*,void*),void*);
 static int ios_probe_priority_change_and_call(ppu_thread*,int(*)(ppu_thread*,void*),void*);
'''
shims += unqueue + '\n' + set_priority + '\n};\n'
production = '\n'.join(function(lv2, sig) for sig in [
    'bool lv2_obj::yield(', 'bool lv2_obj::awake(', 'bool lv2_obj::awake_unlocked(',
    'void lv2_obj::schedule_all(', 'ppu_non_sleeping_count_t lv2_obj::count_non_sleeping_threads(',
    'std::pair<ppu_thread_status, u32> lv2_obj::ppu_state(', 'ppu_thread* lv2_obj::get_running_ppu(',
])
production += '\n' + function(ppu, 'void ppu_thread::fast_call(')
production += '\n' + '\n'.join(function(service, sig) for sig in [
    's32 sys_ppu_thread_yield(', 'error_code sys_ppu_thread_get_join_state(', 'error_code sys_ppu_thread_set_priority(',
    'error_code sys_ppu_thread_get_priority(',
])
production += '\nstatic constexpr u64 g_timebase_freq=80000000ull;\nstatic timespec start_time{};\n' + function(time, 'error_code sys_time_get_current_time(') + '\n' + function(time, 'u64 sys_time_get_timebase_frequency(')
production += '\nu64 g_timebase_offs=0;\n' + function(time,'u64 get_timebased_time(')
# Extract the exact interpreter operation lambda, omitting template dispatch glue.
mftb_body = function(function(interpreter,'auto MFTB()'),'static const auto exec =')
production += '\nvoid execute_MFTB(ppu_thread& ppu,ppu_opcode_t op) {\n'+mftb_body+';\nexec(ppu,op);\n}\n'
probe_start = lv2.index('struct ios_ppu_syscall_probe')
probe_end = lv2.index('extern "C" int armsx3_ios_ppu_probe_syscalls_and_call', probe_start)
production += '\n' + lv2[probe_start:probe_end]
production += '\n' + '\n'.join(function(lv2, sig) for sig in [
    'int lv2_obj::ios_probe_scheduler_time_and_call(',
    'int lv2_obj::ios_probe_scheduler_queue_and_call(',
    'int lv2_obj::ios_probe_priority_change_and_call(',
    'extern "C" int armsx3_ios_ppu_probe_scheduler_time_and_call(',
])
transport = r'''
void run_sc(ppu_thread& worker,ppu_opcode_t,be_t<u32>* pc,void*) {
 const u32 cia=u32(reinterpret_cast<u8*>(pc)-vm::memory.data());
 const u32 code=u32(worker.gpr[11]);
 assert(s_ios_ppu_syscall_probe && code<1024);
 s_ios_ppu_syscall_probe->counts[code]++;
 s32 error=0; const char* name=nullptr;
 if(code==145) {name="sys_time_get_current_time";error=sys_time_get_current_time({u32(worker.gpr[3])},{u32(worker.gpr[4])});}
 else if(code==147) {name="sys_time_get_timebase_frequency";error=s32(sys_time_get_timebase_frequency());}
 else if(code==43) {name="sys_ppu_thread_yield";error=sys_ppu_thread_yield(worker);}
 else if(code==46) {name="sys_ppu_thread_get_join_state";error=sys_ppu_thread_get_join_state(worker,{u32(worker.gpr[3])});}
 else if(code==47) {name="sys_ppu_thread_set_priority";error=sys_ppu_thread_set_priority(worker,u32(worker.gpr[3]),s32(worker.gpr[4]));}
 else if(code==48) {name="sys_ppu_thread_get_priority";error=sys_ppu_thread_get_priority(worker,u32(worker.gpr[3]),{u32(worker.gpr[4])});}
 else {assert(code==6); worker.gpr[3]=u32(CELL_ENOSYS);worker.cia=cia+4;return;}
 worker.gpr[3]=u64(s64(error));
 worker.syscall_history.data[worker.syscall_history.index++%32]={cia,name,worker.gpr[3]};
 worker.cia=cia+4;
 worker.check_state();
}

unsigned fault_mode=0;
int armsx3_ios_ppu_call_bounded(ppu_thread* worker,u32 begin,u32 end,u32 toc,u32 ret,u32 budget) {
 assert(begin==0x10000 && end==0x100c4 && toc==0x20020 && ret==0x4000c && budget==64);
 worker->guest_steps=0;
 worker->exec=[begin,end,ret,budget](ppu_thread& c) {
  while(c.cia!=ret) {
   assert(c.cia>=begin && c.cia<end && c.guest_steps<budget);
   const u32 pc=c.cia,op=vm::read32(pc),type=op>>26,rt=(op>>21)&31,ra=(op>>16)&31;
   const s32 imm=int16_t(op&0xffff);
   const u64 base=ra?c.gpr[ra]:0;
   c.guest_steps++;c.cia=pc+4;
   switch(type) {
    case 14: c.gpr[rt]=base+imm;break;
    case 24: c.gpr[ra]=c.gpr[rt]|(op&0xffff);break;
    case 32: c.gpr[rt]=vm::read32(u32(base+imm));break;
    case 34: c.gpr[rt]=vm::memory.at(base+imm);break;
    case 36: vm::write32(u32(base+imm),u32(c.gpr[rt]));break;
    case 58: c.gpr[rt]=vm::read64(u32(base+int16_t(op&0xfffc)));break;
    case 62: {
     const u64 addr=base+int16_t(op&0xfffc);
     vm::write64(u32(addr),c.gpr[rt]);if(op&1)c.gpr[ra]=addr;break;
    }
    case 31: {
     const u32 xo=(op>>1)&1023,spr=((op>>16)&31)|((op>>6)&0x3e0);
     if(xo==371) {
      execute_MFTB(c,{op});
      if(fault_mode==1 && pc==begin+160)c.gpr[rt]|=1ull<<32;
      if(fault_mode==2 && pc==begin+152)c.gpr[rt]=0;
      if(fault_mode==3 && pc==begin+168)c.gpr[rt]=0;
      if(fault_mode==4 && pc==begin+168)c.gpr[rt]=UINT64_MAX;
      if(fault_mode==5 && pc==begin+160)c.gpr[rt]=get_timebased_time();
      break;
     }
     assert(spr==8 || spr==9);
     if(xo==339)c.gpr[rt]=spr==8?c.lr:c.ctr;
     else {assert(xo==467);if(spr==8)c.lr=c.gpr[rt];else c.ctr=c.gpr[rt];}
     break;
    }
    case 19: {
     const u32 xo=(op>>1)&1023;assert(xo==16 || xo==528);
     c.cia=u32(xo==16?c.lr:c.ctr);if(op&1)c.lr=pc+4;break;
    }
    case 17: assert(op==0x44000002);run_sc(c,{op},vm::_ptr<u32>(pc),nullptr);break;
    default: assert(false);
   }
  }
  c.guest_steps++;c.cia=ret+4;c.state+=cpu_flag::ret;
 };
 worker->fast_call(begin,toc,false);
 return int(worker->guest_steps);
}

'''
checks = program + '\n' + r'''
void populate(ppu_thread& worker,ppu_thread& peer,Program& program) {
 vm::memory.assign(0xa0000,0);logs.clear();notifications=0;
 worker=ppu_thread{};peer=ppu_thread{};
 worker.prio.value.all=0;worker.prio.value.prio=1100;
 peer.prio.value.all=0;peer.prio.value.prio=1100;
 peer.id++;peer.stack_addr=0x90000;peer.start_time=951053533599ull;
 peer.joiner=ppu_join_status::detached;
 program.~Program();new (&program) Program{};
 program.begin=0x10000;program.end=0x100c4;program.returnAddress=0x4000c;
 program.dataAddress=0x20000;program.argvAddress=0x37f40;program.id=worker.id;
 program.primaryPriority=1100;program.initialStack=0x37ed0;program.peer=&peer;
 worker.gpr[4]=program.argvAddress;worker.gpr[7]=worker.id;worker.gpr[13]=0x57060;
 worker.gpr[1]=0x37ed0;worker.gpr[2]=0x13579;
 vm::write32(0x20000,0x10060);vm::write32(0x20004,0x20000);vm::write32(0x200b0,0x20000);
 const unsigned char opcodes[] = {124,8,2,166,248,33,255,129,248,1,0,16,248,65,0,24,96,227,0,0,129,106,0,0,129,139,0,0,128,75,0,4,125,137,3,166,78,128,4,33,232,65,0,24,96,73,0,0,248,98,0,16,56,98,0,24,57,96,0,46,68,0,0,2,144,98,0,28,136,109,144,0,56,99,255,193,248,98,0,0,232,1,0,16,56,33,0,128,124,8,3,166,78,128,0,32,57,96,0,43,68,0,0,2,144,98,0,24,57,96,0,43,68,0,0,2,144,98,0,28,56,97,0,32,56,129,0,40,57,96,0,145,68,0,0,2,248,97,0,48,57,96,0,147,68,0,0,2,248,97,0,56,124,172,66,230,248,161,0,64,124,173,66,230,248,161,0,72,124,172,66,230,248,161,0,80,96,227,0,0,56,130,0,40,57,96,0,48,68,0,0,2,78,128,0,32};
 std::memcpy(vm::memory.data()+program.begin,opcodes,sizeof(opcodes));
 for(unsigned i=0;i<3;i++) std::memcpy(vm::memory.data()+0x50060+i*0x70,"iOSProbe",9);
 cpu_thread::current=&worker;
 g_tls_log_prefix=[]{return "prefix";};
}
void restored(const ppu_thread& worker,const ppu_thread& peer) {
 assert(!lv2_obj::g_ppu && !worker.next_ppu && !peer.next_ppu && !lv2_obj::g_pending && !g_scheduler_ready);
 assert(worker.prio.load().prio==1100 && peer.prio.load().prio==1100);
 assert(worker.prio.load().order==0 && peer.prio.load().order==0 && lv2_obj::g_priority_order_tag.load()==35);
 assert(worker.start_time==951053532566ull && peer.start_time==951053533599ull);
 assert(!s_ios_ppu_syscall_probe && !notifications);
}
int main() {
''' + call_tls + r'''
 ppu_thread worker,peer; Program program;
 for(bool joinable:{true,false}) {
  populate(worker,peer,program);program.joinable=joinable;
  worker.joiner=joinable?ppu_join_status::joinable:ppu_join_status::detached;
  const int result=callWithTLS(&worker,0x50000,&program);
  assert(result==50 && program.syscalls && program.tlsMemory && worker.gpr[3]==42);
  assert(worker.interrupt_thread_executing && !peer.interrupt_thread_executing);
  assert(worker.syscall_history.index==15 && peer.syscall_history.index==0);
  assert(worker.gpr[1]==program.initialStack && worker.gpr[2]==0x13579 && worker.gpr[4]==0x20028);
  std::vector<u8> expectedStack(0x10000,0);
  const u32 frame=program.initialStack-128;
  auto put=[&](u32 offset,u64 value){be_t<u64> word;word=value;std::memcpy(expectedStack.data()+frame-0x30000+offset,&word,8);};
  put(0,program.initialStack);put(16,program.returnAddress);put(24,0x20020);
  put(32,program.clockSeconds);put(40,program.clockNanoseconds);put(48,0);put(56,80000000);
  put(64,program.timebaseFirst);put(72,program.timebaseUpper);put(80,program.timebaseLast);
  assert(!std::memcmp(vm::base(0x30000),expectedStack.data(),expectedStack.size()));
  assert(std::all_of(vm::memory.begin()+0x90000,vm::memory.begin()+0xa0000,[](u8 b){return b==0;}));
  assert(lv2_obj::ppu_state(&worker,false,true).first==PPU_THREAD_STATUS_SLEEP);
  assert(lv2_obj::ppu_state(&peer,false,true).first==PPU_THREAD_STATUS_STOP);
  restored(worker,peer);
  assert(std::count(logs.begin(),logs.end(),"P42 guest yields: FIFO rotated to peer0/worker1, tail yield kept order, both return CELL_CANCEL without context switch")==1);
 }
 // Corrupted guest timebase outputs must fail and restore scheduler state.
 for(fault_mode=1;fault_mode<=5;fault_mode++) {
  populate(worker,peer,program);
  try {callWithTLS(&worker,0x50000,&program);assert(false);}
  catch(const std::runtime_error& e) {assert(std::string(e.what()).find("MFTB full/upper/full")!=std::string::npos);}
  restored(worker,peer);
 }
 fault_mode=0;
 // Exact production MFTB handler semantics around a low32 carry.
 utils::test_freq=80000000;
 for(u64 value:{0xffffffffull,0x100000000ull,0x00123456abcdef01ull}) {
  utils::test_tsc=value;
  execute_MFTB(worker,{0x7cac42e6});assert(worker.gpr[5]==value);
  execute_MFTB(worker,{0x7cad42e6});assert(worker.gpr[5]==(value>>32));
 }
 // Production clock scaling and offset are respected by both selectors.
 g_cfg.core.clocks_scale=50;g_timebase_offs=7;utils::test_tsc=0x200000100ull;
 execute_MFTB(worker,{0x7cac42e6});assert(worker.gpr[5]==0x100000079ull);
 execute_MFTB(worker,{0x7cad42e6});assert(worker.gpr[5]==1);
 g_cfg.core.clocks_scale=100;g_timebase_offs=0;utils::test_freq=0;
 try {execute_MFTB(worker,{0x7ca042e6});assert(false);}catch(const std::runtime_error&) {}
 auto count_calls=+[](ppu_thread* p,void*) {
  assert(sys_ppu_thread_yield(*p)==CELL_CANCEL && sys_ppu_thread_yield(*p)==CELL_CANCEL);p->check_state();s_ios_ppu_syscall_probe->counts[43]=2;s_ios_ppu_syscall_probe->counts[145]=3;s_ios_ppu_syscall_probe->counts[147]=1;s_ios_ppu_syscall_probe->counts[46]=2;s_ios_ppu_syscall_probe->counts[47]=5;
  s_ios_ppu_syscall_probe->counts[48]=2;s_ios_ppu_syscall_probe->counts[6]=1;return 35;};
 auto negative=+[](ppu_thread* p,void*) {lv2_obj::set_priority(*p,1200);return -77;};
 auto throwing=+[](ppu_thread* p,void*) ->int {lv2_obj::set_priority(*p,1200);throw std::runtime_error("injected");};
 populate(worker,peer,program);
 assert(lv2_obj::ios_probe_scheduler_time_and_call(&worker,&peer,negative,nullptr)==-77);restored(worker,peer);
 populate(worker,peer,program);
 try {lv2_obj::ios_probe_scheduler_time_and_call(&worker,&peer,throwing,nullptr);assert(false);}catch(const std::runtime_error&) {} restored(worker,peer);
 auto wrong_counts=+[](ppu_thread*,void*) {return 35;};
 populate(worker,peer,program);
 assert(lv2_obj::ios_probe_scheduler_time_and_call(&worker,&peer,wrong_counts,nullptr)==-3);restored(worker,peer);
 for(int mutation:{0,1,2,3,4,5}) {
  populate(worker,peer,program);
  struct State {ppu_thread* peer;int mutation;int(*counts)(ppu_thread*,void*);} state{&peer,mutation,count_calls};
  auto mutate=+[](ppu_thread* p,void* u) {
   auto& s=*static_cast<State*>(u);s.counts(p,nullptr);
   if(s.mutation==0) p->start_time++;
   if(s.mutation==1) s.peer->start_time++;
   if(s.mutation==2) s.peer->prio.value.prio=1151;
   if(s.mutation==3) lv2_obj::g_priority_order_tag.value++;
   if(s.mutation==4) lv2_obj::set_priority(*p,1200);
   if(s.mutation==5) lv2_obj::yield(*s.peer);
   return 28;
  };
  assert(lv2_obj::ios_probe_scheduler_time_and_call(&worker,&peer,mutate,&state)==-5);restored(worker,peer);
 }
 for(int guard=0;guard<9;guard++) {
  populate(worker,peer,program);
  if(guard==0) g_cfg.core.ppu_threads=1;
  if(guard==1) peer.id=worker.id;
  if(guard==2) peer.stack_addr=0x80000;
  if(guard==3) peer.prio.value.prio=1150;
  if(guard==4) peer.state+=cpu_flag::suspend;
  if(guard==5) peer.state+=cpu_flag::stop;
  if(guard==6) peer.interrupt_thread_executing=true;
  if(guard==7) g_scheduler_ready=true;
  if(guard==8) lv2_obj::g_pending=1;
  assert(lv2_obj::ios_probe_scheduler_time_and_call(&worker,&peer,count_calls,nullptr)<0);
  assert(!lv2_obj::g_ppu && !worker.next_ppu && !peer.next_ppu && !s_ios_ppu_syscall_probe);
  g_cfg.core.ppu_threads=2;g_scheduler_ready=false;lv2_obj::g_pending=0;
 }
 populate(worker,peer,program);
 auto nested=+[](ppu_thread* p,void* u) {auto* peer=static_cast<ppu_thread*>(u);
  assert(lv2_obj::ios_probe_scheduler_time_and_call(p,peer,+[](ppu_thread*,void*){return 0;},nullptr)==-2);return -88;};
 assert(lv2_obj::ios_probe_scheduler_time_and_call(&worker,&peer,nested,&peer)==-88);restored(worker,peer);
 // Admission retains FIFO for equal priorities in unchanged production awake.
 populate(worker,peer,program);peer.prio.value.prio=1100;
 assert(lv2_obj::awake(&worker) && lv2_obj::awake(&peer));assert(lv2_obj::g_ppu==&worker && worker.next_ppu==&peer);
 lv2_obj::unqueue(lv2_obj::g_ppu,&worker,&ppu_thread::next_ppu);lv2_obj::unqueue(lv2_obj::g_ppu,&peer,&ppu_thread::next_ppu);

 // Missing time calls reject and restore the actual scheduler scope.
 for(u32 code:{145u,147u}) {
  populate(worker,peer,program);
  struct Missing {u32 code;int(*fill)(ppu_thread*,void*);} missing{code,count_calls};
  auto omit=+[](ppu_thread* p,void* value){auto& m=*static_cast<Missing*>(value);m.fill(p,nullptr);--s_ios_ppu_syscall_probe->counts[m.code];return 44;};
  assert(lv2_obj::ios_probe_scheduler_time_and_call(&worker,&peer,omit,&missing)==-3);restored(worker,peer);
 }
 // Direct rotation and tail no-op preserve timestamps/order within two slots.
 populate(worker,peer,program);
 assert(lv2_obj::awake(&worker) && lv2_obj::awake(&peer));
 assert(sys_ppu_thread_yield(worker)==CELL_CANCEL);
 assert(lv2_obj::g_ppu==&peer && peer.next_ppu==&worker && !worker.next_ppu);
 assert(sys_ppu_thread_yield(worker)==CELL_CANCEL);
 assert(lv2_obj::g_ppu==&peer && peer.next_ppu==&worker && !worker.next_ppu);
 lv2_obj::unqueue(lv2_obj::g_ppu,&worker,&ppu_thread::next_ppu);lv2_obj::unqueue(lv2_obj::g_ppu,&peer,&ppu_thread::next_ppu);
 restored(worker,peer);
 // Old policies still reject yield counts; policy3 requires exactly two.
 for(u32 policy:{0u,1u,2u,3u,4u}) {
  populate(worker,peer,program);
  auto counts=+[](ppu_thread*,void* value) {
   const u32 policy=*static_cast<u32*>(value);
   auto& c=s_ios_ppu_syscall_probe->counts;c[46]=2;c[6]=1;
   c[policy?48:49]=policy>=2?2:1;
   if(policy)c[47]=policy>=2?5:3;
   if(policy>=3)c[43]=2;
   if(policy==4){c[145]=3;c[147]=1;}
   return 35;
  };
  assert(ppu_probe_syscalls_and_call(&worker,counts,&policy,policy)==35);
  struct Bad {u32 policy;int(*fill)(ppu_thread*,void*);} bad{policy,counts};
  auto wrong=+[](ppu_thread* p,void* value) {
   auto& b=*static_cast<Bad*>(value);b.fill(p,&b.policy);
   s_ios_ppu_syscall_probe->counts[43]=1;return 35;
  };
  assert(ppu_probe_syscalls_and_call(&worker,wrong,&bad,policy)==-3);
  assert(!s_ios_ppu_syscall_probe);
 }
 std::cout<<"PASS: full production queue/priority/service/fast_call bodies, exact P42 callback, loaded guest opcode execution, real current-time/frequency and MFTB handlers/clock body, carry/scaling/offset semantics, five corrupt timebase rejections, null outputs, yield FIFO/tail, histories and rollback/guards\n";
}
'''
with tempfile.TemporaryDirectory(prefix='p42-timebase-') as temp:
    source = Path(temp) / 'regression.cpp'
    binary = Path(temp) / 'regression'
    source.write_text(shims + production + transport + checks)
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                    '-fno-exceptions', '-fexceptions', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', '-g', str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

"""Compile production scheduler/service bodies and the exact P49 callback.

Checks production SC351 page structs/history, error publication and corruptions,
the user1m location/flags, every released heap byte and adjacent canaries,
full-charge availability zero, and oversized ENOMEM. Heap virtual addresses use
0x10000000 so the page handler takes its production VM path, not the stack path.

Locks/atomics/VM/SC transport/guest instruction execution use host shims.
IDM select is the exact production template; its map and FXO lifecycle are shimmed.
Full awake/awake_unlocked/schedule_all/fast_call, priorities, service handlers,
queue bookkeeping and the diagnostic callback/wrappers are unchanged bodies.

Usage: python test_p49_process.py upstream-armsx3/rpcs3 CoreBridge.cpp
The upstream tree must have all 46 iOS patches applied. Both paths are required.
"""
from pathlib import Path
import subprocess
import tempfile
import sys

r = Path(__file__).resolve().parent
if len(sys.argv) != 3:
    raise SystemExit(__doc__)


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
process = read_core('Emu/Cell/lv2/sys_process.cpp','sys_process.cpp')
time = read_core('Emu/Cell/lv2/sys_time.cpp','sys_time.cpp')
memory_service=read_core('Emu/Cell/lv2/sys_memory.cpp','sys_memory.cpp')
memory_header=read_core('Emu/Cell/lv2/sys_memory.h','sys_memory.h')
idm_header=read_core('Emu/IdManager.h','IdManager.h')
interpreter = read_core('Emu/Cell/PPUInterpreter.cpp','PPUInterpreter.cpp')
bridge = bridge_path.read_text().split('int armsx3_core_test_process_sdk()', 1)[1]
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
#include <map>
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
namespace stx {template<class T> using shared_ptr=std::shared_ptr<T>;}
using shared_mutex=std::mutex;
template<class T> T swap_be(T v) {if constexpr(sizeof(T)==4) return T(__builtin_bswap32(u32(v))); else return T(__builtin_bswap64(u64(v)));}
template<class T> struct be_t {T value{}; operator T() const {return swap_be(value);} be_t& operator=(T x) {value=swap_be(x);return *this;} be_t& operator-=(T x) {return *this=T(*this)-x;}};
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
template<class T> const T& ensure(const T& v) {if(!static_cast<bool>(v))throw std::runtime_error("ensure");return v;}
template<class T> struct atomic_t {
 T value{};
 atomic_t()=default; atomic_t(T v):value(v) {}
 operator T() const {return value;} T load() const {return value;}
 void release(T v) {value=v;} atomic_t& operator=(T v) {value=v;return *this;}
 T exchange(T v) {T old=value;value=v;return old;}
 template<class F> auto fetch_op(F f) {T old=value;auto result=f(value);return std::pair{old,result};}
 T operator++() {return ++value;} T operator++(int) {return value++;}
 T operator--(int) {return value--;}
 template<class F> auto atomic_op(F f) {return f(value);}
};
template<class T> struct atomic_storage {static T load(T v) {return v;} static void release(T& a,T v) {a=v;} static void store(T& a,T v) {a=v;}};
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
 void check_state() {state-=cpu_flag::wait;}
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
 u32 raddr=0; u64 ctr=0; unsigned guest_steps=0;bool cr0_equal=false;
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
template<class A,class B> constexpr bool PtrSame=std::is_same_v<A,B>;
template<class A,class B> constexpr bool IdmTypesCompatible=std::is_same_v<A,B>;
template<class T> struct atomic_ptr {
 shared_ptr<T> value;
 T* observe() const {return value.get();} shared_ptr<T> load() const {return value;}
 atomic_ptr& operator=(shared_ptr<T> p) {value=std::move(p);return *this;}
 void reset() {value.reset();}
};
namespace id_manager {
 template<class T> struct id_map {
  struct key {u32 value=0;u32 type() const {return T::id_base;} operator u32() const {return value;}};
  std::array<atomic_ptr<T>,16> vec_data{};
  std::array<key,16> vec_keys{};
 };
}
class idm {
 template<class F> struct function_traits;
 template<class F,class R,class A1,class A2> struct function_traits<R(F::*)(A1,A2&) const> {using object_type=A2;using result_type=R;};
 template<class T,class R> struct return_pair {T ptr;R ret{};};
 template<class T> static constexpr u32 get_type() {return T::id_base;}
public:
 template<class T,class F> static bool check(u32,F) {return false;}
 template<class T,class... Get,class F,class Lock=std::true_type> static auto select(F&&,Lock=std::true_type{});
};
struct {u32 sdk_ver=0xaabbccdd,ppc_seg=0x13579,ctrl_flags1=0x2468;bool debug_or_root() const {return false;}} g_ps3_process_info;
struct logger {template<class... T> void trace(const char*,T...) {}
 template<class... T> void warning(const char*,T...) {} template<class... T> void error(const char*,T...) {} template<class... T> void notice(const char*,T...) {}} ppu_log,sys_ppu_thread,sys_time,sys_memory,sys_process;
struct error_code {s32 value;error_code(s32 v):value(v) {} error_code(s32 v,u64):value(v) {} operator s32() const {return value;}};
enum CellError : u32 {};
constexpr s32 CELL_CANCEL=1,CELL_OK=0,CELL_EINVAL=s32(0x80010002),CELL_EFAULT=s32(0x8001000d),CELL_ESRCH=s32(0x80010005),CELL_ENOSYS=s32(0x80010003);
constexpr s32 CELL_EALIGN=s32(0x80010010),CELL_ENOMEM=s32(0x80010004);
namespace vm {
 std::vector<u8> memory(0x210000);
 u32 index(u32 addr) {return addr>=0x10000000?0x100000+(addr-0x10000000):addr;}
 void* base(u32 addr) {return memory.data()+index(addr);}
 void* get_super_ptr(u32 addr) {return base(addr);}
 template<class T> be_t<T>* _ptr(u32 addr) {return reinterpret_cast<be_t<T>*>(base(addr));}
 template<class T> struct ptr {u32 address=0; u32 addr() const {return address;} u32 size() const {return sizeof(T);} explicit operator bool() const {return address!=0;} auto& operator*() const {if constexpr(std::is_integral_v<T>)return *_ptr<T>(address);else return *reinterpret_cast<T*>(base(address));} T* operator->() const {return reinterpret_cast<T*>(base(address));}};
 u32 read32(u32 a) {return *_ptr<u32>(a);} u64 read64(u32 a) {return *_ptr<u64>(a);}
 void write32(u32 a,u32 v) {*_ptr<u32>(a)=v;} void write64(u32 a,u64 v) {*_ptr<u64>(a)=v;}
 std::map<u32,u32> live_heap;
 unsigned allocation_attempts=0,actual_allocations=0,actual_frees=0;bool allocation_failure=false,guest_allocation_failure=false;
 std::vector<u32> allocator_locations; unsigned guest_heap_reads=0,guest_heap_writes=0;std::vector<u8> freed_heap;
 constexpr u32 user64k=1,user1m=2,any=3;constexpr u64 block_size_64k=1,block_size_1m=2,bf0_0x1=4;
 struct block {u32 addr=0x10000000;u32 alloc(u32 size,void*,u32 align) {
  ++allocation_attempts;if(allocation_failure || (guest_allocation_failure && allocation_attempts==2))return 0;assert(((size==0x10000 && align==0x10000) || (size==0x100000 && align==0x100000)) && live_heap.empty());
  std::fill(memory.begin()+index(addr),memory.begin()+index(addr)+size,0xa5);
  std::fill(memory.begin()+index(addr)-16,memory.begin()+index(addr),0x5a);std::fill(memory.begin()+index(addr)+size,memory.begin()+index(addr)+size+16,0x5a);
  live_heap.emplace(addr,size);++actual_allocations;return addr;}};
 shared_ptr<block> reserve_map(u32 location,u32,u32 size,u64 flags) {assert(size==0x10000000);assert((location==user64k && flags==(block_size_64k|bf0_0x1)) || (location==user1m && flags==(block_size_1m|bf0_0x1)));allocator_locations.push_back(location);return std::make_shared<block>();}
 shared_ptr<block> get(u32,u32) {return std::make_shared<block>();}
 shared_ptr<block> find_map(u32,u32,u64) {return {};}
 u32 dealloc(u32 addr) {auto i=live_heap.find(addr);if(i==live_heap.end())return 0;u32 n=i->second;freed_heap.assign(memory.begin()+index(addr),memory.begin()+index(addr)+n);live_heap.erase(i);++actual_frees;return n;}
 constexpr u32 page_readable=1,page_1m_size=2,page_64k_size=4;
 bool check_addr(u32 addr,u32=page_readable,u32 bytes=1) {
  if(addr>=0x10000 && u64(addr)+bytes<=0xa0000)return true;
  for(auto [start,size]:live_heap)if(addr>=start && u64(addr)+bytes<=u64(start)+size)return true;
  return false;
 }
 std::pair<bool,u32> get_addr_flags(u32 addr) {for(auto [start,size]:live_heap)if(addr>=start && u64(addr)<u64(start)+size)return {true,size==0x100000?page_1m_size:page_64k_size};return {false,0};}
 void lock_sudo(u32 addr,u32 size) {assert(check_addr(addr) && live_heap.at(addr)==size);}
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
 bool failNextInit=false;
 template<class T> static auto& storage() {static std::unique_ptr<T> value;return value;}
 template<class T> bool is_init() {if constexpr(std::is_same_v<T,ppu_interpreter_rt> || std::is_same_v<T,ppu_function_manager>)return true;else return bool(storage<T>());}
 bool is_init() {return true;}
 template<class T,class... Args> T* init(Args&&... args) {auto& p=storage<T>();if(p)return nullptr;if(failNextInit){failNextInit=false;return nullptr;}p=std::make_unique<T>(std::forward<Args>(args)...);return p.get();}
 template<class T> T& get() {if constexpr(std::is_same_v<T,ppu_interpreter_rt>) return interpreter; else if constexpr(std::is_same_v<T,ppu_function_manager>)return manager;else {if(!storage<T>())throw std::runtime_error("uninitialized FXO storage filled with0xCC");return *storage<T>();}}} fxo_instance;
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
namespace utils {u64 test_freq=0,test_tsc=1;u64 get_tsc_freq() {return test_freq;} u32 align(u32 a,u32 b) {return (a+b-1)&~(b-1);}u64 get_tsc() {return test_tsc;}}
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
 static int ios_probe_scheduler_process_sdk_and_call(ppu_thread*,ppu_thread*,int(*)(ppu_thread*,void*),void*);
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
# Scalar FXO/VM/atomic transport is shimmed; all memory operation bodies are exact.
production += '\nconstexpr u32 SYS_MEMORY_CONTAINER_ID_INVALID=UINT32_MAX;\nconstexpr u64 SYS_MEMORY_PAGE_SIZE_64K=0x200,SYS_MEMORY_PAGE_SIZE_1M=0x400;\n'
production += 'struct lv2_memory_container {static constexpr u32 id_base=0x3f000000;const u32 size,id=SYS_MEMORY_CONTAINER_ID_INVALID;atomic_t<u32> used{};explicit lv2_memory_container(u32 n):size(n) {}\n'+function(memory_header,'u32 take(')+'\n'+function(memory_header,'u32 free(')+'\n};\n'
select_body=function(idm_header,'\n\t{\n\t\tstatic_assert((IdmTypesCompatible<T, Get>')
production += '\ntemplate<class T,class... Get,class F,class Lock> auto idm::select(F&& func,Lock) '+select_body+'\n'
production += 'struct sys_memory_address_table {atomic_t<lv2_memory_container*> addrs[65536]{};std::array<u32,2> secondary_areas{};std::mutex mutex;\n'+function(memory_service,'u32 allocate(')+'\n};\n'
production += '\nstd::mutex s_memstats_mtx;\n'+function(memory_service,'struct last_reported_memory_stats')+';\n'+function(memory_header,'struct sys_memory_info_t')+';\n'
production += 'constexpr u32 SPU_FAKE_BASE_ADDR=0xe0000000; constexpr u64 SYS_MEMORY_ACCESS_RIGHT_PPU_THR=8,SYS_MEMORY_ACCESS_RIGHT_ANY=15;\n'+function(memory_header,'struct sys_page_attr_t')+';\n'
production += 'error_code sys_memory_free(cpu_thread&,u32);\n'+'\n'.join(function(memory_service,sig) for sig in ['u32 allocate_user_memory(','error_code sys_memory_allocate(','error_code sys_memory_free(','error_code sys_memory_get_user_memory_size(','error_code sys_memory_get_page_attribute('])
production += '\nstatic thread_local bool s_ios_memory_probe_active=false;\n'+function(memory_service,'extern "C" int armsx3_ios_memory_probe_and_call(')+'\n'+function(memory_service,'extern "C" int armsx3_ios_memory_stats_probe_and_call(')
registry_init='    using ContainerMap = id_manager::id_map<lv2_memory_container>;\n    if (!g_fxo->is_init<ContainerMap>() && !g_fxo->init<ContainerMap>()) return -3;\n'
assert registry_init in memory_service
old_scope=function(memory_service,'extern "C" int armsx3_ios_memory_stats_probe_and_call(').replace(registry_init,'').replace('armsx3_ios_memory_stats_probe_and_call','build64_memory_stats_probe_and_call',1)
production += '\n'+old_scope+'\n'
probe_start = lv2.index('struct ios_ppu_syscall_probe')
probe_end = lv2.index('extern "C" int armsx3_ios_ppu_probe_syscalls_and_call', probe_start)
production += '\n' + lv2[probe_start:probe_end]
production += '\n' + '\n'.join(function(lv2, sig) for sig in [
    'int lv2_obj::ios_probe_scheduler_process_sdk_and_call(',
    'int lv2_obj::ios_probe_scheduler_queue_and_call(',
    'int lv2_obj::ios_probe_priority_change_and_call(',
    'extern "C" int armsx3_ios_ppu_probe_scheduler_process_sdk_and_call(',
])
production += '\n' + '\n'.join(function(process,sig) for sig in ['s32 process_getpid(', 's32 sys_process_getpid(', 's32 process_get_sdk_version(', 'error_code sys_process_get_sdk_version('])
production += '\nstatic thread_local bool s_ios_process_sdk_probe_active=false;\n' + function(process,'extern \"C\" int armsx3_ios_process_sdk_probe_and_call(')
transport = r'''
unsigned fault_mode_stats=0;
unsigned fault_mode_pages=0;
unsigned fault_mode_process=0;
void run_sc(ppu_thread& worker,ppu_opcode_t,be_t<u32>* pc,void*) {
 const u32 cia=u32(reinterpret_cast<u8*>(pc)-vm::memory.data());
 const u32 code=u32(worker.gpr[11]);
 assert(s_ios_ppu_syscall_probe && code<1024);
 s_ios_ppu_syscall_probe->counts[code]++;
 s32 error=0; const char* name=nullptr;
 if(code==1) {name="sys_process_getpid";error=sys_process_getpid();}
 else if(code==25) {name="sys_process_get_sdk_version";assert(worker.gpr[3]==(fault_mode_process==1?2u:1u));error=sys_process_get_sdk_version(u32(worker.gpr[3]),{u32(worker.gpr[4])});}
 else if(code==351) {name="sys_memory_get_page_attribute";error=sys_memory_get_page_attribute(worker,u32(worker.gpr[3]),{u32(worker.gpr[4])});}
 else if(code==352) {name="sys_memory_get_user_memory_size";error=sys_memory_get_user_memory_size(worker,{u32(worker.gpr[3])});}
 else if(code==348) {name="sys_memory_allocate";error=sys_memory_allocate(worker,worker.gpr[3],worker.gpr[4],{u32(worker.gpr[5])});}
 else if(code==349) {name="sys_memory_free";error=sys_memory_free(worker,u32(worker.gpr[3]));}
 else if(code==145) {name="sys_time_get_current_time";error=sys_time_get_current_time({u32(worker.gpr[3])},{u32(worker.gpr[4])});}
 else if(code==147) {name="sys_time_get_timebase_frequency";error=s32(sys_time_get_timebase_frequency());}
 else if(code==43) {name="sys_ppu_thread_yield";error=sys_ppu_thread_yield(worker);}
 else if(code==46) {name="sys_ppu_thread_get_join_state";error=sys_ppu_thread_get_join_state(worker,{u32(worker.gpr[3])});}
 else if(code==47) {name="sys_ppu_thread_set_priority";error=sys_ppu_thread_set_priority(worker,u32(worker.gpr[3]),s32(worker.gpr[4]));}
 else if(code==48) {name="sys_ppu_thread_get_priority";error=sys_ppu_thread_get_priority(worker,u32(worker.gpr[3]),{u32(worker.gpr[4])});}
 else {assert(code==6); worker.gpr[3]=u32(CELL_ENOSYS);worker.cia=cia+4;return;}
 if(code==351 && fault_mode_pages) {
  const u32 a=u32(worker.gpr[4]);
  if(a==0x201c0) {
   if(fault_mode_pages==1)vm::write64(a,0x80000);
   if(fault_mode_pages==2)vm::write64(a+8,8);
   if(fault_mode_pages==3)vm::write32(a+16,0x10000);
   if(fault_mode_pages==4)vm::write32(a+20,1);
   if(fault_mode_pages==5)error=CELL_EFAULT;
  }
  if(a==0 && fault_mode_pages==8)error=CELL_OK;
  if(a==0 && fault_mode_pages==9)error=CELL_EINVAL;
  if(a==0x9fff8 && fault_mode_pages==10)error=CELL_OK;
  if(a==0x9fff8 && fault_mode_pages==11)vm::write64(a,0x40000);
  if(a==0x201e0) {
   if(fault_mode_pages==6)vm::write32(a,1);
   if(fault_mode_pages==7)error=CELL_OK;
  }
 }
 if(code==352 && fault_mode_stats) {
  const u32 a=u32(worker.gpr[3]);
  if((fault_mode_stats==1 && a==0x20180) || (fault_mode_stats==2 && a==0x20188) || (fault_mode_stats==3 && a==0x20190))vm::write32(a+4,vm::read32(a+4)^1);
  if(fault_mode_stats==4 && a==0x20188)vm::write32(a,0xfffff);
  if(fault_mode_stats==5 && a==0x20190)error=CELL_EINVAL;
 }
 if(code==1 && fault_mode_process==1)error=2;
 if(code==25 && fault_mode_process==2)vm::write32(u32(worker.gpr[4]),0x00350001);
 if(code==25 && fault_mode_process==3)error=CELL_EINVAL;
 worker.gpr[3]=u64(s64(error));
 worker.syscall_history.data[worker.syscall_history.index++%32]={cia,name,worker.gpr[3]};
 worker.cia=cia+4;
 worker.check_state();
}

unsigned fault_mode=0;
int armsx3_ios_ppu_call_bounded(ppu_thread* worker,u32 begin,u32 end,u32 toc,u32 ret,u32 budget) {
 assert(begin==0x10000 && end==0x101e4 && toc==0x20020 && ret==0x4000c && budget==122);
 worker->guest_steps=0;
 worker->exec=[begin,end,ret,budget](ppu_thread& c) {
  while(c.cia!=ret) {
   assert(c.cia>=begin && c.cia<end && c.guest_steps<budget);
   const u32 pc=c.cia,op=vm::read32(pc),type=op>>26,rt=(op>>21)&31,ra=(op>>16)&31;
   const s32 imm=int16_t(op&0xffff);
   const u64 base=ra?c.gpr[ra]:0;
   const auto guestAccess=[&](u32 a,u32 bytes,bool store) {
    if(pc>=begin+224 && pc<=begin+284 && ra!=1) {
     assert(a>=0x10000000 && u64(a)+bytes<=0x10100000 && vm::check_addr(0x10000000));
     if(store)++vm::guest_heap_writes;else ++vm::guest_heap_reads;
    }
   };
   c.guest_steps++;c.cia=pc+4;
   switch(type) {
    case 11: assert(op==0x2c030000);c.cr0_equal=s32(c.gpr[3])==0;break;
    case 16: assert(op==0x40820044);if(!c.cr0_equal)c.cia=pc+68;break;
    case 14: c.gpr[rt]=base+imm;break;
    case 15: c.gpr[rt]=base+s64(imm)*65536;break;
    case 24: c.gpr[ra]=c.gpr[rt]|(op&0xffff);break;
    case 32: guestAccess(u32(base+imm),4,false);c.gpr[rt]=vm::read32(u32(base+imm));break;
    case 34: guestAccess(u32(base+imm),1,false);c.gpr[rt]=vm::memory.at(vm::index(u32(base+imm)));break;
    case 40: {const u32 a=u32(base+imm);guestAccess(a,2,false);c.gpr[rt]=(u32(vm::memory.at(vm::index(a)))<<8)|vm::memory.at(vm::index(a+1));break;}
    case 36: {
     const u32 a=u32(base+imm);guestAccess(a,4,true);u32 value=u32(c.gpr[rt]);
     if(ra==1 && ((fault_mode==6 && imm==96) || (fault_mode==7 && imm==108) || (fault_mode==8 && imm==112) || (fault_mode==9 && imm==116)))value^=1;
     if(fault_mode==10 && ra!=1 && pc>=begin+224 && pc<=begin+284)value=__builtin_bswap32(value);
     vm::write32(a,value);break;
    }
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
 vm::memory.assign(0x210000,0);logs.clear();notifications=0;vm::actual_allocations=vm::actual_frees=0;vm::allocation_attempts=0;vm::guest_heap_reads=vm::guest_heap_writes=0;vm::freed_heap.clear();vm::allocator_locations.clear();
 vm::write64(0x9fff8,0x5aa55aa5deadbeefull);
 g_ps3_process_info.sdk_ver=0xaabbccdd;
 worker=ppu_thread{};peer=ppu_thread{};
 worker.prio.value.all=0;worker.prio.value.prio=1100;
 peer.prio.value.all=0;peer.prio.value.prio=1100;
 peer.id++;peer.stack_addr=0x90000;peer.start_time=951053533599ull;
 peer.joiner=ppu_join_status::detached;
 program.~Program();new (&program) Program{};
 program.begin=0x10000;program.end=0x101e4;program.returnAddress=0x4000c;
 program.dataAddress=0x20000;program.argvAddress=0x37f40;program.id=worker.id;
 program.sdkVersion=0x00360001;
 program.primaryPriority=1100;program.initialStack=0x37ed0;program.peer=&peer;
 worker.gpr[4]=program.argvAddress;worker.gpr[7]=worker.id;worker.gpr[13]=0x57060;
 worker.gpr[1]=0x37ed0;worker.gpr[2]=0x13579;
 vm::write32(0x20000,0x10060);vm::write32(0x20004,0x20000);vm::write32(0x200b0,0x20000);
 const unsigned char opcodes[] = {124,8,2,166,248,33,255,129,248,1,0,16,248,65,0,24,96,227,0,0,129,106,0,0,129,139,0,0,128,75,0,4,125,137,3,166,78,128,4,33,232,65,0,24,96,73,0,0,248,98,0,16,56,98,0,24,57,96,0,46,68,0,0,2,144,98,0,28,136,109,144,0,56,99,255,193,248,98,0,0,232,1,0,16,56,33,0,128,124,8,3,166,78,128,0,32,57,96,0,43,68,0,0,2,144,98,0,24,57,96,0,43,68,0,0,2,144,98,0,28,56,97,0,32,56,129,0,40,57,96,0,145,68,0,0,2,248,97,0,48,57,96,0,147,68,0,0,2,248,97,0,56,124,172,66,230,248,161,0,64,124,173,66,230,248,161,0,72,124,172,66,230,248,161,0,80,56,98,1,128,57,96,1,96,68,0,0,2,144,98,1,152,60,96,0,16,56,128,4,0,56,161,0,88,57,96,1,92,68,0,0,2,144,97,0,92,44,3,0,0,64,130,0,68,128,193,0,88,60,160,18,52,96,165,86,120,144,166,0,0,128,102,0,0,144,97,0,96,61,70,0,16,60,160,137,171,96,165,205,239,144,170,255,252,128,106,255,252,144,97,0,108,136,102,0,0,144,97,0,112,160,106,255,252,144,97,0,116,128,97,0,88,56,130,1,192,57,96,1,95,68,0,0,2,144,98,1,216,128,97,0,88,56,128,0,0,57,96,1,95,68,0,0,2,144,98,1,252,128,97,0,88,60,128,0,10,56,132,255,248,57,96,1,95,68,0,0,2,144,98,2,0,56,98,1,136,57,96,1,96,68,0,0,2,144,98,1,156,128,97,0,88,57,96,1,93,68,0,0,2,144,97,0,100,128,97,0,88,57,96,1,93,68,0,0,2,144,97,0,104,128,97,0,88,56,130,1,224,57,96,1,95,68,0,0,2,144,98,1,248,56,98,1,144,57,96,1,96,68,0,0,2,144,98,1,160,57,96,0,1,68,0,0,2,144,98,2,32,56,130,2,36,57,96,0,25,68,0,0,2,144,98,2,40,96,227,0,0,56,130,0,40,57,96,0,48,68,0,0,2,78,128,0,32};
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
 assert(!s_ios_process_sdk_probe_active && g_ps3_process_info.sdk_ver==0xaabbccdd);
 assert(g_ps3_process_info.ppc_seg==0x13579 && g_ps3_process_info.ctrl_flags1==0x2468);
 const auto stats=g_fxo->get<last_reported_memory_stats>().body.load();assert(stats.prev_total==UINT32_MAX && stats.prev_avail==UINT32_MAX);
}
int main() {
''' + call_tls + r'''
 ppu_thread worker,peer; Program program;
 using ContainerMap=id_manager::id_map<lv2_memory_container>;
 populate(worker,peer,program);
 assert(!g_fxo->is_init<ContainerMap>());
 bool reachedGuest=false;
 auto noGuest=+[](ppu_thread*,void* p)->int {*static_cast<bool*>(p)=true;return -77;};
 try {build64_memory_stats_probe_and_call(&worker,noGuest,&reachedGuest);assert(false);}
 catch(const std::runtime_error& e) {assert(std::string(e.what())=="uninitialized FXO storage filled with0xCC");}
 assert(!reachedGuest && !g_fxo->is_init<ContainerMap>() && worker.syscall_history.index==0);
 g_fxo->failNextInit=true;
 assert(armsx3_ios_memory_stats_probe_and_call(&worker,noGuest,&reachedGuest)==-3);
 assert(!reachedGuest && !g_fxo->is_init<ContainerMap>() && worker.syscall_history.index==0);
 ContainerMap* retainedRegistry=nullptr;
 for(bool joinable:{true,false}) {
  populate(worker,peer,program);program.joinable=joinable;
  worker.joiner=joinable?ppu_join_status::joinable:ppu_join_status::detached;
  const int result=callWithTLS(&worker,0x50000,&program);
  assert(g_fxo->is_init<ContainerMap>());
  auto* registry=&g_fxo->get<ContainerMap>();
  assert(!retainedRegistry || retainedRegistry==registry);retainedRegistry=registry;
  assert(std::all_of(registry->vec_data.begin(),registry->vec_data.end(),[](const auto& p){return !p.observe();}));
  assert(result==122 && program.syscalls && program.tlsMemory && worker.gpr[3]==42);
  assert(worker.interrupt_thread_executing && !peer.interrupt_thread_executing);
  assert(worker.syscall_history.index==31 && peer.syscall_history.index==0);
  assert(worker.gpr[1]==program.initialStack && worker.gpr[2]==0x13579 && worker.gpr[4]==0x20028);
  std::vector<u8> expectedStack(0x10000,0);
  const u32 frame=program.initialStack-128;
  auto put=[&](u32 offset,u64 value){be_t<u64> word;word=value;std::memcpy(expectedStack.data()+frame-0x30000+offset,&word,8);};
  put(0,program.initialStack);put(16,program.returnAddress);put(24,0x20020);
  put(32,program.clockSeconds);put(40,program.clockNanoseconds);put(48,0);put(56,80000000);
  put(64,program.timebaseFirst);put(72,program.timebaseUpper);put(80,program.timebaseLast);
  auto put32=[&](u32 offset,u32 value){be_t<u32> word;word=value;std::memcpy(expectedStack.data()+frame-0x30000+offset,&word,4);};
  put32(88,program.allocatedAddress);put32(92,0);put32(100,0);put32(104,u32(CELL_EINVAL));
  put32(96,0x12345678);put32(108,0x89abcdef);put32(112,0x12);put32(116,0x89ab);
  assert(vm::guest_heap_reads==4 && vm::guest_heap_writes==2);
  std::vector<u8> expectedHeap(0x100000,0xa5);
  expectedHeap[0]=0x12;expectedHeap[1]=0x34;expectedHeap[2]=0x56;expectedHeap[3]=0x78;
  expectedHeap[0xffffc]=0x89;expectedHeap[0xffffd]=0xab;expectedHeap[0xffffe]=0xcd;expectedHeap[0xfffff]=0xef;
  assert(vm::freed_heap==expectedHeap);
  assert(std::all_of(vm::memory.begin()+0xffff0,vm::memory.begin()+0x100000,[](u8 b){return b==0x5a;}));
  assert(std::all_of(vm::memory.begin()+0x200000,vm::memory.begin()+0x200010,[](u8 b){return b==0x5a;}));
  assert(program.allocatedAddress==0x10000000 && vm::live_heap.empty());
  for(auto [offset,value]:std::array<std::pair<u32,u32>,9>{{{384,0x100000},{388,0x100000},{392,0x100000},{396,0},{400,0x100000},{404,0x100000},{408,0},{412,0},{416,0}}})assert(vm::read32(0x20000+offset)==value);
  assert(vm::read64(0x201c0)==0x40000 && vm::read64(0x201c8)==15);
  assert(vm::read32(0x201d0)==0x100000 && vm::read32(0x201d4)==0 && vm::read32(0x201d8)==0);
  for(u32 offset:{480u,484u,488u,492u,496u,500u})assert(vm::read32(0x20000+offset)==0);
  assert(vm::read32(0x201f8)==u32(CELL_EINVAL));
  assert(vm::read32(0x20220)==1 && vm::read32(0x20224)==0x00360001 && vm::read32(0x20228)==0);
  assert(g_fxo->get<lv2_memory_container>().used.load()==0);
  assert(vm::actual_allocations==2 && vm::actual_frees==2);assert(vm::allocator_locations==std::vector<u32>({vm::user1m,vm::user1m}));
  assert(!std::memcmp(vm::base(0x30000),expectedStack.data(),expectedStack.size()));
  assert(std::all_of(vm::memory.begin()+0x90000,vm::memory.begin()+0x9fff8,[](u8 b){return b==0;}));
  assert(vm::read64(0x9fff8)==0x5aa55aa5deadbeefull);
  assert(vm::read32(0x201fc)==u32(CELL_EFAULT) && vm::read32(0x20200)==u32(CELL_EFAULT));
  assert(lv2_obj::ppu_state(&worker,false,true).first==PPU_THREAD_STATUS_SLEEP);
  assert(lv2_obj::ppu_state(&peer,false,true).first==PPU_THREAD_STATUS_STOP);
  restored(worker,peer);
  assert(std::count(logs.begin(),logs.end(),"P49 guest yields: FIFO rotated to peer0/worker1, tail yield kept order, both return CELL_CANCEL without context switch")==1);
 }
 // Process handlers and scope: restore a nondefault SDK on every exit path.
 populate(worker,peer,program);
 assert(sys_process_getpid()==1);
 assert(sys_process_get_sdk_version(1,{0x20224})==CELL_OK);
 assert(vm::read32(0x20224)==0xaabbccdd);
 for(fault_mode_process=1;fault_mode_process<=3;fault_mode_process++) {
  populate(worker,peer,program);
  try {callWithTLS(&worker,0x50000,&program);assert(false);}
  catch(const std::runtime_error& e) {assert(std::string(e.what()).find("process SDK/page attributes")!=std::string::npos);}
  assert(vm::live_heap.empty() && !g_fxo->get<lv2_memory_container>().used.load());restored(worker,peer);
 }
 fault_mode_process=0;
 for(unsigned mode=0;mode<4;mode++) {
  populate(worker,peer,program);
  auto executeSDK=+[](ppu_thread*,void* p)->int {
   assert(g_ps3_process_info.sdk_ver==0x00360001 && s_ios_process_sdk_probe_active);
   const unsigned mode=*static_cast<unsigned*>(p);
   if(mode==1)throw std::runtime_error("SDK scope throw");
   if(mode==2)g_ps3_process_info.sdk_ver=7;
   return mode==3?44:-77;
  };
  try {assert(armsx3_ios_process_sdk_probe_and_call(&worker,0x00360001,executeSDK,&mode)==(mode==2?-3:mode==3?44:-77));assert(mode!=1);}
  catch(const std::runtime_error& e) {assert(mode==1 && std::string(e.what())=="SDK scope throw");}
  restored(worker,peer);
 }
 populate(worker,peer,program);
 auto nestedSDK=+[](ppu_thread* p,void*)->int {
  assert(armsx3_ios_process_sdk_probe_and_call(p,0x00360001,+[](ppu_thread*,void*){assert(false);return 0;},nullptr)==-2);
  assert(g_ps3_process_info.sdk_ver==0x00360001 && s_ios_process_sdk_probe_active);return -88;
 };
 assert(armsx3_ios_process_sdk_probe_and_call(&worker,0x00360001,nestedSDK,nullptr)==-88);restored(worker,peer);
 for(unsigned bad=0;bad<10;bad++) {
  populate(worker,peer,program);ppu_thread* p=&worker;u32 sdk=0x00360001;
  auto untouched=+[](ppu_thread*,void*)->int {assert(false);return 0;};
  int(*execute)(ppu_thread*,void*)=untouched;
  if(bad==0)p=nullptr;
  if(bad==1)execute=nullptr;
  if(bad==2)Emu.stopped=false;
  if(bad==3)cpu_thread::current=&peer;
  if(bad==4)g_cfg.core.ppu_decoder=ppu_decoder_type::llvm;
  if(bad==5)sdk=0x00350001;
  if(bad==6)worker.stack_addr=0x30004;
  if(bad==7)worker.stack_size=0x10000;
  if(bad==8)worker.entry_func.addr=0x10004;
  if(bad==9)sdk=UINT32_MAX;
  assert(armsx3_ios_process_sdk_probe_and_call(p,sdk,execute,nullptr)==-1);
  Emu.stopped=true;cpu_thread::current=&worker;g_cfg.core.ppu_decoder=ppu_decoder_type::_static;restored(worker,peer);
 }
 // Corrupt all availability snapshots, total size, and syscall status/history.
 for(fault_mode_pages=1;fault_mode_pages<=11;fault_mode_pages++) {
  populate(worker,peer,program);program.joinable=true;worker.joiner=ppu_join_status::joinable;
  try {callWithTLS(&worker,0x50000,&program);assert(false);}
  catch(const std::runtime_error& e) {assert(std::string(e.what()).find("page attributes/time/memory/yield")!=std::string::npos);}
  assert(vm::live_heap.empty() && !g_fxo->get<lv2_memory_container>().used.load());
  restored(worker,peer);
 }
 fault_mode_pages=0;
 // Extra host-only boundary coverage of the unchanged page-attribute handler.
 populate(worker,peer,program);
 assert(sys_memory_allocate(worker,0x100000,0x400,{0x20010})==CELL_OK);
 const u32 live=vm::read32(0x20010);
 std::fill(vm::memory.begin()+0x201c0,vm::memory.begin()+0x201d8,0x5a);
 assert(sys_memory_get_page_attribute(worker,live,{0})==CELL_EFAULT);
 assert(sys_memory_get_page_attribute(worker,live+0x100000,{0x201c0})==CELL_EINVAL);
 assert(std::all_of(vm::memory.begin()+0x201c0,vm::memory.begin()+0x201d8,[](u8 b){return b==0x5a;}));
 assert(sys_memory_get_page_attribute(worker,live+0xffffc,{0x201c0})==CELL_OK);
 assert(vm::read64(0x201c0)==0x40000 && vm::read64(0x201c8)==15 && vm::read32(0x201d0)==0x100000 && vm::read32(0x201d4)==0);
 assert(sys_memory_free(worker,live)==CELL_OK);worker.check_state();restored(worker,peer);
 for(fault_mode_stats=1;fault_mode_stats<=5;fault_mode_stats++) {
  populate(worker,peer,program);
  try {callWithTLS(&worker,0x50000,&program);assert(false);}
  catch(const std::runtime_error& e) {assert(std::string(e.what()).find("time/memory/yield outputs/history")!=std::string::npos);}
  restored(worker,peer);assert(vm::live_heap.empty() && !g_fxo->get<lv2_memory_container>().used.load());
 }
 fault_mode_stats=0;
 // Preserve a nondefault statistics cache on both return and throw.
 for(bool throwing:{false,true}) {
  populate(worker,peer,program);auto& stats=g_fxo->get<last_reported_memory_stats>().body;
  stats={123,456};
  auto mutateStats=+[](ppu_thread*,void* value)->int {
   g_fxo->get<last_reported_memory_stats>().body={9,10};
   if(*static_cast<bool*>(value))throw std::runtime_error("injected stats failure");
   return -77;
  };
  try {assert(armsx3_ios_memory_stats_probe_and_call(&worker,mutateStats,&throwing)==-77);assert(!throwing);}
  catch(const std::runtime_error&) {assert(throwing);}
  const auto v=stats.load();assert(v.prev_total==123 && v.prev_avail==456);stats=last_reported_memory_stats::inner_body{};restored(worker,peer);
 }
 // Additional IDM containers would change reported total: reject that scope.
 populate(worker,peer,program);auto& registry=g_fxo->get<ContainerMap>();
 registry.vec_data[3]=std::make_shared<lv2_memory_container>(0x10000);
 assert(armsx3_ios_memory_stats_probe_and_call(&worker,+[](ppu_thread*,void*){assert(false);return 0;},nullptr)==-4);
 registry.vec_data[3].reset();restored(worker,peer);
 // Corrupted guest timebase outputs must fail and restore scheduler state.
 for(fault_mode=1;fault_mode<=5;fault_mode++) {
  populate(worker,peer,program);
  try {callWithTLS(&worker,0x50000,&program);assert(false);}
  catch(const std::runtime_error& e) {assert(std::string(e.what()).find("MFTB full/upper/full")!=std::string::npos);}
  restored(worker,peer);
 }
 fault_mode=0;
 // Wrong word snapshots, endian subloads and heap store byte order must fail.
 for(fault_mode=6;fault_mode<=10;fault_mode++) {
  populate(worker,peer,program);
  try {callWithTLS(&worker,0x50000,&program);assert(false);}
  catch(const std::runtime_error& e) {assert(std::string(e.what()).find("time/memory/yield outputs/history")!=std::string::npos);}
  restored(worker,peer);
  assert(vm::live_heap.empty() && !g_fxo->get<lv2_memory_container>().used.load());
 }
 fault_mode=0;
 // Guest allocation ENOMEM takes the real fixture's branch without heap access.
 populate(worker,peer,program);vm::guest_allocation_failure=true;
 try {callWithTLS(&worker,0x50000,&program);assert(false);}
 catch(const std::runtime_error& e) {assert(std::string(e.what()).find("time/memory/yield outputs/history")!=std::string::npos);}
 vm::guest_allocation_failure=false;restored(worker,peer);
 assert(worker.guest_steps==106 && vm::guest_heap_reads==0 && vm::guest_heap_writes==0);
 assert(vm::live_heap.empty() && !g_fxo->get<lv2_memory_container>().used.load());
 // Allocation failure at the null-output check is rejected without retained charge.
 populate(worker,peer,program);vm::allocation_failure=true;
 try {callWithTLS(&worker,0x50000,&program);assert(false);}
 catch(const std::runtime_error& e) {assert(std::string(e.what()).find("allocation boundary/null output")!=std::string::npos);}
 vm::allocation_failure=false;restored(worker,peer);
 assert(vm::live_heap.empty() && !g_fxo->get<lv2_memory_container>().used.load() && !s_ios_memory_probe_active);
 // Leaked successful allocations are recovered for returned errors and thrown exceptions.
 for(bool throwing:{false,true}) {
  populate(worker,peer,program);
  auto leak=+[](ppu_thread* p,void* value)->int {
   assert(sys_memory_allocate(*p,0x10000,0x200,{0x20010})==CELL_OK);
   if(*static_cast<bool*>(value))throw std::runtime_error("injected memory failure");
   return -77;
  };
  try {assert(armsx3_ios_memory_probe_and_call(&worker,leak,&throwing)==-77);assert(!throwing);}
  catch(const std::runtime_error&) {assert(throwing);}
  assert(vm::live_heap.empty() && !g_fxo->get<lv2_memory_container>().used.load() && !s_ios_memory_probe_active);
 }
 // Successful callback retaining a charge is rejected, then recovered.
 populate(worker,peer,program);
 auto retained=+[](ppu_thread* p,void*) {assert(sys_memory_allocate(*p,0x10000,0x200,{0x20010})==CELL_OK);return 1;};
 assert(armsx3_ios_memory_probe_and_call(&worker,retained,nullptr)==-5);
 assert(vm::live_heap.empty() && !g_fxo->get<lv2_memory_container>().used.load());
 // Nested memory scopes are rejected before touching allocations.
 auto nested_memory=+[](ppu_thread* p,void*) {assert(armsx3_ios_memory_probe_and_call(p,+[](ppu_thread*,void*){return 1;},nullptr)==-2);return 1;};
 assert(armsx3_ios_memory_probe_and_call(&worker,nested_memory,nullptr)==1);
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
  s_ios_ppu_syscall_probe->counts[1]=1;s_ios_ppu_syscall_probe->counts[25]=1;
  assert(sys_ppu_thread_yield(*p)==CELL_CANCEL && sys_ppu_thread_yield(*p)==CELL_CANCEL);p->check_state();s_ios_ppu_syscall_probe->counts[43]=2;s_ios_ppu_syscall_probe->counts[145]=3;s_ios_ppu_syscall_probe->counts[147]=1;s_ios_ppu_syscall_probe->counts[348]=5;s_ios_ppu_syscall_probe->counts[349]=2;s_ios_ppu_syscall_probe->counts[352]=3;s_ios_ppu_syscall_probe->counts[351]=4;s_ios_ppu_syscall_probe->counts[46]=2;s_ios_ppu_syscall_probe->counts[47]=5;
  s_ios_ppu_syscall_probe->counts[48]=2;s_ios_ppu_syscall_probe->counts[6]=1;return 35;};
 auto negative=+[](ppu_thread* p,void*) {lv2_obj::set_priority(*p,1200);return -77;};
 auto throwing=+[](ppu_thread* p,void*) ->int {lv2_obj::set_priority(*p,1200);throw std::runtime_error("injected");};
 populate(worker,peer,program);
 assert(lv2_obj::ios_probe_scheduler_process_sdk_and_call(&worker,&peer,negative,nullptr)==-77);restored(worker,peer);
 populate(worker,peer,program);
 try {lv2_obj::ios_probe_scheduler_process_sdk_and_call(&worker,&peer,throwing,nullptr);assert(false);}catch(const std::runtime_error&) {} restored(worker,peer);
 auto wrong_counts=+[](ppu_thread*,void*) {return 35;};
 populate(worker,peer,program);
 assert(lv2_obj::ios_probe_scheduler_process_sdk_and_call(&worker,&peer,wrong_counts,nullptr)==-3);restored(worker,peer);
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
  assert(lv2_obj::ios_probe_scheduler_process_sdk_and_call(&worker,&peer,mutate,&state)==-5);restored(worker,peer);
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
  assert(lv2_obj::ios_probe_scheduler_process_sdk_and_call(&worker,&peer,count_calls,nullptr)<0);
  assert(!lv2_obj::g_ppu && !worker.next_ppu && !peer.next_ppu && !s_ios_ppu_syscall_probe);
  g_cfg.core.ppu_threads=2;g_scheduler_ready=false;lv2_obj::g_pending=0;
 }
 populate(worker,peer,program);
 auto nested=+[](ppu_thread* p,void* u) {auto* peer=static_cast<ppu_thread*>(u);
  assert(lv2_obj::ios_probe_scheduler_process_sdk_and_call(p,peer,+[](ppu_thread*,void*){return 0;},nullptr)==-2);return -88;};
 assert(lv2_obj::ios_probe_scheduler_process_sdk_and_call(&worker,&peer,nested,&peer)==-88);restored(worker,peer);
 // Admission retains FIFO for equal priorities in unchanged production awake.
 populate(worker,peer,program);peer.prio.value.prio=1100;
 assert(lv2_obj::awake(&worker) && lv2_obj::awake(&peer));assert(lv2_obj::g_ppu==&worker && worker.next_ppu==&peer);
 lv2_obj::unqueue(lv2_obj::g_ppu,&worker,&ppu_thread::next_ppu);lv2_obj::unqueue(lv2_obj::g_ppu,&peer,&ppu_thread::next_ppu);

 // Missing time calls reject and restore the actual scheduler scope.
 for(u32 code:{1u,25u,145u,147u,348u,349u,351u,352u}) {
  populate(worker,peer,program);
  struct Missing {u32 code;int(*fill)(ppu_thread*,void*);} missing{code,count_calls};
  auto omit=+[](ppu_thread* p,void* value){auto& m=*static_cast<Missing*>(value);m.fill(p,nullptr);--s_ios_ppu_syscall_probe->counts[m.code];return 44;};
  assert(lv2_obj::ios_probe_scheduler_process_sdk_and_call(&worker,&peer,omit,&missing)==-3);restored(worker,peer);
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
 for(u32 policy:{0u,1u,2u,3u,4u,5u,6u,7u,8u,9u}) {
  populate(worker,peer,program);
  auto counts=+[](ppu_thread*,void* value) {
   const u32 policy=*static_cast<u32*>(value);
   auto& c=s_ios_ppu_syscall_probe->counts;c[46]=2;c[6]=1;
   c[policy?48:49]=policy>=2?2:1;
   if(policy)c[47]=policy>=2?5:3;
   if(policy>=3)c[43]=2;
   if(policy>=4){c[145]=3;c[147]=1;}
   if(policy>=5){c[348]=5;c[349]=2;}
   if(policy>=6){c[352]=3;}
   if(policy>=7){c[351]=policy>=8?4:2;}
   if(policy==9){c[1]=1;c[25]=1;}
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
 std::cout<<"PASS: P49 guest PID/ELF SDK publication and output/history, three process corruptions, SDK scope normal/error/throw/mutation/nested/guard restoration; live/freed SC351 ABI/results/history, eleven page corruption rejections, null-output and last-word/out-of-range boundaries, all ten count policies; production user1m location/flags, full 1 MiB heap/canaries, availability 1 MiB/0/1 MiB, oversized ENOMEM before VM allocation; exact production IDM select, missing-registry initialization regression and initialization failure, fresh and retained empty maps, sparse extra-container rejection; full production queue/priority/service/fast_call bodies, exact P49 callback, loaded guest opcode execution, real current-time/frequency and MFTB handlers/clock body, carry/scaling/offset semantics, five corrupt timebase rejections, actual SC352 user memory report and allocation/free/accounting bodies, three availability snapshots, five statistics corruptions and cache restoration, first/last heap word writes and reads, big-endian byte/halfword loads, guard branch on ENOMEM, five corrupt heap output/store rejections and canaries, null outputs, yield FIFO/tail, histories and rollback/guards\n";
}
'''
with tempfile.TemporaryDirectory(prefix='p49-process-') as temp:
    source = Path(temp) / 'regression.cpp'
    binary = Path(temp) / 'regression'
    source.write_text(shims + production + transport + checks)
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                    '-fno-exceptions', '-fexceptions', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', '-g', str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

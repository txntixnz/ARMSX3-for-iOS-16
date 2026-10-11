#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>
#include <cassert>
#define __APPLE__ 1
#define TARGET_OS_IPHONE 1
using u8=uint8_t;using u16=uint16_t;using u32=uint32_t;using u64=uint64_t;
using s32=int32_t;using s64=int64_t;
template<class T> struct be_t {T bytes{};operator T() const {return __builtin_bswap32(bytes);}be_t& operator=(T x){bytes=__builtin_bswap32(x);return *this;}be_t()=default;be_t(T x){*this=x;}};
std::vector<std::string> logs;
void ARMSX3StartupLog(const char* s){logs.emplace_back(s);}
enum class ppu_decoder_type {_static,llvm};enum class thread_scheduler_mode {os,native};
template<class T>struct setting {T value{};T get()const{return value;}void set(T v){value=v;}operator T()const{return value;}};
struct {struct {setting<bool> ppu_prof{true},spu_prof{true},spu_debug{true};setting<thread_scheduler_mode> thread_scheduler{thread_scheduler_mode::native};setting<ppu_decoder_type> ppu_decoder{ppu_decoder_type::llvm};u32 ppu_threads=2;}core;}g_cfg;
struct {bool stopped=true;bool IsStopped()const{return stopped;}} Emu;
enum class cpu_flag:u32{stop=1,exit=2,suspend=4,memory=8,wait=16,ret=32};
u32 operator+(cpu_flag a,cpu_flag b){return u32(a)|u32(b);}u32 operator+(u32 a,cpu_flag b){return a|u32(b);}
struct flags {std::atomic<u32>bits{0};void operator+=(cpu_flag f){bits.fetch_or(u32(f));}void operator-=(u32 f){bits.fetch_and(~f);}u32 operator&(cpu_flag f)const{return bits.load()&u32(f);}explicit operator bool()const{return bits.load()!=0;}void notify_one(){}};
struct ppu_thread;
struct ppu_opcode_t{u32 opcode;};
struct ppu_intrp_func;
using ppu_intrp_func_t=void(*)(ppu_thread&,ppu_opcode_t,be_t<u32>*,ppu_intrp_func*);
struct ppu_intrp_func{ppu_intrp_func_t fn=nullptr;};
ppu_intrp_func ppu_ret;
namespace id_manager{thread_local u32 g_id=0;}
namespace vm {
 enum addr_t:u32 {};constexpr u32 main=0,page_readable=1,page_writable=2,page_executable=4;
 std::array<u8,0x90000>memory{};alignas(8) std::array<u8,0x100000>exec{};
 u8*g_base_addr=memory.data();u8*g_exec_addr=exec.data();constexpr u32 g_exec_addr_seg_offset=0x80000;
 std::array<bool,8>allocated{};bool executable=false;u32 fail_alloc=0,alloc_calls=0;
 void init(){memory.fill(0);exec.fill(0);allocated.fill(false);executable=false;alloc_calls=0;}
 void close(){allocated.fill(false);executable=false;}
 bool reserve_map(u32,u32 addr,u32 size){return addr==0x10000&&size==0x80000;}
 u32 alloc(u32 size,u32,u32 align=0x10000){
  assert((size==0x10000||size==0x40000)&&align==0x10000);if(++alloc_calls==fail_alloc)return 0;
  unsigned pages=size/0x10000;
  for(unsigned i=0;i+pages<=allocated.size();i++){
   bool free=true;for(unsigned j=0;j<pages;j++)free&=!allocated[i+j];if(!free)continue;
   for(unsigned j=0;j<pages;j++)allocated[i+j]=true;
   const u32 address=0x10000+i*0x10000;std::memset(memory.data()+address,0,size);return address;
  }return 0;
 }
 u32 dealloc(u32 addr,u32){unsigned i=(addr-0x10000)/0x10000;if(i>=8||!allocated[i])return 0;
  unsigned pages=addr==0x50000?4:1;for(unsigned j=0;j<pages;j++)allocated[i+j]=false;return pages*0x10000;
 }
 bool check_addr(u32 addr,u32 flags=0,u32 size=1){
  if(addr<0x10000||addr+size>0x90000)return false;
  for(unsigned i=(addr-0x10000)/0x10000;i<=(addr+size-1-0x10000)/0x10000;i++)if(!allocated[i])return false;
  return !(flags&page_executable)||executable;
 }
 void temporary_unlock(ppu_thread&);

 void*base(u32 addr){return memory.data()+addr;}const void*get_super_ptr(u32 addr){return base(addr);}
 u32 read32(u32 addr){return *reinterpret_cast<be_t<u32>*>(memory.data()+addr);}
 void write32(u32 addr,u32 x){*reinterpret_cast<be_t<u32>*>(memory.data()+addr)=x;}
}
namespace utils{u32 decommits=0;void memory_decommit(u8*,u32 size){assert(size==0x8000);++decommits;}void apple_jit_write_protect(bool){}}
struct cpu_thread{static inline std::atomic<u64>g_threads_created{0},g_threads_deleted{0},live{0};static inline thread_local cpu_thread*current=nullptr;virtual~cpu_thread()=default;};
void*get_current_cpu_thread(){return cpu_thread::current;}
namespace thread_ctrl{void*get_current(){return cpu_thread::current;}}
u64 armsx3_ios_live_cpu_threads();
struct ppu_thread_params{vm::addr_t stack_addr;u32 stack_size,tls_addr;struct opd{u32 addr=0,toc=0;}entry;u64 arg0,arg1;};
constexpr u32 ppu_stack_start_offset=0x70;
enum class ppu_cmd{ptr_call};
struct cmd64{u64 value=0;cmd64(ppu_cmd,u32){}cmd64(u64 x):value(x){}};
extern unsigned fault,construct_calls;
struct ppu_thread:cpu_thread {
 static constexpr u32 id_base=0x1000000;u32 id=0,cia=0,stack_addr,stack_size;u64 gpr[32]{},ctr=0,lr=0;
 flags state;std::atomic<u32>cmd_notify{0};struct{u64 index=0;}syscall_history;
 bool interrupt_thread_executing=false;int hv_ctx=0;ppu_intrp_func_t command=nullptr;
 ppu_thread(const ppu_thread_params&p,const char*,u32):stack_addr(p.stack_addr),stack_size(p.stack_size){id=id_manager::g_id;gpr[1]=stack_addr+stack_size-ppu_stack_start_offset;gpr[13]=p.tls_addr;if(fault==9 && id==id_base+1)gpr[13]^=1;state.bits=u32(cpu_flag::stop);}
 void cmd_list(std::initializer_list<cmd64>list){if((fault==4 && construct_calls==6 && id==id_base+1)||(fault==7 && construct_calls==1)||(fault==8 && construct_calls==2))throw std::runtime_error("queue publication failure");assert(list.size()==2);command=std::bit_cast<ppu_intrp_func_t>(list.begin()[1].value);}
 bool check_state(){return test_stopped();}bool test_stopped(){return state.bits.load()&(u32(cpu_flag::stop)|u32(cpu_flag::exit));}
 void exec_task();
};
void gv_zeroupper(){}void ppu_gateway(ppu_thread*){assert(false);}
unsigned fault=0;unsigned construct_calls=0;std::atomic<unsigned>callback_calls{0};
u64 armsx3_ios_live_cpu_threads(){const auto live=cpu_thread::live.load();return fault==5 && callback_calls==2 && live==2 ? 1u : live;}
void assert_dispatch_clear();
void instruction(ppu_thread&c,ppu_opcode_t op,be_t<u32>*,ppu_intrp_func*){
 if(fault==6)throw std::runtime_error("injected instruction failure");
 const u32 x=op.opcode,type=x>>26,rt=(x>>21)&31,ra=(x>>16)&31;const s32 imm=int16_t(x&0xffff);const u32 pc=c.cia;c.cia+=4;
 switch(type){
 case 14:c.gpr[rt]=(ra?c.gpr[ra]:0)+imm;break;
 case 31:assert(x==0x7c8903a6);c.ctr=c.gpr[4];break;
 case 16:assert(x==0x4200fffc);if(--c.ctr)c.cia=pc+int16_t(x&0xfffc);break;
 case 36:vm::write32(u32(c.gpr[ra]+imm),u32(c.gpr[rt]));if(fault==3)vm::write32(0x20108,1);if(fault==10)vm::write32(0x10100,1);if(fault==11 && ra==13)vm::write32(0x500dc,0xdecafbad);break;
 case 32:c.gpr[rt]=vm::read32(u32(c.gpr[ra]+imm));if(fault==2)c.gpr[rt]^=1;break;
 case 24:c.gpr[ra]=c.gpr[rt]|(x&0xffff);break;
 default:assert(false);
 }
 // Force opportunities for interleaved fetches while using the real thread-local
 // production budget/range boundary; this is not native PPU instruction execution.
 std::this_thread::yield();
}
struct ppu_interpreter_rt{ppu_intrp_func_t decode(u32){return instruction;}};
struct Fxo{ppu_interpreter_rt interpreter;bool available=true;bool is_init(){return available;}template<class T>bool is_init(){return available;}template<class T>bool init(){return available;}template<class T>T&get(){return interpreter;}}fxo;
auto*g_fxo=&fxo;
void ppu_register_range(u32 begin,u32 size){assert(begin==0x10000&&size==48);vm::executable=true;}
void ppu_register_function_at(u32 begin,u32 size,void*){for(u32 off=0;off<size;off+=4){auto*p=reinterpret_cast<ppu_intrp_func*>(vm::g_exec_addr+u64(begin+off)*2);p->fn=instruction;}}
namespace stx{struct launch_retainer{};}
enum class thread_state{created};
template<class T>struct named_thread:T{
 std::thread thread;
 named_thread(stx::launch_retainer,const ppu_thread_params&p,const char*n,u32 priority):T(p,n,priority){++construct_calls;if(fault==12 && construct_calls==2)throw std::runtime_error("peer constructor failure");cpu_thread::g_threads_created++;}
 ~named_thread(){if(thread.joinable())thread.join();}
 named_thread&operator=(thread_state){assert(!thread.joinable());thread=std::thread([this]{cpu_thread::current=this;cpu_thread::live++;if(!this->test_stopped()){
    callback_calls++;this->command(*this,{0},nullptr,nullptr);
   }assert_dispatch_clear();cpu_thread::live--;cpu_thread::g_threads_deleted++;cpu_thread::current=nullptr;});return*this;}
 void operator()(){if(thread.joinable())thread.join();}
};
namespace ppu_instructions {
 namespace implicts{}
 constexpr u32 dform(u32 op,u32 rt,u32 ra,s32 imm){return(op<<26)|(rt<<21)|(ra<<16)|(u32(imm)&0xffff);}
 u32 LI(u32 rt,s32 n){return dform(14,rt,0,n);}u32 MTCTR(u32 rt){return(31u<<26)|(rt<<21)|(9u<<16)|(467u<<1);}
 u32 ADDI(u32 rt,u32 ra,s32 n){return dform(14,rt,ra,n);}u32 BC(u32 bo,u32 bi,s32 n){return dform(16,bo,bi,n&~3);}
 u32 STW(u32 rt,u32 ra,s32 n){return dform(36,rt,ra,n);}u32 LWZ(u32 rt,u32 ra,s32 n){return dform(32,rt,ra,n);}
 u32 ORI(u32 rt,u32 ra,u32 n){return dform(24,rt,ra,n);}
}

namespace vm{void temporary_unlock(ppu_thread&){}}
template<class T>using atomic_t=std::atomic<T>;
void ensure(bool value){if(!value)throw std::runtime_error("ensure failure");}
struct {template<class...T>void error(const char*,T...){}} sysPrxForUser;

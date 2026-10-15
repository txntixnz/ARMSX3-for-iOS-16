"""Reproduce Build116's SPU entry abort with actual native cpu_task/old_interpreter.
The native loops and Apple boundary are real. CPU/storage/state/decoder-table,
logging, group, JIT gateway and platform interfaces are explicit host models.
"""
from pathlib import Path
import subprocess,sys,tempfile
from test_jit_lifecycle import arena_cpp,prelude,target_header
PIN='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
root=Path(__file__).resolve().parent.parent
ADDITION='''#if TARGET_OS_IOS
\t// Static interpretation does not execute mutable generated code. A JIT
\t// instance or any other decoder still requires the real Apple boundary.
\tif (jit || g_cfg.core.spu_decoder != spu_decoder_type::_static)
#endif
\t{
\t\tutils::apple_jit_write_protect(true);
\t}'''

def patched_source(native):
 paths=['rpcs3/Emu/Cell/SPUThread.cpp','rpcs3/Emu/Cell/SPUCommonRecompiler.cpp']
 patches=sorted(p for p in (root/'patches').glob('*.patch') if int(p.name[:4])<=53)
 assert [p.name[:4] for p in patches]==[f'{n:04d}' for n in range(1,54)]
 with tempfile.TemporaryDirectory(prefix='armsx3-spu-entry-source-') as temp:
  temp=Path(temp)
  for rel in paths:
   path=temp/rel;path.parent.mkdir(parents=True,exist_ok=True)
   path.write_bytes(subprocess.check_output(['git','-C',str(native),'show',PIN+':'+rel]))
  options=[f'--include={p}' for p in paths]
  for patch in patches[:-1]:subprocess.run(['git','apply',*options,str(patch)],cwd=temp,check=True)
  before=(temp/paths[0]).read_text()
  subprocess.run(['git','apply','--check',str(patches[-1])],cwd=temp,check=True)
  subprocess.run(['git','apply',str(patches[-1])],cwd=temp,check=True)
  after=(temp/paths[0]).read_text();common=(temp/paths[1]).read_text()
 assert after.count(ADDITION)==1
 assert after.replace(ADDITION,'\tutils::apple_jit_write_protect(true);')==before,'SPU behavior changed outside entry guard'
 def task(s):return s[s.index('void spu_thread::cpu_task()'):s.index('\nvoid spu_thread::cpu_work()')]
 interpreter=common[common.index('void spu_recompiler_base::old_interpreter('):common.index('\nstd::vector<u32> spu_thread::discover_functions(')]
 # Static entry and the actual interpreter continuation contain no other Apple
 # protection calls. All mutable-code gates elsewhere remain unchanged.
 assert task(after).count('apple_jit_write_protect')==1
 assert 'apple_jit_write_protect' not in interpreter
 return task(after),task(before),interpreter

model=r'''
#include <atomic>
#include <bit>
#include <cfenv>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
using u32=std::uint32_t;using namespace std::string_view_literals;
template<class T>using shared_ptr=std::shared_ptr<T>;
template<class T>struct be_t{std::array<u8,sizeof(T)>bytes{};operator T()const{T v=0;for(auto b:bytes)v=(v<<8)|b;return v;}void set(T v){for(unsigned i=0;i<sizeof(T);++i)bytes[sizeof(T)-1-i]=u8(v>>(8*i));}};
enum class spu_decoder_type{_static,dynamic,asmjit,llvm};
struct{struct{spu_decoder_type spu_decoder=spu_decoder_type::_static;}core;}g_cfg;
enum class spu_type{threaded,raw,isolated};enum class cpu_flag{stop=1};
struct State{u32 value=0;explicit operator bool()const{return value!=0;}State operator-(cpu_flag f)const{return {value&~u32(f)};}};
bool is_stopped(State s){return bool(s);}
template<class T>void ensure(const T&v){if(!v)throw std::runtime_error("native ensure");}
namespace fmt{template<class...T>std::string format(const char*,T&&...){return "host-SPU";}template<class...T>[[noreturn]]void throw_exception(const char*,T&&...){throw std::runtime_error("native decoder rejection");}}
struct Log{struct Method{template<class...T>void operator()(const char*,T...)const{}}warning,notice,trace;}spu_log;
struct Counter{std::atomic<u32>value{0},notifications{0};void operator++(int){value++;}u32 exchange(u32 v){return value.exchange(v);}void notify_all(){notifications++;}};
struct Group{std::string name="PrimaryCellSpursKernelGroup";std::array<std::array<u32,2>,6>args{};std::array<unsigned,6>threads_map{0,1,2,3,4,5};std::array<int*,6>threads{};unsigned stop_count=0;Counter spurs_running;Group(){for(auto&a:args)a[1]=0x1000;}};
std::atomic<unsigned>host_names{0},host_denormals{0};
namespace thread_ctrl{template<class A,class B>void set_name(A&,B&){host_names++;}}
namespace vm{bool check_addr(u32 addr){return addr==0x1000;}}
void gv_set_zeroing_denormals(){host_denormals++;}
struct Name{shared_ptr<std::string>text=std::make_shared<std::string>("host");bool is_equal(const shared_ptr<std::string>&v)const{return v==text;}template<class F>void peek_op(F f){f(text);}};
struct spu_block_hash_short{u64 value;};template<class T>struct atomic_storage{static T load(const T&v){return v;}};
enum{spu_at_loop_top,spu_at_check_state,spu_at_stop_signal,spu_at_gateway_enter,spu_at_gateway_exit};
struct spu_thread{
 bool jit=false,interrupts=false,allow_interrupts_in_cpu_work=false,unsavable=false,interp_fallback=false;
 u32 pc=0,spurs_addr=0,index=0,lv2_id=0,interp_fallback_begin=0,interp_fallback_end=0;
 u64 start_time=99,block_hash=0,block_counter=0,block_failure=0,dbg_loops=0;
 int dbg_where=0,thread_name=0;unsigned checks=0,decoded=0,gateway_calls=0,accumulator=0;
 State state;Group*group=nullptr;spu_type type=spu_type::raw;Name spu_tname;
 struct Status{u32 npc=0;Status load()const{return *this;}}status_npc;
 std::array<be_t<u32>,0x10000>local{};
 spu_type get_type()const{return type;}void set_interrupt_status(bool on){interrupts=on;}
 bool check_state(){++checks;return bool(state);}
 bool stop_and_signal(u32){state.value=1;return true;}
 template<class T>T*_ptr(u32 off){return reinterpret_cast<T*>(reinterpret_cast<u8*>(local.data())+off);}
 template<class T>T&_ref(u32 off){return *_ptr<T>(off);}
 void cpu_task();
};
thread_local spu_thread*host_current=nullptr;
spu_thread*get_current_cpu_thread(){return host_current;}
thread_local std::string(*g_tls_log_prefix)()=nullptr;
namespace spu_runtime{using Function=void(*)(spu_thread&,void*,u8*);void host_gateway(spu_thread&s,void*,u8*){++s.gateway_calls;s.state.value=1;}Function g_gateway=host_gateway,g_interpreter=nullptr;}
struct spu_opcode_t{u32 opcode;};
bool host_instruction(spu_thread&s,spu_opcode_t op){
 assert(s.allow_interrupts_in_cpu_work);assert(g_tls_log_prefix&&g_tls_log_prefix()=="host-SPU");++s.decoded;
 if(op.opcode==0x10000001){s.accumulator++;return true;}
 if(op.opcode==0x10000002){s.accumulator+=2;return true;}
 if(op.opcode==0x20000000){s.pc=16;return false;}
 assert(op.opcode==0xff000000);s.state.value=1;return true;
}
struct spu_interpreter_rt{auto decode(u32)const{return host_instruction;}};
struct Fxo{template<class T>T&get(){static T t;return t;}}host_fxo;auto*g_fxo=&host_fxo;
struct spu_recompiler_base{static void old_interpreter(spu_thread&,void*,u8*);};
'''

tests=r'''
#include "immutable_jit.hpp"
int main(int argc,char**argv){
 assert(argc==2);rlimit limit{0,0};assert(setrlimit(RLIMIT_CORE,&limit)==0);
 const std::string scenario=argv[1];
 if(scenario=="dynamic")g_cfg.core.spu_decoder=spu_decoder_type::dynamic;
 if(scenario=="asmjit")g_cfg.core.spu_decoder=spu_decoder_type::asmjit;
 if(scenario=="llvm")g_cfg.core.spu_decoder=spu_decoder_type::llvm;
 const bool jit=scenario=="static-jit"||scenario=="asmjit"||scenario=="llvm";
 const bool static_loop=g_cfg.core.spu_decoder==spu_decoder_type::_static&&!jit;
 spu_runtime::g_interpreter=static_loop?spu_recompiler_base::old_interpreter:spu_runtime::host_gateway;
 asmjit::CodeHolder code;const auto*rx=utils::publish_immutable_jit(code,16);assert(rx);
 const auto immutable=std::vector<u8>(static_cast<const u8*>(rx),static_cast<const u8*>(rx)+code.codeSize());
 const auto immutable_call=reinterpret_cast<int(*)()>(const_cast<void*>(rx));assert(immutable_call()==42);
 auto run=[&](spu_thread&s){host_current=&s;s.cpu_task();assert(std::fegetround()==FE_TOWARDZERO);assert(immutable_call()==42);host_current=nullptr;};
 unsigned tasks=0;
 for(unsigned cycle=0;cycle<8;++cycle){
  Group primary,secondary;secondary.name="SecondaryCellSpursKernelGroup";
  std::array<int,6>owners{};for(unsigned i=0;i<6;++i){primary.threads[i]=&owners[i];secondary.threads[i]=&owners[i];}
  std::vector<std::unique_ptr<spu_thread>>cpus;std::vector<std::thread>threads;
  for(unsigned i=0;i<6;++i){
   auto p=std::make_unique<spu_thread>();p->jit=jit;p->type=spu_type::threaded;p->group=i<5?&primary:&secondary;p->index=i;
   p->status_npc.npc=0x80000001;p->local[0].set(0x10000001);p->local[1].set(0x10000002);p->local[2].set(0x20000000);p->local[4].set(0xff000000);
   cpus.push_back(std::move(p));
  }
  // Match the six concurrently-created SPURS threads on the Build116 phone.
  // The non-iOS protection recorder is a vector, so run those profiles serially.
  for(auto&p:cpus){
#if defined(__APPLE__) && !TARGET_OS_IOS
   run(*p);
#else
   threads.emplace_back([&,s=p.get()]{run(*s);});
#endif
  }
  for(auto&t:threads)t.join();
  for(auto&p:cpus){++tasks;assert(p->start_time==0&&p->interrupts&&!p->allow_interrupts_in_cpu_work&&p->spurs_addr==0x1000);
   if(static_loop){assert(p->pc==20&&p->decoded==4&&p->accumulator==3&&!p->gateway_calls&&p->checks==2);}
   else{assert(!p->decoded&&p->gateway_calls==1&&p->checks==1);}
  }
  assert(primary.spurs_running.value==0&&secondary.spurs_running.value==0);
  // Raw/isolated SPUs and pre-stopped entries use the same native entry guard.
  for(auto type:{spu_type::raw,spu_type::isolated}){
   auto p=std::make_unique<spu_thread>();p->jit=jit;p->type=type;p->state.value=1;p->status_npc.npc=0x40002;
   run(*p);++tasks;assert(p->pc==0&&!p->interrupts&&p->checks==1&&!p->decoded&&!p->gateway_calls&&!p->allow_interrupts_in_cpu_work);
  }
  assert(immutable_call()==42&&std::equal(immutable.begin(),immutable.end(),static_cast<const u8*>(rx)));
 }
 assert(tasks==64&&host_denormals==64&&host_names==48);
#ifdef __APPLE__
#if TARGET_OS_IOS
 assert(jit_metrics.write_protection.empty());
#else
 assert(jit_metrics.write_protection==std::vector<bool>(tasks,true));
#endif
#else
 assert(jit_metrics.write_protection.empty());
#endif
 assert(!jit_metrics.reserves&&!jit_metrics.allocations&&!jit_metrics.resets&&!jit_metrics.decommits);
 std::puts("PASS: actual native SPU cpu_task and old_interpreter loops;64 entries, six-thread groups, PC/interrupt state, decoder routing, stop/flag cleanup and immutable RX bytes; CPU/decoder-table/storage/group/platform interfaces modeled");
}
'''

def main(native):
 fixed,before,interpreter=patched_source(native)
 with tempfile.TemporaryDirectory(prefix='armsx3-spu-entry-') as temp:
  temp=Path(temp)
  def build(name,task,apple=True,ios=True):
   folder=temp/name;folder.mkdir();(folder/'TargetConditionals.h').write_text(target_header(ios))
   source=prelude+('\n#define __APPLE__ 1\n' if apple else '\n')+arena_cpp+model+interpreter+task+tests
   (folder/'host.cpp').write_text(source)
   subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread','-I',str(folder),'-I',str(root/'core'),str(folder/'host.cpp'),'-o',str(folder/'host')],check=True,timeout=180)
   return folder/'host'
  old=build('before',before)
  result=subprocess.run([str(old),'static'],capture_output=True,text=True,timeout=30)
  assert result.returncode<0 and 'pthread_jit_write_protect_np is absent' in result.stderr,result.stderr
  current=build('ios',fixed)
  subprocess.run([str(current),'static'],check=True,timeout=30)
  for mode in ['dynamic','asmjit','llvm','static-jit']:
   result=subprocess.run([str(current),mode],capture_output=True,text=True,timeout=30)
   assert result.returncode<0 and 'pthread_jit_write_protect_np is absent' in result.stderr,(mode,result.stderr)
  for name,apple in [('macos',True),('linux',False)]:
   binary=build(name,fixed,apple,False)
   for mode in ['static','dynamic','asmjit','llvm','static-jit']:subprocess.run([str(binary),mode],check=True,timeout=30)
 print('PASS: Build116 SPU-entry abort reproduced through native cpu_task and real missing-API boundary; iOS static/no-JIT succeeds; all non-static and static-with-JIT entries retain rejection; macOS protection/Linux behavior retained; native SPU scheduling/ISA decoder/backend and ARM gateway execution still require device validation')
if __name__=='__main__':main(Path(sys.argv[1]).resolve())

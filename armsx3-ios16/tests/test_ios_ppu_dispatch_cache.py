"""Exact native PPU dispatch/bounded helper: nesting, stop and TLS access count."""
from pathlib import Path
import os, subprocess, sys, tempfile
root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
path='rpcs3/Emu/Cell/PPUThread.cpp'
pin='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
def function(text,signature):
    start=text.index(signature);opening=text.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
model=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <thread>
#define __APPLE__ 1
#define TARGET_OS_IPHONE 1
using u32=std::uint32_t;using u64=std::uint64_t;
template<class T>struct be_t{T bits{};be_t&operator=(T x){bits=__builtin_bswap32(x);return *this;}operator T()const{return __builtin_bswap32(bits);}};
enum class ppu_decoder_type{_static,llvm};
struct{struct{ppu_decoder_type ppu_decoder=ppu_decoder_type::_static;}core;}g_cfg;
namespace cpu_flag{constexpr u32 ret=1,exit=2;}
struct ppu_thread;struct ppu_opcode_t{u32 opcode;};struct ppu_intrp_func;
using ppu_intrp_func_t=void(*)(ppu_thread&,ppu_opcode_t,be_t<u32>*,ppu_intrp_func*);
struct ppu_intrp_func{ppu_intrp_func_t fn;};ppu_intrp_func ppu_ret{};
namespace vm{alignas(16) unsigned char memory[4096]{},cache[8192]{};auto*g_base_addr=memory;auto*g_exec_addr=cache;}
namespace utils{void apple_jit_write_protect(bool){assert(false);}}
void gv_zeroupper(){}
struct ppu_thread{
 u32 cia=0x100,state=0;u64 hv_ctx=0,executions=0,limit=1000000;
 bool nested=false,throw_now=false;
 bool check_state(){return state&cpu_flag::exit;}bool test_stopped(){return check_state();}
 void exec_task();
};
void ppu_gateway(ppu_thread*p){p->state=cpu_flag::exit;}
/* PROBE */
thread_local ios_ppu_dispatch_probe* probe_pointer=nullptr;
thread_local u64 tls_resolutions=0;
ios_ppu_dispatch_probe*&probe_slot(){++tls_resolutions;return probe_pointer;}
#define s_ios_ppu_dispatch_probe probe_slot()
/* PRODUCTION */
void instruction(ppu_thread&ppu,ppu_opcode_t,be_t<u32>*,ppu_intrp_func*next){
 ++ppu.executions;if(ppu.throw_now)throw std::runtime_error("handler failure");
 if(ppu.nested&&ppu.executions==1){
  auto*const previous=probe_pointer;ppu_thread inner;inner.cia=0x200;
  assert(armsx3_ios_ppu_exec_bounded(&inner,0x200,0x20c,3)==3&&inner.executions==3);
  assert(probe_pointer==previous);
 }
 if(ppu.cia>=0x200){assert(next==&ppu_ret);ppu.cia+=4;}
 if(ppu.executions==ppu.limit)ppu.state=cpu_flag::exit;
}
void prepare(){for(u32 addr=0x100;addr<0x400;addr+=4){
 *reinterpret_cast<be_t<u32>*>(vm::memory+addr)=0x60000000;
 reinterpret_cast<ppu_intrp_func*>(vm::cache+addr*2)->fn=instruction;
}}
void ordinary(){
 tls_resolutions=0;ppu_thread ppu;ppu.exec_task();assert(ppu.executions==1000000&&tls_resolutions==1&&!probe_pointer);
}
int main(){
 prepare();ordinary();std::thread second(ordinary);second.join();
 ppu_thread outer;outer.nested=true;outer.limit=20;outer.exec_task();assert(outer.executions==20&&!probe_pointer);
 ppu_thread bounded;bounded.cia=0x300;bounded.nested=true;
 assert(armsx3_ios_ppu_exec_bounded(&bounded,0x300,0x30c,3)==3&&bounded.executions==3&&!probe_pointer);
 ppu_thread budget;budget.cia=0x200;
 assert(armsx3_ios_ppu_exec_bounded(&budget,0x200,0x210,2)==-2&&budget.executions==2&&!probe_pointer);
 ppu_thread invalid;invalid.cia=0x204;
 assert(armsx3_ios_ppu_exec_bounded(&invalid,0x200,0x208,3)==1&&invalid.executions==1);
 assert(armsx3_ios_ppu_exec_bounded(nullptr,0x200,0x208,3)==-4);
 ppu_thread stopped;stopped.state=cpu_flag::exit;stopped.exec_task();assert(stopped.executions==0);
 ppu_thread failure;failure.cia=0x200;failure.throw_now=true;
 try{armsx3_ios_ppu_exec_bounded(&failure,0x200,0x210,3);assert(false);}catch(const std::runtime_error&){}
 assert(!probe_pointer);ordinary();
 std::puts("PASS: exact native dispatch resolves probe TLS once across one million unbounded iterations; two workers; nested bounded callbacks, budgets/end guards, stop, exception restoration and restart");
}
'''
with tempfile.TemporaryDirectory(prefix='armsx3-ppu-cache-') as temp:
    work=Path(temp);file=work/path;file.parent.mkdir(parents=True)
    file.write_bytes(subprocess.check_output(['git','-C',str(native),'show',pin+':'+path]))
    for patch in sorted((root/'patches').glob('*.patch')):
        subprocess.run(['git','apply','--include='+path,str(patch)],cwd=work,check=True)
    source=file.read_text()
    probe=function(source,'struct ios_ppu_dispatch_probe')+';'
    production=function(source,'void ppu_thread::exec_task()')+'\n'+function(source,'extern "C" int armsx3_ios_ppu_exec_bounded(')
    (work/'test.cpp').write_text(model.replace('/* PROBE */',probe).replace('/* PRODUCTION */',production))
    subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer',str(work/'test.cpp'),'-o',str(work/'test')],check=True)
    subprocess.run([str(work/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})

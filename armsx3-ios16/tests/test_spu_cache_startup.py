"""Reproduce Build115's native SPU startup guard abort and validate static setup.
Use the exact patched native initialize prefix and actual jit_write_guard/Apple
boundary. Cache I/O/recompiler work after the prefix remains an explicit host
interface; the patch validator preserves that entire remainder byte-for-byte.
"""
from pathlib import Path
import os,subprocess,sys,tempfile
from test_jit_lifecycle import arena_cpp,prelude,target_header
PIN='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
root=Path(__file__).resolve().parent.parent
GUARD='''#if defined(__APPLE__) && TARGET_OS_IOS
	// The static interpreter initializes heap dispatcher data only. Keep
	// mutable-code protection for every recompiler/dynamic decoder path.
	std::optional<jit_write_guard> jit_guard;
	if (g_cfg.core.spu_decoder != spu_decoder_type::_static) jit_guard.emplace();
#else
	jit_write_guard jit_guard;
#endif'''

def patched_startup(native):
 paths=['rpcs3/Emu/Cell/SPUCommonRecompiler.cpp','Utilities/JIT.h']
 patches=sorted(p for p in (root/'patches').glob('*.patch') if int(p.name[:4])<=52)
 assert [p.name[:4] for p in patches]==[f'{n:04d}' for n in range(1,53)]
 with tempfile.TemporaryDirectory(prefix='armsx3-spu-cache-source-') as temp:
  temp=Path(temp)
  for rel in paths:
   path=temp/rel;path.parent.mkdir(parents=True,exist_ok=True)
   path.write_bytes(subprocess.check_output(['git','-C',str(native),'show',PIN+':'+rel]))
  options=[f'--include={p}' for p in paths]
  for patch in patches[:-1]:subprocess.run(['git','apply',*options,str(patch)],cwd=temp,check=True)
  before=(temp/paths[0]).read_text();header=(temp/paths[1]).read_text()
  subprocess.run(['git','apply','--check',str(patches[-1])],cwd=temp,check=True)
  subprocess.run(['git','apply',str(patches[-1])],cwd=temp,check=True)
  after=(temp/paths[0]).read_text()
 assert after.count(GUARD)==1
 assert after.replace(GUARD,'\tjit_write_guard jit_guard;')==before,'native cache/worker/dispatcher behavior changed'
 start=after.index('void spu_cache::initialize(bool build_existing_cache)')
 end=after.index('\n\t// SPU cache file (version + block size type)',start)
 old_start=before.index('void spu_cache::initialize(bool build_existing_cache)')
 old_end=before.index('\n\t// SPU cache file (version + block size type)',old_start)
 # Keep the actual guard and original dispatcher/global interpreter/cache-path
 # setup. The unchanged cache-file/worker continuation is a named host model.
 finish='\n host_spu_cache_tail(build_existing_cache);\n}\n'
 guard_start=header.index('#ifdef __APPLE__\nstruct jit_write_guard')
 guard_end=header.index('\n// Build runtime function with asmjit::X86Assembler',guard_start)
 return after[start:end]+finish,before[old_start:old_end]+finish,header[guard_start:guard_end]

model_cpp=r'''
void atomic_fence_acq_rel(){std::atomic_thread_fence(std::memory_order_acq_rel);}
void atomic_fence_seq_cst(){std::atomic_thread_fence(std::memory_order_seq_cst);}
namespace spu_runtime{
using Function=int(*)();
int host_gateway(){return 42;}int host_interpreter(){return 7;}
Function g_gateway=host_gateway,g_interpreter=nullptr;const Function tr_interpreter=host_interpreter;
struct Slot{Function value=nullptr;Function&raw(){return value;}};
std::array<Slot,1<<20>* const g_dispatcher=new std::array<Slot,1<<20>;
}
std::string host_spu_cache_path;
unsigned host_spu_cache_tails=0;bool host_spu_cache_build=false;
namespace rpcs3::cache{std::string get_ppu_cache(){return host_spu_cache_path;}}
void host_spu_cache_tail(bool build){++host_spu_cache_tails;host_spu_cache_build=build;}
class spu_cache{public:static void initialize(bool=true);};
'''
standalone=r'''
#include <atomic>
#include <optional>
#include <string>
#include <sys/wait.h>
#include <unistd.h>
enum class spu_decoder_type{_static,dynamic,asmjit,llvm};
struct{struct{spu_decoder_type spu_decoder=spu_decoder_type::_static;}core;}g_cfg;
'''
tests=r'''
#include "immutable_jit.hpp"
int main(int argc,char**argv){
 assert(argc==2);struct rlimit limit{};assert(setrlimit(RLIMIT_CORE,&limit)==0);
 const std::string scenario=argv[1];
 if(scenario=="dynamic")g_cfg.core.spu_decoder=spu_decoder_type::dynamic;
 if(scenario=="asmjit")g_cfg.core.spu_decoder=spu_decoder_type::asmjit;
 if(scenario=="llvm")g_cfg.core.spu_decoder=spu_decoder_type::llvm;
 asmjit::CodeHolder code;const auto published=utils::publish_immutable_jit(code,16);
 assert(published);spu_runtime::g_gateway=reinterpret_cast<spu_runtime::Function>(published);
 const auto original=std::vector<u8>(static_cast<const u8*>(published),static_cast<const u8*>(published)+code.codeSize());
 for(int cycle=0;cycle<8;++cycle){
  host_spu_cache_path=cycle%2?"host-cache/":"";
  const bool build=cycle%3!=0;const auto before=host_spu_cache_tails;
  std::fill(spu_runtime::g_dispatcher->begin(),spu_runtime::g_dispatcher->end(),spu_runtime::Slot{});
  spu_runtime::g_interpreter=nullptr;spu_cache::initialize(build);
  assert(spu_runtime::g_interpreter==spu_runtime::g_gateway&&spu_runtime::g_interpreter()==42);
  const bool fills=g_cfg.core.spu_decoder==spu_decoder_type::_static||g_cfg.core.spu_decoder==spu_decoder_type::dynamic;
  for(auto&slot:*spu_runtime::g_dispatcher)assert(slot.value==(fills?spu_runtime::tr_interpreter:nullptr));
  assert(host_spu_cache_tails==before+(!host_spu_cache_path.empty()));
  if(!host_spu_cache_path.empty())assert(host_spu_cache_build==build);
  assert(std::equal(original.begin(),original.end(),static_cast<const u8*>(published)));
 }
#if defined(__APPLE__) && !TARGET_OS_IOS
 assert(jit_metrics.write_protection.size()==16);
 for(unsigned i=0;i<16;++i)assert(jit_metrics.write_protection[i]==bool(i%2));
#else
 assert(jit_metrics.write_protection.empty());
#endif
 assert(!jit_metrics.reserves&&!jit_metrics.allocations&&!jit_metrics.resets&&!jit_metrics.decommits);
 std::puts("PASS: native SPU startup prefix; full heap dispatcher/interpreter setup, empty/nonempty cache continuation, build flags, immutable executable bytes and scoped write protection");
}
'''

def main(native):
 fixed,old,guard=patched_startup(native)
 with tempfile.TemporaryDirectory(prefix='armsx3-spu-cache-') as temp:
  temp=Path(temp)
  def build(name,prefix,apple=True,ios=True):
   folder=temp/name;folder.mkdir();(folder/'TargetConditionals.h').write_text(target_header(ios))
   source=prelude+standalone+ ('\n#define __APPLE__ 1\n' if apple else '\n')+arena_cpp+'\n'+model_cpp+'\n'+guard+'\n'+prefix+'\n'+tests
   (folder/'host.cpp').write_text(source)
   subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(folder),'-I',str(root/'core'),str(folder/'host.cpp'),'-o',str(folder/'host')],check=True,timeout=180)
   return folder/'host'
  prior=build('before',old)
  result=subprocess.run([str(prior),'static'],capture_output=True,text=True,timeout=30)
  assert result.returncode<0 and 'pthread_jit_write_protect_np is absent' in result.stderr,result.stderr
  current=build('fixed',fixed)
  subprocess.run([str(current),'static'],check=True,timeout=30)
  for decoder in ['dynamic','asmjit','llvm']:
   result=subprocess.run([str(current),decoder],capture_output=True,text=True,timeout=30)
   assert result.returncode<0 and 'pthread_jit_write_protect_np is absent' in result.stderr,(decoder,result.stderr)
  for name,apple in [('macos',True),('linux',False)]:
   binary=build(name,fixed,apple,False)
   for decoder in ['static','dynamic','asmjit','llvm']:subprocess.run([str(binary),decoder],check=True,timeout=30)
 print('PASS: Build115 static-SPU abort reproduced with actual native guard/Apple boundary; patched iOS data-only startup passes, all3 non-static decoders still reject absent API; native macOS guard pairing/Linux behavior retained; cache I/O/compile continuation is a host model')
if __name__=='__main__':main(Path(sys.argv[1]).resolve())

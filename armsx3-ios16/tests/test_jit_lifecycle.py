"""Exercise native JIT initialize/finalize and real immutable RW-to-RX pages.
The mutable arena backend is a bounded host model. The iOS Apple JIT boundary
uses the actual portability header with the protection symbol absent, matching
the device. macOS/Linux variants verify the original reset/restore paths.
"""
from pathlib import Path
import re,subprocess,sys,tempfile
root=Path(__file__).resolve().parent.parent

def patched_bodies(native):
 source=(Path(native)/'Utilities/JITASM.cpp').read_text()
 # These two call replacements are the exact JITASM changes from patch0003.
 source=source.replace('pthread_jit_write_protect_np(false);','utils::apple_jit_write_protect(false);')
 source=source.replace('pthread_jit_write_protect_np(true);','utils::apple_jit_write_protect(true);')
 with tempfile.TemporaryDirectory(prefix='armsx3-jit-source-') as temp:
  temp=Path(temp);p=temp/'Utilities/JITASM.cpp';p.parent.mkdir();p.write_text(source)
  for name,marker in [('0010-ios-empty-jit-snapshot.patch','Avoid creating it for a zero-length snapshot.'),
                      ('0050-ios-empty-jit-finalize.patch','Finalizing an')]:
   if marker not in p.read_text():
    patch=root/'patches'/name
    subprocess.run(['git','apply','--check',str(patch)],cwd=temp,check=True,capture_output=True)
    subprocess.run(['git','apply',str(patch)],cwd=temp,check=True,capture_output=True)
  source=p.read_text()
 start=source.index('void jit_runtime::initialize()')
 end=source.index('\njit_runtime_base& asmjit::get_global_runtime()',start)
 return source[start:end]

def target_header(ios):
 return '#pragma once\n#define TARGET_OS_IOS '+str(int(ios))+'\n'

arena_cpp=r'''
using u8=std::uint8_t;using u64=std::uint64_t;using usz=std::size_t;using uchar=unsigned char;
struct JitMetrics{unsigned reserves=0,allocations=0,resets=0,decommits=0,protections=0,flushes=0,immutable=0;std::vector<bool>write_protection;}jit_metrics;
struct JitCounter{u64 value=0;u64 load()const{return value;}operator u64()const{return value;}JitCounter&operator=(u64 v){value=v;return *this;}};
static JitCounter s_code_pos,s_data_pos;
static std::vector<u8>s_code_init,s_data_init;
static std::array<u8,0x20000>host_arena{};
static u8*get_jit_memory(){++jit_metrics.reserves;return host_arena.data();}
[[maybe_unused]]struct{template<class...T>void notice(const char*,T...)const{}}jit_log;
namespace utils{
enum class protection{wx,rw};
void memory_reset(void*,usz length,bool exec){assert(length==0x80000000&&exec);++jit_metrics.resets;host_arena.fill(0);}
void memory_decommit(void*,usz length,bool exec){assert(length==0x80000000&&exec);++jit_metrics.decommits;host_arena.fill(0);}
void memory_protect(void*,usz length,protection mode){assert(length==0x40000000&&mode==protection::wx);++jit_metrics.protections;}
}
namespace asmjit{
struct Section{std::vector<u8>bytes{0xb8,42,0,0,0,0xc3};usz offset()const{return 0;}usz bufferSize()const{return bytes.size();}const u8*data()const{return bytes.data();}};
struct CodeHolder{Section section;std::vector<Section*>_sections{&section};int flatten(){return 0;}int resolveUnresolvedLinks(){return 0;}usz codeSize()const{return section.bytes.size();}int relocateToBase(std::uintptr_t){return 0;}};
namespace VirtMem{void flushInstructionCache(void*p,usz n){++jit_metrics.flushes;__builtin___clear_cache(static_cast<char*>(p),static_cast<char*>(p)+n);}}
}
void pthread_jit_write_protect_np(int enabled){jit_metrics.write_protection.push_back(enabled);}
extern "C" void armsx3_record_jit_failure(const char*message){std::fprintf(stderr,"%s\n",message);}
extern "C" void armsx3_record_immutable_jit(usz){++jit_metrics.immutable;}
#ifdef __APPLE__
#include "apple_jit.hpp"
#endif
class jit_runtime{
public:
 static void initialize();static void finalize()noexcept;
 static u8*alloc(usz size,usz alignment,bool exec){++jit_metrics.allocations;get_jit_memory();auto&pos=exec?s_code_pos:s_data_pos;
  if(size){assert(alignment&&size<=0x10000-pos.value);u8*result=host_arena.data()+(exec?0:0x10000)+pos.value;pos.value+=size;return result;}
  return host_arena.data()+(exec?0:0x10000);
 }
};
'''
prelude=r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <sys/resource.h>
#include <sys/mman.h>
'''
tests=r'''
#include "immutable_jit.hpp"
int main(int argc,char**argv){
 rlimit core_limit{0,0};setrlimit(RLIMIT_CORE,&core_limit);
 if(argc>1){
  const auto mode=std::atoi(argv[1]);
  if(mode==1){s_code_pos=1;}
  if(mode==2){s_data_pos=1;}
  if(mode==3){s_code_init={1};}
  if(mode==4){s_data_init={1};}
  if(mode==5){s_code_pos=0x100000000ull;}
  if(mode==6){s_data_pos=0x100000000ull;}
  jit_runtime::finalize();return 0;
 }
#if defined(__APPLE__) && TARGET_OS_IOS
 // Actual immutable publisher, completed x86 return42 function on this host.
 asmjit::CodeHolder code;
 auto*memory=utils::publish_immutable_jit(code,16);
 auto function=reinterpret_cast<int(*)()>(memory);assert(function()==42);
 const auto bytes=code.section.bytes;
 for(unsigned cycle=0;cycle<64;++cycle){jit_runtime::initialize();jit_runtime::finalize();
  assert(function()==42);assert(std::memcmp(memory,bytes.data(),bytes.size())==0);
  assert(s_code_pos.load()==0&&s_data_pos.load()==0&&s_code_init.empty()&&s_data_init.empty());
 }
 assert(jit_metrics.immutable==1&&jit_metrics.reserves==0&&jit_metrics.allocations==0);
 assert(jit_metrics.resets==0&&jit_metrics.decommits==0&&jit_metrics.protections==0&&jit_metrics.write_protection.empty());
#else
 // Startup snapshot persists; post-start allocations must be discarded.
 const std::vector<u8>code{1,2,3,4},data{5,6,7};
 std::memcpy(jit_runtime::alloc(code.size(),1,true),code.data(),code.size());
 std::memcpy(jit_runtime::alloc(data.size(),1,false),data.data(),data.size());
 jit_runtime::initialize();assert(s_code_init==code&&s_data_init==data);
 jit_runtime::alloc(16,1,true);jit_runtime::alloc(16,1,false);host_arena.fill(0xff);
 jit_runtime::finalize();assert(s_code_pos.load()==code.size()&&s_data_pos.load()==data.size());
 assert(std::equal(code.begin(),code.end(),host_arena.begin()));assert(std::equal(data.begin(),data.end(),host_arena.begin()+0x10000));
 assert(host_arena[code.size()]==0&&host_arena[0x10000+data.size()]==0);
 assert(jit_metrics.flushes==1);
#ifdef CAN_OVERCOMMIT
 assert(jit_metrics.resets==1&&jit_metrics.protections==1&&jit_metrics.decommits==0);
#else
 assert(jit_metrics.decommits==1&&jit_metrics.resets==0);
#endif
#ifdef __APPLE__
 assert(jit_metrics.write_protection==std::vector<bool>({false,true}));
#else
 assert(jit_metrics.write_protection.empty());
#endif
#endif
 std::puts("PASS: native JIT lifecycle and immutable page preservation");
}
'''

def main():
 native=Path(sys.argv[1]);bodies=patched_bodies(native)
 guard=re.search(r'(void jit_runtime::finalize\(\) noexcept\n\{\n)(#if defined\(__APPLE__\) && TARGET_OS_IOS\n.*?#endif\n)',bodies,re.S)
 assert guard and 's_code_init.empty() && s_data_init.empty()' in guard[2]
 before=bodies[:guard.start(2)]+bodies[guard.end(2):]
 with tempfile.TemporaryDirectory(prefix='armsx3-jit-lifecycle-') as temp:
  temp=Path(temp)
  for mode,defines,ios in [('ios','#define __APPLE__ 1\n#define ARCH_ARM64 1\n',True),
                           ('mac','#define __APPLE__ 1\n#define ARCH_ARM64 1\n',False),
                           ('linux','#define CAN_OVERCOMMIT 1\n#define ARCH_ARM64 1\n',False),
                           ('before', '#define __APPLE__ 1\n#define ARCH_ARM64 1\n',True)]:
   (temp/'TargetConditionals.h').write_text(target_header(ios))
   (temp/'host.cpp').write_text(prelude+defines+arena_cpp+(before if mode=='before' else bodies)+tests)
   binary=temp/mode
   subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(temp),'-I',str(root/'core'),str(temp/'host.cpp'),'-o',str(binary)],check=True,timeout=180)
   if mode=='before':
    result=subprocess.run([str(binary),'0'],capture_output=True,text=True,timeout=30)
    assert result.returncode!=0 and 'pthread_jit_write_protect_np is absent' in result.stderr
   else:
    subprocess.run([str(binary)],check=True,timeout=30)
    if mode=='ios':
     for fault in range(1,7):
      result=subprocess.run([str(binary),str(fault)],capture_output=True,text=True,timeout=30)
      assert result.returncode!=0 and 'pthread_jit_write_protect_np is absent' in result.stderr
 print('PASS: Build111 cleanup abort reproduced with native Apple boundary; patched iOS initialize/finalize64 cycles preserve real immutable RX code; no mutable reservation/protection/reset/allocation on empty state;6 nonempty counter/snapshot cases remain fail-closed; native macOS/Linux snapshot restore and cache flush retained. Mutable arena backend modeled.')

if __name__=='__main__':main()

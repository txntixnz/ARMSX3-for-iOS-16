"""Check the real diagnostic loader wrapper with host dependencies.

Usage: python test_p40_loader.py PPUModule.before0037.cpp PPUModule.after0037.cpp
Both sources must have prior iOS module patches applied. VM, hash, segment
loader and metadata parsers are substitutes; wrapper bodies are extracted.
"""
from pathlib import Path
import subprocess, tempfile, sys

root = Path(__file__).resolve().parent
if len(sys.argv) == 3:
    sources = [Path(sys.argv[1]), Path(sys.argv[2])]
elif len(sys.argv) == 1:
    sources = [root/'PPUModule.build56.cpp', root/'module-staged/rpcs3/Emu/Cell/PPUModule.cpp']
else:
    raise SystemExit(__doc__)
def function(source):
    start = source.index('extern "C" int armsx3_ios_ppu_load_probe_process_image_segments')
    end = source.index('\n#endif', start)
    return source[start:end]

prelude = r'''
#include <array>
#include <vector>
#include <map>
#include <set>
#include <algorithm>
#include <cstring>
#include <cassert>
#include <cstdint>
#include <cstdio>
using u32=uint32_t;using u64=uint64_t;using u8=uint8_t;
enum class elf_error {ok};enum class ppu_decoder_type {_static};
struct ppu_exec_object {
 struct prog_t {u64 p_type=0,p_vaddr=0,p_memsz=0,p_flags=0,p_filesz=0;std::vector<u8> bin;};
 struct {u64 e_entry=0x20008;} header;
 std::vector<prog_t> progs;
 bool operator!=(elf_error)const{return false;}
};
struct lv2_obj {};struct ppu_interpreter_rt {};
template<class T>struct ppu_module {std::vector<int>segs;std::map<u32,int>addr_to_seg_index;u8 sha1[20]{};};
struct {bool IsStopped(){return true;}} Emu;
struct {struct {ppu_decoder_type ppu_decoder=ppu_decoder_type::_static;} core;}g_cfg;
struct Fxo {bool is_init(){return true;}template<class T>bool is_init(){return true;}} fxo;
auto*g_fxo=&fxo;
namespace vm {
 constexpr u32 page_allocated=1;std::set<u32>allocated;u8 exec[0x20000]{};
 auto*g_exec_addr=exec;constexpr u32 g_exec_addr_seg_offset=0;
 bool check_addr(u32 addr,u32=0,u32=0){return allocated.contains(addr);}
 void dealloc(u32 addr){allocated.erase(addr);}
}
namespace utils {int decommits=0;void memory_decommit(u8*,u32){++decommits;}}
struct sha1_context{};void sha1_starts(sha1_context*){};void sha1_finish(sha1_context*,u8*p){p[0]=42;}
int loader_calls=0,loader_mode=0;
bool ppu_load_exec_segments(const ppu_exec_object&,bool,void*,ppu_module<lv2_obj>&m,bool,u32&size,sha1_context&){
 ++loader_calls;vm::allocated={0x10000,0x20000};m.segs={1,2};m.addr_to_seg_index={{0x10000,0},{0x20000,1}};
 size=loader_mode==2?0:0x20000;return loader_mode!=1;
}
int armsx3_ios_ppu_read_probe_tls_header(const ppu_exec_object::prog_t*p,u32*a,u32*f,u32*m){
 if(p->p_type!=7)return-1;if(p->p_vaddr!=0x20080||p->p_filesz!=9||p->p_memsz!=64)return-3;
 *a=0x20080;*f=9;*m=64;return 0;
}
int armsx3_ios_ppu_read_probe_process_parameters(const ppu_exec_object::prog_t*p,u32*out){
 if(p->p_type!=0x60000001||p->bin.size()!=32)return-1;
 if(p->bin[7]!=0xf6)return-3;
 std::array<u32,5>a{0x00360001,1100,0x8000,0x10000,0};std::copy(a.begin(),a.end(),out);return 0;
}
'''
tests = r'''
ppu_exec_object fixture(u32 code){
 ppu_exec_object e;e.progs.resize(5);
 e.progs[0]={1,0x10000,0x10000,5,code,std::vector<u8>(code)};
 e.progs[1]={1,0x20000,0x10000,6,352,std::vector<u8>(352)};
 e.progs[2]={0x60000002,0x20100,40,0,40,std::vector<u8>(40)};
 e.progs[3]={7,0x20080,64,4,9,std::vector<u8>(9)};
 e.progs[4]={0x60000001,0x20140,32,0,32,std::vector<u8>(32)};
 const char tls[9]="iOSProbe";std::memcpy(e.progs[3].bin.data(),tls,9);
 std::memcpy(e.progs[1].bin.data()+128,tls,9);
 e.progs[4].bin[7]=0xf6;std::memcpy(e.progs[1].bin.data()+320,e.progs[4].bin.data(),32);return e;
}
void reset(){vm::allocated.clear();loader_mode=0;loader_calls=0;utils::decommits=0;}
void rejected(ppu_exec_object&e,int error){
 reset();ppu_module<lv2_obj>m;std::array<u32,8>out;out.fill(0xaaaaaaaa);
 assert(armsx3_ios_ppu_load_probe_process_image_segments(&e,&m,out.data())==error);
 assert(loader_calls==0&&vm::allocated.empty()&&m.segs.empty()&&m.addr_to_seg_index.empty());
 assert(std::all_of(out.begin(),out.end(),[](u32 x){return x==0xaaaaaaaa;}));
}
int main(){
#ifdef OLD_WRAPPER
 auto e=fixture(136);e.progs[3].p_filesz=65;rejected(e,-2);
 std::puts("PASS reproduced build56: 136-byte fixture rejected before TLS validation");
#else
 for(u32 code:{108u,136u}){
  for(int field=0;field<4;++field){auto e=fixture(code);
   if(field==0)e.progs[3].p_filesz=65;if(field==1)e.progs[3].p_flags=6;
   if(field==2)e.progs[3].bin.clear();if(field==3)e.progs[3].bin[0]^=1;rejected(e,-5);
  }
  for(int field=0;field<3;++field){auto e=fixture(code);
   if(field==0)e.progs[4].bin[7]=0;if(field==1)e.progs[4].bin.resize(31);
   if(field==2)e.progs[4].bin[8]^=1;rejected(e,-6);
  }
  reset();auto e=fixture(code);ppu_module<lv2_obj>m;std::array<u32,8>out{};
  assert(armsx3_ios_ppu_load_probe_process_image_segments(&e,&m,out.data())==0);
  const std::array<u32,8>expected{0x00360001,1100,0x8000,0x10000,0,0x20080,9,64};
  assert(out==expected&&loader_calls==1&&vm::allocated.size()==2&&utils::decommits==0);
  for(int mode:{1,2}){reset();loader_mode=mode;m={};out.fill(0xaaaaaaaa);
   assert(armsx3_ios_ppu_load_probe_process_image_segments(&e,&m,out.data())==(mode==1?-3:-4));
   assert(vm::allocated.empty()&&m.segs.empty()&&m.addr_to_seg_index.empty()&&utils::decommits==1);
   assert(std::all_of(out.begin(),out.end(),[](u32 x){return x==0xaaaaaaaa;}));
  }
 }
 for(u32 code:{0u,104u,112u,132u,140u}){auto e=fixture(code);rejected(e,-2);}
 auto e=fixture(136);e.progs[0].bin.pop_back();rejected(e,-2);
 e=fixture(136);e.progs[1].p_filesz=351;e.progs[1].bin.resize(351);rejected(e,-2);
 std::puts("PASS build57: both fixtures, all malformed TLS/process cases, size bounds and rollback");
#endif
}
'''
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    for old,path in zip([True, False], sources):
        source=directory/'test.cpp'; binary=directory/'test'
        source.write_text(prelude+function(path.read_text())+tests)
        cmd=['g++','-std=c++20','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(binary)]
        if old:cmd.insert(1,'-DOLD_WRAPPER')
        subprocess.run(cmd,check=True)
        subprocess.run([str(binary)],check=True)

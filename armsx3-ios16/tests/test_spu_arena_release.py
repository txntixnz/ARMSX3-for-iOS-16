"""Deterministically reproduce allocation reuse during SPU arena teardown.

Usage: python test_spu_arena_release.py SPUThread.before.cpp SPUThread.after.cpp vm_native.cpp
Compile the exact old/new destructor and POSIX memory reserve/release bodies.
Shared views use real mmap; a controlled allocator occupies the first freed
view between unmap calls, or immediately after the single complete release.
This models a scheduling interleaving rather than timing a probabilistic race.
"""
from pathlib import Path
import subprocess,tempfile,sys
root=Path(__file__).resolve().parent
if len(sys.argv)==4:
    before,after,native=map(Path,sys.argv[1:])
elif len(sys.argv)==1:
    before,after,native=root/'SPUThread.build58.cpp',root/'spu-staged/rpcs3/Emu/Cell/SPUThread.cpp',root/'vm_native.base.cpp'
else:raise SystemExit(__doc__)
def function(source,signature):
    start=source.index(signature);opening=source.index('{',start);depth=1;end=opening+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]
vm=native.read_text()
reserve=function(vm,'void* memory_reserve(')
release=function(vm,'void memory_release(').replace('void memory_release(', 'void memory_release_raw(',1)
prelude=r'''
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <memory>
#include <cassert>
#include <cerrno>
using u8=uint8_t;using u64=uint64_t;using s64=int64_t;using usz=size_t;using uptr=uintptr_t;
constexpr uptr umax=UINTPTR_MAX;constexpr usz SPU_LS_SIZE=0x40000;
constexpr s64 SIGNED_LS_SIZE=SPU_LS_SIZE;
bool ensure(bool b){assert(b);return b;}
void* foreign=nullptr;u8* reuse_target=nullptr;unsigned unmaps=0,releases=0;
bool mapped(void* p){unsigned char resident;errno=0;return ::mincore(p,4096,&resident)==0;}
void allocate_reused_view(){
 if(foreign)return;
 foreign=::mmap(reuse_target,SPU_LS_SIZE,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE|MAP_FIXED_NOREPLACE,-1,0);
 assert(foreign==reuse_target);std::memset(foreign,0xa5,SPU_LS_SIZE);
}
namespace utils {
constexpr int c_map_noreserve=MAP_NORESERVE,c_madv_hugepage=0,c_madv_no_dump=0,c_madv_free=MADV_NORMAL;
'''
postlude=r'''
void memory_release(void* pointer,usz size){
 ++releases;memory_release_raw(pointer,size);
 // A caller may reuse the address as soon as this operation completes.
 allocate_reused_view();
}
struct shm {
 int fd;
 shm(){char path[]="/tmp/spu-arena-XXXXXX";fd=::mkstemp(path);assert(fd>=0);assert(!::unlink(path));assert(!::ftruncate(fd,SPU_LS_SIZE));}
 ~shm(){assert(!::close(fd));}
 void map(u8* p){assert(::mmap(p,SPU_LS_SIZE,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,fd,0)==p);}
 void unmap(void* p){++unmaps;assert(!::munmap(p,SPU_LS_SIZE));allocate_reused_view();}
};
}
struct spu_thread {
 std::shared_ptr<utils::shm> shm;u8*ls;
 ~spu_thread();
};
#if PROBE_IOS
#define __APPLE__ 1
#define TARGET_OS_IPHONE 1
#endif
'''
tests=r'''
#if PROBE_IOS
#undef __APPLE__
#undef TARGET_OS_IPHONE
#endif
int main(){
 for(unsigned repeat=0;repeat<128;++repeat){
  foreign=nullptr;unmaps=releases=0;
  auto* region=static_cast<u8*>(utils::memory_reserve(SPU_LS_SIZE*9,nullptr,true,false));assert(region);
  assert(reinterpret_cast<uptr>(region)%0x10000==0);
  assert(!::mprotect(region,SPU_LS_SIZE,PROT_READ|PROT_WRITE));
  assert(!::mprotect(region+SPU_LS_SIZE*8,SPU_LS_SIZE,PROT_READ|PROT_WRITE));
  std::memset(region,0x6c,SPU_LS_SIZE);std::memset(region+SPU_LS_SIZE*8,0x3d,SPU_LS_SIZE);
  reuse_target=region+SPU_LS_SIZE*2;
  auto backing=std::make_shared<utils::shm>();
  {
   spu_thread spu{backing,region+SPU_LS_SIZE*4};
   for(s64 i=-2;i<=2;++i)backing->map(spu.ls+i*SIGNED_LS_SIZE);
   spu.ls[123]=0x42;
   for(s64 i=-2;i<=2;++i)assert(spu.ls[i*SIGNED_LS_SIZE+123]==0x42);
  }
  assert(releases==1);
  if(EXPECT_ATOMIC){assert(unmaps==0&&mapped(foreign));for(usz i=0;i<SPU_LS_SIZE;++i)assert(static_cast<u8*>(foreign)[i]==0xa5);}
  else {assert(unmaps==5&&!mapped(foreign));}
  assert(!mapped(region+SPU_LS_SIZE));assert(!mapped(region+SPU_LS_SIZE*7));
  for(usz i=0;i<SPU_LS_SIZE;++i){assert(region[i]==0x6c);assert(region[SPU_LS_SIZE*8+i]==0x3d);}
  assert(!::munmap(region,SPU_LS_SIZE*9));backing.reset();
 }
 std::puts(EXPECT_ATOMIC?"PASS: iOS single release preserves reused allocation, guards and adjacent mappings (128 cycles)":"PASS: reproduced old/native teardown deleting the allocation that reused a freed mirror (128 cycles)");
}
'''
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    for path,ios,atomic in [(before,1,0),(after,1,1),(after,0,0)]:
        source=directory/'regression.cpp';binary=directory/'regression'
        source.write_text(prelude+reserve+'\n'+release+'\n'+postlude+function(path.read_text(),'spu_thread::~spu_thread()')+'\n'+tests)
        subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',f'-DPROBE_IOS={ios}',f'-DEXPECT_ATOMIC={atomic}',str(source),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)

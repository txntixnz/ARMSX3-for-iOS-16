"""Darwin SIGBUS permissions: exact native ESR decoder and recovery dispatch.
Compile after all57 patches with explicit host signal/VM/RSX interfaces. A real
Linux mprotect fault is routed through Darwin-style SIGBUS/ESR state, then the
actual dispatch retries the native host load/store after a modeled RSX unprotect.
This does not execute iOS signals or the full RSX access-violation implementation.
Apple source: xnu bsd/uxkern/ux_exception.c and bsd/dev/arm/unix_signal.c: Darwin
uses SIGBUS for protection failures and sets BUS_ADRALN for every ARM SIGBUS.
"""
from pathlib import Path
import re,subprocess,sys,tempfile
root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
PIN='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
paths=['Utilities/Thread.cpp','rpcs3/Emu/CPU/Backends/AArch64/AArch64Signal.h','rpcs3/Emu/CPU/Backends/AArch64/AArch64Signal.cpp']
patches=sorted(p for p in (root/'patches').glob('*.patch') if int(p.name[:4])<=57)
assert [p.name[:4] for p in patches]==[f'{n:04d}' for n in range(1,58)]
strip=lambda s:re.sub(r'^#(?:include[^\n]*|pragma once)\n','',s,flags=re.M)
with tempfile.TemporaryDirectory(prefix='armsx3-ios-signal-') as directory:
 temp=Path(directory)
 for rel in paths:
  p=temp/rel;p.parent.mkdir(parents=True,exist_ok=True)
  p.write_bytes(subprocess.check_output(['git','-C',str(native),'show',PIN+':'+rel]))
 options=[f'--include={p}' for p in paths]
 for patch in patches[:-1]:subprocess.run(['git','apply',*options,str(patch)],cwd=temp,check=True)
 before=(temp/paths[0]).read_text()
 subprocess.run(['git','apply','--check',str(patches[-1])],cwd=temp,check=True)
 subprocess.run(['git','apply',str(patches[-1])],cwd=temp,check=True)
 subprocess.run(['git','apply','--reverse','--check',str(patches[-1])],cwd=temp,check=True)
 thread=(temp/paths[0]).read_text();header=strip((temp/paths[1]).read_text());decoder=strip((temp/paths[2]).read_text())
 # Compile unchanged native decoding through the exact fault-direction and
 # three recovery-dispatch branches, stopping before unrelated fatal diagnostics.
 start=thread.index('\t// SIGBUS arrives here too now')
 end=thread.index('\n#ifdef __ANDROID__\n\t// Raw state',start)
 # Convert only void success returns to bool so the harness observes retry.
 prefix=thread[start:end].replace("return;", "return true;")
 bus=thread[thread.index('static const char* bus_error_kind'):thread.index('\nstatic void signal_handler')]
 assert '#if defined(__APPLE__) && !TARGET_OS_IOS\n\tthread_local bool s_tls_is_attempting_recovery' in thread
 assert 'iOS ESR: 0x%08x, FAR: 0x%llx' in thread
 prelude=r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <csignal>
#include <sys/mman.h>
#include <unistd.h>
#include <utility>
using u8=std::uint8_t;using u32=std::uint32_t;using u64=std::uint64_t;using uptr=std::uintptr_t;
// System headers were read for the real Linux mmap/sigaction backend. Model only
// the native Apple exception prefix; the decoder/layout/access remain native.
using real_ucontext_t=void;
#undef __linux__
#define __APPLE__ 1
#define ARCH_ARM64 1
#ifndef TARGET_OS_IOS
#define TARGET_OS_IOS 1
#endif
#define ucontext_t model_ucontext_t
struct model_ucontext_t{void*uc_mcontext{};};
#define RIP(c) (uptr(0x100000000ull))
struct{template<class...T>void warning(const char*,T...)const{}}sig_log;
namespace vm{
 u8*g_base_addr=nullptr;u8*g_exec_addr=reinterpret_cast<u8*>(0x500000000ull);constexpr u64 g_exec_addr_seg_offset=0x100000000ull;
 u64 size=0;
 std::pair<u32,bool>try_get_addr(void*p){const auto delta=uptr(p)-uptr(g_base_addr);return {u32(delta),delta<size};}
}
namespace thread_ctrl{void*get_current(){return reinterpret_cast<void*>(1);}}
volatile sig_atomic_t faults=0,handled=0,write_seen=0;bool allow_recovery=false;void*protected_page=nullptr;std::size_t page_size=0;
bool handle_access_violation(u32 addr,bool writing,bool exec,model_ucontext_t*)noexcept{
 ++handled;write_seen=writing;
 if(!allow_recovery)return false;
 assert(!exec&&addr<vm::size);
 assert(mprotect(protected_page,page_size,PROT_READ|PROT_WRITE)==0);
 return true;
}
"""
 harness=r"""
bool dispatch(int sig,siginfo_t*info,model_ucontext_t*context){
 /* EXACT_NATIVE_PREFIX */
 (void)cause;return false;
}
aarch64::aarch64_darwin_mcontext64 darwin{};
model_ucontext_t state{&darwin};
int observed_direction=0;
void permission_signal(int sig,siginfo_t*info,void*){
 assert(sig==SIGSEGV);++faults;
 // Linux supplies SIGSEGV for this real mprotect fault; Darwin supplies SIGBUS
 // and generic BUS_ADRALN. Feed the documented Darwin frame into native code.
 siginfo_t apple{};apple.si_addr=info->si_addr;apple.si_code=BUS_ADRALN;
 darwin.es.ESR=(0x24u<<26)|0x0fu|(observed_direction?0x40u:0u);
 darwin.es.FAR=uptr(info->si_addr);
 if(!dispatch(SIGBUS,&apple,&state))_exit(95);
}
int main(){
 siginfo_t info{};info.si_code=BUS_ADRALN;info.si_addr=reinterpret_cast<void*>(0x340300400ull);
 vm::g_base_addr=reinterpret_cast<u8*>(0x300000000ull);vm::size=0x100000000ull;
 // Every EC and FSC/direction combination, including true alignment=0x21,
 // translation=0x04..07, external aborts, and instruction faults.
 for(u32 ec=0;ec<64;++ec)for(u32 fsc=0;fsc<64;++fsc)for(u32 write=0;write<2;++write){
  darwin.es.ESR=(ec<<26)|(write<<6)|fsc;
  const bool permission=(ec==0x24||ec==0x25)&&fsc>=0x0c&&fsc<=0x0f;
  assert(aarch64::is_data_permission_fault(&state)==permission);
  handled=0;
  const bool success=dispatch(SIGBUS,&info,&state);
  assert(!success);
#if TARGET_OS_IOS
  // One direct guest branch; metadata aliases are outside the fixture range.
  assert(handled==(permission?1:0));
  if(permission)assert(write_seen==int(write));
#else
  assert(handled==0); // Preserve desktop SIGBUS behavior.
#endif
 }
 darwin.es.ESR=(0x24u<<26)|0x0fu;
 handled=0;info.si_addr=reinterpret_cast<void*>(0x200000000ull);
 assert(!dispatch(SIGBUS,&info,&state)&&handled==0); // not guest/metadata
 info.si_addr=reinterpret_cast<void*>(0x340300400ull);handled=0;
 assert(!dispatch(SIGSEGV,&info,&state)&&handled==1); // existing SIGSEGV path
#if TARGET_OS_IOS
 assert(std::strstr(bus_error_kind(BUS_ADRALN),"Darwin"));
 page_size=std::size_t(sysconf(_SC_PAGESIZE));
 protected_page=mmap(nullptr,page_size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 assert(protected_page!=MAP_FAILED);vm::g_base_addr=static_cast<u8*>(protected_page);vm::size=page_size;allow_recovery=true;
 struct sigaction action{},previous{};action.sa_sigaction=permission_signal;action.sa_flags=SA_SIGINFO;sigemptyset(&action.sa_mask);
 assert(sigaction(SIGSEGV,&action,&previous)==0);
 volatile u8*bytes=static_cast<volatile u8*>(protected_page);
 // Read from a no-access page and write a read-only page at all four addresses
 // in the uploaded fault report (same host page, different128-byte subranges).
 for(unsigned offset:{0x400u,0x480u,0x440u,0x410u}){
  bytes[offset]=0x5a;observed_direction=0;
  assert(mprotect(protected_page,page_size,PROT_NONE)==0);const u8 value=bytes[offset];assert(value==0x5a&&write_seen==0);
  observed_direction=1;assert(mprotect(protected_page,page_size,PROT_READ)==0);bytes[offset]=0x7c;assert(bytes[offset]==0x7c&&write_seen==1);
 }
 assert(faults==8);assert(sigaction(SIGSEGV,&previous,nullptr)==0);assert(munmap(protected_page,page_size)==0);
#else
 assert(std::strstr(bus_error_kind(BUS_ADRALN),"misaligned"));
#endif
 std::puts("PASS native ESR exhaustive matrix, exact protected-page dispatch, original SIGSEGV/desktop behavior and real mmap read/write retry via Darwin frame model");
}
""".replace('/* EXACT_NATIVE_PREFIX */',prefix)
 for ios in (1,0):
  source=prelude+'\n'+header+'\n'+decoder+'\n'+bus+'\n'+harness
  (temp/'test.cpp').write_text(source)
  subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-Wno-volatile','-fsanitize=address,undefined','-fno-omit-frame-pointer',f'-DTARGET_OS_IOS={ios}',str(temp/'test.cpp'),'-o',str(temp/'test')],check=True)
  subprocess.run([str(temp/'test')],check=True,timeout=15)
 # The same matrix must reject the old unconditional SIGBUS gate. Compile
 # the pre57 exact dispatcher against the same test and actual decoder.
 old_start=before.index('\t// SIGBUS arrives here too now')
 old_end=before.index('\n#ifdef __ANDROID__\n\t// Raw state',old_start)
 old_prefix=before[old_start:old_end].replace('return;', 'return true;')
 old_source=prelude+'\n'+header+'\n'+decoder+'\n'+bus+'\n'+harness.replace(prefix,old_prefix)
 (temp/'old.cpp').write_text(old_source)
 subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-Wno-volatile','-DTARGET_OS_IOS=1',str(temp/'old.cpp'),'-o',str(temp/'old')],check=True)
 failed=subprocess.run([str(temp/'old')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
 assert failed.returncode!=0 and b'handled==(permission?1:0)' in failed.stderr,'pre57 must fail permission recovery'
 print('PASS old native SIGBUS gate reproduces the blocked-permission regression')
print('PASS patch57 after exact first56/reverse; true alignment/backing/translation/execute/outside faults remain unhandled. iOS actual signal/RSX recovery still needs device verification.')

"""Darwin SIGBUS permissions: exact native ESR decoder and recovery dispatch.
Compile after all59 patches with explicit host signal/VM/RSX interfaces. A real
Linux mprotect fault is routed through Darwin-style SIGBUS/ESR state, then the
actual dispatch and native ZCULL report-page methods restore host access.
Thread state/locks, VM flags, fmt and GPU interfaces are explicit host models.
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
patches=sorted(p for p in (root/'patches').glob('*.patch') if int(p.name[:4])<=59)
assert [p.name[:4] for p in patches]==[f'{n:04d}' for n in range(1,60)]
strip=lambda s:re.sub(r'^#(?:include[^\n]*|pragma once)\n','',s,flags=re.M)
with tempfile.TemporaryDirectory(prefix='armsx3-ios-signal-') as directory:
 temp=Path(directory)
 for rel in paths:
  p=temp/rel;p.parent.mkdir(parents=True,exist_ok=True)
  p.write_bytes(subprocess.check_output(['git','-C',str(native),'show',PIN+':'+rel]))
 options=[f'--include={p}' for p in paths]
 for patch in patches[:-3]:subprocess.run(['git','apply',*options,str(patch)],cwd=temp,check=True)
 before=(temp/paths[0]).read_text()
 for patch in patches[-3:]:
  if patch.name.startswith('0059'):pre59_thread=(temp/paths[0]).read_text()
  subprocess.run(['git','apply','--check',str(patch)],cwd=temp,check=True)
  subprocess.run(['git','apply',str(patch)],cwd=temp,check=True)
 pre58_header=(temp/paths[1]).read_text().replace('u64 fault_address;','u64 FAR;')
 for patch in reversed(patches[-3:]):
  subprocess.run(['git','apply','--reverse','--check',str(patch)],cwd=temp,check=True)
  subprocess.run(['git','apply','--reverse',str(patch)],cwd=temp,check=True)
 assert (temp/paths[0]).read_text()==before
 for patch in patches[-3:]:subprocess.run(['git','apply',str(patch)],cwd=temp,check=True)
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
#include <cstddef>
#include <string>
#include <cstdio>
#include <cstring>
#include <csignal>
#include <sys/mman.h>
#include <unistd.h>
#include <utility>
#include <functional>
#include <map>
#include <mutex>
#include <stdexcept>
using u8=std::uint8_t;using u32=std::uint32_t;using u64=std::uint64_t;using uptr=std::uintptr_t;
// System headers were read for the real Linux mmap/sigaction backend. Model only
// the native Apple exception prefix; the decoder/layout/access remain native.
using real_ucontext_t=void;
#undef __linux__
#define __APPLE__ 1
#define ARCH_ARM64 1
// Native Thread.cpp dependencies define this compatibility macro.
#define FAR
#ifndef TARGET_OS_IOS
#define TARGET_OS_IOS 1
#endif
#define ucontext_t model_ucontext_t
struct model_ucontext_t{void*uc_mcontext{};};
#define RIP(c) (uptr(0x100000000ull))
struct{template<class...T>void warning(const char*,T...)const{}}sig_log;
namespace vm{
 u8*g_base_addr=nullptr;u8*g_exec_addr=reinterpret_cast<u8*>(0x500000000ull);constexpr u64 g_exec_addr_seg_offset=0x100000000ull;
 u64 size=0;bool allocated=true;
 constexpr u8 page_readable=1,page_writable=2,page_allocated=4;
 bool check_addr(u32,u8=page_readable){return allocated;}
 using addr_t=u32;
 void*base(u32 addr){return reinterpret_cast<void*>(uptr(g_base_addr)+addr);}
 std::pair<u32,bool>try_get_addr(void*p){const auto delta=uptr(p)-uptr(g_base_addr);return {u32(delta),delta<size};}
}
namespace thread_ctrl{void*get_current(){return reinterpret_cast<void*>(1);}}
volatile sig_atomic_t faults=0,handled=0,write_seen=0;bool allow_recovery=false;void*protected_page=nullptr;std::size_t page_size=0;

constexpr u32 RAW_SPU_BASE_ADDR=0xe0000000;
struct spu_thread{bool unsavable=false;}host_spu;
enum class cpu_flag{temp};
struct cpu_thread{
 bool spu=false;struct{void operator+=(cpu_flag){}}state;
 template<class T>T*try_get(){return spu?reinterpret_cast<T*>(&host_spu):nullptr;}
 bool test_stopped(){return false;}
}host_cpu;
cpu_thread*get_current_cpu_thread(){return &host_cpu;}
namespace vm{bool temporary_unlock(cpu_thread&){return false;}}
volatile sig_atomic_t g_tls_fault_rsx=0;auto&g_tls_fault_all=handled;
unsigned generic_calls=0;bool allow_generic_retry=false;
namespace utils{
 enum class protection{no,rw};
 std::size_t get_page_size(){return 16384;}
 /* EXACT_PAGE_START */
 void memory_protect(void*p,std::size_t size,protection prot){assert(mprotect(p,size,prot==protection::no?PROT_NONE:PROT_READ|PROT_WRITE)==0);}
}
struct page_lock{unsigned refs=0;utils::protection prot=utils::protection::rw;void add_ref(){++refs;}bool has_refs()const{return refs!=0;}void release(){assert(refs);--refs;}};
struct model_mutex{void lock(){}void unlock(){}};
struct reader_lock{explicit reader_lock(model_mutex&){}void upgrade(){}};
template<class T>T ensure(T v){if(!v)std::terminate();return v;}
struct{template<class...T>void warning(const char*,T...)const{}}rsx_log;
namespace rsx{
 constexpr unsigned pipe_flush_interrupt=1;
 unsigned classify_location(u32 addr){return addr>=0xc0000000?0:1;}
 const char*location_tostring(u32){return "modeled reports area";}
 struct thread{unsigned m_eng_interrupt_mask=0;}renderer;
 thread*get_current_renderer(){return &renderer;}
 struct eng_lock{explicit eng_lock(thread*){}};
 namespace reports{struct ZCULL_control{
  bool m_pages_accessed[2]{};model_mutex m_pages_mutex;
  std::map<u32,page_lock>m_locked_pages[2];unsigned m_critical_reports_in_flight=0;
  void on_report_enqueued(vm::addr_t);void on_report_completed(vm::addr_t);
  void disable_optimizations(::rsx::thread*,u32);bool on_access_violation(u32);
 };
 /* EXACT_ZCULL */
 }
 reports::ZCULL_control zcull;
 std::function<bool(u32,bool)>g_access_violation_handler=[](u32 addr,bool writing){
  write_seen=writing;
  return allow_recovery&&zcull.on_access_violation(addr);
 };
}
/* EXACT_ACCESS_PREFIX */
 ++generic_calls;(void)context;
 return allow_generic_retry&&vm::check_addr(addr);
}

"""
 access_start=thread.index('bool handle_access_violation(')
 access_end=thread.index('\n#if defined(ARCH_X64)',access_start)
 access_prefix=thread[access_start:access_end]
 assert 'if (rsx_only) return false;' in access_prefix
 zcull_native=(native/'rpcs3/Emu/RSX/RSXZCULL.cpp').read_text()
 zcull_native=zcull_native[zcull_native.index('\t\tvoid ZCULL_control::on_report_enqueued'):zcull_native.index('\n\n\t\t// Conditional rendering helpers')]
 address=(native/'Utilities/address_range.h').read_text()
 page_start=address[address.index('\ttemplate <typename T>\n\tT page_start'):address.index('\n\ttemplate <typename T>\n\tstatic inline T next_page')]
 prelude=prelude.replace('/* EXACT_ACCESS_PREFIX */',access_prefix).replace('/* EXACT_ZCULL */',zcull_native).replace('/* EXACT_PAGE_START */',page_start)
 fatal_start=thread.index('#if defined(__APPLE__) && defined(ARCH_ARM64) && TARGET_OS_IOS\n\tconst auto* darwin_context')
 fatal_end=thread.index('\n#endif',fatal_start)+len('\n#endif')
 fatal_detail=thread[fatal_start:fatal_end]
 harness=r"""
static_assert(sizeof(aarch64::aarch64_exception_state)==16);
static_assert(offsetof(aarch64::aarch64_exception_state,ESR)==8);
static_assert(offsetof(aarch64::aarch64_exception_state,exception_id)==12);
u32 logged_esr=0;u64 logged_far=0;
namespace fmt{[[maybe_unused]] void append(std::string&,const char*,u32 esr,u64 far){logged_esr=esr;logged_far=far;}}
void fatal_detail(model_ucontext_t*context){
 std::string msg;
 /* EXACT_FATAL_DETAIL */
 (void)context;
}
bool dispatch(int sig,siginfo_t*info,model_ucontext_t*context){
 /* EXACT_NATIVE_PREFIX */
 (void)cause;return false;
}
aarch64::aarch64_darwin_mcontext64 darwin{};
model_ucontext_t state{&darwin};
int observed_direction=0;u32 observed_fsc=0x0f;
void permission_signal(int sig,siginfo_t*info,void*){
 assert(sig==SIGSEGV);++faults;
 // Linux supplies SIGSEGV for this real mprotect fault; Darwin supplies SIGBUS
 // and generic BUS_ADRALN. Feed the documented Darwin frame into native code.
 siginfo_t apple{};apple.si_addr=info->si_addr;apple.si_code=BUS_ADRALN;
 darwin.es.ESR=(0x24u<<26)|observed_fsc|(observed_direction?0x40u:0u);
 darwin.es.fault_address=uptr(info->si_addr);
 if(!dispatch(SIGBUS,&apple,&state))_exit(95);
}
int main(){
 darwin.es.ESR=0x9200000fu;darwin.es.fault_address=0x340300400ull;fatal_detail(&state);
#if TARGET_OS_IOS
 assert(logged_esr==0x9200000fu&&logged_far==0x340300400ull);
#else
 assert(logged_esr==0&&logged_far==0);
#endif
 siginfo_t info{};info.si_code=BUS_ADRALN;info.si_addr=reinterpret_cast<void*>(0x340300400ull);
 vm::g_base_addr=reinterpret_cast<u8*>(0x300000000ull);vm::size=0x100000000ull;
 // Every EC and FSC/direction combination, including true alignment=0x21,
 // translation=0x04..07, external aborts, and instruction faults.
 for(u32 ec=0;ec<64;++ec)for(u32 fsc=0;fsc<64;++fsc)for(u32 write=0;write<2;++write){
  darwin.es.ESR=(ec<<26)|(write<<6)|fsc;
  const bool permission=(ec==0x24||ec==0x25)&&fsc>=0x0c&&fsc<=0x0f;
  const bool translation=(ec==0x24||ec==0x25)&&fsc>=0x04&&fsc<=0x07;
  assert(aarch64::is_data_permission_fault(&state)==permission);
  assert(aarch64::is_data_translation_fault(&state)==translation);
  handled=0;
  const bool success=dispatch(SIGBUS,&info,&state);
  assert(!success);
#if TARGET_OS_IOS
  // One direct guest branch; metadata aliases are outside the fixture range.
  assert(handled==((permission||translation)?1:0));
  if(permission||translation)assert(write_seen==int(write));
#else
  assert(handled==0); // Preserve desktop SIGBUS behavior.
#endif
 }
 #if TARGET_OS_IOS
 // Translation is never a logical-permission-only retry: only RSX ownership.
 darwin.es.ESR=0x92000007;vm::allocated=false;handled=0;
 assert(!dispatch(SIGBUS,&info,&state)&&handled==0);
 vm::allocated=true;allow_generic_retry=true;generic_calls=0;handled=0;
 assert(!dispatch(SIGBUS,&info,&state)&&handled==1&&generic_calls==0);
 allow_generic_retry=false;
 #endif
 darwin.es.ESR=(0x24u<<26)|0x0fu;
 handled=0;info.si_addr=reinterpret_cast<void*>(0x200000000ull);
 assert(!dispatch(SIGBUS,&info,&state)&&handled==0); // not guest/metadata
 info.si_addr=reinterpret_cast<void*>(0x340300400ull);handled=0;
 assert(!dispatch(SIGSEGV,&info,&state)&&handled==1); // existing SIGSEGV path
#if TARGET_OS_IOS
 assert(std::strstr(bus_error_kind(BUS_ADRALN),"Darwin"));
 page_size=16384;
 protected_page=mmap(nullptr,page_size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 assert(protected_page!=MAP_FAILED);vm::g_base_addr=reinterpret_cast<u8*>(uptr(protected_page)-0x40300000u);vm::size=0x100000000ull;allow_recovery=true;
 struct sigaction action{},previous{};action.sa_sigaction=permission_signal;action.sa_flags=SA_SIGINFO;sigemptyset(&action.sa_mask);
 assert(sigaction(SIGSEGV,&action,&previous)==0);
 volatile u8*bytes=static_cast<volatile u8*>(protected_page);
 // Read from a no-access page and write a read-only page at all four addresses
 // in the uploaded fault report (same host page, different128-byte subranges).

 for(u32 status:{7u,15u})for(unsigned offset:{0x400u,0x480u,0x440u,0x410u}){
  const u32 report=0x40301400u;observed_fsc=status;
  rsx::zcull={};host_cpu.spu=(offset&0x40)!=0;
  bytes[offset]=0x5a;observed_direction=0;
  rsx::zcull.on_report_enqueued(report); // actual native ZCULL locks16KiB host page
  const u8 value=bytes[offset];
  assert(value==0x5a&&write_seen==0&&rsx::zcull.m_pages_accessed[1]&&!host_spu.unsavable);
  assert(rsx::renderer.m_eng_interrupt_mask&rsx::pipe_flush_interrupt);
  rsx::zcull={};
  rsx::zcull.on_report_enqueued(report);rsx::zcull.on_report_completed(report);
  observed_direction=1;bytes[offset]=0x7c;
  assert(bytes[offset]==0x7c&&write_seen==1&&rsx::zcull.m_locked_pages[1].empty()&&!host_spu.unsavable);
 }
 assert(faults==16&&g_tls_fault_rsx==16);assert(sigaction(SIGSEGV,&previous,nullptr)==0);assert(munmap(protected_page,page_size)==0);
#else
 assert(std::strstr(bus_error_kind(BUS_ADRALN),"misaligned"));
#endif
 std::puts("PASS native ESR matrix/dispatch and native ZCULL16KiB active/stale report recovery:16 real mmap read/write retries via Darwin frame model");
}
""".replace('/* EXACT_NATIVE_PREFIX */',prefix).replace('/* EXACT_FATAL_DETAIL */',fatal_detail)
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
 assert failed.returncode!=0 and b'handled==((permission||translation)?1:0)' in failed.stderr,'pre57 must fail permission recovery'
 print('PASS old native SIGBUS gate reproduces the blocked-permission regression')
 pre59_prefix=pre59_thread[pre59_thread.index('\t// SIGBUS arrives here too now'):pre59_thread.index('\n#ifdef __ANDROID__\n\t// Raw state')].replace('return;', 'return true;')
 pre59_source=prelude+'\n'+header+'\n'+decoder+'\n'+bus+'\n'+harness.replace(prefix,pre59_prefix)
 (temp/'pre59.cpp').write_text(pre59_source)
 subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-Wno-volatile','-DTARGET_OS_IOS=1',str(temp/'pre59.cpp'),'-o',str(temp/'pre59')],check=True)
 regression=subprocess.run([str(temp/'pre59')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
 assert regression.returncode!=0 and b'handled==((permission||translation)?1:0)' in regression.stderr
 print('PASS Build127 permission-only gate reproduces the allocated-translation regression')
 # Reproduce the native macro failure using the exact fatal-detail statement.
 broken_header=strip(pre58_header)
 broken_harness=harness.replace('darwin_context->es.fault_address','darwin_context->es.FAR')
 broken=prelude+'\n'+broken_header+'\n'+decoder+'\n'+bus+'\n'+broken_harness
 (temp/'macro-before.cpp').write_text(broken)
 failure=subprocess.run(['g++','-std=c++23','-fsyntax-only','-DTARGET_OS_IOS=1',str(temp/'macro-before.cpp')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 assert failure.returncode!=0 and b'expected unqualified-id' in failure.stderr
 print('PASS native FAR macro compile regression reproduced; corrected header keeps16-byte context/ESR offset8 and compiles exact fatal-detail access')
print('PASS patches57/58/59 after exact first56/reverse; allocated translation faults require native RSX acceptance; true alignment/external/execute/outside and unallocated/unowned translation faults remain unhandled. iOS actual signal/RSX recovery still needs device verification.')

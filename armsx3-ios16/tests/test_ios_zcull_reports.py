"""Exercise native report-page policy and reproduce Build128's recovery race.

Compile the exact pinned/patched ZCULL constructor, destructor and report-page
methods with real atomics, host locks and mprotect. VM/GPU/query-pool interfaces
are explicit models; no iOS signal delivery or Vulkan query is executed here.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent.parent
native = Path(sys.argv[1]).resolve()
pin = '92b931b9fb5eef7f1317cb482917dfc19aceebd9'
rel = 'rpcs3/Emu/RSX/RSXZCULL.cpp'
patches = sorted(p for p in (root / 'patches').glob('*.patch') if int(p.name[:4]) <= 60)
assert [p.name[:4] for p in patches] == [f'{n:04d}' for n in range(1, 61)]

prelude = r'''
#include <array>
#include <atomic>
#include <barrier>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <mutex>
#include <shared_mutex>
#include <thread>
#include <sys/mman.h>
#include <unistd.h>
using u32=std::uint32_t;using u64=std::uint64_t;
template<class T>using atomic_t=std::atomic<T>;
using shared_mutex=std::shared_mutex;
struct reader_lock{
 shared_mutex&mutex;bool exclusive=false;
 explicit reader_lock(shared_mutex&m):mutex(m){mutex.lock_shared();}
 void upgrade(){mutex.unlock_shared();mutex.lock();exclusive=true;}
 ~reader_lock(){if(exclusive)mutex.unlock();else mutex.unlock_shared();}
};
template<class T>T ensure(T value){assert(value);return value;}
void*host_pages[2]{};std::atomic<unsigned>protect_calls{0};
std::atomic<bool>protected_pages[2]{};
namespace utils{
 enum class protection{rw,no};
 std::size_t get_page_size(){return 16384;}
 template<class T>T page_start(T value){return value&~T(get_page_size()-1);}
 void memory_protect(void*address,std::size_t size,protection prot){
  ++protect_calls;assert(size==16384);
  assert(mprotect(address,size,prot==protection::rw?PROT_READ|PROT_WRITE:PROT_NONE)==0);
  for(unsigned location=0;location<2;++location)if(address==host_pages[location])protected_pages[location].store(prot==protection::no);
 }
}
namespace vm{
 using addr_t=u32;
 void*base(u32 address){const auto location=address>=0xc0000000u?0u:1u;const u32 start=location?0x40300000u:0xc0000000u;assert(address>=start&&address-start<16384);return static_cast<char*>(host_pages[location])+(address-start);}
}
struct{template<class...T>void warning(const char*,T...)const{}}rsx_log;
namespace rsx{
 u32 classify_location(u32 address){return address>=0xc0000000u?0u:1u;}
 const char*location_tostring(u32){return "host location";}
 constexpr unsigned pipe_flush_interrupt=1;
 struct thread{std::atomic<unsigned>m_eng_interrupt_mask{0};}renderer;
 thread*get_current_renderer(){return &renderer;}
 // Hold the first guest's pause request before restoration, like the device
 // log where the PPU finishes only after the RSX/SPU workers terminate/Stop.
 std::atomic<bool>pause_entered{false},allow_pause{false};
 struct eng_lock{
  explicit eng_lock(thread*){pause_entered.store(true);while(!allow_pause.load())std::this_thread::yield();}
 };
 namespace reports{
 struct MMIO_page_data_t{
  unsigned refs=0;utils::protection prot=utils::protection::rw;
  void add_ref(){++refs;}bool has_refs()const{return refs!=0;}void release(){assert(refs);--refs;}
 };
 struct ZCULL_control{
  std::map<u32,MMIO_page_data_t>m_locked_pages[2];
  atomic_t<bool>m_pages_accessed[2]={false,false};
  atomic_t<int>m_critical_reports_in_flight{0};shared_mutex m_pages_mutex;
  struct Query{};std::array<Query,32>m_occlusion_query_data;
  struct{unsigned count=0;void push(Query*){++count;}}m_free_occlusion_pool;
  struct Stat{unsigned flags=1,result=1;};std::array<Stat,16>m_statistics_map;
  ZCULL_control();~ZCULL_control();
  void on_report_enqueued(vm::addr_t);void on_report_completed(vm::addr_t);
  void disable_optimizations(::rsx::thread*,u32);bool on_access_violation(u32);
 };
 /* NATIVE_METHODS */
 }
}
'''

harness = r'''
int main(){
 for(auto&address:host_pages){
  // Keep the modeled 16KiB host page aligned even on a 4KiB Linux host.
  void*allocation=mmap(nullptr,32768,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);assert(allocation!=MAP_FAILED);
  auto start=reinterpret_cast<std::uintptr_t>(allocation);auto aligned=(start+16383)&~std::uintptr_t(16383);
  if(aligned!=start)assert(munmap(allocation,aligned-start)==0);
  if(aligned+16384!=start+32768)assert(munmap(reinterpret_cast<void*>(aligned+16384),start+32768-aligned-16384)==0);
  address=reinterpret_cast<void*>(aligned);
 }
 {
  rsx::reports::ZCULL_control reports;
  assert(reports.m_free_occlusion_pool.count==reports.m_occlusion_query_data.size());
  for(auto&stat:reports.m_statistics_map)assert(stat.flags==0&&stat.result==0);
#if EXPECT_URGENT
  assert(reports.m_pages_accessed[0]&&reports.m_pages_accessed[1]);
  // RSX queues/completes reports while PPU/SPU/RSX control accesses use other
  // words on those very same real16KiB mappings. Fields are disjoint so this
  // test itself has no data races. Native report counters must balance.
  std::barrier rendezvous(4);
  for(auto*address:host_pages){auto*words=static_cast<u32*>(address);words[0x400/4]=0x11223344;words[0x440/4]=0x55667788;}
  auto ppu=[&]{for(unsigned round=0;round<1000;++round){rendezvous.arrive_and_wait();for(auto*address:host_pages)static_cast<volatile u32*>(address)[0x480/4]=round;rendezvous.arrive_and_wait();}};
  auto spu=[&]{for(unsigned round=0;round<1000;++round){rendezvous.arrive_and_wait();for(auto*address:host_pages)assert(static_cast<volatile u32*>(address)[0x400/4]==0x11223344);rendezvous.arrive_and_wait();}};
  auto rsx=[&]{for(unsigned round=0;round<1000;++round){rendezvous.arrive_and_wait();for(auto*address:host_pages)assert(static_cast<volatile u32*>(address)[0x440/4]==0x55667788);rendezvous.arrive_and_wait();}};
  std::thread ppu_worker(ppu),spu_worker(spu),rsx_worker(rsx);
  for(unsigned round=0;round<1000;++round){
   for(u32 base:{0x40300000u,0xc0000000u})for(u32 offset:{0x1400u,0x2400u})reports.on_report_enqueued(base+offset);
   assert(reports.m_critical_reports_in_flight==4);
   rendezvous.arrive_and_wait();rendezvous.arrive_and_wait();
   for(u32 base:{0x40300000u,0xc0000000u})for(u32 offset:{0x1400u,0x2400u})reports.on_report_completed(base+offset);
   assert(reports.m_critical_reports_in_flight==0);
  }
  ppu_worker.join();spu_worker.join();rsx_worker.join();
  assert(protect_calls==0&&!rsx::pause_entered);
  assert(reports.m_locked_pages[0].empty()&&reports.m_locked_pages[1].empty());
  assert(!reports.on_access_violation(0x40300400u)); // No protected page owned.
  std::puts("PASS iOS urgent reports:4000 native enqueue/completions; concurrent PPU/SPU/RSX accesses on main/local16KiB pages; zero protections/pauses; balanced critical count");
#else
  assert(!reports.m_pages_accessed[0]&&!reports.m_pages_accessed[1]);
  reports.on_report_enqueued(0x40301400u);assert(protected_pages[1]);
  std::thread guest([&]{assert(reports.on_access_violation(0x40300480u));});
  const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);
  while(!rsx::pause_entered.load()){assert(std::chrono::steady_clock::now()<deadline);std::this_thread::yield();}
  assert(reports.m_pages_accessed[1]&&protected_pages[1]);
  assert(!reports.on_access_violation(0x40300400u)); // RSX declines mid-recovery.
  assert(!reports.on_access_violation(0x40300400u)); // SPU declines too.
  rsx::allow_pause.store(true);guest.join();assert(!protected_pages[1]);
  assert(reports.m_critical_reports_in_flight==1);
  reports.on_report_completed(0x40301400u);assert(reports.m_critical_reports_in_flight==0);
  std::puts("PASS reproduced native fault-recovery race:PPU marks accessed before restoring page; concurrent RSX/SPU decline while still inaccessible");
#endif
 }
 for(auto*address:host_pages)assert(munmap(address,16384)==0);
}
'''

def methods(source):
    constructor = source[source.index('\t\tZCULL_control::ZCULL_control()'):source.index('\t\tvoid ZCULL_control::set_active')]
    reports = source[source.index('\t\tvoid ZCULL_control::on_report_enqueued'):source.index('\n\n\t\t// Conditional rendering helpers')]
    return constructor + reports

with tempfile.TemporaryDirectory(prefix='armsx3-zcull-') as directory:
    temp = Path(directory)
    path = temp / rel
    path.parent.mkdir(parents=True)
    path.write_bytes(subprocess.check_output(['git', '-C', str(native), 'show', pin + ':' + rel]))
    for patch in patches[:-1]:
        subprocess.run(['git', 'apply', '--include=' + rel, str(patch)], cwd=temp, check=True)
    before = path.read_bytes()
    subprocess.run(['git', 'apply', '--check', str(patches[-1])], cwd=temp, check=True)
    subprocess.run(['git', 'apply', str(patches[-1])], cwd=temp, check=True)
    after = path.read_bytes()
    subprocess.run(['git', 'apply', '--reverse', str(patches[-1])], cwd=temp, check=True)
    assert path.read_bytes() == before
    for name, source, ios, urgent in [('build128', before, 1, 0), ('ios', after, 1, 1), ('macos', after, 0, 0)]:
        exact = methods(source.decode().replace('\r\n', '\n'))
        output = temp / name
        cpp = temp / (name + '.cpp')
        cpp.write_text(prelude.replace('/* NATIVE_METHODS */', exact) + harness)
        subprocess.run(['g++', '-std=c++23', '-Wall', '-Wextra', '-Werror', '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-D__APPLE__=1', f'-DTARGET_OS_IOS={ios}', f'-DEXPECT_URGENT={urgent}', str(cpp), '-o', str(output)], check=True)
        subprocess.run([str(output)], check=True, timeout=15)
print('PASS patch0060 applies after exact first59 and reverses; native constructors and report methods preserve desktop policy. Actual iOS/Vulkan loading and performance require device verification.')

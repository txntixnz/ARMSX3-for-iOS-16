"""Build133 pre-allocation cache reclamation and diagnostic overhead contracts.

Compile exact new renderer method, native cache quota/eviction/pressure methods,
and production log-sync policy. GPU submission/completion, image storage, FXO and
GC are host interfaces. Real MoltenVK/A15 memory and performance need phone tests.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
pin='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
paths=['rpcs3/Emu/RSX/VK/VKGSRender.cpp','rpcs3/Emu/RSX/VK/VKGSRender.h',
       'rpcs3/Emu/RSX/VK/VKDraw.cpp','rpcs3/Emu/RSX/VK/VKTextureCache.cpp']
def original(path):return subprocess.check_output(['git','show',pin+':'+path],cwd=native).decode()
prelude=r'''
#include "LogSyncPolicy.h"
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <mutex>
#include <set>
#include <stdexcept>
#include <thread>
#include <vector>
using u32=std::uint32_t;using u64=std::uint64_t;
constexpr u64 MiB=0x100000;
template<class T>T ensure(T value){assert(value);return value;}
struct Log{template<class...T>void warning(const char*,T...)const{}}rsx_log;
namespace rsx{
 enum class problem_severity{low,moderate,severe,fatal};
 struct RendererIdentity{bool is_current_thread()const{return true;}};
 RendererIdentity identity;RendererIdentity*get_current_renderer(){return &identity;}
 namespace texture_upload_context{constexpr u32 shader_read=1,blit_engine_src=2,framebuffer_storage=4;}
}
u64 allocated=0,pending_delete=0;bool gpu_complete=false,fail_wait=false;
unsigned drains=0,pressure_calls=0,hard_syncs=0,lock_refusals=0;
namespace vk{
 constexpr int VMM_ALLOCATION_POOL_TEXTURE_CACHE=3;
 u64 vmm_get_application_pool_usage(int){return allocated;}
 u64 get_budgetable_device_memory(u64 value){return value;}
 bool uninterruptible=false;bool is_uninterruptible(){return uninterruptible;}
 struct driver_manager_thread{void drain(){++drains;assert(gpu_complete);assert(allocated>=pending_delete);allocated-=pending_delete;pending_delete=0;}};
 struct MemoryMap{u64 device_local_total_bytes=1024*MiB;};
 struct Device{MemoryMap map;auto&get_memory_mapping(){return map;}};
 struct Region{
  u32 address=0,context=rsx::texture_upload_context::shader_read;u64 bytes=0;
  bool dirty=false,locked=true,exists=true;unsigned*unreleased=nullptr;
  bool is_dirty()const{return dirty;}u32 get_context()const{return context;}
  bool is_locked(bool=false)const{return locked;}u32 get_section_base()const{return address;}
  void set_dirty(bool value){if(value&&!dirty)++*unreleased;dirty=value;}
  void discard(bool){locked=false;}
 };
 struct Storage:std::vector<std::vector<Region>>{
  unsigned m_unreleased_texture_objects=0;
  void purge_unreleased_sections(){
   for(auto&block:*this)for(auto&r:block)if(r.exists&&r.dirty&&!r.locked){assert(gpu_complete);r.exists=false;pending_delete+=r.bytes;}
   m_unreleased_texture_objects=0;
  }
  bool purge_unlocked_sections(){
   bool changed=false;for(auto&block:*this)for(auto&r:block)if(r.exists&&!r.locked&&r.context!=rsx::texture_upload_context::framebuffer_storage){assert(gpu_complete);r.exists=false;pending_delete+=r.bytes;changed=true;}return changed;
  }
 };
 class texture_cache{
 public:
  using problem_severity=rsx::problem_severity;
  Device device;Device*m_device=&device;std::mutex m_cache_mutex;Storage m_storage;
  struct thrashed_set{bool violation_handled=false;std::vector<Region*>sections_to_unprotect;};
  void unprotect_set(thrashed_set&set){for(auto*r:set.sections_to_unprotect)r->locked=false;}
  bool is_overallocated()const;
  /* NATIVE_PRESSURE */
  /* NATIVE_EVICT */
  void add(u32 address,u64 bytes,u32 context=rsx::texture_upload_context::shader_read){
   if(allocated+bytes>440*MiB)throw std::runtime_error("modeled driver allocation refusal");
   if(m_storage.empty())m_storage.emplace_back();
   m_storage[0].push_back({address,context,bytes,false,true,true,&m_storage.m_unreleased_texture_objects});allocated+=bytes;
  }
 };
}
using namespace vk;
struct VKGSRender;
struct FXO{vk::driver_manager_thread driver;template<class T>T&get(){return driver;}}fxo;
auto*g_fxo=&fxo;
struct VKGSRender{
 enum flush_queue_state:u32{ok=0,flushing=1,deadlock=2};u32 m_queue_status=ok;
 u64 m_ios_texture_cache_next_check=192*MiB;std::atomic<bool>m_samplers_dirty=false;
 vk::texture_cache m_texture_cache;std::set<u32>exclusions;
 bool is_current_thread()const{return true;}
 bool on_vram_exhausted(rsx::problem_severity severity){
  assert(severity==rsx::problem_severity::fatal);++pressure_calls;++hard_syncs;
  if(fail_wait){throw std::runtime_error("GPU wait failed");}
  gpu_complete=true;
  bool result=m_texture_cache.evict_unused(exclusions);
  result|=m_texture_cache.handle_memory_pressure(severity);
  ++hard_syncs;return result; // Native fatal path's second sync retires queued deletions.
 }
 void reclaim_texture_cache();
};
VKGSRender*current=nullptr;
/* NATIVE_QUOTA */
/* NATIVE_RECLAIM */
'''
cases=r'''
void reset(VKGSRender&renderer){current=&renderer;allocated=0;pending_delete=0;gpu_complete=false;fail_wait=false;drains=pressure_calls=hard_syncs=0;vk::uninterruptible=false;}
void log_policy(){
 ARMSX3LogSyncPolicy policy;unsigned syncs=0;
 for(unsigned t=1;t<100000;t++)syncs+=policy.should_sync("P4 core: routine warning",t);
 assert(syncs==1);assert(policy.should_sync("RUNTIME core fatal observed",100001));
 assert(policy.should_sync("INPUT: START pressed",100002));assert(policy.should_sync("RENDER UI FAIL",100003));
 assert(!policy.should_sync("P4 core: regular",1000000));assert(policy.should_sync("P4 core: regular",1000001));
 std::atomic<unsigned>concurrent=0;std::vector<std::thread>threads;
 for(int i=0;i<8;i++)threads.emplace_back([&]{for(int j=0;j<10000;j++)if(policy.should_sync("P4 core: concurrent",9000000))++concurrent;});
 for(auto&t:threads){t.join();}
 assert(concurrent==1);
}
void budgets(){
 VKGSRender renderer;reset(renderer);
 allocated=192*MiB;assert(!renderer.m_texture_cache.is_overallocated());
 allocated=193*MiB;
#if TARGET_OS_IOS
 assert(renderer.m_texture_cache.is_overallocated());
#else
 assert(!renderer.m_texture_cache.is_overallocated());allocated=308*MiB;assert(renderer.m_texture_cache.is_overallocated());
#endif
 renderer.reclaim_texture_cache();
#if !TARGET_OS_IOS
 assert(pressure_calls==0&&drains==0);return;
#endif
 allocated=0;
}
void safe_reclaim(){
 VKGSRender renderer;reset(renderer);auto&cache=renderer.m_texture_cache;
 renderer.exclusions.insert(0x1000);cache.add(0x1000,32*MiB);
 cache.add(0x2000,16*MiB,rsx::texture_upload_context::framebuffer_storage);
 for(unsigned i=0;i<38;i++)cache.add(0x10000+i*0x1000,4*MiB);
 const u64 before=allocated;assert(before==200*MiB);
 for(auto state:{VKGSRender::flushing,VKGSRender::deadlock}){renderer.m_queue_status=state;renderer.reclaim_texture_cache();}
 renderer.m_queue_status=VKGSRender::ok;vk::uninterruptible=true;renderer.reclaim_texture_cache();vk::uninterruptible=false;
 assert(pressure_calls==0&&allocated==before);
 renderer.reclaim_texture_cache();
#if TARGET_OS_IOS
 assert(pressure_calls==1&&hard_syncs==2&&drains==1);
 assert(allocated==48*MiB&&pending_delete==0&&renderer.m_samplers_dirty);
 assert(cache.m_storage[0][0].exists&&cache.m_storage[0][1].exists);
 // Long streaming load: resident allocations must stay below the old refusal.
 u64 peak=allocated;
 for(unsigned i=0;i<2048;i++){
  renderer.reclaim_texture_cache();gpu_complete=false;cache.add(0x100000+i*0x1000,4*MiB);peak=std::max(peak,allocated);
 }
 assert(peak<=212*MiB&&pressure_calls>40);
 // This old allocator-time call occurs while another owner holds the cache lock.
 std::atomic<bool>held=false,release=false;
 std::thread holder([&]{std::lock_guard lock(cache.m_cache_mutex);held=true;while(!release)std::this_thread::yield();});
 while(!held){std::this_thread::yield();}
 assert(!cache.evict_unused(renderer.exclusions));release=true;holder.join();
#else
 assert(pressure_calls==0&&allocated==before);
#endif
}
void pinned_set(){
 VKGSRender renderer;reset(renderer);auto&cache=renderer.m_texture_cache;
 for(unsigned i=0;i<49;i++){cache.add(i*0x1000,4*MiB);renderer.exclusions.insert(i*0x1000);}
 renderer.reclaim_texture_cache();
#if TARGET_OS_IOS
 assert(pressure_calls==1&&allocated==196*MiB);
 for(int i=0;i<100;i++){renderer.reclaim_texture_cache();}
 assert(pressure_calls==1);
 cache.add(0x100000,15*MiB);renderer.exclusions.insert(0x100000);renderer.reclaim_texture_cache();assert(pressure_calls==1);
 cache.add(0x200000,2*MiB);renderer.exclusions.insert(0x200000);renderer.reclaim_texture_cache();assert(pressure_calls==2);
#endif
}
void failed_sync(){
 VKGSRender renderer;reset(renderer);auto&cache=renderer.m_texture_cache;cache.add(0x1000,200*MiB);fail_wait=true;
 bool failed=false;try{renderer.reclaim_texture_cache();}catch(const std::runtime_error&){failed=true;}
#if TARGET_OS_IOS
 assert(failed&&allocated==200*MiB&&pending_delete==0&&drains==0&&cache.m_storage[0][0].exists);
 assert(renderer.m_ios_texture_cache_next_check==192*MiB);
#else
 assert(!failed&&allocated==200*MiB);
#endif
}
int main(int argc,char**argv){
 if(argc>1){VKGSRender renderer;reset(renderer);for(unsigned i=0;i<120;i++){renderer.reclaim_texture_cache();renderer.m_texture_cache.add(i*0x1000,4*MiB);}return 0;}
 (void)argv;log_policy();budgets();safe_reclaim();pinned_set();failed_sync();
 std::puts("PASS: native cache quota/eviction, protected active textures and render targets, pre-allocation purge/GC completion, bounded repeated reclaim, failed-sync ownership and paced log syncing; GPU/phone performance remains unverified");
}
'''
with tempfile.TemporaryDirectory(prefix='armsx3-menu133-') as directory:
 directory=Path(directory)
 for path in paths:
  target=directory/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(original(path))
 for patch in sorted((root/'patches').glob('*.patch')):
  subprocess.run(['git','apply',*[f'--include={p}' for p in paths],str(patch)],cwd=directory,check=True,capture_output=True)
 cpp=(directory/paths[0]).read_text();header=(directory/paths[1]).read_text();draw=(directory/paths[2]).read_text();texture=(directory/paths[3]).read_text()
 method=cpp[cpp.index('void VKGSRender::reclaim_texture_cache()'):cpp.index('void VKGSRender::retire_completed_work()')]
 quota=texture[texture.index('\tbool texture_cache::is_overallocated()'):texture.rindex('\n}')]
 common=original('rpcs3/Emu/RSX/Common/texture_cache.h')
 pressure=common[common.index('\t\tvirtual bool handle_memory_pressure('):common.index('\n\t\tvoid trim_sections()')].replace('virtual bool','bool',1)
 evict=common[common.index('\t\tbool evict_unused('):common.index('\n\t\t// Expands a _3d_unwrap descriptor')]
 assert 'm_ios_texture_cache_next_check = 192ull * 0x100000' in header
 for source,start,end in [(draw,'void VKGSRender::load_texture_env()','std::lock_guard lock(m_sampler_mutex)'),(cpp,'bool VKGSRender::scaled_image_from_memory(','vk::gpu_scope blit_gpu_scope')]:
  body=source[source.index(start):];assert body.index('reclaim_texture_cache();')<body.index(end)
 assert cpp.index('iOS Vulkan teardown BEFORE DMA sync.')<cpp.index('iOS Vulkan teardown BEFORE device idle.')<cpp.index('iOS Vulkan teardown AFTER device idle.')<cpp.index('iOS Vulkan teardown BEFORE async scheduler join.')<cpp.index('iOS Vulkan teardown BEFORE shader compiler join.')
 # The production callback still hard-syncs before eviction and after purging.
 callback=cpp[cpp.index('bool VKGSRender::on_vram_exhausted('):cpp.index('void VKGSRender::on_descriptor_pool_fragmentation(')]
 assert callback.index('flush_command_queue(true, true)')<callback.index('m_texture_cache.evict_unused(exclusion_list)')<callback.rindex('flush_command_queue(true, true)')
 runtime=(root/'core/loadtest/Runtime.cpp').read_text();assert 'configuration.core.ppu_call_history.set(!render)' in runtime
 interpreter=original('rpcs3/Emu/Cell/PPUInterpreter.cpp');assert 'if (g_cfg.core.ppu_call_history)\n\t\tselected += set_call_history;' in interpreter
 assert 'ppu.syscall_history.index++' in original('rpcs3/Emu/Cell/PPUFunction.h')
 startup=(root/'ios/src/StartupLog.mm').read_text();assert startup.index('write(fd,')<startup.index('sync_policy.should_sync')<startup.index('fsync(fd)')
 source=prelude.replace('/* NATIVE_PRESSURE */',pressure).replace('/* NATIVE_EVICT */',evict).replace('/* NATIVE_QUOTA */',quota).replace('/* NATIVE_RECLAIM */',method)+cases
 for name,ios,text in [('ios',1,source),('desktop',0,source),('old-no-preflight',1,source.replace(method,'void VKGSRender::reclaim_texture_cache(){}\n'))]:
  file=directory/(name+'.cpp');file.write_text(text);output=directory/name
  subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-D__APPLE__=1',f'-DTARGET_OS_IOS={ios}','-I',str(root/'ios/src'),str(file),'-o',str(output)],check=True,timeout=120)
  result=subprocess.run([str(output)]+(['negative'] if name=='old-no-preflight' else []),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
  if name=='old-no-preflight':
   assert result.returncode!=0 and b'modeled driver allocation refusal' in result.stderr;print('PASS: old loading path reproduces modeled 440 MiB allocation refusal')
  else:
   if result.returncode:sys.stderr.buffer.write(result.stderr)
   result.check_returncode();print(result.stdout.decode().strip())

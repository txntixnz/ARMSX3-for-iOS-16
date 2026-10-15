"""Build134: reclaim completed idle allocations before evicting cached pixels.

Compile exact native image retirement ctor/dtor, idle trim, quota, and renderer
preflight. GPU completion, content lookup, FXO and fatal eviction are host
interfaces; the historical Build133 test separately covers native eviction.
"""
from pathlib import Path
import re,subprocess,sys,tempfile
root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
pin='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
paths=['rpcs3/Emu/RSX/VK/VKGSRender.cpp','rpcs3/Emu/RSX/VK/VKGSRender.h',
       'rpcs3/Emu/RSX/VK/VKTextureCache.cpp','rpcs3/Emu/RSX/VK/VKTextureCache.h']
model=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <stdexcept>
#include <thread>
#include <vector>
using u32=std::uint32_t;using u64=std::uint64_t;constexpr u64 MiB=0x100000;
template<class T>using atomic_t=std::atomic<T>;
template<class T>void ensure(const T&value){assert(value);}
struct Log{template<class...T>void warning(const char*,T...)const{}}rsx_log;
namespace rsx{enum class problem_severity{low,moderate,severe,fatal};}
std::atomic<u64>allocated=0;u64 uploads=0;unsigned evictions=0,drains=0,hard_syncs=0;
bool fail_wait=false;
namespace vk{
 constexpr int VK_IMAGE_LAYOUT_UNDEFINED=0,VK_QUEUE_FAMILY_IGNORED=-1,VMM_ALLOCATION_POOL_TEXTURE_CACHE=3;
 struct Allocation{
  const u64 bytes;explicit Allocation(u64 value):bytes(value){allocated+=bytes;}
  ~Allocation(){allocated-=bytes;}u64 size()const{return bytes;}
 };
 struct viewable_image{
  bool completed=false;const u64 id;std::unique_ptr<Allocation>memory;
  int current_layout=7,current_queue_family=1;
  struct{unsigned imageType=1,flags=0,sharingMode=0;}info;
  viewable_image(u64 key,u64 bytes):id(key),memory(std::make_unique<Allocation>(bytes)){}
  ~viewable_image(){assert(completed);} // No freeing a GPU-owned allocation.
  int format()const{return 0;}u64 width()const{return id;}int height()const{return 1;}
  int depth()const{return 1;}int mipmaps()const{return 1;}
 };
 template<class...T>u64 hash_image_properties(int,u64 width,T...){return width;}
 struct MemoryMap{u64 device_local_total_bytes=1024*MiB;};
 struct Device{MemoryMap map;auto&get_memory_mapping(){return map;}};
 u64 get_budgetable_device_memory(u64 value){return value;}
 u64 vmm_get_application_pool_usage(int){return allocated.load();}
 bool uninterruptible=false;bool is_uninterruptible(){return uninterruptible;}
 class texture_cache{
 public:
  /* NATIVE_IMAGE_RECORDS */
  Device device;Device*m_device=&device;
  std::deque<cached_image_t>m_cached_images;atomic_t<u64>m_cached_memory_size{0};
  std::mutex m_cached_pool_lock;atomic_t<bool>m_cache_is_exiting=false;
  std::map<u64,std::unique_ptr<viewable_image>>content;
  std::set<u64>framebuffers;
  std::vector<std::unique_ptr<cached_image_reference_t>>pending;
  ~texture_cache(){
   m_cache_is_exiting=true;complete_gpu();pending.clear();content.clear();trim_reusable_images(0);
  }
  void use(u64 id,u64 bytes=8*MiB){
   auto&image=content[id];if(!image){image=std::make_unique<viewable_image>(id,bytes);uploads+=bytes;}
   image->completed=false;
  }
  void retire_idle(u64 id,u64 bytes){
   auto image=std::make_unique<viewable_image>(id,bytes);
   pending.push_back(std::make_unique<cached_image_reference_t>(this,image));
  }
  void complete_gpu(){
   for(auto&[id,image]:content){(void)id;image->completed=true;}
   for(auto&entry:pending)entry->data->completed=true;
  }
  void drain_completed(){
   for(auto&entry:pending)assert(entry->data->completed);
   pending.clear(); // Exact native dtors publish to the reusable pool only here.
  }
  void evict_content(const std::set<u64>&excluded){
   for(auto it=content.begin();it!=content.end();){
    if(excluded.contains(it->first)||framebuffers.contains(it->first)){++it;continue;}
    pending.push_back(std::make_unique<cached_image_reference_t>(this,it->second));
    it=content.erase(it);
   }
  }
  bool is_overallocated()const;
  u64 trim_reusable_images(u64 keep_bytes);
 };
 /* NATIVE_RETIREMENT */
 /* NATIVE_TRIM */
 /* NATIVE_QUOTA */
 struct driver_manager_thread{void drain();};
}
using namespace vk;
struct FXO{driver_manager_thread driver;template<class T>T&get(){return driver;}}fxo;auto*g_fxo=&fxo;
struct VKGSRender{
 enum flush_queue_state:u32{ok=0,flushing=1,deadlock=2};u32 m_queue_status=ok;
 u64 m_ios_texture_cache_next_check=WATERMARK*MiB;
 std::atomic<bool>m_samplers_dirty=false;texture_cache m_texture_cache;
 std::set<u64>exclusions;
 bool is_current_thread()const{return true;}
 bool on_vram_exhausted(rsx::problem_severity severity){
  assert(severity==rsx::problem_severity::fatal);++hard_syncs;
  if(fail_wait)throw std::runtime_error("GPU wait failed");
  m_texture_cache.complete_gpu();m_texture_cache.drain_completed();
  m_texture_cache.trim_reusable_images(0); // Native fatal-pressure cleanup drops existing reusable images.
  ++evictions;m_texture_cache.evict_content(exclusions);
  ++hard_syncs;m_texture_cache.complete_gpu();return true;
 }
 void reclaim_texture_cache();
};
VKGSRender*current=nullptr;
void vk::driver_manager_thread::drain(){++drains;current->m_texture_cache.drain_completed();}
/* NATIVE_PREFLIGHT */
'''
cases=r'''
void begin(VKGSRender&r){assert(allocated==0);uploads=evictions=drains=hard_syncs=0;fail_wait=false;current=&r;vk::uninterruptible=false;}
void native_retirement(){
 VKGSRender renderer;begin(renderer);auto&cache=renderer.m_texture_cache;
 cache.retire_idle(11,8*MiB);cache.retire_idle(12,8*MiB);
 assert(cache.m_cached_images.empty()&&cache.trim_reusable_images(0)==0&&allocated==16*MiB);
 cache.complete_gpu();cache.drain_completed();assert(cache.m_cached_images.size()==2&&cache.m_cached_memory_size==16*MiB);
 assert(cache.m_cached_images.front().key==12&&cache.m_cached_images.back().key==11);
 assert(cache.m_cached_images.front().data->current_layout==VK_IMAGE_LAYOUT_UNDEFINED);
 assert(cache.trim_reusable_images(8*MiB)==8*MiB&&cache.m_cached_images.front().key==12&&allocated==8*MiB);
 assert(cache.trim_reusable_images(8*MiB)==0&&cache.trim_reusable_images(0)==8*MiB&&allocated==0);
}
void idle_first(){
 VKGSRender renderer;begin(renderer);auto&cache=renderer.m_texture_cache;
 for(unsigned i=0;i<25;i++)cache.use(i); // 200MiB useful content.
 cache.retire_idle(1000,104*MiB);cache.complete_gpu();cache.drain_completed();
 assert(allocated==304*MiB);renderer.reclaim_texture_cache();
#if TARGET_OS_IOS
 assert(allocated==200*MiB&&cache.content.size()==25);
 assert(evictions==0&&drains==0&&hard_syncs==0&&!renderer.m_samplers_dirty);
#else
 assert(allocated==304*MiB&&cache.content.size()==25&&evictions==0);
#endif
}
void repeated_scene(bool historical){
 VKGSRender renderer;begin(renderer);auto&cache=renderer.m_texture_cache;
 u64 peak=0;
 // 200MiB static scene; completed temporary images accumulate between draws.
 for(unsigned frame=0;frame<120;frame++){
  cache.complete_gpu();cache.drain_completed();
  cache.retire_idle(10000+frame,64*MiB);cache.complete_gpu();cache.drain_completed();
  for(unsigned texture=0;texture<25;texture++){
   renderer.exclusions={texture};renderer.reclaim_texture_cache();
   cache.use(texture);peak=std::max(peak,allocated.load());
  }
 }
 if(historical){
  assert(evictions>100&&uploads>10*1024*MiB);
  std::printf("PASS historical192MiB policy: %lluMiB uploads, %u content evictions\n",static_cast<unsigned long long>(uploads/MiB),evictions);
 }else{
#if TARGET_OS_IOS
  assert(uploads==200*MiB&&evictions==0&&hard_syncs==0&&peak<=336*MiB);
  std::printf("PASS warm scene: %lluMiB uploaded once across120frames; idle pools trimmed; zero content evictions/hard syncs\n",static_cast<unsigned long long>(uploads/MiB));
#else
  assert(evictions==0&&hard_syncs==0); // Desktop policy remains outside this helper.
#endif
 }
}
void real_pressure(){
 VKGSRender renderer;begin(renderer);auto&cache=renderer.m_texture_cache;
 cache.use(1,200*MiB);cache.use(2,120*MiB);cache.use(3,16*MiB);
 cache.framebuffers.insert(3);renderer.exclusions={1};
 renderer.reclaim_texture_cache();
#if TARGET_OS_IOS
 assert(evictions==1&&drains==1&&hard_syncs==2&&renderer.m_samplers_dirty);
 assert(cache.content.contains(1)&&cache.content.contains(3)&&!cache.content.contains(2));
 assert(cache.m_cached_images.empty()&&cache.m_cached_memory_size==0&&allocated==216*MiB);
 for(int i=0;i<100;i++){renderer.reclaim_texture_cache();}assert(evictions==1);
#else
 assert(evictions==0&&allocated==336*MiB);
#endif
}
void failure_and_gates(){
 VKGSRender renderer;begin(renderer);auto&cache=renderer.m_texture_cache;cache.use(1,320*MiB);
 for(auto state:{VKGSRender::flushing,VKGSRender::deadlock}){renderer.m_queue_status=state;renderer.reclaim_texture_cache();}
 renderer.m_queue_status=VKGSRender::ok;vk::uninterruptible=true;renderer.reclaim_texture_cache();vk::uninterruptible=false;
 assert(evictions==0&&allocated==320*MiB);
 fail_wait=true;bool failed=false;try{renderer.reclaim_texture_cache();}catch(const std::runtime_error&){failed=true;}
#if TARGET_OS_IOS
 assert(failed&&cache.content.contains(1)&&allocated==320*MiB&&drains==0);
#else
 assert(!failed&&evictions==0);
#endif
}
void concurrent_retirement(){
 VKGSRender renderer;begin(renderer);auto&cache=renderer.m_texture_cache;
 std::atomic<bool>done=false;
 std::thread producer([&]{for(unsigned i=0;i<4096;i++){
  auto image=std::make_unique<viewable_image>(i,65536);image->completed=true;
  auto ref=std::make_unique<texture_cache::cached_image_reference_t>(&cache,image);
  ref.reset(); // Completed driver-GC callback racing the pool trimmer.
 }done=true;});
 while(!done){cache.trim_reusable_images(2*MiB);}
 producer.join();cache.trim_reusable_images(0);
 assert(allocated==0&&cache.m_cached_memory_size==0&&cache.m_cached_images.empty());
}
int main(int argc,char**){
 if(argc>1){repeated_scene(true);return 0;}
 native_retirement();idle_first();repeated_scene(false);real_pressure();failure_and_gates();concurrent_retirement();
 std::puts("PASS native completion-only image retirement, idle trim order/accounting, content preservation, fallback ownership, skip/failure gates and concurrent pool cleanup; real iOS FPS pending");
}
'''
with tempfile.TemporaryDirectory(prefix='armsx3-reuse134-') as directory:
 directory=Path(directory)
 for path in paths:
  target=directory/path;target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes(subprocess.check_output(['git','show',pin+':'+path],cwd=native))
 patches=sorted((root/'patches').glob('*.patch'))
 for patch in patches:
  if int(patch.name[:4])>67:break
  subprocess.run(['git','apply',*[f'--include={p}' for p in paths],str(patch)],cwd=directory,check=True,capture_output=True)
 old_cpp=(directory/paths[0]).read_text();old_texture=(directory/paths[2]).read_text()
 for patch in patches:
  if int(patch.name[:4])<=67:continue
  subprocess.run(['git','apply',*[f'--include={p}' for p in paths],str(patch)],cwd=directory,check=True,capture_output=True)
 cpp=(directory/paths[0]).read_text();header=(directory/paths[1]).read_text();texture=(directory/paths[2]).read_text();cache_header=(directory/paths[3]).read_text()
 assert 'm_ios_texture_cache_next_check = 288ull * 0x100000' in header
 assert 'u64 trim_reusable_images(u64 keep_bytes);' in cache_header
 record=cache_header[cache_header.index('\t\tstruct cached_image_reference_t'):cache_header.index('\n\tpublic:',cache_header.index('\t\tstruct cached_image_reference_t'))]
 retirement=texture[texture.index('\ttexture_cache::cached_image_reference_t::cached_image_reference_t('):texture.index('\n\tvoid cached_texture_section::dma_transfer(')]
 trim=texture[texture.index('\tu64 texture_cache::trim_reusable_images('):texture.index('\tbool texture_cache::is_overallocated() const')]
 def quota(text):return text[text.index('\tbool texture_cache::is_overallocated() const'):text.rindex('\n}')]
 def preflight(text):return text[text.index('void VKGSRender::reclaim_texture_cache()'):text.index('void VKGSRender::retire_completed_work()')]
 assert preflight(cpp).index('trim_reusable_images(idle_reserve)')<preflight(cpp).index('on_vram_exhausted(')
 assert preflight(cpp).rindex('trim_reusable_images(idle_reserve)')>preflight(cpp).index('driver_manager_thread>().drain()')
 common=model.replace('/* NATIVE_IMAGE_RECORDS */',record).replace('/* NATIVE_RETIREMENT */',retirement).replace('/* NATIVE_TRIM */',trim)
 for name,ios,source,watermark,profile in [('ios',1,cpp,288,[]),('desktop',0,cpp,288,[]),('old192',1,old_cpp,192,['historical'])]:
  text=common.replace('WATERMARK',str(watermark)).replace('/* NATIVE_QUOTA */',quota(old_texture if name=='old192' else texture)).replace('/* NATIVE_PREFLIGHT */',preflight(source))+cases
  file=directory/(name+'.cpp');file.write_text(text);output=directory/name
  subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-D__APPLE__=1',f'-DTARGET_OS_IOS={ios}',str(file),'-o',str(output)],check=True,timeout=120)
  subprocess.run([str(output),*profile],check=True,timeout=30)

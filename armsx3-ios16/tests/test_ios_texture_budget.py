"""Compile current native budget selection, view tags, quota, trim and preflight.

GPU fences, allocations, VM page protection, section storage and deferred GC are
explicit host interfaces. This checks cache policy/ownership, not phone FPS.
"""
from pathlib import Path
import os, subprocess, sys, tempfile

root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
pin='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
paths=['rpcs3/Emu/RSX/Common/texture_cache.h','rpcs3/Emu/RSX/VK/VKTextureCache.h',
       'rpcs3/Emu/RSX/VK/VKTextureCache.cpp','rpcs3/Emu/RSX/VK/VKGSRender.cpp']

def block(source,marker):
    start=source.index(marker);opening=source.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]

model=r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <memory>
#include <mutex>
#include <set>
#include <stdexcept>
#include <vector>
using u32=std::uint32_t;using u64=std::uint64_t;constexpr u64 MiB=0x100000;
template<class T>using atomic_t=std::atomic<T>;
template<class T>void ensure(const T&v){assert(v);}
struct Log{template<class...T>void warning(const char*,T...)const{}}rsx_log;
struct TestMutex{
 bool held=false,refuse=false;
 void lock(){assert(!held&&!refuse);held=true;}void unlock(){assert(held);held=false;}
 bool try_lock(){if(held||refuse)return false;held=true;return true;}
};
u64 allocated=0,uploads=0;unsigned syncs=0,drains=0,fail_sync=0;
namespace rsx{
 namespace texture_upload_context{constexpr u32 shader_read=1,blit_engine_src=2,framebuffer_storage=4,blit_engine_dst=8;}
 struct Identity{bool is_current_thread()const{return true;}}identity;
 Identity*get_current_renderer(){return &identity;}
 std::atomic<u64>tag=1;u64 get_shared_tag(){return tag++;}
 struct texture_channel_remap_t{};texture_channel_remap_t default_remap_vector;
 struct Texture{u32 address=0xffff0000;u32 offset()const{return address;}u32 location()const{return 0;}};
 u32 get_address(u32 value,u32){return value;}
 struct{std::array<Texture,16>fragment_textures;std::array<Texture,4>vertex_textures;}method_registers;
 enum class problem_severity{low,moderate,severe,fatal};
}
namespace vk{
 constexpr int VMM_ALLOCATION_POOL_TEXTURE_CACHE=3;
 u64 vmm_get_application_pool_usage(int){return allocated;}
 bool uninterruptible=false;bool is_uninterruptible(){return uninterruptible;}
 u64 get_budgetable_device_memory(u64 value){return value;}
 struct Memory{u64 bytes;explicit Memory(u64 n):bytes(n){allocated+=n;}~Memory(){allocated-=bytes;}u64 size()const{return bytes;}};
 struct image_view{};
 struct Image{
  std::unique_ptr<Memory>memory;bool completed=false;image_view view;
  explicit Image(u64 n):memory(std::make_unique<Memory>(n)){}
  ~Image(){assert(completed);} // No GPU-owned allocation may be freed.
  image_view*get_view(const rsx::texture_channel_remap_t&){return &view;}
 };
 struct Region;std::vector<Region*>live_regions;
 struct Range{u64 start,end;bool overlaps(const Range&other)const{return start<=other.end&&other.start<=end;}};
 struct Region{
  u32 address=0,context=rsx::texture_upload_context::shader_read;
  bool dirty=false,locked=true,page_locked=true,managed=true,unreleased=false;
  atomic_t<u64>ios_last_use_tag{0};std::unique_ptr<Image>image;Image*vram_texture=nullptr;
  Range pages{};const Range&get_locked_range()const{return pages;}
  bool is_dirty()const{return dirty;}bool exists()const{return bool(image);}
  bool is_managed()const{return managed;}u32 get_context()const{return context;}
  u32 get_section_base()const{return address;}bool is_locked(bool actual=false)const{return locked&&(!actual||page_locked);}
  void set_dirty(bool value){dirty=value;unreleased=dirty&&!locked;}
  void discard(bool value){locked=false;if(value||context==rsx::texture_upload_context::shader_read)set_dirty(true);}
  void unprotect();
  Image*get_raw_texture(){return image.get();}
  /* NATIVE_VIEW */
  /* NATIVE_RAW_VIEW */
 };
 void Region::unprotect(){
  for(auto*other:live_regions)assert(other==this||!other->is_locked(true)||!other->pages.overlaps(pages));
  locked=false;if(context==rsx::texture_upload_context::shader_read)set_dirty(true);
 }
 struct Map{u64 device_local_total_bytes=1024*MiB;};
 struct Device{Map map;auto&get_memory_mapping(){return map;}};
 struct texture_cache{
  using section_storage_type=Region;Device device;Device*m_device=&device;
  TestMutex m_cache_mutex;std::deque<std::deque<Region>>m_storage;
  struct thrashed_set{bool violation_handled=false;std::vector<Region*>sections_to_unprotect;};
  struct Cached{std::unique_ptr<Image>data;};
  std::mutex m_cached_pool_lock;std::deque<Cached>m_cached_images;atomic_t<u64>m_cached_memory_size{0};
  std::vector<std::unique_ptr<Image>>pending;
  texture_cache(){m_storage.emplace_back();}
  ~texture_cache(){complete();pending.clear();m_cached_images.clear();m_storage.clear();live_regions.clear();assert(allocated==0);}
  Region*find(u32 address){for(auto&block:m_storage)for(auto&r:block)if(r.address==address&&r.exists()&&!r.dirty)return &r;return nullptr;}
  Region&use(u32 address,u64 bytes=8*MiB,u32 context=rsx::texture_upload_context::shader_read){
   auto*r=find(address);
   if(!r){
    assert(allocated+bytes<=440*MiB); // Historical modeled allocation boundary.
    r=&m_storage.front().emplace_back();r->address=address;r->context=context;
    r->pages={u64(address)*16384,u64(address)*16384+16383};live_regions.push_back(r);
    r->image=std::make_unique<Image>(bytes);r->vram_texture=r->image.get();uploads+=bytes;
   }
   r->image->completed=false;r->get_view(rsx::default_remap_vector);return *r;
  }
  void complete(){for(auto&b:m_storage)for(auto&r:b)if(r.image)r.image->completed=true;for(auto&p:pending)p->completed=true;}
  void unprotect_set(thrashed_set&set){for(auto*r:set.sections_to_unprotect)r->discard(false);}
  void purge_unreleased_sections(){
   std::lock_guard lock(m_cache_mutex);
   for(auto&b:m_storage)for(auto&r:b)if(r.unreleased&&r.image){
    assert(r.dirty&&!r.locked&&r.image->completed);r.vram_texture=nullptr;pending.push_back(std::move(r.image));
   }
  }
  void drain(){for(auto&p:pending){assert(p->completed);m_cached_memory_size+=p->memory->size();m_cached_images.push_back({std::move(p)});}pending.clear();}
  void idle(u64 bytes){auto image=std::make_unique<Image>(bytes);image->completed=true;m_cached_memory_size+=bytes;m_cached_images.push_back({std::move(image)});}
  bool is_overallocated()const;u64 trim_reusable_images(u64);
  /* NATIVE_BOUNDED */
  /* NATIVE_FULL_EVICTION */
 };
 texture_cache*current=nullptr;
 struct driver_manager_thread{void drain(){++drains;current->drain();}};
 /* NATIVE_QUOTA */
 /* NATIVE_TRIM */
}
using namespace vk;
struct FXO{driver_manager_thread driver;template<class T>T&get(){return driver;}}fxo;auto*g_fxo=&fxo;
struct VKGSRender{
 enum flush_queue_state:u32{ok=0,flushing=1,deadlock=2};u32 m_queue_status=ok;
 texture_cache m_texture_cache;u64 m_ios_texture_cache_next_check=288*MiB;
 std::atomic<bool>m_samplers_dirty=false;std::mutex m_secondary_cb_guard;
 bool is_current_thread()const{return true;}
 void flush_command_queue(bool a,bool b){assert(a&&b);if(++syncs==fail_sync)throw std::runtime_error("failed GPU fence");m_texture_cache.complete();}
 bool on_vram_exhausted(rsx::problem_severity severity){
  assert(HISTORICAL&&severity==rsx::problem_severity::fatal);
  flush_command_queue(true,true);fxo.driver.drain();
  std::set<u32>exclusions;for(auto&tex:rsx::method_registers.fragment_textures)exclusions.insert(tex.address);
  for(auto&tex:rsx::method_registers.vertex_textures)exclusions.insert(tex.address);
  const bool result=m_texture_cache.evict_unused(exclusions);m_texture_cache.purge_unreleased_sections();
  flush_command_queue(true,true);return result;
 }
 void reclaim_texture_cache();
};
/* NATIVE_PREFLIGHT */
void begin(VKGSRender&r){
 assert(allocated==0);uploads=0;syncs=drains=fail_sync=0;vk::uninterruptible=false;current=&r.m_texture_cache;
 for(auto&t:rsx::method_registers.fragment_textures)t.address=0xffff0000;
 for(auto&t:rsx::method_registers.vertex_textures)t.address=0xffff0000;
}
'''

cases=r'''
void warm_scene(){
 VKGSRender r;begin(r);auto&c=r.m_texture_cache;
 for(u32 i=1;i<=16;++i)c.use(i); // 128MiB old scene content.
 for(u32 i=100;i<122;++i)c.use(i); // 176MiB actively rebound scene.
 rsx::method_registers.fragment_textures[0].address=100;
 rsx::method_registers.vertex_textures[0].address=101;
 r.reclaim_texture_cache();
#if TARGET_OS_IOS
 if(!HISTORICAL){
  assert(allocated==256*MiB&&!c.find(1)&&!c.find(6)&&c.find(7));
  for(u32 i=100;i<122;++i)assert(c.find(i));
  assert(syncs==2&&drains==2&&r.m_samplers_dirty&&c.pending.empty()&&c.m_cached_images.empty());
 }
#else
 assert(allocated==304*MiB&&syncs==0&&drains==0&&!r.m_samplers_dirty);
#endif
 for(unsigned frame=0;frame<120;++frame)for(u32 i=100;i<122;++i){r.reclaim_texture_cache();c.use(i);}
 if(HISTORICAL){assert(uploads>304*MiB);std::printf("PASS historical policy: warm payload reuploaded %lluMiB\n",(unsigned long long)(uploads/MiB-304));}
 else{assert(uploads==304*MiB);std::puts("PASS current warm scene: zero repeated payload uploads across120frames; cold batch selected; active/vertex bindings retained");}
}
void eligibility_and_recency(){
 VKGSRender r;begin(r);auto&c=r.m_texture_cache;
 auto&recent=c.use(1);auto&old=c.use(2);auto&active=c.use(3);
 auto&fbo=c.use(4,8*MiB,rsx::texture_upload_context::framebuffer_storage);
 auto&dest=c.use(5,8*MiB,rsx::texture_upload_context::blit_engine_dst);
 auto&borrowed=c.use(6);borrowed.managed=false;
 auto&dirty=c.use(7);dirty.dirty=true;
 auto&blit=c.use(8,8*MiB,rsx::texture_upload_context::blit_engine_src);
 auto&non_page=c.use(9);non_page.page_locked=false;
 const auto tag=recent.ios_last_use_tag.load();recent.get_raw_view();
#if TARGET_OS_IOS
 assert(recent.ios_last_use_tag>tag);
 c.complete();
 const auto bytes=[](auto&region){return region.get_raw_texture()->memory->size();};
 c.m_cache_mutex.refuse=true;assert(c.evict_unused_budgeted({},8*MiB,bytes)==0);c.m_cache_mutex.refuse=false;
 assert(c.evict_unused_budgeted({},0,bytes)==0);
 assert(c.evict_unused_budgeted({3},1,bytes)==8*MiB);
 assert(old.dirty&&!old.locked&&recent.exists()&&!recent.dirty&&!active.dirty);
 assert(!fbo.dirty&&!dest.dirty&&!borrowed.dirty&&!blit.dirty);
 c.purge_unreleased_sections();assert(allocated==72*MiB&&c.pending.size()==1); // GC still owns the image.
 r.flush_command_queue(true,true);fxo.driver.drain();c.trim_reusable_images(0);assert(allocated==64*MiB);
 assert(c.evict_unused_budgeted({1,3},128*MiB,bytes)==16*MiB);
 assert(blit.dirty&&!blit.locked&&non_page.dirty&&!non_page.locked);
 c.purge_unreleased_sections();r.flush_command_queue(true,true);fxo.driver.drain();c.trim_reusable_images(0);
#else
 assert(recent.ios_last_use_tag==tag);(void)old;(void)active;(void)fbo;(void)dest;(void)blit;(void)non_page;
#endif
}
void pressure_and_failures(){
 for(unsigned failure:{0u,1u,2u}){
  VKGSRender r;begin(r);auto&c=r.m_texture_cache;
  for(u32 i=1;i<=38;++i)c.use(i);
  fail_sync=failure;bool failed=false;
  try{r.reclaim_texture_cache();}catch(const std::runtime_error&){failed=true;}
#if TARGET_OS_IOS
  assert(failed==(failure!=0));
  if(failure==1){assert(allocated==304*MiB&&c.find(1)&&c.pending.empty()&&drains==0);}
  if(failure==2){assert(allocated==304*MiB&&c.pending.size()==6&&drains==1);}
  if(!failure)assert(allocated==256*MiB&&c.pending.empty());
#else
  assert(!failed&&allocated==304*MiB);
#endif
 }
 {
  VKGSRender r;begin(r);auto&c=r.m_texture_cache;c.use(1,200*MiB);c.idle(104*MiB);r.reclaim_texture_cache();
#if TARGET_OS_IOS
  assert(allocated==200*MiB&&uploads==200*MiB&&syncs==0&&!r.m_samplers_dirty);
#else
  assert(allocated==304*MiB);
#endif
 }
 {
  VKGSRender r;begin(r);auto&c=r.m_texture_cache;c.use(1,304*MiB);
  rsx::method_registers.fragment_textures[0].address=1;r.reclaim_texture_cache();
#if TARGET_OS_IOS
  assert(allocated==304*MiB&&c.find(1)&&syncs==1&&drains==1&&!r.m_samplers_dirty);
  const auto checks=syncs;for(unsigned i=0;i<100;++i)r.reclaim_texture_cache();assert(syncs==checks);
  assert(r.m_ios_texture_cache_next_check==320*MiB);
#else
  assert(syncs==0&&c.find(1));
#endif
 }
 {
  VKGSRender r;begin(r);auto&c=r.m_texture_cache;c.use(1,200*MiB);
  c.pending.push_back(std::make_unique<Image>(104*MiB));r.reclaim_texture_cache();
#if TARGET_OS_IOS
  assert(allocated==200*MiB&&syncs==1&&drains==1&&!r.m_samplers_dirty&&c.find(1));
#else
  assert(allocated==304*MiB&&syncs==0);
#endif
 }
 for(auto gate:{1u,2u,3u}){
  VKGSRender r;begin(r);r.m_texture_cache.use(1,304*MiB);
  if(gate==1)vk::uninterruptible=true;else r.m_queue_status=gate==2?VKGSRender::flushing:VKGSRender::deadlock;
  r.reclaim_texture_cache();assert(allocated==304*MiB&&syncs==0&&!r.m_samplers_dirty);
 }
}
void shared_pages(){
#if TARGET_OS_IOS
 VKGSRender r;begin(r);auto&c=r.m_texture_cache;
 auto&first=c.use(1);auto&alias=c.use(2);alias.pages=first.pages;
 auto&other=c.use(3);auto&fbo=c.use(4,8*MiB,rsx::texture_upload_context::framebuffer_storage);fbo.pages=other.pages;
 auto&independent=c.use(5);c.complete();
 const auto bytes=[](auto&region){return region.get_raw_texture()->memory->size();};
 assert(c.evict_unused_budgeted({},100*MiB,bytes)==8*MiB);
 assert(!first.dirty&&!alias.dirty&&!other.dirty&&!fbo.dirty&&independent.dirty);
 assert(first.is_locked(true)&&alias.is_locked(true)&&other.is_locked(true)&&fbo.is_locked(true));
 c.purge_unreleased_sections();r.flush_command_queue(true,true);fxo.driver.drain();c.trim_reusable_images(0);
 assert(allocated==32*MiB);
#endif
}
void stream(){
#if TARGET_OS_IOS
 VKGSRender r;begin(r);auto&c=r.m_texture_cache;c.use(1);c.use(2);
 rsx::method_registers.fragment_textures[0].address=1;rsx::method_registers.vertex_textures[0].address=2;
 u64 peak=allocated;
 for(u32 i=100;i<1124;++i){r.reclaim_texture_cache();c.use(i);peak=std::max(peak,allocated);assert(c.find(1)&&c.find(2));}
 assert(uploads==8208*MiB&&peak<=304*MiB&&syncs>0&&r.m_samplers_dirty);
 std::printf("PASS8GiB stream: peak %lluMiB, active images retained and every freed image GPU-completed\n",(unsigned long long)(peak/MiB));
#endif
}
int main(){
 warm_scene();if(HISTORICAL)return 0;
 eligibility_and_recency();pressure_and_failures();shared_pages();stream();
 std::puts("PASS native bounded selection/view tags/288MiB quota/idle trim/preflight; lock refusal, VM discard, both wait failures, exclusion/type gates, streaming and desktop policy; device effect pending");
}
'''

with tempfile.TemporaryDirectory(prefix='armsx3-texture-budget-') as directory:
    work=Path(directory)
    for path in paths:
        file=work/path;file.parent.mkdir(parents=True,exist_ok=True)
        file.write_bytes(subprocess.check_output(['git','-C',str(native),'show',pin+':'+path]))
    before=None
    for patch in sorted((root/'patches').glob('*.patch')):
        if patch.name.startswith('0077'):before=[(work/path).read_text() for path in paths]
        subprocess.run(['git','apply',*['--include='+p for p in paths],str(patch)],cwd=work,check=True,capture_output=True)
    common,header,texture,renderer=[(work/path).read_text() for path in paths]
    assert before is not None
    assert before[2]==texture,'quota/actual-allocation recovery changed'
    assert block(before[0],'bool evict_unused(')==block(common,'bool evict_unused(')
    assert block(before[3],'bool VKGSRender::on_vram_exhausted(')==block(renderer,'bool VKGSRender::on_vram_exhausted(')
    assert '#if defined(__APPLE__) && TARGET_OS_IOS\n\t\tatomic_t<u64> ios_last_use_tag{0};\n#endif' in header
    assert 'm_ios_texture_cache_next_check = 288ull * 0x100000' in (root/'patches/0068-ios-preserve-texture-working-set.patch').read_text()
    bounded=block(common,'template <typename GetBytes>\n\t\tu64 evict_unused_budgeted(')
    full=block(common,'bool evict_unused(')
    view=block(header,'vk::image_view* get_view(');raw_view=block(header,'vk::image_view* get_raw_view(')
    quota=block(texture,'bool texture_cache::is_overallocated() const')
    trim=block(texture,'u64 texture_cache::trim_reusable_images(')
    current=block(renderer,'void VKGSRender::reclaim_texture_cache()')
    old=block(before[3],'void VKGSRender::reclaim_texture_cache()')
    assert current.index('flush_command_queue(true, true)')<current.index('evict_unused_budgeted(')<current.rindex('flush_command_queue(true, true)')
    assert current.index('std::lock_guard lock(m_secondary_cb_guard)')<current.index('evict_unused_budgeted(')
    assert current.rindex('driver_manager_thread>().drain()')<current.rindex('trim_reusable_images(0)')<current.index('m_samplers_dirty.store(true)')
    common_model=model.replace('/* NATIVE_BOUNDED */',bounded).replace('/* NATIVE_FULL_EVICTION */',full)
    common_model=common_model.replace('/* NATIVE_VIEW */',view).replace('/* NATIVE_RAW_VIEW */',raw_view)
    common_model=common_model.replace('/* NATIVE_QUOTA */',quota).replace('/* NATIVE_TRIM */',trim)
    for name,ios,historical,preflight in [('ios',1,0,current),('desktop',0,0,current),('historical',1,1,old)]:
        file=work/(name+'.cpp');file.write_text(common_model.replace('/* NATIVE_PREFLIGHT */',preflight)+cases)
        exe=work/name
        subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined',
                        '-fno-omit-frame-pointer','-D__APPLE__=1',f'-DTARGET_OS_IOS={ios}',f'-DHISTORICAL={historical}',str(file),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'},timeout=30)

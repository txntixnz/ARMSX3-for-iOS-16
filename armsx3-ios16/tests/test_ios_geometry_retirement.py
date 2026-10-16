"""Exact native ring/fence/snapshot and between-draw geometry retirement.

Queue submission, GPU bytes and cache/state consumers are explicit host models.
This reproduces unbounded small-draw growth, not real Vulkan/Metal execution.
"""
from pathlib import Path
import ast, os, re, subprocess, sys, tempfile

root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
pin='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
paths=['rpcs3/Emu/RSX/Common/ring_buffer_helper.h',
       'rpcs3/Emu/RSX/VK/VKGSRenderTypes.hpp','rpcs3/Emu/RSX/VK/VKDataHeapManager.cpp',
       'rpcs3/Emu/RSX/VK/VKGSRender.cpp','rpcs3/Emu/RSX/VK/VKGSRender.h','rpcs3/Emu/RSX/VK/VKDraw.cpp']

def block(source,marker):
    start=source.index(marker);opening=source.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]

# Share the explicit queue/fence interfaces with the upload retirement test;
# loading only this string does not execute that test or its historical cases.
old_test=ast.parse((root/'tests/test_ios_upload_retirement.py').read_text())
model=next(ast.literal_eval(node.value) for node in old_test.body if isinstance(node,ast.Assign)
           and any(isinstance(t,ast.Name) and t.id=='model' for t in node.targets))
strip=lambda s:re.sub(r'^#(?:include[^\n]*|pragma once)\n','',s,flags=re.M)
members=r'''
 void reclaim_geometry_uploads();
 vk::data_heap m_attrib_ring_info,m_index_buffer_ring_info,vertex_env,transform_env,fragment_env;
 struct Cache{unsigned purges=0;bool contains=true;void purge(){++purges;contains=false;}};
 std::unique_ptr<Cache>m_vertex_cache=std::make_unique<Cache>();
 using Bulk=rsx::data_heap::bulk_allocator<256,16>;
 std::unique_ptr<Bulk>m_vertex_env_allocator,m_transform_constants_allocator,m_fragment_constants_allocator;
 u32 m_graphics_state=0,m_interpreter_state=0;
'''
model=model.replace('void reclaim_texture_uploads();',members)

cases=r'''
constexpr u32 env_flags=rsx::vertex_state_dirty|rsx::fragment_state_dirty|rsx::fragment_texture_state_dirty|
 rsx::transform_constants_dirty|rsx::fragment_constants_dirty|rsx::polygon_stipple_pattern_dirty;
void setup(VKGSRender&r){
 vk::wait_status=VK_SUCCESS;vk::before_wait={};vk::uninterruptible=false;
 auto&heaps=vk::data_heap_manager::g_managed_heaps;heaps.clear();
 r.m_attrib_ring_info.setup(64*MiB);r.m_index_buffer_ring_info.setup(16*MiB);
 r.m_texture_upload_buffer_ring_info.setup(64*MiB);
 for(auto*h:{&r.m_attrib_ring_info,&r.m_index_buffer_ring_info,&r.m_texture_upload_buffer_ring_info,
             &r.vertex_env,&r.transform_env,&r.fragment_env}){
  if(h==&r.vertex_env||h==&r.transform_env||h==&r.fragment_env)h->setup(MiB);
  heaps.insert(h);
 }
 r.m_vertex_env_allocator=std::make_unique<VKGSRender::Bulk>(r.vertex_env,16);
 r.m_transform_constants_allocator=std::make_unique<VKGSRender::Bulk>(r.transform_env,16);
 r.m_fragment_constants_allocator=std::make_unique<VKGSRender::Bulk>(r.fragment_env,16);
 for(auto*p:{r.m_vertex_env_allocator.get(),r.m_transform_constants_allocator.get(),r.m_fragment_constants_allocator.get()}){
  p->alloc();assert(p->capacity()==15);
 }
 r.m_graphics_state=rsx::rtt_config_valid;r.m_interpreter_state=0x40000000;
}
void thresholds(){
 VKGSRender r;setup(r);auto&a=r.m_attrib_ring_info;auto&i=r.m_index_buffer_ring_info;
 a.alloc<256>(32*MiB-256);i.alloc<256>(8*MiB-256);
 r.reclaim_geometry_uploads();assert(!r.flushes);
 a.alloc<256>(256);
#if IOS_TEST
 vk::uninterruptible=true;r.reclaim_geometry_uploads();assert(!r.flushes);vk::uninterruptible=false;
 r.m_queue_status.store(VKGSRender::flushing);r.reclaim_geometry_uploads();assert(!r.flushes);r.m_queue_status.store(VKGSRender::ok);
 r.m_queue_status.store(VKGSRender::deadlock);r.reclaim_geometry_uploads();assert(!r.flushes);r.m_queue_status.store(VKGSRender::ok);
 a.heap=false;r.reclaim_geometry_uploads();assert(!r.flushes);a.heap=true;
 i.heap=false;r.reclaim_geometry_uploads();assert(!r.flushes);i.heap=true;
 vk::before_wait=[&]{assert(a.pending_bytes()==32*MiB&&r.m_vertex_cache->purges==0);
  assert(r.m_vertex_env_allocator->capacity()==15&&r.m_graphics_state==rsx::rtt_config_valid);};
 r.reclaim_geometry_uploads();vk::before_wait={};
 assert(r.flushes==1&&a.pending_bytes()==0&&i.pending_bytes()==0);
 assert(r.m_vertex_cache->purges==1&&!r.m_vertex_cache->contains);
 assert((r.m_graphics_state&env_flags)==env_flags&&(r.m_graphics_state&rsx::rtt_config_valid));
 assert(r.m_interpreter_state==(0x40000000|rsx::vertex_program_dirty|rsx::fragment_program_dirty));
 for(auto*p:{r.m_vertex_env_allocator.get(),r.m_transform_constants_allocator.get(),r.m_fragment_constants_allocator.get()}){
  assert(p->capacity()==0);assert(p->alloc()==256&&p->capacity()==15);
 }
 // Index pressure independently triggers reclamation without any texture uploads.
 i.alloc<256>(8*MiB);r.reclaim_geometry_uploads();assert(r.flushes==2&&!i.pending_bytes());
 r.reclaim_geometry_uploads();assert(r.flushes==2);
#else
 r.reclaim_geometry_uploads();assert(!r.flushes&&r.m_vertex_cache->purges==0);
 assert(a.pending_bytes()==32*MiB&&i.pending_bytes()==8*MiB-256);
#endif
}
void failures(){
#if IOS_TEST
 for(auto failure:{VK_TIMEOUT,VK_ERROR_DEVICE_LOST}){
  VKGSRender r;setup(r);r.m_attrib_ring_info.alloc<256>(32*MiB);const auto old_get=r.m_attrib_ring_info.get();
  vk::wait_status=failure;bool failed=false;
  try{r.reclaim_geometry_uploads();}catch(const std::runtime_error&){failed=true;}
  assert(failed&&r.flushes==1&&r.chunks[0].is_pending&&r.chunks[0].heap_snapshot_id);
  assert(r.m_attrib_ring_info.get()==old_get&&r.m_vertex_cache->purges==0);
  assert(r.m_vertex_env_allocator->capacity()==15&&r.m_graphics_state==rsx::rtt_config_valid);
 }
#endif
}
void stream(){
#if IOS_TEST
 VKGSRender r;setup(r);
 auto&a=r.m_attrib_ring_info;auto&i=r.m_index_buffer_ring_info;
 std::vector<u8>vertices(64*MiB),indices(16*MiB);
 struct Range{usz vertex,index;u8 marker;};std::vector<Range>pending;
 vk::before_wait=[&]{for(auto x:pending){
  assert(vertices[x.vertex]==x.marker&&vertices[x.vertex+256*1024-1]==x.marker);
  assert(indices[x.index]==x.marker&&indices[x.index+64*1024-1]==x.marker);
 }pending.clear();};
 // Five GiB of vertices plus 1.25 GiB of indices, no presents or texture uploads.
 for(unsigned n=0;n<20480;++n){
  r.reclaim_geometry_uploads();
  const auto vertex=a.alloc<256>(256*1024),index=i.alloc<256>(64*1024);const auto marker=u8(n%251+1);
  assert(vertex+256*1024<a.size()&&index+64*1024<i.size());
  vertices[vertex]=vertices[vertex+256*1024-1]=marker;
  indices[index]=indices[index+64*1024-1]=marker;pending.push_back({vertex,index,marker});
 }
 r.reclaim_geometry_uploads();
 if(!pending.empty()){auto*last=r.m_current_command_buffer;r.flush_command_queue();CHECK_RESULT(last->wait(FRAME_PRESENT_TIMEOUT));}
 vk::before_wait={};
 assert(pending.empty()&&a.pending_bytes()==0&&i.pending_bytes()==0&&a.grows==0&&i.grows==0);
 assert(a.size()==64*MiB&&i.size()==16*MiB&&r.flushes>=160&&r.flushes<=163);
 // Same workload without the new draw hook must reproduce a driver refusal.
 VKGSRender old;setup(old);bool refused=false;
 try{for(unsigned n=0;n<1024;++n)old.m_attrib_ring_info.alloc<256>(256*1024);}
 catch(const std::runtime_error&e){refused=std::string(e.what())=="driver allocation refused";}
 assert(refused&&old.m_attrib_ring_info.grows==1&&old.flushes==0);
#endif
}
int main(){thresholds();failures();stream();vk::data_heap_manager::g_managed_heaps.clear();
 std::puts("PASS: exact native geometry batches/fences/snapshots/bulk reset; thresholds and guards; success-only cache/state renewal; timeout/error ownership; 6.25GiB streamed without growth; no-hook failure reproduced; non-iOS unchanged");}
'''

with tempfile.TemporaryDirectory(prefix='armsx3-geometry-') as directory:
    work=Path(directory)
    for path in paths:
        p=work/path;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(subprocess.check_output(['git','-C',str(native),'show',pin+':'+path]))
    for patch in sorted((root/'patches').glob('*.patch')):
        subprocess.run(['git','apply',*['--include='+p for p in paths],str(patch)],cwd=work,check=True)
    source={p:(work/p).read_text() for p in paths}
    ring=strip(source[paths[0]])
    types=source[paths[1]];chunk=types[types.index('\tstruct command_buffer_chunk :'):types.index('\n\tstruct occlusion_data')]
    manager=source[paths[2]]
    snapshots=manager[manager.index('\tmanaged_heap_snapshot_t get_heap_snapshot()'):manager.index('\n\tvoid reset_heap_allocations()')]
    method=block(source[paths[3]],'void VKGSRender::reclaim_geometry_uploads()')
    assert 'void reclaim_geometry_uploads();' in source[paths[4]]
    end=block(source[paths[5]],'void VKGSRender::end()')
    assert end.index('m_current_frame->flags &= ~frame_context_state::dirty;')<end.index('reclaim_geometry_uploads();')
    assert end.index('reclaim_geometry_uploads();')<end.index('analyse_current_rsx_pipeline();')<end.index('load_program_env();')<end.index('emit_geometry(sub_index++);')
    bitfield=(native/'rpcs3/Emu/RSX/Common/bitfield.hpp').read_text()
    marker='\ttemplate <typename T, typename bitmask_type = u32>'
    start=bitfield.index(marker);stop=bitfield.index('\n'+marker,start+1)
    bitmask='namespace rsx{'+bitfield[start:stop]+'}'
    flags=strip((native/'rpcs3/Emu/RSX/Core/RSXDriverState.h').read_text())
    code=model.replace('/* NATIVE_BITMASK */',bitmask+flags).replace('/* NATIVE_RING */',ring)
    code=code.replace('/* NATIVE_SNAPSHOTS */',snapshots).replace('/* NATIVE_CHUNK */',chunk).replace('/* NATIVE_BATCH */',method)+cases
    cpp=work/'test.cpp';cpp.write_text(code)
    for name,apple,ios in [('ios',True,True),('macos',True,False),('linux',False,False)]:
        options=[f'-DTARGET_OS_IOS={int(ios)}',f'-DIOS_TEST={int(ios)}']
        if apple:options+=['-D__APPLE__=1']
        exe=work/name
        subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined',
                        '-fno-omit-frame-pointer',*options,str(cpp),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})

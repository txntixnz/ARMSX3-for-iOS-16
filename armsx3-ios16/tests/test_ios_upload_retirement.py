"""Native ring/fence retirement and bounded iOS upload batches for Build131.

Compile exact patched ring helper, command-buffer chunk, snapshot manager and
renderer batch method. Vulkan queues/fences/driver bytes are host interfaces;
this does not execute real GPU commands or UIKit. Negative historical profiles
must reproduce the stale PUT and failed blocking-wait retirement regressions.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent.parent
native = Path(sys.argv[1]).resolve()
pin = '92b931b9fb5eef7f1317cb482917dfc19aceebd9'
paths = ['rpcs3/Emu/RSX/Common/ring_buffer_helper.h', 'rpcs3/Emu/RSX/VK/VKGSRenderTypes.hpp',
         'rpcs3/Emu/RSX/VK/VKGSRender.cpp', 'rpcs3/Emu/RSX/VK/VKGSRender.h', 'rpcs3/Emu/RSX/VK/VKDraw.cpp']
patches = sorted(p for p in (root / 'patches').glob('*.patch') if int(p.name[:4]) <= 65)
assert [p.name[:4] for p in patches] == [f'{n:04d}' for n in range(1, 66)]
strip = lambda text: re.sub(r'^#(?:include[^\n]*|pragma once)\n', '', text, flags=re.M)

model = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <unordered_map>
#include <unordered_set>
#include <vector>
using usz=std::size_t;using u8=std::uint8_t;using u32=std::uint32_t;using u64=std::uint64_t;using s64=std::int64_t;
using VkResult=int;constexpr int VK_SUCCESS=0,VK_TIMEOUT=2,VK_ERROR_DEVICE_LOST=-4,VK_TRUE=1;
constexpr usz MiB=0x100000;constexpr u64 FRAME_PRESENT_TIMEOUT=10000000;
#define RSX_PROF_SCOPE(...) ((void)0)
#define CHECK_RESULT(value) do{const auto status=(value);if(status!=VK_SUCCESS)throw std::runtime_error("GPU completion failed");}while(false)
template<class T>struct atomic_t{
 std::atomic<T>data{};atomic_t(T value={}):data(value){}
 T load()const{return data.load();}T observe()const{return load();}void store(T value){data.store(value);}void release(T value){store(value);}
 operator T()const{return load();}T operator++(){return ++data;}void operator=(T value){store(value);}
};
using shared_mutex=std::shared_mutex;
struct reader_lock{
 shared_mutex&mutex;bool exclusive=false;explicit reader_lock(shared_mutex&value):mutex(value){mutex.lock_shared();}
 void upgrade(){mutex.unlock_shared();mutex.lock();exclusive=true;}
 ~reader_lock(){if(exclusive)mutex.unlock();else mutex.unlock_shared();}
};
template<class T>T ensure(T value){assert(value);return value;}
namespace utils{template<class T,class A>T align(T value,A alignment){return (value+alignment-1)&~T(alignment-1);}}
namespace fmt{template<class...T>[[noreturn]]void throw_exception(const char*,T...){throw std::runtime_error("ring capacity exhausted");}}
namespace rsx::prof{bool enabled(){return false;}unsigned g_fence_polls=0,g_fence_polls_not_ready=0;}
struct Log{template<class...T>void warning(const char*,T...)const{}};[[maybe_unused]]Log rsx_log;
/* NATIVE_BITMASK */
/* NATIVE_RING */
namespace vk{
 struct data_heap:rsx::data_heap{
  bool heap=true;unsigned grows=0;usz growth_limit=64*MiB;
  bool grow(usz size)override{++grows;if(size>=growth_limit)throw std::runtime_error("oversized request");if(growth_limit==64*MiB)throw std::runtime_error("driver allocation refused");init(growth_limit);return true;}
  void setup(usz size){init(size);}
  void position(usz value){m_put_pos=value;}usz get()const{return m_get_pos;}
 };
 namespace data_heap_manager{
  using managed_heap_snapshot_t=std::unordered_map<const data_heap*,s64>;
  std::unordered_set<data_heap*>g_managed_heaps;
  /* NATIVE_SNAPSHOTS */
 }
 struct fence{bool flushed=true;unsigned handle=1,resets=0;void reset(){++resets;}void wait_flush(){}};
 struct pool_type{int get_owner(){return 1;}};
 unsigned events=0,base_resets=0,waits=0;VkResult wait_status=VK_SUCCESS,poll_status=VK_TIMEOUT;
 std::function<void()>before_wait;
 void on_event_completed(u64){++events;}u64 get_event_id(){return 1;}
 VkResult wait_for_fence(fence*,u64){++waits;if(before_wait)before_wait();return wait_status;}
 struct command_buffer{
  bool is_pending=false;fence owned_fence;fence*m_submit_fence=&owned_fence;pool_type owned_pool;pool_type*pool=&owned_pool;
  void reset(){assert(!is_pending);++base_resets;}
 };
 bool uninterruptible=false;bool is_uninterruptible(){return uninterruptible;}
}
VkResult vkWaitForFences(int,unsigned,const unsigned*,int,u64){return vk::poll_status;}
namespace vk{
 /* NATIVE_CHUNK */
}
struct VKGSRender{
 enum flush_queue_state:u32{ok=0,flushing=1,deadlock=2};
 rsx::atomic_bitmask_t<flush_queue_state>m_queue_status;
 vk::data_heap m_texture_upload_buffer_ring_info;
 vk::command_buffer_chunk chunks[2];vk::command_buffer_chunk*m_current_command_buffer=&chunks[0];
 unsigned flushes=0;std::function<void()>consume_uploads;
 bool is_current_thread()const{return true;}
 void reclaim_texture_uploads();
 void flush_command_queue(){
  assert(!vk::uninterruptible);++flushes;
  m_current_command_buffer->tag();m_current_command_buffer->is_pending=true;
  m_current_command_buffer=m_current_command_buffer==&chunks[0]?&chunks[1]:&chunks[0];
  assert(!m_current_command_buffer->is_pending);
 }
};
/* NATIVE_BATCH */
'''

cases = r'''
void fresh_put(){
 vk::data_heap heap;heap.setup(64*MiB);heap.position(64*MiB-1024);heap.growth_limit=80*MiB;
 assert(heap.alloc<512>(4096)==0); // New buffer starts at its current PUT=0.
 assert(heap.size()==80*MiB&&heap.grows==1);
 for(unsigned i=0;i<1024;++i)heap.alloc<512>(65536);
 assert(heap.grows==1); // Old cursor skipped64MiB and caused another growth.
}
void fence_cases(){
 vk::data_heap heap;heap.setup(64*MiB);heap.alloc<512>(32*MiB);
 vk::data_heap_manager::g_managed_heaps.insert(&heap);
 vk::command_buffer_chunk chunk;chunk.tag();chunk.is_pending=true;
 const auto ticket=chunk.heap_snapshot_id,original_get=heap.get();const auto old_events=vk::events,old_resets=vk::base_resets;
 vk::wait_status=VK_TIMEOUT;
 assert(chunk.wait(FRAME_PRESENT_TIMEOUT)==VK_TIMEOUT);
 assert(chunk.is_pending&&chunk.heap_snapshot_id==ticket&&chunk.owned_fence.resets==0);
 assert(heap.get()==original_get&&vk::events==old_events);
 bool rejected=false;try{chunk.reset();}catch(const std::runtime_error&){rejected=true;}
 assert(rejected&&vk::base_resets==old_resets&&chunk.is_pending);
 vk::wait_status=VK_ERROR_DEVICE_LOST;
 assert(chunk.wait(FRAME_PRESENT_TIMEOUT)==VK_ERROR_DEVICE_LOST&&chunk.is_pending&&heap.get()==original_get);
 vk::wait_status=VK_SUCCESS;assert(chunk.wait(FRAME_PRESENT_TIMEOUT)==VK_SUCCESS);
 assert(!chunk.is_pending&&chunk.heap_snapshot_id==0&&chunk.heap_snapshot.empty());
 assert(heap.pending_bytes()==0&&chunk.owned_fence.resets==1&&vk::events==old_events+1);
 chunk.wait();chunk.reset();assert(vk::events==old_events+1&&vk::base_resets==old_resets+1);
 // A late older fence must not roll GET back after a newer snapshot retired.
 vk::command_buffer_chunk older,newer;heap.alloc<512>(4096);older.tag();older.is_pending=true;
 heap.alloc<512>(8192);newer.tag();newer.is_pending=true;
 newer.wait();const auto latest=heap.get();older.wait();assert(heap.get()==latest&&heap.pending_bytes()==0);
 // Polling and blocking completion must return the same allocation space.
 heap.alloc<512>(4096);vk::command_buffer_chunk poll;poll.tag();poll.is_pending=true;vk::poll_status=VK_SUCCESS;
 assert(poll.poke()&&heap.pending_bytes()==0);vk::poll_status=VK_TIMEOUT;
 vk::data_heap_manager::g_managed_heaps.clear();
}
void batches(bool stream_only=false){
 VKGSRender renderer;auto&heap=renderer.m_texture_upload_buffer_ring_info;heap.setup(64*MiB);
 vk::data_heap_manager::g_managed_heaps.insert(&heap);
 renderer.reclaim_texture_uploads();assert(renderer.flushes==0);
 heap.alloc<512>(32*MiB);
 vk::uninterruptible=true;renderer.reclaim_texture_uploads();assert(renderer.flushes==0);vk::uninterruptible=false;
 for(auto flag:{VKGSRender::flushing,VKGSRender::deadlock}){renderer.m_queue_status.store(flag);renderer.reclaim_texture_uploads();assert(renderer.flushes==0);}
 renderer.m_queue_status.store(VKGSRender::ok);heap.heap=false;renderer.reclaim_texture_uploads();assert(renderer.flushes==0);heap.heap=true;
#if TARGET_OS_IOS
 if(!stream_only){
 // Completion can fail: no snapshot or ring space may be returned to CPU.
 vk::wait_status=VK_TIMEOUT;bool rejected=false;
 try{renderer.reclaim_texture_uploads();}catch(const std::runtime_error&){rejected=true;}
 assert(rejected&&heap.pending_bytes()==32*MiB&&renderer.chunks[0].is_pending);
 vk::wait_status=VK_SUCCESS;renderer.chunks[0].wait();assert(heap.pending_bytes()==0);
 // Simulate an actual wait while another thread checks completion ordering.
 heap.setup(64*MiB);heap.alloc<512>(32*MiB);std::atomic<bool>entered{false},release{false};
 vk::before_wait=[&]{entered.store(true);while(!release.load())std::this_thread::yield();};
 std::thread gpu([&]{while(!entered.load())std::this_thread::yield();assert(heap.pending_bytes()==32*MiB);release.store(true);});
 renderer.reclaim_texture_uploads();gpu.join();vk::before_wait={};assert(heap.pending_bytes()==0);
 }
 // FiveGiB of small uploads without presents: reuse one64MiB buffer. The
 // modeled GPU checks copied byte markers before each native fence completes.
 heap.setup(64*MiB);std::vector<u8>bytes(64*MiB);struct Transfer{usz offset,size;u8 marker;};std::vector<Transfer>pending;
 vk::before_wait=[&]{for(auto transfer:pending){assert(bytes[transfer.offset]==transfer.marker);assert(bytes[transfer.offset+transfer.size-1]==transfer.marker);}pending.clear();};
 const auto old_flushes=renderer.flushes;
 for(unsigned i=0;i<20480;++i){
  renderer.reclaim_texture_uploads();const auto offset=heap.alloc<512>(256*1024);
  assert(offset+256*1024<heap.size());const auto marker=u8(i%251+1);
  std::fill(bytes.begin()+offset,bytes.begin()+offset+256*1024,marker);
  pending.push_back({offset,256*1024,marker});
 }
 renderer.reclaim_texture_uploads();
 if(!pending.empty()){auto*last=renderer.m_current_command_buffer;renderer.flush_command_queue();CHECK_RESULT(last->wait(FRAME_PRESENT_TIMEOUT));}
 vk::before_wait={};
 assert(pending.empty()&&heap.pending_bytes()==0&&heap.grows==0&&heap.size()==64*MiB);
 assert(renderer.flushes-old_flushes>=160&&renderer.flushes-old_flushes<=163);
#else
 (void)stream_only;
 renderer.reclaim_texture_uploads();assert(renderer.flushes==0&&heap.pending_bytes()==32*MiB);
#endif
 vk::data_heap_manager::g_managed_heaps.clear();
}
int main(int argc,char**argv){
 const std::string profile=argc>1?argv[1]:"all";
 if(profile=="all"||profile=="fresh")fresh_put();
 if(profile=="all"||profile=="fences")fence_cases();
 if(profile=="all"||profile=="batches")batches();
 if(profile=="stream")batches(true);
 std::puts("PASS native fresh PUT; success-only wait/reset/snapshot retirement; stale completion ordering; iOS batches reuse64MiB across5GiB of uploads without presents; desktop batch policy unchanged");
}
'''

with tempfile.TemporaryDirectory(prefix='armsx3-upload-retirement-') as directory:
    temp = Path(directory)
    for rel in paths:
        path = temp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(subprocess.check_output(['git', '-C', str(native), 'show', pin + ':' + rel]))
    options = ['--include=' + path for path in paths]
    for patch in patches[:62]:
        subprocess.run(['git', 'apply', *options, str(patch)], cwd=temp, check=True)
    before = [(temp / rel).read_text() for rel in paths]
    for patch in patches[62:]:
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=temp, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=temp, check=True)
    after = [(temp / rel).read_text() for rel in paths]
    for patch in reversed(patches[62:]):
        subprocess.run(['git', 'apply', '--reverse', str(patch)], cwd=temp, check=True)
    assert before == [(temp / rel).read_text() for rel in paths]

    def chunk(text):
        return text[text.index('\tstruct command_buffer_chunk :'):text.index('\n\tstruct occlusion_data')]

    bitfield = (native / 'rpcs3/Emu/RSX/Common/bitfield.hpp').read_text()
    start = bitfield.index('\ttemplate <typename T, typename bitmask_type = u32>')
    end = bitfield.index('\n\ttemplate <typename T, typename bitmask_type = u32>', start + 1)
    bitmask = 'namespace rsx{\n' + bitfield[start:end] + '\n}'
    manager = (native / 'rpcs3/Emu/RSX/VK/VKDataHeapManager.cpp').read_text()
    snapshots = manager[manager.index('\tmanaged_heap_snapshot_t get_heap_snapshot()'):manager.index('\n\tvoid reset_heap_allocations()')]
    method = after[2][after[2].index('void VKGSRender::reclaim_texture_uploads()'):after[2].index('void VKGSRender::retire_completed_work()')]
    # The draw hook must precede the sampler lock; the blit hook precedes GPU
    # scope creation and cache entry. These boundaries avoid recursive eviction.
    draw = after[4][after[4].index('void VKGSRender::load_texture_env()'):]
    assert draw.index('reclaim_texture_uploads();') < draw.index('std::lock_guard lock(m_sampler_mutex)') < draw.index('m_texture_cache.upload_texture(')
    blit = after[2][after[2].index('bool VKGSRender::scaled_image_from_memory('):]
    assert blit.index('reclaim_texture_uploads();') < blit.index('vk::gpu_scope') < blit.index('m_texture_cache.blit(')
    assert 'void reclaim_texture_uploads();' in after[3]

    def source(ring, command):
        return model.replace('/* NATIVE_RING */', strip(ring)).replace('/* NATIVE_BITMASK */', bitmask).replace('/* NATIVE_SNAPSHOTS */', snapshots).replace('/* NATIVE_CHUNK */', chunk(command)).replace('/* NATIVE_BATCH */', method) + cases

    def compile_run(name, text, ios, profile='all', negative=False, expected=b''):
        cpp = temp / (name + '.cpp')
        cpp.write_text(text)
        output = temp / name
        subprocess.run(['g++', '-std=c++23', '-Wall', '-Wextra', '-Werror', '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-D__APPLE__=1', f'-DTARGET_OS_IOS={ios}', str(cpp), '-o', str(output)], check=True)
        result = subprocess.run([str(output), profile], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if negative:
            assert result.returncode != 0 and expected in result.stderr, name + ' must reproduce the expected regression'
            print('PASS historical negative regression: ' + name)
        else:
            if result.returncode:
                sys.stderr.buffer.write(result.stdout + result.stderr)
            result.check_returncode()
            print(result.stdout.decode().strip())

    compile_run('ios', source(after[0], after[1]), 1)
    compile_run('desktop', source(after[0], after[1]), 0)
    pending = after[0][after[0].index('\t\t// Includes alignment/wrap padding'):after[0].index('\t\tusz size() const')]
    old_ring = before[0].replace('\t\tusz size() const', pending + '\t\tusz size() const')
    compile_run('old-put', source(old_ring, after[1]), 1, 'fresh', True, b'heap.alloc<512>(4096)==0')
    compile_run('old-wait', source(after[0], before[1]), 1, 'fences', True, b'chunk.is_pending&&chunk.heap_snapshot_id==ticket')
    compile_run('old-wait-uploads', source(after[0], before[1]), 1, 'stream', True, b'driver allocation refused')
print('PASS patches0063-0065 apply/reverse after exact first62; host queue/fence/driver models. Real iOS memory, menu and clean Stop still require device verification.')

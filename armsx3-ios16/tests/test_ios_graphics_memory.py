"""Native iOS ring growth and worker destruction regression for Build130.

Compile exact patched ring methods and shutdown fragments. Driver allocations,
FXO objects and the event queue are controlled host interfaces. This verifies
capacity/lifetime/thread ordering, not actual Metal allocation or UIKit behavior.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent.parent
native = Path(sys.argv[1]).resolve()
pin = '92b931b9fb5eef7f1317cb482917dfc19aceebd9'
paths = ['rpcs3/Emu/RSX/VK/vkutils/data_heap.cpp', 'rpcs3/Emu/System.cpp']
patches = sorted(p for p in (root / 'patches').glob('*.patch') if int(p.name[:4]) <= 62)
assert [p.name[:4] for p in patches] == [f'{n:04d}' for n in range(1, 63)]
strip = lambda text: re.sub(r'^#(?:include[^\n]*|pragma once)\n', '', text, flags=re.M)

ring_model = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
using usz=std::size_t;using u32=std::uint32_t;using u64=std::uint64_t;using VkFlags=u32;using VkBufferUsageFlags=u32;
constexpr usz MiB=0x100000;
constexpr unsigned VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT=1,VK_MEMORY_PROPERTY_HOST_COHERENT_BIT=2,VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT=4,VK_BUFFER_USAGE_TRANSFER_SRC_BIT=8,VK_BUFFER_USAGE_TRANSFER_DST_BIT=16,VK_BUFFER_CREATE_ALLOW_NULL_RPCS3=32,VK_BUFFER_CREATE_IGNORE_VMEM_PRESSURE_RPCS3=64;
namespace utils{template<class T,class A>T align(T value,A alignment){return (value+alignment-1)&~T(alignment-1);}}
namespace fmt{
 template<class...T>std::string format(const char*,T...){return "host log";}
 template<class...T>[[noreturn]]void throw_exception(const char*,T...){throw std::runtime_error("native ring declined request");}
}
template<class T>T ensure(T value){assert(value);return value;}
struct{template<class...T>void warning(const char*,T...){}template<class...T>void error(const char*,T...){}template<class...T>void fatal(const char*,T...){}template<class...T>void notice(const char*,T...){}}rsx_log;
namespace rsx{using flags32_t=u32;struct dma_manager{bool sync(){return true;}};namespace overlays{void queue_message(std::string,u64){}}}
struct{template<class T>T&get(){static T value;return value;}}fxo;
auto*g_fxo=&fxo;
struct{bool paused=false;void Pause(bool){paused=true;}}Emu;
/* NATIVE_RING_BASE */
namespace vk{
 constexpr u32 heap_pool_fixed_size=2,heap_changed=1;
 struct memory_type_info{usz bytes=1024*MiB;usz total_bytes()const{return bytes;}};
 struct mapping{memory_type_info device_bar,host_visible_coherent,device_local;usz device_bar_total_bytes=1024*MiB;};
 struct device{mapping memory;const mapping&get_memory_mapping()const{return memory;}}gpu;
 device*g_render_device=&gpu;
 usz used=0,driver_limit=128*MiB;unsigned serial=0,interrupts=0;std::vector<usz>requests;
 usz vmm_get_application_memory_usage(const memory_type_info&){return used;}
 bool reclaim_ring_memory(){return false;}
 void raise_status_interrupt(u32){++interrupts;}
 struct buffer{
  struct{VkBufferUsageFlags usage=0;}info;
  unsigned value=++serial;u64 payload=0x11223344;
  buffer(device&,usz size,memory_type_info,VkFlags,VkBufferUsageFlags usage,VkFlags,int){
   requests.push_back(size);if(size>driver_limit)throw std::bad_alloc();info.usage=usage;
  }
 };
 constexpr int VMM_ALLOCATION_POOL_SYSTEM=1;
 struct collector{
  std::vector<std::unique_ptr<buffer>>retired;
  void dispose(std::unique_ptr<buffer>&value){retired.push_back(std::move(value));}
 }gc;
 collector*get_resource_manager(){return &gc;}
 struct data_heap:rsx::data_heap{
  usz initial_size=0;bool mapped=false,m_prefer_writethrough=false,notify_on_grow=true;u32 m_flags=0;
  std::unique_ptr<buffer>heap,shadow;
  void unmap(bool){mapped=false;}
  bool grow(usz)override;bool can_allocate_heap(const memory_type_info&,usz,int);
  void setup(usz size){rsx::data_heap::init(size,"host ring",4096);initial_size=size;heap=std::make_unique<buffer>(gpu,size,gpu.memory.host_visible_coherent,0,0,0,1);m_put_pos=size-1024;}
  usz put()const{return m_put_pos;}
 };
 /* NATIVE_GROW */
}
'''

ring_cases = r'''
int main(){
 // Replay the boundary that turns a64MiB texture plus8 padding bytes into a
 // 192MiB replacement with the old desktop growth rule, despite a128MiB driver
 // allocation limit. The native ring allocator aligns the actual request.
 {
  vk::data_heap heap;heap.setup(64*MiB);const auto old=heap.heap->value;
  bool rejected=false;usz offset=0;
  try{offset=heap.alloc<512>(64*MiB+8);}catch(const std::bad_alloc&){rejected=true;}
#if EXPECT_SMALL_GROW
  assert(!rejected&&vk::requests.back()==80*MiB&&heap.size()==80*MiB);
  assert(offset==0&&offset+64*MiB+8<heap.size());
  assert(heap.put()==utils::align(64*MiB+8,512));
  assert(vk::interrupts==1);
#else
  assert(rejected&&vk::requests.back()==192*MiB);(void)offset;
#endif
  assert(vk::gc.retired.size()==1&&vk::gc.retired[0]->value==old);
  assert(vk::gc.retired[0]->payload==0x11223344); // Old in-flight data stays owned.
 }
 vk::gc.retired.clear();vk::driver_limit=1024*MiB;
 for(usz request:{usz(512),usz(4096),usz(65536),16*MiB,64*MiB+8,150*MiB}){
  vk::data_heap heap;heap.setup(64*MiB);
  const auto offset=heap.alloc<512>(request);
  assert(offset+request<heap.size()); // No wrapped allocation past its buffer.
  assert(heap.heap&&heap.heap->value&&heap.heap->payload==0x11223344);
 }
 vk::gc.retired.clear();
#if EXPECT_SMALL_GROW
 for(usz request:{64*MiB,64*MiB+8,1024*MiB}){
  vk::data_heap heap;heap.setup(64*MiB);heap.m_flags=vk::heap_pool_fixed_size;
  const auto before=vk::requests.size();const auto old=heap.heap->value;
  bool refused=false;try{heap.alloc<512>(request);}catch(const std::runtime_error&){refused=true;}
  assert(refused&&vk::requests.size()==before&&heap.heap->value==old&&heap.size()==64*MiB);
 }
#endif
 // A real budget check still refuses rather than handing out undersized space.
 {
  vk::data_heap heap;heap.setup(64*MiB);vk::used=1000*MiB;const auto before=vk::requests.size();
  assert(!heap.grow(4096)&&Emu.paused&&vk::requests.size()==before&&heap.heap);
 }
 std::puts(EXPECT_SMALL_GROW?"PASS iOS native ring:64MiB+padding grows to80MiB; old in-flight owner retained; alignment/wrap/large/fixed-limit/budget cases":"PASS old/desktop native ring reproduces192MiB allocation refusal; desktop growth preserved");
}
'''

stop_model = r'''
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <functional>
#include <mutex>
#include <thread>
#include <vector>
std::thread::id main_id;std::atomic<bool>reset_entered{false},release_reset{false},complete{false};
std::atomic<unsigned>cpu_cleaned{0},lv2_cleaned{0},fxo_cleaned{0},vm_closed{0};
struct{template<class...T>void warning(const char*,T...){}template<class...T>void notice(const char*,T...){}}sys_log;
bool expected_worker=false;
void assert_thread(){assert((std::this_thread::get_id()!=main_id)==expected_worker);}
namespace cpu_thread{void cleanup(){assert_thread();++cpu_cleaned;}}
namespace lv2_obj{void cleanup(){assert_thread();++lv2_cleaned;}}
struct Fxo{void reset(){assert_thread();reset_entered.store(true);while(!release_reset.load())std::this_thread::yield();++fxo_cleaned;}}fxo;
auto*g_fxo=&fxo;
namespace vm{void close(){assert_thread();assert(fxo_cleaned==1);++vm_closed;}}
void worker_cleanup(){
 /* WORKER_CLEANUP */
}
void main_cleanup(){
 /* MAIN_CLEANUP */
 assert(cpu_cleaned==1&&lv2_cleaned==1&&fxo_cleaned==1&&vm_closed==1);
 complete.store(true);
}
int main(){
 main_id=std::this_thread::get_id();
#if TARGET_OS_IOS
 expected_worker=true;
 std::mutex mutex;std::function<void()>final_callback;
 std::thread worker([&]{worker_cleanup();std::lock_guard lock(mutex);final_callback=main_cleanup;});
 auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);
 while(!reset_entered.load()){assert(std::chrono::steady_clock::now()<deadline);std::this_thread::yield();}
 // A stuck driver destructor must leave main free. The runtime's timeout can
 // report failure without releasing the still-owned native frame/configuration.
 unsigned main_events=0;
 for(unsigned i=0;i<1000;++i)++main_events;
 assert(main_events==1000&&!complete&&cpu_cleaned==1&&lv2_cleaned==1&&fxo_cleaned==0&&vm_closed==0);
 {std::lock_guard lock(mutex);assert(!final_callback);}
 release_reset.store(true);worker.join();
 {std::lock_guard lock(mutex);assert(final_callback);final_callback();}
 assert(complete);
#else
 expected_worker=false;release_reset.store(true);worker_cleanup();assert(!reset_entered);
 main_cleanup();assert(complete); // Desktop retains final destruction on main.
#endif
 assert(cpu_cleaned==1&&lv2_cleaned==1&&fxo_cleaned==1&&vm_closed==1);
 std::puts(TARGET_OS_IOS?"PASS native iOS teardown fragments:blocked FXO destructor on worker; main events remain available; VM close/final callback only after release; exactly-once cleanup":"PASS desktop native final cleanup remains on main");
}
'''

with tempfile.TemporaryDirectory(prefix='armsx3-ios-memory-') as directory:
    temp = Path(directory)
    for rel in paths:
        path = temp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(subprocess.check_output(['git', '-C', str(native), 'show', pin + ':' + rel]))
    options = ['--include=' + path for path in paths]
    for patch in patches[:60]:
        subprocess.run(['git', 'apply', *options, str(patch)], cwd=temp, check=True)
    before = [(temp / rel).read_bytes() for rel in paths]
    for patch in patches[60:]:
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=temp, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=temp, check=True)
    after = [(temp / rel).read_bytes() for rel in paths]
    for patch in reversed(patches[60:]):
        subprocess.run(['git', 'apply', '--reverse', str(patch)], cwd=temp, check=True)
    assert before == [(temp / rel).read_bytes() for rel in paths]

    ring_base = strip((native / 'rpcs3/Emu/RSX/Common/ring_buffer_helper.h').read_text())
    for name, source, ios, small in [('build129', before[0], 1, 0), ('ios', after[0], 1, 1), ('desktop', after[0], 0, 0)]:
        text = source.decode().replace('\r\n', '\n')
        grow = text[text.index('\tbool data_heap::grow('):text.index('\n\tvoid* data_heap::map_impl(')]
        cpp = temp / (name + '.cpp')
        cpp.write_text(ring_model.replace('/* NATIVE_RING_BASE */', ring_base).replace('/* NATIVE_GROW */', grow) + ring_cases)
        output = temp / name
        subprocess.run(['g++', '-std=c++23', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-D__APPLE__=1', f'-DTARGET_OS_IOS={ios}', f'-DEXPECT_SMALL_GROW={small}', str(cpp), '-o', str(output)], check=True)
        subprocess.run([str(output)], check=True, timeout=15)

    system = after[1].decode()
    start = system.index('#if defined(__APPLE__) && TARGET_OS_IOS\n\t\t// These destructors')
    end = system.index('\n\t\t// Final termination from main thread', start)
    worker = system[start:end]
    main_start = system.index('#if !defined(__APPLE__) || !TARGET_OS_IOS', end)
    main_end = system.index('\n\n\t\t\t*stop_watchdog', main_start)
    main = system[main_start:main_end]
    assert system.index('armsx3_ios_runtime_capture_stopped();') < start
    assert system.index('type.thread_op(data, thread_state::destroying_context);') < start
    assert system.index('m_state = system_state::stopped;', main_end) > main_end
    for ios in (1, 0):
        cpp = temp / f'stop{ios}.cpp'
        cpp.write_text(stop_model.replace('/* WORKER_CLEANUP */', worker).replace('/* MAIN_CLEANUP */', main))
        output = temp / f'stop{ios}'
        subprocess.run(['g++', '-std=c++23', '-Wall', '-Wextra', '-Werror', '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-D__APPLE__=1', f'-DTARGET_OS_IOS={ios}', str(cpp), '-o', str(output)], check=True)
        subprocess.run([str(output)], check=True, timeout=15)
print('PASS patches0061/0062 apply after exact first60 and reverse; host driver/FXO/queue models only. iOS Metal allocation, extended loading and real shutdown need device verification.')

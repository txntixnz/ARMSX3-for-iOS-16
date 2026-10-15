"""Compile native empty-FIFO case and outer poll loop with host backends.

Checks GET publication, hot polls, timed parking, command arrival, Stop/pause,
and next-iteration local/ZCULL/DMA maintenance. Actual iOS scheduling is pending.
"""
from pathlib import Path
import os, subprocess, sys, tempfile
root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
pin='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
paths=['rpcs3/Emu/RSX/RSXFIFO.cpp','rpcs3/Emu/RSX/RSXThread.cpp']

def block(text,marker,start=0):
    begin=text.index(marker,start);opening=text.index('{',begin);end=opening+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[begin:end]

model=r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <functional>
#include <string_view>
#include <vector>
using u8=std::uint8_t;using u32=std::uint32_t;using u64=std::uint64_t;
constexpr u32 RSX_METHOD_NON_METHOD_CMD_MASK=3;
namespace rsx::prof{bool enabled(){return false;}u64 g_fifo_commands=0;}
namespace rsx::FIFO{
enum:u32{FIFO_NOP=0xBABEF1F4,FIFO_EMPTY=0xDEADF1F0};
enum class state:u8{running,empty,spinning,nop};
struct register_pair{u32 reg,value;};
}
std::string_view bucket;
struct Scope{std::string_view previous;Scope(const char*name):previous(bucket){bucket=name;}~Scope(){bucket=previous;}};
#define CAT_(a,b) a##b
#define CAT(a,b) CAT_(a,b)
#define RSX_PROF_SCOPE(b) Scope CAT(scope_,__LINE__){#b}
u64 clock_us=1000;u64 get_system_time(){return clock_us;}
namespace host{unsigned pauses=0,parks=0,wfes=0,yields=0;bool stream=true;std::function<void()> before_park;std::vector<unsigned> park_loops;}
namespace utils{void pause(){++host::pauses;}bool has_wfe_event_stream(){return host::stream;}void wait_for_event(){++host::wfes;}}
namespace host{struct Yield{static void yield(){++host::yields;}};}
struct Control{u32 get=0;};
struct Fifo{
 std::deque<u32>commands;unsigned reads=0,publishes=0,last_publish=0;
 void read(rsx::FIFO::register_pair&command){++reads;if(!commands.empty()){command.reg=commands.front();commands.pop_front();}}
 void sync_get_force(){++publishes;last_publish=reads;}
};
struct Flag{bool value=false;operator bool()const{return value;}void release(bool v){value=v;}};
struct Subunit{std::vector<unsigned>loops;unsigned*current=nullptr;template<class...T>void update(T...){loops.push_back(*current);}};
namespace rsx{
using namespace FIFO;
struct thread{
 u64 m_cycles_counter=0;unsigned m_eng_interrupt_mask=0;
 bool external_interrupt_lock=false,rsx_thread_running=true,in_begin_end=false,stopped=false;
 Flag sync_point_request;u32 restore_point=0,saved_fifo_ret=0,fifo_ret_addr=77;
 Control control;Control*ctrl=&control;Fifo fifo;Fifo*fifo_ctrl=&fifo;
 struct{FIFO::state state=FIFO::state::running;u64 FIFO_idle_timestamp=0;}performance_counters;
 unsigned loops=0,limit=300,executed=0,pause_calls=0;std::vector<unsigned>maintenance;
 Subunit zcull,dma;Subunit*zcull_ctrl=&zcull;Subunit*m_host_dma_ctrl=&dma;
 thread(){zcull.current=&loops;dma.current=&loops;}
 bool test_stopped(){if(stopped||loops==limit)return true;++loops;return false;}
 void wait_pause(){++pause_calls;rsx_thread_running=false;}
 void do_local_task(FIFO::state){maintenance.push_back(loops);}
 void run_FIFO(){
 /* NATIVE_PREFIX */
  // Command execution is a host interface; the production running transition
  // is retained, so subsequent drains reset their native hot-poll budget.
  ++executed;performance_counters.state=FIFO::state::running;
 }
 void run(){RSX_PROF_SCOPE(fifo_decode);/* NATIVE_LOOP */}
};
}
rsx::thread*current=nullptr;
namespace thread_ctrl{
void wait_for(u64 us){
 assert(us==100&&bucket=="idle_fifo");assert(current->fifo.last_publish==current->fifo.reads);
 ++host::parks;host::park_loops.push_back(current->loops);clock_us+=us;
 if(host::before_park)host::before_park();
}
}
/* Native bodies need the wait API declaration before the class. */
void reset(rsx::thread&t){current=&t;host::pauses=host::parks=host::wfes=host::yields=0;host::park_loops.clear();host::before_park={};}
void check_maintenance(const rsx::thread&t){
 assert(t.maintenance==t.zcull.loops&&t.maintenance==t.dma.loops);
 for(auto iteration:host::park_loops)if(iteration<t.loops)
  assert(std::find(t.maintenance.begin(),t.maintenance.end(),iteration+1)!=t.maintenance.end());
}
int main(){
 {
  rsx::thread t;reset(t);t.run();assert(t.executed==0&&t.fifo.publishes==t.loops);
#if IOS_TEST
  assert(host::pauses==8&&host::parks==291&&host::wfes==0&&host::yields==0);check_maintenance(t);
#else
  assert(host::parks==0);
#if ARM_TEST
  assert(host::pauses==8&&host::wfes==291);
#else
  assert(host::yields==299);
#endif
#endif
 }
#if IOS_TEST
 {
  rsx::thread t;reset(t);t.limit=40;
  host::before_park=[&]{if(host::parks==1)t.fifo.commands.push_back(0x100);};
  t.run();assert(t.executed==1&&host::pauses==16&&host::parks==21);check_maintenance(t);
 }
 {
  rsx::thread t;reset(t);host::before_park=[&]{t.stopped=true;};t.run();
  assert(t.loops==10&&host::parks==1&&t.executed==0);
 }
 {
  rsx::thread t;reset(t);host::before_park=[&]{t.external_interrupt_lock=true;};t.run();
  assert(t.loops==11&&t.pause_calls==1&&host::parks==1);
 }
 {
  rsx::thread t;reset(t);t.limit=100;t.fifo.commands.push_back(rsx::FIFO::FIFO_NOP);t.run();
  assert(t.executed==0&&t.fifo.publishes==100&&host::parks>0);check_maintenance(t);
 }
#elif ARM_TEST
 {
  rsx::thread t;reset(t);host::stream=false;t.run();assert(host::parks==0&&host::wfes==0&&host::yields==291);
 }
#endif
 std::puts("PASS: native FIFO GET/hot-poll/wait/command transitions; next-poll maintenance; Stop/pause; platform isolation");
}
'''
with tempfile.TemporaryDirectory(prefix='armsx3-fifo-idle-') as temp:
    work=Path(temp)
    for path in paths:
        file=work/path;file.parent.mkdir(parents=True,exist_ok=True)
        file.write_bytes(subprocess.check_output(['git','-C',str(native),'show',pin+':'+path]))
    for patch in sorted((root/'patches').glob('*.patch')):
        subprocess.run(['git','apply',*['--include='+p for p in paths],str(patch)],cwd=work,check=True)
    fifo=(work/paths[0]).read_text();rsx=(work/paths[1]).read_text()
    begin=fifo.index('void thread::run_FIFO()');opening=fifo.index('{',begin)
    end=fifo.index('\n\t\t\tcase FIFO::FIFO_BUSY:',opening)
    prefix=fifo[opening+1:end]+'\n\t\t\tdefault: return;\n\t\t\t}\n\t\t}\n'
    loop=block(rsx,'while (!test_stopped())',rsx.index('RSX_PROF_SCOPE(fifo_decode);'))
    code=model.replace('/* NATIVE_PREFIX */',prefix).replace('/* NATIVE_LOOP */',loop)
    code=code.replace('namespace rsx{\nusing namespace FIFO;', 'namespace thread_ctrl{void wait_for(u64);}\nnamespace rsx{\nusing namespace FIFO;')
    # Host scheduler yields are counted; ARM wait APIs above are explicit models.
    code=code.replace('std::this_thread::yield()', 'host::Yield::yield()')
    (work/'test.cpp').write_text(code)
    for apple,ios,arm in [(1,1,1),(1,0,1),(0,0,1),(0,0,0)]:
        options=[f'-DIOS_TEST={ios}',f'-DARM_TEST={arm}',f'-DTARGET_OS_IOS={ios}']
        if apple:options+=['-D__APPLE__=1']
        if arm:options+=['-DARCH_ARM64=1']
        # The pinned non-ARM path resets an ARM-only spin counter already.
        if not arm:options+=['-Wno-unused-but-set-variable']
        subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                        '-fno-omit-frame-pointer',*options,str(work/'test.cpp'),'-o',str(work/'test')],check=True)
        subprocess.run([str(work/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})

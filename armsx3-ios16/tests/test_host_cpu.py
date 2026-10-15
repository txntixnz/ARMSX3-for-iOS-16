"""Production CPU-window arithmetic and Mach snapshot ownership with host APIs."""
from pathlib import Path
import os, subprocess, tempfile
root = Path(__file__).resolve().parent.parent
mach = r'''
#pragma once
#include <cstdint>
using kern_return_t=int; using mach_port_t=unsigned; using mach_msg_type_number_t=unsigned;
using thread_act_array_t=mach_port_t*; using thread_info_t=int*;
using vm_address_t=std::uintptr_t; using vm_size_t=std::size_t;
struct time_value_t{int seconds,microseconds;};
struct thread_identifier_info_data_t{std::uint64_t thread_id;};
struct thread_basic_info_data_t{time_value_t user_time,system_time;};
struct thread_extended_info_data_t{char pth_name[64];};
constexpr int KERN_SUCCESS=0,THREAD_IDENTIFIER_INFO=1,THREAD_BASIC_INFO=2,THREAD_EXTENDED_INFO=3;
constexpr unsigned THREAD_IDENTIFIER_INFO_COUNT=1,THREAD_BASIC_INFO_COUNT=1,THREAD_EXTENDED_INFO_COUNT=1;
mach_port_t mach_task_self();
kern_return_t mach_port_deallocate(mach_port_t,mach_port_t);
kern_return_t vm_deallocate(mach_port_t,vm_address_t,vm_size_t);
kern_return_t task_threads(mach_port_t,thread_act_array_t*,mach_msg_type_number_t*);
kern_return_t thread_info(mach_port_t,int,thread_info_t,mach_msg_type_number_t*);
'''
test = r'''
#include <cassert>
#include <cmath>
#include <cstdlib>
#include <set>
#include <stdexcept>
#include <vector>
#include "RuntimeCpu.cpp"
std::vector<std::string> lines; unsigned arrays=0,freed=0,calls=0;
std::set<unsigned> ports; int failed_flavor=0; bool fail_task=false,throw_info=false;
mach_port_t mach_task_self(){return 42;}
kern_return_t task_threads(mach_port_t task,thread_act_array_t*list,mach_msg_type_number_t*count){
 assert(task==42);if(fail_task)return 1;
 *count=3;*list=static_cast<thread_act_array_t>(std::malloc(3*sizeof(mach_port_t)));++arrays;
 for(unsigned i=0;i<3;++i){(*list)[i]=10+i;assert(ports.insert(10+i).second);}return 0;
}
kern_return_t mach_port_deallocate(mach_port_t task,mach_port_t port){assert(task==42&&ports.erase(port)==1);return 0;}
kern_return_t vm_deallocate(mach_port_t task,vm_address_t addr,vm_size_t size){
 assert(task==42&&size==3*sizeof(mach_port_t));std::free(reinterpret_cast<void*>(addr));++freed;return 0;
}
kern_return_t thread_info(mach_port_t port,int flavor,thread_info_t out,mach_msg_type_number_t*){
 assert(ports.contains(port));if(throw_info)throw std::runtime_error("allocation/interface failure");
 if(failed_flavor==flavor)return 1;
 if(flavor==THREAD_IDENTIFIER_INFO)reinterpret_cast<thread_identifier_info_data_t*>(out)->thread_id=1000+port;
 if(flavor==THREAD_BASIC_INFO){auto&info=*reinterpret_cast<thread_basic_info_data_t*>(out);
  info.user_time={0,int(++calls)};info.system_time={0,0};}
 if(flavor==THREAD_EXTENDED_INFO)std::memset(reinterpret_cast<thread_extended_info_data_t*>(out)->pth_name,'x',64);
 return 0;
}
void ARMSX3StartupLog(const char*line){lines.emplace_back(line);}
void clean(){assert(ports.empty()&&arrays==freed);}
bool close(double a,double b){return std::abs(a-b)<0.00001;}
int main(){
 using namespace ios_runtime;HostCpuWindow window;
 std::vector<HostCpuSample> baseline{{1,100,20,"PPU main"},{2,0,0,"SPU"}};
 assert(window.update(1000000000,baseline).empty());
 auto result=window.update(6000000000,{{1,4000100,1000020,"PPU main"},{2,2500000,0,"SPU"},{3,9000000,0,"new"}});
 assert(result.size()==2&&result[0].thread.id==1&&close(result[0].total(),100));
 assert(close(result[0].user_percent,80)&&close(result[0].system_percent,20)&&close(result[1].total(),50));
 // Missing IDs are removed; reused port names cannot resurrect their counters.
 result=window.update(11000000000,{{2,5000000,0,"SPU"}});assert(result.size()==1&&close(result[0].total(),50));
 result=window.update(16000000000,{{1,8000000,0,"reappeared"},{2,1,0,"reset"}});assert(result.empty());
 assert(window.update(16000000000,baseline).empty()); // Zero-duration window.
 assert(window.update(1,baseline).empty()); // Clock reversal rebaselines.
 window.reset();assert(window.update(6000000000,baseline).empty());
 // Exercise the complete production collector and its exception cleanup.
 reset_host_cpu_observation();sample_host_cpu();clean();assert(lines.empty());
 sample_host_cpu();clean();assert(!lines.empty()&&lines.front().find("100%=one core")!=std::string::npos);
 failed_flavor=THREAD_EXTENDED_INFO;sample_host_cpu();clean();assert(lines.back().find("unnamed")!=std::string::npos);
 failed_flavor=THREAD_BASIC_INFO;sample_host_cpu();clean();
 failed_flavor=THREAD_IDENTIFIER_INFO;sample_host_cpu();clean();
 failed_flavor=0;throw_info=true;sample_host_cpu();clean();assert(lines.back().find("game execution continues")!=std::string::npos);
 throw_info=false;fail_task=true;sample_host_cpu();clean();assert(lines.back().find("snapshot unavailable")!=std::string::npos);
 fail_task=false;const auto size=lines.size();sample_host_cpu();clean();assert(lines.size()==size);
 std::puts("PASS: production CPU deltas/ranking, per-core percentages, thread churn/reset/clock cases; complete Mach collector owns/releases every port/array on success, partial failure and exception");
}
'''
with tempfile.TemporaryDirectory(prefix='armsx3-host-cpu-') as temp:
    work=Path(temp);(work/'mach').mkdir();(work/'mach/mach.h').write_text(mach)
    (work/'mach/thread_info.h').write_text('#include "mach.h"\n')
    (work/'test.cpp').write_text(test)
    subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer','-I',str(work),'-I',str(root/'core/loadtest'),
                    '-I',str(root/'ios/src'),str(work/'test.cpp'),'-o',str(work/'test')],check=True)
    subprocess.run([str(work/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})

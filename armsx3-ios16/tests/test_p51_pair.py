"""Host checks of exact P51 bridge plus production thread-local dispatch boundary.

Usage: python test_p51_pair.py staged/rpcs3/Emu/Cell/PPUThread.cpp CoreBridge.cpp
Named CPU workers, VM, decoder, flags and instruction handlers are host shims;
real exec_task and bounded-helper bodies are extracted. Device execution pending.
"""
from pathlib import Path
import subprocess,sys,tempfile
if len(sys.argv)!=3:raise SystemExit(__doc__)
def function(text,signature):
    start=text.index(signature);opening=text.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
core=Path(sys.argv[1]).read_text();bridge=Path(sys.argv[2]).read_text()
# The shim is checked in alongside this test so it is usable from the repository.
shims=(Path(__file__).with_name('p51_host_shims.cpp')).read_text()
production=function(core,'struct ios_ppu_dispatch_probe')+';\n'
assert 'static thread_local ios_ppu_dispatch_probe* s_ios_ppu_dispatch_probe = nullptr;' in core
production+='static thread_local ios_ppu_dispatch_probe* s_ios_ppu_dispatch_probe=nullptr;\n'
production+=function(core,'void ppu_thread::exec_task(')+'\n'
production+=function(core,'extern "C" int armsx3_ios_ppu_exec_bounded(')+'\n'
production+='void assert_dispatch_clear(){assert(!s_ios_ppu_dispatch_probe);assert(cpu_thread::current); }\n'
phase=function(bridge,'extern "C" __attribute__((visibility("default"))) int armsx3_core_test_persistent_ppu_pair(')
checks=r'''
void restored(){
 assert(!cpu_thread::live && cpu_thread::g_threads_created==cpu_thread::g_threads_deleted);
 assert(!s_ios_ppu_dispatch_probe);
 assert(g_cfg.core.ppu_prof.get() && g_cfg.core.spu_prof.get() && g_cfg.core.spu_debug.get());
 assert(g_cfg.core.ppu_decoder.get()==ppu_decoder_type::llvm && g_cfg.core.thread_scheduler.get()==thread_scheduler_mode::native);
 assert(std::none_of(vm::allocated.begin(),vm::allocated.end(),[](bool x){return x;}));
 assert(id_manager::g_id==0);
}
int main(){
 for(unsigned repetition=0;repetition<8;repetition++){
  logs.clear();construct_calls=0;callback_calls=0;queue_publications=0;
  auto created=cpu_thread::g_threads_created.load(),deleted=cpu_thread::g_threads_deleted.load();
  assert(armsx3_core_test_persistent_ppu_pair()==0);restored();
  assert(cpu_thread::g_threads_created==created+2 && cpu_thread::g_threads_deleted==deleted+2 && callback_calls==18 && queue_publications==18);
  assert(construct_calls==2);
  for(const char* values:{"results=39/67","results=-2/73","results=51/-2","results=57/85",
   "results=63/91","results=-2/97","results=75/-2","results=81/109"})
   assert(std::count_if(logs.begin(),logs.end(),[=](const auto&s){return s.find(values)!=std::string::npos;})==1);
 }
 // Mid-batch/initial/second-exit publication errors, second constructor failure
 // and a dropped job exercise active, parked, unstarted and partly exited cleanup.
 for(fault=2;fault<=10;fault++){
  logs.clear();construct_calls=0;callback_calls=0;queue_publications=0;
  assert(armsx3_core_test_persistent_ppu_pair()==-1);restored();
 }
 fault=0;
 for(vm::fail_alloc=1;vm::fail_alloc<=4;vm::fail_alloc++){
  assert(armsx3_core_test_persistent_ppu_pair()==-1);restored();
 }
 vm::fail_alloc=0;
 Emu.stopped=false;assert(armsx3_core_test_persistent_ppu_pair()==-1);Emu.stopped=true;restored();
 g_cfg.core.ppu_threads=1;assert(armsx3_core_test_persistent_ppu_pair()==-1);g_cfg.core.ppu_threads=2;restored();
 fxo.available=false;assert(armsx3_core_test_persistent_ppu_pair()==-1);fxo.available=true;restored();
 std::puts("PASS: exact P51 phase, eight repetitions/16 persistent host workers/128 guest jobs, same worker recovery after either budget stop, 16 queued exits; snapshots/TLS/retained outputs/full aliases/cache/waits/counts; bad results/guards/active publication/initial publication/second exit/constructor failure/dropped job/gate cancellation/instruction throw/allocation/setup restore and join; real bounded dispatch, host queue/VM/decoder/PPU operations shims");
}
'''
with tempfile.TemporaryDirectory(prefix='p51-pair-') as temp:
    source=Path(temp)/'test.cpp';binary=Path(temp)/'test';source.write_text(shims+production+phase+checks)
    subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)

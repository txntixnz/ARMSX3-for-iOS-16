"""Host checks of exact P53 bridge plus production thread-local dispatch boundary.

Usage: python test_p53_pair.py staged/rpcs3/Emu/Cell/PPUThread.cpp CoreBridge.cpp staged/rpcs3/Emu/Cell/Modules/sys_ppu_thread_.cpp
Named CPU workers, VM, decoder, flags and instruction handlers are host shims;
real exec_task and bounded-helper bodies are extracted. Device execution pending.
"""
from pathlib import Path
import subprocess,sys,tempfile
if len(sys.argv)!=4:raise SystemExit(__doc__)
def function(text,signature):
    start=text.index(signature);opening=text.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
core=Path(sys.argv[1]).read_text();bridge=Path(sys.argv[2]).read_text()
# The shim is checked in alongside this test so it is usable from the repository.
shims=(Path(__file__).with_name('p53_host_shims.cpp')).read_text()
production=function(core,'struct ios_ppu_dispatch_probe')+';\n'
assert 'static thread_local ios_ppu_dispatch_probe* s_ios_ppu_dispatch_probe = nullptr;' in core
production+='static thread_local ios_ppu_dispatch_probe* s_ios_ppu_dispatch_probe=nullptr;\n'
production+=function(core,'void ppu_thread::exec_task(')+'\n'
production+=function(core,'extern "C" int armsx3_ios_ppu_exec_bounded(')+'\n'
production+='void assert_dispatch_clear(){assert(!s_ios_ppu_dispatch_probe);assert(cpu_thread::current);assert(id_manager::g_id==0); }\n'
tls=Path(sys.argv[3]).read_text()
production+=tls[tls.index('static u32 s_tls_addr'):tls.index('static u32 ppu_alloc_tls()')]+'\n'
for signature in ['static u32 ppu_alloc_tls(', 'static void ppu_free_tls(', 'static void ppu_initialize_tls_memory(',
                  'extern "C" int armsx3_ios_ppu_probe_tls_and_call(', 'static bool ios_probe_tls_pair_owner(',
                  'extern "C" u32 armsx3_ios_ppu_probe_alloc_peer_tls(', 'extern "C" int armsx3_ios_ppu_probe_free_peer_tls(']:
    production+=function(tls,signature)+'\n'
phase=function(bridge,'extern "C" __attribute__((visibility("default"))) int armsx3_core_test_persistent_guest_tls(')
checks=r'''
void restored(){
 assert(!cpu_thread::live && cpu_thread::g_threads_created==cpu_thread::g_threads_deleted);
 assert(!s_ios_ppu_dispatch_probe);
 assert(!s_tls_addr&&!s_tls_file&&!s_tls_zero&&!s_tls_size&&!s_tls_area&&!s_tls_max&&!s_tls_map);
 assert(g_cfg.core.ppu_prof.get() && g_cfg.core.spu_prof.get() && g_cfg.core.spu_debug.get());
 assert(g_cfg.core.ppu_decoder.get()==ppu_decoder_type::llvm && g_cfg.core.thread_scheduler.get()==thread_scheduler_mode::native);
 assert(std::none_of(vm::allocated.begin(),vm::allocated.end(),[](bool x){return x;}));
 assert(id_manager::g_id==0);
}
int main(){
 for(unsigned repetition=0;repetition<8;repetition++){
  logs.clear();construct_calls=0;callback_calls=0;queue_publications=0;
  auto created=cpu_thread::g_threads_created.load(),deleted=cpu_thread::g_threads_deleted.load();
  assert(armsx3_core_test_persistent_guest_tls()==0);restored();
  assert(cpu_thread::g_threads_created==created+2 && cpu_thread::g_threads_deleted==deleted+2 && callback_calls==10 && construct_calls==2 && queue_publications==10);
  for(const char* values:{"results=45/73","results=-2/79","results=57/-2","results=63/91",
   "results=69/97","results=-2/103","results=81/-2","results=87/115"})
   assert(std::count_if(logs.begin(),logs.end(),[=](const auto&s){return s.find(values)!=std::string::npos;})==1);
 }
 for(fault=2;fault<=13;fault++){
  logs.clear();construct_calls=0;callback_calls=0;queue_publications=0;
  assert(armsx3_core_test_persistent_guest_tls()==-1);restored();
 }
 fault=0;
 // Includes the real TLS bootstrap allocation, in addition to CODE/DATA/stacks.
 for(vm::fail_alloc=1;vm::fail_alloc<=5;vm::fail_alloc++){
  assert(armsx3_core_test_persistent_guest_tls()==-1);restored();
 }
 vm::fail_alloc=0;
 Emu.stopped=false;assert(armsx3_core_test_persistent_guest_tls()==-1);Emu.stopped=true;restored();
 g_cfg.core.ppu_threads=1;assert(armsx3_core_test_persistent_guest_tls()==-1);g_cfg.core.ppu_threads=2;restored();
 fxo.available=false;assert(armsx3_core_test_persistent_guest_tls()==-1);fxo.available=true;restored();
 // Independently call the exact helpers inside the exact production bootstrap.
 vm::init();for(unsigned i=0;i<4;i++)assert(vm::alloc(0x10000,vm::main)==0x10000+i*0x10000);
 std::memcpy(vm::base(0x20080),"iOSProbe",9);
 const ppu_thread_params params{static_cast<vm::addr_t>(0x30000),0x8000,0,{},0,0};
 ppu_thread owner(params,"manual TLS guard context",1000);
 assert(!armsx3_ios_ppu_probe_alloc_peer_tls(&owner,0x50000));
 assert(armsx3_ios_ppu_probe_free_peer_tls(&owner,0x50000,0x570d0)==-1);
 cpu_thread::current=&owner;cpu_thread::live=1;
 const auto guards=+[](ppu_thread*context,u32 pool,void*)->int{
  const auto*bytes=static_cast<const u8*>(vm::base(pool));std::vector<u8>before(bytes,bytes+0x40000);
  assert(!armsx3_ios_ppu_probe_alloc_peer_tls(nullptr,pool));
  assert(!armsx3_ios_ppu_probe_alloc_peer_tls(context,pool+0x10000));
  cpu_thread::current=nullptr;assert(!armsx3_ios_ppu_probe_alloc_peer_tls(context,pool));cpu_thread::current=context;
  assert(!std::memcmp(vm::base(pool),before.data(),before.size()));
  const u32 tls=armsx3_ios_ppu_probe_alloc_peer_tls(context,pool);assert(tls==0x570d0);
  assert(!armsx3_ios_ppu_probe_alloc_peer_tls(context,pool));
  assert(armsx3_ios_ppu_probe_free_peer_tls(context,pool,tls+4)==-1);
  cpu_thread::live=2;assert(armsx3_ios_ppu_probe_free_peer_tls(context,pool,tls)==-1);assert(s_tls_map[1]);cpu_thread::live=1;
  assert(armsx3_ios_ppu_probe_free_peer_tls(context,pool,tls)==0);
  assert(armsx3_ios_ppu_probe_free_peer_tls(context,pool,tls)==-1);
  assert(!std::memcmp(vm::base(pool),before.data(),before.size()));return 0;
 };
 assert(armsx3_ios_ppu_probe_tls_and_call(&owner,0x20080,9,64,guards,nullptr)==0);
 assert(!owner.gpr[13]&&!vm::check_addr(0x50000));
 cpu_thread::current=nullptr;cpu_thread::live=0;vm::close();restored();
 std::puts("PASS: exact P53 bridge and production TLS bootstrap/allocator/free/peer guards plus real bounded dispatch; eight repetitions/16 persistent host workers/128 guest jobs, previous TLS reads/accumulating totals168/246 on same slots, four budget stops and recoveries; all aliases/cleanup/counts, invalid/duplicate/active/double-free guards; corrupt load/data/code/peer TLS slot/constructor r13, queue publication/dropped job/gate cancellation/instruction/constructor/allocation/setup errors restore/join/free; VM/queue/native instruction operations remain host shims");
}
'''
with tempfile.TemporaryDirectory(prefix='p53-pair-') as temp:
    source=Path(temp)/'test.cpp';binary=Path(temp)/'test';source.write_text(shims+production+phase+checks)
    subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)

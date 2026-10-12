"""Exact P67 bridge/native spinlock/binder/bounded/TLS bodies on host models.

Usage: python test_p67_pair.py staged/rpcs3/Emu/Cell/PPUThread.cpp CoreBridge.cpp staged/rpcs3/Emu/Cell/Modules/sys_ppu_thread_.cpp
CPU check_state/atomic wait/VM/registry/queue/decoder are host models;
native test_stopped, service, HLE binding, bounded/TLS bodies are extracted.
No native iOS compile, arbitrary contention or LV2 scheduler claim.
"""
from pathlib import Path
import subprocess,sys,tempfile
if len(sys.argv)!=4:raise SystemExit(__doc__)
previous=Path(__file__).with_name('test_p66_pair.py').read_text()
exec(compile(previous[:previous.index("\nproduction=function(core,")],str(Path(__file__).with_name('test_p66_pair.py')),'exec'))
shims=shims.replace('again=64','again=64,dbg_global_pause=128')
shims=shims.replace('struct flags {', 'extern unsigned fault;struct flags {')
shims=shims.replace('void notify_one(){}', 'void notify_one(){bits.notify_one();}')
shims=shims.replace('void operator-=(u32 f)', 'void operator-=(cpu_flag f){if(fault==199 && f==cpu_flag::dbg_global_pause)return;operator-=(u32(f));}void operator-=(u32 f)')
shims=shims.replace('struct ppu_thread:cpu_thread {','std::atomic<unsigned> native_pause_hits{0};\nstruct ppu_thread:cpu_thread {')
cpu_header=(native.parent/'CPU/CPUThread.h').read_text()
cpu_source=(native.parent/'CPU/CPUThread.cpp').read_text()
for text in ['flags += cpu_flag::wait;', 'cpu_flag::dbg_global_pause + cpu_flag::dbg_pause + cpu_flag::suspend', 'cpu_wait(state1);']:
 assert text in cpu_source,text
assert 'state.wait(old);' in function(core,'void ppu_thread::cpu_wait(')
stopped=function(cpu_header,'[[nodiscard]] bool test_stopped()')
model=r"""bool check_state(){
 if(state&cpu_flag::dbg_global_pause){
  // This models only the specific debugger-pause branch of native check_state.
  // Mutations precede the acquired wait publication, matching the live snapshot.
  if(fault==187){gpr[3]=0;}if(fault==188){cia+=4;}if(fault==189){lr+=4;}
  if(fault==190){current_function=nullptr;}if(fault==191){syscall_history.index++;}
  if(fault==192){fpr[31]=9.0;}if(fault==193){vr[31].bytes[0]^=1;}
  if(fault==194){cr.bits[7]^=1;}if(fault==195){raddr=0x23000;}
  if(fault==196){vm::write32(u32(gpr[6]),0);}if(fault==197){vm::write32(u32(gpr[13]-0x6ff4),99);}
  if(fault==198){vm::write32(0x23004,0);}
  if(fault!=186){state+=cpu_flag::wait;}native_pause_hits++;
  while((state&cpu_flag::dbg_global_pause) && !(state&cpu_flag::exit)){
   const auto old=state.bits.load();if((old&u32(cpu_flag::dbg_global_pause)) && !(old&u32(cpu_flag::exit)))state.bits.wait(old);
  }
  state-=u32(cpu_flag::wait);
 }
 return state.bits.load()&(u32(cpu_flag::stop)|u32(cpu_flag::exit)|u32(cpu_flag::again));
}
"""
old='bool check_state(){return test_stopped();}bool test_stopped(){return state.bits.load()&(u32(cpu_flag::stop)|u32(cpu_flag::exit));}'
assert old in shims
shims=shims.replace(old,model+stopped)
shims=shims.replace('if(fault==169 && x==0)return;', 'if((fault==169 || (fault==200 && (vm::read32(0x23080)&1))) && x==0)return;')
production=function(core,'struct ios_ppu_dispatch_probe')+';\n'
production+='static thread_local ios_ppu_dispatch_probe* s_ios_ppu_dispatch_probe=nullptr;\n'
production+=function(core,'void ppu_thread::exec_task(')+'\n'
production+=function(core,'extern "C" int armsx3_ios_ppu_exec_bounded(')+'\n'
production+='void assert_dispatch_clear(){assert(!s_ios_ppu_dispatch_probe);assert(cpu_thread::current);assert(id_manager::g_id==0);}\n'
tls=Path(sys.argv[3]).read_text()
production+=tls[tls.index('static u32 s_tls_addr'):tls.index('static u32 ppu_alloc_tls()')]+'\n'
for signature in ['static u32 ppu_alloc_tls(', 'static void ppu_free_tls(', 'static void ppu_initialize_tls_memory(',
                  'extern "C" int armsx3_ios_ppu_probe_tls_and_call(', 'static bool ios_probe_tls_pair_owner(',
                  'extern "C" u32 armsx3_ios_ppu_probe_alloc_peer_tls(', 'extern "C" int armsx3_ios_ppu_probe_free_peer_tls(']:
    production+=function(tls,signature)+'\n'
phase=function(bridge,'extern "C" __attribute__((visibility("default"))) int armsx3_core_test_blocking_spinlock_handoff(')
# Reuse the full independent TLS guard, setup and failure cleanup checks.
tail=template[template.index("checks=r'''")+len("checks=r'''"):template.index("\n'''\nwith tempfile.TemporaryDirectory")]
tail=tail.replace('armsx3_core_test_guest_spinlock_handoff','armsx3_core_test_blocking_spinlock_handoff')
tail=tail.replace('callback_calls==50','callback_calls==38').replace('queue_publications==50','queue_publications==38')
start=tail.index('  assert(lock_compares==18');end=tail.index('  for(const char* values:',start)
tail=tail[:start]+'''  assert(reserved_loads==0 && conditional_stores==0 && calls==21);
  assert(executed==165 && native_pause_hits==3 && tls_stores==6 && output_stores==54 && stack_stores==0 && fp_loads==0 && vec_loads==0);
''' +tail[end:]
tail=tail.replace('queue_publications=0;executed=0;', 'queue_publications=0;native_pause_hits=0;executed=0;')
tail=tail.replace('counter=2 checksum=3 TLS=1/1 results=1/1','counter=2 checksum=3 TLS=1/1 results=1/6').replace('counter=4 checksum=10 TLS=2/2 results=1/1','counter=4 checksum=10 TLS=2/2 results=6/1').replace('counter=6 checksum=21 TLS=3/3 results=1/1','counter=6 checksum=21 TLS=3/3 results=1/6')
start=tail.index(' const std::vector<int> faults');end=tail.index('\n for(int value:faults)',start)
tail=tail[:start]+''' const std::vector<int> faults{2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,23,26,27,36,37,38,39,40,41,60,153,
 168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,190,191,192,193,194,195,196,197,198,199,200};''' +tail[end:]
start=tail.index(' std::puts(');end=tail.index('\n}',start)
tail=tail[:start]+''' std::puts("PASS: exact P67/native spinlock services/native HLE binder/native test_stopped/bounded/TLS helpers; eight runs/16 retained host workers/576 slices,72dispatches/66pauses/186 steps(165 instructions+21 HLE calls),21 guest BL calls, six busy returns, final lock0/counter6/checksum21/TLS3/3, full ABI/history/context/memory/cache/cleanup; three controlled in-service native pause snapshots/unlock/resume handoffs; selected foundational and168..200 faults/all allocation/setup/TLS guard negatives detected. CPU check_state/atomic wait/VM/atomic storage/registry/queue/decoder/instructions remain host models; native iOS compile/device execution pending.");''' +tail[end:]
with tempfile.TemporaryDirectory(prefix='p67-pair-') as temp:
    source=Path(temp)/'test.cpp';binary=Path(temp)/'test'
    source.write_text(shims+binding+macro+'\n'+services+'\n'+registry+production+phase+tail)
    subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)

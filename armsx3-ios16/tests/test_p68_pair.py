"""Exact P68 bridge/native spinlock/binder/bounded/TLS bodies on host models.

Usage: python test_p68_pair.py staged/rpcs3/Emu/Cell/PPUThread.cpp CoreBridge.cpp staged/rpcs3/Emu/Cell/Modules/sys_ppu_thread_.cpp
CPU check_state/atomic wait/VM/registry/queue/decoder are host models;
native test_stopped/cpu_on_stop/fast_call, services, HLE binding and bounded/TLS
bodies are extracted. Host-only fast_call mutations test recovery failures.
No native iOS compile, arbitrary contention or LV2 scheduler claim.
"""
from pathlib import Path
import subprocess,sys,tempfile
if len(sys.argv)!=4:raise SystemExit(__doc__)
previous=Path(__file__).with_name('test_p67_pair.py').read_text()
exec(compile(previous[:previous.index("\nproduction=function(core,")],str(Path(__file__).with_name('test_p67_pair.py')),'exec'))
# Extend the established native CPU pause model and its exact test_stopped.
shims=shims.replace('void exec_task();', r"""bool loaded_from_savestate=false,perf_stats_reported=false;
 u64 start_time=0,last_succ=0,last_fail=0,exec_bytes=0;
 struct {u32 addr=0;}entry_func;
 struct NameStore{std::shared_ptr<std::string>value=std::make_shared<std::string>("host PPU");
  bool is_equal(const std::shared_ptr<std::string>&p)const{return value==p;}
  template<class F>void peek_op(F f){f(value);}
 }ppu_tname;
 bool is_stopped()const{return state.bits.load()&(u32(cpu_flag::stop)|u32(cpu_flag::exit)|u32(cpu_flag::again));}
 void dump_all(std::string&)const{}
 void cpu_on_stop();void fast_call(u32,u64,bool=false);void exec_task();""")
shims=shims.replace('setting<bool> ppu_prof{true}', 'setting<bool> ppu_debug{false};setting<bool> ppu_prof{true}')
shims=shims.replace('template<class T>T&get(){return interpreter;}', 'template<class T>T&get(){if constexpr(std::is_same_v<T,ppu_interpreter_rt>)return interpreter;else{static T value;return value;}}')
registry=registry.replace('class ppu_function_manager{public:', 'class ppu_function_manager{public:u32 func_addr(u32,bool=false)const{return 0;}bool is_func(u32)const{return false;}')
shims=shims.replace('return state.bits.load()&(u32(cpu_flag::stop)|u32(cpu_flag::exit)|u32(cpu_flag::again));\n}',
 'const bool stopped=state.bits.load()&(u32(cpu_flag::stop)|u32(cpu_flag::exit)|u32(cpu_flag::again));if(stopped)cpu_on_stop();return stopped;\n}')
shims=shims.replace('if(state&cpu_flag::dbg_global_pause){', 'if((state&cpu_flag::dbg_global_pause) && !(state&cpu_flag::exit)){')
shims=shims.replace('&& !(state&cpu_flag::exit)', '&& !(state&cpu_flag::stop) && !(state&cpu_flag::again) && !(state&cpu_flag::exit)')
shims=shims.replace('!(old&u32(cpu_flag::exit))', '!(old&(u32(cpu_flag::stop)|u32(cpu_flag::again)|u32(cpu_flag::exit)))')
# Native fixup fault models alter the saved input after the interrupted binder,
# or a final CIA/logging boundary, so the production replay checks must catch it.
extras=r"""
template<class T>using shared_ptr=std::shared_ptr<T>;
thread_local std::string(*g_tls_log_prefix)()=nullptr;
struct {template<class...T>void error(const char*,T...){}template<class...T>void notice(const char*,T...){}
 template<class...T>void warning(const char*,T...){} }ppu_log,perf_log;
u64 get_guest_system_time(){return 0;}
namespace fmt{template<class...T>std::string format(const char*,T...){return "host prefix";}}
const char*get_prx_name_by_cia(u32){return nullptr;}
struct lv2_obj{static void sleep(ppu_thread&){assert(false);}};
"""
production=function(core,'struct ios_ppu_dispatch_probe')+';\n'
production+='static thread_local ios_ppu_dispatch_probe* s_ios_ppu_dispatch_probe=nullptr;\n'
production+=function(core,'void ppu_thread::exec_task(')+'\n'
production+=function(core,'void ppu_thread::cpu_on_stop(')+'\n'
fast_call=function(core,'void ppu_thread::fast_call(')
# Mutation checks run only in this host executable. With fault0 the extracted
# native operations execute unchanged; the delivered core is never patched.
assert 'std::memcpy(&gpr[3], syscall_args, sizeof(syscall_args));' in fast_call
fast_call=fast_call.replace('std::memcpy(&gpr[3], syscall_args, sizeof(syscall_args));',
 'if(fault!=201){std::memcpy(&gpr[3], syscall_args, sizeof(syscall_args));}if(fault==205){gpr[10]^=1;}')
fast_call=fast_call.replace('cia -= 4;', 'if(fault!=202){cia -= 4;}if(fault==203){cia -= 4;}')
fast_call=fast_call.replace('state -= cpu_flag::ret;', 'state -= cpu_flag::ret;if(fault==204){g_tls_log_prefix=+[](){return std::string{"bad prefix"};};}')
fast_call=fast_call.replace('lr = old_lr;', 'lr = old_lr;if(fault==206){lr=0;}')
production+=fast_call+'\n'
production+=function(core,'extern "C" int armsx3_ios_ppu_exec_bounded(')+'\n'
production+='void assert_dispatch_clear(){assert(!s_ios_ppu_dispatch_probe);assert(cpu_thread::current);assert(id_manager::g_id==0);}\n'
tls=Path(sys.argv[3]).read_text()
production+=tls[tls.index('static u32 s_tls_addr'):tls.index('static u32 ppu_alloc_tls()')]+'\n'
for signature in ['static u32 ppu_alloc_tls(', 'static void ppu_free_tls(', 'static void ppu_initialize_tls_memory(',
                  'extern "C" int armsx3_ios_ppu_probe_tls_and_call(', 'static bool ios_probe_tls_pair_owner(',
                  'extern "C" u32 armsx3_ios_ppu_probe_alloc_peer_tls(', 'extern "C" int armsx3_ios_ppu_probe_free_peer_tls(']:
    production+=function(tls,signature)+'\n'
phase=function(bridge,'extern "C" __attribute__((visibility("default"))) int armsx3_core_test_interrupted_spinlock_replay(')
# Reuse the full independent TLS guard, setup and failure cleanup checks.
tail=template[template.index("checks=r'''")+len("checks=r'''"):template.index("\n'''\nwith tempfile.TemporaryDirectory")]
tail=tail.replace('armsx3_core_test_guest_spinlock_handoff','armsx3_core_test_interrupted_spinlock_replay')
tail=tail.replace('callback_calls==50','callback_calls==38').replace('queue_publications==50','queue_publications==38')
start=tail.index('  assert(lock_compares==18');end=tail.index('  for(const char* values:',start)
tail=tail[:start]+'''  assert(reserved_loads==0 && conditional_stores==0 && calls==21);
  assert(executed==165 && native_pause_hits==3 && tls_stores==6 && output_stores==54 && stack_stores==0 && fp_loads==0 && vec_loads==0);
''' +tail[end:]
tail=tail.replace('queue_publications=0;executed=0;', 'queue_publications=0;native_pause_hits=0;executed=0;')
tail=tail.replace('counter=2 checksum=3 TLS=1/1 results=1/1','counter=2 checksum=3 TLS=1/1 results=1/6').replace('counter=4 checksum=10 TLS=2/2 results=1/1','counter=4 checksum=10 TLS=2/2 results=6/1').replace('counter=6 checksum=21 TLS=3/3 results=1/1','counter=6 checksum=21 TLS=3/3 results=1/6')
start=tail.index(' const std::vector<int> faults');end=tail.index('\n for(int value:faults)',start)
tail=tail[:start]+''' const std::vector<int> faults{2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,23,26,27,36,37,38,39,40,41,60,153,
 168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,190,191,192,193,194,195,196,197,198,200,201,202,203,204,205,206};''' +tail[end:]
start=tail.index(' std::puts(');end=tail.index('\n}',start)
tail=tail[:start]+''' std::puts("PASS: P68/extracted native spinlock services/HLE binder/test_stopped/cpu_on_stop/fast_call/bounded/TLS helpers; eight runs/16 retained host workers/576 slices,72dispatches/66pauses/192 steps(165 instructions+24 HLE calls+3 nested diagnostic dispatches),21 guest BL calls, six busy returns, final lock0/counter6/checksum21/TLS3/3, full ABI/history/context/memory/cache/cleanup; three controlled interrupted service/input-preservation/native cold fast_call fixup/retry handoffs; selected foundational and168..198/200..206 faults/all allocation/setup/TLS guard negatives detected, including host-only native fast_call mutations. CPU check_state/atomic wait/VM/atomic storage/registry/queue/decoder/instructions remain host models; native iOS compile/device execution pending.");''' +tail[end:]
with tempfile.TemporaryDirectory(prefix='p68-pair-') as temp:
    source=Path(temp)/'test.cpp';binary=Path(temp)/'test'
    source.write_text(shims+extras+binding+macro+'\n'+services+'\n'+registry+production+phase+tail)
    subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)

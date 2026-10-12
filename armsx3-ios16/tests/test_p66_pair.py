"""Exact P66 bridge, native spinlock services and HLE binder on host shims.

Usage: python test_p66_pair.py staged/rpcs3/Emu/Cell/PPUThread.cpp CoreBridge.cpp staged/rpcs3/Emu/Cell/Modules/sys_ppu_thread_.cpp
CPU/VM/queue/registry/atomic storage/instruction operations are host models.
The production bounded dispatch, TLS, service and binder bodies are extracted.
This is not an iOS native compile or proof of blocking contention scheduling.
"""
from pathlib import Path
import subprocess,sys,tempfile
if len(sys.argv)!=4:raise SystemExit(__doc__)
# Reuse the established shim construction, without running the P65 workload.
template=Path(__file__).with_name('test_p65_pair.py').read_text()
exec(compile(template[:template.index("production=function(core,")],str(Path(__file__).with_name('test_p65_pair.py')),'exec'))
shims=shims.replace('queue_publications==50','queue_publications==38').replace('size==116','size==272')
shims=shims.replace('ret=32','ret=32,again=64')
shims=shims.replace('u32 operator+(cpu_flag a', 'bool operator-(cpu_flag f,const struct flags& s);\nu32 operator+(cpu_flag a')
shims=shims.replace('struct ppu_thread;','bool operator-(cpu_flag f,const flags&s){return !(s&f);}\nstruct ppu_thread;')
shims=shims.replace('struct{u64 index=0;}syscall_history;',r'''struct {
 struct entry_t {u64 cia=0;const char*func_name=nullptr;u64 error=0;std::array<u64,4>args{};};
 std::vector<entry_t>data=std::vector<entry_t>(1);u64 index=0;u32 count_debug_arguments=0;
 }syscall_history;const char*current_function=nullptr;const char*last_function=nullptr;const char*current_module=nullptr;u64 syscall_args[8]{};''')
shims=shims.replace('void ppu_register_function_at(u32 begin,u32 size,void*)', 'void ppu_register_function_at(u32 begin,u32 size,ppu_intrp_func_t handler)')
shims=shims.replace('p->fn=instruction;', 'p->fn=handler?handler:instruction;if(fault==168 && handler && begin==0x10108)p->fn=instruction;')
shims=shims.replace('namespace utils{',r'''extern unsigned fault;
namespace vm {
 u32 get_addr(const void*p){return u32(static_cast<const u8*>(p)-memory.data());}
 template<class T>struct ptr{u32 address;T&operator*()const{return *reinterpret_cast<T*>(base(address));}T*operator->()const{return &**this;}};
}
// Atomic storage is a scalar BE host model. Service calls are ordered so no
// modeled ordinary read overlaps a modeled exchange on the same lock word.
template<class T>struct atomic_be_t {
 be_t<T>value;operator T()const{return value;}
 void operator=(T x){if(fault==169 && x==0)return;value=x;if(fault==178)vm::write32(0x23004,0);}
 T exchange(T x){const T old=value;value=(fault==170?1:x);return old;}
};
constexpr s32 CELL_OK=0;constexpr u32 CELL_EBUSY=0x8001000a;
struct error_code{s32 value=0;error_code()=default;error_code(s32 x):value(x){}operator s32()const{return value;}};
s32 not_an_error(u32 x){return s32(fault==171?0:x);}
#define FORCE_INLINE inline
template<class T>u64 ppu_gpr_cast(const T&value){return u64(value);}
template<class T,class S>T ppu_gpr_cast(const S&value){if constexpr(std::is_same_v<T,vm::ptr<atomic_be_t<u32>>>)return T{u32(value)};else return T(value);}
namespace utils{''')
shims=shims.replace('void error(const char*,T...){}', 'void error(const char*,T...){}template<class...T>void trace(const char*,T...){}')
shims=shims.replace('void exec_task();', 'u64*get_stack_arg(u32,u32){assert(false);return gpr;}void exec_task();')
# fault172 corrupts the guest argument before the exact HLE wrapper sees it.
shims=shims.replace('case 14:c.gpr[rt]=(ra?c.gpr[ra]:0)+imm;',
 'case 14:c.gpr[rt]=(ra?c.gpr[ra]:0)+imm;if(fault==172 && rt==3)c.gpr[rt]+=4;')
shims=shims.replace('if(fault==40 || fault==158)', 'if(fault==40 || fault==158)')
shims=shims.replace('if(fault==60)this->raddr=0x21080;',r'''if(fault==60)this->raddr=0x21080;
 if(fault==173 && this->syscall_history.index)this->syscall_history.index++;
 if(fault==174 && this->syscall_history.index)this->syscall_history.data[0].error^=1;
 if(fault==175 && this->syscall_history.index)this->syscall_history.data[0].args[0]^=1;
 if(fault==176 && this->syscall_history.index)this->current_function="leaked HLE";
 if(fault==177 && this->syscall_history.index)this->syscall_args[6]^=1;
 if(fault==179 && this->syscall_history.index)this->syscall_history.data[0].func_name="wrong service";
 if(fault==180 && this->syscall_history.index)this->syscall_history.data[0].cia+=4;''')
shims=shims.replace('if(fault==153){c.gpr[11]-=2*c.gpr[10];}', 'if(fault==153){c.gpr[11]-=2*c.gpr[10];}')
shims=shims.replace('if(fault==3)vm::write32', 'if(fault==181 && rt==9 && ra==5)vm::write32(0x23080,99);if(fault==182 && rt==10 && ra==6)vm::write32(u32(c.gpr[6]+8),0);if(fault==3)vm::write32')
shims=shims.replace('if(fault==23 && (x&1))', 'if((fault==23 || fault==183) && (x&1))')
shims=shims.replace('if(x&1){c.lr=pc+4;++calls;}', 'if(x&1){c.lr=pc+4;++calls;if(fault==184)c.lr+=4;}')

# Extract the exact binding wrapper, argument/result templates and registered
# BLR-return macro. Generic cast and VM pointer/storage remain shim operations.
native=Path(sys.argv[1]).parent
binding=(native/'PPUFunction.h').read_text()
binding=binding[binding.index('// BIND_FUNC macro'):binding.index('class ppu_function_manager')]
module=(native/'PPUModule.h').read_text()
macro=module[module.index('#define BIND_FUNC_WITH_BLR'):module.index('\n\n',module.index('#define BIND_FUNC_WITH_BLR'))]
spin=(native/'Modules/sys_spinlock.cpp').read_text()
services='\n'.join(function(spin,sig) for sig in ['void sys_spinlock_initialize(', 'error_code sys_spinlock_lock(', 'error_code sys_spinlock_trylock(', 'void sys_spinlock_unlock('])
registry=r'''
class ppu_function_manager{public:static const auto&get(){static const std::vector<ppu_intrp_func_t>handlers{
 BIND_FUNC_WITH_BLR(sys_spinlock_initialize,"sysPrxForUser"),BIND_FUNC_WITH_BLR(sys_spinlock_lock,"sysPrxForUser"),
 BIND_FUNC_WITH_BLR(sys_spinlock_trylock,"sysPrxForUser"),BIND_FUNC_WITH_BLR(sys_spinlock_unlock,"sysPrxForUser")};return handlers;}};
struct ppu_static_function{const char*name;u32 index;};
struct ppu_static_module{std::vector<std::pair<u32,ppu_static_function>>functions{
 {0,{"sys_spinlock_initialize",0}},{1,{"sys_spinlock_lock",1}},{2,{"sys_spinlock_trylock",2}},{3,{"sys_spinlock_unlock",3}}};};
class ppu_module_manager{public:static const ppu_static_module*get_module(const std::string&name){
 assert(name=="sysPrxForUser");static ppu_static_module module;
 return fault==185?nullptr:&module;
}};
'''
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
phase=function(bridge,'extern "C" __attribute__((visibility("default"))) int armsx3_core_test_hle_spinlock_handoff(')
# Reuse the full independent TLS guard, setup and failure cleanup checks.
tail=template[template.index("checks=r'''")+len("checks=r'''"):template.index("\n'''\nwith tempfile.TemporaryDirectory")]
tail=tail.replace('armsx3_core_test_guest_spinlock_handoff','armsx3_core_test_hle_spinlock_handoff')
tail=tail.replace('callback_calls==50','callback_calls==38').replace('queue_publications==50','queue_publications==38')
start=tail.index('  assert(lock_compares==18');end=tail.index('  for(const char* values:',start)
tail=tail[:start]+'''  assert(reserved_loads==0 && conditional_stores==0 && calls==21);
  assert(executed==165 && tls_stores==6 && output_stores==54 && stack_stores==0 && fp_loads==0 && vec_loads==0);
''' +tail[end:]
start=tail.index(' const std::vector<int> faults');end=tail.index('\n for(int value:faults)',start)
tail=tail.replace('counter=2 checksum=3 TLS=1/1 results=1/1','counter=2 checksum=3 TLS=1/1 results=1/6').replace('counter=4 checksum=10 TLS=2/2 results=1/1','counter=4 checksum=10 TLS=2/2 results=6/1').replace('counter=6 checksum=21 TLS=3/3 results=1/1','counter=6 checksum=21 TLS=3/3 results=1/6')
tail=tail[:start]+''' const std::vector<int> faults{2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,23,26,27,36,37,38,39,40,41,60,153,
 168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185};''' +tail[end:]
start=tail.index(' std::puts(');end=tail.index('\n}',start)
tail=tail[:start]+''' std::puts("PASS: exact P66/native spinlock service bodies/native HLE binder/native bounded and TLS helpers; eight runs/16 retained host workers/576 slices,72dispatches/66pauses/186 steps(165 instructions+21 HLE calls),21 guest BL calls, six busy returns, final lock0/counter6/checksum21/TLS3/3, full ABI/history/context/memory/cache/cleanup; selected foundational and168..185 faults/all allocation/setup/TLS guard negatives detected. CPU/VM/atomic storage/registry/queue/decoder/instructions remain host models; native iOS compile/device execution pending.");''' +tail[end:]
with tempfile.TemporaryDirectory(prefix='p66-pair-') as temp:
    source=Path(temp)/'test.cpp';binary=Path(temp)/'test'
    source.write_text(shims+binding+macro+'\n'+services+'\n'+registry+production+phase+tail)
    subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)

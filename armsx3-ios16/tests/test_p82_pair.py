"""P82-P85 native event flag services and five-argument guest wait ABI.
Usage: test_p82_pair.py PPUThread.cpp CoreBridge.cpp sys_ppu_thread_.cpp [and|or|clear|clear_all]
CPU/VM/ID/atomic/clock/scheduler use explicit host models. Native iOS pending.
"""
from pathlib import Path
import sys
profile=sys.argv.pop() if len(sys.argv)==5 else 'and'
assert profile in ('and','or','clear','clear_all'),profile
symbol='armsx3_core_test_event_flag_'+profile
parent=Path(__file__).with_name('test_p79_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
def replace(a,b):
 global source
 assert a in source,a
 source=source.replace(a,b)
replace('P79','P82-P85');replace('armsx3_core_test_semaphore_timeout_then_wake',symbol)
replace('sys_semaphore','sys_event_flag');replace('semaphore_source','event_source');replace('lv2_sema','lv2_event_flag')
replace('0x96000000','0x98000000');replace('0x9600ff01','0x9800ff01');replace('semaphore_timeout_observations','event_timeout_observations')
replace("[(90,'create'),(91,'destroy'),(92,'wait'),(93,'trywait'),(94,'post'),(114,'get_value')]", "[(82,'create'),(83,'destroy'),(85,'wait'),(86,'trywait'),(87,'set'),(118,'clear'),(132,'cancel'),(139,'get')]")
replace('==119','==128');replace('size==48','size==52')
# Put common state and virtual check_state on the modeled CPU base as in native.
replace("shims=shims.replace('signal=128}'", """shims=shims.replace('virtual~cpu_thread()=default;', 'u32 id=0;flags state;virtual bool check_state()=0;virtual~cpu_thread()=default;')
shims=shims.replace('u32 id=0,cia=0,stack_addr,stack_size;', 'u32 cia=0,stack_addr,stack_size;')
shims=shims.replace('flags state;notification cmd_notify;', 'notification cmd_notify;')
shims=shims.replace('signal=128}'""")
replace('using shared_mutex=std::mutex;', 'struct shared_mutex:std::mutex{void lock_unlock(){std::lock_guard lock(*this);}};')
replace('CELL_ETIMEDOUT=0x8001000b};','CELL_ETIMEDOUT=0x8001000b,CELL_EAGAIN=0x80010001,CELL_ECANCELED=0x80010013};')
replace('constexpr u32 SYS_SYNC_FIFO=1,SYS_SYNC_PRIORITY=2,SYS_SYNC_NOT_PROCESS_SHARED=0x200;', 'constexpr u32 SYS_SYNC_FIFO=1,SYS_SYNC_PRIORITY=2,SYS_SYNC_NOT_PROCESS_SHARED=0x200,SYS_SYNC_WAITER_SINGLE=0x10000,SYS_SYNC_WAITER_MULTIPLE=0x20000,SYS_EVENT_FLAG_WAIT_AND=1,SYS_EVENT_FLAG_WAIT_OR=2,SYS_EVENT_FLAG_WAIT_CLEAR=0x10,SYS_EVENT_FLAG_WAIT_CLEAR_ALL=0x20;constexpr s32 smax=0x7fffffff;')
replace('be_t<u32>pad;', 'be_t<s32>type;')
# The native wait log sees parameters before event_flag_set uses scratch GPRs.
a=source.index(' void trace(const char*text,u32,u64 timeout)');b=source.index(' template<class...T>void trace',a)
source=source[:a]+''' void trace(const char*,u32,u64 bitptn,u32 mode,vm::ptr<u64>result,u64 timeout){
  auto*c=static_cast<ppu_thread*>(get_current_cpu_thread());if(!c||bitptn!=c->gpr[4]||mode!=c->gpr[5]||result.address!=c->gpr[6]||timeout!=c->gpr[7])throw std::runtime_error("event wait native five-argument ABI truncated");++event_timeout_observations;
 }
'''+source[b:]
a=source.index('struct lv2_event_flag:lv2_obj{');b=source.index('class idm{',a)
source=source[:a]+'''struct lv2_event_flag:lv2_obj{
 static constexpr u32 id_base=0x98000000;
 const u32 protocol;const u64 key;const s32 type;const u64 name;shared_mutex mutex;atomic_t<u64>pattern;ppu_thread*sq=nullptr;
 lv2_event_flag(u32 p,u64 k,s32 t,u64 n,u64 v):protocol(p),key(k),type(t),name(n),pattern(v){}
 static bool check_mode(u32);static bool check_pattern(u64&,u64,u64,u64*);
};
'''+source[b:]
replace('template<class B,class T,class F>static auto check(u32 id,F f)', 'template<class B,class T>static auto get_unlocked(u32 id){std::lock_guard lock(guard);auto it=objects.find(id);return it==objects.end()?shared_ptr<T>{}:it->second;}\n template<class B,class T,class F>static auto check(u32 id,F f)')
# Replace the old service mutation block with complete event flag bodies.
a=source.index("services='\\n'.join");b=source.index('table=r"""',a)
source=source[:a]+r'''
for sig in ['static bool check_mode(', 'static bool check_pattern(']:
 body=function(header,sig).replace('static bool ', 'bool lv2_event_flag::',1)
 if 'check_pattern' in sig:
  body=body.replace('pattern &= ~bitptn;', 'if(fault!=282){pattern &= ~bitptn;}').replace('pattern = 0;', 'if(fault!=283){pattern = 0;}')
  body=body.replace('(pattern & bitptn) != bitptn', '(fault==284 ? false : (pattern & bitptn) != bitptn)')
  body=body.replace('(pattern & bitptn) == 0', '(fault==290 ? (pattern & bitptn) != bitptn : (pattern & bitptn) == 0)')
 else:body=body.replace('return false;', 'return fault==280;')
 extras+=body+'\n'
extras+=function(event_source,'struct sys_event_store_result')+';\n'
extras+='void eflag_record(u32,u32,char,u64,u64){}\n'
extras=extras.replace('static T* unqueue(T*& first, T* object, T* T::* mem_ptr = &T::next_cpu)\n\t{', 'static T* unqueue(T*& first, T* object, T* T::* mem_ptr = &T::next_cpu)\n\t{if(fault==265 && mem_ptr==&T::next_cpu){return {};}')
services='\n'.join(function(event_source,'error_code sys_event_flag_'+name+'(') for name in ['create','destroy','wait','trywait','set','clear','cancel','get'])
services=services.replace('ppu.gpr[3] = CELL_ETIMEDOUT;', 'ppu.gpr[3] = fault==263?u64(CELL_OK):u64(CELL_ETIMEDOUT);')
services=services.replace('const auto _attr = *attr;', 'const auto _attr = *attr;')
services=services.replace('init);', 'fault==281?u64(u32(init)):init);')
services=services.replace('*flags = flag.ret;', 'if(fault!=285){*flags = flag.ret;}')
services=services.replace('flag.pattern &= bitptn;', 'if(fault!=286){flag.pattern &= bitptn;}')
services=services.replace('if (flags) *flags = 0;', 'if (flags && fault!=287) *flags = 0;')
services=services.replace('return not_an_error(CELL_EBUSY);', 'return fault==288?u32(CELL_OK):u32(not_an_error(CELL_EBUSY));')
services=services.replace('*num = value;', '*num = fault==289?value+1:value;')
''' +source[b:]
a=source.index(' table[90]=');b=source.index('return table;}();',a)
source=source[:a]+''' table[82]={BIND_FUNC(sys_event_flag_create),"sys_event_flag_create"};table[83]={BIND_FUNC(sys_event_flag_destroy),"sys_event_flag_destroy"};
 table[85]={BIND_FUNC(sys_event_flag_wait),"sys_event_flag_wait"};table[86]={BIND_FUNC(sys_event_flag_trywait),"sys_event_flag_trywait"};
 table[87]={BIND_FUNC(sys_event_flag_set),"sys_event_flag_set"};table[118]={BIND_FUNC(sys_event_flag_clear),"sys_event_flag_clear"};
 table[132]={BIND_FUNC(sys_event_flag_cancel),"sys_event_flag_cancel"};table[139]={BIND_FUNC(sys_event_flag_get),"sys_event_flag_get"};'''+source[b:]
needle='phase=function(bridge,\'extern "C" __attribute__((visibility("default"))) int '+symbol+'(\')'
replace(needle, 'phase=function(bridge,\'static int armsx3_core_test_event_flag_batch(\')+"\\n"+function(bridge,\'extern "C" __attribute__((visibility("default"))) int '+symbol+'(\')')
replace('executed==936 && tls_stores==78 && output_stores==156','executed==1092 && tls_stores==84 && output_stores==168')
replace('event_timeout_observations==15','event_timeout_observations==9')
a=source.index('assert(syscall_usage.stat[90]');b=source.index("\n''' +checks[b:]",a)
source=source[:a]+'''assert(syscall_usage.stat[82]==9 && syscall_usage.stat[83]==3 && syscall_usage.stat[85]==9 && syscall_usage.stat[86]==21 && syscall_usage.stat[87]==12 && syscall_usage.stat[118]==6 && syscall_usage.stat[132]==6 && syscall_usage.stat[139]==18);'''+source[b:]
for old,new in [(13,14),(26,28),(39,42)]:replace(f'TLS={old}/{old}',f'TLS={new}/{new}')
# Keep applicable ABI/context/queue/registry negatives; event-specific faults
# replace semaphore permit/post metadata mutations. CLEAR mutations apply to
# the matching clearing profile only.
import re
faults=[2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,26,27,36,37,38,39,40,41,60,173,174,175,176,177,179,180,22,212,213,214,216,224,260,261,262,263,265,266,280,281,284,285,286,287,288,289,290]
if profile=='clear':faults.append(282)
if profile=='clear_all':faults.append(283)
source=re.sub(r'const std::vector<int> faults\{[0-9,]+\};','const std::vector<int> faults{'+','.join(map(str,faults))+'};',source)
replace('std::make_shared<lv2_event_flag>(1,0,0,3,2)', 'std::make_shared<lv2_event_flag>(1,0,SYS_SYNC_WAITER_SINGLE,0,2)')
a=source.index(' std::puts("PASS: P82-P85');b=source.index("''' +checks[b:]",a)
source=source[:a]+' std::puts("PASS: '+profile+' P82-P85 native event flag eight APIs/mode and atomic pattern methods/SC/binder/five-argument ABI/TLS/bounded/scheduler scope;8runs/16workers/84SC each/three timeout-requeue-set wakes/full64 outputs and context cleanup;applicable foundational/ABI/registry/queue and event mode/output/clear mutations280..290 detected;CPU/VM/ID/atomic/clock/scheduler are host models;native iOS pending.");'+source[b:]
source=source.replace('str(binary)],check=True)', 'str(binary)],check=True,timeout=180)')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

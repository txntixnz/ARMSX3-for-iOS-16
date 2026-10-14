"""P106-P113 real shared IPC connection and buffered delivery workload.
Native IPC manager, shared creation/destruction, lookup, queue send, syscalls,
binder and guest workload execute on CPU/VM/ID/clock/scheduler host interfaces.
Usage: test_p106_pair.py PPUThread.cpp CoreBridge.cpp sys_ppu_thread_.cpp PROFILE
"""
from pathlib import Path
from collections import Counter
import re,sys
ipc_profile=sys.argv.pop() if len(sys.argv)==5 else 'ppu_fifo_named'
profiles=[f'{q}_{p}_{n}' for q in ('ppu','spu') for p in ('fifo','priority') for n in ('named','auto')]
assert ipc_profile in profiles
parent=Path(__file__).with_name('test_p94_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
ipc_symbol='armsx3_core_test_event_ipc_'+ipc_profile
def replace(a,b):
 global source
 assert a in source,a
 source=source.replace(a,b)
replace('P94-P97','P106-P113');replace(event_symbol,ipc_symbol)
replace('static int armsx3_core_test_event_queue_batch(', 'static int armsx3_core_test_event_ipc_batch(')
replace("(138,'sys_event_port_send')]", "(138,'sys_event_port_send'),(140,'sys_event_port_connect_ipc')]")
replace('table[138]={BIND_FUNC(sys_event_port_send),"sys_event_port_send"};', 'table[138]={BIND_FUNC(sys_event_port_send),"sys_event_port_send"};\n table[140]={BIND_FUNC(sys_event_port_connect_ipc),"sys_event_port_connect_ipc"};')
replace('struct lv2_event_queue:lv2_obj{', 'struct lv2_event_queue:lv2_obj{static shared_ptr<lv2_event_queue>find(u64);')
replace('assert(sleep_count==6 && wake_count==6);assert(semaphore_timeout_observations==9);', 'assert(sleep_count==0 && wake_count==0);assert(semaphore_timeout_observations==0);')
a=source.index('assert(syscall_usage.stat[128]');b=source.index("\n''' +checks[b:]",a)
first=[128,128,140,136,138,138,131,138,129,140,128,140,131,137,140,135,137,140,129,140]
second=[134,140,140,140,138,131,133,131,138,137,140,138,133,138,140,133,135,138,131,129]
counts=Counter(first+second)
source=source[:a]+'assert('+ ' && '.join(f'syscall_usage.stat[{c}]=={n*3}' for c,n in sorted(counts.items()))+');'+source[b:]

# Extract production IPC container and generic shared-object create/destroy
# methods. Only locking, shared pointers, FXO access and ID storage are adapted.
inject=r"""
ipc_header=(native.parent/'IPC.h').read_text()
ipc_class=ipc_header[ipc_header.index('template <typename T, typename K>'):]
ipc_class=ipc_class.replace('null_ptr','shared_ptr<T>{}')
ipc_class=ipc_class.replace('m_map.erase(ipc_key) != 0','fault==365 && get_current_cpu_thread()!=nullptr?false:m_map.erase(ipc_key) != 0')
ipc_class=ipc_class.replace('const auto found = m_map.find(ipc_key);','const auto found = m_map.find(fault==366?u64(u32(ipc_key)):ipc_key);')
ipc_class=ipc_class.replace('if (!existed)','if (!existed || fault==368)')
ipc_class=ipc_class.replace('const bool added = !existed && ptr;','const bool added = fault==368?bool(ptr):!existed && ptr;')
shims=shims.replace('struct Fxo{','template<class T,class K>class ipc_manager;template<class T>struct is_ipc:std::false_type{};template<class T,class K>struct is_ipc<ipc_manager<T,K>>:std::true_type{};template<class T>T&host_ipc();\nstruct Fxo{')
shims=shims.replace('else return syscall_usage;', 'else if constexpr(is_ipc<T>::value)return host_ipc<T>();else return syscall_usage;')
extras=extras.replace('CELL_EISCONN=0x80010015,','CELL_EEXIST=0x80010014,CELL_EISCONN=0x80010015,')
extras=extras.replace('SYS_SYNC_NEWLY_CREATED=1,','SYS_SYNC_NEWLY_CREATED=1,SYS_SYNC_NOT_CREATE=2,SYS_SYNC_NOT_CARE=3,')
extras=extras.replace('struct lv2_obj{', '#include <unordered_map>\nusing reader_lock=std::lock_guard<shared_mutex>;\n'+ipc_class+'\ntemplate<class T>T&host_ipc(){static T value;return value;}\nstruct lv2_obj{',1)
extras=extras.replace('template<class T,class F>static error_code create(u32,u64,s32,F);', 'template<class T,class F,class...Args>static error_code create(u32,u64,s32,F&&,bool=true,Args&&...);')
old_destroy='template<class T>static void on_id_destroy(T&obj,u64 key){assert(!key);obj.exists--;}'
destroy=function(sync,'static void on_id_destroy(T& obj, u64 ipc_key,')
destroy=destroy.replace('u64 pshared = umax','u64 pshared = UINT64_MAX').replace('pshared == umax','pshared == UINT64_MAX')
assert old_destroy in extras
extras=extras.replace(old_destroy,'template<class T>'+destroy)
old_create=function(extras,'template<class T,class F>error_code lv2_obj::create(')
extras=extras.replace(old_create,'')
create=function(sync,'static error_code create(u32 pshared,')
create=create.replace('static error_code create(', 'template<class T,class F,class...Args>error_code lv2_obj::create(',1)
create=create.replace('bool key_not_zero = true','bool key_not_zero')
create=create.replace('AUDIT(!result);','assert(!result);')
extras+=create+'\n'+function(event_source,'shared_ptr<lv2_event_queue> lv2_event_queue::find(u64 ipc_key)')+'\n'
# Detect wrong source/payload, overflow, array/count, drain, connection, key
# truncation, publication leaks, duplicate-key acceptance and wrong queue type.
extras=extras.replace('type(static_cast<u8>(type))','type(static_cast<u8>(fault==356?0:type))')
extras=extras.replace('size(static_cast<u8>(size))','size(static_cast<u8>(fault==357?0:size))')
services=services.replace('port->queue = std::move(queue);','if(fault!=364){port->queue = std::move(queue);}')
services=services.replace('if (queue->type != SYS_PPU_QUEUE)\n\t{\n\t\treturn CELL_EINVAL;', 'if (queue->type != SYS_PPU_QUEUE)\n\t{\n\t\treturn fault==362?u32(CELL_OK):u32(CELL_EINVAL);')
checks=checks.replace('void restored(){','void restored(){for(u64 key:{0xfedcba9810500000ull,0xfedcba9810500001ull,0xfedcba9810500002ull})assert((!host_ipc<ipc_manager<lv2_event_queue,u64>>().check(key)));')
# A preexisting diagnostic key is rejected without deleting its IPC entry.
needle=' const u32 priorID=0x8d00ff01;'
guard='''
 auto& ipc=host_ipc<ipc_manager<lv2_event_queue,u64>>();
 const u64 occupiedKey=0xfedcba9810500000ull;
 auto occupied=std::make_shared<lv2_event_queue>(1,SYS_PPU_QUEUE,2,0,occupiedKey);
 ipc.add(occupiedKey,[&]{return occupied;});
 assert(IPC_SYMBOL()==-1);assert(ipc.get(occupiedKey)==occupied && ipc.check(occupiedKey));
 ipc.remove(occupiedKey);restored();
'''.replace('IPC_SYMBOL','IPC_FUNCTION')
guard=guard.replace('IPC_FUNCTION',IPC_SYMBOL)
assert needle in checks
checks=checks.replace(needle,guard+needle)
"""
# Literal symbol substitution within the generated Python, avoiding text eval.
inject=inject.replace("guard=guard.replace('IPC_FUNCTION',IPC_SYMBOL)","guard=guard.replace('IPC_FUNCTION',"+repr(ipc_symbol)+")")
source=source.replace('\nwith tempfile.TemporaryDirectory', '\n'+inject+'\nwith tempfile.TemporaryDirectory')
faults=[2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,26,27,36,37,38,39,40,41,60,173,174,175,176,177,179,180,22,212,213,214,216,224,341,343,344,345,346,347,349,354,355,356,357,364,365,366,368]
faults += [348,353] if ipc_profile.startswith('ppu_') else [362]
source=re.sub(r'const std::vector<int> faults\{[0-9,]+\};','const std::vector<int> faults{'+','.join(map(str,faults))+'};',source)
a=source.index(' std::puts("PASS: fifo P106-P113');b=source.index("''' +checks[b:]",a)
source=source[:a]+' std::puts("PASS: '+ipc_profile+' P106-P113 native IPC manager/shared create/destroy/find/10 executed APIs/11 table entries/binder/SC/guest/TLS;8runs/16workers/120SC each;full64 keys and payloads/duplicate publication/missing-key/connection/overflow/drain/partial PPU output or SPU rejection/dead-link/recreate/stale/occupied-key preservation;key/payload/lifecycle/ABI mutations detected;CPU/VM/ID/clock/scheduler are host interfaces;SPU waiter mailbox/iOS execution pending.");'+source[b:]
exec(compile(source,str(Path(__file__).resolve()),'exec'))

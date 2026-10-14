"""P98-P105 native event creation/lifetime profiles.
Usage: test_p98_pair.py PPUThread.cpp CoreBridge.cpp sys_ppu_thread_.cpp PROFILE
Native idm make/import, create hook, APIs and guest workload run on explicit
CPU/VM/allocator/storage/clock/scheduler interfaces. No SPU/IPC delivery.
"""
from pathlib import Path
from collections import Counter
import re,sys
creation_profile=sys.argv.pop() if len(sys.argv)==5 else 'queue_fifo_min'
profiles={'queue_fifo_min':(1,1,1,1,True),'queue_priority_max':(2,1,127,1,True),
 'queue_spu_fifo_min':(1,2,1,1,True),'queue_spu_priority_max':(2,2,127,1,True),
 'port_local_named':(1,1,2,1,True),'port_local_auto':(1,1,2,1,False),
 'port_ipc_named':(1,1,2,3,True),'port_ipc_auto':(1,1,2,3,False)}
assert creation_profile in profiles
params=profiles[creation_profile]
parent=Path(__file__).with_name('test_p94_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
creation_symbol='armsx3_core_test_event_object_'+creation_profile
def replace(a,b):
 global source
 assert a in source,a
 source=source.replace(a,b)
replace('P94-P97','P98-P105');replace(event_symbol,creation_symbol)
replace('static int armsx3_core_test_event_queue_batch(', 'static int armsx3_core_test_event_object_batch(')
replace("(138,'sys_event_port_send')]", "(138,'sys_event_port_send'),(140,'sys_event_port_connect_ipc')]")
replace('table[138]={BIND_FUNC(sys_event_port_send),"sys_event_port_send"};', 'table[138]={BIND_FUNC(sys_event_port_send),"sys_event_port_send"};\n table[140]={BIND_FUNC(sys_event_port_connect_ipc),"sys_event_port_connect_ipc"};')
replace('struct lv2_event_queue:lv2_obj{', 'struct lv2_event_queue:lv2_obj{static shared_ptr<lv2_event_queue>find(u64){throw std::runtime_error("real IPC lookup outside host workload");}')
replace('assert(sleep_count==6 && wake_count==6);assert(semaphore_timeout_observations==9);', 'assert(sleep_count==0 && wake_count==0);assert(semaphore_timeout_observations==3);')
a=source.index('assert(syscall_usage.stat[128]');b=source.index("\n''' +checks[b:]",a)
first=[128,128,128,136,137,131,133,140,137,136,135,134,136,129,129,128,136,137,129,130]
second=[134,134,137,136,138,131,131,136,135,137,138,131,136,138,137,137,135,135,131,133]
counts=Counter(first+second)
source=source[:a]+'assert('+ ' && '.join(f'syscall_usage.stat[{c}]=={n*3}' for c,n in sorted(counts.items()))+');'+source[b:]
# Creation-only faults; blocking delivery/queue timer faults are exercised by
# P94-P97 instead. Fields and type rejection are independent negative cases.
inject=r'''
extras=extras.replace('type(static_cast<u8>(type))','type(static_cast<u8>(fault==356?0:type))')
extras=extras.replace('size(static_cast<u8>(size))','size(static_cast<u8>(fault==357?0:size))')
extras=extras.replace(': type(type)',': type(fault==358?0:type)',1)
extras=extras.replace('name(name)','name(fault==359?name^1:name)',1)
extras=extras.replace('if(fault==216)object->exists=2;', 'if constexpr(std::is_same_v<T,lv2_event_port>){if(fault==360)object->is_busy=1;}if(fault==216)object->exists=2;')
services=services.replace('if (size <= 0 || size > 127)', 'if (fault!=361 && (size <= 0 || size > 127))')
services=services.replace('if (queue->type != SYS_PPU_QUEUE)\n\t{\n\t\treturn CELL_EINVAL;', 'if (queue->type != SYS_PPU_QUEUE)\n\t{\n\t\treturn fault==362?u32(CELL_OK):u32(CELL_EINVAL);')
services=services.replace('if (port->type != SYS_EVENT_PORT_LOCAL)\n\t{\n\t\treturn CELL_EINVAL;', 'if (port->type != SYS_EVENT_PORT_LOCAL)\n\t{\n\t\treturn fault==363?u32(CELL_OK):u32(CELL_EINVAL);')
'''
source=source.replace('\nwith tempfile.TemporaryDirectory', '\n'+inject+'\nwith tempfile.TemporaryDirectory')
faults=[2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,26,27,36,37,38,39,40,41,60,173,174,175,176,177,179,180,22,212,213,214,216,224,346,354,355,356,357,358,359,360,361]
if params[3]==1:faults.extend([345,347])
else:faults.append(363)
if params[1]==1:faults.append(348)
else:faults.append(362)
source=re.sub(r'const std::vector<int> faults\{[0-9,]+\};','const std::vector<int> faults{'+','.join(map(str,faults))+'};',source)
a=source.index(' std::puts("PASS: fifo P98-P105');b=source.index("''' +checks[b:]",a)
source=source[:a]+' std::puts("PASS: '+creation_profile+' P98-P105 native11APIs/idm-make-import/create-hook/constructors/binder/SC/guest/TLS/bounded;8runs/16workers/120SC each/queue-exists1-port-exists0/PPU-SPU-type/capacity1-127-invalid0-128/local-IPC-named-auto-port/empty-output-and-type-rejection/recreation-dead-link-stale/whole-context-cleanup;creation-field/hook/boundary/permission mutations detected;CPU/VM/allocator/storage/clock/scheduler are host models;actual IPC connections/SPU delivery/device pending.");'+source[b:]
exec(compile(source,str(Path(__file__).resolve()),'exec'))

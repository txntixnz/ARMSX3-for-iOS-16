"""Build108 independent IPC key/link/message/output oracle and Build107 freeze."""
from pathlib import Path
from collections import Counter,deque
import hashlib,re,plistlib
here=Path(__file__).resolve().parent
parent=(here/'test_p98_fixture.py').read_text()
exec(compile(parent[:parent.rindex('\napp=')],str(here/'test_p98_fixture.py'),'exec'))
marker=b'// Build108 batches real shared IPC event queue connections and buffered delivery.'
assert bridge.count(marker)==1
old,new=bridge.split(b'\n'+marker,1)
assert hashlib.sha1(b'blob '+str(len(old)).encode()+b'\0'+old).hexdigest()=='528d449d05cccb4a05c74a231e910f038817782a'
s=new.decode()
def array(name):return [x.strip() for x in re.search(r'const std::array<u32, 20> '+name+r'\{([^}]+)\}',s).group(1).split(',')]
first=list(map(int,array('firstCodes')));second=list(map(int,array('secondCodes')))
assert first==[128,128,140,136,138,138,131,138,129,140,128,140,131,137,140,135,137,140,129,140]
assert second==[134,140,140,140,138,131,133,131,138,137,140,138,133,138,140,133,135,138,131,129]
assert array('firstErrors')==['0','CELL_EEXIST','0','CELL_EINVAL','0','CELL_EBUSY','ppu?0u:CELL_EINVAL','0','0','CELL_ESRCH','0','CELL_EISCONN','ppu?0u:CELL_EINVAL','0','CELL_ESRCH','CELL_EISCONN','0','CELL_ESRCH','0','CELL_ESRCH']
assert array('secondErrors')==['0','CELL_ESRCH','CELL_EISCONN','CELL_EINVAL','0','ppu?0u:CELL_EINVAL','0','ppu?0u:CELL_EINVAL','CELL_ENOTCONN','CELL_ENOTCONN','0','0','0','CELL_ENOTCONN','0','0','0','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH']
profiles=[f'{q}_{p}_{n}' for q in ('ppu','spu') for p in ('fifo','priority') for n in ('named','auto')]
for profile in profiles:
 ppu=profile.startswith('ppu_');named=profile.endswith('_named');usage=Counter();handles=sent=drained=0
 registry={};keys=set();outputs=[]
 for tx in range(3):
  key=0xfedcba9810500000|tx;missing=key^0x100000000;keys.add(key)
  assert key>0xffffffff and missing>0xffffffff and key!=missing and key not in registry
  qid=0x8d000800+tx;pid=0x0e000800+tx;liveq=livep=False;link=None;events=deque()
  source=0xfedcba9876543210 if named else (1<<32)|pid
  assert source>0xffffffff
  def event(op,role):
   tag=(tx<<24)|(op<<8)|role
   return source,0xfedcba9800000000|tag,0x8123456700000000|tag,0xa987654300000000|tag
  def receive(limit):
   result=[]
   for _ in range(min(limit,len(events))):result.append(events.popleft())
   outputs.append(tuple(result))
  for op in range(20):
   usage.update((first[op],second[op]));firstrole=tx%2;other=1-firstrole
   if op==0:liveq=livep=True;registry[key]=qid;handles+=2
   elif op==1:assert key in registry and missing not in registry and link is None # EEXIST, ESRCH preserve outputs
   elif op==2:link=registry[key];assert link==qid # duplicate EISCONN retains pointer
   elif op==3:assert link==qid and liveq # local-connect and zero IPC key rejection
   elif op==4:events.extend((event(op,firstrole),event(op,other)));sent+=2
   elif op==5:
    assert len(events)==2 # overflowing send returns EBUSY and cannot change either message
    if ppu:receive(1)
   elif op==6:
    if ppu:receive(0) # untouched array, count0, then drain a nonempty queue
    drained+=len(events);events.clear()
   elif op==7:
    events.append(event(op,firstrole));sent+=1
    if ppu:receive(2)
   elif op==8:liveq=False;del registry[key];events.clear();assert link==qid # retired port send ENOTCONN
   elif op==9:assert key not in registry and link==qid # missing connect and disconnect retain dead pointer
   elif op==10:
    retired=qid;qid+=0x100;liveq=True;registry[key]=qid;handles+=1;assert link==retired and retired!=qid
    link=registry[key] # reconnect replaces retired reference with same-key new object
   elif op==11:assert link==qid;events.append(event(op,other));sent+=1 # duplicate connect cannot replace live reference
   elif op==12:
    if ppu:receive(2)
    drained+=len(events);events.clear()
   elif op==13:link=None;assert livep # disconnected send ENOTCONN
   elif op==14:assert missing not in registry;link=registry[key]
   elif op==15:assert link==qid and livep;drained+=len(events);events.clear() # connected port destroy EISCONN
   elif op==16:link=None;livep=False
   elif op==17:assert not livep and key in registry # stale connect/send preserve registry
   elif op==18:liveq=False;del registry[key];assert not livep
   else:assert not liveq and not livep and key not in registry and not events
   assert (key in registry)==liveq and missing not in registry and len(events)<=2
  assert not liveq and not livep and link is None and key not in registry
 assert len(keys)==3 and not registry and handles==9 and sent==12
 assert [len(x) for x in outputs]==([1,0,1,1]*3 if ppu else [])
 assert drained==(3 if ppu else 9)
 assert sum(usage.values())==120 and usage[140]==33 and usage[138]==24 and usage[128]==9
for token in ['using IPCMap = ipc_manager<lv2_event_queue, u64>',
 'g_fxo->is_init<IPCMap>()', 'diagnostic IPC key already present',
 'const u64 missingKey = ipcKey ^ 0x100000000ull', 'arg2 = ipcKey',
 'value.key == ipcKey', 'const auto published = lv2_event_queue::find(ipcKey)',
 'g_fxo->get<IPCMap>().check(ipcKey) == liveQueue', 'expectedEvents.push_back',
 'expectedEvents.pop_front()', 'expectedLong(', 'count * 32 + field * 8',
 'u64(process_getpid() + 0u) << 32', 'IPC connect/lookup/full64 messages',
 'shared IPC key leaked after joined workers', 'cleanup.join(); throw;',
 'program.slices != 180', 'program.totals != std::array<u32, 2>{60, 60}']:
 assert token in s,token
app=(here.parent/'core/loadtest/App.mm').read_text();stages=re.findall(r'\{(\d+), "[^"]+", "(armsx3_core_[^"]+)"\}',app)
assert [int(n) for n,_ in stages]==list(range(2,114)) and len({f for _,f in stages})==112
assert [f for _,f in stages[-8:]]==['armsx3_core_test_event_ipc_'+x for x in profiles]
info=plistlib.loads((here.parent/'core/loadtest/Info.plist.in').read_bytes())
assert info['CFBundleVersion']=='108' and info['MinimumOSVersion']=='16.0'
print('PASS: Build107 bridge frozen;8 independent IPC key/connect/delivery/EEXIST/overflow/partial-output/drain/SPU-rejection/key-reuse/stale lifecycles;120SC each;112 UI stages;Build108/iOS16;native device pending')

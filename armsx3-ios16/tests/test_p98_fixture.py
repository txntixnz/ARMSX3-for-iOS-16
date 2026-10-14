"""Build107 creation/lifecycle oracle and corrected-event prefix freeze."""
from pathlib import Path
from collections import Counter
import hashlib,re,plistlib
here=Path(__file__).resolve().parent
parent=(here/'test_p94_fixture.py').read_text()
exec(compile(parent[:parent.rindex('\napp=')],str(here/'test_p94_fixture.py'),'exec'))
marker=b'// Build107 batches native event object creation and lifecycle diagnostics.'
assert bridge.count(marker)==1
old,new=bridge.split(b'\n'+marker,1)
assert hashlib.sha1(b'blob '+str(len(old)).encode()+b'\0'+old).hexdigest()=='c1c54e0426a256204dea4bd77e3fddfdbad8d089'
s=marker.decode()+new.decode()
def array(name):return [x.strip() for x in re.search(r'const std::array<u32, 20> '+name+r'\{([^}]+)\}',s).group(1).split(',')]
first=list(map(int,array('firstCodes')));second=list(map(int,array('secondCodes')))
assert first==[128,128,128,136,137,131,133,140,137,136,135,134,136,129,129,128,136,137,129,130]
assert second==[134,134,137,136,138,131,131,136,135,137,138,131,136,138,137,137,135,135,131,133]
assert array('firstErrors')==['0','CELL_EINVAL','CELL_EINVAL','local?0u:CELL_EINVAL','local?0u:CELL_ENOTCONN','ppu?0u:CELL_EINVAL','0','CELL_EINVAL','local?0u:CELL_ENOTCONN','CELL_ESRCH','CELL_ESRCH','0','local?0u:CELL_EINVAL','0','CELL_ESRCH','0','local?0u:CELL_EINVAL','local?0u:CELL_ESRCH','0','CELL_ESRCH']
assert array('secondErrors')==['0','CELL_EINVAL','CELL_ENOTCONN','local?CELL_EISCONN:CELL_EINVAL','CELL_ENOTCONN','ppu?0u:CELL_EINVAL','ppu?0u:CELL_EINVAL','local?0u:CELL_EINVAL','0','CELL_ESRCH','CELL_ESRCH','ppu?0u:CELL_EINVAL','local?CELL_EISCONN:CELL_EINVAL','CELL_ENOTCONN','CELL_ENOTCONN','CELL_ENOTCONN','local?CELL_EISCONN:0u','local?0u:CELL_ESRCH','CELL_ESRCH','CELL_ESRCH']
profiles=[('queue_fifo_min',1,1,1,1,True),('queue_priority_max',2,1,127,1,True),
 ('queue_spu_fifo_min',1,2,1,1,True),('queue_spu_priority_max',2,2,127,1,True),
 ('port_local_named',1,1,2,1,True),('port_local_auto',1,1,2,1,False),
 ('port_ipc_named',1,1,2,3,True),('port_ipc_auto',1,1,2,3,False)]
for name,protocol,qtype,capacity,ptype,named in profiles:
 usage=Counter();handles=counts=0;local=ptype==1;ppu=qtype==1
 for tx in range(3):
  qid=0x8d000800+tx;pid=0x0e000800+tx;link=None;liveq=livep=False;existsq=existsp=0;events=[]
  for op in range(20):
   usage.update((first[op],second[op]))
   if op==0:assert not liveq and not livep;liveq=livep=True;existsq=1;existsp=0;handles+=2
   elif op in (1,2):assert liveq and livep and existsq==1 and existsp==0 # capacity0/128 and port-type2 preserve canaries
   elif op==3:
    if local:assert link is None;link=qid # duplicate EISCONN keeps reference
    else:assert link is None # both local connects reject IPC type
   elif op==4:
    if local:assert link==qid;link=None
    else:assert link is None
   elif op in (5,6):
    assert not events and liveq
    if ppu:counts+=2 if op==5 else 1 # empty array unchanged; exact BE32 count0
   elif op==7:
    assert livep # IPC key0 fails before lookup for either port type
    if local:link=qid
   elif op==8:
    if local:assert link==qid;link=None
    else:assert link is None
    livep=False
   elif op in (9,10):assert not livep and link is None # stale port APIs
   elif op==11:
    assert not livep;pid+=0x100;livep=True;existsp=0;handles+=1
    if ppu:counts+=1
   elif op==12:
    if local:link=qid # valid then duplicate connect
    else:assert link is None
   elif op==13:assert liveq;liveq=False;existsq=0 # linked port keeps a retired queue pointer
   elif op==14:assert not liveq and (link==qid if local else link is None)
   elif op==15:
    assert not liveq;retired=qid;qid+=0x100;liveq=True;existsq=1;handles+=1
    if local:assert link==retired and link!=qid
   elif op==16:
    if local:link=qid # replacing dead reference allowed; connected port destroy EISCONN
    else:assert link is None;livep=False
   elif op==17:
    if local:assert livep and link==qid;link=None;livep=False
    else:assert not livep and link is None
   elif op==18:assert liveq and not livep;liveq=False;existsq=0
   else:assert not liveq and not livep and link is None
   assert existsp==0 and existsq==int(liveq) and not events
  assert not liveq and not livep and link is None
 assert handles==12 and counts==(12 if ppu else 0)
 assert sum(usage.values())==120 and usage[128]==12 and usage[134]==9 and usage[140]==3
for token in ['static int armsx3_core_test_event_object_batch(u32 protocol, s32 queueType, s32 capacity, s32 portType, u64 portName)',
 'attribute.type = queueType', 'operation == 2 ? 128', 'operation == 1 ? 2 : u32(program.portType)',
 'value.type == program.queueType', 'value.size == program.capacity', 'value.type == program.portType',
 'portValid = value.exists == 0', 'queueValid = value.exists == 1', 'linkedQueueID == queueID && liveQueue',
 'job.observeQueue = false', 'const bool handoff = false', 'program.queueObserved.load() != 0',
 'program.expiryObserved.load() != 0', 'program.wakeObserved.load() != 0', 'program.slices != 180',
 'program.totals != std::array<u32, 2>{60, 60}', 'cleanup.join(); throw;', 'EVENTOBJ metadata failure:']:
 assert token in s,token
app=(here.parent/'core/loadtest/App.mm').read_text();stages=re.findall(r'\{(\d+), "[^"]+", "(armsx3_core_[^"]+)"\}',app)
assert [int(n) for n,_ in stages]==list(range(2,106)) and len({f for _,f in stages})==104
assert [f for _,f in stages[-8:]]==['armsx3_core_test_event_object_'+x[0] for x in profiles]
info=plistlib.loads((here.parent/'core/loadtest/Info.plist.in').read_bytes())
assert info['CFBundleVersion']=='107' and info['MinimumOSVersion']=='16.0'
print('PASS: corrected P94 prefix frozen;8 independent native creation/lifecycle profiles, queue-exists1/port-exists0/PPU-SPU/capacity1-127-invalid0-128/local-IPC-name/link/recreation/error/output invariants;120SC/12handles each;104 UI diagnostics;Build107/iOS16;device pending')

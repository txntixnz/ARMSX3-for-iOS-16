"""Build106 independent event queue/port/message/cancellation oracle."""
from pathlib import Path
from collections import Counter,deque
import hashlib,plistlib,re
here=Path(__file__).resolve().parent
parent=(here/'test_p90_fixture.py').read_text()
exec(compile(parent[:parent.rindex('\napp=')],str(here/'test_p90_fixture.py'),'exec'))
marker=b'// Build106 batches native event queue and local port diagnostics.'
assert bridge.count(marker)==1
old,new=bridge.split(b'\n'+marker,1)
assert hashlib.sha1(b'blob '+str(len(old)).encode()+b'\0'+old).hexdigest()=='792bb98f6b7f47ac46ece9a2e0d713e8b9453077'
s=marker.decode()+new.decode()
def array(name):
 return [x.strip() for x in re.search(r'const std::array<u32, 20> '+name+r'\{([^}]+)\}',s).group(1).split(',')]
first=array('firstCodes');second=array('secondCodes')
assert first==['128','131','136','135','138','130','130','131','cancel?128u:131u','cancel?136u:131u','138','131','138','cancel?138u:133u','128','137','129','138','130','135']
assert second==['134','134','136','137','136','129','cancel?129u:138u','138','138','138','131','133','138','cancel?133u:131u','129','135','133','131','136','129']
assert array('firstErrors')==['0','0','0','CELL_EISCONN','CELL_ENOTCONN','CELL_ETIMEDOUT','cancel?CELL_ECANCELED:0u','cancel?CELL_ESRCH:0u','0','0','cancel?0u:CELL_EBUSY','0','0','cancel?CELL_EBUSY:0u','CELL_EINVAL','0','0','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH']
assert array('secondErrors')==['0','CELL_EINVAL','CELL_EISCONN','0','0','CELL_EBUSY','0','cancel?CELL_ENOTCONN:0u','cancel?CELL_ENOTCONN:0u','0','0','0','0','0','CELL_EINVAL','0','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH']
def codes(items,cancel):
 return [int(re.fullmatch(r'cancel\?(\d+)u:(\d+)u',x).group(1 if cancel else 2)) if x.startswith('cancel') else int(x) for x in items]
for cancel,protocol in [(False,1),(False,2),(True,1),(True,2)]:
 queued=expired=woken=canceled=handles=0;usage=Counter()
 for tx in range(3):
  first_role=tx%2;second_role=1-first_role;qid=0x8d000800+tx;pid=0x0e000800+tx
  name=0 if tx==1 else 0xfedcba9876543210;source=name if name else (1<<32)|pid
  assert source>0xffffffff
  liveq=livep=False;link=None;events=deque();waiter=None;timer=None;dummy_written=False
  outputs=[]
  def event(op,role):
   tag=(tx<<24)|(op<<8)|role
   return source,0xfedcba9800000000|tag,0x8123456700000000|tag,0xa987654300000000|tag
  for op in range(20):
   usage.update((codes(first,cancel)[op],codes(second,cancel)[op]))
   if op==0:assert not liveq and not livep;liveq=livep=True;handles+=2
   elif op==1:assert not events and liveq and livep;outputs.append(()) # empty count0; invalid port type preserves handle
   elif op==2:assert link is None;link=qid # reconnect EISCONN preserves it
   elif op==3:assert link==qid and liveq;link=None # destroy connected EISCONN, then disconnect
   elif op==4:assert link is None;link=qid # disconnected send ENOTCONN, then reconnect
   elif op in (5,6):
    assert liveq and link==qid and not events and waiter is None and timer is None
    waiter=first_role;timer=100000 if op==5 else 1000000;queued+=1
    if op==5:assert liveq;expired+=1 # normal queued destroy EBUSY then timeout
    elif cancel:liveq=False;canceled+=1;woken+=1 # forced destroy changes no dummy/event payload
    else:
     delivered=event(op,second_role);assert all(v>0xffffffff for v in delivered);woken+=1
     assert not events # direct delivery returns r4-r7, bypasses buffered events
    waiter=None;timer=None
   elif op==7:
    if cancel:assert not liveq and link==qid # stale tryreceive + dead-link send preserve buffers
    else:outputs.append(());events.append(event(op,second_role))
   elif op==8:
    if cancel:assert not liveq;old=qid;qid+=0x100;liveq=True;handles+=1;assert link==old and qid!=old
    else:assert len(events)==1;outputs.append(());events.append(event(op,second_role)) # size0 leaves first event
   elif op==9:
    if cancel:assert link!=qid;link=qid;events.append(event(op,second_role))
    else:assert events[0]==event(7,second_role);outputs.append((events.popleft(),));events.append(event(op,second_role))
   elif op==10:
    if cancel:assert len(events)==1;events.append(event(op,first_role))
    assert len(events)==2 # ordinary full send EBUSY cannot replace messages
    expected=(event(9,second_role),event(10,first_role)) if cancel else (event(8,second_role),event(9,second_role))
    assert tuple(events)==expected;outputs.append(tuple(events));events.clear()
   elif op==11:assert not events;outputs.append(());events.clear()
   elif op==12:events.append(event(op,first_role));events.append(event(op,second_role))
   elif op==13:
    assert len(events)==2;events.clear() # cancel profile first full send EBUSY, peer drain
    if not cancel:outputs.append(())
   elif op==14:assert liveq and link==qid # invalid capacity0 and destroy mode2 keep object/outputs
   elif op==15:assert livep and link==qid;link=None;livep=False
   elif op==16:assert liveq and not events and not livep;liveq=False
   else:assert not liveq and not livep and link is None and not events
   assert waiter is None and timer is None and len(events)<=2 and not dummy_written
  assert not liveq and not livep and not events and link is None
  assert [len(x) for x in outputs]==([0,2,0] if cancel else [0,0,0,1,2,0,0])
 assert (queued,expired,woken,canceled,handles)==(6,3,3,3 if cancel else 0,9 if cancel else 6)
 assert sum(usage.values())==120 and usage[130]==9
for token in ['static int armsx3_core_test_event_queue_batch(u32 protocol, bool cancelReceive)',
 'sizeof(attribute) == 16', 'sizeof(sys_event_t) == 32', 'LD(6, 5, 24), LD(5, 5, 16)',
 'value.pq == job.waiter && !value.sq && value.events.empty()', 'std::array<be_t<u64>, 2> trailing',
 'u64(process_getpid() + 0u) << 32', 'expectedEvents.pop_front()', 'expectedEvents.clear()',
 'value.events.size() == expectedEvents.size()', 'value.queue->exists == (linkedQueueID == queueID && liveQueue ? 1u : 0u)',
 'portValid = value.exists == 0', 'queueValid = value.exists == 1', 'EVENTQ metadata failure:',
 'expected[4 + field] = delivered[field]', 'abi[2] = job.arguments[3]', 'job.waiter, &context, job.waiterTimeout)',
 'armsx3_ios_ppu_probe_mutex_timeout_finished(waiter, signaller) != 1', 'program.slices != 180',
 'program.totals != std::array<u32, 2>{60, 60}', 'program.queueObserved.load() != 6',
 'program.expiryObserved.load() != 3', 'program.wakeObserved.load() != 3', 'cleanup.join(); throw;']:
 assert token in s,token
assert s.index('for (u32 id : portIDs())')<s.index('for (u32 id : queueIDs())')
app=(here.parent/'core/loadtest/App.mm').read_text()
stages=re.findall(r'\{(\d+), "[^"]+", "(armsx3_core_[^"]+)"\}',app)
assert [int(n) for n,_ in stages]==list(range(2,98)) and len({f for _,f in stages})==96
assert [f for _,f in stages[-4:]]==['armsx3_core_test_event_queue_'+x for x in ('fifo','priority','cancel_fifo','cancel_priority')]
info=plistlib.loads((here.parent/'core/loadtest/Info.plist.in').read_bytes())
assert info['CFBundleVersion']=='106' and info['MinimumOSVersion']=='16.0'
print('PASS: frozen Build105 prefix; independent four event queue/port timeout-delivery-cancel-source-payload-order-count-drain-capacity lifecycles;120SC each;8new/96total UI diagnostics; Build106/iOS16; native pending')

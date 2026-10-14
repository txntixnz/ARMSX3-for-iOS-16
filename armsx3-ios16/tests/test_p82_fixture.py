"""Build103 independent native event-flag state/output/mode oracle."""
from pathlib import Path
import hashlib,plistlib,re,struct
here=Path(__file__).resolve().parent
parent=(here/'test_p80_fixture.py').read_text()
exec(compile(parent[:parent.rindex('\napp=')],str(here/'test_p80_fixture.py'),'exec'))
marker=b'// Build103 batches native event-flag AND, OR, CLEAR and CLEAR_ALL diagnostics.'
assert bridge.count(marker)==1
old,new=bridge.split(b'\n'+marker,1)
assert hashlib.sha1(b'blob '+str(len(old)).encode()+b'\0'+old).hexdigest()=='b488610de4861929718396e04c4b2c00f9d5d744'
s=marker.decode()+new.decode()
def array(name):
 return [x.strip() for x in re.search(r'const std::array<u32, 14> '+name+r'\{([^}]+)\}',s).group(1).split(',')]
first=list(map(int,array('firstCodes')));second=list(map(int,array('secondCodes')))
assert first==[82,139,86,86,118,85,85,139,87,118,132,83,85,82]
assert second==[82,86,87,86,139,139,87,86,86,86,139,139,132,87]
assert array('firstErrors')==['0','0','CELL_EINVAL','CELL_EBUSY','0','CELL_ETIMEDOUT','0','0','0','0','0','0','CELL_ESRCH','CELL_EFAULT']
assert array('secondErrors')==['CELL_EFAULT','CELL_EBUSY','0','0','0','0','0','0','0','CELL_EBUSY','CELL_EFAULT','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH']
base=(1<<63)|(1<<32);request=(1<<48)|(1<<7);high=1<<48
# Independent semantic model: clear consumes requested bits or all bits only
# on success; trywait errors store zero; timeout stores the current pattern.
def test_and_clear(pattern,mask,mode):
 ok=(pattern&mask)==mask if mode&0xf==1 else bool(pattern&mask)
 if not ok:return pattern,None
 return (0 if mode&0x20 else pattern&~mask if mode&0x10 else pattern),pattern
for mode in (1,2,0x11,0x22):
 wake_bits=high if mode&0xf==2 else request
 after=0 if mode&0x20 else base if mode&0x10 else base|wake_bits
 immediate=0 if mode&0x20 else base if mode&0x10 else base|request
 usage=dict.fromkeys([82,83,85,86,87,118,132,139],0)
 queued=expired=woken=out64=out32=created=destroyed=0
 for tx in range(3):
  pattern=None;queue=[];timer=None;waiter=tx%2
  for op in range(14):
   for code in (first[op],second[op]):usage[code]+=1
   if op==0:assert pattern is None;pattern=base;created+=1
   elif op==1:
    pattern,result=test_and_clear(pattern,request,mode);assert result is None;out64+=2
   elif op==2:pattern|=high;out64+=1 # invalid mode stores zero, then a partial set
   elif op==3:
    pattern,result=test_and_clear(pattern,request,1);assert result is None
    pattern,result=test_and_clear(pattern,request,2);assert result==base|high;out64+=2
   elif op==4:pattern&=((1<<64)-1)^high;assert pattern==base;out64+=1
   elif op in (5,6):
    _,result=test_and_clear(pattern,request,mode);assert result is None and not queue and timer is None
    queue.append(waiter);timer=100000 if op==5 else 1000000;queued+=1
    if op==5:assert pattern==base;expired+=1;out64+=2
    else:
     pattern|=wake_bits;pattern,result=test_and_clear(pattern,request,mode)
     assert result==base|wake_bits and pattern==after;woken+=1;out64+=1
    queue.remove(waiter);timer=None
   elif op==7:
    assert pattern==after;pattern,result=test_and_clear(pattern,0,1)
    assert result==after;out64+=2
   elif op==8:
    pattern|=base|request;pattern,result=test_and_clear(pattern,request,mode)
    assert result==base|request and pattern==immediate;out64+=1
   elif op==9:
    pattern=0;pattern,result=test_and_clear(pattern,0,2);assert result is None;out64+=1
   elif op==10:assert not queue;out32+=1 # zero cancel count; NULL get preserves canary
   elif op==11:assert pattern==0;pattern=None;destroyed+=1;out64+=1 # stale get writes zero
   elif op==12:assert pattern is None;out64+=1;out32+=1 # stale wait/cancel still initialize outputs
   else:assert pattern is None # NULL attr create + invalid handle set
   assert pattern==[base,base,base|high,base|high,base,base,after,after,immediate,0,0,None,None,None][op]
  assert not queue and timer is None
 assert (queued,expired,woken,out64,out32,created,destroyed)==(6,3,3,45,6,3,3)
 assert usage=={82:9,83:3,85:9,86:21,87:12,118:6,132:6,139:18} and sum(usage.values())==84
# Independent guest instruction encoding and new five-argument descriptor.
def d(op,rt,ra,disp):return op<<26|rt<<21|ra<<16|(disp&0xffff)
words=[d(32,11,5,4),d(32,3,5,0),d(58,4,5,8),d(58,6,5,24),d(58,7,5,32),d(58,5,5,16),0x44000002,d(36,3,9,0),d(32,12,13,-0x6ff4),d(14,12,12,1),d(36,12,13,-0x6ff4),d(36,12,9,4),0x60000000]
assert len(words)==13 and len(struct.pack('>13I',*words))==52
for token in ['const std::array<u32, 13> opcodes', 'LD(6, 5, 24), LD(7, 5, 32), LD(5, 5, 16)',
 'const std::array<be_t<u64>, 4> fields', 'budgets{6, 1, 6}', 'pcs{24, 28, 52}',
 'job.begin + 24', 'abi[3] = job.arguments[4]; abi[4] = job.arguments[5];',
 'job.waiterFinished->load(std::memory_order_acquire)', 'job.nativeFinished.store(true, std::memory_order_release)',
 'attribute.type = SYS_SYNC_WAITER_SINGLE', 'flag.pattern == expectedValue && !flag.sq',
 'program.totals != std::array<u32, 2>{42, 42}', 'program.slices != 126',
 'program.queueObserved.load() != 6', 'program.expiryObserved.load() != 3', 'program.wakeObserved.load() != 3']:
 assert token in s,token
for suffix,expr in [('and','SYS_EVENT_FLAG_WAIT_AND'),('or','SYS_EVENT_FLAG_WAIT_OR'),('clear','SYS_EVENT_FLAG_WAIT_AND | SYS_EVENT_FLAG_WAIT_CLEAR'),('clear_all','SYS_EVENT_FLAG_WAIT_OR | SYS_EVENT_FLAG_WAIT_CLEAR_ALL')]:
 assert 'armsx3_core_test_event_flag_'+suffix+'()' in s
 assert 'armsx3_core_test_event_flag_batch('+expr+')' in s
app=(here.parent/'core/loadtest/App.mm').read_text()
stages=re.findall(r'\{(\d+), "[^"]+", "(armsx3_core_[^"]+)"\}',app)
assert [int(n) for n,_ in stages]==list(range(2,86)) and len({f for _,f in stages})==84
assert [f for _,f in stages[-4:]]==['armsx3_core_test_event_flag_'+x for x in ('and','or','clear','clear_all')]
info=plistlib.loads((here.parent/'core/loadtest/Info.plist.in').read_bytes())
assert info['CFBundleVersion']=='103' and info['MinimumOSVersion']=='16.0'
print('PASS: Build103 frozen Build102 prefix; four independent event-flag mode/pattern/queue/output lifecycles,84SC/45BE64 results/6BE32 cancels each,52byte guest program/five-argument descriptors/84 UI stages/iOS16 metadata; native pending')

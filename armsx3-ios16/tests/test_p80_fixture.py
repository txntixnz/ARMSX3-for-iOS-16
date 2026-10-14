"""Build102 independent semaphore batch oracle and frozen Build101 prefix."""
from pathlib import Path
import hashlib,plistlib,re
here=Path(__file__).resolve().parent
parent=(here/'test_p79_fixture.py').read_text()
exec(compile(parent[:parent.rindex('\napp=')],str(here/'test_p79_fixture.py'),'exec'))
marker=b'// Build102 batches FIFO and priority semaphore surplus-wake diagnostics.'
assert bridge.count(marker)==1
old,new=bridge.split(b'\n'+marker,1)
assert hashlib.sha1(b'blob '+str(len(old)).encode()+b'\0'+old).hexdigest()=='52e84736ca373db4718e99fd6820f7c2b9f115a9'
s=marker.decode()+new.decode()
def array(name):
 return [x.strip() for x in re.search(r'const std::array<u32, 14> '+name+r'\{([^}]+)\}',s).group(1).split(',')]
first=list(map(int,array('firstCodes')));second=list(map(int,array('secondCodes')))
assert first==[90,92,92,92,94,94,94,92,93,94,114,91,91,90]
assert second==[90,93,114,94,114,94,114,93,114,94,92,114,94,114]
assert array('firstErrors')==['0','0','CELL_ETIMEDOUT','0','0','CELL_EBUSY','CELL_EBUSY','0','0','CELL_EINVAL','0','0','CELL_ESRCH','CELL_EINVAL']
assert array('secondErrors')==['CELL_EFAULT','0','0','0','0','CELL_EINVAL','0','0','CELL_EFAULT','0','0','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH']
for protocol in (1,2):
 usage=dict.fromkeys([90,91,92,93,94,114],0)
 queued=expired=woken=writes=0
 for tx in range(3):
  permits=None;posts=0;queue=[];timer=None;waiter=tx%2
  for op in range(14):
   for code in (first[op],second[op]):usage[code]+=1
   if op==0:assert permits is None;permits=2
   elif op==1:assert permits==2;permits-=2
   elif op in (2,3):
    assert permits==0 and not queue and timer is None
    permits-=1;queue.append(waiter);timer=100000 if op==2 else 1000000;queued+=1
    assert permits==-1 and queue==[waiter]
    if op==2:permits+=1;expired+=1;writes+=1
    else:permits+=2;posts+=1;woken+=1
    queue.remove(waiter);timer=None
    assert permits==(0 if op==2 else 1) and not queue and timer is None
   elif op==4:assert permits==1;permits+=2;posts+=1;writes+=1
   elif op in (5,6):
    assert permits==3
    count=1 if op==5 else (1<<31)-1
    assert permits+count>3;posts+=1 # native overflow attempts record metadata
    if op==6:writes+=1
   elif op==7:assert permits==3;permits-=2
   elif op==8:assert permits==1;permits-=1
   elif op==9:
    assert permits==0 and -(1<<31)<0 # rejected INT_MIN changes neither value nor post count
    permits+=1;posts+=1
   elif op==10:assert permits==1;writes+=1;permits-=1
   elif op==11:assert permits==0;permits=None
   else:assert permits is None
   assert permits==[2,0,0,1,3,3,3,1,0,1,0,None,None,None][op]
   assert posts==[0,0,0,1,2,3,4,4,4,5,5,5,5,5][op]
  assert not queue and timer is None
 assert (queued,expired,woken,writes)==(6,3,3,12)
 assert usage=={90:9,91:6,92:15,93:9,94:24,114:21} and sum(usage.values())==84
for token in ['static int armsx3_core_test_semaphore_surplus_batch(u32 protocol)',
 'attribute.protocol = protocol;', 'program.protocol = protocol;', 'sema.protocol == program.protocol',
 'armsx3_core_test_semaphore_surplus_batch(SYS_SYNC_FIFO)', 'armsx3_core_test_semaphore_surplus_batch(SYS_SYNC_PRIORITY)',
 'first && operation == 6 ? 0x7fffffffull', 'first && operation == 9 ? 0x80000000ull', '!first && operation == 3 ? 2ull',
 'program.slices != 126', 'program.totals != std::array<u32, 2>{42, 42}',
 'armsx3_ios_ppu_probe_mutex_timeout_finished(waiter, poster) != 1',
 'program.queueObserved.load() != 6', 'program.expiryObserved.load() != 3', 'program.wakeObserved.load() != 3',
 'cleanup.join(); throw;', '(i ? 0x20000000u : 0u)']:
 assert token in s,token
app=(here.parent/'core/loadtest/App.mm').read_text()
stages=re.findall(r'\{(\d+), "[^"]+", "(armsx3_core_[^"]+)"\}',app)
assert [int(n) for n,_ in stages]==list(range(2,82)) and len({f for _,f in stages})==80
assert stages[-2][1]=='armsx3_core_test_semaphore_fifo_surplus' and stages[-1][1]=='armsx3_core_test_semaphore_priority_surplus'
info=plistlib.loads((here.parent/'core/loadtest/Info.plist.in').read_bytes())
assert info['CFBundleVersion']=='102' and info['MinimumOSVersion']=='16.0'
print('PASS: P80/P81 frozen Build101, independent FIFO/priority surplus permits/count extremes/twelve value outputs/84SC each;80 UI stages and Build102/iOS16; native phone pending')

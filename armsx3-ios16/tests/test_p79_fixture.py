"""Build101/P79 oracle; full Build100 diagnostic prefix remains frozen."""
from pathlib import Path
import hashlib,plistlib,re
here=Path(__file__).resolve().parent
parent=(here/'test_p78_fixture.py').read_text()
exec(compile(parent[:parent.index('app=(here.parent')],str(here/'test_p78_fixture.py'),'exec'))
marker=b'// Build101 adds semaphore timeout followed by requeue and posted wake.'
assert bridge.count(marker)==1
old,new=bridge.split(b'\n'+marker,1)
assert hashlib.sha1(b'blob '+str(len(old)).encode()+b'\0'+old).hexdigest()=='350d5213610a2ba711dd2232b25194db0a34e5f5'
s=marker.decode()+new.decode()
def array(name):
 return [x.strip() for x in re.search(r'const std::array<u32, 13> '+name+r'\{([^}]+)\}',s).group(1).split(',')]
first=list(map(int,array('firstCodes')));second=list(map(int,array('secondCodes')))
assert first==[90,92,92,92,94,94,92,93,94,114,91,91,90]
assert second==[90,93,114,94,114,94,93,114,94,92,114,94,114]
assert array('firstErrors')==['0','0','CELL_ETIMEDOUT','0','0','CELL_EBUSY','0','0','CELL_EINVAL','0','0','CELL_ESRCH','CELL_EINVAL']
assert array('secondErrors')==['CELL_EFAULT','0','0','0','0','CELL_EINVAL','0','CELL_EFAULT','0','0','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH']
usage=dict.fromkeys([90,91,92,93,94,114],0)
queued=expired=woken=writes=0
for tx in range(3):
 permits=None;posts=0;queue=[];timer=None;waiter=tx%2
 for op in range(13):
  for code in (first[op],second[op]):usage[code]+=1
  if op==0:assert permits is None;permits=2
  elif op==1:assert permits==2;permits-=2
  elif op in (2,3):
   assert permits==0 and not queue and timer is None
   permits-=1;queue.append(waiter);timer=100000 if op==2 else 1000000;queued+=1
   assert permits==-1 and queue==[waiter]
   if op==2:expired+=1;writes+=1
   else:posts+=1;woken+=1
   queue.remove(waiter);permits+=1;timer=None
   assert permits==0 and not queue and timer is None
  elif op==4:assert permits==0;permits+=3;posts+=1;writes+=1
  elif op==5:assert permits==3;posts+=1
  elif op==6:assert permits==3;permits-=2
  elif op==7:assert permits==1;permits-=1
  elif op==8:assert permits==0;permits+=1;posts+=1
  elif op==9:assert permits==1;writes+=1;permits-=1
  elif op==10:assert permits==0;permits=None
  else:assert permits is None
  assert permits==[2,0,0,0,3,3,1,0,1,0,None,None,None][op]
  assert posts==[0,0,0,1,2,3,3,3,4,4,4,4,4][op]
 assert not queue and timer is None
assert (queued,expired,woken,writes)==(6,3,3,9)
assert usage=={90:9,91:6,92:15,93:9,94:21,114:18} and sum(usage.values())==78
for token in ['job.waiter, &context, job.waiterTimeout)', 'if (job.expectExpiry)',
 'first && operation == 2 ? 100000ull : first && operation == 3 ? 1000000ull',
 'armsx3_ios_ppu_probe_mutex_timeout_finished(waiter, poster) != 1',
 'program.queueObserved.load() != 6', 'program.expiryObserved.load() != 3', 'program.wakeObserved.load() != 3',
 'program.slices != 117','program.totals != std::array<u32, 2>{39, 39}',
 'armsx3_ios_ppu_probe_mutex_scheduler_and_call(owner, peer.get(), invokeScope, &scopeWork)',
 'cleanup.join(); throw;', '(i ? 0x20000000u : 0u)']:
 assert token in s,token
assert s.count('P79 PASS: transaction=')==1
app=(here.parent/'core/loadtest/App.mm').read_text()
stages=re.findall(r'\{(\d+), "[^"]+", "(armsx3_core_[^"]+)"\}',app)
assert [int(n) for n,_ in stages]==list(range(2,80))
assert len({f for _,f in stages})==78 and stages[-1][1]=='armsx3_core_test_semaphore_timeout_then_wake'
info=plistlib.loads((here.parent/'core/loadtest/Info.plist.in').read_bytes())
assert info['CFBundleVersion']=='101' and info['MinimumOSVersion']=='16.0'
print('PASS: P79 Build100 freeze, three timeout/requeue/wake lifecycles, six queue observations, nine value writes,78SC,78 UI stages and Build101/iOS16; native phone pending')

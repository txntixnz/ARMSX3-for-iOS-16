"""Build100 / P78 semaphore expiry and reuse oracle; Build99 frozen in full."""
from pathlib import Path
import hashlib,plistlib,re,runpy
here=Path(__file__).resolve().parent
runpy.run_path(str(here/'test_p77_fixture.py'))
bridge=(here.parent/'core/loadtest/CoreBridge.cpp').read_bytes()
marker=b'// Build100 adds native semaphore timeout expiry and permit recovery.'
assert bridge.count(marker)==1
old,new=bridge.split(b'\n'+marker,1)
assert hashlib.sha1(b'blob '+str(len(old)).encode()+b'\0'+old).hexdigest()=='941ffaffe9fc88a0b161b6ae12d5ce9ab6d9dd49'
s=marker.decode()+new.decode()
def array(name):
 return [x.strip() for x in re.search(r'const std::array<u32, 12> '+name+r'\{([^}]+)\}',s).group(1).split(',')]
first=list(map(int,array('firstCodes')));second=list(map(int,array('secondCodes')))
assert first==[90,92,92,94,94,92,93,94,114,91,91,90]
assert second==[90,93,114,114,94,93,114,94,92,114,94,114]
assert array('firstErrors')==['0','0','CELL_ETIMEDOUT','0','CELL_EBUSY','0','0','CELL_EINVAL','0','0','CELL_ESRCH','CELL_EINVAL']
assert array('secondErrors')==['CELL_EFAULT','0','0','0','CELL_EINVAL','0','CELL_EFAULT','0','0','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH']
usage=dict.fromkeys([90,91,92,93,94,114],0)
expiries=writes=0
for tx in range(3):
 permits=None;posts=0;queue=[];timer=None
 for op in range(12):
  for code in (first[op],second[op]):usage[code]+=1
  if op==0:assert permits is None;permits=2
  elif op==1:assert permits==2;permits-=2
  elif op==2:
   assert permits==0 and not queue and timer is None
   permits-=1;queue.append(tx%2);timer=100000
   assert permits==-1 and queue==[tx%2] and posts==0
   # Native timed waiter unqueues itself and restores the negative permit.
   queue.remove(tx%2);permits+=1;timer=None;expiries+=1
   assert permits==0 and not queue and timer is None and posts==0
   writes+=1 # peer native get_value must write BE32 zero
  elif op==3:assert permits==0;permits+=3;posts+=1;writes+=1
  elif op==4:assert permits==3;posts+=1 # overflow attempt records metadata, returns EBUSY
  elif op==5:assert permits==3;permits-=2
  elif op==6:assert permits==1;permits-=1 # NULL get_value preserves output canary
  elif op==7:assert permits==0;permits+=1;posts+=1
  elif op==8:assert permits==1;writes+=1;permits-=1
  elif op==9:assert permits==0;permits=None
  else:assert permits is None
  assert permits==[2,0,0,3,3,1,0,1,0,None,None,None][op]
  assert posts==[0,0,0,1,2,2,2,3,3,3,3,3][op]
 assert not queue and timer is None
assert (expiries,writes)==(3,9)
assert usage=={90:9,91:6,92:12,93:9,94:18,114:18} and sum(usage.values())==72
for token in ['armsx3_ios_ppu_probe_mutex_scheduler_and_call(owner, peer.get(), invokeScope, &scopeWork)',
 'armsx3_ios_ppu_probe_mutex_timeout_state(job.waiter, &context, 100000) == 1',
 'armsx3_ios_ppu_probe_mutex_timeout_finished(job.waiter, &context) == 1',
 'value.val == 0 && !value.sq && value.exists == 1 && value.dbg_post_count == 0',
 'program.expiryObserved.load(std::memory_order_acquire) != transaction + 1',
 'cleanup.join(); throw;', 'dataSnapshot->data()', 'tlsSnapshot->data()',
 'first && operation == 2 ? 100000ull', 'job.waiter->state += cpu_flag::exit']:
 assert token in s,token
assert s.count('P78 PASS: transaction=')==1
app=(here.parent/'core/loadtest/App.mm').read_text()
stages=re.findall(r'\{(\d+), "[^"]+", "(armsx3_core_[^"]+)"\}',app)
assert [int(n) for n,_ in stages]==list(range(2,79))
assert len({f for _,f in stages})==77
assert stages[-1][1]=='armsx3_core_test_semaphore_timeout_recovery'
info=plistlib.loads((here.parent/'core/loadtest/Info.plist.in').read_bytes())
assert info['CFBundleVersion']=='100' and info['MinimumOSVersion']=='16.0'
print('PASS: P78 full Build99 freeze, three modeled negative-permit expiries/queue removal/reuse lifecycles, nine value writes,72SC, full64 ABI, clean deadline observation,77 unique stages and Build100/iOS16 metadata; native phone test pending')

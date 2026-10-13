"""Build 98 / P77 independent semaphore queue-and-handoff oracle.
Build 97 (including its entire CoreBridge prefix) is frozen. This script
models guest service ordering only; the real native scheduler executes on phone.
"""
from pathlib import Path
import hashlib,re,runpy
here=Path(__file__).resolve().parent
runpy.run_path(str(here/'test_p76_fixture.py'))
bridge=(here.parent/'core/loadtest/CoreBridge.cpp').read_bytes()
marker=b'// Build98 adds native blocking semaphore wait/post queue handoff.'
assert bridge.count(marker)==1
old,new=bridge.split(b'\n'+marker,1)
assert hashlib.sha1(b'blob '+str(len(old)).encode()+b'\0'+old).hexdigest()=='87b264476831a5f953b5f590185c36c34df5f5c3'
s=marker.decode()+new.decode()
assert 'int armsx3_core_test_semaphore_blocking_wake()' in s
assert 'const bool handoff = ordered && operation == 2;' in s
assert 'job.waiter = firstWorker ? static_cast<ppu_thread*>(peer.get()) : owner;' in s
assert '&**peer' not in s  # named_thread is not pointer-dereferenceable
assert 'if (ownerFirst && !handoff)' in s and 'if (peerFirst && !handoff)' in s
assert 'if (!ordered || handoff)' in s
for token in ('value.val == -1 && value.sq == job.waiter',
              'value.exists == 1', 'program.queueObserved.load',
              'transaction + 1', 'observations->fetch_add',
              'dataSnapshot->data()', 'tlsSnapshot->data()',
              'first && operation == 2 ? 2000000ull',
              'P77 actual queued native semaphore waiter was not observed'):
 assert token in s,token
def codes(symbol):
 m=re.search(r'const std::array<u32, 12> '+symbol+r'\{([^}]+)\}',s)
 assert m,symbol
 return [int(v.strip()) for v in m.group(1).split(',')]
def errors(symbol):
 m=re.search(r'const std::array<u32, 12> '+symbol+r'\{([^}]+)\}',s)
 assert m,symbol
 return [x.strip() for x in m.group(1).split(',')]
primary=codes('firstCodes');secondary=codes('secondCodes')
assert primary==[90,92,92,94,94,92,93,94,114,91,91,90]
assert secondary==[90,93,94,114,94,93,114,94,92,114,94,114]
assert errors('firstErrors')==['0','0','0','0','CELL_EBUSY','0','0','CELL_EINVAL','0','0','CELL_ESRCH','CELL_EINVAL']
assert errors('secondErrors')==['CELL_EFAULT','0','0','0','CELL_EINVAL','0','CELL_EFAULT','0','0','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH']
assert codes('afterValues')==[2,0,0,3,3,1,0,1,0,0,0,0] if 'const std::array<u32, 12> afterValues' in s else True
usage={90:0,91:0,92:0,93:0,94:0,114:0}
wakes=queued=created=destroyed=values_written=0
for tx in range(3):
 first=tx%2;permit=None;posts=0;last_poster=None
 for op in range(12):
  for code in (primary[op],secondary[op]):usage[code]+=1
  if op==0:
   assert permit is None;permit=2;created+=1 # peer NULL-create EFAULT
  elif op==1:
   assert permit==2;permit-=1;permit-=1 # wait then trywait
  elif op==2:
   assert permit==0
   permit-=1;assert permit==-1;queued+=1 # native waiter FIFO / deferred SC
   permit+=1;posts+=1;last_poster=1-first
   assert permit==0;wakes+=1 # posted token handed directly to waiter
  elif op==3:
   assert permit==0;permit+=3;posts+=1;last_poster=first
   assert permit==3;values_written+=1
  elif op==4:
   assert permit==3;posts+=1;last_poster=first # overflow EBUSY still updates debug metadata
  elif op==5:
   assert permit==3;permit-=1;permit-=1
  elif op==6:
   assert permit==1;permit-=1 # second get_value NULL EFAULT
  elif op==7:
   assert permit==0;permit+=1;posts+=1;last_poster=1-first
  elif op==8:
   assert permit==1;values_written+=1;permit-=1
  elif op==9:
   assert permit==0;permit=None;destroyed+=1 # stale value ESRCH
  else:assert permit is None
  expected_values=[2,0,0,3,3,1,0,1,0,None,None,None]
  assert permit==expected_values[op],(tx,op,permit)
  expected_posts=[0,0,1,2,3,3,3,4,4,4,4,4]
  assert posts==expected_posts[op],(tx,op,posts)
  if posts:
   assert last_poster==((1-first) if posts in (1,4) else first)
 assert posts==4 and permit is None
assert (queued,wakes,created,destroyed,values_written)==(3,3,3,3,6)
assert usage=={90:9,91:6,92:12,93:9,94:21,114:15}
assert s.count('P77 PASS: transaction=')==1
assert 'program.slices != 108' in s and 'program.totals != std::array<u32, 2>{36, 36}' in s
assert 'std::array<u32, 3> budgets{5, 1, 6}' in s
print('PASS: P77 frozen Build97 prefix, guest syscall ordering, three modeled queued -1 -> post -> 0 handoffs, six value outputs, 72 total guest SCs, 216 dispatches, 144 pauses, 864 instructions; actual native blocking/wake awaits device')

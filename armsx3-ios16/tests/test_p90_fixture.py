"""Build105 independent reader count/writer/queue/timeout lifecycle oracle."""
from pathlib import Path
from collections import Counter
import hashlib,plistlib,re
here=Path(__file__).resolve().parent
parent=(here/'test_p86_fixture.py').read_text()
exec(compile(parent[:parent.rindex('\napp=')],str(here/'test_p86_fixture.py'),'exec'))
marker=b'// Build105 batches native reader/writer lock contention diagnostics.'
assert bridge.count(marker)==1
old,new=bridge.split(b'\n'+marker,1)
assert hashlib.sha1(b'blob '+str(len(old)).encode()+b'\0'+old).hexdigest()=='a7c6927d014824c1b7c368afd4610491525b7213'
s=marker.decode()+new.decode()
def array(name):
 return [x.strip() for x in re.search(r'const std::array<u32, 20> '+name+r'\{([^}]+)\}',s).group(1).split(',')]
first=array('firstCodes');second=array('secondCodes')
assert first==['120','120','123','126','124','124','127','123','123','124','write ? 125u : 122u','write ? 125u : 122u','126','write ? 127u : 124u','125','127','121','125','121','122']
assert second==['120','124','122','148','121','126','126','125','127','write ? 123u : 126u','121','write ? 124u : 127u','write ? 127u : 123u','124','126','124','123','127','124','148']
assert array('firstErrors')==['0','CELL_EINVAL','0','CELL_EBUSY','0','0','CELL_EPERM','CELL_EBUSY','CELL_EBUSY','CELL_EPERM','CELL_ETIMEDOUT','0','write ? CELL_EDEADLK : CELL_EBUSY','0','0','0','0','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH']
assert array('secondErrors')==['CELL_EFAULT','CELL_EPERM','0','CELL_EBUSY','CELL_EBUSY','0','CELL_EDEADLK','CELL_EDEADLK','0','0','CELL_EBUSY','0','write ? CELL_EPERM : 0u','write ? CELL_EPERM : 0u','CELL_EBUSY','CELL_EPERM','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH']
def codes(items,write):
 return [int(re.sub(r'u$','',re.fullmatch(r'write \? (\d+u) : (\d+u)',x).group(1 if write else 2))) if x.startswith('write') else int(x) for x in items]
for write,protocol in [(False,1),(False,2),(True,1),(True,2)]:
 usage=Counter();queued=expired=woken=handles=created=destroyed=0
 for tx in range(3):
  a=0x1000000+tx%2;b=0x1000000+1-tx%2
  live=False;readers=0;writer=None;waitbit=False;rq=[];wq=[];timer=None
  for op in range(20):
   usage.update((codes(first,write)[op],codes(second,write)[op]))
   if op==0:assert not live;live=True;handles+=1;created+=1
   elif op==1:assert live and not readers and writer is None # invalid attr preserves output and namespace
   elif op==2:assert not readers and writer is None;readers=2 # two different guest workers
   elif op==3:assert readers==2 and writer is None # both try-writer APIs must return busy
   elif op==4:assert readers==2;readers-=1 # destroy must remain busy
   elif op==5:assert readers==1;readers-=1;writer=b # native read release counts readers, not thread IDs
   elif op in (6,7):assert writer==b and not readers # foreign release and recursive write refuse
   elif op==8:assert writer==b;writer=None
   elif op==9:
    assert not readers and writer is None
    if write:readers=1
    else:writer=b
   elif op in (10,11):
    assert live and not rq and not wq and timer is None
    if write:assert readers==1 and writer is None;wq.append(a)
    else:assert not readers and writer==b;rq.append(a)
    waitbit=True;timer=100000 if op==10 else 1000000;queued+=1
    assert (rq,wq)==([], [a]) if write else (rq,wq)==([a], [])
    if op==10:
     assert live # destroy EBUSY cannot consume or replace object
     expired+=1
     if write:wq.remove(a);waitbit=False
     else:rq.remove(a) # native rlock timeout leaves low wait bit
    else:
     woken+=1;waitbit=False
     if write:readers-=1;wq.remove(a);writer=a
     else:writer=None;rq.remove(a);readers=1
    timer=None
   elif op==12:
    if write:assert writer==a and not readers # own write is deadlock; peer release permission
    else:assert readers==1 and writer is None;readers+=1
   elif op==13:
    if write:assert writer==a;writer=None # peer read unlock remains permission error
    else:assert readers==2;readers-=2
   elif op==14:assert not readers and writer is None;writer=a
   elif op==15:assert writer==a;writer=None
   elif op==16:assert live and not readers and writer is None;live=False;destroyed+=1
   else:assert not live and writer is None and not readers
   encoded=(-2*readers if readers else writer*2 if writer else 0)|int(waitbit)
   expected=[0,0,-4,-4,-2,b*2,b*2,b*2,0,-2 if write else b*2,-2 if write else b*2|1,a*2 if write else -2,a*2 if write else -4,0,a*2,0,0,0,0,0][op]
   assert encoded==expected and not rq and not wq and timer is None
  assert not live and not readers and writer is None and not waitbit
 assert (queued,expired,woken,handles,created,destroyed)==(6,3,3,3,3,3)
 assert sum(usage.values())==120 and usage[120]==9 and usage[148]==6
for token in ['static int armsx3_core_test_rwlock_batch(u32 protocol, bool writerWait)',
 'sizeof(attribute) == 32', 'invalidAttribute.protocol = 0', 'value.owner == held',
 'value.wq == job.waiter && !value.rq', 'value.rq == job.waiter && !value.wq',
 'job.waiter, &context, job.waiterTimeout)', 'armsx3_ios_ppu_probe_mutex_timeout_finished(waiter, signaller) != 1',
 'value.owner == expectedOwner && !value.rq && !value.wq', 'for (u32 id : rwlockIDs())',
 'program.slices != 180', 'program.totals != std::array<u32, 2>{60, 60}',
 'program.queueObserved.load() != 6', 'program.expiryObserved.load() != 3', 'program.wakeObserved.load() != 3',
 'budgets{5, 1, 6}', 'pcs{20, 24, 48}', '0xfedcba9876543210ull', 'cleanup.join(); throw;']:
 assert token in s,token
app=(here.parent/'core/loadtest/App.mm').read_text()
stages=re.findall(r'\{(\d+), "[^"]+", "(armsx3_core_[^"]+)"\}',app)
assert [int(n) for n,_ in stages]==list(range(2,94)) and len({f for _,f in stages})==92
assert [f for _,f in stages[-4:]]==['armsx3_core_test_rwlock_'+x for x in ('reader_fifo','reader_priority','writer_fifo','writer_priority')]
info=plistlib.loads((here.parent/'core/loadtest/Info.plist.in').read_bytes())
assert info['CFBundleVersion']=='105' and info['MinimumOSVersion']=='16.0'
print('PASS: frozen Build104 prefix; four independent reader/writer count/owner/queue/timeout/waitbit/wake/error lifecycles;120SC/three handles/60TLS each,92 UI stages and Build105/iOS16; native pending')

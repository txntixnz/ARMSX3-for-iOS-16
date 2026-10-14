"""Build104 independent condition-variable/mutex link/owner/count oracle."""
from pathlib import Path
import hashlib,plistlib,re
from collections import Counter
here=Path(__file__).resolve().parent
parent=(here/'test_p82_fixture.py').read_text()
exec(compile(parent[:parent.rindex('\napp=')],str(here/'test_p82_fixture.py'),'exec'))
marker=b'// Build104 batches native condition-variable mutex release/reacquire diagnostics.'
assert bridge.count(marker)==1
old,new=bridge.split(b'\n'+marker,1)
assert hashlib.sha1(b'blob '+str(len(old)).encode()+b'\0'+old).hexdigest()=='3233e091778b1a809e9e0b65aeb394caea9331f7'
s=marker.decode()+new.decode()
def array(name):
 return [x.strip() for x in re.search(r'const std::array<u32, 18> '+name+r'\{([^}]+)\}',s).group(1).split(',')]
first=list(map(int,array('firstCodes')))
assert first==[100,105,101,103,103,107,107,104,104,107,109,103,103,103,104,101,106,105]
second=array('secondCodes')
assert second==['100','105','107','104','108','106','program.broadcast ? 109u : 108u','103','103','103','110','104','104','106','108','107','104','109']
assert array('firstErrors')==['0','0','CELL_EPERM','0','rec ? 0u : CELL_EDEADLK','CELL_ETIMEDOUT','0','0','rec ? 0u : CELL_EPERM','CELL_EPERM','0','CELL_EBUSY','rec ? CELL_EBUSY : 0u','rec ? 0u : CELL_EDEADLK','0','0','CELL_ESRCH','CELL_ESRCH']
assert array('secondErrors')==['CELL_EFAULT','CELL_ESRCH','CELL_EPERM','CELL_EPERM','0','CELL_EBUSY','0','rec ? CELL_EBUSY : 0u','rec ? 0u : CELL_EDEADLK','rec ? 0u : CELL_EDEADLK','CELL_ESRCH','0','rec ? 0u : CELL_EPERM','0','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH','CELL_ESRCH']
for rec,broadcast,protocol in [(False,False,1),(True,False,1),(False,True,2),(True,True,2)]:
 codes2=[(109 if broadcast else 108) if x=='program.broadcast ? 109u : 108u' else int(x) for x in second]
 queued=expired=woken=handles=created=destroyed=0;usage=Counter()
 for tx in range(3):
  first_role=tx%2;second_role=1-first_role;mutex_live=cond_live=False;links=0;owner=None;depth=0;queue=[];timer=None;signals=0
  for op in range(18):
   usage.update((first[op],codes2[op]))
   if op==0:assert not mutex_live;mutex_live=True;created+=1;handles+=1
   elif op==1:assert mutex_live and not cond_live;cond_live=True;links+=1;created+=1;handles+=1
   elif op==2:
    assert owner is None and links==1 # native linked unlocked mutex destroy EPERM
    assert cond_live # foreign cond_wait EPERM changes no ownership
   elif op==3:assert owner is None;owner=first_role
   elif op==4:
    assert owner==first_role
    if rec:depth+=1
    signals+=1 # empty signal
   elif op in (5,6):
    saved_depth=depth;assert owner==first_role and not queue and timer is None
    queue.append(first_role);owner=None;depth=0;timer=100000 if op==5 else 1000000;queued+=1
    assert links==1 and cond_live # queued cond_destroy EBUSY keeps object/link
    if op==5:expired+=1
    else:signals+=1;woken+=1
    queue.remove(first_role);timer=None;owner=first_role;depth=saved_depth
    assert owner==first_role and depth==int(rec)
   elif op==7:
    assert owner==first_role
    if rec:depth-=1 # peer trylock remains EBUSY
    else:owner=second_role
   elif op==8:
    if rec:assert owner==first_role and depth==0;owner=second_role
    else:assert owner==second_role # foreign unlock EPERM; repeat trylock EDEADLK
   elif op==9:
    assert owner==second_role # foreign cond_wait EPERM; preserve owner/count
    if rec:depth+=1
   elif op==10:signals+=2 # empty broadcast + invalid-target signal metadata
   elif op==11:
    assert owner==second_role
    if rec:depth-=1
    else:owner=None
   elif op==12:
    if rec:assert owner==second_role and depth==0;owner=None
    else:assert owner is None;owner=first_role
   elif op==13:
    if rec:assert owner is None;owner=first_role
    else:assert owner==first_role
    assert cond_live and not queue;cond_live=False;links-=1;destroyed+=1
   elif op==14:assert owner==first_role and depth==0;owner=None
   elif op==15:assert mutex_live and not links and owner is None;mutex_live=False;destroyed+=1
   else:assert not mutex_live and not cond_live # stale APIs cannot publish handles or mutate owners
   assert links==int(cond_live) and not queue and timer is None
   expected_owner=[None,None,None,first_role,first_role,first_role,first_role,first_role if rec else second_role,second_role,second_role,second_role,second_role if rec else None,None if rec else first_role,first_role,None,None,None,None][op]
   assert owner==expected_owner
   assert depth==[0,0,0,0,int(rec),int(rec),int(rec),0,0,int(rec),int(rec),0,0,0,0,0,0,0][op]
   assert signals==[0,0,0,0,1,1,2,2,2,2,4,4,4,4,4,4,4,4][op]
 assert (queued,expired,woken,handles,created,destroyed)==(6,3,3,6,6,6)
 expected={100:6,101:6,103:24,104:21,105:9,106:9,107:15,108:6 if broadcast else 9,109:9 if broadcast else 6,110:3}
 assert usage==expected and sum(usage.values())==108
for token in ['static int armsx3_core_test_cond_batch(u32 protocol, bool recursive, bool broadcast)',
 'sizeof(mutexAttribute) == 40', 'sizeof(conditionAttribute) == 24', 'value.mutex->lock_count == 0 && value.mutex->cond_count == 1',
 'job.waiter, &context, job.waiterTimeout)', 'armsx3_ios_ppu_probe_mutex_timeout_finished(waiter, signaller) != 1',
 'value._mutex.get() == mutex.get()', 'value.cond_count == (liveCondition ? 1u : 0u)',
 'value.dbg_signal_count == signals', 'program.slices != 162', 'program.totals != std::array<u32, 2>{54, 54}',
 'program.queueObserved.load() != 6', 'program.expiryObserved.load() != 3', 'program.wakeObserved.load() != 3',
 'for (u32 id : conditionIDs())', 'for (u32 id : mutexIDs())', 'budgets{5, 1, 6}', 'pcs{20, 24, 48}',
 '0xfedcba9876543210ull', 'cleanup.join(); throw;', '(i ? 0x20000000u : 0u)']:
 assert token in s,token
assert s.index('for (u32 id : conditionIDs())')<s.index('for (u32 id : mutexIDs())')
app=(here.parent/'core/loadtest/App.mm').read_text()
stages=re.findall(r'\{(\d+), "[^"]+", "(armsx3_core_[^"]+)"\}',app)
assert [int(n) for n,_ in stages]==list(range(2,90)) and len({f for _,f in stages})==88
assert [f for _,f in stages[-4:]]==['armsx3_core_test_cond_'+x for x in ('fifo','recursive','broadcast','recursive_broadcast')]
info=plistlib.loads((here.parent/'core/loadtest/Info.plist.in').read_bytes())
assert info['CFBundleVersion']=='104' and info['MinimumOSVersion']=='16.0'
print('PASS: frozen Build103 prefix; four independent condition/mutex link/owner/recursive count/timeout/reacquire/error lifecycles;108SC/six handles/54TLS each,88 UI stages and Build104/iOS16; native pending')

"""Independent guest SC/LV2 mutex ownership and lifecycle oracle."""
from pathlib import Path
import hashlib,re,runpy,struct
root=Path(__file__).resolve().parent
runpy.run_path(str(root/'test_p71_fixture.py'))
bridge=root.parent/'core/loadtest/CoreBridge.cpp'
assert hashlib.sha256(bridge.read_bytes()[:2250420]).hexdigest()=='c0770ffff9e5b9ab6de78cf9dfc6b2b9d1dd10e45d9772d91cd853ef19d068ac','Build92 prefix changed'
source=bridge.read_text();start=source.index('int armsx3_core_test_mutex_sleep_wake()');a=source.index('{',start);end=a+1;depth=1
while depth:depth+=(source[end]=='{')-(source[end]=='}');end+=1
stage=source[start:end]
code=stage.split('const std::array<u32, 10> opcodes{',1)[1].split('};',1)[0]
ops=[]
for m in re.finditer(r'\b(LWZ|LD|SC|STW|ADDI|NOP)\(([^()]*)\)',code):
 name,args=m.groups();v=[int(x.strip(),0) for x in args.split(',')] if args else []
 word=0x44000002|(v[0]<<5) if name=='SC' else 0x60000000 if name=='NOP' else ({'LWZ':32,'LD':58,'STW':36,'ADDI':14}[name]<<26)|(v[0]<<21)|(v[1]<<16)|(v[2]&0xffff)
 ops.append(word)
assert ops==[0x80650000,0xe8850008,0x81650004,0x44000002,0x90660000,0x818d900c,0x398c0001,0x918d900c,0x91860004,0x60000000]
encoded=b''.join(x.to_bytes(4,'big') for x in ops)
data=bytearray([0xa5]*0x10000);data[0x80:0x89]=b'iOSProbe\0'
data[0x3040:0x3068]=struct.pack('>IIIIQII',1,0x10,0x200,0x2000,0,0,0)+b'iOSMutex'
expected=data[:];pool=bytearray(0x40000)
for i in range(3):pool[0x60+i*0x70:0x69+i*0x70]=b'iOSProbe\0'
expected_pool=pool[:];contexts=[dict(history=[],tls=0) for _ in range(2)]
EFAULT=0x8001000d;ESRCH=0x80010005;EBUSY=0x8001000a;EPERM=0x80010009;EDEADLK=0x80010008
first_codes=[100,102,102,101,104,104,102,104,101,101,101,101];second_codes=[100,102,103,104,103,102,103,102,104,104,103,103]
first_errors=[0,0,0,EBUSY,0,0,ESRCH,EPERM,EBUSY,EBUSY,0,ESRCH];second_errors=[EFAULT,ESRCH,EBUSY,EPERM,EBUSY,0,ESRCH,0,0,0,ESRCH,ESRCH]
objects={};usage={100:0,101:0,102:0,103:0,104:0};steps=pauses=stores=creates=destroys=blocked=0;waiter_queued=0
def read(address):
 block,offset=(pool,address-0x50000) if address>=0x50000 else (data,address-0x20000)
 return int.from_bytes(block[offset:offset+4],'big')
def write(address,value):
 block,offset=(pool,address-0x50000) if address>=0x50000 else (data,address-0x20000)
 block[offset:offset+4]=struct.pack('>I',value&0xffffffff)
for tx in range(3):
 first=tx%2;handle=0
 for operation in range(12):
  call=tx*12+operation
  for worker,c in enumerate(contexts):
   primary=worker==first;invalid=(operation==6 if primary else operation in [1,6,10])
   code=(first_codes if primary else second_codes)[operation]
   arg=0x23000 if operation==0 and primary else 0 if operation==0 or invalid else handle
   timeout=[0,0x1122334455667788,0xfedcba9876543210][(call+worker)%3]
   args=[arg,0x23040 if operation==0 else timeout if code==102 and operation!=5 else 0,code]
   request=0x21000+call*0x40+worker*0x20;out=0x20200+call*0x20+worker*0x10
   descriptor=struct.pack('>IIQ',args[0],code,args[1]);offset=request-0x20000
   data[offset:offset+16]=descriptor;expected[offset:offset+16]=descriptor
   g=[0xa5a5000000000000+n for n in range(32)];g[1]=0x37f90+worker*0x10000;g[5]=request;g[6]=out;g[13]=0x57060+worker*0x70;g[30]=0x12345678
   c.update(g=g,pc=0,lr=0x12340000,ctr=0x76540000,args=args,code=code,out=out,last=None,abi=[0]*8)
  for slice,budget in enumerate([3,1,6]):
   if operation==5 and slice==1:
    waiter_queued=0x1000000+1-first;blocked+=1
    c=contexts[1-first];g=c['g'];assert c['pc']==12 and g[11]==102 and g[4]==0 and objects[handle]['owner']==0x1000000+first
    before_data=data[:];before_pool=pool[:];c['pc']=16;steps+=1;usage[102]+=1;c['abi']=g[3:11];g[3]=0
    assert data==before_data and pool==before_pool and objects[handle]['recursive']==0
   for worker in [first,1-first]:
    c=contexts[worker];g=c['g']
    for _ in range(0 if operation==5 and slice==1 and worker==1-first else budget):
     pc=c['pc'];word=ops[pc//4];c['pc']+=4;steps+=1
     typ=word>>26;rt=(word>>21)&31;ra=(word>>16)&31;imm=(word&0xffff)-(0x10000 if word&0x8000 else 0)
     if word==0x44000002:
      arg=g[3];code=g[11];usage[code]+=1;error=0;name={100:'sys_mutex_create',101:'sys_mutex_destroy',103:'sys_mutex_trylock',104:'sys_mutex_unlock',102:'sys_mutex_lock'}[code];c['abi']=g[3:11]
      if code==100:
       if not arg:error=EFAULT
       else:
        assert not objects;handle=0x85000801+tx*0x100;objects[handle]=dict(owner=0,recursive=0,exists=1);write(arg,handle);creates+=1
      elif arg not in objects:error=ESRCH
      elif code==101:
       if objects[arg]['owner']:error=EBUSY
       else:del objects[arg];destroys+=1
      elif code in [102,103]:
       owner=objects[arg]['owner']
       if owner:
        if owner==worker+0x1000000:objects[arg]['recursive']+=1
        else:error=EBUSY
       else:objects[arg]['owner']=worker+0x1000000
      else:
       if objects[arg]['owner']!=worker+0x1000000:error=EPERM
       elif objects[arg]['recursive']:objects[arg]['recursive']-=1
       else:
        objects[arg]['owner']=waiter_queued;waiter_queued=0
      g[3]=error if error<0x80000000 else error|0xffffffff00000000
      c['history'].append((0x1000c,name,g[3],c['abi'][:4]));c['last']=name
      assert error==(first_errors if worker==first else second_errors)[operation]
     elif typ==32:g[rt]=read(g[ra]+imm)
     elif typ==58:g[rt]=int.from_bytes(data[g[ra]+imm-0x20000:g[ra]+imm-0x20000+8],'big')
     elif typ==14:g[rt]=g[ra]+imm
     elif typ==36:write(g[ra]+imm,g[rt]);stores+=1
     else:assert word==0x60000000
    if operation==5 and slice==1 and worker==1-first:
     assert not waiter_queued and objects[handle]['owner']==0x1000000+worker
     c['last']='sys_mutex_lock';c['history'].append((0x1000c,c['last'],g[3],c['abi'][:4]))
    assert c['pc']==[12,16,40][slice];pauses+=int(slice<2)
   if operation==0 and slice==1:expected[0x3000:0x3004]=struct.pack('>I',handle)
   live= slice>=1 if operation==0 else operation<10 or operation==10 and slice==0
   owner=0
   if operation==1 and slice>=1 or operation in [2,3,4] or operation==5 and slice==0:owner=0x1000000+first
   if operation==5 and slice>=1 or operation in [6,7,8] or operation==9 and slice==0:owner=0x1000000+1-first
   assert len(objects)==int(live)
   depth=int(operation==2 and slice>=1 or operation==3 or operation==4 and slice==0 or operation==7 and slice>=1 or operation==8 and slice==0)
   if live:assert objects[handle]==dict(owner=owner,recursive=depth,exists=1)
   for worker,c in enumerate(contexts):
    g=[0xa5a5000000000000+n for n in range(32)];g[1]=0x37f90+worker*0x10000;g[5]=0x21000+call*0x40+worker*0x20;g[6]=c['out'];g[13]=0x57060+worker*0x70;g[30]=0x12345678
    error=(first_errors if worker==first else second_errors)[operation]
    g[3]=(error|0xffffffff00000000 if error else 0) if slice else c['args'][0];g[4]=c['args'][1];g[11]=c['code']
    if slice==2:g[12]=call+1
    assert c['g']==g and c['ctr']==0x76540000 and c['lr']==0x12340000
    assert len(c['history'])==call+int(slice>0)
    if slice:
     abi=g[3:11];abi[0]=c['args'][0];assert c['abi']==abi
     assert c['history'][-1][0]==0x1000c and c['history'][-1][2]==g[3] and c['history'][-1][3]==abi[:4]
    else:assert c['abi']==[0]*8 and c['last'] is None
    if slice==2:
     offset=c['out']-0x20000;expected[offset:offset+8]=struct.pack('>II',error,call+1)
     expected_pool[0x6c+worker*0x70:0x70+worker*0x70]=struct.pack('>I',call+1)
   assert data==expected and pool==expected_pool
assert (steps,pauses,stores,creates,destroys)==(720,144,216,3,3)
assert usage=={100:6,101:15,102:18,103:15,104:18} and not objects and blocked==3 and not waiter_queued
for text in ['ppu_get_syscall_name(codes[i])','sys_mutex_attribute_t attribute{}','SYS_SYNC_RECURSIVE',
 'idm::select<lv2_obj, lv2_mutex>','idm::withdraw<lv2_obj, lv2_mutex>','mutex.control.load()', 'mutex.lock_count == expectedDepth',
 'operation == 9 && slice == 1','job.historyError != error','job.continuation != expected',
 'timeouts{0, 0x1122334455667788ull, 0xfedcba9876543210ull}', 'const be_t<u64> second = job.arguments[1];', 'armsx3_ios_ppu_probe_mutex_sleep_state(job.waiter, &context)', 'cleanup.join(); throw;', 'program.blockedObservations.load() != 3', 'program.slices != 108','std::array<u32, 2>{36, 36}','id_manager::g_id = previous','slice < 2 ? -2 : 6']:
 assert text in stage,text
assert stage.count('std::make_unique<named_thread<ppu_thread>>')==2
registry=stage.index('using MutexMap = id_manager::id_map<lv2_obj>;')
assert registry < stage.index('struct MutexCleanup') < stage.index('MutexCleanup::ids().empty()')
assert 'if (!g_fxo->is_init<MutexMap>() && !g_fxo->init<MutexMap>())' in stage
print('PASS: P72 SHA1='+hashlib.sha1(encoded).hexdigest()+',10words/40bytes,216dispatches/144pauses/720guest instructions/72SC calls,18sys_mutex_lock calls/three queued-suspended-unlock-wake acquisitions/full64 timeouts/recursive lifecycles/exact owner/depth/partial release/error/handoff/destroy/stale states,whole DATA/TLS36/36;P43-P71 preserved')

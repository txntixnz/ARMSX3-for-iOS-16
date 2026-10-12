"""Independent guest SC/LV2 mutex ownership and lifecycle oracle."""
from pathlib import Path
import hashlib,re,runpy,struct
root=Path(__file__).resolve().parent
runpy.run_path(str(root/'test_p68_fixture.py'))
bridge=root.parent/'core/loadtest/CoreBridge.cpp'
assert hashlib.sha256(bridge.read_bytes()[:2123739]).hexdigest()=='7efd56cb6a9ae22e24b83cab553a635cc0173dea779deca9e3e3fca7bc37570f','Build88 prefix changed'
source=bridge.read_text();start=source.index('int armsx3_core_test_lv2_mutex_ownership()');a=source.index('{',start);end=a+1;depth=1
while depth:depth+=(source[end]=='{')-(source[end]=='}');end+=1
stage=source[start:end]
code=stage.split('const std::array<u32, 10> opcodes{',1)[1].split('};',1)[0]
ops=[]
for m in re.finditer(r'\b(LWZ|SC|STW|ADDI|NOP)\(([^()]*)\)',code):
 name,args=m.groups();v=[int(x.strip(),0) for x in args.split(',')] if args else []
 word=0x44000002|(v[0]<<5) if name=='SC' else 0x60000000 if name=='NOP' else ({'LWZ':32,'STW':36,'ADDI':14}[name]<<26)|(v[0]<<21)|(v[1]<<16)|(v[2]&0xffff)
 ops.append(word)
assert ops==[0x80650000,0x80850004,0x81650008,0x44000002,0x90660000,0x818d900c,0x398c0001,0x918d900c,0x91860004,0x60000000]
encoded=b''.join(x.to_bytes(4,'big') for x in ops)
data=bytearray([0xa5]*0x10000);data[0x80:0x89]=b'iOSProbe\0'
data[0x3040:0x3068]=struct.pack('>IIIIQII',1,0x20,0x200,0x2000,0,0,0)+b'iOSMutex'
expected=data[:];pool=bytearray(0x40000)
for i in range(3):pool[0x60+i*0x70:0x69+i*0x70]=b'iOSProbe\0'
expected_pool=pool[:];contexts=[dict(history=[],tls=0) for _ in range(2)]
EFAULT=0x8001000d;ESRCH=0x80010005;EBUSY=0x8001000a;EPERM=0x80010009;EDEADLK=0x80010008
first_codes=[100,103,103,101,104,103,104,101,101,101];second_codes=[100,103,103,104,103,103,103,104,103,103]
first_errors=[0,0,EDEADLK,EBUSY,0,ESRCH,EPERM,EBUSY,0,ESRCH];second_errors=[EFAULT,ESRCH,EBUSY,EPERM,ESRCH,0,EDEADLK,0,ESRCH,ESRCH]
objects={};usage={100:0,101:0,103:0,104:0};steps=pauses=stores=creates=destroys=0
def read(address):
 block,offset=(pool,address-0x50000) if address>=0x50000 else (data,address-0x20000)
 return int.from_bytes(block[offset:offset+4],'big')
def write(address,value):
 block,offset=(pool,address-0x50000) if address>=0x50000 else (data,address-0x20000)
 block[offset:offset+4]=struct.pack('>I',value&0xffffffff)
for tx in range(3):
 first=tx%2;handle=0
 for operation in range(10):
  call=tx*10+operation
  for worker,c in enumerate(contexts):
   primary=worker==first;invalid=(operation==5 if primary else operation in [1,4,8])
   code=(first_codes if primary else second_codes)[operation]
   arg=0x23000 if operation==0 and primary else 0 if operation==0 or invalid else handle
   args=[arg,0x23040 if operation==0 else 0,code]
   request=0x21000+call*0x40+worker*0x20;out=0x20200+call*0x20+worker*0x10
   for n,x in enumerate(args):write(request+n*4,x);expected[request-0x20000+n*4:request-0x20000+n*4+4]=struct.pack('>I',x)
   g=[0xa5a5000000000000+n for n in range(32)];g[1]=0x37f90+worker*0x10000;g[5]=request;g[6]=out;g[13]=0x57060+worker*0x70;g[30]=0x12345678
   c.update(g=g,pc=0,lr=0x12340000,ctr=0x76540000,args=args,code=code,out=out,last=None,abi=[0]*8)
  for slice,budget in enumerate([3,1,6]):
   for worker in [first,1-first]:
    c=contexts[worker];g=c['g']
    for _ in range(budget):
     pc=c['pc'];word=ops[pc//4];c['pc']+=4;steps+=1
     typ=word>>26;rt=(word>>21)&31;ra=(word>>16)&31;imm=(word&0xffff)-(0x10000 if word&0x8000 else 0)
     if word==0x44000002:
      arg=g[3];code=g[11];usage[code]+=1;error=0;name={100:'sys_mutex_create',101:'sys_mutex_destroy',103:'sys_mutex_trylock',104:'sys_mutex_unlock'}[code];c['abi']=g[3:11]
      if code==100:
       if not arg:error=EFAULT
       else:
        assert not objects;handle=0x85000801+tx*0x100;objects[handle]=dict(owner=0,recursive=0,exists=1);write(arg,handle);creates+=1
      elif arg not in objects:error=ESRCH
      elif code==101:
       if objects[arg]['owner']:error=EBUSY
       else:del objects[arg];destroys+=1
      elif code==103:
       owner=objects[arg]['owner']
       if owner:error=EDEADLK if owner==worker+0x1000000 else EBUSY
       else:objects[arg]['owner']=worker+0x1000000
      else:
       if objects[arg]['owner']!=worker+0x1000000:error=EPERM
       else:objects[arg]['owner']=0
      g[3]=error if error<0x80000000 else error|0xffffffff00000000
      c['history'].append((0x1000c,name,g[3],c['abi'][:4]));c['last']=name
      assert error==(first_errors if worker==first else second_errors)[operation]
     elif typ==32:g[rt]=read(g[ra]+imm)
     elif typ==14:g[rt]=g[ra]+imm
     elif typ==36:write(g[ra]+imm,g[rt]);stores+=1
     else:assert word==0x60000000
    assert c['pc']==[12,16,40][slice];pauses+=int(slice<2)
   if operation==0 and slice==1:expected[0x3000:0x3004]=struct.pack('>I',handle)
   live= slice>=1 if operation==0 else operation<8 or operation==8 and slice==0
   owner=0
   if operation==1 and slice>=1 or operation in [2,3] or operation==4 and slice==0:owner=0x1000000+first
   if operation==5 and slice>=1 or operation==6 or operation==7 and slice==0:owner=0x1000000+1-first
   assert len(objects)==int(live)
   if live:assert objects[handle]==dict(owner=owner,recursive=0,exists=1)
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
assert (steps,pauses,stores,creates,destroys)==(600,120,180,3,3)
assert usage=={100:6,101:12,103:30,104:12} and not objects
for text in ['ppu_get_syscall_name(codes[i])','sys_mutex_attribute_t attribute{}','SYS_SYNC_NOT_RECURSIVE',
 'idm::select<lv2_obj, lv2_mutex>','idm::withdraw<lv2_obj, lv2_mutex>','mutex.control.load()',
 'operation == 7 && slice == 1','job.historyError != error','job.continuation != expected',
 'program.slices != 90','std::array<u32, 2>{30, 30}','id_manager::g_id = previous','slice < 2 ? -2 : 6']:
 assert text in stage,text
assert stage.count('std::make_unique<named_thread<ppu_thread>>')==2
registry=stage.index('using MutexMap = id_manager::id_map<lv2_obj>;')
assert registry < stage.index('struct MutexCleanup') < stage.index('MutexCleanup::ids().empty()')
assert 'if (!g_fxo->is_init<MutexMap>() && !g_fxo->init<MutexMap>())' in stage
print('PASS: P69 SHA1='+hashlib.sha1(encoded).hexdigest()+',10words/40bytes,180dispatches/120pauses/600guest instructions/60SC calls,three nonrecursive mutex lifecycles/exact owner/error/handoff/destroy/stale states,whole DATA/TLS30/30;P43-P68 preserved')

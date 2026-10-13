"""Independent semaphore permit/guest-byte oracle; native execution is separate."""
from pathlib import Path
import hashlib,re,runpy,struct
root=Path(__file__).resolve().parent
runpy.run_path(str(root/'test_p75_fixture.py'))
bridge=root.parent/'core/loadtest/CoreBridge.cpp'
assert hashlib.sha256(bridge.read_bytes()[:2444296]).hexdigest()=='1aded3ac213c5a7024704618a6acd44f8c6ac021d3f931be20e802ef4bcacea1'
s=bridge.read_text();a=s.index('int armsx3_core_test_semaphore_lifecycle()');stage=s[a:]
code=stage.split('const std::array<u32, 12> opcodes{',1)[1].split('};',1)[0];ops=[]
for m in re.finditer(r'\b(LWZ|LD|SC|STW|ADDI|NOP)\(([^()]*)\)',code):
 name,args=m.groups();v=[int(x.strip(),0) for x in args.split(',')] if args else []
 ops.append(0x44000002|(v[0]<<5) if name=='SC' else 0x60000000 if name=='NOP' else ({'LWZ':32,'LD':58,'STW':36,'ADDI':14}[name]<<26)|(v[0]<<21)|(v[1]<<16)|(v[2]&0xffff))
assert ops==[0x81650004,0x80650000,0xe8850008,0x80c50014,0x80a50010,0x44000002,0x90690000,0x818d900c,0x398c0001,0x918d900c,0x91890004,0x60000000]
encoded=b''.join(x.to_bytes(4,'big') for x in ops)
data=bytearray([0xa5]*0x10000);data[0x80:0x89]=b'iOSProbe\0';data[0x3040:0x3060]=struct.pack('>IIQII8s',1,0x200,0,0,0,b'iOSSema!');expected=data[:]
pool=bytearray(0x40000)
for i in range(3):pool[0x60+i*0x70:0x69+i*0x70]=b'iOSProbe\0'
expected_pool=pool[:];contexts=[dict(history=[]) for _ in range(2)]
EFAULT=0x8001000d;ESRCH=0x80010005;EBUSY=0x8001000a;EINVAL=0x80010002
first_codes=[90,92,114,94,94,92,93,94,114,91,91,90];second_codes=[90,93,93,114,94,93,114,94,92,114,94,114]
first_errors=[0,0,0,0,EBUSY,0,0,EINVAL,0,0,ESRCH,EINVAL];second_errors=[EFAULT,0,EBUSY,0,EINVAL,0,EFAULT,0,0,ESRCH,ESRCH,ESRCH]
after_values=[2,0,0,3,3,1,0,1,0,0,0,0];objects={};usage={90:0,91:0,92:0,93:0,94:0,114:0};steps=pauses=stores=creates=destroys=count_stores=0
names={90:'sys_semaphore_create',91:'sys_semaphore_destroy',92:'sys_semaphore_wait',93:'sys_semaphore_trywait',94:'sys_semaphore_post',114:'sys_semaphore_get_value'}
def read(address,width=4):
 block,off=(pool,address-0x50000) if address>=0x50000 else (data,address-0x20000)
 return int.from_bytes(block[off:off+width],'big')
def write(address,value):
 block,off=(pool,address-0x50000) if address>=0x50000 else (data,address-0x20000)
 block[off:off+4]=struct.pack('>I',value&0xffffffff)
for tx in range(3):
 first=tx%2;handle=0
 for operation in range(12):
  call=tx*12+operation
  for worker,c in enumerate(contexts):
   primary=worker==first;code=(first_codes if primary else second_codes)[operation]
   ptr=0x24000+call*0x10+worker*4;timeout=[0,0x1122334455667788,0xfedcba9876543210][(call+worker)%3]
   arg0=(0 if operation==0 and not primary else 0x23000) if code==90 else 0 if operation==11 and not primary else handle
   second=0x23040 if code==90 else timeout if code==92 else (0 if not primary and operation==6 else ptr) if code==114 else (3 if primary and operation==3 else 0xffffffff if primary and operation==7 else 0 if not primary and operation==4 else 1) if code==94 else 0
   args=[arg0,second,code,(0xffffffff if operation==11 else 2) if code==90 else 0,3 if code==90 else 0]
   request=0x21000+call*0x40+worker*0x20;out=0x20200+call*0x20+worker*0x10
   descriptor=struct.pack('>IIQII',arg0,code,second,args[3],args[4]);off=request-0x20000;data[off:off+24]=descriptor;expected[off:off+24]=descriptor
   g=[0xa5a5000000000000+n for n in range(32)];g[1]=0x37f90+worker*0x10000;g[5]=request;g[9]=out;g[13]=0x57060+worker*0x70;g[30]=0x12345678
   c.update(g=g,pc=0,lr=0x12340000,ctr=0x76540000,args=args,code=code,out=out,last=None,abi=[0]*8)
  for slice,budget in enumerate([5,1,6]):
   for worker in [first,1-first]:
    c=contexts[worker];g=c['g']
    for _ in range(budget):
     pc=c['pc'];word=ops[pc//4];c['pc']+=4;steps+=1;typ=word>>26;rt=(word>>21)&31;ra=(word>>16)&31;imm=(word&0xffff)-(0x10000 if word&0x8000 else 0)
     if word==0x44000002:
      arg=g[3];code=g[11];usage[code]+=1;error=0;c['abi']=g[3:11]
      if code==90:
       if not arg:error=EFAULT
       elif g[5]&0x80000000 or g[5]>g[6] or not g[6]:error=EINVAL
       else:
        assert not objects;handle=0x96000801+tx*0x100;objects[handle]=dict(val=2,max=3,exists=1,posts=0,poster=0);write(arg,handle);expected[arg-0x20000:arg-0x20000+4]=struct.pack('>I',handle);creates+=1
      elif arg not in objects:error=ESRCH
      elif code==91:del objects[arg];destroys+=1
      elif code in [92,93]:
       if objects[arg]['val']:objects[arg]['val']-=1
       else:assert code==93;error=EBUSY
      elif code==94:
       count=g[4]&0xffffffff
       if not count or count&0x80000000:error=EINVAL
       else:
        objects[arg]['posts']+=1;objects[arg]['poster']=0x1000000+worker
        if count>objects[arg]['max']-objects[arg]['val']:error=EBUSY
        else:objects[arg]['val']+=count
      else:
       if not g[4]:error=EFAULT
       else:
        value=objects[arg]['val'];write(g[4],value);expected[g[4]-0x20000:g[4]-0x20000+4]=struct.pack('>I',value);count_stores+=1
      g[3]=error|0xffffffff00000000 if error else 0;c['history'].append((0x10014,names[code],g[3],c['abi'][:4]));c['last']=names[code]
      assert error==(first_errors if worker==first else second_errors)[operation]
     elif typ==32:g[rt]=read(g[ra]+imm)
     elif typ==58:g[rt]=read(g[ra]+imm,8)
     elif typ==14:g[rt]=g[ra]+imm
     elif typ==36:write(g[ra]+imm,g[rt]);stores+=1
     else:assert word==0x60000000
    assert c['pc']==[20,24,48][slice];pauses+=int(slice<2)
   live=slice>=1 if operation==0 else operation<9 or operation==9 and slice==0
   assert len(objects)==int(live)
   if live:
    val=after_values[operation] if slice else after_values[operation-1];posts=0 if operation<3 or operation==3 and not slice else 1 if operation==3 or operation==4 and not slice else 2 if operation<7 or operation==7 and not slice else 3
    assert objects[handle]==dict(val=val,max=3,exists=1,posts=posts,poster=0 if not posts else 0x1000000+(1-first if posts==3 else first))
   for worker,c in enumerate(contexts):
    args=c['args'];error=(first_errors if worker==first else second_errors)[operation]
    g=[0xa5a5000000000000+n for n in range(32)];g[1]=0x37f90+worker*0x10000;g[3]=error|0xffffffff00000000 if slice and error else 0 if slice else args[0];g[4]=args[1];g[5]=args[3];g[6]=args[4];g[9]=c['out'];g[11]=args[2];g[13]=0x57060+worker*0x70;g[30]=0x12345678
    if slice==2:g[12]=call+1
    assert c['g']==g and c['ctr']==0x76540000 and c['lr']==0x12340000 and len(c['history'])==call+int(slice>0)
    if slice:
     abi=g[3:11];abi[0]=args[0];assert c['abi']==abi and c['history'][-1]==(0x10014,names[args[2]],g[3],args[:2]+args[3:5])
    else:assert c['abi']==[0]*8 and c['last'] is None
    if slice==2:
     off=c['out']-0x20000;expected[off:off+8]=struct.pack('>II',error,call+1);expected_pool[0x6c+worker*0x70:0x70+worker*0x70]=struct.pack('>I',call+1)
   assert data==expected and pool==expected_pool
assert (steps,pauses,stores,creates,destroys,count_stores)==(864,144,216,3,3,9) and not objects
assert usage=={90:9,91:6,92:9,93:12,94:18,114:18}
for text in ['sizeof(attribute) == 32','sys_semaphore_attribute_t attribute{}','lv2_sema','sema.val == expectedValue','sema.max == 3','sema.dbg_post_count == expectedPosts','const bool ordered = slice == 1;','budgets{5, 1, 6}','pcs{20, 24, 48}','job.historyCIA != job.begin + 20','program.slices != 108','std::array<u32, 2>{36, 36}','trailing{u32(job.arguments[3]), u32(job.arguments[4])}']:
 assert text in stage,text
print('PASS: P76 SHA1='+hashlib.sha1(encoded).hexdigest()+',12words/48bytes/216dispatches/144pauses/864instructions/72SC;3semaphore lifecycles/initial2-max3/permits consumed once/max+overflow/zero-negative posts/negative create/value outputs and error canaries/stale handles/full64 wait and4create args/whole DATA/TLS36/36;P43-P75 preserved')

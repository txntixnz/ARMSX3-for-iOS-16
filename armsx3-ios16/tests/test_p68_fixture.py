"""Independent oracle for guest calls into registered spinlock services."""
from pathlib import Path
import ast,hashlib,re,runpy,struct
root=Path(__file__).resolve().parent
runpy.run_path(str(root/'test_p67_fixture.py'))
bridge=root.parent/'core/loadtest/CoreBridge.cpp'
assert hashlib.sha256(bridge.read_bytes()[:2067562]).hexdigest()=='bb4853b5d2a063da159c72b9f2ba943bd72c72b04f0c968d33f17c3588de337b','Build87 bridge prefix changed'
source=bridge.read_text();start=source.index('int armsx3_core_test_interrupted_spinlock_replay()')
opening=source.index('{',start);end=opening+1;depth=1
while depth:
    depth+=(source[end]=='{')-(source[end]=='}');end+=1
stage=source[start:end]
code=stage.split('const std::array<u32, 68> opcodes{',1)[1].split('};',1)[0]
ops=[]
for m in re.finditer(r'\b(B|LWZ|ADDI|STW|NOP)\(([^()]*)\)|\baddToken\b',code):
    name,args=m.group(1),m.group(2)
    if name is None:ops.append(0x7d6b5214);continue
    a=[ast.literal_eval(v.strip().replace('false','False').replace('true','True')) for v in args.split(',')] if args else []
    if name=='NOP':word=0x60000000
    elif name=='B':word=(18<<26)|(a[0]&0x03fffffc)|((int(a[1])<<1)|int(a[2]) if len(a)>1 else 0)
    else:word=({'LWZ':32,'ADDI':14,'STW':36}[name]<<26)|(a[0]<<21)|(a[1]<<16)|(a[2]&0xffff)
    ops.append(word)
golden=[0x38650000,0x480000fd,0x38650000,0x480000f9,0x90660010,0x4800002c,
 0x38650000,0x480000ed,0x90660014,0x38650000,0x480000e1,0x90660018,0x38650000,0x480000d1,0x9066001c,0x48000004,
 0x81250080,0x81650084,0x39290001,0x7d6b5214,0x91250080,0x91650084,0x91260000,0x91660004,0x91460008,
 0x38650000,0x480000a5,0x90660020,0x818d900c,0x398c0001,0x918d900c,0x9186000c,0x48000090,
 0x60000000,0x60000000,0x60000000,0x60000000,0x4bffff84]+[0x60000000]*30
assert ops==golden and len(ops)==68
encoded=b''.join(x.to_bytes(4,'big') for x in ops)
data=bytearray([0xa5]*0x10000);data[0x80:0x89]=b'iOSProbe\0'
data[0x3000:0x3004]=bytes.fromhex('12345678')
data[0x3080:0x3088]=bytes(8);expected=data[:]
pool=bytearray(0x40000)
for slot in range(3):pool[0x60+slot*0x70:0x69+slot*0x70]=b'iOSProbe\0'
expected_pool=pool[:];writes={};contexts=[{'history':[]} for _ in range(2)]
first_budgets=[1,1,1,2,1,6,5,2,1,2,3,1];second_budgets=[1,1,1,1,1,3,4,2,3,8,7,6]
first_pcs=[4,256,8,260,16,80,100,268,108,116,128,272];second_pcs=[136,140,144,148,24,32,44,52,260,84,108,272]
names=['sys_spinlock_initialize','sys_spinlock_lock','sys_spinlock_trylock','sys_spinlock_unlock']
steps=instructions=stops=service_calls=busy_calls=successful_locks=initializations=unlocks=linked=blocked=0
def memory(addr):
    if 0x50000<=addr<0x90000:return pool,addr-0x50000
    assert 0x20000<=addr<0x30000,hex(addr)
    return data,addr-0x20000
def read(addr):
    block,offset=memory(addr);return int.from_bytes(block[offset:offset+4],'big')
def write(addr,value):
    block,offset=memory(addr);block[offset:offset+4]=struct.pack('>I',value&0xffffffff);writes[addr]=writes.get(addr,0)+1
for tx in range(3):
    first_worker=tx%2;prev=tx*2;prevsum=prev*(prev+1)//2;firstsum=prevsum+tx*2+first_worker+1;finalsum=(prev+2)*(prev+3)//2
    for worker,c in enumerate(contexts):
        g=[0xa5a5000000000000+i for i in range(32)]
        g[1]=0x37f90+worker*0x10000;g[5]=0x23000;g[6]=0x20200+tx*0x100+worker*0x80
        g[10]=tx*2+worker+1;g[13]=0x57060+worker*0x70;g[30]=0x12345678
        c.update(g=g,pc=0 if worker==first_worker else 132,lr=0x12340000,last=None,abi=[0]*8)
    for slice in range(12):
        if slice==8:
            # Independent in-flight event before any unlocking instruction:
            # waiter BL reaches lock260 while ABADCAFE is still held. A native
            # CPU pause must preserve this live call before its body returns.
            waiter=contexts[1-first_worker];before=waiter['g'][:];history=waiter['history'][:]
            assert waiter['pc']==52 and before[3]==0x23000 and read(0x23000)==0xabadcafe
            assert ops[13]==0x480000d1 and 52+208==260
            live=dict(g=before[:],lr=0x10038,pc=260,current=names[1],last=names[1],abi=before[3:11],history=history[:],wait=True,pause=True)
            assert live['g']==before and live['g'][3]!=0 and live['history']==history
            assert live['abi']==waiter['abi'] and data==expected and pool==expected_pool
            assert read(0x23080)==prev+1 and read(0x23084)==firstsum
            assert live['wait'] and live['pause'] and live['current']=='sys_spinlock_lock'
            blocked+=1
        for worker in [first_worker,1-first_worker]:
            c=contexts[worker];g=c['g'];budget=(first_budgets if worker==first_worker else second_budgets)[slice]
            if slice==8 and worker!=first_worker:
                # The first worker has now unlocked. The interrupted HLE returns
                # no success, and actual cold fast_call restores args/rewinds CIA.
                assert c['pc']==52 and g[3]==0x23000 and read(0x23000)==0
                saved=g[3:11];steps+=3;instructions+=1;service_calls+=1;linked+=1
                c['lr']=0x10038;c['pc']=264;c['last']=names[1];c['abi']=saved[:]
                c['history'].append((260,None,0x23000,saved[:4]))
                assert g[3]!=0 and g[3:11]==saved
                g[3:11]=[0xbad0000000000000+reg for reg in range(3,11)]
                assert g[3:11]!=saved
                g[3:11]=saved;c['pc']-=4
                assert c['pc']==260 and c['lr']==0x10038
                stops+=1
                continue
            for _ in range(budget):
                pc=c['pc'];assert 0<=pc<272;steps+=1
                if pc>=256:
                    service=(pc-256)//4;assert g[3]==0x23000
                    args=g[3:11];c['abi']=args[:];service_calls+=1
                    if service==0:
                        if read(g[3]):write(g[3],0)
                        initializations+=1
                    elif service in [1,2]:
                        if read(g[3]):
                            assert service==2;g[3]=0xffffffff8001000a;busy_calls+=1
                        else:write(g[3],0xabadcafe);g[3]=0;successful_locks+=1
                    else:write(g[3],0);unlocks+=1
                    c['history'].append((pc,names[service],g[3],args[:4]));c['last']=names[service];c['pc']=c['lr']-0x10000
                else:
                    instructions+=1;word=ops[pc//4];c['pc']+=4
                    typ=word>>26;rt=(word>>21)&31;ra=(word>>16)&31;imm=(word&0xffff)-(0x10000 if word&0x8000 else 0)
                    if typ==18:
                        disp=word&0x03fffffc;disp-=0x4000000 if disp&0x2000000 else 0
                        if word&1:c['lr']=0x10000+pc+4;linked+=1
                        c['pc']=pc+disp
                    elif word==0x7d6b5214:g[11]+=g[10]
                    elif typ==14:g[rt]=(g[ra] if ra else 0)+imm
                    elif typ==32:g[rt]=read(g[ra]+imm)
                    elif typ==36:write(g[ra]+imm,g[rt])
                    else:assert word==0x60000000
            assert c['pc']==(first_pcs if worker==first_worker else second_pcs)[slice]
            stops+=int(slice<11)
        def expected_word(offset,value):expected[offset:offset+4]=struct.pack('>I',value)
        expected_word(0x3000,0x12345678 if tx==0 and slice<2 else 0 if slice<4 or slice==8 or slice>=10 else 0xabadcafe)
        expected_word(0x3080,prev+(2 if slice>=9 else 1 if slice>=6 else 0))
        expected_word(0x3084,finalsum if slice>=10 else firstsum if slice>=6 else prevsum)
        for worker,c in enumerate(contexts):
            first=worker==first_worker;g=[0xa5a5000000000000+i for i in range(32)]
            g[1]=0x37f90+worker*0x10000;g[5]=0x23000;g[6]=0x20200+tx*0x100+worker*0x80
            g[10]=tx*2+worker+1;g[13]=0x57060+worker*0x70;g[30]=0x12345678
            if first:g[3]=0 if 4<=slice<=6 else 0x23000
            elif slice>=5:g[3]=0xffffffff8001000a if slice<=6 else 0x23000 if slice==7 or slice==8 or slice>=10 else 0
            if slice>=(5 if first else 9):g[9]=prev+(1 if first else 2);g[11]=firstsum if first else finalsum
            if first and slice==9:g[12]=tx
            if slice>=(10 if first else 11):g[12]=tx+1
            assert c['g']==g
            lr=(0x12340000 if slice==0 else 0x10000+(8 if slice<3 else 16 if slice<7 else 108)) if first else (0x12340000 if slice<5 else 0x10000+(32 if slice==5 else 44 if slice<8 else 56 if slice<10 else 108))
            assert c['lr']==lr
            count=([0,0,1,1,2,2,2,2,3,3,3,3] if first else [0,0,0,0,0,1,2,2,3,4,5,5])[slice]
            historybase=0 if tx==0 else (5 if worker else 3) if tx==1 else 8
            assert len(c['history'])==historybase+count
            if count:
                service=(0 if slice<4 else 1 if slice<8 else 3) if first else 2 if slice<8 else 1 if slice<10 else 3
                interrupted=not first and slice==8
                error=0x23000 if interrupted else 0 if service==1 else 0xffffffff8001000a if service==2 else 0x23000
                assert c['history'][-1]==(256+service*4,None if interrupted else names[service],error,[0x23000,g[4],g[5],g[6]])
                abi=g[3:11];abi[0]=0x23000;abi[6]=prev+(1 if first else 2) if service==3 else 0xa5a5000000000009
                assert c['last']==names[service] and c['abi']==abi
            else:assert c['last'] is None and c['abi']==[0]*8
            out=g[6]-0x20000
            if slice>=(6 if first else 10):
                for offset,value in [(0,prev+(1 if first else 2)),(4,firstsum if first else finalsum),(8,tx*2+worker+1)]:expected_word(out+offset,value)
            if first and slice>=5:expected_word(out+16,0)
            if not first and slice>=6:expected_word(out+20,0x8001000a)
            if not first and slice>=7:expected_word(out+24,0x8001000a)
            if not first and slice>=9:expected_word(out+28,0)
            if slice>=(9 if first else 11):expected_word(out+32,0x23000)
            if slice>=(10 if first else 11):
                expected_pool[0x6c+worker*0x70:0x70+worker*0x70]=struct.pack('>I',tx+1);expected_word(out+12,tx+1)
        assert data==expected and pool==expected_pool
assert (steps,instructions,stops,service_calls,busy_calls,successful_locks,initializations,unlocks,linked)==(192,165,66,24,6,6,3,6,21)
assert blocked==3
assert len(contexts[0]['history'])==11 and len(contexts[1]['history'])==13
assert writes[0x23000]==13 and writes[0x23080]==writes[0x23084]==6
assert writes[0x5006c]==writes[0x500dc]==3
assert sum(v for k,v in writes.items() if 0x20200<=k<0x20500)==42
for text in ['slice < 12','transaction * 12 + slice','slice < 11 ? -2 : first ? 1 : 6','program.slices != 36',
 'job.continuation != expected','job.status != expectedStatus','context.current_function',
 'context.syscall_history.index == job.historyIndex','job.historyError != error','job.historyArgs != args',
 'job.syscallArgs != abi','count_debug_arguments = 4','slice == 8',
 'ppu_module_manager::get_module("sysPrxForUser")','ppu_function_manager::get()',
 'ppu_register_function_at(codeAddress + 256 + i * 4, 4, i == 1 ? observedLock : services[i])','cache[i].fn != expectedCache[i]']:
    assert text in stage,text
for text in ['const ppu_intrp_func_t observedLock', 'callback.lock(context, op, instruction, next)',
 'context.state += cpu_flag::dbg_global_pause', 'waiter.state & cpu_flag::wait',
 'waiter.state += cpu_flag::stop', 'waiter.state.notify_one()',
 'waiter.syscall_history.index != waiterJob.historyIndex', 'waiter.gpr[reg] != expected[reg]',
 'program.blocked != 3', 'program.contexts[0] = owner.get()', 'program.contexts[1] = peer.get()',
 'callback.release(*owner, callback)', 'callback.release(context, callback)',
 'firstJob.continuation[34] != firstJob.begin + 108', 'P68 blocked call wrote protected data/output/TLS early']:
    assert text in stage,text
assert stage.count('std::make_unique<named_thread<ppu_thread>>')==2
for text in ['context.fast_call(std::exchange(context.cia, 0), context.gpr[2], true)',
 'context.loaded_from_savestate = true', 'program.fixups', 'waiterJob.restart.store(epoch',
 'context.state -= cpu_flag::stop + cpu_flag::again + cpu_flag::dbg_global_pause',
 'context.cia == job.begin + 260', 'interruptedHistory.func_name', 'interruptedHistory.error != 0x23000',
 'P68 native fast_call logging prefix did not restore', 'const bool expectedInterrupt']:
 assert text in stage,text
print('PASS: P68 SHA1='+hashlib.sha1(encoded).hexdigest()+',68words/272bytes,72dispatches/66pauses/192steps,24service calls/six EBUSY/three interrupted call/native cold fast_call replay/fresh retry acquisitions, guest ABI/history/LR/PC and deferred outputs/whole DATA/TLS exact; P43-P67 preserved')

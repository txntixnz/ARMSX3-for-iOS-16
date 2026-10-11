"""Independent guest spinlock, exclusion, release handoff and TLS oracle."""
from pathlib import Path
import ast,hashlib,re,runpy,struct
root=Path(__file__).resolve().parent
runpy.run_path(str(root/'test_p64_fixture.py'))
bridge=root.parent/'core/loadtest/CoreBridge.cpp'
assert hashlib.sha256(bridge.read_bytes()[:1941662]).hexdigest()=='63e582a260e62048c8f07078e9bbde0d73ff90649d7af1e98b5392923b0165ff','Build84 bridge prefix changed'
source=bridge.read_text();start=source.index('int armsx3_core_test_guest_spinlock_handoff()');stage=source[start:]
code=stage.split('const std::array<u32, 29> opcodes{',1)[1].split('};',1)[0]
ops=[]
constants={'compareLock':0x2c070000,'addToken':0x7d6b5214,'acquireFence':0x4c00012c,'releaseFence':0x7c2004ac}
for m in re.finditer(r'\b(loadReserved|storeConditional|BC|LI|LWZ|ADDI|STW|NOP)\(([^()]*)\)|\b(compareLock|addToken|acquireFence|releaseFence)\b',code):
    name,args=m.group(1),m.group(2)
    if name is None:ops.append(constants[m.group(3)]);continue
    a=[ast.literal_eval(v.strip()) for v in args.split(',')] if args else []
    if name=='NOP':word=0x60000000
    elif name in ('loadReserved','storeConditional'):word=(31<<26)|(a[0]<<21)|(a[1]<<11)|((20 if name=='loadReserved' else 150)<<1)|(name=='storeConditional')
    elif name=='LI':word=(14<<26)|(a[0]<<21)|(a[1]&0xffff)
    else:word=({'BC':16,'LWZ':32,'ADDI':14,'STW':36}[name]<<26)|(a[0]<<21)|(a[1]<<16)|(a[2]&0xffff)
    ops.append(word)
assert ops==[0x7ce02828,0x2c070000,0x4082fff8,0x39000001,0x7d00292d,0x4082ffec,0x4c00012c,
    0x81250080,0x81650084,0x39290001,0x7d6b5214,0x91250080,0x91650084,0x91260000,0x91660004,0x91460008,
    0x7c2004ac,0x39000000,0x91050000,0x818d900c,0x398c0001,0x918d900c,0x9186000c]+[0x60000000]*6
for text in ['const u32 compareLock = (11u << 26) | (7u << 16);',
    'const u32 addToken = (31u << 26) | (11u << 21) | (11u << 16) | (10u << 11) | (266u << 1);',
    'const u32 acquireFence = 0x4c00012cu, releaseFence = 0x7c2004acu;']:
    assert text in stage,text
encoded=b''.join(x.to_bytes(4,'big') for x in ops);assert len(encoded)==116
data=bytearray([0xa5]*0x10000);data[0x80:0x89]=b'iOSProbe\0'
for offset in [0x3000,0x3080,0x3084]:data[offset:offset+4]=bytes(4)
expected=data[:];pool=bytearray(0x40000)
for slot in range(3):pool[0x60+slot*0x70:0x69+slot*0x70]=b'iOSProbe\0'
expected_pool=pool[:]
contexts=[dict(rtime=0,cached=0,raddr=0,reservation=None) for _ in range(2)]
first_budgets=[2,3,1,1,4,2,3,3,3,1,1,1,1,1,1,1]
second_budgets=[2,2,1,1,3,3,3,3,2,6,5,3,3,1,5,1]
first_pcs=[8,20,24,28,44,52,64,76,88,92,96,100,104,108,112,116]
second_pcs=[8,16,20,0,0,0,0,12,20,44,64,76,88,92,112,116]
time=0;instructions=stops=loads=stores=successes=failures=held=lost=free=acquired=acquire_fences=release_fences=compares=0
writes={};histories=[]
def memory(addr):
    if 0x50000<=addr<0x90000:return pool,addr-0x50000
    assert 0x20000<=addr<0x30000,hex(addr)
    return data,addr-0x20000
def read(addr,n=4):
    block,offset=memory(addr);return int.from_bytes(block[offset:offset+n],'big')
def write(addr,value):
    block,offset=memory(addr);block[offset:offset+4]=struct.pack('>I',value);writes[addr]=writes.get(addr,0)+1
for transaction in range(3):
    first_worker=transaction%2;previous=transaction*2;previous_sum=previous*(previous+1)//2
    first_sum=previous_sum+transaction*2+first_worker+1;final_sum=(previous+2)*(previous+3)//2
    for worker,c in enumerate(contexts):
        assert c['raddr']==0
        g=[0xa5a5000000000000+i for i in range(32)]
        g[1]=0x37f90+worker*0x10000;g[5]=0x23000;g[6]=0x20200+transaction*0x100+worker*0x80
        g[10]=transaction*2+worker+1;g[13]=0x57060+worker*0x70;g[30]=0x12345678
        c.update(g=g,pc=0,cr=0x8a6c5e79^(transaction<<8)^(worker<<12),so=not worker,steps=0)
    for slice in range(16):
        for worker in [first_worker,1-first_worker]:
            c=contexts[worker];g=c['g'];budget=(first_budgets if worker==first_worker else second_budgets)[slice]
            for step in range(budget):
                pc=c['pc'];assert 0<=pc<116;word=ops[pc//4];c['pc']+=4;c['steps']+=1;instructions+=1
                typ=word>>26;rt=(word>>21)&31;ra=(word>>16)&31;imm=(word&0xffff)-(0x10000 if word&0x8000 else 0)
                if word==0x7ce02828:
                    g[7]=read(g[5]);c['raddr']=g[5]
                    if (g[5]&~127)!=(c['cached']&~127):c['rtime']=time
                    c['reservation']=read(g[5],8);loads+=1
                elif word==0x7d00292d:
                    ok=c['raddr']==g[5] and c['rtime']==time and c['reservation']==read(g[5],8);stores+=1
                    if ok:write(g[5],g[8]);time+=128;c['rtime']+=128;c['cached']=c['raddr'];successes+=1
                    else:c['cached']=0;failures+=1
                    c['raddr']=0;c['cr']=(c['cr']&0x0fffffff)|(((2 if ok else 0)|int(c['so']))<<28)
                elif word==0x2c070000:
                    compares+=1;c['cr']=(c['cr']&0x0fffffff)|(((4 if g[7] else 2)|int(c['so']))<<28)
                elif word in [0x4082fff8,0x4082ffec]:
                    taken=not bool(c['cr']&0x20000000)
                    if taken:c['pc']=pc+imm
                    if pc==8:held+=int(taken);free+=int(not taken)
                    else:lost+=int(taken);acquired+=int(not taken)
                elif word==0x4c00012c:acquire_fences+=1
                elif word==0x7c2004ac:release_fences+=1
                elif word==0x7d6b5214:g[11]+=g[10]
                elif typ==14:g[rt]=(g[ra] if ra else 0)+imm
                elif typ==32:g[rt]=read(g[ra]+imm)
                elif typ==36:write(g[ra]+imm,g[rt])
                else:assert word==0x60000000
            assert c['pc']==(first_pcs if worker==first_worker else second_pcs)[slice]
            stops+=int(slice<15)
        def expected_word(offset,value):expected[offset:offset+4]=struct.pack('>I',value)
        expected_word(0x3000,0 if slice in [0,7] or slice>=11 else 1)
        expected_word(0x3080,previous+(2 if slice>=10 else 1 if slice>=5 else 0))
        expected_word(0x3084,final_sum if slice>=10 else first_sum if slice>=5 else previous_sum)
        for worker,c in enumerate(contexts):
            first=worker==first_worker;g=[0xa5a5000000000000+i for i in range(32)]
            g[1]=0x37f90+worker*0x10000;g[5]=0x23000;g[6]=0x20200+transaction*0x100+worker*0x80
            g[7]=1 if not first and 4<=slice<=6 else 0
            if slice>=1:g[8]=0 if slice>=(7 if first else 11) else 1
            g[10]=transaction*2+worker+1;g[13]=0x57060+worker*0x70;g[30]=0x12345678
            if slice>=(4 if first else 9):g[9]=previous+(1 if first else 2);g[11]=first_sum if first else final_sum
            if slice>=(8 if first else 12):g[12]=transaction+1
            assert c['g']==g
            field=(0 if not first and slice in [2,3] else 4 if not first and 4<=slice<=6 else 2)|int(not worker)
            assert c['cr']==((0x8a6c5e79^(transaction<<8)^(worker<<12))&0x0fffffff)|(field<<28)
            active=slice==0 or (not first and (slice==1 or 4<=slice<=7))
            assert c['raddr']==(0x23000 if active else 0)
            out=g[6]-0x20000
            if slice>=(6 if first else 10):
                for offset,value in [(0,previous+(1 if first else 2)),(4,first_sum if first else final_sum),(8,transaction*2+worker+1)]:expected_word(out+offset,value)
            if slice>=(8 if first else 12):expected_pool[0x6c+worker*0x70:0x70+worker*0x70]=struct.pack('>I',transaction+1)
            if slice>=(9 if first else 13):expected_word(out+12,transaction+1)
        assert data==expected and pool==expected_pool,(transaction,slice)
    assert [c['steps'] for c in contexts]==([29,44] if first_worker==0 else [44,29])
    histories.append((read(0x23080),read(0x23084)))
assert histories==[(2,3),(4,10),(6,21)] and read(0x23000)==0
assert instructions==219 and stops==90 and loads==18 and stores==9 and successes==6 and failures==3
assert compares==18 and held==9 and free==9 and lost==3 and acquired==6 and acquire_fences==release_fences==6
assert writes[0x23000]==12 and writes[0x23080]==writes[0x23084]==6
assert writes[0x5006c]==writes[0x500dc]==3
assert all(v==1 for k,v in writes.items() if 0x20200<=k<0x20500)
for text in ['slice < 16','transaction * 16 + slice','slice < 15 ? -2 : 1','program.slices != 48',
    'job.continuation != expected','job.status != expectedStatus','!context.use_full_rdata',
    'context.raddr == job.reservationAddress','context.rtime == job.reservationTime',
    'context.rdata, job.reservationData.data()','slice == 1 || slice == 7']:
    assert text in stage,text
assert stage.count('std::make_unique<named_thread<ppu_thread>>')==2
print('PASS: P65 SHA1='+hashlib.sha1(encoded).hexdigest()+',29words/116bytes,96dispatches/90stops/219instructions; guest lock contention/exclusion/retry/fenced release/handoff, final counter6/checksum21/TLS3/3, exact GPR/CR/PC/partial outputs/guards; P43-P64 preserved')

"""Independent P55 nested guest-call, saved-stack and continuation oracle."""
from pathlib import Path
import ast,hashlib,re,runpy,sys
root=Path(__file__).resolve().parent
runpy.run_path(str(root/'test_p54_fixture.py'))
bridge=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent/'core/loadtest/CoreBridge.cpp'
source=bridge.read_text();start=source.index('int armsx3_core_test_resumed_guest_calls()')
opening=source.index('{',start);end=opening+1;depth=1
while depth:
    depth+=(source[end]=='{')-(source[end]=='}');end+=1
stage=source[start:end]
code=stage.split('const std::array<u32, 41> opcodes{',1)[1].split('};',1)[0]
def dform(op,rt,ra,imm):return(op<<26)|(rt<<21)|(ra<<16)|(imm&0xffff)
ops=[]
for match in re.finditer(r'\b(LI|MTCTR|ADDI|BC|STW|LWZ|ORI|MFLR|MTLR|STDU|STD|LD|B|BLR|NOP)\(([^()]*)\)|\baddPreviousTLS\b',code):
    name,args=match.group(1),match.group(2)
    if name is None:ops.append((31<<26)|(3<<21)|(3<<16)|(8<<11)|(266<<1));continue
    a=[ast.literal_eval(x.strip().replace('false','False').replace('true','True')) for x in args.split(',')] if args else []
    if name=='LI':word=dform(14,a[0],0,a[1])
    elif name in ['MTCTR','MFLR','MTLR']:
        word=(31<<26)|(a[0]<<21)|((9 if name=='MTCTR' else 8)<<16)|((339 if name=='MFLR' else 467)<<1)
    elif name in ['STD','STDU','LD']:
        word=dform(58 if name=='LD' else 62,a[0],a[1],a[2]&~3)|(name=='STDU')
    elif name=='B':
        word=(18<<26)|(a[0]&0x03fffffc)|((a[1] if len(a)>1 else False)<<1)|(a[2] if len(a)>2 else False)
    elif name=='BLR':word=0x4e800020
    elif name=='NOP':word=0x60000000
    else:word=dform({'ADDI':14,'BC':16,'STW':36,'LWZ':32,'ORI':24}[name],*a)
    ops.append(word)
assert len(ops)==41
assert ops==[
    0x7c0802a6,0xf821ff81,0xf8010010,0xf8410018,0x48000031,
    0xe8410018,0x90660008,0xe8010010,0x38210080,0x7c0803a6,0x606a0100,0x48000078,
    0x60000000,0x60000000,0x60000000,0x60000000,
    0x7c0802a6,0xf821ff81,0xf8010010,0xf8410018,0x38402468,0x4800003d,
    0x80ed9000,0x810d900c,0x7c634214,0x906d900c,0x90e60000,0x91060004,
    0xe8410018,0xe8010010,0x38210080,0x7c0803a6,0x4e800020,
    0x60000000,0x60000000,0x60000000,0x38600000,0x7c8903a6,0x38630001,0x4200fffc,0x4e800020]
encoded=b''.join(word.to_bytes(4,'big') for word in ops)
assert len(encoded)==164
pool=bytearray(0x40000)
for slot in range(3):pool[0x60+slot*0x70:0x69+slot*0x70]=b'iOSProbe\0'
expected_pool=pool[:];data=bytearray([0xa5]*0x10000);data[0x80:0x89]=b'iOSProbe\0';expected_data=data[:]
stacks=[bytearray([0xa5]*0x10000) for _ in range(2)];expected_stacks=[stack[:] for stack in stacks]
contexts=[dict(g=[0]*32,ctr=0,pc=0) for _ in range(2)];totals=[0,0];histories=[]
stops=0;instructions=0;stores={};calls=0;returns=0
addresses=[16,144,156,152,160,96,104,112,20,32,40,164]
def memory(addr):
    if 0x50000<=addr<0x90000:return pool,addr-0x50000
    if 0x30000<=addr<0x50000:
        worker=(addr-0x30000)//0x10000;return stacks[worker],addr-(0x30000+worker*0x10000)
    assert 0x20000<=addr<0x30000;return data,addr-0x20000
for transaction in range(3):
    previous=totals[:]
    for worker,c in enumerate(contexts):
        count=17+transaction*3+worker*14;g=c['g'];sp=0x37f90+worker*0x10000
        assert not transaction or g[1]==sp # previous transaction really restored its stack
        g[0]=0xfedc0000;g[1]=sp;g[2]=0x13579000;g[3]=0;g[4]=count
        g[6]=0x20100+transaction*0x40+worker*0x20;g[13]=0x57060+worker*0x70
        g[7]=0x76540000;g[8]=0x87650000;g[9]=0x98760000;g[10]=0xa9870000
        c.update(pc=0,ctr=0,lr=0x12340000,count=count,transaction_steps=0)
    for slice in range(12):
        before=[(c['g'][:],c['ctr'],c['lr'],c['pc']) for c in contexts]
        for c in contexts:c.update(steps=0,budget=[4,7,3,5,2*c['count']-6,3,2,2,5,3,2,8][slice])
        while any(c['pc']<164 and c['steps']<c['budget'] for c in contexts):
            for c in contexts:
                if c['pc']==164 or c['steps']==c['budget']:continue
                assert c['pc'] in range(0,164,4)
                g=c['g'];x=ops[c['pc']//4];old=c['pc'];c['pc']+=4;c['steps']+=1;c['transaction_steps']+=1;instructions+=1
                op=x>>26;rt=(x>>21)&31;ra=(x>>16)&31;imm=(x&0xffff)-0x10000 if x&0x8000 else x&0xffff
                if op==14:g[rt]=(g[ra] if ra else 0)+imm
                elif op==31:
                    if x==0x7c8903a6:c['ctr']=g[4]
                    elif x==0x7c0802a6:g[0]=c['lr']
                    elif x==0x7c0803a6:c['lr']=g[0]
                    else:assert x==0x7c634214;g[3]+=g[8]
                elif op==16:
                    c['ctr']-=1
                    if c['ctr']:c['pc']=old+imm
                elif op==18:
                    displacement=x&0x03fffffc
                    if displacement&0x02000000:displacement-=0x04000000
                    if x&1:c['lr']=0x10000+old+4;calls+=1
                    c['pc']=old+displacement
                elif op==19:
                    assert x==0x4e800020;c['pc']=(c['lr']&~3)-0x10000;returns+=1
                elif op in (32,36,58,62):
                    addr=g[ra]+((imm&~3) if op in (58,62) else imm);block,offset=memory(addr)
                    size=8 if op in (58,62) else 4
                    if op in (32,58):g[rt]=int.from_bytes(block[offset:offset+size],'big')
                    else:
                        block[offset:offset+size]=g[rt].to_bytes(size,'big');stores[addr]=stores.get(addr,0)+1
                        if op==62 and (x&3)==1:g[ra]=addr
                elif op==24:g[ra]=g[rt]|(x&0xffff)
                else:raise AssertionError(op)
        for worker,c in enumerate(contexts):
            g=c['g'];count=c['count'];total=previous[worker]+count;sp=0x37f90+worker*0x10000
            expected_r3=0 if slice<2 else 1 if slice==2 else 3 if slice==3 else count if slice<6 else total
            expected_sp=sp-(128 if slice==0 or slice in [8,9] else 256 if slice<10 else 0)
            expected_lr=0x12340000 if slice==0 or slice>=10 else 0x10058 if slice<8 else 0x10014
            assert c['pc']==addresses[slice] and c['lr']==expected_lr
            assert c['ctr']==(count if slice==2 else count-3 if slice==3 else 0)
            assert [g[i] for i in [0,1,2,3,7,8,9,10]]==[
                0x12340000 if slice==0 or slice>=9 else 0x10014,expected_sp,
                0x13579000 if slice==0 or slice>=8 else 0x2468,expected_r3,
                0x76540000 if slice<5 else 0x694f5350,
                0x87650000 if slice<5 else previous[worker],0x98760000,
                0xa9870000 if slice<11 else total|0x100]
            assert c['steps']==(c['budget'] if slice<11 else 2)
            if slice<11:stops+=1
            else:assert c['transaction_steps']==2*count+32
            def stackword(addr,value):
                offset=addr-(0x30000+worker*0x10000)
                expected_stacks[worker][offset:offset+8]=value.to_bytes(8,'big')
            stackword(sp-128,sp);stackword(sp-128+16,0x12340000);stackword(sp-128+24,0x13579000)
            if slice>=1:
                stackword(sp-256,sp-128);stackword(sp-256+16,0x10014);stackword(sp-256+24,0x13579000)
            if slice>=6:
                offset=0x6c+worker*0x70;expected_pool[offset:offset+4]=total.to_bytes(4,'big')
            if slice>=7:
                offset=0x100+transaction*0x40+worker*0x20
                expected_data[offset:offset+8]=b'iOSP'+previous[worker].to_bytes(4,'big')
            if slice>=9:expected_data[offset+8:offset+12]=total.to_bytes(4,'big')
            for index in [4,5,6,11,12,*range(13,32)]:assert g[index]==before[worker][0][index]
        assert pool==expected_pool and data==expected_data and stacks==expected_stacks
    totals=[previous[i]+contexts[i]['count'] for i in range(2)];histories.append(totals[:])
assert histories==[[17,31],[37,65],[60,102]] and stops==66 and instructions==516 and calls==returns==12
assert stores[0x5006c]==stores[0x500dc]==3
assert sum(count for addr,count in stores.items() if 0x30000<=addr<0x50000)==36
assert sum(count for addr,count in stores.items() if addr<0x30000)==18
assert all(count==1 for addr,count in stores.items() if addr<0x30000)
assert all(c['g'][1]==0x37f90+i*0x10000 and c['g'][2]==0x13579000 and c['lr']==0x12340000 for i,c in enumerate(contexts))
for invariant in ['if (!job.slice)', 'job.resumed = !job.slice || snapshot() == job.continuation;',
    'for (u32 i = 0; i < 32; ++i) values[i] = context.gpr[i];', 'job.continuation = snapshot();',
    'const std::array<u32, 12> budgets{4, 7, 3, 5, job.count * 2 - 6, 3, 2, 2, 5, 3, 2, 8};',
    'for (u32 transaction = 0; transaction < 3; ++transaction)', 'for (u32 slice = 0; slice < 12; ++slice)',
    'const u32 round = transaction * 12 + slice;', 'if (slice >= 6)', 'if (slice >= 7)', 'if (slice >= 9)',
    'if (slice == 11) program.totals[i] = total;', '!job.resumed', 'job.result != (slice < 11 ? -2 : 2)',
    'program.slices != 36', 'program.totals != std::array<u32, 2>{60, 102}',
    'job.completed.store(round + 1, std::memory_order_release)',
    'program.gate.released.store(round + 1, std::memory_order_release)',
    'cpu_thread::g_threads_created.load() != program.created + 2', 'cpu_thread::g_threads_deleted.load() != program.deleted',
    'program.jobs[1].exitAck.load(std::memory_order_acquire) != 1', 'vm::get_super_ptr(pool)',
    'vm::get_super_ptr(0x30000u + i * 0x10000u)', 'vm::temporary_unlock(*owner)',
    'writeExpectedStack(initialSP - 128, initialSP);', 'writeExpectedStack(initialSP - 256, initialSP - 128);',
    'std::memset(vm::base(addresses[2 + i]), 0xa5, 0x10000);']:
    assert invariant in stage,invariant
assert stage.count('std::make_unique<named_thread<ppu_thread>>')==2
assert stage.count('peerTLS = armsx3_ios_ppu_probe_alloc_peer_tls(owner, pool);')==1
assert stage.index('struct Callback {')<stage.index('struct StopOwner {')
assert stage.index('(*peer)(); joined = true;')<stage.index('peerTLS = 0; program.tlsMemory = true;')
assert stage.index('segmentCleanup.release();')<stage.index('vm::dealloc(address, vm::main)')<stage.index('vm::close(); initialized = false;')
print('PASS: P55 41words/164bytes SHA1='+hashlib.sha1(encoded).hexdigest()+', three guest functions/two frames, 72slices/66stops/516instructions; 36stack/6TLS/18output writes, 12calls/returns, all PC/SP/LR/rTOC/registers/partial bytes, final60/102; P43-P54 preserved')

"""Independent P56 nested guest-call, saved-stack and continuation oracle."""
from pathlib import Path
import ast,hashlib,re,runpy,sys,struct
root=Path(__file__).resolve().parent
runpy.run_path(str(root/'test_p55_fixture.py'))
bridge=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent/'core/loadtest/CoreBridge.cpp'
source=bridge.read_text();start=source.index('int armsx3_core_test_resumed_guest_simd()')
opening=source.index('{',start);end=opening+1;depth=1
while depth:
    depth+=(source[end]=='{')-(source[end]=='}');end+=1
stage=source[start:end]
code=stage.split('const std::array<u32, 49> opcodes{',1)[1].split('};',1)[0]
def dform(op,rt,ra,imm):return(op<<26)|(rt<<21)|(ra<<16)|(imm&0xffff)
ops=[]
for match in re.finditer(r'\b(LI|MTCTR|ADDI|BC|STW|LWZ|ORI|MFLR|MTLR|STDU|STD|LD|B|BLR|NOP|LFD|STFD|LVX|STVX)\(([^()]*)\)|\b(addPreviousTLS|addDouble|xorVector)\b',code):
    name,args=match.group(1),match.group(2)
    if name is None:
        ops.append({'addPreviousTLS':(31<<26)|(3<<21)|(3<<16)|(8<<11)|(266<<1),
            'addDouble':(63<<26)|(3<<21)|(1<<16)|(2<<11)|(21<<1),
            'xorVector':(4<<26)|(3<<21)|(1<<16)|(2<<11)|0x4c4}[match.group(3)]);continue
    a=[ast.literal_eval(x.strip().replace('false','False').replace('true','True')) for x in args.split(',')] if args else []
    if name=='LI':word=dform(14,a[0],0,a[1])
    elif name in ['MTCTR','MFLR','MTLR']:
        word=(31<<26)|(a[0]<<21)|((9 if name=='MTCTR' else 8)<<16)|((339 if name=='MFLR' else 467)<<1)
    elif name in ['STD','STDU','LD']:
        word=dform(58 if name=='LD' else 62,a[0],a[1],a[2]&~3)|(name=='STDU')
    elif name in ['LVX','STVX']:
        word=(31<<26)|(a[0]<<21)|(a[1]<<16)|(a[2]<<11)|((103 if name=='LVX' else 231)<<1)
    elif name in ['LFD','STFD']:word=dform(50 if name=='LFD' else 54,*a)
    elif name=='B':
        word=(18<<26)|(a[0]&0x03fffffc)|((a[1] if len(a)>1 else False)<<1)|(a[2] if len(a)>2 else False)
    elif name=='BLR':word=0x4e800020
    elif name=='NOP':word=0x60000000
    else:word=dform({'ADDI':14,'BC':16,'STW':36,'LWZ':32,'ORI':24}[name],*a)
    ops.append(word)
assert 'const u32 addDouble = (63u << 26) | (3u << 21) | (1u << 16) | (2u << 11) | (21u << 1);' in stage
assert 'const u32 xorVector = (4u << 26) | (3u << 21) | (1u << 16) | (2u << 11) | 0x4c4u;' in stage
assert len(ops)==49
assert ops==[
    0x7c0802a6,0xf821ff81,0xf8010010,0xf8410018,0x48000031,
    0xe8410018,0x90660008,0xe8010010,0x38210080,0x7c0803a6,0x606a0100,0x48000098,
    0x60000000,0x60000000,0x60000000,0x60000000,
    0x7c0802a6,0xf821ff81,0xf8010010,0xf8410018,0x38402468,0x4800003d,
    0x80ed9000,0x810d900c,0x7c634214,0x906d900c,0x90e60000,0x91060004,
    0xe8410018,0xe8010010,0x38210080,0x7c0803a6,0x4e800020,
    0x60000000,0x60000000,0x60000000,0x38600000,0x7c8903a6,0x38630001,0x4200fffc,0xc8260040,0xc8460048,0xfc61102a,0xd8660010,
    0x7c2628ce,0x7c4658ce,0x106114c4,0x7c6661ce,0x4e800020]
encoded=b''.join(word.to_bytes(4,'big') for word in ops)
assert len(encoded)==196
pool=bytearray(0x40000)
for slot in range(3):pool[0x60+slot*0x70:0x69+slot*0x70]=b'iOSProbe\0'
expected_pool=pool[:];data=bytearray([0xa5]*0x10000);data[0x80:0x89]=b'iOSProbe\0'
for transaction in range(3):
    for worker in range(2):
        offset=0x200+transaction*0x100+worker*0x80
        left=1.5+transaction*0.5+worker*2.0;right=2.25+transaction*0.25+worker*4.0
        data[offset+64:offset+80]=struct.pack('>dd',left,right)
        data[offset+80:offset+96]=bytes((0x10+transaction*17+worker*53+byte*3)&255 for byte in range(16))
        data[offset+96:offset+112]=bytes((0xe1-transaction*11-worker*29-byte*5)&255 for byte in range(16))
expected_data=data[:]
stacks=[bytearray([0xa5]*0x10000) for _ in range(2)];expected_stacks=[stack[:] for stack in stacks]
contexts=[dict(g=[0]*32,ctr=0,pc=0) for _ in range(2)];totals=[0,0];histories=[]
stops=0;instructions=0;stores={};calls=0;returns=0;fp_loads=fp_stores=fp_adds=vec_loads=vec_stores=vec_xors=0
addresses=[16,144,156,152,160,168,172,176,184,188,192,96,104,112,20,32,40,196]
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
        g[5]=80;g[11]=96;g[12]=32;g[6]=0x20200+transaction*0x100+worker*0x80;g[13]=0x57060+worker*0x70
        g[7]=0x76540000;g[8]=0x87650000;g[9]=0x98760000;g[10]=0xa9870000
        c.update(pc=0,ctr=0,lr=0x12340000,count=count,transaction_steps=0,f=[7.0]*32,v=[bytes([0x3c]*16) for _ in range(32)])
    for slice in range(18):
        before=[(c['g'][:],c['ctr'],c['lr'],c['pc'],c['f'][:],c['v'][:]) for c in contexts]
        for c in contexts:c.update(steps=0,budget=[4,7,3,5,2*c['count']-6,2,1,1,2,1,1,3,2,2,5,3,2,8][slice])
        while any(c['pc']<196 and c['steps']<c['budget'] for c in contexts):
            for c in contexts:
                if c['pc']==196 or c['steps']==c['budget']:continue
                assert c['pc'] in range(0,196,4)
                g=c['g'];x=ops[c['pc']//4];old=c['pc'];c['pc']+=4;c['steps']+=1;c['transaction_steps']+=1;instructions+=1
                op=x>>26;rt=(x>>21)&31;ra=(x>>16)&31;imm=(x&0xffff)-0x10000 if x&0x8000 else x&0xffff
                if op==14:g[rt]=(g[ra] if ra else 0)+imm
                elif op in (50,54):
                    addr=g[ra]+imm;block,offset=memory(addr)
                    if op==50:c['f'][rt]=struct.unpack('>d',block[offset:offset+8])[0];fp_loads+=1
                    else:
                        block[offset:offset+8]=struct.pack('>d',c['f'][rt]);stores[addr]=stores.get(addr,0)+1;fp_stores+=1
                elif op==63:
                    assert x==0xfc61102a;c['f'][3]=c['f'][1]+c['f'][2];fp_adds+=1
                elif op==4:
                    assert x==0x106114c4;c['v'][3]=bytes(a^b for a,b in zip(c['v'][1],c['v'][2]));vec_xors+=1
                elif op==31:
                    if (x&0x7fe) in (103<<1,231<<1):
                        addr=(g[ra]+g[(x>>11)&31])&~15;block,offset=memory(addr)
                        if (x&0x7fe)==103<<1:c['v'][rt]=bytes(block[offset:offset+16]);vec_loads+=1
                        else:
                            block[offset:offset+16]=c['v'][rt];stores[addr]=stores.get(addr,0)+1;vec_stores+=1
                    elif x==0x7c8903a6:c['ctr']=g[4]
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
            expected_r3=0 if slice<2 else 1 if slice==2 else 3 if slice==3 else count if slice<12 else total
            expected_sp=sp-(128 if slice==0 or slice in [14,15] else 256 if slice<16 else 0)
            expected_lr=0x12340000 if slice==0 or slice>=16 else 0x10058 if slice<14 else 0x10014
            assert c['pc']==addresses[slice] and c['lr']==expected_lr
            assert c['ctr']==(count if slice==2 else count-3 if slice==3 else 0)
            assert [g[i] for i in [0,1,2,3,7,8,9,10]]==[
                0x12340000 if slice==0 or slice>=15 else 0x10014,expected_sp,
                0x13579000 if slice==0 or slice>=14 else 0x2468,expected_r3,
                0x76540000 if slice<11 else 0x694f5350,
                0x87650000 if slice<11 else previous[worker],0x98760000,
                0xa9870000 if slice<17 else total|0x100]
            left=1.5+transaction*0.5+worker*2.0;right=2.25+transaction*0.25+worker*4.0;sum_value=left+right
            for reg in range(32):
                expected=left if reg==1 and slice>=5 else right if reg==2 and slice>=5 else sum_value if reg==3 and slice>=6 else 7.0
                assert struct.pack('>d',c['f'][reg])==struct.pack('>d',expected)
            output=g[6]-0x20000;vector_a=bytes(expected_data[output+80:output+96]);vector_b=bytes(expected_data[output+96:output+112])
            vector_result=bytes(a^b for a,b in zip(vector_a,vector_b))
            for reg in range(32):
                expected=vector_a if reg==1 and slice>=8 else vector_b if reg==2 and slice>=8 else vector_result if reg==3 and slice>=9 else bytes([0x3c]*16)
                assert c['v'][reg]==expected
            if slice>=7:expected_data[output+16:output+24]=struct.pack('>d',sum_value)
            if slice>=10:expected_data[output+32:output+48]=vector_result
            assert c['steps']==(c['budget'] if slice<17 else 2)
            if slice<17:stops+=1
            else:assert c['transaction_steps']==2*count+40
            def stackword(addr,value):
                offset=addr-(0x30000+worker*0x10000)
                expected_stacks[worker][offset:offset+8]=value.to_bytes(8,'big')
            stackword(sp-128,sp);stackword(sp-128+16,0x12340000);stackword(sp-128+24,0x13579000)
            if slice>=1:
                stackword(sp-256,sp-128);stackword(sp-256+16,0x10014);stackword(sp-256+24,0x13579000)
            if slice>=12:
                offset=0x6c+worker*0x70;expected_pool[offset:offset+4]=total.to_bytes(4,'big')
            if slice>=13:
                offset=0x200+transaction*0x100+worker*0x80
                expected_data[offset:offset+8]=b'iOSP'+previous[worker].to_bytes(4,'big')
            if slice>=15:expected_data[offset+8:offset+12]=total.to_bytes(4,'big')
            for index in [4,5,6,11,12,*range(13,32)]:assert g[index]==before[worker][0][index]
        assert pool==expected_pool and data==expected_data and stacks==expected_stacks
    totals=[previous[i]+contexts[i]['count'] for i in range(2)];histories.append(totals[:])
assert histories==[[17,31],[37,65],[60,102]] and stops==102 and instructions==564 and calls==returns==12
assert stores[0x5006c]==stores[0x500dc]==3
assert sum(count for addr,count in stores.items() if 0x30000<=addr<0x50000)==36
assert sum(count for addr,count in stores.items() if addr<0x30000)==30
assert fp_loads==vec_loads==12 and fp_adds==fp_stores==vec_xors==vec_stores==6
assert all(count==1 for addr,count in stores.items() if addr<0x30000)
assert all(c['g'][1]==0x37f90+i*0x10000 and c['g'][2]==0x13579000 and c['lr']==0x12340000 for i,c in enumerate(contexts))
for invariant in ['if (!job.slice)', 'job.resumed = !job.slice || (snapshot() == job.continuation &&',
    'for (u32 i = 0; i < 32; ++i) values[i] = context.gpr[i];', 'job.continuation = snapshot();',
    'const std::array<u32, 18> budgets{4, 7, 3, 5, job.count * 2 - 6, 2, 1, 1, 2, 1, 1, 3, 2, 2, 5, 3, 2, 8};',
    'for (u32 transaction = 0; transaction < 3; ++transaction)', 'for (u32 slice = 0; slice < 18; ++slice)',
    'const u32 round = transaction * 18 + slice;', 'if (slice >= 12)', 'if (slice >= 13)', 'if (slice >= 15)', 'if (slice >= 7)', 'if (slice >= 10)',
    'if (slice == 17) program.totals[i] = total;', '!job.resumed', 'job.result != (slice < 17 ? -2 : 2)',
    'program.slices != 54', 'program.totals != std::array<u32, 2>{60, 102}',
    'job.completed.store(round + 1, std::memory_order_release)',
    'program.gate.released.store(round + 1, std::memory_order_release)',
    'cpu_thread::g_threads_created.load() != program.created + 2', 'cpu_thread::g_threads_deleted.load() != program.deleted',
    'program.jobs[1].exitAck.load(std::memory_order_acquire) != 1', 'vm::get_super_ptr(pool)',
    'vm::get_super_ptr(0x30000u + i * 0x10000u)', 'vm::temporary_unlock(*owner)',
    'writeExpectedStack(initialSP - 128, initialSP);', 'writeExpectedStack(initialSP - 256, initialSP - 128);',
    'std::memset(vm::base(addresses[2 + i]), 0xa5, 0x10000);',
    'std::memcmp(context.fpr, job.floating.data(), sizeof(context.fpr))',
    'std::memcmp(context.vr, job.vectors.data(), sizeof(context.vr))',
    'std::memcpy(job.floating.data(), context.fpr, sizeof(context.fpr));',
    'std::memcpy(job.vectors.data(), context.vr, sizeof(context.vr));',
    'const be_t<v128> value = context.vr[i + 1];', 'for (auto& value : context.fpr) value = 7.0;',
    'std::memset(context.vr, 0x3c, sizeof(context.vr));']:
    assert invariant in stage,invariant
assert stage.count('std::make_unique<named_thread<ppu_thread>>')==2
assert stage.count('peerTLS = armsx3_ios_ppu_probe_alloc_peer_tls(owner, pool);')==1
assert stage.index('struct Callback {')<stage.index('struct StopOwner {')
assert stage.index('(*peer)(); joined = true;')<stage.index('peerTLS = 0; program.tlsMemory = true;')
assert stage.index('segmentCleanup.release();')<stage.index('vm::dealloc(address, vm::main)')<stage.index('vm::close(); initialized = false;')
print('PASS: P56 49words/196bytes SHA1='+hashlib.sha1(encoded).hexdigest()+', interleaved retained GPR/FPR/VR contexts through 108slices/102stops/564instructions; exact double/vector results and deferred bytes/canaries, all PC/SP/LR/rTOC/CTR and stack/TLS states, final60/102; P43-P55 preserved')

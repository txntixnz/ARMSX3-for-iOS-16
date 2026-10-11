"""Independent P54 persistent shared TLS execution/outcomes; P43-P52 preserved."""
from pathlib import Path
import ast,re,runpy,sys
root=Path(__file__).resolve().parent
runpy.run_path(str(root/'test_p53_fixture.py'))
bridge=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent/'core/loadtest/CoreBridge.cpp'
source=bridge.read_text();start=source.index('int armsx3_core_test_resumed_guest_tls()')
opening=source.index('{',start);end=opening+1;depth=1
while depth:
    depth+=(source[end]=='{')-(source[end]=='}');end+=1
stage=source[start:end]
code=stage.split('const std::array<u32, 13> opcodes{',1)[1].split('};',1)[0]
def form(op,rt,ra,imm):return(op<<26)|(rt<<21)|(ra<<16)|(imm&0xffff)
ops=[]
# The core exposes no ADD encoder: independently encode its X-form instruction.
for match in re.finditer(r'\b(LI|MTCTR|ADDI|BC|STW|LWZ|ORI)\(([^()]*)\)|\baddPreviousTLS\b',code):
    name,args=match.group(1),match.group(2)
    if name is None:ops.append((31<<26)|(3<<21)|(3<<16)|(8<<11)|(266<<1));continue
    a=[ast.literal_eval(x.strip()) for x in args.split(',')]
    if name=='LI':ops.append(form(14,a[0],0,a[1]))
    elif name=='MTCTR':ops.append((31<<26)|(a[0]<<21)|(9<<16)|(467<<1))
    else:ops.append(form({'ADDI':14,'BC':16,'STW':36,'LWZ':32,'ORI':24}[name],*a))
assert ops==[0x38600000,0x7c8903a6,0x38630001,0x4200fffc,0x80ed9000,0x810d900c,
             0x7c634214,0x906d900c,0x812d900c,0x90e60000,0x91060004,0x91260008,0x612a0100]
assert 'const u32 addPreviousTLS = (31u << 26) | (3u << 21) | (3u << 16) | (8u << 11) | (266u << 1);' in stage

pool=bytearray(0x40000)
for slot in range(3):pool[0x60+slot*0x70:0x69+slot*0x70]=b'iOSProbe\0'
expected_pool=pool[:];data=bytearray([0xa5]*0x10000);data[0x80:0x89]=b'iOSProbe\0';expected_data=data[:]
contexts=[dict(g=[0]*32,ctr=0,pc=0) for _ in range(2)];totals=[0,0];histories=[];stops=0;stores={};instructions=0
addresses=[12,8,16,24,28,32,36,48,52]
def memory(addr):
    if 0x50000<=addr<0x90000:return pool,addr-0x50000
    assert 0x20000<=addr<0x30000;return data,addr-0x20000
for transaction in range(3):
    previous=totals[:]
    for worker,c in enumerate(contexts):
        count=17+transaction*3+worker*14;g=c['g']
        g[4]=count;g[6]=0x20100+transaction*0x40+worker*0x20;g[13]=0x57060+worker*0x70
        g[7]=0x76540000;g[8]=0x87650000;g[9]=0x98760000;g[10]=0xa9870000
        c.update(pc=0,ctr=0,count=count,transaction_steps=0)
    for slice in range(9):
        before=[(c['g'][:],c['ctr'],c['pc']) for c in contexts]
        for c in contexts:c.update(steps=0,budget=[3,5,2*c['count']-6,2,1,1,1,3,4][slice])
        while any(c['pc']<52 and c['steps']<c['budget'] for c in contexts):
            for c in contexts:
                if c['pc']==52 or c['steps']==c['budget']:continue
                g=c['g'];x=ops[c['pc']//4];old=c['pc'];c['pc']+=4;c['steps']+=1;c['transaction_steps']+=1;instructions+=1
                op=x>>26;rt=(x>>21)&31;ra=(x>>16)&31;imm=(x&0xffff)-0x10000 if x&0x8000 else x&0xffff
                if op==14:g[rt]=(g[ra] if ra else 0)+imm
                elif op==31:
                    if x==0x7c8903a6:c['ctr']=g[4]
                    else:assert x==0x7c634214;g[rt]=g[ra]+g[(x>>11)&31]
                elif op==16:
                    c['ctr']-=1
                    if c['ctr']:c['pc']=old+imm
                elif op in (32,36):
                    addr=g[ra]+imm;block,offset=memory(addr)
                    if op==32:g[rt]=int.from_bytes(block[offset:offset+4],'big')
                    else:
                        block[offset:offset+4]=g[rt].to_bytes(4,'big');stores[addr]=stores.get(addr,0)+1
                elif op==24:g[ra]=g[rt]|(x&0xffff)
                else:raise AssertionError(op)
        for worker,c in enumerate(contexts):
            g=c['g'];count=c['count'];total=previous[worker]+count
            expected_r3=1 if slice==0 else 3 if slice==1 else count if slice<4 else total
            assert c['pc']==addresses[slice] and c['ctr']==(count if slice==0 else count-3 if slice==1 else 0)
            assert g[3]==expected_r3
            assert [g[i] for i in [7,8,9,10]]==[0x76540000 if slice<3 else 0x694f5350,
                0x87650000 if slice<3 else previous[worker],0x98760000 if slice<6 else total,
                0xa9870000 if slice<8 else total|0x100]
            assert c['steps']==(c['budget'] if slice<8 else 1)
            if slice<8:stops+=1
            else:assert c['transaction_steps']==2*count+11
            if slice>=5:
                offset=0x6c+worker*0x70;expected_pool[offset:offset+4]=total.to_bytes(4,'big')
            if slice>=7:
                offset=0x100+transaction*0x40+worker*0x20
                expected_data[offset:offset+12]=b'iOSP'+previous[worker].to_bytes(4,'big')+total.to_bytes(4,'big')
            # Each pause has a fixed exact output boundary. Inputs/tls_addr and
            # unused registers never change; no cold reset between slices.
            for index in [0,1,2,4,5,6,11,12,*range(13,32)]:assert g[index]==before[worker][0][index]
        assert pool==expected_pool and data==expected_data
    totals=[previous[i]+contexts[i]['count'] for i in range(2)];histories.append(totals[:])
assert histories==[[17,31],[37,65],[60,102]] and stops==48 and instructions==390
assert stores[0x5006c]==stores[0x500dc]==3
assert len(stores)==20 and sum(stores.values())==24
assert all(count==1 for addr,count in stores.items() if addr<0x50000)
for invariant in ['if (!job.slice)', 'job.resumed = !job.slice || snapshot() == job.continuation;',
    'for (u32 i = 0; i < 32; ++i) values[i] = context.gpr[i];',
    'job.continuation = snapshot();', 'if (!job.resumed) { job.result = -8; return; }',
    'const std::array<u32, 9> budgets{3, 5, job.count * 2 - 6, 2, 1, 1, 1, 3, 4};',
    'for (u32 transaction = 0; transaction < 3; ++transaction)', 'for (u32 slice = 0; slice < 9; ++slice)',
    'const u32 round = transaction * 9 + slice;', 'if (slice >= 5)', 'if (slice >= 7)',
    'if (slice == 8) program.totals[i] = total;', '!job.resumed', 'job.result != (slice < 8 ? -2 : 1)',
    'program.slices != 27', 'program.totals != std::array<u32, 2>{60, 102}',
    'job.completed.store(round + 1, std::memory_order_release)',
    'program.gate.released.store(round + 1, std::memory_order_release)',
    'cpu_thread::g_threads_created.load() != program.created + 2',
    'cpu_thread::g_threads_deleted.load() != program.deleted',
    'program.jobs[1].exitAck.load(std::memory_order_acquire) != 1',
    'vm::get_super_ptr(pool)', 'vm::temporary_unlock(*owner)']:
    assert invariant in stage,invariant
assert stage.count('std::make_unique<named_thread<ppu_thread>>')==2
assert stage.count('peerTLS = armsx3_ios_ppu_probe_alloc_peer_tls(owner, pool);')==1
assert stage.index('struct Callback {')<stage.index('struct StopOwner {')
assert stage.index('(*peer)(); joined = true;')<stage.index('peerTLS = 0; program.tlsMemory = true;')
assert stage.index('segmentCleanup.release();')<stage.index('vm::dealloc(address, vm::main)')<stage.index('vm::close(); initialized = false;')
print('PASS: P54 independently encoded13words/52bytes, retained/interleaved contexts; 54 slices/48 stops/390instructions, exact PCs/registers/memory at all boundaries, six TLS writes18 deferred output writes, totals60/102; P43-P53 preserved')

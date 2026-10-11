"""Independent P53 persistent shared TLS execution/outcomes; P43-P52 preserved."""
from pathlib import Path
import ast,re,runpy,sys
root=Path(__file__).resolve().parent
runpy.run_path(str(root/'test_p52_fixture.py'))
bridge=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent/'core/loadtest/CoreBridge.cpp'
source=bridge.read_text();start=source.index('int armsx3_core_test_persistent_guest_tls()')
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
# Same address space and same two contexts survive all batches. TLS and output
# bytes persist; one instruction per worker per iteration interleaves the jobs.
pool=bytearray(0x40000)
for slot in range(3):pool[0x60+slot*0x70:0x69+slot*0x70]=b'iOSProbe\0'
expected_pool=pool[:];data=bytearray([0xa5]*0x10000);data[0x80:0x89]=b'iOSProbe\0';expected_data=data[:]
contexts=[dict(g=[0]*32) for _ in range(2)];totals=[0,0];outcomes=[];histories=[];recoveries=[];last=[None,None]
def memory(addr):
    if 0x50000<=addr<0x90000:return pool,addr-0x50000
    assert 0x20000<=addr<0x30000;return data,addr-0x20000
for batch in range(8):
    previous=totals[:]
    for worker,c in enumerate(contexts):
        count=17+batch*3+worker*14;budget=8 if (batch%4,worker) in [(1,0),(2,1)] else 128
        g=c['g'];g[4]=count;g[6]=0x20100+batch*0x40+worker*0x20;g[13]=0x57060+worker*0x70
        g[7]=0x76540000;g[8]=0x87650000;g[9]=0x98760000;g[10]=0xa9870000
        c.update(pc=0,ctr=0,steps=0,budget=budget,count=count)
    while any(c['pc']<52 and c['steps']<c['budget'] for c in contexts):
        for c in contexts:
            if c['pc']==52 or c['steps']==c['budget']:continue
            g=c['g'];x=ops[c['pc']//4];old=c['pc'];c['pc']+=4;c['steps']+=1
            op=x>>26;rt=(x>>21)&31;ra=(x>>16)&31;imm=(x&0xffff)-0x10000 if x&0x8000 else x&0xffff
            if op==14:g[rt]=(g[ra] if ra else 0)+imm
            elif op==31:
                if x==0x7c8903a6:c['ctr']=g[4]
                else:assert x==0x7c634214;g[rt]=g[ra]+g[(x>>11)&31]
            elif op==16:
                c['ctr']-=1
                if c['ctr']:c['pc']=old+imm
            elif op in (32,36):
                block,offset=memory(g[ra]+imm)
                if op==32:g[rt]=int.from_bytes(block[offset:offset+4],'big')
                else:block[offset:offset+4]=g[rt].to_bytes(4,'big')
            elif op==24:g[ra]=g[rt]|(x&0xffff)
            else:raise AssertionError(op)
    results=[]
    for worker,c in enumerate(contexts):
        g=c['g'];count=c['count'];limited=c['budget']==8;total=previous[worker]+(0 if limited else count)
        assert (c['pc'],c['steps'],g[3],c['ctr'])==((8,8,3,count-3) if limited else (52,count*2+11,total,0))
        assert [g[i] for i in [7,8,9,10]]==([0x76540000,0x87650000,0x98760000,0xa9870000] if limited else [0x694f5350,previous[worker],total,total|0x100])
        if not limited:
            offset=0x6c+worker*0x70;expected_pool[offset:offset+4]=total.to_bytes(4,'big')
            offset=0x100+batch*0x40+worker*0x20
            expected_data[offset:offset+12]=b'iOSP'+previous[worker].to_bytes(4,'big')+total.to_bytes(4,'big')
        result=-2 if limited else c['steps']
        if last[worker]==-2 and result>0:recoveries.append((batch,worker))
        last[worker]=result;results.append(result);totals[worker]=total
    assert pool==expected_pool and data==expected_data
    outcomes.append(results);histories.append(totals[:])
assert outcomes==[[45,73],[-2,79],[57,-2],[63,91],[69,97],[-2,103],[81,-2],[87,115]]
assert histories==[[17,31],[17,65],[40,65],[66,105],[95,148],[95,194],[130,194],[168,246]]
assert recoveries==[(2,0),(3,1),(6,0),(7,1)]
for invariant in ['job.ready.store(round + 1, std::memory_order_release)',
    'job.completed.store(round + 1, std::memory_order_release)', 'program.gate.released.store(round + 1, std::memory_order_release)',
    'const auto previous = program.totals;', 'program.totals[i] = total;',
    'cpu_thread::g_threads_created.load() != program.created + 2', 'cpu_thread::g_threads_deleted.load() != program.deleted',
    'callback.program->jobs[1].exitAck.fetch_add(1, std::memory_order_release)',
    'program.jobs[1].exitAck.load(std::memory_order_acquire) != 1', 'program.totals != std::array<u32, 2>{168, 246}',
    'vm::temporary_unlock(*owner)', 'vm::get_super_ptr(pool)', 'program.expectedData->data()']:
    assert invariant in stage,invariant
assert stage.count('std::make_unique<named_thread<ppu_thread>>')==2
assert stage.count('peerTLS = armsx3_ios_ppu_probe_alloc_peer_tls(owner, pool);')==1
assert stage.index('struct Callback {')<stage.index('struct StopOwner {')
assert stage.index('std::make_unique<named_thread<ppu_thread>>',stage.index('peerTLS = armsx3_ios_ppu_probe_alloc_peer_tls'))<stage.index('for (u32 round = 0; round < 8; ++round)')
assert stage.index('(*peer)(); joined = true;')<stage.index('peerTLS = 0; program.tlsMemory = true;')
assert stage.index('segmentCleanup.release();')<stage.index('vm::dealloc(address, vm::main)')<stage.index('vm::close(); initialized = false;')
print('PASS: P53 13 opcodes/52bytes, retained contexts/pool, interleaved previous TLS reads and totals168/246, all eight results/PCs/steps/bytes and four stop/recovery sequences; lifecycle/snapshots/queue/join-before-free; P43-P52 preserved')

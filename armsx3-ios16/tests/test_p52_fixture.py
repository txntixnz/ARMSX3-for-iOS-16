"""Independent P52 paired TLS guest code and memory outcomes; preserve P43-P51 checks."""
from pathlib import Path
import ast,re,runpy,sys
root=Path(__file__).resolve().parent
runpy.run_path(str(root/'test_p51_fixture.py'))
bridge=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent/'core/loadtest/CoreBridge.cpp'
source=bridge.read_text();stage=source.split('int armsx3_core_test_paired_guest_tls()',1)[1]
code=stage.split('const std::array<u32, 12> opcodes{',1)[1].split('};',1)[0]
def form(op,rt,ra,imm):return(op<<26)|(rt<<21)|(ra<<16)|(imm&0xffff)
ops=[]
for name,args in re.findall(r'\b(LI|MTCTR|ADDI|BC|STW|LWZ|ORI)\(([^()]*)\)',code):
    a=[ast.literal_eval(x.strip()) for x in args.split(',')]
    if name=='LI':ops.append(form(14,a[0],0,a[1]))
    elif name=='MTCTR':ops.append((31<<26)|(a[0]<<21)|(9<<16)|(467<<1))
    else:ops.append(form({'ADDI':14,'BC':16,'STW':36,'LWZ':32,'ORI':24}[name],*a))
assert ops==[0x38600000,0x7c8903a6,0x38630001,0x4200fffc,0x80ed9000,0x810d900c,
             0x906d900c,0x812d900c,0x90e60000,0x91060004,0x91260008,0x612a0100]
# An independent shared address space models both TLS slots. Alternate one guest
# instruction per context; inspect every byte of pool/data after each pair.
outcomes=[]
for round in range(4):
    pool=bytearray(0x40000)
    for slot in range(3):pool[0x60+slot*0x70:0x69+slot*0x70]=b'iOSProbe\0'
    expected_pool=pool[:];data=bytearray([0xa5]*0x10000);data[0x80:0x89]=b'iOSProbe\0';expected_data=data[:]
    contexts=[]
    for worker in range(2):
        count=17+round*3+worker*14;budget=8 if (round,worker) in [(1,0),(2,1)] else 128
        g=[0]*32;g[4]=count;g[6]=0x20100+worker*0x100;g[13]=0x57060+worker*0x70
        g[7]=0x76540000;g[8]=0x87650000;g[9]=0x98760000;g[10]=0xa9870000
        contexts.append(dict(g=g,pc=0,ctr=0,steps=0,budget=budget,count=count))
    def memory(addr,size):
        if 0x50000<=addr<0x90000:return pool,addr-0x50000
        assert 0x20000<=addr<0x30000;return data,addr-0x20000
    while any(c['pc']<48 and c['steps']<c['budget'] for c in contexts):
        for c in contexts:
            if c['pc']==48 or c['steps']==c['budget']:continue
            g=c['g'];x=ops[c['pc']//4];old=c['pc'];c['pc']+=4;c['steps']+=1
            op=x>>26;rt=(x>>21)&31;ra=(x>>16)&31;imm=(x&0xffff)-0x10000 if x&0x8000 else x&0xffff
            if op==14:g[rt]=(g[ra] if ra else 0)+imm
            elif op==31:c['ctr']=g[4]
            elif op==16:
                c['ctr']-=1
                if c['ctr']:c['pc']=old+imm
            elif op in (32,36):
                block,offset=memory(g[ra]+imm,4)
                if op==32:g[rt]=int.from_bytes(block[offset:offset+4],'big')
                else:block[offset:offset+4]=g[rt].to_bytes(4,'big')
            elif op==24:g[ra]=g[rt]|(x&0xffff)
            else:raise AssertionError(op)
    results=[]
    for worker,c in enumerate(contexts):
        g=c['g'];count=c['count'];limited=c['budget']==8
        assert (c['pc'],c['steps'],g[3],c['ctr'])==((8,8,3,count-3) if limited else (48,count*2+10,count,0))
        assert [g[i] for i in [7,8,9,10]]==([0x76540000,0x87650000,0x98760000,0xa9870000] if limited else [0x694f5350,0,count,count|0x100])
        if not limited:
            offset=0x6c+worker*0x70;expected_pool[offset:offset+4]=count.to_bytes(4,'big')
            offset=0x100+worker*0x100;expected_data[offset:offset+12]=b'iOSP'+bytes(4)+count.to_bytes(4,'big')
        results.append(-2 if limited else c['steps'])
    assert pool==expected_pool and data==expected_data
    outcomes.append(results)
assert outcomes==[[44,72],[-2,78],[56,-2],[62,90]]
for invariant in ['vm::reserve_map(vm::main, 0x10000, 0x80000)', 'vm::get_super_ptr(pool)',
    'static_cast<vm::addr_t>(0x40000), 0x8000, peerTLS', 'armsx3_ios_live_cpu_threads() != 2',
    'program.gate.go.store(true, std::memory_order_release)', 'vm::temporary_unlock(*owner)',
    'job.completed.store(true, std::memory_order_release)', 'peerTLS = 0; program.tlsMemory = true;',
    'cpu_thread::g_threads_created.load() != created + 2', 'cpu_thread::g_threads_deleted.load() != deleted + 2']:
    assert invariant in stage,invariant
assert stage.index('struct Callback {')<stage.index('struct StopOwner {')
assert stage.index('cleanup.join();')<stage.index('std::vector<u8> expectedPool')<stage.index('peerTLS = 0; program.tlsMemory = true;')
assert stage.index('segmentCleanup.release();')<stage.index('vm::dealloc(address, vm::main)')<stage.index('vm::close(); initialized = false;')
patch=(root.parent/'patches/0047-ios-paired-guest-tls-slots.patch').read_text()
for guard in ['armsx3_ios_live_cpu_threads() == 1', 's_tls_map[0]', 's_tls_map[1] || s_tls_map[2]',
    'const u32 slot = ppu_alloc_tls()', 'ppu_free_tls(tls - 0x7030u)', 'tls != pool + 0x70d0u']:
    assert guard in patch,guard
print('PASS: P52 12 opcodes/48bytes, interleaved paired guest r13 reads/writes, four results/steps/PCs and partial limits, whole pool/data and disjoint slots, constructor TLS/join-before-free/guard invariants; P43-P51 preserved')

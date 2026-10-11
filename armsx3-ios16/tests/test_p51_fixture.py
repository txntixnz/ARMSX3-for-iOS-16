"""Independent P51 encoding and 16 persistent-job outcomes; retain P43-P50 checks."""
from pathlib import Path
import ast,re,runpy,sys
root=Path(__file__).resolve().parent
runpy.run_path(str(root/'test_p50_fixture.py'))
bridge=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent/'core/loadtest/CoreBridge.cpp'
source=bridge.read_text();start=source.index('int armsx3_core_test_persistent_ppu_pair()')
opening=source.index('{',start);end=opening+1;depth=1
while depth:
    depth+=(source[end]=='{')-(source[end]=='}');end+=1
stage=source[start:end] # Later diagnostics must not affect P51's construction count.
code=stage.split('const std::array<u32, 7> opcodes{',1)[1].split('};',1)[0]
def form(op,rt,ra,imm):return(op<<26)|(rt<<21)|(ra<<16)|(imm&0xffff)
ops=[]
for name,args in re.findall(r'\b(LI|MTCTR|ADDI|BC|STW|LWZ|ORI)\(([^()]*)\)',code):
    a=[ast.literal_eval(x.strip()) for x in args.split(',')]
    if name=='LI':ops.append(form(14,a[0],0,a[1]))
    elif name=='MTCTR':ops.append((31<<26)|(a[0]<<21)|(9<<16)|(467<<1))
    else:ops.append(form({'ADDI':14,'BC':16,'STW':36,'LWZ':32,'ORI':24}[name],*a))
assert ops==[0x38600000,0x7c8903a6,0x38630001,0x4200fffc,0x90660000,0x80e60000,0x60e80100]
# Keep the same two contexts across all jobs, but initialize each job's inputs.
# Each output slot belongs to one job; exhaustion must leave it and earlier slots intact.
contexts=[[0]*32 for _ in range(2)];memory=bytearray([0xa5]*0x10000);expected=memory[:]
outcomes=[];recoveries=[];previous=[None,None]
for batch in range(8):
    results=[]
    for worker,g in enumerate(contexts):
        count=17+batch*3+worker*14;limited=(batch%4,worker) in [(1,0),(2,1)];budget=8 if limited else 128
        output=0x100+batch*0x20+worker*4
        g[2]=0x13579000+worker;g[4]=count;g[6]=0x20000+output
        g[7]=0x76540000+worker;g[8]=0x87650000+worker;g[13]=0x24680000+worker
        pc=ctr=steps=0
        while pc<28 and steps<budget:
            x=ops[pc//4];old=pc;pc+=4;steps+=1;op=x>>26;rt=(x>>21)&31;ra=(x>>16)&31
            imm=(x&0xffff)-0x10000 if x&0x8000 else x&0xffff
            if op==14:g[rt]=(g[ra] if ra else 0)+imm
            elif op==31:ctr=g[4]
            elif op==16:
                ctr-=1
                if ctr:pc=old+imm
            elif op==36:memory[output:output+4]=g[rt].to_bytes(4,'big')
            elif op==32:g[rt]=int.from_bytes(memory[output:output+4],'big')
            elif op==24:g[ra]=g[rt]|(x&0xffff)
            else:raise AssertionError(op)
        assert(pc,steps,g[3],ctr)==((8,8,3,count-3) if limited else (28,2*count+5,count,0))
        assert(g[7],g[8])==((0x76540000+worker,0x87650000+worker) if limited else (count,count|0x100))
        if not limited:expected[output:output+4]=count.to_bytes(4,'big')
        result=-2 if limited else steps
        if previous[worker]==-2 and result>0:recoveries.append((batch,worker))
        previous[worker]=result;results.append(result)
        assert memory==expected
    outcomes.append(results)
assert outcomes==[[39,67],[-2,73],[51,-2],[57,85],[63,91],[-2,97],[75,-2],[81,109]]
assert recoveries==[(2,0),(3,1),(6,0),(7,1)]
assert sum(x==-2 for pair in outcomes for x in pair)==4
for invariant in ['program.ready.store(round + 1, std::memory_order_release)',
    'gate.released.store(round + 1, std::memory_order_release)',
    'program.completed.store(round + 1, std::memory_order_release)',
    'cpu_thread::g_threads_created.load() != created + 2', 'cpu_thread::g_threads_deleted.load() != deleted',
    'program.registers != expected', 'program.exitAck.fetch_add(1, std::memory_order_release)',
    'programs[0].exitAck.load(std::memory_order_acquire) != 1',
    'vm::get_super_ptr(region.first)', 'if (!started[i])', 'if (slots[i] && !finished[i])']:
    assert invariant in stage,invariant
assert stage.count('std::make_unique<named_thread<ppu_thread>>')==1
assert stage.index('std::make_unique<named_thread<ppu_thread>>')<stage.index('for (u32 round = 0; round < 8; ++round)')
assert stage.index('segmentCleanup.release();')<stage.index('vm::dealloc(address, vm::main)')<stage.index('vm::close(); initialized = false;')
print('PASS: P51 independently encoded shared code, 16 jobs on retained contexts, four exhaustion/recovery sequences, PCs/steps/registers and accumulated isolated outputs; persistent lifecycle/snapshots/queued exits/cleanup; P43-P50 checks retained')

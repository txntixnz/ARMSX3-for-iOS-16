"""Independent P50 shared-code encoding and paired-loop outcomes; P43-P49 regressions."""
from pathlib import Path
import ast,re,runpy,sys
root=Path(__file__).resolve().parent
helpers=runpy.run_path(str(root/'test_p49_fixture.py'))
bridge=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent/'core/loadtest/CoreBridge.cpp'
source=bridge.read_text();stage=source.split('int armsx3_core_test_active_ppu_pair()',1)[1]
code=stage.split('const std::array<u32, 7> opcodes{',1)[1].split('};',1)[0]
# Encode using instruction fields, independently of core macros and the host shim.
def form(op,rt,ra,imm):return(op<<26)|(rt<<21)|(ra<<16)|(imm&0xffff)
ops=[]
for name,args in re.findall(r'\b(LI|MTCTR|ADDI|BC|STW|LWZ|ORI)\(([^()]*)\)',code):
    a=[ast.literal_eval(x.strip()) for x in args.split(',')]
    if name=='LI':ops.append(form(14,a[0],0,a[1]))
    elif name=='MTCTR':ops.append((31<<26)|(a[0]<<21)|(9<<16)|(467<<1))
    else:ops.append(form({'ADDI':14,'BC':16,'STW':36,'LWZ':32,'ORI':24}[name],*a))
assert ops==[0x38600000,0x7c8903a6,0x38630001,0x4200fffc,0x90660000,0x80e60000,0x60e80100]
# Independent little scalar model: expected PCs, partial register results, untouched
# output on exhaustion, and exact instruction counts from each encoded word.
outcomes=[]
for round in range(4):
    results=[]
    for worker in range(2):
        count=17+round*3+worker*14;budget=8 if (round,worker) in [(1,0),(2,1)] else 128
        g=[0]*32;g[4]=count;g[6]=0x20100+worker*0x100;g[7]=0x76540000+worker;g[8]=0x87650000+worker
        pc=ctr=steps=0;output=None
        while pc<28 and steps<budget:
            x=ops[pc//4];old=pc;pc+=4;steps+=1;op=x>>26;rt=(x>>21)&31;ra=(x>>16)&31
            imm=(x&0xffff)-0x10000 if x&0x8000 else x&0xffff
            if op==14:g[rt]=(g[ra] if ra else 0)+imm
            elif op==31:ctr=g[4]
            elif op==16:
                ctr-=1
                if ctr:pc=old+imm
            elif op==36:output=g[rt]
            elif op==32:g[rt]=output
            elif op==24:g[ra]=g[rt]|(x&0xffff)
            else:raise AssertionError(op)
        limited=budget==8
        assert (pc,steps,g[3],ctr,output)==((8,8,3,count-3,None) if limited else (28,2*count+5,count,0,count))
        assert (g[7],g[8])==((0x76540000+worker,0x87650000+worker) if limited else (count,count|0x100))
        results.append(-2 if limited else steps)
    outcomes.append(results)
assert outcomes==[[39,67],[-2,73],[51,-2],[57,85]]
for invariant in ['program.ready.store(true, std::memory_order_release)',
    'gate.go.store(true, std::memory_order_release)', 'armsx3_ios_live_cpu_threads() != live + 2',
    '(*workers[i])(); joined[i] = true;', 'if (!started[i])', 'if (slots[i] && !finished[i])',
    'vm::get_super_ptr(region.first)', 'program.completed.store(true, std::memory_order_release)',
    'cpu_thread::g_threads_created.load() != created + 2', 'cpu_thread::g_threads_deleted.load() != deleted + 2']:
    assert invariant in stage,invariant
assert stage.index('segmentCleanup.release();')<stage.index('vm::dealloc(address, vm::main)')<stage.index('vm::close(); initialized = false;')
assert '{0x10000, 0x20000, 0x30000, 0x40000}' in stage
print('PASS: P50 seven shared opcodes, ORI source/destination fields, four independent pair outcomes/PCs/steps/partial outputs, release/completion/cleanup invariants; P43-P49 fixture checks preserved')

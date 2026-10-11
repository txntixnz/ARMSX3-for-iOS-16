"""Host checks of exact P56 bridge plus production thread-local dispatch boundary.

Usage: python test_p56_pair.py staged/rpcs3/Emu/Cell/PPUThread.cpp CoreBridge.cpp staged/rpcs3/Emu/Cell/Modules/sys_ppu_thread_.cpp
Named CPU workers, VM, decoder, flags and instruction handlers are host shims;
real exec_task and bounded-helper bodies are extracted. Device execution pending.
"""
from pathlib import Path
import subprocess,sys,tempfile
if len(sys.argv)!=4:raise SystemExit(__doc__)
def function(text,signature):
    start=text.index(signature);opening=text.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
core=Path(sys.argv[1]).read_text();bridge=Path(sys.argv[2]).read_text()
# The shim is checked in alongside this test so it is usable from the repository.
shims=(Path(__file__).with_name('p53_host_shims.cpp')).read_text()
assert 'fault==8 && queue_publications==10' in shims
shims=shims.replace('fault==8 && queue_publications==10','fault==8 && queue_publications==56')
assert 'callback_calls++;command(*this,{0},nullptr,nullptr);assert_dispatch_clear();' in shims
shims=shims.replace('callback_calls++;command(*this,{0},nullptr,nullptr);assert_dispatch_clear();',
    'callback_calls++;command(*this,{0},nullptr,nullptr);assert_dispatch_clear();'
    'if(this->id==ppu_thread::id_base+1){'
    'if(fault==14)this->gpr[31]^=1;if(fault==15)this->cia-=4;'
    'if(fault==16)this->ctr+=1;if(fault==17)this->gpr[13]^=0x70;}')
shims=shims.replace('void instruction(ppu_thread&c,',
    'std::atomic<unsigned> executed{0},tls_stores{0},output_stores{0},stack_stores{0},calls{0},returns{0},fp_loads{0},fp_adds{0},fp_stores{0},vec_loads{0},vec_xors{0},vec_stores{0};\nvoid instruction(ppu_thread&c,')
shims=shims.replace('const u32 x=op.opcode,type=x>>26', '++executed;const u32 x=op.opcode,type=x>>26')
shims=shims.replace('case 36:vm::write32', 'case 36:if(ra==13)++tls_stores;else ++output_stores;vm::write32')

# The P53 shim models 32-bit memory; P56 adds explicit big-endian 64-bit
# stack words and only the instruction forms present in the checked fixture.
assert '__builtin_bswap32(bytes)' in shims and '__builtin_bswap32(x)' in shims
shims=shims.replace('return __builtin_bswap32(bytes);',
    'if constexpr(sizeof(T)==8)return __builtin_bswap64(bytes);else return __builtin_bswap32(bytes);')
shims=shims.replace('bytes=__builtin_bswap32(x);',
    'if constexpr(sizeof(T)==8)bytes=__builtin_bswap64(x);else bytes=__builtin_bswap32(x);')
shims=shims.replace('namespace utils{',r'''namespace vm{
 u64 read64(u32 addr){be_t<u64>word;std::memcpy(&word,base(addr),8);return word;}
 void write64(u32 addr,u64 word){const be_t<u64>value=word;std::memcpy(base(addr),&value,8);}
}
namespace utils{''')
assert 'case 31:if(x==0x7c8903a6)' in shims
shims=shims.replace('case 31:if(x==0x7c8903a6)c.ctr=c.gpr[4];else{assert(x==0x7c634214);c.gpr[3]=c.gpr[3]+c.gpr[8];}break;',
    'case 31:if(x==0x7c8903a6)c.ctr=c.gpr[4];else if(x==0x7c0802a6)c.gpr[0]=c.lr;'
    'else if(x==0x7c0803a6)c.lr=c.gpr[0];else{assert(x==0x7c634214);c.gpr[3]+=c.gpr[8];}break;')
shims=shims.replace('case 24:c.gpr[ra]',r'''case 18:{
   const s32 displacement=s32(x<<6)>>6;const u32 target=pc+(displacement&~3);
   if(x&1){c.lr=pc+4;++calls;}c.cia=target;if(fault==23 && (x&1))c.cia+=4;break;
  }
 case 19:assert(x==0x4e800020);++returns;c.cia=u32(c.lr)&~3u;if(fault==24)c.cia=pc+4;break;
 case 62:{
   const s32 displacement=imm&~3;const u32 addr=u32(c.gpr[ra]+displacement);
   vm::write64(addr,c.gpr[rt]);++stack_stores;
   if((x&3)==1)c.gpr[ra]=addr;else assert(!(x&3));
   if(fault==18 && rt==0)vm::write64(addr,0xdeadbeef);
   if(fault==19 && (x&3)==1)vm::write64(addr,0xdecafbad);
   if(fault==20 && rt==2)vm::write64(addr,0xaabbccdd);
   if(fault==21)vm::write64(0x40200,0x0123456789abcdef);
   if(fault==25 && (x&3)==1)c.gpr[ra]+=8;
   break;
  }
 case 58:assert(!(x&3));c.gpr[rt]=vm::read64(u32(c.gpr[ra]+(imm&~3)));if(fault==22)c.gpr[rt]^=1;break;
 case 24:c.gpr[ra]''')
shims=shims.replace('size==52','size==164')
shims+=r'''
namespace ppu_instructions{
 u32 B(s32 displacement,bool aa=false,bool lk=false){return(18u<<26)|(u32(displacement)&0x03fffffc)|(u32(aa)<<1)|u32(lk);}
 u32 MFLR(u32 rt){return(31u<<26)|(rt<<21)|(8u<<16)|(339u<<1);}
 u32 MTLR(u32 rs){return(31u<<26)|(rs<<21)|(8u<<16)|(467u<<1);}
 u32 STD(u32 rs,u32 ra,s32 displacement){return dform(62,rs,ra,displacement&~3);}
 u32 STDU(u32 rs,u32 ra,s32 displacement){return STD(rs,ra,displacement)|1;}
 u32 LD(u32 rt,u32 ra,s32 displacement){return dform(58,rt,ra,displacement&~3);}
 u32 NOP(){return ORI(0,0,0);}u32 BLR(){return 0x4e800020;}
}
'''
# Verify all newly used encoders exist in the staged native core, not just
# in the host shim. The independent fixture validates their instruction bits.
encoders=Path(sys.argv[1]).with_name('PPUOpcodes.h').read_text()
for declaration in ['inline u32 B(s32 li, bool aa = false, bool lk = false)',
 'inline u32 STD(u32 rs, u32 ra, s32 si)', 'inline u32 STDU(u32 rs, u32 ra, s32 si)',
 'inline u32 LD(u32 rt, u32 ra, s32 si)', 'inline u32 MFLR(u32 reg)',
 'inline u32 MTLR(u32 reg)', 'inline u32 BLR()', 'inline u32 NOP()']:
 assert declaration in encoders,declaration

# Register storage and canonical big-endian vector conversion for this phase.
shims=shims.replace('using s32=int32_t;using s64=int64_t;',
    'using s32=int32_t;using s64=int64_t;using f64=double;struct alignas(16) v128{u8 bytes[16];};')
shims=shims.replace('std::vector<std::string> logs;',r'''template<>struct be_t<v128>{
 v128 bytes{};be_t(v128 value){for(unsigned i=0;i<16;i++)bytes.bytes[i]=value.bytes[15-i];}
};
std::vector<std::string> logs;''')
shims=shims.replace('u64 gpr[32]{},ctr=0,lr=0;', 'u64 gpr[32]{},ctr=0,lr=0;f64 fpr[32]{};v128 vr[32]{};')
assert 'if(fault==17)this->gpr[13]^=0x70;' in shims
shims=shims.replace('if(fault==17)this->gpr[13]^=0x70;',
    'if(fault==17)this->gpr[13]^=0x70;if(fault==26)this->fpr[31]=9.0;'
    'if(fault==27)this->vr[31].bytes[0]^=1;'
    'if(fault==34 && this->cia==0x100bc)this->vr[3].bytes[7]^=1;'
    'if(fault==35 && this->cia==0x100ac)this->fpr[3]=9.0;')
shims=shims.replace('case 31:if(x==',r'''case 50:c.fpr[rt]=std::bit_cast<f64>(vm::read64(u32(c.gpr[ra]+imm)));++fp_loads;
   if(fault==33){c.fpr[rt]+=0.25;}break;
 case 54:vm::write64(u32(c.gpr[ra]+imm),std::bit_cast<u64>(c.fpr[rt]));++fp_stores;
   if(fault==31){vm::write64(u32(c.gpr[ra]+imm),1);}break;
 case 63:assert(x==0xfc61102a);c.fpr[3]=c.fpr[1]+c.fpr[2];++fp_adds;
   if(fault==28){c.fpr[3]=std::bit_cast<f64>(std::bit_cast<u64>(c.fpr[3])^1);}break;
 case 4:assert(x==0x106114c4);for(unsigned i=0;i<16;i++)c.vr[3].bytes[i]=c.vr[1].bytes[i]^c.vr[2].bytes[i];++vec_xors;
   if(fault==30){c.vr[3].bytes[0]^=1;}break;
 case 31:if((x&0x7fe)==(103u<<1)){
    const u32 addr=u32(c.gpr[ra]+c.gpr[(x>>11)&31])&~15u;++vec_loads;
    for(unsigned i=0;i<16;i++)c.vr[rt].bytes[i]=static_cast<u8*>(vm::base(addr))[fault==29?i:15-i];
   }else if((x&0x7fe)==(231u<<1)){
    const u32 addr=u32(c.gpr[ra]+c.gpr[(x>>11)&31])&~15u;++vec_stores;
    for(unsigned i=0;i<16;i++)static_cast<u8*>(vm::base(addr))[i]=c.vr[rt].bytes[15-i];
    if(fault==32)static_cast<u8*>(vm::base(addr))[7]^=1;
   }else if(x==''')
shims=shims.replace('size==164','size==196')
shims+=r'''
namespace ppu_instructions{
 u32 LFD(u32 rt,u32 ra,s32 displacement){return dform(50,rt,ra,displacement);}
 u32 STFD(u32 rt,u32 ra,s32 displacement){return dform(54,rt,ra,displacement);}
 u32 LVX(u32 rt,u32 ra,u32 rb){return(31u<<26)|(rt<<21)|(ra<<16)|(rb<<11)|(103u<<1);}
 u32 STVX(u32 rs,u32 ra,u32 rb){return(31u<<26)|(rs<<21)|(ra<<16)|(rb<<11)|(231u<<1);}
}
'''
for declaration in ['inline u32 LFD(u32 frd, u32 ra, s32 si)', 'inline u32 STFD(u32 frs, u32 ra, s32 si)',
 'inline u32 LVX(u32 vd, u32 ra, u32 rb)', 'inline u32 STVX(u32 vs, u32 ra, u32 rb)']:
 assert declaration in encoders,declaration
production=function(core,'struct ios_ppu_dispatch_probe')+';\n'
assert 'static thread_local ios_ppu_dispatch_probe* s_ios_ppu_dispatch_probe = nullptr;' in core
production+='static thread_local ios_ppu_dispatch_probe* s_ios_ppu_dispatch_probe=nullptr;\n'
production+=function(core,'void ppu_thread::exec_task(')+'\n'
production+=function(core,'extern "C" int armsx3_ios_ppu_exec_bounded(')+'\n'
production+='void assert_dispatch_clear(){assert(!s_ios_ppu_dispatch_probe);assert(cpu_thread::current);assert(id_manager::g_id==0); }\n'
tls=Path(sys.argv[3]).read_text()
production+=tls[tls.index('static u32 s_tls_addr'):tls.index('static u32 ppu_alloc_tls()')]+'\n'
for signature in ['static u32 ppu_alloc_tls(', 'static void ppu_free_tls(', 'static void ppu_initialize_tls_memory(',
                  'extern "C" int armsx3_ios_ppu_probe_tls_and_call(', 'static bool ios_probe_tls_pair_owner(',
                  'extern "C" u32 armsx3_ios_ppu_probe_alloc_peer_tls(', 'extern "C" int armsx3_ios_ppu_probe_free_peer_tls(']:
    production+=function(tls,signature)+'\n'
phase=function(bridge,'extern "C" __attribute__((visibility("default"))) int armsx3_core_test_resumed_guest_simd(')
checks=r'''
void restored(){
 assert(!cpu_thread::live && cpu_thread::g_threads_created==cpu_thread::g_threads_deleted);
 assert(!s_ios_ppu_dispatch_probe);
 assert(!s_tls_addr&&!s_tls_file&&!s_tls_zero&&!s_tls_size&&!s_tls_area&&!s_tls_max&&!s_tls_map);
 assert(g_cfg.core.ppu_prof.get() && g_cfg.core.spu_prof.get() && g_cfg.core.spu_debug.get());
 assert(g_cfg.core.ppu_decoder.get()==ppu_decoder_type::llvm && g_cfg.core.thread_scheduler.get()==thread_scheduler_mode::native);
 assert(std::none_of(vm::allocated.begin(),vm::allocated.end(),[](bool x){return x;}));
 assert(id_manager::g_id==0);
}
int main(){
 for(unsigned repetition=0;repetition<8;repetition++){
  logs.clear();construct_calls=0;callback_calls=0;queue_publications=0;executed=0;tls_stores=0;output_stores=0;stack_stores=0;calls=0;returns=0;fp_loads=0;fp_adds=0;fp_stores=0;vec_loads=0;vec_xors=0;vec_stores=0;
  auto created=cpu_thread::g_threads_created.load(),deleted=cpu_thread::g_threads_deleted.load();
  assert(armsx3_core_test_resumed_guest_simd()==0);restored();
  assert(cpu_thread::g_threads_created==created+2 && cpu_thread::g_threads_deleted==deleted+2 && callback_calls==56 && construct_calls==2 && queue_publications==56);
  assert(fp_loads==12 && fp_adds==6 && fp_stores==6 && vec_loads==12 && vec_xors==6 && vec_stores==6);
  assert(executed==564 && tls_stores==6 && output_stores==18 && stack_stores==36 && calls==12 && returns==12);
  for(const char* values:{"results=2/2 previous=0/0 totals=17/31",
   "results=2/2 previous=17/31 totals=37/65", "results=2/2 previous=37/65 totals=60/102"})
   assert(std::count_if(logs.begin(),logs.end(),[=](const auto&s){return s.find(values)!=std::string::npos;})==1);
 }
 for(fault=2;fault<=35;fault++){
  logs.clear();construct_calls=0;callback_calls=0;queue_publications=0;
  assert(armsx3_core_test_resumed_guest_simd()==-1);restored();
 }
 fault=0;
 // Includes the real TLS bootstrap allocation, in addition to CODE/DATA/stacks.
 for(vm::fail_alloc=1;vm::fail_alloc<=5;vm::fail_alloc++){
  assert(armsx3_core_test_resumed_guest_simd()==-1);restored();
 }
 vm::fail_alloc=0;
 Emu.stopped=false;assert(armsx3_core_test_resumed_guest_simd()==-1);Emu.stopped=true;restored();
 g_cfg.core.ppu_threads=1;assert(armsx3_core_test_resumed_guest_simd()==-1);g_cfg.core.ppu_threads=2;restored();
 fxo.available=false;assert(armsx3_core_test_resumed_guest_simd()==-1);fxo.available=true;restored();
 // Independently call the exact helpers inside the exact production bootstrap.
 vm::init();for(unsigned i=0;i<4;i++)assert(vm::alloc(0x10000,vm::main)==0x10000+i*0x10000);
 std::memcpy(vm::base(0x20080),"iOSProbe",9);
 const ppu_thread_params params{static_cast<vm::addr_t>(0x30000),0x8000,0,{},0,0};
 ppu_thread owner(params,"manual TLS guard context",1000);
 assert(!armsx3_ios_ppu_probe_alloc_peer_tls(&owner,0x50000));
 assert(armsx3_ios_ppu_probe_free_peer_tls(&owner,0x50000,0x570d0)==-1);
 cpu_thread::current=&owner;cpu_thread::live=1;
 const auto guards=+[](ppu_thread*context,u32 pool,void*)->int{
  const auto*bytes=static_cast<const u8*>(vm::base(pool));std::vector<u8>before(bytes,bytes+0x40000);
  assert(!armsx3_ios_ppu_probe_alloc_peer_tls(nullptr,pool));
  assert(!armsx3_ios_ppu_probe_alloc_peer_tls(context,pool+0x10000));
  cpu_thread::current=nullptr;assert(!armsx3_ios_ppu_probe_alloc_peer_tls(context,pool));cpu_thread::current=context;
  assert(!std::memcmp(vm::base(pool),before.data(),before.size()));
  const u32 tls=armsx3_ios_ppu_probe_alloc_peer_tls(context,pool);assert(tls==0x570d0);
  assert(!armsx3_ios_ppu_probe_alloc_peer_tls(context,pool));
  assert(armsx3_ios_ppu_probe_free_peer_tls(context,pool,tls+4)==-1);
  cpu_thread::live=2;assert(armsx3_ios_ppu_probe_free_peer_tls(context,pool,tls)==-1);assert(s_tls_map[1]);cpu_thread::live=1;
  assert(armsx3_ios_ppu_probe_free_peer_tls(context,pool,tls)==0);
  assert(armsx3_ios_ppu_probe_free_peer_tls(context,pool,tls)==-1);
  assert(!std::memcmp(vm::base(pool),before.data(),before.size()));return 0;
 };
 assert(armsx3_ios_ppu_probe_tls_and_call(&owner,0x20080,9,64,guards,nullptr)==0);
 assert(!owner.gpr[13]&&!vm::check_addr(0x50000));
 cpu_thread::current=nullptr;cpu_thread::live=0;vm::close();restored();
 std::puts("PASS: exact P56 phase/production TLS/bounded dispatch; eight runs/16 retained host workers/864 slices; 102 pauses/run preserve all GPR/FPR/VR plus CTR/LR/CIA across nested calls, exact independent big-endian double/vector load/add/xor/store results and canaries; 564 instructions,6 FADD/STFD/VXOR/STVX,12 LFD/LVX,36 stack stores,12 calls/returns,56 callbacks/publications,totals60/102; altered paused/computed FPR/VR, wrong FP/load/vector endian/math/store and previous stack/branch/queue/allocation/setup failures all join/free/restore; host CPU/VM/queue/native instruction operations remain shims");
}
'''
with tempfile.TemporaryDirectory(prefix='p56-pair-') as temp:
    source=Path(temp)/'test.cpp';binary=Path(temp)/'test';source.write_text(shims+production+phase+checks)
    subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)

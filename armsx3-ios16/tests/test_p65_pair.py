"""Host checks of exact P65 bridge plus production thread-local dispatch boundary.

Usage: python test_p65_pair.py staged/rpcs3/Emu/Cell/PPUThread.cpp CoreBridge.cpp staged/rpcs3/Emu/Cell/Modules/sys_ppu_thread_.cpp
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
shims=shims.replace('fault==8 && queue_publications==10','fault==8 && queue_publications==50')
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

# The P53 shim models 32-bit memory; P65 adds explicit big-endian 64-bit
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
 case 63:assert(x==0xfc61102b);c.fpr[3]=c.fpr[1]+c.fpr[2];++fp_adds;
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
shims=shims.replace('size==164','size==116')
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

shims=shims.replace('void instruction(ppu_thread&c,', 'std::atomic<unsigned> carry_ops{0},compare_ops{0},cr_reads{0},xer_reads{0},branch_taken{0},branch_untaken{0};\nvoid instruction(ppu_thread&c,')
# P65 shims describe only the native forms present in this fixture. Native
# source declarations/semantics are checked, but this is not a native compile.
shims=shims.replace('struct ppu_thread:cpu_thread {',r'''struct status_bits {
 u8 bits[32]{};u32 pack()const{u32 x=0;for(u8 bit:bits)x=(x<<1)|bit;return x;}
 void unpack(u32 x){for(unsigned i=0;i<32;i++)bits[i]=(x>>(31-i))&1;}
};
struct ppu_thread:cpu_thread {
 status_bits cr;struct{status_bits bits;}fpscr;struct{bool so=false,ov=false,ca=false;u8 cnt=0;}xer;u32 vrsave=0xffffffff;
''')
shims=shims.replace('if(fault==35 && this->cia==0x100ac)this->fpr[3]=9.0;',
 'if(fault==35 && this->cia==0x100ac)this->fpr[3]=9.0;'
 'if(fault==36)this->cr.bits[9]^=1;if(fault==37)this->xer.ca=!this->xer.ca;'
 'if(fault==38)this->xer.so=!this->xer.so;if(fault==39)this->xer.cnt^=1;'
 'if(fault==40)this->fpscr.bits.bits[3]^=1;if(fault==41)this->vrsave^=1;')
shims=shims.replace('case 16:assert(x==0x4200fffc);if(--c.ctr)c.cia=pc+int16_t(x&0xfffc);break;',r'''case 16:
 if(x==0x4200fffc){if(--c.ctr)c.cia=pc+int16_t(x&0xfffc);}
 else{assert(x==0x419e0008);bool eq=c.cr.bits[30];if(fault==42)eq=!eq;if(eq){c.cia=pc+8;++branch_taken;}else{++branch_untaken;}}
 break;
 case 13:{assert(x==0x35ee0001);++carry_ops;const u64 a=c.gpr[14];c.gpr[15]=a+1;c.xer.ca=(a==~u64{0});
  const u32 f=(c.gpr[15]?4u:2u)|u32(c.xer.so);c.cr.unpack((c.cr.pack()&0x0fffffff)|(f<<28));
  if(fault==43){c.xer.ca=!c.xer.ca;}break;}
 case 11:{assert(x==0x2faf0000);++compare_ops;const u32 f=(c.gpr[15]?4u:2u)|u32(c.xer.so);
  c.cr.unpack((c.cr.pack()&~15u)|f);if(fault==44){c.cr.bits[30]^=1;}break;}
''')
shims=shims.replace('++fp_adds;',
 '++fp_adds;c.cr.unpack((c.cr.pack()&~0x0f000000u)|0x04000000u);'
 'c.fpscr.bits.unpack((c.fpscr.bits.pack()&~0xf000u)|0x4000u);'
 'if(fault==45){c.fpscr.bits.bits[17]=0;}')
shims=shims.replace('case 31:if((x&0x7fe)',
 'case 31:if(x==0x7e000026){++cr_reads;c.gpr[16]=c.cr.pack();if(fault==46)c.gpr[16]^=1;}'
 'else if(x==0x7e2102a6){++xer_reads;c.gpr[17]=(u32(c.xer.so)<<31)|(u32(c.xer.ov)<<30)|(u32(c.xer.ca)<<29)|c.xer.cnt;if(fault==47)c.gpr[17]^=1;}'
 'else if((x&0x7fe)')
shims+=r'''
namespace ppu_instructions::implicts {
 u32 CMPDI(u32 field,u32 ra,u32 imm){return(11u<<26)|(field<<23)|(1u<<21)|(ra<<16)|(imm&0xffff);}
}
namespace ppu_instructions {
 u32 MFSPR(u32 rt,u32 spr){return(31u<<26)|(rt<<21)|(spr<<11)|(339u<<1);}
}
'''
assert 'inline u32 MFSPR(u32 rt, u32 spr)' in encoders
assert 'inline u32 CMPDI(u32 cr, u32 reg, u32 imm)' in encoders


# Reservations below are scalar host models, not the native VM reservation code.
shims=shims.replace("if(fault==41)this->vrsave^=1;", "if(fault==41)this->vrsave^=1;if(fault==60)this->raddr=0x21080;")
shims=shims.replace('struct ppu_thread:cpu_thread {',r'''struct ppu_thread:cpu_thread {
 u32 raddr=0,res_cached=0;u64 reserved_word=0,rtime=0;bool use_full_rdata=false;u8 rdata[128]{};
''')
shims=shims.replace('void instruction(ppu_thread&c,',
 'std::atomic<unsigned> reserved_loads{0},conditional_stores{0},atomic_successes{0},atomic_failures{0};\nvoid instruction(ppu_thread&c,')
shims=shims.replace('case 31:if(x==0x7e000026)',r'''case 31:if((x&0x7fe)==(20u<<1)){
 const u32 addr=u32(c.gpr[(x>>11)&31]);c.gpr[rt]=vm::read32(addr);c.raddr=addr;c.reserved_word=vm::read64(addr&~7u);c.rtime=vm::reservation_times[addr/128];
 std::memcpy(c.rdata,vm::base(addr&~7u),8);c.use_full_rdata=false;++reserved_loads;
 if(fault==51 || (fault==68 && pc==0x1014c)){c.gpr[rt]^=1;}
 }else if((x&0x7fe)==(150u<<1)){
 assert(x&1);++conditional_stores;const u32 addr=u32(c.gpr[(x>>11)&31]);
 bool success=c.raddr==addr && c.reserved_word==vm::read64(addr&~7u) && c.rtime==vm::reservation_times[addr/128];
 if(fault==48){success=true;}if(fault==49){success=false;}if(fault==50 && pc==0x10108){success=true;}
 if(fault==66 && pc==0x10140){success=true;}if(fault==67 && pc==0x1012c){success=false;}
 if(success){++atomic_successes;vm::reservation_times[addr/128]+=128;c.rtime+=128;c.res_cached=addr;if(fault!=57 || pc!=0x100fc){vm::write32(addr,u32(c.gpr[rt]));}
  if(fault==52){vm::write32(addr,__builtin_bswap32(u32(c.gpr[rt])));}
  if(fault==53){vm::write32(addr+4,0);}
  if(fault==58 && pc==0x10118){vm::write32(addr,1);}
 }else{++atomic_failures;c.res_cached=0;if(fault==59){vm::write32(addr,0);}}
 const u32 field=(success?2u:0u)|u32(c.xer.so);c.cr.unpack((c.cr.pack()&~0xf0000000u)|(field<<28));
 if(fault==55){c.cr.bits[3]^=1;}c.raddr=0;if(fault==54){c.raddr=addr;}
 }else if((x&0x7fe)==(19u<<1)){
 ++cr_reads;c.gpr[rt]=c.cr.pack();if(fault==46 || (fault==56 && rt>=22) || (fault==71 && rt==29)){c.gpr[rt]^=1;}
 }else if(x==0x7e000026)''')
shims=shims.replace('default:assert(false);', 'default:throw std::runtime_error("invalid host instruction");')
# The generic MFCR case consumes all readback forms, including original r16.

# Snapshot and ordering fault models for the newly paused reservation phases.
shims=shims.replace('namespace vm {', 'namespace vm {\n std::array<u64,0x1200> reservation_times{};')
shims=shims.replace('void init(){memory.fill(0);', 'void init(){reservation_times.fill(0);memory.fill(0);')
shims=shims.replace('if(fault==60)this->raddr=0x21080;',r''' if(fault==60)this->raddr=0x21080;
 if(fault==61 && this->cia==0x10128)this->raddr=0;
 if(fault==62 && this->cia==0x10128)this->rtime^=1;
 if(fault==63 && this->cia==0x10128)this->res_cached^=1;
 if(fault==64 && this->cia==0x10128)this->use_full_rdata=!this->use_full_rdata;
 if(fault==65 && this->cia==0x10128)this->rdata[127]^=1;
 if(fault==72 && this->cia==0x10128)this->gpr[28]^=1;
 if(fault==73 && this->cia==0x10128)vm::write32(u32(this->gpr[19]),0);
 if(fault==74 && this->cia==0x10150)this->raddr=0;
''')
shims=shims.replace('vm::write32(u32(c.gpr[ra]+imm),u32(c.gpr[rt]));',
 'if(!(fault==69 && ra==31))vm::write32(u32(c.gpr[ra]+imm),u32(c.gpr[rt]));'
 'if(fault==70 && ra==31)vm::write32(u32(c.gpr[ra]+imm+4),0);')

# Shared conditional-store serialization is an explicit scalar host model.
# Alternate which host worker arrives first so both valid winner paths execute.
shims=shims.replace('namespace vm {',
 'unsigned preferred_winner=0;std::mutex reservation_lock;std::array<std::atomic<unsigned>,3> race_first_stores{};\nnamespace vm {')
shims=shims.replace('void init(){reservation_times.fill(0);',
 'void init(){for(auto&v:race_first_stores)v.store(0);reservation_times.fill(0);')
shims=shims.replace('void instruction(ppu_thread&c,',
 'std::atomic<unsigned> race_skips{0},race_retries{0},retry_backedges{0},retry_exits{0};\nvoid instruction(ppu_thread&c,')
shims=shims.replace('case 14:c.gpr[rt]=(ra?c.gpr[ra]:0)+imm;break;',
 'case 14:c.gpr[rt]=(ra?c.gpr[ra]:0)+imm;if(fault==79 && pc==0x10180)--c.gpr[rt];break;'
 'case 15:assert(x==0x3ca00002);c.gpr[5]=0x20000;break;')
shims=shims.replace('bool success=c.raddr==addr &&',r'''const unsigned transaction=unsigned((c.gpr[6]-0x20200)/0x100);
 if(addr==0x23000 && pc==0x1016c && unsigned(c.id-ppu_thread::id_base)!=preferred_winner){
  while(!race_first_stores[transaction].load(std::memory_order_acquire))std::this_thread::yield();
 }
 std::lock_guard lock(reservation_lock);
 bool success=c.raddr==addr &&''')
shims=shims.replace('if(fault==66 && pc==0x10140)',
 'if(fault==75 && pc==0x1016c)success=true;if(fault==76 && pc==0x1016c)success=false;'
 'if(fault==84 && pc==0x10184)success=false;'
 'if(fault==66 && pc==0x10140)')
shims=shims.replace('if(fault==54){c.raddr=addr;}',
 'if(fault==54){c.raddr=addr;}'
 'if(fault==80 && addr==0x23000)vm::write32(addr+4,0);'
 'if(pc==0x1016c)race_first_stores[transaction].fetch_add(1,std::memory_order_release);')
shims=shims.replace('if(fault==51 || (fault==68 && pc==0x1014c))',
 'if(fault==51 || (fault==68 && pc==0x1014c) || (fault==81 && pc==0x10164))')
shims=shims.replace('if(fault==2)c.gpr[rt]^=1;',
 'if(fault==2 || (fault==82 && pc==0x10198))c.gpr[rt]^=1;')
shims=shims.replace('(fault==71 && rt==29)', '(fault==71 && rt==29) || (fault==83 && pc==0x10170)')
shims=shims.replace('if(fault==74 && this->cia==0x10150)this->raddr=0;',
 'if(fault==74 && this->cia==0x10150)this->raddr=0;'
 'if(fault==85 && this->cia==0x10168)this->raddr=0;'
 'if(fault==86 && this->cia==0x10168)this->rtime^=128;')
shims=shims.replace('else{assert(x==0x419e0008);',r'''else if(x==0x41820018){bool eq=c.cr.bits[2];if(fault==77)eq=!eq;
   if(eq){c.cia=pc+24;++race_skips;}else{++race_retries;}}
 else if(x==0x4082fff4){bool eq=c.cr.bits[2];if(fault==78)eq=!eq;
   if(!eq){c.cia=pc-12;++retry_backedges;}else{++retry_exits;}}
 else{assert(x==0x419e0008);''')
shims+='\nnamespace ppu_instructions::implicts {u32 LIS(u32 rt,u32 imm){return(15u<<26)|(rt<<21)|(imm&0xffff);}}\n'
assert 'inline u32 LIS(u32 rt, u32 imm)' in encoders

shims=shims.replace('if(fault==75 && pc==0x1016c)success=true;','if(fault==75 && pc==0x1016c){success=true;}')
shims=shims.replace('if(fault==76 && pc==0x1016c)success=false;','if(fault==76 && pc==0x1016c){success=false;}')
shims=shims.replace('if(fault==84 && pc==0x10184)success=false;','if(fault==84 && pc==0x10184){success=false;}')
shims=shims.replace('if(fault==74 && this->cia==0x10150)this->raddr=0;','if(fault==74 && this->cia==0x10150){this->raddr=0;}')
shims=shims.replace('if(fault==85 && this->cia==0x10168)this->raddr=0;','if(fault==85 && this->cia==0x10168){this->raddr=0;}')
shims=shims.replace('if(fault==86 && this->cia==0x10168)this->rtime^=128;','if(fault==86 && this->cia==0x10168){this->rtime^=128;}')

# Additional scalar host fault/counter models for the ordered native fixture.
shims=shims.replace('void instruction(ppu_thread&c,',
 'std::atomic<unsigned> ordered_skips{0},ordered_retries{0},ordered_backedges{0},ordered_exits{0},ordered_plain_stores{0};\nvoid instruction(ppu_thread&c,')
shims=shims.replace('if(fault==66 && pc==0x10140)',
 'if(fault==88 && pc==0x101c4 && c.gpr[28]==0x44557700u+transaction*3+2){success=true;}'
 'if(fault==89 && pc==0x101c4 && c.gpr[28]==0x44557700u+transaction*3+3){success=false;}'
 'if(fault==66 && pc==0x10140)')
shims=shims.replace('if(fault==79 && pc==0x10180)--c.gpr[rt];',
 'if(fault==79 && pc==0x10180)--c.gpr[rt];if(fault==94 && pc==0x101c0){--c.gpr[rt];}')
shims=shims.replace('if(fault==2 || (fault==82 && pc==0x10198))',
 'if(fault==2 || (fault==82 && pc==0x10198) || (fault==93 && pc==0x10214))')
shims=shims.replace('if(fault==80 && addr==0x23000)vm::write32(addr+4,0);',
 'if(fault==80 && addr==0x23000){vm::write32(addr+4,0);}'
 'if(fault==95 && addr==0x23080){vm::write32(addr+4,0);}')
shims=shims.replace('(fault==83 && pc==0x10170)', '(fault==83 && pc==0x10170) || (fault==96 && pc==0x101c8)')
shims=shims.replace('if(fault==86 && this->cia==0x10168){this->rtime^=128;}',
 'if(fault==86 && this->cia==0x10168){this->rtime^=128;}'
 'if(fault==92 && this->cia==0x101c4){this->raddr=0;}')
shims=shims.replace('if(!(fault==69 && ra==31))vm::write32(u32(c.gpr[ra]+imm),u32(c.gpr[rt]));',
 'if(!(fault==69 && ra==31) && !(fault==87 && pc==0x101f0) && !(fault==97 && pc==0x101cc)){vm::write32(u32(c.gpr[ra]+imm),u32(c.gpr[rt]));}'
 'if(pc==0x101f0){++ordered_plain_stores;}')
shims=shims.replace('else if(x==0x4082fff4)',r'''else if(x==0x41820030){bool eq=c.cr.bits[2];if(fault==91){eq=!eq;}
   if(eq){c.cia=pc+48;++ordered_skips;}else{++ordered_retries;}}
 else if(x==0x4082ffec){bool eq=c.cr.bits[2];if(fault==90){eq=!eq;}
   if(!eq){c.cia=pc-20;++ordered_backedges;}else{++ordered_exits;}}
 else if(x==0x4082fff4)''')
shims=shims.replace('if(fault==23 && (x&1))c.cia+=4;',
 'if(fault==23 && (x&1))c.cia+=4;if(fault==98 && pc==0x101d8){c.cia+=4;}')
for n in range(87,99):assert f'fault=={n}' in shims, f'missing new host fault {n}'
# Native declarations and decoder XO values; execution below stays a host model.
interpreter=Path(sys.argv[1]).with_name('PPUInterpreter.cpp').read_text()
assert 'extern u64 ppu_ldarx(ppu_thread& ppu, u32 addr);' in interpreter
assert 'extern bool ppu_stdcx(ppu_thread& ppu, u32 addr, u64 reg_value);' in interpreter
assert '{ 0x054, GET(LDARX) }' in encoders and '{ 0x0d6, GET(STDCX) }' in encoders
assert 'return ppu_load_acquire_reservation<u64>(ppu, addr);' in core
assert 'return ppu_store_reservation<u64>(ppu, addr, reg_value);' in core
assert 'ppu.gpr[op.rd] = ppu_ldarx(ppu, vm::cast(addr));' in interpreter
assert 'ppu_cr_set(ppu, 0, false, false, ppu_stdcx(ppu, vm::cast(addr), ppu.gpr[op.rs]), ppu.xer.so);' in interpreter
shims=shims.replace('void instruction(ppu_thread&c,',
 'std::atomic<unsigned> wide_loads{0},wide_stores{0},wide_outputs{0};\nvoid instruction(ppu_thread&c,')
shims=shims.replace('if((x&0x7fe)==(20u<<1)){',
 'if((x&0x7fe)==(20u<<1) || (x&0x7fe)==(84u<<1)){const bool wide=(x&0x7fe)==(84u<<1);if(wide){++wide_loads;}')
shims=shims.replace('c.gpr[rt]=vm::read32(addr);c.raddr=addr;',
 'c.gpr[rt]=wide?vm::read64(addr):vm::read32(addr);if(wide && fault==99){c.gpr[rt]=u32(c.gpr[rt]);}c.raddr=addr;')
shims=shims.replace('}else if((x&0x7fe)==(150u<<1)){',
 '}else if((x&0x7fe)==(150u<<1) || (x&0x7fe)==(214u<<1)){const bool wide=(x&0x7fe)==(214u<<1);if(wide){++wide_stores;}')
shims=shims.replace('if(fault==48){success=true;}',
 'if(fault==103 && pc==0x10228){success=true;}if(fault==104 && pc==0x10228){success=false;}'
 'if(fault==105 && pc==0x10240){success=false;}if(fault==106 && pc==0x1025c){success=true;}'
 'if(fault==48){success=true;}')
shims=shims.replace('vm::write32(addr,u32(c.gpr[rt]));',
 'if(wide){u64 value=c.gpr[rt];if(fault==100){value=__builtin_bswap64(value);}if(fault==101){value=u32(value);}vm::write64(addr,value);}'
 'else{vm::write32(addr,u32(c.gpr[rt]));}')
shims=shims.replace('const u32 field=(success?2u:0u)',
 'if(wide && !success && fault==107){vm::write64(addr,0);}'
 'if(wide && fault==109){vm::write32(addr+8,0);}'
 'const u32 field=(success?2u:0u)')
shims=shims.replace('c.raddr=0;if(fault==54)', 'c.raddr=0;if(wide && fault==108){c.raddr=addr;}if(fault==54)')
shims=shims.replace('if(fault==94 && pc==0x101c0){--c.gpr[rt];}',
 'if(fault==94 && pc==0x101c0){--c.gpr[rt];}'
 'if(fault==102 && pc==0x1023c){c.gpr[rt]=u32(c.gpr[rt]);}')
shims=shims.replace('if(fault==92 && this->cia==0x101c4){this->raddr=0;}',
 'if(fault==92 && this->cia==0x101c4){this->raddr=0;}'
 'if(fault==110 && this->cia==0x10224){this->raddr=0;}')
shims=shims.replace('(fault==96 && pc==0x101c8)', '(fault==96 && pc==0x101c8) || (fault==111 && pc==0x1022c)')
shims=shims.replace('if(fault==22)c.gpr[rt]^=1;',
 'if(fault==22 || (fault==112 && pc==0x10254))c.gpr[rt]^=1;')
shims=shims.replace('vm::write64(addr,c.gpr[rt]);++stack_stores;',
 'vm::write64(addr,c.gpr[rt]);if(fault==113 && pc==0x10258){vm::write64(addr,c.gpr[rt]^1);}'
 'if(ra==6)++wide_outputs;else ++stack_stores;')
shims=shims.replace('if(fault==77)eq=!eq;', 'if(fault==77 || (fault==114 && pc==0x10234))eq=!eq;')
shims=shims.replace('if(fault==78)eq=!eq;', 'if(fault==78 || (fault==115 && pc==0x10244))eq=!eq;')
for n in range(99,116):assert f'fault=={n}' in shims, f'missing wide host fault {n}'
# Full-line data comparisons are a scalar host model, not the native writer lock.
shims=shims.replace('u32 ppu_threads=2;',
 'setting<s32> ppu_128_reservations_loop_max_length{3};setting<bool> rsx_accurate_res_access{true};u32 ppu_threads=2;')
shims=shims.replace('std::memcpy(c.rdata,vm::base(addr&~7u),8);c.use_full_rdata=false;',r'''c.use_full_rdata=g_cfg.core.ppu_128_reservations_loop_max_length<0;
 if(fault==117){c.use_full_rdata=false;}
 if(c.use_full_rdata && fault!=118){std::memcpy(c.rdata,vm::base(addr&~127u),128);}
 else{std::memcpy(c.rdata,vm::base(addr&~7u),8);}
 if(fault==124 && pc==0x10288){c.gpr[rt]^=1;}''')
shims=shims.replace('if(fault==103 && pc==0x10228)',r'''if(c.use_full_rdata && fault!=116){success=success&&!std::memcmp(c.rdata,vm::base(addr&~127u),128);}
 if(fault==121 && pc==0x10290){success=false;}
 if(fault==128 && pc==0x102a4){success=true;}
 if(fault==103 && pc==0x10228)''')
shims=shims.replace('if(wide && !success && fault==107)',
 'if(fault==122 && pc==0x1027c && !success){vm::write64(addr,0);}'
 'if(fault==126 && pc==0x1027c){vm::write32(addr+120,0);}'
 'if(wide && !success && fault==107)')
shims=shims.replace('c.raddr=0;if(wide && fault==108)',
 'c.raddr=0;if(fault==123 && pc==0x10290){c.raddr=addr;}if(wide && fault==108)')
shims=shims.replace('if(fault==110 && this->cia==0x10224){this->raddr=0;}',
 'if(fault==110 && this->cia==0x10224){this->raddr=0;}'
 'if(fault==125 && this->cia==0x10274){this->rdata[127]^=1;}')
shims=shims.replace('if(fault==102 && pc==0x1023c){c.gpr[rt]=u32(c.gpr[rt]);}',
 'if(fault==102 && pc==0x1023c){c.gpr[rt]=u32(c.gpr[rt]);}'
 'if(fault==130 && pc==0x1028c){c.gpr[rt]=u32(c.gpr[rt]);}')
shims=shims.replace('!(fault==97 && pc==0x101cc)', '!(fault==97 && pc==0x101cc) && !(fault==119 && pc==0x10278)')
shims=shims.replace('if(pc==0x101f0){++ordered_plain_stores;}',
 'if(pc==0x101f0){++ordered_plain_stores;}if(fault==120 && pc==0x10278){vm::write32(u32(c.gpr[ra]+imm+8),0);}')
shims=shims.replace('(fault==111 && pc==0x1022c)', '(fault==111 && pc==0x1022c) || (fault==129 && pc==0x10280)')
shims=shims.replace('if(fault==113 && pc==0x10258)', 'if((fault==113 && pc==0x10258) || (fault==127 && pc==0x102a0))')
for n in range(116,131):assert f'fault=={n}' in shims or f'fault!={n}' in shims, f'missing full-line host fault {n}'
# Same-line retargeting and cached timestamps are explicit scalar host models.
assert 'if (raddr / 128 != addr / 128 || !ppu.use_full_rdata)' in core
assert 'ppu.res_cached = ppu.raddr;' in core and 'ppu.rtime += 128;' in core
shims=shims.replace('c.rtime=vm::reservation_times[addr/128];',
 'if((addr&~127u)!=(c.res_cached&~127u)){c.rtime=vm::reservation_times[addr/128];}'
 'if(fault==136 && pc==0x102d4){c.rtime-=128;}'
 'if(fault==137 && pc==0x102d4){c.gpr[rt]^=1;}'
 'if(fault==138 && pc==0x102f0){c.rdata[16]^=1;}')
# fault138 must act after snapshot copy, to represent an incorrect fresh reload.
shims=shims.replace('if(fault==138 && pc==0x102f0){c.rdata[16]^=1;}', '')
shims=shims.replace('if(fault==124 && pc==0x10288){c.gpr[rt]^=1;}',
 'if(fault==124 && pc==0x10288){c.gpr[rt]^=1;}'
 'if(fault==138 && pc==0x102f0){c.rdata[16]^=1;}')
shims=shims.replace('bool success=c.raddr==addr && c.reserved_word==vm::read64(addr&~7u) && c.rtime==vm::reservation_times[addr/128];',r'''bool success=c.raddr &&
 (c.use_full_rdata ? c.raddr/128==addr/128 && !std::memcmp(c.rdata+(addr&0x78),vm::base(addr),8) :
 c.raddr==addr && c.reserved_word==vm::read64(addr&~7u)) && c.rtime==vm::reservation_times[addr/128];
 if(fault==131 && pc==0x102c0 && c.raddr!=addr){success=false;}
 if(fault==132 && pc==0x102e0){success=true;}
 if(fault==141 && pc==0x102f8){success=false;}
 if(fault==144 && pc==0x1030c){success=true;}''')
shims=shims.replace('if(c.use_full_rdata && fault!=116)', 'if(c.use_full_rdata && fault!=116 && !(fault==132 && pc==0x102e0))')
shims=shims.replace('if(fault==128 && pc==0x102a4){success=true;}', 'if(fault==128 && pc==0x102a4){success=true;}if(fault==144 && pc==0x1030c){success=true;}')
shims=shims.replace('c.rtime+=128;c.res_cached=addr;',
 'if(!(fault==134 && pc==0x102c0)){c.rtime+=128;}c.res_cached=c.raddr;'
 'if(fault==135 && pc==0x102c0){c.res_cached=addr;}')
shims=shims.replace('vm::write64(addr,value);',
 'vm::write64(fault==133 && pc==0x102c0?c.raddr:addr,value);'
 'if(fault==145 && pc==0x102c0){vm::write32(addr+8,0);}')
shims=shims.replace('if(fault==122 && pc==0x1027c && !success)',
 'if(fault==139 && pc==0x102e0 && !success){vm::write64(addr,0);}'
 'if(fault==122 && pc==0x1027c && !success)')
shims=shims.replace('c.res_cached=0;if(fault==59)', 'if(!(fault==140 && pc==0x102e0)){c.res_cached=0;}if(fault==59)')
shims=shims.replace('(fault==129 && pc==0x10280)', '(fault==129 && pc==0x10280) || (fault==143 && pc==0x102e4)')
shims=shims.replace('(fault==127 && pc==0x102a0)', '(fault==127 && pc==0x102a0) || (fault==142 && pc==0x10308)')
shims=shims.replace('void instruction(ppu_thread&c,', 'std::atomic<bool> target_phase_reached{false};\nvoid instruction(ppu_thread&c,')
shims=shims.replace('const u32 pc=c.cia;c.cia+=4;', 'const u32 pc=c.cia;if(pc>=0x102b0 && pc<0x10318){target_phase_reached=true;}c.cia+=4;')
for n in range(131,146):assert f'fault=={n}' in shims or f'fault!={n}' in shims, f'missing target host fault {n}'

# Guest spinlock instruction forms and fault models; fences here are host models.
assert '{ 0x096, GET(ISYNC) }' in encoders and '{ 0x256, GET(SYNC) }' in encoders
assert 'atomic_fence_acquire();' in function(interpreter,'auto ISYNC(')
assert 'atomic_fence_seq_cst();' in function(interpreter,'auto SYNC(')
shims=shims.replace('void instruction(ppu_thread&c,',
 'std::atomic<unsigned> lock_compares{0},lock_busy_backedges{0},lock_free_branches{0},lock_lost_backedges{0},lock_acquired_branches{0},acquire_fences{0},release_fences{0};\nvoid instruction(ppu_thread&c,')
shims=shims.replace('case 11:{assert(x==0x2faf0000);',r'''case 11:{if(x==0x2c070000){++lock_compares;const u32 field=(c.gpr[7]?4u:2u)|u32(c.xer.so);
 c.cr.unpack((c.cr.pack()&0x0fffffff)|(field<<28));if(fault==147){c.cr.bits[2]^=1;}break;}assert(x==0x2faf0000);''')
shims=shims.replace('case 31:if((x&0x7fe)',r'''case 31:if(x==0x7d6b5214){c.gpr[11]+=c.gpr[10];if(fault==153){c.gpr[11]-=2*c.gpr[10];}}
 else if(x==0x7c2004ac){++release_fences;std::atomic_thread_fence(std::memory_order_seq_cst);if(fault==166){c.gpr[5]^=8;}}
 else if((x&0x7fe)''')
shims=shims.replace('case 19:assert(x==0x4e800020);',
 'case 19:if(x==0x4c00012c){++acquire_fences;std::atomic_thread_fence(std::memory_order_acquire);'
 'if(fault==164){vm::write64(0x30200,0);}if(fault==165){c.cr.bits[9]^=1;}break;}assert(x==0x4e800020);')
shims=shims.replace('else if(x==0x41820018)',r'''else if(x==0x4082fff8){bool eq=c.cr.bits[2];if(fault==148 && c.gpr[7]){eq=true;}
 if(!eq){c.cia=pc-8;++lock_busy_backedges;if(fault==167){c.cia+=4;}}else{++lock_free_branches;}}
 else if(x==0x4082ffec && pc==0x10014){bool eq=c.cr.bits[2];if(fault==149){eq=true;}
 if(!eq){c.cia=pc-20;++lock_lost_backedges;}else{++lock_acquired_branches;}}
 else if(x==0x41820018)''')
shims=shims.replace('if(fault==48){success=true;}',
 'if(fault==150 && pc==0x10010){success=true;}if(fault==151 && pc==0x10010){success=false;}'
 'if(fault==48){success=true;}')
shims=shims.replace('const u32 field=(success?2u:0u)',
 'if(fault==161 && pc==0x10010){vm::write32(addr+4,0);}'
 'if(fault==163 && pc==0x10010 && !success){vm::write32(addr,0);}'
 'const u32 field=(success?2u:0u)')
shims=shims.replace('if(fault==125 && this->cia==0x10274){this->rdata[127]^=1;}',
 'if(fault==125 && this->cia==0x10274){this->rdata[127]^=1;}'
 'if(fault==157 && this->cia==0x10008){this->raddr=0;}')
shims=shims.replace('if(fault==130 && pc==0x1028c){c.gpr[rt]=u32(c.gpr[rt]);}',
 'if(fault==130 && pc==0x1028c){c.gpr[rt]=u32(c.gpr[rt]);}'
 'if(fault==159 && pc==0x10050){++c.gpr[rt];}')
shims=shims.replace('!(fault==119 && pc==0x10278)', '!(fault==119 && pc==0x10278) && !(fault==155 && pc==0x10048)')
shims=shims.replace('if(pc==0x101f0){++ordered_plain_stores;}',
 'if(pc==0x101f0){++ordered_plain_stores;}'
 'if(fault==152 && pc==0x1002c){vm::write32(0x23080,99);}'
 'if(fault==154 && pc==0x1002c){vm::write32(0x23000,0);}'
 'if(fault==160 && pc==0x1003c){vm::write32(u32(c.gpr[6]+8),0);}')
shims=shims.replace('if(fault==124 && pc==0x10288){c.gpr[rt]^=1;}',
 'if(fault==124 && pc==0x10288){c.gpr[rt]^=1;}'
 'if(fault==156 && pc==0x10000 && c.gpr[7]){vm::write32(u32(c.gpr[6]),0);}')
shims=shims.replace('if(fault==2 || (fault==82', 'if(fault==162 && pc==0x1001c){c.gpr[rt]=0;}if(fault==2 || (fault==82')
# An untouched floating status corruption after a peer callback.
shims=shims.replace('if(fault==40)this->fpscr.bits.bits[3]^=1;',
 'if(fault==40 || fault==158)this->fpscr.bits.bits[3]^=1;')
for n in range(147,168):assert f'fault=={n}' in shims, f'missing spinlock host fault {n}'
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
phase=function(bridge,'extern "C" __attribute__((visibility("default"))) int armsx3_core_test_guest_spinlock_handoff(')
checks=r'''
void restored(){
 assert(!cpu_thread::live && cpu_thread::g_threads_created==cpu_thread::g_threads_deleted);
 assert(g_cfg.core.ppu_128_reservations_loop_max_length.get()==3 && g_cfg.core.rsx_accurate_res_access.get());
 assert(!s_ios_ppu_dispatch_probe);
 assert(!s_tls_addr&&!s_tls_file&&!s_tls_zero&&!s_tls_size&&!s_tls_area&&!s_tls_max&&!s_tls_map);
 assert(g_cfg.core.ppu_prof.get() && g_cfg.core.spu_prof.get() && g_cfg.core.spu_debug.get());
 assert(g_cfg.core.ppu_decoder.get()==ppu_decoder_type::llvm && g_cfg.core.thread_scheduler.get()==thread_scheduler_mode::native);
 assert(std::none_of(vm::allocated.begin(),vm::allocated.end(),[](bool x){return x;}));
 assert(id_manager::g_id==0);
}
int main(){
 for(unsigned repetition=0;repetition<8;repetition++){
  logs.clear();construct_calls=0;callback_calls=0;queue_publications=0;executed=0;tls_stores=0;output_stores=0;stack_stores=0;calls=0;returns=0;fp_loads=0;fp_adds=0;fp_stores=0;vec_loads=0;vec_xors=0;vec_stores=0;carry_ops=0;compare_ops=0;cr_reads=0;xer_reads=0;branch_taken=0;branch_untaken=0;reserved_loads=0;conditional_stores=0;atomic_successes=0;atomic_failures=0;
  lock_compares=0;lock_busy_backedges=0;lock_free_branches=0;lock_lost_backedges=0;lock_acquired_branches=0;acquire_fences=0;release_fences=0;
  const auto created=cpu_thread::g_threads_created.load(),deleted=cpu_thread::g_threads_deleted.load();
  const int result=armsx3_core_test_guest_spinlock_handoff();if(result)for(const auto&line:logs)std::fprintf(stderr,"%s\n",line.c_str());assert(result==0);restored();
  assert(cpu_thread::g_threads_created==created+2 && cpu_thread::g_threads_deleted==deleted+2 && callback_calls==50 && construct_calls==2 && queue_publications==50);
  assert(lock_compares==18 && lock_busy_backedges==9 && lock_free_branches==9 && lock_lost_backedges==3 && lock_acquired_branches==6 && acquire_fences==6 && release_fences==6);
  assert(reserved_loads==18 && conditional_stores==9 && atomic_successes==6 && atomic_failures==3);
  assert(executed==219 && tls_stores==6 && output_stores==42 && stack_stores==0 && calls==0 && returns==0 && fp_loads==0 && vec_loads==0);
  for(const char* values:{"transaction=1 first worker=0", "transaction=2 first worker=1", "transaction=3 first worker=0", "counter=2 checksum=3 TLS=1/1 results=1/1", "counter=4 checksum=10 TLS=2/2 results=1/1", "counter=6 checksum=21 TLS=3/3 results=1/1"})
   assert(std::count_if(logs.begin(),logs.end(),[=](const auto&line){return line.find(values)!=std::string::npos;})==1);
 }
 const std::vector<int> faults{2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,26,27,36,37,38,39,40,41,48,49,51,52,53,54,55,59,60,147,148,149,150,151,152,153,154,155,156,157,158,159,160,161,162,163,164,165,166,167};
 for(int value:faults){
  fault=value;logs.clear();construct_calls=0;callback_calls=0;queue_publications=0;
  const int result=armsx3_core_test_guest_spinlock_handoff();if(result!=-1){std::fprintf(stderr,"undetected fault=%d\n",fault);}assert(result==-1);restored();
 }
 fault=0;
 // Includes the real TLS bootstrap allocation, in addition to CODE/DATA/stacks.
 for(vm::fail_alloc=1;vm::fail_alloc<=5;vm::fail_alloc++){
  assert(armsx3_core_test_guest_spinlock_handoff()==-1);restored();
 }
 vm::fail_alloc=0;
 Emu.stopped=false;assert(armsx3_core_test_guest_spinlock_handoff()==-1);Emu.stopped=true;restored();
 g_cfg.core.ppu_threads=1;assert(armsx3_core_test_guest_spinlock_handoff()==-1);g_cfg.core.ppu_threads=2;restored();
 fxo.available=false;assert(armsx3_core_test_guest_spinlock_handoff()==-1);fxo.available=true;restored();
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
 std::puts("PASS: exact P65/production TLS/bounded helpers, eight runs/16 retained host workers/768slices,96dispatches/90stops/219instructions,50queuepubs/callbacks,18 LWARX/9 STWCX/6successes/3failures, nine held-lock and three lost-acquisition backedges, six acquire/release fences, counter6/checksum21/TLS3/3, exclusive critical sections/outputs/full contexts/memory/stacks/aliases/cleanup/config restored; selected foundational faults and147..167/all allocation/setup/TLS guard negatives detected; native CPU/VM/reservation/queue/instruction/fence operations remain host models");
}
'''
with tempfile.TemporaryDirectory(prefix='p65-pair-') as temp:
    source=Path(temp)/'test.cpp';binary=Path(temp)/'test';source.write_text(shims+production+phase+checks)
    subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)

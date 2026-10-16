"""Compare the exact old/new SHUFB bodies with native v128/opcode layouts.

Linux models only the new NEON table-lookup intrinsic; SSE masks execute on the
host. --a15-codegen uses Xcode's real iOS intrinsic/header/compiler and checks
the emitted A15 assembly. Neither mode is a complete emulated game benchmark.
"""
from pathlib import Path
import os, re, subprocess, sys, tempfile

root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
pin='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
path='rpcs3/Emu/Cell/SPUInterpreter.cpp'

def block(text,marker):
    start=text.index(marker);opening=text.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]

def verify_a15_assembly(assembly):
    marker=re.search(r'^_armsx3_shufb_a15:[^\n]*\n',assembly,re.M)
    assert marker is not None,'missing SHUFB function in assembly'
    body=assembly[marker.end():].split('.cfi_endproc',1)[0]
    # Apple spells the vector arrangement on the mnemonic (tbl.16b),
    # while GNU/LLVM syntax puts it on the operands (tbl v1.16b, ...).
    assert len(re.findall(r'^\s*tbl(?:\.16b)?[ \t]+',body,re.M))==1,body
    assert not re.search(r'^\s*ldrb[ \t]+',body,re.M),body

def check_assembly_parser():
    captured=(root/'tests/fixtures/a15-shufb-xcode16_4.txt').read_text()
    verify_a15_assembly(captured)
    gnu=captured.replace('tbl.16b\tv1, { v1, v2 }, v3','tbl\tv1.16b, { v1.16b, v2.16b }, v3.16b')
    assert gnu!=captured
    verify_a15_assembly(gnu)
    verify_a15_assembly(captured+'\t.cfi_endproc\n_other_function:\n\tldrb w0, [x0]\n')
    for invalid in [captured.replace('tbl.16b','orr.16b'),captured.replace('tbl.16b','tbl.8b'),
                    captured+'\ttbl.16b v1, { v1, v2 }, v3\n',captured+'\tldrb w0, [x0]\n',
                    captured.replace('_armsx3_shufb_a15:', '_other_function:')]:
        try:verify_a15_assembly(invalid)
        except AssertionError:pass
        else:raise AssertionError('invalid assembly passed verification')
    print('PASS: captured Xcode16.4 tbl.16b and GNU TBL accepted; missing/wrong-width/duplicate lookup, scalar byte loads and missing target rejected')

check_assembly_parser()
if '--assembly-only' in sys.argv:sys.exit(0)

prefix=r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <type_traits>
#include "util/v128.hpp"
#include "Emu/Cell/SPUOpcodes.h"
#if REAL_NEON
#include "Emu/CPU/sse2neon.h"
#else
#include <emmintrin.h>
using uint8x16_t=std::array<u8,16>;
struct uint8x16x2_t{uint8x16_t val[2];};
unsigned tbl_calls=0;
uint8x16_t vqtbl2q_u8(uint8x16x2_t table,uint8x16_t indices){
 ++tbl_calls;uint8x16_t result{};
 for(unsigned n=0;n<16;++n){const unsigned i=indices[n];result[n]=i<32?table.val[i/16][i%16]:0;}
 return result;
}
#endif
struct alignas(16) spu_thread{v128 gpr[128]{};u64 pc=0x1234,guard=0xfedcba9876543210;};
'''
cases=r'''
u32 random_word(){static u32 seed=0x5926d3b1;seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
v128 random_vector(){v128 value;for(unsigned n=0;n<4;++n)value._u32[n]=random_word();return value;}
void verify(const spu_thread&input,spu_opcode_t op){
 spu_thread before=input,after=input,expected=input;
 const v128 a=input.gpr[op.ra],b=input.gpr[op.rb],c=input.gpr[op.rc];
 for(unsigned n=0;n<16;++n){
  const unsigned control=c._u8[n],index=(~control)&31;
  expected.gpr[op.rt4]._u8[n]=control<128?(index<16?b._u8[index]:a._u8[index-16]):control<192?0:control<224?255:128;
 }
 assert(armsx3_shufb_before(before,op));assert(armsx3_shufb_a15(after,op));
 assert(std::memcmp(&before,&expected,sizeof(expected))==0);
 assert(std::memcmp(&after,&expected,sizeof(expected))==0);
}
int main(){
 static_assert(sizeof(v128)==16&&alignof(v128)==16&&sizeof(spu_opcode_t)==4);
 spu_thread input;for(auto&v:input.gpr)v=random_vector();unsigned cases=0;
 // Every selector byte in every output lane, including special 00/ff/80
 // classes and all combinations of aliased A/B/control/destination registers.
 for(unsigned a=0;a<3;++a)for(unsigned b=0;b<3;++b)for(unsigned c=0;c<3;++c)for(unsigned d=0;d<4;++d){
  spu_opcode_t op{};op.ra=a;op.rb=b;op.rc=c;op.rt4=d;
  for(unsigned control=0;control<256;++control){
   input.gpr[a]=random_vector();input.gpr[b]=random_vector();
   for(unsigned n=0;n<16;++n)input.gpr[c]._u8[n]=u8(control+17*n);
   verify(input,op);++cases;
  }
 }
 // Exercise all 128 architectural registers and mixed selectors/data.
 for(unsigned n=0;n<100000;++n){
  spu_opcode_t op{};op.ra=random_word()%128;op.rb=random_word()%128;op.rc=random_word()%128;op.rt4=random_word()%128;
  input.gpr[op.ra]=random_vector();input.gpr[op.rb]=random_vector();input.gpr[op.rc]=random_vector();
  verify(input,op);++cases;
 }
 assert(cases==127648);
#if EXPECT_NEON
 assert(tbl_calls==cases);
#else
 assert(tbl_calls==0);
#endif
 std::puts("PASS: exact SHUFB before/after, native v128/opcode layouts;127648 cases; every control byte/lane; special values, alias combinations,128 registers and untouched context; iOS-only vector selection");
}
'''

with tempfile.TemporaryDirectory(prefix='armsx3-spu-shuffle-') as directory:
    work=Path(directory);file=work/path;file.parent.mkdir(parents=True)
    file.write_bytes(subprocess.check_output(['git','-C',str(native),'show',pin+':'+path]))
    before=after_shuffle=None
    for patch in sorted((root/'patches').glob('*.patch')):
        if patch.name.startswith('0075'):before=file.read_text()
        subprocess.run(['git','apply','--include='+path,str(patch)],cwd=work,check=True)
        if patch.name.startswith('0075'):after_shuffle=file.read_text()
    after=file.read_text();assert before is not None and after_shuffle is not None
    old=block(before,'bool SHUFB(spu_thread&');new=block(after,'bool SHUFB(spu_thread&')
    patched_shuffle=block(after_shuffle,'bool SHUFB(spu_thread&')
    assert after_shuffle.replace(patched_shuffle,old,1)==before,'patch0075 escaped SHUFB body'
    assert old[old.index('// Select special values'):]==new[new.index('// Select special values'):]
    old=old.replace('bool SHUFB(', 'extern "C" bool armsx3_shufb_before(',1)
    new=new.replace('bool SHUFB(', 'extern "C" bool armsx3_shufb_a15(',1)
    code=prefix+old+'\n'+new
    includes=['-I'+str(native/'rpcs3'),'-I'+str(native)]
    cpp=work/'test.cpp';exe=work/'test'
    if '--a15-codegen' in sys.argv:
        cpp.write_text(code)
        sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
        asm=work/'shuffle.s'
        subprocess.run(['xcrun','--sdk','iphoneos','clang++','-std=c++23','-O3','-target','arm64-apple-ios16.0',
                        '-mcpu=apple-a15','-isysroot',sdk,'-DREAL_NEON=1','-DTARGET_OS_IOS=1',*includes,
                        '-S',str(cpp),'-o',str(asm)],check=True)
        assembly=asm.read_text()
        verify_a15_assembly(assembly)
        print('PASS: real Xcode iOS16/apple-a15 SHUFB codegen emits one TBL and no scalar byte loads')
    else:
        cpp.write_text(code+cases)
        for name,apple,ios,arm in [('ios-arm',True,True,True),('mac-arm',True,False,True),
                                  ('other-arm',False,False,True),('ios-x86',True,True,False),('linux-x86',False,False,False)]:
            options=['-DREAL_NEON=0',f'-DTARGET_OS_IOS={int(ios)}',f'-DEXPECT_NEON={int(apple and ios and arm)}']
            if apple:options+=['-D__APPLE__=1']
            if arm:options+=['-DARCH_ARM64=1']
            subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                            '-fno-omit-frame-pointer',*includes,*options,str(cpp),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})

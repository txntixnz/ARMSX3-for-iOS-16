"""Exact native CNTB/CLZ bodies versus independent bit-by-bit references.
Host models NEON semantics; --a15-codegen checks actual Apple instruction output.
"""
from pathlib import Path
import os, re, subprocess, sys, tempfile
root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
path='rpcs3/Emu/Cell/SPUInterpreter.cpp'
pin='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
def block(text,name):
 start=text.index('bool '+name+'(');end=text.index('{',start)+1;depth=1
 while depth:
  depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]
prefix=r'''
#include <array>
#include <bit>
#include <cassert>
#include <cstdio>
#include <cstring>
#include "util/v128.hpp"
#include "Emu/Cell/SPUOpcodes.h"
#if REAL_NEON
#include "Emu/CPU/sse2neon.h"
#else
#include <emmintrin.h>
using uint8x16_t=std::array<u8,16>;
using uint32x4_t=std::array<u32,4>;
unsigned vector_calls=0;
uint8x16_t vcntq_u8(uint8x16_t a){++vector_calls;for(auto&v:a)v=std::popcount(v);return a;}
uint32x4_t vclzq_u32(uint32x4_t a){++vector_calls;for(auto&v:a)v=std::countl_zero(v);return a;}
#endif
struct alignas(16) spu_thread{v128 gpr[128]{};u64 pc=0x1234,guard=0xfedcba9876543210;};
'''
cases=r'''
u32 random_word(){static u32 s=0x23ce4123;s^=s<<13;s^=s>>17;s^=s<<5;return s;}
unsigned checks=0;
void verify(const spu_thread&input,unsigned a,unsigned d){
 spu_opcode_t op{};op.ra=a;op.rt=d;
 for(unsigned kind=0;kind<2;++kind){
  spu_thread before=input,after=input,expected=input;
  if(kind==0){
   for(unsigned lane=0;lane<16;++lane){unsigned n=0;for(unsigned b=0;b<8;++b)n+=(input.gpr[a]._u8[lane]>>b)&1;expected.gpr[d]._u8[lane]=n;}
   assert(old_CNTB(before,op));assert(ios_CNTB(after,op));
  }else{
   for(unsigned lane=0;lane<4;++lane){u32 v=input.gpr[a]._u32[lane],n=0;while(n<32 && !(v&0x80000000u)){++n;v<<=1;}expected.gpr[d]._u32[lane]=n;}
   assert(old_CLZ(before,op));assert(ios_CLZ(after,op));
  }
  assert(std::memcmp(&before,&expected,sizeof(expected))==0);
  assert(std::memcmp(&after,&expected,sizeof(expected))==0);++checks;
 }
}
int main(){
 static_assert(sizeof(v128)==16&&alignof(v128)==16&&sizeof(spu_opcode_t)==4);
 spu_thread s;for(auto&v:s.gpr)for(unsigned i=0;i<4;++i)v._u32[i]=random_word();
 for(unsigned a=0;a<128;++a){
  for(unsigned alias=0;alias<2;++alias){const unsigned d=alias?a:(a+1)%128;
   // Every byte value in each lane, including every possible population count.
   for(unsigned value=0;value<256;++value){for(unsigned lane=0;lane<16;++lane)s.gpr[a]._u8[lane]=u8(value+lane*17);verify(s,a,d);}
   // Every leading-zero boundary, zero/all-ones, adjacent and mixed lane values.
   for(unsigned bit=0;bit<32;++bit){u32 v=u32(1)<<bit;s.gpr[a]=v128::from32(v,v-1,~v,0);verify(s,a,d);}
   for(unsigned n=0;n<128;++n){for(unsigned i=0;i<4;++i)s.gpr[a]._u32[i]=random_word();verify(s,a,d);}
  }
 }
#if EXPECT_NEON
 assert(vector_calls==checks);
#else
 assert(vector_calls==0);
#endif
 std::printf("PASS: %u exact old/new/reference cases; all bytes, CLZ boundaries,128 registers, aliases and full unchanged context\n",checks);
}
'''
with tempfile.TemporaryDirectory(prefix='spu-bit-counts-') as tmp:
 work=Path(tmp);f=work/path;f.parent.mkdir(parents=True)
 f.write_bytes(subprocess.check_output(['git','-C',str(native),'show',pin+':'+path]))
 before=None
 for p in sorted((root/'patches').glob('*.patch')):
  if p.name=='0077-ios-neon-spu-bit-counts.patch':before=f.read_text()
  subprocess.run(['git','apply','--include='+path,str(p)],cwd=work,check=True)
 after=f.read_text();assert before is not None
 restored=after;code=prefix
 for name in ['CNTB','CLZ']:
  old,new=block(before,name),block(after,name)
  restored=restored.replace(new,old,1)
  code+=old.replace('bool '+name+'(', 'extern "C" bool old_'+name+'(',1)+'\n'
  code+=new.replace('bool '+name+'(', 'extern "C" bool ios_'+name+'(',1)+'\n'
 assert restored==before,'change escaped CNTB/CLZ bodies'
 includes=['-I'+str(native/'rpcs3'),'-I'+str(native)]
 cpp=work/'counts.cpp';exe=work/'counts'
 if '--a15-codegen' in sys.argv:
  cpp.write_text(code)
  sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
  asm=work/'counts.s'
  subprocess.run(['xcrun','--sdk','iphoneos','clang++','-std=c++23','-O3','-target','arm64-apple-ios16.0','-mcpu=apple-a15','-isysroot',sdk,'-DREAL_NEON=1','-DTARGET_OS_IOS=1',*includes,'-S',str(cpp),'-o',str(asm)],check=True)
  text=asm.read_text()
  for name,mnemonic,width in [('CNTB','cnt','16b'),('CLZ','clz','4s')]:
   match=re.search(r'^_ios_'+name+r':[^\n]*\n(.*?)\.cfi_endproc',text,re.M|re.S);assert match,name
   body=match[1]
   pattern=r'^\s*'+mnemonic+r'(?:\.'+width+r'\s+v\d+,\s*v\d+|\s+v\d+\.'+width+r',\s*v\d+\.'+width+r')'
   assert len(re.findall(pattern,body,re.M))==1,body
   assert not re.search(r'\[\s*(?:sp|x29)\b|^\s*(?:bl|blr)\s',body,re.M),body
  print('PASS: actual A15 CNT.16B/CLZ.4S, one vector count per body, no stack or calls')
 else:
  cpp.write_text(code+cases)
  for name,apple,ios,arm in [('ios-arm',1,1,1),('mac-arm',1,0,1),('other-arm',0,0,1),('ios-x86',1,1,0),('linux-x86',0,0,0)]:
   opts=['-DREAL_NEON=0',f'-DTARGET_OS_IOS={ios}',f'-DEXPECT_NEON={apple and ios and arm}']
   if apple:opts+=['-D__APPLE__=1']
   if arm:opts+=['-DARCH_ARM64=1']
   subprocess.run(['g++','-std=c++23','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',*includes,*opts,str(cpp),'-o',str(exe)],check=True)
   subprocess.run([str(exe)],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})

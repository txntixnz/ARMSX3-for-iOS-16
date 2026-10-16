"""Exact nine SPU byte-rotate/shift bodies before/after the iOS vector change.

Native v128/opcode layouts; Linux models the new NEON vector operations.
--a15-codegen checks real iOS/A15 assembly in CI, not phone performance.
"""
from pathlib import Path
import ast, os, re, subprocess, sys, tempfile

root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
pin='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
path='rpcs3/Emu/Cell/SPUInterpreter.cpp'
names=['ROTQBYBI','ROTQMBYBI','SHLQBYBI','ROTQBY','ROTQMBY','SHLQBY','ROTQBYI','ROTQMBYI','SHLQBYI']

def verify_a15_assembly(assembly,name):
    marker=re.search(r'^_ios_'+name+r':[^\n]*\n',assembly,re.M)
    assert marker is not None,'missing '+name+' function in assembly'
    body,end,_=assembly[marker.end():].partition('.cfi_endproc')
    assert end,'missing end of '+name+' function'
    assert len(re.findall(r'^\s*tbl(?:\.16b)?[ \t]+',body,re.M))==1,body
    assert not re.search(r'\[\s*(?:sp|x29)\b',body),body
    # Only the low byte of RB word3 contributes to these register counts.
    # Xcode can narrow that scalar count read to LDRB [gpr(RB), #12]; it
    # does not replace the vector payload lookup with scalar byte loads.
    byte_loads=re.findall(r'^[ \t]*ldrb[ \t]+([^\n;]+)',body,re.M)
    assert len(byte_loads)<=(1 if name in names[:6] else 0),body
    assert all(re.fullmatch(r'w\d+,\s*\[x\d+,\s*#12\]',load.strip()) for load in byte_loads),body

def check_assembly_parser():
    captured=(root/'tests/fixtures/a15-spu-rotqbybi-xcode16_4.txt').read_text()
    verify_a15_assembly(captured,'ROTQBYBI')
    gnu=captured.replace('tbl.16b\tv0, { v0 }, v1','tbl\tv0.16b, { v0.16b }, v1.16b')
    assert gnu!=captured
    verify_a15_assembly(gnu,'ROTQBYBI')
    count_load='\tldrb\tw9, [x9, #12]\n'
    assert count_load in captured
    verify_a15_assembly(captured.replace(count_load,'\tldr\tw9, [x9, #12]\n'),'ROTQBYBI')
    verify_a15_assembly(captured+'\n_other_function:\n\tldrb w0, [x0]\n','ROTQBYBI')
    # Exercise each variant's byte-load policy with the captured body.
    for name in names:
        renamed=captured.replace('_ios_ROTQBYBI:', '_ios_'+name+':')
        verify_a15_assembly(renamed if name in names[:6] else renamed.replace(count_load,''),name)
    invalid=[captured.replace('tbl.16b','orr.16b'),captured.replace('tbl.16b','tbl.8b'),
             captured.replace('\tret\n','\ttbl.16b v0, { v0 }, v1\n\tret\n'),
             captured.replace(count_load,count_load+'\tldrb w10, [x9, #12]\n'),
             captured.replace('[x9, #12]','[x9, #13]'),
             captured.replace('[x9, #12]','[sp, #12]'),
             captured.replace('[x9, #12]','[x29, #12]'),
             captured.replace('_ios_ROTQBYBI:', '_other_function:'),
             captured.replace('.cfi_endproc','')]
    for assembly,name in [(text,'ROTQBYBI') for text in invalid]+[
            (captured.replace('_ios_ROTQBYBI:', '_ios_'+name+':'),name) for name in names[6:]]:
        try:verify_a15_assembly(assembly,name)
        except AssertionError:pass
        else:raise AssertionError('invalid '+name+' assembly passed verification')
    print('PASS: captured Xcode byte-count load and Apple/GNU TBL accepted; all nine load policies, missing/wrong-width/duplicate TBL, extra or misplaced byte loads, stack access and function bounds checked')

check_assembly_parser()
if '--assembly-only' in sys.argv:sys.exit(0)

def block(source,marker):
    start=source.index(marker);opening=source.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]

tree=ast.parse((root/'tests/test_ios_spu_shuffle.py').read_text())
prefix=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='prefix' for t in n.targets))
support=r'''
#if !REAL_NEON
uint8x16_t vdupq_n_u8(u8 byte){uint8x16_t result;result.fill(byte);return result;}
uint8x16_t vaddq_u8(uint8x16_t a,uint8x16_t b){for(unsigned i=0;i<16;++i)a[i]=u8(a[i]+b[i]);return a;}
uint8x16_t vsubq_u8(uint8x16_t a,uint8x16_t b){for(unsigned i=0;i<16;++i)a[i]=u8(a[i]-b[i]);return a;}
uint8x16_t vandq_u8(uint8x16_t a,uint8x16_t b){for(unsigned i=0;i<16;++i)a[i]&=b[i];return a;}
uint8x16_t vqtbl1q_u8(uint8x16_t table,uint8x16_t indices){
 ++tbl_calls;uint8x16_t result{};
 for(unsigned i=0;i<16;++i)result[i]=indices[i]<16?table[indices[i]]:0;
 return result;
}
#endif
'''
cases=r'''
struct Case{bool(*old)(spu_thread&,spu_opcode_t);bool(*current)(spu_thread&,spu_opcode_t);unsigned mode,source;};
Case instructions[]={/* CASE_TABLE */};
u32 random_word(){static u32 seed=0x781296a3;seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
v128 random_vector(){v128 value;for(unsigned i=0;i<4;++i)value._u32[i]=random_word();return value;}
unsigned verified=0;
void verify(const Case&which,const spu_thread&input,spu_opcode_t op){
 spu_thread old=input,current=input,expected=input;
 const auto a=input.gpr[op.ra];
 u32 count=which.source==2?u32(op.i7):input.gpr[op.rb]._u32[3];
 if(which.source==1)count>>=3;
 const int n=int(which.mode==0?count&15:which.mode==1?(0-count)&31:count&31);
 for(int i=0;i<16;++i){
  const int index=which.mode==0?(i+16-n)%16:which.mode==1?i+n:i-n;
  expected.gpr[op.rt]._u8[i]=index>=0&&index<16?a._u8[index]:0;
 }
 assert(which.old(old,op)&&which.current(current,op));
 assert(std::memcmp(&old,&expected,sizeof(expected))==0);
 assert(std::memcmp(&current,&expected,sizeof(expected))==0);
 ++verified;
}
int main(){
 static_assert(sizeof(v128)==16&&alignof(v128)==16&&sizeof(spu_opcode_t)==4);
 spu_thread input;for(auto&v:input.gpr)v=random_vector();
 for(const auto&which:instructions){
  if(which.source==2){
   for(unsigned a=0;a<3;++a)for(unsigned d=0;d<3;++d)for(unsigned n=0;n<128;++n){
    spu_opcode_t op{};op.ra=a;op.rt=d;op.i7=n;input.gpr[a]=random_vector();verify(which,input,op);
   }
  }else{
   for(unsigned a=0;a<3;++a)for(unsigned b=0;b<3;++b)for(unsigned d=0;d<3;++d)for(unsigned n=0;n<256;++n){
    spu_opcode_t op{};op.ra=a;op.rb=b;op.rt=d;
    input.gpr[a]=random_vector();input.gpr[b]=random_vector();input.gpr[b]._u32[3]=n;verify(which,input,op);
   }
  }
  for(unsigned n=0;n<20000;++n){
   spu_opcode_t op{};op.ra=random_word()%128;op.rb=random_word()%128;op.rt=random_word()%128;
   if(which.source==2)op.i7=random_word()%128;
   input.gpr[op.ra]=random_vector();input.gpr[op.rb]=random_vector();verify(which,input,op);
  }
 }
 assert(verified==224928);
#if EXPECT_NEON
 assert(tbl_calls==verified);
#else
 assert(tbl_calls==0);
#endif
 std::puts("PASS: nine exact SPU byte rotate/shift bodies, native layouts;224928 cases; all immediate/count boundaries, alias patterns, high bits,128 registers and untouched context; iOS-only vector selection");
}
'''

with tempfile.TemporaryDirectory(prefix='armsx3-spu-byte-shifts-') as directory:
    work=Path(directory);file=work/path;file.parent.mkdir(parents=True)
    file.write_bytes(subprocess.check_output(['git','-C',str(native),'show',pin+':'+path]))
    before=after_shift_patch=None
    for patch in sorted((root/'patches').glob('*.patch')):
        if patch.name.startswith('0076'):before=file.read_text()
        subprocess.run(['git','apply','--include='+path,str(patch)],cwd=work,check=True)
        if patch.name.startswith('0076'):after_shift_patch=file.read_text()
    after=file.read_text();assert before is not None and after_shift_patch is not None
    start=after.index('#if defined(ARCH_ARM64) && defined(__APPLE__) && TARGET_OS_IOS\nstatic inline v128 ios_spu_rotate_bytes')
    end=after.index('template <spu_exec_bit... Flags>\nbool ROTQBYBI(',start)
    helpers=after[start:end]
    # Scope belongs to patch0076; later independent instruction changes are valid.
    assert helpers in after_shift_patch,'byte-shift helpers changed after patch0076'
    restored=after_shift_patch.replace(helpers,'',1);bodies=[];entries=[]
    for i,name in enumerate(names):
        old=block(before,'bool '+name+'(');new=block(after,'bool '+name+'(')
        assert new==block(after_shift_patch,'bool '+name+'('),'byte-shift body changed after patch0076: '+name
        restored=restored.replace(new,old,1)
        bodies.extend([old.replace('bool '+name+'(', 'extern "C" bool before_'+name+'(',1),
                       new.replace('bool '+name+'(', 'extern "C" bool ios_'+name+'(',1)])
        entries.append('{before_'+name+',ios_'+name+','+str(i%3)+','+str(1 if i<3 else 0 if i<6 else 2)+'}')
    assert restored==before,'changes escaped the helpers/nine instruction bodies'
    code=prefix+support+helpers+'\n'.join(bodies)
    includes=['-I'+str(native/'rpcs3'),'-I'+str(native)]
    cpp=work/'test.cpp';exe=work/'test'
    if '--a15-codegen' in sys.argv:
        cpp.write_text(code)
        sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
        asm=work/'shifts.s'
        subprocess.run(['xcrun','--sdk','iphoneos','clang++','-std=c++23','-O3','-target','arm64-apple-ios16.0',
                        '-mcpu=apple-a15','-isysroot',sdk,'-DREAL_NEON=1','-DTARGET_OS_IOS=1',*includes,
                        '-S',str(cpp),'-o',str(asm)],check=True)
        assembly=asm.read_text()
        for name in names:
            verify_a15_assembly(assembly,name)
        print('PASS: real iOS16/apple-a15 codegen; all nine byte rotates/shifts use one TBL and no stack memory; byte loads limited to register counts')
    else:
        cpp.write_text(code+cases.replace('/* CASE_TABLE */',','.join(entries)))
        for name,apple,ios,arm in [('ios-arm',True,True,True),('mac-arm',True,False,True),
                                  ('other-arm',False,False,True),('ios-x86',True,True,False),('linux-x86',False,False,False)]:
            options=['-DREAL_NEON=0',f'-DTARGET_OS_IOS={int(ios)}',f'-DEXPECT_NEON={int(apple and ios and arm)}']
            if apple:options+=['-D__APPLE__=1']
            if arm:options+=['-DARCH_ARM64=1']
            subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                            '-fno-omit-frame-pointer',*includes,*options,str(cpp),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})

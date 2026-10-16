"""Exact native SPU loop/profile with modeled ISA, clock, storage and log sinks."""
from pathlib import Path
import os, subprocess, sys, tempfile
from test_spu_thread_entry import model
from test_jit_lifecycle import prelude
root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
pin='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
path='rpcs3/Emu/Cell/SPUCommonRecompiler.cpp'

def block(source,marker):
    start=source.index(marker);opening=source.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]

support=r'''
#include <mutex>
#include <type_traits>
using u8=std::uint8_t;using u64=std::uint64_t;using usz=std::size_t;
namespace utils{inline thread_local u64 ticks=100,frequency=1000000000;u64 get_tsc(){return ticks;}u64 get_tsc_freq(){return frequency;}}
struct Report{unsigned id;u64 samples,untracked;double wall;unsigned final;std::string detail;};
std::mutex report_mutex;std::vector<Report> reports;unsigned starts=0;
thread_local unsigned host_limit=200000;
void note_start(){std::lock_guard lock(report_mutex);++starts;}
void note_report(unsigned id,u64 samples,u64 missed,double wall,unsigned final,const std::string&detail){
 std::lock_guard lock(report_mutex);reports.push_back({id,samples,missed,wall,final,detail});
}
namespace fmt{template<class...T>void append(std::string&text,const char*format,T...args){
 char buffer[256];std::snprintf(buffer,sizeof(buffer),format,args...);text+=buffer;
}}
'''
checks=r'''
void prepare(spu_thread&s){
 s.lv2_id=0x2000100;s.allow_interrupts_in_cpu_work=true;
 s.local[0].set(0x10000001);s.local[1].set(0x20000000);s.local[4].set(0x30000000);
 g_tls_log_prefix=+[]()->std::string{return "host-SPU";};
}
int main(){
#if IOS_TEST
 static_assert(std::is_trivially_destructible_v<ios_spu_dispatch_profile>);
 utils::frequency=1000;
 ios_spu_dispatch_profile p(99);unsigned low=32767,high=0;
 for(unsigned i=0;i<20000;++i){const auto stride=p.next_interval();assert(stride>=16384&&stride<=32767);low=std::min(low,stride);high=std::max(high,stride);}
 assert(low==16384&&high==32767);
 for(unsigned i=0;i<70;++i)p.record(0x100,0x12345678);
 for(unsigned i=0;i<30;++i)p.record(0x104,0x23456789);
 utils::ticks+=10000;p.report(false);assert(reports.back().samples==100&&reports.back().untracked==0&&reports.back().wall==10000);
 assert(reports.back().detail.find("70.0%")!=std::string::npos&&reports.back().detail.find("30.0%")!=std::string::npos);
 assert(!p.samples&&!p.untracked);
 // Same address, changed opcode remains a distinct sample; full tables count misses.
 p.record(0x100,1);p.record(0x100,2);
 for(unsigned i=0;i<127;++i)p.record(0x1000+i*4,3);
 assert(p.samples==129&&p.untracked==1);p.record(0x100,1);assert(p.samples==130&&p.untracked==1);
 p.report(true);assert(reports.back().final==1);
 p.report(true);assert(reports.back().samples==0&&reports.back().detail.empty());
 utils::frequency=0;ios_spu_dispatch_profile zero(100);zero.record(0,0);zero.report(true);assert(reports.back().wall==0);
 utils::frequency=1000;ios_spu_dispatch_profile periodic(101);const auto previous=reports.size();
 utils::ticks+=10000;periodic.record(0x300,5);assert(reports.size()==previous+1&&!reports.back().final);
 utils::frequency=1000000000;
#endif
 auto baseline=std::make_unique<spu_thread>();auto current=std::make_unique<spu_thread>();
 prepare(*baseline);prepare(*current);
 spu_recompiler_base::old_interpreter_before(*baseline,baseline->_ptr<u8>(0),nullptr);
 const auto initial_starts=starts;
 spu_recompiler_base::old_interpreter(*current,current->_ptr<u8>(0),nullptr);
 assert(current->decoded==200000&&current->decoded==baseline->decoded);
 assert(current->pc==baseline->pc&&current->accumulator==baseline->accumulator&&current->checks==baseline->checks);
#if IOS_TEST
 assert(starts==initial_starts+1&&reports.back().id==current->lv2_id&&reports.back().samples>0);
 // Many short gateway re-entries retain one TLS table and countdown.
 current->state.value=0;host_limit=10000000;
 for(unsigned i=0;i<40000;++i){current->pc=0;current->interp_fallback=true;current->interp_fallback_begin=0;current->interp_fallback_end=4;
  spu_recompiler_base::old_interpreter(*current,current->_ptr<u8>(0),nullptr);assert(!current->interp_fallback);}
 current->state.value=1;spu_recompiler_base::old_interpreter(*current,current->_ptr<u8>(0),nullptr);
 assert(starts==initial_starts+1&&reports.back().samples>0);
#else
 (void)initial_starts;assert(!starts&&reports.empty());
#endif
 // Six independent worker/TLS tables: no cross-thread register or LS reads.
 const auto before_starts=starts;std::vector<std::thread> workers;
 for(unsigned i=0;i<6;++i)workers.emplace_back([i]{auto s=std::make_unique<spu_thread>();prepare(*s);s->lv2_id+=i;
  spu_recompiler_base::old_interpreter(*s,s->_ptr<u8>(0),nullptr);assert(s->decoded==200000);});
 for(auto&t:workers)t.join();
#if IOS_TEST
 assert(starts==before_starts+6);
#else
 (void)before_starts;assert(!starts);
#endif
 // Rejection, pre-stopped execution and native fallback exit remain intact.
 g_cfg.core.spu_decoder=spu_decoder_type::dynamic;bool rejected=false;
 try{spu_recompiler_base::old_interpreter(*current,current->_ptr<u8>(0),nullptr);}catch(const std::runtime_error&){rejected=true;}assert(rejected);
 std::puts("PASS: exact native SPU loop preserves branch/PC/stop behavior; profile jitter, counts/coverage, bounded storage, opcode changes, zero clocks, reports, gateway re-entry and six-worker isolation; non-iOS path unchanged");
}
'''

with tempfile.TemporaryDirectory(prefix='armsx3-spu-profile-') as temp:
    work=Path(temp);file=work/path;file.parent.mkdir(parents=True)
    file.write_bytes(subprocess.check_output(['git','-C',str(native),'show',pin+':'+path]))
    original=None
    for patch in sorted((root/'patches').glob('*.patch')):
        if patch.name.startswith('0072'):original=file.read_text()
        subprocess.run(['git','apply','--include='+path,str(patch)],cwd=work,check=True)
    source=file.read_text();assert original is not None
    profile=block(source,'struct ios_spu_dispatch_profile')+';'
    interpreter=block(source,'void spu_recompiler_base::old_interpreter(')
    before=block(original,'void spu_recompiler_base::old_interpreter(').replace('::old_interpreter(', '::old_interpreter_before(',1)
    assert 'static thread_local ios_spu_dispatch_profile' in interpreter
    assert 'profile->record(spu.pc, op)' in interpreter
    for forbidden in ['vm::','idm::','g_fxo','ppu_thread','spu._','thread_info']:
        assert forbidden not in profile,forbidden
    host=model
    old='struct Log{struct Method{template<class...T>void operator()(const char*,T...)const{}}warning,notice,trace;}spu_log;'
    new='''struct Log{struct Method{template<class...T>void operator()(const char*,T...)const{}}warning,notice,trace;
 void success(const char*,u32){note_start();}
 void success(const char*,u32 id,u64 n,u64 missed,double wall,u32 final,const std::string&detail){note_report(id,n,missed,wall,final,detail);}
}spu_log;'''
    assert old in host;host=host.replace(old,new)
    host=host.replace('static void old_interpreter(spu_thread&,void*,u8*);', 'static void old_interpreter(spu_thread&,void*,u8*);static void old_interpreter_before(spu_thread&,void*,u8*);')
    host=host.replace('++s.decoded;', '++utils::ticks;++s.decoded;if(s.decoded==host_limit)s.state.value=1;')
    host=host.replace('if(op.opcode==0x10000001)', 'if(op.opcode==0x30000000){s.pc=0;return false;}\n if(op.opcode==0x10000001)')
    for name,apple,ios in [('ios',True,True),('macos',True,False),('linux',False,False)]:
        code=prelude+'\n#include <string>\n'+support+host+before+'\n#if IOS_TEST\n'+profile+'\n#endif\n'+interpreter+checks
        (work/'test.cpp').write_text(code)
        options=[f'-DIOS_TEST={int(ios)}',f'-DTARGET_OS_IOS={int(ios)}']
        if apple:options+=['-D__APPLE__=1']
        subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined',
                        '-fno-omit-frame-pointer',*options,str(work/'test.cpp'),'-o',str(work/'test')],check=True)
        subprocess.run([str(work/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})

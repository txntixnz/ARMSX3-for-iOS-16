"""Compile production iOS RSX clocks/scopes; no GPU or live guest sampler.

The complete native header and the iOS-only function bodies are compiled with
host clock/log interfaces. Full Apple compilation remains an Actions check.
"""
from pathlib import Path
import os, subprocess, sys, tempfile

root = Path(__file__).resolve().parent.parent
native = Path(sys.argv[1]).resolve()
pin = '92b931b9fb5eef7f1317cb482917dfc19aceebd9'
paths = ['rpcs3/Emu/RSX/rsx_profiler.h', 'rpcs3/Emu/RSX/rsx_profiler.cpp',
         'rpcs3/Emu/RSX/RSXThread.cpp']

def function(source, name):
    start = source.index('\tvoid ' + name + '(')
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

def ios_prefix(source, name):
    body = function(source, name)
    end = body.index('\n#endif') + len('\n#endif')
    return body[:end] + '\n\t}'

with tempfile.TemporaryDirectory(prefix='armsx3-rsx-timing-') as directory:
    work = Path(directory)
    for path in paths:
        dest = work / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(subprocess.check_output(['git', '-C', str(native), 'show', pin + ':' + path]))
    for patch in sorted((root / 'patches').glob('*.patch')):
        subprocess.run(['git', 'apply', *['--include=' + p for p in paths], str(patch)], cwd=work, check=True)
    header = (work / paths[0]).read_text()
    source = (work / paths[1]).read_text()
    thread = (work / paths[2]).read_text()
    assert 'prof::begin_ios_timing();' in thread and 'prof::end_ios_timing();' in thread
    assert thread.index('prof::end_ios_timing();') < thread.index('rsx::prof::stop_sampler();')
    for name in ['begin_ios_timing', 'report_ios_timing', 'end_ios_timing']:
        body = function(source, name)
        for forbidden in ['ppu_thread', 'spu_thread', 'vm::', 'idm::', 'g_fxo', 'sample_guest']:
            assert forbidden not in body, (name, forbidden)
    for name in ['start_sampler', 'set_enabled']:
        assert 'return;' in ios_prefix(source, name)
    assert source.count('g_enabled.store(') == 1  # Original non-iOS full profiler only.
    (work / 'util').mkdir()
    (work / 'util/types.hpp').write_text('#pragma once\n#include <cstdint>\n#include <cstddef>\nusing u8=uint8_t; using u16=uint16_t; using u32=uint32_t; using u64=uint64_t; using usz=size_t;\n')
    (work / 'util/tsc.hpp').write_text('#pragma once\n#include "types.hpp"\nnamespace utils { inline thread_local u64 now=100; inline u64 frequency=1000; inline u64 get_tsc(){return now;} inline u64 get_tsc_freq(){return frequency;} }\n')
    (work / 'TargetConditionals.h').write_text('#define TARGET_OS_IOS 1\n')
    code = r'''
#include <cassert>
#include <cstdio>
#include <string>
#include <thread>
#include <vector>
#include "rpcs3/Emu/RSX/rsx_profiler.h"
namespace fmt {
void append(std::string& out, const char* format, const char* name, double percent) {
 char buffer[128]; std::snprintf(buffer,sizeof(buffer),format,name,percent); out += buffer;
}
}
struct Report { u64 frames; double wall, average; unsigned final; std::string detail; };
struct Log {
 std::vector<Report> reports;
 void success(const char*) {}
 void success(const char*,u64 frames,double wall,double average,unsigned final,const std::string&detail) {
  reports.push_back({frames,wall,average,final,detail});
 }
} prof_log;
namespace rsx::prof {
std::atomic<bool> g_enabled{false}; accounting g_acc{};
std::atomic<u64> g_last_frame_tsc{0}; bucket g_current=bucket::unclassified;
u64 g_last_switch=0; const void* g_owner_thread=nullptr;
u64 g_method_ticks[method_slot_count]{};
std::atomic<const void*> g_ios_timing_owner{nullptr};
/* FUNCTIONS */
}
using namespace rsx::prof;
u64 ticks(bucket b) { return g_acc.ticks[static_cast<usz>(b)]; }
void advance(u64 value) { utils::now += value; }
int main() {
 start_sampler(); set_enabled(true); assert(!enabled() && !timing_enabled());
 { scope ignored(bucket::vertex); advance(50); } assert(g_acc.window_start==0);
 utils::now=100; begin_ios_timing(); assert(timing_enabled() && !enabled());
 advance(1000);
 {
  scope outer(bucket::vertex); advance(1000);
  { scope inner(bucket::fence_wait); advance(1000); }
  advance(1000);
 }
 assert(ticks(bucket::vertex)==2000 && ticks(bucket::fence_wait)==1000);
 std::thread foreign([] {
  assert(!timing_enabled()); scope ignored(bucket::texture_upload);
  utils::now=1000000; report_ios_timing(true); end_ios_timing();
 }); foreign.join();
 assert(timing_enabled() && prof_log.reports.empty());
 advance(2000); tick_frame(); assert(g_acc.frames==1 && prof_log.reports.empty());
 advance(4000); tick_frame(); assert(prof_log.reports.size()==1);
 const auto first=prof_log.reports.back();
 assert(first.frames==2 && first.wall==10000 && first.average==5000 && first.final==0);
 assert(first.detail.find("Vertex/index=20.0%")!=std::string::npos);
 assert(first.detail.find("Fence wait=10.0%")!=std::string::npos);
 assert(first.detail.find("Unclassified=70.0%")!=std::string::npos);
 // A report inside nested scopes preserves the active bucket and its parent.
 {
  scope outer(bucket::vertex); advance(6000);
  { scope inner(bucket::fence_wait); advance(4000); tick_frame(); advance(2000); }
  advance(1000); outer.close(); outer.close();
 }
 assert(ticks(bucket::fence_wait)==2000 && ticks(bucket::vertex)==1000);
 advance(1000); end_ios_timing(); assert(!timing_enabled());
 assert(prof_log.reports.size()==3 && prof_log.reports.back().final==1);
 assert(prof_log.reports.back().wall==4000 && prof_log.reports.back().frames==0);
 assert(prof_log.reports.back().detail.find("Fence wait=50.0%")!=std::string::npos);
 // New game on the SAME pthread starts with fresh clocks and frame counts.
 advance(100); begin_ios_timing(); assert(g_acc.frames==0 && ticks(bucket::vertex)==0);
 { method_scope method(0); advance(1000); }
 assert(ticks(bucket::method_call)==1000 && g_method_ticks[0]==1000);
 end_ios_timing(); assert(prof_log.reports.back().wall==1000);
 // Zero-length and unavailable-counter windows never divide by zero.
 begin_ios_timing(); end_ios_timing(); assert(!timing_enabled());
 begin_ios_timing(); utils::frequency=0; advance(1000); tick_frame(); end_ios_timing();
 assert(!timing_enabled() && !enabled());
 std::puts("PASS: exclusive/nested RSX time; 10-second reports; foreign-thread exclusion; final Stop; same-thread restart; disabled guest sampler; zero clocks");
}
'''
    bodies = [function(source, name) for name in
              ['begin_ios_timing', 'report_ios_timing', 'end_ios_timing']]
    # name_of returns const char*, unlike the lifecycle functions.
    # Extract it separately with the same balanced-body parser.
    bodies.insert(0, function(source.replace('\tconst char* name_of(', '\tvoid name_of('), 'name_of').replace('\tvoid name_of(', '\tconst char* name_of(', 1))
    bodies += [ios_prefix(source, name) for name in ['start_sampler', 'set_enabled', 'tick_frame']]
    code = code.replace('/* FUNCTIONS */', '\n'.join(bodies))
    (work / 'test.cpp').write_text(code)
    binary = work / 'test'
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-pthread', '-D__APPLE__=1',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-I', str(work),
                    str(work/'test.cpp'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, env={**os.environ, 'ASAN_OPTIONS':'detect_leaks=0'})

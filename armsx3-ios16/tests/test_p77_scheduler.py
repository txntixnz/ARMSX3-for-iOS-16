"""Build99 regression: P77 admits both workers to native LV2 before blocking.
The inherited scalar fixture keeps P2-P76 frozen. Full slow-path extraction
and modeled native worker lifecycle are in test_p77_pair.py.
"""
from pathlib import Path
import plistlib,runpy
here=Path(__file__).resolve().parent
runpy.run_path(str(here/'test_p77_fixture.py'))
s=(here.parent/'core/loadtest/CoreBridge.cpp').read_text().split('// Build98 adds native blocking semaphore wait/post queue handoff.',1)[1]
assert s.count('armsx3_ios_ppu_probe_mutex_scheduler_and_call(owner, peer.get(), invokeScope, &scopeWork)')==1
scope=s.index('auto scopeWork = [&]() -> int {')
assert scope<s.index('for (u32 transaction = 0; transaction < 3; ++transaction)',scope)
assert 'cleanup.join(); throw;' in s[scope:]
assert s.index('(*peer)(); joined = true;',scope)<s.index('return program.jobs[0].result;',scope)
assert 'armsx3_ios_ppu_probe_mutex_timeout_state(job.waiter, &context, 2000000) == 1' in s
assert s.index('P77 observed native semaphore FIFO waiter')<s.index('job.observations->fetch_add')
assert 'if (job.observeQueue && job.waiter)' in s and 'job.waiter->state += cpu_flag::exit' in s
assert '!(context.state & cpu_flag::suspend) && !(context.state & cpu_flag::signal)' in s
info=plistlib.loads((here.parent/'core/loadtest/Info.plist.in').read_bytes())
assert info['CFBundleVersion']=='99' and info['MinimumOSVersion']=='16.0'
print('PASS: Build99 P77 guarded native scheduler scope, peer join before restoration, queued deadline observation, failure wake, clean signal/suspend checks, unchanged P2-P76 and iOS16 metadata')

"""P90-P93 extracted native reader/writer contention workload.
Usage: test_p90_pair.py PPUThread.cpp CoreBridge.cpp sys_ppu_thread_.cpp [reader_fifo|reader_priority|writer_fifo|writer_priority]
Native APIs, constructor, queues, diagnostic scope, SC/binder and guest slices
run on explicit CPU/VM/ID/atomic storage/clock/scheduler host models.
"""
from pathlib import Path
from collections import Counter
import re,sys
profile=sys.argv.pop() if len(sys.argv)==5 else 'reader_fifo'
assert profile in ('reader_fifo','reader_priority','writer_fifo','writer_priority'),profile
write=profile.startswith('writer_')
symbol='armsx3_core_test_rwlock_'+profile
parent=Path(__file__).with_name('test_p79_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
def replace(a,b):
 global source
 assert a in source,a
 source=source.replace(a,b)
replace('P79','P90-P93');replace('armsx3_core_test_semaphore_timeout_then_wake',symbol)
replace("lv2_sema',a)","lv2_rwlock',a)")
replace('==119','==182')
replace('using std::atomic<T>::atomic;', 'using std::atomic<T>::atomic;void release(T x){this->store(x,std::memory_order_release);}T compare_and_swap(T old,T value){this->compare_exchange_strong(old,value);return old;}template<class F>void atomic_op(F f){this->fetch_op(f);}')
replace('using shared_mutex=std::mutex;', 'struct shared_mutex:std::mutex{void lock_unlock(){std::lock_guard lock(*this);}};')
replace('semaphore_source=(native/', "rwlock_header=(native/'lv2/sys_rwlock.h').read_text();rwlock_source=(native/'lv2/sys_rwlock.cpp').read_text()\nsemaphore_source=(native/")
a=source.index('for code,name in [(90,');b=source.index('# Atomic storage',a)
source=source[:a]+'''for code,name in [(120,'create'),(121,'destroy'),(122,'rlock'),(123,'tryrlock'),(124,'runlock'),(125,'wlock'),(126,'trywlock'),(127,'wunlock')]:
 assert re.search(r'BIND_SYSC\\(sys_rwlock_'+name+r'\\),\\s*//'+str(code)+r'\\s+\\(0x'+f'{code:03x}'+r'\\)',lv2,re.I)
assert re.search(r'BIND_SYSC\\(_sys_rwlock_trywlock\\),\\s*//148',lv2)
assert 'constexpr auto _sys_rwlock_trywlock = sys_rwlock_trywlock;' in rwlock_header
assert 'id_base = 0x88000000' in rwlock_header
'''+source[b:]
replace('std::string_view(text).starts_with("sys_semaphore_wait(")', '(std::string_view(text).starts_with("sys_rwlock_rlock(") || std::string_view(text).starts_with("sys_rwlock_wlock("))')
replace('}sys_semaphore,ppu_log;', '}sys_rwlock,ppu_log;')
replace('struct sys_semaphore_attribute_t', 'struct sys_rwlock_attribute_t')
a=source.index('struct lv2_sema:lv2_obj{');b=source.index('class idm{',a)
source=source[:a]+'''struct lv2_rwlock:lv2_obj{
 static constexpr u32 id_base=0x88000000;
 const u32 protocol;const u64 key,name;shared_mutex mutex;atomic_t<s64>owner{0};ppu_thread*rq=nullptr,*wq=nullptr;
"""+rwlock_header[rwlock_header.index('lv2_rwlock(u32 protocol,'):rwlock_header.index('lv2_rwlock(utils::serial')].strip()+r"""
};
'''+source[b:]
replace('shared_ptr<lv2_sema>','shared_ptr<lv2_rwlock>');replace('lv2_sema::id_base','lv2_rwlock::id_base')
# A failed native withdrawal is injected only inside a worker; root cleanup
# must be able to remove its already-destroyed ghost after the workers join.
replace('fault==212 && ptr->exists==0', 'fault==212 && ptr->exists==0 && get_current_cpu_thread()!=nullptr')
a=source.index("services='\\n'.join");b=source.index('table=r"""',a)
source=source[:a]+r'''
queue_signature='static T* unqueue(T*& first, T* object, T* T::* mem_ptr = &T::next_cpu)\n\t{'
assert queue_signature in extras
extras=extras.replace(queue_signature,queue_signature+'if(fault==265 && mem_ptr==&T::next_cpu){return {};}')
services='\n'.join(function(rwlock_source,'error_code sys_rwlock_'+name+'(') for name in ['create','destroy','rlock','tryrlock','runlock','wlock','trywlock','wunlock'])
services+='\nconstexpr auto _sys_rwlock_trywlock=sys_rwlock_trywlock;\n'
# Independent host mutations of native service branches. Baseline bodies are
# extracted unchanged; these must fail the production workload's oracle.
services=services.replace('ppu.gpr[3] = CELL_ETIMEDOUT;', 'ppu.gpr[3] = fault==263?u64(CELL_OK):u64(CELL_ETIMEDOUT);')
services=services.replace('val -= 2;', 'if(fault!=311){val -= 2;}')
services=services.replace('val = val - 2;', 'val = fault==311?val:val - 2;')
services=services.replace('protocol != SYS_SYNC_FIFO && protocol != SYS_SYNC_PRIORITY', 'fault!=312 && protocol != SYS_SYNC_FIFO && protocol != SYS_SYNC_PRIORITY')
services=services.replace('return CELL_EPERM;', 'return fault==313?CellError{}:CELL_EPERM;')
services=services.replace('return CELL_EDEADLK;', 'return fault==314?CellError{}:CELL_EDEADLK;')
services=services.replace('return not_an_error(CELL_EBUSY);', 'return fault==315?u32(CELL_OK):u32(not_an_error(CELL_EBUSY));')
services=services.replace('return CELL_EBUSY;', 'return fault==316?CellError{}:CELL_EBUSY;')
services=services.replace('rwlock->owner.release(-2 * static_cast<s64>(size));', 'rwlock->owner.release(fault==317?0:-2 * static_cast<s64>(size));')
services=services.replace('rwlock->owner &= -2;', 'if(fault!=318){rwlock->owner &= -2;}')
# Only rlock has this timeout branch; the native reader timeout keeps wait bit.
services=services.replace('ppu.gpr[3] = fault==263?u64(CELL_OK):u64(CELL_ETIMEDOUT);\n\t\t\t\tbreak;', 'if(fault==319 && ppu.gpr[11]==122){rwlock->owner &= -2;}ppu.gpr[3] = fault==263?u64(CELL_OK):u64(CELL_ETIMEDOUT);\n\t\t\t\tbreak;')
services=services.replace('rwlock->owner = cpu->id << 1 | !!rwlock->wq | !!rwlock->rq;', 'rwlock->owner = fault==320?0:cpu->id << 1 | !!rwlock->wq | !!rwlock->rq;')
''' +source[b:]
a=source.index(' table[90]=');b=source.index('return table;}();',a)
entries=[(120,'sys_rwlock_create'),(121,'sys_rwlock_destroy'),(122,'sys_rwlock_rlock'),(123,'sys_rwlock_tryrlock'),(124,'sys_rwlock_runlock'),(125,'sys_rwlock_wlock'),(126,'sys_rwlock_trywlock'),(127,'sys_rwlock_wunlock'),(148,'_sys_rwlock_trywlock')]
source=source[:a]+''.join(f' table[{code}]={{BIND_FUNC({name}),"{name}"}};\n' for code,name in entries)+source[b:]
needle='phase=function(bridge,\'extern "C" __attribute__((visibility("default"))) int '+symbol+'(\')'
replace(needle, 'phase=function(bridge,\'static int armsx3_core_test_rwlock_batch(\')+"\\n"+function(bridge,\'extern "C" __attribute__((visibility("default"))) int '+symbol+'(\')')
replace('executed==936 && tls_stores==78 && output_stores==156', 'executed==1440 && tls_stores==120 && output_stores==240')
replace('semaphore_timeout_observations==15', 'semaphore_timeout_observations==21')
a=source.index('assert(syscall_usage.stat[90]');b=source.index("\n''' +checks[b:]",a)
first=[120,120,123,126,124,124,127,123,123,124,125 if write else 122,125 if write else 122,126,127 if write else 124,125,127,121,125,121,122]
second=[120,124,122,148,121,126,126,125,127,123 if write else 126,121,124 if write else 127,127 if write else 123,124,126,124,123,127,124,148]
counts=Counter(first+second)
source=source[:a]+'assert('+ ' && '.join(f'syscall_usage.stat[{c}]=={n*3}' for c,n in sorted(counts.items()))+');'+source[b:]
for old,new in [(13,20),(26,40),(39,60)]:replace(f'TLS={old}/{old}',f'TLS={new}/{new}')
faults=[2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,26,27,36,37,38,39,40,41,60,173,174,175,176,177,179,180,22,212,213,214,216,224,260,261,262,263,265,266,311,312,313,314,315,316]
faults+= [318,320] if write else [317,319]
source=re.sub(r'const std::vector<int> faults\{[0-9,]+\};','const std::vector<int> faults{'+','.join(map(str,faults))+'};',source)
replace('const u32 priorID=0x9600ff01;', 'const u32 priorID=0x8800ff01;')
replace('std::make_shared<lv2_sema>(1,0,0,3,2)', 'std::make_shared<lv2_rwlock>(1,0,0)')
a=source.index(' std::puts("PASS: P90-P93');b=source.index("''' +checks[b:]",a)
source=source[:a]+' std::puts("PASS: '+profile+' P90-P93 extracted native8rwlock APIs/alias148/constructor/queues/scheduler scope/SC/binder/TLS/bounded;8runs/16workers/120SC each/three shared-reader and exclusive-writer lifecycles/timeout-retry-unlock wake/exact counts and wait flags/full context/cleanup;applicable setup/ABI/registry/ownership/count/permission/timeout/wake mutations detected;CPU/VM/ID allocator/atomic storage/clock/scheduler are host models;native iOS pending.");'+source[b:]
instrument=r"""checks=checks.replace('void restored(){', 'void restored(){if(!(id_manager::g_id==0 && idm::objects.empty() && !lv2_obj::g_ppu && !g_scheduler_ready && !lv2_obj::g_priority_order_tag.load())){std::fprintf(stderr,"restore fault=%u objects=%zu ready=%u priority=%llu",fault,idm::objects.size(),unsigned(bool(g_scheduler_ready)),(unsigned long long)lv2_obj::g_priority_order_tag.load());std::fputc(10,stderr);}')"""
source=source.replace('\nwith tempfile.TemporaryDirectory', '\n'+instrument+'\nwith tempfile.TemporaryDirectory')
source=source.replace('str(binary)],check=True)', 'str(binary)],check=True,timeout=180)')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

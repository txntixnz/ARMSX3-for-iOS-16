"""P94-P97 extracted native event queue/local port workload.
Usage: test_p94_pair.py PPUThread.cpp CoreBridge.cpp sys_ppu_thread_.cpp [fifo|priority|cancel_fifo|cancel_priority]
Native APIs, constructors, queue send, binder, SC, slices and probe helpers
run on CPU/VM/ID/atomic/clock/scheduler/notification host models. SPU paths reject.
"""
from pathlib import Path
from collections import Counter
import re,sys
event_profile=sys.argv.pop() if len(sys.argv)==5 else 'fifo'
assert event_profile in ('fifo','priority','cancel_fifo','cancel_priority')
parent=Path(__file__).with_name('test_p90_pair.py').read_text()
exec(compile(parent[:parent.rindex('\nexec(compile(source,')],str(Path(__file__).resolve()),'exec'))
profile=event_profile;cancel=profile.startswith('cancel_');event_symbol='armsx3_core_test_event_queue_'+profile
def replace(a,b):
 global source
 assert a in source,a
 source=source.replace(a,b)
replace('P90-P93','P94-P97');replace(symbol,event_symbol)
replace("lv2_rwlock',a)","lv2_event_queue',a)")
replace('rwlock_header=(native/', "event_header=(native/'lv2/sys_event.h').read_text();event_source=(native/'lv2/sys_event.cpp').read_text()\nrwlock_header=(native/")
a=source.index('for code,name in [(120,');b=source.index('# Atomic storage',a)
source=source[:a]+'''entries=[(128,'sys_event_queue_create'),(129,'sys_event_queue_destroy'),(130,'sys_event_queue_receive'),(131,'sys_event_queue_tryreceive'),(133,'sys_event_queue_drain'),(134,'sys_event_port_create'),(135,'sys_event_port_destroy'),(136,'sys_event_port_connect_local'),(137,'sys_event_port_disconnect'),(138,'sys_event_port_send')]
for code,name in entries:
 assert re.search(r'BIND_SYSC\\('+name+r'\\),\\s*//'+str(code)+r'\\s+\\(0x'+f'{code:03x}'+r'\\)',lv2,re.I)
assert 'id_base = 0x8d000000' in event_header and 'id_base = 0x0e000000' in event_header
'''+source[b:]
# Event APIs accept cpu_thread& and use CPU downcasts and shared state. These
# interfaces are modeled; native binder context detection is retained.
needle='extras=r"""'
extra=r'''
shims=shims.replace('static cpu_thread*get_current(){return current;}', 'template<class T> T*try_get(){return dynamic_cast<T*>(this);}template<class T=cpu_thread>static T*get_current(){return current?current->try_get<T>():nullptr;}flags state;virtual bool check_state();cpu_thread*get_next_cpu();std::string get_name(){return "host CPU";}')
shims=shims.replace('flags state;notification cmd_notify;', 'notification cmd_notify;')
shims=shims.replace('void*get_current_cpu_thread(){', 'cpu_thread*get_current_cpu_thread(){')
shims=shims.replace('struct ppu_thread:cpu_thread{', 'struct ppu_thread:cpu_thread{bool loaded_from_savestate=false;')
shims=shims.replace('bool IsStopped()const{return stopped;}', 'bool IsStopped()const{return stopped;}bool IsVsh()const{return false;}')
shims=shims.replace('auto*operator->()const{return &**this;}', 'auto*operator->()const{return &**this;}auto*get_ptr()const{return &**this;}')
shims+='\nbool cpu_thread::check_state(){throw std::runtime_error("unexpected base CPU state check");}cpu_thread*cpu_thread::get_next_cpu(){if(auto*p=try_get<ppu_thread>())return p->next_cpu;throw std::runtime_error("unexpected SPU queue");}\n'
'''
replace('CELL_ESRCH=0x80010005,','CELL_EAGAIN=0x80010001,CELL_ECANCELED=0x80010013,CELL_EISCONN=0x80010015,CELL_ENOTCONN=0x80010016,CELL_ESRCH=0x80010005,')
replace('constexpr u32 SYS_SYNC_FIFO=1', 'constexpr s32 SYS_EVENT_PORT_LOCAL=1,SYS_EVENT_PORT_IPC=3,SYS_EVENT_QUEUE_DESTROY_FORCE=1;constexpr u32 SYS_PPU_QUEUE=1,SYS_SPU_QUEUE=2,SYS_SYNC_NEWLY_CREATED=1,SYS_SYNC_PROCESS_SHARED=0x100;constexpr u64 SYS_EVENT_QUEUE_LOCAL=0;\nconstexpr u32 SYS_SYNC_FIFO=1')
a=source.index(' void trace(const char*text,u32,u64 timeout)');b=source.index(' template<class...T>void trace(',a)
source=source[:a]+r'''
 template<class P>void trace(const char*text,u32,P,u64 timeout){if(std::string_view(text).starts_with("sys_event_queue_receive(")){
  auto*c=static_cast<ppu_thread*>(get_current_cpu_thread());if(!c||timeout!=c->gpr[5])throw std::runtime_error("native event timeout truncated");++semaphore_timeout_observations;
 }}
'''+source[b:]
replace('template<class...T>void warning(const char*,T...){}', 'struct Warning{operator bool()const{return false;}template<class...T>void operator()(const char*,T...)const{}}warning;')
replace('}sys_rwlock,ppu_log;', '}sys_event,ppu_log;')
replace('namespace fmt{template<class...T>[[noreturn]]', 'namespace fmt{template<class...T>void append(std::string&,const char*,T...){}template<class...T>[[noreturn]]')
a=source.index('struct sys_rwlock_attribute_t');b=source.index('struct lv2_obj{',a)
source=source[:a]+r'''
using lv2_event=std::tuple<u64,u64,u64,u64>;
struct sys_event_queue_attribute_t{be_t<u32>protocol;be_t<s32>type;union{u64 name_u64;char name[8];};};
struct sys_event_t{be_t<u64>source,data1,data2,data3;};
struct spu_thread:cpu_thread{spu_thread*next_cpu=nullptr;Priority prio;struct Mailbox{template<class...T>void set_values(T...){throw std::runtime_error("SPU queues outside host workload");}}ch_in_mbox;};
void resume_spu_thread_group_from_waiting(spu_thread&,std::array<shared_ptr<named_thread<spu_thread>>,8>&){throw std::runtime_error("SPU wake outside host workload");}
s32 process_getpid(){return 1;}
namespace id_manager{std::recursive_mutex g_mutex;}
'''+source[b:]
replace('struct lv2_obj{', 'struct lv2_obj{virtual~lv2_obj()=default;template<class T>static bool check(const shared_ptr<T>&obj){return obj && obj->exists.load()!=0;}')
a=source.index('struct lv2_rwlock:lv2_obj{');b=source.index('atomic_t<u64>g_sema_wait_us',a)
source=source[:a]+r'''
struct lv2_event_port;
struct lv2_event_queue:lv2_obj{
 static constexpr u32 id_base=0x8d000000;const u32 id,protocol;const u8 type,size;const u64 name,key;
 shared_mutex mutex;std::deque<lv2_event>events;spu_thread*sq=nullptr;ppu_thread*pq=nullptr;
 lv2_event_queue(u32,s32,s32,u64,u64)noexcept;CellError send(lv2_event,bool*,lv2_event_port*);
 CellError send(u64 a,u64 b,u64 c,u64 d,bool*notify=nullptr,lv2_event_port*port=nullptr){return send(std::make_tuple(a,b,c,d),notify,port);}
};
struct lv2_event_port:lv2_obj{
 static constexpr u32 id_base=0x0e000000;const s32 type;const u64 name;atomic_t<usz>is_busy{0};shared_ptr<lv2_event_queue>queue;
"""+event_header[event_header.index('lv2_event_port(s32 type,'):event_header.index('lv2_event_port(utils::serial')].strip()+r"""
};
class idm{public:
 static inline std::recursive_mutex guard;static inline std::map<u32,shared_ptr<lv2_obj>>objects;static inline u32 cookie=0;
 template<class T>static u32 last_id(){return fault==214?0xdeadbeef:id_manager::g_id;}
 template<class B,class T>static shared_ptr<T>get_unlocked(u32 id){std::lock_guard lock(guard);auto it=objects.find(id);if(it==objects.end()||(id&0xff000000u)!=T::id_base)return {};return std::static_pointer_cast<T>(it->second);}
 template<class B,class T>static shared_ptr<T>check_unlocked(u32 id){return get_unlocked<B,T>(id);}
 template<class B,class T,class F>static u32 import(F make){
  std::lock_guard lock(guard);if(!fxo.mutexRegistryReady)return 0;const u32 id=T::id_base+0x800+(++cookie&255);id_manager::g_id=id;
  auto object=make();if(!object)return 0;object->exists=fault==216?2:1;objects[id]=object;return id;
 }
 template<class B,class T,class...A>static u32 make(A&&...a){return import<B,T>([&]{return std::make_shared<T>(std::forward<A>(a)...);});}
 template<class T,class R>struct Pair{shared_ptr<T>ptr;R ret{};explicit operator bool()const{return bool(ptr);}T*operator->()const{return ptr.get();}};
 template<class B,class T,class F>static auto get(u32 id,F f){std::lock_guard lock(guard);auto ptr=get_unlocked<B,T>(id);using R=std::invoke_result_t<F,T&>;
  if constexpr(std::is_void_v<R>){if(!ptr)return shared_ptr<T>{};f(*ptr);return ptr;}else{if(!ptr)return Pair<T,R>{};return Pair<T,R>{ptr,f(*ptr)};}}
 template<class B,class T,class F>static auto check(u32 id,F f){return get<B,T>(id,std::move(f));}
 template<class B,class T,class F>static Pair<T,CellError>withdraw(u32 id,F f){std::lock_guard lock(guard);auto ptr=get_unlocked<B,T>(id);if(!ptr)return {};const CellError error=f(*ptr);if(!error && !(fault==212 && ptr->exists==0 && get_current_cpu_thread()!=nullptr))objects.erase(id);return {ptr,error};}
 template<class B,class T,class F>static u32 select(F f){std::lock_guard lock(guard);u32 n=0;for(auto&e:objects)if((e.first&0xff000000u)==T::id_base){f(e.first,*e.second);++n;}return n;}
};
template<class T,class F>error_code lv2_obj::create(u32 shared,u64 key,s32,F make){assert(shared==SYS_SYNC_NOT_PROCESS_SHARED && !key);return idm::import<lv2_obj,T>(make)?CELL_OK:u32(CELL_EAGAIN);}
''' +source[b:]
# Replace services and mutations, retaining native scheduler scope and observers.
a=source.index("services='\\n'.join");b=source.index('table=r"""',a)
source=source[:a]+extra+r'''
constructor=event_source[event_source.index('lv2_event_queue::lv2_event_queue(u32 protocol,'):event_source.index('lv2_event_queue::lv2_event_queue(utils::serial')].strip()
extras+=constructor+'\n'+function(event_source,'CellError lv2_event_queue::send(lv2_event event,')+'\n'
services='\n'.join(function(event_source,'error_code '+name+'(') for _,name in entries)
services=services.replace('ppu.gpr[3] = CELL_ETIMEDOUT;', 'ppu.gpr[3] = fault==263?u64(CELL_OK):u64(CELL_ETIMEDOUT);')
# Payload, overflow, draining, connection and cancellation mutations.
extras=extras.replace('events.emplace_back(event);','if(fault==341){std::get<2>(event)^=1;}events.emplace_back(event);')
extras=extras.replace('std::tie(ppu.gpr[4], ppu.gpr[5], ppu.gpr[6], ppu.gpr[7]) = event;', 'std::tie(ppu.gpr[4], ppu.gpr[5], ppu.gpr[6], ppu.gpr[7]) = event;if(fault==342)ppu.gpr[7]^=1;')
extras=extras.replace('return CELL_EBUSY;', 'return fault==343?CellError{}:CELL_EBUSY;')
services=services.replace('queue.events.clear();','if(fault!=344){queue.events.clear();}')
services=services.replace('return CELL_EISCONN;', 'return fault==345?CellError{}:CELL_EISCONN;')
services=services.replace('return CELL_ENOTCONN;', 'return fault==346?CellError{}:CELL_ENOTCONN;')
services=services.replace('port->queue.reset();','if(fault!=347){port->queue.reset();}')
services=services.replace('*number = count;', '*number = fault==348?count+1:count;')
services=services.replace('const u64 source = port.name ? port.name :', 'const u64 source = fault==349?0:port.name ? port.name :')
services=services.replace('cpu->gpr[3] = CELL_ECANCELED;', 'cpu->gpr[3] = fault==350?u64(CELL_OK):u64(CELL_ECANCELED);')
services=services.replace('return CELL_EBUSY;', 'return fault==351?CellError{}:CELL_EBUSY;')
services=services.replace('if (mode && mode != SYS_EVENT_QUEUE_DESTROY_FORCE)', 'if (fault!=352 && mode && mode != SYS_EVENT_QUEUE_DESTROY_FORCE)')
services=services.replace('std::tie(dest.source, dest.data1, dest.data2, dest.data3) = queue->events.front();', 'std::tie(dest.source, dest.data1, dest.data2, dest.data3) = queue->events.front();if(fault==353)dest.data1=u64(dest.data1)^1;')
''' +source[b:]
a=source.index(' table[120]=');b=source.index('return table;}();',a)
entries=[(128,'sys_event_queue_create'),(129,'sys_event_queue_destroy'),(130,'sys_event_queue_receive'),(131,'sys_event_queue_tryreceive'),(133,'sys_event_queue_drain'),(134,'sys_event_port_create'),(135,'sys_event_port_destroy'),(136,'sys_event_port_connect_local'),(137,'sys_event_port_disconnect'),(138,'sys_event_port_send')]
source=source[:a]+''.join(f' table[{code}]={{BIND_FUNC({name}),"{name}"}};\n' for code,name in entries)+source[b:]
replace("static int armsx3_core_test_rwlock_batch(","static int armsx3_core_test_event_queue_batch(")
replace('semaphore_timeout_observations==21','semaphore_timeout_observations==9')
a=source.index('assert(syscall_usage.stat[120]');b=source.index("\n''' +checks[b:]",a)
first=[128,131,136,135,138,130,130,131,128 if cancel else 131,136 if cancel else 131,138,131,138,138 if cancel else 133,128,137,129,138,130,135]
second=[134,134,136,137,136,129,129 if cancel else 138,138,138,138,131,133,138,133 if cancel else 131,129,135,133,131,136,129]
counts=Counter(first+second)
source=source[:a]+'assert('+ ' && '.join(f'syscall_usage.stat[{c}]=={n*3}' for c,n in sorted(counts.items()))+');'+source[b:]
faults=[2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,26,27,36,37,38,39,40,41,60,173,174,175,176,177,179,180,22,212,213,214,216,224,260,261,263,265,266,341,343,344,345,346,347,348,349,351,352,353]
faults+= [350] if cancel else [342]
source=re.sub(r'const std::vector<int> faults\{[0-9,]+\};','const std::vector<int> faults{'+','.join(map(str,faults))+'};',source)
replace('const u32 priorID=0x8800ff01;','const u32 priorID=0x8d00ff01;')
replace('std::make_shared<lv2_rwlock>(1,0,0)', 'std::make_shared<lv2_event_queue>(1,SYS_PPU_QUEUE,2,0,0)')
a=source.index(' std::puts("PASS: reader_fifo');b=source.index("''' +checks[b:]",a)
source=source[:a]+' std::puts("PASS: '+profile+' P94-P97 native10event APIs/queue-send/constructors/binder/SC/TLS/bounded/scheduler scope;8runs/16workers/120SC each/three timeout then delivery-or-cancellation linked lifecycles/full64 payload-source-GPR output/tryreceive-array-count-capacity-drain/dead-port-recovery/cleanup;applicable setup/ABI/registry/payload/connection/capacity/cancellation mutations detected;CPU/VM/ID/atomic/clock/scheduler/notification are host models;SPU/IPC/serialized paths outside workload;native iOS pending.");'+source[b:]
replace("b=extras.index('\\n};\\nstruct lv2_event_queue',a)", "b=extras.index('\\n};\\n\\nstruct lv2_event_port;',a)")
exec(compile(source,str(Path(__file__).resolve()),'exec'))

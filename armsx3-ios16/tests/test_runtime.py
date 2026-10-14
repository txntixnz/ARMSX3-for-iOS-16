"""Compile production runtime/frontend with the native callback ABI and BootGame.
Load/VM/FXO/device/config backends are host interfaces, not a native game boot.
The host exercises success, partial loading, failed firmware, callback errors,
delayed teardown and timeout. UIKit dispatch is checked separately in source.
"""
from pathlib import Path
import re,subprocess,sys,tempfile
root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
read=lambda p:(native/p).read_text()
callbacks=read('rpcs3/Emu/emu_callbacks.h')
system=read('rpcs3/Emu/System.cpp')
boot=system[system.index('game_boot_result Emulator::BootGame('):system.index('\nvoid Emulator::SetContinuousMode(')]
frontend=(root/'core/loadtest/RuntimeFrontend.cpp').read_text()
runtime=(root/'core/loadtest/Runtime.cpp').read_text()
strip=lambda s:re.sub(r'^#(?:include[^\n]*|pragma once)\n','',s,flags=re.M)
assert set(re.findall(r'>\s+(\w+)\s*(?:;|=)',callbacks))==set(re.findall(r'g_emu_callbacks\.(\w+)\s*=',frontend))
assert 'std::exchange(m_force_boot, false) || g_cfg.misc.autostart' in system
assert 'm_config_mode == cfg_mode::config_override' in system and 'g_cfg.from_string(cfg_file.to_string())' in system
assert 'cpu_thread::cleanup();' in system and 'm_state = system_state::stopped;' in system
dispatch=(root/'core/loadtest/RuntimeDispatch.mm').read_text()
assert 'dispatch_async(dispatch_get_main_queue(), invoke)' in dispatch
assert 'dispatch_sync(dispatch_get_main_queue(), ^{})' in dispatch
assert '*wake_up = 1; wake_up->notify_one()' in dispatch
prelude=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <memory>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <tuple>
#include <utility>
#include <vector>
using u8=std::uint8_t;using u32=std::uint32_t;using s32=std::int32_t;using u64=std::uint64_t;using f32=float;
template<class T>struct atomic_t{std::atomic<T>value;atomic_t(T v={}):value(v){}operator T()const{return value.load();}atomic_t&operator=(T v){value.store(v);return *this;}void notify_one(){value.notify_one();}};
namespace utils{struct serial{};}namespace stx{template<class T>using shared_ptr=std::shared_ptr<T>;template<class T>struct atomic_ptr{};}
namespace cfg{struct _base{};}
enum class localized_string_id{placeholder};
struct GSFrameBase{virtual~GSFrameBase()=default;};
struct camera_handler_base{virtual~camera_handler_base()=default;};struct null_camera_handler:camera_handler_base{};
struct music_handler_base{virtual~music_handler_base()=default;};struct null_music_handler:music_handler_base{};
struct AudioBackend{virtual~AudioBackend()=default;};struct NullAudioBackend:AudioBackend{};
struct audio_device_enumerator{virtual~audio_device_enumerator()=default;};struct null_enumerator:audio_device_enumerator{};
struct KeyboardHandlerBase{explicit KeyboardHandlerBase(utils::serial*){}virtual~KeyboardHandlerBase()=default;};struct NullKeyboardHandler:KeyboardHandlerBase{using KeyboardHandlerBase::KeyboardHandlerBase;};
struct MouseHandlerBase{explicit MouseHandlerBase(utils::serial*){}virtual~MouseHandlerBase()=default;};struct NullMouseHandler:MouseHandlerBase{using MouseHandlerBase::MouseHandlerBase;};
struct pad_thread{pad_thread(void*,void*,std::string_view){}};
enum cpu_flag:u32{stop=1};struct ppu_thread{u32 state=cpu_flag::stop;};
namespace rsx{struct thread{virtual~thread()=default;};}struct NullGSRender:rsx::thread{explicit NullGSRender(utils::serial*){}};
template<class T>struct named_thread:T{template<class...A>named_thread(A&&...a):T(std::forward<A>(a)...){}};
enum class MsgDialogState{Open,Close};
struct MsgDialogBase{
 atomic_t<MsgDialogState>state{MsgDialogState::Close};virtual~MsgDialogBase()=default;
 virtual void Create(const std::string&,const std::string&)=0;virtual void Close(bool)=0;virtual void SetMsg(const std::string&)=0;
 virtual void ProgressBarSetMsg(u32,const std::string&)=0;virtual void ProgressBarReset(u32)=0;virtual void ProgressBarInc(u32,u32)=0;
 virtual void ProgressBarSetValue(u32,u32)=0;virtual void ProgressBarSetLimit(u32,u32)=0;
};
struct OskDialogBase{};struct SaveDialogBase{};struct SendMessageDialogBase{};struct RecvMessageDialogBase{};struct TrophyNotificationBase{};struct video_source{};
enum class ppu_decoder_type{_static,llvm};enum class spu_decoder_type{_static,llvm};enum class video_renderer{null,vulkan};enum class audio_renderer{null,cubeb};
enum class keyboard_handler{null,basic};enum class mouse_handler{null,basic};enum class np_internet_status{disabled,enabled};enum class np_psn_status{disabled,enabled};
enum class cfg_mode{custom,config_override};enum class game_boot_result{no_errors,invalid_file_or_folder,nothing_to_boot,currently_restricted};
enum class system_state{stopped,stopping,ready,running};
template<class T>struct Setting{T value{};void set(T v){value=v;}T get()const{return value;}};
struct LibrarySet{std::set<std::string>value;void set_set(std::set<std::string>&&v){value=std::move(v);}};
struct cfg_root{
 struct{Setting<ppu_decoder_type>ppu_decoder;Setting<spu_decoder_type>spu_decoder;Setting<bool>llvm_precompilation;LibrarySet libraries_control;}core;
 struct{Setting<video_renderer>renderer;}video;struct{Setting<audio_renderer>renderer;}audio;
 struct{Setting<keyboard_handler>keyboard;Setting<mouse_handler>mouse;}io;
 struct{Setting<bool>autostart,autoexit,start_big_picture_mode,enable_gamemode,prevent_display_sleep;}misc;
 struct{Setting<np_internet_status>net_active;Setting<np_psn_status>psn_status;}net;
 std::string to_string()const{std::ostringstream s;s<<int(core.ppu_decoder.value)<<' '<<int(core.spu_decoder.value)<<' '<<core.llvm_precompilation.value<<' '
 <<core.libraries_control.value.count("liblv2.sprx:lle")<<' '<<int(video.renderer.value)<<' '<<int(audio.renderer.value)<<' '<<int(io.keyboard.value)<<' '<<int(io.mouse.value)<<' '
 <<misc.autostart.value<<' '<<misc.autoexit.value<<' '<<misc.start_big_picture_mode.value<<' '<<misc.enable_gamemode.value<<' '<<misc.prevent_display_sleep.value<<' '
 <<int(net.net_active.value)<<' '<<int(net.psn_status.value);return s.str();}
 bool from_string(const std::string&s){std::istringstream i(s);int p,sp,l,v,a,k,m,n,ps;i>>p>>sp>>core.llvm_precompilation.value>>l>>v>>a>>k>>m
 >>misc.autostart.value>>misc.autoexit.value>>misc.start_big_picture_mode.value>>misc.enable_gamemode.value>>misc.prevent_display_sleep.value>>n>>ps;
 core.ppu_decoder.set(ppu_decoder_type(p));core.spu_decoder.set(spu_decoder_type(sp));core.libraries_control.set_set(l?std::set<std::string>{"liblv2.sprx:lle"}:std::set<std::string>{});
 video.renderer.set(video_renderer(v));audio.renderer.set(audio_renderer(a));io.keyboard.set(keyboard_handler(k));io.mouse.set(mouse_handler(m));net.net_active.set(np_internet_status(n));net.psn_status.set(np_psn_status(ps));return !i.fail();}
}g_cfg,g_backup_cfg;
std::string host_root;int mode=0;unsigned loads=0,kills=0,drains=0;u64 workers=0;bool on_main=false;
std::vector<std::string>host_log;void ARMSX3StartupLog(const char*s){host_log.emplace_back(s);}
extern "C" u64 armsx3_ios_live_cpu_threads(){return workers;}
struct{std::string get_dev_flash()const{return host_root+"/dev_flash/";}}g_cfg_vfs;
namespace fs{
constexpr int read=1,rewrite=2;
struct file{std::string path;mutable std::ifstream input;std::ofstream output;
 file(std::string p,int m):path(std::move(p)){if(m==read)input.open(path,std::ios::binary);else output.open(path,std::ios::binary|std::ios::trunc);}
 explicit operator bool()const{return input.is_open()||output.is_open();}u64 size()const{return std::filesystem::file_size(path);}
 std::string to_string()const{return std::string(std::istreambuf_iterator<char>(input),{});}
 u64 write(const char*p,u64 n){output.write(p,n);return output?n:0;}void sync(){output.flush();}void close(){input.close();output.close();}
};
std::string get_cache_dir(){return host_root+"/cache/";}bool is_file(const std::string&p){return std::filesystem::is_regular_file(p);}
bool is_dir(const std::string&p){return std::filesystem::is_directory(p);}bool get_optical_raw_device(const std::string&){return false;}
}
enum class elf_error{ok,bad};struct ppu_exec_object{
 struct{u64 e_entry=0x20000;}header;struct Segment{u32 p_type=1,p_memsz=0x1000;};std::vector<Segment>progs{Segment{},Segment{}};
 elf_error error;explicit ppu_exec_object(const fs::file&f):error(f.to_string()=="ELF-FIXTURE"?elf_error::ok:elf_error::bad){}elf_error get_error()const{return error;}
};
struct lv2_obj{};struct MemorySegment{u32 addr=0x10000,size=0x1000,type=1;};
template<class T>struct main_ppu_module{u32 elf_entry=0x20000;std::vector<MemorySegment>segs{{},{0x20000,0x1000,1}};};
constexpr u32 PRX_STATE_STARTED=2;
struct lv2_prx{std::string path;u32 state=PRX_STATE_STARTED;std::vector<MemorySegment>segs{{}};std::vector<unsigned>funcs{1};};
std::vector<lv2_prx>modules;
struct Fxo{
 main_ppu_module<lv2_obj>main;
 std::vector<std::shared_ptr<void>>objects;
 template<class T,class Impl=T,class...A>T*init(A&&...a){auto object=std::make_shared<Impl>(std::forward<A>(a)...);T*ptr=object.get();objects.push_back(std::move(object));return ptr;}
 template<class T>T*try_get(){return mode==3?nullptr:reinterpret_cast<T*>(&main);}
}host_fxo;Fxo*g_fxo=&host_fxo;
namespace idm{template<class T,class U,class F>void select(F f){for(auto&m:modules)f(0x23000001,m);}
template<class T,class F>void select(F f){if(mode!=12){ppu_thread p;p.state=mode==11?0:u32(cpu_flag::stop);f(0x1000001,p);}}}
namespace vm{constexpr u8 page_readable=1;bool check_addr(u64,u8,u32){return mode!=4;}}
template<class T>T ensure(T v){if(!v)throw std::runtime_error("host ensure");return v;}
struct{template<class...T>void notice(const char*,T...)const{}}sys_log;
void unload_iso(){}
std::vector<std::function<void()>>main_queue;
class Emulator{
public:
 bool m_restrict_emu_state_change=false,m_force_boot=false;mutable system_state m_state=system_state::stopped;mutable unsigned ticks=0;
 std::string m_path,m_path_original,m_path_old,disc,hdd1,m_config_path;std::vector<std::string>argv,envp;std::vector<u8>data,klic;
 cfg_mode m_config_mode=cfg_mode::custom;std::optional<std::string>m_db_config;std::function<void()>after_kill_callback;
 bool IsStopped(bool fully=false)const{if(m_state==system_state::stopping&&mode!=7&&++ticks>1){m_state=system_state::stopped;workers=0;}
  return fully?m_state==system_state::stopped:m_state<=system_state::stopping;}
 bool IsReady()const{return m_state==system_state::ready;}system_state GetStatus(bool)const{return m_state;}
 utils::serial*DeserialManager(){return nullptr;}
 game_boot_result BootGame(const std::string&,const std::string&="",bool=false,cfg_mode=cfg_mode::custom,const std::string&="",const std::optional<std::string>&=std::nullopt);
 game_boot_result GetElfPathFromDir(std::string&,const std::string&){return game_boot_result::nothing_to_boot;}
 game_boot_result Load(const std::string&);
 void SetForceBoot(bool);
 void Kill(bool);
}Emu;
'''
backend=r'''
emu_callbacks g_emu_callbacks;
namespace ios_runtime{
bool is_main_thread(){return on_main;}
void dispatch_main(std::function<void()>f,atomic_t<u32>*wake){main_queue.push_back([f=std::move(f),wake]{f();if(wake){*wake=1;wake->notify_one();}});}
void drain_main_queue(){++drains;on_main=true;while(!main_queue.empty()){auto f=std::move(main_queue.front());main_queue.erase(main_queue.begin());f();}on_main=false;}
}
game_boot_result Emulator::Load(const std::string&){
 ++loads;assert(m_config_mode==cfg_mode::config_override);assert(!m_force_boot);fs::file c(m_config_path,fs::read);assert(g_cfg.from_string(c.to_string()));
 assert(!g_cfg.misc.autostart.get()&&!g_cfg.misc.autoexit.get());assert(g_cfg.core.libraries_control.value==std::set<std::string>{"liblv2.sprx:lle"});
 assert(g_cfg.core.ppu_decoder.get()==ppu_decoder_type::_static&&g_cfg.core.spu_decoder.get()==spu_decoder_type::_static);
 assert(g_cfg.video.renderer.get()==video_renderer::null&&g_cfg.audio.renderer.get()==audio_renderer::null);
 if(mode==1){m_state=system_state::stopped;return game_boot_result::invalid_file_or_folder;}
 m_state=system_state::ready;workers=2;g_emu_callbacks.on_ready();
 g_emu_callbacks.init_gs_render(nullptr);g_emu_callbacks.init_kb_handler();g_emu_callbacks.init_mouse_handler();g_emu_callbacks.init_pad_handler("");
 assert(!g_emu_callbacks.get_gs_frame());assert(g_emu_callbacks.get_audio());assert(g_emu_callbacks.get_camera_handler());assert(g_emu_callbacks.get_music_handler());
 modules={{g_cfg_vfs.get_dev_flash()+ (mode==5?"wrong.sprx":"liblv2.sprx"),PRX_STATE_STARTED,{{}},{1}}};
 if(mode==2)throw std::runtime_error("injected load failure after contexts");
 if(mode==6)g_emu_callbacks.on_run(false);
 if(mode==8)g_fxo->main.segs.pop_back();
 if(mode==9)g_fxo->main.elf_entry=0;
 if(mode==10)ios_runtime::record_frontend_failure("injected frontend failure");
 return game_boot_result::no_errors;
}
void Emulator::Kill(bool allow_autoexit){assert(!allow_autoexit);++kills;ticks=0;
 if(m_state!=system_state::stopped)m_state=system_state::stopping;
 main_queue.push_back([this]{assert(on_main);assert(m_state==system_state::stopped);workers=0;modules.clear();g_fxo->objects.clear();
  g_emu_callbacks.on_stop();g_emu_callbacks.enable_display_sleep(true);if(after_kill_callback)std::exchange(after_kill_callback,nullptr)();});
}
'''
tests=r'''
int main(int argc,char**argv){
 assert(argc==2);host_root=argv[1];std::filesystem::create_directories(host_root+"/cache");
 char detail[4096]{};assert(armsx3_core_check_runtime(detail,sizeof(detail))==-1);assert(loads==0&&kills==0);
 std::ofstream(host_root+"/cache/ARMSX3-prepared-executable.elf")<<"ELF-FIXTURE";
 assert(armsx3_core_check_runtime(detail,sizeof(detail))==-1);assert(loads==0);
 std::filesystem::create_directories(host_root+"/dev_flash/sys/external");std::ofstream(host_root+"/dev_flash/sys/external/liblv2.sprx")<<"FIRMWARE-FIXTURE";
 on_main=true;assert(armsx3_core_check_runtime(detail,sizeof(detail))==-1);on_main=false;
 Emu.m_state=system_state::stopping;mode=7;workers=0;assert(armsx3_core_check_runtime(detail,sizeof(detail))==-1);assert(loads==0);
 Emu.m_state=system_state::stopped;workers=1;assert(armsx3_core_check_runtime(detail,sizeof(detail))==-1);workers=0;
 assert(armsx3_core_check_runtime(nullptr,0)==-1);char tiny[2]{};assert(armsx3_core_check_runtime(tiny,1)==-1);assert(loads==0);
 g_cfg.core.ppu_decoder.set(ppu_decoder_type::llvm);g_cfg.video.renderer.set(video_renderer::vulkan);g_cfg.misc.autostart.set(true);g_cfg.net.net_active.set(np_internet_status::enabled);
 g_backup_cfg.misc.autoexit.set(true);const auto prior=g_cfg.to_string(),backup=g_backup_cfg.to_string();
 for(int scenario: {0,1,2,3,4,5,6,7,8,9,10,11,12,0}){
  mode=scenario;g_fxo->main={};Emu.m_state=system_state::stopped;workers=0;Emu.m_force_boot=true;
  const auto count=loads;const int result=armsx3_core_check_runtime(detail,sizeof(detail));assert(loads==count+1);
  assert(result==(scenario==0?0:((scenario==6||scenario==7||scenario==10)?-2:-1)));
  if(scenario!=7){assert(Emu.IsStopped(true)&&workers==0);assert(main_queue.empty());assert(modules.empty());assert(g_fxo->objects.empty());assert(drains>0);assert(g_cfg.to_string()==prior&&g_backup_cfg.to_string()==backup);}
  else{assert(!Emu.IsStopped(true));mode=0;Emu.m_state=system_state::stopped;workers=0;ios_runtime::drain_main_queue();g_cfg.from_string(prior);g_backup_cfg.from_string(backup);}
  assert(std::filesystem::is_regular_file(host_root+"/dev_flash/sys/external/liblv2.sprx"));
  for(const auto&p:std::filesystem::directory_iterator(host_root+"/cache"))assert(!p.path().filename().string().starts_with("ARMSX3-runtime-check-"));
 }
 assert(std::string(detail).starts_with("Native runtime load passed"));
 ios_runtime::install_frontend();atomic_t<u32>wake{0};bool dispatched=false;g_emu_callbacks.call_from_main_thread([&]{assert(on_main);dispatched=true;},&wake);
 assert(!dispatched&&!wake);ios_runtime::drain_main_queue();assert(dispatched&&wake);
 std::ofstream(host_root+"/cache/ARMSX3-prepared-executable.elf",std::ios::trunc)<<"BAD";
 const auto count=loads;assert(armsx3_core_check_runtime(detail,sizeof(detail))==-1);assert(loads==count);
 std::puts("PASS: production runtime/frontend compiled against49 native callback signatures and native BootGame; load-only override, mapped segments/firmware identity, missing inputs/idle/main-thread/C ABI guards, partial failures, delayed cleanup, timeout, queue/wake protocol and config restoration. Native Load/VM/FXO/devices/config and UIKit are host models/source contracts; actual iOS runtime loading pending.");
}
'''
# Accelerate the timeout scenario only. The native app retains its 30-second
# budget; all other production logic and the native BootGame body are unchanged.
runtime=runtime.replace('std::chrono::seconds(30)','std::chrono::milliseconds(30)')
prelude=prelude.replace('enum class cfg_mode{custom,config_override};',strip(read('rpcs3/Emu/config_mode.h')))
source=prelude+'\n'+strip(callbacks)+'\n'+backend+'\n'+boot+'\n'+strip(frontend)+'\n'+strip(runtime)+'\n'+tests
source=source.replace('std::string&=""','std::string& = ""').replace('std::string>&=std::nullopt','std::string>& = std::nullopt')
with tempfile.TemporaryDirectory(prefix='armsx3-runtime-') as temp:
 temp=Path(temp);(temp/'host.cpp').write_text(source)
 subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(root/'core/loadtest'),'-include',str(root/'core/loadtest/Runtime.h'),str(temp/'host.cpp'),'-o',str(temp/'host')],check=True,timeout=180)
 subprocess.run([str(temp/'host'),str(temp/'data')],check=True,timeout=60)

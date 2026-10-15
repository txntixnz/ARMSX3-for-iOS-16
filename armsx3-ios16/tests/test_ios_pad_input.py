"""Build132 input -> native Pad -> native standard cellPad packet regressions.

Compile production atomic bridge, exact new native handler, Pad/Button/Stick
structures, copilot publication and standard pad_get_data body. Native endian
storage, FXO/config/clock/logging and PadHandlerBase are host interfaces. UIKit
and GameController event routing are source contracts; phone input is pending.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent.parent
native = Path(sys.argv[1]).resolve()
pin = '92b931b9fb5eef7f1317cb482917dfc19aceebd9'
def original(path):
    return subprocess.check_output(['git', 'show', f'{pin}:{path}'], cwd=native).decode()
def strip(text):
    return re.sub(r'^#(?:include[^\n]*|pragma once)\n', '', text, flags=re.M)
paths = ['rpcs3/Input/pad_thread.cpp', 'rpcs3/Emu/Io/pad_config_types.h',
         'rpcs3/Emu/Io/pad_config_types.cpp', 'rpcs3/Input/ios_pad_handler.h']
ui = (root/'core/loadtest/GameInputController.mm').read_text()
app = (root/'core/loadtest/App.mm').read_text()
cmake = (root/'core/loadtest/CMakeLists.txt').read_text()
for token in ['UIControlEventTouchDown', 'UIControlEventTouchDragEnter', 'UIControlEventTouchUpInside',
              'UIControlEventTouchUpOutside', 'UIControlEventTouchCancel', 'UIControlEventTouchDragExit',
              'GCControllerDidConnectNotification', 'GCControllerDidDisconnectNotification',
              'selected.handlerQueue = dispatch_get_main_queue()', 'self.enableWriter(0)',
              'if (!self.active) return;', 'self.controller.extendedGamepad.valueChangedHandler = nil',
              'pad == owner.controller.extendedGamepad', 'self.touchButtons = 0']:
    assert token in ui, token
for source, target in [('buttonMenu','start'), ('buttonOptions','select'), ('buttonA','cross'),
                       ('buttonB','circle'), ('buttonX','square'), ('buttonY','triangle'),
                       ('leftShoulder','l1'), ('rightShoulder','r1'), ('leftTrigger','l2'),
                       ('rightTrigger','r2'), ('leftThumbstickButton','l3'), ('rightThumbstickButton','r3')]:
    assert f'{{pad.{source},ios_input::{target}}}' in ui
assert 'buttons = self.touchButtons' in ui and 'buttons |= entry.mask' in ui
assert 'RuntimeInput.cpp' in cmake and 'App.mm GameInputController.mm' in cmake and '-framework GameController' in cmake
assert app.index('[self.input stop];', app.index('- (void)requestGameStop {')) < app.index('if (self.stopAction)')
assert '[display.input stop];\n                    self.intakeBusy = NO;' in app
assert 'if (self.renderController && self.intakeBusy) [self.renderController requestGameStop];' in app
assert 'armsx3_core_set_pad_state' in app and 'armsx3_core_enable_pad' in app

prelude = r'''
#include "PadInput.h"
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;
using s16=std::int16_t;using s32=std::int32_t;using usz=std::size_t;using b8=bool;using f32=float;
constexpr u32 umax=~u32{0};template<class T>using be_t=T;struct ps_move_data{};
using steady_clock=std::chrono::steady_clock;using namespace std::chrono_literals;
template<class T>struct atomic_t{std::atomic<T> a;atomic_t(T v):a(v){}T load(){return a.load();}bool compare_and_swap_test(T x,T y){return a.compare_exchange_strong(x,y);}};
std::atomic<bool> focused=false;
namespace ios_runtime{void set_input_focus(bool value)noexcept{focused=value;}}
u64 get_system_time(){return 0;}
struct Trace{explicit operator bool()const{return false;}template<class... T>void operator()(T&&...)const{}};
struct{Trace trace;}cellPad;
#define __APPLE__ 1
#define TARGET_OS_IPHONE 1
#define ARMSX3_IOS 1
'''
base = r'''
namespace pad{std::mutex g_pad_mutex;}
struct cfg_pad{void from_default(){}};
struct pad_list_entry{explicit pad_list_entry(std::string,bool){}};
class PadHandlerBase{
protected:bool b_has_pressure_intensity_button=true;
public:const pad_handler m_type;u32 connected_devices=0;
explicit PadHandlerBase(pad_handler t):m_type(t){}virtual~PadHandlerBase()=default;
virtual void init_config(cfg_pad*){}virtual std::vector<pad_list_entry> list_devices(){return {};}
virtual bool bindPadToDevice(std::shared_ptr<Pad>){return false;}virtual void process(){}
};
class pad_thread{
public:std::array<std::shared_ptr<Pad>,7>m_pads{};PadInfo m_info{};
auto&GetPads(){return m_pads;}auto&GetInfo(){return m_info;}void apply_copilots();};
pad_thread thread_model;namespace pad{pad_thread*get_pad_thread(){return &thread_model;}}
struct pad_info{std::array<u32,7>port_setting{};};
struct FXO{pad_info info;template<class T>T&get(){return info;}}fxo;
auto*g_fxo=&fxo;bool is_input_allowed(){return focused.load();}
enum{CELL_PAD_LEN_NO_CHANGE=0,CELL_PAD_LEN_CHANGE_DEFAULT=8,CELL_PAD_LEN_CHANGE_PRESS_ON=20,CELL_PAD_LEN_CHANGE_SENSOR_ON=24};
'''
tests = r'''
void poll(ios_pad_handler& handler,CellPadData& data){
 handler.process();thread_model.apply_copilots();std::lock_guard lock(pad::g_pad_mutex);pad_get_data(0,&data);
}
int main(){
 using namespace ios_input;
 assert(axis(-1)==0&&axis(1)==255&&axis(0)==128&&axis(0.1f)==128);
 assert(axis(-1,true)==255&&axis(1,true)==0&&axis(NAN)==128&&axis(INFINITY)==128);
 assert(axes(-1,1,1,-1)==0xffFF0000u);
 assert(armsx3_ios_pad_state()==neutral_state);
 armsx3_core_set_pad_state(start,0);assert(armsx3_ios_pad_state()==neutral_state);
 ios_pad_handler handler;
 auto make_pad=[](u32 i){return std::make_shared<Pad>(pad_handler::ios,i,0,0,0);};
 assert(!handler.bindPadToDevice(nullptr));
 for(u32 i=1;i<7;i++)assert(!handler.bindPadToDevice(make_pad(i)));
 auto pad=make_pad(0);thread_model.m_pads[0]=pad;
 assert(handler.bindPadToDevice(pad)&&!handler.bindPadToDevice(make_pad(0)));
 assert(handler.connected_devices==1&&pad->is_connected());
 assert((pad->m_port_status&CELL_PAD_STATUS_ASSIGN_CHANGES)&&pad->m_buttons.size()==16);
 assert(!(pad->m_device_capability&(CELL_PAD_CAPABILITY_SENSOR_MODE|CELL_PAD_CAPABILITY_ACTUATOR)));
 assert((pad->m_device_capability&CELL_PAD_CAPABILITY_PRESS_MODE)&&pad->m_vendor_id==0x054c&&pad->m_product_id==0x0268);
 armsx3_core_enable_pad(1);assert(focused);CellPadData data{};clear_pad_buffer(pad);poll(handler,data);
 assert(data.len==8&&data.button[2]==0&&data.button[3]==0);
 assert(data.button[4]==128&&data.button[5]==128&&data.button[6]==128&&data.button[7]==128);
 const u32 masks[]={ios_input::select,l3,r3,start,up,right,down,left,l2,r2,l1,r1,triangle,circle,cross,square};
 static_assert(u32(start)==u32(CELL_PAD_CTRL_START)&&cross==(CELL_PAD_CTRL_CROSS<<8));
 for(u32 mask:masks){
  armsx3_core_set_pad_state(mask,neutral_axes);poll(handler,data);
  assert(data.len==8&&data.button[2]==(mask&255)&&data.button[3]==(mask>>8));
  assert(data.button[1]==0x74);poll(handler,data);assert(data.len==0); // Held buttons stay pressed.
  armsx3_core_set_pad_state(0,neutral_axes);poll(handler,data);
  assert(data.len==8&&data.button[2]==0&&data.button[3]==0);
 }
 fxo.info.port_setting[0]=CELL_PAD_SETTING_PRESS_ON;
 armsx3_core_set_pad_state(start|cross|up|r2,axes(-1,1,1,-1));poll(handler,data);
 assert(data.len==20&&data.button[2]==(CELL_PAD_CTRL_START|CELL_PAD_CTRL_UP));
 assert(data.button[3]==(CELL_PAD_CTRL_CROSS|CELL_PAD_CTRL_R2));
 assert(data.button[CELL_PAD_BTN_OFFSET_PRESS_CROSS]==255&&data.button[CELL_PAD_BTN_OFFSET_PRESS_UP]==255&&data.button[CELL_PAD_BTN_OFFSET_PRESS_R2]==255);
 assert(data.button[6]==0&&data.button[7]==0&&data.button[4]==255&&data.button[5]==255);
 // Controller disconnect publishes the remaining touch state and neutral sticks.
 armsx3_core_set_pad_state(start,neutral_axes);poll(handler,data);
 assert(data.button[2]==CELL_PAD_CTRL_START&&data.button[3]==0&&data.button[4]==128);
 armsx3_core_enable_pad(0);assert(!focused);poll(handler,data);
 assert(data.button[2]==0&&data.button[3]==0&&data.button[6]==128&&pad->is_connected());
 armsx3_core_set_pad_state(0xffff,0);assert(armsx3_ios_pad_state()==neutral_state);
 for(int cycle=0;cycle<64;cycle++){
  armsx3_core_enable_pad(1);assert(armsx3_ios_pad_state()==neutral_state);
  armsx3_core_set_pad_state(start,neutral_axes);armsx3_core_enable_pad(0);
  assert(armsx3_ios_pad_state()==neutral_state);
 }
 // A snapshot must never combine button bits from one event with another event's axes.
 armsx3_core_enable_pad(1);std::atomic<bool>done=false;
 std::thread writer([&]{for(int i=0;i<100000;i++){
  armsx3_core_set_pad_state(0x1234,0x11223344);armsx3_core_set_pad_state(0xabcd,0x99aabbcc);
 }done=true;});
 while(!done){auto value=armsx3_ios_pad_state();assert(value==neutral_state||value==0x112233441234ULL||value==0x99aabbccabcdULL);}
 writer.join();done=false;
 std::thread racing_writer([&]{while(!done)armsx3_core_set_pad_state(start,0);});
 armsx3_core_enable_pad(0);for(int i=0;i<10000;i++)assert(armsx3_ios_pad_state()==neutral_state);
 done=true;racing_writer.join();assert(armsx3_ios_pad_state()==neutral_state);
 std::puts("PASS: atomic input, all16 buttons, native Pad/copy/standard cellPad packets, holds/releases, pressure, axes, disconnect/reset/stop and concurrent snapshot guards; UIKit/physical controller pending phone test");
}
'''
with tempfile.TemporaryDirectory(prefix='armsx3-pad132-') as directory:
    directory=Path(directory)
    for path in paths[:-1]:
        target=directory/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(original(path))
    for patch in sorted((root/'patches').glob('*.patch')):
        command=['git','apply','--unsafe-paths']+[f'--include={p}' for p in paths]+[str(patch)]
        subprocess.run(command,cwd=directory,check=True,capture_output=True)
    thread=(directory/paths[0]).read_text()
    assert 'handler.set(i == 0 ? pad_handler::ios : pad_handler::null)' in thread
    assert 'case pad_handler::ios:\n\t\treturn std::make_shared<ios_pad_handler>();' in thread
    assert '#if defined(__APPLE__) && TARGET_OS_IPHONE\n\tios,' in (directory/paths[1]).read_text()
    types=original('rpcs3/Emu/Io/pad_types.h');types=types[types.index('enum SystemInfo'):]
    cell=original('rpcs3/Emu/Cell/Modules/cellPad.cpp')
    clear=cell[cell.index('void clear_pad_buffer('):cell.index('\nerror_code cellPadClearBuf(')]
    get=cell[cell.index('void pad_get_data('):cell.index('\n\tconst auto get_pressure_value =')]+ '\n}\n'
    copy=thread[thread.index('void pad_thread::apply_copilots()'):thread.index('\nvoid pad_thread::update_pad_states()')]
    source=prelude+strip((directory/paths[1]).read_text())+types+base+strip((directory/paths[3]).read_text())+copy+clear+get+tests
    (directory/'test.cpp').write_text(source)
    executable=directory/'test'
    subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer','-I',str(root/'core/loadtest'),str(directory/'test.cpp'),
                    str(root/'core/loadtest/RuntimeInput.cpp'),'-o',str(executable)],check=True,timeout=120)
    subprocess.run([str(executable)],check=True,timeout=30)

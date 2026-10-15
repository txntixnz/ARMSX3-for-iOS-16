"""Reproduce Build120's missing iOS Vulkan settings with complete native headers.
The actual cfg_root/system_config_types and FrameGenConfig helpers are compiled;
only cfg storage/serialization interfaces and Apple platform macros are modeled.
This is a configuration ABI/availability regression, not a GPU backend build.
"""
from pathlib import Path
import re,subprocess,sys,tempfile
root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve();PIN='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
paths=['rpcs3/Emu/system_config.h','rpcs3/Emu/system_config_types.h',
 'rpcs3/Emu/RSX/VK/FrameGen/FrameGenConfig.h']
patches=sorted(p for p in (root/'patches').glob('*.patch') if int(p.name[:4])<=55)
assert [p.name[:4] for p in patches]==[f'{n:04d}' for n in range(1,56)]
model=r'''
#pragma once
#include <cstdint>
#include <string>
#include <cassert>
using s32=std::int32_t;using u32=std::uint32_t;using u64=std::uint64_t;using u128=unsigned __int128;
namespace cfg{
struct node{node(node* = nullptr,const char* = ""){};};
template<class T>struct Value{
 T value;Value(node*,const char*,T v={},bool=true):value(v){}
 T get()const{return value;}operator T()const{return value;}void set(T v){value=v;}
 std::string to_string()const{if constexpr(std::is_same_v<T,std::string>)return value;else return {};}
};
template<class T>using _enum=Value<T>;
using _bool=Value<bool>;using string=Value<std::string>;using uint64=Value<u64>;using uint128=Value<u128>;
template<long long,long long>using _int=Value<long long>;
template<unsigned long long,unsigned long long>using uint=Value<unsigned long long>;
template<int,int>using _float=Value<double>;
using set_entry=node;using node_map_entry=node;using log_entry=node;
}
'''
checks=r'''
#include "Emu/system_config.h"
std::string cfg_root::node_sys::get_random_system_name(){return "host";}
u128 cfg_root::node_sys::get_random_psid(){return 0;}
cfg_root g_cfg,g_backup_cfg;
template<class T>concept HasFramegen=requires(T v){v.frame_generation;v.frame_generation_performance;v.frame_generation_flow_scale;v.frame_generation_target_rate;v.frame_generation_dll_path;};
template<class T>concept HasShaderPreset=requires(T v){v.shader_preset_path;};
static_assert(HasFramegen<cfg_root::node_video> == bool(EXPECT_FIELDS));
static_assert(HasShaderPreset<cfg_root::node_video> == bool(EXPECT_ANDROID));
#if EXPECT_FIELDS
#include "FrameGenConfig.h"
int main(){
 assert(!vk::lsfg::enabled()&&vk::lsfg::multiplier()==2&&vk::lsfg::flow_scale()==100&&vk::lsfg::target_rate()==0&&vk::lsfg::performance_mode());
 assert(g_cfg.video.frame_generation_dll_path.to_string().empty());
 g_cfg.video.frame_generation.set(frame_generation_mode::x3);assert(vk::lsfg::enabled()&&vk::lsfg::multiplier()==3);
 g_cfg.video.frame_generation.set(frame_generation_mode::x4);assert(vk::lsfg::multiplier()==4);
 g_cfg.video.frame_generation.set(frame_generation_mode::off);assert(!vk::lsfg::enabled());
 g_cfg.video.frame_generation_flow_scale.set(50);assert(vk::lsfg::flow_scale()==50);
 g_cfg.video.frame_generation_target_rate.set(120);assert(vk::lsfg::target_rate()==120);
 g_cfg.video.frame_generation_performance.set(false);assert(!vk::lsfg::performance_mode());
 // Same explicit setting used by the production iOS Runtime render mode.
 g_cfg.video.frame_generation.set(frame_generation_mode::off);assert(!vk::lsfg::enabled());
}
#else
int main(){}
#endif
'''
with tempfile.TemporaryDirectory(prefix='armsx3-vulkan-config-') as temp:
 temp=Path(temp)
 for rel in paths:
  p=temp/rel;p.parent.mkdir(parents=True,exist_ok=True)
  p.write_bytes(subprocess.check_output(['git','-C',str(native),'show',PIN+':'+rel]))
 options=[f'--include={p}' for p in paths]
 for patch in patches[:-1]:subprocess.run(['git','apply',*options,str(patch)],cwd=temp,check=True)
 source=temp/paths[0];before=source.read_text()
 subprocess.run(['git','apply','--check',str(patches[-1])],cwd=temp,check=True)
 subprocess.run(['git','apply',str(patches[-1])],cwd=temp,check=True)
 after=source.read_text()
 subprocess.run(['git','apply','--reverse','--check',str(patches[-1])],cwd=temp,check=True)
 assert after.replace('#ifdef __APPLE__\n#include <TargetConditionals.h>\n#endif\n','',1).replace(
  '#if defined(__ANDROID__) || (defined(__APPLE__) && TARGET_OS_IOS)\n\t\t// Shared Vulkan sources read these settings on iOS; the iOS run keeps them off.',
  '#ifdef __ANDROID__',1)==before
 (temp/'Utilities').mkdir();(temp/'Utilities/Config.h').write_text(model)
 (temp/'TargetConditionals.h').write_text('#pragma once\n#ifndef TARGET_OS_IOS\n#define TARGET_OS_IOS 0\n#endif\n')
 (temp/'check.cpp').write_text(checks)
 include=['-I',str(temp),'-I',str(temp/'rpcs3'),'-I',str(temp/'rpcs3/Emu/RSX/VK/FrameGen')]
 command=['g++','-std=c++23','-Wall','-Wextra','-Werror',*include,str(temp/'check.cpp'),'-o',str(temp/'check')]
 ios=['-D__APPLE__=1','-DTARGET_OS_IOS=1','-DEXPECT_FIELDS=1','-DEXPECT_ANDROID=0']
 source.write_text(before)
 failed=subprocess.run(command+ios,capture_output=True,text=True)
 assert failed.returncode and all(name in failed.stderr for name in ['frame_generation','frame_generation_flow_scale','frame_generation_target_rate','frame_generation_performance','frame_generation_dll_path']),failed.stderr
 print('PASS: Build120 iOS missing-member compile failure reproduced using full native config headers')
 source.write_text(after)
 for label,flags in [('ios',ios),('android',['-D__ANDROID__=1','-DEXPECT_FIELDS=1','-DEXPECT_ANDROID=1']),('macos',['-D__APPLE__=1','-DTARGET_OS_IOS=0','-DEXPECT_FIELDS=0','-DEXPECT_ANDROID=0']),('linux',['-DEXPECT_FIELDS=0','-DEXPECT_ANDROID=0'])]:
  built=subprocess.run(command+flags,capture_output=True,text=True)
  assert built.returncode==0,built.stderr
  subprocess.run([str(temp/'check')],check=True)
  print('PASS:',label,'complete native config/types headers; field availability/defaults and actual FrameGen helpers where enabled')
 runtime=(root/'core/loadtest/Runtime.cpp').read_text()
 assert 'configuration.video.frame_generation.set(frame_generation_mode::off)' in runtime
 # All settings referenced by native Vulkan sources are covered by the shared block.
 consumers=['rpcs3/Emu/RSX/VK/vkutils/swapchain.cpp','rpcs3/Emu/RSX/VK/VKGSRender.cpp','rpcs3/Emu/RSX/VK/VKPresent.cpp','rpcs3/Emu/RSX/VK/VKFrameGen.cpp','rpcs3/Emu/RSX/VK/FrameGen/FrameGenConfig.h','rpcs3/Emu/RSX/VK/FrameGen/LosslessDll.cpp']
 names=set()
 for rel in consumers:
  text=subprocess.check_output(['git','-C',str(native),'show',PIN+':'+rel],text=True)
  names.update(re.findall(r'g_cfg.video.(frame_generation\w*)',text))
 assert names=={'frame_generation','frame_generation_performance','frame_generation_flow_scale','frame_generation_target_rate','frame_generation_dll_path'}
print('PASS: exact first54+patch55/reverse, only iOS conditional/header change, all Vulkan consumer settings covered; iOS frame generation remains off. Config storage/serialization are host interfaces; full iOS renderer compile/link/device still required.')

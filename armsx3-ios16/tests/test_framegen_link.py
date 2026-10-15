"""Compile/link full native non-Android VKFrameGen.cpp + exact native present call.
The public native header and Vulkan ABI types are real. Unused config/RSX/timer
include seams and empty device/command interfaces are explicit host models.
No GPU work or native Android frame-generation implementation is exercised.
"""
from pathlib import Path
import os,subprocess,sys,tempfile
root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve();PIN='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
paths=['rpcs3/Emu/RSX/VK/VKFrameGen.cpp','rpcs3/Emu/RSX/VK/VKFrameGen.h','rpcs3/Emu/RSX/VK/VKPresent.cpp']
patches=sorted(p for p in (root/'patches').glob('*.patch') if int(p.name[:4])<=56)
assert [p.name[:4] for p in patches]==[f'{n:04d}' for n in range(1,57)]
old='bool capture_presented_frame(const vk::command_buffer&, const vk::render_device&, VkImage, VkImageLayout, u32, u32)'
fixed=old[:-1]+', u32, u32)'
consumer=r'''
#include "VKFrameGen.h"
#include "vkutils/device.h"
#include "vkutils/commands.h"
#include <cassert>
int main(){
 using namespace vk::frame_gen;
 assert(!available()&&!initialized()&&!unavailable_reason().empty());
 assert(!initialize(0,false,1.f,0,false,nullptr,nullptr));
 assert(import_shaders("")==-1&&shader_count()==0&&std::string(last_error()).empty());
 vk::render_device device;vk::command_buffer cmd;
 auto*m_device=&device;auto*m_current_command_buffer=&cmd;
 const VkImage target_image=VK_NULL_HANDLE;
 const VkImageLayout present_layout=VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
 struct{u32 width=1280,height=720;}m_swapchain_dims;
 const u32 buffer_width=1280,buffer_height=720;
 const bool captured = /* NATIVE_PRESENT_CALL */
 assert(!captured);
 assert(!capture_game_frame(cmd,device,nullptr,1280,720,1280,720));
 assert(!generated_at_game_resolution()&&!generated_width()&&!generated_height());
 assert(!generated_frame_count()&&!generate(device)&&generated_image(0)==VK_NULL_HANDLE);
 assert(display_fps()==0.f&&status_text().empty());
 shared_image image;assert(!image.valid()&&!image.width()&&!image.height());
 assert(image.handle()==VK_NULL_HANDLE&&image.view()==VK_NULL_HANDLE&&image.format()==VK_FORMAT_UNDEFINED);
 assert(image.layout==VK_IMAGE_LAYOUT_UNDEFINED&&!image.create(device,1280,720,VK_FORMAT_B8G8R8A8_UNORM));
 shared_image moved(std::move(image));image=std::move(moved);image.destroy();
 commit_capture();release_shared_images();release_device_resources();shutdown();
}
'''
with tempfile.TemporaryDirectory(prefix='armsx3-framegen-link-') as temp:
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
 assert before.count(old)==1 and after.count(fixed)==1 and after.replace(fixed,old,1)==before
 present=(temp/paths[2]).read_text()
 start=present.index('vk::frame_gen::capture_presented_frame(*m_current_command_buffer, *m_device,')
 end=present.index('buffer_width, buffer_height);',start)+len('buffer_width, buffer_height);')
 call=present[start:end]
 (temp/'consumer.cpp').write_text(consumer.replace('/* NATIVE_PRESENT_CALL */',call))
 shims={
  'stdafx.h':'#pragma once\n#include "util/types.hpp"\n#define LOG_CHANNEL(...)\n',
  'util/types.hpp':'#pragma once\n#include <cstdint>\nusing u8=std::uint8_t;using u32=std::uint32_t;using u64=std::uint64_t;using f32=float;\n',
  'VulkanAPI.h':'#pragma once\n#include <vulkan/vulkan.h>\n',
  'vkutils/device.h':'#pragma once\nnamespace vk { class render_device {}; }\n',
  'vkutils/commands.h':'#pragma once\nnamespace vk { class command_buffer {}; }\n',
  'vkutils/image.h':'#pragma once\n',
  'vkutils/barriers.h':'#pragma once\n',
  'Emu/system_config.h':'#pragma once\n',
  'Emu/Cell/timers.hpp':'#pragma once\n',
 }
 # Copy the full, unchanged header/source to the seam directory so quote-include
 # resolution selects these declared host interfaces, never an extracted body.
 cpp=temp/'VKFrameGen.cpp';header=temp/'VKFrameGen.h';header.write_bytes((temp/paths[1]).read_bytes())
 for rel,text in shims.items():
  p=temp/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
 include=os.environ.get('VULKAN_HOST_INCLUDE','/usr/include')
 assert (Path(include)/'vulkan/vulkan.h').is_file(),'Real Vulkan headers required (libvulkan-dev in graphics-host)'
 flags=['g++','-std=c++23','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(temp),'-I',include]
 def compile_objects(text,defines):
  cpp.write_text(text)
  for src,obj in [(cpp,temp/'backend.o'),(temp/'consumer.cpp',temp/'consumer.o')]:
   subprocess.run([*flags,*defines,'-c',str(src),'-o',str(obj)],check=True)
 def link():return subprocess.run([*flags,str(temp/'backend.o'),str(temp/'consumer.o'),'-o',str(temp/'linked')],capture_output=True,text=True)
 ios=['-D__APPLE__=1','-DTARGET_OS_IOS=1']
 compile_objects(before,ios);failed=link()
 assert failed.returncode and 'capture_presented_frame' in failed.stderr,failed.stderr
 print('PASS: Build121 undefined eight-argument capture_presented_frame reproduced at link, native backend and exact-call consumer compile')
 for label,defines in [('ios',ios),('macos',['-D__APPLE__=1','-DTARGET_OS_IOS=0']),('linux',[])]:
  compile_objects(after,defines);linked=link();assert linked.returncode==0,linked.stderr
  subprocess.run([str(temp/'linked')],check=True)
  print('PASS:',label,'full native non-Android VKFrameGen implementation/public header linked; actual native present call and all fallback APIs return disabled/empty')
 assert 'configuration.video.frame_generation.set(frame_generation_mode::off)' in (root/'core/loadtest/Runtime.cpp').read_text()
print('PASS: exact first55 + patch56/reverse; only existing non-Android fallback arity corrected; Android implementation unchanged. Real Vulkan ABI headers, modeled unused RSX/config includes; full iOS link and Metal device presentation remain CI/device checks.')

"""Native patch54 wiring/policy/present-hook contracts; no native GPU backend mock pass.
Reconstruct exact patched sources. Compile the real native present method and
Apple extension selection against explicit host Vulkan interfaces. GSFrameBase /
GSRender + production adapter lifetime are compiled by test_runtime.py.
"""
from pathlib import Path
import os,re,shutil,subprocess,sys,tempfile
root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
PIN='92b931b9fb5eef7f1317cb482917dfc19aceebd9'
paths=['3rdparty/CMakeLists.txt','rpcs3/Emu/RSX/VK/vkutils/instance.cpp',
 'rpcs3/Emu/RSX/VK/vkutils/metal_layer.mm','rpcs3/Emu/RSX/display.h','rpcs3/Emu/RSX/VK/vkutils/swapchain.cpp']
patches=sorted((root/'patches').glob('*.patch'))
assert [p.name[:4] for p in patches]==[f'{n:04d}' for n in range(1,55)]
with tempfile.TemporaryDirectory(prefix='armsx3-native-renderer-') as temp:
 temp=Path(temp)
 for rel in paths:
  p=temp/rel;p.parent.mkdir(parents=True,exist_ok=True)
  p.write_bytes(subprocess.check_output(['git','-C',str(native),'show',PIN+':'+rel]))
 options=[f'--include={p}' for p in paths]
 for patch in patches[:-1]:subprocess.run(['git','apply',*options,str(patch)],cwd=temp,check=True)
 subprocess.run(['git','apply','--check',str(patches[-1])],cwd=temp,check=True)
 subprocess.run(['git','apply',str(patches[-1])],cwd=temp,check=True)
 subprocess.run(['git','apply','--reverse','--check',str(patches[-1])],cwd=temp,check=True)
 read=lambda p:(temp/p).read_text()
 instance=read(paths[1]);layer=read(paths[2]);swap=read(paths[4]);cmake=read(paths[0])
 ios_layer=layer[layer.index('#if TARGET_OS_IOS'):layer.index('#else',layer.index('#if TARGET_OS_IOS'))]
 # First conditional may select imports; inspect the function's conditional.
 ios_layer=layer[layer.index('void* GetCAMetalLayerFromMetalView'):]
 ios_layer=ios_layer[ios_layer.index('#if TARGET_OS_IOS'):ios_layer.index('#else')]
 assert 'return view;' in ios_layer and '.layer' not in ios_layer and 'UIView*)' not in ios_layer
 policy=re.findall(r'if \(support.is_supported\(VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME\)\)\s*extensions.push_back\(VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME\);\s*if \(support.is_supported\(VK_KHR_GET_PHYSICAL_DEVICE_PROPERTIES_2_EXTENSION_NAME\)\)\s*extensions.push_back\(VK_KHR_GET_PHYSICAL_DEVICE_PROPERTIES_2_EXTENSION_NAME\);',instance)
 assert len(policy)==2 and policy[0]==policy[1]
 flag=instance[instance.index('if (std::any_of(extensions.begin()'):instance.index('\n#endif',instance.index('if (std::any_of(extensions.begin()'))]
 method=swap[swap.index('VkResult swapchain_WSI::present('):swap.rindex('\n}')]
 assert method.index('_vkQueuePresentKHR(')<method.index('armsx3_ios_runtime_note_present(')<method.index('return result;')
 cpp=r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <set>
#include <string_view>
#include <vector>
using u32=std::uint32_t;using VkResult=int;using VkSemaphore=std::uintptr_t;
constexpr int VK_STRUCTURE_TYPE_PRESENT_INFO_KHR=100,VK_NULL_HANDLE=0;
constexpr unsigned VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR=1;
#define VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME "VK_KHR_portability_enumeration"
#define VK_KHR_GET_PHYSICAL_DEVICE_PROPERTIES_2_EXTENSION_NAME "VK_KHR_get_physical_device_properties2"
struct Support{std::set<std::string_view>names;bool is_supported(std::string_view name){return names.count(name);}};
unsigned call=0,observed=0;int response=0,reported=0;
struct VkPresentInfoKHR{int sType{};void*pNext{};unsigned swapchainCount{};const std::uintptr_t*pSwapchains{};const unsigned*pImageIndices{};unsigned waitSemaphoreCount{};const VkSemaphore*pWaitSemaphores{};};
int queue=7;
VkResult _vkQueuePresentKHR(int q,const VkPresentInfoKHR*p){assert(q==queue&&p->sType==100&&p->swapchainCount==1&&*p->pSwapchains==9&&*p->pImageIndices==3);assert((p->waitSemaphoreCount==0&&!p->pWaitSemaphores)||(p->waitSemaphoreCount==1&&*p->pWaitSemaphores==11));assert(call==observed);++call;return response;}
extern "C" void armsx3_ios_runtime_note_present(int result)noexcept{assert(call==observed+1);++observed;reported=result;}
struct Device{int get_present_queue(){return queue;}};
namespace vk{struct swapchain_WSI{Device dev;std::uintptr_t m_vk_swapchain=9;VkResult present(VkSemaphore,u32);};
/* PRESENT */
}
int main(){
 for(unsigned mask=0;mask<4;++mask){Support support;if(mask&1)support.names.insert(VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME);if(mask&2)support.names.insert(VK_KHR_GET_PHYSICAL_DEVICE_PROPERTIES_2_EXTENSION_NAME);
  std::vector<const char*>extensions;struct{unsigned flags=0;}instance_info;
  /* POLICY */
  /* FLAG */
  assert(extensions.size()==unsigned(bool(mask&1))+unsigned(bool(mask&2)));assert(instance_info.flags==unsigned(bool(mask&1)));
 }
 vk::swapchain_WSI swap;for(int value:{0,1000001003,-4,-1000001004})for(VkSemaphore semaphore:{0,11}){response=value;assert(swap.present(semaphore,3)==value);assert(reported==value&&call==observed);}
}
'''.replace('/* PRESENT */',method).replace('/* POLICY */',policy[0]).replace('/* FLAG */',flag)
 (temp/'contract.cpp').write_text(cpp)
 subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-D__APPLE__=1','-DTARGET_OS_IOS=1',str(temp/'contract.cpp'),'-o',str(temp/'contract')],check=True)
 subprocess.run([str(temp/'contract')],check=True)
 # Test actual iOS branch + importer across sibling scopes and repeat includes.
 fixture=temp/'cmake';(fixture/'3rdparty').mkdir(parents=True);(fixture/'consumer').mkdir();(fixture/'ios-core').mkdir()
 (fixture/'ios-core/moltenvk.cmake').write_text((root/'core/moltenvk.cmake').read_text())
 package=fixture/'package';(package/'static/MoltenVK.xcframework/ios-arm64').mkdir(parents=True);(package/'include/vulkan').mkdir(parents=True)
 (package/'static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a').touch();(package/'include/vulkan/vulkan.h').touch()
 branch=cmake[cmake.index('if(USE_VULKAN AND ARMSX3_IOS)'):cmake.index('elseif(USE_VULKAN)')]
 (fixture/'3rdparty/CMakeLists.txt').write_text(branch+'endif()\nadd_library(3rdparty::vulkan ALIAS ${VULKAN_TARGET})\n')
 (fixture/'consumer/CMakeLists.txt').write_text('''include("${CMAKE_SOURCE_DIR}/ios-core/moltenvk.cmake")
include("${CMAKE_SOURCE_DIR}/ios-core/moltenvk.cmake")
if(NOT TARGET armsx3_ios_moltenvk OR NOT TARGET 3rdparty::vulkan)
 message(FATAL_ERROR "Imported driver unavailable in sibling scope")
endif()
get_target_property(definitions 3rdparty::vulkan INTERFACE_COMPILE_DEFINITIONS)
if(NOT definitions STREQUAL "HAVE_VULKAN")
 message(FATAL_ERROR "Native Vulkan sources lack HAVE_VULKAN")
endif()
''')
 (fixture/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(NativeRendererWiring NONE)\nset(USE_VULKAN ON)\nset(ARMSX3_IOS ON)\nset(ARMSX3_MOLTENVK_ROOT "${CMAKE_SOURCE_DIR}/package")\nadd_subdirectory(3rdparty)\nadd_subdirectory(consumer)\n')
 subprocess.run([os.environ.get('CMAKE',shutil.which('cmake') or 'cmake'),'-S',str(fixture),'-B',str(temp/'build')],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 app=(root/'core/loadtest/App.mm').read_text();runtime=(root/'core/loadtest/Runtime.cpp').read_text()
 for token in ['CAMetalLayer.class','drawableSize = CGSizeMake(1280,720)','modalInPresentation = YES','self.renderController = display','action(layer,1280,720','if (result == -2)','display.status.text =','self.renderController = nil','self.renderButton.enabled = intakeReady']:
  assert token in app,token
 assert app.index('const int result = action(layer')<app.index('[display dismissViewControllerAnimated')
 assert 'dispatch_sync' not in (root/'core/loadtest/RuntimeFrame.cpp').read_text()
 assert 'presentation_progress().accepted' in runtime and 'presentation_progress().errors' in runtime and 'finish_renderer_frame()' in runtime
 assert '-DUSE_VULKAN=ON' in (root/'core/build-core.sh').read_text()
print('PASS: exact first53 + native patch54/reverse; both native Apple extension paths and flag policy; actual native queue-present return/hook ordering across success/suboptimal/errors; iOS CMake importer visibility/repeated includes; UIKit layer lifetime source contracts. Full native renderer compile and Metal presentation require CI/device.')

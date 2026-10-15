"""Run production GPU clear/readback with real Vulkan/lavapipe and fault wrappers.
Linux driver execution validates Vulkan commands, not Apple's MoltenVK/Metal.
Only core-idle/thread interfaces and injected failure return values are modeled.
"""
from pathlib import Path
import os,subprocess,sys,tempfile
root=Path(__file__).resolve().parent.parent
host=r'''
#include "GraphicsDevice.h"
#include "Runtime.h"
#include <vulkan/vulkan.h>
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <vector>
#include <dlfcn.h>
#include <mutex>
#include <string>
#include <thread>
extern "C" int armsx3_core_check_graphics(char*,std::size_t);
std::string fault;
std::atomic<unsigned>instances{0},devices{0},destroyed_instances{0},destroyed_devices{0},images{0},buffers{0},fences{0},pools{0},memories{0},readbacks{0};
bool host_main=false,host_stopped=true;std::uint64_t host_cpus=0;
namespace ios_runtime{bool is_main_thread(){return host_main;}}
extern "C" std::uint64_t armsx3_ios_live_cpu_threads(){return host_cpus;}
void ARMSX3StartupLog(const char*s){std::puts(s);}
std::mutex waiter_mutex;std::condition_variable waiter;bool entered=false,released=false;
template<class T>T real(const char*name){auto p=dlsym(RTLD_NEXT,name);assert(p);return reinterpret_cast<T>(p);}
extern "C" VkResult vkCreateInstance(const VkInstanceCreateInfo*a,const VkAllocationCallbacks*b,VkInstance*c){
 if(fault=="instance")return VK_ERROR_INITIALIZATION_FAILED;
 VkInstanceCreateInfo info=*a;
 std::vector<const char*>extensions;
 if(a->enabledExtensionCount)extensions.assign(a->ppEnabledExtensionNames,a->ppEnabledExtensionNames+a->enabledExtensionCount);
 const char*layer="VK_LAYER_KHRONOS_validation";
 VkValidationFeatureEnableEXT enabled=VK_VALIDATION_FEATURE_ENABLE_SYNCHRONIZATION_VALIDATION_EXT;
 VkValidationFeaturesEXT validation{};validation.sType=VK_STRUCTURE_TYPE_VALIDATION_FEATURES_EXT;validation.enabledValidationFeatureCount=1;validation.pEnabledValidationFeatures=&enabled;
 if(std::getenv("GRAPHICS_VALIDATION")){extensions.push_back(VK_EXT_VALIDATION_FEATURES_EXTENSION_NAME);info.enabledExtensionCount=extensions.size();info.ppEnabledExtensionNames=extensions.data();info.enabledLayerCount=1;info.ppEnabledLayerNames=&layer;validation.pNext=info.pNext;info.pNext=&validation;}
 auto r=real<PFN_vkCreateInstance>("vkCreateInstance")(&info,b,c);if(r==VK_SUCCESS)instances++;return r;
}
extern "C" VkResult vkCreateDevice(VkPhysicalDevice p,const VkDeviceCreateInfo*a,const VkAllocationCallbacks*b,VkDevice*c){
 if(fault=="device")return VK_ERROR_FEATURE_NOT_PRESENT;
 auto r=real<PFN_vkCreateDevice>("vkCreateDevice")(p,a,b,c);if(r==VK_SUCCESS)devices++;return r;
}
extern "C" VkResult vkQueueSubmit(VkQueue q,uint32_t n,const VkSubmitInfo*s,VkFence f){
 if(fault=="submit")return VK_ERROR_OUT_OF_DEVICE_MEMORY;
 return real<PFN_vkQueueSubmit>("vkQueueSubmit")(q,n,s,f);
}
extern "C" VkResult vkWaitForFences(VkDevice d,uint32_t n,const VkFence*f,VkBool32 all,uint64_t timeout){
 assert(timeout==5'000'000'000ull);auto r=real<PFN_vkWaitForFences>("vkWaitForFences")(d,n,f,all,timeout);assert(r==VK_SUCCESS);
 if(fault=="timeout")return VK_TIMEOUT;
 if(fault=="lost")return VK_ERROR_DEVICE_LOST;
 if(fault=="busy"){std::unique_lock lock(waiter_mutex);entered=true;waiter.notify_all();waiter.wait(lock,[]{return released;});}
 return r;
}
extern "C" VkResult vkMapMemory(VkDevice d,VkDeviceMemory m,VkDeviceSize off,VkDeviceSize size,VkMemoryMapFlags flags,void**data){
 if(fault=="map")return VK_ERROR_MEMORY_MAP_FAILED;
 auto r=real<PFN_vkMapMemory>("vkMapMemory")(d,m,off,size,flags,data);
 if(r==VK_SUCCESS){readbacks++;if(fault=="pixels")std::memset(*data,0,4);}return r;
}
#define DESTROY(type,field) extern "C" void vkDestroy##type(VkDevice d,Vk##type v,const VkAllocationCallbacks*a){field++;real<PFN_vkDestroy##type>("vkDestroy" #type)(d,v,a);}
DESTROY(Image,images) DESTROY(Buffer,buffers) DESTROY(Fence,fences) DESTROY(CommandPool,pools)
extern "C" void vkFreeMemory(VkDevice d,VkDeviceMemory m,const VkAllocationCallbacks*a){memories++;real<PFN_vkFreeMemory>("vkFreeMemory")(d,m,a);}
extern "C" void vkDestroyDevice(VkDevice d,const VkAllocationCallbacks*a){destroyed_devices++;real<PFN_vkDestroyDevice>("vkDestroyDevice")(d,a);}
extern "C" void vkDestroyInstance(VkInstance i,const VkAllocationCallbacks*a){destroyed_instances++;real<PFN_vkDestroyInstance>("vkDestroyInstance")(i,a);}
int main(int argc,char**argv){
 assert(argc==2);fault=argv[1];char detail[4096]{};
 assert(armsx3_core_check_graphics(nullptr,12)==-1&&armsx3_core_check_graphics(detail,0)==-1);
 host_main=true;assert(armsx3_core_check_graphics(detail,sizeof(detail))==-1);host_main=false;
 host_stopped=false;assert(armsx3_core_check_graphics(detail,sizeof(detail))==-1);host_stopped=true;
 host_cpus=1;assert(armsx3_core_check_graphics(detail,sizeof(detail))==-1);host_cpus=std::uint64_t{1}<<32;assert(armsx3_core_check_graphics(detail,sizeof(detail))==-1);host_cpus=0;
 assert(!instances&&!devices);
 if(fault=="busy"){
  int result=-99;std::thread worker([&]{result=armsx3_core_check_graphics(detail,sizeof(detail));});
  {std::unique_lock lock(waiter_mutex);waiter.wait(lock,[]{return entered;});}
  auto other=ios_graphics::check_device(nullptr);assert(other.status==-1&&other.detail.find("already active")!=std::string::npos);
  {std::lock_guard lock(waiter_mutex);released=true;}waiter.notify_all();worker.join();assert(result==0);
 }else if(fault=="success"){
  for(int i=0;i<4;++i)assert(armsx3_core_check_graphics(detail,sizeof(detail))==0);
  assert(instances==4&&devices==4&&readbacks==8);
 }else{
  const int result=armsx3_core_check_graphics(detail,sizeof(detail));
  assert(result==((fault=="timeout"||fault=="submit")?-2:-1));std::puts(detail);
  if(fault=="instance")assert(!instances&&!devices);
  else if(fault=="device")assert(instances==1&&!devices);
  else assert(instances==1&&devices==1);
  if(fault=="pixels")assert(std::strstr(detail,"do not match"));
  if(fault=="timeout"||fault=="submit"){
   assert(std::strstr(detail,"retained")&&!destroyed_instances&&!destroyed_devices&&!images&&!buffers&&!fences&&!pools&&!memories);
   auto again=ios_graphics::check_device(nullptr);assert(again.status==-2&&instances==1&&devices==1);
   std::puts("PASS: unfinished GPU work retains all owners; subsequent work blocked until process restart");return 0;
  }
 }
 assert(destroyed_instances==instances&&destroyed_devices==devices);
 assert(images==devices&&buffers==devices&&fences==devices&&pools==devices&&memories==devices*2);
 std::puts("PASS: production graphics device, real Vulkan clear/copy/fence/readback, repeated lifecycle/concurrency and failure cleanup; core idle/main-thread guard interfaces modeled");
}
'''

def main():
 include=os.environ.get('VULKAN_HOST_INCLUDE','/usr/include')
 with tempfile.TemporaryDirectory(prefix='armsx3-graphics-host-') as tmp:
  tmp=Path(tmp);(tmp/'Emu').mkdir()
  (tmp/'Emu/System.h').write_text('#pragma once\nextern bool host_stopped;struct{bool IsStopped(bool full){return full&&host_stopped;}}Emu;\n')
  (tmp/'host.cpp').write_text(host)
  binary=tmp/'graphics'
  subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread','-I',str(tmp),'-I',str(root/'core/loadtest'),'-I',str(root/'ios/src'),'-I',include,str(root/'core/loadtest/GraphicsDevice.cpp'),str(root/'core/loadtest/GraphicsCheck.cpp'),str(tmp/'host.cpp'),'-l:libvulkan.so.1','-ldl','-o',str(binary)],check=True,timeout=180)
  for scenario in ['success','instance','device','map','pixels','lost','busy','submit','timeout']:
   result=subprocess.run([str(binary),scenario],capture_output=True,text=True,timeout=60)
   assert result.returncode==0,(scenario,result.stdout,result.stderr)
   assert 'Validation Error' not in result.stdout+result.stderr and 'VUID-' not in result.stdout+result.stderr,(result.stdout,result.stderr)
   print(scenario,':',result.stdout.splitlines()[-1])
 print('PASS: graphics GPU work uses actual Linux Vulkan/lavapipe; iOS MoltenVK/Metal and native RSX rendering/presentation still require device validation')
if __name__=='__main__':main()

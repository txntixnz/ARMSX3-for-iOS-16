"""Compile game import with pinned native PSF reader and SFB validation.
Real filesystem copying/publication, malformed metadata, failed imports and idle
boundaries are exercised. Executable intake is an interface model here; its
native SELF/PPU contracts are covered by test_p114_intake.py and the phone.
"""
from pathlib import Path
import re,struct,subprocess,sys,tempfile
root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
strip=lambda s:re.sub(r'^#(?:include[^\n]*|pragma once)\n','',s,flags=re.M)
psf=(native/'rpcs3/Loader/PSF.cpp').read_text()
# Keep actual entry, load, get_string/get_integer/check_registry bodies; the
# unrelated native writer requires RPCS3's container-stream backend.
psf=psf[psf.index('namespace psf\n{'):]
start=psf.index('\n\tstd::vector<u8> save_object(')
end=psf.index('\n\tstd::string_view get_string(',start)
psf=psf[:start]+psf[end:]
system=(native/'rpcs3/Emu/System.cpp').read_text()
sfb=system[system.index('bool Emulator::IsValidSfb('):system.index('\n// Writes the whole config',system.index('bool Emulator::IsValidSfb('))]
prelude=r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iterator>
#include <limits>
#include <map>
#include <memory>
#include <source_location>
#include <stdexcept>
#include <string>
#include <string_view>
#include <tuple>
#include <utility>
#include <vector>
using namespace std::string_view_literals;
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;using s32=std::int32_t;using usz=std::size_t;
constexpr usz umax=std::numeric_limits<usz>::max();
template<class T>struct le_t{
 std::array<u8,sizeof(T)>bytes{};
 le_t()=default;le_t(T v){*this=v;}
 template<class V>le_t&operator=(V v){u64 x=static_cast<u64>(v);for(usz i=0;i<sizeof(T);++i)bytes[i]=u8(x>>(i*8));return *this;}
 operator T()const{u64 v=0;for(usz i=0;i<sizeof(T);++i)v|=u64(bytes[i])<<(i*8);return static_cast<T>(v);}
};
constexpr u32 operator""_u32(const char*s,usz n){u32 v=0;for(usz i=0;i<n&&i<4;++i)v|=u32(u8(s[i]))<<(i*8);return v;}
template<class T>T narrow(usz v){return static_cast<T>(v);}
void ensure(bool v){if(!v)throw std::runtime_error("host ensure");}
namespace fmt{template<class...T>[[noreturn]]void throw_exception(const char*s,T&&...){throw std::runtime_error(s);}}
struct Logger{template<class...T>void error(const char*,T&&...)const{}}psf_log,sys_log;
std::string host_root;bool idle=true,stopping=false;u64 live_threads=0;unsigned inspections=0;int mutate=0;
extern "C" u64 armsx3_ios_live_cpu_threads(){return live_threads;}
struct Emulator{bool IsStopped(bool fully=false)const{return idle&&(!fully||!stopping);}static bool IsValidSfb(const std::string&);}Emu;
struct{std::string get_dev_flash()const{return host_root+"/dev_flash/";}}g_cfg_vfs;
namespace fs{
constexpr int read=1,isfile=2;
struct file{
 std::vector<u8>bytes;bool opened=false;mutable usz cursor=0;
 file(const std::string&path,int=fs::read){std::ifstream f(path,std::ios::binary);opened=bool(f);bytes.assign(std::istreambuf_iterator<char>(f),{});}
 explicit operator bool()const{return opened;}u64 size()const{return bytes.size();}
 usz seek(u64 at)const{cursor=at;return cursor;}
 usz read(void*out,usz n)const{if(cursor>bytes.size())return 0;n=std::min(n,bytes.size()-cursor);std::memcpy(out,bytes.data()+cursor,n);cursor+=n;return n;}
 template<class T>bool read(T&v)const{return read(&v,sizeof(v))==sizeof(v);}
 template<class T>T read()const{T v{};if(!read(v))throw std::runtime_error("host truncated");return v;}
 template<class T>bool read(std::vector<T>&v,u64 n)const{if(n>size()/sizeof(T))return false;v.resize(n);return read(v.data(),n*sizeof(T))==n*sizeof(T);}
 bool read(std::string&v,u64 n)const{if(n>size())return false;v.resize(n);return read(v.data(),n)==n;}
 template<class T>std::vector<T>to_vector()const{static_assert(sizeof(T)==1);return {bytes.begin(),bytes.end()};}
};
}
std::vector<std::string>logs;
void ARMSX3StartupLog(const char*value){
 const std::string text=value;logs.push_back(text);
 if(mutate==1&&text.starts_with("GAME BEFORE copy")){
  std::filesystem::remove(host_root+"/source/PS3_GAME/USRDIR/assets/level.bin");mutate=0;
 }
 if(mutate==3&&text.starts_with("GAME copied files=")){
  std::ofstream(host_root+"/source/PS3_GAME/USRDIR/assets/added.bin")<<"new source file";mutate=0;
 }
 if(mutate==2&&text.starts_with("GAME copied files=")){
  for(const auto&e:std::filesystem::directory_iterator(host_root+"/ios-games"))
   if(e.path().filename().string().starts_with(".stage-"))std::ofstream(e.path()/"PS3_GAME/USRDIR/EBOOT.BIN",std::ios::trunc)<<"BAD";
  mutate=0;
 }
}
namespace ios_intake{std::string inspect(const char*path,bool persist){
 assert(!persist);++inspections;std::ifstream f(path,std::ios::binary);std::string bytes(std::istreambuf_iterator<char>(f),{});
 if(!bytes.starts_with("ELF"))throw std::runtime_error("Executable rejected by intake model");
 return "executable accepted";
}}
'''
tests=r'''
void write(const std::filesystem::path&path,std::string_view value){std::filesystem::create_directories(path.parent_path());std::ofstream f(path,std::ios::binary|std::ios::trunc);f.write(value.data(),value.size());assert(f);}
std::string read(const std::filesystem::path&path){std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
void clean_staging(){for(const auto&e:std::filesystem::directory_iterator(host_root+"/ios-games"))assert(!e.path().filename().string().starts_with(".stage-"));}
int main(int argc,char**argv){
 assert(argc==3);host_root=argv[1];const auto source=std::filesystem::path(host_root)/"source";
 const auto active=std::filesystem::path(host_root)/"ios-games/active-disc";
 std::filesystem::create_directories(host_root+"/dev_flash");
 write(source/"PS3_DISC.SFB",".SFBhost");write(source/"PS3_GAME/PARAM.SFO",read(argv[2]));
 write(source/"PS3_GAME/USRDIR/EBOOT.BIN","ELF source executable");
 write(source/"PS3_GAME/USRDIR/assets/level.bin",std::string(2*1024*1024,'L'));
 write(source/"PS3_GAME/ICON0.PNG","ICON");std::filesystem::create_directory(source/"empty");
 char detail[4096]{};
 assert(armsx3_core_import_game(source.c_str(),nullptr,0)==-1);
 assert(armsx3_core_import_game(nullptr,detail,sizeof(detail))==-1);
 assert(armsx3_core_import_game((source/"PS3_GAME").c_str(),detail,sizeof(detail))==-1);
 assert(armsx3_core_import_game(source.c_str(),detail,sizeof(detail))==0);
 const auto disc=ios_game::installed();assert(disc.id=="TEST00001"&&disc.title=="Host disc"&&disc.category=="DG");
 assert(disc.asset=="assets/level.bin");assert(std::filesystem::is_directory(active/"empty"));
 for(const auto&e:std::filesystem::recursive_directory_iterator(source))if(e.is_regular_file())assert(read(e.path())==read(active/e.path().lexically_relative(source)));
 const auto accepted=read(active/"PS3_GAME/PARAM.SFO"),asset=read(active/"PS3_GAME/USRDIR/assets/level.bin");
 auto preserved=[&]{assert(read(active/"PS3_GAME/PARAM.SFO")==accepted);assert(read(active/"PS3_GAME/USRDIR/assets/level.bin")==asset);clean_staging();};
 auto reject=[&]{assert(armsx3_core_import_game(source.c_str(),detail,sizeof(detail))==-1);preserved();};
 idle=false;reject();idle=true;stopping=true;reject();stopping=false;live_threads=1;reject();live_threads=0;
 assert(armsx3_core_import_game(active.c_str(),detail,sizeof(detail))==-1);preserved();
 assert(armsx3_core_import_game(host_root.c_str(),detail,sizeof(detail))==-1);preserved();
 std::filesystem::create_directory_symlink(source,host_root+"/linked-root");assert(armsx3_core_import_game((host_root+"/linked-root").c_str(),detail,sizeof(detail))==-1);
 std::filesystem::create_symlink(source/"PS3_DISC.SFB",source/"PS3_GAME/USRDIR/assets/link");reject();std::filesystem::remove(source/"PS3_GAME/USRDIR/assets/link");
 std::filesystem::create_directory_symlink(source,source/"loop");reject();std::filesystem::remove(source/"loop");
 write(source/"PS3_DISC.SFB","BAD");reject();write(source/"PS3_DISC.SFB",".SFBhost");
 const auto valid=read(source/"PS3_GAME/PARAM.SFO");
 for(int scenario:{0,1,2,3,4,5,6,7,8}){
  auto bad=valid;
  if(scenario==0)bad="BAD";
  if(scenario==1){bad[16]=char(0xff);bad[17]=char(0xff);bad[18]=char(0xff);bad[19]=char(0xff);}
  if(scenario==2){const auto begin=static_cast<unsigned char>(bad[8]);const auto end=static_cast<unsigned char>(bad[12]);std::fill(bad.begin()+begin,bad.begin()+end,'X');}
  if(scenario==3){bad[28]=char(0xff);bad[29]=char(0xff);bad[30]=char(0xff);bad[31]=char(0x7f);}
  if(scenario==4){const auto at=bad.find("DG");assert(at!=std::string::npos);bad.replace(at,2,"HG");}
  if(scenario==5){const auto at=bad.find("TEST00001");assert(at!=std::string::npos);bad.replace(at,9,"../BAD001");}
  if(scenario==6){const auto at=bad.find("Host disc");assert(at!=std::string::npos);bad[at]='\n';}
  if(scenario==7)bad.resize(25);
  if(scenario==8){bad[22]=0;bad[23]=0;}
  write(source/"PS3_GAME/PARAM.SFO",bad);reject();
 }
 write(source/"PS3_GAME/PARAM.SFO",valid);
 write(source/"PS3_GAME/USRDIR/EBOOT.BIN","BAD");reject();write(source/"PS3_GAME/USRDIR/EBOOT.BIN","ELF source executable");
 // Sparse oversized input exercises the space preflight without allocating or
 // copying its reported size. Rejection must preserve the existing game.
 write(source/"space.bin","");const auto available=std::filesystem::space(host_root).available;
 std::filesystem::resize_file(source/"space.bin",available+1);reject();std::filesystem::remove(source/"space.bin");
 mutate=1;reject();write(source/"PS3_GAME/USRDIR/assets/level.bin",asset);
 mutate=2;reject();
 mutate=3;reject();std::filesystem::remove(source/"PS3_GAME/USRDIR/assets/added.bin");
 write(source/"PS3_GAME/USRDIR/assets/level.bin","new level");
 assert(armsx3_core_import_game(source.c_str(),detail,sizeof(detail))==0);
 assert(read(active/"PS3_GAME/USRDIR/assets/level.bin")=="new level");clean_staging();
 for(const auto&e:std::filesystem::directory_iterator(host_root+"/ios-games"))assert(e.path().filename()=="active-disc");
 assert(inspections>=5);
 std::puts("PASS: production game import plus pinned native PSF reader/SFB validation; complete disk copy and title identity, empty directories/assets, replacement, malformed metadata/executable rejection, insufficient space, source changes/staged corruption, symlink/root/idle/C ABI guards; prior game preserved and staging removed. Executable decoding and OS file-provider access are separate interfaces.");
}
'''
# Independent PSF fixture encoding, without using the native writer under test.
values=[('CATEGORY',b'DG\0',0x204),('TITLE',b'Host disc\0',0x204),('TITLE_ID',b'TEST00001\0',0x204),('ATTRIBUTE',struct.pack('<I',0),0x404)]
keys=bytearray();payload=bytearray();indices=bytearray()
for key,value,format in values:
 indices+=struct.pack('<HHIII',len(keys),format,len(value),len(value),len(payload))
 keys+=key.encode()+b'\0';payload+=value
key_offset=20+len(indices);data_offset=key_offset+len(keys)
fixture=struct.pack('<IIIII',0x46535000,0x101,key_offset,data_offset,len(values))+indices+keys+payload
source=prelude+'\n'+strip((native/'rpcs3/Loader/PSF.h').read_text())+'\n'+psf+'\n'+sfb+'\n'+strip((root/'core/loadtest/GameImport.cpp').read_text())+'\n'+tests
with tempfile.TemporaryDirectory(prefix='armsx3-game-') as temp:
 temp=Path(temp);(temp/'host.cpp').write_text(source);(temp/'fixture.sfo').write_bytes(fixture)
 subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(root/'core/loadtest'),'-include',str(root/'core/loadtest/GameImport.h'),'-include',str(root/'core/loadtest/IntakePolicy.h'),str(temp/'host.cpp'),'-o',str(temp/'host')],check=True,timeout=180)
 subprocess.run([str(temp/'host'),str(temp/'data'),str(temp/'fixture.sfo')],check=True,timeout=120)

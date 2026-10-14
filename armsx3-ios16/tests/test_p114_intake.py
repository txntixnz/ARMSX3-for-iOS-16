"""Compile production intake with native PUP/SHA1 and explicit host interfaces.
Filesystem rename/rollback uses real host disk operations. TAR, SCE, ELF, FXO
and fs::file backend are interface models; native device probes exercise them
against the real core. Usage: test_p114_intake.py PINNED_UPSTREAM
"""
from pathlib import Path
import hashlib,hmac,re,struct,subprocess,tempfile,sys
root=Path(__file__).resolve().parent.parent
native=Path(sys.argv[1]).resolve()
intake=(root/'core/loadtest/Intake.cpp').read_text()
pup_h=(native/'rpcs3/Loader/PUP.h').read_text()
pup_cpp=(native/'rpcs3/Loader/PUP.cpp').read_text()
sha_h=(native/'rpcs3/Crypto/sha1.h').read_text()
sha_cpp=(native/'rpcs3/Crypto/sha1.cpp').read_text()
key_h=(native/'rpcs3/Crypto/key_vault.h').read_text()
key=re.search(r'constexpr u8 PUP_KEY\[0x40\] = \{([^}]+)\}',key_h).group(0)+';'
key_bytes=bytes(int(x,16) for x in re.findall(r'0x([0-9A-Fa-f]{2})',key.split('=')[1]))
assert len(key_bytes)==64
def strip_includes(s):return re.sub(r'^#(?:include[^\n]*|pragma once)\n','',s,flags=re.M)
def tar(entries):
 out=bytearray()
 for name,data in entries:
  header=bytearray(512);header[:len(name)]=name.encode();header[124:136]=f'{len(data):011o}\0'.encode();header[136:148]=b'00000000001\0'
  header[148:156]=b'        ';header[156]=ord('0');header[257:262]=b'ustar'
  header[148:156]=f'{sum(header):06o}\0 '.encode();out+=header+data+b'\0'*((-len(data))%512)
 return bytes(out+b'\0'*1024)
def pup(entries):
 header_len=48+64*len(entries);payload=b''.join(data for _,data in entries);offset=header_len
 table=bytearray();hashes=bytearray()
 for ident,data in entries:
  table+=struct.pack('>QQQ',ident,offset,len(data))+b'\0'*8;offset+=len(data)
  hashes+=struct.pack('>Q',ident)+hmac.new(key_bytes,data,hashlib.sha1).digest()+b'\0'*4
 return b'SCEUF\0\0\0'+struct.pack('>QQQQQ',1,1,len(entries),header_len,len(payload))+table+hashes+payload
valid=pup([(0x100,b'4.93\n'),(0x300,tar([('dev_flash_000.pkg',b'SCEPROBE'+tar([
 ('dev_flash/sys/external/liblv2.sprx',b'probe library'),('dev_flash/vsh/etc/version.txt',b'4.93\n')]))]))])
prelude=r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <map>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;using usz=std::size_t;
template<class T,bool Big=true>struct Endian{
 std::array<u8,sizeof(T)>bytes{};Endian()=default;Endian(T v){*this=v;}
 template<class V>Endian&operator=(V v){u64 x=static_cast<u64>(v);for(usz i=0;i<sizeof(T);++i)bytes[Big?sizeof(T)-1-i:i]=u8(x>>(i*8));return *this;}
 operator T()const{u64 v=0;for(usz i=0;i<sizeof(T);++i)v|=u64(bytes[Big?sizeof(T)-1-i:i])<<(i*8);return static_cast<T>(v);}
};
template<class T>using be_t=Endian<T>;template<class T>using le_t=Endian<T,false>;
constexpr u64 operator""_u64(const char*s,usz n){u64 v=0;for(usz i=0;i<n&&i<8;++i)v|=u64(u8(s[i]))<<(i*8);return v;}
constexpr u32 operator""_u32(const char*s,usz n){u32 v=0;for(usz i=0;i<n&&i<4;++i)v|=u32(u8(s[i]))<<(i*8);return v;}
namespace fmt{template<class...T>std::string format(const char*s,T...){return s;}}
#define AUDIT(x) assert(x)
void mbedtls_zeroize(void*p,usz n){volatile u8*bytes=static_cast<volatile u8*>(p);while(n--)*bytes++=0;}
std::string host_root;bool host_idle=true;u64 host_workers=0;int decoder_fault=0;
void ARMSX3StartupLog(const char*){}
extern "C" u64 armsx3_ios_live_cpu_threads(){return host_workers;}
struct {bool IsStopped()const{return host_idle;}}Emu;
struct {std::string get_dev_flash()const{return host_root+"/installed/";}}g_cfg_vfs;
namespace fs{
constexpr int read=1,rewrite=2;
struct file{
 std::shared_ptr<std::vector<u8>>bytes;mutable usz cursor=0;std::string disk;
 file()=default;file(std::string p,int mode):disk(std::move(p)){
  if(mode==rewrite){bytes=std::make_shared<std::vector<u8>>();sync();}
  else{std::ifstream stream(disk,std::ios::binary);if(stream)bytes=std::make_shared<std::vector<u8>>(std::istreambuf_iterator<char>(stream),std::istreambuf_iterator<char>());}
 }
 explicit operator bool()const{return bool(bytes);}u64 size()const{return bytes?bytes->size():0;}void seek(u64 p)const{cursor=p;}
 usz read(void*out,usz n)const{if(!bytes||cursor>bytes->size())return 0;n=std::min(n,bytes->size()-cursor);std::memcpy(out,bytes->data()+cursor,n);cursor+=n;return n;}
 template<class T>bool read(T&v)const{return read(&v,sizeof(v))==sizeof(v);}
 template<class T>bool read(std::vector<T>&v,u64 n)const{if(n>size()/sizeof(T))return false;v.resize(n);return read(v.data(),n*sizeof(T))==n*sizeof(T);}
 usz write(const void*input,usz n){if(!bytes)return 0;bytes->resize(cursor+n);std::memcpy(bytes->data()+cursor,input,n);cursor+=n;sync();return n;}
 void sync()const{if(!disk.empty()&&bytes){std::ofstream out(disk,std::ios::binary|std::ios::trunc);out.write(reinterpret_cast<const char*>(bytes->data()),bytes->size());if(!out)throw std::runtime_error("host write failed");}}
 std::string to_string()const{return bytes?std::string(bytes->begin(),bytes->end()):"";}
 template<class T>std::vector<T>to_vector()const{std::vector<T>v(size()/sizeof(T));if(!v.empty())std::memcpy(v.data(),bytes->data(),v.size()*sizeof(T));return v;}
};
file make_stream(std::vector<u8>v){file f;f.bytes=std::make_shared<std::vector<u8>>(std::move(v));return f;}
std::string get_cache_dir(){return host_root+"/cache/";}bool is_file(std::string p){return std::filesystem::is_regular_file(p);}
}
namespace utils{struct serial{std::vector<u8>data;struct Handler{void handle_file_op(serial&,u64,u64,void*){}};std::unique_ptr<Handler>m_file_handler;u64 get_size(u64)const{return data.size();}};}
struct TARHeader{char name[100],dontcare[24],size[12],mtime[12],chksum[8],filetype,linkname[100],magic[6],dontcare2[82],prefix[155],padding[12];};
class tar_object{
 std::map<std::string,std::vector<u8>>entries;
 public:tar_object(const fs::file&file){auto bytes=file.to_vector<u8>();for(usz offset=0;offset+512<=bytes.size();){auto*h=reinterpret_cast<const TARHeader*>(bytes.data()+offset);if(!h->name[0]&&!h->prefix[0])break;
 usz length=std::stoull(std::string(h->size,strnlen(h->size,12)),nullptr,8);offset+=512;if(length>bytes.size()-offset)throw std::runtime_error("modeled TAR truncated");
 auto name=std::string(h->prefix,strnlen(h->prefix,155))+std::string(h->name,strnlen(h->name,100));entries[name]={bytes.begin()+offset,bytes.begin()+offset+length};offset+=(length+511)&~usz{511};}}
 std::vector<std::string>get_filenames(){std::vector<std::string>names;for(const auto&e:entries)names.push_back(e.first);return names;}
 std::unique_ptr<utils::serial>get_file(std::string name){auto it=entries.find(name);if(it==entries.end())return {};auto out=std::make_unique<utils::serial>();out->data=it->second;return out;}
 bool extract(const std::string&prefix,bool){for(const auto&e:entries){auto target=std::filesystem::path(prefix)/e.first;std::filesystem::create_directories(target.parent_path());fs::file out(target.string(),fs::rewrite);if(out.write(e.second.data(),e.second.size())!=e.second.size())return false;}return true;}
};
constexpr u8 SCEPKG_ERK[32]{},SCEPKG_RIV[16]{};
class SCEDecrypter{const fs::file&input;public:SCEDecrypter(const fs::file&f):input(f){}bool LoadHeaders(){return decoder_fault!=1&&input.to_string().starts_with("SCEPROBE");}
 bool LoadMetadata(const u8*,const u8*){return decoder_fault!=2;}bool DecryptData(){return decoder_fault!=3;}
 std::vector<fs::file>MakeFile(){if(decoder_fault==4)return {};auto bytes=input.to_vector<u8>();std::vector<fs::file>out(3);out[2]=fs::make_stream({bytes.begin()+8,bytes.end()});return out;}};
enum class elf_os:u8{lv2=102};enum class elf_type:u16{exec=2};enum class elf_machine:u16{ppc64=21};enum class elf_error{ok,bad};
struct ppu_exec_object{
 struct ehdr_t{be_t<u32>e_magic;u8 e_class{},e_data{},e_curver{},e_os_abi{},pad[8]{};be_t<u16>e_type,e_machine;be_t<u32>e_version;be_t<u64>e_entry,e_phoff,e_shoff;be_t<u32>e_flags;be_t<u16>e_ehsize,e_phentsize,e_phnum,e_shentsize,e_shnum,e_shstrndx;};
 struct phdr_t{be_t<u32>p_type,p_flags;be_t<u64>p_offset,p_vaddr,p_paddr,p_filesz,p_memsz,p_align;};
 ehdr_t header{};std::vector<phdr_t>progs;elf_error error=elf_error::bad;
 ppu_exec_object(const fs::file&f){f.seek(0);if(!f.read(header)||header.e_magic!="\177ELF"_u32)return;
 f.seek(header.e_phoff);if(f.read(progs,+header.e_phnum))error=elf_error::ok;}
 elf_error get_error()const{return error;}
};
fs::file decrypt_self(const fs::file&f){return f;}
'''
tests=r'''
int main(int argc,char**argv){
 assert(argc==3);host_root=argv[1];std::filesystem::create_directories(host_root+"/cache");
 unsigned char digest[20]{};unsigned char key[20];std::memset(key,0x0b,20);
 sha1_hmac(key,20,reinterpret_cast<const u8*>("Hi There"),8,digest);
 const std::array<u8,20>known{0xb6,0x17,0x31,0x86,0x55,0x05,0x72,0x64,0xe2,0x8b,0xc0,0xb6,0xfb,0x37,0x8c,0x8e,0xf1,0x46,0xbe,0x00};assert(std::equal(known.begin(),known.end(),digest));
 for(unsigned probe=0;probe<8;++probe)assert(ios_intake::probe(probe)==0);
 std::filesystem::create_directory(host_root+"/installed");ios_intake::write_file(host_root+"/installed/old",{42});
 for(int failure=1;failure<=4;++failure){decoder_fault=failure;char detail[4096]{};
  assert(armsx3_core_import_firmware(argv[2],detail,sizeof(detail))==-1);assert(std::filesystem::is_regular_file(host_root+"/installed/old"));}
 decoder_fault=0;char detail[4096]{};assert(armsx3_core_import_firmware(argv[2],detail,sizeof(detail))==0);
 assert(std::string(detail).starts_with("PS3 firmware 4.93 installed"));assert(!std::filesystem::exists(host_root+"/installed/old"));
 fs::file installed(host_root+"/installed/sys/external/liblv2.sprx",fs::read);assert(installed.to_string()=="probe library");
 assert(ios_intake::archive_name("dev_flash/vsh/",true));assert(!ios_intake::archive_name("dev_flash/../escape",true));assert(!ios_intake::archive_name("dev_flash//file",true));
 assert(!ios_intake::archive_name("dev_flash\\file",true));assert(!ios_intake::firmware_version("4.93.."));
 const auto executable=std::filesystem::path(host_root)/"real.elf";ios_intake::write_file(executable,ios_intake::elf_fixture());
 assert(armsx3_core_inspect_executable(executable.c_str(),detail,sizeof(detail))==0);
 assert(std::filesystem::is_regular_file(host_root+"/cache/ARMSX3-prepared-executable.elf"));
 host_idle=false;assert(armsx3_core_import_firmware(argv[2],detail,sizeof(detail))==-1);host_idle=true;
 host_workers=1;assert(armsx3_core_inspect_executable(executable.c_str(),detail,sizeof(detail))==-1);host_workers=0;
 assert(armsx3_core_import_firmware(nullptr,detail,sizeof(detail))==-1);assert(armsx3_core_import_firmware(argv[2],nullptr,0)==-1);
 for(auto&e:std::filesystem::directory_iterator(host_root))assert(!e.path().filename().string().starts_with(".ios-firmware-stage-"));
 std::puts("PASS:8 intake probes; native PUP/SHA1/RFC-HMAC and independently authenticated fixture; actual disk staging/rename/rollback; decryption failure preserves installed tree; complete installer/executable intake/C ABI idle guards. TAR/SCE/ELF/backend interfaces modeled; actual iOS firmware pending.");
}
'''
source=prelude+'\n#include "IntakePolicy.h"\n'+key+'\n'+strip_includes(sha_h)+'\n'+strip_includes(sha_cpp)+'\n'+strip_includes(pup_h)+'\n'+strip_includes(pup_cpp)+'\n'+strip_includes(intake)+'\n'+tests
# e_os_abi is enum-typed in production; the narrow host header stores its byte.
source=source.replace('header.e_os_abi = elf_os::lv2','header.e_os_abi = static_cast<u8>(elf_os::lv2)')
with tempfile.TemporaryDirectory(prefix='armsx3-intake-') as temp:
 temp=Path(temp);(temp/'fixture.pup').write_bytes(valid);(temp/'host.cpp').write_text(source)
 cmd=['g++','-std=c++23','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(root/'core/loadtest'),str(temp/'host.cpp'),'-o',str(temp/'host')]
 subprocess.run(cmd,check=True,timeout=180)
 subprocess.run([str(temp/'host'),str(temp/'data'),str(temp/'fixture.pup')],check=True,timeout=180)

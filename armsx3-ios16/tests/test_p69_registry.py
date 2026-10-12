"""Native IDM construction/allocator regression; storage/pointers/FXO are shims.

Usage: python test_p69_registry.py upstream-armsx3
Extract the actual id_key, id_map default member layout and allocate_id body.
Trap-valued storage reproduces the failed import; constructed storage supports
real allocation, deletion/reuse and type lookup. No iOS execution is claimed.
"""
from pathlib import Path
import subprocess,sys,tempfile
if len(sys.argv)!=2:raise SystemExit(__doc__)
root=Path(sys.argv[1])/'rpcs3'
header=(root/'Emu/IdManager.h').read_text()
source=(root/'Emu/IdManager.cpp').read_text()
fxo=(root/'util/fixed_typemap.hpp').read_text()
assert 'std::memset(Size == 0 ? m_list : m_data, 0xCC' in fxo
def block(text,signature):
 start=text.index(signature);a=text.index('{',start);end=a+1;depth=1
 while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]
key=block(header,'class id_key')+';'
start=header.index('template <typename T>\n\tstruct id_map')
end=header.index('\n\t\tid_map(utils::serial& ar)',start)
layout=header[start:end]+'\n};'
allocator=block(source,'id_manager::id_key* idm::allocate_id(')
shims=r'''
#include <algorithm>
#include <array>
#include <bit>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <mutex>
#include <span>
#include <utility>
using u32=uint32_t;using u64=uint64_t;constexpr u32 umax=0xffffffffu;
#define ensure(x) assert(x)
template<class T>constexpr bool IdmBaseCompatible=true;
using shared_mutex=std::mutex;
namespace stx{template<class T>struct atomic_ptr{T*value=nullptr;};template<class T>using shared_ptr=std::shared_ptr<T>;}
namespace id_manager{thread_local u32 g_id=0;
 // Only fixed-ID construction uses get_index; implement the documented index
 // operation as a shim. Dynamic allocation executes the extracted body below.
 u32 get_index(u32 id,u32 base,u32 step,u32,std::pair<u32,u32>){return (id-base)/step;}
'''
shims+=key+'\n'+layout+'\n}\n'
shims+='class idm{public:static id_manager::id_key* allocate_id(std::span<id_manager::id_key>,u32&,u32,u32,u32,u32,u32,bool,std::pair<u32,u32>);};\n'+allocator
checks=r'''
struct lv2_obj{static constexpr u32 id_count=8192;static constexpr double savestate_init_pos=4;};
int main(){
 using Map=id_manager::id_map<lv2_obj>;
 // Trap field values model unconstructed FXO bytes without invoking undefined
 // object lifetime behavior. Real allocator sees no free entries and fails.
 auto trap=std::make_unique<Map>();trap->highest_index=0xcccccccc;
 for(auto&key:trap->vec_keys)key=id_manager::id_key(0xcccccccc,0xcccccccc);
 id_manager::g_id=0;
 assert(!idm::allocate_id(trap->vec_keys,trap->highest_index,0x85000000,0,0x85000000,0x100,8192,false,{0,8}));
 assert(!id_manager::g_id && trap->highest_index==0xcccccccc);
 // Default construction runs the exact native map/key initializers.
 auto map=std::make_unique<Map>();assert(map->highest_index==0);
 for(u32 i=0;i<8192;++i){assert(map->vec_keys[i].type()==umax && map->vec_keys[i].value()==0);assert(!map->vec_data[i].value && !map->private_copy[i]);}
 auto allocate=[&]{return idm::allocate_id(map->vec_keys,map->highest_index,0x85000000,0,0x85000000,0x100,8192,false,{0,8});};
 auto*first=allocate();assert(first==&map->vec_keys[0] && first->value()==0x85000000 && first->type()==0x85000000 && id_manager::g_id==first->value());
 first->clear();assert(first->type()==umax);
 auto*second=allocate();assert(second==&map->vec_keys[1] && second->value()==0x85000100 && map->highest_index==2);
 // Exhaust real allocation capacity; then exercise deletion and cookie reuse.
 for(u32 i=2;i<8192;++i){auto*entry=allocate();assert(entry==&map->vec_keys[i] && entry->type()==0x85000000 && entry->value()==0x85000000+i*0x100);}
 auto*reused=allocate();assert(reused==first && reused->value()==0x85000001 && id_manager::g_id==0x85000001);
 assert(!allocate());reused->clear();auto*again=allocate();assert(again==first && again->value()==0x85000002);
 std::puts("PASS: extracted native id_key/map default layout/allocate_id: trap storage rejects creation; constructed8192-entry registry allocates/publishes/types/destroys/reuses cookies, capacity exhaustion;pointer/FXO storage are host shims");
}
'''
with tempfile.TemporaryDirectory(prefix='p69-registry-') as temp:
 code=Path(temp)/'test.cpp';binary=Path(temp)/'test';code.write_text(shims+checks)
 subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(code),'-o',str(binary)],check=True)
 subprocess.run([str(binary)],check=True)

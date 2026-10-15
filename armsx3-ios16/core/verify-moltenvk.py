"""Verify the pinned XCFramework contains only compatible arm64 iOS objects.
Parse archive members directly so this also runs on the Linux validation host.
"""
from pathlib import Path
import plistlib,struct,sys
root=Path(sys.argv[1]);framework=root/'static/MoltenVK.xcframework'
info=plistlib.loads((framework/'Info.plist').read_bytes())
assert info['AvailableLibraries']==[{'BinaryPath':'libMoltenVK.a','LibraryIdentifier':'ios-arm64','LibraryPath':'libMoltenVK.a','SupportedArchitectures':['arm64'],'SupportedPlatform':'ios'}],info
source=(framework/'ios-arm64/libMoltenVK.a').read_bytes();assert source[:8]==b'!<arch>\n'
offset=8;objects=0
while offset<len(source):
 header=source[offset:offset+60];assert len(header)==60 and header[-2:]==b'`\n'
 size=int(header[48:58]);data=source[offset+60:offset+60+size];assert len(data)==size
 name=header[:16].decode().strip()
 if name.startswith('#1/'):
  length=int(name[3:]);name=data[:length].rstrip(b'\0').decode();data=data[length:]
 offset+=60+size+(size%2)
 if name.startswith('__.SYMDEF') or name in ['/', '//']:continue
 assert data[:4]==b'\xcf\xfa\xed\xfe',(name,'Expected Mach-O64 object')
 magic,cpu,subtype,kind,ncmds,cmdsize,flags,reserved=struct.unpack_from('<8I',data)
 assert cpu==0x100000c and kind==1,(name,cpu,kind)
 cursor=32;platforms=[]
 for _ in range(ncmds):
  command,length=struct.unpack_from('<2I',data,cursor);assert length>=8 and cursor+length<=32+cmdsize
  if command==0x32:
   platform,minimum=struct.unpack_from('<2I',data,cursor+8);platforms.append((platform,minimum))
  elif command==0x25:
   minimum=struct.unpack_from('<I',data,cursor+8)[0];platforms.append((2,minimum))
  cursor+=length
 assert cursor==32+cmdsize and platforms and all(p==2 and m<=0x100000 for p,m in platforms),(name,platforms)
 objects+=1
assert objects>0,objects
assert (root/'include/vulkan/vulkan.h').is_file()
print(f'PASS: MoltenVK v1.4.2 XCFramework, {objects} arm64 iOS objects with deployment target <=16.0; no simulator/macOS slice')

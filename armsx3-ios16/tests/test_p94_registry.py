"""Native allocator checks for event queue0x8d and local port0x0e namespaces."""
from pathlib import Path
import sys
profile=sys.argv.pop() if len(sys.argv)==3 else None
assert profile in (None,'queue','port')
p=Path(__file__).with_name('test_p69_registry.py')
h=(Path(sys.argv[1])/'rpcs3/Emu/Cell/lv2/sys_event.h').read_text()
for name,namespace in [('queue','8d'),('port','0e')]:
 if profile and profile!=name:continue
 assert 'id_base = 0x'+namespace+'000000' in h
 source=p.read_text().replace('0x85','0x'+namespace).replace('p69-registry-','p94-registry-'+name+'-')
 source=source.replace('PASS: extracted native id_key/map default layout/allocate_id:', 'PASS: event '+name+'/extracted native id_key/map default layout/allocate_id:')
 exec(compile(source,str(Path(__file__).resolve()),'exec'))

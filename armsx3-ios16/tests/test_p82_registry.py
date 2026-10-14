"""Check extracted native LV2 ID allocation for event flag namespace0x98000000.
Usage: test_p82_registry.py upstream-armsx3
Pointer/FXO storage/get_index remain models; native allocator body is extracted.
"""
from pathlib import Path
import sys
p=Path(__file__).with_name('test_p69_registry.py')
header=(Path(sys.argv[1])/'rpcs3/Emu/Cell/lv2/sys_event_flag.h').read_text()
assert 'id_base = 0x98000000' in header
source=p.read_text().replace('0x85','0x98').replace('p69-registry-','p82-registry-')
source=source.replace('PASS: extracted native id_key/map default layout/allocate_id:', 'PASS: event flag0x98000000/extracted native id_key/map default layout/allocate_id:')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

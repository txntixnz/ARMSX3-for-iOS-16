"""Extracted native allocator for condition namespace0x86000000.
Usage: test_p86_registry.py upstream-armsx3
Constructor/ownership and mutex linking are checked by the pair workload.
"""
from pathlib import Path
import sys
p=Path(__file__).with_name('test_p69_registry.py')
header=(Path(sys.argv[1])/'rpcs3/Emu/Cell/lv2/sys_cond.h').read_text()
assert 'id_base = 0x86000000' in header
source=p.read_text().replace('0x85','0x86').replace('p69-registry-','p86-registry-')
source=source.replace('PASS: extracted native id_key/map default layout/allocate_id:', 'PASS: condition0x86000000/extracted native id_key/map default layout/allocate_id:')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

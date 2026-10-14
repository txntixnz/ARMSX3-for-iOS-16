"""Extracted native allocator for reader/writer namespace0x88000000.
Usage: test_p90_registry.py upstream-armsx3
Constructor and ownership are exercised by the extracted pair workload.
"""
from pathlib import Path
import sys
p=Path(__file__).with_name('test_p69_registry.py')
header=(Path(sys.argv[1])/'rpcs3/Emu/Cell/lv2/sys_rwlock.h').read_text()
assert 'id_base = 0x88000000' in header
source=p.read_text().replace('0x85','0x88').replace('p69-registry-','p90-registry-')
source=source.replace('PASS: extracted native id_key/map default layout/allocate_id:', 'PASS: reader/writer0x88000000/extracted native id_key/map default layout/allocate_id:')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

"""Native shared LV2 registry allocation for mutex and semaphore ID namespaces.
Usage: python test_p76_registry.py upstream-armsx3
Actual id_key/id_map default initializers/allocate_id are extracted; pointer,
FXO storage and get_index remain models. No iOS execution is claimed.
"""
from pathlib import Path
import runpy,sys
p=Path(__file__).with_name('test_p69_registry.py')
runpy.run_path(str(p))
header=(Path(sys.argv[1])/'rpcs3/Emu/Cell/lv2/sys_semaphore.h').read_text()
assert 'id_base = 0x96000000' in header
# Same extracted allocation body, using the pinned semaphore namespace.
source=p.read_text().replace('0x85','0x96').replace('p69-registry-','p76-registry-')
source=source.replace('PASS: extracted native id_key/map default layout/allocate_id:', 'PASS: P76 semaphore0x96000000/extracted native id_key/map default layout/allocate_id:')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

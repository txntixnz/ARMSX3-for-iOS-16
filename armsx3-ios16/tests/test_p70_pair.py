"""P70 extracted recursive mutex services on the established explicit host models.

Usage: python test_p70_pair.py PPUThread.cpp CoreBridge.cpp Modules/sys_ppu_thread_.cpp
Adapt P69 harness construction to the independent P70 workload expectations.
No P69 workload is executed here. Native service/binder/SC/TLS bodies remain
extracted; CPU/VM/ID storage/atomic control/FXO/registry/notification are models.
"""
from pathlib import Path
source=Path(__file__).with_name('test_p69_pair.py').read_text()
def replace(before,after):
 global source
 assert before in source,before
 source=source.replace(before,after)
replace('P69','P70')
replace('armsx3_core_test_lv2_mutex_ownership','armsx3_core_test_recursive_mutex_ownership')
replace('==92','==110')
replace('executed==600 && tls_stores==60 && output_stores==120','executed==720 && tls_stores==72 && output_stores==144')
replace('stat[101]==12 && syscall_usage.stat[103]==30 && syscall_usage.stat[104]==12','stat[101]==15 && syscall_usage.stat[103]==33 && syscall_usage.stat[104]==18')
replace('TLS=10/10','TLS=12/12')
replace('TLS=20/20','TLS=24/24')
replace('TLS=30/30','TLS=36/36')
replace('207,208,209,210','207,208,210') # Nonrecursive self-deadlock mutation inapplicable.
replace('215,216,217};','215,216,217,220,221,222};')
replace("extras+='template<class T>'+lock", """# Host-only mutations; fault0 executes unchanged extracted recursion bodies.
lock=lock.replace('lock_count++;','if(fault==222){return CELL_EDEADLK;}if(fault!=220){lock_count++;}')
unlock=unlock.replace('lock_count--;','if(fault!=221){lock_count--;}')
extras+='template<class T>'+lock""")
replace('8runs/16workers/1440slices/60SC each/600instructions/92pubs','8runs/16workers/1728slices/72SC each/720instructions/110pubs')
replace('memory/TLS30/30','memory/TLS36/36')
replace('foundational and207..219','foundational/applicable207..219/recursive220..222')
exec(compile(source,str(Path(__file__).resolve()),'exec'))

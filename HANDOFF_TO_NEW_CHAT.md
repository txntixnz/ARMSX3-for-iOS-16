# ARMSX3 iOS 16 handoff — 2026-09-30 UTC

User target: iPhone 13 Pro Max / A15 / iOS 16.0 / Dopamine, existing TrollStore.
User explicitly requests using GitHub to compile and says not to monitor the build;
they will report completion. Keep responses concise.

Source: https://github.com/ARMSX2/ARMSX3
Pinned base: 92b931b9fb5eef7f1317cb482917dfc19aceebd9
Build host: txntixnz/ARMSX3-for-iOS-16, main branch.
An empty armsx3-ios16 branch was created in RPCS3-iOS-Releases before the user
created this dedicated repository; no port files or workflows were pushed there.
Workflow: .github/workflows/build-armsx3-ios16.yml
Port overlay: armsx3-ios16/ios; upstream patch: armsx3-ios16/patches.

This checkpoint is P0: native platform diagnostics and a real UIKit patch to the
upstream Metal layer bridge. It is NOT a working emulator; the core is not linked.
Do not claim PS3 firmware installation, game boot or performance is implemented.
Do not confuse the standalone probe target with a full rpcs3_emu build.

Local verification in Linux:
- Compiled/executed ios/tests/vm_probe_test.cpp using g++ C++20 with warnings as errors.
- Tested shared aliases, bounded allocation failure, preservation of an occupied
  hint address, simultaneous 56 GiB layout with PROT_NONE, and cleanup via mincore.
- Apple-style RW reservations fail on this Linux environment at the 12 GiB region;
  this is recorded as an environment result, not a prediction of iPhone behavior.
- Shell syntax and plist/JSON/workflow checks performed before upload.
- Objective-C++/Mach-O compilation requires the Actions Xcode job; no local iOS SDK.

Core findings:
- android/CMakeLists.txt builds rpcsx-android against rpcs3_emu, adding Input sources.
- rpcs3/CMakeLists.txt only excludes desktop Qt when ANDROID is set.
- 3rdparty/CMakeLists.txt assumes desktop MoltenVK paths on APPLE.
- 3rdparty/hidapi/CMakeLists.txt links IOKit on APPLE.
- rpcs3/Emu/Memory/vm.cpp reserves 8+12+32+4 GiB before game boot.
- Utilities/JITASM.cpp, Utilities/JIT.h, Utilities/JITLLVM.cpp and Thread.cpp
  use Apple JIT write-protection APIs; vm_native.cpp has Apple-specific mapping paths.
- Upstream metal_layer.mm used NSView/AppKit; supplied patch supports UIView on iOS.

Next: user reports workflow result; inspect log and fix actual compiler failures,
or inspect on-device diagnostic JSON if build succeeds. Then wire the actual core
and cross-compiled dependencies. A passing JIT test executes only mov w0,#42;ret
through RW->RX memory; it does not establish full RPCS3 JIT compatibility.
Do not shrink guest reservations blindly to fit a small address window.


## P0.1 update
- User confirmed the third Actions run succeeded, then reported instant launch exit
  on iPhone with no Analytics log.
- Removed dynamic-codesigning from signing entitlements (documented TrollStore
  launch-crash risk), plus irrelevant macOS JIT entitlement keys.
- Added final signed-entitlement validation, build number 2, persistent startup
  checkpoints from main(), uncaught Objective-C exception logging, and log sharing
  before any tests. No pre-main or SIGKILL logging claim.
- Removed unused sysinfo_darwin.mm from probe: it had a global Foundation initializer.
- Cause is a strong signing hypothesis, not proven from a device crash report.
- Next: user checks new workflow result and installs build 2, sends startup log.


## P0.2 / build 3
User said continue after P0.1 device report. No need to poll Actions after enqueue.
P0.1 evidence: native Metal and shared aliases passed; iPhone host pages 16 KiB;
RW->RX ARM64 execution returned 42; MAP_JIT EINVAL and pthread JIT symbol absent;
8+12 GiB reservations passed, 32 GiB hook failed ENOMEM.

Source-wide audit at pinned upstream finds g_hook_addr/s_hook only in vm.cpp:
reservation, backing object, logging, mapping and cleanup. Added iOS-only source
patch omitting those lifecycle operations and anchoring stat search after exec.
The patch is applied and audited by CI but vm.cpp is NOT compiled by the probe.
Do not claim an integrated or compiled full emulator memory patch yet.

P0.2 device tests: 24 GiB RW, 24 GiB NONE, original 56 GiB NONE, host-page
reset with neighboring canaries, 32 sequential RW->RX rewrites on the same page
with a fresh joined execution worker for each. ExecutablePage/JITProbe are new
reusable/test helpers; not wired into RPCS3's JIT machinery. No concurrent live
patching is attempted. Tested native host versions with g++ warnings as errors.

Local patch checks: clean pinned checkout accepts both patches; diff --check;
source consumer audit; plist/schema and workflow parse. iOS device results pending.
Next analyze build 3 JSON, then implement the actual core build/dependencies and
JIT integration strategy rather than assuming W^X publication solves live patching.

## P1 core compilation bring-up

User authorized real core integration after successful P0.2 device logs:
24 GiB RW and PROT_NONE layouts, 16 KiB page lifecycle, shared aliases, Metal,
and 32 joined-thread JIT rewrites all passed. MAP_JIT EINVAL, pthread JIT
symbol absent. No concurrent patching or game execution established.

Added separate build-armsx3-ios16-core.yml. It builds iOS FFmpeg from pinned
8.0 source and targets the actual rpcs3_emu archive with LLVM/Vulkan disabled
initially. Patch 0003 separates iOS from desktop Qt/host deps and routes Apple
JIT protection calls through util/apple_jit.hpp, which fails closed if the
symbol is absent on iOS. This is NOT the eventual JIT implementation.
No core IPA yet, no link/boot claim. macOS compilation can only be checked in
Actions; Linux local checks cover patch application, scripts and metadata
validation. Inspect the user's reported workflow result next; do not poll.
See core/README.md for remaining integration requirements.

P1 run 36852284123: iOS FFmpeg compiled successfully; CMake generation failed
because patch 0003 named libusb os/null.c instead of os/null_usb.c. Corrected
and checked all three selected backend files against pinned libusb 87a55632.
P0 run 36852284004 succeeded. No core compiler results yet.

P1 run 36852920200 passed generation and reached real compilation. Patch 0004:
- Disable pinned cubeb macOS AudioUnit backend for iOS (no audio device yet).
- Supply asmjit Apple cache-control header; exclude Android Oboe source.
- Make fmt::throw_exception destructor explicitly non-returning, addressing
  Apple Clang return/fallthrough diagnostics without disabling warnings.
- Use classic-locale round-trip float formatting on iOS 16.0 (to_chars needs16.3).
- Guard desktop disk ioctls and Linux sysfs capacity affinity code.
Build uses ninja -k0 to report all remaining independent compilation failures.
These fixes have local patch and small C++ checks, not Xcode validation yet.


## P2 device crash — 2026-10-08
Build 4 installed and reached Load core. Startup log ends BEFORE dlopen.
Device IPS reports SIGABRT in _GLOBAL__sub_I_PPUThread.cpp.cold.12 during
dyld constructor execution (core UUID 3642d885-ccbe-32b4-b6c7-f463ca97cbee).
PPU globals generate native gateway/escape trampolines through build_function_asm;
its jit_write_guard calls the portability boundary. The prior device report says
pthread_jit_write_protect_np is absent. This is the likely deliberate abort,
not a proven iOS code-signing rejection. Build 5 persists this boundary reason
and call-stack image offsets, and CI uploads a matching line-table dSYM and
unsigned core separately from the installable IPA. It intentionally preserves
fail-closed behavior; this is diagnostic instrumentation, not a functional JIT fix.
Do not claim a successful load or bypass the guard with a no-op. A proper iOS
JIT allocator/publication and concurrency design remains required.


## P2 build 6: immutable startup trampolines
Build 5 device log confirms pthread_jit_write_protect_np absent, abort in
jit_write_guard constructor within PPUThread global initialization. Patch 8
changes only the default (no custom runtime) build_function_asm iOS route to
an independent immutable allocator. Fresh anonymous RW host-page-sized mapping
per function, asmjit resolution/relocation/section copy, instruction cache flush,
then mprotect RX before publishing. Never rewrites existing RX pages and keeps
them until process exit. Uses no MAP_JIT and no RWX mapping. Each successful
publication is logged; errors persist the stage and abort. Custom runtime builders
and other direct jit_write_guard calls retain the fail-closed macOS API boundary.
This is startup code publication, not complete concurrent PPU/SPU JIT support.
Host validation with the pinned actual asmjit generated and executed 401 functions
across four workers, preserving the original RX function. All 8 patches apply
cleanly. Full iPhoneOS compilation and device execution remain unverified locally.
Next test: build 6 Load core, share startup log and crash report if any.


## P2 build 7: SPU startup publication
Build 6 iPhone startup log proves six immutable functions were published as RX.
Next abort is SPUCommonRecompiler global initialization: outer jit_write_guard
remained around ARM64 builders already converted by patch 8. Patch 9 removes
these redundant outer guards only on iOS in tr_dispatch, tr_branch,
tr_interpreter and tr_all. Their completed code still uses isolated immutable
publication. g_dispatcher is pointer data, so allocate the real 2^20-entry
atomic function table in ordinary 64-byte-aligned heap memory, fill with
tr_dispatch, keep for loaded-core lifetime. No executable mapping for the table.
Other runtime guards remain; do not claim complete mutable JIT support.


## P2 device success / build 8 next execution probe
2026-10-08 device build 7: user reports no crash. Uploaded startup log confirms
3887 immutable publications, AFTER dlopen, core state returned 0 (stopped).
This proves loading and read-only state inspection, not guest execution.
Build 8 adds Test core JIT execution after load. Uses actual core
build_function_asm for a synthetic ARM64 return-42 function, executes it, then
64 additional immutable functions published/executed by four joined workers
while checking original still returns 42. UI runs this probe off-main; no
Emulator::Init, guest instructions, mutable JIT or game boot. Share startup log.
Existing verified startup baseline remains the parent commit 76158904f5cff0c934a6b9866d4f8ae448685f8f.

Local validation for build 8: pinned asmjit host build emitted exactly ARM64
MOV W0,#42 (0x52800540) and RET X30 (0xd65f03c0) for the probe; metadata
parses. Full UIKit/iPhoneOS compile and actual ARM64 execution require CI/device.


## P3 execution success / build 9 emulator initialization
2026-10-08 build 8 device log confirms first generated function returned 42;
P3 PASS: all 65 generated functions executed correctly, four workers, original
function retained value 42. This validates immutable code publication/execution
on iOS 16 A15, not mutable guest recompilation.
Build 9 adds Initialize emulator after successful JIT test. Calls real Emu.Init
off-main, headless/null renderer, logs core messages synchronously to startup
log, reports exceptions, core errors and missing config.yml. No game/VM/renderer
boot requested. Configuration uses existing upstream Apple sandbox paths under
HOME/Library/Application Support/rpcs3 and HOME/Library/Caches/rpcs3.
Patch 10 avoids reserving the unused mutable 2 GiB JIT arena solely to memcpy
zero bytes during initialize when both allocation counters are zero. Real
nonempty snapshot path and runtime write guards remain unchanged.
Successful device baseline: parent 2d82e5739a0fa8a08599b8b8b5f1684de0533dc7.


## Build 9 UI compilation fix
Run 37840553352: core archive and dylib compile/link passed. App.mm failed
at property initButton: Objective-C infers init method family when init is
followed by uppercase B; getter returning UIButton is invalid for LoadController.
Rename property initializeButton (init followed by lowercase i) throughout UI.
Initialization probe behavior unchanged.


## P4 device success / build 10 guest-memory probe
Device log confirms real Emu.Init returned with zero core errors and config.yml
created. VFS mounts and default user 00000001 are configured inside sandbox.
Null renderer/headless initialization only; no game or renderer initialization.
Build 10 adds Test PS3 guest memory after Initialize emulator succeeds. Calls
real vm::init, reserve_map main test region at 0x10000/128 KiB, alloc 64 KiB,
validates logical readable/writable flags, writes/checks every byte through
normal and sudo aliases in both directions, deallocates and verifies logical
page removal, vm::close. Logs before risky steps. No guest threads/instructions.
This tests existing core shared-mapping plumbing, not fault-handler correctness
or individual 4 KiB protection on the 16 KiB host. Full device test still needed.
Previous passing initialization baseline is 59ffc5c0254c966de4c9ad73441166dccee8ab34.

Local build-10 check: the actual new guest-memory probe compiles with
g++ -std=c++23 -fsyntax-only against the pinned patched vm.h and utility
headers. UIKit and Apple memory mapping behavior still require CI/device.


## P5 guest memory: iOS shared-memory creation fix (build 11)

Build 10 on iPhone14,3 / iOS 16.0 passed load, immutable JIT execution,
and Emu.Init, then aborted inside utils::shm::shm during vm::init.
Startup log and .ips agree: vm_native.cpp:804, shm_open returned EPERM.
This is a shared-memory creation failure; generated-code execution passed.

Patch 0011 selects an iOS-only unique mkstemp cache file, immediately unlinks
it, sets FD_CLOEXEC and ftruncates to the requested size. The live descriptor
continues through the existing MAP_SHARED mapping/alias/destructor paths.
It leaves desktop POSIX shm and Android memfd paths unchanged. Setup failures
close the descriptor and throw a stage/errno message rather than aborting
on the old shm_open assertion. The anonymous backing file is reclaimed after
its descriptor and mappings are closed; this path uses file-backed storage.

Verified 0011 applies after patches 1–10. Compiled/executed the exact iOS
constructor branch on Linux with filesystem/logging stubs: 64 KiB and 256 MiB
backing sizes, bidirectional alias byte checks and FD_CLOEXEC passed. This
validates POSIX lifecycle, not iPhone mapping behavior; build 11 repeats P5.
No PS3 program, guest page-fault handler or concurrent mutable JIT is tested.


## Build 12: select guest backing with Apple SDK platform macros

Device build 11 still aborted at the original shm_open errno==EEXIST check,
now vm_native.cpp:837. Its line number shifted by exactly the patch size,
but the branch was excluded: IOS was not defined for vm_native.cpp.
Corrected patch 0011 to include Apple's TargetConditionals.h and select
`defined(__APPLE__) && TARGET_OS_IPHONE`. No project IOS define is required.
Build 12 repeats P5; no successful on-device guest mapping claimed yet.


## Build 13: P5 passed; P6 real PPU instruction probe

Device build 12 passed vm::init, 64 KiB allocation, bidirectional shared
alias writes/reads, deallocation and vm::close on iPhone14,3 / iOS 16.0.
Attached ARMSX3-startup.log pid 80782 confirms the entire P5 sequence.

Build 13 adds Test PS3 PPU instructions after P5 passes. It reinitializes
VM, allocates a guest code/data/stack region, registers a direct ppu_thread
context through idm (no named_thread or scheduler), and uses the actual
ppu_interpreter_rt decoder/handlers. Eleven straight-line instructions:
ADDI, ADDI, ADD, STW, LWZ, ORI, ADDI, ADDIS, ORI, STW, LWZ.
Checks arithmetic, 64-bit signed immediate extension, ORI, zero extension
of high-bit LWZ data, exact big-endian guest store bytes, and an explicit
terminating callback. An extra readable opcode pads the tail transition;
the callback never dispatches it. Context ID, diagnostic CPU lifecycle
counter and guest allocation/VM are cleaned up after the run.

Local actual-header syntax check passed without the precompiled header.
Actual core opcode decoder matched all eleven encodings; signed immediate
fields and ORI source/destination fields checked. Decoder-only host harness
stubs log registration and fatal verification helpers, not decode logic.
Full Apple link/compile remains CI; device execution is pending. No branch,
syscall, CPU scheduler, firmware, SPU instruction or game boot tested here.


## Build 14: repair P6 core-load regression

Archive(2).zip shows build 13 aborting inside dlopen before P6 is requested.
IdManager.h:217 make_typeinfo<ppu_thread> reports incompatible duplicate
savestate type metadata. The diagnostic idm::make_ptr<ppu_thread> caused
static registration of raw PPU state, conflicting with the production
named_thread<ppu_thread> metadata. P5 previous device pass remains valid.

P6 now privately owns a direct ppu_thread register context with no ID-map
registration. It supplies a valid PPU construction ID via id_manager::g_id
(thread-local) in an RAII scope and restores the previous ID before execution.
Its custom deleter deletes the context and balances the constructor's CPU
lifecycle counter; no host CPU thread is launched. The diagnostic decoder's
~1 MiB dispatch table now lives on the heap instead of the GCD worker stack.
The instruction chain and expected results are unchanged.

Compiled the exact P6 function into a host object against the actual core
headers. nm confirmed a direct PPU constructor reference and no instantiation
of make_typeinfo<ppu_thread>, raw PPU id_traits_load_func or typedata registry
initializer. Full Apple build and device P6 execution remain pending.


## Build 15: P6 device pass; P7 bounded PPU control-flow probe

ARMSX3-startup(1).log pid 81610 confirms build 14 passed all eleven actual
PPU instructions, expected register/memory results and VM cleanup.

Build 15 adds Test PS3 PPU branches / loops after P6. It reuses the private
context pattern without registry registration, heap decoder and guest VM
lifecycle. The 18-opcode program performs a CTR-counted increment loop,
CMPWI/BNE check, BL subroutine call, ADDI then BLR, guest store/reload and
CMPWI/BEQ success exit. Failure markers and unreachable instructions must
remain skipped. Counts 1, 10 and 64 expect results 6, 15, 69 and instruction
counts 13, 31, 139 respectively. CTR must end at zero and LR must identify
the correct return address. A diagnostic dispatcher follows CIA with a
512-instruction budget and bounds/alignment checks; it dispatches one core
handler at a time. Ordinary handler continuation updates CIA through a
boundary callback; actual taken branch handlers update CIA and return.
It does not invoke the production CPU scheduler, syscalls or mutable JIT.

Both PPU probes compiled to a host object against actual headers; nm found
no duplicate raw PPU registry initializer. Host harness used exact B, BC
and BCLR lambda bodies from pinned interpreter with logging/history hooks
stubbed and simple arithmetic/memory/compare model; all three expected
control-flow traces passed. The host harness is not full core execution;
actual handlers and memory behavior are checked on iPhone by P7 next.


## Build 16: P7 device pass; P8 SPU SIMD and local-store probe

ARMSX3-startup(2).log pid 81732 confirms all three P7 runs: loop counts
1/10/64, executed 13/31/139, results 6/15/69, CTR zero, LR/return correct,
conditional branches and cleanup all passed on iPhone14,3 / iOS 16.0.

Build 16 adds Test PS3 SPU instructions after P7. A private raw-style
spu_thread state (no registry or named_thread) uses a valid construction ID.
SPU decoder setting is temporarily _static during construction and restored
through RAII. It allocates the real 256 KiB shared local store and maps the
five real mirrored views through spu_thread::map_ls. The actual core
spu_interpreter_rt decodes/executes IL, IL, A, AI, IL, STQD, LQD, XORI.
Checks each of four SIMD lanes (42, -7, 35, 32, reload 32, ~32), exact
big-endian quadword bytes, and a marker near the end of LS through all five
mirrors. Deleter frees the VM range lock, invokes the real destructor to
unmap local-store mirrors/release reservation, and balances the direct
context CPU lifecycle counter. It never calls production cleanup(), which
requires a named_thread/LV2 mapping; VM closes after the context is gone.

Local compile of all three CPU probes against real headers passed; nm
found no raw PPU/SPU savestate registry initializers. Host probe used the
actual SPU decoder and eight actual instruction handler bodies, with a
simple in-memory local-store context and SSE gv_add32 helper stub; four
SIMD lane checks and byte-order checks passed. This does not validate the
Apple SIMD backend or Mach/iOS mappings; those are pending P8 device test.
No SPU codegen, DMA/channel, scheduler, firmware or game boot is tested.


## Build 17: fix the SPU shared-memory constructor

Archive(3).zip pid 81907 confirms P6/P7 still pass on build 16. P8 aborted
in private SPU construction before mapping or instruction execution:
utils::shm::shm(u64,u32), vm_native.cpp:583, shm_open EPERM. Patch 0011
handled the storage-string constructor used by guest VM blocks; SPU uses
the flags constructor, which still selected the desktop POSIX shm path.

Patch 0012 routes the flags constructor on Apple TARGET_OS_IPHONE through
the existing patched storage-string constructor, then preserves m_flags.
Other platforms retain their original constructor implementations. Both
iOS overloads now share the same unique/unlinked cache backing lifecycle.
SPU instruction/mirror test is unchanged and still awaiting device pass.

Patch 0012 applies cleanly after 1–11. Host test compiled and ran the exact
new constructor delegation and existing iOS backing branch (filesystem/log
helpers stubbed): flags preserved, 64 KiB rounding, shared aliases at the
first/last bytes, close-on-exec, 64 KiB/256 KiB/256 MiB sizes all passed.
Apple CI/device validation pending; no SPU execution success claimed yet.


## Build 18: SPU device pass and baseline DMA probe

ARMSX3-startup(3).log pid 82026 confirms build 17 passes P8 on the target
phone: eight real SPU instructions, all four SIMD lanes, big-endian local
store, five shared views and context/VM cleanup. P4/P5/P6/P7 also pass.

Build 18 adds Test PS3 SPU DMA transfers after P8. It allocates 128 KiB of
real guest memory and the same private raw-style SPU state used in P8.
Calls the actual spu_thread::do_dma_transfer with the private state for
GET then PUT at sizes 1/2/4/8/16/128/256/16384, repeated twice (32 total).
Cases include guest 4 KiB/16 KiB/64 KiB boundary crossings and the final
256 bytes of LS. GET preserves guest source and guards; transformed PUT
must change exactly the requested guest span. Checks every guest byte
through both aliases, every LS byte through all five mirrors, and that
the PUT range lock returns to zero. Context destruction, guest deallocation
and vm::close are checked in order.

RAII temporarily selects baseline DMA (accurate DMA false, strict rendering
false, FIFO fast) because no renderer or competing guest CPUs exist in this
probe; original settings are restored on success/exception. The probe
bypasses MFC channels/command queue and does not test fences, tag completion,
atomic reservation commands, production CPU scheduler, firmware or games.

New P9 function compiled against actual pinned core headers with GCC C++23.
No raw SPU registry initializer is introduced. Apple compilation/linking and
real DMA execution remain pending CI and the new device test.


## Build 19: SPU channel submission and completion tags

ARMSX3-startup(4).log pid 82129 confirms P9 passed all 16 GET/PUT pairs
(32 transfers), sizes 1 through 16384, two rounds, guards/aliases/mirrors,
range-lock release, private context teardown and VM cleanup. P5–P8 pass.

P10 repeats those transfers through real set_ch_value(MFC_LSA/EAH/EAL/
Size/TagID/Cmd), invoking production process_mfc_cmd rather than the direct
DMA routine. Checks full command capacity before/after each synchronous
submission and empty fence/barrier masks afterward. Rotates tags 0/7/31;
for every transfer checks IMMEDIATE/ANY/ALL tag updates via real read/write
APIs, tag mask readback, exact completion status and consumed status count.
Also checks empty-mask IMMEDIATE and a combined three-tag ALL request.
Ready-count guards prevent entering an empty channel's production wait path.

Calls real spu_thread::cpu_init before channels: constructor-only state has
mfc_barrier/mfc_fence = -1 and must be initialized before submission. This
reset is safe for the private raw-style context and does not start a CPU.
Scoped settings restore accurate DMA, strict rendering, FIFO, command
shuffling and preferred SPU threads. Shuffling/preferred are temporarily
zero, ensuring synchronous commands without competing CPU/renderer work.

GCC C++23 compilation against pinned real headers passed. Device/Apple CI
validation pending. No queued DMA, MFC list/atomic operations, blocking
waits, WRCH/RDCH guest instructions, production scheduler or game boot is
claimed. Next button: Test SPU DMA channels / tags, enabled after P9 PASS.


## Build 20: queued DMA fence/barrier ordering and capacity

ARMSX3-startup(5).log pid 82299 confirms P10 passes all 32 channel DMA
transfers and all completion modes, guards/aliases/lock release and cleanup.
P5–P9 also pass on the same launch.

P11 adds Test SPU DMA queue / ordering. Same private SPU/mappings, real
cpu_init and real MFC channel submission. Shuffling=16 retains commands;
checks queue size/capacity after every enqueue and that memory stays unchanged
until drain. Eight rounds of three dependent chains: GET→PUTF→GETF with
same tag; GET→global BARRIER→PUT→global BARRIER→GET (tags 0/31/7);
and GETB→PUT→GETF with per-tag barrier. Tags 0 and 31 alternate. Each
chain uses 128-byte patterned data, full guest/LS guard checks, both guest
aliases and all five local-store views. Full 16-slot GET queue then verifies
zero writable capacity, all outputs, capacity recovery and completion mask.
Total 88 DMA transfers plus 16 global barrier commands.

Before drain, real ANY and ALL requests must remain not-ready and
get_mfc_completed must exclude pending tags. No empty channel reads occur.
Drain uses production do_mfc(false,false), shuffling=2, steps=true with a
256-pass cap; disables escape to JIT and unbounded must_finish loop. Checks
empty queue/fences/barriers, released range lock, ready ALL result and
read/consume semantics. Settings restored on all exits; context and VM
clean up in established order. This is private-context queue processing,
not production CPU scheduling or guest WRCH/RDCH execution.

Local actual-header GCC C++23 compile passed, plus plist/UI/export checks.
Host harness ran the exact upstream do_mfc body with mock DMA memcpy,
deterministic timestamp masks and mock tag channel: 768 dependency cases
(256 starting seeds × 3 modes) and 256 full queues passed including data
and guards. Does not validate Apple DMA/mappings or native thread waits;
CI and P11 device pass remain pending. Firmware/game boot still untested.


## Build 21: interpreted SPU channel instruction integration

ARMSX3-startup(6).log pid 82450 confirms P11 passes all 24 ordering chains,
full 16-slot queue and 88 total DMA transfers, completion, guards/aliases,
capacity recovery and cleanup. Queue drains took 1–10 passes per chain.

P12 adds Test SPU channel instructions after P11. Reuses the proven P10
32-transfer suite but routes channel writes through actual decoded WRCH,
reads through RDCH, counts through RCHCNT. Encodes real opcodes 0x10d/0x0d/
0x0f in bits 21+, with channel in ra and register in rt. Fetches each opcode
from real big-endian LS scratch address 0x30000, then restores the original
word through RAII; scratch does not overlap any transfer. Heap real decoder.
Hosts supply operand registers; this is a bounded synthetic instruction
sequence, not an autonomous loaded SPU executable or production scheduler.

Private context is cpu_init'ed; RAII temporarily clears its constructor CPU
state so channel handlers return normally, then restores state before its
private destructor. No registered CPU is changed. Shuffling/preferred SPU
threads are zero during this synchronous probe; all config is restored.
4096 instruction cap. RDCH guarded by interpreted RCHCNT readiness to avoid
blocking waits. Checks result in preferred lane 3 and all other lanes zero,
pre-filling all lanes with sentinels. WRCH source preferred lane preserved.
Existing exact byte guards, aliases, LS mirrors, tag modes and cleanup apply.

GCC C++23 actual-header compile passed. Host harness used actual SPU decoder
and three actual handler bodies with mock channels: 105 opcode/preferred-lane
cases passed, including high-bit/0xffffffff values. Apple compile/device DMA
integration pending. No mutable guest JIT, actual CPU thread scheduling,
firmware/game boot or renderer claim. Next: device P12 then CPU lifecycle/
thread-wait support, including iOS 16 availability gap in Utilities/sync.h.


## Build 22: iOS wait-on-address backend and named-thread lifecycle

ARMSX3-startup(8).log pid 84164 confirms P12 passes 1040 interpreted SPU
channel instructions, 32 DMA transfers, all completion modes, guards/aliases,
range-lock release and cleanup. The earlier startup(7) log ended at P11.

Patch 0013 routes Apple TARGET_OS_IPHONE futex calls to a dedicated portable
condition-variable wait-on-address backend, avoiding direct os_sync imports
from the newer Apple API. Desktop Apple retains its existing implementation;
Linux/Windows unchanged. The helper uses 63 locked buckets and stack waiter
records. Registration/value check and wake/removal share the bucket mutex;
wake removes and notifies while locked. Supports mismatch EAGAIN, relative
WAIT timeout, monotonic absolute BITSET timeout, selective mask wake, bounded
wake count, zero wake and complete timeout cleanup. This is a correctness
fallback; native wait performance can be optimized after device validation.

P13 Test core threads / wait-wake: mismatch, 32 timed waits on reused address,
no stale waiter after timeout, four wake-one and four wake-all waiters with
500 ms limits and mandatory joins, then four real named_thread contexts with
TLS registration, thread_ctrl::wait_for(200000), notify, result 42 and join.
Worker lifetimes are joined on exceptions. These are core host threads,
not named_thread<ppu_thread>/SPU scheduling or game execution.

Patch applies cleanly after 1–12. Actual P13 compiles against pinned core
headers (GCC C++23). Host harness ran exact ios_futex helper: 64 timeouts and
address reuse, mismatch, zero wake, wake-one/all, bitset masks and absolute
deadlines passed. Apple CI/linking and iOS real core wait/wake remain pending.
No guest CPU lifecycle, mutable JIT, renderer, firmware/game boot claimed.

## Build 23: stopped PPU CPU-thread lifecycle

Device ARMSX3-startup(9).log pid 85195 confirms P13 mismatch handling,
32 timeouts/address reuse, four wake-one/four wake-all waiters and four core
named-thread wait/notify/result42/join cycles all pass on iPhone iOS16.

P14 adds Test stopped PS3 PPU thread after P13. Four private real
named_thread<ppu_thread> instances are constructed in standby with
stx::launch_retainer and scoped IDM construction ID. Guest 64KiB stack is
allocated through VM. Only constructor exit flag is removed; stop/wait/
suspend/memory remain. No guest cpu_task, instructions or runnable scheduler
is entered. Start actual CPU thread, observe iOS stopped-wait counter and
live CPU count, verify stop/stack, set exit + notify, join, destroy, then
verify created/deleted/live counters balance. Normal CPU TLS cleanup owns
deleted accounting; never manually increment it for these named contexts.
Thread destructor requests exit and joins on exceptions before VM closes.
Profiling is disabled and scheduler OS setting scoped/restored.

Patch 0014 moves profiler existence check into actual profiling registration
paths; a nonprofiling stopped headless thread needs no polling profiler.
Read-only iOS counters expose live CPU count and cumulative stopped-wait
entries; guarded by Apple TARGET_OS_IPHONE with explicit target header.
Wait-entry observation means reaching state.wait, not proof of OS sleep.
UI now scrolls so added diagnostics and Share startup log remain accessible.
CFBundleVersion 23. IPA artifact name remains ARMSX3_iOS16_INSTALL_THIS_IPA.

Validation: patches 13 and 14 apply cleanly after pinned patches 1–12;
exact P14 probe compiles against actual pinned core headers with GCC C++23,
including standby named_thread<ppu_thread>, configuration and state API.
Whitespace check passed. Apple compile/link and device lifecycle pending.
No runnable guest CPU scheduling, mutable guest JIT, firmware, renderer or
game boot claimed. Next: device P14 result, then bounded runnable guest task.

## Build 24: PowerPC instructions on real PPU workers

Build23 Actions run37940582228 succeeded. Device startup(10).log pid85487
confirms all four P14 stopped PPU CPU-thread waits/exits/joins and balanced
counters pass. This is device evidence, not just successful compilation.

P15 Test PPU worker instructions follows P14. Four private standby
named_thread<ppu_thread> workers enter real cpu_thread::operator() and
ppu_thread::cpu_task. Production cmd_list queues set_gpr r6 (guest output),
set_gpr r30 (private host diagnostic pointer), then ptr_call. That queued
callback verifies CPU/core TLS and dispatches six actual interpreter handlers:
addi seed, addi -7, add, stw, lwz, ori. Four seeds42/53/64/75 produce
35/46/57/68; terminator marker proves whole bounded chain ran. Callback
sets exit before publishing completion; host joins before inspecting context
and memory. Verify guest big-endian store, privileged alias, 16-byte guards
on both sides, and created/deleted/live counts. Guest64KiB and heap decoder
cleaned afterward. Completion deadline2s; named-thread destructor aborts/joins
on error. Profiling/OS-thread-scheduler configuration restored on exit.

This intentionally clears private constructor stop/exit/suspend/memory/wait
flags before start and bypasses LV2 admission. It proves cpu_task command
queue dispatch plus real guest handlers on the CPU host thread. It does NOT
prove autonomous guest fetching, fast_call, LV2 runnable scheduling, guest
syscalls, concurrent PPU/SPU, firmware, mutable JIT, rendering or game boot.
No production registry entries or profiler background threads are added.

CFBundleVersion24. Workflow display name changed from stale P1 compilation
to ARMSX3 iOS16 Installable IPA build; workflow filename and IPA artifact
ARMSX3_iOS16_INSTALL_THIS_IPA remain unchanged. Exact P15 function compiles
against pinned core headers with GCC C++23; whitespace validation passes.
Apple linking and iPhone runtime remain pending until user brings results.
Next: device P15, then stronger CPU wait/resume/queue coverage or bounded
normal guest dispatch without firmware dependencies.

## Build 25: one-tap sequential diagnostics

Device ARMSX3-startup(20261009-175754).log pid86820 confirms P15:
four real PPU worker command queues run six actual PowerPC handlers each;
all 24 instructions, registers, CPU TLS, big-endian stores, aliases, guards,
join and balanced counters pass. User asked to automate the growing list
of individual taps. This build changes diagnostic UI only, no new CPU test.

App.mm replaces 14 individual stage buttons with Run all tests, progress,
Run next test only, Stop after current test, Share startup log and transcript.
A single stage catalog retains exact P2–P15 order and symbols. P2 dlopen
still runs on UIKit main after a queue yield, same as validated manual app.
P3–P15 run one at a time on GCD, returning to main before scheduling next.
One-tap run advances only on result0; missing export/load/state/test failure
halts, disables rerun in that process and instructs fresh app launch.
No test auto-starts on launch. Completion requires one Share log tap.

The busy guard disables reentry and sharing until current test finishes.
Stop/background pauses after the current stage without tearing down VM or
threads; remaining stages resume in the same process without rerunning
Emu.Init or completed tests. Queued-next-stage checks stop request too.
Idle timer disabled during run and restored on completion/pause/failure.
NSUserDefaults pending-stage marker synchronized before potentially crashing
calls and cleared after success; next launch shows interrupted stage but
restarts sequence from P2, never restores partial VM state. Startup log is
still append-only/fsynced; AUTO BEFORE/PASS/FAIL milestones complement core
P# logs. No sharing or messages sent automatically.

CFBundleVersion25, IPA artifact remains ARMSX3_iOS16_INSTALL_THIS_IPA.
Validation: exact catalog compiled/executed with GCC C++23; all 14 exports
verified against CoreBridge and ordering compared to previous manual app.
Source checks cover stop/reentry/failure guards and single test dispatch;
whitespace check passed. UIKit/Objective-C++ compilation and device one-tap
runtime pending GitHub CI/user report. Core unchanged from passing build24.
Next: validate automated suite, then stronger guest execution/scheduling.

## Build 26: persistent PPU queue wait/wake

Device startup(20261009-181913).log pid87066 confirms build25 one-tap
runner completes P2–P15 in exact order with final AUTO PASS. No repeated
manual stage taps needed. Build26 adds P16 automatically as stage15.

P16 keeps one private real named_thread<ppu_thread> alive for32 batches.
Start with empty queue, observe real cmd_wait entry, publish two set_gpr
commands and ptr_call using cmd_list, then production cmd_notify.store(1)/
notify_one. Each callback runs six actual PPU interpreter instructions,
snapshots registers/TLS and publishes monotonically increasing completion
with release/acquire. Observe return to empty queue, validate distinct seed
results, big-endian output, adjacent guards and privileged alias. Repeat32
(including eight1ms parking opportunities), then publish queued exit callback,
notify/join and verify created/deleted/live counters and guest cleanup.
192 PowerPC instructions run on the same persistent CPU worker.

Patch0015 adds read-only cumulative iOS command-wait entry counter in
PPUThread.cpp; explicit TargetConditionals guards. Counter observes reaching
wait_on, not proof of kernel sleep. Private context still bypasses LV2
admission by clearing constructor stop/exit/suspend/memory/wait flags.
No autonomous guest fetching, firmware, mutable guest JIT, full LV2 scheduler,
renderer or game boot claimed. Only one diagnostic CPU worker is live.

Host mutates instruction/decoder storage only between acknowledged batches.
Snapshot release/acquire protects result reads, worker is waiting before next
batch. StopWorker guard sets exit and wakes CPU state AND command wait on
exceptions, before named_thread destructor joins and before program/decoder/
VM lifetime ends. No manual deleted accounting. Scoped profiling-off and OS
scheduler settings restore on exit. Per-wait/batch deadlines2s.
CFBundleVersion26, IPA artifact unchanged ARMSX3_iOS16_INSTALL_THIS_IPA.

Validation: exact P16 compiles against actual pinned core headers GCC C++23.
Patch applies cleanly. Exact upstream cmd_wait body in host mock queue/
notification harness passed64 publications alternating before/after wait,
and notified empty exit. This checks queue-wait algorithm, not full iOS atomic
backend. Automated catalog15 stages/exports verified; whitespace check passes.
Apple build and device persistent-CPU wait/wake remain pending user results.
Next: P16 device report, then bounded normal guest dispatch/scheduler work.

## Build 27: normal PPU fetch/cache dispatcher with diagnostic bounds

Device startup(20261009-183734).log pid87211 confirms P16 all32 batches,
192 instructions on one persistent PPU worker, notifications/waits/guards/
aliases and cleanup pass. Final AUTO PASS confirms all15 stages completed.

P17 adds actual ppu_thread::exec_task static-interpreter guest fetch/cache
path on real named_thread<ppu_thread>. Commit RW handler-pointer cache for
the diagnostic64KiB guest allocation (128KiB cache), populate18 decoded
instruction pointers, and fetch from guest memory at CIA. Reuses P7 program:
CTR loops1/10/64, comparisons, branches, bl/blr, guest store/reload. Expected
13/31/139 instructions, result6/15/69, CTR0 and LR at instruction7.
These are now dispatched by exec_task rather than the bridge's own loop.

Patch0016 adds iOS-only thread-local diagnostic range/budget scope invoked
through armsx3_ios_ppu_exec_bounded. Normal execution leaves scope null.
Diagnostic mode uses existing ppu_ret single-step boundary so each fetch is
range-checked and counted before handler invocation. Program end returns
count; invalid CIA -1; exhausted budget -2; early stop -3; bad input/mode -4.
Two negative cases test eight-step exhaustion in64-iteration loop and initial
CIA above end, verifying no output memory writes. TLS probe scope restores
on all exits, including nested scopes. Host deadline2s per real worker.
Normal context still bypasses LV2 admission and enters via queued ptr_call;
no fast_call/firmware/syscalls/autonomous loader/full LV2 scheduler claimed.

Port fix: exec_task previously called apple_jit_write_protect unconditionally.
On this iPhone pthread_jit_write_protect_np is absent and shim aborts. The
call now belongs only inside non-static (native-JIT gateway) branch. Static
interpreter uses already-published handler code and needs no such API.
Native-JIT protection failure check remains intact; no mutable JIT enabled.
Handler cache is data RW, not RWX native code. VM close decommits it.

P17 automatically stage16 in Run all tests; CFBundleVersion27. Artifact
unchanged ARMSX3_iOS16_INSTALL_THIS_IPA. Exact bridge compiles against pinned
headers GCC C++23. Patch16 applies cleanly after15. Exact patched exec_task
and bounded helper host harness with mock handlers validates fetch/end/
range/budget/stop/input guards, TLS scope restoration and static/native-JIT
protection routing. This host check does not run actual PPU instruction
handlers; those need Apple CI/device integration. Whitespace passed.
Next: device P17, then guest loading/admission and fuller execution path.


## Build 28: core ELF parsing and bounded loaded-code execution

Device startup(20261009-185821).log pid88095 confirms P17 loops1/10/64
with dispatch counts13/31/139, range/budget rejection and cleanup PASS.
Final AUTO PASS confirms all16 stages completed on the iPhone.

P18 constructs a small big-endian ELF64 PPC64 ET_EXEC fixture with two
PT_LOAD segments using the actual core header types. Writes it through
core fs::file to the cache and reopens it through ppu_exec_object. Uses a
bounded diagnostic mapper within a private64KiB VM allocation; checks
filesz<=memsz, payload size and guest range with subtraction-safe bounds.
Loads seven words (six instructions plus readable padding), an8-byte PS3
OPD code/TOC descriptor, and a64-byte data segment with zero-filled BSS.
Rejects bad magic/class/endian/machine and truncated payload using actual
ELF reader errors. Oversized memsz is separately rejected by mapping guard.
The trusted synthetic fixture is the only file input, not a user import.

Sets CIA/TOC from loaded OPD and executes six loaded instructions through
P17 bounded actual exec_task/cache dispatch on one real PPU worker. Checks
add/store/reload/OR results35/0x123, six steps, TLS, full64KiB normal and
privileged alias contents, guard bytes, worker counters and VM cleanup.
Cache region remains RW data containing handlers, no mutable native JIT.
Scoped core configuration restores; file removed after test, worker joined
before interpreter and guest memory release. Same private CPU admission
bypass as P17. This is NOT full ppu_load_exec, LV2 module admission, firmware,
syscalls, external executable loading or game boot.

P18 is automatic stage17, CFBundleVersion28. Installable artifact remains
ARMSX3_iOS16_INSTALL_THIS_IPA. Exact bridge probe compiles GCC C++23 with
pinned core headers. Host harness runs actual templated ELF reader and
actual container_stream with minimal unrelated filesystem/error stubs:
five malformed cases, valid segment payloads, oversized mapping guard,
OPD/BSS and every byte of64KiB mapped memory PASS. Host harness does not
execute PPU handlers or exercise Apple on-disk fs/VM/CPU integration.
Catalog symbols/count and whitespace verified. Apple CI and device
integration pending. Next: device P18 result, fuller loader/admission.


## Build 29: production PPU code registration and core decoder

Device startup(20261009-212347).log pid88876 confirms P18 core on-disk
ELF parsing, malformed rejection, bounded mapping, OPD/BSS, six loaded
instructions and cleanup PASS. Final AUTO PASS confirms all17 stages.

Inspection: full ppu_load_exec also creates process/HLE modules and system
threads, requiring staged initialization beyond the private P18 probe.
P19 first tests its actual ppu_register_range/ppu_register_function_at
path with the same trusted diagnostic ELF. No full loader call yet.
Reuses P18 file parse and bounded mapper, initializes only core-owned
ppu_interpreter_rt in g_fxo if absent (requires existing P4 object table).
This decoder is retained under normal core object ownership until the next
Emu reset; no manual destruction of the fixed object's bookkeeping.

Two executions of six instructions each: production range registration
initializes every handler slot to fallback and segment tag to0 for64KiB;
first pass uses actual lazy ppu_fallback decode on execution; second
re-registers the range and uses eager ppu_register_function_at before
execution. Real bounded exec_task verifies six decoded handlers afterward,
untouched outside handlers, page_executable metadata, normal/super memory
contents, OPD/BSS/results, TLS and balanced named CPU lifecycle counters.
Scoped ppu_debug=false avoids unrelated statistics storage and restores.
Guest executable flag is metadata, not native RX or writable JIT.
Production registration commits128KiB RW handler cache plus32KiB segment
tag cache. The latter lives beyond VM close's8GiB cache decommit, so this
probe explicitly decommits that32KiB region via scoped cleanup on both
success and exception paths. Existing VM close handles main cache region.
Still private CPU admission and a diagnostic mapper; no firmware/game boot.

Automatic stage18, CFBundleVersion29, same installable IPA artifact.
Exact bridge compiles GCC C++23 against pinned headers. Host harness uses
exact production registration routines with mocked VM/commit/decoder
boundaries: aligned addresses/sizes/page flags, full64KiB fallback slots,
six eager handlers and outside guards, re-registration and empty-range
no-op PASS. Does not emulate actual lazy handler execution or iOS VM
protection; device integration remains pending. Catalog/export/whitespace
checks PASS. Next: P19 device result, fuller loader/admission preparation.


## Build 30: real executable analysis and static module preparation

Device startup(20261010-012744).log pid93842 confirms P19 lazy fallback
and eager function registration each execute six loaded instructions,
cache/memory/CPU cleanup PASS. Final AUTO PASS confirms all18 stages.

P20 uses the trusted ELF fixture plus BLR and readable padding: seven
instructions,32-byte code PT_LOAD,64-byte OPD/data PT_LOAD. Maps bounded
segments as before, builds local ppu_module<lv2_obj> using actual segment
metadata/pointers and address-to-segment map. Adds explicit8-byte OPD
section. Calls actual module.analyse(0, OPD, code+28, empty patches/exports,
2s deadline callback). Requires entry function discovery and bounds every
returned function/basic block within28-byte executable region before
preparation. No manufactured function list or bridge decoder loop.

Patch0017 adds iOS-only armsx3_ios_ppu_prepare_module wrapper inside
PPUThread.cpp. Requires stopped Emu, static decoder, initialized fixed
object table/decoder and nonempty module. Initializes only core-owned
ppu_toc_manager if absent, then calls normal ppu_initialize(module,false,0).
Static path's false return means no native compilation needed, not failure.
Core owned decoder/TOC manager retained until normal table reset; debug
false means no diagnostic TOC entries persist. No global object sweep,
LV2 admission, system threads, firmware or native JIT introduced.

Production registration + module initialization must prepare all seven
handlers. Actual exec_task on private real PPU worker executes arithmetic,
store/reload/OR and BLR with LR=end; expects seven steps,35/0x123 results,
unchanged TOC, full64KiB normal/privileged alias guards, outside cache
unchanged, CPU counter balance, explicit32KiB segment-cache decommit and
VM teardown. Full ppu_load_exec remains uncalled; mapping and CPU admission
remain diagnostic. No firmware, external executable import or game boot.

Automatic stage19, CFBundleVersion30. Patch applies after0016. Exact bridge
compiles GNU C++23 against pinned headers (GNU mode needed for upstream
u128 bit operations in analyser header; Apple CI uses Clang).
Host harness compiles/runs actual PPUAnalyser.cpp analysis and helper
functions with actual instruction-type decoder and module pointer logic;
only logging/formatting/main-thread-ID boundaries are stubbed. Real analysis
finds entry0x10100,size28,one block,TOC0x10400, covers seven instructions;
empty-module rejection and cancellation callback PASS. No YAML validator
included in harness, no analyser algorithm changes. Separate exact iOS
wrapper harness with mocked objects/ppu_initialize verifies null/empty/
running/decoder/table guards, no rejected side effects, one TOC init and
static false-return semantics. Does not exercise full production module
initialization or real PPU handlers on host; Apple CI/device pending.
Catalog,exports,whitespace checks PASS. Next: P20 device report, fuller
loader/process initialization and admission.


## Build 31: actual fast_call, guest stack frame and HLE return

Device startup(20261010-091005).log pid94257 confirms P20 analyser finds
one entry function/block, production ppu_initialize prepares seven handlers,
loaded execution/return and cleanup PASS. Final AUTO PASS all19 stages.
Older startup(20261010-083732).log was previous installed P19, all18 PASS;
correct build30 artifact link provided, later device result above is P20.

P21 extends trusted ELF fixture to14 guest instructions plus readable
padding (60-byte code segment, bounded analysis end=code+56). Guest saves
LR in a128-byte stack frame with MFLR/STDU/STD, copies callee TOC into r9,
executes arithmetic/store/reload/OR, reloads saved LR with LD, restores SP,
MTLR/BLR. Actual analyser on loaded ELF segments and OPD discovers entry;
normal static module initialization prepares all14 handlers as in P20.

Core function manager is targeted-initialized if absent, requires addr0,
and temporarily points to private guest address+0x800. Only actual index1
HLE RETURN handler is registered at address+0x80c, with normal fake OPD
at address+0x808. This is not full HLE module/dispatch table initialization.
Scoped manager address restores to its previous0 on all exits and explicitly
before VM teardown; initialized core object retained until normal reset.

Patch0018 extends iOS TLS diagnostic probe with optional return_addr;
existing exec_bounded defaults0 retain end/range/budget semantics including
CIA0 rejection outside range. Call probe admits only its executable interval
and exactly one HLE stop slot. Recognizes completion only when actual HLE
handler sets RET and CIA=stop+4; bare fallthrough to code end is failure.
New armsx3_ios_ppu_call_bounded validates static mode, active function
manager/stop address, nonzero caller CIA, no pending RET/savestate, disjoint
aligned ranges and budget. Calls actual context.fast_call(begin, calleeTOC),
then verifies restored caller CIA/TOC/LR/function/log-prefix and cleared RET.
Normal fast_call code is unchanged; normal dispatch has null diagnostic TLS.
No native JIT or autonomous scheduler introduced.

Expected14 guest instructions +1 actual HLE RETURN handler =15 dispatch
steps. Bridge seeds distinct caller CIA/TOC/LR and SP=address+0x8000, checks
result35/0x123, guest r9=ELF TOC, restored caller registers and stack pointer.
Whole64KiB guest/privileged alias comparison includes exactly stack backchain
and saved return address, fake OPD and output store; no outside writes or
cache mutations except explicit stop handler. Named CPU counters balanced,
manager addr reset, segment cache decommitted and VM closed. Still private
CPU admission, diagnostic mapper/stop-slot setup, no full ppu_load_exec,
firmware/syscalls/external imports/game boot. interrupt_thread_executing
follows normal fast_call semantics; no claim it is restored by the core.

Automatic stage20, CFBundleVersion31. Patch0018 applies after0017. Exact
bridge compiles GNU C++23 with pinned headers. Host actual analyser with
new fixture finds entry0x10100,size56,one block,TOC0x10400 and covers14
instructions (same limited logging/formatting stubs as P20). Exact real
fast_call/exec_task and both bounded helpers host harness with mocked CPU,
flags, VM and instruction/HLE handlers verifies normal HLE return, budgets1/
2/3/64, invalid range, fallthrough rejection, caller context restoration,
nested TLS and prior zero-CIA guard. Mock flags implement bitset add/remove
like core, not integer subtraction. This does not execute actual PPU guest
handlers or iOS VM stack writes; Apple CI/device integration pending.
Catalog,exports,selected whitespace PASS. Next: P21 device report then
broader loader/process admission and syscall integration.

## 2026-10-10 — P21 device PASS; build32 / P22 fixed ELF segments
Device log ARMSX3-startup(20261010-134804).log, pid95866 confirms all20
stages PASS, including14 guest instructions +actual HLE return through
fast_call with guest stack/LR and caller context restoration.

P22 adds armsx3_core_test_elf_fixed_segments. An on-disk ELF has code at
0x10100 and data/OPD at0x30400, separated64KiB backing pages. Uses actual
vm::reserve_map and block_t::falloc used by ppu_load_exec, not vm::alloc
followed by a memcpy inside one existing allocation. Diagnostic reserves a
small256KiB main area, then repeats loader-style any/reserve/flags/falloc
operations. Requires exact area reuse; checks fresh zero fill before copy,
full page payload/BSS/alignment padding and privileged aliases. Gap pages
0x20000/0x40000 must stay unallocated. Actual overlapping and below/end-area
allocations must fail. First successful fixed allocation is rolled back
before retrying the two-segment mapping. Exact64KiB deallocation and absent
mapping flags checked; VM close also handles exceptions.

Automatic stage21; CFBundleVersion32. No new core patch. Exact P22 bridge
compiles GNU C++23 against pinned headers. Actual core ELF reader host test
validates separate segment addresses, sizes, entry/OPD, and rejects mapping
of oversized, end-overflow, below-area and filesz>memsz parsed segments.
Catalog/exports and selected whitespace checks PASS. Host cannot validate
iOS VM mappings; new device stage pending. Does not call full ppu_load_exec,
set ELF read-only page protections, analyze/execute the P22 fixture or load
firmware. P20/P21 continue covering analysis/preparation/execution. Next:
loader process/HLE initialization, real executable loading and syscalls.

## 2026-10-10 — build33 / P22 block ownership cleanup fix
Archive(4).zip includes build32 crash, pid96101 and startup log. P2..P21
PASS. P22 overlap/boundary rejection and partial rollback PASS. Fatal
vm::close ensure(block.use_count()==1), vm.cpp2796. Diagnostic retained
`const auto area` shared_ptr while closing the VM on its success path.
Scope unwinding would release it on an exception; explicit success close
occurred before scope exit. Build33 changes area to mutable auto, explicitly
resets it immediately before vm::close, and logs the cleanup boundary.
No core assertion weakened. P22 payload/BSS checks have no individual pass
marker, so not independently claimed as confirmed from this crash log.
CFBundleVersion33, still21 automatic stages. Exact corrected bridge compile
PASS. Host shared ownership teardown harness reproduces retained-reference
failure and verifies reset gives sole VM ownership; this is a ownership
model, not actual iOS VM integration. Device retest pending.

## 2026-10-10 — P22 device PASS; build34 / P23 protected ELF code
ARMSX3-startup(20261010-142551).log, pid96230 confirms all21 stages PASS,
including P22 fixed ELF mapping, full page BSS/padding/aliases, rollback and
block reference release/VM close. Build33 crash fix confirmed on device.

P23 armsx3_core_test_elf_protected_code clones the successful P22 separate
fixed mappings; code is now page-aligned0x10000, data/OPD0x30400. Actual
core ELF reader loads two PowerPC instructions: addi r3,0,42; stw r3,0(r6).
Core-owned static decoder, production ppu_register_range and per-instruction
registration, actual bounded exec_task on private real named PPU worker.
Before execution invokes vm::page_protect like loader:4KiB aligned request
clears page_writable; actual64KiB backing expands the affected range. Tests
all16 guest page flags RO/readable/executable, data separatelyRW, unmapped
gap protection rejected, RW restoration and reapplication of RO. Never
attempts deliberate code write/fault or writes unmapped pages on device.

Guest bounded2 dispatch steps store42 to data+32; requires correct worker
TLS, r3/CIA, creation/deletion/live counters, every byte of both backing
pages and privileged aliases (only store output changes), RO code flags,
RW data and absent gap pages. Execution cache data remains separate from
read-only guest code. Explicit segment cache decommit, guest deallocation
while code remainsRO, area.reset before vmclose. Configuration scoped,
static decoder/os scheduler/profiling off. CPU admission remains private,
not actual LV2 process startup. No native RX/JIT pages added.

CFBundleVersion34,22 automatic stages. Exact P23 bridge compiles GNU C++23
against pinned headers. Actual ELF reader host test validates aligned code,
separate data and two-instruction payload, OPD/layout and four invalid
mapping bounds. Catalog/exports/whitespace PASS. Host cannot validate iOS
memory protection or actual PPU handler execution; device test pending.
Still no full ppu_load_exec, firmware, imports/syscalls, game boot or RSX.

## 2026-10-10 — P23 device PASS; build35 / P24 production HLE table
ARMSX3-startup(20261010-145448).log, pid96337 confirms all22 stages PASS;
P23 real static interpreter fetches read-only code, executes two PowerPC
instructions storing42 to separated writable data, verifies permissions,
aliases/guards, then cleans VM and worker correctly.

Patch0019 factors the existing production HLE descriptor/cache builder from
ppu_initialize_modules into ppu_initialize_hle_table(const vector&). The
normal module initialization passes its same original hle_funcs to this
helper; the allocation/registration/write/protection body is unchanged.
New iOS diagnostic-only prepare_hle_table wrapper requires stopped emulator,
static decoder, initialized fxo/interpreter, unused function manager addr,
and2..8192 functions (one64KiB table bound). Does not initialize module
variables or linkage exports; no firmware/system process admission.

P24 clones P21 actual ELF analyse/preparation/fast_call and14 guest
instructions with stack/LR restoration. Main reserved area now192KiB; guest
allocation64KiB plus separately vm::alloc-owned64KiB HLE table. Calls real
production builder instead of manually installing only index1. Verifies
all descriptors self-address/zeroTOC and manager func_addr pairs, odd cache
slots match every registered handler, even slots remain fallback, entire
backing page RO/readable/executable. Actual fast_call returns through table
index1 HLE RETURN;15 dispatch steps. Full guest64KiB expected bytes include
stack backchain/returnaddr and output35; old fake OPD removed. Full table
page and privileged alias checked (including zero padding), all cache slots
checked after execution. CPU counters/TLS/context checks inherited.

TableCleanup RAII clears manager.addr and decommits table segment cache;
success deallocates actual table64KiB then guest, releases guest segment
cache and vmclose. On exception scopes unwind before vmclose. No retained
block shared_ptr. Retains core-owned function-manager/interpreter objects
for normal core reset. Patch19 targetPPUModule includes PPUInterpreter.h
explicitly for diagnostic type use.

CFBundleVersion35,23 automatic stages. Patch dry-run PASS against pinned
source (no previous patch modifies PPUModule). Exact new bridge and exact
extracted production builder/wrapper compile GNU C++23 with pinned real
headers. Host runs exact builder and wrapper with mocked VM/fxo/state:
3887 descriptors/handlers, RO protection, reuse without allocating another
table, stopped/static/interpreter/existingaddr/count guards PASS. Host mock
does not execute actual guest handlers or iOS VM protection. New device
integration pending. Prior ELF stack fixture/analyser behavior unchanged.
Production table body byte-preservation, catalog/exports/whitespace PASS.
Next: module linkage/process initialization and full executable loading.
Still no full ppu_load_exec, firmware, system syscall/gameboot/RSX.

## 2026-10-10 — P24 device PASS; build36 / P25 bounded import linkage
ARMSX3-startup(20261010-153014).log, pid96501 confirms all23 stages PASS.
Production HLE table has3877 descriptors/handlers on iOS (host table model
used3887; no hardcoded count assumption in device probe). Actual ELF call
returns through production table and cleans all caches/VM/thread state.

P25 clones P24. Synthetic ELF now includes192 file bytes/256 memory bytes
in its data segment: OPD, a44-byte ppu_prx_module_info import record, NUL
terminated iOSProbe name, two FNIDs and two address slots; remaining64 bytes
BSS. Known NID0x49524e31 locally maps to HLE RETURN index1; unknown
0x49524e32 deliberately unmapped. Patch0020 wrapper checks exactly bounded
record shape/addresses/name/NIDs/stubs, builds local ppu_linkage_info, invokes
actual ppu_load_imports, verifies two imports, linkage sets, use addresses,
no relocations, known target and unresolved INVALID table descriptor. No
static module/global export linkage initialized or retained. This tests
production import parsing/linking with synthetic records; does not resolve
real game/library imports or call arbitrary HLE functions.

17 guest instructions include prior stack/result logic plus LWZ r11 from
import slot(r10), LWZ r12 from resolved OPD, MTLR r12 and BLR. Expected18
bounded dispatch steps including actual HLE RETURN. Checks r11/r12 targets,
restored caller CIA/TOC/LR/SP, full64KiB guest bytes including exactly linked
import slot changes, guest output35 and stack writes. Complete HLE table
page/cache/alias and cleanup checks inherited. Analyzer/preparation/range
bounds68 bytes, opcodes72 including zero padding. Data fixture and new
import-slot guards verified. Fixed private CPU admission remains in use.

CFBundleVersion36,24 automatic stages. Exact bridge and private wrapper
compile against pinned real headers. Actual ELF reader tests new fixture,
five malformed cases/oversized bounds PASS. Actual core analyser host runs
new17-instruction fixture: entry0x10100,size68,one block,TOC0x10400, complete
coverage and cancellation/empty guards PASS. Actual production import
function and exact wrapper run on host-backed real ppu_module and vm ptr
layout; known/unknown resolution, use/import sets, bad start/count guards
PASS. Host external services mocked: fxo manager/state, function vector,
logging/formatting, unsupported ref patching and contended mutex paths
throw. Actual uncontended mutex path used. No guest instruction handlers or
iOS mappings executed on host; device integration pending. Patch0020 dry
run after0019 PASS; catalog/exports/selected whitespace PASS.
Next: actual static module export setup, system process initialization and
full executable loader. Firmware/gameboot/RSX still untested.

## 2026-10-10 — P25 device PASS; build37 / P26 guarded PRX export observation
User provided ARMSX3-startup(20261010-160337).log. Last device PID96695
reports AUTO PASS all 24 stages through P25: actual ELF import parser/linker
handles known HLE RETURN and unresolved INVALID import, executes 17 real guest
instructions/18 dispatch steps, checks full guest/HLE table, CPU counters,
cleanup; zero latest-stage failures. The log is cumulative (~107k lines), so
only the latest PID/run establishes the result. No complete PS3 executable,
firmware, LV2 process, RSX or game boot has been tested.

Build37 adds stage P26 (25 ordered stages): repeats the unchanged working P25
end-to-end core diagnostic, then builds a44-byte PRX-export module descriptor
inside the previously zero-filled 64-byte fixture BSS. Reuses existing
NUL-terminated iOSProbe name and known FNID, adds a one-entry exported
function OPD address table. The iOS-only patch0021 wrapper validates exact
segment/record/address bounds and calls real static ppu_load_exports in
for_observing_callbacks mode, checking one guest function descriptor is found
and no global module linkage is registered. Also rejects an invalid export
record start. This intentionally does NOT yet execute a guest-to-guest call,
register exports globally, initialize a PS3 process or boot a real EBOOT.

Changes: append 0021-ios-bounded-export-discovery.patch; CoreBridge.cpp adds
armsx3_core_test_elf_export_discovery; App.mm adds P26; Info.plist bundle37.
Existing P2-P25 paths remain unchanged. Action workflow applies all numbered
patches lexicographically. Test on-device after the new installable IPA build,
share startup log from the latest PID. Next: production export registration,
import backpatch and guest-to-guest function call, followed by real executable
loader and process setup. Build37/device behavior NOT yet verified.

## 2026-10-10 — P26 assertion repair / build38
New log ARMSX3-startup(20261010-162211).log, latest PID96907: all 24
stages P2-P25 PASS. P26 also completed its import/HLE/guest-execution and
memory checks, then failed at the export-observation assertion. The real
scanner log already shows iOSProbe FNID0x49524e31, OPD0x10400,
entry0x10100 and TOC0x10400 correctly discovered. There is no device crash
in this latest diagnostic sequence; failure is returned as -1 by the bridge.

Root cause: patch0021 incorrectly required localLink.modules to stay empty.
The pinned production ppu_load_exports creates its local iOSProbe module
shell before the for_observing_callbacks continue. Observation skips actual
function/variable registration, but still creates the empty local shell.

Build38 preserves the production scanner and existing P2-P25 paths. The
wrapper now requires exactly one iOSProbe module with empty functions,
variables and library locks, plus the existing one-descriptor/empty-special
checks. CoreBridge logs the exact wrapper return code on failure and checks
invalid record start separately. Bundle version advances37->38; still25 tests.

Validation in Work: a temporary C++20 host harness compiled the actual pinned
production export scanner, PRX record and linkage structure with mocked VM,
logging/HLE dependencies. It reproduced build37's -3 and passed the fixed
wrapper, bad/null/stopped-state/metadata rejection, byte preservation and
repeated observation without global registration. Address/undefined behavior
sanitizers passed (leak scanning disabled due to host ptrace restrictions).
Sequential PPUModule patches0019/0020/0021 checked and applied on pinned source.
Host validation does not establish iOS/device success. Install build38 after
Actions succeeds, run all25 tests and inspect newest PID. P26 device success,
complete executable loader, firmware/LV2/RSX/game boot remain untested.

## 2026-10-10 — P26 device PASS; build39 / P27 registration and backpatch
User supplied ARMSX3-startup(20261010-164400).log. Latest PID96972 reports
AUTO PASS all25 stages through P26, including production PRX export observation,
memory/table checks and cleanup. The accidental @Create image tag is a browser
issue; user does not want image generation for this task.

Build39 appends patch0022-ios-bounded-export-registration.patch and P27 as
the26th ordered stage. Existing P2-P26 implementation remains intact. P27
constructs a bounded in-memory code/OPD/import/export fixture, builds the
production HLE table, then runs actual ppu_load_imports and ppu_load_exports.
Both imports first resolve to the INVALID descriptor. Registering known
FNID0x49524e31 backpatches its import slot to the guest OPD; unknown FNID
0x49524e32 stays INVALID. Function linkage is owned by a local container;
the actual production library registry is exercised for registration/unload.

The wrapper refuses preexisting iOSProbe module/library-lock entries, requires
stopped emulator and exact record bounds/metadata, uses production unload to
release its library lock, restores both original import slots and removes
only its own library-lock entry. RAII restores slots/registry on exceptions.
A default ppu_linkage_info fixed object can be retained after initialization,
but no probe function/module/library entry may survive the wrapper. P27 runs
the wrapper twice, checks whole64KiB guest memory and its alias, full HLE page
and its alias, dispatch handlers, read-only flags and unchanged CPU counters.
It rejects a bad record start and releases allocations/table cache on exit.

Validation: patch0022 applies cleanly after0019/0020/0021 on pinned upstream.
A temporary C++20 host harness compiled unchanged production export/import
scanners, PRX/linkage structures and production ppu_register_library_lock
with mocked VM/fixed-object/HLE/logging/lock dependencies. Tests passed for
known backpatch/unknown INVALID, three repeated cycles, malformed/null/stopped
inputs, preservation of preexisting and unrelated registry state, and80
one-shot read exception positions with rollback. Address/undefined behavior
sanitizers passed (host leak scanning disabled due to ptrace restrictions).
This is bounded host integration validation, not full iOS core compilation.

Info.plist bundle39; App.mm26 stages, P27 symbol exported by CoreBridge.
Install ARMSX3_iOS16_INSTALL_THIS_IPA once build39 Actions succeeds, run all26
tests and inspect newest PID. P27 device behavior remains unverified. P27
does NOT execute a guest-to-guest call or use a complete executable loader;
those are next. Firmware/LV2/RSX/game boot are still untested.

## 2026-10-10 — P27 device PASS; build40 / P28 linked guest call
User provided ARMSX3-startup(20261010-170646).log. Latest PID97130 reports
AUTO PASS all26 stages through P27, including production export registration,
known import backpatch, unresolved INVALID import and repeated unload/cleanup.
The @Create image tag remains accidental browser behavior; do not generate images.

Build40 appends patch0023-ios-linked-guest-call.patch and P28 as the27th
ordered diagnostic. P2-P27 code and patches are preserved. A separate bounded
registration wrapper keeps local production import/export linkage and the
production library lock alive while a callback executes the guest test, then
unloads/restores the imports/removes its own lock. Callback rejection or
exception follows the same RAII rollback path; preexisting probe entries
are rejected and unrelated global registry state remains untouched.

P28 constructs an in-memory synthetic code/data fixture. The caller at0x10100
and callee at0x10160 have explicitly declared function blocks (68/12 bytes),
prepared by normal production static-module decoding; this stage does not
use a complete ELF loader/analyser for this new fixture. The caller reads the
actual backpatched import slot, fetches the callee entry/TOC from its OPD,
uses MTCTR/BCTRL, receives42 (35+7), restores caller TOC and stack/LR, stores
the result and returns through the actual production HLE RETURN handler.
Caller/callee TOCs are deliberately distinct. Execution uses the established
bounded fast_call helper,64-dispatch budget and2-second worker deadline.

Checks:20 guest instructions plus1 HLE return dispatch; observed caller/callee
TOCs; external caller CIA/LR/TOC/SP restored; exact64KiB guest memory/alias
including result and frame writes; immutable code/HLE dispatch snapshots;
full read-only HLE page/alias; invalid record-start rejection; two execution
cycles with balanced worker counters and cleanup of allocations/cache/registry.

Validation: patch0023 applies after0019-0022 on pinned source. C++20 host
harness compiles unchanged production import/export/library-lock routines and
the new callback wrapper with mocked VM/fixed-object/HLE/logging/locks. Active
linkage at callback entry, repeated cleanup, callback rejection/exception,
100 injected read failures and earlier regression checks PASS with address/
undefined behavior sanitizers (leak scanning disabled for host ptrace).
Actual upstream opcode generators compiled with a minimal opcode-field shim;
expected key encodings verified. An independent small PPC fixture model
confirms42,20 instructions, caller TOC/SP/LR and exact memory writes. Neither
host test constitutes actual RPCS3 PPU execution or full iOS compilation.

Bundle40; App.mm27 ordered tests; P28 bridge symbol exported. Install
ARMSX3_iOS16_INSTALL_THIS_IPA after Actions succeeds, run all27 tests and
inspect newest PID. P28 device execution remains unverified. Next is actual
executable-loader/module/process integration; firmware/LV2/RSX/game boot
remain untested, and no commercial PS3 game has booted in this diagnostic app.

## 2026-10-10 — P28 device PASS; build41 / P29 production ELF segments
User provided ARMSX3-startup(20261010-173609).log. Latest PID97285 reports
AUTO PASS all27 stages through P28, including two actual linked guest calls
returning42 with separate caller/callee TOCs and complete cleanup.
User explicitly asks to leave workflow completion monitoring to them. Push
and provide the workflow link; do not poll/wait for Actions completion.

Build41 appends patch0024-ios-production-executable-segments.patch and P29
as the28th ordered diagnostic. Existing P2-P28 bridge code is preserved.
The existing ppu_load_exec segment loop is extracted byte-for-byte into
ppu_load_exec_segments, called by the normal executable loader and a bounded
iOS diagnostic wrapper. The normal loader retains its setup, SHA context,
error handler, section processing, HLE/module/process initialization and
thread launch. The wrapper uses a private ppu_module, not the global main
module, and permits exactly two LOAD segments at0x10000/0x20000,64KiB each,
flags5/6 and at most256 file bytes. It rejects occupied pages and malformed
metadata before allocation. RAII removes its pages, segment cache and
segment/index metadata on production failure or exception.

P29 first reserves only the first page so the real second fixed allocation
fails after the first has been copied/registered, verifying rollback. It then
parses a synthetic ELF containing ADDI r3,0,42 and BLR plus an OPD/data payload
and exercises the shared production segment loader twice. Checks include
fixed addresses and module index/metadata, exact code/data pages and aliases,
zero BSS, production hash9ab8513a9fbce423407412a3ec4176485a187e94,
malformed and occupied input rejection without mutation, production static
code preparation, actual bounded PPU worker execution (two guest instructions
plus production HLE RETURN,3 dispatches), restored caller CIA/LR/TOC/SP,
unchanged stack/HLE pages and aliases, immutable dispatch handlers, read-only
HLE flags, balanced worker counters and deallocation. Deadline2seconds,
dispatch budget16. Segment permissions are still those of the production
mapping/registration stage; final executable page protection happens later
in the complete loader and is not performed by this wrapper.

Validation: sequential patch application succeeds after0019-0023; extracted
production loop is byte-for-byte identical. A temporary C++20 host harness
compiles that actual shared loop and wrapper with mocked VM/fixed objects/SHA
dependencies. It verifies fixed allocation/copy/zero BSS, metadata and exact
production hash-input bytes, executable registration, three repeat cycles,
occupied/malformed/state rejection, first/second allocation failures, five
injected exception positions and preservation of unrelated allocation state.
Address/undefined behavior sanitizers PASS (host leak scanning disabled for
ptrace restrictions). Earlier production linkage/exception tests and opcode
fixture tests also PASS. Independent Python SHA1 checks the golden digest.
These are host integration checks, not full iOS compilation or P29 execution.

Bundle41; App.mm28 ordered stages; P29 bridge symbol exported. User will
report Actions completion, then install ARMSX3_iOS16_INSTALL_THIS_IPA, run
all28 diagnostics and send the new startup log. P29 device behavior remains
unverified. This exercises the real executable segment-loader component,
not a complete call to ppu_load_exec: global main-module setup, process
admission, firmware/LV2/RSX/game boot remain untested. No commercial game has
booted. Next integrate executable module/linkage/process preparation within
appropriate bounds before attempting firmware or a game.

## 2026-10-10 — P29 device PASS; build42 / P30 loaded ELF PRX linkage
User provided ARMSX3-startup(20261010-180030).log. Latest PID97507 reports
AUTO PASS all28 stages through P29. The logged vm::falloc failure for the
second segment is intentional, followed by P29 rollback PASS. Both successful
production segment loads and guest execution cycles also passed. User still
handles Actions completion monitoring; do not poll/wait for workflow status.

Build42 appends patch0025-ios-executable-prx-linkage.patch and P30 as the29th
ordered diagnostic. Existing P2-P29 bridge code and patches are preserved.
The normal ppu_load_exec LOOS+2/PRX parameter body is extracted byte-for-byte
into ppu_load_exec_prx_parameters, called by the normal loader and the bounded
diagnostic. Its structure parsing, magic check, exports-before-imports order,
NID stub metadata selection and relocation sorting remain unchanged.

P30 parses a synthetic ELF with three program headers: code LOAD at0x10000
(108 bytes/64KiB), data LOAD at0x20000 (296 bytes/64KiB), and40-byte PRX
control metadata at0x20100, also present in the data LOAD bytes. ELF entry
0x20008 points to the caller OPD (entry0x10000/TOC0x20020); the exported
callee OPD at0x20000 points to0x10060/TOC0x20000. The shared production
segment loop maps/copies/registers the two LOADs and hashes all three headers
as normal; the control header does not create a third allocation. Golden
production hash:5e7882989484d8489b011b0fa5f748df34be50fc.

The bounded parameter wrapper validates exact records/ranges/name/NIDs/OPDs,
requires empty relocation/stub metadata and owns a private linkage object
plus the production iOSProbe library lock. Normal executable metadata loads
the export first and then resolves one import to that guest descriptor while
the unresolved import uses the real INVALID HLE descriptor. A callback runs
the same verified caller/callee instructions from the production-loaded ELF
pages. Twenty guest instructions plus HLE RETURN give21 dispatches/result42,
separate TOCs and restored outer context. The wrapper uses production unload,
restores import words and removes only its library lock, including on callback
failure/throw. Bad magic is passed to the actual production parameter handler
and rejected before linking. Two repeated link/call/unload cycles are checked
against exact code/data/BSS/stack/HLE pages and aliases, dispatch snapshots,
HLE protection, balanced workers and deallocation. Budget64/deadline2seconds.
The caller/callee function blocks are explicitly declared, then passed to the
normal static decoder; this new stage does not run whole-executable analysis.

Validation: patch0025 applies after0019-0024; extracted parameter body remains
byte-for-byte identical. C++20 host harnesses compile actual production
segment/parameter/export/import/library-lock/NID-selection code with mocked
VM/fixed objects/logging/SHA/NID generation. Three-program loading, metadata
versus allocations, copied bytes/zero BSS/hash inputs, repeated loads,
second-allocation rollback and malformed control rejection PASS. Parameter
linking tests confirm active guest descriptor/INVALID import at callback,
bad magic, malformed/preexisting state rejection, callback rejection/throw/
slot mutation and150 injected read-exception rollback paths, preserving
unrelated global state. Address/undefined behavior sanitizers PASS (host leak
scanning disabled due to ptrace restrictions). Actual upstream opcode helpers
plus the independent relocated three-page PPC fixture model confirm42,
separate TOCs,20 guest instructions, caller entry OPD and exact frame/result
writes. These host checks are not full iOS compilation or device execution.

Bundle42; App.mm29 ordered stages; P30 bridge symbol exported. After Actions
succeeds install ARMSX3_iOS16_INSTALL_THIS_IPA, run all29 tests and send latest
log. P30 device behavior remains unverified. This integrates real executable
segment loading and PRX parameter linking using private module/linkage state;
global main-module/process setup, firmware/LV2/RSX/game boot are still untested.
No commercial PS3 game has booted in this diagnostic app.

## Build43 / P31 executable arguments and log export — 2026-10-10

Latest device PID98060 passes P30 and AUTO PASS all29 diagnostics. The
ppu_load_exec Bad magic message is the intentional rejection test, followed
by two successful loaded-ELF PRX linkage/BCTRL/BLR cycles and cleanup.
Do not monitor Actions completion; user continues to report it themselves.

Build43 adds P31 as the30th ordered diagnostic. Patch0026 extracts the normal
ppu_load_exec argv/envp/exitspawn argument packing body byte-for-byte into
ppu_pack_exec_arguments. The normal loader and bounded iOS probe both call
that same helper. The probe preflights fresh retained worker state, the owned
32KiB stack at0x30000, counts/string/data limits, room for the112-byte initial
stack offset plus128-byte guest frame, and readable/writable mapping before
any production writes. Invalid or already prepared input leaves memory,
registers and output pointers unchanged.

P31 reuses P30's real segment loader, PRX parameter linker and linked guest
fixture. Real PPU constructor parameters carry the ELF entry OPD at0x20008,
so entry_func is0x10000/TOC0x20020 and initial SP is0x37f90. Arguments:
argv={probe,15-digit string,16-digit string}, envp={LANG=C,empty string},
17 exitspawn bytes0xa0..0xb0. Independent golden storage is64 pointer bytes
plus96 aligned string bytes plus32 reserved data bytes; argv0x37f40,
envp0x37f60, prepared SP0x37ed0. The actual worker queue executes set_args8
and set_gpr11/12 before a bounded callback checks argc/argv/envp/env count,
thread ID, zero TLS metadata, ELF entry OPD and64KiB malloc page size. Only
after this ABI check does the fixture repurpose r6/r10 for its result/import
slot and call the existing bounded interpreter. Two worker cycles verify42,
21 dispatches, exact packed arguments/frame/data and all aliases, retained
dispatch/HLE protection, balanced thread counts, unload and deallocation.
Emu.argv/envp/data are restored by RAII. This does not enqueue entry_call,
global initialize or sys_initialize_tls, nor admit a full LV2 main process.

User additionally requested fixing the log-file issue: repeated attachments
were listed but unavailable to the conversation, and a pasted excerpt came
from an older run. App.mm now exports a unique plain UTF-8 .txt snapshot of
the latest launch with build metadata and stage results first. Copy results
copies the summary plus the last60 log lines directly for pasting into chat.
Both controls are disabled during testing. Append-only original logging is
preserved. On reopening with an unfinished-stage marker, export selects the
previous diagnostic run and skips intervening idle launches until a new run
starts. Read/export failures show an alert. This addresses app-side export
and provides a fallback; it does not claim to repair ChatGPT/browser upload
handling. LogExport.h is included from the copied core overlay directory.

Validation: patch0026 applies after0019-0025 with unchanged extracted body;
host C++20 harness compiles that actual packer and actual upstream set_args/
set_gpr command cases with mocked VM/thread/configuration. Golden addresses,
big-endian pointers/null termination, whole-page expected writes, empty/max
arguments, 15/16/31/32/127/128-byte boundaries, 0..64-byte data boundaries,
repeated preparation and all preflight rejection paths PASS under address/
undefined-behavior sanitizers (host leak scanning disabled due to ptrace).
P30 actual shared segment/parameter/linker harness regressions PASS, including
150 injected read exceptions. Independent PPC model with actual upstream
opcode encodings confirms the prepared stack's arguments/data survive the
linked guest call and exact frame writes. Log session selection and tail
tests PASS, including repeated idle relaunches and final PASS preservation.
No local iOS SDK/UIKit build; Actions does the actual Xcode compilation.

Bundle43; App.mm30 ordered stages. Install ARMSX3_iOS16_INSTALL_THIS_IPA after
Actions succeeds, run all30 tests, tap Copy results and paste into chat (or
share the new .txt log). P31 and the sharing controls await device validation.
Global process setup, TLS initialization, firmware/LV2/RSX/game boot remain
untested. No commercial PS3 game has booted.


## Build44 / Objective-C ARC log-button compile repair — 2026-10-10

User reported build43 Actions failure. Run38080667626/job114296742293
shows successful patch application, emulator archive compilation and full
ARMSX3Core.dylib link. The only compiler error is App.mm:52: property follows
Cocoa naming convention for returning owned objects: copyButton. Rename the
property and all six references to resultsCopyButton so the implicit getter
is outside the copy method family. The Copy results button/action and .txt
export behavior remain as implemented. Bundle44. Local property-family audit
and plist validation PASS; Xcode/UIKit recompilation still requires Actions.
No P31/core/patch or log selection logic changed. User will report Actions
completion; do not monitor. After success install the IPA and run30 tests.

## Build45 / P32 production TLS memory bootstrap — 2026-10-10

User supplied ARMSX3-startup-20261010-200532-614-98466.txt, exporting build44
PID98466. Latest run passes P31 and AUTO PASS all30 stages. The new .txt log
attachment arrives and is fully readable; its build/result summary and latest
session extraction work. Copy results itself was not separately confirmed.
Keep treating accidental image-generation mentions as the user's browser bug.
Do not monitor Actions after pushing; user reports completion.

P32 integrates the TLS memory portion of sys_initialize_tls from upstream
rpcs3/Emu/Cell/Modules/sys_ppu_thread_.cpp. The full HLE also initializes
process mutexes and globals, so this bounded stage shares the production
memory bootstrap and existing ppu_alloc_tls/ppu_free_tls first. Patch0027
extracts that memory body into ppu_initialize_tls_memory, called by both the
normal initializer and the diagnostic. Copy/zero/allocation/bitmap/r13 code
is retained; one explicit null-pool guard is added before the first TLS write.
The original fallback allocator likewise guards a failed allocation before
writing. Earlier patches0001-0026 do not edit this upstream file.

The diagnostic requires a stopped emulator, the current probe worker's owned
32KiB stack, zero prior r13/TLS globals, exact source0x20080/file9/memory64,
readable iOSProbe-NUL bytes in the production-loaded ELF data, and vacant
pool pages. It owns a256KiB pool allocated at0x50000 with system prefix0x30,
112-byte TLS slots and main r13=0x57060. It dirties two unused slots, calls
the actual allocator to clear/copy/zero them, frees/reuses the second slot,
and checks occupancy before invoking the linked guest callback. An RAII
cleanup restores r13 and all owned TLS statics and destroys/deallocates the
pool even after callback rejection/throw. It rejects preexisting global state
without mutation. vm::temporary_unlock on the actual PPU context performs
the required wait/passive-lock transition before VM allocation and cleanup;
normal guest check_state may reacquire that lock between those operations.

P32 preserves P31's real argument packer, ELF segment loader, PRX parameter
linkage and worker register queue. The main VM block is extended to0x90000
bytes so the pool fits beyond the existing code/data/stack/HLE pages. The
callee's first two instructions become LBZ r3,r13,-0x7000 and ADDI r3,r3,-63,
reading byte i (105) from the production-initialized TLS image to return42.
Its final BLR and caller's BCTRL/stack/LR path stay intact. Twenty guest
instructions plus HLE RETURN still give21 dispatches. Golden ELF hash changes
to425793d502cd9f873d859ae752c1dd2f99d040c3. Entry registers carry the probe
TLS image/file/memory metadata; callback checks those before initialization.
Whole256KiB pool bytes and aliases match three copied9-byte images with
zeroed system/BSS areas, before and after the guest read. Two link/worker/TLS
cycles preserve arguments/frame/data/code/HLE dispatch, free all pool pages,
balance CPU counters, and restore the prior stopped diagnostic state. Wrapper
failure codes and ABI/TLS flags are logged on execution mismatch.

Validation: patch0027 applies to pinned upstream. Extraction matches the
original memory body apart from the explicit null-allocation guard. C++20
host harness compiles actual bootstrap/allocator/free plus the wrapper using
mocked VM/thread/logging. Main r13, copied bytes/zero BSS/system areas, dirty
slots, bitmap free/reuse, fallback allocation/free, repeated cleanup, malformed/
occupied/preexisting rejection, null allocations and25 injected VM access
exceptions PASS under address/undefined-behavior sanitizers (leak scanning
disabled for the host ptrace environment). Mock allocation/free assert the
required wait/unlock transition, including after simulated guest reacquisition.
The independent PPC model uses actual upstream helpers for shared encodings
and verifies exact LBZ0x886d9000/ADDI0x3863ffc1, TLS read/result42, r13 and
arguments/pool preservation,20 instructions and exact frame/result writes.
Production P30 segment/parameter/linker regressions PASS, including150 read
exceptions. Earlier P2-P31 bridge bytes are preserved. No local iOS SDK;
actual Xcode compilation and device P32 behavior remain pending.

Bundle45; App.mm31 ordered stages. After Actions succeeds install the IPA,
run all31 diagnostics and send the .txt log or pasted Copy results. This
stage does not parse a PT_TLS header, invoke the complete TLS HLE or create
its process mutexes. Full process admission, firmware/LV2/RSX/game boot are
still untested; no commercial PS3 game has booted.


## Build46 / P32 compiler repair — 2026-10-10

User reported build45 workflow failure. Run38083168255, job114304091838,
failed compiling Cell/Modules/sys_ppu_thread_.cpp with two exact errors:
line99 Emu undeclared, and line126 try unsupported with exceptions disabled.
The compile command includes -fno-exceptions. Archive/link/IPA stages were
not reached; P32 has not yet run on device.

Patch0027 now includes Emu/System.h explicitly to declare Emu. Its additional
rpcs3/Emu/CMakeLists.txt hunk appends -fexceptions to the source options for
Cell/Modules/sys_ppu_thread_.cpp under ARMSX3_IOS only. It also excludes that
source from precompiled headers, following the existing upstream exception
source convention. This preserves the diagnostic's catch/RAII cleanup and
leaves the global exception setting unchanged. No TLS bootstrap, allocator,
wrapper, bridge, guest fixture, UI or log export behavior changed. Bundle46.

Validation: combined patch0027 applies after the earlier0004/0005 CMake
changes. Explicit header and scoped source option audits PASS. The actual
bootstrap/allocator/free/wrapper host harness is now compiled with both
-fno-exceptions then -fexceptions to check the override and passes ASAN/UBSAN,
including callback failure and25 injected VM exceptions with cleanup. A
negative syntax compile with only -fno-exceptions reproduces the exception
handling error. P32 actual opcodes/independent guest model still reads TLS i
and returns42 with exact preservation checks. Bundle46 plist valid. No local
Xcode SDK; Actions must validate the complete iOS compilation. User reports
completion; do not monitor the new run. After success install the IPA, run
all31 stages and send the .txt log. Firmware/process admission/game boot
remain untested.


## Build47 / P33 executable ELF TLS header — 2026-10-10

User supplied ARMSX3-startup-20261010-204519-482-99182.txt, build46 PID99182.
All31 diagnostics P2-P32 PASS. P32 confirms production TLS memory bootstrap,
main-thread r13, copy/system/BSS zero fill, dirty slot clearing/free/reuse,
guest TLS-relative byte load returning42, exact stack/arguments/aliases and
two cleanup cycles. AUTO PASS completes; no game boot tested. Exported .txt
is fully readable with the summary and complete current launch; Copy results
was not separately confirmed. Accidental image-tool mentions remain browser
bugs. User reports workflow completion; do not monitor Actions after push.

P33 adds real PT_TLS metadata to the production-loaded executable fixture.
Patch0028 extracts the original TLS case's notice, 32-bit overflow guard and
address/file/memory assignment into ppu_read_exec_tls_header. The normal
ppu_load_exec TLS case and diagnostic call that same body unchanged. This
preserves the upstream normal loader semantics. The diagnostic reader uses
local results before publishing outputs and rejects non-TLS/stopped-state/
null/aliased output arguments plus all metadata outside the private tested
image0x20080/file9/memory64. Its extra shape restrictions apply only to the
probe, not the production loader.

A new bounded four-program segment wrapper shares the production segment
loop, verifying the two LOAD pages, existing PRX parameter header, and exact
TLS header with flags4 and9 file bytes matching the LOAD image. It rejects
malformed metadata or inconsistent TLS file bytes before allocating anything,
retains prior allocation/exception rollback, and publishes TLS output values
only after both LOAD segments and their hash succeed. PT_TLS remains metadata
and creates no separate guest allocation. P30/P31/P32 wrappers remain intact.

The fixture now has4 ELF64 program headers: two LOAD, PRX parameters and TLS.
The larger header table ends0x120; code/data file offsets move from0x100/200
to0x200/300 so those headers cannot overwrite code. PRX file offset becomes
0x400, TLS file offset0x380 shares the9 iOSProbe-NUL image bytes from DATA.
Guest addresses/code/loaded296-byte data remain unchanged. TLS metadata read
from that parsed header flows into Program, actual set_args entry registers
r8-r10, and then directly from those worker registers into the production TLS
bootstrap. The existing linked guest LBZ r3,r13,-0x7000/ADDI -63 returns42;
TOCs/arguments/LR/SP/frame/HLE return/decoded cache/aliases and pool cleanup
checks remain. Golden SHA1 nowce2f301a034b0a56fe44a3dac22dd574993cf8c8,
including PT_TLS type7/flags4 in the production loop's hash input.

Device diagnostic first exercises three64-bit overflow fields and malformed
sizes/address/type with sentinel outputs; four invalid TLS program variants
must reject before LOAD allocation/output publication. It then parses/loads
the valid four-header fixture and runs the prior two actual-worker TLS/linked
call cycles. Old P2-P32 bridge prefix is byte-identical to build46 Git blob
014cad81bf4b58d61a37a4208c0c330dc5786765, length371835.

Validation: patch0028 applies after prior PPUModule patches and extracted
header body matches upstream byte-for-byte. Host harness compiles the actual
P33 C++ fixture constructor/opcodes with pinned ELF64 header layouts and
mock endian primitives. Independent binary inspection confirms all4 headers,
no header/code overlap, byte-identical loaded data, correct PRX magic,
shared TLS/LOAD bytes and the golden production SHA1. Actual header helper
and bounded segment wrapper pass ASAN/UBSAN for32-bit boundary values,
overflow fields, malformed/non-mutating rejection, code/data/BSS/hash input,
metadata publication, occupied pages, repeated loading, allocation failure
and injected exception rollback. Actual ELF TLS bytes/parsed metadata feed
production TLS bootstrap/alloc/free in a second sanitizer harness, retaining
its25 injected failures and cleanup tests. Independent PPC model with actual
P33 instruction helpers returns42 with20 guest instructions and exact
memory/frame/register preservation. Existing P30 segment/parameter/link
regressions, including150 injected read errors, pass.32 ordered App exports,
ARC property names and build47 plist audited. No local Xcode SDK; full iOS
compilation/device P33 verification remain pending.

Bundle47,32 stages P2-P33. After Actions succeeds install the IPA, run all32
and send the .txt log. Full TLS HLE/process mutex initialization, complete
process admission, firmware/LV2/RSX/game boot remain untested. No commercial
PS3 game has booted.


## Build48 / P34 executable process parameters and worker — 2026-10-10

User supplied ARMSX3-startup-20261010-211906-075-99663.txt, build47 PID99663.
All32 stages P2-P33 PASS. P33 confirms ELF PT_TLS parsing, overflow/malformed
rejection before allocation, metadata through actual queued registers into
production TLS bootstrap, linked guest TLS read/result42, slot reuse,
arguments/stack/aliases and repeated pool cleanup. .txt export readable.
No commercial game boot. User reports workflow completion; do not monitor.

P34 extracts the real ppu_load_exec process parameter body (LOOS+1,
0x60000001) into ppu_read_exec_process_parameters, used by the normal loader
and diagnostic. It retains SDK assignment, debug/root-sensitive priority
bounds/default fallback, stack/page/PPC fields, bad magic/default behavior
and short declared-size warnings. An explicit bin.size() guard precedes the
32-byte memcpy: truncated file data now returns false before reading beyond
the buffer, and the normal loader returns false before memory mapping. No
other production parameter semantics changed; g_ps3_process_info is read
for priority permissions and never modified by this helper/probe.

Patch0029 includes a bounded process reader and five-program segment wrapper.
The reader accepts only the owned metadata at0x20140,32 file/memory bytes,
flags0,type0x60000001 and stopped emulator. It calls the production body with
normal defaults then requires declared size32, SDK0x00360001, priority1100,
stack0x8000, malloc page0x10000 and PPC flags0 before publishing five output
words. The segment wrapper retains the production LOAD/TLS/PRX path and
preflights process bytes against the DATA program's bytes atoffset320.
Malformed TLS/process metadata and inconsistent shared file bytes reject
before allocating LOAD pages or publishing any output. Allocation/exception
rollback and two-page metadata-only control handling remain in place.

The fixture contains5 ELF64 headers (two LOAD, PRX, TLS, process), ending
0x158 before code fileoffset0x200. DATA at0x300 now contains352 bytes:
previous296 unchanged,24 padding zeros, then32 bytes process parameters at
0x440/guest0x20140. Process version0x00330000, magic0x13bcc5f6. TLS at0x380
still shares the9 iOSProbe-NUL bytes and PRX at0x400 shares the same control
bytes. Golden production hash nowd6f45b20a4ee9f7568d8d3fead077b8545ff9d8d,
including appended process-header type/flags and enlarged DATA bytes.

P34 passes parsed priority1100 and stack0x8000 into the actual named PPU
worker constructor, checks the resulting atomic priority and stack fields,
and derives the prepared stack pointer from parsed stack size. Parsed malloc
page size supplies the queued r12 entry register and is checked inside the
actual worker. Parsed TLS metadata still supplies r8-r10 then production TLS
bootstrap. Linked BCTRL/BLR and r13-relative byte load return42 as before,
with exact full-code/data/stack/TLS/aliases/cache/HLE/cleanup assertions in
two cycles. Process params are preserved in loaded DATA. No full process
admission, TLS HLE process mutex creation or SDK-dependent main VM layout
is invoked here.

Device checks retain P33 overflow/TLS malformed cases and add bad process
magic, declared size, SDK, invalid priority, stack/page/PPC flags and short
file rejection with unchanged output sentinels. Bad magic/short/inconsistent
process-file bytes also reject through the full segment wrapper before
allocation. Old P2-P33 bridge prefix is byte-identical to build47 Git blob
1a0d41a44b453c38c4e18a9677d9de761f64cfc0, length401933.

Validation: patch0029 applies in order after0028; production body matches
upstream apart from the explicit truncated-data guard. Actual P34 C++ fixture
constructor/upstream opcode helpers compiled with pinned ELF64 layouts and
mock endian types; independent inspection verifies all5 headers, code/header
separation, both shared metadata byte ranges, process/PRX magic, identical
first296 DATA bytes and golden SHA1. Actual production process helper and
bounded wrappers pass ASAN/UBSAN for valid fields, both permission states
and priority edges(-513/-512/-1/0/1100/3071/3072), default fallback/bad magic,
short-declared-size warnings, all32 truncated byte counts,18 malformed reader
inputs, inconsistent process/TLS data, unchanged outputs, occupied pages,
repeat LOAD/BSS/hash/code registration, two allocation failure points and
five injected exception rollback paths. Actual P34 ELF TLS bytes feed the
production header reader/TLS bootstrap/allocator/free sanitizer harness,
including25 exception injections and cleanup. Independent PPC model uses
the actual P34 opcodes/enlarged DATA to verify TLS read/result42,20 guest
instructions, exact expected frame/memory changes and preservation. Existing
P33 header/segment regressions PASS.33 ordered exports, ARC property fix,
parsed constructor/entry register flow and build48 plist audited. The real
PPUThread constructor/priority field definitions were checked against pinned
upstream. No local Xcode SDK; full iOS compilation/device P34 remain pending.

Bundle48;33 stages P2-P34. After Actions succeeds install the IPA and run
all33 tests, then send the .txt log. Full process/firmware/LV2/RSX/game boot
remain untested; no commercial PS3 game has booted.

## 2026-10-10 build48 device PASS; build49 P35 guest syscalls

User supplied ARMSX3-startup-20261010-213755-845-99797.txt, PID99797,
build48,5162 lines. All33 stages P2-P34 and final AUTO PASS completed.
P34 confirms the production executable process parser drives real worker
priority1100, stack0x8000, malloc-page r12 and TLS metadata, with actual
linked guest TLS result42 and repeated cleanup. Exported .txt remains readable.
Build48 HEAD was88f2be48d2fd0d23ffd3a6f68f5ba036dfba9ca1,
tree669fe603bb58c43a22dd041c29b701bf4228c0df.

Build49 adds P35, armsx3_core_test_guest_syscalls,34 total tests P2-P35.
The same production-loaded five-header ELF/arguments/process/TLS image
now executes two actual SC(0) instructions through the existing interpreter,
ppu_execute_syscall, production LV2 table, full BIND_FUNC register/return
bindings and unmodified sys_ppu_thread handlers. Linked callee10060 calls
syscall49 (get_stack_information); caller1003c calls syscall46 (get_join_state),
then reads the real initialized TLS byte and returns42. Constructor cycle1
is joinable, cycle2 detached; actual service outputs must reflect each state.
Stack query reports base30000,size8000. DATA offsets40/44 hold stack values,
48 holds successful stack return as u64,56 holds join-state u32,60 holds
successful join return u32; these free bytes end before the PRX record at64.
Caller grows to24 instructions/96bytes, callee remains3 instructions/12bytes;
total code stays108bytes, DATA352bytes.27 guest instructions plus HLE RETURN
give28 bounded dispatches. Full image/stack/TLS/aliases/cache/HLE/CPU counters
and repeated link/TLS/worker cleanup still checked. New production ELF SHA1
d0c52d6772dd173f67886d67dde0cf8a013091d2.

Before the bounded guest call, the worker executes the same loaded SC opcode
with r11=46,r3=0, expecting CELL_EFAULT, and r11=6, expecting CELL_ENOSYS.
Both leave all DATA/aliases unchanged and advance CIA by4. IMPORTANT: the
error_code binding sign-extends its signed32 stored error to64, so EFAULT
must equal u64(s64(s32(CELL_EFAULT))); uns_func_ assigns CellError directly,
so ENOSYS is zero-extended. Full BIND_FUNC retains history for the null error
and both successful services, total3 entries even if history ring size1;
unused service6 bypasses binding/history. Last history verifies syscall46,
loaded CIA1003c,error0 and current_function restoration.

New patch0030-ios-scoped-syscall-statistics.patch extracts the existing
production usage-counter line to ppu_record_syscall_usage. Normal execution
still increments g_fxo->get<named_thread<ppu_syscall_usage>>().stat[code].
That FXO is not initialized by this diagnostic-only startup: fixed_typemap
get() returns potentially uninitialized memory, not a lazily created object.
The new iOS diagnostic-only armsx3_ios_ppu_probe_syscalls_and_call validates
stopped emulator/current real worker/static decoder/owned stack+entry, then
scopes a thread-local1024-counter array around its callback. Only statistics
recording is redirected; SC/table/bindings/services are unchanged. Require
counts46=2,49=1,6=1,all others0. No usage thread or unrelated global process
FXO is created, and normal global statistics are preserved. Nested entry
rejects-2; input-1; counts mismatch-3; negative callback returns propagate.
RAII restores the thread-local pointer on normal, error and exception exits.
Patch also adds iOS-only -fexceptions/PCH skip for Cell/lv2/lv2.cpp so callback
unwind actually runs that restoration under the otherwise -fno-exceptions
core build, following the earlier TLS module source-option pattern.

Host verification: exact C++ P35 fixture constructor/selected upstream opcode
helpers and five-header process/TLS segment loader pass existing sanitizer
checks for malformed input, default/priority boundaries, output sentinels,
allocation/exception rollback, LOAD/BSS/hash and metadata. Independent PPC
model of actual ELF opcodes confirms both SC addresses/numbers/arguments,
joinable/detached BE outputs,27+1 dispatches, TLS result42 and exact whole
memory changes/arguments/TLS/TOC/SP/LR preservation. Actual SC interpreter,
patched production dispatcher, full BIND_FUNC/templates/GPR casts, original
stack/join handlers and scoped statistics wrapper compiled with host VM/type
shims using -fno-exceptions followed by -fexceptions and ASAN/UBSAN: signed
EFAULT,unsigned ENOSYS, BE stack/join results, CIA/history/arguments/function
restore, normal vs scoped counts, invalid opcode/number, LLVM code selection,
nested/invalid wrapper inputs, repeated scopes, mismatch/negative callbacks
and injected exception cleanup all PASS. Actual P35 ELF TLS bytes also pass
production TLS bootstrap/allocator/free sanitizer harness including25 injected
access failures. Patch applies with existing CMake patches; old P2-P34 prefix
unchanged,435414 bytes/Git blob299fe73a97cb502ae90adef84ddd1ee20638ab54.
Build49 plist,34 ordered unique app/bridge exports and resultsCopyButton
ARC repair retained. No local Xcode/iOS SDK: build49 compilation and device
P35 are still unverified until user reports them.

After pushing, DO NOT monitor Actions: user reports workflow completion,
failure or the new device log. On success install build49 and run all34 tests.
Full process admission, full sys_initialize_tls mutex/HLE initialization,
firmware, scheduling/synchronization services, RSX and game boot remain
untested. P35 validates only the two real worker-query services and errors.

## 2026-10-11 build49 device PASS; build50 P36 priority services

User supplied ARMSX3-startup-20261010-220736-453-258.txt, PID258, build49,
5272 lines. All34 diagnostics P2-P35 and final AUTO PASS completed. P35
confirms actual loaded SC dispatch, real stack and joinable/detached queries,
signed EFAULT/unsigned ENOSYS, history/CIA continuation, TLS result42 and
repeated exact image/stack/aliases/cache/worker/TLS/link cleanup. .txt export
remains readable. Build49 HEAD1ff48ff4d835853189a5ddc7cf1cb80fb6407963,
tree88aa10c3910f3253ad126f5badb5bb9a902ffa04.

Build50 adds P36 armsx3_core_test_priority_syscalls,35 tests P2-P36. The same
production five-header ELF/process/arguments/TLS/linkage path now calls
sys_ppu_thread_get_priority via actual loaded guest SC48. Caller copies the
real queued worker ID r7 into r3 before BCTRL; callback supplies r4=DATA+40
as the guest output pointer. Callee10060 sets r11=48, SC at10064 queries self
through the unmodified production handler's scheduler mutex reader lock,
atomic priority read and wait/check_state transition. Returned priority must
match ELF-derived/constructor priority1100. DATA+44 stays0; DATA+48 holds
success0. Caller SC46 still queries joinability, then production TLS read
returns42. Both joinable and detached workers repeat the whole sequence.
Code108/DATA352/layout unchanged,27 guest instructions+HLE RETURN28.
New golden ELF SHA1 is86d1d7ea9c980461ea025add7dfb43bb77f3de41.

Before guest fast_call, decoded loaded SC invokes real syscall47 with self ID
and requests-513,3072,current1100. Both invalid values are rejected in either
privilege mode and must return sign-extended CELL_EINVAL; setting the current
priority must succeed. These invoke actual binding/test_stopped/wait handling
but never change priority or admit the worker into the global scheduler.
Each validates CIA+4, exact history/function restoration, unchanged priority
and full DATA/aliases. Existing null-join EFAULT and unused6 ENOSYS retained.
Total history6 (null1 + set3 + loaded get/join2), excluding unused-service.
Entry ABI still validates queued argv r4 before these calls; final r4 is the
priority output pointer and r7 remains actual worker ID.

Patch0031-ios-worker-priority-syscalls.patch adds a second export to the P35
statistics scope, armsx3_ios_ppu_probe_priority_syscalls_and_call. Shared
private runner validates old stopped/current/static/stack/entry boundaries,
uses the same thread-local RAII counter destination and requires P36 counts
46=2,47=3,48=1,6=1,all others0. The old P35 export still selects exactly its
original counts46=2,49=1,6=1. Production SC interpreter/dispatcher/table/
bindings/services and normal global counter path are unchanged by0031.
Existing0030 iOS lv2.cpp -fexceptions/PCH skip retained for exception cleanup.

Host validation:0031 applies after0030 to pinned lv2.cpp. Actual production
set/get priority handlers, complete BIND_FUNC templates/GPR casts, SC and
patched dispatcher pass ASAN/UBSAN with -fno-exceptions then-fexceptions.
Host scheduler mutex/atomic/check_state/IDM primitives are shims: tests verify
handler selection, signed argument/error ABI, invalid boundaries in both
privilege modes, no-change self success without set_priority invocation,
BE self-query output, history/arguments/CIA/current_function restoration and
read-lock/check_state route. P35 and P36 counter policies, nested/cross-policy
mismatch, negative/exception callbacks and repeated scope/global-statistics
restoration all pass. Actual C++ P36 ELF constructor/opcodes and production
process/TLS loader sanitizer checks validate five headers, hash, malformed/
default/priority cases, exact metadata publication and allocation/exception
rollback. Independent PPC model confirms actual SC48 self ID+r4 pointer,
SC46 join query, both join states, priority1100,27+1 dispatches, TLS result42
and exact full-memory/frame/arguments/TLS/TOC/SP/LR preservation. Actual P36
ELF TLS bytes pass production TLS bootstrap/allocator/free sanitizer tests,
including25 injected access exceptions. Real CPUThread is_stopped/test_stopped
and check_state paths were inspected against pinned upstream. No local iOS
SDK: actual scheduler lock/VM/thread-state behavior is left to device P36.

Old P2-P35 bridge prefix unchanged,474122 bytes/Git blob
e892214cd96c50042d269303663e3179c6b552eb.35 ordered app/bridge exports,
build50 plist and resultsCopyButton ARC repair retained. Build50 Actions and
device P36 remain unverified. Do not monitor Actions after push; user reports
completion/failure. On success install IPA and run all35 diagnostics.
Actual scheduler admission/priority changes, full TLS mutex initialization,
firmware, RSX and game boot remain untested.

## 2026-10-10 — build50 device PASS; build51 adds P37 priority mutation

Latest uploaded device log ARMSX3-startup-20261010-222702-028-374.txt identifies
build50/PID374, 5386 lines. All35 diagnostics P2-P36 PASS, ending AUTO PASS
P36 and AUTO PASS all diagnostic stages. This confirms real worker self
priority query through production LV2 locking/wait/check_state, invalid
-513/3072 signed CELL_EINVAL and same-priority success on the A15 phone.
The exported .txt was readable. Game boot remains untested.

Baseline main before this change is6278a5c6dabe70b5f1ce2b282ccbe6dade65554b,
tree1d14355ff41b5492e0e43eccd80f82b24b9db6f3. Build51 adds diagnostic P37,
armsx3_core_test_priority_change, making36 tests P2-P37. It uses exactly the
P36 ELF fixture: five program headers,27 words/108 code bytes,352 DATA bytes,
golden SHA1 86d1d7ea9c980461ea025add7dfb43bb77f3de41. Same production ELF
process/TLS/argument/linkage path, retained real worker and bounded guest.

P37 retains invalid/null/unused/no-change service checks. Then decoded loaded
SC47 changes the current real worker's priority1100 to1200 via unchanged
production sys_ppu_thread_set_priority -> lv2_obj::set_priority -> awake ->
awake_unlocked. The worker is absent from the scheduler's running queue:
the actual production unqueue-miss branch updates its atomic priority/order
and returns before admission. For1100->1200 it increments the global order
tag and writes the negative complemented tag. Loaded guest callee SC48
queries1200 into DATA+40, then caller SC46 reads joinability and TLS returns42.
After the bounded call, SC47 restores1100, incrementing/writing the positive
order tag, and SC48 queries1100 again. Both joinable and detached workers
repeat. Each mutation checks actual priority/order/global tag, service return,
history/CIA/function state; no DATA mutation occurs on the first set. Post-call
SC operations preserve the guest's r3=42,r4,r11,CIA. Final expected DATA/stack/
TLS/code/aliases stay exactly the P36 expected image.

Patch0032-ios-worker-priority-change.patch keeps production services, SC,
bindings, dispatcher, awake/awake_unlocked/schedule_all/notify_all untouched.
The shared statistics runner selects P37 counts46=2,47=5,48=2,6=1,others0;
P35/P36 policies stay unchanged. Nine BIND history events (unused6 bypasses
history), ten SC invocations, still27 guest instructions+HLE RETURN28.
New iOS-only export armsx3_ios_ppu_probe_priority_change_and_call delegates
to a lv2_obj member so it can inspect private scheduler state. The method
declaration is Apple-guarded in sys_sync.h; definition/export are iOS-guarded.
It requires stopped emulator/current worker/static decoder/stack30000:8000/
entry10000/priority1100 and rejects nesting or any active/pending scheduler,
timeout/sleep/awake queues, notifications/barrier/yield frequency, reservation
notification or worker queue link. It saves the entire atomic priority union
and global order tag under g_mutex, rejects signed50-bit order overflow, runs
the bounded callback, validates exactly two order transitions and restored
priority1100 with empty scheduler state, and RAII restores the original union
and tag on success, negative callback, count mismatch or exception. It never
calls scheduler cleanup or adds/removes global workers. Existing0030 iOS
lv2.cpp exception/PCH override remains needed.

Host validation passes with g++ C++20 -Wall -Wextra -Werror, ASAN/UBSAN and
-fno-exceptions then-fexceptions. Patch0032 applies after0030/0031 to pinned
lv2.cpp/sys_sync.h. Harness compiles unchanged full set/get handlers, full
BIND_FUNC/GPR casts/SC/dispatcher, actual inline set_priority and full awake,
plus exact production default priority/unqueue branch. Scheduler admission/
yield paths are excluded; atomic/mutex/VM/schedule_all are host shims. It
checks change1200/query/restore1100, both signed order directions, ten counts/
nine events, repeated joinable/detached scopes, unchanged normal stats,
P35/P36 policies, all isolation/overflow/nesting guards, and rollback on
negative/exception/count/final-state failures. The actual new CoreBridge
performSyscalls callback is also compiled/executed for both join states;
the bounded guest function is a shim there. Independent PPC decoding of the
actual compiled ELF opcodes confirms the temporary1200 query, final1100
memory restoration, TLS42,27+1 dispatches and exact full-memory/register/
TOC/SP/LR preservation. Production process/TLS loader sanitizer harnesses
check actual constructor/hash/metadata/malformed shapes/rollback. Actual
P37 ELF TLS bytes pass production bootstrap/allocator/free and25 injected
access exceptions. No local Xcode/iOS SDK: real P37 scheduler/VM transition
still needs Actions and phone verification.

P2-P36 CoreBridge prefix remains byte-identical515352 bytes, Git blob
9f7a1d94c52905297144eb5ea4cc373ed18acbe7. App36 ordered unique symbols,
Info build51, existing log export and resultsCopyButton ARC repair retained.
Do not monitor Actions after pushing; user reports completion/failure.
On success install ARMSX3_iOS16_INSTALL_THIS_IPA, run all36 diagnostics and
share the new .txt. Scheduler admission/context switching, full TLS HLE,
firmware, RSX and game boot remain untested.

## 2026-10-11 — build51 device PASS; build52 adds P38 scheduler queue

Latest device log ARMSX3-startup-20261010-225321-729-560.txt identifies build51,
PID560,5500 lines. All36 diagnostics P2-P37 PASS; final P37 confirms actual
LV2 self-priority mutation1100->1200, loaded guest self-query1200, restoration
1100, signed order tags/global counter cleanup and TLS42 on the A15 phone.
The expected EFAULT/EINVAL log lines are deliberate negative diagnostic
cases. Exported .txt remains readable. Game boot remains untested.

Baseline main864ae3263e7fec3ab6d7db00931415d3c3839b95,
tree03f0c2ebf609447146d393040c2d1ebb514c16dc. Build52 appends P38
armsx3_core_test_scheduler_queue,37 tests P2-P38. Same unchanged five-header
ELF/process/arguments/TLS/PRX fixture and golden SHA1
86d1d7ea9c980461ea025add7dfb43bb77f3de41;27 words/108 code bytes,352 DATA
bytes,27 guest instructions+HLE RETURN28. Old P2-P37 prefix is561088 bytes,
Git blob170bcd05ffee3260045362c32dc7376838fae925, verified against main.

Patch0033-ios-single-worker-scheduler-queue.patch adds an iOS-only bounded
lv2_obj::ios_probe_scheduler_queue_and_call member and C export
armsx3_ios_ppu_probe_scheduler_queue_and_call. Before entry it requires
stopped/current/static/fresh real worker, stack30000:8000/entry10000/prio1100,
at least one configured PPU hardware slot, empty running/pending/timeout/
sleep/awake/notification queues, scheduler not ready, no yield frequency,
reservation notifications, suspend acknowledgement, hardware delay, start
time, cancelled sleep or worker suspend flag. Production ppu_state must
report STOP. Nested syscall statistics scopes are rejected.

The wrapper calls public production lv2_obj::awake(context) with its default
enqueue command. Unchanged awake_unlocked admits this single real worker
into g_ppu. It must be the sole node at position0, production ppu_state must
report ONPROC/0 and count_non_sleeping_threads must report one. The wrapper
does not make the scheduler ready or resume any other worker. The same ten
P37 SC service calls execute via the retained worker and existing bounded
guest interpreter: invalid/no-change checks, real SC47 priority1100->1200,
loaded callee SC48 query1200, caller SC46 join-state query and TLS return42,
then SC47 restore1100 and SC48 confirm1100. Both join states repeat.

On an admitted worker the production priority branch successfully unqueues
it, sets priority without modifying its order, and reinserts it into the real
running queue. P38 therefore requires unchanged original order and global
priority tag at both changes, unlike P37's unregistered-worker tag increments.
CoreBridge validates actual get_running_ppu(0), null next link and ONPROC/0
after admission and each priority change. End-state wrapper checks require
the full original priority union, unchanged global tag, single-node queue and
all isolation invariants. RAII invokes actual production unqueue under
g_mutex and restores the original priority union/tag on every return and
exception. After wrapper return CoreBridge requires no running worker/link,
production STOP status and restored priority/tag. All guest DATA/code/stack/
TLS/aliases/caches/counters match P37; post-call service operations preserve
the guest return/continuation. Counts46=2,47=5,48=2,6=1,others0 and nine BIND
history records remain the P37 policy. P35/P36/P37 and normal statistics
paths are unchanged. Production awake/awake_unlocked/schedule_all/service/
state-reporting code is untouched; only the guarded diagnostic wrapper and
Apple-guarded member declaration are added. Prior0030 iOS exception override
and PCH skip remain necessary for lv2.cpp RAII callbacks.

Host validation passes C++20 -Wall -Wextra -Werror, ASAN/UBSAN with
-fno-exceptions then-fexceptions. Patch0033 applies after0030/0031/0032 to
pinned source. Harness compiles unchanged complete production awake,
awake_unlocked and schedule_all bodies, actual inline set_priority/unqueue,
count_non_sleeping_threads/ppu_state/get_running_ppu, production priority/
join handlers, full BIND_FUNC/GPR casts/SC/dispatcher and actual new
CoreBridge performSyscalls callback. Host primitives for VM/atomic/mutex/
CPU state and bounded guest execution are shims; notify_all's relevant
non-suspended PPU prefix is retained. Full scheduler bodies are checked
byte-identical against pinned upstream. Tests exercise actual admission,
priority removal/reinsertion, queue/status preservation, one and two hardware
slots, both join states, exact raw priority/order/global counters/normal stats,
counts/history and cleanup. Negative/exception/count/final-state failures,
nested scope,14 isolation guards, zero hardware slots/null input rejection
pass. P35/P36/P37 scopes still pass against the new scheduler harness.
Independent PPC model of compiled actual P38 fixture checks temporary1200
query, final1100 memory, TLS42, full image/frame/register/TOC/SP/LR bytes.
Production process/TLS loader sanitizer checks validate actual constructor/
golden hash/metadata/malformed shapes/rollback. Production TLS bootstrap/
allocator/free checks pass with actual P38 ELF TLS bytes and25 injected access
exceptions. No local iOS/Xcode SDK: real P38 queue behavior awaits Actions
and device verification.

App has37 ordered unique exports; Info build52; log export/resultsCopyButton
ARC repair retained. Do not observe Actions after push: user reports build
completion/failure. Install ARMSX3_iOS16_INSTALL_THIS_IPA after success, run
all37 diagnostics and share .txt. This is bounded single-worker admission,
not scheduler start or multiworker context switching. Scheduler start,
multiple workers/context switching, full TLS HLE, firmware, RSX and actual
game boot remain untested.

## 2026-10-11 — build52 P38 rejection/abort; build53 timestamp/unwind fix

User Archive(5).zip contains ARMSX3-startup-20261010-231627-519-732.txt
and ARMSX3CoreLoadTest-2026-10-11-011558.ips. Log identifies build52 and
previous unfinished P38/PID722; P2-P37 all PASS again. P38 validates ELF,
PRX parameters and starts the retained worker, then aborts before any of its
deliberate syscall errors. Crash is SIGABRT/EXC_CRASH on user-initiated worker
queue, __cxa_throw -> failed_throw -> terminate -> report_fatal_error, from
armsx3_core_test_scheduler_queue's executeLinked callback through
armsx3_ios_ppu_link_probe_image_and_call. Actual P38 queue path did not pass.

Pinned production PPUThread.cpp constructor explicitly initializes
start_time(get_guest_system_time()) at line3175. The P38 wrapper incorrectly
required !context->start_time, so a correctly constructed worker is rejected
with -4 before admission. Prior host PPU mock wrongly defaulted start_time
to0; its mismatch caused the missed regression. This is a diagnostic guard
bug, not evidence that production scheduler admission itself is broken.
The rejection makes the outer callback throw its execution-mismatch error.
PPUModule.cpp lacked the source exception override used for other diagnostic
callback owners, consistent with failed_throw crossing this frame. The error
text was not logged before throwing, so the device log only shows fatal
termination. Actual iOS unwind fix still needs device verification.

Build53 fixes P38 rather than adding P39;37 diagnostics P2-P38 remain.
New0034-ios-scheduler-timestamp-and-linkage-unwind.patch follows0033.
The scope captures and requires preservation of the existing start_time,
accepting production nonzero timestamps, and restores it alongside original
priority/order tag and queue removal on all exits. All other stopped/single-
worker/isolation/count/history checks remain. iOS-only PPUModule.cpp now
gets APPEND COMPILE_OPTIONS -fexceptions and SKIP_PRECOMPILE_HEADERS ON,
so executable linkage callbacks can unwind their actual import/library-lock
cleanup and reach CoreBridge's error handler. Prior lv2/TLS exception
overrides remain. Production scheduler/services/constructor are unchanged.
P38 CoreBridge logs worker ID/priority/start timestamp/hardware slots before
scope entry and the wrapper return afterward, validates timestamp preservation
and logs the full post-worker mismatch before throwing. Log export unchanged.

Regression harness now models the actual constructor's nonzero timestamp;
the original P38 guard reproducibly returns -4 for nonzero values, while
the revised guard admits the worker and passes the actual CoreBridge syscall
callback through unchanged full production awake/awake_unlocked/schedule_all/
unqueue/count/ppu_state/get_running_ppu bodies. Zero,1,0x12345678 and large
64-bit timestamps are accepted and preserved. Mutation of the timestamp is
rejected at end-state and restored; negative/exception paths also restore it.
Single/two hardware slots and both join states, all prior queue/count/state/
normal-stat guards and P35-P37 policies still pass. ASAN/UBSAN,C++20,Wall/
Wextra/Werror with -fno-exceptions then-fexceptions. Atomic/mutex/VM/CPU
primitives and bounded guest execution remain host shims. Production ELF
PRX parameter/export/import wrapper tests using the same flag ordering pass
callback failures and150 injected exception positions, preserving imports,
library locks, relocs and unrelated state. Per-source CMake override/PCH
exclusion verified;0034 applies to staged lv2.cpp and CMake after all earlier
relevant patches. No local iOS/Xcode SDK: build53 and corrected P38 remain
pending Actions/phone confirmation.

Baseline main b0e414f7b830f63178ead61ed7e1dde30103d795,
tree fbfc9bd1febc4aef575b0c46d546df48e8dfbcf4. P2-P37 CoreBridge prefix
561088 bytes stays byte-identical, Git blob170bcd05ffee3260045362c32dc7376838fae925.
App order/count/symbols unchanged, Info build53, new patch and handoff update.
Do not monitor Actions after pushing. User reports completion/failure, then
installs ARMSX3_iOS16_INSTALL_THIS_IPA and repeats all37 diagnostics. Request
new .txt (plus .ips if another crash). P38 queue admission, scheduler start,
multiworker context switching, full TLS HLE, firmware, RSX and game boot are
still not device-verified.

## 2026-10-11 — build53 P38 cleanup mismatch; build54 classification fix

New upload ARMSX3-startup-20261010-235445-370-774.txt identifies build53,
PID774. P2-P37 all PASS. P38 no longer crashes: production scheduler scope
admits the worker (priority1100, start949320861886, two hardware slots), executes
the priority change/query/restore and linked guest calls, and returns28.
The outer mismatch is wrapper -6, worker TLS1, entry ABI1, TLS memory0,
syscalls1. This locates the remaining exception after scheduler scope return,
before the TLS-memory postcheck completes. Build53's timestamp guard and
linkage exception-unwinding fixes are supported by this device result.

Pinned production ppu_thread::fast_call sets interrupt_thread_executing=true
and deliberately does not restore it. After the scoped worker is unqueued,
unchanged lv2_obj::ppu_state therefore returns SLEEP, not STOP. CoreBridge's
post-scope STOP assertion was wrong and threw through the TLS wrapper, which
returns -6. The previous host bounded-call shim omitted this production flag
side effect. This is a diagnostic expectation error; no production scheduler
or fast_call changes are needed.

Build54 changes only the P38 post-scope diagnostic: expect SLEEP when the
production flag is true and STOP for a worker rejected before fast_call.
Require position0 and retain priority/raw-order, global-tag, timestamp and
empty-queue checks. Log actual/expected state, position and fast_call flag,
and log the precise cleanup error before throwing. Final result28, guest42,
TLS memory/aliases, syscall history/count and other existing checks remain.
No new P39, no new patch, no App.mm or log-export changes; build number54.

Focused host regression compiles the complete unchanged pinned fast_call,
ppu_state and get_running_ppu bodies with host CPU/atomic/lock shims, plus
the exact old and new CoreBridge cleanup blocks. The old block throws after
actual fast_call and queue removal; the new block passes. Both join states,
one/two hardware slots, repeated calls, pre-call STOP, and rejection of
queued workers, dangling next links, priority/tag/timestamp mutations,
IDLE/zombie/deleted states pass. Full fast_call continuation/TOC/LR/function/
log-prefix and ret-flag restoration are also checked on normal return.
An injected exec_task exception confirms its flag remains true; this test
does not assert production fast_call restores continuation after exceptions.
G++ C++20 Wall/Wextra/Werror with ASAN/UBSAN, -fno-exceptions then-fexceptions;
ASAN leak detection disabled because this tool environment cannot access
/proc child tasks (memory/UB instrumentation remains enabled).

P2-P37 prefix remains561088bytes, Git blob170bcd05ffee3260045362c32dc7376838fae925.
Baseline main3a52d23b37cc4bd47841c22654651db2cabc3094,
tree998b6ed48e39f7fa872afb162c9f18f30a72830a. No local Xcode/iOS SDK;
build54 is pending Actions and device confirmation. Do not monitor Actions;
user reports workflow completion/failure. Install ARMSX3_iOS16_INSTALL_THIS_IPA,
run all37 diagnostics and send the new .txt (plus .ips if another crash).
P38 complete PASS, multiworker scheduling, firmware, RSX and game boot remain
unverified. The diagnostic-only queue remains isolated with normal scheduler
stopped throughout; passing it will not imply full process/game startup.

## 2026-10-11 — build54 all37 PASS; build55 P39 two-worker queue

Upload ARMSX3-startup-20261011-002337-395-834.txt identifies build54,
PID834. P2-P38 all PASS, AUTO PASS all diagnostic stages completed.
Both P38 iterations return28 and log cleanup status3/expected3/position0/
fast_call1. Device confirms production single-worker admission, admitted
priority change/query/restore, linked guest return42, both join states and
complete restoration. Expected null-pointer EFAULT and invalid-priority
EINVAL messages are deliberate rejection checks. Build54 cleanup fix is
device-verified. Full game boot remains untested.

Build55 adds P39 "Two-worker scheduler priority ordering" after P38 (38 total
diagnostics P2-P39). New0035-ios-two-worker-scheduler-queue.patch follows0034,
adding an iOS-only lv2_obj member/export and declaration. Production awake,
awake_unlocked, schedule_all, service handlers, SC bindings and fast_call are
unchanged. It requires the stopped/empty scheduler, exactly two configured
hardware slots, current worker stack30000 and retained peer stack90000,
both size8000 and entry10000, distinct IDs, priorities1100/1150, no pending/
timed/yield/notify work or suspend/ack/hw-sleep/cancel state, initial STOP.
Capture both constructor timestamps (nonzero allowed), raw priority unions
and global order counter. Call actual public awake on worker then peer;
verify ordered links, ONPROC0/1 and onproc_count2 with no runnable excess.
Run the existing ten SC calls with policy2 counters. Final checks require
both original priorities/raw orders, original timestamps/counter and initial
queue order. RAII uses actual unqueue on both, restoring priorities/times/
counter on normal, negative, bad-count and throwing callback exits.

P39 CoreBridge is appended as a distinct stage; P2-P38 bytes stay unchanged.
Same production-loaded five-header ELF and27 guest opcodes/golden hash as
device-passed P38. Separate fixed peer stack90000..a0000 does not overlap
TLS pool50000..90000; main reserve10000+90000 covers it. Construct a real
named_thread<ppu_thread> with launch_retainer, IDbase+1 (production id_step1),
priority1150, detached, entry OPD matching worker, no guest commands. Clear
its CPU construction flags for stopped-scheduler classification, never start
it during queue exercise. Program stores the peer pointer for bounded
callback lifetime. With two slots occupied, SC47 worker1100->1200 must
move worker behind peer1150 (peerONPROC0/workerONPROC1); SC48 in linked guest
reads1200. SC47 restore1100 moves worker ahead again (worker0/peer1), SC48
confirms1100. Preserve peer raw priority, registers, CIA/LR/current function,
timestamp, no interrupt execution/history, STOP after removal; verify full
peer stack and all prior code/data/main stack/TLS/HLE aliases/cache cleanup.
Log the three queue transitions, wrapper result, post-fast_call SLEEP and
unexecuted peer STOP. Repeat main joinable and detached variants.

Important peer lifecycle detail: CPU constructor increments created counter;
CPU destructor is empty and only cpu_thread::operator() cleanup increments
deleted. RetainedPeerCleanup therefore sets exit, launches the peer solely
for the CPU cleanup wrapper, and joins it after queue exercise. Production
while(!(state&exit)...) skips cpu_task entirely; no peer guest code runs.
This RAII also retires peer on callback exceptions. Four CPU constructors/
cleanup exits across the two variants; live count must return to baseline.

Host test compiles unchanged full production awake/awake_unlocked/schedule_all/
unqueue/set_priority/count/ppu_state/get_running_ppu/fast_call bodies and
actual join/set/get-priority service handlers, scoped syscall policy runner,
P37/P38 scopes and new P39 scope plus exact CoreBridge callWithTLS callback.
Both join variants pass ten SC count/nine history checks, queue crossing/
restoration, TLS return42 and peer preservation. Negative/throwing callbacks,
bad counts, both timestamp mutations, peer priority/global tag/wrong final
order mutations restore queue/priorities/timestamps/counter. Nested probe,
one-slot configuration, same ID, wrong peer stack/priority, peer stop/suspend/
executing flag, active scheduler/pending state reject before admission.
Production FIFO equal-priority admission and previous P37/P38 scopes pass.
SC transport/history, guest instruction execution, VM aliases, atomics and
locks are host shims; device still must validate full actual P39 execution.
Separate threaded host regression compiles production CPU constructor/
operator/destructor and exact RetainedPeerCleanup struct: normal/exception
paths skip cpu_task and balance CPU created/deleted/live counters. Named
thread launch/join primitives are host shims. G++ C++20 Wall/Wextra/Werror,
ASAN/UBSAN; leak detection off for tool /proc restriction. Previous P38 exact
old/new cleanup regression passes. Patch0035 applies/reverses cleanly after
0034; P39 ELF/opcode builder exactly matches P38; App symbols unique/ordered.

Baseline main259f3bb81b46b1e115bd734bdfa704d5306f5520,
treedf95c00681ef3349932374c9d02aa9944c3a3b0e. P2-P38 prefix610061bytes,
Git blobc59f657328cc9785b7f4073e628333210016034f. Info build55; only Bridge,
App stage entry, Info, new0035 and handoff change. Existing log export intact.
No local iOS/Xcode SDK; build55/P39 pending Actions/device. Do not monitor
Actions after push; user reports workflow result. Install artifact
ARMSX3_iOS16_INSTALL_THIS_IPA, rerun all38, send new.txt plus.ips if crash.
Peer guest execution, scheduler start/context switching, full TLS HLE,
global process/firmware/RSX/game boot remain untested. Passing P39 validates
two-node ordering with scheduler stopped, not runnable multiworker execution.

2026-10-11: build55 DEVICE PASS; build56 P40 guest yield prepared
----------------------------------------------------------------
Uploaded ARMSX3-startup-20261011-005358-046-998.txt, PID998, shows all38
P2-P39 stages PASS. Both P39 repeats confirm priority1100->1200 moves
worker behind peer1150, restore1100 moves it ahead, scope result28,
main SLEEP3 and unexecuted peer STOP, repeated unload/cleanup and AUTO PASS.

Build56 appends P40 "Guest yield and FIFO scheduler ordering". Preserve
P2-P39 byte-for-byte (664686-byte prefix, blob
a3093443df97a3452b232e95ed6d31e32d747028). New patch0036 adds only an iOS
diagnostic two-worker scope/export and syscall-count policy3. Production
scheduler, yield service, syscall bindings and fast_call remain unchanged.
Two stopped workers, equal priority1100, two hardware slots. Real public
awake admits main0/peer1. Guest SC43 rotates main behind peer; another SC43
at the tail preserves peer0/main1. Both remain ONPROC, so production yield
returns CELL_CANCEL=1 without a context switch. Both timestamps, raw priority
unions and global ordering counter must remain unchanged. Actual unqueue
and RAII restore all captured scheduler state on success/failure/exception.
Keep P39's exit-only named-peer cleanup and all ELF/TLS/stack/TOC/HLE checks;
peer never executes guest code. Repeat main joinable and detached variants.

Loaded fixture has34 instructions/136 code bytes, callee40 bytes; execution
expects35 steps including HLE return. Callee SC43 twice stores results1/1
at DATA+24/+28, restores worker ID from r7, then SC48 queries priority1100.
Caller restores TOC, joins, reads TLS and returns42. Guest end10088.
Module SHA1 0998aeffb1a30e1c3a947c500c5ee85179f94b2c, independently derived
from pinned production loader's program-header hash records and fixture.
Policies0/1/2 retain old counts. Policy3 requires SC43=2,46=2,47=5,48=2,6=1,
other=0:12 calls/11 BIND history entries (unused6 has none). Enable actual
ppu_call_history bool before constructing worker and restore afterward;
assert first/tail yield histories have error1 and CIAs begin+100/+112.
Noop SC47 before/after yields must preserve FIFO; query confirms1100.

Host P40 regression compiles full production yield/awake/awake_unlocked/
schedule_all/unqueue/set_priority/count/ppu_state/get_running_ppu/fast_call,
actual yield/join/set/get service handlers, all diagnostic policies/scopes
and exact P40 CoreBridge callback. Independent bounded PPC interpreter
decodes actual fixture instructions, drives service handlers and checks
35 steps, TLS42, histories,1/1 outputs and FIFO changes. Both variants,
negative/throwing/bad-count/mutated-state rollback, nested/invalid guards,
direct production FIFO/yield and policies0/1/2/3 pass. SC transport/history,
VM aliases, atomics, locks and instruction executor are host substitutes;
full production guest interpreter and iOS ABI still need device validation.
P39 callback/priority/rollback regression, exact peer lifecycle normal/
exception regression and P38 fast_call cleanup regression also pass.
G++ C++20 Wall/Wextra/Werror with ASAN/UBSAN, leak detection off due tool
/proc restriction. Patch0036 applies/reverses after0035; UI has39 ordered,
unique stages P2-P40. No local Xcode SDK. Info build56; only Bridge/App/Info,
patch0036 and handoff changed. Log export and workflow are unchanged.

Baseline main6880c20b68a1eebca91f91b84e7e2db706f8e0d3,
tree73a4dd9ad6327119c275a1052862815b5e2b9934. Build56/P40 pending Actions
and phone validation. Do not monitor Actions after push: user reports result.
Install ARMSX3_iOS16_INSTALL_THIS_IPA, run all39, send .txt/.ips if crash.
Scheduler start, >2 runnable workers/suspend handoff, peer guest execution,
real context switching, full TLS HLE, firmware/RSX/process/game boot untested.

2026-10-11: build56 DEVICE FAIL at P40 loader guard; build57 correction
------------------------------------------------------------------
Uploaded ARMSX3-startup-20261011-012234-387-1207.txt, PID1207. All38 P2-P39
pass again. P40 fails "malformed TLS program allocated memory or changed
outputs" before successful segment loading or any guest yield execution.
Root cause is diagnostic fixture size mismatch: P40 grew code from108 to136
bytes, but process-image wrapper added in0029 still caps/requires108.
Thus first malformed TLS case returns-2 at code-size gate, expected-5.
No evidence of actual allocation/output mutation: the combined assertion's
message covers those checks too. Host P40 callback test had bypassed loader;
its passing result did not cover the outdated integration boundary.

New0037-ios-yield-fixture-loader-size.patch changes ONLY iOS diagnostic
armsx3_ios_ppu_load_probe_process_image_segments: max136 and exact accepted
code sizes108 OR136. Data352, both private page locations/permissions/sizes,
PRX/TLS/process metadata gates and production loader/rollback unchanged.
Older segment/TLS wrappers still require their original108/296 fixtures.
No Bridge/App/LV2/workflow/log-export changes. Info increments56->57.

Reconstructed pinned PPUModule by applying all ten touching module patches
0019-0026,0028,0029 in order. New0037 applies/reverses byte-exactly. Host
regression compiles the actual old/new full process-image wrapper. Old136
fixture reproduces-2 instead of-5; fixed108 and136 each pass four malformed
TLS and three malformed process cases with no allocations/unchanged outputs,
successful metadata publication, loader failure and bad loaded-size rollback.
Reject0/104/112/132/140 code lengths, mismatched code bin and data351 before
allocation. This regression uses host types, VM/sha/loader/parser substitutes;
tests actual wrapper control flow, bounds, publication and RAII, not full
production parser or segment-loader runtime. G++ C++20 Werror ASAN/UBSAN.
Existing P40 exact callback/production scheduler/service regression and golden
fixture hash0998aeffb1a30e1c3a947c500c5ee85179f94b2c remain valid.
Persist standalone regression as armsx3-ios16/tests/test_p40_loader.py;
accept module source arguments (before0037 then after0037) for future checks.

Baseline main04b676c4cbed5736cdda681d03995e36e46c5ad2,
tree1e93a561f69171ea04fc8584f70c64998460f842. Build57 pending Xcode/phone.
Do not advance to P41 until P40 device passes. Do not monitor Actions.
User installs ARMSX3_iOS16_INSTALL_THIS_IPA, reruns all39, sends log.

2026-10-11: build57 DEVICE PASS; build58 P41 guest timing integration
------------------------------------------------------------------
Uploaded ARMSX3-startup-20261011-014349-556-1300.txt, PID1300, build57.
All39 P2-P40 PASS. Both P40 repeats show FIFO worker0/peer1 -> peer0/worker1,
tail yield preserves order, both CELL_CANCEL1 without context switch,
scope result35, main SLEEP3/unexecuted peer STOP, exact aliases and cleanup.
Final AUTO PASS. The0037 loader fix is device-confirmed.

Build58 appends P41 "Guest current time and timebase frequency". Earlier
P35 already covered stack-information SC49; do not duplicate that milestone.
P2-P40 prefix722084 bytes remains byte-identical, Git blob
8f2e0fe168f70775be7aca0831094a54033c312f. Clone device-passed P40 bounded
ELF/TLS/two-node yield fixture, extend loaded callee with real SC145 current
time and SC147 timebase frequency. Pinned production sys_time.cpp and syscall
table inspected: seconds/nanoseconds are signed64 outputs, frequency80MHz.
Current-time service checks seconds pointer before any write; with valid
seconds/null nanoseconds it publishes seconds then returns CELL_EFAULT.
P41 dispatches both error cases through loaded SC binding, checks signed
error/history/CIA and exact DATA bytes; verifies partial seconds write within
host epoch-second bracket, then restores that private scratch word.

Actual loaded callee retains two yield SCs, then uses caller frame+32/+40
for seconds/nanoseconds, frame+48 for status0, frame+56 for80000000 frequency;
restores worker ID and priority output pointer, queries SC48, returns. Guest
caller/join/TLS42 unchanged.43 opcodes/172 code bytes, callee76, guest end100ac,
44 steps including HLE return within budget64. Guest SC145 CIA begin+132,
SC147 CIA begin+144; syscall history stores positive frequency in error field
because BIND records full gpr3. Dynamic seconds within before/after host
epoch bracket +/-1 second, nanoseconds<1e9; exact BE64 outputs and surrounding
full stack bytes/aliases verified on both joinable/detached repeats. Golden
module SHA1 35e335c137465f30906b2020757022063602cf7f independently reconstructed
with unchanged P40 hash cross-check; initial DATA unchanged.

P41 Configuration captures/restores clock scale and console-time offset,
temporarily100/0; enables/restores call history and existing probe settings.
Require history capacity>=15 before worker execution. New private iOS scope
ios_probe_scheduler_time_and_call clones P40 guard/admission/order/RAII logic
and invokes count policy4:43=2,46=2,47=5,48=2,145=3,147=1,6=1, others0.
16 calls/15 BIND histories. Policies0-3 preserve prior expectations.
New0038 adds only this private scope/export/header declaration, private count
policy and loader shape acceptance108/136/172 with172 upper bound. Production
time handlers, binding dispatch, scheduler, yield and fast_call are unchanged.
Keep unexecuted peer cleanup, priorities/timestamps/tag restoration, exact
ELF/BSS/stack/TLS/HLE/cache checks and CPU counter balance. No scheduler start,
peer guest execution/context switch, timers/sleep or timebase instruction yet.

Host P41 regression compiles actual full production scheduler/priority/yield/
service/fast_call bodies, real current-time and frequency functions, all
private policies/scopes and exact P41 callback. Independent bounded PPC
executor decodes43 emitted instructions, dispatches real service handlers,
checks44 steps, histories15, TLS42, stack/peer bytes, and null seconds/no-write
vs null nanoseconds/partial-write. Both variants, missing145/147 counts,
negative/throwing callback, bad counts, timestamp/priority/order/FIFO mutation
rollback, isolation/shape/nested guards and policies0-4 pass. Uses POSIX host
clock branch; clocks/offset100/0. VM aliases, locks/atomics, SC transport/
history and opcode executor are host substitutes; full iOS interpreter/ABI
still require phone. Production old P40 and P39 callback regressions pass,
including P37/P38 scopes. G++ C++20 Wall/Wextra/Werror ASAN/UBSAN, leaks off
due tool /proc restriction. Exact all-three-source0038 reverse/apply passes;
40 unique ordered UI stages P2-P41 and unique C exports verified. No XcodeSDK.

Persist test_p41_loader.py: accepts before0038/after0038 PPUModule source
arguments. Compiles real wrapper with dependency substitutes. Old172 fixture
reproduces-2 at old guard; fixed108/136/172 each pass four malformed TLS and
three malformed process checks with no allocation/unchanged outputs,
successful publication, loader failure/bad loaded-size rollback. Rejects
0/104/112/132/140/168/176 lengths, bin mismatch/data351. Same meaningful
boundary regression as0037, covering the expanded fixture before push.

Baseline maind59e5afc0d3a3c49d7fe327aa2f01cb308e0ce98,
treef0532781ac4cd51606be32d77cdd5a8c009dfc7d. Info58; Bridge/App/Info,
0038/test_p41_loader.py/handoff changed. Workflow and log export unchanged.
Build58/P41 pending Actions and phone. Do not monitor Actions. User installs
ARMSX3_iOS16_INSTALL_THIS_IPA, runs all40 diagnostics and sends log.
Full process/firmware/RSX/game boot remain untested.

2026-10-11: build58 P8/host UIKit crash; build59 SPU arena teardown fix
-------------------------------------------------------------------
Uploaded ARMSX3CoreLoadTest-2026-10-11-094357.ips and Archive(6).zip. Crash
PID1454, iOS16.0/iPhone14,3, build58, 09:43:55 Brussels. ZIP log export
ARMSX3-startup-20261011-074454-121-1486.txt was made by restarted PID1486;
contains only preceding unfinished PID1454 run (header pending P8). P2-P7
pass; P8 executes all eight SPU instructions and five mirrors, then main
thread reads invalid host address10fee3259 during CoreGraphics glyph drawing
at190759ab0. Core signal handler calls fatal/emergency_exit and aborts.
Background P8 logs cleanup/VM close continuing during the abort. P41 never
runs in this log; build58 guest timing remains unvalidated on device.

Identified production SPU destructor race in pinned SPUThread.cpp: it first
calls shm->unmap on five contiguous LS views, then memory_release on the
entire seven-LS arena including two guards. POSIX unmap creates reusable
address-space holes; UIKit/malloc can allocate inside one, then final whole
arena munmap deletes that unrelated allocation. The main-thread glyph fault
during background SPU destruction is consistent with this race; supplied
logs lack arena bounds, so exact crashed pointer ownership is inferred.
This explains how older successful runs can coexist with a timing-dependent
failure before new P41 code is reached.

New0039-ios-atomic-spu-arena-release.patch changes only iOS destructor:
release complete owned7*0x40000 arena in one memory_release operation,
without preliminary five unmaps. POSIX munmap removes shared views and guards
together; backing shm lifetime/descriptor destruction stays unchanged.
Other platform destructor branch retains original behavior. Explicit guarded
TargetConditionals include added after stdafx; builds source after0003
apple_jit include. No guest/SPU interpreter/DMA or P41 code changes.

Deterministic regression test_spu_arena_release.py persisted in repo tests.
Accepts before/after SPUThread.cpp and vm_native.cpp paths. Extracts exact
old/new destructor and production POSIX memory_reserve/memory_release bodies;
uses real mmap shared file for five LS aliases. Reserve nine-LS region to
place one sentinel region on each side of owned seven-LS arena. Force an
allocator to reuse first unmapped mirror with MAP_FIXED_NOREPLACE between
teardown operations. Old iOS/native body demonstrably deletes this allocation;
new iOS body has no intermediate holes and replacement allocated immediately
after full release remains accessible with all canary bytes. Both neighboring
sentinels, removed guards, shared aliases and single release checked across
128 cycles per variant. New non-iOS branch reproduces unchanged old behavior.
G++ C++20 Werror with ASAN/UBSAN, leak checking off for tool /proc restriction.
Host Linux syscalls and forced scheduling point model the interleaving;
not a live iOS allocator/CoreGraphics runtime test. No XcodeSDK locally.
Patch0039 exact reverse/apply verified after sole prior SPUThread patch0003.

App.mm log heading now distinguishes previous unfinished run from this run,
for both full .txt sharing and60-line copied results; selection/rotation/
filenames unchanged. This prevents interpreting export PID as the crash PID.
40 UI stages P2-P41 remain identical. CoreBridge unchanged blob
0138511efec8da94d4dada5293103ce3639a50fa. Info58->59. Only new0039,
test_spu_arena_release.py, App heading, Info and handoff changed.

Baseline main1fb8e9b0718965eb0554246d7f29694cfb9dc63e,
treee890fc0a9feb2b6499cd02b8932417e55e1e9765. Build59 pending Actions/phone.
Do not add P42 until P41 passes on phone. Do not monitor Actions after push.
User installs ARMSX3_iOS16_INSTALL_THIS_IPA, reruns all40, sends .txt/.ips
if another crash. Global process/firmware/RSX/game boot remain untested.

2026-10-11: build59 all40 device PASS; build60/P42 guest MFTB
-----------------------------------------------------------
Uploaded ARMSX3-startup-20261011-095455-668-1705.txt, header build59,
PID1705. P2-P41 AUTO PASS and final all-diagnostics PASS. P8 includes both
instruction/mirror PASS and completed-cleanup PASS; P9-P12 also pass their
SPU paths. The previous UIKit crash did not recur in this run. This device
result supports0039 but one run cannot prove the timing-dependent race is
permanently absent. P41 passes both joinable/detached repeats: current time,
null-second/no-write and null-nanosecond/partial-write errors, frequency
80000000, 44 steps, FIFO yields, 16 service calls/15 histories, cleanup.
Do not describe this as global process or game boot validation.

Before this log, user accidentally deleted the GitHub IPA artifact. Confirmed
run38122783221 (build59 commitdaeab29460301e8ea6560ecf2e25c9dda2985b47)
succeeded but install IPA absent; reran job114420781050 successfully through
connector. No code change or build-number bump for artifact recovery.
No monitoring; user subsequently supplied the successful phone log above.

Build60 appends P42 export armsx3_core_test_guest_timebase and UI row42
"Guest timebase full and upper reads". All784933 bytes of baseline
CoreBridge.cpp (Git blob0138511efec8da94d4dada5293103ce3639a50fa) preserved
as exact prefix; P2-P41 still unchanged. Include Emu/Cell/timers.hpp in new
section for core get_timebased_time(). Reuse device-passed P41 private
scheduler_time_and_call scope and syscall count policy4 unchanged; no new
scheduler wrappers, services or production instruction-handler changes.

P42 cloned P41 fixture, adds six callee words after SC147 frequency store:
MFTB r5,TBR268; STD r5,64(r1); MFTB r5,TBR269; STD r5,72(r1);
MFTB r5,TBR268; STD r5,80(r1). Architectural split TBR268 is the core's
full64 result, TBR269 upper32. XFX primary31/XO371/Rc0 encodings7cac42e6
and7cad42e6. Caller24 words unchanged, callee25/100 bytes, total49/196
bytes at10000..100c4, 50 steps including HLE return (budget64). Calleeentry
still10060; ELF data/TLS/process metadata unchanged. Golden SHA1
b792c49b4f4717bfbcae80c1e54acb1d1b92c56b, independently reconstructs
code/data and production hash records; prior P41 digest preserved.

Callback brackets actual bounded guest execution with get_timebased_time()
before/after. Read full/upper/full at frame64/72/80; require before<=first
<=last<=after, upper within first>>32..last>>32 and zero-extended32 bits.
Allows a low32 carry between reads; no arbitrary delay/progress requirement.
Current-time syscall outputs/history PCs unchanged; SC48 shifts24 bytes
within callee but preexisting history checks use final entry/host SC site.
Service counts remain16/history15; full exact stack expected image extended
only with three observed BE64 values. Frame128 retains untouched88..127;
complete ELF/stack/peer-stack/TLS alias and canary checks preserved, repeated
joinable/detached workers and retained unexecuted peers still clean up.

New0040-ios-guest-timebase-fixture.patch changes only private iOS process
probe loader wrapper: code max172->196 and exact allowlist108/136/172/196.
No generic ELF loader change. Applies after0038 and reverses byte-exactly
against staged PPUModule.cpp;0039 continues its independent SPU fix.

Persisted tests:
- test_p42_fixture.py: read-only independent instruction encoding/data/hash
  reconstruction, P41 digest, 49-word lengths, three MFTB and store encodings,
  unchanged SC positions/count. Optional CoreBridge.cpp path; defaults to
  repo core/loadtest or local scratch source.
- test_p42_loader.py: extracts exact pre0040/post0040 wrapper. Reproduces
  old196-byte rejection; checks all4 permitted sizes, malformed TLS/process,
  rejected neighboring sizes/no allocations/output mutation, rollback on
  loader failure and bad loaded size. Supply before/after PPUModule paths.
- test_p42_timebase.py: exact P42 Program/callback/TLS wrapper; full actual
  production scheduler/priority/service/fast_call bodies, unchanged actual
  MFTB operation lambda and get_timebased_time() from pinned core sources.
  VM/SC transport/flags/locks and scalar guest fetch/decode use host shims.
  Executes all49 loaded words/50 steps, validates stack/peer canaries and
  syscall counts/history, both joinability modes. Five corrupt TB variants
  must throw and restore scheduler state: oversizedupper, zero first/last,
  last outside bracket, unshiftedupper. Controlled TSC branch verifies low32
  carry values, high full64 preservation, scale50/offset7 and invalid selector
  rejection; integration uses unchanged production POSIX monotonic branch.
  Optional staged rpcs3 source-root and CoreBridge paths make it repo-usable.
G++ C++20 Werror with ASAN/UBSAN, leak checks off due tool /proc limitation.
Existing P40/P41 host callbacks and0039's three128-cycle mapping variants
also passed. No local XcodeSDK/Darwin execution; device P42 still pending.

Baseline maindaeab29460301e8ea6560ecf2e25c9dda2985b47,
treea07352f85314ef9d89d1e31c0efdfe9b2ecfe95d. Build60 changes Bridge,
App new row, Info59->60,0040,3 tests and this handoff. No workflow edits.
Do not monitor Actions after push. User installs
ARMSX3_iOS16_INSTALL_THIS_IPA, runs all41 diagnostics and sends new log.
No P43 until P42 device result; peer execution/real context switching,
scheduler start/full TLS HLE/firmware/RSX/global process/game boot untested.

2026-10-11: build60 all41 device PASS; build61/P43 memory services
----------------------------------------------------------------
Uploaded ARMSX3-startup-20261011-102428-659-1885.txt, header build60,
PID1885. All P2-P42 AUTO PASS and final all-stages PASS. P42 executes two
repetitions: MFTB full64/upper32/full64 ordered in core clock bracket,
50 steps, history/service checks and cleanup. P8 and subsequent SPU stages
pass again; previous UIKit crash did not recur in this run. Global process,
firmware/RSX/game boot still not tested.

Build61 appends armsx3_core_test_memory_syscalls (unique name; earlier P5
already has a guest_memory export) and UI row43 "Guest memory allocation
and release". P2-P42 baseline849861 bytes preserved as exact prefix,
Git blob7e5752acfe0e577e3a2c1c93abddbe88b9e04d36. Info60->61.
P43 clones device-passed P42 fixtures/worker/TLS/clock/FIFO cleanup and adds
real production SC348 sys_memory_allocate and SC349 sys_memory_free.
No core memory service, allocator, container take/free, time handler, guest
instruction, SC binding, scheduler algorithm or fast_call body changed.

Loaded guest callee adds14 words after MFTB stores: ADDIS creates size64K,
ADDI flags0x200 and frame+88 output pointer; SC348 writes aligned address,
STW saves status at frame+92. LWZ reloads address, SC349 frees it and STW
saves status at+100; reload/SC349 repeats and stores EINVAL at+104. No
dereference of guest heap in this stage; even an allocation failure cannot
cause a null heap access. Heap contents/access remain for a subsequent test.
Frame+96..99 and108..127 remain unchanged canaries. Caller24 words,
callee39/156 bytes, total63/252 bytes, end100fc,64 steps incl HLE return.
Same budget64 remains sufficient and bounded helper already allows<=4096.
ELF CODE file200..2fc ends before DATA300; new static_assert enforces this.
Fixture data/TLS/process metadata unchanged. Golden SHA1
b7696c23538699040aec282e8bc66686a87cf44c independently reconstructed;
P42 golden digest/data unchanged. Memory service PCs: SC348+192,
SC349+208, repeated SC349+224 from guest begin10000.

Before loaded guest call, real SC348 checks four invalid cases: size0 gives
EALIGN, sizeffff/64K gives EALIGN, flag100 (unsupported4K) gives EINVAL,
valid64K with null output gives EFAULT after allocation/internal free. Each
result/CIA/history/name and unchanged data/aliases verified. Error values
explicitly cast to u32 in u64 request arrays to prevent signed narrowing.
Core snapshot allocatedAddress checked nonzero/aligned; after guest release
vm::check_addr returnsfalse; status fields0/0/EINVAL and three exact history
PC/name/results checked. Only observed address added to expected stack.
Prior clock outputs/MFTB, FIFO yields, priority/join/TLS42 checks retained.

New iOS-only armsx3_ios_memory_probe_and_call in sys_memory.cpp surrounds
scheduler scope. Requires stopped Emu, current bounded PPU worker (stack
30000/8000,entry10000), initialized FXO and no nested memory probe. Explicit
TargetConditionals and Emu/System.h includes. Initialize default FXO
lv2_memory_container with1MiB only if absent, and private production
sys_memory_address_table if absent. Require exact1MiB/invalid-container-id,
zero used charge, all65536 table entriesempty and both secondary-area bases0;
refuse unrelated state. First ordinary allocator path reserves a256MiB virtual
user64K area but commits only64KiB per allocation. Retain empty1MiB diagnostic
container metadata in FXO; normal Emu.Init resets FXO before any real boot.
VM reservations are removed by P43's existing vm::close, not counted as
physical memory charge. Successful scope requires no table entries/charge.
RAII recovers any recorded allocation on negative returns or exceptions via
unchanged sys_memory_free and resets thread-local active flag. Initial table
was empty and other workers do not execute guest code, so all entries belong
to this bounded diagnostic scope. Normal memory calls are unchanged.

New private scheduler_memory_and_call clones passed two-worker stopped queue
scope and uses countpolicy5. Policies0-4 unchanged;5 adds SC348x5,SC349x2
while retaining SC145x3,147x1,43x2,46x2,47x5,48x2,6x1:23 calls/22 histories.
Null-output internal direct C++ free is not an SC349 binding event. History
minimum22 before worker execution. Initial null-join entries remainindex0;
allocation errors insertedindex3..6; guest yields11/12, clocks13/14,
allocation/free/double-free15/16/17, guest priority18/join19, post priority
no-op20/query21. All original history PCs/results retained where unchanged.

0041-ios-guest-memory-syscalls-probe.patch contains four sources: bounded
PPUModule process loader allowlist108/136/172/196/252 and max252;
lv2.cpp private policy5/scheduler scope;sys_sync.h private declaration;
sys_memory.cpp includes and private diagnostic memory scope. Audited all40
prior repo patches: none changes sys_memory.cpp/h. Production memory source
byte-identical after stripping new includes and appended iOS scope. Full0041
four-file apply/reverse matched exact baselines after0040 and prior lv2 patches.

Persisted host regressions:
- test_p43_fixture.py: read-only independent opcode/data/hash reconstruction,
  old P42 digest, ADDIS64K/flag/outputpointer/SC348/349 encodings, all9 guestSC
  positions and252-byte CODE-before-DATA boundary. Optional Bridge path.
- test_p43_loader.py: exact before0041/after0041 process wrapper; old252-byte
  rejection; all5 accepted fixtures, malformed TLS/process, rejected neighboring
  lengths, output/allocation preservation and loader-failure/bad-size rollback.
  Pass pre/post PPUModule.cpp paths when running from repo checkout.
- test_p43_memory.py: exact new Program/callback/TLS wrapper, unchanged actual
  full scheduler/priority/service/fast_call bodies; exact production
  sys_memory_allocate/free/allocate_user_memory, address-table allocate body,
  container take/free bodies and new memory-scope wrapper. VM/FXO/locks/atomics/
  SC transport/scalar guest executor use host substitutes; not live iOS VM.
  Two real-source callback repetitions, all63 guest words/64 steps, memory
  status/history/counts, two allocations/two frees per iteration (null output
  plus guest), zero charge/table and exact stack/peer canaries. Inject allocation
  failure, negative/throwing callbacks with retained successful allocations,
  positive callback leaking allocation, nested memory probe, five corrupt TB
  variants and existing scheduler negative/throwing/missingcount/state guards.
  Policies0-5 each checked. MFTB carry/scale/offset tests retained. Optional
  staged rpcs3 source-root and CoreBridge paths make extraction repo-usable.
G++ C++20 Werror, ASAN/UBSAN passed (leak checks off for tool /proc restriction).
Existing P41/P42 callback regressions passed with updated shared count policy;
fixture/loader regressions passed. No local XcodeSDK; actual Darwin/iPhone
memory-service path remains pending build61 device test.

Baseline main09eca259c8658203bb096c78e8064675c0e3310a,
treea3425029c205e10977283764e459a7893a4abc7e. Change Bridge, App new row,
Info61,0041,3 tests and this handoff. No workflow edits. Do not monitor Actions
after push. User installs ARMSX3_iOS16_INSTALL_THIS_IPA, runs all42 stages,
sends log. P44 waits for P43 device outcome. Heap memory read/write and other
memory APIs, actual peer execution/context switch/schedulerstart, full TLS
HLE/globalprocess/firmware/RSX/game boot untested.


## 2026-10-11 — build61 patch-application failure corrected in build62

Failed run38132792382, job114450405275 stopped at Apply iOS core patches, before compilation. Exact error: sys_memory.cpp:538 patch does not apply. The local source used for generating/testing0041 had an extra trailing blank line; the pinned Git source does not. Retrieved source as base64 and verified exact Git blob c3ac2a007c78791b3bbf3de81f78549dc5115f6d (13061bytes). Regenerated only sys_memory.cpp diff against that exact source. EOF blank is now an insertion, not nonexistent context. No P43 code or production service behavior changed. Build version62.

Added tests/test_p43_patch.py: verifies pinned blob, applies/reverses corrected memory patch, checks unchanged production services, reconstructs and rejects the build61 mismatch. CI runs it before patch application. Complete0041 apply/check/reverse/check against all four before0041 sources passed with byte-exact output and restoration. P43 fixture, loader and full memory/scheduler callback host regressions passed (G++C++20, ASAN/UBSAN, leak detection disabled). Real PPU history capacity2048 exceeds P43 required22. No local Xcode SDK; compile/link/device P43 remain pending. Do not advance to P44 until this stage passes on phone.

Push build62 correction to main. User observes workflow completion; do not monitor Actions after push. Download ARMSX3_iOS16_INSTALL_THIS_IPA when successful, install via TrollStore, run all42diagnostics and return phone log. Latest verified phone milestone remains build60 all41 P2–P42 PASS.


## 2026-10-11 — build62 phone PASS; build63 adds P44 allocated heap access

Phone attachment ARMSX3-startup-20261011-110235-561-2208.txt, PID2208, build62. Exactly42 AUTO PASS stages P2–P43 and final all-diagnostics PASS; no AUTO FAIL. P43 twice allocated64KiB at0x10000000, guest SC349 unmapped it, second free returned CELL_EINVAL. Null-output allocation internally freed its temporary allocation; size/alignment/flag rejections matched expected values. Stopped worker/FIFO/timebase/TLS/stack/history/cleanup remained correct. Firmware/RSX/game boot remain untested.

Build63 adds exported armsx3_core_test_heap_access / UI P44 Guest allocated memory reads and writes. Prior920272byte CoreBridge prefix retained exactly. P44 clones successful P43 scope/policy5 and adds18 guest words between allocation and free: CMPWI cr0,r3,0 + BNE +68 guard, then LWZ allocated pointer, construct12345678 with ADDIS/ORI, STW/LWZ at allocation start, construct89abcdef, STW/LWZ at allocation+65532, LBZ at allocation start and LHZ at allocation+65532. Snapshots at stack frame+96/+108/+112/+116 must be12345678/89abcdef/12/89ab. Scratch r3/r5/r6/r10 preserve worker IDr7, TLSr8 and callerTOCr9. Allocation error takes branch to free setup, skipping all heap dereferences; host test injects ENOMEM on the guest allocation (not the earlier null-output request) and confirms66steps and zero heap accesses before callback rejects results. This injected failure is host-tested, not yet phone-tested.

81words/324codebytes, callee57words/228bytes; success82steps inclHLE. Free SC PCbegin+280, double-free+296, priority query+316; allocation remains+192. Policy5 unchanged:23calls/22history. CODE file offset moved200→600, file extent760, CODE ends744; DATA stays300..460 including all ELF PRX/TLS/process metadata. Guest virtual addresses unchanged. SHA1 a7481cbe5f25eae73bf267878f5f4d5a5f5d87de. Patch0042 only extends private process-loader maximum252→324 and exact allowlist108/136/172/196/252/324. No production syscall/scheduler/allocator algorithm changes.

Host validation passed: test_p44_fixture.py independently checks oldP43/newP44 hashes/opcodes, guard target, SC PCs, region bounds, preserved DATA and stack snapshots; CI invokes it before patch application. test_p44_loader.py extracts exact before/after wrapper, confirms old rejects324, all six allowed fixtures/malformed metadata/bounds/rollback. test_p44_memory.py extracts exact P44 Program/performSyscalls/callWithTLS and production scheduler/service/fast_call/allocation/free/container accounting/time/MFTB bodies; atomics/VM/locks/SC transport/scalar guest execution are host substitutes. Both joinability iterations82steps/22histories; four heap reads/two stores; deallocation snapshot checks every64KiB byte and adjacent canaries; tests five heap snapshot/endian/store corruptions, guest ENOMEM guard, earlier error/null-output cases, allocation leak/exception/nested cleanup and all previous clock/FIFO guards. G++C++20 Werror ASAN/UBSAN, detect_leaks=0. Original P43 callback regression also passed. Complete0042 applies/reverses to byte-exact PPUModule baseline/output. Build62 EOF/pinned-source regression remains in CI and passes. No local Xcode SDK; iOS build/link/device P44 pending.

Push build63 to main, user monitors workflow. Download ARMSX3_iOS16_INSTALL_THIS_IPA after success, install TrollStore, run all43diagnostics and send phone log. Do not monitor Actions after push; do not advance toP45 before phone P44 PASS.


## 2026-10-11 — build63 phone PASS; build64 adds P45 memory availability reports

Phone attachment ARMSX3-startup-20261011-113227-831-2360.txt, PID2360, build63. Exactly43 AUTO PASS P2–P44 plus final all-diagnostics PASS. Both P44 iterations82steps: guest allocation0x10000000, first/last heap word STW/LWZ12345678/89abcdef, LBZ12 and LHZ89ab confirm big-endian subloads, guest free unmaps and double-free rejects. All previous diagnostics remain PASS; firmware/RSX/game boot remain untested.

Build64 adds armsx3_core_test_memory_stats / UI P45 Guest available memory accounting. Prior991170bytes of CoreBridge retained exactly. P45 clones successful P44, adding three actual guest SC352 sys_memory_get_user_memory_size calls: before allocation (DATA+384), after heap stores/reads while allocation lives (+392), and after free/double-free (+400). Struct fields total/available are u32 big-endian; expected totals all1MiB and availability1MiB/960KiB/1MiB. Status words atDATA+408/+412/+416 must all0. This is the isolated1MiB diagnostic container, not a game RAM limit. Reports live in initially-zero DATA BSS after unchanged352byte ELF payload. Exact full DATA/stack/code/TLS/peer aliases and canaries retained. No invalid-pointer SC352 call (production handler unconditionally publishes its struct).

93words/372bytes, callee69words/276bytes,94stepsinclHLE. CODE file600..774, file extent780; DATA remains300..460. Failed guest allocation guard still skips16heap access words and lands at during-allocation query; host-injected guest ENOMEM path78steps with zero heap reads/writes, rejected by normal result checks. SC352 PCsbegin+184/+296/+344; allocation+208,free+312,doublefree+328,priority+364. Golden SHA1 399427cd45771d16d0e8c6a24e670900237e1c91. Policy6 counts352x3 plus unchangedpolicy5 counts =26calls/25histories. All policies0–5 preserved.

Patch0043: private loader exact allowlist/max adds372 (all older108/136/172/196/252/324 remain accepted); scheduler_memory_stats_and_call clones unchanged stopped two-slot pair scope with policy6; sys_sync private declaration; appended iOS-only memory_stats_probe_and_call initializes last_reported_memory_stats FXO if absent, rejects extra IDM memory containers, saves/restores its atomic cached total/available on every return/throw, delegates unchanged scoped memory allocator wrapper, then verifies restored cache fields. Production allocation/free/query/scheduler algorithms and syscall bindings unchanged. Scope remains stopped-only, current worker, no existing memory scope; original inner memory wrapper enforces exact stack/entry/container/table guards. FXO metadata retained zero-charged; Emu.Init resets before future game boot.

Host checks passed with G++C++20 Werror ASAN/UBSAN detect_leaks=0. test_p45_fixture.py independent opcode/hash/branch/SCPC/ELFregion/snapshot checks, also P44/P43 regressions; CI now invokes P45 fixture check prepatch and keeps exact pinned-source EOF test. test_p45_loader.py exact before/after wrapper old372rejection, sevenfixtureallowlist, malformedmetadata/bounds/rollback. test_p45_memory.py exact P45 callback, actual sys_memory_get_user_memory_size/allocate/free/container bodies, all scheduler/service/fast_call/time/MFTB implementations; VM/atomics/locks/IDM enumeration/SC transport/scalar guest executor are host shims. Verifies three reports, five corrupt total/available/status/history cases, stats cache restoration with nondefault values on returned error and exception, extra-IDM-container rejection, all prior heap endian/canary/failure/cleanup and clock/FIFO guard tests. Both joinabilityiterations94steps/25histories. Original P44 callback regression passed on new shared policy logic. Complete0041→0042→0043 apply/check and reverse/check chain reproduces all four final production files byte-exactly and restores baseline. Repository-layout CI fixture invocation and workflow YAML verified. No local Xcode SDK: full iOS compile/link and P45 device execution pending.

Push build64 to main; user monitors workflow. After success download ARMSX3_iOS16_INSTALL_THIS_IPA, install TrollStore, run all44diagnostics and send phone log. Do not observe Actions after push and do not advance toP46 before P45 phone PASS. Browser deleting complaint was for another chat; user explicitly withdrew it. Accidental imagegen selector remains irrelevant; do not generate images.


## 2026-10-11 — build64 P45 setup failure corrected in build65

Phone attachment ARMSX3-startup-20261011-115706-145-2493.txt, PID2493, build64. Exactly43 AUTO PASS P2–P44. P45 loaded/validated its ELF/process/TLS/linkage, then returned -4 before the guest call: fast_call0, history/syscalls0, worker/peerSTOP with state restored. No P45 SC352 actually ran; P45 is not yet a verified phone milestone.

Root cause found in the newly appended P45 memory-statistics scope: it called idm::select<lv2_memory_container> without constructing the FXO id_manager::id_map<lv2_memory_container>. Pinned System.cpp Emulator::Init calls g_fxo->reset(), not global FXO init; manual_typemap::reset fills unconstructed storage with0xCC. Its get<T>() explicitly returns potentially uninitialized memory. Exact IdManager.h select body gets the map directly and scans all16 pointer slots, with no is_init check. No earlier diagnostic constructs this memory-container registry. Its nonzero trap pointers make the guard mark otherContainers=true and return-4 before dereferencing container fields. This matches the observed no-guest-execution rejection; source analysis identifies the cause, with device confirmation still pending.

Build65 modifies only P45 iOS diagnostic wrapper in existing0043: explicitly initialize ContainerMap if absent before select, return-3 if initialization fails, retain and preserve an already-initialized map, reject real extra containers as before. Added core-log messages distinguish an actual nonempty-registry rejection from a ready initialized/empty memory scope. Both guard and unchanged production SC352 handler can now safely enumerate constructed empty storage. Production allocator/free/query, scheduler, earlier diagnostics, fixture/opcodes/hash and UI44stages remain unchanged. CFBundleVersion65.

Strengthened test_p45_memory.py: compiles the exact pinned IdManager.h select body (template signature/constraints, map storage and supporting transport remain host substitutes). FXO shim now rejects get<T>() on unconstructed storage instead of letting enumeration use an unrelated vector. Build64 scope with initialization removed reproduces the unsafe access as a deterministic shim exception before callback/history; this host check deliberately avoids dereferencing trap pointers. Corrected scope initializes once, survives reuse across both joinability modes, rejects injected map-init failure without guest execution, preserves a sparse real-container registry while rejecting the scope. Existing P45 tests all pass:94steps/25histories, three total/availability reports1MiB and1MiB/960KiB/1MiB, cache restoration/error/throw, corrupted statistics, heap/canaries/endian, allocation guard, clocks/FIFO/TLS/history and cleanup. G++C++20 Werror ASAN/UBSAN detect_leaks=0. Exact production select body is used by both outer guard and query. P44 full callback regression also passes. P45 fixture/loader and P43 pinned-EOF regression pass. Complete0041→0042→0043 apply/check/reverse/check reproduces all four final source files and restores baselines byte-exactly.

No local Xcode SDK; full iOS compile/link and corrected P45 phone execution remain pending. Do not add P46 until P45 passes on the phone. Push build65 correction to main; user observes Actions completion. After success download ARMSX3_iOS16_INSTALL_THIS_IPA, install TrollStore, run all44diagnostics and send the log. Do not monitor Actions after push. Baseline main0e827b39ac3c8700607871d87888592e87d059aa, tree1ca48b9d9108c8b9be49492edebe5894c01633c4. Four changed repository files:0043 patch, test_p45_memory.py, Info.plist.in and handoff. The review IdManager.h is a byte-exact pinned source dependency for local tests, not a new repository file.


## 2026-10-11 — build65 phone PASS; build66 adds P46 1 MiB pages

Phone attachment ARMSX3-startup-20261011-121853-136-2572(1).txt, PID2572,
build65. Exactly44 AUTO PASS stages P2-P45 and final all-diagnostics PASS.
P45 twice returns94, with constructed/empty memory-container registry,
three total/available reports1MiB and1MiB/960KiB/1MiB, correct first/last
heap snapshots/endian subloads, free/double-free and scheduler/TLS cleanup.
The build65 registry correction is now device-confirmed. Game boot pending.

Build66 adds armsx3_core_test_memory_1m and UI rowP46 Guest 1 MiB memory pages.
All1064313bytes of build65 CoreBridge remain an exact unchanged prefix.
New stage reuses the passed P45 stopped-worker/syscall policy6/memory-statistics
scopes without adding/changing upstream patches or production algorithms.
Guest SC348 now requests0x100000 bytes with flag0x400 SYS_MEMORY_PAGE_SIZE_1M.
Guest ADDIS for the last-word pointer advances1MiB, not64KiB; STW/LWZ at
allocation+0xffffc and LBZ/LHZ retain12345678/89abcdef/12/89ab results.
Returned allocation must be1MiB-aligned. After free, first/last addresses
are both unmapped; double-free remainsEINVAL. Availability now1MiB/0/1MiB.
Diagnostic1MiB container is isolated test metadata, not the future game limit.

Pre-guest real SC348 error cases: zero sizeEALIGN, size0xfffff with1MiB
flagEALIGN, size2MiB with1MiB flagENOMEM (container only1MiB, no VM allocation
or output mutation), valid1MiB with null outputEFAULT after internal release.
These replace the new stage's64KiB preflight cases, retaining four calls and
all syscall history/count indexes. P45 still retains its original tests.
Only3 guest words differ from P45: indices48(size),49(flag),62(end pointer).
93words/372bytes, callee69words/276bytes,94successsteps/78guest-ENOMEM steps,
all12guestSC PCs, DATA metadata and file offsets unchanged. Golden SHA1
c8da24be12d80e9c20442d28885eebed3d7c6288. Exact full DATA/stack/code/TLS/peer
alias and canary comparisons and two joinability modes remain intact.

Host validation: test_p46_fixture.py runs P43-P45 fixture regressions and
independently encodes/checks three changed words, hash, allocation-failure
branch, region bounds,1MiB alignment/last mapping and availability snapshots.
CI runs this fixture prepatch (replaces P45 fixture command, preserving those
checks transitively). test_p46_memory.py compiles exact new Program/callback
and production service/allocator/accounting/scheduler/clock/MFTB/IDM bodies.
VM/FXO/atomics/locks/SC transport/scalar guest executor remain host substitutes.
Asserts production user1m location/block flags on both null-output and guest
allocations, all1MiB released heap bytes plus adjacent canaries, two allocation/
free events (oversized request performs no VM allocation), availability zero,
all existing corruption/cleanup/TLS/FIFO/clock/history/registry guards.
G++C++20 Werror ASAN/UBSAN detect_leaks=0 passed, plus original P45 callback.
All43 existing patches apply/check to exact pinned upstream; pinned-source
P43 EOF regression, bridge-prefix, workflow YAML/plist and diff checks pass.
No local Xcode SDK: full iOS compile/link and P46 device test pending.

Baseline mainccfffaffc561eb1094a040a4c540a3b7b045455c. Push build66 to main;
user observes Actions completion. Do not monitor Actions after push. Download
ARMSX3_iOS16_INSTALL_THIS_IPA, install TrollStore, run all45 diagnostics and
send startup log. Do not advance toP47 until P46 device PASS. Actual peer
execution/context switching/schedulerstart/full TLS HLE/global process/
firmware/RSX/game boot remain untested. No images.


## 2026-10-11 — build66 phone PASS; build67 adds P47 page attributes

Phone ARMSX3-startup-20261011-124725-730-2787.txt, PID2787, build66:
all45 AUTO PASS P2-P46 plus final all-diagnostics PASS, no AUTO FAIL.
P46 both iterations return94: actual1MiB heap0x10000000, first/last
word/endian subloads, availability1MiB/0/1MiB, oversized2MiB ENOMEM,
null-output internal release, guest free/double-free and complete cleanup.
Game boot remains pending. Do not confuse this diagnostic container with
a future game RAM limit.

Build67 adds armsx3_core_test_page_attributes/UI P47 Guest live and freed
page attributes. All1137604bytes of build66 Bridge preserved as exact prefix.
P47 retains P46's1MiB allocation, clocks/FIFO/TLS/heap/arguments/error checks,
adding two actual loaded guest SC351 sys_memory_get_page_attribute calls.
Live heap query after heap accesses and before during-allocation SC352 writes
24byte big-endian sys_page_attr_t at DATA+448: attribute0x40000, access0xf,
page_size0x100000,pad0; status0 at+472. These are the current production
handler's reported fields; permissions/access fields are upstream TODOs,
not proof of complete PS3 permission emulation. Freed heap query after
free/double-free outputs to DATA+480, must returnEINVAL with all24bytes
unchangedzero; status at+504. Exact guest PC/name/history/error checked
for both queries (PC+300/+368), and full DATA/stack/code/TLS/peer aliases
still compared after each of two joinability iterations. Production table
SC351 function/name checked before fixture execution.

Fixture103words/412bytes, callee79words/316bytes,104successsteps inclHLE.
Guest allocation failure guard unchanged, skips16heap-access words and
then attempts query of the unallocated address; host failure path88steps,
no heap reads/writes, normal output checks reject it safely. Same CALLER/
DATA metadata, CODE file600..79c inside fixture800. Golden SHA1
c8cfa90edc95d79ef5c28e293942c461ca6867a0. SC352 PCs184/316/384,
allocation208,free332,doublefree348,priority404. Policy7 adds351x2 to
policy6 counts:28calls/27histories; prior policies0-6 retain exact counts.

New0044 patch touches only private iOS PPUModule process fixture allowlist/
max (adds412), lv2 diagnostic count policy and new stopped two-worker
scheduler_page_attributes scope cloned from passed stats scope, sys_sync
private declaration. Production SC351/allocate/free/query/VM/scheduler
algorithms and bindings unchanged. P45 memory-statistics scope retained,
including build65 FXO registry initialization and error/throw restoration.

Validation passed: test_p47_fixture.py independently reconstructs P47
opcodes/hash/inserted queries/guard/SC PCs/BSS bounds/ABI/status outputs,
and transitively runs P43-P46 fixtures; now CI prepatch check.
test_p47_loader.py extracts exact before/after0044 process wrappers,
reproduces old412 rejection, tests all8accepted sizes, malformed TLS/
process/lengths and complete output/allocation rollback.
test_p47_memory.py extracts exact new Program/performSyscalls/callWithTLS,
unchanged production page-attribute and all earlier service/allocator/
accounting/time/MFTB/scheduler/IDM bodies. Locks/atomics/FXO/VM/SC transport
and scalar guest execution remain host shims. Heap virtual0x10000000 uses
dense backing translated by shim; deliberately different high nibble than
worker stack0x30000, so actual SC351 takes VM path, not stack4KiB fast path.
Valid/freed structs/status/history, seven injected page field/error/output
corruptions reject and restore, null-output EFAULT/out-of-range EINVAL
no-write and last-word1MiB attribute (host-only boundaries), all8count
policies including missing351, heap/canaries/endian/ENOMEM, clock/FIFO/TLS
registry/cached stats and error/throw/leak guards pass. G++C++20 Werror
ASAN/UBSAN detect_leaks=0. Original P46 callback also passes new shared
count code. All44patches apply/check and reverse/check against fresh
pinned source reconstruction, reproduce complete final source bytes and
restore original bytes; specific0044 three-file roundtrip also exact.
Workflow YAML/plist/bridge-prefix/diff checks pass. No local Xcode SDK:
full iOS compile/link and P47 phone execution pending.

Baseline main2dce4cad73140de21ab4d6786bcc860fdf246745. Push build67 main;
user observes Actions completion. Do not monitor Actions after push.
Download ARMSX3_iOS16_INSTALL_THIS_IPA, install TrollStore, run all46tests
and send startup log. NoP48 until phoneP47 PASS. Actual peer execution/
context switching/schedulerstart/global process/full TLS HLE/firmware/
RSX/game boot remain untested. No image creation for startup-log work.


## 2026-10-11 — build67 phone PASS; build68 adds P48 page-output errors

Phone ARMSX3-startup-20261011-131211-382-2962.txt, PID2962, build67:
all46 AUTO PASS P2-P47 and final all-diagnostics PASS, no AUTO FAIL.
P47 returns104 in both iterations: live1MiB page attribute40000/accessf/
page100000/pad0/status0; freed address EINVAL with untouched24-byte output.
All allocation/statistics/endian/FIFO/clock/TLS/alias cleanup checks pass.
Actual game boot remains untested.

Build68 adds armsx3_core_test_page_attribute_errors/UI P48 Guest page
attribute output errors. Complete1213640-byte build67 Bridge remains an
exact prefix. P48 retains all P47 checks, adds two loaded guest SC351 calls
on the live1MiB allocation immediately after its successful page query:
null output pointer and output0x9fff8, the final eight mapped bytes of the
retained peer's64KiB block, followed by an unmapped guard at0xa0000. Both
must return sign-extended CELL_EFAULT, store statuses at DATA+508/+512,
and have exact service names/history/SC PCs+320/+344. A preloaded aligned
64-bit sentinel5aa55aa5deadbeef at0x9fff8 must remain unchanged, including
the exact full peer-stack comparison. Mapping guard verifies readable8,
unreadable24, unmapped0xa0000 before execution. The peer remains unexecuted.
The current SC351 handler checks the complete24-byte output before writes;
these guest tests verify rejection without partial publication on device.
Current reported permission/access values are upstream TODOs, not a claim
that PS3 permission emulation is complete.

Fixture114words/456bytes, callee90words/360bytes,115steps including HLE.
Allocation failure branch still skips16heap accesses,99host steps and no
heap access; normal callback rejects outputs. ELF CODE600..7c8 inside800,
unchanged352-byte DATA payload300..460/TLS/process metadata. SHA1
acdc835b5c0163e1bd8f534e74aca9117e9d2184. SC PCs60,100,112,132,144,
184,208,300,320,344,360,376,392,412,428,448. Stats before/during/after
histories15/20/24 and PCs184/360/428; allocation16/208, live attr17/300,
invalid outputs18/320 and19/344, free21/376, double-free22/392,
freed attr23/412, guest priority25/448, caller join26/60, post no-op
priority27, final query28. Policy8 requires351x4, thirty service calls/
twenty-nine recorded histories. Prior policies0-7 preserve exact counts.

0045-ios-guest-page-output-errors-probe.patch changes only private iOS
fixture loader size allowlist/max (adds456), diagnostic count policy8,
new stopped two-worker scheduler_page_attribute_errors scope/declaration
cloned from passed P47 scope. Production memory/VM/SC351/scheduler service
algorithms and bindings unchanged. Existing1MiB diagnostic container is
isolated; it does not define future game RAM limits.

Validation passed: test_p48_fixture.py independently checks inserted null/
partial-output words, complete code hash, SC PCs, guard, history/status
layout, sentinel,115steps and ELF bounds; transitively P43-P47 fixtures;
CI now runs this prepatch. test_p48_loader.py extracts exact pre/post0045
wrappers, reproduces old456 rejection, verifies all9accepted sizes,
neighbor rejection, malformed metadata and allocation/output rollback.
test_p48_memory.py extracts exact new Program/performSyscalls/callWithTLS,
production page-attribute/allocation/free/stats/clock/MFTB/IDM/scheduler
bodies. VM/FXO/locks/atomics/SC transport/scalar guest execution are host
shims, not native PPU execution. Both joinability runs115steps, statuses/
histories/sentinel,11page corruptions (includes wrong null success/error,
partial-buffer success/write), all9count policies, missing services,
heap/canaries, registry/statistics, ENOMEM99steps, TLS/FIFO/clock/cleanup
regressions pass. G++C++20 Werror ASAN/UBSAN detect_leaks=0. Original P47
host integration also passes new shared policy code. All45patches check/
apply/reverse/check against byte-exact pinned originals, final source
matches staging, originals restored; P43 pinned EOF regression passes.
Workflow/plist/prefix/whitespace checks pass. No local Xcode SDK: full iOS
compile/link and P48 phone run pending.

Baseline main27d0883a15d2e008ac94ab556842f98413fd830a. Push build68 main;
user observes Actions completion. Do not monitor Actions after push.
Download ARMSX3_iOS16_INSTALL_THIS_IPA, install TrollStore, run all47tests
and send startup log. No P49 until phone P48 PASS. Actual peer execution/
context switches/scheduler start/global process/full TLS HLE/firmware/
RSX/game boot remain untested. No images for startup-log work.


## 2026-10-11 — build68 phone PASS; build69 adds P49 process SDK queries

Phone ARMSX3-startup-20261011-133226-499-3719.txt, PID3719, build68:
all47 AUTO PASS P2-P48 and final all-diagnostics PASS, no AUTO FAIL.
P48 returns115 twice, null/partially mapped page outputs EFAULT, peer-tail
sentinel unchanged, all earlier live/freed/heap/stats/FIFO/clock/TLS cleanup
checks pass. Game boot remains untested.

Build69 adds armsx3_core_test_process_sdk/UI P49 Guest process PID and ELF
SDK. Complete1291554-byte build68 Bridge remains an exact prefix. P49 adds
loaded guest SC1 sys_process_getpid and SC25 sys_process_get_sdk_version
after the final memory report and before priority query. SC1 result stays
in r3 for the subsequent SC25 PID argument; outputs at DATA+544 PID1,
+548 parsed ELF SDK00360001, +552 SDK query status0. Exact service table
names, guest SC PCs440/456 and recorded history25/26 verified. The SDK
value enters Program from processParameters[0], the production ELF parser
output, then reaches a stopped-worker metadata scope during execution.
These test current upstream behavior: process_getpid has a TODO and
returns1, process_get_sdk_version ignores PID and reads the global SDK.
This does not implement a real process registry or full process startup.

New iOS-only armsx3_ios_process_sdk_probe_and_call in sys_process.cpp
publishes only the fixture SDK00360001. Guards stopped emulator/current
worker/static decoder/exact stack and entry/expected SDK, rejects nested
scopes, saves previous global sdk_ver, restores it and its active flag on
normal/error/throw exits. Callback SDK mutation returns-3 before RAII
restoration. Production process handlers/bindings remain unchanged.
Scope ordering: TLS -> memory statistics -> process SDK -> stopped pair
scheduler -> exact callback. Bridge snapshots SDK before entering and
checks restoration afterward. Other process fields are not changed.

Fixture121words/484bytes, callee97words/388bytes,122successsteps inclHLE;
allocation failure106host steps skips16heap accesses. CODE600..7e4 inside
800, unchanged352-byte DATA300..460 and TLS/process metadata. SHA1
4c9d73c848817ee4a40eb2aafdd50d4686e23a70. Old memory SC PCs/history
unchanged; new PID25/440, SDK26/456, priority27/476, callerjoin28/60,
post no-op priority29, final query30. Policy9 requires1x1,25x1 and retains
policy8 counts:32service calls/31histories. Ring minimum31. Prior policies
0-8 retain exact counts and existing accepted fixture sizes remain valid.

0046-ios-guest-process-sdk-probe.patch touches private iOS loader max/
allowlist (adds484), diagnostic policy9/new scheduler_process_sdk scope
and declaration, sys_process.cpp iOS metadata wrapper/conditional Apple
header plus system_config include. Production process/VM/memory/scheduler
algorithms are unchanged. Includes sys_process.h only at the new Bridge
append. The isolated diagnostic1MiB memory container is not a game limit.

Validation passed: test_p49_fixture.py independently encodes seven added
words, PID-in-r3/SC25 ABI, hash/bounds122steps, service PCs/history/layout,
parsed SDK propagation/restoration; transitively P43-P48 fixture checks;
CI now invokes it prepatch. test_p49_loader.py exact pre/post0046 wrapper
reproduces prior484rejection, all10accepted sizes, neighbors/malformed
TLS/process metadata and complete output/allocation rollback.
test_p49_process.py extracts exact Program/performSyscalls/callWithTLS,
production process_getpid/sys_process_getpid/process_get_sdk_version/
sys_process_get_sdk_version and SDK wrapper plus all earlier service,
IDM/allocator/clock/MFTB/scheduler bodies. Locks/FXO/VM/atomics/SC transport/
scalar guest execution remain host shims. Both joinability runs122steps,
nondefault SDK restoration, PID argument/publication/history, wrong PID/
SDK/status rejection, positive/negative/throw/mutation/nested/10guard SDK
scope cases, all10count policies/missing services, preceding page/heap/
stats/TLS/FIFO/clock/registry/error/cleanup tests pass. Host CellError shim
uses real enum u32 ABI; no production change needed for that harness fix.
G++C++20 Werror ASAN/UBSAN detect_leaks=0. Original P48 integration also
passes new policy code. All46patches check/apply/reverse/check against
byte-exact pinned originals and final staging, restore original bytes;
P43 pinned EOF regression passes. Workflow/plist/prefix/whitespace pass.
No local Xcode SDK: native iOS compile/link/P49 phone execution pending.

Baseline maindb25ea984906f0a5deaa1b3ba95328788dad38d1. Push build69 main;
user observes Actions completion. Do not monitor Actions after push.
Install ARMSX3_iOS16_INSTALL_THIS_IPA using TrollStore, run all48tests and
send startup log. No P50 until phone P49 PASS. Actual peer execution/
context switches/scheduler start/global process/full TLS HLE/firmware/
RSX/game boot remain untested. No images for startup-log work.


## 2026-10-11 — build69 phone PASS; build70 adds P50 active PPU pair

Phone ARMSX3-startup-20261011-140319-543-3866.txt, PID3866, build69:
all48 AUTO PASS P2-P49, final all-diagnostics PASS, no AUTO FAIL. P49
returns122 twice, SC1 PID1/SC25 ELF SDK00360001/status0, previous SDK
restored, all earlier checks/cleanup pass. Game boot remains untested.

Build70 adds armsx3_core_test_active_ppu_pair/UI P50 Two active PPU workers
and budget isolation. Complete1372215-byte build69 Bridge stays exact
prefix. This is a separate paired-execution diagnostic, not a continuation
of P39-P49's unexecuted scheduler peer. It creates and actually launches
two named PPU CPU command workers per round, with distinct IDs, separate
64KiB stack blocks30000/40000 (constructor uses32KiB), outputs DATA20100/
20200, register sentinels and native CPU/thread_ctrl TLS identity checks.
Requires stopped emulator, no live CPU workers, two configured PPU slots.
Both callbacks publish ready and wait at a release gate; root checks both
ready and exactly two live CPU workers before releasing. This establishes
overlapping native worker lifetimes, not guaranteed simultaneous guest
instruction execution on different physical cores. Both execute the same
prepared guest code via existing production exec_task/exec_bounded helper.
No LV2 scheduler admission, full process startup or context switching.

Shared CODE10000 contains7words: LI r3,0; MTCTR r4; ADDI r3,r3,1;
BC16,0,-4; STW r3,0(r6); LWZ r7,0(r6); ORI r8,r7,100. Note core macro
ORI takes source first, destination second: ORI(7,8,100), encoded60e80100.
Production range registration and eager function decoding occur before
workers launch; no shared lazy-cache mutation. Success steps2*N+5, CIA
CODE+28, ctr0, r3/r7=N,r8=N|100, big-endian outputN. Four rounds use
counts17/31,20/34,23/37,26/40. Results39/67,-2/73,51/-2,57/85; round2
limits primary, round3 limits peer to8instructions, other worker budget128.
Limited worker has r3=3,ctr=N-3,CIA=CODE+8, untouched r7/r8/output. Global
handler's existing ios_ppu_dispatch_probe is thread_local; no new scope,
count policy, loader allowance or upstream patch. Existing46patches intact.

Both programs use release/acquire ready/completion and cancellation gate,
with2second deadlines. StopPair is declared before construction; cancels/
releases gate, sets exit/notifies both workers, launches any retained but
unstarted worker with exit set so CPU retirement balances, joins all
unjoined workers before program/VM storage unwinds. Callback catches
execution exceptions as-7, publishes completion and exits. Four complete
64KiB CODE/DATA/stack blocks compared via normal/super aliases after joins;
only successful4-byte outputs may differ from a5 DATA, stacks/code remain
unchanged. Cache pointers verified unchanged. Each round creation/deletion
counters +2 and live count restored. Segment cache released before VM
allocations/deallocation/close; all configuration restored. P50 does not
bootstrap guest TLS: it verifies host CPU thread-local identity and r13
sentinel isolation, preserving prior P32-P49 guest TLS results separately.

Validation passed: test_p50_fixture.py independently encodes all7words,
ORI field order, executes scalar loop model for normal/limited outcomes,
exact PCs/steps/registers/untouched output, checks gate/cleanup/alias/counter
invariants. Transitively P43-P49 independent ELF fixture/hash tests preserved;
CI now invokes this prepatch. test_p50_pair.py extracts exact full P50
Bridge, production exec_task and exec_bounded bodies and actual thread_local
probe declaration. p50_host_shims.cpp supplies host native std::threads,
CPU flags/lifecycle/queue/VM/cache/FXO/decoder and seven scalar instruction
operations; it does not compile native RPCS3 PPU handlers/CPU queue/VM.
32host pairs (8complete phase repetitions) force interleaved fetches;
check exact4pair logs/results, TLS/current worker, both budget isolations,
registers/stacks/full aliases/cache/counters. Corrupt result/guard, queued
publication failure with both unstarted workers constructed, active-gate
cancellation, interpreter exception, all4allocation failures, stopped/
slot/FXO guards verify join/close/config/ID/counters restored. Each shim
worker checks its own dispatch TLS cleared at exit. G++C++20 Werror,
ASAN/UBSAN detect_leaks=0 passed. Workflow/plist/prefix/whitespace pass.
No source patch changed; prior full46patch-chain validation remains valid.
No local Xcode SDK: native iOS compile/link and P50 phone run pending.

Baseline mainc8719fb11188ca112eef0258dadc62a1d01f6ef4. Push build70 main;
user observes Actions completion. Do not monitor Actions after push.
Install ARMSX3_iOS16_INSTALL_THIS_IPA with TrollStore, run all49tests and
send startup log. No P51 until phone P50 PASS. If P50 passes, two independent
native workers' guest execution is newly confirmed, but LV2 scheduling/
context switches/global process/full TLS HLE/firmware/RSX/game boot remain
untested. Earlier P39-P49 scheduler peers remain unexecuted. No images.

## 2026-10-11 — build70 phone PASS; build71 adds P51 persistent PPU pair

User supplied ARMSX3-startup-20261011-143237-905-4045.txt and "Lets gooo".
Build70 confirmed all49 P2-P50 AUTO PASS plus final all-stages PASS; no
AUTO FAIL. P50 four native pairs yielded39/67,-2/73,51/-2,57/85 with both
workers live at their release gate, independent CPU TLS/registers/budgets,
full aliases/cache and balanced cleanup. This confirms actual independent
native PPU guest execution; it does not prove physical simultaneous CPU
execution or real LV2 scheduler admission/context switching.

Build71 adds armsx3_core_test_persistent_ppu_pair/UI P51 Persistent PPU pair
and budget recovery. P2-P50 Bridge prefix1386378bytes retained exactly;
no source patch changed, existing46patch-chain validation remains valid.
Shared seven opcodes and four64KiB CODE/DATA/stack allocations match P50.
Construct exactly two real native PPU command workers once, start both
with empty queues, observe aggregate command-wait count growth >=2 and
live+2. Across eight rounds enqueue one ptr_call per worker and notify
both real queues. Gate uses monotonically published round numbers;
both ready and completed counters require exact round+1. Worker callback
alone resets its own live registers/CIA/CTR and invokes exact production
bounded exec_task. Host reads a release/acquire register snapshot rather
than touching live registers. No Program/guest access after completion
publication. Inputs republished after previous completion and native
queue publication; cancellation guard wakes/joins both, including any
constructed but unlaunched worker before Program/VM destruction.

Per-worker loop counts17+round*3+i*14, budget8 for(round%4==1,i0) or
(round%4==2,i1),128 otherwise. Expected paired results:
39/67,-2/73,51/-2,57/85,63/91,-2/97,75/-2,81/109.
Four limited jobs stop at8steps/CIA10008/r3=3/CTR=count-3, leaving their
unique output slot and r7/r8 unchanged. Each limited worker completes
its next job on the SAME worker: recovery(round,index)=(2,0),(3,1),
(6,0),(7,1). Each slot DATA+100+round*20+i*4 starts a5; successful output
is count big-endian. Entire DATA snapshot retains every earlier result,
limited slots and guards; compare whole64KiB CODE/DATA/both stacks through
normal and super aliases each batch. Check cache unchanged, own CPU/thread
TLS, snapshot of13register/context values, no syscalls/interrupt/exit,
unchanged IDs and exactlycreated+2/deleted baseline while running. Command
wait counter is aggregate activity, NOT per-worker parked-state proof.
Finally enqueue exactly one exit callback per worker, notify/join both,
require two exit acknowledgments andcreated/deleted+2/live baseline.
Release segment cache before deallocating all four regions and closing VM;
configuration and construction ID restored on success and error.

Validation passed: test_p51_fixture.py independently encodes seven words,
models all16jobs with two reused contexts, precise PC/steps/CTR/partial
registers, four recovery sequences and accumulating guarded output.
Transitively retains P43-P50 fixture/hash checks; CI prepatch now invokes
P51. test_p51_pair.py extracts EXACT full P51 phase and production probe,
exec_task and bounded helper; p51_host_shims.cpp provides persistent host
std::thread workers, mutex/CV command queues, flags/VM/decoder/scalar guest
instruction operations. Eight full repetitions =16persistent host workers,
128guest jobs,16queued exits. Force instruction yields and assert each
worker's own production dispatch TLS cleared after EVERY callback and exit.
G++C++20 Wall/Wextra/Werror ASAN/UBSAN detect_leaks=0 passed. Corrupt load,
extra output write, mid-batch/initial/second-exit queue publication failures,
active-gate cancellation, instruction throw, second constructor failure,
dropped job plus all4alloc/setup guards return error with balanced joins,
no maps/probe, configuration and IDs restored. Host queues/VM/native PPU
operations remain shims; native iOS compile/link/device P51 pending (no
local Xcode SDK). UI50rows uniqueP2-P51 symbols, plist71, workflow fixture,
Bridge exact prefix and whitespace checked.

Baseline mainc28e5ab90fbbee662ab26a0cd1030790b436f28e. Push build71 main;
user observes Actions completion. DO NOT monitor Actions after push.
Install ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, run all50diagnostics
and send startup log. No P52 until phone P51 PASS. Full LV2 scheduler
admission/context switching/global process/full TLS HLE/firmware/RSX/game
boot remain UNTESTED. Earlier P39-P49 scheduler peers remain unexecuted.
No images requested or generated.

## 2026-10-11 — build71 phone PASS; build72 adds P52 paired guest TLS

User supplied ARMSX3-startup-20261011-150754-444-4118(1).txt and Continue/
Here you go. Library idlibfile_30f4ca3195008191bb227649dadbe1fb, scratch
../upload/ARMSX3-startup-20261011-150754-444-4118(1).txt. Build71 ALL50
P2-P51 AUTO PASS, final all-stages PASS, no AUTO FAIL. P51 eight batches
39/67,-2/73,51/-2,57/85,63/91,-2/97,75/-2,81/109 passed on SAME two native
workers: notified real queues, four isolated budget stops and later recovery,
retained output/guards/aliases/cache/snapshots, queued exits/two joins.
This newly confirms persistent paired native PPU execution/reuse on device,
not physical simultaneous CPU execution or actual LV2 scheduling.

Build72 adds armsx3_core_test_paired_guest_tls/UI P52 Paired guest TLS
allocation and isolation. Keeps previous1402983byte Bridge prefix exact.
CODE/DATA/two stacks remain10000/20000/30000/40000, four64KiB allocations;
main reserve now10000 size80000 leaves50000-8ffff for owned256KiB TLS pool.
Shared12words48bytes: LI3,MTCTR4,ADDI3,BC loop; LWZ7,r13-7000(image first
word iOSP), LWZ8,r13-6ff4(initial BSS zero), STW3,r13-6ff4(own count),
LWZ9,r13-6ff4,STW7/r8/r9 to output+0/+4/+8,ORI9->10 with100. Four pairs
counts17+round*3+i*14. Budgets8 for(round1,owner),(round2,peer),128 otherwise.
Expected44/72,-2/78,56/-2,62/90. Success2*N+10steps/CIA10030/r3=N/CTR0,
r7=694f5350/r8=0/r9=N/r10=N|100, output12bytes image/zero/count. Limited
8steps/CIA10008/r3=3/CTR=N-3, all TLS-tail registers/outputs/BSS untouched.

Owner native worker starts with constructor TLS0 and invokes EXACT existing
armsx3_ios_ppu_probe_tls_and_call(P32 bootstrap, unchanged). It initializes
production global pool metadata once and main slot through real allocator,
retaining existing dirty/free/reuse tests for slots1/2. New patch0047 changes
ONLY sys_ppu_thread_.cpp, appending iOS-only helpers before existing endif:
- ios_probe_tls_pair_owner requires stopped/current owner, live count1,
  owner stack30000/8000, pool50000, r13=57060, exact image20080/file9/zero55/
  size70/area50030/max metadata, map0 active, whole pool readable/writable.
- armsx3_ios_ppu_probe_alloc_peer_tls requires map1/map2 free, temporarily
  unlocks owner and calls REAL ppu_alloc_tls. Exact slot500a0 gives r13570d0;
  unexpected allocation is freed and rejected. No algorithm changes.
- armsx3_ios_ppu_probe_free_peer_tls requires owner guard, exact570d0,
  map1 active/map2free (therefore only after peer retirement/live count1),
  unlocks owner and calls REAL ppu_free_tls; verifies map1free.
Owner creates its peer INSIDE the owned bootstrap callback, passes peerTLS
through real ppu_thread_params::tls_addr (explicit vm::addr_t enum cast),
checks constructor r13/unique ID, and starts native peer callback. Peer
publishes ready and waits release/cancel; owner requires both live at gate
and rejects active-peer slot free, releases gate and both run bounded guest
code. Guest runner reads/writes only own context; snapshots14values include
stack/r2/r3/count/output/r7-r10/r13/CTR/CIA/LR/gpr30 and own CPU/thread TLS.
Peer unlocks VM, sets exit, then publishes completed. Owner unlocks its VM
passive lock BEFORE waiting/joining peer. PeerCleanup cancels/wakes/joins on
unwind, also starts constructed-but-unlaunched peers with exit, then frees
peer slot while owner pool still alive. Normal path fully joins peer BEFORE
pool/guest comparisons or free. Whole256KiB TLS pool normal/super aliases
must match: images at60/d0/140, system areas/zero BSS/guards untouched except
successful owner/peer count words at6c/dc. Slot pointers remain57060/570d0.
Invalid pool/unallocated/duplicate/active-peer/double-free guards checked.
Explicit slot free succeeds, then free again rejects; guard release skipped
once token cleared. Returning existing wrapper frees main slot/global map/
metadata/pool and restores owner r13=0. Outer owner callback then exits and
publishes final completion; main joins before checking snapshots/whole guest
CODE/DATA/stacks/cache/unmapped TLS pages and counterscreated/deleted+2/live0.
Four pairs reconstruct8native workers, independently restore whole TLS pool
per pair. Callback storage is declared BEFORE StopOwner, ensuring it outlives
join on timeout/unwind. Thread-local construction IDs restore in both host
main and owner CPU; no shared metadata mutation while peer runs. Segment
cache release precedes four guest deallocations/VM close; config restored.

Validation passed:
- test_p52_fixture.py independently encodes all12words including signed
  r13 offsets and source-first ORI, interleaves two scalar guest contexts
  against one shared pool/data address space, compares exact results/PCs/
  partial registers/all pool/data bytes for either budget stop. P43-P51
  hashes/fixtures retained. P51 fixture extraction now bounds its own exact
  function (old count-to-EOF included later diagnostics); P51 source unchanged.
- test_p52_pair.py extracts EXACT full P52 phase and production TLS globals,
  ppu_alloc_tls/free/initialize/old wrapper/new pair guards/helpers plus exact
  exec_task/probe/bounded helper. p52_host_shims.cpp models native std::thread
  command workers, VM/flags/decoder/scalar PPU ops; vm::addr_t is actual-like
  enum, constructor consumes TLS param, id_manager::g_id is thread_local.
  Eight full repetitions32host pairs/64workers, instruction yields; every
  worker checks own probe cleared and construction ID restored at exit.
  All exact4pair results, TLS/image/BSS/slots/snapshots/pool/guest aliases/
  counts/config/maps pass. Corrupt load/data/code/peer TLS BSS/constructor r13,
  owner/peer/midphase queue publication, gate cancellation, instruction throw,
  peer constructor failure, all5allocations (including TLS pool), stopped/
  slot/FXO guards return error and join/free/close/restore. Independently call
  exact slot helpers inside exact old bootstrap with null/wrong-current/
  wrong-pool/duplicate/wrong-pointer/live-peer/double-free guards and unchanged
  whole-pool bytes. G++C++20 Wall/Wextra/Werror ASAN/UBSAN detect_leaks=0 PASS.
  VM/queue/CPU lifecycle/instruction operations/passive-lock behavior are host
  shims; actual native operations/new iOS phase remain pending device test.
- ALL47patches check/apply/reverse/check pinned upstream92b931b9fb5eef7f1317
  cb482917dfc19aceebd9, exact staging/restored bytes, pinned P43 EOF regression
  pass. Plist72/workflow P52 fixture/UI51 uniqueP2-P52 symbols/prefix/whitespace
  pass. No local Xcode SDK; iOS compile/link/device P52 pending.

Baseline main9608059f0a4c2292634b0d1ff2cd2ebd3a63ac84. Push build72 main;
user observes Actions completion. DO NOT monitor Actions after push.
Install ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, run all51diagnostics
and send startup log. No P53 until phone P52 PASS. Full sys_initialize_tls
process mutex/HLE initialization, global process/LV2 scheduler admission/
context switches/firmware/RSX/game boot remain UNTESTED. Earlier P39-P49
scheduler peers remain unexecuted. No images requested or generated.

## 2026-10-11 — build72 phone PASS; build73 adds P53 persistent guest TLS

User supplied ARMSX3-startup-20261011-153907-336-4396.txt and Lets goo.
Library idlibfile_b6cc7b126a208191b02e5a10ee756337; scratch ../upload same
filename. Build72 ALL51 P2-P52 AUTO PASS plus final all-stages PASS; no
AUTO FAIL. P52 native four pairs44/72,-2/78,56/-2,62/90 passed: owner/
peer production TLS57060/570d0, guest image/zero BSS and isolated writes,
either budget stop, full aliases/guards and two joins. This newly confirms
native paired TLS memory/constructor-slot execution, not full TLS HLE
process mutex initialization or LV2 scheduler/context switching.

Build73 adds armsx3_core_test_persistent_guest_tls/UI P53 Persistent guest
TLS and budget recovery. Previous1424452byte Bridge prefix byte-exact.
No source patch added or changed: all47patches retain build72 validation.
Combines P51 persistent command-queue reuse with P52 real owner TLS bootstrap,
peer slot allocation/constructor TLS and join-before-free. Exactly TWO
workers constructed once, owner callback remains inside one existing
production owned TLS bootstrap, peer remains alive for eight notified
queued jobs and one queued exit. Exactly one pool and slot per worker
throughout all16guest jobs. Owner creates peer inside its callback and
unlocks VM before waiting/joining; RAII cancel/wake/launch-unstarted/join
retires peer before slot/global pool cleanup, including errors. Callback
storage declared before owner StopOwner so it outlives every join.

Shared13opcodes52bytes retain P52 loop/image read, read own previous TLS
BSS via r13-6ff4, ADD that value into count, store/read back own new total,
store image/previous/total to separate DATA output, ORI9->10with100. Core
PPUOpcodes.h exposes no ADD encoder: encode X-form manually as
(31<<26)|(3<<21)|(3<<16)|(8<<11)|(266<<1)=7c634214, as older phases encode
unexposed helpers. No invented ADD call in final Bridge/host shim. TLS
pointers57060/570d0 untouched between jobs, normal image/system/unused
BSS/whole256KiB pool guards and both aliases compare every batch. Outputs
DATA20100+round*40+i*20 are disjoint12-byte slots with earlier outputs
retained and untouched limited slots. Full64KiB DATA and super alias
compared every batch; full CODE/both stacks/cache/aliases after final joins.

Counts17+round*3+i*14, budget8 for(round%4==1,owner) or(round%4==2,peer),
128 otherwise. Exact results45/73,-2/79,57/-2,63/91,69/97,-2/103,81/-2,
87/115. Per-batch totals17/31,17/65,40/65,66/105,95/148,95/194,130/194,
168/246. Success2*N+11steps/CIA10034/r3/r9=total,r7=694f5350,r8=previous,
r10=total|100,CTR0. Limited8steps/CIA10008/r3=3/CTR=N-3, TLS value and all
tail registers/output slots unchanged. Each limited worker later recovers
on same CPU/slot at(round,index)=(2,0),(3,1),(6,0),(7,1). Runner resets only
its own live inputs/registers/PC/CTR, records14-register/CPU TLS snapshot,
no syscalls/interrupt/exit. Host owner compares peer snapshot after exact
release/acquire completed count round+1; never reads peer live registers
until final join. Callback has no Program/guest access after publication.
Owner inputs republished after previous peer completion and native queue
publication. Gate uses monotonic released rounds; ready/completed require
exact round+1. Queue-wait aggregate counter grows each job (peer is the
only CPU returning to an empty queue); both live/created+2/deleted baseline
are required each batch, proving no recreation. Allocation/free while
peer live reject without mutation. After batch8, real queued peer exit
executes once, owner unlocks and joins before slot free/double-free guard.
Existing bootstrap then frees main slot/maps/globals/pool and restores
owner r13=0; owner exits/publishes, main joins. Final totals168/246/result87/
batches8 and CPUcreated/deleted+2/live0 required; TLS pages all unmapped,
segment cache released before four guest deallocations/VM close. Config
and thread-local construction IDs restored.

Validation passed:
- test_p53_fixture.py independently encodes13words including ADD fields,
  signed r13 offsets and ORI direction; retains two scalar contexts and
  shared pool/data through eight interleaved batches. Independently checks
  every result/PC/steps/register, previous/total, whole pool/data bytes,
  limited untouched state, four recoveries and exact accumulated history.
  P43-P52 fixture/hash checks retained; CI prepatch invokes P53.
- test_p53_pair.py extracts EXACT full P53 phase and unchanged production
  TLS globals/allocator/free/bootstrap/peer guards plus probe/exec_task/
  bounded helper. p53_host_shims.cpp models persistent std::thread workers,
  mutex/CV queues, strict vm::addr_t enum, thread-local IDs, flags/VM/scalar
  instructions. Eight repetitions16host workers/128guest jobs; constructor
  count2 and callback/queue publications10 per run (owner callback +8peer
  jobs +1peer exit). Guest instruction yields interleave workers; every
  callback/exit asserts its own production probe cleared/ID restored.
  Exact eight batch logs/results, totals, snapshots/TLS/guards/aliases/maps/
  config/counters pass. Corrupt load/data/code/peer BSS/constructor r13,
  initial/midbatch/queued-exit publication error, dropped third peer job,
  active-gate cancellation, instruction throw, peer constructor failure,
  all5allocations (including pool) and stopped/slot/FXO guards all error
  with balanced joins, maps/probe/TLS globals cleared and config/IDs restored.
  Also retains independent exact helper null/wrong-current/pool/pointer/
  duplicate/live-peer/double-free/unchanged-byte guards from P52. G++C++20
  Wall/Wextra/Werror ASAN/UBSAN detect_leaks=0 PASS. VM/queue/CPU lifecycle/
  passive-lock/native PPU operations are host shims; native iOS phase pending.
- Old prefix/plist73/YAML workflow/UI52 uniqueP2-P53 symbols/whitespace pass.
  No source patch changed; previous full47patch chain check/apply/reverse/
  pinned EOF and byte identity validation remains valid. No local Xcode SDK:
  native iOS compile/link/device P53 pending.

Baseline main3e3eae74c55f367ed3c8d7caaf569425fc0a4a80. Push build73 main;
user observes Actions completion. DO NOT monitor Actions after push.
Install ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, run all52diagnostics
and send startup log. No P54 until phone P53 PASS. Full TLS HLE process
mutex/global process/LV2 scheduler admission/context switches/firmware/RSX/
game boot remain UNTESTED. Earlier P39-P49 scheduler peers remain unexecuted.
No images requested or generated.

## 2026-10-11 — build 74 / P54 exact paused guest continuations

Latest phone evidence: upload/ARMSX3-startup-20261011-160344-645-4641.txt
(build73, pid4641; Library libfile_787dca4ff5ec8191b6c7c7aea13b5c8d,
attachment file_00000000615082109da1d08fa65cf419). ALL52 P2-P53 AUTO PASS,
final all-stages PASS, no AUTO FAIL. Native P53 same owner/peer workers and
production slots57060/570d0 survive eight pairs; expected results
45/73,-2/79,57/-2,63/91,69/97,-2/103,81/-2,87/115 and retained totals168/246.
Four budget stops leave prior TLS/output intact and later transactions
recover. P53 completes about0.0024sec; cleanup/aliases/cache/joins pass.

P54/build74 implements armsx3_core_test_resumed_guest_tls, UI54 "Paused
guest contexts and exact continuation"; 53 diagnostics P2-P54. Plist74.
Appends330lines/25370bytes to CoreBridge.cpp, preserving every byte of
build73's1448080-byte prefix. Existing47 upstream overlay patches unchanged.

Meaningful new distinction: P53 initialized registers/CIA for each new job;
P54 initializes only at the start of a transaction, then resumes the SAME
live context at its exact paused CIA on all later bounded calls. Uses
unchanged shared13-word/52-byte guest code with real decoded LI/MTCTR/
ADDI/BC/LWZ/ADD/STW/ORI. No invented ADD encoder; manual X-form retained.
Exactly TWO native workers and ONE production TLS pool/slot pair persist.
Owner stays inside existing stopped diagnostic TLS wrapper, constructs the
peer with its real allocated TLS pointer; notified peer command queue
returns to a real empty-queue wait after each slice. No LV2 admission.

Three paired transactions; counts17/31,20/34,23/37. Each has nine bounded
slices PER worker. Budgets:3,5,2*N-6,2,1,1,1,3,4. Exact CIA offsets after
each:12,8,16,24,28,32,36,48,52. First eight return-2, final returns1.
- First pause: LI/MTCTR/one ADDI complete, r3=1, CTR=N, pending BC at+12.
- Next pause: r3=3, CTR=N-3, back at loop ADDI+8.
- Loop completion: r3=N, CTR0 at+16, TLS/output still unchanged.
- TLS image/previous value read: r7='iOSP', r8=previous total, CIA+24.
- ADD: r3=previous+N at+28, TLS still previous.
- TLS STW: own total committed at+32; output still sentinel.
- TLS reread: r9=total at+36; output still sentinel.
- Three output STWs: image/previous/total written, CIA+48, r10 sentinel.
- Final ORI: r10=total|0x100, CIA+52, positive1 result.
Final paired totals17/31,37/65,60/102. Each TLS cell written exactly once
per transaction, all18 output words written once, old transaction outputs
retained. There are54 bounded dispatches and48 budget stops per phase.

Every invocation snapshots all32 GPRs+CTR/LR/CIA after dispatch. For any
resume, compares the current snapshot against that prior snapshot BEFORE
any register write or execution; mismatch returns-8 and fails phase.
Only slice0 initializes inputs/CIA/CTR/LR. Expected14 live registers and
native CPU/thread TLS checked at every slice, along with result and clean
syscall/interrupt/exit state. Whole256KiB TLS pool normal/super aliases and
64KiB DATA aliases verified at every slice (including untouched system/BSS/
unused slots and output guards); full CODE/stacks/cache verified afterjoin.

Exactly27 retained peer jobs+one queued exit; one owner callback, total29
queue publications/callbacks. Aggregate real queue wait grows every job;
live2/created baseline+2/deleted baseline invariant throughout. Existing
active-peer/duplicate/double-free guards retained. Completion release is
peer's final Program/memory access; owner waits acquire before editing
jobs/reading guest bytes. Queue ordinal transaction*9+slice+1; final slice
count27/batches3/result1 required. Peer joins before production slot free,
existing wrapper restores owner r13=0 and clears TLS globals/map/pool;
owner joins before segment decommit/guest dealloc/VM close. All unwind
lifetime/cancellation/unstarted-worker/join guards retained from P53.

Validation PASS:
- test_p54_fixture.py independently encodes the guest instructions and runs
  a separate scalar shared-memory oracle, retaining both contexts across
  all slices and interleaving one instruction per worker. Exact PC/CTR/
  registers/step counts and full bytes checked at every boundary. Total
 390 executed instructions,48 stops,six TLS stores and18 one-time output
  stores, final60/102. P43-P53 hash/fixture regressions retained; workflow
  prepatch now invokes P54 fixture.
- test_p54_pair.py extracts exact full P54 phase, production probe/
  exec_task/bounded helper and production TLS globals/bootstrap/alloc/free/
  paired guards. Reuses checked-in p53_host_shims.cpp with explicit P54
  queued-exit fault ordinal29, instruction/store counters and paused-state
  corruption hooks. G++ C++20 Wall/Wextra/Werror pthread ASAN+UBSAN
  (ASAN_OPTIONS=detect_leaks=0): eight runs,16 persistent host workers,
 432 bounded slices. Per run390instructions/six TLS stores/18 output
  stores,29 callbacks/publications,two constructions/joins. Injected
  unused GPR31/CIA/CTR/r13 drift between peer callbacks all detected.
  Prior corrupt load/data/code/peer BSS/constructor r13, initial/midjob/
  exit queue publication errors, dropped job, gate cancellation,
  instruction/constructor exceptions, allfive allocation failures and
  stopped/two-slot/FXO guards return-1 with balanced counts/joins,
  cleared maps/probe/TLS globals and restored config/IDs. Independent
  null/wrong-current/pool/pointer/duplicate/live/double-free helpers pass.
  VM/flags/queue/CPU construction/lifecycle/native instruction handlers are
  HOST SHIMS, not a native iOS build or native PPU execution result.
- Old1448080-byte Bridge prefix, all53 unique UI/exported symbols,
  plist74/YAML fixture54 and git whitespace checks PASS. No upstream
  source or patch changed; build72 full47patch-chain check/apply/reverse/
  pinned EOF/byte identity validation remains applicable. No localXcodeSDK.

Baseline main aed3f4f91fb4d158f6c98d6d703041cabb15f3f8. Push build74 main;
user observes build completion. DO NOT monitor Actions after push.
Install ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, run all53diagnostics
and send startup log. No P55 until phone P54 PASS. Actual LV2 scheduler
admission/context switching/full TLS HLE process mutex/global process/
firmware/RSX/game boot remain UNTESTED. P54 proves bounded diagnostic
continuation; it does not exercise native LV2 scheduling. Earlier P39-P49
scheduler peer contexts remain unexecuted. No images requested/generated.

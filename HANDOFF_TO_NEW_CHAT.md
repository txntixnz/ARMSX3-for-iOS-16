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

## 2026-10-11 — build 75 / P55 nested guest calls and paused stack frames

Latest phone log: upload/ARMSX3-startup-20261011-162826-429-4869.txt
(build 74, pid4869; Library libfile_a0c5f10729688191acaa7873ade45de0,
attachment file_00000000f5d88210b7c7a6aa6f3d773d). All 53 P2–P54 AUTO PASS,
final all-stages PASS, no AUTO FAIL. Native P54's six guest transactions
resume across 54 bounded dispatches and 48 budget stops, including after
TLS commit and before output. Same workers and slots survive, exact final
totals 60/102, queue waits/exit, full aliases/cache and joins pass. P54
native duration about 0.0025 sec. This authorizes the next milestone.

P55/build75 adds armsx3_core_test_resumed_guest_calls and UI55 "Nested guest
calls and paused stack frames". Now 54 diagnostics P2–P55. Plist75; CI
prepatch invokes test_p55_fixture.py. Appends 364 lines / 28411 bytes to
CoreBridge.cpp, preserving build74's entire 1473450-byte prefix. No changes
to upstream sources or the existing 47 overlay patches.

New guest code: 41 words / 164 bytes, golden SHA1
9aadb16d728d2d8dc13b7ff5e7a5873bb533e4f6. Caller at CODE+0, framed callee
at +64, loop leaf at +144. Calls use native B(displacement,false,true),
returns use BLR; MFLR/STDU/STD/LD/ADDI/MTLR save and restore LR/rTOC and
stack frames. Caller B at+16 links LR=CODE+20 and targets+64; callee B
at+84 links LR=CODE+88 and targets+144. Main B at+44 targets END+164.
All guest control flow stays in the diagnostic bounded range. ADD still
uses the manual X-form (the core has no ADD encoder). Newly used native
encoders confirmed present in staged PPUOpcodes.h; host encoder support
is explicitly a shim, independent fixture checks all 41 literal words.

Exactly two native workers and one real production TLS pool/slot pair
persist for three paired transactions. Counts 17/31,20/34,23/37 and totals
17/31,37/65,60/102. Each transaction has twelve bounded slices per worker:

| Slice (zero-based) | Budget | CIA offset after | Expected boundary |
| --- | --- | --- | --- |
| 0 | 4 | 16 | Caller frame/backchain/LR/rTOC saved; SP-128 |
| 1 | 7 | 144 | Callee frame saved; rTOC=0x2468; LR=CODE+88; SP-256 |
| 2 | 3 | 156 | Leaf LI/MTCTR/ADDI; r3=1, CTR=N, next BC |
| 3 | 5 | 152 | Leaf r3=3, CTR=N-3, next ADDI |
| 4 | 2*N-6 | 160 | Loop complete; r3=N, CTR=0, leaf return pending |
| 5 | 3 | 96 | Leaf BLR returns; TLS image and previous total read |
| 6 | 2 | 104 | ADD and TLS commit; output still untouched |
| 7 | 2 | 112 | Image/previous output words written; total still sentinel |
| 8 | 5 | 20 | Callee reloads LR/rTOC and returns; SP-128 |
| 9 | 3 | 32 | Caller total output written and original LR reloaded |
| 10 | 2 | 40 | Initial SP/LR restored; final ORI pending |
| 11 | 8 | 164 | ORI and end branch complete; positive result 2 |

First eleven calls per transaction return -2, final returns 2. Thus 72
bounded dispatches and 66 pauses per phase. Each guest transaction executes
2*N+32 instructions, for 516 total; six TLS stores, 18 output-word stores,
36 stack-word stores, 12 linked calls and 12 BLR returns. Cold inputs set
once per transaction; all resumes compare all 32 GPRs+CTR/LR/CIA against
prior snapshots before any write or dispatch. Caller stack pointer starts
37f90/47f90; never reset by the runner, so guest code must restore it for
later transactions. Expected 15 registers additionally include r0, exact
SP/rTOC/LR during calls and restoration. No guest syscalls/interrupts/exit.

Both entire 64KiB stack pages start with a5 canaries. Guest writes two
128-byte frames each: first backchain=initial SP, saved LR=12340000 and
rTOC=13579000; second backchain=initial SP-128, saved LR=CODE+20, saved
rTOC=13579000. Expected stack images update only those six 64-bit words.
Whole normal/super stack aliases checked at EVERY slice, along with entire
TLS pool and DATA images, so saved return values, partial outputs, unused
bytes and cross-worker writes are checked while calls are still paused.
Callee deliberately changes r2 to2468 and restores it from its own stack;
caller restores its saved r2 too. Final SP/LR/rTOC must match original.

Existing owner/peer lifetime and cleanup from P54 retained. 36 notified
peer jobs plus queued exit, one owner callback: 38 queue publications and
callbacks, exactly two constructions/joins. Queue ordinal transaction*12+
slice+1, growing empty-queue wait counter and live2/created+2/deleted
baseline checked throughout. Completion release remains peer's last
Program/memory access; owner acquire waits before mutation/readback.
Final slices36/batches3/result2/totals60/102. Peer joins before real TLS
slot free; bootstrap clears pool/map/globals and restores owner r13=0;
owner joins before segment decommit, guest deallocations and VM close.
Cancellation, callbacks-before-guards lifetime, unstarted-worker retirement,
config restoration, allocation/free/duplicate/live/double-free guards retained.

Validation passed:
- test_p55_fixture.py independently encodes all 41 words and runs separate
  interleaved scalar contexts with big-endian 32/64-bit shared memory and
  retained stacks. Every paused PC/SP/LR/rTOC/CTR/register, partial TLS/
  DATA/stack byte and exact slice step count checked. Counts 516 instructions,
  66 stops,36 stack stores,6 TLS stores,18 output stores,12 calls/returns;
  final60/102 and initial SP/LR/rTOC. Transitive P43–P54 fixture/hash checks
  pass unchanged.
- test_p55_pair.py extracts exact P55 phase, production bounded probe/
  exec_task/helper and TLS globals/bootstrap/allocator/free/paired guards.
  Reuses unchanged p53_host_shims.cpp with explicit P55 fault ordinal38,
  64-bit big-endian stack words and fixture-specific scalar call/return/
  stack instructions. G++ C++20 Wall/Wextra/Werror pthread ASAN+UBSAN,
  ASAN_OPTIONS=detect_leaks=0 passed eight repetitions: 16 retained host
  workers,576 slices, exact counters/logs and two joins per phase.
  Injected saved LR/rTOC/backchain/stack guard corruption, bad LD/SP/
  linked branch/BLR plus paused GPR31/CIA/CTR/r13 drift all detected.
  Prior corrupt load/DATA/CODE/peer BSS/constructor r13, initial/midjob/
  queued-exit publication failure, dropped job, gate cancellation,
  instruction/constructor throw, all five allocations and stopped/PPU-slot/
  FXO guards return -1 with balanced joins/counts, cleared maps/probe/TLS
  globals and restored config/IDs. Exact independent null/wrong-current/
  pool/pointer/duplicate/live/double-free TLS guards retained and passed.
  Native CPU/flags/VM/queue/PPU operations are HOST SHIMS; this is not a
  native iOS build or device result. Native P55 is pending the next phone log.
- Entire prior 1473450-byte Bridge prefix, 54 unique UI/exported symbols,
  plist75, YAML/CI fixture55, unchanged47patches and whitespace pass.
  No upstream source/patch changed; prior full47patch-chain check/apply/
  reverse/pinned EOF/byte identity validation remains applicable.
  No local Xcode SDK; no claimed native iOS compile/link result.

Baseline main731de7738dcf80fe7f12f2ef1a2990f5e0856293. Push build75 main;
user observes build completion. DO NOT monitor Actions after push.
Install ARMSX3_iOS16_INSTALL_THIS_IPA with TrollStore, run all54 diagnostics,
and send startup log. No P56 until phone P55 PASS. Actual LV2 scheduling/
context switches/full TLS HLE process mutex/global process/firmware/RSX/
game boot remain UNTESTED. This phase proves bounded guest calls and stack
continuation, not actual LV2 scheduling. P39–P49 scheduler peer contexts
remain unexecuted. No images requested/generated.

## 2026-10-11 — build 76 / P56 paused floating-point and vector guest calls

Newest phone evidence: upload/ARMSX3-startup-20261011-165241-768-5063.txt
(build75, pid5063; Library libfile_f5ce5e1901608191861e806eded1f6be,
attachment file_00000000e19481f481a579fdbd174622). All54 P2–P55 AUTO PASS,
final all-stages PASS, no AUTO FAIL. P55's six nested caller/callee/leaf
transactions complete 72 dispatches/66 pauses, exact stack/SP/LR/rTOC,
results2/2 for each pair and TLS totals17/31,37/65,60/102. Full aliases/
cache and join/cleanup pass. Native P55 about0.0029 sec. Next stage authorized.

User "Continue this task" while P56 validation was in progress: continue
same ARMSX3 objective. Build76 adds armsx3_core_test_resumed_guest_simd,
UI56 "Paused floating-point and vector guest calls": 55 diagnostics P2–P56.
Plist76; CI fixture56. Appends425lines/33013bytes to CoreBridge.cpp while
retaining the exact entire build75 prefix1501861bytes. No changes to
upstream sources or the47 overlay patches. No image artifact requested by
actual task text; none generated (tool-selection hint had image_gen, but
startup text/log continuation is the active task; user has opposed
unsolicited images in earlier emulator tasks).

New milestone adds native PPU LFD/FADD/STFD and LVX/VXOR/STVX to P55's
nested guest calls, with real production TLS slots and two persistent
native PPU workers. Shared49words/196bytes, SHA1
0b455429814787413fabaf02c87bf75e18214e58. Caller+0/callee+64/leaf+144 stay
unchanged; main end branch at+44 now B(152) to+196. Leaf loop ends at+160,
then two LFDs at160/164, FADD168, STFD172, LVXs176/180, VXOR184, STVX188,
BLR192. Native PPUOpcodes.h exposes LFD/STFD/LVX/STVX; no FADD/VXOR
encoders, so explicit A-form FADD wordfc61102a and VXOR106114c4 used.
Staged real interpreter semantics and decoder entries inspected; ADD's
manual X-form retained. Exact literal words/manual definitions checked
by independent fixture. Native code and native handlers are not compiled
locally (no Xcode SDK); device P56 result pending.

Each of three paired transactions has18 slices per worker: 108 bounded
calls and102 budget stops. Budgets:
4,7,3,5,2*N-6,2,1,1,2,1,1,3,2,2,5,3,2,8.
Exact paused CIA offsets:
16,144,156,152,160,168,172,176,184,188,192,96,104,112,20,32,40,196.
First17 slices return-2, final returns2. Calls2*N+40 instructions,
564 total per phase. Added six FADDs/six STFDs/six VXORs/six STVXs and
12 LFDs/12 LVXs; same36 stack stores/12 linked calls/12 BLR returns/
six TLS stores/18 integer output stores. TLS counts and final totals
remain17/31,37/65,60/102. Native LV2 scheduling is still NOT exercised.

For each worker/transaction, output slot=20200+transaction*100+worker*80.
Initial outputs and gaps are a5. Integer image/previous/total at0/4/8;
FP result8bytes at+16; vector result16bytes at+32; inputs at+64,+72,
vector A+80/vector B+96. Entire slot128bytes leaves guards and previous
outputs intact. DATA initialized once before workers, copies TLS image
at20080. Double inputs left=1.5+transaction*0.5+worker*2.0 and
right=2.25+transaction*0.25+worker*4.0, sums3.75/9.75,4.5/10.5,5.25/11.25;
all exactly representable. Native byte outputs checked big-endian via
bit_cast<u64>/be_t<u64>. Vectors use distinct nonuniform byte patterns:
A=10+transaction*17+worker*53+byte*3,
B=e1-transaction*11-worker*29-byte*5 (mod256); expected bytewise XOR.
This validates vector endian conversion/lane order as well as computation.

Cold initialization only at transaction slice0: all32 FPRs=7.0, all32
VRs raw3c canaries; r5=80,r11=96,r12=32 for indexed vector access. Later
callbacks resume with no resets. Full prior GPR+CTR/LR/CIA snapshot and
256raw FPR bytes/512raw VR bytes compared BEFORE any dispatch or write.
After dispatch, all32 FPR bit patterns checked against their exact stage
values and unchanged7.0 canaries. VR1/2/3 canonically serialized through
real be_t<v128> and checked against loaded/computed vectors; every byte
of the remaining29 VRs must retain3c. Floating/vector register snapshots
refreshed only after dispatch. FPSCR/CR/XER/general FP edge cases are
not part of this phase; do not claim complete architectural state validation.

Slice5: both FPR inputs loaded, f3 still7.0, FP output untouched.
Slice6: FADD result retained, output untouched.
Slice7: STFD output committed; vectors still3c.
Slice8: both vectors loaded, v3 still3c, vector output untouched.
Slice9: VXOR retained, output untouched.
Slice10: STVX committed. Slice11 returns leaf and loads TLS image/previous;
12 TLS commit;13 first two integer output words;14 callee epilogue/return;
15 caller total output/LR load;16 restores original SP/LR;17 completes.
All64KiB stack normal/super images (two128byte frames each), whole256KiB
TLS pool, DATA aliases, guards/unused slots/old outputs checked every
slice. Full CODE/data/stacks/cache and deallocation verified after joins.

Owner/peer lifetime and cleanup inherited from phone-proven P55.54 peer
jobs+queued exit+owner callback=56 publications/callbacks, exactly two
constructions/joins. Gate ordinaltransaction*18+slice+1; real empty queue
wait counter grows with live2/created+2/deleted baseline invariant. Peer
completion remains final Program/guest memory access; release/acquire
wait before owner edits/reads. Final slices54/batches3/result2/totals60/102.
Peer joins before slot free; bootstrap resets owner r13/map/TLS globals/
pool, owner joins before cache decommit/guest frees/VM close; all unwind
cancel/unstarted-worker/join/config/thread-local-ID guards retained.

Validation PASS:
- test_p56_fixture.py independently encodes49 literal words/manual fields,
  executes separate interleaved scalar GPR/FPR/canonical VR contexts with
  retained stacks/TLS/data through all108 slices. Exact PC/CTR/LR/SP/rTOC,
  every FPR/vector byte/canary, deferred store and full memory image;
  564 instructions/102 stops, all operation/store/call counts, final60/102.
  P43–P55 hash/fixture regressions retained; CI prepatch invokes P56.
- test_p56_pair.py extracts exact full P56 bridge and production bounded
  probe/exec_task/helper, TLS globals/bootstrap/alloc/free/paired guards.
  Extends unchanged checked-in p53_host_shims.cpp with explicit phase
  fault ordinal56, double/VR storage and big-endian vector conversion,
  fixture-specific scalar FP/vector operations. Native CPU/VM/flags/
  queue/instruction handlers are HOST SHIMS, not native iOS operations.
  G++ C++20 Wall/Wextra/Werror pthread ASAN+UBSAN detect_leaks=0 PASS:
  eight phases/16 persistent host workers/864 slices, exact56 callback/
  publication count, two joins and operation counts per phase. Corrupted
  paused unused FPR/VR, computed f3/v3 before store, FP load/add/store,
  vector endian/XOR/store, plus all prior register/stack/branch/return/
  CODE/DATA/TLS/constructor/publication/dropped-job/gate/instruction
  faults detected with balanced joins/counts and cleared maps/probe/
  TLS globals/config/IDs. Allfive allocations and stopped/PPU-slot/FXO
  guards, independent null/wrong-current/pool/pointer/duplicate/live/
  double-free TLS guard calls passed. Results saved in scratch logs.
- Exact1501861-byte prior Bridge prefix; all55 unique UI/exports P2–P56,
  plist76/YAML fixture56/unchanged47patches/whitespace PASS. Prior full47
  patch-chain/pinned-EOF check/apply/reverse/byte identity remains valid
  because no upstream source or patch changed. No local Xcode SDK.

Baseline mainec19b0be75277ca6c8bc7190cf3bcc615a92339b. Push build76 main;
user reports build completion. DO NOT monitor Actions after push.
Install ARMSX3_iOS16_INSTALL_THIS_IPA in TrollStore, run all55diagnostics
and send startup log. No P57 until phone P56 PASS. Real LV2 scheduling/
context switches/full TLS HLE process mutex/global process/firmware/RSX/
game boot remain UNTESTED. Earlier P39–P49 scheduler peer contexts remain
unexecuted. No unsolicited pictures.

## 2026-10-11 — build 77 / P57 paused condition, carry and floating status

Newest device evidence: upload/ARMSX3-startup-20261011-182232-268-5528(1).txt,
build76 pid5528; attachment file_00000000eb2882109ef2dbc5aa679213,
Library libfile_d200266440b481918eb0c3e4ee6801ae. Read the scratch copy per
user instruction. All55 P2–P56 AUTO PASS, final all-stages PASS/no AUTO FAIL.
Native P56 finishes about0.0073sec, three results2/2 and TLS totals17/31,
37/65,60/102. Real FP/vector inputs/results/stores, 108 dispatches/102
pauses, all32 GPR/FPR/VR snapshots and nested stack/aliases/cache/lifecycle
checks PASS. No native P57 evidence yet. User's standing "Continue this
task" covers the next incremental build and push; do not monitor Actions.

Build77 appends armsx3_core_test_resumed_guest_status (P57) while preserving
exact entire1534874byte build76 Bridge prefix; appended36867bytes/471lines.
UI "Paused condition, carry and floating status", stagesP2–P57 =56 checks.
Plist77, CI test_p57_fixture.py. No upstream sources or47patches changed.
Shared59words/236bytes SHA1=34666ca12655524b6ffb024c74ecc37795748b58.
Retains P56 caller/callee/leaf stacks, real production TLS slots, persistent
native pair, FP/vector operands/results, and all cleanup guards.

Record-form FADD wordfc61102b now forces native FPCC/FPSCR field4 and CR1
updates regardless of cached interpreter optional set_fpcc setting; real
PPUInterpreter.cpp selection/handler inspected. Positive exact sum gives
FG nibble4 in FPSCR field4 (packedshift12) and CR1 (packedshift24).
PPUThread.h's actual cr.pack/unpack and fpscr.bits.pack/unpack used; XER
serialized explicitly SO31/OV30/CA29/count0..6, avoiding struct padding.
VRSAVE included as unchanged distinct canary. Snapshot four packed status
registers BEFORE every resume together with all GPR/FPR/VR/CTR/LR/CIA.
Only slice0 initializes context; no later callback resets state.

Initial CR=8a6c5e79 xor(transaction<<8) xor(worker<<12),
FPSCR=13579bdf xor(transaction<<20) xor(worker<<24),
XER.SO=!worker, OV=transaction&1, CA=worker, count15+transaction+worker;
VRSAVE=5aa50000|(transaction<<8)|worker. Nonzero unused fields must survive.
After FADD, only expected CR1 and FPSCR FPCC fields change. Initial XER CA
is opposite each later expected carry. Native ADDIC./CMPDI/MFCR/MFSPR/BC
handlers and encoder declarations inspected directly in pinned overlay.
No local native core compile; these inspections don't prove phone results.

Caller end B(+44) still jumps to+196, now new tenword tail:
196 ADDIC. r15,r14,1 (manual35ee0001, no native ADDIC encoder),
200 CMPDI CR7,r15,0;204 MFCR r16 (manual7e000026, no encoder),
208 MFSPR r17,XER (MFSPR(17,32): helper expects encoded swappedSPR bits),
212/216/220 STW r16/r17/r15 to output+48/+52/+56,
224 BC12,30,+8 tests CR7.EQ without altering CTR,
228 LI r18,1111;232 STW r18,output+60;end236.
Owner inputr14=UINT64_MAX ->r15zero/carry1, CR0/CR7 EQ+SO nibble3,
taken BC skips LI and publishes2222. Peer input7+transaction ->r15=8/9/10,
carry0, CR0/CR7 GT nibble4, not-taken BC executes LI/publishes1111.
XER OV/SO/count and all other CR/FPSCR fields retain their distinct values.
Guest MFCR/MFSPR readbacks verified in registers and exact big-endian memory.

Threepaired transactions,24slices eachworker =144 bounded dispatches/
138 budget stops. Budgets4,7,3,5,2*N-6,2,1,1,2,1,1,3,2,2,5,3,2,2,
1,1,2,3,1,4. Offsets16,144,156,152,160,168,172,176,184,188,192,
96,104,112,20,32,40,196,200,204,212,224,(owner232/peer228),236.
First23 return-2, finalowner1/peer2. Slice18 carry/CR0,19 CR7,20 guest
readbacks,21 firstthree status/result stores,22 branch pause on distinct
PCs,23 final branch output. Total621 instructions, six ADDIC./CMPDI/MFCR/
MFSPR/conditional tailBC, three taken/three not-taken. Old564instructions
plus3*(owner9+peer10)=621. Six native FADD/STFD/VXOR/STVX,12LFD/LVX,
36stackstores/12calls/12returns, sixTLS stores,42integer output stores.
All full DATA/pool/two64KiB stacks normal+super aliases checked eachslice,
prior transaction outputs/guards and CODE/cache afterjoins retained.
FinalTLS totals60/102,72peerjobs + exit + ownercallback =74queuepubs/
callbacks. Exactlytwo constructed/retired workers and two joins; queued
exit/free-after-peer-retirement/ownerjoin-before-VMclose unchanged.

Validation PASS:
- test_p57_fixture.py independent manual/native-form encoding and literal
  59word list/SHA1; separate interleaved scalar oracle executes all144
  retained contexts/slices with exact CR/XER/FPSCR/VRSAVE/branch PC and
  registers, deferred guest readbacks/stores and whole memory/stack/TLS
  images. 138stops/621steps, totals60/102. P43–P56 fixture regressions PASS.
- test_p57_pair.py extracts exact whole P57, real production exec_task/
  bounded helper and TLS globals/bootstrap/alloc/free/paired guard bodies.
  Reuses unchanged p53_host_shims.cpp with explicit scalar FP/vector/
  condition/carry/readback/branch models. Native CPU/VM/queue/flags and
  instruction handlers are HOST SHIMS, not native iOS execution. G++
  C++20 Wall/Wextra/Werror pthread ASAN+UBSAN detect_leaks0: eight full
  phases/16persistent host workers/1152slices PASS;74callbacks/queuepubs,
 621instructions, all operation counts including three taken/three not-
  taken branches and six of each new status operation PASS.
  Faults2..47: all previous queue/publication/instruction/allocation/TLS/
  constructor/GPR/FPR/VR/stack/branch faults plus paused CR bit, XER CA/SO/
  count, FPSCR unused bit and VRSAVE drift, wrong carry/comparison/branch,
  wrong FPSCR FPCC and MFCR/MFSPR readbacks detected. Balanced joins/counts,
  cleared mappings/probe/TLS globals and restored config/IDs verified.
  Allfive allocations, stopped/PPU slots/FXO guards, independent exact TLS
  null/wrong-current/pool/pointer/duplicate/live/double-free guards PASS.
- Build76 all55 native PASS verified; exact1534874byte prefix, all56 unique
  UI/exported symbols/plist77/workflow/unchanged47patches and whitespace
  PASS. No upstream/patch change, so prior full47patch-chain check/apply/
  reverse/pinned-EOF byte identity remains applicable. No Xcode SDK/native
  compile or native P57 result claimed. Scratch p57-host-check.log and
  p57-fixture-check.log contain successful validation output.

Baseline main9150707638ec78a7511d5ab6bb7cc648bf71d163. Push build77 main;
user reports build completion, DO NOT query Actions afterpush. Install
ARMSX3_iOS16_INSTALL_THIS_IPA in TrollStore, run all56diagnostics, send
startup log. No P58 until native phone P57 PASS. This tests specific exact
integer/positive-double architectural state, not all FP exceptions/rounding,
vector status/reservations/full architectural context nor real LV2 context
switches. LV2 scheduling/full TLS HLE process mutex/global process/firmware/
RSX/game boot remain UNTESTED. P39–P49 scheduler peer contexts remain
unexecuted. No images requested/generated.

## 2026-10-11 — build 78 / P58 guest reservation stores and recovery

Newest device evidence upload/ARMSX3-startup-20261011-184558-532-5663.txt,
build77 pid5663; attachment file_00000000ec348246bee5f6a04a4419af,
Library libfile_0e63ecf663f88191a121fac38c997653. Scratch copy read as instructed.
All56 P2–P57 AUTO PASS, final all-stages PASS/no AUTO FAIL. P57 native
about0.0087sec: three results1/2 with totals17/31,37/65,60/102. Exact
CR/XER/FPSCR/VRSAVE, FADD. FPCC/CR1, ADDIC. carry/CR0, CMPDI CR7,
taken/not-taken branch and MFCR/MFSPR readbacks PASS over144dispatches/
138pauses. All register/stack/aliases/cache/joins clean. P58 phone pending.

Build78 adds armsx3_core_test_guest_reservation_stores; UI58 "Guest
reservation stores and recovery",57diagnostics P2–P58. Plist78, CI fixture58.
Appends41097bytes/515lines to exact entire1571741byte build77 Bridge prefix.
No upstream sources or47patches changed. Native LWARX/STWCX interpreter
handlers and production ppu_load_acquire_reservation/ppu_store_reservation
helpers inspected directly in staged pinned core; actual CR0 store result
and reservation clearing/success/failure paths confirmed. No local Xcode
SDK/native compile. Host tests use explicit scalar reservation shims.

Extends P57's exact guest program with fourteen atomic-tail instructions;
73words/292bytes SHA1=7a92d9b84469c6c65b84c3814ff9a89614a1ca06.
Native PPUOpcodes.h has no LWARX/STWCX/MFCR encoders. Small explicit manual
X-form lambdas use main31, XO20 for LWARX, XO150/RC1 for STWCX., XO19 for
MFCR. ra0 and indexedr19 address (rb19) for all reserved accesses. Independent
fixture literal words plus exact lambda source/bit-field checks protect
encodings. All prior native FP/vector/carry/branch/TLS/stack instructions
and outputs retained.

Each worker/transaction owns separate128byte-aligned reservation line:
21000+transaction*100+worker*80, no contended addresses. Its initial word
11223300+transaction*10+worker, neighbors/all other DATA bytesa5.
r19address, r21firstWord=a1b20000+transaction*100+worker*10,
r26secondWord=c3d40000+transaction*100+worker*10. New r20/r22/r23/r24/
r25/r27 distinct dead00xx canaries until guest loads/readbacks change them.
Only slice0 initializes these inputs. Initial context reservation must
be absent (raddr0); each dispatch and every resume verifies raddr0.
No reservation is deliberately carried across a pause or native queue wait.

Atomic tail PCs:
236 STWCX. r21,0,r19 without reservation (FAIL/no write),
240 MFCR r22;244 STW r22,output112;
248 LWARX r20,0,r19;252 STWCX. r21,0,r19 (SUCCESS firstWord);
256 MFCR r23;260 STW r23,output116;
264 STWCX. r21,0,r19 on consumed reservation (FAIL/no write),
268 MFCR r24;272 STW r24,output120;
276 LWARX r25,0,r19;280 STWCX. r26,0,r19 (SUCCESS secondWord);
284 MFCR r27;288 STW r27,output124;end292.
Each LWARX/STWCX pair runs together within ONE bounded dispatch; this first
atomic phase tests missing/consumed rejection and fresh-pair recovery, not
reservation persistence across pauses, invalidation by a peer or retry loops.
STWCX CR0 LT/GT0, EQsuccess, SOretained: ownerSO1 gets nibble1failure/
3success; peerSO0 gets0failure/2success. CR1/CR7/otherfields retain P57
state. Guest MFCR readbacks preserve full packed CR at each result. Other
XER/FPSCR/VRSAVE bits are unchanged. r20 loads initialWord; r25 firstWord.
Checks full128byte lines/all DATA aliases, so native 64-bit backing-store
neighbor preservation and big-endian word order are tested, not just a
selected output. Old P57 r16 CR readback must stay unchanged as CR0 changes.

32slices per worker/transaction =>192dispatches/186stops. P57's slice23
budget changes to owner1/peer2 so both pause exactly at236 before tail.
Next slices24..31 budgets1,2,2,2,1,2,2,4; offsets240,248,256,264,268,
276,284,292. First31 return-2, finalboth2. Total705instructions, old621
plus84 new. Perphase12 LWARX,24 STWCX (12successes/12failures),30MFCR
(sixold+24new),66integeroutputstores (42old+24CR stores),12atomicword
writes; old FP/vector/stack/TLS/call/branch counts retained. TLS totals
17/31,37/65,60/102.96peerjobs+queuedexit+owner=98callbacks/queuepubs.
Exactlytwo persistent native workers/constructions/joins. All production
TLS slot guards, release/acquire job completion, real queue wait/lifecycle
checks, peerjoin-before-free/ownerjoin-before-VMclose/cache cleanup and
unwind/config/thread-local-ID restoration inherited unchanged.

Validation PASS:
- test_p58_fixture.py independently encodes73literalwords/manualX forms,
  separate interleaved scalar reservation/context oracle covers192slices/
  186stops/705instructions, missing/consumed/no-write vs twofresh successes,
  exact CR/readback/register state, reserved values and neighboring bytes,
  all full memory/TLS/stack images and prior P43–P57 fixtures/hashes.
- test_p58_pair.py extracts exact entire P58 and production bounded helper/
  exec_task plus real TLS globals/bootstrap/alloc/free/paired guard bodies.
  Reuses unchanged p53_host_shims.cpp with explicit scalar host reservation/
  FP/vector/condition instruction models. G++C++20 Wall/Wextra/Werror pthread
  ASAN+UBSAN detect_leaks0: eightphases/16persistent host workers/1536slices
  PASS; exact98queuepubs/callbacks,705steps,12load/24store/12success/12fail,
  30MFCR/66outputstores and all prior operation/lifecycle counts PASS.
  Faults2..60 cover inherited register/stack/FP/vector/queue/construct/TLS
  failures plus illegal missing/consumed success, rejected valid pair,
  corrupt reserved load, wrong endian/neighbor writes, reservation leak at
  store and nextqueue callback, wrong CR0 SO/MFCR readback, lost first write,
  wrong recovery write and write despitefailed store. Eachreturns-1 with
  balanced joins/counts, cleared maps/probe/TLS globals and config/IDs.
  Allocation1..5/stopped/PPUslots/FXO plus independently called exact TLS
  null/wrong-current/pool/pointer/duplicate/live/double-free guards PASS.
  Initial host harness fault10 wrote word1 at10100, now inside longer code
  (previously unused CODE), causing shim's default assert abort. Updated
  only shim invalid-op path to throw, allowing diagnostic's existing catch/
  unwind validation; reruns pass. This is not a native-core behavior change.
  Native CPU/VM/reservation/queue/flags/instruction handlers remain HOST SHIMS;
  device/native P58 and reservation implementation are NOT locally proven.
- Exact1571741byte prior Bridge prefix,57unique UI/exported stages/plist78/
  CI fixture58/unchanged47patches/gitwhitespace PASS. Previous full47patch
  check/apply/reverse/pinned-EOF byte identity remains applicable because no
  upstream/patch changes. Scratch p58-host-check.log/p58-fixture-check.log.

Baseline main46de03c658d71f5cedb3071f58ccedc8cb01ac7c. Push build78 main,
user reports build completion; DO NOT query Actions afterpush. Install
ARMSX3_iOS16_INSTALL_THIS_IPA in TrollStore, run all57diagnostics/sendlog.
No P59 until native P58 PASS. Contested/shared reservations, cached reuse/
peer invalidation/retry loops/reservation across pauses, true LV2 scheduling/
context switching/full TLS HLE process mutex/global process/firmware/RSX/
game boot remain UNTESTED. No unsolicited images.

## 2026-10-11 — build 79 / P59 paused reservations and ordered peer writes

Device evidence: upload/ARMSX3-startup-20261011-200928-183-6039.txt,
Build78 pid6039; Library libfile_ba001bc471bc8191b653d9b5bab0e4f9.
Read the attached scratch copy as instructed. All57 P2–P58 AUTO PASS,
final all-stages PASS, no AUTO FAIL. P58 completes about0.0050sec,
three results2/2 and TLS totals17/31,37/65,60/102. Native missing/consumed
reservation failures, two fresh-pair successes per worker/transaction,
exact CR readbacks/word endian/neighbor bytes/192dispatches/186pauses,
registers/stacks/TLS/aliases/cache/lifecycle cleanup PASS. Native P59 pending.

Build79 appends armsx3_core_test_paused_reservations, UI P59 "Paused
reservations and peer writes". All58 diagnostics P2–P59. Plist79;
CI prepatch invokes test_p59_fixture.py, which invokes unchanged P58 and
all prior fixture regressions. Entire1612838byte Build78 bridge prefix is
identical; SHA256 c142e042108c4e2de18f0a60c0390a593e4a0b82b48de04b13f2d360993c9ead.
No native-core source,47patches or pinned upstream commit changed.

P59 retains P58's program and all FP/vector/status/nested stack/TLS,
missing/consumed/reservation-recovery and lifecycle checks. Appends14words:
87words/348bytes SHA1 ef4f7a161439689839125c7c60453d3fa6535949.
Per worker/transaction own128byte-aligned line at21000+tx100+worker80;
r31 points to the other worker's line. r28 is reserved-load result, r29
full guest MFCR readback. Separate guarded extra outputs use original
r6+2000/2004/2008, disjoint from original128byte output slots and atomics.

Extra PCs/boundaries (each runs in its own bounded dispatch unless paired
MFCR+STW):292 LWARX r28;296 NOP;300 STWCX r21 SUCCESS;304 MFCR r29,
308 STW successCR;312 LWARX r28;316 STW r26 to peer line;320 STWCX r26
FAIL/no-write;324 MFCR,328 STW failedCR;332 LWARX r28;336 STWCX r26
SUCCESS recovery;340 MFCR,344 STW successCR;end348. Missing/consumed
cases in the old tail still fail and both old fresh pairs still succeed.
Original slice31 budget is now2 rather than4, preventing execution of new
instructions before the pause at292. New slices32..42 budgets1,1,1,2,1,
1,1,2,1,1,2;PCs296,300,304,312,316,320,324,332,336,340,348.

Both workers finish each slice before either starts the next. Thus both
LWARX loads at312 finish before the two peer guest STW writes at316,
and both writes finish before the stale STWCX attempts at320. Each writes
a distinct opposite-worker secondWord, so rejection is deterministic.
After rejection, own memory contains the peer's different word; fresh
LWARX at332 loads that word and the paused STWCX at336 restores own
secondWord successfully. No simultaneous same-address conditional store
race, same-value/ABA invalidation,128byte cross-word invalidation or retry
loop is claimed. Peer callbacks return to the real empty command queue
between every slice; owner stays inside its TLS bootstrap callback.

At slices32/33/36/37/40, expect raddr=ownLine; all other boundaries raddr0.
Before EVERY resume compare all previously checked architectural registers
plus exact raddr/rtime/res_cached/use_full_rdata and all128 raw rdata bytes.
No reservation/context reset after slice0. These fields may naturally
change inside dispatch; their new snapshots are retained across pauses.
Native ppu_load_acquire_reservation/ppu_store_reservation, PPUThread.h
fields and ptr_call/cmd_get queue behavior inspected from pinned core.
Command wait uses thread_ctrl::wait_on rather than ppu_thread::cpu_sleep;
actual LV2 cpu_sleep DOES clear raddr, and this phase does NOT test LV2
scheduling/context switches. No local Xcode SDK/native compile/result.

43slices per worker/transaction=258dispatches/252budget stops/789guest
instructions,30LWARX/42STWCX,24successes/18failures,48MFCR and90integer
stores (includes6 ordinary cross-peer stores). Three transactions maintain
TLS totals17/31,37/65,60/102.129peerjobs+queuedexit+owner callback=
131publications/callbacks. Exactlytwo persistent native workers and two
joins; peer joined before TLS free, owner joined before cache/VM cleanup.
Full CODE/DATA/pool/two64KiB stacks and super aliases checked eachslice,
including previous outputs, neighbor bytes and unused guard space.

Validation PASS:
- test_p59_fixture.py preserves exact frozen Build78 prefix and P43–P58
  regression fixtures. Independently encodes87 literal words/manual X
  forms and runs separate interleaved scalar contexts across258slices/
  252stops/789instructions. Exact PCs/registers/FP/vector/status/stacks,
  paused reservations, peer-induced stale failures and recovery, readbacks,
  full memory/TLS images and all counts PASS. SHA1 above.
- test_p59_pair.py extracts exact P59 plus real production exec_task/
  bounded helper and TLS bootstrap/slot guard bodies from staged pinned
  source with applicable unchanged patches. CPU/VM/reservations/queue/
  instruction handlers are explicit HOST SHIMS, not native operations.
  G++ C++20 Wall/Wextra/Werror pthread ASAN+UBSAN detect_leaks=0 PASS:
  eight full phases/16persistent host workers/2064slices, exact131callbacks/
  queue publications and operation counts per phase. Faults2..74 plus all
  five allocations/stopped/PPU-slot/FXO and independently called exact TLS
  null/wrong-current/pool/pointer/duplicate/live/double-free guards PASS.
  New faults detect lost paused reservation, rtime/res_cached/full-mode/
  rdata drift, illegal stale success/rejected unmodified paused success,
  corrupt reload/readback/paused GPR, dropped peer store/neighbor corruption,
  premature write and lost fresh reservation. Balanced joins/counts,
  cleared TLS maps/probe/globals and restored config/IDs on every failure.
- Build78 native57/57 verified; baseline exact-P58 host check also PASS.
  All58 unique UI/export symbols, plist79/iOS16.0, unchanged47patches and
  pinned core, git whitespace and Python syntax checks PASS. Applicable
  native PPU/TLS patch subset applied with --check. Prior full47patch-chain
  identity remains valid because no upstream/patch content changed.
  Scratch p58-baseline-check.log,p59-fixture-check.log,p59-host-check.log.

Baseline main70291ebcf244f363a5e8967a995d2056ebfafa83. Push Build79 main;
standing user continuation authorizes next incremental build and push.
DO NOT monitor/query Actions after push. User reports workflow completion.
Install ARMSX3_iOS16_INSTALL_THIS_IPA through TrollStore, run all58
diagnostics, export startup log. No P60 until native phone P59 PASS.
Actual LV2 scheduling, full TLS HLE/process mutex/global process setup,
firmware/RSX/game boot remain UNTESTED; earlier P39–P49 scheduler peer
contexts remain unexecuted. No unsolicited pictures.

## 2026-10-11 — build 80 / P60 shared reservation competition and retry

Device evidence: upload/ARMSX3-startup-20261011-205840-340-6790.txt,
Build79 pid6790; Library libfile_40ff674bbd9081918d4982f862c893e9.
Attached scratch file read directly. All58 P2–P59 AUTO PASS, final all-
stages PASS/no AUTO FAIL. Native P59 about0.0129sec; three results2/2,
TLS totals17/31,37/65,60/102. Paused reservations, ordered peer-write
rejection and fresh recovery, retained reservation metadata/rdata/context,
full memory/stack/TLS/aliases/cache/joins PASS. Native P60 pending.

Build80 appends armsx3_core_test_shared_reservation_retry, UI P60 "Shared
reservation competition and retry";59diagnostics P2–P60, plist80/iOS16.0.
CI prepatch invokes test_p60_fixture.py with P43–P59 fixture regression
chain. Entire1657191byte Build79 bridge prefix preserved; SHA256
684057baf8716eb5560db03cff4317f6b0a699ac11d71c1badbd709741661c55.
Appended47262bytes including separator. No pinned core/47patch changes.

P60 retains all P59 arithmetic/FP/vector/status/nested-stack/TLS/atomics/
paused-context/peer-write and lifecycle checks. Adds17words;104words/
416bytes SHA1 9c460a614c715b9bccea9bff71d8bc445453c036. Shared word at
23000 initialized ONCE before workers to44556600; complete surrounding
DATA64KiB checked after every paired slice. Three transactions carry the
same shared word forward to44556602,44556604,44556606, no host reset.
Extra race CR/final outputs at original r6+2010/2014/2018 are disjoint
from all prior outputs, operand/atomic lines and shared word.

New guest tail PCs:
348 LIS r5,2;352 ORI r5,r5,3000 -> shared address23000.
356 LWARX r28,0,r5;360 ADDI r28,r28,1;364 STWCX r28,0,r5.
368 MFCR r29;372 STW r29,r6,2010 records first outcome.
376 BC12,2,+24 jumps to400 if CR0.EQ success (winner skips retry).
380 LWARX r28,0,r5;384 ADDI r28,r28,1;388 STWCX r28,0,r5;
392 BC4,2,-12 returns to380 if retry failed;396 NOP;400 MFCR r29;
404 STW r29,r6,2014;408 LWZ r28,r5,0;412 STW r28,r6,2018;end416.
Actual native LIS declaration and existing BC/ADDI/LWARX/STWCX/CR semantics
inspected in pinned core. No local Xcode SDK/native compile/result.

Both reserved loads and both additions finish before either first store
attempt. Owner/peer bounded dispatches are released together at the store
slice; real native atomic implementation must permit EXACTLY ONE success
and one failure, accepting either winner. Full CR0 LT/GT/EQ/SO plus other
CR/status preservation checked. Shared memory must be initial+1 after
first attempts, including no neighboring byte changes. Release/acquire
completion and real peer empty-queue wait occur between every slice.
This creates overlapping reservations; no claim of physical instruction
execution at the exact same instant or arbitrary scheduling coverage.

First winner is determined only from captured CR0.EQ at slice46. C++ then
sets instruction budget at slice48 to winner1/loser6; NO context/register
writes or host conditional-store emulation occur in native bridge. Guest
BC selects skip/reload path using its retained actual CR. Both end at400;
loser reloads the updated word and stores initial+2 on its fresh retry.
Retry branch backedge exists but must be untaken in this controlled case;
unexpected retry failure/extra iterations stop within the bounded budget
and fail diagnostic. Both final guest loads/stores must publish initial+2.
Repeated failing retries, ABA/same-value cases, arbitrary contention and
full128-byte cross-word invalidation are not proven by this phase.

New slices43..51 budgets2,1,1,1,2,(winner1/loser6),2,1,1;
PCs356,360,364,368,376,400,408,412,416. Final return1 for both workers;
all51 earlier boundaries return-2. At44/45 raddr must be23000; all prior
P59 active-address boundaries retained; other boundaries require raddr0.
Before EVERY resume retain exact raddr/rtime/res_cached/use_full_rdata,
all128rdata bytes and all previously checked GPR/FPR/VR/status/CTR/LR/CIA.
r5 changes by guest setup at43, r28 tracks shared initial/incremented/
retry/final values, r29 tracks real first/final CR readbacks. Prior r19–
r27/old readbacks, TLS/stacks/FP/vector outputs remain checked unchanged.

52slices/worker/transaction=312dispatches/306pauses/876instructions,
39LWARX/51STWCX/30successes/21failures/60MFCR/108integer stores. Three
first-store competitions each have one winner; three losing-worker fresh
retries succeed.156peerjobs+queuedexit+owner=158queuepubs/callbacks.
Exactlytwo retained workers/constructions/joins; TLS totals60/102. Peer
retired before TLS free, owner joined before cache/deallocation/VM close.
All setup/allocation/unwind/config/current-ID/TLS/queue guards inherited.

Validation PASS:
- test_p60_fixture.py checks frozen Build78 AND Build79 prefixes and all
  P43–P59 fixture regressions. Independently encodes104 literal words,
  executes separate scalar contexts across312slices/306stops/876steps.
  Alternates first-store interleaving by transaction to exercise both
  first winners, validates guest skip/reload/add/store/retry branches,
  exact CR/registers/paused reservations/full DATA/TLS/stacks/guards,
  six shared increments and all operation/PC/budget/store counts.
- test_p60_pair.py extracts exact P60 plus production exec_task/bounded
  helper/TLS bootstrap/slot guards from unchanged staged pinned source.
  CPU/VM/reservations/queue/flags/instruction handlers remain HOST SHIMS.
  Shared conditional stores are serialized by an explicit scalar-model
  mutex; preferred host first winner alternates across eight full phases.
  This does NOT substitute for native phone atomic validation. G++C++20
  Wall/Wextra/Werror pthread ASAN+UBSAN detect_leaks0 PASS:16retained host
  workers/2496slices; perphase158callbacks/pubs and all operation counts.
  Both first-winner paths and losing-worker guest retry verified;3skip/
  3retry entries/3successful retry exits/0taken retry backedges perphase.
  Faults2..86 and all5allocations/stopped/PPU-slot/FXO plus independently
  called exact TLS null/wrong-current/pool/pointer/duplicate/live/double-
  free guards PASS with balanced joins/maps/probe/config/ID cleanup.
  New faults detect both stores succeeding/both failing, wrong winner
  skip/retry branch, missing retry increment, shared neighbor corruption,
  bad shared reserved load/final load/first MFCR, rejected valid retry,
  lost shared reservation and paused reservation timestamp corruption.
- All58 native Build79 passes verified; exact frozen prefix, all59 unique
  UI/export symbols/plist80/iOS16.0, unchanged47patches/pinned core, Python
  syntax and git whitespace checks PASS. No upstream or patch change;
  prior applicable patch-chain/native declaration validation retained.
  Scratch p60-fixture-check.log and p60-host-check.log contain validation.

Baseline main7bdf1d31fbaa05bc8ba07e3237d1885c04e20196. Standing user
continuation authorizes next incremental build/push. Push Build80 main;
DO NOT monitor/query Actions after push. User reports workflow outcome.
Install ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, run all59diagnostics,
export startup log. No P61 until native phone P60 PASS. True LV2 scheduling/
context switching, full TLS HLE/process mutex/global process/firmware/RSX/
game boot remain UNTESTED; P39–P49 scheduler peer contexts unexecuted.
No unsolicited images are part of this diagnostic change.

## 2026-10-11 checkpoint: Build80 native PASS → Build81/P61 ordered winners and failed retry backedge

User uploaded ARMSX3-startup-20261011-212418-869-6870.txt and said
“Lets goo 🔥”. Read the attachment from scratch upload, not Library.
Build80 CFBundleVersion verified. All59 native diagnostics P2–P60 AUTO
PASS, final all-stage PASS, no FAIL. P60 three transactions: winner0 each,
shared44556602/04/06, results1/1, totals17/31→37/65→60/102. P60 ends
1791753852.818315 after start3852.811500. Therefore actual native peer
winning/owner retry was still not proven, although host models covered it.

Build81 appends ONLY armsx3_core_test_ordered_reservation_backedge to the
bridge, adds one App stage P61, plist81, CI fixture P61 and two new host
checks. Original Build80 prefix1704453 bytes SHA256
f77bbcafd54609c2ba35763257cbe3eacb7d01c936770d8b25badc511b018f4c
is frozen and checked along with Build78/79. Prior P2–P60/47patches/pinned
core remain unchanged. 60 UI diagnostics P2–P61. All original P60 cases
retained inside P61, including its unordered shared line23000 and retries.

New guest code extends416→540 bytes (135words), SHA1
a5ed7a5288c3c22cb2f47507184bbbb746487866. Independent shared line23080,
initial44557700, initialized once before workers. Three transaction winner
roles0/1/0. Both loads and additions precede either first store. Only slices
55 and58 order the worker dispatches: owner first executes before releasing
peer gate; peer first completes and reaches real empty command queue before
owner runs. No guest register/reservation/memory/result is changed by the
ordering controller. Existing other slices retain parallel paired release.
Exactly two persistent native PPU workers, real production TLS slots,
real bounded dispatch and production reservation operations are required.

New guest PCs (relative to10000):
416 ORI r5,r5,80;420 LWARX r28,r5;424 ADDI r28,r28,1;
428 STWCX r28,r5;432 MFCR r29;436 STW r29,r6,2020;
440 BC12,2,+48 selects winner488, loser444;
444 LWARX r28,r5;448 ADDI r28,r28,1;452 STWCX r28,r5;
456 MFCR r29;460 STW r29,r6,2024;464 BC4,2,-20 retries444;
468 NOP;472 B+52→524;476/480/484 unused padding;
488 LWZ r28,r5;492 ADDI r28,r28,1;496 STW r28,r5;
500..520 six NOPs;524 MFCR r29;528 STW r29,r6,2028;
532 LWZ r28,r5;536 STW r28,r6,202c;end540.

After ordered first store winner succeeds and loser fails, shared base+1.
Winner skips to488; loser loads/adds fresh and pauses at452 with raddr23080.
Winner executes ordinary guest STW496 (base+2) BEFORE loser STWCX452.
This native stale retry must fail without writing. At59 guest MFCR failure
is stored and checked along with full memory/context. At60 loser BNE464
must take backedge EXACTLY444. At61 fresh LWARX pauses,62 ADDI pauses,63
conditional store succeeds (base+3). At64 MFCR overwrites first failure
output with success and BNE is untaken; loser forward branch and winner
NOPs converge524. Both final readback and final word stores match. Winner's
2024 output stays untouched canary. New shared word ends44557709; original
P60 shared word44556606. Both winner roles and losing retry roles tested.
No claim of arbitrary contention, ABA/full128 cross-word invalidation or
actual LV2 scheduler context switching; queue waits are command waits.

68slices/worker/transaction=408dispatches/402pauses/1011instructions.
51LWARX/63STWCX/36successes/27failures/78MFCR/135integer stores.
204peerjobs+exit+owner=206queuepubs/callbacks. Old P60 skip/retry counters
3/3/0backedges/3exits; new ordered counters3skips/3retry paths/3taken
backedges/3successful exits/3ordinary winner stores per phase.
Exact all32GPR/CTR/LR/CIA/FPR/VR/CR/XER/FPSCR/VRSAVE and raddr/rtime/
res_cached/use_full_rdata/all128rdata snapshot compared before every resume.
Full DATA64KiB, both stacks64KiB, whole TLS256KiB, neighbors/aliases,
all old outputs/code/cache and TLS totals60/102 verified at each boundary.
Peer join precedes TLS release; owner join precedes cache/VM cleanup.

Validation PASS:
- test_p61_fixture.py chains P43–P60 regressions and frozen prefix checks;
  independently encodes135 literal words and models408slices/402stops/
  1011instructions. Both ordered roles, first retry failure output before
  overwrite, exact taken backedge/fresh load/paused reservation/successful
  exit and nine total new shared writes all checked, full memory/TLS/
  stacks and exact instruction/store counts. New counters3/3/3/3; loser
  output2024 written twice, winner output untouched.
- test_p61_pair.py extracts exact P61 plus real production exec_task,
  bounded helper and production TLS bootstrap/slot guard bodies from staged
  pinned source. CPU/VM/reservation/instruction/queue operations remain
  HOST SHIMS, no native compile claim. Old P60 scalar atomic model mutex
  and alternating preferred winner retained; new ordering comes from exact
  bridge controller itself. G++C++20 Wall/Wextra/Werror pthread ASAN+UBSAN
  detect_leaks0 PASS: eight runs/16retained host workers/3264slices; exact
  operation/publication counts and old/new branches checked. Faults2..98
  detected, including skipped invalidating STW, falsely accepted stale retry,
  rejected fresh retry, wrong backedge/winner branch, lost paused reservation,
  bad final load/add/MFCR/neighbor/proof output/forward branch. All5
  allocations/setup/exact TLS guard negatives balanced cleanup. Added
  assertions that each new fault is actually installed in host shims.
- All59 native Build80 passes verified. 60 unique UI/export symbols,
  plist81/iOS16.0, frozen prefix, Python syntax, unchanged47patches and
  git whitespace checks PASS. No Xcode/iOS SDK locally; compilation is CI,
  native P61 execution awaits user's phone log. Scratch p61-fixture-check.log
  and p61-host-check.log retain the validation results.

Remote baseline main67f90c9cf1f5a08c5ca1d08ed3475ccbd33c9778,
treebb6208ad5a570c595575a84acbd31da82e41f72b. User's standing continuation
and observed native P60 PASS authorize Build81 push. Do NOT monitor/query
Actions after push. User reports workflow result; install
ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, run all60 diagnostics and
send startup log. No P62 until phone P61 PASS. Full LV2 scheduling/process
TLS/mutex/global process/firmware/RSX/game boot remain untested. No images.

## 2026-10-12 local checkpoint: Build81 native PASS → Build82/P62 64-bit reservations and carry

User attached ARMSX3-startup-20261011-220021-831-6943.txt. Read from
scratch upload, not Library. Build81 confirmed; all60 stages P2–P61 AUTO
PASS and final all-stage PASS, no FAIL. Native P61 winner roles0/1/0 and
all three failed-retry/backedge/fresh-recovery transactions PASS; old shared
44556602/04/06, new ordered44557703/06/09, results1/1 and totals17/31→
37/65→60/102. Stage start1791756016.430256/end6016.438804 (~8.5ms).
This confirms native peer winning/owner retry plus real guest taken BNE,
not merely the host model. Full game boot remains untested.

Build82 appends armsx3_core_test_wide_reservation_carry, P62 UI stage,
plist82 and new fixture/host tests; CI advances to test_p62_fixture.py.
Build81 original1757203-byte bridge prefix SHA256
e95c88c8a0aaa86762042a84ccb0a99c1be624940db6edeb2800daaab0aed8ab
frozen exactly. Prior P2–P61, all47patches and pinned core unchanged.
61 diagnostics P2–P62. Native LDARX and STDCX decoder XO84/214, interpreter
extern declarations and LDARX load/STDCX full64-bit value+CR0 EQ/SO paths,
and ppu_load_acquire_reservation<u64>/ppu_store_reservation<u64> bodies
verified against staged pinned primary source. No local native SDK compile.

P62 retains all P61 cases and extends guest540→616bytes/154words, SHA1
c07e96e3c6f2cc625f5486d6d9337e552b82dfe5. Fresh aligned line23100 seeded
ONCE with55667788fffffffe. Three native ordered first winners1/0/1 (opposite
P61 roles), both reserved loads and additions completed before first stores.
Controller orders only first wide store slice71 through existing gates;
no guest register/reservation/data/store-result editing. Loser takes guest
reload/add/STDCX retry while winner branches around it. First transaction
carries from low32-bit fffffffe→ffffffff→00000000, upper word55667788→
55667789. Three transactions finish5566778900000000/00000002/00000004.
Both final LD and STD publish full64-bit value; guards check neighboring
bytes and both halves. Afterwards both guest contexts execute STDCX again
with consumed reservation and same value as memory: all six MUST reject,
without writes, full MFCR failure output checked at2040.

New relative PCs:
540 ADDI r5,r5,80;544 LDARX r28,r5;548 ADDI r28,r28,1;
552 STDCX r28,r5;556 MFCR r29;560 STW r29,r6,2030;
564 BC12,2,+24→588 winner skip;
568 LDARX r28,r5;572 ADDI r28,r28,1;576 STDCX r28,r5;
580 BC4,2,-12→568 retry (untaken here);584 NOP;
588 MFCR r29;592 STW r29,r6,2034;596 LD r28,r5;
600 STD r28,r6,2038;604 STDCX r28,r5 (must fail);
608 MFCR r29;612 STW r29,r6,2040;end616.
New slices68..78 budgets1/1/1/1/2/(winner1,loser6)/2/1/1/1/2;
PC544/548/552/556/564/588/596/600/604/608/616. Final return2 both,
all78 previous boundaries return-2. Active wide raddr23100 at69/70;
exact full reservation/context snapshots before EVERY resume inherited.
CR failure preserved at71/72 for loser, retry success73..76, consumed
failure77..78; MFCR first72/final74/consumed78 readbacks verified.

79slices/worker/transaction=474dispatches/468pauses/1110instructions.
Total60reserved loads/78conditional stores/42successes/36failures/96MFCR;
wide-only9LDARX/15STDCX/6successes/9failures.159integer guest stores:
15332-bit stores+6wide outputs (host counts wide outputs separately from
36stack stores).237peerjobs+exit+owner=239pubs/callbacks. Exactly two
persistent workers/constructions/joins. Old TLS totals60/102, two stacks,
full64KiB DATA, whole256KiB TLS, code/cache/aliases/guards all retained.
Old line23000 ends44556606, ordered23080 ends44557709, wide23100 ends
5566778900000004. Peer join before TLS free, owner join before VM close.

Validation PASS:
- test_p62_fixture.py chains P43–P61 plus Build78/79/80/81 frozen prefixes,
  independently encodes154 literal words and executes474slices/468stops/
  1110instructions. Full contexts/CR/PC/budgets/paused reservations/full
  memory/TLS/stacks/store counts checked at each boundary; wide winner
  roles1/0/1, low32 carry, exact64-bit loads/stores, retry and consumed
  failures verified. Dedicated wide counters9/15/6/9, shared six updates.
- test_p62_pair.py extracts exact P62 and unchanged production exec_task,
  bounded helper and TLS bootstrap/slot guard bodies. Native CPU/VM/queue/
  reservations/instruction handlers still HOST SHIMS. 64-bit scalar model
  uses full64-bit read/write and the existing serialization mutex; wide
  ordering supplied by exact bridge gates. G++C++20 Wall/Wextra/Werror
  pthread ASAN+UBSAN detect_leaks0 PASS:8runs/16retained workers/3792slices;
  all239pubs/callbacks and exact operation/role/counter checks. Faults2..115
  detected with cleanup, all5allocations/setup/exact TLS guard negatives
  retained. New faults99..115 catch truncated LDARX, swapped/truncated
  STDCX value, lost upper-word carry, both first stores success/failure,
  refused fresh retry/accepted consumed store, failed-store write, retained
  or dropped reservation, neighbor corruption, wrong MFCR/finalLD/STD
  output/winner branch/retry branch. Assert every new fault installed.
- Build81 all60 native stages verified; exact Build81 prefix, all61 unique
  UI/export symbols, plist82/iOS16.0, unchanged47patches, Python syntax and
  git whitespace checks PASS. Scratch p62-fixture-check.log and
  p62-host-check.log hold results. Native P62 compile is CI; device pending.

Remote baseline main18340b3b01a2d03c364cbde008c7acfc2779e689,
treeb4af7df351295b9f2927c1fe35085a895b1eb493. Standing continuation/log
workflow authorizes next build push. DO NOT monitor/query Actions after
push; user reports outcome. Install ARMSX3_iOS16_INSTALL_THIS_IPA via
TrollStore, run all61 diagnostics and send startup log. No P63 until native
phone P62 PASS. Arbitrary contention/ABA/full128 cross-word invalidation/
LV2 scheduling/firmware/RSX/game boot remain untested. No image deliverable
is requested by the attached diagnostic log.

Publishing note: local snapshot has mode100644 for core/build-core.sh,
core/package-loadtest.sh and ios/scripts/build-probe.sh, while remote has
100755. Preserve remote baseline tree modes; local tree SHA cannot directly
match remote unless those baseline mode differences are accounted for.
Verify every published blob against local git hash-object and entire remote
new tree against baseline+only intended seven files, including modes.

## 2026-10-12 checkpoint: Build82 native PASS → Build83/P63 full128 reservations

User uploaded ARMSX3-startup-20261011-223554-848-7031.txt and said
“Lets goo 🔥”. Read scratch attachment. Build82 confirmed, all61 stages
P2–P62 AUTO PASS plus final all-stage PASS, no FAIL. Native P62 wide winner
roles1/0/1, carry/retry/consumed rejection all PASS; wide values
5566778900000000/00000002/00000004, results2/2 and totals17/31→37/65→
60/102. Starts1791758152.550745/ends8152.559961 (~9.2ms). Old shared
44556606/ordered44557709 and all prior diagnostics passed. Device now
proves native LDARX/STDCX full64-bit values and low32 carry. Game untested.

Build83 appends only armsx3_core_test_full_line_reservations, adds P63 UI,
plist83 and new P63 fixture/host tests, advances CI to test_p63_fixture.py.
Original Build82 prefix1813469 bytes SHA256
65072fde8fba57cc220d55c846aa7faff85947efa3b949bfbb33258b4be704e2
frozen exactly. All prior P2–P62/47patches/pinned core unchanged;62 UI
stages P2–P63. No image requested/created. Native primary source inspected:
ppu_load_acquire_reservation<u64> copies full128 bytes when max<0, full
store path uses reservation counter/range writer lock/cmp_rdata; previous
full-line snapshots are not rewritten by a successful/failed conditional
store. system_config.h pinned cfg::_int<-1,14> max_length0 (-1 alwaysfull).
RSX/Core/RSXReservationLock.hpp uses a renderer only if
rsx_accurate_res_access is enabled (defaultfalse). Stopped diagnostic has
no renderer, so P63 RAII explicitly saves/disables/restores that bool along
with saving/restoring reservation max_length. Renderer path is NOT tested.

P63 runs all prior P62 cases with max_length0. Both retained contexts are
paused and peer has returned to empty queue when controller changes mode:
slice0 sets0; slice79 sets-1 BEFORE publishing the next peer command.
No concurrent reservation instruction/config mutation, no context/rdata/
memory/store-result edits by controller. Full mode held through last slice,
then reset0 for next transaction; RAII restores original value after joins
and cleanup, including exceptions. This is a diagnostic-local mode change,
not a new persistent user setting or change to earlier diagnostic functions.

Guest extends616→688bytes/172words, SHA1
9bcdec2fa30c214770cb17737e1ae96bb3c674f1. Separate six aligned128-byte
lines24000/24080/24100/24180/24200/24280, seeded once before workers with
66778899aabbcc00 +transaction100+worker10. Each worker loads full64-bit
word at its OWN line base then NOPs in another dispatch. Peer ordinary STW
writes its r26 into line+64: different aligned8-byte word, original target
word unchanged. Both writes finish before either stale STDCX. Each stale
STDCX uses original value EQUAL to target memory and MUST reject. Full
128-byte snapshot compared explicitly at each boundary: initial 64-bit
word, untouched a5 guards and still-old peer-neighbor bytes remain in rdata.
Fresh LDARX reload incorporates peer's line+64 mutation; paused ADDI then
STDCX succeeds, target initial+1. Snapshot remains pre-success target value
as native source specifies. Both final LD/STD publish full64-bit output.
Consumed STDCX then rejects; initial-failure/success/consumed MFCR stored.

New relative PCs:
616 ADDI r5,r19,3000;620 ADDI r31,r31,3040;
624 LDARX r28,r5;628 NOP;632 STW r26,r31,0 (peer line+64);
636 STDCX r28,r5 (stale mustfail);640 MFCR r29;644 STW r29,r6,2044;
648 LDARX r28,r5;652 ADDI r28,r28,1;656 STDCX r28,r5 (fresh success);
660 MFCR r29;664 STW r29,r6,2048;668 LD r28,r5;
672 STD r28,r6,2050;676 STDCX r28,r5 (consumed fail);
680 MFCR r29;684 STW r29,r6,2058;end688.
New slices79..92 budgets2/1/1/1/1/2/1/1/1/2/1/1/1/2, PCs
624/628/632/636/640/648/652/656/660/668/672/676/680/688. Full raddr
ownline at80/81/82/85/86; other new boundaries zero. use_full_rdata MUST
be true and all128rdata bytes match independently built captured line at
EVERY slice80..92, including stale and fresh snapshots. All context/status/
reservation fields preserved before every resume; full DATA/TLS/stacks/
aliases/code/cache/guards and old outputs verified at every boundary.

93slices/worker/transaction=558dispatches/552pauses/1218instructions.
Total72reserved loads/96conditional stores/48successes/48failures/114MFCR;
wide-only21LDARX/33STDCX/12successes/21failures. Full-only12loads/18stores/
6fresh successes/6stale failures/6consumed failures.189integer guest stores
=17732-bit+12wide outputs, separate36stack stores.279peerjobs+exit+owner
=281pubs/callbacks; exactly2retained workers/constructions/joins, TLS60/102.
Prior shared/wide results intact; each new line has one neighbor mutation
and one successful target increment; all other a5 guard bytes are
covered by whole64KiB DATA comparison. No cross-word conditional-store
address change, ABA, arbitrary contention or LV2 context switch claimed.

Validation PASS:
- test_p63_fixture.py chains P43–P62 and all frozen prefixes throughBuild82;
  independently encodes172 literal words and models558slices/552stops/
  1218instructions. New full-line model captures128bytes, compares all128
  for stores, verifies exact stale/fresh captured buffers (before/after peer
  mutation), unchanged target on rejection, fresh increment/consumed failure,
  every CR/PC/budget/output/neighbor/full memory/stack/TLS and operation count.
- test_p63_pair.py extracts exact P63 plus unchanged production exec_task,
  bounded helper and TLS bootstrap/slot guard bodies. CPU/VM/queue/instruction/
  reservation operations including full-line comparison remain HOST SHIMS;
  native range writer lock/RSX lock not executed locally. Full128 scalar
  model uses memcmp; config model starts max3/RSXtrue and asserts3/true
  restored after EVERY full success/negative/setup/guard run, proving save/
  restore rather than fixed defaults. G++C++20 Wall/Wextra/Werror pthread
  ASAN+UBSAN detect_leaks0 PASS:8runs/16retained host workers/4464slices;
  all281pubs/callbacks and operation counts. Faults2..130 detected with
  balanced cleanup; all5allocation/setup/exact TLS guard negatives retained.
  New116..130 catch ignored full comparison, disabled full mode/8-byte-only
  snapshot, skipped/wrong peer neighbor store, refused fresh success, stale
  failed-store write, retained/damaged reservation data, changed guard,
  wrong finalSTD/consumed result/MFCR/truncated addition. Assert every new
  fault installed, including != checks used to disable full comparison.
- Build82 all61 native diagnostics confirmed. Exact Build82 prefix,62unique
  UI/export stages, plist83/iOS16.0, unchanged47patches, Python syntax and
  git whitespace checks PASS. Scratch p63-fixture-check.log and
  p63-host-check.log hold results. Native compilation CI and phone P63 await.

Remote baseline main7f63c65eadb45998adaf04d97febe27e80a32c4e,
tree3040d38e17bc89efd9fcc3d85e6790315cbc4e43. Standing user continuation
and native P62 PASS authorize Build83 push. DO NOT monitor/query Actions
after push; user reports result. Install ARMSX3_iOS16_INSTALL_THIS_IPA via
TrollStore, run all62 diagnostics and send startup log. No P64 until native
P63 PASS. Arbitrary contention/ABA/full-line cross-address stores/LV2
scheduling/firmware/RSX/game boot remain untested. Preserve remote script
100755 modes as earlier publishing note; verify remote tree+seven changes.

## 2026-10-12 checkpoint: Build83 native PASS → Build84/P64 reservation target granularity

User uploaded ARMSX3-startup-20261011-225939-495-7174.txt (“Here you go”).
Read scratch attachment. Build83 confirmed; all62 diagnostics P2–P63 AUTO
PASS plus final all-stage PASS, no FAIL. P63 starts1791759576.980462 and
ends9576.991993 (~11.5ms). All three93-slice transaction pairs results2/2,
totals17/31→37/65→60/102, shared44556606/ordered44557709/wide
5566778900000004. Full128 snapshots, six peer line+64 stale rejections,
six fresh paused full-line recoveries and six consumed rejections native
PASS. This now proves native full-line operation/range-lock path with
RSX reservation access disabled in stopped diagnostic. Renderer/game untested.

Build84 appends armsx3_core_test_reservation_line_targets, P64 UI, plist84,
CI test_p64_fixture.py and two new tests. Original Build83 bridge prefix
1874705 bytes SHA256
85f7ddca129f07fb3cbfd809278c59c6aaa09d786c31f52bd2bc2a65fc1df8fa
frozen exactly. Prior P2–P63/47patches/pinned core unchanged.63 UI stages
P2–P64. All P63 cases retained inside P64; full reservation mode persists
through added tail. Reservation max_length and stopped-core RSX reservation
access saved/restored by same RAII; no persistent settings changed.

Native ppu_store_reservation source explicitly permits different aligned
8-byte target if load/store addresses share aligned128-byte line and
use_full_rdata is true; outside-line address rejects and clears raddr/
res_cached before target writes. Success stores res_cached=original raddr
and advances rtime128. Cached same-line reload keeps rtime; native full
load copies updated128bytes. Primary CPUThread.h/.cpp inspected: full-store
test_stopped/check_state calls cpu_sleep only for suspend, not wait alone;
ppu.cpu_sleep clears reservation but true LV2 suspend not part of this test.
No core patch changes or host substitution in native bridge.

Guest extends688→792bytes/198words, SHA1
4ed65229c225767011ec8e1ab6ec7dbe64031c77. Six aligned lines25000/25080/
25100/25180/25200/25280; seeded once with line+8 load word
778899aabbccdd00 +transaction100+worker10 and DISTINCT line+16 target word
8899aabbccdde000 +transaction100+worker10. Each worker LDARX at line+8,
paused ADDI r28+1 and paused r5 address change to line+16; STDCX MUST
succeed in full128 mode. Original load word unchanged, target becomes load+1.
Next LDARX at line+16 uses cached same-line timestamp and sees written word.
ADD r28+1, then move r5 by128 OUTSIDE reserved line; STDCX MUST fail and
preserve all target/peer/canary memory. Some outside targets lie in peer or
next-transaction lines, others untouched guard; all valid mapped addresses.
Restore r5, fresh paused LDARX/add/STDCX succeeds to load+2; consumed store
then fails. Both full64-bit outputs and four guest MFCR outputs checked.

New relative PCs:
688 ADDI r5,r5,1008;692 LDARX r28,r5;696 ADDI r28,r28,1;
700 ADDI r5,r5,8;704 STDCX r28,r5 (same line, different word success);
708 MFCR r29;712 STW r29,r6,205c;716 LD r28,r5;720 STD r28,r6,2060;
724 LDARX r28,r5 (cached reload);728 ADDI r28,r28,1;
732 ADDI r5,r5,80;736 STDCX r28,r5 (outside line failure);
740 MFCR r29;744 STW r29,r6,2068;748 ADDI r5,r5,-80;
752 LDARX r28,r5;756 ADDI r28,r28,1;760 STDCX r28,r5 (fresh recovery);
764 MFCR r29;768 STW r29,r6,206c;772 LD r28,r5;776 STD r28,r6,2070;
780 STDCX r28,r5 (consumed failure);784 MFCR r29;788 STW r29,r6,2078;
end792. New slices93..114 budgets1/1/1/1/1/2/1/1/1/1/1/1/2/1/1/1/1/2/
1/1/1/2. Exact PC table, full GPR/CR/raddr and untouched registers verified.
At94/95/96 raddr is line+8 even after r5 changes; at101/102/103/107/108
raddr is line+16 even while r5 temporarily targets outside line. Full128
snapshot remains original until cached reload101, then contains targetload+1
through end (successful store does not modify snapshot). All128 bytes checked.
Capture actual initial reservationTime at94 (do NOT assume native counter0);
require same time94..96, +128 at97..108, +256 at109..114. res_cached must
be original loadaddr+8 at97..103, zero104..108, target+16 at109..112, zero
113..114. Thus native success/cached reload timestamp behavior checked
explicitly, beyond merely preserving arbitrary snapshot fields.

115slices/worker/transaction=690dispatches/684pauses/1374instructions.
90reserved loads/120conditional stores/60successes/60failures/138MFCR;
wide-only39LDARX/57STDCX/24successes/33failures. New cross-target-only18
loads/24stores/12successes/12failures.225integer stores=20132-bit+24wide
outputs, separate36stack stores.345peerjobs+exit+owner=347pubs/callbacks.
Exactlytwo persistent workers/constructions/joins, TLS60/102, full DATA/
TLS/stacks/aliases/code/cache/guards preserved. Each new load word has no
stores; each target exactlytwo successful stores; all outside attempts
have no memory effects. No mixed-width, ABA, arbitrary contention, true LV2
scheduling, RSX, firmware or game boot claimed.

Validation PASS:
- test_p64_fixture.py chains P43–P63/all frozen prefixes throughBuild83;
  independently encodes198 literal words and models690slices/684stops/
  1374instructions. Full-line address-granularity model, scalar reservation
  timestamp/cached-address model, all128-byte snapshots, exact field/CR/PC/
  budget/readback/memory/guard/stack/TLS and operation counts verified.
- test_p64_pair.py exact P64 plus production exec_task/bounded/TLS bodies;
  CPU/VM/queue/reservation/instruction handlers remain HOST SHIMS. Added
  explicit full-line retargeting and cached timestamp scalar rules matching
  inspected primary core. G++C++20 Wall/Wextra/Werror pthread ASAN+UBSAN
  detect_leaks0 PASS:8runs/16retained workers/5520slices;347pubs/callbacks and
  all counters exact. Faults2..145 detected, all5allocation/setup/exact TLS
  guard negatives balanced cleanup/config restoration. New131..145 catch
  incorrectly requiring exact same address, allowing outside-line store,
  writing load word instead of target, omitted timestamp advance/wrong
  cached source address/stale reload timestamp/bad cached value/full snapshot,
  writing on outside failure or retaining cache, refused fresh recovery,
  bad finalSTD/CR/consumed store/neighbor corruption. Each new fault must
  actually reach the added target phase; fault132 bypass of full comparison
  is scoped to new outside attempt, preventing an earlier P63 failure from
  masking lack of target-phase coverage. All fault hooks asserted installed.
- Build83 all62 native diagnostics verified. Exact Build83 prefix,63unique
  UI/export stages/plist84/iOS16.0/47unchangedpatches/Python syntax/git
  whitespace checks PASS. Scratch p64-fixture-check.log/p64-host-check.log
  hold results. Native P64 compilation CI; phone execution still pending.

Remote baseline main9ac672f754e6307dc957585549d6ef44abd6cc09,
tree7e8a86cec151178a33c950f7adbb07f22f52ece2. Standing continuation and
native P63 PASS authorize Build84 push. DO NOT monitor/query Actions after
push; user reports outcome. Install ARMSX3_iOS16_INSTALL_THIS_IPA via
TrollStore, run all63 diagnostics and send startup log. No P65 until native
P64 PASS. After that, prioritize integrating guest synchronization/scheduler
behavior over adding equivalent atomic fixtures. Preserve remote script
100755 baseline modes; verify remote baseline tree+only seven intended files.

## 2026-10-12 checkpoint: Build84 native PASS → Build85/P65 integrated guest spinlock

User attached ARMSX3-startup-20261011-233546-624-7416.txt. Read scratch
attachment. Build84 confirmed, all63 diagnostics P2–P64 AUTO PASS and
final all-stage PASS, no FAIL. Native P64 starts1791761742.296294 and ends
1742.309789 (~13.5ms). All three115-slice transaction pairs results2/2,
totals17/31→37/65→60/102, old shared/wide results preserved. Native full128
cross-word stores, cached reload timestamps/source cached addresses,
outside-line rejections/fresh recovery/consumed failures all PASS.
User explicitly selected Midnight Club Los Angeles as desired first game;
that is a future target, game boot/RSX/firmware still untested. Build84 ZIP
was accidentally deleted; reran successful workflow's single build job
114600110769 on run38183256017 (attempt2) with GitHub rerun_job, success=true.
No source changes for rerun. User supplied this phone log afterwards.

Build85 appends ONLY armsx3_core_test_guest_spinlock_handoff, adds P65 UI,
plist85, CI test_p65_fixture.py and two new tests. Original Build84 prefix
1941662 bytes SHA256
63e582a260e62048c8f07078e9bbde0d73ff90649d7af1e98b5392923b0165ff
frozen exactly. Previous P2–P64/47patches/pinned upstream unchanged;64 UI
stages P2–P65. P65 is a new compact workload; it does NOT rerun all P64
atomic fixtures internally (the UI and chained fixtures retain them).
Scaffold uses proven two persistent native workers, production TLS slots,
bounded dispatch, gate/queue/lifecycle/VM cleanup from P64. Job initializer
sets transaction inputs once, all later resumes compare complete retained
GPR/FPR/VR/status/CIA/CTR/LR and reservation snapshots without edits.
Reservation mode0 and stopped-core RSX accessfalse held for this diagnostic,
saved/restored on all exits, with all other configuration RAII preserved.

New guest spinlock program29words/116bytes, SHA1
c8762334c18218a5eae0ad7f502135218ee598e8:
0 LWARX r7,r5;4 CMPWI r7,0;8 BNE -8→0 if held;
12 LI r8,1;16 STWCX r8,r5;20 BNE -20→0 if lost acquisition;
24 ISYNC;28 LWZ r9,r5,128 counter;32 LWZ r11,r5,132 checksum;
36 ADDI r9,r9,1;40 ADD r11,r11,r10 token;
44 STW counter;48 STW checksum;52/56/60 STW own counter/checksum/token;
64 LWSYNC;68 LI r8,0;72 STW lock release;
76 LWZ r12,r13,-6ff4 previousTLS;80 ADDI r12,r12,1;
84 STW TLS;88 STW own TLS output;92..112 six NOPs;end116.
Native primary CMPI/ISYNC/SYNC decoder XO and interpreter handlers inspected;
ISYNC handler atomic_fence_acquire, SYNC handler atomic_fence_seq_cst
(including guest LWSYNC encoding). Fence opcodes/decode executed, but this
controlled test is NOT a weak-memory litmus test.

Shared lock23000=0, counter23080=0, checksum23084=0 initialized ONCE.
Tokens1..6, own outputs20200+transaction100+worker80. Two retained threads
execute3transactions each, first roles0/1/0. Both load lock0 before first
store. Designated first stores1; other conditional store loses and guest
BNE retries. Waiting worker completes THREE LWARX/CMPWI/BNE held-lock loops
while first worker computes/updates protected counter/checksum and outputs.
Whole DATA check ensures waiting worker cannot write protected values or
its own outputs during held-lock slices. First guest LWSYNC/STW releases0;
second guest reserved load sees0, STWCX takes lock, ISYNC enters critical
section, updates each value exactly once and releases. Both TLS counters
advance once per transaction. Final lock0, counter6, checksum21, TLS3/3.
Counter/checksum histories2/3→4/10→6/21; own output counter/checksum shows
which worker owned each critical section. Release/acquire word and adjacent
bytes/full DATA/full TLS/stacks/aliases/cache preserved at every boundary.
No host controller writes guest lock/counter/output/register/reservation
results. Only acquisition slice1 and release-before-reload slice7 are
ordered by native callback gates; other paired slices release concurrently.

16slices per worker pertransaction=96dispatches/90pauses/219instructions,
first29steps/second44steps (extra6lost-acquisition instructions+9held-loop
instructions).18LWARX/9STWCX/6successes/3failures;18CMPWI,9held BNE backedges,
3lost-acquisition backedges,6successful acquisition exits,6ISYNC/6LWSYNC.
42non-TLS32-bit stores+6TLS stores; lock12writes (6conditional locks+
6ordinary releases), counter/checksum6writes each,24own output stores.
No guest calls/stack/FP/vector writes; all untouched64-bit GPR and FPR/VR/
status/stack canaries checked.48peerjobs+exit+owner=50pubs/callbacks.
Exactlytwo persistent workers/constructions/joins. Peer join before TLS free,
owner join before VM/cache/deallocation; all errors cancel gates and balance
maps/thread counts/TLS/id/config/probe state. Sequential role alternation
also exercises native cached reservations without resetting rtime/res_cached.

Validation PASS:
- test_p65_fixture.py chains P43–P64 and all frozen prefixes throughBuild84;
  independently encodes29 literal words and models96dispatches/90stops/
  219instructions with scalar memory, CR, cached reservation timestamps and
  real guest branch targets. Checks full GPR/CR/PC/step budgets/active raddr,
  exact lock/protected values/deferred outputs/whole memory/TLS/guards and
  operation/write counts at every boundary; both lock owner roles tested.
  Static Build84 hash retained (not dynamic gitHEAD), safe for CI/new commits.
- test_p65_pair.py extracts exact P65 plus unchanged production exec_task,
  bounded helper and TLS bootstrap/slot guards. CPU/VM/queue/reservations/
  instruction/fence operations remain HOST MODELS, not native emulation.
  G++C++20 Wall/Wextra/Werror pthread ASAN+UBSAN detect_leaks0 PASS:8runs/
  16retained workers/768slices; all50pubs/callbacks and instruction/branch/
  fence/store/lifecycle counters exact, all three transaction log values.
  Selected applicable foundational faults2..17/26/27/36..41/48/49/51..55/
  59/60 and new147..167 detected; unused old instruction-specific faults
  not claimed. New faults catch bad compare/held or lost retry branch,
  wrongly successful/rejected acquisitions, wrong counter/checksum update,
  premature/missing unlock, waiting-worker output write, lost paused
  reservation/status/TLS/token/neighbor output, failed store writing lock,
  changed stack/CR/address/retry PC. All5allocation/setup/exact TLS guard
  negatives and config max3/RSXtrue restoration retained. Test template
  bswap64 name preserved (do not blindly replace p64 substrings).
- Build84 all63 native diagnostics verified.64unique UI/export symbols,
  exact frozen prefix/plist85/iOS16.0/47unchangedpatches/Python syntax/git
  whitespace PASS. Scratch p65-fixture-check.log and p65-host-check.log
  contain results. Native P65 compile via CI; phone result awaits user.

Remote baseline maind29292e1bb8ec5b00c17bc92c7a0e0de4c0b8301,
tree793c716120e444a53e3f75fec59a05536e7c5528. Standing log/continuation
workflow and observed native P64 PASS authorize Build85 push. DO NOT
monitor/query Actions after push; user reports outcome. Install
ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, run all64 diagnostics and
send startup log. No P66 until phone P65 PASS. Next consider production
synchronization HLE / actual scheduler integration, not equivalent atomic
fixtures. Controlled guest spinlock workload is now integrated, while
arbitrary contention/weak-memory stress/production sys_spinlock HLE/LV2
scheduling/renderer/firmware/game boot remain untested. Preserve remote
100755 script baseline modes; verify baseline tree+seven intended changes.

## 2026-10-12 — Build85 native PASS; Build86 / P66 registered spinlock HLE

Authoritative continuation: root handoff only. User attached
ARMSX3-startup-20261012-004335-066-7746.txt (scratch upload; LibraryID
libfile_2ed11ce84de08191887f6153c225f05b). Build85 header verified;
all64 unique P2–P65 AUTO PASS, final all-stage PASS, no FAIL.
P65 starts1791765811.527929, ends5811.531215 (~3.3ms). Transactions:
first0 counter2 checksum3 TLS1/1; first1 counter4 checksum10 TLS2/2;
first0 counter6 checksum21 TLS3/3, results1/1 each. Native guest spinlock
acquisition/exclusion/retry/fenced release/handoff and exact context/VM/
TLS/stack/cache/lifecycle cleanup confirmed. This is not game boot.

Build86 appends ONLY armsx3_core_test_hle_spinlock_handoff and its required
PPUModule.h include to CoreBridge.cpp, preserving the entire Build85
1976066-byte prefix exactly, SHA256
47f8bd0063ab6aed0804726a36b7ead7c4a1c560ef4702c8c34d4f6ba350df2e.
No prior native P2–P65 code,47 patches,upstream pin or build scripts changed.
Adds UI P66/plist86/CI test_p66_fixture.py plus two new P66 tests.
One prior test correction: test_p65_fixture.py now extracts its function
through balanced braces rather than treating the entire remaining bridge
as P65. Its original oracle/assertions/frozen prefix remain unchanged;
this allows append-only phases to coexist without counting their workers
as P65 constructors. Eight intended changed files including root handoff.

P66 resolves four actual native registered handlers by exact names from
ppu_module_manager::get_module("sysPrxForUser")->functions and
ppu_function_manager::get(). Exactly one match per name, in-range/non-null
indices, distinct handlers required. No duplicated native service bodies,
new core hooks, global module initialization, HLE table allocation or
import linkage mutation. Isolated CODE slots at10000+256/260/264/268 are
registered with actual production BIND_FUNC_WITH_BLR initialize/lock/
trylock/unlock handlers using ppu_register_function_at. Generic words
decoded first; custom cache entries and full CODE bytes checked before
execution and after joined cleanup. The diagnostic therefore exercises
guest BL → native registered HLE ABI wrapper → actual sys_spinlock body
→ LR return → guest continuation, with all fetches bounded.

Pinned primary sources inspected from ARMSX2/ARMSX3 commit
92b931b9fb5eef7f1317cb482917dfc19aceebd9:
Modules/sys_spinlock.cpp, PPUFunction.h, PPUModule.h, ErrorCodes.h and
local patched PPUThread.cpp/.h/PPUOpcodes.h. Services initialize conditionally
clear a nonzero word; lock uncontended exchanges ABADCAFE; trylock returns
not_an_error(CELL_EBUSY=8001000a) when held and otherwise exchanges ABADCAFE;
unlock stores0. Error_code is signed32 and binder returns sign-extended
EBUSY ffffffff8001000a in64-bit r3. Initialize/unlock are void: their
r3 remains input lock address23000, including syscall history error field.
History captures four arguments from eight saved syscall_args. Native
BIND_FUNC sets CIA to handler address, records name/error/args, restores
current_function and returns to masked LR. With current_function initially
null, last_function updates to the most recently called service.

Guest program68words/272bytes, SHA1
25216a46c35be459b66d128891fcf9c695d26626. Main paths:
0 ADDI r3,r5,0;4 BL initialize256;8 ADDI;12 BL lock260;
16 STW lock result→own+16;20 B→common64.
Waiter enters132/136/140/144 NOP;148 B→24. At24 ADDI;
28 BL try264;32 store first busy→own+20;36 ADDI;40 BL try264;
44 store second busy→own+24;48 ADDI;52 BL try264;
56 store success→own+28;60 B→common64.
Common64/68 LWZ protected counter/checksum,72 ADDI counter,76 ADD token;
80/84 protected stores;88/92/96 own counter/checksum/token stores;
100 ADDI lock argument;104 BL unlock268;108 store void result→own+32;
112/116/120 increment real guest TLS word via r13-6ff4;
124 own TLS output;128 B→end272. Remaining words NOP placeholders,
with last four positions receiving native HLE handlers in cache.

Initial lock23000=12345678 deliberately nonzero, counter23080=0,
checksum23084=0; DATA64KiB A5 except bootstrap/inputs. No host updates
guest lock/protected/output results after initialization. Three transactions
on two retained native workers/production TLS slots, first roles0/1/0.
First guest initialization clears nonzero lock; later initialization calls
take no-write zero branch. First native lock is ALWAYS called while free,
so no unbounded blocking wait is entered. Waiting guest calls trylock twice
while held (six EBUSY total), then once AFTER ordered production unlock;
three fresh successes. Both workers each perform exactly one protected
counter/checksum update, unlock and increment private TLS per transaction.
Whole DATA/TLS/stack/alias checks validate deferred outputs at every slice.
Expected totals counter2/4/6,checksum3/10/21,TLS1/2/3 on each worker.

12 paired slices per transaction=72 bounded dispatches/66 pauses/186steps:
first26steps,second36steps each transaction;165 guest instructions plus
21 registered HLE calls.21 guest BL calls,3 initialize,3 uncontended lock,
9 trylock(6 busy+3 success),6 unlock. First budgets
[1,1,1,2,1,6,5,2,1,2,3,1],PC offsets
[4,256,8,260,16,80,100,268,108,116,128,272]. Waiter budgets
[1,1,1,1,1,3,4,2,2,7,7,6],PC offsets
[136,140,144,148,24,32,44,52,56,84,108,272]. Only slice8 orders unlock
before fresh try; other paired slices release concurrently. First final
bounded result1,second6 (helper returns instruction steps in final slice),
so transaction logs results1/6,6/1,1/6.21 HLE history records cumulatively
split10/11 across worker0/1.54 non-TLS guest STW+6TLS stores;
42 own output words+12 protected writes;13 native service lock writes
(one initclear+6acquire+6release). No guest reservation operations or stack/
FPR/VR/status changes. Full retained32GPR/CTR/LR/CIA/FPR/VR/CR/XER/FPSCR/
VRSAVE/reservation snapshots, syscall args/history/current/last names,
HLE count/address/signed-or-void result/four input arguments checked.
Contexts initialized only at transaction start; resumes compare before
executing without register repair. Failure details logged before native TLS
bootstrap's existing catch-all converts them to its error result.
36peerjobs+queuedexit+owner=38queue publications/callbacks, exactly2
constructions/joins; peer join before TLS free,owner join before VM/cache
deallocation. Proven gate/cancel/stop/join/config guards retained.

Validation PASS:
- Independent test_p66_fixture.py chains all P43–P65/frozen prefixes,
  checks68literal instruction words and independently models72dispatches,
  every PC/LR/complete GPR/history/ABI/whole DATA/TLS/deferred output boundary,
  all instruction/service/store counts and both role orders. SHA1 above.
- test_p66_pair.py reuses existing P65 shim construction WITHOUT running
  its workload. Extracts exact new P66, unchanged production exec_task,
  bounded helper,TLS bootstrap/slot guards, all four native sys_spinlock
  service bodies and actual BIND_FUNC/argument/result templates plus
  BIND_FUNC_WITH_BLR macro. CPU/VM/queue/registry/atomic storage/casts/
  decoder/instructions remain HOST MODELS, not native emulation. Atomic
  BE scalar storage is safe for this explicitly ordered workload and is
  not a model of arbitrary host atomic contention. Native source files
  staged under scratch upstream for extraction; do not vendor them in repo.
  G++C++20 Wall/Wextra/Werror pthread ASAN+UBSAN detect_leaks0 PASS:
  8runs/16workers/576slices,all instruction/BL/store/publication/lifecycle
  counts and three transaction logs exact. Selected applicable foundational
  faults2..17/23/26/27/36..41/60/153 plus168..185 detected (bad cache,
  omitted initialize/unlock,wrong acquisition marker/busy result/argument,
  history count/error/args/name/CIA,current-function leak,saved syscall args,
  adjacent lock word,protected counter/output token,branch target/LR,missing
  registry). All5allocation/setup/exact TLS guard negatives/config restoration
  retained. Faults apply in host shims; no injected bugs in delivered native.
- Native Build85 all64 stages verified.65unique UI/export symbols P2–P66,
  exact Build85 frozen prefix/plist86/iOS16.0/47unchangedpatches/Python syntax/
  whitespace checked. Scratch p66-fixture-check.log,p66-host-check.log.
  Native P66 iOS compile via CI; phone execution PENDING user log.

Remote baseline main7a19c9da7bd6a52359bd4482c42aa0401d8726c2,
tree060c07c462b362ad68637621495206ae91d6bc75. Observed P65 native PASS
and standing continuation authorize Build86 push. Preserve remote100755
script modes; verify baseline tree plus exactly eight intended changes.
DO NOT query/monitor Actions after push; user reports build/phone outcome.
Install ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, run all65diagnostics,
send startup log. No P67 before native P66 PASS. Blocking spinlock contention/
cpu_flag::again recovery or real LV2 synchronization scheduler could be next,
but must research appropriate bounded path before implementation. Global
HLE table/import loader/weak-memory stress/arbitrary contention/LV2 scheduling/
renderer/firmware/game boot remain untested. Midnight Club Los Angeles remains
the user's desired first eventual game; do not promise compatibility/boot.

## 2026-10-12 — Build86 native PASS; Build87 / P67 blocking spinlock pause/resume

User supplied ARMSX3-startup-20261012-011428-471-8012.txt, scratch upload,
LibraryID libfile_4531055cbe308191874d4739db03d98c. Build86 header and
all65 unique P2–P66 AUTO PASS verified; final all-stage PASS, no FAIL.
Native P66 starts1791767665.608683, ends7665.611561 (~2.9ms).
Transactions first0 counter2 checksum3 TLS1/1 results1/6; first1 counter4
checksum10 TLS2/2 results6/1; first0 counter6 checksum21 TLS3/3 results1/6.
Actual registered production initialize/lock/trylock/unlock, six signed
EBUSY returns, three fresh trylock acquisitions and exact ABI/history/
guest contexts/whole VM/TLS/cache/lifecycle now natively proven. No game boot.

Build87 appends ONLY armsx3_core_test_blocking_spinlock_handoff; preserves
all Build86 bridge2018202 bytes exactly, SHA256
77aed343a6d3919d1e8a088d9d546c3d7cbb3ec8f9941153c934d2c2696ee862.
No prior P2–P66 implementation, prior tests,47 patches,upstream pin or
build scripts changed. Adds P67 UI/plist87/CI test_p67_fixture.py and
two new tests plus root handoff; exactly seven intended changed files.
No new upstream hook, service-body replacement or global debugger setting.

P67 retains P66 compact program, paired workers/TLS/configuration,
12-slice budgets/exact contexts/VM/cache/gates/cleanup. ONE opcode changed:
guest waiter third call atoffset52 now BL208→production lock260 rather
than BL212→trylock264.68words/272bytes SHA1
cacb3c02a2daa1324de32b0568f6a5f235c3bf35.21 total guest BL/HLE calls:
3initialize,3uncontended lock,3CONTENDED lock,6busy trylock,6unlock.
Still72dispatches/66budget pauses/186bounded steps(165 ordinary guest
instructions+21 HLE calls),54non-TLS guest stores+6TLS,42own output words,
12protected writes,13native lock writes. First roles0/1/0 and final
counter6/checksum21/TLS3/3/lock0 unchanged; results1/6,6/1,1/6.
The recovered call's history name/CIA is now sys_spinlock_lock/10260.

CODE10260 cache entry is a DIAGNOSTIC observedLock wrapper. It forwards
every invocation to the actual registered sys_spinlock_lock HLE binder
with original opcode/this_op/next arguments. Only waiter slice8 requests
per-thread cpu_flag::dbg_global_pause before forwarding, then publishes
lockEntered epoch. No guest register repair or host lock release is used.
The held native lock enters its actual while condition/test_stopped body,
which calls native cpu_thread::check_state and publishes cpu_flag::wait.
No ordinary cross-thread context read occurs until controller acquires
that wait flag and the matching entry epoch. Wrapper requires no preexisting
pause/wait on entry, ensuring this is a new in-service wait publication.
The dbg_global_pause branch holds the worker inside native check_state until
explicitly cleared. Uses this flag deliberately: cpu_flag::suspend would
invoke cpu_sleep/LV2 awake, while dbg_pause would invoke gdb_server.
Neither of those additional paths is part of this diagnostic.

Before any unlocking instruction, the first worker verifies the blocked
call: r3 remains input lock address23000 (rather than early success0),
full32GPR/CTR/FPR/VR/status/reservation snapshot unchanged from slice7;
only guest BL updated LR=10038 and HLE binder set CIA=10260. Current and
last function are sys_spinlock_lock, saved syscall args intact; completed
history count remains prior value, no return/worker-completion published.
Whole DATA/TLS/stacks and aliases match previous boundary exactly, including
held ABADCAFE/protected counter+checksum and absence of waiter output/TLS
writes. This also distinguishes waiting inside the busy body from pausing
in the binder's post-call test_stopped after a premature success result.
Then first worker executes the guest's actual production unlock at10268,
requires lock0 and expected bounded result/PC108 before clearing pause and
notifying waiter state. Native check_state clears wait, native lock loop
re-evaluates/acquires ABADCAFE, returns CELL_OK through real HLE history/LR,
and guest completes its protected updates/unlock/private TLS increment.
Three entry/return epochs and blocked count checked; paused flags clear on
normal completion. No fabricated service return value or restored register.

Controller roles alternate too: owner controls blocked peer for tx1/3;
peer controls blocked owner for tx2. Shared Callback carries runGuest,
actual lock handler and releaseBlocked pointers; Program holds two native
context pointers and valid expected-pool snapshot during controller scope.
Atomic entry/wait publications precede live read; pause-clear notification
and callback completion publications order subsequent reads. All native
CPU flags remain actual core atomics. Peer-side controller exceptions log
details, cancel gates and signal owner's exit so a blocked native service
can escape. Existing2-second readiness/wait/completion deadlines,8-second
owner deadline and cancel/exit/notify/stop/join RAII retained. On every error
peer is joined before TLS freeing, owner before VM/cache teardown. Exit
releases debugger pause waits; normal flow never enters cpu_flag::again.
The instruction budget does not count inner HLE loop iterations; deadline/
CPU exit guards bound error handling. Native compile/device result pending.

Pinned primary native sources inspected at upstream92b931b9...:
CPU/CPUThread.cpp/.h, Utilities/bit_set.h, rpcs3/util/atomic.hpp, plus P66
service/binder/PPU sources already staged. test_stopped calls check_state
when state nonzero; check_state handles dbg_global_pause, publishes wait
atomically and calls PPU cpu_wait→state.wait. atomic_bs_t inherits atomic_t;
its fetch_op uses seq_cst compare_exchange and loads, providing acquired
publication for live context reads while pause prevents further changes.
No need for global Emu pause or scheduler registry mutations.

Validation PASS:
- test_p67_fixture.py chains unchanged P43–P66 including all frozen-prefix
  checks, independently encodes68 literal words and models72dispatches,
  exact GPR/LR/PC/ABI/history/whole DATA/TLS/deferred outputs and counts.
  Additional independent in-flight event requires held lock/prior history/
  input r3 unchanged at native call260 with LR10038 before unlock; three
  role-alternating blocking handoffs and source wiring/cleanup assertions.
- test_p67_pair.py reuses P66 shim construction WITHOUT its workload.
  Extracts exact P67, native spinlock bodies/binder argument/result macros,
  native CPU test_stopped, unchanged bounded exec_task/helper and TLS/slot
  helpers. CPU check_state/debugger atomic wait/VM/atomic BE storage/registry/
  queues/decoders/instructions are explicitly HOST MODELS; native CPU wait
  is not claimed from host compilation. Modeled BE lock accesses are ordered
  by this controlled pause, not an arbitrary-contention atomic model.
  G++C++20 Wall/Wextra/Werror pthread ASAN+UBSAN detect_leaks0 PASS:
  8runs/16retained workers/576slices/24live pause snapshots, exactly3pause
  handoffs perrun,21calls/165ordinary instructions/38queuepubs+callbacks/
  all store/lifecycle/log counts. Applicable foundational faults and168..185
  retained; new186..200 detect missing wait publication,early success/input
  change,blocked CIA/LR/current-function/history/FPR/VR/CR/reservation damage,
  premature own output/TLS/neighbor writes,missing pause clear and failed
  unlock. All5allocation/setup/production TLS guard negatives/config restore
  retained. Faults only in host models; delivered native has no injected bugs.
- Build86 all65 native phases verified;66unique UI/export symbols P2–P67,
  plist87/minimum iOS16.0/47unchanged patches/exact frozen prefix/Python
  syntax/git whitespace verified. Scratch p67-fixture-check.log and
  p67-host-check.log. No native SDK/Xcode in local runtime; CI/native phone
  run required to prove the new CPU check_state/atomic wait integration.

Remote baseline mainbecb2d60d1d6c84963809b3b61629b20b54a569e,
tree9839c2ca9c8ab8957035a05be01e39d2eb78e8a1. Standing continuation and
observed native P66 PASS authorize Build87 push. Preserve remote100755
script modes; verify baseline tree plus seven intended changes. DO NOT
query/monitor Actions after push; user reports outcome. Install
ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, run all66diagnostics, send
startup log. No P68 until native P67 PASS. This is a controlled native CPU
debugger-pause handoff, not arbitrary spinlock contention/weak-memory stress
or LV2 mutex scheduling. Retry-again cancellation/resumption,global HLE
table/import loader,renderer/firmware/game boot remain untested. Preserve
Midnight Club Los Angeles goal without promising compatibility or timing.

## 2026-10-12 — Build87 native PASS; Build88 / P68 interrupted native lock replay

User supplied ARMSX3-startup-20261012-014108-316-8856.txt, scratch upload,
LibraryID libfile_4c1117adcf4c8191bb14b38f40b49570. Build87 header and
all66 unique P2–P67 AUTO PASS verified, final all-stage PASS, no FAIL.
P67 starts1791769265.642096, ends9265.645120 (~3.0ms).
First roles0/1/0, counter2/4/6,checksum3/10/21,TLS1/2/3 each;
results1/6,6/1,1/6. Actual native held-lock busy path, CPU debugger pause/
wait publication/live snapshot, real guest unlock and native lock resumption
now confirmed on phone. No game boot claimed.

Build88 appends ONLY armsx3_core_test_interrupted_spinlock_replay and an
extern declaration for native thread-local g_tls_log_prefix. Full Build87
2067562-byte bridge prefix preserved byte-for-byte, SHA256
bb4853b5d2a063da159c72b9f2ba943bd72c72b04f0c968d33f17c3588de337b.
Prior P2–P67 implementation/tests,47 patches,upstream pin and build scripts
unchanged. Adds UI P68/plist88/CI test_p68_fixture.py,two new tests,root
handoff; seven intended changed files. No native service/core hook patch.

P68 keeps P67's exact68word/272byte guest program, SHA1
cacb3c02a2daa1324de32b0568f6a5f235c3bf35, and isolated registry/cache/
VM/TLS/two-worker setup. Changes the controlled held-lock handoff: the
pending native call is STOPPED before first worker unlocks, native lock
sets cpu_flag::again, binder must suppress false success and retain the
input r3/other args. It then exercises actual production cold fast_call
recovery, followed by a bounded retry of that same service address.
No serialized savestate file or actual title reload is involved.

Native primary PPUThread.cpp::fast_call/cpu_task::cia_call/cpu_on_stop,
CPUThread check_state, service/binder sources inspected. Native fast_call
only performs argument/CIA reload fixup when old_cia==0 and state&again;
old_cia nonzero takes another path and logs unimplemented HLE callstack
savestates. P68 deliberately uses production cia_call's cold setup:
loaded_from_savestate=true; fast_call(exchange(cia,0),gpr2,true). Native
loaded_from_savestate preserves the already-created guest BL return LR.
No global HLE table allocation needed; return sentinel is not reached on
this interrupted path. Native fast_call retains interrupt_thread_executing
and the replay module; diagnostic expects those instead of clearing them.

Only waiter slice8 enters this cold call. The outer diagnostic lock cache
wrapper sets coldActive and invokes actual fast_call while the original
bounded probe remains active. That nested exec_task dispatches the same
cache slot once; coldActive prevents recursive cold setup and its inner
wrapper requests dbg_global_pause before calling the unchanged registered
lock handler. Native busy-body check_state publishes wait as in P67.
First worker verifies full live context/input/PC10260/LR10038/history/
whole DATA/TLS/stacks and aliases while lock remains ABADCAFE. It then
adds reversible cpu_flag::stop and notifies, without unlocking yet.
Native check_state stops even with debugger pause set, clears wait and
calls actual ppu_thread::cpu_on_stop. The held lock returns {}, sets again;
native bind_result sees again and does NOT write success0 to r3.
Binder's stop processing clears current_function; interrupted history
therefore has null func_name, CIA10260,error23000,four original args.
last_function remains sys_spinlock_lock; BIND_FUNC_WITH_BLR leaves CIA10264
and records current_module=sysPrxForUser instead of returning via LR.
Stop-related 'aborted' or perf-stat logs are expected for this intentional
interruption; diagnostic PASS/FAIL controls the result.

Inner wrapper publishes interrupted epoch and waits on a separate replay
gate. First worker acquires it, verifies stop/again/debugger flags with
wait cleared, preserved full GPR inputs/syscall args, false-success
suppression, native module/history/LR/CIA and unchanged guest memory,
then executes actual guest production unlock. Requires lock0 and PC108,
then publishes restart. Only AFTER the interrupted values are verified,
the inner wrapper deliberately dirties r3..r10 to BAD0000000000000+reg.
This is a diagnostic fault stimulus, not native service behavior. It proves
the real fast_call saved-argument copy matters rather than merely comparing
inputs that already match. No diagnostic argument repair is performed.
The inner wrapper returns with stop/again still set. Probe budget boundary
returns -2; actual fast_call::at_ret restores all eight syscall_args into
r3..r10 and rewinds CIA10264→10260. It consumes loaded_from_savestate and
restores caller logging prefix/current_function; interrupt/module retained.
Outer wrapper compares native restored prefix, counts fixup and returns.
Its RAII additionally restores logging prefix/coldActive on exceptions.
After bounded helper returns, waiter verifies production fixup/CIA/module/
flags, then clears ONLY reversible stop/again/debugger control flags and
notifies. CIA/GPR/LR are not repaired. Next queued slice starts at10260;
registered lock retries uncontended, returns CELL_OK through real HLE ABI,
and guest writes success/protected values/output/unlock/TLS exactly once.

Both controller roles exercised: owner controls stopped peer tx1/3; peer
controls stopped owner tx2. Acquired wait/interrupted/restart/completion
epochs order every cross-thread read. Existing deadline/cancel/exit/notify/
stop/join guards kept; peer joins before TLS free,owner before VM/cache
teardown. Clear stop/again before returning worker callback to normal queue,
so retained workers survive. Program has exactly3fixups/3interrupted calls.
Native fast_call, bounded scope nesting and cpu_on_stop are real functions,
not equivalent recovery code duplicated into CoreBridge.

Budgets first unchanged[1,1,1,2,1,6,5,2,1,2,3,1]; waiter now
[1,1,1,1,1,3,4,2,3,8,7,6]. Waiter PCs
[136,140,144,148,24,32,44,52,260,84,108,272]. Slice8 paused/replayed
input r3=23000 and lock0; slice9 retry then counter store yields lock
ABADCAFE/counter+2,checksum waits untilslice10 as before.72dispatches/
66budget pauses/192bounded steps=165ordinary guest instructions+24actual
HLE calls+3extra outer diagnostic dispatches.21guest BL calls.3initialize,
3uncontended initial lock,3interrupted held lock,3successful retry lock,
6busy trylock,6unlock; interrupted attempts do not write lock or guest
output. Guest/native write counts unchanged from P67. Histories now11/13
for workers0/1, transaction bases0/0→3/5→8/8; aborted history counts once,
retry adds one further record. Final counter6/checksum21/TLS3/3/lock0,
transaction results1/6,6/1,1/6. Full retained GPR/FPR/VR/status/reservation/
CIA/LR/history/ABI/module/interrupt/context snapshots and VM/TLS/cache/
aliases/stack guards still checked at every normal boundary.

Validation PASS:
- test_p68_fixture.py chains all unchanged P43–P67/frozen prefixes, checks
  exact68words/SHA1, independently models192steps/24service records, live
  held event, stopped history/no-success preservation, deliberate volatile
  clobber/saved-input restoration/CIA rewind and fresh retry. Every normal
  PC/LR/GPR/ABI/history/DATA/TLS/deferred output and write count checked.
- test_p68_pair.py builds P67 host models WITHOUT its workload and extracts
  native CPU test_stopped, exact cpu_on_stop and fast_call plus unchanged
  spinlock service/binder/TLS/bounded helper/exec_task bodies. Host CPU
  check_state model now handles STOP priority over debugger pause and calls
  extracted cpu_on_stop; native CPU check_state/atomic waits/VM/registry/
  names/log formatting/queues/instructions remain explicitly HOST MODELS.
  Minimal model function-manager return address0 suffices for this aborted
  path; global HLE return table is not tested here.
  G++C++20 Wall/Wextra/Werror pthread ASAN+UBSAN detect_leaks0 PASS:
  8runs/16workers/576slices/24native-fast_call recovery executions; all
  counts/logs/cleanup and allocation/setup/TLS guard negatives retained.
  Applicable foundational/168..198/200 faults retained;199(single debugger
  pause-clear mutation) is inapplicable to new combined flag-clear path.
  Host-only mutation201..206 of extracted fast_call catches omitted arg
  copy,missing/double CIA rewind,bad restored logging prefix,damaged saved
  arg/token and missing loaded-state LR preservation. With fault0 native
  operations execute unchanged; these mutation branches are NOT delivered
  in native core or services. Restored-input proof uses deliberate clobber
  in diagnostic after cancellation verification, described above.
- Build87 all66 native phases verified,67unique UI/export symbols P2–P68,
  exact frozen prefix/plist88/minimum iOS16.0/47unchangedpatches/Python
  syntax/whitespace PASS. Scratch p68-fixture-check.log,p68-host-check.log.
  Native new phase compile/device execution still PENDING user outcome.

Remote baseline main79ba4ce767ba5f0687f32756dd94804a9f96712b,
tree6e60feab1aead7ce97027f6cb656874f68b0199f. Standing continuation and
observed P67 native PASS authorize Build88 push. Verify baseline plus seven
changes, preserve remote100755 scripts. DO NOT monitor/query Actions after
push; user supplies result. Install ARMSX3_iOS16_INSTALL_THIS_IPA via
TrollStore, run all67diagnostics, send startup log. No P69 before native
P68 PASS. Serialized savestate reload/arbitrary contention/LV2 mutex
scheduling/global HLE table/import loader/weak-memory stress/renderer/
firmware/game boot remain untested; Midnight Club Los Angeles goal retained.

## 2026-10-12 — Build89 / P69: native LV2 mutex ownership and lifecycle

Latest actual phone evidence: ARMSX3-startup-20261012-031751-457-9697.txt,
pid9697, Build88. ALL67 stages P2–P68 AUTO PASS in order, final all-stage
PASS, no FAIL. P68 tx1/2/3 first roles0/1/0, counter2/4/6 checksum3/10/21
TLS1/2/3, results1/6,6/1,1/6. Deliberate native sys_spinlock_lock aborted
messages are expected cancellation evidence. Earlier pid9270 Build88 log
also passes. P68 phone PASS authorizes next diagnostic; game boot untested.

Build89 appends armsx3_core_test_lv2_mutex_ownership(), P69 UI stage and
fixture chain; plist89/minimum iOS16.0. CoreBridge Build88 prefix is preserved
byte-for-byte:2123739 bytes SHA256
7efd56cb6a9ae22e24b83cab553a635cc0173dea779deca9e3e3fca7bc37570f.
All47 patches and upstream pin92b931b9fb5eef7f1317cb482917dfc19aceebd9
remain unchanged. Authoritative handoff is this ROOT file, not nested copy.

Native path: guest SC(0) uses actual interpreter SC handler, normal
ppu_execute_syscall/g_ppu_syscall_table/BIND_FUNC and real sys_mutex_create,
sys_mutex_destroy, sys_mutex_trylock, sys_mutex_unlock. Read-only handler/name
checks for codes100/101/103/104. No global table mutation, syscall fixture
hook, copied native service bodies, blocking sys_mutex_lock(102), or new core
patch. Two retained named_thread<ppu_thread> contexts keep real production
TLS/queue/bootstrap/stop/join helpers. Private nonrecursive FIFO mutexes,
NOT_PROCESS_SHARED/NOT_ADAPTIVE, key0, flags0, native-endian name iOSMutex.
The 40-byte zero-initialized attribute lives23040; real guest ID output23000.
Require initially empty native mutex namespace; preserve existing objects
when that guard rejects. IDs are read from actual native output, checked
against85000000 type prefix; no predicted cookie/uniqueness requirement.

Ten guest words/40bytes, SHA1 02e9f1e9d5ec6989fede817305bc7086af199b3c:
LWZ r3/r4/r11 from request r5; SC0; STW r3 to result r6;
LWZ/ADDI/STW own TLS count using r13-6ff4; STW count to result+4; NOP.
Requests21000+call*40hex+worker*20hex; results20200+call*20hex+worker*10hex.
Host writes only request inputs, never native mutex owner/result/TLS outputs.
Pause budgets3/1/6 give exact CIA offsets12/16/40: beforeSC, afterSC before
guest result stores, then6steps completed. Each new request initializes
register inputs once; later callbacks require complete unchanged context.
Full32GPR/CTR/LR/CIA,FPR32/VR32/status4/reservation128 and native syscall
history/latest args/8saved syscall args checked. Errors sign-extend s32 into
r3/history64; guest STW stores32bits. RestoreID RAII restores id_manager::g_id
TLS scratch after bounded calls because native object creation updates it;
this preserves worker infrastructure without repairing guest registers.

Three mutex lifecycles, first worker roles0/1/0. Paired calls by operation
(first worker / second worker):
0 create OK / create null-output EFAULT;
1 acquire OK / invalid0 ESRCH;
2 self try EDEADLK / peer try EBUSY;
3 destroy held EBUSY / wrong-owner unlock EPERM;
4 release OK / invalid0 ESRCH;
5 invalid0 ESRCH / second acquire OK;
6 wrong-owner unlock EPERM / second self try EDEADLK;
7 destroy held EBUSY / second release OK (busy destroy explicitly ordered
before release during SC slice; all other paired slices released together);
8 destroy OK / invalid0 ESRCH;
9 destroy stale ESRCH / try stale ESRCH.
At every paired boundary read actual IDM object owner/metadata/exists1,
reserved0/empty sleep queue/lock_count0/cond_count0/protocol/name and exact
namespace cardinality. Verify whole DATA/TLS/stacks/code, privileged aliases,
decoded cache and untouched guards. Stale handle checks precede new creation.

60 actual guest SC calls: create6,destroy12,trylock30,unlock12;
180dispatches/120pauses/600guest instructions/180guest STW
(120result/TLS-output stores +60own TLS stores),3native ID stores.
90peer jobs +peer exit +owner entry =92queue publications/callbacks.
Exactly2worker constructions/joins; TLS10/10→20/20→30/30 and results6/6
after each lifecycle. Peer joins before TLS free; owner joins before VM/cache
teardown. MutexCleanup declared before worker guards, so on failure it
withdraws only isolated diagnostic mutexes AFTER both workers join and calls
native on_id_destroy for key0. Normal final namespace must already be empty.
Settings restored on all paths, including reservation max0/RSX reservation
disabled during bounded probe. Final log explicitly limits this evidence.

Validation PASS:
- test_p69_fixture.py chains unchanged P43–P68/frozen prefixes, independently
  decodes exact10words and models all60SC calls/errors/ownership/ID lifetimes,
  600steps/120pauses/deferred outputs/TLS/full scalar GPR/PC/LR/CTR/history/ABI,
  whole DATA/TLS and180guest stores. Build88 phone log all67PASS verified.
- test_p69_pair.py constructs earlier host shims WITHOUT rerunning spinlock
  workload, extracts exact four native mutex APIs and try_lock/try_unlock,
  SC lambda, normal dispatcher/name/lookup, binder, bounded exec_task and
  production TLS helpers. CPU/VM/ID allocator/storage/atomic control/notify/
  registry/table shape/queue/decoder remain explicit HOST MODELS; native
  service/binder bodies execute on those models. G++ C++20 Wall/Wextra/Werror,
  pthread, ASAN+UBSAN detect_leaks0 PASS:8runs/16workers/1440paired slices,
  all call/store/usage/context/memory/TLS/cleanup counts. Applicable faults
  2..17,26,27,36..41,60,173..177,179,180 plus207..217 all detected;
  old172/181/182 spinlock-specific mutations are inapplicable and omitted.
  New host-only mutations cover wrong owner, false success for busy/self/
  wrong-owner/held-destroy, stale object retained, unsigned error ABI, bad
  published ID/protocol/exists/recursive count. Fault0 extracted operations
  unchanged; mutations are NOT delivered to native services. Allocation/
  setup/production TLS guards retained. Nonempty namespace negative preserves
  prior object/exists and rejects before CPU construction; host seed then
  removed by harness. All config restoration/cleanup checks pass.
-68unique P2–P69 UI/export symbols, exact frozen prefix, plist89/iOS16.0,
  47unchanged patches, Python syntax and git whitespace checks PASS.
  Scratch p69-fixture-check.log/p69-host-check.log. Local host checks cannot
  establish native16byte atomic implementation or LV2 scheduler behavior.
  No local Xcode/iOS SDK; native compile and P69 phone execution PENDING.

Remote baseline main753dd166dc1246f44511f2f01e95158ff1214cbf,
tree1e6864d2b6b86aac28deb4ee9608d586dcb636b4. Standing continuation and
observed P68 native PASS authorize Build89 push. Verify baseline plus seven
changes, preserve remote100755 scripts. DO NOT monitor/query Actions after
push; user supplies result. Install ARMSX3_iOS16_INSTALL_THIS_IPA via
TrollStore, run all68diagnostics, send startup log. No P70 before native
P69 PASS. Blocking LV2 mutex queues/recursive mutexes/serialized savestate/
weak-memory stress/import loader/renderer/firmware/game boot remain untested;
Midnight Club Los Angeles goal retained.

## 2026-10-12 — Build89 phone failure; Build90 repairs P69 registry initialization

Newest supplied log ARMSX3-startup-20261012-043501-722-10323.txt,
pid10323, Build89: P2–P68 all67AUTO PASS; P69 FAIL at first valid create.
Null-output create correctly returns CELL_EFAULT8001000d. Valid create
returns CELL_EAGAIN80010001, publishes no mutex handle, then diagnostic
reports missing handle and callback/final totals mismatch. P69 did NOT pass.
No next phase: Build90 reruns corrected P69, still68diagnostics P2–P69.

Root cause: stopped diagnostic core initializes selected FXO types on demand;
P69 used idm::select/import on id_manager::id_map<lv2_obj> without constructing
that map. Primary util/fixed_typemap.hpp reset fills unconstructed storage
with0xCC, get<T>() directly returns that storage and does not initialize it.
Native IdManager.h default map constructor initializes8192keys to typeumax
and highest_index0; allocate_id in IdManager.cpp requires those defaults.
Trap-valued highest_index/keys instead make allocation return nullptr;
lv2_obj::create propagates CELL_EAGAIN. Same explicit registry initialization
pattern already exists for memory-container diagnostic in patch0043.
Build89 host model incorrectly assumed every FXO type was already initialized,
so it did not expose this native prerequisite. Correct that model here.

Build90 adds explicit is_init<MutexMap>/init<MutexMap> for actual
id_manager::id_map<lv2_obj> BEFORE first namespace select, import or worker
construction. Initialization failure returns a named diagnostic error through
existing RAII cleanup. Existing initialized registry is reused; existing
mutex namespace still rejects without deleting those objects. No registry
reset, service replacement, predicted IDs, allocator bypass, or new core patch.
All P2–P68 bytes remain identical to Build88 frozen2123739-byte prefix;
P69 workload/opcodes/syscalls/ownership errors/counters/history/TLS/guard and
cleanup behavior otherwise unchanged. Plist90/minimum iOS16.0;47unchanged
patches and same upstream pin. App UI still has68unique exports/stages.

Validation PASS:
- Updated test_p69_fixture.py retains full P43–P68 chain, exact frozen prefix,
  all P69 independent guest SC ownership oracle and new init-before-first-use
  requirement. No change to expected60SC/600steps/180dispatches/120pauses,
  three lifecycles/TLS30/30/results6/6.
- Updated test_p69_pair.py explicitly models fresh/constructed LV2 registry,
  one construction across8successful runs, then failed initialization218 and
  host-only omitted-init219 negatives, followed by successful fresh recovery.
  All earlier applicable faults207..217/foundational failures, setup/TLS/
  cleanup/context/memory checks and nonempty namespace preservation pass.
  Extracted native service/binder/SC/dispatcher/TLS/bounded bodies unchanged;
  CPU/VM/ID storage/atomic control/notify/registry remain HOST MODELS.
- New test_p69_registry.py extracts actual native id_key class, id_map default
  member layout/constructor and allocate_id body from pinned source. Trap field
  values model0xCC storage WITHOUT illegal C++ object lifetime access and
  reproduce rejected allocation. Exact map default constructors then establish
  zero highest_index/free keys/null storage; actual allocator publishes correct
  IDs/types, reaches8192capacity, detects exhaustion, clears/reuses entries and
  advances invalidation cookies. Pointer/FXO storage and fixed-ID index helper
  remain shims; dynamic allocator/key/default initializers execute natively on
  host. ASAN+UBSAN/Wall/Wextra/Werror C++20 PASS. Workflow runs this regression
  against pinned upstream before patches. No iOS atomics/scheduler claim.
- Python syntax/git whitespace/frozen prefix/68UI exports/plist90 and native
  Build89 log failure ordering verified. Scratch p69-build90-fixture.log,
  p69-build90-host.log,p69-build90-registry.log. Native Build90 compile/phone
  execution PENDING; do not describe P69 as proven until new phone PASS.

Remote baseline main4fb33b6ecb22bbda60b69894df1226f6d062dee4,
treedd1374fd98f3f109066e06d214019034b33dc370. Standing continuation authorizes
Build90 correction push. Verify baseline plus seven changes, retain remote
100755 scripts. DO NOT monitor/query Actions after push; user supplies result.
Install ARMSX3_iOS16_INSTALL_THIS_IPA with TrollStore, run all68diagnostics,
send log. No P70 until native P69 PASS. Blocking LV2 mutex sleep queues,
recursive mutexes/serialized savestate/renderer/firmware/game boot untested.

## 2026-10-12 — Build90 native PASS; Build91 / P70 recursive LV2 mutex depth

Newest actual phone log ARMSX3-startup-20261012-123812-498-10632.txt,
pid10632, Build90: ALL68 phases P2–P69 AUTO PASS in order and final all-stage
PASS. P69 tx1/2/3 first roles0/1/0, TLS10/10→20/20→30/30, results6/6.
Valid native create now succeeds, all expected error results and object owner/
metadata/history/VM/TLS/cache/cleanup guards pass, zero native mutex IDs leak.
P69 duration1791808688.847351→8688.860722 approximately13.4ms (includes
expected service error logging). CELL_EFAULT/ESRCH/EDEADLK/EPERM/EBUSY log
messages are deliberately tested guest responses, not diagnostic failures.
This phone evidence confirms Build90 registry initialization fix. Game boot
still untested. P69 native PASS authorizes next P70 diagnostic.

Build91 appends armsx3_core_test_recursive_mutex_ownership(), new P70 UI
stage and test_p70_fixture.py chain. Plist91/minimum iOS16.0. Exact Build90
CoreBridge prefix preserved:2165582 bytes SHA256
a94cec9d79c2c6ea09b18308ab8a27248a1d9644a68d4db44310d5af9ef86efa.
All47 core patches/upstream pin unchanged; ROOT handoff authoritative.

P70 uses the proven P69 stopped-core, actual native mutex map initialization/
empty-namespace guard, retained two PPU workers/production TLS slots, real
SC0 interpreter/syscall table/binder/services, complete paused contexts and
VM/ID cleanup. No internal P69 workload invocation, global table mutation,
service body replacement, diagnostic owner/count writes, predicted IDs,
blocking mutex service, or new core patch. Attribute recursive flag is now
SYS_SYNC_RECURSIVE10 rather than NOT_RECURSIVE20; other private FIFO attributes
and name/key remain same. Actual sys_mutex_trylock native try_lock increments
lock_count for same-owner acquisition; native try_unlock decrements nonzero
count and returns WITHOUT clearing owner. Only next unlock with count0 clears
owner. Native count records additional acquisitions:0 means one owned level,
1 means two owned levels. Test validates that convention directly.

Three lifecycles first roles0/1/0, twelve paired operations each:
0 valid create / null-output EFAULT;
1 first acquire OK / invalid0 ESRCH;
2 first recursive acquire OK (count1) / peer try EBUSY;
3 destroy held EBUSY / wrong-owner unlock EPERM;
4 first partial release OK (count0 but owner retained) / peer try EBUSY;
5 first final release OK (owner0) / invalid0 ESRCH;
6 invalid0 ESRCH / second acquire OK;
7 wrong-owner unlock EPERM / second recursive acquire OK (count1);
8 destroy held EBUSY / second partial release OK (count0, owner retained);
9 destroy held EBUSY / second final release OK (owner0), explicitly ordered
busy destroy BEFORE final release on SC slice;
10 destroy OK / invalid0 ESRCH;
11 destroy stale ESRCH / try stale ESRCH.
All other paired slices run together. First-worker partial-release peer call
can occur on either side of decrement because ownership must remain held.
Second-owner partial-release destroy remains EBUSY in either order.

Same10guest words/40bytes SHA1 02e9f1e9d5ec6989fede817305bc7086af199b3c;
budgets3/1/6, CIA12/16/40. Native dynamic IDs read from guest output; stale
checks precede next creation. Request/output regions stay disjoint for36calls
per worker. Every paired boundary verifies exact native owner AND recursion
count, exists1/protocol/recursive/adaptive/key/name/cond_count0/empty sq and
namespace size. Complete GPR/FPR/VR/status/reservation snapshots, signed
r3/history/error results, actual syscall names/8arguments, deferred outputs,
whole DATA/TLS/stacks/code/cache/privileged aliases and untouched guards kept.
RestoreID preserves native allocation scratch; guest contexts not repaired.

72SC calls, usage100create6/101destroy15/103trylock33/104unlock18;
216dispatches/144budget pauses/720guest instructions.216guest STW
(144output words +72own TLS increments),3native ID writes.
108peer slice jobs +peer exit +owner entry =110pubs/callbacks;
exactly2worker constructions/joins. TLS12/12→24/24→36/36, results6/6.
Peer join before TLS free; owner join before VM/cache teardown; isolated
mutex cleanup after both joins on exceptions, normally namespace already
empty. Registry initialized conditionally/reused, never reset; nonempty
namespace rejected preserving objects. Settings/config restored on all paths.

Validation PASS:
- test_p70_fixture.py chains all unchanged P43–P69/frozen prefixes, freezes
  complete Build90 prefix, checks exact guest words and independently models
  recursion increments/partial and final releases/all ownership/error/handle
  transitions,72SC/720steps/144pauses, every scalar context/history/ABI/PC/LR/
  CTR/deferred output and whole DATA/TLS36/36, all216guest stores. Requires
  registry initialization before lookup and two retained CPU constructions.
- test_p70_pair.py adapts P69 host harness construction without running P69
  workload. Extracted native service/binder/SC/dispatcher/TLS/bounded bodies
  retained, exact native recursive try_lock/try_unlock branches executed.
  Independent expectations for110pubs/720instructions/72TLSstores/144output
  stores and actual syscall usage/logs. G++C++20 Wall/Wextra/Werror pthread
  ASAN+UBSAN detect_leaks0 PASS:8runs/16workers/1728paired slices plus fresh
  registry recovery, all guards/contexts/memory/counts/cleanup.
  Applicable foundational/207..219 fault set retained, except209 nonrecursive
  self-deadlock false-success mutation inapplicable. New host-only220 omits
  recursive increment,221 omits partial-release decrement,222 wrongly returns
  EDEADLK for recursive acquisition, all detected. Fault0 native method
  operations unchanged; these mutations are NOT delivered to native services.
  Fresh registry construction/reuse/rejected init/omitted init/nonempty namespace
  preservation and allocation/setup/TLS negatives remain covered.
  CPU/VM/ID allocator/storage/atomic control/notify/FXO/registry/queues/decoder
  remain explicitly HOST MODELS. Build90 test_p69_registry.py unchanged and
  retained in workflow for native key/map-default/allocator regression.
- Native Build90 phone all68PASS verified,69unique UI/export symbols P2–P70,
  exact2165582-byte prefix,47unchanged patches/plist91/iOS16.0/Python syntax/
  git whitespace PASS. Scratch p70-fixture-check.log,p70-host-check.log.
  No local Xcode/iOS SDK; new P70 native compile/phone execution PENDING.

Remote baseline maindfdc6959beb1c7e3d1c2b06cca7d4bd116599731,
treecb4101caf3a61fef48b1a26f3906d704aef6b5b2. Standing continuation and
P69 native PASS authorize Build91 push. Verify baseline plus seven files,
preserve remote100755 scripts. DO NOT monitor/query Actions after push;
user supplies result. Install ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore,
run all69diagnostics, send log. No P71 before native P70 PASS. Blocking LV2
sleep queues/recursive overflow/serialized savestate/import loader/renderer/
firmware/game boot remain untested; Midnight Club Los Angeles goal retained.

## 2026-10-12 — Build91 native PASS; Build92 / P71 production mutex-lock immediate paths

Latest supplied phone log ARMSX3-startup-20261012-144853-456-11372.txt,
pid11372, Build91: ALL69 stages P2–P70 AUTO PASS in order, final all-stage
PASS, no FAIL. P70 tx1/2/3 first roles0/1/0, TLS12/12→24/24→36/36,
results6/6, actual recursive count/partial release/retained owner/full release
and native-ID cleanup PASS. Duration1791816530.516471→6530.531632 ~15.2ms
including expected service-error logging. P69 also still passes. Game boot
untested. P70 native PASS authorizes P71; same two-worker architecture.

Build92 appends armsx3_core_test_mutex_lock_fast_paths(), adds UI P71 and
test_p71_fixture.py chain, plist92/minimum iOS16.0. Exact Build91 CoreBridge
prefix remains2207638bytes SHA256
151c3c28cdd5377a146607c96142adca3913f08fc61169fac8cdad04350c4fe0.
All47 patches and upstream pin unchanged. ROOT handoff remains authoritative.

P71 extends proven P70 ownership test to actual sys_mutex_lock syscall102
through normal guest SC0/interpreter/table/binder/service. Read-only table/name
check now covers100/101/102/103/104. The full production sys_mutex_lock service
executes its initial IDM lookup/try_lock branches: immediately acquired free
mutex, same-owner recursive acquisition, and invalid-ID ESRCH. Peer-held
requests still use sys_mutex_trylock103 and EBUSY, so the new syscall102 never
queues or sleeps. This phase explicitly proves only its immediate branches,
not sleep/wake/timeouts. No copied core service, custom table, object-state
injection, scheduler bypass, or new patch. Existing recursive counts/partial
and final releases/error/destroy/stale guards retained.

Guest argument loading changes from three LWZ to LWZ r3,r5,0;
LD r4,r5,8; LWZ r11,r5,4. Remaining SC/result/TLS/NOP words unchanged.
Exact10words/40bytes SHA1 6fb8b669d0f97364f3ece4e1171767e2f5ca3a21.
Each host-written INPUT descriptor is16bytes: BE32id/output pointer, BE32code,
BE64second argument. Creation uses attribute pointer23040; other non-lock
second arguments0. Lock102 uses timeout sequence0,1122334455667788,
FEDCBA9876543210 selected(call+worker)%3. New job arguments use u64 so the
full timeout survives input setup, r4, saved8argument ABI and history. Native
method takes u64 timeout; these values do not wait because each request
succeeds immediately or rejects invalid ID. No expiry claim.

Same twelve paired operations and recursive lifecycle as P70, but first
worker ops1/2/6 and second worker ops1/6/7 call102 instead of103. Per lifecycle
four successful immediate/recursive lock calls and two invalid-lock ESRCH;
three lifecycles give12successes+6invalid-lock calls. Other held-peer probes
use103; wrong-owner unlock EPERM, partial release retains owner, final release
permits handoff, held destruction ordered before second final release at
op9/SC, successful destroy/stale handles still checked. First roles0/1/0.
All native object owner/count/metadata/exists/queue and complete paused CPU
context/history/ABI/data/TLS/stacks/aliases/cache/ID/TLS/config/VM cleanup
guards kept; zero native mutex IDs leaked required. Registry conditional
construction/reuse/nonempty rejection preserved from Build90.

72actual guest syscalls:100create6/101destroy15/102lock18/103trylock15/
104unlock18.216dispatches/144budget pauses/720guest instructions;
216guest STW (144output+72TLS),3native-ID writes.108peer slice jobs+exit+
owner entry =110pubs/callbacks;2worker constructions/joins. TLS12/12→24/24→
36/36, results6/6. Pause budgets3/1/6 still exact CIA12/16/40. Host input
descriptors now16bytes, output layout unchanged and disjoint for all36calls.
Join/stop/TLS free/mutex exception cleanup/cache/VM/settings guards unchanged.

Validation PASS:
- test_p71_fixture.py chains unchanged P43–P70/frozen prefixes, freezes whole
  Build91 prefix, independently decodes exact LD/LWZ/SC words and models all
  immediate/recursive lock/try/error/partial-release/destroy/handle transitions,
  full64descriptors/timeouts/r4/ABI/history,72SC/720steps/144pauses/216stores
  and whole DATA/TLS36/36/scalar context/PC/LR/CTR at every boundary.
- test_p71_pair.py adapts earlier explicit host shims without running previous
  phase workloads; extracts all FIVE native mutex service bodies including
  complete sys_mutex_lock, actual lock methods/SC/binder/dispatcher/TLS/
  bounded execution. Sleep/queue/busy-wait/timeout interfaces are compile-only
  host stubs that throw if entered; no scheduler execution is modeled here.
  Inherited host decoder already implements LD. GPR cast host shim unified
  to match signed error and full64argument conversions without ambiguous
  old overloads; native binder code still extracted. CPU/VM/ID storage/atomic
  control/registry/FXO/notifications/queues/decoder/GPR casts remain models.
  Native logger overload observes actual u64 timeout parameter in extracted
  sys_mutex_lock and compares it with guest r4,18observations per successful
  workload. C++20 Wall/Wextra/Werror pthread ASAN+UBSAN detect_leaks0 PASS:
  8runs/16workers/1728paired slices plus fresh registry recovery. All counts,
  lifecycle/errors/contexts/memory/TLS/cleanup checked. Applicable faults
  retained from P70, plus22guest LD mutation,223host-only skipped real lock
  acquisition,224host-only truncated u64 argument cast; all detected. Native
  timeout observation detects224 even when r4/history still retain full64.
  Recursion220..222 and registry218/219/setup/TLS/nonempty preservation
  negatives still pass. Fault0 extracted service/method operations unchanged;
  mutations are NOT delivered to native core. Native scheduler/atomics unproven.
- Native Build91 log all69PASS/three exact P70 transactions verified;
  70unique UI/export symbols P2–P71, whole2207638-byte frozen prefix,
  plist92/iOS16.0/47unchanged patches/Python syntax/whitespace PASS.
  Scratch p71-fixture-check.log,p71-host-check.log. Local Xcode/iOS SDK not
  available; P71 native compile/phone execution PENDING.

Remote baseline main177bcfff35a6ff36f068ffae79233d52ccc2124f,
tree468d87c0d832f9d76e5b45edb780b16b642ae12f. Standing continuation and
P70 native PASS authorize Build92 push. Verify baseline plus seven changes,
preserve remote100755 scripts. DO NOT monitor/query Actions after push;
user supplies result. Install ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore,
run all70diagnostics, send log. No P72 before native P71 PASS. Blocking LV2
sleep queue entry/wake/timeout expiry/recursive overflow/serialized savestate/
import loader/renderer/firmware/game boot remain untested; Midnight Club Los
Angeles goal retained.

## 2026-10-12 — Build92 native PASS; Build93 / P72 contended LV2 mutex sleep/wake

Latest actual phone log ARMSX3-startup-20261012-162613-812-11640(1).txt,
pid11640, Build92: ALL70 phases P2–P71 AUTO PASS in order, final all-stage
PASS, no FAIL. P71 tx1/2/3 first roles0/1/0, TLS12/12→24/24→36/36,
results6/6. Eighteen native sys_mutex_lock calls/12immediate successes/6invalid
ESRCH and full64 timeout ABI/history/object/context/cleanup PASS. Expected
service-error logs are tested guest responses, not diagnostic failure.
P71 native PASS authorizes next P72. Game boot remains untested.

Build93 appends armsx3_core_test_mutex_sleep_wake(), adds UI P72 and fixture
chain, plist93/minimum iOS16.0. Exact Build92 CoreBridge prefix preserved:
2250420bytes SHA256 c0770ffff9e5b9ab6de78cf9dfc6b2b9d1dd10e45d9772d91cd853ef19d068ac.
All original47 patches unchanged; new patch0048-ios-lv2-mutex-sleep-wake-probe
adds narrow iOS diagnostic scope/observation helpers in lv2.cpp/sys_sync.h.
Total48 patches, same upstream pin. ROOT handoff authoritative.

P72 keeps proven P71 guest code10words/40bytes, SHA1
6fb8b669d0f97364f3ece4e1171767e2f5ca3a21, BE32ID/BE32code/BE64arg input
layout, full64 timeout tests, budgets3/1/6/CIA12/16/40, actual SC0/syscall table/
binder/five mutex APIs and native object/TLS/context/memory/cleanup guards.
No global syscall table mutation, service replacements or copied equivalent
locking code. Workload changes second worker op5 from invalid try to actual
sys_mutex_lock(handle,0) while first still owns, and second op6 becomes
invalid try ESRCH. First op5 is real guest unlock104. Thus each transaction
has one real contended zero-timeout lock and native release/reown/wakeup;
remaining first/second recursive ownership checks continue as before.
After op5/SC second owns with count0; op6 leaves that ownership intact;
op7 recursively acquires count1, op8 partial release count0, op9 full release
with first busy destroy explicitly ordered before release, op10 destroy,
op11 stale ESRCH. First role0/1/0 exercises blocked peer and blocked owner.

First worker's runGuest callback waits BEFORE its unlock SC until actual
IDM mutex control.owner equals that worker, control.sq equals waiter and
lock_count0, plus new native observation confirms scheduler removed waiter:
g_ppu is holder alone, no next_ppu/next_cpu, waiter wait+suspend, no signal/
again/exit, scheduler ready, no pending/startup/timeout queues. Observation
uses native scheduler mutex and atomic CPU flags, synchronized with native
sleep_unlocked's removal. It reads NO live waiter guest GPR/history. Holder
then compares full DATA/TLS and aliases with expected pre-SC bytes (no guest
output/TLS stores during blocked service), increments observation and runs
real guest unlock. Native try_unlock detects queue, reown/FIFO transfers
owner, awake/schedule_all clears suspend and signals waiter; real lock body
consumes signal and returns success once. Post-boundary checks require exact
signed ABI/history/context/memory, new second owner/count0 and empty queue.
Three observations required, no sleep/signal/again flags left after service.
Deadline/cancel guard stops/notifies waiter on observation failure so both
roles can unwind without waiting indefinitely for an unlock.

Patch48 scope requires stopped core/current controller, two slots/static
interpreter, exact stacks30000/40000 size8000, quiet empty native scheduler
queues/unready state and clean worker scheduling fields. Saves both native
priorities/start/end timestamps/global priority tag, calls actual awake for
both then make_scheduler_ready, invokes diagnostic work. Work lambda joins
peer on success and exceptions BEFORE scheduler restoration; outer existing
peer guard still handles construction/setup failure. Checks final pair
membership/empty waiting/startup queues/no suspend/signal/again/CPU linkage.
Restore unqueues only pair, removes only their timeout/startup entries, clears
pair links/sleep-signal flags/cancel scratch, restores priorities/tag/times
and prior unready scheduler state. Successful path explicitly finishes
restore and checks native empty queue/ready flag/priorities/tag/timestamps;
exception destructor executes same restore. Existing unrelated scheduler
state is rejected before activation and preserved. MutexCleanup still runs
AFTER both worker joins; zero native mutex IDs required on normal path.
Native service and existing scheduler implementations unchanged by patch.

72syscalls:100create6/101destroy15/102lock18/103trylock15/104unlock18;
9immediate/recursive lock successes +3queued successes +6invalid-lock ESRCH.
216dispatches/144budget pauses/720guest instructions/216guest STW
(144output words+72TLSincrements)/3native ID stores.110pubs/callbacks,
2worker constructions/joins. TLS12/12→24/24→36/36, results6/6. Peer joins
before TLS free and scheduler restoration, owner joins before VM/cache and
mutex exception cleanup. All code/DATA/TLS/stacks/aliases/cache/full paused
register/status/reservation/history/settings/ID infrastructure checks kept.

Validation PASS:
- test_p72_fixture.py chains unchanged P43–P71/frozen prefixes and freezes
  entire Build92 prefix. Independent scalar queue model enters held lock
  before unlock, leaves whole DATA/TLS unchanged while queued, transfers owner
  on release and resumes waiter once; three queue handoffs/full64 ABI/history/
  owner/count/errors/handle lifetime/PC/LR/CTR and all720steps/144pauses/
  216stores/72SC/whole DATA/TLS checked. No native scheduler claim from oracle.
- test_p72_pair.py adapts P71 host harness WITHOUT running earlier workloads.
  Extracts actual five service bodies including full lock, native try_lock/
  try_unlock/try_own/reown/FIFO schedule/unqueue, SC/binder/dispatcher/TLS/
  bounded bodies, plus exact new native scope/observation bodies (host counter
  instrumentation counts observations). Sleep/awake/ready/CPU/VM/ID/atomic
  control/priority/notifications/FXO/queue/decoder/GPR casts are explicit HOST
  MODELS. Actual lv2_obj sleep_unlocked/awake_unlocked/schedule_all/CPU waits
  and ARM16-byte CAS are NOT executed locally; iOS build executes them.
  C++20 Wall/Wextra/Werror pthread ASAN+UBSAN detect_leaks0 PASS:
  8runs/16workers/1728paired slices plus fresh registry recovery;3modeled
  sleeps/wakes and18native timeout parameter observations per successful
  workload; all contexts/memory/results/counts/cleanup/global scope restore
  verified. Applicable foundational/207..224 and LD22 faults retained.
  New225 omits queue insertion,226 omits scheduler removal,227 omits signal,
  228wrong owner on reown,229early guest result mutation while asleep,
  230bad restored priority and231bad restored end_time all detected.
  Mutations are HOST ONLY; fault0 native method/scope operations unchanged.
  Registry init/reuse/rejected init/omitted init/nonempty namespace/setup/TLS
  negatives retained. Prior scheduler-ready state negative rejects scope and
  preserves ready=true; harness clears its seed afterward, not native core.
- test_p72_patch.py applies original47 then patch48 to two pinned target files
  in temporary tree; preserves whole prior lv2.cpp as prefix, verifies only
  iOS helper declarations added to header, explicit guards/awake/ready/restore/
  queue observation structure, no syscall-table or mutex-service changes.
  Initial local check exposed an extra newline in the staged mirror; fixed
  generated patch against exact pinned EOF. Fresh upstream regression PASS.
  Workflow runs this patch regression before its actual full patch sequence.
- Build92 phone all70PASS/three exact transactions,71unique UI/export stages
  P2–P72, exact2250420-byte prefix,48patches/original47unchanged/plist93/iOS16/
  Python syntax/non-patch git whitespace/new patch added-line whitespace PASS.
  Unified diff context retains its required space/tab markers. Scratch p72-fixture-check.log,
  p72-host-check.log,p72-patch-check.log. No local Xcode/iOS SDK; native P72
  compile and real iOS scheduler/blocked syscall execution remain PENDING.

Remote baseline main0245304d0b69d7b1917df22698ece25d5cd547ff,
treebb2ab3f35ed23acc1842627b56766a05614a6498. Standing continuation and
P71 native PASS authorize Build93 push. Verify baseline plus nine files,
retain remote100755 scripts. DO NOT monitor/query Actions after push;
user supplies result. Install ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore,
run all71diagnostics, send log. No P73 before native P72 PASS. Arbitrary
multiwaiter contention/timeout expiry/cancellation replay/weak-memory stress/
recursive overflow/serialized savestate/import loader/renderer/firmware/game
boot remain untested; Midnight Club Los Angeles goal retained.

## Build 94 / P73 — timed LV2 mutex expiry (2026-10-12)

Authoritative phone evidence: ARMSX3-startup-20261012-185114-802-11780.txt
(Library libfile_91ee15a1e7448191812c55e829ab308a). Build93 completed ALL71
ordered diagnostics P2–P72, final all-stage AUTO PASS, no FAIL. P72 native
transactions1/2/3 had first roles0/1/0, TLS12/12→24/24→36/36, results6/6;
actual queue/suspend/guest unlock/reown/signal/lock return and scheduler
cleanup passed. Native P72 start1791831070.805675→finish1070.821611 (~15.9ms).
Game boot remains untested. This native PASS authorizes the next diagnostic.

Build94 appends armsx3_core_test_mutex_timeout_expiry / P73 and UI stage72;
bundle94/minimumiOS16.0. Whole Build93 CoreBridge prefix2298617 bytes frozen,
SHA2564140614afc034712917862c54845ff1398a302c30ead8a79550f5d86bab09f98.
All original48 patches and prior test files unchanged. Upstream remains
ARMSX2/ARMSX3 commit92b931b9fb5eef7f1317cb482917dfc19aceebd9. Patch49 adds
ONLY read-only iOS timeout-state/finished-state observers to lv2.cpp and two
sys_sync.h declarations. Existing service bodies, timers, scheduler, patch48
scope, guest clock/config and syscall table are unchanged.

P73 reuses proven isolated P72 scheduler pair, native PPU workers/production
TLS and recursive FIFO mutex. Calls real syscalls100/101/102/103/104 through
guest SC0→normal interpreter→production dispatcher/binder/services, without
injected ownership, timers, service hooks or table mutation. CODE10000,
DATA20000, stacks30000/40000 and TLS pool50000..90000 remain guarded. Exact
10words/40bytes SHA1=6fb8b669d0f97364f3ece4e1171767e2f5ca3a21:
LWZr3;LDr4;LWZr11;SC0;STWresult;LWZTLS;ADDI;STWTLS;STWTLScopy;NOP.
Sixteen-byte input contains BE32handle/output, BE32syscall, BE64secondarg.
Paired budgets3/1/6 require CIA12/16/40 and complete paused register/status/
reservation/history/8argument ABI/aliases/code/DATA/TLS/stack/cache checks.

Three12-operation mutex lifecycles, first roles0/1/0:
0 create / null-output EFAULT;1 lock / invalid-lock ESRCH;
2 recursive lock / try EBUSY;3 held destroy EBUSY / wrong unlock EPERM;
4 partial unlock retains owner / try EBUSY;
5 held destroy EBUSY / contended lock100000us returns CELL_ETIMEDOUT;
6 final unlock / fresh lock succeeds (explicitly release before acquisition);
7 wrong unlock EPERM / recursive lock;8 held destroy EBUSY / partial unlock;
9 held destroy EBUSY / final unlock (destroy before release);
10 destroy / invalid try ESRCH;11 stale destroy ESRCH / stale try ESRCH.
Other lock timeout args cycle0/1122334455667788/FEDCBA9876543210, full64 ABI.
Timed operation uses100000us (100ms), no strict wall-time threshold or clock
mutation. Timer expiry must retain first owner/count0 and remove mutex waiter;
next ordered acquisition becomes second owner/count0 without another sleep.

Holder observes native atomic owner/queue/count plus read-only scheduler
observer under real g_mutex: ready scheduler, no pending/startup work, exactly
one timed entry whose waiter/end_time matches and end-start=100000, active
holder alone, waiter wait+suspend and no signal/again/exit/notify/CPU links.
Whole DATA/TLS must still match while blocked; no live waiter GPR/history read.
Holder then executes guest held destroy EBUSY, leaving ownership intact.
Real native wait_timeout/check_state/cpu_sleep/awake resumes timed waiter;
actual sys_mutex_lock timeout branch unqueue<false> removes queue entry,
clears next_cpu and returns not_an_error(CELL_ETIMEDOUT). Native s32 error
still sign-extends through binder into GPR/history. After both SC callbacks,
second observer requires no waiting/startup entries, exact active pair and
clean suspend/signal/again/exit/notify/CPU links. Exact errors/ownership/history
checked before guest result and TLS stores. Three timed observations required.
Observation failure cancels gate/stops/notifies waiter to allow both joins.
Peer joins before TLS free and patch48 scheduler restoration; owner joins
before VM/cache/mutex exception cleanup. Existing registry initialization,
nonempty namespace guard and all global-state restoration remain enforced.

72SC:100create6/101destroy18/102lock18/103try12/104unlock18. Twelve successful
immediate/recursive locks,3timed ETIMEDOUT,3invalid lock ESRCH.216dispatches,
144budget pauses,720guest instructions,216guest STW (144outputs+72TLS),
3native ID stores,110publications/callbacks (108peer jobs+peer exit+owner entry),
2workers constructed/joined. TLS12/12→24/24→36/36, results6/6, zero mutex leaks.

Validation PASS:
- test_p73_fixture.py chains unchanged P43–P72 and freezes whole Build93
  prefix. Independent scalar guest oracle checks3registered timed requests,
  unchanged bytes while queued, holder destroy EBUSY before expiry, signed
  ETIMEDOUT/no transfer/queue removal, ordered release+fresh lock, all ownership/
  recursive/error/stale/handle states, full64 ABI/history/PC/LR/CTR, whole DATA/
  TLS and720instructions/144pauses/216stores/72SC. No native scheduling claim.
- test_p73_patch.py applies original48+49 to two exact pinned targets in a
  temporary tree; whole prior lv2.cpp prefix and header except2iOS declarations
  preserved. Deadline/queue/finished-state read-only observers verified; no
  GPR/service/table/state mutations. Workflow runs it before full patch apply.
- test_p73_pair.py adapts P72 harness without executing prior workloads;
  extracts real five APIs, native mutex lock timeout-unqueue branch/methods/
  FIFO/unqueue, binder/SC/dispatcher/TLS/bounded and exact patch48/49 helper
  bodies. CPU/VM/ID allocator/storage/atomic control/priority/actual guest clock/
  wait_timeout/CPU check_state/sleep-awake scheduler/notify/FXO/decoder/GPR casts
  remain explicit HOST MODELS. Real native wait_timeout and CPU scheduling are
  NOT locally executed. Modeled steady-clock timer registers100000us, modeled
  reschedule removes timer/restores pair; real extracted lock code then unqueues
  mutex and reports timeout. C++20 Wall/Wextra/Werror pthread ASAN+UBSAN
  detect_leaks0 PASS:8runs/16workers/1728paired slices plus fresh registry recovery;
  3modeled timed sleeps/reschedules,18native API timeout parameter observations,
  720instructions/110pubs/TLS36/36 each. Applicable foundation/207..224/LD22 and
  queue225..227/229/scope230..231 faults retained. Old228reown mutation and
  nonrecursive deadlock209 are inapplicable to this workload, not claimed.
  New232false timeout success,233missing mutex unqueue,234wrong deadline delta,
  235cleared holder ownership,236unremoved timer all detected. Mutations are
  HOST ONLY; fault0 extracted method operations unchanged. Unsupported mutated
  timeout throws in host model so negative cleanup can unwind boundedly.
  Registry init/reuse/rejected/omitted init/nonempty namespace preservation,
  allocations/setup/TLS guards and prior scheduler-ready seed preservation PASS.
- Phone71orderedPASS/3exactP72transactions;72unique UI/export stages;whole
  frozen bridge prefix;49patches/prior48unchanged;plist94/iOS16/Python syntax/
  nonpatch git whitespace/new native added-line whitespace PASS. Logs in scratch
  p73-fixture-check.log/p73-host-check.log/p73-patch-check.log. Host report range
  wording corrected afterward to exclude fault228; executable logic unchanged.
  No local Xcode/iOS SDK. P73 native compile/device execution remain PENDING.

Publication baseline mainacb8b84eb08c6ab1a651052d29f430cbb08c7343,
tree6af5b721054a56541c22ceaa3820de86ca9ee24b (167blobs). Publish9files,
4newblobs→171; verify hashes and preserve remote100755 script modes. Standing
continuation authorizes push. DO NOT monitor/query Actions after push; user
supplies result. Install ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, run all72
ordered diagnostics, send startup log. No P74 before native P73 PASS. Exact
wall-clock latency/timeout-unlock races/arbitrary multiwaiter/cancellation/
replay/weak-memory stress/recursive overflow/serialized savestate/import loader/
renderer/firmware/game boot remain untested; Midnight Club Los Angeles retained.

## Build 95 / P74 — timed mutex unlock and timer cancellation (2026-10-12)

Latest authoritative phone log ARMSX3-startup-20261012-212638-402-12096.txt
(Library libfile_10eb62624bc88191bac9703576183379) is Build94: ALL72 ordered
P2–P73 AUTO PASS, final all-stage PASS, no FAIL. Three P73 native timed expiry
transactions1/2/3 first roles0/1/0, TLS12/12→24/24→36/36, results6/6. Actual
100000us deadlines registered, ETIMEDOUT sign-extended, holder retained/count0,
mutex/timer queues empty, fresh acquisition and scheduler/ID cleanup allPASS.
P73 native start1791840395.299259→finish0395.619555 (~320.3ms for3timeouts;
observed duration, not a latency guarantee). Earlier212442-584-12077 attachment
was another Build93 ALL71PASS run, not P73 evidence. Build94 workflow97/run
38296906427 had succeeded; at user's request its single build job114970064542
was rerun successfully via GitHub API to regenerate deleted artifact (rerun
accepted, completion not monitored). No P74 before P73nativePASS, now satisfied.

Build95 appends armsx3_core_test_mutex_timed_wake / P74, UI stage73, bundle95,
minimumiOS16.0. Whole Build94 CoreBridge2347165-byte prefix frozen, SHA256
52167d36b34eee76b20ab389106ec352a5a9d16dd29fdff1866c4c7edc6df6b5.
All49 patches unchanged; patch48 scheduler scope and patch49 read-only native
deadline/finished-state observers reused. Upstream remains pinned
92b931b9fb5eef7f1317cb482917dfc19aceebd9. Native service/scheduler/timer bodies,
clock/config, ownership and dispatcher are unchanged and not injected/hooked.

P74 uses successful P72 lifecycle scaffold with a real timed request and
stronger finished-state check. Same2nativeworkers/productionTLS, recursive
FIFO mutex100create/101destroy/102lock/103try/104unlock through real guestSC0,
normal interpreter/production binder/table/services. Same10words/40bytes SHA1
6fb8b669d0f97364f3ece4e1171767e2f5ca3a21, CODE10000/DATA20000, stacks30000/
40000, TLS50000..90000, budgets3/1/6 and exactCIA12/16/40. Full paused GPR/FPR/
VR/status/reservation/history/8syscallargs/aliases/code/DATA/TLS/stacks/cache
checks retained. Descriptor16bytes BE32handle/output+BE32syscall+BE64secondarg.

Three12-operation transactions, firstroles0/1/0:
0create/nulloutputEFAULT;1lock/invalidlockESRCH;2recursive/tryEBUSY;
3helddestroyEBUSY/wrongunlockEPERM;4partialunlock retainsowner/tryEBUSY;
5holderfinalunlock/timedlock(handle,1000000us) SUCCESS;
6invalidlockESRCH/invalidtryESRCH;7wrongunlockEPERM/recursive lock;
8helddestroyEBUSY/partialunlock;9helddestroyEBUSY/finalunlock (ordered destroy
before release);10destroy/invalidtryESRCH;11staledestroyESRCH/staletryESRCH.
Other lock timeout args cycle0/1122334455667788/FEDCBA9876543210 as before.

At operation5 SC slice, waiter enters actual mutex queue and timed native LV2
sleep. Holder waits for owner/count0/queue and patch49 observer under native
g_mutex: exact one timer for waiter, end_time matches entry and end-start=
1000000, active holder alone, waiter wait+suspend/clean signal/again/exit/notify/
CPU links. Whole DATA/TLS remain unchanged; no live waiter register/history
reads. Then actual guest finalunlock transfers FIFO ownership via native reown/
awake, unregisters pending timer and signals waiter. Actual lock consumes
signal and returns CELL_OK. After both callbacks finish and peer returns to
real command queue, patch49 finished observer requires empty waiting/startup
queues, exact active pair and clean flags/links. Validate secondowner/count0,
empty mutex queue, success ABI/history/context before guest stores. Three
observations required, no timed failure accepted. Uses1s timeout for scheduling
margin; no strict wall-time threshold/claim. Deadline-boundary race not tested.

72SC:100create6/101destroy15/102lock18/103try15/104unlock18. Nine immediate/
recursive successes+3timed-wake successes+6invalid-lockESRCH.216dispatches,
144pauses,720instructions,216guestSTW (144outputs+72TLS),3nativeIDstores,
110publications/callbacks,2workersconstructed/joined. TLS12/12→24/24→36/36,
results6/6. Failure gate stops/notifies waiter for unwind. Peer joins BEFORE
TLS release and scheduler restore; owner joins BEFORE VM/cache/mutex cleanup.
Zero leaked mutex IDs and prior registry/settings/scheduler state preserved.

Validation PASS:
- test_p74_fixture.py chains unchanged P43–P73 and freezes entire Build94
  prefix. Independent scalar oracle adds1s timer registration for actual waiter,
  unchanged bytes while blocked, guest unlock transfers owner/removes timer,
  successful waiter continuation,3cancellations/no remaining timers. Checks all
  ownership/depth/errors/stale/handle lifecycles/full64 ABI/history/PC/LR/CTR,
  whole DATA/TLS and720steps/144pauses/216stores/72SC. Not native scheduling.
- Unchanged test_p73_patch.py again applies frozen48+49 to exact pinned targets
  and verifies previous implementations preserved/read-only observers PASS.
  Workflow now runs P74 fixture plus existing P73patch/P69registry checks.
- test_p74_pair.py adapts P73 host harness without running old workloads;
  extracts five native APIs/full lock branch/mutexmethods/FIFO/unqueue, guestSC/
  binder/dispatcher/TLS/bounded and native patch48/49 helper bodies. Actual guest
  clock/wait_timeout/CPU check_state/sleep-awake scheduler/VM/CPU/ID allocator/
  storage/atomic control/priority/notify/FXO/decoder/GPR casts are explicit HOST
  MODELS; native kernel timer and scheduler not locally executed.1s modeled
  timer, modeled awake cancellation; real extracted lock consumes signal and
  returns success. C++20 Wall/Wextra/Werror pthread ASAN+UBSAN detect_leaks0
  PASS:8runs/16workers/1728paired slices plus fresh registry recovery; per success
  3registered waits/3cancellations/zero modeled expiries/3successful native lock
  returns/18API timeout observations/720instructions/110pubs/TLS36/36. Applicable
  foundational/207..224/LD22 and queue225..229 (including reown228) and scope
  230..231 retained. Deadline234/timer-removal236 retained. New237false expiry
  on signalled lock,238timer registered to holder instead of waiter,239stale
  next_cpu link all detected. Expiry-only232/233/235 and nonrecursive deadlock209
  inapplicable, not claimed. Mutations HOST ONLY; fault0 extracted code unchanged.
  Registry init/reuse/rejected/omitted init/nonempty namespace/settings/setup/
  allocations/TLS guards and prior scheduler-ready preservation PASS. Host-only
  unsupported mutated timeout throws for bounded negative unwind. LSan disabled
  because runtime cannot inspect /proc under ptrace; ASAN/UBSAN remained enabled.
- Phone72orderedPASS/3exactP73transactions;73uniqueUI/export stages;whole prior
  bridge frozen;all49patches unchanged;bundle95/iOS16/Python syntax/git whitespace
  and exact1s native request/observer matching PASS. Scratch p74-fixture-check.log
  and p74-host-check.log. No local Xcode/iOS SDK: P74compile/device execution
  remain PENDING. Do not equate host model success with native timer success.

Publication baseline maind6702ce0a8dc56b039bd9c70f9c9b9dd5e1d0aea,
tree87dd51fd362850816bbfa0486b08c48548fa4a6a (171blobs). Publish7files,
2newtests→173blobs; verify all hashes/preserve remote100755 scripts. Standing
continuation and nativeP73PASS authorize push. DO NOT monitor/query Actions
after push unless user specifically requests an operation needing a run ID.
Install ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, run all73diagnostics, send
log. No P75 before nativeP74PASS. Exact wall-time latency/deadline-boundary unlock
races/multiwaiter/cancellation replay/weak-memory stress/recursive overflow/
serialized savestate/import loader/renderer/firmware/game boot remain untested.
Midnight Club Los Angeles goal retained.

## Build 96 / P75 — same-mutex timeout then timed wake reuse (2026-10-12)

Phone evidence ARMSX3-startup-20261012-214622-999-12165.txt (Library
libfile_147b3c5b130c81919f6a18b4fd66d816), also supplied as identical-named
run duplicate ARMSX3-startup-20261012-214622-999-12165(1).txt (Library
libfile_2d6487e42b148191a20b04a2801733c7). Original read header/tail via Library;
new attachment read locally and independently verified Build95 ALL73 ordered
P2–P74 AUTO PASS/final all-stage PASS/no FAIL. P74native transactions1/2/3:
roles0/1/0, TLS12/12→24/24→36/36, results6/6. Actual timed deadline registration,
guest unlock/reown/signal/success/pending timer removal and ID/scheduler cleanup
PASS. Native P74start1791841580.971345→finish1580.983964 (~12.6ms for3timed
wake lifecycles, observation only). P73 expiry also remains PASS in this run.
Standing continue authorization and nativeP74PASS permit next build.

Build96 appends armsx3_core_test_mutex_timeout_then_wake / P75, UI stage74,
bundle96/minimumiOS16.0. Entire Build95 CoreBridge2395588-byte prefix frozen,
SHA256d8f971381ef9347e4abe0c01c8ac138fb4d8a3a899891e978a9a6b98b1b05455.
All49 patches and all previous test files unchanged. Uses patch48 native pair
scope and patch49 read-only native timeout-state/finished-state observers.
Upstream pin unchanged92b931b9fb5eef7f1317cb482917dfc19aceebd9. No production
service/dispatcher/timer/scheduler/guest clock or ownership changes/hooks.

New workload composes native-proven P73 expiry and P74 timed-wake on the SAME
mutex handle and SAME waiter within each transaction, keeping holder active
between the two requests. Copies P73 isolated two-worker/TLS/guestSC scaffold
with two observed queued slices rather than one. Same recursive FIFO private
mutex, table100/101/102/103/104, CODE10000/DATA20000/stacks30000/40000/TLS pool
50000..90000, descriptor16bytes BE32handle/output+BE32syscall+BE64secondarg.
Same10words/40bytes SHA1=6fb8b669d0f97364f3ece4e1171767e2f5ca3a21, budgets
3/1/6, exactCIA12/16/40/full paused context/history/8arguments/reservations/
whole DATA/TLS/stacks/code/aliases/cache checks retained.

Three12-operation lifecycles firstroles0/1/0:
0create/nulloutputEFAULT;1lock/invalidlockESRCH;2recursive/tryEBUSY;
3helddestroyEBUSY/wrongunlockEPERM;4partialunlock retainsowner/tryEBUSY;
5helddestroyEBUSY/100000us timed wait expires ETIMEDOUT, holder remainsowner;
6holderfinalunlock/NEW1000000us timed wait succeeds by reown/signal;
7wrongunlockEPERM/recursive lock;8helddestroyEBUSY/partialunlock;
9helddestroyEBUSY/finalunlock (destroy ordered before release);
10destroy/invalidtryESRCH;11staledestroyESRCH/staletryESRCH.
Other102arguments cycle0/1122334455667788/FEDCBA9876543210 full64 as before.

Operation5 holder waits for atomic owner/count0/mutex queue plus exact native
100000us deadline registration/active-holder/suspended-waiter under g_mutex;
checks unchanged whole DATA/TLS then executes held destroy EBUSY. Actual kernel
wait_timeout/rescheduling/API unqueue reports signed ETIMEDOUT and preserves
holder. After both SCcallbacks/peer queue return, native finished observer
requires no timer/startup queue, clean active pair/flags/links, then exact
ownership/error/history and normal guest stores. Operation6 is concurrent:
same waiter calls102 on SAME handle while holder still owns it; holder waits
for NEW1000000us registration and unchanged bytes BEFORE guest finalunlock.
Actual unlock/reown/awake removes new timer/signals success; empty mutex/timer
queues/secondowner/count0/current success history required before stores.
Holder's observer uses job.waiterTimeout set separately for operations5/6;
request encoding/full64 ABI independently checked. Six observations required,
three expiry then wake transitions, no stale timeout/signal/CPU links accepted.

72SC:100create6/101destroy18/102lock18/103try12/104unlock18. Nine immediate/
recursive successes+3timed expiry+3timed wake successes+3invalidlockESRCH.
216dispatches/144pauses/720instructions/216guestSTW (144outputs+72TLS),
3nativeIDstores/110pubs+callbacks/2workersconstructed+joined. TLS12/12→24/24→
36/36, results6/6. Stops/notifies waiter on observationfailure. Peer joins before
TLS release and scheduler restore; owner joins before VM/cache/mutex cleanup.
Registry/settings/native scheduler restoration and zero mutex ID leaks retained.
No strict wall-time threshold or clock/config mutation; deadline-boundary race
not tested.1s second timeout supplies ordinary scheduling margin.

Validation PASS:
- test_p75_fixture.py chains unchanged P43–P74 and freezes entire Build95
  prefix. Independent scalar oracle registers6timers on3handles/same waiter,
  first3expire without transfer and fully clear; second3require different new
  deadline then guest unlock transfers owner/removes timer/returns success.
  Full ownership/depth/errors/stale/handle/full64 ABI/history/PC/LR/CTR and all
 720steps/144pauses/216stores/72SC/whole DATA+TLS checked. Not native scheduling.
- Unchanged test_p73_patch.py again applies frozen48+49 on exact pinned target
  files and verifies original implementations/read-only observers PASS.
  Workflow latest fixture now P75; P73patch/P69registry tests retained.
- test_p75_pair.py adapts P74 host harness without running previous workloads;
  extracts actual five APIs/full timeout and signal-return branches/native
  mutex methods/FIFO/unqueue/binder/SC/dispatcher/TLS/bounded and patch48/49
  diagnostic bodies. CPU/VM/ID allocator/storage/atomic control/priority/actual
  guest clock/wait_timeout/CPU check_state/sleep-awake scheduler/notify/FXO/
  decoder/GPR casts remain explicit HOST MODELS. Real kernel timer/scheduling
  not locally executed. Mixed100000us/1000000us host clock model,6modeled
  timer removals including3expiry reschedules+3unlock wakes; actual extracted
  API timeout-unqueue and signal-consume returns executed. C++20 Wall/Wextra/
  Werror pthread ASAN+UBSAN detect_leaks0 PASS:8runs/16workers/1728paired slices
  plus fresh registry recovery;6registered waits/3modeled expiries/3native wake
  successes/18API timeout observations/720instructions/110pubs/TLS36/36 each.
  Applicable foundation/207..224/LD22, queue225..229, scope230..231 and BOTH
  expiry232/233/235 and deadline234/timer236/wake237..239 fault models retained.
  Nonrecursive deadlock209 inapplicable, not claimed. New240secondrequest reuses
  old100000us duration,241omits fresh timer registration all detected. Faults
  HOST ONLY; fault0 extracted method operations unchanged. Registry init/reuse/
  rejected/omitted init/nonempty namespace preservation/settings/allocations/
  setup/TLS guards/prior scheduler-ready seed preservation PASS. Unsupported
  mutated timeout throws in model for bounded failure unwind. LSan disabled
  for runtime ptrace restriction; ASAN/UBSAN stayed enabled.
- Phone73orderedPASS/3exactP74transactions;74uniqueUI/export stages;whole prior
  bridge frozen;all49patches unchanged;bundle96/iOS16/Python syntax/git whitespace
  PASS. Scratch p75-fixture-check.log/p75-host-check.log/p75-patch-check.log.
  No local Xcode/iOS SDK: native P75compile/device execution remain PENDING.

Publication baseline mainc5daa64558ec5129f2b3cbd4cadea48f713a93d5,
tree056d2695d1c9310d522b5c95af3053ce84e179f3 (173blobs). Publish7files,
2newtests→175blobs; verify every baseline/target hash and preserve remote100755
scripts. DO NOT monitor/query Actions after push unless user explicitly asks
for an operation requiring a run ID. Install ARMSX3_iOS16_INSTALL_THIS_IPA via
TrollStore, run all74diagnostics, send startup log. No P76 before nativeP75PASS.
Exact wall-time latency/deadline-boundary unlock races/multiwaiter/cancellation
replay/weak-memory stress/recursive overflow/serialized savestate/import loader/
renderer/firmware/game boot remain untested. Midnight Club Los Angeles retained.

## Build 97 / P76 — production semaphore permits and lifecycle (2026-10-13)

Latest phone ARMSX3-startup-20261013-020910-274-15090.txt (Library
libfile_bdf8bc3e796c819193aa84965f48fc21) is Build96 ALL74 ordered P2–P75 AUTO
PASS, final all-stage PASS, no FAIL. P75transactions1/2/3 firstroles0/1/0,
TLS12/12→24/24→36/36, results6/6: actual first100000us timeout then NEW1000000us
queued wait on SAME mutex/waiter, guest unlock/reown/signal/success/timer removal,
full contexts and ID/scheduler cleanup PASS. Native start1791857345.765851→
finish7346.076864 (~311ms for3expiry+3wake lifecycles, observation only).
Build96 publication had been interrupted before ref update; resumed and
published353ec562562275117ce1bb122163d274ad15da3e after revalidating the entire
175file tree and main lease. Standing continue/nativeP75PASS permit P76.

Build97 appends armsx3_core_test_semaphore_lifecycle / P76, UI stage75,
bundle97/minimumiOS16.0. Entire Build96 CoreBridge2444296-byte prefix frozen,
SHA2561aded3ac213c5a7024704618a6acd44f8c6ac021d3f931be20e802ef4bcacea1.
All49 patches and old tests unchanged. No new native patch; sys_semaphore.h
included in appended section. Native syscall APIs/table/scheduler unchanged.
Pinned ARMSX2/ARMSX3 commit92b931b9fb5eef7f1317cb482917dfc19aceebd9 remains.
Retrieved exact pinned sys_semaphore.cpp/.h through GitHub primary source and
staged in scratch upstream mirror. Verified table90create/91destroy/92wait/
93trywait/94post/114get_value and header id_base96000000/attribute32bytes.

P76 expands to a new service family using proven P71 persistent native PPU pair
and production TLS scaffold. No scheduler activation/sleep instrumentation.
Real guestSC0→normal interpreter→production dispatcher/binder→six actual
semaphore APIs. Isolated FIFO/not-process-shared attr23040, zero initialized
32bytes with key/flags/pad0/nameiOSSema!, outputID23000. Native shared LV2 FXO
id_map initialized conditionally; existing semaphore namespace rejected before
worker construction and preserved. Cleanup selects only lv2_sema objects and
runs after both worker joins. No injected permits or syscall-table hooks.

New exact guest12words/48bytes SHA1=241b53df6fbad64e716f4b0e009c418f5fa571b5:
LWZr11,r5,4;LWZr3,r5,0;LDr4,r5,8;LWZr6,r5,20;LWZr5,r5,16;SC0;
STWr3,r9,0;LWZr12,r13,-6ff4;ADDI1;STWTLS;STWr12,r9,4;NOP.
Twenty-four-byte descriptor BE32arg0+BE32code+BE64arg1+BE32arg2+BE32arg3.
Inputr5 becomes third ABI argument only AFTER final descriptor read; outputr9
keeps result pointer separate from fourth ABI argumentr6. Budgets5/1/6 require
CIA20/24/48. Full saved8argument ABI/first4history args/native signed errors
and GPR/FPR/VR/status/reservation/code/cache/whole DATA/TLS/stacks/aliases checks
retained. CODE10000/DATA20000/stacks30000/40000/TLS pool50000..90000 unchanged.
Requests21000+call40hex+worker20hex; results20200+call20hex+worker10hex;
native count outputs24000+call10hex+worker4. Entire unused output/padding guarded.

Three12-operation lifecycles firstroles0/1/0, every SCpair explicitly ordered
first worker before second in both roles (non-SC slices still paired):
0create(initial2,max3)/null-outputcreateEFAULT;
1wait consumes2→1/trywait consumes1→0;
2get_value writes0/emptytrywaitEBUSY;
3post3 reaches max/get_value writes3;
4post1 overflowEBUSY/post0EINVAL, value remains3;
5wait consumes3→2/trywait consumes2→1;
6trywait consumes1→0/get_valueNULL EFAULT;
7post(-1)EINVAL/post1 succeeds value1;
8get_value writes1/wait consumes1→0;
9destroy/get_value staleESRCH;
10staledestroyESRCH/stalepostESRCH;
11create(initial-1,max3)EINVAL/invalidhandle0get_valueESRCH.
Wait timeouts cycle0/1122334455667788/FEDCBA9876543210 full64; all waits have a
positive permit and must return immediately. Signed initial-1 and post-1
loaded as u32ffffffff then actual binder casts s32; native errors prove handling.
All18get-value calls preserve canaries on error;9valid BE32 count writes.
At every boundary check actual sem.val/max3/exists1/FIFO/key0/name/empty sq.
Stock native post debug fields checked: positive attempts3/overflow/1 count
1→2→3, poster role first/first/second, LR12340000, nonzero time; zero/negative
posts do not update metadata. No precise latency/profiling-counter claim.

72SC:90create9 (3valid/3NULL/3negative),91destroy6 (3valid/3stale),92wait9
(success),93trywait12 (9success/3emptyEBUSY),94post18 (6success/3overflow/
6zero-negativeEINVAL/3stale),114get_value18 (9writes/3NULL/6stale-invalid).
216dispatches/144pauses/864guest instructions/216guestSTW (144outputs+72TLS),
3nativeIDstores+9nativecountstores/110pubs+callbacks/2workersconstructed+joined.
TLS12/12→24/24→36/36, results6/6. Peer joins before TLS release; owner joins
before VM/cache/object cleanup. ID last scratch/settings restored, zero IDs
leaked. No blocking semaphore wait, queue/scheduler wake or timeout tested yet.

Validation PASS:
- test_p76_fixture.py chains unchanged P43–P75/frozen prefixes and freezes
  whole Build96. Independent scalar oracle covers12words/new24byte descriptor,
  four-create-argument/full64-wait ABI, all permit mutations/max/errors/native
  count outputs/canaries/stale IDs/post metadata/whole DATA+TLS/context/history/
  PC/LR/CTR and864instructions/144pauses/216stores/72SC. Does not execute kernel.
- test_p76_pair.py adapts P71 host harness WITHOUT executing old workloads;
  extracts ALL six pinned API bodies including full wait/post slow branches,
  real guestSC/binder/dispatcher/TLS/bounded core bodies. CPU/VM/ID allocator/
  storage/atomic storage/notify/clock/profiler/FXO/decoder/GPR casts remain HOST
  MODELS. Scalar std::atomic interface model supplies compare_and_swap/try_dec/
  fetch_op; no ARM atomic/concurrent-CAS claim. Native semaphore class layout
  modeled from pinned header. Timer/profile support compiled with modeled
  profiler disabled; ALL sleep/queue/scheduler stubs throw if reached, so this
  validates only immediate waits. Real production iOS service bodies unchanged.
  C++20 Wall/Wextra/Werror pthread ASAN+UBSAN detect_leaks0 PASS:
  8runs/16workers/1728paired slices plus fresh registry recovery;9actual API
  full64 wait observations/864instructions/110pubs/TLS36/36 each. Applicable
  foundational/history/LD22/ID212/213/214/216/registry218/219/ABI224 negatives
  retained; old mutex faults inapplicable and not claimed. New242trywait skips
  consume,243wait skips decrement,244false EBUSY success,245post skips increment,
  246bad get_value,247NULL falsely succeeds,248negative initial accepted,
  250wrong max,252missing post debug increment,253missing native count store all
  detected. HOST ONLY fault mutations; baseline APIs operate unchanged. Registry
  init/reuse/rejected/omitted init/nonempty namespace preservation/settings/
  allocations/setup/TLS guards/join/deallocation checks PASS. Final host report
  wording corrected ID212..216→ID212/213/214/216 after run; executable unchanged.
- test_p76_registry.py first runs unchanged P69 registry regression then repeats
  same extracted native id_key/default id_map/allocate_id for header-confirmed
  semaphore namespace96000000. Trap-valued unconstructed registry rejects;
  default-constructed8192entry map allocates/publishes/types/deletes/reuses cookies/
  exhausts capacity PASS under ASAN+UBSAN; pointer/FXO/get_index remain shims.
- Unchanged P73patch test applies49frozen patches to exact pinned targets and
  read-only observers/preservation PASS. Workflow now runs latest P76fixture,
  P73patch and P76registry (which also runs P69registry) before native build.
- Phone74orderedPASS/3exactP75transactions;75uniqueUI/export stages;whole bridge
  prefix/all49patches unchanged;bundle97/iOS16/Python syntax/git whitespace PASS.
  Scratch p76-fixture-check.log/p76-host-check.log/p76-registry-check.log/
  p76-patch-check.log. No local Xcode/iOS SDK: native P76compile/device execution
  remain PENDING. Host models are not native scheduling or ARM atomic evidence.

Publication baseline main353ec562562275117ce1bb122163d274ad15da3e,
tree777a7cb743ce6b815a33c2e1ceaac4554f9d4ac8 (175blobs). Publish8files,
3newtests→178blobs; verify every baseline/target hash/preserve remote100755
scripts. DO NOT monitor/query Actions after push unless user explicitly asks
for an operation requiring a run ID. Install ARMSX3_iOS16_INSTALL_THIS_IPA via
TrollStore, run all75diagnostics, send startup log. No P77 before nativeP76PASS.
Blocking semaphore queues/wake/timeouts/multiwaiter/shared IPC/invalid attr
variations/serialized savestate/renderer/firmware/game boot remain untested.
Midnight Club Los Angeles goal retained.


## Build 98 / P77 — semaphore negative-permit FIFO wait/post handoff (2026-10-13)

Device log ARMSX3-startup-20261013-042500-763-15790.txt verifies Build97 P2-P76 ALL75 PASS with real native P76 semaphore permit/lifecycle operations. The existing Build97 bridge is frozen byte-for-byte (Git blob 87b264476831a5f953b5f590185c36c34df5f5c3); Build98 only appends a new P77 function. All 49 existing upstream patches and old probe stages are unchanged. Build number98, new UI P77, fixture test_p77_fixture.py (which runs the unchanged P76 oracle). No native scheduler patch or production semaphore service edits.

P77 replays the same production guest syscall/PPU/TLS/ID/scheduler-isolated P76 scaffold for three 12-operation transactions, but replaces operation2's nonblocking get-value/trywait on empty permits with a real timed semaphore wait of 2000000us and guest post1. Both worker-role orientations are exercised: first roles0/1/0. Peer gate is released first only for that stage. The poster observes native semaphore val -1 and exact PPU FIFO sq under its own mutex, verifies DATA/TLS and aliases have not been prematurely written, then runs the real guest SC94 to post1. The waiter must return CELL_OK through production wake and SC92; the resulting val is zero and queue empty. Queue observation count must be3. Remaining max-post/overflow/negative post, remaining permits/get-value/destroy/stale guards, all 72 SC, complete guest context/whole DATA/TLS/aliases and two PPU worker lifetime/cleanup invariants are retained from P76; six get-value writes expected instead of nine, post debug count grows from3 to4 per transaction. Expected syscall usage: create9/destroy6/wait12/trywait9/post21/get_value15. Two-second bounded queue observation and explicit failure logs are diagnostic only; actual wake timing and timeout behavior require a real device run.

Host fixture independently simulates three queued negative permit and successful post-handoff transitions and verifies frozen source, guest syscall tables, roles, counts, context guards, and 72-SC totals. This is a static/scalar oracle, **not** native runtime or ARM atomic/scheduler validation. GitHub Actions Xcode compile and device P77 remain pending until CI/user test. On workflow success, install ARMSX3_iOS16_INSTALL_THIS_IPA through TrollStore, run all76 stages, share exported startup .txt. Do not infer firmware, RSX or game boot from diagnostics. Midnight Club Los Angeles remains eventual game-boot target.


## Build 99 / P77 scheduler registration repair (2026-10-13)

Latest phone log ARMSX3-startup-20261013-112735-849-17192.txt
(libfile_efbcf3a45c248191b10e97ea0c62263e) identifies Build98: P2-P76 PASS;
P77 hangs in first real sys_semaphore_wait and is aborted by the eight-second
controller deadline. No native P77 success, renderer, firmware or game boot.
Repository baseline main4abcd7e8aadc90385ac3b65246056fd812cc1dba.

Root implementation defect: P77 copied the immediate-service P76 scaffold,
but omitted the native stopped-core scheduler scope needed by blocking waits.
P72-P75 already use armsx3_ios_ppu_probe_mutex_scheduler_and_call. Build99
wraps the P77 workload in that same guarded two-worker admission/ready scope,
joins the peer before restoring queues/priority/time state on success and
exception, and leaves all49 patches and all production semaphore APIs intact.
The poster now observes BOTH exact val=-1/FIFO waiter under semaphore mutex
and the actual registered2000000us scheduler deadline via the existing
read-only timeout observer before SC94. DATA/TLS premature-output checks
remain. Observer failure signals exit to the waiter for bounded cleanup;
returned contexts must have neither suspend nor signal flags left.
Whole P2-P76 bridge prefix and old tests remain unchanged. Bundle99/iOS16.0;
76 ordered diagnostics still P2-P77. No P78 added before native P77 PASS.

Validation: test_p77_scheduler.py runs the unchanged P77/P76/foundational
scalar fixtures and checks scope placement, peer join before restoration,
registered deadline observation, failure wake and bundle metadata. Workflow
runs this test instead of the older P77 entry point. New test_p77_pair.py
extracts the full native semaphore API bodies, FIFO/emplace/unqueue algorithms,
existing scheduler scope/timeout observer, guestSC/binder/dispatcher/bounded
execution and TLS bodies onto explicit CPU/VM/ID/atomic/clock/scheduler models.
C++20 Wall/Wextra/Werror with ASAN+UBSAN (detect_leaks=0) passes eight normal
runs/16workers, three timed queued/post handoffs per run, first roles0/1/0,
72SC/full DATA/TLS/context/permit/debug metadata/cleanup invariants. Retained
immediate-service/ABI negatives pass; new mutations260 bypasses scheduler
scope,261 refuses queue/deadline observation,262 omits wake signal are all
rejected. These are HOST model tests, not native timer or ARM atomics evidence.
Unchanged49-patch application/read-only observers and native semaphore/mutex
registry allocation harnesses pass. Xcode/iPhone compile remains CI-only.

On successful workflow install ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore,
reopen the app, run all76 diagnostics, send exported startup.txt. Do not
monitor Actions after pushing; user reports completion/failure. Keep replies
concise. Midnight Club Los Angeles remains eventual game target; timeout
expiry/multiwaiter/sharedIPC/renderer/firmware/game boot remain untested.


## Build 100 / P78 — semaphore timeout expiry and permit recovery (2026-10-13)

Phone ARMSX3-startup-20261013-214942-771-20688.txt (Library
libfile_a7a9a126b26c819197abda549763ffa9) confirms Build99 ALL76 P2-P77 PASS.
P77 native FIFO waiter/deadline observations and wait/post handoffs pass all
three transactions, first roles0/1/0, TLS12/12,24/24,36/36 and results6/6.
The Build99 scheduler-scope repair is now device-proven. Baseline commit
4eb8a4e9558caf257ca924cf40da2f9e2e39bfaa/tree16e41b6d0c6e8f814f522bb2b5170da1b4400e46.

Build100 appends P78 armsx3_core_test_semaphore_timeout_recovery. Entire
Build99 CoreBridge prefix remains byte-identical, Git blob
941ffaffe9fc88a0b161b6ae12d5ce9ab6d9dd49. Old stages/tests/all49 patches and
production native services/scheduler unchanged; UI adds stage78 (77 tests),
bundle100/minimumiOS16.0. Same guarded scheduler scope, native retained PPU
pair/TLS and 12-word guest SC workload, budgets5/1/6.

P78 changes operation2 after initial permits have been consumed: first worker
SC92 waits100000us, peer observes exact val=-1/sq waiter AND registered native
deadline under existing read-only observer. No post is issued. Peer then
observes native expiry cleanup: val0, empty semaphore FIFO, no post metadata,
empty timer queue and both workers re-admitted without suspend/signal. Whole
DATA/TLS/aliases must still match the deferred-output snapshots before peer
SC114 returns0. Waiter must return signed CELL_ETIMEDOUT through native binder
and history; next guest slice writes the result. Subsequent post3/max overflow
and wait/trywait consume permits on the SAME semaphore, proving recovery.
Three transactions swap roles0/1/0. Existing invalid-output/negative create/
negative post/stale IDs/context/cache/stack/ID/scheduler cleanup retained.
72SC: create9/destroy6/wait12/trywait9/post18/get_value18; nine BE32 value writes,
216dispatches/144pauses/864instructions and TLS36/36. No precise wall-time
latency claim. Host code catches an overly long transaction log and a carry
constant substitution before publication; final source keeps original carry
mask0x20000000, short transaction messages and exact frozen earlier prefix.

Validation PASS: test_p78_fixture.py runs unchanged P77/P76/foundational
oracles, verifies whole Build99 freeze, independently models three timeout
negative-permit/queue/reuse lifecycles and 72SC/nine-output counts, and checks
77 unique UI stages/build100/iOS16. Workflow now runs this fixture. New
test_p78_pair.py reuses P77 extracted native semaphore bodies/queue methods/
SC/binder/dispatcher/TLS/bounded helpers and native scheduler scope/observers
on explicit CPU/VM/ID/atomic/clock/scheduler host models. C++20 Wall/Wextra/
Werror ASAN+UBSAN detect_leaks0: eight normal runs/16workers, three100000us
expiries per run and same-object reuse pass. Retained API/ABI/registry/setup/
cleanup negatives pass, plus missing scope260, rejected observation261, false
timeout success263, missing permit increment264, missing unqueue265 and stale
timer266 all rejected. Native timer scheduling/ARM atomics not simulated as
hardware evidence. Host extraction uses patched PPUThread/TLS files, native
semaphore files, and the original pinned lv2.cpp syscall dispatcher (before
iOS scoped-statistics patch), as in P77. UIKit/Xcode compilation and native
P78 execution remain CI/device pending. Python/workflow/plist/whitespace valid.

Do not poll Actions after push. User reports build result. On success install
ARMSX3_iOS16_INSTALL_THIS_IPA through TrollStore, reopen, run all77diagnostics,
send startup.txt. Keep responses concise. Native P78PASS is required before
next semaphore stage. Timeout-vs-post boundary races/multiwaiter/sharedIPC/
serialized savestate/renderer/firmware/game boot remain untested; Midnight
Club Los Angeles remains eventual game target.


## 2026-10-13 — Build100 device PASS; Build101/P79 timeout then requeue/wake

Device evidence: ARMSX3-startup-20261013-220929-610-20833.txt, build100,
all77 diagnostics P2–P78 PASS and final AUTO PASS. P78 observed three exact
100000us queued deadlines; native CELL_ETIMEDOUT restored zero permits and
empty semaphore FIFO/timer queues, then same-object permit reuse passed.
Roles0/1/0, TLS12/12 ->24/24 ->36/36, results6/6. No game boot claim.

Build101 appends P79 armsx3_core_test_semaphore_timeout_then_wake and UI stage79.
Entire Build100 bridge prefix remains byte-identical (git blob
350d5213610a2ba711dd2232b25194db0a34e5f5); all49 patches unchanged.
Three13-operation transactions retain the same semaphore handle and waiter
across a100000us timeout and a fresh1000000us queued wait. The peer observes
the second native FIFO entry/deadline, posts one permit through guest SC,
and both workers must return success with zero permits and empty FIFO/timer
queues. Full ABI/history/context/DATA/TLS/alias/cache/stack/lifecycle checks
remain; max/overflow/invalid posts/get-value canaries/destroy/stale IDs retained.
Totals:78SC (create9,destroy6,wait15,trywait9,post21,get-value18), nine BE32
value outputs,234dispatches/156pauses/936instructions, TLS39/39, six queue
observations/three expiries/three wakes; worker roles0/1/0.

Validation PASS: test_p79_fixture.py preserves earlier fixture chain, freezes
whole Build100 prefix, independently models all permit/queue/count changes,
and verifies78 UI stages/build101/iOS16. Workflow uses the new fixture.
Extracted native semaphore/queue/scheduler-scope/observer/SC/binder/TLS/bounded
host harness passes eight normal runs/16workers with C++20 Wall/Wextra/Werror
ASAN+UBSAN (detect_leaks0). Retained setup/API/ABI/context/cleanup negatives and
260/261/263–266 pass. Fault262 initially exposed host timer fallback masking a
missing wake signal: new host consistency guard rejects expiry after a timer
was already canceled. This guard is a host-model check, not a native latency
assertion. CPU/VM/ID/atomic/clock/scheduler remain models. Native timer/ARM
scheduling and UIKit/Xcode build remain CI/device pending. Patch49 application,
registry harness, Python/YAML/plist syntax and whitespace checks pass.

Next: let user report Actions result; DO NOT poll Actions after publishing.
After successful build, install ARMSX3_iOS16_INSTALL_THIS_IPA with TrollStore,
reopen and run all78 diagnostics, then request startup.txt. Wait for native
P79PASS before advancing. Target iPhone13ProMax/iOS16.0/Dopamine/TrollStore.
Timeout-post boundary races, multiwaiter/shared IPC, serialized savestate,
renderer, firmware and game boot remain untested. Midnight Club Los Angeles
remains eventual target. Keep user replies concise.


## 2026-10-14 — Build101 device PASS; Build102 batches P80 and P81

New user preference: batch multiple related device tests into one workflow/IPA
when logical, to reduce build/install cycles and speed up porting. Preserve
separate stage results and bounded failures. Do not poll Actions after push.

Device evidence: ARMSX3-startup-20261013-223238-535-20915.txt, build101,
all78 diagnostics P2–P79 PASS and final AUTO PASS. P79 confirms three100000us
native expiries followed by same-worker/object1000000us waits successfully
woken by posts; roles0/1/0, TLS13/13 ->26/26 ->39/39, results6/6. Native
FIFO/timer cleanup passed. No renderer/firmware/game boot evidence.

Build102 appends a shared surplus-semaphore diagnostic with two public stages:
P80 armsx3_core_test_semaphore_fifo_surplus; P81
armsx3_core_test_semaphore_priority_surplus. Entire Build101 bridge frozen at
git blob52e84736ca373db4718e99fd6820f7c2b9f115a9; all49 patches unchanged.
Each profile has three14-operation lifecycles with roles0/1/0:100000us timeout,
fresh1000000us queued wait, peer guest post2 wakes one worker and retains
exactly one spare permit; subsequent post2 reaches max3. INT_MAX positive
post must return EBUSY without permit changes; INT_MIN negative post must
return EINVAL without permit/post-metadata changes. Native priority protocol
is created/retained and its single-waiter schedule branch executes; ordering
among multiple priority waiters is explicitly untested. Other API/error/ABI/
context/output canary/ID/worker/TLS/cache/alias/scheduler cleanup checks retained.
Each profile84SC (create9,destroy6,wait15,trywait9,post24,get-value21),12 BE32
value writes,252dispatches/168pauses/1008instructions/TLS42/42, six queue
observations/three expiries/three wakes. UI now80 stages P2–P81; build102/iOS16.

Validation PASS: test_p80_fixture.py preserves earlier fixture chain and full
Build101 bridge prefix, independently models both profiles and exact84SC/
12-output counts. test_p80_pair.py takes optional fifo/priority profile and
extracts shared helper plus both public wrappers, real native semaphore/
queue/scheduler-scope/observers/SC/binder/TLS/bounded bodies. C++20 Wall/Wextra/
Werror ASAN+UBSAN detect_leaks0: eight normal runs/16workers per profile;
16 normal runs/32workers total. Retained setup/API/ABI/context/cleanup negatives
pass plus267 lost surplus,268 false INT_MAX success,269 false INT_MIN success,
and270 wrong protocol in priority profile.262 remains a canceled-timer host
consistency guard, not a native latency assertion. CPU/VM/ID/atomic/clock/
scheduler remain explicit host models. Python/YAML/plist/whitespace checks pass.

Workflow now has ubuntu24.04 semaphore-host job before macOS core build:
checkout pinned native source, verify batch fixture, apply all49 patches,
restore original pinned lv2.cpp dispatcher only in isolated host checkout,
run fifo then priority extracted workloads under sanitizers. Core job needs
semaphore-host and repeats fixture before its own full patch application;
production iOS source is fully patched. Added tests/** to workflow triggers.
CI preparation was reproduced locally: all49 patches apply sequentially on
pinned original files, dispatcher restoration yields same sources as validated
local extraction. Host compiler/binary subprocesses have180second timeouts,
job10minute timeout. Xcode/iOS compilation and native P80/P81 execution pending.

After Actions succeeds user should install ARMSX3_iOS16_INSTALL_THIS_IPA with
TrollStore, reopen and run all80 diagnostics, then send startup.txt. Review
both new native stage results before next family. Continue sensible batches
rather than one small variant per IPA; next distinct LV2 synchronization
family can bundle immediate ABI/lifecycle checks and related bounded queue
cases when supported. Target iPhone13ProMax/iOS16.0/Dopamine/TrollStore.
Multiwaiter/priority ordering/shared IPC/savestate, timeout-post boundary races,
renderer/firmware/game boot remain untested. Midnight Club Los Angeles remains
eventual target. Keep responses concise.


## 2026-10-14 — Build102 device PASS; Build103 four event-flag diagnostics

User explicitly wants faster porting and more than two new diagnostics per
workflow. Target4–6 meaningful stages per IPA when logical, centered on new
boot-critical coverage. Current batch adds four native event-flag modes. Keep
separate stage results, do local checks, and DO NOT poll Actions after push.

Device evidence: ARMSX3-startup-20261014-025336-575-21797.txt, build102,
all80 diagnostics P2–P81 PASS and final AUTO PASS. Both FIFO and priority
single-waiter surplus profiles pass on iPhone, including post2/spare1, signed
count boundaries and cleanup. No game/firmware/renderer boot claim.

Build103 appends armsx3_core_test_event_flag_batch plus four exported stages:
P82 event_flag_and; P83 event_flag_or; P84 event_flag_clear (AND|CLEAR);
P85 event_flag_clear_all (OR|CLEAR_ALL). All symbols prefixed
armsx3_core_test_. Entire Build102 bridge frozen at blob
b488610de4861929718396e04c4b2c00f9d5d744; all49 production patches unchanged.
Each mode has three14-operation lifecycles on two retained PPU workers with
roles0/1/0, native single-waiter/FIFO attributes and64-bit patterns using bits
63/48/32/7. Eight production APIs82/83/85/86/87/118/132/139 execute via actual
guest SC/table/binder: create/get/trywait/set/clear/wait/cancel/destroy. Checks
include partial AND rejection vs OR success, invalid mode3, full mask AND
and partial-bit OR wakes, selected/all/no clearing, zero-mask AND success vs
OR busy,100000us timeout preserving pattern, fresh same-worker/object1000000us
wait woken by set, zero cancel counts, NULL output, stale handle zero-output
contracts and valid lifecycle recovery. Native cancel with blocked waiters,
multiple waiters/priority ordering/shared IPC/savestate remain untested.

New13-word/52-byte guest program loads all five native argument registers via
full64 LDs;40-byte input descriptors, pre-SC budget6, SC budget1, continuation6;
PC boundaries24/28/52. ABI/history verifies original argument snapshots, while
native wait scratch GPR6 receives delivered flags and GPR7 is marked1 by set.
Full64 init and timeout—including stale0xfedcba9876543210—are checked. Native
wait/trywait always write BE64 results even on errors; stale get writes zero;
cancel initializes BE32 counts even on ESRCH. Per mode84SC
(create9,destroy3,wait9,trywait21,set12,clear6,cancel6,get18),45 BE64 outputs,
six BE32 cancel counts plus three BE32 handle writes,252dispatches/168pauses/
1092instructions/TLS42/42. Six queue observations, three expiries/three wakes.
Whole code/DATA/TLS/stacks/aliases/cache/context/history/ID/worker/scheduler
cleanup retained. A release/acquire nativeFinished publication ensures the
expiry observer reads native BE64 output only after the waiter has completed
its SC callback; observer polling does not race guest-memory result writes.

Validation PASS: test_p82_fixture.py runs previous fixture chain, freezes
entire Build102 prefix, independently models all four modes/partial wakes/
pattern/output/queue counts and verifies84 unique UI stages/build103/iOS16.
test_p82_pair.py extracts complete native eight API bodies, check_mode and
check_pattern, sys_event_store_result, queue methods, scheduler probes,
SC/binder/dispatcher/TLS/bounded helpers, and shared bridge plus selected
public wrapper. CPU/VM/ID/storage atomics/clock/scheduler are host models;
eflag_record watch logging is a stub, not a modeled game behavior. C++20
Wall/Wextra/Werror ASAN+UBSAN detect_leaks0: eight normal runs/16workers per
profile (32runs/64workers total) plus retained applicable context/ABI/registry/
queue/setup/cleanup negatives pass. New mutations280 invalid mode accepted,
281 truncated init,282 skipped CLEAR (clear profile),283 skipped CLEAR_ALL
(clear_all profile),284 false AND success,285 missing get output,286 skipped
clear mask,287 stale output not zeroed,288 false trywait success,289 bad cancel
count and290 OR incorrectly requires all bits are rejected.263 false timeout,
265 missing unqueue,260/261 scope/observation and266 stale timer retained;
262 is the host canceled-timer consistency guard. Initial host fault265 was
inactive due to inherited service-section replacement; injection was restored
and verified rejected before final runs. Native event flag namespace0x98000000
allocator harness test_p82_registry.py passes constructed-map publication,
type/cookie/reuse/destruction/capacity and unconstructed-map rejection tests.
Python/YAML/plist/whitespace checks pass. Xcode/ARM/native execution pending.

Workflow synchronization-host matrix now runs six independent profiles in
parallel: previous FIFO/priority semaphore workloads and and/or/clear/clear_all
event flag workloads. Each isolated host checkout applies all49 patches and
restores original pinned lv2.cpp dispatcher for modeled statistics, as before.
Fixture and new registry test run before patches. Core job needs the complete
matrix; it repeats fixture/registry checks then applies full production patches
in its own checkout. Only one iOS IPA build follows the six-profile gate.
No production patch or old-stage implementation changed. No Actions polling.

After successful Actions install ARMSX3_iOS16_INSTALL_THIS_IPA with TrollStore,
reopen and run all84 diagnostics P2–P85, then send startup.txt. Check all four
new mode results before extending the next synchronization family; continue
4–6 stage batches that advance distinct native coverage. Target iPhone13ProMax,
iOS16.0, Dopamine/TrollStore. Timeout-set boundary races/multiple waiters/
blocked cancellation/priority/shared IPC/firmware/renderer/game boot remain
untested. Midnight Club Los Angeles remains eventual game target. Replies short.


## 2026-10-14 — Build103 device PASS; Build104 four condition-variable profiles

Device evidence: ARMSX3-startup-20261014-055644-075-22253.txt, build103,
all84 diagnostics P2–P85 PASS and final AUTO PASS. AND/OR/CLEAR/CLEAR_ALL
native event-flag modes all passed on iPhone. Still no firmware/renderer/game
boot evidence. User wants faster4–6-stage batches and fewer build/install cycles.

Build104 adds shared armsx3_core_test_cond_batch plus four exported diagnostics:
P86 cond_fifo (FIFO ordinary mutex/signal); P87 cond_recursive (FIFO recursive/
signal); P88 cond_broadcast (priority ordinary/broadcast); P89
cond_recursive_broadcast (priority recursive/broadcast). Each symbol begins
armsx3_core_test_. Entire Build103 bridge prefix frozen at git blob
3233e091778b1a809e9e0b65aeb394caea9331f7; all49 production patches unchanged.
UI88 stages P2–P89, CFBundleVersion104, iOS16 minimum.

Each profile performs three18-operation linked mutex/condition lifecycles on
retained two-worker/TLS slots, roles0/1/0. Native ten APIs100/101/103/104 and
105/106/107/108/109/110 execute via guest SC/table/binder. Actual constructors
and condition on_id_create associate mutex pointer/shared reference and
increment cond_count. Native contract detail: destroying an UNLOCKED mutex
with cond_count1 returns EPERM, not EBUSY; queued condition destroy returns
EBUSY. Foreign cond_wait/unlock errors preserve ownership. Ordinary repeated
trylock returns EDEADLK; recursive trylock increments the extra count.
Observed100000us wait queues condition and fully releases mutex owner/count;
peer queued destroy gets EBUSY; timeout reacquires the same mutex and restores
recursive count. A fresh same-worker/handle1000000us wait is signaled, then
reacquires/restores again. Ordinary partial/full unlock and recursive count
restoration are checked throughout. Empty signal/broadcast and invalid
thread0 targeted signal update native signal metadata as implemented; real
registered targeted wake and multiple waiters are not tested. Stale creation,
wait/signal/destroy/unlock calls must return ESRCH without output publication.

Profile totals108SC;100create6/101destroy6/103trylock24/104unlock21/
105condcreate9/106conddestroy9/107condwait15/110signal_to3. Signal profile
108signal9/109all6; broadcast profile108signal6/109all9. Six native BE32 handle
writes, full DATA output/error canaries,324dispatches/216pauses/1296instructions/
TLS54/54. Guest12words/48bytes, budgets5/1/6, PCs20/24/48, full64 foreign/stale
wait timeouts0xfedcba9876543210 observed at native ABI. Six exact queue/deadline
observations, three expiries/three wakes. Native link/refcount/owner/recursive
count/signal metadata/queue/context/history/memory/TLS/stacks/aliases/cache/
settings/worker/ID/scheduler cleanup all checked. Cold syscall state guard
rejects missing optional_savestate_state or loaded_from_savestate; real pinned
PPU constructor initializes serial state. Emergency cleanup withdraws private
conditions before mutexes and skips already-destroyed bookkeeping, preventing
double link/refcount decrement after a failed withdrawal. New ABI errors log
transaction/op/slice/worker/SC and expected/observed error for device debugging.

Validation PASS: test_p86_fixture.py preserves prior fixture chain, freezes
whole Build103 prefix and independently models four linked object/owner/count/
queue/lifecycle/error protocols and108SC/six handles/88 stage metadata.
test_p86_pair.py extracts four native mutex API bodies and try_lock/try_unlock/
try_own/reown, six condition API bodies, native constructor and active ordinary
on_id_create branch, actual binder/SC/dispatcher/TLS/bounded/queue/probe bodies.
Deferred serialized on_id_create branch is rejected in host model; optional
syscall serialization interface is a model. CPU/VM/ID/storage atomic/control/
clock/scheduler remain models. C++20 Wall/Wextra/Werror ASAN+UBSAN detect_leaks0:
eight normal runs/16workers per profile (32runs/64workers total), applicable
setup/ABI/context/registry/queue/cleanup negatives pass. New faults301 missing
mutex link increment,302 ignoring linked-mutex destruction guard,303 false
queued destroy success,304 missing link decrement,305 unreleased recursive
count and306 lost restored count (recursive profiles),307 bad signal metadata,
308 false permission success,309 missing serial state and310 loaded-state
misuse all detected; false timeout263/missing unqueue265/stale timer266 retained.
212 failed service withdrawal is injected only in worker syscall context so
fallback namespace cleanup remains available. Missing admission260 retains
host priority snapshot cleanup: native cond_wait emplaces and assigns order
before sleep, unlike semaphore ordering. Native scheduler scope still supplies
actual restoration under normal/other fault cases.262 remains host canceled-
timer consistency guard. Host normal run initially caught wrong EPERM expected
result; corrected to pinned native contract before final checks. Local native
condition namespace0x86000000 allocator harness test_p86_registry.py checks
constructed-map publication/type/cookie/capacity/reuse and unconstructed-map
rejection. Python/YAML/plist/whitespace checks pass. ARM/Xcode/native pending.

Workflow now includes ten parallel synchronization-host matrix profiles:
previous two semaphore/four event-flag workloads plus four condition profiles.
Job names include script and profile to disambiguate fifo. Common fixture is
test_p86_fixture.py; new namespace registry test runs before patch application
in host and core checkouts. Original pinned lv2.cpp dispatcher restoration
remains confined to isolated host checkout with modeled stats. iOS core keeps
all49 patches. Core waits for all ten matrix entries before one IPA build.
No Actions polling after publishing; user reports result.

Next: after Actions succeeds install ARMSX3_iOS16_INSTALL_THIS_IPA through
TrollStore, reopen, run all88 diagnostics and send startup.txt. Verify four
new native stage results, then continue meaningful4–6-stage batches toward
boot-critical coverage. Target iPhone13ProMax/iOS16.0/Dopamine/TrollStore.
Multiwaiter/broadcast among multiple waiters/contended reacquisition/valid
registered targeted wake/shared IPC/serialized state/firmware/renderer/game
boot remain untested; Midnight Club Los Angeles eventual game target.
Keep user replies short.


## 2026-10-14 — Build104 device PASS; Build105 P90–P93 reader/writer lock batch

Latest user attachment read directly from its supplied local copy:
ARMSX3-startup-20261014-072809-291-22897.txt. Device Build104 passed all88
stages P2–P89, including FIFO ordinary/recursive condition waits and priority
ordinary/recursive broadcast waits. Final AUTO PASS; no AUTO FAIL. Native
condition queue observation, released mutex/count, timeout reacquisition,
signaled reacquisition, recursive count restoration, links, ABI/TLS and final
cleanup all confirmed on iPhone13ProMax/iOS16.0. This confirms single-waiter
condition paths; multiwaiter ordering, registered targeted wake and contended
mutex reacquisition still not tested.

Build105 adds four tests in one workflow/IPA:
P90 rwlock_reader_fifo; P91 rwlock_reader_priority;
P92 rwlock_writer_fifo; P93 rwlock_writer_priority.
Each exported function begins armsx3_core_test_. Shared implementation:
armsx3_core_test_rwlock_batch(u32 protocol, bool writerWait).
Whole Build104 bridge prefix remains byte-identical, frozen git blob
 a7c6927d014824c1b7c368afd4610491525b7213.
All49 production patches unchanged. UI92 stages P2–P93, CFBundleVersion105,
MinimumOSVersion16.0. Pinned ARMSX2/ARMSX3 source remains
92b931b9fb5eef7f1317cb482917dfc19aceebd9.

Each profile performs three20-operation native rwlock lifecycles with the
retained two-worker pair and TLS slots, first-worker roles0/1/0. Native APIs
120create/121destroy/122rlock/123tryrlock/124runlock/125wlock/126trywlock/
127wunlock and alias148 _sys_rwlock_trywlock run through guest SC/table/binder.
Only one successful create per lifecycle; null output returns EFAULT and
invalid protocol0 returns EINVAL with output canary and existing ID unchanged.
Two distinct workers hold shared reads concurrently, owner=-4; try-write and
alias report EBUSY. Native read unlock releases a count without checking which
thread acquired it; exact transition -4 to -2 to0 is verified. Exclusive writer
ownership, foreign writer unlock EPERM, repeat writer acquire EDEADLK, try-read
exclusion and busy destruction are checked.

Reader profiles: peer holds write; first worker queues read100000us; peer
observes exact rq/wq/owner and scheduler deadline, then destroy EBUSY. Native
reader timeout removes rq but RETAINS the owner's low wait bit. Same-worker/
handle read1000000us queues again; peer write unlock wakes it, owner becomes-2
and wait bit clears. Second guest reader joins, exact-4 count; both read
releases restore0.
Writer profiles: peer holds one read; first queues write100000us; peer observes
exact wq/rq/owner=-1 and deadline, then destroy EBUSY. Native writer timeout
removes wq and CLEARS the wait bit, restoring owner=-2. Same-worker/handle
write1000000us queues again; final peer read release transfers exclusive
ownership to the waiter. Own repeated write EDEADLK and foreign release EPERM
must preserve it. Later immediate write acquire/release, destroy and stale
read/write/try/alias/unlock/destroy ESRCH paths are checked in both profiles.

Per-profile totals120SC/three BE32 handle writes/360dispatches/240pauses/
1440instructions/TLS60 per worker. Guest12words/48bytes; budgets5/1/6,
PCs20/24/48. Full64 immediate/self/stale wait timeout0xfedcba9876543210;
100000us expiry and1000000us unlock wake. Six exact queued-state/deadline
observations, three expiries/three wakes. Every paused/SC/continuation boundary
checks GPR/FPR/VR/status/reservation/history/ABI/signed results/DATA/output
canaries/TLS/stacks/VM aliases/cache. Worker joins precede scheduler scope
restoration and emergency private ID withdrawal. Settings, mappings, CPU/TLS
lifetime counts and native reader/writer namespace cleanup must balance.

Validation PASS:
- test_p90_fixture.py retains prior fixture chain, freezes Build104 prefix,
  independently models all four reader-count/writer-owner/queue/timer/waitbit/
  handle/error lifecycles, validates code/error tables,120SC,92 UI stages,
  Build105 metadata and iOS16 minimum.
- test_p90_pair.py extracts eight unchanged native rwlock API bodies and
  native constructor, real queue/schedule/emplace algorithms, diagnostic
  admission/restoration/deadline observer, binder/SC/dispatcher/TLS/bounded
  helper and production bridge workload. Four profiles,8 normal runs and
  16workers each (32runs/64workers total), plus applicable negative/setup/
  ABI/context/registry/timeout/cleanup tests, all PASS with C++20,
  Wall/Wextra/Werror, ASAN+UBSAN, ASAN_OPTIONS=detect_leaks=0.
- New faults311 lost reader increment;312 invalid protocol accepted;313 false
  permission success;314 false recursive write success;315 false try-busy
  success;316 false busy destruction;317 lost reader wake count and319 wrongly
  cleared reader timeout wait bit (reader profiles);318 missing writer timeout
  wait-bit cleanup and320 lost writer handoff owner (writer profiles). False
  timeout263, missing service unqueue265, stale timer266 and other applicable
  inherited faults detected. Queue-unqueue mutation is explicitly reinserted
  after replacing semaphore services, with a signature assertion.
- test_p90_registry.py runs the extracted native id_key/map/allocate_id code
  for namespace0x88000000: constructed8192-entry map publication/type/cookie/
  capacity/reuse/deletion and unconstructed-map rejection all PASS.
- Sanitizers caught concurrent writes to the host-only log vector during
  injected worker failures; p53_host_shims.cpp now serializes log collection
  with a mutex. All14 workflow host profiles rerun and PASS: two semaphore,
  four event-flag, four condition and four reader/writer workloads. CPU/VM/ID
  allocator/atomic storage/clock/scheduler/notification remain explicit host
  models; these local checks do not claim native iOS or ARM timer execution.
- Python/YAML/plist and git diff --check PASS. Full Xcode/ARM build and new
  native device execution pending Actions/user install.

Workflow runs14 independent synchronization-host matrix profiles with
fail-fast:false, then builds one installable IPA. Common fixture updated to
test_p90_fixture.py; native rwlock allocator test runs before patch application
in host and core checkouts. Host-only original pinned lv2.cpp restoration for
modeled syscall statistics retained; iOS core still uses all49 patches.
No Actions polling after publishing: user reports build/device outcome.

Next: after Actions succeeds install ARMSX3_iOS16_INSTALL_THIS_IPA through
TrollStore, reopen, run all92 diagnostics and send startup.txt. Continue
meaningful4–6-stage batches, prioritizing new boot-critical subsystems such as
native event queues/ports or lightweight synchronization rather than repeated
minor variants. Multiwaiter ordering, writer preference, blocked reader wake
when last queued writer times out, shared IPC, serialized savestate, firmware,
renderer and actual game boot remain untested. Target iPhone13ProMax/iOS16.0/
Dopamine/TrollStore; eventual game Midnight Club Los Angeles. Keep replies
short and proceed autonomously within the established publish workflow.


## 2026-10-14 — Build106 expands the next IPA to eight new diagnostics

User explicitly requested eight diagnostics after Build105 publication.
Build106 adds P94–P97 event queue/local port tests alongside the still-device-
unverified P90–P93 reader/writer tests. Relative to the last verified Build104,
the next IPA contains eight NEW diagnostics P90–P97 and96 total P2–P97.
CFBundleVersion106, iOS16 minimum. Entire Build105 bridge prefix frozen at
 git blob792bb98f6b7f47ac46ece9a2e0d713e8b9453077; all49 production patches and
upstream pin92b931b9fb5eef7f1317cb482917dfc19aceebd9 unchanged.
Build105 commitd4ec539fb8f1ce19b692150e22752caf3834807a is superseded by this
expanded build; use the latest Build106 IPA. No new device log was processed.

New profiles:
P94 event_queue_fifo; P95 event_queue_priority;
P96 event_queue_cancel_fifo; P97 event_queue_cancel_priority.
Exports start armsx3_core_test_. Shared function
armsx3_core_test_event_queue_batch(u32 protocol, bool cancelReceive).
All profiles test PPU queues and local ports, three20-operation transactions
on the retained two-worker/TLS pair, first roles0/1/0. Ten native APIs:
128queue_create/129destroy/130receive/131tryreceive/133drain/
134port_create/135destroy/136connect_local/137disconnect/138send.
Native queue/port constructors and queue::send execute unchanged. Queue
capacity2, protocolFIFO/priority, typePPU, key0, nameiOSQevt!. Port named
0xfedcba9876543210 for transactions1/3; name0 in transaction2 exercises native
source(process_getpid()<<32)|portID (pinned process_getpid returns1).

Guest descriptor now32bytes: BE32 handle/SC plus three BE64 fields.12 guest
instructions unchanged in count but r5/r6 loads are LD instead of LWZ, so
port names, data1/data2/data3 and receive timeout retain64 bits. Native receive
returns source/data1/data2/data3 in r4–r7 and ignores dummy_event; its entire
canary buffer must remain unchanged. Input history/syscall_args stay exact
while result registers change. Tryreceive writes exact BE64 event arrays and
BE32 count; zero-size, empty, one-item and bulk requests preserve unused bytes.

Each profile: create queue/port; empty tryreceive; invalid port type0 preserves
output; connect, duplicate connect/connected destroy EISCONN; disconnect;
disconnected send ENOTCONN; reconnect; receive100000us queues with exact native
PPU pq/empty event buffer/registered deadline; normal queued destroy EBUSY;
timeout removes waiter and timer. Fresh same-worker/queue1000000us receive:
ordinary profiles send full64 payload directly to the waiter, bypassing the
buffer; cancel profiles force-destroy queue, returning ECANCELED, leaving the
port reference to a queue whose exists count is0. Dead-link sends ENOTCONN.
Cancellation profiles recreate the queue in a separate operation, then
reconnect the existing port in the next operation before payload sends. Track
linkedQueueID separately from the fresh live queueID until reconnect; this
verifies the retired reference and prevents using a handle before creation.
All profiles then exercise buffered FIFO payload order, capacity2 overflow
EBUSY, exact bulk/count outputs, effective draining of two queued events,
invalid queue size0/destroy mode2 with canary preservation, disconnect and
port removal, empty queue destruction and stale receive/tryreceive/drain/
connect/send/queue-destroy/port-destroy ESRCH. Queue/port namespaces0x8d/0x0e
are empty before and after; emergency cleanup removes ports/references before
queues after worker joins.

Per profile120SC/360dispatches/240pauses/1440instructions/TLS60 perworker;
three ordinary queue + three port handles (six writes), or cancellation queue
replacement adds three writes (nine). Six observed queues, three expiries and
three native wakes/delivery-or-cancellation completions. Paused/SC/continuation
GPR/FPR/VR/status/reservation/history/ABI/signed results/DATA/arrays/counts/
canaries/TLS/stacks/VM aliases/cache/settings/CPU lifecycle/ID/scheduler scope
cleanup all checked. Combined eight new stages960SC/2880dispatches/
1920pauses/11520guest instructions.

Validation PASS: test_p94_fixture.py preserves prior chain/Build105 bytes and
independently models all four port-link/source/payload/order/capacity/buffer/
count/timeout/delivery/cancel/replacement/drain/error lifecycles, validates
code/error arrays,96 UI stages/eight new symbols, Build106/iOS16 metadata.
test_p94_pair.py extracts ten native API bodies, native constructors, native
queue::send/queue algorithms/probes/binder/SC/dispatcher/TLS/bounded helper and
production guest workload. Four profiles, eight normal runs/16workers each,
plus applicable setup/context/ABI/registry/timer/cleanup failures, all PASS
under C++20 Wall/Wextra/Werror ASAN+UBSAN detect_leaks0. New faults341 corrupted
buffered payload;342 bad delivered register (ordinary);343 false full-queue
success;344 failed drain;345 false EISCONN;346 false ENOTCONN;347 failed
disconnect;348 wrong count;349 wrong event source;350 false cancellation
success (cancel);351 false queued destruction success;352 invalid mode
accepted;353 corrupt BE event output, all detected where applicable. Retains
false timeout263/missing unqueue265/stale timer266 and other relevant faults.
CPU/VM/ID allocator/atomic storage/clock/scheduler/notification are explicit
host models; unused SPU paths reject entry. No native ARM/device result claimed.
Both native allocator namespaces pass test_p94_registry.py (constructed8192-
entry map type/publication/capacity/delete/cookie reuse and unconstructed-map
rejection). Python/YAML/plist/whitespace/prefix checks PASS. Previous14 host
profiles passed earlier in this same task and their production bodies remain
byte-identical; four additional event profiles now pass,18 configured total.
Xcode/full ARM build and P90–P97 device execution await Actions/user install.

Workflow has18 independent synchronization-host matrix profiles and one IPA
core build that waits for all profiles. Common fixture test_p94_fixture.py;
queue/port allocator tests run before patch application in both checkouts.
Host-only original lv2.cpp restoration remains isolated from production.
Concurrency cancel-in-progress is now TRUE, as discussed with the user, to
cancel superseded versions and avoid waiting behind the previous four-test
Build105. No Actions polling after push; user reports build/device outcome.

Next: when the latest Build106 workflow succeeds, install
ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, reopen, run all96 tests and send
the startup log. Verify all eight new native results before advancing further.
SPU queue delivery, multiwaiter FIFO/priority ordering, priority-dependent port
is_busy handoff, shared IPC, serialized savestate, firmware/renderer/game boot
remain untested. Target remains iPhone13ProMax/iOS16.0/Dopamine/TrollStore;
Midnight Club Los Angeles eventual game target. Keep replies short. Standing
batch request is now eight meaningful diagnostics per next IPA where logical.


## 2026-10-14 — Build106 device P2–P93 PASS; P94 creation assertion fixed; Build107 adds eight diagnostics

Processed the user-supplied local copy
ARMSX3-startup-20261014-171721-382-26254(1).txt (Build106).
The log confirms92 diagnostic stages P2–P93 PASS, including all four new
reader/writer profiles P90–P93. P94 failed immediately after successful queue
and port creation at the metadata assertion. P94–P97 did not complete; no game
boot result. This is a diagnostic expectation/model bug introduced in Build106.

Pinned native source explains the failure: lv2_obj::exists defaults0 and its
private on_id_create increments it. lv2_obj::create<lv2_event_queue> runs that
hook through its provider, so a queue has exists1. sys_event_port_create uses
idm::make<lv2_obj,lv2_event_port>, which publishes the constructor result directly
and runs no hook; a live event port legitimately has exists0. idm lookup uses
registry presence/type, not this port counter. The diagnostic required port
exists1 and the old host import model synthesized1 for every kind, hiding the
wrong assertion. Corrected port expectation to0; preserve queue expectation1.
No upstream emulator behavior or production patch was changed.

The revised P94 host harness now extracts actual native idm::make and import
bodies, and the native lv2_obj::on_id_create body; its modeled create_id/storage
publishes objects without manufacturing normal counter values. The nonshared
queue-create model explicitly executes the extracted hook. Real native
constructor bodies/default-counter contract remain checked. Running the old
bridge against this creation path reproduced the same metadata failure BEFORE
the fix (p94-native-creation-before-fix.log); after the fix all four event
profiles PASS. Added faults354 erroneous port hook and355 missing queue hook,
which must fail. New device failure detail prints transaction/op/slice, both
IDs/counters/presence/validity/expected-live flags and linked queue ID, instead
of only a generic metadata error.

Build107 retains the standing eight-new-diagnostics request, focused on this
native creation/lifecycle gap. Adds P98–P105;104 total UI stages P2–P105,
CFBundleVersion107, MinimumOSVersion16.0. New helper
armsx3_core_test_event_object_batch(u32 protocol,s32 queueType,s32 capacity,
                                  s32 portType,u64 portName).
Exports all start armsx3_core_test_event_object_. Profiles:
P98 queue_fifo_min: FIFO PPU queue,capacity1;
P99 queue_priority_max: priority PPU queue,capacity127;
P100 queue_spu_fifo_min: FIFO SPU queue,capacity1;
P101 queue_spu_priority_max: priority SPU queue,capacity127;
P102 port_local_named: local port/full64 name;
P103 port_local_auto: local port/name0;
P104 port_ipc_named: IPC port/full64 name;
P105 port_ipc_auto: IPC port/name0.
Port profiles use FIFO PPU queue capacity2; queue profiles also create a named
local port. These tests validate object creation/lifetime and type rejection,
not actual SPU messages or IPC connections. IPC key0 fails before external
lookup; no external messages or real shared IPC setup occurs.

Every profile executes three20-operation transactions on the retained two-PPU
pair/TLS slots, first roles0/1/0. Native11 APIs128/129/130/131/133/134/135/136/
137/138/140 run through guest SC/table/binder. Two successful queue and two
successful port creations per transaction (twelve BE32 handles total/profile).
Native queue counter1 vs port0, queue type/protocol/capacity/name/key/id, port
type/full64 name/busy0/link and registry membership checked at every boundary.
Capacity0/128 and port type2 reject EINVAL without publishing handles or
modifying canaries. Local connects then duplicates return EISCONN; IPC ports
reject local connect EINVAL. Empty PPU tryreceive writes only count0 and leaves
the array untouched; SPU queues reject it EINVAL without writing outputs.
Disconnected/dead-linked send ENOTCONN, disconnect/destruction, stale port
APIs, port recreation, queue destruction while a port retains its reference,
new queue creation with a retired link then replacement, final detach/remove
and stale queue receive/drain/try/destroy paths checked. All valid requests
are nonblocking; no queue, timer or wake observation should occur here.

Per profile120SC/360dispatches/240pauses/1440instructions/TLS60 perworker.
Full64 name, error-path payload and stale receive timeout preserve ABI. All
GPR/FPR/VR/status/reservation/history/signed results/DATA/output canaries/TLS/
stacks/VM aliases/cache/settings/ID/CPU lifetime/scheduler restoration checks
retained. Worker joins precede port/reference then queue cleanup. Corrected
Build106 bridge prefix frozen at git blob
c1c54e0426a256204dea4bd77e3fddfdbad8d089 before new helper append. Prior P2–P93
bridge bytes remain unchanged; test_p94_fixture retains Build105 blob freeze.
All49 production patches and pinned upstream92b931b9fb5eef7f1317cb482917dfc19aceebd9
unchanged.

Validation PASS: four corrected test_p94_pair profiles and eight new
 test_p98_pair profiles under C++20 Wall/Wextra/Werror ASAN+UBSAN,
ASAN_OPTIONS=detect_leaks=0. Eight normal runs/16workers per profile, plus
applicable setup/context/ABI/registry/lifecycle negatives:96normal runs and
192workers across the12 changed/new profiles. New faults356 wrong queue type,
357 wrong capacity,358 wrong port type,359 wrong port name,360 busy counter,
361 incorrectly accepting capacity128,362 false SPU tryreceive success (SPU
profiles),363 false IPC local-connect success (IPC profiles); applicable
354/355 hook, connection/count/error/canary/setup mutations all detected.
Blocking/timer/payload delivery mutations remain in the separate P94 profiles.
CPU/VM/allocator/storage/clock/scheduler/notification are host interfaces; no
new native ARM/device result claimed. test_p98_fixture independently models
all eight creation/link/counter/handle/error/output lifecycles, freezes corrected
prefix, validates code/error tables and104 UI/Build107/iOS16 metadata. Python,
YAML/plist/whitespace and device stage parsing pass. Native allocator tests for
queue0x8d/port0x0e remain in CI; their native source/tests unchanged.

Workflow now has26 independent synchronization-host profiles (previous18 plus
new8) gating one installable IPA. Common fixture is test_p98_fixture.py.
Superseded builds still auto-cancel. Host-only original lv2.cpp restoration
for modeled statistics remains isolated from the production49-patch checkout.
No Actions polling after push; user reports outcome. Both handoffs updated.

Next: install the latest Build107 ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore
after Actions succeeds, reopen, run all104 diagnostics, send the startup log.
First verify corrected P94–P97 and all new P98–P105 before advancing. Last
verified native stage remainsP93 until new device evidence. Actual IPC
connections/SPU event delivery/multiwaiter ordering/priority-dependent port
busy handoff/serialized savestate/firmware/renderer/game boot remain untested.
Target iPhone13ProMax/iOS16.0/Dopamine/TrollStore, eventual Midnight Club Los
Angeles. Keep replies short; eight meaningful new diagnostics per batch where
logical, while repairing failed gates first.

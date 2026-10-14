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

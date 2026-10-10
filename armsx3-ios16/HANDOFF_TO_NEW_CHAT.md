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

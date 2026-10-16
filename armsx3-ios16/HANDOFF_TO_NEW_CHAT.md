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


## Build108 — native IPC event connections and buffered delivery (2026-10-14)

Build107 device evidence: ARMSX3-startup-20261014-203102-732-27601(1).txt,
PID27601. Exactly104 unique AUTO PASS stages P2-P105, followed by
AUTO PASS: all diagnostic stages completed; game boot remains untested.
P94-P97 now pass after the native port counter correction. P98-P105 creation,
queue capacity/type and named/unnamed local/IPC port lifecycle profiles pass.
No new crash or failed diagnostic in this log. Last verified native stageP105.

Build108 adds eight P106-P113 profiles for actual shared IPC queue connection,
publication and buffered event delivery. Profiles, in UI order:
P106 ppu_fifo_named; P107 ppu_fifo_auto; P108 ppu_priority_named;
P109 ppu_priority_auto; P110 spu_fifo_named; P111 spu_fifo_auto;
P112 spu_priority_named; P113 spu_priority_auto.
All use an IPC port, queue capacity2, and three private full64 keys
0xfedcba9810500000/1/2. Named source is0xfedcba9876543210; unnamed source uses
native process_getpid in high32 and the port ID in low32.

Each stage reuses the proven retained two-PPU/TLS/guest SC/table/binder design:
three20-operation transactions,120SC/360dispatches/240pauses/1440instructions,
TLS60perworker. Shared creation publishes the key; duplicate creation must
return EEXIST without changing the handle canary. IPC connections exercise
unknown key ESRCH, valid success, duplicate EISCONN, local-connect EINVAL and
key0 EINVAL. Two full64 messages fill the queue; overflow EBUSY preserves both.
PPU queues exercise partial BE64 array output, size0/count0 preservation,
nonempty drain/refill and subsequent receive. SPU queues exercise real buffered
sends and PPU receive rejection without changing outputs; no SPU waiter/mailbox
consumption is claimed. Native payload/order/source/queue/port/IPC registry
metadata is checked at all three paused instruction boundaries.

Destroying the shared queue must unpublish its key while a port retains the
retired pointer; send/disconnect return ENOTCONN and lookup ESRCH. Recreating
the same key produces a fresh queue and IPC reconnect replaces that dead link.
Final detach/port destruction/queue destruction and stale requests verify both
ID namespaces and the IPC keys are empty. Failure details include the full64
key, published ID and IPC validity. Existing private diagnostic keys and their
missing-key counterparts are rejected before activating cleanup; cleanup
removes only the three keys proved absent at entry. Workers join before object
and key cleanup; configuration/scheduler/ID/VM/TLS/cache/context/canary checks
remain intact. No external messages or other emulator sessions are involved.

The entire Build107 CoreBridge prefix is frozen at git blob
528d449d05cccb4a05c74a231e910f038817782a. All49 production patches and pinned
upstream92b931b9fb5eef7f1317cb482917dfc19aceebd9 remain unchanged.
CFBundleVersion108, MinimumOSVersion16.0,112 ordered UI stages P2-P113.

Host validation uses the actual pinned IPC manager class, generic lv2_obj
shared create/on_id_destroy hooks, event queue find/send/constructor, native
APIs, binder/SC/dispatcher and diagnostic bodies. Locking/shared-pointer/FXO,
CPU/VM/ID storage/clock/scheduler are host interfaces. Applicable negative
mutations include key truncation, publication leaks, duplicate-key acceptance,
missing connect assignment, payload/source/count/array/drain/overflow errors,
wrong metadata, ownership/hook/context/ABI failures. A preexisting IPC key
must survive a rejected diagnostic. test_p106_fixture.py independently models
all eight key/link/message/output lifecycles and freezes previous source.

Workflow matrix expands26to34 host profiles gating one installable IPA.
Common fixture becomes test_p106_fixture.py; superseded builds auto-cancel.
Local sanitizer/fixture/metadata verification and publication recorded below.
Do not poll Actions after push; user reports workflow completion.
Next: after Actions succeeds, install Build108 ARMSX3_iOS16_INSTALL_THIS_IPA
via TrollStore, reopen, run all112 diagnostics, send the startup log. Verify
P106-P113 before advancing. Firmware installation, renderer and game boot,
actual SPU waiter mailbox delivery, multiple-emulator IPC, multiwaiter ordering
and serialized savestates remain untested. Target iPhone13ProMax/iOS16.0,
Dopamine/TrollStore; eventual Midnight Club Los Angeles. Keep replies short.

Build108 local validation completed: all eight test_p106_pair profiles PASS
under g++ C++20 Wall/Wextra/Werror ASAN+UBSAN, with ASAN_OPTIONS=detect_leaks=0
for this runtime (same setting as existing CI). Eight normal runs and16workers
per profile,64normal runs/128workers total, plus all applicable negative
mutations and occupied-key preservation. Independent test_p106_fixture,
Build107 device stage parser, Python AST/YAML/plist/34-profile dependency
validation, three core shell syntax checks and git diff --check PASS. All
production patches are unchanged. New native ARM/iOS execution awaits Build108.


## Build109 — faster porting: firmware import and real executable intake

User explicitly clarified on2026-10-14 that the requested speedup is overall
porting, if appropriate at this stage; their PS3 firmware is already ready.
Shift to actual game prerequisites instead of more synchronization variations.
Build108 device log ARMSX3-startup-20261014-211100-268-27760.txt, PID27760,
passes112 unique ordered stages P2-P113 and the final all-stages completion.
Last verified native stageP113. No failed diagnostic in this device log.

Build109 adds two functional UIKit actions after the full readiness sequence:
Install firmware and Inspect EBOOT/ELF. UIDocumentPicker uses UTTypeData and
asCopy:YES; scope is held while copying to an app-owned temporary file. Core
operations run off-main with one intake action at a time, controls/idle timer
managed on main, crash marker persisted before the call and temporary input
removed afterward. User chooses their own PS3UPDAT.PUP in Files, no PC needed.
Both actions append details to the same startup log/transcript/export path.

Intake.cpp uses real native pup_object with SHA1-HMAC validation, bounded
header/entry preflight, version0x100 and update TAR0x300, SCEDecrypter with
native SCEPKG keys and the third decompressed TAR from each dev_flash package.
All TAR headers/checksums/lengths/types and relative dev_flash paths are checked
before native tar_object extraction into a fresh sibling staging directory.
Require sys/external/liblv2.sprx and vsh/etc/version.txt before publication.
Rename the prior dev_flash to a private backup, then rename staged dev_flash
into place; publication failure restores the prior directory. Extraction or
decryption failure leaves the existing installation untouched. Cleanup is
scoped to the operation's fresh stage; failed backup removal retains backup.
Destination is g_cfg_vfs.get_dev_flash() already configured by native Emu.Init;
no remount or Emu.Init reset during import. Native logs name package progress
and publication boundaries. Actual official-firmware installation awaits user
PUP selection on device; do not claim that HMAC fixtures install real firmware.

Executable intake uses native decrypt_self and ppu_exec_object on the selected
real file, validates loadable segment guest-address/memory bounds, then writes
the decrypted ELF atomically to cache/ARMSX3-prepared-executable.elf. No game
worker or renderer is started, and no assets from a game folder are imported
by this single-file inspection. UI states that execution is a subsequent
milestone; no playable game or real title memory-load claim. No license/RAP
management is added. Unsupported decryption is reported with a startup log.

Eight focused readiness stages P114-P121 (120 total): native disk read/write/
rename; missing/truncated/bad-magic PUP rejection; bounded tables/entry ranges
and native size rejection; authenticated PUP version/update/missing-entry;
PUP hash tamper rejection; native staged TAR extraction/path guards; the actual
selected-executable inspection path with synthetic ELF and invalid data;
transactional publication with an injected rename failure and rollback.
All synthetic files use unique disposable cache subdirectories and never
replace installed firmware. The entire Build108 CoreBridge prefix is frozen
at git blob ec4bb6ac7c2d47c52dc55256a08a87e7fb4b03bc; all49 production patches
and pinned upstream92b931b9fb5eef7f1317cb482917dfc19aceebd9 unchanged.

New local host test compiles the production intake source and portable policy
with actual pinned PUP parser and SHA1/HMAC code. An independent Python fixture
uses HMAC plus a known RFC HMAC vector. Real disk rename/rollback, all eight
probe bodies, complete install/inspect entry points, injected decoder failure
preservation and C ABI idle/input guards are checked under ASAN/UBSAN and
warnings as errors. TAR/SCE/ELF/backend/Emu interfaces are host models in that
check; new on-device P119/P120 and real PUP installation use original core
implementations. Do not confuse modeled decoder success with native SCE proof.

Workflow adds one intake-host job alongside existing34 synchronization jobs;
both gate the sole iOS IPA. Common fixture is test_p114_fixture.py. CMake links
Intake.cpp into the actual core and UniformTypeIdentifiers into UIKit app.
CFBundleVersion109, deployment16.0. No Actions polling after publish; user
reports completion. Both handoffs updated; current core README describes the
functional intake stage instead of the old compile-only P1 checkpoint.

Next device flow: install latest ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore,
reopen, Run all tests (120). If all pass, tap Install firmware, pick the user's
PS3UPDAT.PUP, keep app open until it finishes, share startup log. Once installed,
Inspect EBOOT/ELF may be used for their own executable and its intake log.
Remaining real-game blockers include frontend callbacks/runtime boot lifecycle,
RSX rendering (Vulkan/MoltenVK still disabled), audio/input integration, optional
LLVM/JIT backends and actual game execution. Next implementation should use
real firmware/title evidence to advance those prerequisites instead of returning
to exhaustive synchronization variants by default. Keep responses short.

Build109 local validation PASS: test_p114_intake under C++23 Wall/Wextra/Werror
ASAN+UBSAN (detect_leaks=0 in this runtime), all eight production probe bodies,
actual native PUP/SHA1 plus independent HMAC fixture/known vector, real host
file writes/renames/publication/rollback, modeled decoder failure preservation,
full install/inspect and stopped/no-worker/C ABI guards. test_p114_fixture,
Build108 device stage parser, Python/YAML/plist/host dependency checks, pinned
SCE/ELF/serialization API contract review, core shell syntax and diff whitespace
PASS. UIKit/Apple compilation and native real PUP installation await Actions
and device testing respectively. No game boot result claimed.


## Build110 — repair selected raw ELF intake from Build109 device evidence

Device log ARMSX3-startup-20261014-220603-549-27999(1).txt has118 unique
AUTO PASS stages P2-P119, then FAIL P120; P121 never started. Native P114-P119
storage/PUP bounds/authentication/hash rejection/TAR staging all passed.
The firmware action remained gated, so no real PUP installation was attempted.

Root cause is confirmed in pinned Crypto/unself.cpp: decrypt_self handles raw
ELF only when Emu.GetBoot() ends in .elf/.ELF. Intake has no boot file configured,
and called that function unconditionally. Native Emulator::Load decrypts only
SCE-magic SELF; Build110 intake now follows that routing. Inspect magic with
read_at; SELF uses decrypt_self, raw ELF moves the existing file directly to
native ppu_exec_object, unknown/truncated headers are rejected. Do not set or
mutate emulator boot state to work around this dependency. Log decryption and
PPU parsing separately. Failed intake preserves the previously prepared ELF.

P120 now exercises raw ELF as probe.elf and EBOOT.BIN, both native debug SELF
key versions0x80 (big-endian offset) and0xc0 (little-endian offset), and unknown/
truncated ELF rejection. Keep120 total readiness stages; all CoreBridge bytes,
production patches, workflow dependencies and prior diagnostic sequence remain
unchanged. CFBundleVersion110; no renderer/game boot/firmware success claim.

The host intake harness now compiles the actual pinned CheckDebugSelf and
decrypt_self bodies, with a deliberately failing retail SELF decoder interface.
Removed the fake identity decrypt_self that hid Build109's native dependency.
The host ELF magic field now matches the native little-endian storage. Host
fs::file is move-only; native routing sees real read_at/stream copy behavior.
Explicitly reproduce empty-boot decrypt_self(raw ELF) failure, then verify the
production intake succeeds without changing boot state, both debug headers
extract native bytes, malformed/decryption-failed inputs preserve the prepared
ELF, and unrelated boot names do not affect raw intake. Retail crypto/TAR/ELF/
FXO/fs backend remain host models; native PUP/SHA1/HMAC and SELF routing/debug
removal are extracted production implementations. Real SCE firmware packages
still await the user's PUP on device.

Build110 local validation: production intake/native-routing host suite under
g++ C++23 Wall/Wextra/Werror ASAN+UBSAN with detect_leaks=0; all8 readiness
probe bodies, independently authenticated PUP/RFC HMAC, real filesystem staging/
publication/rollback, failure preservation and C ABI idle guards PASS. Common
fixture preserves the complete Build108 bridge prefix and verifies120 ordered
stages, Build110/iOS16 metadata, file-picker gates and34+1 host dependencies.
Python/plist/workflow metadata and git diff --check PASS. Apple compile and
Build110 native P120/P121 are still pending user-reported workflow/device tests.

Next: install Build110 from ARMSX3_iOS16_INSTALL_THIS_IPA through TrollStore,
reopen, Run all tests. If all120 pass, tap Install firmware, select the user's
PS3UPDAT.PUP, keep the app open, share startup log after completion/failure.
Inspect EBOOT/ELF prepares their selected executable after firmware installation;
it does not launch the game. Advance actual firmware/runtime boot evidence next.
Do not poll Actions after publication. User reports completion. Keep replies short.


## Build111 — actual native runtime loading after real firmware/EBOOT intake

Build110 device evidence:
- ARMSX3-startup-20261014-225142-714-28147.txt: all120 unique ordered stages
  P2-P121 PASS, including repaired P120 raw ELF/both debug SELF encodings and
  P121 publication/rollback. The user selected PS3UPDAT.PUP; native PUP/HMAC,
  SCE package decryption and TAR extraction installed firmware4.93,23packages.
  INTAKE UI PASS and transactional dev_flash publication completed. This is
  actual firmware on the iPhone, not a synthetic installer result.
- ARMSX3-startup-20261014-231002-454-28147.txt: same installed firmware. Initial
  PS3_DISC.SFB selection correctly rejects metadata with no SELF/ELF header.
  EBOOT.BIN then decrypts via native SELF, parses via native PPU ELF, has5
  loadable segments and entry descriptor11963416. Prepared ELF saved at
  Library/Caches/rpcs3/ARMSX3-prepared-executable.elf. User's target is Midnight
  Club LA, but game identity/title ID was not confirmed through PARAM.SFO.
User says Let's gooo: proceed to actual runtime load integration. Do not return
by default to more synchronization variants or request firmware again.

Build111 adds Check runtime load after the existing120 stages. New Runtime.cpp,
RuntimeFrontend.cpp, RuntimeDispatch.mm and Runtime.h link into the existing core.
CoreBridge.cpp is entirely unchanged from Build110. All49 production patches,
pinned source/dependencies, stage order and34 synchronization profiles retained.
CFBundleVersion111, iOS16.0/A15/Dopamine/TrollStore. User reports Actions result;
do not poll Actions after publication.

The action uses the existing prepared ELF in cache and installed dev_flash.
Reject main-thread invocation, non-fully-stopped emulator, live CPU contexts,
missing/invalid/oversized prepared ELF or missing liblv2 before attempting load.
Copy config to a unique temporary file, static PPU/SPU decoders, LLVM precompile
OFF, force liblv2.sprx LLE, null video/audio, null keyboard/mouse, autostart OFF,
autoexit/big-picture/GameMode/display-sleep prevention OFF, internet/PSN disabled.
No modification to persistent config.yml. Native BootGame uses direct=true and
cfg_mode::config_override, which survives Init's default reset and avoids custom
or database config overriding the request. SetForceBoot(false) prevents the
other native autostart path. No Emu.Run/Resume invocation in this implementation.

All49 fields of the exact pinned emu_callbacks ABI are bound. Main dispatch uses
GCD to UIKit main with wake flag/notify acknowledgement; actual native null RSX,
Keyboard/Mouse/Pad/Audio/Camera/Music factories and log-only progress dialog.
There is no Vulkan/Metal display, controller device or audio hardware integration
claimed. on_run rejects unexpected execution, on_resume/missing-firmware/stop
watchdog/callback exception flag frontend failure. Unsupported package installs
return failure. Callback bindings remain installed for the process lifetime;
operations are serialized by the UIKit intakeBusy/main-thread control state.

After BootGame, require no_errors + native ready state and effective static/null/
autostart-OFF settings. Inspect actual registered main module entry and every
loadable segment's guest readable mapping; count must match the prepared ELF.
List registered firmware PRX modules with paths, IDs, segment/function counts.
Require loaded liblv2.sprx with PRX_STATE_STARTED and actual segments; forcing HLE
fallback is explicitly not success. Require at least one PPU context, all with
cpu_flag::stop. Native CPU thread startup defaults STOP+WAIT and its task loop
cannot execute queued guest entry while STOP is set. Firmware/library start
calls and guest entry remain queued for a later Run step.

Always call native Kill(false) after an attempted load, even a failed/throwing
load. Wait up to30seconds for Emu.IsStopped(true) + zero live CPU threads, then
synchronously drain UIKit's main queue: native on_stop occurs before the final
main cleanup lambda returns, so the queue barrier prevents racing later config
restoration/import. Restore both g_cfg and g_backup_cfg snapshots after cleanup.
On timeout/cleanup/frontend failure return-2, latch UI failed, retain the pending
runtime crash marker and require reopening. Recoverable load failures return-1
only after successful cleanup; share log. Runtime C ABI bounds detail buffer.
Intake idle guard now also uses IsStopped(true), since default IsStopped treats
stopping as stopped and zero CPU count can precede final object cleanup.

Runtime uses only the cached ELF. It has no PARAM.SFO/game-folder/title metadata
and does not import game assets, mount a real disc, start guest entry or produce
video/audio. Do not claim playable Midnight Club or actual execution on success.
Next native evidence should establish real mapping/firmware PRX/context/cleanup,
then advance full game-folder import and boot/execution/render integration.

Host validation test_runtime.py compiles unchanged production runtime/frontend
logic against the actual49-field native callback ABI and actual Emulator::BootGame
and SetForceBoot bodies. Native Load, config serializer, fs/FXO/VM/input/RSX and
UIKit queue are explicit host interfaces. Tests include prerequisite/main-thread/
fully-stopped/C ABI guards, native BootGame config routing, success, failed load,
throw after contexts, absent main registration, unreadable/wrong count segments,
wrong entry, missing real firmware PRX, unexpected Run/frontend failure, missing
or started PPU contexts, delayed stop, cleanup timeout, restoration, reusable
success after failure, and queue/wake acknowledgement. Host only substitutes a
30ms timeout for the app's30sec budget. G++ C++23 Wall/Wextra/Werror ASAN/UBSAN
with detect_leaks=0 PASS. Existing intake suite PASS, including native PUP/SHA1/
SELF-routing/debug removal and new zero-worker-but-stopping intake rejection.
Common fixture checks120 ordered stages/old bridge freeze/Build111 metadata/
runtime config and UI gates; Apple frontend compile/native Load still await
Actions/user device testing. Workflow adds runtime host check to intake-host,
retains34+1 host jobs gating the sole installable IPA.

Next device flow: update existing app using Build111 ARMSX3_iOS16_INSTALL_THIS_IPA
in TrollStore, reopen, Run all120 tests, tap Check runtime load and share startup
log after completion or failure. Installed firmware/prepared ELF may be reused.
If prepared file was evicted, Inspect EBOOT/ELF again; reinstall firmware only
if the app says it is missing. No Actions monitoring; user reports workflow.
Keep replies concise. Both handoffs and current core README updated.


## Build112 — fix native JIT finalization after successful runtime loading

User reports 'Crashed at runtime load' with:
- ARMSX3-startup-20261014-234707-324-28366.txt. Exported previous unfinished
  Build111 session PID28347, all120 unique stages P2-P121 PASS. Firmware4.93
  reinstalled successfully, EBOOT.BIN decrypted/parsed with5 LOAD headers and
  entry11963416. Actual native BootGame returned result0/state6 (ready). The
  check verified2 nonempty mapped LOAD segments, real liblv2.sprx PRX id587203072
  with2segments/3635functions, one PPU context with STOP flag. Guest not started.
  Native Kill then stopped all threads, unmounted VFS, cleared FXO objects.
  Before stopped-state completion it hit the Apple JIT portability boundary.
- ARMSX3CoreLoadTest-2026-10-15-014641.ips: Build111, EXC_CRASH/SIGABRT,
  abort() on main thread. Full stack jit_runtime::finalize -> Emulator::Kill's
  final main-queue callback -> ios_runtime::dispatch_main. Core UUID
  55a20afd-8350-38c4-9cac-1c5fadda1e38. The startup log records the exact missing
  pthread_jit_write_protect_np boundary and matching frames. Cause is confirmed
  finalization, not failure to decrypt/map/load firmware, device memory pressure,
  guest execution or a bad Files selection. No full runtime-cleanup PASS yet.
- ARMSX3CoreLoadTest.diskwrites_resource-2026-10-14-103252.ips is older Build105,
  PID23310, disk-write resource report, action taken none. It is not the latest
  Build111 abort and should not be conflated with the cleanup failure.

Patch0050-ios-empty-jit-finalize.patch adds an iOS-only early return in native
Utilities/JITASM.cpp::jit_runtime::finalize. If BOTH full allocation counters
are zero AND BOTH startup snapshots are empty, the mutable2GiB arena is unused.
Immutable iOS functions/SPU heap bootstrap do not use that arena (existing
patches0009/0010 strategy). Native finalization must not reserve/decommit/reset
it, ask for macOS write protection or restore a zero-byte snapshot. Log that
immutable functions remain published, then return. Existing initialize already
has the empty-counter guard from0010; this closes its missing finalize half.

Do not replace/disable the general apple_jit_write_protect failure boundary.
The actual helper/header is unchanged; any nonempty code/data counter, including
high-water-only state, or nonempty snapshot still follows the original mutable
path and fails closed if that API is absent. The original macOS/Linux reset,
restore, protection and cache maintenance behavior is unchanged. Real immutable
RX mappings remain intact for process lifetime, as required by their allocator.
Do not implement a generic no-op JIT protection fix or rewrite live RX pages.
This does not enable mutable JIT/LLVM/Vulkan/game execution.

Build112 changes only patch0050, bundle version112, focused host lifecycle tests,
workflow intake-host command/common metadata fixture, and README/handoffs. All
120 diagnostics, CoreBridge.cpp, Runtime.cpp/Frontend/Dispatch, Intake and the
original49 production patches are unchanged. There are now50 production patches.

New test_jit_lifecycle.py extracts actual pinned initialize/finalize bodies,
materializing exact0010/0050 patch hunks and the two existing0003 API replacements
in an isolated source copy when CI's checkout is pristine. It uses the actual
apple_jit.hpp missing-symbol boundary and actual immutable_jit.hpp publisher.
With the pre-fix finalizer, zero-state cleanup abort is reproduced. Fixed iOS
initialize/finalize run64cycles and a real RW->RX x86-host return42 function
continues to execute with unchanged bytes, with zero mutable arena reservation/
allocation/reset/decommit/write-protection. Six separate nonempty code/data/
snapshot/high-water cases still abort at the missing symbol. macOS/Linux macro
variants retain snapshots, discard post-start data, perform reset/protection,
restore startup counters/bytes and execute instruction-cache maintenance.
The mutable arena operations are bounded host models; not real macOS/iOS memory
backends. Intentional abort cases run as subprocesses with core dumps disabled.
Do not misstate x86 host code as device ARM execution.

The existing runtime host check now invokes the actual native JIT finalizer in
its final main-queue teardown operation. Thus its load, partial-failure, context,
timeout, wake acknowledgement and config-restoration scenarios cover this native
cleanup boundary instead of bypassing it with an empty Kill model. Other native
Load/FXO/VM/device/config backends remain host interfaces, clearly documented.
Native loader/PRX/mappings/STOP context were verified by the phone; patched cleanup
is still pending the next device run. No Actions monitoring after publication.

Local validation: g++ C++23 Wall/Wextra/Werror ASAN+UBSAN with detect_leaks=0:
native JIT lifecycle/regression/negative/non-iOS branches PASS; integrated runtime
suite PASS. Clean pinned JIT source materialization matches intake-host's raw
checkout path and passes. New patch applies cleanly after all49 existing patches.
Common fixture/Python/YAML/plist/shell/unchanged bridge/whitespace checks recorded
before publication. iOS compilation and complete device teardown await user.

Next: install Build112 ARMSX3_iOS16_INSTALL_THIS_IPA through TrollStore, reopen,
Run all120 tests, tap Check runtime load, keep app open and share startup log.
Reuse installed firmware and prepared EBOOT if present; repeat their import only
if the app says one is missing. Expected new boundary: 'iOS JIT finalize: unused
mutable arena; immutable functions retained', then callback stop completed,
fully-stopped/zero CPU context cleanup, RUNTIME UI PASS. If any mutable arena
state is actually present on device, retain the fail-closed evidence and inspect
its allocator source rather than bypassing protection.
Then advance complete game-folder/PARAM.SFO/disc assets and guest execution/
render integration. Current cache-only load cannot establish actual title identity
or playable Midnight Club LA. Keep replies short; user reports Actions result.


## Build113 — repair the workflow's historical patch validator (2026-10-15)

User reports Build112 workflow failed. Run38660569062 at commit
f4d49503a67f09e0afad5b404aa6e75cc5c5d5a8 passed all35 host jobs
(34 synchronization profiles plus intake/runtime/native-JIT lifecycle). Core job
116180946509 stopped at Apply iOS core patches, before iOS compilation:
test_p73_patch.py asserted the entire patch directory contained exactly49 files.
Build112 added patch0050 for the confirmed native runtime cleanup abort.
The obsolete catalog assertion, rather than a compilation or runtime result,
prevented that repair from reaching an IPA.

Build113 scopes test_p73_patch.py to its exact historical ordered prefix0001
through0049. It still requires every predecessor, patch0049's exact filename,
clean apply/check, unchanged prior services/scheduler/probes, and the observer
body/declarations. Newer patches no longer alter this historical test's target.
The production workflow still applies/checks every patch, including0050.
Only this validator, bundle/fixture version113, README and both handoffs changed.
No native/runtime/UI/intake code or production patch changed from Build112.
All120 diagnostics and the unused-mutable-JIT cleanup repair remain intact.

Validation: ran the complete exact Apply iOS core patches workflow shell step
against a fresh detached local clone of pinned upstream
92b931b9fb5eef7f1317cb482917dfc19aceebd9. Pinned source audit, P43 historical
patch check, P114/common fixture and all earlier fixture checks, corrected P73,
P76/P82/P86/P90/P94 registry checks, all50 git apply --check/applications, and
core/iOS/header overlays passed. ASAN_OPTIONS=detect_leaks=0 is needed locally
because LeakSanitizer cannot inspect /proc tasks in this environment; ASAN/UBSAN
remain enabled by the native registry checks. The initial archive-only staging
attempt lacked .git for the audit, so it was replaced by a pristine real clone.
No workflow command was skipped. This validates preparation, not iOS compilation
or phone cleanup; those remain pending Build113's workflow/device results.

Next: after Build113 workflow succeeds, install ARMSX3_iOS16_INSTALL_THIS_IPA
through TrollStore, reopen, Run all120 tests, then Check runtime load and share
the startup log. Reuse installed firmware4.93/prepared EBOOT if still present.
The phone already reached native ready state on Build111; expected new result
is unused mutable arena skipped, final stopped callback completed and RUNTIME
UI PASS. No guest entry is started. Preserve the missing-API failure for any
nonempty mutable arena. No LLVM/Vulkan/gameplay claim. Complete game-folder/
PARAM.SFO/assets import and execution/rendering remain later work. Keep replies
short and do not monitor Actions after publishing; user reports the result.


## Build114 — Build113 device cleanup PASS; full disc-folder import (2026-10-15)

New user log ARMSX3-startup-20261015-005505-758-28700.txt is Build113/PID28700.
All120 ordered P2-P121 diagnostics PASS. Firmware4.93 installed with23 native
packages; real EBOOT parsed with5 LOAD headers, entry11963416. Native BootGame
returned0/state6, mapped2 nonempty segments, registered real liblv2.sprx
id587203072 with2segments/3635functions and one stopped PPU context. Kill stopped
all threads, cleared FXO, logged 'iOS JIT finalize: unused mutable arena;
immutable functions retained', completed the stop callback, reached fully-stopped
with zero live CPU threads and RUNTIME UI PASS. Build111's cleanup abort is
confirmed fixed on the phone. Guest entry remained stopped; no gameplay claim.
Build113's workflow necessarily produced this installed IPA; no Actions polling.

Build114 advances actual functionality instead of extending the120-stage table.
New GameImport.cpp/.h implements armsx3_core_import_game. Select the complete
PS3 disc root containing PS3_DISC.SFB and PS3_GAME, including PARAM.SFO,
USRDIR/EBOOT.BIN and assets. Only DG disc folders are supported; no ISO/PKG,
update-only or installed HG folder support is claimed. One active imported disc
is kept under the configured dev_flash sibling ios-games/active-disc. The title
identity is read from the selected native PSF, never assumed to be Midnight Club.

Importer checks fully-stopped/zeroCPU state, required regular files/directories,
native Emulator::IsValidSfb and native psf::load/get_string. A bounded PSF preflight
protects native key-NUL reads/table allocation and invalid entry sizes. Requires
four uppercase ASCII letters plus five digits in TITLE_ID, a nonempty bounded
control-free title and CATEGORY=DG. Directory inventory rejects links/special
nodes/overlapping storage roots, bounds entry count and total-byte overflow,
checks free space for all new files plus256MiB, and validates EBOOT through the
existing native intake route before copying. It copies every selected file and
empty directory once with std::filesystem::copy_file, checks size/mtime, rechecks
the complete source inventory, staged identity and EBOOT, then uses the existing
same-volume rename/rollback publisher. Invalid imports preserve the prior game,
firmware and independent prepared-ELF cache. Unique staging trees are removed on
caught failures; superseded backup removed after successful publication. Progress
files/bytes logged every256MiB or at completion. Does not prove a source dump has
all title-required assets; it faithfully copies the selected stable tree.

Intake.cpp factors its unchanged raw-ELF/native-SELF routing into exported C++
ios_intake::read_executable; inspect still parses/bounds segments and persists
only when requested. Runtime preflight uses the same reader, supporting original
EBOOT SELF instead of only an already decrypted cache. Production tests retain
actual native CheckDebugSelf/decrypt_self bodies and all8 intake probes.

New armsx3_core_check_game shares runtime check/configuration/frontend/teardown.
It loads original active-disc/PS3_GAME/USRDIR/EBOOT.BIN through native BootGame
with direct=true, static decoders, real liblv2, null video/audio, autostart=false.
The original path is deliberate: native Load discovers PARAM.SFO and SFB up the
USRDIR/PS3_GAME ancestors, decrypts original SELF and mounts /dev_bdvd. It avoids
the native directory-scan mode that would force LLVM/precompilation. After ready,
require actual Emu title/ID/category match the imported PSF, canonical boot path
match selected EBOOT, canonical VFS /dev_bdvd and PS3_GAME roots/SFO/EBOOT match,
and representative USRDIR asset path resolves when present. Then require actual
ELF entry and nonempty mapped segment count/readability, real started liblv2,
stopped PPU context(s), clean frontend and fully stopped/zeroCPU/mainqueue-drained
Kill completion. Restores config and backup exactly as cached check. A load/mount
mismatch fails after cleanup; incomplete cleanup retains the existing -2/reopen
policy. No Run/Resume, guest execution, renderer/audio/controller integration.

UIKit adds Import game folder and Check game load alongside existing controls.
Folder picker uses UTTypeFolder with asCopy:NO and NSFileCoordinator reading
under a security-scoped resource. Native code creates the single staged copy;
no temporary duplicate of a multi-GB game. Files remain app-owned after scope
release. Both actions run on a background queue, preserve the pending-operation
marker/idle timer and serialize with diagnostics/import/runtime buttons. Existing
firmware/ELF file pickers retain their original asCopy:YES route. No firmware
reinstall or standalone executable inspection is needed if firmware remains and
the full disc is being imported. Keep app open during copy/load.

Host validation: production game importer compiled with pinned native PSF
entry/load/get_string code and native SFB validator, independent binary SFO
fixture and actual disk operations. Full tree/empty dirs/assets byte equality,
replacement, rejection of bad size/count/key/table/format/identity/category,
insufficient-space sparse input, links/overlapping roots/idle/C ABI boundaries,
removed/added source files and corrupted staged EBOOT all preserve old import
and remove staging. Executable decoding is an interface model in this new
harness, separately covered by native intake/phone evidence. Existing runtime
harness additionally covers success and wrong title/category/title ID/boot path,
disc mapping and missing asset mapping, with cleanup/config restoration for each.
Native BootGame, all49 callback signatures and actual patched JIT finalizer
remain in that harness; native Load/VM/FXO/devices/config/VFS are host models.
NSFileCoordinator/file-provider behavior and full-disc native loading await phone.

The workflow intake-host gate now includes test_game_import.py with unchanged
34 synchronization profiles. New CMake source GameImport.cpp and bundle114.
All50 production patches, CoreBridge, frontend/dispatch and120 stages unchanged.
Local g++ C++23 Wall/Wextra/Werror ASAN+UBSAN checks use detect_leaks=0 because
this host prevents LeakSanitizer /proc inspection. Exact clean-checkout host and
core-preparation workflow steps are checked before publication. iOS compilation
and new game-folder device result remain pending; do not claim they passed.

Next: install Build114 ARMSX3_iOS16_INSTALL_THIS_IPA through TrollStore, reopen,
Run all120 tests, reuse installed firmware, Import game folder (select parent
containing both PS3_GAME and PS3_DISC.SFB), keep open, Check game load, share log.
Do not request or fabricate the user's game dump. Real title/ID, source copy and
mount/cleanup result from that run determine the next execution/render work.
Keep replies short; user reports Actions success/failure; do not monitor Actions.


## Build115 — full Midnight Club disc load PASS; bounded native guest execution (2026-10-15)

New phone log ARMSX3-startup-20261015-012638-552-29061.txt is Build114/PID29061.
All120 ordered P2-P121 diagnostics PASS. Complete selected disc import passed:
19files/5,668,431,532bytes (~5.67GB), source snapshot/staged checks and transaction
publication, actual PARAM.SFO title 'Midnight Club: Los Angeles', TITLE_ID
BLUS30442, CATEGORY DG. Native BootGame from original imported EBOOT returned0/
state6. Actual native title/ID/category, boot path, /dev_bdvd and PS3_GAME roots,
PARAM.SFO/EBOOT and carchive_audio.rpf asset mapping all matched. Native main
mapped2nonempty segments, real liblv2 id587203072 had2segments/3635functions,
one PPU stayed STOP. Native Kill joined threads, unmounted disc/assets/firmware,
cleared FXO, skipped the unused mutable JIT arena and completed fully-stopped/
zeroCPU/mainqueue-drained cleanup with GAME UI PASS. Original SELF loading and
coordinated full folder import are now device verified. Guest entry not started.
This is the confirmed real title identity, replacing earlier unconfirmed guesses.

Build115 adds functional Run game (3 seconds), retaining all120 diagnostics and
both existing load-only actions. It reuses the imported disc and firmware; no
5.67GB recopy needed if the app retained those files. armsx3_core_run_game calls
the common runtime path with game=true/execute=true. It first performs all native
identity/disc/ELF/real-firmware/STOP/frontend checks. A one-use frontend start
permit is then armed and consumed by on_run. Native Emu.Run(false) starts the
emulator; the actual native RSX startup callback calls RunPPU, releasing native
queued PPU initialization/firmware/game work. Do not directly call RunPPU from
the app; that would race the native RSX startup. Emu.Run is main-queue synchronous
and exceptions are propagated to the worker. All load-only actions still reject
on_run, all unexpected extra starts and Resume stay rejected.

Worker waits at most15seconds for native running state (not merely starting),
then monitors a3second guest window with atomic state/liveCPU heartbeats, allows
a guest early stop after running, and requests native Kill(false) on UIKit's main
queue. It reads no live CPU registers or non-atomic instruction counters. The
common teardown still waits up to30seconds for complete stop, drains finalmain
queue and restores g_cfg/g_backup_cfg. Run-only temporary configuration enables
PPU call history and sets native channel regex .* to warning, retaining warnings/
errors while avoiding per-call notice/trace synchronous fsync traffic. After
cleanup native configure_logs restores the prior channel configuration too.
Native Run/RunPPU, interpreter, firmware, null RSX and devices remain native;
LLVM/mutable JIT/Vulkan/MoltenVK are not enabled by this feature.

Patch0051-ios-guest-execution-lifecycle.patch has two iOS-only additions:
- System.cpp declares/calls armsx3_ios_runtime_capture_stopped after every native
  emulation-thread join and before semi-destructors/context destruction. No
  scheduler/guest mutation. Existing50 patches unchanged;51total now.
- RSXThread.cpp startup callback ignores itself if Emu is no longer starting.
  The host timeout scenario caught the late queued start -> RunPPU ensure race.
  Explicit Run and Kill are main-queue serialized and this callback checks state
  on that same queue, so an old startup request cannot restart a stopped run.
  Non-iOS callback behavior is unchanged. Do not remove native ensure guards or
  force state/CPU flags directly from UIKit.

New RuntimeCapture.cpp arms one joined snapshot only for an explicit guest run.
After native joins it enumerates registered PPU/SPU contexts, logs PPU id/PC/
exec_bytes/4/native completed HLE-LV2 history index/last function, up to8 recent
retained calls for the first16PPUs, SPU id/PC/block counter for first8SPUs, and
aggregates. Reads occur before context destruction with owners joined. A mutex
protects the returned summary and atomic one-shot arm prevents duplicate reads.
Contexts that retired/unregistered before shutdown can be absent; these counters
are surviving-context evidence, not complete process totals or a benchmark. SPU
blocks are backend-dependent and may remainzero. A successful action requires
captured, error-free, nonzero PPU instructions OR completed calls plus complete
cleanup. Missing/zero evidence, paused/error state or startup timeout fail with
log detail. A frontend/cleanup failure retains -2/reopen policy. Fatal native CPU
errors can abort the process and leave the existing pending-operation marker.
No device guest-execution success, menu progress or playable FPS is claimed yet.

RuntimeDispatch adds invoke_main: synchronous UIKit queue execution, captured
std::exception_ptr rethrown on the worker, preserving main-thread operation order
and normal C++ error handling. Existing asynchronous native callbacks/wake-ack
protocol and final drain remain. UIKit Run game button reuses serialized background
runtime action, all120 readiness gate, pending marker, idle timer and failure
handling. It says keep app open; no GPU display/audio/controller presentation in
this initial execution window. Execution markers are logged before native Run,
on accepted callback, running state, heartbeat, window end, joined capture, cleanup
and final UI result. A black/no game picture is expected with null video/audio.

Host test_runtime.py now compiles production runtime/frontend/capture, pinned
native BootGame/SetForceBoot AND actual native Run/RunPPU bodies plus patched RSX
startup callback and joined-capture hook. PPU initialization/guest work/RSX queue/
Load/VM/FXO/devices/config and UIKit remain explicit host models. Modeled work
provides known counters solely to verify observation/report logic; do not call
that device ARM or real game execution. Covers authorized one-shot start, original
cached/game load cases, partial load/firmware/mapping failures, missing inputs,
startup timeout, zero progress, unexpected extra start/paused state, missing or
failed capture, late RSX callback after stop, joined-only/one-shot field reads,
automatic stop/config/log restoration and existing timeout/wake/cleanup cases.
Native initialize/finalize and actual Apple missing-symbol boundary remain in the
suite. ASAN+UBSAN Wall/Wextra/Werror use detect_leaks=0 for host /proc restriction.

test_runtime_capture.py reconstructs native System/RSX files from the exact pinned
git objects and applies the first50 production patches in isolation, then0051.
It verifies capture after native finished joins/before destroying_context and
that removing the scoped additions restores prior source byte-for-byte. It
exports the actual guarded RSX callback and hook into the runtime host test.
The existing workflow host gate invokes that validator through test_runtime.py;
34 synchronization profiles unchanged. CMake includes RuntimeCapture.cpp; version
115/metadata fixtures/README/both handoffs updated. CoreBridge/all120 stages,
GameImport/Intake/first50patches remain unchanged. Exact clean pinned host and
all51-patch core-preparation steps are validated before publishing. iOS compile
and real guest-run result remain pending this build's workflow and phone.

Next: install Build115 ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, reopen,
Run all120 tests, reuse existing firmware/disc if present, tap Run game (3 seconds),
keep app open through automatic stop and share startup log; if a crash also share
matching .ips. Avoid redundant firmware/game reimport unless reported missing.
The resulting native running/startup/last-call/CPU counters determine subsequent
execution fixes and rendering/audio integration. Keep responses short and no
Actions monitoring after publication; user reports success/failure.


## Build116 — static SPU startup guard fix (2026-10-15)

Device evidence: ARMSX3-startup-20261015-020122-221-29413.txt exports the
unfinished Build115 Game execution (3 seconds), PID29391; the matching
ARMSX3CoreLoadTest-2026-10-15-040050.ips is Build115/PID29391, core UUID
77324877-7a9c-30d2-94fb-585e2a2bc099. All120 diagnostics passed. The real
Midnight Club: Los Angeles [BLUS30442], DG, original EBOOT load again reached
native ready/state6 with two nonempty segments, real liblv2 and matching
SFO/disc/EBOOT/carchive_audio.rpf mappings. Run(false) and the explicit one-use
start callback were accepted. PPU[0x1000000] entered initialization, then
spu_cache::initialize(bool) constructed jit_write_guard and aborted at the absent
pthread_jit_write_protect_np Apple boundary. Symbolized constructor+100 and
spu_cache::initialize+64 match the startup log. Running state was never reached;
there is no three-second guest window, joined counter result or cleanup PASS.
The preceding .eh_frame warnings are not the proven abort cause. This is a
startup guard failure, not Build111's already-fixed empty-arena teardown abort.

Patch0052-ios-static-spu-cache-startup.patch changes only the initial local guard
in native SPUCommonRecompiler.cpp spu_cache::initialize. For iOS, optional guard
emplacement occurs only when the decoder is not _static. The static path assigns
the interpreter pointer and fills the existing ordinary heap dispatcher; it does
not generate or modify code. The complete original cache-path/file/queue/worker
continuation is preserved. Dynamic/asmjit/LLVM paths retain the real guard and
missing-API rejection. macOS retains the original scoped guard and Linux retains
its existing behavior. Global Apple JIT protection and immutable publication are
unchanged; do not make apple_jit_write_protect a no-op. First51 patches unchanged;
52 total. Production Runtime/Frontend/Capture/Intake/GameImport/CoreBridge and
all120 diagnostics unchanged from115.

New test_spu_cache_startup.py reconstructs pinned native SPU source and JIT.h from
git objects, applies the exact prior51 patches to those files then0052, and proves
that removing the new conditional restores the full original source byte-for-byte.
It compiles the actual native initialize prefix through dispatcher/cache-path
setup, the actual native jit_write_guard and real Apple portability boundary.
The remaining cache-file I/O and compiler continuation are an explicit named
host interface, not a full native cache/backend test. Before-patch static iOS
startup reproduces the missing-API abort. Patched static iOS startup succeeds;
all three non-static decoder variants still abort as expected. Eight cycles check
all1<<20 heap dispatcher slots, interpreter pointer, empty/nonempty cache path,
build flags, unchanged real immutable RX bytes and zero mutable-arena work.
macOS all decoder variants preserve guard pairing; Linux original behavior is
retained. ASAN+UBSAN/Wall/Wextra/Werror remain enabled, with detect_leaks=0 for the
host environment's /proc restriction and core dumps disabled for intentional
negative aborts.

The existing runtime host test now executes that same actual SPU prefix and guard
inside its modeled PPU notification, before FinalizeRunRequest. It retains actual
native BootGame/Run/RunPPU, callback ABI49, production runtime/frontend/capture,
native JIT finalization, late RSX callback, one-use permission, startup timeout,
paused/zero-progress/missing-or-failed capture, stop/config/log restore coverage.
Remaining PPU/guest work, Load/VM/FXO/devices/config/UIKit and cache continuation
are host models. This catches the specific Build115 startup boundary that115's
PPU initialization model skipped. It does not establish device guest execution.

Workflow intake-host adds the SPU startup regression;34 synchronization profiles
and the existing35-host-job dependency remain unchanged. Bundle version116,
metadata fixture, README and both independent handoffs are updated. Run the exact
clean pinned intake-host and all52-patch core-preparation steps before publishing.
An actual iOS compile/link and phone run still belong to the workflow/device.

Next: install Build116 ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore after the
workflow succeeds. Reopen, Run all120 tests, reuse installed firmware and imported
disc, then Run game (3 seconds). Keep the app open through automatic stop and
share the startup log; if it crashes, also share the matching .ips. Do not repeat
the5.67GB game import unless it is missing. Rendering/audio/controller presentation
remain future work. Keep replies short, English, no images. After publication,
verify the workflow queued once and do not monitor Actions; user reports result.

Build116 prepublication validation PASSED in a fresh shared clone at pinned
92b931b9fb5eef7f1317cb482917dfc19aceebd9: the exact YAML intake-host command
(fixture, intake, runtime, JIT lifecycle, SPU startup, game import) and exact core
Apply iOS core patches command both exited0. All52 patches apply; reverse-check
of0052 and byte comparisons of both installed overlays passed. Python AST, YAML,
plist/build116 and workflow shell syntax plus git diff --check passed. Prior51
patches, Apple/immutable JIT headers and production runtime/intake/import/bridge
sources remain unchanged. The unchanged34 synchronization profiles are left to
Actions rather than redundantly rerun locally. iOS compile/link/device result
still pending. No Actions monitoring after publishing.


## Build117 — static SPU thread entry protection (2026-10-15)

Build116 device progress/crash: attached ARMSX3-startup-20261015-023410-566-29730.txt
exports previous unfinished Game execution (3 seconds), PID29712. Matching
ARMSX3CoreLoadTest-2026-10-15-043349.ips is Build116/PID29712, EXC_CRASH/SIGABRT,
faulting thread39 SPU[0x0000200], core UUID ab8fffae-1487-3ced-af17-a9c447f1428d.
All120 diagnostics passed, firmware installed, full19-file/5,668,431,532-byte
Midnight Club: Los Angeles [BLUS30442], DG, imported and game load/cleanup passed.
Run again passed title/segments/firmware/disc/SFO/EBOOT/carchive_audio.rpf checks.

Patch0052 worked on phone: native running state was reached at1792031628.650217;
heartbeat reported2liveCPUobjects. Guest firmware/game startup executed real
syscalls, loaded libsre/libnet/libfs/libusbd, created PrimaryCellSpursKernelGroup
with5SPUs and SecondaryCellSpursKernelGroup with1SPU, PPU SPURS handler threads,
RAGE printf threads and event ports/queues. Later calls include cellGameBootCheck,
cellGameGetParamString, cellGameContentPermit and cellSysutilRegisterCallback.
This is real startup execution evidence beyond load readiness. Do not claim a
completed window, joined instruction totals, menu, rendering or playable FPS.

At1792031628.717593 six SPU threads hit the absent pthread_jit_write_protect_np
boundary. The backtraces all enter spu_thread::cpu_task +0x28c33c. The .ips places
spu_thread::cpu_task+1340 below an optimizer-shared cold abort block misleadingly
named named_thread<Emulator::Load...>::trampoline cold.5; this is not the original
loader thread failure. Actual native cpu_task begins with an unconditional Apple
execute-mode call, even for static interpretation. There was no clean stop,
joined capture or completed three-second result. The preceding eh_frame/unknown
cellLibprof warnings are not the proven abort cause.

Patch0053-ios-static-spu-thread-entry.patch adds an iOS-only condition around that
one entry call: require it if jit is present OR configured decoder != _static.
Static with no JIT uses native C++ interpretation and existing immutable gateways;
it does not mutate code and needs no per-thread mutable-JIT protection transition.
Any non-static decoder, including dynamic with jit==null, retains the real call.
A static configuration with a JIT instance also retains the boundary. macOS still
always calls the original protection API; Linux is unchanged. First52 patches,
Apple/immutable JIT headers, production runtime/frontend/capture/intake/import/
bridge and all120 diagnostics remain unchanged.53patches total.

Audited static SPU continuation: cpu_task's no-jit loop calls g_interpreter then
native old_interpreter via the existing immutable ARM gateway/heap dispatcher.
old_interpreter contains no mutable-code protection call. Recompiler dispatch,
branch patchpoints, LLVM and worker code keep their protection calls. PPU static
execution already excludes its non-static-only guard. General fault-recovery
Apple protection is untouched; do not disable the global boundary or conflate
future memory faults with this entry-only abort. Forced-interpreter environment
behavior is unchanged and is not used to broaden this exception.

New test_spu_thread_entry.py reconstructs both native SPU files from pinned git
92b931b9fb5eef7f1317cb482917dfc19aceebd9, applies the first52 scoped patches then0053.
Removing0053's conditional restores all of prior SPUThread.cpp byte-for-byte.
Compiles complete actual native spu_thread::cpu_task AND
spu_recompiler_base::old_interpreter bodies with the actual Apple portability
header/missing symbol. Original116 entry reproduces SIGABRT. Patched static iOS
passes64entries:8cycles of six concurrent SPURS threads, plus raw and isolated
pre-stopped entries. Native PC masking/interrupt setup, interpreter branch and
advance loop, stop checks, interrupt-work flag cleanup, group cleanup and real
immutable executable RX bytes are checked. The tiny instruction table handlers,
CPU state/storage/group/logging/platform/JIT gateway interfaces are explicit host
models; it is not a full native SPU ISA/scheduler or ARM gateway execution test.
Dynamic/asmjit/LLVM and static-with-JIT iOS variants still abort at the missing
API. macOS all5profiles retain64execute-mode protection calls; Linux all5profiles
retain zero calls. macOS protection recording is serial to avoid a host recorder
race; iOS/Linux six-thread groups run concurrently. ASAN+UBSAN/Wall/Wextra/Werror
remain enabled with detect_leaks=0 for the host /proc restriction; intentional
negative aborts disable core dumps. Existing runtime/JIT/cache/import checks stay.

Workflow intake-host adds this new regression;34synchronization jobs and35total
host dependencies remain. Metadata/Info.plist version117, README and both
independent handoffs updated. Run exact clean pinned intake-host/core-preparation
commands and all53patches before publishing. Actual iOS compile/link and the
completed device execution window remain pending the workflow/phone.

Next: install Build117 ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, reopen and
Run all120tests. Reuse firmware/disc if present, then Run game (3 seconds) and
keep app open through automatic stop. Share startup log and matching .ips if
crashed. Do not require another5.67GBimport unless the app reports it missing.
Keep replies concise English, no images. Verify queued once after publishing;
no Actions monitoring beyond that. User reports outcome.

Build117 prepublication validation PASSED in fresh build117-validation clone:
exact YAML intake-host (fixture/intake/runtime/JIT/cache/thread-entry/game-import)
and core Apply iOS core patches steps both exited0 on pinned native source.
All53patches applied;0053 reverse-check and all overlay byte comparisons passed
(README refreshed after documentation edits). Python AST/YAML/plist/version117/
workflow bash syntax and git diff --check passed. Prior52patches, Apple/immutable
JIT headers and production app/runtime/frontend/capture/intake/import/bridge
sources remain unchanged. Unchanged34synchronization profiles remain for Actions.
Phone success and full iOS compile/link are still pending; no monitoring Actions
after the single queued check at publication.


## Build118 — MoltenVK graphics-device foundation (2026-10-15)

Build117 phone SUCCESS: ARMSX3-startup-20261015-094237-913-29981.txt, PID29981.
All120diagnostics passed, cached runtime and actual game-folder load/cleanup
passed, then Midnight Club: Los Angeles [BLUS30442] completed its full3second
native running window. Running1792057351.097407 -> window end1792057354.101032;
joined snapshot1792057354.120176 has20PPUcontexts,6SPUs,51,678completed HLE/LV2calls.
Native exec_bytes/4 aggregate=1,588,286,587 is a backend estimate, not independently
measured instruction throughput/FPS. Five primary SPUs PC4520, secondary PC70136,
block counters0 are normal for static interpretation; DMA/code-sized GET logs
prove SPU work beyond thread creation. Log shows native RSX device memory/context,
GCM event queue, display buffers, render/streamer/audio threads and asset reads.
The syscalls/MFC waits marked aborted after the explicit window-end/Kill request
are stop cancellation, not an app crash. Stop callback completed, fully stopped
with zero liveCPUthreads1792057354.149632, EXECUTION UI PASS1792057354.154463.
No JIT abort or crash report. No rendering/menu/audio/playable FPS claim yet.

Build118 adds Check graphics device separately from the verified guest-run path.
Native RSX still uses NullGSRender; WITH_LLVM=OFF and USE_VULKAN=OFF remain for the
native core. The new MoltenVK library is linked solely into the core frontend's
independent graphics check. No fake game frames or CPU-generated game image.
No Vulkan native renderer source/shader/swapchain/frontend frame is enabled yet.
Next substantive integration after this device check is native VKGSRender plus
UIKit CAMetalLayer GSFrame and swapchain ownership.

New GraphicsDevice.cpp/.h use real Vulkan API:1.1instance with portability
enumeration/flag when available (required onApple), enumerate device/graphics
queue, enable portability_subset when exposed, create device, log physical/API/
driver/maxTexture/storageBuffer/geometry/tessellation/fragmentStores capabilities.
Allocate32x32RGBA8 optimal image plus host-visible readback buffer, prefer coherent
memory but invalidate non-coherent memory correctly. Submit red clear, barrier,
image-to-buffer copy and host-read barrier; wait5second fence; compare all1024RGBA
pixels. Repeat blue with command/fence reset and correct prior layout. This
validates transfer/GPU synchronization/readback; no shader translation, draw,
surface or screen presentation is tested. Destroy resources in dependency order.
No native guest memory is read or mutated.

Resources use one RAII owner and serialized try-lock. Any uncertain submission
failure or unfinished fence wait retains the complete owner until process exit,
marks graphics unusable and returns-2/reopen; do not destroy image/buffer/pool
while the GPU might still use them. Device-lost wait permits normal destruction.
No unbounded vkDeviceWaitIdle is used. Ordinary setup/readback failures return-1
with complete cleanup; another check can run. Concurrent checks reject safely.
GraphicsCheck.cpp C ABI rejects main-thread execution, non-fully-stopped Emu or
liveCPUcontexts; UIKit readiness120/idle gate runs it on the existing serialized
worker flow, stores unfinished-operation marker, restores idle timer and disables
all further actions on-2. Graphics and Run game buttons share a row. Firmware/
game imports are not prerequisites for the graphics check. Existing game flow
unchanged; Runtime/Capture output now labels exec_bytes/4 as an estimate/raw
backend counter instead of claiming an independent instruction count.

Pinned dependency: KhronosGroup/MoltenVK releasev1.4.2 MoltenVK-ios.tar,
SHA256 b5d947b1660e6e9fed40b9cd2387e160aaab9e80b775c0cef7e14059405178c1.
Fetched official release metadata/archive; runtime docs say iOS>=15. Download
contains static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a and include/vulkan.
Verifier parses XCFramework metadata and every Mach-O archive object, requiring
arm64/object kind/device iOS/platform2/minOS<=16, rejecting macOS/simulator. This
release archive is one combined Mach-O object (not a count of source units),
minOS15.0, built with SDK26; full Xcode16.4/iOS16link still belongs to Actions.
fetch-moltenvk.sh checks exact archive digest before extraction. Imported STATIC
CMake target exposes headers only to ARMSX3Core and links required iOS Metal/
Foundation/QuartzCore/CoreGraphics/IOSurface/UIKit frameworks. No dynamic external
MVK framework. Package includes upstream LICENSE and runtime guide under
ThirdParty/MoltenVK. build-core.sh now takes third arg verified MoltenVK root;
workflow fetches/verifies before native compile and passes all3roots.

New independent graphics-host job installs Vulkan headers, mesa lavapipe and
Khronos validation layer, selects software ICD and runs production GraphicsDevice
AND GraphicsCheck under ASAN+UBSAN/Wall/Wextra/Werror, real Vulkan GPU commands and
synchronization validation enabled via instance pNext. Core idle/main-thread and
injected error return values are explicit host models. Success repeated4cycles,
instance/device/map failure, wrong pixel, device loss, concurrent rejection,
uncertain submit and fence timeout are covered. Exact pixel mismatch fails;
normal failure owners are all destroyed; uncertain work destroys none and blocks
reuse. The timeout fault is injected after waiting for the actual software GPU,
so the host test itself leaves no active GPU work. The submit fault skips actual
queueing but tests conservative retention. No validation VUID/errors permitted.
Linux results prove Vulkan command use, not Apple driver/Metal/ISA or device iOS.

Local host environment initially lacked Vulkan headers/ICD: downloaded Ubuntu24
packages into scratch only, extracted headers/lavapipe/validation libraries,
pointed private ICD/layer JSON paths at those extracted libraries. Actual software
GPU reports llvmpipe LLVM20.1.2/Vulkan1.4. Production positive readback and all
failure scenarios passed with Khronos synchronization validation. No stubbed GPU.
Pinned MoltenVK fetch/check/extraction script also passed locally against exact
34.5MBarchive. Existing runtime/intake/JIT/SPU/import/120fixtures stay in their
host gate;34synchronization profiles unchanged. Total host prerequisites36 now:
34sync +intake-host +graphics-host. All53production patches remain unchanged.
Info.plist/metadata fixtures/README and both independent handoffs nowBuild118.
Run exact clean intake-host/core-preparation and graphics checks before publishing.

Next phone step: install Build118 ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore
once workflow succeeds. Reopen, Run all120tests, tap Check graphics device,
share startup log. No firmware/game reimport is needed for this check. Optional
Run game3seconds regression can reuse existing firmware/disc. If graphics/core
load crashes share unfinished startup log and matching.ips. No game picture yet;
this is the real driver foundation for native renderer integration. Keep replies
concise English, no generated images. Verify workflow queued once after publishing,
then no Actions monitoring; user reports success/failure.

Build118 final prepublication validation PASSED: exact clean YAML intake-host
and all53patch core-preparation commands exited0; final overlay byte comparisons
passed after docs/packaging edits. Nine production graphics scenarios passed with
real lavapipe/Khronos synchronization validation and ASAN+UBSAN. Correct full64
CPU-count ABI is used and a high32bit-live count is rejected in the host wrapper
check. Native Runtime/Capture differ only in counter log labels. All53patches/
CoreBridge/intake/import/frontend/dispatch/JIT headers remain unchanged. Exact
pinned MoltenVK download/digest/extraction/Mach-O verifier passed; Apple branch
compiled against actual Vulkan headers; standalone imported-target CMake3.28
configure/generate passed. Python/YAML/plist118/shell syntax and git diff --check
passed. License files are checked before IPA packaging. Actual Xcode16.4/iOS16
compile/link and phone graphics result remain pending. No Actions monitoring
after the single queued check.


## Build119 — direct MoltenVK instance setup fix (2026-10-15)

Device evidence: ARMSX3-startup-20261015-102235-835-30258.txt, Build118/PID30258.
All120diagnostics passed. The game completed its3second run again with20joined
PPUs/6SPUs,51,171completed HLE/LV2calls and full native cleanup. The aggregate
native exec_bytes/4=1,528,671,915 stays labeled an estimate; not a benchmark.
The following Check graphics device returned ordinary-1 before instance creation:
GRAPHICS BEFORE1792059753.239343 -> MoltenVK portability enumeration is absent
1792059753.243114 -> GRAPHICS UI FAIL1792059753.253068. No app crash, no GPU work,
no owner quarantine. Guest execution remains device-verified on117and118.

Cause is our Apple-only precondition in GraphicsDevice.cpp, not hardware support
or firmware/game data. This app links the MoltenVK static driver directly and does
not use the Vulkan loader. Pinned MoltenVK v1.4.2's actual extension catalog
MoltenVK/MoltenVK/Layers/MVKExtensions.def includes KHR_portability_subset as a
DEVICE extension but does not contain KHR_portability_enumeration. Its runtime
guide explicitly describes the enumeration flag as needed when the Vulkan loader
enumerates MoltenVK. The pinned GPUObjects/MVKInstance.mm constructor validates
only requested/advertised extensions and getPhysicalDevices enumerates directly.
Primary source paths were read at the exact v1.4.2 tag through GitHub; runtime
guide is also in the downloaded, digest-verified package from118.

Build119 removes only that Apple precondition and adds one instance-extension/
flag log. If KHR_portability_enumeration is advertised, still enable the extension
AND VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR. Otherwise request neither
and proceed to vkCreateInstance/direct physical-device enumeration. Device-level
portability_subset enabling is unchanged. All queue/memory/clear/barrier/copy/
fence/readback, resource cleanup and uncertain-work retention are unchanged.
MoltenVKv1.4.2 archive/SHA/headers/frameworks/CMake/package/license scripts are
unchanged. All53native patches,120diagnostics, production guest runtime/capture/
frontend/dispatch/intake/import/bridge and UIKit actions remain unchanged from118.
Bundle version/metadata fixture/README and both independent handoffs now119.

Expanded test_graphics_device.py filters only the loader portability extension
from actual Linux instance-extension enumeration to model the direct-driver list.
GPU commands still execute through real lavapipe and Khronos synchronization
validation; no synthetic GPU/readback backend. vkCreateInstance wrapper asserts
that extension and flag are paired, and direct-list input has flags0. Ten existing/
new standard scenarios cover loader-present/direct-absent success and all prior
failure/concurrency/timeout cases. Production sources are additionally compiled
with __APPLE__=1, passing loader-present AND direct-absent GPU/readback cycles.
A third binary reinstates Build118's exact Apple-only rejection before the same
GPU code: loader-present passes and direct-absent reproduces the same error with
zero created instances/devices. This is a scoped reconstruction of the original
precondition, not an actual Apple driver test.14process scenarios passed with
ASAN+UBSAN/Wall/Wextra/Werror and zero validation VUID/errors. The Apple branch
that escaped118's Linux host tests is now covered. Full iOS compile/phone device
creation/readback remain pending119; no rendering/surface/shader success claimed.

Workflow jobs/36host dependencies unchanged; the existing graphics-host invokes
the expanded regression. Exact clean pinned intake-host and53patch preparation
must pass before publishing. Don't rerun unchanged34synchronization profiles
locally just for this frontend fix. Native VKGSRender remains disabled, so audit
its separate instance-extension setup against direct MoltenVK when enabling it
later; don't assume loader-only setup will work unchanged.

Next phone step: install Build119 ARMSX3_iOS16_INSTALL_THIS_IPA when workflow
succeeds, Run all120tests, then Check graphics device and share startup log.
No firmware/game reimport needed. Optional existing Run game3seconds regression
can reuse retained data. Keep replies concise English, no images, and verify
workflow queued only once after publication; do not monitor Actions afterward.

Build119 prepublication validation PASSED in fresh pinned build119-validation:
exact YAML intake-host and all53patch core-preparation commands both exited0;
all final core/ios overlay byte comparisons passed. Graphics regression14processes
passed with real lavapipe/synchronization validation and ASAN+UBSAN, including
old Apple guard failure and corrected Apple direct-driver success. Source
comparison proves GPU work/cleanup unchanged outside the instance precondition/
log; all guest/native patches/UI/dependency/workflow sources unchanged. Python/
YAML/plist119/shell syntax and git diff --check passed. Build118 already proved
Xcode16.4 static driver linking/core load/iOS16compatibility; first actual Apple
VkInstance/device/readback still awaits119phone test. Do not monitor Actions
after the single queued check at publication.


## Build120 — 2026-10-15: native Vulkan renderer / retained UIKit surface

Latest device evidence: attached ARMSX3-startup-20261015-104445-008-30463.txt,
Build119. All120 diagnostics, native Midnight Club: Los Angeles BLUS30442 DG
load/identity/disc checks and three-second real guest execution/clean teardown
passed. Joined snapshot:20 PPU contexts/six SPUs,49,092 completed HLE/LV2 calls;
exec_bytes/4=1,514,516,280 is a backend estimate, not independent throughput/FPS.
Graphics:18 instance extensions, portability enumeration absent/flags0; Apple A15
GPU, probe API1.1/driver10402; maxTexture2D16384/maxStorageBuffer1474871296,
geometry0/tessellation1/fragmentStores1. Both1024-pixel RGBA8 clear/copy/fence/
readback passes and GRAPHICS UI PASS. Probe API1.1 is the request used by that
check, not proof native renderer's negotiated <=1.2 request is unsupported.

Build120 now enables USE_VULKAN=ON, LLVM remains OFF. Native patch0054 imports
the same verified MoltenVK1.4.2 arm64 iOS archive (no macOS build/submodule fetch),
uses advertised-only Apple loader extension/flag policy in normal/fast instance
creation, passes an already-captured CAMetalLayer directly through the iOS bridge,
and observes actual swapchain_WSI::present return values after vkQueuePresentKHR.
All first53 patches are unchanged;54 total. MoltenVK importer is include_guard
GLOBAL with GLOBAL imported target for sibling3rdparty/loadtest scopes. Digest,
platform/minOS/license checks and full undefined-error/-force_load link stay intact.

New separate UI action: Render game (10 seconds). UIKit creates/retains a modal
RenderController/RenderSurface(CAMetalLayer), with1280x720 drawable letterboxed to
viewport. The C ABI armsx3_core_render_game borrows this layer+fixed dimensions.
RuntimeFrame implements actual GSFrameBase; native GSRender consumes the unique
frame then close() deletes it after the native Vulkan destructor. No RSX UIKit
reads or dispatch_sync/main geometry calls. Finish rejects a live native frame.
On -2 incomplete cleanup the view/layer remains retained AND attached; UI says to
close/reopen and share the previous unfinished log. Normal returns dismiss only
after native GPU/CPU stop and frame release. Pending markers/log sharing retained.

Render mode uses native BootGame/Run(false)/RSX-started RunPPU, original disc and
firmware validation, static PPU/SPU, null audio, MSAA none, async_recompiler/two
shader compiler threads, framegen off and1024MiB native VRAM allocation limit.
15sec startup budget,10sec running window, native Kill(false) and fully-stopped
cleanup/drain/config restoration. The original3sec null video/audio action and
load/device checks remain. Render PASS additionally requires accepted native
VK_SUCCESS/VK_SUBOPTIMAL_KHR presents>0 andzero present errors, plus joined CPU
progress andclean stop. Present acceptance is NOT evidence of meaningful game
pixels/FPS. First accepted native present is explicitly logged. Audio/controls
pending. Full backend compile, Metal surface/device presentation and actual game
content remain unverified until CI/phone. No fabricated game frames or GPU passes.

Validation completed locally:
- Exact workflow intake-host step including fixture/intake/runtime/native JIT/
  SPU cache/SPU entry/game import; ASAN+UBSAN detect_leaks=0.
- Runtime regression now compiles actual GSFrameBase/GSRender constructor/dtor/
  context/exit methods with production RuntimeFrame;64 ownership cycles, pending/
  duplicate/invalid-size/take-once/live-frame guards, counts reset/unarmed cases,
  modeled render success/no-present/device-error/suboptimal, cleanup/config restore.
  Guest/VM/FXO/native Vulkan subclass/queue outcomes are explicit host models.
- New test_native_renderer.py reconstructs exact first53+54 sources, reverse
  checks54; compiles actual native queue-present method + both Apple extension
  selection paths/flag policy with host Vulkan interfaces; hook order/returns;
  actual iOS CMake branch/importer across sibling scopes/repeated includes; UIKit
  lifetime source contracts. Included in existing intake-host job.
- Fresh build120-validation at pinned92b931b: exact workflow core Apply iOS core
  patches step passed, all54 patches/overlays. Original first49 historical validator
  and registry checks retained;34 synchronization + intake + graphics prerequisites.
- Production graphics-device/check regression passed real Vulkan/lavapipe with
  Khronos synchronization validation,14 process cases including direct-driver
  policy and old Build118 guard reproduction. No Apple/Metal claim from Linux.
- Full iOS SDK/toolchain unavailable locally; Actions compiles/links real native
  renderer and app. Build120 device result remains pending.

Repo txntixnz/ARMSX3-for-iOS-16 main; pinned upstream92b931b9fb5eef7f1317cb482917dfc19aceebd9.
Build119 parent74ebbb84e2d89fcb3074def844532207f6b6c60f. Source/tests/plist/docs120.
Publish via Git data API with expected-head lease (CLI push has no token), verify
identical local/remote tree and sync local tracking. One queued Actions check is
permitted; DO NOT monitor afterwards. User will report results. After successful
workflow install ARMSX3_iOS16_INSTALL_THIS_IPA through TrollStore, run120 tests,
tap Render game (10 seconds), keep app open, share log and describe screen. On
crash request unfinished log + matching .ips. Do not claim visible rendering,
performance or playability yet. No images; keep replies concise English.


## Build121 — 2026-10-15: fix native Vulkan settings visibility on iOS

User reported Build120 workflow failure. Actions38724925004 / native job116388791080:
all36 host prerequisites passed. Native archive compilation failed with83 errors,
all missing cfg_root::node_video members from the Android-only frame-generation
block: frame_generation, frame_generation_flow_scale, frame_generation_target_rate,
frame_generation_performance, frame_generation_dll_path. Consumers include native
swapchain.cpp, VKGSRender.cpp, VKPresent.cpp and FrameGen helpers/LosslessDll.cpp.
No IPA or iOS runtime renderer test occurred. Fetch decoded logs via GitHub
fetch_workflow_job_logs(repo_full_name,job_id), not generic fetch of /logs.

Build121 patch0055 changes only rpcs3/Emu/system_config.h: explicitly includes
TargetConditionals.h on Apple, and exposes that exact configuration block on
Android OR (Apple AND TARGET_OS_IOS). ARMSX3_IOS is only a CMake variable for the
native archive, so do not assume it is a native preprocessor definition. Other
Android-only settings (shader preset/audio defaults) and macOS/Linux availability
remain unchanged. Native enum frame_generation_mode is already unconditional.
The production iOS render request still sets frame_generation_mode::off. First54
patches, native Vulkan backend selection, frame adapter, UIKit ownership, actions,
GPU library pin/digest and full-link policy are unchanged.55 patches total.

New tests/test_vulkan_config.py reconstructs pinned config/types/FrameGenConfig
headers through exact first54+55 patches and checks reverse applicability. It
compiles complete actual native cfg_root and enums with explicit host cfg storage
interfaces / TargetConditionals macros. Reinstating Build120's config header
reproduces missing-field compilation; fixed iOS and original Android compile and
run actual native FrameGen helper defaults/mode/flow/target/performance access;
macOS/Linux compile and verify existing field absence. Covers allfive fields
referenced by allsix native consumer files, empty DLL path/defaultoff and adjacent
Android-only shader preset visibility. No full native GPU or serialization claim.
Added to intake-host. test_native_renderer.py now explicitly scopes its historical
patch54 fixture to first54, so additive patch55 cannot shift the target.

Validation: exact workflow intake-host step passes, including actual-header
regression and existing ASAN+UBSAN lifecycle/JIT/SPU/import checks. Fresh
build121-validation at92b931b runs exact core preparation/audits/registries and
all55 patches plus overlays. AST/YAML/plist checks and frozen first54/renderer/
frontend/diagnostic-core verification pass. Local environment has no iOS SDK;
full compile/link and actual native renderer presentation remain pending CI/phone.
34 synchronization profiles and graphics implementation unchanged; all36 host
jobs passed Build120. Do not imply this local config test proves full iOS linking.

The additional attached ARMSX3-startup-20261015-112725-269-30756.txt is explicitly
Build119 again:120 diagnostics, imported-game checks/three-second execution,
50,516 joined completed HLE/LV2 calls,20PPU/sixSPUs, clean stop and both A15 graphics
readbacks passed. It has no RENDER action and is no evidence of Build120 rendering.
User was directed to the new Render game (10 seconds) action once an IPA builds.

Repo main parentdd6bc81d9cb11193e7cf5de98c371ef82220eca3 (Build120), parent tree
1e4ce2316cbd130406c6c10d0d1d48d18f8ef573. Build121 metadata/plist/docs updated.
Publish with Git data API expected-head lease, verify tree, sync local branch.
One queued check permitted; do not monitor new Actions run after publication.
After successful CI install ARMSX3_iOS16_INSTALL_THIS_IPA, run120 tests, tap Render
game (10 seconds), keep app open and share log + what appeared. No images and
concise English replies. Audio/controls pending; meaningful pixels/FPS unverified.


## Build122 — 2026-10-15: correct non-Android frame-generation fallback ABI

User reported Build121 failed. Actions38728549593 / native job116400862689:
all36 host jobs passed; the full rpcs3_emu archive INCLUDING native Vulkan built,
and verify-archive passed522 arm64 iPhoneOS objects/minOS<=16.0. Production Runtime,
RuntimeFrontend, RuntimeFrame and ObjC++ App.mm all compiled. Final ARMSX3Core dylib
link failed on exactly one unresolved symbol: vk::frame_gen::capture_presented_frame
with command_buffer/render_device/VkImage/VkImageLayout/four u32 arguments, called
by VKPresent.cpp. Its public header and actual caller have8 arguments; upstream's
non-Android fallback definition still had6. No IPA and no new phone renderer result.

Patch0056 changes only that existing native fallback signature from6 to8 args.
It continues returning false off Android, as the native header explicitly promises;
no fabricated renderer implementation or ignored undefined symbol was added.
Native Android frame-generation implementation is byte-for-byte unchanged. The
first55 patches, cfg visibility fix0055, native Vulkan backend, GPU library pin,
UIKit layer ownership, Runtime render configuration/action and full undefined-error
link policy are unchanged.56 patches total. iOS frame generation remains off.

New tests/test_framegen_link.py reconstructs pinned native VKFrameGen.cpp/.h and
VKPresent.cpp through exact first55+56; reverse checks56 and proves only the fallback
arity changes. It compiles the FULL native non-Android VKFrameGen.cpp and unchanged
public header against REAL Vulkan ABI headers. Only unused config/RSX/timer include
seams and empty command/device interfaces are modeled. Separate caller TU retains
the EXACT native VKPresent capture call, including its four dimensions, and exercises
all public fallback APIs/shared_image operations. Old code compiles but fails linking
on the exact eight-argument symbol; corrected iOS/macOS/Linux profiles compile/link/
execute under ASAN+UBSAN, returning disabled/empty as promised. No GPU work in this
ABI test. Graphics-host now checks out the pinned native source and runs it after
the existing real Vulkan regression; job count/prerequisite graph stays34+2.
The test fixture scopes itself to first56; config regression now scopes to first55.

Local validation: exact workflow intake-host step passes; fresh build122-validation
executes exact core preparation, frozen historical first49/registries, all56 patches
and overlays. Native framegen link regression passes, actual config regression
retained. Production graphics-device/check still passes14 real lavapipe/validation
process cases. AST/YAML/plist/source freeze checks pass. No local iOS SDK; the FINAL
full iOS dylib/app link, packaging and phone Metal presentation remain pending.
Build121 proves real native archive and new frontend/app compilation; do not keep
claiming native iOS compile is wholly untested, and do not claim final link passed.

Repo main parent06c5a296d1948999e1efd85bad22b0bd5f866ea6 (Build121), parent tree
14808b7e4ad274f04733c361c5a3ed59fd08bd85. Build122 plist/fixture/README updated;
both independent handoffs appended. Publish via Git data API expected-head lease,
verify identical tree, sync local branch. One queued run check allowed; DO NOT
monitor after publication. User reports completion/failure. Once IPA builds:
install ARMSX3_iOS16_INSTALL_THIS_IPA in TrollStore, run120 tests, then Render game
(10 seconds), keep app foreground, share log and screen result. Retained firmware/
disc should be reused. Audio/controls pending, meaningful game pixels/FPS unverified.
Keep replies concise English and do not create images.


## Build123 — 2026-10-15: link CoreGraphics into the app executable

User reported Build122 failure. Actions38731608703 / native job116411215237:
all36 host prerequisites passed, real native Vulkan archive built/verified, and
libARMSX3Core.dylib FINALLY linked successfully. App.mm and all frontend/runtime
objects compiled. The separate ARMSX3CoreLoadTest executable then failed linking
only CGRectGetMaxY/CGRectGetMidX/CGRectGetMidY from RenderController geometry.
CoreGraphics was already linked into the core dylib but omitted from the separate
app target. The app deliberately dlopens the core, so it does not inherit those
private link dependencies. No IPA or phone renderer validation occurred.

Build123 adds exactly "-framework CoreGraphics" to the app's explicit CMake
framework list: UIKit/Foundation/UniformTypeIdentifiers/QuartzCore/Metal/CoreGraphics.
All56 native patches, renderer source, C ABI, UIKit layer ownership, configuration,
Vulkan library pin and strict core link are unchanged. No new patch or dummy
implementation; frame generation remains off. Metadata/fixture/README now123.

Local verification: existing full120-stage fixture/intake/UI/runtime contract
passes; actual app target_link_libraries command extracted into temporary CMake
project configures and generates all6 frameworks INCLUDING CoreGraphics in its
link command. Native source/all56 patches and packaging/workflow are frozen;
AST/plist/YAML/diff checks pass. Audited UIKit/Metal/QuartzCore/UTType/CoreGraphics
uses against direct app frameworks, plus existing copy/license/platform/dependency/
symbol/signing/bundle/IPA packaging sequence. Did not repeat native tests or all56
patch preparation: none of their source/patches/workflow changed and all36 host
jobs plus the native core full link passed Build122. No local iOS SDK; app's final
iOS link, packaging/signing and phone Metal presentation remain pending CI/device.
No new repository test for this one-framework build dependency change.

Repo main parentd1dbcfc0cf94ce3aaa809f6c172c819a2337854b (Build122), parent tree
8954b4ab86c2b4d582951b60439e6e2e1fa2a458. Both independent handoffs appended.
Publish through Git data API expected-head lease, verify tree, sync local branch.
One queued Actions check allowed; no monitoring afterwards. User will report.
Once IPA succeeds, install ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, run120
tests, tap Render game (10 seconds), keep foreground and share log/screen result.
Reuse retained firmware/disc. Audio/controls pending and game content/FPS unverified.
Keep concise English; do not create images. Build122 proved full native core link;
do not describe that as still wholly untested or claim app link/packaging passed.


## Build124 — 2026-10-15: renderer selection and optional diagnostics

Build123 Actions38735031485 succeeded. Latest phone log
ARMSX3-startup-20261015-124837-170-31316.txt confirms120 diagnostic passes,
Midnight Club LA imported-game execution with51114 completed HLE/LV2 calls and
clean stop, plus two exact A15 offscreen GPU readbacks. Render game failed its
configuration check: native System.cpp fixup_settings changes Vulkan to Null
in headless mode. CoreBridge initialization deliberately sets headless=true and
only supports Null. That initialization baseline and all56 patches remain frozen.

Runtime.cpp now selects headless=false and supports Null+Vulkan for the explicitly
owned render surface before BootGame. Load-only and nonrender execution remain
headless/Null. Default stays Null. Original headless flag, supported renderer set
and default renderer are restored only after successful teardown/frame release.
Incomplete cleanup retains ownership/policy and requires app restart as before.
Native renderer/config validation and accepted-present/error checks are retained.

Quick start runs the actual first4 stages: core load, immutable JIT, Emu.Init,
guest memory. A separate foundationReady flag enables firmware/game/graphics/
render actions. The120-stage cursor is never fabricated or marked complete;
Run remaining tests resumes the116 remaining stages. Failure and serial work
gates remain. No diagnostic starts automatically. Firmware/disc retained.

Validation: Build124 fixture/prior bridge freeze passes; runtime/frontend/JIT/
BootGame host regression passes ASAN+UBSAN including exact native System.h policy
accessors and System.cpp video fixup, render success/no-present/error/suboptimal,
partial loading, stopped restoration and incomplete cleanup. Renderer regression
compiled/executed native present/extension contract but its unchanged CMake
importer check could not run locally because cmake is absent. Native renderer/
all56 patches unchanged; Build123 full native compile/link/package succeeded.
No local iOS SDK; new UIKit compilation and actual phone pixels pending CI/device.

Parent6140317d925c13e26cbd8315c77b7a658a03a88a. Publish main, let Actions build;
DO NOT monitor after publication (user reports finish/failure). Next: install
ARMSX3_iOS16_INSTALL_THIS_IPA in TrollStore, Quick start -> Render game (10 seconds),
keep foreground, share startup log and what appeared. Audio/controls pending.
No generated images; concise English replies.


## Build125 — 2026-10-15: persistent game session and Stop game

Build124 d21a65e238298cf5203179192ac14168419f12e7 booted on phone. User log
ARMSX3-startup-20261015-151935-919-32293.txt: Quick start4 passes; real native
Vulkan318 accepted presentations,221364 completed HLE/LV2 calls, clean GPU/CPU
teardown. User clip RPReplay_Final1792077966.mp4 visibly shows Midnight Club LA
startup/licensing screens progressing; no main menu yet. Its return to app is
the programmed10-second stop, not a demonstrated crash. Do not report318 unique
game frames/FPS or successful gameplay. SPU block counter0 is merely that counter.

Build125 changes the main rendering action to Start game, using a new exported
armsx3_core_render_session C ABI with an off-main stop predicate/context. UIKit
sets only an atomic flag when Stop game is tapped or the app resigns active.
The worker polls after loading/during native startup/while running; it retains
all existing Kill/main-queue drain/CPU joins/frame lifetime/config and renderer
policy restoration. Stop while loading waits for native load to return before
cleanup. Session has no10-second deadline; the old bounded render_game export
remains as a diagnostic API. Three-second execution checks unchanged.
A stop before execution is a cancellation with clean teardown, not a false
zero-counter failure. No-present and Vulkan errors still fail after a real run.
Incomplete teardown still returns-2, retains the Metal layer/view and requires
process restart. No overlapping UI actions; all120 diagnostics remain optional.
Heartbeat every5 seconds during continuous session. UI shows Stop game and
reserves its bottom row. Uses existing UIKit/CoreGraphics/stdlib dependencies.

Validation: production runtime/frontend + actual native BootGame/policy/Run/
GSRender contracts pass ASAN+UBSAN. Added threaded atomic cancellation after
120ms while the old render diagnostic deadline is40ms in host tests, four
repeated success/no-present/error/success runs, pre-start and startup cancellation,
existing bounded startup/run/cleanup/error/timeout and64 adapter lifetimes pass.
Build125 fixture validates frozen diagnostic bridge,4-stage Quick start/readiness,
continuous C ABI/UI wiring and optional full120 cursor. Python AST/plist and
git diff checks pass. All56 native patches/renderer implementation unchanged.
No local iOS SDK; new UIKit build and longer device session pending CI/phone.

User explicitly authorized publishing this project to main and starting Actions.
Use GitHub tools (shell git push has no credentials). Parent mainBuild124
d21a65e238298cf5203179192ac14168419f12e7. Publish with expected-head lease;
one queued check only, do not monitor. Next user installs
ARMSX3_iOS16_INSTALL_THIS_IPA via TrollStore, Quick start -> Start game; keep
foreground, allow startup to progress, then Stop game and share log/screen result.
Firmware/disc persist. Audio/gamepad controls still pending. Concise English,
no generated images; extracted video frames used only for internal inspection.


## Build126 — 2026-10-15: iOS protected-page signal recovery

User reports Build125 did not reach the main menu. Attached
ARMSX3-startup-20261015-155642-086-32731.txt exports the previous unfinished
PID32705 session: boot/request around1792079628, native threads progress through
shader compilation and game disk-cache creation. At1792079690.44, two SPUs, the
MC Render PPU and RSX all fault reading guest addresses0x40300400/440/480/410
(host0x340300400 etc, all in one page). Upstream labels SIGBUS/BUS_ADRALN as
misaligned without logging ESR. Native writer_lock then waits on the dead Render
PPU, heartbeats continue; Stop at1792079763 reaches incomplete cleanup/-2 after
30s waiting on SPU3. No main-menu or successful long shutdown evidence.

Confirmed code bug: native signal_handler unconditionally excludes SIGBUS from
handle_access_violation. Darwin sends SIGBUS for KERN_PROTECTION_FAILURE, and
ARM unix_signal.c assigns BUS_ADRALN to every SIGBUS. Thus this log label alone
does NOT establish alignment. Sources inspected: Apple xnu
bsd/uxkern/ux_exception.c, bsd/dev/arm/unix_signal.c; CPU syndrome constants
confirmed against Linux arch/arm64/include/asm/esr.h. Recovery of GPU-protected
guest pages is the strong working explanation; exact fault ESR was absent, so
do NOT claim the phone root cause or menu fix already proven.

New patch0057 applies after frozen first56 to Utilities/Thread.cpp and actual
AArch64Signal.h/.cpp. Adds hardware decoder for DATA ABORT EC0x24/25 plus
permission FSC0x0c..0x0f. Only on Apple ARM64 TARGET_OS_IOS may SIGBUS with that
classification reach existing guest/metadata VM/RSX recovery. Normal SIGSEGV and
Linux/Android/macOS SIGBUS behavior unchanged. Alignment0x21, translation, backing/
external errors, instruction faults and outside addresses are not newly retried.
It does NOT blindly unprotect memory or ignore a fatal error; native handler must
accept the page. Fatal iOS reports now include ESR/FAR and remove misleading
misalignment-only wording. Unhandled iOS faults skip the inapplicable macOS
pthread-JIT recovery branch; real JIT allocation/publication behavior untouched.

Validation: new test_ios_signal_recovery.py reconstructs exact first56+57 and
reverse checks57. Compiles real native decoder and actual direction/dispatch
branches against explicit host context/VM/RSX interfaces.8192 EC/FSC/write cases
per iOS/macOS profile; true alignment/invalid/outside faults rejected. Eight real
Linux mprotect read/write faults at the uploaded within-page offsets are routed
through Darwin-shaped SIGBUS/ESR contexts and exact dispatch; model RSX backend
restores page permission, native host accesses retry correctly. ASAN+UBSAN pass.
Pre57 gate fails the same matrix as expected. This is NOT native iOS signal or
full RSX recovery proof. Build126 fixture/frozen bridge/Quick start/session checks
pass. Exact fresh pinned core preparation/audits/registries/all57 patches/overlays
pass (registry retry used CI ASAN_OPTIONS=detect_leaks=0 after host LeakSanitizer
ptrace restriction). Python syntax/plist/diff checks pass.

Workflow adds new regression to existing intake-host;34+2 jobs unchanged.
Runtime/session/UI/renderer/decoders/configuration remain Build125. No new device
diagnostic stages; Quick start remains four. Native iOS compile and full game
load/shutdown with this patch pending CI/phone. Parentmain
a64e4ec181c5a0718f7ce90c973622eacca8f775. User authorized main publication.
Use GitHub tools expected-head lease, one queued check; do not monitor. Next:
install ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start game, keep foreground,
let loading progress, Stop game and send log/screen result. Audio/pad pending.
Do not generate images; concise English replies.


## Build127 — 2026-10-15: fix FAR macro collision in fatal diagnostics

User reported Build126 workflow failed. Actions38766320420, native
job116530985028 failed at Compile emulator core archive. All36 host jobs passed
(including new iOS signal regression and actual Vulkan host work). Native ninja
-k0 compiled remaining sources including AArch64Signal.cpp. The only compiler
error was Utilities/Thread.cpp:3719 expected unqualified-id at the new fatal
log expression darwin_context->es.FAR. Its header also warned that u64 FAR;
declares nothing: a dependency compatibility macro expands FAR to empty in
this translation unit. No Build126 IPA or new on-phone fault result exists.

New patch0058 changes the existing Darwin modeled exception-state field name
FAR -> fault_address and updates the one diagnostic member access. Keeps the
field as u64 at offset0, ESR u32 at8, exception_id u32 at12, total16 bytes.
Protects the native context layout when headers define FAR. No undefined-symbol
workaround or global macro undef; patch0057 recovery policy/CPU decoder and all
Runtime/frontend/render/session/UI behavior unchanged. Total58 patches.

Extended test_ios_signal_recovery.py reconstructs exact first56+57+58 and checks
both reverse applications/roundtrip. Defines the actual colliding FAR macro
condition before native AArch64Signal header; static asserts16-byte state and
ESR offset8. Compiles exact new native fatal-detail block against an explicit
fmt interface, asserts captured ESR/FAR values, and proves pre58 header/member
access fails compilation with the observed expected-unqualified-id diagnostic.
All prior8192 EC/FSC/write combinations per iOS/macOS profile and real host mmap
fault/retry tests still pass ASAN+UBSAN; old native SIGBUS gate still fails as
expected. These remain host context/VM/RSX models, NOT native iOS signal proof.
Build127 fixture/prior bridge/Quick start/session contracts and syntax/plist
checks pass. Patch58 applies to the full prepared first57 worktree; Build126
CI already applied/compiled first57 except the one Thread.cpp logging access.
New complete iOS compile/link/package and main-menu progress still pending.

Parentmain0bcc9f1f7d25ee0945973eeced8e59b14b0a3037. User authorized main
publication; GitHub API with expected-head lease, confirm one queued run only,
do not monitor. When IPA succeeds: Quick start -> Start game, keep foreground,
wait for loading, Stop game, send log and screen result. Retained disc/firmware.
No new diagnostic stages. Audio/gamepad pending. Concise English; no images.


## Build128 — 2026-10-15: renderer-owned iOS translation faults

Build127 compiled and ran. User log ARMSX3-startup-20261015-164852-474-33182.txt
exports PID33168: native run starts1792082822.23, shaders/cache/workers progress,
then RSX fails1792082886.40 reading host0x340300400/guest0x40300400 with
ESR0x92000007. GCM interrupt PPU then faults writing0x40300470, ESR0x92000047.
These are data-abort translation FSC7, not permission FSC0xc..0xf or alignment.
Stop at1792082897 ends in30s cleanup timeout due two SPUs waiting on dead PPU.
Main menu remains unconfirmed; previous permission-only fix missed this class.

The actual native sys_rsx_context_allocate allocates3MiB at0x40100000 and sets
reports=base+2MiB=0x40300000. Native ZCULL report locks use real host page_size
and page_start. With16KiB host pages, report at0x40301400 shares protection with
semaphore/control accesses0x40300400 etc. Native on_access_violation can restore
the whole page, but prior SIGBUS/FSC7 gate never called it.

Patch0059 after frozen58 adds is_data_translation_fault for EC0x24/25 and
FSC0x04..07. Only iOS ARM64 SIGBUS data translation faults in an allocated guest
page may enter the native access handler with new optional rsx_only=true. That
retains SPU unsavable scope/temporary VM unlock/CPU state handling and requires
actual native RSX callback acceptance. If declined, returns false BEFORE generic
logical-permission retries, preventing a logically-readable but unbacked mapping
from becoming an endless loop. Normal callers defaultfalse and all previous
permission/SIGSEGV/platform behavior remains. No arbitrary page unprotection,
new allocations, fault-PC skips, changed texture data or guessed shader fix.

Regression now reconstructs exact59 patches and roundtrip reverses57/58/59 to
frozen56. Compiles exact ESR decoder, signal direction/dispatch, native access
handler prefix including SPU state scope, native utils::page_start and actual
ZCULL on_report_enqueued/completed/disable_optimizations/on_access_violation.
Host interfaces model CPU state/locks, VM flags, fmt, GPU and platform context;
native ZCULL methods perform real mmap/mprotect with16KiB report protection.
Sixteen real host read/write faults at the uploaded offsets, active/stale report
blocks, FSC7/F plus direction variants recover and preserve bytes. ASAN+UBSAN
pass. Exhaustive8192 EC/FSC/write combinations per iOS/macOS profile pass;
unallocated/unowned translation faults and true alignment/external/execute/
outside faults remain unhandled. Generic logical fallback is deliberately made
able to retry in a negative guard case; rsx_only blocks it. Exact old Build127
permission-only gate fails the new matrix; pre57 gate and FAR macro regression
checks retained. New behavior still needs actual iOS signals/GPU concurrency test.

All59 patches apply on full prepared native worktree and native diff check passes.
Build128 fixture/frozen bridge/Quick start/session gates and AST/plist checks pass.
Runtime/frontend/UI/3second diagnostic/session/renderer config remain Build125.
No new phone diagnostic stages or user setup. Same workflow34+2 host jobs.
Complete iOS compile/link/package and device main-menu/shutdown test pending.
Parentmain a52dba6f013a7bfeb16ff1aa9b031a8049b85807. User authorized main
publication. Publish via GitHub API lease; confirm one queued run, do not monitor.
Next: install ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start game, keep
foreground, let loading progress, Stop game and send log/result. Disc/firmware
persist. Audio/gamepad pending. Concise English; no generated images.


## Build129 — eager iOS report policy and fatal-worker result reporting (2026-10-15)

User reports “Same I think” with Build128 PID33377 log at
/workspace/scratch/8dcd4680dd95/upload/ARMSX3-startup-20261015-171753-725-33377.txt.
The game still has not reached its main menu. Native Run reaches running at
1792084570.626297; RSX and SPU4 die around1792084659.4 while reading guest
0x40300400 / host0x340300400, ESR0x92000007. At Stop1792084662.969207, the PPU
Render Thread finally logs ZCULL optimization disabling. Cleanup completes at
1792084663.145533, zero live CPU threads. The old UI falsely reports PASS based
on earlier2679 presents and2,285,355 calls despite both fatal worker deaths.

Native source exposes a race consistent with this timing: ZCULL's first guest
fault sets m_pages_accessed=true, releases its pages mutex and waits for an RSX
pause before unprotecting. Other RSX/SPU faults then immediately decline because
m_pages_accessed is already true, although the shared host page is inaccessible.
The Build128 host test modeled locks/eng_lock as no-ops and missed concurrency.

Patch0060-ios-urgent-zcull-reports.patch enables both report locations' existing
urgent mode in the iOS ZCULL constructor, before any report can be queued. Reports
and real occlusion queries/results remain active; native enqueue/completion
balance m_critical_reports_in_flight. This prevents ZCULL from protecting report
pages and avoids fault-driven recovery on16KiB pages shared with RSX controls.
Other platforms retain their prior constructor and fault-based policy. This is a
conservative iOS compatibility policy with a possible performance cost. It does
not disable queries, fake results, skip faulting instructions or widen generic
translation retries. Existing patches0057-0059 remain unchanged for other faults.
The app logs “iOS: urgent ZCULL reports enabled without report-page protection.”

RuntimeFrontend now installs one process-lifetime native fatal-log observer. Its
atomic core-failure flag resets only when the next idle session installs its
frontend. Load/run loops and the final result after cleanup check this flag, so
native fatal errors cause FAIL and automatic teardown. A fatal with completed
cleanup returns -1, releases the frame/configuration and permits retry; incomplete
cleanup still returns -2. Ordinary guest error logs remain nonfatal. Frozen
CoreBridge.cpp and120 diagnostic stages are untouched.

Validation completed locally:
- All60 patches apply in order on a clean pinned92b931b9f native worktree; source
  whitespace check recognizes the original CRLF in RSXZCULL.cpp (per-command
  core.whitespace=cr-at-eol, no repository configuration changes).
- New test_ios_zcull_reports.py compiles exact native constructor/destructor and
  report-page methods with real atomics/host locks/mprotect under ASAN+UBSAN.
  Before0060, a held guest pause request reproduces concurrent RSX/SPU rejection
  while the page remains protected. Patched iOS completes4000 report enqueue/
  completions with concurrent PPU/SPU/RSX accesses on real aligned16KiB main/local
  mappings, zero protection calls/engine pauses and balanced critical counts.
  Patched desktop retains the original policy/race. GPU/pause/query-pool/VM are
  explicit host interfaces; no actual iOS signals or Vulkan queries are executed.
- Existing signal recovery matrix,16 real fault retries and negative regressions
  pass; this test intentionally covers unchanged patches0057-0059 separately.
- Production runtime/frontend host harness passes with fatal injections during
  load, from a worker during execution, and during teardown despite prior progress
  and presents; normal errors do not fail, clean release and fresh retry pass.
- Build129 fixture/frozen bridge/Quick start/session contracts, Python AST, plist
  and staged non-patch whitespace checks pass. Workflow adds the new ZCULL test
  to the existing intake job, retaining34+2 host prerequisites.

Complete iOS compile/link/package and actual device main-menu/performance behavior
remain unverified. Parent main b7b37d50250ecd98daaf35bf50f4427ce19b8e35. User has
explicitly authorized publication and builds. Publish via GitHub API with expected
parent lease; inspect only one queued run, then do not monitor it. User reports
workflow outcome. Next: install ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start
game, keep foreground, let loading progress, Stop game and send the log/result.
Firmware/disc persist; no reimport or full diagnostics required. Audio/gamepad
remain pending. Concise English; no generated images.


## Build130 — iOS streaming-buffer growth and responsive teardown (2026-10-15)

User reports unchanged loading screen and whole-app hangs twice, requiring app
switcher termination. Uploaded ARMSX3-startup-20261015-175355-405-33871.txt is a
recovered previous unfinished Build129 run, PID33843 (exporting process33871).
Local copy /workspace/scratch/8dcd4680dd95/upload/ARMSX3-startup-20261015-175355-405-33871.txt;
Library ID libfile_ce393337eea08191b45f3e5dd005bef8. Read local attachment directly.

The failure has changed. Urgent ZCULL mode logs at1792086577.236595 and there are
no report-page Bus errors. Run reaches running at1792086578.041943. At
1792086637.284613, allocator refuses196608K (192MiB), system pool1 holds274MiB,
configured cap1024MiB. The preceding warnings say recovery is uninterruptible
and the texture cache cannot release temporary resources from within itself.
RSX terminates with VK_ERROR_OUT_OF_DEVICE_MEMORY at memory.cpp:400. New fatal
observer correctly detects this and automatically starts Kill(false) at
1792086637.301183. All CPU contexts join/capture, but final cleanup stalls;
30-second watchdog logs1792086667.307976. No final UI FAIL appears because final
core destruction is queued onto UIKit's main thread and blocks that queue.
No main menu or clean shutdown success should be claimed.

Patch0061-ios-vulkan-ring-growth.patch changes iOS data_heap::grow only. Native
old policy aligns old_capacity+request to64MiB. A64MiB upload+8 bytes (native
VKTexture.cpp padding) on a64MiB ring therefore asks for192MiB. Replacement
buffers start empty and old buffers stay in GC for in-flight references, so iOS
now chooses max(old_capacity+16MiB, request+4096), aligned to16MiB. That boundary
fits80MiB. Native ring allocation/wrapping, GC disposal, growth interrupts and
budget checks remain in use. Requests at/above capacity limit refuse before
mutating the ring. Named iOS growth warnings now precede allocation, and runtime
heartbeats include accepted Vulkan presents. The uploaded allocator log does
NOT identify which heap/request produced192MiB: the padding case is a native
reproducer and plausible contributor, not confirmed device call-site evidence.
The next device log can distinguish this via the new heap-name/request markers.

Patch0062-ios-worker-core-destruction.patch moves CPU cleanup, LV2 cleanup, FXO
reset (including Vulkan/compiler destruction) and VM close to the existing join
worker after native joins, stopped-context capture and semi-destructors. iOS
stage markers bracket CPU/FXO/VM operations. Final state/JIT/watchdog/on_stop
callbacks still complete on main. Desktop retains its original main-thread
cleanup. RuntimeFrame closes via atomics/C++ ownership, with no UIKit work.
If a GPU destructor remains blocked, runtime can return -2 after30s and UIKit
can display incomplete cleanup; view/layer/config remain retained and restarting
requires process exit as before. This improves failure responsiveness; it does
not assert that driver destruction itself will always finish.

Validation completed:
- All62 patches apply sequentially on clean pinned92b931b9f native worktree;
  applied files match expected; CRLF-aware source whitespace check passes.
- New test_ios_graphics_memory.py applies exact first60, applies/reverses61/62,
  compiles actual native ring helper/grow/budget code and shutdown fragments
  under ASAN+UBSAN. Controlled driver limit128MiB reproduces old192MiB failure;
  iOS allocates80MiB, wraps within bounds, keeps old in-flight buffer ownership
  and sends growth interrupt. Small/large/aligned/fixed-limit/budget refusal
  cases pass. Desktop growth stays unchanged. VM/GPU/GC are host interfaces.
- Shutdown test blocks actual extracted FXO reset call on a worker while main
  processes modeled events. VM close/final callback happen only after release;
  cleanup occurs exactly once; desktop destruction stays on main. This models
  the event queue and FXO objects, not actual UIKit/Metal driver waits.
- Production runtime/frontend host harness passes, including fatal observations,
  threaded stop, timeout ownership/config retention and clean retries. This
  harness's older native lifecycle fixture remains intentionally frozen at51;
  the new shutdown fragment test covers62 separately.
- Build130 fixture preserves frozen bridge,120 stages/four quick foundations,
  session ABI and34+2 host prerequisites. Python AST/plist and non-patch staged
  whitespace checks pass. Workflow runs the new graphics-memory test in intake.
- Existing ZCULL regression now explicitly selects patches<=60 so later patches
  cannot break its fixed historical policy reconstruction. No report-page or
  signal dispatch policy changes this iteration.

Actual iOS compile/link/package, loading/main menu, memory use and clean Stop
still require workflow/device verification. A smaller allocation can still be
refused by the real driver; no fixed promise of boot progress. Parent main
f871259928af2003a263ad5d631b987a2d88632a. User authorizes main publication and
builds. Publish via GitHub API lease and inspect one queued run only; do not
monitor builds. Next: install ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start
game, keep foreground, Stop game, send log/result. Firmware/disc persist. No
reimport/full diagnostics. Concise English; no generated images; audio/input
pending. Scratch native130-validation has all62 patches; native129-validation
also now contains these current changes (its directory name is historical).


## Build131 — completed upload reuse and correct ring/fence accounting (2026-10-15)

User supplied ARMSX3-startup-20261015-183748-236-34201.txt and then asked to
continue. Local attachment at /workspace/scratch/8dcd4680dd95/upload/ARMSX3-startup-20261015-183748-236-34201.txt;
Library ID libfile_70a161bf5c6c81918536473c1e996a4b. Read local copy directly.
Recovered previous unfinished Build130 run is PID34187, export process34201.

At running1792089360.581512, accepted presents38. They progress to1662 at
1792089415.650123. Texture upload buffer then grows64->80MiB at1792089417.746798
(request64KiB),80->96MiB at1792089417.820559 (request1024KiB),96->112MiB at
1792089417.859684 (request256KiB). Refusal of112MiB kills RSX at1792089418.054669.
Thus Build130's earlier hypothesized64MiB+padding request is NOT the observed
cause: the real workload consists of small uploads and missing reuse. Fatal
observer starts teardown; this time SPU0 cannot join, so capture/FXO stage markers
are never reached. Runtime times out30s later and RENDER UI FAIL is logged at
1792089448.095490. UIKit is responsive enough to report incomplete cleanup;
clean Stop and main menu are still not confirmed. Do not attribute this run's
blocked join to FXO destruction: the log identifies an earlier stuck SPU join.

Found three concrete native issues/changes, combined in this iteration:
1. Patch0063-ring-put-after-growth.patch recomputes the aligned write position
   AFTER grow() can reset the ring to zero. The original cached pre-growth PUT
   skipped64MiB in a fresh80MiB replacement for a4KiB request, wasting most of the
   new buffer and causing another resize after only16MiB. Normal allocation and
   fixed-size static allocation semantics remain native. This common correctness
   fix is portable, not an iOS-only preprocessor workaround.
2. Patch0064-vulkan-wait-ring-retirement.patch makes successful blocking fence
   waits restore/clear the existing command-buffer heap snapshot like poke().
   Previously only polling reclaimed ring memory. Timeout/device error now leaves
   fence, snapshot, event and pending state intact. reset() checks the wait result
   before resetting a command buffer, preventing reuse after an unsuccessful wait.
   Native monotonic snapshot IDs still prevent older completion from rolling GET
   back. These are portable correctness fixes in the native completion primitive.
3. Patch0065-ios-texture-upload-batches.patch adds pending_bytes() and an iOS
   renderer method which submits and waits for a command buffer once upload space
   held reaches32MiB. It uses native flush_command_queue and snapshot retirement;
   it never resets ring pointers by hand. Calls precede sampler/cache locks in
   load_texture_env and precede the GPU scope/cache entry in scaled-image blits.
   Uninterruptible, flushing/deadlock, missing heap and below-threshold cases skip
   submission. This lets loads reclaim space without a present. Other platforms
   have no added batching policy. New marker: “iOS: completed texture upload batch
   (...K); pending ...K.” Waits are bounded by native FRAME_PRESENT_TIMEOUT.

The extra synchronization may slow texture-heavy loads. Large single uploads,
other GPU allocations and actual MoltenVK behavior remain device concerns; no
promise of main-menu or clean-stop success. No allocation-limit increase, shader
result substitutions, discarded uploads, new diagnostic stages or intake changes.
Previous report-page compatibility mode and responsive-timeout ownership remain.

Validation completed locally:
- All65 patches apply sequentially on clean pinned92b931b9f source; affected
  source matches prepared files and CRLF-aware whitespace check passes.
- New test_ios_upload_retirement.py reconstructs exact first62 then applies and
  reverses63-65. It compiles exact native common ring helper, atomic queue mask,
  command-buffer chunk (tag/poke/wait/reset), snapshot manager and renderer batch
  method under ASAN+UBSAN. Queue/fence/driver are explicit host interfaces.
- Fresh replacement begins at0 and serves another64MiB without growing again.
  Timeout/device error preserve pending ownership; reset refuses failed waits;
  success releases exactly once; older completion cannot roll GET backwards;
  polling and blocking retirement agree. A held simulated GPU wait proves no ring
  space is reclaimed before completion. Busy/missing/below-threshold gates pass.
- Simulated5GiB stream of256KiB uploads with no presents uses one64MiB buffer,
  with byte markers checked before completion/reuse. Desktop policy is unchanged.
  Native Vulkan/Metal command execution is not simulated by a real driver here.
- Negative historical native PUT code fails the fresh-buffer assertion; old wait
  fails timeout-ownership checks and exhausts the modeled buffer on the same
  successful-upload stream. Tests require the expected assertion/error text.
- Earlier graphics-memory/shutdown regression passes. It now reads the common
  helper from git pin explicitly so its historical first62 fixture cannot drift
  when a patched input checkout is supplied. Frozen bridge/120 stages/four Quick
  start foundations/session ABI/Build131 plist and Python AST checks pass.
- Workflow adds the new retirement regression to intake, retaining34+2 host jobs.
  Staged non-patch whitespace check passes. Full iOS build and phone test pending.

Parent main2e8edaca2081693dd623e1019990a2b1a16192ad. User explicitly authorizes
main publication and workflow builds. Publish with GitHub API expected-parent
lease. Check one queued run only; do not monitor. Next: install
ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start game, keep foreground, let
loading progress, Stop game, send result/log. Firmware and game persist; no full
diagnostics/reimport required. Audio/input pending. Concise English, no generated
images. native131-validation contains all65 patches; native130-validation also
now contains these latest changes despite its historical directory name.


## Build132 — verified Build131 menu/Stop; player-one START and menu input (2026-10-15)

User: “Didn’t crash didn’t hang up reached the ‘main main menu’. Couldn’t proceed
further because the game requested me to press START”. Treat this as user-verified
Press START/menu presentation, not proof of gameplay or navigation past START.
Read local attachment directly, no Library lookup:
/workspace/scratch/8dcd4680dd95/upload/ARMSX3-startup-20261015-201829-418-35679.txt
Library ID libfile_285ca60c29d88191a417566200e23958. Build131/PID35679.

Build131 evidence: running1792095415.212071 with40 accepted presents;2134 at
5485.306598. Seven upload batches at5487.936244..5488.666678, each32-36MiB,
pending0K afterward. No ring growth/fatal/OOM. User Stop5502.346595;28PPU+6SPU
contexts joined, execution capture11.5B estimated instructions/1,927,291 HLE
calls; CPU/FXO/VM destruction markers all finish by5506.2933. Native stopped
callback5506.2947, fully stopped zero liveCPU5506.2966. RENDER/UI PASS and2151
accepted presents. Prior rendering/loading/shutdown issue now phone-verified.

Build132 implementation:
- Patch0066-ios-player-one-input.patch adds an iOS-only pad_handler::ios at the
  END of the enum; TargetConditionals guards match in header and formatter.
  Important: ARMSX3_IOS compile definition is only set for the core dylib, not
  rpcs3_emu, so it MUST NOT guard an enum shared by those translation units.
- Native pad_thread overrides its loaded in-memory handler selection to iOS for
  player0, null for other6 ports. Saved profiles are not written. New header
  ios_pad_handler binds a standard Sony054c/0268 pad, reports connected+assign
  changes,16 digital buttons/four centered sticks, PS3/pressure/high-precision
  stick capabilities, no rumble/sensors. It polls one atomic snapshot under
  pad::g_pad_mutex, then uses native copilot publication and cellPadGetData.
- PadInput.h and RuntimeInput.cpp pack digital1/digital2 and LX/LY/RX/RY bytes in
  one lock-free64-bit atomic, with a session enable bit. Disable clears the state;
  CAS writers cannot republish after disable. Fresh sessions start neutral.
- GameInputController.mm owns on-screen arrows, START/SELECT and square,
  triangle,cross,circle buttons. TouchDown/DragEnter hold; UpInside/UpOutside/
  Cancel/DragExit release. Physical iOS GameController extended profile supplies
  all16 buttons and two sticks, Y inverted and0.12 deadzone. Menu (DS4 Options)
  maps START; secondary Options (DS4 Share) maps SELECT. Digital trigger pressure
  is0/255; analog trigger/motion/rumble fidelity is not implemented.
- Main-queue callbacks merge physical and touch buttons. One physical controller
  selected, connect/disconnect observed; old handlers detached, weak ownership
  plus active/current-pad checks discard stale callbacks. Disconnect returns to
  touch state with centered sticks. System gestures disabled for menu/options
  during this app's input ownership. On-screen controls stay visible.
- RuntimeFrontend::set_input_focus updates native g_game_window_focused atomically
  when input is enabled/disabled. Native is_input_allowed otherwise depends on
  this or saved background_input_enabled. Do not rely only on its true default.
- App resolves two new input exports, enables before presenting the renderer,
  clears/disables before Stop cancellation, on resign-active via existing Stop,
  on view disappearance and on all result paths including incomplete cleanup.
  Rendering/JIT/memory policy is unchanged from131. Audio remains null.
- CMake builds RuntimeInput.cpp in the dylib, GameInputController.mm in the app,
  links GameController framework only to the app. Info/fixture version132.

Validation: all66 patches apply from exact92b931b9fb5eef7f1317cb482917dfc19aceebd9.
New test_ios_pad_input.py reconstructs affected native files with all patches,
compiles exact handler, Pad/Button/Stick types, native copilot copying and standard
pad_get_data body with production atomic bridge under ASAN+UBSAN. All16 independent
press/release packets, held/no-change packets, pressure mode, neutral/inverted axes,
wrong-port/duplicate binding rejection, stop/focus/disconnect state,64 resets,
100000 concurrent alternating snapshots and racing writers after disable pass.
FXO/config/clock/logging/endian storage/PadHandlerBase are host interfaces; UIKit
and physical GameController are source contracts, pending iOS compilation/device.
Production runtime/frontend lifecycle regression and frozen CoreBridge/120 stages/
four Quick start foundation/session ABI fixtures pass. Workflow runs new input
regression in intake job;34+2 prerequisites retained. No full iOS SDK locally.

Parent main e275027ed3343def02fe39ebfa92610019526b25. User already authorizes main
publication/builds. Publish with expected-parent lease; check one queued run, do
NOT monitor. Next phone test: install ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start ->
Start game, wait for Press START, tap the visible START (hold briefly if needed),
then arrows/cross/circle or connected controller. Stop game and share log/result.
No reimport/full diagnostics required. No sub-agents. Concise English, no images.
native132-validation has all66; native131-validation also now has66 despite name.


## Build133 — early texture-cache eviction; remove play-session diagnostic cost (2026-10-15)

User supplied ARMSX3-startup-20261015-205439-635-36051.txt and reports:
“Hung up somewhere in the menu, very bad frames per second. Buttons work”.
Read local attachment directly (no Library tool):
/workspace/scratch/8dcd4680dd95/upload/ARMSX3-startup-20261015-205439-635-36051.txt
Library ID libfile_b82030430cec8191afd9e06aa4500a2a. Export PID36051 recovers prior
Build132/PID36027 session. Input/UI touches repeatedly log PS3 START and the user
confirms actual button effects. Do not regress/rework the confirmed input path.

Evidence: run starts1792097520.209142. Initial presents advance~150/5s, then95,
148,40,14,12 and stay~12/5s (~2.4fps), reaching1851 at7620.632288. The game writes
~1.9GiB carchive_cache.rpf into31 cached files; this completes7617.868971 and may
make later tests warmer/faster independently of code changes. Reused upload
batches at7623.8515..7624.3411 all finish withpending0K. No upload-ring growth.
At7624.461864 texture cache usage462127232bytes (~440MiB), native quota321912832
bytes (~307MiB). Two eviction attempts refuse the already-held cache mutex.
341KiB pool3 allocation fails7624.464421; RSX fatal VK_ERROR_OUT_OF_DEVICE_MEMORY
7624.471051. The fatal observer begins shutdown; all28PPU+6SPU contexts join,
11,852,331,123 instruction estimate /2,067,159 completed HLE calls captured.
CPU/FXO teardown begins7624.492310, but no AFTER FXO/VM marker; two shader workers
finish within~0.12s. Cleanup times out30s later7654.489308 and UIKit reports FAIL.
Do not claim a clean stop or identify a particular Vulkan destructor wait yet.

Patch0067-ios-preempt-texture-cache-pressure.patch:
- iOS texture-cache quota=min(native quota,192MiB). Other platforms retain native
  quotas. Fix the common warning's incorrect units (bytes were printed with M).
  Explicit TargetConditionals include in VKTextureCache.cpp for reliable guard.
- New private renderer reclaim_texture_cache() runs after the proven upload-ring
  batch helper, before load_texture_env sampler/cache locks and before blit's
  GPU scope/cache entry. Skip when uninterruptible/flushing/deadlock.
- Check current texture-pool bytes at a192MiB watermark. If native quota exceeded,
  invoke existing on_vram_exhausted(fatal) OUTSIDE cache locks. Native path syncs
  GPU before evict_unused, excludes current guest fragment/vertex textures,
  purges invalidated/unlocked entries and performs a second sync. New helper
  drains driver GC afterward, ensuring queued deletion completes before the next
  allocation, and marks samplers dirty so old descriptors are rebuilt.
- Next check=max(192MiB,remaining+16MiB). If no eligible textures can be released,
  avoid repeating hard syncs on every draw; retry after another16MiB growth.
  Marker “iOS: texture-cache budget pass beforeM -> afterM (released=N)”. No
  arbitrary unlocking, manual ring pointer reset, ignored allocation error or
  discarded active GPU resource. Cached-vs-live working-set limitations remain.
- Add low-frequency native VKGSRender destructor markers BEFORE DMA sync,
  BEFORE/AFTER device idle, BEFORE async scheduler join, BEFORE shader compiler
  join, AFTER device/instance destruction. These diagnose residual cleanup hangs;
  they do not bypass or cancel native ownership/synchronization.

Performance changes:
- Runtime renders set ppu_call_history=false (non-render3s diagnostics keep true).
  Native interpreter selects set_call_history only when true, so this removes
  branch recording from interpreter work. Native syscall-history index still
  increments with a single last-call record, preserving capture totals/evidence.
  Update runtime host test to assert this policy at native Run and model1 entry.
- StartupLog.mm still write()s every line immediately. LogSyncPolicy.h only
  fsyncs P4 core chatter at most once/second; all explicit startup/input/result
  markers retain immediate fsync. No queued/background log worker. Avoids the
  earlier per-message disk flush while preserving logs on app termination.
  Note logs::warning includes native success levels; there was NO regex bug:
  logs.cpp explicitly supports patterns such as “.*”. sys_fs and network use
  warning for routine operations, so warning-only still produces many lines.
- Success UI detail no longer says controls are pending. Renderer/decoders/JIT,
  resolution720p and audio policy unchanged. Static interpreters remain a likely
  performance limit; no speedup claim before device measurement.

Validation:
- All67 patches apply to exact92b931b9fb5eef7f1317cb482917dfc19aceebd9.
- New test_ios_menu_memory.py reconstructs changed native files then compiles
  exact cache quota, common evict_unused/handle_memory_pressure, new renderer
  method and production log-sync policy with ASAN+UBSAN and warnings-as-errors.
  Modeled8GiB stream stays<=212MiB texture-pool peak, preserves excluded active
  textures and framebuffer storage, waits/drains before free, checks lock refusal,
  all skip gates, pinned-set16MiB hysteresis and failed-GPU-wait ownership.
  Desktop retains307MiB quota/no iOS reclaim. Old no-preflight path must reproduce
  modeled440MiB allocation refusal. GPU/FXO/storage/GC are host interfaces, not
  real driver execution.100000 routine logs /8 concurrent writers prove paced
  syncing; explicit boundary messages still sync immediately.
- Production runtime/frontend lifecycle test passes with render history disabled,
  one-entry capture and existing failure/timeout/config restoration cases.
- Input regression and frozen bridge/120 stages/four Quick start foundation/
  Build133 fixture pass. Python scripts parse, non-patch whitespace passes.
- Workflow adds menu-memory test to intake (still34+2 prerequisites), adds header
  to push paths. Whole ios directory copied, so new sync header reaches both app
  and dylib compile. Actual iOS SDK/build and phone behavior remain pending.

Parent main f5508cb6653bcdfb0905f000c2cbedb9d973c8fe. Publication/build authorized.
Publish expected-parent lease, check one queued run, do NOT monitor. Next install
ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start game, START, navigate the same
menus, Stop game, send log/result/responsiveness. No reimport/full diagnostic run.
Latest working tree native133-validation has all67; native132-validation also67
now despite its historical name. Concise English, no generated images/agents.


## Build134 — preserve cached pixels; trim completed idle images first (2026-10-15)

User supplies ARMSX3-startup-20261015-212729-223-36239.txt and says:
“Graphic looks fantastic no glitches. It’s just very laggy fps wise. I bought the
starter car and accidentally closed my phone and the game closed.”
Read local copy directly, no Library attachment lookup:
/workspace/scratch/8dcd4680dd95/upload/ARMSX3-startup-20261015-212729-223-36239.txt
Library ID libfile_7b2b23d3a798819194e97ee90fba2a27. Build133/PID36239.

Phone evidence: glitch-free visuals, input and car purchase confirmed by user;
driving is NOT confirmed. Render runs~362s with2474 accepted presents. Initial
startup~29fps; menu/car activity mostly1.4-3.9fps.1903 completed upload batches
sum60.46GiB,481 texture-cache pressure passes; median drop22MiB, before-pass peak
226MiB, after-pass max206MiB. Some30s windows upload~9GiB for only~45 presents.
This is severe cache churn, not evidence that an interpreter switch is required.
No OOM/fatal. At9626.408162 input disables;9626.411175 Stop begins after screen
lock via sessionWillResignActive. CPU joins finish9633.74236:28PPU+6SPU,
32,157,589,740 estimated instructions and4,729,405 completed HLE/LV2 calls.
All Vulkan/FXO/VM teardown markers complete, device/instance destruction9636.96536,
fully stopped9637.130547, RENDER/UI PASS9637.137635. Phone lock intentionally stops
the current session; this was NOT a crash. Do not change lifecycle/background GPU
behavior while optimizing texture reuse. App now logs the inactive-trigger cause.

Identified two interacting allocation classes in Vulkan texture pool:
- Content-backed cached sections retain useful guest pixels.
- m_cached_images contains GPU-completed images whose content association has
  been discarded. cached_image_reference_t moves them into the reuse pool only
  when its native deferred GC callback runs after GPU completion.
Build133 checked total pool usage and called native fatal eviction first. That
invalidated clean sections unnecessarily. During eviction, section images were
queued to GC, then returned to m_cached_images AFTER handle_memory_pressure had
already cleared that pool. The helper drained GC but did not trim the newly
returned images, so repeated passes could keep~185MiB allocated and throw away
useful pixels again after only16MiB growth. Raising a quota alone is insufficient.

Patch0068-ios-preserve-texture-working-set.patch:
- Public vk::texture_cache::trim_reusable_images(keep_bytes) holds the existing
  m_cached_pool_lock and pop_back()s oldest completed idle images until the pool
  is within keep_bytes. Subtract actual image memory size from cached counter;
  return freed bytes. Direct destruction matches existing on_frame_end resize
  semantics. Never scan/invalidate content sections or touch in-flight objects.
- iOS cache quota and renderer initial check watermark192->288MiB, still below
  the observed440MiB refusal and native307MiB quota on this1024MiB config.
- At safe draw/blit boundaries, trim idle pool to32MiB FIRST. If pool usage now
  fits quota, keep useful cached content and sampler descriptors, avoid native
  eviction/GPU hard waits. Log “trimmed idle texture images ... cached content
  preserved”. Compute nextcheck=max(288MiB,remaining+16MiB).
- If content pressure remains, retain the verified native synchronized fatal
  eviction fallback. Drain GC, THEN trim newly returned idle images to32MiB,
  mark samplers dirty and compute nextcheck as above. No texture quality,
  resolution, shader, JIT/decoder, input, upload-ring, audio or lifecycle changes.
- App resign-active path adds an explicit “app inactive (lock/app switch)” marker
  before the existing clean Stop. Does not add background execution or resume.

Validation:
- All68 patches apply to exact92b931b9fb5eef7f1317cb482917dfc19aceebd9.
- New test_ios_texture_reuse.py compiles exact native cached-image retirement
  ctor/dtor/record definitions, trim method, quota and new renderer preflight
  under ASAN+UBSAN and warnings-as-errors. GPU/content lookup/fatal eviction/FXO
  remain host interfaces; the historical133 test separately compiles native
  common eviction and pressure paths.
- Deferred images stay outside reusable pool until modeled completion+GC; trim
  cannot touch them. Newest reserve preserved; counters/actual allocation bytes
  agree; current native retirement resets image layout/queue family. Real content
  pressure keeps active textures/framebuffer storage, fallback drains before
  post-GC trim, repeated checks do not thrash, skip gates and failed GPU wait
  preserve live ownership.4096 concurrent completed-image callbacks race pool
  trimming safely under the native pool lock.
-120-frame200MiB modeled scene uploads200MiB once, zero content evictions/hard
  syncs; historical133 path produces23960MiB uploads and234 evictions. These are
  model results, not actual FPS or proof of all real scenes fitting288MiB.
- test_ios_menu_memory.py now explicitly reconstructs first67 patches as the
  historical133 regression, matching previous historical tests' bounded scope.
  It still passes. Input and frozen bridge/120-stage/four-foundation/Build134
  fixtures pass; modified scripts parse. Prior runtime behavior unchanged.
- Workflow adds new reuse test, keeps34+2 prerequisites. Full iOS compilation and
  phone performance/memory stability remain pending. No generated images/agents.

Parent main0265cdb0b735cb2067a5e362889cc2699a830c0a. User already authorizes main
publication and builds; publish expected-parent lease. Check one queued build,
do NOT monitor. Next install ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start
game, same menu/car sequence, keep foreground, Stop game, share log/result/FPS
impression. Firmware/disc/cache persist, no reimport/full diagnostics required.
native134-validation has all68; native133-validation also68 despite directory name.


## Build135 — measure remaining RSX frame time after verified texture reuse

User: “Still very laggy but little improvement I think. I stopped the game myself”.
Respect the intentional Stop report. Latest attachment read directly from upload:
ARMSX3-startup-20261015-215246-219-36483.txt, PID36483. Build134 main commit
84151d72eb7ad49d9259c9ca626f751647350adf; run38811129582. No Library tools.

Phone evidence:
- Running1792100957.788703; final1964 accepted presents over roughly199seconds.
-134 upload batches, about4.32GiB,20 fatal-budget cache passes,2 idle-only trims.
  Prior133 run had1903 batches/60.46GiB and481 evictions over roughly362seconds.
  Different user-driven runs; not a controlled FPS comparison. Build134 clearly
  reduces repeated upload/eviction traffic but the user still sees severe lag.
- First30seconds~28.8FPS; next30~27.27FPS; slow scene~1.5–2.6FPS.
  Crucially the90–121second window averages~2.05FPS with ZERO upload batches and
  ZERO cache evictions. Texture churn is not a complete explanation for low FPS.
- Main PPU estimated10.187B instructions; [MC] Render Thread2.631B instructions
  and2,013,643 completed HLE calls; all34 joined guest threads total16.257B
  estimated instructions/3,104,051 calls. These are collected AFTER joining,
  not a new license to race live guest cia/registers/function/history fields.
- Log inactive marker1792101156.418729, Stop1156.422664; all28PPU+6SPU joined;
  Vulkan device/instance teardown1157.1925, FXO1157.3812, VM1157.3844;
  fully stopped zeroCPU1157.386671, RENDER/UI PASS1157.392093. Clean Stop,
  no fatal/OOM. Do not treat the nearby inactive marker as a crash or contradict
  the user's report that they stopped intentionally.

Patch0069-ios-rsx-exclusive-timing.patch:
- Uses existing native rsx::prof scope buckets for RSX-thread exclusive wall
  time, independently of g_enabled. Existing fine scopes include FIFO decode,
  FIFO starvation, guest semaphore wait, vertex/shaders/textures, submissions,
  fence waits, swap waits and resource collection. Method scope also bills the
  method-handler bucket. No graphics algorithm, quality, decoder or input change.
- iOS owner is atomic<const void*>; only matching pthread_self() accesses the
  plain clock/bucket accounting. Foreign threads return before accessing it.
  Darwin identity uses pthread_self rather than assuming ARM's generic thread
  pointer builtin identifies Darwin pthreads. Non-iOS gating remains unchanged.
- begin_ios_timing on RSX cpu_task before measured scopes resets every session,
  even if pthread identities are reused. report every>=10seconds at frame end;
  flush current bucket, print only buckets>=0.5%, frames/window wall/average,
  then reset clocks while preserving the active/enclosing scope. Final report
  from thread::on_exit before native cleanup, then disarm owner. Reporting/log
  time excluded from the next window. Zero frequency/elapsed cannot divide by0.
- Full native profiler has live guest-register/VM walks, background sampler,
  watchdog snapshots and racy auxiliary histograms. Do NOT enable it wholesale.
  On iOS start_sampler and set_enabled return without enabling or creating it;
  g_enabled remains false; iOS tick_frame returns after its dedicated report,
  bypassing native spike/guest snapshot code. No new background thread and no
  enabled GPU timestamp profiler. Native default config rsx_profiler is false.
- Timing reports describe wall time, NOT actual CPU utilization or measured GPU
  execution. Idle FIFO dominance would support guest production bottleneck;
  fence/swap dominance suggests synchronization/GPU path; expensive work buckets
  select the next fix. It cannot alone identify a guest loop or exact GPU kernel.
  Counter reads/pthread identity add profiling overhead; no FPS gain promised.

Validation completed:
-69 patches apply cleanly to pinned92b931b9fb5eef7f1317cb482917dfc19aceebd9.
- New test_ios_rsx_timing.py compiles the COMPLETE patched native profiler header
  plus exact iOS report/lifecycle/prefix bodies under ASAN+UBSAN, warnings as
  errors, mocked clock/log interfaces. Covers nested exclusive70/20/10percent,
  ten-second windows, reset inside nested scopes, idempotent early scope close,
  foreign-thread exclusion, final Stop, same-pthread restart, method attribution,
  zero length/frequency and disabled sampler/full-profiler enable calls.
- Production runtime/frontend/native BootGame/JIT-finalizer regression passes,
  including Stop, delayed teardown and cleanup failure paths. Complete native
  Vulkan/Apple compilation is NOT possible without SDK; Actions validates it.
- Texture retirement/reuse regression passes:200MiB modeled scene uploaded once
  across120frames, zero content evictions; historical192MiB path23960MiB/234
  evictions; completion/ownership/failed-wait/concurrent idle pool checks pass.
- Native input regression passes all16buttons, holds/releases/axes/Stop/concurrent
  snapshot checks. Frozen bridge/120stages/four Quickstart foundations/Build135
  fixture passes; scripts parse; nonpatch whitespace check passes.
- Workflow adds timing regression, retains34+2 prerequisites. No agents/images.

Next publish135 to main using expected-parent lease84151d72..., check one queued
installable core workflow only, do NOT monitor builds. User already authorizes
publishing/builds. Install ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start game,
START, same menu/car sequence about60seconds, Stop game, share log/responsiveness.
Existing firmware/disc/cache persist. Graphics previously glitch-free and starter
car purchase verified; driving still unconfirmed. Null audio unchanged.
Native135-validation contains69 patches; native134-validation still68.


## Build136 — PPU dispatch lookup reduction and kernel CPU-time samples

Latest attachment read directly from upload, no Library tool:
ARMSX3-startup-20261015-223207-130-36752.txt, PID36752, Build135.
Parent main7bc62e849aeafe266f01401ce96fb25e18b84d25; tree
9fe203efb0c48c02e8d34282ebfcae042e052e26; installable run38814478748.

Phone evidence:
- Running1792103235.754506; manual Stop1792103512.113905; final2138 accepted
  presents. RSX final report3512.207299; Vulkan device/instance destroyed
 3513.052652; FXO3513.224430; VM3513.227501; fully stopped3513.233354;
  RENDER/UI PASS3513.235247/3513.245943. No crash/fatal or stuck cleanup.
-21 complete slow timing windows:435frames in216.68seconds =2.01FPS.
  Wall-time-weighted exclusive RSX buckets: empty FIFO71.04%, fence wait8.95%,
  texcache lookup4.64%, vertex/index3.78%, submit3.32%. Most slow windows empty
  FIFO60–84%; one texture-pressure window26.5%FIFO/28.8%texcache/21.7%fences.
  Earlier startup/copyright windows mostly30FPS and guest-semaphore pacing.
-196 upload batches/about6.36GiB over~277seconds, broadly consistent with the
  improved134 texture policy. Do not revert to192MiB eviction or lower graphics
  quality to attack predominantly empty FIFO time.
- Joined totals20,126,183,449 estimated PPU instructions/4,148,685 completed calls,
 28PPU+6SPU contexts. First mainPPU11,014,578,847 instructions/62058calls;
  guest0x1000008 [MC] Render Thread3,827,675,113/2,759,901, lastusleep. CPU-side
  command starvation is supported; which interpreter or synchronization path
  dominates is not yet proven. New kernel metrics are intended to resolve it.

Patch0070-ios-ppu-dispatch-probe-cache.patch:
- PPU static exec_task captures its thread-local diagnostic probe ONCE before
  the loop and uses the local pointer for budget/end/step handling. Existing
  bounded entry points set the TLS pointer before entering exec_task and restore
  it with RAII, including nesting and exceptions. Ordinary runtime previously
  resolved the null probe repeatedly at every interpreter dispatch boundary.
- No guest ISA, instruction count, scheduler, clocks, decoder, state/stop check,
  mutable JIT, memory protection or diagnostics budget change. Nested exec_task
  invocations get their own current pointer. Non-Apple paths unchanged.
- iOS kernel thread names retain63bytes rather than the original15; macOS and
  Linux name behavior unchanged. Guest name storage/native log names unchanged.
  Needed so kernel samples can say main/render/SPURS names rather than only IDs.

RuntimeCpu.cpp/HostCpuUsage.h:
- Runs on the existing serialized runtime worker at render heartbeats (every5s
  in continuous sessions), first call establishes baseline. No extra thread.
- task_threads acquires own-process Mach rights. THREAD_IDENTIFIER_INFO supplies
  stable64-bit kernel IDs; THREAD_BASIC_INFO supplies cumulative user/system
  CPU seconds+microseconds; THREAD_EXTENDED_INFO supplies bounded kernel names.
  Does NOT use pthread pointers or touch live CPUThread/VM/register/history data.
- Rank per-thread deltas over steady-clock wall duration.100%=one fully used CPU
  core, summed usage may exceed100%. Log top8 and sum of comparable LIVE threads.
  First-seen, missing, counter-reset and non-forward-clock cases rebaseline;
  previous maps retain only this snapshot, avoiding accumulation across churn.
  This is not complete process accounting for threads that exited mid-window.
- RAII releases EVERY acquired thread port and the returned VM array, including
  thread_info failures and allocation exceptions. Observation errors reset the
  baseline and log nonfatal failure, leaving game execution/Stop intact.
- Runtime resets observation at each authorized run and samples only rendering
  heartbeats. New CMake source is linked into the core. Runtime regression models
  the CPU-observer APIs; dedicated tests compile the complete production collector.
- Apple primary API references checked: official thread_extended_info_data_t
  docs; apple-oss-distributions/adv_cmds ps/tasks.c demonstrates task_threads
  port+array cleanup; Apple XNU THREAD_IDENTIFIER_INFO test and basic-info
  microsecond conversion. No final external API guidance/citations needed.

Validation completed:
- All70 patches apply to exact pinned92b931b9fb5eef7f1317cb482917dfc19aceebd9;
  native136-validation contains70; native135-validation still69.
- test_ios_ppu_dispatch_cache.py compiles exact native exec_task and bounded
  helper with host VM/ISA/state interfaces, counts TLS resolutions: ONE across
  one million ordinary iterations per worker, two joined workers. Nested bounded
  callbacks inside ordinary and bounded callers restore pointers; end/budget,
  invalid args, pre-stopped state, handler exception cleanup/restart all pass.
- Existing P55 production dispatcher/retained workers/caller/callee/leaf/stack/
  TLS fixture passes576slices with intended faults and joins/restoration. Full
 34 synchronization job matrix remains required in Actions.
- test_host_cpu.py compiles production HostCpuWindow AND RuntimeCpu.cpp under
  ASAN/UBSAN and warnings-as-errors with explicit Mach interfaces. Verifies
 100%/50% per-core usage and user/system split, ranking, identity churn, reset,
  zero/reversed clock and baseline; complete collector releases every acquired
  right/VM array on success, partial query failures, missing names, task snapshot
  failure and exception. Real Mach ABI/SDK compilation still requires Actions.
- Production runtime/frontend/BootGame/JIT-finalizer/Stop regression passes,
  isolated RSX timing regression passes, frozen bridge/120stages/four Quickstart
  foundations/Build136 fixture passes; modified scripts parse; whitespace clean.
- Workflow adds both new tests;34+2 prerequisites unchanged. No agents/images.
  Build135 graphics/input/texture reuse retained; null audio unchanged. No large
  FPS gain claimed from the lookup change. New kernel data must guide next fix.

Next publish136 using parent lease7bc62e8..., check installable queued run ONCE,
DO NOT monitor. User authorizes publishing/builds. Install artifact
ARMSX3_iOS16_INSTALL_THIS_IPA; Quick start -> Start game, same menu/car sequence
for about60seconds, Stop game, share log/responsiveness. Imported state persists.
PPU enum supports only static and LLVM; SPU dynamic still has the missing Apple
mutable-JIT boundary. Do not flip decoder blindly. Full recompiler performance
will require implementing the real iOS JIT backend/LLVM build, not bypassing
apple_jit_write_protect or pretending static is a recompiler. Driving unconfirmed.


## Build137 — park sustained empty RSX FIFO on iOS

Latest attachment read directly from upload:
ARMSX3-startup-20261015-231031-944-37145.txt, PID37145, Build136.
Parent mainc6a8658ec54bc32779e9e1565a10083c726fbeef; tree
00ebbf9dbedb22c5e01bc285d91f4ad428537e36; installable run38819019886.

Phone evidence:
- Running1792105523.486214; user Stop5826.403588; final2352 accepted presents;
  RSX final5826.888175; GPU idle5826.903573; device/instance5827.810685;
  FXO5828.003297; VM5828.006490; fully stopped5828.010174; RENDER/UI PASS
 5828.012070/5828.023808. No fatal/crash or hung teardown.28PPU+6SPU contexts,
 22,784,884,733 estimated instructions/4,480,224 completed HLE/LV2 calls.
-22 complete slow windows:400frames/225.26seconds =1.78FPS. Weighted RSX wall:
  empty FIFO66.79%, fences10.84%, texcache lookup6.08%. Many late windows
  empty FIFO~78–80%, frame time~570–595ms. Startup generally~30FPS.
- Kernel sampling now works on the phone. Later29 snapshots (timestamp>=5680)
  average555.1% sampled LIVE CPU usage;100%=one core. Main persistent consumers:
  Primary SPURS Kernel2 and3 each98.2% CPU (97.5%user/0.7%system), Secondary
  SPURS Kernel0 96.5%(95.8/0.7). RSX mean70.1%(69.3/0.7), often75–85% in late
  samples. Other SPUs30–65%, guest render thread~13–16%, audio engine~14–16%.
  SPU interpretation dominates CPU consumption; RSX is also consuming a large
  fraction of a core despite spending most frame time in an empty-FIFO wait.
-259 upload batches/about8.25GiB in~303seconds. No controlled playback comparison;
  do not infer a PPU-cache regression merely from1.78 vs previous2.01FPS.

Native source finding:
- RSXFIFO.cpp EMPTY case always sync_get_force()s before idling, initializes an
 8-poll hot window on running->empty, then ARM uses has_wfe_event_stream() to
  choose WFE or yield. util/sysinfo.cpp returns TRUE for non-Linux, including
  Apple, WITHOUT a measured capability probe. The iOS path was therefore using
  the ARM WFE shape, not necessarily sched_yield. Do not mislabel its observed
  high USER CPU time as kernel yield overhead. We have direct CPU/wall evidence
  it is still an expensive wait on this phone, without proving exact WFE behavior.
- Upstream comments discuss50us sleeps previously reverted after Android affinity/
  reservation changes left cores idle. That evidence does not match this A15
  run:~5.55core-equivalents busy across a six-core CPU. Keep non-iOS paths intact.

Patch0071-ios-park-idle-rsx-fifo.patch:
- iOS-only branch retains initial8pause() polls. On sustained FIFO_EMPTY use
  native thread_ctrl::wait_for(100), default alert=true. PUT stores do NOT notify
  that wait, hence timed100us request rather than indefinite park. No WFE event
  stream assumption on this branch. Scheduler may wake later than100us; actual
  latency/frame pacing must be measured on phone.
- Native sync_get_force publication, FIFO reread, command flow/state transitions,
  thread Stop/pause/interrupt checks, shaders, texture policy, decoder and input
  remain intact. No extra sleeping for already available commands. Native busy,
  NOP, jump-to-self and guest semaphore paths are not modified.
- Set RSX-owned m_cycles_counter=0 after parking. Only its outer-loop64-poll
  maintenance cadence uses this field. Next iteration therefore services native
  do_local_task/ZCULL/host DMA before reading again; otherwise100us*64 would
  add~6.4ms requested delay to periodic servicing. Stop/pause remains first.
- Existing idle_fifo scope encloses the wait. begin_ios_timing log identifies
  “empty FIFO wait=100us after 8 hot polls”; RSX wall and kernel CPU reports stay
  enabled so next log can compare idle CPU reduction and actual frame progress.
- No new ABI/source/helper dependencies; RSXFIFO.cpp includes the patched profiler
  header providing TargetConditionals. m_cycles_counter is accessed by its own
  member function. Current wait implementation/backend already compiles in core.

Validation completed:
- All71 patches apply to exact92b931b9fb5eef7f1317cb482917dfc19aceebd9;
  native137-validation has71; native136-validation has70. Native whitespace clean.
- New test_ios_fifo_idle.py reconstructs exact native RSXFIFO prefix through
  EMPTY/NOP and exact complete outer while(!test_stopped()) loop, with explicit
  FIFO/clock/wait/state/subunit interfaces. ASAN+UBSAN, warnings as errors.
  Four compile profiles: iOS ARM64, macOS ARM64, non-Apple ARM64, non-ARM.
  Pinned non-ARM code already has an unused-but-set ARM spin counter, so ONLY
  that profile suppresses that inherited warning; all iOS/ARM checks retain it.
-300idle polls: GET published each time,8hot polls then291timed parks on iOS;
  zero iOS WFE/yield. Command injected during a wait is consumed once on the next
  poll; subsequent drain gets8fresh hot polls. Stop injected during park exits
  before another FIFO read; external pause uses native exit path. NOP transitions
  remain native. Every park followed by another running iteration gets native
  local-task/ZCULL/DMA service on THAT iteration, with matching service counts.
- Non-iOS ARM retains WFE when capability=true and yield when=false; non-ARM
  retains yield and zero new timed waits. Host wait duration is modeled; this
  does not establish real Mach/iOS wake precision or CPU/FPS improvements.
- Production runtime/frontend/BootGame/JIT-finalizer/Stop regression passes,
  isolated RSX timing and complete kernel CPU collector regression pass, frozen
  bridge/120stages/four Quickstart/Build137 fixture passes. Scripts parse.
- Workflow adds FIFO regression;34+2 prerequisites unchanged. No agents/images.
  No SPU profiling overhead, decoder change, recompiler enablement, GPU quality
  change or arbitrary clock/scheduler tuning added. Real FPS remains untested.

Next publish137 with leasec6a8658..., verify installable workflow queued ONCE,
DO NOT monitor. User authorizes publication/builds. Install
ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start game, same menu/car sequence
about60seconds, Stop, share log/responsiveness. Compare rsx::thread CPU vs its
FIFO idle wall time and frame count, and SPU CPU usage. Static SPU may still be
real-work-bound or spinning in guest loops; utilization alone cannot distinguish
those. If lag persists, investigate SPU work using owner-thread-safe evidence
and/or real iOS recompiler implementation. Do not enable native live guest sampler
or bypass the missing mutable-JIT boundary. Driving remains unconfirmed.


## Build138 — SPU-owned sparse dispatch profiling after verified RSX CPU savings

Latest attachment read directly from upload:
ARMSX3-startup-20261015-233940-517-37371.txt, PID 37371, Build137.
Parent main 18d592fb9784325058cdb8d1465b9dc5d51d7bd6; tree
272de1dd0efe1d42e0737fdbeeb5e898bcb77fae; installable run 38822889067.

Phone evidence:
- Clean user Stop at 1792107575.214346; final 2243 accepted presents. RSX final
  7575.218951, GPU idle 7575.233717, device/instance gone 7576.166075, FXO done
  7576.353942, VM done 7576.356738, fully stopped with zero CPUs 7576.361438,
  RENDER/UI PASS 7576.363271/7576.367242. No fatal/crash or hung teardown.
- 25 complete slow RSX windows: 510 frames / 257.88 seconds = 1.98 FPS, weighted
  empty-FIFO wall time 55.8%. Later stable windows remain about 79–80% idle.
  Build136 had 22 slow windows, 400 frames / 225.26 seconds = 1.78 FPS.
  Different manual sessions: do not claim a controlled FPS gain.
- Last 20 CPU snapshots: RSX mean 17.1% of one core, versus 78.9% in the prior
  run's late 20. Build137 timed parking clearly reduced renderer CPU use.
  Primary SPURS Kernel2/3 still average 98.8%/98.7%, Secondary Kernel0 97.1%.
  Total sampled live CPU is about 495–500% late versus about 555% previously.
  PPU render thread is about 16%; other SPUs vary around 35–65%.
- 28 PPU + 6 SPU joined contexts; 21,865,732,711 estimated instructions and
  6,690,721 completed HLE/LV2 calls. Utilization alone does not tell whether
  SPUs perform useful work or spin in guest loops. Native SPU log/kernel names
  use lv2_id; joined runtime registry IDs are different and must not be equated.

Patch0072-ios-spu-owned-dispatch-profile.patch:
- Only SPUCommonRecompiler.cpp changes. iOS-only, static thread_local profile
  per SPU host worker, cached pointer once on entry to old_interpreter. The
  fixed table/countdown persists across short gateway re-entries. Destruction
  stays trivial because SPU g_escape can abandon interpreter stack frames.
- Sample the opcode ALREADY fetched by the owner, with its current PC. Jittered
  LCG stride 16384..32767 dispatches avoids one fixed sampling interval. There
  is a decrement/branch each instruction; actual phone overhead is unmeasured.
  No extra guest-memory read, remote live register/LS/registry access or thread.
- Sample handling is noinline, fixed 128-entry open-address table keyed by
  PC AND opcode, so code changes at the same address remain separate. Full
  tables count untracked samples; they do not silently claim full coverage.
  Entries retained early in a window can omit later sites: interpret coverage.
- Clock checks occur only on sparse samples. Every >=10 seconds report total
  samples, untracked count, window wall time, final flag and six frequent
  PC/opcode pairs with percentage of ALL samples. Ranked copy/string formatting
  happens only when reporting. The fixed table itself needs no heap allocation.
- Normal stopped-loop return flushes the remaining window. Gateway escape or
  exception can bypass that final report; periodic reports remain the evidence.
  Normal fallback re-entry does not clear the histogram or emit per-entry logs.
- The log explicitly calls this instruction frequency, not CPU-time attribution.
  High dispatch counts alone do not justify skipping instructions or sleeping
  SPUs. Keep the native guest semantics, state checks and fallback/decoder gates.
- Keep Build137 FIFO parking/next-poll maintenance, all graphics/texture policies,
  input, PPU dispatch cache, null audio and current JIT protections. Full native
  profiler stays disabled: its remote guest register/memory sampler is unsafe.
  SPU dynamic requires LLVM-generated code, not a free C++ decoder setting.
  Real recompiler performance still needs the actual iOS LLVM/JIT implementation;
  never bypass apple_jit_write_protect or enable mutable code speculatively.

Validation completed:
- All 72 patches applied to exact 92b931b9fb5eef7f1317cb482917dfc19aceebd9 in
  native138-validation; native whitespace clean. No submodules/Apple SDK locally.
- New test_ios_spu_profile.py reconstructs the exact pinned native SPU file
  through all patches, compiles the production old_interpreter before/after72
  and actual profile class. ISA/storage/clock/log/state interfaces are explicit
  host models; this is not full SPU ISA or ARM gateway/device validation.
- ASAN+UBSAN, warnings as errors, iOS/macOS/Linux compile profiles all pass:
  200000 dispatches retain exact branch/PC/accumulator/state-check results;
  stride range/endpoints, 70/30 counts, coverage/misses, changed opcodes, reset,
  zero samples/frequency, periodic/final reports and trivial destruction pass.
  40000 short fallback invocations retain one TLS histogram/countdown, and six
  concurrent host workers keep independent profiles. Non-iOS execution unchanged.
- Historical SPU entry/missing Apple API boundary, production runtime/Stop/JIT
  finalizer, four-platform exact FIFO wait/outer maintenance and frozen fixture
  all pass; changed Python scripts compile. LeakSanitizer cannot inspect this
  sandbox's /proc tasks, so rerun the two historical tests with the same
  ASAN_OPTIONS=detect_leaks=0 already configured in CI; ASAN+UBSAN remain enabled.
- Workflow adds the SPU profile regression to intake-host; 34+2 prerequisites
  unchanged. App/fixture version138. No agents/images. No promised FPS increase.

Next publish138 with lease18d592fb..., verify installable workflow queued ONCE,
DO NOT monitor. User authorizes publication/builds. Install
ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start game, spend about60seconds
in the SLOW 3D menu/car screen (startup copyright screens can already run30FPS),
Stop game, share log/responsiveness. Look for “iOS SPU dispatch profile” together
with HOST CPU and iOS RSX timing. Decode repeated PC/opcodes with native sources,
account for untracked coverage and quantify overhead before a targeted change.
Graphics/input/starter-car purchase work; driving remains unconfirmed.


## Build139 — retire geometry between draws after an attribute-ring OOM

Latest attachment read directly from upload:
ARMSX3-startup-20261016-013526-546-37950.txt, PID 37950, Build138.
Parent main 9421381f6ede00fd46d8029f58db4d7cadc0e3e0; tree
34d9d616c9cab7c8514821cb892582a1e0b1772c; installable run 38833243398.

Phone evidence and revised priority:
- UI FAILED because RSX hit VK_ERROR_OUT_OF_DEVICE_MEMORY, not because the
  user requested Stop. Last heartbeat at 1792114429.690273 had 1902 accepted
  presents. Fatal at 4431.826087; runtime caught it at 4431.829302 and cleaned
  up. Device/instance gone 4436.189710; FXO 4436.378866; VM 4436.381660;
  fully stopped with zero live CPU threads 4436.382902; UI FAIL 4436.394583.
- At 4430.429575 the attribute buffer starts growing 64->80->96->112->128->
  144->160 MiB over about 1.4 seconds. Requests only 550,473,255,92,67,492 KiB.
  Several allocation recoveries succeed, then the 160 MiB replacement is refused
  (system pool=1, pool total=274 MiB, reported heap cap=1024 MiB). This is a
  geometry-stream retention problem before the existing 1 GiB reclaim ceiling.
  The heap budget check does not predict what the iOS driver can allocate.
- 9 complete slow windows: 143 frames / 94.2113 seconds = 1.52 FPS. Startup
  remains near 30 FPS. Late FIFO-empty wall shares reach about 80–86%; the
  4422.792212 window instead spends 43.6% in texcache lookup and only 2.5%
  FIFO idle. 193 completed texture-upload batches, about 6.17 GiB, pending=0.
  Texture batching alone cannot bound a draw burst with few texture uploads.
- All six SPUs emit 17 instruction-profile reports including final flushes.
  Kernel2/3 total 513260/508669 samples, 420100/419957 untracked (about 82%).
  Secondary Kernel0 970817 samples/718981 untracked; Primary Kernel4
  272910/149193. Primary2/3 contain many different PC/opcodes around d3c4–d504;
  Primary4 has a repeated four-instruction loop around cacc–cad8/b828–b834.
  This is instruction frequency with incomplete coverage, not CPU time and not
  proof of safe idle loops. Do not skip guest work based on these samples.
- No controlled Build137/138 FPS comparison; diagnostic countdown, scene, timing
  and thermal state can differ. Address the concrete fatal allocation first.

Patch0073-ios-retire-geometry-between-draws.patch:
- VKGSRender::end invokes reclaim_geometry_uploads after dirty frame-context
  handling, before pipeline analysis, texture/sampler locking, load_program_env
  or emit_geometry. No new draw's offsets or CPU upload pointers exist yet.
  Deliberately not called from grow()/mid-upload/mid-subdraw with live temporary
  allocations. A very large single guest draw still uses native growth; this
  is a batching watermark, not a universal hard cap or an allocator OOM retry.
- iOS-only checks: skip uninterruptible/flushing/deadlock or absent geometry
  heaps; trigger if pending attributes>=32 MiB OR indices>=8 MiB (half of the
  initial 64/16 MiB rings). No dependency on presents or texture-upload bytes.
- Capture submitted CB pointer, native flush_command_queue(), then CHECK_RESULT
  on its wait(FRAME_PRESENT_TIMEOUT). Native success-only monotonic snapshots
  return managed ring space. Timeout/device failure leaves snapshots/memory
  pending and skips cache invalidation. No early GET reset or buffer deletion.
- After SUCCESS, purge cached vertex ranges, reset the three shader bulk
  allocators, mark vertex/fragment contexts, texture parameters, transform and
  fragment constants, raster stipple and interpreter instruction data dirty.
  Subsequent load_program_env rebuilds references before ring bytes are reused.
  Bulk reset simply discards unused suballocations; it never rewinds the ring.
- Log “iOS: completed geometry batch” with attribute/index bytes and pending
  bytes. Existing CB render-pass/query close, queue ordering and state reload
  behavior is used. No manual Vulkan command injection or altered draw semantics.
- Non-iOS helper is empty; prior growth policy and all texture/image/input/audio
  policies remain. A new generic bulk_allocator::reset is only used here.

Patch0074-ios-make-spu-dispatch-profile-opt-in.patch:
- Gate only the four Build138 observer regions with the compile definition
  ARMSX3_IOS_SPU_DISPATCH_PROFILE=1. Normal build has no per-instruction observer
  decrement, sample table, TLS initialization or profile logging. Keep optional
  code/test available for targeted investigation; no UI option required.
- Preserve the two earlier independent iOS immutable/JIT boundary guards in
  SPUCommonRecompiler.cpp. No decoder change, LLVM enablement or protection bypass.
  RSX wall reports and Mach kernel CPU sampling remain active.

Validation completed:
- All 74 patches check/apply in order to exact pinned92b931b9... in
  native139-validation, native whitespace clean; changed Python scripts parse.
- New test_ios_geometry_retirement.py reconstructs relevant exact source through
  all patches. Compiles actual ring helper, CB chunk/wait, snapshot manager,
  pipeline flags, bulk reset and new renderer helper. Queue submission, byte
  storage and cache/environment consumers are explicit host interfaces; placement
  is checked against the real end() source. Not a full Vulkan/Metal execution.
- ASAN+UBSAN, warnings as errors, iOS/macOS/Linux profiles pass. Tests cover both
  watermarks, below-threshold no-op, all skip gates, success-only cache purge/
  bulk reset/state flags, preservation of unrelated flags, timeout/device-lost
  retaining pending GET/snapshot/refs, and index-only pressure. Six-and-quarter
  GiB of small vertex/index draws without presents/texture uploads reuses original
  64/16 MiB heaps with no growth; pending byte markers survive until completion.
  Same host workload without the hook reproduces the driver growth refusal.
- SPU test now runs iOS profiling-enabled, iOS DEFAULT-disabled, macOS, Linux:
  all pass. Optional histogram behavior remains covered; default has zero starts
  or reports and matches baseline PC/branch/state results.
- Production runtime/Stop/JIT finalizer, upload retirement including historical
  negatives, graphics-memory/worker cleanup, menu-memory, texture-reuse and
  frozen120stage/Quickstart Build139 fixture pass. ASAN_OPTIONS=detect_leaks=0
  matches CI's environment limitation; ASAN+UBSAN stay enabled.
- Workflow adds geometry regression to intake-host;34+2 prerequisites unchanged.
  No local Apple SDK/full linked emulator test. Real effect needs next phone log.

Next publish139 with lease9421381..., check installable workflow queued ONCE,
DO NOT monitor. User authorizes publication/builds. Install
ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start game, repeat the menu/car
sequence that led to OOM and stay in that scene about60seconds, Stop, share log.
Check geometry batch pending bytes, any further attribute growth/OOM, cleanup,
RSX CPU/wall and FPS. Profiling disabled may remove overhead but promise no gain.
Graphics/input/starter-car purchase work; driving remains unconfirmed.

## Build140 — native iOS ARM64 SPU byte shuffle

Latest attachment read directly from upload:
ARMSX3-startup-20261016-021029-832-38137.txt, PID38137, Build139.
Parent main18040f331f081cce53edc3bafada8ff802366440; tree
2b02c5f5193e868d8676e31df475e1ddc11e5d21; installable run38836907011.

Phone evidence:
- Native running1792116384.832777; user Stop6626.107975; final2141 accepted
  presents. Final RSX profile6626.118351; GPU idle6626.133406; device/instance
  gone6627.063271; FXO6627.240537; VM6627.243621; fully stopped with zero CPUs
  6627.250759; RENDER/UI PASS6627.252641/6627.266506. No fatal/OOM/hung cleanup.
- No attribute-ring growth, no completed geometry-batch report. This session
  did not reach the Build139 watermark, so absence of OOM alone does not prove
  the geometry batching path on-device. Retain its host-verified lifetime fix.
-17 complete slow windows:395frames/176.3714seconds=2.2396FPS. Weighted
  FIFO-empty wall54.41%; later stable windows about70–79%. Initial slow scene
  windows instead spend21–32% in texcache lookup and19–29% waiting on fences.
  Last20 kernel samples: RSX15.3%; Primary SPURS Kernel2/3 98.5/98.4%; Secondary
  Kernel0 97.0%. Other SPUs about58/58.5/66.7%; PPU Render Thread16.4%.
-600 completed texture-upload batches/about19.04GiB;82texture budget passes,
  one idle-image trim. Native PPU estimate18,676,265,006;4,842,254completed
  HLE/LV2 calls;28PPU+6SPU contexts. Normal SPU observer correctly emits no logs.
- Runs/scene/thermal conditions differ. Do not claim controlled gains against
  Build138's1.52FPS or Build137's1.98FPS. Static SPU work remains the priority.

Native source finding / patch0075-ios-neon-spu-byte-shuffle.patch:
- Build138's incomplete owner-only trace contains SHUFB opcodes at many busy
  Primary2/3 sites (top nibble0xb, e.g. b0c30252/bbc7c325). This proves use, not
  a CPU-time percentage. Its full frequency is unknown because coverage missed
  about82% on those workers. No idle-loop shortcut is justified by those reports.
- SPUInterpreter.cpp::SHUFB used16 scalar dependent byte lookups even on ARM64.
  Pinned PPUInterpreter.cpp::VPERM already uses vqtbl2q_u8 with RB/B in the low
  table half and RA/A in the high half. Apply that same host byte-order shape
  only under ARCH_ARM64 && __APPLE__ && TARGET_OS_IOS. Utilities/JIT.h includes
  the existing apple_jit.hpp/TargetConditionals header in the actual core build.
- Preserve index calculation ~control&31 and the complete original SIMD special
  selection: normal bytes for controls<0x80, zero for0x80..bf, ff for c0..df,
  80 for e0..ff. Snapshot all sources before writing destination, retaining
  all RA/RB/RC/RT4 aliases. Remaining function/table/PC/state behavior is intact.
- No new guest-memory reads, cache, TLS, counter, JIT code, decoder setting,
  scheduler change or floating-point/rounding change. Non-iOS paths retain
  scalar selection. x86 optimized_shufb and INIT(SHUFB) routing stay untouched.
- Official Arm reference confirms vqtbl2q_u8 maps to A64 TBL over two vectors:
  https://documentation-service.arm.com/static/5f7b5205bcda971b14568107 (p145).
  This establishes the instruction interface, not an emulator speedup.

Validation completed / CI validation added:
- All75 patches check/apply to exact92b931b9fb5eef7f1317cb482917dfc19aceebd9
  in native140-validation; native whitespace clean; changed Python scripts parse.
- New test_ios_spu_shuffle.py reconstructs exact original/new SHUFB bodies and
  asserts no source changes outside that body or special-value block. Compiles
  real native util/types/v128, BitField/SPUOpcodes headers. Mock spu_thread owns
  128actual v128 GPRs plus PC/guard; only the new NEON table intrinsic is modeled
  on Linux. Existing SSE masks run on x86. This is not real ARM instruction
  execution or a full native spu_thread layout/scheduler/game test.
- ASAN+UBSAN, warnings as errors, five compile profiles pass: iOS ARM selects
  lookup; macOS ARM/other ARM/iOS x86/Linux x86 retain original path.127648cases
  each: every control byte in each lane, all combinations of aliased three
  source registers and four destinations,100000mixed random cases across128
  architectural registers, byte-for-byte old/new/oracle/full-context comparison.
  Return=true and untouched PC/neighbor GPR/guard are checked through comparison.
- Workflow intake-host adds this regression. Core job adds --a15-codegen after
  patch application/toolchain setup and before FFmpeg/core build. It uses real
  xcrun iphoneos clang++, iOS16target/apple-a15, native sse2neon/intrinsic headers,
  and asserts new function assembly has one TBL and no scalar LDRB. Apple SDK
  unavailable locally: this check and full archive/link remain pending CI.
- Historical SPU entry/missing mutable-JIT API rejection, production runtime/Stop/
  finalizer, geometry batch/timeout/ownership and frozen120stage/Quickstart
  Build140 fixture all pass. Existing ASAN_OPTIONS=detect_leaks=0 limitation.
  34+2 host prerequisites unchanged. No agents/images or new standalone artifact.

Next publish140 with lease18040f3..., verify installable workflow queued ONCE,
DO NOT monitor. User authorizes publication/builds. Install
ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start game, same slow3Dmenu/car
screen about60seconds, Stop, share log/responsiveness. Compare frame progress,
HOST CPU and RSX FIFO wall time; make no FPS promise from this isolated change.
Keep Build139 geometry retirement/Build137 FIFO parking, texture quality/input,
null audio and disabled-by-default SPU observer. Real LLVM/JIT work still needs
proper iOS implementation; never bypass apple_jit_write_protect. Driving unconfirmed.

## Build141 — accept Apple's valid vector mnemonic in the A15 assembly check

User reported Build140 workflow failure. Inspected run38840055202, commit
1b77f4ad952c1cbc8b727d8fcf87640c86110338, tree
d26444932ed8ab7250b3358374f21fbb583921cb. All host jobs succeeded. Only core
job116778306403 failed at step9 “Verify A15 SPU shuffle code generation”.

Evidence/cause:
- xcrun/Xcode16.4 successfully compiled the isolated real iOS16/apple-a15
  instruction function. No compiler error. Its output has exactly one
  `tbl.16b v1, { v1, v2 }, v3`, vector loads/stores and no scalar LDRB.
- The Python regex `^\s+tbl\s` only accepted a bare TBL mnemonic. Apple's
  assembly prints the arrangement suffix on the mnemonic, so the assertion
  falsely counted zero. Failure happened before FFmpeg or the full core build.
  Build140 produced no new phone/IPA evidence. Do not claim a native-code fix.

Build141 changes:
- Extract verify_a15_assembly and use it in both the fixture regression and the
  real Xcode path. Accept `tbl` or `tbl.16b`, require exactly one, preserve the
  no-scalar-byte-load requirement and scope checks to the target function.
- Save actual failed diagnostic in tests/fixtures/a15-shufb-xcode16_4.txt.
  It is the printed function fragment, ending before cfi_endproc as in the
  original assertion; not a standalone executable assembly artifact.
- Regression accepts captured Apple output and GNU operand suffix spelling,
  accepts unrelated scalar loads after the target function ends, and rejects
  missing/wrong-width/duplicate lookups, scalar LDRB inside the target, and a
  missing target symbol. No checker skip or weakened instruction-count goal.
- Version/fixture141, README and both handoffs updated. No native patch, decoder,
  graphics, scheduler, Stop or JIT protection change; still75 patches. Retain
  the Build140 vector optimization and the previous tested memory/idle fixes.

Validation:
- Captured assembly/parser regression passes, including negative cases.
- All five sanitized native-layout SHUFB before/after/oracle profiles pass,
  127648 cases each. Build141 frozen120stage/four-stage Quickstart fixture and
  Python syntax checks pass. No need to rerun unrelated native suites locally;
  all host prerequisites passed Build140 and CI retains all34+2 prerequisites.
- The isolated Xcode compile is proven by the failed job's assembly; corrected
  real-codegen assertion and full iOS archive/link still require the next CI run.

Next publish141 with lease1b77f4a..., check queued installable workflow ONCE,
DO NOT monitor. User authorizes publication/builds. Latest device log remains
Build139 (2141presents/clean Stop); do not invent Build140 performance. Once
ready use ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start game, same slow3D
menu about60seconds, Stop, share log. No promised FPS gain. Driving unconfirmed.

## Build142 — native iOS SPU byte rotates and zero-fill shifts

Latest attachment read directly from upload:
ARMSX3-startup-20261016-030418-844-39009.txt, PID39009, Build141.
Parent main8382c229064992eb7adc9bd07ba0b4e24c923239; tree
2ba1b3159d890ef2bbb8281d387f7b2a46cb5125; installable run38840871782.

Phone evidence:
- Running1792119666.234504; user Stop9855.876337. Final2058accepted presents;
  RSX final9855.879532; GPU idle9855.895592; device/instance gone9856.891771;
  FXO9857.078013; VM9857.080998; fully stopped zeroCPUs9857.085281;
  RENDER/UI PASS9857.087155/9857.094070. No fatal/OOM/hung teardown.
-12complete slow windows:321frames/123.4356seconds=2.6005FPS, weighted empty
  FIFO wall61.93%, late stable windows~69–77%. Build139 had17windows/395frames/
  176.3714seconds=2.2396FPS. Different manual scenes, caches and thermal state:
  do not claim a controlled SHUFB speedup from this comparison alone.
- Last20 kernel samples: Primary SPURS Kernel2/3 each98.1% of a core; Secondary
  Kernel0 95.6%; other SPUs51.0/52.7/71.5%. RSX19.5%, PPU Render Thread14.9%.
  Guest CPU work remains a target; utilization is not instruction throughput.
-117texture upload batches/about3.819GiB,17texture budget passes. No ring growth
  or geometry-batch report, so Build139's watermark remains unexercised on this
  session. Joined28PPU+6SPU;16,951,035,345PPU estimated instructions and
  3,732,758completed HLE/LV2 calls. No SPU dispatch-sampler overhead/logs.

Patch0076-ios-neon-spu-byte-rotate-shifts.patch:
- SPUInterpreter.cpp only, three small inline helpers under ARCH_ARM64 &&
  __APPLE__ && TARGET_OS_IOS. Replace aligned32/64byte temporary arrays and
  a dynamic unaligned stack load with native register-vector lookup paths.
- All nine forms: ROTQBYBI/ROTQMBYBI/SHLQBYBI, ROTQBY/ROTQMBY/SHLQBY,
  ROTQBYI/ROTQMBYI/SHLQBYI. The earlier Build138 trace includes ROTQBY opcodes
  0x3b9325c0 and0x3b8991a5; their decoder index=word>>21=0x1dc. This establishes
  use, not a CPU-time fraction. Do not infer that all SPU time is these ops.
- A lane-number vector0..15 minus byte count (masked15) selects rotation;
  lane+count selects zero-fill right shift; lane-count with unsigned-byte wrap
  selects zero-fill left shift. TBL indices>=16 yield zero, including counts
  16..31. Native register and BYBI>>3/negation/immediate masks remain exact.
- Source operands are evaluated before destination assignment. Preserve all
  RA/RB/RT aliases, return=true, PC/state behavior and non-iOS scalar bodies.
  No guest memory access, heap allocation, table cache, TLS/counter, JIT code,
  floating-point change, decoder switch or guest-work skipping is introduced.
- Arm's primary TBL reference confirms out-of-range zero semantics:
  https://documentation-service.arm.com/static/6245c734b059dc5ff9a8bdab
  (D6.225). This confirms instruction behavior, not a measured game speedup.
- Keep the tested SHUFB change, FIFO parking, geometry/texture lifetime fixes,
  input and null audio. Full mutable-JIT/LLVM work remains separate and must
  not bypass apple_jit_write_protect or enable a decoder with a missing backend.

Validation:
- All76 patches check/apply to exact92b931b9fb5eef7f1317cb482917dfc19aceebd9
  in native142-validation; native whitespace clean; changed Python scripts parse.
- New test_ios_spu_byte_shifts.py reconstructs actual native before/after code,
  verifies scope is limited to three helpers/nine bodies, and compiles real
  v128/SPU opcode/bitfield layouts. Reuses the explicit register-context prefix
  from the shuffle test; Linux models only new NEON vector operations. Existing
  SSE/unaligned-load implementations execute on the host as the golden baseline.
- ASAN+UBSAN, warnings as errors, all five profiles pass: iOS ARM uses the new
  code; macOS ARM/other ARM/iOS x86/Linux x86 keep the old path.224928cases each:
  all128immediates, raw counts0..255 and all mask/zero-fill boundaries, random
  full32bit high counts, all small source/destination alias patterns,20000random
  cases per opcode across128registers. Old/new/independent byte-index oracle
  agree on the full register context, PC and guard; return=true preserved.
- Existing SHUFB test now checks patch0075's source-scope assertion against its
  immediate post-patch source, then tests the current final SHUFB body. Later
  independent instruction patches no longer falsely fail a whole-file check.
  Its five profiles and captured Apple tbl.16b parser regressions pass.
- Historical SPU entry/missing mutable-JIT API rejection and frozen120stage/
  four-stage Quickstart Build142 fixture pass. No unrelated native code change.
- Workflow adds host byte-shift regression and actual Xcode iOS16/apple-a15
  assembly validation before FFmpeg/core compile. Require one TBL in each of
  nine new bodies, no scalar LDRB and no SP/x29 stack memory access. Same accepted
  Apple/GNU mnemonic spellings as the repaired shuffle check. No local Apple SDK:
  these codegen checks/full linked build and real phone effect remain pending.
  All34+2 prerequisites retained. No agents/images. No promised FPS gain.

Next publish142 with lease8382c22..., verify installable workflow queued ONCE,
DO NOT monitor. User authorizes publication/builds. Install
ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start game, same slow3Dmenu/car
screen about60seconds, Stop, share log/responsiveness. Check frame progress,
HOST CPU/RSX FIFO wall and any geometry batches/OOM. Driving remains unconfirmed.


## Build143 — accept Xcode's scalar byte read of the SPU shift count

User reported Workflow failed for Build142. Parent main
 d37aeefbd2389b6869f2d3be3cf1824406f7e1eb, tree
 d3d303f78955ad2ecf7bcfd47a654122770a5086.
Run38844716162, core job116792967183, failed step10:
Verify A15 SPU byte rotate and shift code generation. All host prerequisite
jobs and the preceding real SHUFB A15 assembly check succeeded.

Actual failure: isolated Xcode16.4 iOS16/apple-a15 C++ compilation completed;
Python line122 rejected LDRB in the first ROTQBYBI body. The emitted code has
one tbl.16b and no stack memory. Xcode narrowed the scalar RB word3 count read
into `ldrb w9, [x9, #12]`; x9 is gpr(RB), computed from x0 plus RB shifted4.
ROTQBYBI only uses RB bits3..6, so a low-byte count read is valid. Other
register-count forms use at most RB bits0..7. This is not scalar loading of
sixteen payload bytes. No compiler/native correctness failure was observed;
the old assertion was too strict. Full core compile/link had not started.

Build143 changes validation, app build number and docs only. Native patch0076
and all76 patches are identical to Build142; no performance change is claimed.
- New verify_a15_assembly requires the named function and its cfi_endproc,
  exactly one Apple tbl.16b or GNU tbl, and no SP/x29 stack-memory access.
- The six register-count variants may contain zero or one scalar LDRB with
  word3 offset12; extra/misplaced byte loads fail. The three immediate-count
  variants permit none. Wider scalar count loads are also valid.
- Captured actual failed ROTQBYBI body is tests/fixtures/
  a15-spu-rotqbybi-xcode16_4.txt. The symbol/end delimiters are restored and
  labeled as such because the assertion printed only the function body.
- Parser regression accepts captured Apple/GNU spellings and a wider scalar
  count load. Exercises all nine load policies; rejects missing/wrong-width/
  duplicate TBL, extra/wrong-offset byte loads, stack access, missing target
  and missing function end. Later unrelated functions are outside its scope.

Local validation143:
- Full test_ios_spu_byte_shifts.py passes ASAN+UBSAN/warnings-as-errors in all
  five profiles,224928cases per profile, using exact native before/after bodies
  and real layouts with modeled NEON. Captured assembly parser regressions pass.
- test_p114_fixture.py passes frozen bridge/120ordered stages, four-stage
  Quickstart/cancellable frontend and Build143/iOS16/34+2 workflow dependencies.
- Existing SHUFB captured Apple/GNU parser check, Python syntax and whitespace
  checks pass. No native source edit; no need to repeat unrelated native suites.
- No local Apple SDK. Corrected full nine-function real codegen assertions and
  the complete iOS archive/link still require the newly queued workflow.

Latest device evidence remains Build141,2058presents/clean Stop and slow manual
windows2.60FPS; see Build142 notes. There is no Build142 phone result.
Next publish143 with lease d37aeef..., check installable workflow queued ONCE,
then DO NOT monitor. User authorizes publication/builds. No agents/images.
Once ready install ARMSX3_iOS16_INSTALL_THIS_IPA, Quick start -> Start game,
same slow3Dmenu/car screen about60seconds, Stop and share log/responsiveness.
Driving remains unconfirmed. No promised FPS gain.


## Build144 — bounded texture-cache budget eviction after Build143 menu stalls

User: Hung up at the main menu. Read all three local attachments directly:
ARMSX3-startup-20261016-110928-953-43434.txt,
ARMSX3CoreLoadTest.cpu_resource-2026-10-16-130900.ips,
ARMSX3CoreLoadTest.wakeups_resource-2026-10-16-130724.ips.
Phone Build143/PID43434; parent main9912ca04a28c4181081f54ce8553b15f50a3cf03,
tree9e461956c1c794fc668349c5ece90914529f73c0; installable run38845617965.

Evidence:
- Game runs1792148842.371123; early presents advance~30FPS. By8912.560938 the
  count1846 advances only to1898 by8957.720017. Four complete slow RSX windows:
  47frames/42.0021seconds=1.119FPS. Draw setup25.9–44.1%, texture lookup26.1–31.9%,
  empty FIFO7.0–17.9%. This run has substantially more active renderer work than
  the older mostly-empty-FIFO sessions; do not blindly attribute it all to SPU.
-61texture-cache budget passes,462completed32MiB-ish upload batches/14.6577GiB.
  Last45.6357seconds alone58passes/13.8619GiB. Typical sweep288MiB ->37–41MiB.
  Repeated whole-cache invalidation/reupload is directly supported by logs/source.
- User Stop8958.164470; RSX final8958.168663; shader workers continue compiling
  during join; device/instance8967.148197; FXO8967.249435; VM8967.252295;
  fully stopped zero CPU threads8967.255678; RENDER/UI PASS8967.257575/8967.264370.
  Final1900accepted presents;28PPU+6SPU joined;11,600,254,541 estimated PPU
  instructions/2,152,296completed HLE/LV2 calls. No OOM/fatal/unclean teardown.
  Respect the reported perceived hang; log proves very slow continuing progress,
  not its exact visible appearance or input behavior. Cleanup took9.09seconds.
- Both IPS files say Action taken:none. Wakeups45001/5.833seconds~7714/s; CPU
  report90CPU-seconds/97.76seconds, footprint211.97->1121.36MB. These are resource
  reports, not an observed iOS kill. Do not disable resource protection or infer
  a deadlocked UIKit thread from them. SPUs remain highly utilized in host data.
- Downloaded matching Build143 core symbols artifact12023362763; SHA256
  d5e6d53a9f4fd62743fccd9659d523e537326932afb27dd8c2ffe7f7e39b2bdf.
  UUID8E333E75-5F7C-3D53-A13D-983EB59C9D79 matches the resource-report core image.
  Local symbols143 Mach-O symbol table maps offsets0x274ba4 to SPU old_interpreter,
 0x25c9c0 to RDCH,0x299798 to get_ch_value,0x859c84 to RSX semaphore_acquire,
 0xa0bea8 to load_texture_env,0xab4418 to upload_image_from_cpu and0xab3e54 to
  create_new_texture. Reports span startup/intro as well as menu; samples alone
  do not establish a new interpreter correctness defect. The other unknown UUID
  in stacks was not identified; do not invent its function names.

Patch0077-ios-bound-texture-budget-eviction.patch, three native files only:
- Add iOS-only atomic recent-view tag to vk::cached_texture_section, updated
  by exact get_view/get_raw_view with existing monotonic rsx::get_shared_tag().
  No new sampling thread, guest-state probe, cache-hit logging or JIT changes.
- New iOS common function template evict_unused_budgeted(exclusions,target,bytes)
  try-locks native cache mutex and considers clean, existing, managed shader-read/
  blit-source sections outside active-address exclusions. Sort by recent-view tag
  and stop once selected actual GPU allocation sizes reach the requested bytes.
- Preserve all retained page protections: refuse a candidate sharing locked pages
  with ANY other locked section, including an active texture/FBO at a different
  base address. This conservative check avoids using bulk unprotect_set without
  its required complete overlap exclusions. Native region.unprotect()/discard()
  handles individual independent pages/hash sections. Set dirty AFTER unlocking
  so unreleased accounting updates for blit sources as well as shader textures.
- Same288MiB soft quota/watermark;256MiB target. Preflight remains before sampler/
  cache locks at existing draw/blit boundaries and skips uninterruptible/flushing/
  deadlock states. Trim completed idle images to0 when pressure is checked. If
  still above quota, hard-sync GPU, drain GC, trim newly completed idle images,
  then recheck before choosing any content victim.
- Preserve native secondary-before-cache lock order and all current fragment/
  vertex guest-address exclusions. Byte weights use image->memory->size(), not
  compressed guest section lengths. Purge selected unreleased sections through
  native APIs, perform retirement fence and driver drain, THEN trim completed
  idle allocations and mark samplers dirty. Failed waits never free GPU-owned data.
- Retain16MiB check hysteresis for unreclaimable/pinned sets; add marker
  iOS: bounded texture-cache pass beforeM -> afterM; selected=M.
- Existing on_vram_exhausted emergency callback, whole-cache emergency eviction,
  allocation quotas and recovery paths are byte-for-byte unchanged. No increased
  memory cap, lower texture/resolution quality or relaxed ownership/protection.
  A scene larger than the cache may still churn; physical phone benefit is unknown.

Validation144:
- All77patches check/apply to pin92b931b9fb5eef7f1317cb482917dfc19aceebd9 in
  native144-validation. Patch77 reverses to exact indexed Build143 sources,
  reapplies cleanly; native whitespace and changed Python syntax pass.
- New test_ios_texture_budget.py reconstructs actual native current methods and
  compiles bounded selection, view tags, quota, idle trim and renderer preflight
  under ASAN+UBSAN/warnings-as-errors for iOS and desktop, plus historical policy.
  Explicit host GPU/storage/VM/GC interfaces, not a real Metal game benchmark.
- Modeled304MiB initial cache contains128MiB old scene and176MiB warm scene.
  New policy removes48MiB older content, retains all warm pixels across120frames;
  historical whole-cache policy reuploads160MiB.8GiB streaming peak304MiB includes
  original16MiB check hysteresis; active vertex/fragment references survive.
- Cover recent raw-view rebinding, dirty/borrowed/FBO/blit-destination exclusions,
  eligible blit sources, hash-only sections, target0/oversized object, mutex
  refusal, shared pages between textures AND FBOs, delayed GC, idle-only pressure,
  newly completed idle pressure, pinned-set backoff, skip gates and failures of
  first/second GPU fence. No freed image is still marked GPU-owned in the model.
- Historical Build134 reuse test now explicitly reconstructs patches1..68 so its
  previous policy remains reproducible. It passes completion-only/concurrent idle
  retirement and the original200MiB scene/old192MiB negative comparison.
- Production runtime/Stop/failure/config restoration, upload retirement/failure
  regressions and Build144120-stage/four-foundation fixture pass. CMake is absent
  locally: broader test_native_renderer.py passes its native present/extension
  fragment then cannot start the CMake importer check. That test remains required
  in Actions; no missing-dependency workaround/false pass was added.
- Workflow adds current budget test to intake; all34+2 prerequisites retained.
  Real Xcode compilation/full linked IPA and phone validation remain pending.

Next publish144 with lease9912ca0..., verify installable workflow queued ONCE,
DO NOT monitor. User authorizes publication/builds; no agents/images. Once ready,
install ARMSX3_iOS16_INSTALL_THIS_IPA; Quick start -> Start game; same menu/car
screen about60seconds; Stop and share log/responsiveness. Check new bounded-pass
sizes/frequency, upload totals, FIFO/draw/texture timing, frame progress and OOM.
Keep SPU vector paths/FIFO parking/input/graphics; null audio unchanged. Driving
unconfirmed. No claimed or promised device FPS gain from host cache models.


## Build145 — revert Build144 after device graphics regression

User reports very glitchy graphics with roughly unchanged FPS. Evidence:
ARMSX3-startup-20261016-114840-742-43835.txt, build144/PID43835.
Two complete slow RSX windows: 20 frames/10.2433s and 18/10.4024s
(~1.84 FPS combined); final partial window 18/9.7626s. These manual
sessions are not a controlled benchmark. 1686 accepted presents and clean
Stop with zero live CPU threads do not validate visual correctness.
Bounded cache passes start at 292MiB and later reach 418MiB before a pass,
with retained usage approaching 402MiB despite the nominal 288MiB quota.
The precise stale texture/graphics corruption mechanism is NOT established.

Recovery: remove patch0077 and its policy-specific test/workflow invocation;
restore texture reuse validation and all production patch inputs exactly to
Build143. Preserve patches1..76, SPU vector optimizations, input and runtime.
Build number145 and fixture updated. No new performance optimization bundled.
Build144 analysis stays above for history; its policy is no longer active.

Validate fixture and byte-for-byte Build143 production-patch/workflow parity.
Publish once and verify workflow queued; do not monitor. Phone confirmation
required: Quick start -> Start game, same menu about60seconds, Stop and share
log plus whether graphics are restored. No promised FPS improvement. Once
visual baseline is recovered, investigate FIFO/SPU bottleneck separately.

Local validation passed: Build145 fixture, diff whitespace check, exact Build143
76-patch/workflow/reuse-test parity. Full iOS CI and phone test pending.

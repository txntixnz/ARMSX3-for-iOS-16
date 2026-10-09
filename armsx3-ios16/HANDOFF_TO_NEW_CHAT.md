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

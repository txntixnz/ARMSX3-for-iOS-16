// SPDX-License-Identifier: GPL-2.0-only
#import <UIKit/UIKit.h>
#import <QuartzCore/CAMetalLayer.h>
#import <Metal/Metal.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#include <dlfcn.h>
#include <cstdio>
#include <atomic>
#include "StartupLog.h"
#include "LogExport.h"

// UIKit writes only this cancellation flag. The runtime worker owns teardown.
static std::atomic<bool> renderStopRequested{false};
static int renderShouldStop(void* context) {
    return static_cast<std::atomic<bool>*>(context)->load(std::memory_order_relaxed) ? 1 : 0;
}

struct DiagnosticStage { unsigned phase; const char* title; const char* symbol; };
static constexpr DiagnosticStage stages[] = {
    {2, "Load emulator core", "armsx3_core_state"},
    {3, "Core JIT execution", "armsx3_core_test_immutable_jit"},
    {4, "Initialize emulator", "armsx3_core_initialize"},
    {5, "PS3 guest memory", "armsx3_core_test_guest_memory"},
    {6, "PPU instructions", "armsx3_core_test_ppu_instructions"},
    {7, "PPU branches and loops", "armsx3_core_test_ppu_control_flow"},
    {8, "SPU instructions", "armsx3_core_test_spu_instructions"},
    {9, "SPU DMA transfers", "armsx3_core_test_spu_dma"},
    {10, "SPU DMA channels and tags", "armsx3_core_test_spu_channels"},
    {11, "SPU DMA queue and ordering", "armsx3_core_test_spu_queue"},
    {12, "SPU channel instructions", "armsx3_core_test_spu_channel_instructions"},
    {13, "Core threads and wait/wake", "armsx3_core_test_thread_waits"},
    {14, "Stopped PPU thread lifecycle", "armsx3_core_test_ppu_lifecycle"},
    {15, "PPU worker instructions", "armsx3_core_test_ppu_worker_instructions"},
    {16, "Persistent PPU queue wait/wake", "armsx3_core_test_ppu_queue_wake"},
    {17, "PPU guest fetch and dispatch", "armsx3_core_test_ppu_dispatch"},
    {18, "ELF parsing and loaded PPU code", "armsx3_core_test_elf_execution"},
    {19, "Core code registration and decode", "armsx3_core_test_registered_elf"},
    {20, "Executable analysis and preparation", "armsx3_core_test_analyzed_elf"},
    {21, "ELF function call and stack return", "armsx3_core_test_elf_call"},
    {22, "ELF fixed segments and rollback", "armsx3_core_test_elf_fixed_segments"},
    {23, "Protected ELF code and data store", "armsx3_core_test_elf_protected_code"},
    {24, "Production HLE table and ELF return", "armsx3_core_test_elf_hle_table"},
    {25, "ELF imports and linked HLE branch", "armsx3_core_test_elf_import_linkage"},
    {26, "PRX export descriptor discovery", "armsx3_core_test_elf_export_discovery"},
    {27, "PRX registration and import backpatch", "armsx3_core_test_elf_export_registration"},
    {28, "Linked guest function call and return", "armsx3_core_test_linked_guest_call"},
    {29, "Production ELF segment loading", "armsx3_core_test_production_elf_segments"},
    {30, "Loaded ELF PRX linkage and guest call", "armsx3_core_test_loaded_elf_linkage"},
    {31, "Executable arguments and entry registers", "armsx3_core_test_executable_arguments"},
    {32, "TLS memory bootstrap and guest read", "armsx3_core_test_tls_bootstrap"},
    {33, "ELF TLS header and guest bootstrap", "armsx3_core_test_elf_tls_header"},
    {34, "Executable process parameters and worker", "armsx3_core_test_process_parameters"},
    {35, "Guest syscalls and worker services", "armsx3_core_test_guest_syscalls"},
    {36, "Guest priority query and validation", "armsx3_core_test_priority_syscalls"},
    {37, "Guest priority change and restoration", "armsx3_core_test_priority_change"},
    {38, "Single-worker scheduler queue and priority", "armsx3_core_test_scheduler_queue"},
    {39, "Two-worker scheduler priority ordering", "armsx3_core_test_scheduler_pair"},
    {40, "Guest yield and FIFO scheduler ordering", "armsx3_core_test_scheduler_yield"},
    {41, "Guest current time and timebase frequency", "armsx3_core_test_guest_time"},
    {42, "Guest timebase full and upper reads", "armsx3_core_test_guest_timebase"},
    {43, "Guest memory allocation and release", "armsx3_core_test_memory_syscalls"},
    {44, "Guest allocated memory reads and writes", "armsx3_core_test_heap_access"},
    {45, "Guest available memory accounting", "armsx3_core_test_memory_stats"},
    {46, "Guest 1 MiB memory pages", "armsx3_core_test_memory_1m"},
    {47, "Guest live and freed page attributes", "armsx3_core_test_page_attributes"},
    {48, "Guest page attribute output errors", "armsx3_core_test_page_attribute_errors"},
    {49, "Guest process PID and ELF SDK", "armsx3_core_test_process_sdk"},
    {50, "Two active PPU workers and budget isolation", "armsx3_core_test_active_ppu_pair"},
    {51, "Persistent PPU pair and budget recovery", "armsx3_core_test_persistent_ppu_pair"},
    {52, "Paired guest TLS allocation and isolation", "armsx3_core_test_paired_guest_tls"},
    {53, "Persistent guest TLS and budget recovery", "armsx3_core_test_persistent_guest_tls"},
    {54, "Paused guest contexts and exact continuation", "armsx3_core_test_resumed_guest_tls"},
    {55, "Nested guest calls and paused stack frames", "armsx3_core_test_resumed_guest_calls"},
    {56, "Paused floating-point and vector guest calls", "armsx3_core_test_resumed_guest_simd"},
    {57, "Paused condition, carry and floating status", "armsx3_core_test_resumed_guest_status"},
    {58, "Guest reservation stores and recovery", "armsx3_core_test_guest_reservation_stores"},
    {59, "Paused reservations and peer writes", "armsx3_core_test_paused_reservations"},
    {60, "Shared reservation competition and retry", "armsx3_core_test_shared_reservation_retry"},
    {61, "Ordered winners and failed retry backedge", "armsx3_core_test_ordered_reservation_backedge"},
    {62, "64-bit reservations, carry and consumed stores", "armsx3_core_test_wide_reservation_carry"},
    {63, "Full-line reservations and peer neighbor writes", "armsx3_core_test_full_line_reservations"},
    {64, "Reservation line targets and outside rejection", "armsx3_core_test_reservation_line_targets"},
    {65, "Guest spinlock and protected worker handoff", "armsx3_core_test_guest_spinlock_handoff"},
    {66, "Production spinlock services and guest calls", "armsx3_core_test_hle_spinlock_handoff"},
    {67, "Blocking spinlock and paused native service", "armsx3_core_test_blocking_spinlock_handoff"},
    {68, "Interrupted lock and native replay fixup", "armsx3_core_test_interrupted_spinlock_replay"},
    {69, "LV2 mutex ownership and lifecycle", "armsx3_core_test_lv2_mutex_ownership"},
    {70, "Recursive mutex depth and partial release", "armsx3_core_test_recursive_mutex_ownership"},
    {71, "Mutex lock service and 64-bit timeout arguments", "armsx3_core_test_mutex_lock_fast_paths"},
    {72, "Contended mutex and native LV2 sleep/wake", "armsx3_core_test_mutex_sleep_wake"},
    {73, "Mutex timeout expiry and fresh acquisition", "armsx3_core_test_mutex_timeout_expiry"},
    {74, "Timed mutex unlock and timer cancellation", "armsx3_core_test_mutex_timed_wake"},
    {75, "Mutex timeout then timed wake on the same object", "armsx3_core_test_mutex_timeout_then_wake"},
    {76, "Semaphore permits and lifecycle services", "armsx3_core_test_semaphore_lifecycle"},
    {77, "Semaphore blocking wait and native post wake", "armsx3_core_test_semaphore_blocking_wake"},
    {78, "Semaphore timeout expiry and permit recovery", "armsx3_core_test_semaphore_timeout_recovery"},
    {79, "Semaphore timeout then requeue and wake", "armsx3_core_test_semaphore_timeout_then_wake"},
    {80, "FIFO semaphore wake and spare permit", "armsx3_core_test_semaphore_fifo_surplus"},
    {81, "Priority semaphore wake and spare permit", "armsx3_core_test_semaphore_priority_surplus"},
    {82, "Event flags: and mode and timed wake", "armsx3_core_test_event_flag_and"},
    {83, "Event flags: or mode and timed wake", "armsx3_core_test_event_flag_or"},
    {84, "Event flags: clear mode and timed wake", "armsx3_core_test_event_flag_clear"},
    {85, "Event flags: clear all mode and timed wake", "armsx3_core_test_event_flag_clear_all"},
    {86, "Condition variables: fifo wait and wake", "armsx3_core_test_cond_fifo"},
    {87, "Condition variables: recursive wait and wake", "armsx3_core_test_cond_recursive"},
    {88, "Condition variables: broadcast wait and wake", "armsx3_core_test_cond_broadcast"},
    {89, "Condition variables: recursive broadcast wait and wake", "armsx3_core_test_cond_recursive_broadcast"},
    {90, "FIFO readers waiting behind a writer", "armsx3_core_test_rwlock_reader_fifo"},
    {91, "Priority readers waiting behind a writer", "armsx3_core_test_rwlock_reader_priority"},
    {92, "FIFO writers waiting behind readers", "armsx3_core_test_rwlock_writer_fifo"},
    {93, "Priority writers waiting behind readers", "armsx3_core_test_rwlock_writer_priority"},
    {94, "FIFO event receive and 64-bit port messages", "armsx3_core_test_event_queue_fifo"},
    {95, "Priority event receive and 64-bit port messages", "armsx3_core_test_event_queue_priority"},
    {96, "FIFO event receive cancellation and port recovery", "armsx3_core_test_event_queue_cancel_fifo"},
    {97, "Priority event receive cancellation and port recovery", "armsx3_core_test_event_queue_cancel_priority"},
    {98, "FIFO PPU queue minimum capacity", "armsx3_core_test_event_object_queue_fifo_min"},
    {99, "Priority PPU queue maximum capacity", "armsx3_core_test_event_object_queue_priority_max"},
    {100, "FIFO SPU queue minimum capacity", "armsx3_core_test_event_object_queue_spu_fifo_min"},
    {101, "Priority SPU queue maximum capacity", "armsx3_core_test_event_object_queue_spu_priority_max"},
    {102, "Named local port creation and lifetime", "armsx3_core_test_event_object_port_local_named"},
    {103, "Unnamed local port creation and lifetime", "armsx3_core_test_event_object_port_local_auto"},
    {104, "Named IPC port creation and lifetime", "armsx3_core_test_event_object_port_ipc_named"},
    {105, "Unnamed IPC port creation and lifetime", "armsx3_core_test_event_object_port_ipc_auto"},
    {106, "IPC ppu fifo named delivery and key reuse", "armsx3_core_test_event_ipc_ppu_fifo_named"},
    {107, "IPC ppu fifo auto delivery and key reuse", "armsx3_core_test_event_ipc_ppu_fifo_auto"},
    {108, "IPC ppu priority named delivery and key reuse", "armsx3_core_test_event_ipc_ppu_priority_named"},
    {109, "IPC ppu priority auto delivery and key reuse", "armsx3_core_test_event_ipc_ppu_priority_auto"},
    {110, "IPC spu fifo named delivery and key reuse", "armsx3_core_test_event_ipc_spu_fifo_named"},
    {111, "IPC spu fifo auto delivery and key reuse", "armsx3_core_test_event_ipc_spu_fifo_auto"},
    {112, "IPC spu priority named delivery and key reuse", "armsx3_core_test_event_ipc_spu_priority_named"},
    {113, "IPC spu priority auto delivery and key reuse", "armsx3_core_test_event_ipc_spu_priority_auto"},
    {114, "Firmware storage and file rename", "armsx3_core_test_intake_storage"},
    {115, "Native PUP header rejection", "armsx3_core_test_intake_pup_headers"},
    {116, "Bounded firmware entry tables", "armsx3_core_test_intake_pup_bounds"},
    {117, "Authenticated PUP entries and version", "armsx3_core_test_intake_pup_authenticated"},
    {118, "Tampered firmware hash rejection", "armsx3_core_test_intake_pup_tamper"},
    {119, "Native TAR extraction to staging", "armsx3_core_test_intake_tar_staging"},
    {120, "Selected executable intake path", "armsx3_core_test_intake_executable_intake"},
    {121, "Firmware publication and rollback", "armsx3_core_test_intake_firmware_publication"},
};
static constexpr NSUInteger stageCount = sizeof(stages) / sizeof(stages[0]);
static NSString* const pendingStageKey = @"ARMSX3PendingDiagnosticStage";

// UIKit owns this layer for the entire native renderer lifetime. No RSX-thread
// UIView reads or main-queue synchronous geometry callbacks are needed.
@interface RenderSurface : UIView
@end
@implementation RenderSurface
+ (Class)layerClass { return CAMetalLayer.class; }
@end
@interface RenderController : UIViewController
@property(nonatomic,strong) RenderSurface* surface;
@property(nonatomic,strong) UILabel* status;
@property(nonatomic,strong) UIButton* stopGameButton;
@property(nonatomic,copy) dispatch_block_t stopAction;
- (void)requestGameStop;
@end
@implementation RenderController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.blackColor;
    self.surface = [[RenderSurface alloc] init];
    self.surface.opaque = YES;
    CAMetalLayer* layer = (CAMetalLayer*)self.surface.layer;
    layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
    layer.framebufferOnly = YES;
    layer.presentsWithTransaction = NO;
    layer.drawableSize = CGSizeMake(1280,720);
    [self.view addSubview:self.surface];
    self.status = [[UILabel alloc] init];
    self.status.textColor = UIColor.whiteColor;
    self.status.numberOfLines = 0;
    self.status.textAlignment = NSTextAlignmentCenter;
    self.status.text = @"Game session · tap Stop game when finished";
    [self.view addSubview:self.status];
    self.stopGameButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.stopGameButton setTitle:@"Stop game" forState:UIControlStateNormal];
    [self.stopGameButton setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    [self.stopGameButton addTarget:self action:@selector(requestGameStop) forControlEvents:UIControlEventTouchUpInside];
    [self.view addSubview:self.stopGameButton];
}
- (void)requestGameStop {
    self.stopGameButton.enabled = NO;
    self.status.text = @"Stopping game… waiting for cleanup";
    if (self.stopAction) self.stopAction();
}
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    const CGRect area = UIEdgeInsetsInsetRect(self.view.bounds,self.view.safeAreaInsets);
    const CGFloat width = MIN(area.size.width, MAX(1,area.size.height - 80) * 16.0 / 9.0);
    const CGFloat height = width * 9.0 / 16.0;
    self.surface.frame = CGRectMake(CGRectGetMidX(area) - width/2,CGRectGetMidY(area) - height/2,width,height);
    ((CAMetalLayer*)self.surface.layer).drawableSize = CGSizeMake(1280,720);
    self.status.frame = CGRectMake(area.origin.x + 12,CGRectGetMaxY(area) - 72,MAX(1,area.size.width - 148),70);
    self.stopGameButton.frame = CGRectMake(CGRectGetMaxX(area) - 128,CGRectGetMaxY(area) - 64,116,54);
}
@end

@interface LoadController : UIViewController <UIDocumentPickerDelegate>
@property(nonatomic,strong) UITextView* output;
@property(nonatomic,strong) UILabel* progressLabel;
@property(nonatomic,strong) UIProgressView* progress;
@property(nonatomic,strong) UIButton* runButton;
@property(nonatomic,strong) UIButton* quickButton;
@property(nonatomic,assign) BOOL quickMode;
@property(nonatomic,assign) BOOL foundationReady;
@property(nonatomic,strong) UIButton* nextButton;
@property(nonatomic,strong) UIButton* stopButton;
@property(nonatomic,strong) UIButton* shareButton;
@property(nonatomic,strong) UIButton* resultsCopyButton;
@property(nonatomic,strong) UIButton* firmwareButton;
@property(nonatomic,strong) UIButton* executableButton;
@property(nonatomic,strong) UIButton* runtimeButton;
@property(nonatomic,strong) UIButton* gameButton;
@property(nonatomic,strong) UIButton* gameLoadButton;
@property(nonatomic,strong) UIButton* gameRunButton;
@property(nonatomic,strong) UIButton* graphicsButton;
@property(nonatomic,strong) UIButton* renderButton;
@property(nonatomic,strong) RenderController* renderController;
@property(nonatomic,assign) BOOL intakeBusy;
@property(nonatomic,assign) NSInteger intakeMode;
@property(nonatomic,assign) BOOL previousRunPending;
@property(nonatomic,assign) void* coreHandle;
@property(nonatomic,assign) NSUInteger nextStage;
@property(nonatomic,assign) BOOL running;
@property(nonatomic,assign) BOOL runAll;
@property(nonatomic,assign) BOOL stopRequested;
@property(nonatomic,assign) BOOL failed;
@property(nonatomic,assign) BOOL previousIdleTimerDisabled;
@property(nonatomic,strong) NSMutableString* transcript;
- (void)runCurrentStage;
- (void)completeStage:(NSUInteger)index result:(int)result detail:(NSString*)detail;
- (void)refreshControls;
@end
@implementation LoadController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    self.title = @"ARMSX3";
    self.transcript = [NSMutableString string];
    UIStackView* stack = [[UIStackView alloc] init];
    stack.axis = UILayoutConstraintAxisVertical;
    stack.spacing = 16;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[
        [stack.leadingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.leadingAnchor constant:20],
        [stack.trailingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.trailingAnchor constant:-20],
        [stack.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor constant:20],
        [stack.bottomAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.bottomAnchor constant:-20]]];
    self.quickButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.quickButton setTitle:@"Quick start" forState:UIControlStateNormal];
    [self.quickButton addTarget:self action:@selector(startQuick) forControlEvents:UIControlEventTouchUpInside];
    self.runButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.runButton setTitle:@"Run all tests" forState:UIControlStateNormal];
    [self.runButton addTarget:self action:@selector(startAll) forControlEvents:UIControlEventTouchUpInside];
    UIStackView* startControls = [[UIStackView alloc] initWithArrangedSubviews:@[self.quickButton,self.runButton]];
    startControls.distribution = UIStackViewDistributionFillEqually;
    startControls.spacing = 12;
    [stack addArrangedSubview:startControls];
    self.progressLabel = [[UILabel alloc] init];
    self.progressLabel.numberOfLines = 0;
    self.progressLabel.text = [NSString stringWithFormat:@"Ready · %lu tests", (unsigned long)stageCount];
    [stack addArrangedSubview:self.progressLabel];
    self.progress = [[UIProgressView alloc] initWithProgressViewStyle:UIProgressViewStyleDefault];
    [stack addArrangedSubview:self.progress];
    self.nextButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.nextButton setTitle:@"Run next test only" forState:UIControlStateNormal];
    [self.nextButton addTarget:self action:@selector(startNext) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.nextButton];
    self.stopButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.stopButton setTitle:@"Stop after current test" forState:UIControlStateNormal];
    [self.stopButton addTarget:self action:@selector(requestStop) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.stopButton];
    self.shareButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.shareButton setTitle:@"Share log (.txt)" forState:UIControlStateNormal];
    [self.shareButton addTarget:self action:@selector(shareLog) forControlEvents:UIControlEventTouchUpInside];
    self.resultsCopyButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.resultsCopyButton setTitle:@"Copy results" forState:UIControlStateNormal];
    [self.resultsCopyButton addTarget:self action:@selector(copyResults) forControlEvents:UIControlEventTouchUpInside];
    UIStackView* logControls = [[UIStackView alloc] initWithArrangedSubviews:@[self.shareButton, self.resultsCopyButton]];
    logControls.distribution = UIStackViewDistributionFillEqually;
    logControls.spacing = 12;
    [stack addArrangedSubview:logControls];
    self.firmwareButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.firmwareButton setTitle:@"Install firmware" forState:UIControlStateNormal];
    [self.firmwareButton addTarget:self action:@selector(selectFirmware) forControlEvents:UIControlEventTouchUpInside];
    self.executableButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.executableButton setTitle:@"Inspect EBOOT / ELF" forState:UIControlStateNormal];
    [self.executableButton addTarget:self action:@selector(selectExecutable) forControlEvents:UIControlEventTouchUpInside];
    UIStackView* intakeControls = [[UIStackView alloc] initWithArrangedSubviews:@[self.firmwareButton,self.executableButton]];
    intakeControls.distribution = UIStackViewDistributionFillEqually; intakeControls.spacing = 12;
    [stack addArrangedSubview:intakeControls];
    self.runtimeButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.runtimeButton setTitle:@"Check runtime load" forState:UIControlStateNormal];
    [self.runtimeButton addTarget:self action:@selector(checkRuntime) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.runtimeButton];
    self.gameButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.gameButton setTitle:@"Import game folder" forState:UIControlStateNormal];
    [self.gameButton addTarget:self action:@selector(selectGame) forControlEvents:UIControlEventTouchUpInside];
    self.gameLoadButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.gameLoadButton setTitle:@"Check game load" forState:UIControlStateNormal];
    [self.gameLoadButton addTarget:self action:@selector(checkGame) forControlEvents:UIControlEventTouchUpInside];
    UIStackView* gameControls = [[UIStackView alloc] initWithArrangedSubviews:@[self.gameButton,self.gameLoadButton]];
    gameControls.distribution = UIStackViewDistributionFillEqually; gameControls.spacing = 12;
    [stack addArrangedSubview:gameControls];
    self.gameRunButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.gameRunButton setTitle:@"Run game (3 seconds)" forState:UIControlStateNormal];
    [self.gameRunButton addTarget:self action:@selector(runGame) forControlEvents:UIControlEventTouchUpInside];
    self.graphicsButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.graphicsButton setTitle:@"Check graphics device" forState:UIControlStateNormal];
    [self.graphicsButton addTarget:self action:@selector(checkGraphics) forControlEvents:UIControlEventTouchUpInside];
    UIStackView* executionControls = [[UIStackView alloc] initWithArrangedSubviews:@[self.gameRunButton,self.graphicsButton]];
    executionControls.distribution = UIStackViewDistributionFillEqually; executionControls.spacing = 12;
    [stack addArrangedSubview:executionControls];
    self.renderButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.renderButton setTitle:@"Start game" forState:UIControlStateNormal];
    [self.renderButton addTarget:self action:@selector(renderGame) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.renderButton];
    self.output = [[UITextView alloc] init];
    self.output.editable = NO;
    self.output.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    self.output.text = @"Tap Quick start for four foundation checks, then Start game. Run all tests remains available for full diagnostics.\n\nWhen finished, share the .txt log or tap Copy results and paste into chat. Quick start or the full tests enable firmware, game and graphics actions.";
    [stack addArrangedSubview:self.output];
    NSString* pending = [NSUserDefaults.standardUserDefaults stringForKey:pendingStageKey];
    if (pending.length) {
        self.previousRunPending = YES;
        self.output.text = [NSString stringWithFormat:@"Previous run did not finish: %@.\n\nShare log or Copy results includes that previous run until you start testing again. Run all tests starts a fresh sequence in this process. Quick start or the full tests enable firmware, game and graphics actions.", pending];
    }
    [self refreshControls];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(enteredBackground:)
        name:UIApplicationDidEnterBackgroundNotification object:nil];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(sessionWillResignActive:)
        name:UIApplicationWillResignActiveNotification object:nil];
    ARMSX3StartupLog("AUTO UI ready; one-tap ordered diagnostics available; no test starts without a tap");
}
- (void)dealloc {
    [NSNotificationCenter.defaultCenter removeObserver:self];
}
- (void)refreshControls {
    const BOOL available = !self.running && !self.intakeBusy && !self.failed && self.nextStage < stageCount;
    self.quickButton.enabled = available && !self.foundationReady && self.nextStage < 4;
    self.runButton.enabled = available;
    self.nextButton.enabled = available;
    self.stopButton.enabled = self.running && self.runAll && !self.stopRequested;
    self.shareButton.enabled = !self.running && !self.intakeBusy;
    self.resultsCopyButton.enabled = !self.running && !self.intakeBusy;
    const BOOL intakeReady = self.coreHandle && !self.running && !self.intakeBusy && !self.failed && (self.foundationReady || self.nextStage == stageCount);
    self.firmwareButton.enabled = intakeReady; self.executableButton.enabled = intakeReady;
    self.runtimeButton.enabled = intakeReady;
    self.gameButton.enabled = intakeReady; self.gameLoadButton.enabled = intakeReady;
    self.gameRunButton.enabled = intakeReady;
    self.graphicsButton.enabled = intakeReady;
    self.renderButton.enabled = intakeReady;
    [self.runButton setTitle:self.nextStage ? @"Run remaining tests" : @"Run all tests" forState:UIControlStateNormal];
    self.progress.progress = float(self.nextStage) / float(stageCount);
}
- (void)startQuick {
    if (self.running || self.intakeBusy || self.failed || self.foundationReady || self.nextStage >= 4) return;
    [self startSequence:YES];
    self.quickMode = YES;
    ARMSX3StartupLog("QUICK foundation checks requested; full diagnostics remain optional");
}
- (void)startAll { [self startSequence:YES]; }
- (void)startNext { [self startSequence:NO]; }
- (void)startSequence:(BOOL)all {
    if (self.running || self.intakeBusy || self.failed || self.nextStage >= stageCount) return;
    self.running = YES;
    self.quickMode = NO;
    self.previousRunPending = NO;
    self.runAll = all;
    self.stopRequested = NO;
    self.previousIdleTimerDisabled = UIApplication.sharedApplication.idleTimerDisabled;
    UIApplication.sharedApplication.idleTimerDisabled = YES;
    ARMSX3StartupLog(all ? "AUTO user requested ordered diagnostic sequence" : "AUTO user requested one diagnostic stage");
    [self refreshControls];
    [self runCurrentStage];
}
- (void)requestStop {
    if (!self.running) return;
    self.stopRequested = YES;
    self.progressLabel.text = @"Stopping after the current test…";
    ARMSX3StartupLog("AUTO stop requested; current test will finish before pausing");
    [self refreshControls];
}
- (void)sessionWillResignActive:(NSNotification*)notification {
    (void)notification;
    if (self.renderController && self.intakeBusy) [self.renderController requestGameStop];
}
- (void)enteredBackground:(NSNotification*)notification {
    (void)notification;
    if (self.running) [self requestStop];
}
- (void)finishSequence {
    self.running = NO;
    UIApplication.sharedApplication.idleTimerDisabled = self.previousIdleTimerDisabled;
    [self refreshControls];
}
- (void)pauseSequence {
    ARMSX3StartupLog("AUTO paused after completed stage; remaining stages can resume in this process");
    [self.transcript appendString:@"\nPaused. Tap Run remaining tests to continue.\n"];
    self.output.text = self.transcript;
    self.progressLabel.text = [NSString stringWithFormat:@"Paused · %lu / %lu passed", (unsigned long)self.nextStage, (unsigned long)stageCount];
    [self finishSequence];
}
- (void)runCurrentStage {
    if (self.stopRequested) { [self pauseSequence]; return; }
    // All runner state is accessed on the UIKit main queue. Only one core test
    // is outstanding; the next stage starts after its result returns here.
    const NSUInteger index = self.nextStage;
    const auto& stage = stages[index];
    NSString* label = [NSString stringWithFormat:@"P%u · %s", stage.phase, stage.title];
    self.progressLabel.text = [NSString stringWithFormat:@"%lu / %lu · %@", (unsigned long)(index + 1), (unsigned long)stageCount, label];
    [self.transcript appendFormat:@"RUN %@\n", label];
    self.output.text = self.transcript;
    [self.output scrollRangeToVisible:NSMakeRange(self.output.text.length, 0)];
    // Save the pending stage before calling code that could close the process.
    [NSUserDefaults.standardUserDefaults setObject:label forKey:pendingStageKey];
    [NSUserDefaults.standardUserDefaults synchronize];
    ARMSX3StartupLog([NSString stringWithFormat:@"AUTO BEFORE %@ (%lu/%lu)", label, (unsigned long)(index + 1), (unsigned long)stageCount].UTF8String);
    if (index == 0) {
        // Keep dlopen on the same main-thread path as the validated manual app.
        // Yield once so UIKit can present the progress before core constructors.
        dispatch_async(dispatch_get_main_queue(), ^{
            NSString* path = [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"Frameworks/libARMSX3Core.dylib"];
            void* handle = dlopen(path.fileSystemRepresentation, RTLD_NOW | RTLD_LOCAL);
            if (!handle) {
                const char* error = dlerror();
                [self completeStage:index result:-1 detail:[NSString stringWithUTF8String:error ?: "dlopen failed"]];
                return;
            }
            self.coreHandle = handle; // Keep loaded for process lifetime.
            auto state = reinterpret_cast<int (*)()>(dlsym(handle, stages[index].symbol));
            if (!state) {
                [self completeStage:index result:-1 detail:@"Core state export missing"];
                return;
            }
            const int result = state();
            [self completeStage:index result:result detail:result == 0 ? nil : @"Core must be stopped"];
        });
        return;
    }
    auto test = reinterpret_cast<int (*)()>(dlsym(self.coreHandle, stage.symbol));
    if (!test) {
        [self completeStage:index result:-1 detail:[NSString stringWithFormat:@"Missing export: %s", stage.symbol]];
        return;
    }
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        const int result = test();
        dispatch_async(dispatch_get_main_queue(), ^{
            [self completeStage:index result:result detail:nil];
        });
    });
}
- (void)completeStage:(NSUInteger)index result:(int)result detail:(NSString*)detail {
    const auto& stage = stages[index];
    NSString* label = [NSString stringWithFormat:@"P%u · %s", stage.phase, stage.title];
    if (result != 0) {
        self.failed = YES;
        NSString* message = [NSString stringWithFormat:@"FAIL %@ (%d)%@", label, result,
            detail.length ? [@": " stringByAppendingString:detail] : @""];
        ARMSX3StartupLog(message.UTF8String);
        [self.transcript appendFormat:@"%@\n\nStopped. Share the startup log. Reopen the app before testing again.\n", message];
        self.output.text = self.transcript;
        self.progressLabel.text = [NSString stringWithFormat:@"Stopped · %@ failed", label];
        // Keep the failed stage marker for the next launch.
        [self finishSequence];
        return;
    }
    ARMSX3StartupLog([NSString stringWithFormat:@"AUTO PASS %@", label].UTF8String);
    [NSUserDefaults.standardUserDefaults removeObjectForKey:pendingStageKey];
    [NSUserDefaults.standardUserDefaults synchronize];
    [self.transcript appendFormat:@"PASS %@\n", label];
    self.nextStage = index + 1;
    [self refreshControls];
    if (self.quickMode && self.nextStage == 4) {
        self.foundationReady = YES;
        self.quickMode = NO;
        ARMSX3StartupLog("QUICK PASS: four foundation checks completed; remaining diagnostics were not run");
        [self.transcript appendString:@"\nQuick start passed. Tap Start game; full diagnostics are optional.\n"];
        self.output.text = self.transcript;
        self.progressLabel.text = @"Ready · Start game available";
        [self finishSequence];
    } else if (self.nextStage == stageCount) {
        ARMSX3StartupLog("AUTO PASS: all diagnostic stages completed; game boot remains untested");
        [self.transcript appendFormat:@"\nAll %lu tests passed. Share the startup log.\nQuick start or the full tests enable firmware, game and graphics actions.\n", (unsigned long)stageCount];
        self.output.text = self.transcript;
        self.progressLabel.text = [NSString stringWithFormat:@"All %lu tests passed", (unsigned long)stageCount];
        [self finishSequence];
    } else if (self.runAll && !self.stopRequested) {
        self.output.text = self.transcript;
        // Yield to UIKit between stages; never run two tests concurrently.
        dispatch_async(dispatch_get_main_queue(), ^{ [self runCurrentStage]; });
    } else {
        [self pauseSequence];
    }
}
- (void)showLogMessage:(NSString*)title detail:(NSString*)detail {
    UIAlertController* alert = [UIAlertController alertControllerWithTitle:title message:detail preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
    [self presentViewController:alert animated:YES completion:nil];
}
- (void)selectFirmware { [self selectIntake:1]; }
- (void)selectExecutable { [self selectIntake:2]; }
- (void)selectGame { [self selectIntake:3]; }
- (void)checkRuntime { [self checkRuntimeMode:NO execute:NO]; }
- (void)checkGame { [self checkRuntimeMode:YES execute:NO]; }
- (void)runGame { [self checkRuntimeMode:YES execute:YES]; }
- (void)renderGame {
    if (self.running || self.intakeBusy || self.failed || (!self.foundationReady && self.nextStage != stageCount) || !self.coreHandle) return;
    auto action = reinterpret_cast<int (*)(void*,unsigned,unsigned,int (*)(void*),void*,char*,size_t)>(dlsym(self.coreHandle,"armsx3_core_render_session"));
    if (!action) { [self showLogMessage:@"Rendering unavailable" detail:@"The native rendering function is missing."]; return; }
    self.intakeBusy = YES; self.previousRunPending = NO;
    const BOOL previousIdle = UIApplication.sharedApplication.idleTimerDisabled;
    UIApplication.sharedApplication.idleTimerDisabled = YES;
    renderStopRequested.store(false, std::memory_order_relaxed);
    [NSUserDefaults.standardUserDefaults setObject:@"Game session (Stop game to finish)" forKey:pendingStageKey];
    [NSUserDefaults.standardUserDefaults synchronize];
    [self.transcript appendString:@"\nRUN · Game session, 1280×720, Stop game to finish\n"];
    self.output.text = self.transcript;
    self.progressLabel.text = @"Starting native Vulkan renderer…";
    RenderController* display = [[RenderController alloc] init];
    display.stopAction = ^{ renderStopRequested.store(true, std::memory_order_relaxed); };
    display.modalPresentationStyle = UIModalPresentationFullScreen;
    display.modalInPresentation = YES;
    self.renderController = display;
    [display loadViewIfNeeded];
    void* layer = (__bridge void*)display.surface.layer;
    [self refreshControls];
    ARMSX3StartupLog("RENDER UI BEFORE native Vulkan game; UIKit retains CAMetalLayer through GPU/CPU cleanup");
    [self presentViewController:display animated:YES completion:^{
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0), ^{
            @autoreleasepool {
                char buffer[4096] = {};
                const int result = action(layer,1280,720,renderShouldStop,&renderStopRequested,buffer,sizeof(buffer));
                NSString* detail = [NSString stringWithUTF8String:buffer] ?: @"Renderer returned no detail.";
                dispatch_async(dispatch_get_main_queue(), ^{
                    self.intakeBusy = NO;
                    UIApplication.sharedApplication.idleTimerDisabled = previousIdle;
                    self.failed = result == -2;
                    [self.transcript appendFormat:@"%@ · %@\n",result == 0 ? @"PASS" : @"FAILED",detail];
                    self.output.text = self.transcript;
                    self.progressLabel.text = result == 0 ? @"Game stopped · share the log" : @"Rendering failed · share the log";
                    ARMSX3StartupLog([NSString stringWithFormat:@"RENDER UI %@: %@",result == 0 ? @"PASS" : @"FAIL",detail].UTF8String);
                    if (result == -2) {
                        // Keep the view AND its layer attached while native ownership is uncertain.
                        display.stopGameButton.enabled = NO;
                        display.status.text = @"Cleanup incomplete. Close and reopen ARMSX3, then share the previous log.";
                    } else {
                        [NSUserDefaults.standardUserDefaults removeObjectForKey:pendingStageKey];
                        [NSUserDefaults.standardUserDefaults synchronize];
                        [display dismissViewControllerAnimated:YES completion:^{ self.renderController = nil; }];
                    }
                    [self refreshControls];
                });
            }
        });
    }];
}
- (void)checkGraphics {
    if (self.running || self.intakeBusy || self.failed || (!self.foundationReady && self.nextStage != stageCount) || !self.coreHandle) return;
    auto action = reinterpret_cast<int (*)(char*,size_t)>(dlsym(self.coreHandle,"armsx3_core_check_graphics"));
    if (!action) { [self showLogMessage:@"Graphics check unavailable" detail:@"The graphics function is missing."]; return; }
    self.intakeBusy = YES; self.previousRunPending = NO;
    const BOOL previousIdle = UIApplication.sharedApplication.idleTimerDisabled;
    UIApplication.sharedApplication.idleTimerDisabled = YES;
    [NSUserDefaults.standardUserDefaults setObject:@"Graphics device check" forKey:pendingStageKey];
    [NSUserDefaults.standardUserDefaults synchronize];
    self.progressLabel.text = @"Checking graphics device and GPU readback…";
    [self.transcript appendString:@"\nRUN · Graphics device and offscreen readback\n"];
    self.output.text = self.transcript;
    [self refreshControls];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0), ^{
        @autoreleasepool {
            char buffer[4096] = {};
            const int result = action(buffer,sizeof(buffer));
            NSString* detail = [NSString stringWithUTF8String:buffer] ?: @"Graphics check returned no detail.";
            dispatch_async(dispatch_get_main_queue(), ^{
                self.intakeBusy = NO; UIApplication.sharedApplication.idleTimerDisabled = previousIdle;
                self.failed = result == -2;
                if (result != -2) {
                    [NSUserDefaults.standardUserDefaults removeObjectForKey:pendingStageKey];
                    [NSUserDefaults.standardUserDefaults synchronize];
                }
                [self.transcript appendFormat:@"%@ · %@\n",result == 0 ? @"PASS" : @"FAILED",detail];
                self.output.text = self.transcript;
                [self.output scrollRangeToVisible:NSMakeRange(self.output.text.length,0)];
                self.progressLabel.text = result == 0 ? @"Graphics device passed · share the log" : @"Graphics check failed · share the log";
                ARMSX3StartupLog([NSString stringWithFormat:@"GRAPHICS UI %@: %@",result == 0 ? @"PASS" : @"FAIL",detail].UTF8String);
                [self refreshControls];
            });
        }
    });
}
- (void)checkRuntimeMode:(BOOL)game execute:(BOOL)execute {
    if (self.running || self.intakeBusy || self.failed || (!self.foundationReady && self.nextStage != stageCount) || !self.coreHandle) return;
    const char* symbol = execute ? "armsx3_core_run_game" : game ? "armsx3_core_check_game" : "armsx3_core_check_runtime";
    auto action = reinterpret_cast<int (*)(char*,size_t)>(dlsym(self.coreHandle,symbol));
    if (!action) { [self showLogMessage:@"Runtime loading unavailable" detail:@"The core runtime function is missing."]; return; }
    self.intakeBusy = YES; self.previousRunPending = NO;
    const BOOL previousIdle = UIApplication.sharedApplication.idleTimerDisabled;
    UIApplication.sharedApplication.idleTimerDisabled = YES;
    [NSUserDefaults.standardUserDefaults setObject:execute ? @"Game execution (3 seconds)" : game ? @"Game load check" : @"Runtime load check" forKey:pendingStageKey];
    [NSUserDefaults.standardUserDefaults synchronize];
    self.progressLabel.text = execute ? @"Starting game… runs for 3 seconds after startup; keep app open" :
        game ? @"Loading imported game and checking disc paths…" : @"Loading executable and firmware modules…";
    [self.transcript appendString:execute ? @"\nRUN · Imported game execution and automatic stop\n" :
        game ? @"\nRUN · Imported game load and cleanup\n" : @"\nRUN · Native runtime load and cleanup\n"];
    self.output.text = self.transcript;
    ARMSX3StartupLog(execute ? "EXECUTION UI BEFORE explicit imported-game run; 15-second startup budget, 3-second run, then native cleanup" :
        game ? "GAME UI BEFORE native game load; original EBOOT and disc assets, no guest execution" :
        "RUNTIME UI BEFORE native load check; prepared executable, no guest execution");
    [self refreshControls];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0), ^{
        @autoreleasepool {
            char buffer[4096] = {};
            const int result = action(buffer,sizeof(buffer));
            NSString* detail = [NSString stringWithUTF8String:buffer] ?: @"Runtime returned no detail.";
            dispatch_async(dispatch_get_main_queue(), ^{
                self.intakeBusy = NO; UIApplication.sharedApplication.idleTimerDisabled = previousIdle;
                self.failed = result == -2; // Unfinished teardown requires a fresh process.
                if (result != -2) {
                    [NSUserDefaults.standardUserDefaults removeObjectForKey:pendingStageKey];
                    [NSUserDefaults.standardUserDefaults synchronize];
                }
                [self.transcript appendFormat:@"%@ · %@\n",result == 0 ? @"PASS" : @"FAILED",detail];
                self.output.text = self.transcript;
                [self.output scrollRangeToVisible:NSMakeRange(self.output.text.length,0)];
                self.progressLabel.text = result == 0 ? @"Runtime load complete · share the log" : @"Runtime load failed · share the log";
                ARMSX3StartupLog([NSString stringWithFormat:@"%@ UI %@: %@",execute ? @"EXECUTION" : game ? @"GAME" : @"RUNTIME",result == 0 ? @"PASS" : @"FAIL",detail].UTF8String);
                [self refreshControls];
            });
        }
    });
}
- (void)selectIntake:(NSInteger)mode {
    if (self.running || self.intakeBusy || self.failed || (!self.foundationReady && self.nextStage != stageCount) || !self.coreHandle) return;
    self.intakeMode = mode;
    UIDocumentPickerViewController* picker = mode == 3 ?
        [[UIDocumentPickerViewController alloc] initForOpeningContentTypes:@[UTTypeFolder] asCopy:NO] :
        [[UIDocumentPickerViewController alloc] initForOpeningContentTypes:@[UTTypeData] asCopy:YES];
    if (mode == 3) picker.title = @"Select folder with PS3_GAME and PS3_DISC.SFB";
    picker.delegate = self; picker.allowsMultipleSelection = NO;
    [self presentViewController:picker animated:YES completion:nil];
}
- (void)documentPicker:(UIDocumentPickerViewController*)controller didPickDocumentsAtURLs:(NSArray<NSURL*>*)urls {
    (void)controller;
    NSURL* source = urls.firstObject;
    if (!source || self.running || self.intakeBusy || !self.coreHandle) return;
    const NSInteger mode = self.intakeMode;
    const char* symbol = mode == 1 ? "armsx3_core_import_firmware" : mode == 3 ? "armsx3_core_import_game" : "armsx3_core_inspect_executable";
    auto action = reinterpret_cast<int (*)(const char*,char*,size_t)>(dlsym(self.coreHandle,symbol));
    if (!action) { [self showLogMessage:@"Import unavailable" detail:@"The core import function is missing."]; return; }
    self.intakeBusy = YES; self.previousRunPending = NO;
    const BOOL previousIdle = UIApplication.sharedApplication.idleTimerDisabled;
    UIApplication.sharedApplication.idleTimerDisabled = YES;
    NSString* label = mode == 1 ? @"Install PS3 firmware" : mode == 3 ? @"Import PS3 game folder" : @"Inspect PS3 executable";
    [NSUserDefaults.standardUserDefaults setObject:label forKey:pendingStageKey];
    [NSUserDefaults.standardUserDefaults synchronize];
    self.progressLabel.text = mode == 1 ? @"Installing firmware…" : mode == 3 ? @"Copying game folder… keep the app open" : @"Preparing executable…";
    [self.transcript appendFormat:@"\n%@ · %@\n",label,source.lastPathComponent]; self.output.text = self.transcript;
    ARMSX3StartupLog([NSString stringWithFormat:@"INTAKE UI BEFORE %@ selected=%@",label,source.lastPathComponent].UTF8String);
    [self refreshControls];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0), ^{
        @autoreleasepool {
            const BOOL scoped = [source startAccessingSecurityScopedResource];
            NSURL* local = [[NSURL fileURLWithPath:NSTemporaryDirectory() isDirectory:YES]
                URLByAppendingPathComponent:[@"ARMSX3-intake-" stringByAppendingString:NSUUID.UUID.UUIDString]];
            NSError* error = nil; __block NSString* detail = nil; __block int result = -1;
            if (mode == 3) {
                // Open the selected directory under its security scope. The
                // core makes one staged copy; avoid duplicating a multi-GB game
                // into NSTemporaryDirectory before importing it again.
                NSFileCoordinator* coordinator = [[NSFileCoordinator alloc] initWithFilePresenter:nil];
                [coordinator coordinateReadingItemAtURL:source options:0 error:&error byAccessor:^(NSURL* readingURL) {
                    char buffer[4096] = {};
                    result = action(readingURL.fileSystemRepresentation,buffer,sizeof(buffer));
                    detail = [NSString stringWithUTF8String:buffer] ?: @"Game import returned no detail.";
                }];
                if (!detail) detail = error.localizedDescription ?: @"The selected game folder is unavailable.";
            } else if ([NSFileManager.defaultManager copyItemAtURL:source toURL:local error:&error]) {
                char buffer[4096] = {};
                result = action(local.fileSystemRepresentation,buffer,sizeof(buffer));
                detail = [NSString stringWithUTF8String:buffer] ?: @"Import returned no detail.";
                [NSFileManager.defaultManager removeItemAtURL:local error:nil];
            } else detail = error.localizedDescription ?: @"The selected file could not be copied.";
            if (scoped) [source stopAccessingSecurityScopedResource];
            dispatch_async(dispatch_get_main_queue(), ^{
                self.intakeBusy = NO; UIApplication.sharedApplication.idleTimerDisabled = previousIdle;
                [NSUserDefaults.standardUserDefaults removeObjectForKey:pendingStageKey];
                [NSUserDefaults.standardUserDefaults synchronize];
                [self.transcript appendFormat:@"%@ · %@\n",result == 0 ? @"PASS" : @"FAILED",detail];
                self.output.text = self.transcript;
                [self.output scrollRangeToVisible:NSMakeRange(self.output.text.length,0)];
                self.progressLabel.text = result == 0 ? @"Import complete · share the log" : @"Import failed · share the log";
                ARMSX3StartupLog([NSString stringWithFormat:@"INTAKE UI %@ %@: %@",result == 0 ? @"PASS" : @"FAIL",label,detail].UTF8String);
                [self refreshControls];
            });
        }
    });
}
- (NSString*)logTextWithTail:(BOOL)tail {
    NSURL* docs = [[NSFileManager defaultManager] URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    NSError* error = nil;
    NSData* bytes = [NSData dataWithContentsOfURL:[docs URLByAppendingPathComponent:@"ARMSX3-startup.log"] options:0 error:&error];
    if (!bytes.length) {
        [self showLogMessage:@"Could not read startup log" detail:error.localizedDescription ?: @"The startup log is empty."];
        return nil;
    }
    NSString* text = [[NSString alloc] initWithData:bytes encoding:NSUTF8StringEncoding];
    if (!text) text = [[NSString alloc] initWithData:bytes encoding:NSISOLatin1StringEncoding];
    const auto session = armsx3_startup_log_session(text.UTF8String, self.previousRunPending);
    const auto selected = tail ? armsx3_startup_log_tail(session, 60) : session;
    NSString* build = [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleVersion"] ?: @"unknown";
    NSString* summary = self.previousRunPending ? [NSString stringWithFormat:@"Previous unfinished run: %@\n",
        [NSUserDefaults.standardUserDefaults stringForKey:pendingStageKey] ?: @"unknown stage"] : self.transcript;
    NSString* source = self.previousRunPending ? @"previous unfinished run" : @"this run";
    NSString* heading = [NSString stringWithFormat:tail ? @"Last 60 log lines from %@:\n" : @"Full log from %@:\n", source];
    return [NSString stringWithFormat:@"ARMSX3 diagnostics · build %@\n%@\n%@%@", build, summary,
        heading,
        [NSString stringWithUTF8String:selected.c_str()]];
}
- (void)copyResults {
    if (self.running) return;
    NSString* text = [self logTextWithTail:YES];
    if (!text) return;
    UIPasteboard.generalPasteboard.string = text;
    [self showLogMessage:@"Results copied" detail:@"Paste into chat. This includes the test results and the end of the log."];
}
- (void)shareLog {
    if (self.running) return;
    NSString* text = [self logTextWithTail:NO];
    if (!text) return;
    NSDateFormatter* format = [[NSDateFormatter alloc] init];
    format.locale = [NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];
    format.timeZone = [NSTimeZone timeZoneForSecondsFromGMT:0];
    format.dateFormat = @"yyyyMMdd-HHmmss-SSS";
    NSString* filename = [NSString stringWithFormat:@"ARMSX3-startup-%@-%d.txt", [format stringFromDate:NSDate.date], NSProcessInfo.processInfo.processIdentifier];
    NSURL* log = [[NSURL fileURLWithPath:NSTemporaryDirectory() isDirectory:YES] URLByAppendingPathComponent:filename];
    NSError* error = nil;
    if (![text writeToURL:log atomically:YES encoding:NSUTF8StringEncoding error:&error]) {
        [self showLogMessage:@"Could not export startup log" detail:error.localizedDescription];
        return;
    }
    UIActivityViewController* share = [[UIActivityViewController alloc] initWithActivityItems:@[log] applicationActivities:nil];
    share.popoverPresentationController.sourceView = self.shareButton;
    share.popoverPresentationController.sourceRect = self.shareButton.bounds;
    [self presentViewController:share animated:YES completion:nil];
}
@end
@interface LoadDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic,strong) UIWindow* window;
@end
@implementation LoadDelegate
- (BOOL)application:(UIApplication*)application didFinishLaunchingWithOptions:(NSDictionary*)options {
    (void)application; (void)options;
    ARMSX3StartupLog("P2 didFinishLaunching");
    self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    self.window.rootViewController = [[UINavigationController alloc] initWithRootViewController:[LoadController new]];
    [self.window makeKeyAndVisible];
    return YES;
}
@end
int main(int argc, char** argv) {
    ARMSX3StartupLog("P2 main entered");
    @autoreleasepool {
        ARMSX3InstallExceptionLogger();
        return UIApplicationMain(argc, argv, nil, NSStringFromClass(LoadDelegate.class));
    }
}

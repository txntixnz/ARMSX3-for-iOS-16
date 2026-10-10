// SPDX-License-Identifier: GPL-2.0-only
#import <UIKit/UIKit.h>
#include <dlfcn.h>
#include <cstdio>
#include "StartupLog.h"

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
};
static constexpr NSUInteger stageCount = sizeof(stages) / sizeof(stages[0]);
static NSString* const pendingStageKey = @"ARMSX3PendingDiagnosticStage";

@interface LoadController : UIViewController
@property(nonatomic,strong) UITextView* output;
@property(nonatomic,strong) UILabel* progressLabel;
@property(nonatomic,strong) UIProgressView* progress;
@property(nonatomic,strong) UIButton* runButton;
@property(nonatomic,strong) UIButton* nextButton;
@property(nonatomic,strong) UIButton* stopButton;
@property(nonatomic,strong) UIButton* shareButton;
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
    self.title = @"ARMSX3 · diagnostics";
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
    self.runButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.runButton setTitle:@"Run all tests" forState:UIControlStateNormal];
    [self.runButton addTarget:self action:@selector(startAll) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.runButton];
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
    [self.shareButton setTitle:@"Share startup log" forState:UIControlStateNormal];
    [self.shareButton addTarget:self action:@selector(shareLog) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.shareButton];
    self.output = [[UITextView alloc] init];
    self.output.editable = NO;
    self.output.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    self.output.text = @"Tap Run all tests. The core loads and every test runs in order. The sequence stops on the first failure.\n\nWhen finished, tap Share startup log. Game boot is still pending.";
    [stack addArrangedSubview:self.output];
    NSString* pending = [NSUserDefaults.standardUserDefaults stringForKey:pendingStageKey];
    if (pending.length) {
        self.output.text = [NSString stringWithFormat:@"Previous run did not finish: %@.\n\nShare the startup log if the app crashed. Run all tests starts a fresh sequence in this process. Game boot is still pending.", pending];
    }
    [self refreshControls];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(enteredBackground:)
        name:UIApplicationDidEnterBackgroundNotification object:nil];
    ARMSX3StartupLog("AUTO UI ready; one-tap ordered diagnostics available; no test starts without a tap");
}
- (void)dealloc {
    [NSNotificationCenter.defaultCenter removeObserver:self];
}
- (void)refreshControls {
    const BOOL available = !self.running && !self.failed && self.nextStage < stageCount;
    self.runButton.enabled = available;
    self.nextButton.enabled = available;
    self.stopButton.enabled = self.running && self.runAll && !self.stopRequested;
    self.shareButton.enabled = !self.running;
    [self.runButton setTitle:self.nextStage ? @"Run remaining tests" : @"Run all tests" forState:UIControlStateNormal];
    self.progress.progress = float(self.nextStage) / float(stageCount);
}
- (void)startAll { [self startSequence:YES]; }
- (void)startNext { [self startSequence:NO]; }
- (void)startSequence:(BOOL)all {
    if (self.running || self.failed || self.nextStage >= stageCount) return;
    self.running = YES;
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
    if (self.nextStage == stageCount) {
        ARMSX3StartupLog("AUTO PASS: all diagnostic stages completed; game boot remains untested");
        [self.transcript appendFormat:@"\nAll %lu tests passed. Share the startup log.\nGame boot is still pending.\n", (unsigned long)stageCount];
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
- (void)shareLog {
    if (self.running) return;
    NSURL* docs = [[NSFileManager defaultManager] URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    NSURL* log = [docs URLByAppendingPathComponent:@"ARMSX3-startup.log"];
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

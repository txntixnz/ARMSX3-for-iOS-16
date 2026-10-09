// SPDX-License-Identifier: GPL-2.0-only
#import <UIKit/UIKit.h>
#include <dlfcn.h>
#include <cstdio>
#include "StartupLog.h"

@interface LoadController : UIViewController
@property(nonatomic,strong) UITextView* output;
@property(nonatomic,strong) UIButton* loadButton;
@property(nonatomic,strong) UIButton* jitButton;
@property(nonatomic,strong) UIButton* initializeButton;
@property(nonatomic,strong) UIButton* memoryButton;
@property(nonatomic,strong) UIButton* cpuButton;
@property(nonatomic,strong) UIButton* flowButton;
@property(nonatomic,strong) UIButton* spuButton;
@property(nonatomic,strong) UIButton* dmaButton;
@property(nonatomic,assign) void* coreHandle;
@end
@implementation LoadController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    self.title = @"ARMSX3 · core load test";
    UIStackView* stack = [[UIStackView alloc] init];
    stack.axis = UILayoutConstraintAxisVertical;
    stack.spacing = 20;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[
        [stack.leadingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.leadingAnchor constant:20],
        [stack.trailingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.trailingAnchor constant:-20],
        [stack.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor constant:20],
        [stack.bottomAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.bottomAnchor constant:-20]]];
    self.loadButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.loadButton setTitle:@"Load emulator core" forState:UIControlStateNormal];
    [self.loadButton addTarget:self action:@selector(loadCore) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.loadButton];
    self.jitButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.jitButton setTitle:@"Test core JIT execution" forState:UIControlStateNormal];
    self.jitButton.enabled = NO;
    [self.jitButton addTarget:self action:@selector(testJit) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.jitButton];
    self.initializeButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.initializeButton setTitle:@"Initialize emulator" forState:UIControlStateNormal];
    self.initializeButton.enabled = NO;
    [self.initializeButton addTarget:self action:@selector(initializeCore) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.initializeButton];
    self.memoryButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.memoryButton setTitle:@"Test PS3 guest memory" forState:UIControlStateNormal];
    self.memoryButton.enabled = NO;
    [self.memoryButton addTarget:self action:@selector(testMemory) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.memoryButton];
    self.cpuButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.cpuButton setTitle:@"Test PS3 PPU instructions" forState:UIControlStateNormal];
    self.cpuButton.enabled = NO;
    [self.cpuButton addTarget:self action:@selector(testCPU) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.cpuButton];
    self.flowButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.flowButton setTitle:@"Test PS3 PPU branches / loops" forState:UIControlStateNormal];
    self.flowButton.enabled = NO;
    [self.flowButton addTarget:self action:@selector(testFlow) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.flowButton];
    self.spuButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.spuButton setTitle:@"Test PS3 SPU instructions" forState:UIControlStateNormal];
    self.spuButton.enabled = NO;
    [self.spuButton addTarget:self action:@selector(testSPU) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.spuButton];
    self.dmaButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.dmaButton setTitle:@"Test PS3 SPU DMA transfers" forState:UIControlStateNormal];
    self.dmaButton.enabled = NO;
    [self.dmaButton addTarget:self action:@selector(testDMA) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:self.dmaButton];
    UIButton* share = [UIButton buttonWithType:UIButtonTypeSystem];
    [share setTitle:@"Share startup log" forState:UIControlStateNormal];
    [share addTarget:self action:@selector(shareLog) forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:share];
    self.output = [[UITextView alloc] init];
    self.output.editable = NO;
    self.output.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    self.output.text = @"P2 tests loading the real emulator core. Game boot is not available.\n\nTap Load emulator core. Its startup constructors may close the app. Reopen and share the startup log if that happens.";
    [stack addArrangedSubview:self.output];
    ARMSX3StartupLog("P2 UI ready; core not loaded");
}
- (void)loadCore {
    self.loadButton.enabled = NO;
    self.output.text = @"Loading core…";
    ARMSX3StartupLog("P2 user requested core load");
    // Return to UIKit once so the loading text can be presented first.
    dispatch_async(dispatch_get_main_queue(), ^{
        NSString* path = [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"Frameworks/libARMSX3Core.dylib"];
        ARMSX3StartupLog("P2 BEFORE dlopen: core constructors pending");
        void* handle = dlopen(path.fileSystemRepresentation, RTLD_NOW | RTLD_LOCAL);
        if (!handle) {
            const char* error = dlerror();
            ARMSX3StartupLog(error ?: "dlopen failed without error text");
            self.output.text = [NSString stringWithFormat:@"Core load failed:\n%s\n\nShare the startup log.", error ?: "Unknown error"];
            return;
        }
        self.coreHandle = handle;
        // Keep the handle for process lifetime: unloading could invalidate core globals.
        ARMSX3StartupLog("P2 AFTER dlopen: core constructors returned");
        auto state = reinterpret_cast<int (*)()>(dlsym(handle, "armsx3_core_state"));
        if (!state) {
            ARMSX3StartupLog("P2 missing armsx3_core_state export");
            self.output.text = @"Core loaded but bridge export is missing. Share the log.";
            return;
        }
        ARMSX3StartupLog("P2 BEFORE read-only core state query");
        int value = state();
        char message[96];
        snprintf(message, sizeof(message), "P2 core state query returned %d", value);
        ARMSX3StartupLog(message);
        self.jitButton.enabled = YES;
        self.output.text = [NSString stringWithFormat:@"Core loaded. State: %d (0 = stopped).\n\nTap Test core JIT execution, then share the log. This executes small test functions; game boot is not available.", value];
    });
}
- (void)testJit {
    self.jitButton.enabled = NO;
    auto test = reinterpret_cast<int (*)()>(dlsym(self.coreHandle, "armsx3_core_test_immutable_jit"));
    if (!test) {
        ARMSX3StartupLog("P3 missing immutable JIT test export");
        self.output.text = @"JIT test export missing. Share the log.";
        return;
    }
    self.output.text = @"Testing generated code…";
    ARMSX3StartupLog("P3 user requested core JIT execution test; worker pending");
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        const int result = test();
        dispatch_async(dispatch_get_main_queue(), ^{
            self.initializeButton.enabled = result == 0;
            self.output.text = result == 0
                ? @"PASS: generated core code executed correctly across four workers.\n\nTap Initialize emulator, then share the startup log. Game boot is still pending."
                : [NSString stringWithFormat:@"Core JIT execution test failed (%d). Share the startup log.", result];
        });
    });
}
- (void)initializeCore {
    self.initializeButton.enabled = NO;
    auto initialize = reinterpret_cast<int (*)()>(dlsym(self.coreHandle, "armsx3_core_initialize"));
    if (!initialize) {
        ARMSX3StartupLog("P4 missing initialization export");
        self.output.text = @"Initialization export missing. Share the log.";
        return;
    }
    self.output.text = @"Initializing emulator…";
    ARMSX3StartupLog("P4 user requested initialization; worker pending");
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        const int result = initialize();
        dispatch_async(dispatch_get_main_queue(), ^{
            self.memoryButton.enabled = result == 0;
            self.output.text = result == 0
                ? @"Emulator initialization passed.\n\nTap Test PS3 guest memory, then share the startup log. Game boot is still pending."
                : [NSString stringWithFormat:@"Emulator initialization reported an error (%d). Share the startup log.", result];
        });
    });
}
- (void)testMemory {
    self.memoryButton.enabled = NO;
    auto test = reinterpret_cast<int (*)()>(dlsym(self.coreHandle, "armsx3_core_test_guest_memory"));
    if (!test) {
        ARMSX3StartupLog("P5 missing guest memory test export");
        self.output.text = @"Memory test export missing. Share the log.";
        return;
    }
    self.output.text = @"Testing PS3 guest memory…";
    ARMSX3StartupLog("P5 user requested guest memory test; worker pending");
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        const int result = test();
        dispatch_async(dispatch_get_main_queue(), ^{
            self.cpuButton.enabled = result == 0;
            self.output.text = result == 0
                ? @"PASS: core guest memory allocation, shared mappings and cleanup.\n\nTap Test PS3 PPU instructions next."
                : [NSString stringWithFormat:@"Guest memory test failed (%d). Share the startup log.", result];
        });
    });
}
- (void)testCPU {
    self.cpuButton.enabled = NO;
    auto test = reinterpret_cast<int (*)()>(dlsym(self.coreHandle, "armsx3_core_test_ppu_instructions"));
    if (!test) {
        ARMSX3StartupLog("P6 missing PPU instruction test export");
        self.output.text = @"PPU instruction test export missing. Share the log.";
        return;
    }
    self.output.text = @"Testing PS3 PPU instructions…";
    ARMSX3StartupLog("P6 user requested PPU instruction test; worker pending");
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        const int result = test();
        dispatch_async(dispatch_get_main_queue(), ^{
            self.flowButton.enabled = result == 0;
            self.output.text = result == 0
                ? @"PASS: 11 real PPU instructions, register results, big-endian memory and cleanup.\n\nTap Test PS3 PPU branches / loops next."
                : [NSString stringWithFormat:@"PPU instruction test failed (%d). Share the startup log.", result];
        });
    });
}
- (void)testFlow {
    self.flowButton.enabled = NO;
    auto test = reinterpret_cast<int (*)()>(dlsym(self.coreHandle, "armsx3_core_test_ppu_control_flow"));
    if (!test) {
        ARMSX3StartupLog("P7 missing PPU control-flow test export");
        self.output.text = @"PPU control-flow test export missing. Share the log.";
        return;
    }
    self.output.text = @"Testing PS3 PPU branches and loops…";
    ARMSX3StartupLog("P7 user requested PPU control-flow test; worker pending");
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        const int result = test();
        dispatch_async(dispatch_get_main_queue(), ^{
            self.spuButton.enabled = result == 0;
            self.output.text = result == 0
                ? @"PASS: core PPU loops, branches, calls, returns and memory results.\n\nTap Test PS3 SPU instructions next."
                : [NSString stringWithFormat:@"PPU control-flow test failed (%d). Share the startup log.", result];
        });
    });
}
- (void)testSPU {
    self.spuButton.enabled = NO;
    auto test = reinterpret_cast<int (*)()>(dlsym(self.coreHandle, "armsx3_core_test_spu_instructions"));
    if (!test) {
        ARMSX3StartupLog("P8 missing SPU instruction test export");
        self.output.text = @"SPU test export missing. Share the log.";
        return;
    }
    self.output.text = @"Testing PS3 SPU instructions and local memory…";
    ARMSX3StartupLog("P8 user requested SPU instruction test; worker pending");
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        const int result = test();
        dispatch_async(dispatch_get_main_queue(), ^{
            self.dmaButton.enabled = result == 0;
            self.output.text = result == 0
                ? @"PASS: SPU SIMD instructions, local memory and cleanup.\n\nRun Test PS3 SPU DMA transfers next. Game boot is still pending."
                : [NSString stringWithFormat:@"SPU test failed (%d). Share the startup log.", result];
        });
    });
}
- (void)testDMA {
    self.dmaButton.enabled = NO;
    auto test = reinterpret_cast<int (*)()>(dlsym(self.coreHandle, "armsx3_core_test_spu_dma"));
    if (!test) {
        ARMSX3StartupLog("P9 missing SPU DMA test export");
        self.output.text = @"SPU DMA test export missing. Share the log.";
        return;
    }
    self.output.text = @"Testing SPU DMA transfers, memory boundaries and cleanup…";
    ARMSX3StartupLog("P9 user requested SPU DMA test; worker pending");
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        const int result = test();
        dispatch_async(dispatch_get_main_queue(), ^{
            self.output.text = result == 0
                ? @"PASS: 32 SPU DMA transfers, memory guards, aliases and cleanup.\n\nShare the startup log. Game boot is still pending."
                : [NSString stringWithFormat:@"SPU DMA test failed (%d). Share the startup log.", result];
        });
    });
}
- (void)shareLog {
    NSURL* docs = [[NSFileManager defaultManager] URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    NSURL* log = [docs URLByAppendingPathComponent:@"ARMSX3-startup.log"];
    UIActivityViewController* share = [[UIActivityViewController alloc] initWithActivityItems:@[log] applicationActivities:nil];
    share.popoverPresentationController.sourceView = self.view;
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

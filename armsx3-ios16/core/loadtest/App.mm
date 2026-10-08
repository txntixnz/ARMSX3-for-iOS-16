// SPDX-License-Identifier: GPL-2.0-only
#import <UIKit/UIKit.h>
#include <dlfcn.h>
#include <cstdio>
#include "StartupLog.h"

@interface LoadController : UIViewController
@property(nonatomic,strong) UITextView* output;
@property(nonatomic,strong) UIButton* loadButton;
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
        self.output.text = [NSString stringWithFormat:@"Core loaded. State: %d (0 = stopped).\n\nShare the startup log. No game or JIT execution was requested.", value];
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

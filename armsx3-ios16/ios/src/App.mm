// SPDX-License-Identifier: GPL-2.0-only
#import <UIKit/UIKit.h>
#import <QuartzCore/CAMetalLayer.h>
#import <Metal/Metal.h>
#import "Diagnostics.h"
#include "StartupLog.h"
#include "Emu/RSX/VK/vkutils/metal_layer.h"

@interface MetalPreview : UIView
@property(nonatomic, strong) id<MTLCommandQueue> queue;
@property(nonatomic) BOOL bridgePassed;
@end
@implementation MetalPreview
+ (Class)layerClass { return CAMetalLayer.class; }
- (instancetype)initWithFrame:(CGRect)frame {
    if ((self = [super initWithFrame:frame])) {
        CAMetalLayer* layer = (CAMetalLayer*)self.layer;
        layer.device = MTLCreateSystemDefaultDevice();
        layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
        self.queue = [layer.device newCommandQueue];
        self.bridgePassed = GetCAMetalLayerFromMetalView((__bridge void*)self) == (__bridge void*)layer;
    }
    return self;
}
- (void)layoutSubviews {
    [super layoutSubviews];
    CAMetalLayer* layer = (CAMetalLayer*)self.layer;
    CGFloat scale = self.window.screen.scale ?: UIScreen.mainScreen.scale;
    layer.contentsScale = scale;
    layer.drawableSize = CGSizeMake(MAX(1, self.bounds.size.width * scale), MAX(1, self.bounds.size.height * scale));
    if (!self.window || !self.queue) return;
    id<CAMetalDrawable> drawable = [layer nextDrawable];
    if (!drawable) return;
    MTLRenderPassDescriptor* pass = MTLRenderPassDescriptor.renderPassDescriptor;
    pass.colorAttachments[0].texture = drawable.texture;
    pass.colorAttachments[0].loadAction = MTLLoadActionClear;
    pass.colorAttachments[0].storeAction = MTLStoreActionStore;
    pass.colorAttachments[0].clearColor = MTLClearColorMake(0.08, 0.55, 0.65, 1);
    id<MTLCommandBuffer> command = [self.queue commandBuffer];
    id<MTLRenderCommandEncoder> encoder = [command renderCommandEncoderWithDescriptor:pass];
    [encoder endEncoding];
    [command presentDrawable:drawable];
    [command commit];
}
@end

@interface ProbeController : UIViewController
@property(nonatomic, strong) UITextView* output;
@property(nonatomic, strong) UIButton* runButton;
@property(nonatomic, strong) UIButton* jitButton;
@property(nonatomic, strong) UIButton* shareButton;
@property(nonatomic, strong) MetalPreview* preview;
@property(nonatomic, strong) NSMutableDictionary* report;
@property(nonatomic, strong) NSURL* reportURL;
@end
@implementation ProbeController
- (UIButton*)button:(NSString*)title action:(SEL)action {
    UIButton* button = [UIButton buttonWithType:UIButtonTypeSystem];
    [button setTitle:title forState:UIControlStateNormal];
    button.titleLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    [button addTarget:self action:action forControlEvents:UIControlEventTouchUpInside];
    return button;
}
- (void)viewDidLoad {
    [super viewDidLoad];
    ARMSX3StartupLog("viewDidLoad entered");
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    self.title = @"ARMSX3 · iOS 16 port";
    NSURL* documents = [[NSFileManager defaultManager] URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    self.reportURL = [documents URLByAppendingPathComponent:@"ARMSX3-iOS16-diagnostic.json"];
    NSData* previous = [NSData dataWithContentsOfURL:self.reportURL];
    id decoded = previous ? [NSJSONSerialization JSONObjectWithData:previous options:NSJSONReadingMutableContainers error:nil] : nil;
    if ([decoded isKindOfClass:NSMutableDictionary.class]) self.report = decoded;
    self.output = [[UITextView alloc] init];
    self.output.editable = NO;
    self.output.font = [UIFont monospacedSystemFontOfSize:12 weight:UIFontWeightRegular];
    self.output.text = @"P0.2 memory/JIT diagnostics — the PS3 core is not linked yet.\n\nTarget: iPhone 13 Pro Max (A15), iOS 16.0.\n\nRun platform checks, then share the report. The separate JIT execution test may close the app if iOS rejects generated code; its pending stage is saved first.\n\nA cyan panel shows the UIKit Metal surface.";
    ARMSX3StartupLog("Creating Metal preview");
    self.preview = [[MetalPreview alloc] initWithFrame:CGRectZero];
    ARMSX3StartupLog("Metal preview created");
    [self.preview.heightAnchor constraintEqualToConstant:48].active = YES;
    self.runButton = [self button:@"Run platform checks" action:@selector(runChecks)];
    self.jitButton = [self button:@"Test JIT rewrites" action:@selector(confirmJIT)];
    self.shareButton = [self button:@"Share logs / report" action:@selector(shareReport)];
    self.jitButton.enabled = self.report != nil;
    self.shareButton.enabled = YES;
    UIStackView* stack = [[UIStackView alloc] initWithArrangedSubviews:@[self.preview, self.runButton, self.jitButton, self.shareButton, self.output]];
    stack.axis = UILayoutConstraintAxisVertical;
    stack.spacing = 10;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:stack];
    UILayoutGuide* safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [stack.topAnchor constraintEqualToAnchor:safe.topAnchor constant:12],
        [stack.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-12],
        [stack.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:16],
        [stack.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-16]]];
    if (self.report) [self displayReport];
    ARMSX3StartupLog("viewDidLoad complete");
}
- (void)displayReport {
    NSData* data = [NSJSONSerialization dataWithJSONObject:self.report options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:nil];
    if (data) self.output.text = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
}
- (BOOL)saveReport {
    NSError* error = nil;
    NSData* data = [NSJSONSerialization dataWithJSONObject:self.report options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:&error];
    BOOL saved = data && [data writeToURL:self.reportURL options:NSDataWritingAtomic error:&error];
    [self displayReport];
    if (!saved) self.output.text = [NSString stringWithFormat:@"Report could not be saved: %@", error.localizedDescription];
    return saved;
}
- (void)setBusy:(BOOL)busy {
    self.runButton.enabled = !busy;
    self.jitButton.enabled = !busy && self.report != nil;
    self.shareButton.enabled = !busy;
}
- (void)runChecks {
    [self setBusy:YES];
    self.report = [@{ @"build": @"ARMSX3 iOS16 P0.2", @"status": @"platform_checks_pending",
                      @"emulator_core_linked": @NO } mutableCopy];
    if (![self saveReport]) { [self setBusy:NO]; return; }
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        @autoreleasepool {
            NSDictionary* result = ARMSX3RunPlatformDiagnostics();
            dispatch_async(dispatch_get_main_queue(), ^{
                self.report = [result mutableCopy];
                self.report[@"uikit_metal_bridge_passed"] = @(self.preview.bridgePassed);
                self.report[@"status"] = @"platform_checks_completed";
                [self saveReport];
                [self setBusy:NO];
            });
        }
    });
}
- (void)confirmJIT {
    UIAlertController* alert = [UIAlertController alertControllerWithTitle:@"Run JIT test?"
        message:@"This rewrites a code page 32 times and executes each version on a worker thread. If iOS denies execution, the app may close. Reopen it and share the saved report; a pending result does not prove why it closed."
        preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Run test" style:UIAlertActionStyleDefault handler:^(UIAlertAction*) { [self runJIT]; }]];
    [self presentViewController:alert animated:YES completion:nil];
}
- (void)runJIT {
    [self setBusy:YES];
    self.report[@"jit_execution"] = @{ @"status": @"pending", @"note": @"Saved before entering generated-code test" };
    if (![self saveReport]) { [self setBusy:NO]; return; }
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        @autoreleasepool {
            NSDictionary* result = ARMSX3RunJITExecutionTest();
            dispatch_async(dispatch_get_main_queue(), ^{
                self.report[@"jit_execution"] = result;
                [self saveReport];
                [self setBusy:NO];
            });
        }
    });
}
- (void)shareReport {
    if (self.report && ![self saveReport]) return;
    NSMutableArray* items = [NSMutableArray array];
    NSURL* startupURL = [[self.reportURL URLByDeletingLastPathComponent] URLByAppendingPathComponent:@"ARMSX3-startup.log"];
    for (NSURL* url in @[startupURL, self.reportURL]) {
        if ([[NSFileManager defaultManager] fileExistsAtPath:url.path]) [items addObject:url];
    }
    if (!items.count) { self.output.text = @"No log files available yet."; return; }
    UIActivityViewController* share = [[UIActivityViewController alloc] initWithActivityItems:items applicationActivities:nil];
    share.popoverPresentationController.sourceView = self.shareButton;
    share.popoverPresentationController.sourceRect = self.shareButton.bounds;
    [self presentViewController:share animated:YES completion:nil];
}
@end

@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow* window;
@end
@implementation AppDelegate
- (BOOL)application:(UIApplication*)application didFinishLaunchingWithOptions:(NSDictionary*)options {
    ARMSX3StartupLog("didFinishLaunching entered");
    self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    self.window.rootViewController = [[UINavigationController alloc] initWithRootViewController:[ProbeController new]];
    ARMSX3StartupLog("Window and root controller created");
    [self.window makeKeyAndVisible];
    ARMSX3StartupLog("Window visible");
    return YES;
}
@end
int main(int argc, char* argv[]) {
    ARMSX3StartupLog("=== P0.2 build 3: main entered ===");
    @autoreleasepool {
        ARMSX3InstallExceptionLogger();
        ARMSX3StartupLog("Entering UIApplicationMain");
        return UIApplicationMain(argc, argv, nil, NSStringFromClass(AppDelegate.class));
    }
}

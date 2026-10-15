// SPDX-License-Identifier: GPL-2.0-only
#import "GameInputController.h"
#import <GameController/GameController.h>
#include "StartupLog.h"

@interface GameInputController ()
@property(nonatomic,strong,readwrite) UIView* touchControls;
@property(nonatomic,strong) GCController* controller;
@property(nonatomic,assign) ios_input::StateWriter stateWriter;
@property(nonatomic,assign) ios_input::EnableWriter enableWriter;
@property(nonatomic,assign) uint32_t touchButtons;
@property(nonatomic,assign) uint32_t lastButtons;
@property(nonatomic,assign) BOOL active;
@end

@implementation GameInputController
- (instancetype)initWithStateWriter:(ios_input::StateWriter)stateWriter
                      enableWriter:(ios_input::EnableWriter)enableWriter {
    self = [super init];
    if (!self) return nil;
    self.stateWriter = stateWriter;
    self.enableWriter = enableWriter;
    UIStackView* rows = [[UIStackView alloc] init];
    rows.axis = UILayoutConstraintAxisVertical;
    rows.spacing = 8;
    rows.distribution = UIStackViewDistributionFillEqually;
    const NSArray<NSArray<NSString*>*>* titles = @[@[@"↑",@"↓",@"←",@"→",@"START"],
        @[@"□",@"△",@"×",@"○",@"SELECT"]];
    const uint32_t masks[][5] = {
        {ios_input::up,ios_input::down,ios_input::left,ios_input::right,ios_input::start},
        {ios_input::square,ios_input::triangle,ios_input::cross,ios_input::circle,ios_input::select}};
    for (NSUInteger row = 0; row < 2; row++) {
        UIStackView* buttons = [[UIStackView alloc] init];
        buttons.spacing = 8;
        buttons.distribution = UIStackViewDistributionFillEqually;
        for (NSUInteger column = 0; column < 5; column++) {
            UIButton* button = [UIButton buttonWithType:UIButtonTypeCustom];
            [button setTitle:titles[row][column] forState:UIControlStateNormal];
            [button setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
            [button setTitleColor:UIColor.systemYellowColor forState:UIControlStateHighlighted];
            button.titleLabel.font = [UIFont boldSystemFontOfSize:column == 4 ? 14 : 24];
            button.backgroundColor = [UIColor colorWithWhite:0.12 alpha:0.78];
            button.layer.cornerRadius = 10;
            button.tag = masks[row][column];
            button.accessibilityLabel = @{@(ios_input::up):@"D-pad up", @(ios_input::down):@"D-pad down",
                @(ios_input::left):@"D-pad left", @(ios_input::right):@"D-pad right",
                @(ios_input::start):@"START", @(ios_input::select):@"SELECT",
                @(ios_input::square):@"Square", @(ios_input::triangle):@"Triangle",
                @(ios_input::cross):@"Cross", @(ios_input::circle):@"Circle"}[@(button.tag)];
            [button addTarget:self action:@selector(buttonDown:)
                forControlEvents:UIControlEventTouchDown | UIControlEventTouchDragEnter];
            [button addTarget:self action:@selector(buttonUp:)
                forControlEvents:UIControlEventTouchUpInside | UIControlEventTouchUpOutside |
                    UIControlEventTouchCancel | UIControlEventTouchDragExit];
            [buttons addArrangedSubview:button];
        }
        [rows addArrangedSubview:buttons];
    }
    self.touchControls = rows;
    return self;
}
- (void)start {
    NSAssert(NSThread.isMainThread, @"Input is owned by UIKit's main queue");
    if (self.active) return;
    self.touchButtons = 0;
    self.lastButtons = 0;
    self.active = YES;
    self.touchControls.userInteractionEnabled = YES;
    self.enableWriter(1);
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(controllerChanged:)
        name:GCControllerDidConnectNotification object:nil];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(controllerChanged:)
        name:GCControllerDidDisconnectNotification object:nil];
    [self chooseController];
    ARMSX3StartupLog("INPUT: player one enabled; on-screen START, D-pad and face buttons ready");
}
- (void)stop {
    NSAssert(NSThread.isMainThread, @"Input is owned by UIKit's main queue");
    if (!self.active) return;
    self.active = NO;
    [NSNotificationCenter.defaultCenter removeObserver:self];
    self.controller.extendedGamepad.valueChangedHandler = nil;
    self.controller = nil;
    self.touchButtons = 0;
    self.lastButtons = 0;
    self.touchControls.userInteractionEnabled = NO;
    self.enableWriter(0);
    ARMSX3StartupLog("INPUT: player one cleared and disabled");
}
- (void)controllerChanged:(NSNotification*)notification {
    (void)notification;
    __weak GameInputController* weakSelf = self;
    dispatch_async(dispatch_get_main_queue(), ^{ [weakSelf chooseController]; });
}
- (void)chooseController {
    if (!self.active) return;
    GCController* selected = nil;
    for (GCController* candidate in GCController.controllers) {
        if (candidate.extendedGamepad && (!selected || candidate == self.controller)) selected = candidate;
    }
    if (selected != self.controller) {
        self.controller.extendedGamepad.valueChangedHandler = nil;
        self.controller = selected;
        if (selected) {
            selected.handlerQueue = dispatch_get_main_queue();
            selected.playerIndex = GCControllerPlayerIndex1;
            selected.extendedGamepad.buttonMenu.preferredSystemGestureState = GCSystemGestureStateDisabled;
            selected.extendedGamepad.buttonOptions.preferredSystemGestureState = GCSystemGestureStateDisabled;
            __weak GameInputController* weakSelf = self;
            selected.extendedGamepad.valueChangedHandler = ^(GCExtendedGamepad* pad, GCControllerElement* element) {
                (void)element;
                GameInputController* owner = weakSelf;
                if (owner.active && pad == owner.controller.extendedGamepad) [owner publishState];
            };
            ARMSX3StartupLog([NSString stringWithFormat:@"INPUT: controller connected: %@; Menu/Options = PS3 START",
                selected.vendorName ?: @"iOS gamepad"].UTF8String);
        } else {
            ARMSX3StartupLog("INPUT: physical controller disconnected; on-screen controls remain ready");
        }
    }
    [self publishState];
}
- (void)buttonDown:(UIButton*)button {
    if (!self.active) return;
    self.touchButtons |= static_cast<uint32_t>(button.tag);
    [self publishState];
}
- (void)buttonUp:(UIButton*)button {
    if (!self.active) return;
    self.touchButtons &= ~static_cast<uint32_t>(button.tag);
    [self publishState];
}
- (void)publishState {
    if (!self.active) return;
    GCExtendedGamepad* pad = self.controller.extendedGamepad;
    uint32_t buttons = self.touchButtons;
    if (pad) {
        const struct { __unsafe_unretained GCControllerButtonInput* input; uint32_t mask; } mapping[] = {
            {pad.buttonMenu,ios_input::start}, {pad.buttonOptions,ios_input::select},
            {pad.dpad.up,ios_input::up}, {pad.dpad.down,ios_input::down},
            {pad.dpad.left,ios_input::left}, {pad.dpad.right,ios_input::right},
            {pad.buttonA,ios_input::cross}, {pad.buttonB,ios_input::circle},
            {pad.buttonX,ios_input::square}, {pad.buttonY,ios_input::triangle},
            {pad.leftShoulder,ios_input::l1}, {pad.rightShoulder,ios_input::r1},
            {pad.leftTrigger,ios_input::l2}, {pad.rightTrigger,ios_input::r2},
            {pad.leftThumbstickButton,ios_input::l3}, {pad.rightThumbstickButton,ios_input::r3}};
        for (const auto& entry : mapping) if (entry.input.pressed) buttons |= entry.mask;
    }
    if ((buttons & ios_input::start) && !(self.lastButtons & ios_input::start))
        ARMSX3StartupLog("INPUT: PS3 START pressed on player one");
    self.lastButtons = buttons;
    self.stateWriter(buttons, pad ? ios_input::axes(pad.leftThumbstick.xAxis.value, pad.leftThumbstick.yAxis.value,
        pad.rightThumbstick.xAxis.value, pad.rightThumbstick.yAxis.value) : ios_input::neutral_axes);
}
- (void)dealloc {
    [NSNotificationCenter.defaultCenter removeObserver:self];
}
@end

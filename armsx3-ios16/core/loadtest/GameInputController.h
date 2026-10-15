// SPDX-License-Identifier: GPL-2.0-only
#import <UIKit/UIKit.h>
#include "PadInput.h"

@interface GameInputController : NSObject
@property(nonatomic,strong,readonly) UIView* touchControls;
- (instancetype)initWithStateWriter:(ios_input::StateWriter)stateWriter
                      enableWriter:(ios_input::EnableWriter)enableWriter;
- (void)start;
- (void)stop;
@end

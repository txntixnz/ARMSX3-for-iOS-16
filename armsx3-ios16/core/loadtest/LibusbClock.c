// SPDX-License-Identifier: GPL-2.0-only
// The pinned libusb excludes Apple from its generic clock_gettime helpers,
// expecting darwin_usb.c to supply them. The iOS null backend needs them too.
#include <time.h>
#include <stdlib.h>
void usbi_get_monotonic_time(struct timespec *value)
{
    if (clock_gettime(CLOCK_MONOTONIC, value) != 0) abort();
}
void usbi_get_real_time(struct timespec *value)
{
    if (clock_gettime(CLOCK_REALTIME, value) != 0) abort();
}

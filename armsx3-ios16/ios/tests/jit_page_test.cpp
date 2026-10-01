// SPDX-License-Identifier: GPL-2.0-only
#include "../src/JITProbe.hpp"
#include <cassert>
#include <iostream>
int main() {
    armsx3::ios::ExecutablePage page;
    assert(page.error() == 0);
    assert(page.entry() == nullptr);
    assert(!page.publish(nullptr, 1));
    const unsigned char invalid[] = {0};
    assert(!page.publish(invalid, page.capacity() + 1));
    assert(page.entry() == nullptr);
    auto result = armsx3::ios::probeJITRewrites();
    assert(result.passed && result.iterations == 32 && result.returned == 84);
    std::cout << "PASS: reject invalid writes, 32 same-page rewrites, joined-worker execution\n";
}

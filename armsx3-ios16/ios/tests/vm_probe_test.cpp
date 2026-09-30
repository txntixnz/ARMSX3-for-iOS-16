// SPDX-License-Identifier: GPL-2.0-only
#include "../src/VMProbe.hpp"
#include <cassert>
#include <iostream>
int main() {
    using namespace armsx3::ios;
    assert(probeSharedMirror().passed);
    auto noAttempts = probeCoreLayout(0);
    assert(!noAttempts.complete && noAttempts.regions.size() == 1);
    assert(noAttempts.regions[0].address == 0 && noAttempts.regions[0].attempts == 0);
    // Occupy the first desired address: the probe must never clobber it.
    const size_t page = static_cast<size_t>(getpagesize());
    void* hint = reinterpret_cast<void*>(uint64_t{12} << 30);
    void* occupied = mmap(hint, page, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
    assert(occupied != MAP_FAILED);
    Reservation sentinel(occupied, page);
    *static_cast<volatile uint32_t*>(occupied) = 0xfeedcafe;
    // Linux overcommit policy may reject the Apple-style RW reservation.
    // Use PROT_NONE to test address selection and cleanup independently.
    auto result = probeCoreLayout(256, PROT_NONE);
    assert(*static_cast<volatile uint32_t*>(occupied) == 0xfeedcafe);
    assert(result.complete && result.regions.size() == 4);
    if (occupied == hint) assert(result.regions[0].attempts > 1);
    uint64_t total = 0;
    for (const auto& region : result.regions) {
        total += region.size;
        // The successful diagnostic must release all reservations before return.
        unsigned char residency = 0;
        errno = 0;
        assert(mincore(reinterpret_cast<void*>(region.address), page, &residency) == -1);
        assert(errno == ENOMEM);
    }
    assert(total == (uint64_t{56} << 30));
    std::cout << "PASS: shared aliases, bounded failure, no mapping clobber, 56 GiB layout, cleanup\n";
}

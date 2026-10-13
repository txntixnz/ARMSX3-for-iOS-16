"""P77 preparation: verify the pinned semaphore slow-wait/timeout/wakeup contract.

This is a source-shape regression and deterministic queue oracle. It does NOT
execute the production LV2 scheduler, native ARM atomics, or iPhone guest code.
Usage: python3 test_p77_semaphore_queue_contract.py upstream-armsx3/rpcs3/Emu/Cell/lv2/sys_semaphore.cpp
"""
from collections import deque
from pathlib import Path
import re
import sys


def source_contract(text):
    required = {
        "sleep preparation": r"lv2_obj::prepare_for_sleep\(ppu\);",
        "decrement and queue": r"if\s*\(sema\.val--\s*<=\s*0\)",
        "enqueue waiter": r"lv2_obj::emplace\(sema\.sq,\s*&ppu\);",
        "native deadline": r"lv2_obj::wait_timeout\(timeout,\s*&ppu\)",
        "timeout unqueue": r"sem->unqueue\(sem->sq,\s*&ppu\)",
        "restore expired permit": r"if\s*\(val\s*<\s*0\)\s*\{\s*val\+\+;",
        "return timeout": r"ppu\.gpr\[3\]\s*=\s*CELL_ETIMEDOUT;",
        "busy destroy": r"if\s*\(sema\.val\s*<\s*0\)",
        "post validation": r"if\s*\(count\s*<=\s*0\)",
        "maximum bound": r"count\s*\+\s*0u\s*<=\s*sema\.max\s*\+\s*0u\s*-\s*val",
        "wake count": r"std::min<s32>\(-std::min<s32>\(val,\s*0\),\s*count\)",
        "ordered scheduler": r"sem->\.schedule<ppu_thread>\(sem->sq,\s*sem->protocol\)",
        "awake scheduling": r"lv2_obj::awake_all\(\);",
        "visible nonnegative value": r"std::max<s32>\(0,\s*sema\.val\)",
    }
    missing = [name for name, expression in required.items() if not re.search(expression, text)]
    assert not missing, "Review changed upstream semaphore contract: " + ", ".join(missing)
    wait = text.split("error_code sys_semaphore_wait(", 1)[1].split("error_code sys_semaphore_trywait(", 1)[0]
    post = text.split("error_code sys_semaphore_post(", 1)[1].split("error_code sys_semaphore_get_value(", 1)[0]
    for piece in ("prepare_for_sleep(ppu)", "sema.sleep(ppu, timeout)", "wait_timeout(timeout, &ppu)", "sem->unqueue"):
        assert piece in wait, "missing wait path: " + piece
    for piece in ("sem->val.fetch_op", "sem->schedule<ppu_thread>", "lv2_obj::awake_all()"):
        assert piece in post, "missing post path: " + piece


class SemaphoreOracle:
    def __init__(self, initial, maximum):
        assert 0 <= initial <= maximum and maximum > 0
        self.val, self.maximum = initial, maximum
        self.queued = deque()
        self.woken, self.expired = set(), set()
        self.alive = True
        self.check()

    def check(self):
        if self.alive:
            assert self.val <= self.maximum
            assert (self.val < 0) == bool(self.queued)
            assert len(self.queued) == -min(self.val, 0)
            assert not (set(self.queued) & (self.woken | self.expired))

    def wait(self, name):
        if not self.alive:
            return "ESRCH"
        assert name not in self.queued and name not in self.woken and name not in self.expired
        if self.val > 0:
            self.val -= 1
            self.check()
            return "OK"
        self.val -= 1
        self.queued.append(name)
        self.check()
        return "BLOCKED"

    def trywait(self):
        if not self.alive:
            return "ESRCH"
        if self.val <= 0:
            return "EBUSY"
        self.val -= 1
        self.check()
        return "OK"

    def get_value(self):
        return max(self.val, 0) if self.alive else "ESRCH"

    def timeout(self, name):
        if name in self.woken:
            return "ALREADY_SIGNALED"
        if name not in self.queued:
            return "NO_PENDING_WAITER"
        self.queued.remove(name)
        self.val += 1
        self.expired.add(name)
        self.check()
        return "ETIMEDOUT"

    def post(self, count):
        if not self.alive:
            return ("ESRCH", [])
        if count <= 0:
            return ("EINVAL", [])
        if count > self.maximum - self.val:
            return ("EBUSY", [])
        previous = self.val
        self.val += count
        wake_count = min(-min(previous, 0), count)
        waking = [self.queued.popleft() for _ in range(wake_count)]
        self.woken.update(waking)
        self.check()
        return ("OK", waking)

    def destroy(self):
        if not self.alive:
            return "ESRCH"
        if self.val < 0:
            return "EBUSY"
        self.alive = False
        return "OK"


def model_scenarios():
    for expire_first in (False, True, False):
        sem = SemaphoreOracle(0, 3)
        assert sem.wait("A") == "BLOCKED" and sem.wait("B") == "BLOCKED"
        assert sem.val == -2 and sem.get_value() == 0
        assert sem.trywait() == "EBUSY" and sem.destroy() == "EBUSY"
        if expire_first:
            assert sem.timeout("A") == "ETIMEDOUT"
            assert sem.val == -1 and list(sem.queued) == ["B"]
            assert sem.post(1) == ("OK", ["B"])
            assert sem.timeout("B") == "ALREADY_SIGNALED"
        else:
            assert sem.post(1) == ("OK", ["A"])
            assert sem.val == -1 and list(sem.queued) == ["B"]
            assert sem.timeout("B") == "ETIMEDOUT"
            assert sem.timeout("A") == "ALREADY_SIGNALED"
        assert sem.val == 0 and not sem.queued
        assert sem.post(2) == ("OK", [])
        assert sem.wait("C") == "OK" and sem.val == 1
        assert sem.post(3) == ("EBUSY", []) and sem.post(0) == ("EINVAL", [])
        assert sem.get_value() == 1 and sem.destroy() == "OK"
        assert sem.trywait() == "ESRCH" and sem.post(1) == ("ESRCH", [])
    sem = SemaphoreOracle(0, 2)
    assert sem.wait("one") == "BLOCKED" and sem.wait("two") == "BLOCKED"
    assert sem.post(2) == ("OK", ["one", "two"])
    assert sem.val == 0 and not sem.queued
    assert sem.timeout("one") == "ALREADY_SIGNALED"
    assert sem.timeout("two") == "ALREADY_SIGNALED"
    assert sem.post(3) == ("EBUSY", []) and sem.destroy() == "OK"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_p77_semaphore_queue_contract.py sys_semaphore.cpp")
    source_contract(Path(sys.argv[1]).read_text())
    model_scenarios()
    print("P77 PREPARATION PASS: source contract and deterministic waiter/permit oracle; native device execution not tested.")

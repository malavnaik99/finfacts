import pytest

from finfacts.sec.rate_limit import TokenBucket


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_never_exceeds_rate_over_one_second() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate=8, clock=clock, sleep=clock.sleep)
    for _ in range(80):
        bucket.acquire()
    # 8 burst tokens, then 72 more at 8/s -> 9 seconds.
    assert clock.now == pytest.approx(9.0)


def test_refills_after_idle() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate=8, clock=clock, sleep=clock.sleep)
    for _ in range(8):
        bucket.acquire()
    clock.now += 10  # idle long enough to refill, but never above capacity
    for _ in range(8):
        bucket.acquire()
    assert clock.now == pytest.approx(10.0)


def test_rejects_non_positive_rate() -> None:
    with pytest.raises(ValueError, match="positive"):
        TokenBucket(rate=0)

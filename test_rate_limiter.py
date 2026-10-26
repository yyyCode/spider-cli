import pytest

from rate_limiter import IntervalPolicy, RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FixedRng:
    def __init__(self, value):
        self.value = value

    def uniform(self, low, high):
        return self.value


def make_limiter(policy, clock, value):
    return RateLimiter(
        policy,
        clock=clock,
        sleep=clock.sleep,
        rng=FixedRng(value),
    )


def test_first_wait_does_not_sleep():
    clock = FakeClock()
    limiter = make_limiter(IntervalPolicy(2, 4), clock, 3)
    assert limiter.wait() == 0.0
    assert clock.now == 0.0


def test_second_wait_uses_interval():
    clock = FakeClock()
    limiter = make_limiter(IntervalPolicy(2, 4), clock, 3)
    limiter.wait()
    assert limiter.wait() == 3.0
    assert clock.now == 3.0


def test_block_for_delays_next_wait():
    clock = FakeClock()
    limiter = make_limiter(IntervalPolicy(1, 1), clock, 1)
    limiter.wait()
    limiter.block_for(10)
    assert limiter.wait() == 10.0
    assert clock.now == 10.0


def test_block_for_does_not_shorten_existing_block():
    clock = FakeClock()
    limiter = make_limiter(IntervalPolicy(1, 1), clock, 1)
    limiter.wait()
    limiter.block_for(10)
    limiter.block_for(5)
    assert limiter.wait() == 10.0


def test_invalid_policy_raises():
    with pytest.raises(ValueError):
        IntervalPolicy(3, 2)
    with pytest.raises(ValueError):
        IntervalPolicy(-1, 2)

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class IntervalPolicy:
    min_seconds: float
    max_seconds: float

    def __post_init__(self) -> None:
        if self.min_seconds < 0 or self.max_seconds < self.min_seconds:
            raise ValueError("限频区间不合法")


class RateLimiter:
    def __init__(
        self,
        policy: IntervalPolicy,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ):
        self.policy = policy
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._last: float | None = None
        self._blocked_until = 0.0

    def wait(self) -> float:
        now = self._clock()
        target = now
        if self._last is not None:
            target = self._last + self._rng.uniform(
                self.policy.min_seconds,
                self.policy.max_seconds,
            )
        target = max(target, self._blocked_until)
        delay = max(0.0, target - now)
        if delay > 0:
            self._sleep(delay)
        self._last = self._clock()
        return delay

    def block_for(self, seconds: float) -> None:
        until = self._clock() + max(0.0, seconds)
        self._blocked_until = max(self._blocked_until, until)

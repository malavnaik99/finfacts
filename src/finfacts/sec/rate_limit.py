"""Thread-safe token bucket used to stay under SEC's 10 requests/second limit."""

import threading
import time
from collections.abc import Callable


class TokenBucket:
    """Allows ``rate`` acquisitions per second, with bursts up to ``capacity``."""

    def __init__(
        self,
        rate: float,
        capacity: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.rate = rate
        self.capacity = capacity if capacity is not None else rate
        self._tokens = self.capacity
        self._clock = clock
        self._sleep = sleep
        self._last = clock()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
            self._last = now
            if self._tokens >= 1:
                self._tokens -= 1
                return
            wait = (1 - self._tokens) / self.rate
            # Sleep inside the lock so concurrent callers queue instead of all waking together.
            self._sleep(wait)
            self._last = self._clock()
            self._tokens = 0

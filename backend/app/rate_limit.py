from __future__ import annotations

from collections import defaultdict
from time import monotonic


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        """Record an attempt. Returns True if allowed, False if over limit."""
        now = monotonic()
        cutoff = now - self.window
        self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]
        if len(self._attempts[key]) >= self.max_attempts:
            return False
        self._attempts[key].append(now)
        return True


invite_redeem_limiter = RateLimiter(max_attempts=5, window_seconds=60)

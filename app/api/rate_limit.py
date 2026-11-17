from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int


class FixedWindowRateLimiter:
    """Fixed-window limiter. Local mode is per-process; Redis mode is shared."""

    _SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
if current > tonumber(ARGV[2]) then return {0, math.max(ttl, 1)} end
return {1, 0}
"""

    def __init__(self, *, limit: int, window_seconds: int) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("rate limit and window must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._local: dict[str, tuple[int, int]] = {}

    async def check(self, identity: str, redis_client=None) -> RateLimitDecision:
        now = int(time.time())
        window = now // self.window_seconds
        key = f"api-rate:{identity}:{window}"
        if redis_client is not None:
            allowed, retry = await redis_client.eval(
                self._SCRIPT, 1, key, self.window_seconds, self.limit
            )
            return RateLimitDecision(bool(allowed), int(retry))

        count, expires = self._local.get(identity, (0, window))
        if expires != window:
            count = 0
        count += 1
        self._local[identity] = (count, window)
        # Bound memory for this development-only fallback.
        if len(self._local) > 10000:
            self._local.clear()
            self._local[identity] = (count, window)
        return RateLimitDecision(
            allowed=count <= self.limit,
            retry_after=max(1, (window + 1) * self.window_seconds - now),
        )

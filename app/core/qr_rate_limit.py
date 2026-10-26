"""Shared, short-lived link/global counters. Never read or key on visitor data."""

from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.rate_limit import RateLimitDecision

RESERVE_SCAN = """
local limits = {120, 5000}
for i = 1, 2 do
  if tonumber(redis.call('GET', KEYS[i]) or '0') >= limits[i] then
    return {0, math.max(redis.call('TTL', KEYS[i]), 1)}
  end
end
for i = 1, 2 do
  local n = redis.call('INCR', KEYS[i])
  if n == 1 then redis.call('EXPIRE', KEYS[i], 60) end
end
return {1, 0}
"""


class QRRateLimiter:
    def __init__(self, redis: Redis | None):
        self.redis = redis

    async def reserve(self, code: str) -> RateLimitDecision:
        if self.redis is not None:
            try:
                result = await cast(
                    Awaitable[object],
                    self.redis.eval(
                        RESERVE_SCAN, 2, f"ratelimit:qr:link:{code}", "ratelimit:qr:global"
                    ),
                )
                if result == [1, 0]:
                    return RateLimitDecision(allowed=True)
                if isinstance(result, list) and len(result) == 2 and result[0] == 0:
                    return RateLimitDecision(allowed=False, retry_after_seconds=int(result[1]))
            except (RedisError, ValueError, TypeError):
                pass
        return RateLimitDecision(allowed=False, storage_available=False)

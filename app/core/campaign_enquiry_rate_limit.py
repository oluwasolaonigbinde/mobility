import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.rate_limit import RateLimitDecision

# Reserve both counters together, across API processes. Do not refund failures:
# repeated transport failures must not provide unlimited access to the relay.
# ARGV: per-IP limit, global limit, per-IP window, global window (seconds).
RESERVE_ENQUIRY = """
for i = 1, 2 do
  local count = tonumber(redis.call('GET', KEYS[i]) or '0')
  if count >= tonumber(ARGV[i]) then
    local ttl = redis.call('TTL', KEYS[i])
    if ttl < 1 then
      redis.call('EXPIRE', KEYS[i], ARGV[2 + i])
      ttl = tonumber(ARGV[2 + i])
    end
    return {0, ttl}
  end
end
for i = 1, 2 do
  local count = redis.call('INCR', KEYS[i])
  if count == 1 then redis.call('EXPIRE', KEYS[i], ARGV[2 + i]) end
end
return {1, 0}
"""


@dataclass(frozen=True)
class PublicSubmitLimits:
    """One per-IP bucket and one global bucket for a public write endpoint."""

    key_prefix: str
    ip_max_attempts: int
    ip_window_seconds: int
    global_max_attempts: int
    global_window_seconds: int


def campaign_enquiry_limits(settings: Settings) -> PublicSubmitLimits:
    window = settings.campaign_enquiry_rate_limit_window_seconds
    return PublicSubmitLimits(
        key_prefix="campaign-enquiry",
        ip_max_attempts=settings.campaign_enquiry_rate_limit_ip_max_attempts,
        ip_window_seconds=window,
        global_max_attempts=settings.campaign_enquiry_rate_limit_global_max_attempts,
        global_window_seconds=window,
    )


class EnquiryRateLimiter(Protocol):
    async def reserve(self, ip: str) -> RateLimitDecision: ...


class UnavailableEnquiryRateLimiter:
    async def reserve(self, ip: str) -> RateLimitDecision:
        del ip
        return RateLimitDecision(allowed=False, storage_available=False)


class RedisEnquiryRateLimiter:
    def __init__(
        self, redis: Redis, settings: Settings, limits: PublicSubmitLimits | None = None
    ) -> None:
        self.redis = redis
        self.limits = limits or campaign_enquiry_limits(settings)
        self.script = redis.register_script(RESERVE_ENQUIRY)

    def keys(self, ip: str) -> list[str]:
        digest = hashlib.sha256(ip.encode()).hexdigest()
        prefix = self.limits.key_prefix
        return [f"ratelimit:{prefix}:ip:{digest}", f"ratelimit:{prefix}:global"]

    async def reserve(self, ip: str) -> RateLimitDecision:
        try:
            raw = await self.script(
                keys=self.keys(ip),
                args=[
                    self.limits.ip_max_attempts,
                    self.limits.global_max_attempts,
                    self.limits.ip_window_seconds,
                    self.limits.global_window_seconds,
                ],
            )
            if raw == [1, 0]:
                return RateLimitDecision(allowed=True)
            if isinstance(raw, list) and len(raw) == 2 and raw[0] == 0 and int(raw[1]) > 0:
                return RateLimitDecision(allowed=False, retry_after_seconds=int(raw[1]))
        except (RedisError, TypeError, ValueError):
            pass
        return RateLimitDecision(allowed=False, storage_available=False)


@asynccontextmanager
async def open_submit_limiter(
    settings: Settings, limits: PublicSubmitLimits | None = None
) -> AsyncIterator[EnquiryRateLimiter]:
    """A Redis-backed limiter, or one that reports storage unavailable (fail closed)."""
    if not settings.redis_url:
        yield UnavailableEnquiryRateLimiter()
        return
    try:
        redis = Redis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )
    except ValueError:
        yield UnavailableEnquiryRateLimiter()
        return
    async with redis:
        yield RedisEnquiryRateLimiter(redis, settings, limits)

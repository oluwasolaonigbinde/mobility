import hashlib
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.rate_limit import RateLimitDecision

# Reserve both counters together, across API processes. Do not refund failures:
# repeated transport failures must not provide unlimited access to the relay.
RESERVE_ENQUIRY = """
for i = 1, 2 do
  local count = tonumber(redis.call('GET', KEYS[i]) or '0')
  if count >= tonumber(ARGV[i]) then
    local ttl = redis.call('TTL', KEYS[i])
    if ttl < 1 then
      redis.call('EXPIRE', KEYS[i], ARGV[3])
      ttl = tonumber(ARGV[3])
    end
    return {0, ttl}
  end
end
for i = 1, 2 do
  local count = redis.call('INCR', KEYS[i])
  if count == 1 then redis.call('EXPIRE', KEYS[i], ARGV[3]) end
end
return {1, 0}
"""


class EnquiryRateLimiter(Protocol):
    async def reserve(self, ip: str) -> RateLimitDecision: ...


class UnavailableEnquiryRateLimiter:
    async def reserve(self, ip: str) -> RateLimitDecision:
        del ip
        return RateLimitDecision(allowed=False, storage_available=False)


class RedisEnquiryRateLimiter:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self.redis = redis
        self.settings = settings
        self.script = redis.register_script(RESERVE_ENQUIRY)

    def keys(self, ip: str) -> list[str]:
        digest = hashlib.sha256(ip.encode()).hexdigest()
        return [f"ratelimit:campaign-enquiry:ip:{digest}", "ratelimit:campaign-enquiry:global"]

    async def reserve(self, ip: str) -> RateLimitDecision:
        try:
            raw = await self.script(
                keys=self.keys(ip),
                args=[
                    self.settings.campaign_enquiry_rate_limit_ip_max_attempts,
                    self.settings.campaign_enquiry_rate_limit_global_max_attempts,
                    self.settings.campaign_enquiry_rate_limit_window_seconds,
                ],
            )
            if raw == [1, 0]:
                return RateLimitDecision(allowed=True)
            if isinstance(raw, list) and len(raw) == 2 and raw[0] == 0 and int(raw[1]) > 0:
                return RateLimitDecision(allowed=False, retry_after_seconds=int(raw[1]))
        except (RedisError, TypeError, ValueError):
            pass
        return RateLimitDecision(allowed=False, storage_available=False)

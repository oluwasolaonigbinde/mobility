import ipaddress
import logging
from dataclasses import dataclass
from typing import Protocol

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.services.users import normalize_email

logger = logging.getLogger(__name__)
_limiters: dict[tuple[str, int, int, int, int, int, int], "RedisLoginRateLimiter"] = {}

# The reserve script derives the notify-marker key from KEYS[i] inside Lua
# instead of declaring it. That is fine on standalone Redis (the supported
# topology) but would break on Redis Cluster, which requires every touched key
# to be declared and co-located. Revisit before any cluster migration.
RESERVE_LOGIN_ATTEMPT = """
local limits = {tonumber(ARGV[1]), tonumber(ARGV[3]), tonumber(ARGV[5])}
local ttls = {tonumber(ARGV[2]), tonumber(ARGV[4]), tonumber(ARGV[6])}
for i = 1, 3 do
  local current = tonumber(redis.call('GET', KEYS[i]) or '0')
  if current >= limits[i] then
    local ttl = redis.call('TTL', KEYS[i])
    if ttl < 0 then
      redis.call('EXPIRE', KEYS[i], ttls[i])
      ttl = ttls[i]
    end
    local marker = 'ratelimit:login:notify:' .. KEYS[i]
    local notified = redis.call('SET', marker, '1', 'NX', 'EX', math.max(ttl, 1))
    return {0, i, ttl, notified and 1 or 0}
  end
end
for i = 1, 3 do
  local value = redis.call('INCR', KEYS[i])
  if value == 1 then redis.call('EXPIRE', KEYS[i], ttls[i]) end
end
return {1, 0, 0, 0}
"""

RELEASE_LOGIN_SUCCESS = """
redis.call('DEL', KEYS[2])
for _, i in ipairs({1, 3}) do
  local value = tonumber(redis.call('GET', KEYS[i]) or '0')
  if value > 0 then redis.call('DECR', KEYS[i]) end
end
return 1
"""


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    bucket: str | None = None
    retry_after_seconds: int = 0
    newly_blocked: bool = False
    storage_available: bool = True


class LoginRateLimiter(Protocol):
    async def reserve(self, ip: str, email: str) -> RateLimitDecision: ...

    async def release_success(self, ip: str, email: str) -> None: ...


class RegistrationRateLimiter(Protocol):
    async def reserve(self, ip: str, email: str) -> RateLimitDecision: ...


class NoopLoginRateLimiter:
    async def reserve(self, ip: str, email: str) -> RateLimitDecision:
        del ip, email
        return RateLimitDecision(allowed=True)

    async def release_success(self, ip: str, email: str) -> None:
        del ip, email


class FailClosedRegistrationRateLimiter:
    """Default when enabled registration has no usable Redis boundary."""

    async def reserve(self, ip: str, email: str) -> RateLimitDecision:
        del ip, email
        return RateLimitDecision(
            allowed=False,
            bucket="storage",
            retry_after_seconds=60,
            storage_available=False,
        )


class InMemoryRegistrationRateLimiter:
    """Explicit deterministic fake for local/test injection only."""

    def __init__(self, *, ip_limit: int = 100, email_limit: int = 20):
        self.ip_limit = ip_limit
        self.email_limit = email_limit
        self._ip: dict[str, int] = {}
        self._email: dict[str, int] = {}
        self._notified: set[str] = set()

    async def reserve(self, ip: str, email: str) -> RateLimitDecision:
        normalized_email = normalize_email(email)
        bucket_values = (
            ("ip", self._ip.get(ip, 0), self.ip_limit),
            ("email", self._email.get(normalized_email, 0), self.email_limit),
        )
        for bucket, value, limit in bucket_values:
            if value >= limit:
                marker_value = {
                    "ip": ip,
                    "email": normalized_email,
                }[bucket]
                marker = f"{bucket}:{marker_value}"
                newly_blocked = marker not in self._notified
                self._notified.add(marker)
                return RateLimitDecision(
                    allowed=False,
                    bucket=bucket,
                    retry_after_seconds=60,
                    newly_blocked=newly_blocked,
                )
        self._ip[ip] = self._ip.get(ip, 0) + 1
        self._email[normalized_email] = self._email.get(normalized_email, 0) + 1
        return RateLimitDecision(allowed=True)


class RedisLoginRateLimiter:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self.redis = redis
        self.settings = settings
        self.reserve_script = redis.register_script(RESERVE_LOGIN_ATTEMPT)
        self.release_script = redis.register_script(RELEASE_LOGIN_SUCCESS)

    def keys(self, ip: str, email: str) -> list[str]:
        return [
            f"ratelimit:login:ip:{ip}",
            f"ratelimit:login:acct:{normalize_email(email)}",
            "ratelimit:login:global",
        ]

    async def reserve(self, ip: str, email: str) -> RateLimitDecision:
        try:
            raw = await self.reserve_script(
                keys=self.keys(ip, email),
                args=[
                    self.settings.login_rate_limit_ip_max_failures,
                    self.settings.login_rate_limit_ip_window_seconds,
                    self.settings.login_rate_limit_account_max_failures,
                    self.settings.login_rate_limit_account_window_seconds,
                    self.settings.login_rate_limit_global_max_failures,
                    self.settings.login_rate_limit_global_window_seconds,
                ],
            )
            if not isinstance(raw, (list, tuple)) or len(raw) != 4:
                raise ValueError("malformed reserve response")
            values = [int(value) for value in raw]
            if values == [1, 0, 0, 0]:
                return RateLimitDecision(allowed=True)
            if (
                values[0] != 0
                or values[2] < 1
                or values[3] not in (0, 1)
            ):
                raise ValueError("invalid reserve response values")
            bucket = {1: "ip", 2: "account", 3: "global"}.get(values[1])
            if bucket is None:
                raise ValueError("unknown rate-limit bucket")
            return RateLimitDecision(
                allowed=False,
                bucket=bucket,
                retry_after_seconds=max(values[2], 1),
                newly_blocked=values[3] == 1,
            )
        except (RedisError, TypeError, ValueError) as exc:
            logger.warning("Login rate limiter unavailable: %s", exc)
            return RateLimitDecision(
                allowed=False,
                bucket="storage",
                retry_after_seconds=60,
                storage_available=False,
            )

    async def release_success(self, ip: str, email: str) -> None:
        try:
            await self.release_script(keys=self.keys(ip, email))
        except (RedisError, TypeError, ValueError) as exc:
            logger.warning("Login rate limiter success refund failed: %s", exc)


RESERVE_REGISTRATION_ATTEMPT = """
local limits = {tonumber(ARGV[1]), tonumber(ARGV[3])}
local ttls = {tonumber(ARGV[2]), tonumber(ARGV[4])}
for i = 1, 2 do
  local current = tonumber(redis.call('GET', KEYS[i]) or '0')
  if current >= limits[i] then
    local ttl = redis.call('TTL', KEYS[i])
    if ttl < 0 then
      redis.call('EXPIRE', KEYS[i], ttls[i])
      ttl = ttls[i]
    end
    local marker = 'ratelimit:driver-registration:notify:' .. KEYS[i]
    local notified = redis.call('SET', marker, '1', 'NX', 'EX', math.max(ttl, 1))
    return {0, i, ttl, notified and 1 or 0}
  end
end
for i = 1, 2 do
  local value = redis.call('INCR', KEYS[i])
  if value == 1 then redis.call('EXPIRE', KEYS[i], ttls[i]) end
end
return {1, 0, 0, 0}
"""


class RedisRegistrationRateLimiter:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self.redis = redis
        self.settings = settings
        self.reserve_script = redis.register_script(RESERVE_REGISTRATION_ATTEMPT)

    def keys(self, ip: str, email: str) -> list[str]:
        return [
            f"ratelimit:driver-registration:ip:{ip}",
            f"ratelimit:driver-registration:email:{normalize_email(email)}",
        ]

    async def reserve(self, ip: str, email: str) -> RateLimitDecision:
        try:
            raw = await self.reserve_script(
                keys=self.keys(ip, email),
                args=[
                    self.settings.driver_registration_rate_limit_ip_max_attempts,
                    self.settings.driver_registration_rate_limit_ip_window_seconds,
                    self.settings.driver_registration_rate_limit_email_max_attempts,
                    self.settings.driver_registration_rate_limit_email_window_seconds,
                ],
            )
            if not isinstance(raw, (list, tuple)) or len(raw) != 4:
                raise ValueError("malformed registration reserve response")
            values = [int(value) for value in raw]
            if values == [1, 0, 0, 0]:
                return RateLimitDecision(allowed=True)
            if values[0] != 0 or values[2] < 1 or values[3] not in (0, 1):
                raise ValueError("invalid registration reserve values")
            bucket = {1: "ip", 2: "email"}.get(values[1])
            if bucket is None:
                raise ValueError("unknown registration rate-limit bucket")
            return RateLimitDecision(
                allowed=False,
                bucket=bucket,
                retry_after_seconds=values[2],
                newly_blocked=values[3] == 1,
            )
        except (RedisError, TypeError, ValueError) as exc:
            logger.warning("Driver registration rate limiter unavailable: %s", exc)
            return RateLimitDecision(
                allowed=False,
                bucket="storage",
                retry_after_seconds=60,
                storage_available=False,
            )


def login_client_ip(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    if not settings.login_rate_limit_trust_client_ip_header:
        return peer
    try:
        peer_address = ipaddress.ip_address(peer)
        trusted = any(
            peer_address in ipaddress.ip_network(value.strip(), strict=False)
            for value in settings.login_rate_limit_trusted_proxy_cidrs.split(",")
            if value.strip()
        )
    except ValueError:
        trusted = False
    if not trusted:
        return peer
    forwarded = request.headers.get("X-Client-IP", "").strip()
    try:
        return str(ipaddress.ip_address(forwarded))
    except ValueError:
        return peer


def registration_client_ip(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    if not settings.driver_registration_rate_limit_trust_client_ip_header:
        return peer
    try:
        peer_address = ipaddress.ip_address(peer)
        trusted = any(
            peer_address in ipaddress.ip_network(value.strip(), strict=False)
            for value in settings.driver_registration_rate_limit_trusted_proxy_cidrs.split(",")
            if value.strip()
        )
    except ValueError:
        trusted = False
    if not trusted:
        return peer
    forwarded = request.headers.get("X-Client-IP", "").strip()
    try:
        return str(ipaddress.ip_address(forwarded))
    except ValueError:
        return peer


def build_login_rate_limiter(settings: Settings) -> LoginRateLimiter:
    if not settings.redis_url:
        return NoopLoginRateLimiter()
    key = (
        settings.redis_url,
        settings.login_rate_limit_ip_max_failures,
        settings.login_rate_limit_ip_window_seconds,
        settings.login_rate_limit_account_max_failures,
        settings.login_rate_limit_account_window_seconds,
        settings.login_rate_limit_global_max_failures,
        settings.login_rate_limit_global_window_seconds,
    )
    existing = _limiters.get(key)
    if existing is not None:
        return existing
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    limiter = RedisLoginRateLimiter(redis, settings)
    _limiters[key] = limiter
    return limiter


_registration_limiters: dict[tuple[str, int, int, int, int], RegistrationRateLimiter] = {}


def build_registration_rate_limiter(settings: Settings) -> RegistrationRateLimiter:
    if not settings.redis_url:
        return FailClosedRegistrationRateLimiter()
    key = (
        settings.redis_url,
        settings.driver_registration_rate_limit_ip_max_attempts,
        settings.driver_registration_rate_limit_ip_window_seconds,
        settings.driver_registration_rate_limit_email_max_attempts,
        settings.driver_registration_rate_limit_email_window_seconds,
    )
    existing = _registration_limiters.get(key)
    if existing is not None:
        return existing
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        limiter = RedisRegistrationRateLimiter(redis, settings)
    except (RedisError, TypeError, ValueError) as exc:
        logger.warning("Driver registration rate limiter configuration unavailable: %s", exc)
        return FailClosedRegistrationRateLimiter()
    _registration_limiters[key] = limiter
    return limiter

import asyncio
import os

import pytest
from conftest import auth_headers, create_test_user
from fastapi import Request
from redis.asyncio import Redis

from app.api.v1.dependencies import get_login_rate_limiter
from app.core.config import Settings
from app.core.rate_limit import RateLimitDecision, RedisLoginRateLimiter, login_client_ip
from app.models.user import UserRole


class BlockingLimiter:
    async def reserve(self, ip: str, email: str) -> RateLimitDecision:
        del ip, email
        return RateLimitDecision(
            allowed=False,
            bucket="account",
            retry_after_seconds=42,
            newly_blocked=False,
        )

    async def release_success(self, ip: str, email: str) -> None:
        del ip, email


def request_with_headers(peer: str, headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": headers,
            "client": (peer, 1234),
            "server": ("test", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_forged_headers_are_ignored_without_trust() -> None:
    request = request_with_headers(
        "203.0.113.5",
        [(b"x-client-ip", b"198.51.100.8"), (b"x-forwarded-for", b"192.0.2.2")],
    )
    assert login_client_ip(request, Settings()) == "203.0.113.5"


def test_forged_headers_are_ignored_outside_trusted_proxy_cidrs() -> None:
    request = request_with_headers("203.0.113.5", [(b"x-client-ip", b"198.51.100.8")])
    settings = Settings(
        login_rate_limit_trust_client_ip_header=True,
        login_rate_limit_trusted_proxy_cidrs="10.0.0.0/8",
    )
    assert login_client_ip(request, settings) == "203.0.113.5"


def test_trusted_proxy_can_supply_validated_client_ip() -> None:
    request = request_with_headers("10.0.0.7", [(b"x-client-ip", b"198.51.100.8")])
    settings = Settings(
        login_rate_limit_trust_client_ip_header=True,
        login_rate_limit_trusted_proxy_cidrs="10.0.0.0/8",
    )
    assert login_client_ip(request, settings) == "198.51.100.8"


def test_login_429_surfaces_retry_after(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="limited@example.com", role=UserRole.ADMIN)
    db_client.app.dependency_overrides[get_login_rate_limiter] = lambda: BlockingLimiter()
    try:
        response = db_client.post(
            "/api/v1/auth/login",
            json={"email": "limited@example.com", "password": "long-secure-password"},
        )
    finally:
        db_client.app.dependency_overrides.pop(get_login_rate_limiter, None)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "42"
    assert response.json()["error"]["details"]["retry_after_seconds"] == 42


def test_change_password_429_surfaces_retry_after(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="limited-change@example.com", role=UserRole.ADMIN)
    headers = auth_headers(db_client, "limited-change@example.com")
    db_client.app.dependency_overrides[get_login_rate_limiter] = lambda: BlockingLimiter()
    try:
        response = db_client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "long-secure-password",
                "new_password": "another-long-secure-password",
            },
            headers=headers,
        )
    finally:
        db_client.app.dependency_overrides.pop(get_login_rate_limiter, None)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "42"
    assert response.json()["error"]["details"]["retry_after_seconds"] == 42


def test_redis_reservations_are_atomic_ttl_bound_and_refundable() -> None:
    redis_url = os.environ.get("RATE_LIMIT_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("Redis rate-limit test URL is not configured")

    async def exercise() -> None:
        redis = Redis.from_url(redis_url, decode_responses=True)
        await redis.flushdb()
        settings = Settings(
            redis_url=redis_url,
            login_rate_limit_ip_max_failures=20,
            login_rate_limit_account_max_failures=3,
            login_rate_limit_global_max_failures=30,
            login_rate_limit_ip_window_seconds=30,
            login_rate_limit_account_window_seconds=30,
            login_rate_limit_global_window_seconds=30,
        )
        limiter = RedisLoginRateLimiter(redis, settings)
        decisions = await asyncio.gather(
            *(limiter.reserve("203.0.113.10", "target@example.com") for _ in range(10))
        )
        assert sum(decision.allowed for decision in decisions) == 3
        blocked = [decision for decision in decisions if not decision.allowed]
        assert blocked
        assert sum(decision.newly_blocked for decision in blocked) == 1
        assert all(decision.bucket == "account" for decision in blocked)

        keys = limiter.keys("203.0.113.10", "target@example.com")
        ttls = await asyncio.gather(*(redis.ttl(key) for key in keys))
        assert all(ttl > 0 for ttl in ttls)
        before_ip = int(await redis.get(keys[0]) or 0)
        before_global = int(await redis.get(keys[2]) or 0)
        await limiter.release_success("203.0.113.10", "target@example.com")
        assert await redis.exists(keys[1]) == 0
        assert int(await redis.get(keys[0]) or 0) == before_ip - 1
        assert int(await redis.get(keys[2]) or 0) == before_global - 1

        per_ip = RedisLoginRateLimiter(
            redis,
            Settings(
                redis_url=redis_url,
                login_rate_limit_ip_max_failures=1,
                login_rate_limit_account_max_failures=20,
                login_rate_limit_global_max_failures=30,
                login_rate_limit_ip_window_seconds=30,
                login_rate_limit_account_window_seconds=30,
                login_rate_limit_global_window_seconds=30,
            ),
        )
        await redis.flushdb()
        assert (await per_ip.reserve("198.51.100.1", "one@example.com")).allowed
        same_ip = await per_ip.reserve("198.51.100.1", "two@example.com")
        assert not same_ip.allowed and same_ip.bucket == "ip"
        assert (await per_ip.reserve("198.51.100.2", "two@example.com")).allowed
        await redis.aclose()

    asyncio.run(exercise())

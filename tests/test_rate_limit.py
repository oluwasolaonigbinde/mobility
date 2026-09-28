import asyncio
import logging
import os

import pytest
from conftest import auth_headers, create_test_user
from fastapi import Request
from redis.asyncio import Redis

from app.api.v1 import auth as auth_api
from app.api.v1.dependencies import get_login_rate_limiter
from app.core.config import Settings
from app.core.rate_limit import (
    FailClosedRegistrationRateLimiter,
    InMemoryRegistrationRateLimiter,
    RateLimitDecision,
    RedisLoginRateLimiter,
    RedisRegistrationRateLimiter,
    build_registration_rate_limiter,
    login_client_ip,
    registration_client_ip,
)
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


class UnavailableLimiter:
    async def reserve(self, ip: str, email: str) -> RateLimitDecision:
        del ip, email
        return RateLimitDecision(
            allowed=False,
            bucket="storage",
            retry_after_seconds=60,
            storage_available=False,
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


def test_registration_client_ip_has_its_own_trust_boundary() -> None:
    request = request_with_headers("10.0.0.7", [(b"x-client-ip", b"198.51.100.8")])
    settings = Settings(
        driver_registration_rate_limit_trust_client_ip_header=True,
        driver_registration_rate_limit_trusted_proxy_cidrs="10.0.0.0/8",
    )
    assert registration_client_ip(request, settings) == "198.51.100.8"
    assert (
        registration_client_ip(
            request_with_headers("203.0.113.5", [(b"x-client-ip", b"198.51.100.8")]), settings
        )
        == "203.0.113.5"
    )


def test_registration_in_memory_limits_stop_at_each_exact_boundary() -> None:
    async def exercise() -> None:
        per_ip = InMemoryRegistrationRateLimiter(ip_limit=2, email_limit=20)
        assert (await per_ip.reserve("203.0.113.1", "one@example.com")).allowed
        assert (await per_ip.reserve("203.0.113.1", "two@example.com")).allowed
        ip_block = await per_ip.reserve("203.0.113.1", "three@example.com")
        assert (
            not ip_block.allowed and ip_block.bucket == "ip" and ip_block.retry_after_seconds == 60
        )

        per_email = InMemoryRegistrationRateLimiter(ip_limit=20, email_limit=2)
        assert (await per_email.reserve("203.0.113.1", "same@example.com")).allowed
        assert (await per_email.reserve("203.0.113.2", "same@example.com")).allowed
        email_block = await per_email.reserve("203.0.113.3", "SAME@example.com")
        assert not email_block.allowed and email_block.bucket == "email"

        distributed = InMemoryRegistrationRateLimiter(ip_limit=2, email_limit=2)
        for index in range(25):
            assert (
                await distributed.reserve(
                    f"10.0.0.{index + 1}", f"applicant-{index}@example.com"
                )
            ).allowed

    asyncio.run(exercise())


def test_registration_redis_malformed_response_fails_closed() -> None:
    class MalformedRedis:
        def register_script(self, _script):
            async def malformed(**_kwargs):
                return ["not", "a", "reservation"]

            return malformed

    async def exercise() -> None:
        limiter = RedisRegistrationRateLimiter(MalformedRedis(), Settings())
        decision = await limiter.reserve("203.0.113.1", "driver@example.com")
        assert not decision.allowed
        assert decision.storage_available is False
        assert decision.bucket == "storage"
        assert decision.retry_after_seconds == 60

    asyncio.run(exercise())


def test_registration_redis_malformed_success_tuple_fails_closed() -> None:
    class MalformedRedis:
        def register_script(self, _script):
            async def malformed(**_kwargs):
                return [1, 99, 0, 0]

            return malformed

    async def exercise() -> None:
        decision = await RedisRegistrationRateLimiter(MalformedRedis(), Settings()).reserve(
            "203.0.113.1", "driver@example.com"
        )
        assert not decision.allowed
        assert decision.storage_available is False

    asyncio.run(exercise())


def test_login_redis_failure_is_reported_as_storage_unavailable() -> None:
    class BrokenRedis:
        def register_script(self, _script):
            async def broken(**_kwargs):
                raise TypeError("unavailable")

            return broken

    decision = asyncio.run(
        RedisLoginRateLimiter(BrokenRedis(), Settings()).reserve(
            "203.0.113.1", "driver@example.com"
        )
    )
    assert not decision.allowed
    assert decision.storage_available is False
    assert decision.bucket == "storage"


def test_login_global_alert_admits_and_logs_one_error(caplog) -> None:
    class AlertingRedis:
        def register_script(self, _script):
            async def alerting(**_kwargs):
                return [1, 0, 0, 1]

            return alerting

    with caplog.at_level(logging.ERROR, logger="app.core.rate_limit"):
        decision = asyncio.run(
            RedisLoginRateLimiter(AlertingRedis(), Settings()).reserve(
                "203.0.113.1", "driver@example.com"
            )
        )

    assert decision == RateLimitDecision(allowed=True)
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert "global alert threshold" in message
    assert "250 failures in 300 seconds" in message
    assert "203.0.113.1" not in message and "driver@example.com" not in message


@pytest.mark.parametrize(
    "raw",
    [
        [1, 99, 0, 0],
        [1, 0, 1, 0],
        [1, 0, 0, 2],
        [0, 99, 1, 0],
        [0, 3, 1, 0],
        [0, 1, 0, 0],
        [0, 1, 1, 2],
    ],
)
def test_login_redis_malformed_tuple_fails_closed(raw: list[int]) -> None:
    class MalformedRedis:
        def register_script(self, _script):
            async def malformed(**_kwargs):
                return raw

            return malformed

    decision = asyncio.run(
        RedisLoginRateLimiter(MalformedRedis(), Settings()).reserve(
            "203.0.113.1", "driver@example.com"
        )
    )
    assert not decision.allowed
    assert decision.storage_available is False
    assert decision.bucket == "storage"


def test_registration_invalid_redis_configuration_builds_fail_closed_limiter() -> None:
    limiter = build_registration_rate_limiter(Settings(redis_url="invalid://redis"))
    assert isinstance(limiter, FailClosedRegistrationRateLimiter)

    decision = asyncio.run(limiter.reserve("203.0.113.1", "driver@example.com"))
    assert not decision.allowed
    assert decision.storage_available is False


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


def test_login_and_change_password_fail_closed_before_credentials_or_audit(
    db_client, db_sessionmaker, monkeypatch
) -> None:
    create_test_user(db_sessionmaker, email="unavailable@example.com", role=UserRole.ADMIN)
    headers = auth_headers(db_client, "unavailable@example.com")
    reached: list[str] = []

    async def forbidden(*_args, **_kwargs):
        reached.append("credential-or-audit")
        raise AssertionError("unavailable limiter must stop before credentials or audit")

    monkeypatch.setattr(auth_api, "login_with_password", forbidden)
    monkeypatch.setattr(auth_api, "change_user_password", forbidden)
    monkeypatch.setattr(auth_api, "create_audit_event", forbidden)
    db_client.app.dependency_overrides[get_login_rate_limiter] = lambda: UnavailableLimiter()
    try:
        login = db_client.post(
            "/api/v1/auth/login",
            json={"email": "unavailable@example.com", "password": "long-secure-password"},
        )
        change = db_client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "long-secure-password",
                "new_password": "another-long-secure-password",
            },
            headers=headers,
        )
    finally:
        db_client.app.dependency_overrides.pop(get_login_rate_limiter, None)

    for response in (login, change):
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "60"
        assert response.json()["error"]["code"] == "RATE_LIMIT_UNAVAILABLE"
    assert reached == []


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


def test_redis_global_bucket_alerts_once_and_never_blocks(caplog) -> None:
    redis_url = os.environ.get("RATE_LIMIT_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("Redis rate-limit test URL is not configured")

    async def exercise() -> list[RateLimitDecision]:
        redis = Redis.from_url(redis_url, decode_responses=True)
        await redis.flushdb()
        limiter = RedisLoginRateLimiter(
            redis,
            Settings(
                redis_url=redis_url,
                login_rate_limit_ip_max_failures=20,
                login_rate_limit_account_max_failures=3,
                login_rate_limit_global_max_failures=3,
                login_rate_limit_ip_window_seconds=30,
                login_rate_limit_account_window_seconds=30,
                login_rate_limit_global_window_seconds=30,
            ),
        )
        decisions = [
            await limiter.reserve(f"198.51.100.{index}", f"spread-{index}@example.com")
            for index in range(10)
        ]
        global_key = limiter.keys("198.51.100.0", "spread-0@example.com")[2]
        assert int(await redis.get(global_key)) == 10
        assert await redis.ttl(f"ratelimit:login:notify:{global_key}") > 0
        # A missing TTL on the global key is repaired before the alert marker is set.
        await redis.flushdb()
        await redis.set(global_key, 5)
        assert (await limiter.reserve("198.51.100.99", "late@example.com")).allowed
        assert await redis.ttl(global_key) > 0
        # With the global bucket over its limit, the account bucket still refuses on
        # its own limit and the alert does not repeat within the window.
        for _ in range(3):
            assert (await limiter.reserve("198.51.100.50", "same@example.com")).allowed
        account_block = await limiter.reserve("198.51.100.51", "same@example.com")
        assert not account_block.allowed and account_block.bucket == "account"
        await redis.aclose()
        return decisions

    with caplog.at_level(logging.ERROR, logger="app.core.rate_limit"):
        decisions = asyncio.run(exercise())

    assert all(decision.allowed for decision in decisions)
    alerts = [
        record
        for record in caplog.records
        if record.levelno == logging.ERROR and "global alert threshold" in record.getMessage()
    ]
    # Once at the third failure of the first window, once after the flush that
    # cleared the marker for the TTL-repair case.
    assert len(alerts) == 2


def test_registration_redis_reservations_are_atomic_ttl_bound_and_notify_once() -> None:
    redis_url = os.environ.get("RATE_LIMIT_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("Redis rate-limit test URL is not configured")

    async def exercise() -> None:
        redis = Redis.from_url(redis_url, decode_responses=True)
        await redis.flushdb()
        settings = Settings(
            redis_url=redis_url,
            driver_registration_rate_limit_ip_max_attempts=20,
            driver_registration_rate_limit_email_max_attempts=3,
            driver_registration_rate_limit_ip_window_seconds=30,
            driver_registration_rate_limit_email_window_seconds=30,
        )
        limiter = RedisRegistrationRateLimiter(redis, settings)
        decisions = await asyncio.gather(
            *(limiter.reserve("203.0.113.20", "applicant@example.com") for _ in range(10))
        )
        assert sum(decision.allowed for decision in decisions) == 3
        blocked = [decision for decision in decisions if not decision.allowed]
        assert blocked
        assert all(decision.bucket == "email" for decision in blocked)
        assert sum(decision.newly_blocked for decision in blocked) == 1
        keys = limiter.keys("203.0.113.20", "applicant@example.com")
        assert all(ttl > 0 for ttl in await asyncio.gather(*(redis.ttl(key) for key in keys)))
        for index in range(25):
            assert (
                await limiter.reserve(
                    f"10.0.0.{index + 1}", f"distributed-{index}@example.com"
                )
            ).allowed

        await redis.flushdb()
        alias = RedisRegistrationRateLimiter(
            redis,
            Settings(
                redis_url=redis_url,
                driver_registration_rate_limit_ip_max_attempts=20,
                driver_registration_rate_limit_email_max_attempts=1,
                driver_registration_rate_limit_ip_window_seconds=30,
                driver_registration_rate_limit_email_window_seconds=30,
            ),
        )
        assert (await alias.reserve("198.51.100.3", "  Alias@Example.COM  ")).allowed
        alias_block = await alias.reserve("198.51.100.4", "alias@example.com")
        assert not alias_block.allowed
        assert alias_block.bucket == "email"
        assert alias_block.newly_blocked
        repeated_alias_block = await alias.reserve("198.51.100.5", "ALIAS@EXAMPLE.COM")
        assert not repeated_alias_block.allowed
        assert not repeated_alias_block.newly_blocked
        await redis.aclose()

    asyncio.run(exercise())

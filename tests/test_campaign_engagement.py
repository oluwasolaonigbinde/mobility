import asyncio
import logging
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.qr_privacy import ScanAccessFilter, scan_event_filter, scan_path
from app.core.qr_rate_limit import QRRateLimiter
from app.schemas.campaign_engagement import ArtworkLinkWrite, validated_website


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "javascript:alert(1)",
        "//example.com",
        "https://localhost",
        "https://127.0.0.1",
        "https://[::1]",
        "https://office.local",
        "https://app.internal",
        "https://user:pass@example.com",
        "https://example.com:8080",
        "https://example.com:bad",
        "https://example.com\\@attacker.com",
        "https://example.com\r\nLocation: https://evil.com",
        "https://example.com/" + "a" * 2048,
    ],
)
def test_website_accepts_only_public_https(url):
    with pytest.raises(ValueError):
        validated_website(url)


def test_website_normalizes_host_but_keeps_the_exact_destination_path():
    assert (
        validated_website(" https://EXAMPLE.com:443/order?campaign=car#menu ")
        == "https://example.com/order?campaign=car#menu"
    )
    with pytest.raises(ValidationError):
        ArtworkLinkWrite(destination="https://example.com", redirect_to="https://evil.com")


def test_scan_limiter_uses_only_artwork_and_global_keys_and_fails_closed():
    redis = AsyncMock()
    redis.eval.return_value = [1, 0]
    assert asyncio.run(QRRateLimiter(redis).reserve("a" * 32)).allowed
    assert redis.eval.call_args.args[2:] == ("ratelimit:qr:link:" + "a" * 32, "ratelimit:qr:global")
    redis.eval.return_value = [0, 35]
    decision = asyncio.run(QRRateLimiter(redis).reserve("a" * 32))
    assert not decision.allowed and decision.retry_after_seconds == 35
    redis.eval.side_effect = RedisConnectionError("private failure")
    assert not asyncio.run(QRRateLimiter(redis).reserve("a" * 32)).storage_available
    assert not asyncio.run(QRRateLimiter(None).reserve("a" * 32)).storage_available


def test_scan_application_access_logs_and_error_events_are_dropped():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        "%s %s %s %s %s",
        ("192.0.2.45", "GET", "/api/v1/qr/" + "a" * 32, "1.1", 302),
        None,
    )
    assert not ScanAccessFilter().filter(record)
    record.args = ("192.0.2.45", "GET", "/health", "1.1", 200)
    assert ScanAccessFilter().filter(record)
    event = {
        "request": {
            "url": "https://cardvert.example/q/" + "a" * 32,
            "headers": {"user-agent": "private browser"},
        }
    }
    assert scan_event_filter(event, {}) is None
    assert scan_event_filter({"transaction": "GET /api/v1/qr/{code}"}, {}) is None
    assert scan_event_filter({"transaction": "GET /health"}, {}) == {"transaction": "GET /health"}
    assert not scan_path("https://[invalid")


def test_scan_limits_are_atomic_across_independent_redis_clients():
    url = os.environ.get("RATE_LIMIT_TEST_REDIS_URL")
    if not url:
        pytest.skip("RATE_LIMIT_TEST_REDIS_URL must point to this lane's isolated Redis")

    async def run():
        clients = [Redis.from_url(url), Redis.from_url(url)]
        code = uuid4().hex
        other = uuid4().hex
        keys = [f"ratelimit:qr:link:{code}", f"ratelimit:qr:link:{other}", "ratelimit:qr:global"]
        try:
            await clients[0].delete(*keys)
            limiters = [QRRateLimiter(client) for client in clients]
            results = await asyncio.gather(
                *(limiters[index % 2].reserve(code) for index in range(130))
            )
            assert sum(result.allowed for result in results) == 120
            assert all(result.storage_available for result in results)
            assert all(result.retry_after_seconds > 0 for result in results if not result.allowed)
            assert 0 < await clients[0].ttl(keys[0]) <= 60
            assert await clients[0].get(keys[2]) == b"120"
            await clients[0].set(keys[2], 5000, ex=60)
            assert not (await limiters[1].reserve(other)).allowed
            assert await clients[0].get(keys[1]) is None
        finally:
            await clients[0].delete(*keys)
            for client in clients:
                await client.aclose()

    asyncio.run(run())

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.v1.campaign_enquiries import (
    get_enquiry_limiter,
    read_enquiry,
)
from app.core.campaign_enquiry_rate_limit import RedisEnquiryRateLimiter
from app.core.config import Settings
from app.core.errors import AppError
from app.core.rate_limit import RateLimitDecision
from app.db.session import get_session
from app.main import create_app

PAYLOAD = {
    "company": "Test brand",
    "contact_name": "Example contact",
    "email": "contact@example.test",
    "phone": "",
    "brief": "A vehicle campaign in Abuja, starting next month.",
}


def make_client(*, session=None, decision=None, **settings_values):
    session = session or MagicMock(spec=AsyncSession)
    limiter = AsyncMock()
    limiter.reserve.return_value = decision or RateLimitDecision(allowed=True)
    app = create_app(Settings(**settings_values))

    async def store():
        yield session

    app.dependency_overrides[get_session] = store
    app.dependency_overrides[get_enquiry_limiter] = lambda: limiter
    return TestClient(app, raise_server_exceptions=False), session, limiter


def test_valid_enquiry_has_non_sensitive_reply(caplog):
    client, session, limiter = make_client()
    response = client.post("/api/v1/campaign-enquiries", json=PAYLOAD)
    assert response.status_code == 200
    assert response.json() == {"status": "submitted"}
    assert PAYLOAD["email"] not in response.text + caplog.text
    session.commit.assert_awaited_once()
    assert limiter.reserve.call_args.args[0] == "testclient"


@pytest.mark.parametrize(
    "patch",
    [
        {"company": " "},
        {"contact_name": "\t"},
        {"brief": " "},
        {"email": "invalid"},
        {"email": "a" * 255 + "@example.test"},
        {"brief": "x" * 2001},
        {"company": "x" * 161},
        {"contact_name": "x" * 161},
        {"phone": "x" * 33},
        {"recipient": "attacker@example.test"},
        {"email": "one@example.test\r\nBcc: victim@example.test"},
        {"company": 123},
        {"brief": "text\x00text"},
    ],
)
def test_invalid_input_is_rejected_without_send_or_input_echo(patch):
    client, session, limiter = make_client()
    response = client.post("/api/v1/campaign-enquiries", json={**PAYLOAD, **patch})
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {}
    assert PAYLOAD["email"] not in response.text
    session.commit.assert_not_called()
    limiter.reserve.assert_not_called()


@pytest.mark.parametrize(
    "body,content_type,expected",
    [
        ("not json", "application/json", 422),
        (json.dumps(PAYLOAD), "text/plain", 415),
        ("x" * 8193, "application/json", 413),
        ("[]", "application/json", 422),
    ],
)
def test_request_parsing_fails_safely(body, content_type, expected):
    client, session, _ = make_client()
    response = client.post(
        "/api/v1/campaign-enquiries", content=body, headers={"Content-Type": content_type}
    )
    assert response.status_code == expected
    session.commit.assert_not_called()


def test_stream_limit_does_not_require_content_length():
    async def run():
        chunks = iter([b"x" * 4096, b"x" * 4097])

        async def receive():
            return {"type": "http.request", "body": next(chunks), "more_body": True}

        request = Request(
            {"type": "http", "headers": [(b"content-type", b"application/json")]}, receive
        )
        with pytest.raises(AppError) as error:
            await read_enquiry(request)
        assert error.value.status_code == 413

    asyncio.run(run())


@pytest.mark.parametrize(
    "decision,expected",
    [
        (RateLimitDecision(allowed=False, retry_after_seconds=12), 429),
        (RateLimitDecision(allowed=False, storage_available=False), 503),
    ],
)
def test_gates_never_send(decision, expected):
    client, session, _ = make_client(decision=decision)
    response = client.post("/api/v1/campaign-enquiries", json=PAYLOAD)
    assert response.status_code == expected
    if expected == 429:
        assert response.headers["Retry-After"] == "12"
    session.commit.assert_not_called()


def test_storage_failure_never_reports_success():
    session = MagicMock(spec=AsyncSession)
    session.commit.side_effect = RuntimeError("synthetic database failure")
    client, _, _ = make_client(session=session)
    response = client.post("/api/v1/campaign-enquiries", json=PAYLOAD)
    assert response.status_code == 500
    assert "submitted" not in response.text
    assert PAYLOAD["email"] not in response.text


def test_forged_ip_header_is_not_trusted():
    client, _, limiter = make_client(
        login_rate_limit_trust_client_ip_header=True,
        login_rate_limit_trusted_proxy_cidrs="127.0.0.1/32",
    )
    client.post("/api/v1/campaign-enquiries", json=PAYLOAD, headers={"X-Client-IP": "203.0.113.10"})
    assert limiter.reserve.call_args.args[0] == "testclient"


def test_limiter_unavailable_and_malformed_fail_closed():
    async def run():
        redis = AsyncMock()
        redis.register_script = lambda _: AsyncMock(side_effect=RedisConnectionError())
        limiter = RedisEnquiryRateLimiter(redis, Settings())
        assert not (await limiter.reserve("127.0.0.1")).storage_available
        limiter.script = AsyncMock(return_value=[7])
        assert not (await limiter.reserve("127.0.0.1")).storage_available
        assert "127.0.0.1" not in limiter.keys("127.0.0.1")[0]

    asyncio.run(run())


def test_real_redis_atomic_limits_expiry_and_global_scope():
    async def run():
        async with Redis.from_url("redis://localhost:6379/0", decode_responses=True) as redis:
            # Unique test namespace; leave unrelated runtime counters untouched.
            prefix = f"test:campaign-enquiry:{uuid4()}"
            settings = Settings()
            limiter = RedisEnquiryRateLimiter(redis, settings)
            limiter.keys = lambda ip: [f"{prefix}:ip:{ip}", f"{prefix}:global"]
            results = await asyncio.gather(*(limiter.reserve("a") for _ in range(8)))
            assert sum(result.allowed for result in results) == 5
            for index in range(95):
                assert (await limiter.reserve(f"peer-{index}")).allowed
            assert not (await limiter.reserve("c")).allowed
            assert 0 < await redis.ttl(f"{prefix}:global") <= 3600
            await redis.pexpire(f"{prefix}:ip:a", 1)
            await redis.pexpire(f"{prefix}:global", 1)
            await asyncio.sleep(0.02)
            assert (await limiter.reserve("a")).allowed
            await redis.delete(*[key async for key in redis.scan_iter(match=f"{prefix}:*")])

    asyncio.run(run())


def test_fixed_rate_policy_cannot_be_weakened_by_settings():
    fixed = Settings(campaign_enquiry_rate_limit_ip_max_attempts=0)
    assert fixed.campaign_enquiry_rate_limit_ip_max_attempts == 5
    assert fixed.campaign_enquiry_rate_limit_global_max_attempts == 100
    assert fixed.campaign_enquiry_rate_limit_window_seconds == 3600


def test_no_redis_configuration_returns_safe_unavailable():
    app = create_app(Settings(redis_url=None))
    session = MagicMock(spec=AsyncSession)

    async def store():
        yield session

    app.dependency_overrides[get_session] = store
    response = TestClient(app).post("/api/v1/campaign-enquiries", json=PAYLOAD)
    assert response.status_code == 503
    session.commit.assert_not_called()


def test_deep_json_fails_with_safe_validation_error():
    client, session, _ = make_client()
    response = client.post(
        "/api/v1/campaign-enquiries",
        content="[" * 4000 + "]" * 4000,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    session.commit.assert_not_called()

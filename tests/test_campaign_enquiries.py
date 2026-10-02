import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.requests import Request

from app.adapters.messaging.email import DisabledEmailAdapter, EmailSendError, EmailSubmission
from app.api.v1.campaign_enquiries import (
    get_enquiry_email_adapter,
    get_enquiry_limiter,
    read_enquiry,
)
from app.core.campaign_enquiry_rate_limit import RedisEnquiryRateLimiter
from app.core.config import Settings
from app.core.errors import AppError
from app.core.rate_limit import RateLimitDecision
from app.main import create_app

PAYLOAD = {
    "company": "Test brand",
    "contact_name": "Example contact",
    "email": "contact@example.test",
    "phone": "",
    "brief": "A vehicle campaign in Abuja, starting next month.",
}


def make_client(*, enabled=True, adapter=None, decision=None, **settings_values):
    adapter = adapter or AsyncMock()
    if isinstance(adapter, AsyncMock):
        adapter.send.return_value = EmailSubmission(provider_message_id="local-message")
    limiter = AsyncMock()
    limiter.reserve.return_value = decision or RateLimitDecision(allowed=True)
    app = create_app(Settings(campaign_enquiry_enabled=enabled, **settings_values))
    app.dependency_overrides[get_enquiry_email_adapter] = lambda: adapter
    app.dependency_overrides[get_enquiry_limiter] = lambda: limiter
    return TestClient(app), adapter, limiter


def test_valid_enquiry_uses_fixed_recipient_and_escaped_body(caplog):
    client, adapter, limiter = make_client()
    response = client.post(
        "/api/v1/campaign-enquiries", json={**PAYLOAD, "company": " <b>Brand</b> "}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "submitted"}
    message = adapter.send.call_args.args[0]
    assert message.recipient == "terraxmediacompany@gmail.com"
    assert message.subject == "Campaign quote enquiry — Terrax Media"
    assert "Company: <b>Brand</b>" in message.text_body
    assert "&lt;b&gt;Brand&lt;/b&gt;" in message.html_body
    assert "<b>Brand</b>" not in message.html_body
    assert PAYLOAD["email"] in message.text_body
    assert message.idempotency_key.startswith("campaign-enquiry-")
    assert PAYLOAD["email"] not in response.text + caplog.text
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
    client, adapter, limiter = make_client()
    response = client.post("/api/v1/campaign-enquiries", json={**PAYLOAD, **patch})
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {}
    assert PAYLOAD["email"] not in response.text
    adapter.send.assert_not_called()
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
    client, adapter, _ = make_client()
    response = client.post(
        "/api/v1/campaign-enquiries", content=body, headers={"Content-Type": content_type}
    )
    assert response.status_code == expected
    adapter.send.assert_not_called()


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
    "enabled,decision,expected",
    [
        (False, RateLimitDecision(allowed=True), 503),
        (True, RateLimitDecision(allowed=False, retry_after_seconds=12), 429),
        (True, RateLimitDecision(allowed=False, storage_available=False), 503),
    ],
)
def test_gates_never_send(enabled, decision, expected):
    client, adapter, _ = make_client(enabled=enabled, decision=decision)
    response = client.post("/api/v1/campaign-enquiries", json=PAYLOAD)
    assert response.status_code == expected
    if expected == 429:
        assert response.headers["Retry-After"] == "12"
    adapter.send.assert_not_called()


@pytest.mark.parametrize("adapter", [DisabledEmailAdapter(), AsyncMock()])
def test_unavailable_transport_never_reports_success(adapter):
    client, adapter, _ = make_client(adapter=adapter)
    if isinstance(adapter, AsyncMock):
        adapter.send.side_effect = EmailSendError("email_provider_unavailable", retryable=True)
    response = client.post("/api/v1/campaign-enquiries", json=PAYLOAD)
    assert response.status_code == 503
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
            settings = Settings(
                campaign_enquiry_rate_limit_ip_max_attempts=2,
                campaign_enquiry_rate_limit_global_max_attempts=3,
                campaign_enquiry_rate_limit_window_seconds=1,
            )
            limiter = RedisEnquiryRateLimiter(redis, settings)
            limiter.keys = lambda ip: [f"{prefix}:ip:{ip}", f"{prefix}:global"]
            results = await asyncio.gather(*(limiter.reserve("a") for _ in range(8)))
            assert sum(result.allowed for result in results) == 2
            assert (await limiter.reserve("b")).allowed
            assert not (await limiter.reserve("c")).allowed
            assert 0 < await redis.ttl(f"{prefix}:global") <= 1
            await asyncio.sleep(1.1)
            assert (await limiter.reserve("a")).allowed
            await redis.delete(f"{prefix}:ip:a", f"{prefix}:ip:b", f"{prefix}:global")

    asyncio.run(run())


def test_invalid_rate_policy_is_not_accepted():
    with pytest.raises(ValidationError):
        Settings(campaign_enquiry_rate_limit_ip_max_attempts=0)


@pytest.mark.parametrize("enabled", [False, True])
def test_no_redis_configuration_returns_safe_unavailable(enabled):
    app = create_app(Settings(campaign_enquiry_enabled=enabled, redis_url=None))
    adapter = AsyncMock()
    app.dependency_overrides[get_enquiry_email_adapter] = lambda: adapter
    response = TestClient(app).post("/api/v1/campaign-enquiries", json=PAYLOAD)
    assert response.status_code == 503
    adapter.send.assert_not_called()


def test_deep_json_fails_with_safe_validation_error():
    client, adapter, _ = make_client()
    response = client.post(
        "/api/v1/campaign-enquiries",
        content="[" * 4000 + "]" * 4000,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    adapter.send.assert_not_called()


def test_real_dependencies_without_email_configuration_return_unavailable(monkeypatch):
    prefix = f"test:campaign-enquiry:{uuid4()}"
    monkeypatch.setattr(
        RedisEnquiryRateLimiter, "keys", lambda self, ip: [f"{prefix}:ip", f"{prefix}:global"]
    )
    app = create_app(
        Settings(
            campaign_enquiry_enabled=True,
            redis_url="redis://127.0.0.1:6379/0",
            email_provider="",
            email_smtp_host="",
            email_sender_address="",
            campaign_enquiry_rate_limit_window_seconds=1,
        )
    )
    response = TestClient(app).post("/api/v1/campaign-enquiries", json=PAYLOAD)
    assert response.status_code == 503
    assert "submitted" not in response.text

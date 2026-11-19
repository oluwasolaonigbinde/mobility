"""REQ-336/D172: site-wide feedback button and the password-protected review page."""

import asyncio
import base64
import csv
import io
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from authorization_matrix import PROJECT_REVIEW_ROUTES, Principal, authorization_inventory
from conftest import auth_headers, create_test_user, isolated_postgis_sessionmaker
from database_helpers import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    fetch_all,
    upgrade_to,
)
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from test_config import production_settings

from alembic import command
from app.api.v1.project_feedback import (
    get_feedback_submit_limiter,
    get_feedback_unlock_limiter,
)
from app.core import clock
from app.core.campaign_enquiry_rate_limit import PublicSubmitLimits, RedisEnquiryRateLimiter
from app.core.config import Settings
from app.core.errors import AppError
from app.core.rate_limit import RateLimitDecision
from app.core.security import create_access_token
from app.db.session import get_session
from app.main import create_app
from app.models.project_feedback import ProjectFeedbackItem
from app.models.user import User, UserRole
from app.services.project_feedback import (
    MAX_SCREENSHOT_BYTES,
    reencode_screenshot,
)

REVIEW_PASSWORD = "project-review-password-for-tests"
PAYLOAD = {"name": "Ada Tester", "page_path": "/advertiser/campaigns", "message": "Button is odd."}


class FakeLimiter:
    """Per-IP in-memory buckets; records every reserved IP."""

    def __init__(self, limit: int = 100, decision: RateLimitDecision | None = None) -> None:
        self.limit = limit
        self.decision = decision
        self.ips: list[str] = []

    async def reserve(self, ip: str) -> RateLimitDecision:
        self.ips.append(ip)
        if self.decision is not None:
            return self.decision
        if self.ips.count(ip) > self.limit:
            return RateLimitDecision(allowed=False, retry_after_seconds=42)
        return RateLimitDecision(allowed=True)


def feedback_settings(**overrides) -> Settings:
    values = {
        "environment": "test",
        "database_url": None,
        "redis_url": None,
        "jwt_secret_key": "test-secret-key-at-least-32-bytes",
        "feedback_enabled": True,
        "feedback_review_password": REVIEW_PASSWORD,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_client(db_sessionmaker, *, settings=None, submit=None, unlock=None, client=None):
    app = create_app(settings or feedback_settings())

    async def store():
        async with db_sessionmaker() as session:
            yield session

    submit = submit or FakeLimiter()
    unlock = unlock or FakeLimiter()
    app.dependency_overrides[get_session] = store
    app.dependency_overrides[get_feedback_submit_limiter] = lambda: submit
    app.dependency_overrides[get_feedback_unlock_limiter] = lambda: unlock
    kwargs = {"client": client} if client else {}
    return TestClient(app, raise_server_exceptions=False, **kwargs), submit, unlock


@pytest.fixture(scope="module")
def db_sessionmaker():
    """One isolated schema for this module; each test starts with no feedback rows."""
    with isolated_postgis_sessionmaker() as sessionmaker:
        yield sessionmaker


@pytest.fixture(autouse=True)
def _empty_feedback_table(request):
    if "db_sessionmaker" not in request.fixturenames:
        yield
        return
    sessionmaker = request.getfixturevalue("db_sessionmaker")

    async def clear():
        async with sessionmaker() as session:
            await session.execute(delete(ProjectFeedbackItem))
            await session.commit()

    asyncio.run(clear())
    yield


@pytest.fixture
def feedback(db_sessionmaker):
    client, submit, unlock = make_client(db_sessionmaker)
    with client:
        yield client, submit, unlock


def rows(db_sessionmaker) -> list[tuple]:
    async def fetch():
        async with db_sessionmaker() as session:
            result = await session.execute(
                select(
                    ProjectFeedbackItem.name,
                    ProjectFeedbackItem.page_path,
                    ProjectFeedbackItem.message,
                    ProjectFeedbackItem.submitter_user_id,
                    ProjectFeedbackItem.screenshot,
                    ProjectFeedbackItem.screenshot_width,
                    ProjectFeedbackItem.screenshot_height,
                    ProjectFeedbackItem.pin_x,
                    ProjectFeedbackItem.pin_y,
                    ProjectFeedbackItem.status,
                )
            )
            return list(result.all())

    return asyncio.run(fetch())


def insert_items(db_sessionmaker, specs) -> list[UUID]:
    async def insert():
        ids = []
        async with db_sessionmaker() as session:
            for spec in specs:
                item = ProjectFeedbackItem(
                    name="Seeded", page_path="/", message="Seeded note", status="opened"
                )
                for key, value in spec.items():
                    setattr(item, key, value)
                session.add(item)
                await session.flush()
                ids.append(item.id)
            await session.commit()
        return ids

    return asyncio.run(insert())


def data_url(image: Image.Image, fmt: str = "PNG", **save) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **save)
    mime = {"PNG": "png", "JPEG": "jpeg", "WEBP": "webp"}[fmt]
    return f"data:image/{mime};base64,{base64.b64encode(buffer.getvalue()).decode()}"


def unlock_token(client) -> str:
    response = client.post("/api/v1/feedback/review/unlock", json={"password": REVIEW_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def review_headers(client) -> dict[str, str]:
    return {"X-Feedback-Review-Token": unlock_token(client)}


# --- Submit --------------------------------------------------------------------


def test_anonymous_text_note_is_stored(feedback, db_sessionmaker):
    client, submit, _ = feedback
    response = client.post("/api/v1/feedback", json={**PAYLOAD, "name": "  Ada Tester  "})
    assert response.status_code == 200
    assert response.json() == {"status": "received"}
    ((name, path, message, user_id, shot, width, *_rest, status),) = rows(db_sessionmaker)
    assert (name, path, message, user_id, shot, width, status) == (
        "Ada Tester",
        "/advertiser/campaigns",
        "Button is odd.",
        None,
        None,
        None,
        "opened",
    )
    assert submit.ips == ["testclient"]


def test_signed_in_sender_comes_from_the_session(feedback, db_sessionmaker):
    client, _, _ = feedback
    user = create_test_user(db_sessionmaker, email="fb-driver@example.com", role=UserRole.DRIVER)
    headers = auth_headers(client, "fb-driver@example.com")
    assert client.post("/api/v1/feedback", json=PAYLOAD, headers=headers).status_code == 200
    assert rows(db_sessionmaker)[0][3] == user.id


def test_invalid_expired_and_password_change_sessions_are_stored_as_anonymous(
    feedback, db_sessionmaker
):
    client, _, _ = feedback
    settings = feedback_settings()
    user = create_test_user(db_sessionmaker, email="fb-admin@example.com")
    expired = create_access_token(
        user.id,
        settings,
        session_version=user.session_version,
        auth_time=datetime.now(UTC) - timedelta(hours=2),
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )[0]
    revoked = create_access_token(user.id, settings, session_version=999)[0]
    for token in ("not-a-jwt", expired, revoked):
        response = client.post(
            "/api/v1/feedback", json=PAYLOAD, headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    valid = auth_headers(client, "fb-admin@example.com")

    async def require_change():
        async with db_sessionmaker() as session:
            await session.execute(
                update(User).where(User.id == user.id).values(must_change_password=True)
            )
            await session.commit()

    asyncio.run(require_change())
    assert client.post("/api/v1/feedback", json=PAYLOAD, headers=valid).status_code == 200
    assert [row[3] for row in rows(db_sessionmaker)] == [None, None, None, None]


@pytest.mark.parametrize(
    "patch",
    [
        {"role": "admin"},
        {"submitter_user_id": str(uuid4())},
        {"user_id": str(uuid4())},
        {"name": " "},
        {"name": "x" * 121},
        {"name": "Ada\nTester"},
        {"message": "\t"},
        {"message": "x" * 5001},
        {"message": "bad\x00byte"},
        {"page_path": ""},
        {"page_path": "//evil.example/path"},
        {"page_path": "/\\evil.example"},
        {"page_path": "https://evil.example/"},
        {"page_path": "javascript:alert(1)"},
        {"page_path": "relative/page"},
        {"page_path": "/driver?token=secret"},
        {"page_path": "/driver#fragment"},
        {"page_path": "/driver\r\nSet-Cookie: x"},
        {"page_path": "/" + "x" * 500},
        {"screenshot": {"data_url": "data:image/png;base64,AAAA", "pin_x": 1.5, "pin_y": 0}},
        {"screenshot": {"data_url": "data:image/png;base64,AAAA", "pin_x": 0.5}},
        {"screenshot": {"data_url": "x", "pin_x": 0, "pin_y": 0, "extra": 1}},
    ],
)
def test_invalid_or_spoofed_fields_are_refused_before_the_limiter(feedback, db_sessionmaker, patch):
    client, submit, _ = feedback
    response = client.post("/api/v1/feedback", json={**PAYLOAD, **patch})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert submit.ips == []
    assert rows(db_sessionmaker) == []


def test_page_path_keeps_a_same_site_path(feedback, db_sessionmaker):
    client, _, _ = feedback
    for path in ("/", "/admin/driver-applications/123", "/driver"):
        assert client.post("/api/v1/feedback", json={**PAYLOAD, "page_path": path}).status_code == (
            200
        )
    assert sorted(row[1] for row in rows(db_sessionmaker)) == [
        "/",
        "/admin/driver-applications/123",
        "/driver",
    ]


def test_honeypot_looks_like_success_and_stores_nothing(feedback, db_sessionmaker):
    client, submit, _ = feedback
    response = client.post("/api/v1/feedback", json={**PAYLOAD, "website": "http://spam"})
    assert (response.status_code, response.json()) == (200, {"status": "received"})
    assert rows(db_sessionmaker) == []
    assert submit.ips == []


@pytest.mark.parametrize(
    "decision,expected,code",
    [
        (RateLimitDecision(allowed=False, retry_after_seconds=42), 429, "FEEDBACK_RATE_LIMITED"),
        (RateLimitDecision(allowed=False, storage_available=False), 503, "FEEDBACK_UNAVAILABLE"),
    ],
)
def test_limiter_refusals_store_nothing(db_sessionmaker, decision, expected, code):
    client, _, _ = make_client(db_sessionmaker, submit=FakeLimiter(decision=decision))
    response = client.post("/api/v1/feedback", json=PAYLOAD)
    assert (response.status_code, response.json()["error"]["code"]) == (expected, code)
    if expected == 429:
        assert response.headers["Retry-After"] == "42"
    assert rows(db_sessionmaker) == []


def test_without_redis_submit_and_unlock_are_unavailable(db_sessionmaker):
    app = create_app(feedback_settings(redis_url=None))

    async def store():
        async with db_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = store
    client = TestClient(app)
    assert client.post("/api/v1/feedback", json=PAYLOAD).status_code == 503
    unlock = client.post("/api/v1/feedback/review/unlock", json={"password": REVIEW_PASSWORD})
    assert unlock.status_code == 503
    assert rows(db_sessionmaker) == []


def test_relayed_client_ips_get_separate_buckets(db_sessionmaker):
    settings = feedback_settings(
        login_rate_limit_trust_client_ip_header=True,
        login_rate_limit_trusted_proxy_cidrs="127.0.0.1/32",
    )
    client, submit, unlock = make_client(
        db_sessionmaker,
        settings=settings,
        submit=FakeLimiter(limit=1),
        unlock=FakeLimiter(limit=1),
        client=("127.0.0.1", 50000),
    )
    first = {"X-Client-IP": "203.0.113.1"}
    second = {"X-Client-IP": "203.0.113.2"}
    assert client.post("/api/v1/feedback", json=PAYLOAD, headers=first).status_code == 200
    assert client.post("/api/v1/feedback", json=PAYLOAD, headers=first).status_code == 429
    assert client.post("/api/v1/feedback", json=PAYLOAD, headers=second).status_code == 200
    assert submit.ips == ["203.0.113.1", "203.0.113.1", "203.0.113.2"]
    body = {"password": "wrong-password"}
    assert client.post("/api/v1/feedback/review/unlock", json=body, headers=first).status_code == (
        401
    )
    assert client.post("/api/v1/feedback/review/unlock", json=body, headers=first).status_code == (
        429
    )
    assert unlock.ips == ["203.0.113.1", "203.0.113.1"]


def test_forged_client_ip_from_an_untrusted_peer_is_ignored(feedback):
    client, submit, _ = feedback
    client.post("/api/v1/feedback", json=PAYLOAD, headers={"X-Client-IP": "203.0.113.9"})
    assert submit.ips == ["testclient"]


@pytest.mark.parametrize(
    "body,content_type,expected",
    [
        ("not json", "application/json", 422),
        (json.dumps(PAYLOAD), "text/plain", 415),
        ("x" * (1024 * 1024 + 1), "application/json", 413),
        ("[]", "application/json", 422),
        ("[" * 4000 + "]" * 4000, "application/json", 422),
    ],
    ids=["not-json", "text-plain", "over-1mib", "array", "deep-json"],
)
def test_body_parsing_fails_safely(feedback, db_sessionmaker, body, content_type, expected):
    client, submit, _ = feedback
    response = client.post("/api/v1/feedback", content=body, headers={"Content-Type": content_type})
    assert response.status_code == expected
    assert submit.ips == []
    assert rows(db_sessionmaker) == []


def test_marked_screenshot_is_reencoded_without_metadata(feedback, db_sessionmaker):
    client, _, _ = feedback
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"
    source = data_url(Image.new("RGB", (2400, 1000), "red"), "JPEG", exif=exif)
    assert b"SecretCameraMaker" in base64.b64decode(source.split(",", 1)[1])
    response = client.post(
        "/api/v1/feedback",
        json={**PAYLOAD, "screenshot": {"data_url": source, "pin_x": 0.25, "pin_y": 0.75}},
    )
    assert response.status_code == 200, response.text
    ((*_, shot, width, height, pin_x, pin_y, _status),) = rows(db_sessionmaker)
    assert (width, height, pin_x, pin_y) == (1200, 500, 0.25, 0.75)
    assert b"SecretCameraMaker" not in shot
    with Image.open(io.BytesIO(shot)) as stored:
        assert stored.format == "JPEG"
        assert stored.size == (1200, 500)
        assert not stored.getexif()


@pytest.mark.parametrize("fmt", ["PNG", "WEBP"])
def test_png_and_webp_captures_are_accepted(feedback, db_sessionmaker, fmt):
    client, _, _ = feedback
    image = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    response = client.post(
        "/api/v1/feedback",
        json={**PAYLOAD, "screenshot": {"data_url": data_url(image, fmt), "pin_x": 0, "pin_y": 1}},
    )
    assert response.status_code == 200, response.text
    shot = rows(db_sessionmaker)[0][4]
    with Image.open(io.BytesIO(shot)) as stored:
        assert stored.size == (300, 200)
        assert stored.getpixel((10, 10)) == pytest.approx((255, 255, 255), abs=3)


def _bomb() -> str:
    return data_url(Image.new("1", (10000, 10000)), "PNG", optimize=True)


@pytest.mark.parametrize(
    "screenshot_url",
    [
        "data:image/gif;base64,R0lGODlhAQABAAAAACw=",
        "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",
        "data:image/png;base64,not*base64",
        "data:image/png;base64,",
        "data:image/png;base64," + base64.b64encode(b"not an image at all").decode(),
        # Declared PNG, actually JPEG: the declared decoder alone is used.
        "data:image/png;base64," + data_url(Image.new("RGB", (10, 10)), "JPEG").split(",", 1)[1],
        "https://evil.example/image.png",
    ],
)
def test_non_images_and_mismatched_types_are_refused(feedback, db_sessionmaker, screenshot_url):
    client, _, _ = feedback
    response = client.post(
        "/api/v1/feedback",
        json={**PAYLOAD, "screenshot": {"data_url": screenshot_url, "pin_x": 0, "pin_y": 0}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FEEDBACK_SCREENSHOT_INVALID"
    assert rows(db_sessionmaker) == []


def test_decompression_bomb_is_refused_before_decoding(feedback, db_sessionmaker):
    client, _, _ = feedback
    bomb = _bomb()
    assert len(bomb) < 200_000
    response = client.post(
        "/api/v1/feedback",
        json={**PAYLOAD, "screenshot": {"data_url": bomb, "pin_x": 0, "pin_y": 0}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FEEDBACK_SCREENSHOT_INVALID"
    assert rows(db_sessionmaker) == []


def test_oversize_and_tall_images_are_refused_by_the_decoder():
    oversize = (
        "data:image/png;base64," + base64.b64encode(b"x" * (MAX_SCREENSHOT_BYTES + 1)).decode()
    )
    with pytest.raises(AppError) as error:
        reencode_screenshot(oversize)
    assert error.value.status_code == 422
    with pytest.raises(AppError):
        reencode_screenshot(data_url(Image.new("RGB", (10, 4001)), "PNG"))


def test_feature_off_answers_404_everywhere(db_sessionmaker):
    for settings in (
        feedback_settings(feedback_enabled=False),
        feedback_settings(feedback_review_password=None),
    ):
        client, submit, unlock = make_client(db_sessionmaker, settings=settings)
        token = {"X-Feedback-Review-Token": "fbr1.1.x"}
        responses = [
            client.get("/api/v1/feedback/review", headers=token),
            client.patch(
                f"/api/v1/feedback/{uuid4()}/status", json={"status": "resolved"}, headers=token
            ),
            client.get(f"/api/v1/feedback/{uuid4()}/screenshot", headers=token),
            client.get("/api/v1/feedback/export.csv", headers=token),
            client.post("/api/v1/feedback/review/unlock", json={"password": REVIEW_PASSWORD}),
        ]
        if not settings.feedback_enabled:
            responses.append(client.post("/api/v1/feedback", json=PAYLOAD))
        for response in responses:
            assert (response.status_code, response.json()["error"]["code"]) == (
                404,
                "FEEDBACK_NOT_ENABLED",
            )
        assert unlock.ips == []
    assert rows(db_sessionmaker) == []


# --- Review --------------------------------------------------------------------


def test_unlock_refuses_wrong_password_and_issues_a_twelve_hour_token(feedback):
    client, _, unlock = feedback
    wrong = client.post("/api/v1/feedback/review/unlock", json={"password": "nope"})
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (
        401,
        "FEEDBACK_REVIEW_PASSWORD_MISMATCH",
    )
    assert REVIEW_PASSWORD not in wrong.text
    right = client.post("/api/v1/feedback/review/unlock", json={"password": REVIEW_PASSWORD})
    assert right.status_code == 200
    body = right.json()
    assert REVIEW_PASSWORD not in right.text
    expires = datetime.fromisoformat(body["expires_at"])
    assert timedelta(hours=11, minutes=59) < expires - datetime.now(UTC) <= timedelta(hours=12)
    assert len(unlock.ips) == 2
    headers = {"X-Feedback-Review-Token": body["token"]}
    assert client.get("/api/v1/feedback/review", headers=headers).status_code == 200


def test_unlock_rate_limit_answers_429(db_sessionmaker):
    limited = FakeLimiter(decision=RateLimitDecision(allowed=False, retry_after_seconds=7))
    client, _, _ = make_client(db_sessionmaker, unlock=limited)
    response = client.post("/api/v1/feedback/review/unlock", json={"password": REVIEW_PASSWORD})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "7"


def test_review_routes_refuse_missing_tampered_expired_and_session_tokens(
    feedback, db_sessionmaker
):
    client, _, _ = feedback
    create_test_user(db_sessionmaker, email="fb-staff@example.com")
    session_jwt = auth_headers(client, "fb-staff@example.com")["Authorization"].split()[1]
    token = unlock_token(client)
    prefix, expires, mac = token.split(".")
    other = feedback_settings(feedback_review_password="a-different-review-password")
    other_client, _, _ = make_client(db_sessionmaker, settings=other)
    other_token = unlock_token_for(other_client, "a-different-review-password")
    candidates = [
        None,
        "",
        session_jwt,
        f"{prefix}.{int(expires) + 3600}.{mac}",
        f"{prefix}.{expires}.{mac[:-2]}AA",
        f"fbr2.{expires}.{mac}",
        other_token,
        "x" * 500,
    ]
    for candidate in candidates:
        headers = {} if candidate is None else {"X-Feedback-Review-Token": candidate}
        response = client.get("/api/v1/feedback/review", headers=headers)
        assert (response.status_code, response.json()["error"]["code"]) == (
            401,
            "FEEDBACK_REVIEW_TOKEN_INVALID",
        ), candidate
    later = datetime.now(UTC) + timedelta(hours=12, seconds=1)
    with clock.use_clock(lambda: later):
        response = client.get("/api/v1/feedback/review", headers={"X-Feedback-Review-Token": token})
    assert response.status_code == 401
    assert (
        client.get(
            "/api/v1/feedback/review", headers={"X-Feedback-Review-Token": token}
        ).status_code
        == 200
    )


def unlock_token_for(client, password: str) -> str:
    response = client.post("/api/v1/feedback/review/unlock", json={"password": password})
    assert response.status_code == 200
    return response.json()["token"]


def test_every_review_route_is_classified_and_refuses_without_a_review_token(
    feedback, db_sessionmaker
):
    client, _, _ = feedback
    inventory = {route.key: route for route in authorization_inventory()}
    assert {
        key for key, route in inventory.items() if route.principal is Principal.PROJECT_REVIEW
    } == PROJECT_REVIEW_ROUTES
    create_test_user(db_sessionmaker, email="fb-matrix@example.com")
    bearer = auth_headers(client, "fb-matrix@example.com")
    for method, path in PROJECT_REVIEW_ROUTES:
        concrete = path.replace("{feedback_id}", str(uuid4()))
        kwargs = {"json": {"status": "resolved"}} if method == "PATCH" else {}
        for headers in ({}, bearer):
            response = client.request(method, concrete, headers=headers, **kwargs)
            assert response.status_code == 401, (method, path)


def test_review_list_pages_newest_first_with_counts(feedback, db_sessionmaker):
    client, _, _ = feedback
    base = datetime(2026, 11, 1, 9, tzinfo=UTC)
    insert_items(
        db_sessionmaker,
        [
            {"message": f"opened {index}", "created_at": base + timedelta(minutes=index)}
            for index in range(12)
        ]
        + [
            {
                "message": f"resolved {index}",
                "status": "resolved",
                "resolved_at": base + timedelta(days=1),
                "created_at": base + timedelta(minutes=index),
            }
            for index in range(2)
        ],
    )
    headers = review_headers(client)
    first = client.get("/api/v1/feedback/review", headers=headers).json()
    assert first["counts"] == {"opened": 12, "resolved": 2}
    assert (first["total"], first["limit"], first["offset"]) == (12, 10, 0)
    assert [item["message"] for item in first["items"]] == [
        f"opened {index}" for index in range(11, 1, -1)
    ]
    second = client.get("/api/v1/feedback/review", headers=headers, params={"offset": 10}).json()
    assert [item["message"] for item in second["items"]] == ["opened 1", "opened 0"]
    resolved = client.get(
        "/api/v1/feedback/review", headers=headers, params={"status": "resolved", "limit": 1}
    ).json()
    assert resolved["total"] == 2
    assert [item["message"] for item in resolved["items"]] == ["resolved 1"]
    for params in ({"limit": 0}, {"limit": 51}, {"offset": -1}, {"status": "deleted"}):
        assert client.get(
            "/api/v1/feedback/review", headers=headers, params=params
        ).status_code == (422)


def test_review_item_shape_and_portal_labels(feedback, db_sessionmaker):
    client, _, _ = feedback
    user = create_test_user(db_sessionmaker, email="fb-shape@example.com")
    paths = ["/", "/advertiser", "/driver/trips", "/admin/campaigns", "/advertisers"]
    insert_items(
        db_sessionmaker,
        [
            {"page_path": path, "created_at": datetime(2026, 11, 1, 9, index, tzinfo=UTC)}
            for index, path in enumerate(paths)
        ]
        + [
            {
                "page_path": "/driver",
                "submitter_user_id": user.id,
                "created_at": datetime(2026, 11, 2, tzinfo=UTC),
                "screenshot": b"jpeg",
                "screenshot_width": 1200,
                "screenshot_height": 600,
                "pin_x": 0.5,
                "pin_y": 0.25,
            }
        ],
    )
    items = client.get("/api/v1/feedback/review", headers=review_headers(client)).json()["items"]
    newest = items[0]
    assert set(newest) == {
        "id",
        "name",
        "page_path",
        "portal",
        "message",
        "status",
        "created_at",
        "resolved_at",
        "signed_in",
        "has_screenshot",
        "screenshot_width",
        "screenshot_height",
        "pin_x",
        "pin_y",
    }
    assert (newest["signed_in"], newest["has_screenshot"], newest["pin_x"], newest["pin_y"]) == (
        True,
        True,
        0.5,
        0.25,
    )
    assert [item["portal"] for item in items[1:]] == [
        "public",
        "staff",
        "driver",
        "advertiser",
        "public",
    ]
    assert items[1]["has_screenshot"] is False and items[1]["signed_in"] is False


def test_status_change_resolves_reopens_and_updates_counts(feedback, db_sessionmaker):
    client, _, _ = feedback
    (item_id,) = insert_items(db_sessionmaker, [{}])
    headers = review_headers(client)
    path = f"/api/v1/feedback/{item_id}/status"
    resolved = client.patch(path, json={"status": "resolved"}, headers=headers)
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolved_at"] is not None
    counts = client.get("/api/v1/feedback/review", headers=headers).json()["counts"]
    assert counts == {"opened": 0, "resolved": 1}
    reopened = client.patch(path, json={"status": "opened"}, headers=headers).json()
    assert (reopened["status"], reopened["resolved_at"]) == ("opened", None)
    assert client.patch(path, json={"status": "deleted"}, headers=headers).status_code == 422
    missing = client.patch(
        f"/api/v1/feedback/{uuid4()}/status", json={"status": "resolved"}, headers=headers
    )
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "FEEDBACK_NOT_FOUND")


def test_screenshot_endpoint_serves_stored_jpeg_without_caching(feedback, db_sessionmaker):
    client, _, _ = feedback
    with_shot, without = insert_items(
        db_sessionmaker,
        [
            {
                "screenshot": b"\xff\xd8stored-jpeg",
                "screenshot_width": 10,
                "screenshot_height": 10,
                "pin_x": 0.1,
                "pin_y": 0.2,
            },
            {},
        ],
    )
    headers = review_headers(client)
    response = client.get(f"/api/v1/feedback/{with_shot}/screenshot", headers=headers)
    assert response.status_code == 200
    assert response.content == b"\xff\xd8stored-jpeg"
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"
    for item_id in (without, uuid4()):
        assert client.get(
            f"/api/v1/feedback/{item_id}/screenshot", headers=headers
        ).status_code == (404)


def test_csv_export_lists_every_note_with_neutralised_cells(feedback, db_sessionmaker):
    client, _, _ = feedback
    insert_items(
        db_sessionmaker,
        [
            {
                "name": '=HYPERLINK("https://evil.example")',
                "message": "+SUM(1,2)",
                "page_path": "/driver",
                "created_at": datetime(2026, 11, 2, tzinfo=UTC),
                "screenshot": b"jpeg",
                "screenshot_width": 1,
                "screenshot_height": 1,
                "pin_x": 0,
                "pin_y": 0,
            },
            {
                "name": "@Ada",
                "message": "-1 plain",
                "status": "resolved",
                "resolved_at": datetime(2026, 11, 3, tzinfo=UTC),
                "created_at": datetime(2026, 11, 1, tzinfo=UTC),
            },
        ],
    )
    response = client.get("/api/v1/feedback/export.csv", headers=review_headers(client))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]
    table = list(csv.reader(io.StringIO(response.text)))
    assert table[0] == [
        "created_at",
        "status",
        "portal",
        "name",
        "page_path",
        "message",
        "has_screenshot",
        "resolved_at",
    ]
    assert [row[1:7] for row in table[1:]] == [
        [
            "opened",
            "driver",
            '\'=HYPERLINK("https://evil.example")',
            "/driver",
            "'+SUM(1,2)",
            "yes",
        ],
        ["resolved", "public", "'@Ada", "/", "'-1 plain", "no"],
    ]
    assert table[1][7] == "" and table[2][7].startswith("2026-11-03")
    assert "jpeg" not in response.text


# --- Settings, limiter and migration -----------------------------------------


def test_settings_validate_password_length_and_refuse_production():
    with pytest.raises(ValidationError, match="at least 20 characters"):
        feedback_settings(feedback_review_password="short-password")
    assert feedback_settings(feedback_review_password="").feedback_review_password is None
    with pytest.raises(ValidationError, match="FEEDBACK_ENABLED is refused in production"):
        production_settings(feedback_enabled=True)
    assert production_settings().feedback_enabled is False
    staging = production_settings(environment="staging", feedback_enabled=True)
    assert staging.feedback_enabled is True


def test_feedback_limits_are_fixed_constants():
    fixed = Settings(
        _env_file=None, feedback_submit_ip_max_attempts=0, feedback_review_token_ttl_seconds=1
    )
    assert fixed.feedback_submit_ip_max_attempts == 10
    assert fixed.feedback_submit_global_max_attempts == 300
    assert fixed.feedback_submit_global_window_seconds == 86400
    assert fixed.feedback_unlock_ip_max_attempts == 10
    assert fixed.feedback_review_token_ttl_seconds == 43200
    for name in ("feedback_submit_ip_max_attempts", "feedback_review_token_ttl_seconds"):
        assert name not in Settings.model_fields


def test_real_redis_feedback_buckets_use_their_own_windows():
    async def run():
        async with Redis.from_url("redis://localhost:6379/0", decode_responses=True) as redis:
            prefix = f"test:feedback:{uuid4()}"
            limits = PublicSubmitLimits(prefix, 2, 600, 3, 86400)
            limiter = RedisEnquiryRateLimiter(redis, Settings(_env_file=None), limits)
            assert limiter.keys("a")[0].startswith(f"ratelimit:{prefix}:ip:")
            assert [(await limiter.reserve("a")).allowed for _ in range(3)] == [True, True, False]
            assert (await limiter.reserve("b")).allowed
            blocked = await limiter.reserve("c")
            assert not blocked.allowed and 600 < blocked.retry_after_seconds <= 86400
            ip_key, global_key = limiter.keys("a")
            assert 0 < await redis.ttl(ip_key) <= 600
            assert 600 < await redis.ttl(global_key) <= 86400
            await redis.delete(
                *[key async for key in redis.scan_iter(match=f"ratelimit:{prefix}:*")]
            )

    asyncio.run(run())


def test_migration_upgrades_matches_models_and_downgrades(monkeypatch):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(url, "0122_receipt_non_receipts", monkeypatch)
        upgrade_to(url, "head", monkeypatch)
        command.check(Config("alembic.ini"))
        table = "SELECT to_regclass('project_feedback_items')::text"
        assert asyncio.run(fetch_all(url, table)) == [("project_feedback_items",)]
        command.downgrade(Config("alembic.ini"), "0122_receipt_non_receipts")
        assert asyncio.run(fetch_all(url, table)) == [(None,)]
        upgrade_to(url, "head", monkeypatch)
        assert asyncio.run(fetch_all(url, table)) == [("project_feedback_items",)]
    finally:
        asyncio.run(drop_database(url))

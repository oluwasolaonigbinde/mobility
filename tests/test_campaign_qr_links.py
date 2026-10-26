import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_campaign_creative,
    create_test_organization,
    create_test_user,
)
from sqlalchemy import select, update
from test_campaign_live_positions import PASSWORD, driving_graph  # noqa: F401

from app.api.v1.campaign_engagement import get_qr_limiter
from app.core.rate_limit import RateLimitDecision
from app.models.audit import AuditEvent
from app.models.campaign_engagement import ArtworkLink, ArtworkScanDay
from app.models.organization import OrganizationMembership
from app.models.user import UserRole
from app.services import campaign_engagement


@pytest.fixture
def qr_graph(db_client, db_sessionmaker, driving_graph, settings, monkeypatch):  # noqa: F811
    settings.public_origin = "http://localhost:3220"
    settings.environment = "test"
    limiter = AsyncMock()
    limiter.reserve.return_value = RateLimitDecision(allowed=True)
    db_client.app.dependency_overrides[get_qr_limiter] = lambda: limiter

    async def clock(_session):
        return datetime(2026, 10, 20, 23, 30, tzinfo=UTC)

    monkeypatch.setattr(campaign_engagement, "database_clock", clock)
    creative = create_test_campaign_creative(
        db_sessionmaker, campaign_id=driving_graph["campaign"].id
    )
    path = f"/api/v1/advertiser/campaigns/{driving_graph['campaign'].id}/creatives/{creative.id}"
    return {
        **driving_graph,
        "creative": creative,
        "path": path,
        "limiter": limiter,
        "headers": auth_headers(db_client, driving_graph["owner"].email, PASSWORD),
    }


def save(client, graph, destination="https://example.com/order"):
    return client.put(
        graph["path"] + "/website", headers=graph["headers"], json={"destination": destination}
    )


def test_one_link_per_artwork_stable_code_and_stored_destination_only(
    db_client, db_sessionmaker, qr_graph
):
    empty = db_client.get(qr_graph["path"] + "/website", headers=qr_graph["headers"]).json()
    assert empty["destination"] is None and empty["scans"] == 0
    first = save(db_client, qr_graph)
    assert first.status_code == 200
    data = first.json()
    assert data["destination"] == "https://example.com/order"
    code = data["short_path"].split("/")[-1]
    assert len(code) == 32
    response = db_client.get(
        f"/api/v1/qr/{code}?url=https://attacker.com&next=https://attacker.com",
        follow_redirects=False,
        headers={"User-Agent": "private browser", "X-Forwarded-For": "192.0.2.45"},
    )
    assert (
        response.status_code == 302 and response.headers["location"] == "https://example.com/order"
    )
    assert (
        response.headers["cache-control"] == "no-store"
        and response.headers["referrer-policy"] == "no-referrer"
    )
    changed = save(db_client, qr_graph, "https://example.org/new")
    assert changed.json()["short_path"] == data["short_path"]
    assert (
        db_client.get(f"/api/v1/qr/{code}", follow_redirects=False).headers["location"]
        == "https://example.org/new"
    )
    assert db_client.head(f"/api/v1/qr/{code}", follow_redirects=False).status_code == 302
    result = db_client.get(qr_graph["path"] + "/website", headers=qr_graph["headers"]).json()
    assert result["scans"] == 2 and result["days"] == [{"day": "2026-10-21", "scans": 2}]
    scans = db_client.get(
        f"/api/v1/advertiser/campaigns/{qr_graph['campaign'].id}/qr-scans",
        headers=qr_graph["headers"],
    ).json()
    assert scans["scans"] == 2

    async def audit():
        async with db_sessionmaker() as session:
            events = (
                await session.scalars(
                    select(AuditEvent).where(AuditEvent.action == "creative.website_updated")
                )
            ).all()
            assert len(events) == 2
            assert all(event.actor_user_id == qr_graph["owner"].id for event in events)
            assert all(
                event.event_metadata == {"campaign_id": str(qr_graph["campaign"].id)}
                for event in events
            )

    asyncio.run(audit())


@pytest.mark.parametrize(
    "destination",
    [
        "http://example.com",
        "https://localhost",
        "https://name:password@example.com",
        "https://example.com:444",
    ],
)
def test_invalid_links_do_not_overwrite_valid_destination(db_client, qr_graph, destination):
    save(db_client, qr_graph)
    assert save(db_client, qr_graph, destination).status_code == 422
    assert (
        db_client.get(qr_graph["path"] + "/website", headers=qr_graph["headers"]).json()[
            "destination"
        ]
        == "https://example.com/order"
    )


def test_download_encodes_cardvert_short_url_and_never_counts_as_scan(
    db_client, qr_graph, monkeypatch
):
    from app.api.v1 import campaign_engagement as api

    assert (
        db_client.get(qr_graph["path"] + "/qr.svg", headers=qr_graph["headers"]).status_code == 409
    )
    data = save(db_client, qr_graph).json()
    make = api.qrcode.make
    encoded = []

    def capture(value, **kwargs):
        encoded.append(value)
        return make(value, **kwargs)

    monkeypatch.setattr(api.qrcode, "make", capture)
    response = db_client.get(qr_graph["path"] + "/qr.svg", headers=qr_graph["headers"])
    assert response.status_code == 200 and b"<svg" in response.content
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "attachment" in response.headers["content-disposition"]
    assert encoded == ["http://localhost:3220" + data["short_path"]]
    assert (
        db_client.get(qr_graph["path"] + "/website", headers=qr_graph["headers"]).json()["scans"]
        == 0
    )


@pytest.mark.parametrize(
    "origin",
    ["https://cardvert.example:bad", "https://cardvert.example/path", "http://cardvert.example"],
)
def test_invalid_configured_origin_never_produces_a_printable_code(
    db_client, qr_graph, settings, origin
):
    save(db_client, qr_graph)
    settings.public_origin = origin
    response = db_client.get(qr_graph["path"] + "/qr.svg", headers=qr_graph["headers"])
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "QR_ORIGIN_UNAVAILABLE"


def test_rate_limit_outage_unknown_and_tampered_stored_url_fail_closed(
    db_client, db_sessionmaker, qr_graph
):
    link = save(db_client, qr_graph).json()
    code = link["short_path"].split("/")[-1]
    qr_graph["limiter"].reserve.return_value = RateLimitDecision(
        allowed=False, retry_after_seconds=50
    )
    denied = db_client.get(f"/api/v1/qr/{code}", follow_redirects=False)
    assert (
        denied.status_code == 429
        and denied.headers["retry-after"] == "50"
        and "location" not in denied.headers
    )
    qr_graph["limiter"].reserve.return_value = RateLimitDecision(
        allowed=False, storage_available=False
    )
    assert db_client.get(f"/api/v1/qr/{code}", follow_redirects=False).status_code == 503
    qr_graph["limiter"].reserve.return_value = RateLimitDecision(allowed=True)
    assert db_client.get("/api/v1/qr/" + "0" * 32, follow_redirects=False).status_code == 404

    async def tamper():
        async with db_sessionmaker() as session:
            await session.execute(
                update(ArtworkLink)
                .where(ArtworkLink.creative_id == qr_graph["creative"].id)
                .values(destination="javascript:alert(1)")
            )
            await session.commit()

    asyncio.run(tamper())
    assert db_client.get(f"/api/v1/qr/{code}", follow_redirects=False).status_code == 404


def test_tenant_roles_and_inactive_membership_cannot_manage_or_download(
    db_client, db_sessionmaker, qr_graph
):
    save(db_client, qr_graph)
    stranger = create_test_user(
        db_sessionmaker, email="other-qr@example.com", password=PASSWORD, role=UserRole.ADVERTISER
    )
    create_test_organization(db_sessionmaker, owner_user_id=stranger.id, name="Other QR company")
    headers = auth_headers(db_client, stranger.email, PASSWORD)
    assert db_client.get(qr_graph["path"] + "/website", headers=headers).status_code == 404
    assert (
        db_client.put(
            qr_graph["path"] + "/website",
            headers=headers,
            json={"destination": "https://example.com"},
        ).status_code
        == 404
    )
    assert db_client.get(qr_graph["path"] + "/qr.svg", headers=headers).status_code == 404

    async def disable():
        async with db_sessionmaker() as session:
            await session.execute(
                update(OrganizationMembership)
                .where(OrganizationMembership.id == qr_graph["membership"].id)
                .values(status="disabled")
            )
            await session.commit()

    asyncio.run(disable())
    assert db_client.put(
        qr_graph["path"] + "/website",
        headers=qr_graph["headers"],
        json={"destination": "https://example.com"},
    ).status_code in {403, 404}


def test_concurrent_increments_are_atomic_and_store_only_daily_buckets(
    db_client, db_sessionmaker, qr_graph
):
    code = save(db_client, qr_graph).json()["short_path"].split("/")[-1]

    async def scan():
        async with db_sessionmaker() as session:
            return await campaign_engagement.stored_destination(session, code=code, count_scan=True)

    async def run():
        assert (
            await asyncio.gather(*(scan() for _ in range(6))) == ["https://example.com/order"] * 6
        )
        async with db_sessionmaker() as session:
            rows = list(await session.scalars(select(ArtworkScanDay)))
            assert len(rows) == 1 and rows[0].scans == 6

    asyncio.run(run())
    assert set(ArtworkScanDay.__table__.columns.keys()) == {"creative_id", "day", "scans"}


def test_disabled_membership_cannot_read_print_or_change_the_website(
    db_client, db_sessionmaker, qr_graph
):
    save(db_client, qr_graph)

    async def disable_membership():
        async with db_sessionmaker() as session:
            await session.execute(
                update(OrganizationMembership)
                .where(OrganizationMembership.id == qr_graph["membership"].id)
                .values(status="disabled")
            )
            await session.commit()

    asyncio.run(disable_membership())
    assert (
        db_client.get(qr_graph["path"] + "/website", headers=qr_graph["headers"]).status_code == 404
    )
    assert (
        db_client.get(qr_graph["path"] + "/qr.svg", headers=qr_graph["headers"]).status_code == 404
    )
    assert save(db_client, qr_graph, "https://example.org/changed").status_code == 404

    async def unchanged():
        async with db_sessionmaker() as session:
            link = await session.get(ArtworkLink, qr_graph["creative"].id)
            assert link.destination == "https://example.com/order"

    asyncio.run(unchanged())


def test_database_write_failure_never_returns_a_successful_counted_redirect(monkeypatch, client):
    from fastapi.testclient import TestClient

    from app.db.session import get_session
    from app.models.campaign_engagement import ArtworkLink
    from app.services.campaign_engagement import stored_destination

    session = AsyncMock()
    session.scalar.return_value = ArtworkLink(
        creative_id=uuid4(), code="a" * 32, destination="https://example.com"
    )

    async def clock(_session):
        return datetime(2026, 10, 20, tzinfo=UTC)

    monkeypatch.setattr(campaign_engagement, "database_clock", clock)
    session.commit.side_effect = RuntimeError("unavailable")
    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(stored_destination(session, code="a" * 32, count_scan=True))

    async def failed_session():
        yield session

    limiter = AsyncMock()
    limiter.reserve.return_value = RateLimitDecision(allowed=True)
    client.app.dependency_overrides[get_session] = failed_session
    client.app.dependency_overrides[get_qr_limiter] = lambda: limiter
    with TestClient(client.app, raise_server_exceptions=False) as http:
        response = http.get("/api/v1/qr/" + "a" * 32, follow_redirects=False)
    assert response.status_code == 500
    assert "location" not in response.headers
    assert "unavailable" not in response.text

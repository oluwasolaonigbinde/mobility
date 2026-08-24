from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import auth_headers, create_test_organization, create_test_user
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.retargeting_source import RetargetingSource, RetargetingSourceEvent
from app.models.user import UserRole
from app.schemas.retargeting_sources import RetargetingSourceCreate, RetargetingSourceRead
from app.services.audience import create_retargeting_source, list_admin_retargeting_sources

PASSWORD = "StrongPassword123!"


def payload(source_type: str) -> dict:
    common = {
        "source_type": source_type,
        "provenance": "advertiser-declared",
        "lawful_basis_reference": "candidate-legitimate-interest",
        "lawful_basis_status": "unapproved",
        "consent_disclaimer_status": "not-reviewed",
        "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        "dsr_owner_role": "privacy-officer",
        "dsr_status": "pending",
    }
    variants = {
        "website-traffic": {
            "audience_category": "site-visitor",
            "aggregation_window_days": 30,
        },
        "digital-campaign-audience": {
            "channel": "social",
            "audience_stage": "awareness",
            "aggregation_window_days": 30,
        },
        "CRM-upload-reference": {
            "reference_mode": "aggregate-availability-only",
            "record_count_band": "100-999",
        },
        "UTM-source": {"channel": "search", "campaign_stage": "consideration"},
        "manual-insight": {"insight_category": "area-demand", "confidence_band": "medium"},
    }
    return common | variants[source_type]


def test_all_five_allowlisted_source_shapes_and_forbidden_fields() -> None:
    adapter = TypeAdapter(RetargetingSourceCreate)
    for source_type in (
        "website-traffic",
        "digital-campaign-audience",
        "CRM-upload-reference",
        "UTM-source",
        "manual-insight",
    ):
        assert adapter.validate_python(payload(source_type)).source_type == source_type

    for forbidden in ("email", "phone", "url", "upload", "notes", "metadata", "driver_id"):
        with pytest.raises(ValidationError):
            adapter.validate_python(payload("manual-insight") | {forbidden: "forbidden"})

    read_payload = {
        "id": uuid4(),
        "organization_id": uuid4(),
        "source_type": "manual-insight",
        "snapshot": payload("manual-insight") | {"notes": {"person": "hidden"}},
        "snapshot_sha256": "a" * 64,
        "status": "active",
        "expires_at": datetime.now(UTC) + timedelta(days=1),
        "created_at": datetime.now(UTC),
        "deactivated_at": None,
    }
    with pytest.raises(ValidationError):
        RetargetingSourceRead.model_validate(read_payload)


def test_registry_lifecycle_retry_history_tenant_and_admin_monitoring(
    db_client, db_sessionmaker
) -> None:
    advertiser = create_test_user(
        db_sessionmaker, email="source-owner@example.com", password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    other = create_test_user(
        db_sessionmaker, email="source-other@example.com", password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    admin = create_test_user(
        db_sessionmaker, email="source-admin@example.com", password=PASSWORD,
        role=UserRole.ADMIN,
    )
    create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    create_test_organization(db_sessionmaker, name="Other Ads", owner_user_id=other.id)
    owner_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    other_headers = auth_headers(db_client, other.email, PASSWORD)
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)

    created = db_client.post(
        "/api/v1/advertiser/retargeting-sources",
        headers=owner_headers | {"Idempotency-Key": "source-create-1"},
        json=payload("website-traffic"),
    )
    assert created.status_code == 201, created.text
    source = created.json()
    replay = db_client.post(
        "/api/v1/advertiser/retargeting-sources",
        headers=owner_headers | {"Idempotency-Key": "source-create-1"},
        json=payload("website-traffic") | {"expires_at": source["expires_at"]},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == source["id"]
    conflict = db_client.post(
        "/api/v1/advertiser/retargeting-sources",
        headers=owner_headers | {"Idempotency-Key": "source-create-1"},
        json=payload("manual-insight"),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "RETARGETING_SOURCE_IDEMPOTENCY_CONFLICT"

    assert db_client.get(
        f"/api/v1/advertiser/retargeting-sources/{source['id']}", headers=other_headers
    ).status_code == 404
    monitor = db_client.get("/api/v1/admin/retargeting-sources", headers=admin_headers)
    assert monitor.status_code == 200
    assert monitor.json()["total"] == 1

    deactivated = db_client.post(
        f"/api/v1/advertiser/retargeting-sources/{source['id']}/deactivate",
        headers=owner_headers | {"Idempotency-Key": "source-deactivate-1"},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "deactivated"
    deactivation_replay = db_client.post(
        f"/api/v1/advertiser/retargeting-sources/{source['id']}/deactivate",
        headers=owner_headers | {"Idempotency-Key": "source-deactivate-1"},
    )
    assert deactivation_replay.status_code == 200
    history = db_client.get(
        f"/api/v1/advertiser/retargeting-sources/{source['id']}/history",
        headers=owner_headers,
    ).json()
    assert [event["event_type"] for event in history["events"]] == ["created", "deactivated"]
    assert all(len(event["snapshot_sha256"]) == 64 for event in history["events"])

    async def counts() -> tuple[int, int, int]:
        async with db_sessionmaker() as session:
            return (
                int(await session.scalar(select(func.count()).select_from(RetargetingSource)) or 0),
                int(
                    await session.scalar(select(func.count()).select_from(RetargetingSourceEvent))
                    or 0
                ),
                int(
                    await session.scalar(
                        select(func.count())
                        .select_from(AuditEvent)
                        .where(AuditEvent.entity_type == "retargeting_source")
                    )
                    or 0
                ),
            )

    assert asyncio.run(counts()) == (1, 2, 2)


def test_live_gate_runs_before_admin_registry_read() -> None:
    class NoReadSession:
        async def scalars(self, *_args, **_kwargs):
            raise AssertionError("privacy gate must run before database reads")

    async def scenario() -> None:
        with pytest.raises(AppError) as blocked:
            await list_admin_retargeting_sources(NoReadSession(), settings=Settings())  # type: ignore[arg-type]
        assert blocked.value.code == "PRIVACY_LIVE_USE_BLOCKED"

    asyncio.run(scenario())


def test_expired_source_is_derived_without_history_rewrite(db_client, db_sessionmaker) -> None:
    advertiser = create_test_user(
        db_sessionmaker, email="source-expiry@example.com", password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    headers = auth_headers(db_client, advertiser.email, PASSWORD)
    created = db_client.post(
        "/api/v1/advertiser/retargeting-sources",
        headers=headers | {"Idempotency-Key": "source-expiry-1"},
        json=payload("manual-insight"),
    ).json()

    async def expire() -> None:
        async with db_sessionmaker() as session:
            source = await session.get(RetargetingSource, UUID(created["id"]))
            assert source is not None
            source.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire())
    current = db_client.get(
        f"/api/v1/advertiser/retargeting-sources/{created['id']}", headers=headers
    ).json()
    history = db_client.get(
        f"/api/v1/advertiser/retargeting-sources/{created['id']}/history", headers=headers
    ).json()
    assert current["status"] == "expired"
    assert [event["event_type"] for event in history["events"]] == ["created"]


def test_registry_rejects_when_synthetic_gate_is_disabled(
    db_client, db_sessionmaker, settings
) -> None:
    advertiser = create_test_user(
        db_sessionmaker, email="source-blocked@example.com", password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    db_client.app.dependency_overrides[get_settings] = lambda: settings.model_copy(
        update={"privacy_disclosure_synthetic_test_mode": False}
    )
    response = db_client.get(
        "/api/v1/advertiser/retargeting-sources",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PRIVACY_LIVE_USE_BLOCKED"


def test_concurrent_create_retry_converges_on_postgres(postgis_db_sessionmaker) -> None:
    advertiser = create_test_user(
        postgis_db_sessionmaker,
        email="source-race@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    create_test_organization(postgis_db_sessionmaker, owner_user_id=advertiser.id)
    typed = TypeAdapter(RetargetingSourceCreate).validate_python(payload("manual-insight"))
    settings = Settings(environment="test", privacy_disclosure_synthetic_test_mode=True)

    async def create_once():
        async with postgis_db_sessionmaker() as session:
            source = await create_retargeting_source(
                session,
                settings=settings,
                actor_user_id=advertiser.id,
                payload=typed,
                idempotency_key="source-concurrent-1",
            )
            await session.commit()
            return source.id

    async def scenario() -> None:
        first, second = await asyncio.gather(create_once(), create_once())
        assert first == second
        async with postgis_db_sessionmaker() as session:
            assert int(
                await session.scalar(select(func.count()).select_from(RetargetingSource)) or 0
            ) == 1
            assert int(
                await session.scalar(select(func.count()).select_from(RetargetingSourceEvent))
                or 0
            ) == 1
            assert int(
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.entity_type == "retargeting_source")
                )
                or 0
            ) == 1
            changed = TypeAdapter(RetargetingSourceCreate).validate_python(
                payload("manual-insight") | {"confidence_band": "high"}
            )
            with pytest.raises(AppError) as conflict:
                await create_retargeting_source(
                    session,
                    settings=settings,
                    actor_user_id=advertiser.id,
                    payload=changed,
                    idempotency_key="source-concurrent-1",
                )
            assert conflict.value.code == "RETARGETING_SOURCE_IDEMPOTENCY_CONFLICT"

    asyncio.run(scenario())

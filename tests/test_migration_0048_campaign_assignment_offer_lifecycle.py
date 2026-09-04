"""Migration 0048: legacy evidence stays identifiable and new evidence is durable."""

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from conftest import (
    create_test_campaign,
    create_test_driver_profile,
    create_test_organization,
    create_test_payout_rule,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    fetch_all,
    upgrade_to,
)

from app.models.campaign import CampaignStatus
from app.models.driver import DriverOnboardingStatus
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus

PRE_OFFER_REVISION = "0047_retargeting_source_links"
OFFER_REVISION = "0048_campaign_assignment_offer_lifecycle"
R18_PREVIOUS_REVISION = "0080_trip_evidence_partial_disposition"


def test_offer_migration_static_shape_and_sqlite_branch() -> None:
    migration = Path(
        "alembic/versions/0048_campaign_assignment_offer_lifecycle.py"
    ).read_text()
    assert 'revision: str = "0048_campaign_assignment_offer_lifecycle"' in migration
    assert f'down_revision: str | Sequence[str] | None = "{PRE_OFFER_REVISION}"' in migration
    assert "offer_terms_sha256" in migration
    assert "campaign_activation_events_append_only_update" in migration
    assert "assignment_rule_binding_offer_evidence_immutable" in migration
    assert 'bind.dialect.name == "sqlite"' in migration
    assert "recreate=\"always\"" in migration
    assert "0048 downgrade blocked" in migration


def test_legacy_roundtrip_and_new_evidence_downgrade_guard(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))

    def seed_legacy() -> dict:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        admin = create_test_user(
            sessionmaker,
            email=f"migration-admin-{uuid4().hex}@example.com",
            password="migration-password",
        )
        driver = create_test_user(
            sessionmaker,
            email=f"migration-driver-{uuid4().hex}@example.com",
            password="migration-password",
            role=UserRole.DRIVER,
        )
        organization, _ = create_test_organization(sessionmaker, owner_user_id=admin.id)
        campaign = create_test_campaign(
            sessionmaker,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            campaign_status=CampaignStatus.DRAFT,
        )
        profile = create_test_driver_profile(
            sessionmaker,
            user_id=driver.id,
            onboarding_status=DriverOnboardingStatus.ACTIVE,
        )
        vehicle = create_test_vehicle(
            sessionmaker,
            driver_profile_id=profile.id,
            vehicle_status=VehicleStatus.ACTIVE,
            plate_number=f"MIG-{uuid4().hex[:8]}",
        )
        rule = create_test_payout_rule(
            sessionmaker,
            campaign_id=campaign.id,
            created_by_user_id=admin.id,
        )
        revision_id = uuid4()
        assignment_id = uuid4()
        binding_id = uuid4()

        async def insert_rows() -> None:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO campaign_payout_rule_revisions "
                        "(id,campaign_id,payout_rule_id,revision_number,effective_from,"
                        "hourly_rate_naira,premium_hourly_rate_naira,"
                        "daily_payable_hours_cap,eligibility_params,formula_version,"
                        "reason,created_by_user_id) VALUES "
                        "(:id,:campaign_id,:rule_id,1,now()-interval '1 day',1000,1500,8,"
                        "'{}'::jsonb,'payout_v3','test offer terms',:admin_id)"
                    ),
                    {
                        "id": revision_id,
                        "campaign_id": campaign.id,
                        "rule_id": rule.id,
                        "admin_id": admin.id,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO campaign_assignments "
                        "(id,campaign_id,driver_profile_id,vehicle_id,assigned_by_user_id,"
                        "status,offered_at,accepted_at,metadata) VALUES "
                        "(:id,:campaign_id,:profile_id,:vehicle_id,:admin_id,'accepted',"
                        "now(),now(),'{}'::jsonb)"
                    ),
                    {
                        "id": assignment_id,
                        "campaign_id": campaign.id,
                        "profile_id": profile.id,
                        "vehicle_id": vehicle.id,
                        "admin_id": admin.id,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO campaign_activation_events "
                        "(assignment_id,actor_user_id,event_type,new_status,occurred_at,metadata) "
                        "VALUES (:assignment_id,:admin_id,'accepted','active',now(),'{}'::jsonb)"
                    ),
                    {"assignment_id": assignment_id, "admin_id": admin.id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO assignment_rule_bindings "
                        "(id,assignment_id,revision_id,hourly_rate_naira,"
                        "premium_hourly_rate_naira,daily_payable_hours_cap,eligibility_params,"
                        "formula_version,premium_zone_ids,premium_zone_geometry_hash,"
                        "resolved_eligibility_params,premium_zone_geometry_wkts,"
                        "exclusion_zone_ids,exclusion_zone_geometry_hash,"
                        "exclusion_zone_geometry_wkts,stationary_policy_marker,"
                        "campaign_window_frozen,bound_at) VALUES "
                        "(:id,:assignment_id,:revision_id,1000,1500,8,'{}'::jsonb,'payout_v3',"
                        "'[]'::jsonb,repeat('a',64),'{}'::jsonb,'[]'::jsonb,'[]'::jsonb,"
                        "repeat('b',64),'[]'::jsonb,'ext-rm2-fail-closed',false,now())"
                    ),
                    {
                        "id": binding_id,
                        "assignment_id": assignment_id,
                        "revision_id": revision_id,
                    },
                )

        asyncio.run(insert_rows())
        asyncio.run(engine.dispose())
        return {
            "admin_id": admin.id,
            "campaign_id": campaign.id,
            "assignment_id": assignment_id,
            "binding_id": binding_id,
            "revision_id": revision_id,
        }

    try:
        upgrade_to(migration_url, PRE_OFFER_REVISION, monkeypatch)
        seeded = seed_legacy()
        upgrade_to(migration_url, OFFER_REVISION, monkeypatch)

        async def assert_new_columns() -> None:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            try:
                async with engine.connect() as connection:
                    columns = set(
                        (
                            await connection.execute(
                                text(
                                    "SELECT column_name FROM information_schema.columns "
                                    "WHERE table_name='campaign_assignments'"
                                )
                            )
                        ).scalars()
                    )
                    assert {"expires_at", "offer_terms", "offer_terms_sha256"} <= columns
                    legacy_status = await connection.scalar(
                        text(
                            "SELECT new_status FROM campaign_activation_events "
                            "WHERE assignment_id=:assignment_id AND event_type='accepted'"
                        ),
                        {"assignment_id": seeded["assignment_id"]},
                    )
                    assert legacy_status == "active"
            finally:
                await engine.dispose()

        asyncio.run(assert_new_columns())
        downgrade_to(migration_url, PRE_OFFER_REVISION, monkeypatch)
        upgrade_to(migration_url, OFFER_REVISION, monkeypatch)

        async def insert_new_evidence() -> UUID:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            new_assignment_id = uuid4()
            try:
                async with engine.begin() as connection:
                    campaign_id = await connection.scalar(
                        text(
                            "INSERT INTO campaigns "
                            "(organization_id,created_by_user_id,name,status,currency,metadata) "
                            "SELECT organization_id,created_by_user_id,'New evidence',"
                            "'draft','NGN','{}'::jsonb "
                            "FROM campaigns WHERE id=:campaign_id RETURNING id"
                        ),
                        {"campaign_id": seeded["campaign_id"]},
                    )
                    await connection.execute(
                        text(
                            "INSERT INTO campaign_assignments "
                            "(id,campaign_id,driver_profile_id,vehicle_id,assigned_by_user_id,"
                            "status,offered_at,expires_at,offer_terms,offer_terms_sha256,metadata) "
                            "SELECT :id,:campaign_id,driver_profile_id,vehicle_id,"
                            "assigned_by_user_id,'offered',now(),now()+interval '1 day',"
                            "'{\"currency\":\"NGN\"}'::jsonb,"
                            "repeat('c',64),'{}'::jsonb FROM campaign_assignments "
                            "WHERE id=:legacy_id"
                        ),
                        {
                            "id": new_assignment_id,
                            "campaign_id": campaign_id,
                            "legacy_id": seeded["assignment_id"],
                        },
                    )
            finally:
                await engine.dispose()
            return new_assignment_id

        async def mutate_binding() -> None:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE assignment_rule_bindings SET hourly_rate_naira=999 "
                            "WHERE id=:binding_id"
                        ),
                        {"binding_id": seeded["binding_id"]},
                    )
            finally:
                await engine.dispose()

        with pytest.raises(DBAPIError, match="immutable"):
            asyncio.run(mutate_binding())

        async def mutate_legacy_decision_timestamp() -> None:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE campaign_assignments SET accepted_at=now() + interval '1 hour' "
                            "WHERE id=:assignment_id"
                        ),
                        {"assignment_id": seeded["assignment_id"]},
                    )
            finally:
                await engine.dispose()

        with pytest.raises(DBAPIError, match="immutable"):
            asyncio.run(mutate_legacy_decision_timestamp())

        async def mutate_event() -> None:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                                "UPDATE campaign_activation_events SET "
                                "metadata=jsonb_build_object('tampered', true) "
                            "WHERE assignment_id=:assignment_id"
                        ),
                        {"assignment_id": seeded["assignment_id"]},
                    )
            finally:
                await engine.dispose()

        with pytest.raises(DBAPIError, match="append-only"):
            asyncio.run(mutate_event())
        new_assignment_id = asyncio.run(insert_new_evidence())

        async def mutate_offer() -> None:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE campaign_assignments SET offer_terms='{}'::jsonb "
                            "WHERE id=:assignment_id"
                        ),
                        {"assignment_id": new_assignment_id},
                    )
            finally:
                await engine.dispose()

        with pytest.raises(DBAPIError, match="immutable"):
            asyncio.run(mutate_offer())
        with pytest.raises(RuntimeError, match="0048 downgrade blocked"):
            downgrade_to(migration_url, PRE_OFFER_REVISION, monkeypatch)
        upgrade_to(migration_url, R18_PREVIOUS_REVISION, monkeypatch)
        with pytest.raises(DBAPIError, match="0081 upgrade blocked"):
            upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(fetch_all(migration_url, "SELECT version_num FROM alembic_version")) == [
            (R18_PREVIOUS_REVISION,)
        ]
    finally:
        asyncio.run(drop_database(migration_url))

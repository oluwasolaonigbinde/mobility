"""Fail-closed downgrade coverage for populated Package 1 financial structures."""

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import text
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

from app.models.payout import CampaignPayoutRule
from app.models.user import UserRole

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


async def execute_sql(
    migration_url: str,
    statement: str,
    params: dict | None = None,
) -> None:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(statement), params or {})
    finally:
        await engine.dispose()


def seed_assignment_and_rule_at_0017(migration_url: str, *, suffix: str) -> SimpleNamespace:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    admin = create_test_user(sessionmaker, email=f"guard-admin-{suffix}@example.com")
    advertiser = create_test_user(
        sessionmaker,
        email=f"guard-advertiser-{suffix}@example.com",
        role=UserRole.ADVERTISER,
    )
    driver = create_test_user(
        sessionmaker,
        email=f"guard-driver-{suffix}@example.com",
        role=UserRole.DRIVER,
    )
    organization, _ = create_test_organization(sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name=f"Downgrade guard {suffix}",
    )
    profile = create_test_driver_profile(sessionmaker, user_id=driver.id)
    vehicle = create_test_vehicle(
        sessionmaker,
        driver_profile_id=profile.id,
        plate_number=f"G-{suffix[:6].upper()}",
    )
    assignment = create_test_campaign_assignment(
        sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
    )

    async def add_rule() -> None:
        async with sessionmaker() as session:
            session.add(
                CampaignPayoutRule(
                    campaign_id=campaign.id,
                    created_by_user_id=admin.id,
                    formula_version="payout_v2",
                    status="active",
                    currency="NGN",
                    hourly_rate_naira=Decimal("1200.00"),
                    daily_payable_hours_cap=Decimal("8.00"),
                    eligibility_params={},
                    rule_metadata={},
                )
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(add_rule())
    return SimpleNamespace(
        admin_id=admin.id,
        campaign_id=campaign.id,
        assignment_id=assignment.id,
    )


def insert_binding(migration_url: str, seeded: SimpleNamespace) -> None:
    revision_id = asyncio.run(
        fetch_all(
            migration_url,
            "SELECT id FROM campaign_payout_rule_revisions WHERE campaign_id = :campaign_id",
            {"campaign_id": seeded.campaign_id},
        )
    )[0][0]
    asyncio.run(
        execute_sql(
            migration_url,
            """
            INSERT INTO assignment_rule_bindings
                (assignment_id, revision_id, hourly_rate_naira,
                 premium_hourly_rate_naira, daily_payable_hours_cap,
                 eligibility_params, formula_version, premium_zone_ids,
                 premium_zone_geometry_hash, stationary_policy_marker, bound_at)
            VALUES
                (:assignment_id, :revision_id, 1200.00, NULL, 8.00,
                 '{}'::jsonb, 'payout_v3', '[]'::jsonb,
                 :empty_hash, 'ext-rm2-fail-closed', now())
            """,
            {
                "assignment_id": seeded.assignment_id,
                "revision_id": revision_id,
                "empty_hash": EMPTY_SHA256,
            },
        )
    )


def test_0019_refuses_to_drop_populated_bindings(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, "0017_seal_review_hardening", monkeypatch)
        seeded = seed_assignment_and_rule_at_0017(migration_url, suffix="0019")
        upgrade_to(migration_url, "0019_assignment_rule_bindings", monkeypatch)
        insert_binding(migration_url, seeded)

        with pytest.raises(RuntimeError, match="Refusing to downgrade 0019"):
            downgrade_to(migration_url, "0018_payout_rule_revisions", monkeypatch)
        assert asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM assignment_rule_bindings")
        ) == [(1,)]

        asyncio.run(execute_sql(migration_url, "DELETE FROM assignment_rule_bindings"))
        downgrade_to(migration_url, "0018_payout_rule_revisions", monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'assignment_rule_bindings'",
            )
        ) == [(0,)]
    finally:
        asyncio.run(drop_database(migration_url))


def test_0020_refuses_to_drop_populated_correction_orders(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, "0017_seal_review_hardening", monkeypatch)
        seeded = seed_assignment_and_rule_at_0017(migration_url, suffix="0020")
        upgrade_to(migration_url, "0020_payout_correction_orders", monkeypatch)
        asyncio.run(
            execute_sql(
                migration_url,
                """
                INSERT INTO payout_correction_orders
                    (campaign_id, lagos_day, status, created_by_user_id, reason)
                VALUES (:campaign_id, :lagos_day, 'draft', :admin_id, :reason)
                """,
                {
                    "campaign_id": seeded.campaign_id,
                    "lagos_day": date(2026, 8, 21),
                    "admin_id": seeded.admin_id,
                    "reason": "downgrade guard regression",
                },
            )
        )

        with pytest.raises(RuntimeError, match="Refusing to downgrade 0020"):
            downgrade_to(migration_url, "0019_assignment_rule_bindings", monkeypatch)
        assert asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM payout_correction_orders")
        ) == [(1,)]

        asyncio.run(execute_sql(migration_url, "DELETE FROM payout_correction_orders"))
        downgrade_to(migration_url, "0019_assignment_rule_bindings", monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'payout_correction_orders'",
            )
        ) == [(0,)]
    finally:
        asyncio.run(drop_database(migration_url))


def test_0021_refuses_to_strip_populated_frozen_terms(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, "0017_seal_review_hardening", monkeypatch)
        seeded = seed_assignment_and_rule_at_0017(migration_url, suffix="0021")
        upgrade_to(migration_url, "0021_frozen_payout_v3_terms", monkeypatch)
        insert_binding(migration_url, seeded)

        with pytest.raises(RuntimeError, match="Refusing to downgrade 0021"):
            downgrade_to(migration_url, "0020_payout_correction_orders", monkeypatch)
        assert asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM assignment_rule_bindings")
        ) == [(1,)]

        asyncio.run(execute_sql(migration_url, "DELETE FROM assignment_rule_bindings"))
        downgrade_to(migration_url, "0020_payout_correction_orders", monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'assignment_rule_bindings' "
                "AND column_name = 'resolved_eligibility_params'",
            )
        ) == [(0,)]
    finally:
        asyncio.run(drop_database(migration_url))

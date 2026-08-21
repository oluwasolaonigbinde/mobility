"""Migration 0018: append-only payout-rule revisions (MNY-06A).

Style-B: throwaway Postgres database, real Alembic chain. Verifies the
backfill writes exactly one payout_v3 genesis revision per campaign from its
ACTIVE payout_v2 rule — values copied verbatim (money-neutral: v2 pricing
keeps reading the frozen rule row), effective_from = the rule's created_at,
the PR9 honesty reason recorded — while v1 rules and inactive v2 rules are
not backfilled. Populated downgrades fail closed; after explicit data removal
the empty-schema downgrade/re-upgrade cycle remains valid.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
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

REVISION_PRE_REVISIONS = "0017_seal_review_hardening"

BACKFILL_REASON = (
    "backfill: values as observed at migration 0018; pre-migration mutation"
    " history not reconstructed (names-only audit)"
)


async def execute_sql(migration_url: str, statement: str) -> None:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


def seed_rules_at_0017(migration_url: str) -> SimpleNamespace:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    admin = create_test_user(sessionmaker, email="m18-admin@example.com")
    advertiser = create_test_user(
        sessionmaker, email="m18-advertiser@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(sessionmaker, owner_user_id=advertiser.id)
    v2_campaign = create_test_campaign(
        sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name="M18 hourly campaign",
    )
    v1_campaign = create_test_campaign(
        sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name="M18 legacy campaign",
    )
    created_at = datetime.now(UTC) - timedelta(days=30)

    async def add_rules() -> SimpleNamespace:
        async with sessionmaker() as session:
            active_v2 = CampaignPayoutRule(
                campaign_id=v2_campaign.id,
                created_by_user_id=admin.id,
                formula_version="payout_v2",
                status="active",
                currency="NGN",
                hourly_rate_naira=Decimal("1200.00"),
                daily_payable_hours_cap=Decimal("8.00"),
                eligibility_params={"stationary_grace_min": 5},
                rule_metadata={},
                created_at=created_at,
            )
            superseded_v2 = CampaignPayoutRule(
                campaign_id=v2_campaign.id,
                created_by_user_id=admin.id,
                formula_version="payout_v2",
                status="inactive",
                currency="NGN",
                hourly_rate_naira=Decimal("1000.00"),
                daily_payable_hours_cap=Decimal("6.00"),
                eligibility_params=None,
                rule_metadata={},
                created_at=created_at - timedelta(days=10),
            )
            active_v1 = CampaignPayoutRule(
                campaign_id=v1_campaign.id,
                created_by_user_id=admin.id,
                formula_version="payout_v1",
                status="active",
                currency="NGN",
                base_rate_per_km=Decimal("10.00"),
                base_rate_per_active_hour=Decimal("0.00"),
                target_zone_bonus_rate_per_km=Decimal("0.00"),
                bonus_zone_bonus_rate_per_km=Decimal("0.00"),
                estimated_impression_rate_per_1000=Decimal("0.00"),
                min_payout_per_trip=Decimal("0.00"),
                low_fraud_multiplier=Decimal("0.90"),
                medium_fraud_multiplier=Decimal("0.70"),
                high_fraud_multiplier=Decimal("0.25"),
                rule_metadata={},
            )
            session.add_all([active_v2, superseded_v2, active_v1])
            await session.commit()
            return SimpleNamespace(
                active_v2_id=active_v2.id,
                superseded_v2_id=superseded_v2.id,
                active_v1_id=active_v1.id,
            )

    seeded = asyncio.run(add_rules())
    seeded.admin_id = admin.id
    seeded.v2_campaign_id = v2_campaign.id
    seeded.v1_campaign_id = v1_campaign.id
    seeded.created_at = created_at
    return seeded


def test_backfill_writes_one_genesis_revision_per_active_v2_rule(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, REVISION_PRE_REVISIONS, monkeypatch)
        seeded = seed_rules_at_0017(migration_url)
        upgrade_to(migration_url, "head", monkeypatch)

        rows = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT campaign_id, payout_rule_id, revision_number,"
                " effective_from, hourly_rate_naira, premium_hourly_rate_naira,"
                " daily_payable_hours_cap, eligibility_params::text,"
                " formula_version, reason, created_by_user_id"
                " FROM campaign_payout_rule_revisions",
            )
        )
        # Exactly one revision: the ACTIVE payout_v2 rule. The inactive v2
        # rule and the v1 rule are never backfilled.
        assert len(rows) == 1
        row = rows[0]
        assert row[0] == seeded.v2_campaign_id
        assert row[1] == seeded.active_v2_id
        assert row[2] == 1
        assert row[3] == seeded.created_at
        assert row[4] == Decimal("1200.00")
        assert row[5] is None
        assert row[6] == Decimal("8.00")
        assert row[7] == '{"stationary_grace_min": 5}'
        assert row[8] == "payout_v3"
        assert row[9] == BACKFILL_REASON
        assert row[10] == seeded.admin_id

        # Money-neutrality at the source: the frozen v2 rule row (the only
        # thing payout_v2 pricing reads) is untouched by the migration.
        rule_rows = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT hourly_rate_naira, daily_payable_hours_cap, status"
                " FROM campaign_payout_rules WHERE id = :id",
                {"id": seeded.active_v2_id},
            )
        )
        assert rule_rows == [(Decimal("1200.00"), Decimal("8.00"), "active")]

        # Populated authoritative history is never silently destroyed.
        with pytest.raises(RuntimeError, match="Refusing to downgrade 0018"):
            downgrade_to(migration_url, REVISION_PRE_REVISIONS, monkeypatch)
        assert asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM campaign_payout_rule_revisions")
        ) == [(1,)]

        # Empty-schema down/up behaviour remains available after an explicit,
        # operator-owned removal of the authoritative rows.
        asyncio.run(execute_sql(migration_url, "DELETE FROM campaign_payout_rule_revisions"))
        downgrade_to(migration_url, REVISION_PRE_REVISIONS, monkeypatch)
        tables = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.tables"
                " WHERE table_name = 'campaign_payout_rule_revisions'",
            )
        )
        assert tables == [(0,)]
        upgrade_to(migration_url, "head", monkeypatch)
        recount = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM campaign_payout_rule_revisions",
            )
        )
        assert recount == [(1,)]
    finally:
        asyncio.run(drop_database(migration_url))


def test_revision_table_constraints_exist(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        constraints = {
            row[0]
            for row in asyncio.run(
                fetch_all(
                    migration_url,
                    "SELECT conname FROM pg_constraint"
                    " WHERE conrelid = 'campaign_payout_rule_revisions'::regclass",
                )
            )
        }
        assert "uq_campaign_payout_rule_revisions_campaign_number" in constraints
        assert "uq_campaign_payout_rule_revisions_campaign_effective" in constraints
        assert "ck_campaign_payout_rule_revisions_number_ge_1" in constraints
        assert "ck_campaign_payout_rule_revisions_hourly_rate_non_negative" in constraints
        assert "ck_campaign_payout_rule_revisions_premium_rate_non_negative" in constraints
    finally:
        asyncio.run(drop_database(migration_url))

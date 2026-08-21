import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.config import get_settings

REVISION_0013 = "0013_payout_v2_hourly_caps"
REVISION_0012 = "0012_audit_event_indexes"
RELAXED_RULE_COLUMNS = {
    "base_rate_per_km",
    "base_rate_per_active_hour",
    "target_zone_bonus_rate_per_km",
    "bonus_zone_bonus_rate_per_km",
    "estimated_impression_rate_per_1000",
    "min_payout_per_trip",
    "low_fraud_multiplier",
    "medium_fraud_multiplier",
    "high_fraud_multiplier",
}
NEW_RULE_COLUMNS = {"hourly_rate_naira", "daily_payable_hours_cap", "eligibility_params"}
RELAXED_CALCULATION_COLUMNS = {
    "distance_component",
    "active_time_component",
    "target_zone_bonus_component",
    "bonus_zone_bonus_component",
    "impression_component",
    "cap_adjustment",
    "quality_multiplier",
    "fraud_multiplier",
}
NEW_CALCULATION_COLUMNS = {
    "eligible_seconds",
    "payable_seconds",
    "excluded_seconds_by_reason",
    "inputs_fingerprint",
}


def configured_postgres_url() -> str:
    database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if database_url is None or not database_url.startswith("postgresql+asyncpg://"):
        pytest.skip("PostGIS test database is not configured")
    return database_url


async def create_database_from_url(database_url: str) -> str:
    source_url = make_url(database_url)
    database_name = f"test_0013_migration_{uuid4().hex}"
    maintenance_url = source_url.set(database="postgres")
    engine = create_async_engine(
        maintenance_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        await engine.dispose()
    return source_url.set(database=database_name).render_as_string(hide_password=False)


async def drop_database(database_url: str) -> None:
    url = make_url(database_url)
    database_name = url.database
    if database_name is None:
        return
    maintenance_url = url.set(database="postgres")
    engine = create_async_engine(
        maintenance_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name
                      AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": database_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
    finally:
        await engine.dispose()


def test_0013_migration_extends_payout_tables_without_new_tables() -> None:
    migration = Path("alembic/versions/0013_payout_v2_hourly_caps.py").read_text()

    assert f'revision: str = "{REVISION_0013}"' in migration
    assert f'down_revision: str | Sequence[str] | None = "{REVISION_0012}"' in migration
    assert migration.count("op.create_table(") == 0
    for required in [
        "ck_campaign_payout_rules_model_xor",
        "ck_campaign_payout_rules_hourly_rate_non_negative",
        "ck_campaign_payout_rules_daily_cap_range",
        "ck_payout_calculations_v2_time_fields",
        "ck_payout_calculations_payable_lte_eligible",
        "uq_earnings_ledger_entries_trip_payout_per_trip",
        "entry_type = 'trip_payout'",
        "formula_version <> 'payout_v2'",
        "hourly_rate_naira",
        "daily_payable_hours_cap",
        "eligibility_params",
        "eligible_seconds",
        "payable_seconds",
        "excluded_seconds_by_reason",
        "inputs_fingerprint",
        "Money values are never invented on downgrade",
        "Cannot apply 0013",
        "HAVING count(*) > 1",
    ]:
        assert required in migration
    for forbidden_table in [
        "payout_batches",
        "notifications",
        "fraud_disputes",
        "invoices",
        "payments",
    ]:
        assert f'"{forbidden_table}"' not in migration


def test_0013_migration_upgrades_preserves_v1_rows_and_enforces_model_xor(
    monkeypatch,
) -> None:
    source_url = configured_postgres_url()
    try:
        migration_url = asyncio.run(create_database_from_url(source_url))
    except Exception as exc:  # pragma: no cover - exercised only without local DB privilege
        pytest.fail(f"Could not create temporary Postgres migration database: {exc}")

    async def seed_v1_graph() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        INSERT INTO users (id, email, password_hash, role, status, full_name)
                        VALUES (:id, 'mig-admin@example.com', 'x', 'admin', 'active', 'Mig Admin')
                        """
                    ),
                    {"id": str(uuid4())},
                )
                admin_id = (
                    await connection.execute(text("SELECT id FROM users LIMIT 1"))
                ).scalar_one()
                org_id = (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO advertiser_organizations (name, status)
                            VALUES ('Mig Org', 'active')
                            RETURNING id
                            """
                        )
                    )
                ).scalar_one()
                campaign_id = (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO campaigns
                                (organization_id, created_by_user_id, name, status, currency)
                            VALUES (:org_id, :admin_id, 'Mig Campaign', 'active', 'NGN')
                            RETURNING id
                            """
                        ),
                        {"org_id": org_id, "admin_id": admin_id},
                    )
                ).scalar_one()
                # Legacy-shaped v1 rule inserted while still at 0012.
                await connection.execute(
                    text(
                        """
                        INSERT INTO campaign_payout_rules
                            (campaign_id, created_by_user_id, formula_version, status,
                             currency, base_rate_per_km, base_rate_per_active_hour,
                             target_zone_bonus_rate_per_km, bonus_zone_bonus_rate_per_km,
                             estimated_impression_rate_per_1000, min_payout_per_trip,
                             max_payout_per_trip)
                        VALUES (:campaign_id, :admin_id, 'payout_v1', 'active', 'NGN',
                                100.00, 500.00, 50.00, 75.00, 25.00, 1200.00, 10000.00)
                        """
                    ),
                    {"campaign_id": campaign_id, "admin_id": admin_id},
                )
        finally:
            await engine.dispose()

    async def assert_upgraded_schema() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                columns = {
                    (row.table_name, row.column_name): row.is_nullable
                    for row in (
                        await connection.execute(
                            text(
                                """
                                SELECT table_name, column_name, is_nullable
                                FROM information_schema.columns
                                WHERE table_name IN
                                    ('campaign_payout_rules', 'payout_calculations')
                                """
                            )
                        )
                    ).all()
                }
                for column in RELAXED_RULE_COLUMNS | NEW_RULE_COLUMNS:
                    assert columns[("campaign_payout_rules", column)] == "YES", column
                for column in RELAXED_CALCULATION_COLUMNS | NEW_CALCULATION_COLUMNS:
                    assert columns[("payout_calculations", column)] == "YES", column
                # FKs stay NOT NULL (architecture 16.1).
                assert columns[("payout_calculations", "trip_analytics_id")] == "NO"
                assert columns[("payout_calculations", "impression_estimate_id")] == "NO"

                defaults = {
                    row.column_name: row.column_default
                    for row in (
                        await connection.execute(
                            text(
                                """
                                SELECT column_name, column_default
                                FROM information_schema.columns
                                WHERE table_name = 'campaign_payout_rules'
                                """
                            )
                        )
                    ).all()
                }
                for column in RELAXED_RULE_COLUMNS:
                    assert defaults[column] is None, column

                index_definition = (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef FROM pg_indexes
                            WHERE indexname =
                                'uq_earnings_ledger_entries_trip_payout_per_trip'
                            """
                        )
                    )
                ).scalar_one()
                assert "UNIQUE" in index_definition
                assert "trip_payout" in index_definition

                v1_row = (
                    await connection.execute(
                        text(
                            """
                            SELECT base_rate_per_km, min_payout_per_trip, hourly_rate_naira
                            FROM campaign_payout_rules
                            WHERE formula_version = 'payout_v1'
                            """
                        )
                    )
                ).one()
                assert str(v1_row.base_rate_per_km) == "100.00"
                assert str(v1_row.min_payout_per_trip) == "1200.00"
                assert v1_row.hourly_rate_naira is None

            async with engine.begin() as connection:
                admin_id = (
                    await connection.execute(text("SELECT id FROM users LIMIT 1"))
                ).scalar_one()
                campaign_id = (
                    await connection.execute(text("SELECT id FROM campaigns LIMIT 1"))
                ).scalar_one()
                # A valid v2 row inserts.
                await connection.execute(
                    text(
                        """
                        INSERT INTO campaign_payout_rules
                            (campaign_id, created_by_user_id, formula_version, status,
                             currency, hourly_rate_naira, daily_payable_hours_cap)
                        VALUES (:campaign_id, :admin_id, 'payout_v2', 'inactive', 'NGN',
                                1100.00, 8.00)
                        """
                    ),
                    {"campaign_id": campaign_id, "admin_id": admin_id},
                )
            async with engine.connect() as connection:
                # A mixed-model row violates the XOR check.
                with pytest.raises(Exception, match="ck_campaign_payout_rules_model_xor"):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO campaign_payout_rules
                                (campaign_id, created_by_user_id, formula_version, status,
                                 currency, hourly_rate_naira, daily_payable_hours_cap,
                                 base_rate_per_km)
                            VALUES (:campaign_id, :admin_id, 'payout_v2', 'inactive', 'NGN',
                                    1100.00, 8.00, 10.00)
                            """
                        ),
                        {"campaign_id": campaign_id, "admin_id": admin_id},
                    )
        finally:
            await engine.dispose()

    async def delete_v2_rows() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "DELETE FROM campaign_payout_rules "
                        "WHERE formula_version = 'payout_v2'"
                    )
                )
        finally:
            await engine.dispose()

    try:
        monkeypatch.setenv("DATABASE_URL", migration_url)
        get_settings.cache_clear()
        alembic_config = Config("alembic.ini")
        command.upgrade(alembic_config, REVISION_0012)
        asyncio.run(seed_v1_graph())
        command.upgrade(alembic_config, REVISION_0013)
        asyncio.run(assert_upgraded_schema())
        # Downgrade refuses while payout_v2 rows exist; succeeds once removed.
        with pytest.raises(Exception, match="Cannot downgrade 0013"):
            command.downgrade(alembic_config, REVISION_0012)
        asyncio.run(delete_v2_rows())
        command.downgrade(alembic_config, REVISION_0012)
        command.upgrade(alembic_config, REVISION_0013)
    finally:
        get_settings.cache_clear()
        asyncio.run(drop_database(migration_url))

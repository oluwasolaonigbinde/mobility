"""Migration 0079: immutable traffic-density profile provenance."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)

PRE_PROFILE_REVISION = "0078_campaign_assignment_driver_active"
PROFILE_REVISION = "0079_traffic_density_profile_revisions"
PROFILE_ID = "79000000-0000-0000-0000-000000000001"


async def _execute(migration_url: str, statement: str) -> list:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(text(statement))
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def _seed_legacy_profile(migration_url: str) -> None:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL session_replication_role = replica"))
            await connection.execute(
                text(
                    f"""
                    INSERT INTO traffic_density_profiles
                      (id, name, description, profile_type, traffic_density_per_km,
                       dwell_impressions_per_minute, road_category_weight, morning_weight,
                       midday_weight, evening_weight, night_weight, target_zone_weight,
                       bonus_zone_weight, exclusion_zone_weight, is_default, status, metadata)
                    VALUES
                      ('{PROFILE_ID}', 'Legacy profile', 'pre-0079', 'default', 120, 3, 1,
                       1.1, 1, 1.2, 0.7, 1, 1.25, 0, true, 'active',
                       jsonb_build_object('source', 'legacy'))
                    """
                )
            )
            await connection.execute(
                text(
                    f"""
                    INSERT INTO impression_estimates
                      (id, trip_session_id, trip_analytics_id, assignment_id, campaign_id,
                       driver_profile_id, vehicle_id, traffic_density_profile_id,
                       formula_version, status, is_authoritative, estimated_impressions,
                       base_distance_impressions, dwell_impressions,
                       target_zone_impressions, bonus_zone_impressions,
                       exclusion_zone_adjustment, quality_multiplier,
                       fraud_adjustment_multiplier, confidence_score, estimated_at, metadata)
                    VALUES
                      ('79000000-0000-0000-0000-000000000002',
                       '79000000-0000-0000-0000-000000000011',
                       '79000000-0000-0000-0000-000000000012',
                       '79000000-0000-0000-0000-000000000013',
                       '79000000-0000-0000-0000-000000000014',
                       '79000000-0000-0000-0000-000000000015',
                       '79000000-0000-0000-0000-000000000016',
                       '{PROFILE_ID}', 'impressions_v1', 'estimated', true, 100, 100,
                       0, 0, 0, 0, 1, 1, 1, now(), jsonb_build_object('legacy', true))
                    """
                )
            )
    finally:
        await engine.dispose()


def test_profile_revision_migration_backfill_catalog_and_guards(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_PROFILE_REVISION, monkeypatch)
        asyncio.run(_seed_legacy_profile(migration_url))
        upgrade_to(migration_url, PROFILE_REVISION, monkeypatch)

        assert asyncio.run(
            _execute(
                migration_url,
                f"""
                SELECT lineage_id::text, revision, supersedes_id,
                       effective_from = created_at, length(value_fingerprint)
                FROM traffic_density_profiles
                WHERE id = '{PROFILE_ID}'
                """,
            )
        ) == [(PROFILE_ID, 1, None, True, 64)]
        estimate_fingerprint = asyncio.run(
            _execute(
                migration_url,
                """
                SELECT metadata->>'traffic_density_profile_fingerprint'
                FROM impression_estimates
                WHERE id = '79000000-0000-0000-0000-000000000002'
                """,
            )
        )
        assert len(estimate_fingerprint[0][0]) == 64
        assert asyncio.run(
            _execute(
                migration_url,
                """
                SELECT tgname
                FROM pg_trigger
                WHERE tgrelid = 'traffic_density_profiles'::regclass
                  AND NOT tgisinternal
                ORDER BY tgname
                """,
            )
        ) == [
            ("trg_traffic_density_profile_revision_immutable",),
            ("trg_traffic_density_profile_revision_validate",),
        ]
        assert asyncio.run(
            _execute(
                migration_url,
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'traffic_density_profiles'
                  AND indexname IN (
                    'ix_traffic_density_profiles_lineage_effective',
                    'uq_traffic_density_profiles_lineage_revision',
                    'uq_traffic_density_profiles_supersedes_id'
                  )
                ORDER BY indexname
                """,
            )
        ) == [
            ("ix_traffic_density_profiles_lineage_effective",),
            ("uq_traffic_density_profiles_lineage_revision",),
            ("uq_traffic_density_profiles_supersedes_id",),
        ]

        with pytest.raises(DBAPIError, match="revision values are immutable"):
            asyncio.run(
                _execute(
                    migration_url,
                    f"""
                    UPDATE traffic_density_profiles
                    SET traffic_density_per_km = 240
                    WHERE id = '{PROFILE_ID}'
                    """,
                )
            )

        with pytest.raises(DBAPIError, match="revisions cannot be deleted"):
            asyncio.run(
                _execute(
                    migration_url,
                    f"DELETE FROM traffic_density_profiles WHERE id = '{PROFILE_ID}'",
                )
            )

        with pytest.raises(DBAPIError, match="monotonic in its lineage"):
            asyncio.run(
                _execute(
                    migration_url,
                    f"""
                    INSERT INTO traffic_density_profiles
                      (id, lineage_id, revision, effective_from, supersedes_id,
                       value_fingerprint, name, description, profile_type,
                       traffic_density_per_km, dwell_impressions_per_minute,
                       road_category_weight, morning_weight, midday_weight,
                       evening_weight, night_weight, target_zone_weight,
                       bonus_zone_weight, exclusion_zone_weight, is_default,
                       status, metadata)
                    SELECT gen_random_uuid(), lineage_id, 2, effective_from,
                           id, repeat('a', 64), name, description, profile_type,
                           240, dwell_impressions_per_minute,
                           road_category_weight, morning_weight, midday_weight,
                           evening_weight, night_weight, target_zone_weight,
                           bonus_zone_weight, exclusion_zone_weight, false,
                           status, metadata
                    FROM traffic_density_profiles
                    WHERE id = '{PROFILE_ID}'
                    """,
                )
            )

        downgrade_to(migration_url, PRE_PROFILE_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_profile_revision_migration_refuses_populated_successor_downgrade(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_PROFILE_REVISION, monkeypatch)
        asyncio.run(_seed_legacy_profile(migration_url))
        upgrade_to(migration_url, PROFILE_REVISION, monkeypatch)
        asyncio.run(
            _execute(
                migration_url,
                f"""
                INSERT INTO traffic_density_profiles
                  (id, lineage_id, revision, effective_from, supersedes_id,
                   value_fingerprint, name, description, profile_type,
                   traffic_density_per_km, dwell_impressions_per_minute,
                   road_category_weight, morning_weight, midday_weight,
                   evening_weight, night_weight, target_zone_weight,
                   bonus_zone_weight, exclusion_zone_weight, is_default,
                   status, metadata)
                SELECT gen_random_uuid(), lineage_id, 2,
                       effective_from + interval '1 second', id, repeat('b', 64),
                       name, description, profile_type, 240,
                       dwell_impressions_per_minute, road_category_weight,
                       morning_weight, midday_weight, evening_weight,
                       night_weight, target_zone_weight, bonus_zone_weight,
                       exclusion_zone_weight, false, status, metadata
                FROM traffic_density_profiles
                WHERE id = '{PROFILE_ID}'
                """,
            )
        )

        with pytest.raises(RuntimeError, match="Refusing to drop versioned"):
            downgrade_to(migration_url, PRE_PROFILE_REVISION, monkeypatch)
        assert asyncio.run(_execute(migration_url, "SELECT version_num FROM alembic_version")) == [
            (PROFILE_REVISION,)
        ]
    finally:
        asyncio.run(drop_database(migration_url))

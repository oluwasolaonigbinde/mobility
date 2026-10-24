"""Disposable PostgreSQL and current-schema test helpers."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic.config import Config
from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import CheckConstraint, UniqueConstraint, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.config import get_settings
from app.db.base import Base, PostGISGeometry
from app.models.user import UserRole
from app.services.data_lifecycle import add_months, month_start

BASELINE_REVISION = "0106_development_baseline"


EXPECTED_CHECKS = {
    "ck_location_pings_sequence_number_non_negative",
    "ck_location_pings_latitude",
    "ck_location_pings_longitude",
    "ck_location_pings_accuracy_non_negative",
    "ck_location_pings_speed_non_negative",
    "ck_location_pings_heading_degrees",
    "ck_location_pings_altitude_m",
}


EXPECTED_INDEXES = {
    "ix_location_pings_trip_session_id",
    "ix_location_pings_trip_recorded_at",
    "ix_location_pings_batch_id",
    "ix_location_pings_geom",
}


def configured_postgres_url() -> str:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None or not database_url.startswith("postgresql+asyncpg://"):
        pytest.skip("PostGIS test database is not configured")
    return database_url


async def create_database_from_url(database_url: str) -> str:
    source_url = make_url(database_url)
    database_name = f"test_schema_{uuid4().hex}"
    maintenance_url = source_url.set(database="postgres")
    engine = create_async_engine(maintenance_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
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
    engine = create_async_engine(maintenance_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": database_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
    finally:
        await engine.dispose()


def upgrade_to(migration_url: str, revision: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migration_url)
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), revision)
    get_settings.cache_clear()


async def fetch_all(migration_url: str, query: str, params: dict | None = None) -> list:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text(query), params or {})
            return list(result.all())
    finally:
        await engine.dispose()


async def execute_sql(migration_url: str, statement: str | tuple[str, ...]) -> None:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            statements = (statement,) if isinstance(statement, str) else statement
            for item in statements:
                await connection.execute(text(item))
    finally:
        await engine.dispose()


def flatten_alembic_diffs(diffs: list) -> list[tuple]:
    flattened: list[tuple] = []
    for diff in diffs:
        if isinstance(diff, list):
            flattened.extend(flatten_alembic_diffs(diff))
        else:
            flattened.append(diff)
    return flattened


async def fetch_catalog_authority(migration_url: str) -> dict[str, dict]:
    table_names = sorted(Base.metadata.tables)
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            key_constraint_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT table_class.relname AS table_name,
                           constraint_row.conname AS constraint_name,
                           constraint_row.contype::text AS constraint_type,
                           ARRAY(
                               SELECT attribute.attname
                               FROM unnest(constraint_row.conkey) WITH ORDINALITY
                                   AS key_column(attribute_number, ordinality)
                               JOIN pg_attribute attribute
                                 ON attribute.attrelid = table_class.oid
                                AND attribute.attnum = key_column.attribute_number
                               ORDER BY key_column.ordinality
                           ) AS key_column_names,
                           constraint_row.condeferrable AS deferrable,
                           constraint_row.condeferred AS initially_deferred,
                           ARRAY(
                               SELECT attribute.attname
                               FROM unnest(index_row.indkey) WITH ORDINALITY
                                   AS index_column(attribute_number, ordinality)
                               JOIN pg_attribute attribute
                                 ON attribute.attrelid = table_class.oid
                                AND attribute.attnum = index_column.attribute_number
                               WHERE index_column.ordinality > index_row.indnkeyatts
                               ORDER BY index_column.ordinality
                           ) AS included_column_names
                    FROM pg_constraint constraint_row
                    JOIN pg_class table_class ON table_class.oid = constraint_row.conrelid
                    JOIN pg_namespace namespace_row
                      ON namespace_row.oid = table_class.relnamespace
                    JOIN pg_index index_row
                      ON index_row.indexrelid = constraint_row.conindid
                    WHERE namespace_row.nspname = 'public'
                      AND constraint_row.contype IN ('p', 'u')
                      AND table_class.relname = ANY(CAST(:table_names AS text[]))
                        """
                    ),
                    {"table_names": table_names},
                )
            ).all()

            def catalog_signature(row) -> dict:
                return {
                    "key_columns": tuple(row.key_column_names),
                    "deferrable": row.deferrable,
                    "initially": ("DEFERRED" if row.initially_deferred else "IMMEDIATE"),
                    "included_columns": tuple(row.included_column_names),
                }

            actual_primary_keys = {
                row.table_name: catalog_signature(row)
                for row in key_constraint_rows
                if row.constraint_type == "p"
            }
            actual_unique_constraints = {
                (row.table_name, row.constraint_name): catalog_signature(row)
                for row in key_constraint_rows
                if row.constraint_type == "u"
            }

            check_rows = await connection.execute(
                text(
                    """
                    SELECT table_class.relname AS table_name,
                           constraint_row.conname AS constraint_name,
                           pg_get_constraintdef(constraint_row.oid, false) AS definition
                    FROM pg_constraint constraint_row
                    JOIN pg_class table_class ON table_class.oid = constraint_row.conrelid
                    JOIN pg_namespace namespace_row
                      ON namespace_row.oid = table_class.relnamespace
                    WHERE namespace_row.nspname = 'public'
                      AND constraint_row.contype = 'c'
                      AND table_class.relname = ANY(CAST(:table_names AS text[]))
                    """
                ),
                {"table_names": table_names},
            )
            actual_checks = {
                (row.table_name, row.constraint_name): row.definition for row in check_rows
            }

            expected_checks: dict[tuple[str, str], str] = {}
            preparer = connection.dialect.identifier_preparer
            for index, metadata_table in enumerate(
                sorted(Base.metadata.tables.values(), key=lambda table: table.name)
            ):
                check_constraints = sorted(
                    (
                        constraint
                        for constraint in metadata_table.constraints
                        if isinstance(constraint, CheckConstraint)
                    ),
                    key=lambda constraint: constraint.name or "",
                )
                if not check_constraints:
                    continue
                assert all(constraint.name for constraint in check_constraints)
                temporary_table = f"r04_expected_checks_{index}"
                quoted_temporary_table = preparer.quote(temporary_table)
                quoted_public_table = (
                    f"{preparer.quote_schema('public')}.{preparer.quote(metadata_table.name)}"
                )
                await connection.execute(
                    text(
                        f"CREATE TEMP TABLE {quoted_temporary_table} "
                        f"(LIKE {quoted_public_table} INCLUDING ALL) ON COMMIT DROP"
                    )
                )
                copied_checks = await connection.execute(
                    text(
                        """
                        SELECT conname
                        FROM pg_constraint
                        WHERE contype = 'c' AND conrelid = to_regclass(:table_name)
                        """
                    ),
                    {"table_name": f"pg_temp.{temporary_table}"},
                )
                for (constraint_name,) in copied_checks:
                    await connection.execute(
                        text(
                            f"ALTER TABLE {quoted_temporary_table} DROP CONSTRAINT "
                            f"{preparer.quote(constraint_name)}"
                        )
                    )
                for constraint in check_constraints:
                    expression = str(
                        constraint.sqltext.compile(
                            dialect=postgresql.dialect(),
                            compile_kwargs={"literal_binds": True},
                        )
                    )
                    await connection.execute(
                        text(
                            f"ALTER TABLE {quoted_temporary_table} ADD CONSTRAINT "
                            f"{preparer.quote(constraint.name)} CHECK ({expression})"
                        )
                    )
                expected_rows = await connection.execute(
                    text(
                        """
                        SELECT conname, pg_get_constraintdef(oid, false)
                        FROM pg_constraint
                        WHERE contype = 'c' AND conrelid = to_regclass(:table_name)
                        """
                    ),
                    {"table_name": f"pg_temp.{temporary_table}"},
                )
                expected_checks.update(
                    {
                        (metadata_table.name, constraint_name): definition
                        for constraint_name, definition in expected_rows
                    }
                )

            geometry_rows = await connection.execute(
                text(
                    """
                    SELECT table_class.relname AS table_name,
                           attribute.attname AS column_name,
                           postgis_typmod_type(attribute.atttypmod) AS subtype,
                           postgis_typmod_srid(attribute.atttypmod) AS srid
                    FROM pg_attribute attribute
                    JOIN pg_class table_class ON table_class.oid = attribute.attrelid
                    JOIN pg_namespace namespace_row
                      ON namespace_row.oid = table_class.relnamespace
                    JOIN pg_type type_row ON type_row.oid = attribute.atttypid
                    WHERE namespace_row.nspname = 'public'
                      AND type_row.typname = 'geometry'
                      AND attribute.attnum > 0
                      AND NOT attribute.attisdropped
                      AND table_class.relname = ANY(CAST(:table_names AS text[]))
                    """
                ),
                {"table_names": table_names},
            )
            actual_geometry = {
                (row.table_name, row.column_name): (row.subtype, row.srid) for row in geometry_rows
            }
    finally:
        await engine.dispose()

    def metadata_signature(constraint) -> dict:
        included_columns = constraint.dialect_options["postgresql"].get("include") or ()
        return {
            "key_columns": tuple(column.name for column in constraint.columns),
            "deferrable": (constraint.deferrable if constraint.deferrable is not None else False),
            "initially": constraint.initially or "IMMEDIATE",
            "included_columns": tuple(
                column if isinstance(column, str) else column.name for column in included_columns
            ),
        }

    expected_primary_keys = {
        table.name: metadata_signature(table.primary_key)
        for table in Base.metadata.tables.values()
        if table.primary_key.columns
    }
    expected_unique_constraints = {
        (table.name, constraint.name): metadata_signature(constraint)
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint) and constraint.name is not None
    }
    actual_unique_constraints = {
        identity: signature
        for identity, signature in actual_unique_constraints.items()
        if identity in expected_unique_constraints
    }
    expected_geometry = {
        (table.name, column.name): (column.type.geometry_type, column.type.srid)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, PostGISGeometry)
    }
    return {
        "actual_primary_keys": actual_primary_keys,
        "expected_primary_keys": expected_primary_keys,
        "actual_unique_constraints": actual_unique_constraints,
        "expected_unique_constraints": expected_unique_constraints,
        "actual_checks": actual_checks,
        "expected_checks": expected_checks,
        "actual_geometry": actual_geometry,
        "expected_geometry": expected_geometry,
    }


def partition_rows(migration_url: str) -> list[tuple[str, str]]:
    return asyncio.run(
        fetch_all(
            migration_url,
            """
            SELECT child.relname, pg_get_expr(child.relpartbound, child.oid)
            FROM pg_inherits inh
            JOIN pg_class child ON child.oid = inh.inhrelid
            JOIN pg_class parent ON parent.oid = inh.inhparent
            WHERE parent.relname = 'location_pings'
            ORDER BY child.relname
            """,
        )
    )


def seed_ping_graph(migration_url: str, *, future_straddling_at: datetime | None = None) -> dict:
    """Build the minimal FK graph on the current baseline and insert pings across
    three UTC months, including a batch straddling two months."""
    engine = create_async_engine(migration_url, poolclass=NullPool)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    months = [add_months(month_start(now), -2), add_months(month_start(now), -1), month_start(now)]

    admin = create_test_user(sessionmaker, email="mig-admin@example.com")
    advertiser = create_test_user(
        sessionmaker, email="mig-advertiser@example.com", role=UserRole.ADVERTISER
    )
    driver = create_test_user(sessionmaker, email="mig-driver@example.com", role=UserRole.DRIVER)
    organization, _ = create_test_organization(
        sessionmaker, owner_user_id=advertiser.id, legacy_schema=True
    )
    campaign = create_test_campaign(
        sessionmaker, organization_id=organization.id, created_by_user_id=advertiser.id
    )
    profile = create_test_driver_profile(sessionmaker, user_id=driver.id)
    vehicle = create_test_vehicle(sessionmaker, driver_profile_id=profile.id)
    assignment = create_test_campaign_assignment(
        sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
    )
    # Raw SQL: this seed runs on the current baseline, before the 0016 seal columns
    # exist — the current ORM model would INSERT columns the old schema lacks.
    trip_id = uuid4()

    async def add_trip() -> None:
        async with sessionmaker() as session:
            await session.execute(
                text(
                    "INSERT INTO trip_sessions (id, assignment_id, campaign_id,"
                    " driver_profile_id, vehicle_id, started_by_user_id, status,"
                    " started_at, metadata)"
                    " VALUES (:id, :assignment_id, :campaign_id, :driver_profile_id,"
                    " :vehicle_id, :started_by_user_id, 'active', :started_at, '{}')"
                ),
                {
                    "id": trip_id,
                    "assignment_id": assignment.id,
                    "campaign_id": campaign.id,
                    "driver_profile_id": profile.id,
                    "vehicle_id": vehicle.id,
                    "started_by_user_id": driver.id,
                    "started_at": months[0] + timedelta(hours=8),
                },
            )
            await session.commit()

    asyncio.run(add_trip())

    async def add_batch(key: str, recorded_ats: list[datetime]) -> tuple[str, list[str]]:
        batch_id = uuid4()
        batch_sequence = {"batch-oldest": 0, "batch-middle": 1, "batch-straddling": 2}[key]
        ping_ids = [uuid4() for _ in recorded_ats]
        async with sessionmaker() as session:
            await session.execute(
                text(
                    "INSERT INTO location_ping_batches"
                    " (id, trip_session_id, idempotency_key, payload_hash,"
                    "  pings_accepted, pings_submitted, batch_sequence, receipt_format_version, "
                    "receipt_key_version, receipt_signature, receipt_outcome, "
                    "received_at, metadata)"
                    " VALUES (:id, :trip_session_id, :idempotency_key, :payload_hash,"
                    "         :pings_accepted, :pings_accepted, :batch_sequence, NULL, NULL, "
                    "NULL, NULL, :received_at, '{}'::jsonb)"
                ),
                {
                    "id": batch_id,
                    "trip_session_id": trip_id,
                    "idempotency_key": key,
                    "payload_hash": chr(ord("a") + batch_sequence) * 64,
                    "batch_sequence": batch_sequence,
                    "signature": f"batch-signature-{batch_sequence}",
                    "pings_accepted": len(recorded_ats),
                    "received_at": recorded_ats[0],
                },
            )
            for ping_id, (sequence, recorded_at) in zip(
                ping_ids, enumerate(recorded_ats), strict=True
            ):
                await session.execute(
                    text(
                        "INSERT INTO location_pings"
                        " (id, trip_session_id, batch_id, recorded_at, received_at,"
                        "  sequence_number, latitude, longitude, accuracy_m, geom, metadata)"
                        " VALUES (:id, :trip_session_id, :batch_id, :recorded_at, :received_at,"
                        "         :sequence_number, 6.45, 3.39, 10,"
                        "         ST_SetSRID(ST_MakePoint(3.39, 6.45), 4326), '{}'::jsonb)"
                    ),
                    {
                        "id": ping_id,
                        "trip_session_id": trip_id,
                        "batch_id": batch_id,
                        "recorded_at": recorded_at,
                        "received_at": recorded_at,
                        "sequence_number": sequence,
                    },
                )
            await session.execute(
                text(
                    "UPDATE location_ping_batches SET receipt_format_version=2, "
                    "receipt_key_version=1, "
                    "receipt_outcome='accepted', receipt_signature=:signature WHERE id=:id"
                ),
                {"signature": f"batch-signature-{batch_sequence}", "id": batch_id},
            )
            await session.commit()
            return str(batch_id), [str(ping_id) for ping_id in ping_ids]

    batches = {}
    batches["oldest"] = asyncio.run(
        add_batch("batch-oldest", [months[0] + timedelta(hours=9, minutes=m) for m in range(3)])
    )
    batches["middle"] = asyncio.run(
        add_batch("batch-middle", [months[1] + timedelta(hours=9, minutes=m) for m in range(3)])
    )
    # Straddles the previous and current month.
    batches["straddling"] = asyncio.run(
        add_batch(
            "batch-straddling",
            [months[2] - timedelta(minutes=1), months[2] + timedelta(minutes=1)]
            + ([future_straddling_at] if future_straddling_at else []),
        )
    )
    asyncio.run(engine.dispose())
    return {"trip_id": str(trip_id), "batches": batches, "months": months}

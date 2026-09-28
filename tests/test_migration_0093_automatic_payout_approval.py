"""Migration 0093: automatic payout approval tables, batch mode and system actor."""

import asyncio
import hashlib

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    fetch_all,
    upgrade_to,
)

from app.core.security import verify_password
from app.db.base import Base
from app.models.disbursement import (
    CARDVERT_AUTOMATIC_PAYOUT_ACTOR_EMAIL,
    CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID,
)

PREVIOUS = "0092_payout_v4_daily_rate"
CURRENT = "0093_automatic_payout_approval"
TABLES = (
    "payout_batches",
    "payout_automatic_runs",
    "payout_automatic_controls",
    "payout_automatic_alerts",
)
ADMIN = "93000000-0000-0000-0000-00000000000a"
MANUAL_BATCH = (
    "INSERT INTO payout_batches (id, status, currency, total_amount, created_by_user_id)"
    " VALUES ('93000000-0000-0000-0000-000000000001', 'draft', 'NGN', 0, '" + ADMIN + "')"
)
RUN = (
    "INSERT INTO payout_automatic_runs (id, period_key, frequency, currency, batch_limit,"
    " total_amount, batch_count, line_count, exclusions, settings_fingerprint) VALUES"
    " ('93000000-0000-0000-0000-000000000002', '2026-09-28', 'daily', 'NGN', 1000, {total},"
    " 1, 1, '{{}}', '" + "a" * 64 + "')"
)
AUTOMATIC_BATCH = (
    "INSERT INTO payout_batches (id, status, currency, total_amount, created_by_user_id,"
    " approval_mode, automatic_run_id, approved_at, approved_by_user_id,"
    " instruction_set_fingerprint) VALUES ('93000000-0000-0000-0000-000000000003', 'reserved',"
    " 'NGN', 100, '{actor}', 'automatic', {run}, {approved_at}, {approver}, '" + "b" * 64 + "')"
)


async def execute(url: str, statement: str, *, replica: bool = True) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            if replica:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


def automatic_batch(**overrides) -> str:
    values = {
        "actor": str(CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID),
        "run": "'93000000-0000-0000-0000-000000000002'",
        "approved_at": "now()",
        "approver": "NULL",
    }
    values.update(overrides)
    return AUTOMATIC_BATCH.format(**values)


@pytest.fixture
def migration_url(monkeypatch):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(url, PREVIOUS, monkeypatch)
        asyncio.run(execute(url, MANUAL_BATCH))
        yield url
    finally:
        asyncio.run(drop_database(url))


def test_0093_seeds_a_disabled_actor_enforces_modes_and_blocks_lossy_downgrade(
    migration_url, monkeypatch
) -> None:
    upgrade_to(migration_url, CURRENT, monkeypatch)

    async def model_drift():
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                return await connection.run_sync(
                    lambda sync: compare_metadata(
                        MigrationContext.configure(sync, opts={"compare_type": True}),
                        Base.metadata,
                    )
                )
        finally:
            await engine.dispose()

    changes = asyncio.run(model_drift())
    assert [change for change in changes if any(t in repr(change) for t in TABLES)] == []
    # Existing batches become maker-checker; nothing is automatic by default.
    assert asyncio.run(
        fetch_all(migration_url, "SELECT approval_mode, automatic_run_id FROM payout_batches")
    ) == [("maker_checker", None)]
    ((email, role, user_status, password_hash, name),) = asyncio.run(
        fetch_all(
            migration_url,
            "SELECT email, role, status, password_hash, full_name FROM users"
            f" WHERE id = '{CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID}'",
        )
    )
    assert (email, role, user_status) == (
        CARDVERT_AUTOMATIC_PAYOUT_ACTOR_EMAIL,
        "admin",
        "disabled",
    )
    assert name == "Cardvert (automatic payouts)"
    assert password_hash.startswith("$argon2") and not verify_password("", password_hash)
    assert asyncio.run(
        fetch_all(
            migration_url,
            "SELECT id, paused, reason, changed_by_user_id, actor_password_fingerprint"
            " FROM payout_automatic_controls",
        )
    ) == [(1, False, None, None, hashlib.sha256(password_hash.encode()).hexdigest())]

    invalid = (
        # A second control row, or a pause without who/why.
        "INSERT INTO payout_automatic_controls (id, paused, actor_password_fingerprint)"
        " VALUES (2, false, '" + "c" * 64 + "')",
        "UPDATE payout_automatic_controls SET paused = true",
        # A maker-checker batch may not point at a run.
        "UPDATE payout_batches SET automatic_run_id = '93000000-0000-0000-0000-000000000002'",
        # An automatic run may not exceed its own limit.
        RUN.format(total="1000.01"),
        # An automatic batch needs its run and approval time, and no human approver.
        automatic_batch(run="NULL"),
        automatic_batch(approved_at="NULL"),
        automatic_batch(approver="'" + ADMIN + "'"),
        # Only the system actor makes automatic batches, and never manual ones.
        automatic_batch(actor=ADMIN),
        "UPDATE payout_batches SET created_by_user_id = '"
        + str(CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID)
        + "'",
        # Alert kinds are closed and a resolution needs who, when and a note.
        "INSERT INTO payout_automatic_alerts (kind, dedupe_key, detail) VALUES"
        " ('other', 'k1', '{}')",
        "INSERT INTO payout_automatic_alerts (kind, dedupe_key, detail, resolved_at) VALUES"
        " ('run_failed', 'k2', '{}', now())",
    )
    for statement in invalid:
        with pytest.raises(IntegrityError):
            asyncio.run(execute(migration_url, statement))

    # With no automatic history the migration round-trips.
    downgrade_to(migration_url, PREVIOUS, monkeypatch)
    assert asyncio.run(
        fetch_all(
            migration_url,
            f"SELECT count(*) FROM users WHERE id = '{CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID}'",
        )
    ) == [(0,)]
    upgrade_to(migration_url, CURRENT, monkeypatch)

    asyncio.run(execute(migration_url, RUN.format(total="100")))
    asyncio.run(execute(migration_url, automatic_batch()))
    with pytest.raises(RuntimeError, match="0093 downgrade blocked"):
        downgrade_to(migration_url, PREVIOUS, monkeypatch)

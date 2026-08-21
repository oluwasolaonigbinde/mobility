"""Migration 0020: maker-checker payout correction orders (MNY-06C).

Style-B: throwaway Postgres database, real Alembic chain. 0020 is create-only
for `payout_correction_orders` plus an additive nullable
`earnings_ledger_entries.release_at` column (PR13), so the tests verify the
empty create, the constraint set (status CHECK + approver <> creator CHECK),
the new column, and a clean downgrade/re-upgrade. The autogenerate-empty
check lives in test_migration_0014_partitioning and covers model/table
parity.
"""

import asyncio

from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    fetch_all,
    upgrade_to,
)

REVISION_PRE_CORRECTIONS = "0019_assignment_rule_bindings"


def test_correction_orders_created_empty_and_downgrade_drops_them(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        count = asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM payout_correction_orders")
        )
        assert count == [(0,)]

        columns = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT column_name, is_nullable"
                " FROM information_schema.columns"
                " WHERE table_name = 'payout_correction_orders'"
                " ORDER BY column_name",
            )
        )
        by_column = {row[0]: row[1] for row in columns}
        assert by_column["campaign_id"] == "NO"
        assert by_column["lagos_day"] == "NO"
        assert by_column["status"] == "NO"
        assert by_column["created_by_user_id"] == "NO"
        assert by_column["approved_by_user_id"] == "YES"
        assert by_column["executed_by_user_id"] == "YES"
        assert by_column["reason"] == "NO"
        assert by_column["projected_delta"] == "YES"
        assert by_column["projection_fingerprint"] == "YES"
        assert by_column["projected_at"] == "YES"
        assert by_column["decided_at"] == "YES"
        assert by_column["executed_at"] == "YES"
        assert by_column["execution_result"] == "YES"

        # PR13: additive nullable release column; nothing consumes it until
        # MNY-03A's release sweep.
        release = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT is_nullable, data_type"
                " FROM information_schema.columns"
                " WHERE table_name = 'earnings_ledger_entries'"
                " AND column_name = 'release_at'",
            )
        )
        assert release == [("YES", "timestamp with time zone")]

        downgrade_to(migration_url, REVISION_PRE_CORRECTIONS, monkeypatch)
        tables = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.tables"
                " WHERE table_name = 'payout_correction_orders'",
            )
        )
        assert tables == [(0,)]
        release_gone = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.columns"
                " WHERE table_name = 'earnings_ledger_entries'"
                " AND column_name = 'release_at'",
            )
        )
        assert release_gone == [(0,)]
        upgrade_to(migration_url, "head", monkeypatch)
        recount = asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM payout_correction_orders")
        )
        assert recount == [(0,)]
    finally:
        asyncio.run(drop_database(migration_url))


def test_correction_order_constraints_exist(monkeypatch) -> None:
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
                    " WHERE conrelid = 'payout_correction_orders'::regclass",
                )
            )
        }
        assert "ck_payout_correction_orders_status" in constraints
        assert "ck_payout_correction_orders_approver_not_creator" in constraints
    finally:
        asyncio.run(drop_database(migration_url))

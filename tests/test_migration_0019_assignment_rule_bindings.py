"""Migration 0019: acceptance-time payout value freeze (MNY-06B).

Style-B: throwaway Postgres database, real Alembic chain. 0019 is create-only
— assignments accepted before it get NO backfilled binding (they stay
payout_v2) — so the tests verify the empty create, the constraint set, and a
clean downgrade/re-upgrade. The autogenerate-empty check lives in
test_migration_0014_partitioning and covers the new model/table parity.
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

REVISION_PRE_BINDINGS = "0018_payout_rule_revisions"


def test_bindings_table_created_empty_and_downgrade_drops_it(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        count = asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM assignment_rule_bindings")
        )
        # Create only, no backfill: pre-existing accepted assignments keep v2.
        assert count == [(0,)]

        defaults = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT column_name, is_nullable, column_default"
                " FROM information_schema.columns"
                " WHERE table_name = 'assignment_rule_bindings'"
                " ORDER BY column_name",
            )
        )
        by_column = {row[0]: (row[1], row[2]) for row in defaults}
        assert by_column["hourly_rate_naira"][0] == "NO"
        assert by_column["premium_hourly_rate_naira"][0] == "YES"
        assert by_column["daily_payable_hours_cap"][0] == "YES"
        assert by_column["eligibility_params"][0] == "NO"
        assert by_column["formula_version"][0] == "NO"
        assert by_column["premium_zone_ids"][0] == "NO"
        assert by_column["premium_zone_geometry_hash"][0] == "NO"
        assert by_column["stationary_policy_marker"] == (
            "NO",
            "'ext-rm2-fail-closed'::text",
        )
        assert by_column["bound_at"][0] == "NO"

        downgrade_to(migration_url, REVISION_PRE_BINDINGS, monkeypatch)
        tables = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.tables"
                " WHERE table_name = 'assignment_rule_bindings'",
            )
        )
        assert tables == [(0,)]
        upgrade_to(migration_url, "head", monkeypatch)
        recount = asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM assignment_rule_bindings")
        )
        assert recount == [(0,)]
    finally:
        asyncio.run(drop_database(migration_url))


def test_binding_table_constraints_exist(monkeypatch) -> None:
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
                    " WHERE conrelid = 'assignment_rule_bindings'::regclass",
                )
            )
        }
        assert "uq_assignment_rule_bindings_assignment_id" in constraints
        assert "ck_assignment_rule_bindings_hourly_rate_non_negative" in constraints
        assert "ck_assignment_rule_bindings_premium_rate_non_negative" in constraints
    finally:
        asyncio.run(drop_database(migration_url))

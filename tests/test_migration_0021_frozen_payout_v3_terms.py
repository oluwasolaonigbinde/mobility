"""Migration 0021: complete payout_v3 acceptance-time terms freeze."""

import asyncio

from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    fetch_all,
    upgrade_to,
)

REVISION_PRE_FREEZE = "0020_payout_correction_orders"


def test_frozen_terms_columns_upgrade_downgrade_and_reupgrade(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        # 0019–0021 are deployed as one lane. 0021 itself asserts the interim
        # binding table is empty because the missing accepted geometry and
        # resolved settings cannot be reconstructed truthfully.
        binding_count = asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM assignment_rule_bindings")
        )
        assert binding_count == [(0,)]
        rows = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT column_name, is_nullable, column_default"
                " FROM information_schema.columns"
                " WHERE table_name = 'assignment_rule_bindings'"
                " AND column_name IN ("
                " 'resolved_eligibility_params',"
                " 'premium_zone_geometry_wkts',"
                " 'exclusion_zone_ids',"
                " 'exclusion_zone_geometry_hash',"
                " 'exclusion_zone_geometry_wkts')"
                " ORDER BY column_name",
            )
        )
        by_column = {row[0]: (row[1], row[2]) for row in rows}
        assert by_column["resolved_eligibility_params"] == ("YES", None)
        assert by_column["premium_zone_geometry_wkts"][0] == "NO"
        assert by_column["exclusion_zone_ids"][0] == "NO"
        assert by_column["exclusion_zone_geometry_hash"][0] == "NO"
        assert by_column["exclusion_zone_geometry_wkts"][0] == "NO"

        downgrade_to(migration_url, REVISION_PRE_FREEZE, monkeypatch)
        remaining = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.columns"
                " WHERE table_name = 'assignment_rule_bindings'"
                " AND column_name IN ("
                " 'resolved_eligibility_params',"
                " 'premium_zone_geometry_wkts',"
                " 'exclusion_zone_ids',"
                " 'exclusion_zone_geometry_hash',"
                " 'exclusion_zone_geometry_wkts')",
            )
        )
        assert remaining == [(0,)]
        upgrade_to(migration_url, "head", monkeypatch)
        restored = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.columns"
                " WHERE table_name = 'assignment_rule_bindings'"
                " AND column_name = 'resolved_eligibility_params'",
            )
        )
        assert restored == [(1,)]
    finally:
        asyncio.run(drop_database(migration_url))

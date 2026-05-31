from pathlib import Path


def test_slice1_migration_contains_only_approved_tables() -> None:
    migration = Path("alembic/versions/0002_identity_and_organizations.py").read_text()

    assert 'down_revision: str | None = "0001_enable_extensions"' in migration
    for table_name in [
        "users",
        "advertiser_organizations",
        "organization_memberships",
        "audit_events",
    ]:
        assert f'"{table_name}"' in migration
    for forbidden_table in [
        "drivers",
        "vehicles",
        "campaigns",
        "creatives",
        "gps_pings",
        "trip_sessions",
        "payouts",
        "ledgers",
    ]:
        assert f'"{forbidden_table}"' not in migration
    assert "gen_random_uuid()" in migration
    assert "'{}'::jsonb" in migration

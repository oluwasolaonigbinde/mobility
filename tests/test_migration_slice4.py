from pathlib import Path


def test_slice4_migration_contains_only_campaign_zone_table() -> None:
    migration = Path("alembic/versions/0005_campaign_zones.py").read_text()

    assert 'down_revision: str | None = "0004_campaigns_and_creatives"' in migration
    assert migration.count("op.create_table(") == 1
    assert '"campaign_zones"' in migration
    for required_constraint_or_index in [
        "ck_campaign_zones_zone_type",
        "ix_campaign_zones_campaign_id",
        "ix_campaign_zones_campaign_zone_type",
        "ix_campaign_zones_created_by_user_id",
        "ix_campaign_zones_geom",
        'postgresql_using="gist"',
        "geometry(MultiPolygon,4326)",
        "gen_random_uuid()",
        "'{}'::jsonb",
    ]:
        assert required_constraint_or_index in migration
    for required_column in [
        '"campaign_id"',
        '"created_by_user_id"',
        '"name"',
        '"description"',
        '"zone_type"',
        '"geom"',
        '"metadata"',
        '"created_at"',
        '"updated_at"',
    ]:
        assert required_column in migration
    for forbidden_table in [
        "campaign_assignments",
        "driver_activations",
        "gps_pings",
        "trip_sessions",
        "route_analytics",
        "fraud_flags",
        "impressions",
        "payouts",
        "earnings_ledgers",
        "reports",
        "heatmaps",
        "seed_trips",
    ]:
        assert f'"{forbidden_table}"' not in migration

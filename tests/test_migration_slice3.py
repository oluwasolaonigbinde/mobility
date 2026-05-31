from pathlib import Path


def test_slice3_migration_contains_only_campaign_and_creative_tables() -> None:
    migration = Path("alembic/versions/0004_campaigns_and_creatives.py").read_text()

    assert 'down_revision: str | None = "0003_driver_vehicle_foundations"' in migration
    assert migration.count("op.create_table(") == 2
    for table_name in ["campaigns", "campaign_creatives"]:
        assert f'"{table_name}"' in migration
    for required_constraint_or_index in [
        "ck_campaigns_status",
        "ck_campaigns_currency_length",
        "ck_campaigns_budget_amount_non_negative",
        "ck_campaigns_daily_budget_amount_non_negative",
        "ck_campaigns_daily_budget_not_exceed_budget",
        "ck_campaigns_date_range",
        "ix_campaigns_organization_id",
        "ix_campaigns_organization_status",
        "ix_campaigns_start_end",
        "ix_campaigns_created_by_user_id",
        "ck_campaign_creatives_creative_type",
        "ck_campaign_creatives_placement",
        "ck_campaign_creatives_status",
        "ck_campaign_creatives_width_positive",
        "ck_campaign_creatives_height_positive",
        "ck_campaign_creatives_duration_positive",
        "ix_campaign_creatives_campaign_id",
        "ix_campaign_creatives_campaign_status",
        "ix_campaign_creatives_creative_type",
    ]:
        assert required_constraint_or_index in migration
    for forbidden_table in [
        "campaign_zones",
        "geofences",
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
    assert "gen_random_uuid()" in migration
    assert "'{}'::jsonb" in migration

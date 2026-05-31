from pathlib import Path


def test_slice5_migration_contains_only_assignment_tables() -> None:
    migration = Path("alembic/versions/0006_campaign_assignments.py").read_text()

    assert 'down_revision: str | None = "0005_campaign_zones"' in migration
    assert migration.count("op.create_table(") == 2
    assert '"campaign_assignments"' in migration
    assert '"campaign_activation_events"' in migration
    for required_constraint_or_index in [
        "ck_campaign_assignments_status",
        "ck_campaign_activation_events_event_type",
        "ix_campaign_assignments_campaign_id",
        "ix_campaign_assignments_driver_profile_id",
        "ix_campaign_assignments_vehicle_id",
        "ix_campaign_assignments_campaign_status",
        "ix_campaign_assignments_driver_status",
        "ix_campaign_assignments_vehicle_status",
        "uq_campaign_assignments_vehicle_active",
        "uq_campaign_assignments_campaign_vehicle_non_terminal",
        "ix_campaign_activation_events_assignment_id",
        "ix_campaign_activation_events_actor_user_id",
        "ix_campaign_activation_events_assignment_occurred",
        "postgresql_where=sa.text(\"status = 'active'\")",
        "status IN ('offered', 'accepted', 'active', 'deactivated')",
        "gen_random_uuid()",
        "'{}'::jsonb",
    ]:
        assert required_constraint_or_index in migration
    for required_column in [
        '"campaign_id"',
        '"driver_profile_id"',
        '"vehicle_id"',
        '"assigned_by_user_id"',
        '"status"',
        '"offered_at"',
        '"accepted_at"',
        '"activated_at"',
        '"deactivated_at"',
        '"cancelled_at"',
        '"completed_at"',
        '"notes"',
        '"metadata"',
        '"created_at"',
        '"updated_at"',
        '"assignment_id"',
        '"actor_user_id"',
        '"event_type"',
        '"previous_status"',
        '"new_status"',
        '"occurred_at"',
    ]:
        assert required_column in migration
    for forbidden_table in [
        "gps_pings",
        "trip_sessions",
        "location_pings",
        "route_analytics",
        "zone_overlap_analytics",
        "fraud_flags",
        "impressions",
        "payouts",
        "earnings_ledgers",
        "reports",
        "heatmaps",
        "seed_trips",
    ]:
        assert f'"{forbidden_table}"' not in migration

from pathlib import Path


def test_slice6_migration_contains_only_trip_tracking_tables() -> None:
    migration = Path("alembic/versions/0007_trip_tracking.py").read_text()

    assert 'down_revision: str | None = "0006_campaign_assignments"' in migration
    assert migration.count("op.create_table(") == 3
    assert '"trip_sessions"' in migration
    assert '"location_ping_batches"' in migration
    assert '"location_pings"' in migration
    for required_constraint_or_index in [
        "ck_trip_sessions_status",
        "uq_trip_sessions_driver_profile_active",
        "uq_trip_sessions_vehicle_active",
        "ck_location_ping_batches_pings_accepted_non_negative",
        "uq_location_ping_batches_trip_idempotency_key",
        "ix_location_ping_batches_trip_received_at",
        "ck_location_pings_sequence_number_non_negative",
        "ck_location_pings_latitude",
        "ck_location_pings_longitude",
        "ix_location_pings_geom",
        'postgresql_using="gist"',
        'postgresql_where=sa.text("status = \'active\'")',
        "geometry(Point,4326)",
        "gen_random_uuid()",
        "'{}'::jsonb",
    ]:
        assert required_constraint_or_index in migration
    for required_column in [
        '"assignment_id"',
        '"campaign_id"',
        '"driver_profile_id"',
        '"vehicle_id"',
        '"started_by_user_id"',
        '"status"',
        '"started_at"',
        '"ended_at"',
        '"end_reason"',
        '"idempotency_key"',
        '"payload_hash"',
        '"pings_accepted"',
        '"received_at"',
        '"batch_id"',
        '"recorded_at"',
        '"sequence_number"',
        '"latitude"',
        '"longitude"',
        '"accuracy_m"',
        '"speed_mps"',
        '"heading_degrees"',
        '"altitude_m"',
        '"geom"',
        '"metadata"',
        '"created_at"',
        '"updated_at"',
    ]:
        assert required_column in migration
    for forbidden_table in [
        "route_analytics",
        "zone_overlap_analytics",
        "fraud_flags",
        "impressions",
        "payouts",
        "earnings_ledgers",
        "reports",
        "heatmaps",
        "map_tiles",
        "seed_trips",
    ]:
        assert f'"{forbidden_table}"' not in migration

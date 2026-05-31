from pathlib import Path


def test_slice2_migration_contains_only_driver_and_vehicle_tables() -> None:
    migration = Path("alembic/versions/0003_driver_vehicle_foundations.py").read_text()

    assert 'down_revision: str | None = "0002_identity_and_organizations"' in migration
    for table_name in ["driver_profiles", "vehicles"]:
        assert f'"{table_name}"' in migration
    for required_constraint_or_index in [
        "ck_driver_profiles_onboarding_status",
        "uq_driver_profiles_user_id",
        "ix_driver_profiles_user_id",
        "ix_driver_profiles_onboarding_status",
        "ix_driver_profiles_country_city",
        "ck_vehicles_vehicle_type",
        "ck_vehicles_status",
        "uq_vehicles_plate_country_normalized",
        "ix_vehicles_driver_profile_id",
        "ix_vehicles_status",
        "ix_vehicles_plate_country_normalized",
    ]:
        assert required_constraint_or_index in migration
    for forbidden_table in [
        "campaigns",
        "creatives",
        "geofences",
        "assignments",
        "gps_pings",
        "trip_sessions",
        "route_analytics",
        "payouts",
        "earnings_ledgers",
        "heatmaps",
    ]:
        assert f'"{forbidden_table}"' not in migration
    assert "gen_random_uuid()" in migration
    assert "'{}'::jsonb" in migration

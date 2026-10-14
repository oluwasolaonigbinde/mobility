"""Retire development payout engines and unsigned trip evidence (D80)."""

import sqlalchemy as sa

from alembic import op

revision = "0103_retire_legacy_engines"
down_revision = "0102_driver_agreement_acceptance"
branch_labels = None
depends_on = None

RETIRED_COLUMNS = {
    "campaign_payout_rules": [
        "base_rate_per_active_hour",
        "base_rate_per_km",
        "bonus_zone_bonus_rate_per_km",
        "daily_payable_hours_cap",
        "eligibility_params",
        "estimated_impression_rate_per_1000",
        "high_fraud_multiplier",
        "hourly_rate_naira",
        "low_fraud_multiplier",
        "max_payout_per_trip",
        "medium_fraud_multiplier",
        "min_payout_per_trip",
        "target_zone_bonus_rate_per_km",
    ],
    "campaign_payout_rule_revisions": [
        "daily_payable_hours_cap",
        "hourly_rate_naira",
        "premium_hourly_rate_naira",
    ],
    "assignment_rule_bindings": [
        "daily_payable_hours_cap",
        "hourly_rate_naira",
        "premium_hourly_rate_naira",
    ],
    "payout_calculations": [
        "active_time_component",
        "bonus_zone_bonus_component",
        "cap_adjustment",
        "distance_component",
        "fraud_multiplier",
        "impression_component",
        "payable_seconds",
        "payable_seconds_by_day",
        "quality_multiplier",
        "target_zone_bonus_component",
    ],
}


def upgrade() -> None:
    # No live data exists. Legacy demo data is disposable; this migration
    # refuses incompatible rows instead of translating unaccepted money terms.
    for table, columns in RETIRED_COLUMNS.items():
        for column in columns:
            op.drop_column(table, column)
    op.create_check_constraint(
        "ck_campaign_payout_rules_model_xor",
        "campaign_payout_rules",
        "formula_version = 'payout_v4'",
    )
    for table in ("campaign_payout_rule_revisions", "assignment_rule_bindings"):
        # Dropping hourly columns drops the dependent old shape constraint.
        op.create_check_constraint(
            f"ck_{table}_terms_shape",
            table,
            "formula_version = 'payout_v4' AND daily_rate_naira IS NOT NULL AND "
            "daily_target_miles IS NOT NULL AND minimum_miles IS NOT NULL AND "
            "outside_area_weight IS NOT NULL AND shortfall_strategy IS NOT NULL AND "
            "daily_rate_naira > 0 AND daily_target_miles > 0 AND minimum_miles >= 0 AND "
            "minimum_miles <= daily_target_miles AND outside_area_weight >= 0 AND "
            "outside_area_weight <= 1 AND ((shortfall_strategy = 'proportional' AND "
            "deduction_per_mile_naira IS NULL) OR (shortfall_strategy = "
            "'per_mile_deduction' AND deduction_per_mile_naira IS NOT NULL AND "
            "deduction_per_mile_naira > 0))",
        )
    op.create_check_constraint(
        "ck_payout_calculations_daily_rate_fields",
        "payout_calculations",
        "formula_version = 'payout_v4' AND eligible_seconds IS NOT NULL AND "
        "excluded_seconds_by_reason IS NOT NULL AND inputs_fingerprint IS NOT NULL AND "
        "distance_m_by_day IS NOT NULL AND amount_by_day IS NOT NULL",
    )
    for table in ("campaign_payout_rules", "payout_calculations"):
        op.alter_column(table, "formula_version", server_default=sa.text("'payout_v4'"))
    op.drop_constraint("ck_trip_sessions_evidence_protocol_version", "trip_sessions", type_="check")
    op.create_check_constraint(
        "ck_trip_sessions_evidence_protocol_version",
        "trip_sessions",
        "evidence_protocol_version = 2",
    )
    op.drop_constraint(
        "ck_trip_sessions_v2_sealed_manifest_verified", "trip_sessions", type_="check"
    )
    op.create_check_constraint(
        "ck_trip_sessions_v2_sealed_manifest_verified",
        "trip_sessions",
        "status != 'sealed' OR evidence_manifest_verified_at IS NOT NULL",
    )
    op.alter_column("location_ping_batches", "payload_hash_version", server_default=sa.text("2"))
    op.alter_column("quarantined_ping_batches", "payload_hash_version", server_default=sa.text("2"))
    op.drop_constraint(
        "ck_location_ping_batches_evidence_scope", "location_ping_batches", type_="check"
    )
    op.create_check_constraint(
        "ck_location_ping_batches_evidence_scope",
        "location_ping_batches",
        "evidence_scope IN ('manifest', 'postseal_applied')",
    )
    op.alter_column("location_ping_batches", "evidence_scope", server_default=sa.text("'manifest'"))
    op.execute(
        sa.text("""
        CREATE OR REPLACE FUNCTION prevent_assignment_rule_binding_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
                RAISE EXCEPTION 'assignment rule binding evidence is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    )


def downgrade() -> None:
    raise RuntimeError("Development legacy engines were removed; recreate the development database")

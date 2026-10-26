"""Remove unrequested daily display proof and automatic driver challenges.

Revision ID: 0109_remove_daily_display_proof
Revises: 0108_req180_backend_batch2
"""

from alembic import op

revision = "0109_remove_daily_display_proof"
down_revision = "0108_req180_backend_batch2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Disposable development challenge records have no continuing purpose.
    op.execute(
        "DELETE FROM evidence_verifications WHERE verification_type <> 'physical_spot_check'"
    )
    for name in (
        "ck_evidence_verifications_resolution",
        "ck_evidence_verifications_due_at",
        "ck_evidence_verifications_type",
        "ck_evidence_verifications_status",
    ):
        op.drop_constraint(name, "evidence_verifications", type_="check")
    op.drop_index("uq_evidence_verifications_automatic_source", table_name="evidence_verifications")
    op.drop_column("evidence_verifications", "display_proof_id")
    op.drop_column("trip_sessions", "display_proof_id")
    op.drop_table("display_proofs")
    op.drop_table("display_proof_challenges")
    op.execute("DROP FUNCTION guard_display_proof_challenge_mutation()")
    op.create_check_constraint(
        "ck_evidence_verifications_type",
        "evidence_verifications",
        "verification_type = 'physical_spot_check'",
    )
    op.create_check_constraint(
        "ck_evidence_verifications_status",
        "evidence_verifications",
        "status IN ('pending', 'passed', 'failed')",
    )
    op.create_check_constraint(
        "ck_evidence_verifications_resolution",
        "evidence_verifications",
        "(status = 'pending' AND resolved_at IS NULL AND resolved_by_user_id IS NULL "
        "AND fraud_flag_id IS NULL) OR "
        "(status = 'passed' AND resolved_at IS NOT NULL AND resolved_by_user_id IS NOT NULL "
        "AND fraud_flag_id IS NULL) OR "
        "(status = 'failed' AND resolved_at IS NOT NULL AND fraud_flag_id IS NOT NULL)",
    )
    op.drop_constraint("ck_fraud_flags_flag_type", "fraud_flags", type_="check")
    op.create_check_constraint(
        "ck_fraud_flags_flag_type",
        "fraud_flags",
        "flag_type IN ('insufficient_pings', 'impossible_speed', 'poor_accuracy', "
        "'stationary_trip', 'excessive_ping_gap', 'future_timestamp', 'route_looping', "
        "'route_replay', 'exclusion_zone_presence', 'physical_spot_check_failed')",
    )


def downgrade() -> None:
    raise RuntimeError("Recreate the disposable development database to restore removed features")

"""Remove unused privacy/complaint steps and simplify driver operations.

Revision ID: 0110_simplify_driver_operations
Revises: 0109_remove_daily_display_proof
"""

from alembic import op

revision = "0110_simplify_driver_operations"
down_revision = "0109_remove_daily_display_proof"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("data_subject_location_assessments")
    op.drop_table("data_subject_requests")
    op.execute("DROP FUNCTION reject_data_subject_assessment_mutation()")
    op.execute("DROP FUNCTION validate_data_subject_request_mutation()")
    op.drop_column("complaints", "assigned_to_user_id")
    for name in (
        "ck_assignment_activity_flags_type",
        "ck_assignment_activity_flags_status",
        "ck_assignment_activity_flags_recovery_coherence",
    ):
        op.drop_constraint(name, "assignment_activity_flags", type_="check")
    op.alter_column("assignment_activity_flags", "recovered_at", new_column_name="closed_at")
    op.create_check_constraint(
        "ck_assignment_activity_flags_type", "assignment_activity_flags", "flag_type = 'inactivity'"
    )
    op.create_check_constraint(
        "ck_assignment_activity_flags_status",
        "assignment_activity_flags",
        "status IN ('open', 'closed')",
    )
    op.create_check_constraint(
        "ck_assignment_activity_flags_recovery_coherence",
        "assignment_activity_flags",
        "(status = 'open' AND closed_at IS NULL) OR (status = 'closed' AND closed_at IS NOT NULL)",
    )
    op.drop_constraint(
        "ck_assignment_activity_flag_events_type", "assignment_activity_flag_events", type_="check"
    )
    op.create_check_constraint(
        "ck_assignment_activity_flag_events_type",
        "assignment_activity_flag_events",
        "event_type IN ('opened', 'closed')",
    )
    op.drop_constraint("ck_evidence_verifications_status", "evidence_verifications", type_="check")
    op.drop_constraint(
        "ck_evidence_verifications_resolution", "evidence_verifications", type_="check"
    )
    op.drop_column("evidence_verifications", "due_at")
    op.drop_column("evidence_verifications", "result_fingerprint")
    op.create_check_constraint(
        "ck_evidence_verifications_status",
        "evidence_verifications",
        "status IN ('passed', 'failed')",
    )
    op.create_check_constraint(
        "ck_evidence_verifications_resolution",
        "evidence_verifications",
        "resolved_at IS NOT NULL AND resolved_by_user_id IS NOT NULL AND "
        "((status = 'passed' AND fraud_flag_id IS NULL) OR "
        "(status = 'failed' AND fraud_flag_id IS NOT NULL))",
    )


def downgrade() -> None:
    raise RuntimeError("Recreate the disposable development database to restore removed workflows")

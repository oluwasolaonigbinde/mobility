"""Add recurring proof challenges and physical spot-check authority."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0060_evidence_verifications"
down_revision: str | Sequence[str] | None = "0059_campaign_cancellations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_fraud_flags_flag_type", "fraud_flags", type_="check")
    op.create_check_constraint(
        "ck_fraud_flags_flag_type",
        "fraud_flags",
        "flag_type IN ('insufficient_pings', 'impossible_speed', 'poor_accuracy', "
        "'stationary_trip', 'excessive_ping_gap', 'future_timestamp', 'route_looping', "
        "'route_replay', 'exclusion_zone_presence', 'missed_display_challenge', "
        "'concurrent_session_day', 'physical_spot_check_failed')",
    )
    op.create_table(
        "evidence_verifications",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("assignment_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("campaign_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_trip_session_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("verification_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("issued_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("client_request_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=True),
        sa.Column("result_fingerprint", sa.String(64), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("display_proof_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("fraud_flag_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("result_note", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "verification_type IN ('high_earner_renewal', 'concurrent_session', "
            "'physical_spot_check')",
            name="ck_evidence_verifications_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'satisfied', 'missed', 'passed', 'failed')",
            name="ck_evidence_verifications_status",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL AND resolved_by_user_id IS NULL "
            "AND display_proof_id IS NULL AND fraud_flag_id IS NULL) OR "
            "(status = 'satisfied' AND resolved_at IS NOT NULL "
            "AND display_proof_id IS NOT NULL AND fraud_flag_id IS NULL) OR "
            "(status = 'missed' AND resolved_at IS NOT NULL "
            "AND display_proof_id IS NULL AND fraud_flag_id IS NOT NULL) OR "
            "(status = 'passed' AND resolved_at IS NOT NULL "
            "AND resolved_by_user_id IS NOT NULL AND display_proof_id IS NULL "
            "AND fraud_flag_id IS NULL) OR "
            "(status = 'failed' AND resolved_at IS NOT NULL "
            "AND display_proof_id IS NULL AND fraud_flag_id IS NOT NULL)",
            name="ck_evidence_verifications_resolution",
        ),
        sa.CheckConstraint(
            "(verification_type = 'high_earner_renewal' AND due_at IS NOT NULL) OR "
            "(verification_type <> 'high_earner_renewal' AND due_at IS NULL)",
            name="ck_evidence_verifications_due_at",
        ),
        sa.CheckConstraint(
            "(verification_type = 'physical_spot_check' AND issued_by_user_id IS NOT NULL "
            "AND client_request_id IS NOT NULL AND request_fingerprint IS NOT NULL) OR "
            "(verification_type <> 'physical_spot_check' AND client_request_id IS NULL "
            "AND request_fingerprint IS NULL)",
            name="ck_evidence_verifications_request_authority",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["campaign_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_trip_session_id"], ["trip_sessions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["display_proof_id"], ["display_proofs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["fraud_flag_id"], ["fraud_flags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_verifications_assignment_status",
        "evidence_verifications",
        ["assignment_id", "status"],
    )
    op.create_index(
        "ix_evidence_verifications_driver_status",
        "evidence_verifications",
        ["driver_profile_id", "status"],
    )
    op.create_index(
        "ix_evidence_verifications_type_status",
        "evidence_verifications",
        ["verification_type", "status"],
    )
    op.create_index(
        "uq_evidence_verifications_automatic_source",
        "evidence_verifications",
        ["verification_type", "source_trip_session_id"],
        unique=True,
        postgresql_where=sa.text("verification_type <> 'physical_spot_check'"),
    )
    op.create_index(
        "uq_evidence_verifications_admin_request",
        "evidence_verifications",
        ["issued_by_user_id", "client_request_id"],
        unique=True,
        postgresql_where=sa.text("client_request_id IS NOT NULL"),
    )
    op.create_index(
        "ix_evidence_verifications_fraud_flag",
        "evidence_verifications",
        ["fraud_flag_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    populated = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM evidence_verifications)")
    ).scalar_one()
    new_flags = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM fraud_flags WHERE flag_type IN "
            "('missed_display_challenge', 'concurrent_session_day', "
            "'physical_spot_check_failed'))"
        )
    ).scalar_one()
    if populated or new_flags:
        raise RuntimeError(
            "cannot downgrade while evidence verification or derived fraud evidence is populated"
        )
    op.drop_table("evidence_verifications")
    op.drop_constraint("ck_fraud_flags_flag_type", "fraud_flags", type_="check")
    op.create_check_constraint(
        "ck_fraud_flags_flag_type",
        "fraud_flags",
        "flag_type IN ('insufficient_pings', 'impossible_speed', 'poor_accuracy', "
        "'stationary_trip', 'excessive_ping_gap', 'future_timestamp', 'route_looping', "
        "'route_replay', 'exclusion_zone_presence')",
    )

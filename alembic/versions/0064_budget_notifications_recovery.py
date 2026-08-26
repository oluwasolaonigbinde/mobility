"""Add budget enforcement, audited contact, and account recovery authority.

Revision ID: 0064_budget_notifications_recovery
Revises: 0063_measurement_runs
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0064_budget_notifications_recovery"
down_revision: str | Sequence[str] | None = "0063_measurement_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    op.drop_constraint(
        "ck_budget_policy_evaluations_state", "budget_policy_evaluations", type_="check"
    )
    op.drop_constraint(
        "ck_budget_policy_evaluations_external_gate",
        "budget_policy_evaluations",
        type_="check",
    )
    op.drop_constraint(
        "ck_budget_policy_evaluations_blocked_fields",
        "budget_policy_evaluations",
        type_="check",
    )
    op.alter_column("budget_policy_evaluations", "external_gate", nullable=True)
    op.alter_column(
        "budget_policy_evaluations", "policy_version", new_column_name="policy_revision"
    )
    op.add_column("budget_policy_evaluations", sa.Column("policy_id", sa.String(128)))
    op.add_column("budget_policy_evaluations", sa.Column("policy_source", sa.String(32)))
    op.add_column("budget_policy_evaluations", sa.Column("budget_basis", sa.String(16)))
    op.add_column("budget_policy_evaluations", sa.Column("billing_fact_source", sa.String(32)))
    op.add_column(
        "budget_policy_evaluations", sa.Column("resume_threshold_amount", sa.Numeric(14, 2))
    )
    op.add_column(
        "budget_policy_evaluations",
        sa.Column("alert_applied", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "budget_policy_evaluations",
        sa.Column("resume_allowed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_check_constraint(
        "ck_budget_policy_evaluations_state",
        "budget_policy_evaluations",
        "state IN ('blocked_external_policy', 'within_budget', 'alert_threshold', "
        "'pause_threshold')",
    )
    op.create_check_constraint(
        "ck_budget_policy_evaluations_external_gate",
        "budget_policy_evaluations",
        "(state = 'blocked_external_policy' AND external_gate = 'EXT-BUDGET-POLICY') OR "
        "(state <> 'blocked_external_policy' AND external_gate IS NULL)",
    )
    op.create_check_constraint(
        "ck_budget_policy_evaluations_authority_fields",
        "budget_policy_evaluations",
        "(state = 'blocked_external_policy' AND policy_id IS NULL "
        "AND policy_revision IS NULL AND policy_source IS NULL AND budget_basis IS NULL "
        "AND billing_fact_source IS NULL "
        "AND billing_spend_amount IS NULL AND alert_threshold_amount IS NULL "
        "AND pause_threshold_amount IS NULL AND resume_threshold_amount IS NULL "
        "AND alert_applied = false AND pause_applied = false AND resume_allowed = false) OR "
        "(state <> 'blocked_external_policy' AND policy_id IS NOT NULL "
        "AND policy_revision IS NOT NULL "
        "AND policy_source IN ('external_approved', 'synthetic_test') "
        "AND budget_basis IN ('total', 'daily') "
        "AND billing_fact_source IN ('confirmed_funding', 'production_obligation') "
        "AND billing_spend_amount >= 0 "
        "AND alert_threshold_amount >= 0 AND pause_threshold_amount > alert_threshold_amount "
        "AND resume_threshold_amount <= alert_threshold_amount)",
    )

    op.create_table(
        "budget_campaign_transitions",
        _uuid("id"),
        _uuid("campaign_id"),
        _uuid("evaluation_id"),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("prior_status", sa.String(32), nullable=False),
        sa.Column("new_status", sa.String(32), nullable=False),
        _uuid("actor_user_id", nullable=True),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('pause', 'resume')", name="ck_budget_transitions_action"),
        sa.CheckConstraint(
            "prior_status IN ('scheduled', 'active', 'paused') AND "
            "new_status IN ('scheduled', 'active', 'paused') AND prior_status <> new_status",
            name="ck_budget_transitions_statuses",
        ),
        sa.CheckConstraint(
            "(action = 'pause' AND actor_user_id IS NULL AND new_status = 'paused') OR "
            "(action = 'resume' AND actor_user_id IS NOT NULL AND prior_status = 'paused' "
            "AND length(trim(reason)) > 0)",
            name="ck_budget_transitions_authority",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["evaluation_id"], ["budget_policy_evaluations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evaluation_id", "action", name="uq_budget_transition_evaluation_action"
        ),
    )
    op.create_index(
        "ix_budget_campaign_transitions_campaign_id",
        "budget_campaign_transitions",
        ["campaign_id", "created_at"],
    )
    op.execute(
        "CREATE TRIGGER budget_campaign_transitions_append_only "
        "BEFORE UPDATE OR DELETE ON budget_campaign_transitions "
        "FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
    )

    op.create_table(
        "password_reset_attempts",
        _uuid("id"),
        sa.Column("email_digest", sa.String(64), nullable=False),
        sa.Column("ip_digest", sa.String(64), nullable=False),
        _uuid("issued_user_id", nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(email_digest) = 64", name="ck_password_reset_attempt_email_hash"
        ),
        sa.CheckConstraint("length(ip_digest) = 64", name="ck_password_reset_attempt_ip_hash"),
        sa.ForeignKeyConstraint(["issued_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_password_reset_attempt_email",
        "password_reset_attempts",
        ["email_digest", "requested_at"],
    )
    op.create_index(
        "ix_password_reset_attempt_ip", "password_reset_attempts", ["ip_digest", "requested_at"]
    )
    op.create_table(
        "password_reset_tokens",
        _uuid("id"),
        _uuid("attempt_id"),
        _uuid("user_id"),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("length(token_hash) = 64", name="ck_password_reset_tokens_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_password_reset_tokens_expiry"),
        sa.CheckConstraint("session_version > 0", name="ck_password_reset_tokens_session_version"),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["password_reset_attempts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", name="uq_password_reset_tokens_attempt"),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_tokens_hash"),
    )
    op.create_index(
        "ix_password_reset_tokens_user", "password_reset_tokens", ["user_id", "created_at"]
    )

    op.create_table(
        "driver_phone_versions",
        _uuid("id"),
        _uuid("driver_profile_id"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("phone_fingerprint", sa.String(64), nullable=False),
        sa.Column("masked_phone", sa.String(32), nullable=False),
        _uuid("recorded_by_user_id"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("version > 0", name="ck_driver_phone_versions_version"),
        sa.CheckConstraint("length(phone_fingerprint) = 64", name="ck_driver_phone_versions_hash"),
        sa.CheckConstraint("length(masked_phone) > 0", name="ck_driver_phone_versions_mask"),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("driver_profile_id", "version", name="uq_driver_phone_version"),
    )
    op.create_index(
        "ix_driver_phone_versions_profile",
        "driver_phone_versions",
        ["driver_profile_id", "version"],
    )
    op.create_table(
        "phone_verification_challenges",
        _uuid("id"),
        _uuid("phone_version_id"),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _uuid("sent_by_user_id", nullable=True),
        sa.Column("sent_channel", sa.String(16)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("operator_evidence_reference", sa.String(255)),
        sa.Column("provider_message_id", sa.String(255)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("length(code_hash) = 64", name="ck_phone_challenges_hash"),
        sa.CheckConstraint("max_attempts > 0", name="ck_phone_challenges_max_attempts"),
        sa.CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= max_attempts",
            name="ck_phone_challenges_attempt_count",
        ),
        sa.CheckConstraint(
            "status IN ('pending_operator', 'sent', 'verified', 'expired', 'exhausted')",
            name="ck_phone_challenges_status",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_phone_challenges_expiry"),
        sa.CheckConstraint(
            "(sent_by_user_id IS NULL AND sent_channel IS NULL AND sent_at IS NULL "
            "AND operator_evidence_reference IS NULL AND provider_message_id IS NULL) OR "
            "(sent_by_user_id IS NOT NULL AND sent_channel IN ('whatsapp', 'voice') "
            "AND sent_at IS NOT NULL AND length(trim(operator_evidence_reference)) > 0 "
            "AND length(trim(provider_message_id)) > 0)",
            name="ck_phone_challenges_send_evidence",
        ),
        sa.ForeignKeyConstraint(
            ["phone_version_id"], ["driver_phone_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["sent_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_phone_challenges_version",
        "phone_verification_challenges",
        ["phone_version_id", "created_at"],
    )
    op.create_table(
        "whatsapp_consents",
        _uuid("id"),
        _uuid("driver_profile_id"),
        _uuid("phone_version_id"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(128), nullable=False),
        sa.Column("notice_version", sa.String(64), nullable=False),
        _uuid("granted_by_user_id"),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        _uuid("withdrawn_by_user_id", nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("version > 0", name="ck_whatsapp_consents_version"),
        sa.CheckConstraint("length(trim(purpose)) > 0", name="ck_whatsapp_consents_purpose"),
        sa.CheckConstraint(
            "length(trim(notice_version)) > 0", name="ck_whatsapp_consents_notice_version"
        ),
        sa.CheckConstraint(
            "withdrawn_at IS NULL OR withdrawn_at >= granted_at",
            name="ck_whatsapp_consents_timeline",
        ),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["phone_version_id"], ["driver_phone_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["withdrawn_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("driver_profile_id", "version", name="uq_whatsapp_consent_version"),
    )
    op.create_index(
        "ix_whatsapp_consents_profile", "whatsapp_consents", ["driver_profile_id", "version"]
    )
    op.create_table(
        "manual_driver_contact_tasks",
        _uuid("id"),
        _uuid("driver_profile_id"),
        _uuid("phone_version_id"),
        _uuid("consent_id"),
        sa.Column("event_key", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _uuid("completed_by_user_id", nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completion_outcome", sa.String(16)),
        sa.Column("completion_note", sa.Text()),
        sa.CheckConstraint("length(trim(event_key)) > 0", name="ck_manual_contact_event_key"),
        sa.CheckConstraint("length(trim(purpose)) > 0", name="ck_manual_contact_purpose"),
        sa.CheckConstraint("status IN ('open', 'completed')", name="ck_manual_contact_status"),
        sa.CheckConstraint(
            "(status = 'open' AND completed_by_user_id IS NULL AND completed_at IS NULL "
            "AND completion_outcome IS NULL AND completion_note IS NULL) OR "
            "(status = 'completed' AND completed_by_user_id IS NOT NULL "
            "AND completed_at IS NOT NULL AND completion_outcome IN "
            "('attempted', 'reached', 'failed') AND length(trim(completion_note)) > 0)",
            name="ck_manual_contact_completion",
        ),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["phone_version_id"], ["driver_phone_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["consent_id"], ["whatsapp_consents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("driver_profile_id", "event_key", name="uq_manual_contact_event"),
    )
    op.create_index(
        "ix_manual_contact_tasks_status", "manual_driver_contact_tasks", ["status", "created_at"]
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM budget_campaign_transitions) OR "
                "EXISTS (SELECT 1 FROM password_reset_attempts) OR "
                "EXISTS (SELECT 1 FROM driver_phone_versions) OR "
                "EXISTS (SELECT 1 FROM manual_driver_contact_tasks) OR "
                "EXISTS (SELECT 1 FROM budget_policy_evaluations "
                "WHERE state <> 'blocked_external_policy')"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0064 downgrade blocked: budget/contact/recovery evidence exists")
    for table in (
        "manual_driver_contact_tasks",
        "whatsapp_consents",
        "phone_verification_challenges",
        "driver_phone_versions",
        "password_reset_tokens",
        "password_reset_attempts",
    ):
        op.drop_table(table)
    op.execute(
        "DROP TRIGGER budget_campaign_transitions_append_only ON budget_campaign_transitions"
    )
    op.drop_table("budget_campaign_transitions")
    op.drop_constraint(
        "ck_budget_policy_evaluations_authority_fields", "budget_policy_evaluations", type_="check"
    )
    op.drop_constraint(
        "ck_budget_policy_evaluations_external_gate", "budget_policy_evaluations", type_="check"
    )
    op.drop_constraint(
        "ck_budget_policy_evaluations_state", "budget_policy_evaluations", type_="check"
    )
    op.drop_column("budget_policy_evaluations", "resume_allowed")
    op.drop_column("budget_policy_evaluations", "alert_applied")
    op.drop_column("budget_policy_evaluations", "resume_threshold_amount")
    op.drop_column("budget_policy_evaluations", "budget_basis")
    op.drop_column("budget_policy_evaluations", "billing_fact_source")
    op.drop_column("budget_policy_evaluations", "policy_source")
    op.drop_column("budget_policy_evaluations", "policy_id")
    op.alter_column(
        "budget_policy_evaluations", "policy_revision", new_column_name="policy_version"
    )
    op.alter_column("budget_policy_evaluations", "external_gate", nullable=False)
    op.create_check_constraint(
        "ck_budget_policy_evaluations_state",
        "budget_policy_evaluations",
        "state = 'blocked_external_policy'",
    )
    op.create_check_constraint(
        "ck_budget_policy_evaluations_external_gate",
        "budget_policy_evaluations",
        "external_gate = 'EXT-BUDGET-POLICY'",
    )
    op.create_check_constraint(
        "ck_budget_policy_evaluations_blocked_fields",
        "budget_policy_evaluations",
        "policy_version IS NULL AND billing_spend_amount IS NULL "
        "AND alert_threshold_amount IS NULL AND pause_threshold_amount IS NULL "
        "AND pause_applied = false",
    )

"""Persist enquiries and automatic report obligations; enable D92 headroom.

Revision ID: 0108_req180_backend_batch2
Revises: 0107_audience_sweep_cursor
"""

from uuid import UUID

import sqlalchemy as sa

from alembic import op

revision = "0108_req180_backend_batch2"
down_revision = "0107_audience_sweep_cursor"
branch_labels = None
depends_on = None

# D104 retired the external policy gate, so every evaluation carries full authority.
STATE = "state IN ('within_budget', 'alert_threshold', 'urgent_threshold', 'pause_threshold')"
URGENT = (
    "(state <> 'urgent_threshold' AND urgent_threshold_amount IS NULL) OR "
    "(urgent_threshold_amount IS NOT NULL "
    "AND urgent_threshold_amount > alert_threshold_amount "
    "AND urgent_threshold_amount < pause_threshold_amount)"
)
AUTHORITY = (
    "policy_id IS NOT NULL AND policy_revision IS NOT NULL "
    "AND policy_source IN ('external_approved', 'synthetic_test') "
    "AND budget_basis = 'total' "
    "AND billing_fact_source IN ('confirmed_funding', 'production_obligation') "
    "AND billing_spend_amount >= 0 AND alert_threshold_amount >= 0 "
    "AND pause_threshold_amount > alert_threshold_amount "
    "AND resume_threshold_amount <= pause_threshold_amount"
)
OLD_STATE = (
    "state IN ('blocked_external_policy', 'within_budget', "
    "'alert_threshold', 'urgent_threshold', 'pause_threshold')"
)
OLD_URGENT = (
    "(state = 'blocked_external_policy' AND urgent_threshold_amount IS NULL) OR "
    "(state NOT IN ('blocked_external_policy', 'urgent_threshold') "
    "AND urgent_threshold_amount IS NULL) OR "
    "(state <> 'blocked_external_policy' AND urgent_threshold_amount IS NOT NULL "
    "AND urgent_threshold_amount > alert_threshold_amount "
    "AND urgent_threshold_amount < pause_threshold_amount)"
)
OLD_GATE = (
    "(state = 'blocked_external_policy' AND external_gate = 'EXT-BUDGET-POLICY') OR "
    "(state <> 'blocked_external_policy' AND external_gate IS NULL)"
)
OLD_AUTHORITY = (
    "(state = 'blocked_external_policy' AND policy_id IS NULL "
    "AND policy_revision IS NULL AND policy_source IS NULL AND budget_basis IS NULL "
    "AND billing_fact_source IS NULL AND billing_spend_amount IS NULL "
    "AND alert_threshold_amount IS NULL AND pause_threshold_amount IS NULL "
    "AND resume_threshold_amount IS NULL AND alert_applied = false "
    "AND pause_applied = false AND resume_allowed = false) OR "
    "(state <> 'blocked_external_policy' AND policy_id IS NOT NULL AND policy_revision IS NOT NULL "
    "AND policy_source IN ('external_approved', 'synthetic_test') "
    "AND budget_basis IN ('total', 'daily') "
    "AND billing_fact_source IN ('confirmed_funding', 'production_obligation') "
    "AND billing_spend_amount >= 0 AND alert_threshold_amount >= 0 "
    "AND pause_threshold_amount > alert_threshold_amount "
    "AND resume_threshold_amount <= alert_threshold_amount)"
)
BUDGET_CHECKS = {
    "ck_budget_policy_evaluations_state": (STATE, OLD_STATE),
    "ck_budget_policy_evaluations_urgent": (URGENT, OLD_URGENT),
    "ck_budget_policy_evaluations_authority_fields": (AUTHORITY, OLD_AUTHORITY),
}


def upgrade():
    op.add_column("budget_policy_evaluations", sa.Column("funding_fingerprint", sa.String(64)))
    for field in ("alert", "urgent", "pause", "resume"):
        op.alter_column(
            "budget_policy_evaluations", field + "_threshold_amount", type_=sa.Numeric(16, 4)
        )
    op.create_table(
        "campaign_enquiries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company", sa.String(160), nullable=False),
        sa.Column("contact_name", sa.String(160), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("brief", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("advertiser_organizations.id")),
        sa.Column("converted_at", sa.DateTime(timezone=True)),
        sa.Column("converted_by_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("converted_owner_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.CheckConstraint(
            "(organization_id IS NULL AND converted_at IS NULL "
            "AND converted_by_user_id IS NULL) OR "
            "(organization_id IS NOT NULL AND converted_at IS NOT NULL "
            "AND converted_by_user_id IS NOT NULL)",
            name="ck_campaign_enquiries_conversion",
        ),
    )
    op.create_index("ix_campaign_enquiries_created", "campaign_enquiries", ["created_at", "id"])
    op.create_table(
        "report_schedules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("campaign_id", sa.Uuid(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("period_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("measurement_request_id", sa.Uuid(), nullable=False),
        sa.Column("issuance_request_id", sa.Uuid(), nullable=False),
        sa.Column("measurement_run_id", sa.Uuid(), sa.ForeignKey("measurement_runs.id")),
        sa.Column("report_issuance_id", sa.Uuid(), sa.ForeignKey("report_issuances.id")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("error_code", sa.String(128)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "campaign_id", "period_start_at", "period_end_at", name="uq_report_schedule_window"
        ),
        sa.CheckConstraint("period_start_at < period_end_at", name="ck_report_schedule_period"),
        sa.CheckConstraint("kind IN ('weekly','final')", name="ck_report_schedule_kind"),
        sa.CheckConstraint(
            "state IN ('pending','error','complete')", name="ck_report_schedule_state"
        ),
    )
    op.create_table(
        "report_schedule_cursors",
        sa.Column("name", sa.String(32), primary_key=True),
        sa.Column("campaign_id", sa.Uuid()),
    )
    op.bulk_insert(
        sa.table(
            "users",
            sa.column("id", sa.Uuid()),
            sa.column("email"),
            sa.column("full_name"),
            sa.column("password_hash"),
            sa.column("role"),
            sa.column("status"),
        ),
        [
            {
                "id": UUID("c37324b8-dddf-4d83-b923-4975d4569cd9"),
                "email": "report-automation@cardvert.invalid",
                "full_name": "Cardvert report automation",
                "password_hash": "!report-automation-disabled",
                "role": "admin",
                "status": "disabled",
            }
        ],
    )
    # Blocked rows were never acted on and nothing references them; the trigger keeps the
    # rest of the history append-only.
    trigger = "TRIGGER budget_policy_evaluations_append_only"
    op.execute(f"ALTER TABLE budget_policy_evaluations DISABLE {trigger}")
    op.execute("DELETE FROM budget_policy_evaluations WHERE state = 'blocked_external_policy'")
    op.execute(f"ALTER TABLE budget_policy_evaluations ENABLE {trigger}")
    op.drop_constraint(
        "ck_budget_policy_evaluations_external_gate", "budget_policy_evaluations", type_="check"
    )
    op.drop_column("budget_policy_evaluations", "external_gate")
    for name, (check, _) in BUDGET_CHECKS.items():
        op.drop_constraint(name, "budget_policy_evaluations", type_="check")
        op.create_check_constraint(name, "budget_policy_evaluations", check)


def downgrade():
    connection = op.get_bind()
    for table in ("campaign_enquiries", "report_schedules", "report_schedule_cursors"):
        if connection.scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("Cannot downgrade populated REQ-180 records")
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM budget_policy_evaluations "
            "WHERE resume_threshold_amount > alert_threshold_amount)"
        )
    ):
        raise RuntimeError("Cannot downgrade D92 budget authority")
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM budget_policy_evaluations "
            "WHERE alert_threshold_amount <> round(alert_threshold_amount, 2) "
            "OR urgent_threshold_amount <> round(urgent_threshold_amount, 2) "
            "OR pause_threshold_amount <> round(pause_threshold_amount, 2) "
            "OR resume_threshold_amount <> round(resume_threshold_amount, 2))"
        )
    ):
        raise RuntimeError("Cannot round stored percentage thresholds on downgrade")
    for name, (_, check) in BUDGET_CHECKS.items():
        op.drop_constraint(name, "budget_policy_evaluations", type_="check")
        op.create_check_constraint(name, "budget_policy_evaluations", check)
    op.add_column("budget_policy_evaluations", sa.Column("external_gate", sa.String(64)))
    op.create_check_constraint(
        "ck_budget_policy_evaluations_external_gate", "budget_policy_evaluations", OLD_GATE
    )
    connection.execute(sa.text("DELETE FROM users WHERE id='c37324b8-dddf-4d83-b923-4975d4569cd9'"))
    op.drop_column("budget_policy_evaluations", "funding_fingerprint")
    for field in ("alert", "urgent", "pause", "resume"):
        op.alter_column(
            "budget_policy_evaluations", field + "_threshold_amount", type_=sa.Numeric(14, 2)
        )
    op.drop_table("report_schedule_cursors")
    op.drop_table("report_schedules")
    op.drop_table("campaign_enquiries")

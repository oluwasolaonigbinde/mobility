"""Fix the client's daily in-area pay policy and remove unused subsidy authority.

Revision ID: 0111_fix_daily_pay_policy
Revises: 0110_simplify_driver_operations
"""

from sqlalchemy import Numeric

from alembic import op

revision = "0111_fix_daily_pay_policy"
down_revision = "0110_simplify_driver_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A run or batch may sum hundreds of valid Numeric(14, 2) entries.
    for table in ("payout_automatic_runs", "payout_batches"):
        op.alter_column(
            table,
            "total_amount",
            existing_type=Numeric(14, 2),
            type_=Numeric(18, 2),
            existing_nullable=False,
        )
    # Accepted terms remain immutable audit facts, now constrained to D43.
    terms_shape = (
        "formula_version = 'payout_v4'"
        " AND daily_rate_naira IS NOT NULL AND daily_target_miles IS NOT NULL"
        " AND minimum_miles IS NOT NULL AND outside_area_weight IS NOT NULL"
        " AND shortfall_strategy IS NOT NULL"
        " AND daily_rate_naira > 0 AND daily_target_miles > 0"
        " AND minimum_miles = 0 AND outside_area_weight = 0"
        " AND shortfall_strategy = 'proportional' AND deduction_per_mile_naira IS NULL"
    )
    for table, constraint in (
        ("campaign_payout_rule_revisions", "ck_campaign_payout_rule_revisions_terms_shape"),
        ("assignment_rule_bindings", "ck_assignment_rule_bindings_terms_shape"),
    ):
        op.drop_constraint(constraint, table, type_="check")
        op.create_check_constraint(constraint, table, terms_shape)
    for name in (
        "ck_payout_automatic_runs_freq",
        "ck_payout_automatic_runs_limit_positive",
        "ck_payout_automatic_runs_total_within_limit",
    ):
        op.drop_constraint(name, "payout_automatic_runs", type_="check")
    op.drop_column("payout_automatic_runs", "frequency")
    op.drop_column("payout_automatic_runs", "batch_limit")
    op.create_check_constraint(
        "ck_payout_automatic_runs_total_nonnegative", "payout_automatic_runs", "total_amount >= 0"
    )
    op.drop_constraint("ck_payout_automatic_alerts_kind", "payout_automatic_alerts", type_="check")
    op.create_check_constraint(
        "ck_payout_automatic_alerts_kind",
        "payout_automatic_alerts",
        "kind IN ('failed_payment', 'duplicate_payment', 'daily_limit', "
        "'run_failed', 'submission_blocked', 'business_health')",
    )
    for name in (
        "ck_campaign_financial_authorizations_type",
        "ck_campaign_financial_authorizations_evidence",
    ):
        op.drop_constraint(name, "campaign_financial_authorizations", type_="check")
    op.drop_column("campaign_financial_authorizations", "subsidy_reference")
    op.create_check_constraint(
        "ck_campaign_financial_authorizations_type",
        "campaign_financial_authorizations",
        "authority_type IN ('prepaid_cash', 'approved_credit')",
    )
    op.create_check_constraint(
        "ck_campaign_financial_authorizations_evidence",
        "campaign_financial_authorizations",
        "(authority_type = 'prepaid_cash' AND funded_cash_amount = authorized_amount "
        "AND credit_limit IS NULL AND credit_due_at IS NULL AND "
        "credit_approved_by_user_id IS NULL AND credit_terms IS NULL) OR "
        "(authority_type = 'approved_credit' AND funded_cash_amount = 0 "
        "AND credit_limit = authorized_amount AND credit_due_at IS NOT NULL AND "
        "credit_approved_by_user_id IS NOT NULL AND credit_terms IS NOT NULL)",
    )


def downgrade() -> None:
    raise RuntimeError(
        "Recreate the disposable development database to restore removed pay options"
    )

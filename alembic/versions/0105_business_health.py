"""Operational Finance alerts and terminal email failure time (D82)."""

import sqlalchemy as sa

from alembic import op

revision = "0105_business_health"
down_revision = "0104_retire_v1_trip_watermarks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_payout_automatic_alerts_kind", "payout_automatic_alerts", type_="check")
    op.create_check_constraint(
        "ck_payout_automatic_alerts_kind",
        "payout_automatic_alerts",
        "kind IN ('failed_payment', 'duplicate_payment', 'daily_limit', "
        "'batch_limit', 'run_failed', 'submission_blocked', 'business_health')",
    )
    op.add_column("notifications", sa.Column("failed_at", sa.DateTime(timezone=True)))

    op.create_index(
        "ix_health_payout_line_progress", "payout_batch_lines", ["status", "created_at"]
    )
    op.create_index("ix_health_payout_event_received", "payout_provider_events", ["received_at"])
    op.create_index("ix_health_payment_event_received", "payment_gateway_events", ["received_at"])
    op.create_index(
        "ix_health_trip_status_activity", "trip_sessions", ["status", "started_at", "ended_at"]
    )
    op.create_index(
        "ix_health_email_status_age",
        "notifications",
        ["channel", "status", "created_at", "failed_at"],
    )


def downgrade() -> None:
    raise RuntimeError("Recreate the disposable development database")

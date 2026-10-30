"""Allow trips with no location for 2 hours to be sealed as auto_ended (REQ-264)."""

from alembic import op

revision = "0120_req264_auto_end_seal_reason"
down_revision = "0119_advertiser_login_invites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_trip_sessions_seal_reason", "trip_sessions", type_="check")
    op.create_check_constraint(
        "ck_trip_sessions_seal_reason",
        "trip_sessions",
        "seal_reason IS NULL OR seal_reason IN "
        "('client_complete', 'late_data_complete', 'auto_ended')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_trip_sessions_seal_reason", "trip_sessions", type_="check")
    op.create_check_constraint(
        "ck_trip_sessions_seal_reason",
        "trip_sessions",
        "seal_reason IS NULL OR seal_reason IN ('client_complete', 'late_data_complete')",
    )

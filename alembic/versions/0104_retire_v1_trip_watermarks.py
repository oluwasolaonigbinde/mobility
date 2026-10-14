"""Remove the remaining protocol-v1 watermark format (D80/REQ-161)."""

from alembic import op

revision = "0104_retire_v1_trip_watermarks"
down_revision = "0103_retire_legacy_engines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("client_batch_count", "client_ping_count", "client_complete"):
        op.drop_column("trip_sessions", column)
    op.drop_constraint("ck_trip_sessions_seal_reason", "trip_sessions", type_="check")
    op.create_check_constraint(
        "ck_trip_sessions_seal_reason",
        "trip_sessions",
        "seal_reason IS NULL OR seal_reason IN ('client_complete', 'late_data_complete')",
    )


def downgrade() -> None:
    raise RuntimeError("Recreate the disposable development database; protocol v1 is retired")

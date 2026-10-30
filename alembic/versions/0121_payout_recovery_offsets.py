"""Final audited recovery offsets (REQ-260/262)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0121_payout_recovery_offsets"
down_revision = "0120_req264_auto_end_seal_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payout_recovery_offsets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source_trip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trip_sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "funding_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "driver_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("driver_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "automatic_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payout_automatic_runs.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("amount > 0", name="ck_payout_recovery_offsets_amount"),
        sa.CheckConstraint("length(currency) = 3", name="ck_payout_recovery_offsets_currency"),
        sa.CheckConstraint(
            "(actor_user_id IS NULL) <> (automatic_run_id IS NULL)",
            name="ck_payout_recovery_offsets_actor",
        ),
        sa.UniqueConstraint(
            "request_id",
            "funding_entry_id",
            "source_trip_id",
            name="uq_payout_recovery_offsets_request_source",
        ),
    )
    for label, columns in (
        ("driver", ["driver_profile_id", "currency"]),
        ("source", ["source_trip_id"]),
        ("funding", ["funding_entry_id"]),
    ):
        op.create_index(f"ix_payout_recovery_offsets_{label}", "payout_recovery_offsets", columns)
    op.execute("""CREATE FUNCTION reject_payout_recovery_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'Payout recovery offsets are immutable';
        END; $$""")
    op.execute("""CREATE TRIGGER payout_recovery_offsets_immutable BEFORE UPDATE OR DELETE
        ON payout_recovery_offsets FOR EACH ROW
        EXECUTE FUNCTION reject_payout_recovery_mutation()""")


def downgrade() -> None:
    op.drop_table("payout_recovery_offsets")
    op.execute("DROP FUNCTION reject_payout_recovery_mutation()")

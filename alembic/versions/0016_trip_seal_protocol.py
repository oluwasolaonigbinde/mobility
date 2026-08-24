"""Trip finality protocol: seal lifecycle + post-seal quarantine (RM3/RM4/RM5)

trip_sessions gains the ``sealed`` status (the sole money-chain trigger), the
client finalization watermark columns, and seal evidence columns. Existing
``ended`` rows are backfilled to ``sealed`` — they were already processed under
the pre-seal regime and must not strand outside the new sweep predicate.

Also creates ``quarantined_ping_batches`` (post-seal batches are preserved as
evidence, never flat-400 rejected) and extends the data_purge_audit event set
so quarantine payloads (raw location data) share the NDPR retention trail.

Revision ID: 0016_trip_seal_protocol
Revises: 0015_payout_day_allocation
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_trip_seal_protocol"
down_revision: str | Sequence[str] | None = "0015_payout_day_allocation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Widen the status CHECK before any backfill writes 'sealed'.
    op.drop_constraint("ck_trip_sessions_status", "trip_sessions", type_="check")
    op.create_check_constraint(
        "ck_trip_sessions_status",
        "trip_sessions",
        "status IN ('active', 'ended', 'sealed')",
    )

    op.add_column("trip_sessions", sa.Column("client_batch_count", sa.Integer(), nullable=True))
    op.add_column("trip_sessions", sa.Column("client_ping_count", sa.Integer(), nullable=True))
    op.add_column("trip_sessions", sa.Column("client_complete", sa.Boolean(), nullable=True))
    op.add_column(
        "trip_sessions",
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("trip_sessions", sa.Column("seal_reason", sa.Text(), nullable=True))

    # 2. Backfill: every pre-protocol ended trip was already eligible for (and
    # usually processed by) the money chain, so it seals as-of its end time.
    # COALESCE guards the (never-observed) ended-with-null-ended_at row.
    op.execute(
        """
        UPDATE trip_sessions
        SET status = 'sealed',
            sealed_at = COALESCE(ended_at, updated_at),
            seal_reason = 'migration_backfill'
        WHERE status = 'ended'
        """
    )

    # 3. Seal-field invariants, added after the backfill satisfies them.
    op.create_check_constraint(
        "ck_trip_sessions_sealed_fields",
        "trip_sessions",
        "(status = 'sealed') = (sealed_at IS NOT NULL AND seal_reason IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_trip_sessions_seal_reason",
        "trip_sessions",
        "seal_reason IS NULL OR seal_reason IN "
        "('client_complete', 'late_data_complete', 'grace_expired', 'migration_backfill')",
    )

    op.create_table(
        "quarantined_ping_batches",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "trip_session_id",
            sa.Uuid(),
            sa.ForeignKey("trip_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("ping_count", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'quarantined'"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "applied_batch_id",
            sa.Uuid(),
            sa.ForeignKey("location_ping_batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('quarantined', 'applied', 'discarded')",
            name="ck_quarantined_ping_batches_status",
        ),
        sa.CheckConstraint(
            "(status = 'quarantined') = (resolved_at IS NULL)",
            name="ck_quarantined_ping_batches_resolution",
        ),
        sa.UniqueConstraint(
            "trip_session_id",
            "idempotency_key",
            name="uq_quarantined_ping_batches_trip_idempotency_key",
        ),
    )
    op.create_index(
        "ix_quarantined_ping_batches_trip_session_id",
        "quarantined_ping_batches",
        ["trip_session_id"],
    )
    op.create_index(
        "ix_quarantined_ping_batches_status",
        "quarantined_ping_batches",
        ["status"],
    )

    # 4. Quarantine payloads are raw location data: register their purge event
    # kinds in the compliance trail (partition_name stays NULL for them).
    op.drop_constraint("ck_data_purge_audit_event", "data_purge_audit", type_="check")
    op.create_check_constraint(
        "ck_data_purge_audit_event",
        "data_purge_audit",
        "event IN ('purge_started', 'detach_finalized', 'dropped', 'batches_purged', "
        "'quarantined_batches_purged')",
    )
    op.drop_constraint(
        "ck_data_purge_audit_partition_name_required", "data_purge_audit", type_="check"
    )
    op.create_check_constraint(
        "ck_data_purge_audit_partition_name_required",
        "data_purge_audit",
        "partition_name IS NOT NULL OR event IN ('batches_purged', 'quarantined_batches_purged')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_data_purge_audit_partition_name_required", "data_purge_audit", type_="check"
    )
    op.create_check_constraint(
        "ck_data_purge_audit_partition_name_required",
        "data_purge_audit",
        "partition_name IS NOT NULL OR event = 'batches_purged'",
    )
    op.drop_constraint("ck_data_purge_audit_event", "data_purge_audit", type_="check")
    op.create_check_constraint(
        "ck_data_purge_audit_event",
        "data_purge_audit",
        "event IN ('purge_started', 'detach_finalized', 'dropped', 'batches_purged')",
    )
    op.drop_index("ix_quarantined_ping_batches_status", table_name="quarantined_ping_batches")
    op.drop_index(
        "ix_quarantined_ping_batches_trip_session_id",
        table_name="quarantined_ping_batches",
    )
    op.drop_table("quarantined_ping_batches")
    op.drop_constraint("ck_trip_sessions_seal_reason", "trip_sessions", type_="check")
    op.drop_constraint("ck_trip_sessions_sealed_fields", "trip_sessions", type_="check")
    op.execute("UPDATE trip_sessions SET status = 'ended' WHERE status = 'sealed'")
    op.drop_column("trip_sessions", "seal_reason")
    op.drop_column("trip_sessions", "sealed_at")
    op.drop_column("trip_sessions", "client_complete")
    op.drop_column("trip_sessions", "client_ping_count")
    op.drop_column("trip_sessions", "client_batch_count")
    op.drop_constraint("ck_trip_sessions_status", "trip_sessions", type_="check")
    op.create_check_constraint(
        "ck_trip_sessions_status",
        "trip_sessions",
        "status IN ('active', 'ended')",
    )

"""Add exact signed v2 trip evidence manifests and receipts.

Revision ID: 0074_trip_evidence_manifest
Revises: 0073_refund_cancellation_provenance
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0074_trip_evidence_manifest"
down_revision: str | Sequence[str] | None = "0073_refund_cancellation_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_trip_columns() -> None:
    op.add_column("trip_sessions", sa.Column("evidence_protocol_version", sa.Integer()))
    op.execute("UPDATE trip_sessions SET evidence_protocol_version = 1")
    op.alter_column(
        "trip_sessions",
        "evidence_protocol_version",
        nullable=False,
        server_default=sa.text("2"),
    )
    for column in (
        sa.Column("evidence_manifest_version", sa.Integer()),
        sa.Column("evidence_manifest_root_sha256", sa.String(length=64)),
        sa.Column("evidence_manifest_batch_count", sa.Integer()),
        sa.Column("evidence_manifest_ping_count", sa.Integer()),
        sa.Column("evidence_manifest_committed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "evidence_manifest_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("evidence_manifest_verified_at", sa.DateTime(timezone=True)),
        sa.Column("evidence_manifest_receipt_format_version", sa.Integer()),
        sa.Column("evidence_manifest_receipt_key_version", sa.Integer()),
        sa.Column("evidence_manifest_receipt_signature", sa.Text()),
        sa.Column("grace_expired_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("trip_sessions", column)
    op.create_check_constraint(
        "ck_trip_sessions_evidence_protocol_version",
        "trip_sessions",
        "evidence_protocol_version IN (1, 2)",
    )
    op.create_check_constraint(
        "ck_trip_sessions_manifest_batch_count_non_negative",
        "trip_sessions",
        "evidence_manifest_batch_count IS NULL OR evidence_manifest_batch_count >= 0",
    )
    op.create_check_constraint(
        "ck_trip_sessions_manifest_ping_count_non_negative",
        "trip_sessions",
        "evidence_manifest_ping_count IS NULL OR evidence_manifest_ping_count >= 0",
    )
    op.create_check_constraint(
        "ck_trip_sessions_manifest_header_cluster",
        "trip_sessions",
        "(evidence_manifest_version IS NULL AND evidence_manifest_root_sha256 IS NULL "
        "AND evidence_manifest_batch_count IS NULL AND evidence_manifest_ping_count IS NULL "
        "AND evidence_manifest_committed_at IS NULL) OR "
        "(evidence_manifest_version = 2 AND evidence_manifest_root_sha256 IS NOT NULL "
        "AND evidence_manifest_batch_count IS NOT NULL "
        "AND evidence_manifest_ping_count IS NOT NULL "
        "AND evidence_manifest_committed_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_trip_sessions_manifest_receipt_cluster",
        "trip_sessions",
        "(evidence_manifest_verified_at IS NULL "
        "AND evidence_manifest_receipt_format_version IS NULL "
        "AND evidence_manifest_receipt_key_version IS NULL "
        "AND evidence_manifest_receipt_signature IS NULL) OR "
        "(evidence_manifest_complete AND evidence_manifest_verified_at IS NOT NULL "
        "AND evidence_manifest_receipt_format_version = 2 "
        "AND evidence_manifest_receipt_key_version IS NOT NULL "
        "AND evidence_manifest_receipt_signature IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_trip_sessions_v2_sealed_manifest_verified",
        "trip_sessions",
        "evidence_protocol_version = 1 OR status != 'sealed' "
        "OR evidence_manifest_verified_at IS NOT NULL",
    )


def _add_batch_columns(table: str, *, live: bool) -> None:
    op.add_column(table, sa.Column("batch_sequence", sa.Integer()))
    op.add_column(
        table,
        sa.Column(
            "payload_hash_version", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
    )
    op.add_column(table, sa.Column("pings_submitted", sa.Integer()))
    source = "pings_accepted" if live else "ping_count"
    op.execute(f"UPDATE {table} SET pings_submitted = {source}")
    op.alter_column(table, "pings_submitted", nullable=False)
    op.add_column(
        table,
        sa.Column("pings_rejected", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    if live:
        op.add_column(
            table,
            sa.Column(
                "evidence_scope",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'legacy'"),
            ),
        )
    op.add_column(table, sa.Column("receipt_format_version", sa.Integer()))
    op.add_column(table, sa.Column("receipt_key_version", sa.Integer()))
    op.add_column(table, sa.Column("receipt_signature", sa.Text()))
    op.add_column(table, sa.Column("receipt_outcome", sa.String(length=32)))


def _create_manifest_entries() -> None:
    op.create_table(
        "trip_evidence_manifest_entries",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "trip_session_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("trip_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("batch_sequence", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("payload_hash_version", sa.Integer(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("submitted_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("batch_sequence >= 0", name="ck_trip_manifest_entries_sequence"),
        sa.CheckConstraint(
            "payload_hash_version = 2", name="ck_trip_manifest_entries_hash_version"
        ),
        sa.CheckConstraint(
            "submitted_count >= 0", name="ck_trip_manifest_entries_submitted_count"
        ),
        sa.UniqueConstraint(
            "trip_session_id",
            "batch_sequence",
            name="uq_trip_manifest_entries_trip_sequence",
        ),
        sa.UniqueConstraint(
            "trip_session_id",
            "idempotency_key",
            name="uq_trip_manifest_entries_trip_idempotency_key",
        ),
    )
    op.create_index(
        "ix_trip_manifest_entries_trip_session_id",
        "trip_evidence_manifest_entries",
        ["trip_session_id"],
    )


def _create_postgres_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION guard_trip_evidence_manifest() RETURNS trigger AS $$
        BEGIN
          IF OLD.evidence_manifest_root_sha256 IS NOT NULL AND (
            NEW.evidence_manifest_version IS DISTINCT FROM OLD.evidence_manifest_version OR
            NEW.evidence_manifest_root_sha256 IS DISTINCT FROM OLD.evidence_manifest_root_sha256 OR
            NEW.evidence_manifest_batch_count IS DISTINCT FROM OLD.evidence_manifest_batch_count OR
            NEW.evidence_manifest_ping_count IS DISTINCT FROM OLD.evidence_manifest_ping_count OR
            NEW.evidence_manifest_committed_at IS DISTINCT FROM OLD.evidence_manifest_committed_at
          ) THEN RAISE EXCEPTION 'trip evidence manifest header is immutable'; END IF;
          IF OLD.evidence_manifest_complete AND NOT NEW.evidence_manifest_complete
          THEN RAISE EXCEPTION 'trip evidence completeness is one-way'; END IF;
          IF OLD.evidence_manifest_verified_at IS NOT NULL AND (
            NEW.evidence_manifest_verified_at IS DISTINCT FROM OLD.evidence_manifest_verified_at OR
            NEW.evidence_manifest_receipt_format_version IS DISTINCT FROM
              OLD.evidence_manifest_receipt_format_version OR
            NEW.evidence_manifest_receipt_key_version IS DISTINCT FROM
              OLD.evidence_manifest_receipt_key_version OR
            NEW.evidence_manifest_receipt_signature IS DISTINCT FROM
              OLD.evidence_manifest_receipt_signature
          ) THEN RAISE EXCEPTION 'trip evidence verification receipt is immutable'; END IF;
          IF OLD.grace_expired_at IS NOT NULL AND
             NEW.grace_expired_at IS DISTINCT FROM OLD.grace_expired_at
          THEN RAISE EXCEPTION 'trip evidence grace marker is immutable'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trip_evidence_manifest_guard
        BEFORE UPDATE ON trip_sessions FOR EACH ROW
        EXECUTE FUNCTION guard_trip_evidence_manifest()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_trip_manifest_entry_mutation() RETURNS trigger AS $$
        DECLARE
          committed_at_value timestamptz;
        BEGIN
          IF TG_OP = 'INSERT' THEN
            SELECT evidence_manifest_committed_at INTO committed_at_value
            FROM trip_sessions
            WHERE id = NEW.trip_session_id
            FOR UPDATE;
            IF committed_at_value IS NOT NULL
            THEN RAISE EXCEPTION 'trip evidence manifest entries are immutable'; END IF;
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'trip evidence manifest entries are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trip_evidence_manifest_entries_immutable
        BEFORE INSERT OR UPDATE OR DELETE ON trip_evidence_manifest_entries FOR EACH ROW
        EXECUTE FUNCTION reject_trip_manifest_entry_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION guard_trip_batch_receipt() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            IF OLD.receipt_signature IS NOT NULL AND (
              EXISTS (SELECT 1 FROM location_pings WHERE batch_id = OLD.id) OR
              NOT EXISTS (
                SELECT 1 FROM data_purge_audit
                WHERE event = 'dropped'
                  AND range_from IS NOT NULL
                  AND range_to IS NOT NULL
                  AND OLD.received_at >= range_from
                  AND OLD.received_at < range_to
              )
            )
            THEN RAISE EXCEPTION 'trip batch receipt is immutable'; END IF;
            RETURN OLD;
          END IF;
          IF OLD.receipt_signature IS NOT NULL AND (
            NEW.trip_session_id IS DISTINCT FROM OLD.trip_session_id OR
            NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key OR
            NEW.batch_sequence IS DISTINCT FROM OLD.batch_sequence OR
            NEW.payload_hash_version IS DISTINCT FROM OLD.payload_hash_version OR
            NEW.payload_hash IS DISTINCT FROM OLD.payload_hash OR
            NEW.pings_submitted IS DISTINCT FROM OLD.pings_submitted OR
            NEW.pings_accepted IS DISTINCT FROM OLD.pings_accepted OR
            NEW.pings_rejected IS DISTINCT FROM OLD.pings_rejected OR
            NEW.evidence_scope IS DISTINCT FROM OLD.evidence_scope OR
            NEW.receipt_format_version IS DISTINCT FROM OLD.receipt_format_version OR
            NEW.receipt_key_version IS DISTINCT FROM OLD.receipt_key_version OR
            NEW.receipt_signature IS DISTINCT FROM OLD.receipt_signature OR
            NEW.receipt_outcome IS DISTINCT FROM OLD.receipt_outcome OR
            NEW.received_at IS DISTINCT FROM OLD.received_at OR
            NEW.metadata IS DISTINCT FROM OLD.metadata
          ) THEN RAISE EXCEPTION 'trip batch receipt is immutable'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trip_batch_receipt_guard
        BEFORE UPDATE OR DELETE ON location_ping_batches FOR EACH ROW
        EXECUTE FUNCTION guard_trip_batch_receipt()
        """
    )
    op.execute(
        """
        CREATE FUNCTION guard_signed_location_ping() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            IF EXISTS (
              SELECT 1 FROM location_ping_batches
              WHERE id = NEW.batch_id AND receipt_signature IS NOT NULL
            ) THEN RAISE EXCEPTION 'signed trip ping evidence is immutable'; END IF;
            RETURN NEW;
          ELSIF TG_OP = 'DELETE' THEN
            IF EXISTS (
              SELECT 1 FROM location_ping_batches
              WHERE id = OLD.batch_id AND receipt_signature IS NOT NULL
            ) THEN RAISE EXCEPTION 'signed trip ping evidence is immutable'; END IF;
            RETURN OLD;
          END IF;
          IF EXISTS (
            SELECT 1 FROM location_ping_batches
            WHERE id IN (OLD.batch_id, NEW.batch_id) AND receipt_signature IS NOT NULL
          ) THEN RAISE EXCEPTION 'signed trip ping evidence is immutable'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER signed_location_ping_guard
        BEFORE INSERT OR UPDATE OR DELETE ON location_pings FOR EACH ROW
        EXECUTE FUNCTION guard_signed_location_ping()
        """
    )
    op.execute(
        """
        CREATE FUNCTION guard_quarantined_trip_batch_receipt() RETURNS trigger AS $$
        BEGIN
          IF OLD.receipt_signature IS NOT NULL AND (
            NEW.trip_session_id IS DISTINCT FROM OLD.trip_session_id OR
            NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key OR
            NEW.batch_sequence IS DISTINCT FROM OLD.batch_sequence OR
            NEW.payload_hash_version IS DISTINCT FROM OLD.payload_hash_version OR
            NEW.payload_hash IS DISTINCT FROM OLD.payload_hash OR
            NEW.pings_submitted IS DISTINCT FROM OLD.pings_submitted OR
            NEW.pings_rejected IS DISTINCT FROM OLD.pings_rejected OR
            NEW.receipt_format_version IS DISTINCT FROM OLD.receipt_format_version OR
            NEW.receipt_key_version IS DISTINCT FROM OLD.receipt_key_version OR
            NEW.receipt_signature IS DISTINCT FROM OLD.receipt_signature OR
            NEW.receipt_outcome IS DISTINCT FROM OLD.receipt_outcome OR
            NEW.payload::jsonb IS DISTINCT FROM OLD.payload::jsonb OR
            NEW.ping_count IS DISTINCT FROM OLD.ping_count OR
            NEW.received_at IS DISTINCT FROM OLD.received_at
          ) THEN RAISE EXCEPTION 'quarantined trip batch receipt is immutable'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER quarantined_trip_batch_receipt_guard
        BEFORE UPDATE ON quarantined_ping_batches FOR EACH ROW
        EXECUTE FUNCTION guard_quarantined_trip_batch_receipt()
        """
    )


def upgrade() -> None:
    _add_trip_columns()
    _add_batch_columns("location_ping_batches", live=True)
    _add_batch_columns("quarantined_ping_batches", live=False)
    op.create_check_constraint(
        "ck_location_ping_batches_ping_conservation",
        "location_ping_batches",
        "pings_submitted >= 0 AND pings_rejected >= 0 "
        "AND pings_submitted = pings_accepted + pings_rejected",
    )
    op.create_check_constraint(
        "ck_location_ping_batches_evidence_scope",
        "location_ping_batches",
        "evidence_scope IN ('legacy', 'manifest', 'postseal_applied')",
    )
    op.create_check_constraint(
        "ck_location_ping_batches_receipt_cluster",
        "location_ping_batches",
        "(receipt_format_version IS NULL AND receipt_key_version IS NULL "
        "AND receipt_signature IS NULL AND receipt_outcome IS NULL) OR "
        "(receipt_format_version = 2 AND receipt_key_version IS NOT NULL "
        "AND receipt_signature IS NOT NULL AND receipt_outcome IS NOT NULL)",
    )
    op.create_index(
        "uq_location_ping_batches_trip_sequence_manifest",
        "location_ping_batches",
        ["trip_session_id", "batch_sequence"],
        unique=True,
        postgresql_where=sa.text("evidence_scope = 'manifest'"),
        sqlite_where=sa.text("evidence_scope = 'manifest'"),
    )
    op.create_check_constraint(
        "ck_quarantined_ping_batches_ping_counts",
        "quarantined_ping_batches",
        "pings_submitted >= 0 AND pings_rejected >= 0",
    )
    op.create_check_constraint(
        "ck_quarantined_ping_batches_receipt_cluster",
        "quarantined_ping_batches",
        "(receipt_format_version IS NULL AND receipt_key_version IS NULL "
        "AND receipt_signature IS NULL AND receipt_outcome IS NULL) OR "
        "(receipt_format_version = 2 AND receipt_key_version IS NOT NULL "
        "AND receipt_signature IS NOT NULL AND receipt_outcome IS NOT NULL)",
    )
    _create_manifest_entries()
    if op.get_bind().dialect.name == "postgresql":
        _create_postgres_guards()


def downgrade() -> None:
    bind = op.get_bind()
    unsafe = bind.execute(
        sa.text(
            """
            SELECT EXISTS (
              SELECT 1 FROM trip_sessions
              WHERE evidence_protocol_version = 2
                 OR evidence_manifest_root_sha256 IS NOT NULL
                 OR grace_expired_at IS NOT NULL
              UNION ALL
              SELECT 1 FROM location_ping_batches WHERE receipt_signature IS NOT NULL
              UNION ALL
              SELECT 1 FROM quarantined_ping_batches WHERE receipt_signature IS NOT NULL
            )
            """
        )
    ).scalar()
    if unsafe:
        raise RuntimeError("0074 downgrade blocked: v2 trip evidence exists")

    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER quarantined_trip_batch_receipt_guard ON quarantined_ping_batches")
        op.execute("DROP FUNCTION guard_quarantined_trip_batch_receipt()")
        op.execute("DROP TRIGGER signed_location_ping_guard ON location_pings")
        op.execute("DROP FUNCTION guard_signed_location_ping()")
        op.execute("DROP TRIGGER trip_batch_receipt_guard ON location_ping_batches")
        op.execute("DROP FUNCTION guard_trip_batch_receipt()")
        op.execute(
            "DROP TRIGGER trip_evidence_manifest_entries_immutable "
            "ON trip_evidence_manifest_entries"
        )
        op.execute("DROP FUNCTION reject_trip_manifest_entry_mutation()")
        op.execute("DROP TRIGGER trip_evidence_manifest_guard ON trip_sessions")
        op.execute("DROP FUNCTION guard_trip_evidence_manifest()")

    op.drop_table("trip_evidence_manifest_entries")
    op.drop_index(
        "uq_location_ping_batches_trip_sequence_manifest", table_name="location_ping_batches"
    )
    op.drop_constraint(
        "ck_quarantined_ping_batches_receipt_cluster",
        "quarantined_ping_batches",
        type_="check",
    )
    op.drop_constraint(
        "ck_quarantined_ping_batches_ping_counts", "quarantined_ping_batches", type_="check"
    )
    op.drop_constraint(
        "ck_location_ping_batches_receipt_cluster",
        "location_ping_batches",
        type_="check",
    )
    op.drop_constraint(
        "ck_location_ping_batches_evidence_scope", "location_ping_batches", type_="check"
    )
    op.drop_constraint(
        "ck_location_ping_batches_ping_conservation", "location_ping_batches", type_="check"
    )
    for table, columns in (
        (
            "quarantined_ping_batches",
            (
                "receipt_outcome",
                "receipt_signature",
                "receipt_key_version",
                "receipt_format_version",
                "pings_rejected",
                "pings_submitted",
                "payload_hash_version",
                "batch_sequence",
            ),
        ),
        (
            "location_ping_batches",
            (
                "receipt_outcome",
                "receipt_signature",
                "receipt_key_version",
                "receipt_format_version",
                "evidence_scope",
                "pings_rejected",
                "pings_submitted",
                "payload_hash_version",
                "batch_sequence",
            ),
        ),
    ):
        for column in columns:
            op.drop_column(table, column)
    for constraint in (
        "ck_trip_sessions_v2_sealed_manifest_verified",
        "ck_trip_sessions_manifest_receipt_cluster",
        "ck_trip_sessions_manifest_header_cluster",
        "ck_trip_sessions_manifest_ping_count_non_negative",
        "ck_trip_sessions_manifest_batch_count_non_negative",
        "ck_trip_sessions_evidence_protocol_version",
    ):
        op.drop_constraint(constraint, "trip_sessions", type_="check")
    for column in (
        "grace_expired_at",
        "evidence_manifest_receipt_signature",
        "evidence_manifest_receipt_key_version",
        "evidence_manifest_receipt_format_version",
        "evidence_manifest_verified_at",
        "evidence_manifest_complete",
        "evidence_manifest_committed_at",
        "evidence_manifest_ping_count",
        "evidence_manifest_batch_count",
        "evidence_manifest_root_sha256",
        "evidence_manifest_version",
        "evidence_protocol_version",
    ):
        op.drop_column("trip_sessions", column)

"""Durable per-sample ping dispositions and final evidence adjudication."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0080_trip_evidence_partial_disposition"
down_revision: str | Sequence[str] | None = "0079_traffic_density_profile_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DISPOSITION_TRIGGER = "trg_location_ping_batch_disposition_immutable"
DISPOSITION_FUNCTION = "reject_location_ping_batch_disposition_mutation"
ADJUDICATION_TRIGGER = "trg_trip_evidence_adjudication_immutable"
ADJUDICATION_FUNCTION = "reject_trip_evidence_adjudication_mutation"


def upgrade() -> None:
    # --- OFF-005: immutable per-sample batch disposition ---------------------
    #
    # Rows written before this revision keep NULL. They are deliberately not
    # backfilled: their receipts were signed over a value that omits the
    # disposition key, so inventing one would either invalidate sealed
    # evidence or force a re-signature of history.
    op.add_column(
        "location_ping_batches",
        sa.Column("rejection_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "location_ping_batches",
        sa.Column("rejection_digest", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_location_ping_batches_rejection_cluster",
        "location_ping_batches",
        "(rejection_manifest IS NULL) = (rejection_digest IS NULL)",
    )
    op.create_check_constraint(
        "ck_location_ping_batches_rejection_digest_length",
        "location_ping_batches",
        "rejection_digest IS NULL OR length(rejection_digest) = 64",
    )
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {DISPOSITION_FUNCTION}()
            RETURNS trigger AS $$
            BEGIN
              IF (OLD.receipt_signature IS NOT NULL OR OLD.rejection_digest IS NOT NULL)
                 AND (NEW.rejection_digest, NEW.rejection_manifest)
                     IS DISTINCT FROM (OLD.rejection_digest, OLD.rejection_manifest) THEN
                RAISE EXCEPTION USING ERRCODE = '55000',
                  MESSAGE = 'location ping batch dispositions are immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {DISPOSITION_TRIGGER}
            BEFORE UPDATE ON location_ping_batches
            FOR EACH ROW EXECUTE FUNCTION {DISPOSITION_FUNCTION}()
            """
        )
    )

    # --- OFF-006: final evidence adjudication --------------------------------
    #
    # A signed terminal statement for a v2 trip whose declared evidence can no
    # longer arrive. It never seals and never authenticates a manifest, so D25
    # keeps `sealed` the sole money trigger; no existing row is backfilled.
    op.add_column(
        "trip_sessions",
        sa.Column("evidence_adjudicated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "trip_sessions",
        sa.Column("evidence_adjudication_outcome", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "trip_sessions",
        sa.Column("evidence_adjudication_receipt_format_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "trip_sessions",
        sa.Column("evidence_adjudication_receipt_key_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "trip_sessions",
        sa.Column("evidence_adjudication_receipt_signature", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_trip_sessions_adjudication_cluster",
        "trip_sessions",
        "(evidence_adjudicated_at IS NULL AND "
        "evidence_adjudication_outcome IS NULL AND "
        "evidence_adjudication_receipt_format_version IS NULL AND "
        "evidence_adjudication_receipt_key_version IS NULL AND "
        "evidence_adjudication_receipt_signature IS NULL) OR "
        "(evidence_adjudicated_at IS NOT NULL AND "
        "evidence_adjudication_outcome = 'incomplete_grace_expired' AND "
        "evidence_adjudication_receipt_format_version = 2 AND "
        "evidence_adjudication_receipt_key_version IS NOT NULL AND "
        "evidence_adjudication_receipt_signature IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_trip_sessions_adjudication_excludes_verification",
        "trip_sessions",
        "evidence_adjudicated_at IS NULL OR evidence_manifest_verified_at IS NULL",
    )
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {ADJUDICATION_FUNCTION}()
            RETURNS trigger AS $$
            BEGIN
              IF OLD.evidence_adjudicated_at IS NOT NULL
                 AND (
                   NEW.evidence_adjudicated_at,
                   NEW.evidence_adjudication_outcome,
                   NEW.evidence_adjudication_receipt_format_version,
                   NEW.evidence_adjudication_receipt_key_version,
                   NEW.evidence_adjudication_receipt_signature
                 ) IS DISTINCT FROM (
                   OLD.evidence_adjudicated_at,
                   OLD.evidence_adjudication_outcome,
                   OLD.evidence_adjudication_receipt_format_version,
                   OLD.evidence_adjudication_receipt_key_version,
                   OLD.evidence_adjudication_receipt_signature
                 ) THEN
                RAISE EXCEPTION USING ERRCODE = '55000',
                  MESSAGE = 'trip evidence adjudications are immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {ADJUDICATION_TRIGGER}
            BEFORE UPDATE ON trip_sessions
            FOR EACH ROW EXECUTE FUNCTION {ADJUDICATION_FUNCTION}()
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("LOCK TABLE trip_sessions IN ACCESS EXCLUSIVE MODE"))
    op.execute(sa.text("LOCK TABLE location_ping_batches IN ACCESS EXCLUSIVE MODE"))
    adjudicated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM trip_sessions "
                "WHERE evidence_adjudicated_at IS NOT NULL)"
            )
        )
        .scalar_one()
    )
    if adjudicated:
        raise RuntimeError("Refusing to drop signed final trip evidence adjudications")
    durable_rejections = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM location_ping_batches "
                "WHERE rejection_digest IS NOT NULL)"
            )
        )
        .scalar_one()
    )
    if durable_rejections:
        raise RuntimeError("Refusing to drop durable ping batch rejection dispositions")

    op.execute(sa.text(f"DROP TRIGGER {ADJUDICATION_TRIGGER} ON trip_sessions"))
    op.execute(sa.text(f"DROP FUNCTION {ADJUDICATION_FUNCTION}()"))
    op.drop_constraint(
        "ck_trip_sessions_adjudication_excludes_verification", "trip_sessions", type_="check"
    )
    op.drop_constraint("ck_trip_sessions_adjudication_cluster", "trip_sessions", type_="check")
    op.drop_column("trip_sessions", "evidence_adjudication_receipt_signature")
    op.drop_column("trip_sessions", "evidence_adjudication_receipt_key_version")
    op.drop_column("trip_sessions", "evidence_adjudication_receipt_format_version")
    op.drop_column("trip_sessions", "evidence_adjudication_outcome")
    op.drop_column("trip_sessions", "evidence_adjudicated_at")

    op.execute(sa.text(f"DROP TRIGGER {DISPOSITION_TRIGGER} ON location_ping_batches"))
    op.execute(sa.text(f"DROP FUNCTION {DISPOSITION_FUNCTION}()"))
    op.drop_constraint(
        "ck_location_ping_batches_rejection_digest_length",
        "location_ping_batches",
        type_="check",
    )
    op.drop_constraint(
        "ck_location_ping_batches_rejection_cluster",
        "location_ping_batches",
        type_="check",
    )
    op.drop_column("location_ping_batches", "rejection_digest")
    op.drop_column("location_ping_batches", "rejection_manifest")

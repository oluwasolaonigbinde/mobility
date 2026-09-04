"""Register every generated report object before it is written, so orphans are recoverable.

Revision ID: 0082_report_publication_intents
Revises: 0081_payout_money_authority
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0082_report_publication_intents"
down_revision: str | Sequence[str] | None = "0081_payout_money_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATE_FIELDS_CHECK = (
    "(state = 'prepared' AND publisher_token IS NULL "
    "AND lease_expires_at IS NOT NULL AND completed_at IS NULL "
    "AND abandoned_at IS NULL AND cleaned_at IS NULL) OR "
    "(state = 'publishing' AND publisher_token IS NOT NULL "
    "AND lease_expires_at IS NOT NULL AND completed_at IS NULL "
    "AND abandoned_at IS NULL AND cleaned_at IS NULL) OR "
    "(state = 'complete' AND publisher_token IS NULL "
    "AND lease_expires_at IS NULL AND completed_at IS NOT NULL "
    "AND abandoned_at IS NULL AND cleaned_at IS NULL) OR "
    "(state = 'abandoned' AND publisher_token IS NULL "
    "AND lease_expires_at IS NULL AND completed_at IS NULL "
    "AND abandoned_at IS NOT NULL AND cleaned_at IS NULL) OR "
    "(state = 'cleaning' AND publisher_token IS NOT NULL "
    "AND lease_expires_at IS NOT NULL AND completed_at IS NULL "
    "AND abandoned_at IS NOT NULL AND cleaned_at IS NULL) OR "
    "(state = 'cleaned' AND publisher_token IS NULL "
    "AND lease_expires_at IS NULL AND completed_at IS NULL "
    "AND abandoned_at IS NOT NULL AND cleaned_at IS NOT NULL)"
)


def upgrade() -> None:
    op.create_table(
        "report_publication_intents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("report_issuance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), server_default=sa.text("'prepared'"), nullable=False),
        sa.Column("csv_object_key", sa.String(1024), nullable=False),
        sa.Column("pdf_object_key", sa.String(1024), nullable=False),
        sa.Column("publisher_token", postgresql.UUID(as_uuid=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("abandoned_at", sa.DateTime(timezone=True)),
        sa.Column("cleaned_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("generation > 0", name="ck_report_publication_intents_generation"),
        sa.CheckConstraint(
            "state IN ('prepared', 'publishing', 'complete', 'abandoned', 'cleaning', 'cleaned')",
            name="ck_report_publication_intents_state",
        ),
        sa.CheckConstraint(
            "csv_object_key <> pdf_object_key",
            name="ck_report_publication_intents_distinct_keys",
        ),
        sa.CheckConstraint(
            STATE_FIELDS_CHECK,
            name="ck_report_publication_intents_state_fields",
        ),
        sa.ForeignKeyConstraint(
            ["report_issuance_id"], ["report_issuances.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_issuance_id",
            "generation",
            name="uq_report_publication_intents_generation",
        ),
        sa.UniqueConstraint("csv_object_key", name="uq_report_publication_intents_csv_key"),
        sa.UniqueConstraint("pdf_object_key", name="uq_report_publication_intents_pdf_key"),
    )
    # At most one live generation per issuance, so two publishers never write concurrently
    # and a retry can only begin once the previous generation is abandoned.
    op.create_index(
        "uq_report_publication_intents_live",
        "report_publication_intents",
        ["report_issuance_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('prepared', 'publishing')"),
    )
    op.create_index(
        "ix_report_publication_intents_due",
        "report_publication_intents",
        ["state", "lease_expires_at", "created_at"],
    )
    op.execute(
        "CREATE FUNCTION reject_report_publication_mutation() RETURNS trigger AS $$ "
        "BEGIN IF ROW(NEW.report_issuance_id, NEW.generation, NEW.csv_object_key, "
        "NEW.pdf_object_key, NEW.created_at) IS DISTINCT FROM ROW(OLD.report_issuance_id, "
        "OLD.generation, OLD.csv_object_key, OLD.pdf_object_key, OLD.created_at) THEN "
        "RAISE EXCEPTION 'report publication generation identity is immutable'; END IF; "
        "IF NEW.state IS DISTINCT FROM OLD.state AND NOT ( "
        "(OLD.state = 'prepared' AND NEW.state = 'publishing') "
        "OR (OLD.state = 'prepared' AND NEW.state = 'abandoned') "
        "OR (OLD.state = 'publishing' AND NEW.state = 'complete') "
        "OR (OLD.state = 'publishing' AND NEW.state = 'abandoned') "
        "OR (OLD.state = 'abandoned' AND NEW.state = 'cleaning') "
        "OR (OLD.state = 'cleaning' AND NEW.state = 'cleaned') "
        "OR (OLD.state = 'cleaning' AND NEW.state = 'abandoned') "
        ") THEN RAISE EXCEPTION 'report publication state transition is invalid'; END IF; "
        "RETURN NEW; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER report_publication_intents_guarded BEFORE UPDATE "
        "ON report_publication_intents "
        "FOR EACH ROW EXECUTE FUNCTION reject_report_publication_mutation()"
    )
    op.execute(
        "CREATE FUNCTION reject_report_publication_delete() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'report publication generations are append-only'; END; "
        "$$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER report_publication_intents_no_delete BEFORE DELETE "
        "ON report_publication_intents "
        "FOR EACH ROW EXECUTE FUNCTION reject_report_publication_delete()"
    )


def downgrade() -> None:
    # A generation in one of these states is the ONLY record of a private object that no
    # artifact references. Dropping the table would strand exactly the orphans this
    # migration exists to make recoverable. Completed generations are already covered by
    # the 0071 report-evidence downgrade guard, and cleaned tombstones own nothing.
    pending = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM report_publication_intents "
                "WHERE state IN ('prepared', 'publishing', 'abandoned', 'cleaning'))"
            )
        )
        .scalar_one()
    )
    if pending:
        raise RuntimeError("0082 downgrade blocked: unreclaimed report publication objects exist")
    op.execute("DROP TRIGGER report_publication_intents_no_delete ON report_publication_intents")
    op.execute("DROP FUNCTION reject_report_publication_delete()")
    op.execute("DROP TRIGGER report_publication_intents_guarded ON report_publication_intents")
    op.execute("DROP FUNCTION reject_report_publication_mutation()")
    op.drop_index("ix_report_publication_intents_due", "report_publication_intents")
    op.drop_index("uq_report_publication_intents_live", "report_publication_intents")
    op.drop_table("report_publication_intents")

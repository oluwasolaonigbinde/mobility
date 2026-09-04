"""Persist and fence provider-visible payout submission effects.

Revision ID: 0083_payout_submission_intents
Revises: 0082_report_publication_intents
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0083_payout_submission_intents"
down_revision: str | Sequence[str] | None = "0082_report_publication_intents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INTENT_STATE_FIELDS = (
    "(state IN ('pending', 'query_only') AND claim_token IS NULL "
    "AND claim_action IS NULL AND claim_expires_at IS NULL "
    "AND provider_transfer_reference IS NULL AND resolved_at IS NULL) OR "
    "(state = 'claimed' AND generation > 0 AND claim_token IS NOT NULL "
    "AND claim_action IS NOT NULL AND claim_expires_at IS NOT NULL "
    "AND provider_transfer_reference IS NULL AND resolved_at IS NULL) OR "
    "(state = 'resolved' AND claim_token IS NULL AND claim_action IS NULL "
    "AND claim_expires_at IS NULL AND provider_transfer_reference IS NOT NULL "
    "AND resolved_at IS NOT NULL)"
)


def _create_intent_table() -> None:
    op.create_table(
        "payout_submission_intents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("payout_batch_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_name", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("instruction", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("instruction_fingerprint", sa.String(64), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("generation", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True)),
        sa.Column("claim_action", sa.String(16)),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True)),
        sa.Column("provider_submission_reference", sa.Text()),
        sa.Column("provider_transfer_reference", sa.Text()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
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
        sa.CheckConstraint(
            "length(instruction_fingerprint) = 64",
            name="ck_payout_submission_intents_instruction_fingerprint",
        ),
        sa.CheckConstraint(
            "length(idempotency_key) = 64",
            name="ck_payout_submission_intents_idempotency_key",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'claimed', 'query_only', 'resolved')",
            name="ck_payout_submission_intents_state",
        ),
        sa.CheckConstraint(
            "claim_action IS NULL OR claim_action IN ('submit', 'query')",
            name="ck_payout_submission_intents_claim_action",
        ),
        sa.CheckConstraint("generation >= 0", name="ck_payout_submission_intents_generation"),
        sa.CheckConstraint(
            INTENT_STATE_FIELDS,
            name="ck_payout_submission_intents_state_fields",
        ),
        sa.ForeignKeyConstraint(
            ["payout_batch_line_id"], ["payout_batch_lines.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "payout_batch_line_id", name="uq_payout_submission_intents_line"
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_payout_submission_intents_key"),
        sa.UniqueConstraint("claim_token", name="uq_payout_submission_intents_claim_token"),
    )
    op.create_index(
        "ix_payout_submission_intents_due",
        "payout_submission_intents",
        ["state", "claim_expires_at", "updated_at"],
    )
    op.create_index(
        "uq_payout_submission_intents_provider_transfer_reference",
        "payout_submission_intents",
        ["provider_transfer_reference"],
        unique=True,
        postgresql_where=sa.text("provider_transfer_reference IS NOT NULL"),
        sqlite_where=sa.text("provider_transfer_reference IS NOT NULL"),
    )


def _create_attempt_tables() -> None:
    op.create_table(
        "payout_submission_attempts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("instruction_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "generation > 0", name="ck_payout_submission_attempts_generation"
        ),
        sa.CheckConstraint(
            "action IN ('submit', 'query')", name="ck_payout_submission_attempts_action"
        ),
        sa.CheckConstraint(
            "length(idempotency_key) = 64",
            name="ck_payout_submission_attempts_idempotency_key",
        ),
        sa.CheckConstraint(
            "length(instruction_fingerprint) = 64",
            name="ck_payout_submission_attempts_instruction_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["intent_id"], ["payout_submission_intents.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "intent_id", "generation", name="uq_payout_submission_attempts_intent_generation"
        ),
        sa.UniqueConstraint("claim_token", name="uq_payout_submission_attempts_claim_token"),
        sa.UniqueConstraint(
            "id",
            "intent_id",
            "generation",
            "idempotency_key",
            "instruction_fingerprint",
            name="uq_payout_submission_attempts_observation_binding",
        ),
    )
    op.create_table(
        "payout_submission_observations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("instruction_fingerprint", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("provider_submission_reference", sa.Text()),
        sa.Column("provider_transfer_reference", sa.Text()),
        sa.Column("evidence_fingerprint", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "generation > 0", name="ck_payout_submission_observations_generation"
        ),
        sa.CheckConstraint(
            "outcome IN ('submitted', 'found', 'not_found', 'unknown')",
            name="ck_payout_submission_observations_outcome",
        ),
        sa.CheckConstraint(
            "length(idempotency_key) = 64",
            name="ck_payout_submission_observations_idempotency_key",
        ),
        sa.CheckConstraint(
            "length(instruction_fingerprint) = 64",
            name="ck_payout_submission_observations_instruction_fingerprint",
        ),
        sa.CheckConstraint(
            "length(evidence_fingerprint) = 64",
            name="ck_payout_submission_observations_evidence_fingerprint",
        ),
        sa.CheckConstraint(
            "(outcome IN ('submitted', 'found') "
            "AND provider_transfer_reference IS NOT NULL) OR "
            "(outcome IN ('not_found', 'unknown') "
            "AND provider_transfer_reference IS NULL)",
            name="ck_payout_submission_observations_provider_reference",
        ),
        sa.ForeignKeyConstraint(
            [
                "attempt_id",
                "intent_id",
                "generation",
                "idempotency_key",
                "instruction_fingerprint",
            ],
            [
                "payout_submission_attempts.id",
                "payout_submission_attempts.intent_id",
                "payout_submission_attempts.generation",
                "payout_submission_attempts.idempotency_key",
                "payout_submission_attempts.instruction_fingerprint",
            ],
            ondelete="RESTRICT",
            name="fk_payout_submission_observations_attempt_binding",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attempt_id", name="uq_payout_submission_observations_attempt"
        ),
        sa.UniqueConstraint(
            "intent_id",
            "generation",
            name="uq_payout_submission_observations_intent_generation",
        ),
    )
    op.create_index(
        "ix_payout_submission_observations_intent",
        "payout_submission_observations",
        ["intent_id", "created_at"],
    )


def _backfill_resolved_intents() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO payout_submission_intents (
                payout_batch_line_id,
                provider_name,
                idempotency_key,
                instruction,
                instruction_fingerprint,
                requested_by_user_id,
                state,
                generation,
                provider_submission_reference,
                provider_transfer_reference,
                resolved_at,
                created_at,
                updated_at
            )
            SELECT
                line.id,
                'legacy',
                line.idempotency_key,
                line.instruction,
                line.instruction_fingerprint,
                batch.created_by_user_id,
                'resolved',
                0,
                COALESCE(batch.provider_submission_reference, 'legacy-' || line.id::text),
                line.provider_transfer_reference,
                COALESCE(line.reconciled_at, batch.submitted_at, line.created_at),
                line.created_at,
                now()
            FROM payout_batch_lines AS line
            JOIN payout_batches AS batch ON batch.id = line.batch_id
            WHERE line.provider_transfer_reference IS NOT NULL
            """
        )
    )


def _create_guards() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION guard_payout_submission_intent_mutation()
            RETURNS trigger AS $$
            BEGIN
              IF ROW(
                NEW.payout_batch_line_id,
                NEW.provider_name,
                NEW.idempotency_key,
                NEW.instruction,
                NEW.instruction_fingerprint,
                NEW.requested_by_user_id,
                NEW.created_at
              ) IS DISTINCT FROM ROW(
                OLD.payout_batch_line_id,
                OLD.provider_name,
                OLD.idempotency_key,
                OLD.instruction,
                OLD.instruction_fingerprint,
                OLD.requested_by_user_id,
                OLD.created_at
              ) THEN
                RAISE EXCEPTION 'payout submission intent identity is immutable';
              END IF;
              IF NOT (
                (OLD.state IN ('pending', 'query_only')
                  AND NEW.state = 'claimed' AND NEW.generation = OLD.generation + 1)
                OR (OLD.state = 'claimed' AND NEW.state = 'claimed'
                  AND NEW.generation = OLD.generation + 1)
                OR (OLD.state = 'claimed' AND NEW.state IN ('pending', 'query_only', 'resolved')
                  AND NEW.generation = OLD.generation)
              ) THEN
                RAISE EXCEPTION 'payout submission intent state transition is invalid';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        "CREATE TRIGGER payout_submission_intents_guarded BEFORE UPDATE "
        "ON payout_submission_intents FOR EACH ROW "
        "EXECUTE FUNCTION guard_payout_submission_intent_mutation()"
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION reject_payout_submission_history_mutation()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'payout submission history is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    for table in (
        "payout_submission_intents",
        "payout_submission_attempts",
        "payout_submission_observations",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_payout_submission_history_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION reject_payout_submission_history_mutation()"
        )
    for table in ("payout_submission_attempts", "payout_submission_observations"):
        op.execute(
            f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_payout_submission_history_mutation()"
        )


def upgrade() -> None:
    _create_intent_table()
    _create_attempt_tables()
    _backfill_resolved_intents()
    _create_guards()


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM payout_submission_intents) "
                "OR EXISTS (SELECT 1 FROM payout_submission_attempts) "
                "OR EXISTS (SELECT 1 FROM payout_submission_observations)"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0083 downgrade blocked: payout submission history exists")
    for table in (
        "payout_submission_observations",
        "payout_submission_attempts",
        "payout_submission_intents",
    ):
        op.execute(f"DROP TRIGGER {table}_no_truncate ON {table}")
        op.execute(f"DROP TRIGGER {table}_no_delete ON {table}")
    for table in ("payout_submission_observations", "payout_submission_attempts"):
        op.execute(f"DROP TRIGGER {table}_no_update ON {table}")
    op.execute("DROP TRIGGER payout_submission_intents_guarded ON payout_submission_intents")
    op.execute("DROP FUNCTION reject_payout_submission_history_mutation()")
    op.execute("DROP FUNCTION guard_payout_submission_intent_mutation()")
    op.drop_index(
        "ix_payout_submission_observations_intent",
        table_name="payout_submission_observations",
    )
    op.drop_table("payout_submission_observations")
    op.drop_table("payout_submission_attempts")
    op.drop_index(
        "uq_payout_submission_intents_provider_transfer_reference",
        table_name="payout_submission_intents",
    )
    op.drop_index(
        "ix_payout_submission_intents_due", table_name="payout_submission_intents"
    )
    op.drop_table("payout_submission_intents")

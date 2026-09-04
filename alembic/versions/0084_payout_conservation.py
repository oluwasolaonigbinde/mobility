"""Conserve payout money across failure, replacement and recovery.

Revision ID: 0084_payout_conservation
Revises: 0083_payout_submission_intents
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0084_payout_conservation"
down_revision: str | Sequence[str] | None = "0083_payout_submission_intents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE_STATE = (
    "(status IN ('reserved', 'submitted') AND reservation_active = true) OR "
    "(status IN ('succeeded', 'failed', 'void') AND reservation_active = false)"
)
INTENT_STATE_FIELDS = (
    "(state IN ('pending', 'query_only') AND claim_token IS NULL "
    "AND claim_action IS NULL AND claim_expires_at IS NULL "
    "AND provider_transfer_reference IS NULL AND resolved_at IS NULL) OR "
    "(state = 'claimed' AND generation > 0 AND claim_token IS NOT NULL "
    "AND claim_action IS NOT NULL AND claim_expires_at IS NOT NULL "
    "AND provider_transfer_reference IS NULL AND resolved_at IS NULL) OR "
    "(state = 'resolved' AND claim_token IS NULL AND claim_action IS NULL "
    "AND claim_expires_at IS NULL AND provider_transfer_reference IS NOT NULL "
    "AND resolved_at IS NOT NULL) OR "
    "(state = 'cancelled' AND claim_token IS NULL AND claim_action IS NULL "
    "AND claim_expires_at IS NULL AND provider_transfer_reference IS NULL "
    "AND resolved_at IS NOT NULL)"
)


def _replace_intent_guards(*, include_cancelled: bool) -> None:
    states = (
        "'pending', 'claimed', 'query_only', 'resolved', 'cancelled'"
        if include_cancelled
        else "'pending', 'claimed', 'query_only', 'resolved'"
    )
    state_fields = (
        INTENT_STATE_FIELDS
        if include_cancelled
        else (
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
    )
    op.drop_constraint(
        "ck_payout_submission_intents_state",
        "payout_submission_intents",
        type_="check",
    )
    op.drop_constraint(
        "ck_payout_submission_intents_state_fields",
        "payout_submission_intents",
        type_="check",
    )
    op.create_check_constraint(
        "ck_payout_submission_intents_state",
        "payout_submission_intents",
        f"state IN ({states})",
    )
    op.create_check_constraint(
        "ck_payout_submission_intents_state_fields",
        "payout_submission_intents",
        state_fields,
    )
    cancelled_transition = (
        "OR (OLD.state = 'pending' AND NEW.state = 'cancelled' AND NEW.generation = OLD.generation)"
        if include_cancelled
        else ""
    )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION guard_payout_submission_intent_mutation()
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
                OR (OLD.state = 'claimed'
                  AND NEW.state IN ('pending', 'query_only', 'resolved')
                  AND NEW.generation = OLD.generation)
                {cancelled_transition}
              ) THEN
                RAISE EXCEPTION 'payout submission intent state transition is invalid';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )


def _create_line_guards() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION guard_payout_batch_line_mutation()
            RETURNS trigger AS $$
            BEGIN
              IF ROW(
                NEW.batch_id, NEW.ledger_entry_id, NEW.predecessor_line_id,
                NEW.payee_version_id, NEW.bank_account_version_id,
                NEW.amount, NEW.currency, NEW.instruction,
                NEW.instruction_fingerprint, NEW.idempotency_key, NEW.created_at
              ) IS DISTINCT FROM ROW(
                OLD.batch_id, OLD.ledger_entry_id, OLD.predecessor_line_id,
                OLD.payee_version_id, OLD.bank_account_version_id,
                OLD.amount, OLD.currency, OLD.instruction,
                OLD.instruction_fingerprint, OLD.idempotency_key, OLD.created_at
              ) THEN
                RAISE EXCEPTION 'payout batch line identity is immutable';
              END IF;
              IF NOT (
                OLD.status = NEW.status
                OR (OLD.status = 'reserved' AND NEW.status IN ('submitted', 'void'))
                OR (OLD.status = 'submitted' AND NEW.status IN ('succeeded', 'failed'))
                OR (OLD.status = 'failed' AND NEW.status = 'succeeded')
              ) THEN
                RAISE EXCEPTION 'payout batch line state transition is invalid';
              END IF;
              IF OLD.provider_transfer_reference IS DISTINCT FROM
                   NEW.provider_transfer_reference
                 AND NOT (
                   OLD.provider_transfer_reference IS NULL
                   AND NEW.provider_transfer_reference IS NOT NULL
                   AND OLD.status = 'reserved' AND NEW.status = 'submitted'
                 ) THEN
                RAISE EXCEPTION 'payout provider transfer reference is immutable';
              END IF;
              IF OLD.reservation_active IS DISTINCT FROM NEW.reservation_active
                 AND NOT (
                   OLD.reservation_active = true
                   AND NEW.reservation_active = false
                   AND NEW.status IN ('succeeded', 'failed', 'void')
                 ) THEN
                RAISE EXCEPTION 'payout reservation release is invalid';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        "CREATE TRIGGER payout_batch_lines_guarded BEFORE UPDATE "
        "ON payout_batch_lines FOR EACH ROW "
        "EXECUTE FUNCTION guard_payout_batch_line_mutation()"
    )
    op.execute(
        "CREATE TRIGGER payout_batch_lines_no_delete BEFORE DELETE "
        "ON payout_batch_lines FOR EACH ROW "
        "EXECUTE FUNCTION reject_payout_submission_history_mutation()"
    )
    op.execute(
        "CREATE TRIGGER payout_batch_lines_no_truncate BEFORE TRUNCATE "
        "ON payout_batch_lines FOR EACH STATEMENT "
        "EXECUTE FUNCTION reject_payout_submission_history_mutation()"
    )


def _create_recovery_incidents() -> None:
    op.create_table(
        "payout_recovery_incidents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("ledger_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chain_root_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exposure_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_fraud_flag_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_reversal_entry_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("dedupe_key", sa.String(64), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('confirmed_fraud', 'duplicate_cash')",
            name="ck_payout_recovery_incidents_kind",
        ),
        sa.CheckConstraint(
            "status IN ('contingent', 'debt_activated', 'closed')",
            name="ck_payout_recovery_incidents_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_payout_recovery_incidents_amount_positive"),
        sa.CheckConstraint("length(currency) = 3", name="ck_payout_recovery_incidents_currency"),
        sa.CheckConstraint(
            "length(dedupe_key) = 64",
            name="ck_payout_recovery_incidents_dedupe_key",
        ),
        sa.CheckConstraint(
            "(kind = 'confirmed_fraud' AND source_fraud_flag_id IS NOT NULL "
            "AND source_reversal_entry_id IS NOT NULL) OR "
            "(kind = 'duplicate_cash' AND source_fraud_flag_id IS NULL "
            "AND source_reversal_entry_id IS NULL)",
            name="ck_payout_recovery_incidents_source",
        ),
        sa.CheckConstraint(
            "(status = 'contingent' AND exposure_line_id IS NOT NULL "
            "AND resolved_at IS NULL) OR "
            "(status IN ('debt_activated', 'closed') AND resolved_at IS NOT NULL)",
            name="ck_payout_recovery_incidents_resolution",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_entry_id"], ["earnings_ledger_entries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["chain_root_line_id"], ["payout_batch_lines.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["exposure_line_id"], ["payout_batch_lines.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["source_fraud_flag_id"], ["fraud_flags.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_reversal_entry_id"],
            ["earnings_ledger_entries.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_payout_recovery_incidents_dedupe_key"),
    )
    op.create_index(
        "ix_payout_recovery_incidents_ledger",
        "payout_recovery_incidents",
        ["ledger_entry_id", "created_at"],
    )
    op.create_index(
        "ix_payout_recovery_incidents_exposure",
        "payout_recovery_incidents",
        ["exposure_line_id", "status"],
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION guard_payout_recovery_incident_mutation()
            RETURNS trigger AS $$
            BEGIN
              IF ROW(
                NEW.ledger_entry_id, NEW.chain_root_line_id, NEW.exposure_line_id,
                NEW.source_fraud_flag_id, NEW.source_reversal_entry_id,
                NEW.created_by_user_id, NEW.kind, NEW.amount, NEW.currency,
                NEW.dedupe_key, NEW.created_at
              ) IS DISTINCT FROM ROW(
                OLD.ledger_entry_id, OLD.chain_root_line_id, OLD.exposure_line_id,
                OLD.source_fraud_flag_id, OLD.source_reversal_entry_id,
                OLD.created_by_user_id, OLD.kind, OLD.amount, OLD.currency,
                OLD.dedupe_key, OLD.created_at
              ) THEN
                RAISE EXCEPTION 'payout recovery incident identity is immutable';
              END IF;
              IF NOT (
                OLD.status = NEW.status
                OR (OLD.status = 'contingent' AND NEW.status IN ('debt_activated', 'closed'))
                OR (OLD.status = 'debt_activated' AND NEW.status = 'closed')
                OR (OLD.status = 'closed' AND NEW.status = 'debt_activated')
              ) THEN
                RAISE EXCEPTION 'payout recovery incident state transition is invalid';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        "CREATE TRIGGER payout_recovery_incidents_guarded BEFORE UPDATE "
        "ON payout_recovery_incidents FOR EACH ROW "
        "EXECUTE FUNCTION guard_payout_recovery_incident_mutation()"
    )
    for operation, scope in (("DELETE", "ROW"), ("TRUNCATE", "STATEMENT")):
        op.execute(
            f"CREATE TRIGGER payout_recovery_incidents_no_{operation.lower()} "
            f"BEFORE {operation} ON payout_recovery_incidents FOR EACH {scope} "
            "EXECUTE FUNCTION reject_payout_submission_history_mutation()"
        )


def upgrade() -> None:
    op.add_column(
        "payout_batch_lines",
        sa.Column("predecessor_line_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "fk_payout_batch_lines_predecessor_line_id_payout_batch_lines",
        "payout_batch_lines",
        "payout_batch_lines",
        ["predecessor_line_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_payout_batch_lines_predecessor_not_self",
        "payout_batch_lines",
        "predecessor_line_id IS NULL OR predecessor_line_id <> id",
    )
    op.create_index(
        "uq_payout_batch_lines_predecessor",
        "payout_batch_lines",
        ["predecessor_line_id"],
        unique=True,
        postgresql_where=sa.text("predecessor_line_id IS NOT NULL"),
        sqlite_where=sa.text("predecessor_line_id IS NOT NULL"),
    )
    op.drop_constraint("ck_payout_batch_lines_active_state", "payout_batch_lines", type_="check")
    op.execute(
        "UPDATE payout_batch_lines SET reservation_active = false "
        "WHERE status IN ('succeeded', 'failed')"
    )
    op.create_check_constraint(
        "ck_payout_batch_lines_active_state", "payout_batch_lines", ACTIVE_STATE
    )
    _replace_intent_guards(include_cancelled=True)
    _create_line_guards()
    _create_recovery_incidents()

    op.drop_constraint(
        "uq_payout_debt_obligations_source_reversal",
        "payout_debt_obligations",
        type_="unique",
    )
    op.alter_column("payout_debt_obligations", "source_reversal_entry_id", nullable=True)
    op.add_column(
        "payout_debt_obligations",
        sa.Column("recovery_incident_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "fk_payout_debt_obligations_recovery_incident",
        "payout_debt_obligations",
        "payout_recovery_incidents",
        ["recovery_incident_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_payout_debt_obligations_recovery_incident",
        "payout_debt_obligations",
        ["recovery_incident_id"],
    )
    op.create_check_constraint(
        "ck_payout_debt_obligations_source",
        "payout_debt_obligations",
        "source_reversal_entry_id IS NOT NULL OR recovery_incident_id IS NOT NULL",
    )
    op.create_index(
        "uq_payout_debt_obligations_direct_reversal",
        "payout_debt_obligations",
        ["source_reversal_entry_id"],
        unique=True,
        postgresql_where=sa.text("recovery_incident_id IS NULL"),
        sqlite_where=sa.text("recovery_incident_id IS NULL"),
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM payout_recovery_incidents) "
                "OR EXISTS (SELECT 1 FROM payout_batch_lines "
                "WHERE predecessor_line_id IS NOT NULL "
                "OR (status IN ('succeeded', 'failed') AND reservation_active = false)) "
                "OR EXISTS (SELECT 1 FROM payout_submission_intents "
                "WHERE state = 'cancelled') "
                "OR EXISTS (SELECT 1 FROM payout_debt_obligations "
                "WHERE recovery_incident_id IS NOT NULL)"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0084 downgrade blocked: payout conservation authority exists")

    op.drop_index(
        "uq_payout_debt_obligations_direct_reversal",
        table_name="payout_debt_obligations",
    )
    op.drop_constraint(
        "ck_payout_debt_obligations_source",
        "payout_debt_obligations",
        type_="check",
    )
    op.drop_constraint(
        "uq_payout_debt_obligations_recovery_incident",
        "payout_debt_obligations",
        type_="unique",
    )
    op.drop_constraint(
        "fk_payout_debt_obligations_recovery_incident",
        "payout_debt_obligations",
        type_="foreignkey",
    )
    op.drop_column("payout_debt_obligations", "recovery_incident_id")
    op.alter_column("payout_debt_obligations", "source_reversal_entry_id", nullable=False)
    op.create_unique_constraint(
        "uq_payout_debt_obligations_source_reversal",
        "payout_debt_obligations",
        ["source_reversal_entry_id"],
    )

    op.execute("DROP TRIGGER payout_recovery_incidents_no_truncate ON payout_recovery_incidents")
    op.execute("DROP TRIGGER payout_recovery_incidents_no_delete ON payout_recovery_incidents")
    op.execute("DROP TRIGGER payout_recovery_incidents_guarded ON payout_recovery_incidents")
    op.execute("DROP FUNCTION guard_payout_recovery_incident_mutation()")
    op.drop_index(
        "ix_payout_recovery_incidents_exposure",
        table_name="payout_recovery_incidents",
    )
    op.drop_index(
        "ix_payout_recovery_incidents_ledger",
        table_name="payout_recovery_incidents",
    )
    op.drop_table("payout_recovery_incidents")

    op.execute("DROP TRIGGER payout_batch_lines_no_truncate ON payout_batch_lines")
    op.execute("DROP TRIGGER payout_batch_lines_no_delete ON payout_batch_lines")
    op.execute("DROP TRIGGER payout_batch_lines_guarded ON payout_batch_lines")
    op.execute("DROP FUNCTION guard_payout_batch_line_mutation()")
    _replace_intent_guards(include_cancelled=False)
    op.drop_constraint("ck_payout_batch_lines_active_state", "payout_batch_lines", type_="check")
    op.execute("UPDATE payout_batch_lines SET reservation_active = (status <> 'void')")
    op.create_check_constraint(
        "ck_payout_batch_lines_active_state",
        "payout_batch_lines",
        "(status = 'void' AND reservation_active = false) OR "
        "(status <> 'void' AND reservation_active = true)",
    )
    op.drop_index("uq_payout_batch_lines_predecessor", table_name="payout_batch_lines")
    op.drop_constraint(
        "ck_payout_batch_lines_predecessor_not_self",
        "payout_batch_lines",
        type_="check",
    )
    op.drop_constraint(
        "fk_payout_batch_lines_predecessor_line_id_payout_batch_lines",
        "payout_batch_lines",
        type_="foreignkey",
    )
    op.drop_column("payout_batch_lines", "predecessor_line_id")

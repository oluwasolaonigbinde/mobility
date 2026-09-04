from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PayoutBatchStatus(StrEnum):
    DRAFT = "draft"
    RESERVED = "reserved"
    SUBMITTED = "submitted"
    RECONCILED = "reconciled"
    COMPLETED = "completed"
    FAILED = "failed"
    VOID = "void"


class PayoutBatchLineStatus(StrEnum):
    RESERVED = "reserved"
    SUBMITTED = "submitted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    VOID = "void"


class PayoutSubmissionIntentState(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    QUERY_ONLY = "query_only"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class PayoutSubmissionClaimAction(StrEnum):
    SUBMIT = "submit"
    QUERY = "query"


class PayoutSubmissionObservationOutcome(StrEnum):
    SUBMITTED = "submitted"
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


class PayoutRecoveryIncidentKind(StrEnum):
    CONFIRMED_FRAUD = "confirmed_fraud"
    DUPLICATE_CASH = "duplicate_cash"


class PayoutRecoveryIncidentStatus(StrEnum):
    CONTINGENT = "contingent"
    DEBT_ACTIVATED = "debt_activated"
    CLOSED = "closed"


class PayoutBatch(Base):
    __tablename__ = "payout_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'reserved', 'submitted', 'reconciled', "
            "'completed', 'failed', 'void')",
            name="ck_payout_batches_status",
        ),
        CheckConstraint("length(currency) = 3", name="ck_payout_batches_currency"),
        CheckConstraint("total_amount >= 0", name="ck_payout_batches_total_non_negative"),
        CheckConstraint(
            "(status = 'draft' AND instruction_set_fingerprint IS NULL) OR "
            "(status <> 'draft' AND instruction_set_fingerprint IS NOT NULL)",
            name="ck_payout_batches_reserved_fingerprint",
        ),
        CheckConstraint(
            "approved_by_user_id IS NULL OR approved_by_user_id <> created_by_user_id",
            name="ck_payout_batches_maker_checker",
        ),
        Index("ix_payout_batches_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default=text("0"), nullable=False
    )
    instruction_set_fingerprint: Mapped[str | None] = mapped_column(String(64))
    provider_submission_reference: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayoutBatchLine(Base):
    __tablename__ = "payout_batch_lines"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payout_batch_lines_amount_positive"),
        CheckConstraint("length(currency) = 3", name="ck_payout_batch_lines_currency"),
        CheckConstraint(
            "length(instruction_fingerprint) = 64",
            name="ck_payout_batch_lines_instruction_fingerprint",
        ),
        CheckConstraint(
            "status IN ('reserved', 'submitted', 'succeeded', 'failed', 'void')",
            name="ck_payout_batch_lines_status",
        ),
        CheckConstraint(
            "(status IN ('reserved', 'void') AND provider_transfer_reference IS NULL) OR "
            "(status IN ('submitted', 'succeeded', 'failed') "
            "AND provider_transfer_reference IS NOT NULL)",
            name="ck_payout_batch_lines_provider_state",
        ),
        CheckConstraint(
            "(status IN ('reserved', 'submitted') AND reservation_active = true) OR "
            "(status IN ('succeeded', 'failed', 'void') AND reservation_active = false)",
            name="ck_payout_batch_lines_active_state",
        ),
        CheckConstraint(
            "predecessor_line_id IS NULL OR predecessor_line_id <> id",
            name="ck_payout_batch_lines_predecessor_not_self",
        ),
        Index("ix_payout_batch_lines_batch_id", "batch_id"),
        Index("ix_payout_batch_lines_ledger_entry_id", "ledger_entry_id"),
        Index(
            "uq_payout_batch_lines_active_ledger_entry",
            "ledger_entry_id",
            unique=True,
            sqlite_where=text("reservation_active = true"),
            postgresql_where=text("reservation_active = true"),
        ),
        Index(
            "uq_payout_batch_lines_provider_transfer_reference",
            "provider_transfer_reference",
            unique=True,
            sqlite_where=text("provider_transfer_reference IS NOT NULL"),
            postgresql_where=text("provider_transfer_reference IS NOT NULL"),
        ),
        Index(
            "uq_payout_batch_lines_predecessor",
            "predecessor_line_id",
            unique=True,
            sqlite_where=text("predecessor_line_id IS NOT NULL"),
            postgresql_where=text("predecessor_line_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_batches.id", ondelete="RESTRICT"), nullable=False
    )
    ledger_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT"), nullable=False
    )
    predecessor_line_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("payout_batch_lines.id", ondelete="RESTRICT")
    )
    payee_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("payee_versions.id", ondelete="RESTRICT"), nullable=False
    )
    bank_account_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("payee_bank_account_versions.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    instruction: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
    )
    instruction_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(16),
        default=PayoutBatchLineStatus.RESERVED,
        server_default=text("'reserved'"),
        nullable=False,
    )
    provider_transfer_reference: Mapped[str | None] = mapped_column(Text)
    reconciled_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_provider_evidence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reservation_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayoutSubmissionIntent(Base):
    __tablename__ = "payout_submission_intents"
    __table_args__ = (
        CheckConstraint(
            "length(instruction_fingerprint) = 64",
            name="ck_payout_submission_intents_instruction_fingerprint",
        ),
        CheckConstraint(
            "length(idempotency_key) = 64",
            name="ck_payout_submission_intents_idempotency_key",
        ),
        CheckConstraint(
            "state IN ('pending', 'claimed', 'query_only', 'resolved', 'cancelled')",
            name="ck_payout_submission_intents_state",
        ),
        CheckConstraint(
            "claim_action IS NULL OR claim_action IN ('submit', 'query')",
            name="ck_payout_submission_intents_claim_action",
        ),
        CheckConstraint("generation >= 0", name="ck_payout_submission_intents_generation"),
        CheckConstraint(
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
            "AND resolved_at IS NOT NULL)",
            name="ck_payout_submission_intents_state_fields",
        ),
        Index(
            "ix_payout_submission_intents_due",
            "state",
            "claim_expires_at",
            "updated_at",
        ),
        Index(
            "uq_payout_submission_intents_provider_transfer_reference",
            "provider_transfer_reference",
            unique=True,
            sqlite_where=text("provider_transfer_reference IS NOT NULL"),
            postgresql_where=text("provider_transfer_reference IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    payout_batch_line_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_batch_lines.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    instruction: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
    )
    instruction_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(16),
        default=PayoutSubmissionIntentState.PENDING,
        server_default=text("'pending'"),
        nullable=False,
    )
    generation: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    claim_token: Mapped[UUID | None] = mapped_column(unique=True)
    claim_action: Mapped[str | None] = mapped_column(String(16))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_submission_reference: Mapped[str | None] = mapped_column(Text)
    provider_transfer_reference: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PayoutSubmissionAttempt(Base):
    __tablename__ = "payout_submission_attempts"
    __table_args__ = (
        CheckConstraint("generation > 0", name="ck_payout_submission_attempts_generation"),
        CheckConstraint(
            "action IN ('submit', 'query')", name="ck_payout_submission_attempts_action"
        ),
        CheckConstraint(
            "length(idempotency_key) = 64",
            name="ck_payout_submission_attempts_idempotency_key",
        ),
        CheckConstraint(
            "length(instruction_fingerprint) = 64",
            name="ck_payout_submission_attempts_instruction_fingerprint",
        ),
        UniqueConstraint(
            "intent_id", "generation", name="uq_payout_submission_attempts_intent_generation"
        ),
        UniqueConstraint("claim_token", name="uq_payout_submission_attempts_claim_token"),
        UniqueConstraint(
            "id",
            "intent_id",
            "generation",
            "idempotency_key",
            "instruction_fingerprint",
            name="uq_payout_submission_attempts_observation_binding",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    intent_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_submission_intents.id", ondelete="RESTRICT"), nullable=False
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_token: Mapped[UUID] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    instruction_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayoutSubmissionObservation(Base):
    __tablename__ = "payout_submission_observations"
    __table_args__ = (
        CheckConstraint("generation > 0", name="ck_payout_submission_observations_generation"),
        CheckConstraint(
            "outcome IN ('submitted', 'found', 'not_found', 'unknown')",
            name="ck_payout_submission_observations_outcome",
        ),
        CheckConstraint(
            "length(idempotency_key) = 64",
            name="ck_payout_submission_observations_idempotency_key",
        ),
        CheckConstraint(
            "length(instruction_fingerprint) = 64",
            name="ck_payout_submission_observations_instruction_fingerprint",
        ),
        CheckConstraint(
            "length(evidence_fingerprint) = 64",
            name="ck_payout_submission_observations_evidence_fingerprint",
        ),
        CheckConstraint(
            "(outcome IN ('submitted', 'found') "
            "AND provider_transfer_reference IS NOT NULL) OR "
            "(outcome IN ('not_found', 'unknown') "
            "AND provider_transfer_reference IS NULL)",
            name="ck_payout_submission_observations_provider_reference",
        ),
        ForeignKeyConstraint(
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
        UniqueConstraint("attempt_id", name="uq_payout_submission_observations_attempt"),
        UniqueConstraint(
            "intent_id",
            "generation",
            name="uq_payout_submission_observations_intent_generation",
        ),
        Index("ix_payout_submission_observations_intent", "intent_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    attempt_id: Mapped[UUID] = mapped_column(nullable=False)
    intent_id: Mapped[UUID] = mapped_column(nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    instruction_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_submission_reference: Mapped[str | None] = mapped_column(Text)
    provider_transfer_reference: Mapped[str | None] = mapped_column(Text)
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


_SUBMISSION_INTENT_IDENTITY_FIELDS = frozenset(
    {
        "payout_batch_line_id",
        "provider_name",
        "idempotency_key",
        "instruction",
        "instruction_fingerprint",
        "requested_by_user_id",
        "created_at",
    }
)
_SUBMISSION_INTENT_TRANSITIONS = frozenset(
    {
        (PayoutSubmissionIntentState.PENDING.value, PayoutSubmissionIntentState.CLAIMED.value),
        (
            PayoutSubmissionIntentState.QUERY_ONLY.value,
            PayoutSubmissionIntentState.CLAIMED.value,
        ),
        (PayoutSubmissionIntentState.CLAIMED.value, PayoutSubmissionIntentState.PENDING.value),
        (
            PayoutSubmissionIntentState.CLAIMED.value,
            PayoutSubmissionIntentState.QUERY_ONLY.value,
        ),
        (PayoutSubmissionIntentState.CLAIMED.value, PayoutSubmissionIntentState.RESOLVED.value),
        (PayoutSubmissionIntentState.PENDING.value, PayoutSubmissionIntentState.CANCELLED.value),
    }
)


@event.listens_for(PayoutSubmissionIntent, "before_update")
def validate_payout_submission_intent_update(_mapper, _connection, target) -> None:
    state = inspect(target)
    if any(
        state.attrs[field].history.has_changes() for field in _SUBMISSION_INTENT_IDENTITY_FIELDS
    ):
        raise ValueError("payout submission intent identity is immutable")
    state_history = state.attrs.state.history
    before = state_history.deleted[0] if state_history.deleted else target.state
    after = state_history.added[0] if state_history.added else target.state
    if state_history.has_changes() and (before, after) not in _SUBMISSION_INTENT_TRANSITIONS:
        raise ValueError("payout submission intent state transition is invalid")
    generation_history = state.attrs.generation.history
    generation_changed = generation_history.has_changes()
    old_generation = (
        generation_history.deleted[0] if generation_history.deleted else target.generation
    )
    entering_claimed = after == PayoutSubmissionIntentState.CLAIMED.value and (
        before
        in {
            PayoutSubmissionIntentState.PENDING.value,
            PayoutSubmissionIntentState.QUERY_ONLY.value,
            PayoutSubmissionIntentState.CLAIMED.value,
        }
    )
    leaving_claimed = before == PayoutSubmissionIntentState.CLAIMED.value and after in {
        PayoutSubmissionIntentState.PENDING.value,
        PayoutSubmissionIntentState.QUERY_ONLY.value,
        PayoutSubmissionIntentState.RESOLVED.value,
    }
    if entering_claimed:
        if not generation_changed or target.generation != old_generation + 1:
            raise ValueError("payout submission intent generation is not monotonic")
    elif leaving_claimed:
        if generation_changed:
            raise ValueError("payout submission intent generation is not monotonic")
    elif (
        before == PayoutSubmissionIntentState.PENDING.value
        and after == PayoutSubmissionIntentState.CANCELLED.value
    ):
        if generation_changed:
            raise ValueError("payout submission intent generation is not monotonic")
    else:
        raise ValueError("payout submission intent state transition is invalid")


@event.listens_for(PayoutSubmissionIntent, "before_delete")
def reject_payout_submission_intent_delete(_mapper, _connection, _target) -> None:
    raise ValueError("payout submission intents are append-only")


@event.listens_for(PayoutSubmissionAttempt, "before_update")
@event.listens_for(PayoutSubmissionAttempt, "before_delete")
def reject_payout_submission_attempt_mutation(_mapper, _connection, _target) -> None:
    raise ValueError("payout submission attempts are append-only")


@event.listens_for(PayoutSubmissionObservation, "before_update")
@event.listens_for(PayoutSubmissionObservation, "before_delete")
def reject_payout_submission_observation_mutation(_mapper, _connection, _target) -> None:
    raise ValueError("payout submission observations are append-only")


class PayoutLineReconciliationEvent(Base):
    __tablename__ = "payout_line_reconciliation_events"
    __table_args__ = (
        CheckConstraint("source IN ('webhook', 'poll')", name="ck_payout_line_events_source"),
        CheckConstraint("outcome IN ('succeeded', 'failed')", name="ck_payout_line_events_outcome"),
        CheckConstraint(
            "length(evidence_fingerprint) = 64",
            name="ck_payout_line_events_evidence_fingerprint",
        ),
        Index("ix_payout_line_events_line_id", "line_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    line_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_batch_lines.id", ondelete="RESTRICT"), nullable=False
    )
    provider_event_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reconciled_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayoutRecoveryIncident(Base):
    __tablename__ = "payout_recovery_incidents"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('confirmed_fraud', 'duplicate_cash')",
            name="ck_payout_recovery_incidents_kind",
        ),
        CheckConstraint(
            "status IN ('contingent', 'debt_activated', 'closed')",
            name="ck_payout_recovery_incidents_status",
        ),
        CheckConstraint("amount > 0", name="ck_payout_recovery_incidents_amount_positive"),
        CheckConstraint("length(currency) = 3", name="ck_payout_recovery_incidents_currency"),
        CheckConstraint("length(dedupe_key) = 64", name="ck_payout_recovery_incidents_dedupe_key"),
        CheckConstraint(
            "(kind = 'confirmed_fraud' AND source_fraud_flag_id IS NOT NULL "
            "AND source_reversal_entry_id IS NOT NULL) OR "
            "(kind = 'duplicate_cash' AND source_fraud_flag_id IS NULL "
            "AND source_reversal_entry_id IS NULL)",
            name="ck_payout_recovery_incidents_source",
        ),
        CheckConstraint(
            "(status = 'contingent' AND exposure_line_id IS NOT NULL "
            "AND resolved_at IS NULL) OR "
            "(status IN ('debt_activated', 'closed') AND resolved_at IS NOT NULL)",
            name="ck_payout_recovery_incidents_resolution",
        ),
        Index("ix_payout_recovery_incidents_ledger", "ledger_entry_id", "created_at"),
        Index("ix_payout_recovery_incidents_exposure", "exposure_line_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    ledger_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT"), nullable=False
    )
    chain_root_line_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_batch_lines.id", ondelete="RESTRICT"), nullable=False
    )
    exposure_line_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_batch_lines.id", ondelete="RESTRICT"), nullable=False
    )
    source_fraud_flag_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fraud_flags.id", ondelete="RESTRICT")
    )
    source_reversal_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT")
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


_RECOVERY_INCIDENT_IDENTITY_FIELDS = frozenset(
    {
        "ledger_entry_id",
        "chain_root_line_id",
        "exposure_line_id",
        "source_fraud_flag_id",
        "source_reversal_entry_id",
        "created_by_user_id",
        "kind",
        "amount",
        "currency",
        "dedupe_key",
        "created_at",
    }
)


@event.listens_for(PayoutRecoveryIncident, "before_update")
def validate_payout_recovery_incident_update(_mapper, _connection, target) -> None:
    state = inspect(target)
    if any(
        state.attrs[field].history.has_changes() for field in _RECOVERY_INCIDENT_IDENTITY_FIELDS
    ):
        raise ValueError("payout recovery incident identity is immutable")
    status_history = state.attrs.status.history
    before = status_history.deleted[0] if status_history.deleted else target.status
    after = status_history.added[0] if status_history.added else target.status
    if status_history.has_changes() and (before, after) not in {
        (
            PayoutRecoveryIncidentStatus.CONTINGENT.value,
            PayoutRecoveryIncidentStatus.DEBT_ACTIVATED.value,
        ),
        (
            PayoutRecoveryIncidentStatus.CONTINGENT.value,
            PayoutRecoveryIncidentStatus.CLOSED.value,
        ),
        (
            PayoutRecoveryIncidentStatus.DEBT_ACTIVATED.value,
            PayoutRecoveryIncidentStatus.CLOSED.value,
        ),
        (
            PayoutRecoveryIncidentStatus.CLOSED.value,
            PayoutRecoveryIncidentStatus.DEBT_ACTIVATED.value,
        ),
    }:
        raise ValueError("payout recovery incident state transition is invalid")


@event.listens_for(PayoutRecoveryIncident, "before_delete")
def reject_payout_recovery_incident_delete(_mapper, _connection, _target) -> None:
    raise ValueError("payout recovery incidents are append-only")


class DriverCurrencyDebtAccount(Base):
    __tablename__ = "driver_currency_debt_accounts"
    __table_args__ = (
        CheckConstraint("length(currency) = 3", name="ck_driver_debt_accounts_currency"),
        CheckConstraint(
            "outstanding_amount >= 0 AND lifetime_incurred_amount >= 0 "
            "AND lifetime_allocated_amount >= 0",
            name="ck_driver_debt_accounts_amounts_non_negative",
        ),
        CheckConstraint(
            "lifetime_incurred_amount = outstanding_amount + lifetime_allocated_amount",
            name="ck_driver_debt_accounts_conservation",
        ),
        UniqueConstraint(
            "driver_profile_id", "currency", name="uq_driver_debt_accounts_driver_currency"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    driver_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    outstanding_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    lifetime_incurred_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    lifetime_allocated_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PayoutDebtObligation(Base):
    __tablename__ = "payout_debt_obligations"
    __table_args__ = (
        CheckConstraint("length(currency) = 3", name="ck_payout_debt_obligations_currency"),
        CheckConstraint(
            "original_amount > 0 AND outstanding_amount >= 0 "
            "AND outstanding_amount <= original_amount",
            name="ck_payout_debt_obligations_amounts",
        ),
        CheckConstraint(
            "source_reversal_entry_id IS NOT NULL OR recovery_incident_id IS NOT NULL",
            name="ck_payout_debt_obligations_source",
        ),
        Index("ix_payout_debt_obligations_account", "debt_account_id", "created_at"),
        UniqueConstraint(
            "recovery_incident_id",
            name="uq_payout_debt_obligations_recovery_incident",
        ),
        Index(
            "uq_payout_debt_obligations_direct_reversal",
            "source_reversal_entry_id",
            unique=True,
            sqlite_where=text("recovery_incident_id IS NULL"),
            postgresql_where=text("recovery_incident_id IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    debt_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_currency_debt_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    source_reversal_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT"),
    )
    recovery_incident_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("payout_recovery_incidents.id", ondelete="RESTRICT")
    )
    correction_order_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("payout_correction_orders.id", ondelete="RESTRICT")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    original_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    outstanding_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayoutDebtPaidSource(Base):
    __tablename__ = "payout_debt_paid_sources"
    __table_args__ = (
        UniqueConstraint(
            "debt_obligation_id",
            "paid_ledger_entry_id",
            name="uq_payout_debt_paid_sources_obligation_entry",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    debt_obligation_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_debt_obligations.id", ondelete="RESTRICT"), nullable=False
    )
    paid_ledger_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayoutDebtSettlement(Base):
    __tablename__ = "payout_debt_settlements"
    __table_args__ = (
        CheckConstraint(
            "original_credit_amount > 0 AND allocated_amount > 0 "
            "AND allocated_amount <= original_credit_amount",
            name="ck_payout_debt_settlements_amounts",
        ),
        CheckConstraint(
            "(allocated_amount = original_credit_amount AND remainder_entry_id IS NULL) OR "
            "(allocated_amount < original_credit_amount AND remainder_entry_id IS NOT NULL)",
            name="ck_payout_debt_settlements_remainder",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_credit_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    remainder_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT"), unique=True
    )
    original_credit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayoutDebtAllocation(Base):
    __tablename__ = "payout_debt_allocations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payout_debt_allocations_amount_positive"),
        UniqueConstraint(
            "settlement_id",
            "debt_obligation_id",
            name="uq_payout_debt_allocations_settlement_obligation",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    settlement_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_debt_settlements.id", ondelete="RESTRICT"), nullable=False
    )
    debt_obligation_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_debt_obligations.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status

from app.adapters.disbursement import (
    DisbursementAdapter,
    DisbursementInstruction,
    DisbursementProviderCapabilities,
    ProviderLookupStatus,
    VerifiedLineEvidence,
)
from app.adapters.disbursement.provider import DisbursementUnavailableError
from app.core.errors import AppError
from app.db.integrity import integrity_constraint_name
from app.models.disbursement import (
    PayoutBatch,
    PayoutBatchLine,
    PayoutBatchLineStatus,
    PayoutBatchStatus,
    PayoutLineReconciliationEvent,
    PayoutSubmissionAttempt,
    PayoutSubmissionClaimAction,
    PayoutSubmissionIntent,
    PayoutSubmissionIntentState,
    PayoutSubmissionObservation,
    PayoutSubmissionObservationOutcome,
)
from app.models.payee import (
    Payee,
    PayeeBankAccount,
    PayeeBankAccountPayoutVerification,
    PayeeBankAccountVersion,
    PayeeVersion,
)
from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
)
from app.models.trip_analytics import FraudFlag
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.fraud_holds import fraud_hold_active_clause, lock_fraud_hold_scope
from app.services.payout_debt import lock_driver_currency_debt_scope

DISBURSEMENT_CLAIM_LEASE = timedelta(minutes=2)


@dataclass(frozen=True, slots=True)
class ClaimedDisbursementIntent:
    intent_id: UUID
    batch_id: UUID
    line_id: UUID
    generation: int
    claim_token: UUID
    action: PayoutSubmissionClaimAction
    idempotency_key: str
    instruction: dict[str, str]
    instruction_fingerprint: str


@dataclass(frozen=True, slots=True)
class DisbursementClaimObservation:
    outcome: PayoutSubmissionObservationOutcome
    provider_submission_reference: str | None = None
    provider_transfer_reference: str | None = None
    error_code: str | None = None


def _error(code: str, message: str, *, http_status: int = status.HTTP_409_CONFLICT) -> AppError:
    return AppError(code, message, status_code=http_status)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


async def create_payout_batch_draft(
    session: AsyncSession, *, currency: str, actor_user_id: UUID
) -> PayoutBatch:
    await require_active_admin(session, actor_user_id)
    normalized = currency.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise _error(
            "PAYOUT_BATCH_CURRENCY_INVALID",
            "Currency must be a three-letter code",
            http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    batch = PayoutBatch(
        status=PayoutBatchStatus.DRAFT,
        currency=normalized,
        total_amount=Decimal("0"),
        created_by_user_id=actor_user_id,
    )
    session.add(batch)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.payout_batch.created",
        entity_type="payout_batch",
        entity_id=str(batch.id),
        metadata={"currency": normalized},
    )
    return batch


async def _frozen_payee_authority(
    session: AsyncSession, entry: EarningsLedgerEntry, payee: Payee
) -> tuple[PayeeVersion, PayeeBankAccountVersion]:
    payee_version = await session.scalar(
        select(PayeeVersion)
        .where(PayeeVersion.payee_id == payee.id)
        .order_by(PayeeVersion.version.desc())
        .limit(1)
    )
    account_version = await session.scalar(
        select(PayeeBankAccountVersion)
        .join(PayeeBankAccount, PayeeBankAccount.id == PayeeBankAccountVersion.bank_account_id)
        .where(PayeeBankAccount.payee_id == payee.id)
        .order_by(PayeeBankAccountVersion.version.desc())
        .limit(1)
    )
    if payee_version is None or account_version is None:
        raise _error(
            "PAYOUT_BANK_ACCOUNT_MISSING",
            "The payee has no verified bank-account version",
        )
    if account_version.payee_version_id != payee_version.id:
        raise _error(
            "PAYOUT_PAYEE_VERSION_STALE",
            "The verified account does not bind the current payee version",
        )
    payout_verification = await session.scalar(
        select(PayeeBankAccountPayoutVerification.id).where(
            PayeeBankAccountPayoutVerification.bank_account_version_id == account_version.id
        )
    )
    if payout_verification is None:
        raise _error(
            "PAYOUT_BANK_ACCOUNT_UNVERIFIED",
            "The current bank-account version has no authorized payout verification",
        )
    return payee_version, account_version


async def reserve_payout_batch(
    session: AsyncSession,
    *,
    batch_id: UUID,
    ledger_entry_ids: tuple[UUID, ...],
    actor_user_id: UUID,
) -> tuple[PayoutBatch, tuple[PayoutBatchLine, ...]]:
    await require_active_admin(session, actor_user_id)
    if not ledger_entry_ids or len(set(ledger_entry_ids)) != len(ledger_entry_ids):
        raise _error(
            "PAYOUT_BATCH_ENTRIES_INVALID",
            "Select one or more distinct ledger entries",
            http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    batch = await session.scalar(
        select(PayoutBatch)
        .where(PayoutBatch.id == batch_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if batch is None:
        raise _error(
            "PAYOUT_BATCH_NOT_FOUND",
            "Payout batch was not found",
            http_status=status.HTTP_404_NOT_FOUND,
        )
    if batch.status != PayoutBatchStatus.DRAFT:
        raise _error("PAYOUT_BATCH_NOT_DRAFT", "Only a draft batch can be reserved")
    if batch.created_by_user_id != actor_user_id:
        raise _error(
            "PAYOUT_BATCH_MAKER_REQUIRED",
            "Only the batch maker can reserve it",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    stubs = (
        await session.execute(
            select(
                EarningsLedgerEntry.id,
                EarningsLedgerEntry.trip_session_id,
                EarningsLedgerEntry.driver_profile_id,
                EarningsLedgerEntry.currency,
            ).where(EarningsLedgerEntry.id.in_(ledger_entry_ids))
        )
    ).all()
    if len(stubs) != len(ledger_entry_ids) or any(row.trip_session_id is None for row in stubs):
        raise _error("PAYOUT_ENTRY_INELIGIBLE", "Every selected entry must belong to a trip")
    for trip_id in sorted({row.trip_session_id for row in stubs}, key=str):
        await lock_fraud_hold_scope(session, trip_id)
    for driver_profile_id, currency in sorted(
        {(row.driver_profile_id, row.currency) for row in stubs},
        key=lambda item: (str(item[0]), item[1]),
    ):
        _, debt_account = await lock_driver_currency_debt_scope(
            session,
            driver_profile_id=driver_profile_id,
            currency=currency,
        )
        if debt_account is not None and debt_account.outstanding_amount > 0:
            raise _error(
                "PAYOUT_DEBT_ALLOCATION_REQUIRED",
                "Carry-forward debt must be allocated before earnings become batchable",
            )

    entries = list(
        (
            await session.scalars(
                select(EarningsLedgerEntry)
                .where(EarningsLedgerEntry.id.in_(ledger_entry_ids))
                .order_by(EarningsLedgerEntry.id)
                .with_for_update()
            )
        ).all()
    )
    payees = list(
        (
            await session.scalars(
                select(Payee)
                .where(
                    Payee.payee_type == "driver",
                    Payee.subject_id.in_({entry.driver_profile_id for entry in entries}),
                )
                .order_by(Payee.id)
                .with_for_update()
            )
        ).all()
    )
    payees_by_subject = {(payee.subject_id, payee.tenant_id): payee for payee in payees}
    lines: list[PayoutBatchLine] = []
    await session.flush()
    for entry in entries:
        held = await session.scalar(
            select(func.count(FraudFlag.id)).where(
                FraudFlag.trip_session_id == entry.trip_session_id,
                fraud_hold_active_clause(),
            )
        )
        if held:
            raise _error("PAYOUT_ENTRY_HELD", "A selected ledger entry has an active fraud hold")
        if (
            entry.status != EarningsLedgerEntryStatus.AVAILABLE
            or entry.entry_type == EarningsLedgerEntryType.REVERSAL
            or entry.amount <= 0
            or entry.currency != batch.currency
        ):
            raise _error(
                "PAYOUT_ENTRY_INELIGIBLE",
                "Every selected entry must be positive, available, payable, "
                "and in batch currency",
            )
        payee = payees_by_subject.get((entry.driver_profile_id, entry.driver_user_id))
        if payee is None:
            raise _error("PAYOUT_PAYEE_MISSING", "The ledger entry has no pilot payee")
        payee_version, account_version = await _frozen_payee_authority(session, entry, payee)
        instruction = {
            "ledger_entry_id": str(entry.id),
            "payee_version_id": str(payee_version.id),
            "bank_account_version_id": str(account_version.id),
            "amount": f"{entry.amount:.2f}",
            "currency": entry.currency,
        }
        instruction_fingerprint = _fingerprint(instruction)
        idempotency_key = _fingerprint(
            {
                "scope": "cardvert-payout-line-v1",
                "batch_id": str(batch.id),
                "instruction_fingerprint": instruction_fingerprint,
            }
        )
        lines.append(
            PayoutBatchLine(
                batch_id=batch.id,
                ledger_entry_id=entry.id,
                payee_version_id=payee_version.id,
                bank_account_version_id=account_version.id,
                amount=entry.amount,
                currency=entry.currency,
                instruction=instruction,
                instruction_fingerprint=instruction_fingerprint,
                idempotency_key=idempotency_key,
                status=PayoutBatchLineStatus.RESERVED,
                reservation_active=True,
            )
        )
    try:
        async with session.begin_nested():
            session.add_all(lines)
            batch.total_amount = sum((line.amount for line in lines), Decimal("0"))
            batch.instruction_set_fingerprint = _fingerprint(
                {
                    "currency": batch.currency,
                    "total_amount": f"{batch.total_amount:.2f}",
                    "line_fingerprints": sorted(
                        line.instruction_fingerprint for line in lines
                    ),
                }
            )
            batch.status = PayoutBatchStatus.RESERVED
            await session.flush()
    except IntegrityError as exc:
        constraint = integrity_constraint_name(exc)
        if constraint != "uq_payout_batch_lines_active_ledger_entry":
            raise
        raise _error(
            "PAYOUT_ENTRY_ALREADY_RESERVED",
            "A selected ledger entry already has an active payout reservation",
        ) from exc
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.payout_batch.reserved",
        entity_type="payout_batch",
        entity_id=str(batch.id),
        metadata={"line_count": len(lines), "currency": batch.currency},
    )
    return batch, tuple(lines)


async def _locked_batch_with_lines(
    session: AsyncSession, batch_id: UUID
) -> tuple[PayoutBatch, tuple[PayoutBatchLine, ...]]:
    batch = await session.scalar(
        select(PayoutBatch).where(PayoutBatch.id == batch_id).with_for_update()
    )
    if batch is None:
        raise _error(
            "PAYOUT_BATCH_NOT_FOUND",
            "Payout batch was not found",
            http_status=status.HTTP_404_NOT_FOUND,
        )
    lines = tuple(
        (
            await session.scalars(
                select(PayoutBatchLine)
                .where(PayoutBatchLine.batch_id == batch.id)
                .order_by(PayoutBatchLine.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    return batch, lines


def _assert_frozen(batch: PayoutBatch, lines: tuple[PayoutBatchLine, ...]) -> None:
    if not lines:
        raise _error("PAYOUT_BATCH_EMPTY", "A payout batch cannot be empty")
    for line in lines:
        if line.instruction_fingerprint != _fingerprint(line.instruction):
            raise _error("PAYOUT_INSTRUCTION_CHANGED", "A frozen payout instruction changed")
        expected_instruction = {
            "ledger_entry_id": str(line.ledger_entry_id),
            "payee_version_id": str(line.payee_version_id),
            "bank_account_version_id": str(line.bank_account_version_id),
            "amount": f"{line.amount:.2f}",
            "currency": line.currency,
        }
        expected_idempotency = _fingerprint(
            {
                "scope": "cardvert-payout-line-v1",
                "batch_id": str(batch.id),
                "instruction_fingerprint": line.instruction_fingerprint,
            }
        )
        if (
            line.instruction != expected_instruction
            or line.idempotency_key != expected_idempotency
            or line.currency != batch.currency
        ):
            raise _error("PAYOUT_INSTRUCTION_CHANGED", "A frozen payout instruction changed")
    total = sum((line.amount for line in lines), Decimal("0"))
    expected = _fingerprint(
        {
            "currency": batch.currency,
            "total_amount": f"{total:.2f}",
            "line_fingerprints": sorted(line.instruction_fingerprint for line in lines),
        }
    )
    if total != batch.total_amount or expected != batch.instruction_set_fingerprint:
        raise _error("PAYOUT_BATCH_CHANGED", "The frozen payout batch snapshot changed")


async def approve_payout_batch(
    session: AsyncSession, *, batch_id: UUID, actor_user_id: UUID
) -> tuple[PayoutBatch, tuple[PayoutBatchLine, ...]]:
    await require_active_admin(session, actor_user_id)
    batch, lines = await _locked_batch_with_lines(session, batch_id)
    if batch.status != PayoutBatchStatus.RESERVED:
        raise _error("PAYOUT_BATCH_NOT_RESERVED", "Only a reserved batch can be approved")
    if batch.created_by_user_id == actor_user_id:
        raise _error(
            "PAYOUT_BATCH_MAKER_CHECKER_REQUIRED",
            "The batch approver must be different from its maker",
            http_status=status.HTTP_403_FORBIDDEN,
        )
    _assert_frozen(batch, lines)
    if batch.approved_by_user_id is not None:
        if batch.approved_by_user_id != actor_user_id:
            raise _error(
                "PAYOUT_BATCH_APPROVAL_CONFLICT",
                "The batch was already approved by another checker",
            )
        return batch, lines
    batch.approved_by_user_id = actor_user_id
    batch.approved_at = datetime.now(UTC)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.payout_batch.approved",
        entity_type="payout_batch",
        entity_id=str(batch.id),
        metadata={"maker_user_id": str(batch.created_by_user_id)},
    )
    return batch, lines


async def submit_payout_batch(
    session: AsyncSession,
    *,
    batch_id: UUID,
    actor_user_id: UUID,
    adapter: DisbursementAdapter,
) -> tuple[PayoutBatch, tuple[PayoutBatchLine, ...]]:
    await require_active_admin(session, actor_user_id)
    batch, lines = await _locked_batch_with_lines(session, batch_id)
    if batch.status not in {PayoutBatchStatus.RESERVED, PayoutBatchStatus.SUBMITTED}:
        raise _error("PAYOUT_BATCH_NOT_RESERVED", "The batch is not ready for submission")
    if batch.approved_by_user_id is None or batch.approved_at is None:
        raise _error("PAYOUT_BATCH_NOT_APPROVED", "A separate admin must approve the batch")
    _assert_frozen(batch, lines)
    capabilities = _submission_capabilities(adapter)
    existing = {
        intent.payout_batch_line_id: intent
        for intent in (
            await session.scalars(
                select(PayoutSubmissionIntent).where(
                    PayoutSubmissionIntent.payout_batch_line_id.in_(
                        [line.id for line in lines]
                    )
                )
            )
        ).all()
    }
    created = 0
    for line in lines:
        intent = existing.get(line.id)
        if intent is not None:
            if (
                intent.provider_name != capabilities.provider_name
                or intent.idempotency_key != line.idempotency_key
                or intent.instruction != line.instruction
                or intent.instruction_fingerprint != line.instruction_fingerprint
            ):
                raise _error(
                    "PAYOUT_SUBMISSION_INTENT_CONFLICT",
                    "The durable payout submission intent conflicts with the frozen line",
                )
            continue
        if line.status != PayoutBatchLineStatus.RESERVED:
            raise _error(
                "PAYOUT_SUBMISSION_INTENT_MISSING",
                "A provider-visible payout line has no durable submission intent",
            )
        session.add(
            PayoutSubmissionIntent(
                payout_batch_line_id=line.id,
                provider_name=capabilities.provider_name,
                idempotency_key=line.idempotency_key,
                instruction=dict(line.instruction),
                instruction_fingerprint=line.instruction_fingerprint,
                requested_by_user_id=actor_user_id,
            )
        )
        created += 1
    await session.flush()
    if created:
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="admin.payout_batch.submission_queued",
            entity_type="payout_batch",
            entity_id=str(batch.id),
            metadata={"line_count": created},
        )
    return batch, lines


def _submission_capabilities(
    adapter: DisbursementAdapter,
) -> DisbursementProviderCapabilities:
    capabilities = adapter.capabilities
    if not (
        capabilities.provider_name
        and capabilities.lookup_by_idempotency_key
        and capabilities.semantic_same_key_idempotency
    ):
        raise _error(
            "DISBURSEMENT_PROVIDER_UNAVAILABLE",
            "Automated disbursement requires same-key idempotency and durable-key lookup",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return capabilities


def _aware_utc(value: datetime) -> datetime:
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).astimezone(UTC)


async def find_due_payout_submission_intent_ids(
    session: AsyncSession, *, limit: int = 100
) -> tuple[UUID, ...]:
    return tuple(
        (
            await session.scalars(
                select(PayoutSubmissionIntent.id)
                .where(
                    or_(
                        PayoutSubmissionIntent.state.in_(
                            [
                                PayoutSubmissionIntentState.PENDING.value,
                                PayoutSubmissionIntentState.QUERY_ONLY.value,
                            ]
                        ),
                        (
                            PayoutSubmissionIntent.state
                            == PayoutSubmissionIntentState.CLAIMED.value
                        )
                        & (PayoutSubmissionIntent.claim_expires_at <= func.now()),
                    )
                )
                .order_by(
                    PayoutSubmissionIntent.updated_at,
                    PayoutSubmissionIntent.id,
                )
                .limit(limit)
            )
        ).all()
    )


async def claim_payout_submission_intent(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    intent_id: UUID,
    adapter: DisbursementAdapter,
) -> ClaimedDisbursementIntent | None:
    capabilities = _submission_capabilities(adapter)
    async with sessionmaker() as session:
        stub = (
            await session.execute(
                select(
                    PayoutSubmissionIntent.payout_batch_line_id,
                    PayoutBatchLine.batch_id,
                )
                .join(
                    PayoutBatchLine,
                    PayoutBatchLine.id == PayoutSubmissionIntent.payout_batch_line_id,
                )
                .where(PayoutSubmissionIntent.id == intent_id)
            )
        ).one_or_none()
        if stub is None:
            return None
        batch, lines = await _locked_batch_with_lines(session, stub.batch_id)
        intent = await session.scalar(
            select(PayoutSubmissionIntent)
            .where(PayoutSubmissionIntent.id == intent_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if intent is None:
            return None
        line = next(item for item in lines if item.id == intent.payout_batch_line_id)
        if (
            intent.state == PayoutSubmissionIntentState.RESOLVED.value
            or line.status != PayoutBatchLineStatus.RESERVED.value
        ):
            return None
        if intent.provider_name != capabilities.provider_name:
            raise _error(
                "DISBURSEMENT_PROVIDER_CHANGED",
                "The configured provider does not own this durable submission intent",
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        now = _aware_utc(await session.scalar(select(func.now())))
        if intent.state == PayoutSubmissionIntentState.CLAIMED.value:
            if (
                intent.claim_expires_at is not None
                and _aware_utc(intent.claim_expires_at) > now
            ):
                return None
            action = PayoutSubmissionClaimAction.QUERY
        elif intent.state == PayoutSubmissionIntentState.QUERY_ONLY.value:
            action = PayoutSubmissionClaimAction.QUERY
        elif intent.state == PayoutSubmissionIntentState.PENDING.value:
            action = PayoutSubmissionClaimAction.SUBMIT
        else:
            return None
        claim_token = uuid4()
        intent.state = PayoutSubmissionIntentState.CLAIMED.value
        intent.generation += 1
        intent.claim_token = claim_token
        intent.claim_action = action.value
        intent.claim_expires_at = now + DISBURSEMENT_CLAIM_LEASE
        attempt = PayoutSubmissionAttempt(
            intent_id=intent.id,
            generation=intent.generation,
            claim_token=claim_token,
            action=action.value,
            idempotency_key=intent.idempotency_key,
            instruction_fingerprint=intent.instruction_fingerprint,
        )
        session.add(attempt)
        await session.commit()
        return ClaimedDisbursementIntent(
            intent_id=intent.id,
            batch_id=batch.id,
            line_id=line.id,
            generation=intent.generation,
            claim_token=claim_token,
            action=action,
            idempotency_key=intent.idempotency_key,
            instruction={str(key): str(value) for key, value in intent.instruction.items()},
            instruction_fingerprint=intent.instruction_fingerprint,
        )


def _clear_disbursement_claim(intent: PayoutSubmissionIntent) -> None:
    intent.claim_token = None
    intent.claim_action = None
    intent.claim_expires_at = None


def _submission_observation_fingerprint(
    claim: ClaimedDisbursementIntent,
    observation: DisbursementClaimObservation,
) -> str:
    return _fingerprint(
        {
            "intent_id": str(claim.intent_id),
            "generation": claim.generation,
            "claim_token": str(claim.claim_token),
            "idempotency_key": claim.idempotency_key,
            "instruction_fingerprint": claim.instruction_fingerprint,
            "outcome": observation.outcome.value,
            "provider_submission_reference": observation.provider_submission_reference,
            "provider_transfer_reference": observation.provider_transfer_reference,
            "error_code": observation.error_code,
        }
    )


def _provider_reference_lock_id(provider_transfer_reference: str) -> int:
    raw = hashlib.sha256(provider_transfer_reference.encode()).digest()[:8]
    return int.from_bytes(raw, byteorder="big", signed=True)


async def _resolve_payout_submission_claim(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    claim: ClaimedDisbursementIntent,
    observation: DisbursementClaimObservation,
) -> str:
    async with sessionmaker() as session:
        batch, lines = await _locked_batch_with_lines(session, claim.batch_id)
        intent = await session.scalar(
            select(PayoutSubmissionIntent)
            .where(PayoutSubmissionIntent.id == claim.intent_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if intent is None:
            return "stale"
        now = _aware_utc(await session.scalar(select(func.now())))
        if (
            intent.state != PayoutSubmissionIntentState.CLAIMED.value
            or intent.generation != claim.generation
            or intent.claim_token != claim.claim_token
            or intent.claim_action != claim.action.value
            or intent.claim_expires_at is None
            or _aware_utc(intent.claim_expires_at) <= now
        ):
            return "stale"
        attempt = await session.scalar(
            select(PayoutSubmissionAttempt).where(
                PayoutSubmissionAttempt.intent_id == claim.intent_id,
                PayoutSubmissionAttempt.generation == claim.generation,
                PayoutSubmissionAttempt.claim_token == claim.claim_token,
            )
        )
        if attempt is None:
            raise RuntimeError("A committed disbursement claim has no durable attempt")
        line = next(item for item in lines if item.id == intent.payout_batch_line_id)
        final_observation = observation
        resolved = observation.outcome in {
            PayoutSubmissionObservationOutcome.SUBMITTED,
            PayoutSubmissionObservationOutcome.FOUND,
        }
        if resolved:
            provider_reference = observation.provider_transfer_reference
            if not provider_reference or not observation.provider_submission_reference:
                resolved = False
                final_observation = DisbursementClaimObservation(
                    outcome=PayoutSubmissionObservationOutcome.UNKNOWN,
                    error_code="provider_response_invalid",
                )
            else:
                if session.bind is not None and session.bind.dialect.name == "postgresql":
                    await session.execute(
                        select(
                            func.pg_advisory_xact_lock(
                                _provider_reference_lock_id(provider_reference)
                            )
                        )
                    )
                conflicting_line_id = await session.scalar(
                    select(PayoutBatchLine.id).where(
                        PayoutBatchLine.provider_transfer_reference == provider_reference,
                        PayoutBatchLine.id != line.id,
                    )
                )
                if conflicting_line_id is not None:
                    resolved = False
                    final_observation = DisbursementClaimObservation(
                        outcome=observation.outcome,
                        provider_submission_reference=(
                            observation.provider_submission_reference
                        ),
                        provider_transfer_reference=provider_reference,
                        error_code="provider_transfer_reference_duplicate",
                    )
        observed_at = now
        session.add(
            PayoutSubmissionObservation(
                attempt_id=attempt.id,
                intent_id=intent.id,
                generation=intent.generation,
                idempotency_key=intent.idempotency_key,
                instruction_fingerprint=intent.instruction_fingerprint,
                outcome=final_observation.outcome.value,
                provider_submission_reference=(
                    final_observation.provider_submission_reference
                ),
                provider_transfer_reference=final_observation.provider_transfer_reference,
                evidence_fingerprint=_submission_observation_fingerprint(
                    claim, final_observation
                ),
                error_code=final_observation.error_code,
                observed_at=observed_at,
            )
        )
        first_provider_resolution = batch.submitted_at is None
        if resolved:
            intent.state = PayoutSubmissionIntentState.RESOLVED.value
            intent.provider_submission_reference = (
                final_observation.provider_submission_reference
            )
            intent.provider_transfer_reference = final_observation.provider_transfer_reference
            intent.resolved_at = observed_at
            line.provider_transfer_reference = final_observation.provider_transfer_reference
            line.status = PayoutBatchLineStatus.SUBMITTED.value
            batch.provider_submission_reference = (
                batch.provider_submission_reference
                or final_observation.provider_submission_reference
            )
            batch.submitted_at = batch.submitted_at or observed_at
            batch.status = _derive_batch_status(lines).value
        elif final_observation.outcome == PayoutSubmissionObservationOutcome.NOT_FOUND:
            intent.state = PayoutSubmissionIntentState.PENDING.value
        else:
            intent.state = PayoutSubmissionIntentState.QUERY_ONLY.value
        _clear_disbursement_claim(intent)
        await session.flush()
        if resolved and first_provider_resolution:
            await create_audit_event(
                session,
                actor_user_id=intent.requested_by_user_id,
                action="admin.payout_batch.submitted",
                entity_type="payout_batch",
                entity_id=str(batch.id),
                metadata={"line_count": len(lines)},
            )
        await session.commit()
        return intent.state


async def process_payout_submission_intent(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    intent_id: UUID,
    adapter: DisbursementAdapter,
) -> str:
    claim = await claim_payout_submission_intent(
        sessionmaker,
        intent_id=intent_id,
        adapter=adapter,
    )
    if claim is None:
        return "skipped"
    if claim.action == PayoutSubmissionClaimAction.SUBMIT:
        try:
            receipt = await adapter.submit_batch(
                batch_id=str(claim.batch_id),
                instructions=(
                    DisbursementInstruction(
                        line_id=str(claim.line_id),
                        idempotency_key=claim.idempotency_key,
                        instruction=claim.instruction,
                        instruction_fingerprint=claim.instruction_fingerprint,
                    ),
                ),
            )
            provider_transfer_reference = receipt.line_references.get(str(claim.line_id))
            if (
                not receipt.provider_reference
                or set(receipt.line_references) != {str(claim.line_id)}
                or not provider_transfer_reference
            ):
                raise ValueError("Provider did not return the claimed line reference")
            observation = DisbursementClaimObservation(
                outcome=PayoutSubmissionObservationOutcome.SUBMITTED,
                provider_submission_reference=receipt.provider_reference,
                provider_transfer_reference=provider_transfer_reference,
            )
        except Exception as exc:
            observation = DisbursementClaimObservation(
                outcome=PayoutSubmissionObservationOutcome.UNKNOWN,
                error_code=type(exc).__name__.lower(),
            )
    else:
        try:
            lookup = await adapter.lookup_line(
                idempotency_key=claim.idempotency_key,
                instruction_fingerprint=claim.instruction_fingerprint,
            )
            if lookup.status == ProviderLookupStatus.FOUND:
                observation = DisbursementClaimObservation(
                    outcome=PayoutSubmissionObservationOutcome.FOUND,
                    provider_submission_reference=lookup.provider_submission_reference,
                    provider_transfer_reference=lookup.provider_transfer_reference,
                )
            elif lookup.status == ProviderLookupStatus.NOT_FOUND:
                observation = DisbursementClaimObservation(
                    outcome=PayoutSubmissionObservationOutcome.NOT_FOUND
                )
            else:
                observation = DisbursementClaimObservation(
                    outcome=PayoutSubmissionObservationOutcome.UNKNOWN
                )
        except Exception as exc:
            observation = DisbursementClaimObservation(
                outcome=PayoutSubmissionObservationOutcome.UNKNOWN,
                error_code=type(exc).__name__.lower(),
            )
    return await _resolve_payout_submission_claim(
        sessionmaker,
        claim=claim,
        observation=observation,
    )


def _derive_batch_status(lines: tuple[PayoutBatchLine, ...]) -> PayoutBatchStatus:
    statuses = {line.status for line in lines}
    if statuses == {PayoutBatchLineStatus.SUCCEEDED}:
        return PayoutBatchStatus.COMPLETED
    if statuses == {PayoutBatchLineStatus.FAILED}:
        return PayoutBatchStatus.FAILED
    if PayoutBatchLineStatus.SUBMITTED in statuses:
        return PayoutBatchStatus.SUBMITTED
    if statuses == {PayoutBatchLineStatus.VOID}:
        return PayoutBatchStatus.VOID
    return PayoutBatchStatus.RECONCILED


async def _apply_verified_line_evidence(
    session: AsyncSession,
    *,
    evidence: VerifiedLineEvidence,
    source: str,
    actor_user_id: UUID | None,
) -> tuple[PayoutBatch, tuple[PayoutBatchLine, ...], PayoutLineReconciliationEvent]:
    if source not in {"webhook", "poll"}:
        raise ValueError("Unknown provider evidence source")
    if source == "webhook" and actor_user_id is not None:
        raise ValueError("Webhook evidence must use the system actor")
    if source == "poll" and actor_user_id is None:
        raise ValueError("Poll evidence must use an authenticated admin actor")
    if source == "poll":
        await require_active_admin(session, actor_user_id)
    stub = (
        await session.execute(
            select(PayoutBatchLine.id, PayoutBatchLine.batch_id).where(
                PayoutBatchLine.provider_transfer_reference == evidence.provider_transfer_reference
            )
        )
    ).one_or_none()
    if stub is None:
        raise _error(
            "PAYOUT_PROVIDER_LINE_NOT_FOUND",
            "The verified provider reference is not bound to a payout line",
            http_status=status.HTTP_404_NOT_FOUND,
        )
    batch, lines = await _locked_batch_with_lines(session, stub.batch_id)
    line = next(item for item in lines if item.id == stub.id)
    if actor_user_id is not None and actor_user_id in {
        batch.created_by_user_id,
        batch.approved_by_user_id,
    }:
        raise _error(
            "PAYOUT_RECONCILER_SEPARATION_REQUIRED",
            "The reconciler must differ from the batch maker and approver",
            http_status=status.HTTP_403_FORBIDDEN,
        )
    if line.status not in {
        PayoutBatchLineStatus.SUBMITTED,
        PayoutBatchLineStatus.FAILED,
        PayoutBatchLineStatus.SUCCEEDED,
    }:
        raise _error("PAYOUT_LINE_NOT_SUBMITTED", "The payout line is not reconcilable")
    existing_event = await session.scalar(
        select(PayoutLineReconciliationEvent).where(
            PayoutLineReconciliationEvent.provider_event_id == evidence.provider_event_id
        )
    )
    if existing_event is not None:
        if (
            existing_event.line_id != line.id
            or existing_event.outcome != evidence.outcome
            or existing_event.evidence_fingerprint != evidence.evidence_fingerprint
        ):
            raise _error(
                "PAYOUT_PROVIDER_EVENT_REPLAY_CONFLICT",
                "The provider event ID was replayed with conflicting evidence",
            )
        return batch, lines, existing_event

    occurred_at = _aware_utc(evidence.occurred_at)
    last_evidence_at = (
        _aware_utc(line.last_provider_evidence_at)
        if line.last_provider_evidence_at is not None
        else None
    )
    applied = False
    if line.status != PayoutBatchLineStatus.SUCCEEDED and (
        last_evidence_at is None or occurred_at >= last_evidence_at
    ):
        if evidence.outcome == PayoutBatchLineStatus.SUCCEEDED:
            ledger_authority = (
                await session.execute(
                    select(
                        EarningsLedgerEntry.driver_profile_id,
                        EarningsLedgerEntry.currency,
                    ).where(EarningsLedgerEntry.id == line.ledger_entry_id)
                )
            ).one_or_none()
            if ledger_authority is None:
                raise _error(
                    "PAYOUT_LEDGER_FINALITY_CONFLICT",
                    "The payout ledger entry no longer exists",
                )
            await lock_driver_currency_debt_scope(
                session,
                driver_profile_id=ledger_authority.driver_profile_id,
                currency=ledger_authority.currency,
            )
            ledger = await session.scalar(
                select(EarningsLedgerEntry)
                .where(EarningsLedgerEntry.id == line.ledger_entry_id)
                .with_for_update()
            )
            if ledger is None or ledger.status not in {
                EarningsLedgerEntryStatus.AVAILABLE,
                EarningsLedgerEntryStatus.PAID,
            }:
                raise _error(
                    "PAYOUT_LEDGER_FINALITY_CONFLICT",
                    "The payout ledger entry is not available for cash-paid finality",
                )
            if ledger.status != EarningsLedgerEntryStatus.PAID:
                ledger.status = EarningsLedgerEntryStatus.PAID
                line.status = PayoutBatchLineStatus.SUCCEEDED
                line.reconciled_by_user_id = actor_user_id
                line.reconciled_at = datetime.now(UTC)
                applied = True
        elif evidence.outcome == PayoutBatchLineStatus.FAILED:
            ledger_status = await session.scalar(
                select(EarningsLedgerEntry.status)
                .where(EarningsLedgerEntry.id == line.ledger_entry_id)
                .with_for_update()
            )
            if ledger_status == EarningsLedgerEntryStatus.PAID:
                raise _error(
                    "PAYOUT_PAID_HISTORY_IMMUTABLE",
                    "Verified cash-paid history cannot be changed by failure evidence",
                )
            if line.status != PayoutBatchLineStatus.FAILED:
                line.status = PayoutBatchLineStatus.FAILED
                line.reconciled_by_user_id = actor_user_id
                line.reconciled_at = datetime.now(UTC)
                applied = True
        else:
            raise _error(
                "PAYOUT_PROVIDER_OUTCOME_INVALID",
                "Verified provider evidence has an unsupported outcome",
                http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
    if last_evidence_at is None or occurred_at > last_evidence_at:
        line.last_provider_evidence_at = occurred_at
    event = PayoutLineReconciliationEvent(
        line_id=line.id,
        provider_event_id=evidence.provider_event_id,
        source=source,
        outcome=evidence.outcome,
        evidence_fingerprint=evidence.evidence_fingerprint,
        provider_occurred_at=occurred_at,
        applied=applied,
        reconciled_by_user_id=actor_user_id,
    )
    session.add(event)
    batch.status = _derive_batch_status(lines)
    await session.flush()
    if applied:
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="provider.payout_line.reconciled",
            entity_type="payout_batch_line",
            entity_id=str(line.id),
            metadata={"source": source, "outcome": evidence.outcome},
        )
    return batch, lines, event


async def reconcile_payout_webhook(
    session: AsyncSession,
    *,
    payload: bytes,
    signature: str,
    adapter: DisbursementAdapter,
) -> tuple[PayoutBatch, tuple[PayoutBatchLine, ...], PayoutLineReconciliationEvent]:
    try:
        evidence = await adapter.verify_webhook(payload=payload, signature=signature)
    except DisbursementUnavailableError as exc:
        raise _error(
            "DISBURSEMENT_PROVIDER_UNAVAILABLE",
            "Provider webhook verification is not configured",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    except ValueError as exc:
        raise _error(
            "DISBURSEMENT_WEBHOOK_INVALID",
            "Provider webhook verification failed",
            http_status=status.HTTP_401_UNAUTHORIZED,
        ) from exc
    return await _apply_verified_line_evidence(
        session, evidence=evidence, source="webhook", actor_user_id=None
    )


async def poll_payout_line(
    session: AsyncSession,
    *,
    line_id: UUID,
    actor_user_id: UUID,
    adapter: DisbursementAdapter,
) -> tuple[PayoutBatch, tuple[PayoutBatchLine, ...], PayoutLineReconciliationEvent]:
    if session.new or session.dirty or session.deleted:
        raise RuntimeError("Provider polling requires a clean database unit of work")
    await require_active_admin(session, actor_user_id)
    authority = (
        await session.execute(
            select(
                PayoutBatchLine.provider_transfer_reference,
                PayoutBatch.created_by_user_id,
                PayoutBatch.approved_by_user_id,
            )
            .join(PayoutBatch, PayoutBatch.id == PayoutBatchLine.batch_id)
            .where(PayoutBatchLine.id == line_id)
        )
    ).one_or_none()
    if authority is None or authority.provider_transfer_reference is None:
        raise _error(
            "PAYOUT_PROVIDER_LINE_NOT_FOUND",
            "The payout line has no provider reference",
            http_status=status.HTTP_404_NOT_FOUND,
        )
    if actor_user_id in {
        authority.created_by_user_id,
        authority.approved_by_user_id,
    }:
        raise _error(
            "PAYOUT_RECONCILER_SEPARATION_REQUIRED",
            "The reconciler must differ from the batch maker and approver",
            http_status=status.HTTP_403_FORBIDDEN,
        )
    provider_transfer_reference = authority.provider_transfer_reference
    await session.rollback()
    try:
        evidence = await adapter.poll_line(
            provider_transfer_reference=provider_transfer_reference
        )
    except DisbursementUnavailableError as exc:
        raise _error(
            "DISBURSEMENT_PROVIDER_UNAVAILABLE",
            "Authenticated provider polling is not configured",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    except ValueError as exc:
        raise _error(
            "DISBURSEMENT_POLL_FAILED",
            "Authenticated provider polling failed",
            http_status=status.HTTP_502_BAD_GATEWAY,
        ) from exc
    return await _apply_verified_line_evidence(
        session, evidence=evidence, source="poll", actor_user_id=actor_user_id
    )


async def retry_failed_payout_lines(
    session: AsyncSession,
    *,
    batch_id: UUID,
    actor_user_id: UUID,
    adapter: DisbursementAdapter,
) -> tuple[PayoutBatch, tuple[PayoutBatchLine, ...]]:
    await require_active_admin(session, actor_user_id)
    batch, lines = await _locked_batch_with_lines(session, batch_id)
    failed_lines = tuple(line for line in lines if line.status == PayoutBatchLineStatus.FAILED)
    if not failed_lines:
        raise _error("PAYOUT_FAILED_LINES_MISSING", "The batch has no failed lines to retry")
    _assert_frozen(batch, lines)
    _submission_capabilities(adapter)
    raise _error(
        "PAYOUT_RESOLVED_LINES_NOT_RETRYABLE",
        "Provider-resolved failed lines cannot be replayed; create a governed replacement",
    )


async def void_payout_batch(
    session: AsyncSession, *, batch_id: UUID, actor_user_id: UUID
) -> tuple[PayoutBatch, tuple[PayoutBatchLine, ...]]:
    await require_active_admin(session, actor_user_id)
    batch, lines = await _locked_batch_with_lines(session, batch_id)
    submission_intents = int(
        await session.scalar(
            select(func.count(PayoutSubmissionIntent.id)).where(
                PayoutSubmissionIntent.payout_batch_line_id.in_([line.id for line in lines])
            )
        )
        or 0
    )
    if batch.status != PayoutBatchStatus.RESERVED or any(
        line.status != PayoutBatchLineStatus.RESERVED
        or line.provider_transfer_reference is not None
        for line in lines
    ) or submission_intents:
        raise _error(
            "PAYOUT_BATCH_VOID_UNSAFE",
            "Only a pre-provider reserved batch can be voided",
        )
    ledger_entries = list(
        (
            await session.scalars(
                select(EarningsLedgerEntry)
                .where(EarningsLedgerEntry.id.in_([line.ledger_entry_id for line in lines]))
                .order_by(EarningsLedgerEntry.id)
                .with_for_update()
            )
        ).all()
    )
    if len(ledger_entries) != len(lines) or any(
        entry.status != EarningsLedgerEntryStatus.AVAILABLE for entry in ledger_entries
    ):
        raise _error(
            "PAYOUT_BATCH_VOID_UNSAFE",
            "The batch contains a provider-final or cash-final ledger entry",
        )
    for line in lines:
        line.status = PayoutBatchLineStatus.VOID
        line.reservation_active = False
    batch.status = PayoutBatchStatus.VOID
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.payout_batch.voided",
        entity_type="payout_batch",
        entity_id=str(batch.id),
        metadata={"released_line_count": len(lines)},
    )
    return batch, lines


async def get_payout_batch(
    session: AsyncSession, batch_id: UUID
) -> tuple[PayoutBatch, tuple[PayoutBatchLine, ...]]:
    return await _locked_batch_with_lines(session, batch_id)


async def list_payout_batches(
    session: AsyncSession, *, limit: int, offset: int
) -> tuple[list[tuple[PayoutBatch, tuple[PayoutBatchLine, ...]]], int]:
    total = int(await session.scalar(select(func.count()).select_from(PayoutBatch)) or 0)
    batches = list(
        (
            await session.scalars(
                select(PayoutBatch)
                .order_by(PayoutBatch.created_at.desc(), PayoutBatch.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    batch_ids = [batch.id for batch in batches]
    lines = (
        list(
            (
                await session.scalars(
                    select(PayoutBatchLine)
                    .where(PayoutBatchLine.batch_id.in_(batch_ids))
                    .order_by(PayoutBatchLine.id)
                )
            ).all()
        )
        if batch_ids
        else []
    )
    lines_by_batch: dict[UUID, list[PayoutBatchLine]] = {}
    for line in lines:
        lines_by_batch.setdefault(line.batch_id, []).append(line)
    return [(batch, tuple(lines_by_batch.get(batch.id, []))) for batch in batches], total

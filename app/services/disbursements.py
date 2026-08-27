import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.adapters.disbursement import (
    DisbursementAdapter,
    DisbursementInstruction,
    VerifiedLineEvidence,
)
from app.adapters.disbursement.provider import DisbursementUnavailableError
from app.core.errors import AppError
from app.models.disbursement import (
    PayoutBatch,
    PayoutBatchLine,
    PayoutBatchLineStatus,
    PayoutBatchStatus,
    PayoutLineReconciliationEvent,
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
from app.models.user import User, UserRole, UserStatus
from app.services.audit import create_audit_event
from app.services.fraud_holds import fraud_hold_active_clause, lock_fraud_hold_scope
from app.services.payout_debt import lock_driver_currency_debt_scope


def _error(code: str, message: str, *, http_status: int = status.HTTP_409_CONFLICT) -> AppError:
    return AppError(code, message, status_code=http_status)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _violated_constraint(exc: IntegrityError) -> str | None:
    candidates = (exc.orig, getattr(exc.orig, "__cause__", None))
    return next(
        (
            str(name)
            for candidate in candidates
            if candidate is not None
            if (name := getattr(candidate, "constraint_name", None)) is not None
        ),
        None,
    )


async def _active_admin(session: AsyncSession, actor_user_id: UUID) -> None:
    actor = await session.get(User, actor_user_id)
    if actor is None or actor.role != UserRole.ADMIN or actor.status != UserStatus.ACTIVE:
        raise _error(
            "PAYOUT_BATCH_ADMIN_REQUIRED",
            "An active admin is required",
            http_status=status.HTTP_403_FORBIDDEN,
        )


async def create_payout_batch_draft(
    session: AsyncSession, *, currency: str, actor_user_id: UUID
) -> PayoutBatch:
    await _active_admin(session, actor_user_id)
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
    await _active_admin(session, actor_user_id)
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
                "Every selected entry must be positive, available, payable, and in batch currency",
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
        line = PayoutBatchLine(
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
        session.add(line)
        lines.append(line)
    batch.total_amount = sum((line.amount for line in lines), Decimal("0"))
    batch.instruction_set_fingerprint = _fingerprint(
        {
            "currency": batch.currency,
            "total_amount": f"{batch.total_amount:.2f}",
            "line_fingerprints": sorted(line.instruction_fingerprint for line in lines),
        }
    )
    batch.status = PayoutBatchStatus.RESERVED
    try:
        await session.flush()
    except IntegrityError as exc:
        constraint = _violated_constraint(exc)
        await session.rollback()
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
    await _active_admin(session, actor_user_id)
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
    await _active_admin(session, actor_user_id)
    batch, lines = await _locked_batch_with_lines(session, batch_id)
    if batch.status not in {PayoutBatchStatus.RESERVED, PayoutBatchStatus.SUBMITTED}:
        raise _error("PAYOUT_BATCH_NOT_RESERVED", "The batch is not ready for submission")
    if batch.approved_by_user_id is None or batch.approved_at is None:
        raise _error("PAYOUT_BATCH_NOT_APPROVED", "A separate admin must approve the batch")
    _assert_frozen(batch, lines)
    instructions = tuple(
        DisbursementInstruction(
            line_id=str(line.id),
            idempotency_key=line.idempotency_key,
            instruction={str(key): str(value) for key, value in line.instruction.items()},
        )
        for line in lines
    )
    try:
        receipt = await adapter.submit_batch(batch_id=str(batch.id), instructions=instructions)
    except DisbursementUnavailableError as exc:
        raise _error(
            "DISBURSEMENT_PROVIDER_UNAVAILABLE",
            "Automated disbursement submission is not configured",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    if batch.provider_submission_reference not in {None, receipt.provider_reference}:
        raise _error(
            "DISBURSEMENT_PROVIDER_REPLAY_CONFLICT",
            "The provider returned a conflicting submission reference",
        )
    expected_line_ids = {str(line.id) for line in lines}
    if set(receipt.line_references) != expected_line_ids or len(
        set(receipt.line_references.values())
    ) != len(lines):
        raise _error(
            "DISBURSEMENT_PROVIDER_RESPONSE_INVALID",
            "The provider did not return one unique reference per payout line",
            http_status=status.HTTP_502_BAD_GATEWAY,
        )
    for line in lines:
        provider_reference = receipt.line_references[str(line.id)]
        if not provider_reference or line.provider_transfer_reference not in {
            None,
            provider_reference,
        }:
            raise _error(
                "DISBURSEMENT_PROVIDER_REPLAY_CONFLICT",
                "The provider returned a conflicting line reference",
            )
        line.provider_transfer_reference = provider_reference
        if line.status == PayoutBatchLineStatus.RESERVED:
            line.status = PayoutBatchLineStatus.SUBMITTED
    replay = batch.status == PayoutBatchStatus.SUBMITTED
    batch.status = PayoutBatchStatus.SUBMITTED
    batch.provider_submission_reference = receipt.provider_reference
    batch.submitted_at = batch.submitted_at or datetime.now(UTC)
    try:
        await session.flush()
    except IntegrityError as exc:
        constraint = _violated_constraint(exc)
        await session.rollback()
        if constraint != "uq_payout_batch_lines_provider_transfer_reference":
            raise
        raise _error(
            "DISBURSEMENT_PROVIDER_REFERENCE_DUPLICATE",
            "The provider transfer reference is already bound to another payout line",
        ) from exc
    if not replay:
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="admin.payout_batch.submitted",
            entity_type="payout_batch",
            entity_id=str(batch.id),
            metadata={"line_count": len(lines)},
        )
    return batch, lines


def _aware_utc(value: datetime) -> datetime:
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).astimezone(UTC)


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
        await _active_admin(session, actor_user_id)
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
    await _active_admin(session, actor_user_id)
    stub = await session.get(PayoutBatchLine, line_id)
    if stub is None or stub.provider_transfer_reference is None:
        raise _error(
            "PAYOUT_PROVIDER_LINE_NOT_FOUND",
            "The payout line has no provider reference",
            http_status=status.HTTP_404_NOT_FOUND,
        )
    batch, lines = await _locked_batch_with_lines(session, stub.batch_id)
    line = next(item for item in lines if item.id == line_id)
    if actor_user_id in {batch.created_by_user_id, batch.approved_by_user_id}:
        raise _error(
            "PAYOUT_RECONCILER_SEPARATION_REQUIRED",
            "The reconciler must differ from the batch maker and approver",
            http_status=status.HTTP_403_FORBIDDEN,
        )
    try:
        evidence = await adapter.poll_line(
            provider_transfer_reference=line.provider_transfer_reference
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
    await _active_admin(session, actor_user_id)
    batch, lines = await _locked_batch_with_lines(session, batch_id)
    failed_lines = tuple(line for line in lines if line.status == PayoutBatchLineStatus.FAILED)
    if not failed_lines:
        raise _error("PAYOUT_FAILED_LINES_MISSING", "The batch has no failed lines to retry")
    _assert_frozen(batch, lines)
    instructions = tuple(
        DisbursementInstruction(
            line_id=str(line.id),
            idempotency_key=line.idempotency_key,
            instruction={str(key): str(value) for key, value in line.instruction.items()},
        )
        for line in failed_lines
    )
    try:
        receipt = await adapter.submit_batch(batch_id=str(batch.id), instructions=instructions)
    except DisbursementUnavailableError as exc:
        raise _error(
            "DISBURSEMENT_PROVIDER_UNAVAILABLE",
            "Automated disbursement submission is not configured",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    if set(receipt.line_references) != {str(line.id) for line in failed_lines}:
        raise _error(
            "DISBURSEMENT_PROVIDER_RESPONSE_INVALID",
            "The provider did not return every retried payout line",
            http_status=status.HTTP_502_BAD_GATEWAY,
        )
    for line in failed_lines:
        if receipt.line_references[str(line.id)] != line.provider_transfer_reference:
            raise _error(
                "DISBURSEMENT_PROVIDER_REPLAY_CONFLICT",
                "A retry changed the frozen provider line reference",
            )
        line.status = PayoutBatchLineStatus.SUBMITTED
        line.reconciled_by_user_id = None
        line.reconciled_at = None
    batch.status = PayoutBatchStatus.SUBMITTED
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.payout_batch.failed_lines_retried",
        entity_type="payout_batch",
        entity_id=str(batch.id),
        metadata={"line_count": len(failed_lines)},
    )
    return batch, lines


async def void_payout_batch(
    session: AsyncSession, *, batch_id: UUID, actor_user_id: UUID
) -> tuple[PayoutBatch, tuple[PayoutBatchLine, ...]]:
    await _active_admin(session, actor_user_id)
    batch, lines = await _locked_batch_with_lines(session, batch_id)
    if batch.status != PayoutBatchStatus.RESERVED or any(
        line.status != PayoutBatchLineStatus.RESERVED
        or line.provider_transfer_reference is not None
        for line in lines
    ):
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

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
)
from app.adapters.disbursement.provider import DisbursementUnavailableError
from app.core.errors import AppError
from app.models.disbursement import PayoutBatch, PayoutBatchLine, PayoutBatchStatus
from app.models.payee import Payee, PayeeBankAccount, PayeeBankAccountVersion, PayeeVersion
from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
)
from app.models.trip_analytics import FraudFlag
from app.models.user import User, UserRole, UserStatus
from app.services.audit import create_audit_event
from app.services.fraud_holds import fraud_hold_active_clause, lock_fraud_hold_scope


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
        select(PayoutBatch).where(PayoutBatch.id == batch_id).with_for_update()
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
            select(EarningsLedgerEntry.id, EarningsLedgerEntry.trip_session_id).where(
                EarningsLedgerEntry.id.in_(ledger_entry_ids)
            )
        )
    ).all()
    if len(stubs) != len(ledger_entry_ids) or any(row.trip_session_id is None for row in stubs):
        raise _error("PAYOUT_ENTRY_INELIGIBLE", "Every selected entry must belong to a trip")
    for trip_id in sorted({row.trip_session_id for row in stubs}, key=str):
        await lock_fraud_hold_scope(session, trip_id)

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
    replay = batch.status == PayoutBatchStatus.SUBMITTED
    batch.status = PayoutBatchStatus.SUBMITTED
    batch.provider_submission_reference = receipt.provider_reference
    batch.submitted_at = batch.submitted_at or datetime.now(UTC)
    await session.flush()
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


async def get_payout_batch(
    session: AsyncSession, batch_id: UUID
) -> tuple[PayoutBatch, tuple[PayoutBatchLine, ...]]:
    return await _locked_batch_with_lines(session, batch_id)


async def list_payout_batches(
    session: AsyncSession, *, limit: int, offset: int
) -> tuple[list[PayoutBatch], int]:
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
    return batches, total

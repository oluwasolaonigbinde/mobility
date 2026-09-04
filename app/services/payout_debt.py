import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.disbursement import (
    DriverCurrencyDebtAccount,
    PayoutBatchLine,
    PayoutBatchLineStatus,
    PayoutDebtAllocation,
    PayoutDebtObligation,
    PayoutDebtPaidSource,
    PayoutDebtSettlement,
    PayoutRecoveryIncident,
    PayoutRecoveryIncidentKind,
    PayoutRecoveryIncidentStatus,
    PayoutSubmissionIntent,
    PayoutSubmissionIntentState,
)
from app.models.driver import DriverProfile
from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
)
from app.services.audit import create_audit_event

MONEY = Decimal("0.01")


def _money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DriverMoneyBalance:
    driver_profile_id: UUID
    currency: str
    earned_net: Decimal
    released_available: Decimal
    reserved: Decimal
    in_flight: Decimal
    terminal_failed: Decimal
    cash_paid: Decimal
    carry_forward_debt: Decimal
    batch_payable: Decimal


@dataclass(frozen=True)
class DebtAllocationResult:
    balance: DriverMoneyBalance
    settlement_ids: tuple[UUID, ...]
    remainder_entry_ids: tuple[UUID, ...]


def _recovery_incident_key(*parts: object) -> str:
    return hashlib.sha256(":".join(str(part) for part in parts).encode()).hexdigest()


async def get_or_create_recovery_incident(
    session: AsyncSession,
    *,
    kind: PayoutRecoveryIncidentKind,
    ledger_entry: EarningsLedgerEntry,
    amount: Decimal,
    exposure_line_id: UUID,
    chain_root_line_id: UUID,
    created_by_user_id: UUID,
    dedupe_parts: tuple[object, ...],
    source_fraud_flag_id: UUID | None = None,
    source_reversal_entry_id: UUID | None = None,
) -> PayoutRecoveryIncident:
    normalized_amount = _money(amount)
    dedupe_key = _recovery_incident_key("cardvert-recovery-v1", *dedupe_parts)
    incident = await session.scalar(
        select(PayoutRecoveryIncident)
        .where(PayoutRecoveryIncident.dedupe_key == dedupe_key)
        .with_for_update()
    )
    expected = (
        kind.value,
        ledger_entry.id,
        normalized_amount,
        ledger_entry.currency,
        exposure_line_id,
        chain_root_line_id,
        source_fraud_flag_id,
        source_reversal_entry_id,
        created_by_user_id,
    )
    if incident is not None:
        actual = (
            incident.kind,
            incident.ledger_entry_id,
            incident.amount,
            incident.currency,
            incident.exposure_line_id,
            incident.chain_root_line_id,
            incident.source_fraud_flag_id,
            incident.source_reversal_entry_id,
            incident.created_by_user_id,
        )
        if actual != expected:
            raise RuntimeError("Recovery incident replay conflicts with immutable authority")
        return incident
    incident = PayoutRecoveryIncident(
        ledger_entry_id=ledger_entry.id,
        chain_root_line_id=chain_root_line_id,
        exposure_line_id=exposure_line_id,
        source_fraud_flag_id=source_fraud_flag_id,
        source_reversal_entry_id=source_reversal_entry_id,
        created_by_user_id=created_by_user_id,
        kind=kind.value,
        status=PayoutRecoveryIncidentStatus.CONTINGENT.value,
        amount=normalized_amount,
        currency=ledger_entry.currency,
        dedupe_key=dedupe_key,
    )
    session.add(incident)
    await session.flush()
    return incident


async def activate_recovery_incident_debt(
    session: AsyncSession,
    *,
    incident: PayoutRecoveryIncident,
    resolved_at: datetime,
) -> PayoutDebtObligation:
    obligation = await session.scalar(
        select(PayoutDebtObligation).where(PayoutDebtObligation.recovery_incident_id == incident.id)
    )
    if obligation is not None:
        return obligation
    ledger = await session.get(EarningsLedgerEntry, incident.ledger_entry_id)
    if ledger is None:
        raise RuntimeError("Recovery incident lost its ledger authority")
    account = await _locked_debt_account(
        session,
        driver_profile_id=ledger.driver_profile_id,
        driver_user_id=ledger.driver_user_id,
        currency=incident.currency,
    )
    if account is None:
        raise RuntimeError("Recovery debt account could not be created")
    obligation = PayoutDebtObligation(
        debt_account_id=account.id,
        source_reversal_entry_id=incident.source_reversal_entry_id,
        recovery_incident_id=incident.id,
        correction_order_id=None,
        currency=incident.currency,
        original_amount=incident.amount,
        outstanding_amount=incident.amount,
    )
    session.add(obligation)
    await session.flush()
    if ledger.status == EarningsLedgerEntryStatus.PAID.value:
        session.add(
            PayoutDebtPaidSource(
                debt_obligation_id=obligation.id,
                paid_ledger_entry_id=ledger.id,
            )
        )
    account.outstanding_amount = _money(account.outstanding_amount + incident.amount)
    account.lifetime_incurred_amount = _money(account.lifetime_incurred_amount + incident.amount)
    incident.status = PayoutRecoveryIncidentStatus.DEBT_ACTIVATED.value
    incident.resolved_at = resolved_at
    await session.flush()
    return obligation


async def close_recovery_incident(
    session: AsyncSession,
    *,
    incident: PayoutRecoveryIncident,
    resolved_at: datetime,
) -> None:
    if incident.status == PayoutRecoveryIncidentStatus.CLOSED.value:
        return
    incident.status = PayoutRecoveryIncidentStatus.CLOSED.value
    incident.resolved_at = resolved_at
    await session.flush()


async def settle_recovery_incident_from_credit(
    session: AsyncSession,
    *,
    incident: PayoutRecoveryIncident,
    credit: EarningsLedgerEntry,
    actor_user_id: UUID,
    resolved_at: datetime,
    preserve_credit_authority: bool = False,
) -> PayoutDebtSettlement:
    existing = await session.scalar(
        select(PayoutDebtSettlement).where(PayoutDebtSettlement.source_credit_entry_id == credit.id)
    )
    if existing is not None:
        obligation = await session.scalar(
            select(PayoutDebtObligation).where(
                PayoutDebtObligation.recovery_incident_id == incident.id
            )
        )
        if obligation is not None and obligation.outstanding_amount == 0:
            await close_recovery_incident(session, incident=incident, resolved_at=resolved_at)
        return existing
    if credit.status != EarningsLedgerEntryStatus.AVAILABLE.value:
        raise RuntimeError("Recovery netting requires an available source credit")
    obligation = await activate_recovery_incident_debt(
        session,
        incident=incident,
        resolved_at=resolved_at,
    )
    allocated = _money(min(credit.amount, obligation.outstanding_amount))
    if allocated <= 0:
        raise RuntimeError("Recovery netting has no positive allocation")
    settlement_id = uuid4()
    remainder_amount = _money(credit.amount - allocated)
    remainder: EarningsLedgerEntry | None = None
    if remainder_amount > 0:
        remainder = EarningsLedgerEntry(
            id=uuid4(),
            payout_calculation_id=None,
            driver_profile_id=credit.driver_profile_id,
            driver_user_id=credit.driver_user_id,
            campaign_id=credit.campaign_id,
            trip_session_id=credit.trip_session_id,
            vehicle_id=credit.vehicle_id,
            entry_type=EarningsLedgerEntryType.DEBT_REMAINDER.value,
            status=EarningsLedgerEntryStatus.AVAILABLE.value,
            amount=remainder_amount,
            currency=credit.currency,
            description="Credit remaining after recovery netting",
            occurred_at=credit.occurred_at,
            release_at=None,
            ledger_metadata={
                "recovery_remainder": True,
                "source_credit_entry_id": str(credit.id),
                "recovery_incident_id": str(incident.id),
            },
        )
        session.add(remainder)
    settlement = PayoutDebtSettlement(
        id=settlement_id,
        source_credit_entry_id=credit.id,
        remainder_entry_id=remainder.id if remainder is not None else None,
        original_credit_amount=credit.amount,
        allocated_amount=allocated,
        idempotency_key=_recovery_incident_key("cardvert-recovery-net-v1", incident.id, credit.id),
        created_by_user_id=actor_user_id,
    )
    session.add(settlement)
    if remainder is not None:
        await session.flush([remainder])
    await session.flush([settlement])
    session.add(
        PayoutDebtAllocation(
            settlement_id=settlement.id,
            debt_obligation_id=obligation.id,
            amount=allocated,
        )
    )
    if not preserve_credit_authority:
        credit.status = EarningsLedgerEntryStatus.REVERSED.value
    obligation.outstanding_amount = _money(obligation.outstanding_amount - allocated)
    account = await session.get(DriverCurrencyDebtAccount, obligation.debt_account_id)
    if account is None:
        raise RuntimeError("Recovery debt account was not found")
    account.outstanding_amount = _money(account.outstanding_amount - allocated)
    account.lifetime_allocated_amount = _money(account.lifetime_allocated_amount + allocated)
    if obligation.outstanding_amount == 0:
        await close_recovery_incident(
            session,
            incident=incident,
            resolved_at=resolved_at,
        )
    await session.flush()
    return settlement


async def lock_driver_currency_debt_scope(
    session: AsyncSession,
    *,
    driver_profile_id: UUID,
    currency: str,
) -> tuple[DriverProfile, DriverCurrencyDebtAccount | None]:
    """Shared serialization seam for cash finality, debt, allocation and batching."""
    profile = await session.scalar(
        select(DriverProfile).where(DriverProfile.id == driver_profile_id).with_for_update()
    )
    if profile is None:
        raise ValueError("Driver profile was not found")
    account = await session.scalar(
        select(DriverCurrencyDebtAccount)
        .where(
            DriverCurrencyDebtAccount.driver_profile_id == driver_profile_id,
            DriverCurrencyDebtAccount.currency == currency,
        )
        .with_for_update()
    )
    return profile, account


async def _locked_debt_account(
    session: AsyncSession,
    *,
    driver_profile_id: UUID,
    driver_user_id: UUID,
    currency: str,
    create_if_missing: bool = True,
) -> DriverCurrencyDebtAccount | None:
    # The profile lock serializes first-account creation; subsequent work also
    # locks the currency-specific account so different currencies never offset.
    profile, account = await lock_driver_currency_debt_scope(
        session,
        driver_profile_id=driver_profile_id,
        currency=currency,
    )
    if profile.user_id != driver_user_id:
        raise ValueError("Debt authority does not match the driver profile")
    if account is None and create_if_missing:
        account = DriverCurrencyDebtAccount(
            driver_profile_id=driver_profile_id,
            driver_user_id=driver_user_id,
            currency=currency,
            outstanding_amount=Decimal("0.00"),
            lifetime_incurred_amount=Decimal("0.00"),
            lifetime_allocated_amount=Decimal("0.00"),
        )
        session.add(account)
        await session.flush()
    return account


async def record_reversal_obligation(
    session: AsyncSession,
    *,
    reversal_entry: EarningsLedgerEntry,
) -> PayoutDebtObligation | None:
    """Net an available reversal, linking actual paid history when present."""
    if reversal_entry.entry_type != EarningsLedgerEntryType.REVERSAL:
        raise ValueError("Only a reversal can create carry-forward debt")
    profile, account = await lock_driver_currency_debt_scope(
        session,
        driver_profile_id=reversal_entry.driver_profile_id,
        currency=reversal_entry.currency,
    )
    if profile.user_id != reversal_entry.driver_user_id:
        raise ValueError("Reversal authority does not match the driver profile")
    existing = await session.scalar(
        select(PayoutDebtObligation).where(
            PayoutDebtObligation.source_reversal_entry_id == reversal_entry.id,
            PayoutDebtObligation.recovery_incident_id.is_(None),
        )
    )
    if existing is not None:
        return existing
    active_reservation = await session.scalar(
        select(PayoutBatchLine.id)
        .join(EarningsLedgerEntry, EarningsLedgerEntry.id == PayoutBatchLine.ledger_entry_id)
        .where(
            PayoutBatchLine.reservation_active.is_(True),
            PayoutBatchLine.status != "succeeded",
            EarningsLedgerEntry.driver_profile_id == reversal_entry.driver_profile_id,
            EarningsLedgerEntry.currency == reversal_entry.currency,
        )
        .limit(1)
    )
    if active_reservation is not None:
        raise AppError(
            "PAYOUT_DEBT_ACTIVE_RESERVATION",
            "Resolve the active payout reservation before applying reversal debt",
            status_code=409,
        )
    paid_entries = tuple(
        (
            await session.scalars(
                select(EarningsLedgerEntry)
                .where(
                    EarningsLedgerEntry.driver_profile_id == reversal_entry.driver_profile_id,
                    EarningsLedgerEntry.trip_session_id == reversal_entry.trip_session_id,
                    EarningsLedgerEntry.currency == reversal_entry.currency,
                    EarningsLedgerEntry.status == EarningsLedgerEntryStatus.PAID,
                    EarningsLedgerEntry.entry_type != EarningsLedgerEntryType.REVERSAL,
                )
                .order_by(EarningsLedgerEntry.occurred_at, EarningsLedgerEntry.id)
                .with_for_update()
            )
        ).all()
    )
    if paid_entries:
        # The cash boundary is derived from any actual paid same-trip credit,
        # never merely from the original trip-payout row.
        reversal_entry.status = EarningsLedgerEntryStatus.AVAILABLE
    if not paid_entries and reversal_entry.status != EarningsLedgerEntryStatus.AVAILABLE:
        return None
    if account is None:
        account = DriverCurrencyDebtAccount(
            driver_profile_id=reversal_entry.driver_profile_id,
            driver_user_id=reversal_entry.driver_user_id,
            currency=reversal_entry.currency,
            outstanding_amount=Decimal("0.00"),
            lifetime_incurred_amount=Decimal("0.00"),
            lifetime_allocated_amount=Decimal("0.00"),
        )
        session.add(account)
        await session.flush()
    correction_raw = (reversal_entry.ledger_metadata or {}).get("correction_order_id")
    correction_order_id = UUID(correction_raw) if correction_raw else None
    amount = _money(reversal_entry.amount)
    obligation = PayoutDebtObligation(
        debt_account_id=account.id,
        source_reversal_entry_id=reversal_entry.id,
        recovery_incident_id=None,
        correction_order_id=correction_order_id,
        currency=reversal_entry.currency,
        original_amount=amount,
        outstanding_amount=amount,
    )
    session.add(obligation)
    await session.flush()
    session.add_all(
        PayoutDebtPaidSource(
            debt_obligation_id=obligation.id,
            paid_ledger_entry_id=paid.id,
        )
        for paid in paid_entries
    )
    account.outstanding_amount = _money(account.outstanding_amount + amount)
    account.lifetime_incurred_amount = _money(account.lifetime_incurred_amount + amount)
    await session.flush()
    return obligation


async def driver_money_balance(
    session: AsyncSession, *, driver_profile_id: UUID, currency: str
) -> DriverMoneyBalance:
    normalized = currency.strip().upper()
    signed = case(
        (
            EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.REVERSAL,
            -EarningsLedgerEntry.amount,
        ),
        else_=EarningsLedgerEntry.amount,
    )
    row = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (EarningsLedgerEntry.status != EarningsLedgerEntryStatus.VOIDED)
                                & (
                                    EarningsLedgerEntry.entry_type
                                    != EarningsLedgerEntryType.DEBT_REMAINDER
                                ),
                                signed,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (EarningsLedgerEntry.status == EarningsLedgerEntryStatus.PAID)
                                & (
                                    EarningsLedgerEntry.entry_type
                                    != EarningsLedgerEntryType.REVERSAL
                                ),
                                EarningsLedgerEntry.amount,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(
                EarningsLedgerEntry.driver_profile_id == driver_profile_id,
                EarningsLedgerEntry.currency == normalized,
            )
        )
    ).one()
    debt = await session.scalar(
        select(DriverCurrencyDebtAccount.outstanding_amount).where(
            DriverCurrencyDebtAccount.driver_profile_id == driver_profile_id,
            DriverCurrencyDebtAccount.currency == normalized,
        )
    )
    available_credits = tuple(
        (
            await session.execute(
                select(EarningsLedgerEntry.id, EarningsLedgerEntry.amount).where(
                    EarningsLedgerEntry.driver_profile_id == driver_profile_id,
                    EarningsLedgerEntry.currency == normalized,
                    EarningsLedgerEntry.status == EarningsLedgerEntryStatus.AVAILABLE,
                    EarningsLedgerEntry.entry_type != EarningsLedgerEntryType.REVERSAL,
                    ~exists(
                        select(PayoutDebtSettlement.id).where(
                            PayoutDebtSettlement.source_credit_entry_id == EarningsLedgerEntry.id
                        )
                    ),
                )
            )
        ).all()
    )
    credit_ids = tuple(row.id for row in available_credits)
    line_rows = (
        tuple(
            (
                await session.execute(
                    select(PayoutBatchLine, PayoutSubmissionIntent)
                    .outerjoin(
                        PayoutSubmissionIntent,
                        PayoutSubmissionIntent.payout_batch_line_id == PayoutBatchLine.id,
                    )
                    .where(PayoutBatchLine.ledger_entry_id.in_(credit_ids))
                    .order_by(PayoutBatchLine.created_at, PayoutBatchLine.id)
                )
            ).all()
        )
        if credit_ids
        else ()
    )
    lines_by_credit: dict[UUID, list[tuple[PayoutBatchLine, PayoutSubmissionIntent | None]]] = {}
    for line, intent in line_rows:
        lines_by_credit.setdefault(line.ledger_entry_id, []).append((line, intent))

    released = Decimal("0.00")
    reserved = Decimal("0.00")
    in_flight = Decimal("0.00")
    terminal_failed = Decimal("0.00")
    for credit_id, raw_amount in available_credits:
        amount = _money(raw_amount)
        history = lines_by_credit.get(credit_id, [])
        active = [(line, intent) for line, intent in history if line.reservation_active]
        if active:
            line, intent = active[0]
            unknown = line.status == PayoutBatchLineStatus.SUBMITTED.value or (
                line.status == PayoutBatchLineStatus.RESERVED.value
                and intent is not None
                and intent.state
                in {
                    PayoutSubmissionIntentState.CLAIMED.value,
                    PayoutSubmissionIntentState.QUERY_ONLY.value,
                }
            )
            if unknown:
                in_flight += amount
            else:
                reserved += amount
            continue
        predecessor_ids = {
            line.predecessor_line_id for line, _ in history if line.predecessor_line_id is not None
        }
        leaves = [line for line, _ in history if line.id not in predecessor_ids]
        if any(line.status == PayoutBatchLineStatus.FAILED.value for line in leaves):
            terminal_failed += amount
        else:
            released += amount

    earned_net = _money(row[0])
    released = _money(released)
    reserved = _money(reserved)
    in_flight = _money(in_flight)
    terminal_failed = _money(terminal_failed)
    paid = _money(row[1])
    outstanding = _money(debt or 0)
    # This is a settlement projection, not an entry-selection rule. Whole-entry
    # reservation still refuses a gross source while debt is outstanding, but
    # the public balance must expose the economic amount that will remain after
    # deterministic allocation.
    batch_payable = _money(max(released + terminal_failed - outstanding, Decimal("0.00")))
    return DriverMoneyBalance(
        driver_profile_id=driver_profile_id,
        currency=normalized,
        earned_net=earned_net,
        released_available=released,
        reserved=reserved,
        in_flight=in_flight,
        terminal_failed=terminal_failed,
        cash_paid=paid,
        carry_forward_debt=outstanding,
        batch_payable=batch_payable,
    )


async def allocate_available_credit_to_debt(
    session: AsyncSession,
    *,
    driver_profile_id: UUID,
    currency: str,
    actor_user_id: UUID,
) -> DebtAllocationResult:
    normalized = currency.strip().upper()
    profile = await session.get(DriverProfile, driver_profile_id)
    if profile is None:
        raise ValueError("Driver profile was not found")
    account = await _locked_debt_account(
        session,
        driver_profile_id=driver_profile_id,
        driver_user_id=profile.user_id,
        currency=normalized,
        create_if_missing=False,
    )
    if account is None or account.outstanding_amount <= 0:
        return DebtAllocationResult(
            balance=await driver_money_balance(
                session, driver_profile_id=driver_profile_id, currency=normalized
            ),
            settlement_ids=(),
            remainder_entry_ids=(),
        )
    obligations = list(
        (
            await session.scalars(
                select(PayoutDebtObligation)
                .where(
                    PayoutDebtObligation.debt_account_id == account.id,
                    PayoutDebtObligation.outstanding_amount > 0,
                )
                .order_by(PayoutDebtObligation.created_at, PayoutDebtObligation.id)
                .with_for_update()
            )
        ).all()
    )
    credits = list(
        (
            await session.scalars(
                select(EarningsLedgerEntry)
                .where(
                    EarningsLedgerEntry.driver_profile_id == driver_profile_id,
                    EarningsLedgerEntry.currency == normalized,
                    EarningsLedgerEntry.status == EarningsLedgerEntryStatus.AVAILABLE,
                    EarningsLedgerEntry.entry_type != EarningsLedgerEntryType.REVERSAL,
                    ~exists(
                        select(PayoutDebtSettlement.id).where(
                            PayoutDebtSettlement.source_credit_entry_id == EarningsLedgerEntry.id
                        )
                    ),
                    ~exists(
                        select(PayoutBatchLine.id).where(
                            PayoutBatchLine.ledger_entry_id == EarningsLedgerEntry.id,
                            PayoutBatchLine.reservation_active.is_(True),
                        )
                    ),
                )
                .order_by(EarningsLedgerEntry.occurred_at, EarningsLedgerEntry.id)
                .with_for_update()
            )
        ).all()
    )
    settlement_ids: list[UUID] = []
    remainder_ids: list[UUID] = []
    obligation_index = 0
    for credit in credits:
        if account.outstanding_amount <= 0:
            break
        allocated = _money(min(credit.amount, account.outstanding_amount))
        settlement_id = uuid4()
        remainder_amount = _money(credit.amount - allocated)
        remainder: EarningsLedgerEntry | None = None
        if remainder_amount > 0:
            remainder = EarningsLedgerEntry(
                id=uuid4(),
                payout_calculation_id=None,
                driver_profile_id=credit.driver_profile_id,
                driver_user_id=credit.driver_user_id,
                campaign_id=credit.campaign_id,
                trip_session_id=credit.trip_session_id,
                vehicle_id=credit.vehicle_id,
                entry_type=EarningsLedgerEntryType.DEBT_REMAINDER,
                status=EarningsLedgerEntryStatus.AVAILABLE,
                amount=remainder_amount,
                currency=credit.currency,
                description="Credit remaining after carry-forward debt allocation",
                occurred_at=credit.occurred_at,
                release_at=None,
                ledger_metadata={
                    "debt_remainder": True,
                    "source_credit_entry_id": str(credit.id),
                    "debt_settlement_id": str(settlement_id),
                    "source_metadata": credit.ledger_metadata or {},
                },
            )
            session.add(remainder)
            remainder_ids.append(remainder.id)
        settlement = PayoutDebtSettlement(
            id=settlement_id,
            source_credit_entry_id=credit.id,
            remainder_entry_id=remainder.id if remainder is not None else None,
            original_credit_amount=credit.amount,
            allocated_amount=allocated,
            idempotency_key=hashlib.sha256(
                f"cardvert-debt-settlement-v1:{credit.id}".encode()
            ).hexdigest(),
            created_by_user_id=actor_user_id,
        )
        session.add(settlement)
        if remainder is not None:
            await session.flush([remainder])
        await session.flush([settlement])
        credit.status = EarningsLedgerEntryStatus.REVERSED
        remaining = allocated
        while remaining > 0:
            obligation = obligations[obligation_index]
            applied = _money(min(remaining, obligation.outstanding_amount))
            session.add(
                PayoutDebtAllocation(
                    settlement_id=settlement.id,
                    debt_obligation_id=obligation.id,
                    amount=applied,
                )
            )
            obligation.outstanding_amount = _money(obligation.outstanding_amount - applied)
            remaining = _money(remaining - applied)
            if obligation.outstanding_amount == 0:
                obligation_index += 1
        account.outstanding_amount = _money(account.outstanding_amount - allocated)
        account.lifetime_allocated_amount = _money(account.lifetime_allocated_amount + allocated)
        settlement_ids.append(settlement.id)
    await session.flush()
    if settlement_ids:
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="admin.payout_debt.allocated",
            entity_type="driver_currency_debt_account",
            entity_id=str(account.id),
            metadata={
                "currency": normalized,
                "settlement_ids": [str(value) for value in settlement_ids],
                "outstanding_amount": str(account.outstanding_amount),
            },
        )
    return DebtAllocationResult(
        balance=await driver_money_balance(
            session, driver_profile_id=driver_profile_id, currency=normalized
        ),
        settlement_ids=tuple(settlement_ids),
        remainder_entry_ids=tuple(remainder_ids),
    )

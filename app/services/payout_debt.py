import hashlib
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.disbursement import (
    DriverCurrencyDebtAccount,
    PayoutBatchLine,
    PayoutDebtAllocation,
    PayoutDebtObligation,
    PayoutDebtPaidSource,
    PayoutDebtSettlement,
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
    cash_paid: Decimal
    carry_forward_debt: Decimal
    batch_payable: Decimal


@dataclass(frozen=True)
class DebtAllocationResult:
    balance: DriverMoneyBalance
    settlement_ids: tuple[UUID, ...]
    remainder_entry_ids: tuple[UUID, ...]


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
            PayoutDebtObligation.source_reversal_entry_id == reversal_entry.id
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
                                (EarningsLedgerEntry.status == EarningsLedgerEntryStatus.AVAILABLE)
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
    earned_net = _money(row[0])
    released = _money(row[1])
    paid = _money(row[2])
    outstanding = _money(debt or 0)
    # This is a settlement projection, not an entry-selection rule. Whole-entry
    # reservation still refuses a gross source while debt is outstanding, but
    # the public balance must expose the economic amount that will remain after
    # deterministic allocation.
    batch_payable = _money(max(released - outstanding, Decimal("0.00")))
    return DriverMoneyBalance(
        driver_profile_id=driver_profile_id,
        currency=normalized,
        earned_net=earned_net,
        released_available=released,
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

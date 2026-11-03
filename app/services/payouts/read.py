"""Payouts: read domain operations."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.campaign import Campaign
from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    PayoutCalculation,
)
from app.models.trip import TripSession
from app.services.drivers import get_required_driver_profile_with_user_by_user_id
from app.services.impressions import (
    quantize_2,
)
from app.services.payout_balances import driver_money_balance
from app.services.payouts.common import (
    DriverCurrencyEarnings,
    DriverEarnings,
    signed_ledger_amount_expression,
    validate_currency_code,
)


async def list_payout_calculations(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    campaign_id: UUID | None,
    trip_session_id: UUID | None,
    driver_profile_id: UUID | None,
    vehicle_id: UUID | None,
    calculation_status: str | None,
    currency: str | None,
) -> tuple[list[tuple[PayoutCalculation, datetime, str]], int]:
    filters = []
    if campaign_id is not None:
        filters.append(PayoutCalculation.campaign_id == campaign_id)
    if trip_session_id is not None:
        filters.append(PayoutCalculation.trip_session_id == trip_session_id)
    if driver_profile_id is not None:
        filters.append(PayoutCalculation.driver_profile_id == driver_profile_id)
    if vehicle_id is not None:
        filters.append(PayoutCalculation.vehicle_id == vehicle_id)
    if calculation_status is not None:
        filters.append(PayoutCalculation.status == calculation_status)
    normalized_currency = validate_currency_code(currency)
    if normalized_currency is not None:
        filters.append(PayoutCalculation.currency == normalized_currency)

    statement = (
        select(PayoutCalculation, TripSession.started_at, Campaign.name)
        .join(TripSession, TripSession.id == PayoutCalculation.trip_session_id)
        .join(Campaign, Campaign.id == PayoutCalculation.campaign_id)
    )
    count_statement = select(func.count()).select_from(PayoutCalculation)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(PayoutCalculation.calculated_at.desc(), PayoutCalculation.id)
        .limit(limit)
        .offset(offset)
    )
    return [(row[0], row[1], row[2]) for row in result.all()], int(total or 0)


async def driver_earnings_summary(
    session: AsyncSession,
    *,
    user_id: UUID,
    currency: str | None,
    settings: Settings,
) -> DriverEarnings:
    profile, _ = await get_required_driver_profile_with_user_by_user_id(session, user_id)
    filters = [
        EarningsLedgerEntry.driver_profile_id == profile.id,
        EarningsLedgerEntry.driver_user_id == user_id,
    ]
    normalized_currency = validate_currency_code(currency)
    if normalized_currency is not None:
        filters.append(EarningsLedgerEntry.currency == normalized_currency)

    signed_amount = signed_ledger_amount_expression()
    result = await session.execute(
        select(
            EarningsLedgerEntry.currency,
            func.coalesce(
                func.sum(
                    case(
                        (
                            EarningsLedgerEntry.status == EarningsLedgerEntryStatus.PENDING.value,
                            signed_amount,
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
                            EarningsLedgerEntry.status == EarningsLedgerEntryStatus.AVAILABLE.value,
                            signed_amount,
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
                            EarningsLedgerEntry.status == EarningsLedgerEntryStatus.VOIDED.value,
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
                            EarningsLedgerEntry.status == EarningsLedgerEntryStatus.PAID.value,
                            signed_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.count(EarningsLedgerEntry.id),
        )
        .where(*filters)
        .group_by(EarningsLedgerEntry.currency)
    )
    totals = []
    for row in result.all():
        pending = quantize_2(Decimal(str(row[1] or 0)))
        voided = quantize_2(Decimal(str(row[3] or 0)))
        balance = await driver_money_balance(
            session,
            driver_profile_id=profile.id,
            currency=row[0],
        )
        totals.append(
            DriverCurrencyEarnings(
                currency=row[0],
                pending_amount=pending,
                available_amount=balance.released_available,
                paid_amount=balance.cash_paid,
                voided_amount=voided,
                lifetime_earned_amount=balance.earned_net,
                released_available_amount=balance.released_available,
                cash_paid_amount=balance.cash_paid,
                batch_payable_amount=balance.batch_payable,
                ledger_entry_count=int(row[5] or 0),
            )
        )
    if not totals:
        totals.append(
            DriverCurrencyEarnings(
                currency=validate_currency_code(currency, fallback=settings.default_currency),
                pending_amount=Decimal("0.00"),
                available_amount=Decimal("0.00"),
                paid_amount=Decimal("0.00"),
                voided_amount=Decimal("0.00"),
                lifetime_earned_amount=Decimal("0.00"),
                released_available_amount=Decimal("0.00"),
                cash_paid_amount=Decimal("0.00"),
                batch_payable_amount=Decimal("0.00"),
                ledger_entry_count=0,
            )
        )
    return DriverEarnings(driver_profile_id=profile.id, totals_by_currency=totals)


async def list_driver_ledger_entries(
    session: AsyncSession,
    *,
    user_id: UUID,
    limit: int,
    offset: int,
    ledger_status: str | None,
    entry_type: str | None,
    currency: str | None,
) -> tuple[list[EarningsLedgerEntry], int]:
    profile, _ = await get_required_driver_profile_with_user_by_user_id(session, user_id)
    filters = [
        EarningsLedgerEntry.driver_profile_id == profile.id,
        EarningsLedgerEntry.driver_user_id == user_id,
    ]
    if ledger_status is not None:
        filters.append(EarningsLedgerEntry.status == ledger_status)
    if entry_type is not None:
        filters.append(EarningsLedgerEntry.entry_type == entry_type)
    normalized_currency = validate_currency_code(currency)
    if normalized_currency is not None:
        filters.append(EarningsLedgerEntry.currency == normalized_currency)

    statement = select(EarningsLedgerEntry).where(*filters)
    count_statement = select(func.count()).select_from(EarningsLedgerEntry).where(*filters)
    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(EarningsLedgerEntry.occurred_at.desc(), EarningsLedgerEntry.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)

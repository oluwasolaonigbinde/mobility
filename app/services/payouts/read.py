"""Payouts: read domain operations."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.campaign import Campaign
from app.models.payout import (
    CampaignPayoutRule,
    CampaignPayoutRuleStatus,
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    PayoutCalculation,
    PayoutCalculationStatus,
)
from app.models.trip import TripSession
from app.services.campaigns import get_advertiser_campaign
from app.services.drivers import get_required_driver_profile_with_user_by_user_id
from app.services.impressions import (
    quantize_2,
)
from app.services.payout_debt import driver_money_balance
from app.services.payouts.common import (
    PAYOUT_V4,
    CampaignCost,
    CampaignCurrencyCost,
    DriverCurrencyEarnings,
    DriverEarnings,
    signed_ledger_amount_expression,
    validate_currency_code,
)
from app.services.payouts.ledger import latest_payout_calculation_ids


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
            func.coalesce(
                func.sum(
                    case(
                        (
                            EarningsLedgerEntry.status != EarningsLedgerEntryStatus.VOIDED.value,
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
        available = quantize_2(Decimal(str(row[2] or 0)))
        voided = quantize_2(Decimal(str(row[3] or 0)))
        paid = quantize_2(Decimal(str(row[4] or 0)))
        balance = await driver_money_balance(
            session,
            driver_profile_id=profile.id,
            currency=row[0],
        )
        totals.append(
            DriverCurrencyEarnings(
                currency=row[0],
                pending_amount=pending,
                available_amount=available,
                paid_amount=paid,
                voided_amount=voided,
                lifetime_earned_amount=quantize_2(Decimal(str(row[5] or 0))),
                released_available_amount=balance.released_available,
                cash_paid_amount=balance.cash_paid,
                carry_forward_debt_amount=balance.carry_forward_debt,
                batch_payable_amount=balance.batch_payable,
                ledger_entry_count=int(row[6] or 0),
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
                carry_forward_debt_amount=Decimal("0.00"),
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


async def advertiser_campaign_cost_summary(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    currency: str | None,
    settings: Settings,
) -> CampaignCost:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    # Sum the stored calculation amounts for this campaign.
    # rows side by side; reports render whichever version a row carries (16.1),
    # and each trip counts once (its latest calculation).
    filters = [
        PayoutCalculation.campaign_id == campaign.id,
        PayoutCalculation.id.in_(latest_payout_calculation_ids(campaign_id=campaign.id)),
    ]
    if start_at is not None:
        filters.append(PayoutCalculation.calculated_at >= start_at)
    if end_at is not None:
        filters.append(PayoutCalculation.calculated_at <= end_at)
    normalized_currency = validate_currency_code(currency)
    if normalized_currency is not None:
        filters.append(PayoutCalculation.currency == normalized_currency)

    result = await session.execute(
        select(
            PayoutCalculation.currency,
            func.coalesce(func.sum(PayoutCalculation.final_payout), 0),
            func.coalesce(func.sum(PayoutCalculation.gross_payout), 0),
            func.coalesce(
                func.sum(
                    case(
                        (
                            PayoutCalculation.status == PayoutCalculationStatus.CALCULATED.value,
                            1,
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
                            PayoutCalculation.status == PayoutCalculationStatus.BLOCKED.value,
                            1,
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
                            PayoutCalculation.status
                            == PayoutCalculationStatus.INSUFFICIENT_DATA.value,
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.count(EarningsLedgerEntry.id),
        )
        .select_from(PayoutCalculation)
        .outerjoin(
            EarningsLedgerEntry,
            EarningsLedgerEntry.payout_calculation_id == PayoutCalculation.id,
        )
        .where(*filters)
        .group_by(PayoutCalculation.currency)
    )
    # Reversal netting lives in a separate ledger aggregate: adjustment and
    # reversal entries carry no payout_calculation_id, so the calc join above
    # can never see them. Note the ranges differ deliberately: calc aggregates
    # window on calculated_at (when cost was computed), the ledger net on
    # occurred_at (when money was posted).
    ledger_filters = [EarningsLedgerEntry.campaign_id == campaign.id]
    if start_at is not None:
        ledger_filters.append(EarningsLedgerEntry.occurred_at >= start_at)
    if end_at is not None:
        ledger_filters.append(EarningsLedgerEntry.occurred_at <= end_at)
    if normalized_currency is not None:
        ledger_filters.append(EarningsLedgerEntry.currency == normalized_currency)
    ledger_result = await session.execute(
        select(
            EarningsLedgerEntry.currency,
            func.coalesce(func.sum(signed_ledger_amount_expression()), 0),
        )
        .where(
            *ledger_filters,
            EarningsLedgerEntry.status != EarningsLedgerEntryStatus.VOIDED.value,
        )
        .group_by(EarningsLedgerEntry.currency)
    )
    ledger_net_by_currency = {
        row[0]: quantize_2(Decimal(str(row[1] or 0))) for row in ledger_result.all()
    }

    formula_rows = await session.execute(
        select(PayoutCalculation.formula_version)
        .where(PayoutCalculation.campaign_id == campaign.id)
        .distinct()
        .order_by(PayoutCalculation.formula_version)
    )
    formula_versions = [row[0] for row in formula_rows.all()]
    governing_rule = await session.scalar(
        select(CampaignPayoutRule.formula_version)
        .where(
            CampaignPayoutRule.campaign_id == campaign.id,
            CampaignPayoutRule.status == CampaignPayoutRuleStatus.ACTIVE.value,
        )
        .order_by(CampaignPayoutRule.created_at.desc(), CampaignPayoutRule.id)
        .limit(1)
    )

    totals = [
        CampaignCurrencyCost(
            currency=row[0],
            final_payout_total=quantize_2(Decimal(str(row[1] or 0))),
            gross_payout_total=quantize_2(Decimal(str(row[2] or 0))),
            ledger_net_total=ledger_net_by_currency.pop(row[0], Decimal("0.00")),
            calculated_trip_count=int(row[3] or 0),
            blocked_trip_count=int(row[4] or 0),
            insufficient_data_trip_count=int(row[5] or 0),
            ledger_entry_count=int(row[6] or 0),
        )
        for row in result.all()
    ]
    for leftover_currency, net_total in sorted(ledger_net_by_currency.items()):
        totals.append(
            CampaignCurrencyCost(
                currency=leftover_currency,
                final_payout_total=Decimal("0.00"),
                gross_payout_total=Decimal("0.00"),
                ledger_net_total=net_total,
                calculated_trip_count=0,
                blocked_trip_count=0,
                insufficient_data_trip_count=0,
                ledger_entry_count=0,
            )
        )
    if not totals:
        totals.append(
            CampaignCurrencyCost(
                currency=validate_currency_code(currency, fallback=settings.default_currency),
                final_payout_total=Decimal("0.00"),
                gross_payout_total=Decimal("0.00"),
                ledger_net_total=Decimal("0.00"),
                calculated_trip_count=0,
                blocked_trip_count=0,
                insufficient_data_trip_count=0,
                ledger_entry_count=0,
            )
        )
    return CampaignCost(
        campaign_id=campaign.id,
        formula_version=governing_rule or PAYOUT_V4,
        formula_versions=formula_versions,
        totals_by_currency=totals,
        start_at=start_at,
        end_at=end_at,
    )

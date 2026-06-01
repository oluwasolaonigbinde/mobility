from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Query, status

from app.api.v1.dependencies import (
    AdminUserDependency,
    AdvertiserUserDependency,
    DriverUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.core.errors import AppError
from app.models.payout import (
    CampaignPayoutRule,
    CampaignPayoutRuleStatus,
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCalculation,
    PayoutCalculationStatus,
)
from app.schemas.campaigns import ensure_timezone_aware
from app.schemas.payouts import (
    CalculatePayoutRequest,
    CampaignCostCurrencySummary,
    CampaignCostSummary,
    CampaignPayoutRuleCreate,
    CampaignPayoutRuleListResponse,
    CampaignPayoutRuleRead,
    CampaignPayoutRuleUpdate,
    DriverEarningsCurrencySummary,
    DriverEarningsSummary,
    EarningsLedgerEntryListResponse,
    EarningsLedgerEntryRead,
    PayoutCalculationListResponse,
    PayoutCalculationRead,
    PayoutLedgerEntrySummary,
)
from app.services.audit import create_audit_event
from app.services.payouts import (
    advertiser_campaign_cost_summary,
    calculate_trip_payout,
    create_campaign_payout_rule,
    driver_earnings_summary,
    get_campaign_payout_rule,
    ledger_for_calculation,
    list_campaign_payout_rules,
    list_driver_ledger_entries,
    list_payout_calculations,
    update_campaign_payout_rule,
)

router = APIRouter(tags=["payouts"])


def ensure_timezone_aware_query(value: datetime | None, field_name: str) -> datetime | None:
    try:
        return ensure_timezone_aware(value)
    except ValueError as exc:
        raise AppError(
            "VALIDATION_ERROR",
            "Request validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"errors": [{"loc": ["query", field_name], "msg": str(exc)}]},
        ) from exc


def payout_rule_response(rule: CampaignPayoutRule) -> CampaignPayoutRuleRead:
    return CampaignPayoutRuleRead(
        id=rule.id,
        campaign_id=rule.campaign_id,
        created_by_user_id=rule.created_by_user_id,
        updated_by_user_id=rule.updated_by_user_id,
        formula_version=rule.formula_version,
        status=rule.status,
        currency=rule.currency,
        base_rate_per_km=rule.base_rate_per_km,
        base_rate_per_active_hour=rule.base_rate_per_active_hour,
        target_zone_bonus_rate_per_km=rule.target_zone_bonus_rate_per_km,
        bonus_zone_bonus_rate_per_km=rule.bonus_zone_bonus_rate_per_km,
        estimated_impression_rate_per_1000=rule.estimated_impression_rate_per_1000,
        min_payout_per_trip=rule.min_payout_per_trip,
        max_payout_per_trip=rule.max_payout_per_trip,
        low_fraud_multiplier=rule.low_fraud_multiplier,
        medium_fraud_multiplier=rule.medium_fraud_multiplier,
        high_fraud_multiplier=rule.high_fraud_multiplier,
        metadata=rule.rule_metadata,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def ledger_summary_response(entry: EarningsLedgerEntry) -> PayoutLedgerEntrySummary:
    return PayoutLedgerEntrySummary(
        id=entry.id,
        status=entry.status,
        amount=entry.amount,
        currency=entry.currency,
    )


def ledger_entry_response(entry: EarningsLedgerEntry) -> EarningsLedgerEntryRead:
    return EarningsLedgerEntryRead(
        id=entry.id,
        payout_calculation_id=entry.payout_calculation_id,
        driver_profile_id=entry.driver_profile_id,
        campaign_id=entry.campaign_id,
        trip_session_id=entry.trip_session_id,
        vehicle_id=entry.vehicle_id,
        entry_type=entry.entry_type,
        status=entry.status,
        amount=entry.amount,
        currency=entry.currency,
        description=entry.description,
        occurred_at=entry.occurred_at,
        metadata=entry.ledger_metadata,
        created_at=entry.created_at,
    )


async def payout_calculation_response(
    session: SessionDependency,
    calculation: PayoutCalculation,
    ledger_entry: EarningsLedgerEntry | None = None,
) -> PayoutCalculationRead:
    if ledger_entry is None:
        ledger_entry = await ledger_for_calculation(session, calculation.id)
    return PayoutCalculationRead(
        id=calculation.id,
        trip_session_id=calculation.trip_session_id,
        trip_analytics_id=calculation.trip_analytics_id,
        impression_estimate_id=calculation.impression_estimate_id,
        payout_rule_id=calculation.payout_rule_id,
        assignment_id=calculation.assignment_id,
        campaign_id=calculation.campaign_id,
        driver_profile_id=calculation.driver_profile_id,
        vehicle_id=calculation.vehicle_id,
        formula_version=calculation.formula_version,
        status=calculation.status,
        currency=calculation.currency,
        distance_component=calculation.distance_component,
        active_time_component=calculation.active_time_component,
        target_zone_bonus_component=calculation.target_zone_bonus_component,
        bonus_zone_bonus_component=calculation.bonus_zone_bonus_component,
        impression_component=calculation.impression_component,
        gross_payout=calculation.gross_payout,
        quality_multiplier=calculation.quality_multiplier,
        fraud_multiplier=calculation.fraud_multiplier,
        cap_adjustment=calculation.cap_adjustment,
        final_payout=calculation.final_payout,
        calculated_at=calculation.calculated_at,
        metadata=calculation.payout_metadata,
        ledger_entry=ledger_summary_response(ledger_entry) if ledger_entry else None,
        created_at=calculation.created_at,
        updated_at=calculation.updated_at,
    )


@router.post(
    "/admin/campaigns/{campaign_id}/payout-rules",
    response_model=CampaignPayoutRuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a campaign payout rule",
)
async def admin_create_campaign_payout_rule(
    campaign_id: UUID,
    payload: CampaignPayoutRuleCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> CampaignPayoutRuleRead:
    rule = await create_campaign_payout_rule(
        session,
        campaign_id=campaign_id,
        created_by_user_id=current_user.id,
        payload=payload,
        settings=settings,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.campaign_payout_rule.created",
        entity_type="campaign_payout_rule",
        entity_id=str(rule.id),
        metadata={"campaign_id": str(campaign_id), "status": rule.status},
    )
    await session.commit()
    return payout_rule_response(rule)


@router.get(
    "/admin/campaigns/{campaign_id}/payout-rules",
    response_model=CampaignPayoutRuleListResponse,
    summary="List campaign payout rules",
)
async def admin_list_campaign_payout_rules(
    campaign_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: CampaignPayoutRuleStatus | None = None,
) -> CampaignPayoutRuleListResponse:
    del current_user
    rules, total = await list_campaign_payout_rules(
        session,
        campaign_id=campaign_id,
        limit=limit,
        offset=offset,
        rule_status=status,
    )
    return CampaignPayoutRuleListResponse(
        items=[payout_rule_response(rule) for rule in rules],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/campaigns/{campaign_id}/payout-rules/{rule_id}",
    response_model=CampaignPayoutRuleRead,
    summary="Read a campaign payout rule",
)
async def admin_get_campaign_payout_rule(
    campaign_id: UUID,
    rule_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> CampaignPayoutRuleRead:
    del current_user
    rule = await get_campaign_payout_rule(session, campaign_id=campaign_id, rule_id=rule_id)
    return payout_rule_response(rule)


@router.patch(
    "/admin/campaigns/{campaign_id}/payout-rules/{rule_id}",
    response_model=CampaignPayoutRuleRead,
    summary="Update a campaign payout rule",
)
async def admin_update_campaign_payout_rule(
    campaign_id: UUID,
    rule_id: UUID,
    payload: CampaignPayoutRuleUpdate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> CampaignPayoutRuleRead:
    rule, changed_fields = await update_campaign_payout_rule(
        session,
        campaign_id=campaign_id,
        rule_id=rule_id,
        updated_by_user_id=current_user.id,
        payload=payload,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.campaign_payout_rule.updated",
        entity_type="campaign_payout_rule",
        entity_id=str(rule.id),
        metadata={"campaign_id": str(campaign_id), "changed_fields": changed_fields},
    )
    await session.commit()
    return payout_rule_response(rule)


@router.post(
    "/admin/trips/{trip_id}/calculate-payout",
    response_model=PayoutCalculationRead,
    summary="Calculate payout for one trip",
)
async def admin_calculate_trip_payout(
    trip_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    payload: Annotated[CalculatePayoutRequest | None, Body()] = None,
) -> PayoutCalculationRead:
    calculation, ledger_entry, created = await calculate_trip_payout(
        session,
        trip_id=trip_id,
        payout_rule_id=payload.payout_rule_id if payload is not None else None,
        metadata=payload.metadata if payload is not None else {},
        settings=settings,
    )
    if created:
        await create_audit_event(
            session,
            actor_user_id=current_user.id,
            action="admin.payout_calculation.created",
            entity_type="payout_calculation",
            entity_id=str(calculation.id),
            metadata={
                "trip_session_id": str(calculation.trip_session_id),
                "campaign_id": str(calculation.campaign_id),
                "status": calculation.status,
            },
        )
    await session.commit()
    return await payout_calculation_response(session, calculation, ledger_entry)


@router.get(
    "/admin/payout-calculations",
    response_model=PayoutCalculationListResponse,
    summary="List payout calculations",
)
async def admin_list_payout_calculations(
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    campaign_id: UUID | None = None,
    trip_session_id: UUID | None = None,
    driver_profile_id: UUID | None = None,
    vehicle_id: UUID | None = None,
    status: PayoutCalculationStatus | None = None,
    currency: str | None = None,
) -> PayoutCalculationListResponse:
    del current_user
    calculations, total = await list_payout_calculations(
        session,
        limit=limit,
        offset=offset,
        campaign_id=campaign_id,
        trip_session_id=trip_session_id,
        driver_profile_id=driver_profile_id,
        vehicle_id=vehicle_id,
        calculation_status=status,
        currency=currency,
    )
    items = [
        await payout_calculation_response(session, calculation)
        for calculation in calculations
    ]
    return PayoutCalculationListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/driver/earnings/summary",
    response_model=DriverEarningsSummary,
    summary="Read current driver earnings summary",
)
async def driver_get_earnings_summary(
    current_user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    currency: str | None = None,
) -> DriverEarningsSummary:
    summary = await driver_earnings_summary(
        session,
        user_id=current_user.id,
        currency=currency,
        settings=settings,
    )
    return DriverEarningsSummary(
        driver_profile_id=summary.driver_profile_id,
        totals_by_currency=[
            DriverEarningsCurrencySummary(
                currency=total.currency,
                pending_amount=total.pending_amount,
                available_amount=total.available_amount,
                voided_amount=total.voided_amount,
                lifetime_earned_amount=total.lifetime_earned_amount,
                ledger_entry_count=total.ledger_entry_count,
            )
            for total in summary.totals_by_currency
        ],
    )


@router.get(
    "/driver/earnings/ledger",
    response_model=EarningsLedgerEntryListResponse,
    summary="List current driver earnings ledger entries",
)
async def driver_list_earnings_ledger(
    current_user: DriverUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: EarningsLedgerEntryStatus | None = None,
    entry_type: EarningsLedgerEntryType | None = None,
    currency: str | None = None,
) -> EarningsLedgerEntryListResponse:
    entries, total = await list_driver_ledger_entries(
        session,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        ledger_status=status,
        entry_type=entry_type,
        currency=currency,
    )
    return EarningsLedgerEntryListResponse(
        items=[ledger_entry_response(entry) for entry in entries],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/advertiser/campaigns/{campaign_id}/cost-summary",
    response_model=CampaignCostSummary,
    summary="Read advertiser campaign cost summary",
)
async def advertiser_get_campaign_cost_summary(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    currency: str | None = None,
) -> CampaignCostSummary:
    start_at = ensure_timezone_aware_query(start_at, "start_at")
    end_at = ensure_timezone_aware_query(end_at, "end_at")
    summary = await advertiser_campaign_cost_summary(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        start_at=start_at,
        end_at=end_at,
        currency=currency,
        settings=settings,
    )
    return CampaignCostSummary(
        campaign_id=summary.campaign_id,
        formula_version=summary.formula_version,
        totals_by_currency=[
            CampaignCostCurrencySummary(
                currency=total.currency,
                final_payout_total=total.final_payout_total,
                gross_payout_total=total.gross_payout_total,
                calculated_trip_count=total.calculated_trip_count,
                blocked_trip_count=total.blocked_trip_count,
                insufficient_data_trip_count=total.insufficient_data_trip_count,
                ledger_entry_count=total.ledger_entry_count,
            )
            for total in summary.totals_by_currency
        ],
        start_at=summary.start_at,
        end_at=summary.end_at,
    )

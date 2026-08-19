from datetime import date, datetime
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
    CampaignPayoutRuleRevision,
    CampaignPayoutRuleStatus,
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCalculation,
    PayoutCalculationStatus,
    PayoutCorrectionOrder,
    PayoutCorrectionOrderStatus,
)
from app.schemas.campaigns import ensure_timezone_aware
from app.schemas.payouts import (
    CalculatePayoutRequest,
    CampaignCostCurrencySummary,
    CampaignCostSummary,
    CampaignPayoutRuleCreate,
    CampaignPayoutRuleListResponse,
    CampaignPayoutRuleRead,
    CampaignPayoutRuleRevisionCreate,
    CampaignPayoutRuleRevisionListResponse,
    CampaignPayoutRuleRevisionRead,
    CampaignPayoutRuleUpdate,
    DriverEarningsCurrencySummary,
    DriverEarningsSummary,
    DriverTripEarningsBreakdown,
    DriverTripEarningsCapProgress,
    EarningsLedgerEntryListResponse,
    EarningsLedgerEntryRead,
    PayoutCalculationListResponse,
    PayoutCalculationRead,
    PayoutCorrectionOrderCreate,
    PayoutCorrectionOrderExecuteRequest,
    PayoutCorrectionOrderListResponse,
    PayoutCorrectionOrderRead,
    PayoutDayProjection,
    PayoutLedgerEntrySummary,
    RecomputePayoutDayRequest,
    RecomputePayoutDayResult,
)
from app.services.audit import create_audit_event
from app.services.payout_corrections import (
    approve_correction_order,
    create_correction_order,
    execute_correction_order,
    get_correction_order,
    list_correction_orders,
    project_campaign_day,
    reject_correction_order,
    submit_correction_order,
)
from app.services.payouts import (
    advertiser_campaign_cost_summary,
    calculate_trip_payout,
    create_campaign_payout_rule,
    create_payout_rule_revision,
    driver_earnings_summary,
    driver_trip_earnings_breakdown,
    get_campaign_payout_rule,
    ledger_for_calculation,
    list_campaign_payout_rules,
    list_driver_ledger_entries,
    list_payout_calculations,
    list_payout_rule_revisions,
    recompute_requires_correction_order,
    update_campaign_payout_rule,
)

router = APIRouter(tags=["Payouts"])


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


def ensure_payout_date_range(
    start_at: datetime | None,
    end_at: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    start_at = ensure_timezone_aware_query(start_at, "start_at")
    end_at = ensure_timezone_aware_query(end_at, "end_at")
    if start_at is not None and end_at is not None and start_at > end_at:
        raise AppError(
            "INVALID_DATE_RANGE",
            "start_at must be before or equal to end_at",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return start_at, end_at


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
        hourly_rate_naira=rule.hourly_rate_naira,
        daily_payable_hours_cap=rule.daily_payable_hours_cap,
        eligibility_params=rule.eligibility_params,
        metadata=rule.rule_metadata,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def payout_rule_revision_response(
    revision: CampaignPayoutRuleRevision,
) -> CampaignPayoutRuleRevisionRead:
    return CampaignPayoutRuleRevisionRead(
        id=revision.id,
        campaign_id=revision.campaign_id,
        payout_rule_id=revision.payout_rule_id,
        revision_number=revision.revision_number,
        effective_from=revision.effective_from,
        hourly_rate_naira=revision.hourly_rate_naira,
        premium_hourly_rate_naira=revision.premium_hourly_rate_naira,
        daily_payable_hours_cap=revision.daily_payable_hours_cap,
        eligibility_params=revision.eligibility_params,
        formula_version=revision.formula_version,
        reason=revision.reason,
        created_by_user_id=revision.created_by_user_id,
        created_at=revision.created_at,
    )


def payout_rule_revision_audit_values(
    revision: CampaignPayoutRuleRevision | None,
) -> dict | None:
    """Value-complete audit payload (A3): full money-bearing values, Decimal
    as string, never field names alone (closes RM6 for this path)."""
    if revision is None:
        return None
    return {
        "revision_number": revision.revision_number,
        "effective_from": revision.effective_from.isoformat(),
        "hourly_rate_naira": str(revision.hourly_rate_naira),
        "premium_hourly_rate_naira": (
            str(revision.premium_hourly_rate_naira)
            if revision.premium_hourly_rate_naira is not None
            else None
        ),
        "daily_payable_hours_cap": (
            str(revision.daily_payable_hours_cap)
            if revision.daily_payable_hours_cap is not None
            else None
        ),
        "eligibility_params": revision.eligibility_params,
        "formula_version": revision.formula_version,
    }


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
        eligible_seconds=calculation.eligible_seconds,
        payable_seconds=calculation.payable_seconds,
        excluded_seconds_by_reason=calculation.excluded_seconds_by_reason,
        inputs_fingerprint=calculation.inputs_fingerprint,
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
    rule, genesis_revision = await create_campaign_payout_rule(
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
        metadata={
            "campaign_id": str(campaign_id),
            "status": rule.status,
            "genesis_revision": payout_rule_revision_audit_values(genesis_revision),
        },
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
    "/admin/campaigns/{campaign_id}/payout-rules/{rule_id}/revisions",
    response_model=CampaignPayoutRuleRevisionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an effective-dated payout-rule revision (supersede)",
)
async def admin_create_payout_rule_revision(
    campaign_id: UUID,
    rule_id: UUID,
    payload: CampaignPayoutRuleRevisionCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> CampaignPayoutRuleRevisionRead:
    revision, previous = await create_payout_rule_revision(
        session,
        campaign_id=campaign_id,
        rule_id=rule_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.payout_rule_revision.created",
        entity_type="campaign_payout_rule_revision",
        entity_id=str(revision.id),
        metadata={
            "campaign_id": str(campaign_id),
            "payout_rule_id": str(rule_id),
            "reason": revision.reason,
            "before": payout_rule_revision_audit_values(previous),
            "after": payout_rule_revision_audit_values(revision),
        },
    )
    await session.commit()
    return payout_rule_revision_response(revision)


@router.get(
    "/admin/campaigns/{campaign_id}/payout-rules/{rule_id}/revisions",
    response_model=CampaignPayoutRuleRevisionListResponse,
    summary="List a campaign's payout-rule revisions",
)
async def admin_list_payout_rule_revisions(
    campaign_id: UUID,
    rule_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CampaignPayoutRuleRevisionListResponse:
    del current_user
    revisions, total = await list_payout_rule_revisions(
        session,
        campaign_id=campaign_id,
        rule_id=rule_id,
        limit=limit,
        offset=offset,
    )
    return CampaignPayoutRuleRevisionListResponse(
        items=[payout_rule_revision_response(revision) for revision in revisions],
        total=total,
        limit=limit,
        offset=offset,
    )


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
    start_at, end_at = ensure_payout_date_range(start_at, end_at)
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
        formula_versions=summary.formula_versions,
        totals_by_currency=[
            CampaignCostCurrencySummary(
                currency=total.currency,
                final_payout_total=total.final_payout_total,
                gross_payout_total=total.gross_payout_total,
                ledger_net_total=total.ledger_net_total,
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


@router.post(
    "/admin/payouts/recompute-day",
    response_model=RecomputePayoutDayResult,
    summary="Retired: direct day recompute now requires a correction order",
)
async def admin_recompute_payout_day(
    payload: RecomputePayoutDayRequest,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> RecomputePayoutDayResult:
    """PR7: the direct execute path is retired. Every retroactive recompute —
    regardless of delta sign — runs through an approved maker-checker
    correction order. The route stays registered so the contract and the
    audit-coverage table remain consistent; it always answers 409."""
    del payload, current_user, session, settings
    raise recompute_requires_correction_order()


def correction_order_response(order: PayoutCorrectionOrder) -> PayoutCorrectionOrderRead:
    return PayoutCorrectionOrderRead(
        id=order.id,
        campaign_id=order.campaign_id,
        lagos_day=order.lagos_day,
        status=PayoutCorrectionOrderStatus(order.status),
        created_by_user_id=order.created_by_user_id,
        approved_by_user_id=order.approved_by_user_id,
        executed_by_user_id=order.executed_by_user_id,
        reason=order.reason,
        projected_delta=order.projected_delta,
        projection_fingerprint=order.projection_fingerprint,
        projected_at=order.projected_at,
        decided_at=order.decided_at,
        executed_at=order.executed_at,
        execution_result=order.execution_result,
        created_at=order.created_at,
    )


def correction_order_audit_values(order: PayoutCorrectionOrder) -> dict:
    """Value-complete audit payload (C4): the order's full state, money
    amounts as Decimal strings inside projected_delta/execution_result."""
    return {
        "campaign_id": str(order.campaign_id),
        "lagos_day": order.lagos_day.isoformat(),
        "status": order.status,
        "reason": order.reason,
        "created_by_user_id": str(order.created_by_user_id),
        "approved_by_user_id": (
            str(order.approved_by_user_id)
            if order.approved_by_user_id is not None
            else None
        ),
        "executed_by_user_id": (
            str(order.executed_by_user_id)
            if order.executed_by_user_id is not None
            else None
        ),
        "projection_fingerprint": order.projection_fingerprint,
        "projected_delta": order.projected_delta,
        "projected_at": (
            order.projected_at.isoformat() if order.projected_at is not None else None
        ),
        "decided_at": (
            order.decided_at.isoformat() if order.decided_at is not None else None
        ),
        "executed_at": (
            order.executed_at.isoformat() if order.executed_at is not None else None
        ),
        "execution_result": order.execution_result,
    }


@router.get(
    "/admin/payouts/day-projection",
    response_model=PayoutDayProjection,
    summary="Dry-run projection of one campaign/Lagos-day recompute",
)
async def admin_project_payout_day(
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    campaign_id: UUID,
    lagos_day: date,
) -> PayoutDayProjection:
    """Side-effect-free replacement for the retired direct recompute: the PR6
    core in dry-run mode. Writes nothing and changes no order state."""
    del current_user
    projection = await project_campaign_day(
        session, campaign_id=campaign_id, lagos_day=lagos_day, settings=settings
    )
    return PayoutDayProjection(
        campaign_id=campaign_id,
        lagos_day=lagos_day,
        projected_delta=projection.projected_delta,
        projection_fingerprint=projection.fingerprint,
    )


@router.post(
    "/admin/payouts/correction-orders",
    response_model=PayoutCorrectionOrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Project a campaign/Lagos-day correction into a draft order",
)
async def admin_create_correction_order(
    payload: PayoutCorrectionOrderCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> PayoutCorrectionOrderRead:
    order = await create_correction_order(
        session,
        campaign_id=payload.campaign_id,
        lagos_day=payload.lagos_day,
        reason=payload.reason,
        created_by_user_id=current_user.id,
        settings=settings,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.payout_correction_order.created",
        entity_type="payout_correction_order",
        entity_id=str(order.id),
        metadata={
            "status_before": None,
            "status_after": order.status,
            **correction_order_audit_values(order),
        },
    )
    await session.commit()
    return correction_order_response(order)


@router.get(
    "/admin/payouts/correction-orders",
    response_model=PayoutCorrectionOrderListResponse,
    summary="List payout correction orders",
)
async def admin_list_correction_orders(
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    campaign_id: UUID | None = None,
    status: PayoutCorrectionOrderStatus | None = None,
) -> PayoutCorrectionOrderListResponse:
    del current_user
    orders, total = await list_correction_orders(
        session,
        limit=limit,
        offset=offset,
        campaign_id=campaign_id,
        order_status=status,
    )
    return PayoutCorrectionOrderListResponse(
        items=[correction_order_response(order) for order in orders],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/payouts/correction-orders/{order_id}",
    response_model=PayoutCorrectionOrderRead,
    summary="Read one payout correction order",
)
async def admin_get_correction_order(
    order_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> PayoutCorrectionOrderRead:
    del current_user
    order = await get_correction_order(session, order_id)
    return correction_order_response(order)


@router.post(
    "/admin/payouts/correction-orders/{order_id}/submit",
    response_model=PayoutCorrectionOrderRead,
    summary="Submit a draft correction order for approval",
)
async def admin_submit_correction_order(
    order_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> PayoutCorrectionOrderRead:
    order = await submit_correction_order(
        session, order_id=order_id, actor_user_id=current_user.id
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.payout_correction_order.submitted",
        entity_type="payout_correction_order",
        entity_id=str(order.id),
        metadata={
            "status_before": PayoutCorrectionOrderStatus.DRAFT.value,
            "status_after": order.status,
            **correction_order_audit_values(order),
        },
    )
    await session.commit()
    return correction_order_response(order)


@router.post(
    "/admin/payouts/correction-orders/{order_id}/approve",
    response_model=PayoutCorrectionOrderRead,
    summary="Approve a correction order (approver must differ from creator)",
)
async def admin_approve_correction_order(
    order_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> PayoutCorrectionOrderRead:
    order = await approve_correction_order(
        session, order_id=order_id, actor_user_id=current_user.id, settings=settings
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.payout_correction_order.approved",
        entity_type="payout_correction_order",
        entity_id=str(order.id),
        metadata={
            "status_before": PayoutCorrectionOrderStatus.PENDING_APPROVAL.value,
            "status_after": order.status,
            **correction_order_audit_values(order),
        },
    )
    await session.commit()
    return correction_order_response(order)


@router.post(
    "/admin/payouts/correction-orders/{order_id}/reject",
    response_model=PayoutCorrectionOrderRead,
    summary="Reject a pending correction order",
)
async def admin_reject_correction_order(
    order_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> PayoutCorrectionOrderRead:
    order = await reject_correction_order(
        session, order_id=order_id, actor_user_id=current_user.id
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.payout_correction_order.rejected",
        entity_type="payout_correction_order",
        entity_id=str(order.id),
        metadata={
            "status_before": PayoutCorrectionOrderStatus.PENDING_APPROVAL.value,
            "status_after": order.status,
            "rejected_by_user_id": str(current_user.id),
            **correction_order_audit_values(order),
        },
    )
    await session.commit()
    return correction_order_response(order)


@router.post(
    "/admin/payouts/correction-orders/{order_id}/execute",
    response_model=PayoutCorrectionOrderRead,
    summary="Execute an approved correction order (idempotent)",
)
async def admin_execute_correction_order(
    order_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    payload: Annotated[PayoutCorrectionOrderExecuteRequest | None, Body()] = None,
) -> PayoutCorrectionOrderRead:
    request = payload or PayoutCorrectionOrderExecuteRequest()
    order, executed_now = await execute_correction_order(
        session,
        order_id=order_id,
        actor_user_id=current_user.id,
        release_at=request.release_at,
        request_metadata=request.metadata,
        settings=settings,
    )
    if executed_now:
        await create_audit_event(
            session,
            actor_user_id=current_user.id,
            action="admin.payout_correction_order.executed",
            entity_type="payout_correction_order",
            entity_id=str(order.id),
            metadata={
                "status_before": PayoutCorrectionOrderStatus.APPROVED.value,
                "status_after": order.status,
                "release_at": (
                    request.release_at.isoformat()
                    if request.release_at is not None
                    else None
                ),
                **correction_order_audit_values(order),
            },
        )
        await session.commit()
    # Idempotent replay: no mutation happened, return the recorded result.
    return correction_order_response(order)


@router.get(
    "/driver/trips/{trip_id}/earnings-breakdown",
    response_model=DriverTripEarningsBreakdown,
    summary="Read the current driver's trip earnings breakdown",
)
async def driver_get_trip_earnings_breakdown(
    trip_id: UUID,
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> DriverTripEarningsBreakdown:
    breakdown = await driver_trip_earnings_breakdown(
        session,
        user_id=current_user.id,
        trip_id=trip_id,
    )
    cap = None
    if (
        breakdown.lagos_day is not None
        and breakdown.cap_seconds is not None
        and breakdown.day_payable_seconds is not None
    ):
        cap = DriverTripEarningsCapProgress(
            lagos_day=breakdown.lagos_day,
            cap_seconds=breakdown.cap_seconds,
            day_payable_seconds=breakdown.day_payable_seconds,
        )
    return DriverTripEarningsBreakdown(
        trip_session_id=breakdown.trip_session_id,
        formula_version=breakdown.formula_version,
        currency=breakdown.currency,
        amount=breakdown.amount,
        eligible_seconds=breakdown.eligible_seconds,
        excluded_seconds_by_reason=breakdown.excluded_seconds_by_reason,
        hourly_rate=breakdown.hourly_rate,
        capped_seconds=breakdown.capped_seconds,
        superseded_by_recompute=breakdown.superseded_by_recompute,
        entries=[ledger_entry_response(entry) for entry in breakdown.entries],
        cap=cap,
    )

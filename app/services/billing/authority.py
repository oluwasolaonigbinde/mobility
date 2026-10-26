"""Billing: authority domain operations."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.billing import (
    CampaignFinancialAuthorization,
    CampaignLiabilityReservation,
    CommercialTerms,
    ExpeditedProductionWaiver,
    FinancialAuthorityType,
    FinancialAuthorizationAllocation,
    PaymentClass,
    PaymentReceipt,
    ProductionAuthorityBasis,
    ProductionStart,
    ReceiptAllocation,
)
from app.models.campaign import Campaign
from app.models.campaign_assignment import CampaignAssignment
from app.models.campaign_cancellation import (
    CampaignCancellation,
)
from app.models.payout import AssignmentRuleBinding
from app.models.user import User, UserStatus
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.billing.common import (
    DAILY_RATE_LIABILITY_FORMULA_VERSION,
    EXPEDITED_WAIVER_WORDING,
    EXPEDITED_WAIVER_WORDING_HASH,
    EXPEDITED_WAIVER_WORDING_VERSION,
    LAGOS_TZ,
    MONEY_QUANTUM,
    _aware_utc,
    _campaign,
    _money,
    _stored_aware_utc,
)
from app.services.billing.queries import (
    _active_cash_allocations,
    _active_receipt_predicate,
    _commercial_terms_for_campaign,
    effective_invoice_obligation,
)
from app.services.campaigns import get_required_advertiser_context
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock


async def effective_financial_authorization(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    effective_at: datetime | None = None,
) -> CampaignFinancialAuthorization | None:
    at = effective_at or await database_clock(session)
    return await session.scalar(
        select(CampaignFinancialAuthorization)
        .where(
            CampaignFinancialAuthorization.campaign_id == campaign_id,
            CampaignFinancialAuthorization.effective_from <= at,
        )
        .order_by(
            CampaignFinancialAuthorization.effective_from.desc(),
            CampaignFinancialAuthorization.revision_number.desc(),
        )
        .limit(1)
    )


async def _latest_financial_authorization(
    session: AsyncSession, campaign_id: UUID
) -> CampaignFinancialAuthorization | None:
    return await session.scalar(
        select(CampaignFinancialAuthorization)
        .where(CampaignFinancialAuthorization.campaign_id == campaign_id)
        .order_by(CampaignFinancialAuthorization.revision_number.desc())
        .limit(1)
        .with_for_update()
    )


async def _append_financial_authorization(  # noqa: C901
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    authority_type: FinancialAuthorityType,
    authorized_amount: Decimal,
    max_driver_liability: Decimal,
    reason: str,
    cash_allocations: list[ReceiptAllocation] | None = None,
    credit_due_at: datetime | None = None,
    credit_approved_by_user_id: UUID | None = None,
    credit_terms: dict | None = None,
) -> CampaignFinancialAuthorization:
    await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    campaign = await _campaign(session, campaign_id, lock=True)
    terms = await _commercial_terms_for_campaign(session, campaign_id)
    if terms is None:
        raise AppError(
            "COMMERCIAL_TERMS_REQUIRED",
            "Accepted commercial terms are required before financial authorization",
            status_code=status.HTTP_409_CONFLICT,
        )
    if terms.currency != campaign.currency:
        raise AppError(
            "FINANCIAL_AUTHORITY_CURRENCY_MISMATCH",
            "Campaign and accepted commercial terms currency must match",
            status_code=status.HTTP_409_CONFLICT,
        )
    terms = await _commercial_terms_for_campaign(session, campaign_id, lock=True)
    if terms is None:
        raise AppError(
            "COMMERCIAL_TERMS_REQUIRED",
            "Accepted commercial terms are required before financial authorization",
            status_code=status.HTTP_409_CONFLICT,
        )
    if authority_type == FinancialAuthorityType.PREPAID_CASH:
        current_allocations = await _active_cash_allocations(session, terms.id)
        authorized_amount = sum(
            (Decimal(row.amount) for row in current_allocations), Decimal("0.00")
        )
        cash_allocations = current_allocations
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise AppError(
            "FINANCIAL_AUTHORITY_REASON_REQUIRED",
            "A financial authorization reason is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if authorized_amount <= 0 or max_driver_liability <= 0:
        raise AppError(
            "INVALID_FINANCIAL_AUTHORITY_AMOUNT",
            "Authorized amount and maximum driver liability must be positive",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if max_driver_liability > authorized_amount:
        raise AppError(
            "DRIVER_LIABILITY_EXCEEDS_AUTHORITY",
            "Maximum driver liability cannot exceed financial authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    latest = await _latest_financial_authorization(session, campaign_id)
    if latest is not None and (
        authorized_amount < Decimal(latest.authorized_amount)
        or max_driver_liability < Decimal(latest.max_driver_liability)
    ):
        raise AppError(
            "FINANCIAL_AUTHORITY_REDUCTION_REQUIRES_GOVERNANCE",
            "Package 3 permits funded expansions only; reductions require governed revision",
            status_code=status.HTTP_409_CONFLICT,
        )
    normalized_credit_terms = deepcopy(credit_terms) if credit_terms is not None else None
    if latest is not None and all(
        (
            latest.authority_type == authority_type,
            Decimal(latest.authorized_amount) == authorized_amount,
            Decimal(latest.max_driver_liability) == max_driver_liability,
            latest.credit_due_at == credit_due_at,
            latest.credit_approved_by_user_id == credit_approved_by_user_id,
            latest.credit_terms == normalized_credit_terms,
        )
    ):
        return latest
    now = await database_clock(session)
    authorization = CampaignFinancialAuthorization(
        campaign_id=campaign_id,
        commercial_terms_id=terms.id,
        revision_number=1 if latest is None else latest.revision_number + 1,
        authority_type=authority_type,
        currency=terms.currency,
        authorized_amount=authorized_amount,
        funded_cash_amount=(
            authorized_amount
            if authority_type == FinancialAuthorityType.PREPAID_CASH
            else Decimal("0.00")
        ),
        max_driver_liability=max_driver_liability,
        credit_limit=(
            authorized_amount if authority_type == FinancialAuthorityType.APPROVED_CREDIT else None
        ),
        credit_due_at=credit_due_at,
        credit_approved_by_user_id=credit_approved_by_user_id,
        credit_terms=normalized_credit_terms,
        effective_from=now,
        created_by_user_id=actor_user_id,
        reason=normalized_reason,
        created_at=now,
    )
    session.add(authorization)
    await session.flush()
    for allocation in cash_allocations or []:
        session.add(
            FinancialAuthorizationAllocation(
                authorization_id=authorization.id,
                receipt_allocation_id=allocation.id,
                amount=allocation.amount,
            )
        )
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.financial_authority.recorded",
        entity_type="campaign_financial_authorization",
        entity_id=str(authorization.id),
        metadata={
            "campaign_id": str(campaign_id),
            "revision_number": authorization.revision_number,
            "authority_type": authority_type.value,
            "authorized_amount": f"{authorized_amount:.2f}",
            "max_driver_liability": f"{max_driver_liability:.2f}",
            "currency": terms.currency,
        },
    )
    return authorization


async def record_prepaid_cash_authorization(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    max_driver_liability: Decimal | str,
    reason: str,
) -> CampaignFinancialAuthorization:
    if await session.scalar(select(Campaign.id).where(Campaign.id == campaign_id)) is None:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    terms = await _commercial_terms_for_campaign(session, campaign_id)
    if terms is None:
        raise AppError(
            "COMMERCIAL_TERMS_REQUIRED", "Accepted commercial terms are required", status_code=409
        )
    if terms.payment_class != PaymentClass.STANDARD_PREPAID:
        raise AppError(
            "PREPAID_AUTHORITY_NOT_PERMITTED",
            "The accepted terms do not permit prepaid-cash authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    allocations = await _active_cash_allocations(session, terms.id)
    funded = sum((Decimal(row.amount) for row in allocations), Decimal("0.00"))
    if funded <= 0:
        raise AppError(
            "CONFIRMED_FUNDING_REQUIRED",
            "Confirmed active allocations are required for prepaid authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    liability = _money(max_driver_liability, "max_driver_liability")
    return await _append_financial_authorization(
        session,
        campaign_id=campaign_id,
        actor_user_id=actor_user_id,
        authority_type=FinancialAuthorityType.PREPAID_CASH,
        authorized_amount=funded,
        max_driver_liability=liability,
        reason=reason,
        cash_allocations=allocations,
    )


async def record_approved_credit_authorization(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    credit_limit: Decimal | str,
    max_driver_liability: Decimal | str,
    due_at: datetime,
    approved_by_user_id: UUID,
    credit_terms: dict,
    reason: str,
) -> CampaignFinancialAuthorization:
    await acquire_campaign_terms_lock(session, campaign_id)
    for admin_user_id in sorted(
        {actor_user_id, approved_by_user_id}, key=lambda user_id: user_id.int
    ):
        await require_active_admin(session, admin_user_id)
    terms = await _commercial_terms_for_campaign(session, campaign_id)
    if terms is None or terms.payment_class != PaymentClass.APPROVED_CORPORATE_CREDIT:
        raise AppError(
            "APPROVED_CREDIT_TERMS_REQUIRED",
            "Accepted approved-corporate-credit terms are required",
            status_code=status.HTTP_409_CONFLICT,
        )
    normalized_due_at = _aware_utc(due_at)
    now = await database_clock(session)
    if normalized_due_at <= now or not isinstance(credit_terms, dict) or not credit_terms:
        raise AppError(
            "INVALID_CREDIT_APPROVAL",
            "Credit approval requires a future due date and a non-empty terms snapshot",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return await _append_financial_authorization(
        session,
        campaign_id=campaign_id,
        actor_user_id=actor_user_id,
        authority_type=FinancialAuthorityType.APPROVED_CREDIT,
        authorized_amount=_money(credit_limit, "credit_limit"),
        max_driver_liability=_money(max_driver_liability, "max_driver_liability"),
        reason=reason,
        credit_due_at=normalized_due_at,
        credit_approved_by_user_id=approved_by_user_id,
        credit_terms=credit_terms,
    )


async def _authorization_usable_liability(
    session: AsyncSession,
    authorization: CampaignFinancialAuthorization,
    *,
    effective_at: datetime | None = None,
) -> Decimal:
    if authorization.authority_type == FinancialAuthorityType.APPROVED_CREDIT:
        at = effective_at or await database_clock(session)
        if (
            authorization.credit_due_at is None
            or _stored_aware_utc(authorization.credit_due_at) <= at
        ):
            return Decimal("0.00")
    if authorization.authority_type != FinancialAuthorityType.PREPAID_CASH:
        return Decimal(authorization.max_driver_liability)
    receipt = PaymentReceipt.__table__.alias("active_authority_receipt")
    confirmed, not_reversed = _active_receipt_predicate(receipt)
    active_sources = await session.scalar(
        select(func.coalesce(func.sum(FinancialAuthorizationAllocation.amount), 0))
        .join(
            ReceiptAllocation,
            ReceiptAllocation.id == FinancialAuthorizationAllocation.receipt_allocation_id,
        )
        .join(receipt, receipt.c.id == ReceiptAllocation.receipt_id)
        .where(
            FinancialAuthorizationAllocation.authorization_id == authorization.id,
            confirmed,
            not_reversed,
        )
    )
    return min(Decimal(authorization.max_driver_liability), Decimal(active_sources or 0))


async def reserved_campaign_liability_total(
    session: AsyncSession,
    *,
    campaign_id: UUID,
) -> Decimal:
    from app.models.campaign_cancellation import CampaignCancellation
    from app.models.campaign_change import CampaignChangeRequest

    cancelled = await session.scalar(
        select(CampaignCancellation.id).where(CampaignCancellation.campaign_id == campaign_id)
    )
    if cancelled is not None:
        return Decimal("0.00")

    assignment_total = await session.scalar(
        select(func.coalesce(func.sum(CampaignLiabilityReservation.reserved_amount), 0)).where(
            CampaignLiabilityReservation.campaign_id == campaign_id,
            CampaignLiabilityReservation.status == "reserved",
        )
    )
    change_total = await session.scalar(
        select(func.coalesce(func.sum(CampaignChangeRequest.reserved_liability_amount), 0)).where(
            CampaignChangeRequest.campaign_id == campaign_id,
            CampaignChangeRequest.status == "applied",
        )
    )
    return Decimal(assignment_total or 0) + Decimal(change_total or 0)


@dataclass(frozen=True)
class AssignmentLiabilityCalculation:
    binding: AssignmentRuleBinding
    authorization: CampaignFinancialAuthorization | None
    covered_days: int
    rate: Decimal
    cap: Decimal
    requested: Decimal
    now: datetime
    can_reserve: bool


def _liability_formula_version(binding: AssignmentRuleBinding) -> str:
    return DAILY_RATE_LIABILITY_FORMULA_VERSION


async def _assignment_liability_calculation(
    session: AsyncSession, assignment: CampaignAssignment
) -> AssignmentLiabilityCalculation:
    if (
        await session.scalar(
            select(CampaignCancellation.id).where(
                CampaignCancellation.campaign_id == assignment.campaign_id
            )
        )
        is not None
    ):
        raise AppError(
            "CAMPAIGN_FINANCIAL_CUTOFF",
            "Cancelled campaign liability cannot be reserved",
            status_code=status.HTTP_409_CONFLICT,
        )
    binding = await session.scalar(
        select(AssignmentRuleBinding).where(AssignmentRuleBinding.assignment_id == assignment.id)
    )
    frozen_ceiling = None if binding is None else binding.daily_rate_naira
    if (
        binding is None
        or binding.formula_version != "payout_v4"
        or frozen_ceiling is None
        or binding.campaign_window_start_at is None
        or binding.campaign_window_end_at is None
    ):
        raise AppError(
            "FROZEN_PAYOUT_BINDING_REQUIRED",
            "A frozen rate and daily cap are required before reserving liability",
            status_code=status.HTTP_409_CONFLICT,
        )
    start_date = _stored_aware_utc(binding.campaign_window_start_at).astimezone(LAGOS_TZ).date()
    end_date = _stored_aware_utc(binding.campaign_window_end_at).astimezone(LAGOS_TZ).date()
    covered_days = max(1, (end_date - start_date).days + 1)
    rate, cap = Decimal(frozen_ceiling), Decimal("1")
    requested = (rate * cap * covered_days).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    if requested <= 0:
        raise AppError(
            "ZERO_LIABILITY_RESERVE",
            "The frozen payout contract does not create positive liability",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    authorization = await effective_financial_authorization(
        session, campaign_id=assignment.campaign_id, effective_at=now
    )
    reserved_total = await reserved_campaign_liability_total(
        session,
        campaign_id=assignment.campaign_id,
    )
    usable = (
        await _authorization_usable_liability(session, authorization, effective_at=now)
        if authorization is not None
        else Decimal("0.00")
    )
    can_reserve = authorization is not None and usable - reserved_total >= requested
    return AssignmentLiabilityCalculation(
        binding, authorization, covered_days, rate, cap, requested, now, can_reserve
    )


@dataclass(frozen=True)
class AssignmentLiabilityReadiness:
    eligible: bool
    existing_reservation_id: UUID | None
    reason: str | None


async def assignment_liability_readiness(
    session: AsyncSession, *, assignment_id: UUID
) -> AssignmentLiabilityReadiness:
    assignment = await session.get(CampaignAssignment, assignment_id)
    if assignment is None:
        raise AppError("ASSIGNMENT_NOT_FOUND", "Assignment was not found", status_code=404)
    existing = await session.scalar(
        select(CampaignLiabilityReservation).where(
            CampaignLiabilityReservation.assignment_id == assignment_id
        )
    )
    try:
        calculation = await _assignment_liability_calculation(session, assignment)
        if existing is not None and Decimal(existing.requested_amount) != calculation.requested:
            return AssignmentLiabilityReadiness(False, existing.id, "Frozen liability changed")
        if existing is not None and existing.status == "released":
            return AssignmentLiabilityReadiness(False, existing.id, "Liability was released")
        already_reserved = existing is not None and existing.status == "reserved"
        if not already_reserved and not calculation.can_reserve:
            return AssignmentLiabilityReadiness(
                False,
                existing.id if existing else None,
                "Current funding cannot cover the assignment",
            )
        authorization = await assert_campaign_production_authorized(
            session, campaign_id=assignment.campaign_id
        )
        await _assert_authorization_covers_liability(
            session,
            authorization,
            campaign_id=assignment.campaign_id,
            additional=Decimal("0.00") if already_reserved else calculation.requested,
        )
    except AppError as error:
        return AssignmentLiabilityReadiness(False, existing.id if existing else None, error.message)
    return AssignmentLiabilityReadiness(True, existing.id if existing else None, None)


async def reserve_assignment_liability(
    session: AsyncSession,
    *,
    assignment_id: UUID,
    actor_user_id: UUID,
    require_admin: bool = True,
) -> CampaignLiabilityReservation:
    if not require_admin:
        actor = await session.get(User, actor_user_id)
        if actor is None or actor.status != UserStatus.ACTIVE:
            raise AppError(
                "ACTIVE_ACTOR_REQUIRED",
                "An active user is required to reserve assignment liability",
                status_code=status.HTTP_403_FORBIDDEN,
            )
    campaign_id = await session.scalar(
        select(CampaignAssignment.campaign_id).where(CampaignAssignment.id == assignment_id)
    )
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    if require_admin:
        await require_active_admin(session, actor_user_id)
    assignment = await session.get(CampaignAssignment, assignment_id)
    if assignment is None:
        raise AppError("ASSIGNMENT_NOT_FOUND", "Assignment was not found", status_code=404)
    assert campaign_id == assignment.campaign_id
    await _campaign(session, assignment.campaign_id, lock=True)
    calculation = await _assignment_liability_calculation(session, assignment)
    binding, authorization = calculation.binding, calculation.authorization
    authorization_id = authorization.id if authorization is not None else None
    requested, now, can_reserve = calculation.requested, calculation.now, calculation.can_reserve
    covered_days, rate, cap = calculation.covered_days, calculation.rate, calculation.cap
    assignment = await session.scalar(
        select(CampaignAssignment).where(CampaignAssignment.id == assignment_id).with_for_update()
    )
    if assignment is None:
        raise AppError("ASSIGNMENT_NOT_FOUND", "Assignment was not found", status_code=404)
    existing = await session.scalar(
        select(CampaignLiabilityReservation)
        .where(CampaignLiabilityReservation.assignment_id == assignment.id)
        .with_for_update()
    )
    if existing is not None and Decimal(existing.requested_amount) != requested:
        raise AppError(
            "LIABILITY_RESERVATION_IMMUTABLE",
            "The assignment liability request is already frozen",
            status_code=status.HTTP_409_CONFLICT,
        )
    if existing is None:
        existing = CampaignLiabilityReservation(
            campaign_id=assignment.campaign_id,
            assignment_id=assignment.id,
            assignment_rule_binding_id=binding.id,
            authorization_id=authorization_id if can_reserve else None,
            status="reserved" if can_reserve else "pending_funding",
            covered_vehicle_days=covered_days,
            hourly_rate=rate,
            daily_hours_cap=cap,
            requested_amount=requested,
            reserved_amount=requested if can_reserve else None,
            requested_at=now,
            reserved_at=now if can_reserve else None,
            formula_version=_liability_formula_version(binding),
        )
        session.add(existing)
    elif existing.status == "pending_funding" and can_reserve:
        existing.authorization_id = authorization_id
        existing.status = "reserved"
        existing.reserved_amount = requested
        existing.reserved_at = now
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.liability_reservation.recorded",
        entity_type="campaign_liability_reservation",
        entity_id=str(existing.id),
        metadata={
            "campaign_id": str(assignment.campaign_id),
            "assignment_id": str(assignment.id),
            "status": existing.status,
            "requested_amount": f"{requested:.2f}",
            "formula_version": existing.formula_version,
        },
    )
    return existing


async def record_expedited_production_waiver(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    wording_version: str,
    accepted_wording: str,
    accepted_wording_hash: str,
) -> ExpeditedProductionWaiver:
    organization, _ = await get_required_advertiser_context(
        session, actor_user_id, require_write=True
    )
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await _campaign(session, campaign_id, lock=True)
    if campaign.organization_id != organization.id:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    terms = await _commercial_terms_for_campaign(session, campaign_id, lock=True)
    if terms is None or not wording_version or not accepted_wording or not accepted_wording_hash:
        raise AppError(
            "EXPEDITED_WAIVER_EVIDENCE_REQUIRED",
            "Accepted terms, wording version, wording and wording hash are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if (
        wording_version != EXPEDITED_WAIVER_WORDING_VERSION
        or accepted_wording != EXPEDITED_WAIVER_WORDING
        or accepted_wording_hash != EXPEDITED_WAIVER_WORDING_HASH
    ):
        raise AppError(
            "EXPEDITED_WAIVER_COPY_MISMATCH",
            "The expedited-production waiver copy is not the approved canonical version",
            status_code=status.HTTP_409_CONFLICT,
        )
    existing = await session.scalar(
        select(ExpeditedProductionWaiver).where(
            ExpeditedProductionWaiver.campaign_id == campaign_id
        )
    )
    if existing is not None:
        if (
            existing.accepted_by_user_id == actor_user_id
            and existing.commercial_terms_id == terms.id
            and existing.wording_version == EXPEDITED_WAIVER_WORDING_VERSION
            and existing.accepted_wording_hash == EXPEDITED_WAIVER_WORDING_HASH
        ):
            return existing
        raise AppError(
            "EXPEDITED_WAIVER_IMMUTABLE",
            "An immutable expedited-production waiver already exists",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    waiver = ExpeditedProductionWaiver(
        campaign_id=campaign_id,
        commercial_terms_id=terms.id,
        requested_by_user_id=actor_user_id,
        requested_at=now,
        accepted_by_user_id=actor_user_id,
        accepted_at=now,
        wording_version=EXPEDITED_WAIVER_WORDING_VERSION,
        accepted_wording_hash=EXPEDITED_WAIVER_WORDING_HASH,
    )
    session.add(waiver)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.expedited_waiver.accepted",
        entity_type="expedited_production_waiver",
        entity_id=str(waiver.id),
        metadata={
            "campaign_id": str(campaign_id),
            "wording_version": EXPEDITED_WAIVER_WORDING_VERSION,
            "accepted_wording_hash": EXPEDITED_WAIVER_WORDING_HASH,
        },
    )
    return waiver


async def _fully_funded_at(session: AsyncSession, terms: CommercialTerms) -> datetime | None:
    obligation = await effective_invoice_obligation(session, commercial_terms_id=terms.id)
    if obligation == 0:
        return await database_clock(session)
    cumulative = Decimal("0.00")
    for allocation in await _active_cash_allocations(session, terms.id):
        cumulative += Decimal(allocation.amount)
        if cumulative >= obligation:
            return allocation.allocated_at
    return None


async def record_production_start(  # noqa: C901
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    waiver_id: UUID | None = None,
) -> ProductionStart:
    await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    await _campaign(session, campaign_id, lock=True)
    from app.models.campaign_cancellation import CampaignCancellation

    if (
        await session.scalar(
            select(CampaignCancellation.id).where(CampaignCancellation.campaign_id == campaign_id)
        )
        is not None
    ):
        raise AppError(
            "CAMPAIGN_FINANCIAL_CUTOFF",
            "Cancelled campaign production cannot start",
            status_code=status.HTTP_409_CONFLICT,
        )
    existing = await session.scalar(
        select(ProductionStart).where(ProductionStart.campaign_id == campaign_id)
    )
    if existing is not None:
        return existing
    terms = await _commercial_terms_for_campaign(session, campaign_id, lock=True)
    now = await database_clock(session)
    authorization = await effective_financial_authorization(
        session, campaign_id=campaign_id, effective_at=now
    )
    if terms is None or authorization is None:
        raise AppError(
            "PRODUCTION_FINANCIAL_AUTHORITY_REQUIRED",
            "Production requires accepted terms and effective financial authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    fully_funded_at: datetime | None = None
    waiver: ExpeditedProductionWaiver | None = None
    if authorization.authority_type == FinancialAuthorityType.APPROVED_CREDIT:
        if (
            authorization.credit_due_at is None
            or _stored_aware_utc(authorization.credit_due_at) <= now
        ):
            raise AppError(
                "CREDIT_AUTHORITY_EXPIRED",
                "Approved credit is no longer valid for production start",
                status_code=status.HTTP_409_CONFLICT,
            )
        basis = ProductionAuthorityBasis.APPROVED_CREDIT
        if waiver_id is not None:
            raise AppError(
                "WAIVER_NOT_APPLICABLE",
                "Expedited waiver is not applicable to approved-credit production",
                status_code=status.HTTP_409_CONFLICT,
            )
    elif authorization.authority_type == FinancialAuthorityType.PREPAID_CASH:
        fully_funded_at = await _fully_funded_at(session, terms)
        if fully_funded_at is None:
            raise AppError(
                "FULL_FUNDING_REQUIRED",
                "Standard production requires confirmed allocations covering the full amount",
                status_code=status.HTTP_409_CONFLICT,
            )
        if waiver_id is None:
            boundary = fully_funded_at + timedelta(hours=terms.standard_production_wait_hours)
            if now < boundary:
                raise AppError(
                    "PRODUCTION_WAIT_ACTIVE",
                    "The exact 24-hour standard production wait has not elapsed",
                    status_code=status.HTTP_409_CONFLICT,
                )
            basis = ProductionAuthorityBasis.STANDARD_WINDOW_ELAPSED
        else:
            waiver = await session.get(ExpeditedProductionWaiver, waiver_id)
            if (
                waiver is None
                or waiver.campaign_id != campaign_id
                or _stored_aware_utc(waiver.accepted_at) > now
            ):
                raise AppError(
                    "VALID_EXPEDITED_WAIVER_REQUIRED",
                    "A valid immutable advertiser waiver is required",
                    status_code=status.HTTP_409_CONFLICT,
                )
            basis = ProductionAuthorityBasis.ADVERTISER_EXPEDITED_WAIVER
    else:
        raise AppError(
            "FINANCIAL_AUTHORITY_NOT_PRODUCTION_AUTHORITY",
            "Confirmed cash or approved credit is required before production can start",
            status_code=status.HTTP_409_CONFLICT,
        )
    production_start = ProductionStart(
        campaign_id=campaign_id,
        authorization_id=authorization.id,
        authority_basis=basis,
        waiver_id=waiver.id if waiver is not None else None,
        fully_funded_at=fully_funded_at,
        started_by_user_id=actor_user_id,
        started_at=now,
    )
    session.add(production_start)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.production.started",
        entity_type="production_start",
        entity_id=str(production_start.id),
        metadata={"campaign_id": str(campaign_id), "authority_basis": basis.value},
    )
    return production_start


async def assert_new_work_authorized(
    session: AsyncSession, *, campaign_id: UUID, assignment_id: UUID
) -> None:
    from app.models.campaign_cancellation import CampaignCancellation

    if (
        await session.scalar(
            select(CampaignCancellation.id).where(CampaignCancellation.campaign_id == campaign_id)
        )
        is not None
    ):
        raise AppError(
            "CAMPAIGN_FINANCIAL_CUTOFF",
            "The campaign cancellation cutoff blocks new work",
            status_code=status.HTTP_409_CONFLICT,
        )
    try:
        authorization = await assert_campaign_production_authorized(
            session, campaign_id=campaign_id
        )
    except AppError as exc:
        if exc.code == "CREDIT_AUTHORITY_EXPIRED":
            raise
        raise AppError(
            "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED",
            "Current campaign funding does not authorize new work",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    reservation = await session.scalar(
        select(CampaignLiabilityReservation).where(
            CampaignLiabilityReservation.campaign_id == campaign_id,
            CampaignLiabilityReservation.assignment_id == assignment_id,
            CampaignLiabilityReservation.status == "reserved",
        )
    )
    if reservation is None:
        raise AppError(
            "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED",
            "Production start and a funded assignment liability reserve are required",
            status_code=status.HTTP_409_CONFLICT,
        )
    await _assert_authorization_covers_liability(session, authorization, campaign_id=campaign_id)


async def _assert_authorization_covers_liability(
    session: AsyncSession,
    authorization: CampaignFinancialAuthorization,
    *,
    campaign_id: UUID,
    additional: Decimal = Decimal("0.00"),
) -> None:
    usable = await _authorization_usable_liability(session, authorization)
    reserved_total = await reserved_campaign_liability_total(
        session,
        campaign_id=campaign_id,
    )
    if usable < reserved_total + additional:
        raise AppError(
            "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED",
            "Current financial authority no longer covers reserved driver liability",
            status_code=status.HTTP_409_CONFLICT,
        )


async def assert_campaign_production_authorized(
    session: AsyncSession, *, campaign_id: UUID
) -> CampaignFinancialAuthorization:
    await acquire_campaign_terms_lock(session, campaign_id)
    terms = await _commercial_terms_for_campaign(session, campaign_id)
    production_start = await session.scalar(
        select(ProductionStart).where(ProductionStart.campaign_id == campaign_id)
    )
    now = await database_clock(session)
    authorization = await effective_financial_authorization(
        session, campaign_id=campaign_id, effective_at=now
    )
    if terms is None or production_start is None or authorization is None:
        raise AppError(
            "PRODUCTION_FINANCIAL_AUTHORITY_REQUIRED",
            "Campaign activation requires accepted terms and current production authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    usable = await _authorization_usable_liability(session, authorization, effective_at=now)
    if authorization.authority_type == FinancialAuthorityType.APPROVED_CREDIT:
        if usable <= 0:
            raise AppError(
                "CREDIT_AUTHORITY_EXPIRED",
                "Approved credit is no longer valid for new work",
                status_code=status.HTTP_409_CONFLICT,
            )
    elif authorization.authority_type == FinancialAuthorityType.PREPAID_CASH:
        if await _fully_funded_at(session, terms) is None or usable <= 0:
            raise AppError(
                "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED",
                "Confirmed cash authority no longer covers new work",
                status_code=status.HTTP_409_CONFLICT,
            )
    else:
        raise AppError(
            "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED",
            "Subsidy authority does not authorize advertiser production",
            status_code=status.HTTP_409_CONFLICT,
        )
    return authorization

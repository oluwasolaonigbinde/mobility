import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.billing import (
    CampaignLiabilityReservation,
    CommercialTerms,
    PaymentClass,
    ReceiptAllocation,
    RefundSettlement,
    SettlementDisposition,
)
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_assignment import (
    CampaignActivationEventType,
    CampaignAssignment,
    CampaignAssignmentStatus,
)
from app.models.campaign_cancellation import (
    CampaignCancellation,
    CampaignCancellationDisposition,
    CampaignCancellationSettlementRevision,
)
from app.models.campaign_change import CampaignChangeRequest, CampaignChangeStatus
from app.schemas.campaign_cancellations import CampaignCancellationCreate
from app.services.audit import create_audit_event
from app.services.billing import _commercial_terms_for_campaign, _refund_window
from app.services.campaign_assignments import create_activation_event
from app.services.campaigns import get_required_advertiser_context
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _digest(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _error(code: str, message: str, status_code: int = 409) -> AppError:
    return AppError(code, message, status_code=status_code)


async def campaign_financial_cutoff(
    session: AsyncSession, campaign_id: UUID
) -> datetime | None:
    value = await session.scalar(
        select(CampaignCancellation.cutoff_at).where(
            CampaignCancellation.campaign_id == campaign_id
        )
    )
    return _aware(value) if value is not None else None


async def effective_trip_end(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    ended_at: datetime,
) -> datetime:
    cutoff = await campaign_financial_cutoff(session, campaign_id)
    end = _aware(ended_at)
    return min(end, cutoff) if cutoff is not None else end


async def _cash_remaining_for_terms(
    session: AsyncSession, commercial_terms_id: UUID
) -> Decimal:
    allocated = Decimal(
        await session.scalar(
            select(func.coalesce(func.sum(ReceiptAllocation.amount), 0)).where(
                ReceiptAllocation.commercial_terms_id == commercial_terms_id
            )
        )
        or 0
    )
    refunded = Decimal(
        await session.scalar(
            select(func.coalesce(func.sum(RefundSettlement.amount), 0)).where(
                RefundSettlement.commercial_terms_id == commercial_terms_id,
                RefundSettlement.disposition == SettlementDisposition.REFUND_RECORDED.value,
            )
        )
        or 0
    )
    return max(Decimal("0.00"), allocated - refunded)


async def request_campaign_cancellation(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    campaign_id: UUID,
    payload: CampaignCancellationCreate,
) -> CampaignCancellation:
    organization, _ = await get_required_advertiser_context(
        session, actor_user_id, require_write=True
    )
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == campaign_id).with_for_update()
    )
    if campaign is None or campaign.organization_id != organization.id:
        raise _error("CAMPAIGN_NOT_FOUND", "Campaign was not found", 404)

    fingerprint = _digest(
        {
            "campaign_id": str(campaign_id),
            "client_request_id": str(payload.client_request_id),
            "reason": payload.reason,
        }
    )
    existing = await session.scalar(
        select(CampaignCancellation).where(
            CampaignCancellation.campaign_id == campaign_id
        )
    )
    if existing is not None:
        if (
            existing.requested_by_user_id == actor_user_id
            and existing.client_request_id == payload.client_request_id
            and existing.request_fingerprint == fingerprint
        ):
            return existing
        raise _error(
            "CAMPAIGN_CANCELLATION_CONFLICT",
            "This campaign already has a different immutable cancellation",
        )
    if campaign.status not in {
        CampaignStatus.APPROVED.value,
        CampaignStatus.SCHEDULED.value,
        CampaignStatus.ACTIVE.value,
        CampaignStatus.PAUSED.value,
    }:
        raise _error(
            "CAMPAIGN_CANCELLATION_NOT_AVAILABLE",
            "Only an approved, scheduled, active or paused campaign can be cancelled",
        )

    now = await database_clock(session)
    terms: CommercialTerms | None = await _commercial_terms_for_campaign(
        session, campaign_id, lock=True
    )
    funding_authorized_at = None
    eligibility_ends_at = None
    production = None
    refundable_amount = Decimal("0.00")
    if terms is None:
        disposition = CampaignCancellationDisposition.NO_SETTLEMENT
    elif terms.payment_class == PaymentClass.APPROVED_CORPORATE_CREDIT.value:
        disposition = CampaignCancellationDisposition.CREDIT_SETTLEMENT_DUE
    else:
        funding_authorized_at, eligibility_ends_at, production = await _refund_window(
            session, terms
        )
        remaining_cash = await _cash_remaining_for_terms(session, terms.id)
        if (
            funding_authorized_at is not None
            and eligibility_ends_at is not None
            and _aware(now) < _aware(eligibility_ends_at)
            and remaining_cash > 0
        ):
            disposition = CampaignCancellationDisposition.CASH_REFUND_DUE
            refundable_amount = remaining_cash
        else:
            disposition = CampaignCancellationDisposition.CASH_REFUND_NOT_DUE

    reservations = list(
        await session.scalars(
            select(CampaignLiabilityReservation)
            .where(
                CampaignLiabilityReservation.campaign_id == campaign_id,
                CampaignLiabilityReservation.status.in_({"pending_funding", "reserved"}),
            )
            .order_by(CampaignLiabilityReservation.id)
            .with_for_update()
        )
    )
    assignment_liability = sum(
        (Decimal(item.reserved_amount or 0) for item in reservations), Decimal("0.00")
    )
    change_liability = Decimal(
        await session.scalar(
            select(
                func.coalesce(func.sum(CampaignChangeRequest.reserved_liability_amount), 0)
            ).where(
                CampaignChangeRequest.campaign_id == campaign_id,
                CampaignChangeRequest.status == CampaignChangeStatus.APPLIED.value,
            )
        )
        or 0
    )
    assignments = list(
        await session.scalars(
            select(CampaignAssignment)
            .where(
                CampaignAssignment.campaign_id == campaign_id,
                CampaignAssignment.status.in_(
                    {
                        CampaignAssignmentStatus.OFFERED.value,
                        CampaignAssignmentStatus.ACCEPTED.value,
                        CampaignAssignmentStatus.ACTIVE.value,
                        CampaignAssignmentStatus.DEACTIVATED.value,
                    }
                ),
            )
            .order_by(CampaignAssignment.id)
            .with_for_update()
        )
    )
    cancellation_id = uuid4()
    prior_status = campaign.status
    cancellation = CampaignCancellation(
        id=cancellation_id,
        campaign_id=campaign.id,
        organization_id=campaign.organization_id,
        requested_by_user_id=actor_user_id,
        client_request_id=payload.client_request_id,
        request_fingerprint=fingerprint,
        reason=payload.reason,
        prior_status=prior_status,
        cutoff_at=now,
        commercial_terms_id=terms.id if terms is not None else None,
        production_start_id=production.id if production is not None else None,
        funding_authorized_at=funding_authorized_at,
        refund_eligibility_ends_at=eligibility_ends_at,
        disposition=disposition.value,
        refundable_amount=refundable_amount,
        currency=campaign.currency,
        released_liability_amount=assignment_liability + change_liability,
        cancelled_assignment_count=len(assignments),
    )
    session.add(cancellation)
    await session.flush([cancellation])

    for reservation in reservations:
        reservation.status = "released"
        reservation.released_at = now
        reservation.release_cancellation_id = cancellation.id
    for assignment in assignments:
        previous_status = assignment.status
        assignment.status = CampaignAssignmentStatus.CANCELLED.value
        assignment.cancelled_at = now
        await create_activation_event(
            session,
            assignment=assignment,
            actor_user_id=actor_user_id,
            event_type=CampaignActivationEventType.CANCELLED,
            previous_status=previous_status,
            metadata={
                "reason": payload.reason,
                "campaign_cancellation_id": str(cancellation.id),
                "financial_cutoff_at": _aware(now).isoformat(),
            },
            occurred_at=now,
        )
    campaign.status = CampaignStatus.CANCELLED.value

    snapshot = {
        "campaign_id": str(campaign.id),
        "cancellation_id": str(cancellation.id),
        "cutoff_at": _aware(now).isoformat(),
        "prior_status": prior_status,
        "disposition": disposition.value,
        "refundable_amount": str(refundable_amount),
        "currency": campaign.currency,
        "funding_authorized_at": (
            _aware(funding_authorized_at).isoformat()
            if funding_authorized_at is not None
            else None
        ),
        "refund_eligibility_ends_at": (
            _aware(eligibility_ends_at).isoformat()
            if eligibility_ends_at is not None
            else None
        ),
        "production_start_id": str(production.id) if production is not None else None,
        "released_assignment_liability_amount": str(assignment_liability),
        "released_change_liability_amount": str(change_liability),
        "cancelled_assignment_ids": [str(item.id) for item in assignments],
        "reason": payload.reason,
    }
    revision = CampaignCancellationSettlementRevision(
        cancellation_id=cancellation.id,
        campaign_id=campaign.id,
        revision_number=1,
        effective_from=now,
        snapshot=snapshot,
        snapshot_sha256=_digest(snapshot),
    )
    session.add(revision)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="advertiser.campaign.cancelled",
        entity_type="campaign_cancellation",
        entity_id=str(cancellation.id),
        metadata={
            "campaign_id": str(campaign.id),
            "cutoff_at": _aware(now).isoformat(),
            "disposition": disposition.value,
            "refundable_amount": str(refundable_amount),
            "released_liability_amount": str(assignment_liability + change_liability),
            "settlement_revision_id": str(revision.id),
        },
    )
    return cancellation

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

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
from app.services.billing.queries import _commercial_terms_for_campaign
from app.services.billing.settlements import _refund_window
from app.services.campaign_assignments import create_activation_event
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _digest(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _error(code: str, message: str, status_code: int = 409) -> AppError:
    return AppError(code, message, status_code=status_code)


async def campaign_financial_cutoff(session: AsyncSession, campaign_id: UUID) -> datetime | None:
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


async def _cash_remaining_for_terms(session: AsyncSession, commercial_terms_id: UUID) -> Decimal:
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


async def _lock_cancellation_campaign(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    campaign_id: UUID,
    actor_session_version: int,
) -> Campaign:
    from app.services.admin_authorization import require_active_admin

    await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(
        session, actor_user_id, share_lock=True, expected_session_version=actor_session_version
    )
    campaign = await session.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if campaign is None:
        raise _error("CAMPAIGN_NOT_FOUND", "Campaign was not found", 404)

    return campaign


def _request_fingerprint(campaign_id, payload, *, complaint_id):
    return _digest(
        {
            "campaign_id": str(campaign_id),
            "client_request_id": str(payload.client_request_id),
            "reason": payload.reason,
            "complaint_id": str(complaint_id) if complaint_id else None,
        }
    )


async def request_campaign_cancellation(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    campaign_id: UUID,
    payload: CampaignCancellationCreate,
    actor_session_version: int,
    complaint_id: UUID | None = None,
) -> CampaignCancellation:
    """D7: only Terrax staff cancel a whole campaign, on the advertiser's request."""
    campaign = await _lock_cancellation_campaign(
        session,
        actor_user_id=actor_user_id,
        campaign_id=campaign_id,
        actor_session_version=actor_session_version,
    )
    fingerprint = _request_fingerprint(campaign_id, payload, complaint_id=complaint_id)
    existing = await session.scalar(
        select(CampaignCancellation).where(CampaignCancellation.campaign_id == campaign_id)
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
    if complaint_id is not None:
        await _validate_cancellation_complaint(session, campaign, complaint_id)
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
            _aware(funding_authorized_at).isoformat() if funding_authorized_at is not None else None
        ),
        "refund_eligibility_ends_at": (
            _aware(eligibility_ends_at).isoformat() if eligibility_ends_at is not None else None
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
        action="admin.campaign.cancelled",
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
    from app.models.notification import NotificationType
    from app.services.notifications import create_advertiser_business_notifications

    await create_advertiser_business_notifications(
        session,
        advertiser_organization_id=campaign.organization_id,
        type_key=NotificationType.CAMPAIGN_CANCELLED,
        event_key=f"campaign:cancelled:v1:{cancellation.id}",
        payload={
            "campaign_id": str(campaign.id),
            "campaign_cancellation_id": str(cancellation.id),
            "disposition": disposition.value,
        },
    )
    await _reply_to_cancellation(session, cancellation, complaint_id)
    return cancellation


async def _reply_to_cancellation(session, cancellation, complaint_id):
    if complaint_id is None:
        return
    from app.services.complaints import reply_as_staff

    await reply_as_staff(
        session,
        actor_user_id=cancellation.requested_by_user_id,
        complaint_id=complaint_id,
        message="The campaign has been cancelled.",
        resolve=False,
        client_request_id=uuid5(NAMESPACE_URL, f"cardvert:campaign-cancelled:{cancellation.id}"),
    )


async def _validate_cancellation_complaint(session, campaign, complaint_id):
    from app.models.complaint import Complaint, ComplaintParty, ComplaintReferenceType
    from app.schemas.complaints import ComplaintCategory

    complaint = await session.scalar(
        select(Complaint)
        .where(
            Complaint.id == complaint_id,
            Complaint.party == ComplaintParty.ADVERTISER.value,
            Complaint.category == ComplaintCategory.CAMPAIGN_CANCELLATION.value,
            Complaint.reference_type == ComplaintReferenceType.CAMPAIGN.value,
            Complaint.campaign_id == campaign.id,
            Complaint.advertiser_organization_id == campaign.organization_id,
        )
        .with_for_update()
    )
    if complaint is None:
        raise _error(
            "CAMPAIGN_CANCELLATION_REQUEST_NOT_FOUND",
            "The cancellation request was not found for this campaign",
            404,
        )

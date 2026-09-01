import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.billing import CampaignFinancialAuthorization
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.campaign_change import (
    CampaignChangeRequest,
    CampaignChangeRevision,
    CampaignChangeStatus,
)
from app.models.payout import AssignmentRuleBinding
from app.schemas.campaign_changes import CampaignChangeCreate
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.billing import (
    _authorization_usable_liability,
    effective_financial_authorization,
    reserved_campaign_liability_total,
)
from app.services.campaigns import get_required_advertiser_context
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock

MONEY = Decimal("0.01")
LAGOS_TZ = ZoneInfo("Africa/Lagos")


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _json_value(value):
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def campaign_change_snapshot(campaign: Campaign) -> dict[str, object]:
    return {
        "campaign_id": str(campaign.id),
        "campaign_name": campaign.name,
        "currency": campaign.currency,
        "budget_amount": _json_value(campaign.budget_amount),
        "daily_budget_amount": _json_value(campaign.daily_budget_amount),
        "start_at": _json_value(campaign.start_at),
        "end_at": _json_value(campaign.end_at),
    }


def _digest(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _error(code: str, message: str, status_code: int = 409) -> AppError:
    return AppError(code, message, status_code=status_code)


def _classify(before: dict[str, object], changes: dict[str, object]) -> list[str]:
    classifications: set[str] = set()
    for field, proposed in changes.items():
        current = before[field]
        if field in {"start_at", "end_at"}:
            classifications.add("date_change")
            is_expansion = (
                field == "end_at" and current is not None and proposed > current
            ) or (
                field == "start_at" and current is not None and proposed < current
            )
            if is_expansion:
                classifications.add("expansion")
            else:
                classifications.add("reduction")
        elif current is None or Decimal(str(proposed)) > Decimal(str(current)):
            classifications.add("expansion")
        elif Decimal(str(proposed)) < Decimal(str(current)):
            classifications.add("reduction")
    return sorted(classifications)


async def _additional_window_liability(
    session: AsyncSession,
    *,
    campaign: Campaign,
    proposed_start_at: datetime | None,
    proposed_end_at: datetime | None,
) -> Decimal:
    if campaign.start_at is None or campaign.end_at is None:
        return Decimal("0.00")
    current_start = _aware(campaign.start_at)
    current_end = _aware(campaign.end_at)
    proposed_start = _aware(proposed_start_at) if proposed_start_at else current_start
    proposed_end = _aware(proposed_end_at) if proposed_end_at else current_end
    extra_days = max(
        0,
        (
            current_start.astimezone(LAGOS_TZ).date()
            - proposed_start.astimezone(LAGOS_TZ).date()
        ).days,
    ) + max(
        0,
        (
            proposed_end.astimezone(LAGOS_TZ).date()
            - current_end.astimezone(LAGOS_TZ).date()
        ).days,
    )
    if extra_days <= 0:
        return Decimal("0.00")
    bindings = list(
        await session.scalars(
            select(AssignmentRuleBinding)
            .join(
                CampaignAssignment,
                CampaignAssignment.id == AssignmentRuleBinding.assignment_id,
            )
            .where(
                CampaignAssignment.campaign_id == campaign.id,
                CampaignAssignment.status.in_(
                    {
                        CampaignAssignmentStatus.ACCEPTED.value,
                        CampaignAssignmentStatus.ACTIVE.value,
                        CampaignAssignmentStatus.DEACTIVATED.value,
                    }
                ),
            )
            .order_by(AssignmentRuleBinding.assignment_id)
            .with_for_update()
        )
    )
    requested = Decimal("0.00")
    for binding in bindings:
        rate = max(
            Decimal(binding.hourly_rate_naira),
            Decimal(binding.premium_hourly_rate_naira or binding.hourly_rate_naira),
        )
        cap = Decimal(binding.daily_payable_hours_cap or 0)
        requested += rate * cap * extra_days
    return requested.quantize(MONEY, rounding=ROUND_HALF_UP)


async def _locked_campaign(session: AsyncSession, campaign_id: UUID) -> Campaign:
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == campaign_id).with_for_update()
    )
    if campaign is None:
        raise _error("CAMPAIGN_NOT_FOUND", "Campaign was not found", 404)
    if campaign.status not in {
        CampaignStatus.SCHEDULED.value,
        CampaignStatus.ACTIVE.value,
        CampaignStatus.PAUSED.value,
    }:
        raise _error(
            "CAMPAIGN_CHANGE_NOT_AVAILABLE",
            "Mid-flight changes require a scheduled, active or paused campaign",
        )
    return campaign


async def _apply_if_funded(
    session: AsyncSession,
    *,
    request: CampaignChangeRequest,
    campaign: Campaign,
    actor_user_id: UUID,
    review_reason: str | None,
) -> CampaignChangeRequest:
    now = await database_clock(session)
    new_review = review_reason is not None and request.review_reason is None
    if review_reason is not None and request.review_reason is not None and (
        request.review_reason != review_reason
        or request.reviewed_by_user_id != actor_user_id
    ):
        raise _error(
            "CAMPAIGN_CHANGE_DECISION_CONFLICT",
            "This campaign change already has a different admin decision",
        )
    requested = Decimal(request.requested_liability_amount)
    authorization: CampaignFinancialAuthorization | None = None
    if requested > 0:
        authorization = await effective_financial_authorization(
            session, campaign_id=campaign.id, effective_at=now
        )
        usable = (
            await _authorization_usable_liability(session, authorization, effective_at=now)
            if authorization is not None
            else Decimal("0.00")
        )
        reserved = await reserved_campaign_liability_total(
            session, campaign_id=campaign.id
        )
        if authorization is None or usable - reserved < requested:
            request.status = CampaignChangeStatus.PENDING_FUNDING.value
            if new_review:
                request.reviewed_by_user_id = actor_user_id
                request.reviewed_at = now
                request.review_reason = review_reason
            await session.flush()
            if new_review:
                await create_audit_event(
                    session,
                    actor_user_id=actor_user_id,
                    action="admin.campaign_change.pending_funding",
                    entity_type="campaign_change_request",
                    entity_id=str(request.id),
                    metadata={
                        "campaign_id": str(campaign.id),
                        "requested_liability_amount": str(requested),
                        "reason": review_reason,
                    },
                )
            return request

    before_digest = request.impact_preview.get("before_sha256")
    if before_digest != _digest(campaign_change_snapshot(campaign)):
        raise _error(
            "CAMPAIGN_CHANGE_STALE",
            "Campaign facts changed after this request was previewed",
        )
    for field, value in request.proposed_changes.items():
        if field in {"start_at", "end_at"}:
            value = datetime.fromisoformat(str(value))
        elif value is not None:
            value = Decimal(str(value))
        setattr(campaign, field, value)
    if (
        campaign.start_at is None
        or campaign.end_at is None
        or _aware(campaign.start_at) >= _aware(campaign.end_at)
    ):
        raise _error("INVALID_CAMPAIGN_WINDOW", "Campaign start must remain before its end", 400)
    if (
        campaign.budget_amount is not None
        and campaign.daily_budget_amount is not None
        and Decimal(campaign.daily_budget_amount) > Decimal(campaign.budget_amount)
    ):
        raise _error(
            "INVALID_CAMPAIGN_BUDGET",
            "Daily budget cannot exceed the total budget",
            400,
        )
    latest_number = await session.scalar(
        select(CampaignChangeRevision.revision_number)
        .where(CampaignChangeRevision.campaign_id == campaign.id)
        .order_by(CampaignChangeRevision.revision_number.desc())
        .limit(1)
    )
    snapshot = campaign_change_snapshot(campaign)
    revision = CampaignChangeRevision(
        campaign_id=campaign.id,
        request_id=request.id,
        revision_number=(latest_number or 0) + 1,
        effective_from=now,
        snapshot=snapshot,
        snapshot_sha256=_digest(snapshot),
        applied_by_user_id=actor_user_id,
    )
    session.add(revision)
    request.status = CampaignChangeStatus.APPLIED.value
    request.authorization_id = authorization.id if authorization is not None else None
    request.reserved_liability_amount = requested
    request.applied_at = now
    if new_review:
        request.reviewed_by_user_id = actor_user_id
        request.reviewed_at = now
        request.review_reason = review_reason
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="campaign.change.applied",
        entity_type="campaign_change_request",
        entity_id=str(request.id),
        metadata={
            "campaign_id": str(campaign.id),
            "classifications": request.classifications,
            "revision_id": str(revision.id),
            "reserved_liability_amount": str(requested),
        },
    )
    return request


async def request_campaign_change(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    campaign_id: UUID,
    payload: CampaignChangeCreate,
) -> CampaignChangeRequest:
    organization, _ = await get_required_advertiser_context(
        session, actor_user_id, require_write=True
    )
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await _locked_campaign(session, campaign_id)
    if campaign.organization_id != organization.id:
        raise _error("CAMPAIGN_NOT_FOUND", "Campaign was not found", 404)
    raw = payload.model_dump(exclude_unset=True)
    reason = raw.pop("reason")
    client_request_id = raw.pop("client_request_id")
    requested_changes = {field: _json_value(value) for field, value in raw.items()}
    fingerprint = _digest(
        {
            "requested_changes": requested_changes,
            "reason": reason,
            "client_request_id": str(client_request_id),
        }
    )
    existing = await session.scalar(
        select(CampaignChangeRequest).where(
            CampaignChangeRequest.campaign_id == campaign.id,
            CampaignChangeRequest.requested_by_user_id == actor_user_id,
            CampaignChangeRequest.client_request_id == client_request_id,
        )
    )
    if existing is not None:
        if existing.request_fingerprint == fingerprint:
            return existing
        raise _error(
            "CAMPAIGN_CHANGE_RETRY_CONFLICT",
            "The client request ID was already used for different changes",
        )
    before = campaign_change_snapshot(campaign)
    proposed = {
        field: value for field, value in requested_changes.items() if value != before[field]
    }
    if not proposed:
        raise _error("CAMPAIGN_CHANGE_NOOP", "The request does not change campaign facts", 400)
    now = await database_clock(session)
    if "start_at" in raw and _aware(raw["start_at"]) < now:
        raise _error(
            "CAMPAIGN_CHANGE_RETROACTIVE_DATE",
            "A campaign change cannot move its start into the past",
            400,
        )
    if "end_at" in raw and _aware(raw["end_at"]) <= now:
        raise _error(
            "CAMPAIGN_CHANGE_RETROACTIVE_DATE",
            "A campaign change cannot move its end into the past",
            400,
        )
    classifications = _classify(before, proposed)
    requested_liability = await _additional_window_liability(
        session,
        campaign=campaign,
        proposed_start_at=raw.get("start_at"),
        proposed_end_at=raw.get("end_at"),
    )
    needs_admin = bool({"reduction", "date_change"}.intersection(classifications))
    request = CampaignChangeRequest(
        campaign_id=campaign.id,
        organization_id=campaign.organization_id,
        requested_by_user_id=actor_user_id,
        client_request_id=client_request_id,
        request_fingerprint=fingerprint,
        proposed_changes=proposed,
        classifications=classifications,
        impact_preview={
            "before": before,
            "after": before | proposed,
            "before_sha256": _digest(before),
            "request_reason": reason,
            "requested_liability_amount": str(requested_liability),
        },
        status=CampaignChangeStatus.PENDING_ADMIN.value,
        requested_liability_amount=requested_liability,
    )
    session.add(request)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="advertiser.campaign_change.requested",
        entity_type="campaign_change_request",
        entity_id=str(request.id),
        metadata={"campaign_id": str(campaign.id), "classifications": classifications},
    )
    if not needs_admin:
        return await _apply_if_funded(
            session,
            request=request,
            campaign=campaign,
            actor_user_id=actor_user_id,
            review_reason=None,
        )
    return request


async def decide_campaign_change(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    request_id: UUID,
    approve: bool,
    reason: str,
) -> CampaignChangeRequest:
    await require_active_admin(session, actor_user_id)
    campaign_id = await session.scalar(
        select(CampaignChangeRequest.campaign_id).where(CampaignChangeRequest.id == request_id)
    )
    if campaign_id is None:
        raise _error("CAMPAIGN_CHANGE_NOT_FOUND", "Campaign change was not found", 404)
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await _locked_campaign(session, campaign_id)
    request = await session.scalar(
        select(CampaignChangeRequest)
        .where(CampaignChangeRequest.id == request_id)
        .with_for_update()
    )
    assert request is not None
    if request.status == CampaignChangeStatus.APPLIED.value:
        return request
    if request.status == CampaignChangeStatus.REJECTED.value:
        if not approve and request.review_reason == reason:
            return request
        raise _error("CAMPAIGN_CHANGE_DECISION_CONFLICT", "This change is already rejected")
    if not approve:
        if request.review_reason is not None:
            raise _error(
                "CAMPAIGN_CHANGE_DECISION_CONFLICT",
                "An approved change waiting for funding cannot be rejected as a retry",
            )
        now = await database_clock(session)
        request.status = CampaignChangeStatus.REJECTED.value
        request.reviewed_by_user_id = actor_user_id
        request.reviewed_at = now
        request.review_reason = reason
        await session.flush()
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="admin.campaign_change.rejected",
            entity_type="campaign_change_request",
            entity_id=str(request.id),
            metadata={"campaign_id": str(campaign.id), "reason": reason},
        )
        return request
    return await _apply_if_funded(
        session,
        request=request,
        campaign=campaign,
        actor_user_id=actor_user_id,
        review_reason=reason,
    )


async def list_advertiser_campaign_changes(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    campaign_id: UUID,
) -> list[CampaignChangeRequest]:
    organization, _ = await get_required_advertiser_context(session, actor_user_id)
    return list(
        await session.scalars(
            select(CampaignChangeRequest)
            .where(
                CampaignChangeRequest.campaign_id == campaign_id,
                CampaignChangeRequest.organization_id == organization.id,
            )
            .order_by(CampaignChangeRequest.created_at.desc(), CampaignChangeRequest.id.desc())
        )
    )


async def list_pending_campaign_changes(session: AsyncSession) -> list[CampaignChangeRequest]:
    return list(
        await session.scalars(
            select(CampaignChangeRequest)
            .where(
                CampaignChangeRequest.status.in_(
                    {
                        CampaignChangeStatus.PENDING_ADMIN.value,
                        CampaignChangeStatus.PENDING_FUNDING.value,
                    }
                )
            )
            .order_by(CampaignChangeRequest.created_at, CampaignChangeRequest.id)
        )
    )


async def resolve_campaign_change_snapshot(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    effective_at: datetime,
) -> dict[str, object]:
    """Resolve the immutable campaign revision in force for an interval instant."""
    effective_at = _aware(effective_at)
    revision = await session.scalar(
        select(CampaignChangeRevision)
        .where(
            CampaignChangeRevision.campaign_id == campaign_id,
            CampaignChangeRevision.effective_from <= effective_at,
        )
        .order_by(
            CampaignChangeRevision.effective_from.desc(),
            CampaignChangeRevision.revision_number.desc(),
        )
        .limit(1)
    )
    if revision is not None:
        return dict(revision.snapshot)
    earliest_request = await session.scalar(
        select(CampaignChangeRequest)
        .join(
            CampaignChangeRevision,
            CampaignChangeRevision.request_id == CampaignChangeRequest.id,
        )
        .where(CampaignChangeRevision.campaign_id == campaign_id)
        .order_by(CampaignChangeRevision.revision_number)
        .limit(1)
    )
    if earliest_request is not None:
        return dict(earliest_request.impact_preview["before"])
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise _error("CAMPAIGN_NOT_FOUND", "Campaign was not found", 404)
    return campaign_change_snapshot(campaign)

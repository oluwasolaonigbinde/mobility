"""Staff resumption from recorded current pause authority; unknown causes fail closed."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.billing import BudgetCampaignTransition
from app.models.campaign import Campaign, CampaignCreative
from app.models.campaign_assignment import CampaignAssignment
from app.models.driver import DriverProfile
from app.models.payout import CampaignPayoutRule, CampaignPayoutRuleRevision
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.billing import assert_campaign_production_authorized, assert_new_work_authorized
from app.services.campaign_assignments import (
    _creative_snapshot,
    as_aware_utc,
    ensure_active_driver_profile,
    ensure_active_vehicle,
    ensure_campaign_review_approved,
    ensure_current_activation_snapshot,
    ensure_vehicle_belongs_to_driver,
)
from app.services.installation_evidence import ensure_current_approved_installation_evidence
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock
from app.services.vehicle_onboarding import (
    acquire_work_eligibility_lock,
    ensure_current_driver_vehicle_eligibility,
)


async def pause_info(session: AsyncSession, campaign: Campaign) -> dict[str, Any]:
    audit = await session.scalar(
        select(AuditEvent)
        .join(User, AuditEvent.actor_user_id == User.id)
        .where(
            AuditEvent.entity_type == "campaign",
            AuditEvent.entity_id == str(campaign.id),
            AuditEvent.action.in_(("admin.campaign.paused", "admin.campaign.resumed")),
            User.role == "admin",
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    budget = await session.scalar(
        select(BudgetCampaignTransition)
        .where(
            BudgetCampaignTransition.campaign_id == campaign.id,
        )
        .order_by(BudgetCampaignTransition.created_at.desc(), BudgetCampaignTransition.id.desc())
        .limit(1)
    )
    unknown = {
        "kind": "unknown",
        "reason": "The reason for this pause was not recorded.",
        "pause_id": None,
        "resume_allowed": False,
        "resume_explanation": "Staff cannot resume until the pause reason is recorded.",
    }
    if campaign.status != "paused":
        return unknown
    if budget and (not audit or as_aware_utc(budget.created_at) >= as_aware_utc(audit.created_at)):
        if budget.action == "pause":
            return {
                "kind": "budget",
                "reason": budget.reason,
                "pause_id": budget.id,
                "resume_allowed": False,
                "resume_explanation": "Finance can resume after the budget check permits it.",
            }
        return unknown
    if not audit or audit.action != "admin.campaign.paused":
        return unknown
    evidence = audit.event_metadata
    version = evidence.get("pause_version")
    try:
        current_version = isinstance(version, str) and as_aware_utc(
            datetime.fromisoformat(version)
        ) == as_aware_utc(campaign.updated_at)
    except ValueError:
        current_version = False
    if not current_version or evidence.get("status_after") != "paused":
        return unknown
    kind = evidence.get("pause_reason_kind")
    reason = evidence.get("reason")
    if kind == "budget":
        return {
            **unknown,
            "kind": "budget",
            "reason": reason
            if isinstance(reason, str) and reason.strip()
            else "Paused for budget.",
            "resume_explanation": "Use the Finance budget check to resume this campaign.",
        }
    if kind != "operational" or not isinstance(reason, str) or not reason.strip():
        return unknown
    # An inconsistent recorded category must never provide a budget bypass.
    if any(word in reason.casefold() for word in ("budget", "funding", "insufficient funds")):
        return {
            **unknown,
            "kind": "budget",
            "reason": reason,
            "resume_explanation": "Budget-related pause. Use the Finance budget check.",
        }
    return {
        "kind": "operational",
        "reason": reason,
        "pause_id": audit.id,
        "resume_allowed": True,
        "resume_explanation": "Staff can resume after Cardvert checks the start requirements.",
    }


async def resume_campaign(
    session: AsyncSession, *, campaign_id: UUID, actor_user_id: UUID, pause_id: UUID, reason: str
) -> Campaign:
    await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    reason = reason.strip()
    if not reason or len(reason) > 1000:
        raise AppError(
            "RESUME_REASON_REQUIRED", "Give a reason for resuming this campaign.", status_code=400
        )
    campaign = await session.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if campaign is None:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign not found.", status_code=404)
    if campaign.status != "paused":
        return await _exact_resume_retry(session, campaign, actor_user_id, pause_id, reason)
    await _require_operational_pause(session, campaign, pause_id)
    now = await database_clock(session)
    await _check_start_requirements(session, campaign, now)
    await _check_active_jobs(session, campaign.id, now)
    assert campaign.start_at is not None
    campaign.status = "scheduled" if as_aware_utc(campaign.start_at) > now else "active"
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.campaign.resumed",
        entity_type="campaign",
        entity_id=str(campaign.id),
        metadata={
            "pause_id": str(pause_id),
            "reason": reason,
            "pause_reason_kind": "operational",
            "status_before": "paused",
            "status_after": campaign.status,
        },
    )
    await session.flush()
    return campaign


async def _exact_resume_retry(
    session: AsyncSession, campaign: Campaign, actor_user_id: UUID, pause_id: UUID, reason: str
) -> Campaign:
    # An exact repeated request is safe only while that same resume is current.
    previous = await session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == "campaign",
            AuditEvent.entity_id == str(campaign.id),
            AuditEvent.action.in_(("admin.campaign.paused", "admin.campaign.resumed")),
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    if (
        previous
        and previous.action == "admin.campaign.resumed"
        and previous.actor_user_id == actor_user_id
        and previous.event_metadata.get("pause_id") == str(pause_id)
        and previous.event_metadata.get("reason") == reason
        and previous.event_metadata.get("status_after") == campaign.status
    ):
        return campaign
    raise AppError(
        "CAMPAIGN_NOT_PAUSED",
        "This campaign is no longer paused. Refresh the page.",
        status_code=409,
    )


async def _require_operational_pause(
    session: AsyncSession, campaign: Campaign, pause_id: UUID
) -> None:
    pause = await pause_info(session, campaign)
    if pause["kind"] == "budget":
        raise AppError(
            "BUDGET_PAUSE_REQUIRES_FINANCE",
            "This pause is budget-related. Finance must use the budget check to resume it.",
            status_code=409,
        )
    if pause["kind"] != "operational":
        raise AppError(
            "PAUSE_REASON_UNKNOWN",
            "The pause reason is not recorded, so staff cannot resume this campaign.",
            status_code=409,
        )
    if pause["pause_id"] != pause_id:
        raise AppError(
            "CAMPAIGN_PAUSE_CHANGED",
            "The pause has changed. Refresh the page before resuming.",
            status_code=409,
        )


async def _check_start_requirements(
    session: AsyncSession, campaign: Campaign, now: datetime
) -> None:
    if campaign.start_at is None or campaign.end_at is None or as_aware_utc(campaign.end_at) <= now:
        raise AppError(
            "CAMPAIGN_EXPIRED",
            "Check the campaign dates; it cannot resume after its end date.",
            status_code=409,
        )
    await ensure_campaign_review_approved(session, campaign.id)
    await assert_campaign_production_authorized(session, campaign_id=campaign.id)
    artwork = await session.scalar(
        select(CampaignCreative.id)
        .where(CampaignCreative.campaign_id == campaign.id, CampaignCreative.status == "approved")
        .limit(1)
    )
    if artwork is None:
        raise AppError(
            "APPROVED_CAMPAIGN_CREATIVE_REQUIRED",
            "Approve the campaign artwork before resuming.",
            status_code=409,
        )
    rule = await session.scalar(
        select(CampaignPayoutRule)
        .where(CampaignPayoutRule.campaign_id == campaign.id, CampaignPayoutRule.status == "active")
        .with_for_update()
    )
    if rule is None:
        raise AppError(
            "CURRENT_PAY_TERMS_REQUIRED",
            "Set current driver pay terms before resuming.",
            status_code=409,
        )
    if rule.formula_version in {"payout_v2", "payout_v3", "payout_v4"}:
        current = await session.scalar(
            select(CampaignPayoutRuleRevision.id)
            .where(
                CampaignPayoutRuleRevision.campaign_id == campaign.id,
                CampaignPayoutRuleRevision.payout_rule_id == rule.id,
                CampaignPayoutRuleRevision.effective_from <= now,
            )
            .order_by(
                CampaignPayoutRuleRevision.effective_from.desc(),
                CampaignPayoutRuleRevision.revision_number.desc(),
            )
            .limit(1)
        )
        if current is None:
            raise AppError(
                "CURRENT_PAY_TERMS_REQUIRED",
                "The driver pay terms are not effective yet.",
                status_code=409,
            )


async def _check_active_jobs(session: AsyncSession, campaign_id: UUID, now: datetime) -> None:
    jobs = await session.scalars(
        select(CampaignAssignment)
        .where(CampaignAssignment.campaign_id == campaign_id, CampaignAssignment.status == "active")
        .order_by(CampaignAssignment.id)
        .with_for_update()
    )
    for job in jobs:
        await _check_active_job(session, job, now)


async def _check_active_job(session: AsyncSession, job: CampaignAssignment, now: datetime) -> None:
    await acquire_work_eligibility_lock(
        session, driver_profile_id=job.driver_profile_id, vehicle_id=job.vehicle_id
    )
    driver = await session.scalar(
        select(DriverProfile).where(DriverProfile.id == job.driver_profile_id).with_for_update()
    )
    car = await session.scalar(
        select(Vehicle).where(Vehicle.id == job.vehicle_id).with_for_update()
    )
    if driver is None or car is None:
        raise AppError(
            "RESUME_JOB_INELIGIBLE", "Check the campaign's drivers and cars.", status_code=409
        )
    ensure_active_driver_profile(driver)
    ensure_active_vehicle(car)
    ensure_vehicle_belongs_to_driver(car, driver)
    await ensure_current_driver_vehicle_eligibility(
        session, driver_profile=driver, vehicle=car, now=now, lock=True
    )
    await ensure_current_activation_snapshot(session, assignment=job, lock=True)
    await ensure_current_approved_installation_evidence(
        session, assignment=job, settings=get_settings(), now=now, lock=True
    )
    await assert_new_work_authorized(session, campaign_id=job.campaign_id, assignment_id=job.id)
    terms = job.offer_terms or {}
    artwork = terms.get("creative")
    try:
        creative_id = UUID(str(artwork["id"])) if isinstance(artwork, dict) else None
    except (KeyError, ValueError):
        creative_id = None
    creative = await session.scalar(
        select(CampaignCreative)
        .where(CampaignCreative.id == creative_id, CampaignCreative.campaign_id == job.campaign_id)
        .with_for_update()
    )
    if creative is None or creative.status != "approved" or _creative_snapshot(creative) != artwork:
        raise AppError(
            "RESUME_ARTWORK_CHANGED",
            "Review the campaign's approved artwork before resuming.",
            status_code=409,
        )

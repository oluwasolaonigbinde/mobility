"""Driver-scoped preview of the managed artwork frozen in a current job."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import PresignedGet, StorageProvider
from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign import Campaign, CampaignCreative, CreativeStatus
from app.models.campaign_assignment import CampaignAssignment
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.stored_file import FilePurpose, StoredFile
from app.models.user import User
from app.services.campaign_assignments import (
    _creative_content_identity,
    _offer_terms_complete,
    as_aware_utc,
)
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock
from app.services.stored_files import _issue_download


def _not_found():
    return AppError("ASSIGNMENT_ARTWORK_NOT_FOUND", "Job artwork is unavailable", status_code=404)


def _unavailable():
    return AppError(
        "ASSIGNMENT_ARTWORK_UNAVAILABLE",
        "Job artwork is unavailable. Contact Terrax for help.",
        status_code=409,
    )


def _deadline(assignment, campaign, *, now):
    if assignment.status not in {"offered", "accepted", "active"} or campaign.status in {
        "cancelled",
        "rejected",
    }:
        raise _not_found()
    if not _offer_terms_complete(assignment.offer_terms, assignment.offer_terms_sha256):
        raise _unavailable()
    terms = assignment.offer_terms
    if terms["branding"]["campaign_id"] != str(campaign.id) or terms["branding"][
        "organization_id"
    ] != str(campaign.organization_id):
        raise _unavailable()
    try:
        end = as_aware_utc(datetime.fromisoformat(terms["campaign_window_end_at"]))
    except (TypeError, ValueError):
        raise _unavailable() from None
    if campaign.end_at is not None:
        end = min(end, as_aware_utc(campaign.end_at))
    if assignment.status == "offered":
        if assignment.expires_at is None:
            raise _not_found()
        end = min(end, as_aware_utc(assignment.expires_at))
    if now >= end:
        raise _not_found()
    return end


async def _artwork_file(session, *, assignment, campaign):
    frozen = assignment.offer_terms["creative"]
    try:
        creative_id = UUID(frozen["id"])
        file_id = UUID(frozen["content_identity"]["stored_file_id"])
    except (KeyError, TypeError, ValueError):
        raise _unavailable() from None
    creative = await session.scalar(
        select(CampaignCreative)
        .where(CampaignCreative.id == creative_id, CampaignCreative.campaign_id == campaign.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        creative is None
        or creative.status != CreativeStatus.APPROVED
        or creative.stored_file_id != file_id
    ):
        raise _unavailable()
    try:
        current = _creative_content_identity(creative)
    except AppError:
        raise _unavailable() from None
    if current != frozen["content_identity"]:
        raise _unavailable()
    stored_file = await session.scalar(
        select(StoredFile)
        .where(
            StoredFile.id == file_id,
            StoredFile.organization_id == campaign.organization_id,
            StoredFile.purpose == FilePurpose.CREATIVE,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        stored_file is None
        or stored_file.checksum_sha256 != current["checksum"]
        or stored_file.content_type != current["mime_type"]
        or stored_file.actual_content_type != current["mime_type"]
    ):
        raise _unavailable()
    return stored_file


async def issue_driver_job_artwork(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    actor_session_version: int,
    assignment_id: UUID,
    storage: StorageProvider,
    settings: Settings,
) -> PresignedGet:
    campaign_id = await session.scalar(
        select(CampaignAssignment.campaign_id)
        .join(DriverProfile, DriverProfile.id == CampaignAssignment.driver_profile_id)
        .where(CampaignAssignment.id == assignment_id, DriverProfile.user_id == actor_user_id)
    )
    if campaign_id is None:
        raise _not_found()
    await acquire_campaign_terms_lock(session, campaign_id)
    user = await session.scalar(
        select(User)
        .where(User.id == actor_user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        user is None
        or user.role != "driver"
        or user.status != "active"
        or user.session_version != actor_session_version
    ):
        raise _not_found()
    campaign = await session.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assignment = await session.scalar(
        select(CampaignAssignment)
        .where(
            CampaignAssignment.id == assignment_id, CampaignAssignment.campaign_id == campaign_id
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if campaign is None or assignment is None:
        raise _not_found()
    profile = await session.scalar(
        select(DriverProfile)
        .where(
            DriverProfile.id == assignment.driver_profile_id, DriverProfile.user_id == actor_user_id
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if profile is None or profile.onboarding_status in {
        DriverOnboardingStatus.SUSPENDED,
        DriverOnboardingStatus.REJECTED,
    }:
        raise _not_found()
    end = _deadline(assignment, campaign, now=await database_clock(session))
    stored_file = await _artwork_file(session, assignment=assignment, campaign=campaign)
    return await _issue_download(
        session,
        stored_file=stored_file,
        actor_user_id=actor_user_id,
        access_purpose="driver_job_artwork",
        reason="Preview the artwork frozen in the assigned job",
        storage=storage,
        settings=settings,
        access_expires_at=end,
    )

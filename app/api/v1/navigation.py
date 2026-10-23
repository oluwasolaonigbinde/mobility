from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.v1.campaign_assignments import driver_get_active_campaign_assignment
from app.api.v1.dependencies import (
    AdminUserDependency,
    DriverUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.models.campaign_assignment import CampaignAssignment
from app.models.driver import DriverProfile
from app.schemas.navigation import AdminBadgeSummary, DriverCurrentJob
from app.schemas.reports import ASSIGNMENT_STATUSES
from app.services.campaign_lifecycle import assignment_status_expression
from app.services.navigation import admin_badge_summary

router = APIRouter(tags=["Navigation summaries"])


@router.get("/admin/badge-summary", response_model=AdminBadgeSummary)
async def staff_badges(_user: AdminUserDependency, session: SessionDependency) -> AdminBadgeSummary:
    return AdminBadgeSummary(**await admin_badge_summary(session))


@router.get("/driver/current-job", response_model=DriverCurrentJob)
async def current_job(
    user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> DriverCurrentJob:
    # Reuse the exact active-job/photo authority and offer-expiry treatment.
    active = await driver_get_active_campaign_assignment(user, session, settings)
    status_column = assignment_status_expression()
    rows = await session.execute(
        select(status_column, func.count())
        .join(DriverProfile, DriverProfile.id == CampaignAssignment.driver_profile_id)
        .where(DriverProfile.user_id == user.id)
        .group_by(status_column)
    )
    counts = dict.fromkeys(ASSIGNMENT_STATUSES, 0)
    counts.update({status: count for status, count in rows})
    return DriverCurrentJob.model_validate({**active.model_dump(), "counts": counts})

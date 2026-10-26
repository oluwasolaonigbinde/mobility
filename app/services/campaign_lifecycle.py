"""Finished is a read projection of the campaign end, never stored state (D118)."""

from datetime import UTC, datetime

from sqlalchemy import case, func, select

from app.core.errors import AppError
from app.models.campaign import Campaign
from app.models.campaign_assignment import CampaignAssignment


def campaign_display_status(status, end_at, *, now=None):
    now = now or datetime.now(UTC)
    end = end_at.replace(tzinfo=UTC) if end_at and end_at.tzinfo is None else end_at
    return (
        "finished" if status in {"approved", "active", "paused"} and end and end <= now else status
    )


def campaign_status_expression():
    return case(
        (
            Campaign.status.in_(("approved", "active", "paused")) & (Campaign.end_at <= func.now()),
            "finished",
        ),
        else_=Campaign.status,
    )


def ensure_campaign_not_finished(campaign, *, now, action):
    if campaign_display_status(campaign.status, campaign.end_at, now=now) == "finished":
        raise AppError(
            "CAMPAIGN_FINISHED",
            f"This campaign has finished and cannot be {action}",
            status_code=409,
        )


def assignment_status_expression():
    ended = (
        select(Campaign.id)
        .where(Campaign.id == CampaignAssignment.campaign_id, Campaign.end_at <= func.now())
        .correlate(CampaignAssignment)
        .exists()
    )
    return case(
        (CampaignAssignment.status.in_(("offered", "accepted", "active")) & ended, "finished"),
        else_=CampaignAssignment.status,
    )


def assignment_window_open():
    return (
        select(Campaign.id)
        .where(
            Campaign.id == CampaignAssignment.campaign_id,
            (Campaign.end_at.is_(None)) | (Campaign.end_at > func.now()),
            Campaign.status != "cancelled",
        )
        .correlate(CampaignAssignment)
        .exists()
    )

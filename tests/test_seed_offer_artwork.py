import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from test_campaign_assignments import create_assignment_ready_graph

from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.user import User
from app.seeds import rich
from app.services import assignment_artwork


@pytest.mark.parametrize(
    "state", [CampaignAssignmentStatus.OFFERED, CampaignAssignmentStatus.ACTIVE]
)
def test_seeded_job_can_preview_artwork_with_a_bounded_offer_deadline(
    db_sessionmaker, settings, monkeypatch, state
):
    now = datetime.now(UTC)
    end = now + timedelta(hours=12)
    admin, campaign, _, profile, vehicle = create_assignment_ready_graph(
        db_sessionmaker, start_at=now + timedelta(hours=1), end_at=end
    )
    monkeypatch.setattr(rich, "utc_now", lambda: now)

    # Isolate this seed's lifecycle dates from independently tested frozen-term
    # construction and signature validation; the real artwork deadline is used.
    async def prepare(*args, **kwargs):
        return {
            "branding": {
                "campaign_id": str(campaign.id),
                "organization_id": str(campaign.organization_id),
            },
            "campaign_window_end_at": end.isoformat(),
        }, "0" * 64

    monkeypatch.setattr("app.seeds.demo_authority.prepare_daily_offer", prepare)
    monkeypatch.setattr(assignment_artwork, "_offer_terms_complete", lambda *args: True)

    async def scenario():
        async with db_sessionmaker() as session:
            advertiser = await session.get(User, campaign.created_by_user_id)
            assignment = await rich._ensure_assignment(
                session,
                campaign=campaign,
                asset=SimpleNamespace(profile=profile, vehicle=vehicle, index=1),
                admin=admin,
                advertiser=advertiser,
                settings=settings,
                status_value=state,
            )
            assert assignment_artwork._deadline(assignment, campaign, now=now) == end
            if state == CampaignAssignmentStatus.OFFERED:
                assert now < assignment.expires_at <= now + timedelta(days=1)
            else:
                assert assignment.expires_at is None
            same = await rich._ensure_assignment(
                session,
                campaign=campaign,
                asset=SimpleNamespace(profile=profile, vehicle=vehicle, index=1),
                admin=admin,
                advertiser=advertiser,
                settings=settings,
                status_value=state,
            )
            assert same.id == assignment.id

    asyncio.run(scenario())

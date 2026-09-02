import asyncio
from decimal import Decimal
from uuid import UUID

import pytest
from conftest import auth_headers
from test_exposure_segments import PASSWORD, _create_link_and_run

from app.core.errors import AppError
from app.models.campaign_zone import CampaignZone
from app.models.exposure_segment import ExposureSegment
from app.models.measurement import MeasurementRun
from app.models.retargeting_source_link import RetargetingSourceLink
from app.models.user import User
from app.services.audience import (
    HIGH_EXPOSURE_ZONE_DISCLAIMER,
    ZoneInsightTotal,
    high_exposure_zone_insights,
    materialize_exposure_segment,
    rank_high_exposure_zones,
)


def test_zone_insight_v1_ranking_ties_and_terminology() -> None:
    first_id = UUID("00000000-0000-0000-0000-000000000001")
    second_id = UUID("00000000-0000-0000-0000-000000000002")
    third_id = UUID("00000000-0000-0000-0000-000000000003")

    ranked = rank_high_exposure_zones(
        [
            ZoneInsightTotal(third_id, Decimal("90"), 9),
            ZoneInsightTotal(second_id, Decimal("120"), 4),
            ZoneInsightTotal(first_id, Decimal("120"), 4),
        ]
    )

    assert [(item.rank, item.zone_id) for item in ranked] == [
        (1, first_id),
        (2, second_id),
        (3, third_id),
    ]
    assert "modelled potential contacts" in HIGH_EXPOSURE_ZONE_DISCLAIMER.lower()
    assert "exposure score" in HIGH_EXPOSURE_ZONE_DISCLAIMER.lower()
    assert "impressions" in HIGH_EXPOSURE_ZONE_DISCLAIMER.lower()
    assert "roi" not in HIGH_EXPOSURE_ZONE_DISCLAIMER.lower()
    assert "separate" in HIGH_EXPOSURE_ZONE_DISCLAIMER.lower()


def test_zone_insights_are_governed_authorized_and_frozen_into_segment_history(
    db_client, db_sessionmaker, settings
) -> None:
    advertiser, outsider, link_id, run_id = _create_link_and_run(db_client, db_sessionmaker)
    governed = settings

    async def issue_and_read() -> tuple[UUID, UUID, dict]:
        async with db_sessionmaker() as session:
            segment = await materialize_exposure_segment(
                session,
                settings=governed,
                source_link_id=link_id,
                measurement_run_id=run_id,
            )
            await session.commit()
            link = await session.get(RetargetingSourceLink, link_id)
            assert link is not None
            insight = await high_exposure_zone_insights(
                session,
                settings=governed,
                actor_user_id=advertiser.id,
                campaign_id=link.campaign_id,
            )
            return segment.id, link.campaign_id, insight.model_dump(mode="json")

    first_segment_id, campaign_id, first = asyncio.run(issue_and_read())
    assert first["state"] == "ready"
    assert first["items"][0]["rank"] == 1
    assert first["items"][0]["zone_name"] == "Segment target"
    assert first["items"][0]["modelled_potential_contacts"] == "500.0000"
    assert first["campaign_exposure_score"] == "84.00"
    assert first["provenance"]["measurement_run_id"] == str(run_id)
    assert first["provenance"]["source_segments"][0]["segment_version"] == 1

    response = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/zone-insights",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )
    assert response.status_code == 200, response.text
    assert response.json() == first

    async def admin_email() -> str:
        async with db_sessionmaker() as session:
            run = await session.get(MeasurementRun, run_id)
            assert run is not None
            admin = await session.get(User, run.created_by_user_id)
            assert admin is not None
            return admin.email

    admin_response = db_client.get(
        f"/api/v1/admin/campaigns/{campaign_id}/zone-insights",
        headers=auth_headers(db_client, asyncio.run(admin_email()), PASSWORD),
    )
    assert admin_response.status_code == 200
    assert admin_response.json() == first

    isolated = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/zone-insights",
        headers=auth_headers(db_client, outsider.email, PASSWORD),
    )
    assert isolated.status_code == 404

    report = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/report",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )
    assert report.status_code == 200, report.text
    assert report.json()["high_exposure_zone_insights"] == first
    assert report.json()["measurement_result"]["roi"] is None

    async def replay_and_suppress_fixed() -> tuple[dict, dict]:
        async with db_sessionmaker() as session:
            replay = await materialize_exposure_segment(
                session,
                settings=governed,
                source_link_id=link_id,
                measurement_run_id=run_id,
            )
            assert replay.id == first_segment_id
            await session.commit()
            frozen = await session.get(ExposureSegment, first_segment_id)
            assert frozen is not None
            suppressed = await high_exposure_zone_insights(
                session,
                settings=governed.model_copy(update={"privacy_min_vehicles_per_cell": 2}),
                actor_user_id=advertiser.id,
                campaign_id=campaign_id,
            )
            return frozen.snapshot, suppressed.model_dump(mode="json")

    frozen_snapshot, suppressed = asyncio.run(replay_and_suppress_fixed())
    assert frozen_snapshot["version"] == 1
    assert frozen_snapshot["zone_insight_authority"]["formula_version"] == ("high_exposure_zone_v1")
    assert suppressed["state"] == "suppressed"
    assert suppressed["items"] == []
    assert suppressed["campaign_exposure_score"] is None
    assert suppressed["provenance"] is None
    assert suppressed["uncertainty"] is None
    assert "zone_name" not in str(suppressed)

    async def make_parent_stale() -> dict:
        async with db_sessionmaker() as session:
            segment = await session.get(ExposureSegment, first_segment_id)
            assert segment is not None
            zone = await session.get(CampaignZone, segment.zone_id)
            assert zone is not None
            zone.name = "Changed after issuance"
            await session.commit()
        async with db_sessionmaker() as session:
            stale = await high_exposure_zone_insights(
                session,
                settings=governed,
                actor_user_id=advertiser.id,
                campaign_id=campaign_id,
            )
            return stale.model_dump(mode="json")

    stale = asyncio.run(make_parent_stale())
    assert stale["state"] == "stale"
    assert stale["items"] == []
    assert stale["provenance"] is None
    assert "Changed after issuance" not in str(stale)


def test_zone_insight_live_disclosure_gate_runs_before_authority_reads(
    db_sessionmaker, settings
) -> None:
    blocked = settings.model_copy(
        update={
            "privacy_disclosure_synthetic_test_mode": False,
            "privacy_disclosure_live_authorized": False,
        }
    )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as error:
                await high_exposure_zone_insights(
                    session,
                    settings=blocked,
                    actor_user_id=UUID("00000000-0000-0000-0000-000000000099"),
                    campaign_id=UUID("00000000-0000-0000-0000-000000000098"),
                )
            assert error.value.code == "PRIVACY_LIVE_USE_BLOCKED"

    asyncio.run(scenario())

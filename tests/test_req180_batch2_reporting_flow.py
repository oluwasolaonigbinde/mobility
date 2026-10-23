"""S9/D118: current report publication retains D105 shared three-car area outputs."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from conftest import auth_headers, create_test_installation_evidence
from report_fixtures import create_report_fixture
from sqlalchemy import select
from test_advertiser_reports import DAY_1, PASSWORD, create_report_graph
from test_heatmaps import add_ping_batch
from test_stored_files import FakeStorageProvider

from app.models.campaign import CampaignCreative
from app.models.campaign_assignment import CampaignActivationEvent
from app.models.campaign_report import CampaignReport
from app.models.campaign_zone import CampaignZone
from app.models.installation_evidence import InstallationEvidenceSubmission
from app.models.trip import TripSession
from app.services.campaign_assignments import activation_snapshot_digest
from app.services.campaign_report_delivery import publish_campaign_report


def three_car_run(db_client, maker, *, vehicle_count=3, dominant=False):
    admin, advertiser, campaign = create_report_fixture(maker)
    for index in range(2, vehicle_count + 1):
        *_, assignment, _, _, _ = create_report_graph(
            maker,
            admin=admin,
            advertiser=advertiser,
            campaign=campaign,
            driver_email=f"area-driver-{index}@example.test",
            plate_number=f"AREA-{index}",
            started_at=DAY_1,
            **(
                {"distance_m": Decimal("1.00"), "estimated_impressions": Decimal("1.00")}
                if dominant
                else {}
            ),
        )
        proof = create_test_installation_evidence(
            maker, assignment_id=assignment.id, reviewed_by_user_id=admin.id
        )

        async def bind(assignment=assignment, proof=proof):
            async with maker() as session:
                creative = await session.scalar(
                    select(CampaignCreative).where(CampaignCreative.campaign_id == campaign.id)
                )
                event = await session.scalar(
                    select(CampaignActivationEvent).where(
                        CampaignActivationEvent.assignment_id == assignment.id
                    )
                )
                evidence = await session.get(InstallationEvidenceSubmission, proof.id)
                evidence.reviewed_at = event.occurred_at - timedelta(minutes=1)
                evidence.approved_until = event.occurred_at + timedelta(days=1)
                snapshot = {
                    **event.event_metadata["activation_snapshot"],
                    "creative_id": str(creative.id),
                    "installation_evidence_submission_id": str(evidence.id),
                    "installation_evidence_revision": evidence.revision,
                }
                event.event_metadata = {
                    **event.event_metadata,
                    "activation_snapshot": snapshot,
                    "activation_snapshot_sha256": activation_snapshot_digest(snapshot),
                }
                await session.commit()

        asyncio.run(bind())

    async def zone_and_trips():
        async with maker() as session:
            zone = CampaignZone(
                campaign_id=campaign.id,
                created_by_user_id=advertiser.id,
                name="Central area",
                zone_type="target",
                geom="MULTIPOLYGON(((3 6,3.1 6,3.1 6.1,3 6.1,3 6)))",
            )
            session.add(zone)
            await session.commit()
            return zone.id, list(
                await session.scalars(
                    select(TripSession.id).where(TripSession.campaign_id == campaign.id)
                )
            )

    zone_id, trips = asyncio.run(zone_and_trips())
    for trip in trips:
        add_ping_batch(
            maker,
            trip_id=trip,
            points=[
                (DAY_1 + timedelta(minutes=10), 6.05, 3.05),
                (DAY_1 + timedelta(minutes=11), 6.051, 3.051),
            ],
            idempotency_key=f"area-{trip}",
        )
    headers = auth_headers(db_client, advertiser.email, PASSWORD)
    response = db_client.post(
        "/api/v1/advertiser/reports",
        headers=headers,
        json={
            "client_request_id": str(uuid4()),
            "campaign_id": str(campaign.id),
            "start_date": DAY_1.date().isoformat(),
            "end_date": DAY_1.date().isoformat(),
        },
    )
    assert response.status_code == 202, response.text
    return advertiser, campaign, response.json(), headers


def test_released_areas_never_block_other_advertiser_outputs(
    db_client,
    db_sessionmaker,
    settings,
):
    # D105: three-car areas are shown, and every other output still answers.
    advertiser, campaign, run, headers = three_car_run(db_client, db_sessionmaker)

    path = f"/api/v1/advertiser/campaigns/{campaign.id}/report"
    params = {"start_at": DAY_1.isoformat(), "end_at": (DAY_1 + timedelta(days=1)).isoformat()}
    first = db_client.get(path, params=params, headers=headers)
    assert first.status_code == 200 and len(first.json()["areas"]) == 1, first.text
    result = db_client.get(path, params=params, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["totals"] == {
        "distance_m": "30000.00",
        "trip_count": 3,
        "driving_days": 1,
        "estimated_views": "1500.00",
    }
    assert result.json()["areas"] == first.json()["areas"]

    async def publish():
        async with db_sessionmaker() as session:
            row = await session.get(CampaignReport, UUID(run["id"]))
            assert "linked_source_recommendations" not in row.snapshot
            assert len(row.snapshot["campaigns"][0]["areas"]) == 1
        storage = FakeStorageProvider()
        assert (
            await publish_campaign_report(db_sessionmaker, report_id=run["id"], storage=storage)
            == "ready"
        )
        async with db_sessionmaker() as session:
            row = await session.get(CampaignReport, UUID(run["id"]))
            assert row.status == "ready"
        assert len(storage.contents) == 2
        csv = next(
            content for content in storage.contents.values() if not content.startswith(b"%PDF-")
        )
        for value in (b"30000.00", b"1500.00", b"Driving days", b"Estimated views"):
            assert value in csv

    asyncio.run(publish())
    base = f"/api/v1/advertiser/campaigns/{campaign.id}"
    for response in (
        db_client.get("/api/v1/advertiser/dashboard/summary", headers=headers),
        db_client.get(f"{base}/summary", headers=headers),
        db_client.get(f"{base}/trips", headers=headers),
        db_client.get(f"{base}/heatmap", params={"bbox": "3,6,3.1,6.1"}, headers=headers),
    ):
        assert response.status_code == 200, response.text

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from conftest import auth_headers, create_test_display_proof
from sqlalchemy import func, select
from test_advertiser_reports import DAY_1, PASSWORD, create_report_graph
from test_heatmaps import add_ping_batch
from test_measurement_runs import create_measurement_graph, issue_payload
from test_report_issuances import ReportStorage
from test_retargeting_source_links import source_payload

from app.jobs.exposure_segments import sweep_exposure_segments
from app.models.campaign import CampaignCreative
from app.models.campaign_assignment import CampaignActivationEvent
from app.models.campaign_zone import CampaignZone
from app.models.disclosure import DisclosureQueryDecision
from app.models.exposure_segment import ExposureSegment
from app.models.installation_evidence import InstallationEvidenceSubmission
from app.models.report_issuance import ReportIssuance
from app.models.trip import TripSession
from app.services.campaign_assignments import activation_snapshot_digest
from app.services.report_issuances import sweep_report_issuances


def three_car_run(db_client, maker):
    admin, advertiser, campaign = create_measurement_graph(maker)
    for index in (2, 3):
        *_, assignment, _, _, _ = create_report_graph(
            maker,
            admin=admin,
            advertiser=advertiser,
            campaign=campaign,
            driver_email=f"area-driver-{index}@example.test",
            plate_number=f"AREA-{index}",
            started_at=DAY_1,
        )
        proof = create_test_display_proof(
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
                evidence = await session.get(
                    InstallationEvidenceSubmission, proof.evidence_submission_id
                )
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
            points=[(DAY_1 + timedelta(minutes=10), 6.05, 3.05)],
            idempotency_key=f"area-{trip}",
        )
    headers = auth_headers(db_client, advertiser.email, PASSWORD)
    source = db_client.post(
        "/api/v1/advertiser/retargeting-sources",
        headers=headers | {"Idempotency-Key": str(uuid4())},
        json=source_payload(datetime.now(UTC) + timedelta(days=365)),
    )
    assert source.status_code == 201, source.text
    link = db_client.post(
        "/api/v1/advertiser/retargeting-source-links",
        headers=headers | {"Idempotency-Key": str(uuid4())},
        json={
            "source_id": source.json()["id"],
            "campaign_id": str(campaign.id),
            "zone_id": str(zone_id),
            "start_at": DAY_1.isoformat(),
            "end_at": (DAY_1 + timedelta(days=1)).isoformat(),
        },
    )
    assert link.status_code == 201, link.text
    response = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=issue_payload(campaign.id),
        headers=auth_headers(db_client, admin.email, PASSWORD),
    )
    assert response.status_code == 201, response.text
    return advertiser, campaign, response.json(), headers


def test_released_areas_never_block_other_advertiser_outputs(
    db_client,
    db_sessionmaker,
    settings,
):
    # D105: three-car areas are shown, and every other output still answers.
    advertiser, campaign, run, headers = three_car_run(db_client, db_sessionmaker)

    async def ready():
        assert (
            await sweep_exposure_segments({"settings": settings, "sessionmaker": db_sessionmaker})
            == 1
        )
        async with db_sessionmaker() as session:
            # Private measurement/segment construction is not a public disclosure.
            assert (
                await session.scalar(select(func.count()).select_from(DisclosureQueryDecision)) == 0
            )

    asyncio.run(ready())
    path = f"/api/v1/advertiser/campaigns/{campaign.id}/report"
    params = {"start_at": DAY_1.isoformat(), "end_at": (DAY_1 + timedelta(days=1)).isoformat()}
    first = db_client.get(path, params=params, headers=headers)
    assert first.status_code == 200 and len(first.json()["areas"]) == 1, first.text
    issuance = db_client.post(
        f"/api/v1/advertiser/measurement-runs/{run['id']}/report-issuances",
        headers=headers,
        json={"client_request_id": str(uuid4())},
    )
    assert issuance.status_code == 202, issuance.text
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
            row = await session.get(ReportIssuance, UUID(issuance.json()["id"]))
            recommendations = row.snapshot["linked_source_recommendations"][0]
            assert recommendations["state"] == "ready"
            assert recommendations["recommendations"]
            assert len(row.snapshot["exposure"]["zones"]) == 1
        storage = ReportStorage()
        assert (
            await sweep_report_issuances(
                {"sessionmaker": db_sessionmaker, "settings": settings, "storage": storage}
            )
            == 1
        )
        async with db_sessionmaker() as session:
            row = await session.get(ReportIssuance, UUID(issuance.json()["id"]))
            assert row.status == "ready"
        assert len(storage.contents) == 2
        csv = next(
            content for content in storage.contents.values() if content.startswith(b"section,")
        )
        for value in (b"30000.00", b"1500.00", b"Driving days", b"Estimated views"):
            assert value in csv
        async with db_sessionmaker() as session:
            return await session.scalar(
                select(ExposureSegment.id).where(ExposureSegment.campaign_id == campaign.id)
            )

    segment_id = asyncio.run(publish())
    base = f"/api/v1/advertiser/campaigns/{campaign.id}"
    for response in (
        db_client.get("/api/v1/advertiser/dashboard/summary", headers=headers),
        db_client.get(f"{base}/summary", headers=headers),
        db_client.get(f"{base}/trips", headers=headers),
        db_client.get(f"{base}/heatmap", params={"bbox": "3,6,3.1,6.1"}, headers=headers),
    ):
        assert response.status_code == 200, response.text
    exported = db_client.post(
        f"/api/v1/advertiser/exposure-segments/{segment_id}/exports",
        headers=headers | {"Idempotency-Key": str(uuid4())},
        json={},
    )
    assert exported.status_code == 201, exported.text

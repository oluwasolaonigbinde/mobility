"""Development preview uses ordinary data access, with no legal display switches."""

from app.core.config import Settings


def test_removed_display_and_collection_switches_have_no_replacement() -> None:
    removed = {
        "privacy_disclosure_live_authorized",
        "privacy_disclosure_synthetic_test_mode",
        "privacy_collection_live_authorized",
        "privacy_collection_synthetic_test_mode",
        "privacy_disclosure_config_reference",
        "privacy_query_history_retention_reference",
        "measurement_live_issuance_authorized",
        "measurement_report_method_reference",
    }
    assert removed.isdisjoint(Settings.model_fields)


def test_default_aggregation_supports_navigation_frozen_reports_and_maps(
    postgis_db_client,
    postgis_db_sessionmaker,
):
    import asyncio
    from datetime import timedelta

    from conftest import auth_headers, create_test_installation_evidence
    from report_fixtures import DAY_1, PASSWORD, create_report_fixture
    from sqlalchemy import select
    from test_advertiser_reports import create_report_graph
    from test_heatmaps import add_ping_batch

    from app.core.config import get_settings
    from app.models.campaign import CampaignCreative
    from app.models.campaign_assignment import CampaignActivationEvent
    from app.models.campaign_zone import CampaignZone
    from app.models.disclosure import DisclosureQueryDecision
    from app.models.installation_evidence import InstallationEvidenceSubmission
    from app.models.trip import TripSession
    from app.services.campaign_assignments import activation_snapshot_digest

    baseline = Settings(environment="test")
    assert (baseline.privacy_min_vehicles_per_cell, baseline.privacy_min_resolution_m) == (3, 500)
    assert baseline.privacy_legal_approval_reference == ""
    postgis_db_client.app.dependency_overrides[get_settings] = lambda: baseline
    admin, advertiser, campaign = create_report_fixture(postgis_db_sessionmaker)
    for day in range(2):
        for index in range(6):
            *_, assignment, trip, _, _ = create_report_graph(
                postgis_db_sessionmaker,
                admin=admin,
                advertiser=advertiser,
                campaign=campaign,
                driver_email=f"navigation-{day}-{index}@example.com",
                plate_number=f"NAV-{day}-{index}",
                started_at=DAY_1 + timedelta(days=day),
            )
            proof = create_test_installation_evidence(
                postgis_db_sessionmaker,
                assignment_id=assignment.id,
                reviewed_by_user_id=admin.id,
            )

            async def bind(assignment=assignment, proof=proof):
                async with postgis_db_sessionmaker() as session:
                    event = await session.scalar(
                        select(CampaignActivationEvent).where(
                            CampaignActivationEvent.assignment_id == assignment.id
                        )
                    )
                    creative = await session.scalar(
                        select(CampaignCreative).where(CampaignCreative.campaign_id == campaign.id)
                    )
                    evidence = await session.get(InstallationEvidenceSubmission, proof.id)
                    evidence.reviewed_at = event.occurred_at - timedelta(minutes=1)
                    evidence.approved_until = event.occurred_at + timedelta(days=1)
                    snapshot = dict(event.event_metadata["activation_snapshot"])
                    snapshot.update(
                        creative_id=str(creative.id),
                        installation_evidence_submission_id=str(evidence.id),
                        installation_evidence_revision=evidence.revision,
                    )
                    event.event_metadata = {
                        **event.event_metadata,
                        "activation_snapshot": snapshot,
                        "activation_snapshot_sha256": activation_snapshot_digest(snapshot),
                    }
                    await session.commit()

            asyncio.run(bind())

    async def prepare():
        async with postgis_db_sessionmaker() as session:
            zone = CampaignZone(
                campaign_id=campaign.id,
                created_by_user_id=advertiser.id,
                name="Wuse route",
                zone_type="target",
                geom="MULTIPOLYGON(((3 6,3.1 6,3.1 6.1,3 6.1,3 6)))",
            )
            session.add(zone)
            await session.commit()
            trips = list(
                await session.scalars(
                    select(TripSession).where(TripSession.campaign_id == campaign.id)
                )
            )
            return zone.id, trips

    zone_id, trips = asyncio.run(prepare())
    for trip in trips:
        add_ping_batch(
            postgis_db_sessionmaker,
            trip_id=trip.id,
            points=[
                (trip.started_at + timedelta(minutes=10), 6.05, 3.05),
                (trip.started_at + timedelta(minutes=11), 6.051, 3.051),
            ],
            idempotency_key=f"navigation-{trip.id}",
        )
    headers = auth_headers(postgis_db_client, advertiser.email, PASSWORD)
    dates = {"start_at": DAY_1.isoformat(), "end_at": (DAY_1 + timedelta(days=2)).isoformat()}
    for path in (
        "/api/v1/advertiser/dashboard/summary",
        f"/api/v1/advertiser/campaigns/{campaign.id}/summary",
        f"/api/v1/advertiser/campaigns/{campaign.id}/daily-metrics",
        f"/api/v1/advertiser/campaigns/{campaign.id}/trips",
    ):
        response = postgis_db_client.get(path, headers=headers, params=dates)
        assert response.status_code == 200, response.text
        replay = postgis_db_client.get(path, headers=headers, params=dates)
        assert replay.json() == response.json()
    report = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/report", headers=headers, params=dates
    )
    assert report.status_code == 200, report.text
    assert report.json()["totals"]["trip_count"] == 13
    heatmap = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=headers,
        params={**dates, "bbox": "3,6,3.1,6.1", "resolution_m": 500, "metric": "trip_count"},
    )
    assert heatmap.status_code == 200, heatmap.text
    assert len(heatmap.json()["features"]) == 1
    assert heatmap.json()["features"][0]["properties"]["trip_count"] == 13

    async def history():
        async with postgis_db_sessionmaker() as session:
            return list(await session.scalars(select(DisclosureQueryDecision)))

    records = asyncio.run(history())
    assert len(records) >= 6
    assert all(row.decision == "served" for row in records)

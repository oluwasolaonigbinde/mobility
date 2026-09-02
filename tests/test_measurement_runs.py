import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_creative,
    create_test_display_proof,
    create_test_organization,
    create_test_payout_rule,
    create_test_user,
)
from sqlalchemy import delete, func, select
from test_advertiser_reports import DAY_1, PASSWORD, add_payout_calculation, create_report_graph

from app.core.config import get_settings
from app.models.campaign import CampaignStatus, CreativeStatus
from app.models.campaign_assignment import CampaignActivationEvent
from app.models.impression import ImpressionEstimate
from app.models.installation_evidence import InstallationEvidenceSubmission
from app.models.measurement import MeasurementRun
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip import TripSession
from app.models.trip_analytics import TripAnalytics
from app.models.user import UserRole
from app.schemas.measurement import MeasurementRunCreate
from app.services.campaign_assignments import activation_snapshot_digest
from app.services.measurement import issue_measurement_run
from app.services.report_cohorts import select_report_cohort


def create_measurement_graph(
    db_sessionmaker,
    *,
    identity_tag: str = "measurement",
    identity_domain: str = "example.com",
    organization_name: str = "Acme Ads",
    billing_email: str = "billing@acme.test",
    campaign_name: str = "Launch Campaign",
    service_city: str = "Lagos",
    advertiser_first: bool = False,
):
    actors = {}
    actor_roles = (
        (UserRole.ADVERTISER, UserRole.ADMIN)
        if advertiser_first
        else (UserRole.ADMIN, UserRole.ADVERTISER)
    )
    for role in actor_roles:
        actors[role] = create_test_user(
            db_sessionmaker,
            email=f"{identity_tag}-{role.value}@{identity_domain}",
            password=PASSWORD,
            role=role,
        )
    admin = actors[UserRole.ADMIN]
    advertiser = actors[UserRole.ADVERTISER]
    organization, _ = create_test_organization(
        db_sessionmaker,
        name=organization_name,
        billing_email=billing_email,
        owner_user_id=advertiser.id,
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=DAY_1 - timedelta(days=1),
        end_at=DAY_1 + timedelta(days=10),
        name=campaign_name,
    )
    creative = create_test_campaign_creative(
        db_sessionmaker,
        campaign_id=campaign.id,
        creative_status=CreativeStatus.APPROVED,
    )
    *_, assignment, _trip, _analytics, _estimate = create_report_graph(
        db_sessionmaker,
        admin=admin,
        advertiser=advertiser,
        campaign=campaign,
        driver_email=f"{identity_tag}-driver@{identity_domain}",
        plate_number="MEASURE-1",
        started_at=DAY_1,
        service_city=service_city,
        driver_phone=None if identity_domain.endswith(".invalid") else "+234555000",
    )
    proof = create_test_display_proof(
        db_sessionmaker,
        assignment_id=assignment.id,
        reviewed_by_user_id=admin.id,
    )

    async def bind_proof() -> None:
        async with db_sessionmaker() as session:
            event = await session.scalar(
                select(CampaignActivationEvent).where(
                    CampaignActivationEvent.assignment_id == assignment.id
                )
            )
            assert event is not None
            evidence = await session.get(
                InstallationEvidenceSubmission, proof.evidence_submission_id
            )
            assert evidence is not None
            evidence.reviewed_at = event.occurred_at - timedelta(minutes=1)
            evidence.approved_until = event.occurred_at + timedelta(days=1)
            snapshot = dict(event.event_metadata["activation_snapshot"])
            snapshot["creative_id"] = str(creative.id)
            snapshot["installation_evidence_submission_id"] = str(proof.evidence_submission_id)
            snapshot["installation_evidence_revision"] = evidence.revision
            event.event_metadata = {
                **event.event_metadata,
                "activation_snapshot": snapshot,
                "activation_snapshot_sha256": activation_snapshot_digest(snapshot),
            }
            await session.commit()

    asyncio.run(bind_proof())
    return admin, advertiser, campaign


def issue_payload(campaign_id, client_request_id=None):
    return {
        "campaign_id": str(campaign_id),
        "client_request_id": str(client_request_id or uuid4()),
        "period_start_at": DAY_1.isoformat(),
        "period_end_at": (DAY_1 + timedelta(days=1)).isoformat(),
        "mode": "performance_only",
        "test_only": True,
    }


def test_measurement_run_replays_reproduces_reissues_and_drives_report(
    db_client, db_sessionmaker, settings
) -> None:
    admin, advertiser, campaign = create_measurement_graph(db_sessionmaker)
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    request_id = uuid4()
    payload = issue_payload(campaign.id, request_id)

    first = db_client.post("/api/v1/admin/measurement-runs", json=payload, headers=admin_headers)
    assert first.status_code == 201, first.text
    first_body = first.json()
    assert first_body["reproducible"] is True
    assert first_body["mode"] == "performance_only"
    assert first_body["result_manifest"]["roi"] is None
    assert first_body["proof_bindings"][0]["creative_id"]

    replay = db_client.post("/api/v1/admin/measurement-runs", json=payload, headers=admin_headers)
    assert replay.status_code == 201
    assert replay.json()["id"] == first_body["id"]

    changed = {**payload, "period_end_at": (DAY_1 + timedelta(days=2)).isoformat()}
    conflict = db_client.post("/api/v1/admin/measurement-runs", json=changed, headers=admin_headers)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "MEASUREMENT_REQUEST_REUSE_CONFLICT"

    async def change_source() -> None:
        async with db_sessionmaker() as session:
            payout = await session.scalar(
                select(PayoutCalculation).where(PayoutCalculation.campaign_id == campaign.id)
            )
            assert payout is not None
            payout.final_payout = Decimal("1300.00")
            await session.commit()

    asyncio.run(change_source())
    second = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=issue_payload(campaign.id),
        headers=admin_headers,
    )
    assert second.status_code == 201, second.text
    second_body = second.json()
    assert second_body["id"] != first_body["id"]
    assert second_body["reissue_of_run_id"] == first_body["id"]
    assert second_body["result_manifest_sha256"] != first_body["result_manifest_sha256"]

    frozen = db_client.get(
        f"/api/v1/admin/measurement-runs/{first_body['id']}", headers=admin_headers
    )
    assert frozen.status_code == 200
    assert frozen.json()["reproducible"] is True
    report = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/report",
        params={
            "start_at": DAY_1.isoformat(),
            "end_at": (DAY_1 + timedelta(days=1)).isoformat(),
        },
        headers=advertiser_headers,
    )
    assert report.status_code == 200, report.text
    assert report.json()["measurement_run"]["id"] == second_body["id"]
    assert report.json()["measurement_result"]["title"] == "Campaign Performance Analysis"
    assert report.json()["measurement_result"]["roi"] is None

    live_settings = settings.model_copy(
        update={
            "privacy_disclosure_synthetic_test_mode": False,
            "privacy_disclosure_live_authorized": True,
            "privacy_legal_approval_reference": "approved-legal-v1",
            "privacy_disclosure_config_reference": "approved-disclosure-v1",
            "privacy_query_history_retention_reference": "approved-retention-v1",
            "measurement_live_issuance_authorized": True,
            "measurement_report_method_reference": "measurement-contract-v1",
        }
    )
    db_client.app.dependency_overrides[get_settings] = lambda: live_settings
    blocked_live = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/report",
        params={
            "start_at": DAY_1.isoformat(),
            "end_at": (DAY_1 + timedelta(days=1)).isoformat(),
        },
        headers=advertiser_headers,
    )
    assert blocked_live.status_code == 503
    assert blocked_live.json()["error"]["code"] == "MEASUREMENT_LIVE_ISSUANCE_BLOCKED"

    async def count_runs() -> int:
        async with db_sessionmaker() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(MeasurementRun)
                    .where(MeasurementRun.campaign_id == campaign.id)
                )
                or 0
            )

    assert asyncio.run(count_runs()) == 2


def test_measurement_and_screen_share_trip_start_cohort_when_sources_arrive_late(
    db_client, db_sessionmaker
) -> None:
    admin, advertiser, campaign = create_measurement_graph(
        db_sessionmaker, identity_tag="measurement-late-sources"
    )

    async def delay_derivative_sources() -> None:
        async with db_sessionmaker() as session:
            estimate = await session.scalar(
                select(ImpressionEstimate).where(ImpressionEstimate.campaign_id == campaign.id)
            )
            payout = await session.scalar(
                select(PayoutCalculation).where(PayoutCalculation.campaign_id == campaign.id)
            )
            assert estimate is not None and payout is not None
            estimate.estimated_at = estimate.estimated_at + timedelta(days=3)
            payout.calculated_at = DAY_1 + timedelta(days=4)
            await session.commit()

    asyncio.run(delay_derivative_sources())
    response = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=issue_payload(campaign.id),
        headers=auth_headers(db_client, admin.email, PASSWORD),
    )

    assert response.status_code == 201, response.text
    run = response.json()
    assert len(run["input_manifest"]["sources"]["impression_estimates"]) == 1, run["input_manifest"]
    metrics = {row["id"]: row for row in run["result_manifest"]["metrics"]}
    assert metrics["modelled_potential_contacts"]["value"] == "500.00"
    assert metrics["driver_campaign_cost"]["totals_by_currency"] == [
        {"currency": "NGN", "value": "1200.00"}
    ]
    report = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/report",
        params={
            "start_at": DAY_1.isoformat(),
            "end_at": (DAY_1 + timedelta(days=1)).isoformat(),
        },
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    ).json()
    assert report["impression_summary"]["estimated_impressions"] == "500.00"
    assert report["cost_summary"]["totals_by_currency"][0]["final_payout_total"] == "1200.00"
    assert len(run["input_manifest"]["cohort"]) == 1
    assert run["input_manifest"]["cohort"][0]["trip_fingerprint"]
    for source_rows in run["input_manifest"]["sources"].values():
        assert all(row["source_fingerprint"] for row in source_rows)

    repeated = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=issue_payload(campaign.id),
        headers=auth_headers(db_client, admin.email, PASSWORD),
    ).json()
    assert repeated["input_manifest_sha256"] == run["input_manifest_sha256"]
    assert repeated["result_manifest_sha256"] == run["result_manifest_sha256"]
    assert repeated["report_snapshot_sha256"] == run["report_snapshot_sha256"]


def test_profile_revision_reissues_current_measurement_without_rewriting_frozen_run(
    db_client, db_sessionmaker
) -> None:
    admin, _, campaign = create_measurement_graph(
        db_sessionmaker,
        identity_tag="measurement-profile-drift",
    )
    headers = auth_headers(db_client, admin.email, PASSWORD)
    first = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=issue_payload(campaign.id),
        headers=headers,
    ).json()
    impression_source = first["input_manifest"]["sources"]["impression_estimates"][0]
    profile_id = impression_source["traffic_density_profile_id"]
    profile = db_client.get(
        f"/api/v1/admin/traffic-density-profiles/{profile_id}", headers=headers
    ).json()

    revised_profile = db_client.patch(
        f"/api/v1/admin/traffic-density-profiles/{profile_id}",
        headers=headers,
        json={
            "traffic_density_per_km": "240",
            "expected_revision": profile["revision"],
            "expected_value_fingerprint": profile["value_fingerprint"],
        },
    )
    assert revised_profile.status_code == 200, revised_profile.text

    second = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=issue_payload(campaign.id),
        headers=headers,
    )
    assert second.status_code == 201, second.text
    second_body = second.json()
    assert second_body["reissue_of_run_id"] == first["id"]
    assert second_body["input_manifest_sha256"] != first["input_manifest_sha256"]
    assert second_body["input_manifest"]["sources"]["impression_estimates"] == []

    frozen = db_client.get(f"/api/v1/admin/measurement-runs/{first['id']}", headers=headers).json()
    assert frozen["input_manifest_sha256"] == first["input_manifest_sha256"]
    assert frozen["input_manifest"]["sources"]["impression_estimates"] == [impression_source]
    assert frozen["reproducible"] is True


def test_measurement_run_fails_closed_without_proof_or_roi_prerequisites(
    db_client, db_sessionmaker
) -> None:
    admin, _, campaign = create_measurement_graph(db_sessionmaker)
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)

    async def remove_creative_binding() -> None:
        async with db_sessionmaker() as session:
            event = await session.scalar(
                select(CampaignActivationEvent).where(
                    CampaignActivationEvent.assignment_id.in_(
                        select(PayoutCalculation.assignment_id).where(
                            PayoutCalculation.campaign_id == campaign.id
                        )
                    )
                )
            )
            assert event is not None
            snapshot = dict(event.event_metadata["activation_snapshot"])
            snapshot.pop("creative_id")
            event.event_metadata = {
                **event.event_metadata,
                "activation_snapshot": snapshot,
                "activation_snapshot_sha256": activation_snapshot_digest(snapshot),
            }
            await session.commit()

    asyncio.run(remove_creative_binding())
    missing_proof = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=issue_payload(campaign.id),
        headers=admin_headers,
    )
    assert missing_proof.status_code == 409
    assert missing_proof.json()["error"]["code"] == "MEASUREMENT_PROOF_REQUIRED"

    roi_missing = issue_payload(campaign.id)
    roi_missing["mode"] = "roi_enabled"
    response = db_client.post(
        "/api/v1/admin/measurement-runs", json=roi_missing, headers=admin_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ROI_PREREQUISITES_REQUIRED"


def test_synthetic_roi_run_freezes_complete_method_and_inputs(db_client, db_sessionmaker) -> None:
    admin, _, campaign = create_measurement_graph(db_sessionmaker)
    payload = issue_payload(campaign.id)
    payload["mode"] = "roi_enabled"
    payload["roi"] = {
        "attributed_revenue": "2400.00",
        "approved_cost_basis": "1200.00",
        "currency": "NGN",
        "conversion_provenance": "SYNTHETIC_TEST_ONLY conversion fixture",
        "revenue_provenance": "SYNTHETIC_TEST_ONLY revenue fixture",
        "reporting_cutoff": (DAY_1 + timedelta(days=1)).isoformat(),
        "synthetic": True,
        "method": {
            "revision": "synthetic-roi-v1",
            "approval_reference": "SYNTHETIC_TEST_ONLY",
            "attribution_rule": "Synthetic conversion belongs to the fixture campaign.",
            "attribution_window": "Synthetic one-day fixture window.",
            "cost_basis": "Frozen driver campaign cost in NGN.",
            "exclusions": "No synthetic exclusions.",
            "corrections": "Reissue on changed fixture input.",
            "late_data": "Late fixture data requires reissue.",
        },
    }
    response = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=payload,
        headers=auth_headers(db_client, admin.email, PASSWORD),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["reproducible"] is True
    assert body["roi_method_revision"] == "synthetic-roi-v1"
    assert body["result_manifest"]["roi"]["ratio"] == "1"
    assert body["result_manifest"]["roi_gate"] == {
        "decision": "INCLUDE",
        "test_only": True,
    }


def test_production_measurement_issuance_stays_default_denied(
    db_client, db_sessionmaker, settings
) -> None:
    admin, _, campaign = create_measurement_graph(db_sessionmaker)
    headers = auth_headers(db_client, admin.email, PASSWORD)
    live_settings = settings.model_copy(
        update={
            "privacy_disclosure_synthetic_test_mode": False,
            "privacy_disclosure_live_authorized": True,
            "privacy_legal_approval_reference": "approved-legal-v1",
            "privacy_disclosure_config_reference": "approved-disclosure-v1",
            "privacy_query_history_retention_reference": "approved-retention-v1",
        }
    )
    db_client.app.dependency_overrides[get_settings] = lambda: live_settings
    response = db_client.post(
        "/api/v1/admin/measurement-runs",
        json={**issue_payload(campaign.id), "test_only": False},
        headers=headers,
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MEASUREMENT_LIVE_ISSUANCE_BLOCKED"


def test_measurement_result_manifest_is_canonical_json() -> None:
    # A small contract guard against non-JSON Decimal/date values leaking into
    # persisted manifests and making fingerprints database-dependent.
    from app.services.measurement import calculate_measurement_result

    manifest = {
        "mode": "performance_only",
        "test_only": True,
        "formula_version": "measurement-result-v1",
        "method_revision": "measurement-contract-v1",
        "period": {"start_at": DAY_1.isoformat(), "end_at": (DAY_1 + timedelta(1)).isoformat()},
        "proof_manifest_sha256": "a" * 64,
        "sources": {
            "trip_analytics": [],
            "impression_estimates": [],
            "payout_calculations": [],
        },
        "roi": None,
    }
    json.dumps(calculate_measurement_result(manifest), sort_keys=True)


def test_postgres_cohort_orders_trips_and_selects_one_replacement_payout(
    postgis_db_sessionmaker, settings
) -> None:
    admin, advertiser, campaign = create_measurement_graph(
        postgis_db_sessionmaker, identity_tag="measurement-pg-cohort"
    )
    create_report_graph(
        postgis_db_sessionmaker,
        admin=admin,
        advertiser=advertiser,
        campaign=campaign,
        driver_email="measurement-pg-cohort-second@example.com",
        plate_number="PG-COHORT-2",
        started_at=DAY_1 + timedelta(hours=1),
    )

    async def original_sources():
        async with postgis_db_sessionmaker() as session:
            trip = await session.scalar(
                select(TripSession)
                .where(TripSession.campaign_id == campaign.id)
                .order_by(TripSession.started_at)
            )
            assert trip is not None
            analytics = await session.scalar(
                select(TripAnalytics).where(TripAnalytics.trip_session_id == trip.id)
            )
            estimate = await session.scalar(
                select(ImpressionEstimate).where(ImpressionEstimate.trip_session_id == trip.id)
            )
            ledger = await session.scalar(
                select(EarningsLedgerEntry).where(EarningsLedgerEntry.trip_session_id == trip.id)
            )
            assert analytics is not None and estimate is not None and ledger is not None
            await session.execute(
                delete(EarningsLedgerEntry).where(EarningsLedgerEntry.trip_session_id == trip.id)
            )
            await session.commit()
            return trip, analytics, estimate, ledger.driver_user_id

    trip, analytics, estimate, driver_user_id = asyncio.run(original_sources())
    replacement_rule = create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        currency=campaign.currency,
        status="inactive",
    )
    add_payout_calculation(
        postgis_db_sessionmaker,
        trip=trip,
        analytics=analytics,
        estimate=estimate,
        payout_rule_id=replacement_rule.id,
        driver_user_id=driver_user_id,
        status="calculated",
        final_payout=Decimal("700.00"),
        gross_payout=Decimal("800.00"),
        calculated_at=DAY_1 + timedelta(days=3),
    )

    async def selected():
        async with postgis_db_sessionmaker() as session:
            return await select_report_cohort(
                session,
                campaign_id=campaign.id,
                start_at=DAY_1,
                end_at=DAY_1 + timedelta(days=1),
                settings=settings,
            )

    cohort = asyncio.run(selected())
    assert [row.started_at for row in cohort.trips] == sorted(
        row.started_at for row in cohort.trips
    )
    first_trip_payouts = [row for row in cohort.payouts if row.trip_session_id == trip.id]
    assert len(first_trip_payouts) == 1
    assert first_trip_payouts[0].final_payout == Decimal("700.00")


def test_concurrent_same_request_converges_on_postgres(postgis_db_sessionmaker, settings) -> None:
    admin, _, campaign = create_measurement_graph(postgis_db_sessionmaker)
    payload = MeasurementRunCreate.model_validate(issue_payload(campaign.id))

    async def issue_once():
        async with postgis_db_sessionmaker() as session:
            run = await issue_measurement_run(
                session,
                actor_user_id=admin.id,
                payload=payload,
                settings=settings,
            )
            await session.commit()
            return run.id

    async def run_both():
        return await asyncio.gather(issue_once(), issue_once())

    first_id, second_id = asyncio.run(run_both())
    assert first_id == second_id

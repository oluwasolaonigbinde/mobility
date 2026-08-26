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
    create_test_user,
)
from sqlalchemy import func, select
from test_advertiser_reports import DAY_1, PASSWORD, create_report_graph

from app.core.config import get_settings
from app.models.campaign import CampaignStatus, CreativeStatus
from app.models.campaign_assignment import CampaignActivationEvent
from app.models.installation_evidence import InstallationEvidenceSubmission
from app.models.measurement import MeasurementRun
from app.models.payout import PayoutCalculation
from app.models.user import UserRole
from app.schemas.measurement import MeasurementRunCreate
from app.services.campaign_assignments import activation_snapshot_digest
from app.services.measurement import issue_measurement_run


def create_measurement_graph(db_sessionmaker):
    admin = create_test_user(
        db_sessionmaker,
        email="measurement-admin@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    advertiser = create_test_user(
        db_sessionmaker,
        email="measurement-advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=DAY_1 - timedelta(days=1),
        end_at=DAY_1 + timedelta(days=10),
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
        driver_email="measurement-driver@example.com",
        plate_number="MEASURE-1",
        started_at=DAY_1,
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

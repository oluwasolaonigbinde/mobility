from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid5

import pytest
from conftest import auth_headers, create_test_organization, create_test_user
from sqlalchemy import func, select
from test_measurement_runs import DAY_1, PASSWORD, create_measurement_graph, issue_payload
from test_retargeting_source_links import source_payload

from app.adapters.ad_platforms import FakeAdPlatformAdapter
from app.adapters.crypto import EnvelopeCryptoProvider
from app.adapters.disbursement import FakeDisbursementAdapter
from app.api.v1.dependencies import get_ad_platform_adapter
from app.models.audience_delivery import AudienceDelivery
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.disbursement import PayoutBatch, PayoutBatchLine
from app.models.driver import DriverProfile
from app.models.measurement import MeasurementRun
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.report_issuance import ReportArtifact, ReportIssuance
from app.models.user import User, UserRole
from app.services.audience import materialize_exposure_segment
from app.services.disbursements import (
    approve_payout_batch,
    create_payout_batch_draft,
    reserve_payout_batch,
)
from app.services.payees import (
    VerifiedBankAccountDetails,
    add_verified_bank_account_version,
    create_pilot_payee,
)
from scripts import evaluate_pilot_gates
from scripts.run_w403b_synthetic_journey import (
    CORRELATION_ID,
    EXPECTED_BLOCKERS,
    STAGES,
)

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_DOMAIN = "cardvert.invalid"


@dataclass(frozen=True)
class FrozenReceipt:
    correlation_id: str
    campaign_id: str
    measurement_run_id: str
    result_sha256: str
    audience_delivery_count: int
    report_issuance_count: int
    report_artifact_count: int
    payout_instruction_count: int
    payout_batch_status: str
    fake_activation_calls: int
    live_activation_calls: int
    disbursement_provider_calls: int
    synthetic_ping_batches: int
    live_gps_claims: int


async def _add_abuja_zone(db_sessionmaker, campaign_id: UUID, advertiser_id: UUID) -> UUID:
    async with db_sessionmaker() as session:
        zone = CampaignZone(
            campaign_id=campaign_id,
            created_by_user_id=advertiser_id,
            name=f"Synthetic Abuja target · {CORRELATION_ID}",
            zone_type=CampaignZoneType.TARGET,
            geom="MULTIPOLYGON(((7.39 9.07,7.41 9.07,7.41 9.09,7.39 9.09,7.39 9.07)))",
        )
        session.add(zone)
        await session.commit()
        return zone.id


def _run_pwa_proof() -> dict[str, object]:
    environment = dict(os.environ)
    environment["W403B_SYNTHETIC"] = "1"
    result = subprocess.run(
        (
            "npm",
            "run",
            "test:e2e",
            "--",
            "w403b-synthetic-pilot-journey.spec.ts",
            "--project=mobile-chrome",
        ),
        cwd=ROOT / "frontend",
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    assert result.returncode == 0
    marker = "W403B_BROWSER_RECEIPT="
    receipt_lines = [line for line in result.stdout.splitlines() if marker in line]
    assert len(receipt_lines) == 1
    return json.loads(receipt_lines[0].split(marker, 1)[1])


async def _materialize_segment(
    db_sessionmaker,
    settings,
    *,
    link_id: UUID,
    run_id: UUID,
) -> UUID:
    async with db_sessionmaker() as session:
        segment = await materialize_exposure_segment(
            session,
            settings=settings,
            source_link_id=link_id,
            measurement_run_id=run_id,
        )
        await session.commit()
        return segment.id


async def _freeze_payout_instruction(
    db_sessionmaker,
    *,
    campaign_id: UUID,
    admin: User,
    checker: User,
) -> tuple[UUID, str]:
    async with db_sessionmaker() as session:
        calculation = await session.scalar(
            select(PayoutCalculation).where(PayoutCalculation.campaign_id == campaign_id)
        )
        assert calculation is not None
        profile = await session.get(DriverProfile, calculation.driver_profile_id)
        assert profile is not None
        driver = await session.get(User, profile.user_id)
        assert driver is not None
        payee, _ = await create_pilot_payee(
            session,
            driver_profile_id=calculation.driver_profile_id,
            actor_user_id=admin.id,
        )
        await add_verified_bank_account_version(
            session,
            payee_id=payee.id,
            details=VerifiedBankAccountDetails(
                account_name="Synthetic Abuja Driver",
                account_number="0000000000",
                bank_code="000",
            ),
            verification_reference=f"SYNTHETIC_TEST_ONLY:{CORRELATION_ID}",
            actor_user_id=admin.id,
            crypto=EnvelopeCryptoProvider(keys={1: b"w" * 32}, active_key_version=1),
        )
        entry = EarningsLedgerEntry(
            payout_calculation_id=None,
            driver_profile_id=calculation.driver_profile_id,
            driver_user_id=driver.id,
            campaign_id=campaign_id,
            trip_session_id=calculation.trip_session_id,
            vehicle_id=calculation.vehicle_id,
            entry_type="adjustment",
            status="available",
            amount=Decimal("100.00"),
            currency="NGN",
            description=f"Synthetic payout instruction · {CORRELATION_ID}",
            occurred_at=calculation.calculated_at,
            ledger_metadata={"synthetic_test": True, "correlation_id": CORRELATION_ID},
        )
        session.add(entry)
        await session.flush()
        batch = await create_payout_batch_draft(session, currency="NGN", actor_user_id=admin.id)
        _, lines = await reserve_payout_batch(
            session,
            batch_id=batch.id,
            ledger_entry_ids=(entry.id,),
            actor_user_id=admin.id,
        )
        await approve_payout_batch(session, batch_id=batch.id, actor_user_id=checker.id)
        await session.commit()
        assert len(lines) == 1
        return batch.id, lines[0].instruction_fingerprint


async def _receipt(
    db_sessionmaker,
    *,
    campaign_id: UUID,
    run_id: UUID,
    batch_id: UUID,
    fake_activation_calls: int,
    live_activation_calls: int,
    disbursement_provider_calls: int,
    synthetic_ping_batches: int,
    live_gps_claims: int,
) -> FrozenReceipt:
    async with db_sessionmaker() as session:
        run = await session.get(MeasurementRun, run_id)
        batch = await session.get(PayoutBatch, batch_id)
        assert run is not None and batch is not None
        counts = []
        for model in (AudienceDelivery, ReportIssuance, ReportArtifact, PayoutBatchLine):
            counts.append(int(await session.scalar(select(func.count()).select_from(model)) or 0))
        return FrozenReceipt(
            correlation_id=CORRELATION_ID,
            campaign_id=str(campaign_id),
            measurement_run_id=str(run_id),
            result_sha256=run.result_manifest_sha256,
            audience_delivery_count=counts[0],
            report_issuance_count=counts[1],
            report_artifact_count=counts[2],
            payout_instruction_count=counts[3],
            payout_batch_status=batch.status,
            fake_activation_calls=fake_activation_calls,
            live_activation_calls=live_activation_calls,
            disbursement_provider_calls=disbursement_provider_calls,
            synthetic_ping_batches=synthetic_ping_batches,
            live_gps_claims=live_gps_claims,
        )


def test_correlated_synthetic_pilot_journey(db_client, db_sessionmaker, settings) -> None:
    completed: list[str] = []
    admin, advertiser, campaign = create_measurement_graph(
        db_sessionmaker,
        identity_tag=CORRELATION_ID,
        identity_domain=IDENTITY_DOMAIN,
        organization_name=f"Synthetic advertiser · {CORRELATION_ID}",
        billing_email=f"{CORRELATION_ID}-billing@{IDENTITY_DOMAIN}",
        campaign_name=f"Synthetic Abuja Campaign · {CORRELATION_ID}",
        service_city="Abuja",
        advertiser_first=True,
    )
    assert advertiser.email == f"{CORRELATION_ID}-advertiser@{IDENTITY_DOMAIN}"
    completed.append("advertiser")
    assert admin.email == f"{CORRELATION_ID}-admin@{IDENTITY_DOMAIN}"
    completed.append("admin")

    zone_id = asyncio.run(_add_abuja_zone(db_sessionmaker, campaign.id, advertiser.id))
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    source = db_client.post(
        "/api/v1/advertiser/retargeting-sources",
        headers=advertiser_headers | {"Idempotency-Key": f"{CORRELATION_ID}-source"},
        json=source_payload(datetime.now(UTC) + timedelta(days=365)),
    )
    assert source.status_code == 201, source.text
    link = db_client.post(
        "/api/v1/advertiser/retargeting-source-links",
        headers=advertiser_headers | {"Idempotency-Key": f"{CORRELATION_ID}-link"},
        json={
            "source_id": source.json()["id"],
            "campaign_id": str(campaign.id),
            "zone_id": str(zone_id),
            "start_at": DAY_1.isoformat(),
            "end_at": (DAY_1 + timedelta(days=1)).isoformat(),
        },
    )
    assert link.status_code == 201, link.text

    browser_receipt = _run_pwa_proof()
    assert browser_receipt["correlation_id"] == CORRELATION_ID
    assert browser_receipt["synthetic_ping_batches"] == 1
    assert browser_receipt["live_gps_claims"] == 0
    completed.extend(("PWA", "synthetic GPS"))

    payload = issue_payload(campaign.id, uuid5(campaign.id, CORRELATION_ID))
    payload["mode"] = "roi_enabled"
    payload["roi"] = {
        "attributed_revenue": "2400.00",
        "approved_cost_basis": "1200.00",
        "currency": "NGN",
        "conversion_provenance": f"SYNTHETIC_TEST_ONLY:{CORRELATION_ID}",
        "revenue_provenance": f"SYNTHETIC_TEST_ONLY:{CORRELATION_ID}",
        "reporting_cutoff": (DAY_1 + timedelta(days=1)).isoformat(),
        "synthetic": True,
        "method": {
            "revision": "synthetic-roi-v1",
            "approval_reference": "SYNTHETIC_TEST_ONLY",
            "attribution_rule": "Synthetic conversion belongs to the fixture campaign.",
            "attribution_window": "Synthetic one-day fixture window.",
            "cost_basis": "Frozen synthetic campaign cost in NGN.",
            "exclusions": "No synthetic exclusions.",
            "corrections": "Reissue on changed synthetic input.",
            "late_data": "Late synthetic data requires reissue.",
        },
    }
    run = db_client.post(
        "/api/v1/admin/measurement-runs",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json=payload,
    )
    assert run.status_code == 201, run.text
    completed.append("measurement")

    report = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/report",
        params={
            "start_at": DAY_1.isoformat(),
            "end_at": (DAY_1 + timedelta(days=1)).isoformat(),
        },
        headers=advertiser_headers,
    )
    assert report.status_code == 200, report.text
    assert report.json()["measurement_result"]["title"] == "Campaign Performance Analysis"
    completed.append("Campaign Performance Analysis")
    assert report.json()["measurement_result"]["roi"]["ratio"] == "1"
    completed.append("qualified synthetic conditional ROI")

    outsider = create_test_user(
        db_sessionmaker,
        email=f"{CORRELATION_ID}-outsider@{IDENTITY_DOMAIN}",
        role=UserRole.ADVERTISER,
    )
    create_test_organization(
        db_sessionmaker,
        name=f"Synthetic outsider · {CORRELATION_ID}",
        billing_email=f"{CORRELATION_ID}-outsider-billing@{IDENTITY_DOMAIN}",
        owner_user_id=outsider.id,
    )
    isolated = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/report",
        params={
            "start_at": DAY_1.isoformat(),
            "end_at": (DAY_1 + timedelta(days=1)).isoformat(),
        },
        headers=auth_headers(db_client, outsider.email, PASSWORD),
    )
    assert isolated.status_code == 404

    run_id = UUID(run.json()["id"])
    segment_id = asyncio.run(
        _materialize_segment(
            db_sessionmaker,
            settings,
            link_id=UUID(link.json()["id"]),
            run_id=run_id,
        )
    )
    fake_activation = FakeAdPlatformAdapter()
    db_client.app.dependency_overrides[get_ad_platform_adapter] = lambda: fake_activation
    activation_approval = db_client.post(
        f"/api/v1/admin/exposure-segments/{segment_id}/delivery-approvals",
        headers=auth_headers(db_client, admin.email, PASSWORD)
        | {"Idempotency-Key": f"{CORRELATION_ID}-activation-approval"},
        json={
            "operation": "ad_platform_activation",
            "purpose_code": "aggregate_contextual_activation",
            "provider": fake_activation.name,
            "provider_account_reference": "synthetic-test-account",
            "budget_ceiling": "0.00",
            "legal_approval_reference": f"synthetic-test-{CORRELATION_ID}",
            "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert activation_approval.status_code == 201, activation_approval.text
    approval_id = activation_approval.json()["id"]
    activated = db_client.post(
        f"/api/v1/admin/exposure-segments/{segment_id}/activations",
        headers=auth_headers(db_client, admin.email, PASSWORD)
        | {"Idempotency-Key": f"{CORRELATION_ID}-activation"},
        json={"approval_id": approval_id},
    )
    assert activated.status_code == 201, activated.text
    assert activated.json()["synthetic"] is True
    assert len(fake_activation.calls) == 1
    completed.append("aggregate contextual activation")

    class TrapLiveAdapter:
        name = "unapproved-live-adapter"
        enabled = True
        synthetic = False

        def __init__(self) -> None:
            self.calls = 0

        async def activate(self, request):
            self.calls += 1
            raise AssertionError(f"live adapter received {request}")

    live_activation = TrapLiveAdapter()
    db_client.app.dependency_overrides[get_ad_platform_adapter] = lambda: live_activation
    blocked_activation = db_client.post(
        f"/api/v1/admin/exposure-segments/{segment_id}/activations",
        headers=auth_headers(db_client, admin.email, PASSWORD)
        | {"Idempotency-Key": f"{CORRELATION_ID}-live-activation"},
        json={"approval_id": approval_id},
    )
    assert blocked_activation.status_code == 503
    assert blocked_activation.json()["error"]["code"] == "AD_PLATFORM_LIVE_ACTIVATION_BLOCKED"
    assert live_activation.calls == 0
    db_client.app.dependency_overrides.pop(get_ad_platform_adapter, None)

    checker = create_test_user(
        db_sessionmaker,
        email=f"{CORRELATION_ID}-checker@{IDENTITY_DOMAIN}",
        role=UserRole.ADMIN,
    )
    batch_id, instruction_fingerprint = asyncio.run(
        _freeze_payout_instruction(
            db_sessionmaker,
            campaign_id=campaign.id,
            admin=admin,
            checker=checker,
        )
    )
    assert len(instruction_fingerprint) == 64
    fake_disbursement = FakeDisbursementAdapter()
    assert fake_disbursement.calls == []
    completed.append("payout instruction")

    before = asyncio.run(
        _receipt(
            db_sessionmaker,
            campaign_id=campaign.id,
            run_id=run_id,
            batch_id=batch_id,
            fake_activation_calls=len(fake_activation.calls),
            live_activation_calls=live_activation.calls,
            disbursement_provider_calls=len(fake_disbursement.calls),
            synthetic_ping_batches=int(browser_receipt["synthetic_ping_batches"]),
            live_gps_claims=int(browser_receipt["live_gps_claims"]),
        )
    )
    assert before.report_issuance_count == before.report_artifact_count == 0
    assert len(fake_disbursement.calls) == before.disbursement_provider_calls == 0
    assert before.live_gps_claims == 0

    snapshot = evaluate_pilot_gates.parse_authority(
        *(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "docs/progress.md",
                ROOT / "docs/architecture.md",
                ROOT / "docs/decisions-log.md",
            )
        )
    )
    assert evaluate_pilot_gates.evaluate_gates(snapshot, {}) == EXPECTED_BLOCKERS
    forged = dict(os.environ)
    forged.update(
        {
            "PRIVACY_DISCLOSURE_LIVE_AUTHORIZED": "true",
            "MEASUREMENT_LIVE_ISSUANCE_AUTHORIZED": "true",
            "INVOICE_ISSUER_EXTERNAL_INPUT_REFERENCE": "fabricated-runtime-approval",
        }
    )
    with pytest.raises(evaluate_pilot_gates.ContradictionError):
        evaluate_pilot_gates.evaluate_gates(snapshot, forged)
    assert evaluate_pilot_gates.evaluate_gates(snapshot, {}) == EXPECTED_BLOCKERS

    after = asyncio.run(
        _receipt(
            db_sessionmaker,
            campaign_id=campaign.id,
            run_id=run_id,
            batch_id=batch_id,
            fake_activation_calls=len(fake_activation.calls),
            live_activation_calls=live_activation.calls,
            disbursement_provider_calls=len(fake_disbursement.calls),
            synthetic_ping_batches=int(browser_receipt["synthetic_ping_batches"]),
            live_gps_claims=int(browser_receipt["live_gps_claims"]),
        )
    )
    assert asdict(after) == asdict(before)
    assert fake_disbursement.calls == []
    completed.append("incident/recovery")
    assert tuple(completed) == STAGES

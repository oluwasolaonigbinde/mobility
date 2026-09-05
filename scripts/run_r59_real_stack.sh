#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

export R59_PROJECT="${R59_PROJECT:-cardvert-r59-${GITHUB_RUN_ID:-local}-$(date +%s)-$$}"
if [[ ! "$R59_PROJECT" =~ ^cardvert-r59-[a-z0-9-]+$ ]]; then
  echo "R59 project must match ^cardvert-r59-[a-z0-9-]+$" >&2
  exit 2
fi
if docker compose ls --all --format json | grep -Eq "\"Name\"[[:space:]]*:[[:space:]]*\"${R59_PROJECT}\""; then
  echo "R59 refuses to reuse existing Compose project $R59_PROJECT" >&2
  exit 2
fi

export R59_GIT_SHA="$(git rev-parse HEAD)"
export R59_API_PORT="${R59_API_PORT:-48159}"
export R59_FRONTEND_PORT="${R59_FRONTEND_PORT:-34159}"
export PAYOUT_CRYPTO_KEYRING_B64='{"1":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="}'
export R59_ARTIFACT_DIR="$repo_root/frontend/test-results/r59-real-stack"
mkdir -p "$R59_ARTIFACT_DIR"

compose=(docker compose -p "$R59_PROJECT" --profile full -f docker-compose.yml -f frontend/e2e/support/docker-compose.r59.yml)

cleanup() {
  local original_status=$?
  local down_status=0
  trap - EXIT INT TERM
  set +e
  cd "$repo_root"
  mkdir -p "$R59_ARTIFACT_DIR"
  "${compose[@]}" ps --all >"$R59_ARTIFACT_DIR/compose-ps.txt" 2>&1
  "${compose[@]}" logs --no-color api worker frontend >"$R59_ARTIFACT_DIR/stack.log" 2>&1
  "${compose[@]}" down -v --remove-orphans || down_status=$?
  if (( original_status == 0 && down_status != 0 )); then
    echo "R59 exact-project teardown failed" >&2
    exit "$down_status"
  fi
  exit "$original_status"
}
trap cleanup EXIT INT TERM

wait_for_postgres() {
  for attempt in $(seq 1 60); do
    if "${compose[@]}" exec -T db pg_isready -h 127.0.0.1 -U mobility -d mobility >/dev/null; then
      return 0
    fi
    if [[ "$attempt" == "60" ]]; then
      echo "PostGIS did not become ready" >&2
      return 1
    fi
    sleep 2
  done
}

wait_for_url() {
  local url=$1
  local label=$2
  for attempt in $(seq 1 90); do
    if curl --fail --silent --show-error "$url" >/dev/null; then
      return 0
    fi
    if [[ "$attempt" == "90" ]]; then
      echo "$label did not become ready" >&2
      return 1
    fi
    sleep 2
  done
}

wait_for_local_dependencies() {
  for attempt in $(seq 1 90); do
    if "${compose[@]}" exec -T api python - <<'PY' >/dev/null 2>&1
import socket
from urllib.request import urlopen

for host, port in (("redis", 6379), ("clamav", 3310), ("mailpit", 1025)):
    with socket.create_connection((host, port), timeout=2):
        pass
with urlopen("http://minio:9000/minio/health/live", timeout=2) as response:
    if response.status != 200:
        raise RuntimeError("MinIO health check failed")
PY
    then
      return 0
    fi
    if [[ "$attempt" == "90" ]]; then
      echo "Redis, MinIO, ClamAV, or Mailpit did not become ready" >&2
      return 1
    fi
    sleep 2
  done
}

services=(db redis minio minio-init clamav mailpit api frontend)
if [[ "${R59_WITHHOLD_WORKER:-0}" != "1" ]]; then
  services+=(worker)
fi
"${compose[@]}" up -d --build "${services[@]}"
wait_for_postgres
wait_for_url "http://127.0.0.1:${R59_API_PORT}/health" API
wait_for_local_dependencies
"${compose[@]}" exec -T api alembic upgrade head
"${compose[@]}" exec -T api python -m app.seeds.demo

# Local-only deterministic readiness layered over the unmodified demo seed.
# It creates the same immutable authority rows production services require; it
# is neither a product bypass nor a change to shared seed semantics.
"${compose[@]}" exec -T api python - <<'PY'
import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.db.session import get_engine
from app.models.campaign import Campaign
from app.models.campaign_assignment import CampaignActivationEvent, CampaignActivationEventType, CampaignAssignment
from app.models.driver import DriverProfile
from app.models.installation_evidence import DisplayProof, DisplayProofChallenge, InstallationEvidencePhoto, InstallationEvidenceStatus, InstallationEvidenceSubmission
from app.models.kyc import DriverKycSubmission, VehicleEvidenceSubmission
from app.models.payee import Payee, PayeeBankAccount, PayeeBankAccountVersion, PayeeVersion
from app.models.payout import AssignmentRuleBinding, CampaignPayoutRule, CampaignPayoutRuleRevision
from app.models.stored_file import FilePurpose, FileScanStatus, FileUploadIntent, StoredFile, UploadIntentStatus
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.billing import AcceptanceMethod, PaymentClass, QuoteRequestSource, accept_quotation_revision, record_approved_credit_authorization, record_production_start, record_quotation_revision, request_custom_quote, reserve_assignment_liability
from app.services.campaign_assignments import resolved_eligibility_snapshot


async def main():
    settings = get_settings()
    maker = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with maker() as session:
        driver = await session.scalar(select(User).where(User.email == "driver@demo.mobility.local"))
        admin = await session.scalar(select(User).where(User.email == "admin@demo.mobility.local"))
        advertiser = await session.scalar(select(User).where(User.email == "advertiser@demo.mobility.local"))
        assert driver and admin and advertiser
        profile = await session.scalar(select(DriverProfile).where(DriverProfile.user_id == driver.id))
        assert profile
        assignment = await session.scalar(
            select(CampaignAssignment)
            .where(CampaignAssignment.driver_profile_id == profile.id, CampaignAssignment.status == "active")
            .order_by(CampaignAssignment.created_at)
        )
        assert assignment
        campaign = await session.get(Campaign, assignment.campaign_id)
        vehicle = await session.get(Vehicle, assignment.vehicle_id)
        assert campaign and vehicle and campaign.start_at and campaign.end_at
        now = datetime.now(UTC)

        payee = Payee(tenant_id=driver.id, payee_type="driver", subject_id=profile.id, created_by_user_id=admin.id)
        session.add(payee)
        await session.flush()
        payee_version = PayeeVersion(payee_id=payee.id, version=1, payee_type="driver", subject_id=profile.id, created_by_user_id=admin.id)
        bank = PayeeBankAccount(payee_id=payee.id, created_by_user_id=admin.id)
        session.add_all([payee_version, bank])
        await session.flush()
        bank_version = PayeeBankAccountVersion(
            bank_account_id=bank.id,
            payee_version_id=payee_version.id,
            version=1,
            encrypted_details={"synthetic": True},
            encryption_algorithm="AES-256-GCM",
            encryption_key_version=1,
            verification_reference_sha256="a" * 64,
            verified_at=now,
            verified_by_user_id=admin.id,
        )
        session.add(bank_version)
        await session.flush()
        session.add(
            DriverKycSubmission(
                driver_profile_id=profile.id,
                nin_record_id=uuid4(),
                version=1,
                client_request_id=uuid4(),
                status="approved",
                encrypted_nin={"synthetic": True},
                encryption_algorithm="AES-256-GCM",
                encryption_key_version=1,
                nin_last_four="0000",
                bank_account_version_id=bank_version.id,
                created_by_user_id=driver.id,
            )
        )
        session.add(
            VehicleEvidenceSubmission(
                vehicle_id=vehicle.id,
                version=1,
                client_request_id=uuid4(),
                status="approved",
                snapshot_trusted=True,
                plate_number_snapshot=vehicle.plate_number,
                plate_number_normalized_snapshot=vehicle.plate_number_normalized,
                plate_country_code_snapshot=vehicle.plate_country_code,
                vehicle_type_snapshot=vehicle.vehicle_type,
                make_snapshot=vehicle.make,
                model_snapshot=vehicle.model,
                year_snapshot=vehicle.year,
                color_snapshot=vehicle.color,
                created_by_user_id=driver.id,
            )
        )

        async def managed_image(label):
            file_id = uuid4()
            intent = FileUploadIntent(
                subject_user_id=driver.id,
                uploader_user_id=driver.id,
                client_request_id=uuid4(),
                request_fingerprint="b" * 64,
                purpose=FilePurpose.INSTALLATION_EVIDENCE.value,
                original_filename=f"{label}.png",
                declared_content_type="image/png",
                declared_size_bytes=128,
                declared_sha256="c" * 64,
                object_key=f"r59/{file_id}",
                expires_at=now + timedelta(hours=1),
                status=UploadIntentStatus.CONFIRMED.value,
            )
            session.add(intent)
            await session.flush()
            stored = StoredFile(
                id=file_id,
                upload_intent_id=intent.id,
                subject_user_id=driver.id,
                uploader_user_id=driver.id,
                purpose=FilePurpose.INSTALLATION_EVIDENCE.value,
                original_filename=f"{label}.png",
                storage_key=f"r59/{file_id}",
                content_type="image/png",
                size_bytes=128,
                checksum_sha256="c" * 64,
                scan_status=FileScanStatus.CLEAN.value,
                actual_content_type="image/png",
                scan_attempts=1,
                scanned_at=now,
                created_at=now,
            )
            session.add(stored)
            await session.flush()
            return stored

        installation_file = await managed_image("installation")
        proof_file = await managed_image("display-proof")
        device_id = uuid4()
        evidence = InstallationEvidenceSubmission(
            assignment_id=assignment.id,
            campaign_id=campaign.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            submitted_by_user_id=driver.id,
            reviewed_by_user_id=admin.id,
            revision=1,
            client_request_id=uuid4(),
            request_fingerprint="d" * 64,
            device_id=device_id,
            captured_at=now,
            required_views=["front"],
            status=InstallationEvidenceStatus.APPROVED.value,
            reviewed_at=now,
            approved_until=now + timedelta(hours=24),
            evidence_metadata={"r59_synthetic": True},
            submitted_at=now,
        )
        session.add(evidence)
        await session.flush()
        session.add(InstallationEvidencePhoto(submission_id=evidence.id, view_code="front", stored_file_id=installation_file.id))
        challenge = DisplayProofChallenge(
            assignment_id=assignment.id,
            evidence_submission_id=evidence.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            device_id=device_id,
            nonce_sha256="e" * 64,
            expires_at=now + timedelta(minutes=5),
            consumed_at=now,
            created_at=now,
        )
        session.add(challenge)
        await session.flush()
        proof = DisplayProof(
            challenge_id=challenge.id,
            assignment_id=assignment.id,
            evidence_submission_id=evidence.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            device_id=device_id,
            stored_file_id=proof_file.id,
            verified_at=now,
            valid_until=now + timedelta(hours=1),
            proof_metadata={"r59_synthetic": True},
        )
        session.add(proof)

        rule = await session.scalar(select(CampaignPayoutRule).where(CampaignPayoutRule.campaign_id == campaign.id, CampaignPayoutRule.status == "active"))
        assert rule
        revision = CampaignPayoutRuleRevision(
            campaign_id=campaign.id,
            payout_rule_id=rule.id,
            revision_number=1,
            effective_from=campaign.start_at,
            hourly_rate_naira=Decimal("1200.00"),
            premium_hourly_rate_naira=Decimal("1500.00"),
            daily_payable_hours_cap=Decimal("8.00"),
            currency="NGN",
            eligibility_params={},
            formula_version="payout_v3",
            reason="R59 local synthetic release authority",
            created_by_user_id=admin.id,
        )
        session.add(revision)
        await session.flush()
        empty_hash = hashlib.sha256(b"").hexdigest()
        binding = AssignmentRuleBinding(
            assignment_id=assignment.id,
            revision_id=revision.id,
            hourly_rate_naira=revision.hourly_rate_naira,
            premium_hourly_rate_naira=revision.premium_hourly_rate_naira,
            daily_payable_hours_cap=revision.daily_payable_hours_cap,
            currency="NGN",
            eligibility_params={},
            resolved_eligibility_params=resolved_eligibility_snapshot(settings, {}),
            formula_version="payout_v3",
            premium_zone_ids=[],
            premium_zone_geometry_hash=empty_hash,
            premium_zone_geometry_wkts=[],
            exclusion_zone_ids=[],
            exclusion_zone_geometry_hash=empty_hash,
            exclusion_zone_geometry_wkts=[],
            stationary_policy_marker="stationary-rd-v1",
            campaign_window_start_at=campaign.start_at,
            campaign_window_end_at=campaign.end_at,
            campaign_window_frozen=True,
            offer_terms_sha256=assignment.offer_terms_sha256,
            bound_at=now,
        )
        session.add(binding)
        await session.flush()

        quote_request = await request_custom_quote(
            session,
            campaign_id=campaign.id,
            actor_user_id=advertiser.id,
            source=QuoteRequestSource.IN_PLATFORM,
            request_details={"r59_synthetic": True},
        )
        quote = await record_quotation_revision(
            session,
            quote_request_id=quote_request.id,
            actor_user_id=admin.id,
            quote_reference=f"R59-{campaign.id}",
            currency="NGN",
            line_items=[{"code": "R59", "description": "R59 synthetic authority", "kind": "media", "amount": "100000000.00"}],
            production_scope={"vehicle_count": 1},
            payment_class=PaymentClass.APPROVED_CORPORATE_CREDIT,
            payment_terms={"r59_synthetic": True},
            tax_rate="0",
        )
        await accept_quotation_revision(
            session,
            quotation_revision_id=quote.id,
            actor_user_id=advertiser.id,
            acceptance_method=AcceptanceMethod.IN_PLATFORM,
        )
        await record_approved_credit_authorization(
            session,
            campaign_id=campaign.id,
            actor_user_id=admin.id,
            credit_limit="100000000.00",
            max_driver_liability="100000000.00",
            due_at=now + timedelta(days=30),
            approved_by_user_id=admin.id,
            credit_terms={"r59_synthetic": True},
            reason="R59 local synthetic release authority",
        )
        await record_production_start(session, campaign_id=campaign.id, actor_user_id=admin.id)
        reservation = await reserve_assignment_liability(session, assignment_id=assignment.id, actor_user_id=admin.id)
        assert reservation.status == "reserved"

        activated_at = assignment.activated_at
        assert activated_at
        if activated_at.tzinfo is None:
            activated_at = activated_at.replace(tzinfo=UTC)
        else:
            activated_at = activated_at.astimezone(UTC)
        snapshot = {
            "version": "assignment-activation-v1",
            "assignment_id": str(assignment.id),
            "campaign_id": str(campaign.id),
            "driver_profile_id": str(profile.id),
            "vehicle_id": str(vehicle.id),
            "offer_terms_sha256": assignment.offer_terms_sha256,
            "activated_at": activated_at.isoformat(),
            "r59_synthetic": True,
        }
        canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        session.add(
            CampaignActivationEvent(
                assignment_id=assignment.id,
                actor_user_id=admin.id,
                event_type=CampaignActivationEventType.ACTIVATED.value,
                previous_status="accepted",
                new_status="active",
                occurred_at=now,
                event_metadata={
                    "activation_snapshot": snapshot,
                    "activation_snapshot_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
                    "r59_synthetic": True,
                },
                offer_terms_sha256=assignment.offer_terms_sha256,
            )
        )
        await session.commit()
        print(json.dumps({"assignment_id": str(assignment.id), "campaign_id": str(campaign.id), "fixture": "r59-ready"}, sort_keys=True))


asyncio.run(main())
PY

preflight_count="$("${compose[@]}" exec -T db psql -XAt -v ON_ERROR_STOP=1 -U mobility -d mobility -c \
  "SELECT count(*) FROM campaign_assignments a JOIN driver_profiles d ON d.id=a.driver_profile_id JOIN users u ON u.id=d.user_id JOIN assignment_rule_bindings b ON b.assignment_id=a.id JOIN campaign_liability_reservations r ON r.assignment_id=a.id JOIN display_proofs p ON p.assignment_id=a.id WHERE u.email='driver@demo.mobility.local' AND a.status='active' AND r.status='reserved' AND p.valid_until > now();")"
if [[ "$preflight_count" != "1" ]]; then
  echo "R59 readiness preflight failed closed" >&2
  exit 1
fi

export R59_IMAGE_IDS="$("${compose[@]}" images -q api worker frontend | sort -u | paste -sd, -)"
leased_paths=(
  .github/workflows/ci.yml
  frontend/playwright.config.ts
  frontend/e2e/r59-real-stack.spec.ts
  frontend/e2e/support/r59-stack.ts
  frontend/e2e/support/docker-compose.r59.yml
  scripts/run_r59_real_stack.sh
  tests/test_r59_real_stack_contract.py
  docs/pkg-07-w4-01d-release-rehearsal.md
)
export R59_LEASED_FILES_DIGEST="$(git hash-object "${leased_paths[@]}" | git hash-object --stdin)"
export R59_REAL_STACK=1
export PLAYWRIGHT_BASE_URL="http://127.0.0.1:${R59_FRONTEND_PORT}"

wait_for_url "$PLAYWRIGHT_BASE_URL/login" frontend
cd frontend
if command -v xvfb-run >/dev/null 2>&1; then
  xvfb-run -a npx playwright test e2e/r59-real-stack.spec.ts --project=r59-chromium --workers=1 --retries=0
else
  npx playwright test e2e/r59-real-stack.spec.ts --project=r59-chromium --workers=1 --retries=0
fi

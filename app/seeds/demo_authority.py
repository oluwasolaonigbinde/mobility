"""Explicit local-only demo facts consumed by the unchanged production Start guards.

No provider object, bank verification, real credit or physical installation is
asserted by these synthetic fixtures. Existing immutable facts survive reruns.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.crypto import AssociatedData, EnvelopeCryptoProvider
from app.core.config import Settings
from app.models.billing import ProductionStart
from app.models.campaign_assignment import (
    CampaignActivationEvent,
    CampaignActivationEventType,
)
from app.models.installation_evidence import (
    DisplayProof,
    DisplayProofChallenge,
    InstallationEvidencePhoto,
    InstallationEvidenceStatus,
    InstallationEvidenceSubmission,
)
from app.models.kyc import DriverKycSubmission, VehicleEvidenceSubmission
from app.models.payee import Payee, PayeeBankAccount, PayeeBankAccountVersion, PayeeVersion
from app.models.payout import AssignmentRuleBinding, CampaignPayoutRule, CampaignPayoutRuleRevision
from app.models.stored_file import (
    FilePurpose,
    FileScanStatus,
    FileUploadIntent,
    StoredFile,
    UploadIntentStatus,
)
from app.services.billing import (
    AcceptanceMethod,
    PaymentClass,
    QuoteRequestSource,
    accept_quotation_revision,
    record_approved_credit_authorization,
    record_production_start,
    record_quotation_revision,
    request_custom_quote,
    reserve_assignment_liability,
)
from app.services.campaign_assignments import (
    ensure_current_activation_snapshot,
    resolved_eligibility_snapshot,
)

if TYPE_CHECKING:
    from app.seeds.demo import DemoGraph


async def ensure_demo_start_authority(
    session: AsyncSession, *, graph: "DemoGraph", settings: Settings
) -> None:
    from app.seeds.demo import ensure_seed_allowed

    ensure_seed_allowed(
        settings.model_copy(
            update={"database_url": settings.database_url or str(session.get_bind().url)}
        )
    )
    driver, admin, advertiser = graph.driver, graph.admin, graph.advertiser
    profile, assignment, campaign, vehicle = (
        graph.driver_profile,
        graph.assignment,
        graph.campaign,
        graph.vehicle,
    )
    now = datetime.now(UTC)

    if not await session.scalar(
        select(DriverKycSubmission.id).where(DriverKycSubmission.driver_profile_id == profile.id)
    ):
        payee = Payee(
            tenant_id=driver.id,
            payee_type="driver",
            subject_id=profile.id,
            created_by_user_id=admin.id,
        )
        session.add(payee)
        await session.flush()
        payee_version = PayeeVersion(
            payee_id=payee.id,
            version=1,
            payee_type="driver",
            subject_id=profile.id,
            created_by_user_id=admin.id,
        )
        bank = PayeeBankAccount(payee_id=payee.id, created_by_user_id=admin.id)
        session.add_all([payee_version, bank])
        await session.flush()
        crypto = EnvelopeCryptoProvider(
            keys=settings.payout_crypto_keys, active_key_version=settings.payout_crypto_key_version
        )
        bank_envelope = crypto.encrypt(
            json.dumps(
                {
                    "account_name": "SYNTHETIC DEMO ONLY",
                    "account_number": "0000000000",
                    "bank_code": "000",
                }
            ).encode(),
            AssociatedData(
                tenant_id=driver.id, record_id=bank.id, field_name="bank_account.details"
            ),
        )
        nin_record_id = uuid4()
        nin_envelope = crypto.encrypt(
            b"00000000000",
            AssociatedData(
                tenant_id=driver.id, record_id=nin_record_id, field_name="driver_kyc.nin"
            ),
        )
        bank_version = PayeeBankAccountVersion(
            bank_account_id=bank.id,
            payee_version_id=payee_version.id,
            version=1,
            encrypted_details=bank_envelope.to_mapping(),
            encryption_algorithm="AES-256-GCM",
            encryption_key_version=bank_envelope.key_version,
            verification_reference_sha256="a" * 64,
            verified_at=now,
            verified_by_user_id=admin.id,
        )
        session.add(bank_version)
        await session.flush()
        session.add(
            DriverKycSubmission(
                driver_profile_id=profile.id,
                nin_record_id=nin_record_id,
                version=1,
                client_request_id=uuid4(),
                status="approved",
                encrypted_nin=nin_envelope.to_mapping(),
                encryption_algorithm="AES-256-GCM",
                encryption_key_version=nin_envelope.key_version,
                nin_last_four="0000",
                bank_account_version_id=bank_version.id,
                created_by_user_id=driver.id,
            )
        )
    if not await session.scalar(
        select(VehicleEvidenceSubmission.id).where(
            VehicleEvidenceSubmission.vehicle_id == vehicle.id
        )
    ):
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
            object_key=f"demo-start/{file_id}",
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
            storage_key=f"demo-start/{file_id}",
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

    proof = await session.scalar(
        select(DisplayProof)
        .where(DisplayProof.assignment_id == assignment.id)
        .order_by(DisplayProof.verified_at.desc())
        .limit(1)
    )
    if proof is None or proof.valid_until.replace(tzinfo=UTC) <= now:
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
            revision=(
                await session.scalar(
                    select(func.max(InstallationEvidenceSubmission.revision)).where(
                        InstallationEvidenceSubmission.assignment_id == assignment.id
                    )
                )
                or 0
            )
            + 1,
            client_request_id=uuid4(),
            request_fingerprint="d" * 64,
            device_id=device_id,
            captured_at=now,
            required_views=list(settings.installation_evidence_views),
            status=InstallationEvidenceStatus.APPROVED.value,
            reviewed_at=now,
            approved_until=now
            + timedelta(hours=settings.installation_evidence_validity_hours or 24),
            evidence_metadata={"demo_synthetic": True},
            submitted_at=now,
        )
        session.add(evidence)
        await session.flush()
        for index, view in enumerate(settings.installation_evidence_views or ("front",)):
            image_file = installation_file if index == 0 else await managed_image(view)
            session.add(
                InstallationEvidencePhoto(
                    submission_id=evidence.id, view_code=view, stored_file_id=image_file.id
                )
            )
        challenge = DisplayProofChallenge(
            assignment_id=assignment.id,
            evidence_submission_id=evidence.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            device_id=device_id,
            nonce_sha256=hashlib.sha256(uuid4().bytes).hexdigest(),
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
            valid_until=now + timedelta(seconds=settings.display_proof_validity_seconds or 3600),
            proof_metadata={"demo_synthetic": True},
        )
        session.add(proof)

    binding = await session.scalar(
        select(AssignmentRuleBinding).where(AssignmentRuleBinding.assignment_id == assignment.id)
    )
    if binding is None:
        rule = await session.scalar(
            select(CampaignPayoutRule).where(
                CampaignPayoutRule.campaign_id == campaign.id, CampaignPayoutRule.status == "active"
            )
        )
        assert rule
        revision = CampaignPayoutRuleRevision(
            campaign_id=campaign.id,
            payout_rule_id=rule.id,
            revision_number=(
                await session.scalar(
                    select(func.max(CampaignPayoutRuleRevision.revision_number)).where(
                        CampaignPayoutRuleRevision.campaign_id == campaign.id
                    )
                )
                or 0
            )
            + 1,
            effective_from=campaign.start_at,
            hourly_rate_naira=Decimal("1200.00"),
            premium_hourly_rate_naira=Decimal("1500.00"),
            daily_payable_hours_cap=Decimal("8.00"),
            currency="NGN",
            eligibility_params={},
            formula_version="payout_v3",
            reason="Local demo authority; no real payment or provider evidence",
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

    if not await session.scalar(
        select(ProductionStart.id).where(ProductionStart.campaign_id == campaign.id)
    ):
        quote_request = await request_custom_quote(
            session,
            campaign_id=campaign.id,
            actor_user_id=advertiser.id,
            source=QuoteRequestSource.IN_PLATFORM,
            request_details={"demo_synthetic": True},
        )
        quote = await record_quotation_revision(
            session,
            quote_request_id=quote_request.id,
            actor_user_id=admin.id,
            quote_reference=f"DEMO-{campaign.id}",
            currency="NGN",
            line_items=[
                {
                    "code": "DEMO",
                    "description": "Local synthetic demo authority",
                    "kind": "media",
                    "amount": "100000000.00",
                }
            ],
            production_scope={"vehicle_count": 1},
            payment_class=PaymentClass.APPROVED_CORPORATE_CREDIT,
            payment_terms={"demo_synthetic": True},
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
            credit_terms={"demo_synthetic": True},
            reason="Local demo authority; no real payment or provider evidence",
        )
        await record_production_start(session, campaign_id=campaign.id, actor_user_id=admin.id)
    reservation = await reserve_assignment_liability(
        session, assignment_id=assignment.id, actor_user_id=admin.id
    )
    assert reservation.status == "reserved"

    activation = await session.scalar(
        select(CampaignActivationEvent)
        .where(
            CampaignActivationEvent.assignment_id == assignment.id,
            CampaignActivationEvent.event_type == CampaignActivationEventType.ACTIVATED.value,
        )
        .order_by(CampaignActivationEvent.occurred_at.desc(), CampaignActivationEvent.id.desc())
        .limit(1)
    )
    if activation is None or "activation_snapshot" not in activation.event_metadata:
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
            "demo_synthetic": True,
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
                    "demo_synthetic": True,
                },
                offer_terms_sha256=assignment.offer_terms_sha256,
            )
        )
    await session.flush()
    await ensure_current_activation_snapshot(session, assignment=assignment, lock=True)

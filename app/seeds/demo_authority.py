"""Explicit local-only demo facts consumed by the unchanged production Start guards.

No provider object, bank verification, real credit or physical installation is
asserted by these synthetic fixtures. Existing immutable facts survive reruns.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple, Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.crypto import AssociatedData, EnvelopeCryptoProvider
from app.adapters.scanner import MalwareScanVerdict, build_malware_scanner
from app.adapters.storage import build_storage_provider
from app.core.config import Settings
from app.models.billing import ProductionStart
from app.models.campaign import Campaign, CampaignCreative
from app.models.campaign_assignment import (
    CampaignActivationEvent,
    CampaignActivationEventType,
    CampaignAssignment,
)
from app.models.driver import DriverProfile
from app.models.installation_evidence import (
    DisplayProof,
    DisplayProofChallenge,
    InstallationEvidencePhoto,
    InstallationEvidenceStatus,
    InstallationEvidenceSubmission,
)
from app.models.kyc import (
    DriverKycSubmission,
    KycReviewReason,
    KycSubmissionStatus,
    VehicleReviewReason,
)
from app.models.payee import Payee, PayeeBankAccount, PayeeBankAccountVersion, PayeeVersion
from app.models.payout import AssignmentRuleBinding, CampaignPayoutRule, CampaignPayoutRuleRevision
from app.models.stored_file import (
    FilePurpose,
    FileUploadIntent,
    StoredFile,
)
from app.models.user import User
from app.models.vehicle import Vehicle, VehicleType
from app.services.billing import (
    reserve_assignment_liability,
)
from app.services.campaign_assignments import (
    build_offer_terms,
    create_rule_binding_for_accept,
    ensure_current_activation_snapshot,
)


async def managed_seed_image(
    session, *, settings, subject, label, purpose, organization_id=None, identity="", at=None
):
    """Persist the same real image bytes referenced by the private file record."""
    file_id = uuid5(NAMESPACE_URL, f"cardvert-preview:{subject.id}:{purpose}:{identity}:{label}")
    stored = await session.get(StoredFile, file_id)
    if stored is not None:
        return stored
    asset = Path(__file__).with_name("assets") / f"{label.replace('_', '-')}.png"
    data = asset.read_bytes()

    async def chunks():
        yield data

    scan = await build_malware_scanner(settings).scan(chunks())
    if scan.verdict != MalwareScanVerdict.CLEAN:
        raise ValueError("Installation image did not pass malware scanning")
    digest = hashlib.sha256(data).hexdigest()
    key = f"campaign-files/{file_id}.png"
    await build_storage_provider(settings).put(
        object_key=key, content_type="image/png", data=data, checksum_sha256=digest
    )
    now = at or datetime.now(UTC)
    intent = FileUploadIntent(
        subject_user_id=None if organization_id else subject.id,
        uploader_user_id=subject.id,
        organization_id=organization_id,
        client_request_id=file_id,
        request_fingerprint=digest,
        purpose=purpose,
        original_filename=f"{label}.png",
        declared_content_type="image/png",
        declared_size_bytes=len(data),
        declared_sha256=digest,
        object_key=key,
        expires_at=now + timedelta(hours=1),
        status="confirmed",
        created_at=now,
        updated_at=now,
    )
    session.add(intent)
    await session.flush()
    stored = StoredFile(
        id=file_id,
        upload_intent_id=intent.id,
        subject_user_id=None if organization_id else subject.id,
        uploader_user_id=subject.id,
        organization_id=organization_id,
        purpose=purpose,
        original_filename=f"{label}.png",
        storage_key=key,
        content_type="image/png",
        size_bytes=len(data),
        checksum_sha256=digest,
        scan_status="clean",
        actual_content_type="image/png",
        scan_attempts=1,
        scanned_at=now,
        created_at=now,
    )
    session.add(stored)
    await session.flush()
    return stored


async def prepare_daily_offer(
    session, *, campaign, profile, admin, advertiser, settings, offered_at
):
    """Create canonical D43 revisions and accepted offer bindings before calculation."""
    rule = await session.scalar(
        select(CampaignPayoutRule).where(
            CampaignPayoutRule.campaign_id == campaign.id, CampaignPayoutRule.status == "active"
        )
    )
    if rule is None:
        rule = CampaignPayoutRule(
            campaign_id=campaign.id,
            created_by_user_id=admin.id,
            updated_by_user_id=admin.id,
            formula_version="payout_v4",
            status="active",
            currency="NGN",
            rule_metadata={
                "seed_version": campaign.campaign_metadata.get("seed_version", "f7_rich_v1")
            },
        )
        session.add(rule)
        await session.flush()
    revision = await session.scalar(
        select(CampaignPayoutRuleRevision)
        .where(CampaignPayoutRuleRevision.campaign_id == campaign.id)
        .order_by(CampaignPayoutRuleRevision.revision_number.desc())
        .limit(1)
    )
    if revision is None:
        revision = CampaignPayoutRuleRevision(
            campaign_id=campaign.id,
            payout_rule_id=rule.id,
            revision_number=1,
            effective_from=campaign.start_at - timedelta(days=7),
            daily_rate_naira=Decimal("10000.00"),
            daily_target_miles=Decimal("70"),
            shortfall_strategy="proportional",
            minimum_miles=Decimal("0"),
            outside_area_weight=Decimal("0"),
            currency="NGN",
            eligibility_params={},
            formula_version="payout_v4",
            reason="Daily rate agreed for the scheduled routes.",
            created_by_user_id=admin.id,
        )
        session.add(revision)
        await session.flush()
    creative = await session.scalar(
        select(CampaignCreative)
        .where(CampaignCreative.campaign_id == campaign.id)
        .order_by(CampaignCreative.created_at)
        .limit(1)
    )
    assert creative
    if creative.stored_file_id is None:
        stored = await managed_seed_image(
            session,
            settings=settings,
            subject=advertiser,
            label=campaign.name.split(" — ")[0].lower().replace(" ", "-"),
            identity=str(creative.id),
            purpose=FilePurpose.CREATIVE.value,
            organization_id=campaign.organization_id,
            at=offered_at - timedelta(hours=3),
        )
        creative.stored_file_id = stored.id
        creative.asset_url = None
        creative.checksum = stored.checksum_sha256
        creative.status = "draft"
        creative.mime_type = "image/png"
        await session.flush()
        await session.refresh(creative)
        from sqlalchemy import event

        from app.models.audit import AuditEvent
        from app.models.campaign import CreativeReviewEvent, CreativeStatus
        from app.models.user import User
        from app.services.campaigns import decide_creative_review, submit_creative_for_review

        compliance = await session.scalar(
            select(User).where(User.email == "olumide.fashola@terraxmedia.com")
        )
        review_at = offered_at - timedelta(hours=2)

        def record_review_time(seed_session, _flush_context, _instances):
            for row in seed_session.new:
                if isinstance(row, CreativeReviewEvent) and row.creative_id == creative.id:
                    row.created_at = review_at
                elif isinstance(row, AuditEvent) and row.entity_id == str(creative.id):
                    row.created_at = review_at

        event.listen(session.sync_session, "before_flush", record_review_time)
        try:
            await submit_creative_for_review(
                session, user_id=advertiser.id, campaign_id=campaign.id, creative_id=creative.id
            )
            review_at = offered_at - timedelta(hours=1)
            await decide_creative_review(
                session,
                admin_user_id=(compliance or admin).id,
                creative_id=creative.id,
                target_status=CreativeStatus.APPROVED,
            )
        finally:
            event.remove(session.sync_session, "before_flush", record_review_time)
        await session.refresh(creative)

    await session.refresh(campaign)
    terms, digest = await build_offer_terms(
        session,
        campaign=campaign,
        driver_profile=profile,
        now=offered_at,
        creative_id=creative.id,
        settings=settings,
    )
    return terms, digest


async def ensure_daily_terms(
    session, *, campaign, assignment, profile, admin, advertiser, settings
):
    binding = await session.scalar(
        select(AssignmentRuleBinding).where(AssignmentRuleBinding.assignment_id == assignment.id)
    )
    if binding is not None or assignment.accepted_at is None:
        return binding
    return await create_rule_binding_for_accept(
        session,
        assignment=assignment,
        now=assignment.accepted_at,
        campaign=campaign,
        settings=settings,
    )


async def seed_campaign_financials(
    session,
    *,
    campaign,
    admin,
    advertiser,
    funding_fraction=Decimal("1"),
    invoice_status="issued",
    production=True,
    financial_at=None,
    accept_terms=True,
):
    """Historical fictional cash facts, never submitted to a payment provider."""
    from app.models.billing import (
        CampaignFinancialAuthorization,
        CommercialQuotationRevision,
        CommercialQuoteRequest,
        CommercialTerms,
        FinancialAuthorizationAllocation,
        Invoice,
        InvoiceIssuerProfile,
        PaymentReceipt,
        ReceiptAllocation,
        ReceiptLifecycleEvent,
        ReceiptReconciliation,
    )

    if await session.scalar(
        select(CommercialQuoteRequest.id).where(CommercialQuoteRequest.campaign_id == campaign.id)
    ):
        return
    from app.models.organization import AdvertiserOrganization

    organization = await session.get(AdvertiserOrganization, campaign.organization_id)
    at = financial_at or campaign.start_at - timedelta(days=8)
    gross = campaign.budget_amount
    net = (gross / Decimal("1.075")).quantize(Decimal("0.01"))
    tax = gross - net
    lines = [
        {
            "code": "media",
            "description": "Vehicle advertising on the agreed routes",
            "kind": "media",
            "amount": str(net),
        }
    ]
    request = CommercialQuoteRequest(
        campaign_id=campaign.id,
        organization_id=campaign.organization_id,
        source="in_platform",
        request_details={"notes": "Please quote for weekday visibility around the selected areas."},
        requested_by_user_id=advertiser.id,
        requested_at=at,
    )
    session.add(request)
    await session.flush()
    common = dict(
        campaign_id=campaign.id,
        organization_id=campaign.organization_id,
        quote_reference=f"TX-{campaign.id.hex[:8].upper()}",
        currency="NGN",
        line_items=lines,
        production_scope={"vehicle_count": 5},
        production_cost_amount=Decimal("0"),
        payment_class="standard_prepaid",
        payment_terms={"notes": "Payment before printing and installation."},
        standard_production_wait_hours=24,
        net_amount=net,
        tax_rate=Decimal("0.075"),
        tax_amount=tax,
        gross_amount=gross,
    )
    quote = CommercialQuotationRevision(
        quote_request_id=request.id,
        revision_number=1,
        created_by_user_id=admin.id,
        created_at=at + timedelta(hours=1),
        **common,
    )
    session.add(quote)
    await session.flush()
    if not accept_terms:
        return
    terms = CommercialTerms(
        quotation_revision_id=quote.id,
        quotation_revision_number=1,
        acceptance_method="in_platform",
        accepted_by_user_id=advertiser.id,
        recorded_by_user_id=advertiser.id,
        accepted_at=at + timedelta(hours=2),
        created_at=at + timedelta(hours=2),
        **common,
    )
    session.add(terms)
    await session.flush()
    funded_amount = (gross * funding_fraction).quantize(Decimal("0.01"))
    if funded_amount > 0:
        receipt = PaymentReceipt(
            organization_id=campaign.organization_id,
            method="manual_transfer",
            provider="bank_transfer",
            external_transaction_id=f"TRX-{campaign.id.hex[:12].upper()}",
            amount=funded_amount,
            currency="NGN",
            payer_name=organization.name,
            evidence_reference="Transfer advice received by Finance.",
            observed_by_user_id=admin.id,
            observed_at=at + timedelta(hours=3),
        )
        session.add(receipt)
        await session.flush()
        session.add(
            ReceiptReconciliation(
                receipt_id=receipt.id,
                expected_amount=funded_amount,
                expected_currency="NGN",
                matched=True,
                verification_source="manual",
                reconciled_by_user_id=admin.id,
                reconciled_at=at + timedelta(hours=4),
            )
        )
        for i, state in enumerate(("observed", "reconciled", "confirmed")):
            session.add(
                ReceiptLifecycleEvent(
                    receipt_id=receipt.id,
                    status=state,
                    sequence_number=i + 1,
                    actor_user_id=admin.id,
                    reason="Transfer amount matches the accepted quotation."
                    if funding_fraction == 1
                    else "First instalment received; the balance is due before printing.",
                    occurred_at=at + timedelta(hours=3 + i),
                )
            )
        allocation = ReceiptAllocation(
            receipt_id=receipt.id,
            commercial_terms_id=terms.id,
            amount=funded_amount,
            currency="NGN",
            allocation_source="manual",
            allocated_by_user_id=admin.id,
            allocated_at=at + timedelta(hours=6),
        )
        session.add(allocation)
        if production:
            auth = CampaignFinancialAuthorization(
                campaign_id=campaign.id,
                commercial_terms_id=terms.id,
                revision_number=1,
                authority_type="prepaid_cash",
                currency="NGN",
                authorized_amount=gross,
                funded_cash_amount=gross,
                max_driver_liability=gross,
                effective_from=at + timedelta(hours=6),
                created_by_user_id=admin.id,
                reason="Full payment received for the agreed routes.",
                created_at=at + timedelta(hours=6),
            )
            session.add(auth)
            await session.flush()
            session.add(
                FinancialAuthorizationAllocation(
                    authorization_id=auth.id, receipt_allocation_id=allocation.id, amount=gross
                )
            )
            session.add(
                ProductionStart(
                    campaign_id=campaign.id,
                    authorization_id=auth.id,
                    authority_basis="standard_window_elapsed",
                    fully_funded_at=at + timedelta(hours=6),
                    started_by_user_id=admin.id,
                    started_at=at + timedelta(days=2),
                )
            )
    issuer = await session.scalar(
        select(InvoiceIssuerProfile).where(
            InvoiceIssuerProfile.external_input_reference == "cardvert-preview-invoice"
        )
    )
    if issuer is None:
        issuer = InvoiceIssuerProfile(
            legal_name="Terrax Media Company Ltd",
            tax_identification_number="2521515778093",
            company_registration_number="8688553",
            registered_address="73 Lome Crescent, Wuse Zone 7, Abuja",
            country_code="NG",
            invoice_wording="Vehicle advertising",
            numbering_prefix="TXM",
            verification_status="synthetic",
            external_input_reference="cardvert-preview-invoice",
            contact_phone="07074200080",
            contact_email="terraxmediacompany@gmail.com",
            recorded_by_user_id=admin.id,
            recorded_at=at,
        )
        session.add(issuer)
        await session.flush()
    session.add(
        Invoice(
            commercial_terms_id=terms.id,
            campaign_id=campaign.id,
            organization_id=campaign.organization_id,
            issuer_profile_id=issuer.id if invoice_status != "draft" else None,
            invoice_number=f"TXM-{campaign.id.hex[:8].upper()}"
            if invoice_status != "draft"
            else None,
            status=invoice_status,
            customer_snapshot={"name": organization.name},
            issuer_snapshot=None
            if invoice_status == "draft"
            else {
                "legal_name": issuer.legal_name,
                "bank_name": "OPay",
                "bank_account_name": "Terrax Media Company Ltd",
                "bank_account_number": "0000000000",
            },
            line_items=lines,
            currency="NGN",
            net_amount=net,
            tax_rate=Decimal("0.075"),
            tax_amount=tax,
            gross_amount=gross,
            created_by_user_id=admin.id,
            issued_by_user_id=admin.id if invoice_status != "draft" else None,
            issued_at=at + timedelta(hours=2) if invoice_status != "draft" else None,
            created_at=at + timedelta(hours=2),
        )
    )
    await session.flush()


class StartAuthorityGraph(Protocol):
    @property
    def driver(self) -> User: ...

    @property
    def admin(self) -> User: ...

    @property
    def advertiser(self) -> User: ...

    @property
    def driver_profile(self) -> DriverProfile: ...

    @property
    def assignment(self) -> CampaignAssignment: ...

    @property
    def campaign(self) -> Campaign: ...

    @property
    def vehicle(self) -> Vehicle: ...


class SeedStartAuthorityGraph(NamedTuple):
    driver: User
    admin: User
    advertiser: User
    driver_profile: DriverProfile
    assignment: CampaignAssignment
    campaign: Campaign
    vehicle: Vehicle


def require_seed_value[T](value: T | None, label: str) -> T:
    if value is None:
        raise ValueError(f"Expected demo {label} is missing")
    return value


async def ensure_applicant_review(session, *, application, person, stage, staff, settings):
    from app.seeds.history import initial_action_history

    with initial_action_history(session, application.created_at + timedelta(days=1)) as clock:
        await _ensure_applicant_review(
            session,
            application=application,
            person=person,
            stage=stage,
            staff=staff,
            settings=settings,
            clock=clock,
        )


async def _ensure_applicant_review(session, *, application, person, stage, staff, settings, clock):
    from app.schemas.driver_onboarding import (
        PersonPayeeReviewDecisionCreate,
        PersonPayeeSubmissionCreate,
    )
    from app.services.driver_applications import (
        _access_token_value,
        issue_driver_application_access,
    )
    from app.services.driver_onboarding import (
        review_application_person_payee,
        submit_application_person_payee,
    )
    from app.services.kyc import reveal_driver_nin
    from app.services.payees import (
        read_verified_bank_account,
        verify_bank_account_version_for_payout,
    )
    from app.services.stored_files import issue_admin_file_download

    current = await session.scalar(
        select(DriverKycSubmission).where(
            DriverKycSubmission.driver_profile_id == application.driver_profile_id
        )
    )
    if stage == "not_submitted" or current is not None:
        return
    access = await issue_driver_application_access(
        session, application=application, settings=settings
    )
    if access is None:
        raise ValueError("Expected demo applicant access token is missing")
    token = _access_token_value(access, settings)
    crypto = EnvelopeCryptoProvider(
        keys=settings.payout_crypto_keys, active_key_version=settings.payout_crypto_key_version
    )
    clock[0] += timedelta(hours=1)
    files = {}
    for kind in ("driver_license", "driver_photo", "signed_agreement"):
        stored = await managed_seed_image(
            session,
            settings=settings,
            subject=person,
            label=f"{person.full_name.lower().replace(' ', '-')}-{kind.replace('_', '-')}",
            purpose=FilePurpose.DRIVER_KYC.value,
            identity=str(application.id),
            at=clock[0],
        )
        files[kind] = stored.id
    clock[0] += timedelta(hours=1)
    view = await submit_application_person_payee(
        session,
        settings=settings,
        crypto=crypto,
        payload=PersonPayeeSubmissionCreate(
            application_access_token=SecretStr(token),
            client_request_id=uuid5(application.id, "person-payee"),
            nin=SecretStr("00000000000"),
            account_name=SecretStr(person.full_name),
            account_number=SecretStr("0000000000"),
            bank_code=SecretStr("999"),
            driver_license_file_id=files["driver_license"],
            driver_photo_file_id=files["driver_photo"],
            signed_agreement_file_id=files["signed_agreement"],
        ),
    )
    if view.submission is None:
        raise ValueError("Expected demo person/payee submission is missing")
    if stage == "pending_review":
        return
    clock[0] += timedelta(hours=1)
    if stage == "approved":
        await verify_bank_account_version_for_payout(
            session,
            bank_account_version_id=view.submission.bank_account_version_id,
            verification_reference=f"BNK-{application.id.hex.upper()}",
            actor_user_id=staff[0].id,
        )
        await reveal_driver_nin(
            session,
            submission_id=view.submission.id,
            actor_user_id=staff[2].id,
            purpose="person_payee_approval",
            crypto=crypto,
        )
        await read_verified_bank_account(
            session,
            bank_account_version_id=view.submission.bank_account_version_id,
            actor_user_id=staff[2].id,
            purpose="person_payee_approval",
            crypto=crypto,
        )
        for file_id in files.values():
            await issue_admin_file_download(
                session,
                actor_user_id=staff[2].id,
                file_id=file_id,
                access_purpose="kyc_review",
                reason=f"person_payee_approval:{view.submission.id}",
                storage=build_storage_provider(settings),
                settings=settings,
            )
    await review_application_person_payee(
        session,
        application_id=application.id,
        actor_user_id=staff[2].id,
        payload=PersonPayeeReviewDecisionCreate(
            submission_id=view.submission.id,
            client_request_id=uuid5(application.id, "person-review"),
            decision=KycSubmissionStatus(stage),
            reason_code=KycReviewReason.COMPLETE_CURRENT_EVIDENCE
            if stage == "approved"
            else KycReviewReason.UNREADABLE_EVIDENCE,
            identity_match_confirmed=stage == "approved",
            bank_account_match_confirmed=stage == "approved",
            documents_readable_confirmed=stage == "approved",
        ),
    )
    if stage == "approved":
        await _ensure_applicant_vehicle(
            session,
            application=application,
            person=person,
            token=token,
            staff=staff,
            settings=settings,
            clock=clock,
        )
    else:
        from app.models.driver_application import DriverApplicationStatus
        from app.services.driver_applications import terminalize_driver_application

        await terminalize_driver_application(
            session,
            application=application,
            terminal_status=DriverApplicationStatus.REJECTED,
            actor_user_id=staff[2].id,
            source_entity_type="driver_kyc_submission",
            source_entity_id=view.submission.id,
        )
        person.status = "disabled"


async def _ensure_applicant_vehicle(session, *, application, person, token, staff, settings, clock):
    from app.schemas.driver_onboarding import (
        ApplicantVehicleSubmissionCreate,
        VehicleReviewDecisionCreate,
    )
    from app.services.driver_account_setup import initiate_driver_account_setup
    from app.services.stored_files import issue_admin_file_download
    from app.services.vehicle_onboarding import (
        review_application_vehicle,
        submit_application_vehicle,
    )

    clock[0] += timedelta(hours=1)
    files = {}
    for kind in ("registration", "insurance", "vehicle_photo"):
        stored = await managed_seed_image(
            session,
            settings=settings,
            subject=person,
            label=f"ayodele-bakare-{kind.replace('_', '-')}",
            purpose=FilePurpose.VEHICLE_EVIDENCE.value,
            identity=str(application.id),
            at=clock[0],
        )
        files[kind] = stored.id
    clock[0] += timedelta(hours=1)
    view = await submit_application_vehicle(
        session,
        settings=settings,
        payload=ApplicantVehicleSubmissionCreate(
            application_access_token=SecretStr(token),
            client_request_id=uuid5(application.id, "vehicle"),
            plate_number="ABJ-603-MR",
            plate_country_code="NG",
            vehicle_type=VehicleType.CAR,
            make="Toyota",
            model="Corolla",
            year=2020,
            color="White",
            registration_file_id=files["registration"],
            insurance_file_id=files["insurance"],
            vehicle_photo_file_id=files["vehicle_photo"],
        ),
    )
    if view.submission is None:
        raise ValueError("Expected demo vehicle submission is missing")
    clock[0] += timedelta(hours=1)
    for file_id in files.values():
        await issue_admin_file_download(
            session,
            actor_user_id=staff[3].id,
            file_id=file_id,
            access_purpose="kyc_review",
            reason=f"vehicle_approval:{view.submission.id}",
            storage=build_storage_provider(settings),
            settings=settings,
        )
    await review_application_vehicle(
        session,
        application_id=application.id,
        vehicle_id=view.submission.vehicle_id,
        submission_id=view.submission.id,
        actor_user_id=staff[3].id,
        payload=VehicleReviewDecisionCreate(
            client_request_id=uuid5(application.id, "vehicle-review"),
            decision=KycSubmissionStatus.APPROVED,
            reason_code=VehicleReviewReason.COMPLETE_CURRENT_EVIDENCE,
            owner_match_confirmed=True,
            vehicle_identity_confirmed=True,
            roadworthy_confirmed=True,
            pilot_car_confirmed=True,
            documents_readable_confirmed=True,
            valid_until=datetime.now(UTC) + timedelta(days=90),
        ),
    )
    await initiate_driver_account_setup(
        session,
        application_id=application.id,
        actor_user_id=staff[3].id,
        client_request_id=uuid5(application.id, "account-setup"),
        settings=settings,
    )


async def ensure_demo_start_authority(
    session: AsyncSession, *, graph: StartAuthorityGraph, settings: Settings
) -> None:
    from app.seeds.demo import ensure_seed_allowed

    ensure_seed_allowed(
        settings.model_copy(
            update={"database_url": settings.database_url or str(session.get_bind().url)}
        )
    )
    accepted_at = require_seed_value(graph.assignment.accepted_at, "assignment acceptance date")
    activated_at = require_seed_value(graph.assignment.activated_at, "assignment activation date")
    driver, admin, advertiser = graph.driver, graph.admin, graph.advertiser
    from app.models.user import User

    operations = await session.scalar(
        select(User).where(User.email == "ibrahim.danjuma@terraxmedia.com")
    )
    finance = await session.scalar(select(User).where(User.email == "hauwa.sani@terraxmedia.com"))
    compliance = await session.scalar(
        select(User).where(User.email == "olumide.fashola@terraxmedia.com")
    )
    admin = operations or admin
    profile, assignment, campaign, vehicle = (
        graph.driver_profile,
        graph.assignment,
        graph.campaign,
        graph.vehicle,
    )
    now = datetime.now(UTC)
    await ensure_daily_terms(
        session,
        campaign=campaign,
        assignment=assignment,
        profile=profile,
        admin=admin,
        advertiser=advertiser,
        settings=settings,
    )
    await seed_campaign_financials(
        session, campaign=campaign, admin=finance or admin, advertiser=advertiser
    )

    if not await session.scalar(
        select(Payee.id).where(
            Payee.tenant_id == driver.id,
            Payee.payee_type == "driver",
            Payee.subject_id == profile.id,
        )
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
                    "account_name": driver.full_name,
                    "account_number": "0000000000",
                    "bank_code": "999",
                }
            ).encode(),
            AssociatedData(
                tenant_id=driver.id, record_id=bank.id, field_name="bank_account.details"
            ),
        )
        bank_version = PayeeBankAccountVersion(
            bank_account_id=bank.id,
            payee_version_id=payee_version.id,
            version=1,
            encrypted_details=bank_envelope.to_mapping(),
            encryption_algorithm="AES-256-GCM",
            encryption_key_version=bank_envelope.key_version,
            verification_reference_sha256=hashlib.sha256(bank.id.bytes).hexdigest(),
            verified_at=assignment.accepted_at,
            verified_by_user_id=(finance or admin).id,
        )
        session.add(bank_version)
        await session.flush()
        from app.models.payee import PayeeBankAccountPayoutVerification

        session.add(
            PayeeBankAccountPayoutVerification(
                bank_account_version_id=bank_version.id,
                verification_reference_sha256=bank_version.verification_reference_sha256,
                verified_by_user_id=(finance or admin).id,
                created_at=assignment.accepted_at,
            )
        )
    image_revision = (
        await session.scalar(
            select(func.max(InstallationEvidenceSubmission.revision)).where(
                InstallationEvidenceSubmission.assignment_id == assignment.id
            )
        )
        or 0
    ) + 1

    evidence_step = (activated_at - accepted_at) / 4
    captured_at = accepted_at + evidence_step
    submitted_at = captured_at + evidence_step
    reviewed_at = submitted_at + evidence_step

    async def managed_image(label):
        return await managed_seed_image(
            session,
            settings=settings,
            subject=driver,
            label=label,
            purpose=FilePurpose.INSTALLATION_EVIDENCE.value,
            identity=f"{assignment.id}:{image_revision}",
            at=captured_at,
        )

    proof = await session.scalar(
        select(DisplayProof)
        .where(DisplayProof.assignment_id == assignment.id)
        .order_by(DisplayProof.verified_at.desc())
        .limit(1)
    )
    if proof is None or proof.valid_until.replace(tzinfo=UTC) <= now:
        installation_file = await managed_image("front")
        proof_file = await managed_image("back")
        device_id = uuid4()
        evidence = InstallationEvidenceSubmission(
            assignment_id=assignment.id,
            campaign_id=campaign.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            submitted_by_user_id=driver.id,
            reviewed_by_user_id=(compliance or admin).id,
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
            captured_at=captured_at,
            required_views=list(
                settings.installation_evidence_views
                or ("front", "back", "left", "right", "close_up")
            ),
            status=InstallationEvidenceStatus.APPROVED.value,
            reviewed_at=reviewed_at,
            approved_until=now
            + timedelta(hours=settings.installation_evidence_validity_hours or 168),
            evidence_metadata={"demo_synthetic": True},
            submitted_at=submitted_at,
        )
        session.add(evidence)
        await session.flush()
        for index, view in enumerate(evidence.required_views):
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

    await ensure_daily_terms(
        session,
        campaign=campaign,
        assignment=assignment,
        profile=profile,
        admin=admin,
        advertiser=advertiser,
        settings=settings,
    )
    await seed_campaign_financials(
        session, campaign=campaign, admin=finance or admin, advertiser=advertiser
    )
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
        offer_terms = require_seed_value(assignment.offer_terms, "frozen offer terms")
        binding = require_seed_value(
            await session.scalar(
                select(AssignmentRuleBinding).where(
                    AssignmentRuleBinding.assignment_id == assignment.id
                )
            ),
            "assignment rule binding",
        )
        production = require_seed_value(
            await session.scalar(
                select(ProductionStart).where(ProductionStart.campaign_id == campaign.id)
            ),
            "production start",
        )
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
            "creative_id": offer_terms["creative"]["id"],
            "installation_evidence_submission_id": str(proof.evidence_submission_id),
            "installation_evidence_revision": image_revision,
            "assignment_rule_binding_id": str(binding.id),
            "liability_reservation_id": str(reservation.id),
            "financial_authorization_id": str(reservation.authorization_id),
            "production_start_id": str(production.id),
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
                occurred_at=activated_at,
                event_metadata={
                    "activation_snapshot": snapshot,
                    "activation_snapshot_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
                    "demo_synthetic": True,
                },
                offer_terms_sha256=assignment.offer_terms_sha256,
            )
        )
    await session.flush()
    if assignment.status == "active":
        await ensure_current_activation_snapshot(session, assignment=assignment, lock=True)

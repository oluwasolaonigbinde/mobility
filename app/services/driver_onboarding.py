import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.adapters.crypto import CryptoProvider
from app.core.config import Settings
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.driver import DriverProfile
from app.models.driver_application import DriverApplication, DriverApplicationStatus
from app.models.kyc import (
    DriverKycReviewDecision,
    DriverKycSubmission,
    KycReviewReason,
    KycSubmissionStatus,
)
from app.models.payee import (
    PayeeBankAccount,
    PayeeBankAccountPayoutVerification,
    PayeeBankAccountVersion,
)
from app.schemas.driver_onboarding import (
    PersonPayeeRenewalCreate,
    PersonPayeeReviewDecisionCreate,
    PersonPayeeStageStatus,
    PersonPayeeSubmissionCreate,
)
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.driver_applications import application_from_access_token, status_reference_hash
from app.services.kyc import (
    require_submission_payload,
    submit_driver_kyc,
    validate_driver_kyc_for_approval,
)
from app.services.payees import (
    VerifiedBankAccountDetails,
    add_applicant_bank_account_version,
    create_applicant_payee,
    read_applicant_verified_bank_account,
    verification_reference_hash,
)


@dataclass(frozen=True, slots=True)
class PersonPayeeView:
    submission: DriverKycSubmission | None
    decision: DriverKycReviewDecision | None
    document_file_ids: dict[str, UUID]
    bank_account_verified: bool = False

    @property
    def status(self) -> PersonPayeeStageStatus:
        if self.submission is None:
            return PersonPayeeStageStatus.NOT_SUBMITTED
        return PersonPayeeStageStatus(self.submission.status)


def _error(code: str, message: str, status_code: int) -> AppError:
    return AppError(code, message, status_code=status_code)


async def _acquire_work_eligibility_authority(
    session: AsyncSession, *, driver_profile_id: UUID
) -> None:
    from app.services.vehicle_onboarding import acquire_work_eligibility_lock

    await acquire_work_eligibility_lock(session, driver_profile_id=driver_profile_id)


async def application_from_reference(
    session: AsyncSession, *, reference: str, lock: bool
) -> DriverApplication:
    normalized = reference.strip()
    if not 32 <= len(normalized) <= 128:
        raise _error(
            "ONBOARDING_REFERENCE_INVALID",
            "Driver onboarding reference is unavailable",
            status.HTTP_404_NOT_FOUND,
        )
    query = select(DriverApplication).where(
        DriverApplication.status_reference_sha256 == status_reference_hash(normalized),
        DriverApplication.status == DriverApplicationStatus.PENDING,
    )
    if lock:
        query = query.with_for_update()
    application = await session.scalar(query)
    if application is None:
        raise _error(
            "ONBOARDING_REFERENCE_INVALID",
            "Driver onboarding reference is unavailable",
            status.HTTP_404_NOT_FOUND,
        )
    return application


async def _documents(session: AsyncSession, submission_id: UUID) -> dict[str, UUID]:
    from app.models.kyc import DriverKycDocument

    rows = list(
        (
            await session.scalars(
                select(DriverKycDocument).where(DriverKycDocument.submission_id == submission_id)
            )
        ).all()
    )
    return {row.document_type: row.stored_file_id for row in rows}


async def _view_for_profile(session: AsyncSession, *, profile_id: UUID) -> PersonPayeeView:
    submission = await session.scalar(
        select(DriverKycSubmission)
        .where(DriverKycSubmission.driver_profile_id == profile_id)
        .order_by(DriverKycSubmission.version.desc())
        .limit(1)
    )
    if submission is None:
        return PersonPayeeView(None, None, {})
    decision = await session.scalar(
        select(DriverKycReviewDecision).where(
            DriverKycReviewDecision.submission_id == submission.id
        )
    )
    payout_verification = await session.scalar(
        select(PayeeBankAccountPayoutVerification.id).where(
            PayeeBankAccountPayoutVerification.bank_account_version_id
            == submission.bank_account_version_id
        )
    )
    return PersonPayeeView(
        submission,
        decision,
        await _documents(session, submission.id),
        payout_verification is not None,
    )


async def person_payee_status_by_reference(
    session: AsyncSession, *, reference: str
) -> PersonPayeeView:
    try:
        application = await application_from_reference(session, reference=reference, lock=False)
    except AppError:
        return PersonPayeeView(None, None, {})
    return await _view_for_profile(session, profile_id=application.driver_profile_id)


async def _lock_review_users(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    application_id: UUID | None,
    driver_profile_id: UUID | None,
) -> None:
    from app.services.users import _lock_users

    query = select(DriverProfile.user_id)
    if application_id is not None:
        query = query.join(
            DriverApplication, DriverApplication.driver_profile_id == DriverProfile.id
        ).where(DriverApplication.id == application_id)
    else:
        query = query.where(DriverProfile.id == driver_profile_id)
    subject = await session.scalar(query)
    await _lock_users(session, {actor_user_id, subject} if subject else {actor_user_id})
    await require_active_admin(session, actor_user_id)


async def _capture_identity(
    session: AsyncSession,
    payload: PersonPayeeSubmissionCreate | PersonPayeeRenewalCreate,
    actor_user_id: UUID | None,
    settings: Settings,
) -> tuple[UUID, UUID]:
    from app.services.users import _lock_users

    if isinstance(payload, PersonPayeeSubmissionCreate):
        application = await application_from_access_token(
            session,
            token=payload.application_access_token.get_secret_value(),
            settings=settings,
            lock=False,
        )
        await _lock_users(session, {application.user_id})
        application = await application_from_access_token(
            session,
            token=payload.application_access_token.get_secret_value(),
            settings=settings,
            lock=True,
        )
        return application.user_id, application.driver_profile_id
    from app.services.kyc import _driver_profile

    if actor_user_id is None:
        raise _error("KYC_SCOPE_NOT_FOUND", "Driver documents were not found", 404)
    await _lock_users(session, {actor_user_id})
    profile_id = await session.scalar(
        select(DriverProfile.id).where(DriverProfile.user_id == actor_user_id)
    )
    if profile_id is None:
        raise _error("KYC_SCOPE_NOT_FOUND", "Driver documents were not found", 404)
    await _acquire_work_eligibility_authority(session, driver_profile_id=profile_id)
    profile = await _driver_profile(session, actor_user_id=actor_user_id, lock=True)
    return profile.user_id, profile.id


async def submit_application_person_payee(
    session: AsyncSession,
    *,
    payload: PersonPayeeSubmissionCreate | PersonPayeeRenewalCreate,
    actor_user_id: UUID | None = None,
    crypto: CryptoProvider,
    settings: Settings,
) -> PersonPayeeView:
    user_id, profile_id = await _capture_identity(session, payload, actor_user_id, settings)
    await _acquire_work_eligibility_authority(session, driver_profile_id=profile_id)
    profile = await session.scalar(
        select(DriverProfile).where(DriverProfile.id == profile_id).with_for_update()
    )
    if profile is None or profile.user_id != user_id:
        raise _error("PERSON_PAYEE_AUTHORITY_INVALID", "Driver documents are unavailable", 409)
    if isinstance(payload, PersonPayeeRenewalCreate):
        return await _submit_partial_person_renewal(
            session, profile=profile, payload=payload, crypto=crypto, settings=settings
        )
    documents = {
        "driver_license": payload.driver_license_file_id,
        "driver_photo": payload.driver_photo_file_id,
        "signed_agreement": payload.signed_agreement_file_id,
    }
    existing = await session.scalar(
        select(DriverKycSubmission).where(
            DriverKycSubmission.driver_profile_id == profile.id,
            DriverKycSubmission.client_request_id == payload.client_request_id,
        )
    )
    details = VerifiedBankAccountDetails(
        account_name=payload.account_name.get_secret_value(),
        account_number=payload.account_number.get_secret_value(),
        bank_code=payload.bank_code.get_secret_value(),
    )
    applicant_capture_reference = f"driver-application-capture-v1:{payload.client_request_id}"
    if existing is not None:
        require_submission_payload(existing)
        stored_details = await read_applicant_verified_bank_account(
            session,
            bank_account_version_id=existing.bank_account_version_id,
            actor_user_id=user_id,
            crypto=crypto,
            purpose="onboarding_exact_retry",
        )
        account_version = await session.get(
            PayeeBankAccountVersion, existing.bank_account_version_id
        )
        if (
            stored_details != details
            or account_version is None
            or account_version.verification_reference_sha256
            != verification_reference_hash(applicant_capture_reference)
        ):
            raise _error(
                "PERSON_PAYEE_RETRY_CONFLICT",
                "The onboarding retry does not match the original request",
                status.HTTP_409_CONFLICT,
            )
        view = await submit_driver_kyc(
            session,
            actor_user_id=user_id,
            client_request_id=payload.client_request_id,
            nin=payload.nin.get_secret_value(),
            bank_account_version_id=existing.bank_account_version_id,
            document_file_ids=documents,
            crypto=crypto,
            settings=settings,
            allow_invited_actor=True,
            allow_document_renewal=True,
        )
        return PersonPayeeView(view.submission, None, view.document_file_ids)

    current = await session.scalar(
        select(DriverKycSubmission)
        .where(DriverKycSubmission.driver_profile_id == profile.id)
        .order_by(DriverKycSubmission.version.desc())
        .limit(1)
    )
    if current is not None and current.status not in {
        KycSubmissionStatus.REJECTED,
        KycSubmissionStatus.EXPIRED,
    }:
        raise _error(
            "PERSON_PAYEE_RESUBMISSION_NOT_ALLOWED",
            "Only rejected or expired evidence can be resubmitted",
            status.HTTP_409_CONFLICT,
        )
    payee, _ = await create_applicant_payee(
        session,
        driver_profile_id=profile.id,
        actor_user_id=user_id,
    )
    account = await add_applicant_bank_account_version(
        session,
        payee_id=payee.id,
        details=details,
        verification_reference=applicant_capture_reference,
        actor_user_id=user_id,
        crypto=crypto,
    )
    kyc_view = await submit_driver_kyc(
        session,
        actor_user_id=user_id,
        client_request_id=payload.client_request_id,
        nin=payload.nin.get_secret_value(),
        bank_account_version_id=account.id,
        document_file_ids=documents,
        crypto=crypto,
        settings=settings,
        allow_invited_actor=True,
        allow_document_renewal=True,
    )
    return PersonPayeeView(kyc_view.submission, None, kyc_view.document_file_ids)


async def _submit_partial_person_renewal(session, *, profile, payload, crypto, settings):
    from app.services.document_reviews import document_outcomes

    original = await session.get(DriverKycSubmission, payload.expected_submission_id)
    if original is None or original.driver_profile_id != profile.id:
        raise _error(
            "PERSON_PAYEE_REVISION_STALE",
            "Your documents changed. Refresh before uploading again",
            409,
        )
    existing = await session.scalar(
        select(DriverKycSubmission).where(
            DriverKycSubmission.driver_profile_id == profile.id,
            DriverKycSubmission.client_request_id == payload.client_request_id,
        )
    )
    current = await session.scalar(
        select(DriverKycSubmission)
        .where(
            DriverKycSubmission.driver_profile_id == profile.id,
        )
        .order_by(DriverKycSubmission.version.desc())
        .limit(1)
    )
    if existing is not None:
        if original.version != existing.version - 1:
            raise _error(
                "PERSON_PAYEE_RETRY_CONFLICT",
                "The document retry does not match the original request",
                409,
            )
    elif current is None or current.id != original.id:
        raise _error(
            "PERSON_PAYEE_REVISION_STALE",
            "Your documents changed. Refresh before uploading again",
            409,
        )
    if original.status not in {
        KycSubmissionStatus.REJECTED,
        KycSubmissionStatus.EXPIRED,
        KycSubmissionStatus.APPROVED,
    }:
        raise _error(
            "PERSON_PAYEE_RESUBMISSION_NOT_ALLOWED",
            "Only rejected or expired evidence can be resubmitted",
            409,
        )
    previous_documents = await _documents(session, original.id)
    decision = await session.scalar(
        select(DriverKycReviewDecision).where(DriverKycReviewDecision.submission_id == original.id)
    )
    from app.services.payout_rule_serialization import database_clock

    outcomes = document_outcomes(decision, previous_documents, await database_clock(session))
    if (
        existing is None
        and original.status == KycSubmissionStatus.APPROVED
        and not any(item["status"] == "expired" for item in outcomes.values())
    ):
        raise _error(
            "PERSON_PAYEE_RESUBMISSION_NOT_ALLOWED",
            "Only rejected or expired documents can be replaced",
            409,
        )
    documents = _renewal_person_documents(
        original, payload, previous_documents, outcomes, exact_retry=existing is not None
    )
    nin = await _renewal_nin(session, profile, original, decision, payload, crypto)
    bank_id = await _renewal_bank_version(
        session, profile, original, decision, existing, payload, crypto
    )
    view = await submit_driver_kyc(
        session,
        actor_user_id=profile.user_id,
        client_request_id=payload.client_request_id,
        nin=nin,
        bank_account_version_id=bank_id,
        document_file_ids=documents,
        crypto=crypto,
        settings=settings,
        allow_invited_actor=True,
        allow_document_renewal=True,
    )
    from app.services.vehicle_onboarding import reconcile_driver_work_eligibility

    await reconcile_driver_work_eligibility(session, driver_profile_id=profile.id)
    return PersonPayeeView(view.submission, None, view.document_file_ids)


def _renewal_person_documents(
    original, payload, previous_documents, outcomes, *, exact_retry=False
):
    supplied_documents = {
        kind: value
        for kind in ("driver_license", "driver_photo", "signed_agreement")
        if (value := getattr(payload, f"{kind}_file_id")) is not None
    }
    required = {
        kind
        for kind, item in outcomes.items()
        if not exact_retry and item["status"] in {"rejected", "expired"}
    }
    required.update(
        {"driver_license", "driver_photo", "signed_agreement"} - set(previous_documents)
    )
    if original.purged_at is not None:
        required.update({"driver_license", "driver_photo", "signed_agreement"})
    if not required.issubset(supplied_documents):
        raise _error(
            "PERSON_PAYEE_REPLACEMENTS_REQUIRED",
            "Replace the documents marked rejected or expired",
            422,
        )
    return {**previous_documents, **supplied_documents}


async def _renewal_nin(session, profile, original, decision, payload, crypto):
    from app.adapters.crypto import AssociatedData, CryptoOperationError
    from app.services.kyc import DRIVER_NIN_FIELD, _envelope

    nin = payload.nin.get_secret_value() if payload.nin else None
    if (
        original.purged_at is not None
        or (decision and decision.reason_code == KycReviewReason.IDENTITY_MISMATCH)
    ) and nin is None:
        raise _error("PERSON_PAYEE_NIN_REQUIRED", "Enter your corrected NIN", 422)
    if nin is None:
        try:
            nin = crypto.decrypt(
                _envelope(original.encrypted_nin),
                AssociatedData(
                    tenant_id=profile.user_id,
                    record_id=original.nin_record_id,
                    field_name=DRIVER_NIN_FIELD,
                ),
            ).decode("ascii")
        except (CryptoOperationError, UnicodeDecodeError):
            raise _error(
                "KYC_DECRYPTION_FAILED", "Saved identity details could not be authenticated", 409
            ) from None
        await create_audit_event(
            session,
            actor_user_id=profile.user_id,
            action="driver.kyc.renewal_reuse",
            entity_type="driver_kyc_submission",
            entity_id=str(original.id),
            metadata={"version": original.version},
        )
    return nin


async def _renewal_bank_version(session, profile, original, decision, existing, payload, crypto):
    bank_values = [payload.account_name, payload.account_number, payload.bank_code]
    if any(bank_values) and not all(bank_values):
        raise _error(
            "PERSON_PAYEE_BANK_DETAILS_REQUIRED",
            "Enter the account name, number and bank together",
            422,
        )
    replace_bank = original.purged_at is not None or bool(
        decision and decision.reason_code == KycReviewReason.BANK_ACCOUNT_MISMATCH
    )
    if replace_bank and not all(bank_values):
        raise _error("PERSON_PAYEE_BANK_DETAILS_REQUIRED", "Enter your corrected bank details", 422)
    bank_id = original.bank_account_version_id
    if all(bank_values):
        details = VerifiedBankAccountDetails(
            account_name=payload.account_name.get_secret_value(),
            account_number=payload.account_number.get_secret_value(),
            bank_code=payload.bank_code.get_secret_value(),
        )
        if existing:
            stored = await read_applicant_verified_bank_account(
                session,
                bank_account_version_id=existing.bank_account_version_id,
                actor_user_id=profile.user_id,
                crypto=crypto,
                purpose="onboarding_exact_retry",
            )
            if stored != details:
                raise _error(
                    "PERSON_PAYEE_RETRY_CONFLICT",
                    "The document retry does not match the original request",
                    409,
                )
            bank_id = existing.bank_account_version_id
        else:
            payee, _ = await create_applicant_payee(
                session, driver_profile_id=profile.id, actor_user_id=profile.user_id
            )
            account = await add_applicant_bank_account_version(
                session,
                payee_id=payee.id,
                details=details,
                verification_reference=f"driver-application-capture-v1:{payload.client_request_id}",
                actor_user_id=profile.user_id,
                crypto=crypto,
            )
            bank_id = account.id
    return bank_id


def _decision_fingerprint(*, application_id: UUID, payload: PersonPayeeReviewDecisionCreate) -> str:
    document = {
        "application_id": str(application_id),
        **payload.model_dump(mode="json"),
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validate_decision_facts(payload: PersonPayeeReviewDecisionCreate) -> None:
    approvals = (
        payload.identity_match_confirmed,
        payload.bank_account_match_confirmed,
        payload.documents_readable_confirmed,
    )
    if payload.decision == KycSubmissionStatus.APPROVED:
        if payload.reason_code != KycReviewReason.COMPLETE_CURRENT_EVIDENCE or not all(approvals):
            raise _error(
                "PERSON_PAYEE_APPROVAL_FACTS_REQUIRED",
                "Approval requires complete identity, account and readability checks",
                status.HTTP_409_CONFLICT,
            )
    elif payload.reason_code == KycReviewReason.COMPLETE_CURRENT_EVIDENCE:
        raise _error(
            "PERSON_PAYEE_DECISION_REASON_INVALID",
            "A terminal evidence reason is required",
            status.HTTP_409_CONFLICT,
        )


async def _require_exact_review_evidence(
    session: AsyncSession,
    *,
    submission: DriverKycSubmission,
    document_file_ids: dict[str, UUID],
    actor_user_id: UUID,
) -> None:
    account_version = await session.get(PayeeBankAccountVersion, submission.bank_account_version_id)
    payout_verification = await session.scalar(
        select(PayeeBankAccountPayoutVerification.id).where(
            PayeeBankAccountPayoutVerification.bank_account_version_id
            == submission.bank_account_version_id
        )
    )
    if account_version is None or payout_verification is None:
        raise _error(
            "PERSON_PAYEE_BANK_ACCOUNT_UNVERIFIED",
            "The exact current bank-account version requires authorized payout verification",
            status.HTTP_409_CONFLICT,
        )
    account = await session.get(PayeeBankAccount, account_version.bank_account_id)
    if account is None:  # pragma: no cover - protected by FK
        raise RuntimeError("Person/payee bank-account authority disappeared")
    review_purpose = "person_payee_approval"
    nin_read = bool(
        await session.scalar(
            select(
                select(AuditEvent.id)
                .where(
                    AuditEvent.actor_user_id == actor_user_id,
                    AuditEvent.action == "admin.kyc.nin_read",
                    AuditEvent.entity_type == "driver_kyc_submission",
                    AuditEvent.entity_id == str(submission.id),
                    AuditEvent.event_metadata["purpose"].as_string() == review_purpose,
                )
                .limit(1)
                .exists()
            )
        )
    )
    account_read = bool(
        await session.scalar(
            select(
                select(AuditEvent.id)
                .where(
                    AuditEvent.actor_user_id == actor_user_id,
                    AuditEvent.action == "admin.bank_account.read",
                    AuditEvent.entity_type == "payee_bank_account",
                    AuditEvent.entity_id == str(account.id),
                    AuditEvent.event_metadata["bank_account_version"].as_integer()
                    == account_version.version,
                    AuditEvent.event_metadata["purpose"].as_string() == review_purpose,
                )
                .limit(1)
                .exists()
            )
        )
    )
    required_file_ids = tuple(str(file_id) for file_id in document_file_ids.values())
    reviewed_files = set(
        (
            await session.scalars(
                select(AuditEvent.entity_id)
                .distinct()
                .where(
                    AuditEvent.actor_user_id == actor_user_id,
                    AuditEvent.action == "stored_file.read",
                    AuditEvent.entity_type == "stored_file",
                    AuditEvent.entity_id.in_(required_file_ids),
                    AuditEvent.event_metadata["file_purpose"].as_string() == "driver_kyc",
                    AuditEvent.event_metadata["access_purpose"].as_string() == "kyc_review",
                    AuditEvent.event_metadata["reason"].as_string()
                    == f"person_payee_approval:{submission.id}",
                )
                .limit(len(required_file_ids))
            )
        ).all()
    )
    if not nin_read or not account_read or not set(required_file_ids).issubset(reviewed_files):
        raise _error(
            "PERSON_PAYEE_REVIEW_EVIDENCE_INCOMPLETE",
            "Approval requires exact current identity, account and document review evidence",
            status.HTTP_409_CONFLICT,
        )


async def review_application_person_payee(
    session: AsyncSession,
    *,
    application_id: UUID | None = None,
    driver_profile_id: UUID | None = None,
    actor_user_id: UUID,
    payload: PersonPayeeReviewDecisionCreate,
) -> PersonPayeeView:
    _validate_decision_facts(payload)
    authority_id = application_id or driver_profile_id
    if authority_id is None:
        raise _error("DRIVER_PROFILE_NOT_FOUND", "Driver documents were not found", 404)
    await _lock_review_users(
        session,
        actor_user_id=actor_user_id,
        application_id=application_id,
        driver_profile_id=driver_profile_id,
    )
    fingerprint = _decision_fingerprint(application_id=authority_id, payload=payload)
    application = await session.scalar(
        select(DriverApplication)
        .where(
            DriverApplication.id == application_id
            if application_id
            else DriverApplication.driver_profile_id == driver_profile_id
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if application_id and application is None:
        raise _error("DRIVER_APPLICATION_NOT_FOUND", "Driver application was not found", 404)
    profile_id = application.driver_profile_id if application else authority_id
    await _acquire_work_eligibility_authority(session, driver_profile_id=profile_id)
    profile = await session.scalar(
        select(DriverProfile).where(DriverProfile.id == profile_id).with_for_update()
    )
    if profile is None:
        raise _error("PERSON_PAYEE_INCOMPLETE", "Driver documents are unavailable", 409)
    retry = await session.scalar(
        select(DriverKycReviewDecision).where(
            DriverKycReviewDecision.client_request_id == payload.client_request_id
        )
    )
    if retry is not None:
        original_submission = await session.scalar(
            select(DriverKycSubmission)
            .where(
                DriverKycSubmission.id == retry.submission_id,
                DriverKycSubmission.driver_profile_id == profile_id,
            )
            .with_for_update()
        )
        if (
            original_submission is None
            or retry.request_fingerprint != fingerprint
            or original_submission.id != payload.submission_id
        ):
            raise _error(
                "PERSON_PAYEE_DECISION_RETRY_CONFLICT",
                "The decision retry does not match the original request",
                status.HTTP_409_CONFLICT,
            )
        await _reconcile_review_eligibility(
            session,
            application=application,
            driver_profile_id=profile.id,
            actor_user_id=actor_user_id,
            source_entity_type="driver_kyc_submission",
            source_entity_id=original_submission.id,
        )
        return PersonPayeeView(
            original_submission,
            retry,
            await _documents(session, original_submission.id),
            (
                await session.scalar(
                    select(PayeeBankAccountPayoutVerification.id).where(
                        PayeeBankAccountPayoutVerification.bank_account_version_id
                        == original_submission.bank_account_version_id
                    )
                )
                is not None
            ),
        )
    submission = await session.scalar(
        select(DriverKycSubmission)
        .where(DriverKycSubmission.driver_profile_id == profile_id)
        .order_by(DriverKycSubmission.version.desc())
        .limit(1)
        .with_for_update()
    )
    if submission is None:
        raise _error(
            "PERSON_PAYEE_INCOMPLETE",
            "A complete current person/payee submission is required",
            status.HTTP_409_CONFLICT,
        )
    if submission.id != payload.submission_id:
        raise _error(
            "PERSON_PAYEE_REVISION_STALE", "Documents changed. Refresh before reviewing them", 409
        )
    require_submission_payload(submission)
    if submission.status != KycSubmissionStatus.PENDING_REVIEW:
        raise _error(
            "PERSON_PAYEE_ALREADY_DECIDED",
            "The current person/payee submission already has a decision",
            status.HTTP_409_CONFLICT,
        )
    documents = await _documents(session, submission.id)
    if payload.decision == KycSubmissionStatus.APPROVED:
        documents = await validate_driver_kyc_for_approval(
            session,
            submission=submission,
            profile=profile,
        )
        await _require_exact_review_evidence(
            session,
            submission=submission,
            document_file_ids=documents,
            actor_user_id=actor_user_id,
        )
    from app.services.document_reviews import validate_document_reviews

    await validate_document_reviews(
        session,
        payload=payload,
        documents=documents,
        submission_id=submission.id,
        actor_user_id=actor_user_id,
    )
    decision = DriverKycReviewDecision(
        submission_id=submission.id,
        client_request_id=payload.client_request_id,
        request_fingerprint=fingerprint,
        document_reviews={
            key: item.model_dump(mode="json") for key, item in payload.document_reviews.items()
        },
        decision=payload.decision,
        reason_code=payload.reason_code,
        identity_match_confirmed=payload.identity_match_confirmed,
        bank_account_match_confirmed=payload.bank_account_match_confirmed,
        documents_readable_confirmed=payload.documents_readable_confirmed,
        decided_by_user_id=actor_user_id,
    )
    session.add(decision)
    submission.status = payload.decision.value
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action=f"admin.driver_person_payee.{payload.decision.value}",
        entity_type="driver_kyc_submission",
        entity_id=str(submission.id),
        metadata={
            "driver_profile_id": str(profile.id),
            "version": submission.version,
            "reason_code": payload.reason_code.value,
            "identity_match_confirmed": payload.identity_match_confirmed,
            "bank_account_match_confirmed": payload.bank_account_match_confirmed,
            "documents_readable_confirmed": payload.documents_readable_confirmed,
        },
    )
    await _reconcile_review_eligibility(
        session,
        application=application,
        driver_profile_id=profile.id,
        actor_user_id=actor_user_id,
        source_entity_type="driver_kyc_submission",
        source_entity_id=submission.id,
    )
    return PersonPayeeView(
        submission,
        decision,
        documents,
        (
            await session.scalar(
                select(PayeeBankAccountPayoutVerification.id).where(
                    PayeeBankAccountPayoutVerification.bank_account_version_id
                    == submission.bank_account_version_id
                )
            )
            is not None
        ),
    )


async def application_person_payee_view(
    session: AsyncSession, *, application: DriverApplication
) -> PersonPayeeView:
    return await _view_for_profile(session, profile_id=application.driver_profile_id)


async def _reconcile_review_eligibility(
    session: AsyncSession,
    *,
    application: DriverApplication | None,
    driver_profile_id: UUID,
    actor_user_id: UUID,
    source_entity_type: str,
    source_entity_id: UUID,
) -> None:
    from app.services.vehicle_onboarding import (
        reconcile_application_approval,
        reconcile_driver_work_eligibility,
    )

    if application:
        await reconcile_application_approval(
            session,
            application=application,
            actor_user_id=actor_user_id,
            source_entity_type=source_entity_type,
            source_entity_id=source_entity_id,
        )
    else:
        await reconcile_driver_work_eligibility(session, driver_profile_id=driver_profile_id)

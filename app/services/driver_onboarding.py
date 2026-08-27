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
    PersonPayeeReviewDecisionCreate,
    PersonPayeeStageStatus,
    PersonPayeeSubmissionCreate,
)
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.driver_applications import application_from_access_token, status_reference_hash
from app.services.kyc import submit_driver_kyc, validate_driver_kyc_for_approval
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


async def submit_application_person_payee(
    session: AsyncSession,
    *,
    payload: PersonPayeeSubmissionCreate,
    crypto: CryptoProvider,
    settings: Settings,
) -> PersonPayeeView:
    application = await application_from_access_token(
        session,
        token=payload.application_access_token.get_secret_value(),
        settings=settings,
        lock=True,
    )
    profile = await session.scalar(
        select(DriverProfile)
        .where(DriverProfile.id == application.driver_profile_id)
        .with_for_update()
    )
    if profile is None or profile.user_id != application.user_id:
        raise _error(
            "PERSON_PAYEE_AUTHORITY_INVALID",
            "Driver onboarding authority is unavailable",
            status.HTTP_409_CONFLICT,
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
        stored_details = await read_applicant_verified_bank_account(
            session,
            bank_account_version_id=existing.bank_account_version_id,
            actor_user_id=application.user_id,
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
            actor_user_id=application.user_id,
            client_request_id=payload.client_request_id,
            nin=payload.nin.get_secret_value(),
            bank_account_version_id=existing.bank_account_version_id,
            document_file_ids=documents,
            crypto=crypto,
            allow_invited_actor=True,
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
        actor_user_id=application.user_id,
    )
    account = await add_applicant_bank_account_version(
        session,
        payee_id=payee.id,
        details=details,
        verification_reference=applicant_capture_reference,
        actor_user_id=application.user_id,
        crypto=crypto,
    )
    kyc_view = await submit_driver_kyc(
        session,
        actor_user_id=application.user_id,
        client_request_id=payload.client_request_id,
        nin=payload.nin.get_secret_value(),
        bank_account_version_id=account.id,
        document_file_ids=documents,
        crypto=crypto,
        allow_invited_actor=True,
    )
    return PersonPayeeView(kyc_view.submission, None, kyc_view.document_file_ids)


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
    events = list(
        (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.actor_user_id == actor_user_id,
                    AuditEvent.action.in_(
                        (
                            "admin.kyc.nin_read",
                            "admin.bank_account.read",
                            "stored_file.read",
                        )
                    ),
                )
            )
        ).all()
    )
    nin_read = any(
        event.action == "admin.kyc.nin_read"
        and event.entity_id == str(submission.id)
        and event.event_metadata.get("purpose") == "person_payee_approval"
        for event in events
    )
    account_read = any(
        event.action == "admin.bank_account.read"
        and event.entity_id == str(account.id)
        and event.event_metadata.get("bank_account_version") == account_version.version
        and event.event_metadata.get("purpose") == "person_payee_approval"
        for event in events
    )
    reviewed_files = {
        UUID(event.entity_id)
        for event in events
        if event.action == "stored_file.read"
        and event.entity_id is not None
        and event.event_metadata.get("file_purpose") == "driver_kyc"
        and event.event_metadata.get("access_purpose") == "kyc_review"
        and event.event_metadata.get("reason") == f"person_payee_approval:{submission.id}"
    }
    if (
        not nin_read
        or not account_read
        or not set(document_file_ids.values()).issubset(reviewed_files)
    ):
        raise _error(
            "PERSON_PAYEE_REVIEW_EVIDENCE_INCOMPLETE",
            "Approval requires exact current identity, account and document review evidence",
            status.HTTP_409_CONFLICT,
        )


async def review_application_person_payee(
    session: AsyncSession,
    *,
    application_id: UUID,
    actor_user_id: UUID,
    payload: PersonPayeeReviewDecisionCreate,
) -> PersonPayeeView:
    await require_active_admin(session, actor_user_id)
    _validate_decision_facts(payload)
    fingerprint = _decision_fingerprint(application_id=application_id, payload=payload)
    application = await session.scalar(
        select(DriverApplication).where(DriverApplication.id == application_id).with_for_update()
    )
    if application is None:
        raise _error(
            "DRIVER_APPLICATION_NOT_FOUND",
            "Driver application was not found",
            status.HTTP_404_NOT_FOUND,
        )
    profile = await session.scalar(
        select(DriverProfile)
        .where(DriverProfile.id == application.driver_profile_id)
        .with_for_update()
    )
    if profile is None:
        raise _error(
            "PERSON_PAYEE_INCOMPLETE",
            "A complete current person/payee submission is required",
            status.HTTP_409_CONFLICT,
        )
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
                DriverKycSubmission.driver_profile_id == application.driver_profile_id,
            )
            .with_for_update()
        )
        if original_submission is None or retry.request_fingerprint != fingerprint:
            raise _error(
                "PERSON_PAYEE_DECISION_RETRY_CONFLICT",
                "The decision retry does not match the original request",
                status.HTTP_409_CONFLICT,
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
        .where(DriverKycSubmission.driver_profile_id == application.driver_profile_id)
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
    decision = DriverKycReviewDecision(
        submission_id=submission.id,
        client_request_id=payload.client_request_id,
        request_fingerprint=fingerprint,
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
            "application_id": str(application.id),
            "version": submission.version,
            "reason_code": payload.reason_code.value,
            "identity_match_confirmed": payload.identity_match_confirmed,
            "bank_account_match_confirmed": payload.bank_account_match_confirmed,
            "documents_readable_confirmed": payload.documents_readable_confirmed,
        },
    )
    from app.services.vehicle_onboarding import reconcile_driver_work_eligibility

    await reconcile_driver_work_eligibility(session, driver_profile_id=profile.id)
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

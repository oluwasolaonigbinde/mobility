import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.adapters.storage import StorageObjectNotFound, StorageProvider, StorageUnavailable
from app.core.errors import AppError
from app.models.data_subject_request import (
    DataSubjectDisposition,
    DataSubjectLocation,
    DataSubjectLocationAssessment,
    DataSubjectRequest,
    DataSubjectRequestStatus,
    DataSubjectRequestType,
)
from app.models.stored_file import FileUploadIntent, StoredFile, UploadIntentStatus
from app.models.user import User
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.data_subject_inventory import build_subject_link_registry

_LEGACY_DATABASE_COUNTS = {
    "account_identity": "SELECT count(*) FROM users WHERE id = :subject_user_id",
    "organization_membership": (
        "SELECT count(*) FROM organization_memberships WHERE user_id = :subject_user_id"
    ),
    "driver_application": (
        "SELECT (SELECT count(*) FROM driver_applications "
        "WHERE user_id = :subject_user_id) + "
        "(SELECT count(*) FROM driver_application_access_tokens t "
        "JOIN driver_applications a ON a.id = t.application_id "
        "WHERE a.user_id = :subject_user_id)"
    ),
    "driver_profile": ("SELECT count(*) FROM driver_profiles WHERE user_id = :subject_user_id"),
    "identity_kyc": (
        "SELECT (SELECT count(*) FROM driver_kyc_submissions k JOIN driver_profiles d "
        "ON d.id = k.driver_profile_id WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM driver_kyc_documents kd JOIN driver_kyc_submissions k "
        "ON k.id = kd.submission_id JOIN driver_profiles d ON d.id = k.driver_profile_id "
        "WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM driver_kyc_review_decisions r "
        "JOIN driver_kyc_submissions k ON k.id = r.submission_id "
        "JOIN driver_profiles d ON d.id = k.driver_profile_id "
        "WHERE d.user_id = :subject_user_id)"
    ),
    "vehicle_evidence": (
        "SELECT (SELECT count(*) FROM vehicles v JOIN driver_profiles d "
        "ON d.id = v.driver_profile_id WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM vehicle_evidence_submissions s JOIN vehicles v "
        "ON v.id = s.vehicle_id JOIN driver_profiles d ON d.id = v.driver_profile_id "
        "WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM vehicle_evidence_documents vd "
        "JOIN vehicle_evidence_submissions s ON s.id = vd.submission_id JOIN vehicles v "
        "ON v.id = s.vehicle_id JOIN driver_profiles d ON d.id = v.driver_profile_id "
        "WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM installation_evidence_submissions s JOIN driver_profiles d "
        "ON d.id = s.driver_profile_id WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM installation_evidence_photos p "
        "JOIN installation_evidence_submissions s ON s.id = p.submission_id "
        "JOIN driver_profiles d ON d.id = s.driver_profile_id "
        "WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM display_proof_challenges c JOIN driver_profiles d "
        "ON d.id = c.driver_profile_id WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM display_proofs p JOIN driver_profiles d "
        "ON d.id = p.driver_profile_id WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM evidence_verifications e JOIN driver_profiles d "
        "ON d.id = e.driver_profile_id WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM vehicle_evidence_review_decisions r "
        "JOIN vehicle_evidence_submissions s ON s.id = r.submission_id JOIN vehicles v "
        "ON v.id = s.vehicle_id JOIN driver_profiles d ON d.id = v.driver_profile_id "
        "WHERE d.user_id = :subject_user_id)"
    ),
    "trip_session": (
        "SELECT count(*) FROM trip_sessions t JOIN driver_profiles d "
        "ON d.id = t.driver_profile_id WHERE d.user_id = :subject_user_id"
    ),
    "precise_location": (
        "SELECT count(*) FROM location_pings p JOIN trip_sessions t ON t.id = p.trip_session_id "
        "JOIN driver_profiles d ON d.id = t.driver_profile_id "
        "WHERE d.user_id = :subject_user_id"
    ),
    "device_queue_evidence": (
        "SELECT (SELECT count(*) FROM location_ping_batches b JOIN trip_sessions t "
        "ON t.id = b.trip_session_id JOIN driver_profiles d ON d.id = t.driver_profile_id "
        "WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM quarantined_ping_batches q JOIN trip_sessions t "
        "ON t.id = q.trip_session_id JOIN driver_profiles d ON d.id = t.driver_profile_id "
        "WHERE d.user_id = :subject_user_id)"
    ),
    "derived_location_analytics": (
        "SELECT count(*) FROM trip_analytics a JOIN trip_sessions t "
        "ON t.id = a.trip_session_id JOIN driver_profiles d ON d.id = t.driver_profile_id "
        "WHERE d.user_id = :subject_user_id"
    ),
    "route_replay_hashes": (
        "SELECT count(*) FROM route_replay_signatures r JOIN trip_sessions t "
        "ON t.id = r.trip_session_id JOIN driver_profiles d ON d.id = t.driver_profile_id "
        "WHERE d.user_id = :subject_user_id"
    ),
    "fraud_evidence": (
        "SELECT (SELECT count(*) FROM fraud_flags f JOIN driver_profiles d "
        "ON d.id = f.driver_profile_id WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM fraud_disputes WHERE submitted_by_user_id = :subject_user_id) + "
        "(SELECT count(*) FROM fraud_assessments a JOIN trip_sessions t "
        "ON t.id = a.trip_session_id JOIN driver_profiles d ON d.id = t.driver_profile_id "
        "WHERE d.user_id = :subject_user_id)"
    ),
    "impression_estimates": (
        "SELECT count(*) FROM impression_estimates i JOIN trip_sessions t "
        "ON t.id = i.trip_session_id JOIN driver_profiles d ON d.id = t.driver_profile_id "
        "WHERE d.user_id = :subject_user_id"
    ),
    "payout_ledger": (
        "SELECT (SELECT count(*) FROM payout_calculations p JOIN trip_sessions t "
        "ON t.id = p.trip_session_id JOIN driver_profiles d ON d.id = t.driver_profile_id "
        "WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM earnings_ledger_entries "
        "WHERE driver_user_id = :subject_user_id) + "
        "(SELECT count(*) FROM payout_batch_lines l JOIN earnings_ledger_entries e "
        "ON e.id = l.ledger_entry_id WHERE e.driver_user_id = :subject_user_id) + "
        "(SELECT count(*) FROM payout_line_reconciliation_events r "
        "JOIN payout_batch_lines l ON l.id = r.line_id JOIN earnings_ledger_entries e "
        "ON e.id = l.ledger_entry_id WHERE e.driver_user_id = :subject_user_id) + "
        "(SELECT count(*) FROM driver_currency_debt_accounts "
        "WHERE driver_user_id = :subject_user_id) + "
        "(SELECT count(*) FROM payout_debt_obligations o JOIN driver_currency_debt_accounts a "
        "ON a.id = o.debt_account_id WHERE a.driver_user_id = :subject_user_id) + "
        "(SELECT count(*) FROM payout_debt_paid_sources s JOIN payout_debt_obligations o "
        "ON o.id = s.debt_obligation_id JOIN driver_currency_debt_accounts a "
        "ON a.id = o.debt_account_id WHERE a.driver_user_id = :subject_user_id) + "
        "(SELECT count(*) FROM payout_debt_settlements s JOIN earnings_ledger_entries e "
        "ON e.id = s.source_credit_entry_id WHERE e.driver_user_id = :subject_user_id) + "
        "(SELECT count(*) FROM payout_debt_allocations a JOIN payout_debt_obligations o "
        "ON o.id = a.debt_obligation_id JOIN driver_currency_debt_accounts d "
        "ON d.id = o.debt_account_id WHERE d.driver_user_id = :subject_user_id)"
    ),
    "financial_identifiers": (
        "SELECT (SELECT count(*) FROM payees p JOIN driver_profiles d "
        "ON d.id = p.subject_id WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM payee_versions v JOIN payees p ON p.id = v.payee_id "
        "JOIN driver_profiles d ON d.id = p.subject_id "
        "WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM payee_bank_accounts a JOIN payees p ON p.id = a.payee_id "
        "JOIN driver_profiles d ON d.id = p.subject_id "
        "WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM payee_bank_account_versions av "
        "JOIN payee_bank_accounts a ON a.id = av.bank_account_id "
        "JOIN payees p ON p.id = a.payee_id JOIN driver_profiles d ON d.id = p.subject_id "
        "WHERE d.user_id = :subject_user_id) + "
        "(SELECT count(*) FROM payee_bank_account_payout_verifications v "
        "JOIN payee_bank_account_versions av ON av.id = v.bank_account_version_id "
        "JOIN payee_bank_accounts a ON a.id = av.bank_account_id "
        "JOIN payees p ON p.id = a.payee_id JOIN driver_profiles d ON d.id = p.subject_id "
        "WHERE d.user_id = :subject_user_id)"
    ),
    "notification_evidence": (
        "SELECT (SELECT count(*) FROM notifications "
        "WHERE recipient_user_id = :subject_user_id) + "
        "(SELECT count(*) FROM notification_delivery_receipts r JOIN notifications n "
        "ON n.id = r.notification_id WHERE n.recipient_user_id = :subject_user_id)"
    ),
    "audit_event": ("SELECT count(*) FROM audit_events WHERE actor_user_id = :subject_user_id"),
    "privacy_request_evidence": (
        "SELECT count(*) FROM data_subject_requests WHERE subject_user_id = :subject_user_id"
    ),
    "measurement_evidence": (
        "SELECT (SELECT count(*) FROM measurement_runs "
        "WHERE created_by_user_id = :subject_user_id) + "
        "(SELECT count(*) FROM measurement_run_proof_bindings b "
        "JOIN campaign_assignments a ON a.id = b.assignment_id "
        "JOIN driver_profiles d ON d.id = a.driver_profile_id "
        "WHERE d.user_id = :subject_user_id)"
    ),
}

SUBJECT_LINK_REGISTRY = build_subject_link_registry(_LEGACY_DATABASE_COUNTS)

_ALL_LOCATIONS = set(DataSubjectLocation)


def _fingerprint(document: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _conflict(code: str, message: str) -> AppError:
    return AppError(code, message, status_code=status.HTTP_409_CONFLICT)


async def create_data_subject_request(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    subject_user_id: UUID,
    request_type: DataSubjectRequestType,
    client_request_id: UUID,
    requested_at: datetime,
) -> DataSubjectRequest:
    await require_active_admin(session, actor_user_id)
    if requested_at.tzinfo is None:
        raise AppError(
            "INVALID_DSR_REQUEST_TIME",
            "Data-subject request time must include a timezone",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if await session.get(User, subject_user_id) is None:
        raise AppError(
            "DATA_SUBJECT_NOT_FOUND",
            "Data subject was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    document = {
        "subject_user_id": str(subject_user_id),
        "request_type": request_type.value,
        "requested_at": requested_at.astimezone(UTC).isoformat(),
    }
    fingerprint = _fingerprint(document)
    existing = await session.scalar(
        select(DataSubjectRequest).where(
            DataSubjectRequest.opened_by_user_id == actor_user_id,
            DataSubjectRequest.client_request_id == client_request_id,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise _conflict(
                "DSR_REQUEST_REPLAY_CONFLICT",
                "Data-subject request retry does not match the original request",
            )
        return existing
    case = DataSubjectRequest(
        subject_user_id=subject_user_id,
        request_type=request_type.value,
        status=DataSubjectRequestStatus.OPEN.value,
        opened_by_user_id=actor_user_id,
        client_request_id=client_request_id,
        request_fingerprint=fingerprint,
        requested_at=requested_at,
    )
    try:
        async with session.begin_nested():
            session.add(case)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(DataSubjectRequest).where(
                DataSubjectRequest.opened_by_user_id == actor_user_id,
                DataSubjectRequest.client_request_id == client_request_id,
            )
        )
        if existing is None or existing.request_fingerprint != fingerprint:
            raise _conflict(
                "DSR_REQUEST_REPLAY_CONFLICT",
                "Data-subject request retry conflicts with an accepted request",
            ) from None
        return existing
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="privacy.dsr.opened",
        entity_type="data_subject_request",
        entity_id=str(case.id),
        metadata={
            "request_type": request_type.value,
        },
    )
    return case


async def verify_data_subject_identity(
    session: AsyncSession, *, actor_user_id: UUID, request_id: UUID
) -> DataSubjectRequest:
    await require_active_admin(session, actor_user_id)
    case = await session.scalar(
        select(DataSubjectRequest).where(DataSubjectRequest.id == request_id).with_for_update()
    )
    if case is None:
        raise AppError(
            "DATA_SUBJECT_REQUEST_NOT_FOUND",
            "Data-subject request was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if case.status != DataSubjectRequestStatus.OPEN.value:
        return case
    case.status = DataSubjectRequestStatus.IDENTITY_VERIFIED.value
    case.identity_verified_at = datetime.now(UTC)
    case.identity_verified_by_user_id = actor_user_id
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="privacy.dsr.identity_verified",
        entity_type="data_subject_request",
        entity_id=str(case.id),
        metadata={},
    )
    return case


async def data_subject_inventory(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    request_id: UUID,
    storage: StorageProvider | None = None,
    verify_object_storage: bool = False,
    audit_access: bool = False,
) -> dict[str, dict[str, int]]:
    await require_active_admin(session, actor_user_id)
    case = await session.get(DataSubjectRequest, request_id)
    if case is None:
        raise AppError(
            "DATA_SUBJECT_REQUEST_NOT_FOUND",
            "Data-subject request was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if case.status == DataSubjectRequestStatus.OPEN.value:
        raise _conflict("DSR_IDENTITY_NOT_VERIFIED", "Verify identity before inventory")
    subject_parameter = (
        case.subject_user_id.hex
        if session.get_bind().dialect.name == "sqlite"
        else str(case.subject_user_id)
    )
    parameters = {"subject_user_id": subject_parameter}
    database: dict[str, int] = {}
    for rule in SUBJECT_LINK_REGISTRY:
        database[rule.data_class] = int(
            (await session.execute(text(rule.count_query), parameters)).scalar_one() or 0
        )
    stored_files = list(
        await session.scalars(
            select(StoredFile).where(StoredFile.subject_user_id == case.subject_user_id)
        )
    )
    upload_intents = list(
        await session.scalars(
            select(FileUploadIntent).where(FileUploadIntent.subject_user_id == case.subject_user_id)
        )
    )
    object_storage = {
        "stored_files": len(stored_files),
        "upload_intents": len(upload_intents),
    }
    if verify_object_storage:
        if storage is None:
            raise AppError(
                "DSR_STORAGE_UNAVAILABLE",
                "Private object storage is required for DSR inventory",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        for stored_file in stored_files:
            try:
                observed = await storage.stat(stored_file.storage_key)
            except StorageObjectNotFound:
                raise _conflict(
                    "DSR_STORAGE_OBJECT_MISSING",
                    "A managed object is missing from private storage",
                ) from None
            except StorageUnavailable:
                raise AppError(
                    "DSR_STORAGE_UNAVAILABLE",
                    "Private object storage is unavailable",
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                ) from None
            if (
                observed.size_bytes != stored_file.size_bytes
                or observed.checksum_sha256.lower() != stored_file.checksum_sha256.lower()
            ):
                raise _conflict(
                    "DSR_STORAGE_OBJECT_MISMATCH",
                    "Managed object metadata does not match the database inventory",
                )
        object_storage["objects_verified"] = len(stored_files)
        pending_objects_verified = 0
        for intent in upload_intents:
            if intent.status != UploadIntentStatus.PENDING.value:
                continue
            try:
                observed = await storage.stat(intent.object_key)
            except StorageObjectNotFound:
                continue
            except StorageUnavailable:
                raise AppError(
                    "DSR_STORAGE_UNAVAILABLE",
                    "Private object storage is unavailable",
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                ) from None
            if (
                observed.size_bytes != intent.declared_size_bytes
                or observed.checksum_sha256.lower() != intent.declared_sha256.lower()
            ):
                raise _conflict(
                    "DSR_STORAGE_OBJECT_MISMATCH",
                    "Pending object metadata does not match the database inventory",
                )
            pending_objects_verified += 1
        object_storage["pending_objects_verified"] = pending_objects_verified
    if audit_access:
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="privacy.dsr.inventory_read",
            entity_type="data_subject_request",
            entity_id=str(case.id),
            metadata={
                "database_record_count": sum(database.values()),
                "object_record_count": len(stored_files) + len(upload_intents),
            },
        )
    return {"database": database, "object_storage": object_storage}


def _allowed_dispositions(request_type: str) -> set[DataSubjectDisposition]:
    return {
        DataSubjectRequestType.ACCESS.value: {
            DataSubjectDisposition.PROVIDED,
            DataSubjectDisposition.NOT_FOUND,
            DataSubjectDisposition.RETAINED_EXCEPTION,
        },
        DataSubjectRequestType.RECTIFICATION.value: {
            DataSubjectDisposition.RECTIFIED,
            DataSubjectDisposition.NOT_FOUND,
            DataSubjectDisposition.RETAINED_EXCEPTION,
        },
        DataSubjectRequestType.ERASURE.value: {
            DataSubjectDisposition.ERASED,
            DataSubjectDisposition.NOT_FOUND,
            DataSubjectDisposition.RETAINED_EXCEPTION,
        },
    }[request_type]


async def record_location_assessment(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    request_id: UUID,
    location: DataSubjectLocation,
    disposition: DataSubjectDisposition,
    evidence_reference: str,
    exception_reference: str | None,
    external_record_count: int | None,
    client_request_id: UUID,
    approved_exception_references: set[str],
    storage: StorageProvider | None = None,
) -> DataSubjectLocationAssessment:
    await require_active_admin(session, actor_user_id)
    case = await session.scalar(
        select(DataSubjectRequest).where(DataSubjectRequest.id == request_id).with_for_update()
    )
    if case is None:
        raise AppError(
            "DATA_SUBJECT_REQUEST_NOT_FOUND",
            "Data-subject request was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if case.status != DataSubjectRequestStatus.IDENTITY_VERIFIED.value:
        raise _conflict("DSR_NOT_ASSESSABLE", "Request is not awaiting assessments")
    if disposition not in _allowed_dispositions(case.request_type):
        raise _conflict(
            "DSR_DISPOSITION_MISMATCH",
            "Assessment disposition does not match the requested right",
        )
    if not evidence_reference.strip():
        raise AppError(
            "DSR_EVIDENCE_REQUIRED",
            "A non-sensitive evidence reference is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if disposition is DataSubjectDisposition.RETAINED_EXCEPTION:
        if not exception_reference or exception_reference not in approved_exception_references:
            raise _conflict(
                "DSR_EXCEPTION_NOT_APPROVED",
                "Retained data requires a configured approved exception reference",
            )
    elif exception_reference is not None:
        raise _conflict(
            "DSR_EXCEPTION_NOT_APPLICABLE",
            "Exception reference is valid only for retained data",
        )

    if (
        location in {DataSubjectLocation.DATABASE, DataSubjectLocation.OBJECT_STORAGE}
        and external_record_count is not None
    ):
        raise AppError(
            "DSR_EXTERNAL_COUNT_NOT_APPLICABLE",
            "Database and object-storage counts are computed by the system",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    inventory = await data_subject_inventory(
        session,
        actor_user_id=actor_user_id,
        request_id=request_id,
        storage=storage,
        verify_object_storage=location is DataSubjectLocation.OBJECT_STORAGE,
    )
    if location is DataSubjectLocation.DATABASE:
        counts = inventory["database"]
    elif location is DataSubjectLocation.OBJECT_STORAGE:
        counts = {
            key: value
            for key, value in inventory["object_storage"].items()
            if key not in {"objects_verified", "pending_objects_verified"}
        }
    else:
        if external_record_count is None or external_record_count < 0:
            raise AppError(
                "DSR_EXTERNAL_COUNT_REQUIRED",
                "External location assessment requires a nonnegative record count",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        counts = {"operator_verified_records": external_record_count}
    record_count = sum(counts.values())
    if disposition is DataSubjectDisposition.NOT_FOUND and record_count != 0:
        raise _conflict("DSR_RECORDS_EXIST", "Not-found disposition conflicts with inventory")
    if (
        case.request_type == DataSubjectRequestType.ERASURE.value
        and disposition is DataSubjectDisposition.ERASED
        and record_count != 0
    ):
        raise _conflict(
            "DSR_RECORDS_REMAIN",
            "Erasure cannot be recorded while the system inventory still finds records",
        )
    document = {
        "actor_user_id": str(actor_user_id),
        "client_request_id": str(client_request_id),
        "request_id": str(request_id),
        "location": location.value,
        "disposition": disposition.value,
        "record_count": record_count,
        "data_class_counts": counts,
        "evidence_reference": evidence_reference.strip(),
        "exception_reference": exception_reference,
    }
    fingerprint = _fingerprint(document)
    existing = await session.scalar(
        select(DataSubjectLocationAssessment).where(
            DataSubjectLocationAssessment.request_id == request_id,
            DataSubjectLocationAssessment.location == location.value,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise _conflict(
                "DSR_ASSESSMENT_CONFLICT",
                "Location already has a different immutable assessment",
            )
        return existing
    assessment = DataSubjectLocationAssessment(
        request_id=request_id,
        location=location.value,
        disposition=disposition.value,
        record_count=record_count,
        data_class_counts=counts,
        evidence_reference=evidence_reference.strip(),
        exception_reference=exception_reference,
        assessed_by_user_id=actor_user_id,
        client_request_id=client_request_id,
        request_fingerprint=fingerprint,
    )
    try:
        async with session.begin_nested():
            session.add(assessment)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(DataSubjectLocationAssessment).where(
                DataSubjectLocationAssessment.request_id == request_id,
                DataSubjectLocationAssessment.location == location.value,
            )
        )
        if existing is None or existing.request_fingerprint != fingerprint:
            raise _conflict(
                "DSR_ASSESSMENT_CONFLICT",
                "Location assessment conflicts with accepted evidence",
            ) from None
        return existing
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="privacy.dsr.location_assessed",
        entity_type="data_subject_request",
        entity_id=str(request_id),
        metadata={
            "location": location.value,
            "disposition": disposition.value,
            "record_count": record_count,
        },
    )
    return assessment


async def complete_data_subject_request(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    request_id: UUID,
    storage: StorageProvider,
) -> DataSubjectRequest:
    await require_active_admin(session, actor_user_id)
    case = await session.scalar(
        select(DataSubjectRequest).where(DataSubjectRequest.id == request_id).with_for_update()
    )
    if case is None:
        raise AppError(
            "DATA_SUBJECT_REQUEST_NOT_FOUND",
            "Data-subject request was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if case.status == DataSubjectRequestStatus.COMPLETED.value:
        return case
    if case.status != DataSubjectRequestStatus.IDENTITY_VERIFIED.value:
        raise _conflict("DSR_NOT_COMPLETABLE", "Request is not ready for completion")
    assessments = list(
        await session.scalars(
            select(DataSubjectLocationAssessment).where(
                DataSubjectLocationAssessment.request_id == request_id
            )
        )
    )
    locations = {assessment.location for assessment in assessments}
    missing = sorted(
        location.value for location in _ALL_LOCATIONS if location.value not in locations
    )
    if missing:
        raise AppError(
            "DSR_LOCATIONS_INCOMPLETE",
            "Every data location must have immutable evidence before completion",
            status_code=status.HTTP_409_CONFLICT,
            details={"missing_locations": missing},
        )
    inventory = await data_subject_inventory(
        session,
        actor_user_id=actor_user_id,
        request_id=request_id,
        storage=storage,
        verify_object_storage=True,
    )
    current_system_counts = {
        DataSubjectLocation.DATABASE.value: sum(inventory["database"].values()),
        DataSubjectLocation.OBJECT_STORAGE.value: sum(
            count
            for name, count in inventory["object_storage"].items()
            if name not in {"objects_verified", "pending_objects_verified"}
        ),
    }
    invalid_system_claims = sorted(
        assessment.location
        for assessment in assessments
        if assessment.location in current_system_counts
        and assessment.disposition
        in {
            DataSubjectDisposition.ERASED.value,
            DataSubjectDisposition.NOT_FOUND.value,
        }
        and current_system_counts[assessment.location] != 0
    )
    if invalid_system_claims:
        raise AppError(
            "DSR_SYSTEM_INVENTORY_CHANGED",
            "System-controlled data changed after assessment and must be reassessed",
            status_code=status.HTTP_409_CONFLICT,
            details={"invalid_locations": invalid_system_claims},
        )
    if case.request_type == DataSubjectRequestType.ERASURE.value:
        invalid = sorted(
            assessment.location
            for assessment in assessments
            if assessment.disposition == DataSubjectDisposition.ERASED.value
            and assessment.record_count != 0
        )
        if invalid:
            raise AppError(
                "DSR_ERASURE_EVIDENCE_INVALID",
                "Erasure completion requires zero-count evidence for every erased location",
                status_code=status.HTTP_409_CONFLICT,
                details={"invalid_locations": invalid},
            )
    case.status = DataSubjectRequestStatus.COMPLETED.value
    case.completed_at = datetime.now(UTC)
    case.completed_by_user_id = actor_user_id
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="privacy.dsr.completed",
        entity_type="data_subject_request",
        entity_id=str(case.id),
        metadata={
            "request_type": case.request_type,
            "locations_assessed": len(locations),
        },
    )
    return case

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_organization,
    create_test_user,
)
from sqlalchemy import func, select
from test_driver_person_payee_onboarding import (
    PASSWORD,
    _application,
    _complete_admin_review,
    _person_payee_payload,
    _register,
    _seed_clean_kyc_files,
)

from app.core.errors import AppError
from app.jobs.vehicle_approvals import sweep_vehicle_approval_expiries
from app.models.driver import DriverProfile
from app.models.kyc import VehicleEvidenceReviewDecision, VehicleEvidenceSubmission
from app.models.stored_file import FileScanStatus, FileUploadIntent, StoredFile
from app.models.user import UserRole
from app.models.vehicle import Vehicle
from app.schemas.driver_onboarding import (
    ApplicantVehicleSubmissionCreate,
    VehicleReviewDecisionCreate,
)
from app.schemas.trips import TripStartRequest
from app.services.trips import start_driver_trip
from app.services.vehicle_onboarding import (
    review_application_vehicle,
    submit_application_vehicle,
)


def _approved_applicant(db_client, db_sessionmaker, settings, *, suffix: str):
    token, _ = _register(db_client, db_sessionmaker, settings, suffix=suffix)
    email = f"person-payee-{suffix}@example.com"
    application = _application(db_sessionmaker, email=email)
    files = _seed_clean_kyc_files(db_sessionmaker, email=email)
    submitted = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json=_person_payee_payload(token, files),
    )
    assert submitted.status_code == 201
    admin = create_test_user(
        db_sessionmaker,
        email=f"vehicle-{suffix}-admin@example.com",
        password=PASSWORD,
    )
    _complete_admin_review(
        db_client,
        db_sessionmaker,
        admin=admin,
        application=application,
        files=files,
    )
    decision = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "decision": "approved",
            "reason_code": "complete_current_evidence",
            "identity_match_confirmed": True,
            "bank_account_match_confirmed": True,
            "documents_readable_confirmed": True,
        },
    )
    assert decision.status_code == 200
    return token, application, admin


def _seed_vehicle_files(db_sessionmaker, *, application, suffix: str) -> dict[str, UUID]:
    async def seed() -> dict[str, UUID]:
        async with db_sessionmaker() as session:
            result: dict[str, UUID] = {}
            for index, name in enumerate(("registration", "insurance", "vehicle_photo"), 4):
                intent = FileUploadIntent(
                    organization_id=None,
                    subject_user_id=application.user_id,
                    uploader_user_id=application.user_id,
                    client_request_id=uuid4(),
                    request_fingerprint=f"{index}" * 64,
                    purpose="vehicle_evidence",
                    original_filename=f"{suffix}-{name}.png",
                    declared_content_type="image/png",
                    declared_size_bytes=68,
                    declared_sha256=f"{index}" * 64,
                    object_key=f"unconfirmed/subject/{application.user_id}/{uuid4()}",
                    expires_at=datetime.now(UTC),
                    status="confirmed",
                )
                session.add(intent)
                await session.flush()
                stored = StoredFile(
                    upload_intent_id=intent.id,
                    organization_id=None,
                    subject_user_id=application.user_id,
                    uploader_user_id=application.user_id,
                    purpose="vehicle_evidence",
                    original_filename=f"{suffix}-{name}.png",
                    storage_key=f"managed/subject/{application.user_id}/{intent.id}",
                    content_type="image/png",
                    size_bytes=68,
                    checksum_sha256=f"{index}" * 64,
                    scan_status=FileScanStatus.CLEAN,
                )
                session.add(stored)
                await session.flush()
                result[name] = stored.id
            await session.commit()
            return result

    return asyncio.run(seed())


def _vehicle_payload(token: str, files: dict[str, UUID], **changes):
    payload = {
        "application_access_token": token,
        "client_request_id": str(uuid4()),
        "plate_number": "ABC-123-XY",
        "plate_country_code": "NG",
        "vehicle_type": "car",
        "make": "Toyota",
        "model": "Corolla",
        "year": 2021,
        "color": "White",
        "registration_file_id": str(files["registration"]),
        "insurance_file_id": str(files["insurance"]),
        "vehicle_photo_file_id": str(files["vehicle_photo"]),
    }
    payload.update(changes)
    return payload


def _review_files(db_client, *, admin, submission_id: str, files: dict[str, UUID]) -> None:
    for file_id in files.values():
        response = db_client.post(
            f"/api/v1/admin/files/{file_id}/download",
            headers=auth_headers(db_client, admin.email, PASSWORD),
            json={
                "purpose": "kyc_review",
                "reason": f"vehicle_approval:{submission_id}",
            },
        )
        assert response.status_code == 200


def _decision_path(application_id, vehicle_id, submission_id) -> str:
    return (
        f"/api/v1/admin/driver-applications/{application_id}/vehicles/{vehicle_id}/"
        f"submissions/{submission_id}/decision"
    )


def _approve_vehicle(db_client, *, application, admin, submitted, files):
    _review_files(
        db_client,
        admin=admin,
        submission_id=submitted["submission_id"],
        files=files,
    )
    response = db_client.post(
        _decision_path(application.id, submitted["vehicle_id"], submitted["submission_id"]),
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "decision": "approved",
            "reason_code": "complete_current_evidence",
            "owner_match_confirmed": True,
            "vehicle_identity_confirmed": True,
            "roadworthy_confirmed": True,
            "pilot_car_confirmed": True,
            "documents_readable_confirmed": True,
            "valid_until": "2099-01-01T00:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_vehicle_approval_denies_cross_owner_and_self_approval(
    db_client, db_sessionmaker, settings
) -> None:
    token, application, admin = _approved_applicant(
        db_client, db_sessionmaker, settings, suffix="owner-a"
    )
    files = _seed_vehicle_files(db_sessionmaker, application=application, suffix="owner-a")
    submitted = db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle", json=_vehicle_payload(token, files)
    )
    assert submitted.status_code == 201

    other_token, other_application, _ = _approved_applicant(
        db_client, db_sessionmaker, settings, suffix="owner-b"
    )
    other_files = _seed_vehicle_files(
        db_sessionmaker, application=other_application, suffix="owner-b"
    )
    cross_owner = db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle",
        json=_vehicle_payload(
            other_token,
            other_files,
            vehicle_id=submitted.json()["vehicle_id"],
        ),
    )
    assert cross_owner.status_code == 404
    assert cross_owner.json()["error"]["code"] == "VEHICLE_NOT_FOUND"

    driver = create_test_user(
        db_sessionmaker,
        email="vehicle-self-approver@example.com",
        role=UserRole.DRIVER,
    )
    self_approval = db_client.post(
        _decision_path(
            application.id,
            submitted.json()["vehicle_id"],
            submitted.json()["submission_id"],
        ),
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "decision": "rejected",
            "reason_code": "owner_mismatch",
        },
    )
    assert self_approval.status_code == 403
    assert self_approval.json()["error"]["code"] == "FORBIDDEN_ROLE"
    assert admin.id is not None


def test_vehicle_approval_fails_closed_for_unsafe_and_unread_evidence(
    db_client, db_sessionmaker, settings
) -> None:
    token, application, admin = _approved_applicant(
        db_client, db_sessionmaker, settings, suffix="unsafe"
    )
    files = _seed_vehicle_files(db_sessionmaker, application=application, suffix="unsafe")

    async def mark_pending() -> None:
        async with db_sessionmaker() as session:
            stored = await session.get(StoredFile, files["insurance"])
            assert stored is not None
            stored.scan_status = FileScanStatus.PENDING.value
            await session.commit()

    asyncio.run(mark_pending())
    unsafe = db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle", json=_vehicle_payload(token, files)
    )
    assert unsafe.status_code == 409
    assert unsafe.json()["error"]["code"] == "KYC_DOCUMENT_NOT_CLEARED"

    async def mark_clean() -> None:
        async with db_sessionmaker() as session:
            stored = await session.get(StoredFile, files["insurance"])
            assert stored is not None
            stored.scan_status = FileScanStatus.CLEAN.value
            await session.commit()

    asyncio.run(mark_clean())
    payload = _vehicle_payload(token, files)
    submitted = db_client.post("/api/v1/auth/driver-onboarding/vehicle", json=payload)
    assert submitted.status_code == 201
    unread = db_client.post(
        _decision_path(
            application.id,
            submitted.json()["vehicle_id"],
            submitted.json()["submission_id"],
        ),
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "decision": "approved",
            "reason_code": "complete_current_evidence",
            "owner_match_confirmed": True,
            "vehicle_identity_confirmed": True,
            "roadworthy_confirmed": True,
            "pilot_car_confirmed": True,
            "documents_readable_confirmed": True,
            "valid_until": "2099-01-01T00:00:00Z",
        },
    )
    assert unread.status_code == 409
    assert unread.json()["error"]["code"] == "VEHICLE_REVIEW_EVIDENCE_INCOMPLETE"


def test_material_vehicle_revision_invalidates_approval_without_rewriting_history(
    db_client, db_sessionmaker, settings
) -> None:
    token, application, admin = _approved_applicant(
        db_client, db_sessionmaker, settings, suffix="revision"
    )
    files = _seed_vehicle_files(db_sessionmaker, application=application, suffix="revision")
    submitted = db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle", json=_vehicle_payload(token, files)
    ).json()
    _approve_vehicle(
        db_client,
        application=application,
        admin=admin,
        submitted=submitted,
        files=files,
    )
    revised = db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle",
        json=_vehicle_payload(
            token,
            files,
            vehicle_id=submitted["vehicle_id"],
            plate_number="XYZ-999-ZZ",
        ),
    )
    assert revised.status_code == 201, revised.text
    assert revised.json()["status"] == "pending_review"
    assert revised.json()["version"] == 2

    async def inspect() -> tuple[list[str], int, str, str]:
        async with db_sessionmaker() as session:
            statuses = list(
                (
                    await session.scalars(
                        select(VehicleEvidenceSubmission.status).order_by(
                            VehicleEvidenceSubmission.version
                        )
                    )
                ).all()
            )
            decisions = int(
                await session.scalar(select(func.count(VehicleEvidenceReviewDecision.id))) or 0
            )
            profile = await session.get(DriverProfile, application.driver_profile_id)
            vehicle = await session.get(Vehicle, UUID(submitted["vehicle_id"]))
            assert profile is not None and vehicle is not None
            return statuses, decisions, profile.onboarding_status, vehicle.status

    assert asyncio.run(inspect()) == (["approved", "pending_review"], 1, "pending", "pending")


def test_rejected_vehicle_can_resubmit_as_a_new_immutable_revision(
    db_client, db_sessionmaker, settings
) -> None:
    token, application, admin = _approved_applicant(
        db_client, db_sessionmaker, settings, suffix="resubmit"
    )
    files = _seed_vehicle_files(db_sessionmaker, application=application, suffix="resubmit")
    submitted = db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle", json=_vehicle_payload(token, files)
    ).json()
    rejected = db_client.post(
        _decision_path(application.id, submitted["vehicle_id"], submitted["submission_id"]),
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "decision": "rejected",
            "reason_code": "not_roadworthy",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    resubmitted = db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle",
        json=_vehicle_payload(
            token,
            files,
            vehicle_id=submitted["vehicle_id"],
            color="Silver",
        ),
    )
    assert resubmitted.status_code == 201
    assert (resubmitted.json()["version"], resubmitted.json()["status"]) == (
        2,
        "pending_review",
    )

    async def statuses() -> list[str]:
        async with db_sessionmaker() as session:
            return list(
                (
                    await session.scalars(
                        select(VehicleEvidenceSubmission.status).order_by(
                            VehicleEvidenceSubmission.version
                        )
                    )
                ).all()
            )

    assert asyncio.run(statuses()) == ["rejected", "pending_review"]


def test_vehicle_eligibility_opens_and_expiry_closes_assignment_and_trip(
    db_client, db_sessionmaker, settings
) -> None:
    token, application, admin = _approved_applicant(
        db_client, db_sessionmaker, settings, suffix="eligibility"
    )
    files = _seed_vehicle_files(db_sessionmaker, application=application, suffix="eligibility")
    submitted = db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle", json=_vehicle_payload(token, files)
    ).json()
    approved = _approve_vehicle(
        db_client,
        application=application,
        admin=admin,
        submitted=submitted,
        files=files,
    )
    assert approved["status"] == "approved"

    advertiser = create_test_user(
        db_sessionmaker,
        email="vehicle-eligibility-advertiser@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status="active",
        start_at=datetime(2020, 1, 1, tzinfo=UTC),
        end_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=application.driver_profile_id,
        vehicle_id=UUID(submitted["vehicle_id"]),
        assigned_by_user_id=admin.id,
        assignment_status="active",
        activated_at=datetime.now(UTC),
    )
    expired = db_client.post(
        _decision_path(
            application.id,
            submitted["vehicle_id"],
            submitted["submission_id"],
        ),
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "decision": "expired",
            "reason_code": "expired_evidence",
        },
    )
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"

    async def start() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as raised:
                await start_driver_trip(
                    session,
                    user_id=application.user_id,
                    payload=TripStartRequest(assignment_id=assignment.id, metadata={}),
                    settings=settings,
                )
            assert raised.value.code == "DRIVER_PROFILE_NOT_ACTIVE"

    asyncio.run(start())


def test_vehicle_submission_and_decision_exact_retries_converge_changed_retries_conflict(
    db_client, db_sessionmaker, settings
) -> None:
    token, application, admin = _approved_applicant(
        db_client, db_sessionmaker, settings, suffix="retries"
    )
    files = _seed_vehicle_files(db_sessionmaker, application=application, suffix="retries")
    request_id = str(uuid4())
    payload = _vehicle_payload(token, files, client_request_id=request_id)
    first = db_client.post("/api/v1/auth/driver-onboarding/vehicle", json=payload)
    exact = db_client.post("/api/v1/auth/driver-onboarding/vehicle", json=payload)
    assert first.status_code == exact.status_code == 201
    assert first.json()["submission_id"] == exact.json()["submission_id"]
    changed = db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle",
        json={**payload, "color": "Black"},
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "VEHICLE_SUBMISSION_RETRY_CONFLICT"

    submitted = first.json()
    _review_files(
        db_client,
        admin=admin,
        submission_id=submitted["submission_id"],
        files=files,
    )
    decision_request_id = str(uuid4())
    decision = {
        "client_request_id": decision_request_id,
        "decision": "approved",
        "reason_code": "complete_current_evidence",
        "owner_match_confirmed": True,
        "vehicle_identity_confirmed": True,
        "roadworthy_confirmed": True,
        "pilot_car_confirmed": True,
        "documents_readable_confirmed": True,
        "valid_until": "2099-01-01T00:00:00Z",
    }
    path = _decision_path(application.id, submitted["vehicle_id"], submitted["submission_id"])
    headers = auth_headers(db_client, admin.email, PASSWORD)
    approved = db_client.post(path, headers=headers, json=decision)
    replay = db_client.post(path, headers=headers, json=decision)
    assert approved.status_code == replay.status_code == 200
    conflict = db_client.post(
        path,
        headers=headers,
        json={**decision, "valid_until": "2098-01-01T00:00:00Z"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "VEHICLE_DECISION_RETRY_CONFLICT"


def test_vehicle_expiry_worker_appends_history_and_closes_eligibility(
    db_client, db_sessionmaker, settings
) -> None:
    token, application, admin = _approved_applicant(
        db_client, db_sessionmaker, settings, suffix="expiry-worker"
    )
    files = _seed_vehicle_files(db_sessionmaker, application=application, suffix="expiry-worker")
    submitted = db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle", json=_vehicle_payload(token, files)
    ).json()
    _review_files(
        db_client,
        admin=admin,
        submission_id=submitted["submission_id"],
        files=files,
    )
    expires = datetime.now(UTC) + timedelta(seconds=2)
    response = db_client.post(
        _decision_path(application.id, submitted["vehicle_id"], submitted["submission_id"]),
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "decision": "approved",
            "reason_code": "complete_current_evidence",
            "owner_match_confirmed": True,
            "vehicle_identity_confirmed": True,
            "roadworthy_confirmed": True,
            "pilot_car_confirmed": True,
            "documents_readable_confirmed": True,
            "valid_until": expires.isoformat(),
        },
    )
    assert response.status_code == 200

    async def sweep_and_inspect() -> tuple[dict[str, int | float], list[str], str, str]:
        await asyncio.sleep(2.1)
        result = await sweep_vehicle_approval_expiries({"sessionmaker": db_sessionmaker})
        async with db_sessionmaker() as session:
            decisions = list(
                (
                    await session.scalars(
                        select(VehicleEvidenceReviewDecision.decision).order_by(
                            VehicleEvidenceReviewDecision.sequence
                        )
                    )
                ).all()
            )
            profile = await session.get(DriverProfile, application.driver_profile_id)
            vehicle = await session.get(Vehicle, UUID(submitted["vehicle_id"]))
            assert profile is not None and vehicle is not None
            return result, decisions, profile.onboarding_status, vehicle.status

    result, decisions, profile_status, vehicle_status = asyncio.run(sweep_and_inspect())
    assert result["expired"] == 1
    assert decisions == ["approved", "expired"]
    assert (profile_status, vehicle_status) == ("pending", "pending")


def test_postgres_concurrent_vehicle_revision_and_expiry_serialize(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    token, application, admin = _approved_applicant(
        postgis_db_client, postgis_db_sessionmaker, settings, suffix="pg-race"
    )
    files = _seed_vehicle_files(postgis_db_sessionmaker, application=application, suffix="pg-race")
    submitted = postgis_db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle", json=_vehicle_payload(token, files)
    ).json()
    _approve_vehicle(
        postgis_db_client,
        application=application,
        admin=admin,
        submitted=submitted,
        files=files,
    )
    revision_payload = ApplicantVehicleSubmissionCreate.model_validate(
        _vehicle_payload(
            token,
            files,
            vehicle_id=submitted["vehicle_id"],
            color="Silver",
        )
    )
    expiry_payload = VehicleReviewDecisionCreate.model_validate(
        {
            "client_request_id": str(uuid4()),
            "decision": "expired",
            "reason_code": "expired_evidence",
        }
    )

    async def revise() -> str:
        async with postgis_db_sessionmaker() as session:
            view = await submit_application_vehicle(
                session, payload=revision_payload, settings=settings
            )
            await session.commit()
            assert view.submission is not None
            return "revised"

    async def expire() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await review_application_vehicle(
                    session,
                    application_id=application.id,
                    vehicle_id=UUID(submitted["vehicle_id"]),
                    submission_id=UUID(submitted["submission_id"]),
                    actor_user_id=admin.id,
                    payload=expiry_payload,
                )
                await session.commit()
                return "expired"
            except AppError as error:
                await session.rollback()
                assert error.code == "VEHICLE_REVISION_STALE"
                return "stale"

    async def exercise() -> tuple[list[str], list[tuple[int, str]], str, str]:
        outcomes = await asyncio.gather(revise(), expire())
        async with postgis_db_sessionmaker() as session:
            revisions = list(
                (
                    await session.execute(
                        select(VehicleEvidenceSubmission.version, VehicleEvidenceSubmission.status)
                        .where(
                            VehicleEvidenceSubmission.vehicle_id == UUID(submitted["vehicle_id"])
                        )
                        .order_by(VehicleEvidenceSubmission.version)
                    )
                ).all()
            )
            profile = await session.get(DriverProfile, application.driver_profile_id)
            vehicle = await session.get(Vehicle, UUID(submitted["vehicle_id"]))
            assert profile is not None and vehicle is not None
            return outcomes, revisions, profile.onboarding_status, vehicle.status

    outcomes, revisions, profile_status, vehicle_status = asyncio.run(exercise())
    assert "revised" in outcomes
    assert revisions[-1] == (2, "pending_review")
    assert (profile_status, vehicle_status) == ("pending", "pending")

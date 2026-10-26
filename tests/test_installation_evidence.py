import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_driver_profile,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import func, select
from test_campaign_assignments import (
    PASSWORD,
    create_assignment_ready_graph,
    post_assignment,
)
from test_trips import create_trip_ready_graph, start_trip

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.installation_evidence import (
    InstallationEvidenceStatus,
    InstallationEvidenceSubmission,
)
from app.models.stored_file import (
    FilePurpose,
    FileScanStatus,
    FileUploadIntent,
    StoredFile,
    UploadIntentStatus,
)
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.schemas.installation_evidence import InstallationEvidenceCreate
from app.services.installation_evidence import (
    INSTALLATION_EVIDENCE_VIEWS,
    submit_installation_evidence,
)


def create_clean_evidence_file(db_sessionmaker, *, user_id: UUID) -> UUID:
    async def create() -> UUID:
        async with db_sessionmaker() as session:
            file_id = uuid4()
            intent = FileUploadIntent(
                subject_user_id=user_id,
                uploader_user_id=user_id,
                client_request_id=uuid4(),
                request_fingerprint="a" * 64,
                purpose=FilePurpose.INSTALLATION_EVIDENCE.value,
                original_filename="installation-evidence.png",
                declared_content_type="image/png",
                declared_size_bytes=128,
                declared_sha256="b" * 64,
                object_key=f"test-intents/{file_id}",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                status=UploadIntentStatus.CONFIRMED.value,
            )
            session.add(intent)
            await session.flush()
            session.add(
                StoredFile(
                    id=file_id,
                    upload_intent_id=intent.id,
                    subject_user_id=user_id,
                    uploader_user_id=user_id,
                    purpose=FilePurpose.INSTALLATION_EVIDENCE.value,
                    original_filename="installation-evidence.png",
                    storage_key=f"test-files/{file_id}",
                    content_type="image/png",
                    size_bytes=128,
                    checksum_sha256="b" * 64,
                    scan_status=FileScanStatus.CLEAN.value,
                    actual_content_type="image/png",
                    scan_attempts=1,
                    scanned_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()
            return file_id

    return asyncio.run(create())


def accepted_assignment(db_client, db_sessionmaker, *, suffix: str):
    admin, campaign, driver, profile, vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        advertiser_email=f"evidence-advertiser-{suffix}@example.com",
        driver_email=f"evidence-driver-{suffix}@example.com",
        plate_number=f"EVD-{suffix.upper()}",
    )
    offered = post_assignment(db_client, campaign, profile, vehicle)
    assert offered.status_code == 201, offered.text
    assignment_id = offered.json()["id"]
    accepted = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json={"metadata": {}},
    )
    assert accepted.status_code == 200, accepted.text
    return admin, driver, vehicle, assignment_id


def evidence_payload(db_sessionmaker, *, driver_id: UUID) -> dict:
    return {
        "client_request_id": str(uuid4()),
        "device_id": str(uuid4()),
        "captured_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        "photos": [
            {
                "view": view,
                "stored_file_id": str(
                    create_clean_evidence_file(db_sessionmaker, user_id=driver_id)
                ),
            }
            for view in INSTALLATION_EVIDENCE_VIEWS
        ],
        "metadata": {"source": "synthetic-test"},
    }


def test_history_requires_existing_owned_assignment_before_read_audit(
    db_client, db_sessionmaker
) -> None:
    admin, campaign, driver, profile, vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        advertiser_email="evidence-advertiser-history@example.com",
        driver_email="evidence-driver-history-owner@example.com",
        plate_number="EVD-HISTORY-OWNER",
    )
    offered = post_assignment(db_client, campaign, profile, vehicle)
    assignment_id = offered.json()["id"]
    accepted = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json={"metadata": {}},
    )
    assert accepted.status_code == 200
    other_driver = create_test_user(
        db_sessionmaker,
        email="evidence-driver-history-other@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    other_profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=other_driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
        license_number="EVD-HISTORY-OTHER",
    )
    other_vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=other_profile.id,
        plate_number="EVD-HISTORY-OTHER",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    other_assignment = post_assignment(db_client, campaign, other_profile, other_vehicle)
    assert other_assignment.status_code == 201
    other_assignment_id = other_assignment.json()["id"]
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)
    driver_headers = auth_headers(db_client, driver.email, PASSWORD)
    missing_id = uuid4()

    async def read_audit_count() -> int:
        async with db_sessionmaker() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(
                        AuditEvent.action.in_(
                            {
                                "installation_evidence.read",
                                "installation_evidence.history_read",
                            }
                        )
                    )
                )
                or 0
            )

    before = asyncio.run(read_audit_count())
    missing_admin = db_client.get(
        f"/api/v1/admin/campaign-assignments/{missing_id}/installation-evidence",
        headers=admin_headers,
    )
    missing_driver = db_client.get(
        f"/api/v1/driver/campaign-assignments/{missing_id}/installation-evidence",
        headers=driver_headers,
    )
    non_owner = db_client.get(
        f"/api/v1/driver/campaign-assignments/{other_assignment_id}/installation-evidence",
        headers=driver_headers,
    )

    for response in (missing_admin, missing_driver, non_owner):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CAMPAIGN_ASSIGNMENT_NOT_FOUND"
    assert asyncio.run(read_audit_count()) == before

    owned_driver = db_client.get(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence",
        headers=driver_headers,
    )
    existing_admin = db_client.get(
        f"/api/v1/admin/campaign-assignments/{other_assignment_id}/installation-evidence",
        headers=admin_headers,
    )
    assert owned_driver.status_code == existing_admin.status_code == 200
    assert (
        owned_driver.json()
        == existing_admin.json()
        == {
            "items": [],
            "total": None,
            "limit": None,
            "offset": None,
        }
    )
    assert asyncio.run(read_audit_count()) == before + 2


def set_assignment_active(db_sessionmaker, assignment_id: UUID) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, assignment_id)
            assert assignment is not None
            assignment.status = CampaignAssignmentStatus.ACTIVE.value
            assignment.activated_at = datetime.now(UTC)
            await session.commit()

    asyncio.run(update())


def test_driver_admin_evidence_flow_is_bound_and_idempotent(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    admin, driver, vehicle, assignment_id = accepted_assignment(
        db_client, db_sessionmaker, suffix="flow"
    )
    payload = evidence_payload(db_sessionmaker, driver_id=driver.id)

    submitted = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json=payload,
    )
    assert submitted.status_code == 201, submitted.text
    body = submitted.json()
    assert body["assignment_id"] == assignment_id
    assert body["vehicle_id"] == str(vehicle.id)
    assert body["device_id"] == payload["device_id"]
    assert body["status"] == "pending_review"
    assert {photo["view"] for photo in body["photos"]} == set(INSTALLATION_EVIDENCE_VIEWS)

    duplicate = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json=payload,
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == body["id"]

    pending = db_client.get(
        "/api/v1/admin/installation-evidence/pending",
        headers=auth_headers(db_client, admin.email, PASSWORD),
    )
    assert pending.status_code == 200
    assert [item["id"] for item in pending.json()["items"]] == [body["id"]]

    approved = db_client.post(
        f"/api/v1/admin/installation-evidence/{body['id']}/approve",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"reason": "Synthetic review passed"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_until"] is not None


def test_distinct_submission_is_rejected_while_review_is_pending(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    _, driver, _, assignment_id_value = accepted_assignment(
        db_client, db_sessionmaker, suffix="pending-guard"
    )
    assignment_id = UUID(assignment_id_value)
    first_payload = InstallationEvidenceCreate.model_validate(
        evidence_payload(db_sessionmaker, driver_id=driver.id)
    )
    second_payload = InstallationEvidenceCreate.model_validate(
        evidence_payload(db_sessionmaker, driver_id=driver.id)
    )

    async def exercise() -> tuple[UUID, list[InstallationEvidenceSubmission]]:
        async with db_sessionmaker() as session:
            first = await submit_installation_evidence(
                session,
                actor_user_id=driver.id,
                actor_role="driver",
                assignment_id=assignment_id,
                payload=first_payload,
                settings=settings,
            )
            await session.commit()
            first_id = first.id

        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as caught:
                await submit_installation_evidence(
                    session,
                    actor_user_id=driver.id,
                    actor_role="driver",
                    assignment_id=assignment_id,
                    payload=second_payload,
                    settings=settings,
                )
            assert caught.value.code == "INSTALLATION_EVIDENCE_REVIEW_PENDING"
            assert caught.value.status_code == 409
            await session.rollback()

        async with db_sessionmaker() as session:
            rows = list(
                await session.scalars(
                    select(InstallationEvidenceSubmission).where(
                        InstallationEvidenceSubmission.assignment_id == assignment_id
                    )
                )
            )
            return first_id, rows

    first_id, rows = asyncio.run(exercise())
    assert [(row.id, row.client_request_id, row.status) for row in rows] == [
        (first_id, first_payload.client_request_id, InstallationEvidenceStatus.PENDING_REVIEW.value)
    ]


def test_future_capture_is_rejected_without_persisting_submission_or_audit(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    _, driver, _, assignment_id_value = accepted_assignment(
        db_client, db_sessionmaker, suffix="future-guard"
    )
    assignment_id = UUID(assignment_id_value)
    payload_data = evidence_payload(db_sessionmaker, driver_id=driver.id)
    payload_data["captured_at"] = datetime(2099, 1, 1, tzinfo=UTC).isoformat()
    payload = InstallationEvidenceCreate.model_validate(payload_data)

    async def exercise() -> tuple[int, int]:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as caught:
                await submit_installation_evidence(
                    session,
                    actor_user_id=driver.id,
                    actor_role="driver",
                    assignment_id=assignment_id,
                    payload=payload,
                    settings=settings,
                )
            assert caught.value.code == "INSTALLATION_EVIDENCE_CAPTURE_TIME_INVALID"
            assert caught.value.status_code == 422
            await session.rollback()

        async with db_sessionmaker() as session:
            submissions = int(
                await session.scalar(
                    select(func.count())
                    .select_from(InstallationEvidenceSubmission)
                    .where(InstallationEvidenceSubmission.assignment_id == assignment_id)
                )
                or 0
            )
            audits = int(
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "installation_evidence.submitted")
                )
                or 0
            )
            return submissions, audits

    assert asyncio.run(exercise()) == (0, 0)


def test_built_in_photo_rule_needs_no_settings_and_still_fails_closed(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    """REQ-208: five views, driver or admin, 7 days; no deployment switch to set first."""
    admin, driver, vehicle, assignment_id = accepted_assignment(
        db_client, db_sessionmaker, suffix="policy"
    )
    url = f"/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence"
    headers = auth_headers(db_client, driver.email, PASSWORD)

    short = evidence_payload(db_sessionmaker, driver_id=driver.id)
    short["photos"] = short["photos"][:4]
    missing_view = db_client.post(url, headers=headers, json=short)
    assert missing_view.status_code == 422, missing_view.text
    assert missing_view.json()["error"]["code"] == "INSTALLATION_EVIDENCE_VIEWS_INVALID"

    payload = evidence_payload(db_sessionmaker, driver_id=driver.id)
    payload["photos"][0]["stored_file_id"] = str(
        create_clean_evidence_file(db_sessionmaker, user_id=admin.id)
    )
    invalid = db_client.post(url, headers=headers, json=payload)
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "INSTALLATION_EVIDENCE_FILE_INVALID"

    payload = evidence_payload(db_sessionmaker, driver_id=driver.id)
    submitted = db_client.post(url, headers=headers, json=payload)
    assert submitted.status_code == 201, submitted.text
    approved = db_client.post(
        f"/api/v1/admin/installation-evidence/{submitted.json()['id']}/approve",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"reason": "Synthetic review passed"},
    )
    assert approved.status_code == 200, approved.text
    approved_at = datetime.fromisoformat(approved.json()["reviewed_at"])
    approved_until = datetime.fromisoformat(approved.json()["approved_until"])
    assert approved_until - approved_at == timedelta(days=7)


def test_trip_starts_with_weekly_photos_without_daily_configuration(db_client, db_sessionmaker):
    """A fresh database's ordinary trip authority needs only weekly photos."""
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    response = start_trip(db_client, assignment.id)
    assert response.status_code == 201, response.text
    assert "display_proof_id" not in response.json()


@pytest.mark.parametrize("photo_state", ["expired", "rejected", "missing"])
def test_trip_still_requires_current_approved_weekly_photos(
    db_client, db_sessionmaker, photo_state
):
    _, _, _, _, _, assignment = create_trip_ready_graph(
        db_sessionmaker, with_installation_evidence=photo_state != "missing"
    )

    async def change_photo_authority():
        async with db_sessionmaker() as session:
            evidence = await session.scalar(
                select(InstallationEvidenceSubmission).where(
                    InstallationEvidenceSubmission.assignment_id == assignment.id
                )
            )
            if photo_state == "expired":
                evidence.approved_until = datetime.now(UTC) - timedelta(seconds=1)
            elif photo_state == "rejected":
                evidence.status = "rejected"
                evidence.rejection_reason = "Photos need replacement"
                evidence.approved_until = None
            await session.commit()

    if photo_state != "missing":
        asyncio.run(change_photo_authority())
    response = start_trip(db_client, assignment.id)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] in {
        "APPROVED_INSTALLATION_EVIDENCE_REQUIRED",
        "INSTALLATION_EVIDENCE_EXPIRED",
    }


def test_installation_policy_has_only_weekly_rule(db_client, db_sessionmaker):
    driver = create_test_user(
        db_sessionmaker,
        email="weekly-policy@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    create_test_driver_profile(db_sessionmaker, user_id=driver.id)
    response = db_client.get(
        "/api/v1/driver/installation-evidence/policy",
        headers=auth_headers(db_client, driver.email, PASSWORD),
    )
    assert response.status_code == 200
    assert response.json() == {
        "required_views": ["front", "back", "left", "right", "close_up"],
        "evidence_validity_hours": 168,
    }

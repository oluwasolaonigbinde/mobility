import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from conftest import (
    auth_headers,
    create_test_driver_profile,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import delete, func, select
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
from app.models.evidence_verification import EvidenceVerification
from app.models.installation_evidence import DisplayProof
from app.models.stored_file import (
    FilePurpose,
    FileScanStatus,
    FileUploadIntent,
    StoredFile,
    UploadIntentStatus,
)
from app.models.trip import TripSession
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.schemas.installation_evidence import DisplayProofCreate
from app.services.installation_evidence import submit_display_proof


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


def configure_evidence_policy(settings) -> None:
    settings.installation_evidence_uploader_roles = "driver,admin"
    settings.installation_evidence_required_views = "front,close_up"
    settings.installation_evidence_validity_hours = 24
    settings.display_proof_challenge_ttl_seconds = 120
    settings.display_proof_validity_seconds = 3600


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
                "view": "front",
                "stored_file_id": str(
                    create_clean_evidence_file(db_sessionmaker, user_id=driver_id)
                ),
            },
            {
                "view": "close_up",
                "stored_file_id": str(
                    create_clean_evidence_file(db_sessionmaker, user_id=driver_id)
                ),
            },
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
    assert owned_driver.json() == existing_admin.json() == {"items": []}
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
    configure_evidence_policy(settings)
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
    assert {photo["view"] for photo in body["photos"]} == {"front", "close_up"}

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


def test_evidence_policy_absence_and_cross_driver_file_fail_closed(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    settings.installation_evidence_uploader_roles = ""
    settings.installation_evidence_required_views = ""
    settings.installation_evidence_validity_hours = None
    settings.display_proof_challenge_ttl_seconds = None
    settings.display_proof_validity_seconds = None
    admin, driver, vehicle, assignment_id = accepted_assignment(
        db_client, db_sessionmaker, suffix="policy"
    )
    payload = evidence_payload(db_sessionmaker, driver_id=driver.id)
    unavailable = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json=payload,
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "INSTALLATION_EVIDENCE_POLICY_UNAVAILABLE"

    configure_evidence_policy(settings)
    payload["client_request_id"] = str(uuid4())
    payload["photos"][0]["stored_file_id"] = str(
        create_clean_evidence_file(db_sessionmaker, user_id=admin.id)
    )
    invalid = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json=payload,
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "INSTALLATION_EVIDENCE_FILE_INVALID"


def test_display_proof_nonce_is_device_bound_fresh_and_one_use(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    configure_evidence_policy(settings)
    admin, driver, vehicle, assignment_id = accepted_assignment(
        db_client, db_sessionmaker, suffix="proof"
    )
    payload = evidence_payload(db_sessionmaker, driver_id=driver.id)
    submitted = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json=payload,
    )
    assert submitted.status_code == 201, submitted.text
    approved = db_client.post(
        f"/api/v1/admin/installation-evidence/{submitted.json()['id']}/approve",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"reason": "Synthetic review passed"},
    )
    assert approved.status_code == 200, approved.text
    set_assignment_active(db_sessionmaker, UUID(assignment_id))

    async def seed_recurring_challenge() -> UUID:
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, UUID(assignment_id))
            issued_at = datetime.now(UTC) - timedelta(minutes=1)
            source_trip = TripSession(
                assignment_id=assignment.id,
                campaign_id=assignment.campaign_id,
                driver_profile_id=assignment.driver_profile_id,
                vehicle_id=vehicle.id,
                started_by_user_id=driver.id,
                status="sealed",
                started_at=issued_at - timedelta(hours=1),
                ended_at=issued_at - timedelta(minutes=10),
                sealed_at=issued_at - timedelta(minutes=5),
                seal_reason="migration_backfill",
                trip_metadata={"synthetic": True},
            )
            session.add(source_trip)
            await session.flush()
            verification = EvidenceVerification(
                assignment_id=assignment.id,
                campaign_id=assignment.campaign_id,
                driver_profile_id=assignment.driver_profile_id,
                vehicle_id=vehicle.id,
                source_trip_session_id=source_trip.id,
                verification_type="high_earner_renewal",
                status="pending",
                due_at=issued_at + timedelta(hours=1),
                verification_metadata={"source": "synthetic-test"},
                issued_at=issued_at,
            )
            session.add(verification)
            await session.commit()
            return verification.id

    verification_id = asyncio.run(seed_recurring_challenge())

    wrong_device = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/display-proof/challenge",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json={"device_id": str(uuid4())},
    )
    assert wrong_device.status_code == 409
    assert wrong_device.json()["error"]["code"] == "DISPLAY_PROOF_DEVICE_MISMATCH"

    challenge = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/display-proof/challenge",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json={"device_id": payload["device_id"]},
    )
    assert challenge.status_code == 201, challenge.text
    proof_file_id = create_clean_evidence_file(db_sessionmaker, user_id=driver.id)
    proof_payload = {
        "challenge_id": challenge.json()["challenge_id"],
        "nonce": challenge.json()["nonce"],
        "device_id": payload["device_id"],
        "stored_file_id": str(proof_file_id),
        "metadata": {"source": "synthetic-test"},
    }
    proof = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/display-proof",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json=proof_payload,
    )
    assert proof.status_code == 201, proof.text
    assert proof.json()["assignment_id"] == assignment_id
    assert proof.json()["evidence_submission_id"] == approved.json()["id"]

    async def read_verification() -> EvidenceVerification:
        async with db_sessionmaker() as session:
            return await session.get(EvidenceVerification, verification_id)

    verification = asyncio.run(read_verification())
    assert verification.status == "satisfied"
    assert verification.display_proof_id == UUID(proof.json()["id"])

    replay = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/display-proof",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json=proof_payload,
    )
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "DISPLAY_PROOF_CHALLENGE_REPLAYED"


def test_concurrent_display_proof_replay_has_one_winner_on_postgres(
    postgis_db_client,
    postgis_db_sessionmaker,
    settings,
) -> None:
    configure_evidence_policy(settings)
    admin, driver, _, assignment_id = accepted_assignment(
        postgis_db_client, postgis_db_sessionmaker, suffix="race"
    )
    evidence = evidence_payload(postgis_db_sessionmaker, driver_id=driver.id)
    submitted = postgis_db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence",
        headers=auth_headers(postgis_db_client, driver.email, PASSWORD),
        json=evidence,
    )
    assert submitted.status_code == 201, submitted.text
    approved = postgis_db_client.post(
        f"/api/v1/admin/installation-evidence/{submitted.json()['id']}/approve",
        headers=auth_headers(postgis_db_client, admin.email, PASSWORD),
        json={"reason": "Synthetic review passed"},
    )
    assert approved.status_code == 200, approved.text
    set_assignment_active(postgis_db_sessionmaker, UUID(assignment_id))
    challenge = postgis_db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/display-proof/challenge",
        headers=auth_headers(postgis_db_client, driver.email, PASSWORD),
        json={"device_id": evidence["device_id"]},
    )
    assert challenge.status_code == 201, challenge.text
    proof_file_id = create_clean_evidence_file(postgis_db_sessionmaker, user_id=driver.id)
    payload = DisplayProofCreate(
        challenge_id=UUID(challenge.json()["challenge_id"]),
        nonce=challenge.json()["nonce"],
        device_id=UUID(evidence["device_id"]),
        stored_file_id=proof_file_id,
        metadata={"source": "synthetic-race"},
    )

    async def attempt() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await submit_display_proof(
                    session,
                    actor_user_id=driver.id,
                    assignment_id=UUID(assignment_id),
                    payload=payload,
                    settings=settings,
                )
                await session.commit()
                return "ok"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def run_race() -> list[str]:
        return list(await asyncio.gather(attempt(), attempt()))

    outcomes = asyncio.run(run_race())
    assert sorted(outcomes) == ["DISPLAY_PROOF_CHALLENGE_REPLAYED", "ok"]


def test_trip_start_fails_closed_without_current_bound_display_proof(
    db_client,
    db_sessionmaker,
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)

    async def remove_proof() -> None:
        async with db_sessionmaker() as session:
            await session.execute(
                delete(DisplayProof).where(DisplayProof.assignment_id == assignment.id)
            )
            await session.commit()

    asyncio.run(remove_proof())
    response = start_trip(db_client, assignment.id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CURRENT_DISPLAY_PROOF_REQUIRED"

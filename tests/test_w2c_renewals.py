import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from conftest import auth_headers, create_test_driver_profile, create_test_user, create_test_vehicle
from sqlalchemy import func, select
from test_driver_person_payee_onboarding import _complete_admin_review
from test_kyc import PASSWORD, _payload, _seed_driver_authority

from app.adapters.crypto import EnvelopeCryptoProvider
from app.core.errors import AppError
from app.models.driver import DriverProfile
from app.models.kyc import DriverKycSubmission
from app.models.payee import PayeeBankAccountVersion
from app.models.user import UserRole
from app.schemas.driver_onboarding import PersonPayeeRenewalCreate, PersonPayeeReviewDecisionCreate
from app.services.driver_onboarding import (
    review_application_person_payee,
    submit_application_person_payee,
)


def test_active_driver_can_read_document_renewal_status(db_client, db_sessionmaker):
    driver = create_test_user(
        db_sessionmaker, email="renewal-driver@example.com", role=UserRole.DRIVER
    )
    profile = create_test_driver_profile(db_sessionmaker, user_id=driver.id)
    vehicle = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
    response = db_client.get(
        "/api/v1/driver/documents",
        headers=auth_headers(db_client, driver.email, "long-secure-password"),
    )
    assert response.status_code == 200
    assert response.json()["person_payee"]["status"] == "not_submitted"
    car = response.json()["vehicles"][0]
    assert car["vehicle_id"] == str(vehicle.id)
    assert car["status"] == "not_submitted" and car["submission_id"] is None
    assert car["valid_until"] is None and car["vehicle_type"] == "car"


def prepare(client, maker, *, state="rejected", reason=None):
    admin, driver, profile, bank_id, files = _seed_driver_authority(maker, suffix="renew")
    dh = auth_headers(client, driver.email, PASSWORD)
    ah = auth_headers(client, admin.email, PASSWORD)
    first = client.post("/api/v1/driver/kyc/submissions", headers=dh, json=_payload(bank_id, files))
    assert first.status_code == 201, first.text
    sid = first.json()["id"]
    review = client.post(
        f"/api/v1/admin/drivers/{profile.id}/documents/person-payee-decision",
        headers=ah,
        json={
            "submission_id": sid,
            "client_request_id": str(uuid4()),
            "decision": state,
            "reason_code": reason
            or ("expired_evidence" if state == "expired" else "unreadable_evidence"),
        },
    )
    assert review.status_code == 200, review.text
    payload = {
        "expected_submission_id": sid,
        "client_request_id": str(uuid4()),
        "nin": "12345678901",
        "account_name": "KYC Driver",
        "account_number": "0123456789",
        "bank_code": "058",
        **{
            f"{kind}_file_id": str(files[kind])
            for kind in ("driver_license", "driver_photo", "signed_agreement")
        },
    }
    return admin, driver, profile, files, dh, ah, payload


@pytest.mark.parametrize(
    "reason,omitted,expected",
    [
        ("identity_mismatch", ("nin",), "PERSON_PAYEE_NIN_REQUIRED"),
        (
            "bank_account_mismatch",
            ("account_name", "account_number", "bank_code"),
            "PERSON_PAYEE_BANK_DETAILS_REQUIRED",
        ),
        ("bank_account_mismatch", ("bank_code",), "PERSON_PAYEE_BANK_DETAILS_REQUIRED"),
        ("unreadable_evidence", ("nin",), "KYC_DECRYPTION_FAILED"),
    ],
)
def test_person_renewal_denials_preserve_revision_bank_and_review(
    postgis_db_client, postgis_db_sessionmaker, monkeypatch, reason, omitted, expected
):
    import json

    from app.models.audit import AuditEvent
    from app.models.kyc import DriverKycReviewDecision

    client, maker = postgis_db_client, postgis_db_sessionmaker
    _, _, profile, _, dh, _, payload = prepare(client, maker, reason=reason)
    before = client.get("/api/v1/driver/documents", headers=dh).json()
    for field in omitted:
        payload.pop(field)
    if expected == "KYC_DECRYPTION_FAILED":
        # The saved envelope uses key 1; simulate its unavailability, not corrupt ciphertext.
        monkeypatch.setattr(
            "app.api.v1.driver_documents._crypto",
            lambda _: EnvelopeCryptoProvider(keys={2: bytes(range(32))}, active_key_version=2),
        )
    denied = client.post("/api/v1/driver/documents/person-payee", headers=dh, json=payload)
    assert denied.status_code == (409 if expected == "KYC_DECRYPTION_FAILED" else 422)
    assert denied.json()["error"]["code"] == expected
    assert client.get("/api/v1/driver/documents", headers=dh).json() == before
    assert "12345678901" not in denied.text and "0123456789" not in denied.text

    async def inspect():
        async with maker() as session:
            assert await session.scalar(select(func.count(DriverKycSubmission.id))) == 1
            assert await session.scalar(select(func.count(PayeeBankAccountVersion.id))) == 1
            assert await session.scalar(select(func.count(DriverKycReviewDecision.id))) == 1
            assert (await session.get(DriverProfile, profile.id)).onboarding_status == "pending"
            submission = await session.scalar(select(DriverKycSubmission))
            assert submission.status == "rejected" and submission.encryption_key_version == 1
            review = await session.scalar(select(DriverKycReviewDecision))
            assert review.reason_code == reason
            audits = list(await session.scalars(select(AuditEvent)))
            assert not any(a.action == "driver.kyc.renewal_reuse" for a in audits)
            metadata = json.dumps([a.event_metadata for a in audits])
            assert "12345678901" not in metadata and "0123456789" not in metadata

    asyncio.run(inspect())


@pytest.mark.parametrize("state", ["rejected", "expired"])
def test_active_account_without_application_renews_and_staff_reviews_current_revision(
    db_client, db_sessionmaker, state
):
    admin, _, profile, files, dh, ah, payload = prepare(db_client, db_sessionmaker, state=state)
    old = db_client.get("/api/v1/driver/documents", headers=dh).json()
    bypass = db_client.post(
        "/api/v1/driver/kyc/submissions",
        headers=dh,
        json=_payload(
            db_client.get("/api/v1/driver/kyc/current", headers=dh).json()[
                "bank_account_version_id"
            ],
            files,
            client_request_id=str(uuid4()),
        ),
    )
    assert bypass.status_code == 409
    assert old["person_payee"]["reason_code"] == (
        "expired_evidence" if state == "expired" else "unreadable_evidence"
    )
    assert "person_document_names" not in old
    assert old["person_payee"]["documents"]["driver_license"]["status"] == "on_file"
    new = db_client.post("/api/v1/driver/documents/person-payee", headers=dh, json=payload)
    retry = db_client.post("/api/v1/driver/documents/person-payee", headers=dh, json=payload)
    assert new.status_code == retry.status_code == 201, new.text
    assert new.json()["submission_id"] == retry.json()["submission_id"]
    assert new.json()["version"] == 2 and new.json()["status"] == "pending_review"
    assert "12345678901" not in new.text and "0123456789" not in new.text
    path = f"/api/v1/admin/drivers/{profile.id}/documents/person-payee-decision"
    stale = db_client.post(
        path,
        headers=ah,
        json={
            "submission_id": payload["expected_submission_id"],
            "client_request_id": str(uuid4()),
            "decision": "rejected",
            "reason_code": "unreadable_evidence",
        },
    )
    assert (
        stale.status_code == 409 and stale.json()["error"]["code"] == "PERSON_PAYEE_REVISION_STALE"
    )
    distinct = db_client.post(
        "/api/v1/driver/documents/person-payee",
        headers=dh,
        json={**payload, "client_request_id": str(uuid4())},
    )
    assert distinct.status_code == 409
    conflict = db_client.post(
        "/api/v1/driver/documents/person-payee",
        headers=dh,
        json={**payload, "account_number": "9876543210"},
    )
    assert conflict.status_code == 409
    _complete_admin_review(
        db_client,
        db_sessionmaker,
        admin=admin,
        application=SimpleNamespace(driver_profile_id=profile.id),
        files={k: v for k, v in files.items() if k.startswith("driver") or k == "signed_agreement"},
    )
    approved = db_client.post(
        path,
        headers=ah,
        json={
            "submission_id": new.json()["submission_id"],
            "client_request_id": str(uuid4()),
            "decision": "approved",
            "reason_code": "complete_current_evidence",
            "identity_match_confirmed": True,
            "bank_account_match_confirmed": True,
            "documents_readable_confirmed": True,
        },
    )
    assert approved.status_code == 200, approved.text
    forbidden = db_client.post(
        "/api/v1/driver/documents/person-payee",
        headers=dh,
        json={
            **payload,
            "expected_submission_id": new.json()["submission_id"],
            "client_request_id": str(uuid4()),
        },
    )
    assert forbidden.status_code == 409

    async def inspect():
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count(DriverKycSubmission.id))) == 2
            assert await session.scalar(select(func.count(PayeeBankAccountVersion.id))) == 2
            assert (await session.get(DriverProfile, profile.id)).onboarding_status == "pending"

    asyncio.run(inspect())


def test_vehicle_renewal_status_names_dates_ownership_and_exact_retry(db_client, db_sessionmaker):
    admin, driver, profile, files, dh, ah, _ = prepare(db_client, db_sessionmaker)
    vehicle = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
    payload = {
        "client_request_id": str(uuid4()),
        **{f"{k}_file_id": str(files[k]) for k in ("registration", "insurance", "vehicle_photo")},
    }
    route = f"/api/v1/driver/vehicles/{vehicle.id}/evidence-submissions"
    first = db_client.post(route, headers=dh, json=payload)
    assert first.status_code == 201, first.text
    sid = first.json()["id"]
    reviewpath = (
        f"/api/v1/admin/drivers/{profile.id}/vehicles/{vehicle.id}/submissions/{sid}/decision"
    )
    pending = db_client.post(
        route,
        headers=dh,
        json={"client_request_id": str(uuid4()), "expected_submission_id": sid},
    )
    assert pending.status_code == 409
    assert pending.json()["error"]["code"] == "VEHICLE_RESUBMISSION_NOT_ALLOWED"
    reviewed = db_client.post(
        reviewpath,
        headers=ah,
        json={
            "client_request_id": str(uuid4()),
            "decision": "expired",
            "reason_code": "expired_evidence",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    status = db_client.get("/api/v1/driver/documents", headers=dh).json()["vehicles"][0]
    assert status["status"] == "expired" and status["valid_until"] is None
    renewal = {**payload, "client_request_id": str(uuid4()), "expected_submission_id": sid}
    second = db_client.post(route, headers=dh, json=renewal)
    retry = db_client.post(route, headers=dh, json=renewal)
    assert second.status_code == retry.status_code == 201, second.text
    assert second.json()["id"] == retry.json()["id"] and second.json()["version"] == 2
    for changes, code in [
        ({"expected_submission_id": str(uuid4())}, "VEHICLE_REVISION_STALE"),
        ({"expected_submission_id": second.json()["id"]}, "VEHICLE_EVIDENCE_RETRY_CONFLICT"),
        ({"insurance_file_id": str(files["registration"])}, "VEHICLE_EVIDENCE_RETRY_CONFLICT"),
        ({"client_request_id": str(uuid4())}, "VEHICLE_REVISION_STALE"),
    ]:
        denied = db_client.post(route, headers=dh, json={**renewal, **changes})
        assert denied.status_code == 409
        assert denied.json()["error"]["code"] == code
    other_car = create_test_vehicle(
        db_sessionmaker, driver_profile_id=profile.id, plate_number="DEF-456"
    )
    other_submission = db_client.post(
        f"/api/v1/driver/vehicles/{other_car.id}/evidence-submissions",
        headers=dh,
        json={**payload, "client_request_id": str(uuid4())},
    )
    assert other_submission.status_code == 201, other_submission.text
    cross_vehicle = db_client.post(
        route,
        headers=dh,
        json={**renewal, "expected_submission_id": other_submission.json()["id"]},
    )
    assert cross_vehicle.status_code == 409
    assert cross_vehicle.json()["error"]["code"] == "VEHICLE_REVISION_STALE"

    async def inspect_retries():
        from app.models.audit import AuditEvent
        from app.models.kyc import VehicleEvidenceDocument, VehicleEvidenceSubmission

        async with db_sessionmaker() as session:
            submissions = list(
                await session.scalars(
                    select(VehicleEvidenceSubmission)
                    .where(VehicleEvidenceSubmission.vehicle_id == vehicle.id)
                    .order_by(VehicleEvidenceSubmission.version)
                )
            )
            assert [(str(s.id), s.version) for s in submissions] == [
                (sid, 1),
                (second.json()["id"], 2),
            ]
            documents = list(
                await session.scalars(
                    select(VehicleEvidenceDocument).where(
                        VehicleEvidenceDocument.submission_id == UUID(second.json()["id"])
                    )
                )
            )
            assert {d.document_type: str(d.stored_file_id) for d in documents} == second.json()[
                "document_file_ids"
            ]
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "driver.vehicle_evidence.submitted",
                        AuditEvent.entity_id == second.json()["id"],
                    )
                )
                == 1
            )

    asyncio.run(inspect_retries())
    assert (
        db_client.post(
            reviewpath,
            headers=ah,
            json={
                "client_request_id": str(uuid4()),
                "decision": "rejected",
                "reason_code": "unreadable_evidence",
            },
        ).status_code
        == 409
    )
    other = create_test_user(db_sessionmaker, email="other-renew@example.com", role=UserRole.DRIVER)
    create_test_driver_profile(db_sessionmaker, user_id=other.id)
    assert (
        db_client.post(
            route, headers=auth_headers(db_client, other.email, PASSWORD), json=renewal
        ).status_code
        == 404
    )


@pytest.mark.parametrize("mode", ["distinct", "exact", "review"])
def test_postgres_renewal_races_leave_one_revision_no_orphan_bank(
    postgis_db_client, postgis_db_sessionmaker, settings, mode
):
    admin, driver, profile, _, _, _, payload = prepare(postgis_db_client, postgis_db_sessionmaker)
    crypto = EnvelopeCryptoProvider(keys={1: bytes(range(32))}, active_key_version=1)
    barrier = asyncio.Barrier(2)

    async def worker(index):
        async with postgis_db_sessionmaker() as session:
            await barrier.wait()
            try:
                if mode == "review" and index:
                    await review_application_person_payee(
                        session,
                        driver_profile_id=profile.id,
                        actor_user_id=admin.id,
                        payload=PersonPayeeReviewDecisionCreate(
                            submission_id=UUID(payload["expected_submission_id"]),
                            client_request_id=uuid4(),
                            decision="rejected",
                            reason_code="unreadable_evidence",
                        ),
                    )
                    result = "review"
                else:
                    data = {**payload}
                    if mode == "distinct" and index:
                        data["client_request_id"] = str(uuid4())
                    view = await submit_application_person_payee(
                        session,
                        actor_user_id=driver.id,
                        payload=PersonPayeeRenewalCreate.model_validate(data),
                        crypto=crypto,
                        settings=settings,
                    )
                    result = str(view.submission.id)
                await session.commit()
                return result
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def scenario():
        results = await asyncio.gather(worker(0), worker(1))
        async with postgis_db_sessionmaker() as session:
            assert await session.scalar(select(func.count(DriverKycSubmission.id))) == 2
            assert await session.scalar(select(func.count(PayeeBankAccountVersion.id))) == 2
        if mode == "exact":
            assert results[0] == results[1]
        elif mode == "distinct":
            assert "PERSON_PAYEE_REVISION_STALE" in results
        else:
            assert any(
                r in {"PERSON_PAYEE_REVISION_STALE", "PERSON_PAYEE_ALREADY_DECIDED"}
                for r in results
            )

    asyncio.run(scenario())


def test_locked_driver_authority_refreshes_preloaded_account(
    postgis_db_client, postgis_db_sessionmaker, settings
):
    from app.models.user import User

    _, driver, _, _, _, _, payload = prepare(postgis_db_client, postgis_db_sessionmaker)

    async def scenario():
        async with postgis_db_sessionmaker() as stale:
            cached = await stale.get(User, driver.id)
            assert cached.status == "active"
            async with postgis_db_sessionmaker() as changed:
                current = await changed.get(User, driver.id)
                current.status = "suspended"
                await changed.commit()
            with pytest.raises(AppError) as denied:
                await submit_application_person_payee(
                    stale,
                    actor_user_id=driver.id,
                    payload=PersonPayeeRenewalCreate.model_validate(payload),
                    settings=settings,
                    crypto=EnvelopeCryptoProvider(keys={1: bytes(range(32))}, active_key_version=1),
                )
            assert denied.value.code == "KYC_SCOPE_NOT_FOUND"
            await stale.rollback()
        async with postgis_db_sessionmaker() as inspect:
            assert await inspect.scalar(select(func.count(DriverKycSubmission.id))) == 1
            assert await inspect.scalar(select(func.count(PayeeBankAccountVersion.id))) == 1

    asyncio.run(scenario())


def test_staff_document_status_is_current_secret_free_and_role_scoped(db_client, db_sessionmaker):
    admin, driver, profile, files, dh, ah, payload = prepare(db_client, db_sessionmaker)
    vehicle = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
    read = db_client.get(f"/api/v1/admin/drivers/{profile.id}/documents", headers=ah)
    assert read.status_code == 200, read.text
    person = read.json()["person_payee"]
    assert person["submission_id"] == payload["expected_submission_id"]
    assert person["status"] == "rejected"
    assert person["document_file_ids"] == {
        kind: str(files[kind]) for kind in ("driver_license", "driver_photo", "signed_agreement")
    }
    assert read.json()["vehicles"][0]["vehicle_id"] == str(vehicle.id)
    assert read.json()["vehicles"][0]["status"] == "not_submitted"
    assert payload["nin"] not in read.text and payload["account_number"] not in read.text
    assert (
        db_client.get(f"/api/v1/admin/drivers/{profile.id}/documents", headers=dh).status_code
        == 403
    )
    absent = db_client.get(f"/api/v1/admin/drivers/{uuid4()}/documents", headers=ah)
    assert (
        absent.status_code == 404 and absent.json()["error"]["code"] == "DRIVER_PROFILE_NOT_FOUND"
    )


@pytest.mark.parametrize(
    "reason,field",
    [
        ("unreadable_evidence", "driver_license_file_id"),
        ("bank_account_mismatch", None),
        ("identity_mismatch", None),
    ],
)
def test_partial_person_renewal_reuses_accepted_files_and_saved_details(
    db_client, db_sessionmaker, reason, field
):
    admin, driver, profile, bank_id, files = _seed_driver_authority(
        db_sessionmaker, suffix="partial"
    )
    dh = auth_headers(db_client, driver.email, PASSWORD)
    ah = auth_headers(db_client, admin.email, PASSWORD)
    initial = db_client.post(
        "/api/v1/driver/kyc/submissions", headers=dh, json=_payload(bank_id, files)
    ).json()
    review_document_files(
        db_client,
        db_sessionmaker,
        admin=admin,
        submission_id=initial["id"],
        files={k: files[k] for k in ("driver_license", "driver_photo", "signed_agreement")},
    )
    reviews = {
        kind: {"status": "accepted"}
        for kind in ("driver_license", "driver_photo", "signed_agreement")
    }
    if field:
        reviews["driver_license"] = {"status": "rejected", "reason_code": reason}
    decision = db_client.post(
        f"/api/v1/admin/drivers/{profile.id}/documents/person-payee-decision",
        headers=ah,
        json={
            "submission_id": initial["id"],
            "client_request_id": str(uuid4()),
            "decision": "rejected",
            "reason_code": reason,
            "document_reviews": reviews,
        },
    )
    assert decision.status_code == 200, decision.text
    status = db_client.get("/api/v1/driver/documents", headers=dh).json()["person_payee"]
    assert status["documents"]["driver_photo"]["status"] == "accepted"
    assert status["replace_bank"] == (reason == "bank_account_mismatch")
    assert status["replace_nin"] == (reason == "identity_mismatch")
    data = {"expected_submission_id": initial["id"], "client_request_id": str(uuid4())}
    if field:
        data[field] = str(files["driver_license"])
    if reason == "bank_account_mismatch":
        data.update(account_name="KYC Driver", account_number="0123456789", bank_code="058")
    if reason == "identity_mismatch":
        data["nin"] = "12345678901"
    first = db_client.post("/api/v1/driver/documents/person-payee", headers=dh, json=data)
    retry = db_client.post("/api/v1/driver/documents/person-payee", headers=dh, json=data)
    assert first.status_code == retry.status_code == 201, first.text
    assert first.json()["submission_id"] == retry.json()["submission_id"]
    current = db_client.get("/api/v1/driver/kyc/current", headers=dh).json()
    assert current["document_file_ids"] == {kind: str(files[kind]) for kind in reviews}
    assert (current["bank_account_version_id"] == str(bank_id)) == (
        reason != "bank_account_mismatch"
    )
    assert "12345678901" not in first.text and "0123456789" not in first.text
    changed = db_client.post(
        "/api/v1/driver/documents/person-payee", headers=dh, json={**data, "nin": "10987654321"}
    )
    assert changed.status_code == 409


def test_nonapproved_review_cannot_fabricate_accepted_document_without_read(
    db_client, db_sessionmaker
):
    admin, driver, profile, bank_id, files = _seed_driver_authority(
        db_sessionmaker, suffix="no-read"
    )
    dh = auth_headers(db_client, driver.email, PASSWORD)
    ah = auth_headers(db_client, admin.email, PASSWORD)
    first = db_client.post(
        "/api/v1/driver/kyc/submissions", headers=dh, json=_payload(bank_id, files)
    ).json()
    response = db_client.post(
        f"/api/v1/admin/drivers/{profile.id}/documents/person-payee-decision",
        headers=ah,
        json={
            "submission_id": first["id"],
            "client_request_id": str(uuid4()),
            "decision": "rejected",
            "reason_code": "bank_account_mismatch",
            "document_reviews": {
                kind: {"status": "accepted"}
                for kind in ("driver_license", "driver_photo", "signed_agreement")
            },
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOCUMENT_REVIEW_READ_REQUIRED"
    other_admin = create_test_user(db_sessionmaker, email="other-reader@example.com")
    document_files = {k: files[k] for k in ("driver_license", "driver_photo", "signed_agreement")}
    review_document_files(
        db_client,
        db_sessionmaker,
        admin=other_admin,
        submission_id=first["id"],
        files=document_files,
    )
    payload = {
        "submission_id": first["id"],
        "client_request_id": str(uuid4()),
        "decision": "rejected",
        "reason_code": "bank_account_mismatch",
        "document_reviews": {k: {"status": "accepted"} for k in document_files},
    }
    path = f"/api/v1/admin/drivers/{profile.id}/documents/person-payee-decision"

    async def no_decision():
        from app.models.kyc import DriverKycReviewDecision

        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count(DriverKycReviewDecision.id))) == 0
            assert (
                await session.get(DriverKycSubmission, UUID(first["id"]))
            ).status == "pending_review"

    # Another actor's reads cannot authorize this actor; nor can reading only two files.
    for own_reads in ({}, {k: files[k] for k in ("driver_license", "driver_photo")}):
        review_document_files(
            db_client, db_sessionmaker, admin=admin, submission_id=first["id"], files=own_reads
        )
        denied = db_client.post(path, headers=ah, json=payload)
        assert denied.status_code == 409
        assert denied.json()["error"]["code"] == "DOCUMENT_REVIEW_READ_REQUIRED"
        asyncio.run(no_decision())
    incomplete = db_client.post(
        path,
        headers=ah,
        json={**payload, "document_reviews": {"driver_license": {"status": "accepted"}}},
    )
    assert incomplete.status_code == 422
    assert incomplete.json()["error"]["code"] == "DOCUMENT_REVIEW_INCOMPLETE"
    asyncio.run(no_decision())
    review_document_files(
        db_client,
        db_sessionmaker,
        admin=admin,
        submission_id=first["id"],
        files={"signed_agreement": files["signed_agreement"]},
    )
    accepted = db_client.post(path, headers=ah, json=payload)
    assert accepted.status_code == 200, accepted.text

    async def inspect_reads():
        from app.models.audit import AuditEvent
        from app.models.kyc import DriverKycReviewDecision

        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count(DriverKycReviewDecision.id))) == 1
            reads = list(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.action == "stored_file.read",
                        AuditEvent.actor_user_id == admin.id,
                    )
                )
            )
            assert {a.entity_id for a in reads} == {str(f) for f in document_files.values()}
            assert all(
                a.entity_type == "stored_file"
                and a.event_metadata["reason"] == f"person_payee_approval:{first['id']}"
                and a.event_metadata["access_purpose"] == "kyc_review"
                and a.event_metadata["file_purpose"] == "driver_kyc"
                for a in reads
            )

    asyncio.run(inspect_reads())


@pytest.mark.parametrize("whole_car", [False, True])
def test_vehicle_partial_renewal_keeps_accepted_files_and_separates_approval_expiry(
    db_client, db_sessionmaker, whole_car
):
    from datetime import UTC, datetime, timedelta

    admin, driver, profile, files, dh, ah, _ = prepare(db_client, db_sessionmaker)
    vehicle = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
    route = f"/api/v1/driver/vehicles/{vehicle.id}/evidence-submissions"
    first = db_client.post(
        route,
        headers=dh,
        json={
            "client_request_id": str(uuid4()),
            **{
                f"{k}_file_id": str(files[k])
                for k in ("registration", "insurance", "vehicle_photo")
            },
        },
    ).json()
    review_document_files(
        db_client,
        db_sessionmaker,
        admin=admin,
        submission_id=first["id"],
        files={k: files[k] for k in ("registration", "insurance", "vehicle_photo")},
        vehicle=True,
    )
    reviews = {k: {"status": "accepted"} for k in ("registration", "insurance", "vehicle_photo")}
    if not whole_car:
        reviews["insurance"] = {
            "status": "expired",
            "reason_code": "expired_evidence",
            "expires_on": "2026-10-03",
        }
    review = db_client.post(
        f"/api/v1/admin/drivers/{profile.id}/vehicles/{vehicle.id}/submissions/{first['id']}/decision",
        headers=ah,
        json={
            "client_request_id": str(uuid4()),
            "decision": "expired",
            "reason_code": "expired_evidence",
            "document_reviews": reviews,
            "valid_until": (datetime.now(UTC) - timedelta(days=1)).isoformat()
            if whole_car
            else None,
        },
    )
    assert review.status_code == 200, review.text
    current = db_client.get("/api/v1/driver/documents", headers=dh).json()["vehicles"][0]
    assert current["documents"]["insurance"]["status"] == ("accepted" if whole_car else "expired")
    renewal = {"client_request_id": str(uuid4()), "expected_submission_id": first["id"]}
    if not whole_car:
        denied = db_client.post(route, headers=dh, json=renewal)
        assert denied.status_code == 422
        assert denied.json()["error"]["code"] == "VEHICLE_REPLACEMENTS_REQUIRED"
        unchanged = db_client.get("/api/v1/driver/documents", headers=dh).json()["vehicles"][0]
        assert unchanged == current
        renewal["insurance_file_id"] = str(files["insurance"])
    updated = db_client.post(route, headers=dh, json=renewal)
    retry = db_client.post(route, headers=dh, json=renewal)
    assert updated.status_code == retry.status_code == 201, updated.text
    assert updated.json()["id"] == retry.json()["id"]
    assert updated.json()["document_file_ids"] == {k: str(files[k]) for k in reviews}


def review_document_files(client, maker, *, admin, submission_id, files, vehicle=False):
    from test_stored_files import FakeStorageProvider

    from app.adapters.storage import ObjectMetadata
    from app.api.v1.dependencies import get_storage_provider
    from app.models.stored_file import StoredFile

    storage = FakeStorageProvider()
    client.app.dependency_overrides[get_storage_provider] = lambda: storage

    async def populate():
        async with maker() as session:
            for file_id in files.values():
                stored = await session.get(StoredFile, file_id)
                storage.objects[stored.storage_key] = ObjectMetadata(
                    object_key=stored.storage_key,
                    size_bytes=stored.size_bytes,
                    content_type=stored.actual_content_type or stored.content_type,
                    checksum_sha256=stored.checksum_sha256,
                )

    asyncio.run(populate())
    review_purpose = "vehicle_approval" if vehicle else "person_payee_approval"
    for file_id in files.values():
        read = client.post(
            f"/api/v1/admin/files/{file_id}/download",
            headers=auth_headers(client, admin.email, PASSWORD),
            json={
                "purpose": "kyc_review",
                "reason": f"{review_purpose}:{submission_id}",
            },
        )
        assert read.status_code == 200, read.text


def test_vehicle_approval_expires_at_exact_boundary_without_inventing_document_expiry(
    postgis_db_client, postgis_db_sessionmaker, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    from app.models.kyc import VehicleEvidenceSubmission
    from app.models.vehicle import Vehicle
    from app.services.vehicle_onboarding import ensure_current_driver_vehicle_eligibility

    client, maker = postgis_db_client, postgis_db_sessionmaker
    admin, _, profile, files, dh, ah, renewal_payload = prepare(client, maker)
    person = client.post("/api/v1/driver/documents/person-payee", headers=dh, json=renewal_payload)
    assert person.status_code == 201
    _complete_admin_review(
        client,
        maker,
        admin=admin,
        application=SimpleNamespace(driver_profile_id=profile.id),
        files={k: files[k] for k in ("driver_license", "driver_photo", "signed_agreement")},
    )
    approved_person = client.post(
        f"/api/v1/admin/drivers/{profile.id}/documents/person-payee-decision",
        headers=ah,
        json={
            "submission_id": person.json()["submission_id"],
            "client_request_id": str(uuid4()),
            "decision": "approved",
            "reason_code": "complete_current_evidence",
            "identity_match_confirmed": True,
            "bank_account_match_confirmed": True,
            "documents_readable_confirmed": True,
        },
    )
    assert approved_person.status_code == 200, approved_person.text
    car = create_test_vehicle(maker, driver_profile_id=profile.id)
    route = f"/api/v1/driver/vehicles/{car.id}/evidence-submissions"
    documents = {k: files[k] for k in ("registration", "insurance", "vehicle_photo")}
    submitted = client.post(
        route,
        headers=dh,
        json={
            "client_request_id": str(uuid4()),
            **{f"{k}_file_id": str(v) for k, v in documents.items()},
        },
    )
    assert submitted.status_code == 201
    sid = submitted.json()["id"]
    review_document_files(
        client, maker, admin=admin, submission_id=sid, files=documents, vehicle=True
    )
    expiry = datetime.now(UTC) + timedelta(days=1)
    approved = client.post(
        f"/api/v1/admin/drivers/{profile.id}/vehicles/{car.id}/submissions/{sid}/decision",
        headers=ah,
        json={
            "client_request_id": str(uuid4()),
            "decision": "approved",
            "reason_code": "complete_current_evidence",
            "valid_until": expiry.isoformat(),
            "owner_match_confirmed": True,
            "vehicle_identity_confirmed": True,
            "roadworthy_confirmed": True,
            "pilot_car_confirmed": True,
            "documents_readable_confirmed": True,
            "document_reviews": {k: {"status": "accepted"} for k in documents},
        },
    )
    assert approved.status_code == 200, approved.text
    renewal = {"client_request_id": str(uuid4()), "expected_submission_id": sid}
    now = expiry - timedelta(microseconds=1)

    async def clock(_):
        return now

    for module in (
        "app.api.v1.driver_documents",
        "app.services.kyc",
        "app.services.vehicle_onboarding",
    ):
        monkeypatch.setattr(module + ".database_clock", clock)

    async def work_allowed():
        async with maker() as session:
            await ensure_current_driver_vehicle_eligibility(
                session,
                driver_profile=await session.get(DriverProfile, profile.id),
                vehicle=await session.get(Vehicle, car.id),
                now=now,
                lock=False,
            )

    before = client.get("/api/v1/driver/documents", headers=dh).json()["vehicles"][0]
    assert before["status"] == "approved"
    asyncio.run(work_allowed())
    too_early = client.post(route, headers=dh, json=renewal)
    assert too_early.status_code == 409
    assert too_early.json()["error"]["code"] == "VEHICLE_RESUBMISSION_NOT_ALLOWED"
    now = expiry
    at_boundary = client.get("/api/v1/driver/documents", headers=dh).json()["vehicles"][0]
    assert at_boundary["status"] == "expired"
    assert all(
        d["status"] == "accepted" and d["expires_on"] is None
        for d in at_boundary["documents"].values()
    )
    with pytest.raises(AppError) as denied:
        asyncio.run(work_allowed())
    assert denied.value.code == "VEHICLE_APPROVAL_REQUIRED"

    async def persisted_approval():
        async with maker() as session:
            assert (await session.get(VehicleEvidenceSubmission, UUID(sid))).status == "approved"

    asyncio.run(persisted_approval())
    renewed = client.post(route, headers=dh, json=renewal)
    assert renewed.status_code == 201, renewed.text
    assert renewed.json()["version"] == 2 and renewed.json()["status"] == "pending_review"
    assert renewed.json()["document_file_ids"] == {k: str(v) for k, v in documents.items()}
    with pytest.raises(AppError) as pending:
        asyncio.run(work_allowed())
    assert pending.value.code == "VEHICLE_APPROVAL_REQUIRED"


def test_purged_person_requires_fresh_full_inputs_without_recovering_erased_nin(
    db_client, db_sessionmaker
):
    from datetime import UTC, datetime

    admin, driver, profile, files, dh, ah, data = prepare(db_client, db_sessionmaker)

    async def purge():
        async with db_sessionmaker() as session:
            row = await session.get(DriverKycSubmission, UUID(data["expected_submission_id"]))
            row.purged_at = datetime.now(UTC)
            row.encrypted_nin = None
            row.encryption_algorithm = None
            row.encryption_key_version = None
            row.nin_last_four = None
            await session.commit()

    asyncio.run(purge())
    partial = {
        "client_request_id": str(uuid4()),
        "expected_submission_id": data["expected_submission_id"],
        "driver_license_file_id": str(files["driver_license"]),
    }
    denied = db_client.post("/api/v1/driver/documents/person-payee", headers=dh, json=partial)
    assert denied.status_code == 422
    complete = db_client.post("/api/v1/driver/documents/person-payee", headers=dh, json=data)
    assert complete.status_code == 201, complete.text
    status = db_client.get("/api/v1/driver/documents", headers=dh).json()["person_payee"]
    assert "masked_nin" not in status and "person_document_names" not in status
    assert status["version"] == 2


def test_recorded_person_document_expiry_blocks_work_and_allows_partial_renewal(
    db_client, db_sessionmaker, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    from app.models.kyc import DriverKycReviewDecision
    from app.services.vehicle_onboarding import _current_person_payee_approved

    admin, driver, profile, bank_id, files = _seed_driver_authority(
        db_sessionmaker, suffix="known-expiry"
    )
    dh = auth_headers(db_client, driver.email, PASSWORD)
    initial = db_client.post(
        "/api/v1/driver/kyc/submissions", headers=dh, json=_payload(bank_id, files)
    ).json()
    expires = (datetime.now(UTC) + timedelta(days=1)).date()

    async def record_earlier_approval():
        async with db_sessionmaker() as session:
            row = await session.get(DriverKycSubmission, UUID(initial["id"]))
            row.status = "approved"
            session.add(
                DriverKycReviewDecision(
                    submission_id=row.id,
                    client_request_id=uuid4(),
                    request_fingerprint="a" * 64,
                    decision="approved",
                    reason_code="complete_current_evidence",
                    identity_match_confirmed=True,
                    bank_account_match_confirmed=True,
                    documents_readable_confirmed=True,
                    decided_by_user_id=admin.id,
                    document_reviews={
                        "driver_license": {"status": "accepted", "expires_on": expires.isoformat()},
                        "driver_photo": {"status": "accepted"},
                        "signed_agreement": {"status": "accepted"},
                    },
                )
            )
            await session.commit()

    asyncio.run(record_earlier_approval())

    async def later_clock(_):
        return datetime.combine(expires + timedelta(days=1), datetime.min.time(), UTC)

    for module in [
        "app.api.v1.driver_documents",
        "app.services.kyc",
        "app.services.vehicle_onboarding",
        "app.services.payout_rule_serialization",
        "app.services.document_reviews",
    ]:
        monkeypatch.setattr(module + ".database_clock", later_clock)

    async def work_check():
        async with db_sessionmaker() as session:
            assert not await _current_person_payee_approved(
                session, driver_profile_id=profile.id, lock=False
            )

    asyncio.run(work_check())
    status = db_client.get("/api/v1/driver/documents", headers=dh).json()["person_payee"]
    assert status["status"] == "expired"
    assert status["documents"]["driver_photo"]["status"] == "accepted"
    response = db_client.post(
        "/api/v1/driver/documents/person-payee",
        headers=dh,
        json={
            "client_request_id": str(uuid4()),
            "expected_submission_id": initial["id"],
            "driver_license_file_id": str(files["driver_license"]),
        },
    )
    assert response.status_code == 201, response.text


def test_exact_person_renewal_retry_survives_retained_document_expiring_overnight(
    db_client, db_sessionmaker, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    from app.models.kyc import DriverKycReviewDecision

    _, _, _, files, dh, _, data = prepare(db_client, db_sessionmaker)
    today = datetime.now(UTC).date()

    async def record_document_facts():
        async with db_sessionmaker() as session:
            review = await session.scalar(
                select(DriverKycReviewDecision).where(
                    DriverKycReviewDecision.submission_id == UUID(data["expected_submission_id"])
                )
            )
            review.document_reviews = {
                "driver_license": {"status": "rejected", "reason_code": "unreadable_evidence"},
                "driver_photo": {"status": "accepted"},
                "signed_agreement": {"status": "accepted", "expires_on": today.isoformat()},
            }
            await session.commit()

    asyncio.run(record_document_facts())
    renewal = {
        "client_request_id": str(uuid4()),
        "expected_submission_id": data["expected_submission_id"],
        "driver_license_file_id": str(files["driver_license"]),
    }

    async def clock(_):
        return datetime.combine(today, datetime.min.time(), UTC)

    monkeypatch.setattr("app.services.payout_rule_serialization.database_clock", clock)
    response = db_client.post("/api/v1/driver/documents/person-payee", headers=dh, json=renewal)
    assert response.status_code == 201, response.text
    today += timedelta(days=1)
    replay = db_client.post("/api/v1/driver/documents/person-payee", headers=dh, json=renewal)
    assert replay.status_code == 201, replay.text
    assert replay.json()["submission_id"] == response.json()["submission_id"]
    changed = db_client.post(
        "/api/v1/driver/documents/person-payee",
        headers=dh,
        json={**renewal, "driver_license_file_id": str(files["driver_photo"])},
    )
    assert changed.status_code == 409


@pytest.mark.parametrize("vehicle", [False, True])
def test_missing_retained_file_is_visible_and_can_be_replaced(db_client, db_sessionmaker, vehicle):
    from sqlalchemy import delete

    from app.models.kyc import DriverKycDocument, VehicleEvidenceDocument

    _, driver, profile, files, dh, ah, data = prepare(db_client, db_sessionmaker)
    if vehicle:
        car = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
        route = f"/api/v1/driver/vehicles/{car.id}/evidence-submissions"
        first = db_client.post(
            route,
            headers=dh,
            json={
                "client_request_id": str(uuid4()),
                **{
                    f"{kind}_file_id": str(files[kind])
                    for kind in ("registration", "insurance", "vehicle_photo")
                },
            },
        ).json()
        sid = first["id"]
        db_client.post(
            f"/api/v1/admin/drivers/{profile.id}/vehicles/{car.id}/submissions/{sid}/decision",
            headers=ah,
            json={
                "client_request_id": str(uuid4()),
                "decision": "expired",
                "reason_code": "expired_evidence",
            },
        )
        model, kind = VehicleEvidenceDocument, "insurance"
    else:
        route = "/api/v1/driver/documents/person-payee"
        sid = data["expected_submission_id"]
        model, kind = DriverKycDocument, "driver_photo"

    async def remove_reference():
        async with db_sessionmaker() as session:
            await session.execute(
                delete(model).where(model.submission_id == UUID(sid), model.document_type == kind)
            )
            await session.commit()

    asyncio.run(remove_reference())
    current = db_client.get("/api/v1/driver/documents", headers=dh).json()
    stage = current["vehicles"][0] if vehicle else current["person_payee"]
    assert stage["documents"][kind] == {
        "status": "rejected",
        "reason_code": "missing_evidence",
        "expires_on": None,
    }
    renewal = db_client.post(
        route,
        headers=dh,
        json={
            "client_request_id": str(uuid4()),
            "expected_submission_id": sid,
            f"{kind}_file_id": str(files[kind]),
        },
    )
    assert renewal.status_code == 201, renewal.text


def test_purged_vehicle_read_requests_and_accepts_complete_fresh_replacement(
    db_client, db_sessionmaker
):
    from datetime import UTC, datetime

    from app.models.kyc import VehicleEvidenceSubmission

    _, _, profile, files, dh, ah, _ = prepare(db_client, db_sessionmaker)
    car = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
    route = f"/api/v1/driver/vehicles/{car.id}/evidence-submissions"
    complete = {
        f"{kind}_file_id": str(files[kind])
        for kind in ("registration", "insurance", "vehicle_photo")
    }
    first = db_client.post(
        route,
        headers=dh,
        json={
            "client_request_id": str(uuid4()),
            **complete,
        },
    ).json()
    db_client.post(
        f"/api/v1/admin/drivers/{profile.id}/vehicles/{car.id}/submissions/{first['id']}/decision",
        headers=ah,
        json={
            "client_request_id": str(uuid4()),
            "decision": "expired",
            "reason_code": "expired_evidence",
        },
    )

    async def purge_snapshot():
        async with db_sessionmaker() as session:
            row = await session.get(VehicleEvidenceSubmission, UUID(first["id"]))
            row.purged_at = datetime.now(UTC)
            for field in (
                "plate_number_snapshot",
                "plate_number_normalized_snapshot",
                "plate_country_code_snapshot",
                "vehicle_type_snapshot",
                "make_snapshot",
                "model_snapshot",
                "year_snapshot",
                "color_snapshot",
            ):
                setattr(row, field, None)
            await session.commit()

    asyncio.run(purge_snapshot())
    stage = db_client.get("/api/v1/driver/documents", headers=dh).json()["vehicles"][0]
    assert stage["purged_at"] and stage["plate_number"] == car.plate_number
    attempt = {"client_request_id": str(uuid4()), "expected_submission_id": first["id"]}
    assert db_client.post(route, headers=dh, json=attempt).status_code == 422
    fresh = db_client.post(route, headers=dh, json={**attempt, **complete})
    assert fresh.status_code == 201, fresh.text


@pytest.mark.parametrize("vehicle", [False, True])
def test_partial_retry_after_source_payload_purge_fails_closed(db_client, db_sessionmaker, vehicle):
    from datetime import UTC, datetime

    from app.models.kyc import VehicleEvidenceSubmission

    _, _, profile, files, dh, ah, initial = prepare(db_client, db_sessionmaker)
    if vehicle:
        car = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
        route = f"/api/v1/driver/vehicles/{car.id}/evidence-submissions"
        first = db_client.post(
            route,
            headers=dh,
            json={
                "client_request_id": str(uuid4()),
                **{
                    f"{kind}_file_id": str(files[kind])
                    for kind in ("registration", "insurance", "vehicle_photo")
                },
            },
        ).json()
        reviewed = db_client.post(
            f"/api/v1/admin/drivers/{profile.id}/vehicles/{car.id}/submissions/{first['id']}/decision",
            headers=ah,
            json={
                "client_request_id": str(uuid4()),
                "decision": "expired",
                "reason_code": "expired_evidence",
            },
        )
        assert reviewed.status_code == 200, reviewed.text
        source_id = first["id"]
        payload = {
            "client_request_id": str(uuid4()),
            "expected_submission_id": source_id,
            "insurance_file_id": str(files["insurance"]),
        }
    else:
        route = "/api/v1/driver/documents/person-payee"
        source_id = initial["expected_submission_id"]
        payload = {
            "client_request_id": str(uuid4()),
            "expected_submission_id": source_id,
            "driver_license_file_id": str(files["driver_license"]),
        }
    accepted = db_client.post(route, headers=dh, json=payload)
    assert accepted.status_code == 201, accepted.text

    async def purge_source():
        async with db_sessionmaker() as session:
            row = await session.get(
                VehicleEvidenceSubmission if vehicle else DriverKycSubmission, UUID(source_id)
            )
            row.purged_at = datetime.now(UTC)
            fields = (
                (
                    "plate_number_snapshot",
                    "plate_number_normalized_snapshot",
                    "plate_country_code_snapshot",
                    "vehicle_type_snapshot",
                    "make_snapshot",
                    "model_snapshot",
                    "year_snapshot",
                    "color_snapshot",
                )
                if vehicle
                else (
                    "encrypted_nin",
                    "nin_last_four",
                    "encryption_algorithm",
                    "encryption_key_version",
                )
            )
            for field in fields:
                setattr(row, field, None)
            await session.commit()

    asyncio.run(purge_source())
    retried = db_client.post(route, headers=dh, json=payload)
    assert retried.status_code == 422, retried.text
    current = db_client.get("/api/v1/driver/documents", headers=dh).json()
    stage = current["vehicles"][0] if vehicle else current["person_payee"]
    assert stage["version"] == 2

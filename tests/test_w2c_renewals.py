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


def prepare(client, maker, *, state="rejected"):
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
            "reason_code": "expired_evidence" if state == "expired" else "unreadable_evidence",
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
    assert old["person_document_names"]["driver_license"] == "driver_license.png"
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
    assert (
        db_client.post(
            route, headers=dh, json={**renewal, "expected_submission_id": str(uuid4())}
        ).status_code
        == 409
    )
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

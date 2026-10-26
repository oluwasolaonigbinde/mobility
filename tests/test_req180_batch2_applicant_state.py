"""D8 / REQ-195: the continue link says where the applicant stands, and why changes are needed."""

import asyncio
from uuid import uuid4

from conftest import auth_headers, create_test_user
from sqlalchemy import delete, select
from test_driver_person_payee_onboarding import (
    PASSWORD,
    _application,
    _current_submission_id,
    _person_payee_payload,
    _register,
    _seed_clean_kyc_files,
)
from test_driver_vehicle_approval import (
    _approve_vehicle,
    _approved_applicant,
    _decision_path,
    _seed_vehicle_files,
    _vehicle_payload,
)

from app.models.kyc import (
    DriverKycReviewDecision,
    DriverKycSubmission,
    VehicleEvidenceSubmission,
)
from app.models.payee import PayeeBankAccountPayoutVerification

CONTINUE = "/api/v1/auth/driver-onboarding/continue"
EXPIRED = "Some documents have expired. Please send current copies."


def _state(client, token):
    response = client.post(CONTINUE, json={"application_access_token": token})
    assert response.status_code == 200, response.text
    body = response.json()
    return body["step"], body["state"], body["changes_reason"]


def _update(maker, model, where, **values):
    async def run():
        async with maker() as session:
            row = await session.scalar(select(model).where(where))
            for key, value in values.items():
                setattr(row, key, value)
            await session.commit()

    asyncio.run(run())


def test_details_states_follow_the_latest_submission_and_its_review(
    db_client, db_sessionmaker, settings
):
    token, _ = _register(db_client, db_sessionmaker, settings, suffix="state-details")
    assert _state(db_client, token) == ("details", "details_needed", None)
    email = "person-payee-state-details@example.com"
    application = _application(db_sessionmaker, email=email)
    files = _seed_clean_kyc_files(db_sessionmaker, email=email)
    submitted = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json=_person_payee_payload(token, files, db_client),
    )
    assert submitted.status_code == 201, submitted.text
    assert _state(db_client, token) == ("details", "details_in_review", None)
    admin = create_test_user(
        db_sessionmaker, email="state-details-admin@example.com", password=PASSWORD
    )
    rejected = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={
            "submission_id": _current_submission_id(db_sessionmaker, application.driver_profile_id),
            "client_request_id": str(uuid4()),
            "decision": "rejected",
            "reason_code": "identity_mismatch",
            "identity_match_confirmed": False,
            "bank_account_match_confirmed": False,
            "documents_readable_confirmed": False,
        },
    )
    assert rejected.status_code == 200, rejected.text
    assert _state(db_client, token) == (
        "details",
        "details_changes_needed",
        "Your ID details do not match. Please check them.",
    )
    profile = DriverKycSubmission.driver_profile_id == application.driver_profile_id
    _update(db_sessionmaker, DriverKycSubmission, profile, status="expired")
    assert _state(db_client, token) == ("details", "details_changes_needed", EXPIRED)


def test_approved_details_that_expired_or_await_payout_check_stay_on_details(
    db_client, db_sessionmaker, settings
):
    token, application, _ = _approved_applicant(
        db_client, db_sessionmaker, settings, suffix="state-approved"
    )
    assert _state(db_client, token) == ("car", "car_needed", None)

    async def submission():
        async with db_sessionmaker() as session:
            return await session.scalar(
                select(DriverKycSubmission).where(
                    DriverKycSubmission.driver_profile_id == application.driver_profile_id
                )
            )

    current = asyncio.run(submission())
    _update(
        db_sessionmaker,
        DriverKycReviewDecision,
        DriverKycReviewDecision.submission_id == current.id,
        document_reviews={"driver_license": {"status": "accepted", "expires_on": "2000-01-01"}},
    )
    assert _state(db_client, token) == ("details", "details_changes_needed", EXPIRED)
    _update(
        db_sessionmaker,
        DriverKycReviewDecision,
        DriverKycReviewDecision.submission_id == current.id,
        document_reviews={},
    )

    async def remove_payout_check():
        async with db_sessionmaker() as session:
            await session.execute(
                delete(PayeeBankAccountPayoutVerification).where(
                    PayeeBankAccountPayoutVerification.bank_account_version_id
                    == current.bank_account_version_id
                )
            )
            await session.commit()

    asyncio.run(remove_payout_check())
    assert _state(db_client, token) == ("details", "details_in_review", None)


def test_car_states_and_the_link_closes_after_final_approval(db_client, db_sessionmaker, settings):
    token, application, admin = _approved_applicant(
        db_client, db_sessionmaker, settings, suffix="state-car"
    )
    files = _seed_vehicle_files(db_sessionmaker, application=application, suffix="state-car")
    submitted = db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle", json=_vehicle_payload(token, files)
    ).json()
    assert _state(db_client, token) == ("car", "car_in_review", None)
    rejected = db_client.post(
        _decision_path(application.id, submitted["vehicle_id"], submitted["submission_id"]),
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "decision": "rejected",
            "reason_code": "not_roadworthy",
        },
    )
    assert rejected.status_code == 200, rejected.text
    assert _state(db_client, token) == (
        "car",
        "car_changes_needed",
        "The car did not pass the roadworthiness check.",
    )
    _update(
        db_sessionmaker,
        VehicleEvidenceSubmission,
        VehicleEvidenceSubmission.id == submitted["submission_id"],
        status="expired",
    )
    assert _state(db_client, token) == ("car", "car_changes_needed", EXPIRED)
    second = db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle",
        json=_vehicle_payload(token, files, vehicle_id=submitted["vehicle_id"], color="Silver"),
    )
    assert second.status_code == 201, second.text
    assert _state(db_client, token) == ("car", "car_in_review", None)
    _approve_vehicle(
        db_client,
        db_sessionmaker,
        application=application,
        admin=admin,
        submitted=second.json(),
        files=files,
    )
    # Final approval closes the application and its link; the setup email takes over.
    closed = db_client.post(CONTINUE, json={"application_access_token": token})
    assert closed.status_code == 404
    assert closed.json()["error"]["code"] == "ONBOARDING_ACCESS_INVALID"

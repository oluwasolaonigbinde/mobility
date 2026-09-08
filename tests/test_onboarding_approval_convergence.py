import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from conftest import auth_headers
from sqlalchemy import func, select
from test_driver_person_payee_onboarding import (
    PASSWORD,
    _complete_admin_review,
    _person_payee_payload,
    _seed_clean_kyc_files,
)
from test_driver_vehicle_approval import (
    _approved_applicant,
    _decision_path,
    _review_files,
    _seed_vehicle_files,
    _vehicle_payload,
)

from app.models.audit import AuditEvent
from app.models.driver_application import DriverApplication
from app.models.kyc import (
    DriverKycReviewDecision,
    DriverKycSubmission,
    VehicleEvidenceReviewDecision,
)
from app.models.user import User
from app.services import vehicle_onboarding


def prepare(client, maker, settings):
    token, application, admin = _approved_applicant(client, maker, settings, suffix="convergence")
    files = _seed_vehicle_files(maker, application=application, suffix="convergence")
    response = client.post(
        "/api/v1/auth/driver-onboarding/vehicle", json=_vehicle_payload(token, files)
    )
    assert response.status_code == 201, response.text
    submitted = response.json()

    async def seed_expired_current_projection():
        async with maker() as session:
            current = await session.scalar(
                select(DriverKycSubmission).where(
                    DriverKycSubmission.driver_profile_id == application.driver_profile_id
                )
            )
            current.status = "expired"
            await session.commit()

    asyncio.run(seed_expired_current_projection())
    person_files = _seed_clean_kyc_files(maker, email="person-payee-convergence@example.com")
    response = client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json=_person_payee_payload(token, person_files),
    )
    assert response.status_code == 201, response.text
    _complete_admin_review(client, maker, admin=admin, application=application, files=person_files)
    _review_files(client, maker, admin=admin, submission_id=submitted["submission_id"], files=files)
    requests = {
        "person": (
            f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision",
            {
                "client_request_id": str(uuid4()),
                "decision": "approved",
                "reason_code": "complete_current_evidence",
                "identity_match_confirmed": True,
                "bank_account_match_confirmed": True,
                "documents_readable_confirmed": True,
            },
        ),
        "vehicle": (
            _decision_path(application.id, submitted["vehicle_id"], submitted["submission_id"]),
            {
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
        ),
    }
    return application, auth_headers(client, admin.email, PASSWORD), requests


async def state(maker, application):
    async with maker() as session:
        app = await session.get(DriverApplication, application.id)
        user = await session.get(User, application.user_id)
        audits = await session.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.action == "admin.driver_application.approved",
                AuditEvent.entity_id == str(application.id),
            )
        )
        decisions = [
            await session.scalar(select(func.count(model.id)))
            for model in (DriverKycReviewDecision, VehicleEvidenceReviewDecision)
        ]
        return app.status, user.status, audits, decisions


@pytest.mark.parametrize("order", [("vehicle", "person"), ("person", "vehicle")])
def test_both_approval_orders_converge_without_user_activation(
    postgis_db_client, postgis_db_sessionmaker, settings, order
):
    application, headers, requests = prepare(postgis_db_client, postgis_db_sessionmaker, settings)
    for stage in order:
        path, body = requests[stage]
        response = postgis_db_client.post(path, json=body, headers=headers)
        assert response.status_code == 200, response.text
    assert asyncio.run(state(postgis_db_sessionmaker, application)) == (
        "approved",
        "invited",
        1,
        [2, 1],
    )
    for path, body in requests.values():
        assert postgis_db_client.post(path, json=body, headers=headers).status_code == 200
    assert asyncio.run(state(postgis_db_sessionmaker, application)) == (
        "approved",
        "invited",
        1,
        [2, 1],
    )


@pytest.mark.parametrize("retry_stage", ["person", "vehicle"])
def test_exact_review_retry_repairs_legacy_pending_projection(
    postgis_db_client, postgis_db_sessionmaker, settings, monkeypatch, retry_stage
):
    application, headers, requests = prepare(postgis_db_client, postgis_db_sessionmaker, settings)
    with monkeypatch.context() as legacy:
        legacy.setattr(
            vehicle_onboarding, "terminalize_driver_application", AsyncMock(return_value=False)
        )
        for path, body in requests.values():
            response = postgis_db_client.post(path, json=body, headers=headers)
            assert response.status_code == 200, response.text
    assert asyncio.run(state(postgis_db_sessionmaker, application)) == (
        "pending",
        "invited",
        0,
        [2, 1],
    )
    path, body = requests[retry_stage]
    response = postgis_db_client.post(path, json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert asyncio.run(state(postgis_db_sessionmaker, application)) == (
        "approved",
        "invited",
        1,
        [2, 1],
    )

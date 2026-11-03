"""Email-dependent entry points fail honestly before creating undeliverable work."""

import asyncio
from uuid import uuid4

import pytest
from conftest import auth_headers, create_test_user
from sqlalchemy import func, select
from test_driver_applications import enable_registration

from app.models.contact import PasswordResetAttempt, PasswordResetToken
from app.models.driver_application import (
    DriverAccountSetupToken,
    DriverApplication,
    DriverApplicationAccessToken,
)
from app.models.notification import Notification
from app.models.organization import OrganizationMembership
from app.models.user import User
from app.services.email_availability import (
    APPLICATION_LINK_UNAVAILABLE,
    APPLICATION_UNAVAILABLE,
    INVITE_UNAVAILABLE,
    RESET_UNAVAILABLE,
)


def effects(maker):
    async def read():
        async with maker() as session:
            counts = []
            for model in (
                User,
                DriverApplication,
                DriverApplicationAccessToken,
                DriverAccountSetupToken,
                PasswordResetAttempt,
                PasswordResetToken,
                Notification,
            ):
                counts.append(int(await session.scalar(select(func.count(model.id))) or 0))
            return tuple(counts)

    return asyncio.run(read())


@pytest.mark.parametrize(
    "path,payload,message",
    [
        (
            "/api/v1/auth/register-driver",
            {"full_name": "New Driver", "service_city": "Abuja"},
            APPLICATION_UNAVAILABLE,
        ),
        ("/api/v1/auth/driver-onboarding-access/request", {}, APPLICATION_LINK_UNAVAILABLE),
        ("/api/v1/auth/password-reset/request", {}, RESET_UNAVAILABLE),
    ],
)
def test_public_email_off_refuses_without_enumeration_or_writes(
    db_client, db_sessionmaker, settings, path, payload, message
):
    create_test_user(db_sessionmaker, email="known@demo.mobility.local", role="driver")
    enable_registration(db_client, settings)
    settings.email_provider = ""
    before = effects(db_sessionmaker)
    replies = [
        db_client.post(
            path,
            json=payload | {"email": email},
            headers={"X-Request-ID": "email-availability-test"},
        )
        for email in ("known@demo.mobility.local", "unknown@demo.mobility.local")
    ]
    assert [reply.status_code for reply in replies] == [503, 503]
    assert replies[0].json() == replies[1].json()
    assert replies[0].json()["error"]["code"] == "EMAIL_NOT_CONFIGURED"
    assert replies[0].json()["error"]["message"] == message
    assert effects(db_sessionmaker) == before


def test_configured_public_application_link_and_reset_keep_existing_behaviour(
    db_client, db_sessionmaker, settings
):
    enable_registration(db_client, settings)
    created = db_client.post(
        "/api/v1/auth/register-driver",
        json={"email": "apply@demo.mobility.local", "full_name": "Driver", "service_city": "Abuja"},
    )
    assert created.status_code == 202, created.text
    before = effects(db_sessionmaker)
    assert before[1] == 1 and before[2] == 1 and before[6] == 1
    for email in ("apply@demo.mobility.local", "unknown@demo.mobility.local"):
        renewed = db_client.post(
            "/api/v1/auth/driver-onboarding-access/request", json={"email": email}
        )
        assert renewed.status_code == 202, renewed.text
    create_test_user(db_sessionmaker, email="active@demo.mobility.local", role="driver")
    replies = [
        db_client.post("/api/v1/auth/password-reset/request", json={"email": email})
        for email in ("active@demo.mobility.local", "unknown@demo.mobility.local")
    ]
    assert [reply.status_code for reply in replies] == [202, 202]
    assert replies[0].json() == replies[1].json()
    after = effects(db_sessionmaker)
    assert after[5] == 1 and after[6] > before[6]


@pytest.mark.parametrize("connected", [False, True])
def test_company_create_and_invite_honestly_report_email_state(
    db_client, db_sessionmaker, settings, connected
):
    admin = create_test_user(db_sessionmaker, email="staff@demo.mobility.local")
    headers = auth_headers(db_client, admin.email)
    if not connected:
        settings.email_provider = ""
    created = db_client.post(
        "/api/v1/admin/advertiser-organizations",
        headers=headers,
        json={"name": "New company", "email": "company@demo.mobility.local"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["login_invite_sent"] is connected
    company_id = created.json()["organization"]["id"]
    before = effects(db_sessionmaker)
    assert before[5] == int(connected) and before[6] == int(connected)
    sent = db_client.post(
        f"/api/v1/admin/advertiser-organizations/{company_id}/login-invite",
        headers=headers,
        json={"email": "company@demo.mobility.local"},
    )
    assert sent.status_code == (200 if connected else 503), sent.text
    if not connected:
        assert sent.json()["error"]["code"] == "EMAIL_NOT_CONFIGURED"
        assert sent.json()["error"]["message"] == INVITE_UNAVAILABLE
        assert effects(db_sessionmaker) == before

    async def membership():
        async with db_sessionmaker() as session:
            member = await session.scalar(select(OrganizationMembership))
            user = await session.get(User, member.user_id)
            assert member.status == "invited" and user.status == "invited"

    asyncio.run(membership())


@pytest.mark.parametrize("connected", [False, True])
def test_driver_invite_email_off_blocks_only_invite_not_review_decisions(
    db_client, db_sessionmaker, settings, connected
):
    # Approve with email off as well: recording decisions must remain available.
    if not connected:
        settings.email_provider = ""
    # Preparation itself registers a public applicant, so connect for that step.
    from test_onboarding_approval_convergence import prepare

    provider = settings.email_provider
    settings.email_provider = "smtp"
    application, headers, requests = prepare(db_client, db_sessionmaker, settings)
    settings.email_provider = provider
    for stage in ("person", "vehicle"):
        path, body = requests[stage]
        response = db_client.post(path, json=body, headers=headers)
        assert response.status_code == 200, response.text
    before = effects(db_sessionmaker)
    reply = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/account-setup",
        headers=headers,
        json={"client_request_id": str(uuid4())},
    )
    assert reply.status_code == (201 if connected else 503), reply.text
    if connected:
        assert effects(db_sessionmaker)[3] == before[3] + 1
    else:
        assert reply.json()["error"]["code"] == "EMAIL_NOT_CONFIGURED"
        assert reply.json()["error"]["message"] == INVITE_UNAVAILABLE
        assert effects(db_sessionmaker) == before

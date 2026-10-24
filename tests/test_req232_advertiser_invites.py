import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import auth_headers, create_test_organization, create_test_user
from sqlalchemy import select
from test_req234_report_ready import CaptureEmail

from app.core.errors import AppError
from app.models.contact import PasswordResetToken
from app.models.notification import Notification
from app.models.organization import AdvertiserOrganization, OrganizationMembership
from app.models.user import User, UserRole
from app.services.account_recovery import password_reset_token_for_delivery, request_password_reset
from app.services.advertiser_invites import complete_login_invite, send_login_invite
from app.services.email_delivery import process_email_notification


def company_without_login(maker):
    admin = create_test_user(maker, email="invite-staff@example.invalid")
    company, _ = create_test_organization(maker, name="Invited company")
    return admin, company


async def token_rows(session, settings):
    reset = await session.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.purpose == "advertiser_invite",
            PasswordResetToken.used_at.is_(None),
        )
    )
    assert reset is not None
    user = await session.get(User, reset.user_id)
    assert user is not None
    token = password_reset_token_for_delivery(reset, user, settings)
    return reset, user, token


@pytest.mark.parametrize("origin", [True, False])
def test_explicit_invite_email_and_password_activate_one_login_without_auto_sign_in(
    db_client, db_sessionmaker, settings, origin
):
    admin, company = company_without_login(db_sessionmaker)
    settings.public_origin = "http://localhost:3221" if origin else ""
    settings.password_reset_public_url = "http://localhost:3221/reset-password"
    headers = auth_headers(db_client, admin.email)
    url = f"/api/v1/admin/advertiser-organizations/{company.id}"
    assert db_client.get(url + "/members", headers=headers).json()["login_invite_available"] is True
    sent = db_client.post(
        url + "/login-invite", headers=headers, json={"email": " NEW@EXAMPLE.INVALID "}
    )
    assert sent.status_code == 200, sent.text
    assert set(sent.json()) == {"message"}

    async def inspect_and_deliver():
        async with db_sessionmaker() as session:
            reset, user, token = await token_rows(session, settings)
            assert user.status == "invited" and user.role == "advertiser"
            assert reset.expires_at - reset.created_at == timedelta(hours=24)
            assert reset.attempt_id is None and reset.organization_id == company.id
            assert reset.token_hash == hashlib.sha256(token.encode()).hexdigest()
            membership = await session.scalar(
                select(OrganizationMembership).where(OrganizationMembership.user_id == user.id)
            )
            assert membership.status == "invited" and membership.role == "advertiser"
            assert (
                await request_password_reset(
                    session, email=user.email, client_ip="127.0.0.1", settings=settings
                )
                is None
            )
            await session.commit()
            notices = list(await session.scalars(select(Notification)))
            assert len(notices) == 1
            notice = notices[0]
            assert notice.type_key == "advertiser_login_invite"
            assert set(notice.payload) == {"password_reset_request_id"}
        mail = CaptureEmail()
        assert (
            await process_email_notification(
                db_sessionmaker,
                notification_id=notice.id,
                settings=settings,
                email_adapter=mail,
                now=datetime.now(UTC),
            )
            == "sent"
        )
        assert len(mail.messages) == 1
        body = mail.messages[0].text_body
        assert "24 hours" in body and "invited" in body
        link = urlsplit(body.split("Set password: ", 1)[1])
        assert link.path == "/advertiser-invite" and not link.query
        assert parse_qs(link.fragment) == {"token": [token]}
        return token

    token = asyncio.run(inspect_and_deliver())
    assert (
        db_client.post(
            "/api/v1/auth/password-reset/complete",
            json={"token": token, "new_password": "chosen-long-password"},
        ).status_code
        == 400
    )
    completed = db_client.post(
        "/api/v1/auth/advertiser-invite/complete",
        json={"token": token, "new_password": "chosen-long-password"},
    )
    assert completed.status_code == 200, completed.text
    assert set(completed.json()) == {"message"}
    assert "set-cookie" not in completed.headers
    assert (
        db_client.post(
            "/api/v1/auth/advertiser-invite/complete",
            json={"token": token, "new_password": "chosen-long-password"},
        ).status_code
        == 400
    )
    assert (
        db_client.get(url + "/members", headers=headers).json()["login_invite_available"] is False
    )
    assert (
        db_client.post(
            url + "/login-invite", headers=headers, json={"email": "another@example.invalid"}
        ).status_code
        == 409
    )
    signed_in = db_client.post(
        "/api/v1/auth/login",
        json={"email": "new@example.invalid", "password": "chosen-long-password"},
    )
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["user"]["status"] == "active"


def test_resend_replaces_tokens_and_a_different_email_disables_the_old_pending_login(
    db_sessionmaker, settings
):
    admin, company = company_without_login(db_sessionmaker)

    async def exercise():
        async def send(email):
            async with db_sessionmaker() as session:
                await send_login_invite(
                    session,
                    organization_id=company.id,
                    actor_user_id=admin.id,
                    email=email,
                    settings=settings,
                )
                await session.commit()
                return await token_rows(session, settings)

        first, original, old_token = await send("first@example.invalid")
        second, same, resend_token = await send("first@example.invalid")
        assert same.id == original.id and first.id != second.id
        third, replacement, current_token = await send("second@example.invalid")
        assert replacement.id != original.id
        for stale in [old_token, resend_token]:
            async with db_sessionmaker() as session:
                with pytest.raises(AppError, match="invalid, expired, or already used"):
                    await complete_login_invite(
                        session, token=stale, new_password="chosen-long-password", settings=settings
                    )
        async with db_sessionmaker() as session:
            old = await session.get(User, original.id)
            assert old.status == "disabled"
            member = await session.scalar(
                select(OrganizationMembership).where(OrganizationMembership.user_id == old.id)
            )
            assert member.status == "disabled"
            for identity in [first.id, second.id]:
                assert (await session.get(PasswordResetToken, identity)).used_at is not None
            assert third.used_at is None
            await complete_login_invite(
                session, token=current_token, new_password="chosen-long-password", settings=settings
            )
            await session.commit()

    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["expired", "user", "membership", "company", "session"])
def test_invite_completion_rechecks_current_authority(
    db_sessionmaker, settings, monkeypatch, change
):
    admin, company = company_without_login(db_sessionmaker)

    async def exercise():
        async with db_sessionmaker() as session:
            await send_login_invite(
                session,
                organization_id=company.id,
                actor_user_id=admin.id,
                email="pending@example.invalid",
                settings=settings,
            )
            await session.commit()
            reset, user, token = await token_rows(session, settings)
            if change == "expired":

                async def clock(_session):
                    return reset.expires_at

                monkeypatch.setattr("app.services.advertiser_invites.database_clock", clock)
            elif change == "user":
                user.status = "suspended"
            elif change == "session":
                user.session_version += 1
            elif change == "company":
                (await session.get(AdvertiserOrganization, company.id)).status = "suspended"
            else:
                member = await session.scalar(
                    select(OrganizationMembership).where(OrganizationMembership.user_id == user.id)
                )
                member.status = "disabled"
            await session.commit()
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as denied:
                await complete_login_invite(
                    session, token=token, new_password="chosen-long-password", settings=settings
                )
            assert denied.value.code == "ADVERTISER_INVITE_INVALID"
            assert (await session.get(PasswordResetToken, reset.id)).used_at is None

    asyncio.run(exercise())


def test_existing_login_email_is_refused_without_new_members_or_tokens(db_client, db_sessionmaker):
    admin, company = company_without_login(db_sessionmaker)
    existing = create_test_user(
        db_sessionmaker, email="existing@example.invalid", role=UserRole.ADVERTISER
    )
    url = f"/api/v1/admin/advertiser-organizations/{company.id}/login-invite"
    assert db_client.post(url, json={"email": existing.email}).status_code == 401
    assert (
        db_client.post(
            url,
            headers=auth_headers(db_client, existing.email),
            json={"email": "other@example.invalid"},
        ).status_code
        == 403
    )
    response = db_client.post(
        url, headers=auth_headers(db_client, admin.email), json={"email": existing.email}
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "ADVERTISER_LOGIN_EXISTS"

    async def verify():
        async with db_sessionmaker() as session:
            assert not list(await session.scalars(select(OrganizationMembership)))
            assert not list(await session.scalars(select(PasswordResetToken)))

    asyncio.run(verify())


def test_concurrent_resends_leave_one_pending_login_and_one_live_token(db_sessionmaker, settings):
    admin, company = company_without_login(db_sessionmaker)

    async def exercise():
        async def send(email):
            async with db_sessionmaker() as session:
                await send_login_invite(
                    session,
                    organization_id=company.id,
                    actor_user_id=admin.id,
                    email=email,
                    settings=settings,
                )
                await session.commit()

        await asyncio.wait_for(
            asyncio.gather(send("first@example.invalid"), send("second@example.invalid")),
            timeout=10,
        )
        async with db_sessionmaker() as session:
            pending = list(
                await session.scalars(
                    select(OrganizationMembership).where(OrganizationMembership.status == "invited")
                )
            )
            tokens = list(
                await session.scalars(
                    select(PasswordResetToken).where(PasswordResetToken.used_at.is_(None))
                )
            )
            assert len(pending) == len(tokens) == 1
            assert pending[0].user_id == tokens[0].user_id

    asyncio.run(exercise())


def test_same_email_race_between_companies_refuses_one_without_partial_invite(
    db_sessionmaker, settings
):
    admin, first = company_without_login(db_sessionmaker)
    second, _ = create_test_organization(db_sessionmaker, name="Second company")

    async def exercise():
        async def send(company):
            async with db_sessionmaker() as session:
                try:
                    await send_login_invite(
                        session,
                        organization_id=company.id,
                        actor_user_id=admin.id,
                        email="shared@example.invalid",
                        settings=settings,
                    )
                    await session.commit()
                    return "sent"
                except AppError as error:
                    await session.rollback()
                    return error.code

        outcomes = await asyncio.wait_for(asyncio.gather(send(first), send(second)), timeout=10)
        assert sorted(outcomes) == ["ADVERTISER_LOGIN_EXISTS", "sent"]
        async with db_sessionmaker() as session:
            assert len(list(await session.scalars(select(OrganizationMembership)))) == 1
            assert len(list(await session.scalars(select(PasswordResetToken)))) == 1

    asyncio.run(exercise())


def test_add_company_creates_invite_atomically_and_refuses_existing_email_without_rows(
    db_client, db_sessionmaker, settings
):
    admin = create_test_user(db_sessionmaker, email="add-company-staff@example.invalid")
    headers = auth_headers(db_client, admin.email)
    path = "/api/v1/admin/advertiser-organizations"
    assert (
        db_client.post(path, json={"name": "Denied", "email": "x@example.invalid"}).status_code
        == 401
    )
    created = db_client.post(
        path,
        headers=headers,
        json={"name": "New company", "email": " NEW@EXAMPLE.INVALID ", "currency": "ngn"},
    )
    assert created.status_code == 201, created.text
    company_id = created.json()["organization"]["id"]
    assert set(created.json()) == {"organization"}
    assert created.json()["organization"]["currency"] == "NGN"
    refused = db_client.post(
        path, headers=headers, json={"name": "Must not exist", "email": "new@example.invalid"}
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "ADVERTISER_LOGIN_EXISTS"
    assert (
        db_client.post(
            path, headers=headers, json={"name": "Obsolete", "owner_user_id": str(admin.id)}
        ).status_code
        == 422
    )

    async def verify():
        async with db_sessionmaker() as session:
            companies = list(await session.scalars(select(AdvertiserOrganization)))
            assert len(companies) == 1 and str(companies[0].id) == company_id
            reset, user, token = await token_rows(session, settings)
            assert user.status == "invited" and str(reset.organization_id) == company_id
            assert len(list(await session.scalars(select(OrganizationMembership)))) == 1
            assert len(list(await session.scalars(select(Notification)))) == 1
        return user, token

    user, token = asyncio.run(verify())
    assert (
        db_client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "chosen-long-password"}
        ).status_code
        == 401
    )
    assert (
        db_client.patch(
            f"/api/v1/admin/users/{user.id}", headers=headers, json={"status": "active"}
        ).status_code
        == 409
    )
    assert (
        db_client.patch(
            f"/api/v1/admin/users/{user.id}",
            headers=headers,
            json={"role": "driver", "status": "active"},
        ).status_code
        == 409
    )
    complete = db_client.post(
        "/api/v1/auth/advertiser-invite/complete",
        json={"token": token, "new_password": "chosen-long-password"},
    )
    assert complete.status_code == 200, complete.text
    assert (
        db_client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "chosen-long-password"}
        ).status_code
        == 200
    )


def test_add_company_service_rolls_back_company_even_if_caller_commits_after_refusal(
    db_sessionmaker, settings
):
    from app.schemas.organizations import AdminOrganizationCreate
    from app.services.advertiser_invites import create_company_with_invite

    admin = create_test_user(db_sessionmaker, email="transaction-staff@example.invalid")

    async def exercise():
        async with db_sessionmaker() as session:
            with pytest.raises(AppError):
                await create_company_with_invite(
                    session,
                    payload=AdminOrganizationCreate(name="No company", email=admin.email),
                    actor_user_id=admin.id,
                    settings=settings,
                )
            await session.commit()
            assert not list(await session.scalars(select(AdvertiserOrganization)))
            assert not list(await session.scalars(select(OrganizationMembership)))
            assert not list(await session.scalars(select(PasswordResetToken)))
            assert not list(await session.scalars(select(Notification)))

    asyncio.run(exercise())


def test_advertiser_temporary_password_creation_and_role_conversion_are_refused(
    db_client, db_sessionmaker
):
    admin = create_test_user(db_sessionmaker, email="role-staff@example.invalid")
    driver = create_test_user(
        db_sessionmaker, email="role-driver@example.invalid", role=UserRole.DRIVER
    )
    headers = auth_headers(db_client, admin.email)
    response = db_client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "no-password@example.invalid",
            "full_name": "Not created",
            "role": "advertiser",
            "status": "active",
            "password": "staff-chosen-password",
        },
    )
    assert response.status_code == 422
    converted = db_client.patch(
        f"/api/v1/admin/users/{driver.id}", headers=headers, json={"role": "advertiser"}
    )
    assert converted.status_code == 409
    assert converted.json()["error"]["code"] == "ADVERTISER_ACTIVATION_REQUIRES_INVITE"


@pytest.mark.parametrize("intermediate", ["suspended", "disabled"])
@pytest.mark.parametrize("change", [{"status": "active"}, {"role": "driver"}, {"role": "admin"}])
def test_pending_invite_cannot_be_bypassed_by_status_hops(
    db_client, db_sessionmaker, intermediate, change
):
    admin, company = company_without_login(db_sessionmaker)
    headers = auth_headers(db_client, admin.email)
    sent = db_client.post(
        f"/api/v1/admin/advertiser-organizations/{company.id}/login-invite",
        headers=headers,
        json={"email": "hop@example.invalid"},
    )
    assert sent.status_code == 200

    async def pending_id():
        async with db_sessionmaker() as session:
            return (
                await session.scalar(select(User).where(User.email == "hop@example.invalid"))
            ).id

    user_id = asyncio.run(pending_id())
    path = f"/api/v1/admin/users/{user_id}"
    assert db_client.patch(path, headers=headers, json={"status": intermediate}).status_code == 200
    assert db_client.patch(path, headers=headers, json=change).status_code == 409
    recovered = db_client.post(
        "/api/v1/auth/password-reset/request", json={"email": "hop@example.invalid"}
    )
    assert recovered.status_code == 202

    async def verify():
        async with db_sessionmaker() as session:
            assert not list(
                await session.scalars(
                    select(PasswordResetToken).where(PasswordResetToken.purpose == "password_reset")
                )
            )
            user = await session.get(User, user_id)
            assert user.status == intermediate and user.role == "advertiser"

    asyncio.run(verify())


@pytest.mark.parametrize("create_company", [False, True])
def test_invite_commands_recheck_session_after_dependency_authentication(
    db_client, db_sessionmaker, monkeypatch, create_company
):
    import app.api.v1.admin as admin_routes

    admin, company = company_without_login(db_sessionmaker)
    function_name = "create_company_with_invite" if create_company else "send_login_invite"
    original = getattr(admin_routes, function_name)

    async def revoked(session, **kwargs):
        async with db_sessionmaker() as revoking:
            actor = await revoking.get(User, kwargs["actor_user_id"])
            actor.session_version += 1
            await revoking.commit()
        return await original(session, **kwargs)

    monkeypatch.setattr(admin_routes, function_name, revoked)
    path = "/api/v1/admin/advertiser-organizations"
    body = {"email": "revoked@example.invalid"}
    if create_company:
        body["name"] = "Not created"
    else:
        path += f"/{company.id}/login-invite"
    response = db_client.post(path, headers=auth_headers(db_client, admin.email), json=body)
    assert response.status_code == 403, response.text

    async def verify():
        async with db_sessionmaker() as session:
            assert len(list(await session.scalars(select(AdvertiserOrganization)))) == 1
            assert not list(await session.scalars(select(PasswordResetToken)))
            assert not list(await session.scalars(select(OrganizationMembership)))
            assert not list(await session.scalars(select(Notification)))

    asyncio.run(verify())


def test_resend_and_staff_user_edit_use_the_same_user_lock_order(
    db_sessionmaker, settings, monkeypatch
):
    from uuid import UUID

    from sqlalchemy import update

    import app.services.advertiser_invites as invites

    admin, company = company_without_login(db_sessionmaker)
    old_admin_id = admin.id
    admin.id = UUID(int=(1 << 128) - 1)

    async def exercise():
        async with db_sessionmaker() as setup:
            await setup.execute(update(User).where(User.id == old_admin_id).values(id=admin.id))
            await send_login_invite(
                setup,
                organization_id=company.id,
                actor_user_id=admin.id,
                email="ordered@example.invalid",
                settings=settings,
            )
            await setup.commit()
            _, pending, _ = await token_rows(setup, settings)
        entered = asyncio.Event()
        original = invites._lock_users

        async def observed(session, ids):
            entered.set()
            return await original(session, ids)

        monkeypatch.setattr(invites, "_lock_users", observed)

        async def resend():
            async with db_sessionmaker() as session:
                await send_login_invite(
                    session,
                    organization_id=company.id,
                    actor_user_id=admin.id,
                    email=pending.email,
                    settings=settings,
                )
                await session.commit()

        async with db_sessionmaker() as editing:
            # This is the first lock of update_user's UUID-ordered SELECT.
            await editing.scalar(select(User).where(User.id == pending.id).with_for_update())
            contender = asyncio.create_task(resend())
            await asyncio.wait_for(entered.wait(), timeout=3)
            await asyncio.sleep(0.1)
            assert not contender.done()
            await asyncio.wait_for(
                editing.scalar(select(User).where(User.id == admin.id).with_for_update()), timeout=3
            )
            await editing.commit()
            await asyncio.wait_for(contender, timeout=5)

    asyncio.run(exercise())

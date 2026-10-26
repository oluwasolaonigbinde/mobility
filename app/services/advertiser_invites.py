"""Explicit first-login invitations use the existing password-token store (D130)."""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_password_async
from app.models.contact import PasswordResetToken
from app.models.notification import NotificationChannel, NotificationType
from app.models.organization import AdvertiserOrganization, OrganizationMembership
from app.models.user import User
from app.schemas.organizations import AdminOrganizationCreate, AdvertiserOrganizationCreate
from app.services.account_recovery import _reset_token_value, _token_id, _utc
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.driver_applications import _is_user_email_conflict
from app.services.notifications import create_notification
from app.services.organizations import create_advertiser_organization
from app.services.payout_rule_serialization import database_clock
from app.services.users import _lock_users, normalize_email, validate_password_length

ADVERTISER_INVITE_LIFETIME = timedelta(hours=24)


async def _lock_company_invites(session: AsyncSession, organization_id: UUID) -> None:
    key = int.from_bytes(
        hashlib.sha256(f"advertiser-invite:{organization_id}".encode()).digest()[:8],
        byteorder="big",
        signed=True,
    )
    await session.execute(select(func.pg_advisory_xact_lock(key)))


async def create_company_with_invite(
    session: AsyncSession,
    *,
    payload: AdminOrganizationCreate,
    actor_user_id: UUID,
    settings: Settings,
    actor_session_version: int | None = None,
) -> AdvertiserOrganization:
    await require_active_admin(
        session, actor_user_id, expected_session_version=actor_session_version
    )
    # One savepoint also protects service callers: a refused invite leaves no company.
    async with session.begin_nested():
        organization, _ = await create_advertiser_organization(
            session,
            AdvertiserOrganizationCreate(name=payload.name, currency=payload.currency),
            settings,
        )
        await send_login_invite(
            session,
            organization_id=organization.id,
            actor_user_id=actor_user_id,
            email=payload.email,
            settings=settings,
            actor_session_version=actor_session_version,
        )
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="admin.advertiser_organization.created",
            entity_type="advertiser_organization",
            entity_id=str(organization.id),
            metadata={"name": organization.name},
        )
    return organization


async def login_invite_available(
    session: AsyncSession, organization: AdvertiserOrganization
) -> bool:
    if organization.status != "active":
        return False
    return (
        await session.scalar(
            select(OrganizationMembership.id)
            .where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.status == "active",
            )
            .limit(1)
        )
        is None
    )


def login_exists() -> AppError:
    return AppError(
        "ADVERTISER_LOGIN_EXISTS",
        "This email already has a Cardvert login. Use a different email.",
        status_code=409,
    )


async def _replace_pending_invites(
    session: AsyncSession,
    pending: list[OrganizationMembership],
    replacement: User,
    now: datetime,
    actor_user_id: UUID,
) -> None:
    prior_users = await _lock_users(session, {member.user_id for member in pending})
    for member in pending:
        prior_user = prior_users.get(member.user_id)
        if prior_user is None:
            raise RuntimeError("pending company login disappeared")
        if prior_user.id != replacement.id:
            if prior_user.status != "invited" or prior_user.role != "advertiser":
                raise AppError(
                    "COMPANY_LOGIN_UNAVAILABLE",
                    "Check this company's existing login before sending an invite.",
                    status_code=409,
                )
            prior_user.status, member.status = "disabled", "disabled"
            await create_audit_event(
                session,
                actor_user_id=actor_user_id,
                action="advertiser.login_invite.replaced",
                entity_type="user",
                entity_id=str(prior_user.id),
                metadata={
                    "organization_id": str(member.organization_id),
                    "replacement_user_id": str(replacement.id),
                },
            )
        prior_user.session_version += 1
        resets = await session.scalars(
            select(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == prior_user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .order_by(PasswordResetToken.id)
            .with_for_update()
        )
        for reset in resets:
            reset.used_at = now


async def send_login_invite(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    email: str,
    settings: Settings,
    actor_session_version: int | None = None,
) -> PasswordResetToken:
    await _lock_company_invites(session, organization_id)
    pending_ids = set(
        await session.scalars(
            select(OrganizationMembership.user_id).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.status == "invited",
            )
        )
    )
    # Company invite serialization keeps discovery stable; administrative user
    # commands all take actor and target locks in UUID order.
    await _lock_users(session, pending_ids | {actor_user_id})
    await require_active_admin(
        session, actor_user_id, expected_session_version=actor_session_version
    )
    organization = await session.scalar(
        select(AdvertiserOrganization)
        .where(
            AdvertiserOrganization.id == organization_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if organization is None:
        raise AppError("ORGANIZATION_NOT_FOUND", "Company was not found.", status_code=404)
    if not await login_invite_available(session, organization):
        raise AppError(
            "COMPANY_LOGIN_UNAVAILABLE",
            "This company already has a login, or is unavailable for an invite.",
            status_code=409,
        )
    normalized = normalize_email(email)
    if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", normalized):
        raise AppError("INVALID_EMAIL", "Enter a valid email address.", status_code=400)
    pending = list(
        await session.scalars(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.status == "invited",
            )
            .order_by(OrganizationMembership.user_id)
            .with_for_update()
        )
    )
    user = await session.scalar(
        select(User).where(User.email == normalized).execution_options(populate_existing=True)
    )
    same_member = next((member for member in pending if user and member.user_id == user.id), None)
    if user is not None and (
        same_member is None or user.role != "advertiser" or user.status != "invited"
    ):
        raise login_exists()
    resend = user is not None
    if user is None:
        user = User(
            email=normalized,
            password_hash=await hash_password_async(secrets.token_urlsafe(64)),
            full_name=organization.name,
            role="advertiser",
            status="invited",
        )
        try:
            async with session.begin_nested():
                session.add(user)
                await session.flush()
        except IntegrityError as exc:
            if not _is_user_email_conflict(exc):
                raise
            raise login_exists() from exc
    now = await database_clock(session)
    await _replace_pending_invites(session, pending, user, now, actor_user_id)
    if same_member is None:
        session.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role="advertiser",
                status="invited",
            )
        )
    reset = PasswordResetToken(
        id=uuid4(),
        purpose="advertiser_invite",
        attempt_id=None,
        organization_id=organization.id,
        user_id=user.id,
        token_hash="0" * 64,
        session_version=user.session_version,
        created_at=now,
        expires_at=now + ADVERTISER_INVITE_LIFETIME,
    )
    reset.token_hash = hashlib.sha256(
        _reset_token_value(reset, user, settings).encode()
    ).hexdigest()
    session.add(reset)
    await session.flush()
    await create_notification(
        session,
        recipient_user_id=user.id,
        type_key=NotificationType.ADVERTISER_LOGIN_INVITE,
        channel=NotificationChannel.TRANSACTIONAL_EMAIL,
        dedupe_key=f"advertiser_login_invite:v1:{reset.id}:transactional_email",
        payload={"password_reset_request_id": str(reset.id)},
    )
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="advertiser.login_invite.sent",
        entity_type="user",
        entity_id=str(user.id),
        metadata={
            "organization_id": str(organization.id),
            "resend": resend,
            "expires_at": reset.expires_at.isoformat(),
        },
    )
    return reset


def invalid_invite() -> AppError:
    return AppError(
        "ADVERTISER_INVITE_INVALID",
        "This invite link is invalid, expired, or already used. Ask Terrax for a new invite.",
        status_code=400,
    )


async def pending_invite_membership(session: AsyncSession, reset: PasswordResetToken, user: User):
    if (
        reset.purpose != "advertiser_invite"
        or user.role != "advertiser"
        or user.status != "invited"
    ):
        return None
    organization = await session.get(AdvertiserOrganization, reset.organization_id)
    if organization is None or not await login_invite_available(session, organization):
        return None
    return await session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "invited",
        )
    )


async def complete_login_invite(
    session: AsyncSession,
    *,
    token: str,
    new_password: str,
    settings: Settings,
) -> User:
    validate_password_length(new_password, settings)
    reset = await session.get(PasswordResetToken, _token_id(token)) if _token_id(token) else None
    if reset is None or reset.purpose != "advertiser_invite" or reset.organization_id is None:
        raise invalid_invite()
    # Same order as sending: invite lock, users, company, tokens/membership.
    await _lock_company_invites(session, reset.organization_id)
    user = (await _lock_users(session, {reset.user_id})).get(reset.user_id)
    await session.scalar(
        select(AdvertiserOrganization)
        .where(
            AdvertiserOrganization.id == reset.organization_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    reset = await session.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.id == reset.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = await database_clock(session)
    if (
        reset is None
        or user is None
        or reset.used_at is not None
        or now >= _utc(reset.expires_at)
        or reset.session_version != user.session_version
        or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), reset.token_hash)
    ):
        raise invalid_invite()
    membership = await pending_invite_membership(session, reset, user)
    if membership is None:
        raise invalid_invite()
    reset.used_at = now
    user.password_hash = await hash_password_async(new_password)
    user.status, membership.status = "active", "active"
    user.must_change_password = False
    user.session_version += 1
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=user.id,
        action="advertiser.login_invite.completed",
        entity_type="user",
        entity_id=str(user.id),
        metadata={"organization_id": str(reset.organization_id), "sessions_revoked": True},
    )
    return user

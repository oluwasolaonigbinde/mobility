from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.organization import (
    AdvertiserOrganization,
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
)
from app.models.user import User, UserRole, UserStatus
from app.schemas.organizations import AdvertiserOrganizationCreate
from app.services.audit import create_audit_event
from app.services.users import get_user_by_id

ADVERTISER_PROFILE_FIELDS = frozenset(
    {
        "name",
        "billing_email",
        "address_line_1",
        "address_line_2",
        "address_city",
        "address_region",
        "address_postal_code",
        "address_country_code",
        "industry",
        "operational_contact_name",
        "operational_contact_email",
        "operational_contact_phone",
        "billing_contact_name",
        "billing_contact_phone",
    }
)
ADMIN_PROFILE_FIELDS = ADVERTISER_PROFILE_FIELDS | frozenset(
    {"country_code", "currency", "status", "profile_notes"}
)


def _normalize_profile_value(field: str, value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AppError(
            "INVALID_COMPANY_PROFILE",
            f"{field} must be a string or null",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    normalized = value.strip()
    if not normalized:
        return None
    if field in {"billing_email", "operational_contact_email"}:
        if "@" not in normalized or len(normalized) > 255:
            raise AppError(
                "INVALID_COMPANY_PROFILE",
                f"{field} must be a valid email address",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return normalized.lower()
    if field in {"country_code", "address_country_code"}:
        if len(normalized) != 2 or not normalized.isalpha():
            raise AppError(
                "INVALID_COMPANY_PROFILE",
                f"{field} must be a two-letter country code",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return normalized.upper()
    if field == "currency":
        if len(normalized) != 3 or not normalized.isalpha():
            raise AppError(
                "INVALID_COMPANY_PROFILE",
                "currency must be a three-letter code",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return normalized.upper()
    if field == "status" and normalized not in {"active", "suspended", "disabled"}:
        raise AppError(
            "INVALID_COMPANY_PROFILE",
            "status is not supported",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return normalized


async def _profile_access(
    session: AsyncSession, *, actor_user_id: UUID, organization_id: UUID | None, write: bool
) -> tuple[AdvertiserOrganization, bool]:
    actor = await session.get(User, actor_user_id)
    if actor is None or actor.status != UserStatus.ACTIVE:
        raise AppError(
            "COMPANY_PROFILE_NOT_FOUND", "Company profile was not found", status_code=404
        )
    if actor.role == UserRole.ADMIN:
        if organization_id is None:
            raise AppError(
                "ORGANIZATION_REQUIRED",
                "organization_id is required for an administrator",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        organization = await session.get(AdvertiserOrganization, organization_id)
        if organization is None:
            raise AppError(
                "COMPANY_PROFILE_NOT_FOUND", "Company profile was not found", status_code=404
            )
        return organization, True
    context = await get_advertiser_organization_for_user(session, actor_user_id)
    if context is None or (organization_id is not None and context[0].id != organization_id):
        raise AppError(
            "COMPANY_PROFILE_NOT_FOUND", "Company profile was not found", status_code=404
        )
    organization, membership = context
    if membership.status != MembershipStatus.ACTIVE:
        raise AppError(
            "COMPANY_PROFILE_NOT_FOUND", "Company profile was not found", status_code=404
        )
    if write and membership.role not in {MembershipRole.OWNER, MembershipRole.MANAGER}:
        raise AppError(
            "ORGANIZATION_WRITE_FORBIDDEN",
            "Owner or manager access is required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return organization, False


async def get_company_profile(
    session: AsyncSession, *, actor_user_id: UUID, organization_id: UUID | None = None
) -> AdvertiserOrganization:
    organization, _ = await _profile_access(
        session, actor_user_id=actor_user_id, organization_id=organization_id, write=False
    )
    return organization


async def update_company_profile(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    organization_id: UUID | None,
    changes: dict[str, object],
) -> AdvertiserOrganization:
    organization, is_admin = await _profile_access(
        session, actor_user_id=actor_user_id, organization_id=organization_id, write=True
    )
    if not isinstance(changes, dict) or not changes:
        raise AppError(
            "COMPANY_PROFILE_CHANGES_REQUIRED",
            "At least one company profile change is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    allowed = ADMIN_PROFILE_FIELDS if is_admin else ADVERTISER_PROFILE_FIELDS
    unexpected = sorted(set(changes) - allowed)
    if unexpected:
        raise AppError(
            "COMPANY_PROFILE_FIELD_FORBIDDEN",
            "One or more company profile fields cannot be changed by this actor",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"fields": unexpected},
        )
    before: dict[str, str | None] = {}
    after: dict[str, str | None] = {}
    for field, raw_value in changes.items():
        value = _normalize_profile_value(field, raw_value)
        current = getattr(organization, field)
        current_value = current.value if hasattr(current, "value") else current
        if current_value == value:
            continue
        before[field] = current_value
        after[field] = value
        setattr(organization, field, value)
    if not after:
        return organization
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="advertiser_company_profile.updated",
        entity_type="advertiser_organization",
        entity_id=str(organization.id),
        metadata={
            "before": before,
            "after": after,
            "actor_scope": "admin" if is_admin else "advertiser",
        },
    )
    return organization


async def create_advertiser_organization(
    session: AsyncSession,
    payload: AdvertiserOrganizationCreate,
    settings: Settings,
) -> tuple[AdvertiserOrganization, OrganizationMembership | None]:
    organization = AdvertiserOrganization(
        name=payload.name,
        billing_email=payload.billing_email,
        country_code=payload.country_code,
        currency=(payload.currency or settings.default_currency).upper(),
        status=payload.status,
    )
    session.add(organization)
    await session.flush()

    owner_membership = None
    if payload.owner_user_id is not None:
        owner = await get_user_by_id(session, payload.owner_user_id)
        if owner is None or owner.role != UserRole.ADVERTISER:
            raise AppError(
                "INVALID_OWNER_USER",
                "Organization owner must be an existing advertiser user",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        owner_membership = OrganizationMembership(
            organization_id=organization.id,
            user_id=owner.id,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
        session.add(owner_membership)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise AppError(
                "DUPLICATE_MEMBERSHIP",
                "User is already a member of this organization",
                status_code=status.HTTP_409_CONFLICT,
            ) from exc

    return organization, owner_membership


async def get_advertiser_organization_for_user(
    session: AsyncSession,
    user_id: UUID,
) -> tuple[AdvertiserOrganization, OrganizationMembership] | None:
    result = await session.execute(
        select(AdvertiserOrganization, OrganizationMembership)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == AdvertiserOrganization.id,
        )
        .where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status.in_(
                [MembershipStatus.ACTIVE, MembershipStatus.INVITED]
            ),
        )
        .order_by(OrganizationMembership.created_at.desc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None
    return row[0], row[1]

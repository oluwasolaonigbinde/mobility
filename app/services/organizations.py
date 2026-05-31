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
from app.models.user import UserRole
from app.schemas.organizations import AdvertiserOrganizationCreate
from app.services.users import get_user_by_id


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

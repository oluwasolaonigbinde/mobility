from fastapi import APIRouter

from app.api.v1.dependencies import CurrentUserDependency, SessionDependency
from app.schemas.organizations import MeAdvertiserOrganization, MeResponse
from app.schemas.users import UserRead
from app.services.organizations import get_advertiser_organization_for_user

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeResponse, summary="Get current user context")
async def me(user: CurrentUserDependency, session: SessionDependency) -> MeResponse:
    organization_context = await get_advertiser_organization_for_user(session, user.id)
    advertiser_organization = None
    if organization_context is not None:
        organization, membership = organization_context
        advertiser_organization = MeAdvertiserOrganization(
            id=organization.id,
            name=organization.name,
            currency=organization.currency,
            membership_role=membership.role,
            membership_status=membership.status,
        )

    return MeResponse(
        user=UserRead.model_validate(user),
        advertiser_organization=advertiser_organization,
    )

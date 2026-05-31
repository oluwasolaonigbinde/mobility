from fastapi import APIRouter
from starlette import status

from app.api.v1.dependencies import AdvertiserUserDependency, SessionDependency
from app.core.errors import AppError
from app.schemas.organizations import AdvertiserOrganizationContextResponse
from app.services.organizations import get_advertiser_organization_for_user

router = APIRouter(prefix="/advertiser", tags=["advertiser"])


@router.get(
    "/organization",
    response_model=AdvertiserOrganizationContextResponse,
    summary="Get current advertiser organization",
)
async def advertiser_organization(
    user: AdvertiserUserDependency,
    session: SessionDependency,
) -> AdvertiserOrganizationContextResponse:
    organization_context = await get_advertiser_organization_for_user(session, user.id)
    if organization_context is None:
        raise AppError(
            "ADVERTISER_ORGANIZATION_NOT_FOUND",
            "Advertiser organization was not found for the current user",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    organization, membership = organization_context
    return AdvertiserOrganizationContextResponse(
        organization=organization,
        membership=membership,
    )

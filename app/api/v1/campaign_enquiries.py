import json
from collections.abc import AsyncIterator
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from redis.asyncio import Redis

from app.api.v1.dependencies import AdminUserDependency, SessionDependency, SettingsDependency
from app.core.campaign_enquiry_rate_limit import (
    EnquiryRateLimiter,
    RedisEnquiryRateLimiter,
    UnavailableEnquiryRateLimiter,
)
from app.core.errors import AppError
from app.core.rate_limit import login_client_ip
from app.schemas.campaign_enquiries import (
    CampaignEnquiryConversion,
    CampaignEnquiryConverted,
    CampaignEnquiryCreate,
    CampaignEnquiryRead,
    StaffCampaignEnquiryList,
    StaffCampaignEnquiryRead,
)
from app.services.campaign_enquiries import (
    convert_enquiry,
    enquiry_read,
    save_campaign_enquiry,
    staff_enquiries,
    staff_enquiry,
)

router = APIRouter(tags=["Campaign enquiries"])
MAX_BODY_BYTES = 8192


async def get_enquiry_limiter(settings: SettingsDependency) -> AsyncIterator[EnquiryRateLimiter]:
    if not settings.redis_url:
        yield UnavailableEnquiryRateLimiter()
        return
    try:
        redis = Redis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )
    except ValueError:
        yield UnavailableEnquiryRateLimiter()
        return
    async with redis:
        yield RedisEnquiryRateLimiter(redis, settings)


async def read_enquiry(request: Request) -> CampaignEnquiryCreate:
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise AppError("unsupported_media_type", "Use JSON for this request.", status_code=415)
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise AppError("request_too_large", "Enquiry is too large.", status_code=413)
        chunks.append(chunk)
    try:
        return CampaignEnquiryCreate.model_validate(json.loads(b"".join(chunks)))
    except (ValidationError, ValueError, UnicodeError, RecursionError):
        raise AppError("validation_error", "Check your enquiry details.", status_code=422) from None


@router.post(
    "/campaign-enquiries",
    response_model=CampaignEnquiryRead,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": CampaignEnquiryCreate.model_json_schema()}},
        }
    },
)
async def submit_campaign_enquiry(
    request: Request,
    settings: SettingsDependency,
    limiter: Annotated[EnquiryRateLimiter, Depends(get_enquiry_limiter)],
    session: SessionDependency,
) -> CampaignEnquiryRead:
    enquiry = await read_enquiry(request)
    decision = await limiter.reserve(login_client_ip(request, settings))
    if not decision.storage_available:
        raise AppError(
            "campaign_enquiry_unavailable", "Please contact Terrax by email.", status_code=503
        )
    if not decision.allowed:
        raise AppError(
            "campaign_enquiry_rate_limited",
            "Please wait before sending another enquiry.",
            status_code=429,
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    await save_campaign_enquiry(session, enquiry)
    await session.commit()
    return CampaignEnquiryRead()


@router.get("/admin/campaign-enquiries", response_model=StaffCampaignEnquiryList)
async def list_staff_enquiries(
    user: AdminUserDependency,
    session: SessionDependency,
    status: Literal["new", "converted"] = "new",
    q: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> StaffCampaignEnquiryList:
    items, total = await staff_enquiries(
        session, actor_user_id=user.id, status=status, q=q, limit=limit, offset=offset
    )
    return StaffCampaignEnquiryList(items=items, total=total, limit=limit, offset=offset)


@router.get("/admin/campaign-enquiries/{enquiry_id}", response_model=StaffCampaignEnquiryRead)
async def read_staff_enquiry(
    enquiry_id: UUID, user: AdminUserDependency, session: SessionDependency
):
    return enquiry_read(await staff_enquiry(session, actor_user_id=user.id, enquiry_id=enquiry_id))


@router.post(
    "/admin/campaign-enquiries/{enquiry_id}/create-advertiser",
    response_model=CampaignEnquiryConverted,
)
async def convert_staff_enquiry(
    enquiry_id: UUID,
    payload: CampaignEnquiryConversion,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> CampaignEnquiryConverted:
    organization_id = await convert_enquiry(
        session,
        actor_user_id=user.id,
        enquiry_id=enquiry_id,
        settings=settings,
    )
    await session.commit()
    return CampaignEnquiryConverted(organization_id=organization_id)

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from redis.asyncio import Redis

from app.adapters.messaging.email import EmailAdapter, build_email_adapter
from app.api.v1.dependencies import SettingsDependency
from app.core.campaign_enquiry_rate_limit import (
    EnquiryRateLimiter,
    RedisEnquiryRateLimiter,
    UnavailableEnquiryRateLimiter,
)
from app.core.errors import AppError
from app.core.rate_limit import login_client_ip
from app.schemas.campaign_enquiries import CampaignEnquiryCreate, CampaignEnquiryRead
from app.services.campaign_enquiries import send_campaign_enquiry

router = APIRouter(tags=["Campaign enquiries"])
MAX_BODY_BYTES = 8192


def get_enquiry_email_adapter(settings: SettingsDependency) -> EmailAdapter:
    return build_email_adapter(settings)


async def get_enquiry_limiter(settings: SettingsDependency) -> AsyncIterator[EnquiryRateLimiter]:
    if not settings.campaign_enquiry_enabled or not settings.redis_url:
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
    adapter: Annotated[EmailAdapter, Depends(get_enquiry_email_adapter)],
) -> CampaignEnquiryRead:
    if not settings.campaign_enquiry_enabled:
        raise AppError(
            "campaign_enquiry_unavailable", "Please contact Terrax by email.", status_code=503
        )
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
    await send_campaign_enquiry(enquiry, adapter)
    return CampaignEnquiryRead()

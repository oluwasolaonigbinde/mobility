import io
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

import qrcode
from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.responses import RedirectResponse
from qrcode.image.svg import SvgPathFillImage
from redis.asyncio import Redis

from app.api.v1.dependencies import AdvertiserUserDependency, SessionDependency, SettingsDependency
from app.core.errors import AppError
from app.core.qr_privacy import install_scan_privacy
from app.core.qr_rate_limit import QRRateLimiter
from app.schemas.campaign_engagement import (
    ArtworkLinkRead,
    ArtworkLinkWrite,
    CampaignScansRead,
    LivePositionsRead,
)
from app.services.campaign_engagement import (
    campaign_scans,
    read_artwork_link,
    save_artwork_link,
    stored_destination,
)
from app.services.campaign_live_positions import live_positions

install_scan_privacy()
router = APIRouter(tags=["Campaign engagement"])
PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"}
PUBLIC_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}
CREATIVE = "/advertiser/campaigns/{campaign_id}/creatives/{creative_id}"


async def get_qr_limiter(settings: SettingsDependency):
    redis = Redis.from_url(settings.redis_url) if settings.redis_url else None
    try:
        yield QRRateLimiter(redis)
    finally:
        if redis is not None:
            await redis.aclose()


@router.get(CREATIVE + "/website", response_model=ArtworkLinkRead)
async def get_website(
    campaign_id: UUID,
    creative_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    response: Response,
):
    response.headers.update(PRIVATE_HEADERS)
    return await read_artwork_link(
        session, user_id=current_user.id, campaign_id=campaign_id, creative_id=creative_id
    )


@router.put(CREATIVE + "/website", response_model=ArtworkLinkRead)
async def put_website(
    campaign_id: UUID,
    creative_id: UUID,
    payload: ArtworkLinkWrite,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    response: Response,
):
    response.headers.update(PRIVATE_HEADERS)
    return await save_artwork_link(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        creative_id=creative_id,
        destination=payload.destination,
    )


@router.get(
    CREATIVE + "/qr.svg",
    response_class=Response,
    responses={200: {"content": {"image/svg+xml": {}}}},
)
async def download_qr(
    campaign_id: UUID,
    creative_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
):
    link = await read_artwork_link(
        session, user_id=current_user.id, campaign_id=campaign_id, creative_id=creative_id
    )
    if not link.short_path:
        raise AppError("QR_WEBSITE_REQUIRED", "Add a website link first", status_code=409)
    origin = settings.public_origin.strip().rstrip("/")
    try:
        parsed = urlsplit(origin)
        _ = parsed.port  # Reject malformed configured ports before creating printable codes.
    except ValueError as exc:
        raise AppError(
            "QR_ORIGIN_UNAVAILABLE", "QR download is unavailable. Try again later.", status_code=503
        ) from exc
    local = settings.environment.lower() in {
        "local",
        "development",
        "test",
    } and parsed.hostname in {
        "localhost",
        "127.0.0.1",
    }
    if (
        parsed.scheme not in ({"http", "https"} if local else {"https"})
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise AppError(
            "QR_ORIGIN_UNAVAILABLE", "QR download is unavailable. Try again later.", status_code=503
        )
    output = io.BytesIO()
    qrcode.make(origin + link.short_path, image_factory=SvgPathFillImage, border=4).save(output)
    return Response(
        output.getvalue(),
        media_type="image/svg+xml",
        headers={
            **PRIVATE_HEADERS,
            "Content-Disposition": 'attachment; filename="advert-qr.svg"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/advertiser/campaigns/{campaign_id}/qr-scans", response_model=CampaignScansRead)
async def get_campaign_scans(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    response: Response,
):
    response.headers.update(PRIVATE_HEADERS)
    return await campaign_scans(session, user_id=current_user.id, campaign_id=campaign_id)


@router.get("/advertiser/campaigns/{campaign_id}/live-positions", response_model=LivePositionsRead)
async def get_live_positions(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    response: Response,
):
    response.headers.update(PRIVATE_HEADERS)
    return await live_positions(
        session, user_id=current_user.id, campaign_id=campaign_id, settings=settings
    )


@router.head(
    "/qr/{code}", response_class=RedirectResponse, status_code=302, include_in_schema=False
)
@router.get("/qr/{code}", response_class=RedirectResponse, status_code=302)
async def qr_redirect(
    code: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")],
    session: SessionDependency,
    limiter: Annotated[QRRateLimiter, Depends(get_qr_limiter)],
    request: Request,
):
    decision = await limiter.reserve(code)
    if not decision.storage_available:
        raise AppError(
            "QR_UNAVAILABLE",
            "This advert link is temporarily unavailable",
            status_code=503,
            headers=PUBLIC_HEADERS,
        )
    if not decision.allowed:
        raise AppError(
            "QR_RATE_LIMITED",
            "Please try this advert link again shortly",
            status_code=429,
            headers={**PUBLIC_HEADERS, "Retry-After": str(decision.retry_after_seconds)},
        )
    destination = await stored_destination(session, code=code, count_scan=request.method == "GET")
    return RedirectResponse(destination, status_code=302, headers=PUBLIC_HEADERS)

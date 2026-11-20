"""REQ-336/D172/D173: site-wide feedback button and the open review page API.

Routes are always registered so the API contract is stable; they answer 404
unless FEEDBACK_ENABLED is set. With it set, the review routes need no login
or password (D173): anyone with the URL of a test version can read the notes.
"""

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.v1.dependencies import (
    SessionDependency,
    SettingsDependency,
    get_current_user,
    oauth2_scheme,
)
from app.core.campaign_enquiry_rate_limit import (
    EnquiryRateLimiter,
    PublicSubmitLimits,
    open_submit_limiter,
)
from app.core.config import Settings
from app.core.errors import AppError
from app.core.rate_limit import RateLimitDecision, login_client_ip
from app.schemas.project_feedback import (
    FeedbackCounts,
    FeedbackCreate,
    FeedbackItemRead,
    FeedbackList,
    FeedbackReceived,
    FeedbackStatusUpdate,
)
from app.services.project_feedback import (
    feedback_csv,
    feedback_screenshot,
    reencode_screenshot,
    review_page,
    save_feedback,
    set_feedback_status,
)

router = APIRouter(tags=["Project feedback"])
MAX_BODY_BYTES = 1024 * 1024


def _inline_schema(model: type[FeedbackCreate]) -> dict[str, Any]:
    """The request JSON schema with nested models inlined (OpenAPI cannot see `$defs`)."""
    schema = model.model_json_schema()
    definitions: dict[str, Any] = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(definitions[node["$ref"].rsplit("/", 1)[-1]])
            return {key: resolve(value) for key, value in node.items()}
        if isinstance(node, list):
            return [resolve(value) for value in node]
        return node

    return {key: resolve(value) for key, value in schema.items()}


def require_feedback_enabled(settings: SettingsDependency) -> None:
    if not settings.feedback_enabled:
        raise AppError("FEEDBACK_NOT_ENABLED", "Feedback is not switched on here", status_code=404)


FeedbackEnabledDependency = Annotated[None, Depends(require_feedback_enabled)]


def _submit_limits(settings: Settings) -> PublicSubmitLimits:
    return PublicSubmitLimits(
        key_prefix="feedback-submit",
        ip_max_attempts=settings.feedback_submit_ip_max_attempts,
        ip_window_seconds=settings.feedback_submit_ip_window_seconds,
        global_max_attempts=settings.feedback_submit_global_max_attempts,
        global_window_seconds=settings.feedback_submit_global_window_seconds,
    )


async def get_feedback_submit_limiter(
    settings: SettingsDependency,
) -> AsyncIterator[EnquiryRateLimiter]:
    async with open_submit_limiter(settings, _submit_limits(settings)) as limiter:
        yield limiter


def _enforce(decision: RateLimitDecision) -> None:
    if not decision.storage_available:
        raise AppError(
            "FEEDBACK_UNAVAILABLE", "Feedback is unavailable. Try again later.", status_code=503
        )
    if not decision.allowed:
        raise AppError(
            "FEEDBACK_RATE_LIMITED",
            "Please wait before trying again.",
            status_code=429,
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


async def optional_submitter_user_id(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: SessionDependency,
    settings: SettingsDependency,
) -> UUID | None:
    """The signed-in user, if the session is fully valid; otherwise anonymous, never 401/403."""
    if token is None or not settings.feedback_enabled:
        return None
    try:
        user = await get_current_user(token, session, settings, request)
    except AppError:
        return None
    return user.id


async def read_feedback(request: Request) -> FeedbackCreate:
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise AppError("unsupported_media_type", "Use JSON for this request.", status_code=415)
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise AppError("request_too_large", "Feedback is too large.", status_code=413)
        chunks.append(chunk)
    try:
        return FeedbackCreate.model_validate(json.loads(b"".join(chunks)))
    except (ValidationError, ValueError, UnicodeError, RecursionError):
        raise AppError(
            "validation_error", "Check your feedback details.", status_code=422
        ) from None


@router.post(
    "/feedback",
    response_model=FeedbackReceived,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": _inline_schema(FeedbackCreate)}},
        }
    },
)
async def submit_feedback(
    request: Request,
    settings: SettingsDependency,
    session: SessionDependency,
    limiter: Annotated[EnquiryRateLimiter, Depends(get_feedback_submit_limiter)],
    submitter_user_id: Annotated[UUID | None, Depends(optional_submitter_user_id)],
) -> FeedbackReceived:
    require_feedback_enabled(settings)
    payload = await read_feedback(request)
    if payload.website:
        return FeedbackReceived()
    _enforce(await limiter.reserve(login_client_ip(request, settings)))
    screenshot = None
    if payload.screenshot is not None:
        screenshot = await run_in_threadpool(reencode_screenshot, payload.screenshot.data_url)
    await save_feedback(
        session, payload, submitter_user_id=submitter_user_id, screenshot=screenshot
    )
    await session.commit()
    return FeedbackReceived()


@router.get("/feedback/review", response_model=FeedbackList)
async def list_feedback(
    _: FeedbackEnabledDependency,
    session: SessionDependency,
    status: Literal["opened", "resolved"] = "opened",
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> FeedbackList:
    items, counts = await review_page(session, status=status, limit=limit, offset=offset)
    return FeedbackList(
        items=items,
        total=counts[status],
        counts=FeedbackCounts(**counts),
        limit=limit,
        offset=offset,
    )


@router.patch("/feedback/{feedback_id}/status", response_model=FeedbackItemRead)
async def update_feedback_status(
    feedback_id: UUID,
    payload: FeedbackStatusUpdate,
    _: FeedbackEnabledDependency,
    session: SessionDependency,
) -> FeedbackItemRead:
    item = await set_feedback_status(session, item_id=feedback_id, status=payload.status)
    await session.commit()
    return item


@router.get(
    "/feedback/export.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
)
async def export_feedback(_: FeedbackEnabledDependency, session: SessionDependency) -> Response:
    return Response(
        content=await feedback_csv(session),
        media_type="text/csv; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="cardvert-feedback.csv"',
        },
    )


@router.get(
    "/feedback/{feedback_id}/screenshot",
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}}}
    },
)
async def read_feedback_screenshot(
    feedback_id: UUID, _: FeedbackEnabledDependency, session: SessionDependency
) -> Response:
    return Response(
        content=await feedback_screenshot(session, feedback_id),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )

"""REQ-336/D172 feedback notes: screenshot hardening, queries and CSV."""

import base64
import binascii
import csv
import io
import re
from dataclasses import dataclass
from uuid import UUID

from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import AppError
from app.models.project_feedback import FeedbackStatus, ProjectFeedbackItem
from app.schemas.project_feedback import FeedbackCreate, FeedbackItemRead, FeedbackPortal
from app.services.campaign_report_rendering import _cell

MAX_SCREENSHOT_BYTES = 1024 * 1024
MAX_SOURCE_SIDE = 4000
MAX_SOURCE_PIXELS = 16_000_000
MAX_STORED_WIDTH = 1200
_DATA_URL = re.compile(r"data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=\s]+)")
_FORMATS = {"jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}
CSV_COLUMNS = (
    "created_at",
    "status",
    "portal",
    "name",
    "page_path",
    "message",
    "has_screenshot",
    "resolved_at",
)


@dataclass(frozen=True)
class StoredScreenshot:
    jpeg: bytes
    width: int
    height: int


def screenshot_invalid() -> AppError:
    return AppError(
        "FEEDBACK_SCREENSHOT_INVALID",
        "The marked screenshot could not be used. Send the note without it.",
        status_code=422,
    )


def reencode_screenshot(data_url: str) -> StoredScreenshot:
    """Decode an untrusted browser capture and store only a fresh, metadata-free JPEG.

    CPU-bound; callers run it in a worker thread.
    """
    match = _DATA_URL.fullmatch(data_url)
    if match is None:
        raise screenshot_invalid()
    declared, encoded = match.groups()
    try:
        raw = base64.b64decode("".join(encoded.split()), validate=True)
    except (binascii.Error, ValueError):
        raise screenshot_invalid() from None
    if not raw or len(raw) > MAX_SCREENSHOT_BYTES:
        raise screenshot_invalid()
    try:
        with Image.open(io.BytesIO(raw), formats=[_FORMATS[declared]]) as image:
            width, height = image.size
            if (
                not 0 < width <= MAX_SOURCE_SIDE
                or not 0 < height <= MAX_SOURCE_SIDE
                or width * height > MAX_SOURCE_PIXELS
            ):
                raise ValueError("Screenshot dimensions exceed the boundary")
            image.seek(0)
            image.load()
            if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                frame = Image.new("RGB", rgba.size, "white")
                frame.paste(rgba, mask=rgba.getchannel("A"))
            else:
                frame = image.convert("RGB")
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise screenshot_invalid() from None
    if frame.width > MAX_STORED_WIDTH:
        frame = frame.resize(
            (MAX_STORED_WIDTH, max(1, round(frame.height * MAX_STORED_WIDTH / frame.width))),
            Image.Resampling.LANCZOS,
        )
    output = io.BytesIO()
    frame.save(output, format="JPEG", quality=80, optimize=True)
    jpeg = output.getvalue()
    if len(jpeg) > MAX_SCREENSHOT_BYTES:
        raise screenshot_invalid()
    return StoredScreenshot(jpeg=jpeg, width=frame.width, height=frame.height)


async def save_feedback(
    session: AsyncSession,
    payload: FeedbackCreate,
    *,
    submitter_user_id: UUID | None,
    screenshot: StoredScreenshot | None,
) -> None:
    item = ProjectFeedbackItem(
        name=payload.name,
        page_path=payload.page_path,
        message=payload.message,
        status="opened",
        submitter_user_id=submitter_user_id,
    )
    if screenshot is not None and payload.screenshot is not None:
        item.screenshot = screenshot.jpeg
        item.screenshot_width = screenshot.width
        item.screenshot_height = screenshot.height
        item.pin_x = payload.screenshot.pin_x
        item.pin_y = payload.screenshot.pin_y
    session.add(item)
    await session.flush()


_PORTAL_PREFIXES: tuple[tuple[str, FeedbackPortal], ...] = (
    ("/advertiser", "advertiser"),
    ("/driver", "driver"),
    ("/admin", "staff"),
)


def portal_for(page_path: str) -> FeedbackPortal:
    for prefix, portal in _PORTAL_PREFIXES:
        if page_path == prefix or page_path.startswith(f"{prefix}/"):
            return portal
    return "public"


def item_read(item: ProjectFeedbackItem) -> FeedbackItemRead:
    return FeedbackItemRead(
        id=item.id,
        name=item.name,
        page_path=item.page_path,
        portal=portal_for(item.page_path),
        message=item.message,
        status=item.status,
        created_at=item.created_at,
        resolved_at=item.resolved_at,
        signed_in=item.submitter_user_id is not None,
        # The screenshot check constraint makes width present exactly when bytes are.
        has_screenshot=item.screenshot_width is not None,
        screenshot_width=item.screenshot_width,
        screenshot_height=item.screenshot_height,
        pin_x=item.pin_x,
        pin_y=item.pin_y,
    )


async def review_page(
    session: AsyncSession, *, status: FeedbackStatus, limit: int, offset: int
) -> tuple[list[FeedbackItemRead], dict[str, int]]:
    rows = await session.scalars(
        select(ProjectFeedbackItem)
        .where(ProjectFeedbackItem.status == status)
        .order_by(ProjectFeedbackItem.created_at.desc(), ProjectFeedbackItem.id.desc())
        .limit(limit)
        .offset(offset)
    )
    counts = {"opened": 0, "resolved": 0}
    for value, count in await session.execute(
        select(ProjectFeedbackItem.status, func.count()).group_by(ProjectFeedbackItem.status)
    ):
        counts[value] = int(count)
    return [item_read(item) for item in rows], counts


async def set_feedback_status(
    session: AsyncSession, *, item_id: UUID, status: FeedbackStatus
) -> FeedbackItemRead:
    item = await session.get(ProjectFeedbackItem, item_id, with_for_update=True)
    if item is None:
        raise feedback_not_found()
    if item.status != status:
        item.status = status
        item.resolved_at = clock.now() if status == "resolved" else None
        await session.flush()
    return item_read(item)


async def feedback_screenshot(session: AsyncSession, item_id: UUID) -> bytes:
    data = await session.scalar(
        select(ProjectFeedbackItem.screenshot).where(ProjectFeedbackItem.id == item_id)
    )
    if data is None:
        raise feedback_not_found()
    return data


async def feedback_csv(session: AsyncSession) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    rows = await session.scalars(
        select(ProjectFeedbackItem).order_by(
            ProjectFeedbackItem.created_at.desc(), ProjectFeedbackItem.id.desc()
        )
    )
    for item in rows:
        read = item_read(item)
        writer.writerow(
            [
                _cell(read.created_at.isoformat()),
                _cell(read.status),
                _cell(read.portal),
                _cell(read.name),
                _cell(read.page_path),
                _cell(read.message),
                _cell("yes" if read.has_screenshot else "no"),
                _cell(read.resolved_at.isoformat() if read.resolved_at else ""),
            ]
        )
    return output.getvalue()


def feedback_not_found() -> AppError:
    return AppError("FEEDBACK_NOT_FOUND", "Feedback note not found", status_code=404)

"""REQ-336 feedback button and review page API shapes."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.project_feedback import FeedbackStatus

FeedbackPortal = Literal["public", "advertiser", "driver", "staff"]


def _has_control(value: str, *, allowed: str = "") -> bool:
    return any((ord(char) < 32 or ord(char) == 127) and char not in allowed for char in value)


class FeedbackScreenshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A browser capture as a data URL; the server re-encodes it before storing.
    data_url: str = Field(min_length=1, max_length=1_500_000)
    pin_x: float = Field(ge=0, le=1)
    pin_y: float = Field(ge=0, le=1)


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    page_path: str = Field(min_length=1, max_length=500)
    message: str = Field(min_length=1, max_length=5000)
    # Honeypot: people never see this field, so any value marks an automated post.
    website: str | None = Field(default=None, max_length=500)
    screenshot: FeedbackScreenshotCreate | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if _has_control(value):
            raise ValueError("Unsupported control character")
        return value

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if _has_control(value, allowed="\n\t\r"):
            raise ValueError("Unsupported control character")
        return value

    @field_validator("page_path")
    @classmethod
    def validate_page_path(cls, value: str) -> str:
        # Only a same-site path: never another origin, query string or fragment.
        if (
            not value.startswith("/")
            or value.startswith(("//", "/\\"))
            or "?" in value
            or "#" in value
            or _has_control(value)
        ):
            raise ValueError("Use the path of a page on this site")
        return value


class FeedbackReceived(BaseModel):
    status: Literal["received"] = "received"


class FeedbackItemRead(BaseModel):
    id: UUID
    name: str
    page_path: str
    portal: FeedbackPortal
    message: str
    status: FeedbackStatus
    created_at: datetime
    resolved_at: datetime | None
    signed_in: bool
    has_screenshot: bool
    screenshot_width: int | None
    screenshot_height: int | None
    pin_x: float | None
    pin_y: float | None


class FeedbackCounts(BaseModel):
    opened: int
    resolved: int


class FeedbackList(BaseModel):
    items: list[FeedbackItemRead]
    total: int
    counts: FeedbackCounts
    limit: int
    offset: int


class FeedbackStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FeedbackStatus

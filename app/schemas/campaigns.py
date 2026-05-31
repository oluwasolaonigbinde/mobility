from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.models.campaign import CampaignStatus, CreativePlacement, CreativeStatus, CreativeType
from app.models.organization import OrganizationStatus
from app.schemas.drivers import normalize_optional_text
from app.schemas.vehicles import normalize_required_text


def normalize_currency(value: str) -> str:
    normalized = normalize_required_text(value).upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("Currency must be a three-letter code")
    return normalized


def ensure_timezone_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("Datetime must include timezone information")
    return value


def trim_non_empty_optional(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be blank")
    return stripped


class DecimalStringMixin(BaseModel):
    @field_serializer("budget_amount", "daily_budget_amount", check_fields=False)
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return str(value)


class CampaignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str | None = None
    status: CampaignStatus = CampaignStatus.DRAFT
    start_at: datetime | None = None
    end_at: datetime | None = None
    budget_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    daily_budget_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_currency(value)

    @field_validator("start_at", "end_at")
    @classmethod
    def datetimes_must_be_aware(cls, value: datetime | None) -> datetime | None:
        return ensure_timezone_aware(value)

    @model_validator(mode="after")
    def validate_campaign_rules(self) -> "CampaignCreate":
        if (
            self.budget_amount is not None
            and self.daily_budget_amount is not None
            and self.daily_budget_amount > self.budget_amount
        ):
            raise ValueError("Daily budget must not exceed total budget")
        if self.start_at is not None and self.end_at is not None and self.start_at >= self.end_at:
            raise ValueError("Campaign start_at must be before end_at")
        return self


class CampaignUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    status: CampaignStatus | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    budget_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    daily_budget_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    metadata: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_required_text(value)

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_currency(value)

    @field_validator("start_at", "end_at")
    @classmethod
    def datetimes_must_be_aware(cls, value: datetime | None) -> datetime | None:
        return ensure_timezone_aware(value)

    @model_validator(mode="after")
    def validate_campaign_rules(self) -> "CampaignUpdate":
        if (
            self.budget_amount is not None
            and self.daily_budget_amount is not None
            and self.daily_budget_amount > self.budget_amount
        ):
            raise ValueError("Daily budget must not exceed total budget")
        if self.start_at is not None and self.end_at is not None and self.start_at >= self.end_at:
            raise ValueError("Campaign start_at must be before end_at")
        return self


class CampaignRead(DecimalStringMixin):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    status: CampaignStatus
    start_at: datetime | None
    end_at: datetime | None
    budget_amount: Decimal | None
    daily_budget_amount: Decimal | None
    currency: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CampaignListResponse(BaseModel):
    items: list[CampaignRead]
    total: int
    limit: int
    offset: int


class AdminCampaignOrganizationSummary(BaseModel):
    id: UUID
    name: str
    currency: str
    status: OrganizationStatus


class AdminCampaignRead(CampaignRead):
    organization: AdminCampaignOrganizationSummary


class AdminCampaignListResponse(BaseModel):
    items: list[AdminCampaignRead]
    total: int
    limit: int
    offset: int


class CreativeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    creative_type: CreativeType
    placement: CreativePlacement
    asset_url: str | None = None
    mime_type: str | None = None
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)
    duration_seconds: int | None = Field(default=None, gt=0)
    checksum: str | None = None
    status: CreativeStatus = CreativeStatus.DRAFT
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("asset_url")
    @classmethod
    def validate_asset_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        parsed = urlsplit(stripped)
        if not stripped or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Asset URL must be an HTTP or HTTPS URL")
        return stripped

    @field_validator("mime_type")
    @classmethod
    def trim_mime_type(cls, value: str | None) -> str | None:
        return trim_non_empty_optional(value, "mime_type")

    @field_validator("checksum")
    @classmethod
    def trim_checksum(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class CreativeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    creative_type: CreativeType | None = None
    placement: CreativePlacement | None = None
    asset_url: str | None = None
    mime_type: str | None = None
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)
    duration_seconds: int | None = Field(default=None, gt=0)
    checksum: str | None = None
    status: CreativeStatus | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_required_text(value)

    @field_validator("asset_url")
    @classmethod
    def validate_asset_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        parsed = urlsplit(stripped)
        if not stripped or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Asset URL must be an HTTP or HTTPS URL")
        return stripped

    @field_validator("mime_type")
    @classmethod
    def trim_mime_type(cls, value: str | None) -> str | None:
        return trim_non_empty_optional(value, "mime_type")

    @field_validator("checksum")
    @classmethod
    def trim_checksum(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class CreativeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    name: str
    creative_type: CreativeType
    placement: CreativePlacement
    asset_url: str | None
    mime_type: str | None
    width_px: int | None
    height_px: int | None
    duration_seconds: int | None
    checksum: str | None
    status: CreativeStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CreativeListResponse(BaseModel):
    items: list[CreativeRead]
    total: int
    limit: int
    offset: int

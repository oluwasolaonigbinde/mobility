from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
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
from app.models.stored_file import FileScanStatus
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


class CampaignReviewReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        return normalize_required_text(value)


class CampaignReviewEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    actor_user_id: UUID
    prior_status: CampaignStatus
    new_status: CampaignStatus
    rejection_reason: str | None
    reviewed_snapshot: dict[str, Any] | None
    reviewed_snapshot_sha256: str | None
    submission_event_id: UUID | None
    created_at: datetime


class CampaignReviewEventListResponse(BaseModel):
    items: list[CampaignReviewEventRead]
    total: int
    limit: int
    offset: int


class CreativeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    creative_type: CreativeType
    placement: CreativePlacement
    stored_file_id: UUID
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)
    duration_seconds: int | None = Field(default=None, gt=0)
    status: CreativeStatus = CreativeStatus.DRAFT
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        return normalize_required_text(value)

class CreativeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    creative_type: CreativeType | None = None
    placement: CreativePlacement | None = None
    stored_file_id: UUID | None = None
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)
    duration_seconds: int | None = Field(default=None, gt=0)
    status: CreativeStatus | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_required_text(value)

class CreativeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    name: str
    creative_type: CreativeType
    placement: CreativePlacement
    stored_file_id: UUID | None
    asset_source: Literal["managed_file", "legacy_url"]
    scan_status: FileScanStatus | None
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


class CreativeReviewReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        return normalize_required_text(value)


class CreativeReviewEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    creative_id: UUID
    actor_user_id: UUID
    prior_status: CreativeStatus
    new_status: CreativeStatus
    rejection_reason: str | None
    reviewed_snapshot: dict[str, Any] | None
    reviewed_snapshot_sha256: str | None
    submission_event_id: UUID | None
    created_at: datetime


class CreativeReviewEventListResponse(BaseModel):
    items: list[CreativeReviewEventRead]
    total: int
    limit: int
    offset: int


class AdminCreativeReviewItem(BaseModel):
    creative: CreativeRead
    campaign_name: str
    organization: AdminCampaignOrganizationSummary


class AdminCreativeReviewListResponse(BaseModel):
    items: list[AdminCreativeReviewItem]
    total: int
    limit: int
    offset: int

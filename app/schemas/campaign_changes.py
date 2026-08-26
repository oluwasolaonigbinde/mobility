from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.campaigns import ensure_timezone_aware


class CampaignChangeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: UUID
    budget_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    daily_budget_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    start_at: datetime | None = None
    end_at: datetime | None = None
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("start_at", "end_at")
    @classmethod
    def aware_datetimes(cls, value: datetime | None) -> datetime | None:
        return ensure_timezone_aware(value)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must not be empty")
        return normalized

    @model_validator(mode="after")
    def at_least_one_change(self) -> "CampaignChangeCreate":
        change_fields = {"budget_amount", "daily_budget_amount", "start_at", "end_at"}
        selected = self.model_fields_set.intersection(change_fields)
        if not selected:
            raise ValueError("At least one campaign change is required")
        if any(getattr(self, field) is None for field in selected):
            raise ValueError("Campaign change values cannot be null")
        return self


class CampaignChangeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must not be empty")
        return normalized


class CampaignChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    organization_id: UUID
    requested_by_user_id: UUID
    client_request_id: UUID
    proposed_changes: dict[str, Any]
    classifications: list[str]
    impact_preview: dict[str, Any]
    status: str
    requested_liability_amount: Decimal
    reserved_liability_amount: Decimal | None
    authorization_id: UUID | None
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    review_reason: str | None
    applied_at: datetime | None
    created_at: datetime


class CampaignChangeList(BaseModel):
    items: list[CampaignChangeRead]


class CampaignChangeRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    request_id: UUID
    revision_number: int
    effective_from: datetime
    snapshot: dict[str, Any]
    snapshot_sha256: str
    applied_by_user_id: UUID
    created_at: datetime

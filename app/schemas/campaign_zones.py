from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.campaign_zone import CampaignZoneType
from app.schemas.drivers import normalize_optional_text
from app.schemas.vehicles import normalize_required_text


class CampaignZoneCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str | None = None
    zone_type: CampaignZoneType
    geometry: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class CampaignZoneUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    zone_type: CampaignZoneType | None = None
    geometry: dict[str, Any] | None = None
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


class CampaignZoneRead(BaseModel):
    id: UUID
    campaign_id: UUID
    name: str
    description: str | None
    zone_type: CampaignZoneType
    geometry: dict[str, Any]
    area_sq_m: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CampaignZoneListResponse(BaseModel):
    items: list[CampaignZoneRead]
    total: int
    limit: int
    offset: int

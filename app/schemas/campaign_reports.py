from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class CampaignReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: UUID
    start_date: date
    end_date: date
    campaign_id: UUID | None = None

    @model_validator(mode="after")
    def valid_period(self):
        if self.start_date > self.end_date:
            raise ValueError("Start date must be on or before end date")
        return self


class CampaignReportRerun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: UUID


class CampaignReportCampaignRead(BaseModel):
    id: UUID
    name: str


class CampaignReportRead(BaseModel):
    id: UUID
    kind: Literal["weekly", "final", "custom", "issued"]
    status: Literal["queued", "ready", "failed"]
    start_date: date
    end_date: date
    timezone: Literal["Africa/Lagos"] = "Africa/Lagos"
    campaigns: list[CampaignReportCampaignRead]
    version: int
    created_at: datetime
    ready_at: datetime | None
    legacy: bool = False
    error: str | None = None


class CampaignReportList(BaseModel):
    items: list[CampaignReportRead]
    total: int
    limit: int
    offset: int

from pydantic import BaseModel, Field

from app.models.campaign_assignment import CampaignAssignmentStatus
from app.schemas.campaign_assignments import ActiveCampaignAssignmentResponse


class AdminBadgeSummary(BaseModel):
    total: int = Field(ge=0)
    drivers: int = Field(ge=0)
    campaigns: int = Field(ge=0)
    trips: int = Field(ge=0)
    money: int = Field(ge=0)
    support: int = Field(ge=0)
    source_counts: dict[str, int]


class DriverCurrentJob(ActiveCampaignAssignmentResponse):
    counts: dict[CampaignAssignmentStatus, int]

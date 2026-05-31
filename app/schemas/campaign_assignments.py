from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.campaign import CampaignStatus
from app.models.campaign_assignment import CampaignActivationEventType, CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.vehicle import VehicleStatus, VehicleType
from app.schemas.drivers import normalize_optional_text


class CampaignAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("notes")
    @classmethod
    def trim_notes(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class CampaignAssignmentTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: dict[str, Any] = Field(default_factory=dict)


class CampaignAssignmentCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class AssignmentCampaignSummary(BaseModel):
    id: UUID
    name: str
    status: CampaignStatus
    start_at: datetime | None
    end_at: datetime | None


class AssignmentDriverProfileSummary(BaseModel):
    id: UUID
    user_id: UUID
    onboarding_status: DriverOnboardingStatus


class AssignmentVehicleSummary(BaseModel):
    id: UUID
    plate_number: str
    plate_country_code: str
    vehicle_type: VehicleType
    status: VehicleStatus


class CampaignActivationEventRead(BaseModel):
    id: UUID
    assignment_id: UUID
    actor_user_id: UUID | None
    event_type: CampaignActivationEventType
    previous_status: str | None
    new_status: str
    occurred_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class CampaignAssignmentRead(BaseModel):
    id: UUID
    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    assigned_by_user_id: UUID
    status: CampaignAssignmentStatus
    offered_at: datetime
    accepted_at: datetime | None
    activated_at: datetime | None
    deactivated_at: datetime | None
    cancelled_at: datetime | None
    completed_at: datetime | None
    notes: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    campaign: AssignmentCampaignSummary | None = None
    driver_profile: AssignmentDriverProfileSummary | None = None
    vehicle: AssignmentVehicleSummary | None = None
    events: list[CampaignActivationEventRead] | None = None


class CampaignAssignmentListResponse(BaseModel):
    items: list[CampaignAssignmentRead]
    total: int
    limit: int
    offset: int


class ActiveCampaignAssignmentResponse(BaseModel):
    assignment: CampaignAssignmentRead | None

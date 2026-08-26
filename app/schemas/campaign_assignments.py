from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.assignment_activity import (
    AssignmentActivityFlagStatus,
    AssignmentActivityFlagType,
)
from app.models.campaign import CampaignStatus
from app.models.campaign_assignment import CampaignActivationEventType, CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.vehicle import VehicleStatus, VehicleType
from app.schemas.drivers import normalize_optional_text
from app.schemas.vehicles import normalize_required_text

MATCHING_V1 = "matching_v1"


class CampaignAssignmentRecommendationContext(BaseModel):
    """The advisory candidate snapshot an admin explicitly selected."""

    model_config = ConfigDict(extra="forbid")

    service_city: str = Field(min_length=1, max_length=128)
    vehicle_type: Literal["car"]
    matching_version: Literal["matching_v1"]
    fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")

    @field_validator("service_city")
    @classmethod
    def normalize_service_city(cls, value: str) -> str:
        return normalize_required_text(value)


class CampaignAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    creative_id: UUID
    expires_at: datetime
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    recommendation_context: CampaignAssignmentRecommendationContext | None = None

    @field_validator("notes")
    @classmethod
    def trim_notes(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class CampaignAssignmentTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: dict[str, Any] = Field(default_factory=dict)


class CampaignAssignmentOfferTerms(BaseModel):
    # Preserve unknown historical keys without treating them as authoritative;
    # service-layer completeness checks still fail closed for activation.
    model_config = ConfigDict(extra="allow")

    # Legacy rows may contain a partial historical snapshot. New offers are
    # complete by service-layer validation; nullable read fields preserve the
    # ability to identify those rows without fabricating terms.
    offer_terms_version: str | None = None
    currency: str | None = None
    campaign_window_start_at: datetime | None = None
    campaign_window_end_at: datetime | None = None
    service_area: dict[str, Any] | None = None
    branding: dict[str, Any] | None = None
    creative: dict[str, Any] | None = None
    payout: dict[str, Any] | None = None
    zones: dict[str, Any] | None = None
    eligibility: dict[str, Any] | None = None


class CampaignAssignmentCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        normalized = normalize_optional_text(value)
        if normalized is None:
            raise ValueError("reason must not be empty")
        return normalized


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
    offer_terms_sha256: str | None = None


class CampaignAssignmentRead(BaseModel):
    id: UUID
    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    assigned_by_user_id: UUID
    status: CampaignAssignmentStatus
    offered_at: datetime
    expires_at: datetime | None
    accepted_at: datetime | None
    declined_at: datetime | None
    expired_at: datetime | None
    activated_at: datetime | None
    deactivated_at: datetime | None
    cancelled_at: datetime | None
    completed_at: datetime | None
    notes: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    offer_terms: CampaignAssignmentOfferTerms | None = None
    offer_terms_sha256: str | None
    created_at: datetime
    updated_at: datetime
    campaign: AssignmentCampaignSummary | None = None
    driver_profile: AssignmentDriverProfileSummary | None = None
    vehicle: AssignmentVehicleSummary | None = None
    events: list[CampaignActivationEventRead] | None = None
    activity_flags: list["AssignmentActivityFlagRead"] | None = None


class AssignmentActivityFlagRead(BaseModel):
    """Admin-only projection; no raw trip/analytics evidence is returned."""

    id: UUID
    assignment_id: UUID
    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    flag_type: AssignmentActivityFlagType
    status: AssignmentActivityFlagStatus
    window_start: datetime
    window_end: datetime
    threshold_seconds: int | None
    observed_seconds: int
    last_verified_activity_at: datetime | None
    first_detected_at: datetime
    last_evaluated_at: datetime
    recovered_at: datetime | None
    eligible_trip_count: int
    evidence_event_count: int


class CampaignAssignmentListResponse(BaseModel):
    items: list[CampaignAssignmentRead]
    total: int
    limit: int
    offset: int


class CampaignAssignmentRecommendationComponents(BaseModel):
    vehicle_load: int
    driver_load: int
    active_tracking_seconds: int
    latest_computed_at: datetime | None


class CampaignAssignmentRecommendation(BaseModel):
    rank: int
    driver_profile_id: UUID
    driver_name: str
    vehicle_id: UUID
    vehicle_plate_number: str
    vehicle_make: str | None
    vehicle_model: str | None
    service_city: str
    vehicle_type: Literal["car"]
    matching_version: Literal["matching_v1"]
    fingerprint: str
    components: CampaignAssignmentRecommendationComponents


class CampaignAssignmentRecommendationListResponse(BaseModel):
    items: list[CampaignAssignmentRecommendation]
    total: int
    limit: int
    offset: int


class ActiveCampaignAssignmentResponse(BaseModel):
    assignment: CampaignAssignmentRead | None

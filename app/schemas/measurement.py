from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.campaigns import ensure_timezone_aware
from app.schemas.exposure_scores import ExposureScoreRead


class MeasurementRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: UUID
    client_request_id: UUID
    period_start_at: datetime
    period_end_at: datetime
    test_only: bool = False

    @model_validator(mode="after")
    def validate_run_request(self) -> "MeasurementRunCreate":
        self.period_start_at = ensure_timezone_aware(self.period_start_at)
        self.period_end_at = ensure_timezone_aware(self.period_end_at)
        if self.period_start_at >= self.period_end_at:
            raise ValueError("period_start_at must be before period_end_at")
        return self


class MeasurementProofBindingRead(BaseModel):
    assignment_id: UUID
    activation_event_id: UUID
    creative_id: UUID
    installation_evidence_submission_id: UUID
    activation_snapshot_sha256: str
    binding_fingerprint: str


class MeasurementRunSummary(BaseModel):
    id: UUID
    formula_version: str
    method_revision: str
    period_start_at: datetime
    period_end_at: datetime
    input_manifest_sha256: str
    result_manifest_sha256: str
    proof_manifest_sha256: str
    report_snapshot_sha256: str
    reissue_of_run_id: UUID | None
    created_at: datetime


class AdminMeasurementRunSummary(MeasurementRunSummary):
    campaign_id: UUID
    campaign_name: str
    test_only: bool
    reproducible: bool
    superseded: bool
    report_issuance_id: UUID | None = None
    report_status: str | None = None


class AdminMeasurementRunList(BaseModel):
    items: list[AdminMeasurementRunSummary]
    total: int
    limit: int
    offset: int


class MeasurementPeriodRead(BaseModel):
    start_at: datetime
    end_at: datetime


class MeasurementCompletenessRead(BaseModel):
    """The frozen completeness/denominator disclosure carried by every metric."""

    cohort_trip_count: int
    denominator_trip_count: int
    in_progress_trip_count: int
    covered_trip_count: int
    insufficient_data_trip_count: int
    excluded_trip_count: int
    complete: bool
    suppressed: bool


class DensityProfileProvenanceRead(BaseModel):
    profile_id: str
    lineage_id: str
    revision: str
    effective_from: str
    value_fingerprint: str
    traffic_density_per_km: str
    dwell_impressions_per_minute: str
    road_category_method: str


class DensityProvenanceRead(BaseModel):
    source: str
    calibration: str
    profiles: list[DensityProfileProvenanceRead]


class VerifiedMovementMetricRead(BaseModel):
    id: Literal["verified_vehicle_movement"]
    label: Literal["Verified vehicle movement"]
    metric_class: Literal["measured_operational_fact"] = Field(alias="class")
    trip_count: int
    distance_m: str | None
    active_tracking_seconds: int | None
    completeness: MeasurementCompletenessRead
    uncertainty: str


class ModelledContactsMetricRead(BaseModel):
    id: Literal["modelled_potential_contacts"]
    label: Literal["Modelled potential contacts"]
    metric_class: Literal["modelled_measure"] = Field(alias="class")
    value: str | None
    formula_versions: list[str]
    completeness: MeasurementCompletenessRead
    density_provenance: DensityProvenanceRead
    uncertainty: str


class CampaignCostTotalRead(BaseModel):
    currency: str
    value: str


class DriverCampaignCostMetricRead(BaseModel):
    id: Literal["driver_campaign_cost"]
    label: Literal["Driver campaign cost"]
    metric_class: Literal["measured_financial_fact"] = Field(alias="class")
    totals_by_currency: list[CampaignCostTotalRead]
    completeness: MeasurementCompletenessRead


MeasurementMetricRead = Annotated[
    VerifiedMovementMetricRead | ModelledContactsMetricRead | DriverCampaignCostMetricRead,
    Field(discriminator="id"),
]


class MeasurementResultRead(BaseModel):
    schema_version: Literal["measurement-result-v1"]
    title: Literal["Campaign Performance Analysis"]
    formula_version: str
    method_revision: str
    period: MeasurementPeriodRead
    metrics: list[MeasurementMetricRead]
    proof_manifest_sha256: str


class MeasurementRunRead(MeasurementRunSummary):
    organization_id: UUID
    campaign_id: UUID
    created_by_user_id: UUID
    client_request_id: UUID
    test_only: bool
    input_manifest: dict[str, Any]
    result_manifest: dict[str, Any]
    proof_manifest: dict[str, Any]
    proof_bindings: list[MeasurementProofBindingRead]
    exposure_score: ExposureScoreRead | None = None
    reproducible: bool

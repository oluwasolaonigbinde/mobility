from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.measurement import MeasurementRunMode
from app.schemas.campaigns import ensure_timezone_aware
from app.schemas.exposure_scores import ExposureScoreRead


class RoiMethodInput(BaseModel):
    revision: str = Field(min_length=1, max_length=255)
    approval_reference: str = Field(min_length=1, max_length=255)
    attribution_rule: str = Field(min_length=1, max_length=1000)
    attribution_window: str = Field(min_length=1, max_length=255)
    cost_basis: str = Field(min_length=1, max_length=500)
    exclusions: str = Field(min_length=1, max_length=1000)
    corrections: str = Field(min_length=1, max_length=1000)
    late_data: str = Field(min_length=1, max_length=1000)


class RoiInput(BaseModel):
    attributed_revenue: Decimal = Field(ge=0)
    approved_cost_basis: Decimal = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    conversion_provenance: str = Field(min_length=1, max_length=1000)
    revenue_provenance: str = Field(min_length=1, max_length=1000)
    reporting_cutoff: datetime
    synthetic: bool = False
    method: RoiMethodInput

    @model_validator(mode="after")
    def validate_cutoff(self) -> "RoiInput":
        self.reporting_cutoff = ensure_timezone_aware(self.reporting_cutoff)
        return self


class MeasurementRunCreate(BaseModel):
    campaign_id: UUID
    client_request_id: UUID
    period_start_at: datetime
    period_end_at: datetime
    mode: MeasurementRunMode = MeasurementRunMode.PERFORMANCE_ONLY
    test_only: bool = False
    roi: RoiInput | None = None

    @model_validator(mode="after")
    def validate_run_request(self) -> "MeasurementRunCreate":
        self.period_start_at = ensure_timezone_aware(self.period_start_at)
        self.period_end_at = ensure_timezone_aware(self.period_end_at)
        if self.period_start_at >= self.period_end_at:
            raise ValueError("period_start_at must be before period_end_at")
        if self.mode == MeasurementRunMode.PERFORMANCE_ONLY and self.roi is not None:
            raise ValueError("performance_only runs cannot contain ROI inputs")
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
    mode: MeasurementRunMode
    formula_version: str
    method_revision: str
    roi_method_revision: str | None
    period_start_at: datetime
    period_end_at: datetime
    input_manifest_sha256: str
    result_manifest_sha256: str
    proof_manifest_sha256: str
    report_snapshot_sha256: str
    reissue_of_run_id: UUID | None
    created_at: datetime


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


class MeasurementRoiMethodRead(BaseModel):
    """Every ROI method fact the methodology contract requires beside a result."""

    approval_reference: str
    attribution_rule: str
    attribution_window: str
    cost_basis: str
    exclusions: str
    corrections: str
    late_data: str
    limitations: str


class MeasurementRoiProvenanceRead(BaseModel):
    conversion_provenance: str
    revenue_provenance: str
    reporting_cutoff: str
    synthetic: bool


class MeasurementRoiRead(BaseModel):
    label: Literal["Return on investment"]
    metric_class: Literal["conditional_financial_measure"] = Field(alias="class")
    ratio: str
    percent: str
    currency: str
    method_revision: str
    method: MeasurementRoiMethodRead
    provenance: MeasurementRoiProvenanceRead


class MeasurementRoiOmittedRead(BaseModel):
    decision: Literal["OMIT"]


class MeasurementRoiIncludedRead(BaseModel):
    decision: Literal["INCLUDE"]
    test_only: bool


MeasurementRoiGateRead = Annotated[
    MeasurementRoiOmittedRead | MeasurementRoiIncludedRead,
    Field(discriminator="decision"),
]


class MeasurementResultRead(BaseModel):
    schema_version: Literal["measurement-result-v1"]
    title: Literal["Campaign Performance Analysis"]
    mode: MeasurementRunMode
    formula_version: str
    method_revision: str
    period: MeasurementPeriodRead
    metrics: list[MeasurementMetricRead]
    proof_manifest_sha256: str
    roi: MeasurementRoiRead | None
    roi_gate: MeasurementRoiGateRead


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

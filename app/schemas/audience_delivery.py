from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AudienceDeliveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: UUID


class AudienceDeliveryApprovalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["csv_export", "ad_platform_activation"]
    purpose_code: Literal[
        "aggregate_campaign_planning", "aggregate_contextual_activation"
    ]
    provider: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    provider_account_reference: str | None = Field(default=None, min_length=1, max_length=255)
    budget_ceiling: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=2)
    legal_approval_reference: str = Field(min_length=1, max_length=255)
    valid_until: datetime

    @model_validator(mode="after")
    def validate_operation_fields(self) -> "AudienceDeliveryApprovalCreate":
        if self.valid_until.tzinfo is None or self.valid_until.utcoffset() is None:
            raise ValueError("valid_until must be timezone-aware")
        if self.operation == "csv_export":
            if (
                self.purpose_code != "aggregate_campaign_planning"
                or self.provider != "controlled-csv-v1"
                or self.provider_account_reference is not None
                or self.budget_ceiling is not None
            ):
                raise ValueError("CSV approval fields do not match the controlled export")
        elif (
            self.purpose_code != "aggregate_contextual_activation"
            or self.provider_account_reference is None
            or self.budget_ceiling is None
        ):
            raise ValueError("Activation approval requires provider account and budget authority")
        return self


class AudienceDeliveryApprovalRead(BaseModel):
    id: UUID
    organization_id: UUID
    campaign_id: UUID
    segment_id: UUID
    approved_by_user_id: UUID
    operation: Literal["csv_export", "ad_platform_activation"]
    purpose_code: str
    provider: str
    provider_account_reference: str | None
    budget_ceiling: Decimal | None
    legal_approval_reference: str
    snapshot_sha256: str
    synthetic: bool
    valid_from: datetime
    valid_until: datetime
    created_at: datetime


class AggregateTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coverage_cell: str = Field(pattern=r"^grid-[1-9][0-9]*m:-?[0-9]+:-?[0-9]+$", max_length=64)
    window_start_at: datetime
    window_end_at: datetime
    context: Literal["vehicle_transit"]

    @model_validator(mode="after")
    def validate_window(self) -> "AggregateTarget":
        if (
            self.window_start_at.tzinfo is None
            or self.window_start_at.utcoffset() is None
            or self.window_end_at.tzinfo is None
            or self.window_end_at.utcoffset() is None
        ):
            raise ValueError("Aggregate targeting windows must be timezone-aware")
        if self.window_start_at >= self.window_end_at:
            raise ValueError("window_start_at must be before window_end_at")
        return self


class AggregateActivationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aggregate-contextual-activation-v1"]
    campaign_id: UUID
    campaign_context: Literal["vehicle_transit"]
    targets: list[AggregateTarget] = Field(min_length=1)


class RecommendationProvenance(BaseModel):
    segment_id: UUID
    segment_version: int
    segment_snapshot_sha256: str
    source_link_id: UUID
    source_link_snapshot_sha256: str
    measurement_run_id: UUID
    measurement_input_sha256: str
    measurement_result_sha256: str
    measurement_proof_sha256: str


class AggregateRecommendation(BaseModel):
    rank: int
    coverage_cell: str
    window_start_at: datetime
    window_end_at: datetime
    campaign_context: Literal["vehicle_transit"]
    rationale: str


class RecommendationsRead(BaseModel):
    state: Literal["empty", "suppressed", "ready", "stale"]
    segment_id: UUID | None
    campaign_id: UUID | None
    recommendations: list[AggregateRecommendation]
    provenance: RecommendationProvenance | None
    disclaimer: str
    uncertainty: str | None
    export_approval_id: UUID | None = None


class AudienceExportRead(BaseModel):
    id: UUID
    segment_id: UUID
    operation: Literal["csv_export"]
    approval_id: UUID
    purpose_code: str
    payload_sha256: str
    csv_content: str
    csv_sha256: str
    created_at: datetime


class AudienceActivationRead(BaseModel):
    id: UUID
    segment_id: UUID
    operation: Literal["ad_platform_activation"]
    approval_id: UUID
    purpose_code: str
    adapter_name: str
    provider_reference: str
    payload_sha256: str
    synthetic: bool
    created_at: datetime

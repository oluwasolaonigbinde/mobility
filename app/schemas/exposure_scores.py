from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ExposureScoreRangeRead(BaseModel):
    minimum: Literal["0.00"]
    maximum: Literal["100.00"]


class ExposureScoreConstantsRead(BaseModel):
    distance_cap_m: Literal["10000"]
    active_tracking_cap_seconds: Literal[3600]
    distance_weight: Literal["0.60"]
    active_tracking_weight: Literal["0.40"]


class ExposureScoreFormulaRead(BaseModel):
    formula_version: Literal["exposure_v1"]
    scope: Literal["campaign_route"]
    unit: Literal["points"]
    range: ExposureScoreRangeRead
    inputs: list[Literal["distance_m", "active_tracking_seconds", "quality_score"]]
    constants: ExposureScoreConstantsRead
    route_calculation: str
    campaign_calculation: str
    missing_data: str
    rounding: Literal["ROUND_HALF_UP to 2 decimal places"]


class ExposureScoreUncertaintyRead(BaseModel):
    classification: Literal["synthetic_uncalibrated_index"]
    statement: str


class ExposureScoreProvenanceRead(BaseModel):
    measurement_run_id: UUID
    measurement_input_sha256: str
    measurement_result_sha256: str
    measurement_proof_sha256: str


class RouteExposureScoreRead(BaseModel):
    trip_analytics_id: UUID
    trip_session_id: UUID
    score: str


class ExposureScoreResultRead(BaseModel):
    schema_version: Literal["exposure-score-result-v1"]
    label: Literal["Exposure score"]
    metric_class: Literal["operational_composite_index"]
    formula_version: Literal["exposure_v1"]
    formula_fingerprint: str
    input_fingerprint: str
    unit: Literal["points"]
    range: ExposureScoreRangeRead
    status: Literal["scored", "insufficient_data"]
    score: str | None
    route_count: int
    missing_route_count: int
    route_scores: list[RouteExposureScoreRead]
    formula: ExposureScoreFormulaRead
    uncertainty: ExposureScoreUncertaintyRead
    provenance: ExposureScoreProvenanceRead


class ExposureScoreRead(BaseModel):
    id: UUID
    organization_id: UUID
    campaign_id: UUID
    measurement_run_id: UUID
    issued_by_user_id: UUID
    formula_version: str
    formula_fingerprint: str
    input_fingerprint: str
    result_fingerprint: str
    measurement_input_sha256: str
    measurement_result_sha256: str
    measurement_proof_sha256: str
    result: ExposureScoreResultRead
    reissue_of_score_id: UUID | None
    reproducible: bool
    stale: bool
    created_at: datetime

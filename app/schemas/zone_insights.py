from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_serializer


class HighExposureZoneItem(BaseModel):
    rank: int
    zone_id: UUID
    zone_name: str
    modelled_potential_contacts: Decimal
    trip_count: int

    @field_serializer("modelled_potential_contacts")
    def serialize_contacts(self, value: Decimal) -> str:
        return str(value)


class ZoneInsightSegmentProvenance(BaseModel):
    segment_id: UUID
    segment_version: int
    segment_snapshot_sha256: str
    reissue_of_segment_id: UUID | None


class HighExposureZoneProvenance(BaseModel):
    formula_version: Literal["high_exposure_zone_v1"]
    formula_fingerprint: str
    measurement_run_id: UUID
    exposure_score_id: UUID
    exposure_formula_version: str
    exposure_formula_fingerprint: str
    exposure_input_fingerprint: str
    source_segments: list[ZoneInsightSegmentProvenance]


class HighExposureZoneInsightsRead(BaseModel):
    state: Literal["empty", "suppressed", "ready", "stale", "unavailable"]
    campaign_id: UUID
    campaign_exposure_score: str | None
    items: list[HighExposureZoneItem]
    provenance: HighExposureZoneProvenance | None
    uncertainty: str | None
    disclaimer: str

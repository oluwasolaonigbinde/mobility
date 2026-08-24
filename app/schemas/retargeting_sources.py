from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceCommon(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provenance: Literal["advertiser-declared", "third-party-aggregate"]
    lawful_basis_reference: Literal["candidate-legitimate-interest", "candidate-consent"]
    # W3-01A has no legal-approval transition: advertisers may record only
    # candidate facts until EXT-LEGAL-PRIVACY supplies approved evidence.
    lawful_basis_status: Literal["unapproved"]
    consent_disclaimer_status: Literal["not-reviewed"]
    expires_at: datetime
    dsr_owner_role: Literal["privacy-officer", "compliance-owner"]
    dsr_status: Literal["pending", "not-applicable"]

    @field_validator("expires_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("expires_at must include timezone information")
        return value


class WebsiteTrafficSourceCreate(SourceCommon):
    source_type: Literal["website-traffic"]
    audience_category: Literal["site-visitor", "content-interest", "conversion-intent"]
    aggregation_window_days: int = Field(ge=1, le=365)


class DigitalCampaignAudienceSourceCreate(SourceCommon):
    source_type: Literal["digital-campaign-audience"]
    channel: Literal["search", "social", "display"]
    audience_stage: Literal["awareness", "consideration", "conversion-intent"]
    aggregation_window_days: int = Field(ge=1, le=365)


class CrmUploadReferenceSourceCreate(SourceCommon):
    source_type: Literal["CRM-upload-reference"]
    reference_mode: Literal["aggregate-availability-only"]
    record_count_band: Literal["0-99", "100-999", "1000-plus"]


class UtmSourceCreate(SourceCommon):
    source_type: Literal["UTM-source"]
    channel: Literal["search", "social", "display", "email"]
    campaign_stage: Literal["awareness", "consideration", "conversion-intent"]


class ManualInsightSourceCreate(SourceCommon):
    source_type: Literal["manual-insight"]
    insight_category: Literal["area-demand", "time-pattern", "contextual-affinity"]
    confidence_band: Literal["low", "medium", "high"]


RetargetingSourceCreate = Annotated[
    WebsiteTrafficSourceCreate
    | DigitalCampaignAudienceSourceCreate
    | CrmUploadReferenceSourceCreate
    | UtmSourceCreate
    | ManualInsightSourceCreate,
    Field(discriminator="source_type"),
]

RetargetingSourceSnapshot = RetargetingSourceCreate


class RetargetingSourceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    organization_id: UUID
    source_type: str
    snapshot: RetargetingSourceSnapshot
    snapshot_sha256: str
    status: Literal["active", "expired", "deactivated"]
    expires_at: datetime
    created_at: datetime
    deactivated_at: datetime | None


class RetargetingSourceListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RetargetingSourceRead]
    total: int


class RetargetingSourceEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    sequence_number: int
    event_type: Literal["created", "deactivated"]
    snapshot: RetargetingSourceSnapshot
    snapshot_sha256: str
    created_at: datetime


class RetargetingSourceHistoryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: RetargetingSourceRead
    events: list[RetargetingSourceEventRead]

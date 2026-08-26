from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CampaignCancellationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: UUID
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must not be empty")
        return normalized


class CampaignCancellationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    organization_id: UUID
    requested_by_user_id: UUID
    client_request_id: UUID
    reason: str
    prior_status: str
    cutoff_at: datetime
    commercial_terms_id: UUID | None
    production_start_id: UUID | None
    funding_authorized_at: datetime | None
    refund_eligibility_ends_at: datetime | None
    disposition: str
    refundable_amount: Decimal
    currency: str
    released_liability_amount: Decimal
    cancelled_assignment_count: int
    created_at: datetime


class CampaignCancellationSettlementRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cancellation_id: UUID
    campaign_id: UUID
    revision_number: int
    effective_from: datetime
    snapshot: dict[str, Any]
    snapshot_sha256: str
    created_at: datetime

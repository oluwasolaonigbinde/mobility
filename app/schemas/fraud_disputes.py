from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.fraud_dispute import FraudDisputeStatus
from app.schemas.notifications import DriverNotificationRead


class NormalizedMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class FraudDisputeCreate(NormalizedMessage):
    message: str = Field(min_length=1, max_length=2000)


class FraudDisputeReply(NormalizedMessage):
    reply: str = Field(min_length=1, max_length=2000)


class DriverFraudDisputeRead(BaseModel):
    id: UUID
    message: str
    status: FraudDisputeStatus
    reply: str | None
    submitted_at: datetime
    replied_at: datetime | None


class AdminFraudDisputeRead(BaseModel):
    id: UUID
    fraud_flag_id: UUID
    driver_profile_id: UUID
    submitted_by_user_id: UUID
    message: str
    status: FraudDisputeStatus
    replied_by_user_id: UUID | None
    replied_at: datetime | None
    reply: str | None
    created_at: datetime
    updated_at: datetime


class AdminFraudDisputeList(BaseModel):
    items: list[AdminFraudDisputeRead]
    total: int
    limit: int
    offset: int


class DriverFraudHoldReason(BaseModel):
    code: str
    version: Literal["v1"] = "v1"
    title: str
    body: str


class DriverFraudHoldRead(BaseModel):
    id: UUID
    trip_session_id: UUID
    public_status: Literal[
        "assessment_pending", "under_review", "issue_confirmed", "review_cleared"
    ]
    reason: DriverFraudHoldReason
    detected_at: datetime
    reviewed_at: datetime | None
    dispute: DriverFraudDisputeRead | None
    notices: list[DriverNotificationRead] = Field(default_factory=list)


class DriverFraudHoldList(BaseModel):
    items: list[DriverFraudHoldRead]

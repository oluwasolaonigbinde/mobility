from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.complaint import ComplaintParty, ComplaintReferenceType, ComplaintStatus


class ComplaintCategory(StrEnum):
    """Neutral default categories (Batch E); the client has not supplied a list."""

    PAY_OR_PAYOUT = "pay_or_payout"
    TRIP_OR_TRACKING = "trip_or_tracking"
    CAMPAIGN_OR_JOB = "campaign_or_job"
    BILLING_OR_INVOICE = "billing_or_invoice"
    ACCOUNT = "account"
    OTHER = "other"


class _Stripped(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        # PostgreSQL refuses NUL; rejecting it here keeps message text out of a 500's error.
        if "\x00" in value:
            raise ValueError("Text must not contain a NUL character")
        return value.strip()


class ComplaintCreate(_Stripped):
    category: ComplaintCategory
    message: str = Field(min_length=1, max_length=2000)
    reference_type: ComplaintReferenceType | None = None
    reference_id: UUID | None = None
    client_request_id: UUID


class ComplaintMessageCreate(_Stripped):
    message: str = Field(min_length=1, max_length=2000)
    client_request_id: UUID


class StaffComplaintReplyCreate(ComplaintMessageCreate):
    resolve: bool = False


class StaffComplaintUpdate(BaseModel):
    """Both fields are optional; an empty body is a valid no-op.

    An omitted field is left unchanged; an explicit null assignee clears it.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "resolved"] | None = None
    assigned_to_user_id: UUID | None = None


class ComplaintReferenceOption(BaseModel):
    id: UUID
    label: str


class ComplaintReferenceOptions(BaseModel):
    campaigns: list[ComplaintReferenceOption]
    trips: list[ComplaintReferenceOption]
    payouts: list[ComplaintReferenceOption]


class ComplaintMessageRead(BaseModel):
    sender: Literal["you", "your_team", "terrax_media"]
    body: str
    sent_at: datetime


class ComplaintSummaryRead(BaseModel):
    id: UUID
    category: ComplaintCategory
    status: ComplaintStatus
    reference_type: ComplaintReferenceType | None
    reference_label: str | None
    created_at: datetime
    last_message_at: datetime
    waiting_on_you: bool


class ComplaintDetailRead(ComplaintSummaryRead):
    messages: list[ComplaintMessageRead]


class ComplaintList(BaseModel):
    items: list[ComplaintSummaryRead]


class StaffComplaintMessageRead(BaseModel):
    id: UUID
    author_side: Literal["complainant", "staff"]
    author_user_id: UUID
    author_name: str
    body: str
    status_after: ComplaintStatus
    sent_at: datetime


class StaffComplaintSummaryRead(BaseModel):
    id: UUID
    party: ComplaintParty
    category: ComplaintCategory
    status: ComplaintStatus
    raised_by_user_id: UUID
    raised_by_name: str
    driver_profile_id: UUID | None
    advertiser_organization_id: UUID | None
    party_name: str
    reference_type: ComplaintReferenceType | None
    reference_id: UUID | None
    reference_label: str | None
    assigned_to_user_id: UUID | None
    assigned_to_name: str | None
    revision: int
    created_at: datetime
    last_message_at: datetime
    resolved_at: datetime | None


class StaffComplaintDetailRead(StaffComplaintSummaryRead):
    messages: list[StaffComplaintMessageRead]


class StaffComplaintList(BaseModel):
    items: list[StaffComplaintSummaryRead]
    total: int
    limit: int
    offset: int

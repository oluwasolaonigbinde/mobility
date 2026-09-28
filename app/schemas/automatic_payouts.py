from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.models.disbursement import PayoutAutomaticAlertKind

Money = Annotated[Decimal, PlainSerializer(str, return_type=str)]
Reason = Annotated[str, Field(min_length=3, max_length=500)]


class AutomaticPayoutReason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Reason


class AutomaticPayoutAlertResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: Reason


class AutomaticPayoutRunRead(BaseModel):
    id: UUID
    period_key: str
    created_at: datetime
    batch_count: int
    line_count: int
    total_amount: Money
    batch_limit: Money | None = None


class AutomaticPayoutStatusRead(BaseModel):
    switched_on: bool
    frequency: Literal["daily", "weekly"] | None
    batch_limit: Money | None
    currency: str
    missing_settings: list[str]
    paused: bool
    pause_reason: str | None
    pause_changed_by_name: str | None
    pause_changed_at: datetime | None
    identity_ready: bool
    provider_ready: bool
    runnable: bool
    last_run: AutomaticPayoutRunRead | None
    open_alert_count: int
    unsent_count: int


class AutomaticPayoutReleaseRead(BaseModel):
    released_count: int
    released_amount: Money


class AutomaticPayoutAlertRead(BaseModel):
    id: UUID
    kind: PayoutAutomaticAlertKind
    created_at: datetime
    driver_name: str | None
    lagos_day: date | None
    amount: Money | None
    currency: str | None
    batch_id: UUID | None
    line_id: UUID | None
    detail: dict[str, Any]
    resolved_at: datetime | None
    resolved_by_name: str | None
    resolution_note: str | None


class AutomaticPayoutAlertListRead(BaseModel):
    items: list[AutomaticPayoutAlertRead]
    total: int
    limit: int
    offset: int


class AutomaticOutcomeRead(BaseModel):
    outcome: str
    count: int
    amount: Money


class AutomaticEvidenceRead(BaseModel):
    outcome: str
    applied: bool
    count: int


class AutomaticAlertCountRead(BaseModel):
    kind: PayoutAutomaticAlertKind
    count: int


class AutomaticManualReasonRead(BaseModel):
    reason: str
    count: int
    amount: Money


class AutomaticReconciliationLineRead(BaseModel):
    id: UUID
    batch_id: UUID
    driver_name: str
    amount: Money
    currency: str
    outcome: str
    provider_transfer_reference: str | None
    last_provider_evidence_at: datetime | None


class AutomaticReconciliationRead(BaseModel):
    day: date
    runs: list[AutomaticPayoutRunRead]
    outcomes: list[AutomaticOutcomeRead]
    provider_evidence: list[AutomaticEvidenceRead]
    awaiting_provider_count: int
    alerts_raised: list[AutomaticAlertCountRead]
    kept_for_manual_review: list[AutomaticManualReasonRead]
    lines: list[AutomaticReconciliationLineRead]
    total: int
    limit: int
    offset: int

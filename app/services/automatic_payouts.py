"""Automatic payout approval with safeguards (D39(c), Batch C).

Cardvert prepares, approves and queues payouts for provably clean payout_v4
trip earnings without a person, then the existing submission sweep, provider
evidence and recovery paths take over unchanged. Anything not provably clean
stays on the maker-checker path. Nothing runs until the client's settings are
supplied (payout frequency and run limit) and the switch is on; Finance can
pause it at any time.

Lock order (plan review R2): control row -> fraud-hold scopes -> batches/lines/
intents -> driver debt scopes -> ledger rows -> payees. The system actor is read
without a lock; pause/resume lock the acting admin before the control row.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from starlette import status

from app.adapters.disbursement import DisbursementAdapter
from app.core.config import Settings
from app.core.errors import AppError
from app.db.integrity import integrity_constraint_name
from app.models.audit import AuditEvent
from app.models.disbursement import (
    CARDVERT_AUTOMATIC_PAYOUT_ACTOR_EMAIL,
    CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID,
    CARDVERT_AUTOMATIC_PAYOUT_ACTOR_NAME,
    PayoutAutomaticAlert,
    PayoutAutomaticAlertKind,
    PayoutAutomaticControl,
    PayoutAutomaticRun,
    PayoutBatch,
    PayoutBatchApprovalMode,
    PayoutBatchLine,
    PayoutBatchLineStatus,
    PayoutBatchStatus,
    PayoutLineReconciliationEvent,
    PayoutRecoveryIncident,
    PayoutRecoveryIncidentKind,
    PayoutSubmissionAttempt,
    PayoutSubmissionIntent,
    PayoutSubmissionIntentState,
    PayoutSubmissionObservation,
)
from app.models.fraud_dispute import FraudDispute, FraudDisputeStatus
from app.models.notification import NotificationType
from app.models.payee import Payee
from app.models.payout import (
    AssignmentRuleBinding,
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCalculation,
    PayoutCalculationStatus,
)
from app.models.trip import TripSession
from app.models.trip_analytics import FraudFlag
from app.models.user import User, UserRole, UserStatus
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.disbursements import (
    _cancel_uncalled_line,
    _derive_batch_status,
    _frozen_payee_authority,
    _locked_batch_with_lines,
    _submission_capabilities,
    build_frozen_payout_line,
    freeze_batch_instruction_set,
)
from app.services.fraud_assessments import load_current_successful_assessment
from app.services.fraud_holds import fraud_hold_active_clause, lock_fraud_hold_scopes
from app.services.notifications import create_active_admin_notices
from app.services.payout_debt import lock_driver_currency_debt_scope
from app.services.payout_operations import _outcome
from app.services.payouts import (
    PAYOUT_V4,
    _day_trip_overlap,
    lagos_day_for,
    lagos_day_utc_range,
    latest_daily_rate_position,
)

AUTOMATIC_CURRENCY = "NGN"
# Engineering bound on one run's candidate scan (keeps fraud-hold scopes short);
# not a client value. Entries past it wait for the next period.
MAX_CANDIDATES_PER_RUN = 200
CONTROL_ID = 1
REASON_MIN, REASON_MAX = 3, 500
# Ledger rows that count toward a v4 trip's day position (plan review R5).
_COUNTED_ENTRY_STATUSES = (
    EarningsLedgerEntryStatus.PENDING.value,
    EarningsLedgerEntryStatus.AVAILABLE.value,
    EarningsLedgerEntryStatus.PAID.value,
    EarningsLedgerEntryStatus.REVERSED.value,
)
_SETTING_NAMES = {
    "enabled": "PAYOUT_AUTOMATIC_APPROVAL_ENABLED",
    "frequency": "PAYOUT_AUTOMATIC_FREQUENCY",
    "limit": "PAYOUT_AUTOMATIC_BATCH_LIMIT_NGN",
}


def _error(code: str, message: str, http_status: int = status.HTTP_409_CONFLICT) -> AppError:
    return AppError(code, message, status_code=http_status)


def _key(*parts: object) -> str:
    return hashlib.sha256(":".join(str(part) for part in parts).encode()).hexdigest()


def _money(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


# --- settings, switch and system actor ---------------------------------------


def missing_automatic_settings(settings: Settings) -> list[str]:
    missing = []
    if not settings.payout_automatic_approval_enabled:
        missing.append(_SETTING_NAMES["enabled"])
    if not settings.payout_automatic_frequency:
        missing.append(_SETTING_NAMES["frequency"])
    if settings.payout_automatic_batch_limit_ngn is None:
        missing.append(_SETTING_NAMES["limit"])
    return missing


def period_key_for(moment: datetime, frequency: str) -> str:
    day = lagos_day_for(moment)
    if frequency == "weekly":
        year, week, _ = day.isocalendar()
        return f"{year}-W{week:02d}"
    return day.isoformat()


async def load_control(
    session: AsyncSession, *, lock: str | None = None
) -> PayoutAutomaticControl | None:
    query = select(PayoutAutomaticControl).where(PayoutAutomaticControl.id == CONTROL_ID)
    if lock == "update":
        query = query.with_for_update()
    elif lock == "share":
        query = query.with_for_update(read=True)
    return await session.scalar(query.execution_options(populate_existing=True))


async def actor_integrity_problem(
    session: AsyncSession, control: PayoutAutomaticControl | None
) -> str | None:
    """Why the system actor cannot act, or None. Never creates either row (R8)."""
    if control is None:
        return "control_missing"
    actor = await session.get(User, CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID, populate_existing=True)
    if actor is None:
        return "actor_missing"
    if (
        actor.email != CARDVERT_AUTOMATIC_PAYOUT_ACTOR_EMAIL
        or actor.full_name != CARDVERT_AUTOMATIC_PAYOUT_ACTOR_NAME
        or actor.role != UserRole.ADMIN.value
        or actor.status != UserStatus.DISABLED.value
        or hashlib.sha256(actor.password_hash.encode()).hexdigest()
        != control.actor_password_fingerprint
    ):
        return "actor_changed"
    return None


async def automatic_submission_blocker(
    session: AsyncSession, settings: Settings, *, lock: bool = True
) -> str | None:
    """Why an automatic SUBMIT claim must not happen now (control row FOR SHARE)."""
    control = await load_control(session, lock="share" if lock else None)
    if await actor_integrity_problem(session, control) is not None:
        return "actor_invalid"
    if missing_automatic_settings(settings):
        return "not_set_up"
    if control is not None and control.paused:
        return "paused"
    return None


def _settings_fingerprint(settings: Settings) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "frequency": settings.payout_automatic_frequency,
                "batch_limit_ngn": f"{settings.payout_automatic_batch_limit_ngn:.2f}",
                "currency": AUTOMATIC_CURRENCY,
                "clean_rule": "batch-c-clean-v4-v1",
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


# --- alerts ------------------------------------------------------------------


async def raise_alert(
    session: AsyncSession,
    *,
    kind: PayoutAutomaticAlertKind,
    dedupe: tuple[object, ...],
    detail: dict[str, object],
    run_id: UUID | None = None,
    batch_id: UUID | None = None,
    line_id: UUID | None = None,
    ledger_entry_id: UUID | None = None,
    driver_profile_id: UUID | None = None,
    lagos_day: date | None = None,
    amount: Decimal | None = None,
) -> PayoutAutomaticAlert | None:
    """Create one alert per dedupe key and tell active admins; None if it exists."""
    dedupe_key = _key("cardvert-automatic-payout-alert-v1", kind.value, *dedupe)
    if await session.scalar(
        select(PayoutAutomaticAlert.id).where(PayoutAutomaticAlert.dedupe_key == dedupe_key)
    ):
        return None
    alert = PayoutAutomaticAlert(
        id=uuid4(),
        kind=kind.value,
        dedupe_key=dedupe_key,
        run_id=run_id,
        batch_id=batch_id,
        line_id=line_id,
        ledger_entry_id=ledger_entry_id,
        driver_profile_id=driver_profile_id,
        lagos_day=lagos_day,
        amount=amount,
        currency=AUTOMATIC_CURRENCY if amount is not None else None,
        detail=detail,
    )
    try:
        async with session.begin_nested():
            session.add(alert)
            await session.flush()
    except IntegrityError as exc:
        if integrity_constraint_name(exc) != "uq_payout_automatic_alerts_dedupe_key":
            raise
        return None
    await create_active_admin_notices(
        session,
        type_key=NotificationType.PAYOUT_AUTOMATIC_ALERT,
        event_key=f"payout-automatic-alert:v1:{alert.id}",
        payload={"alert_id": str(alert.id), "kind": alert.kind},
    )
    return alert


async def scan_automatic_payout_alerts(session: AsyncSession, *, limit: int = 200) -> int:
    """Detect failures and duplicates on automatic batches from existing rows.

    Read-only over reconciliation state; runs even while paused or switched off.
    """
    automatic_line_ids = (
        select(PayoutBatchLine.id)
        .join(PayoutBatch, PayoutBatch.id == PayoutBatchLine.batch_id)
        .where(PayoutBatch.approval_mode == PayoutBatchApprovalMode.AUTOMATIC.value)
    )
    created = 0
    failed = (
        await session.execute(
            select(PayoutBatchLine, EarningsLedgerEntry.driver_profile_id)
            .join(PayoutBatch, PayoutBatch.id == PayoutBatchLine.batch_id)
            .join(EarningsLedgerEntry, EarningsLedgerEntry.id == PayoutBatchLine.ledger_entry_id)
            .where(
                PayoutBatch.approval_mode == PayoutBatchApprovalMode.AUTOMATIC.value,
                PayoutBatchLine.status == PayoutBatchLineStatus.FAILED.value,
                ~exists().where(
                    PayoutAutomaticAlert.line_id == PayoutBatchLine.id,
                    PayoutAutomaticAlert.kind == PayoutAutomaticAlertKind.FAILED_PAYMENT.value,
                ),
            )
            .order_by(PayoutBatchLine.id)
            .limit(limit)
        )
    ).all()
    for line, driver_profile_id in failed:
        created += bool(
            await raise_alert(
                session,
                kind=PayoutAutomaticAlertKind.FAILED_PAYMENT,
                dedupe=(line.id,),
                detail={"provider_transfer_reference": line.provider_transfer_reference},
                batch_id=line.batch_id,
                line_id=line.id,
                ledger_entry_id=line.ledger_entry_id,
                driver_profile_id=driver_profile_id,
                amount=line.amount,
            )
        )
    incidents = (
        await session.scalars(
            select(PayoutRecoveryIncident)
            .where(
                PayoutRecoveryIncident.kind == PayoutRecoveryIncidentKind.DUPLICATE_CASH.value,
                (PayoutRecoveryIncident.chain_root_line_id.in_(automatic_line_ids))
                | (PayoutRecoveryIncident.exposure_line_id.in_(automatic_line_ids)),
            )
            # Newest first, so a new duplicate is never hidden behind ones already
            # alerted (dedupe happens in raise_alert).
            .order_by(PayoutRecoveryIncident.created_at.desc(), PayoutRecoveryIncident.id)
            .limit(limit)
        )
    ).all()
    for incident in incidents:
        created += bool(
            await raise_alert(
                session,
                kind=PayoutAutomaticAlertKind.DUPLICATE_PAYMENT,
                dedupe=("incident", incident.id),
                detail={"recovery_incident_id": str(incident.id), "status": incident.status},
                line_id=incident.exposure_line_id,
                ledger_entry_id=incident.ledger_entry_id,
                amount=incident.amount,
            )
        )
    observations = (
        await session.execute(
            select(PayoutSubmissionObservation, PayoutSubmissionIntent.payout_batch_line_id)
            .join(
                PayoutSubmissionIntent,
                PayoutSubmissionIntent.id == PayoutSubmissionObservation.intent_id,
            )
            .where(
                PayoutSubmissionObservation.error_code == "provider_transfer_reference_duplicate",
                PayoutSubmissionIntent.payout_batch_line_id.in_(automatic_line_ids),
            )
            .order_by(PayoutSubmissionObservation.created_at.desc(), PayoutSubmissionObservation.id)
            .limit(limit)
        )
    ).all()
    for observation, line_id in observations:
        created += bool(
            await raise_alert(
                session,
                kind=PayoutAutomaticAlertKind.DUPLICATE_PAYMENT,
                dedupe=("observation", observation.id),
                detail={
                    "provider_transfer_reference": observation.provider_transfer_reference,
                    "error_code": observation.error_code,
                },
                line_id=line_id,
            )
        )
    # Refused automatic submissions: the sweep records a durable failure audit
    # per intent; one alert per intent and error code (plan review R4).
    automatic_intents = {
        intent_id: line_id
        for intent_id, line_id in (
            await session.execute(
                select(PayoutSubmissionIntent.id, PayoutSubmissionIntent.payout_batch_line_id)
                .where(PayoutSubmissionIntent.payout_batch_line_id.in_(automatic_line_ids))
                .where(PayoutSubmissionIntent.state != PayoutSubmissionIntentState.RESOLVED.value)
            )
        ).all()
    }
    if automatic_intents:
        failures = (
            await session.execute(
                select(AuditEvent.entity_id, AuditEvent.event_metadata)
                .where(
                    AuditEvent.action == "worker.payout_submission.failed",
                    AuditEvent.entity_type == "payout_submission_intent",
                    AuditEvent.entity_id.in_([str(item) for item in automatic_intents]),
                )
                .order_by(AuditEvent.created_at.desc())
                .limit(limit * 5)
            )
        ).all()
        for entity_id, metadata in failures:
            try:
                intent_id = UUID(str(entity_id))
            except ValueError:
                continue
            if intent_id not in automatic_intents:
                continue
            error_code = str((metadata or {}).get("error_code") or "unknown")
            created += bool(
                await raise_alert(
                    session,
                    kind=PayoutAutomaticAlertKind.SUBMISSION_BLOCKED,
                    dedupe=(intent_id, error_code),
                    detail={"intent_id": str(intent_id), "error_code": error_code},
                    line_id=automatic_intents[intent_id],
                )
            )
    return created


# --- the day ceiling ---------------------------------------------------------


@dataclass
class _DayPosition:
    earned: Decimal = Decimal("0.00")
    rates: set[Decimal] = field(default_factory=set)
    mixed: bool = False
    missing_binding: bool = False

    @property
    def ceiling(self) -> Decimal | None:
        if self.mixed or self.missing_binding or len(self.rates) != 1:
            return None
        return next(iter(self.rates))


def _positive_days(amount_by_day: dict) -> dict[date, Decimal]:
    return {
        date.fromisoformat(key): _money(value)
        for key, value in amount_by_day.items()
        if _money(value) > 0
    }


async def _day_position(
    session: AsyncSession, *, driver_profile_id: UUID, day: date
) -> _DayPosition:
    """Everything the driver earned on one Lagos day, across all campaigns (A4/R5)."""
    counted_trip_payout = (
        select(EarningsLedgerEntry.id)
        .where(
            EarningsLedgerEntry.trip_session_id == PayoutCalculation.trip_session_id,
            EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value,
            EarningsLedgerEntry.status.in_(_COUNTED_ENTRY_STATUSES),
        )
        .correlate(PayoutCalculation)
        .exists()
    )
    calculations = (
        await session.scalars(
            select(PayoutCalculation)
            .join(TripSession, TripSession.id == PayoutCalculation.trip_session_id)
            .where(
                PayoutCalculation.driver_profile_id == driver_profile_id,
                _day_trip_overlap([day]),
                counted_trip_payout,
            )
            .order_by(PayoutCalculation.calculated_at, PayoutCalculation.id)
        )
    ).all()
    position = _DayPosition()
    for calculation in calculations:
        if calculation.formula_version != PAYOUT_V4:
            position.mixed = True
            continue
        if calculation.status != PayoutCalculationStatus.CALCULATED.value:
            continue
        _, amount_by_day = await latest_daily_rate_position(session, calculation)
        position.earned += _money(amount_by_day.get(day.isoformat(), "0"))
        rate = await session.scalar(
            select(AssignmentRuleBinding.daily_rate_naira).where(
                AssignmentRuleBinding.assignment_id == calculation.assignment_id,
                AssignmentRuleBinding.formula_version == PAYOUT_V4,
            )
        )
        if rate is None:
            position.missing_binding = True
        else:
            position.rates.add(_money(rate))
    return position


async def _cash_by_day(session: AsyncSession, *, driver_profile_id: UUID) -> dict[date, Decimal]:
    """Payout line amounts (manual or automatic) not void or failed for the driver's
    v4 trips, the full amount on every day the trip touched (money review #3)."""
    rows = (
        await session.execute(
            select(PayoutBatchLine.amount, PayoutCalculation.amount_by_day)
            .join(EarningsLedgerEntry, EarningsLedgerEntry.id == PayoutBatchLine.ledger_entry_id)
            .join(
                PayoutCalculation,
                PayoutCalculation.id == EarningsLedgerEntry.payout_calculation_id,
            )
            .where(
                PayoutCalculation.formula_version == PAYOUT_V4,
                EarningsLedgerEntry.driver_profile_id == driver_profile_id,
                PayoutBatchLine.status.not_in(
                    (PayoutBatchLineStatus.VOID.value, PayoutBatchLineStatus.FAILED.value)
                ),
            )
        )
    ).all()
    totals: dict[date, Decimal] = {}
    for amount, amount_by_day in rows:
        for day in _positive_days(amount_by_day or {}):
            totals[day] = totals.get(day, Decimal("0.00")) + _money(amount)
    return totals


# --- the run -----------------------------------------------------------------


@dataclass
class _Exclusions:
    by_reason: dict[str, dict[str, str | int]] = field(default_factory=dict)

    def add(self, reason: str, amount: Decimal) -> None:
        current = self.by_reason.setdefault(reason, {"count": 0, "amount": "0.00"})
        current["count"] = int(current["count"]) + 1
        current["amount"] = f"{_money(current['amount']) + amount:.2f}"


async def _clean_reason(
    session: AsyncSession,
    *,
    entry: EarningsLedgerEntry,
    payee: Payee | None,
    settings: Settings,
) -> tuple[str | None, dict[date, Decimal], tuple | None]:
    """(exclusion reason or None, the entry's paid days, payee authority)."""
    if entry.trip_session_id is None or entry.payout_calculation_id is None:
        return "not_daily_rate", {}, None
    calculation = await session.get(PayoutCalculation, entry.payout_calculation_id)
    if (
        calculation is None
        or calculation.formula_version != PAYOUT_V4
        or calculation.status != PayoutCalculationStatus.CALCULATED.value
        or calculation.trip_session_id != entry.trip_session_id
        or calculation.driver_profile_id != entry.driver_profile_id
    ):
        return "not_daily_rate", {}, None
    days = _positive_days(calculation.amount_by_day or {})
    _, latest_amounts = await latest_daily_rate_position(session, calculation)
    if (
        _money(calculation.final_payout) != entry.amount
        or sum(days.values(), Decimal("0.00")) != entry.amount
        or _positive_days(latest_amounts) != days
    ):
        return "adjusted_trip", days, None
    if await session.scalar(
        select(EarningsLedgerEntry.id)
        .where(
            EarningsLedgerEntry.trip_session_id == entry.trip_session_id,
            EarningsLedgerEntry.id != entry.id,
            EarningsLedgerEntry.status != EarningsLedgerEntryStatus.VOIDED.value,
        )
        .limit(1)
    ):
        return "adjusted_trip", days, None
    if await session.scalar(
        select(FraudFlag.id)
        .where(FraudFlag.trip_session_id == entry.trip_session_id, fraud_hold_active_clause())
        .limit(1)
    ):
        return "fraud_hold", days, None
    if await session.scalar(
        select(FraudFlag.id).where(FraudFlag.trip_session_id == entry.trip_session_id).limit(1)
    ):
        return "fraud_flag", days, None
    if await session.scalar(
        select(FraudDispute.id)
        .where(
            FraudDispute.driver_profile_id == entry.driver_profile_id,
            FraudDispute.status == FraudDisputeStatus.OPEN.value,
        )
        .limit(1)
    ):
        return "open_dispute", days, None
    assessment = await load_current_successful_assessment(
        session, trip_id=entry.trip_session_id, settings=settings, lock_rows=True
    )
    if not assessment.current:
        return "assessment_not_current", days, None
    if payee is None:
        return "payee_unverified", days, None
    try:
        authority = await _frozen_payee_authority(session, entry, payee)
    except AppError:
        return "payee_unverified", days, None
    if not await bank_account_paid_before(session, authority[1].id):
        return "new_bank_destination", days, None
    return None, days, authority


async def bank_account_paid_before(session: AsyncSession, bank_account_version_id: UUID) -> bool:
    """One admin may add and verify a bank account (D29); with no batch approver,
    the first payment to an account stays manual until a person has paid it."""
    return (
        await session.scalar(
            select(PayoutBatchLine.id)
            .where(
                PayoutBatchLine.bank_account_version_id == bank_account_version_id,
                PayoutBatchLine.status == PayoutBatchLineStatus.SUCCEEDED.value,
            )
            .limit(1)
        )
        is not None
    )


async def run_automatic_payouts(
    session: AsyncSession,
    *,
    settings: Settings,
    adapter: DisbursementAdapter,
    now: datetime | None = None,
) -> dict[str, object]:
    """One automatic payout pass. The caller commits."""
    missing = missing_automatic_settings(settings)
    if missing:
        return {"outcome": "not_set_up", "missing_settings": missing}
    now = now or datetime.now(UTC)
    frequency = str(settings.payout_automatic_frequency)
    limit = _money(settings.payout_automatic_batch_limit_ngn)
    period = period_key_for(now, frequency)
    control = await load_control(session, lock="update")
    problem = await actor_integrity_problem(session, control)
    if problem is not None:
        await raise_alert(
            session,
            kind=PayoutAutomaticAlertKind.RUN_FAILED,
            dedupe=(problem, period),
            detail={"reason": problem, "period": period},
        )
        return {"outcome": "actor_invalid", "reason": problem}
    assert control is not None
    if control.paused:
        return {"outcome": "paused"}
    if await session.scalar(
        select(PayoutAutomaticRun.id).where(PayoutAutomaticRun.period_key == period)
    ):
        return {"outcome": "already_ran", "period": period}
    try:
        capabilities = _submission_capabilities(adapter)
    except AppError:
        await raise_alert(
            session,
            kind=PayoutAutomaticAlertKind.RUN_FAILED,
            dedupe=("provider_unavailable", period),
            detail={"reason": "provider_unavailable", "period": period},
        )
        return {"outcome": "provider_unavailable", "period": period}

    earlier_automatic_line = (
        select(PayoutBatchLine.id)
        .join(PayoutBatch, PayoutBatch.id == PayoutBatchLine.batch_id)
        .where(
            PayoutBatchLine.ledger_entry_id == EarningsLedgerEntry.id,
            (PayoutBatch.approval_mode == PayoutBatchApprovalMode.AUTOMATIC.value)
            | (PayoutBatchLine.reservation_active.is_(True))
            | (PayoutBatchLine.status == PayoutBatchLineStatus.FAILED.value),
        )
        .correlate(EarningsLedgerEntry)
        .exists()
    )
    other_entry = aliased(EarningsLedgerEntry)
    stubs = (
        await session.execute(
            select(
                EarningsLedgerEntry.id,
                EarningsLedgerEntry.trip_session_id,
                EarningsLedgerEntry.driver_profile_id,
            )
            .join(
                PayoutCalculation,
                PayoutCalculation.id == EarningsLedgerEntry.payout_calculation_id,
            )
            .where(
                EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value,
                EarningsLedgerEntry.status == EarningsLedgerEntryStatus.AVAILABLE.value,
                EarningsLedgerEntry.amount > 0,
                EarningsLedgerEntry.currency == AUTOMATIC_CURRENCY,
                EarningsLedgerEntry.trip_session_id.is_not(None),
                PayoutCalculation.formula_version == PAYOUT_V4,
                ~earlier_automatic_line,
                # Permanently unclean trips never take a scan place (money review
                # #2): any review flag, or any other non-voided entry on the trip.
                ~exists().where(FraudFlag.trip_session_id == EarningsLedgerEntry.trip_session_id),
                ~exists().where(
                    other_entry.trip_session_id == EarningsLedgerEntry.trip_session_id,
                    other_entry.id != EarningsLedgerEntry.id,
                    other_entry.status != EarningsLedgerEntryStatus.VOIDED.value,
                ),
            )
            .order_by(EarningsLedgerEntry.occurred_at, EarningsLedgerEntry.id)
            .limit(MAX_CANDIDATES_PER_RUN)
        )
    ).all()
    exclusions = _Exclusions()
    included: list[tuple[EarningsLedgerEntry, tuple]] = []
    running = Decimal("0.00")
    if stubs:
        await lock_fraud_hold_scopes(session, (stub.trip_session_id for stub in stubs))
        indebted: set[UUID] = set()
        for driver_profile_id in sorted({stub.driver_profile_id for stub in stubs}, key=str):
            _, debt = await lock_driver_currency_debt_scope(
                session, driver_profile_id=driver_profile_id, currency=AUTOMATIC_CURRENCY
            )
            if debt is not None and debt.outstanding_amount > 0:
                indebted.add(driver_profile_id)
        entries = {
            entry.id: entry
            for entry in (
                await session.scalars(
                    select(EarningsLedgerEntry)
                    .where(EarningsLedgerEntry.id.in_([stub.id for stub in stubs]))
                    .order_by(EarningsLedgerEntry.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        }
        payees = {
            (payee.subject_id, payee.tenant_id): payee
            for payee in (
                await session.scalars(
                    select(Payee)
                    .where(
                        Payee.payee_type == "driver",
                        Payee.subject_id.in_({stub.driver_profile_id for stub in stubs}),
                    )
                    .order_by(Payee.id)
                    .with_for_update()
                )
            ).all()
        }
        positions: dict[tuple[UUID, date], _DayPosition] = {}
        cash: dict[UUID, dict[date, Decimal]] = {}
        for stub in stubs:
            entry = entries[stub.id]
            if (
                entry.status != EarningsLedgerEntryStatus.AVAILABLE.value
                or entry.entry_type != EarningsLedgerEntryType.TRIP_PAYOUT.value
                or entry.amount <= 0
            ):
                continue
            if entry.driver_profile_id in indebted:
                exclusions.add("debt_outstanding", entry.amount)
                continue
            reason, days, authority = await _clean_reason(
                session,
                entry=entry,
                payee=payees.get((entry.driver_profile_id, entry.driver_user_id)),
                settings=settings,
            )
            if reason is None:
                driver_cash = cash.get(entry.driver_profile_id)
                if driver_cash is None:
                    driver_cash = await _cash_by_day(
                        session, driver_profile_id=entry.driver_profile_id
                    )
                    cash[entry.driver_profile_id] = driver_cash
                for day in sorted(days):
                    scope = (entry.driver_profile_id, day)
                    if scope not in positions:
                        positions[scope] = await _day_position(
                            session, driver_profile_id=entry.driver_profile_id, day=day
                        )
                    position = positions[scope]
                    ceiling = position.ceiling
                    over_cash = (
                        ceiling is not None
                        and driver_cash.get(day, Decimal("0.00")) + entry.amount > ceiling
                    )
                    if ceiling is None or position.earned > ceiling or over_cash:
                        reason = "daily_limit"
                        await raise_alert(
                            session,
                            kind=PayoutAutomaticAlertKind.DAILY_LIMIT,
                            dedupe=(
                                (entry.driver_profile_id, day, position.earned, ceiling)
                                if not over_cash
                                else ("cash", entry.id, day)
                            ),
                            detail={
                                "earned": f"{position.earned:.2f}",
                                "ceiling": None if ceiling is None else f"{ceiling:.2f}",
                                "rates_differ": len(position.rates) > 1,
                                "other_pay_type_same_day": position.mixed,
                                "day_rate_missing": position.missing_binding,
                                "already_paid_or_sending": f"{driver_cash.get(day, 0):.2f}",
                            },
                            ledger_entry_id=entry.id,
                            driver_profile_id=entry.driver_profile_id,
                            lagos_day=day,
                            amount=entry.amount,
                        )
                        break
            if reason is not None:
                exclusions.add(reason, entry.amount)
                continue
            if entry.amount > limit:
                exclusions.add("above_run_limit", entry.amount)
                await raise_alert(
                    session,
                    kind=PayoutAutomaticAlertKind.BATCH_LIMIT,
                    dedupe=("entry", entry.id),
                    detail={"reason": "above_run_limit", "limit": f"{limit:.2f}"},
                    ledger_entry_id=entry.id,
                    driver_profile_id=entry.driver_profile_id,
                    amount=entry.amount,
                )
                continue
            if running + entry.amount > limit:
                # Stop at the first miss (R10): later entries wait for the next run.
                waiting = [stub.id for stub in stubs[stubs.index(stub) :]]
                await raise_alert(
                    session,
                    kind=PayoutAutomaticAlertKind.BATCH_LIMIT,
                    dedupe=("run", period),
                    detail={
                        "reason": "run_limit_reached",
                        "limit": f"{limit:.2f}",
                        "waiting_candidates": len(waiting),
                        "period": period,
                    },
                    amount=running,
                )
                break
            running += entry.amount
            for day in days:
                cash[entry.driver_profile_id][day] = (
                    cash[entry.driver_profile_id].get(day, Decimal("0.00")) + entry.amount
                )
            included.append((entry, authority))

    by_driver: dict[UUID, list[tuple[EarningsLedgerEntry, tuple]]] = {}
    for entry, authority in included:
        by_driver.setdefault(entry.driver_profile_id, []).append((entry, authority))
    run = PayoutAutomaticRun(
        id=uuid4(),
        period_key=period,
        frequency=frequency,
        currency=AUTOMATIC_CURRENCY,
        batch_limit=limit,
        total_amount=running,
        batch_count=len(by_driver),
        line_count=len(included),
        exclusions=exclusions.by_reason,
        settings_fingerprint=_settings_fingerprint(settings),
    )
    batches: list[tuple[PayoutBatch, list[PayoutBatchLine]]] = []
    try:
        async with session.begin_nested():
            session.add(run)
            await session.flush()
            for driver_profile_id in sorted(by_driver, key=str):
                batch = PayoutBatch(
                    id=uuid4(),
                    status=PayoutBatchStatus.RESERVED.value,
                    currency=AUTOMATIC_CURRENCY,
                    created_by_user_id=CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID,
                    approval_mode=PayoutBatchApprovalMode.AUTOMATIC.value,
                    automatic_run_id=run.id,
                    approved_at=now,
                )
                lines = [
                    build_frozen_payout_line(
                        batch_id=batch.id,
                        entry=entry,
                        payee_version=authority[0],
                        account_version=authority[1],
                    )
                    for entry, authority in sorted(
                        by_driver[driver_profile_id], key=lambda item: str(item[0].id)
                    )
                ]
                freeze_batch_instruction_set(batch, lines)
                session.add(batch)
                await session.flush()
                session.add_all(lines)
                await session.flush()
                for line in lines:
                    session.add(
                        PayoutSubmissionIntent(
                            payout_batch_line_id=line.id,
                            provider_name=capabilities.provider_name,
                            idempotency_key=line.idempotency_key,
                            instruction=dict(line.instruction),
                            instruction_fingerprint=line.instruction_fingerprint,
                            requested_by_user_id=CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID,
                        )
                    )
                await session.flush()
                batches.append((batch, lines))
    except IntegrityError as exc:
        if integrity_constraint_name(exc) not in {
            "uq_payout_batch_lines_active_ledger_entry",
            "uq_payout_automatic_runs_period_key",
        }:
            raise
        return {"outcome": "conflict", "period": period}
    for batch, lines in batches:
        await create_audit_event(
            session,
            actor_user_id=CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID,
            action="system.payout_batch.automatically_approved",
            entity_type="payout_batch",
            entity_id=str(batch.id),
            metadata={
                "automatic_run_id": str(run.id),
                "period": period,
                "line_count": len(lines),
                "currency": batch.currency,
                "total_amount": f"{batch.total_amount:.2f}",
            },
        )
    await create_audit_event(
        session,
        actor_user_id=CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID,
        action="system.payout_automatic_run.completed",
        entity_type="payout_automatic_run",
        entity_id=str(run.id),
        metadata={
            "period": period,
            "batch_count": run.batch_count,
            "line_count": run.line_count,
            "total_amount": f"{run.total_amount:.2f}",
            "batch_limit": f"{limit:.2f}",
            "exclusions": exclusions.by_reason,
            "settings_fingerprint": run.settings_fingerprint,
        },
    )
    return {
        "outcome": "completed",
        "period": period,
        "run_id": str(run.id),
        "batch_count": run.batch_count,
        "line_count": run.line_count,
        "total_amount": f"{run.total_amount:.2f}",
    }


async def automatic_final_clean_authority(
    session: AsyncSession,
    *,
    batch: PayoutBatch,
    trip_ids: tuple[UUID, ...],
    driver_profile_ids: tuple[UUID, ...],
) -> dict[str, object]:
    """Extra final-gate checks for an automatic SUBMIT (A10). Callers hold the locks."""
    if await session.scalar(
        select(FraudFlag.id).where(FraudFlag.trip_session_id.in_(trip_ids)).limit(1)
    ):
        raise _error(
            "PAYOUT_AUTOMATIC_NOT_CLEAN",
            "A trip in this automatic payout now has a review flag",
        )
    if await session.scalar(
        select(FraudDispute.id)
        .where(
            FraudDispute.driver_profile_id.in_(driver_profile_ids),
            FraudDispute.status == FraudDisputeStatus.OPEN.value,
        )
        .limit(1)
    ):
        raise _error(
            "PAYOUT_AUTOMATIC_NOT_CLEAN",
            "A driver in this automatic payout has an open dispute",
        )
    return {
        "approval_mode": PayoutBatchApprovalMode.AUTOMATIC.value,
        "automatic_run_id": str(batch.automatic_run_id),
        "automatic_clean_check": "no_flag_no_open_dispute_v1",
    }


# --- Finance actions -----------------------------------------------------------


def _reason(value: str) -> str:
    reason = value.strip()
    if not REASON_MIN <= len(reason) <= REASON_MAX:
        raise _error(
            "PAYOUT_AUTOMATIC_REASON_INVALID",
            "Give a reason between 3 and 500 characters",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return reason


async def _locked_control(session: AsyncSession) -> PayoutAutomaticControl:
    control = await load_control(session, lock="update")
    if control is None:
        raise _error(
            "PAYOUT_AUTOMATIC_NOT_INSTALLED",
            "Automatic payouts are not installed on this database",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return control


async def set_automatic_payouts_paused(
    session: AsyncSession, *, paused: bool, reason: str, actor_user_id: UUID
) -> PayoutAutomaticControl:
    await require_active_admin(session, actor_user_id)
    reason = _reason(reason)
    control = await _locked_control(session)
    if control.paused == paused:
        raise _error(
            "PAYOUT_AUTOMATIC_ALREADY_PAUSED" if paused else "PAYOUT_AUTOMATIC_NOT_PAUSED",
            "Automatic payouts are already paused"
            if paused
            else "Automatic payouts are not paused",
        )
    before = {
        "paused": control.paused,
        "reason": control.reason,
        "changed_by_user_id": str(control.changed_by_user_id)
        if control.changed_by_user_id
        else None,
        "changed_at": control.changed_at.isoformat() if control.changed_at else None,
    }
    changed_at = datetime.now(UTC)
    control.paused = paused
    control.reason = reason
    control.changed_by_user_id = actor_user_id
    control.changed_at = changed_at
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.payout_automatic.paused" if paused else "admin.payout_automatic.resumed",
        entity_type="payout_automatic_control",
        entity_id=str(control.id),
        metadata={
            "before": before,
            "after": {"paused": paused, "reason": reason, "changed_at": changed_at.isoformat()},
            "reason": reason,
        },
    )
    await create_active_admin_notices(
        session,
        type_key=NotificationType.PAYOUT_AUTOMATIC_PAUSED
        if paused
        else NotificationType.PAYOUT_AUTOMATIC_RESUMED,
        event_key=f"payout-automatic-switch:v1:{changed_at.isoformat()}",
        payload={"paused": str(paused).lower()},
        exclude_user_id=actor_user_id,
    )
    return control


async def _unsent_intent_rows(session: AsyncSession) -> list[tuple[UUID, UUID]]:
    """(batch_id, intent_id) for automatic intents never tried with the provider."""
    return [
        (row.batch_id, row.id)
        for row in (
            await session.execute(
                select(PayoutBatchLine.batch_id, PayoutSubmissionIntent.id)
                .join(
                    PayoutSubmissionIntent,
                    PayoutSubmissionIntent.payout_batch_line_id == PayoutBatchLine.id,
                )
                .join(PayoutBatch, PayoutBatch.id == PayoutBatchLine.batch_id)
                .where(
                    PayoutBatch.approval_mode == PayoutBatchApprovalMode.AUTOMATIC.value,
                    PayoutBatchLine.status == PayoutBatchLineStatus.RESERVED.value,
                    PayoutSubmissionIntent.state == PayoutSubmissionIntentState.PENDING.value,
                    ~exists().where(PayoutSubmissionAttempt.intent_id == PayoutSubmissionIntent.id),
                )
                .order_by(PayoutBatchLine.batch_id, PayoutSubmissionIntent.id)
            )
        ).all()
    ]


async def release_unsent_automatic_payments(
    session: AsyncSession, *, reason: str, actor_user_id: UUID, settings: Settings
) -> dict[str, object]:
    """Move never-tried automatic payments back to the maker-checker path (A8/R3)."""
    await require_active_admin(session, actor_user_id)
    reason = _reason(reason)
    control = await _locked_control(session)
    if not control.paused and not missing_automatic_settings(settings):
        raise _error(
            "PAYOUT_AUTOMATIC_RELEASE_REQUIRES_PAUSE",
            "Pause automatic payouts before moving unsent payments to manual review",
        )
    rows = await _unsent_intent_rows(session)
    batch_ids = sorted({batch_id for batch_id, _ in rows}, key=str)
    if batch_ids:
        trip_ids = tuple(
            await session.scalars(
                select(EarningsLedgerEntry.trip_session_id)
                .join(PayoutBatchLine, PayoutBatchLine.ledger_entry_id == EarningsLedgerEntry.id)
                .where(
                    PayoutBatchLine.batch_id.in_(batch_ids),
                    EarningsLedgerEntry.trip_session_id.is_not(None),
                )
                .distinct()
            )
        )
        await lock_fraud_hold_scopes(session, trip_ids)
    released_at = datetime.now(UTC)
    released = 0
    released_amount = Decimal("0.00")
    for batch_id in batch_ids:
        batch, lines = await _locked_batch_with_lines(session, batch_id)
        intents = {
            intent.payout_batch_line_id: intent
            for intent in (
                await session.scalars(
                    select(PayoutSubmissionIntent)
                    .where(
                        PayoutSubmissionIntent.payout_batch_line_id.in_([line.id for line in lines])
                    )
                    .order_by(PayoutSubmissionIntent.payout_batch_line_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        }
        released_lines: list[str] = []
        for line in lines:
            intent = intents.get(line.id)
            if intent is None or await session.scalar(
                select(PayoutSubmissionAttempt.id)
                .where(PayoutSubmissionAttempt.intent_id == intent.id)
                .limit(1)
            ):
                continue
            if _cancel_uncalled_line(line, intent, cancelled_at=released_at):
                released_lines.append(str(line.id))
                released_amount += line.amount
        if not released_lines:
            continue
        batch.status = _derive_batch_status(lines).value
        await session.flush()
        released += len(released_lines)
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="admin.payout_automatic.released_to_manual",
            entity_type="payout_batch",
            entity_id=str(batch.id),
            metadata={"reason": reason, "line_ids": released_lines},
        )
    return {"released_count": released, "released_amount": released_amount}


async def resolve_automatic_payout_alert(
    session: AsyncSession, *, alert_id: UUID, note: str, actor_user_id: UUID
) -> PayoutAutomaticAlert:
    await require_active_admin(session, actor_user_id)
    note = _reason(note)
    alert = await session.scalar(
        select(PayoutAutomaticAlert).where(PayoutAutomaticAlert.id == alert_id).with_for_update()
    )
    if alert is None:
        raise _error(
            "PAYOUT_AUTOMATIC_ALERT_NOT_FOUND", "Alert was not found", status.HTTP_404_NOT_FOUND
        )
    if alert.resolved_at is not None:
        raise _error("PAYOUT_AUTOMATIC_ALERT_RESOLVED", "This alert is already followed up")
    alert.resolved_by_user_id = actor_user_id
    alert.resolved_at = datetime.now(UTC)
    alert.resolution_note = note
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.payout_automatic_alert.resolved",
        entity_type="payout_automatic_alert",
        entity_id=str(alert.id),
        metadata={"kind": alert.kind, "note": note},
    )
    return alert


# --- read models ----------------------------------------------------------------


def _page(limit: int, offset: int) -> None:
    if not 1 <= limit <= 100 or offset < 0:
        raise _error(
            "PAYOUT_PAGE_INVALID",
            "Choose a valid result page",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


async def automatic_payout_status(
    session: AsyncSession, *, settings: Settings, adapter: DisbursementAdapter
) -> dict[str, object]:
    control = await load_control(session)
    problem = await actor_integrity_problem(session, control)
    changed_by = (
        await session.get(User, control.changed_by_user_id)
        if control is not None and control.changed_by_user_id
        else None
    )
    try:
        _submission_capabilities(adapter)
        provider_ready = True
    except AppError:
        provider_ready = False
    last_run = await session.scalar(
        select(PayoutAutomaticRun).order_by(PayoutAutomaticRun.created_at.desc()).limit(1)
    )
    missing = missing_automatic_settings(settings)
    open_alerts = int(
        await session.scalar(
            select(func.count(PayoutAutomaticAlert.id)).where(
                PayoutAutomaticAlert.resolved_at.is_(None)
            )
        )
        or 0
    )
    paused = bool(control and control.paused)
    return {
        "switched_on": settings.payout_automatic_approval_enabled,
        "frequency": settings.payout_automatic_frequency,
        "batch_limit": settings.payout_automatic_batch_limit_ngn,
        "currency": AUTOMATIC_CURRENCY,
        "missing_settings": missing,
        "paused": paused,
        "pause_reason": control.reason if control else None,
        "pause_changed_by_name": changed_by.full_name if changed_by else None,
        "pause_changed_at": control.changed_at if control else None,
        "identity_ready": problem is None,
        "provider_ready": provider_ready,
        "runnable": not missing and not paused and problem is None and provider_ready,
        "last_run": None
        if last_run is None
        else {
            "id": last_run.id,
            "period_key": last_run.period_key,
            "created_at": last_run.created_at,
            "batch_count": last_run.batch_count,
            "line_count": last_run.line_count,
            "total_amount": last_run.total_amount,
        },
        "open_alert_count": open_alerts,
        "unsent_count": len(await _unsent_intent_rows(session)),
    }


async def list_automatic_payout_alerts(
    session: AsyncSession,
    *,
    alert_status: str,
    limit: int = 25,
    offset: int = 0,
    alert_id: UUID | None = None,
    oldest_first: bool = False,
) -> dict[str, object]:
    _page(limit, offset)
    query = select(PayoutAutomaticAlert)
    if alert_id is not None:
        query = query.where(PayoutAutomaticAlert.id == alert_id)
    if alert_status == "open":
        query = query.where(PayoutAutomaticAlert.resolved_at.is_(None))
    elif alert_status == "resolved":
        query = query.where(PayoutAutomaticAlert.resolved_at.is_not(None))
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    driver = aliased(User)
    resolver = aliased(User)
    from app.models.driver import DriverProfile

    rows = (
        await session.execute(
            select(PayoutAutomaticAlert, driver.full_name, resolver.full_name)
            .select_from(PayoutAutomaticAlert)
            .outerjoin(DriverProfile, DriverProfile.id == PayoutAutomaticAlert.driver_profile_id)
            .outerjoin(driver, driver.id == DriverProfile.user_id)
            .outerjoin(resolver, resolver.id == PayoutAutomaticAlert.resolved_by_user_id)
            .where(PayoutAutomaticAlert.id.in_(query.with_only_columns(PayoutAutomaticAlert.id)))
            .order_by(
                PayoutAutomaticAlert.created_at.asc()
                if oldest_first
                else PayoutAutomaticAlert.created_at.desc(),
                PayoutAutomaticAlert.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {
        "items": [
            {
                "id": alert.id,
                "kind": alert.kind,
                "created_at": alert.created_at,
                "driver_name": driver_name,
                "lagos_day": alert.lagos_day,
                "amount": alert.amount,
                "currency": alert.currency,
                "batch_id": alert.batch_id,
                "line_id": alert.line_id,
                "detail": alert.detail,
                "resolved_at": alert.resolved_at,
                "resolved_by_name": resolver_name,
                "resolution_note": alert.resolution_note,
            }
            for alert, driver_name, resolver_name in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


async def automatic_reconciliation_day(
    session: AsyncSession, *, day: date, limit: int = 25, offset: int = 0
) -> dict[str, object]:
    """The Finance Officer's daily view of automatic payouts (A12). Read-only."""
    _page(limit, offset)
    start, end = lagos_day_utc_range(day)
    runs = (
        await session.scalars(
            select(PayoutAutomaticRun)
            .where(PayoutAutomaticRun.created_at >= start, PayoutAutomaticRun.created_at < end)
            .order_by(PayoutAutomaticRun.created_at)
        )
    ).all()
    day_batches = select(PayoutBatch.id).where(
        PayoutBatch.approval_mode == PayoutBatchApprovalMode.AUTOMATIC.value,
        PayoutBatch.created_at >= start,
        PayoutBatch.created_at < end,
    )
    rows = (
        await session.execute(
            select(PayoutBatchLine.status, PayoutSubmissionIntent.state, PayoutBatchLine.amount)
            .outerjoin(
                PayoutSubmissionIntent,
                PayoutSubmissionIntent.payout_batch_line_id == PayoutBatchLine.id,
            )
            .where(PayoutBatchLine.batch_id.in_(day_batches))
        )
    ).all()
    outcomes: dict[str, dict[str, object]] = {}
    for line_status, intent_state, amount in rows:
        outcome = _outcome(line_status, intent_state)
        current = outcomes.setdefault(outcome, {"count": 0, "amount": Decimal("0.00")})
        current["count"] = int(current["count"]) + 1
        current["amount"] = _money(current["amount"]) + _money(amount)
    automatic_lines = (
        select(PayoutBatchLine.id)
        .join(PayoutBatch, PayoutBatch.id == PayoutBatchLine.batch_id)
        .where(PayoutBatch.approval_mode == PayoutBatchApprovalMode.AUTOMATIC.value)
    )
    evidence_rows = (
        await session.execute(
            select(
                PayoutLineReconciliationEvent.outcome,
                PayoutLineReconciliationEvent.applied,
                func.count(PayoutLineReconciliationEvent.id),
            )
            .where(
                PayoutLineReconciliationEvent.line_id.in_(automatic_lines),
                PayoutLineReconciliationEvent.created_at >= start,
                PayoutLineReconciliationEvent.created_at < end,
            )
            .group_by(PayoutLineReconciliationEvent.outcome, PayoutLineReconciliationEvent.applied)
        )
    ).all()
    alerts_raised = (
        await session.execute(
            select(PayoutAutomaticAlert.kind, func.count(PayoutAutomaticAlert.id))
            .where(PayoutAutomaticAlert.created_at >= start, PayoutAutomaticAlert.created_at < end)
            .group_by(PayoutAutomaticAlert.kind)
        )
    ).all()
    awaiting_provider = int(
        await session.scalar(
            select(func.count(PayoutBatchLine.id)).where(
                PayoutBatchLine.batch_id.in_(day_batches),
                PayoutBatchLine.status == PayoutBatchLineStatus.SUBMITTED.value,
            )
        )
        or 0
    )
    kept_manual: dict[str, dict[str, object]] = {}
    for run in runs:
        for reason, value in (run.exclusions or {}).items():
            current = kept_manual.setdefault(reason, {"count": 0, "amount": Decimal("0.00")})
            current["count"] = int(current["count"]) + int(value.get("count", 0))
            current["amount"] = _money(current["amount"]) + _money(value.get("amount", "0"))
    total_lines = len(rows)
    driver = aliased(User)
    line_rows = (
        await session.execute(
            select(PayoutBatchLine, PayoutSubmissionIntent.state, driver.full_name)
            .join(EarningsLedgerEntry, EarningsLedgerEntry.id == PayoutBatchLine.ledger_entry_id)
            .join(driver, driver.id == EarningsLedgerEntry.driver_user_id)
            .outerjoin(
                PayoutSubmissionIntent,
                PayoutSubmissionIntent.payout_batch_line_id == PayoutBatchLine.id,
            )
            .where(PayoutBatchLine.batch_id.in_(day_batches))
            .order_by(PayoutBatchLine.created_at, PayoutBatchLine.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {
        "day": day,
        "runs": [
            {
                "id": run.id,
                "period_key": run.period_key,
                "created_at": run.created_at,
                "batch_count": run.batch_count,
                "line_count": run.line_count,
                "total_amount": run.total_amount,
                "batch_limit": run.batch_limit,
            }
            for run in runs
        ],
        "outcomes": [
            {"outcome": key, "count": value["count"], "amount": value["amount"]}
            for key, value in sorted(outcomes.items())
        ],
        "provider_evidence": [
            {"outcome": outcome, "applied": applied, "count": count}
            for outcome, applied, count in sorted(evidence_rows, key=lambda row: (row[0], row[1]))
        ],
        "awaiting_provider_count": awaiting_provider,
        "alerts_raised": [{"kind": kind, "count": count} for kind, count in sorted(alerts_raised)],
        "kept_for_manual_review": [
            {"reason": key, "count": value["count"], "amount": value["amount"]}
            for key, value in sorted(kept_manual.items())
        ],
        "lines": [
            {
                "id": line.id,
                "batch_id": line.batch_id,
                "driver_name": driver_name,
                "amount": line.amount,
                "currency": line.currency,
                "outcome": _outcome(line.status, intent_state),
                "provider_transfer_reference": line.provider_transfer_reference,
                "last_provider_evidence_at": line.last_provider_evidence_at,
            }
            for line, intent_state, driver_name in line_rows
        ],
        "total": total_lines,
        "limit": limit,
        "offset": offset,
    }

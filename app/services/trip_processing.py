from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.impression import ImpressionEstimate
from app.models.payout import (
    CampaignPayoutRule,
    CampaignPayoutRuleStatus,
    EarningsLedgerEntry,
    EarningsLedgerEntryType,
    PayoutCalculation,
    PayoutCalculationStatus,
)
from app.models.trip import TripSealReason, TripSession, TripSessionStatus
from app.models.trip_analytics import (
    FraudFlag,
    FraudFlagSeverity,
    FraudFlagStatus,
    TripAnalytics,
)
from app.services.audit import create_audit_event
from app.services.impressions import (
    estimate_trip_impressions,
    is_current_estimate_for_analytics,
)
from app.services.impressions import (
    open_fraud_counts as impression_open_fraud_counts,
)
from app.services.payouts import (
    PAYOUT_V2,
    calculate_trip_payout,
    repair_missing_ledger_entries,
)
from app.services.trip_analytics import recompute_trip_analytics
from app.services.trips import trip_not_found, try_seal_trip

WORKER_METADATA = {"source": "worker"}
AUDIT_ACTION_TRIP_PROCESSING = "worker.trip_processing.completed"


@dataclass(frozen=True)
class StageResult:
    stage: str
    outcome: str  # created | reused | skipped | blocked
    reason: str | None = None
    row_ids: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TripProcessingResult:
    trip_id: UUID
    overall: str  # completed | partial | blocked
    stages: list[StageResult]


@dataclass(frozen=True)
class DueTrip:
    id: UUID
    ended_at: datetime


async def database_now(session: AsyncSession) -> datetime:
    value = await session.scalar(select(func.now()))
    if value is None:
        raise RuntimeError("Database clock did not return a timestamp")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _audit_processing_writes(
    session: AsyncSession,
    *,
    trip: TripSession,
    stages: list[StageResult],
    created_ledger_ids: list[UUID],
    repaired_ledger_ids: list[UUID],
) -> None:
    created_row_ids = {
        key: value
        for stage in stages
        if stage.outcome == "created"
        for key, value in stage.row_ids.items()
        if key.endswith("_id")
    }
    for index, ledger_id in enumerate(created_ledger_ids, start=1):
        key = "earnings_ledger_entry_id" if len(created_ledger_ids) == 1 else (
            f"earnings_ledger_entry_{index}_id"
        )
        created_row_ids.setdefault(key, str(ledger_id))
    await create_audit_event(
        session,
        actor_user_id=None,
        action=AUDIT_ACTION_TRIP_PROCESSING,
        entity_type="trip_session",
        entity_id=str(trip.id),
        metadata={
            "stages": {stage.stage: stage.outcome for stage in stages},
            "created_row_ids": created_row_ids,
            "repaired_ledger_entry_ids": [str(entry_id) for entry_id in repaired_ledger_ids],
        },
    )


async def process_ended_trip(
    session: AsyncSession,
    *,
    trip_id: UUID,
    settings: Settings,
    now: datetime | None = None,
) -> TripProcessingResult:
    trip = await session.get(TripSession, trip_id)
    if trip is None:
        raise trip_not_found()
    # Sealed is the SOLE money-chain trigger (RM3): an `ended` trip may still
    # be receiving late batches inside the grace window and must not have its
    # write-once money computed from an incomplete ping set.
    if trip.status != TripSessionStatus.SEALED.value or trip.ended_at is None:
        return TripProcessingResult(
            trip_id=trip_id,
            overall="blocked",
            stages=[StageResult(stage="trip", outcome="blocked", reason="trip_not_sealed")],
        )

    processing_now = now or await database_now(session)
    stages: list[StageResult] = []
    repaired_ledgers = await repair_missing_ledger_entries(
        session,
        trip_id=trip.id,
    )
    repaired_ledger_ids = [ledger.id for ledger in repaired_ledgers]
    if repaired_ledgers:
        stages.append(
            StageResult(
                stage="ledger_repair",
                outcome="created",
                row_ids={
                    f"earnings_ledger_entry_{index}_id": str(ledger.id)
                    for index, ledger in enumerate(repaired_ledgers, start=1)
                },
            )
        )

    analytics = await session.scalar(
        select(TripAnalytics).where(TripAnalytics.trip_session_id == trip.id)
    )
    if analytics is not None:
        if analytics.formula_version != settings.route_analytics_formula_version:
            stages.extend(
                [
                    StageResult(
                        stage="analytics",
                        outcome="blocked",
                        reason="analytics_formula_version_mismatch",
                        row_ids={"trip_analytics_id": str(analytics.id)},
                    ),
                    StageResult(
                        stage="impressions",
                        outcome="skipped",
                        reason="analytics_formula_version_mismatch",
                    ),
                    StageResult(
                        stage="payout",
                        outcome="skipped",
                        reason="analytics_formula_version_mismatch",
                    ),
                ]
            )
            if repaired_ledger_ids:
                await _audit_processing_writes(
                    session,
                    trip=trip,
                    stages=stages,
                    created_ledger_ids=repaired_ledger_ids,
                    repaired_ledger_ids=repaired_ledger_ids,
                )
            return TripProcessingResult(trip_id=trip.id, overall="blocked", stages=stages)
        stages.append(
            StageResult(
                stage="analytics",
                outcome="reused",
                row_ids={"trip_analytics_id": str(analytics.id)},
            )
        )
    else:
        computation = await recompute_trip_analytics(
            session,
            trip_id=trip.id,
            metadata=dict(WORKER_METADATA),
            settings=settings,
            now=processing_now,
        )
        analytics = computation.analytics
        stages.append(
            StageResult(
                stage="analytics",
                outcome="created",
                row_ids={
                    "trip_analytics_id": str(computation.analytics.id),
                    "open_fraud_flag_count": str(len(computation.fraud_flags)),
                },
            )
        )

    # Reuse only an estimate derived from the current analytics and open-fraud state.
    current_fraud_counts = await impression_open_fraud_counts(session, trip.id)
    estimate_result = await session.execute(
        select(ImpressionEstimate)
        .where(
            ImpressionEstimate.trip_session_id == trip.id,
            ImpressionEstimate.formula_version == settings.impression_formula_version,
        )
        .order_by(ImpressionEstimate.estimated_at.desc(), ImpressionEstimate.id)
    )
    estimate = next(
        (
            candidate
            for candidate in estimate_result.scalars().all()
            if is_current_estimate_for_analytics(
                candidate,
                analytics,
                settings,
                fraud_counts=current_fraud_counts,
            )
        ),
        None,
    )
    if estimate is not None:
        stages.append(
            StageResult(
                stage="impressions",
                outcome="reused",
                row_ids={"impression_estimate_id": str(estimate.id)},
            )
        )
    else:
        estimate = await estimate_trip_impressions(
            session,
            trip_id=trip.id,
            traffic_density_profile_id=None,
            metadata=dict(WORKER_METADATA),
            settings=settings,
            now=processing_now,
        )
        stages.append(
            StageResult(
                stage="impressions",
                outcome="created",
                row_ids={"impression_estimate_id": str(estimate.id)},
            )
        )

    prior_ledger_ids = set(
        (
            await session.execute(
                select(EarningsLedgerEntry.id).where(
                    EarningsLedgerEntry.trip_session_id == trip.id
                )
            )
        ).scalars()
    )
    try:
        calculation, ledger, calculation_created = await calculate_trip_payout(
            session,
            trip_id=trip.id,
            payout_rule_id=None,
            metadata=dict(WORKER_METADATA),
            settings=settings,
            now=processing_now,
            # payout_v2 rows are write-once: input drift never auto-recomputes
            # money in the pipeline; the admin recompute-day tool corrects.
            strict_staleness=False,
        )
    except AppError as exc:
        # Expected non-progression only; raised before any payout write, so the
        # session stays healthy and earlier stages commit with the caller.
        if exc.code != "PAYOUT_RULE_NOT_FOUND":
            raise
        stages.append(
            StageResult(stage="payout", outcome="blocked", reason="no_active_payout_rule")
        )
        if repaired_ledger_ids:
            await _audit_processing_writes(
                session,
                trip=trip,
                stages=stages,
                created_ledger_ids=repaired_ledger_ids,
                repaired_ledger_ids=repaired_ledger_ids,
            )
        return TripProcessingResult(trip_id=trip.id, overall="partial", stages=stages)

    ledger_created = ledger is not None and ledger.id not in prior_ledger_ids
    payout_row_ids = {"payout_calculation_id": str(calculation.id)}
    if ledger is not None:
        payout_row_ids["earnings_ledger_entry_id"] = str(ledger.id)
    stages.append(
        StageResult(
            stage="payout",
            outcome="created" if calculation_created else "reused",
            row_ids=payout_row_ids,
        )
    )

    if calculation_created or ledger_created or repaired_ledger_ids:
        created_ledger_ids = list(repaired_ledger_ids)
        if ledger_created and ledger is not None and ledger.id not in created_ledger_ids:
            created_ledger_ids.append(ledger.id)
        await _audit_processing_writes(
            session,
            trip=trip,
            stages=stages,
            created_ledger_ids=created_ledger_ids,
            repaired_ledger_ids=repaired_ledger_ids,
        )

    return TripProcessingResult(trip_id=trip.id, overall="completed", stages=stages)


async def find_unprocessed_trip_page(
    session: AsyncSession,
    *,
    limit: int,
    settings: Settings,
    after: tuple[datetime, UUID] | None = None,
) -> list[DueTrip]:
    def open_fraud_count(severity: FraudFlagSeverity):
        return (
            select(func.count(FraudFlag.id))
            .where(
                FraudFlag.trip_session_id == TripSession.id,
                FraudFlag.status == FraudFlagStatus.OPEN.value,
                FraudFlag.severity == severity.value,
            )
            .correlate(TripSession)
            .scalar_subquery()
        )

    open_low_count = open_fraud_count(FraudFlagSeverity.LOW)
    open_medium_count = open_fraud_count(FraudFlagSeverity.MEDIUM)
    open_high_count = open_fraud_count(FraudFlagSeverity.HIGH)
    analytics_exists = (
        select(TripAnalytics.id).where(TripAnalytics.trip_session_id == TripSession.id).exists()
    )
    current_analytics_exists = (
        select(TripAnalytics.id)
        .where(
            TripAnalytics.trip_session_id == TripSession.id,
            TripAnalytics.formula_version == settings.route_analytics_formula_version,
        )
        .exists()
    )
    source_formula = ImpressionEstimate.estimate_metadata[
        "source_analytics_formula_version"
    ].as_string()
    source_analytics_fingerprint = ImpressionEstimate.estimate_metadata[
        "source_analytics_fingerprint"
    ].as_string()
    analytics_output_fingerprint = TripAnalytics.analytics_metadata[
        "output_fingerprint"
    ].as_string()
    estimate_low_count = ImpressionEstimate.estimate_metadata["fraud_flag_counts"][
        FraudFlagSeverity.LOW.value
    ].as_integer()
    estimate_medium_count = ImpressionEstimate.estimate_metadata["fraud_flag_counts"][
        FraudFlagSeverity.MEDIUM.value
    ].as_integer()
    estimate_high_count = ImpressionEstimate.estimate_metadata["fraud_flag_counts"][
        FraudFlagSeverity.HIGH.value
    ].as_integer()
    current_estimate_exists = (
        select(ImpressionEstimate.id)
        .join(TripAnalytics, TripAnalytics.id == ImpressionEstimate.trip_analytics_id)
        .where(
            TripAnalytics.trip_session_id == TripSession.id,
            TripAnalytics.formula_version == settings.route_analytics_formula_version,
            ImpressionEstimate.formula_version == settings.impression_formula_version,
            estimate_low_count == open_low_count,
            estimate_medium_count == open_medium_count,
            estimate_high_count == open_high_count,
            or_(
                and_(
                    source_formula == settings.route_analytics_formula_version,
                    source_analytics_fingerprint.is_not(None),
                    analytics_output_fingerprint.is_not(None),
                    source_analytics_fingerprint == analytics_output_fingerprint,
                ),
                and_(
                    source_analytics_fingerprint.is_not(None),
                    analytics_output_fingerprint.is_(None),
                    source_formula == settings.route_analytics_formula_version,
                    ImpressionEstimate.estimated_at >= TripAnalytics.computed_at,
                ),
                and_(
                    source_analytics_fingerprint.is_(None),
                    or_(
                        source_formula.is_(None),
                        source_formula == settings.route_analytics_formula_version,
                    ),
                    ImpressionEstimate.estimated_at >= TripAnalytics.computed_at,
                ),
            ),
        )
        .exists()
    )
    payout_source_analytics_formula = PayoutCalculation.payout_metadata[
        "source_analytics_formula_version"
    ].as_string()
    payout_source_impression_formula = PayoutCalculation.payout_metadata[
        "source_impression_formula_version"
    ].as_string()
    payout_source_analytics_fingerprint = PayoutCalculation.payout_metadata[
        "source_analytics_fingerprint"
    ].as_string()
    payout_source_impression_fingerprint = PayoutCalculation.payout_metadata[
        "source_impression_fingerprint"
    ].as_string()
    estimate_output_fingerprint = ImpressionEstimate.estimate_metadata[
        "output_fingerprint"
    ].as_string()
    payout_low_count = PayoutCalculation.payout_metadata["fraud_flag_counts"][
        FraudFlagSeverity.LOW.value
    ].as_integer()
    payout_medium_count = PayoutCalculation.payout_metadata["fraud_flag_counts"][
        FraudFlagSeverity.MEDIUM.value
    ].as_integer()
    payout_high_count = PayoutCalculation.payout_metadata["fraud_flag_counts"][
        FraudFlagSeverity.HIGH.value
    ].as_integer()
    # Expected payout formula comes from the governing (active) rule row, not
    # the global setting: v1 and v2 campaigns coexist after S1 (D2/D8).
    active_rule_formula = (
        select(CampaignPayoutRule.formula_version)
        .where(
            CampaignPayoutRule.campaign_id == TripSession.campaign_id,
            CampaignPayoutRule.status == CampaignPayoutRuleStatus.ACTIVE.value,
        )
        .order_by(CampaignPayoutRule.created_at.desc(), CampaignPayoutRule.id)
        .limit(1)
        .correlate(TripSession)
        .scalar_subquery()
    )
    any_payout_calculation_exists = (
        select(PayoutCalculation.id)
        .where(PayoutCalculation.trip_session_id == TripSession.id)
        .exists()
    )
    current_payout_exists = (
        select(PayoutCalculation.id)
        .join(TripAnalytics, TripAnalytics.id == PayoutCalculation.trip_analytics_id)
        .join(
            ImpressionEstimate,
            ImpressionEstimate.id == PayoutCalculation.impression_estimate_id,
        )
        .where(
            PayoutCalculation.trip_session_id == TripSession.id,
            PayoutCalculation.formula_version == active_rule_formula,
            TripAnalytics.formula_version == settings.route_analytics_formula_version,
            ImpressionEstimate.formula_version == settings.impression_formula_version,
            payout_low_count == open_low_count,
            payout_medium_count == open_medium_count,
            payout_high_count == open_high_count,
            or_(
                and_(
                    payout_source_analytics_formula
                    == settings.route_analytics_formula_version,
                    payout_source_impression_formula == settings.impression_formula_version,
                    payout_source_analytics_fingerprint == analytics_output_fingerprint,
                    payout_source_impression_fingerprint == estimate_output_fingerprint,
                ),
                and_(
                    analytics_output_fingerprint.is_(None),
                    payout_source_analytics_formula
                    == settings.route_analytics_formula_version,
                    payout_source_impression_formula == settings.impression_formula_version,
                    payout_source_impression_fingerprint == estimate_output_fingerprint,
                    PayoutCalculation.calculated_at >= ImpressionEstimate.estimated_at,
                ),
                and_(
                    payout_source_analytics_fingerprint.is_(None),
                    payout_source_impression_fingerprint.is_(None),
                    or_(
                        payout_source_analytics_formula.is_(None),
                        payout_source_analytics_formula
                        == settings.route_analytics_formula_version,
                    ),
                    or_(
                        payout_source_impression_formula.is_(None),
                        payout_source_impression_formula == settings.impression_formula_version,
                    ),
                    PayoutCalculation.calculated_at >= ImpressionEstimate.estimated_at,
                ),
            ),
        )
        .exists()
    )
    ledger_exists = (
        select(EarningsLedgerEntry.id)
        .where(EarningsLedgerEntry.payout_calculation_id == PayoutCalculation.id)
        .exists()
    )
    trip_payout_entry_exists = (
        select(EarningsLedgerEntry.id)
        .where(
            EarningsLedgerEntry.trip_session_id == TripSession.id,
            EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value,
        )
        .correlate(TripSession)
        .exists()
    )
    # Rule-agnostic repair gap, mirroring exactly what repair will fix: a
    # calculated, payable calculation missing its entry AND no trip_payout
    # entry for the trip at all (the cross-model guard skips otherwise).
    repairable_ledger_gap_exists = and_(
        select(PayoutCalculation.id)
        .where(
            PayoutCalculation.trip_session_id == TripSession.id,
            PayoutCalculation.status == PayoutCalculationStatus.CALCULATED.value,
            PayoutCalculation.final_payout > 0,
            ~ledger_exists,
        )
        .exists(),
        ~trip_payout_entry_exists,
    )
    active_rule_exists = (
        select(CampaignPayoutRule.id)
        .where(
            CampaignPayoutRule.campaign_id == TripSession.campaign_id,
            CampaignPayoutRule.status == CampaignPayoutRuleStatus.ACTIVE.value,
        )
        .exists()
    )
    governing_formula_calculation_exists = (
        select(PayoutCalculation.id)
        .where(
            PayoutCalculation.trip_session_id == TripSession.id,
            PayoutCalculation.formula_version == active_rule_formula,
        )
        .exists()
    )
    statement = select(TripSession.id, TripSession.ended_at).where(
        TripSession.status == TripSessionStatus.SEALED.value,
        TripSession.ended_at.is_not(None),
        or_(
            ~analytics_exists,
            and_(current_analytics_exists, ~current_estimate_exists),
            and_(
                current_analytics_exists,
                current_estimate_exists,
                active_rule_exists,
                or_(
                    # The dispatcher computes fresh only when NO calculation
                    # exists at all (formula-agnostic reuse; payout_v2 is
                    # write-once) - the sweep mirrors that exactly so a
                    # cross-model switch in either direction never re-queues
                    # an already-calculated trip.
                    ~any_payout_calculation_exists,
                    # payout_v1 staleness recompute path: only when the trip's
                    # chain is itself under the governing v1 formula.
                    and_(
                        active_rule_formula != PAYOUT_V2,
                        governing_formula_calculation_exists,
                        ~current_payout_exists,
                    ),
                ),
            ),
            repairable_ledger_gap_exists,
        ),
    )
    if after is not None:
        after_ended_at, after_id = after
        statement = statement.where(
            or_(
                TripSession.ended_at > after_ended_at,
                and_(TripSession.ended_at == after_ended_at, TripSession.id > after_id),
            )
        )
    result = await session.execute(
        statement.order_by(TripSession.ended_at.asc(), TripSession.id.asc()).limit(limit)
    )
    return [DueTrip(id=trip_id, ended_at=ended_at) for trip_id, ended_at in result.all()]


async def find_unprocessed_trips(
    session: AsyncSession,
    *,
    limit: int,
    settings: Settings,
) -> list[UUID]:
    return [
        trip.id
        for trip in await find_unprocessed_trip_page(
            session,
            limit=limit,
            settings=settings,
        )
    ]


async def seal_due_trips(
    session: AsyncSession,
    *,
    settings: Settings,
    now: datetime | None = None,
    limit: int | None = None,
) -> list[UUID]:
    """Force-seal ended trips whose recovery grace has expired (RM3).

    The guaranteed path for incomplete/legacy ends: after
    ``trip_seal_grace_seconds`` the trip seals with reason ``grace_expired``
    even if the client watermark was never satisfied — late data past this
    point goes to quarantine. Each seal is a guarded transition (winner-only),
    so a concurrent late-batch seal or duplicate cron fire cannot double-seal.
    """
    processing_now = now or await database_now(session)
    cutoff = processing_now - timedelta(seconds=settings.trip_seal_grace_seconds)
    result = await session.execute(
        select(TripSession)
        .where(
            TripSession.status == TripSessionStatus.ENDED.value,
            TripSession.ended_at.is_not(None),
            TripSession.ended_at <= cutoff,
        )
        .order_by(TripSession.ended_at.asc(), TripSession.id.asc())
        .limit(limit or settings.worker_sweep_batch_size)
    )
    sealed_ids: list[UUID] = []
    for trip in result.scalars().all():
        if await try_seal_trip(
            session,
            trip,
            reason=TripSealReason.GRACE_EXPIRED,
            now=processing_now,
        ):
            sealed_ids.append(trip.id)
    return sealed_ids

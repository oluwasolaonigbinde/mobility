from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.impression import ImpressionEstimate
from app.models.payout import (
    CampaignPayoutRule,
    CampaignPayoutRuleStatus,
    EarningsLedgerEntry,
    PayoutCalculation,
)
from app.models.trip import TripSession, TripSessionStatus
from app.models.trip_analytics import TripAnalytics
from app.services.audit import create_audit_event
from app.services.impressions import estimate_trip_impressions
from app.services.payouts import calculate_trip_payout
from app.services.trip_analytics import recompute_trip_analytics
from app.services.trips import trip_not_found

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


async def process_ended_trip(
    session: AsyncSession,
    *,
    trip_id: UUID,
    settings: Settings,
) -> TripProcessingResult:
    trip = await session.get(TripSession, trip_id)
    if trip is None:
        raise trip_not_found()
    if trip.status != TripSessionStatus.ENDED.value or trip.ended_at is None:
        return TripProcessingResult(
            trip_id=trip_id,
            overall="blocked",
            stages=[StageResult(stage="trip", outcome="blocked", reason="trip_not_ended")],
        )

    stages: list[StageResult] = []

    analytics = await session.scalar(
        select(TripAnalytics).where(TripAnalytics.trip_session_id == trip.id)
    )
    if analytics is not None:
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
        )
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

    # Any current-formula estimate completes the stage — mirrors the selection payout uses.
    estimate = await session.scalar(
        select(ImpressionEstimate)
        .where(
            ImpressionEstimate.trip_session_id == trip.id,
            ImpressionEstimate.formula_version == settings.impression_formula_version,
        )
        .order_by(ImpressionEstimate.estimated_at.desc(), ImpressionEstimate.id)
        .limit(1)
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
        )
    except AppError as exc:
        # Expected non-progression only; raised before any payout write, so the
        # session stays healthy and earlier stages commit with the caller.
        if exc.code != "PAYOUT_RULE_NOT_FOUND":
            raise
        stages.append(
            StageResult(stage="payout", outcome="blocked", reason="no_active_payout_rule")
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

    if calculation_created or ledger_created:
        created_row_ids = {
            key: value
            for stage in stages
            if stage.outcome == "created"
            for key, value in stage.row_ids.items()
            if key.endswith("_id")
        }
        if ledger_created and ledger is not None:
            created_row_ids["earnings_ledger_entry_id"] = str(ledger.id)
        await create_audit_event(
            session,
            actor_user_id=None,
            action=AUDIT_ACTION_TRIP_PROCESSING,
            entity_type="trip_session",
            entity_id=str(trip.id),
            metadata={
                "stages": {stage.stage: stage.outcome for stage in stages},
                "created_row_ids": created_row_ids,
            },
        )

    return TripProcessingResult(trip_id=trip.id, overall="completed", stages=stages)


async def find_unprocessed_trips(
    session: AsyncSession,
    *,
    limit: int,
    settings: Settings,
) -> list[UUID]:
    analytics_exists = (
        select(TripAnalytics.id).where(TripAnalytics.trip_session_id == TripSession.id).exists()
    )
    estimate_exists = (
        select(ImpressionEstimate.id)
        .where(
            ImpressionEstimate.trip_session_id == TripSession.id,
            ImpressionEstimate.formula_version == settings.impression_formula_version,
        )
        .exists()
    )
    payout_exists = (
        select(PayoutCalculation.id)
        .where(
            PayoutCalculation.trip_session_id == TripSession.id,
            PayoutCalculation.formula_version == settings.payout_formula_version,
        )
        .exists()
    )
    active_rule_exists = (
        select(CampaignPayoutRule.id)
        .where(
            CampaignPayoutRule.campaign_id == TripSession.campaign_id,
            CampaignPayoutRule.status == CampaignPayoutRuleStatus.ACTIVE.value,
        )
        .exists()
    )
    result = await session.execute(
        select(TripSession.id)
        .where(
            TripSession.status == TripSessionStatus.ENDED.value,
            TripSession.ended_at.is_not(None),
            or_(
                ~analytics_exists,
                ~estimate_exists,
                and_(~payout_exists, active_rule_exists),
            ),
        )
        .order_by(TripSession.ended_at.asc(), TripSession.id.asc())
        .limit(limit)
    )
    return list(result.scalars().all())

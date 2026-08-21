"""Maker-checker payout correction orders (MNY-06C, Q22, PR7/PR12).

The PR6 recompute core (services/payouts.py) is the single computation
engine; this module wraps it in the correction-order authority: a named
adjuster projects a campaign/Lagos-day delta (dry-run, no writes), a
DIFFERENT admin approves, and execution re-verifies the projection
fingerprint before running the same core in execution mode. All state
transitions are winner-only guarded UPDATEs (order row FOR UPDATE); an
executed order replays its recorded execution_result and never recomputes.
Stale is terminal: input drift at approve or execute marks the order stale
and a fresh projection (a new order) is required.

Actor policy (Q22): only the creator may submit their own draft; approval
requires a different admin (service check + DB CHECK); execution may be
performed by any
admin including the creator, because independent approval has already
happened — Q22 forbids only creator-approves-own.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    PayoutCorrectionOrder,
    PayoutCorrectionOrderStatus,
)
from app.models.trip import TripSession, TripSessionStatus
from app.services.audit import create_audit_event
from app.services.payouts import (
    PAYOUT_V2,
    DayComputation,
    RecomputeDayOutcome,
    compute_payout_day_targets,
    correction_release_at_required,
    get_campaign,
    lagos_day_utc_range,
    quantize_2,
    utc_now,
    write_day_differentials,
)
from app.services.provenance import stable_source_fingerprint


def correction_order_not_found() -> AppError:
    return AppError(
        "CORRECTION_ORDER_NOT_FOUND",
        "Payout correction order was not found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def correction_order_invalid_state(current: str, action: str) -> AppError:
    return AppError(
        "CORRECTION_ORDER_INVALID_STATE",
        f"Cannot {action} a correction order in status '{current}'",
        status_code=status.HTTP_409_CONFLICT,
        details={"status": current, "action": action},
    )


def correction_order_self_approval() -> AppError:
    return AppError(
        "CORRECTION_ORDER_SELF_APPROVAL",
        "A correction order must be approved by a different admin than its"
        " creator (Q22 maker-checker)",
        status_code=status.HTTP_403_FORBIDDEN,
    )


def correction_order_creator_only() -> AppError:
    return AppError(
        "CORRECTION_ORDER_CREATOR_ONLY",
        "Only the correction order's creator may submit their own draft",
        status_code=status.HTTP_403_FORBIDDEN,
    )


def correction_order_stale() -> AppError:
    return AppError(
        "CORRECTION_ORDER_STALE",
        "The projection inputs changed since this order was projected; the"
        " order is now stale — project a new correction order",
        status_code=status.HTTP_409_CONFLICT,
    )


@dataclass(frozen=True)
class CampaignDayProjection:
    computations: list[DayComputation]
    projected_delta: dict
    fingerprint: str


async def _affected_driver_ids(
    session: AsyncSession, campaign_id: UUID, lagos_day: date
) -> list[UUID]:
    """Drivers whose ended/sealed trips overlap the campaign's Lagos day.

    Sorted ascending so every projection/execution acquires the per-day
    advisory locks in one deterministic order (no cross-order deadlocks)."""
    day_start, day_end = lagos_day_utc_range(lagos_day)
    rows = await session.execute(
        select(TripSession.driver_profile_id)
        .distinct()
        .where(
            TripSession.campaign_id == campaign_id,
            TripSession.status.in_(
                [TripSessionStatus.ENDED.value, TripSessionStatus.SEALED.value]
            ),
            TripSession.ended_at.is_not(None),
            TripSession.started_at < day_end,
            TripSession.ended_at >= day_start,
        )
        .order_by(TripSession.driver_profile_id)
    )
    return [row[0] for row in rows.all()]


def _projection_payload(computations: list[DayComputation]) -> dict:
    """Owner-facing projected delta: per-trip old vs new amounts plus day
    totals. Decimal amounts are serialized as strings (§6.4.4)."""
    trips = []
    previous_total = Decimal("0.00")
    target_total = Decimal("0.00")
    adjustment_count = 0
    reversal_count = 0
    currencies: set[str] = set()
    for computation in computations:
        for target in computation.trips:
            trips.append(
                {
                    "trip_session_id": str(target.trip_session_id),
                    "driver_profile_id": str(computation.driver_profile_id),
                    "formula_version": target.formula_version,
                    "currency": target.currency,
                    "previous_posted_amount": str(target.previous_posted_amount),
                    "target_amount": str(target.target_amount),
                    "delta_amount": str(target.delta_amount),
                    "eligible_seconds": target.eligible_seconds,
                    "payable_seconds": target.payable_seconds,
                    "voided": target.voided,
                }
            )
            previous_total += target.previous_posted_amount
            target_total += target.target_amount
            if target.delta_amount > 0:
                adjustment_count += 1
            elif target.delta_amount < 0:
                reversal_count += 1
            currencies.add(target.currency)
    return {
        "currencies": sorted(currencies),
        "trips": trips,
        "day_totals": {
            "previous_posted_amount": str(quantize_2(previous_total)),
            "target_amount": str(quantize_2(target_total)),
            "delta_amount": str(quantize_2(target_total - previous_total)),
            "projected_adjustment_count": adjustment_count,
            "projected_reversal_count": reversal_count,
            "trip_count": len(trips),
        },
    }


async def _projection_fingerprint(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    lagos_day: date,
    computations: list[DayComputation],
) -> str:
    """PR12 inputs hash: per affected trip its stored calculation
    inputs_fingerprint, its CURRENT ping-set fingerprint, and its governing
    rule-row or frozen-binding values (with resolved eligibility params); the
    campaign window and zone-state fingerprint the classifier would use; cap
    parameters and formula versions; and the day's posted non-voided ledger
    entries (id, type, amount, currency). Any drift in these at approve or
    execute time marks the order stale."""
    trip_inputs = []
    trip_ids: list[UUID] = []
    for computation in computations:
        for target in computation.trips:
            trip_ids.append(target.trip_session_id)
            trip_inputs.append(
                {
                    "trip_session_id": target.trip_session_id,
                    "driver_profile_id": computation.driver_profile_id,
                    "formula_version": target.formula_version,
                    "stored_inputs_fingerprint": target.stored_inputs_fingerprint,
                    "current_ping_fingerprint": target.current_ping_fingerprint,
                    "governing_values": target.governing_values,
                    "cap_seconds": target.cap_seconds,
                    "voided": target.voided,
                }
            )
    ledger_rows: list[dict] = []
    if trip_ids:
        entries = await session.execute(
            select(EarningsLedgerEntry)
            .where(
                EarningsLedgerEntry.trip_session_id.in_(trip_ids),
                EarningsLedgerEntry.status != EarningsLedgerEntryStatus.VOIDED.value,
            )
            .order_by(EarningsLedgerEntry.id)
        )
        ledger_rows = [
            {
                "id": entry.id,
                "entry_type": entry.entry_type,
                "amount": entry.amount,
                "currency": entry.currency,
            }
            for entry in entries.scalars().all()
        ]
    first = computations[0] if computations else None
    return stable_source_fingerprint(
        {
            "campaign_id": campaign_id,
            "lagos_day": lagos_day.isoformat(),
            "trips": trip_inputs,
            "ledger_entries": ledger_rows,
            # Live zones affect payout_v2 classification. payout_v3 consumes
            # only the acceptance-time geometry snapshot, already carried in
            # governing_values/current_ping_fingerprint, so unrelated live
            # zone edits must not stale a v3-only order.
            "zone_state_fingerprint": (
                first.zone_state_fingerprint
                if any(
                    target.formula_version == PAYOUT_V2
                    for computation in computations
                    for target in computation.trips
                )
                else None
            ),
            "window_start_at": (
                first.window_start_at
                if first is not None
                and any(
                    target.formula_version == PAYOUT_V2
                    for computation in computations
                    for target in computation.trips
                )
                else None
            ),
            "window_end_at": (
                first.window_end_at
                if first is not None
                and any(
                    target.formula_version == PAYOUT_V2
                    for computation in computations
                    for target in computation.trips
                )
                else None
            ),
        }
    )


async def project_campaign_day(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    lagos_day: date,
    settings: Settings,
) -> CampaignDayProjection:
    """The PR6 core in dry-run across every affected driver of the day.

    Acquires the same per-driver/day advisory locks as the pipeline (sorted
    driver order) so the projection is a consistent snapshot; writes nothing.
    """
    await get_campaign(session, campaign_id)
    driver_ids = await _affected_driver_ids(session, campaign_id, lagos_day)
    computations = [
        await compute_payout_day_targets(
            session,
            campaign_id=campaign_id,
            driver_profile_id=driver_id,
            lagos_date=lagos_day,
            settings=settings,
        )
        for driver_id in driver_ids
    ]
    fingerprint = await _projection_fingerprint(
        session,
        campaign_id=campaign_id,
        lagos_day=lagos_day,
        computations=computations,
    )
    return CampaignDayProjection(
        computations=computations,
        projected_delta=_projection_payload(computations),
        fingerprint=fingerprint,
    )


async def create_correction_order(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    lagos_day: date,
    reason: str,
    created_by_user_id: UUID,
    settings: Settings,
) -> PayoutCorrectionOrder:
    """Project the campaign day and persist it as a draft order (C1: the
    named adjuster's proposal, value-complete before anyone approves)."""
    projection = await project_campaign_day(
        session, campaign_id=campaign_id, lagos_day=lagos_day, settings=settings
    )
    order = PayoutCorrectionOrder(
        campaign_id=campaign_id,
        lagos_day=lagos_day,
        status=PayoutCorrectionOrderStatus.DRAFT.value,
        created_by_user_id=created_by_user_id,
        reason=reason,
        projected_delta=projection.projected_delta,
        projection_fingerprint=projection.fingerprint,
        projected_at=utc_now(),
    )
    session.add(order)
    await session.flush()
    await session.refresh(order)
    return order


async def get_correction_order(
    session: AsyncSession,
    order_id: UUID,
    *,
    for_update: bool = False,
) -> PayoutCorrectionOrder:
    query = select(PayoutCorrectionOrder).where(PayoutCorrectionOrder.id == order_id)
    if for_update:
        query = query.with_for_update()
    order = await session.scalar(query)
    if order is None:
        raise correction_order_not_found()
    return order


async def list_correction_orders(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    campaign_id: UUID | None = None,
    order_status: PayoutCorrectionOrderStatus | None = None,
) -> tuple[list[PayoutCorrectionOrder], int]:
    conditions = []
    if campaign_id is not None:
        conditions.append(PayoutCorrectionOrder.campaign_id == campaign_id)
    if order_status is not None:
        conditions.append(PayoutCorrectionOrder.status == order_status.value)
    total = await session.scalar(
        select(func.count()).select_from(PayoutCorrectionOrder).where(*conditions)
    )
    result = await session.execute(
        select(PayoutCorrectionOrder)
        .where(*conditions)
        .order_by(
            PayoutCorrectionOrder.created_at.desc(), PayoutCorrectionOrder.id.desc()
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def submit_correction_order(
    session: AsyncSession,
    *,
    order_id: UUID,
    actor_user_id: UUID,
) -> PayoutCorrectionOrder:
    order = await get_correction_order(session, order_id, for_update=True)
    if order.status != PayoutCorrectionOrderStatus.DRAFT.value:
        raise correction_order_invalid_state(order.status, "submit")
    if actor_user_id != order.created_by_user_id:
        # "Creator submits own draft": the proposal stays the named
        # adjuster's until they put it forward for approval.
        raise correction_order_creator_only()
    order.status = PayoutCorrectionOrderStatus.PENDING_APPROVAL.value
    await session.flush()
    return order


async def _mark_stale_and_raise(
    session: AsyncSession,
    order: PayoutCorrectionOrder,
    *,
    actor_user_id: UUID,
    action: str,
    current_fingerprint: str,
) -> None:
    """Persist the stale transition (with its own audit event) even though the
    caller's request fails with 409: the API error handler rolls the request
    transaction back, so the stale status must be committed here first."""
    previous_status = order.status
    order.status = PayoutCorrectionOrderStatus.STALE.value
    order.decided_at = utc_now()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.payout_correction_order.stale",
        entity_type="payout_correction_order",
        entity_id=str(order.id),
        metadata={
            "campaign_id": str(order.campaign_id),
            "lagos_day": order.lagos_day.isoformat(),
            "reason": order.reason,
            "created_by_user_id": str(order.created_by_user_id),
            "detected_during": action,
            "status_before": previous_status,
            "status_after": order.status,
            "projection_fingerprint": order.projection_fingerprint,
            "current_fingerprint": current_fingerprint,
        },
    )
    await session.commit()
    raise correction_order_stale()


async def approve_correction_order(
    session: AsyncSession,
    *,
    order_id: UUID,
    actor_user_id: UUID,
    settings: Settings,
) -> PayoutCorrectionOrder:
    order = await get_correction_order(session, order_id, for_update=True)
    if order.status != PayoutCorrectionOrderStatus.PENDING_APPROVAL.value:
        raise correction_order_invalid_state(order.status, "approve")
    if actor_user_id == order.created_by_user_id:
        # Service-level maker-checker (C1); the DB CHECK is the backstop.
        raise correction_order_self_approval()
    projection = await project_campaign_day(
        session,
        campaign_id=order.campaign_id,
        lagos_day=order.lagos_day,
        settings=settings,
    )
    if projection.fingerprint != order.projection_fingerprint:
        await _mark_stale_and_raise(
            session,
            order,
            actor_user_id=actor_user_id,
            action="approve",
            current_fingerprint=projection.fingerprint,
        )
    order.status = PayoutCorrectionOrderStatus.APPROVED.value
    order.approved_by_user_id = actor_user_id
    order.decided_at = utc_now()
    await session.flush()
    return order


async def reject_correction_order(
    session: AsyncSession,
    *,
    order_id: UUID,
    actor_user_id: UUID,
) -> PayoutCorrectionOrder:
    del actor_user_id  # the rejecting actor is recorded in the audit event
    order = await get_correction_order(session, order_id, for_update=True)
    if order.status != PayoutCorrectionOrderStatus.PENDING_APPROVAL.value:
        raise correction_order_invalid_state(order.status, "reject")
    order.status = PayoutCorrectionOrderStatus.REJECTED.value
    order.decided_at = utc_now()
    await session.flush()
    return order


def _execution_result_payload(
    outcomes: list[RecomputeDayOutcome],
    *,
    executed_at: datetime,
    executed_by_user_id: UUID,
    release_at: datetime | None,
) -> dict:
    drivers = []
    adjustment_count = 0
    reversal_count = 0
    for outcome in outcomes:
        adjustment_count += outcome.adjustment_count
        reversal_count += outcome.reversal_count
        drivers.append(
            {
                "driver_profile_id": str(outcome.driver_profile_id),
                "adjustment_count": outcome.adjustment_count,
                "reversal_count": outcome.reversal_count,
                "trips": [
                    {
                        "trip_session_id": str(trip.trip_session_id),
                        "payout_calculation_id": (
                            str(trip.payout_calculation_id)
                            if trip.payout_calculation_id is not None
                            else None
                        ),
                        "previous_posted_amount": str(trip.previous_posted_amount),
                        "target_amount": str(trip.target_amount),
                        "delta_amount": str(trip.delta_amount),
                        "entry_id": (
                            str(trip.entry.id) if trip.entry is not None else None
                        ),
                        "entry_type": (
                            trip.entry.entry_type if trip.entry is not None else None
                        ),
                        "entry_status": (
                            trip.entry.status if trip.entry is not None else None
                        ),
                        "voided": trip.voided,
                    }
                    for trip in outcome.trips
                ],
            }
        )
    return {
        "executed_at": executed_at.isoformat(),
        "executed_by_user_id": str(executed_by_user_id),
        "release_at": release_at.isoformat() if release_at is not None else None,
        "adjustment_count": adjustment_count,
        "reversal_count": reversal_count,
        "drivers": drivers,
    }


async def execute_correction_order(
    session: AsyncSession,
    *,
    order_id: UUID,
    actor_user_id: UUID,
    release_at: datetime | None,
    request_metadata: dict,
    settings: Settings,
) -> tuple[PayoutCorrectionOrder, bool]:
    """Run the approved order exactly once (C3).

    Returns (order, executed_now). A concurrent or repeated execute
    serializes on the row lock, observes status 'executed', and returns the
    recorded execution_result without recomputing anything. The status flip,
    execution_result, and every ledger write share one transaction — a crash
    before commit leaves the order approved and no money written."""
    order = await get_correction_order(session, order_id, for_update=True)
    if order.status == PayoutCorrectionOrderStatus.EXECUTED.value:
        return order, False
    if order.status != PayoutCorrectionOrderStatus.APPROVED.value:
        raise correction_order_invalid_state(order.status, "execute")
    projection = await project_campaign_day(
        session,
        campaign_id=order.campaign_id,
        lagos_day=order.lagos_day,
        settings=settings,
    )
    if projection.fingerprint != order.projection_fingerprint:
        await _mark_stale_and_raise(
            session,
            order,
            actor_user_id=actor_user_id,
            action="execute",
            current_fingerprint=projection.fingerprint,
        )
    has_positive_delta = any(
        target.delta_amount > 0
        for computation in projection.computations
        for target in computation.trips
    )
    if has_positive_delta and release_at is None:
        raise correction_release_at_required()

    executed_at = utc_now()
    outcomes = [
        await write_day_differentials(
            session,
            computation=computation,
            request_metadata=request_metadata,
            recompute_at=executed_at,
            correction_order_id=order.id,
            release_at=release_at,
        )
        for computation in projection.computations
    ]
    order.execution_result = _execution_result_payload(
        outcomes,
        executed_at=executed_at,
        executed_by_user_id=actor_user_id,
        release_at=release_at,
    )
    order.status = PayoutCorrectionOrderStatus.EXECUTED.value
    order.executed_by_user_id = actor_user_id
    order.executed_at = executed_at
    await session.flush()
    return order, True

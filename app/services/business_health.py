"""Read-only operational predicates; Finance owns every resulting resolution."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.gps_health import gps_window
from app.models.billing import PaymentGatewayEvent, PaymentGatewayProcessingAttempt
from app.models.disbursement import (
    PayoutAutomaticAlert,
    PayoutAutomaticAlertKind,
    PayoutAutomaticControl,
    PayoutBatchLine,
    PayoutProviderEvent,
    PayoutProviderEventProcessingAttempt,
    PayoutSubmissionIntent,
)
from app.models.notification import Notification
from app.models.trip import LocationPingBatch, TripSession
from app.services.automatic_payouts import _key, raise_alert
from app.services.data_lifecycle import check_partition_coverage

CHECKS = frozenset(
    {
        "stuck_payouts",
        "unprocessed_webhooks",
        "paused_payouts",
        "gps_rejections",
        "gps_telemetry_unavailable",
        "stale_trips",
        "partition_coverage",
        "email_failures",
    }
)
COUNT_LIMIT = 1000


async def _count(session: AsyncSession, query: Any) -> int:
    # Only a bounded count is needed to route investigation; never load payloads.
    return int(
        await session.scalar(select(func.count()).select_from(query.limit(COUNT_LIMIT).subquery()))
        or 0
    )


async def stuck_payouts(session: AsyncSession, now: datetime) -> int:
    latest_intent = (
        select(func.max(PayoutSubmissionIntent.updated_at))
        .where(PayoutSubmissionIntent.payout_batch_line_id == PayoutBatchLine.id)
        .scalar_subquery()
    )
    lines = select(PayoutBatchLine.id).where(
        PayoutBatchLine.status == "submitted",
        func.greatest(
            PayoutBatchLine.created_at, PayoutBatchLine.last_provider_evidence_at, latest_intent
        )
        < now - timedelta(hours=1),
    )
    # Pending/claimed/query-only intents are the durable submitting state.
    intents = select(PayoutSubmissionIntent.id).where(
        PayoutSubmissionIntent.state.in_(("pending", "claimed", "query_only")),
        PayoutSubmissionIntent.updated_at < now - timedelta(hours=1),
    )
    return min(COUNT_LIMIT, await _count(session, lines) + await _count(session, intents))


async def unprocessed_webhooks(session: AsyncSession, now: datetime) -> int:
    cutoff = now - timedelta(minutes=15)
    payment_done = exists().where(
        PaymentGatewayProcessingAttempt.gateway_event_id == PaymentGatewayEvent.id,
        PaymentGatewayProcessingAttempt.outcome.in_(
            ("confirmed", "confirmed_unallocated", "ignored_failed")
        ),
    )
    payout_done = exists().where(
        PayoutProviderEventProcessingAttempt.provider_event_id == PayoutProviderEvent.id,
        PayoutProviderEventProcessingAttempt.outcome == "processed",
    )
    payments = await _count(
        session,
        select(PaymentGatewayEvent.id).where(
            PaymentGatewayEvent.received_at < cutoff, ~payment_done
        ),
    )
    payouts = await _count(
        session,
        select(PayoutProviderEvent.id).where(
            PayoutProviderEvent.received_at < cutoff, ~payout_done
        ),
    )
    return min(COUNT_LIMIT, payments + payouts)


async def stale_trips(session: AsyncSession, now: datetime, settings: Settings) -> int:
    last_ping = (
        select(func.max(LocationPingBatch.received_at))
        .where(
            LocationPingBatch.trip_session_id == TripSession.id,
            LocationPingBatch.pings_accepted > 0,
        )
        .scalar_subquery()
    )
    return await _count(
        session,
        select(TripSession.id).where(
            or_(
                and_(
                    TripSession.status == "active",
                    func.greatest(TripSession.started_at, last_ping) < now - timedelta(minutes=30),
                ),
                and_(
                    TripSession.status == "ended",
                    TripSession.sealed_at.is_(None),
                    TripSession.evidence_adjudicated_at.is_(None),
                    TripSession.ended_at
                    < now - timedelta(seconds=settings.trip_seal_grace_seconds),
                ),
            )
        ),
    )


def _gps_failure_key(now: datetime) -> str:
    return _key(
        "cardvert-automatic-payout-alert-v1",
        PayoutAutomaticAlertKind.BUSINESS_HEALTH.value,
        "gps_telemetry_unavailable",
        now.astimezone(UTC).date().isoformat(),
    )


async def record_gps_counter_failure(session: AsyncSession, *, now: datetime) -> None:
    await publish_health_alerts(session, now=now, counts={"gps_telemetry_unavailable": 1})
    alert = await session.scalar(
        select(PayoutAutomaticAlert)
        .where(PayoutAutomaticAlert.dedupe_key == _gps_failure_key(now))
        .with_for_update()
    )
    assert alert is not None
    # The failed minute must leave the 15-complete-minute window before any
    # readable counters can prove health. Resolution never clears this signal.
    until = now.astimezone(UTC).replace(second=0, microsecond=0) + timedelta(minutes=16)
    previous = alert.detail.get("counter_incomplete_until")
    if previous is None or datetime.fromisoformat(previous) < until:
        alert.detail = {**alert.detail, "counter_incomplete_until": until.isoformat()}
    await session.flush()


async def _gps_counter_incomplete(session: AsyncSession, now: datetime) -> bool:
    details = await session.scalars(
        select(PayoutAutomaticAlert.detail).where(
            PayoutAutomaticAlert.dedupe_key.in_(
                (_gps_failure_key(now), _gps_failure_key(now - timedelta(days=1)))
            )
        )
    )
    return any(
        datetime.fromisoformat(detail["counter_incomplete_until"]) > now
        for detail in details
        if "counter_incomplete_until" in detail
    )


async def health_counts(
    session: AsyncSession, *, now: datetime, settings: Settings, redis: Any
) -> dict[str, int]:
    covered, _ = await check_partition_coverage(session, now=now)
    gps = None if await _gps_counter_incomplete(session, now) else await gps_window(redis, now=now)
    counts = {
        "stuck_payouts": await stuck_payouts(session, now),
        "unprocessed_webhooks": await unprocessed_webhooks(session, now),
        "paused_payouts": await _count(
            session,
            select(PayoutAutomaticControl.id).where(
                PayoutAutomaticControl.paused.is_(True),
                PayoutAutomaticControl.changed_at < now - timedelta(days=1),
            ),
        ),
        "stale_trips": await stale_trips(session, now, settings),
        "partition_coverage": int(not covered),
        "email_failures": await _count(
            session,
            select(Notification.id).where(
                Notification.channel == "transactional_email",
                or_(
                    and_(
                        Notification.status == "failed",
                        Notification.failed_at >= now - timedelta(days=1),
                        Notification.failed_at <= now,
                    ),
                    and_(
                        Notification.status == "pending",
                        Notification.created_at < now - timedelta(minutes=15),
                    ),
                ),
            ),
        ),
    }
    if gps is None:
        counts["gps_telemetry_unavailable"] = 1
    else:
        attempts, rejected = gps
        counts["gps_rejections"] = rejected if attempts >= 20 and rejected * 4 >= attempts else 0
    return counts


async def publish_health_alerts(
    session: AsyncSession, *, now: datetime, counts: dict[str, int]
) -> int:
    created = 0
    for check, count in counts.items():
        if check not in CHECKS or type(count) is not int or count < 0:
            raise ValueError("Invalid business-health result")
        if count:
            alert = await raise_alert(
                session,
                kind=PayoutAutomaticAlertKind.BUSINESS_HEALTH,
                dedupe=(check, now.astimezone(UTC).date().isoformat()),
                detail={"check": check, "count": count},
            )
            created += int(alert is not None)
    return created

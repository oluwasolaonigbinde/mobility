import logging
import time
from typing import Any

from app.core.observability import capture_exception
from app.services.earnings_release import (
    escalate_fraud_flag_if_due,
    find_due_fraud_flag_ids,
    find_pending_release_trip_ids,
    release_pending_earnings_for_trip,
)

logger = logging.getLogger(__name__)


async def sweep_earnings_release_reviews(ctx: dict[str, Any]) -> dict[str, int]:
    """Release eligible money and escalate overdue reviews from DB facts."""
    settings = ctx["settings"]
    sessionmaker = ctx["sessionmaker"]
    started = time.monotonic()

    trip_ids = []
    after_trip_id = None
    async with sessionmaker() as session:
        while True:
            page = await find_pending_release_trip_ids(
                session,
                limit=settings.worker_sweep_batch_size,
                after=after_trip_id,
            )
            trip_ids.extend(page)
            if len(page) < settings.worker_sweep_batch_size:
                break
            after_trip_id = page[-1]
        flag_ids = await find_due_fraud_flag_ids(
            session,
            review_sla_days=settings.fraud_review_sla_days,
            limit=settings.worker_sweep_batch_size,
        )

    released_entries = 0
    release_failed = 0
    for trip_id in trip_ids:
        async with sessionmaker() as session:
            try:
                result = await release_pending_earnings_for_trip(
                    session,
                    trip_id=trip_id,
                    settings=settings,
                )
                await session.commit()
            except Exception as exc:
                await session.rollback()
                release_failed += 1
                logger.exception(
                    "job=sweep_earnings_release_reviews phase=release trip_id=%s "
                    "outcome=error error_class=%s",
                    trip_id,
                    type(exc).__name__,
                )
                capture_exception(exc)
                continue
        released_entries += len(result.released_entry_ids)

    escalated_flags = 0
    escalation_failed = 0
    for flag_id in flag_ids:
        async with sessionmaker() as session:
            try:
                changed = await escalate_fraud_flag_if_due(
                    session,
                    flag_id=flag_id,
                    review_sla_days=settings.fraud_review_sla_days,
                )
                await session.commit()
            except Exception as exc:
                await session.rollback()
                escalation_failed += 1
                logger.exception(
                    "job=sweep_earnings_release_reviews phase=escalation flag_id=%s "
                    "outcome=error error_class=%s",
                    flag_id,
                    type(exc).__name__,
                )
                capture_exception(exc)
                continue
        escalated_flags += int(changed)

    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "job=sweep_earnings_release_reviews release_candidates=%d released_entries=%d "
        "release_failed=%d escalation_candidates=%d escalated_flags=%d "
        "escalation_failed=%d duration_ms=%d",
        len(trip_ids),
        released_entries,
        release_failed,
        len(flag_ids),
        escalated_flags,
        escalation_failed,
        duration_ms,
    )
    return {
        "release_candidates": len(trip_ids),
        "released_entries": released_entries,
        "release_failed": release_failed,
        "escalation_candidates": len(flag_ids),
        "escalated_flags": escalated_flags,
        "escalation_failed": escalation_failed,
        "duration_ms": duration_ms,
    }

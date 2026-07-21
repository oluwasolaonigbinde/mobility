import logging
import time
from typing import Any
from uuid import UUID

from arq.worker import Retry
from sqlalchemy.exc import IntegrityError

from app.core.observability import capture_exception
from app.services.trip_processing import find_unprocessed_trips, process_ended_trip

logger = logging.getLogger(__name__)


async def process_trip(ctx: dict[str, Any], trip_id: str) -> dict[str, Any]:
    parsed_trip_id = UUID(trip_id)
    settings = ctx["settings"]
    sessionmaker = ctx["sessionmaker"]
    started = time.monotonic()
    async with sessionmaker() as session:
        try:
            result = await process_ended_trip(
                session,
                trip_id=parsed_trip_id,
                settings=settings,
            )
            await session.commit()
        except IntegrityError:
            # Lost a first-write race; committed rows are reused on retry (D2).
            await session.rollback()
            logger.warning(
                "job=process_trip trip_id=%s outcome=lost_write_race retry_defer_s=5",
                parsed_trip_id,
            )
            raise Retry(defer=5) from None
        except Exception as exc:
            await session.rollback()
            logger.error(
                "job=process_trip trip_id=%s outcome=error error_class=%s",
                parsed_trip_id,
                type(exc).__name__,
            )
            # Sentry capture for one-off job failures relies on sentry-sdk's
            # Arq/logging integrations when a DSN is configured.
            raise
    duration_ms = int((time.monotonic() - started) * 1000)
    stages = {stage.stage: stage.outcome for stage in result.stages}
    logger.info(
        "job=process_trip trip_id=%s overall=%s stages=%s duration_ms=%d",
        parsed_trip_id,
        result.overall,
        stages,
        duration_ms,
    )
    return {
        "trip_id": str(parsed_trip_id),
        "overall": result.overall,
        "stages": stages,
        "duration_ms": duration_ms,
    }


async def process_unprocessed_trips(ctx: dict[str, Any]) -> dict[str, Any]:
    settings = ctx["settings"]
    sessionmaker = ctx["sessionmaker"]
    started = time.monotonic()
    async with sessionmaker() as session:
        due_trip_ids = await find_unprocessed_trips(
            session,
            limit=settings.worker_sweep_batch_size,
            settings=settings,
        )
    processed = partial = failed = skipped = 0
    # Fresh session per trip: one trip's failure must never poison another's run (D3).
    for due_trip_id in due_trip_ids:
        async with sessionmaker() as session:
            try:
                result = await process_ended_trip(
                    session,
                    trip_id=due_trip_id,
                    settings=settings,
                )
                await session.commit()
            except IntegrityError:
                await session.rollback()
                skipped += 1
                logger.warning(
                    "job=process_unprocessed_trips trip_id=%s outcome=lost_race_skipped",
                    due_trip_id,
                )
                continue
            except Exception as exc:
                await session.rollback()
                failed += 1
                logger.error(
                    "job=process_unprocessed_trips trip_id=%s outcome=error error_class=%s",
                    due_trip_id,
                    type(exc).__name__,
                )
                capture_exception(exc)
                continue
        processed += 1
        if result.overall == "partial":
            partial += 1
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "job=process_unprocessed_trips selected=%d processed=%d partial=%d failed=%d "
        "skipped=%d duration_ms=%d",
        len(due_trip_ids),
        processed,
        partial,
        failed,
        skipped,
        duration_ms,
    )
    return {
        "selected": len(due_trip_ids),
        "processed": processed,
        "partial": partial,
        "failed": failed,
        "skipped": skipped,
        "duration_ms": duration_ms,
    }

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.observability import capture_exception
from app.db.integrity import integrity_constraint_name
from app.services.trip_processing import (
    find_unprocessed_trip_page,
    process_ended_trip,
    seal_due_trips,
)

logger = logging.getLogger(__name__)
SWEEP_CURSOR_KEY = "worker:trip-processing:sweep-cursor:v1"
SWEEP_CURSOR_CONTEXT_KEY = "_trip_processing_sweep_cursor"


def _encode_cursor(cursor: tuple[datetime, UUID]) -> str:
    ended_at, trip_id = cursor
    return json.dumps({"ended_at": ended_at.isoformat(), "trip_id": str(trip_id)})


def _decode_cursor(raw: bytes | str | None) -> tuple[datetime, UUID] | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    payload = json.loads(raw)
    ended_at = datetime.fromisoformat(payload["ended_at"])
    if ended_at.tzinfo is None:
        ended_at = ended_at.replace(tzinfo=UTC)
    return ended_at, UUID(payload["trip_id"])


async def _load_sweep_cursor(ctx: dict[str, Any]) -> tuple[datetime, UUID] | None:
    redis = ctx.get("redis")
    if redis is None:
        return _decode_cursor(ctx.get(SWEEP_CURSOR_CONTEXT_KEY))
    try:
        return _decode_cursor(await redis.get(SWEEP_CURSOR_KEY))
    except Exception as exc:
        logger.exception("job=process_unprocessed_trips event=cursor_load_failed")
        capture_exception(exc)
        return None


async def _store_sweep_cursor(
    ctx: dict[str, Any],
    cursor: tuple[datetime, UUID] | None,
) -> None:
    redis = ctx.get("redis")
    if redis is None:
        if cursor is None:
            ctx.pop(SWEEP_CURSOR_CONTEXT_KEY, None)
        else:
            ctx[SWEEP_CURSOR_CONTEXT_KEY] = _encode_cursor(cursor)
        return
    try:
        if cursor is None:
            await redis.delete(SWEEP_CURSOR_KEY)
        else:
            await redis.set(SWEEP_CURSOR_KEY, _encode_cursor(cursor))
    except Exception as exc:
        logger.exception("job=process_unprocessed_trips event=cursor_store_failed")
        capture_exception(exc)


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
        except IntegrityError as exc:
            await session.rollback()
            logger.exception(
                "job=process_trip trip_id=%s outcome=error error_class=%s constraint=%s",
                parsed_trip_id,
                type(exc).__name__,
                integrity_constraint_name(exc) or "unknown",
            )
            capture_exception(exc)
            raise
        except Exception as exc:
            await session.rollback()
            logger.exception(
                "job=process_trip trip_id=%s outcome=error error_class=%s",
                parsed_trip_id,
                type(exc).__name__,
            )
            capture_exception(exc)
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
    processed = partial = failed = skipped = 0
    selected = 0
    cursor = await _load_sweep_cursor(ctx)
    async with sessionmaker() as session:
        due_trips = await find_unprocessed_trip_page(
            session,
            limit=settings.worker_sweep_batch_size,
            settings=settings,
            after=cursor,
        )
    selected = len(due_trips)
    # Fresh session per trip: one trip's failure must never poison another's run (D3).
    for due_trip in due_trips:
        async with sessionmaker() as session:
            try:
                result = await process_ended_trip(
                    session,
                    trip_id=due_trip.id,
                    settings=settings,
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                failed += 1
                logger.exception(
                    "job=process_unprocessed_trips trip_id=%s outcome=error "
                    "error_class=%s constraint=%s",
                    due_trip.id,
                    type(exc).__name__,
                    integrity_constraint_name(exc) or "unknown",
                )
                capture_exception(exc)
                continue
            except Exception as exc:
                await session.rollback()
                failed += 1
                logger.exception(
                    "job=process_unprocessed_trips trip_id=%s outcome=error error_class=%s",
                    due_trip.id,
                    type(exc).__name__,
                )
                capture_exception(exc)
                continue
        processed += 1
        if result.overall == "partial":
            partial += 1

    if not due_trips or len(due_trips) < settings.worker_sweep_batch_size:
        await _store_sweep_cursor(ctx, None)
    else:
        last_trip = due_trips[-1]
        await _store_sweep_cursor(ctx, (last_trip.ended_at, last_trip.id))
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "job=process_unprocessed_trips selected=%d processed=%d partial=%d failed=%d "
        "skipped=%d duration_ms=%d",
        selected,
        processed,
        partial,
        failed,
        skipped,
        duration_ms,
    )
    return {
        "selected": selected,
        "processed": processed,
        "partial": partial,
        "failed": failed,
        "skipped": skipped,
        "duration_ms": duration_ms,
    }


async def seal_ended_trips_job(ctx: dict[str, Any]) -> dict[str, Any]:
    settings = ctx["settings"]
    sessionmaker = ctx["sessionmaker"]
    started = time.monotonic()
    async with sessionmaker() as session:
        try:
            sealed_ids = await seal_due_trips(session, settings=settings)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.exception(
                "job=seal_ended_trips outcome=error error_class=%s",
                type(exc).__name__,
            )
            capture_exception(exc)
            raise
    # Latency optimization only: the processing sweep would pick these up anyway.
    enqueued = 0
    redis = ctx.get("redis")
    if redis is not None:
        for trip_id in sealed_ids:
            try:
                await redis.enqueue_job(
                    "process_trip", str(trip_id), _job_id=f"trip-process:{trip_id}"
                )
                enqueued += 1
            except Exception as exc:  # fail-open (§14.3.2)
                logger.warning(
                    "job=seal_ended_trips trip_id=%s event=enqueue_failed error_class=%s",
                    trip_id,
                    type(exc).__name__,
                )
                capture_exception(exc)
                break
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "job=seal_ended_trips sealed=%d enqueued=%d duration_ms=%d",
        len(sealed_ids),
        enqueued,
        duration_ms,
    )
    return {
        "sealed": len(sealed_ids),
        "enqueued": enqueued,
        "duration_ms": duration_ms,
    }

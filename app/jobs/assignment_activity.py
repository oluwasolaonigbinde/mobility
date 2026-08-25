"""Scheduled Q20 assignment activity operations sweep."""

import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.observability import capture_exception
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.services.assignment_activity import sweep_activity_flags
from app.services.payout_rule_serialization import database_clock

logger = logging.getLogger(__name__)

SWEEP_CURSOR_KEY = "worker:assignment-activity:sweep-cursor:v1"
SWEEP_CURSOR_CONTEXT_KEY = "_assignment_activity_sweep_cursor"


def _decode_cursor(raw: bytes | str | None) -> UUID | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return UUID(raw)
    except (TypeError, ValueError):
        logger.warning("job=sweep_assignment_activity event=invalid_cursor")
        return None


async def _load_sweep_cursor(ctx: dict[str, Any]) -> UUID | None:
    redis = ctx.get("redis")
    try:
        if redis is None:
            return _decode_cursor(ctx.get(SWEEP_CURSOR_CONTEXT_KEY))
        return _decode_cursor(await redis.get(SWEEP_CURSOR_KEY))
    except Exception:
        logger.exception("job=sweep_assignment_activity event=cursor_load_failed")
        return None


async def _store_sweep_cursor(ctx: dict[str, Any], cursor: UUID | None) -> None:
    redis = ctx.get("redis")
    try:
        if redis is None:
            if cursor is None:
                ctx.pop(SWEEP_CURSOR_CONTEXT_KEY, None)
            else:
                ctx[SWEEP_CURSOR_CONTEXT_KEY] = str(cursor)
            return
        if cursor is None:
            await redis.delete(SWEEP_CURSOR_KEY)
        else:
            await redis.set(SWEEP_CURSOR_KEY, str(cursor))
    except Exception:
        logger.exception("job=sweep_assignment_activity event=cursor_store_failed")


async def _active_assignment_batch(session, *, limit: int, after: UUID | None) -> list[UUID]:
    query = select(CampaignAssignment.id).where(
        CampaignAssignment.status == CampaignAssignmentStatus.ACTIVE.value
    )
    if after is not None:
        query = query.where(CampaignAssignment.id > after)
    return list((await session.scalars(query.order_by(CampaignAssignment.id).limit(limit))).all())


async def sweep_assignment_activity_flags(ctx: dict[str, Any]) -> dict[str, Any]:
    """Claim one fair bounded page, then evaluate each assignment independently."""
    started = time.monotonic()
    sessionmaker = ctx["sessionmaker"]
    settings = ctx["settings"]
    batch_size = settings.worker_sweep_batch_size
    cursor = await _load_sweep_cursor(ctx)
    try:
        async with sessionmaker() as session:
            evaluation_now = await database_clock(session)
            assignment_ids = await _active_assignment_batch(
                session,
                limit=batch_size,
                after=cursor,
            )
            if not assignment_ids and cursor is not None:
                assignment_ids = await _active_assignment_batch(
                    session,
                    limit=batch_size,
                    after=None,
                )
        result = await sweep_activity_flags(
            sessionmaker,
            assignment_ids=assignment_ids,
            settings=settings,
            now=evaluation_now,
        )
    except Exception as exc:
        capture_exception(exc)
        raise

    next_cursor = assignment_ids[-1] if len(assignment_ids) == batch_size else None
    await _store_sweep_cursor(ctx, next_cursor)
    result["cursor"] = "advanced" if next_cursor is not None else "wrapped"
    result["duration_ms"] = int((time.monotonic() - started) * 1000)
    return result

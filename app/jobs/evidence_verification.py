"""Bounded recurring evidence-verification sweep."""

import time
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select

from app.core.observability import capture_exception
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.evidence_verification import (
    EvidenceVerification,
    EvidenceVerificationStatus,
    EvidenceVerificationType,
)
from app.services.evidence_verification import evaluate_assignment_verification
from app.services.payout_rule_serialization import database_clock

CURSOR_KEY = "worker:evidence-verification:sweep-cursor:v1"
CURSOR_CONTEXT_KEY = "_evidence_verification_sweep_cursor"


def _decode_cursor(raw: bytes | str | None) -> UUID | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        return UUID(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("evidence verification cursor is malformed") from exc


async def _load_cursor(ctx: dict[str, Any]) -> UUID | None:
    redis = ctx.get("redis")
    if redis is None:
        return _decode_cursor(ctx.get(CURSOR_CONTEXT_KEY))
    return _decode_cursor(await redis.get(CURSOR_KEY))


async def _store_cursor(ctx: dict[str, Any], cursor: UUID | None) -> None:
    redis = ctx.get("redis")
    if redis is None:
        if cursor is None:
            ctx.pop(CURSOR_CONTEXT_KEY, None)
        else:
            ctx[CURSOR_CONTEXT_KEY] = str(cursor)
        return
    if cursor is None:
        await redis.delete(CURSOR_KEY)
    else:
        await redis.set(CURSOR_KEY, str(cursor))


async def sweep_evidence_verifications(ctx: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    settings = ctx["settings"]
    sessionmaker = ctx["sessionmaker"]
    after = await _load_cursor(ctx)
    async with sessionmaker() as session:
        now = await database_clock(session)
        due_challenge_exists = (
            select(EvidenceVerification.id)
            .where(
                EvidenceVerification.assignment_id == CampaignAssignment.id,
                EvidenceVerification.verification_type
                == EvidenceVerificationType.HIGH_EARNER_RENEWAL.value,
                EvidenceVerification.status == EvidenceVerificationStatus.PENDING.value,
                EvidenceVerification.due_at <= now,
            )
            .exists()
        )
        query = select(CampaignAssignment.id).where(
            or_(
                CampaignAssignment.status == CampaignAssignmentStatus.ACTIVE.value,
                due_challenge_exists,
            )
        )
        if after is not None:
            query = query.where(CampaignAssignment.id > after)
        assignment_ids = list(
            (
                await session.scalars(
                    query.order_by(CampaignAssignment.id).limit(settings.worker_sweep_batch_size)
                )
            ).all()
        )

    totals = {
        "processed": 0,
        "failed": 0,
        "high_earner_issued": 0,
        "missed_challenges": 0,
        "concurrent_holds": 0,
        "policy_unconfigured": 0,
    }
    for assignment_id in assignment_ids:
        async with sessionmaker() as session:
            try:
                result = await evaluate_assignment_verification(
                    session,
                    assignment_id=assignment_id,
                    settings=settings,
                    now=now,
                )
                await session.commit()
                totals["processed"] += 1
                totals["high_earner_issued"] += result.high_earner_issued
                totals["missed_challenges"] += result.missed_challenges
                totals["concurrent_holds"] += result.concurrent_holds
                totals["policy_unconfigured"] += int(result.policy_error is not None)
            except Exception as exc:  # pragma: no cover - observable worker boundary
                await session.rollback()
                capture_exception(exc)
                totals["failed"] += 1

    next_cursor = (
        assignment_ids[-1] if len(assignment_ids) == settings.worker_sweep_batch_size else None
    )
    await _store_cursor(ctx, next_cursor)
    return {
        **totals,
        "cursor": str(next_cursor) if next_cursor else None,
        "duration_seconds": time.monotonic() - started,
    }

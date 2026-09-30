import logging
from typing import Any
from uuid import UUID

from sqlalchemy import exists, func, select

from app.adapters.disbursement import DisabledDisbursementAdapter, DisbursementAdapter
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.models.disbursement import PayoutProviderEvent, PayoutProviderEventProcessingAttempt
from app.services.audit import create_audit_event
from app.services.disbursements import (
    find_due_payout_submission_intent_ids,
    process_payout_provider_event,
    process_payout_submission_intent,
    record_payout_provider_event_failure,
)

logger = logging.getLogger(__name__)

_TERMINAL_PAYOUT_EVENT_ERRORS = frozenset(
    {
        "PAYOUT_PROVIDER_EVIDENCE_MISMATCH",
        "PAYOUT_PROVIDER_EVENT_REPLAY_CONFLICT",
        "PAYOUT_PAID_HISTORY_IMMUTABLE",
        "PAYOUT_LEDGER_FINALITY_CONFLICT",
        "PAYOUT_PROVIDER_OUTCOME_INVALID",
    }
)
_BOUNDED_PAYOUT_EVENT_ERRORS = frozenset(
    {"PAYOUT_PROVIDER_LINE_NOT_FOUND", "PAYOUT_LINE_NOT_SUBMITTED"}
)
_MAX_BOUNDED_PAYOUT_EVENT_ATTEMPTS = 3


def _adapter(ctx: dict[str, Any]) -> DisbursementAdapter:
    return ctx.get("disbursement_adapter") or DisabledDisbursementAdapter()


def _settings(ctx: dict[str, Any]) -> Settings:
    return ctx.get("settings") or get_settings()


async def process_disbursement_intent_job(
    ctx: dict[str, Any], intent_id: str
) -> dict[str, str]:
    parsed_intent_id = UUID(intent_id)
    outcome = await process_payout_submission_intent(
        ctx["sessionmaker"],
        intent_id=parsed_intent_id,
        adapter=_adapter(ctx),
        settings=_settings(ctx),
    )
    return {"intent_id": str(parsed_intent_id), "outcome": outcome}


async def sweep_disbursement_intents(ctx: dict[str, Any]) -> dict[str, int]:
    """The database is the catch-up authority when request-path enqueue is absent or fails."""
    async with ctx["sessionmaker"]() as session:
        intent_ids = await find_due_payout_submission_intent_ids(session, settings=_settings(ctx))
    processed = 0
    failed = 0
    for intent_id in intent_ids:
        try:
            await process_disbursement_intent_job(ctx, str(intent_id))
            processed += 1
        except Exception as exc:
            error_code = exc.code if isinstance(exc, AppError) else type(exc).__name__
            logger.warning(
                "Payout submission processing failed",
                extra={"intent_id": str(intent_id), "error_code": error_code},
            )
            async with ctx["sessionmaker"]() as session:
                await create_audit_event(
                    session,
                    actor_user_id=None,
                    action="worker.payout_submission.failed",
                    entity_type="payout_submission_intent",
                    entity_id=str(intent_id),
                    metadata={"error_code": error_code},
                )
                await session.commit()
            failed += 1
    return {"selected": len(intent_ids), "processed": processed, "failed": failed}


async def process_payout_provider_event_job(
    ctx: dict[str, Any], event_id: str
) -> dict[str, str | int]:
    parsed_event_id = UUID(event_id)
    async with ctx["sessionmaker"]() as session:
        try:
            attempt = await process_payout_provider_event(session, event_id=parsed_event_id)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            error_code = exc.code if isinstance(exc, AppError) else type(exc).__name__
            async with ctx["sessionmaker"]() as failure_session:
                await record_payout_provider_event_failure(
                    failure_session,
                    event_id=parsed_event_id,
                    error_code=error_code,
                )
                await failure_session.commit()
            raise
    return {
        "event_id": str(parsed_event_id),
        "outcome": attempt.outcome,
        "attempt_number": attempt.attempt_number,
    }


async def sweep_payout_provider_events(ctx: dict[str, Any]) -> dict[str, int]:
    async with ctx["sessionmaker"]() as session:
        bounded_failures = (
            select(func.count(PayoutProviderEventProcessingAttempt.id))
            .where(
                PayoutProviderEventProcessingAttempt.provider_event_id
                == PayoutProviderEvent.id,
                PayoutProviderEventProcessingAttempt.outcome == "failed",
                PayoutProviderEventProcessingAttempt.error_code.in_(
                    _BOUNDED_PAYOUT_EVENT_ERRORS
                ),
            )
            .correlate(PayoutProviderEvent)
            .scalar_subquery()
        )
        event_ids = list(
            await session.scalars(
                select(PayoutProviderEvent.id)
                .where(
                    ~exists().where(
                        PayoutProviderEventProcessingAttempt.provider_event_id
                        == PayoutProviderEvent.id,
                        PayoutProviderEventProcessingAttempt.outcome == "processed",
                    ),
                    ~exists().where(
                        PayoutProviderEventProcessingAttempt.provider_event_id
                        == PayoutProviderEvent.id,
                        PayoutProviderEventProcessingAttempt.outcome == "failed",
                        PayoutProviderEventProcessingAttempt.error_code.in_(
                            _TERMINAL_PAYOUT_EVENT_ERRORS
                        ),
                    ),
                    bounded_failures < _MAX_BOUNDED_PAYOUT_EVENT_ATTEMPTS,
                )
                .order_by(PayoutProviderEvent.received_at, PayoutProviderEvent.id)
                .limit(100)
            )
        )
    processed = 0
    failed = 0
    for event_id in event_ids:
        try:
            await process_payout_provider_event_job(ctx, str(event_id))
            processed += 1
        except Exception:
            failed += 1
    return {"selected": len(event_ids), "processed": processed, "failed": failed}

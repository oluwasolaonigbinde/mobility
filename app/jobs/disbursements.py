import logging
from typing import Any
from uuid import UUID

from app.adapters.disbursement import DisabledDisbursementAdapter, DisbursementAdapter
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.services.audit import create_audit_event
from app.services.disbursements import (
    find_due_payout_submission_intent_ids,
    process_payout_submission_intent,
)

logger = logging.getLogger(__name__)


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
        intent_ids = await find_due_payout_submission_intent_ids(session)
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

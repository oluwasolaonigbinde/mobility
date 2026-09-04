from typing import Any
from uuid import UUID

from app.adapters.disbursement import DisabledDisbursementAdapter, DisbursementAdapter
from app.services.disbursements import (
    find_due_payout_submission_intent_ids,
    process_payout_submission_intent,
)


def _adapter(ctx: dict[str, Any]) -> DisbursementAdapter:
    return ctx.get("disbursement_adapter") or DisabledDisbursementAdapter()


async def process_disbursement_intent_job(
    ctx: dict[str, Any], intent_id: str
) -> dict[str, str]:
    parsed_intent_id = UUID(intent_id)
    outcome = await process_payout_submission_intent(
        ctx["sessionmaker"],
        intent_id=parsed_intent_id,
        adapter=_adapter(ctx),
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
        except Exception:
            failed += 1
    return {"selected": len(intent_ids), "processed": processed, "failed": failed}

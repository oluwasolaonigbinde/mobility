from typing import Any
from uuid import UUID

from sqlalchemy import exists, select

from app.core.errors import AppError
from app.models.billing import PaymentGatewayEvent, PaymentGatewayProcessingAttempt
from app.services.billing import process_payment_gateway_event, record_payment_gateway_failure


async def process_payment_gateway_event_job(
    ctx: dict[str, Any], event_id: str
) -> dict[str, str | int]:
    parsed_event_id = UUID(event_id)
    async with ctx["sessionmaker"]() as session:
        try:
            attempt = await process_payment_gateway_event(session, event_id=parsed_event_id)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            error_code = exc.code if isinstance(exc, AppError) else type(exc).__name__
            async with ctx["sessionmaker"]() as failure_session:
                await record_payment_gateway_failure(
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


async def sweep_payment_gateway_events(ctx: dict[str, Any]) -> dict[str, int]:
    """Recover committed events after request-path enqueue failure or worker retry."""
    async with ctx["sessionmaker"]() as session:
        event_ids = list(
            await session.scalars(
                select(PaymentGatewayEvent.id)
                .where(
                    ~exists().where(
                        PaymentGatewayProcessingAttempt.gateway_event_id == PaymentGatewayEvent.id,
                        PaymentGatewayProcessingAttempt.outcome.in_(
                            ("confirmed", "ignored_failed")
                        ),
                    )
                )
                .order_by(PaymentGatewayEvent.received_at, PaymentGatewayEvent.id)
                .limit(100)
            )
        )
    processed = 0
    failed = 0
    for event_id in event_ids:
        try:
            await process_payment_gateway_event_job(ctx, str(event_id))
            processed += 1
        except Exception:
            failed += 1
    return {"selected": len(event_ids), "processed": processed, "failed": failed}

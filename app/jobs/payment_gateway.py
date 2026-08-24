from typing import Any
from uuid import UUID

from app.core.errors import AppError
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

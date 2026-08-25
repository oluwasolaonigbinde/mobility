"""Background lifecycle jobs for campaign-assignment offers."""

from time import monotonic
from typing import Any

from app.services.campaign_assignments import expire_due_assignment_offers


async def sweep_campaign_assignment_expiries(ctx: dict[str, Any]) -> dict[str, int | float]:
    """Expire due offers in one bounded, retry-safe worker transaction."""
    started = monotonic()
    sessionmaker = ctx["sessionmaker"]
    expired = 0
    try:
        async with sessionmaker() as session:
            expired = await expire_due_assignment_offers(session)
            await session.commit()
    except Exception:
        # The worker framework retries the failed run; the transaction is
        # rolled back by the session context and every transition is idempotent.
        raise
    return {"expired": expired, "duration_seconds": monotonic() - started}

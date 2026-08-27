"""Background expiry materialization for approved vehicle evidence."""

from time import monotonic
from typing import Any

from app.services.vehicle_onboarding import expire_due_vehicle_approvals


async def sweep_vehicle_approval_expiries(ctx: dict[str, Any]) -> dict[str, int | float]:
    started = monotonic()
    async with ctx["sessionmaker"]() as session:
        expired = await expire_due_vehicle_approvals(session)
        await session.commit()
    return {"expired": expired, "duration_seconds": monotonic() - started}

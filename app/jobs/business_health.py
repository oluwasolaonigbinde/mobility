"""Five-minute Finance health sweep; never changes money or evidence authority."""

from datetime import UTC, datetime
from typing import Any

from app.services.business_health import health_counts, publish_health_alerts


async def sweep_business_health(ctx: dict[str, Any]) -> dict[str, int]:
    now = datetime.now(UTC)
    async with ctx["sessionmaker"]() as session:
        counts = await health_counts(
            session, now=now, settings=ctx["settings"], redis=ctx.get("redis")
        )
        created = await publish_health_alerts(session, now=now, counts=counts)
        await session.commit()
    return {"alerts_created": created}

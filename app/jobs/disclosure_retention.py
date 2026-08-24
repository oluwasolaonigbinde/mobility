import logging
from typing import Any

from sqlalchemy import delete, func

from app.models.disclosure import DisclosureQueryDecision

logger = logging.getLogger(__name__)


async def purge_expired_disclosure_query_history(ctx: dict[str, Any]) -> dict[str, int]:
    """Physically remove expired differencing history without waiting for new traffic."""
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        result = await session.execute(
            delete(DisclosureQueryDecision).where(
                DisclosureQueryDecision.expires_at <= func.now()
            )
        )
        await session.commit()
    deleted = int(result.rowcount or 0)
    logger.info("job=purge_expired_disclosure_query_history deleted=%d", deleted)
    return {"deleted": deleted}

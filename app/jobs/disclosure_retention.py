import logging
from typing import Any

logger = logging.getLogger(__name__)


async def purge_expired_disclosure_query_history(ctx: dict[str, Any]) -> dict[str, int]:
    """Retain protection until durable authority proves the source unqueryable.

    Keep the scheduled entry point compatible with already queued jobs. No source
    retirement authority exists yet, so elapsed time alone cannot permit deletion.
    """
    logger.info("job=purge_expired_disclosure_query_history deleted=0 source_retirement=unproven")
    return {"deleted": 0}

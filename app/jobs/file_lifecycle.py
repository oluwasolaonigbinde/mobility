import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import build_storage_provider
from app.services.stored_files import purge_expired_upload_intents

logger = logging.getLogger(__name__)


async def purge_orphaned_file_uploads(ctx: dict[str, Any]) -> dict[str, int]:
    settings = ctx["settings"]
    storage = build_storage_provider(settings)
    async with ctx["sessionmaker"]() as session:
        session: AsyncSession
        purged = await purge_expired_upload_intents(
            session,
            storage=storage,
            limit=settings.worker_sweep_batch_size,
        )
        await session.commit()
    logger.info("job=purge_orphaned_file_uploads purged=%d", purged)
    return {"purged": purged}

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import build_storage_provider
from app.services.file_kyc_lifecycle import purge_terminal_file_kyc
from app.services.stored_files import purge_expired_upload_intents
from app.services.stored_object_deletions import process_stored_object_deletions

logger = logging.getLogger(__name__)


async def recover_stored_object_deletions(ctx: dict[str, Any]) -> dict[str, int]:
    settings = ctx["settings"]
    storage = build_storage_provider(settings)
    completed = await process_stored_object_deletions(
        ctx["sessionmaker"],
        storage=storage,
        limit=settings.worker_sweep_batch_size,
    )
    logger.info("job=recover_stored_object_deletions completed=%d", completed)
    return {"completed": completed}


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


async def purge_expired_file_kyc(ctx: dict[str, Any]) -> dict[str, int | bool]:
    settings = ctx["settings"]
    if settings.file_kyc_retention_days is None:
        logger.warning("job=purge_expired_file_kyc policy_configured=false")
        return {
            "policy_configured": False,
            "lock_acquired": False,
            "eligible_submissions": 0,
            "purged_submissions": 0,
            "purged_files": 0,
        }
    storage = build_storage_provider(settings)
    async with ctx["sessionmaker"]() as session:
        session: AsyncSession
        result = await purge_terminal_file_kyc(
            session,
            storage=storage,
            retention_days=settings.file_kyc_retention_days,
            limit=settings.worker_sweep_batch_size,
            dry_run=False,
            actor_user_id=None,
            reason="scheduled_file_kyc_retention",
        )
        await session.commit()
    logger.info(
        "job=purge_expired_file_kyc eligible=%d purged_submissions=%d purged_files=%d",
        result.eligible_submissions,
        result.purged_submissions,
        result.purged_files,
    )
    return {
        "policy_configured": result.policy_configured,
        "lock_acquired": result.lock_acquired,
        "eligible_submissions": result.eligible_submissions,
        "purged_submissions": result.purged_submissions,
        "purged_files": result.purged_files,
    }

import logging
from typing import Any

from sqlalchemy import func, or_, select

from app.adapters.scanner import build_malware_scanner
from app.adapters.storage import build_storage_provider
from app.models.stored_file import FileScanStatus, StoredFile
from app.services.stored_files import scan_stored_file

logger = logging.getLogger(__name__)


async def scan_pending_files(ctx: dict[str, Any]) -> dict[str, int]:
    settings = ctx["settings"]
    storage = build_storage_provider(settings)
    scanner = build_malware_scanner(settings)
    async with ctx["sessionmaker"]() as session:
        candidate_ids = list(
            (
                await session.scalars(
                    select(StoredFile.id)
                    .where(
                        StoredFile.scan_status.in_([FileScanStatus.PENDING, FileScanStatus.ERROR]),
                        or_(
                            StoredFile.next_scan_at.is_(None),
                            StoredFile.next_scan_at <= func.now(),
                        ),
                    )
                    .order_by(StoredFile.created_at, StoredFile.id)
                    .limit(settings.worker_sweep_batch_size)
                )
            ).all()
        )

    counts = {"selected": len(candidate_ids), "clean": 0, "unsafe": 0, "failed": 0}
    for file_id in candidate_ids:
        async with ctx["sessionmaker"]() as session:
            outcome = await scan_stored_file(
                session,
                file_id=file_id,
                storage=storage,
                scanner=scanner,
            )
            await session.commit()
        if outcome == FileScanStatus.CLEAN:
            counts["clean"] += 1
        elif outcome in {FileScanStatus.INFECTED, FileScanStatus.REJECTED}:
            counts["unsafe"] += 1
        elif outcome == FileScanStatus.ERROR:
            counts["failed"] += 1
    logger.info("job=scan_pending_files counts=%s", counts)
    return counts

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.outbox_enqueue import enqueue_outbox_jobs


class OutboxSession(AsyncSession):
    """Await queue hints only after the outer transaction commits successfully."""

    async def commit(self) -> None:
        await self.flush()
        jobs = self.info.pop("outbox_jobs", set())
        if jobs:
            from app.models.campaign_report import CampaignReport
            from app.models.notification import (
                Notification,
                NotificationChannel,
                NotificationStatus,
            )
            from app.models.stored_file import FileScanStatus, StoredFile

            # A rolled-back savepoint may have left a hint in session.info. Only
            # IDs still visible in this transaction may escape after its commit.
            files = set(
                await self.scalars(
                    select(StoredFile.id).where(
                        StoredFile.id.in_([i for kind, i in jobs if kind == "scan_file"]),
                        StoredFile.scan_status.in_([FileScanStatus.PENDING, FileScanStatus.ERROR]),
                    )
                )
            )
            emails = set(
                await self.scalars(
                    select(Notification.id).where(
                        Notification.id.in_([i for kind, i in jobs if kind == "deliver_email"]),
                        Notification.channel == NotificationChannel.TRANSACTIONAL_EMAIL,
                        Notification.status == NotificationStatus.PENDING,
                    )
                )
            )
            reports = set(
                await self.scalars(
                    select(CampaignReport.id).where(
                        CampaignReport.id.in_(
                            [i for kind, i in jobs if kind == "generate_campaign_report"]
                        ),
                        CampaignReport.status == "queued",
                    )
                )
            )
            visible = {
                "scan_file": files,
                "deliver_email": emails,
                "generate_campaign_report": reports,
            }
            jobs = {(kind, i) for kind, i in jobs if i in visible.get(kind, set())}
        await super().commit()
        settings = self.info.get("enqueue_settings")
        if settings is not None:
            await enqueue_outbox_jobs(settings, jobs)

    async def rollback(self) -> None:
        self.info.pop("outbox_jobs", None)
        await super().rollback()

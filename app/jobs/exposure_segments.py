import logging
from typing import Any
from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.core.errors import AppError
from app.models.audience_work import AudienceSweepCursor
from app.models.exposure_segment import ExposureSegment
from app.models.measurement import MeasurementRun
from app.models.retargeting_source_link import RetargetingSourceLink
from app.services.audience import materialize_exposure_segment
from app.services.disclosure import audience_disclosure_policy
from app.services.measurement import canonical_sha256

logger = logging.getLogger(__name__)


async def materialize_exposure_segment_job(
    ctx: dict[str, Any],
    measurement_run_id: str,
    source_link_id: str,
) -> str:
    async with ctx["sessionmaker"]() as session:
        segment = await materialize_exposure_segment(
            session,
            settings=ctx["settings"],
            measurement_run_id=UUID(measurement_run_id),
            source_link_id=UUID(source_link_id),
        )
        await session.commit()
        return str(segment.id)


async def sweep_exposure_segments(ctx: dict[str, Any]) -> int:
    """Discover committed run/link pairs in either creation order, without Redis authority.

    A durable keyset cursor advances even over invalid candidates. Each pair has its
    own transaction; failed/lost work is revisited after wrap, not stuck at a prefix.
    """
    async with ctx["sessionmaker"]() as session:
        await session.execute(
            insert(AudienceSweepCursor)
            .values(name="exposure_segments")
            .on_conflict_do_nothing(index_elements=["name"])
        )
        cursor = await session.scalar(
            select(AudienceSweepCursor)
            .where(AudienceSweepCursor.name == "exposure_segments")
            .with_for_update()
        )
        assert cursor is not None
        statement = (
            select(MeasurementRun.id, RetargetingSourceLink.id)
            .join(
                RetargetingSourceLink,
                and_(
                    RetargetingSourceLink.campaign_id == MeasurementRun.campaign_id,
                    RetargetingSourceLink.organization_id == MeasurementRun.organization_id,
                ),
            )
            .where(
                RetargetingSourceLink.status == "active",
                ~MeasurementRun.id.in_(
                    select(MeasurementRun.reissue_of_run_id).where(
                        MeasurementRun.reissue_of_run_id.is_not(None)
                    )
                ),
                ~exists().where(
                    ExposureSegment.measurement_run_id == MeasurementRun.id,
                    ExposureSegment.source_link_id == RetargetingSourceLink.id,
                    ExposureSegment.disclosure_policy_sha256
                    == canonical_sha256(audience_disclosure_policy(ctx["settings"])),
                ),
            )
        )
        if cursor.measurement_run_id is not None:
            statement = statement.where(
                or_(
                    MeasurementRun.id > cursor.measurement_run_id,
                    and_(
                        MeasurementRun.id == cursor.measurement_run_id,
                        RetargetingSourceLink.id > cursor.source_link_id,
                    ),
                )
            )
        pairs = list(
            (
                await session.execute(
                    statement.order_by(MeasurementRun.id, RetargetingSourceLink.id).limit(
                        ctx["settings"].worker_sweep_batch_size
                    )
                )
            ).all()
        )
        if pairs:
            cursor.measurement_run_id, cursor.source_link_id = pairs[-1]
        else:
            cursor.measurement_run_id = cursor.source_link_id = None
        await session.commit()
    completed = 0
    failed = 0
    for run_id, link_id in pairs:
        try:
            await materialize_exposure_segment_job(ctx, str(run_id), str(link_id))
            completed += 1
        except AppError as exc:
            failed += 1
            logger.warning("event=audience_catchup_refused code=%s", exc.code)
        except Exception:
            failed += 1
            logger.exception("event=audience_catchup_failed")
    logger.info(
        "event=audience_catchup scanned=%s completed=%s failed=%s", len(pairs), completed, failed
    )
    return completed

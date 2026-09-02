from typing import Any
from uuid import UUID

from app.services.audience import materialize_exposure_segment


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

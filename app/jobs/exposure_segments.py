from typing import Any
from uuid import UUID

from pydantic import TypeAdapter

from app.schemas.exposure_segments import ExposureCellInput
from app.services.audience import materialize_exposure_segment


async def materialize_exposure_segment_job(
    ctx: dict[str, Any],
    measurement_run_id: str,
    source_link_id: str,
    cells: list[dict[str, Any]],
) -> str:
    typed_cells = TypeAdapter(list[ExposureCellInput]).validate_python(cells)
    async with ctx["sessionmaker"]() as session:
        segment = await materialize_exposure_segment(
            session,
            settings=ctx["settings"],
            measurement_run_id=UUID(measurement_run_id),
            source_link_id=UUID(source_link_id),
            cells=typed_cells,
        )
        await session.commit()
        return str(segment.id)

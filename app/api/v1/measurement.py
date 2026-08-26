from uuid import UUID

from fastapi import APIRouter
from starlette import status

from app.api.v1.dependencies import AdminUserDependency, SessionDependency, SettingsDependency
from app.core.errors import AppError
from app.models.measurement import MeasurementRun
from app.schemas.measurement import MeasurementRunCreate, MeasurementRunRead
from app.services.measurement import issue_measurement_run, measurement_run_read

router = APIRouter(tags=["Measurement"])


@router.post(
    "/admin/measurement-runs",
    response_model=MeasurementRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Issue an immutable campaign measurement run",
)
async def admin_issue_measurement_run(
    payload: MeasurementRunCreate,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> MeasurementRunRead:
    run = await issue_measurement_run(
        session, actor_user_id=user.id, payload=payload, settings=settings
    )
    response = await measurement_run_read(session, run)
    await session.commit()
    return response


@router.get(
    "/admin/measurement-runs/{run_id}",
    response_model=MeasurementRunRead,
    summary="Read and reproduce an immutable measurement run",
)
async def admin_get_measurement_run(
    run_id: UUID,
    _user: AdminUserDependency,
    session: SessionDependency,
) -> MeasurementRunRead:
    run = await session.get(MeasurementRun, run_id)
    if run is None:
        raise AppError(
            "MEASUREMENT_RUN_NOT_FOUND",
            "Measurement run was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return await measurement_run_read(session, run)

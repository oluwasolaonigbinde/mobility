from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from starlette import status

from app.api.v1.dependencies import AdminUserDependency, SessionDependency, SettingsDependency
from app.core.errors import AppError
from app.models.campaign import Campaign
from app.models.measurement import MeasurementRun
from app.models.report_issuance import ReportIssuance
from app.schemas.measurement import (
    AdminMeasurementRunList,
    AdminMeasurementRunSummary,
    MeasurementRunCreate,
    MeasurementRunRead,
    MeasurementRunSummary,
)
from app.services.measurement import (
    issue_measurement_run,
    measurement_run_read,
    measurement_run_reproducible,
)
from app.services.operator_search import operator_search

router = APIRouter(tags=["Measurement"])


@router.get("/admin/measurement-runs", response_model=AdminMeasurementRunList)
async def admin_list_measurement_runs(
    user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    campaign_id: UUID | None = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> AdminMeasurementRunList:
    query = select(MeasurementRun, Campaign.name).join(
        Campaign, MeasurementRun.campaign_id == Campaign.id
    )
    if campaign_id is not None:
        query = query.where(MeasurementRun.campaign_id == campaign_id)
    if q and q.strip():
        query = query.where(operator_search(q, Campaign.name))
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = (
        await session.execute(
            query.order_by(MeasurementRun.created_at.desc(), MeasurementRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    items = []
    for run, name in rows:
        issuance = await session.scalar(
            select(ReportIssuance)
            .where(ReportIssuance.measurement_run_id == run.id)
            .order_by(ReportIssuance.version.desc())
            .limit(1)
        )
        superseded = await session.scalar(
            select(MeasurementRun.id).where(MeasurementRun.reissue_of_run_id == run.id).limit(1)
        )
        items.append(
            AdminMeasurementRunSummary(
                **MeasurementRunSummary.model_validate(run, from_attributes=True).model_dump(),
                campaign_id=run.campaign_id,
                campaign_name=name,
                test_only=run.test_only,
                reproducible=measurement_run_reproducible(run),
                superseded=superseded is not None,
                report_issuance_id=issuance.id if issuance else None,
                report_status=issuance.status if issuance else None,
            )
        )
    return AdminMeasurementRunList(items=items, total=total, limit=limit, offset=offset)


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

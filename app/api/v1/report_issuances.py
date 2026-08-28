from uuid import UUID

from fastapi import APIRouter, status

from app.api.v1.dependencies import (
    AdminUserDependency,
    AdvertiserUserDependency,
    SessionDependency,
    SettingsDependency,
    StorageDependency,
)
from app.models.report_issuance import ReportArtifactFormat
from app.schemas.report_issuances import (
    ReportArtifactDownloadRead,
    ReportArtifactDownloadRequest,
    ReportIssuanceCreate,
    ReportIssuanceRead,
)
from app.services.report_issuances import (
    get_report_issuance,
    issue_report_artifact_download,
    report_issuance_read,
    request_report_issuance,
)

router = APIRouter(tags=["Report Issuances"])


@router.post(
    "/advertiser/measurement-runs/{run_id}/report-issuances",
    response_model=ReportIssuanceRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def advertiser_request_report_issuance(
    run_id: UUID,
    payload: ReportIssuanceCreate,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> ReportIssuanceRead:
    issuance = await request_report_issuance(
        session,
        actor_user_id=user.id,
        measurement_run_id=run_id,
        payload=payload,
        settings=settings,
        admin=False,
    )
    response = await report_issuance_read(session, issuance)
    await session.commit()
    return response


@router.post(
    "/admin/measurement-runs/{run_id}/report-issuances",
    response_model=ReportIssuanceRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def admin_request_report_issuance(
    run_id: UUID,
    payload: ReportIssuanceCreate,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> ReportIssuanceRead:
    issuance = await request_report_issuance(
        session,
        actor_user_id=user.id,
        measurement_run_id=run_id,
        payload=payload,
        settings=settings,
        admin=True,
    )
    response = await report_issuance_read(session, issuance)
    await session.commit()
    return response


@router.get(
    "/advertiser/report-issuances/{issuance_id}",
    response_model=ReportIssuanceRead,
)
async def advertiser_get_report_issuance(
    issuance_id: UUID,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> ReportIssuanceRead:
    issuance = await get_report_issuance(
        session,
        actor_user_id=user.id,
        issuance_id=issuance_id,
        settings=settings,
        admin=False,
    )
    return await report_issuance_read(session, issuance)


@router.get(
    "/admin/report-issuances/{issuance_id}",
    response_model=ReportIssuanceRead,
)
async def admin_get_report_issuance(
    issuance_id: UUID,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> ReportIssuanceRead:
    issuance = await get_report_issuance(
        session,
        actor_user_id=user.id,
        issuance_id=issuance_id,
        settings=settings,
        admin=True,
    )
    return await report_issuance_read(session, issuance)


@router.post(
    "/advertiser/report-issuances/{issuance_id}/artifacts/{artifact_format}/download",
    response_model=ReportArtifactDownloadRead,
)
async def advertiser_download_report_artifact(
    issuance_id: UUID,
    artifact_format: ReportArtifactFormat,
    payload: ReportArtifactDownloadRequest,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    storage: StorageDependency,
    settings: SettingsDependency,
) -> ReportArtifactDownloadRead:
    response = await issue_report_artifact_download(
        session,
        actor_user_id=user.id,
        issuance_id=issuance_id,
        artifact_format=artifact_format,
        reason=payload.reason,
        storage=storage,
        settings=settings,
        admin=False,
    )
    await session.commit()
    return response


@router.post(
    "/admin/report-issuances/{issuance_id}/artifacts/{artifact_format}/download",
    response_model=ReportArtifactDownloadRead,
)
async def admin_download_report_artifact(
    issuance_id: UUID,
    artifact_format: ReportArtifactFormat,
    payload: ReportArtifactDownloadRequest,
    user: AdminUserDependency,
    session: SessionDependency,
    storage: StorageDependency,
    settings: SettingsDependency,
) -> ReportArtifactDownloadRead:
    response = await issue_report_artifact_download(
        session,
        actor_user_id=user.id,
        issuance_id=issuance_id,
        artifact_format=artifact_format,
        reason=payload.reason,
        storage=storage,
        settings=settings,
        admin=True,
    )
    await session.commit()
    return response

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.v1.dependencies import (
    AdminUserDependency,
    AdvertiserUserDependency,
    SessionDependency,
    SettingsDependency,
    StorageDependency,
)
from app.models.report_issuance import ReportArtifactFormat
from app.schemas.campaign_reports import (
    CampaignReportCreate,
    CampaignReportList,
    CampaignReportRead,
    CampaignReportRerun,
)
from app.schemas.report_issuances import ReportArtifactDownloadRead, ReportArtifactDownloadRequest
from app.services.campaign_reports import (
    download_report,
    get_report,
    list_reports,
    report_read,
    request_advertiser_report,
)

router = APIRouter(tags=["Campaign reports"])


@router.post(
    "/advertiser/reports", response_model=CampaignReportRead, status_code=status.HTTP_202_ACCEPTED
)
async def advertiser_request_report(
    payload: CampaignReportCreate,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    storage: StorageDependency,
) -> CampaignReportRead:
    report = await request_advertiser_report(
        session, actor_user_id=user.id, payload=payload, settings=settings, storage=storage
    )
    response = report_read(report)
    await session.commit()
    return response


@router.get("/advertiser/reports", response_model=CampaignReportList)
async def advertiser_list_reports(
    user: AdvertiserUserDependency,
    session: SessionDependency,
    campaign_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CampaignReportList:
    return await list_reports(
        session,
        actor_user_id=user.id,
        admin=False,
        campaign_id=campaign_id,
        limit=limit,
        offset=offset,
    )


@router.get("/admin/reports", response_model=CampaignReportList)
async def admin_list_reports(
    user: AdminUserDependency,
    session: SessionDependency,
    campaign_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CampaignReportList:
    return await list_reports(
        session,
        actor_user_id=user.id,
        admin=True,
        campaign_id=campaign_id,
        limit=limit,
        offset=offset,
    )


@router.get("/advertiser/reports/{report_id}", response_model=CampaignReportRead)
async def advertiser_get_report(
    report_id: UUID, user: AdvertiserUserDependency, session: SessionDependency
) -> CampaignReportRead:
    return report_read(
        await get_report(session, report_id=report_id, actor_user_id=user.id, admin=False)
    )


@router.post(
    "/advertiser/reports/{report_id}/artifacts/{artifact_format}/download",
    response_model=ReportArtifactDownloadRead,
)
async def advertiser_download_report(
    report_id: UUID,
    artifact_format: ReportArtifactFormat,
    payload: ReportArtifactDownloadRequest,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    storage: StorageDependency,
) -> ReportArtifactDownloadRead:
    response = await download_report(
        session,
        report_id=report_id,
        artifact_format=artifact_format,
        actor_user_id=user.id,
        admin=False,
        storage=storage,
        settings=settings,
        reason=payload.reason,
    )
    await session.commit()
    return response


@router.post(
    "/admin/reports/{report_id}/artifacts/{artifact_format}/download",
    response_model=ReportArtifactDownloadRead,
)
async def admin_download_report(
    report_id: UUID,
    artifact_format: ReportArtifactFormat,
    payload: ReportArtifactDownloadRequest,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    storage: StorageDependency,
) -> ReportArtifactDownloadRead:
    response = await download_report(
        session,
        report_id=report_id,
        artifact_format=artifact_format,
        actor_user_id=user.id,
        admin=True,
        storage=storage,
        settings=settings,
        reason=payload.reason,
    )
    await session.commit()
    return response


@router.post(
    "/admin/campaigns/{campaign_id}/reports/re-run",
    response_model=CampaignReportRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def admin_rerun_report(
    campaign_id: UUID,
    payload: CampaignReportRerun,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    storage: StorageDependency,
) -> CampaignReportRead:
    from app.services.report_scheduling import rerun_campaign_report

    report = await rerun_campaign_report(
        session,
        actor_user_id=user.id,
        campaign_id=campaign_id,
        request_id=payload.client_request_id,
        settings=settings,
        storage=storage,
    )
    response = report_read(report)
    await session.commit()
    return response

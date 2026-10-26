from uuid import UUID

from fastapi import APIRouter

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
)
from app.services.report_issuances import (
    issue_report_artifact_download,
)

router = APIRouter(tags=["Report Issuances"])


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

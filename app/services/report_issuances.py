"""Read-only D71 downloads for files issued before the D118 report replacement."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.adapters.storage import PresignedGet, StorageProvider
from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign import Campaign
from app.models.measurement import MeasurementRun
from app.models.organization import (
    AdvertiserOrganization,
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
    OrganizationStatus,
)
from app.models.report_issuance import (
    ReportArtifact,
    ReportArtifactFormat,
    ReportIssuance,
    ReportIssuanceStatus,
)
from app.models.stored_file import FilePurpose, StoredFile
from app.models.user import User, UserRole, UserStatus
from app.schemas.report_issuances import ReportArtifactDownloadRead
from app.services.audit import create_audit_event
from app.services.report_authorization import REPORT_ACTOR_ID, is_report_automation_user
from app.services.report_integrity import canonical_sha256
from app.services.stored_files import _issue_download


def _error(code: str, message: str, status_code: int) -> AppError:
    return AppError(code, message, status_code=status_code)


def _not_found() -> AppError:
    return _error(
        "REPORT_ISSUANCE_NOT_FOUND",
        "Report issuance was not found",
        status.HTTP_404_NOT_FOUND,
    )


async def _authorize_scope(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    organization_id: UUID,
    campaign_id: UUID,
    write: bool,
) -> User:
    user = await session.scalar(
        select(User)
        .where(User.id == actor_user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    organization = await session.scalar(
        select(AdvertiserOrganization)
        .where(AdvertiserOrganization.id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    campaign = await session.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id, Campaign.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        user is None
        or (
            not is_report_automation_user(user)
            if user.id == REPORT_ACTOR_ID
            else user.status != UserStatus.ACTIVE
        )
        or organization is None
        or organization.status != OrganizationStatus.ACTIVE
        or campaign is None
    ):
        raise _not_found()
    if user.role == UserRole.ADMIN:
        return user
    if user.role != UserRole.ADVERTISER:
        raise _not_found()
    membership = await session.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.user_id == actor_user_id,
            OrganizationMembership.organization_id == organization_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        raise _not_found()
    if write and membership.role != MembershipRole.ADVERTISER:
        raise _error(
            "REPORT_ISSUANCE_ROLE_FORBIDDEN",
            "Active advertiser access is required for report issuance",
            status.HTTP_403_FORBIDDEN,
        )
    return user


def _filename(issuance: ReportIssuance, artifact_format: str) -> str:
    return f"cardvert-campaign-performance-analysis-v{issuance.version}.{artifact_format}"


def _issued_snapshot_is_intact(issuance: ReportIssuance, run: MeasurementRun) -> bool:
    if canonical_sha256(issuance.snapshot) != issuance.snapshot_sha256:
        return False
    return all(
        digest == bound_digest and canonical_sha256(value) == digest
        for value, digest, bound_digest in (
            (run.input_manifest, run.input_manifest_sha256, issuance.input_manifest_sha256),
            (run.result_manifest, run.result_manifest_sha256, issuance.result_manifest_sha256),
            (run.proof_manifest, run.proof_manifest_sha256, issuance.proof_manifest_sha256),
            (run.report_snapshot, run.report_snapshot_sha256, issuance.report_snapshot_sha256),
        )
    )


async def get_report_issuance(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    issuance_id: UUID,
    settings: Settings,
    admin: bool,
) -> ReportIssuance:
    issuance = await session.get(ReportIssuance, issuance_id)
    if issuance is None:
        raise _not_found()
    try:
        actor = await _authorize_scope(
            session,
            actor_user_id=actor_user_id,
            organization_id=issuance.organization_id,
            campaign_id=issuance.campaign_id,
            write=True,
        )
    except AppError as exc:
        if exc.code == "REPORT_ISSUANCE_ROLE_FORBIDDEN":
            raise _not_found() from exc
        raise
    if admin != (actor.role == UserRole.ADMIN):
        raise _not_found()
    run = await session.get(MeasurementRun, issuance.measurement_run_id)
    if run is None:
        raise _not_found()
    if issuance.status != "ready" or not _issued_snapshot_is_intact(issuance, run):
        raise _not_found()
    return issuance


async def issue_report_artifact_download(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    issuance_id: UUID,
    artifact_format: ReportArtifactFormat,
    reason: str,
    storage: StorageProvider,
    settings: Settings,
    admin: bool,
) -> ReportArtifactDownloadRead:
    issuance = await get_report_issuance(
        session,
        actor_user_id=actor_user_id,
        issuance_id=issuance_id,
        settings=settings,
        admin=admin,
    )
    if issuance.status != ReportIssuanceStatus.READY:
        raise _not_found()
    artifact = await session.scalar(
        select(ReportArtifact).where(
            ReportArtifact.report_issuance_id == issuance.id,
            ReportArtifact.format == artifact_format,
        )
    )
    if artifact is None:
        raise _not_found()
    stored_file = await session.scalar(
        select(StoredFile).where(
            StoredFile.id == artifact.stored_file_id,
            StoredFile.organization_id == issuance.organization_id,
            StoredFile.purpose == FilePurpose.REPORT_EXPORT,
            StoredFile.checksum_sha256 == artifact.checksum_sha256,
            StoredFile.size_bytes == artifact.size_bytes,
            StoredFile.content_type == artifact.content_type,
        )
    )
    if stored_file is None:
        raise _not_found()
    download: PresignedGet = await _issue_download(
        session,
        stored_file=stored_file,
        actor_user_id=actor_user_id,
        access_purpose="report_download",
        reason=reason,
        storage=storage,
        settings=settings,
    )
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="report_artifact.downloaded",
        entity_type="report_issuance",
        entity_id=str(issuance.id),
        metadata={
            "version": issuance.version,
            "format": artifact.format,
            "checksum_sha256": artifact.checksum_sha256,
        },
    )
    return ReportArtifactDownloadRead(
        url=download.url,
        expires_in_seconds=download.expires_in_seconds,
        filename=_filename(issuance, artifact.format),
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
        checksum_sha256=artifact.checksum_sha256,
    )

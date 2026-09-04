from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status

from app.adapters.storage import (
    PresignedGet,
    StorageObjectConflict,
    StorageObjectNotFound,
    StorageProvider,
    StorageUnavailable,
)
from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign import Campaign
from app.models.exposure_score import ExposureScore
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
from app.models.stored_file import FilePurpose, FileScanStatus, StoredFile
from app.models.user import User, UserRole, UserStatus
from app.schemas.measurement import MeasurementResultRead
from app.schemas.report_issuances import (
    ReportArtifactDownloadRead,
    ReportArtifactRead,
    ReportIssuanceCreate,
    ReportIssuanceRead,
)
from app.services.audit import create_audit_event
from app.services.measurement import (
    SUPPRESSED_TOTAL_LABEL,
    canonical_sha256,
    measurement_run_reproducible,
)
from app.services.payout_rule_serialization import database_clock
from app.services.report_rendering import (
    ReportRenderLimitError,
    render_report_csv,
    render_report_pdf,
)
from app.services.stored_files import _issue_download

REPORT_SCHEMA_VERSION = "campaign-performance-export-v1"
REPORT_RENDERER_VERSION = "campaign-report-renderer-v1"
REPORT_LEASE_SECONDS = 120
REPORT_MAX_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class _RenderedArtifact:
    format: ReportArtifactFormat
    content_type: str
    filename: str
    storage_key: str
    content: bytes
    checksum_sha256: str


def _error(code: str, message: str, status_code: int) -> AppError:
    return AppError(code, message, status_code=status_code)


def _not_found() -> AppError:
    return _error(
        "REPORT_ISSUANCE_NOT_FOUND",
        "Report issuance was not found",
        status.HTTP_404_NOT_FOUND,
    )


def _approved_reference(value: str) -> bool:
    return value.strip().lower() not in {"", "missing", "todo", "tbd", "placeholder", "n/a", "none"}


def _authority_document(run: MeasurementRun, settings: Settings) -> dict[str, object]:
    if run.test_only:
        if (
            settings.environment.lower() != "test"
            or not settings.privacy_disclosure_synthetic_test_mode
        ):
            raise _error(
                "REPORT_SYNTHETIC_ISSUANCE_BLOCKED",
                "Synthetic report issuance is limited to the explicit test authority",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        authority_mode = "synthetic_test_only"
    else:
        required_privacy_references = (
            settings.privacy_legal_approval_reference,
            settings.privacy_disclosure_config_reference,
            settings.privacy_query_history_retention_reference,
        )
        if (
            not settings.privacy_disclosure_live_authorized
            or not all(_approved_reference(value) for value in required_privacy_references)
            or not settings.measurement_live_issuance_authorized
            or not _approved_reference(settings.measurement_report_method_reference)
            or run.method_revision != settings.measurement_report_method_reference
        ):
            raise _error(
                "REPORT_LIVE_ISSUANCE_BLOCKED",
                "Live report issuance is unavailable until legal and method approval exists",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        authority_mode = "approved_live"
    result = MeasurementResultRead.model_validate(run.result_manifest)
    if result.roi_gate.decision == "INCLUDE":
        roi_input = run.input_manifest.get("roi")
        method = roi_input.get("method") if isinstance(roi_input, dict) else None
        approval_reference = method.get("approval_reference") if isinstance(method, dict) else None
        if run.test_only:
            if approval_reference != "SYNTHETIC_TEST_ONLY":
                raise _error(
                    "REPORT_ROI_AUTHORITY_INVALID",
                    "The frozen financial result has no valid synthetic approval authority",
                    status.HTTP_409_CONFLICT,
                )
        elif (
            not _approved_reference(settings.measurement_roi_method_reference)
            or approval_reference != settings.measurement_roi_method_reference
        ):
            raise _error(
                "REPORT_ROI_AUTHORITY_INVALID",
                "The frozen financial result no longer matches approved authority",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
    return {
        "schema_version": "report-issuance-authority-v1",
        "mode": authority_mode,
        "run_id": str(run.id),
        "run_method_revision": run.method_revision,
        "run_roi_method_revision": run.roi_method_revision,
        "privacy_live_authorized": settings.privacy_disclosure_live_authorized,
        "privacy_synthetic_test_mode": settings.privacy_disclosure_synthetic_test_mode,
        "privacy_legal_approval_reference": settings.privacy_legal_approval_reference,
        "privacy_disclosure_config_reference": settings.privacy_disclosure_config_reference,
        "privacy_query_history_retention_reference": (
            settings.privacy_query_history_retention_reference
        ),
        "privacy_min_vehicles_per_cell": settings.privacy_min_vehicles_per_cell,
        "privacy_min_trips_per_cell": settings.privacy_min_trips_per_cell,
        "privacy_min_days_per_cell": settings.privacy_min_days_per_cell,
        "privacy_max_contributor_share": settings.privacy_max_contributor_share,
        "privacy_min_resolution_m": settings.privacy_min_resolution_m,
        "measurement_live_issuance_authorized": (settings.measurement_live_issuance_authorized),
        "measurement_report_method_reference": settings.measurement_report_method_reference,
        "measurement_roi_method_reference": settings.measurement_roi_method_reference,
    }


def _validate_frozen_run(run: MeasurementRun) -> MeasurementResultRead:
    if not measurement_run_reproducible(run):
        raise _error(
            "REPORT_MEASUREMENT_INTEGRITY_FAILURE",
            "The frozen measurement run failed reproducibility verification",
            status.HTTP_409_CONFLICT,
        )
    result = MeasurementResultRead.model_validate(run.result_manifest)
    if result.title != "Campaign Performance Analysis":
        raise _error(
            "REPORT_MEASUREMENT_INTEGRITY_FAILURE",
            "The frozen measurement result has an unsupported report identity",
            status.HTTP_409_CONFLICT,
        )
    if run.mode == "performance_only":
        valid = (
            result.roi is None
            and result.roi_gate.decision == "OMIT"
            and run.roi_method_revision is None
        )
    else:
        valid = (
            result.roi is not None
            and result.roi_gate.decision == "INCLUDE"
            and run.roi_method_revision == result.roi.method_revision
        )
    if not valid:
        raise _error(
            "REPORT_ROI_DECISION_INCONSISTENT",
            "The frozen report and financial-result decision do not agree",
            status.HTTP_409_CONFLICT,
        )
    return result


async def _authorize_scope(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    organization_id: UUID,
    campaign_id: UUID,
    write: bool,
) -> User:
    user = await session.scalar(select(User).where(User.id == actor_user_id).with_for_update())
    organization = await session.scalar(
        select(AdvertiserOrganization)
        .where(AdvertiserOrganization.id == organization_id)
        .with_for_update()
    )
    campaign = await session.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id, Campaign.organization_id == organization_id)
        .with_for_update()
    )
    if (
        user is None
        or user.status != UserStatus.ACTIVE
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
    )
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        raise _not_found()
    if write and membership.role not in {MembershipRole.OWNER, MembershipRole.MANAGER}:
        raise _error(
            "REPORT_ISSUANCE_ROLE_FORBIDDEN",
            "Owner or manager access is required for report issuance",
            status.HTTP_403_FORBIDDEN,
        )
    return user


async def _lock_key(session: AsyncSession, label: str) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    digest = hashlib.sha256(label.encode()).digest()[:8]
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(digest, "big", signed=True)},
    )


def _completeness_snapshot(completeness) -> dict[str, object]:
    return {
        "cohort_trip_count": completeness.cohort_trip_count,
        "denominator_trip_count": completeness.denominator_trip_count,
        "in_progress_trip_count": completeness.in_progress_trip_count,
        "covered_trip_count": completeness.covered_trip_count,
        "insufficient_data_trip_count": completeness.insufficient_data_trip_count,
        "excluded_trip_count": completeness.excluded_trip_count,
        "complete": completeness.complete,
        "suppressed": completeness.suppressed,
        "statement": (
            f"{completeness.covered_trip_count} of {completeness.denominator_trip_count} "
            f"completed trips covered; {completeness.insufficient_data_trip_count} "
            f"insufficient-data and {completeness.excluded_trip_count} excluded trips are not "
            f"zero-filled; {completeness.in_progress_trip_count} trips were still in progress."
        ),
    }


def _metric_snapshot(result: MeasurementResultRead) -> list[dict[str, object]]:
    metrics: list[dict[str, object]] = []
    for metric in result.metrics:
        density_provenance = None
        if metric.id == "verified_vehicle_movement":
            values = [
                {"label": "Trip count", "value": str(metric.trip_count), "unit": "trips"},
                {
                    "label": "Distance",
                    "value": (
                        SUPPRESSED_TOTAL_LABEL if metric.distance_m is None else metric.distance_m
                    ),
                    "unit": "metres",
                },
                {
                    "label": "Active tracking time",
                    "value": (
                        SUPPRESSED_TOTAL_LABEL
                        if metric.active_tracking_seconds is None
                        else str(metric.active_tracking_seconds)
                    ),
                    "unit": "seconds",
                },
            ]
        elif metric.id == "modelled_potential_contacts":
            values = [
                {
                    "label": "Value",
                    "value": SUPPRESSED_TOTAL_LABEL if metric.value is None else metric.value,
                    "unit": "modelled contacts",
                }
            ]
            density_provenance = {
                "source": metric.density_provenance.source,
                "calibration": metric.density_provenance.calibration,
                "profiles": [
                    profile.model_dump() for profile in metric.density_provenance.profiles
                ],
            }
        else:
            values = [
                {"label": total.currency, "value": total.value, "unit": total.currency}
                for total in metric.totals_by_currency
            ]
        item: dict[str, object] = {
            "id": metric.id,
            "label": metric.label,
            "class": metric.metric_class,
            "values": values,
            "completeness": _completeness_snapshot(metric.completeness),
        }
        uncertainty = getattr(metric, "uncertainty", None)
        if uncertainty:
            item["uncertainty"] = uncertainty
        if density_provenance is not None:
            item["density_provenance"] = density_provenance
        metrics.append(item)
    return metrics


async def _compose_snapshot(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    run: MeasurementRun,
    settings: Settings,
    admin: bool,
) -> dict[str, object]:
    result = _validate_frozen_run(run)
    authority_fingerprint = canonical_sha256(_authority_document(run, settings))
    score = await session.scalar(
        select(ExposureScore)
        .where(ExposureScore.measurement_run_id == run.id)
        .order_by(ExposureScore.created_at.desc(), ExposureScore.id.desc())
        .limit(1)
    )
    if score is None:
        raise _error(
            "REPORT_EXPOSURE_AUTHORITY_UNAVAILABLE",
            "The frozen report has no exposure-score authority",
            status.HTTP_409_CONFLICT,
        )
    from app.services.exposure_scores import (
        advertiser_exposure_score_read,
        exposure_score_is_stale,
    )

    if await exposure_score_is_stale(session, score):
        raise _error(
            "REPORT_EXPOSURE_AUTHORITY_UNAVAILABLE",
            "The frozen exposure score no longer matches the measurement run",
            status.HTTP_409_CONFLICT,
        )
    advertiser_score = await advertiser_exposure_score_read(session, score)
    from app.services.audience import high_exposure_zone_insights

    insights = await high_exposure_zone_insights(
        session,
        settings=settings,
        actor_user_id=actor_user_id,
        campaign_id=run.campaign_id,
        measurement_run_id=run.id,
        admin=admin,
    )
    if insights.state in {"stale", "unavailable"}:
        raise _error(
            "REPORT_DISCLOSURE_AUTHORITY_UNAVAILABLE",
            "The governed disclosure projection is unavailable",
            status.HTTP_409_CONFLICT,
        )
    provenance = insights.provenance
    exposure = {
        "state": insights.state,
        "score": advertiser_score.result.score,
        "zones": [
            {
                "rank": item.rank,
                "label": item.zone_name,
                "modelled_potential_contacts": str(item.modelled_potential_contacts),
                "trip_count": item.trip_count,
            }
            for item in insights.items
        ]
        if insights.state == "ready"
        else [],
        "formula_version": advertiser_score.formula_version,
        "formula_fingerprint": advertiser_score.formula_fingerprint,
        "input_fingerprint": advertiser_score.input_fingerprint,
        "segment_snapshot_hashes": sorted(
            item.segment_snapshot_sha256 for item in provenance.source_segments
        )
        if provenance is not None
        else [],
        "disclaimer": insights.disclaimer,
        "uncertainty": insights.uncertainty,
        "authority_fingerprint": authority_fingerprint,
    }
    snapshot: dict[str, object] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "title": result.title,
        "synthetic": run.test_only,
        "creation_authority": "administrator" if admin else "advertiser_owner_or_manager",
        "measurement": {
            "run_id": str(run.id),
            "input_sha256": run.input_manifest_sha256,
            "result_sha256": run.result_manifest_sha256,
            "proof_sha256": run.proof_manifest_sha256,
            "report_sha256": run.report_snapshot_sha256,
            "formula_version": run.formula_version,
            "method_revision": run.method_revision,
            "period_start_at": run.period_start_at.isoformat(),
            "period_end_at": run.period_end_at.isoformat(),
        },
        "metrics": _metric_snapshot(result),
        "exposure": exposure,
    }
    if result.roi_gate.decision == "INCLUDE" and result.roi is not None:
        snapshot["financial_result"] = {
            "label": result.roi.label,
            "class": result.roi.metric_class,
            "ratio": result.roi.ratio,
            "percent": result.roi.percent,
            "currency": result.roi.currency,
            "method_revision": result.roi.method_revision,
            "method": result.roi.method.model_dump(),
            "provenance": result.roi.provenance.model_dump(),
        }
    return snapshot


async def request_report_issuance(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    measurement_run_id: UUID,
    payload: ReportIssuanceCreate,
    settings: Settings,
    admin: bool,
) -> ReportIssuance:
    run = await session.scalar(
        select(MeasurementRun).where(MeasurementRun.id == measurement_run_id).with_for_update()
    )
    if run is None:
        raise _not_found()
    await _authorize_scope(
        session,
        actor_user_id=actor_user_id,
        organization_id=run.organization_id,
        campaign_id=run.campaign_id,
        write=True,
    )
    await _lock_key(session, f"report-request:{actor_user_id}:{payload.client_request_id}")
    replay = await session.scalar(
        select(ReportIssuance).where(
            ReportIssuance.requested_by_user_id == actor_user_id,
            ReportIssuance.client_request_id == payload.client_request_id,
        )
    )
    if replay is not None:
        if replay.measurement_run_id != run.id or replay.reissue_of_id != payload.reissue_of_id:
            raise _error(
                "REPORT_ISSUANCE_REQUEST_CONFLICT",
                "The client request id was reused with different report parameters",
                status.HTTP_409_CONFLICT,
            )
        _validate_frozen_run(run)
        _authority_document(run, settings)
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="report_issuance.replayed",
            entity_type="report_issuance",
            entity_id=str(replay.id),
            metadata={"version": replay.version, "status": replay.status},
        )
        return replay
    snapshot = await _compose_snapshot(
        session,
        actor_user_id=actor_user_id,
        run=run,
        settings=settings,
        admin=admin,
    )
    snapshot_sha256 = canonical_sha256(snapshot)
    authority_fingerprint = snapshot["exposure"]["authority_fingerprint"]
    request_fingerprint = canonical_sha256(
        {
            "measurement_run_id": str(run.id),
            "reissue_of_id": str(payload.reissue_of_id) if payload.reissue_of_id else None,
            "snapshot_sha256": snapshot_sha256,
            "authority_fingerprint": authority_fingerprint,
            "schema_version": REPORT_SCHEMA_VERSION,
            "renderer_version": REPORT_RENDERER_VERSION,
        }
    )
    await _lock_key(session, f"report-lineage:{run.id}")
    latest = await session.scalar(
        select(ReportIssuance)
        .where(ReportIssuance.measurement_run_id == run.id)
        .order_by(ReportIssuance.version.desc())
        .limit(1)
        .with_for_update()
    )
    if payload.reissue_of_id is None:
        if latest is not None:
            raise _error(
                "REPORT_REISSUE_PARENT_REQUIRED",
                "An explicit current issuance parent is required for reissue",
                status.HTTP_409_CONFLICT,
            )
        version = 1
        parent = None
    else:
        parent = await session.scalar(
            select(ReportIssuance)
            .where(
                ReportIssuance.id == payload.reissue_of_id,
                ReportIssuance.measurement_run_id == run.id,
            )
            .with_for_update()
        )
        if (
            parent is None
            or parent.status not in {ReportIssuanceStatus.READY, ReportIssuanceStatus.FAILED}
            or latest is None
            or latest.id != parent.id
        ):
            raise _error(
                "REPORT_REISSUE_PARENT_INVALID",
                "The reissue parent must be the current ready or failed issuance",
                status.HTTP_409_CONFLICT,
            )
        version = parent.version + 1
    result = MeasurementResultRead.model_validate(run.result_manifest)
    issuance = ReportIssuance(
        organization_id=run.organization_id,
        campaign_id=run.campaign_id,
        measurement_run_id=run.id,
        requested_by_user_id=actor_user_id,
        client_request_id=payload.client_request_id,
        request_fingerprint=request_fingerprint,
        reissue_of_id=parent.id if parent is not None else None,
        version=version,
        snapshot=snapshot,
        snapshot_sha256=snapshot_sha256,
        authority_fingerprint=authority_fingerprint,
        input_manifest_sha256=run.input_manifest_sha256,
        result_manifest_sha256=run.result_manifest_sha256,
        proof_manifest_sha256=run.proof_manifest_sha256,
        report_snapshot_sha256=run.report_snapshot_sha256,
        schema_version=REPORT_SCHEMA_VERSION,
        renderer_version=REPORT_RENDERER_VERSION,
        method_revision=run.method_revision,
        roi_decision=result.roi_gate.decision,
        synthetic=run.test_only,
        status=ReportIssuanceStatus.QUEUED,
    )
    session.add(issuance)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="report_issuance.requested",
        entity_type="report_issuance",
        entity_id=str(issuance.id),
        metadata={
            "version": issuance.version,
            "synthetic": issuance.synthetic,
            "snapshot_sha256": issuance.snapshot_sha256,
            "result_manifest_sha256": issuance.result_manifest_sha256,
        },
    )
    return issuance


def _filename(issuance: ReportIssuance, artifact_format: str) -> str:
    return f"cardvert-campaign-performance-analysis-v{issuance.version}.{artifact_format}"


async def report_issuance_read(
    session: AsyncSession, issuance: ReportIssuance
) -> ReportIssuanceRead:
    artifacts = list(
        (
            await session.scalars(
                select(ReportArtifact)
                .where(ReportArtifact.report_issuance_id == issuance.id)
                .order_by(ReportArtifact.format)
            )
        ).all()
    )
    return ReportIssuanceRead(
        id=issuance.id,
        measurement_run_id=issuance.measurement_run_id,
        campaign_id=issuance.campaign_id,
        version=issuance.version,
        reissue_of_id=issuance.reissue_of_id,
        status=issuance.status,
        synthetic=issuance.synthetic,
        schema_version=issuance.schema_version,
        renderer_version=issuance.renderer_version,
        worker_attempts=issuance.worker_attempts,
        error_code=issuance.last_error_code
        if issuance.status == ReportIssuanceStatus.FAILED
        else None,
        artifacts=[
            ReportArtifactRead(
                format=artifact.format,
                filename=_filename(issuance, artifact.format),
                content_type=artifact.content_type,
                size_bytes=artifact.size_bytes,
                checksum_sha256=artifact.checksum_sha256,
            )
            for artifact in artifacts
        ]
        if issuance.status == ReportIssuanceStatus.READY
        else [],
        created_at=issuance.created_at,
        ready_at=issuance.ready_at,
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
    if run is None or not measurement_run_reproducible(run):
        raise _not_found()
    try:
        authority_fingerprint = canonical_sha256(_authority_document(run, settings))
    except AppError as exc:
        raise _not_found() from exc
    if authority_fingerprint != issuance.authority_fingerprint:
        raise _not_found()
    return issuance


def _rendered_artifacts(issuance: ReportIssuance) -> tuple[_RenderedArtifact, ...]:
    render_snapshot = {
        **issuance.snapshot,
        "issuance": {
            "id": str(issuance.id),
            "version": issuance.version,
            "schema_version": issuance.schema_version,
            "renderer_version": issuance.renderer_version,
            "created_at": issuance.created_at.isoformat(),
            "creation_authority": issuance.snapshot["creation_authority"],
        },
    }
    csv_content = render_report_csv(render_snapshot)
    pdf_content = render_report_pdf(render_snapshot)
    result = []
    for artifact_format, content_type, content in (
        (ReportArtifactFormat.CSV, "text/csv", csv_content),
        (ReportArtifactFormat.PDF, "application/pdf", pdf_content),
    ):
        result.append(
            _RenderedArtifact(
                format=artifact_format,
                content_type=content_type,
                filename=_filename(issuance, artifact_format.value),
                storage_key=(
                    f"managed/{issuance.organization_id}/reports/{issuance.id}/"
                    f"artifact.{artifact_format.value}"
                ),
                content=content,
                checksum_sha256=hashlib.sha256(content).hexdigest(),
            )
        )
    return tuple(result)


async def _record_worker_failure(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    issuance_id: UUID,
    token: UUID,
    error_code: str,
) -> None:
    async with sessionmaker() as session:
        issuance = await session.scalar(
            select(ReportIssuance).where(ReportIssuance.id == issuance_id).with_for_update()
        )
        if (
            issuance is None
            or issuance.status != ReportIssuanceStatus.PROCESSING
            or issuance.processing_token != token
        ):
            return
        now = await database_clock(session)
        terminal = issuance.worker_attempts >= REPORT_MAX_ATTEMPTS
        issuance.status = ReportIssuanceStatus.FAILED if terminal else ReportIssuanceStatus.QUEUED
        issuance.processing_token = None
        issuance.lease_expires_at = None
        issuance.ready_at = None
        issuance.last_error_code = error_code
        issuance.next_attempt_at = (
            None
            if terminal
            else now + timedelta(seconds=30 * (2 ** (issuance.worker_attempts - 1)))
        )
        await create_audit_event(
            session,
            actor_user_id=None,
            action="report_issuance.failed" if terminal else "report_issuance.retry_scheduled",
            entity_type="report_issuance",
            entity_id=str(issuance.id),
            metadata={"attempt": issuance.worker_attempts, "error_code": error_code},
        )
        await session.commit()


async def _generate_and_publish(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    storage: StorageProvider,
    settings: Settings,
    issuance_id: UUID,
    token: UUID,
) -> None:
    try:
        async with sessionmaker() as session:
            issuance = await session.get(ReportIssuance, issuance_id)
            if (
                issuance is None
                or issuance.status != ReportIssuanceStatus.PROCESSING
                or issuance.processing_token != token
            ):
                return
            run = await session.get(MeasurementRun, issuance.measurement_run_id)
            if run is None:
                raise _error(
                    "REPORT_SOURCE_RUN_UNAVAILABLE",
                    "The frozen measurement run is unavailable",
                    status.HTTP_409_CONFLICT,
                )
            await _authorize_scope(
                session,
                actor_user_id=issuance.requested_by_user_id,
                organization_id=issuance.organization_id,
                campaign_id=issuance.campaign_id,
                write=True,
            )
            _validate_frozen_run(run)
            if (
                run.input_manifest_sha256 != issuance.input_manifest_sha256
                or run.result_manifest_sha256 != issuance.result_manifest_sha256
                or run.proof_manifest_sha256 != issuance.proof_manifest_sha256
                or run.report_snapshot_sha256 != issuance.report_snapshot_sha256
                or canonical_sha256(issuance.snapshot) != issuance.snapshot_sha256
                or canonical_sha256(_authority_document(run, settings))
                != issuance.authority_fingerprint
            ):
                raise _error(
                    "REPORT_FROZEN_AUTHORITY_MISMATCH",
                    "The queued report no longer matches its frozen authority",
                    status.HTTP_409_CONFLICT,
                )
            rendered = _rendered_artifacts(issuance)
        for artifact in rendered:
            observed = await storage.put(
                object_key=artifact.storage_key,
                content_type=artifact.content_type,
                data=artifact.content,
                checksum_sha256=artifact.checksum_sha256,
            )
            if (
                observed.object_key != artifact.storage_key
                or observed.content_type.lower() != artifact.content_type
                or observed.size_bytes != len(artifact.content)
                or observed.checksum_sha256.lower() != artifact.checksum_sha256
            ):
                raise StorageObjectConflict("Generated report object metadata mismatch")
        async with sessionmaker() as session:
            issuance = await session.scalar(
                select(ReportIssuance).where(ReportIssuance.id == issuance_id).with_for_update()
            )
            if (
                issuance is None
                or issuance.status != ReportIssuanceStatus.PROCESSING
                or issuance.processing_token != token
            ):
                return
            run = await session.get(MeasurementRun, issuance.measurement_run_id)
            if run is None:
                raise _error(
                    "REPORT_SOURCE_RUN_UNAVAILABLE",
                    "The frozen measurement run is unavailable",
                    status.HTTP_409_CONFLICT,
                )
            await _authorize_scope(
                session,
                actor_user_id=issuance.requested_by_user_id,
                organization_id=issuance.organization_id,
                campaign_id=issuance.campaign_id,
                write=True,
            )
            if (
                canonical_sha256(_authority_document(run, settings))
                != issuance.authority_fingerprint
            ):
                raise _error(
                    "REPORT_AUTHORITY_REVOKED",
                    "Report publication authority is no longer current",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            existing_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ReportArtifact)
                    .where(ReportArtifact.report_issuance_id == issuance.id)
                )
                or 0
            )
            if existing_count:
                raise _error(
                    "REPORT_ARTIFACT_STATE_CONFLICT",
                    "The report artifact pair is not publishable",
                    status.HTTP_409_CONFLICT,
                )
            now = await database_clock(session)
            for artifact in rendered:
                stored_file = StoredFile(
                    upload_intent_id=None,
                    organization_id=issuance.organization_id,
                    subject_user_id=None,
                    uploader_user_id=issuance.requested_by_user_id,
                    purpose=FilePurpose.REPORT_EXPORT,
                    original_filename=artifact.filename,
                    storage_key=artifact.storage_key,
                    content_type=artifact.content_type,
                    size_bytes=len(artifact.content),
                    checksum_sha256=artifact.checksum_sha256,
                    scan_status=FileScanStatus.CLEAN,
                    actual_content_type=artifact.content_type,
                    scan_attempts=0,
                    scanned_at=now,
                )
                session.add(stored_file)
                await session.flush()
                session.add(
                    ReportArtifact(
                        report_issuance_id=issuance.id,
                        stored_file_id=stored_file.id,
                        format=artifact.format,
                        content_type=artifact.content_type,
                        size_bytes=len(artifact.content),
                        checksum_sha256=artifact.checksum_sha256,
                        renderer_version=REPORT_RENDERER_VERSION,
                    )
                )
            issuance.status = ReportIssuanceStatus.READY
            issuance.processing_token = None
            issuance.lease_expires_at = None
            issuance.next_attempt_at = None
            issuance.last_error_code = None
            issuance.ready_at = now
            await create_audit_event(
                session,
                actor_user_id=None,
                action="report_issuance.ready",
                entity_type="report_issuance",
                entity_id=str(issuance.id),
                metadata={
                    "version": issuance.version,
                    "artifact_hashes": {
                        artifact.format.value: artifact.checksum_sha256 for artifact in rendered
                    },
                },
            )
            await session.commit()
    except AppError as exc:
        await _record_worker_failure(
            sessionmaker,
            issuance_id=issuance_id,
            token=token,
            error_code=exc.code,
        )
    except ReportRenderLimitError:
        await _record_worker_failure(
            sessionmaker,
            issuance_id=issuance_id,
            token=token,
            error_code="report_render_limit",
        )
    except StorageObjectConflict:
        await _record_worker_failure(
            sessionmaker,
            issuance_id=issuance_id,
            token=token,
            error_code="stored_object_conflict",
        )
    except (StorageObjectNotFound, StorageUnavailable):
        await _record_worker_failure(
            sessionmaker,
            issuance_id=issuance_id,
            token=token,
            error_code="storage_unavailable",
        )


async def sweep_report_issuances(ctx: dict) -> int:
    sessionmaker: async_sessionmaker[AsyncSession] = ctx["sessionmaker"]
    settings: Settings = ctx["settings"]
    storage: StorageProvider = ctx["storage"]
    claims: list[tuple[UUID, UUID]] = []
    async with sessionmaker() as session:
        now = await database_clock(session)
        rows = list(
            (
                await session.scalars(
                    select(ReportIssuance)
                    .where(
                        or_(
                            and_(
                                ReportIssuance.status == ReportIssuanceStatus.QUEUED,
                                or_(
                                    ReportIssuance.next_attempt_at.is_(None),
                                    ReportIssuance.next_attempt_at <= now,
                                ),
                            ),
                            and_(
                                ReportIssuance.status == ReportIssuanceStatus.PROCESSING,
                                ReportIssuance.lease_expires_at <= now,
                            ),
                        )
                    )
                    .order_by(ReportIssuance.created_at, ReportIssuance.id)
                    .limit(settings.worker_sweep_batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for issuance in rows:
            token = uuid4()
            issuance.status = ReportIssuanceStatus.PROCESSING
            issuance.worker_attempts += 1
            issuance.processing_token = token
            issuance.lease_expires_at = now + timedelta(seconds=REPORT_LEASE_SECONDS)
            issuance.next_attempt_at = None
            issuance.last_error_code = None
            claims.append((issuance.id, token))
            await create_audit_event(
                session,
                actor_user_id=None,
                action="report_issuance.worker_claimed",
                entity_type="report_issuance",
                entity_id=str(issuance.id),
                metadata={"attempt": issuance.worker_attempts},
            )
        await session.commit()
    for issuance_id, token in claims:
        await _generate_and_publish(
            sessionmaker,
            storage=storage,
            settings=settings,
            issuance_id=issuance_id,
            token=token,
        )
    return len(claims)


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

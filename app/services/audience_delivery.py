from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.audience_delivery import AudienceDelivery
from app.models.campaign import Campaign
from app.models.campaign_zone import CampaignZone
from app.models.exposure_segment import ExposureSegment, ExposureSegmentCell
from app.models.measurement import MeasurementRun
from app.models.retargeting_source import RetargetingSource
from app.models.retargeting_source_link import RetargetingSourceLink
from app.schemas.audience_delivery import (
    AggregateActivationPayload,
    AggregateRecommendation,
    AggregateTarget,
    AudienceActivationRead,
    AudienceExportRead,
    RecommendationProvenance,
    RecommendationsRead,
)
from app.services.audience import (
    _active_admin,
    _advertiser_membership,
    _as_utc,
    _link_access,
    _privacy_gate,
    exposure_segment_is_stale,
)
from app.services.audit import create_audit_event
from app.services.disclosure import exposure_cell_meets_disclosure_floor
from app.services.payout_rule_serialization import database_clock

RECOMMENDATION_DISCLAIMER = (
    "Modelled potential contacts are estimates, not observed people or guaranteed outcomes. "
    "Use these recommendations only for aggregate geography, time-window and contextual "
    "campaign planning."
)


@dataclass(frozen=True)
class AdPlatformActivationRequest:
    idempotency_key: str
    payload: AggregateActivationPayload


@dataclass(frozen=True)
class AdPlatformActivationResult:
    provider_reference: str


class AdPlatformAdapter(Protocol):
    name: str
    enabled: bool
    synthetic: bool

    async def activate(
        self, request: AdPlatformActivationRequest
    ) -> AdPlatformActivationResult: ...


class DisabledAdPlatformAdapter:
    name = "disabled"
    enabled = False
    synthetic = False

    async def activate(
        self, request: AdPlatformActivationRequest
    ) -> AdPlatformActivationResult:
        del request
        raise RuntimeError("disabled ad-platform adapter cannot be invoked")


class FakeAdPlatformAdapter:
    name = "synthetic-fake-ad-platform"
    enabled = True
    synthetic = True

    def __init__(self) -> None:
        self.calls: list[AdPlatformActivationRequest] = []

    async def activate(
        self, request: AdPlatformActivationRequest
    ) -> AdPlatformActivationResult:
        self.calls.append(request)
        return AdPlatformActivationResult(
            provider_reference=f"fake-activation-{request.idempotency_key}"
        )


def build_ad_platform_adapter() -> AdPlatformAdapter:
    # EXT-AD-PLATFORM is deliberately absent. No environment value can turn a
    # live provider on until the external facts and a concrete adapter ship.
    return DisabledAdPlatformAdapter()


def _canonical_hash(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def _delivery_lock(
    session: AsyncSession, *, actor_user_id: UUID, operation: str, idempotency_key: str
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    digest = hashlib.sha256(
        f"audience-delivery-v1:{actor_user_id}:{operation}:{idempotency_key}".encode()
    ).digest()[:8]
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(digest, "big", signed=True)},
    )


async def _delivery_replay(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    operation: str,
    idempotency_key: str,
    request_fingerprint: str,
) -> AudienceDelivery | None:
    delivery = await session.scalar(
        select(AudienceDelivery).where(
            AudienceDelivery.actor_user_id == actor_user_id,
            AudienceDelivery.operation == operation,
            AudienceDelivery.idempotency_key == idempotency_key,
        )
    )
    if delivery is None:
        return None
    if delivery.request_fingerprint != request_fingerprint:
        raise AppError(
            "AUDIENCE_DELIVERY_IDEMPOTENCY_CONFLICT",
            "Idempotency key was reused with different governed aggregate facts",
            status_code=status.HTTP_409_CONFLICT,
        )
    return delivery


async def _segment_access(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: UUID,
    segment_id: UUID,
    write: bool,
    admin: bool,
) -> tuple[ExposureSegment, RetargetingSourceLink]:
    await _privacy_gate(settings)
    organization_id: UUID | None = None
    if admin:
        await _active_admin(session, actor_user_id)
    else:
        organization_id = (
            await _advertiser_membership(
                session, actor_user_id=actor_user_id, write=write
            )
        ).organization_id
    statement = select(ExposureSegment).where(ExposureSegment.id == segment_id)
    if organization_id is not None:
        statement = statement.where(ExposureSegment.organization_id == organization_id)
    segment = await session.scalar(statement)
    if segment is None:
        raise AppError(
            "EXPOSURE_SEGMENT_NOT_FOUND",
            "Exposure segment was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    # Mutations follow W3-01B's source -> campaign -> zone -> link authority
    # order. Parent locks make the authorization/staleness decision stable
    # until the immutable delivery receipt commits.
    parent_ids = (
        (RetargetingSource, segment.source_id),
        (Campaign, segment.campaign_id),
        (CampaignZone, segment.zone_id),
        (RetargetingSourceLink, segment.source_link_id),
    )
    parents = []
    for model, parent_id in parent_ids:
        parent_statement = select(model).where(model.id == parent_id)
        if write:
            parent_statement = parent_statement.with_for_update()
        parents.append(await session.scalar(parent_statement))
    source, campaign, zone, link = parents
    if (
        source is None
        or campaign is None
        or zone is None
        or link is None
        or link.organization_id != segment.organization_id
        or link.campaign_id != segment.campaign_id
        or link.zone_id != segment.zone_id
        or link.source_id != segment.source_id
        or source.organization_id != segment.organization_id
        or campaign.organization_id != segment.organization_id
        or zone.campaign_id != segment.campaign_id
    ):
        raise AppError(
            "EXPOSURE_SEGMENT_SCOPE_MISMATCH",
            "Exposure segment tenant and campaign authority did not match",
            status_code=status.HTTP_409_CONFLICT,
        )
    return segment, link


async def _governed_cells(
    session: AsyncSession, *, segment: ExposureSegment, settings: Settings
) -> list[ExposureSegmentCell]:
    rows = list(
        await session.scalars(
            select(ExposureSegmentCell)
            .where(ExposureSegmentCell.segment_id == segment.id)
            .order_by(
                ExposureSegmentCell.coverage_cell,
                ExposureSegmentCell.window_start_at,
                ExposureSegmentCell.window_end_at,
            )
        )
    )
    return [
        row
        for row in rows
        if exposure_cell_meets_disclosure_floor(
            distinct_vehicle_count=row.distinct_vehicle_count, settings=settings
        )
    ]


def _measurement_uncertainty(run: MeasurementRun) -> str:
    metrics = run.result_manifest.get("metrics")
    if isinstance(metrics, list):
        for metric in metrics:
            if (
                isinstance(metric, dict)
                and metric.get("id") == "modelled_potential_contacts"
                and isinstance(metric.get("uncertainty"), str)
                and metric["uncertainty"].strip()
            ):
                return metric["uncertainty"]
    raise AppError(
        "AUDIENCE_RECOMMENDATION_UNCERTAINTY_MISSING",
        "The immutable measurement run has no model uncertainty statement",
        status_code=status.HTTP_409_CONFLICT,
    )


def _provenance(segment: ExposureSegment) -> RecommendationProvenance:
    return RecommendationProvenance(
        segment_id=segment.id,
        segment_version=segment.version,
        segment_snapshot_sha256=segment.snapshot_sha256,
        source_link_id=segment.source_link_id,
        source_link_snapshot_sha256=segment.source_link_snapshot_sha256,
        measurement_run_id=segment.measurement_run_id,
        measurement_input_sha256=segment.measurement_input_sha256,
        measurement_result_sha256=segment.measurement_result_sha256,
        measurement_proof_sha256=segment.measurement_proof_sha256,
    )


async def _recommendations_for_segment(
    session: AsyncSession,
    *,
    segment: ExposureSegment,
    link: RetargetingSourceLink,
    settings: Settings,
) -> RecommendationsRead:
    if link.status != "active" or await exposure_segment_is_stale(session, segment):
        return RecommendationsRead(
            state="stale",
            segment_id=segment.id,
            campaign_id=segment.campaign_id,
            recommendations=[],
            provenance=None,
            disclaimer=RECOMMENDATION_DISCLAIMER,
            uncertainty=None,
        )
    run = await session.get(MeasurementRun, segment.measurement_run_id)
    if run is None:
        raise AppError(
            "EXPOSURE_SEGMENT_MEASUREMENT_RUN_NOT_FOUND",
            "The immutable measurement run was not found",
            status_code=status.HTTP_409_CONFLICT,
        )
    cells = await _governed_cells(session, segment=segment, settings=settings)
    ranked = sorted(
        cells,
        key=lambda row: (
            -row.modelled_potential_contacts,
            -row.trip_count,
            row.coverage_cell,
            row.window_start_at,
        ),
    )
    state = "ready" if ranked else "suppressed"
    return RecommendationsRead(
        state=state,
        segment_id=segment.id,
        campaign_id=segment.campaign_id,
        recommendations=[
            AggregateRecommendation(
                rank=rank,
                coverage_cell=row.coverage_cell,
                window_start_at=_as_utc(row.window_start_at),
                window_end_at=_as_utc(row.window_end_at),
                campaign_context="vehicle_transit",
                rationale=(
                    "Prioritize this aggregate cell and time window because it has the "
                    "strongest governed modelled contact signal in this issued segment."
                ),
            )
            for rank, row in enumerate(ranked, start=1)
        ],
        provenance=_provenance(segment),
        disclaimer=RECOMMENDATION_DISCLAIMER,
        uncertainty=_measurement_uncertainty(run),
    )


async def recommendations_for_link(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: UUID,
    source_link_id: UUID,
    admin: bool = False,
) -> RecommendationsRead:
    link = await _link_access(
        session,
        settings=settings,
        actor_user_id=actor_user_id,
        link_id=source_link_id,
        write=False,
        admin=admin,
    )
    segment = await session.scalar(
        select(ExposureSegment)
        .where(ExposureSegment.source_link_id == link.id)
        .order_by(ExposureSegment.version.desc())
        .limit(1)
    )
    if segment is None:
        return RecommendationsRead(
            state="empty",
            segment_id=None,
            campaign_id=link.campaign_id,
            recommendations=[],
            provenance=None,
            disclaimer=RECOMMENDATION_DISCLAIMER,
            uncertainty=None,
        )
    return await _recommendations_for_segment(
        session, segment=segment, link=link, settings=settings
    )


async def _outbound_payload(
    session: AsyncSession,
    *,
    segment: ExposureSegment,
    link: RetargetingSourceLink,
    settings: Settings,
) -> AggregateActivationPayload:
    if link.status != "active" or await exposure_segment_is_stale(session, segment):
        raise AppError(
            "EXPOSURE_SEGMENT_STALE",
            "A current exposure segment is required for export or activation",
            status_code=status.HTTP_409_CONFLICT,
        )
    cells = await _governed_cells(session, segment=segment, settings=settings)
    if not cells:
        raise AppError(
            "AUDIENCE_AGGREGATE_SUPPRESSED",
            "No aggregate cells satisfy the current disclosure floor",
            status_code=status.HTTP_409_CONFLICT,
        )
    return AggregateActivationPayload(
        schema_version="aggregate-contextual-activation-v1",
        campaign_id=segment.campaign_id,
        campaign_context="vehicle_transit",
        targets=[
            AggregateTarget(
                coverage_cell=row.coverage_cell,
                window_start_at=_as_utc(row.window_start_at),
                window_end_at=_as_utc(row.window_end_at),
                context="vehicle_transit",
            )
            for row in cells
        ],
    )


def _csv_content(payload: AggregateActivationPayload) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=(
            "campaign_id",
            "coverage_cell",
            "window_start_at",
            "window_end_at",
            "campaign_context",
        ),
        lineterminator="\n",
    )
    writer.writeheader()
    for target in payload.targets:
        writer.writerow(
            {
                "campaign_id": str(payload.campaign_id),
                "coverage_cell": target.coverage_cell,
                "window_start_at": target.window_start_at.isoformat(),
                "window_end_at": target.window_end_at.isoformat(),
                "campaign_context": target.context,
            }
        )
    return stream.getvalue()


def _delivery_id(actor_user_id: UUID, operation: str, idempotency_key: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"cardvert-audience-delivery-v1:{actor_user_id}:{operation}:{idempotency_key}",
    )


async def export_exposure_segment(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: UUID,
    segment_id: UUID,
    idempotency_key: str,
) -> AudienceExportRead:
    segment, link = await _segment_access(
        session,
        settings=settings,
        actor_user_id=actor_user_id,
        segment_id=segment_id,
        write=True,
        admin=False,
    )
    payload = await _outbound_payload(
        session, segment=segment, link=link, settings=settings
    )
    payload_dict = payload.model_dump(mode="json")
    payload_sha256 = _canonical_hash(payload_dict)
    request_fingerprint = _canonical_hash(
        {"segment_id": str(segment.id), "payload_sha256": payload_sha256}
    )
    await _delivery_lock(
        session,
        actor_user_id=actor_user_id,
        operation="csv_export",
        idempotency_key=idempotency_key,
    )
    replay = await _delivery_replay(
        session,
        actor_user_id=actor_user_id,
        operation="csv_export",
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if replay is not None:
        return AudienceExportRead(
            id=replay.id,
            segment_id=replay.segment_id,
            operation="csv_export",
            payload_sha256=replay.payload_sha256,
            csv_content=replay.result["csv_content"],
            csv_sha256=replay.result["csv_sha256"],
            created_at=_as_utc(replay.created_at),
        )
    content = _csv_content(payload)
    result = {
        "csv_content": content,
        "csv_sha256": hashlib.sha256(content.encode()).hexdigest(),
    }
    now = await database_clock(session)
    delivery = AudienceDelivery(
        id=_delivery_id(actor_user_id, "csv_export", idempotency_key),
        organization_id=segment.organization_id,
        campaign_id=segment.campaign_id,
        segment_id=segment.id,
        actor_user_id=actor_user_id,
        operation="csv_export",
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        payload=payload_dict,
        payload_sha256=payload_sha256,
        result=result,
        result_sha256=_canonical_hash(result),
        adapter_name="controlled-csv-v1",
        synthetic=False,
        created_at=now,
    )
    session.add(delivery)
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="audience_segment.exported",
        entity_type="audience_delivery",
        entity_id=str(delivery.id),
        metadata={
            "organization_id": str(segment.organization_id),
            "campaign_id": str(segment.campaign_id),
            "segment_id": str(segment.id),
            "payload_sha256": payload_sha256,
        },
    )
    await session.flush()
    return AudienceExportRead(
        id=delivery.id,
        segment_id=delivery.segment_id,
        operation="csv_export",
        payload_sha256=delivery.payload_sha256,
        csv_content=result["csv_content"],
        csv_sha256=result["csv_sha256"],
        created_at=_as_utc(delivery.created_at),
    )


async def activate_exposure_segment(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: UUID,
    segment_id: UUID,
    idempotency_key: str,
    adapter: AdPlatformAdapter,
) -> AudienceActivationRead:
    segment, link = await _segment_access(
        session,
        settings=settings,
        actor_user_id=actor_user_id,
        segment_id=segment_id,
        write=True,
        admin=True,
    )
    payload = await _outbound_payload(
        session, segment=segment, link=link, settings=settings
    )
    payload_dict = payload.model_dump(mode="json")
    payload_sha256 = _canonical_hash(payload_dict)
    request_fingerprint = _canonical_hash(
        {"segment_id": str(segment.id), "payload_sha256": payload_sha256}
    )
    await _delivery_lock(
        session,
        actor_user_id=actor_user_id,
        operation="ad_platform_activation",
        idempotency_key=idempotency_key,
    )
    replay = await _delivery_replay(
        session,
        actor_user_id=actor_user_id,
        operation="ad_platform_activation",
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if replay is not None:
        return AudienceActivationRead(
            id=replay.id,
            segment_id=replay.segment_id,
            operation="ad_platform_activation",
            adapter_name=replay.adapter_name,
            provider_reference=replay.result["provider_reference"],
            payload_sha256=replay.payload_sha256,
            synthetic=replay.synthetic,
            created_at=_as_utc(replay.created_at),
        )
    if (
        not adapter.enabled
        or not adapter.synthetic
        or settings.environment not in {"test", "testing"}
        or not settings.privacy_disclosure_synthetic_test_mode
    ):
        raise AppError(
            "AD_PLATFORM_LIVE_ACTIVATION_BLOCKED",
            "Live aggregate activation is unavailable until EXT-AD-PLATFORM is complete",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    delivery_id = _delivery_id(
        actor_user_id, "ad_platform_activation", idempotency_key
    )
    submission = await adapter.activate(
        AdPlatformActivationRequest(
            idempotency_key=str(delivery_id), payload=payload
        )
    )
    result = {"provider_reference": submission.provider_reference}
    now = await database_clock(session)
    delivery = AudienceDelivery(
        id=delivery_id,
        organization_id=segment.organization_id,
        campaign_id=segment.campaign_id,
        segment_id=segment.id,
        actor_user_id=actor_user_id,
        operation="ad_platform_activation",
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        payload=payload_dict,
        payload_sha256=payload_sha256,
        result=result,
        result_sha256=_canonical_hash(result),
        adapter_name=adapter.name,
        synthetic=True,
        created_at=now,
    )
    session.add(delivery)
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="audience_segment.activation_submitted",
        entity_type="audience_delivery",
        entity_id=str(delivery.id),
        metadata={
            "organization_id": str(segment.organization_id),
            "campaign_id": str(segment.campaign_id),
            "segment_id": str(segment.id),
            "adapter_name": adapter.name,
            "payload_sha256": payload_sha256,
            "synthetic": True,
        },
    )
    await session.flush()
    return AudienceActivationRead(
        id=delivery.id,
        segment_id=delivery.segment_id,
        operation="ad_platform_activation",
        adapter_name=delivery.adapter_name,
        provider_reference=submission.provider_reference,
        payload_sha256=delivery.payload_sha256,
        synthetic=True,
        created_at=_as_utc(delivery.created_at),
    )

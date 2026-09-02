from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.adapters.ad_platforms import AdPlatformActivationRequest, AdPlatformAdapter
from app.core.config import Settings
from app.core.errors import AppError
from app.models.audience_delivery import AudienceDelivery, AudienceDeliveryApproval
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
    AudienceDeliveryApprovalCreate,
    AudienceDeliveryApprovalRead,
    AudienceExportRead,
    RecommendationProvenance,
    RecommendationsRead,
)
from app.schemas.exposure_segments import AuthoritativeExposureCell
from app.services.admin_authorization import require_active_admin
from app.services.audience import (
    AUDIENCE_EXPOSURE_FORMULA_VERSION,
    _advertiser_membership,
    _as_utc,
    _cell_snapshot,
    _derive_authoritative_cells,
    _link_access,
    _privacy_gate,
    exposure_segment_is_stale,
)
from app.services.audit import create_audit_event
from app.services.disclosure import (
    DisclosureQuery,
    _approved_reference,
    audience_disclosure_policy,
    exposure_cell_meets_disclosure_floor,
    record_disclosure,
)
from app.services.measurement import measurement_run_reproducible
from app.services.payout_rule_serialization import database_clock

RECOMMENDATION_DISCLAIMER = (
    "Modelled potential contacts are estimates, not observed people or guaranteed outcomes. "
    "Use these recommendations only for aggregate geography, time-window and contextual "
    "campaign planning."
)


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


async def _approval_lock(
    session: AsyncSession, *, actor_user_id: UUID, idempotency_key: str
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    digest = hashlib.sha256(
        f"audience-delivery-approval-v1:{actor_user_id}:{idempotency_key}".encode()
    ).digest()[:8]
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(digest, "big", signed=True)},
    )


def _approval_read(approval: AudienceDeliveryApproval) -> AudienceDeliveryApprovalRead:
    return AudienceDeliveryApprovalRead.model_validate(approval, from_attributes=True)


async def create_audience_delivery_approval(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: UUID,
    segment_id: UUID,
    idempotency_key: str,
    payload: AudienceDeliveryApprovalCreate,
) -> AudienceDeliveryApprovalRead:
    segment, link = await _segment_access(
        session,
        settings=settings,
        actor_user_id=actor_user_id,
        segment_id=segment_id,
        write=True,
        admin=True,
    )
    if await exposure_segment_is_stale(session, segment):
        raise AppError(
            "EXPOSURE_SEGMENT_STALE",
            "A current exposure segment is required for approval",
            status_code=status.HTTP_409_CONFLICT,
        )
    await _verify_segment_governance(session, segment=segment, link=link, settings=settings)
    synthetic = segment.synthetic
    legal_reference = payload.legal_approval_reference.strip()
    if synthetic:
        if (
            settings.environment not in {"test", "testing"}
            or not settings.privacy_disclosure_synthetic_test_mode
            or not legal_reference.lower().startswith("synthetic-test-")
        ):
            raise AppError(
                "AUDIENCE_DELIVERY_APPROVAL_INVALID",
                "Synthetic approval authority is restricted to explicit test mode",
                status_code=status.HTTP_409_CONFLICT,
            )
    elif (
        not _approved_reference(legal_reference)
        or legal_reference != settings.privacy_legal_approval_reference
    ):
        raise AppError(
            "AUDIENCE_DELIVERY_APPROVAL_INVALID",
            "Approval legal evidence does not match live privacy authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    if _as_utc(payload.valid_until) <= now:
        raise AppError(
            "AUDIENCE_DELIVERY_APPROVAL_EXPIRED",
            "Delivery approval must expire after the database clock",
            status_code=status.HTTP_409_CONFLICT,
        )
    request = {
        "segment_id": str(segment.id),
        **payload.model_dump(mode="json"),
        "legal_approval_reference": legal_reference,
    }
    request_fingerprint = _canonical_hash(request)
    await _approval_lock(session, actor_user_id=actor_user_id, idempotency_key=idempotency_key)
    replay = await session.scalar(
        select(AudienceDeliveryApproval).where(
            AudienceDeliveryApproval.approved_by_user_id == actor_user_id,
            AudienceDeliveryApproval.idempotency_key == idempotency_key,
        )
    )
    if replay is not None:
        if replay.request_fingerprint != request_fingerprint:
            raise AppError(
                "AUDIENCE_DELIVERY_APPROVAL_IDEMPOTENCY_CONFLICT",
                "Approval idempotency key was reused with a different request",
                status_code=status.HTTP_409_CONFLICT,
            )
        return _approval_read(replay)
    snapshot = {
        "schema_version": "audience-delivery-approval-v1",
        "organization_id": str(segment.organization_id),
        "campaign_id": str(segment.campaign_id),
        "source_id": str(segment.source_id),
        "source_fingerprint": link.source_fingerprint,
        "source_link_id": str(link.id),
        "source_link_snapshot_sha256": link.snapshot_sha256,
        "segment_id": str(segment.id),
        "segment_snapshot_sha256": segment.snapshot_sha256,
        "aggregate_formula_version": segment.aggregate_formula_version,
        "aggregate_authority_sha256": segment.aggregate_authority_sha256,
        "disclosure_policy_sha256": segment.disclosure_policy_sha256,
        "operation": payload.operation,
        "purpose_code": payload.purpose_code,
        "provider": payload.provider,
        "provider_account_reference": payload.provider_account_reference,
        "budget_ceiling": (
            str(payload.budget_ceiling) if payload.budget_ceiling is not None else None
        ),
        "legal_approval_reference": legal_reference,
        "approved_by_user_id": str(actor_user_id),
        "valid_from": now.isoformat(),
        "valid_until": _as_utc(payload.valid_until).isoformat(),
        "synthetic": synthetic,
    }
    approval = AudienceDeliveryApproval(
        organization_id=segment.organization_id,
        campaign_id=segment.campaign_id,
        segment_id=segment.id,
        approved_by_user_id=actor_user_id,
        operation=payload.operation,
        purpose_code=payload.purpose_code,
        provider=payload.provider,
        provider_account_reference=payload.provider_account_reference,
        budget_ceiling=payload.budget_ceiling,
        legal_approval_reference=legal_reference,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        snapshot=snapshot,
        snapshot_sha256=_canonical_hash(snapshot),
        synthetic=synthetic,
        valid_from=now,
        valid_until=_as_utc(payload.valid_until),
        created_at=now,
    )
    session.add(approval)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="audience_delivery.approved",
        entity_type="audience_delivery_approval",
        entity_id=str(approval.id),
        metadata={
            "organization_id": str(segment.organization_id),
            "campaign_id": str(segment.campaign_id),
            "segment_id": str(segment.id),
            "operation": payload.operation,
            "purpose_code": payload.purpose_code,
            "provider": payload.provider,
            "synthetic": synthetic,
            "snapshot_sha256": approval.snapshot_sha256,
        },
    )
    return _approval_read(approval)


async def _require_delivery_approval(
    session: AsyncSession,
    *,
    settings: Settings,
    segment: ExposureSegment,
    approval_id: UUID,
    operation: str,
    provider: str,
) -> AudienceDeliveryApproval:
    approval = await session.scalar(
        select(AudienceDeliveryApproval)
        .where(AudienceDeliveryApproval.id == approval_id)
        .with_for_update()
    )
    now = await database_clock(session)
    if approval is None:
        raise AppError(
            "AUDIENCE_DELIVERY_APPROVAL_NOT_FOUND",
            "Delivery approval was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if not _approval_matches_segment(
        approval,
        settings=settings,
        segment=segment,
        operation=operation,
        provider=provider,
        now=now,
    ):
        raise AppError(
            "AUDIENCE_DELIVERY_APPROVAL_MISMATCH",
            "Delivery approval does not authorize these exact governed inputs",
            status_code=status.HTTP_409_CONFLICT,
        )
    return approval


def _approval_matches_segment(
    approval: AudienceDeliveryApproval,
    *,
    settings: Settings,
    segment: ExposureSegment,
    operation: str,
    provider: str,
    now: datetime,
) -> bool:
    purpose_code = (
        "aggregate_campaign_planning"
        if operation == "csv_export"
        else "aggregate_contextual_activation"
    )
    legal_authority_matches = (
        approval.synthetic
        and segment.synthetic
        and settings.environment in {"test", "testing"}
        and settings.privacy_disclosure_synthetic_test_mode
        and approval.legal_approval_reference.lower().startswith("synthetic-test-")
    ) or (
        not approval.synthetic
        and not segment.synthetic
        and _approved_reference(settings.privacy_legal_approval_reference)
        and approval.legal_approval_reference == settings.privacy_legal_approval_reference
    )
    snapshot = approval.snapshot
    return not (
        approval.organization_id != segment.organization_id
        or approval.campaign_id != segment.campaign_id
        or approval.segment_id != segment.id
        or approval.operation != operation
        or approval.purpose_code != purpose_code
        or approval.provider != provider
        or _as_utc(approval.valid_from) > now
        or _as_utc(approval.valid_until) <= now
        or not legal_authority_matches
        or _canonical_hash(snapshot) != approval.snapshot_sha256
        or snapshot.get("schema_version") != "audience-delivery-approval-v1"
        or snapshot.get("organization_id") != str(segment.organization_id)
        or snapshot.get("campaign_id") != str(segment.campaign_id)
        or snapshot.get("source_id") != str(segment.source_id)
        or snapshot.get("source_link_id") != str(segment.source_link_id)
        or snapshot.get("source_link_snapshot_sha256") != segment.source_link_snapshot_sha256
        or snapshot.get("segment_id") != str(segment.id)
        or snapshot.get("segment_snapshot_sha256") != segment.snapshot_sha256
        or snapshot.get("aggregate_formula_version") != segment.aggregate_formula_version
        or snapshot.get("aggregate_authority_sha256") != segment.aggregate_authority_sha256
        or snapshot.get("disclosure_policy_sha256") != segment.disclosure_policy_sha256
        or snapshot.get("operation") != approval.operation
        or snapshot.get("purpose_code") != approval.purpose_code
        or snapshot.get("provider") != approval.provider
        or snapshot.get("provider_account_reference") != approval.provider_account_reference
        or snapshot.get("budget_ceiling")
        != (str(approval.budget_ceiling) if approval.budget_ceiling is not None else None)
        or snapshot.get("legal_approval_reference") != approval.legal_approval_reference
        or snapshot.get("approved_by_user_id") != str(approval.approved_by_user_id)
        or snapshot.get("valid_from") != _as_utc(approval.valid_from).isoformat()
        or snapshot.get("valid_until") != _as_utc(approval.valid_until).isoformat()
        or snapshot.get("synthetic") is not approval.synthetic
    )


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
        await require_active_admin(session, actor_user_id)
    else:
        organization_id = (
            await _advertiser_membership(session, actor_user_id=actor_user_id, write=write)
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


def _segment_governance_error(message: str) -> AppError:
    return AppError(
        "EXPOSURE_SEGMENT_GOVERNANCE_STALE",
        message,
        status_code=status.HTTP_409_CONFLICT,
    )


async def _verify_segment_governance(
    session: AsyncSession,
    *,
    segment: ExposureSegment,
    link: RetargetingSourceLink,
    settings: Settings,
) -> list[ExposureSegmentCell]:
    if (
        segment.aggregate_formula_version != AUDIENCE_EXPOSURE_FORMULA_VERSION
        or segment.aggregate_authority_sha256 is None
        or segment.disclosure_policy_sha256 is None
        or _canonical_hash(segment.snapshot) != segment.snapshot_sha256
    ):
        raise _segment_governance_error(
            "The segment has no current authoritative aggregate evidence"
        )
    policy = audience_disclosure_policy(settings)
    policy_sha256 = _canonical_hash(policy)
    if policy_sha256 != segment.disclosure_policy_sha256:
        raise _segment_governance_error(
            "The segment disclosure policy no longer matches current authority"
        )
    authoritative_cells = segment.snapshot.get("authoritative_cells")
    if not isinstance(authoritative_cells, list):
        raise _segment_governance_error("The segment aggregate authority is incomplete")
    run = await session.get(MeasurementRun, segment.measurement_run_id)
    if (
        run is None
        or run.organization_id != segment.organization_id
        or run.campaign_id != segment.campaign_id
        or run.input_manifest_sha256 != segment.measurement_input_sha256
        or run.result_manifest_sha256 != segment.measurement_result_sha256
        or run.proof_manifest_sha256 != segment.measurement_proof_sha256
        or not measurement_run_reproducible(run)
    ):
        raise _segment_governance_error("The segment measurement authority no longer matches")
    recomputed_cells = sorted(
        (
            _cell_snapshot(cell)
            for cell in await _derive_authoritative_cells(
                session, settings=settings, link=link, run=run
            )
        ),
        key=lambda item: (
            item["coverage_cell"],
            item["window_start_at"],
            item["window_end_at"],
            item["context"],
        ),
    )
    if recomputed_cells != authoritative_cells:
        raise _segment_governance_error(
            "The segment cells do not recompute from measurement authority"
        )
    authority = {
        "schema_version": "audience-exposure-authority-v1",
        "formula_version": AUDIENCE_EXPOSURE_FORMULA_VERSION,
        "measurement_run_id": str(segment.measurement_run_id),
        "measurement_input_sha256": segment.measurement_input_sha256,
        "measurement_result_sha256": segment.measurement_result_sha256,
        "measurement_proof_sha256": segment.measurement_proof_sha256,
        "source_link_snapshot_sha256": segment.source_link_snapshot_sha256,
        "disclosure_policy": policy,
        "cells": authoritative_cells,
    }
    if _canonical_hash(authority) != segment.aggregate_authority_sha256:
        raise _segment_governance_error("The segment aggregate authority was altered")
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
    try:
        stored_cells = [
            AuthoritativeExposureCell(
                coverage_cell=row.coverage_cell,
                window_start_at=_as_utc(row.window_start_at),
                window_end_at=_as_utc(row.window_end_at),
                context=row.context,
                distinct_vehicle_count=row.distinct_vehicle_count,
                trip_count=row.trip_count,
                distinct_day_count=row.distinct_day_count,
                max_contributor_share=row.max_contributor_share,
                modelled_potential_contacts=row.modelled_potential_contacts,
                formula_version=segment.aggregate_formula_version,
                synthetic=segment.synthetic,
            ).model_dump(mode="json")
            for row in rows
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise _segment_governance_error(
            "The stored segment cells violate the aggregate authority"
        ) from exc
    if stored_cells != segment.snapshot.get("cells"):
        raise _segment_governance_error("The persisted aggregate cells were altered")
    governed = [
        row
        for row in rows
        if exposure_cell_meets_disclosure_floor(
            distinct_vehicle_count=row.distinct_vehicle_count,
            trip_count=row.trip_count,
            distinct_day_count=row.distinct_day_count or 0,
            max_contributor_share=float(row.max_contributor_share or 1),
            resolution_m=row.resolution_m or 0,
            settings=settings,
        )
    ]
    if len(governed) != len(rows):
        raise AppError(
            "AUDIENCE_AGGREGATE_SUPPRESSED",
            "No aggregate cells satisfy the current disclosure policy",
            status_code=status.HTTP_409_CONFLICT,
        )
    return governed


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


async def _current_export_approval_id(
    session: AsyncSession, *, settings: Settings, segment: ExposureSegment
) -> UUID | None:
    now = await database_clock(session)
    approvals = list(
        await session.scalars(
            select(AudienceDeliveryApproval)
            .where(
                AudienceDeliveryApproval.segment_id == segment.id,
                AudienceDeliveryApproval.operation == "csv_export",
                AudienceDeliveryApproval.valid_from <= now,
                AudienceDeliveryApproval.valid_until > now,
            )
            .order_by(
                AudienceDeliveryApproval.created_at.desc(),
                AudienceDeliveryApproval.id.desc(),
            )
        )
    )
    for approval in approvals:
        if _approval_matches_segment(
            approval,
            settings=settings,
            segment=segment,
            operation="csv_export",
            provider="controlled-csv-v1",
            now=now,
        ):
            return approval.id
    return None


async def _recommendations_for_segment(
    session: AsyncSession,
    *,
    segment: ExposureSegment,
    link: RetargetingSourceLink,
    settings: Settings,
    actor_user_id: UUID,
    admin: bool,
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
    cells = await _verify_segment_governance(session, segment=segment, link=link, settings=settings)
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
    export_approval_id = (
        await _current_export_approval_id(session, settings=settings, segment=segment)
        if ranked
        else None
    )
    if cells:
        await _record_audience_release(
            session,
            settings=settings,
            route_id=(
                "admin.audience.recommendations" if admin else "advertiser.audience.recommendations"
            ),
            actor_user_id=actor_user_id,
            segment=segment,
            cells=cells,
        )
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
        export_approval_id=export_approval_id,
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
        session,
        segment=segment,
        link=link,
        settings=settings,
        actor_user_id=actor_user_id,
        admin=admin,
    )


async def _outbound_payload(
    session: AsyncSession,
    *,
    segment: ExposureSegment,
    link: RetargetingSourceLink,
    settings: Settings,
) -> tuple[AggregateActivationPayload, list[ExposureSegmentCell]]:
    if link.status != "active" or await exposure_segment_is_stale(session, segment):
        raise AppError(
            "EXPOSURE_SEGMENT_STALE",
            "A current exposure segment is required for export or activation",
            status_code=status.HTTP_409_CONFLICT,
        )
    cells = await _verify_segment_governance(session, segment=segment, link=link, settings=settings)
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
    ), cells


def _audience_release_hash(*, segment: ExposureSegment, cells: list[ExposureSegmentCell]) -> str:
    targets = sorted(
        (
            {
                "coverage_cell": row.coverage_cell,
                "window_start_at": _as_utc(row.window_start_at).isoformat(),
                "window_end_at": _as_utc(row.window_end_at).isoformat(),
                "context": row.context,
            }
            for row in cells
        ),
        key=lambda item: (
            item["coverage_cell"],
            item["window_start_at"],
            item["window_end_at"],
            item["context"],
        ),
    )
    return _canonical_hash(
        {
            "schema_version": "aggregate-target-disclosure-v1",
            "campaign_id": str(segment.campaign_id),
            "targets": targets,
        }
    )


async def _record_audience_release(
    session: AsyncSession,
    *,
    settings: Settings,
    route_id: str,
    actor_user_id: UUID,
    segment: ExposureSegment,
    cells: list[ExposureSegmentCell],
    commit_served: bool = True,
) -> None:
    await record_disclosure(
        session,
        query=DisclosureQuery(
            route_id=route_id,
            principal_id=actor_user_id,
            tenant_id=segment.organization_id,
            campaign_id=segment.campaign_id,
            start_at=min(_as_utc(row.window_start_at) for row in cells),
            end_at=max(_as_utc(row.window_end_at) for row in cells),
            filters={"aggregate_authority_sha256": segment.aggregate_authority_sha256},
        ),
        settings=settings,
        has_releasable_cells=True,
        result_hash=_audience_release_hash(segment=segment, cells=cells),
        commit_served=commit_served,
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
    approval_id: UUID,
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
    payload, cells = await _outbound_payload(session, segment=segment, link=link, settings=settings)
    await _record_audience_release(
        session,
        settings=settings,
        route_id="advertiser.audience.export",
        actor_user_id=actor_user_id,
        segment=segment,
        cells=cells,
        commit_served=False,
    )
    approval = await _require_delivery_approval(
        session,
        settings=settings,
        segment=segment,
        approval_id=approval_id,
        operation="csv_export",
        provider="controlled-csv-v1",
    )
    payload_dict = payload.model_dump(mode="json")
    payload_sha256 = _canonical_hash(payload_dict)
    request_fingerprint = _canonical_hash(
        {
            "segment_id": str(segment.id),
            "approval_snapshot_sha256": approval.snapshot_sha256,
            "payload_sha256": payload_sha256,
        }
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
            approval_id=approval.id,
            purpose_code=approval.purpose_code,
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
        approval_id=approval.id,
        approval_snapshot_sha256=approval.snapshot_sha256,
        purpose_code=approval.purpose_code,
        actor_user_id=actor_user_id,
        operation="csv_export",
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        payload=payload_dict,
        payload_sha256=payload_sha256,
        result=result,
        result_sha256=_canonical_hash(result),
        adapter_name="controlled-csv-v1",
        synthetic=segment.synthetic,
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
            "approval_id": str(approval.id),
            "approval_snapshot_sha256": approval.snapshot_sha256,
            "purpose_code": approval.purpose_code,
            "payload_sha256": payload_sha256,
        },
    )
    await session.flush()
    return AudienceExportRead(
        id=delivery.id,
        segment_id=delivery.segment_id,
        operation="csv_export",
        approval_id=approval.id,
        purpose_code=approval.purpose_code,
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
    approval_id: UUID,
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
    payload, cells = await _outbound_payload(session, segment=segment, link=link, settings=settings)
    await _record_audience_release(
        session,
        settings=settings,
        route_id="admin.audience.activation",
        actor_user_id=actor_user_id,
        segment=segment,
        cells=cells,
        commit_served=False,
    )
    payload_dict = payload.model_dump(mode="json")
    payload_sha256 = _canonical_hash(payload_dict)
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
    approval = await _require_delivery_approval(
        session,
        settings=settings,
        segment=segment,
        approval_id=approval_id,
        operation="ad_platform_activation",
        provider=adapter.name,
    )
    request_fingerprint = _canonical_hash(
        {
            "segment_id": str(segment.id),
            "approval_snapshot_sha256": approval.snapshot_sha256,
            "payload_sha256": payload_sha256,
        }
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
            approval_id=approval.id,
            purpose_code=approval.purpose_code,
            adapter_name=replay.adapter_name,
            provider_reference=replay.result["provider_reference"],
            payload_sha256=replay.payload_sha256,
            synthetic=replay.synthetic,
            created_at=_as_utc(replay.created_at),
        )
    delivery_id = _delivery_id(actor_user_id, "ad_platform_activation", idempotency_key)
    submission = await adapter.activate(
        AdPlatformActivationRequest(idempotency_key=str(delivery_id), payload=payload)
    )
    result = {"provider_reference": submission.provider_reference}
    now = await database_clock(session)
    delivery = AudienceDelivery(
        id=delivery_id,
        organization_id=segment.organization_id,
        campaign_id=segment.campaign_id,
        segment_id=segment.id,
        approval_id=approval.id,
        approval_snapshot_sha256=approval.snapshot_sha256,
        purpose_code=approval.purpose_code,
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
            "approval_id": str(approval.id),
            "approval_snapshot_sha256": approval.snapshot_sha256,
            "purpose_code": approval.purpose_code,
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
        approval_id=approval.id,
        purpose_code=approval.purpose_code,
        adapter_name=delivery.adapter_name,
        provider_reference=submission.provider_reference,
        payload_sha256=delivery.payload_sha256,
        synthetic=True,
        created_at=_as_utc(delivery.created_at),
    )

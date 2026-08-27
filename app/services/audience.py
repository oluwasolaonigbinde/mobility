from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign import Campaign
from app.models.campaign_zone import CampaignZone
from app.models.exposure_score import ExposureScore
from app.models.exposure_segment import ExposureSegment, ExposureSegmentCell
from app.models.measurement import MeasurementRun
from app.models.organization import (
    AdvertiserOrganization,
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
    OrganizationStatus,
)
from app.models.retargeting_source import (
    RetargetingSource,
    RetargetingSourceEvent,
    RetargetingSourceIdempotency,
)
from app.models.retargeting_source_link import (
    RetargetingSourceLink,
    RetargetingSourceLinkEvent,
    RetargetingSourceLinkIdempotency,
)
from app.models.user import User, UserRole, UserStatus
from app.schemas.exposure_segments import ExposureCellInput
from app.schemas.retargeting_source_links import RetargetingSourceLinkCreate
from app.schemas.retargeting_sources import RetargetingSourceCreate
from app.schemas.zone_insights import (
    HighExposureZoneInsightsRead,
    HighExposureZoneItem,
    HighExposureZoneProvenance,
    ZoneInsightSegmentProvenance,
)
from app.services.audit import create_audit_event
from app.services.disclosure import (
    _approved_reference,
    ensure_disclosure_live_gate,
    exposure_cell_meets_disclosure_floor,
)
from app.services.measurement import measurement_run_reproducible
from app.services.payout_rule_serialization import database_clock


def _canonical_hash(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


HIGH_EXPOSURE_ZONE_FORMULA_VERSION = "high_exposure_zone_v1"
HIGH_EXPOSURE_ZONE_FORMULA_CONTRACT = {
    "formula_version": HIGH_EXPOSURE_ZONE_FORMULA_VERSION,
    "scope": "campaign_target_zone",
    "authority": (
        "Latest immutable exposure segment per source link for one reproducible measurement "
        "run, bound to its issued exposure_v1 score."
    ),
    "aggregation": (
        "Deduplicate identical zone/cell/window/context facts, then sum frozen modelled "
        "potential contacts and trip counts per target zone."
    ),
    "ordering": [
        "modelled_potential_contacts descending",
        "trip_count descending",
        "zone_id ascending",
    ],
    "ties": "Equal measures receive stable consecutive ranks using zone_id ascending.",
    "missing_data": (
        "No issued run or segment is empty; a missing/insufficient exposure score is "
        "unavailable; stale authority fails closed; any current k-floor failure suppresses "
        "the entire result."
    ),
    "metric_separation": (
        "The campaign exposure score is frozen provenance and context only. Ranking uses "
        "modelled potential contacts and is not impressions, observed contacts, attribution, "
        "financial ROI, or a new exposure score."
    ),
}
HIGH_EXPOSURE_ZONE_FORMULA_FINGERPRINT = _canonical_hash(HIGH_EXPOSURE_ZONE_FORMULA_CONTRACT)
HIGH_EXPOSURE_ZONE_DISCLAIMER = (
    "Ranks disclosure-cleared zones by frozen modelled potential contacts. The campaign "
    "exposure score is a separate uncalibrated operational index; exposure score, "
    "impressions, potential contacts, attribution and ROI remain separate measures. "
    "The ranking does not represent observed people or guaranteed outcomes."
)


@dataclass(frozen=True)
class ZoneInsightTotal:
    zone_id: UUID
    modelled_potential_contacts: Decimal
    trip_count: int


@dataclass(frozen=True)
class RankedZoneInsight(ZoneInsightTotal):
    rank: int


def rank_high_exposure_zones(
    totals: list[ZoneInsightTotal],
) -> list[RankedZoneInsight]:
    ordered = sorted(
        totals,
        key=lambda item: (
            -item.modelled_potential_contacts,
            -item.trip_count,
            item.zone_id,
        ),
    )
    return [
        RankedZoneInsight(
            zone_id=item.zone_id,
            modelled_potential_contacts=item.modelled_potential_contacts,
            trip_count=item.trip_count,
            rank=rank,
        )
        for rank, item in enumerate(ordered, start=1)
    ]


def _source_status(source: RetargetingSource, now: datetime) -> str:
    if source.status == "deactivated":
        return "deactivated"
    expires_at = source.expires_at
    if expires_at.tzinfo is None or expires_at.tzinfo.utcoffset(expires_at) is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return "expired" if expires_at <= now else "active"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso_utc(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value is not None else None


def _source_not_found() -> AppError:
    return AppError(
        "RETARGETING_SOURCE_NOT_FOUND", "Retargeting source was not found", status_code=404
    )


async def _privacy_gate(settings: Settings) -> None:
    # This is intentionally first in every public source operation: no source,
    # membership, idempotency, or organization query is permitted before it.
    ensure_disclosure_live_gate(settings, requires_measurement_run=False)


async def _advertiser_membership(
    session: AsyncSession, *, actor_user_id: UUID, write: bool
) -> OrganizationMembership:
    membership = await session.scalar(
        select(OrganizationMembership)
        .join(
            AdvertiserOrganization,
            AdvertiserOrganization.id == OrganizationMembership.organization_id,
        )
        .where(
            OrganizationMembership.user_id == actor_user_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
            AdvertiserOrganization.status == OrganizationStatus.ACTIVE,
        )
        .order_by(OrganizationMembership.created_at.desc(), OrganizationMembership.id.desc())
        .limit(1)
    )
    if membership is None:
        raise AppError(
            "ADVERTISER_ORGANIZATION_NOT_FOUND",
            "Advertiser organization was not found",
            status_code=404,
        )
    if write and membership.role not in {MembershipRole.OWNER, MembershipRole.MANAGER}:
        raise AppError(
            "ORGANIZATION_WRITE_FORBIDDEN", "Owner or manager access is required", status_code=403
        )
    return membership


async def _active_admin(session: AsyncSession, actor_user_id: UUID) -> None:
    admin_id = await session.scalar(
        select(User.id).where(
            User.id == actor_user_id,
            User.role == UserRole.ADMIN,
            User.status == UserStatus.ACTIVE,
        )
    )
    if admin_id is None:
        raise AppError(
            "FORBIDDEN_ROLE",
            "Admin role is required",
            status_code=status.HTTP_403_FORBIDDEN,
        )


async def _idempotency_lock(
    session: AsyncSession, *, actor_user_id: UUID, operation: str, key: str
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    digest = hashlib.sha256(
        f"retargeting-source-v1:{actor_user_id}:{operation}:{key}".encode()
    ).digest()[:8]
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(digest, "big", signed=True)},
    )


async def _idempotency_replay(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    organization_id: UUID,
    operation: str,
    key: str,
    fingerprint: str,
) -> RetargetingSource | None:
    record = await session.scalar(
        select(RetargetingSourceIdempotency).where(
            RetargetingSourceIdempotency.actor_user_id == actor_user_id,
            RetargetingSourceIdempotency.operation == operation,
            RetargetingSourceIdempotency.idempotency_key == key,
        )
    )
    if record is None:
        return None
    if record.request_fingerprint != fingerprint:
        raise AppError(
            "RETARGETING_SOURCE_IDEMPOTENCY_CONFLICT",
            "Idempotency key was reused with a different request",
            status_code=status.HTTP_409_CONFLICT,
        )
    source = await session.get(RetargetingSource, record.source_id)
    if source is None:  # defensive fail-closed guard for an invalid authority row
        raise RuntimeError("Retargeting source idempotency row has no source")
    if source.organization_id != organization_id:
        raise AppError(
            "RETARGETING_SOURCE_IDEMPOTENCY_CONFLICT",
            "Idempotency key belongs to a different advertiser organization",
            status_code=status.HTTP_409_CONFLICT,
        )
    return source


async def create_retargeting_source(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: UUID,
    payload: RetargetingSourceCreate,
    idempotency_key: str,
) -> RetargetingSource:
    await _privacy_gate(settings)
    membership = await _advertiser_membership(session, actor_user_id=actor_user_id, write=True)
    snapshot = payload.model_dump(mode="json")
    fingerprint = _canonical_hash(snapshot)
    await _idempotency_lock(
        session, actor_user_id=actor_user_id, operation="create", key=idempotency_key
    )
    replay = await _idempotency_replay(
        session,
        actor_user_id=actor_user_id,
        organization_id=membership.organization_id,
        operation="create",
        key=idempotency_key,
        fingerprint=fingerprint,
    )
    if replay is not None:
        return replay
    now = await database_clock(session)
    if payload.expires_at <= now:
        raise AppError(
            "RETARGETING_SOURCE_EXPIRY_INVALID",
            "expires_at must be in the future",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    source = RetargetingSource(
        organization_id=membership.organization_id,
        source_type=payload.source_type,
        snapshot=snapshot,
        snapshot_sha256=fingerprint,
        expires_at=payload.expires_at,
        created_at=now,
    )
    session.add(source)
    await session.flush()
    session.add(
        RetargetingSourceEvent(
            source_id=source.id,
            sequence_number=1,
            event_type="created",
            snapshot=snapshot,
            snapshot_sha256=fingerprint,
            created_at=now,
        )
    )
    session.add(
        RetargetingSourceIdempotency(
            actor_user_id=actor_user_id,
            operation="create",
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            source_id=source.id,
            created_at=now,
        )
    )
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="retargeting_source.created",
        entity_type="retargeting_source",
        entity_id=str(source.id),
        metadata={
            "organization_id": str(source.organization_id),
            "source_type": source.source_type,
        },
    )
    await session.flush()
    return source


async def list_advertiser_retargeting_sources(
    session: AsyncSession, *, settings: Settings, actor_user_id: UUID
) -> list[RetargetingSource]:
    await _privacy_gate(settings)
    membership = await _advertiser_membership(session, actor_user_id=actor_user_id, write=False)
    return list(
        await session.scalars(
            select(RetargetingSource)
            .where(RetargetingSource.organization_id == membership.organization_id)
            .order_by(RetargetingSource.created_at.desc())
        )
    )


async def get_advertiser_retargeting_source(
    session: AsyncSession, *, settings: Settings, actor_user_id: UUID, source_id: UUID
) -> RetargetingSource:
    await _privacy_gate(settings)
    membership = await _advertiser_membership(session, actor_user_id=actor_user_id, write=False)
    source = await session.scalar(
        select(RetargetingSource).where(
            RetargetingSource.id == source_id,
            RetargetingSource.organization_id == membership.organization_id,
        )
    )
    if source is None:
        raise _source_not_found()
    return source


async def retargeting_source_history(
    session: AsyncSession, *, source: RetargetingSource
) -> list[RetargetingSourceEvent]:
    return list(
        await session.scalars(
            select(RetargetingSourceEvent)
            .where(RetargetingSourceEvent.source_id == source.id)
            .order_by(RetargetingSourceEvent.sequence_number)
        )
    )


async def deactivate_retargeting_source(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: UUID,
    source_id: UUID,
    idempotency_key: str,
) -> RetargetingSource:
    await _privacy_gate(settings)
    membership = await _advertiser_membership(session, actor_user_id=actor_user_id, write=True)
    fingerprint = _canonical_hash({"source_id": str(source_id)})
    await _idempotency_lock(
        session, actor_user_id=actor_user_id, operation="deactivate", key=idempotency_key
    )
    replay = await _idempotency_replay(
        session,
        actor_user_id=actor_user_id,
        organization_id=membership.organization_id,
        operation="deactivate",
        key=idempotency_key,
        fingerprint=fingerprint,
    )
    if replay is not None:
        return replay
    source = await session.scalar(
        select(RetargetingSource)
        .where(
            RetargetingSource.id == source_id,
            RetargetingSource.organization_id == membership.organization_id,
        )
        .with_for_update()
    )
    if source is None:
        raise _source_not_found()
    if source.status != "active":
        raise AppError(
            "RETARGETING_SOURCE_NOT_ACTIVE",
            "Retargeting source is already deactivated",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    source.status = "deactivated"
    source.deactivated_at = now
    # Lifecycle is the event type and projection status; keep the evidence
    # payload inside the same closed five-shape source contract.
    event_snapshot = source.snapshot
    event_hash = _canonical_hash(event_snapshot)
    session.add(
        RetargetingSourceEvent(
            source_id=source.id,
            sequence_number=2,
            event_type="deactivated",
            snapshot=event_snapshot,
            snapshot_sha256=event_hash,
            created_at=now,
        )
    )
    session.add(
        RetargetingSourceIdempotency(
            actor_user_id=actor_user_id,
            operation="deactivate",
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            source_id=source.id,
            created_at=now,
        )
    )
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="retargeting_source.deactivated",
        entity_type="retargeting_source",
        entity_id=str(source.id),
        metadata={
            "organization_id": str(source.organization_id),
            "source_type": source.source_type,
        },
    )
    await session.flush()
    return source


async def list_admin_retargeting_sources(
    session: AsyncSession, *, settings: Settings, actor_user_id: UUID
) -> list[RetargetingSource]:
    await _privacy_gate(settings)
    await _active_admin(session, actor_user_id)
    return list(
        await session.scalars(
            select(RetargetingSource).order_by(RetargetingSource.created_at.desc())
        )
    )


async def get_admin_retargeting_source(
    session: AsyncSession, *, settings: Settings, actor_user_id: UUID, source_id: UUID
) -> RetargetingSource:
    await _privacy_gate(settings)
    await _active_admin(session, actor_user_id)
    source = await session.get(RetargetingSource, source_id)
    if source is None:
        raise _source_not_found()
    return source


async def source_effective_status(session: AsyncSession, source: RetargetingSource) -> str:
    return _source_status(source, await database_clock(session))


def _parent_fingerprint(value: dict) -> str:
    return _canonical_hash(value)


def _source_fingerprint(source: RetargetingSource) -> str:
    return _parent_fingerprint(
        {
            "snapshot": source.snapshot_sha256,
            "status": source.status,
            "expires_at": _iso_utc(source.expires_at),
        }
    )


def _campaign_fingerprint(campaign: Campaign) -> str:
    return _parent_fingerprint(
        {
            "id": str(campaign.id),
            "organization_id": str(campaign.organization_id),
            "status": campaign.status,
            "start_at": _iso_utc(campaign.start_at),
            "end_at": _iso_utc(campaign.end_at),
        }
    )


def _zone_fingerprint(zone: CampaignZone) -> str:
    return _parent_fingerprint(
        {
            "id": str(zone.id),
            "campaign_id": str(zone.campaign_id),
            "zone_type": zone.zone_type,
            "updated_at": _iso_utc(zone.updated_at),
        }
    )


async def _link_idempotency_lock(
    session: AsyncSession, actor_user_id: UUID, operation: str, key: str
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    digest = hashlib.sha256(
        f"retargeting-link-v1:{actor_user_id}:{operation}:{key}".encode()
    ).digest()[:8]
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(digest, "big", signed=True)},
    )


async def _link_replay(
    session: AsyncSession,
    actor_user_id: UUID,
    organization_id: UUID,
    operation: str,
    key: str,
    fingerprint: str,
) -> RetargetingSourceLink | None:
    row = await session.scalar(
        select(RetargetingSourceLinkIdempotency).where(
            RetargetingSourceLinkIdempotency.actor_user_id == actor_user_id,
            RetargetingSourceLinkIdempotency.operation == operation,
            RetargetingSourceLinkIdempotency.idempotency_key == key,
        )
    )
    if row is None:
        return None
    if row.request_fingerprint != fingerprint:
        raise AppError(
            "RETARGETING_SOURCE_LINK_IDEMPOTENCY_CONFLICT",
            "Idempotency key was reused with a different request",
            status_code=409,
        )
    link = await session.get(RetargetingSourceLink, row.link_id)
    if link is None:
        raise RuntimeError("Retargeting link idempotency row has no link")
    if link.organization_id != organization_id:
        raise AppError(
            "RETARGETING_SOURCE_LINK_IDEMPOTENCY_CONFLICT",
            "Idempotency key belongs to a different advertiser organization",
            status_code=status.HTTP_409_CONFLICT,
        )
    return link


async def create_retargeting_source_link(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: UUID,
    payload: RetargetingSourceLinkCreate,
    idempotency_key: str,
) -> RetargetingSourceLink:
    await _privacy_gate(settings)
    membership = await _advertiser_membership(session, actor_user_id=actor_user_id, write=True)
    request = payload.model_dump(mode="json")
    fingerprint = _canonical_hash(request)
    await _link_idempotency_lock(session, actor_user_id, "create", idempotency_key)
    replay = await _link_replay(
        session,
        actor_user_id,
        membership.organization_id,
        "create",
        idempotency_key,
        fingerprint,
    )
    if replay is not None:
        return replay
    source = await session.scalar(
        select(RetargetingSource)
        .where(
            RetargetingSource.id == payload.source_id,
            RetargetingSource.organization_id == membership.organization_id,
        )
        .with_for_update()
    )
    if source is None:
        raise _source_not_found()
    campaign = await session.scalar(
        select(Campaign)
        .where(
            Campaign.id == payload.campaign_id,
            Campaign.organization_id == membership.organization_id,
        )
        .with_for_update()
    )
    if campaign is None:
        raise AppError(
            "RETARGETING_LINK_CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404
        )
    zone = await session.scalar(
        select(CampaignZone).where(CampaignZone.id == payload.zone_id).with_for_update()
    )
    if zone is None or zone.campaign_id != campaign.id or zone.zone_type != "target":
        raise AppError(
            "RETARGETING_LINK_TARGET_ZONE_REQUIRED",
            "A target zone for the selected campaign is required",
            status_code=409,
        )
    now = await database_clock(session)
    if source.status != "active" or _source_status(source, now) != "active":
        raise AppError(
            "RETARGETING_LINK_SOURCE_INACTIVE",
            "An active unexpired source is required",
            status_code=409,
        )
    if (
        (campaign.start_at and payload.start_at < _as_utc(campaign.start_at))
        or (campaign.end_at and payload.end_at > _as_utc(campaign.end_at))
        or payload.end_at > _as_utc(source.expires_at)
    ):
        raise AppError(
            "RETARGETING_LINK_WINDOW_INVALID",
            "Link window is outside campaign or source bounds",
            status_code=409,
        )
    source_fp, campaign_fp, zone_fp = (
        _source_fingerprint(source),
        _campaign_fingerprint(campaign),
        _zone_fingerprint(zone),
    )
    snapshot = {
        "organization_id": str(membership.organization_id),
        "source_id": str(source.id),
        "campaign_id": str(campaign.id),
        "zone_id": str(zone.id),
        "start_at": payload.start_at.isoformat(),
        "end_at": payload.end_at.isoformat(),
        "source_fingerprint": source_fp,
        "campaign_fingerprint": campaign_fp,
        "zone_fingerprint": zone_fp,
    }
    snapshot_hash = _canonical_hash(snapshot)
    existing = await session.scalar(
        select(RetargetingSourceLink)
        .where(
            RetargetingSourceLink.source_id == source.id,
            RetargetingSourceLink.campaign_id == campaign.id,
            RetargetingSourceLink.zone_id == zone.id,
            RetargetingSourceLink.start_at == payload.start_at,
            RetargetingSourceLink.end_at == payload.end_at,
            RetargetingSourceLink.status == "active",
        )
        .with_for_update()
    )
    if existing is not None:
        raise AppError(
            "RETARGETING_SOURCE_LINK_ALREADY_ACTIVE",
            "An identical active link already exists",
            status_code=409,
        )
    link = RetargetingSourceLink(
        organization_id=membership.organization_id,
        source_id=source.id,
        campaign_id=campaign.id,
        zone_id=zone.id,
        start_at=payload.start_at,
        end_at=payload.end_at,
        source_fingerprint=source_fp,
        campaign_fingerprint=campaign_fp,
        zone_fingerprint=zone_fp,
        snapshot=snapshot,
        snapshot_sha256=snapshot_hash,
        created_at=now,
    )
    session.add(link)
    await session.flush()
    session.add(
        RetargetingSourceLinkEvent(
            link_id=link.id,
            sequence_number=1,
            event_type="created",
            snapshot=snapshot,
            snapshot_sha256=snapshot_hash,
            created_at=now,
        )
    )
    session.add(
        RetargetingSourceLinkIdempotency(
            actor_user_id=actor_user_id,
            operation="create",
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            link_id=link.id,
            created_at=now,
        )
    )
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="retargeting_source_link.created",
        entity_type="retargeting_source_link",
        entity_id=str(link.id),
        metadata={
            "organization_id": str(link.organization_id),
            "source_id": str(link.source_id),
            "campaign_id": str(link.campaign_id),
            "zone_id": str(link.zone_id),
        },
    )
    await session.flush()
    return link


async def _link_access(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: UUID,
    link_id: UUID,
    write: bool,
    admin: bool = False,
) -> RetargetingSourceLink:
    await _privacy_gate(settings)
    organization_id: UUID | None = None
    if admin:
        await _active_admin(session, actor_user_id)
    else:
        organization_id = (
            await _advertiser_membership(session, actor_user_id=actor_user_id, write=write)
        ).organization_id
    statement = select(RetargetingSourceLink).where(RetargetingSourceLink.id == link_id)
    if organization_id is not None:
        statement = statement.where(RetargetingSourceLink.organization_id == organization_id)
    if write:
        statement = statement.with_for_update()
    link = await session.scalar(statement)
    if link is None:
        raise AppError(
            "RETARGETING_SOURCE_LINK_NOT_FOUND",
            "Retargeting source link was not found",
            status_code=404,
        )
    return link


async def list_retargeting_source_links(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: UUID,
    admin: bool = False,
) -> list[RetargetingSourceLink]:
    await _privacy_gate(settings)
    statement = select(RetargetingSourceLink).order_by(RetargetingSourceLink.created_at.desc())
    if admin:
        await _active_admin(session, actor_user_id)
    else:
        membership = await _advertiser_membership(session, actor_user_id=actor_user_id, write=False)
        statement = statement.where(
            RetargetingSourceLink.organization_id == membership.organization_id
        )
    return list(await session.scalars(statement))


async def retargeting_source_link_history(
    session: AsyncSession, *, link: RetargetingSourceLink
) -> list[RetargetingSourceLinkEvent]:
    return list(
        await session.scalars(
            select(RetargetingSourceLinkEvent)
            .where(RetargetingSourceLinkEvent.link_id == link.id)
            .order_by(RetargetingSourceLinkEvent.sequence_number)
        )
    )


async def remove_retargeting_source_link(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: UUID,
    link_id: UUID,
    idempotency_key: str,
) -> RetargetingSourceLink:
    await _privacy_gate(settings)
    membership = await _advertiser_membership(session, actor_user_id=actor_user_id, write=True)
    fingerprint = _canonical_hash({"link_id": str(link_id)})
    await _link_idempotency_lock(session, actor_user_id, "remove", idempotency_key)
    replay = await _link_replay(
        session,
        actor_user_id,
        membership.organization_id,
        "remove",
        idempotency_key,
        fingerprint,
    )
    if replay is not None:
        return replay
    source = await session.scalar(
        select(RetargetingSource)
        .join(RetargetingSourceLink, RetargetingSourceLink.source_id == RetargetingSource.id)
        .where(
            RetargetingSourceLink.id == link_id,
            RetargetingSourceLink.organization_id == membership.organization_id,
        )
        .with_for_update(of=RetargetingSource)
    )
    link = await _link_access(
        session, settings=settings, actor_user_id=actor_user_id, link_id=link_id, write=True
    )
    if source is None:
        raise AppError(
            "RETARGETING_SOURCE_LINK_NOT_FOUND",
            "Retargeting source link was not found",
            status_code=404,
        )
    if link.status != "active":
        raise AppError(
            "RETARGETING_SOURCE_LINK_NOT_ACTIVE",
            "Retargeting source link is already removed",
            status_code=409,
        )
    now = await database_clock(session)
    link.status, link.removed_at = "removed", now
    session.add(
        RetargetingSourceLinkEvent(
            link_id=link.id,
            sequence_number=2,
            event_type="removed",
            snapshot=link.snapshot,
            snapshot_sha256=link.snapshot_sha256,
            created_at=now,
        )
    )
    session.add(
        RetargetingSourceLinkIdempotency(
            actor_user_id=actor_user_id,
            operation="remove",
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            link_id=link.id,
            created_at=now,
        )
    )
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="retargeting_source_link.removed",
        entity_type="retargeting_source_link",
        entity_id=str(link.id),
        metadata={"organization_id": str(link.organization_id), "source_id": str(link.source_id)},
    )
    await session.flush()
    return link


async def link_is_stale(session: AsyncSession, link: RetargetingSourceLink) -> bool:
    source = await session.get(RetargetingSource, link.source_id)
    campaign = await session.get(Campaign, link.campaign_id)
    zone = await session.get(CampaignZone, link.zone_id)
    now = await database_clock(session)
    return (
        source is None
        or campaign is None
        or zone is None
        or _source_status(source, now) != "active"
        or _source_fingerprint(source) != link.source_fingerprint
        or _campaign_fingerprint(campaign) != link.campaign_fingerprint
        or _zone_fingerprint(zone) != link.zone_fingerprint
    )


async def _exposure_materialization_lock(
    session: AsyncSession, source_link_id: UUID
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    digest = hashlib.sha256(
        f"exposure-segment-v1:{source_link_id}".encode()
    ).digest()[:8]
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(digest, "big", signed=True)},
    )


def _cell_snapshot(cell: ExposureCellInput) -> dict:
    return cell.model_dump(mode="json")


async def materialize_exposure_segment(
    session: AsyncSession,
    *,
    settings: Settings,
    source_link_id: UUID,
    measurement_run_id: UUID,
    cells: list[ExposureCellInput],
) -> ExposureSegment:
    await _privacy_gate(settings)
    if not cells:
        raise AppError(
            "EXPOSURE_SEGMENT_CELLS_REQUIRED",
            "At least one aggregate coverage cell is required",
            status_code=status.HTTP_409_CONFLICT,
        )
    await _exposure_materialization_lock(session, source_link_id)
    link = await session.scalar(
        select(RetargetingSourceLink)
        .where(RetargetingSourceLink.id == source_link_id)
        .with_for_update()
    )
    run = await session.get(MeasurementRun, measurement_run_id)
    if link is None:
        raise AppError(
            "EXPOSURE_SEGMENT_LINK_NOT_FOUND",
            "Retargeting source link was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if run is None:
        raise AppError(
            "EXPOSURE_SEGMENT_MEASUREMENT_RUN_NOT_FOUND",
            "Measurement run was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if (
        link.status != "active"
        or await link_is_stale(session, link)
        or run.organization_id != link.organization_id
        or run.campaign_id != link.campaign_id
    ):
        raise AppError(
            "EXPOSURE_SEGMENT_SCOPE_MISMATCH",
            "An active current link and measurement run in the same tenant and campaign "
            "are required",
            status_code=status.HTTP_409_CONFLICT,
        )
    if not measurement_run_reproducible(run):
        raise AppError(
            "EXPOSURE_SEGMENT_MEASUREMENT_RUN_INVALID",
            "The immutable measurement run did not reproduce",
            status_code=status.HTTP_409_CONFLICT,
        )
    if not run.test_only and settings.privacy_disclosure_synthetic_test_mode:
        raise AppError(
            "EXPOSURE_SEGMENT_LIVE_RUN_FORBIDDEN",
            "Synthetic materialization cannot consume a live measurement run",
            status_code=status.HTTP_409_CONFLICT,
        )
    from app.services.exposure_scores import exposure_score_is_stale

    score = await session.scalar(
        select(ExposureScore)
        .where(
            ExposureScore.measurement_run_id == run.id,
            ExposureScore.formula_version == "exposure_v1",
        )
        .order_by(ExposureScore.created_at.desc(), ExposureScore.id.desc())
        .limit(1)
    )
    if score is None:
        raise AppError(
            "ZONE_INSIGHT_EXPOSURE_SCORE_REQUIRED",
            "An issued exposure_v1 score is required before exposure segments can carry "
            "high-exposure zone authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    if await exposure_score_is_stale(session, score):
        raise AppError(
            "ZONE_INSIGHT_EXPOSURE_SCORE_STALE",
            "The issued exposure score no longer matches its immutable measurement run",
            status_code=status.HTTP_409_CONFLICT,
        )
    zone_insight_authority = {
        "formula_version": HIGH_EXPOSURE_ZONE_FORMULA_VERSION,
        "formula_fingerprint": HIGH_EXPOSURE_ZONE_FORMULA_FINGERPRINT,
        "exposure_score_id": str(score.id),
        "exposure_formula_version": score.formula_version,
        "exposure_formula_fingerprint": score.formula_fingerprint,
        "exposure_input_fingerprint": score.input_fingerprint,
        "exposure_result_fingerprint": score.result_fingerprint,
        "exposure_score_status": score.result_snapshot.get("status"),
        "campaign_exposure_score": score.result_snapshot.get("score"),
    }

    normalized = sorted(
        (_cell_snapshot(cell) for cell in cells),
        key=lambda item: (
            item["coverage_cell"],
            item["window_start_at"],
            item["window_end_at"],
            item["context"],
        ),
    )
    identities = {
        (
            item["coverage_cell"],
            item["window_start_at"],
            item["window_end_at"],
            item["context"],
        )
        for item in normalized
    }
    if len(identities) != len(normalized):
        raise AppError(
            "EXPOSURE_SEGMENT_DUPLICATE_CELL",
            "Duplicate coverage-cell/time/context facts are not allowed",
            status_code=status.HTTP_409_CONFLICT,
        )
    link_start = _as_utc(link.start_at)
    link_end = _as_utc(link.end_at)
    run_start = _as_utc(run.period_start_at)
    run_end = _as_utc(run.period_end_at)
    for cell in cells:
        start_at = _as_utc(cell.window_start_at)
        end_at = _as_utc(cell.window_end_at)
        if start_at < link_start or end_at > link_end or start_at < run_start or end_at > run_end:
            raise AppError(
                "EXPOSURE_SEGMENT_WINDOW_INVALID",
                "Every cell window must be inside both the link and immutable run periods",
                status_code=status.HTTP_409_CONFLICT,
            )

    facts = {
        "schema_version": "exposure-segment-facts-v1",
        "source_link_id": str(link.id),
        "source_link_snapshot_sha256": link.snapshot_sha256,
        "measurement_run_id": str(run.id),
        "measurement_input_sha256": run.input_manifest_sha256,
        "measurement_result_sha256": run.result_manifest_sha256,
        "measurement_proof_sha256": run.proof_manifest_sha256,
        "zone_insight_authority": zone_insight_authority,
        "cells": normalized,
    }
    facts_fingerprint = _canonical_hash(facts)
    replay = await session.scalar(
        select(ExposureSegment).where(
            ExposureSegment.source_link_id == link.id,
            ExposureSegment.facts_fingerprint == facts_fingerprint,
        )
    )
    if replay is not None:
        return replay
    latest = await session.scalar(
        select(ExposureSegment)
        .where(ExposureSegment.source_link_id == link.id)
        .order_by(ExposureSegment.version.desc())
        .limit(1)
    )
    releasable = [
        item
        for item in normalized
        if exposure_cell_meets_disclosure_floor(
            distinct_vehicle_count=item["distinct_vehicle_count"], settings=settings
        )
    ]
    snapshot = {
        "schema_version": "exposure-segment-v1",
        "organization_id": str(link.organization_id),
        "campaign_id": str(link.campaign_id),
        "zone_id": str(link.zone_id),
        "source_link_id": str(link.id),
        "measurement_run_id": str(run.id),
        "version": (latest.version + 1) if latest is not None else 1,
        "zone_insight_authority": zone_insight_authority,
        "cells": releasable,
    }
    segment = ExposureSegment(
        organization_id=link.organization_id,
        campaign_id=link.campaign_id,
        zone_id=link.zone_id,
        source_id=link.source_id,
        source_link_id=link.id,
        measurement_run_id=run.id,
        version=snapshot["version"],
        facts_fingerprint=facts_fingerprint,
        source_link_snapshot_sha256=link.snapshot_sha256,
        measurement_input_sha256=run.input_manifest_sha256,
        measurement_result_sha256=run.result_manifest_sha256,
        measurement_proof_sha256=run.proof_manifest_sha256,
        snapshot=snapshot,
        snapshot_sha256=_canonical_hash(snapshot),
        releasable_cell_count=len(releasable),
        suppressed_cell_count=len(normalized) - len(releasable),
        reissue_of_segment_id=latest.id if latest is not None else None,
    )
    session.add(segment)
    await session.flush()
    for item in releasable:
        session.add(
            ExposureSegmentCell(
                segment_id=segment.id,
                coverage_cell=item["coverage_cell"],
                window_start_at=datetime.fromisoformat(item["window_start_at"]),
                window_end_at=datetime.fromisoformat(item["window_end_at"]),
                context=item["context"],
                distinct_vehicle_count=item["distinct_vehicle_count"],
                trip_count=item["trip_count"],
                modelled_potential_contacts=item["modelled_potential_contacts"],
            )
        )
    await session.flush()
    return segment


async def exposure_segment_cells(
    session: AsyncSession, segment: ExposureSegment
) -> list[ExposureSegmentCell]:
    return list(
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


async def list_exposure_segments(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: UUID,
    source_link_id: UUID,
    admin: bool = False,
) -> list[ExposureSegment]:
    link = await _link_access(
        session,
        settings=settings,
        actor_user_id=actor_user_id,
        link_id=source_link_id,
        write=False,
        admin=admin,
    )
    return list(
        await session.scalars(
            select(ExposureSegment)
            .where(ExposureSegment.source_link_id == link.id)
            .order_by(ExposureSegment.version.desc())
        )
    )


async def exposure_segment_is_stale(
    session: AsyncSession, segment: ExposureSegment
) -> bool:
    link = await session.get(RetargetingSourceLink, segment.source_link_id)
    run = await session.get(MeasurementRun, segment.measurement_run_id)
    return (
        link is None
        or run is None
        or link.snapshot_sha256 != segment.source_link_snapshot_sha256
        or await link_is_stale(session, link)
        or run.input_manifest_sha256 != segment.measurement_input_sha256
        or run.result_manifest_sha256 != segment.measurement_result_sha256
        or run.proof_manifest_sha256 != segment.measurement_proof_sha256
        or not measurement_run_reproducible(run)
    )


def _zone_insight_response(*, campaign_id: UUID, state: str) -> HighExposureZoneInsightsRead:
    return HighExposureZoneInsightsRead(
        state=state,
        campaign_id=campaign_id,
        campaign_exposure_score=None,
        items=[],
        provenance=None,
        uncertainty=None,
        disclaimer=HIGH_EXPOSURE_ZONE_DISCLAIMER,
    )


def _zone_insight_uncertainty(run: MeasurementRun, score: ExposureScore) -> str:
    contact_uncertainty: str | None = None
    metrics = run.result_manifest.get("metrics")
    if isinstance(metrics, list):
        for metric in metrics:
            if (
                isinstance(metric, dict)
                and metric.get("id") == "modelled_potential_contacts"
                and isinstance(metric.get("uncertainty"), str)
                and metric["uncertainty"].strip()
            ):
                contact_uncertainty = metric["uncertainty"].strip()
                break
    score_uncertainty = score.result_snapshot.get("uncertainty")
    score_statement = (
        score_uncertainty.get("statement") if isinstance(score_uncertainty, dict) else None
    )
    if (
        not contact_uncertainty
        or not isinstance(score_statement, str)
        or not score_statement.strip()
    ):
        raise AppError(
            "ZONE_INSIGHT_UNCERTAINTY_MISSING",
            "Issued measurement and exposure-score uncertainty are required",
            status_code=status.HTTP_409_CONFLICT,
        )
    return f"{contact_uncertainty} {score_statement.strip()}"


async def high_exposure_zone_insights(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_user_id: UUID,
    campaign_id: UUID,
    admin: bool = False,
    measurement_run_id: UUID | None = None,
) -> HighExposureZoneInsightsRead:
    # The central disclosure gate is deliberately first: no membership,
    # campaign, run, score, segment, zone label, or ranking fact is read before it.
    await _privacy_gate(settings)
    organization_id: UUID | None = None
    if admin:
        await _active_admin(session, actor_user_id)
    else:
        organization_id = (
            await _advertiser_membership(session, actor_user_id=actor_user_id, write=False)
        ).organization_id
    campaign_filters = [Campaign.id == campaign_id]
    if organization_id is not None:
        campaign_filters.append(Campaign.organization_id == organization_id)
    campaign = await session.scalar(select(Campaign).where(*campaign_filters))
    if campaign is None:
        raise AppError(
            "CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=status.HTTP_404_NOT_FOUND
        )

    run_filters = [
        MeasurementRun.campaign_id == campaign.id,
        MeasurementRun.organization_id == campaign.organization_id,
    ]
    if measurement_run_id is not None:
        run_filters.append(MeasurementRun.id == measurement_run_id)
    else:
        run_filters.append(
            ~MeasurementRun.id.in_(
                select(MeasurementRun.reissue_of_run_id).where(
                    MeasurementRun.reissue_of_run_id.is_not(None)
                )
            )
        )
    run = await session.scalar(
        select(MeasurementRun)
        .where(*run_filters)
        .order_by(MeasurementRun.created_at.desc(), MeasurementRun.id.desc())
        .limit(1)
    )
    if run is None:
        return _zone_insight_response(campaign_id=campaign.id, state="empty")
    if not measurement_run_reproducible(run):
        return _zone_insight_response(campaign_id=campaign.id, state="stale")
    if not settings.privacy_disclosure_synthetic_test_mode and (
        run.test_only
        or not settings.measurement_live_issuance_authorized
        or not _approved_reference(settings.measurement_report_method_reference)
        or run.method_revision != settings.measurement_report_method_reference
    ):
        return _zone_insight_response(campaign_id=campaign.id, state="unavailable")

    score = await session.scalar(
        select(ExposureScore)
        .where(
            ExposureScore.measurement_run_id == run.id,
            ExposureScore.formula_version == "exposure_v1",
        )
        .order_by(ExposureScore.created_at.desc(), ExposureScore.id.desc())
        .limit(1)
    )
    if score is None:
        return _zone_insight_response(campaign_id=campaign.id, state="unavailable")
    from app.services.exposure_scores import exposure_score_is_stale

    if await exposure_score_is_stale(session, score):
        return _zone_insight_response(campaign_id=campaign.id, state="stale")
    if score.result_snapshot.get("status") != "scored" or not isinstance(
        score.result_snapshot.get("score"), str
    ):
        return _zone_insight_response(campaign_id=campaign.id, state="unavailable")

    segment_rows = list(
        await session.scalars(
            select(ExposureSegment)
            .where(
                ExposureSegment.organization_id == campaign.organization_id,
                ExposureSegment.campaign_id == campaign.id,
                ExposureSegment.measurement_run_id == run.id,
            )
            .order_by(
                ExposureSegment.source_link_id,
                ExposureSegment.version.desc(),
                ExposureSegment.id.desc(),
            )
        )
    )
    current_segments: list[ExposureSegment] = []
    seen_links: set[UUID] = set()
    for segment in segment_rows:
        if segment.source_link_id not in seen_links:
            seen_links.add(segment.source_link_id)
            current_segments.append(segment)
    if not current_segments:
        return _zone_insight_response(campaign_id=campaign.id, state="empty")

    expected_authority = {
        "formula_version": HIGH_EXPOSURE_ZONE_FORMULA_VERSION,
        "formula_fingerprint": HIGH_EXPOSURE_ZONE_FORMULA_FINGERPRINT,
        "exposure_score_id": str(score.id),
        "exposure_formula_version": score.formula_version,
        "exposure_formula_fingerprint": score.formula_fingerprint,
        "exposure_input_fingerprint": score.input_fingerprint,
        "exposure_result_fingerprint": score.result_fingerprint,
        "exposure_score_status": score.result_snapshot.get("status"),
        "campaign_exposure_score": score.result_snapshot.get("score"),
    }
    for segment in current_segments:
        if (
            await exposure_segment_is_stale(session, segment)
            or segment.snapshot.get("zone_insight_authority") != expected_authority
        ):
            return _zone_insight_response(campaign_id=campaign.id, state="stale")

    governed_rows: list[tuple[ExposureSegment, ExposureSegmentCell]] = []
    for segment in current_segments:
        cells = await exposure_segment_cells(session, segment)
        if any(
            not exposure_cell_meets_disclosure_floor(
                distinct_vehicle_count=cell.distinct_vehicle_count, settings=settings
            )
            for cell in cells
        ):
            return _zone_insight_response(campaign_id=campaign.id, state="suppressed")
        governed_rows.extend((segment, cell) for cell in cells)
    if not governed_rows:
        return _zone_insight_response(campaign_id=campaign.id, state="suppressed")

    deduplicated: dict[tuple[UUID, str, datetime, datetime, str], ExposureSegmentCell] = {}
    for segment, cell in governed_rows:
        identity = (
            segment.zone_id,
            cell.coverage_cell,
            _as_utc(cell.window_start_at),
            _as_utc(cell.window_end_at),
            cell.context,
        )
        prior = deduplicated.get(identity)
        if prior is not None and (
            prior.distinct_vehicle_count != cell.distinct_vehicle_count
            or prior.trip_count != cell.trip_count
            or prior.modelled_potential_contacts != cell.modelled_potential_contacts
        ):
            return _zone_insight_response(campaign_id=campaign.id, state="stale")
        deduplicated[identity] = cell

    totals: dict[UUID, ZoneInsightTotal] = {}
    for identity, cell in deduplicated.items():
        zone_id = identity[0]
        prior = totals.get(zone_id)
        totals[zone_id] = ZoneInsightTotal(
            zone_id=zone_id,
            modelled_potential_contacts=(
                (prior.modelled_potential_contacts if prior else Decimal("0"))
                + cell.modelled_potential_contacts
            ),
            trip_count=(prior.trip_count if prior else 0) + cell.trip_count,
        )
    ranked = rank_high_exposure_zones(list(totals.values()))
    zones = {
        zone.id: zone
        for zone in await session.scalars(
            select(CampaignZone).where(
                CampaignZone.campaign_id == campaign.id,
                CampaignZone.id.in_([item.zone_id for item in ranked]),
            )
        )
    }
    if len(zones) != len(ranked) or any(
        zones[item.zone_id].zone_type != "target" for item in ranked
    ):
        return _zone_insight_response(campaign_id=campaign.id, state="stale")

    return HighExposureZoneInsightsRead(
        state="ready",
        campaign_id=campaign.id,
        campaign_exposure_score=score.result_snapshot["score"],
        items=[
            HighExposureZoneItem(
                rank=item.rank,
                zone_id=item.zone_id,
                zone_name=zones[item.zone_id].name,
                modelled_potential_contacts=item.modelled_potential_contacts,
                trip_count=item.trip_count,
            )
            for item in ranked
        ],
        provenance=HighExposureZoneProvenance(
            formula_version=HIGH_EXPOSURE_ZONE_FORMULA_VERSION,
            formula_fingerprint=HIGH_EXPOSURE_ZONE_FORMULA_FINGERPRINT,
            measurement_run_id=run.id,
            exposure_score_id=score.id,
            exposure_formula_version=score.formula_version,
            exposure_formula_fingerprint=score.formula_fingerprint,
            exposure_input_fingerprint=score.input_fingerprint,
            source_segments=[
                ZoneInsightSegmentProvenance(
                    segment_id=segment.id,
                    segment_version=segment.version,
                    segment_snapshot_sha256=segment.snapshot_sha256,
                    reissue_of_segment_id=segment.reissue_of_segment_id,
                )
                for segment in sorted(current_segments, key=lambda item: item.id)
            ],
        ),
        uncertainty=_zone_insight_uncertainty(run, score),
        disclaimer=HIGH_EXPOSURE_ZONE_DISCLAIMER,
    )

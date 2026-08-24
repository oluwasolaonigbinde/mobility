from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
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
from app.schemas.retargeting_sources import RetargetingSourceCreate
from app.services.audit import create_audit_event
from app.services.disclosure import ensure_disclosure_live_gate
from app.services.payout_rule_serialization import database_clock


def _canonical_hash(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _source_status(source: RetargetingSource, now: datetime) -> str:
    if source.status == "deactivated":
        return "deactivated"
    expires_at = source.expires_at
    if expires_at.tzinfo is None or expires_at.tzinfo.utcoffset(expires_at) is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return "expired" if expires_at <= now else "active"


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
        .order_by(OrganizationMembership.created_at.desc())
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
    session: AsyncSession, *, actor_user_id: UUID, operation: str, key: str, fingerprint: str
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
    session: AsyncSession, *, settings: Settings
) -> list[RetargetingSource]:
    await _privacy_gate(settings)
    return list(
        await session.scalars(
            select(RetargetingSource).order_by(RetargetingSource.created_at.desc())
        )
    )


async def get_admin_retargeting_source(
    session: AsyncSession, *, settings: Settings, source_id: UUID
) -> RetargetingSource:
    await _privacy_gate(settings)
    source = await session.get(RetargetingSource, source_id)
    if source is None:
        raise _source_not_found()
    return source


async def source_effective_status(session: AsyncSession, source: RetargetingSource) -> str:
    return _source_status(source, await database_clock(session))

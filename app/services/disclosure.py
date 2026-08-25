from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.disclosure import DisclosureQueryDecision
from app.models.organization import AdvertiserOrganization, OrganizationMembership

DISCLOSURE_ROUTE_INVENTORY = frozenset(
    {
        "advertiser.dashboard.summary",
        "advertiser.campaign.summary",
        "advertiser.campaign.daily_metrics",
        "advertiser.campaign.trips",
        "advertiser.campaign.report",
        "advertiser.campaign.impressions_summary",
        "advertiser.campaign.heatmap",
        "admin.heatmap",
    }
)

_PLACEHOLDERS = {"", "missing", "todo", "tbd", "placeholder", "n/a", "none"}
_DEFAULT_WINDOW_START = datetime(2000, 1, 1, tzinfo=UTC)
_DEFAULT_WINDOW_END = datetime(2100, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class DisclosureQuery:
    route_id: str
    principal_id: UUID
    tenant_id: UUID | None
    campaign_id: UUID | None
    start_at: datetime | None
    end_at: datetime | None
    filters: dict[str, Any]


def _approved_reference(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized not in _PLACEHOLDERS and not normalized.startswith("ext-")


def ensure_disclosure_live_gate(settings: Settings, *, requires_measurement_run: bool) -> None:
    if settings.privacy_disclosure_synthetic_test_mode:
        return
    references = (
        settings.privacy_legal_approval_reference,
        settings.privacy_disclosure_config_reference,
        settings.privacy_query_history_retention_reference,
    )
    if not settings.privacy_disclosure_live_authorized or not all(
        _approved_reference(reference) for reference in references
    ):
        raise AppError(
            "PRIVACY_LIVE_USE_BLOCKED",
            "Advertiser analytics are unavailable until privacy approval and disclosure "
            "controls are complete",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if requires_measurement_run:
        raise AppError(
            "SAFE_MEASUREMENT_RUN_REQUIRED",
            "This output remains unavailable until immutable measurement runs are implemented",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


async def require_governed_advertiser_output(
    session: AsyncSession,
    *,
    settings: Settings,
    route_id: str,
    user_id: UUID,
    requires_measurement_run: bool = True,
) -> UUID:
    if route_id not in DISCLOSURE_ROUTE_INVENTORY:
        raise RuntimeError(f"Unregistered disclosure route: {route_id}")
    ensure_disclosure_live_gate(
        settings,
        requires_measurement_run=requires_measurement_run,
    )
    row = (
        await session.execute(
            select(AdvertiserOrganization.id)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id == AdvertiserOrganization.id,
            )
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == "active",
                AdvertiserOrganization.status == "active",
            )
            .order_by(
                OrganizationMembership.created_at.desc(),
                OrganizationMembership.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise AppError(
            "ADVERTISER_ORGANIZATION_NOT_FOUND",
            "Advertiser organization was not found for the current user",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return row


def _canonical_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _principal_hash(principal_id: UUID) -> str:
    return hashlib.sha256(f"disclosure-principal-v1:{principal_id}".encode()).hexdigest()


def _window(query: DisclosureQuery) -> tuple[datetime, datetime]:
    return query.start_at or _DEFAULT_WINDOW_START, query.end_at or _DEFAULT_WINDOW_END


async def _lock_spatial_history(session: AsyncSession) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    lock_digest = hashlib.sha256(b"disclosure-spatial-history-v1").digest()[:8]
    lock_key = int.from_bytes(lock_digest, "big", signed=True)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})


def disclosure_suppressed(reason: str) -> AppError:
    return AppError(
        "DISCLOSURE_SUPPRESSED",
        "The requested aggregate is unavailable under the privacy disclosure floor",
        status_code=status.HTTP_409_CONFLICT,
        details={"reason": reason},
    )


async def record_heatmap_disclosure(
    session: AsyncSession,
    *,
    query: DisclosureQuery,
    settings: Settings,
    has_releasable_cells: bool,
    result_hash: str,
) -> None:
    if query.route_id not in {"advertiser.campaign.heatmap", "admin.heatmap"}:
        raise RuntimeError("Heatmap disclosure history received a non-heatmap route")
    ensure_disclosure_live_gate(settings, requires_measurement_run=False)
    if settings.privacy_disclosure_synthetic_test_mode:
        return
    principal_hash = _principal_hash(query.principal_id)
    scope_hash = _canonical_hash(
        {
            "tenant_id": query.tenant_id,
            "campaign_id": query.campaign_id,
            "family": "spatial_aggregate_v1",
        }
    )
    window_start, window_end = _window(query)
    query_hash = _canonical_hash(
        {
            "route_id": query.route_id,
            "scope_hash": scope_hash,
            "window_start": window_start,
            "window_end": window_end,
            "filters": query.filters,
        }
    )
    await _lock_spatial_history(session)
    now = datetime.now(UTC)
    await session.execute(
        delete(DisclosureQueryDecision).where(DisclosureQueryDecision.expires_at <= now)
    )
    exact = await session.scalar(
        select(DisclosureQueryDecision).where(
            DisclosureQueryDecision.principal_hash == principal_hash,
            DisclosureQueryDecision.scope_hash == scope_hash,
            DisclosureQueryDecision.query_hash == query_hash,
            DisclosureQueryDecision.result_hash == result_hash,
        )
    )
    if exact is not None:
        if exact.decision == "suppressed":
            raise disclosure_suppressed(exact.reason)
        return

    if query.tenant_id is None:
        overlap_scope = True
    elif query.campaign_id is None:
        overlap_scope = or_(
            DisclosureQueryDecision.tenant_id.is_(None),
            DisclosureQueryDecision.tenant_id == query.tenant_id,
        )
    else:
        overlap_scope = or_(
            DisclosureQueryDecision.tenant_id.is_(None),
            and_(
                DisclosureQueryDecision.tenant_id == query.tenant_id,
                or_(
                    DisclosureQueryDecision.campaign_id.is_(None),
                    DisclosureQueryDecision.campaign_id == query.campaign_id,
                ),
            ),
        )
    prior = await session.scalar(
        select(DisclosureQueryDecision.id).where(
            overlap_scope,
            DisclosureQueryDecision.expires_at > now,
            DisclosureQueryDecision.window_start <= window_end,
            DisclosureQueryDecision.window_end >= window_start,
        ).limit(1)
    )
    decision = "served"
    reason = "privacy_floor_passed"
    if prior is not None:
        decision = "suppressed"
        reason = "overlapping_query_differencing"
    elif not has_releasable_cells:
        decision = "suppressed"
        reason = "minimum_counts_or_contributor_cap"
    session.add(
        DisclosureQueryDecision(
            principal_hash=principal_hash,
            scope_hash=scope_hash,
            query_hash=query_hash,
            result_hash=result_hash,
            tenant_id=query.tenant_id,
            campaign_id=query.campaign_id,
            output_class=query.route_id,
            decision=decision,
            reason=reason,
            window_start=window_start,
            window_end=window_end,
            expires_at=now + timedelta(days=settings.privacy_query_history_retention_days),
        )
    )
    await session.commit()
    if decision == "suppressed":
        raise disclosure_suppressed(reason)

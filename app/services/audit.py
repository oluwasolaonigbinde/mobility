from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.core.observability import scrub_observability_value
from app.models.audit import AuditEvent
from app.models.billing import CommercialTerms
from app.models.user import User


async def create_audit_event(
    session: AsyncSession,
    *,
    actor_user_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        event_metadata=scrub_observability_value(metadata or {}, semantic_context=entity_type),
    )
    session.add(event)
    await session.flush()
    return event


async def list_audit_events(
    session: AsyncSession,
    *,
    action: str | None,
    entity_type: str | None,
    entity_id: str | None,
    actor_user_id: UUID | None,
    campaign_id: UUID | None = None,
    created_from: datetime | None,
    created_to: datetime | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[AuditEvent, str | None, str | None]], int]:
    filters = []
    if action is not None:
        filters.append(AuditEvent.action == action)
    if entity_type is not None:
        filters.append(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        filters.append(AuditEvent.entity_id == entity_id)
    if actor_user_id is not None:
        filters.append(AuditEvent.actor_user_id == actor_user_id)
    if campaign_id is not None:
        terms_ids = select(cast(CommercialTerms.id, String)).where(
            CommercialTerms.campaign_id == campaign_id
        )
        filters.append(
            or_(
                and_(
                    AuditEvent.entity_type == "campaign", AuditEvent.entity_id == str(campaign_id)
                ),
                and_(
                    AuditEvent.entity_type.in_(
                        ["campaign_cancellation", "commercial_quote_request", "refund_settlement"]
                    ),
                    AuditEvent.event_metadata["campaign_id"].as_string() == str(campaign_id),
                ),
                and_(
                    AuditEvent.entity_type == "refund_settlement",
                    AuditEvent.event_metadata["commercial_terms_id"].as_string().in_(terms_ids),
                ),
            )
        )
    if created_from is not None:
        filters.append(AuditEvent.created_at >= created_from)
    if created_to is not None:
        filters.append(AuditEvent.created_at <= created_to)

    total = await session.scalar(select(func.count()).select_from(AuditEvent).where(*filters))
    result = await session.execute(
        select(AuditEvent, User.email, User.full_name)
        .outerjoin(User, User.id == AuditEvent.actor_user_id)
        .where(*filters)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list(result.all())
    for event, _email, _name in rows:
        set_committed_value(
            event,
            "event_metadata",
            scrub_observability_value(
                event.event_metadata,
                semantic_context=event.entity_type,
            ),
        )
    return rows, int(total or 0)

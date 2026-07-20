from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.dependencies import AdminUserDependency, SessionDependency
from app.schemas.audit import AuditEventListResponse, AuditEventRead
from app.services.audit import list_audit_events

router = APIRouter(prefix="/admin/audit-events", tags=["Admin Audit"])


@router.get("", response_model=AuditEventListResponse, summary="List audit events")
async def admin_list_audit_events(
    current_user: AdminUserDependency,
    session: SessionDependency,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_user_id: UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventListResponse:
    del current_user
    rows, total = await list_audit_events(
        session,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
    return AuditEventListResponse(
        items=[
            AuditEventRead(
                id=event.id,
                actor_user_id=event.actor_user_id,
                actor_email=email,
                action=event.action,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                metadata=event.event_metadata,
                created_at=event.created_at,
            )
            for event, email in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )

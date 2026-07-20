from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditEventRead(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    actor_email: str | None
    action: str
    entity_type: str
    entity_id: str | None
    metadata: dict[str, Any]
    created_at: datetime


class AuditEventListResponse(BaseModel):
    items: list[AuditEventRead]
    total: int
    limit: int
    offset: int

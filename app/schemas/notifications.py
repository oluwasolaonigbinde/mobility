from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.notification import NotificationType


class DriverNotificationRead(BaseModel):
    id: UUID
    type_key: NotificationType
    template_version: str
    fraud_flag_id: UUID
    trip_session_id: UUID
    outcome: str | None = None
    fraud_dispute_id: UUID | None = None
    created_at: datetime

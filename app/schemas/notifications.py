from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.notification import NotificationChannel, NotificationType


class DriverNotificationRead(BaseModel):
    id: UUID
    type_key: NotificationType
    template_version: str
    fraud_flag_id: UUID | None = None
    trip_session_id: UUID | None = None
    activity_flag_id: UUID | None = None
    assignment_id: UUID | None = None
    outcome: str | None = None
    fraud_dispute_id: UUID | None = None
    created_at: datetime


class NotificationFeedItemRead(BaseModel):
    id: UUID
    type_key: NotificationType
    channel: NotificationChannel
    title: str
    body: str
    created_at: datetime
    read_at: datetime | None


class NotificationFeedListRead(BaseModel):
    items: list[NotificationFeedItemRead]
    total: int
    limit: int
    offset: int


class NotificationUnreadCountRead(BaseModel):
    unread_count: int


class AdvertiserNotificationPreferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transactional_email_enabled: bool
    in_app_enabled: bool = True


class AdvertiserNotificationPreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transactional_email_enabled: bool = Field()

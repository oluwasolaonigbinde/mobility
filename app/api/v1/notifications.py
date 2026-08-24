"""Notification persistence is intentionally API-private until W2-04A."""

from app.models.notification import Notification
from app.schemas.notifications import DriverNotificationRead


def driver_notification_response(notice: Notification) -> DriverNotificationRead:
    # Persisted JSON is never returned wholesale. Legacy or malformed payloads
    # fail closed at the DTO boundary instead of leaking future/internal keys.
    return DriverNotificationRead(
        id=notice.id,
        type_key=notice.type_key,
        template_version=notice.template_version,
        fraud_flag_id=notice.payload.get("fraud_flag_id"),
        trip_session_id=notice.payload.get("trip_session_id"),
        outcome=(
            notice.payload.get("outcome")
            if notice.payload.get("outcome") in {"confirmed", "dismissed"}
            else None
        ),
        fraud_dispute_id=notice.payload.get("fraud_dispute_id"),
        created_at=notice.created_at,
    )

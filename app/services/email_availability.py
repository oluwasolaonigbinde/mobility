"""Availability checks for actions whose next step requires an email."""

from app.adapters.messaging.email import email_is_available
from app.core.config import Settings
from app.core.errors import AppError

INVITE_UNAVAILABLE = "Emails aren't connected yet, so this invite can't be sent."
RESET_UNAVAILABLE = "Password reset isn't available right now. Please contact Terrax Media."
APPLICATION_UNAVAILABLE = (
    "Driver applications aren't available right now. Please contact Terrax Media."
)
APPLICATION_LINK_UNAVAILABLE = (
    "Application links aren't available right now. Please contact Terrax Media."
)


def require_email(settings: Settings, message: str) -> None:
    if not email_is_available(settings):
        raise AppError("EMAIL_NOT_CONFIGURED", message, status_code=503)

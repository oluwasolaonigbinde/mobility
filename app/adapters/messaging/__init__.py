from app.adapters.messaging.email import (
    DisabledEmailAdapter,
    EmailAdapter,
    EmailMessage,
    EmailSendError,
    EmailSubmission,
    SmtpEmailAdapter,
    build_email_adapter,
)

__all__ = [
    "DisabledEmailAdapter",
    "EmailAdapter",
    "EmailMessage",
    "EmailSendError",
    "EmailSubmission",
    "SmtpEmailAdapter",
    "build_email_adapter",
]

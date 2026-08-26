import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as SmtpMessage
from email.utils import formataddr
from typing import Protocol

from app.core.config import Settings


class EmailSendError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class EmailMessage:
    recipient: str
    subject: str
    text_body: str
    html_body: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class EmailSubmission:
    provider_message_id: str


class EmailAdapter(Protocol):
    async def send(self, message: EmailMessage) -> EmailSubmission: ...


class DisabledEmailAdapter:
    async def send(self, message: EmailMessage) -> EmailSubmission:
        del message
        raise EmailSendError("email_provider_unconfigured", retryable=True)


class SmtpEmailAdapter:
    """Provider-neutral SMTP adapter used by local Mailpit and compatible relays."""

    def __init__(self, settings: Settings) -> None:
        self.host = settings.email_smtp_host
        self.port = settings.email_smtp_port
        self.username = settings.email_smtp_username
        self.password = (
            settings.email_smtp_password.get_secret_value()
            if settings.email_smtp_password is not None
            else None
        )
        self.use_starttls = settings.email_smtp_starttls
        self.sender_address = settings.email_sender_address
        self.sender_name = settings.email_sender_name
        self.message_id_domain = self.sender_address.rsplit("@", 1)[-1]
        if not self.host or not self.sender_address:
            raise ValueError("SMTP host and sender address must be configured")

    async def send(self, message: EmailMessage) -> EmailSubmission:
        provider_message_id = f"<{message.idempotency_key}@{self.message_id_domain}>"
        smtp_message = SmtpMessage()
        smtp_message["From"] = formataddr((self.sender_name, self.sender_address))
        smtp_message["To"] = message.recipient
        smtp_message["Subject"] = message.subject
        smtp_message["Message-ID"] = provider_message_id
        smtp_message["X-Cardvert-Idempotency-Key"] = message.idempotency_key
        smtp_message.set_content(message.text_body)
        smtp_message.add_alternative(message.html_body, subtype="html")

        def deliver() -> None:
            try:
                with smtplib.SMTP(self.host, self.port, timeout=15) as client:
                    if self.use_starttls:
                        client.starttls()
                    if self.username:
                        client.login(self.username, self.password or "")
                    client.send_message(smtp_message)
            except smtplib.SMTPRecipientsRefused as exc:
                raise EmailSendError("email_recipient_rejected", retryable=False) from exc
            except (OSError, smtplib.SMTPException) as exc:
                raise EmailSendError("email_provider_unavailable", retryable=True) from exc

        await asyncio.to_thread(deliver)
        return EmailSubmission(provider_message_id=provider_message_id)


def build_email_adapter(settings: Settings) -> EmailAdapter:
    if (
        settings.email_provider == "smtp"
        and settings.email_smtp_host
        and settings.email_sender_address
    ):
        return SmtpEmailAdapter(settings)
    return DisabledEmailAdapter()

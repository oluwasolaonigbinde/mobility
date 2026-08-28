import json
import logging
import re
from datetime import UTC, datetime

import sentry_sdk

from app.core.config import Settings
from app.core.middleware import get_request_id

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|cookie|token|password|secret|api[_-]?key|nin|bvn|"
    r"kyc|fraud(?:[_-]?evidence)?|evidence|bank(?:[_-]?account)?|lat(?:itude)?|"
    r"lon(?:gitude)?|gps|coord(?:inate)?s?|(?:private|signed|presigned|download|"
    r"storage|object)[_-]?url|url)"
    r"\s*[=:]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_SENSITIVE_KEY = re.compile(
    r"(?i)^(authorization|cookie|token|password|secret|api[_-]?key|nin|bvn|"
    r"kyc|fraud(?:[_-]?evidence)?|evidence|bank(?:[_-]?account)?|lat(?:itude)?|"
    r"lon(?:gitude)?|gps|coord(?:inate)?s?|(?:private|signed|presigned|download|"
    r"storage|object)[_-]?url|url)$"
)
_QUOTED_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(?P<quote>['\"])(?P<key>authorization|cookie|token|password|secret|"
    r"api[_-]?key|nin|bvn|kyc|fraud(?:[_-]?evidence)?|evidence|"
    r"bank(?:[_-]?account)?|lat(?:itude)?|lon(?:gitude)?|gps|coord(?:inate)?s?|"
    r"(?:private|signed|presigned|download|storage|object)[_-]?url|url)"
    r"(?P=quote)\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+)"
)


def redact_log_message(message: str) -> str:
    redacted = _QUOTED_SENSITIVE_ASSIGNMENT.sub(
        lambda match: (
            f'{match.group("quote")}{match.group("key")}{match.group("quote")}="[REDACTED]"'
        ),
        message,
    )
    return _SENSITIVE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)


class JsonLogFormatter(logging.Formatter):
    def __init__(self, *, service: str, release_revision: str) -> None:
        super().__init__()
        self.service = service
        self.release_revision = release_revision

    def format(self, record: logging.LogRecord) -> str:
        safe_message = scrub_observability_value(record.msg)
        safe_arguments = scrub_observability_value(record.args)
        try:
            message = str(safe_message) % safe_arguments if safe_arguments else str(safe_message)
        except (TypeError, ValueError):
            message = f"{redact_log_message(str(safe_message))} [REDACTED_ARGUMENTS]"
        payload = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "service": self.service,
            "release_revision": self.release_revision,
            "logger": record.name,
            "request_id": get_request_id(),
            "message": redact_log_message(message),
        }
        if record.exc_info:
            payload["exception"] = "[REDACTED_EXCEPTION]"
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def configure_logging(settings: Settings, *, service: str) -> None:
    if settings.log_format != "json":
        return
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    for handler in root.handlers:
        if getattr(handler, "_cardvert_json", False):
            handler.setFormatter(
                JsonLogFormatter(service=service, release_revision=settings.release_revision)
            )
            return
    handler = logging.StreamHandler()
    handler._cardvert_json = True  # type: ignore[attr-defined]
    handler.setFormatter(
        JsonLogFormatter(service=service, release_revision=settings.release_revision)
    )
    root.handlers.clear()
    root.addHandler(handler)


def scrub_observability_value(value):
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if _SENSITIVE_KEY.fullmatch(str(key))
                else scrub_observability_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub_observability_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub_observability_value(item) for item in value)
    if isinstance(value, str):
        return redact_log_message(value)
    return value


def _before_send(event, _hint):
    return scrub_observability_value(event)


def init_error_tracking(settings: Settings) -> None:
    dsn = settings.sentry_dsn.strip()
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        release=settings.release_revision or None,
        traces_sample_rate=0.0,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        before_send=_before_send,
    )


def capture_exception(exc: Exception) -> None:
    sentry_sdk.capture_exception(exc)

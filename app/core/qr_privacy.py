"""Keep public scan requests out of application access logs and error telemetry."""

import logging
from urllib.parse import urlsplit

import sentry_sdk


def scan_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return urlsplit(value).path.startswith(("/q/", "/api/v1/qr/"))
    except ValueError:
        return False


class ScanAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn's access tuple: client, method, full path, version, status.
        args = record.args
        return not (isinstance(args, tuple) and len(args) >= 3 and scan_path(args[2]))


def scan_event_filter(event, hint):
    del hint
    request = event.get("request") or {}
    if scan_path(request.get("url")) or "/api/v1/qr/" in event.get("transaction", ""):
        return None
    return event


def install_scan_privacy() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, ScanAccessFilter) for item in logger.filters):
        logger.addFilter(ScanAccessFilter())
        sentry_sdk.get_global_scope().add_event_processor(scan_event_filter)

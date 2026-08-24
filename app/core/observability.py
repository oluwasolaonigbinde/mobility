import sentry_sdk

from app.core.config import Settings


def init_error_tracking(settings: Settings) -> None:
    dsn = settings.sentry_dsn.strip()
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=0.0,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
    )


def capture_exception(exc: Exception) -> None:
    sentry_sdk.capture_exception(exc)

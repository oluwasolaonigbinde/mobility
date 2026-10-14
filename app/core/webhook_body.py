"""Bound unauthenticated webhook buffering without transforming signed bytes."""

from starlette.requests import Request

from app.core.errors import AppError

# Charge/transfer notifications are small JSON documents. Keep generous room for
# provider metadata while bounding each public request to the same edge limit.
WEBHOOK_MAX_BODY_BYTES = 1024 * 1024


def _oversize() -> AppError:
    return AppError(
        "WEBHOOK_BODY_TOO_LARGE", "Webhook body exceeds the 1 MiB limit", status_code=413
    )


async def read_webhook_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            declared_size = int(declared)
        except ValueError:
            declared_size = 0
        if declared_size > WEBHOOK_MAX_BODY_BYTES:
            raise _oversize()
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > WEBHOOK_MAX_BODY_BYTES:
            raise _oversize()
        payload.extend(chunk)
    return bytes(payload)

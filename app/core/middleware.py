from contextvars import ContextVar
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import Settings

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_scan_request: ContextVar[bool] = ContextVar("scan_request", default=False)


def get_request_id() -> str | None:
    return _request_id.get()


def is_scan_path(path: str) -> bool:
    return path.startswith(("/q/", "/api/v1/qr/"))


def is_scan_request() -> bool:
    return _scan_request.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self.header_name = settings.request_id_header

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(self.header_name) or str(uuid4())
        request.state.request_id = request_id
        token = _request_id.set(request_id)
        scan_token = _scan_request.set(is_scan_path(request.url.path))
        try:
            response = await call_next(request)
        except Exception as exc:
            exc.__dict__["_cardvert_request_id"] = request_id
            if is_scan_request():
                exc.__dict__["_cardvert_scan_request"] = True
            raise
        finally:
            _request_id.reset(token)
            _scan_request.reset(scan_token)
        response.headers[self.header_name] = request_id
        return response

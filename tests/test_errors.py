from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app


def test_app_error_uses_standard_envelope() -> None:
    app = create_app()

    @app.get("/test-error")
    async def test_error() -> None:
        raise AppError("TEST_ERROR", "Test error", status_code=status.HTTP_409_CONFLICT)

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/test-error", headers={"X-Request-ID": "req-test"})

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "error": {
            "code": "TEST_ERROR",
            "message": "Test error",
            "details": {},
            "request_id": "req-test",
        }
    }


def test_unhandled_exception_uses_standard_envelope(monkeypatch) -> None:
    captured: list[Exception] = []
    monkeypatch.setattr("app.core.observability.sentry_sdk.capture_exception", captured.append)
    app = create_app()

    @app.get("/test-unhandled-error")
    async def test_unhandled_error() -> None:
        raise RuntimeError("sensitive internal detail")

    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-unhandled-error", headers={"X-Request-ID": "req-unhandled"})

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "details": {},
            "request_id": "req-unhandled",
        }
    }
    assert len(captured) == 1
    assert isinstance(captured[0], RuntimeError)


def test_error_tracking_is_inert_without_dsn(monkeypatch) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )

    create_app(Settings(sentry_dsn=""))

    assert init_calls == []


def test_error_tracking_uses_privacy_safe_defaults(monkeypatch) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )

    create_app(Settings(sentry_dsn="https://public@example.invalid/1"))

    assert init_calls == [
        {
            "dsn": "https://public@example.invalid/1",
            "traces_sample_rate": 0.0,
            "send_default_pii": False,
            "include_local_variables": False,
            "max_request_body_size": "never",
        }
    ]

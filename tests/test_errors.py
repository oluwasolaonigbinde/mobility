from starlette import status

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

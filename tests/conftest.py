from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_name="mobility-adtech-api",
        environment="test",
        database_url=None,
        redis_url=None,
        backend_cors_origins=["http://localhost:3000"],
    )


@pytest.fixture
def client(settings: Settings) -> Generator[TestClient, None, None]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client

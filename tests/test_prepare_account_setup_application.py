"""Safety contract for the connected account-setup E2E fixture."""

import asyncio
import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "frontend/e2e/support/prepare-account-setup-application.py"
)
SPEC = importlib.util.spec_from_file_location("prepare_account_setup_application", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
SCRIPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCRIPT)

ISOLATED_E2E_DATABASE_URL = "postgresql+asyncpg://mobility:mobility@db:5432/mobility"


class StubSettings:
    def __init__(self, *, environment: str, database_url: str | None) -> None:
        self.environment = environment
        self.database_url = database_url
        self.model_copy_called = False

    def model_copy(self, *, update: dict[str, object]):
        self.model_copy_called = True
        for name, value in update.items():
            setattr(self, name, value)
        return self


@pytest.mark.parametrize(
    ("environment", "database_url"),
    [
        ("local", ISOLATED_E2E_DATABASE_URL),
        ("testing", ISOLATED_E2E_DATABASE_URL),
        ("production", ISOLATED_E2E_DATABASE_URL),
        ("test", None),
        ("test", "not-a-database-url"),
        ("test", "postgresql+psycopg://mobility:mobility@db:5432/mobility"),
        ("test", "postgresql+asyncpg://other:mobility@db:5432/mobility"),
        ("test", "postgresql+asyncpg://mobility:other@db:5432/mobility"),
        ("test", "postgresql+asyncpg://mobility:mobility@prod.example.com:5432/mobility"),
        ("test", "postgresql+asyncpg://mobility:mobility@db:5433/mobility"),
        ("test", "postgresql+asyncpg://mobility:mobility@db:5432/other"),
        ("test", f"{ISOLATED_E2E_DATABASE_URL}?ssl=require"),
    ],
)
def test_unsafe_configuration_is_refused_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    database_url: str | None,
) -> None:
    settings = StubSettings(environment=environment, database_url=database_url)
    database_accessed = False

    def reject_engine_creation(_database_url: str):
        nonlocal database_accessed
        database_accessed = True
        raise AssertionError("database engine creation must not be reached")

    monkeypatch.setattr(SCRIPT, "get_settings", lambda: settings)
    monkeypatch.setattr(SCRIPT, "create_async_engine", reject_engine_creation)

    with pytest.raises(RuntimeError, match="isolated account-setup E2E database"):
        asyncio.run(SCRIPT.main())

    assert database_accessed is False
    assert settings.model_copy_called is False


@pytest.mark.parametrize(
    "database_url",
    [
        ISOLATED_E2E_DATABASE_URL,
        "postgresql+asyncpg://mobility:mobility@db/mobility",
    ],
)
def test_exact_test_compose_authority_is_accepted_without_relabelling_environment(
    database_url: str,
) -> None:
    settings = StubSettings(environment="test", database_url=database_url)

    validated = SCRIPT.validate_isolated_e2e_settings(settings)

    assert validated is settings
    assert settings.environment == "test"
    assert settings.database_url == database_url
    assert settings.model_copy_called is False

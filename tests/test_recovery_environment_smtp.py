import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.adapters.messaging.email import EmailMessage, SmtpEmailAdapter
from app.core.config import Settings


@pytest.mark.parametrize("environment", [None, "", "prod", "invalid"])
@pytest.mark.parametrize(
    "entrypoint",
    ["settings", "api", "worker", "alembic", "openapi", "seed"],
)
def test_environment_required_at_real_entrypoints(tmp_path, environment, entrypoint):
    # Neither the repository .env nor pytest's explicit test mode may hide a missing mode.
    (tmp_path / ".env").write_text("", encoding="utf-8")
    env = os.environ.copy()
    env.pop("ENVIRONMENT", None)
    if environment is not None:
        env["ENVIRONMENT"] = environment
    root = Path(__file__).resolve().parents[1]
    env.update(PYTHONPATH=str(root), DATABASE_URL="", REDIS_URL="", ALLOW_DEMO_SEED="false")
    config = tmp_path / "alembic.ini"
    config.write_text(
        (root / "alembic.ini")
        .read_text()
        .replace("script_location = alembic", f"script_location = {root / 'alembic'}")
    )
    commands = {
        "settings": ["-c", "from app.core.config import get_settings; get_settings()"],
        "api": ["-c", "import app.main"],
        "worker": ["-c", "import app.jobs.worker_entry"],
        "alembic": ["-m", "alembic", "-c", str(config), "upgrade", "head", "--sql"],
        "openapi": [str(root / "scripts/update_openapi_snapshot.py"), "--check"],
        "seed": ["-m", "app.seeds.demo"],
    }
    result = subprocess.run(
        [sys.executable, *commands[entrypoint]],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "environment" in result.stderr.lower()


@pytest.mark.parametrize("environment", ["local", "dev", "development", "test", "testing"])
def test_explicit_local_modes_and_normalization(environment):
    settings = Settings(_env_file=None, environment=f" {environment.upper()} ")
    assert settings.environment == environment
    assert settings.trip_evidence_signing_keys


def test_nonlocal_smtp_refuses_plaintext():
    with pytest.raises(ValidationError, match="SMTP.*TLS"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret_key="production-secret-with-at-least-32-characters",
            database_url="postgresql+asyncpg://mobility:synthetic-db-secret@db:5432/mobility?ssl=require",
            redis_url="rediss://:synthetic-redis-secret@redis:6379/0",
            email_provider="smtp",
            email_smtp_host="smtp.terrax.invalid",
            email_sender_address="sender@terrax.invalid",
            email_smtp_starttls=False,
        )


def test_direct_smtp_adapter_cannot_bypass_transport_requirement():
    settings = Settings(
        environment="test",
        email_smtp_host="localhost",
        email_sender_address="fixture@cardvert.invalid",
    ).model_copy(update={"environment": "production"})
    with pytest.raises(ValueError, match="SMTP.*TLS"):
        SmtpEmailAdapter(settings)


def test_smtp_starttls_uses_verifying_context_before_auth(monkeypatch):
    import ssl

    calls = []

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, *, context=None):
            assert context is not None
            assert context.verify_mode == ssl.CERT_REQUIRED
            assert context.check_hostname is True
            calls.append("tls")

        def login(self, *args):
            assert calls == ["tls"]
            calls.append("auth")

        def send_message(self, message):
            assert calls == ["tls", "auth"]
            calls.append("data")

    monkeypatch.setattr("app.adapters.messaging.email.smtplib.SMTP", SMTP)
    settings = Settings(
        _env_file=None,
        environment="test",
        email_smtp_host="localhost",
        email_sender_address="sender@terrax.invalid",
        email_smtp_starttls=True,
        email_smtp_username="synthetic-user",
    )
    asyncio.run(
        SmtpEmailAdapter(settings).send(
            EmailMessage(
                recipient="recipient@terrax.invalid",
                subject="Synthetic test",
                text_body="test",
                html_body="<p>test</p>",
                idempotency_key="synthetic-test",
            )
        )
    )
    assert calls == ["tls", "auth", "data"]

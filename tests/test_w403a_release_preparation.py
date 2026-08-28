from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.observability import (
    JsonLogFormatter,
    configure_logging,
    scrub_observability_value,
)
from scripts.release_contract import (
    ContractError,
    build_backup_manifest,
    validate_backup_manifest,
    validate_compatibility_evidence,
    validate_compose_model,
    validate_release_environment,
    validate_release_state,
)

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_COMPOSE = ROOT / "docker-compose.production.yml"
PRODUCTION_ENV = ROOT / "production.env.example"


def production_model(*, profiles: tuple[str, ...] = ()) -> dict:
    command = ["docker", "compose", "-f", str(PRODUCTION_COMPOSE)]
    for profile in profiles:
        command.extend(("--profile", profile))
    command.extend(("--env-file", str(PRODUCTION_ENV), "config", "--format", "json"))
    result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def valid_release_environment(tmp_path: Path) -> dict[str, str]:
    passphrase = tmp_path / "backup-passphrase"
    passphrase.write_text("Release-Backup-Passphrase-Kept-Outside-Repository-2026!\n")
    passphrase.chmod(0o600)
    return {
        "ENVIRONMENT": "production",
        "RELEASE_ID": "20260828T120000Z-1715fe53",
        "RELEASE_REVISION": "1715fe53b19972cd6db829a08a9d6cf572fbd656",
        "BACKEND_IMAGE": "registry.invalid/cardvert/backend@sha256:" + "1" * 64,
        "FRONTEND_IMAGE": "registry.invalid/cardvert/frontend@sha256:" + "2" * 64,
        "POSTGIS_IMAGE": "postgis/postgis@sha256:" + "3" * 64,
        "REDIS_IMAGE": "redis@sha256:" + "4" * 64,
        "CADDY_IMAGE": "caddy@sha256:" + "5" * 64,
        "EDGE_HOSTNAME": "cardvert.example.com",
        "PUBLIC_ORIGIN": "https://cardvert.example.com",
        "BACKEND_CORS_ORIGINS": "[]",
        "POSTGRES_PASSWORD": "Correct-Horse-Battery-Staple-Database-2026",
        "DATABASE_URL": (
            "postgresql+asyncpg://mobility:Correct-Horse-Battery-Staple-Database-2026"
            "@db:5432/mobility"
        ),
        "REDIS_PASSWORD": "Correct-Horse-Battery-Staple-Redis-2026",
        "REDIS_URL": "redis://:Correct-Horse-Battery-Staple-Redis-2026@redis:6379/0",
        "JWT_SECRET_KEY": "Jwt-release-secret-with-more-than-thirty-two-random-characters-2026",
        "PAYOUT_CRYPTO_KEYRING_B64": ('{"1":"yPdM2Hgg3Q1M+MS4iF26TyMQmmuUOMf7p9hNSMlcycI="}'),
        "PAYOUT_CRYPTO_KEY_VERSION": "1",
        "OBJECT_STORAGE_ENDPOINT_URL": "https://objects.example.com",
        "OBJECT_STORAGE_PUBLIC_ENDPOINT_URL": "https://objects.example.com",
        "OBJECT_STORAGE_REGION": "client-approved-region",
        "OBJECT_STORAGE_BUCKET": "cardvert-private-production",
        "OBJECT_STORAGE_ACCESS_KEY_ID": "client-storage-access-key",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": (
            "Client-storage-secret-with-more-than-thirty-two-characters-2026"
        ),
        "SESSION_COOKIE_NAME": "__Host-cardvert_session",
        "ALLOW_DEMO_SEED": "false",
        "DEMO_LOGIN_ENABLED": "false",
        "PRIVACY_DISCLOSURE_SYNTHETIC_TEST_MODE": "false",
        "MEASUREMENT_LIVE_ISSUANCE_AUTHORIZED": "false",
        "PRIVACY_DISCLOSURE_LIVE_AUTHORIZED": "false",
        "LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER": "false",
        "LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER": "false",
        "LOGIN_RATE_LIMIT_TRUSTED_PROXY_CIDRS": "",
        "BACKUP_PASSPHRASE_FILE": str(passphrase),
        "BACKUP_RETENTION_DAYS": "35",
    }


def test_production_model_has_only_tls_edge_public_and_no_builds() -> None:
    model = production_model(profiles=("release",))
    services = model["services"]

    assert set(services) == {"api", "db", "edge", "frontend", "migrate", "redis", "worker"}
    assert [port["published"] for port in services["edge"]["ports"]] == ["80", "443", "443"]
    assert all(not service.get("ports") for name, service in services.items() if name != "edge")
    assert all("build" not in service for service in services.values())
    assert all("@sha256:" in service["image"] for service in services.values())
    assert services["worker"].get("profiles") is None
    assert services["migrate"]["profiles"] == ["release"]
    assert services["api"]["read_only"] is True
    assert services["worker"]["read_only"] is True
    assert services["frontend"]["read_only"] is True
    assert services["api"]["security_opt"] == ["no-new-privileges:true"]
    assert services["worker"]["cap_drop"] == ["ALL"]
    assert services["db"]["networks"] == {"data": None}
    assert services["redis"]["networks"] == {"data": None}
    assert services["edge"]["networks"] == {"app": {}, "edge": {}}
    assert model["networks"]["app"]["internal"] is True
    assert model["networks"]["data"]["internal"] is True


def test_compose_contract_rejects_public_data_or_privileged_application() -> None:
    model = production_model(profiles=("release",))
    model["services"]["db"]["ports"] = [{"published": "5432", "target": 5432}]
    with pytest.raises(ContractError):
        validate_compose_model(model)

    model = production_model(profiles=("release",))
    model["services"]["api"]["privileged"] = True
    with pytest.raises(ContractError):
        validate_compose_model(model)

    model = production_model(profiles=("release",))
    model["services"]["api"]["volumes"] = [
        {"type": "bind", "source": "/tmp", "target": "/app"}
    ]
    with pytest.raises(ContractError):
        validate_compose_model(model)


def test_caddy_exposes_only_health_webhooks_and_frontend() -> None:
    caddyfile = (ROOT / "Caddyfile").read_text()

    assert "path /health /api/v1/health* /api/v1/webhooks/*" in caddyfile
    assert "reverse_proxy api:8000" in caddyfile
    assert "reverse_proxy frontend:3000" in caddyfile
    assert "header_up -X-Forwarded-For" in caddyfile
    assert "log_append request_id {http.request.uuid}" in caddyfile
    assert "header_up X-Request-ID {http.request.uuid}" in caddyfile
    assert "Strict-Transport-Security" in caddyfile


def test_production_builds_pin_base_images_and_dependency_graphs() -> None:
    backend = (ROOT / "Dockerfile").read_text()
    frontend = (ROOT / "frontend/Dockerfile").read_text()
    python_lock = (ROOT / "requirements-production.txt").read_text()

    assert backend.startswith("FROM python@sha256:")
    assert "--require-hashes -r requirements-production.txt" in backend
    assert '".[dev]"' not in backend
    assert all("==" in line for line in python_lock.splitlines() if line and line[0].isalnum())
    assert "--hash=sha256:" in python_lock
    assert frontend.count("FROM node@sha256:") == 3
    assert "npm ci --ignore-scripts" in frontend


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("JWT_SECRET_KEY", "EXAMPLE-ONLY-REPLACE-WITH-A-SECRET-THAT-IS-LONG-ENOUGH"),
        ("POSTGRES_PASSWORD", "weak-password"),
        ("EDGE_HOSTNAME", "staging.invalid"),
        ("PUBLIC_ORIGIN", "http://cardvert.example.com"),
        ("BACKEND_CORS_ORIGINS", '["*"]'),
        ("BACKEND_IMAGE", "registry.invalid/cardvert/backend:latest"),
        ("ALLOW_DEMO_SEED", "true"),
        ("DEMO_LOGIN_ENABLED", "true"),
        ("PRIVACY_DISCLOSURE_SYNTHETIC_TEST_MODE", "true"),
        ("OBJECT_STORAGE_ENDPOINT_URL", "http://objects.example.com"),
        ("SESSION_COOKIE_NAME", "cardvert_session"),
        ("DATABASE_URL", "postgresql+asyncpg://mobility:Wrong-Password-That-Is-Long@db:5432/mobility"),
        ("REDIS_URL", "redis://:Wrong-Password-That-Is-Long@redis:6379/0"),
        ("PAYOUT_CRYPTO_KEYRING_B64", "EXAMPLE-ONLY-REPLACE-WITH-A-KEYRING"),
        ("SENTRY_DSN", "http://public@example.invalid/1"),
    ],
)
def test_release_environment_rejects_unsafe_values(tmp_path: Path, name: str, value: str) -> None:
    environment = valid_release_environment(tmp_path)
    environment[name] = value

    with pytest.raises(ContractError):
        validate_release_environment(environment, allow_local_rehearsal=False)


def test_release_environment_accepts_complete_provider_neutral_contract(tmp_path: Path) -> None:
    validated = validate_release_environment(
        valid_release_environment(tmp_path), allow_local_rehearsal=False
    )

    assert validated["release_revision"] == "1715fe53b19972cd6db829a08a9d6cf572fbd656"
    assert validated["public_origin"] == "https://cardvert.example.com"


def test_production_settings_fail_closed_on_missing_services_and_test_switches() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            database_url=None,
            redis_url=None,
            allow_demo_seed=True,
            privacy_disclosure_synthetic_test_mode=True,
            payout_crypto_keyring_b64=('{"1":"yPdM2Hgg3Q1M+MS4iF26TyMQmmuUOMf7p9hNSMlcycI="}'),
        )


def test_json_logs_correlate_and_redact_sensitive_values() -> None:
    formatter = JsonLogFormatter(service="api", release_revision="a" * 40)
    record = logging.LogRecord(
        "app.test",
        logging.INFO,
        __file__,
        1,
        (
            "request token=eyJsecret password=Hidden123 bank_account=1234567890 "
            "lat=9.0765 lon=7.3986 url=https://objects.invalid/private?signature=secret"
        ),
        (),
        None,
    )
    payload = json.loads(formatter.format(record))

    assert payload["service"] == "api"
    assert payload["release_revision"] == "a" * 40
    assert payload["message"].count("[REDACTED]") >= 5
    assert "Hidden123" not in formatter.format(record)
    assert "1234567890" not in formatter.format(record)
    assert "9.0765" not in formatter.format(record)

    event = scrub_observability_value(
        {
            "request": {"headers": {"authorization": "Bearer secret"}},
            "extra": {
                "latitude": 9.0765,
                "private_url": "https://object",
                "fraud_evidence": {"raw": "private"},
            },
        }
    )
    assert event["request"]["headers"]["authorization"] == "[REDACTED]"
    assert event["extra"] == {
        "latitude": "[REDACTED]",
        "private_url": "[REDACTED]",
        "fraud_evidence": "[REDACTED]",
    }


def test_configure_logging_replaces_root_handlers_with_json_handler() -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    try:
        configure_logging(
            Settings(_env_file=None, log_format="json", release_revision="a" * 40),
            service="api",
        )
        handlers = [
            handler for handler in root.handlers if getattr(handler, "_cardvert_json", False)
        ]
        assert len(handlers) == 1
        assert isinstance(handlers[0].formatter, JsonLogFormatter)
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)


def test_release_state_is_append_only_and_retry_convergent() -> None:
    state = {
        "schema_version": 1,
        "release_id": "20260828T120000Z-1715fe53",
        "revision": "1" * 40,
        "backend_image": "registry.invalid/backend@sha256:" + "2" * 64,
        "frontend_image": "registry.invalid/frontend@sha256:" + "3" * 64,
        "config_sha256": "4" * 64,
        "previous_release_id": "20260827T120000Z-previous",
        "stages": ["preflight", "backup", "migration", "compatibility", "traffic"],
    }

    assert validate_release_state(state)["stages"][-1] == "traffic"
    with pytest.raises(ContractError):
        validate_release_state({**state, "stages": ["preflight", "migration"]})


def test_compatibility_evidence_binds_previous_image_and_forward_schema() -> None:
    evidence = {
        "schema_version": 1,
        "result": "passed",
        "target_release_id": "20260828T120000Z-current",
        "target_revision": "1" * 40,
        "target_backend_image": "registry.invalid/backend@sha256:" + "2" * 64,
        "previous_release_id": "20260827T120000Z-previous",
        "previous_revision": "3" * 40,
        "previous_backend_image": "registry.invalid/backend@sha256:" + "4" * 64,
        "forward_alembic_revision": "0071_report_issuance",
        "checks": {
            "no_database_downgrade": True,
            "previous_image_readiness": True,
            "previous_image_report_schema_canary": True,
        },
    }
    assert validate_compatibility_evidence(
        evidence,
        target_release_id=evidence["target_release_id"],
        target_revision=evidence["target_revision"],
        target_backend_image=evidence["target_backend_image"],
        previous_release_id=evidence["previous_release_id"],
        forward_alembic_revision=evidence["forward_alembic_revision"],
    )["result"] == "passed"

    changed = {**evidence, "forward_alembic_revision": "0070_other"}
    with pytest.raises(ContractError):
        validate_compatibility_evidence(
            changed,
            target_release_id=evidence["target_release_id"],
            target_revision=evidence["target_revision"],
            target_backend_image=evidence["target_backend_image"],
            previous_release_id=evidence["previous_release_id"],
            forward_alembic_revision=evidence["forward_alembic_revision"],
        )


def test_backup_manifest_authenticates_database_objects_and_release() -> None:
    manifest = build_backup_manifest(
        release_id="20260828T120000Z-1715fe53",
        release_revision="1" * 40,
        config_sha256="2" * 64,
        alembic_revision="0071_report_issuance",
        database_sha256="3" * 64,
        database_bytes=1234,
        database_marker="2026-08-28T12:00:00Z/0-A1B2",
        objects=[
            {
                "key": "private/report.pdf",
                "version_id": "version-1",
                "sha256": "4" * 64,
                "bytes": 456,
            }
        ],
        retention_days=35,
        created_at="2026-08-28T12:00:00Z",
    )

    assert validate_backup_manifest(manifest)["object_count"] == 1
    with pytest.raises(ContractError):
        validate_backup_manifest({**manifest, "database_sha256": "5" * 64})


def test_operational_entry_points_are_shell_valid() -> None:
    scripts = [
        ROOT / "scripts/release.sh",
        ROOT / "scripts/recover_release.sh",
        ROOT / "scripts/backup_release.sh",
        ROOT / "scripts/verify_restore.sh",
        ROOT / "scripts/rehearse_w403a.sh",
    ]
    result = subprocess.run(
        ["bash", "-n", *(str(path) for path in scripts)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_release_scripts_never_run_alembic_downgrade() -> None:
    scripts = "\n".join(
        path.read_text()
        for path in (ROOT / "scripts/release.sh", ROOT / "scripts/recover_release.sh")
    )

    assert "alembic downgrade" not in scripts
    assert "--no-build" in scripts
    assert "migration_response_lost" in scripts


def test_encrypted_bundle_rejects_wrong_key_and_changed_ciphertext(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    home = Path(tempfile.mkdtemp(prefix="w403a-gpg-", dir="/tmp"))
    request.addfinalizer(lambda: shutil.rmtree(home, ignore_errors=True))
    home.chmod(0o700)
    plaintext = tmp_path / "bundle.tar"
    plaintext.write_bytes(b"synthetic release bundle")
    good_key = tmp_path / "good-key"
    wrong_key = tmp_path / "wrong-key"
    good_key.write_text("Correct-Horse-Battery-Staple-Backup-Key-2026\n")
    wrong_key.write_text("Different-Horse-Battery-Staple-Backup-Key-2026\n")
    good_key.chmod(0o600)
    wrong_key.chmod(0o600)
    encrypted = tmp_path / "bundle.tar.gpg"
    subprocess.run(
        [
            "gpg",
            "--homedir",
            str(home),
            "--batch",
            "--yes",
            "--pinentry-mode",
            "loopback",
            "--passphrase-file",
            str(good_key),
            "--symmetric",
            "--cipher-algo",
            "AES256",
            "--output",
            str(encrypted),
            str(plaintext),
        ],
        check=True,
        capture_output=True,
    )

    wrong_key_result = subprocess.run(
        [
            "gpg",
            "--homedir",
            str(home),
            "--batch",
            "--yes",
            "--pinentry-mode",
            "loopback",
            "--passphrase-file",
            str(wrong_key),
            "--decrypt",
            str(encrypted),
        ],
        capture_output=True,
    )
    assert wrong_key_result.returncode != 0

    changed = tmp_path / "changed.tar.gpg"
    ciphertext = bytearray(encrypted.read_bytes())
    ciphertext[len(ciphertext) // 2] ^= 0x01
    changed.write_bytes(ciphertext)
    changed_result = subprocess.run(
        [
            "gpg",
            "--homedir",
            str(home),
            "--batch",
            "--yes",
            "--pinentry-mode",
            "loopback",
            "--passphrase-file",
            str(good_key),
            "--decrypt",
            str(changed),
        ],
        capture_output=True,
    )
    assert changed_result.returncode != 0

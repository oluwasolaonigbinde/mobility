from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.observability import (
    JsonLogFormatter,
    configure_logging,
    scrub_observability_value,
)
from app.operations import storage_snapshot
from app.operations.readiness import _storage_check
from scripts.release_contract import (
    ContractError,
    build_backup_manifest,
    database_url_for_name,
    validate_backup_authority,
    validate_backup_manifest,
    validate_compatibility_evidence,
    validate_compose_model,
    validate_release_environment,
    validate_release_state,
)

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_COMPOSE = ROOT / "docker-compose.production.yml"
PRODUCTION_ENV = ROOT / "production.env.example"


def production_model(
    *, profiles: tuple[str, ...] = (), overrides: dict[str, str] | None = None
) -> dict:
    command = ["docker", "compose", "-f", str(PRODUCTION_COMPOSE)]
    for profile in profiles:
        command.extend(("--profile", profile))
    command.extend(("--env-file", str(PRODUCTION_ENV), "config", "--format", "json"))
    environment = os.environ.copy()
    environment.update(overrides or {})
    result = subprocess.run(
        command, cwd=ROOT, check=True, capture_output=True, text=True, env=environment
    )
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
        "EDGE_HOSTNAME": "cardvert.client-owned-domain.com",
        "PUBLIC_ORIGIN": "https://cardvert.client-owned-domain.com",
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
        "OBJECT_STORAGE_ENDPOINT_URL": "https://objects.client-storage.net",
        "OBJECT_STORAGE_PUBLIC_ENDPOINT_URL": "https://objects.client-storage.net",
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
        "DRIVER_REGISTRATION_RATE_LIMIT_TRUST_CLIENT_IP_HEADER": "false",
        "DRIVER_REGISTRATION_RATE_LIMIT_TRUSTED_PROXY_CIDRS": "",
        "BACKUP_PASSPHRASE_FILE": str(passphrase),
        "BACKUP_RETENTION_DAYS": "35",
        "LOG_LEVEL": "INFO",
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


def test_production_compose_preserves_package_configuration_overrides() -> None:
    overrides = {
        "LOGIN_RATE_LIMIT_ACCOUNT_MAX_FAILURES": "17",
        "DRIVER_REGISTRATION_RATE_LIMIT_EMAIL_MAX_ATTEMPTS": "19",
        "FRAUD_ASSESSMENT_FORMULA_VERSION": "reviewed_formula_v9",
        "ROUTE_REPLAY_MIN_DISTANCE_M": "777",
        "PRIVACY_MIN_VEHICLES_PER_CELL": "9",
        "INSTALLATION_EVIDENCE_VALIDITY_HOURS": "47",
        "DISPLAY_PROOF_VALIDITY_SECONDS": "313",
        "EVIDENCE_RENEWAL_LOOKBACK_DAYS": "91",
    }
    model = production_model(profiles=("release",), overrides=overrides)

    for service_name in ("api", "worker", "migrate"):
        environment = model["services"][service_name]["environment"]
        assert {name: str(environment[name]) for name in overrides} == overrides

    model = production_model(profiles=("release",))
    model["services"]["api"]["privileged"] = True
    with pytest.raises(ContractError):
        validate_compose_model(model)

    model = production_model(profiles=("release",))
    model["services"]["api"]["volumes"] = [{"type": "bind", "source": "/tmp", "target": "/app"}]
    with pytest.raises(ContractError):
        validate_compose_model(model)


def test_caddy_exposes_only_health_webhooks_and_frontend() -> None:
    caddyfile = (ROOT / "Caddyfile").read_text()

    assert "path /health /api/v1/health* /api/v1/webhooks/*" in caddyfile
    assert "reverse_proxy api:8000" in caddyfile
    assert "reverse_proxy frontend:3000" in caddyfile
    assert "header_up -X-Forwarded-For" in caddyfile
    assert "log_append request_id {http.request.uuid}" in caddyfile
    assert "log_append request_path {http.request.uri.path}" in caddyfile
    assert "log_append release_revision {$RELEASE_REVISION:unbound}" in caddyfile
    assert "request>uri delete" in caddyfile
    assert "request>headers>Authorization delete" in caddyfile
    assert "request>headers>Cookie delete" in caddyfile
    assert "header_up X-Request-ID {http.request.uuid}" in caddyfile
    assert "Strict-Transport-Security" in caddyfile


def test_production_builds_pin_base_images_and_dependency_graphs() -> None:
    backend = (ROOT / "Dockerfile").read_text()
    frontend = (ROOT / "frontend/Dockerfile").read_text()
    python_lock = (ROOT / "requirements-production.txt").read_text()

    assert backend.startswith("FROM python@sha256:")
    assert "--require-hashes -r requirements-production.txt" in backend
    assert "--timeout 600 --retries 10" in backend
    assert backend.index("RUN pip install") < backend.index("COPY app ./app")
    assert backend.index("RUN pip install") < backend.index("ARG VCS_REF")
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
        ("PUBLIC_ORIGIN", "http://cardvert.client-owned-domain.com"),
        ("BACKEND_CORS_ORIGINS", '["*"]'),
        ("BACKEND_IMAGE", "registry.invalid/cardvert/backend:latest"),
        ("ALLOW_DEMO_SEED", "true"),
        ("DEMO_LOGIN_ENABLED", "true"),
        ("PRIVACY_DISCLOSURE_SYNTHETIC_TEST_MODE", "true"),
        ("OBJECT_STORAGE_ENDPOINT_URL", "http://objects.client-storage.net"),
        (
            "OBJECT_STORAGE_ENDPOINT_URL",
            "https://operator:secret@objects.client-storage.net",
        ),
        ("OBJECT_STORAGE_ENDPOINT_URL", "https://objects.client-storage.net?token=secret"),
        ("OBJECT_STORAGE_ENDPOINT_URL", "https://objects.client-storage.net/#private"),
        ("OBJECT_STORAGE_ENDPOINT_URL", "https://localhost"),
        ("OBJECT_STORAGE_ENDPOINT_URL", "https://minio:9000/prefix"),
        ("OBJECT_STORAGE_ENDPOINT_URL", "https://objects.invalid"),
        ("OBJECT_STORAGE_ENDPOINT_URL", "https://objects.test"),
        ("OBJECT_STORAGE_ENDPOINT_URL", "https://objects.example"),
        ("OBJECT_STORAGE_ENDPOINT_URL", "https://192.0.2.1"),
        ("OBJECT_STORAGE_ENDPOINT_URL", "https://224.0.0.1"),
        ("OBJECT_STORAGE_PUBLIC_ENDPOINT_URL", "https://127.1.2.3"),
        ("OBJECT_STORAGE_PUBLIC_ENDPOINT_URL", "https://198.18.0.1"),
        ("OBJECT_STORAGE_PUBLIC_ENDPOINT_URL", "https://100.64.0.1"),
        ("OBJECT_STORAGE_PUBLIC_ENDPOINT_URL", "https://[ff02::1]"),
        ("OBJECT_STORAGE_PUBLIC_ENDPOINT_URL", "https://objects.client-storage.net:0"),
        ("SESSION_COOKIE_NAME", "cardvert_session"),
        (
            "DATABASE_URL",
            "postgresql+asyncpg://mobility:Wrong-Password-That-Is-Long@db:5432/mobility",
        ),
        ("REDIS_URL", "redis://:Wrong-Password-That-Is-Long@redis:6379/0"),
        ("PAYOUT_CRYPTO_KEYRING_B64", "EXAMPLE-ONLY-REPLACE-WITH-A-KEYRING"),
        ("SENTRY_DSN", "http://public@example.invalid/1"),
        ("PUBLIC_ORIGIN", "https://operator:secret@cardvert.client-owned-domain.com"),
        ("PUBLIC_ORIGIN", "https://cardvert.client-owned-domain.com?token=secret"),
        ("PUBLIC_ORIGIN", "https://cardvert.client-owned-domain.com/#private"),
        ("PUBLIC_ORIGIN", "https://cardvert.client-owned-domain.com:8443"),
        ("LOG_LEVEL", "DEBUG"),
        ("DEBUG", "true"),
        ("DRIVER_REGISTRATION_RATE_LIMIT_TRUST_CLIENT_IP_HEADER", "true"),
        ("DRIVER_REGISTRATION_RATE_LIMIT_TRUSTED_PROXY_CIDRS", "10.0.0.0/8"),
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
    assert validated["public_origin"] == "https://cardvert.client-owned-domain.com"


@pytest.mark.parametrize(
    "hostname",
    [
        "127.0.0.1",
        "10.42.0.7",
        "169.254.169.254",
        "100.64.0.1",
        "192.0.2.1",
        "198.18.0.1",
        "224.0.0.1",
        "8.8.8.8",
        "::1",
        "fd00::1",
        "fe80::1",
        "ff02::1",
        "2001:db8::1",
        "2606:4700:4700::1111",
    ],
)
def test_release_environment_rejects_every_edge_ip_literal(
    tmp_path: Path, hostname: str
) -> None:
    environment = valid_release_environment(tmp_path)
    environment["EDGE_HOSTNAME"] = hostname
    environment["PUBLIC_ORIGIN"] = (
        f"https://[{hostname}]" if ":" in hostname else f"https://{hostname}"
    )

    with pytest.raises(ContractError, match="EDGE_HOSTNAME"):
        validate_release_environment(environment, allow_local_rehearsal=False)


@pytest.mark.parametrize(
    "hostname",
    [
        "localhost",
        "cardvert.localhost",
        "cardvert.local",
        "cardvert.invalid",
        "cardvert.test",
        "cardvert.example",
        "example.com",
        "cardvert.example.com",
        "example.net",
        "cardvert.example.net",
        "example.org",
        "cardvert.example.org",
    ],
)
def test_release_environment_rejects_reserved_edge_dns_names(
    tmp_path: Path, hostname: str
) -> None:
    environment = valid_release_environment(tmp_path)
    environment["EDGE_HOSTNAME"] = hostname
    environment["PUBLIC_ORIGIN"] = f"https://{hostname}"

    with pytest.raises(ContractError, match="EDGE_HOSTNAME"):
        validate_release_environment(environment, allow_local_rehearsal=False)


@pytest.mark.parametrize(
    "name",
    ["OBJECT_STORAGE_ENDPOINT_URL", "OBJECT_STORAGE_PUBLIC_ENDPOINT_URL"],
)
@pytest.mark.parametrize(
    "hostname",
    [
        "example.com",
        "objects.example.com",
        "example.net",
        "objects.example.net",
        "example.org",
        "objects.example.org",
    ],
)
def test_release_environment_rejects_reserved_storage_dns_names(
    tmp_path: Path, name: str, hostname: str
) -> None:
    environment = valid_release_environment(tmp_path)
    environment[name] = f"https://{hostname}"

    with pytest.raises(ContractError, match="Object storage endpoints"):
        validate_release_environment(environment, allow_local_rehearsal=False)


def test_release_environment_preserves_explicit_local_rehearsal(tmp_path: Path) -> None:
    environment = valid_release_environment(tmp_path)
    environment.update(
        {
            "ENVIRONMENT": "rehearsal",
            "EDGE_HOSTNAME": "cardvert-rehearsal.local",
            "PUBLIC_ORIGIN": "https://cardvert-rehearsal.local",
            "OBJECT_STORAGE_ENDPOINT_URL": "http://minio:9000/private",
            "OBJECT_STORAGE_PUBLIC_ENDPOINT_URL": "http://localhost:9000/private",
        }
    )

    validate_release_environment(environment, allow_local_rehearsal=True)


def test_release_environment_does_not_allow_local_production_with_rehearsal_flag(
    tmp_path: Path,
) -> None:
    environment = valid_release_environment(tmp_path)
    environment["EDGE_HOSTNAME"] = "cardvert-production.local"
    environment["PUBLIC_ORIGIN"] = "https://cardvert-production.local"

    with pytest.raises(ContractError, match="EDGE_HOSTNAME"):
        validate_release_environment(environment, allow_local_rehearsal=True)


def test_release_environment_accepts_private_rfc1918_storage_with_port_and_prefix(
    tmp_path: Path,
) -> None:
    environment = valid_release_environment(tmp_path)
    environment["OBJECT_STORAGE_ENDPOINT_URL"] = "https://10.42.0.7:9443/s3"
    environment["OBJECT_STORAGE_PUBLIC_ENDPOINT_URL"] = "https://192.168.7.9:9443/s3"

    validate_release_environment(environment, allow_local_rehearsal=False)


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

    structured = logging.LogRecord(
        "app.test",
        logging.INFO,
        __file__,
        1,
        "payload=%r context=%s",
        (
            {"password": "Hidden-Structured", "nested": {"token": "Token-Structured"}},
            '{"bank_account":"9988776655","latitude":9.1234}',
        ),
        None,
    )
    structured_message = json.loads(formatter.format(structured))["message"]
    assert "Hidden-Structured" not in structured_message
    assert "Token-Structured" not in structured_message
    assert "9988776655" not in structured_message
    assert "9.1234" not in structured_message
    assert structured_message.count("[REDACTED]") >= 4


def test_storage_readiness_requires_write_read_delete_canary() -> None:
    with pytest.raises(RuntimeError, match="write/read/delete canary"):
        asyncio.run(_storage_check(write_canary=False))


class _VersionPaginator:
    def __init__(self, client: _VersionedStorage) -> None:
        self.client = client

    def paginate(self, *, Bucket: str, Prefix: str):  # noqa: N803
        del Bucket
        versions = [
            {"Key": key, "VersionId": version}
            for key, entries in self.client.versions.items()
            if key.startswith(Prefix)
            for version in entries
        ]
        yield {"Versions": versions, "DeleteMarkers": []}


class _VersionedStorage:
    def __init__(self, *, corrupt_read: bool = False) -> None:
        self.versions: dict[str, list[str]] = {}
        self.payloads: dict[tuple[str, str], bytes] = {}
        self.corrupt_read = corrupt_read

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, Metadata: dict):  # noqa: N803
        del Bucket, Metadata
        version = f"version-{len(self.payloads) + 1}"
        self.versions.setdefault(Key, []).append(version)
        self.payloads[(Key, version)] = Body
        return {"VersionId": version}

    def get_object(self, *, Bucket: str, Key: str, VersionId: str):  # noqa: N803
        del Bucket
        payload = self.payloads[(Key, VersionId)]
        if self.corrupt_read:
            payload += b"corrupt"
        return {"Body": io.BytesIO(payload)}

    def get_paginator(self, name: str):
        assert name == "list_object_versions"
        return _VersionPaginator(self)

    def delete_objects(self, *, Bucket: str, Delete: dict):  # noqa: N803
        del Bucket
        for item in Delete["Objects"]:
            self.payloads.pop((item["Key"], item["VersionId"]), None)
            entries = self.versions.get(item["Key"], [])
            if item["VersionId"] in entries:
                entries.remove(item["VersionId"])
            if not entries:
                self.versions.pop(item["Key"], None)
        return {}


@pytest.mark.parametrize("corrupt_read", [False, True])
def test_restore_verification_removes_exact_object_versions_on_success_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corrupt_read: bool
) -> None:
    payload = b"private report bytes"
    digest = __import__("hashlib").sha256(payload).hexdigest()
    inventory = [
        {
            "stored_file_id": "80000000-0000-4000-8000-000000000003",
            "key": "private/report.pdf",
            "sha256": digest,
            "bytes": len(payload),
            "purpose": "report_export",
            "version_id": "source-version-1",
        }
    ]
    archive_path = tmp_path / "objects.tar"
    with tarfile.open(archive_path, "w") as archive:
        encoded = json.dumps(inventory).encode()
        info = tarfile.TarInfo("inventory.json")
        info.size = len(encoded)
        archive.addfile(info, io.BytesIO(encoded))
        info = tarfile.TarInfo("objects/00000000")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    client = _VersionedStorage(corrupt_read=corrupt_read)
    monkeypatch.setattr(storage_snapshot, "_client", lambda: client)
    monkeypatch.setattr(
        storage_snapshot,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "database_url": "postgresql://unused",
                "object_storage_bucket": "private",
            },
        )(),
    )

    async def database_inventory(_: str):
        return [{key: value for key, value in inventory[0].items() if key != "version_id"}]

    monkeypatch.setattr(storage_snapshot, "_database_inventory", database_inventory)
    if corrupt_read:
        with pytest.raises(RuntimeError, match="isolated object restore"):
            asyncio.run(
                storage_snapshot.verify_snapshot(
                    archive_path, "restore-verification/release/unique"
                )
            )
    else:
        asyncio.run(
            storage_snapshot.verify_snapshot(archive_path, "restore-verification/release/unique")
        )
    assert client.versions == {}


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
    assert (
        validate_compatibility_evidence(
            evidence,
            target_release_id=evidence["target_release_id"],
            target_revision=evidence["target_revision"],
            target_backend_image=evidence["target_backend_image"],
            previous_release_id=evidence["previous_release_id"],
            forward_alembic_revision=evidence["forward_alembic_revision"],
        )["result"]
        == "passed"
    )

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


def test_backup_completion_binds_ciphertext_manifest_state_and_retention() -> None:
    created = datetime.now(UTC).replace(microsecond=0)
    manifest = build_backup_manifest(
        release_id="20260828T120000Z-authority",
        release_revision="1" * 40,
        config_sha256="2" * 64,
        alembic_revision="0070_report_storage",
        database_sha256="3" * 64,
        database_bytes=1234,
        database_marker="2026-08-28T12:00:00Z/0-A1B2",
        objects=[],
        retention_days=35,
        created_at=created.isoformat().replace("+00:00", "Z"),
    )
    state = {
        "schema_version": 1,
        "release_id": manifest["release_id"],
        "revision": manifest["release_revision"],
        "backend_image": "registry.invalid/backend@sha256:" + "4" * 64,
        "frontend_image": "registry.invalid/frontend@sha256:" + "5" * 64,
        "config_sha256": manifest["config_sha256"],
        "previous_release_id": None,
        "stages": ["preflight"],
        "events": [],
    }
    bundle_sha = "6" * 64
    complete = {
        "schema_version": 1,
        "state": "complete",
        "release_id": manifest["release_id"],
        "release_revision": manifest["release_revision"],
        "config_sha256": manifest["config_sha256"],
        "bundle_sha256": bundle_sha,
        "manifest_sha256": manifest["manifest_sha256"],
        "created_at": manifest["created_at"],
        "expires_at": manifest["expires_at"],
    }
    arguments = {
        "complete_marker": complete,
        "manifest": manifest,
        "release_state": state,
        "bundle_sha256": bundle_sha,
        "expected_release_id": manifest["release_id"],
        "expected_release_revision": manifest["release_revision"],
        "expected_config_sha256": manifest["config_sha256"],
    }

    assert validate_backup_authority(**arguments)["bundle_sha256"] == bundle_sha
    for changed_arguments in (
        {**arguments, "complete_marker": {**complete, "bundle_sha256": "7" * 64}},
        {**arguments, "release_state": {**state, "revision": "8" * 40}},
        {
            **arguments,
            "complete_marker": {
                **complete,
                "expires_at": (created - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
            },
        },
    ):
        with pytest.raises(ContractError):
            validate_backup_authority(**changed_arguments)

    expired_manifest = build_backup_manifest(
        release_id=manifest["release_id"],
        release_revision=manifest["release_revision"],
        config_sha256=manifest["config_sha256"],
        alembic_revision=manifest["alembic_revision"],
        database_sha256=manifest["database_sha256"],
        database_bytes=manifest["database_bytes"],
        database_marker=manifest["database_marker"],
        objects=[],
        retention_days=35,
        created_at=(created - timedelta(days=36)).isoformat().replace("+00:00", "Z"),
    )
    expired_complete = {
        **complete,
        "manifest_sha256": expired_manifest["manifest_sha256"],
        "created_at": expired_manifest["created_at"],
        "expires_at": expired_manifest["expires_at"],
    }
    with pytest.raises(ContractError, match="expired"):
        validate_backup_authority(
            **{
                **arguments,
                "complete_marker": expired_complete,
                "manifest": expired_manifest,
            }
        )


def test_restore_database_url_preserves_percent_encoded_password() -> None:
    original = "postgresql+asyncpg://mobility:p%40ss%2Fword%3A2026@db:5432/mobility"

    assert database_url_for_name(original, "cardvert_restore_verify_1234") == (
        "postgresql+asyncpg://mobility:p%40ss%2Fword%3A2026@db:5432/cardvert_restore_verify_1234"
    )
    with pytest.raises(ContractError):
        database_url_for_name(original, "unsafe/name")


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
    assert "bootstrap:no-predecessor-empty-database" in scripts
    assert "--expected-database-revision" in scripts
    assert "--current-env-file" in scripts
    assert scripts.count("--wait-timeout 120 edge") == 2
    backup = (ROOT / "scripts/backup_release.sh").read_text()
    release = (ROOT / "scripts/release.sh").read_text()
    assert "--leave-writers-stopped" in release
    assert '"${compose[@]}" start "${service}"' in backup
    assert 'up -d --no-build "${service}"' not in backup


@pytest.mark.parametrize("script_name", ["release.sh", "recover_release.sh"])
def test_lock_contender_never_removes_active_owner(tmp_path: Path, script_name: str) -> None:
    state_dir = tmp_path / "state"
    lock_dir = state_dir / ".release.lock"
    lock_dir.mkdir(parents=True)
    owner = json.dumps({"host": os.uname().nodename, "pid": os.getpid()}).encode()
    (lock_dir / "owner.json").write_bytes(owner)
    env_file = tmp_path / "release.env"
    env_file.write_text("ENVIRONMENT=production\n")
    state_file = tmp_path / "current-state.json"
    state_file.write_text("{}\n")
    evidence = tmp_path / "compatibility.json"
    evidence.write_text("{}\n")
    password = tmp_path / "smoke-password"
    password.write_text("secret\n")
    password.chmod(0o600)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for command in ("docker", "jq"):
        executable = fake_bin / command
        executable.write_text("#!/usr/bin/env bash\nexit 0\n")
        executable.chmod(0o755)
    if script_name == "release.sh":
        arguments = [
            "--env-file",
            str(env_file),
            "--state-dir",
            str(state_dir),
            "--backup-dir",
            str(tmp_path / "backups"),
            "--compatibility-evidence",
            str(evidence),
        ]
    else:
        arguments = [
            "--current-state",
            str(state_file),
            "--current-env-file",
            str(env_file),
            "--previous-env-file",
            str(env_file),
            "--state-dir",
            str(state_dir),
            "--smoke-email",
            "smoke@example.invalid",
            "--smoke-password-file",
            str(password),
            "--compatibility-evidence",
            str(evidence),
        ]
    result = subprocess.run(
        [str(ROOT / "scripts" / script_name), *arguments],
        cwd=ROOT,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert lock_dir.is_dir()
    assert (lock_dir / "owner.json").read_bytes() == owner


def test_smoke_password_file_must_be_external_and_private(tmp_path: Path) -> None:
    env_file = tmp_path / "release.env"
    env_file.write_text("ENVIRONMENT=production\n")
    broad = tmp_path / "broad-password"
    broad.write_text("secret\n")
    broad.chmod(0o644)
    base_environment = {
        **os.environ,
        "SMOKE_BASE_URL": "https://cardvert.example.com",
        "COMPOSE_ENV_FILE": str(env_file),
    }
    for source, message in (
        (PRODUCTION_ENV, "outside the repository"),
        (broad, "0600 or stricter"),
    ):
        result = subprocess.run(
            [
                str(ROOT / "scripts/release_smoke.sh"),
                "--email",
                "smoke@example.invalid",
                "--password-file",
                str(source),
            ],
            cwd=ROOT,
            env=base_environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert message in result.stderr


@pytest.mark.parametrize("script_name", ["backup_release.sh", "release.sh"])
def test_backup_output_must_stay_outside_repository(tmp_path: Path, script_name: str) -> None:
    state = tmp_path / "state.json"
    state.write_text("{}\n")
    compatibility = tmp_path / "compatibility.json"
    compatibility.write_text("{}\n")
    arguments = ["--env-file", str(PRODUCTION_ENV)]
    if script_name == "backup_release.sh":
        arguments.extend(["--state-file", str(state), "--output-dir", str(ROOT / ".unsafe-backup")])
    else:
        arguments.extend(
            [
                "--state-dir",
                str(tmp_path / "release-state"),
                "--backup-dir",
                str(ROOT / ".unsafe-backup"),
                "--compatibility-evidence",
                str(compatibility),
            ]
        )
    result = subprocess.run(
        [str(ROOT / "scripts" / script_name), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "backup output must stay outside the repository" in result.stderr
    assert not (ROOT / ".unsafe-backup").exists()


def test_failure_cleanup_stops_an_open_edge(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "docker.calls"
    docker = fake_bin / "docker"
    docker.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >>"$DOCKER_CALLS"\n')
    docker.chmod(0o755)
    env_file = tmp_path / "release.env"
    env_file.write_text("ENVIRONMENT=production\n")
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                "source scripts/release_common.sh; "
                'release_stop_edge_if_open false "$ENV_FILE"; '
                'release_stop_edge_if_open true "$ENV_FILE"'
            ),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "DOCKER_CALLS": str(calls),
            "ENV_FILE": str(env_file),
        },
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert calls.read_text().splitlines() == [
        f"compose -f {PRODUCTION_COMPOSE} --env-file {env_file} stop edge"
    ]


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

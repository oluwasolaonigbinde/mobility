from __future__ import annotations

import asyncio
import copy
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
    TLS_FILE_NAMES,
    ContractError,
    _check_image_labels,
    _write_new_private_json,
    build_backup_manifest,
    build_compatibility_receipt,
    compatibility_acceptance_hmac,
    compatibility_receipt_sha256,
    compose_environment_names,
    database_url_for_name,
    frontend_build_environment_names,
    read_env_file,
    release_config_sha256,
    release_environment_names,
    settings_environment_names,
    validate_backup_authority,
    validate_backup_manifest,
    validate_compatibility_evidence,
    validate_compose_model,
    validate_data_service_urls,
    validate_environment_key_contract,
    validate_release_environment,
    validate_release_state,
)

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_COMPOSE = ROOT / "docker-compose.production.yml"
PRODUCTION_ENV = ROOT / "production.env.example"
STAGING_ENV = ROOT / "staging.env.example"


def example_environment_names(path: Path) -> set[str]:
    return {
        line.split("=", 1)[0]
        for line in path.read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
    }


def test_live_environment_examples_cover_current_settings_source() -> None:
    expected = release_environment_names()

    assert expected <= example_environment_names(STAGING_ENV)
    assert expected <= example_environment_names(PRODUCTION_ENV)
    assert example_environment_names(STAGING_ENV) == example_environment_names(PRODUCTION_ENV)
    assert frontend_build_environment_names() <= expected
    assert settings_environment_names() <= compose_environment_names() | {
        "APP_NAME",
        "API_V1_PREFIX",
        "LOG_FORMAT",
        "REQUEST_ID_HEADER",
        "JWT_ALGORITHM",
        "ALLOW_DEMO_SEED",
        "PRIVACY_DISCLOSURE_SYNTHETIC_TEST_MODE",
    }


@pytest.mark.parametrize("path", [STAGING_ENV, PRODUCTION_ENV])
def test_checked_in_environment_examples_cannot_pass_preflight(path: Path) -> None:
    with pytest.raises(ContractError, match="placeholder|development value"):
        validate_environment_key_contract(read_env_file(path))


@pytest.mark.parametrize("name", sorted(release_environment_names()))
def test_release_key_contract_rejects_each_omission(name: str) -> None:
    environment = {item: "" for item in release_environment_names()}
    environment.pop(name)

    with pytest.raises(ContractError, match=name):
        validate_environment_key_contract(environment)


@pytest.mark.parametrize("value", ["REPLACE-ME", "placeholder", "sample-secret"])
def test_release_key_contract_rejects_placeholders(value: str) -> None:
    environment = {item: "" for item in release_environment_names()}
    environment["PRIVACY_LEGAL_APPROVAL_REFERENCE"] = value

    with pytest.raises(ContractError, match="PRIVACY_LEGAL_APPROVAL_REFERENCE"):
        validate_environment_key_contract(environment)


def test_environment_file_rejects_duplicate_names(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.env"
    path.write_text("ENVIRONMENT=production\nENVIRONMENT=staging\n")

    with pytest.raises(ContractError, match="duplicate environment name"):
        read_env_file(path)


def production_model(
    *,
    profiles: tuple[str, ...] = (),
    overrides: dict[str, str] | None = None,
    env_file: Path = PRODUCTION_ENV,
) -> dict:
    command = ["docker", "compose", "-f", str(PRODUCTION_COMPOSE)]
    for profile in profiles:
        command.extend(("--profile", profile))
    command.extend(("--env-file", str(env_file), "config", "--format", "json"))
    environment = os.environ.copy()
    environment.update(overrides or {})
    result = subprocess.run(
        command, cwd=ROOT, check=True, capture_output=True, text=True, env=environment
    )
    return json.loads(result.stdout)


def valid_release_environment(tmp_path: Path) -> dict[str, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    passphrase = tmp_path / "backup-passphrase"
    passphrase.write_text("Release-Backup-Passphrase-Kept-Outside-Repository-2026!\n")
    passphrase.chmod(0o600)
    tls = tmp_path / "tls"
    tls.mkdir(exist_ok=True)
    ca_key = tls / "ca.key"
    ca_cert = tls / "ca.crt"
    if not ca_cert.exists():
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "ec",
                "-pkeyopt",
                "ec_paramgen_curve:P-256",
                "-nodes",
                "-subj",
                "/CN=Cardvert test CA",
                "-keyout",
                str(ca_key),
                "-out",
                str(ca_cert),
                "-days",
                "1",
            ],
            check=True,
            capture_output=True,
        )
        for host in ("db", "redis"):
            key = tls / f"{host}.key"
            csr = tls / f"{host}.csr"
            certificate = tls / f"{host}.crt"
            extensions = tls / f"{host}.ext"
            extensions.write_text(f"subjectAltName=DNS:{host}\n")
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-new",
                    "-newkey",
                    "ec",
                    "-pkeyopt",
                    "ec_paramgen_curve:P-256",
                    "-nodes",
                    "-subj",
                    f"/CN={host}",
                    "-keyout",
                    str(key),
                    "-out",
                    str(csr),
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "openssl",
                    "x509",
                    "-req",
                    "-in",
                    str(csr),
                    "-CA",
                    str(ca_cert),
                    "-CAkey",
                    str(ca_key),
                    "-CAcreateserial",
                    "-out",
                    str(certificate),
                    "-days",
                    "1",
                    "-extfile",
                    str(extensions),
                ],
                check=True,
                capture_output=True,
            )
            key.chmod(0o600)
    environment = read_env_file(PRODUCTION_ENV)
    environment.update(
        {
            "ENVIRONMENT": "production",
            "RELEASE_ID": "20260828T120000Z-1715fe53",
            "RELEASE_REVISION": "1715fe53b19972cd6db829a08a9d6cf572fbd656",
            "RELEASE_EVIDENCE_SIGNING_SECRET": RELEASE_EVIDENCE_SECRET,
            "RELEASE_EVIDENCE_KEY_ID": RELEASE_EVIDENCE_KEY_ID,
            "BACKEND_IMAGE": "registry.invalid/cardvert/backend@sha256:" + "1" * 64,
            "FRONTEND_IMAGE": "registry.invalid/cardvert/frontend@sha256:" + "2" * 64,
            "POSTGIS_IMAGE": "postgis/postgis@sha256:" + "3" * 64,
            "REDIS_IMAGE": "redis@sha256:" + "4" * 64,
            "CADDY_IMAGE": "caddy@sha256:" + "5" * 64,
            "EDGE_HOSTNAME": "cardvert.client-owned-domain.com",
            "PUBLIC_ORIGIN": "https://cardvert.client-owned-domain.com",
            "BACKEND_CORS_ORIGINS": "[]",
            "POSTGRES_PASSWORD": "Correct-Horse-Battery-Staple-Database-2026",
            "POSTGRES_TLS_CA_FILE": str(ca_cert),
            "POSTGRES_TLS_CERT_FILE": str(tls / "db.crt"),
            "POSTGRES_TLS_KEY_FILE": str(tls / "db.key"),
            "DATABASE_URL": (
                "postgresql+asyncpg://mobility:Correct-Horse-Battery-Staple-Database-2026"
                "@db:5432/mobility?ssl=verify-full"
            ),
            "REDIS_PASSWORD": "Correct-Horse-Battery-Staple-Redis-2026",
            "REDIS_TLS_CA_FILE": str(ca_cert),
            "REDIS_TLS_CERT_FILE": str(tls / "redis.crt"),
            "REDIS_TLS_KEY_FILE": str(tls / "redis.key"),
            "REDIS_URL": (
                "rediss://:Correct-Horse-Battery-Staple-Redis-2026@redis:6379/0"
                "?ssl_ca_certs=/run/secrets/redis_tls_ca&ssl_cert_reqs=required"
            ),
            "JWT_SECRET_KEY": "Jwt-release-secret-with-more-than-thirty-two-random-characters-2026",
            "PAYOUT_CRYPTO_KEYRING_B64": ('{"1":"yPdM2Hgg3Q1M+MS4iF26TyMQmmuUOMf7p9hNSMlcycI="}'),
            "PAYOUT_CRYPTO_KEY_VERSION": "1",
            "TRIP_EVIDENCE_SIGNING_KEYRING_B64": (
                '{"1":"N3PXmtgm1eTDuCG8zb7JojEgXkQp4GbgN5j5kHlp4Rs="}'
            ),
            "TRIP_EVIDENCE_SIGNING_KEY_VERSION": "1",
            "OBJECT_STORAGE_ENDPOINT_URL": "https://objects.client-storage.net",
            "OBJECT_STORAGE_PUBLIC_ENDPOINT_URL": "https://objects.client-storage.net",
            "OBJECT_STORAGE_REGION": "client-approved-region",
            "OBJECT_STORAGE_BUCKET": "cardvert-private-production",
            "OBJECT_STORAGE_ACCESS_KEY_ID": "client-storage-access-key",
            "OBJECT_STORAGE_SECRET_ACCESS_KEY": (
                "Client-storage-secret-with-more-than-thirty-two-characters-2026"
            ),
            "MALWARE_SCANNER_HOST": "scanner.internal.client-owned-domain.com",
            "MALWARE_SCANNER_PORT": "3310",
            "MALWARE_SCANNER_TIMEOUT_SECONDS": "30",
            "FILE_KYC_RETENTION_DAYS": "365",
            "INSTALLATION_EVIDENCE_UPLOADER_ROLES": "driver,admin",
            "INSTALLATION_EVIDENCE_REQUIRED_VIEWS": "front,rear,left,right",
            "INSTALLATION_EVIDENCE_VALIDITY_HOURS": "24",
            "DISPLAY_PROOF_CHALLENGE_TTL_SECONDS": "900",
            "DISPLAY_PROOF_VALIDITY_SECONDS": "86400",
            "EVIDENCE_HIGH_EARNER_THRESHOLD_NGN": "100000",
            "EVIDENCE_RENEWAL_LOOKBACK_DAYS": "30",
            "EVIDENCE_CHALLENGE_RESPONSE_HOURS": "24",
            "VERIFIED_HOURS_FLOOR_PER_WEEK": "10",
            "EMAIL_PROVIDER": "smtp",
            "EMAIL_SENDER_ADDRESS": "notifications@client-owned-domain.com",
            "EMAIL_SMTP_HOST": "smtp.client-owned-domain.com",
            "EMAIL_SMTP_PORT": "587",
            "EMAIL_SMTP_USERNAME": "cardvert-notifications",
            "EMAIL_SMTP_PASSWORD": "Smtp-password-with-more-than-thirty-two-characters-2026!",
            "EMAIL_SMTP_STARTTLS": "true",
            "EMAIL_RECEIPT_SIGNING_SECRET": (
                "Email-receipt-secret-with-more-than-thirty-two-characters-2026!"
            ),
            "EMAIL_RECEIPT_KEY_ID": "email-receipt-2026-01",
            "PRIVACY_COLLECTION_LIVE_AUTHORIZED": "true",
            "PRIVACY_COLLECTION_SYNTHETIC_TEST_MODE": "false",
            "PRIVACY_LEGAL_APPROVAL_REFERENCE": "legal-approval-reference-2026-01",
            "NEXT_PUBLIC_MAP_STYLE_URL": (
                "https://maps.client-owned-domain.com/styles/cardvert.json"
            ),
            "SESSION_COOKIE_NAME": "__Host-cardvert_session",
            "ALLOW_DEMO_SEED": "false",
            "DEMO_LOGIN_ENABLED": "false",
            "PRIVACY_DISCLOSURE_SYNTHETIC_TEST_MODE": "false",
            "MEASUREMENT_LIVE_ISSUANCE_AUTHORIZED": "false",
            "PRIVACY_DISCLOSURE_LIVE_AUTHORIZED": "false",
            "LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER": "true",
            "LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER": "true",
            "LOGIN_RATE_LIMIT_TRUSTED_PROXY_CIDRS": "10.255.254.10/32",
            "DRIVER_REGISTRATION_RATE_LIMIT_TRUST_CLIENT_IP_HEADER": "false",
            "DRIVER_REGISTRATION_RATE_LIMIT_TRUSTED_PROXY_CIDRS": "",
            "BACKUP_PASSPHRASE_FILE": str(passphrase),
            "BACKUP_RETENTION_DAYS": "35",
            "LOG_LEVEL": "INFO",
        }
    )
    return environment


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
    model["services"]["api"]["environment"].pop("TRIP_SEAL_GRACE_SECONDS")
    with pytest.raises(ContractError, match="TRIP_SEAL_GRACE_SECONDS"):
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
        ("LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER", "false"),
        ("LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER", "false"),
        ("LOGIN_RATE_LIMIT_TRUSTED_PROXY_CIDRS", "10.255.254.0/24"),
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
    assert validated["data_service_adapter"] == "bundled"


@pytest.mark.parametrize(
    "source_name",
    [
        "JWT_SECRET_KEY",
        "EMAIL_RECEIPT_SIGNING_SECRET",
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
        "EMAIL_SMTP_PASSWORD",
        "PAYOUT_CRYPTO_KEYRING_B64",
        "TRIP_EVIDENCE_SIGNING_KEYRING_B64",
        "BACKUP_PASSPHRASE_FILE",
    ],
)
def test_release_evidence_secret_must_use_dedicated_custody(
    tmp_path: Path, source_name: str
) -> None:
    environment = valid_release_environment(tmp_path)
    if source_name.endswith("KEYRING_B64"):
        version_name = (
            "PAYOUT_CRYPTO_KEY_VERSION"
            if source_name.startswith("PAYOUT")
            else "TRIP_EVIDENCE_SIGNING_KEY_VERSION"
        )
        keyring = json.loads(environment[source_name])
        environment["RELEASE_EVIDENCE_SIGNING_SECRET"] = keyring[environment[version_name]]
    elif source_name == "BACKUP_PASSPHRASE_FILE":
        environment["RELEASE_EVIDENCE_SIGNING_SECRET"] = Path(
            environment[source_name]
        ).read_text().strip()
    else:
        environment["RELEASE_EVIDENCE_SIGNING_SECRET"] = environment[source_name]

    with pytest.raises(ContractError, match="dedicated signing secret"):
        validate_release_environment(environment, allow_local_rehearsal=False)


def test_staging_environment_uses_same_fail_closed_contract(tmp_path: Path) -> None:
    environment = valid_release_environment(tmp_path)
    environment["ENVIRONMENT"] = "staging"

    validated = validate_release_environment(environment, allow_local_rehearsal=False)

    assert validated["environment"] == "staging"


@pytest.mark.parametrize("mode", ["staging", "production"])
def test_complete_synthetic_environment_validates_settings_and_renders_compose(
    tmp_path: Path, mode: str
) -> None:
    environment = valid_release_environment(tmp_path)
    environment["ENVIRONMENT"] = mode
    env_file = tmp_path / f"{mode}.env"
    env_file.write_text("".join(f"{name}={value}\n" for name, value in environment.items()))
    env_file.chmod(0o600)

    validate_release_environment(environment, allow_local_rehearsal=False)
    settings_values = {name.lower(): environment[name] for name in settings_environment_names()}
    settings = Settings(_env_file=None, **settings_values)
    model = production_model(profiles=("release",), env_file=env_file)
    validate_compose_model(model)

    assert settings.environment == mode
    assert model["services"]["api"]["environment"]["ENVIRONMENT"] == mode


@pytest.mark.parametrize(
    ("name", "value", "reason"),
    [
        ("TRIP_EVIDENCE_SIGNING_KEYRING_B64", "", "TRIP_EVIDENCE"),
        ("TRIP_EVIDENCE_SIGNING_KEY_VERSION", "2", "TRIP_EVIDENCE"),
        ("MALWARE_SCANNER_HOST", "", "MALWARE_SCANNER_HOST"),
        ("MALWARE_SCANNER_HOST", "scanner.invalid", "MALWARE_SCANNER_HOST"),
        ("MALWARE_SCANNER_PORT", "0", "MALWARE_SCANNER_PORT"),
        ("MALWARE_SCANNER_TIMEOUT_SECONDS", "0", "MALWARE_SCANNER_TIMEOUT_SECONDS"),
        ("PRIVACY_COLLECTION_LIVE_AUTHORIZED", "false", "PRIVACY_COLLECTION"),
        ("PRIVACY_LEGAL_APPROVAL_REFERENCE", "", "PRIVACY_LEGAL"),
        ("PRIVACY_COLLECTION_SYNTHETIC_TEST_MODE", "true", "SYNTHETIC_TEST_MODE"),
        ("EMAIL_PROVIDER", "", "EMAIL_PROVIDER"),
        ("EMAIL_SENDER_ADDRESS", "", "EMAIL_SENDER_ADDRESS"),
        ("EMAIL_SMTP_HOST", "", "EMAIL_SMTP_HOST"),
        ("EMAIL_SMTP_USERNAME", "", "EMAIL_SMTP_USERNAME"),
        ("EMAIL_SMTP_PASSWORD", "", "EMAIL_SMTP_PASSWORD"),
        ("EMAIL_SMTP_STARTTLS", "false", "EMAIL_SMTP_STARTTLS"),
        ("EMAIL_RECEIPT_SIGNING_SECRET", "", "EMAIL_RECEIPT_SIGNING_SECRET"),
        ("EMAIL_RECEIPT_KEY_ID", "", "EMAIL_RECEIPT_KEY_ID"),
        ("NEXT_PUBLIC_MAP_STYLE_URL", "", "NEXT_PUBLIC_MAP_STYLE_URL"),
        ("NEXT_PUBLIC_MAP_STYLE_URL", "http://maps.example.org/style", "MAP_STYLE"),
        (
            "NEXT_PUBLIC_MAP_STYLE_URL",
            "https://maps.client-owned-domain.com/style?access_token=secret",
            "MAP_STYLE",
        ),
        ("FILE_KYC_RETENTION_DAYS", "", "FILE_KYC_RETENTION_DAYS"),
        ("INSTALLATION_EVIDENCE_UPLOADER_ROLES", "", "UPLOADER_ROLES"),
        ("INSTALLATION_EVIDENCE_REQUIRED_VIEWS", "", "REQUIRED_VIEWS"),
        ("INSTALLATION_EVIDENCE_VALIDITY_HOURS", "", "VALIDITY_HOURS"),
        ("DISPLAY_PROOF_CHALLENGE_TTL_SECONDS", "", "CHALLENGE_TTL"),
        ("DISPLAY_PROOF_VALIDITY_SECONDS", "", "PROOF_VALIDITY"),
        ("EVIDENCE_HIGH_EARNER_THRESHOLD_NGN", "", "HIGH_EARNER"),
        ("EVIDENCE_RENEWAL_LOOKBACK_DAYS", "", "RENEWAL_LOOKBACK"),
        ("EVIDENCE_CHALLENGE_RESPONSE_HOURS", "", "CHALLENGE_RESPONSE"),
        ("VERIFIED_HOURS_FLOOR_PER_WEEK", "", "VERIFIED_HOURS_FLOOR_PER_WEEK"),
    ],
)
def test_release_environment_rejects_incomplete_live_authority(
    tmp_path: Path, name: str, value: str, reason: str
) -> None:
    environment = valid_release_environment(tmp_path)
    environment[name] = value

    with pytest.raises(ContractError, match=reason):
        validate_release_environment(environment, allow_local_rehearsal=False)


def test_image_check_proves_frontend_build_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "1" * 40
    frontend_image = "registry.invalid/frontend@sha256:" + "2" * 64
    model = {
        "services": {
            "api": {"image": "registry.invalid/backend@sha256:" + "3" * 64},
            "frontend": {"image": frontend_image},
        }
    }
    environment = {
        "NEXT_PUBLIC_MAP_STYLE_URL": "https://maps.client-owned-domain.com/style.json",
        "NEXT_PUBLIC_SENTRY_DSN": "",
    }
    calls: list[list[str]] = []

    def successful_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        stdout = revision if command[1:3] == ["image", "inspect"] else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", successful_run)
    _check_image_labels(model, revision, environment)

    assert any(
        command[:4] == ["docker", "run", "--rm", "--entrypoint"]
        and command[-1] == environment["NEXT_PUBLIC_MAP_STYLE_URL"]
        for command in calls
    )

    def missing_input(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        is_build_check = command[1:3] == ["run", "--rm"]
        return subprocess.CompletedProcess(
            command,
            1 if is_build_check else 0,
            stdout="" if is_build_check else revision,
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", missing_input)
    with pytest.raises(ContractError, match="approved NEXT_PUBLIC_MAP_STYLE_URL"):
        _check_image_labels(model, revision, environment)


def test_release_config_digest_binds_frontend_build_inputs() -> None:
    environment = {
        "NEXT_PUBLIC_MAP_STYLE_URL": "https://maps.client-owned-domain.com/style-a.json",
        "NEXT_PUBLIC_SENTRY_DSN": "",
    }
    first = release_config_sha256(
        caddyfile_sha256="1" * 64, compose={"services": {}}, environment=environment
    )
    changed = release_config_sha256(
        caddyfile_sha256="1" * 64,
        compose={"services": {}},
        environment={
            **environment,
            "NEXT_PUBLIC_MAP_STYLE_URL": "https://maps.client-owned-domain.com/style-b.json",
        },
    )

    assert changed != first


def test_provider_neutral_data_urls_allow_managed_but_bundled_release_stops(
    tmp_path: Path,
) -> None:
    environment = valid_release_environment(tmp_path)
    environment["DATABASE_URL"] = (
        "postgresql+asyncpg://managed:Correct-Horse-Battery-Staple-Database-2026"
        "@postgres.internal:5432/cardvert?ssl=verify-full"
    )
    environment["REDIS_URL"] = (
        "rediss://:Correct-Horse-Battery-Staple-Redis-2026@cache.internal:6380/0"
        "?ssl_cert_reqs=required"
    )
    for name in (*TLS_FILE_NAMES, "POSTGIS_IMAGE", "REDIS_IMAGE"):
        environment.pop(name)
    assert validate_data_service_urls(environment) == "managed"
    with pytest.raises(ContractError, match="MANAGED_DATA_RELEASE_ADAPTER_REQUIRED"):
        validate_release_environment(environment, allow_local_rehearsal=False)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (
            "DATABASE_URL",
            "postgresql+asyncpg://managed:Correct-Horse-Battery-Staple-Database-2026"
            "@postgres.internal:5432/cardvert?ssl=verify-ca",
        ),
        (
            "REDIS_URL",
            "rediss://:Correct-Horse-Battery-Staple-Redis-2026@cache.internal:6380/0",
        ),
        (
            "REDIS_URL",
            "rediss://:Correct-Horse-Battery-Staple-Redis-2026@cache.internal:6380/0"
            "?ssl_cert_reqs=none",
        ),
    ],
)
def test_provider_neutral_data_urls_require_explicit_peer_verification(
    tmp_path: Path, name: str, value: str
) -> None:
    environment = valid_release_environment(tmp_path)
    environment["DATABASE_URL"] = (
        "postgresql+asyncpg://managed:Correct-Horse-Battery-Staple-Database-2026"
        "@postgres.internal:5432/cardvert?ssl=verify-full"
    )
    environment["REDIS_URL"] = (
        "rediss://:Correct-Horse-Battery-Staple-Redis-2026@cache.internal:6380/0"
        "?ssl_cert_reqs=required"
    )
    environment[name] = value

    with pytest.raises(ContractError):
        validate_data_service_urls(environment)


def test_bundled_tls_rejects_wrong_ca_without_disclosing_certificate_content(
    tmp_path: Path,
) -> None:
    environment = valid_release_environment(tmp_path / "primary")
    other = valid_release_environment(tmp_path / "other")
    environment["POSTGRES_TLS_CA_FILE"] = other["POSTGRES_TLS_CA_FILE"]

    with pytest.raises(ContractError, match="Bundled TLS certificate validation failed") as error:
        validate_release_environment(environment, allow_local_rehearsal=False)

    assert "BEGIN CERTIFICATE" not in str(error.value)


def test_bundled_tls_rejects_wrong_san(tmp_path: Path) -> None:
    environment = valid_release_environment(tmp_path)
    environment["REDIS_TLS_CERT_FILE"] = environment["POSTGRES_TLS_CERT_FILE"]
    environment["REDIS_TLS_KEY_FILE"] = environment["POSTGRES_TLS_KEY_FILE"]

    with pytest.raises(ContractError, match="Bundled TLS certificate validation failed"):
        validate_release_environment(environment, allow_local_rehearsal=False)


def test_bundled_tls_rejects_certificate_key_mismatch(tmp_path: Path) -> None:
    environment = valid_release_environment(tmp_path)
    environment["POSTGRES_TLS_KEY_FILE"] = environment["REDIS_TLS_KEY_FILE"]

    with pytest.raises(ContractError, match="do not match"):
        validate_release_environment(environment, allow_local_rehearsal=False)


def test_bundled_tls_rejects_permissive_private_key_mode(tmp_path: Path) -> None:
    environment = valid_release_environment(tmp_path)
    key = Path(environment["POSTGRES_TLS_KEY_FILE"])
    key.chmod(0o640)

    with pytest.raises(ContractError, match="mode 0600 or stricter"):
        validate_release_environment(environment, allow_local_rehearsal=False)


def test_w403a_rehearsal_supplies_verified_tls_data_service_material() -> None:
    rehearsal = (ROOT / "scripts/rehearse_w403a.sh").read_text()

    assert "subjectAltName=DNS:%s" in rehearsal
    assert "POSTGRES_TLS_CA_FILE=${tls_dir}/ca.crt" in rehearsal
    assert "DATABASE_URL=postgresql+asyncpg://" in rehearsal
    assert "?ssl=verify-full" in rehearsal
    assert "REDIS_TLS_CA_FILE=${tls_dir}/ca.crt" in rehearsal
    assert "REDIS_URL=rediss://" in rehearsal
    assert "ssl_cert_reqs=required" in rehearsal


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
    generated_at = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    evidence = compatibility_receipt(generated_at=generated_at)

    assert validate_compatibility_evidence(
        evidence,
        target_release_id=evidence["target_release_id"],
        target_revision=evidence["target_revision"],
        target_backend_image=evidence["target_backend_image"],
        previous_release_id=evidence["previous_release_id"],
        previous_revision=evidence["previous_revision"],
        previous_backend_image=evidence["previous_backend_image"],
        forward_alembic_revision=evidence["forward_alembic_revision"],
        signing_secret=RELEASE_EVIDENCE_SECRET,
        key_id=RELEASE_EVIDENCE_KEY_ID,
        now=generated_at + timedelta(minutes=1),
    )["result"] == "passed"


RELEASE_EVIDENCE_SECRET = "Release-evidence-secret-that-is-dedicated-and-random-2026!"
RELEASE_EVIDENCE_KEY_ID = "release-evidence-2026-01"


def compatibility_receipt(
    *,
    generated_at: datetime | None = None,
    readiness_revision: str | None = None,
    readiness_status: str = "ready",
    report_status: str = "passed",
) -> dict:
    generated_at = generated_at or datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    previous_revision = "3" * 40
    forward_revision = "0082_report_publication_intents"
    checked_at = (generated_at - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    readiness_output = {
        "event": "release_readiness",
        "status": readiness_status,
        "release_revision": readiness_revision or previous_revision,
        "checked_at": checked_at,
        "checks": {"database": {"alembic_revision": forward_revision}},
    }
    report_output = {
        "event": "report_schema_canary",
        "status": report_status,
        "release_revision": previous_revision,
        "forward_alembic_revision": forward_revision,
        "checked_at": checked_at,
        "checks": {
            "report_issuances_select": "ok",
            "report_artifacts_select": "ok",
        },
    }
    return build_compatibility_receipt(
        target_release_id="20260828T120000Z-current",
        target_revision="1" * 40,
        target_backend_image="registry.invalid/backend@sha256:" + "2" * 64,
        previous_release_id="20260827T120000Z-previous",
        previous_revision=previous_revision,
        previous_backend_image="registry.invalid/backend@sha256:" + "4" * 64,
        forward_alembic_revision=forward_revision,
        readiness_output=readiness_output,
        report_schema_output=report_output,
        generated_at=generated_at,
        key_id=RELEASE_EVIDENCE_KEY_ID,
        signing_secret=RELEASE_EVIDENCE_SECRET,
    )


def validate_test_compatibility_receipt(evidence: dict, *, now: datetime | None = None) -> None:
    validate_compatibility_evidence(
        evidence,
        target_release_id="20260828T120000Z-current",
        target_revision="1" * 40,
        target_backend_image="registry.invalid/backend@sha256:" + "2" * 64,
        previous_release_id="20260827T120000Z-previous",
        previous_revision="3" * 40,
        previous_backend_image="registry.invalid/backend@sha256:" + "4" * 64,
        forward_alembic_revision="0082_report_publication_intents",
        signing_secret=RELEASE_EVIDENCE_SECRET,
        key_id=RELEASE_EVIDENCE_KEY_ID,
        now=now or datetime(2026, 8, 28, 12, 1, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("path", "changed_value"),
    [
        (("target_release_id",), "20260828T120000Z-changed"),
        (("target_revision",), "a" * 40),
        (("target_backend_image",), "registry.invalid/backend@sha256:" + "a" * 64),
        (("previous_release_id",), "20260827T120000Z-changed"),
        (("previous_revision",), "b" * 40),
        (("previous_backend_image",), "registry.invalid/backend@sha256:" + "b" * 64),
        (("forward_alembic_revision",), "0081_payout_money_authority"),
        (("generated_at",), "2026-08-28T11:59:00Z"),
        (("key_id",), "release-evidence-2026-02"),
        (("probes", "readiness", "output_sha256"), "c" * 64),
        (("probes", "readiness", "output", "status"), "failed"),
        (("probes", "report_schema", "output_sha256"), "d" * 64),
        (("probes", "report_schema", "output", "status"), "failed"),
    ],
)
def test_compatibility_receipt_rejects_tampering(
    path: tuple[str, ...], changed_value: str
) -> None:
    evidence = copy.deepcopy(compatibility_receipt())
    target = evidence
    for name in path[:-1]:
        target = target[name]
    target[path[-1]] = changed_value

    with pytest.raises(ContractError):
        validate_test_compatibility_receipt(evidence)


@pytest.mark.parametrize("signature_index", range(64))
def test_compatibility_receipt_rejects_every_changed_signature_byte(
    signature_index: int,
) -> None:
    evidence = compatibility_receipt()
    signature = evidence["hmac_sha256"]
    replacement = "0" if signature[signature_index] != "0" else "1"
    evidence["hmac_sha256"] = (
        signature[:signature_index] + replacement + signature[signature_index + 1 :]
    )

    with pytest.raises(ContractError, match="HMAC"):
        validate_test_compatibility_receipt(evidence)


@pytest.mark.parametrize("probe_name", ["readiness", "report_schema"])
@pytest.mark.parametrize("field", ["output", "output_sha256"])
def test_compatibility_receipt_rejects_missing_probe_output(
    probe_name: str, field: str
) -> None:
    evidence = compatibility_receipt()
    del evidence["probes"][probe_name][field]

    with pytest.raises(ContractError):
        validate_test_compatibility_receipt(evidence)


def test_compatibility_receipt_rejects_malformed_signed_readiness_checks() -> None:
    generated_at = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    with pytest.raises(ContractError, match="readiness output did not pass"):
        build_compatibility_receipt(
            target_release_id="20260828T120000Z-current",
            target_revision="1" * 40,
            target_backend_image="registry.invalid/backend@sha256:" + "2" * 64,
            previous_release_id="20260827T120000Z-previous",
            previous_revision="3" * 40,
            previous_backend_image="registry.invalid/backend@sha256:" + "4" * 64,
            forward_alembic_revision="0082_report_publication_intents",
            readiness_output={
                "event": "release_readiness",
                "status": "ready",
                "release_revision": "3" * 40,
                "checked_at": "2026-08-28T11:59:59Z",
                "checks": [],
            },
            report_schema_output={
                "event": "report_schema_canary",
                "status": "passed",
                "release_revision": "3" * 40,
                "forward_alembic_revision": "0082_report_publication_intents",
                "checked_at": "2026-08-28T11:59:59Z",
                "checks": {
                    "report_issuances_select": "ok",
                    "report_artifacts_select": "ok",
                },
            },
            generated_at=generated_at,
            key_id=RELEASE_EVIDENCE_KEY_ID,
            signing_secret=RELEASE_EVIDENCE_SECRET,
        )


def test_compatibility_receipt_rejects_legacy_booleans_and_current_image_output() -> None:
    legacy = {
        "schema_version": 1,
        "result": "passed",
        "checks": {
            "no_database_downgrade": True,
            "previous_image_readiness": True,
            "previous_image_report_schema_canary": True,
        },
    }
    with pytest.raises(ContractError):
        validate_test_compatibility_receipt(legacy)

    with pytest.raises(ContractError, match="previous revision"):
        compatibility_receipt(readiness_revision="1" * 40)


@pytest.mark.parametrize(
    "receipt_factory",
    [
        lambda: compatibility_receipt(readiness_status="failed"),
        lambda: compatibility_receipt(report_status="failed"),
    ],
)
def test_compatibility_receipt_is_not_generated_from_failed_previous_image_probe(
    receipt_factory,
) -> None:
    with pytest.raises(ContractError, match="did not pass"):
        receipt_factory()


def test_first_release_uses_signed_bootstrap_receipt_without_inventing_predecessor() -> None:
    generated_at = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    evidence = build_compatibility_receipt(
        target_release_id="20260828T120000Z-current",
        target_revision="1" * 40,
        target_backend_image="registry.invalid/backend@sha256:" + "2" * 64,
        previous_release_id="",
        previous_revision="",
        previous_backend_image="",
        forward_alembic_revision="0082_report_publication_intents",
        readiness_output=None,
        report_schema_output=None,
        generated_at=generated_at,
        key_id=RELEASE_EVIDENCE_KEY_ID,
        signing_secret=RELEASE_EVIDENCE_SECRET,
    )

    assert evidence["previous_release_id"] is None
    assert evidence["previous_revision"] is None
    assert evidence["previous_backend_image"] is None
    assert evidence["probes"] is None
    assert validate_compatibility_evidence(
        evidence,
        target_release_id=evidence["target_release_id"],
        target_revision=evidence["target_revision"],
        target_backend_image=evidence["target_backend_image"],
        previous_release_id="",
        previous_revision="",
        previous_backend_image="",
        forward_alembic_revision=evidence["forward_alembic_revision"],
        signing_secret=RELEASE_EVIDENCE_SECRET,
        key_id=RELEASE_EVIDENCE_KEY_ID,
        now=generated_at,
    )["result"] == "passed"


def test_unaccepted_stale_compatibility_receipt_fails_but_exact_release_anchor_survives() -> None:
    evidence = compatibility_receipt()
    receipt_sha256 = compatibility_receipt_sha256(evidence)
    acceptance_hmac = compatibility_acceptance_hmac(
        receipt_sha256=receipt_sha256,
        target_release_id=evidence["target_release_id"],
        target_revision=evidence["target_revision"],
        target_backend_image=evidence["target_backend_image"],
        key_id=RELEASE_EVIDENCE_KEY_ID,
        signing_secret=RELEASE_EVIDENCE_SECRET,
    )
    stale_now = datetime(2026, 8, 28, 13, 0, tzinfo=UTC)
    with pytest.raises(ContractError, match="stale"):
        validate_test_compatibility_receipt(evidence, now=stale_now)

    validate_compatibility_evidence(
        evidence,
        target_release_id=evidence["target_release_id"],
        target_revision=evidence["target_revision"],
        target_backend_image=evidence["target_backend_image"],
        previous_release_id=evidence["previous_release_id"],
        previous_revision=evidence["previous_revision"],
        previous_backend_image=evidence["previous_backend_image"],
        forward_alembic_revision=evidence["forward_alembic_revision"],
        signing_secret=RELEASE_EVIDENCE_SECRET,
        key_id=RELEASE_EVIDENCE_KEY_ID,
        now=stale_now,
        accepted_receipt_sha256=receipt_sha256,
        accepted_receipt_hmac=acceptance_hmac,
    )
    with pytest.raises(ContractError, match="accepted receipt"):
        validate_compatibility_evidence(
            evidence,
            target_release_id=evidence["target_release_id"],
            target_revision=evidence["target_revision"],
            target_backend_image=evidence["target_backend_image"],
            previous_release_id=evidence["previous_release_id"],
            previous_revision=evidence["previous_revision"],
            previous_backend_image=evidence["previous_backend_image"],
            forward_alembic_revision=evidence["forward_alembic_revision"],
            signing_secret=RELEASE_EVIDENCE_SECRET,
            key_id=RELEASE_EVIDENCE_KEY_ID,
            now=stale_now,
            accepted_receipt_sha256="f" * 64,
            accepted_receipt_hmac=acceptance_hmac,
        )
    with pytest.raises(ContractError, match="authority"):
        validate_compatibility_evidence(
            evidence,
            target_release_id=evidence["target_release_id"],
            target_revision=evidence["target_revision"],
            target_backend_image=evidence["target_backend_image"],
            previous_release_id=evidence["previous_release_id"],
            previous_revision=evidence["previous_revision"],
            previous_backend_image=evidence["previous_backend_image"],
            forward_alembic_revision=evidence["forward_alembic_revision"],
            signing_secret=RELEASE_EVIDENCE_SECRET,
            key_id=RELEASE_EVIDENCE_KEY_ID,
            now=stale_now,
            accepted_receipt_sha256=receipt_sha256,
            accepted_receipt_hmac="f" * 64,
        )


def test_compatibility_receipt_rejects_any_future_generation_time() -> None:
    evidence = compatibility_receipt()
    with pytest.raises(ContractError, match="future"):
        validate_test_compatibility_receipt(
            evidence, now=datetime(2026, 8, 28, 11, 59, 59, 999999, tzinfo=UTC)
        )


def test_compatibility_receipt_writer_never_replaces_an_existing_artifact(
    tmp_path: Path,
) -> None:
    path = tmp_path / "receipt.json"
    path.write_text('{"existing":true}\n')
    path.chmod(0o600)

    with pytest.raises(ContractError, match="cannot be overwritten"):
        _write_new_private_json(path, {"replacement": True})

    assert json.loads(path.read_text()) == {"existing": True}


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


def test_restore_database_url_preserves_percent_encoded_password_and_tls_query() -> None:
    original = (
        "postgresql+asyncpg://mobility:p%40ss%2Fword%3A2026@db:5432/mobility"
        "?ssl=verify-full"
    )

    assert database_url_for_name(original, "cardvert_restore_verify_1234") == (
        "postgresql+asyncpg://mobility:p%40ss%2Fword%3A2026@db:5432/"
        "cardvert_restore_verify_1234?ssl=verify-full"
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
    release = (ROOT / "scripts/release.sh").read_text()
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
    assert "compatibility-generate" in release
    assert "--previous-env-file" in release
    assert "--accepted-receipt-sha256" in scripts
    assert "--accepted-receipt-hmac" in scripts
    recovery = (ROOT / "scripts/recover_release.sh").read_text()
    assert (
        'current_backend_image="$(release_env_value "${CURRENT_ENV_FILE}" BACKEND_IMAGE)"'
    ) in recovery
    assert (
        '"${current_backend_image}" == "$(jq -r \'.backend_image\' "${CURRENT_STATE}")"'
    ) in recovery
    assert release.index('--stage compatibility') < release.index(
        "python -m app.operations.readiness --write-canary"
    )
    assert '"${previous_compose[@]}" stop api worker' not in release
    previous_probe = release[
        release.index("previous_compose=(") : release.index("validation_args=(")
    ]
    assert "worker" not in previous_probe
    assert "current_compose" not in recovery
    assert "previous_image_readiness" not in scripts
    assert "previous_image_report_schema_canary" not in scripts
    rehearsal = (ROOT / "scripts/rehearse_w403a.sh").read_text()
    assert "recovery-compatibility.json" not in rehearsal
    assert rehearsal.count('--compatibility-evidence "${release_compatibility}"') == 6
    assert "RELEASE_COMPATIBILITY_BREAK_REPORT_CANARY=true" in rehearsal
    backup = (ROOT / "scripts/backup_release.sh").read_text()
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

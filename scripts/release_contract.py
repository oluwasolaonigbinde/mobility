#!/usr/bin/env python3
"""Fail-closed W4-03A release, state, and recovery manifest contracts."""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlparse, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[a-zA-Z0-9][a-zA-Z0-9._-]{3,63}$")
RELEASE_EVIDENCE_KEY_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{3,63}$")
PINNED_IMAGE_RE = re.compile(r"^[^\s:@]+(?:/[^\s:@]+)*@sha256:[0-9a-f]{64}$")
LOCAL_IMAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PLACEHOLDER_RE = re.compile(
    r"(?i)(example-only|replace[-_ ]?me|change[-_ ]?me|placeholder|\btodo\b|\btbd\b|"
    r"dummy|sample-secret|weak-password|local-secret|test-secret)"
)
RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
SPECIAL_USE_DNS_SUFFIXES = (
    "localhost",
    "local",
    "invalid",
    "test",
    "example",
    "example.com",
    "example.net",
    "example.org",
)
SECRET_NAMES = (
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "JWT_SECRET_KEY",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    "EMAIL_SMTP_PASSWORD",
    "EMAIL_RECEIPT_SIGNING_SECRET",
    "RELEASE_EVIDENCE_SIGNING_SECRET",
)
TLS_FILE_NAMES = (
    "POSTGRES_TLS_CA_FILE",
    "POSTGRES_TLS_CERT_FILE",
    "POSTGRES_TLS_KEY_FILE",
    "REDIS_TLS_CA_FILE",
    "REDIS_TLS_CERT_FILE",
    "REDIS_TLS_KEY_FILE",
)
REQUIRED_NAMES = (
    "ENVIRONMENT",
    "RELEASE_ID",
    "RELEASE_REVISION",
    "BACKEND_IMAGE",
    "FRONTEND_IMAGE",
    "CADDY_IMAGE",
    "EDGE_HOSTNAME",
    "PUBLIC_ORIGIN",
    "BACKEND_CORS_ORIGINS",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "REDIS_PASSWORD",
    "REDIS_URL",
    "JWT_SECRET_KEY",
    "PAYOUT_CRYPTO_KEYRING_B64",
    "PAYOUT_CRYPTO_KEY_VERSION",
    "OBJECT_STORAGE_ENDPOINT_URL",
    "OBJECT_STORAGE_PUBLIC_ENDPOINT_URL",
    "OBJECT_STORAGE_REGION",
    "OBJECT_STORAGE_BUCKET",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    "SESSION_COOKIE_NAME",
    "BACKUP_PASSPHRASE_FILE",
    "BACKUP_RETENTION_DAYS",
    "RELEASE_EVIDENCE_SIGNING_SECRET",
    "RELEASE_EVIDENCE_KEY_ID",
)
BUNDLED_REQUIRED_NAMES = ("POSTGIS_IMAGE", "REDIS_IMAGE", *TLS_FILE_NAMES)
RELEASE_ONLY_NAMES = (
    "RELEASE_ID",
    "PREVIOUS_RELEASE_ID",
    "BACKEND_IMAGE",
    "FRONTEND_IMAGE",
    "POSTGIS_IMAGE",
    "REDIS_IMAGE",
    "CADDY_IMAGE",
    "EDGE_HOSTNAME",
    "PUBLIC_ORIGIN",
    "SESSION_COOKIE_NAME",
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "BACKUP_PASSPHRASE_FILE",
    "BACKUP_RETENTION_DAYS",
    "RELEASE_EVIDENCE_SIGNING_SECRET",
    "RELEASE_EVIDENCE_KEY_ID",
    *TLS_FILE_NAMES,
)
STAGE_ORDER = (
    "preflight",
    "backup",
    "migration",
    "compatibility",
    "traffic",
)
COMPATIBILITY_RECEIPT_MAX_AGE = timedelta(minutes=30)
COMPATIBILITY_RECEIPT_FUTURE_SKEW = timedelta(0)


class ContractError(ValueError):
    """A production or recovery contract is incomplete or unsafe."""


def _canonical_json_bytes(value: Any) -> bytes:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return payload.encode()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def release_config_sha256(
    *, caddyfile_sha256: str, compose: Mapping[str, Any], environment: Mapping[str, str]
) -> str:
    return _canonical_sha256(
        {
            "caddyfile_sha256": caddyfile_sha256,
            "compose": compose,
            "frontend_build": {
                name: environment.get(name, "")
                for name in sorted(frontend_build_environment_names())
            },
        }
    )


def _require(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ContractError(f"{name} is required")
    return value


def settings_environment_names(config_file: Path | None = None) -> frozenset[str]:
    """Derive environment names from the current Settings source."""
    path = config_file or ROOT / "app/core/config.py"
    try:
        module = ast.parse(path.read_text())
        settings = next(
            node
            for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "Settings"
        )
    except (OSError, StopIteration, SyntaxError) as exc:
        raise ContractError("Unable to derive the live Settings contract") from exc
    names = {
        node.target.id.upper()
        for node in settings.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    if not names:
        raise ContractError("The live Settings contract is empty")
    return frozenset(names)


def compose_environment_names(compose_file: Path | None = None) -> frozenset[str]:
    path = compose_file or ROOT / "docker-compose.production.yml"
    try:
        names = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", path.read_text()))
    except OSError as exc:
        raise ContractError("Unable to derive the production Compose contract") from exc
    if not names:
        raise ContractError("The production Compose environment contract is empty")
    return frozenset(names)


def frontend_build_environment_names(dockerfile: Path | None = None) -> frozenset[str]:
    path = dockerfile or ROOT / "frontend/Dockerfile"
    try:
        names = {
            match.group(1)
            for match in re.finditer(
                r"^ARG (NEXT_PUBLIC_[A-Z0-9_]+)(?:=|$)", path.read_text(), re.MULTILINE
            )
        }
    except OSError as exc:
        raise ContractError("Unable to derive the frontend build contract") from exc
    if not names:
        raise ContractError("The frontend build environment contract is empty")
    return frozenset(names)


def release_environment_names() -> frozenset[str]:
    return frozenset(
        (
            *settings_environment_names(),
            *compose_environment_names(),
            *frontend_build_environment_names(),
            *RELEASE_ONLY_NAMES,
        )
    )


def validate_environment_key_contract(environment: Mapping[str, str]) -> None:
    missing = sorted(release_environment_names() - environment.keys())
    if missing:
        raise ContractError(f"Release environment omits required names: {', '.join(missing)}")
    for name, value in environment.items():
        if value.strip() and PLACEHOLDER_RE.search(value):
            raise ContractError(f"{name} contains a placeholder or development value")


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def _is_special_use_dns_name(hostname: str) -> bool:
    normalized = hostname.lower().rstrip(".")
    return any(
        normalized == suffix or normalized.endswith(f".{suffix}")
        for suffix in SPECIAL_USE_DNS_SUFFIXES
    )


def database_url_for_name(database_url: str, database_name: str) -> str:
    """Replace only the database path while preserving encoded credentials."""
    if not re.fullmatch(r"[a-zA-Z0-9_]+", database_name):
        raise ContractError("Restore database name contains unsafe characters")
    parts = urlsplit(database_url)
    if not parts.scheme or not parts.netloc:
        raise ContractError("Database URL is invalid")
    return urlunsplit(
        (parts.scheme, parts.netloc, f"/{quote(database_name, safe='')}", parts.query, "")
    )


def _validate_secret(name: str, value: str) -> None:
    if len(value) < 32:
        raise ContractError(f"{name} must contain at least 32 characters")
    if PLACEHOLDER_RE.search(value):
        raise ContractError(f"{name} contains a placeholder or development value")
    character_classes = sum(
        bool(re.search(pattern, value))
        for pattern in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^a-zA-Z0-9]")
    )
    if character_classes < 3:
        raise ContractError(f"{name} is insufficiently varied")


def _validate_image(name: str, value: str, *, allow_local_rehearsal: bool) -> None:
    if PINNED_IMAGE_RE.fullmatch(value):
        return
    if allow_local_rehearsal and LOCAL_IMAGE_RE.fullmatch(value):
        return
    raise ContractError(f"{name} must be an immutable sha256 image reference")


def _validate_private_key_file(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ContractError("BACKUP_PASSPHRASE_FILE must be a readable regular file")
    if ROOT == path or ROOT in path.parents:
        raise ContractError("BACKUP_PASSPHRASE_FILE must be outside the repository")
    if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ContractError("BACKUP_PASSPHRASE_FILE must have mode 0600 or stricter")
    if not os.access(path, os.R_OK):
        raise ContractError("BACKUP_PASSPHRASE_FILE is not readable")
    _validate_secret("BACKUP_PASSPHRASE_FILE content", path.read_text().strip())
    return path


def _validate_external_tls_file(name: str, value: str, *, private_key: bool) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.R_OK):
        raise ContractError(f"{name} must be a readable regular file")
    if ROOT == path or ROOT in path.parents:
        raise ContractError(f"{name} must be outside the repository")
    if private_key and path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ContractError(f"{name} must have mode 0600 or stricter")
    return path


def _openssl(*args: str) -> bytes:
    result = subprocess.run(
        ["openssl", *args], check=False, capture_output=True
    )
    if result.returncode:
        raise ContractError("Bundled TLS certificate validation failed")
    return result.stdout


def _validate_server_certificate(*, ca: Path, certificate: Path, key: Path, host: str) -> None:
    _openssl("verify", "-CAfile", str(ca), str(certificate))
    _openssl("x509", "-in", str(certificate), "-noout", "-checkhost", host)
    certificate_key = _openssl("x509", "-in", str(certificate), "-pubkey", "-noout")
    private_key = _openssl("pkey", "-in", str(key), "-pubout")
    if not certificate_key or certificate_key != private_key:
        raise ContractError("Bundled TLS certificate and private key do not match")


def _deployable_runtime_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.lower().rstrip(".")
    if not normalized or "*" in normalized or PLACEHOLDER_RE.search(normalized):
        return False
    if _is_special_use_dns_name(normalized):
        return False
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return True
    return not (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    )


def validate_data_service_urls(environment: Mapping[str, str]) -> str:
    """Validate provider-neutral data authorities and identify the release adapter."""
    database_raw = _require(environment, "DATABASE_URL")
    redis_raw = _require(environment, "REDIS_URL")
    database = urlsplit(database_raw)
    redis = urlsplit(redis_raw)
    database_query = parse_qsl(database.query, keep_blank_values=True)
    redis_query = parse_qsl(redis.query, keep_blank_values=True)
    database_names = [name.lower() for name, _ in database_query]
    redis_names = [name.lower() for name, _ in redis_query]
    authority_names = {"host", "port", "user", "username", "password", "database", "dbname"}
    database_ssl = [value for name, value in database_query if name.lower() == "ssl"]
    redis_cert_reqs = [
        value for name, value in redis_query if name.lower() == "ssl_cert_reqs"
    ]
    if (
        database.scheme != "postgresql+asyncpg"
        or not _deployable_runtime_host(database.hostname)
        or not database.username
        or not database.password
        or not database.path.strip("/")
        or any(name in authority_names for name in database_names)
        or "sslmode" in database_names
        or database_ssl != ["verify-full"]
    ):
        raise ContractError("DATABASE_URL must use authenticated asyncpg with verified TLS")
    if (
        redis.scheme != "rediss"
        or not _deployable_runtime_host(redis.hostname)
        or not redis.password
        or any(name in authority_names | {"db"} for name in redis_names)
        or [value.lower() for value in redis_cert_reqs] != ["required"]
    ):
        raise ContractError("REDIS_URL must use authenticated Redis with verified TLS")
    if (
        unquote(database.password) != _require(environment, "POSTGRES_PASSWORD")
        or unquote(redis.password) != _require(environment, "REDIS_PASSWORD")
    ):
        raise ContractError("Database and Redis URL credentials must match supplied secrets")

    database_bundled = (
        database.hostname == "db"
        and database.port == 5432
        and unquote(database.username) == "mobility"
        and database.path == "/mobility"
    )
    redis_bundled = redis.hostname == "redis" and redis.port == 6379 and redis.path == "/0"
    if database_bundled != redis_bundled:
        raise ContractError("Database and Redis must use one coherent release adapter")
    if not database_bundled:
        return "managed"
    redis_ca_paths = [
        value for name, value in redis_query if name.lower() == "ssl_ca_certs"
    ]
    if redis_ca_paths != ["/run/secrets/redis_tls_ca"]:
        raise ContractError("Bundled Redis must use its mounted release CA")
    return "bundled"


def _validate_payout_keyring(environment: Mapping[str, str]) -> None:
    raw_keyring = _require(environment, "PAYOUT_CRYPTO_KEYRING_B64")
    version = _require(environment, "PAYOUT_CRYPTO_KEY_VERSION")
    try:
        keyring = json.loads(raw_keyring)
        encoded_key = keyring[version]
        decoded_key = base64.b64decode(encoded_key, validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error, json.JSONDecodeError) as exc:
        raise ContractError("Payout keyring must contain the active base64 key version") from exc
    if not isinstance(keyring, dict) or len(decoded_key) != 32:
        raise ContractError("Payout keyring must contain 32-byte keys")


def _validate_versioned_keyring(
    environment: Mapping[str, str], *, keyring_name: str, version_name: str
) -> None:
    raw_keyring = _require(environment, keyring_name)
    version = _require(environment, version_name)
    try:
        keyring = json.loads(raw_keyring)
        encoded_key = keyring[version]
        decoded_key = base64.b64decode(encoded_key, validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error, json.JSONDecodeError) as exc:
        raise ContractError(f"{keyring_name} must contain its active base64 key version") from exc
    if not isinstance(keyring, dict) or len(decoded_key) != 32:
        raise ContractError(f"{keyring_name} must contain 32-byte keys")


def _active_keyring_material(
    environment: Mapping[str, str], *, keyring_name: str, version_name: str
) -> tuple[str, bytes]:
    try:
        keyring = json.loads(_require(environment, keyring_name))
        encoded_key = keyring[_require(environment, version_name)]
        decoded_key = base64.b64decode(encoded_key, validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error, json.JSONDecodeError) as exc:
        raise ContractError(f"{keyring_name} must contain its active base64 key version") from exc
    if not isinstance(encoded_key, str) or len(decoded_key) != 32:
        raise ContractError(f"{keyring_name} must contain 32-byte keys")
    return encoded_key, decoded_key


def validate_release_evidence_configuration(
    environment: Mapping[str, str],
) -> tuple[str, str]:
    secret = _require(environment, "RELEASE_EVIDENCE_SIGNING_SECRET")
    key_id = _require(environment, "RELEASE_EVIDENCE_KEY_ID")
    _validate_secret("RELEASE_EVIDENCE_SIGNING_SECRET", secret)
    if not RELEASE_EVIDENCE_KEY_ID_RE.fullmatch(key_id) or PLACEHOLDER_RE.search(key_id):
        raise ContractError("RELEASE_EVIDENCE_KEY_ID is invalid")

    forbidden_text = {
        environment.get(name, "").strip()
        for name in (
            "JWT_SECRET_KEY",
            "EMAIL_RECEIPT_SIGNING_SECRET",
            "POSTGRES_PASSWORD",
            "REDIS_PASSWORD",
            "OBJECT_STORAGE_SECRET_ACCESS_KEY",
            "EMAIL_SMTP_PASSWORD",
        )
    }
    backup_path = Path(environment.get("BACKUP_PASSPHRASE_FILE", "")).expanduser()
    if backup_path.is_file():
        forbidden_text.add(backup_path.read_text().strip())

    forbidden_bytes: set[bytes] = set()
    for keyring_name, version_name in (
        ("PAYOUT_CRYPTO_KEYRING_B64", "PAYOUT_CRYPTO_KEY_VERSION"),
        ("TRIP_EVIDENCE_SIGNING_KEYRING_B64", "TRIP_EVIDENCE_SIGNING_KEY_VERSION"),
    ):
        encoded, decoded = _active_keyring_material(
            environment, keyring_name=keyring_name, version_name=version_name
        )
        forbidden_text.add(encoded)
        forbidden_bytes.add(decoded)

    if secret in forbidden_text or secret.encode() in forbidden_bytes:
        raise ContractError("Release evidence must use a dedicated signing secret")
    try:
        decoded_secret = base64.b64decode(secret, validate=True)
    except (ValueError, binascii.Error):
        decoded_secret = b""
    if decoded_secret in forbidden_bytes:
        raise ContractError("Release evidence must use a dedicated signing secret")
    return secret, key_id


def _validate_https_authority(name: str, value: str) -> None:
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ContractError(f"{name} contains an invalid port") from exc
    if (
        parsed.scheme != "https"
        or not _deployable_runtime_host(parsed.hostname)
        or port == 0
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ContractError(f"{name} must use a deployable HTTPS authority")


def _validate_live_adapters(environment: Mapping[str, str]) -> None:
    _validate_versioned_keyring(
        environment,
        keyring_name="TRIP_EVIDENCE_SIGNING_KEYRING_B64",
        version_name="TRIP_EVIDENCE_SIGNING_KEY_VERSION",
    )
    scanner_host = _require(environment, "MALWARE_SCANNER_HOST")
    if not _deployable_runtime_host(scanner_host):
        raise ContractError("MALWARE_SCANNER_HOST must be a deployable hostname")
    for name in ("MALWARE_SCANNER_PORT", "MALWARE_SCANNER_TIMEOUT_SECONDS"):
        try:
            value = int(_require(environment, name))
        except ValueError as exc:
            raise ContractError(f"{name} must be an integer") from exc
        if value <= 0 or name.endswith("PORT") and value > 65535:
            raise ContractError(f"{name} is outside its accepted range")

    if not _is_true(environment.get("PRIVACY_COLLECTION_LIVE_AUTHORIZED")):
        raise ContractError("PRIVACY_COLLECTION_LIVE_AUTHORIZED must be true")
    _require(environment, "PRIVACY_LEGAL_APPROVAL_REFERENCE")
    if _is_true(environment.get("PRIVACY_COLLECTION_SYNTHETIC_TEST_MODE")):
        raise ContractError("PRIVACY_COLLECTION_SYNTHETIC_TEST_MODE must be false")

    if _require(environment, "EMAIL_PROVIDER").lower() != "smtp":
        raise ContractError("EMAIL_PROVIDER must select the accepted smtp adapter")
    email_host = _require(environment, "EMAIL_SMTP_HOST")
    if not _deployable_runtime_host(email_host):
        raise ContractError("EMAIL_SMTP_HOST must be a deployable hostname")
    if not _is_true(environment.get("EMAIL_SMTP_STARTTLS")):
        raise ContractError("EMAIL_SMTP_STARTTLS must be true")
    for name in (
        "EMAIL_SENDER_ADDRESS",
        "EMAIL_SMTP_USERNAME",
        "EMAIL_SMTP_PASSWORD",
        "EMAIL_RECEIPT_SIGNING_SECRET",
        "EMAIL_RECEIPT_KEY_ID",
    ):
        _require(environment, name)
    try:
        email_port = int(_require(environment, "EMAIL_SMTP_PORT"))
    except ValueError as exc:
        raise ContractError("EMAIL_SMTP_PORT must be an integer") from exc
    if not 1 <= email_port <= 65535:
        raise ContractError("EMAIL_SMTP_PORT is outside its accepted range")

    _validate_https_authority(
        "NEXT_PUBLIC_MAP_STYLE_URL", _require(environment, "NEXT_PUBLIC_MAP_STYLE_URL")
    )
    for name in (
        "FILE_KYC_RETENTION_DAYS",
        "INSTALLATION_EVIDENCE_UPLOADER_ROLES",
        "INSTALLATION_EVIDENCE_REQUIRED_VIEWS",
        "INSTALLATION_EVIDENCE_VALIDITY_HOURS",
        "DISPLAY_PROOF_CHALLENGE_TTL_SECONDS",
        "DISPLAY_PROOF_VALIDITY_SECONDS",
        "EVIDENCE_HIGH_EARNER_THRESHOLD_NGN",
        "EVIDENCE_RENEWAL_LOOKBACK_DAYS",
        "EVIDENCE_CHALLENGE_RESPONSE_HOURS",
        "VERIFIED_HOURS_FLOOR_PER_WEEK",
    ):
        _require(environment, name)


def validate_release_environment(
    environment: Mapping[str, str], *, allow_local_rehearsal: bool
) -> dict[str, str]:
    """Validate the release environment without returning any secret values."""
    for name in REQUIRED_NAMES:
        _require(environment, name)

    mode = _require(environment, "ENVIRONMENT").lower()
    if allow_local_rehearsal:
        if mode not in {"rehearsal", "production"}:
            raise ContractError("ENVIRONMENT must be rehearsal or production")
    elif mode not in {"staging", "production"}:
        raise ContractError("ENVIRONMENT must be staging or production")

    data_service_adapter = validate_data_service_urls(environment)
    if data_service_adapter != "bundled":
        raise ContractError(
            "MANAGED_DATA_RELEASE_ADAPTER_REQUIRED: bundled release automation cannot "
            "operate managed data services"
        )
    validate_environment_key_contract(environment)
    for name in BUNDLED_REQUIRED_NAMES:
        _require(environment, name)

    release_id = _require(environment, "RELEASE_ID")
    revision = _require(environment, "RELEASE_REVISION").lower()
    if not RELEASE_ID_RE.fullmatch(release_id):
        raise ContractError("RELEASE_ID has an invalid format")
    if not REVISION_RE.fullmatch(revision):
        raise ContractError("RELEASE_REVISION must be a full lowercase Git revision")

    for name in ("BACKEND_IMAGE", "FRONTEND_IMAGE", "POSTGIS_IMAGE", "REDIS_IMAGE", "CADDY_IMAGE"):
        _validate_image(
            name,
            _require(environment, name),
            allow_local_rehearsal=allow_local_rehearsal,
        )

    hostname = _require(environment, "EDGE_HOSTNAME").lower()
    normalized_hostname = hostname.rstrip(".")
    try:
        edge_address = ipaddress.ip_address(normalized_hostname)
    except ValueError:
        edge_address = None
    local_hostname = allow_local_rehearsal and mode == "rehearsal"
    if (
        not local_hostname
        and (
            edge_address is not None
            or "." not in normalized_hostname
            or _is_special_use_dns_name(normalized_hostname)
        )
        or hostname in {"localhost", "0.0.0.0"}
        or PLACEHOLDER_RE.search(hostname)
    ):
        raise ContractError("EDGE_HOSTNAME must be an approved deployable hostname")
    origin = urlparse(_require(environment, "PUBLIC_ORIGIN"))
    try:
        origin_port = origin.port
    except ValueError as exc:
        raise ContractError("PUBLIC_ORIGIN contains an invalid port") from exc
    if (
        origin.scheme != "https"
        or origin.hostname != hostname
        or origin_port not in {None, 443}
        or origin.path not in {"", "/"}
        or origin.username is not None
        or origin.password is not None
        or origin.params
        or origin.query
        or origin.fragment
    ):
        raise ContractError("PUBLIC_ORIGIN must be the HTTPS EDGE_HOSTNAME origin")

    try:
        cors = json.loads(_require(environment, "BACKEND_CORS_ORIGINS"))
    except json.JSONDecodeError as exc:
        raise ContractError("BACKEND_CORS_ORIGINS must be JSON") from exc
    if cors != []:
        raise ContractError("Production BACKEND_CORS_ORIGINS must be [] for the BFF-only surface")

    for name in SECRET_NAMES:
        _validate_secret(name, _require(environment, name))
    _validate_payout_keyring(environment)
    _validate_live_adapters(environment)
    validate_release_evidence_configuration(environment)

    tls_paths = {
        name: _validate_external_tls_file(
            name,
            _require(environment, name),
            private_key=name.endswith("_KEY_FILE"),
        )
        for name in TLS_FILE_NAMES
    }
    _validate_server_certificate(
        ca=tls_paths["POSTGRES_TLS_CA_FILE"],
        certificate=tls_paths["POSTGRES_TLS_CERT_FILE"],
        key=tls_paths["POSTGRES_TLS_KEY_FILE"],
        host="db",
    )
    _validate_server_certificate(
        ca=tls_paths["REDIS_TLS_CA_FILE"],
        certificate=tls_paths["REDIS_TLS_CERT_FILE"],
        key=tls_paths["REDIS_TLS_KEY_FILE"],
        host="redis",
    )

    storage_endpoint = urlparse(_require(environment, "OBJECT_STORAGE_ENDPOINT_URL"))
    public_storage_endpoint = urlparse(_require(environment, "OBJECT_STORAGE_PUBLIC_ENDPOINT_URL"))
    if storage_endpoint.scheme != "https" or public_storage_endpoint.scheme != "https":
        if not (allow_local_rehearsal and mode == "rehearsal"):
            raise ContractError("Object storage endpoints must use HTTPS")
    if not storage_endpoint.hostname or not public_storage_endpoint.hostname:
        raise ContractError("Object storage endpoints must include a hostname")
    for endpoint in (storage_endpoint, public_storage_endpoint):
        endpoint_hostname = (endpoint.hostname or "").lower()
        try:
            endpoint_port = endpoint.port
        except ValueError as exc:
            raise ContractError("Object storage endpoints contain an invalid port") from exc
        if endpoint.username is not None or endpoint.password is not None:
            raise ContractError("Object storage endpoints must not contain userinfo")
        if endpoint.params or endpoint.query or endpoint.fragment:
            raise ContractError("Object storage endpoints must not contain query or fragment data")
        if not (allow_local_rehearsal and mode == "rehearsal"):
            normalized_hostname = endpoint_hostname.rstrip(".")
            try:
                endpoint_address = ipaddress.ip_address(normalized_hostname)
            except ValueError:
                endpoint_address = None
            is_rfc1918 = endpoint_address is not None and any(
                endpoint_address.version == network.version and endpoint_address in network
                for network in RFC1918_NETWORKS
            )
            if (
                endpoint_port == 0
                or endpoint_address is None
                and (
                    "." not in normalized_hostname
                    or _is_special_use_dns_name(normalized_hostname)
                    or PLACEHOLDER_RE.search(normalized_hostname)
                )
                or endpoint_address is not None
                and not (
                    endpoint_address.is_global and not endpoint_address.is_multicast or is_rfc1918
                )
            ):
                raise ContractError("Object storage endpoints must use deployable hostnames")
    for name in ("OBJECT_STORAGE_REGION", "OBJECT_STORAGE_BUCKET", "OBJECT_STORAGE_ACCESS_KEY_ID"):
        value = _require(environment, name)
        if PLACEHOLDER_RE.search(value):
            raise ContractError(f"{name} contains a placeholder")

    sentry_dsn = environment.get("SENTRY_DSN", "").strip()
    if sentry_dsn and urlparse(sentry_dsn).scheme != "https":
        raise ContractError("SENTRY_DSN must use HTTPS")

    if _require(environment, "SESSION_COOKIE_NAME") != "__Host-cardvert_session":
        raise ContractError("SESSION_COOKIE_NAME must be __Host-cardvert_session")
    for name in (
        "ALLOW_DEMO_SEED",
        "DEMO_LOGIN_ENABLED",
        "PRIVACY_DISCLOSURE_SYNTHETIC_TEST_MODE",
        "PRIVACY_COLLECTION_SYNTHETIC_TEST_MODE",
    ):
        if _is_true(environment.get(name)):
            raise ContractError(f"{name} must be false")
    if _is_true(environment.get("DEBUG")):
        raise ContractError("DEBUG must be false")
    log_level = environment.get("LOG_LEVEL", "INFO").strip().upper()
    if log_level not in {"INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ContractError("LOG_LEVEL must be a non-debug production level")
    if (
        not _is_true(environment.get("LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER"))
        or not _is_true(environment.get("LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER"))
        or environment.get("LOGIN_RATE_LIMIT_TRUSTED_PROXY_CIDRS", "").strip()
        != "10.255.254.10/32"
    ):
        raise ContractError("Login client-IP forwarding must use the exact private BFF authority")
    if (
        _is_true(environment.get("DRIVER_REGISTRATION_RATE_LIMIT_TRUST_CLIENT_IP_HEADER"))
        or environment.get("DRIVER_REGISTRATION_RATE_LIMIT_TRUSTED_PROXY_CIDRS", "").strip()
    ):
        raise ContractError(
            "Driver-registration client-IP forwarding requires a separate reviewed BFF relay"
        )

    try:
        retention_days = int(_require(environment, "BACKUP_RETENTION_DAYS"))
    except ValueError as exc:
        raise ContractError("BACKUP_RETENTION_DAYS must be an integer") from exc
    if not 1 <= retention_days <= 35:
        raise ContractError("BACKUP_RETENTION_DAYS must be from 1 through 35")
    _validate_private_key_file(_require(environment, "BACKUP_PASSPHRASE_FILE"))

    return {
        "environment": mode,
        "release_id": release_id,
        "release_revision": revision,
        "public_origin": origin.geturl().rstrip("/"),
        "data_service_adapter": data_service_adapter,
    }


def validate_release_state(state: Mapping[str, Any]) -> dict[str, Any]:
    if state.get("schema_version") != 1:
        raise ContractError("Release state schema_version must be 1")
    if not RELEASE_ID_RE.fullmatch(str(state.get("release_id", ""))):
        raise ContractError("Release state has an invalid release_id")
    if not REVISION_RE.fullmatch(str(state.get("revision", ""))):
        raise ContractError("Release state has an invalid revision")
    for field in ("backend_image", "frontend_image"):
        _validate_image(field, str(state.get(field, "")), allow_local_rehearsal=True)
    if not SHA256_RE.fullmatch(str(state.get("config_sha256", ""))):
        raise ContractError("Release state has an invalid config digest")
    stages = state.get("stages")
    if not isinstance(stages, list) or stages != list(STAGE_ORDER[: len(stages)]):
        raise ContractError("Release stages must be a consecutive, ordered prefix")
    return dict(state)


def _utc_timestamp(value: Any, *, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(f"{name} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{name} must be a UTC timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ContractError(f"{name} must be a UTC timestamp")
    return parsed.astimezone(UTC)


def _generated_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractError("Compatibility receipt generation time must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def compatibility_receipt_sha256(evidence: Mapping[str, Any]) -> str:
    return _canonical_sha256(evidence)


def _compatibility_signature(value: Mapping[str, Any], signing_secret: str) -> str:
    unsigned = {name: field for name, field in value.items() if name != "hmac_sha256"}
    return hmac.new(
        signing_secret.encode(), _canonical_json_bytes(unsigned), hashlib.sha256
    ).hexdigest()


def compatibility_acceptance_hmac(
    *,
    receipt_sha256: str,
    target_release_id: str,
    target_revision: str,
    target_backend_image: str,
    key_id: str,
    signing_secret: str,
) -> str:
    return hmac.new(
        signing_secret.encode(),
        _canonical_json_bytes(
            {
                "authority": "accepted_release_compatibility_receipt",
                "key_id": key_id,
                "receipt_sha256": receipt_sha256,
                "target_backend_image": target_backend_image,
                "target_release_id": target_release_id,
                "target_revision": target_revision,
            }
        ),
        hashlib.sha256,
    ).hexdigest()


def _validate_probe_time(
    output: Mapping[str, Any], *, generated_at: datetime, probe_name: str
) -> None:
    checked_at = _utc_timestamp(output.get("checked_at"), name=f"{probe_name} checked_at")
    if checked_at > generated_at + COMPATIBILITY_RECEIPT_FUTURE_SKEW:
        raise ContractError(f"Compatibility {probe_name} output is from the future")
    if generated_at - checked_at > COMPATIBILITY_RECEIPT_MAX_AGE:
        raise ContractError(f"Compatibility {probe_name} output is stale")


def _validate_compatibility_probe_outputs(
    probes: Any,
    *,
    previous_revision: str,
    forward_alembic_revision: str,
    generated_at: datetime,
) -> None:
    if not isinstance(probes, Mapping) or set(probes) != {"readiness", "report_schema"}:
        raise ContractError("Compatibility receipt must contain both previous-image probes")
    for probe_name in ("readiness", "report_schema"):
        probe = probes.get(probe_name)
        if not isinstance(probe, Mapping) or set(probe) != {"output", "output_sha256"}:
            raise ContractError(f"Compatibility {probe_name} probe output is missing")
        output = probe.get("output")
        digest = probe.get("output_sha256")
        if not isinstance(output, Mapping) or not SHA256_RE.fullmatch(str(digest)):
            raise ContractError(f"Compatibility {probe_name} probe output is invalid")
        if not hmac.compare_digest(str(digest), _canonical_sha256(output)):
            raise ContractError(f"Compatibility {probe_name} output digest is invalid")
        if output.get("release_revision") != previous_revision:
            raise ContractError(f"Compatibility {probe_name} did not run the previous revision")
        _validate_probe_time(output, generated_at=generated_at, probe_name=probe_name)

    readiness = probes["readiness"]["output"]
    readiness_checks = readiness.get("checks")
    readiness_database = (
        readiness_checks.get("database") if isinstance(readiness_checks, Mapping) else None
    )
    if (
        not isinstance(readiness_database, Mapping)
        or
        readiness.get("event") != "release_readiness"
        or readiness.get("status") != "ready"
        or readiness_database.get("alembic_revision") != forward_alembic_revision
    ):
        raise ContractError("Compatibility readiness output did not pass the forward schema")

    report = probes["report_schema"]["output"]
    if (
        report.get("event") != "report_schema_canary"
        or report.get("status") != "passed"
        or report.get("forward_alembic_revision") != forward_alembic_revision
        or report.get("checks")
        != {
            "report_issuances_select": "ok",
            "report_artifacts_select": "ok",
        }
    ):
        raise ContractError("Compatibility report-schema output did not pass the forward schema")


def build_compatibility_receipt(
    *,
    target_release_id: str,
    target_revision: str,
    target_backend_image: str,
    previous_release_id: str,
    previous_revision: str,
    previous_backend_image: str,
    forward_alembic_revision: str,
    readiness_output: Mapping[str, Any] | None,
    report_schema_output: Mapping[str, Any] | None,
    generated_at: datetime,
    key_id: str,
    signing_secret: str,
) -> dict[str, Any]:
    generated = _generated_timestamp(generated_at)
    probes = None
    if previous_release_id:
        if readiness_output is None or report_schema_output is None:
            raise ContractError("Previous-image compatibility requires both probe outputs")
        probes = {
            "readiness": {
                "output": dict(readiness_output),
                "output_sha256": _canonical_sha256(readiness_output),
            },
            "report_schema": {
                "output": dict(report_schema_output),
                "output_sha256": _canonical_sha256(report_schema_output),
            },
        }
    elif readiness_output is not None or report_schema_output is not None:
        raise ContractError("First-release compatibility must not invent predecessor probes")

    receipt: dict[str, Any] = {
        "schema_version": 2,
        "evidence_type": "previous_image_forward_schema_compatibility",
        "result": "passed",
        "target_release_id": target_release_id,
        "target_revision": target_revision,
        "target_backend_image": target_backend_image,
        "previous_release_id": previous_release_id or None,
        "previous_revision": previous_revision or None,
        "previous_backend_image": previous_backend_image or None,
        "forward_alembic_revision": forward_alembic_revision,
        "probes": probes,
        "generated_at": generated,
        "key_id": key_id,
    }
    receipt["hmac_sha256"] = _compatibility_signature(receipt, signing_secret)
    validate_compatibility_evidence(
        receipt,
        target_release_id=target_release_id,
        target_revision=target_revision,
        target_backend_image=target_backend_image,
        previous_release_id=previous_release_id,
        previous_revision=previous_revision,
        previous_backend_image=previous_backend_image,
        forward_alembic_revision=forward_alembic_revision,
        signing_secret=signing_secret,
        key_id=key_id,
        now=generated_at,
    )
    return receipt


def validate_compatibility_evidence(
    evidence: Mapping[str, Any],
    *,
    target_release_id: str,
    target_revision: str,
    target_backend_image: str,
    previous_release_id: str,
    previous_revision: str,
    previous_backend_image: str,
    forward_alembic_revision: str,
    signing_secret: str,
    key_id: str,
    now: datetime | None = None,
    accepted_receipt_sha256: str = "",
    accepted_receipt_hmac: str = "",
) -> dict[str, Any]:
    value = dict(evidence)
    required_fields = {
        "schema_version",
        "evidence_type",
        "result",
        "target_release_id",
        "target_revision",
        "target_backend_image",
        "previous_release_id",
        "previous_revision",
        "previous_backend_image",
        "forward_alembic_revision",
        "probes",
        "generated_at",
        "key_id",
        "hmac_sha256",
    }
    if set(value) != required_fields:
        raise ContractError("Compatibility receipt fields are incomplete or unsupported")
    expected = {
        "schema_version": 2,
        "evidence_type": "previous_image_forward_schema_compatibility",
        "result": "passed",
        "target_release_id": target_release_id,
        "target_revision": target_revision,
        "target_backend_image": target_backend_image,
        "previous_release_id": previous_release_id or None,
        "previous_revision": previous_revision or None,
        "previous_backend_image": previous_backend_image or None,
        "forward_alembic_revision": forward_alembic_revision,
        "key_id": key_id,
    }
    for name, expected_value in expected.items():
        if value.get(name) != expected_value:
            raise ContractError(f"Compatibility receipt conflicts on {name}")

    if not RELEASE_ID_RE.fullmatch(target_release_id) or not REVISION_RE.fullmatch(target_revision):
        raise ContractError("Compatibility receipt target identity is invalid")
    _validate_image("target_backend_image", target_backend_image, allow_local_rehearsal=True)
    if not forward_alembic_revision.strip():
        raise ContractError("Compatibility receipt lacks the forward migration revision")
    if not RELEASE_EVIDENCE_KEY_ID_RE.fullmatch(key_id):
        raise ContractError("Compatibility receipt key ID is invalid")
    _validate_secret("RELEASE_EVIDENCE_SIGNING_SECRET", signing_secret)

    generated_at = _utc_timestamp(value.get("generated_at"), name="generated_at")
    observed_now = now or datetime.now(UTC)
    if observed_now.tzinfo is None or observed_now.utcoffset() is None:
        raise ContractError("Compatibility validation time must be timezone-aware")
    observed_now = observed_now.astimezone(UTC)
    if generated_at > observed_now + COMPATIBILITY_RECEIPT_FUTURE_SKEW:
        raise ContractError("Compatibility receipt generation time is in the future")

    receipt_sha256 = compatibility_receipt_sha256(value)
    anchored = False
    if accepted_receipt_sha256:
        if not SHA256_RE.fullmatch(accepted_receipt_sha256):
            raise ContractError("Compatibility accepted receipt digest is invalid")
        if not hmac.compare_digest(receipt_sha256, accepted_receipt_sha256):
            raise ContractError("Compatibility accepted receipt digest does not match")
        expected_acceptance_hmac = compatibility_acceptance_hmac(
            receipt_sha256=receipt_sha256,
            target_release_id=target_release_id,
            target_revision=target_revision,
            target_backend_image=target_backend_image,
            key_id=key_id,
            signing_secret=signing_secret,
        )
        if (
            not SHA256_RE.fullmatch(accepted_receipt_hmac)
            or not hmac.compare_digest(accepted_receipt_hmac, expected_acceptance_hmac)
        ):
            raise ContractError("Compatibility accepted receipt authority is invalid")
        anchored = True
    elif accepted_receipt_hmac:
        raise ContractError("Compatibility accepted receipt authority lacks its digest")
    if observed_now - generated_at > COMPATIBILITY_RECEIPT_MAX_AGE and not anchored:
        raise ContractError("Compatibility receipt is stale")

    signature = value.get("hmac_sha256")
    if not isinstance(signature, str) or not SHA256_RE.fullmatch(signature):
        raise ContractError("Compatibility receipt HMAC is invalid")
    expected_signature = _compatibility_signature(value, signing_secret)
    if not hmac.compare_digest(signature, expected_signature):
        raise ContractError("Compatibility receipt HMAC is invalid")

    if previous_release_id:
        if not RELEASE_ID_RE.fullmatch(previous_release_id):
            raise ContractError("Compatibility receipt previous release is invalid")
        if not REVISION_RE.fullmatch(previous_revision):
            raise ContractError("Compatibility receipt previous revision is invalid")
        _validate_image(
            "previous_backend_image", previous_backend_image, allow_local_rehearsal=True
        )
        _validate_compatibility_probe_outputs(
            value["probes"],
            previous_revision=previous_revision,
            forward_alembic_revision=forward_alembic_revision,
            generated_at=generated_at,
        )
    elif previous_revision or previous_backend_image or value.get("probes") is not None:
        raise ContractError("First-release compatibility receipt must not invent a predecessor")
    return value


def build_backup_manifest(
    *,
    release_id: str,
    release_revision: str,
    config_sha256: str,
    alembic_revision: str,
    database_sha256: str,
    database_bytes: int,
    database_marker: str,
    objects: list[dict[str, Any]],
    retention_days: int,
    created_at: str,
) -> dict[str, Any]:
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    expires = created + timedelta(days=retention_days)
    ordered_objects = sorted(objects, key=lambda item: (item["key"], item["version_id"]))
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "state": "complete",
        "release_id": release_id,
        "release_revision": release_revision,
        "config_sha256": config_sha256,
        "alembic_revision": alembic_revision,
        "database_sha256": database_sha256,
        "database_bytes": database_bytes,
        "database_marker": database_marker,
        "objects": ordered_objects,
        "object_count": len(ordered_objects),
        "object_bytes": sum(int(item["bytes"]) for item in ordered_objects),
        "created_at": created.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "retention_days": retention_days,
        "expires_at": expires.astimezone(UTC).isoformat().replace("+00:00", "Z"),
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return validate_backup_manifest(manifest)


def validate_backup_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(manifest)
    supplied_digest = str(value.pop("manifest_sha256", ""))
    if not SHA256_RE.fullmatch(supplied_digest) or supplied_digest != _canonical_sha256(value):
        raise ContractError("Backup manifest digest mismatch")
    if value.get("schema_version") != 1 or value.get("state") != "complete":
        raise ContractError("Backup manifest is not complete schema version 1")
    if not RELEASE_ID_RE.fullmatch(str(value.get("release_id", ""))):
        raise ContractError("Backup manifest release_id is invalid")
    if not REVISION_RE.fullmatch(str(value.get("release_revision", ""))):
        raise ContractError("Backup manifest release revision is invalid")
    for field in ("config_sha256", "database_sha256"):
        if not SHA256_RE.fullmatch(str(value.get(field, ""))):
            raise ContractError(f"Backup manifest {field} is invalid")
    if (
        not str(value.get("alembic_revision", "")).strip()
        or not str(value.get("database_marker", "")).strip()
    ):
        raise ContractError("Backup manifest lacks database revision/marker authority")
    if not isinstance(value.get("database_bytes"), int) or value["database_bytes"] <= 0:
        raise ContractError("Backup database size must be positive")
    retention_days = value.get("retention_days")
    if not isinstance(retention_days, int) or not 1 <= retention_days <= 35:
        raise ContractError("Backup retention must be from 1 through 35 days")
    objects = value.get("objects")
    if not isinstance(objects, list):
        raise ContractError("Backup object inventory must be a list")
    keys: set[tuple[str, str]] = set()
    for item in objects:
        if not isinstance(item, dict):
            raise ContractError("Backup object entry must be an object")
        identity = (str(item.get("key", "")), str(item.get("version_id", "")))
        if not identity[0] or not identity[1] or identity in keys:
            raise ContractError("Backup object keys/versions must be present and unique")
        keys.add(identity)
        if not SHA256_RE.fullmatch(str(item.get("sha256", ""))):
            raise ContractError("Backup object sha256 is invalid")
        if not isinstance(item.get("bytes"), int) or item["bytes"] < 0:
            raise ContractError("Backup object size is invalid")
    if value.get("object_count") != len(objects) or value.get("object_bytes") != sum(
        item["bytes"] for item in objects
    ):
        raise ContractError("Backup object totals disagree with inventory")
    value["manifest_sha256"] = supplied_digest
    return value


def validate_backup_authority(
    *,
    complete_marker: Mapping[str, Any],
    manifest: Mapping[str, Any],
    release_state: Mapping[str, Any],
    bundle_sha256: str,
    expected_release_id: str,
    expected_release_revision: str,
    expected_config_sha256: str,
) -> dict[str, Any]:
    complete = dict(complete_marker)
    validated_manifest = validate_backup_manifest(manifest)
    validated_state = validate_release_state(release_state)
    if complete.get("schema_version") != 1 or complete.get("state") != "complete":
        raise ContractError("Backup complete marker is invalid")
    if not SHA256_RE.fullmatch(bundle_sha256) or complete.get("bundle_sha256") != bundle_sha256:
        raise ContractError("Backup complete marker does not bind the ciphertext")
    if complete.get("manifest_sha256") != validated_manifest["manifest_sha256"]:
        raise ContractError("Backup complete marker does not bind the manifest")
    expected_identity = {
        "release_id": expected_release_id,
        "release_revision": expected_release_revision,
        "config_sha256": expected_config_sha256,
    }
    for field, expected in expected_identity.items():
        if complete.get(field) != expected or validated_manifest.get(field) != expected:
            raise ContractError(f"Backup authority conflicts on {field}")
    state_identity = {
        "release_id": expected_release_id,
        "revision": expected_release_revision,
        "config_sha256": expected_config_sha256,
    }
    for field, expected in state_identity.items():
        if validated_state.get(field) != expected:
            raise ContractError(f"Bundled release state conflicts on {field}")
    if (
        complete.get("created_at") != validated_manifest["created_at"]
        or complete.get("expires_at") != validated_manifest["expires_at"]
    ):
        raise ContractError("Backup completion and retention times disagree")
    try:
        expires = datetime.fromisoformat(str(complete["expires_at"]).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ContractError("Backup complete marker expiry is invalid") from exc
    if expires.tzinfo is None:
        raise ContractError("Backup complete marker expiry must include a timezone")
    if expires <= datetime.now(UTC):
        raise ContractError("Backup complete marker is expired")
    return {
        **expected_identity,
        "bundle_sha256": bundle_sha256,
        "manifest_sha256": validated_manifest["manifest_sha256"],
        "expires_at": complete["expires_at"],
    }


def read_env_file(path: Path) -> dict[str, str]:
    environment: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ContractError(f"Invalid environment line {line_number}")
        name, value = line.split("=", 1)
        if not name or name != name.strip() or name in environment:
            raise ContractError(f"Invalid or duplicate environment name on line {line_number}")
        environment[name] = value
    return environment


def validate_compose_model(model: Mapping[str, Any]) -> None:
    services = model.get("services")
    if not isinstance(services, dict):
        raise ContractError("Compose model has no services")
    allowed = {"api", "db", "edge", "frontend", "migrate", "redis", "worker"}
    required = {"api", "db", "edge", "frontend", "redis", "worker"}
    if not set(services) <= allowed or not required <= set(services):
        raise ContractError("Compose model contains missing or unapproved services")
    for name, service in services.items():
        if "build" in service:
            raise ContractError(f"{name} must not build on the release host")
        if service.get("privileged") or service.get("network_mode"):
            raise ContractError(f"{name} has an unsafe privilege or network mode")
        _validate_image(f"{name}.image", str(service.get("image", "")), allow_local_rehearsal=True)
        if name != "edge" and service.get("ports"):
            raise ContractError(f"{name} must not publish host ports")
        for volume in service.get("volumes", []):
            if volume.get("type") != "bind":
                continue
            if not (
                name == "edge"
                and Path(str(volume.get("source", ""))).resolve() == ROOT / "Caddyfile"
                and volume.get("target") == "/etc/caddy/Caddyfile"
                and volume.get("read_only") is True
            ):
                raise ContractError(f"{name} contains an unapproved host bind mount")
    edge_ports = [
        (str(item.get("published")), int(item.get("target", 0)), item.get("protocol", "tcp"))
        for item in services["edge"].get("ports", [])
    ]
    if edge_ports != [("80", 80, "tcp"), ("443", 443, "tcp"), ("443", 443, "udp")]:
        raise ContractError("Only edge ports 80/443 TCP and 443 UDP may be public")
    expected_networks = {
        "api": {"app", "data", "egress"},
        "db": {"data"},
        "edge": {"app", "edge"},
        "frontend": {"app", "edge", "egress"},
        "migrate": {"app", "data", "egress"},
        "redis": {"data"},
        "worker": {"app", "data", "egress"},
    }
    for name, expected in expected_networks.items():
        if name in services and set(services[name].get("networks", {})) != expected:
            raise ContractError(f"{name} is attached to an unsafe network set")
    networks = model.get("networks", {})
    if set(networks) != {"app", "data", "edge", "egress"}:
        raise ContractError("Production networks must match the approved topology")
    if not networks["app"].get("internal") or not networks["data"].get("internal"):
        raise ContractError("Application and data networks must be private")
    if networks["edge"].get("internal") or networks["egress"].get("internal"):
        raise ContractError("Edge and egress networks have an invalid direction")
    frontend_environment = services["frontend"].get("environment", {})
    api_environment = services["api"].get("environment", {})
    missing_settings = sorted(settings_environment_names() - api_environment.keys())
    if missing_settings:
        raise ContractError(
            "Production Compose omits live Settings names: " + ", ".join(missing_settings)
        )
    if (
        frontend_environment.get("LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER") != "true"
        or api_environment.get("LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER") != "true"
        or api_environment.get("LOGIN_RATE_LIMIT_TRUSTED_PROXY_CIDRS") != "10.255.254.10/32"
        or services["frontend"]["networks"]["app"].get("ipv4_address") != "10.255.254.10"
        or networks["app"].get("ipam", {}).get("config") != [{"subnet": "10.255.254.0/24"}]
    ):
        raise ContractError("Login client-IP forwarding topology is not the exact private BFF")
    for name in ("api", "frontend", "migrate", "worker"):
        service = services.get(name)
        if service is None:
            continue
        if (
            service.get("read_only") is not True
            or service.get("cap_drop") != ["ALL"]
            or service.get("security_opt") != ["no-new-privileges:true"]
        ):
            raise ContractError(f"{name} lacks the required runtime confinement")


def _render_compose(compose_file: Path, env_file: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "--profile",
            "release",
            "--env-file",
            str(env_file),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ContractError(f"Compose render failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _check_image_labels(
    model: Mapping[str, Any], revision: str, environment: Mapping[str, str]
) -> None:
    checked: set[str] = set()
    for service in ("api", "frontend"):
        image = str(model["services"][service]["image"])
        if image in checked:
            continue
        checked.add(image)
        result = subprocess.run(
            [
                "docker",
                "image",
                "inspect",
                image,
                "--format",
                '{{index .Config.Labels "org.opencontainers.image.revision"}}',
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode or result.stdout.strip() != revision:
            raise ContractError(f"{service} image revision label does not match RELEASE_REVISION")
    frontend_image = str(model["services"]["frontend"]["image"])
    for name in frontend_build_environment_names():
        value = environment.get(name, "").strip()
        if not value:
            continue
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "sh",
                frontend_image,
                "-c",
                'grep -R -F -l -- "$1" /app/.next >/dev/null',
                "release-build-input-check",
                value,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise ContractError(f"Frontend image does not contain the approved {name} build input")


def _check_release_checkout(revision: str, *, allow_local_rehearsal: bool) -> None:
    if allow_local_rehearsal:
        return
    commands = (
        ["git", "rev-parse", "HEAD"],
        ["git", "diff", "--quiet"],
        ["git", "diff", "--cached", "--quiet"],
    )
    results = [
        subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
        for command in commands
    ]
    if results[0].returncode or results[0].stdout.strip() != revision:
        raise ContractError("Release checkout does not match RELEASE_REVISION")
    if results[1].returncode or results[2].returncode:
        raise ContractError("Release checkout contains uncommitted tracked changes")


def _write_private_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_new_private_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise ContractError(
                "Compatibility receipt already exists and cannot be overwritten"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def _read_private_json(path: Path, *, label: str) -> dict[str, Any]:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise ContractError(f"{label} must not be a symbolic link")
    resolved = expanded.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise ContractError(f"{label} must stay outside the repository")
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(resolved, flags)
        with os.fdopen(descriptor, encoding="utf-8") as source:
            details = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.geteuid()
                or details.st_mode & (stat.S_IRWXG | stat.S_IRWXO)
            ):
                raise ContractError(f"{label} must be an owner-only regular file")
            value = json.load(source)
    except json.JSONDecodeError as exc:
        raise ContractError(f"{label} must contain JSON") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{label} must contain a JSON object")
    return value


def _cli_preflight(args: argparse.Namespace) -> int:
    env_file = Path(args.env_file).resolve()
    compose_file = Path(args.compose_file).resolve()
    if compose_file != ROOT / "docker-compose.production.yml":
        raise ContractError("Release preflight requires the reviewed production Compose file")
    if ROOT == env_file or ROOT in env_file.parents:
        raise ContractError("Release environment file must stay outside the repository")
    if not env_file.is_file() or env_file.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ContractError("Release environment file must be a mode-0600 regular file")
    environment = read_env_file(env_file)
    validated = validate_release_environment(
        environment, allow_local_rehearsal=args.local_rehearsal
    )
    checkout_revision = args.expected_checkout_revision or validated["release_revision"]
    if not REVISION_RE.fullmatch(checkout_revision):
        raise ContractError("Expected checkout revision must be a full Git revision")
    _check_release_checkout(checkout_revision, allow_local_rehearsal=args.local_rehearsal)
    model = _render_compose(compose_file, env_file)
    validate_compose_model(model)
    if args.check_images:
        _check_image_labels(model, validated["release_revision"], environment)
    caddyfile_sha256 = hashlib.sha256((ROOT / "Caddyfile").read_bytes()).hexdigest()
    output = {
        **validated,
        "caddyfile_sha256": caddyfile_sha256,
        "checkout_revision": checkout_revision,
        "config_sha256": release_config_sha256(
            caddyfile_sha256=caddyfile_sha256,
            compose=model,
            environment=environment,
        ),
        "services": sorted(model["services"]),
        "status": "ready",
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


def _cli_state_init(args: argparse.Namespace) -> int:
    path = Path(args.state_file).resolve()
    state = validate_release_state(
        {
            "schema_version": 1,
            "release_id": args.release_id,
            "revision": args.revision,
            "backend_image": args.backend_image,
            "frontend_image": args.frontend_image,
            "config_sha256": args.config_sha256,
            "previous_release_id": args.previous_release_id or None,
            "stages": [],
            "events": [],
        }
    )
    if path.exists():
        existing = validate_release_state(json.loads(path.read_text()))
        for field in (
            "release_id",
            "revision",
            "backend_image",
            "frontend_image",
            "config_sha256",
            "previous_release_id",
        ):
            if existing.get(field) != state.get(field):
                raise ContractError(f"Existing release state conflicts on {field}")
        state = existing
    else:
        _write_private_json(path, state)
    print(json.dumps(state, sort_keys=True, separators=(",", ":")))
    return 0


def _cli_state_advance(args: argparse.Namespace) -> int:
    path = Path(args.state_file).resolve()
    state = validate_release_state(json.loads(path.read_text()))
    if state["release_id"] != args.release_id:
        raise ContractError("Release ID does not own this state file")
    stage_index = STAGE_ORDER.index(args.stage)
    stages = state["stages"]
    if args.stage in stages:
        print(json.dumps(state, sort_keys=True, separators=(",", ":")))
        return 0
    if len(stages) != stage_index:
        raise ContractError("Release stage cannot skip or reorder the state machine")
    stages.append(args.stage)
    state.setdefault("events", []).append(
        {
            "stage": args.stage,
            "outcome": args.outcome,
            "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
    )
    validate_release_state(state)
    _write_private_json(path, state)
    print(json.dumps(state, sort_keys=True, separators=(",", ":")))
    return 0


def _cli_backup_manifest(args: argparse.Namespace) -> int:
    objects = json.loads(Path(args.objects_json).read_text())
    manifest = build_backup_manifest(
        release_id=args.release_id,
        release_revision=args.release_revision,
        config_sha256=args.config_sha256,
        alembic_revision=args.alembic_revision,
        database_sha256=args.database_sha256,
        database_bytes=args.database_bytes,
        database_marker=args.database_marker,
        objects=objects,
        retention_days=args.retention_days,
        created_at=args.created_at,
    )
    _write_private_json(Path(args.output).resolve(), manifest)
    print(manifest["manifest_sha256"])
    return 0


def _cli_manifest_validate(args: argparse.Namespace) -> int:
    manifest = validate_backup_manifest(json.loads(Path(args.manifest).read_text()))
    print(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    return 0


def _cli_compatibility_generate(args: argparse.Namespace) -> int:
    output_path = Path(args.output).expanduser().resolve()
    if output_path == ROOT or ROOT in output_path.parents:
        raise ContractError("Compatibility receipt must stay outside the repository")
    if output_path.exists():
        raise ContractError("Compatibility receipt already exists and cannot be overwritten")
    environment = read_env_file(Path(args.env_file).expanduser().resolve())
    signing_secret, key_id = validate_release_evidence_configuration(environment)
    readiness_output = (
        _read_private_json(Path(args.readiness_output), label="Readiness probe output")
        if args.readiness_output
        else None
    )
    report_schema_output = (
        _read_private_json(Path(args.report_schema_output), label="Report-schema probe output")
        if args.report_schema_output
        else None
    )
    receipt = build_compatibility_receipt(
        target_release_id=args.target_release_id,
        target_revision=args.target_revision,
        target_backend_image=args.target_backend_image,
        previous_release_id=args.previous_release_id,
        previous_revision=args.previous_revision,
        previous_backend_image=args.previous_backend_image,
        forward_alembic_revision=args.forward_alembic_revision,
        readiness_output=readiness_output,
        report_schema_output=report_schema_output,
        generated_at=datetime.now(UTC),
        key_id=key_id,
        signing_secret=signing_secret,
    )
    _write_new_private_json(output_path, receipt)
    print(compatibility_receipt_sha256(receipt))
    return 0


def _cli_compatibility_validate(args: argparse.Namespace) -> int:
    environment = read_env_file(Path(args.env_file).expanduser().resolve())
    signing_secret, key_id = validate_release_evidence_configuration(environment)
    evidence = validate_compatibility_evidence(
        _read_private_json(Path(args.evidence), label="Compatibility receipt"),
        target_release_id=args.target_release_id,
        target_revision=args.target_revision,
        target_backend_image=args.target_backend_image,
        previous_release_id=args.previous_release_id,
        previous_revision=args.previous_revision,
        previous_backend_image=args.previous_backend_image,
        forward_alembic_revision=args.forward_alembic_revision,
        signing_secret=signing_secret,
        key_id=key_id,
        accepted_receipt_sha256=args.accepted_receipt_sha256,
        accepted_receipt_hmac=args.accepted_receipt_hmac,
    )
    receipt_sha256 = compatibility_receipt_sha256(evidence)
    acceptance_hmac = compatibility_acceptance_hmac(
        receipt_sha256=receipt_sha256,
        target_release_id=args.target_release_id,
        target_revision=args.target_revision,
        target_backend_image=args.target_backend_image,
        key_id=key_id,
        signing_secret=signing_secret,
    )
    print(f"{receipt_sha256}:{acceptance_hmac}")
    return 0


def _cli_backup_authority_validate(args: argparse.Namespace) -> int:
    authority = validate_backup_authority(
        complete_marker=json.loads(Path(args.complete_marker).read_text()),
        manifest=json.loads(Path(args.manifest).read_text()),
        release_state=json.loads(Path(args.release_state).read_text()),
        bundle_sha256=args.bundle_sha256,
        expected_release_id=args.expected_release_id,
        expected_release_revision=args.expected_release_revision,
        expected_config_sha256=args.expected_config_sha256,
    )
    print(json.dumps(authority, sort_keys=True, separators=(",", ":")))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--env-file", required=True)
    preflight.add_argument("--compose-file", default=str(ROOT / "docker-compose.production.yml"))
    preflight.add_argument("--local-rehearsal", action="store_true")
    preflight.add_argument("--check-images", action="store_true")
    preflight.add_argument("--expected-checkout-revision", default="")
    preflight.set_defaults(handler=_cli_preflight)
    state_init = subparsers.add_parser("state-init")
    state_init.add_argument("--state-file", required=True)
    state_init.add_argument("--release-id", required=True)
    state_init.add_argument("--revision", required=True)
    state_init.add_argument("--backend-image", required=True)
    state_init.add_argument("--frontend-image", required=True)
    state_init.add_argument("--config-sha256", required=True)
    state_init.add_argument("--previous-release-id", default="")
    state_init.set_defaults(handler=_cli_state_init)
    state_advance = subparsers.add_parser("state-advance")
    state_advance.add_argument("--state-file", required=True)
    state_advance.add_argument("--release-id", required=True)
    state_advance.add_argument("--stage", required=True, choices=STAGE_ORDER)
    state_advance.add_argument("--outcome", default="passed")
    state_advance.set_defaults(handler=_cli_state_advance)
    backup_manifest = subparsers.add_parser("backup-manifest")
    backup_manifest.add_argument("--release-id", required=True)
    backup_manifest.add_argument("--release-revision", required=True)
    backup_manifest.add_argument("--config-sha256", required=True)
    backup_manifest.add_argument("--alembic-revision", required=True)
    backup_manifest.add_argument("--database-sha256", required=True)
    backup_manifest.add_argument("--database-bytes", required=True, type=int)
    backup_manifest.add_argument("--database-marker", required=True)
    backup_manifest.add_argument("--objects-json", required=True)
    backup_manifest.add_argument("--retention-days", required=True, type=int)
    backup_manifest.add_argument("--created-at", required=True)
    backup_manifest.add_argument("--output", required=True)
    backup_manifest.set_defaults(handler=_cli_backup_manifest)
    manifest_validate = subparsers.add_parser("manifest-validate")
    manifest_validate.add_argument("--manifest", required=True)
    manifest_validate.set_defaults(handler=_cli_manifest_validate)
    compatibility_generate = subparsers.add_parser("compatibility-generate")
    compatibility_generate.add_argument("--output", required=True)
    compatibility_generate.add_argument("--env-file", required=True)
    compatibility_generate.add_argument("--target-release-id", required=True)
    compatibility_generate.add_argument("--target-revision", required=True)
    compatibility_generate.add_argument("--target-backend-image", required=True)
    compatibility_generate.add_argument("--previous-release-id", default="")
    compatibility_generate.add_argument("--previous-revision", default="")
    compatibility_generate.add_argument("--previous-backend-image", default="")
    compatibility_generate.add_argument("--forward-alembic-revision", required=True)
    compatibility_generate.add_argument("--readiness-output", default="")
    compatibility_generate.add_argument("--report-schema-output", default="")
    compatibility_generate.set_defaults(handler=_cli_compatibility_generate)
    compatibility_validate = subparsers.add_parser("compatibility-validate")
    compatibility_validate.add_argument("--evidence", required=True)
    compatibility_validate.add_argument("--env-file", required=True)
    compatibility_validate.add_argument("--target-release-id", required=True)
    compatibility_validate.add_argument("--target-revision", required=True)
    compatibility_validate.add_argument("--target-backend-image", required=True)
    compatibility_validate.add_argument("--previous-release-id", default="")
    compatibility_validate.add_argument("--previous-revision", default="")
    compatibility_validate.add_argument("--previous-backend-image", default="")
    compatibility_validate.add_argument("--forward-alembic-revision", required=True)
    compatibility_validate.add_argument("--accepted-receipt-sha256", default="")
    compatibility_validate.add_argument("--accepted-receipt-hmac", default="")
    compatibility_validate.set_defaults(handler=_cli_compatibility_validate)
    backup_authority_validate = subparsers.add_parser("backup-authority-validate")
    backup_authority_validate.add_argument("--complete-marker", required=True)
    backup_authority_validate.add_argument("--manifest", required=True)
    backup_authority_validate.add_argument("--release-state", required=True)
    backup_authority_validate.add_argument("--bundle-sha256", required=True)
    backup_authority_validate.add_argument("--expected-release-id", required=True)
    backup_authority_validate.add_argument("--expected-release-revision", required=True)
    backup_authority_validate.add_argument("--expected-config-sha256", required=True)
    backup_authority_validate.set_defaults(handler=_cli_backup_authority_validate)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        payload = {"event": "release_contract", "status": "failed", "reason": str(exc)}
        print(json.dumps(payload), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

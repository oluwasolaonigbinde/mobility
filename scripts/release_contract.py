#!/usr/bin/env python3
"""Fail-closed W4-03A release, state, and recovery manifest contracts."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
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
)
BUNDLED_REQUIRED_NAMES = ("POSTGIS_IMAGE", "REDIS_IMAGE", *TLS_FILE_NAMES)
STAGE_ORDER = (
    "preflight",
    "backup",
    "migration",
    "compatibility",
    "traffic",
)


class ContractError(ValueError):
    """A production or recovery contract is incomplete or unsafe."""


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _require(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ContractError(f"{name} is required")
    return value


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
    elif mode != "production":
        raise ContractError("ENVIRONMENT must be production")

    data_service_adapter = validate_data_service_urls(environment)
    if data_service_adapter != "bundled":
        raise ContractError(
            "MANAGED_DATA_RELEASE_ADAPTER_REQUIRED: bundled release automation cannot "
            "operate managed data services"
        )
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


def validate_compatibility_evidence(
    evidence: Mapping[str, Any],
    *,
    target_release_id: str,
    target_revision: str,
    target_backend_image: str,
    previous_release_id: str,
    forward_alembic_revision: str,
) -> dict[str, Any]:
    value = dict(evidence)
    checks = (
        {
            "no_database_downgrade": True,
            "previous_image_readiness": True,
            "previous_image_report_schema_canary": True,
        }
        if previous_release_id
        else {"first_release_no_predecessor": True, "no_database_downgrade": True}
    )
    expected = {
        "schema_version": 1,
        "result": "passed",
        "target_release_id": target_release_id,
        "target_revision": target_revision,
        "target_backend_image": target_backend_image,
        "previous_release_id": previous_release_id or None,
        "forward_alembic_revision": forward_alembic_revision,
        "checks": checks,
    }
    for name, expected_value in expected.items():
        if value.get(name) != expected_value:
            raise ContractError(f"Compatibility evidence conflicts on {name}")
    if not RELEASE_ID_RE.fullmatch(target_release_id) or not REVISION_RE.fullmatch(target_revision):
        raise ContractError("Compatibility evidence target identity is invalid")
    _validate_image("target_backend_image", target_backend_image, allow_local_rehearsal=True)
    if not forward_alembic_revision.strip():
        raise ContractError("Compatibility evidence lacks the forward migration revision")
    if previous_release_id:
        if not RELEASE_ID_RE.fullmatch(previous_release_id):
            raise ContractError("Compatibility evidence previous release is invalid")
        previous_revision = str(value.get("previous_revision", ""))
        previous_backend_image = str(value.get("previous_backend_image", ""))
        if not REVISION_RE.fullmatch(previous_revision):
            raise ContractError("Compatibility evidence previous revision is invalid")
        _validate_image(
            "previous_backend_image", previous_backend_image, allow_local_rehearsal=True
        )
    elif (
        value.get("previous_revision") is not None
        or value.get("previous_backend_image") is not None
    ):
        raise ContractError("First-release compatibility evidence must not invent a predecessor")
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


def _check_image_labels(model: Mapping[str, Any], revision: str) -> None:
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
        _check_image_labels(model, validated["release_revision"])
    caddyfile_sha256 = hashlib.sha256((ROOT / "Caddyfile").read_bytes()).hexdigest()
    output = {
        **validated,
        "caddyfile_sha256": caddyfile_sha256,
        "checkout_revision": checkout_revision,
        "config_sha256": _canonical_sha256(
            {"caddyfile_sha256": caddyfile_sha256, "compose": model}
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


def _cli_compatibility_validate(args: argparse.Namespace) -> int:
    evidence = validate_compatibility_evidence(
        json.loads(Path(args.evidence).read_text()),
        target_release_id=args.target_release_id,
        target_revision=args.target_revision,
        target_backend_image=args.target_backend_image,
        previous_release_id=args.previous_release_id,
        forward_alembic_revision=args.forward_alembic_revision,
    )
    print(_canonical_sha256(evidence))
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
    compatibility_validate = subparsers.add_parser("compatibility-validate")
    compatibility_validate.add_argument("--evidence", required=True)
    compatibility_validate.add_argument("--target-release-id", required=True)
    compatibility_validate.add_argument("--target-revision", required=True)
    compatibility_validate.add_argument("--target-backend-image", required=True)
    compatibility_validate.add_argument("--previous-release-id", default="")
    compatibility_validate.add_argument("--forward-alembic-revision", required=True)
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

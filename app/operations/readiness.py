"""Layered operator readiness probe; it does not alter HTTP traffic readiness."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.scanner import MalwareScanVerdict, build_malware_scanner
from app.adapters.storage import build_storage_provider
from app.core.config import LOCAL_ENVIRONMENTS, Settings, get_settings

WORKER_HEALTH_KEY = "arq:queue:health-check"
WORKER_HEALTH_MAX_TTL_SECONDS = 31
COMPONENT_TIMEOUT_SECONDS = 2
OVERALL_TIMEOUT_SECONDS = 5
SUCCESS_CACHE_SECONDS = 30
FAILURE_CACHE_SECONDS = 5


async def _database_check(database_url: str, *, allow_database_ahead: bool) -> dict[str, str]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT (SELECT version_num FROM alembic_version), "
                        "(SELECT extversion FROM pg_extension WHERE extname='postgis')"
                    )
                )
            ).one()
    finally:
        await engine.dispose()
    code_head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    if not code_head or (row[0] != code_head and not allow_database_ahead) or not row[1]:
        raise RuntimeError("database migration or PostGIS revision is not ready")
    return {"alembic_revision": row[0], "postgis_version": row[1]}


async def _broker_check(redis_url: str) -> dict[str, int | str]:
    redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        if not await redis.ping():
            raise RuntimeError("broker ping failed")
        if await redis.eval("return 1", 0) != 1:
            raise RuntimeError("broker script check failed")
        queue_depth = await redis.zcard("arq:queue")
    finally:
        await redis.aclose()
    return {"status": "ok", "queue_depth": int(queue_depth)}


async def _storage_check(*, write_canary: bool, settings: Settings | None = None) -> dict[str, str]:
    if not write_canary:
        raise RuntimeError("storage readiness requires the private write/read/delete canary")
    settings = settings or get_settings()
    storage = build_storage_provider(settings)
    revision = settings.release_revision or "unversioned"
    canary_key = f"release-canary/{revision}/{uuid4().hex}"
    payload = b"cardvert-private-storage-readiness-v1"
    digest = hashlib.sha256(payload).hexdigest()
    try:
        observed = await storage.put(
            object_key=canary_key,
            content_type="application/octet-stream",
            data=payload,
            checksum_sha256=digest,
        )
        if observed.checksum_sha256 != digest:
            raise RuntimeError("storage canary checksum mismatch")
        streamed = bytearray()
        async for chunk in storage.stream(canary_key):
            streamed.extend(chunk)
        if hashlib.sha256(streamed).hexdigest() != digest:
            raise RuntimeError("storage canary read mismatch")
        anonymous_url = (
            f"{settings.object_storage_public_endpoint_url.rstrip('/')}"
            f"/{quote(settings.object_storage_bucket, safe='')}"
            f"/{quote(canary_key, safe='/')}"
        )
        try:
            response = await asyncio.to_thread(urlopen, anonymous_url, None, 5)
        except HTTPError as exc:
            if exc.code not in {401, 403, 404}:
                raise RuntimeError("storage privacy canary returned an unsafe response") from exc
        else:
            response.close()
            raise RuntimeError("storage canary is anonymously readable")
    finally:
        await storage.delete(canary_key)
    return {"status": "private_read_write_delete_ok"}


async def _worker_check(redis_url: str) -> dict[str, str]:
    redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        value, ttl_ms = await asyncio.gather(
            redis.get(WORKER_HEALTH_KEY), redis.pttl(WORKER_HEALTH_KEY)
        )
    finally:
        await redis.aclose()
    if not value or ttl_ms <= 0 or ttl_ms > WORKER_HEALTH_MAX_TTL_SECONDS * 1000:
        raise RuntimeError("worker health key is missing or stale")
    return {"status": "ok"}


async def _scanner_check(settings: Settings) -> dict[str, str]:
    scanner = build_malware_scanner(settings)

    async def benign_stream():
        yield b"cardvert-readiness-benign-v1"

    result = await scanner.scan(benign_stream())
    if result.verdict is not MalwareScanVerdict.CLEAN or result.signature is not None:
        raise RuntimeError("scanner did not return the exact clean verdict")
    return {"status": "ok"}


async def _signing_check(settings: Settings) -> dict[str, str]:
    keys = settings.trip_evidence_signing_keys
    if not keys or settings.trip_evidence_signing_key_version not in keys:
        raise RuntimeError("trip evidence signing authority is unavailable")
    if not settings.database_url:
        return {"status": "ok"}
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT evidence_manifest_receipt_key_version FROM trip_sessions "
                    "WHERE evidence_manifest_receipt_key_version IS NOT NULL UNION "
                    "SELECT receipt_key_version FROM location_ping_batches "
                    "WHERE receipt_key_version IS NOT NULL UNION "
                    "SELECT receipt_key_version FROM quarantined_ping_batches "
                    "WHERE receipt_key_version IS NOT NULL"
                )
            )
            referenced = {int(row[0]) for row in rows.all()}
    finally:
        await engine.dispose()
    if not referenced.issubset(keys):
        raise RuntimeError("trip evidence signing authority is incomplete")
    return {"status": "ok"}


@dataclass(frozen=True, slots=True)
class PublicReadiness:
    ready: bool
    components: dict[str, str]


async def _component_state(configured: bool, check) -> str:
    if not configured:
        return "not_configured"
    try:
        await asyncio.wait_for(check(), timeout=COMPONENT_TIMEOUT_SECONDS)
    except Exception:
        return "unavailable"
    return "ok"


async def _run_component_checks(settings: Settings) -> PublicReadiness:
    storage_configured = all(
        (
            settings.object_storage_endpoint_url.strip(),
            settings.object_storage_public_endpoint_url.strip(),
            settings.object_storage_bucket.strip(),
            settings.object_storage_access_key_id,
            settings.object_storage_secret_access_key,
        )
    )
    scanner_configured = bool(settings.malware_scanner_host.strip())
    signing_configured = bool(settings.trip_evidence_signing_keys)
    checks = {
        "database": _component_state(
            bool(settings.database_url),
            lambda: _database_check(settings.database_url or "", allow_database_ahead=False),
        ),
        "redis": _component_state(
            bool(settings.redis_url), lambda: _broker_check(settings.redis_url or "")
        ),
        "worker": _component_state(
            bool(settings.redis_url), lambda: _worker_check(settings.redis_url or "")
        ),
        "storage": _component_state(
            storage_configured, lambda: _storage_check(write_canary=True, settings=settings)
        ),
        "scanner": _component_state(scanner_configured, lambda: _scanner_check(settings)),
        "trip_evidence_signing": _component_state(
            signing_configured, lambda: _signing_check(settings)
        ),
    }
    try:
        async with asyncio.timeout(OVERALL_TIMEOUT_SECONDS):
            values = await asyncio.gather(*checks.values())
    except TimeoutError:
        values = ["unavailable"] * len(checks)
    components = dict(zip(checks, values, strict=True))
    allowed = {"ok"}
    if settings.environment.lower() in LOCAL_ENVIRONMENTS:
        allowed.add("not_configured")
    return PublicReadiness(
        ready=all(state in allowed for state in components.values()), components=components
    )


class ReadinessCoordinator:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[PublicReadiness] | None = None
        self._cached: PublicReadiness | None = None
        self._expires_at = 0.0
        self._fingerprint: tuple[object, ...] | None = None

    async def get(self, settings: Settings) -> PublicReadiness:
        fingerprint = (
            settings.environment,
            settings.database_url,
            settings.redis_url,
            settings.object_storage_endpoint_url,
            settings.object_storage_bucket,
            settings.malware_scanner_host,
            settings.trip_evidence_signing_key_version,
            tuple(settings.trip_evidence_signing_keys),
        )
        now = time.monotonic()
        async with self._lock:
            if (
                self._cached is not None
                and self._fingerprint == fingerprint
                and now < self._expires_at
            ):
                return self._cached
            if self._task is None or self._task.done() or self._fingerprint != fingerprint:
                self._fingerprint = fingerprint
                self._task = asyncio.create_task(_run_component_checks(settings))
            task = self._task
        result = await asyncio.shield(task)
        async with self._lock:
            if task is self._task:
                self._cached = result
                self._expires_at = time.monotonic() + (
                    SUCCESS_CACHE_SECONDS if result.ready else FAILURE_CACHE_SECONDS
                )
                self._task = None
        return result


_public_readiness = ReadinessCoordinator()


async def public_readiness(settings: Settings) -> PublicReadiness:
    return await _public_readiness.get(settings)


async def run_probe(*, write_canary: bool, allow_database_ahead: bool) -> dict[str, object]:
    settings = get_settings()
    if not settings.database_url or not settings.redis_url:
        raise RuntimeError("database and broker must be configured")
    checks: dict[str, object] = {}
    checks["database"] = await _database_check(
        settings.database_url, allow_database_ahead=allow_database_ahead
    )
    checks["broker"] = await _broker_check(settings.redis_url)
    checks["storage"] = await _storage_check(write_canary=write_canary)
    checks["worker"] = await _worker_check(settings.redis_url)
    checks["scanner"] = await _scanner_check(settings)
    return {
        "event": "release_readiness",
        "status": "ready",
        "release_revision": settings.release_revision,
        "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-canary", action="store_true")
    parser.add_argument("--allow-database-ahead", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(
            run_probe(
                write_canary=args.write_canary,
                allow_database_ahead=args.allow_database_ahead,
            )
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "event": "release_readiness",
                    "status": "failed",
                    "reason": type(exc).__name__,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Layered operator readiness probe; it does not alter HTTP traffic readiness."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
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

from app.adapters.storage import build_storage_provider
from app.core.config import get_settings


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
        queue_depth = await redis.zcard("arq:queue")
    finally:
        await redis.aclose()
    return {"status": "ok", "queue_depth": int(queue_depth)}


async def _storage_check(*, write_canary: bool) -> dict[str, str]:
    if not write_canary:
        raise RuntimeError("storage readiness requires the private write/read/delete canary")
    settings = get_settings()
    storage = build_storage_provider(settings)
    canary_key = f"release-canary/{settings.release_revision}/{uuid4().hex}"
    payload = b"cardvert-private-storage-readiness-v1"
    digest = hashlib.sha256(payload).hexdigest()
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


def _worker_check() -> dict[str, str]:
    result = subprocess.run(
        ["arq", "--check", "app.jobs.worker_entry.WorkerSettings"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("worker health key is missing or stale")
    return {"status": "ok"}


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
    checks["worker"] = _worker_check()
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

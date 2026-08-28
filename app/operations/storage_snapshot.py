"""Stream and verify an immutable private-object snapshot against restored DB rows."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

import boto3
from botocore.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db.base  # noqa: F401  # import the complete model registry before model symbols
from app.core.config import get_settings
from app.models.stored_file import StoredFile


def _client():
    settings = get_settings()
    access_key = settings.object_storage_access_key_id
    secret_key = settings.object_storage_secret_access_key
    if access_key is None or secret_key is None:
        raise RuntimeError("private object storage credentials are not configured")
    return boto3.client(
        "s3",
        endpoint_url=settings.object_storage_endpoint_url,
        region_name=settings.object_storage_region,
        aws_access_key_id=access_key.get_secret_value(),
        aws_secret_access_key=secret_key.get_secret_value(),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


async def _database_inventory(database_url: str) -> list[dict[str, object]]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            rows = (
                await session.execute(
                    select(
                        StoredFile.id,
                        StoredFile.storage_key,
                        StoredFile.checksum_sha256,
                        StoredFile.size_bytes,
                        StoredFile.purpose,
                    ).order_by(StoredFile.storage_key)
                )
            ).all()
    finally:
        await engine.dispose()
    return [
        {
            "stored_file_id": str(row.id),
            "key": row.storage_key,
            "sha256": row.checksum_sha256,
            "bytes": row.size_bytes,
            "purpose": row.purpose,
        }
        for row in rows
    ]


def _tar_member(name: str, payload: bytes) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = 0o600
    info.mtime = 0
    return info


async def export_snapshot() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required")
    inventory = await _database_inventory(settings.database_url)
    client = _client()
    bucket = settings.object_storage_bucket
    output = sys.stdout.buffer
    with tarfile.open(fileobj=output, mode="w|") as archive:
        for index, item in enumerate(inventory):
            response = client.get_object(Bucket=bucket, Key=item["key"])
            version_id = str(response.get("VersionId") or "")
            if not version_id:
                raise RuntimeError("object storage versioning must be enabled for release backup")
            body = response["Body"]
            try:
                data = body.read()
            finally:
                body.close()
            if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise RuntimeError("private object bytes disagree with database authority")
            item["version_id"] = version_id
            archive.addfile(_tar_member(f"objects/{index:08d}", data), io.BytesIO(data))
        encoded = json.dumps(
            inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
        archive.addfile(_tar_member("inventory.json", encoded), io.BytesIO(encoded))


async def verify_snapshot(archive_path: Path, restore_prefix: str) -> None:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required")
    expected = await _database_inventory(settings.database_url)
    expected_by_key = {item["key"]: item for item in expected}
    client = _client()
    bucket = settings.object_storage_bucket
    restored_keys: list[str] = []
    try:
        with tarfile.open(archive_path, mode="r:") as archive:
            inventory_member = archive.getmember("inventory.json")
            source = archive.extractfile(inventory_member)
            if source is None:
                raise RuntimeError("object inventory is unreadable")
            inventory = json.load(source)
            if {item["key"] for item in inventory} != set(expected_by_key):
                raise RuntimeError("restored database and object inventory disagree")
            for index, item in enumerate(inventory):
                member = archive.getmember(f"objects/{index:08d}")
                object_source = archive.extractfile(member)
                if object_source is None:
                    raise RuntimeError("object snapshot member is unreadable")
                data = object_source.read()
                db_item = expected_by_key[item["key"]]
                if (
                    item["sha256"] != db_item["sha256"]
                    or item["bytes"] != db_item["bytes"]
                    or hashlib.sha256(data).hexdigest() != item["sha256"]
                    or len(data) != item["bytes"]
                ):
                    raise RuntimeError("restored object does not agree with database authority")
                restore_key = f"{restore_prefix.rstrip('/')}/{index:08d}"
                client.put_object(
                    Bucket=bucket,
                    Key=restore_key,
                    Body=data,
                    Metadata={"sha256": item["sha256"], "source-version": item["version_id"]},
                )
                restored_keys.append(restore_key)
                observed = client.get_object(Bucket=bucket, Key=restore_key)
                try:
                    restored = observed["Body"].read()
                finally:
                    observed["Body"].close()
                if hashlib.sha256(restored).hexdigest() != item["sha256"]:
                    raise RuntimeError("isolated object restore verification failed")
    finally:
        for key in restored_keys:
            client.delete_object(Bucket=bucket, Key=key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("export")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--archive", required=True)
    verify.add_argument("--restore-prefix", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            asyncio.run(export_snapshot())
        else:
            asyncio.run(verify_snapshot(Path(args.archive), args.restore_prefix))
    except Exception as exc:
        print(
            json.dumps(
                {"event": "storage_snapshot", "status": "failed", "reason": type(exc).__name__}
            ),
            file=sys.stderr,
        )
        return 1
    if args.command != "export":
        print('{"event":"storage_snapshot","status":"verified"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

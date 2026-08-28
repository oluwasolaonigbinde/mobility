from collections.abc import AsyncIterator

from app.adapters.storage.base import (
    ObjectMetadata,
    PresignedGet,
    PresignedPost,
    StorageError,
    StorageObjectConflict,
    StorageObjectNotFound,
    StorageProvider,
    StorageUnavailable,
)
from app.adapters.storage.s3 import S3StorageProvider
from app.core.config import Settings


class UnconfiguredStorageProvider:
    async def presign_post(self, **kwargs: object) -> PresignedPost:
        raise StorageUnavailable("Private object storage is not configured")

    async def stat(self, object_key: str) -> ObjectMetadata:
        raise StorageUnavailable("Private object storage is not configured")

    async def put(self, **kwargs: object) -> ObjectMetadata:
        raise StorageUnavailable("Private object storage is not configured")

    async def stream(self, object_key: str) -> AsyncIterator[bytes]:
        raise StorageUnavailable("Private object storage is not configured")
        yield b""  # pragma: no cover

    async def presign_get(self, *, object_key: str, expires_in_seconds: int) -> PresignedGet:
        raise StorageUnavailable("Private object storage is not configured")

    async def promote(self, *, source_key: str, destination_key: str) -> ObjectMetadata:
        raise StorageUnavailable("Private object storage is not configured")

    async def delete(self, object_key: str) -> None:
        raise StorageUnavailable("Private object storage is not configured")


def build_storage_provider(settings: Settings) -> StorageProvider:
    access_key = (
        settings.object_storage_access_key_id.get_secret_value().strip()
        if settings.object_storage_access_key_id is not None
        else ""
    )
    secret_key = (
        settings.object_storage_secret_access_key.get_secret_value().strip()
        if settings.object_storage_secret_access_key is not None
        else ""
    )
    strings = (
        settings.object_storage_endpoint_url,
        settings.object_storage_public_endpoint_url,
        settings.object_storage_bucket,
        access_key,
        secret_key,
    )
    if not all(value and value.strip() for value in strings):
        return UnconfiguredStorageProvider()
    return S3StorageProvider(
        endpoint_url=settings.object_storage_endpoint_url,
        public_endpoint_url=settings.object_storage_public_endpoint_url,
        region=settings.object_storage_region,
        bucket=settings.object_storage_bucket,
        access_key_id=access_key,
        secret_access_key=secret_key,
    )


__all__ = [
    "ObjectMetadata",
    "PresignedPost",
    "PresignedGet",
    "S3StorageProvider",
    "StorageError",
    "StorageObjectConflict",
    "StorageObjectNotFound",
    "StorageProvider",
    "StorageUnavailable",
    "UnconfiguredStorageProvider",
    "build_storage_provider",
]

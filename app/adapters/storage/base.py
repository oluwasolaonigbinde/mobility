from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class StorageError(RuntimeError):
    """Base storage failure without provider or credential detail."""


class StorageUnavailable(StorageError):
    """The private object store is unavailable or not configured."""


class StorageObjectNotFound(StorageError):
    """The requested private object does not exist."""


@dataclass(frozen=True, slots=True)
class PresignedPost:
    url: str
    fields: dict[str, str]


@dataclass(frozen=True, slots=True)
class PresignedGet:
    url: str
    expires_in_seconds: int


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    object_key: str
    size_bytes: int
    content_type: str
    checksum_sha256: str


@runtime_checkable
class StorageProvider(Protocol):
    async def presign_post(
        self,
        *,
        object_key: str,
        content_type: str,
        size_bytes: int,
        checksum_sha256: str,
        expires_in_seconds: int,
    ) -> PresignedPost: ...

    async def stat(self, object_key: str) -> ObjectMetadata: ...

    def stream(self, object_key: str) -> AsyncIterator[bytes]: ...

    async def presign_get(self, *, object_key: str, expires_in_seconds: int) -> PresignedGet: ...

    async def promote(self, *, source_key: str, destination_key: str) -> ObjectMetadata: ...

    async def delete(self, object_key: str) -> None: ...

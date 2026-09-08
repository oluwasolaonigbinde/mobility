from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class StorageError(RuntimeError):
    """Base storage failure without provider or credential detail."""


class StorageUnavailable(StorageError):
    """The private object store is unavailable or not configured."""


class StorageWriteUncertain(StorageUnavailable):
    """A write was issued but may still complete after its caller lost the response."""


class StorageObjectNotFound(StorageError):
    """The requested private object does not exist."""


class StorageObjectConflict(StorageError):
    """An immutable destination exists with different bytes or metadata."""


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

    async def put(
        self,
        *,
        object_key: str,
        content_type: str,
        data: bytes,
        checksum_sha256: str,
    ) -> ObjectMetadata:
        """One write call; raise StorageWriteUncertain if a request may still complete.

        Other handled storage errors guarantee no future write from this call.
        Adapters must disable untracked retries that could outlive a returned result.
        """
        ...

    def stream(self, object_key: str) -> AsyncIterator[bytes]: ...

    async def presign_get(self, *, object_key: str, expires_in_seconds: int) -> PresignedGet: ...

    async def promote(self, *, source_key: str, destination_key: str) -> ObjectMetadata:
        """Copy or adopt the destination; retain the source until lifecycle cleanup."""
        ...

    async def delete(self, object_key: str) -> None: ...

    async def delete_all_versions(self, object_key: str) -> None:
        """Delete and verify absence of every exact-key version and delete marker."""
        ...

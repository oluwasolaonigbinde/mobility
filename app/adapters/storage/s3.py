import asyncio
import base64
import hashlib
from typing import Any

from app.adapters.storage.base import (
    ObjectMetadata,
    PresignedPost,
    StorageObjectNotFound,
    StorageUnavailable,
)

READ_CHUNK_BYTES = 1024 * 1024


class S3StorageProvider:
    """S3-compatible private storage, including local MinIO."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        public_endpoint_url: str,
        region: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - packaging guard
            raise StorageUnavailable("Private object storage support is unavailable") from exc

        config = Config(signature_version="s3v4", s3={"addressing_style": "path"})
        common = {
            "service_name": "s3",
            "region_name": region,
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
            "config": config,
        }
        self._client = boto3.client(endpoint_url=endpoint_url, **common)
        self._public_client = boto3.client(endpoint_url=public_endpoint_url, **common)
        self._bucket = bucket

    async def presign_post(
        self,
        *,
        object_key: str,
        content_type: str,
        size_bytes: int,
        checksum_sha256: str,
        expires_in_seconds: int,
    ) -> PresignedPost:
        checksum_b64 = base64.b64encode(bytes.fromhex(checksum_sha256)).decode("ascii")
        fields = {
            "key": object_key,
            "Content-Type": content_type,
            "x-amz-meta-sha256": checksum_sha256,
            "x-amz-checksum-algorithm": "SHA256",
            "x-amz-checksum-sha256": checksum_b64,
        }
        conditions: list[dict[str, str] | list[str | int]] = [
            {"key": object_key},
            {"Content-Type": content_type},
            {"x-amz-meta-sha256": checksum_sha256},
            {"x-amz-checksum-algorithm": "SHA256"},
            {"x-amz-checksum-sha256": checksum_b64},
            ["content-length-range", size_bytes, size_bytes],
        ]
        try:
            response = await asyncio.to_thread(
                self._public_client.generate_presigned_post,
                Bucket=self._bucket,
                Key=object_key,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=expires_in_seconds,
            )
        except Exception as exc:
            raise StorageUnavailable("Private object storage is unavailable") from exc
        return PresignedPost(
            url=str(response["url"]),
            fields={str(key): str(value) for key, value in response["fields"].items()},
        )

    def _stat_sync(self, object_key: str) -> ObjectMetadata:
        try:
            response: dict[str, Any] = self._client.get_object(
                Bucket=self._bucket,
                Key=object_key,
            )
        except Exception as exc:
            self._raise_provider_error(exc, object_key)
        body = response["Body"]
        digest = hashlib.sha256()
        try:
            while chunk := body.read(READ_CHUNK_BYTES):
                digest.update(chunk)
        except Exception as exc:
            raise StorageUnavailable("Private object storage is unavailable") from exc
        finally:
            body.close()
        return ObjectMetadata(
            object_key=object_key,
            size_bytes=int(response["ContentLength"]),
            content_type=str(response.get("ContentType") or "application/octet-stream").lower(),
            checksum_sha256=digest.hexdigest(),
        )

    async def stat(self, object_key: str) -> ObjectMetadata:
        return await asyncio.to_thread(self._stat_sync, object_key)

    def _promote_sync(self, source_key: str, destination_key: str) -> ObjectMetadata:
        try:
            destination = self._stat_sync(destination_key)
        except StorageObjectNotFound:
            try:
                self._client.copy_object(
                    Bucket=self._bucket,
                    Key=destination_key,
                    CopySource={"Bucket": self._bucket, "Key": source_key},
                    MetadataDirective="COPY",
                    ChecksumAlgorithm="SHA256",
                )
                destination = self._stat_sync(destination_key)
            except StorageObjectNotFound:
                raise
            except Exception as exc:
                self._raise_provider_error(exc, source_key)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=source_key)
        except Exception as exc:
            raise StorageUnavailable("Private object storage is unavailable") from exc
        return destination

    async def promote(self, *, source_key: str, destination_key: str) -> ObjectMetadata:
        return await asyncio.to_thread(self._promote_sync, source_key, destination_key)

    async def delete(self, object_key: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.delete_object,
                Bucket=self._bucket,
                Key=object_key,
            )
        except Exception as exc:
            raise StorageUnavailable("Private object storage is unavailable") from exc

    @staticmethod
    def _raise_provider_error(exc: Exception, object_key: str) -> None:
        response = getattr(exc, "response", None)
        code = None
        if isinstance(response, dict):
            error = response.get("Error")
            if isinstance(error, dict):
                code = error.get("Code")
        if code in {"404", "NoSuchKey", "NotFound"}:
            raise StorageObjectNotFound(object_key) from None
        raise StorageUnavailable("Private object storage is unavailable") from exc

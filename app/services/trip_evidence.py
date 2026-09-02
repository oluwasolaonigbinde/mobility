import base64
import hashlib
import hmac
import math
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.trip import (
    LocationPingBatch,
    QuarantinedPingBatch,
    TripEvidenceManifestEntry,
    TripSession,
)
from app.schemas.trips import (
    LocationPingBatchCreate,
    TripEvidenceManifestCreate,
    TripEvidenceManifestEntryCreate,
)

BATCH_HASH_VERSION = 2
RECEIPT_FORMAT_VERSION = 2
MANIFEST_VERSION = 2
BATCH_DOMAIN = b"cardvert.trip-batch.v2\x00"
MANIFEST_ENTRY_DOMAIN = b"cardvert.trip-manifest-entry.v2\x00"
MANIFEST_DOMAIN = b"cardvert.trip-manifest.v2\x00"
BATCH_RECEIPT_DOMAIN = b"cardvert.trip-receipt.v2\x00"
MANIFEST_RECEIPT_DOMAIN = b"cardvert.trip-manifest-receipt.v2\x00"


@dataclass(frozen=True)
class SignedReceipt:
    format_version: int
    key_version: int
    signature: str
    outcome: str


@dataclass(frozen=True)
class ManifestCompleteness:
    complete: bool
    missing_count: int
    mismatch_count: int
    undeclared_count: int


def _u32(value: int) -> bytes:
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError("canonical u32 is out of range")
    return struct.pack(">I", value)


def canonical_bytes(value: Any) -> bytes:
    if value is None:
        return b"n"
    if value is False:
        return b"f"
    if value is True:
        return b"t"
    if isinstance(value, int):
        if value < -(2**63) or value > 2**63 - 1:
            raise ValueError("canonical i64 is out of range")
        return b"i" + value.to_bytes(8, "big", signed=True)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical floats must be finite")
        normalized = 0.0 if value == 0 else value
        return b"d" + struct.pack(">d", normalized)
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        return b"s" + _u32(len(encoded)) + encoded
    if isinstance(value, list):
        return b"a" + _u32(len(value)) + b"".join(canonical_bytes(item) for item in value)
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda item: item[0].encode("utf-8"))
        if any(not isinstance(key, str) for key, _ in items):
            raise ValueError("canonical object keys must be strings")
        return b"o" + _u32(len(items)) + b"".join(
            canonical_bytes(key) + canonical_bytes(item) for key, item in items
        )
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def epoch_milliseconds(value: datetime) -> int:
    if value.tzinfo is None:
        raise ValueError("canonical datetime must be timezone-aware")
    utc = value.astimezone(UTC)
    if utc.microsecond % 1000:
        raise ValueError("canonical datetime must have exact millisecond precision")
    return int(utc.timestamp()) * 1000 + utc.microsecond // 1000


def canonical_ping_payload(payload: LocationPingBatchCreate) -> dict[str, Any]:
    return {
        "pings": [
            {
                "recorded_at_ms": epoch_milliseconds(ping.recorded_at),
                "lat": ping.lat,
                "lon": ping.lon,
                "accuracy_m": ping.accuracy_m,
                "speed_mps": ping.speed_mps,
                "heading_degrees": ping.heading_degrees,
                "altitude_m": ping.altitude_m,
                "sequence_number": ping.sequence_number,
                "metadata": ping.metadata or {},
            }
            for ping in payload.pings
        ],
        "metadata": payload.metadata or {},
    }


def batch_payload_hash(payload: LocationPingBatchCreate) -> str:
    return hashlib.sha256(
        BATCH_DOMAIN + canonical_bytes(canonical_ping_payload(payload))
    ).hexdigest()


def manifest_entry_value(entry: TripEvidenceManifestEntryCreate) -> dict[str, Any]:
    return {
        "batch_sequence": entry.batch_sequence,
        "idempotency_key": entry.idempotency_key,
        "payload_hash_version": entry.payload_hash_version,
        "payload_hash": entry.payload_hash,
        "submitted_count": entry.submitted_count,
    }


def manifest_root(
    *,
    trip_id: UUID,
    entries: list[TripEvidenceManifestEntryCreate],
    ping_count: int,
) -> str:
    entry_digests = [
        hashlib.sha256(
            MANIFEST_ENTRY_DOMAIN + canonical_bytes(manifest_entry_value(entry))
        ).hexdigest()
        for entry in entries
    ]
    value = {
        "version": MANIFEST_VERSION,
        "trip_id": str(trip_id),
        "batch_count": len(entries),
        "ping_count": ping_count,
        "entry_digests": entry_digests,
    }
    return hashlib.sha256(MANIFEST_DOMAIN + canonical_bytes(value)).hexdigest()


def validate_manifest(trip_id: UUID, manifest: TripEvidenceManifestCreate) -> None:
    sequences = [entry.batch_sequence for entry in manifest.entries]
    keys = [entry.idempotency_key for entry in manifest.entries]
    if sequences != list(range(len(manifest.entries))):
        raise AppError(
            "TRIP_EVIDENCE_MANIFEST_INVALID",
            "Evidence manifest batch sequences must be ordered and contiguous",
            status_code=status.HTTP_409_CONFLICT,
        )
    if len(keys) != len(set(keys)):
        raise AppError(
            "TRIP_EVIDENCE_MANIFEST_INVALID",
            "Evidence manifest contains a duplicate idempotency key",
            status_code=status.HTTP_409_CONFLICT,
        )
    if sum(entry.submitted_count for entry in manifest.entries) != manifest.ping_count:
        raise AppError(
            "TRIP_EVIDENCE_MANIFEST_INVALID",
            "Evidence manifest ping count does not match its entries",
            status_code=status.HTTP_409_CONFLICT,
        )
    if manifest_root(
        trip_id=trip_id,
        entries=manifest.entries,
        ping_count=manifest.ping_count,
    ) != manifest.root_sha256:
        raise AppError(
            "TRIP_EVIDENCE_MANIFEST_INVALID",
            "Evidence manifest root does not match its content",
            status_code=status.HTTP_409_CONFLICT,
        )


def signing_key(settings: Settings, version: int | None = None) -> tuple[int, bytes]:
    selected = settings.trip_evidence_signing_key_version if version is None else version
    key = settings.trip_evidence_signing_keys.get(selected)
    if key is None:
        raise AppError(
            "TRIP_EVIDENCE_SIGNING_UNAVAILABLE",
            "Trip evidence signing is unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return selected, key


def _signature(domain: bytes, value: dict[str, Any], key: bytes) -> str:
    digest = hmac.new(key, domain + canonical_bytes(value), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify_signature(domain: bytes, value: dict[str, Any], key: bytes, signature: str) -> bool:
    return hmac.compare_digest(_signature(domain, value, key), signature)


def batch_receipt_value(batch: LocationPingBatch) -> dict[str, Any]:
    return {
        "format_version": RECEIPT_FORMAT_VERSION,
        "trip_id": str(batch.trip_session_id),
        "batch_sequence": batch.batch_sequence,
        "idempotency_key": batch.idempotency_key,
        "payload_hash_version": batch.payload_hash_version,
        "payload_hash": batch.payload_hash,
        "submitted_count": batch.pings_submitted,
        "accepted_count": batch.pings_accepted,
        "rejected_count": batch.pings_rejected,
        "outcome": batch.receipt_outcome,
        "evidence_scope": batch.evidence_scope,
    }


def sign_batch_receipt(batch: LocationPingBatch, settings: Settings) -> SignedReceipt:
    key_version, key = signing_key(settings)
    outcome = "accepted"
    batch.receipt_format_version = RECEIPT_FORMAT_VERSION
    batch.receipt_key_version = key_version
    batch.receipt_outcome = outcome
    batch.receipt_signature = _signature(BATCH_RECEIPT_DOMAIN, batch_receipt_value(batch), key)
    return SignedReceipt(RECEIPT_FORMAT_VERSION, key_version, batch.receipt_signature, outcome)


def sign_quarantine_receipt(
    batch: QuarantinedPingBatch, settings: Settings
) -> SignedReceipt:
    key_version, key = signing_key(settings)
    outcome = "quarantined"
    batch.receipt_format_version = RECEIPT_FORMAT_VERSION
    batch.receipt_key_version = key_version
    batch.receipt_outcome = outcome
    batch.receipt_signature = _signature(
        BATCH_RECEIPT_DOMAIN, quarantine_receipt_value(batch), key
    )
    return SignedReceipt(RECEIPT_FORMAT_VERSION, key_version, batch.receipt_signature, outcome)


def quarantine_receipt_value(batch: QuarantinedPingBatch) -> dict[str, Any]:
    return {
        "format_version": RECEIPT_FORMAT_VERSION,
        "trip_id": str(batch.trip_session_id),
        "batch_sequence": batch.batch_sequence,
        "idempotency_key": batch.idempotency_key,
        "payload_hash_version": batch.payload_hash_version,
        "payload_hash": batch.payload_hash,
        "submitted_count": batch.pings_submitted,
        "accepted_count": 0,
        "rejected_count": batch.pings_rejected,
        "outcome": batch.receipt_outcome,
        "evidence_scope": "quarantine",
    }


def verify_batch_receipt(batch: LocationPingBatch, settings: Settings) -> bool:
    if (
        batch.receipt_format_version != RECEIPT_FORMAT_VERSION
        or batch.receipt_key_version is None
        or batch.receipt_signature is None
    ):
        return False
    _, key = signing_key(settings, batch.receipt_key_version)
    return verify_signature(
        BATCH_RECEIPT_DOMAIN,
        batch_receipt_value(batch),
        key,
        batch.receipt_signature,
    )


def verify_quarantine_receipt(batch: QuarantinedPingBatch, settings: Settings) -> bool:
    if (
        batch.receipt_format_version != RECEIPT_FORMAT_VERSION
        or batch.receipt_key_version is None
        or batch.receipt_signature is None
    ):
        return False
    _, key = signing_key(settings, batch.receipt_key_version)
    return verify_signature(
        BATCH_RECEIPT_DOMAIN,
        quarantine_receipt_value(batch),
        key,
        batch.receipt_signature,
    )


def manifest_receipt_value(trip: TripSession) -> dict[str, Any]:
    verified_at = trip.evidence_manifest_verified_at
    if verified_at is None:
        raise ValueError("verified manifest receipt requires a verification timestamp")
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=UTC)
    return {
        "format_version": RECEIPT_FORMAT_VERSION,
        "trip_id": str(trip.id),
        "manifest_version": trip.evidence_manifest_version,
        "manifest_root_sha256": trip.evidence_manifest_root_sha256,
        "batch_count": trip.evidence_manifest_batch_count,
        "ping_count": trip.evidence_manifest_ping_count,
        "verified_at_ms": epoch_milliseconds(verified_at),
    }


def sign_manifest_receipt(trip: TripSession, settings: Settings) -> SignedReceipt:
    key_version, key = signing_key(settings)
    trip.evidence_manifest_receipt_format_version = RECEIPT_FORMAT_VERSION
    trip.evidence_manifest_receipt_key_version = key_version
    trip.evidence_manifest_receipt_signature = _signature(
        MANIFEST_RECEIPT_DOMAIN, manifest_receipt_value(trip), key
    )
    return SignedReceipt(
        RECEIPT_FORMAT_VERSION,
        key_version,
        trip.evidence_manifest_receipt_signature,
        "verified",
    )


def verify_manifest_receipt(trip: TripSession, settings: Settings) -> bool:
    if (
        trip.evidence_manifest_receipt_format_version != RECEIPT_FORMAT_VERSION
        or trip.evidence_manifest_receipt_key_version is None
        or trip.evidence_manifest_receipt_signature is None
        or trip.evidence_manifest_verified_at is None
    ):
        return False
    _, key = signing_key(settings, trip.evidence_manifest_receipt_key_version)
    return verify_signature(
        MANIFEST_RECEIPT_DOMAIN,
        manifest_receipt_value(trip),
        key,
        trip.evidence_manifest_receipt_signature,
    )


async def manifest_completeness(
    session: AsyncSession,
    trip: TripSession,
    settings: Settings,
) -> ManifestCompleteness:
    entries = list(
        (
            await session.execute(
                select(TripEvidenceManifestEntry)
                .where(TripEvidenceManifestEntry.trip_session_id == trip.id)
                .order_by(TripEvidenceManifestEntry.batch_sequence)
            )
        )
        .scalars()
        .all()
    )
    batches = list(
        (
            await session.execute(
                select(LocationPingBatch).where(
                    LocationPingBatch.trip_session_id == trip.id,
                    LocationPingBatch.evidence_scope == "manifest",
                )
            )
        )
        .scalars()
        .all()
    )
    by_key = {batch.idempotency_key: batch for batch in batches}
    declared = {entry.idempotency_key for entry in entries}
    missing = mismatch = 0
    for entry in entries:
        batch = by_key.get(entry.idempotency_key)
        if batch is None:
            missing += 1
            continue
        if (
            batch.batch_sequence != entry.batch_sequence
            or batch.payload_hash_version != entry.payload_hash_version
            or batch.payload_hash != entry.payload_hash
            or batch.pings_submitted != entry.submitted_count
            or not verify_batch_receipt(batch, settings)
        ):
            mismatch += 1
    undeclared = sum(batch.idempotency_key not in declared for batch in batches)
    complete = (
        len(entries) == (trip.evidence_manifest_batch_count or 0)
        and missing == 0
        and mismatch == 0
        and undeclared == 0
    )
    return ManifestCompleteness(complete, missing, mismatch, undeclared)

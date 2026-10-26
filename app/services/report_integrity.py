"""Canonical hashes for immutable report facts, independent of current formulas."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID


def _json_value(value):
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def canonical_sha256(value):
    return hashlib.sha256(
        json.dumps(
            _json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def frozen_measurement_is_intact(run):
    """Historical manifests stay checkable after the write workflow is retired."""
    return all(
        canonical_sha256(getattr(run, field)) == getattr(run, field + "_sha256")
        for field in ("input_manifest", "result_manifest", "proof_manifest", "report_snapshot")
    )

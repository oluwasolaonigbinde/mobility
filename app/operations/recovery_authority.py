"""Host-issued operator authority. Never consulted by public HTTP readiness."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

CAPABILITY = "signed-forward-schema-v1"
QUALIFICATION_LIFETIME = timedelta(minutes=30)


def authority_signature(authority: dict[str, Any], secret: str) -> str:
    payload = {key: value for key, value in authority.items() if key != "signature"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(secret.encode(), encoded, hashlib.sha256).hexdigest()


def validate_authority(
    authority: dict[str, Any],
    *,
    secret: str,
    scope: str,
    release_id: str,
    revision: str,
    image: str,
    code_head: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    fields = {
        "capability",
        "scope",
        "previous_release_id",
        "previous_revision",
        "previous_backend_image",
        "previous_alembic_revision",
        "target_release_id",
        "target_revision",
        "target_backend_image",
        "forward_alembic_revision",
        "accepted_receipt_sha256",
        "issued_at",
        "expires_at",
        "key_id",
        "signature",
    }
    if not isinstance(authority, dict) or set(authority) != fields or len(secret) < 32:
        raise ValueError("invalid operator authority")
    if not hmac.compare_digest(str(authority["signature"]), authority_signature(authority, secret)):
        raise ValueError("invalid operator signature")
    expected = {
        "capability": CAPABILITY,
        "scope": scope,
        "previous_release_id": release_id,
        "previous_revision": revision,
        "previous_backend_image": image,
        "previous_alembic_revision": code_head,
    }
    if scope not in {"qualification", "recovery"} or any(
        not value or authority[key] != value for key, value in expected.items()
    ):
        raise ValueError("operator scope or image identity mismatch")
    if (
        not re.fullmatch(r"[a-zA-Z0-9_]+", authority["forward_alembic_revision"])
        or authority["target_backend_image"] == image
        or authority["target_revision"] == revision
    ):
        raise ValueError("operator authority requires distinct exact images")
    issued_at = datetime.fromisoformat(authority["issued_at"])
    observed = now or datetime.now(UTC)
    if issued_at.tzinfo is None or issued_at > observed:
        raise ValueError("invalid operator issue time")
    if scope == "qualification":
        expires_at = datetime.fromisoformat(authority["expires_at"])
        if (
            expires_at.tzinfo is None
            or expires_at <= observed
            or not timedelta(0) < expires_at - issued_at <= QUALIFICATION_LIFETIME
            or authority["accepted_receipt_sha256"] is not None
        ):
            raise ValueError("invalid or expired qualification authority")
    elif authority["expires_at"] is not None or not re.fullmatch(
        r"[0-9a-f]{64}", str(authority["accepted_receipt_sha256"])
    ):
        raise ValueError("recovery requires accepted receipt authority")
    return authority

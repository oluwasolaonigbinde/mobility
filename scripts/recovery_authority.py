#!/usr/bin/env python3
"""Issue a private Compose overlay after exact-image compatibility authorization."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.operations.recovery_authority import (  # noqa: E402
    CAPABILITY,
    QUALIFICATION_LIFETIME,
    authority_signature,
    validate_authority,
)
from scripts.release_contract import (  # noqa: E402
    ContractError,
    _read_private_json,
    _validate_image,
    _write_private_json,
    compatibility_receipt_sha256,
    read_env_file,
    validate_compatibility_evidence,
    validate_release_evidence_configuration,
)


def image_command(image: str, revision: str, command: list[str]) -> str:
    _validate_image("backend image", image, allow_local_rehearsal=True)
    label = subprocess.check_output(
        [
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            '{{index .Config.Labels "org.opencontainers.image.revision"}}',
        ],
        text=True,
    ).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or label != revision:
        raise ContractError("Image revision differs from the exact source authority")
    return subprocess.check_output(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--network",
            "none",
            "--entrypoint",
            command[0],
            image,
            *command[1:],
        ],
        text=True,
    ).strip()


def image_head(image: str, revision: str) -> str:
    output = image_command(image, revision, ["alembic", "heads"])
    lines = output.splitlines()
    if len(lines) != 1 or not re.fullmatch(r"[a-zA-Z0-9_]+ \(head\)", lines[0]):
        raise ContractError("Image must have exactly one authoritative migration head")
    return lines[0].split()[0]


def build_overlay(
    *,
    current: dict,
    previous: dict,
    capability: dict,
    forward: str,
    scope: str,
    evidence: dict | None = None,
    state: dict | None = None,
    now: datetime | None = None,
) -> dict:
    secret, key_id = validate_release_evidence_configuration(current)
    if set(capability) != {"capability", "alembic_revision"} or (
        capability["capability"] != CAPABILITY
        or not re.fullmatch(r"[a-zA-Z0-9_]+", capability["alembic_revision"])
    ):
        raise ContractError("Previous image lacks the required recovery capability")
    identities = {
        "target_release_id": current["RELEASE_ID"],
        "target_revision": current["RELEASE_REVISION"],
        "target_backend_image": current["BACKEND_IMAGE"],
        "previous_release_id": previous["RELEASE_ID"],
        "previous_revision": previous["RELEASE_REVISION"],
        "previous_backend_image": previous["BACKEND_IMAGE"],
        "forward_alembic_revision": forward,
    }
    if current.get("PREVIOUS_RELEASE_ID") != previous["RELEASE_ID"]:
        raise ContractError("Previous release is not the declared predecessor")
    accepted_digest = None
    observed = now or datetime.now(UTC)
    if scope == "recovery":
        if state is None or evidence is None:
            raise ContractError("Recovery requires the accepted release state and receipt")
        for name in ("release_id", "revision", "backend_image", "previous_release_id"):
            expected = (
                identities["target_" + name]
                if name != "previous_release_id"
                else (identities[name])
            )
            if state.get(name) != expected:
                raise ContractError("Recovery state identity mismatch")
        outcomes = [
            event.get("outcome", "")
            for event in state["events"]
            if event["stage"] == "compatibility"
        ]
        if "migration" not in state["stages"] or len(outcomes) != 1:
            raise ContractError("Recovery lacks accepted compatibility authority")
        parts = outcomes[0].split(":")
        if len(parts) != 3 or parts[0] != "passed":
            raise ContractError("Recovery lacks accepted compatibility authority")
        validate_compatibility_evidence(
            evidence,
            **identities,
            signing_secret=secret,
            key_id=key_id,
            now=observed,
            accepted_receipt_sha256=parts[1],
            accepted_receipt_hmac=parts[2],
        )
        accepted_digest = compatibility_receipt_sha256(evidence)
    elif scope != "qualification" or evidence is not None or state is not None:
        raise ContractError("Invalid qualification authority")
    authority = {
        "capability": CAPABILITY,
        "scope": scope,
        **identities,
        "previous_alembic_revision": capability["alembic_revision"],
        "accepted_receipt_sha256": accepted_digest,
        "issued_at": observed.isoformat(),
        "expires_at": (observed + QUALIFICATION_LIFETIME).isoformat()
        if scope == "qualification"
        else None,
        "key_id": key_id,
    }
    authority["signature"] = authority_signature(authority, secret)
    validate_authority(
        authority,
        secret=secret,
        scope=scope,
        release_id=previous["RELEASE_ID"],
        revision=previous["RELEASE_REVISION"],
        image=previous["BACKEND_IMAGE"],
        code_head=capability["alembic_revision"],
        now=observed,
    )
    api = {
        "environment": {
            "RELEASE_ID": previous["RELEASE_ID"],
            "RELEASE_COMPATIBILITY_IMAGE": previous["BACKEND_IMAGE"],
            "RELEASE_COMPATIBILITY_AUTHORITY": json.dumps(authority, sort_keys=True),
            "RELEASE_COMPATIBILITY_KEY": secret,
        }
    }
    if scope == "recovery":
        api["healthcheck"] = {
            "test": [
                "CMD",
                "python",
                "-m",
                "app.operations.readiness",
                "--write-canary",
                "--compatibility",
                "recovery",
            ],
            "timeout": "45s",
        }
    # Compose interpolates even JSON/YAML string values, including secrets.
    api["environment"] = {
        key: value.replace("$", "$$") for key, value in api["environment"].items()
    }
    return {"services": {"api": api}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-head", action="store_true")
    parser.add_argument("--image")
    parser.add_argument("--revision")
    parser.add_argument("--scope", choices=("qualification", "recovery"))
    parser.add_argument("--current-env-file")
    parser.add_argument("--previous-env-file")
    parser.add_argument("--forward-alembic-revision")
    parser.add_argument("--evidence")
    parser.add_argument("--state")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.image_head:
        print(image_head(args.image, args.revision))
        return 0
    output = Path(args.output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ContractError("Recovery authority must stay outside the repository")
    current = read_env_file(Path(args.current_env_file))
    previous = read_env_file(Path(args.previous_env_file))
    forward = image_head(current["BACKEND_IMAGE"], current["RELEASE_REVISION"])
    if args.forward_alembic_revision != forward:
        raise ContractError("Database does not match the exact target image head")
    capability = json.loads(
        image_command(
            previous["BACKEND_IMAGE"],
            previous["RELEASE_REVISION"],
            ["python", "-m", "app.operations.readiness", "--capability"],
        )
    )
    overlay = build_overlay(
        current=current,
        previous=previous,
        capability=capability,
        forward=forward,
        scope=args.scope,
        evidence=_read_private_json(Path(args.evidence), label="Compatibility receipt")
        if args.evidence
        else None,
        state=_read_private_json(Path(args.state), label="Release state") if args.state else None,
    )
    _write_private_json(output, overlay)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContractError, ValueError, KeyError, OSError, subprocess.CalledProcessError):
        # Never print configuration, signed tokens or provider details on failure.
        print("ERROR: signed previous-image operator authority failed", file=sys.stderr)
        raise SystemExit(2) from None

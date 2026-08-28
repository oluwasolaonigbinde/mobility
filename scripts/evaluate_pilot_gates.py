#!/usr/bin/env python3
"""Evaluate the six Cardvert live-use gates without performing live actions."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

if __package__:
    from .validate_progress import (
        _authoritative_view,
        _plain,
        _section,
        _table,
        validate_text,
    )
else:
    from validate_progress import (  # type: ignore[no-redef]
        _authoritative_view,
        _plain,
        _section,
        _table,
        validate_text,
    )


AUTHORITY_PATHS = (
    "docs/progress.md",
    "docs/architecture.md",
    "docs/decisions-log.md",
)


class AuthorityError(RuntimeError):
    """Committed gate authority is malformed, incomplete, or untrusted."""


class ContradictionError(RuntimeError):
    """Committed and runtime gate claims disagree."""


@dataclass(frozen=True, slots=True)
class TrustedEvidence:
    evidence: str
    document: str
    identifiers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Gate:
    name: str
    checklists: tuple[str, ...]
    evidence: tuple[str, ...]
    required_inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuthoritySnapshot:
    checklist_states: Mapping[str, str]
    external_states: Mapping[str, str]
    deferred_states: Mapping[str, str]
    architecture_gates: tuple[str, ...]


TRUSTED_PRESENT_EVIDENCE: Mapping[str, TrustedEvidence] = {
    "EXT-RM2-POLICY": TrustedEvidence(
        evidence="docs/decisions-log.md D22; reviewed synthetic Option A",
        document="docs/decisions-log.md",
        identifiers=("D22",),
    ),
    "EXT-PILOT-FACTS": TrustedEvidence(
        evidence="docs/decisions-log.md D18/D20, Q30/Q33",
        document="docs/decisions-log.md",
        identifiers=("D18", "D20", "Q30", "Q33"),
    ),
}


GATES = (
    Gate(
        name="G-money",
        checklists=("MNY-06C", "MNY-03A", "MNY-10C", "MNY-11A"),
        evidence=("RM1", "RM6", "RM8", "RM10", "RM11", "D18"),
        required_inputs=("EXT-DISBURSEMENT-PROVIDER", "EXT-SETTLEMENT-BANK"),
    ),
    Gate(
        name="G-GPS",
        checklists=("FND-02B", "MNY-09A", "W2-02E", "W2-03G", "W3-00C", "W4-01D"),
        evidence=("RM2", "RM3", "RM4", "RM5", "RM9", "RM15", "RM18", "D18", "D23"),
        required_inputs=(
            "EXT-RM2-POLICY",
            "EXT-STORAGE-PROVIDER",
            "EXT-MALWARE-SCANNER",
            "EXT-KMS-CUSTODY",
            "EXT-PHONE-OPERATOR",
            "EXT-EVIDENCE-POLICY",
            "EXT-LEGAL-PRIVACY",
            "EXT-UPLOAD-POLICY",
            "DV-PWA-PHYSICAL-MATRIX",
            "DV-PWA-ROUTE-BATTERY",
        ),
    ),
    Gate(
        name="G-commercial",
        checklists=(
            "W2-00C",
            "W2-01C",
            "W2-01E",
            "W2-03D",
            "W2-03F",
            "W2-03G",
        ),
        evidence=("RM12", "RM13", "D18", "D20"),
        required_inputs=(
            "EXT-PAYMENT-PROVIDER",
            "EXT-STORAGE-PROVIDER",
            "EXT-MALWARE-SCANNER",
            "EXT-BUDGET-POLICY",
            "EXT-Q28-COMPANY",
            "EXT-COMMERCIAL-VALUES",
            "EXT-EVIDENCE-POLICY",
            "EXT-CAMPAIGN-BUDGET-SCOPE",
            "EXT-UPLOAD-POLICY",
        ),
    ),
    Gate(
        name="G-advertiser",
        checklists=("W3-00C", "W3-00E", "W3-02B", "W4-02B"),
        evidence=("RM15", "RM16", "D20"),
        required_inputs=("EXT-BASEMAP", "EXT-REPORT-METHOD", "EXT-LEGAL-PRIVACY"),
    ),
    Gate(
        name="G-moduleG",
        checklists=("W3-00C", "W3-00E", "W3-01D"),
        evidence=("RM15", "RM16", "D18", "D20"),
        required_inputs=("EXT-REPORT-METHOD", "EXT-LEGAL-PRIVACY", "EXT-AD-PLATFORM"),
    ),
    Gate(
        name="G-pilot",
        checklists=("R17-A", "W4-01D", "W4-02B", "W4-03A"),
        evidence=(
            "G-money",
            "G-GPS",
            "G-commercial",
            "G-advertiser",
            "G-moduleG",
            "RM17",
            "D18",
            "D19",
            "D20",
            "D23",
        ),
        required_inputs=(
            "EXT-DISBURSEMENT-PROVIDER",
            "EXT-SETTLEMENT-BANK",
            "EXT-RM2-POLICY",
            "EXT-STORAGE-PROVIDER",
            "EXT-MALWARE-SCANNER",
            "EXT-KMS-CUSTODY",
            "EXT-PHONE-OPERATOR",
            "EXT-EVIDENCE-POLICY",
            "EXT-LEGAL-PRIVACY",
            "EXT-UPLOAD-POLICY",
            "EXT-PAYMENT-PROVIDER",
            "EXT-BUDGET-POLICY",
            "EXT-Q28-COMPANY",
            "EXT-COMMERCIAL-VALUES",
            "EXT-CAMPAIGN-BUDGET-SCOPE",
            "EXT-BASEMAP",
            "EXT-REPORT-METHOD",
            "EXT-AD-PLATFORM",
            "EXT-RELEASE-ENV",
            "EXT-STAGING-APPROVAL",
            "EXT-PILOT-FACTS",
            "EXT-PILOT-PERMITS",
            "DV-PWA-PHYSICAL-MATRIX",
            "DV-PWA-ROUTE-BATTERY",
            "DV-STAGING-LIVE",
        ),
    ),
)


CONTROLLED_CHECKLISTS: Mapping[str, tuple[str, ...]] = {
    "W2-01C": ("EXT-PAYMENT-PROVIDER",),
    "W4-03A": ("EXT-RELEASE-ENV", "DV-STAGING-LIVE"),
}


BOOLEAN_RUNTIME_CLAIMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PRIVACY_DISCLOSURE_LIVE_AUTHORIZED", ("EXT-LEGAL-PRIVACY",)),
    (
        "MEASUREMENT_LIVE_ISSUANCE_AUTHORIZED",
        ("EXT-REPORT-METHOD", "EXT-LEGAL-PRIVACY"),
    ),
    ("BUDGET_POLICY_EXTERNAL_APPROVED", ("EXT-BUDGET-POLICY",)),
    ("PHONE_OPERATOR_EXTERNAL_APPROVED", ("EXT-PHONE-OPERATOR",)),
)

REFERENCE_RUNTIME_CLAIMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("INVOICE_ISSUER_EXTERNAL_INPUT_REFERENCE", ("EXT-Q28-COMPANY",)),
)

GROUP_RUNTIME_CLAIMS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        (
            "INSTALLATION_EVIDENCE_UPLOADER_ROLES",
            "INSTALLATION_EVIDENCE_REQUIRED_VIEWS",
            "INSTALLATION_EVIDENCE_VALIDITY_HOURS",
            "DISPLAY_PROOF_CHALLENGE_TTL_SECONDS",
            "DISPLAY_PROOF_VALIDITY_SECONDS",
        ),
        ("EXT-EVIDENCE-POLICY",),
    ),
    (
        (
            "EVIDENCE_HIGH_EARNER_THRESHOLD_NGN",
            "EVIDENCE_RENEWAL_LOOKBACK_DAYS",
            "EVIDENCE_CHALLENGE_RESPONSE_HOURS",
        ),
        ("EXT-EVIDENCE-POLICY",),
    ),
)


def _rows(
    progress: str, heading: str, next_heading: str, header: str
) -> list[tuple[int, list[str]]]:
    errors: list[str] = []
    authoritative = _authoritative_view(progress, errors)
    if errors:
        raise AuthorityError(errors[0])
    try:
        section, line = _section(authoritative, heading, next_heading)
        return _table(section, header, line)
    except ValueError as exc:
        raise AuthorityError(str(exc)) from exc


def _authority_identifiers(document: str, identifiers: tuple[str, ...], external_id: str) -> None:
    for identifier in identifiers:
        count = len(
            re.findall(
                rf"^\| (?:\*\*)?{re.escape(identifier)}(?:\*\*)?(?: [^|]*)? \|",
                document,
                re.MULTILINE,
            )
        )
        if count != 1:
            raise AuthorityError(
                f"untrusted committed evidence for {external_id}: authority identifier count"
            )


def _architecture_gate_names(architecture: str) -> tuple[str, ...]:
    match = re.search(
        r"^### 35\.3 Live-use and dependent-action gates\s*$([\s\S]*?)^## 34\.",
        architecture,
        re.MULTILINE,
    )
    if match is None:
        raise AuthorityError("architecture §35.3 gate table is missing")
    names = tuple(
        re.findall(r"^\| \*\*(G-[A-Za-z0-9-]+)\*\* \|", match.group(1), re.MULTILINE)
    )
    expected = tuple(gate.name for gate in GATES)
    if names != expected or len(names) != len(set(names)):
        raise AuthorityError("architecture §35.3 gate identities/order contradict the evaluator")
    return names


def _validate_evidence_manifest(architecture: str, decisions: str) -> None:
    gate_names = {gate.name for gate in GATES}
    for gate in GATES:
        for identifier in gate.evidence:
            if identifier in gate_names:
                continue
            document = architecture if identifier.startswith("RM") else decisions
            _authority_identifiers(document, (identifier,), gate.name)


def parse_authority(
    progress: str,
    architecture: str,
    decisions: str,
    *,
    trusted_evidence: Mapping[str, TrustedEvidence] = TRUSTED_PRESENT_EVIDENCE,
) -> AuthoritySnapshot:
    validation_errors = validate_text(progress)
    if validation_errors:
        raise AuthorityError(f"delivery-control validation failed: {validation_errors[0]}")

    checklist_states: dict[str, str] = {}
    for _line, cells in _rows(
        progress,
        "## Mandatory checklist item register",
        "## Checklist item specifications",
        "| # | Checklist item |",
    ):
        match = re.match(r"\*\*([A-Z0-9-]+) —", cells[1])
        if match is not None:
            checklist_states[match.group(1)] = _plain(cells[3])

    external_rows = _rows(
        progress,
        "## External prerequisite register",
        "## Canonical repository",
        "| ID | State |",
    )
    external_states: dict[str, str] = {}
    external_evidence: dict[str, str] = {}
    for _line, cells in external_rows:
        external_id = _plain(cells[0])
        external_states[external_id] = _plain(cells[1])
        external_evidence[external_id] = _plain(cells[3])

    deferred_states: dict[str, str] = {}
    for _line, cells in _rows(
        progress,
        "## External prerequisite register",
        "## Canonical repository",
        "| Validation | State |",
    ):
        deferred_states[_plain(cells[0])] = _plain(cells[1])

    required_external = {
        item
        for gate in GATES
        for item in gate.required_inputs
        if item.startswith("EXT-")
    }
    documents = {
        "docs/progress.md": progress,
        "docs/architecture.md": architecture,
        "docs/decisions-log.md": decisions,
    }
    for external_id in required_external:
        if external_states.get(external_id) != "PRESENT":
            continue
        rule = trusted_evidence.get(external_id)
        if rule is None or external_evidence.get(external_id) != rule.evidence:
            raise AuthorityError(f"untrusted committed evidence for {external_id}")
        document = documents.get(rule.document)
        if document is None:
            raise AuthorityError(f"untrusted committed evidence document for {external_id}")
        _authority_identifiers(document, rule.identifiers, external_id)

    architecture_gates = _architecture_gate_names(architecture)
    _validate_evidence_manifest(architecture, decisions)
    return AuthoritySnapshot(
        checklist_states=checklist_states,
        external_states=external_states,
        deferred_states=deferred_states,
        architecture_gates=architecture_gates,
    )


def _runtime_claims(runtime: Mapping[str, str]) -> set[str]:
    claimed: set[str] = set()
    for name, external_ids in BOOLEAN_RUNTIME_CLAIMS:
        value = runtime.get(name, "").strip().lower()
        if value not in {"", "true", "false", "0", "1"}:
            gate = next(gate for gate in GATES if external_ids[0] in gate.required_inputs)
            raise AuthorityError(f"malformed runtime claim for {gate.name} / {external_ids[0]}")
        if value in {"true", "1"}:
            claimed.update(external_ids)
    for name, external_ids in REFERENCE_RUNTIME_CLAIMS:
        if runtime.get(name, "").strip():
            claimed.update(external_ids)
    for names, external_ids in GROUP_RUNTIME_CLAIMS:
        if all(runtime.get(name, "").strip() for name in names):
            claimed.update(external_ids)
    return claimed


def _input_complete(snapshot: AuthoritySnapshot, input_id: str) -> bool:
    if input_id.startswith("EXT-"):
        return snapshot.external_states.get(input_id) == "PRESENT"
    return snapshot.deferred_states.get(input_id) == "COMPLETE"


def evaluate_gates(
    snapshot: AuthoritySnapshot, runtime: Mapping[str, str]
) -> tuple[str, ...]:
    claims = _runtime_claims(runtime)
    lines: list[str] = []
    for gate in GATES:
        blockers = tuple(
            input_id
            for input_id in gate.required_inputs
            if not _input_complete(snapshot, input_id)
        )
        for input_id in gate.required_inputs:
            if input_id in claims and snapshot.external_states.get(input_id) == "MISSING":
                raise ContradictionError(
                    f"runtime contradiction for {gate.name} / {input_id}"
                )
        for checklist in gate.checklists:
            if snapshot.checklist_states.get(checklist) == "DONE":
                continue
            controlled_by = CONTROLLED_CHECKLISTS.get(checklist, ())
            if controlled_by and any(input_id in blockers for input_id in controlled_by):
                continue
            raise ContradictionError(
                f"checklist contradiction for {gate.name} / {checklist}"
            )
        if blockers:
            lines.append(f"{gate.name}: BLOCKED — {', '.join(blockers)}")
        else:
            lines.append(f"{gate.name}: PASS")
    return tuple(lines)


def _load_head_authority(
    runner: Callable[..., Any],
) -> tuple[str, str, str]:
    snapshots: list[str] = []
    for path in AUTHORITY_PATHS:
        result = runner(
            ["git", "show", f"HEAD:{path}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AuthorityError(f"committed authority unavailable: {path}")
        snapshots.append(result.stdout)
    return snapshots[0], snapshots[1], snapshots[2]


def _runtime_snapshot(environment: Mapping[str, str]) -> dict[str, str]:
    names = {
        name for name, _external_ids in BOOLEAN_RUNTIME_CLAIMS + REFERENCE_RUNTIME_CLAIMS
    }
    names.update(name for group, _external_ids in GROUP_RUNTIME_CLAIMS for name in group)
    return {name: environment.get(name, "") for name in names}


def main(
    *,
    environment: Mapping[str, str] | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> int:
    try:
        progress, architecture, decisions = _load_head_authority(runner)
        snapshot = parse_authority(progress, architecture, decisions)
        runtime = _runtime_snapshot(dict(os.environ) if environment is None else dict(environment))
        lines = evaluate_gates(snapshot, runtime)
    except (AuthorityError, ContradictionError) as exc:
        print(f"pilot-gate evaluation failed: {exc}", file=sys.stderr)
        return 2
    for line in lines:
        print(line)
    return 1 if any("BLOCKED" in line for line in lines) else 0


if __name__ == "__main__":
    raise SystemExit(main())

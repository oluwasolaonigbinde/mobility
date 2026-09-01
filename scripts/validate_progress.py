#!/usr/bin/env python3
"""Validate the package queue and mandatory checklist in docs/progress.md."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROGRESS = ROOT / "docs" / "progress.md"
ACTIVE_PACKAGE_STATUSES = {"NEXT", "IN PROGRESS", "REVIEW"}
PACKAGE_STATUSES = ACTIVE_PACKAGE_STATUSES | {"QUEUED", "DONE", "BLOCKED"}
CHECKLIST_STATUSES = {"TODO", "DONE"}
REMEDIATION_SLICE_STATUSES = {"QUEUED", "ACTIVE", "COMPLETE"}

# This manifest is the review boundary for delivery-control changes. Changing an
# item identity, package or dependency requires an explicit validator diff; a
# tidy-up of docs/progress.md cannot silently weaken the delivery contract.
CANONICAL_ITEMS = (
    ("R14-A", "PKG-01", "none"),
    ("R14-B", "PKG-01", "leaf: R14-A"),
    ("R17-A", "PKG-01", "none"),
    ("FND-02A", "PKG-01", "none"),
    ("FND-02B", "PKG-01", "leaf: FND-02A; external: EXT-RM2-POLICY"),
    ("FND-07", "PKG-01", "none"),
    ("MNY-06A", "PKG-01", "none"),
    ("MNY-06B", "PKG-01", "leaf: MNY-06A"),
    ("MNY-06C", "PKG-01", "leaf: MNY-06B"),
    ("MNY-08A", "PKG-02", "none"),
    ("MNY-09A", "PKG-02", "leaf: MNY-08A"),
    ("MNY-08B", "PKG-02", "leaf: MNY-08A, MNY-09A"),
    ("MNY-08C", "PKG-02", "leaf: MNY-08B"),
    ("MNY-03A", "PKG-02", "leaf: MNY-08B"),
    ("MNY-10A", "PKG-02", "none"),
    ("MNY-10B", "PKG-02", "leaf: MNY-10A"),
    ("MNY-10C", "PKG-02", "leaf: MNY-10B"),
    ("MNY-11A", "PKG-02", "leaf: MNY-10C, MNY-06C"),
    ("W2-00A", "PKG-03", "leaf: MNY-11A"),
    ("W2-00D", "PKG-03", "none"),
    ("W2-00B", "PKG-03", "leaf: W2-00A"),
    ("W2-01A", "PKG-03", "leaf: W2-00A, W2-00D"),
    ("W2-01B", "PKG-03", "leaf: W2-00B, W2-01A"),
    ("W2-00C", "PKG-03", "leaf: W2-01B, MNY-11A"),
    ("W2-01C", "PKG-03", "leaf: W2-00B, W2-01A; external: EXT-PAYMENT-PROVIDER"),
    ("W2-01D", "PKG-03", "leaf: W2-01A, W2-01B"),
    ("W2-01E", "PKG-03", "leaf: W2-01A, W2-01B"),
    ("W2-02A", "PKG-04", "none"),
    ("W2-02B", "PKG-04", "leaf: W2-02A"),
    ("W2-02C", "PKG-04", "leaf: W2-02B"),
    ("W2-02D", "PKG-04", "leaf: W2-02B, MNY-10A"),
    ("W2-02E", "PKG-04", "leaf: W2-02B, W2-02D"),
    ("W2-03A", "PKG-04", "none"),
    ("W2-03B", "PKG-04", "leaf: W2-02C"),
    ("W2-03C", "PKG-04", "leaf: W2-02B"),
    ("W2-03D", "PKG-04", "leaf: W2-00C, W2-01A, W2-01B, W2-03A, W2-03B, W2-03C"),
    ("W2-03E", "PKG-04", "leaf: W2-00A, W2-00C, W2-03D"),
    ("W2-03F", "PKG-04", "leaf: W2-01D, W2-03D, MNY-11A"),
    ("W2-03G", "PKG-04", "leaf: MNY-09A, W2-03C, W2-03D"),
    ("W2-04A", "PKG-04", "leaf: MNY-08C"),
    ("W2-04B", "PKG-04", "leaf: W2-04A"),
    ("W2-04C", "PKG-04", "leaf: W2-04A, W2-04B, W2-01E, W2-03F, W2-03G, MNY-10C"),
    ("W2-04D", "PKG-04", "leaf: W2-04B, W2-04C"),
    ("W3-00A", "PKG-05", "none"),
    ("W3-00B", "PKG-05", "leaf: W3-00A, W2-02E"),
    ("W3-00C", "PKG-05", "leaf: W3-00A"),
    ("W3-00D", "PKG-05", "none"),
    ("W3-00E", "PKG-05", "leaf: W3-00D, W2-03C, W2-03D"),
    ("W3-01A", "PKG-05", "leaf: W3-00A, W3-00D"),
    ("W3-01B", "PKG-05", "leaf: W3-01A"),
    ("W3-01C", "PKG-05", "leaf: W3-00C, W3-00D, W3-00E, W3-01B"),
    ("W3-01D", "PKG-05", "leaf: W3-01C, W3-00D, W3-00E"),
    ("W3-02A", "PKG-05", "leaf: W3-00D, W3-00E"),
    ("W3-02B", "PKG-05", "leaf: W3-00C, W3-00E"),
    ("W3-03A", "PKG-06", "none"),
    ("W3-03B", "PKG-06", "leaf: W3-03A, W2-00A, MNY-06B"),
    ("W3-03C", "PKG-06", "leaf: W3-03B, W2-04A"),
    ("W3-04A", "PKG-06", "none"),
    ("W3-04B", "PKG-06", "leaf: W3-04A, W2-02D, MNY-10A"),
    ("W3-04C", "PKG-06", "leaf: W3-04B, W2-02B, W2-02D"),
    (
        "W4-01A",
        "PKG-07",
        "leaf: R14-A, R14-B; external: EXT-PKG07-OWNER-RELEASE",
    ),
    ("W4-01B", "PKG-07", "leaf: W4-01A, R14-B"),
    ("W4-01C", "PKG-07", "leaf: W4-01B, W3-04C, W3-03B, W2-03D"),
    (
        "W4-01D",
        "PKG-07",
        "leaf: W4-01C, MNY-08C, MNY-11A, W2-04A, W2-04C",
    ),
    (
        "W4-02A",
        "PKG-08",
        "leaf: W3-00C, W3-00D, W3-00E, W3-01D, W3-02A, W3-02B",
    ),
    ("W4-02B", "PKG-08", "leaf: W4-02A"),
    (
        "W4-03A",
        "PKG-08",
        "leaf: R17-A, W4-01D, W4-02B; external-live: EXT-RELEASE-ENV, "
        "EXT-STAGING-APPROVAL",
    ),
    (
        "W4-03B",
        "PKG-08",
        "leaf: W4-02B; external-live: EXT-DISBURSEMENT-PROVIDER, "
        "EXT-SETTLEMENT-BANK, EXT-RM2-POLICY, EXT-STORAGE-PROVIDER, "
        "EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, "
        "EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, "
        "EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, "
        "EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, "
        "EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, "
        "EXT-STAGING-APPROVAL, EXT-PILOT-FACTS, EXT-PILOT-PERMITS",
    ),
    (
        "W4-04A",
        "PKG-09",
        "leaf: W4-01D, W4-02B; external-live: EXT-RELEASE-ENV, "
        "EXT-STAGING-APPROVAL, EXT-OPERATIONS-OWNER",
    ),
    (
        "W4-03C",
        "PKG-09",
        "leaf: W4-01D, W4-02B; external-live: EXT-DISBURSEMENT-PROVIDER, "
        "EXT-SETTLEMENT-BANK, EXT-RM2-POLICY, EXT-STORAGE-PROVIDER, "
        "EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, "
        "EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, "
        "EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, "
        "EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, "
        "EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, "
        "EXT-STAGING-APPROVAL, EXT-PILOT-FACTS, EXT-PILOT-PERMITS, "
        "EXT-OPERATIONS-OWNER",
    ),
    (
        "W4-04B",
        "PKG-09",
        "leaf: W4-01D, W4-02B; external-live: EXT-DISBURSEMENT-PROVIDER, "
        "EXT-SETTLEMENT-BANK, EXT-RM2-POLICY, EXT-STORAGE-PROVIDER, "
        "EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, "
        "EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, "
        "EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, "
        "EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, "
        "EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, "
        "EXT-STAGING-APPROVAL, EXT-PILOT-FACTS, EXT-PILOT-PERMITS, "
        "EXT-OPERATIONS-OWNER, EXT-BRAND-APPROVAL",
    ),
)

# The owner-approved remediation graph is a second, independently pinned
# register. It does not replace, renumber, or relax the original 71 checklist
# obligations above. Dependencies combine the admitted serial-lane and
# cross-lane edges; slice numbers are stable identities, not a topological
# ordering (R09 intentionally follows R10).
CANONICAL_REMEDIATION_SLICES = (
    ("R01", "GOV-001", "none", "CP-CONTROL"),
    ("R02", "GOV-003, TST-001, DB-005", "R01", "CP-CONTROL"),
    ("R03", "GOV-004", "R02", "CP-CONTROL"),
    ("R04", "DB-004", "none", "CP-DB"),
    ("R05", "DB-001, TST-012, ONB-010", "R02, R04", "CP-DB"),
    ("R06", "DB-002", "R02, R04, R05", "CP-DB"),
    ("R07", "DB-003", "R02, R04, R06", "CP-DB"),
    ("R08", "GOV-005", "none", "CP-SECURITY"),
    ("R09", "GOV-007, AUT-001, AUT-002", "R10", "CP-SECURITY"),
    ("R10", "AUT-005", "R08", "CP-SECURITY"),
    ("R11", "AUT-004", "R09", "CP-SECURITY"),
    ("R12", "AUT-003, REL-003", "R11", "CP-SECURITY"),
    ("R13", "SEC-001, PRV-008", "none", "CP-PRIVACY"),
    ("R14", "SEC-002, TST-004", "R12", "CP-SECURITY"),
    ("R15", "GOV-006", "none", "CP-WORKERS"),
    ("R16", "GOV-008", "none", "CP-CONTROL"),
    ("R17", "TST-007", "R02, R03", "CP-CONTROL"),
    ("R18", "MON-005, MON-006", "R04, R06, R07", "CP-MONEY"),
    ("R19", "MON-002", "R18", "CP-MONEY"),
    ("R20", "MON-001, DB-007, MON-008", "R05, R18", "CP-MONEY"),
    ("R21", "MON-003", "R20", "CP-MONEY"),
    ("R22", "MON-004, MON-007, MON-009", "R20, R21", "CP-MONEY"),
    ("R23", "COM-001, COM-004", "R08", "CP-COMMERCIAL"),
    ("R24", "COM-002", "R08, R23", "CP-COMMERCIAL"),
    ("R25", "COM-003, COM-005", "R08, R24", "CP-COMMERCIAL"),
    ("R26", "COM-006", "R08, R25", "CP-COMMERCIAL"),
    ("R27", "COM-007", "R08, R26", "CP-COMMERCIAL"),
    ("R28", "CAM-001", "none", "CP-CAMPAIGN"),
    ("R29", "CAM-002", "R04, R08, R28", "CP-CAMPAIGN"),
    ("R30", "CAM-003", "R29", "CP-CAMPAIGN"),
    ("R31", "CAM-004", "R18, R19, R30", "CP-CAMPAIGN"),
    ("R32", "ONB-002", "none", "CP-ONBOARDING"),
    ("R33", "ONB-006", "R05, R32", "CP-ONBOARDING"),
    ("R34", "OFF-001", "R04", "CP-OFFLINE"),
    ("R35", "OFF-002, OFF-003", "R34", "CP-OFFLINE"),
    ("R36", "OFF-005", "R35", "CP-OFFLINE"),
    ("R37", "OFF-006", "R36", "CP-OFFLINE"),
    ("R38", "PRV-001, PRV-002", "R13", "CP-PRIVACY"),
    ("R39", "PRV-003", "R38", "CP-PRIVACY"),
    ("R40", "PRV-004, AUD-001, AUD-002", "R16, R39", "CP-PRIVACY"),
    ("R41", "PRV-009, AUD-004, TST-010", "R40", "CP-PRIVACY"),
    ("R42", "PRV-005, PRV-006", "R41", "CP-PRIVACY"),
    ("R43", "PRV-007", "R42", "CP-PRIVACY"),
    ("R44", "AUD-005", "R16, R40", "CP-PRIVACY"),
    ("R45", "MET-003", "R04, R41", "CP-REPORTING"),
    ("R46", "REP-001", "R45", "CP-REPORTING"),
    ("R47", "MET-001, MET-002, MET-004, REP-002", "R41, R46", "CP-REPORTING"),
    ("R48", "REP-003", "R47", "CP-REPORTING"),
    ("R49", "REP-004", "R47, R48", "CP-REPORTING"),
    ("R50", "REP-005", "R47, R49", "CP-REPORTING"),
    ("R51", "REP-006", "R43, R49, R50", "CP-REPORTING"),
    ("R52", "MET-006", "R51", "CP-REPORTING"),
    ("R53", "REL-005", "none", "CP-RELEASE"),
    ("R54", "REL-006", "R12, R16, R53", "CP-RELEASE"),
    ("R55", "REL-004", "R03, R18, R48, R51, R54", "CP-RELEASE"),
    ("R56", "TST-005", "R09, R11, R14, R40", "CP-SECURITY"),
    ("R57", "TST-008", "R19, R27, R49, R55", "CP-RELEASE"),
    ("R58", "TST-011", "R15, R20, R21, R43, R49, R51", "CP-WORKERS"),
    (
        "R59",
        "TST-002",
        "R22, R31, R33, R37, R41, R44, R48, R50, R51, R56, R57, R58",
        "CP-RELEASE",
    ),
    (
        "R60",
        "GOV-009",
        "R03, R17, R18, R22, R27, R31, R33, R37, R43, R44, R52, R55, R56, R59",
        "CP-CONTROL",
    ),
)

# Stable external-input identities, in register order. States and evidence are
# mutable; adding, removing, renaming, or reordering an id requires an
# explicit validator diff — a docs/progress.md edit alone cannot erase a gate.
CANONICAL_EXTERNAL_IDS = (
    "EXT-STAGING-APPROVAL",
    "EXT-RM2-POLICY",
    "EXT-PAYMENT-PROVIDER",
    "EXT-STORAGE-PROVIDER",
    "EXT-MALWARE-SCANNER",
    "EXT-KMS-CUSTODY",
    "EXT-EMAIL-PROVIDER",
    "EXT-BUDGET-POLICY",
    "EXT-PHONE-OPERATOR",
    "EXT-BASEMAP",
    "EXT-STORE-ASSETS",
    "EXT-RELEASE-ENV",
    "EXT-PILOT-FACTS",
    "EXT-REPORT-METHOD",
    "EXT-Q28-COMPANY",
    "EXT-COMMERCIAL-VALUES",
    "EXT-EVIDENCE-POLICY",
    "EXT-LEGAL-PRIVACY",
    "EXT-DISBURSEMENT-PROVIDER",
    "EXT-AD-PLATFORM",
    "EXT-PILOT-PERMITS",
    "EXT-PKG07-OWNER-RELEASE",
    "EXT-RM2-CALIBRATION-DATA",
    "EXT-BRAND-APPROVAL",
    "EXT-CAMPAIGN-BUDGET-SCOPE",
    "EXT-SETTLEMENT-BANK",
    "EXT-UPLOAD-POLICY",
    "EXT-MESSAGE-COPY",
    "EXT-RM2-APPROVER",
    "EXT-OPERATIONS-OWNER",
)

CANONICAL_DEFERRED_VALIDATIONS = (
    ("DV-PWA-PHYSICAL-MATRIX", "W4 production-PWA pilot acceptance / any real driver GPS"),
    ("DV-PWA-ROUTE-BATTERY", "W4 production-PWA pilot acceptance"),
    ("DV-STAGING-LIVE", "W4 client-owned release and pilot gates"),
)

# Authoritative headings must occur exactly once at top level; the boundary
# headings that close them are pinned too, so a decoy cannot truncate a
# section. All parsing runs on the sanitized authoritative view.
AUTHORITATIVE_HEADINGS = (
    "## External prerequisite register",
    "## Deferred post-build validation register",
    "## Canonical repository",
    "## Executable package queue",
    "## Executable package contracts",
    "## Remediation slice register",
    "## Architecture traceability — non-executable parent groups",
    "## Mandatory checklist item register",
    "## Checklist item specifications",
    "## Coverage proof",
)
CONTROLLER_LABELS = ("Controller state", "Control package", "Current checkpoint")


@dataclass(frozen=True)
class Package:
    number: int
    package_id: str
    status: str
    prerequisites: str
    line: int


@dataclass(frozen=True)
class Item:
    number: int
    item_id: str
    package_id: str
    status: str
    prerequisites: str
    line: int


@dataclass(frozen=True)
class RemediationSlice:
    slice_id: str
    candidate_ids: str
    dependencies: str
    status: str
    plan_review: str
    diff_review: str
    checkpoint: str
    line: int


def _plain(value: str) -> str:
    return value.replace("**", "").replace("`", "").strip()


def _blank_preserving_newlines(segment: str) -> str:
    return "".join("\n" if char == "\n" else " " for char in segment)


def _authoritative_view(text: str, errors: list[str]) -> str:
    """Blank HTML comments and fenced code blocks, preserving every newline.

    Hidden or fenced content can decoy human-invisible authoritative
    sections/pointers, so it never participates in validation. Unbalanced
    markers fail loudly instead of silently hiding part of the document.
    """
    pieces: list[str] = []
    position = 0
    while True:
        start = text.find("<!--", position)
        if start < 0:
            pieces.append(text[position:])
            break
        end = text.find("-->", start + 4)
        pieces.append(text[position:start])
        if end < 0:
            errors.append(
                f"line {text[:start].count(chr(10)) + 1}: unterminated HTML comment"
            )
            pieces.append(_blank_preserving_newlines(text[start:]))
            break
        pieces.append(_blank_preserving_newlines(text[start : end + 3]))
        position = end + 3
    lines = "".join(pieces).split("\n")
    fence_open_line: int | None = None
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fence_open_line = None if fence_open_line is not None else index + 1
            lines[index] = " " * len(line)
        elif fence_open_line is not None:
            lines[index] = " " * len(line)
    if fence_open_line is not None:
        errors.append(f"line {fence_open_line}: unclosed code fence")
    return "\n".join(lines)


def _check_unique_authority_markers(text: str, errors: list[str]) -> None:
    for heading in AUTHORITATIVE_HEADINGS:
        title = heading.removeprefix("## ")
        occurrences = re.findall(
            rf"^#{{1,6}}\s+{re.escape(title)}\b.*$", text, re.MULTILINE
        )
        if len(occurrences) != 1:
            errors.append(
                f"authoritative heading {title!r} must appear exactly once at any "
                f"heading level; found {len(occurrences)}"
            )
    for label in CONTROLLER_LABELS:
        count = len(re.findall(rf"\*\*{label}:\*\*", text))
        if count != 1:
            errors.append(
                f"controller field {label!r} must appear exactly once; found {count}"
            )


def _section(text: str, heading: str, next_heading: str) -> tuple[str, int]:
    match = re.search(rf"^{re.escape(heading)}\b.*$", text, re.MULTILINE)
    if not match:
        raise ValueError(f"missing section {heading!r}")
    start = match.start()
    boundary = re.compile(rf"^{re.escape(next_heading)}\b.*$", re.MULTILINE)
    end_match = boundary.search(text, match.end())
    if not end_match:
        raise ValueError(f"missing section boundary {next_heading!r}")
    return text[start : end_match.start()], text[:start].count("\n") + 1


def _table(section: str, header_prefix: str, base_line: int) -> list[tuple[int, list[str]]]:
    lines = section.splitlines()
    matches = [i for i, line in enumerate(lines) if line.startswith(header_prefix)]
    if not matches:
        raise ValueError(f"missing table header {header_prefix!r}")
    if len(matches) > 1:
        raise ValueError(
            f"table header {header_prefix!r} must appear exactly once in its "
            f"section; found {len(matches)}"
        )
    index = matches[0]
    rows: list[tuple[int, list[str]]] = []
    for row_index, line in enumerate(lines[index + 2 :], start=index + 2):
        if not line.startswith("|"):
            break
        rows.append((base_line + row_index, [cell.strip() for cell in line.strip("|").split("|")]))
    return rows


def _parse_item_prerequisites(
    item: Item,
    earlier_ids: set[str],
    external_states: dict[str, str],
    errors: list[str],
) -> tuple[list[str], list[str]]:
    if item.prerequisites == "none":
        return [], []
    item_dependencies: list[str] = []
    external_dependencies: list[str] = []
    all_prior = False
    for segment in item.prerequisites.split("; "):
        if segment == "all-prior":
            if item.item_id != "W4-03B":
                errors.append(f"line {item.line}: all-prior is reserved for W4-03B")
            all_prior = True
        elif segment.startswith("leaf: "):
            values = segment.removeprefix("leaf: ").split(", ")
            item_dependencies.extend(values)
        elif segment.startswith("external: "):
            values = segment.removeprefix("external: ").split(", ")
            external_dependencies.extend(values)
        elif segment.startswith("external-live: "):
            values = segment.removeprefix("external-live: ").split(", ")
            external_dependencies.extend(values)
        else:
            errors.append(f"line {item.line}: non-canonical prerequisite {segment!r}")
    if all_prior:
        item_dependencies.extend(sorted(earlier_ids))
    for dependency in item_dependencies:
        if dependency not in earlier_ids:
            errors.append(
                f"line {item.line}: {item.item_id} dependency {dependency} "
                "is missing or not earlier"
            )
    for dependency in external_dependencies:
        if dependency not in external_states:
            errors.append(
                f"line {item.line}: {item.item_id} external prerequisite "
                f"{dependency} is unregistered"
            )
    if len(item_dependencies) != len(set(item_dependencies)):
        errors.append(f"line {item.line}: {item.item_id} repeats an item dependency")
    if len(external_dependencies) != len(set(external_dependencies)):
        errors.append(f"line {item.line}: {item.item_id} repeats an external dependency")
    return item_dependencies, external_dependencies


def validate_text(text: str) -> list[str]:
    errors: list[str] = []

    text = _authoritative_view(text, errors)
    _check_unique_authority_markers(text, errors)

    external_section = ""
    external_line = 0
    try:
        external_section, external_line = _section(
            text, "## External prerequisite register", "## Canonical repository"
        )
        external_rows = _table(external_section, "| ID | State |", external_line)
    except ValueError as exc:
        errors.append(str(exc))
        external_rows = []
    external_states: dict[str, str] = {}
    for line, cells in external_rows:
        if len(cells) != 5:
            errors.append(f"line {line}: external row must have 5 cells")
            continue
        external_id, state, evidence = _plain(cells[0]), _plain(cells[1]), _plain(cells[3])
        if not re.fullmatch(r"EXT-[A-Z0-9-]+", external_id):
            errors.append(f"line {line}: invalid external id {external_id!r}")
            continue
        if external_id in external_states:
            errors.append(f"line {line}: duplicate external id {external_id}")
        if state not in {"PRESENT", "MISSING"}:
            errors.append(f"line {line}: {external_id} state must be PRESENT or MISSING")
        if state == "PRESENT" and evidence in {"", "—"}:
            errors.append(f"line {line}: PRESENT input {external_id} must cite evidence")
        external_states[external_id] = state
    if tuple(external_states) != CANONICAL_EXTERNAL_IDS:
        errors.append(
            "external register identities/order changed: expected "
            f"{list(CANONICAL_EXTERNAL_IDS)}, found {list(external_states)}"
        )

    try:
        deferred_rows = _table(
            external_section, "| Validation | State |", external_line
        )
    except ValueError as exc:
        errors.append(str(exc))
        deferred_rows = []
    deferred_states: dict[str, str] = {}
    deferred_contract: list[tuple[str, str]] = []
    for line, cells in deferred_rows:
        if len(cells) != 4:
            errors.append(f"line {line}: deferred validation row must have 4 cells")
            continue
        validation_id = _plain(cells[0])
        state = _plain(cells[1])
        required_before = _plain(cells[3])
        if not re.fullmatch(r"DV-[A-Z0-9-]+", validation_id):
            errors.append(f"line {line}: invalid deferred validation id {validation_id!r}")
            continue
        if state != "COMPLETE" and not state.startswith("NOT RUN — "):
            errors.append(
                f"line {line}: {validation_id} state must be COMPLETE or NOT RUN — reason"
            )
        deferred_states[validation_id] = state
        deferred_contract.append((validation_id, required_before))
    if tuple(deferred_contract) != CANONICAL_DEFERRED_VALIDATIONS:
        errors.append(
            "deferred validation identities/order/gates changed: expected "
            f"{list(CANONICAL_DEFERRED_VALIDATIONS)}, found {deferred_contract}"
        )

    try:
        package_section, package_line = _section(
            text, "## Executable package queue", "## Executable package contracts"
        )
        package_rows = _table(package_section, "| # | Package |", package_line)
    except ValueError as exc:
        errors.append(str(exc))
        package_rows = []
    packages: list[Package] = []
    for line, cells in package_rows:
        if len(cells) != 5:
            errors.append(f"line {line}: package row must have 5 cells")
            continue
        try:
            number = int(_plain(cells[0]))
        except ValueError:
            errors.append(f"line {line}: invalid package number")
            continue
        match = re.match(r"\*\*(PKG-\d{2}) —", cells[1])
        if not match:
            errors.append(f"line {line}: package must begin with bold PKG-NN id")
            continue
        packages.append(Package(number, match.group(1), _plain(cells[2]), cells[4], line))
    if [package.number for package in packages] != list(range(1, 11)):
        errors.append("package numbering must be exactly 1 through 10")
    if [package.package_id for package in packages] != [f"PKG-{n:02d}" for n in range(1, 11)]:
        errors.append("package ids must be exactly PKG-01 through PKG-10")
    for package in packages:
        if package.status not in PACKAGE_STATUSES:
            errors.append(f"line {package.line}: invalid package status {package.status!r}")
        allowed_prerequisites = {"none", "none — checklist DAG gates entry"}
        if package.package_id == "PKG-10":
            allowed_prerequisites.add("none — remediation DAG gates entry")
        if package.prerequisites not in allowed_prerequisites:
            errors.append(
                f"line {package.line}: package entry must use its pinned DAG authority"
            )

    try:
        contract_section, contract_line = _section(
            text, "## Executable package contracts", "## Remediation slice register"
        )
        package_card_ids = re.findall(r"^### (PKG-\d{2}) —", contract_section, re.MULTILINE)
    except ValueError as exc:
        errors.append(str(exc))
        package_card_ids = []
        contract_line = 0
        contract_section = ""
    if [package.package_id for package in packages] != package_card_ids:
        errors.append(
            "package queue ids must equal package card ids in order "
            f"(cards near line {contract_line})"
        )
    canonical_numbers_by_package: dict[str, set[int]] = {}
    for number, (_, owner_package, _) in enumerate(CANONICAL_ITEMS, start=1):
        canonical_numbers_by_package.setdefault(owner_package, set()).add(number)
    card_chunks = re.split(r"^### (PKG-\d{2}) —.*$", contract_section, flags=re.MULTILINE)
    for card_id, card_body in zip(card_chunks[1::2], card_chunks[2::2], strict=False):
        if card_id == "PKG-10":
            owns_count = len(
                re.findall(
                    r"^- \*\*Owns:\*\* remediation slices R01–R60\.$",
                    card_body,
                    re.MULTILINE,
                )
            )
            if owns_count != 1:
                errors.append(
                    "package card PKG-10 must declare exactly `Owns: remediation "
                    "slices R01–R60.`"
                )
            continue
        owns_matches = re.findall(
            r"- \*\*Owns:\*\* checklist (\d+)[–-](\d+)", card_body
        )
        if len(owns_matches) != 1:
            errors.append(
                f"package card {card_id} must declare exactly one Owns: checklist "
                f"A–B range; found {len(owns_matches)}"
            )
            continue
        declared = set(range(int(owns_matches[0][0]), int(owns_matches[0][1]) + 1))
        if declared != canonical_numbers_by_package.get(card_id, set()):
            errors.append(
                f"package card {card_id} Owns declaration does not match the "
                "canonical checklist membership"
            )

    try:
        remediation_section, remediation_line = _section(
            text,
            "## Remediation slice register",
            "## Architecture traceability — non-executable parent groups",
        )
        remediation_rows = _table(
            remediation_section, "| Slice | Candidate IDs |", remediation_line
        )
    except ValueError as exc:
        errors.append(str(exc))
        remediation_rows = []
    remediation_slices: list[RemediationSlice] = []
    for line, cells in remediation_rows:
        if len(cells) != 7:
            errors.append(f"line {line}: remediation slice row must have 7 cells")
            continue
        slice_id = _plain(cells[0])
        if not re.fullmatch(r"R\d{2}", slice_id):
            errors.append(f"line {line}: invalid remediation slice id {slice_id!r}")
            continue
        remediation_slices.append(
            RemediationSlice(
                slice_id=slice_id,
                candidate_ids=_plain(cells[1]),
                dependencies=_plain(cells[2]),
                status=_plain(cells[3]),
                plan_review=_plain(cells[4]),
                diff_review=_plain(cells[5]),
                checkpoint=_plain(cells[6]),
                line=line,
            )
        )

    actual_remediation_manifest = tuple(
        (
            remediation_slice.slice_id,
            remediation_slice.candidate_ids,
            remediation_slice.dependencies,
            remediation_slice.checkpoint.split(" ", 1)[0],
        )
        for remediation_slice in remediation_slices
    )
    if actual_remediation_manifest != CANONICAL_REMEDIATION_SLICES:
        for number, (actual, expected) in enumerate(
            zip(actual_remediation_manifest, CANONICAL_REMEDIATION_SLICES, strict=False),
            start=1,
        ):
            if actual != expected:
                errors.append(
                    f"remediation slice {number} identity/candidates/dependencies/checkpoint "
                    f"changed: expected {expected!r}, found {actual!r}"
                )
        if len(actual_remediation_manifest) != len(CANONICAL_REMEDIATION_SLICES):
            errors.append(
                f"canonical remediation register has {len(CANONICAL_REMEDIATION_SLICES)} "
                f"slices; found {len(actual_remediation_manifest)}"
            )

    remediation_ids = [remediation_slice.slice_id for remediation_slice in remediation_slices]
    if len(remediation_ids) != len(set(remediation_ids)):
        errors.append("remediation slice ids must be unique")
    remediation_by_id = {
        remediation_slice.slice_id: remediation_slice
        for remediation_slice in remediation_slices
    }
    remediation_dependencies: dict[str, list[str]] = {}
    for remediation_slice in remediation_slices:
        dependencies = (
            []
            if remediation_slice.dependencies == "none"
            else remediation_slice.dependencies.split(", ")
        )
        remediation_dependencies[remediation_slice.slice_id] = dependencies
        if len(dependencies) != len(set(dependencies)):
            errors.append(
                f"line {remediation_slice.line}: {remediation_slice.slice_id} repeats a dependency"
            )
        for dependency in dependencies:
            if dependency == remediation_slice.slice_id:
                errors.append(
                    f"line {remediation_slice.line}: {remediation_slice.slice_id} depends on itself"
                )
            elif dependency not in remediation_by_id:
                errors.append(
                    f"line {remediation_slice.line}: {remediation_slice.slice_id} dependency "
                    f"{dependency} is unknown"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit_remediation(slice_id: str) -> None:
        if slice_id in visiting:
            errors.append(f"remediation dependency graph contains a cycle at {slice_id}")
            return
        if slice_id in visited:
            return
        visiting.add(slice_id)
        for dependency in remediation_dependencies.get(slice_id, []):
            if dependency in remediation_by_id:
                visit_remediation(dependency)
        visiting.remove(slice_id)
        visited.add(slice_id)

    for remediation_slice in remediation_slices:
        visit_remediation(remediation_slice.slice_id)

    for remediation_slice in remediation_slices:
        slice_id = remediation_slice.slice_id
        expected_checkpoint = next(
            (
                checkpoint
                for expected_id, _, _, checkpoint in CANONICAL_REMEDIATION_SLICES
                if expected_id == slice_id
            ),
            "",
        )
        plan_pass = remediation_slice.plan_review == f"PASS — {slice_id}-P"
        diff_pass = remediation_slice.diff_review == f"PASS — {slice_id}-M"
        checkpoint_pending = remediation_slice.checkpoint == f"{expected_checkpoint} PENDING"
        checkpoint_pass = (
            remediation_slice.checkpoint
            == f"{expected_checkpoint} PASS — {slice_id}-{expected_checkpoint}"
        )
        if remediation_slice.status not in REMEDIATION_SLICE_STATUSES:
            errors.append(
                f"line {remediation_slice.line}: invalid remediation state "
                f"{remediation_slice.status!r}"
            )
        if remediation_slice.plan_review not in {"PENDING", f"PASS — {slice_id}-P"}:
            errors.append(
                f"line {remediation_slice.line}: invalid {slice_id} plan-review receipt"
            )
        if remediation_slice.diff_review not in {"PENDING", f"PASS — {slice_id}-M"}:
            errors.append(
                f"line {remediation_slice.line}: invalid {slice_id} diff-review receipt"
            )
        if not (checkpoint_pending or checkpoint_pass):
            errors.append(
                f"line {remediation_slice.line}: invalid {slice_id} domain-checkpoint receipt"
            )
        if remediation_slice.status == "QUEUED" and (
            remediation_slice.diff_review != "PENDING" or not checkpoint_pending
        ):
            errors.append(
                f"line {remediation_slice.line}: QUEUED {slice_id} must keep diff and "
                "checkpoint receipts pending"
            )
        if remediation_slice.status == "ACTIVE" and not plan_pass:
            errors.append(
                f"line {remediation_slice.line}: ACTIVE {slice_id} requires its plan-review PASS"
            )
        if checkpoint_pass and not diff_pass:
            errors.append(
                f"line {remediation_slice.line}: {slice_id} checkpoint cannot pass "
                "before diff review"
            )
        if remediation_slice.status == "COMPLETE" and not (
            plan_pass and diff_pass and checkpoint_pass
        ):
            errors.append(
                f"line {remediation_slice.line}: COMPLETE {slice_id} requires P, M, and "
                "domain-checkpoint PASS receipts"
            )

    remediation_status_by_id = {
        remediation_slice.slice_id: remediation_slice.status
        for remediation_slice in remediation_slices
    }
    for remediation_slice in remediation_slices:
        if remediation_slice.status in {"ACTIVE", "COMPLETE"}:
            unfinished = [
                dependency
                for dependency in remediation_dependencies.get(remediation_slice.slice_id, [])
                if remediation_status_by_id.get(dependency) != "COMPLETE"
            ]
            if unfinished:
                errors.append(
                    f"line {remediation_slice.line}: {remediation_slice.status} "
                    f"{remediation_slice.slice_id} has unfinished dependencies: "
                    + ", ".join(unfinished)
                )
    active_remediation_slices = [
        remediation_slice
        for remediation_slice in remediation_slices
        if remediation_slice.status == "ACTIVE"
    ]
    if len(active_remediation_slices) > 2:
        errors.append(
            f"at most two remediation slices may be ACTIVE; found {len(active_remediation_slices)}"
        )

    try:
        parent_section, parent_line = _section(
            text,
            "## Architecture traceability — non-executable parent groups",
            "## Mandatory checklist item register",
        )
        parent_rows = _table(parent_section, "| Order | Parent outcome |", parent_line)
    except ValueError as exc:
        errors.append(str(exc))
        parent_rows = []
    if len(parent_rows) != 22:
        errors.append(
            f"architecture traceability must contain 22 parent rows; found {len(parent_rows)}"
        )
    for line, cells in parent_rows:
        if len(cells) != 7 or _plain(cells[2]) != "PARENT":
            errors.append(f"line {line}: traceability row must have 7 cells and type PARENT")

    try:
        item_section, item_line = _section(
            text, "## Mandatory checklist item register", "## Checklist item specifications"
        )
        item_rows = _table(item_section, "| # | Checklist item |", item_line)
    except ValueError as exc:
        errors.append(str(exc))
        item_rows = []
    items: list[Item] = []
    for line, cells in item_rows:
        if len(cells) != 6:
            errors.append(f"line {line}: checklist row must have 6 cells")
            continue
        try:
            number = int(_plain(cells[0]))
        except ValueError:
            errors.append(f"line {line}: invalid checklist number")
            continue
        match = re.match(r"\*\*([A-Z0-9-]+) —", cells[1])
        if not match:
            errors.append(f"line {line}: checklist item must begin with a bold stable id")
            continue
        items.append(
            Item(number, match.group(1), _plain(cells[2]), _plain(cells[3]), cells[5], line)
        )
    if [item.number for item in items] != list(range(1, 72)):
        errors.append("checklist numbering must be exactly 1 through 71")
    item_ids = [item.item_id for item in items]
    if len(item_ids) != len(set(item_ids)):
        errors.append("checklist ids must be unique")
    actual_manifest = tuple(
        (item.item_id, item.package_id, item.prerequisites) for item in items
    )
    if actual_manifest != CANONICAL_ITEMS:
        for number, (actual, expected) in enumerate(
            zip(actual_manifest, CANONICAL_ITEMS, strict=False), start=1
        ):
            if actual != expected:
                errors.append(
                    f"checklist {number} identity/package/prerequisites changed: "
                    f"expected {expected!r}, found {actual!r}"
                )
        if len(actual_manifest) != len(CANONICAL_ITEMS):
            errors.append(
                f"canonical checklist has {len(CANONICAL_ITEMS)} items; "
                f"found {len(actual_manifest)}"
            )
    for item in items:
        if item.status not in CHECKLIST_STATUSES and not item.status.startswith("BLOCKED — "):
            errors.append(f"line {item.line}: invalid checklist status {item.status!r}")
        if item.status in ACTIVE_PACKAGE_STATUSES or item.status == "QUEUED":
            errors.append(f"line {item.line}: checklist items cannot carry package-active status")

    try:
        specification_section, specification_line = _section(
            text, "## Checklist item specifications", "## Coverage proof"
        )
        specification_ids = re.findall(r"^#### ([A-Z0-9-]+) —", specification_section, re.MULTILINE)
    except ValueError as exc:
        errors.append(str(exc))
        specification_ids = []
        specification_line = 0
        specification_section = ""
    if item_ids != specification_ids:
        errors.append(
            "checklist ids must equal specification-card ids in order "
            f"(cards near line {specification_line})"
        )
    specification_chunks = re.split(
        r"^#### [A-Z0-9-]+ —.*$", specification_section, flags=re.MULTILINE
    )[1:]
    for item_id, chunk in zip(specification_ids, specification_chunks, strict=False):
        obligations = ("- **Scope / authority:**", "- **Acceptance:**", "- **Verify / review:**")
        for obligation in obligations:
            if obligation not in chunk:
                errors.append(f"checklist specification {item_id} is missing {obligation}")

    dependencies: dict[str, tuple[list[str], list[str]]] = {}
    earlier_ids: set[str] = set()
    for item in items:
        dependencies[item.item_id] = _parse_item_prerequisites(
            item, earlier_ids, external_states, errors
        )
        earlier_ids.add(item.item_id)
    status_by_id = {item.item_id: item.status for item in items}
    incomplete_deferred = [
        validation_id
        for validation_id, _ in CANONICAL_DEFERRED_VALIDATIONS
        if deferred_states.get(validation_id) != "COMPLETE"
    ]
    if status_by_id.get("W4-03B") == "DONE" and incomplete_deferred:
        errors.append(
            "W4-03B cannot be DONE while deferred validation remains incomplete: "
            + ", ".join(incomplete_deferred)
        )
    if (
        status_by_id.get("W4-03A") == "DONE"
        and deferred_states.get("DV-STAGING-LIVE") != "COMPLETE"
    ):
        errors.append("W4-03A cannot be DONE while DV-STAGING-LIVE is incomplete")

    def runnable(item: Item) -> bool:
        if item.status != "TODO":
            return False
        item_dependencies, external_dependencies = dependencies.get(item.item_id, ([], []))
        live_only = {
            value
            for segment in item.prerequisites.split("; ")
            if segment.startswith("external-live: ")
            for value in segment.removeprefix("external-live: ").split(", ")
        }
        return all(status_by_id.get(dep) == "DONE" for dep in item_dependencies) and all(
            external_states.get(dep) == "PRESENT"
            for dep in external_dependencies
            if dep not in live_only
        )

    def blocked_chain(item_id: str, seen: set[str] | None = None) -> bool:
        item = next((candidate for candidate in items if candidate.item_id == item_id), None)
        if not item:
            return False
        if item.status.startswith("BLOCKED — "):
            return True
        if item.status == "DONE":
            return False
        seen = set() if seen is None else seen
        if item_id in seen:
            return False
        seen.add(item_id)
        item_dependencies, _ = dependencies.get(item_id, ([], []))
        return bool(item_dependencies) and any(
            blocked_chain(dependency, seen.copy()) for dependency in item_dependencies
        )

    def blocker_ids(item_id: str, seen: set[str] | None = None) -> set[str]:
        item = next((candidate for candidate in items if candidate.item_id == item_id), None)
        if not item or item.status == "DONE":
            return set()
        if item.status.startswith("BLOCKED — "):
            return set(item.status.removeprefix("BLOCKED — ").split(", "))
        seen = set() if seen is None else seen
        if item_id in seen:
            return set()
        seen.add(item_id)
        item_dependencies, _ = dependencies.get(item_id, ([], []))
        return set().union(
            *(blocker_ids(dependency, seen.copy()) for dependency in item_dependencies)
        )

    for item in items:
        item_dependencies, external_dependencies = dependencies.get(item.item_id, ([], []))
        if item.status == "DONE":
            unfinished_dependencies = [
                dependency
                for dependency in item_dependencies
                if status_by_id.get(dependency) != "DONE"
            ]
            missing_external = [
                dependency
                for dependency in external_dependencies
                if external_states.get(dependency) != "PRESENT"
            ]
            if unfinished_dependencies:
                errors.append(
                    f"line {item.line}: DONE item {item.item_id} has unfinished "
                    f"dependencies: {', '.join(unfinished_dependencies)}"
                )
            if missing_external:
                errors.append(
                    f"line {item.line}: DONE item {item.item_id} has missing external "
                    f"prerequisites: {', '.join(missing_external)}"
                )
        if item.status.startswith("BLOCKED — "):
            named = item.status.removeprefix("BLOCKED — ").split(", ")
            for external_id in named:
                if external_id not in external_dependencies:
                    errors.append(
                        f"line {item.line}: blocked input {external_id} is not an item prerequisite"
                    )
                elif external_states.get(external_id) != "MISSING":
                    errors.append(
                        f"line {item.line}: blocked input {external_id} is not registered MISSING"
                    )
            direct_missing = {
                dependency
                for dependency in external_dependencies
                if external_states.get(dependency) == "MISSING"
            }
            if set(named) != direct_missing:
                errors.append(
                    f"line {item.line}: {item.item_id} must name exactly its missing "
                    f"direct external inputs ({', '.join(sorted(direct_missing)) or 'none'})"
                )

    package_items = {
        package.package_id: [item for item in items if item.package_id == package.package_id]
        for package in packages
    }
    for package in packages:
        if package.package_id == "PKG-10":
            all_remediation_complete = bool(remediation_slices) and all(
                remediation_slice.status == "COMPLETE"
                for remediation_slice in remediation_slices
            )
            if package.status == "DONE" and not all_remediation_complete:
                errors.append(
                    f"line {package.line}: DONE PKG-10 contains unfinished remediation slices"
                )
            if all_remediation_complete and package.status != "DONE":
                errors.append(
                    f"line {package.line}: PKG-10 must be DONE when all remediation slices "
                    "are COMPLETE"
                )
            if active_remediation_slices and package.status not in ACTIVE_PACKAGE_STATUSES:
                errors.append(
                    f"line {package.line}: ACTIVE remediation slices require active PKG-10"
                )
            continue
        owned = package_items.get(package.package_id, [])
        if package.status == "DONE" and any(item.status != "DONE" for item in owned):
            errors.append(f"line {package.line}: DONE package contains unfinished checklist items")
        if package.status == "BLOCKED":
            if not any(item.status != "DONE" for item in owned):
                errors.append(f"line {package.line}: BLOCKED package has no unfinished work")
            if any(runnable(item) for item in owned):
                errors.append(f"line {package.line}: BLOCKED package still has runnable TODO work")
            if any(item.status != "DONE" and not blocked_chain(item.item_id) for item in owned):
                errors.append(
                    f"line {package.line}: BLOCKED package has unfinished work "
                    "not tied to a blocker"
                )

    def remediation_runnable(remediation_slice: RemediationSlice) -> bool:
        return remediation_slice.status == "QUEUED" and all(
            remediation_status_by_id.get(dependency) == "COMPLETE"
            for dependency in remediation_dependencies.get(remediation_slice.slice_id, [])
        )

    active_packages = [package for package in packages if package.status in ACTIVE_PACKAGE_STATUSES]
    controller_match = re.search(r"\*\*Controller state:\*\* `([^`]+)`", text)
    package_pointer_match = re.search(r"\*\*Control package:\*\* `([^`]+)`", text)
    checkpoint_match = re.search(r"\*\*Current checkpoint:\*\* `(PKG-\d{2}) / ([A-Z0-9-]+)`", text)
    controller_state = controller_match.group(1) if controller_match else ""
    package_pointer = package_pointer_match.group(1) if package_pointer_match else ""
    if len(active_packages) == 1:
        active = active_packages[0]
        earlier_packages = [package for package in packages if package.number < active.number]
        if any(package.status not in {"DONE", "BLOCKED"} for package in earlier_packages):
            errors.append(
                "active package bypasses an earlier package that is neither DONE nor BLOCKED"
            )
        for later in packages:
            if later.number > active.number and later.status not in {"QUEUED", "BLOCKED"}:
                errors.append(
                    f"line {later.line}: package after the active frontier must be "
                    "QUEUED or BLOCKED"
                )
        if controller_state != "ACTIVE":
            errors.append("controller must be ACTIVE while a package is active")
        if package_pointer != active.package_id:
            errors.append("control package pointer does not match the active package")
        if active.package_id == "PKG-10":
            if not checkpoint_match:
                errors.append("active PKG-10 requires a Current checkpoint")
            else:
                checkpoint_package, checkpoint_id = checkpoint_match.groups()
                checkpoint_slice = remediation_by_id.get(checkpoint_id)
                if checkpoint_package != "PKG-10" or not checkpoint_slice:
                    errors.append("current checkpoint does not belong to PKG-10")
                elif checkpoint_slice.status != "ACTIVE" and not remediation_runnable(
                    checkpoint_slice
                ):
                    errors.append(
                        "current remediation checkpoint is neither ACTIVE nor "
                        "dependency-satisfied QUEUED work"
                    )
            if not active_remediation_slices and not any(
                remediation_runnable(remediation_slice)
                for remediation_slice in remediation_slices
            ):
                errors.append("active PKG-10 has no ACTIVE or runnable remediation slice")
        else:
            owned_active = package_items.get(active.package_id, [])
            # A REVIEW package with every owned item DONE is the consolidated
            # closure review; any other active state still needs runnable work.
            closure_review = active.status == "REVIEW" and bool(owned_active) and all(
                item.status == "DONE" for item in owned_active
            )
            if not checkpoint_match:
                errors.append("active package requires a Current checkpoint")
            else:
                checkpoint_package, checkpoint_id = checkpoint_match.groups()
                checkpoint = next((item for item in items if item.item_id == checkpoint_id), None)
                if checkpoint_package != active.package_id or not checkpoint:
                    errors.append("current checkpoint does not belong to the active package")
                elif checkpoint.package_id != active.package_id:
                    errors.append("current checkpoint item is mapped to another package")
                elif not closure_review and not runnable(checkpoint):
                    errors.append("current checkpoint is not a dependency-satisfied runnable TODO")
            if not closure_review and not any(runnable(item) for item in owned_active):
                errors.append("active package has no runnable TODO checklist item")
    elif not active_packages:
        all_complete = bool(packages and items and remediation_slices) and all(
            package.status == "DONE" for package in packages
        ) and all(item.status == "DONE" for item in items) and all(
            remediation_slice.status == "COMPLETE"
            for remediation_slice in remediation_slices
        )
        if controller_state == "COMPLETE":
            if not all_complete:
                errors.append(
                    "COMPLETE controller requires every package and owned item to be DONE"
                )
            if package_pointer != "PKG-09":
                errors.append("COMPLETE controller must retain PKG-09 as control package")
            if not checkpoint_match or checkpoint_match.groups() != ("PKG-09", "W4-04B"):
                errors.append("COMPLETE controller must retain PKG-09 / W4-04B checkpoint")
            if all_complete and incomplete_deferred:
                errors.append(
                    "COMPLETE controller requires deferred validation COMPLETE: "
                    + ", ".join(incomplete_deferred)
                )
        else:
            if not re.fullmatch(r"PAUSED — EXT-[A-Z0-9-]+", controller_state):
                errors.append(
                    "zero-active state requires Controller state PAUSED — EXT-ID or COMPLETE"
                )
            pointed = next(
                (package for package in packages if package.package_id == package_pointer), None
            )
            if not pointed or pointed.status != "BLOCKED":
                errors.append("paused control package must point to a BLOCKED package")
            if pointed:
                for other in packages:
                    if other.number < pointed.number and other.status not in {"DONE", "BLOCKED"}:
                        errors.append(
                            f"line {other.line}: paused control package bypasses an earlier "
                            "package that is neither DONE nor BLOCKED"
                        )
                    if other.number > pointed.number and other.status not in {
                        "QUEUED",
                        "BLOCKED",
                        "DONE",
                    }:
                        errors.append(
                            f"line {other.line}: package after the paused control package "
                            "must be QUEUED, BLOCKED, or DONE"
                        )
            checkpoint = None
            if not checkpoint_match:
                errors.append("paused controller requires a Current checkpoint")
            else:
                checkpoint_package, checkpoint_id = checkpoint_match.groups()
                checkpoint = next(
                    (item for item in items if item.item_id == checkpoint_id), None
                )
                if (
                    not pointed
                    or checkpoint_package != pointed.package_id
                    or not checkpoint
                    or checkpoint.package_id != pointed.package_id
                ):
                    errors.append("paused checkpoint must belong to the blocked control package")
            paused_external = controller_state.removeprefix("PAUSED — ")
            if paused_external not in external_states:
                errors.append("paused controller external id is not registered")
            elif external_states[paused_external] != "MISSING":
                errors.append("paused controller external id is not MISSING")
            if any(runnable(item) for item in items) or any(
                remediation_runnable(remediation_slice)
                for remediation_slice in remediation_slices
            ):
                errors.append("paused controller is invalid while runnable TODO work exists")
            if not checkpoint or paused_external not in blocker_ids(checkpoint.item_id):
                errors.append(
                    "paused controller external id does not block the current checkpoint"
                )
    else:
        errors.append(f"exactly one package may be active; found {len(active_packages)}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PROGRESS)
    args = parser.parse_args(argv)
    errors = validate_text(args.path.read_text(encoding="utf-8"))
    if errors:
        print(f"{args.path}: delivery-control validation failed", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"{args.path}: package/checklist validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

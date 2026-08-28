#!/usr/bin/env python3
"""Validate the provider-neutral W4-04B-P1 handover preparation pack."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

HANDOVER_FILES = {
    "README.md",
    "backup-schedule.md",
    "credential-handover-checklist.md",
    "external-and-deferred-risks.md",
    "post-mvp-roadmap.md",
    "roles-and-responsibilities.md",
    "support-sla-escalation.md",
}

INDEX_DOMAINS = {
    "System",
    "Release",
    "Backup and recovery",
    "Training",
    "Pilot operations",
    "Privacy and security",
    "Money and payout",
    "Reporting",
    "Incident and recovery",
}

ROLE_PLACEHOLDERS = {
    "<BUSINESS_ACCOUNTABLE_ROLE>",
    "<OPERATIONS_OWNER_ROLE>",
    "<RELEASE_OPERATOR_ROLE>",
    "<SERVICE_SUPPORT_COORDINATOR_ROLE>",
    "<INCIDENT_COMMANDER_ROLE>",
    "<SECURITY_OWNER_ROLE>",
    "<PRIVACY_DECISION_ROLE>",
    "<MONEY_MAKER_ROLE>",
    "<MONEY_CHECKER_ROLE>",
    "<MONEY_RECONCILER_ROLE>",
    "<REPORT_METHOD_AUTHORITY_ROLE>",
    "<EVIDENCE_RECORDER_ROLE>",
    "<EVIDENCE_CHECKER_ROLE>",
    "<TRAINING_FACILITATOR_ROLE>",
    "<CREDENTIAL_CUSTODIAN_ROLE>",
    "<CREDENTIAL_CHECKER_ROLE>",
    "<BRAND_RELEASE_APPROVER_ROLE>",
}

CROSS_PACK_ROLE_FILES = {
    "training": (
        Path("docs/training/README.md"),
        Path("docs/training/operator-procedures.md"),
    ),
    "pilot operations": (Path("docs/pilot-operations/operations-pack.md"),),
}

REQUIRED_CROSS_PACK_SEPARATION_ROLES = {
    "<INCIDENT_COMMANDER_ROLE>",
    "<SECURITY_OWNER_ROLE>",
    "<MONEY_MAKER_ROLE>",
    "<MONEY_CHECKER_ROLE>",
    "<MONEY_RECONCILER_ROLE>",
}

BACKUP_FIELDS = {
    "Scope": "`<BACKUP_SCOPE — OWNER APPROVAL REQUIRED>`",
    "Cadence": "`<BACKUP_CADENCE — OWNER APPROVAL REQUIRED>`",
    "Schedule authority": (
        "`<OPERATIONS_OWNER_ROLE>` — assignment and approval required"
    ),
    "Retention source": (
        "`<RETENTION_SOURCE — EXT-LEGAL-PRIVACY AND "
        "EXT-EVIDENCE-POLICY APPROVAL REQUIRED>`"
    ),
    "Protected evidence pointer": "`<PROTECTED_EVIDENCE_POINTER>`",
    "Recovery verification evidence": (
        "`<RECOVERY_VERIFICATION_EVIDENCE — APPROVED ISOLATED RESTORE REQUIRED>`"
    ),
    "Approval state": "`<NOT APPROVED — EXTERNAL OWNER APPROVAL REQUIRED>`",
}

RACI_WORKSTREAMS = {
    "System documentation index",
    "Release and recovery",
    "Training",
    "Privacy and DSR",
    "Money preparation",
    "Reporting",
    "Incident response",
    "Credential custody",
    "Support and escalation",
    "Brand/release acceptance",
}

SUPPORT_FUNCTIONS = {
    "Intake and record hygiene",
    "Operational triage",
    "Incident command",
    "Security and custody",
    "Privacy/legal",
    "Money",
    "Reporting/method",
}

NOT_PERFORMED_ACTIVITIES = {
    "Handover",
    "Rehearsal",
    "Controlled pilot",
    "Owner/client acceptance",
    "Credential transfer",
    "Live activation",
}

SLA_TARGETS = {
    "Support coverage window",
    "Initial acknowledgement",
    "Triage target",
    "Status-update cadence",
    "Escalation target",
    "Service restoration target",
    "Recovery-point target",
    "Recovery-time target",
    "Availability objective",
    "Evidence-retention target",
}
SLA_PLACEHOLDER = "<PROPOSED — OWNER APPROVAL REQUIRED>"

CUSTODY_FAMILIES = {
    "Release, DNS, and image registry",
    "Database and broker/cache",
    "Object storage, KMS/vault, and scanner",
    "Session signing and application cryptography",
    "Email, phone, and messaging",
    "Payment, disbursement, and settlement",
    "Basemap and aggregate ad platform",
    "Monitoring and error tracking",
    "Backup encryption and off-host recovery",
}

ROADMAP_PLACEMENTS = {
    "Role-scoped admin, advertiser, and screen-on driver PWA workflows": "Integrated capability",
    (
        "Provider-neutral release, backup, isolated restore, and previous-image "
        "recovery preparation"
    ): "Integrated capability",
    "Training and controlled-pilot operations preparation": "Integrated capability",
    "Privacy/DSR fail-closed build controls": "Integrated capability",
    "Provider-neutral money/payout conservation and replay": "Integrated capability",
    (
        "Reproducible Campaign Performance Analysis and bounded CSV/PDF issuance"
    ): "Integrated capability",
    (
        "Client-owned release, external staging, protected credential custody, "
        "live recovery evidence, and approved support ownership"
    ): "External/live activation",
    (
        "Production providers, commercial/statutory values, upload/evidence rules, "
        "privacy/method authority, permits, and brand approval"
    ): "External/live activation",
    (
        "Physical-device install/permission/offline matrix and real-route battery evidence"
    ): "External/live activation",
    (
        "Controlled pilot, stabilization, facilitated rehearsal, credential "
        "handover, and named-owner acceptance"
    ): "External/live activation",
    "Automated driver transfers": "External/live activation",
    "Aggregate geography/time/context ad-platform activation": "External/live activation",
    "Person-level activation": "External/live activation",
    "Native background driver application and store distribution": "Post-MVP idea",
    "Expanded recurring billing": "Post-MVP idea",
    "Edge-AI vehicle and pedestrian counting": "Post-MVP idea",
    "Multi-city optimisation": "Post-MVP idea",
}

EXCLUDED_EXTERNAL_GATE = "EXT-PKG07-OWNER-RELEASE"


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    if marker not in text:
        return ""
    tail = text.split(marker, 1)[1]
    return tail.split("\n## ", 1)[0]


def _table_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        rows.append(cells)
    return rows


def _markdown_slugs(path: Path) -> set[str]:
    slugs: set[str] = set()
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        heading = re.sub(r"<[^>]+>", "", match.group(1))
        heading = re.sub(r"[`*_~]", "", heading).lower()
        slug = re.sub(r"[^\w\- ]", "", heading, flags=re.UNICODE)
        slug = re.sub(r"\s+", "-", slug.strip())
        duplicate = counts.get(slug, 0)
        counts[slug] = duplicate + 1
        slugs.add(f"{slug}-{duplicate}" if duplicate else slug)
    return slugs


def _validate_links(repo_root: Path, handover_files: list[Path]) -> list[str]:
    errors: list[str] = []
    root = repo_root.resolve()
    link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
    for source in handover_files:
        text = source.read_text(encoding="utf-8")
        for raw_target in link_pattern.findall(text):
            target = raw_target.strip().split(maxsplit=1)[0]
            if target.startswith(("http://", "https://", "mailto:")):
                errors.append(f"external link is not provider-neutral: {source}: {target}")
                continue
            path_part, separator, fragment = target.partition("#")
            decoded_path = unquote(path_part)
            resolved = (
                (source.parent / decoded_path).resolve() if decoded_path else source.resolve()
            )
            if not resolved.is_relative_to(root):
                errors.append(f"link escapes repository: {source}: {target}")
                continue
            if not resolved.is_file():
                errors.append(f"broken local link: {source}: {target}")
                continue
            if separator:
                if resolved.suffix.lower() != ".md":
                    errors.append(f"fragment targets non-Markdown file: {source}: {target}")
                    continue
                if unquote(fragment).lower() not in _markdown_slugs(resolved):
                    errors.append(f"broken local fragment: {source}: {target}")
    return errors


def _authoritative_external_states(progress_text: str) -> dict[str, str]:
    section = progress_text.split("## External prerequisite register", 1)[-1]
    section = section.split("### Deferred post-build validation register", 1)[0]
    return dict(
        re.findall(
            r"^\| \*\*(EXT-[A-Z0-9-]+)\*\* \| (PRESENT|MISSING) \|",
            section,
            flags=re.MULTILINE,
        )
    )


def _authoritative_deferred_states(progress_text: str) -> dict[str, str]:
    section = progress_text.split("### Deferred post-build validation register", 1)[-1]
    section = section.split("\n## ", 1)[0]
    return {
        gate: state.strip()
        for gate, state in re.findall(
            r"^\| \*\*(DV-[A-Z0-9-]+)\*\* \| ([^|]+) \|",
            section,
            flags=re.MULTILINE,
        )
    }


def _validate_external_and_deferred(repo_root: Path, risk_text: str) -> list[str]:
    errors: list[str] = []
    progress_path = repo_root / "docs/progress.md"
    if not progress_path.is_file():
        return ["authoritative docs/progress.md is missing"]
    progress_text = progress_path.read_text(encoding="utf-8")
    authoritative = _authoritative_external_states(progress_text)
    if EXCLUDED_EXTERNAL_GATE not in authoritative:
        errors.append(f"authoritative register lacks {EXCLUDED_EXTERNAL_GATE}")
    expected = dict(authoritative)
    expected.pop(EXCLUDED_EXTERNAL_GATE, None)
    actual = dict(
        re.findall(
            r"^\| (EXT-[A-Z0-9-]+) \| (PRESENT|MISSING) \|",
            _section(risk_text, "Relevant external inputs"),
            flags=re.MULTILINE,
        )
    )
    if actual != expected:
        missing = sorted(expected.keys() - actual.keys())
        extra = sorted(actual.keys() - expected.keys())
        changed = sorted(
            gate for gate in expected.keys() & actual.keys() if expected[gate] != actual[gate]
        )
        errors.append(
            f"external gate parity mismatch (missing={missing}, extra={extra}, changed={changed})"
        )
    if len(expected) != 29 or sum(state == "PRESENT" for state in expected.values()) != 2:
        errors.append(
            "authoritative relevant external set is not 29 rows with exactly two PRESENT states"
        )
    if "deliberately excluded" not in risk_text or EXCLUDED_EXTERNAL_GATE not in risk_text:
        errors.append(f"historical exclusion reason is missing for {EXCLUDED_EXTERNAL_GATE}")

    expected_deferred = _authoritative_deferred_states(progress_text)
    actual_deferred = {
        gate: state.strip()
        for gate, state in re.findall(
            r"^\| (DV-[A-Z0-9-]+) \| ([^|]+) \|",
            _section(risk_text, "Deferred validation"),
            flags=re.MULTILINE,
        )
    }
    if actual_deferred != expected_deferred:
        errors.append(
            "deferred validation parity mismatch "
            f"(expected={expected_deferred}, actual={actual_deferred})"
        )
    if len(expected_deferred) != 3:
        errors.append("authoritative deferred register does not contain exactly three rows")
    return errors


def _validate_roles(roles_text: str, support_text: str, credential_text: str) -> list[str]:
    errors: list[str] = []
    registry_rows = _table_rows(_section(roles_text, "Role registry"))[1:]
    actual_roles = {row[0].strip("`") for row in registry_rows if row}
    if actual_roles != ROLE_PLACEHOLDERS:
        errors.append(
            "role registry mismatch "
            f"(missing={sorted(ROLE_PLACEHOLDERS - actual_roles)}, "
            f"extra={sorted(actual_roles - ROLE_PLACEHOLDERS)})"
        )

    raci_rows = _table_rows(_section(roles_text, "RACI workstream skeleton"))[1:]
    actual_workstreams = {row[0] for row in raci_rows if row}
    if actual_workstreams != RACI_WORKSTREAMS:
        errors.append(
            "RACI workstream mismatch "
            f"(missing={sorted(RACI_WORKSTREAMS - actual_workstreams)}, "
            f"extra={sorted(actual_workstreams - RACI_WORKSTREAMS)})"
        )
    for row in raci_rows:
        if len(row) < 6:
            errors.append(f"malformed RACI row: {row}")
            continue
        for cell in row[1:5]:
            values = [part.strip().strip("`") for part in cell.split(",")]
            if not values or any(value not in ROLE_PLACEHOLDERS for value in values):
                errors.append(f"RACI role cell is not placeholder-only: {cell}")

    support_rows = _table_rows(_section(support_text, "Support ownership placeholders"))[1:]
    actual_support_functions = {row[0] for row in support_rows if row}
    if actual_support_functions != SUPPORT_FUNCTIONS:
        errors.append(
            "support function mismatch "
            f"(missing={sorted(SUPPORT_FUNCTIONS - actual_support_functions)}, "
            f"extra={sorted(actual_support_functions - SUPPORT_FUNCTIONS)})"
        )
    for row in support_rows:
        if len(row) < 3 or row[1].strip("`") not in ROLE_PLACEHOLDERS:
            errors.append(f"support owner cell is not placeholder-only: {row}")

    custody_rows = _table_rows(_section(credential_text, "Custody-family inventory skeleton"))[1:]
    custody_families = {row[0] for row in custody_rows if row}
    if custody_families != CUSTODY_FAMILIES:
        errors.append(
            "credential custody family mismatch "
            f"(missing={sorted(CUSTODY_FAMILIES - custody_families)}, "
            f"extra={sorted(custody_families - CUSTODY_FAMILIES)})"
        )
    for row in custody_rows:
        if len(row) < 5:
            errors.append(f"malformed custody row: {row}")
            continue
        for cell in row[1:4]:
            if cell.strip("`") not in ROLE_PLACEHOLDERS:
                errors.append(f"custody role cell is not placeholder-only: {cell}")
        if row[4].strip("`") != "<PROTECTED_INVENTORY_POINTER>":
            errors.append(f"custody inventory cell is not a protected pointer: {row[4]}")
    return errors


def _validate_cross_pack_roles(repo_root: Path, roles_text: str) -> list[str]:
    errors: list[str] = []
    registry_rows = _table_rows(_section(roles_text, "Role registry"))[1:]
    canonical = {row[0].strip("`") for row in registry_rows if row}
    role_pattern = re.compile(r"<[A-Z0-9_-]+_ROLE>")
    for pack, relative_paths in CROSS_PACK_ROLE_FILES.items():
        texts: list[str] = []
        for relative_path in relative_paths:
            path = repo_root / relative_path
            if not path.is_file():
                errors.append(f"{pack} role source is missing: {relative_path}")
                continue
            texts.append(path.read_text(encoding="utf-8"))
        documented = set(role_pattern.findall("\n".join(texts)))
        unknown = sorted(documented - canonical)
        missing = sorted(REQUIRED_CROSS_PACK_SEPARATION_ROLES - documented)
        if unknown:
            errors.append(f"{pack} uses non-canonical role placeholders: {unknown}")
        if missing:
            errors.append(f"{pack} lacks required separation roles: {missing}")
    return errors


def _validate_backup(backup_text: str) -> list[str]:
    errors: list[str] = []
    rows = _table_rows(_section(backup_text, "Backup schedule preparation fields"))[1:]
    actual = {row[0]: row[1] for row in rows if len(row) == 2}
    if actual != BACKUP_FIELDS:
        changed = sorted(
            field
            for field in BACKUP_FIELDS.keys() & actual.keys()
            if BACKUP_FIELDS[field] != actual[field]
        )
        errors.append(
            "backup schedule field mismatch "
            f"(missing={sorted(BACKUP_FIELDS.keys() - actual.keys())}, "
            f"extra={sorted(actual.keys() - BACKUP_FIELDS.keys())}, "
            f"changed={changed})"
        )
    if "Status: **PREPARATION ONLY**" not in backup_text:
        errors.append("backup schedule lacks PREPARATION ONLY status")
    numeric_schedule = re.search(
        r"\b\d+(?:\.\d+)?\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b",
        backup_text,
        flags=re.IGNORECASE,
    )
    if numeric_schedule:
        errors.append(f"unapproved numeric backup cadence/retention: {numeric_schedule.group(0)}")
    return errors


def _validate_index_and_claims(readme_text: str, all_text: str) -> list[str]:
    errors: list[str] = []
    index_rows = _table_rows(_section(readme_text, "Documentation index"))[1:]
    domains = {row[0] for row in index_rows if row}
    if domains != INDEX_DOMAINS:
        errors.append(
            "documentation index domain mismatch "
            f"(missing={sorted(INDEX_DOMAINS - domains)}, extra={sorted(domains - INDEX_DOMAINS)})"
        )

    activity_rows = dict(
        re.findall(
            r"^\| (Handover|Rehearsal|Controlled pilot|Owner/client acceptance|"
            r"Credential transfer|Live activation) \| ([^|]+) \|$",
            readme_text,
            flags=re.MULTILINE,
        )
    )
    if set(activity_rows) != NOT_PERFORMED_ACTIVITIES or any(
        state.strip() != "NOT PERFORMED" for state in activity_rows.values()
    ):
        errors.append("canonical PREPARATION ONLY activity states are missing or changed")

    false_claim_patterns = {
        "affirmative completion/live claim": re.compile(
            r"\b(?:handover|rehearsal|controlled pilot|owner/client acceptance|"
            r"credential transfer|live activation|production)\s+"
            r"(?:is|was|has been)\s+(?:complete|completed|performed|accepted|approved|live)\b",
            flags=re.IGNORECASE,
        ),
        "affirmative completion/live claim (finished form)": re.compile(
            r"\b(?:handover|rehearsal|controlled pilot|owner/client acceptance|"
            r"credential transfer|live activation)\s+"
            r"(?:finished|completed|concluded)(?:\s+successfully)?\b",
            flags=re.IGNORECASE,
        ),
        "affirmative credential-transfer claim": re.compile(
            r"\bcredentials?\s+(?:have|has|were|was)\s+(?:been\s+)?transferred\b",
            flags=re.IGNORECASE,
        ),
        "acceptance attribution": re.compile(r"\baccepted by\b", flags=re.IGNORECASE),
        "completed pilot claim": re.compile(
            r"\bpilot\s+(?:is\s+)?completed\b|"
            r"\b(?:the\s+)?controlled pilot\s+(?:ran|operated)\s+live\b",
            flags=re.IGNORECASE,
        ),
    }
    for label, pattern in false_claim_patterns.items():
        match = pattern.search(all_text)
        if match:
            errors.append(f"{label}: {match.group(0)}")
    return errors


def _validate_sla(support_text: str) -> list[str]:
    errors: list[str] = []
    sla_section = _section(support_text, "Proposed SLA fields")
    rows = _table_rows(sla_section)[1:]
    actual_targets = {row[0] for row in rows if row}
    if actual_targets != SLA_TARGETS:
        errors.append(
            "SLA target mismatch "
            f"(missing={sorted(SLA_TARGETS - actual_targets)}, "
            f"extra={sorted(actual_targets - SLA_TARGETS)})"
        )
    for row in rows:
        if len(row) != 2 or row[1].strip("`") != SLA_PLACEHOLDER:
            errors.append(f"SLA target is not proposed/owner-approval placeholder-only: {row}")
    numeric_target = re.search(
        r"\b\d+(?:\.\d+)?\s*(?:milliseconds?|ms|seconds?|minutes?|hours?|days?|weeks?|months?|%)\b",
        support_text,
        flags=re.IGNORECASE,
    )
    if numeric_target:
        errors.append(f"unapproved numeric SLA/SLO target: {numeric_target.group(0)}")
    return errors


def _validate_sensitive_values(all_text: str) -> list[str]:
    errors: list[str] = []
    patterns = {
        "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
        "provider secret token": r"\bsk-(?:live|prod|test)[-_A-Za-z0-9]{6,}\b",
        "credential-bearing URL": r"\b[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s/@]+@",
        "account identifier": r"\bacct_[A-Za-z0-9]{6,}\b",
        "contact email": r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "contact phone": r"(?<![A-Z0-9-])\+?\d[\d ()-]{7,}\d(?![A-Z0-9-])",
        "secret/account assignment": (
            r"(?im)^\s*(?:api[_ -]?key|secret|password|token|account[_ -]?(?:id|number)|"
            r"bank[_ -]?account|tenant[_ -]?id|subscription[_ -]?id|username|"
            r"private[_ -]?endpoint|dsn)\s*[:=]\s*[\"']?"
            r"(?!<|NOT\b|MISSING\b|PRESENT\b|PROPOSED\b)\S+"
        ),
    }
    for label, raw_pattern in patterns.items():
        match = re.search(
            raw_pattern, all_text, flags=re.IGNORECASE if "(?" not in raw_pattern else 0
        )
        if match:
            errors.append(f"unsafe {label}: {match.group(0)}")
    return errors


def _validate_roadmap(roadmap_text: str) -> list[str]:
    errors: list[str] = []
    rows = _table_rows(_section(roadmap_text, "Roadmap lanes"))[1:]
    placements = {row[1]: row[0] for row in rows if len(row) >= 4}
    if placements != ROADMAP_PLACEMENTS or len(rows) != len(ROADMAP_PLACEMENTS):
        errors.append(
            "roadmap capability set mismatch "
            f"(missing={sorted(ROADMAP_PLACEMENTS.keys() - placements.keys())}, "
            f"extra={sorted(placements.keys() - ROADMAP_PLACEMENTS.keys())})"
        )
    for capability, expected_lane in ROADMAP_PLACEMENTS.items():
        if placements.get(capability) != expected_lane:
            errors.append(
                f"roadmap placement mismatch for {capability}: "
                f"expected={expected_lane}, actual={placements.get(capability)}"
            )
    if not any(row and row[0] == "Integrated capability" for row in rows):
        errors.append("roadmap lacks integrated capability evidence")
    future_claim = re.search(
        r"\b(?:will (?:deliver|launch|ship|complete)|committed (?:for|to|by)|delivery date)\b",
        roadmap_text,
        flags=re.IGNORECASE,
    )
    if future_claim:
        errors.append(f"unapproved roadmap commitment: {future_claim.group(0)}")
    return errors


def validate_repository(repo_root: Path) -> list[str]:
    """Return deterministic validation errors for ``repo_root``."""

    repo_root = repo_root.resolve()
    handover_dir = repo_root / "docs/handover"
    if not handover_dir.is_dir():
        return ["docs/handover directory is missing"]
    actual_files = {path.name for path in handover_dir.iterdir() if path.is_file()}
    errors: list[str] = []
    if actual_files != HANDOVER_FILES:
        errors.append(
            "handover artifact set mismatch "
            f"(missing={sorted(HANDOVER_FILES - actual_files)}, "
            f"extra={sorted(actual_files - HANDOVER_FILES)})"
        )
    missing = HANDOVER_FILES - actual_files
    if missing:
        return errors

    paths = [handover_dir / name for name in sorted(HANDOVER_FILES)]
    texts = {path.name: path.read_text(encoding="utf-8") for path in paths}
    all_text = "\n".join(texts[name] for name in sorted(texts))

    validator_path = repo_root / "scripts/validate_w404b_handover_preparation.py"
    documented_command = "python3 scripts/validate_w404b_handover_preparation.py"
    if not validator_path.is_file() or documented_command not in texts["README.md"]:
        errors.append("documented validator command or target is missing")

    errors.extend(_validate_links(repo_root, paths))
    errors.extend(_validate_index_and_claims(texts["README.md"], all_text))
    errors.extend(
        _validate_roles(
            texts["roles-and-responsibilities.md"],
            texts["support-sla-escalation.md"],
            texts["credential-handover-checklist.md"],
        )
    )
    errors.extend(_validate_cross_pack_roles(repo_root, texts["roles-and-responsibilities.md"]))
    errors.extend(_validate_backup(texts["backup-schedule.md"]))
    errors.extend(_validate_sla(texts["support-sla-escalation.md"]))
    errors.extend(
        _validate_external_and_deferred(repo_root, texts["external-and-deferred-risks.md"])
    )
    errors.extend(_validate_sensitive_values(all_text))
    errors.extend(_validate_roadmap(texts["post-mvp-roadmap.md"]))
    return sorted(set(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root to validate (defaults to this script's repository)",
    )
    args = parser.parse_args(argv)
    errors = validate_repository(args.repo_root)
    if errors:
        print("W4-04B handover preparation audit: FAIL", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        "W4-04B handover preparation audit: PASS "
        "(7 files, 29 external gates, 3 deferred validations)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

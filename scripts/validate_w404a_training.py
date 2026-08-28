#!/usr/bin/env python3
"""Audit W4-04A provider-neutral training preparation."""

from __future__ import annotations

import argparse
import re
import shlex
import shutil
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import unquote

TRAINING_PATHS = (
    Path("docs/training/README.md"),
    Path("docs/training/role-task-inventories.md"),
    Path("docs/training/operator-procedures.md"),
)
ROLE_INVENTORY_PATH = Path("docs/training/role-task-inventories.md")
PROCEDURES_PATH = Path("docs/training/operator-procedures.md")
PROGRESS_PATH = Path("docs/progress.md")
ROLE_REGISTRY_PATH = Path("docs/handover/roles-and-responsibilities.md")
CHECKLIST_ID = "W4-04A"
ROLES = ("admin", "advertiser", "driver")
DOMAINS = {
    "privacy": "Privacy / DSR",
    "kyc": "KYC and private files",
    "fraud": "Fraud review",
    "payout": "Payout operations",
    "reporting": "Reporting",
    "incidents": "Incidents",
}
PROCEDURE_SUBSECTIONS = (
    "Authorized role and entry point",
    "Prerequisites",
    "Ordered actions",
    "Retry identity",
    "Expected safe result",
    "Stop conditions and escalation",
    "Synthetic rehearsal note",
)
REQUIRED_NEGATIVE_STATEMENT = (
    "W4-04A remains incomplete: facilitated rehearsal, user acceptance, "
    "and live operation have not occurred."
)
REQUIRED_PLACEHOLDERS = (
    "<TRAINING_FACILITATOR_ROLE>",
    "<OPERATIONS_OWNER_ROLE>",
    "<PRIVACY_DECISION_ROLE>",
    "<MONEY_MAKER_ROLE>",
    "<MONEY_CHECKER_ROLE>",
    "<MONEY_RECONCILER_ROLE>",
    "<INCIDENT_COMMANDER_ROLE>",
    "<SECURITY_OWNER_ROLE>",
    "<REPORT_METHOD_AUTHORITY_ROLE>",
)
REQUIRED_COMMANDS = (
    "python3 scripts/validate_w404a_training.py",
    "python3 scripts/run_w403b_synthetic_journey.py",
    "bash scripts/rehearse_w403a.sh",
)
PROHIBITED_CLAIMS = (
    re.compile(r"\bW4-04A\s+(?:is\s+)?(?:DONE|complete|completed)\b", re.IGNORECASE),
    re.compile(
        r"\bfacilitated rehearsal\s+(?:is\s+|was\s+|has been\s+)?"
        r"(?:complete|completed|passed|approved|recorded)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\buser acceptance\s+(?:is\s+|was\s+|has been\s+)?"
        r"(?:complete|completed|passed|approved|recorded)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\blive (?:operation|deployment|pilot)\s+"
        r"(?:is\s+|was\s+|has been\s+)?"
        r"(?:complete|completed|passed|approved|occurred|performed)\b",
        re.IGNORECASE,
    ),
    re.compile(r"^Approved by:\s*(?!<)\S.+$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:Named )?operations owner:\s*(?!<)\S.+$", re.IGNORECASE | re.MULTILINE),
)
LOCAL_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
REPOSITORY_COMMAND_RE = re.compile(r"Repository command:\s*`([^`]+)`")
ROLE_PLACEHOLDER_RE = re.compile(r"<[A-Z0-9_-]+_ROLE>")


def _read(path: Path, overrides: Mapping[Path, str]) -> str:
    return overrides.get(path.resolve(), path.read_text(encoding="utf-8"))


def _inside_repo(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _heading_slugs(text: str) -> set[str]:
    slugs: set[str] = set()
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*$", text, flags=re.MULTILINE):
        slug = heading.strip().lower()
        slug = re.sub(r"[`*_{}\[\]()]", "", slug)
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s-]+", "-", slug).strip("-")
        slugs.add(slug)
    return slugs


def _frontend_page_routes(root: Path) -> set[str]:
    app_root = root / "frontend" / "src" / "app"
    routes: set[str] = set()
    for page in app_root.rglob("page.tsx"):
        parts: list[str] = []
        for part in page.parent.relative_to(app_root).parts:
            if part.startswith("(") and part.endswith(")"):
                continue
            if part.startswith("[") and part.endswith("]"):
                part = "{" + part[1:-1] + "}"
            parts.append(part)
        routes.add("/" + "/".join(parts) if parts else "/")
    return routes


def _role_inventory_errors(root: Path, text: str) -> list[str]:
    errors: list[str] = []
    shipped_routes = _frontend_page_routes(root)
    seen_roles: set[str] = set()
    row_count = 0

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.startswith("|"):
            continue
        columns = [column.strip() for column in line.strip().strip("|").split("|")]
        if len(columns) != 5 or columns[0] not in ROLES:
            continue
        role, route, permitted, boundary, source = columns
        route = route.strip("`")
        seen_roles.add(role)
        row_count += 1
        if not permitted or not boundary or not source:
            errors.append(f"{ROLE_INVENTORY_PATH}:{line_number}: incomplete role inventory row")
        if route != f"/{role}" and not route.startswith(f"/{role}/"):
            errors.append(
                f"{ROLE_INVENTORY_PATH}:{line_number}: role {role} route {route} "
                "crosses its role boundary"
            )
        if route not in shipped_routes:
            errors.append(
                f"{ROLE_INVENTORY_PATH}:{line_number}: UI route does not resolve: {route}"
            )
        if not LOCAL_LINK_RE.search(source):
            errors.append(
                f"{ROLE_INVENTORY_PATH}:{line_number}: role inventory source is not a local link"
            )

    for role in ROLES:
        if role not in seen_roles:
            errors.append(f"missing role coverage: {role}")
    if row_count < 3:
        errors.append("role inventory contains too few task rows")
    return errors


def _procedure_errors(text: str) -> list[str]:
    errors: list[str] = []
    for domain, heading in DOMAINS.items():
        match = re.search(
            rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)",
            text,
            flags=re.MULTILINE,
        )
        if match is None:
            errors.append(f"missing operator domain: {domain}")
            continue
        section = match.group(1)
        for subsection in PROCEDURE_SUBSECTIONS:
            if re.search(rf"^### {re.escape(subsection)}\s*$", section, flags=re.MULTILINE) is None:
                errors.append(
                    f"operator domain {domain}: missing required subsection '{subsection}'"
                )
    return errors


def _markdown_section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    if marker not in text:
        return ""
    tail = text.split(marker, 1)[1]
    return tail.split("\n## ", 1)[0]


def _authoritative_checklist_gate_states(
    progress_text: str,
    checklist_id: str,
) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    marker = "## External prerequisite register"
    if progress_text.count(marker) != 1:
        return {}, ["authoritative progress source lacks one external register"]
    register = progress_text.split(marker, 1)[1]
    register = register.split("### Deferred post-build validation register", 1)[0]
    pairs = re.findall(
        r"^\| \*\*(EXT-[A-Z0-9-]+)\*\* \| (PRESENT|MISSING) \|",
        register,
        flags=re.MULTILINE,
    )
    if not pairs or len(pairs) != len({gate for gate, _ in pairs}):
        errors.append("authoritative external register is empty or contains duplicate IDs")
    external_states = dict(pairs)

    rows = [
        line
        for line in progress_text.splitlines()
        if line.startswith("|") and f"**{checklist_id} —" in line
    ]
    if len(rows) != 1:
        errors.append(f"authoritative progress source lacks one {checklist_id} checklist row")
        return {}, errors
    cells = [cell.strip() for cell in rows[0].strip().strip("|").split("|")]
    dependency_cell = cells[-1] if cells else ""
    match = re.search(r"external-live:\s*(.+)$", dependency_cell)
    if match is None:
        errors.append(f"authoritative {checklist_id} row lacks external-live dependencies")
        return {}, errors
    gates = [gate.strip().strip("`") for gate in match.group(1).split(",")]
    if not gates or any(not re.fullmatch(r"EXT-[A-Z0-9-]+", gate) for gate in gates):
        errors.append(f"authoritative {checklist_id} gate list is malformed")
        return {}, errors
    if len(gates) != len(set(gates)):
        errors.append(f"authoritative {checklist_id} gate list contains duplicate IDs")
    missing_states = sorted(set(gates) - external_states.keys())
    if missing_states:
        errors.append(
            f"authoritative {checklist_id} gates lack external-register state: {missing_states}"
        )
    return (
        {gate: external_states[gate] for gate in gates if gate in external_states},
        errors,
    )


def _gate_parity_errors(
    root: Path,
    readme_text: str,
    overrides: Mapping[Path, str],
) -> list[str]:
    progress_path = (root / PROGRESS_PATH).resolve()
    if not progress_path.is_file():
        return ["authoritative docs/progress.md is missing"]
    expected, errors = _authoritative_checklist_gate_states(
        _read(progress_path, overrides), CHECKLIST_ID
    )
    actual_pairs = re.findall(
        r"^\| (EXT-[A-Z0-9-]+) \| (PRESENT|MISSING) \|$",
        _markdown_section(readme_text, "W4-04A external/live gate snapshot"),
        flags=re.MULTILINE,
    )
    if len(actual_pairs) != len({gate for gate, _ in actual_pairs}):
        errors.append("training gate snapshot contains duplicate IDs")
    actual = dict(actual_pairs)
    if actual != expected:
        errors.append(
            "training gate parity mismatch "
            f"(expected={expected}, actual={actual})"
        )
    return errors


def _canonical_role_errors(
    root: Path,
    combined_text: str,
    overrides: Mapping[Path, str],
) -> list[str]:
    registry_path = (root / ROLE_REGISTRY_PATH).resolve()
    if not registry_path.is_file():
        return ["canonical handover role registry is missing"]
    registry_text = _read(registry_path, overrides)
    canonical = set(
        ROLE_PLACEHOLDER_RE.findall(_markdown_section(registry_text, "Role registry"))
    )
    if not canonical:
        return ["canonical handover role registry is empty"]
    documented = set(ROLE_PLACEHOLDER_RE.findall(combined_text))
    unknown = sorted(documented - canonical)
    missing = sorted(set(REQUIRED_PLACEHOLDERS) - documented)
    errors: list[str] = []
    if unknown:
        errors.append(f"training role placeholders are not canonical: {unknown}")
    if missing:
        errors.append(f"training role separation placeholders are missing: {missing}")
    return errors


def _local_link_errors(
    root: Path,
    documents: Mapping[Path, str],
    overrides: Mapping[Path, str],
) -> list[str]:
    errors: list[str] = []
    for document, text in documents.items():
        for raw_target in LOCAL_LINK_RE.findall(text):
            target = raw_target.strip().strip("<>")
            if target.startswith(("http://", "https://", "mailto:")):
                errors.append(f"{document.relative_to(root)}: non-local training link: {target}")
                continue
            path_text, separator, fragment = target.partition("#")
            resolved = (document.parent / unquote(path_text)).resolve()
            if not _inside_repo(resolved, root) or not resolved.is_file():
                errors.append(
                    f"{document.relative_to(root)}: broken local link: {target}"
                )
                continue
            if separator and fragment:
                linked_text = _read(resolved, overrides)
                if unquote(fragment).lower() not in _heading_slugs(linked_text):
                    errors.append(
                        f"{document.relative_to(root)}: broken local link anchor: {target}"
                    )
    return errors


def _command_errors(root: Path, documents: Mapping[Path, str]) -> list[str]:
    errors: list[str] = []
    commands: list[tuple[Path, str]] = []
    for document, text in documents.items():
        commands.extend((document, command) for command in REPOSITORY_COMMAND_RE.findall(text))

    command_values = {command for _, command in commands}
    for required in REQUIRED_COMMANDS:
        if required not in command_values:
            errors.append(f"missing required repository command: {required}")

    for document, command in commands:
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            errors.append(f"{document.relative_to(root)}: invalid repository command: {exc}")
            continue
        if len(parts) != 2 or parts[0] not in {"python3", "bash"}:
            errors.append(
                f"{document.relative_to(root)}: unsupported repository command shape: {command}"
            )
            continue
        if shutil.which(parts[0]) is None:
            errors.append(
                f"{document.relative_to(root)}: repository command interpreter is unavailable: "
                f"{parts[0]}"
            )
            continue
        target = (root / parts[1]).resolve()
        expected_suffix = ".sh" if parts[0] == "bash" else ".py"
        if (
            not _inside_repo(target, root)
            or not target.is_file()
            or target.suffix != expected_suffix
        ):
            errors.append(
                f"{document.relative_to(root)}: repository command target does not exist "
                f"or has the wrong type: {parts[1]}"
            )
    return errors


def _claim_errors(combined_text: str) -> list[str]:
    errors: list[str] = []
    if REQUIRED_NEGATIVE_STATEMENT not in combined_text:
        errors.append("missing required negative gate statement")
    for pattern in PROHIBITED_CLAIMS:
        for match in pattern.finditer(combined_text):
            errors.append(f"prohibited completion or live claim: {match.group(0)}")
    return errors


def audit_repository(
    repo_root: Path,
    document_overrides: Mapping[Path, str] | None = None,
) -> list[str]:
    root = repo_root.resolve()
    overrides = {
        path.resolve(): text for path, text in (document_overrides or {}).items()
    }
    documents: dict[Path, str] = {}
    errors: list[str] = []

    for relative_path in TRAINING_PATHS:
        path = (root / relative_path).resolve()
        if not path.is_file():
            errors.append(f"missing training artifact: {relative_path}")
            continue
        documents[path] = _read(path, overrides)

    if errors:
        return errors

    inventory = documents[(root / ROLE_INVENTORY_PATH).resolve()]
    procedures = documents[(root / PROCEDURES_PATH).resolve()]
    errors.extend(_role_inventory_errors(root, inventory))
    errors.extend(_procedure_errors(procedures))
    errors.extend(_local_link_errors(root, documents, overrides))
    errors.extend(_command_errors(root, documents))
    combined_text = "\n".join(documents.values())
    errors.extend(_claim_errors(combined_text))
    errors.extend(_canonical_role_errors(root, combined_text, overrides))
    errors.extend(
        _gate_parity_errors(
            root,
            documents[(root / TRAINING_PATHS[0]).resolve()],
            overrides,
        )
    )
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to this script's checkout)",
    )
    args = parser.parse_args()
    errors = audit_repository(args.root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        "W4-04A training audit passed: preparation only; "
        "live gates remain unresolved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

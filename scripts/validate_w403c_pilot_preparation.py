#!/usr/bin/env python3
"""Audit the provider-neutral W4-03C-P1 preparation pack."""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs" / "pilot-operations"
PROGRESS = Path("docs/progress.md")
ROLE_REGISTRY = Path("docs/handover/roles-and-responsibilities.md")
CHECKLIST_ID = "W4-03C"

DOCUMENTS = ("README.md", "operations-pack.md", "synthetic-exercises.md")
DOMAINS = (
    "telemetry-readiness",
    "rollback-recovery",
    "payout-replay",
    "report-replay",
    "incident-escalation",
    "evidence-chain",
)
REQUIRED_LABELS = (
    "Authoritative sources:",
    "Authoritative state:",
    "Roles:",
    "Stop criteria:",
    "Evidence fields:",
    "Ordered preparation procedure:",
    "Do not:",
)
DOMAIN_FIELDS = {
    "telemetry-readiness": (
        "readiness_status",
        "worker_heartbeat_age",
        "queue_depth",
        "threshold_comparator",
        "threshold_window",
        "protected_evidence_pointer",
    ),
    "rollback-recovery": (
        "current_revision",
        "previous_revision",
        "compatibility_evidence_pointer",
        "traffic_state_before",
        "traffic_state_after",
        "rollback_outcome",
    ),
    "payout-replay": (
        "batch_id",
        "line_id",
        "idempotency_key",
        "provider_transfer_reference",
        "instruction_sha256",
        "amount",
        "currency",
        "ledger_finality_after",
        "maker_id",
        "checker_id",
        "reconciler_id",
        "external_provider_actions",
    ),
    "report-replay": (
        "request_id",
        "request_fingerprint",
        "measurement_run_id",
        "issuance_version",
        "reissue_of_id",
        "csv_artifact_id",
        "csv_sha256",
        "pdf_artifact_id",
        "pdf_sha256",
    ),
    "incident-escalation": (
        "discovery_time_utc",
        "discovery_source",
        "systems",
        "purposes",
        "data_classes",
        "subject_estimate",
        "containment",
        "decisions",
        "decision_actors",
        "notifications_considered",
        "recovery_evidence",
        "closure_decision",
        "protected_store_pointer",
    ),
    "evidence-chain": (
        "source_authority",
        "command_or_entry_point",
        "exit_code",
        "expected_result",
        "observed_result",
        "before_sha256",
        "after_sha256",
        "recorder_id",
        "checker_id",
        "protected_store_pointer",
        "redaction_review",
    ),
}
EXERCISE_NODES = {
    "telemetry-readiness": (
        "tests/test_health.py::test_api_ready_without_database_url_is_deterministic",
        "tests/test_worker_jobs.py::test_sweep_isolates_per_trip_failures_and_continues",
    ),
    "rollback-recovery": (
        "tests/test_w403a_release_preparation.py::test_compatibility_evidence_binds_previous_image_and_forward_schema",
        "tests/test_w403a_release_preparation.py::test_failure_cleanup_stops_an_open_edge",
        "tests/test_w403a_release_preparation.py::test_release_scripts_never_run_alembic_downgrade",
    ),
    "payout-replay": (
        "tests/test_payout_reconciliation.py::test_line_level_partial_reconciliation_retry_and_paid_finality",
        "tests/test_payout_batches.py::test_submission_fails_closed_without_approved_provider",
    ),
    "report-replay": (
        "tests/test_report_issuances.py::test_lost_response_replay_does_not_recompose_mutable_latest_projection",
        "tests/test_report_issuances.py::test_partial_storage_failure_exposes_no_artifact_and_retry_recovers_pair",
    ),
    "incident-escalation": (
        "tests/test_privacy_operating_model.py::test_privacy_register_is_fail_closed_and_complete",
        "tests/test_privacy_operating_model.py::test_provider_notice_breach_and_dpia_registers_do_not_claim_approval",
    ),
    "evidence-chain": (
        "tests/test_data_subject_requests.py::test_admin_access_request_inventories_and_closes_all_locations",
        "tests/test_data_subject_requests.py::test_completion_requires_every_store",
    ),
}
ROLE_PLACEHOLDER_RE = re.compile(r"<[A-Z0-9_-]+_ROLE>")
REQUIRED_SEPARATION_ROLES = {
    "<INCIDENT_COMMANDER_ROLE>",
    "<SECURITY_OWNER_ROLE>",
    "<MONEY_MAKER_ROLE>",
    "<MONEY_CHECKER_ROLE>",
    "<MONEY_RECONCILER_ROLE>",
}
PROHIBITED_CLAIMS = (
    re.compile(r"\bW4-03C (?:is )?DONE\b", re.IGNORECASE),
    re.compile(r"\bcontrolled pilot (?:is |was )?(?:complete|completed|passed)\b", re.IGNORECASE),
    re.compile(r"\blive telemetry (?:was )?captured\b", re.IGNORECASE),
    re.compile(r"\blive payment (?:was )?executed\b", re.IGNORECASE),
    re.compile(r"\bdeployed successfully\b", re.IGNORECASE),
    re.compile(r"\buser acceptance passed\b", re.IGNORECASE),
    re.compile(r"\brehearsal completed\b", re.IGNORECASE),
)


def _sections(content: str) -> dict[str, str]:
    matches = list(re.finditer(r"^## Domain: ([a-z-]+)\s*$", content, re.MULTILINE))
    return {
        match.group(1): content[match.start() : matches[index + 1].start()]
        if index + 1 < len(matches)
        else content[match.start() :]
        for index, match in enumerate(matches)
    }


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
    progress_text_override: str | None,
) -> list[str]:
    progress_path = root / PROGRESS
    if progress_text_override is None and not progress_path.is_file():
        return ["authoritative docs/progress.md is missing"]
    progress_text = (
        progress_text_override
        if progress_text_override is not None
        else progress_path.read_text(encoding="utf-8")
    )
    expected, errors = _authoritative_checklist_gate_states(progress_text, CHECKLIST_ID)
    actual_pairs = re.findall(
        r"^\| (EXT-[A-Z0-9-]+) \| (PRESENT|MISSING) \|$",
        _markdown_section(readme_text, "W4-03C external/live gate snapshot"),
        flags=re.MULTILINE,
    )
    if len(actual_pairs) != len({gate for gate, _ in actual_pairs}):
        errors.append("pilot gate snapshot contains duplicate IDs")
    actual = dict(actual_pairs)
    if actual != expected:
        errors.append(f"pilot gate parity mismatch (expected={expected}, actual={actual})")
    return errors


def _canonical_role_errors(root: Path, operations_text: str) -> list[str]:
    registry_path = root / ROLE_REGISTRY
    if not registry_path.is_file():
        return ["canonical handover role registry is missing"]
    registry_text = registry_path.read_text(encoding="utf-8")
    canonical = set(
        ROLE_PLACEHOLDER_RE.findall(_markdown_section(registry_text, "Role registry"))
    )
    if not canonical:
        return ["canonical handover role registry is empty"]
    documented = set(ROLE_PLACEHOLDER_RE.findall(operations_text))
    errors: list[str] = []
    unknown = sorted(documented - canonical)
    missing = sorted(REQUIRED_SEPARATION_ROLES - documented)
    if unknown:
        errors.append(f"pilot role placeholders are not canonical: {unknown}")
    if missing:
        errors.append(f"pilot role separation placeholders are missing: {missing}")
    return errors


def _check_links(root: Path, logical_path: Path, content: str) -> list[str]:
    errors: list[str] = []
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        clean_target = target.split("#", 1)[0]
        resolved = (logical_path.parent / clean_target).resolve()
        if root.resolve() not in (resolved, *resolved.parents) or not resolved.exists():
            errors.append(f"{logical_path.name}: broken local link: {target}")
    return errors


def _check_pytest_node(root: Path, node: str) -> str | None:
    path_text, separator, node_name = node.partition("::")
    path = root / path_text
    if not separator or not path.is_file():
        return f"broken local command target: {node}"
    if not re.search(
        rf"^def {re.escape(node_name)}\(", path.read_text(encoding="utf-8"), re.MULTILINE
    ):
        return f"missing pytest node: {node}"
    return None


def _check_commands(root: Path, content: str) -> list[str]:
    errors: list[str] = []
    commands = re.findall(r"```sh\n(.*?)\n```", content, re.DOTALL)
    for block in commands:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) != 1:
            errors.append("command block must contain one exact local command")
            continue
        try:
            tokens = shlex.split(lines[0])
        except ValueError:
            errors.append(f"broken local command syntax: {lines[0]}")
            continue
        if tokens[:4] == ["python3", "-m", "pytest", "-q"]:
            if len(tokens) < 5:
                errors.append("pytest command has no node")
                continue
            for node in tokens[4:]:
                error = _check_pytest_node(root, node)
                if error:
                    errors.append(error)
        elif tokens[:1] == ["python3"] and len(tokens) == 2:
            target = root / tokens[1]
            if not target.is_file():
                errors.append(f"broken local command target: {tokens[1]}")
        else:
            errors.append(f"command is not an allowlisted local entry point: {lines[0]}")
    return errors


def validate_pack(
    root: Path = ROOT,
    pack_dir: Path = PACK,
    progress_text_override: str | None = None,
) -> list[str]:
    errors: list[str] = []
    contents: dict[str, str] = {}
    for name in DOCUMENTS:
        path = pack_dir / name
        if not path.is_file():
            errors.append(f"missing document: {name}")
            continue
        content = path.read_text(encoding="utf-8")
        contents[name] = content
        logical_path = root / "docs" / "pilot-operations" / name
        errors.extend(_check_links(root, logical_path, content))
        errors.extend(_check_commands(root, content))
        for claim in PROHIBITED_CLAIMS:
            if claim.search(content):
                errors.append(f"{name}: prohibited completion/live claim: {claim.pattern}")

    readme = contents.get("README.md", "")
    if (
        "W4-03C remains incomplete and externally blocked. No monitored controlled "
        "pilot\nhas been performed."
        not in readme
    ):
        errors.append(
            "README.md: missing truthful W4-03C incomplete/external-block statement"
        )
    errors.extend(_gate_parity_errors(root, readme, progress_text_override))

    operations = contents.get("operations-pack.md", "")
    operation_sections = _sections(operations)
    for domain in DOMAINS:
        section = operation_sections.get(domain)
        if section is None:
            errors.append(f"operations-pack.md: missing domain: {domain}")
            continue
        for label in REQUIRED_LABELS:
            if label not in section:
                errors.append(f"{domain}: missing required label: {label}")
        for field in DOMAIN_FIELDS[domain]:
            if field not in section:
                errors.append(f"{domain}: missing evidence/authority field: {field}")
        if ROLE_PLACEHOLDER_RE.search(section) is None:
            errors.append(f"{domain}: missing canonical role placeholder")

    errors.extend(_canonical_role_errors(root, operations))

    exercises = contents.get("synthetic-exercises.md", "")
    exercise_sections = _sections(exercises)
    for domain in DOMAINS:
        section = exercise_sections.get(domain)
        if section is None:
            errors.append(f"synthetic-exercises.md: missing domain: {domain}")
            continue
        if "Happy command:" not in section or "Stop/failure command:" not in section:
            errors.append(f"{domain}: missing happy or stop/failure exercise")
        for node in EXERCISE_NODES[domain]:
            if node not in section:
                errors.append(f"{domain}: missing required exercise node: {node}")

    return errors


def main() -> int:
    errors = validate_pack()
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "W4-03C-P1 preparation audit PASS — synthetic/local preparation only; "
        "W4-03C remains incomplete and externally blocked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

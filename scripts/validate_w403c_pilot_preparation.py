#!/usr/bin/env python3
"""Audit the provider-neutral W4-03C-P1 preparation pack."""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs" / "pilot-operations"

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
GATE_STATES = {
    "EXT-DISBURSEMENT-PROVIDER": "MISSING",
    "EXT-SETTLEMENT-BANK": "MISSING",
    "EXT-RM2-POLICY": "PRESENT",
    "EXT-STORAGE-PROVIDER": "MISSING",
    "EXT-MALWARE-SCANNER": "MISSING",
    "EXT-KMS-CUSTODY": "MISSING",
    "EXT-PHONE-OPERATOR": "MISSING",
    "EXT-EVIDENCE-POLICY": "MISSING",
    "EXT-LEGAL-PRIVACY": "MISSING",
    "EXT-UPLOAD-POLICY": "MISSING",
    "EXT-PAYMENT-PROVIDER": "MISSING",
    "EXT-BUDGET-POLICY": "MISSING",
    "EXT-Q28-COMPANY": "MISSING",
    "EXT-COMMERCIAL-VALUES": "MISSING",
    "EXT-CAMPAIGN-BUDGET-SCOPE": "MISSING",
    "EXT-BASEMAP": "MISSING",
    "EXT-REPORT-METHOD": "MISSING",
    "EXT-AD-PLATFORM": "MISSING",
    "EXT-RELEASE-ENV": "MISSING",
    "EXT-STAGING-APPROVAL": "MISSING",
    "EXT-PILOT-FACTS": "PRESENT",
    "EXT-PILOT-PERMITS": "MISSING",
    "EXT-OPERATIONS-OWNER": "MISSING",
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


def validate_pack(root: Path = ROOT, pack_dir: Path = PACK) -> list[str]:
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
    if "W4-03C remains `TODO`. No monitored controlled pilot has been performed." not in readme:
        errors.append("README.md: missing truthful W4-03C TODO/no-pilot statement")
    found_gates = {
        gate: state
        for gate, state in re.findall(
            r"^\| (EXT-[A-Z0-9-]+) \| (MISSING|PRESENT) \|$", readme, re.MULTILINE
        )
    }
    if found_gates != GATE_STATES:
        errors.append("README.md: W4-03C external gate states are missing or drifted")

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
        if "<PLACEHOLDER —" not in section:
            errors.append(f"{domain}: missing approval-safe placeholder")

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
        "W4-03C-P1 preparation audit PASS — synthetic/local preparation only; W4-03C remains TODO"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

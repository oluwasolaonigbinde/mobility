from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

from scripts import evaluate_pilot_gates as evaluator

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def authority_texts() -> tuple[str, str, str]:
    return (
        (ROOT / "docs/progress.md").read_text(encoding="utf-8"),
        (ROOT / "docs/architecture.md").read_text(encoding="utf-8"),
        (ROOT / "docs/decisions-log.md").read_text(encoding="utf-8"),
    )


def _snapshot(authority_texts: tuple[str, str, str]) -> evaluator.AuthoritySnapshot:
    return evaluator.parse_authority(*authority_texts)


def _complete_snapshot(
    authority_texts: tuple[str, str, str],
) -> evaluator.AuthoritySnapshot:
    current = _snapshot(authority_texts)
    return evaluator.AuthoritySnapshot(
        checklist_states={name: "DONE" for name in current.checklist_states},
        external_states={name: "PRESENT" for name in current.external_states},
        deferred_states={name: "COMPLETE" for name in current.deferred_states},
        architecture_gates=current.architecture_gates,
    )


def _replace_external_row(
    progress: str, external_id: str, *, state: str, evidence: str
) -> str:
    pattern = re.compile(
        rf"^\| \*\*{re.escape(external_id)}\*\* \| [^|]+ \| ([^|]+) \| [^|]+ \| ([^|]+) \|$",
        re.MULTILINE,
    )
    match = pattern.search(progress)
    assert match is not None
    return (
        progress[: match.start()]
        + f"| **{external_id}** | {state} | {match.group(1).strip()} | {evidence} | "
        + f"{match.group(2).strip()} |"
        + progress[match.end() :]
    )


def test_current_authority_has_exact_ordered_honest_blockers(
    authority_texts: tuple[str, str, str],
) -> None:
    lines = evaluator.evaluate_gates(_snapshot(authority_texts), {})

    assert lines == (
        "G-money: BLOCKED — EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK",
        "G-GPS: BLOCKED — EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, "
        "EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, "
        "EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, DV-PWA-PHYSICAL-MATRIX, "
        "DV-PWA-ROUTE-BATTERY",
        "G-commercial: BLOCKED — EXT-PAYMENT-PROVIDER, EXT-STORAGE-PROVIDER, "
        "EXT-MALWARE-SCANNER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, "
        "EXT-COMMERCIAL-VALUES, EXT-EVIDENCE-POLICY, "
        "EXT-CAMPAIGN-BUDGET-SCOPE, EXT-UPLOAD-POLICY",
        "G-advertiser: BLOCKED — EXT-BASEMAP, EXT-REPORT-METHOD, "
        "EXT-LEGAL-PRIVACY",
        "G-moduleG: BLOCKED — EXT-REPORT-METHOD, EXT-LEGAL-PRIVACY, "
        "EXT-AD-PLATFORM",
        "G-pilot: BLOCKED — EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, "
        "EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, "
        "EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, "
        "EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, "
        "EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, "
        "EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, "
        "EXT-STAGING-APPROVAL, EXT-PILOT-PERMITS, DV-PWA-PHYSICAL-MATRIX, "
        "DV-PWA-ROUTE-BATTERY, DV-STAGING-LIVE",
    )
    assert len(lines) == 6


def test_gate_manifest_matches_architecture_once_and_controls_live_adapter(
    authority_texts: tuple[str, str, str],
) -> None:
    snapshot = _snapshot(authority_texts)

    assert tuple(gate.name for gate in evaluator.GATES) == snapshot.architecture_gates
    assert len(snapshot.architecture_gates) == len(set(snapshot.architecture_gates)) == 6
    commercial = next(gate for gate in evaluator.GATES if gate.name == "G-commercial")
    assert "W2-01C" in commercial.checklists
    assert "EXT-PAYMENT-PROVIDER" in commercial.required_inputs


@pytest.mark.parametrize(
    ("runtime", "gate", "external_id"),
    [
        (
            {"INVOICE_ISSUER_EXTERNAL_INPUT_REFERENCE": "fabricated-secret-reference"},
            "G-commercial",
            "EXT-Q28-COMPANY",
        ),
        (
            {"PRIVACY_DISCLOSURE_LIVE_AUTHORIZED": "true"},
            "G-GPS",
            "EXT-LEGAL-PRIVACY",
        ),
        (
            {"MEASUREMENT_LIVE_ISSUANCE_AUTHORIZED": "true"},
            "G-GPS",
            "EXT-LEGAL-PRIVACY",
        ),
        (
            {
                "INSTALLATION_EVIDENCE_UPLOADER_ROLES": "driver",
                "INSTALLATION_EVIDENCE_REQUIRED_VIEWS": "front",
                "INSTALLATION_EVIDENCE_VALIDITY_HOURS": "24",
                "DISPLAY_PROOF_CHALLENGE_TTL_SECONDS": "300",
                "DISPLAY_PROOF_VALIDITY_SECONDS": "600",
            },
            "G-GPS",
            "EXT-EVIDENCE-POLICY",
        ),
    ],
)
def test_runtime_or_fabricated_reference_cannot_override_missing_authority(
    authority_texts: tuple[str, str, str],
    runtime: dict[str, str],
    gate: str,
    external_id: str,
) -> None:
    secret = next(iter(runtime.values()))

    with pytest.raises(evaluator.ContradictionError) as raised:
        evaluator.evaluate_gates(_snapshot(authority_texts), runtime)

    diagnostic = str(raised.value)
    assert gate in diagnostic
    assert external_id in diagnostic
    assert secret not in diagnostic


def test_measurement_runtime_claim_requires_method_and_privacy_authority(
    authority_texts: tuple[str, str, str],
) -> None:
    progress, architecture, decisions = authority_texts
    progress = _replace_external_row(
        progress,
        "EXT-LEGAL-PRIVACY",
        state="PRESENT",
        evidence="docs/decisions-log.md D18/Q31",
    )
    trusted = {
        **evaluator.TRUSTED_PRESENT_EVIDENCE,
        "EXT-LEGAL-PRIVACY": evaluator.TrustedEvidence(
            evidence="docs/decisions-log.md D18/Q31",
            document="docs/decisions-log.md",
            identifiers=("D18", "Q31"),
        ),
    }
    snapshot = evaluator.parse_authority(
        progress, architecture, decisions, trusted_evidence=trusted
    )

    with pytest.raises(evaluator.ContradictionError) as raised:
        evaluator.evaluate_gates(snapshot, {"MEASUREMENT_LIVE_ISSUANCE_AUTHORIZED": "true"})

    assert "G-advertiser" in str(raised.value)
    assert "EXT-REPORT-METHOD" in str(raised.value)


def test_incomplete_deferred_validation_never_passes(
    authority_texts: tuple[str, str, str],
) -> None:
    lines = evaluator.evaluate_gates(_snapshot(authority_texts), {})

    assert "DV-PWA-PHYSICAL-MATRIX" in lines[1]
    assert "DV-PWA-ROUTE-BATTERY" in lines[1]
    assert "DV-STAGING-LIVE" in lines[5]


def test_present_input_needs_exact_trusted_committed_evidence(
    authority_texts: tuple[str, str, str],
) -> None:
    progress, architecture, decisions = authority_texts
    progress = _replace_external_row(
        progress,
        "EXT-PILOT-FACTS",
        state="PRESENT",
        evidence="docs/decisions-log.md D99/Q99",
    )

    with pytest.raises(evaluator.AuthorityError) as raised:
        evaluator.parse_authority(progress, architecture, decisions)

    assert "EXT-PILOT-FACTS" in str(raised.value)
    assert "D99" not in str(raised.value)


def test_newly_present_input_without_reviewed_evidence_rule_fails_closed(
    authority_texts: tuple[str, str, str],
) -> None:
    progress, architecture, decisions = authority_texts
    progress = _replace_external_row(
        progress,
        "EXT-REPORT-METHOD",
        state="PRESENT",
        evidence="docs/decisions-log.md D20/Q30",
    )

    with pytest.raises(evaluator.AuthorityError) as raised:
        evaluator.parse_authority(progress, architecture, decisions)

    assert str(raised.value) == "untrusted committed evidence for EXT-REPORT-METHOD"


def test_cleared_w403a_inputs_cannot_hide_incomplete_checklist(
    authority_texts: tuple[str, str, str],
) -> None:
    current = _snapshot(authority_texts)
    external_states = dict(current.external_states)
    external_states["EXT-RELEASE-ENV"] = "PRESENT"
    deferred_states = dict(current.deferred_states)
    deferred_states["DV-STAGING-LIVE"] = "COMPLETE"
    snapshot = evaluator.AuthoritySnapshot(
        checklist_states=current.checklist_states,
        external_states=external_states,
        deferred_states=deferred_states,
        architecture_gates=current.architecture_gates,
    )

    with pytest.raises(evaluator.ContradictionError) as raised:
        evaluator.evaluate_gates(snapshot, {})

    assert str(raised.value) == "checklist contradiction for G-pilot / W4-03A"


def test_malformed_or_duplicate_authority_fails_closed(
    authority_texts: tuple[str, str, str],
) -> None:
    progress, architecture, decisions = authority_texts
    duplicated = progress.replace(
        "## External prerequisite register",
        "## External prerequisite register\n\n## External prerequisite register",
        1,
    )

    with pytest.raises(evaluator.AuthorityError):
        evaluator.parse_authority(duplicated, architecture, decisions)


def test_all_complete_snapshot_emits_six_passes_and_cli_returns_zero(
    authority_texts: tuple[str, str, str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete = _complete_snapshot(authority_texts)
    expected = tuple(f"{gate.name}: PASS" for gate in evaluator.GATES)

    assert evaluator.evaluate_gates(complete, {}) == expected

    monkeypatch.setattr(evaluator, "parse_authority", lambda *_args: complete)
    result = subprocess.CompletedProcess([], 0, "unused", "")
    exit_code = evaluator.main(environment={}, runner=lambda *_args, **_kwargs: result)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert tuple(captured.out.splitlines()) == expected
    assert captured.err == ""


@pytest.mark.parametrize("failure", ["authority", "runtime"])
def test_cli_malformed_input_returns_one_sanitized_diagnostic(
    authority_texts: tuple[str, str, str],
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    progress, architecture, decisions = authority_texts
    if failure == "authority":
        progress = progress.replace(
            "## External prerequisite register",
            "## External prerequisite register\n\n## External prerequisite register",
            1,
        )
        environment = {}
    else:
        environment = {"PRIVACY_DISCLOSURE_LIVE_AUTHORIZED": "CANARY-MALFORMED-SECRET"}
    returned = iter((progress, architecture, decisions))

    def fake_run(command, **kwargs):
        del kwargs
        return subprocess.CompletedProcess(command, 0, next(returned), "")

    exit_code = evaluator.main(environment=environment, runner=fake_run)
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    assert "pilot-gate evaluation failed:" in captured.err
    assert "CANARY-MALFORMED-SECRET" not in captured.err


def test_cli_reads_only_committed_authorities_and_sanitizes_environment(
    authority_texts: tuple[str, str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    progress, architecture, decisions = authority_texts
    returned = {
        "docs/progress.md": progress,
        "docs/architecture.md": architecture,
        "docs/decisions-log.md": decisions,
    }
    calls: list[tuple[str, ...]] = []

    def fake_run(command, **kwargs):
        del kwargs
        calls.append(tuple(command))
        path = command[-1].removeprefix("HEAD:")
        return subprocess.CompletedProcess(command, 0, returned[path], "")

    exit_code = evaluator.main(
        environment={"UNRELATED_SECRET": "never-print-this-secret"}, runner=fake_run
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert len(captured.out.splitlines()) == 6
    assert captured.err == ""
    assert "never-print-this-secret" not in captured.out
    assert calls == [
        ("git", "show", "HEAD:docs/progress.md"),
        ("git", "show", "HEAD:docs/architecture.md"),
        ("git", "show", "HEAD:docs/decisions-log.md"),
    ]


def test_evaluator_has_no_app_network_database_or_write_surface() -> None:
    path = ROOT / "scripts/evaluate_pilot_gates.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert imported.isdisjoint({"app", "socket", "sqlite3", "sqlalchemy", "requests", "httpx"})
    assert not re.search(
        r"\b(open|write_text|write_bytes|unlink|remove|rename|replace)\s*\(", source
    )
    assert "subprocess.Popen" not in source

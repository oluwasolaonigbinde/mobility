from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_progress", ROOT / "scripts" / "validate_progress.py"
)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)


def _progress() -> str:
    return (ROOT / "docs" / "progress.md").read_text()


def _errors(text: str) -> list[str]:
    return VALIDATOR.validate_text(text)


def _paused_at_final_gate() -> str:
    """Create the canonical no-runnable-work pause at W4-03B."""
    text = _progress()
    package_lines = []
    for line in text.splitlines():
        match = re.match(r"\| (\d+) \| \*\*PKG-", line)
        if match:
            number = int(match.group(1))
            current = "**IN PROGRESS**" if number == 1 else "QUEUED"
            replacement = "DONE" if number < 8 else "BLOCKED" if number == 8 else "QUEUED"
            line = line.replace(f"| {current} |", f"| {replacement} |", 1)
        item_match = re.match(r"\| (\d+) \| \*\*(?!PKG-).*\| PKG-\d{2} \|", line)
        if item_match:
            number = int(item_match.group(1))
            if number < 68:
                line = re.sub(r"\| (?:TODO|BLOCKED — EXT-[A-Z0-9-]+) \|", "| DONE |", line, count=1)
            elif number == 68:
                line = line.replace("| TODO |", "| BLOCKED — EXT-LEGAL-PRIVACY |", 1)
        if line.startswith("| **EXT-") and "**EXT-LEGAL-PRIVACY**" not in line:
            line = line.replace("| MISSING |", "| PRESENT |", 1).replace(
                "| — |", "| fixture evidence |", 1
            )
        package_lines.append(line)
    text = "\n".join(package_lines) + "\n"
    return (
        text.replace(
            "**Controller state:** `ACTIVE`",
            "**Controller state:** `PAUSED — EXT-LEGAL-PRIVACY`",
        )
        .replace("**Control package:** `PKG-01`", "**Control package:** `PKG-08`")
        .replace(
            "**Current checkpoint:** `PKG-01 / FND-07`",
            "**Current checkpoint:** `PKG-08 / W4-03B`",
        )
    )


def test_repository_progress_is_valid() -> None:
    assert _errors(_progress()) == []


def test_rejects_second_active_package_and_stale_pointer() -> None:
    text = (
        _progress()
        .replace(
            "| 2 | **PKG-02 — money integrity and payout operations** | QUEUED |",
            "| 2 | **PKG-02 — money integrity and payout operations** | REVIEW |",
        )
        .replace("**Control package:** `PKG-01`", "**Control package:** `PKG-09`")
    )
    errors = _errors(text)
    assert any("exactly one package may be active" in error for error in errors)


def test_rejects_checklist_mapping_or_card_drift() -> None:
    text = (
        _progress()
        .replace(
            "| 10 | **MNY-08A — current fraud assessments** | PKG-02 |",
            "| 10 | **MNY-08A — current fraud assessments** | PKG-03 |",
        )
        .replace("#### MNY-09A —", "#### WRONG-11 —")
    )
    errors = _errors(text)
    assert any("checklist 10 identity/package/prerequisites changed" in error for error in errors)
    assert any("specification-card ids" in error for error in errors)


def test_rejects_forward_dependency_and_unready_checkpoint() -> None:
    text = re.sub(
        r"^(\| 6 \| \*\*FND-07 —.*\| )none \|$",
        r"\1leaf: MNY-06A |",
        _progress(),
        flags=re.MULTILINE,
    )
    errors = _errors(text)
    assert any("missing or not earlier" in error for error in errors)
    assert any("checkpoint is not" in error for error in errors)


def test_rejects_done_package_with_unfinished_items() -> None:
    text = _progress().replace(
        "| 1 | **PKG-01 — foundations and empirical risk proof** | **IN PROGRESS** |",
        "| 1 | **PKG-01 — foundations and empirical risk proof** | DONE |",
    )
    errors = _errors(text)
    assert any("DONE package contains unfinished" in error for error in errors)


def test_rejects_falsely_blocked_package_with_runnable_todo() -> None:
    text = (
        _progress()
        .replace(
            "| 1 | **PKG-01 — foundations and empirical risk proof** | **IN PROGRESS** |",
            "| 1 | **PKG-01 — foundations and empirical risk proof** | BLOCKED |",
        )
        .replace(
            "**Controller state:** `ACTIVE`", "**Controller state:** `PAUSED — EXT-RM2-POLICY`"
        )
    )
    errors = _errors(text)
    assert any("BLOCKED package still has runnable" in error for error in errors)


def test_blocked_item_must_name_its_missing_registered_input() -> None:
    text = _progress().replace(
        "BLOCKED — EXT-STAGING-APPROVAL",
        "BLOCKED — EXT-EMAIL-PROVIDER",
        1,
    )
    errors = _errors(text)
    assert any("is not an item prerequisite" in error for error in errors)


def test_dependency_safe_later_package_checkpoint_is_allowed() -> None:
    text = (
        _progress()
        .replace(
            "| 1 | **PKG-01 — foundations and empirical risk proof** | **IN PROGRESS** |",
            "| 1 | **PKG-01 — foundations and empirical risk proof** | BLOCKED |",
        )
        .replace(
            "| 2 | **PKG-02 — money integrity and payout operations** | QUEUED |",
            "| 2 | **PKG-02 — money integrity and payout operations** | **NEXT** |",
        )
        .replace("**Control package:** `PKG-01`", "**Control package:** `PKG-02`")
        .replace(
            "**Current checkpoint:** `PKG-01 / FND-07`",
            "**Current checkpoint:** `PKG-02 / MNY-08A`",
        )
    )
    # Close every runnable PKG-01 obligation while leaving only the genuine
    # staging blocker, then activate independent PKG-02 work.
    lines = []
    for line in text.splitlines():
        if re.match(r"\| ([124-9]) \| \*\*.*\| PKG-01 \| TODO \|", line):
            line = line.replace("| TODO |", "| DONE |", 1)
        if line.startswith("| 5 | **FND-02B —"):
            line = line.replace("| BLOCKED — EXT-RM2-POLICY |", "| DONE |", 1)
        if line.startswith("| **EXT-RM2-POLICY** |"):
            line = line.replace("| MISSING |", "| PRESENT |", 1).replace(
                "| — |", "| owner decision fixture |", 1
            )
        lines.append(line)
    text = "\n".join(lines) + "\n"
    assert _errors(text) == []


def test_live_use_gate_does_not_block_provider_neutral_item() -> None:
    # EXT-LEGAL-PRIVACY remains MISSING, but W3-00A has no entry dependency and
    # therefore remains a valid future runnable item once selected.
    text = _progress()
    assert "| **EXT-LEGAL-PRIVACY** | MISSING |" in text
    w3_row = next(
        line for line in text.splitlines() if "**W3-00A —" in line and line.startswith("| 44 |")
    )
    assert w3_row.endswith("| none |")
    assert _errors(text) == []


def test_done_item_requires_done_item_dependencies() -> None:
    text = _progress().replace(
        "| 50 | **W3-01B — source/campaign/zone linkage** | PKG-05 | TODO |",
        "| 50 | **W3-01B — source/campaign/zone linkage** | PKG-05 | DONE |",
    )
    errors = _errors(text)
    assert any("DONE item W3-01B has unfinished dependencies: W3-01A" in error for error in errors)


def test_done_item_requires_present_external_prerequisites() -> None:
    text = _progress().replace(
        "| 3 | **R17-A — external synthetic staging drill** | PKG-01 "
        "| BLOCKED — EXT-STAGING-APPROVAL |",
        "| 3 | **R17-A — external synthetic staging drill** | PKG-01 | DONE |",
    )
    errors = _errors(text)
    assert any(
        "DONE item R17-A has missing external prerequisites: EXT-STAGING-APPROVAL" in error
        for error in errors
    )


def test_all_done_terminal_complete_state_is_valid() -> None:
    text = _progress()
    text = re.sub(
        r"^(\| \d+ \| \*\*PKG-\d{2} —.*?\| )"
        r"(?:\*\*NEXT\*\*|\*\*IN PROGRESS\*\*|\*\*REVIEW\*\*|QUEUED)( \|)",
        r"\1DONE\2",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^(\| \d+ \| \*\*(?!PKG-)[A-Z0-9-]+ —.*?\| PKG-\d{2} \| )"
        r"(?:TODO|BLOCKED — EXT-[A-Z0-9-]+)( \|)",
        r"\1DONE\2",
        text,
        flags=re.MULTILINE,
    )
    external_lines = []
    for line in text.splitlines():
        if line.startswith("| **EXT-"):
            line = line.replace("| MISSING |", "| PRESENT |", 1).replace(
                "| — |", "| terminal acceptance evidence |", 1
            )
        external_lines.append(line)
    text = "\n".join(external_lines) + "\n"
    text = text.replace("**Controller state:** `ACTIVE`", "**Controller state:** `COMPLETE`")
    text = text.replace("**Control package:** `PKG-01`", "**Control package:** `PKG-09`")
    text = text.replace(
        "**Current checkpoint:** `PKG-01 / FND-07`",
        "**Current checkpoint:** `PKG-09 / W4-04B`",
    )
    assert _errors(text) == []


def test_rejects_canonical_identity_or_dependency_erasure() -> None:
    renamed = _progress().replace("**FND-07 —", "**MOVED-RM7 —").replace(
        "#### FND-07 —", "#### MOVED-RM7 —"
    )
    erased = _progress().replace(
        "leaf: FND-02A; external: EXT-RM2-POLICY",
        "leaf: FND-02A",
        1,
    )
    assert any(
        "checklist 6 identity/package/prerequisites changed" in error
        for error in _errors(renamed)
    )
    assert any(
        "checklist 5 identity/package/prerequisites changed" in error
        for error in _errors(erased)
    )


def test_live_only_inputs_gate_pilot_not_synthetic_build_items() -> None:
    text = _progress()
    pilot_row = next(line for line in text.splitlines() if line.startswith("| 68 |"))
    for external_id in (
        "EXT-Q28-COMPANY",
        "EXT-COMMERCIAL-VALUES",
        "EXT-EVIDENCE-POLICY",
        "EXT-LEGAL-PRIVACY",
        "EXT-DISBURSEMENT-PROVIDER",
        "EXT-PILOT-PERMITS",
    ):
        assert external_id in pilot_row
    pwa_release_row = next(
        line for line in text.splitlines() if line.startswith("| 64 |")
    )
    assert "EXT-STORE-ASSETS" not in pwa_release_row
    assert next(
        line
        for line in text.splitlines()
        if line.startswith("| 19 |") and "| PKG-03 |" in line
    ).endswith(
        "| leaf: MNY-11A |"
    )
    assert next(
        line
        for line in text.splitlines()
        if line.startswith("| 44 |") and "| PKG-05 |" in line
    ).endswith(
        "| none |"
    )


def test_valid_pause_requires_no_runnable_work_and_real_blocker() -> None:
    text = _paused_at_final_gate()
    assert _errors(text) == []

    runnable = text.replace(
        "| 10 | **MNY-08A — current fraud assessments** | PKG-02 | DONE |",
        "| 10 | **MNY-08A — current fraud assessments** | PKG-02 | TODO |",
    ).replace(
        "| 2 | **PKG-02 — money integrity and payout operations** | DONE |",
        "| 2 | **PKG-02 — money integrity and payout operations** | QUEUED |",
    )
    assert any("runnable TODO work exists" in error for error in _errors(runnable))

    unknown = text.replace(
        "PAUSED — EXT-LEGAL-PRIVACY", "PAUSED — EXT-DOES-NOT-EXIST", 1
    )
    assert any("external id is not registered" in error for error in _errors(unknown))

    stale = text.replace("PKG-08 / W4-03B", "PKG-08 / W4-03A", 1)
    assert any("paused controller external id does not block" in error for error in _errors(stale))


def test_ci_push_validation_covers_arbitrary_branches() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    push_block = workflow.split("  push:\n", 1)[1].split("  pull_request:\n", 1)[0]
    assert "branches:" not in push_block

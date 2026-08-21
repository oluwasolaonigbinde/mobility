from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

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


def _with_control_pointer(text: str, *, state: str, package: str, checkpoint: str) -> str:
    """Replace the live pointer without depending on its current checkpoint."""
    text = re.sub(
        r"^\*\*Controller state:\*\* `[^`]+`$",
        f"**Controller state:** `{state}`",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^\*\*Control package:\*\* `PKG-\d{2}`",
        f"**Control package:** `{package}`",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    return re.sub(
        r"^\*\*Current checkpoint:\*\* `PKG-\d{2} / [A-Z0-9-]+`",
        f"**Current checkpoint:** `{package} / {checkpoint}`",
        text,
        count=1,
        flags=re.MULTILINE,
    )


def _pkg01_active() -> str:
    """Reconstruct the immediately preceding valid frontier for transition tests."""
    text = re.sub(
        r"^(\| 1 \| \*\*PKG-01 —.*?\| )(?:\*\*[^|]+\*\*|DONE|QUEUED|BLOCKED)( \|)",
        r"\1**IN PROGRESS**\2",
        _progress(),
        count=1,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^(\| 2 \| \*\*PKG-02 —.*?\| )(?:\*\*[^|]+\*\*|DONE|QUEUED|BLOCKED)( \|)",
        r"\1QUEUED\2",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    text = _with_control_pointer(
        text,
        state="ACTIVE",
        package="PKG-01",
        checkpoint="FND-02A",
    )
    lines = []
    for line in text.splitlines():
        pkg01_fixture_item = re.match(
            r"\| ([1-5]) \| \*\*.*\| PKG-01 \| DONE \|", line
        )
        pkg02_live_item = re.match(r"\| \d+ \| \*\*.*\| PKG-02 \| DONE \|", line)
        if pkg01_fixture_item or pkg02_live_item:
            line = line.replace("| DONE |", "| TODO |", 1)
        lines.append(line)
    return "\n".join(lines) + "\n"


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
            replacement = "DONE" if number < 8 else "BLOCKED" if number == 8 else "QUEUED"
            line = re.sub(
                r"\| (?:\*\*NEXT\*\*|\*\*IN PROGRESS\*\*|\*\*REVIEW\*\*|QUEUED|DONE|BLOCKED) \|",
                f"| {replacement} |",
                line,
                count=1,
            )
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
        if line.startswith("| **DV-"):
            line = re.sub(r"\| NOT RUN — [^|]+\|", "| COMPLETE |", line, count=1)
        package_lines.append(line)
    text = "\n".join(package_lines) + "\n"
    return _with_control_pointer(
        text,
        state="PAUSED — EXT-LEGAL-PRIVACY",
        package="PKG-08",
        checkpoint="W4-03B",
    )


def test_repository_progress_is_valid() -> None:
    assert _errors(_progress()) == []


def test_rejects_second_active_package_and_stale_pointer() -> None:
    text = (
        _pkg01_active()
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
        r"^(\| 4 \| \*\*FND-02A —.*\| )none \|$",
        r"\1leaf: MNY-08A |",
        _pkg01_active(),
        flags=re.MULTILINE,
    )
    errors = _errors(text)
    assert any("missing or not earlier" in error for error in errors)
    assert any("checkpoint is not" in error for error in errors)


def test_rejects_done_package_with_unfinished_items() -> None:
    text = _pkg01_active().replace(
        "| 1 | **PKG-01 — foundations and empirical risk proof** | **IN PROGRESS** |",
        "| 1 | **PKG-01 — foundations and empirical risk proof** | DONE |",
    )
    errors = _errors(text)
    assert any("DONE package contains unfinished" in error for error in errors)


def test_rejects_falsely_blocked_package_with_runnable_todo() -> None:
    text = (
        _pkg01_active()
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
    text = _pkg01_active().replace(
        "| 5 | **FND-02B — stationary policy implementation** | PKG-01 | TODO |",
        "| 5 | **FND-02B — stationary policy implementation** | PKG-01 "
        "| BLOCKED — EXT-EMAIL-PROVIDER |",
        1,
    )
    errors = _errors(text)
    assert any("is not an item prerequisite" in error for error in errors)


def test_next_package_after_completed_package_is_allowed() -> None:
    text = (
        _pkg01_active()
        .replace(
            "| 1 | **PKG-01 — foundations and empirical risk proof** | **IN PROGRESS** |",
            "| 1 | **PKG-01 — foundations and empirical risk proof** | DONE |",
        )
        .replace(
            "| 2 | **PKG-02 — money integrity and payout operations** | QUEUED |",
            "| 2 | **PKG-02 — money integrity and payout operations** | **NEXT** |",
        )
        .replace("**Control package:** `PKG-01`", "**Control package:** `PKG-02`")
        .replace(
            "**Current checkpoint:** `PKG-01 / FND-02A`",
            "**Current checkpoint:** `PKG-02 / MNY-08A`",
        )
    )
    # Close every PKG-01 obligation, then activate PKG-02.
    lines = []
    for line in text.splitlines():
        if re.match(r"\| ([1-9]) \| \*\*.*\| PKG-01 \| TODO \|", line):
            line = line.replace("| TODO |", "| DONE |", 1)
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
        "| 25 | **W2-01C — gateway adapter and webhook ingestion** | PKG-03 | TODO |",
        "| 25 | **W2-01C — gateway adapter and webhook ingestion** | PKG-03 | DONE |",
    )
    errors = _errors(text)
    assert any(
        "DONE item W2-01C has missing external prerequisites: EXT-PAYMENT-PROVIDER" in error
        for error in errors
    )


def test_deferred_validation_rows_and_gates_are_pinned() -> None:
    removed = re.sub(
        r"^\| \*\*DV-PWA-PHYSICAL-MATRIX\*\* \|.*\n",
        "",
        _progress(),
        flags=re.MULTILINE,
    )
    weakened = _progress().replace(
        "W4 client-owned release and pilot gates",
        "informational only",
        1,
    )
    assert any(
        "deferred validation identities/order/gates changed" in error
        for error in _errors(removed)
    )
    assert any(
        "deferred validation identities/order/gates changed" in error
        for error in _errors(weakened)
    )


def test_pilot_acceptance_rejects_incomplete_deferred_validation() -> None:
    text = _progress().replace(
        "| 68 | **W4-03B — Cardvert pilot gate and acceptance suite** | PKG-08 | TODO |",
        "| 68 | **W4-03B — Cardvert pilot gate and acceptance suite** | PKG-08 | DONE |",
    )
    errors = _errors(text)
    assert any(
        "W4-03B cannot be DONE while deferred validation remains incomplete" in error
        for error in errors
    )


def test_release_environment_rejects_incomplete_live_staging_validation() -> None:
    text = _progress().replace(
        "| 67 | **W4-03A — client-owned release environment** | PKG-08 | TODO |",
        "| 67 | **W4-03A — client-owned release environment** | PKG-08 | DONE |",
    )
    errors = _errors(text)
    assert any(
        "W4-03A cannot be DONE while DV-STAGING-LIVE is incomplete" in error
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
        if line.startswith("| **DV-"):
            line = re.sub(r"\| NOT RUN — [^|]+\|", "| COMPLETE |", line, count=1)
        external_lines.append(line)
    text = "\n".join(external_lines) + "\n"
    text = _with_control_pointer(
        text,
        state="COMPLETE",
        package="PKG-09",
        checkpoint="W4-04B",
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


def test_ci_avoids_duplicate_feature_branch_runs() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    push_block = workflow.split("  push:\n", 1)[1].split("  pull_request:\n", 1)[0]
    pull_request_block = workflow.split("  pull_request:\n", 1)[1].split(
        "\nconcurrency:\n", 1
    )[0]

    assert "branches:\n      - master" in push_block
    assert "branches:" not in pull_request_block
    assert "github.event.pull_request.number || github.ref" in workflow
    assert "cancel-in-progress: true" in workflow


# --- Control-plane hardening regressions (task-master correction, 16 Aug 2026) ---


def test_rejects_hidden_controller_pointer_decoy() -> None:
    decoy = (
        "<!--\n"
        "**Controller state:** `ACTIVE`\n"
        "**Control package:** `PKG-01`\n"
        "**Current checkpoint:** `PKG-01 / FND-02A`\n"
        "-->\n"
    )
    text = (
        _pkg01_active()
        .replace("### Current control pointer", "### Current control pointer\n\n" + decoy)
        .replace(
            "**Control package:** `PKG-01` — see package queue row 2",
            "**Control package:** `PKG-09` — see package queue row 2",
        )
    )
    errors = _errors(text)
    assert any("control package pointer does not match" in error for error in errors)


def test_rejects_fenced_decoy_package_queue() -> None:
    fence = (
        "```md\n"
        "## Executable package queue\n\n"
        "| # | Package | Status | Outcome | Package prerequisites |\n"
        "| ---: | --- | --- | --- | --- |\n"
        "```\n\n"
    )
    text = _pkg01_active().replace(
        "## Executable package queue", fence + "## Executable package queue", 1
    ).replace(
        "| 1 | **PKG-01 — foundations and empirical risk proof** | **IN PROGRESS** |",
        "| 1 | **PKG-01 — foundations and empirical risk proof** | DONE |",
    )
    errors = _errors(text)
    assert any("DONE package contains unfinished" in error for error in errors)


def test_rejects_unterminated_comment() -> None:
    text = _pkg01_active().replace(
        "### Current control pointer", "<!--\n### Current control pointer", 1
    )
    assert any("unterminated HTML comment" in error for error in _errors(text))


def test_rejects_unclosed_fence() -> None:
    text = _progress().replace(
        "## Executable package queue", "```\n## Executable package queue", 1
    )
    assert any("unclosed code fence" in error for error in _errors(text))


def test_rejects_sublevel_heading_decoy_table() -> None:
    decoy = (
        "### Executable package queue (decoy)\n\n"
        "| # | Package | Status | Outcome | Package prerequisites |\n"
        "| ---: | --- | --- | --- | --- |\n\n"
    )
    text = _progress().replace(
        "| # | Package | Status | Outcome | Package prerequisites |",
        decoy + "| # | Package | Status | Outcome | Package prerequisites |",
        1,
    )
    errors = _errors(text)
    assert any("must appear exactly once at any heading level" in error for error in errors)
    assert any("must appear exactly once in its" in error for error in errors)


def test_review_cannot_avoid_pause_with_blocked_checkpoint() -> None:
    text = _pkg01_active().replace(
        "| 1 | **PKG-01 — foundations and empirical risk proof** | **IN PROGRESS** |",
        "| 1 | **PKG-01 — foundations and empirical risk proof** | REVIEW |",
    ).replace(
        "**Current checkpoint:** `PKG-01 / FND-02A`",
        "**Current checkpoint:** `PKG-01 / FND-07`",
    )
    errors = _errors(text)
    assert any(
        "current checkpoint is not a dependency-satisfied runnable TODO" in error
        for error in errors
    )


def test_review_valid_only_when_all_items_done_or_runnable() -> None:
    # Direction 1: REVIEW with unfinished work and a runnable checkpoint is valid.
    reviewing = _pkg01_active().replace(
        "| 1 | **PKG-01 — foundations and empirical risk proof** | **IN PROGRESS** |",
        "| 1 | **PKG-01 — foundations and empirical risk proof** | REVIEW |",
    )
    assert _errors(reviewing) == []
    # Direction 2: REVIEW with every owned item DONE (consolidated closure
    # review) is valid even though nothing is runnable.
    lines = []
    for line in reviewing.splitlines():
        if re.match(r"\| [1-9] \| \*\*(?!PKG-).*\| PKG-01 \|", line):
            line = re.sub(
                r"\| (?:TODO|BLOCKED — EXT-[A-Z0-9-]+) \|", "| DONE |", line, count=1
            )
        if line.startswith("| **EXT-STAGING-APPROVAL** |") or line.startswith(
            "| **EXT-RM2-POLICY** |"
        ):
            line = line.replace("| MISSING |", "| PRESENT |", 1).replace(
                "| — |", "| owner-recorded evidence |", 1
            )
        lines.append(line)
    assert _errors("\n".join(lines) + "\n") == []


def test_rejects_done_item_in_queued_package() -> None:
    text = _pkg01_active().replace(
        "| 10 | **MNY-08A — current fraud assessments** | PKG-02 | TODO |",
        "| 10 | **MNY-08A — current fraud assessments** | PKG-02 | DONE |",
    )
    errors = _errors(text)
    assert any("QUEUED package contains DONE checklist items" in error for error in errors)


def test_rejects_nonqueued_package_after_active_frontier() -> None:
    text = _progress().replace(
        "| 3 | **PKG-03 — commercial contracts and billing** | QUEUED |",
        "| 3 | **PKG-03 — commercial contracts and billing** | DONE |",
    )
    errors = _errors(text)
    assert any(
        "package after the active frontier must be QUEUED or BLOCKED" in error
        for error in errors
    )


def test_later_blocked_package_still_validates() -> None:
    text = _progress().replace(
        "| 8 | **PKG-08 — governed reporting and pilot readiness** | QUEUED |",
        "| 8 | **PKG-08 — governed reporting and pilot readiness** | BLOCKED |",
    ).replace(
        "| 65 | **W4-02A — governed maps and report experience** | PKG-08 | TODO |",
        "| 65 | **W4-02A — governed maps and report experience** | PKG-08 "
        "| BLOCKED — EXT-BASEMAP |",
    ).replace(
        "| 67 | **W4-03A — client-owned release environment** | PKG-08 | TODO |",
        "| 67 | **W4-03A — client-owned release environment** | PKG-08 "
        "| BLOCKED — EXT-RELEASE-ENV |",
    )
    assert _errors(text) == []


def test_rejects_package_contract_ownership_drift() -> None:
    text = _progress().replace(
        "- **Owns:** checklist 1–9.",
        "- **Owns:** checklist 1–71.",
    )
    errors = _errors(text)
    assert any(
        "PKG-01 Owns declaration does not match the canonical checklist membership" in error
        for error in errors
    )


def test_report_method_gates_pilot_not_w4_02b_build() -> None:
    text = _progress()
    row_66 = next(line for line in text.splitlines() if line.startswith("| 66 | **W4-02B"))
    row_68 = next(line for line in text.splitlines() if line.startswith("| 68 | **W4-03B"))
    assert "EXT-REPORT-METHOD" not in row_66
    assert row_66.rstrip().endswith("| leaf: W4-02A |")
    assert "EXT-REPORT-METHOD" in row_68
    assert _errors(text) == []
    regressed = text.replace(
        "| leaf: W4-02A |", "| leaf: W4-02A; external: EXT-REPORT-METHOD |", 1
    )
    assert any(
        "checklist 66 identity/package/prerequisites changed" in error
        for error in _errors(regressed)
    )


@pytest.mark.parametrize("external_id", ["EXT-STORE-ASSETS", "EXT-AD-PLATFORM"])
def test_rejects_stable_external_id_erasure(external_id: str) -> None:
    text = _progress()
    row = next(line for line in text.splitlines() if line.startswith(f"| **{external_id}**"))
    errors = _errors(text.replace(row + "\n", ""))
    assert any("external register identities/order changed" in error for error in errors)


def test_blocked_item_names_all_direct_missing_inputs() -> None:
    text = _progress().replace(
        "| 68 | **W4-03B — Cardvert pilot gate and acceptance suite** | PKG-08 | TODO |",
        "| 68 | **W4-03B — Cardvert pilot gate and acceptance suite** | PKG-08 "
        "| BLOCKED — EXT-Q28-COMPANY |",
    )
    errors = _errors(text)
    assert any(
        "W4-03B must name exactly its missing direct external inputs" in error
        for error in errors
    )


def test_rejects_stale_control_package_pointer() -> None:
    text = _progress().replace(
        "**Control package:** `PKG-02`", "**Control package:** `PKG-09`"
    )
    errors = _errors(text)
    assert any("control package pointer does not match" in error for error in errors)


def test_ci_explicitly_runs_progress_validation() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "scripts/validate_progress.py" in workflow


def test_rejects_h1_shadow_section_with_divergent_statuses() -> None:
    shadow = (
        "# Executable package queue\n\n"
        "| # | Package | Status | Outcome | Package prerequisites |\n"
        "| ---: | --- | --- | --- | --- |\n"
        "| 1 | **PKG-01 — foundations and empirical risk proof** | DONE | x | none |\n\n"
    )
    text = _progress().replace(
        "## Executable package queue", shadow + "## Executable package queue", 1
    )
    errors = _errors(text)
    assert any("must appear exactly once at any heading level" in error for error in errors)


def test_rejects_duplicate_contradictory_owns_declaration() -> None:
    text = _progress().replace(
        "- **Owns:** checklist 1–9.",
        "- **Owns:** checklist 1–9.\n- **Owns:** checklist 1–71.",
        1,
    )
    errors = _errors(text)
    assert any(
        "PKG-01 must declare exactly one Owns: checklist" in error for error in errors
    )


def test_rejects_full_shadow_duplicate_document() -> None:
    text = _progress()
    errors = _errors(text + "\n\n" + text)
    assert any("must appear exactly once" in error for error in errors)


def test_ci_e2e_boot_is_fail_closed() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "pg_isready" in workflow
    assert workflow.count("never became ready") >= 2

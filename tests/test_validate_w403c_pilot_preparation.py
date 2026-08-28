from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.validate_w403c_pilot_preparation import validate_pack

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs" / "pilot-operations"
PROGRESS = ROOT / "docs" / "progress.md"


def _copy_pack(tmp_path: Path) -> Path:
    destination = tmp_path / "pilot-operations"
    shutil.copytree(PACK, destination)
    return destination


def _replace(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def test_committed_pilot_preparation_pack_passes() -> None:
    assert validate_pack(ROOT, PACK) == []


@pytest.mark.parametrize(
    ("filename", "old", "new", "expected_error"),
    (
        (
            "operations-pack.md",
            "## Domain: payout-replay",
            "## Omitted domain: payout-replay",
            "missing domain: payout-replay",
        ),
        (
            "README.md",
            "../w4-03a-release-operations.md",
            "../missing-release-operations.md",
            "broken local link",
        ),
        (
            "synthetic-exercises.md",
            "tests/test_payout_batches.py::test_submission_fails_closed_without_approved_provider",
            "tests/test_payout_batches.py::test_missing_provider_stop_node",
            "missing pytest node",
        ),
        (
            "operations-pack.md",
            "Stop criteria:",
            "Stop rules omitted:",
            "missing required label: Stop criteria:",
        ),
        (
            "operations-pack.md",
            "Evidence fields:",
            "Evidence details omitted:",
            "missing required label: Evidence fields:",
        ),
        (
            "README.md",
            "W4-03C remains incomplete and externally blocked.",
            "W4-03C is DONE.",
            "prohibited completion/live claim",
        ),
        (
            "README.md",
            "| EXT-PILOT-FACTS | PRESENT |",
            "| EXT-PILOT-FACTS | MISSING |",
            "pilot gate parity mismatch",
        ),
    ),
)
def test_audit_rejects_missing_broken_or_false_pack_evidence(
    tmp_path: Path,
    filename: str,
    old: str,
    new: str,
    expected_error: str,
) -> None:
    copied_pack = _copy_pack(tmp_path)
    _replace(copied_pack / filename, old, new)

    errors = validate_pack(ROOT, copied_pack)

    assert any(expected_error in error for error in errors), errors


def test_audit_rejects_authoritative_progress_source_drift() -> None:
    progress_text = PROGRESS.read_text(encoding="utf-8")
    source_row = "| **EXT-RM2-POLICY** | PRESENT |"
    assert source_row in progress_text
    drifted_progress = progress_text.replace(
        source_row,
        "| **EXT-RM2-POLICY** | MISSING |",
        1,
    )

    errors = validate_pack(ROOT, PACK, progress_text_override=drifted_progress)

    assert any("pilot gate parity mismatch" in error for error in errors), errors

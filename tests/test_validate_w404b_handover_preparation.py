from __future__ import annotations

import shutil
from pathlib import Path

from scripts.validate_w404b_handover_preparation import validate_repository

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fixture_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "docs", root / "docs")
    shutil.copy2(REPO_ROOT / "README.md", root / "README.md")
    (root / "scripts").mkdir()
    shutil.copy2(
        REPO_ROOT / "scripts/validate_w404b_handover_preparation.py",
        root / "scripts/validate_w404b_handover_preparation.py",
    )
    return root


def _replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_repository_handover_preparation_is_valid() -> None:
    assert validate_repository(REPO_ROOT) == []


def test_broken_local_fragment_fails(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path)
    _replace(
        root / "docs/handover/README.md",
        "../../README.md#project-status",
        "../../README.md#missing-heading",
    )
    assert any("broken local fragment" in error for error in validate_repository(root))


def test_missing_required_domain_and_role_fail(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path)
    readme = root / "docs/handover/README.md"
    readme.write_text(
        "\n".join(
            line
            for line in readme.read_text(encoding="utf-8").splitlines()
            if not line.startswith("| Reporting |")
        )
        + "\n",
        encoding="utf-8",
    )
    roles = root / "docs/handover/roles-and-responsibilities.md"
    roles.write_text(
        "\n".join(
            line
            for line in roles.read_text(encoding="utf-8").splitlines()
            if not line.startswith("| `<MONEY_RECONCILER_ROLE>` |")
        )
        + "\n",
        encoding="utf-8",
    )
    errors = validate_repository(root)
    assert any("documentation index domain mismatch" in error for error in errors)
    assert any("role registry mismatch" in error for error in errors)


def test_external_gate_omission_state_drift_and_deferred_drift_fail(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path)
    risks = root / "docs/handover/external-and-deferred-risks.md"
    text = risks.read_text(encoding="utf-8")
    text = (
        "\n".join(
            line for line in text.splitlines() if not line.startswith("| EXT-PAYMENT-PROVIDER |")
        )
        + "\n"
    )
    text = text.replace("| EXT-RM2-POLICY | PRESENT |", "| EXT-RM2-POLICY | MISSING |", 1)
    text = text.replace(
        "| DV-STAGING-LIVE | NOT RUN — EXT-STAGING-APPROVAL |",
        "| DV-STAGING-LIVE | COMPLETE |",
        1,
    )
    risks.write_text(text, encoding="utf-8")
    errors = validate_repository(root)
    assert any("external gate parity mismatch" in error for error in errors)
    assert any("deferred validation parity mismatch" in error for error in errors)


def test_unsafe_secret_contact_and_account_identifier_fail(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path)
    credentials = root / "docs/handover/credential-handover-checklist.md"
    credentials.write_text(
        credentials.read_text(encoding="utf-8")
        + '\napi_key = "sk-live-unsafevalue"\n'
        + "account_id: acct_unsafe123\n"
        + "contact: owner@example.com\n",
        encoding="utf-8",
    )
    errors = validate_repository(root)
    assert any("unsafe provider secret token" in error for error in errors)
    assert any("unsafe account identifier" in error for error in errors)
    assert any("unsafe contact email" in error for error in errors)


def test_unapproved_numeric_sla_fails(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path)
    _replace(
        root / "docs/handover/support-sla-escalation.md",
        "| Initial acknowledgement | `<PROPOSED — OWNER APPROVAL REQUIRED>` |",
        "| Initial acknowledgement | 15 minutes |",
    )
    errors = validate_repository(root)
    assert any("placeholder-only" in error for error in errors)
    assert any("unapproved numeric SLA/SLO target" in error for error in errors)


def test_unapproved_numeric_sla_outside_table_fails(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path)
    support = root / "docs/handover/support-sla-escalation.md"
    support.write_text(
        support.read_text(encoding="utf-8")
        + "\nCritical cases receive a response within 15 minutes.\n",
        encoding="utf-8",
    )
    assert any("unapproved numeric SLA/SLO target" in error for error in validate_repository(root))


def test_additional_prohibited_identifier_assignments_fail(tmp_path: Path) -> None:
    assignments = (
        "tenant_id: tenant-unsafe",
        "subscription_id: subscription-unsafe",
        "username: unsafe-user",
        "private_endpoint: https://private.internal",
    )
    for index, assignment in enumerate(assignments):
        root = _fixture_repo(tmp_path / str(index))
        credentials = root / "docs/handover/credential-handover-checklist.md"
        credentials.write_text(
            credentials.read_text(encoding="utf-8") + f"\n{assignment}\n",
            encoding="utf-8",
        )
        assert any(
            "unsafe secret/account assignment" in error for error in validate_repository(root)
        )


def test_affirmative_completion_live_and_acceptance_claims_fail(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path)
    readme = root / "docs/handover/README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\nHandover is complete. Production is live. "
        + "Credentials have been transferred. Accepted by the owner.\n",
        encoding="utf-8",
    )
    errors = validate_repository(root)
    assert any("affirmative completion/live claim" in error for error in errors)
    assert any("affirmative credential-transfer claim" in error for error in errors)
    assert any("acceptance attribution" in error for error in errors)


def test_additional_affirmative_completion_forms_fail(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path)
    readme = root / "docs/handover/README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\nHandover finished successfully. Credentials were transferred. "
        + "The controlled pilot ran live.\n",
        encoding="utf-8",
    )
    errors = validate_repository(root)
    assert any("affirmative completion/live claim" in error for error in errors)
    assert any("affirmative credential-transfer claim" in error for error in errors)
    assert any("completed pilot claim" in error for error in errors)


def test_safe_negative_claims_remain_valid(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path)
    readme = root / "docs/handover/README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\nHandover is not complete; production is not live; "
        + "credentials have not been transferred.\n",
        encoding="utf-8",
    )
    assert validate_repository(root) == []


def test_roadmap_category_drift_fails(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path)
    _replace(
        root / "docs/handover/post-mvp-roadmap.md",
        "| Post-MVP idea | Expanded recurring billing |",
        "| Integrated capability | Expanded recurring billing |",
    )
    assert any("roadmap placement mismatch" in error for error in validate_repository(root))


def test_missing_raci_support_and_extra_roadmap_rows_fail(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path)
    roles = root / "docs/handover/roles-and-responsibilities.md"
    role_text = roles.read_text(encoding="utf-8")
    role_text = "\n".join(
        line for line in role_text.splitlines() if not line.startswith("| Training |")
    )
    roles.write_text(role_text + "\n", encoding="utf-8")

    support = root / "docs/handover/support-sla-escalation.md"
    support_text = support.read_text(encoding="utf-8")
    support_text = "\n".join(
        line for line in support_text.splitlines() if not line.startswith("| Reporting/method |")
    )
    support.write_text(support_text + "\n", encoding="utf-8")

    roadmap = root / "docs/handover/post-mvp-roadmap.md"
    roadmap_text = roadmap.read_text(encoding="utf-8")
    roadmap.write_text(
        roadmap_text.replace(
            "\nOptional RM2 field calibration",
            "\n| Post-MVP idea | Speculative extra | Not authorized. | None |\n"
            "\nOptional RM2 field calibration",
            1,
        ),
        encoding="utf-8",
    )
    errors = validate_repository(root)
    assert any("RACI workstream mismatch" in error for error in errors)
    assert any("support function mismatch" in error for error in errors)
    assert any("roadmap capability set mismatch" in error for error in errors)

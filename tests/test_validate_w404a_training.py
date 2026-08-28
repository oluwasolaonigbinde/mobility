import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.validate_w404a_training import audit_repository


ROOT = Path(__file__).resolve().parents[1]
ROLE_INVENTORY = ROOT / "docs" / "training" / "role-task-inventories.md"
TRAINING_INDEX = ROOT / "docs" / "training" / "README.md"
PROCEDURES = ROOT / "docs" / "training" / "operator-procedures.md"


def _replace_once(path: Path, old: str, new: str) -> dict[Path, str]:
    original = path.read_text(encoding="utf-8")
    assert old in original
    return {path: original.replace(old, new, 1)}


class ValidateW404ATrainingTests(unittest.TestCase):
    def test_repository_training_materials_pass_the_focused_audit(self) -> None:
        self.assertEqual(audit_repository(ROOT), [])

    def test_audit_rejects_missing_role_and_domain_coverage(self) -> None:
        original = ROLE_INVENTORY.read_text(encoding="utf-8")
        self.assertIn("| driver |", original)
        missing_role = {ROLE_INVENTORY: original.replace("| driver |", "| rider |")}
        self.assertTrue(
            any(
                "missing role coverage: driver" in error
                for error in audit_repository(ROOT, missing_role)
            )
        )

        missing_domain = _replace_once(PROCEDURES, "## Fraud review", "## Risk review")
        self.assertTrue(
            any(
                "missing operator domain: fraud" in error
                for error in audit_repository(ROOT, missing_domain)
            )
        )

    def test_audit_rejects_fictitious_and_cross_role_ui_routes(self) -> None:
        fictitious = _replace_once(ROLE_INVENTORY, "/admin/audit", "/admin/not-a-real-page")
        self.assertTrue(
            any(
                "UI route does not resolve" in error
                for error in audit_repository(ROOT, fictitious)
            )
        )

        cross_role = _replace_once(
            ROLE_INVENTORY,
            "| admin | /admin/audit",
            "| admin | /advertiser/billing",
        )
        self.assertTrue(
            any(
                "crosses its role boundary" in error
                for error in audit_repository(ROOT, cross_role)
            )
        )

    def test_audit_rejects_broken_local_link_and_repository_command(self) -> None:
        bad_link = _replace_once(TRAINING_INDEX, "../runbook.md", "../missing-runbook.md")
        self.assertTrue(
            any("broken local link" in error for error in audit_repository(ROOT, bad_link))
        )

        bad_command = _replace_once(
            PROCEDURES,
            "python3 scripts/run_w403b_synthetic_journey.py",
            "python3 scripts/missing_synthetic_journey.py",
        )

        bad_interpreter = _replace_once(
            TRAINING_INDEX,
            "python3 scripts/validate_w404a_training.py",
            "python scripts/validate_w404a_training.py",
        )
        self.assertTrue(
            any(
                "unsupported repository command shape" in error
                for error in audit_repository(ROOT, bad_interpreter)
            )
        )
        self.assertTrue(
            any(
                "repository command target does not exist" in error
                for error in audit_repository(ROOT, bad_command)
            )
        )

        with patch("scripts.validate_w404a_training.shutil.which", return_value=None):
            unavailable_errors = audit_repository(ROOT)
        self.assertTrue(
            any(
                "repository command interpreter is unavailable" in error
                for error in unavailable_errors
            )
        )

    def test_audit_accepts_negative_gate_language_and_rejects_false_live_claims(self) -> None:
        self.assertEqual(audit_repository(ROOT), [])

        false_claim = _replace_once(
            TRAINING_INDEX,
            "W4-04A remains incomplete: facilitated rehearsal, user acceptance, "
            "and live operation have not occurred.",
            "W4-04A is complete: facilitated rehearsal and user acceptance passed, "
            "and live operation occurred.",
        )
        errors = audit_repository(ROOT, false_claim)
        self.assertTrue(
            any("missing required negative gate statement" in error for error in errors)
        )
        self.assertTrue(any("prohibited completion or live claim" in error for error in errors))

    def test_each_operator_domain_requires_the_common_procedure_schema(self) -> None:
        missing_stop_condition = _replace_once(
            PROCEDURES,
            "### Stop conditions and escalation",
            "### Escalation notes",
        )
        self.assertTrue(
            any(
                "missing required subsection 'Stop conditions and escalation'" in error
                for error in audit_repository(ROOT, missing_stop_condition)
            )
        )


if __name__ == "__main__":
    unittest.main()

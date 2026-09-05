from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.main import create_app
from scripts.update_architecture_inventory import (
    REQUIRED_DSR_ROUTES,
    REQUIRED_ONBOARDING_ROUTES,
    collect_inventory,
    render_architecture,
)

ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE_PATH = ROOT / "docs" / "architecture.md"


def test_architecture_current_state_inventory_matches_repository() -> None:
    current = ARCHITECTURE_PATH.read_text(encoding="utf-8")

    assert render_architecture(current, collect_inventory()) == current


def test_representative_inventory_drift_is_detected() -> None:
    current = ARCHITECTURE_PATH.read_text(encoding="utf-8")
    inventory = collect_inventory()
    expected = f"Current OpenAPI: **{inventory.operations} operations"
    drifted = current.replace(expected, f"Current OpenAPI: **{inventory.operations - 1} operations")

    assert drifted != current
    assert render_architecture(drifted, inventory) == current


def test_architecture_inventory_requires_one_linear_alembic_head() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    revisions = tuple(scripts.walk_revisions())

    assert scripts.get_bases() == ["0001_enable_extensions"]
    assert scripts.get_heads() == ["0084_payout_conservation"]
    assert len(revisions) == 84
    assert not any(revision.is_branch_point or revision.is_merge_point for revision in revisions)


def test_required_onboarding_and_dsr_routes_are_present() -> None:
    paths = set(create_app().openapi()["paths"])

    assert REQUIRED_ONBOARDING_ROUTES <= paths
    assert REQUIRED_DSR_ROUTES <= paths

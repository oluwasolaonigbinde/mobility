"""R02 / GOV-003, TST-001, DB-005 — CI selection and real-integration authority.

These are static assertions over `.github/workflows/ci.yml`. They exist because the
defect class is *silence*: a dropped path filter or a removed service disarms every
downstream gate without any check turning red. The workflow cannot police itself, so
the repository suite polices the workflow.

Every-branch push and pull-request selection is pinned by
`tests/test_validate_progress.py::test_ci_runs_for_every_direct_branch_push_and_pull_request`.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/ci.yml"
E2E_COMPOSE_OVERRIDE_PATH = REPO_ROOT / "frontend/e2e/support/docker-compose.e2e.yml"

# Release-critical paths a change to which must select CI. The root entries are the
# ones codex-production-readiness-audit P1 found omitted; `.codex/**` closes the
# controller-state gap in chatgpt-architecture-implementation-audit §3.
REQUIRED_SELECTED_PATHS = (
    "app/**",
    "alembic/**",
    "tests/**",
    "frontend/**",
    "scripts/**",
    "docs/**",
    ".codex/**",
    ".github/workflows/**",
    "openapi.json",
    "pyproject.toml",
    "alembic.ini",
    "Dockerfile",
    ".env.example",
    "production.env.example",
    "requirements-production.in",
    "requirements-production.txt",
    "docker-compose.yml",
    "docker-compose.production.yml",
    "Caddyfile",
    "staging.env.example",
    "AGENTS.md",
    ".pre-commit-config.yaml",
)

# Authority the backend job must hand pytest so no real integration can opt itself out.
REQUIRED_BACKEND_ENV = {
    "REQUIRE_REAL_INTEGRATIONS": "1",
    "RUN_LOCAL_FILE_INTEGRATION": "1",
    "RUN_REPORT_STORAGE_LOCAL_INTEGRATION": "1",
}

CANDIDATE_SHA_EXPRESSION = "${{ github.event.pull_request.head.sha || github.sha }}"
AUTHORITY_ENV = "REQUIRE_REAL_INTEGRATIONS"
SKIP_PROBE_ENV = "R02_AUTHORITY_SKIP_PROBE"


def _run_probe(
    nodeid: str,
    *,
    authority: bool,
    database_url: str | None,
    force_skip: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env.pop("TEST_DATABASE_URL", None)
    env.pop(AUTHORITY_ENV, None)
    env.pop(SKIP_PROBE_ENV, None)
    if authority:
        env[AUTHORITY_ENV] = "1"
    if database_url is not None:
        env["TEST_DATABASE_URL"] = database_url
    if force_skip:
        env[SKIP_PROBE_ENV] = "1"

    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", nodeid],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def triggers(workflow: dict) -> dict:
    # PyYAML resolves the bare key `on` to the boolean True (YAML 1.1 truthiness).
    return workflow[True] if True in workflow else workflow["on"]


@pytest.mark.parametrize("required_path", REQUIRED_SELECTED_PATHS)
@pytest.mark.parametrize("event", ("push", "pull_request"))
def test_release_critical_paths_select_ci(triggers: dict, event: str, required_path: str) -> None:
    selected = triggers[event]["paths"]

    assert required_path in selected, (
        f"{event} path filter omits {required_path!r}; a change confined to it would "
        f"merge with no backend, frontend, contract, build or e2e evidence."
    )


def test_push_and_pull_request_select_identically(triggers: dict) -> None:
    assert triggers["push"]["paths"] == triggers["pull_request"]["paths"]


@pytest.mark.skipif(
    os.environ.get(SKIP_PROBE_ENV) == "1",
    reason="R02 authority-mode skip accounting probe",
)
def test_authority_skip_probe() -> None:
    pass


def test_authority_mode_rejects_a_skipped_integration() -> None:
    result = _run_probe(
        f"{__file__}::test_authority_skip_probe",
        authority=True,
        database_url="postgresql+asyncpg://unused:unused@localhost/unused",
        force_skip=True,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "1 test(s) skipped while REQUIRE_REAL_INTEGRATIONS=1" in result.stdout


@pytest.mark.parametrize("database_url", (None, "sqlite+aiosqlite:///local.db"))
def test_authority_mode_rejects_missing_or_non_postgresql_database(
    database_url: str | None,
) -> None:
    result = _run_probe(
        f"{__file__}::test_authority_skip_probe",
        authority=True,
        database_url=database_url,
    )

    assert result.returncode == 4, result.stdout + result.stderr
    assert "SQLite create_all evidence is not authoritative" in result.stderr


def test_fast_local_sqlite_probe(db_sessionmaker) -> None:
    async def probe() -> str:
        async with db_sessionmaker() as session:
            return str((await session.execute(text("SELECT 1"))).scalar_one())

    assert asyncio.run(probe()) == "1"


def test_local_mode_keeps_fast_sqlite_available() -> None:
    result = _run_probe(
        f"{__file__}::test_fast_local_sqlite_probe",
        authority=False,
        database_url=None,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_backend_job_declares_real_postgis_and_redis_services(workflow: dict) -> None:
    services = workflow["jobs"]["backend_tests"]["services"]

    assert services["db"]["image"].startswith("postgis/postgis:"), services["db"]["image"]
    assert services["redis"]["image"].startswith("redis:"), services["redis"]["image"]


def test_backend_job_starts_real_minio_and_clamav(workflow: dict) -> None:
    """TST-001: MinIO/ClamAV tests must run, not skip for want of infrastructure."""
    steps = yaml.safe_dump(workflow["jobs"]["backend_tests"]["steps"])

    # Pinned in docker-compose.yml; CI must exercise the same images, not a drifted tag.
    assert "minio/minio:RELEASE.2025-07-23T15-54-02Z" in steps
    assert "clamav/clamav:1.4" in steps
    assert "cardvert-private" in steps


def test_e2e_stack_uses_only_explicit_synthetic_disclosure_authority(workflow: dict) -> None:
    boot_step = next(
        step
        for step in workflow["jobs"]["e2e"]["steps"]
        if step.get("name") == "Boot backend (api + PostGIS + Redis)"
    )

    assert boot_step["env"]["COMPOSE_FILE"] == (
        "docker-compose.yml:frontend/e2e/support/docker-compose.e2e.yml"
    )

    override = yaml.safe_load(E2E_COMPOSE_OVERRIDE_PATH.read_text(encoding="utf-8"))
    environment = override["services"]["api"]["environment"]
    assert environment == {
        "ENVIRONMENT": "test",
        "PRIVACY_DISCLOSURE_SYNTHETIC_TEST_MODE": "true",
        "PRIVACY_DISCLOSURE_LIVE_AUTHORIZED": "false",
    }

    default_compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())
    default_environment = default_compose["services"]["api"]["environment"]
    assert default_environment["ENVIRONMENT"] == "local"
    assert default_environment["PRIVACY_DISCLOSURE_LIVE_AUTHORIZED"].endswith(":-false}")
    assert "PRIVACY_DISCLOSURE_SYNTHETIC_TEST_MODE" not in default_environment


def test_backend_job_requires_real_integration_authority(workflow: dict) -> None:
    env = workflow["jobs"]["backend_tests"]["env"]

    for name, value in REQUIRED_BACKEND_ENV.items():
        assert env.get(name) == value, f"backend job must export {name}={value}"

    assert env["TEST_DATABASE_URL"].startswith("postgresql+asyncpg://"), (
        "DB-005: the authoritative backend job must run against real PostgreSQL, "
        "never the SQLite fast-local fixture."
    )
    assert env["REDIS_URL"] == "redis://localhost:6379/0"
    assert env["RATE_LIMIT_TEST_REDIS_URL"] == "redis://localhost:6379/9"
    assert env["ARQ_TEST_REDIS_URL"] == "redis://localhost:6379/8"


def test_backend_job_installs_release_and_frontend_test_dependencies(workflow: dict) -> None:
    steps = workflow["jobs"]["backend_tests"]["steps"]

    setup_node = next(step for step in steps if step.get("uses") == "actions/setup-node@v4")
    assert setup_node["with"] == {
        "node-version-file": "frontend/.nvmrc",
        "cache": "npm",
        "cache-dependency-path": "frontend/package-lock.json",
    }
    for command in (
        "sudo apt-get update && sudo apt-get install --yes jq",
        "npm ci",
        "npx playwright install --with-deps chromium",
    ):
        matching_steps = [step for step in steps if step.get("run") == command]
        assert matching_steps, f"backend job does not provision {command!r}"
        if command.startswith(("npm", "npx")):
            assert matching_steps[0].get("working-directory") == "frontend"


@pytest.mark.parametrize(
    "job_name", ("backend_static", "backend_tests", "backend", "quality", "e2e")
)
def test_every_job_binds_evidence_to_the_candidate_sha(workflow: dict, job_name: str) -> None:
    """Evidence from a synthetic merge commit is evidence for a SHA nobody can re-check."""
    steps = workflow["jobs"][job_name]["steps"]

    checkouts = [step for step in steps if str(step.get("uses", "")).startswith("actions/checkout")]
    assert checkouts, f"{job_name} has no checkout step"

    for checkout in checkouts:
        assert checkout.get("with", {}).get("ref") == CANDIDATE_SHA_EXPRESSION, (
            f"{job_name} checks out the default ref; on pull_request that is a merge "
            f"commit, so the run is not exact-SHA evidence for the candidate."
        )

    assert any("Verify exact candidate SHA" == step.get("name") for step in steps), (
        f"{job_name} does not assert that the checked-out tree is the candidate SHA"
    )


def test_backend_matrix_is_six_disjoint_fail_complete_shards(workflow: dict) -> None:
    job = workflow["jobs"]["backend_tests"]

    assert job["strategy"]["fail-fast"] is False
    assert job["strategy"]["matrix"]["shard"] == [0, 1, 2, 3, 4, 5]
    run = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert "scripts/pytest_shard.py plan" in run
    assert '--shard-count 6' in run
    assert 'coverage run -m pytest -- "${shard_files[@]}"' in run
    assert "mapfile -t shard_files" in run
    upload = next(step for step in job["steps"] if step.get("uses") == "actions/upload-artifact@v4")
    assert upload["with"]["include-hidden-files"] is True


def test_named_backend_gate_fails_closed_on_any_prerequisite(workflow: dict) -> None:
    job = workflow["jobs"]["backend"]

    assert job["name"] == "backend lint · tests"
    assert job["if"] == "${{ always() }}"
    assert set(job["needs"]) == {"backend_static", "backend_tests"}
    first_step = job["steps"][0]
    assert first_step["name"] == "Require every backend prerequisite"
    assert first_step["env"] == {
        "STATIC_RESULT": "${{ needs.backend_static.result }}",
        "TESTS_RESULT": "${{ needs.backend_tests.result }}",
    }
    assert '!= "success"' in first_step["run"]


def test_backend_aggregate_verifies_manifests_before_combining_coverage(workflow: dict) -> None:
    steps = workflow["jobs"]["backend"]["steps"]
    download = next(step for step in steps if step.get("uses") == "actions/download-artifact@v4")
    assert download["with"] == {
        "pattern": "r17-backend-shard-*",
        "path": "coverage/artifacts/backend",
    }
    combine = next(
        step for step in steps if step.get("name") == "Verify and combine backend coverage shards"
    )["run"]
    assert combine.index("scripts/pytest_shard.py verify") < combine.index("coverage combine")
    assert "--shard-count 6" in combine
    provenance = next(
        step for step in steps if step.get("name") == "Record backend coverage producer provenance"
    )["run"]
    for field in ("inventory_sha256", "inventory_nodeid_count", "shards"):
        assert field in provenance


def test_preprod_tests_execute_only_inside_authoritative_matrix(workflow: dict) -> None:
    static_steps = yaml.safe_dump(workflow["jobs"]["backend_static"]["steps"])
    aggregate_steps = yaml.safe_dump(workflow["jobs"]["backend"]["steps"])
    matrix_steps = yaml.safe_dump(workflow["jobs"]["backend_tests"]["steps"])

    assert "scripts/verify_preprod.sh --static-only" in static_steps
    assert "coverage run -m pytest" not in static_steps
    assert "pytest -q" not in static_steps
    assert "coverage run -m pytest" not in aggregate_steps
    assert "pytest -q" not in aggregate_steps
    assert matrix_steps.count("coverage run -m pytest") == 1
    verify_preprod = (REPO_ROOT / "scripts/verify_preprod.sh").read_text()
    assert "--static-only" in verify_preprod
    assert (
        "tests/test_preprod_operations.py tests/test_w403a_release_preparation.py"
        in verify_preprod
    )

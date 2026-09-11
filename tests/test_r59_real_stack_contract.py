from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _job(workflow: str, job_id: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(job_id)}:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
        workflow,
    )
    assert match is not None, f"missing CI job {job_id}"
    return match.group(0)


def test_ci_has_separate_exact_candidate_r59_authority() -> None:
    workflow = _read(".github/workflows/ci.yml")
    ordinary_e2e = _job(workflow, "e2e")
    r59 = _job(workflow, "r59_real_stack")

    assert "e2e against the real stack" in ordinary_e2e
    assert "run_r59_real_stack.sh" not in ordinary_e2e
    assert "R59 real-stack release journey" in r59
    assert "needs: quality" in r59
    assert "actions/checkout@v4" in r59
    assert "github.event.pull_request.head.sha || github.sha" in r59
    assert "./scripts/run_r59_real_stack.sh" in r59
    assert "playwright install --with-deps chromium" in r59
    assert "if: always()" in r59
    assert "r59-real-stack" in r59
    for mock_flag in ("W401C_SYNTHETIC", "W401D_SYNTHETIC", "W403B_SYNTHETIC"):
        assert mock_flag not in r59


def test_playwright_separates_ordinary_and_specialist_modes() -> None:
    config = _read("frontend/playwright.config.ts")

    assert "Specialist modes are opt-in and mutually exclusive" in config
    assert 'process.env.R59_REAL_STACK === "1"' in config
    assert 'process.env.R14_SECURITY_BOUNDARY === "1"' in config
    assert "selectedModes.length > 1" in config
    assert 'const mode = selectedModes[0]?.[0] ?? "ordinary"' in config
    assert 'testMatch: mode === "ordinary" ? undefined : specialistSpecByMode[mode]' in config
    assert 'testIgnore: mode === "ordinary" ? specialistSpecs : undefined' in config
    for specialist_spec in (
        "r59-real-stack.spec.ts",
        "security-boundary.spec.ts",
        "w401c-campaign-journey.spec.ts",
        "w401d-release-rehearsal.spec.ts",
        "w403b-synthetic-pilot-journey.spec.ts",
    ):
        assert config.count(specialist_spec) == 2
    assert 'const w401cMockServer = mode === "w401c" || mode === "w403b"' in config
    assert 'fullyParallel: mode !== "ordinary" && !r59RealStack' in config
    assert "retries: r59RealStack ? 0" in config
    assert 'workers: mode === "ordinary" || r59RealStack ? 1' in config
    assert 'name: "r59-chromium"' in config
    assert "webServer: r59RealStack" in config


def test_r59_spec_is_one_serial_no_mock_browser_journey() -> None:
    spec = _read("frontend/e2e/r59-real-stack.spec.ts")

    assert 'test.describe.configure({ mode: "serial" })' in spec
    assert "R59_REAL_STACK" in spec
    assert "R59_BROWSER_RECEIPT=" in spec
    assert "stopService" in spec
    assert "startService" in spec
    assert "waitForService" in spec
    assert "writeReceipt" in spec
    for forbidden in (
        "test.skip",
        "test.fixme",
        "page.route",
        "context.route",
        "page.request",
        "request.get",
        "request.post",
        "W401C",
        "W401D",
        "W403B",
        "mock-api",
    ):
        assert forbidden not in spec


def test_r59_compose_is_local_isolated_and_uses_production_commands() -> None:
    compose = _read("frontend/e2e/support/docker-compose.r59.yml")

    for service in ("db", "redis", "minio", "clamav", "mailpit", "api", "worker", "frontend"):
        assert re.search(rf"(?m)^  {service}:$", compose)
    assert '127.0.0.1:${R59_API_PORT:-48159}:8000' in compose
    assert '127.0.0.1:${R59_FRONTEND_PORT:-34159}:3000' in compose
    assert compose.count("ports: !reset []") >= 4
    assert "uvicorn app.main:app --host 0.0.0.0 --port 8000" in compose
    assert "--reload" not in compose
    assert "arq app.jobs.worker_entry.WorkerSettings" in compose
    assert "ENVIRONMENT: test" in compose
    assert "ALLOW_DEMO_SEED: \"true\"" in compose
    assert "F7_SEED_MAX_TRIPS_PER_DAY: \"1\"" in compose
    assert "PRIVACY_DISCLOSURE_LIVE_AUTHORIZED: \"false\"" in compose
    assert "MEASUREMENT_LIVE_ISSUANCE_AUTHORIZED: \"false\"" in compose
    assert "BUDGET_POLICY_EXTERNAL_APPROVED: \"false\"" in compose
    assert "PHONE_OPERATOR_EXTERNAL_APPROVED: \"false\"" in compose
    assert "PRIVACY_COLLECTION_LIVE_AUTHORIZED: \"false\"" in compose
    assert "PRIVACY_COLLECTION_SYNTHETIC_TEST_MODE: \"true\"" in compose


def test_wrapper_scopes_every_compose_mutation_and_always_tears_down() -> None:
    wrapper = _read("scripts/run_r59_real_stack.sh")

    assert "^cardvert-r59-[a-z0-9-]+$" in wrapper
    assert "docker compose ls --all --format json" in wrapper
    assert 'compose=(docker compose -p "$R59_PROJECT"' in wrapper
    assert "docker-compose.r59.yml" in wrapper
    assert 'trap cleanup EXIT INT TERM' in wrapper
    assert "trap - EXIT INT TERM" in wrapper
    assert '"${compose[@]}" down -v --remove-orphans' in wrapper
    assert '"${compose[@]}" down -v --remove-orphans || down_status=$?' in wrapper
    assert "original_status == 0 && down_status != 0" in wrapper
    assert '"${compose[@]}" up -d --build' in wrapper
    assert '"${compose[@]}" exec -T api alembic upgrade head' in wrapper
    assert '"${compose[@]}" exec -T api python -m app.seeds.demo' in wrapper
    assert "R59_REAL_STACK=1" in wrapper
    assert "--project=r59-chromium" in wrapper
    assert "--workers=1" in wrapper
    assert "--retries=0" in wrapper
    assert not re.search(r"(?m)^\s*docker\s+(?:stop|rm)\b", wrapper)
    assert not re.search(r"(?m)^\s*docker\s+compose\s+down\b", wrapper)


def test_stack_helper_enforces_project_scope_and_sanitized_receipt() -> None:
    helper = _read("frontend/e2e/support/r59-stack.ts")

    assert "^cardvert-r59-[a-z0-9-]+$" in helper
    assert "docker" in helper and "compose" in helper and "-p" in helper
    assert "SELECT" in helper
    assert "redis-cli" in helper
    assert "sanitizeReceipt" in helper
    assert "assertNoSensitiveReceiptData" in helper
    assert "R59_REAL_STACK_RECEIPT.json" in helper
    for live_value in (
        'PRIVACY_DISCLOSURE_LIVE_AUTHORIZED: "true"',
        'MEASUREMENT_LIVE_ISSUANCE_AUTHORIZED: "true"',
        'BUDGET_POLICY_EXTERNAL_APPROVED: "true"',
        'PHONE_OPERATOR_EXTERNAL_APPROVED: "true"',
    ):
        assert live_value not in helper


def test_w401_modes_and_documentation_are_explicitly_ui_only() -> None:
    config = _read("frontend/playwright.config.ts")
    rehearsal = _read("docs/pkg-07-w4-01d-release-rehearsal.md")

    assert "W401C_SYNTHETIC" in config
    assert "W401D_SYNTHETIC" in config
    assert "W403B_SYNTHETIC" in config
    assert "UI-only synthetic rehearsal" in rehearsal
    assert "not real-stack release authority" in rehearsal


def test_r14_security_boundary_has_an_explicit_external_edge_mode() -> None:
    config = _read("frontend/playwright.config.ts")
    readme = _read("frontend/README.md")

    assert 'process.env.R14_SECURITY_BOUNDARY === "1"' in config
    assert 'r14: "**/security-boundary.spec.ts"' in config
    assert "r59RealStack || r14SecurityBoundary" in config
    assert "R14_SECURITY_BOUNDARY=1" in readme
    assert "PLAYWRIGHT_BASE_URL=https://" in readme


def test_mutating_ordinary_journeys_use_isolated_campaigns() -> None:
    fixture = _read("frontend/e2e/support/campaign-fixture.ts")
    cancellation = _read("frontend/e2e/campaign-cancellation.spec.ts")
    campaign_change = _read("frontend/e2e/campaign-change.spec.ts")

    assert "createIsolatedActiveCampaign" in fixture
    assert "cleanupIsolatedCampaign" in fixture
    assert "synthetic_e2e_fixture" in fixture
    assert "SET session_replication_role = replica" in fixture
    for spec in (cancellation, campaign_change):
        assert "createIsolatedActiveCampaign" in spec
        assert "finally" in spec
        assert "cleanupIsolatedCampaign(campaignId)" in spec
        assert 'getByRole("link", { name: "Demo Lagos Mobility Campaign" })' not in spec

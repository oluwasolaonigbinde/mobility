"""Regression tests for the fail-closed changed-code coverage policy."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

import pytest

import coverage as coverage_module

CHECKER = Path(__file__).parents[1] / "scripts" / "check_changed_coverage.py"
REPOSITORY = CHECKER.parents[1]


def test_ci_routes_baseline_changes_through_the_reviewable_provenance_gate():
    workflow = (CHECKER.parents[1] / ".github/workflows/ci.yml").read_text()
    coverage_job = workflow.split("\n  coverage:\n", 1)[1].split("\n  e2e:\n", 1)[0]
    assert "--verify-baseline-provenance" in coverage_job
    assert "--sensitive-branches" in coverage_job
    assert "--backend-provenance" in coverage_job
    assert "backend-provenance.json" in workflow
    assert "Record backend coverage producer provenance" in workflow
    assert "baseline is immutable after its one bootstrap commit" not in coverage_job
    assert "--refresh-baseline" not in coverage_job


def test_ci_runs_when_the_coverage_receipt_changes() -> None:
    workflow = (CHECKER.parents[1] / ".github/workflows/ci.yml").read_text()
    push_paths = workflow.split("  push:\n", 1)[1].split("  pull_request:\n", 1)[0]
    pull_request_paths = workflow.split("  pull_request:\n", 1)[1].split("\nconcurrency:", 1)[0]

    assert "paths:" not in push_paths + pull_request_paths
    assert "paths-ignore:" not in push_paths + pull_request_paths


def test_ratchet_tolerance_absorbs_noise_but_not_real_drops() -> None:
    spec = importlib.util.spec_from_file_location("coverage_policy_tolerance", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    def metrics(line_covered: int, branch_covered: int = 700) -> dict[str, float | int]:
        return {
            "line_covered": line_covered,
            "line_total": 10_000,
            "line_percent": line_covered / 100,
            "branch_covered": branch_covered,
            "branch_total": 1_000,
            "branch_percent": branch_covered / 10,
        }

    floor = metrics(8_800)
    tolerance = module.RATCHET_TOLERANCE_POINTS
    assert tolerance == module.Fraction(3, 10)
    # 0.3 points is within; 0.4 points is a real drop, for lines and for branches.
    module._assert_not_regressed(
        "global", metrics(8_770, branch_covered=697), floor, tolerance=tolerance
    )
    with pytest.raises(module.PolicyError, match="regressed"):
        module._assert_not_regressed("global", metrics(8_760), floor, tolerance=tolerance)
    with pytest.raises(module.PolicyError, match="regressed"):
        module._assert_not_regressed(
            "global", metrics(8_800, branch_covered=696), floor, tolerance=tolerance
        )
    # Exact comparisons (refresh adoption) keep zero tolerance.
    with pytest.raises(module.PolicyError, match="regressed"):
        module._assert_not_regressed("global", metrics(8_799), floor)


def test_exact_critical_paths_support_next_dynamic_segments() -> None:
    spec = importlib.util.spec_from_file_location("coverage_policy", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module._matches(
        "frontend/src/app/advertiser/[campaignId]/page.tsx",
        ["frontend/src/app/advertiser/[campaignId]/page.tsx"],
        "critical.frontend",
    )


def _run(command: list[str], cwd: Path) -> str:
    return subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True).stdout


def _write_lcov(
    path: Path, records: dict[str, tuple[dict[int, int], dict[int, list[int]]]]
) -> None:
    parts: list[str] = []
    for source, (lines, branches) in records.items():
        parts.append(f"SF:{source}")
        parts.extend(f"DA:{line},{hits}" for line, hits in sorted(lines.items()))
        for line, hits in sorted(branches.items()):
            parts.extend(f"BRDA:{line},0,{index},{hit}" for index, hit in enumerate(hits))
        parts.append("end_of_record")
    path.write_text("\n".join(parts) + "\n")


def _repository(tmp_path: Path, *, renamed: bool = False) -> tuple[Path, str, Path, Path, Path]:
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "frontend" / "src").mkdir(parents=True)
    backend = repo / "app" / "sample.py"
    frontend = repo / "frontend" / "src" / "sample.ts"
    backend.write_text("def value(flag):\n    return 1\n")
    (repo / "app" / "removed.py").write_text("def removed():\n    return 1\n")
    frontend.write_text("export const value = 1;\n")
    _run(["git", "init", "--quiet"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Coverage Test"], repo)
    _run(["git", "config", "core.autocrlf", "false"], repo)
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "--quiet", "-m", "base"], repo)
    base = _run(["git", "rev-parse", "HEAD"], repo).strip()
    if renamed:
        backend.rename(repo / "app" / "renamed.py")
        backend = repo / "app" / "renamed.py"
    else:
        backend.write_text("def value(flag):\n    if flag:\n        return 1\n    return 0\n")
    return repo, base, backend, frontend, repo / "coverage"


def _baseline(path: Path, *, line: float = 100.0, branch: float = 100.0) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "global": {"line_percent": line, "branch_percent": branch},
                "critical": {
                    "backend": {
                        "paths": ["app/**/*.py"],
                        "line_percent": line,
                        "branch_percent": branch,
                    },
                    "frontend": {
                        "paths": ["frontend/src/**/*.ts", "frontend/src/**/*.tsx"],
                        "line_percent": line,
                        "branch_percent": branch,
                    },
                },
            }
        )
    )


def _check(
    repo: Path, base: str, backend_lcov: Path, frontend_lcov: Path, baseline: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-S",
            str(CHECKER),
            "--repo-root",
            str(repo),
            "--base",
            base,
            "--backend-lcov",
            str(backend_lcov),
            "--frontend-lcov",
            str(frontend_lcov),
            "--baseline",
            str(baseline),
        ],
        text=True,
        capture_output=True,
    )


def test_accepts_changed_eligible_code_at_required_floors_and_exact_baselines(
    tmp_path: Path,
) -> None:
    repo, base, backend, frontend, coverage = _repository(tmp_path)
    coverage.mkdir()
    backend_lcov = coverage / "backend.lcov"
    frontend_lcov = coverage / "frontend.lcov"
    _write_lcov(backend_lcov, {str(backend): ({1: 1, 2: 1, 3: 1, 4: 1}, {2: [1, 1]})})
    _write_lcov(frontend_lcov, {str(frontend): ({1: 1}, {})})
    baseline = coverage / "baseline.json"
    _baseline(baseline)

    result = _check(repo, base, backend_lcov, frontend_lcov, baseline)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["changed"]["line_percent"] == 100.0
    assert report["changed"]["branch_percent"] == 100.0
    assert report["changed"]["added"] == []
    assert report["changed"]["modified"] == ["app/sample.py"]


def test_rejects_changed_code_below_the_branch_floor(tmp_path: Path) -> None:
    repo, base, backend, frontend, coverage = _repository(tmp_path)
    coverage.mkdir()
    backend_lcov = coverage / "backend.lcov"
    frontend_lcov = coverage / "frontend.lcov"
    _write_lcov(backend_lcov, {str(backend): ({1: 1, 2: 1, 3: 1, 4: 1}, {2: [1, 0]})})
    _write_lcov(frontend_lcov, {str(frontend): ({1: 1}, {})})
    baseline = coverage / "baseline.json"
    _baseline(baseline, branch=50.0)

    result = _check(repo, base, backend_lcov, frontend_lcov, baseline)

    assert result.returncode == 1
    assert "changed branch coverage" in result.stderr


def test_accepts_coverage_py_descriptive_branch_identifier(tmp_path: Path) -> None:
    repo, base, backend, frontend, coverage = _repository(tmp_path)
    coverage.mkdir()
    backend_lcov = coverage / "backend.lcov"
    frontend_lcov = coverage / "frontend.lcov"
    backend_lcov.write_text(
        f"SF:{backend}\nDA:1,1\nDA:2,1\nDA:3,1\nDA:4,1\nBRDA:2,0,jump to line 3,1\nend_of_record\n"
    )
    _write_lcov(frontend_lcov, {str(frontend): ({1: 1}, {})})
    baseline = coverage / "baseline.json"
    _baseline(baseline)

    result = _check(repo, base, backend_lcov, frontend_lcov, baseline)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["changed"]["branch_percent"] == 100.0


def test_renamed_file_is_checked_and_deleted_file_is_reported(tmp_path: Path) -> None:
    repo, base, backend, frontend, coverage = _repository(tmp_path, renamed=True)
    (repo / "app" / "removed.py").unlink()
    _run(["git", "add", "-A"], repo)
    coverage.mkdir()
    backend_lcov = coverage / "backend.lcov"
    frontend_lcov = coverage / "frontend.lcov"
    _write_lcov(backend_lcov, {str(backend): ({1: 1, 2: 1}, {})})
    _write_lcov(frontend_lcov, {str(frontend): ({1: 1}, {})})
    baseline = coverage / "baseline.json"
    _baseline(baseline)

    result = _check(repo, base, backend_lcov, frontend_lcov, baseline)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["changed"]["renamed"] == ["app/renamed.py"]
    assert report["changed"]["deleted"] == ["app/removed.py"]


def test_untracked_eligible_source_is_not_silently_skipped(tmp_path: Path) -> None:
    repo, base, backend, frontend, coverage = _repository(tmp_path)
    new_source = repo / "app" / "new.py"
    new_source.write_text("def new_value():\n    return 1\n")
    coverage.mkdir()
    backend_lcov = coverage / "backend.lcov"
    frontend_lcov = coverage / "frontend.lcov"
    _write_lcov(
        backend_lcov,
        {
            str(backend): ({1: 1, 2: 1, 3: 1, 4: 1}, {}),
            str(new_source): ({1: 1, 2: 1}, {}),
        },
    )
    _write_lcov(frontend_lcov, {str(frontend): ({1: 1}, {})})
    baseline = coverage / "baseline.json"
    _baseline(baseline)

    result = _check(repo, base, backend_lcov, frontend_lcov, baseline)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["changed"]["untracked"] == ["app/new.py"]
    assert report["changed"]["modified"] == ["app/sample.py"]


def test_rejects_invalid_base_and_malformed_or_missing_lcov(tmp_path: Path) -> None:
    repo, base, backend, frontend, coverage = _repository(tmp_path)
    coverage.mkdir()
    backend_lcov = coverage / "backend.lcov"
    frontend_lcov = coverage / "frontend.lcov"
    _write_lcov(backend_lcov, {str(backend): ({1: 1, 2: 1, 3: 1, 4: 1}, {})})
    _write_lcov(frontend_lcov, {str(frontend): ({1: 1}, {})})
    baseline = coverage / "baseline.json"
    _baseline(baseline)

    invalid_base = _check(repo, "not-a-full-sha", backend_lcov, frontend_lcov, baseline)
    assert invalid_base.returncode == 1
    assert "40-character" in invalid_base.stderr

    backend_lcov.write_text(f"SF:{backend}\nDA:1,1\n")
    malformed = _check(repo, base, backend_lcov, frontend_lcov, baseline)
    assert malformed.returncode == 1
    assert "end_of_record" in malformed.stderr

    missing = _check(repo, base, coverage / "missing.lcov", frontend_lcov, baseline)
    assert missing.returncode == 1
    assert "missing coverage report" in missing.stderr

    _write_lcov(backend_lcov, {str(backend): ({1: 1, 2: 1, 3: 1, 4: 1}, {})})
    _write_lcov(frontend_lcov, {str(backend): ({1: 1}, {})})
    conflicting = _check(repo, base, backend_lcov, frontend_lcov, baseline)
    assert conflicting.returncode == 1
    assert "conflicting backend/frontend LCOV source" in conflicting.stderr

    _write_lcov(backend_lcov, {str(repo / "app" / "missing.py"): ({1: 1}, {})})
    invalid_source = _check(repo, base, backend_lcov, frontend_lcov, baseline)
    assert invalid_source.returncode == 1
    assert "not a current regular file" in invalid_source.stderr


def test_no_eligible_change_is_explicit_and_still_checks_baselines(tmp_path: Path) -> None:
    repo, base, backend, frontend, coverage = _repository(tmp_path)
    backend.write_text("def value(flag):\n    return 1\n")
    coverage.mkdir()
    backend_lcov = coverage / "backend.lcov"
    frontend_lcov = coverage / "frontend.lcov"
    _write_lcov(backend_lcov, {str(backend): ({1: 1, 2: 1}, {})})
    _write_lcov(frontend_lcov, {str(frontend): ({1: 1}, {})})
    baseline = coverage / "baseline.json"
    _baseline(baseline)

    result = _check(repo, base, backend_lcov, frontend_lcov, baseline)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["changed"]["line_total"] == 0
    assert report["changed"]["no_eligible_changes"] is True
    assert report["changed"]["added"] == []
    assert report["changed"]["modified"] == []


def test_singular_test_fixture_and_migration_directories_are_excluded(tmp_path: Path) -> None:
    repo, base, backend, frontend, coverage = _repository(tmp_path)
    for directory in ("test", "fixture", "migration"):
        path = repo / "app" / directory / "helper.py"
        path.parent.mkdir()
        path.write_text("def excluded():\n    return 1\n")
    coverage.mkdir()
    backend_lcov = coverage / "backend.lcov"
    frontend_lcov = coverage / "frontend.lcov"
    _write_lcov(backend_lcov, {str(backend): ({1: 1, 2: 1, 3: 1, 4: 1}, {})})
    _write_lcov(frontend_lcov, {str(frontend): ({1: 1}, {})})
    baseline = coverage / "baseline.json"
    _baseline(baseline)

    result = _check(repo, base, backend_lcov, frontend_lcov, baseline)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["changed"]["modified"] == ["app/sample.py"]


def _refresh_repository(tmp_path: Path):
    repo, _, backend, frontend, coverage = _repository(tmp_path)
    backend.write_text("def value(flag):\n    return 1\n")
    (repo / "app" / "__init__.py").write_text('"""Package marker."""\n')
    coverage.mkdir()
    (repo / ".github/workflows").mkdir(parents=True)
    (repo / ".github/workflows/ci.yml").write_bytes(
        (REPOSITORY / ".github/workflows/ci.yml").read_bytes()
    )
    (repo / "docs/evidence").mkdir(parents=True)
    (repo / "docs/evidence/coverage-runtime-34354263174.json").write_text("{}\n")
    baseline = coverage / "baseline.json"
    (repo / "scripts").mkdir()
    (repo / "scripts" / CHECKER.name).write_bytes(CHECKER.read_bytes())
    for name in (
        "scripts/pytest_shard.py",
        "scripts/install_ci_dependencies.py",
        "scripts/ci_load_minio_images.sh",
        ".github/actions/verify-candidate-sha/action.yml",
        "requirements-production.txt",
        "frontend/.nvmrc",
    ):
        destination = repo / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REPOSITORY / name).read_bytes())
    for name in (
        "pyproject.toml",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/vitest.config.ts",
    ):
        (repo / name).write_text("{}\n")
    (repo / "pyproject.toml").write_text(
        '[project.optional-dependencies]\ndev = ["coverage==7.16.0", "pytest>=8.3,<9.0"]\n'
        '[tool.coverage.run]\nbranch = true\nsource = ["app"]\n'
    )
    tools = {name: "^1.0.0" for name in (
        "vitest", "@vitest/coverage-v8", "@vitejs/plugin-react", "jsdom"
    )}
    (repo / "frontend/package.json").write_text(json.dumps({
        "scripts": {"test": "vitest run"}, "devDependencies": tools,
    }))
    (repo / "frontend/package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {f"node_modules/{name}": {"version": "1.0.0"} for name in tools},
    }))
    (repo / "frontend/vitest.config.ts").write_text(
        'export default {coverage: {provider: "v8"}};\n'
    )
    metrics = {
        "line_covered": 5,
        "line_total": 5,
        "line_percent": 100.0,
        "branch_covered": 0,
        "branch_total": 0,
        "branch_percent": 100.0,
    }
    backend_metrics = {**metrics, "line_covered": 4, "line_total": 4}
    frontend_metrics = {**metrics, "line_covered": 1, "line_total": 1}
    baseline.write_text(
        json.dumps(
            {
                "version": 1,
                "global": metrics,
                "critical": {
                    "backend": {**backend_metrics, "paths": ["app/removed.py", "app/sample.py"]},
                    "frontend": {**frontend_metrics, "paths": ["frontend/src/sample.ts"]},
                },
            }
        )
    )
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "--quiet", "-m", "trusted coverage authority"], repo)
    base = _run(["git", "rev-parse", "HEAD"], repo).strip()
    backend_lcov, frontend_lcov = coverage / "backend.lcov", coverage / "frontend.lcov"

    def reports(*, omit: str | None = None, uncovered: bool = False):
        _write_lcov(
            backend_lcov,
            {
                str(path): ({1: 1, 2: 0 if uncovered else 1}, {})
                for path in (repo / "app").glob("*.py")
                if path.name not in {"__init__.py", omit}
            },
        )
        _write_lcov(frontend_lcov, {str(frontend): ({1: 1}, {})})

    def check(*, refresh: bool = False, comparison_base: str | None = None):
        command = [
            sys.executable,
            str(CHECKER),
            "--repo-root",
            str(repo),
            "--base",
            comparison_base or base,
            "--backend-lcov",
            str(backend_lcov),
            "--frontend-lcov",
            str(frontend_lcov),
            "--baseline",
            str(baseline),
            "--verify-baseline-provenance",
        ]
        if refresh:
            command += ["--refresh-baseline", "Reviewed source inventory correction"]
        return subprocess.run(command, text=True, capture_output=True)

    return repo, base, baseline, reports, check


@pytest.mark.parametrize("change", ["add", "rename", "delete", "policy"])
def test_controlled_refresh_accepts_inventory_and_policy_changes(tmp_path: Path, change: str):
    repo, base, baseline, reports, check = _refresh_repository(tmp_path)
    if change == "add":
        (repo / "app" / "new.py").write_text("def new():\n    return 1\n")
    elif change == "rename":
        (repo / "app" / "removed.py").rename(repo / "app" / "renamed.py")
    elif change == "delete":
        (repo / "app" / "removed.py").unlink()
    else:
        lock = repo / "frontend/package-lock.json"
        value = json.loads(lock.read_text())
        value["packages"]["node_modules/vitest"]["version"] = "1.1.0"
        lock.write_text(json.dumps(value))
    reports()
    result = check(refresh=True)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(baseline.read_text())
    assert receipt["source_parent_sha"] == base
    assert receipt["refresh"]["reason"] == "Reviewed source inventory correction"
    assert "app/__init__.py" in receipt["critical"]["backend"]["paths"]
    assert check().returncode == 0
    assert json.loads(result.stdout)["baseline_refreshed"] is True


def test_refresh_refuses_missing_unchanged_source_coverage(tmp_path: Path):
    _, _, baseline, reports, check = _refresh_repository(tmp_path)
    before = baseline.read_bytes()
    reports(omit="removed.py")
    result = check(refresh=True)
    assert result.returncode == 1
    assert "absent from LCOV" in result.stderr
    assert baseline.read_bytes() == before


def test_refresh_cannot_lower_trusted_ratchet_using_candidate_baseline(tmp_path: Path):
    _, _, baseline, reports, check = _refresh_repository(tmp_path)
    candidate = json.loads(baseline.read_text())
    for scope in [candidate["global"], *candidate["critical"].values()]:
        scope.update(line_percent=0, line_covered=0)
    baseline.write_text(json.dumps(candidate))
    reports(uncovered=True)
    result = check(refresh=True)
    assert result.returncode == 1
    assert "coverage regressed" in result.stderr


def test_refresh_rejects_an_existing_nonancestor_commit(tmp_path: Path):
    repo, _, _, reports, check = _refresh_repository(tmp_path)
    tree = _run(["git", "rev-parse", "HEAD^{tree}"], repo).strip()
    unrelated = _run(["git", "commit-tree", tree, "-m", "unrelated authority"], repo).strip()
    reports()
    result = check(refresh=True, comparison_base=unrelated)
    assert result.returncode == 1
    assert "merge-base --is-ancestor" in result.stderr


def test_refresh_rejects_candidate_source_eligibility_exclusion(tmp_path: Path, monkeypatch):
    from argparse import Namespace

    repo, base, baseline, reports, _ = _refresh_repository(tmp_path)
    reports()
    spec = importlib.util.spec_from_file_location("coverage_policy_exclusion", CHECKER)
    assert spec is not None and spec.loader is not None
    policy = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = policy
    spec.loader.exec_module(policy)
    original = policy._eligible
    monkeypatch.setattr(
        policy, "_eligible", lambda path: path != "app/removed.py" and original(path)
    )
    with pytest.raises(policy.PolicyError, match="source eligibility drift"):
        policy._evaluate(
            Namespace(
                repo_root=repo,
                base=base,
                backend_lcov=repo / "coverage/backend.lcov",
                frontend_lcov=repo / "coverage/frontend.lcov",
                baseline=baseline,
                verify_baseline_provenance=True,
                refresh_baseline="Reviewed refresh",
            )
        )


@pytest.mark.parametrize("change", ["branch", "excluded_lines", "vitest", "empty_module"])
def test_refresh_does_not_authorize_weaker_instrumentation(tmp_path: Path, change: str):
    repo, _, _, reports, check = _refresh_repository(tmp_path)
    if change == "branch":
        path = repo / "pyproject.toml"
        path.write_text(path.read_text().replace("branch = true", "branch = false"))
    elif change == "excluded_lines":
        with (repo / "pyproject.toml").open("a") as config:
            config.write('\n[tool.coverage.report]\nexclude_lines = [".*"]\n')
    elif change == "vitest":
        (repo / "frontend/vitest.config.ts").write_text(
            "export default {coverage: {enabled: false}};"
        )
    else:
        (repo / "app/__init__.py").write_text("import os\n")
    reports()
    result = check(refresh=True)
    assert result.returncode == 1
    assert (
        "absent from LCOV" if change == "empty_module" else "instrumentation drift"
    ) in result.stderr


@pytest.mark.parametrize("tamper", ["floor", "policy", "inventory", "base", "source",
                                    "lineage", "nonancestor", "typed_floor"])
def test_ci_verifies_refresh_receipt_against_current_evidence(tmp_path: Path, tamper: str):
    repo, _, baseline, reports, check = _refresh_repository(tmp_path)
    reports()
    assert check(refresh=True).returncode == 0
    receipt = json.loads(baseline.read_text())
    if tamper == "floor":
        receipt["global"]["line_covered"] -= 1
    elif tamper == "policy":
        receipt["policy_sha256"] = "0" * 64
    elif tamper == "inventory":
        receipt["critical"]["backend"]["paths"].remove("app/removed.py")
    elif tamper == "base":
        receipt["source_parent_sha"] = "0" * 40
    elif tamper == "lineage":
        receipt["refresh"]["previous_baseline_sha256"] = "0" * 64
    elif tamper == "nonancestor":
        tree = _run(["git", "rev-parse", "HEAD^{tree}"], repo).strip()
        receipt["source_parent_sha"] = _run(
            ["git", "commit-tree", tree, "-m", "unrelated receipt origin"], repo
        ).strip()
    elif tamper == "typed_floor":
        receipt["global"]["branch_covered"] = False
    else:
        (repo / "app" / "sample.py").write_text("def value(flag):\n    return 2\n")
    baseline.write_text(json.dumps(receipt))
    result = check()
    assert result.returncode == 1
    assert "refresh" in result.stderr


def test_unchanged_committed_refresh_allows_no_change_and_covered_edits(tmp_path: Path):
    repo, _, baseline, reports, check = _refresh_repository(tmp_path)
    reports()
    assert check(refresh=True).returncode == 0
    _run(["git", "add", str(baseline)], repo)
    _run(["git", "commit", "--quiet", "-m", "reviewed baseline"], repo)
    # The next comparison trusts the committed receipt, without requiring another refresh.
    base = _run(["git", "rev-parse", "HEAD"], repo).strip()
    for edit in (False, True):
        if edit:
            (repo / "app" / "sample.py").write_text("def value(flag):\n    return 2\n")
        result = subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                "--repo-root",
                str(repo),
                "--base",
                base,
                "--backend-lcov",
                str(repo / "coverage/backend.lcov"),
                "--frontend-lcov",
                str(repo / "coverage/frontend.lcov"),
                "--baseline",
                str(baseline),
                "--verify-baseline-provenance",
            ],
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr


def _v3_repository(tmp_path: Path):
    repo, _, baseline, reports, _ = _refresh_repository(tmp_path)
    runtime = {"implementation": platform.python_implementation(),
               "major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
               "coverage_version": "7.16.0"}
    prior = json.loads(baseline.read_text())
    prior.update(version=3, backend_runtime=runtime)
    prior["global"].update(line_covered=3, line_percent=60.0)
    prior["critical"]["backend"].update(line_covered=2, line_percent=50.0)
    baseline.write_text(json.dumps(prior))
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "--quiet", "-m", "trusted v3 floors"], repo)
    origin = _run(["git", "rev-parse", "HEAD"], repo).strip()

    def check(*, refresh=False, comparison_base=None, tamper_producer=None):
        backend = repo / "coverage/backend.lcov"
        producer = {"version": 1,
                    "candidate_sha": _run(["git", "rev-parse", "HEAD"], repo).strip(),
                    "lcov_sha256": hashlib.sha256(backend.read_bytes()).hexdigest(),
                    "runtime": runtime}
        if tamper_producer:
            producer.update(tamper_producer)
        provenance = repo / "coverage/backend-provenance.json"
        provenance.write_text(json.dumps(producer))
        command = [sys.executable, "-S", str(CHECKER), "--repo-root", str(repo),
                   "--base", comparison_base or origin, "--backend-lcov", str(backend),
                   "--frontend-lcov", str(repo / "coverage/frontend.lcov"),
                   "--baseline", str(baseline), "--verify-baseline-provenance",
                   "--backend-provenance", str(provenance)]
        if refresh:
            command += ["--refresh-baseline", "Reviewed event-independent receipt"]
        return subprocess.run(command, text=True, capture_output=True)

    return repo, origin, baseline, reports, check


def test_committed_v3_receipt_accepts_branch_and_master_ancestor_bases(tmp_path: Path):
    # 8e509f7f: branch run 38571889225 used 4f41e895; master run
    # 38578629525 used 966abd3a. Both events measured the same candidate.
    repo, branch_base, baseline, reports, check = _v3_repository(tmp_path)
    (repo / "notes.txt").write_text("master ancestor, same prior baseline\n")
    _run(["git", "add", "notes.txt"], repo)
    _run(["git", "commit", "--quiet", "-m", "master ancestor"], repo)
    master_base = _run(["git", "rev-parse", "HEAD"], repo).strip()
    (repo / "app/sample.py").write_text("def value(flag):\n    return 2\n")
    reports()
    refreshed = check(refresh=True)
    assert refreshed.returncode == 0, refreshed.stderr
    _run(["git", "add", "app/sample.py", str(baseline)], repo)
    _run(["git", "commit", "--quiet", "-m", "same source and adopted receipt"], repo)
    receipt = baseline.read_bytes()
    for base in (branch_base, master_base):
        result = check(comparison_base=base)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["base"] == base
        assert json.loads(result.stdout)["changed"]["modified"] == ["app/sample.py"]
        assert baseline.read_bytes() == receipt


def test_event_base_still_controls_changed_code_checks(tmp_path: Path):
    repo, old_base, baseline, reports, check = _v3_repository(tmp_path)
    (repo / "app/sample.py").write_text("def value(flag):\n    return 2\n")
    _run(["git", "add", "app/sample.py"], repo)
    _run(["git", "commit", "--quiet", "-m", "source comparison boundary"], repo)
    new_base = _run(["git", "rev-parse", "HEAD"], repo).strip()
    reports(uncovered=True)
    refreshed = check(refresh=True, comparison_base=new_base)
    assert refreshed.returncode == 0, refreshed.stderr
    _run(["git", "add", str(baseline)], repo)
    _run(["git", "commit", "--quiet", "-m", "adopt existing floors"], repo)
    assert check(comparison_base=new_base).returncode == 0
    rejected = check(comparison_base=old_base)
    assert rejected.returncode == 1
    assert "changed line coverage 0.0%" in rejected.stderr


@pytest.mark.parametrize("measured", [False, True])
def test_receipt_origin_cannot_bypass_stronger_event_floors(tmp_path: Path, measured: bool):
    repo, _, baseline, reports, check = _v3_repository(tmp_path)
    reports(uncovered=True)
    assert check(refresh=True).returncode == 0
    adopted = baseline.read_bytes()
    stronger = json.loads(adopted)
    for metrics in (stronger["global"], *stronger["critical"].values()):
        metrics.update(line_covered=metrics["line_total"], line_percent=100.0)
    baseline.write_text(json.dumps(stronger))
    _run(["git", "add", str(baseline)], repo)
    _run(["git", "commit", "--quiet", "-m", "stronger event floors"], repo)
    event = _run(["git", "rev-parse", "HEAD"], repo).strip()
    baseline.write_bytes(adopted)
    reports(uncovered=measured)
    rejected = check(comparison_base=event)
    assert rejected.returncode == 1
    assert ("event.global" if measured else "adopted.global") in rejected.stderr


def test_typed_metric_tampering_cannot_masquerade_as_unchanged_receipt(tmp_path: Path):
    repo, _, baseline, reports, check = _v3_repository(tmp_path)
    reports()
    assert check(refresh=True).returncode == 0
    _run(["git", "add", str(baseline)], repo)
    _run(["git", "commit", "--quiet", "-m", "trusted receipt"], repo)
    event = _run(["git", "rev-parse", "HEAD"], repo).strip()
    altered = json.loads(baseline.read_text())
    altered["global"]["branch_covered"] = False
    baseline.write_text(json.dumps(altered))
    rejected = check(comparison_base=event)
    assert rejected.returncode == 1
    assert "invalid adopted coverage metrics" in rejected.stderr


@pytest.mark.parametrize("field", ["candidate_sha", "lcov_sha256", "runtime"])
def test_adopted_receipt_retains_exact_producer_provenance(tmp_path: Path, field: str):
    repo, _, baseline, reports, check = _v3_repository(tmp_path)
    reports()
    assert check(refresh=True).returncode == 0
    _run(["git", "add", str(baseline)], repo)
    _run(["git", "commit", "--quiet", "-m", "adopt receipt"], repo)
    value = {} if field == "runtime" else "0" * (40 if field == "candidate_sha" else 64)
    rejected = check(tamper_producer={field: value})
    assert rejected.returncode == 1
    assert "coverage policy failed:" in rejected.stderr
    assert "provenance" in rejected.stderr


def _policy_module():
    spec = importlib.util.spec_from_file_location("receipt_policy", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _policy_repository(tmp_path: Path):
    policy = _policy_module()
    repo = tmp_path / "policy-inputs"
    for path in (*policy.POLICY_FILES, ".github/workflows/ci.yml", "pyproject.toml",
                 "frontend/package.json", "frontend/package-lock.json"):
        destination = repo / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REPOSITORY / path).read_bytes())
    return repo, policy


def test_unrelated_workflow_edits_do_not_change_measurement_policy(tmp_path: Path):
    repo, policy = _policy_repository(tmp_path)
    path = repo / ".github/workflows/ci.yml"
    before = policy._policy_hash(repo)
    workflow = path.read_text()
    workflow = workflow.replace("timeout-minutes: 45", "timeout-minutes: 46")
    workflow = workflow.replace("fail-fast: false", "fail-fast: false\n      max-parallel: 2")
    workflow = workflow.replace("cache: pip", "cache: false")
    workflow = workflow.replace("cancel-in-progress: ${{ github.ref != 'refs/heads/master' }}",
                                "cancel-in-progress: false")
    workflow = workflow.replace("- uses: actions/upload-artifact@v4",
                                "- uses: actions/upload-artifact@v4\n        if: always()")
    path.write_text(workflow)
    (repo / "scripts/pytest_shard_durations.json").write_text('{"scheduling": "only"}\n')
    assert policy._policy_hash(repo) == before


def test_basedpyright_config_is_not_measurement_policy(tmp_path: Path):
    repo, policy = _policy_repository(tmp_path)
    before = policy._policy_hash(repo)
    project = repo / "pyproject.toml"
    content = project.read_text()
    replacement = '[tool.basedpyright]\nreportUnusedCallResult = false\n'
    if "[tool.basedpyright]" in content:
        content = re.sub(r"(?ms)^\[tool\.basedpyright\]\n.*?(?=^\[|\Z)", replacement, content)
    else:
        content += "\n" + replacement
    project.write_text(content)
    assert policy._policy_hash(repo) == before


def test_unrelated_frontend_package_and_lock_edits_preserve_measurement_policy(tmp_path: Path):
    repo, policy = _policy_repository(tmp_path)
    before = policy._policy_hash(repo)
    path = repo / "frontend/package.json"
    package = json.loads(path.read_text())
    package["description"] = "Unrelated metadata"
    package["scripts"]["build"] = "echo unrelated build"
    package["devDependencies"]["eslint"] = "^99.0.0"
    path.write_text(json.dumps(package))
    path = repo / "frontend/package-lock.json"
    lock = json.loads(path.read_text())
    lock["name"] = "Unrelated metadata"
    lock["packages"][""]["devDependencies"]["eslint"] = "^99.0.0"
    lock["packages"]["node_modules/eslint"]["version"] = "99.0.0"
    path.write_text(json.dumps(lock))
    assert policy._policy_hash(repo) == before


@pytest.mark.parametrize(("old", "new"), [
    ('concurrency = ["thread", "greenlet"]', 'concurrency = ["thread"]'),
    ('testpaths = ["tests"]', 'testpaths = ["tests/unit"]'),
    ('coverage[toml]==7.16.0', 'coverage[toml]==7.17.0'),
    ('pytest>=8.3,<9.0', 'pytest>=8.4,<9.0'),
])
def test_python_measurement_configuration_changes_policy(tmp_path: Path, old: str, new: str):
    repo, policy = _policy_repository(tmp_path)
    before = policy._policy_hash(repo)
    path = repo / "pyproject.toml"
    content = path.read_text()
    assert old in content
    path.write_text(content.replace(old, new))
    assert policy._policy_hash(repo) != before


@pytest.mark.parametrize(("dependency", "old", "new"), [
    ("pluggy", "1.5.0", "1.6.0"), ("packaging", "24.2", "25.0"),
    ("iniconfig", "2.1.0", "2.3.0"),
])
def test_explicit_transitive_python_tool_pins_are_measurement_policy(
    tmp_path: Path, dependency: str, old: str, new: str,
):
    repo, policy = _policy_repository(tmp_path)
    project = repo / "pyproject.toml"
    project.write_text(
        '[project.optional-dependencies]\n'
        f'dev = ["coverage==7.16.0", "pytest>=8.3,<9.0", "{dependency}=={old}"]\n'
    )
    before = policy._policy_hash(repo)
    project.write_text(project.read_text().replace(f"{dependency}=={old}", f"{dependency}=={new}"))
    assert policy._policy_hash(repo) != before


@pytest.mark.parametrize("script", ["prelint", "postlint", "pretypecheck", "posttypecheck",
                                   "lint", "typecheck"])
def test_lint_typecheck_preparation_hooks_and_changed_bodies_are_bound(tmp_path: Path, script: str):
    repo, policy = _policy_repository(tmp_path)
    before = policy._policy_hash(repo)
    path = repo / "frontend/package.json"
    package = json.loads(path.read_text())
    package["scripts"][script] = 'echo "NODE_ENV=production" >> "$GITHUB_ENV"'
    path.write_text(json.dumps(package))
    assert policy._policy_hash(repo) != before


@pytest.mark.parametrize("context", [
    "        env:\n          NODE_OPTIONS: --require=./preload.cjs\n",
    "        shell: bash\n",
    "        working-directory: .\n",
])
def test_lint_step_measurement_preparation_context_is_bound(tmp_path: Path, context: str):
    repo, policy = _policy_repository(tmp_path)
    before = policy._policy_hash(repo)
    path = repo / ".github/workflows/ci.yml"
    command = "      - run: npm run lint\n"
    workflow = path.read_text()
    assert command in workflow
    path.write_text(workflow.replace(command, command + context))
    assert policy._policy_hash(repo) != before


@pytest.mark.parametrize("change", ["tool_range", "test_command", "test_hook", "transitive",
                                   "provider_integrity", "missing_tool", "missing_transitive"])
def test_frontend_measurement_configuration_and_tool_closure_are_bound(tmp_path: Path, change: str):
    repo, policy = _policy_repository(tmp_path)
    before = policy._policy_hash(repo)
    path = repo / "frontend/package.json"
    package = json.loads(path.read_text())
    lock_path = repo / "frontend/package-lock.json"
    lock = json.loads(lock_path.read_text())
    if change == "tool_range":
        package["devDependencies"]["vitest"] = "99.0.0"
    elif change == "test_command":
        package["scripts"]["test"] += " --pool=threads"
    elif change == "test_hook":
        package["scripts"]["pretest"] = "echo preparation"
    elif change == "transitive":
        lock["packages"]["node_modules/vite"]["version"] = "99.0.0"
    elif change == "provider_integrity":
        lock["packages"]["node_modules/@vitest/coverage-v8"]["integrity"] = "tampered"
    else:
        name = "@vitest/coverage-v8" if change == "missing_tool" else "vite"
        del lock["packages"][f"node_modules/{name}"]
    path.write_text(json.dumps(package))
    lock_path.write_text(json.dumps(lock))
    if change.startswith("missing_"):
        with pytest.raises(policy.PolicyError, match="measurement lock is missing dependency"):
            policy._policy_hash(repo)
    else:
        assert policy._policy_hash(repo) != before


@pytest.mark.parametrize(("old", "new"), [
    ("coverage run -m pytest", "coverage run --timid -m pytest"),
    ("coverage lcov", "coverage lcov --ignore-errors"),
    ("npm run test -- --coverage", "npm run test -- --coverage --pool=threads"),
    ('python-version: "3.12.14"', 'python-version: "3.13.0"'),
    ('REQUIRE_REAL_INTEGRATIONS: "1"', 'REQUIRE_REAL_INTEGRATIONS: "0"'),
    ("shard: [0, 1, 2, 3, 4, 5]", "shard: [0, 1, 2, 3, 4]"),
    ("image: redis:7-alpine", "image: redis:8-alpine"),
    ("coverage combine", "echo mutate >> $GITHUB_ENV\n          coverage combine"),
])
def test_measurement_workflow_changes_are_detected(tmp_path: Path, old: str, new: str):
    repo, policy = _policy_repository(tmp_path)
    path = repo / ".github/workflows/ci.yml"
    before = policy._policy_hash(repo)
    workflow = path.read_text()
    assert old in workflow
    path.write_text(workflow.replace(old, new))
    assert policy._policy_hash(repo) != before


@pytest.mark.parametrize("path", ["scripts/pytest_shard.py", "scripts/install_ci_dependencies.py",
                                 "scripts/ci_load_minio_images.sh",
                                 ".github/actions/verify-candidate-sha/action.yml",
                                 "requirements-production.txt", "frontend/.nvmrc"])
def test_measurement_helper_changes_and_missing_files_fail_closed(tmp_path: Path, path: str):
    repo, policy = _policy_repository(tmp_path)
    before = policy._policy_hash(repo)
    helper = repo / path
    helper.write_bytes(helper.read_bytes() + b"\n# measurement change\n")
    assert policy._policy_hash(repo) != before
    helper.unlink()
    with pytest.raises(policy.PolicyError, match="missing provenance source"):
        policy._policy_hash(repo)


@pytest.mark.parametrize(("old", "new"), [
    ("  backend_tests:", "  renamed_producer:"),
    ("coverage lcov", "echo no report"),
    ("coverage combine", "python scripts/unreviewed.py\n          coverage combine"),
    ("./.github/actions/verify-candidate-sha", "./.github/actions/unreviewed"),
    ("    steps:", "    steps: *dynamic_steps"),
    ("      REQUIRE_REAL_INTEGRATIONS:", "      <<: *defaults\n      REQUIRE_REAL_INTEGRATIONS:"),
    ('      REQUIRE_REAL_INTEGRATIONS: "1"',
     '      REQUIRE_REAL_INTEGRATIONS: "1"\n      REQUIRE_REAL_INTEGRATIONS: "0"'),
    ("    env:\n", "    env: {REQUIRE_REAL_INTEGRATIONS: 0}\n"),
])
def test_unsupported_measurement_workflow_fails_closed(tmp_path: Path, old: str, new: str):
    repo, policy = _policy_repository(tmp_path)
    path = repo / ".github/workflows/ci.yml"
    workflow = path.read_text()
    assert old in workflow
    path.write_text(workflow.replace(old, new))
    with pytest.raises(policy.PolicyError, match="measurement workflow"):
        policy._policy_hash(repo)


def _runtime_reconciliation_evidence(
    repo: Path,
    base: str,
    backend_lcov: Path,
    frontend_lcov: Path,
) -> tuple[Path, Path]:
    runtime = {
        "implementation": platform.python_implementation(),
        "major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "coverage_version": coverage_module.__version__,
    }
    attestation = repo / "docs/evidence/coverage-runtime-34354263174.json"
    attestation.write_text(
        json.dumps(
            {
                "version": 1,
                "run_id": 34354263174,
                "job_id": 102474833000,
                "head_sha": base,
                "python_version": platform.python_version(),
                "setup_python_action_sha": "a" * 40,
                "runtime": runtime,
                "artifacts": {
                    "backend": {
                        "id": 10109024797,
                        "name": "r17-backend-lcov",
                        "url": "https://example.test/backend",
                        "archive_sha256": "b" * 64,
                        "lcov_sha256": hashlib.sha256(backend_lcov.read_bytes()).hexdigest(),
                    },
                    "frontend": {
                        "id": 10105098738,
                        "name": "r17-frontend-lcov",
                        "url": "https://example.test/frontend",
                        "archive_sha256": "c" * 64,
                        "lcov_sha256": hashlib.sha256(frontend_lcov.read_bytes()).hexdigest(),
                    },
                },
            }
        )
        + "\n"
    )
    provenance = repo / "coverage/backend-provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "version": 1,
                "candidate_sha": base,
                "lcov_sha256": hashlib.sha256(backend_lcov.read_bytes()).hexdigest(),
                "runtime": runtime,
            }
        )
        + "\n"
    )
    return attestation, provenance


def _runtime_reconcile(
    repo: Path,
    base: str,
    baseline: Path,
    backend_lcov: Path,
    frontend_lcov: Path,
    attestation: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-S",
            str(CHECKER),
            "--repo-root",
            str(repo),
            "--base",
            base,
            "--backend-lcov",
            str(backend_lcov),
            "--frontend-lcov",
            str(frontend_lcov),
            "--baseline",
            str(baseline),
            "--verify-baseline-provenance",
            "--reconcile-unprovenanced-runtime",
            "Reviewed one-time runtime reconciliation",
            "--legacy-runtime-attestation",
            str(attestation),
        ],
        text=True,
        capture_output=True,
    )


def test_one_time_runtime_reconciliation_replaces_only_unprovenanced_ratios(
    tmp_path: Path,
) -> None:
    repo, base, baseline, reports, _ = _refresh_repository(tmp_path)
    reports(uncovered=True)
    backend_lcov = repo / "coverage/backend.lcov"
    frontend_lcov = repo / "coverage/frontend.lcov"
    attestation, provenance = _runtime_reconciliation_evidence(
        repo, base, backend_lcov, frontend_lcov
    )

    result = _runtime_reconcile(repo, base, baseline, backend_lcov, frontend_lcov, attestation)

    assert result.returncode == 0, result.stderr
    receipt = json.loads(baseline.read_text())
    assert receipt["version"] == 3
    assert receipt["backend_runtime"]["major_minor"] == (
        f"{sys.version_info.major}.{sys.version_info.minor}"
    )
    assert receipt["refresh"]["kind"] == "runtime_reconciliation"
    assert (
        receipt["refresh"]["legacy_attestation_sha256"]
        == hashlib.sha256(attestation.read_bytes()).hexdigest()
    )

    _run(["git", "add", "."], repo)
    _run(["git", "commit", "--quiet", "-m", "runtime receipt"], repo)
    trusted = _run(["git", "rev-parse", "HEAD"], repo).strip()
    current_provenance = json.loads(provenance.read_text())
    current_provenance["candidate_sha"] = trusted
    provenance.write_text(json.dumps(current_provenance) + "\n")
    verify = subprocess.run(
        [
            sys.executable,
            "-S",
            str(CHECKER),
            "--repo-root",
            str(repo),
            "--base",
            trusted,
            "--backend-lcov",
            str(backend_lcov),
            "--frontend-lcov",
            str(frontend_lcov),
            "--baseline",
            str(baseline),
            "--verify-baseline-provenance",
            "--backend-provenance",
            str(provenance),
        ],
        text=True,
        capture_output=True,
    )
    assert verify.returncode == 0, verify.stderr
    missing_provenance = subprocess.run(verify.args[:-2], text=True, capture_output=True)
    assert missing_provenance.returncode == 1
    assert "requires backend producer provenance" in missing_provenance.stderr

    mismatched = json.loads(provenance.read_text())
    mismatched["runtime"]["major_minor"] = "0.0"
    provenance.write_text(json.dumps(mismatched) + "\n")
    mismatched_provenance = subprocess.run(verify.args, text=True, capture_output=True)
    assert mismatched_provenance.returncode == 1
    assert "differs from checker runtime" in mismatched_provenance.stderr


def test_runtime_reconciliation_rejects_tampered_evidence_and_reuse(tmp_path: Path) -> None:
    repo, base, baseline, reports, _ = _refresh_repository(tmp_path)
    reports()
    backend_lcov = repo / "coverage/backend.lcov"
    frontend_lcov = repo / "coverage/frontend.lcov"
    attestation, provenance = _runtime_reconciliation_evidence(
        repo, base, backend_lcov, frontend_lcov
    )
    evidence = json.loads(attestation.read_text())
    evidence["artifacts"]["backend"]["lcov_sha256"] = "0" * 64
    attestation.write_text(json.dumps(evidence) + "\n")

    rejected = _runtime_reconcile(repo, base, baseline, backend_lcov, frontend_lcov, attestation)
    assert rejected.returncode == 1
    assert "attestation" in rejected.stderr

    attestation, _ = _runtime_reconciliation_evidence(repo, base, backend_lcov, frontend_lcov)
    assert (
        _runtime_reconcile(
            repo, base, baseline, backend_lcov, frontend_lcov, attestation
        ).returncode
        == 0
    )
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "--quiet", "-m", "runtime receipt"], repo)
    trusted = _run(["git", "rev-parse", "HEAD"], repo).strip()
    reused = _runtime_reconcile(repo, trusted, baseline, backend_lcov, frontend_lcov, attestation)
    assert reused.returncode == 1
    assert "one-time" in reused.stderr
    # Ordinary admission cannot use a legacy origin to reopen reconciliation
    # after the event base has adopted v3, either.
    candidate = json.loads(baseline.read_text())
    candidate["refresh"]["reason"] = "Attempt to reuse legacy origin"
    baseline.write_text(json.dumps(candidate))
    producer = json.loads(provenance.read_text())
    producer["candidate_sha"] = trusted
    provenance.write_text(json.dumps(producer))
    command = reused.args[:reused.args.index("--reconcile-unprovenanced-runtime")]
    rejected = subprocess.run(command + ["--backend-provenance", str(provenance)],
                              text=True, capture_output=True)
    assert rejected.returncode == 1
    assert "cannot bypass a version 3 event base" in rejected.stderr


def test_policy_only_refresh_preserves_adopted_floors_and_rejects_regression(tmp_path):
    repo, base, baseline, reports, _ = _refresh_repository(tmp_path)
    reports(uncovered=True)
    backend = repo / "coverage/backend.lcov"
    frontend = repo / "coverage/frontend.lcov"
    attestation, provenance = _runtime_reconciliation_evidence(repo, base, backend, frontend)
    result = _runtime_reconcile(repo, base, baseline, backend, frontend, attestation)
    assert result.returncode == 0, result.stderr
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "--quiet", "-m", "trusted runtime floors"], repo)
    base = _run(["git", "rev-parse", "HEAD"], repo).strip()
    trusted = json.loads(baseline.read_text())
    lock = repo / "frontend/package-lock.json"
    value = json.loads(lock.read_text())
    value["packages"]["node_modules/vitest"]["version"] = "1.1.0"
    lock.write_text(json.dumps(value))

    def check(refresh=False):
        producer = json.loads(provenance.read_text())
        producer["candidate_sha"] = base
        producer["lcov_sha256"] = hashlib.sha256(backend.read_bytes()).hexdigest()
        provenance.write_text(json.dumps(producer))
        command = [
            sys.executable,
            "-S",
            str(CHECKER),
            "--repo-root",
            str(repo),
            "--base",
            base,
            "--backend-lcov",
            str(backend),
            "--frontend-lcov",
            str(frontend),
            "--baseline",
            str(baseline),
            "--verify-baseline-provenance",
            "--backend-provenance",
            str(provenance),
        ]
        if refresh:
            command += ["--refresh-baseline", "Reviewed provisioning-only correction"]
        return subprocess.run(command, capture_output=True, text=True)

    reports()
    refreshed = check(refresh=True)
    assert refreshed.returncode == 0, refreshed.stderr
    receipt = json.loads(baseline.read_text())
    assert receipt["global"] == trusted["global"]
    assert receipt["critical"] == trusted["critical"]
    assert receipt["policy_sha256"] != trusted["policy_sha256"]
    reports(uncovered=True)
    exact = check()
    assert exact.returncode == 0, exact.stderr
    backend.write_text(backend.read_text().replace("DA:1,1", "DA:1,0"))
    below = check()
    assert below.returncode == 1
    assert "regressed" in below.stderr
    reports()
    altered = json.loads(baseline.read_text())
    altered["global"]["line_covered"] += 1
    baseline.write_text(json.dumps(altered))
    assert check().returncode == 1
    baseline.write_text(json.dumps(receipt))
    (repo / "app/sample.py").write_text("def value(flag):\n    return 2\n")
    changed_source = check(refresh=True)
    assert changed_source.returncode == 0, changed_source.stderr
    assert json.loads(baseline.read_text())["global"]["line_percent"] == 100


def test_v3_refresh_verifies_adopted_ratios_instead_of_repeating_hit_counts(tmp_path):
    repo, base, baseline, reports, _ = _refresh_repository(tmp_path)
    reports(uncovered=True)
    backend, frontend = repo / "coverage/backend.lcov", repo / "coverage/frontend.lcov"
    attestation, provenance = _runtime_reconciliation_evidence(repo, base, backend, frontend)
    assert _runtime_reconcile(repo, base, baseline, backend, frontend, attestation).returncode == 0
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "--quiet", "-m", "trusted floors"], repo)
    base = _run(["git", "rev-parse", "HEAD"], repo).strip()
    (repo / "app/sample.py").write_text("def value(flag):\n    return 2\n")

    def check(refresh=False):
        producer = json.loads(provenance.read_text())
        producer.update(
            candidate_sha=base, lcov_sha256=hashlib.sha256(backend.read_bytes()).hexdigest()
        )
        provenance.write_text(json.dumps(producer))
        command = [
            sys.executable,
            str(CHECKER),
            "--repo-root",
            str(repo),
            "--base",
            base,
            "--backend-lcov",
            str(backend),
            "--frontend-lcov",
            str(frontend),
            "--baseline",
            str(baseline),
            "--backend-provenance",
            str(provenance),
            "--verify-baseline-provenance",
        ]
        if refresh:
            command += ["--refresh-baseline", "Reviewed source correction"]
        return subprocess.run(command, text=True, capture_output=True)

    _write_lcov(
        backend,
        {
            str(repo / "app/sample.py"): ({1: 1, 2: 1}, {}),
            str(repo / "app/removed.py"): ({1: 1, 2: 0}, {}),
        },
    )
    refreshed = check(True)
    assert refreshed.returncode == 0, refreshed.stderr
    adopted = json.loads(baseline.read_text())
    assert adopted["global"]["line_covered"] == 4
    assert check().returncode == 0
    reports()
    improved = check()
    assert improved.returncode == 0, improved.stderr
    reports(uncovered=True)
    assert check().returncode == 1  # meets trusted floor, but not newly adopted floor
    reports()
    mutations = [
        ("global", "line_covered", 2),
        ("global", "line_percent", 79),
        ("global", "line_total", 6),
        ("global", "branch_covered", True),
        ("global", "unknown", 1),
        ("critical", "backend", {}),
        (None, "source_sha256", "0" * 64),
        (None, "policy_sha256", "0" * 64),
        (None, "source_parent_sha", "0" * 40),
        (None, "backend_runtime", {}),
        (None, "eligible_inventory_sha256", "0" * 64),
        (None, "unknown", 1),
    ]
    for section, key, value in mutations:
        changed = json.loads(json.dumps(adopted))
        (changed if section is None else changed[section])[key] = value
        baseline.write_text(json.dumps(changed))
        assert check().returncode == 1, (section, key)
    baseline.write_text(json.dumps(adopted))


@pytest.mark.parametrize(
    ("money_hits", "privacy_hits", "failure"),
    [
        (85, 85, None),
        (100, 84, "sensitive.privacy"),
        (84, 100, "sensitive.money"),
    ],
)
def test_sensitive_branch_floors_are_separate_and_exact(
    tmp_path, monkeypatch, money_hits, privacy_hits, failure
):
    spec = importlib.util.spec_from_file_location("sensitive_policy", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    paths = ["app/money/rules.py", "app/money/__init__.py", "app/privacy.py"]
    for name in paths:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('"""Package."""' if "__init__" in name else "value = 1\n")
    monkeypatch.setattr(module, "_run_git", lambda *args: "\0".join(paths))
    monkeypatch.setattr(
        module,
        "SENSITIVE_SCOPES",
        {
            "money": ("app/money/",),
            "privacy": ("app/privacy.py",),
        },
    )

    def record(hits):
        return module.CoverageRecord(
            lines={1: 1}, branches={(1, 0, str(i)): int(i < hits) for i in range(100)}
        )

    records = {paths[0]: record(money_hits), paths[2]: record(privacy_hits)}
    if failure:
        with pytest.raises(module.PolicyError, match=failure):
            module._sensitive_coverage(tmp_path, records)
    else:
        result = module._sensitive_coverage(tmp_path, records)
        assert result["money"]["branch_percent"] == 85
        assert result["privacy"]["branch_percent"] == 85
        assert result["money"]["paths"] == sorted(paths[:2])
        with pytest.raises(module.PolicyError, match="absent from LCOV"):
            module._sensitive_coverage(tmp_path, {paths[0]: record(100)})
        monkeypatch.setattr(module, "SENSITIVE_SCOPES", {"money": ("app/missing.py",)})
        with pytest.raises(module.PolicyError, match="required source is missing"):
            module._sensitive_coverage(tmp_path, records)

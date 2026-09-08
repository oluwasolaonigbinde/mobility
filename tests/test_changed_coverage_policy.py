"""Regression tests for the fail-closed changed-code coverage policy."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

CHECKER = Path(__file__).parents[1] / "scripts" / "check_changed_coverage.py"


def test_ci_routes_baseline_changes_through_the_reviewable_provenance_gate():
    workflow = (CHECKER.parents[1] / ".github/workflows/ci.yml").read_text()
    coverage_job = workflow.split("\n  coverage:\n", 1)[1].split("\n  e2e:\n", 1)[0]
    assert "--verify-baseline-provenance" in coverage_job
    assert "baseline is immutable after its one bootstrap commit" not in coverage_job
    assert "--refresh-baseline" not in coverage_job


def test_exact_critical_paths_support_next_dynamic_segments() -> None:
    spec = importlib.util.spec_from_file_location("coverage_policy", CHECKER)
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
        f"SF:{backend}\nDA:1,1\nDA:2,1\nDA:3,1\nDA:4,1\n"
        "BRDA:2,0,jump to line 3,1\nend_of_record\n"
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
    baseline = coverage / "baseline.json"
    (repo / "scripts").mkdir()
    (repo / "scripts" / CHECKER.name).write_bytes(CHECKER.read_bytes())
    for name in (
        "pyproject.toml",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/vitest.config.ts",
    ):
        (repo / name).write_text("{}\n")
    (repo / "pyproject.toml").write_text('[tool.coverage.run]\nbranch = true\nsource = ["app"]\n')
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
        (repo / "frontend" / "package-lock.json").write_text('{"lockfileVersion": 3}\n')
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


@pytest.mark.parametrize("tamper", ["floor", "policy", "inventory", "base", "source"])
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

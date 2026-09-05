"""Regression tests for the fail-closed changed-code coverage policy."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CHECKER = Path(__file__).parents[1] / "scripts" / "check_changed_coverage.py"


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

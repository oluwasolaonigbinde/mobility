#!/usr/bin/env python3
"""Fail-closed changed-code coverage policy checker."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

LINE_FLOOR = 90.0
BRANCH_FLOOR = 80.0
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
HUNK = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class PolicyError(ValueError):
    """A coverage input cannot support a trustworthy policy decision."""


@dataclass
class CoverageRecord:
    lines: dict[int, int] = field(default_factory=dict)
    branches: dict[tuple[int, int, int], int | None] = field(default_factory=dict)
    declared_line_total: int | None = None
    declared_line_covered: int | None = None
    declared_branch_total: int | None = None
    declared_branch_covered: int | None = None


@dataclass(frozen=True)
class Change:
    path: str
    status: str


def _run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args], text=True, capture_output=True, check=False
    )
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "unknown git failure"
        raise PolicyError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def _validate_base(repo_root: Path, base: str) -> None:
    if not FULL_SHA.fullmatch(base):
        raise PolicyError("--base must be an explicit 40-character lowercase commit SHA")
    _run_git(repo_root, "cat-file", "-e", f"{base}^{{commit}}")
    _run_git(repo_root, "merge-base", "--is-ancestor", base, "HEAD")


def _relative_source(source: str, source_root: Path, repo_root: Path) -> str:
    candidate = Path(source)
    if not candidate.is_absolute():
        candidate = source_root / candidate
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise PolicyError(f"LCOV source is not a current regular file: {source}")
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError as error:
        raise PolicyError(f"LCOV source escapes repository: {source}") from error


def _parse_summary(line: str, prefix: str) -> int | None:
    if not line.startswith(prefix):
        return None
    value = line.removeprefix(prefix)
    if not value.isdecimal():
        raise PolicyError(f"malformed LCOV summary {line!r}")
    return int(value)


def _parse_lcov(path: Path, source_root: Path, repo_root: Path) -> dict[str, CoverageRecord]:
    if not path.is_file():
        raise PolicyError(f"missing coverage report: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise PolicyError(f"LCOV report is not UTF-8: {path}") from error

    reports: dict[str, CoverageRecord] = {}
    source: str | None = None
    record: CoverageRecord | None = None
    ended = True
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("TN:"):
            continue
        if line.startswith("SF:"):
            if source is not None:
                raise PolicyError(f"LCOV record missing end_of_record before {line!r}")
            source = _relative_source(line.removeprefix("SF:"), source_root, repo_root)
            if source in reports:
                raise PolicyError(f"conflicting duplicate LCOV source: {source}")
            record = CoverageRecord()
            ended = False
            continue
        if line == "end_of_record":
            if source is None or record is None:
                raise PolicyError("LCOV end_of_record has no source")
            _validate_record(source, record)
            reports[source] = record
            source = None
            record = None
            ended = True
            continue
        if source is None or record is None:
            raise PolicyError(f"LCOV data is outside a source record: {line!r}")
        _parse_record_line(record, line)

    if not ended or source is not None:
        raise PolicyError("LCOV record is missing end_of_record")
    if not reports:
        raise PolicyError(f"LCOV report contains no source records: {path}")
    return reports


def _parse_record_line(record: CoverageRecord, line: str) -> None:
    if line.startswith("DA:"):
        try:
            number, hits, *_ = line.removeprefix("DA:").split(",")
            number_int, hits_int = int(number), int(hits)
        except ValueError as error:
            raise PolicyError(f"malformed LCOV line coverage: {line!r}") from error
        if number_int <= 0 or hits_int < 0 or number_int in record.lines:
            raise PolicyError(f"conflicting LCOV line coverage: {line!r}")
        record.lines[number_int] = hits_int
        return
    if line.startswith("BRDA:"):
        try:
            number, block, branch, taken = line.removeprefix("BRDA:").split(",")
            key = (int(number), int(block), int(branch))
            value = None if taken == "-" else int(taken)
        except ValueError as error:
            raise PolicyError(f"malformed LCOV branch coverage: {line!r}") from error
        invalid_key = key[0] <= 0 or key[1] < 0 or key[2] < 0
        if invalid_key or (value is not None and value < 0) or key in record.branches:
            raise PolicyError(f"conflicting LCOV branch coverage: {line!r}")
        record.branches[key] = value
        return
    for prefix, attribute in (
        ("LF:", "declared_line_total"),
        ("LH:", "declared_line_covered"),
        ("BRF:", "declared_branch_total"),
        ("BRH:", "declared_branch_covered"),
    ):
        parsed = _parse_summary(line, prefix)
        if parsed is not None:
            if getattr(record, attribute) is not None:
                raise PolicyError(f"conflicting LCOV summary: {line!r}")
            setattr(record, attribute, parsed)
            return
    if line.startswith(("FN:", "FNDA:", "FNF:", "FNH:")):
        return
    raise PolicyError(f"unsupported LCOV record line: {line!r}")


def _validate_record(source: str, record: CoverageRecord) -> None:
    actual_line_total = len(record.lines)
    actual_line_covered = sum(hits > 0 for hits in record.lines.values())
    actual_branch_total = len(record.branches)
    actual_branch_covered = sum(hits is not None and hits > 0 for hits in record.branches.values())
    for attribute, actual in (
        ("declared_line_total", actual_line_total),
        ("declared_line_covered", actual_line_covered),
        ("declared_branch_total", actual_branch_total),
        ("declared_branch_covered", actual_branch_covered),
    ):
        declared = getattr(record, attribute)
        if declared is not None and declared != actual:
            raise PolicyError(f"conflicting LCOV summary for {source}: {attribute}")


def _eligible(path: str) -> bool:
    if path.startswith("app/") and path.endswith(".py"):
        pass
    elif path.startswith("frontend/src/") and path.endswith((".ts", ".tsx")):
        pass
    else:
        return False
    parts = path.split("/")
    return not (
        any(
            part
            in {
                "test",
                "tests",
                "fixture",
                "fixtures",
                "migration",
                "migrations",
                "build",
                "dist",
                "vendor",
                "node_modules",
                ".next",
                "generated",
            }
            for part in parts
        )
        or path.endswith((".d.ts", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    )


def _changes(repo_root: Path, base: str) -> list[Change]:
    raw = _run_git(repo_root, "diff", "--name-status", "-z", "-M", base)
    fields = raw.split("\0")
    changes: list[Change] = []
    index = 0
    while index < len(fields) - 1:
        status = fields[index]
        index += 1
        if not status:
            continue
        if status.startswith(("R", "C")):
            if index + 1 >= len(fields):
                raise PolicyError("malformed git rename/copy status")
            _old_path, new_path = fields[index], fields[index + 1]
            index += 2
            changes.append(Change(new_path, "renamed" if status.startswith("R") else "copied"))
        else:
            if index >= len(fields):
                raise PolicyError("malformed git status")
            path = fields[index]
            index += 1
            status_name = {
                "A": "added",
                "M": "modified",
                "D": "deleted",
                "T": "type_changed",
            }.get(status[:1])
            if status_name is None:
                raise PolicyError(f"unsupported git change status: {status}")
            changes.append(Change(path, status_name))
    changed_paths = {change.path for change in changes}
    untracked = _run_git(repo_root, "ls-files", "--others", "--exclude-standard", "-z")
    for path in untracked.split("\0"):
        if path and path not in changed_paths and _eligible(path):
            changes.append(Change(path, "untracked"))
    return changes


def _changed_lines(repo_root: Path, base: str, path: str) -> set[int]:
    diff = _run_git(repo_root, "diff", "--no-ext-diff", "--unified=0", base, "--", path)
    lines: set[int] = set()
    for line in diff.splitlines():
        match = HUNK.match(line)
        if match is None:
            continue
        first, count = int(match.group(1)), int(match.group(2) or "1")
        lines.update(range(first, first + count))
    return lines


def _percent(covered: int, total: int) -> float:
    return 100.0 if total == 0 else round(covered * 100 / total, 4)


def _metrics(records: Iterable[CoverageRecord]) -> dict[str, float | int]:
    line_total = line_covered = branch_total = branch_covered = 0
    for record in records:
        line_total += len(record.lines)
        line_covered += sum(hits > 0 for hits in record.lines.values())
        branch_total += len(record.branches)
        branch_covered += sum(hits is not None and hits > 0 for hits in record.branches.values())
    return {
        "line_covered": line_covered,
        "line_total": line_total,
        "line_percent": _percent(line_covered, line_total),
        "branch_covered": branch_covered,
        "branch_total": branch_total,
        "branch_percent": _percent(branch_covered, branch_total),
    }


def _load_baseline(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise PolicyError(f"missing baseline: {path}")
    try:
        baseline = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PolicyError(f"malformed baseline: {path}") from error
    if not isinstance(baseline, dict) or baseline.get("version") != 1:
        raise PolicyError("baseline must be a version 1 object")
    has_sections = isinstance(baseline.get("global"), dict) and isinstance(
        baseline.get("critical"), dict
    )
    if not has_sections:
        raise PolicyError("baseline must contain global and critical objects")
    return baseline


def _required_percentages(scope: object, label: str) -> tuple[float, float]:
    if not isinstance(scope, dict):
        raise PolicyError(f"baseline {label} must be an object")
    values: list[float] = []
    for key in ("line_percent", "branch_percent"):
        value = scope.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
            raise PolicyError(f"baseline {label}.{key} must be a percentage")
        values.append(float(value))
    return values[0], values[1]


def _assert_not_regressed(label: str, actual: dict[str, float | int], expected: object) -> None:
    expected_line, expected_branch = _required_percentages(expected, label)
    if actual["line_percent"] < expected_line or actual["branch_percent"] < expected_branch:
        raise PolicyError(
            f"{label} coverage regressed: line {actual['line_percent']}% < {expected_line}% "
            f"or branch {actual['branch_percent']}% < {expected_branch}%"
        )


def _matches(path: str, patterns: object, label: str) -> bool:
    valid_patterns = (
        isinstance(patterns, list)
        and bool(patterns)
        and all(isinstance(pattern, str) for pattern in patterns)
    )
    if not valid_patterns:
        raise PolicyError(f"baseline {label}.paths must be a non-empty string list")
    candidates = set(patterns)
    pending = list(candidates)
    while pending:
        candidate = pending.pop()
        if "**/" not in candidate:
            continue
        zero_directory = candidate.replace("**/", "", 1)
        if zero_directory not in candidates:
            candidates.add(zero_directory)
            pending.append(zero_directory)
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in candidates)


def _evaluate(args: argparse.Namespace) -> dict[str, object]:
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / ".git").exists():
        raise PolicyError(f"repository root is not a git checkout: {repo_root}")
    _validate_base(repo_root, args.base)
    backend = _parse_lcov(Path(args.backend_lcov), repo_root, repo_root)
    frontend = _parse_lcov(Path(args.frontend_lcov), repo_root / "frontend", repo_root)
    overlap = set(backend).intersection(frontend)
    if overlap:
        raise PolicyError(f"conflicting backend/frontend LCOV source: {sorted(overlap)[0]}")
    records = backend | frontend
    baseline = _load_baseline(Path(args.baseline))

    changes = _changes(repo_root, args.base)
    changed_records: list[CoverageRecord] = []
    added: list[str] = []
    modified: list[str] = []
    untracked: list[str] = []
    renamed: list[str] = []
    deleted: list[str] = []
    copied: list[str] = []
    type_changed: list[str] = []
    for change in changes:
        if not _eligible(change.path):
            continue
        if change.status == "deleted":
            deleted.append(change.path)
            continue
        record = records.get(change.path)
        if record is None:
            raise PolicyError(f"eligible changed source is absent from LCOV: {change.path}")
        lines = _changed_lines(repo_root, args.base, change.path)
        if change.status in {"renamed", "untracked"} and not lines:
            lines = set(record.lines)
        if change.status == "renamed":
            renamed.append(change.path)
        elif change.status == "added":
            added.append(change.path)
        elif change.status == "modified":
            modified.append(change.path)
        elif change.status == "untracked":
            untracked.append(change.path)
        elif change.status == "copied":
            copied.append(change.path)
        elif change.status == "type_changed":
            type_changed.append(change.path)
        else:
            raise PolicyError(f"unsupported eligible change status: {change.status}")
        changed_records.append(
            CoverageRecord(
                lines={line: hits for line, hits in record.lines.items() if line in lines},
                branches={key: hits for key, hits in record.branches.items() if key[0] in lines},
            )
        )

    changed_metrics = _metrics(changed_records)
    if changed_metrics["line_percent"] < LINE_FLOOR:
        raise PolicyError(
            f"changed line coverage {changed_metrics['line_percent']}% is below {LINE_FLOOR}%"
        )
    if changed_metrics["branch_percent"] < BRANCH_FLOOR:
        raise PolicyError(
            f"changed branch coverage {changed_metrics['branch_percent']}% is below {BRANCH_FLOOR}%"
        )

    global_metrics = _metrics(records.values())
    _assert_not_regressed("global", global_metrics, baseline["global"])
    critical_results: dict[str, dict[str, float | int]] = {}
    critical = baseline["critical"]
    assert isinstance(critical, dict)
    if not critical:
        raise PolicyError("baseline critical groups must not be empty")
    for name, definition in critical.items():
        if not isinstance(name, str) or not isinstance(definition, dict):
            raise PolicyError("baseline critical groups must be named objects")
        selected = [
            record
            for path, record in records.items()
            if _matches(path, definition.get("paths"), f"critical.{name}")
        ]
        if not selected:
            raise PolicyError(f"critical coverage group has no LCOV sources: {name}")
        metrics = _metrics(selected)
        _assert_not_regressed(f"critical.{name}", metrics, definition)
        critical_results[name] = metrics

    return {
        "base": args.base,
        "changed": {
            **changed_metrics,
            "added": sorted(added),
            "modified": sorted(modified),
            "untracked": sorted(untracked),
            "renamed": sorted(renamed),
            "deleted": sorted(deleted),
            "copied": sorted(copied),
            "type_changed": sorted(type_changed),
            "no_eligible_changes": not any(
                (added, modified, untracked, renamed, deleted, copied, type_changed)
            ),
        },
        "global": global_metrics,
        "critical": critical_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=Path(__file__).parents[1])
    parser.add_argument("--base", required=True, help="explicit full ancestor commit SHA")
    parser.add_argument("--backend-lcov", required=True)
    parser.add_argument("--frontend-lcov", required=True)
    parser.add_argument("--baseline", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(_evaluate(args), indent=2, sort_keys=True))
    except PolicyError as error:
        print(f"coverage policy failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

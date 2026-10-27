#!/usr/bin/env python3
"""Fail-closed changed-code coverage policy checker."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

LINE_FLOOR = 90.0
BRANCH_FLOOR = 80.0
# D41: a run's global/critical ratios may sit this many percentage points below
# the adopted floor, absorbing run-to-run noise from concurrency tests. Adopted
# floors are never lowered, refreshes stay exact, and D32 floors are unaffected.
# 0.3: four runs of identical code spread 0.20 points on critical backend branches.
RATCHET_TOLERANCE_POINTS = Fraction(3, 10)
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
HUNK = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
LEGACY_RUNTIME_ATTESTATION = "docs/evidence/coverage-runtime-34354263174.json"
POLICY_FILES = (
    LEGACY_RUNTIME_ATTESTATION,
    "scripts/check_changed_coverage.py",
    "scripts/pytest_shard.py",
    "scripts/install_ci_dependencies.py",
    "scripts/ci_load_minio_images.sh",
    ".github/actions/verify-candidate-sha/action.yml",
    "requirements-production.txt",
    "frontend/.nvmrc",
    "frontend/vitest.config.ts",
)
FRONTEND_MEASUREMENT_TOOLS = ("vitest", "@vitest/coverage-v8", "@vitejs/plugin-react", "jsdom")
# Reviewed coverage.py/pytest dependency closure (including conditional Python
# and platform dependencies). Explicit overrides of these affect the runner.
PYTHON_MEASUREMENT_TOOLS = {
    "coverage", "pytest", "greenlet", "pluggy", "packaging", "iniconfig", "pygments",
    "colorama", "exceptiongroup", "tomli", "typing-extensions",
}


# Separately aggregated absolute branch floors; D32/D36 ratchets still apply.
SENSITIVE_BRANCH_FLOOR = 85
SENSITIVE_SCOPES = {
    "money": (
        "app/services/payouts/",
        "app/services/billing/",
        "app/services/payout_corrections.py",
        "app/services/payout_adjustments.py",
        "app/services/payout_balances.py",
        "app/services/payout_eligibility.py",
        "app/services/payout_operations.py",
        "app/services/payout_rule_serialization.py",
        "app/services/automatic_payouts.py",
        "app/services/disbursements.py",
        "app/services/paystack_disbursements.py",
        "app/services/earnings_release.py",
        "app/services/payees.py",
        "app/services/campaign_cancellations.py",
        "app/adapters/payments/",
        "app/adapters/disbursement/",
    ),
    "privacy": (
        "app/services/disclosure.py",
        "app/services/data_lifecycle.py",
        "app/services/file_kyc_lifecycle.py",
        "app/services/stored_files.py",
        "app/services/stored_object_deletions.py",
        "app/services/kyc.py",
        "app/core/observability.py",
        "app/adapters/crypto/",
    ),
}


class PolicyError(ValueError):
    """A coverage input cannot support a trustworthy policy decision."""


@dataclass
class CoverageRecord:
    lines: dict[int, int] = field(default_factory=dict)
    branches: dict[tuple[int, int, str], int | None] = field(default_factory=dict)
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
            number, block, branch_id, taken = line.removeprefix("BRDA:").split(",")
            if not branch_id.strip():
                raise ValueError("empty branch identifier")
            key = (int(number), int(block), branch_id)
            value = None if taken == "-" else int(taken)
        except ValueError as error:
            raise PolicyError(f"malformed LCOV branch coverage: {line!r}") from error
        invalid_key = key[0] <= 0 or key[1] < 0
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
    if not isinstance(baseline, dict) or baseline.get("version") not in (1, 2, 3):
        raise PolicyError("baseline must be a version 1, 2 or 3 object")
    has_sections = isinstance(baseline.get("global"), dict) and isinstance(
        baseline.get("critical"), dict
    )
    if not has_sections:
        raise PolicyError("baseline must contain global and critical objects")
    return baseline


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise PolicyError(f"missing provenance source: {path}") from error


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PolicyError(f"invalid {label}: {path}") from error
    if not isinstance(value, dict):
        raise PolicyError(f"invalid {label}: expected an object")
    return value


def _runtime(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {
        "implementation",
        "major_minor",
        "coverage_version",
    }:
        raise PolicyError(f"invalid {label} runtime")
    runtime = {key: value[key] for key in value}
    if not all(isinstance(item, str) and item.strip() for item in runtime.values()):
        raise PolicyError(f"invalid {label} runtime")
    if not re.fullmatch(r"\d+\.\d+", runtime["major_minor"]):
        raise PolicyError(f"invalid {label} Python major/minor")
    return runtime


def _current_runtime() -> dict[str, str]:
    return {
        "implementation": platform.python_implementation(),
        "major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
    }


def _backend_producer(path: Path, backend_lcov: Path, repo_root: Path) -> dict[str, str]:
    value = _load_json_object(path, "backend coverage provenance")
    if value.get("version") != 1:
        raise PolicyError("invalid backend coverage provenance version")
    if value.get("candidate_sha") != _run_git(repo_root, "rev-parse", "HEAD").strip():
        raise PolicyError("backend coverage provenance is for a different candidate SHA")
    if value.get("lcov_sha256") != _sha256(backend_lcov):
        raise PolicyError("backend coverage provenance LCOV hash mismatch")
    runtime = _runtime(value.get("runtime"), "backend coverage provenance")
    current = _current_runtime()
    for key in ("implementation", "major_minor"):
        if runtime[key] != current[key]:
            raise PolicyError(f"backend coverage producer {key} differs from checker runtime")
    return runtime


def _legacy_attestation(
    path: Path, backend_lcov: Path, frontend_lcov: Path, *, verify_reports: bool
) -> dict[str, object]:
    value = _load_json_object(path, "legacy runtime attestation")
    if value.get("version") != 1:
        raise PolicyError("invalid legacy runtime attestation version")
    if not isinstance(value.get("run_id"), int) or not isinstance(value.get("job_id"), int):
        raise PolicyError("invalid legacy runtime attestation run identity")
    head_sha = value.get("head_sha")
    if not isinstance(head_sha, str) or not FULL_SHA.fullmatch(head_sha):
        raise PolicyError("invalid legacy runtime attestation head SHA")
    action_sha = value.get("setup_python_action_sha")
    if not isinstance(action_sha, str) or not FULL_SHA.fullmatch(action_sha):
        raise PolicyError("invalid legacy runtime attestation action SHA")
    runtime = _runtime(value.get("runtime"), "legacy runtime attestation")
    python_version = value.get("python_version")
    if not isinstance(python_version, str) or not python_version.startswith(
        f"{runtime['major_minor']}."
    ):
        raise PolicyError("invalid legacy runtime attestation Python version")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"backend", "frontend"}:
        raise PolicyError("invalid legacy runtime attestation artifacts")
    for name, report in (("backend", backend_lcov), ("frontend", frontend_lcov)):
        artifact = artifacts.get(name)
        required = {"id", "name", "url", "archive_sha256", "lcov_sha256"}
        if not isinstance(artifact, dict) or set(artifact) != required:
            raise PolicyError(f"invalid legacy runtime attestation {name} artifact")
        if not isinstance(artifact["id"], int) or artifact["id"] <= 0:
            raise PolicyError(f"invalid legacy runtime attestation {name} artifact id")
        if not isinstance(artifact["name"], str) or not artifact["name"]:
            raise PolicyError(f"invalid legacy runtime attestation {name} artifact name")
        if not isinstance(artifact["url"], str) or not artifact["url"].startswith("https://"):
            raise PolicyError(f"invalid legacy runtime attestation {name} artifact URL")
        for key in ("archive_sha256", "lcov_sha256"):
            if not isinstance(artifact[key], str) or not re.fullmatch(
                r"[0-9a-f]{64}", artifact[key]
            ):
                raise PolicyError(f"invalid legacy runtime attestation {name} {key}")
        if verify_reports and artifact["lcov_sha256"] != _sha256(report):
            raise PolicyError(f"legacy runtime attestation {name} LCOV hash mismatch")
    return {**value, "runtime": runtime}


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


def _assert_not_regressed(
    label: str,
    actual: dict[str, float | int],
    expected: object,
    *,
    tolerance: Fraction = Fraction(0),
) -> None:
    """Refuse a ratio below the floor; ``tolerance`` is in percentage points."""
    expected_line, expected_branch = _required_percentages(expected, label)
    assert isinstance(expected, dict)
    for metric in ("line", "branch"):
        covered, total = expected.get(f"{metric}_covered"), expected.get(f"{metric}_total")
        if covered is None and total is None:
            continue
        if type(covered) is not int or type(total) is not int or not 0 <= covered <= total:
            raise PolicyError(f"baseline {label}.{metric} counts are invalid")
        floor = Fraction(covered, total) if total else Fraction(1)
        actual_total = actual[f"{metric}_total"]
        actual_covered = actual[f"{metric}_covered"]
        assert isinstance(actual_total, int) and isinstance(actual_covered, int)
        measured = (
            Fraction(actual_covered, actual_total) if actual_total else Fraction(1)
        )
        if measured < floor - tolerance / 100:
            raise PolicyError(f"{label} {metric} coverage regressed from exact baseline ratio")
    slack = float(tolerance)
    if (
        actual["line_percent"] < expected_line - slack
        or actual["branch_percent"] < expected_branch - slack
    ):
        raise PolicyError(
            f"{label} coverage regressed: line {actual['line_percent']}% < {expected_line}% "
            f"or branch {actual['branch_percent']}% < {expected_branch}%"
        )


def _matches(path: str, patterns: object, label: str) -> bool:
    if (
        not isinstance(patterns, list)
        or not patterns
        or not all(isinstance(pattern, str) for pattern in patterns)
    ):
        raise PolicyError(f"baseline {label}.paths must be a non-empty string list")
    if path in patterns:
        return True
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


def _hash_files(repo_root: Path, paths: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.encode())
        digest.update(b"\0")
        try:
            digest.update((repo_root / path).read_bytes())
        except OSError as error:
            raise PolicyError(f"missing provenance source: {path}") from error
    return digest.hexdigest()


def _hash_git_files(repo_root: Path, revision: str, paths: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{revision}:{path}"],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise PolicyError(f"legacy attestation source is missing at {revision}: {path}")
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(result.stdout)
    return digest.hexdigest()


def _workflow_fields(block: str, indent: int) -> dict[str, str]:
    """Read the workflow's block-mapping subset, never interpret executable YAML.

    Scalar bodies (notably shell scripts) stay opaque. Relevant mappings are
    inspected separately; flow mappings, aliases and merges cannot replace them.
    """
    lines = [line.rstrip() for line in block.splitlines()]
    fields: dict[str, str] = {}
    key = None
    for line in lines:
        depth = len(line) - len(line.lstrip(" "))
        if not line:
            if key is not None:
                fields[key] += "\n"
            continue
        if line.lstrip().startswith("#") and depth <= indent:
            continue
        if "\t" in line[:depth + 1] or depth < indent:
            raise PolicyError("unsupported measurement workflow indentation")
        if depth == indent:
            match = re.fullmatch(r" *([A-Za-z_][\w-]*):(?: (.*))?", line)
            if match is None or match[1] in fields:
                raise PolicyError("invalid or duplicate measurement workflow field")
            key = match[1]
            fields[key] = line[indent:] + "\n"
        elif key is None:
            raise PolicyError("unsupported measurement workflow mapping")
        else:
            fields[key] += line[indent:] + "\n"
    return fields


def _workflow_mapping(field: str, *, recursive: bool = True) -> dict[str, str]:
    head, _, body = field.partition("\n")
    if not head.endswith(":"):
        raise PolicyError("measurement workflow requires a static block mapping")
    fields = _workflow_fields(body, 2)
    for value in fields.values():
        scalar = value.split("\n", 1)[0].split(":", 1)[1].strip()
        if scalar.startswith(("&", "*", "!", "{")):
            raise PolicyError("unsupported measurement workflow alias or flow mapping")
        if scalar.startswith("[") and not re.fullmatch(
            r"\[\s*(?:[\w-]+|\"[^\"\\]*\"|'[^'\\]*')"
            r"(?:\s*,\s*(?:[\w-]+|\"[^\"\\]*\"|'[^'\\]*'))*\s*\]", scalar
        ):
            raise PolicyError("measurement workflow requires static scalar sequences")
        if not scalar and recursive:
            _workflow_mapping(value)
    return fields


def _measurement_workflow(repo_root: Path) -> dict[str, object]:
    """Explicit measurement inputs; upload metadata and scheduling are not policy.

    Keep every producer/preparation step, including unknown new commands, so an
    earlier GITHUB_ENV/file mutation cannot evade the binding. Lint/typecheck
    step context remains bound even though their known package script bodies
    are exempt. Steps after the frontend report upload are outside measurement.
    """
    try:
        root = _workflow_fields(
            (repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8"), 0
        )
    except (OSError, UnicodeDecodeError) as error:
        raise PolicyError("missing or invalid measurement workflow") from error
    jobs = _workflow_mapping(root.get("jobs", ""), recursive=False)
    policy: dict[str, object] = {}
    for key in ("env", "defaults"):
        if key in root:
            policy[key] = _workflow_mapping(root[key])
    required = {
        "backend_tests": ("pytest_shard.py plan", "coverage run", "-m pytest"),
        "backend": ("pytest_shard.py verify", "coverage combine", "coverage lcov",
                    'Path("coverage/backend-provenance.json")'),
        "quality": ("npm ci", "npm run test", "--coverage"),
        "coverage": ("check_changed_coverage.py", "--verify-baseline-provenance"),
    }
    for name, commands in required.items():
        if name not in jobs:
            raise PolicyError(f"missing measurement workflow job: {name}")
        job = _workflow_mapping(jobs[name], recursive=False)
        allowed_job = {
            "name", "runs-on", "container", "if", "continue-on-error", "needs", "outputs",
            "timeout-minutes", "concurrency", "permissions", "env", "defaults", "services",
            "strategy", "steps",
        }
        if set(job) - allowed_job:
            raise PolicyError(f"unsupported measurement workflow job fields: {name}")
        definition: dict[str, object] = {}
        for key in ("env", "defaults", "services", "strategy", "outputs"):
            if key in job:
                mapping = _workflow_mapping(job[key])
                if key == "strategy":
                    # fail-fast only schedules failures; matrix defines producer membership.
                    mapping = {"matrix": mapping.get("matrix", "")}
                definition[key] = mapping
        for key in ("runs-on", "container", "if", "continue-on-error", "needs"):
            if key in job:
                definition[key] = job[key]
        steps = job.get("steps", "")
        if not steps.startswith("steps:\n"):
            raise PolicyError(f"missing static measurement workflow steps: {name}")
        bodies = re.split(r"(?m)^  - ", steps.removeprefix("steps:\n"))
        prelude = [line for line in bodies[0].splitlines()
                   if line.strip() and not line.lstrip().startswith("#")]
        if prelude or len(bodies) == 1:
            raise PolicyError(f"unsupported measurement workflow steps: {name}")
        selected = []
        for body in bodies[1:]:
            step = _workflow_fields("    " + body, 4)
            allowed = {
                "name", "id", "uses", "with", "run", "env", "if", "shell",
                "working-directory", "continue-on-error", "timeout-minutes",
            }
            if set(step) - allowed or ("uses" in step) == ("run" in step):
                raise PolicyError(f"unsupported measurement workflow step: {name}")
            for value in step.values():
                scalar = value.split("\n", 1)[0].split(":", 1)[1].strip()
                if scalar.startswith(("&", "*", "!", "{")):
                    raise PolicyError("unsupported measurement workflow step alias/flow mapping")
            uses = step.get("uses", "").removeprefix("uses: ").strip()
            if uses.startswith("./") and uses != "./.github/actions/verify-candidate-sha":
                raise PolicyError("unreviewed local measurement workflow action")
            if uses.startswith("actions/upload-artifact@"):
                if name == "quality":
                    break  # The frontend report has now been produced and uploaded.
                continue
            for helper in re.findall(r"\bscripts/[\w./${}-]+", step.get("run", "")):
                if helper not in (*POLICY_FILES, "scripts/pytest_shard_durations.json"):
                    raise PolicyError(f"unreviewed measurement workflow helper: {helper}")
            for key in ("with", "env"):
                if key in step:
                    _workflow_mapping(step[key])
            if uses.startswith("actions/setup-") and "with" in step:
                inputs = _workflow_mapping(step["with"])
                step["with"] = "with:\n" + "".join(
                    "  " + value.replace("\n", "\n  ").rstrip() + "\n"
                    for key, value in inputs.items()
                    if key not in {"cache", "cache-dependency-path"}
                )
            selected.append({key: value for key, value in step.items()
                             if key not in {"name", "timeout-minutes"}})
        serialized = "\n".join(value for step in selected for value in step.values())
        if not all(command in serialized for command in commands):
            raise PolicyError(f"missing required measurement workflow command: {name}")
        setup = "actions/setup-node@" if name == "quality" else "actions/setup-python@"
        if setup not in serialized or "verify-candidate-sha" not in serialized:
            raise PolicyError(f"missing measurement runtime/candidate verification: {name}")
        definition["steps"] = selected
        policy[name] = definition
    return policy


def _policy_hash(repo_root: Path) -> str:
    representation = {
        "files_sha256": _hash_files(repo_root, POLICY_FILES),
        "measurement_workflow": _measurement_workflow(repo_root),
        "measurement_configuration": _measurement_configuration(repo_root),
    }
    return hashlib.sha256(json.dumps(representation, sort_keys=True).encode()).hexdigest()


def _measurement_configuration(repo_root: Path) -> dict[str, object]:
    try:
        project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PolicyError("invalid measurement pyproject.toml") from error
    project_metadata = project.get("project", {})
    tool = project.get("tool", {})
    if not isinstance(project_metadata, dict) or not isinstance(tool, dict):
        raise PolicyError("measurement pyproject requires project/tool tables")
    dependencies = project_metadata.get("dependencies", [])
    optional_groups = project_metadata.get("optional-dependencies", {})
    if not isinstance(dependencies, list) or not isinstance(optional_groups, dict):
        raise PolicyError("invalid measurement Python dependencies")
    dependencies = list(dependencies)
    # The measurement jobs invoke install_ci_dependencies without --static;
    # its hashed implementation installs the dev group, not static tooling.
    development = optional_groups.get("dev", [])
    if not isinstance(development, list):
        raise PolicyError("invalid measurement Python dependency group")
    dependencies.extend(development)
    if not all(isinstance(requirement, str) for requirement in dependencies):
        raise PolicyError("measurement Python requirements must be strings")
    python_tools = []
    for requirement in dependencies:
        match = re.match(r"[A-Za-z0-9_.-]+", requirement)
        name = re.sub(r"[-_.]+", "-", match[0]).lower() if match else ""
        if name in PYTHON_MEASUREMENT_TOOLS or name.startswith("pytest-"):
            python_tools.append(requirement)
    package = _load_json_object(repo_root / "frontend/package.json", "measurement package")
    lock = _load_json_object(repo_root / "frontend/package-lock.json", "measurement lock")
    packages = lock.get("packages")
    if lock.get("lockfileVersion") != 3 or not isinstance(packages, dict):
        raise PolicyError("measurement lock requires npm lockfile version 3 packages")
    declarations = {}
    for name in FRONTEND_MEASUREMENT_TOOLS:
        matches = []
        for section in ("dependencies", "devDependencies", "optionalDependencies"):
            definition = package.get(section, {})
            if not isinstance(definition, dict):
                raise PolicyError(f"invalid measurement package dependencies: {section}")
            if name in definition:
                matches.append((section, definition[name]))
        if len(matches) != 1 or not isinstance(matches[0][1], str):
            raise PolicyError(f"measurement package requires one tool declaration: {name}")
        declarations[name] = matches[0]

    # Follow npm's nearest-node_modules resolution, including optional/peer
    # tooling dependencies. Unrelated lint/build packages and lock metadata
    # cannot invalidate coverage; a transitive V8/Vite instrumenter change can.
    def resolve(location: str, name: str, *, optional: bool = False) -> str | None:
        while True:
            path = f"{location}/node_modules/{name}" if location else f"node_modules/{name}"
            if path in packages:
                return path
            if not location:
                break
            location = (
                location.rsplit("/node_modules/", 1)[0] if "/node_modules/" in location else ""
            )
        if not optional:
            raise PolicyError(f"measurement lock is missing dependency: {name}")
        return None

    pending = [resolve("", name) for name in FRONTEND_MEASUREMENT_TOOLS]
    selected = {}
    while pending:
        path = pending.pop()
        if path is None or path in selected:
            continue
        entry = packages[path]
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("version"), str)
            or entry.get("link")
        ):
            raise PolicyError(f"invalid measurement lock package: {path}")
        selected[path] = {
            key: entry[key] for key in (
                "version", "resolved", "integrity", "dependencies", "optionalDependencies",
                "peerDependencies", "peerDependenciesMeta", "engines", "os", "cpu", "bin",
                "hasInstallScript", "inBundle",
            ) if key in entry
        }
        for section in ("dependencies", "optionalDependencies", "peerDependencies"):
            requirements = entry.get(section, {})
            if not isinstance(requirements, dict):
                raise PolicyError(f"invalid measurement lock dependencies: {path}")
            peer_metadata = entry.get("peerDependenciesMeta", {})
            if not isinstance(peer_metadata, dict):
                raise PolicyError(f"invalid measurement lock peer metadata: {path}")
            for name in requirements:
                metadata = peer_metadata.get(name, {})
                if not isinstance(metadata, dict):
                    raise PolicyError(f"invalid measurement lock peer metadata: {path}")
                optional = section == "optionalDependencies" or (
                    section == "peerDependencies"
                    and metadata.get("optional") is True
                )
                pending.append(resolve(path, name, optional=optional))
    scripts = package.get("scripts", {})
    if not isinstance(scripts, dict) or not isinstance(scripts.get("test"), str):
        raise PolicyError("measurement package requires a test command")
    return {
        "python": {
            "requires-python": project_metadata.get("requires-python"),
            "coverage": tool.get("coverage", {}),
            "pytest": tool.get("pytest", {}),
            "dependencies": sorted(python_tools),
        },
        "frontend": {
            "tools": declarations,
            "scripts": {key: scripts[key] for key in (
                "preinstall", "install", "postinstall", "prepublish", "preprepare", "prepare",
                "postprepare", "pretest", "test", "posttest",
                "prelint", "lint", "postlint", "pretypecheck", "typecheck", "posttypecheck",
            ) if key in scripts and (key, scripts[key]) not in (
                ("lint", "eslint ."), ("typecheck", "tsc --noEmit"),
            )},
            "lock_packages": selected,
        },
    }


def _assert_attested_source_identity(repo_root: Path, revision: str, inventory: list[str]) -> None:
    previous = sorted(
        path
        for path in _run_git(repo_root, "ls-tree", "-r", "--name-only", revision).splitlines()
        if _eligible(path)
    )
    if previous != inventory:
        raise PolicyError(
            "legacy runtime attestation eligible inventory differs from current source"
        )
    if _hash_git_files(repo_root, revision, inventory) != _hash_files(repo_root, inventory):
        raise PolicyError("legacy runtime attestation eligible source differs from current source")


def _complete_inventory(repo_root: Path, records: dict[str, CoverageRecord]) -> list[str]:
    paths = _run_git(repo_root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    inventory = sorted(
        {
            path
            for path in paths.split("\0")
            if path and _eligible(path) and (repo_root / path).is_file()
        }
    )
    for path in inventory:
        if not (repo_root / path).resolve().is_relative_to(repo_root):
            raise PolicyError(f"eligible source escapes repository: {path}")
        if path in records:
            continue
        # coverage.py omits modules containing only a docstring or comments.
        if path.endswith(".py"):
            try:
                body = ast.parse((repo_root / path).read_text(encoding="utf-8")).body
            except (SyntaxError, UnicodeDecodeError) as error:
                raise PolicyError(f"cannot classify uncovered source: {path}") from error
            if not body or (
                len(body) == 1
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                records[path] = CoverageRecord()
                continue
        raise PolicyError(f"eligible source is absent from LCOV: {path}")
    if set(records) != set(inventory):
        raise PolicyError("LCOV inventory contains sources outside the eligible git inventory")
    return inventory


def _coverage_block(source: str) -> list[str]:
    tokens = re.findall(
        r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|//[^\n]*|/\*[\s\S]*?\*/|\w+|[^\s]""", source
    )
    tokens = [token for token in tokens if not token.startswith(("//", "/*"))]
    starts = [
        index
        for index in range(len(tokens) - 2)
        if tokens[index : index + 3] == ["coverage", ":", "{"]
    ]
    if len(starts) != 1:
        raise PolicyError("coverage instrumentation requires one static Vitest coverage block")
    depth = 0
    for end in range(starts[0] + 2, len(tokens)):
        depth += (tokens[end] == "{") - (tokens[end] == "}")
        if depth == 0:
            return tokens[starts[0] : end + 1]
    raise PolicyError("unterminated Vitest coverage instrumentation block")


def _validate_instrumentation(repo_root: Path, base: str) -> None:
    old_pyproject = _run_git(repo_root, "show", f"{base}:pyproject.toml")
    try:
        old = tomllib.loads(old_pyproject).get("tool", {}).get("coverage", {})
        new = (
            tomllib.loads((repo_root / "pyproject.toml").read_text())
            .get("tool", {})
            .get("coverage", {})
        )
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise PolicyError("coverage configuration must be valid TOML") from error
    for section, keys in {
        "run": ("branch", "source", "source_pkgs", "include", "omit", "plugins"),
        "report": (
            "exclude_lines",
            "exclude_also",
            "partial_branches",
            "partial_also",
            "include",
            "omit",
        ),
    }.items():
        for key in keys:
            if old.get(section, {}).get(key) != new.get(section, {}).get(key):
                raise PolicyError(
                    f"coverage instrumentation drift requires D32 authority: {section}.{key}"
                )
    previous = _run_git(repo_root, "show", f"{base}:frontend/vitest.config.ts")
    current = (repo_root / "frontend/vitest.config.ts").read_text()
    if _coverage_block(previous) != _coverage_block(current):
        raise PolicyError("coverage instrumentation drift requires D32 authority: vitest.coverage")


def _trusted_baseline(
    args: argparse.Namespace,
    repo_root: Path,
    records: dict[str, CoverageRecord],
    producer_runtime: dict[str, str] | None,
) -> tuple[dict[str, object], dict[str, object]]:
    try:
        relative = Path(args.baseline).resolve().relative_to(repo_root).as_posix()
    except ValueError as error:
        raise PolicyError("verified baseline must be inside the repository") from error
    raw = _run_git(repo_root, "show", f"{args.base}:{relative}")
    try:
        trusted = json.loads(raw)
    except json.JSONDecodeError as error:
        raise PolicyError("trusted ancestor baseline is malformed") from error
    if not isinstance(trusted, dict) or trusted.get("version") not in (1, 2, 3):
        raise PolicyError("trusted ancestor baseline has an unsupported version")
    if not isinstance(trusted.get("critical"), dict) or set(trusted["critical"]) != {
        "backend",
        "frontend",
    }:
        raise PolicyError("trusted named critical groups must remain backend and frontend")
    inventory = _complete_inventory(repo_root, records)
    candidate = _load_baseline(Path(args.baseline))
    candidate_global, candidate_critical = candidate["global"], candidate["critical"]
    assert isinstance(candidate_global, dict) and isinstance(candidate_critical, dict)
    event_trusted = trusted
    origin = args.base
    # JSON types are part of the receipt schema (False is not an integer zero).
    changed_receipt = json.dumps(candidate, sort_keys=True) != json.dumps(
        event_trusted, sort_keys=True
    )
    admitting = changed_receipt and not (
        args.refresh_baseline or getattr(args, "reconcile_unprovenanced_runtime", None)
    )
    if admitting:
        origin = candidate.get("source_parent_sha")
        if not isinstance(origin, str) or not FULL_SHA.fullmatch(origin):
            raise PolicyError("baseline refresh origin must be a full ancestor SHA")
        try:
            _validate_base(repo_root, origin)
            raw = _run_git(repo_root, "show", f"{origin}:{relative}")
            trusted = json.loads(raw)
        except (PolicyError, json.JSONDecodeError) as error:
            raise PolicyError("baseline refresh origin/previous baseline is invalid") from error
        if (
            not isinstance(trusted, dict)
            or trusted.get("version") not in (1, 2, 3)
            or not isinstance(trusted.get("critical"), dict)
            or set(trusted["critical"]) != {"backend", "frontend"}
        ):
            raise PolicyError("baseline refresh origin has an invalid previous baseline")
    candidate_refresh = candidate.get("refresh")
    migration_admission = (
        trusted.get("version") in (1, 2)
        and candidate.get("version") == 3
        and isinstance(candidate_refresh, dict)
        and candidate_refresh.get("kind") == "runtime_reconciliation"
    )
    migration_write = bool(getattr(args, "reconcile_unprovenanced_runtime", None))
    runtime_migration = migration_write or migration_admission
    if runtime_migration and event_trusted.get("version") == 3:
        raise PolicyError("one-time runtime reconciliation cannot bypass a version 3 event base")
    if migration_write and trusted.get("version") == 3:
        raise PolicyError("one-time runtime reconciliation cannot be reused")
    if runtime_migration and trusted.get("version") not in (1, 2):
        raise PolicyError("one-time runtime reconciliation requires an unprovenanced baseline")
    for authority in (event_trusted, trusted):
        if authority.get("version") == 3:
            if producer_runtime is None:
                raise PolicyError("version 3 baseline requires backend producer provenance")
            trusted_runtime = _runtime(authority.get("backend_runtime"), "trusted baseline")
            for key in ("implementation", "major_minor", "coverage_version"):
                if trusted_runtime[key] != producer_runtime[key]:
                    raise PolicyError(f"backend coverage runtime mismatch: {key}")
    groups = {
        "backend": sorted(path for path in inventory if path.startswith("app/")),
        "frontend": sorted(path for path in inventory if path.startswith("frontend/")),
    }
    # Eligibility itself is D32 authority, not a configurable coverage exclusion.
    old_source = _run_git(repo_root, "show", f"{origin}:scripts/check_changed_coverage.py")
    old_tree = ast.parse(old_source)
    old_eligible = next(
        (
            node
            for node in old_tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_eligible"
        ),
        None,
    )
    if old_eligible is None:
        raise PolicyError("trusted source eligibility policy is missing")
    namespace: dict[str, object] = {}
    exec(
        compile(ast.Module(body=[old_eligible], type_ignores=[]), "trusted eligibility", "exec"),
        namespace,
    )
    previous_eligible = namespace["_eligible"]
    assert callable(previous_eligible)
    previous_paths = _run_git(repo_root, "ls-tree", "-r", "--name-only", origin).splitlines()
    current_paths = _run_git(
        repo_root, "ls-files", "--cached", "--others", "--exclude-standard", "-z"
    ).split("\0")
    for path in set(previous_paths + current_paths) - {""}:
        if previous_eligible(path) != _eligible(path):
            raise PolicyError(f"source eligibility drift requires separate D32 authority: {path}")
    if LINE_FLOOR < 90 or BRANCH_FLOOR < 80:
        raise PolicyError("D32 changed-code floors cannot be lowered by baseline refresh")
    _validate_instrumentation(repo_root, origin)
    if origin != args.base:
        _validate_instrumentation(repo_root, args.base)
        # Event authority still guards eligibility; the receipt origin cannot
        # hide an intervening change to the eligible-source definition.
        event_source = _run_git(
            repo_root, "show", f"{args.base}:scripts/check_changed_coverage.py"
        )
        event_tree = ast.parse(event_source)
        event_eligible = next(
            (node for node in event_tree.body
             if isinstance(node, ast.FunctionDef) and node.name == "_eligible"), None
        )
        if event_eligible is None or ast.dump(event_eligible) != ast.dump(old_eligible):
            raise PolicyError("source eligibility drift requires separate D32 authority")
    actual = _metrics(records.values())
    tolerance = RATCHET_TOLERANCE_POINTS
    if not runtime_migration:
        _assert_not_regressed("global", actual, trusted.get("global"), tolerance=tolerance)
        _assert_not_regressed("event.global", actual, event_trusted.get("global"),
                              tolerance=tolerance)
    critical = {}
    for name, paths in groups.items():
        if not paths:
            raise PolicyError(f"critical coverage group has no eligible sources: {name}")
        metrics = _metrics(records[path] for path in paths)
        if not runtime_migration:
            _assert_not_regressed(
                f"critical.{name}", metrics, trusted["critical"][name], tolerance=tolerance
            )
            _assert_not_regressed(
                f"event.critical.{name}", metrics, event_trusted["critical"][name],
                tolerance=tolerance,
            )
        critical[name] = {**metrics, "paths": paths}
    inventory_hash = hashlib.sha256(
        ("\n".join(groups["backend"] + groups["frontend"]) + "\n").encode()
    ).hexdigest()
    trusted_inventory = {
        path
        for definition in trusted["critical"].values()
        if isinstance(definition, dict)
        for path in definition.get("paths", [])
        if isinstance(path, str)
    }
    policy_hash = _policy_hash(repo_root)
    snapshot: dict[str, object] = {
        "version": 3 if runtime_migration or trusted.get("version") == 3 else 2,
        "source_parent_sha": origin,
        "eligible_inventory_sha256": inventory_hash,
        "policy_sha256": policy_hash,
        "source_sha256": _hash_files(repo_root, inventory),
        "global": actual,
        "critical": critical,
        "refresh": {
            "previous_baseline_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "inventory_changes": {
                "added": sorted(set(inventory) - trusted_inventory),
                "removed": sorted(trusted_inventory - set(inventory)),
            },
        },
    }
    if snapshot["version"] == 3:
        if producer_runtime is None and not runtime_migration:
            raise PolicyError("runtime baseline requires backend producer provenance")
        if producer_runtime is not None:
            snapshot["backend_runtime"] = producer_runtime
    if (
        trusted.get("version") == 3
        and snapshot["source_sha256"] == trusted.get("source_sha256")
        and inventory_hash == trusted.get("eligible_inventory_sha256")
        and snapshot.get("backend_runtime") == trusted.get("backend_runtime")
        and all(groups[name] == trusted["critical"][name].get("paths") for name in groups)
    ):
        # Metadata-only refreshes retain adopted floors; actual evidence was checked above.
        snapshot["global"] = trusted["global"]
        snapshot["critical"] = trusted["critical"]
    elif args.refresh_baseline and not runtime_migration:
        # This refresh adopts the measured ratios, so they must meet the floors
        # exactly; the D41 tolerance never lowers an adopted floor.
        _assert_not_regressed("global", actual, trusted.get("global"))
        for name in groups:
            _assert_not_regressed(f"critical.{name}", critical[name], trusted["critical"][name])
    if runtime_migration:
        attestation_path = repo_root / LEGACY_RUNTIME_ATTESTATION
        attestation = _legacy_attestation(
            attestation_path,
            Path(args.backend_lcov),
            Path(args.frontend_lcov),
            verify_reports=migration_write,
        )
        attested_head = attestation["head_sha"]
        assert isinstance(attested_head, str)
        _assert_attested_source_identity(repo_root, attested_head, inventory)
        attested_runtime = attestation["runtime"]
        assert isinstance(attested_runtime, dict)
        if producer_runtime is None:
            producer_runtime = attested_runtime
            snapshot["backend_runtime"] = producer_runtime
        for key in ("implementation", "major_minor", "coverage_version"):
            if producer_runtime[key] != attested_runtime[key]:
                raise PolicyError(f"legacy runtime attestation producer mismatch: {key}")
        refresh = snapshot["refresh"]
        assert isinstance(refresh, dict)
        refresh.update(
            kind="runtime_reconciliation",
            legacy_attestation_sha256=_sha256(attestation_path),
            runtime_transition={"from": "unprovenanced", "to": producer_runtime},
        )
    if args.refresh_baseline:
        if not args.refresh_baseline.strip():
            raise PolicyError("baseline refresh requires a reviewable reason")
        refresh = snapshot["refresh"]
        assert isinstance(refresh, dict)
        refresh["reason"] = args.refresh_baseline.strip()
    elif migration_write:
        reason = getattr(args, "reconcile_unprovenanced_runtime", None)
        if not isinstance(reason, str) or not reason.strip():
            raise PolicyError("runtime reconciliation requires a reviewable reason")
        refresh = snapshot["refresh"]
        assert isinstance(refresh, dict)
        refresh["reason"] = reason.strip()
    elif admitting:
        refresh = candidate.get("refresh")
        reason = refresh.get("reason") if isinstance(refresh, dict) else None
        if not isinstance(reason, str) or not reason.strip():
            raise PolicyError("baseline refresh receipt requires a reviewable reason")
        snapshot_refresh = snapshot["refresh"]
        assert isinstance(snapshot_refresh, dict)
        snapshot_refresh["reason"] = reason
        if (
            trusted.get("version") == 3
            and not runtime_migration
            and snapshot["source_sha256"] != trusted.get("source_sha256")
        ):
            for label, measured, adopted, prior in (
                ("global", actual, candidate.get("global"), trusted["global"]),
                *(
                    (
                        f"critical.{name}",
                        critical[name],
                        candidate_critical.get(name),
                        trusted["critical"][name],
                    )
                    for name in groups
                ),
            ):
                if not isinstance(adopted, dict) or set(adopted) != set(measured):
                    raise PolicyError(f"invalid adopted coverage metrics: {label}")
                for metric in ("line", "branch"):
                    covered, total = adopted[f"{metric}_covered"], adopted[f"{metric}_total"]
                    if (
                        type(covered) is not int
                        or type(total) is not int
                        or not 0 <= covered <= total
                        or total != measured[f"{metric}_total"]
                        or type(adopted[f"{metric}_percent"]) not in (int, float)
                        or adopted[f"{metric}_percent"] != _percent(covered, total)
                    ):
                        raise PolicyError(f"invalid adopted coverage metrics: {label}.{metric}")
                _assert_not_regressed(label, adopted, prior)
                _assert_not_regressed(label, measured, adopted, tolerance=RATCHET_TOLERANCE_POINTS)
            snapshot["global"] = candidate["global"]
            snapshot["critical"] = {
                name: {**candidate_critical[name], "paths": groups[name]} for name in groups
            }
        # Origin/previous-baseline lineage is reconstructed at the recorded
        # ancestor, independently of the event-selected changed-code base.
        # Every field remains bound; in particular no parent field is ignored.
        if set(candidate) != set(snapshot):
            raise PolicyError("baseline refresh receipt has unexpected or missing fields")
        for key in snapshot:
            if json.dumps(candidate[key], sort_keys=True) != json.dumps(
                snapshot[key], sort_keys=True
            ):
                raise PolicyError(f"baseline refresh receipt differs from evidence: {key}")
        if not runtime_migration:
            _assert_not_regressed("adopted.global", candidate_global, event_trusted["global"])
            for name in groups:
                _assert_not_regressed(
                    f"adopted.critical.{name}", candidate_critical[name],
                    event_trusted["critical"][name],
                )
    else:
        if (
            candidate.get("eligible_inventory_sha256") != inventory_hash
            or candidate.get("policy_sha256") != policy_hash
        ):
            raise PolicyError("inventory or policy changed; controlled baseline refresh required")
    # Apply the trusted ratios to current group membership, including additions and renames.
    floors = {
        **(snapshot if runtime_migration else event_trusted),
        "critical": {
            name: {
                **(critical[name] if runtime_migration else event_trusted["critical"][name]),
                "paths": paths,
            }
            for name, paths in groups.items()
        },
    }
    return floors, snapshot


def _sensitive_coverage(repo_root: Path, records: dict[str, CoverageRecord]) -> dict:
    records = {path: record for path, record in records.items() if _eligible(path)}
    inventory = _complete_inventory(repo_root, records)
    results = {}
    for name, specifications in SENSITIVE_SCOPES.items():
        paths = set()
        for specification in specifications:
            selected = (
                {
                    path
                    for path in inventory
                    if path.startswith(specification) and path.endswith(".py")
                }
                if specification.endswith("/")
                else {specification} & set(inventory)
            )
            if not selected:
                raise PolicyError(f"sensitive.{name} required source is missing: {specification}")
            paths.update(selected)
        metrics = _metrics(records[path] for path in sorted(paths))
        total = metrics["branch_total"]
        covered = metrics["branch_covered"]
        assert isinstance(total, int) and isinstance(covered, int)
        if not total:
            raise PolicyError(f"sensitive.{name} has no executable branches")
        if Fraction(covered, total) < Fraction(SENSITIVE_BRANCH_FLOOR, 100):
            raise PolicyError(
                f"sensitive.{name} branch coverage {metrics['branch_percent']}% "
                f"is below {SENSITIVE_BRANCH_FLOOR}%"
            )
        results[name] = {**metrics, "paths": sorted(paths)}
    return results


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
    sensitive_metrics = (
        _sensitive_coverage(repo_root, records)
        if getattr(args, "sensitive_branches", False)
        else {}
    )
    baseline = _load_baseline(Path(args.baseline))
    snapshot = None
    reconcile_reason = getattr(args, "reconcile_unprovenanced_runtime", None)
    provenance_required = (
        args.verify_baseline_provenance or args.refresh_baseline or reconcile_reason
    )
    producer_runtime = None
    if provenance_required:
        if reconcile_reason:
            if not args.verify_baseline_provenance:
                raise PolicyError("runtime reconciliation requires provenance verification")
            supplied = Path(args.legacy_runtime_attestation).resolve()
            expected = (repo_root / LEGACY_RUNTIME_ATTESTATION).resolve()
            if supplied != expected:
                raise PolicyError("runtime reconciliation requires the fixed legacy attestation")
            attestation = _legacy_attestation(
                supplied,
                Path(args.backend_lcov),
                Path(args.frontend_lcov),
                verify_reports=True,
            )
            producer_runtime = attestation["runtime"]
            assert isinstance(producer_runtime, dict)
        elif baseline.get("version") == 3:
            if not args.backend_provenance:
                raise PolicyError("version 3 baseline requires backend producer provenance")
            producer_runtime = _backend_producer(
                Path(args.backend_provenance), Path(args.backend_lcov), repo_root
            )
        records = {path: record for path, record in records.items() if _eligible(path)}
        baseline, snapshot = _trusted_baseline(args, repo_root, records, producer_runtime)

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
    _assert_not_regressed(
        "global", global_metrics, baseline["global"], tolerance=RATCHET_TOLERANCE_POINTS
    )
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
        _assert_not_regressed(
            f"critical.{name}", metrics, definition, tolerance=RATCHET_TOLERANCE_POINTS
        )
        critical_results[name] = metrics

    result = {
        "base": args.base,
        "sensitive": sensitive_metrics,
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
    if args.refresh_baseline or reconcile_reason:
        result["refreshed_baseline"] = snapshot
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=Path(__file__).parents[1])
    parser.add_argument("--base", required=True, help="explicit full ancestor commit SHA")
    parser.add_argument("--backend-lcov", required=True)
    parser.add_argument("--frontend-lcov", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--verify-baseline-provenance", action="store_true")
    parser.add_argument(
        "--sensitive-branches",
        action="store_true",
        help="enforce separate 85% money/privacy branch floors over complete source inventory",
    )
    refresh = parser.add_mutually_exclusive_group()
    refresh.add_argument(
        "--refresh-baseline",
        metavar="REASON",
        help="write a reviewed refresh only after all trusted gates pass",
    )
    refresh.add_argument(
        "--reconcile-unprovenanced-runtime",
        metavar="REASON",
        help="one-time reviewed v1/v2 runtime reconciliation",
    )
    parser.add_argument("--backend-provenance")
    parser.add_argument("--legacy-runtime-attestation")
    args = parser.parse_args()
    try:
        report = _evaluate(args)
        if args.refresh_baseline or args.reconcile_unprovenanced_runtime:
            baseline = Path(args.baseline)
            content = json.dumps(report.pop("refreshed_baseline"), indent=2, sort_keys=True) + "\n"
            with tempfile.NamedTemporaryFile(mode="w", dir=baseline.parent, delete=False) as output:
                output.write(content)
                name = output.name
            try:
                os.replace(name, baseline)
            finally:
                Path(name).unlink(missing_ok=True)
            report["baseline_refreshed"] = True
        print(json.dumps(report, indent=2, sort_keys=True))
    except PolicyError as error:
        print(f"coverage policy failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Plan and verify deterministic whole-file pytest coverage shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import coverage

FULL_SHA = re.compile(r"[0-9a-f]{40}")
MANIFEST_VERSION = 1


class ShardError(RuntimeError):
    pass


def _digest_lines(values: list[str]) -> str:
    return hashlib.sha256(("\n".join(values) + "\n").encode()).hexdigest()


def parse_collected_nodeids(output: str) -> list[str]:
    nodeids = sorted(
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith("tests/") and "::" in line
    )
    if not nodeids:
        raise ShardError("pytest collection produced no test node IDs")
    if len(nodeids) != len(set(nodeids)):
        raise ShardError("pytest collection produced duplicate test node IDs")
    for nodeid in nodeids:
        test_file = nodeid.split("::", 1)[0]
        if not test_file.endswith(".py") or "\n" in test_file or "\r" in test_file:
            raise ShardError(f"invalid collected test file: {test_file!r}")
    return nodeids


def collect_nodeids(repo_root: Path) -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()
        raise ShardError(f"pytest collection failed ({result.returncode}): {detail}")
    return parse_collected_nodeids(result.stdout)


def assign_files(nodeids: list[str], shard_count: int) -> list[list[str]]:
    if shard_count <= 0:
        raise ShardError("shard count must be positive")
    counts = Counter(nodeid.split("::", 1)[0] for nodeid in nodeids)
    if shard_count > len(counts):
        raise ShardError("shard count exceeds collected test-file count")
    assignments: list[list[str]] = [[] for _ in range(shard_count)]
    weights = [0] * shard_count
    for test_file, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        shard_index = min(range(shard_count), key=lambda index: (weights[index], index))
        assignments[shard_index].append(test_file)
        weights[shard_index] += count
    return [sorted(files) for files in assignments]


def _runtime() -> dict[str, str]:
    return {
        "implementation": platform.python_implementation(),
        "major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "python_version": platform.python_version(),
        "coverage_version": coverage.__version__,
    }


def _validate_sha(value: str) -> str:
    if not FULL_SHA.fullmatch(value):
        raise ShardError("candidate SHA must be 40 lowercase hexadecimal characters")
    return value


def plan(args: argparse.Namespace) -> None:
    candidate_sha = _validate_sha(args.candidate_sha)
    if args.shard_count <= 0 or not 0 <= args.shard_index < args.shard_count:
        raise ShardError("shard index must be within the configured shard count")
    repo_root = Path(args.repo_root).resolve()
    nodeids = collect_nodeids(repo_root)
    assignments = assign_files(nodeids, args.shard_count)
    assigned_files = assignments[args.shard_index]
    if not assigned_files:
        raise ShardError(f"shard {args.shard_index} has no assigned test files")
    assigned_file_set = set(assigned_files)
    assigned_nodeids = [
        nodeid for nodeid in nodeids if nodeid.split("::", 1)[0] in assigned_file_set
    ]

    files_output = Path(args.files_output)
    manifest_output = Path(args.manifest_output)
    files_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    files_output.write_text("\n".join(assigned_files) + "\n")
    manifest = {
        "version": MANIFEST_VERSION,
        "candidate_sha": candidate_sha,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "runtime": _runtime(),
        "inventory_sha256": _digest_lines(nodeids),
        "inventory_nodeids": nodeids,
        "assigned_files": assigned_files,
        "assigned_nodeids": assigned_nodeids,
    }
    manifest_output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _load_manifest(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ShardError(f"invalid shard manifest {path}") from error
    if not isinstance(value, dict) or value.get("version") != MANIFEST_VERSION:
        raise ShardError(f"unsupported shard manifest {path}")
    return value


def finalize(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest).resolve()
    coverage_path = Path(args.coverage_file).resolve()
    manifest = _load_manifest(manifest_path)
    if not coverage_path.is_file() or coverage_path.stat().st_size == 0:
        raise ShardError("raw coverage file is missing or empty")
    if args.elapsed_seconds < 0:
        raise ShardError("elapsed seconds must be non-negative")
    manifest["coverage_file"] = coverage_path.name
    manifest["coverage_sha256"] = hashlib.sha256(coverage_path.read_bytes()).hexdigest()
    manifest["elapsed_seconds"] = args.elapsed_seconds
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ShardError(f"{label} must be a string list")
    return value


def verify(args: argparse.Namespace) -> None:
    candidate_sha = _validate_sha(args.candidate_sha)
    if args.shard_count <= 0:
        raise ShardError("shard count must be positive")
    artifacts_dir = Path(args.artifacts_dir).resolve()
    directories = sorted(
        path for path in artifacts_dir.glob("r17-backend-shard-*") if path.is_dir()
    )
    if len(directories) != args.shard_count:
        raise ShardError(
            f"expected {args.shard_count} shard artifact directories, found {len(directories)}"
        )

    manifests: dict[int, tuple[Path, dict[str, object]]] = {}
    for directory in directories:
        manifest_path = directory / "manifest.json"
        manifest = _load_manifest(manifest_path)
        index = manifest.get("shard_index")
        if type(index) is not int or index in manifests:
            raise ShardError("shard IDs must be unique integers")
        manifests[index] = (manifest_path, manifest)
    expected_ids = set(range(args.shard_count))
    if set(manifests) != expected_ids:
        raise ShardError(f"shard IDs differ from expected {sorted(expected_ids)}")

    first = manifests[0][1]
    inventory = _string_list(first.get("inventory_nodeids"), "inventory_nodeids")
    inventory_digest = first.get("inventory_sha256")
    if inventory != sorted(inventory) or len(inventory) != len(set(inventory)):
        raise ShardError("full test inventory must be sorted and unique")
    if inventory_digest != _digest_lines(inventory):
        raise ShardError("full test inventory digest differs")

    assigned_nodeids: set[str] = set()
    assigned_files: set[str] = set()
    receipt_shards: list[dict[str, object]] = []
    for index in range(args.shard_count):
        manifest_path, manifest = manifests[index]
        if manifest.get("candidate_sha") != candidate_sha:
            raise ShardError(f"shard {index} candidate SHA differs")
        if manifest.get("shard_count") != args.shard_count:
            raise ShardError(f"shard {index} count differs")
        if manifest.get("runtime") != first.get("runtime"):
            raise ShardError(f"shard {index} runtime differs")
        if manifest.get("inventory_sha256") != inventory_digest:
            raise ShardError(f"shard {index} inventory digest differs")
        if _string_list(manifest.get("inventory_nodeids"), "inventory_nodeids") != inventory:
            raise ShardError(f"shard {index} inventory differs")
        nodeids = _string_list(manifest.get("assigned_nodeids"), "assigned_nodeids")
        files = _string_list(manifest.get("assigned_files"), "assigned_files")
        if not nodeids or not files:
            raise ShardError(f"shard {index} assignment is empty")
        if nodeids != sorted(nodeids) or len(nodeids) != len(set(nodeids)):
            raise ShardError(f"shard {index} node IDs must be sorted and unique")
        if files != sorted(files) or len(files) != len(set(files)):
            raise ShardError(f"shard {index} files must be sorted and unique")
        if assigned_nodeids.intersection(nodeids) or assigned_files.intersection(files):
            raise ShardError(f"shard {index} overlaps an earlier assignment")
        if {nodeid.split("::", 1)[0] for nodeid in nodeids} != set(files):
            raise ShardError(f"shard {index} node IDs do not match its files")
        assigned_nodeids.update(nodeids)
        assigned_files.update(files)

        coverage_name = manifest.get("coverage_file")
        coverage_sha256 = manifest.get("coverage_sha256")
        elapsed_seconds = manifest.get("elapsed_seconds")
        if coverage_name != f".coverage.{index}":
            raise ShardError(f"shard {index} coverage filename is invalid")
        if type(elapsed_seconds) is not int or elapsed_seconds < 0:
            raise ShardError(f"shard {index} elapsed seconds are invalid")
        coverage_path = manifest_path.parent / coverage_name
        if not coverage_path.is_file():
            raise ShardError(f"shard {index} raw coverage file is missing")
        actual_hash = hashlib.sha256(coverage_path.read_bytes()).hexdigest()
        if coverage_sha256 != actual_hash:
            raise ShardError(f"shard {index} raw coverage hash differs")
        data = coverage.CoverageData(basename=str(coverage_path))
        try:
            data.read()
            if not data.measured_files() or not data.has_arcs():
                raise ShardError(f"shard {index} coverage is empty or lacks branch data")
        except coverage.exceptions.CoverageException as error:
            raise ShardError(f"shard {index} unreadable coverage data") from error
        receipt_shards.append(
            {
                "index": index,
                "assigned_file_count": len(files),
                "assigned_nodeid_count": len(nodeids),
                "coverage_file": coverage_path.relative_to(artifacts_dir).as_posix(),
                "coverage_sha256": actual_hash,
                "elapsed_seconds": elapsed_seconds,
                "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            }
        )

    if assigned_nodeids != set(inventory):
        raise ShardError("shard node-ID union is not the complete collected inventory")
    expected_files = {nodeid.split("::", 1)[0] for nodeid in inventory}
    if assigned_files != expected_files:
        raise ShardError("shard file union is not the complete collected inventory")

    receipt = {
        "version": 1,
        "candidate_sha": candidate_sha,
        "runtime": first.get("runtime"),
        "inventory_sha256": inventory_digest,
        "inventory_nodeid_count": len(inventory),
        "inventory_file_count": len(expected_files),
        "shards": receipt_shards,
    }
    receipt_output = Path(args.receipt_output)
    receipt_output.parent.mkdir(parents=True, exist_ok=True)
    receipt_output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    subparsers = result.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--repo-root", default=".")
    plan_parser.add_argument("--candidate-sha", required=True)
    plan_parser.add_argument("--shard-index", type=int, required=True)
    plan_parser.add_argument("--shard-count", type=int, required=True)
    plan_parser.add_argument("--files-output", required=True)
    plan_parser.add_argument("--manifest-output", required=True)
    plan_parser.set_defaults(handler=plan)

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--manifest", required=True)
    finalize_parser.add_argument("--coverage-file", required=True)
    finalize_parser.add_argument("--elapsed-seconds", type=int, required=True)
    finalize_parser.set_defaults(handler=finalize)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--candidate-sha", required=True)
    verify_parser.add_argument("--shard-count", type=int, required=True)
    verify_parser.add_argument("--artifacts-dir", required=True)
    verify_parser.add_argument("--receipt-output", required=True)
    verify_parser.set_defaults(handler=verify)
    return result


def main() -> int:
    try:
        args = parser().parse_args()
        args.handler(args)
    except ShardError as error:
        print(f"pytest shard error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

from scripts import pytest_shard

SHA = "a" * 40


def test_parse_collected_nodeids_ignores_summary_and_warning_output() -> None:
    output = """
tests/test_beta.py::test_two
warning: plugin emitted a message
tests/test_alpha.py::test_one[param]

2 tests collected in 0.10s
"""

    assert pytest_shard.parse_collected_nodeids(output) == [
        "tests/test_alpha.py::test_one[param]",
        "tests/test_beta.py::test_two",
    ]


@pytest.mark.parametrize(
    "output, message",
    [
        ("no tests collected", "no test node IDs"),
        ("tests/test_a.py::test_one\ntests/test_a.py::test_one\n", "duplicate"),
    ],
)
def test_parse_collected_nodeids_fails_closed(output: str, message: str) -> None:
    with pytest.raises(pytest_shard.ShardError, match=message):
        pytest_shard.parse_collected_nodeids(output)


def test_collect_nodeids_propagates_collection_failure(monkeypatch, tmp_path: Path) -> None:
    result = argparse.Namespace(returncode=3, stdout="", stderr="collection exploded")
    monkeypatch.setattr(pytest_shard.subprocess, "run", lambda *args, **kwargs: result)

    with pytest.raises(pytest_shard.ShardError, match="collection exploded"):
        pytest_shard.collect_nodeids(tmp_path)


def test_assign_files_is_deterministic_balanced_and_preserves_quoted_paths() -> None:
    nodeids = [
        "tests/test large.py::test_one",
        "tests/test large.py::test_two",
        "tests/test_small.py::test_one",
        "tests/test_other.py::test_one",
    ]

    first = pytest_shard.assign_files(nodeids, 2)
    second = pytest_shard.assign_files(list(reversed(nodeids)), 2)

    assert first == second
    assert sorted(path for shard in first for path in shard) == [
        "tests/test large.py",
        "tests/test_other.py",
        "tests/test_small.py",
    ]


@pytest.mark.parametrize("shard_count", [0, 3])
def test_assign_files_rejects_invalid_or_empty_shards(shard_count: int) -> None:
    with pytest.raises(pytest_shard.ShardError):
        pytest_shard.assign_files(["tests/test_one.py::test_one"], shard_count)


def test_plan_rejects_an_invalid_shard_index(tmp_path: Path) -> None:
    args = argparse.Namespace(
        candidate_sha=SHA,
        shard_count=2,
        shard_index=2,
        repo_root=str(tmp_path),
        files_output=str(tmp_path / "files.txt"),
        manifest_output=str(tmp_path / "manifest.json"),
    )

    with pytest.raises(pytest_shard.ShardError, match="shard index"):
        pytest_shard.plan(args)


def _write_shard(
    root: Path,
    *,
    index: int,
    inventory: list[str],
    assigned: list[str],
) -> Path:
    directory = root / f"r17-backend-shard-{index}"
    directory.mkdir(parents=True)
    coverage_path = directory / f".coverage.{index}"
    data = pytest_shard.coverage.CoverageData(basename=str(coverage_path))
    data.add_arcs({f"/repo/tests/test_{index}.py": {(1, 2), (2, -1)}})
    data.write()
    runtime = {
        "implementation": "CPython",
        "major_minor": "3.12",
        "python_version": "3.12.1",
        "coverage_version": "7.16.0",
    }
    manifest = {
        "version": 1,
        "candidate_sha": SHA,
        "shard_index": index,
        "shard_count": 2,
        "runtime": runtime,
        "inventory_nodeids": inventory,
        "inventory_sha256": pytest_shard._digest_lines(inventory),
        "assigned_files": sorted({nodeid.split("::", 1)[0] for nodeid in assigned}),
        "assigned_nodeids": assigned,
        "coverage_file": coverage_path.name,
        "coverage_sha256": hashlib.sha256(coverage_path.read_bytes()).hexdigest(),
        "elapsed_seconds": 10 + index,
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path


def test_verify_proves_exact_exhaustive_disjoint_shards(tmp_path: Path) -> None:
    inventory = ["tests/test_a.py::test_one", "tests/test_b.py::test_two"]
    _write_shard(tmp_path, index=0, inventory=inventory, assigned=inventory[:1])
    _write_shard(tmp_path, index=1, inventory=inventory, assigned=inventory[1:])
    receipt = tmp_path / "receipt.json"

    pytest_shard.verify(
        argparse.Namespace(
            candidate_sha=SHA,
            shard_count=2,
            artifacts_dir=str(tmp_path),
            receipt_output=str(receipt),
        )
    )

    value = json.loads(receipt.read_text())
    assert value["candidate_sha"] == SHA
    assert value["inventory_nodeid_count"] == 2
    assert [shard["index"] for shard in value["shards"]] == [0, 1]
    assert [shard["elapsed_seconds"] for shard in value["shards"]] == [10, 11]


def test_verify_rejects_overlap_and_raw_coverage_tampering(tmp_path: Path) -> None:
    inventory = ["tests/test_a.py::test_one", "tests/test_b.py::test_two"]
    _write_shard(tmp_path, index=0, inventory=inventory, assigned=inventory[:1])
    second = _write_shard(tmp_path, index=1, inventory=inventory, assigned=inventory[:1])
    args = argparse.Namespace(
        candidate_sha=SHA,
        shard_count=2,
        artifacts_dir=str(tmp_path),
        receipt_output=str(tmp_path / "receipt.json"),
    )

    with pytest.raises(pytest_shard.ShardError, match="overlaps"):
        pytest_shard.verify(args)

    manifest = json.loads(second.read_text())
    manifest["assigned_files"] = ["tests/test_b.py"]
    manifest["assigned_nodeids"] = inventory[1:]
    second.write_text(json.dumps(manifest))
    (second.parent / ".coverage.1").write_bytes(b"tampered")
    with pytest.raises(pytest_shard.ShardError, match="raw coverage hash differs"):
        pytest_shard.verify(args)


def test_verify_rejects_missing_shard(tmp_path: Path) -> None:
    inventory = ["tests/test_a.py::test_one"]
    _write_shard(tmp_path, index=0, inventory=inventory, assigned=inventory)

    with pytest.raises(pytest_shard.ShardError, match="expected 2"):
        pytest_shard.verify(
            argparse.Namespace(
                candidate_sha=SHA,
                shard_count=2,
                artifacts_dir=str(tmp_path),
                receipt_output=str(tmp_path / "receipt.json"),
            )
        )


def test_verify_rejects_correctly_hashed_malformed_coverage(tmp_path: Path) -> None:
    inventory = ["tests/test_a.py::test_one", "tests/test_b.py::test_two"]
    _write_shard(tmp_path, index=0, inventory=inventory, assigned=inventory[:1])
    second = _write_shard(tmp_path, index=1, inventory=inventory, assigned=inventory[1:])
    raw = second.parent / ".coverage.1"
    raw.write_bytes(b"not a coverage database")
    manifest = json.loads(second.read_text())
    manifest["coverage_sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
    second.write_text(json.dumps(manifest))

    with pytest.raises(pytest_shard.ShardError, match="unreadable coverage"):
        pytest_shard.verify(argparse.Namespace(
            candidate_sha=SHA, shard_count=2, artifacts_dir=str(tmp_path),
            receipt_output=str(tmp_path / "receipt.json"),
        ))

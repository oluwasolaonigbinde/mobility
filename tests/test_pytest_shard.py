from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
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
    execution = ET.Element("testsuites")
    suite = ET.SubElement(
        execution,
        "testsuite",
        name="pytest",
        tests=str(len(assigned)),
        failures="0",
        errors="0",
        skipped="0",
    )
    for nodeid in assigned:
        classname, name = pytest_shard._execution_identity(nodeid)
        ET.SubElement(suite, "testcase", classname=classname, name=name)
    report = directory / "execution.xml"
    ET.ElementTree(execution).write(report)
    manifest = {
        "execution_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
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


@pytest.mark.parametrize(
    "body",
    [
        "def test_one(): pass\ndef test_two(): pass",
        "def test_one(): pass\ndef test_two(): assert False",
        "import pytest\ndef test_one(): pass\n@pytest.mark.skip(reason='probe')\n"
        "def test_two(): pass",
        "import pytest\ndef test_one(): pass\n@pytest.mark.xfail(reason='probe')\n"
        "def test_two(): assert False",
        "import pytest\n@pytest.fixture\ndef broken(): raise RuntimeError('setup')\n"
        "def test_one(): pass\ndef test_two(broken): pass",
        "import pytest\n@pytest.fixture\ndef broken():\n yield\n raise RuntimeError('teardown')\n"
        "def test_one(): pass\ndef test_two(broken): pass",
    ],
)
def test_finalize_rejects_incomplete_or_unsuccessful_real_execution(tmp_path, body):
    suite = tmp_path / "tests"
    suite.mkdir()
    (suite / "test_probe.py").write_text(body)
    report = tmp_path / "execution.xml"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--junitxml",
            str(report),
            *(
                ["-k", "test_one"]
                if body.startswith("def test_one(): pass\ndef") and "assert False" not in body
                else []
            ),
            "tests",
        ],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "assigned_nodeids": [
                    "tests/test_probe.py::test_one",
                    "tests/test_probe.py::test_two",
                ],
            }
        )
    )
    raw = tmp_path / ".coverage.0"
    raw.write_bytes(b"coverage")
    with pytest.raises(pytest_shard.ShardError, match="execution"):
        pytest_shard.finalize(
            argparse.Namespace(
                manifest=str(manifest),
                coverage_file=str(raw),
                elapsed_seconds=1,
                execution_report=str(report),
            )
        )


def test_real_junit_preserves_class_and_parameter_identity(tmp_path):
    suite = tmp_path / "tests"
    suite.mkdir()
    (suite / "test_probe.py").write_text(
        "import pytest\ndef test_plain(): pass\nclass TestGroup:\n"
        " @pytest.mark.parametrize('value', [1], ids=['a.b::c[quoted]'])\n"
        " def test_parameter(self, value): assert value == 1\n"
    )
    report = tmp_path / "execution.xml"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--junitxml", str(report), "tests"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        pytest_shard.verify_execution(
            report,
            [
                "tests/test_probe.py::test_plain",
                "tests/test_probe.py::TestGroup::test_parameter[a.b::c[quoted]]",
            ],
        )
        == 2
    )


@pytest.mark.parametrize(
    "change", ["missing", "duplicate", "unexpected", "skipped", "error", "malformed"]
)
def test_aggregate_rejects_rehashed_invalid_execution(tmp_path, change):
    inventory = ["tests/test_a.py::test_one", "tests/test_b.py::test_two"]
    _write_shard(tmp_path, index=0, inventory=inventory, assigned=inventory[:1])
    manifest_path = _write_shard(tmp_path, index=1, inventory=inventory, assigned=inventory[1:])
    report = manifest_path.parent / "execution.xml"
    tree = ET.parse(report)
    suite = tree.getroot().find("testsuite")
    case = suite.find("testcase")
    if change == "missing":
        suite.remove(case)
        suite.set("tests", "0")
    elif change == "duplicate":
        suite.append(ET.fromstring(ET.tostring(case)))
        suite.set("tests", "2")
    elif change == "unexpected":
        case.set("name", "test_wrong")
    elif change in ("skipped", "error"):
        ET.SubElement(case, change)
    tree.write(report)
    if change == "malformed":
        report.write_text("broken XML")
    manifest = json.loads(manifest_path.read_text())
    manifest["execution_sha256"] = hashlib.sha256(report.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(pytest_shard.ShardError, match="execution"):
        pytest_shard.verify(
            argparse.Namespace(
                candidate_sha=SHA,
                shard_count=2,
                artifacts_dir=str(tmp_path),
                receipt_output=str(tmp_path / "receipt.json"),
            )
        )


def test_execution_rejects_real_collection_error(tmp_path):
    (tmp_path / "test_broken.py").write_text("raise RuntimeError('collection probe')")
    report = tmp_path / "execution.xml"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--junitxml", str(report)],
        cwd=tmp_path,
        capture_output=True,
    )
    assert result.returncode != 0
    with pytest.raises(pytest_shard.ShardError, match="execution"):
        pytest_shard.verify_execution(report, ["test_broken.py::test_one"])

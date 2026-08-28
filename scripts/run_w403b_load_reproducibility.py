#!/usr/bin/env python3
"""Run the bounded, provider-neutral W4-03B load and reproducibility check."""

from __future__ import annotations

import contextlib
import json
import math
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.measurement import calculate_measurement_result, canonical_sha256  # noqa: E402
from app.services.report_rendering import render_report_csv, render_report_pdf  # noqa: E402
from app.services.target_area_coverage import seal_synthetic_target_area_provenance  # noqa: E402

if __package__:
    from . import run_w403b_synthetic_journey as journey
else:
    import run_w403b_synthetic_journey as journey  # type: ignore[no-redef]


FIXTURE_PATH = ROOT / "tests/fixtures/measurement/w403b_load_reproducibility.json"
COVERAGE_FIXTURE_PATH = ROOT / "tests/fixtures/measurement/target_area_coverage_abuja.json"
SAMPLE_COUNT = 10
TIMEOUT_MS = 5_000
# No approved production SLO exists in the bounded authority. These are only
# local regression ceilings.
SYNTHETIC_REGRESSION_CEILINGS_MS = {
    "campaign_performance_analysis": 2_000,
    "governed_heatmap_provenance": 2_000,
    "report_worker_artifact_pair": 2_000,
}


class HarnessError(RuntimeError):
    """The synthetic harness cannot prove its local-only contract."""


class NetworkAttemptError(HarnessError):
    """A profiled operation tried to open a network connection."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError("fixture_invalid") from exc
    if not isinstance(value, dict):
        raise HarnessError("fixture_invalid")
    return value


def load_frozen_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    fixture = _read_json(path)
    expected = fixture.pop("frozen_authority_sha256", None)
    if not isinstance(expected, str) or canonical_sha256(fixture) != expected:
        raise HarnessError("input_drift")
    profile = fixture.get("profile")
    if profile != {
        "city": "Abuja",
        "vehicles": 10,
        "advertisers": 5,
        "nominal_duration_days": 92,
        "time_compression": (
            "Ten deterministic in-process samples represent the confirmed three-month cohort; "
            "this is not a burn-in."
        ),
    }:
        raise HarnessError("cohort_contract_invalid")
    return fixture


def load_frozen_coverage(path: Path = COVERAGE_FIXTURE_PATH) -> dict[str, Any]:
    fixture = _read_json(path)
    expected = fixture.get("provenance_sha256")
    try:
        sealed = seal_synthetic_target_area_provenance(fixture)
    except ValueError as exc:
        raise HarnessError("coverage_invalid") from exc
    if expected != sealed["provenance_sha256"]:
        raise HarnessError("input_drift")
    return fixture


def nearest_rank_percentile(samples_ms: Sequence[float], percentile: int) -> float:
    if not samples_ms or not 0 < percentile <= 100:
        raise HarnessError("percentile_input_invalid")
    ranked = sorted(samples_ms)
    return ranked[math.ceil(len(ranked) * percentile / 100) - 1]


@contextlib.contextmanager
def block_network() -> Iterator[None]:
    def blocked(*_args: Any, **_kwargs: Any) -> None:
        raise NetworkAttemptError("network_attempt")

    original_socket = socket.socket
    original_connection = socket.create_connection
    socket.socket = blocked  # type: ignore[assignment]
    socket.create_connection = blocked  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket = original_socket  # type: ignore[assignment]
        socket.create_connection = original_connection  # type: ignore[assignment]


def profile_operation(
    name: str,
    operation: Callable[[], Any],
    *,
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    samples_ms: list[float] = []
    try:
        with block_network():
            for _ in range(SAMPLE_COUNT):
                started = clock()
                operation()
                elapsed_ms = (clock() - started) * 1_000
                if elapsed_ms < 0 or elapsed_ms > TIMEOUT_MS:
                    raise HarnessError("operation_timeout")
                samples_ms.append(elapsed_ms)
    except NetworkAttemptError:
        raise
    except HarnessError:
        raise
    except Exception as exc:
        raise HarnessError("operation_error") from exc
    p95_ms = nearest_rank_percentile(samples_ms, 95)
    ceiling_ms = SYNTHETIC_REGRESSION_CEILINGS_MS[name]
    if p95_ms > ceiling_ms:
        raise HarnessError("threshold_breach")
    result = {
        "operation": name,
        "sample_count": len(samples_ms),
        "percentile_method": "nearest-rank",
        "p50_ms": nearest_rank_percentile(samples_ms, 50),
        "p95_ms": p95_ms,
        "synthetic_regression_ceiling_ms": ceiling_ms,
    }
    if name == "report_worker_artifact_pair":
        total_ms = sum(samples_ms)
        result["artifact_pairs_per_second"] = (
            SAMPLE_COUNT / (total_ms / 1_000) if total_ms else None
        )
    return result


def verify_reproducibility(fixture: Mapping[str, Any]) -> dict[str, str]:
    measurement_input = fixture["measurement_input"]
    snapshot = fixture["report_snapshot"]
    try:
        with block_network():
            first_result = calculate_measurement_result(measurement_input)
            first_csv = render_report_csv(snapshot)
            first_pdf = render_report_pdf(snapshot)
            second_result = calculate_measurement_result(measurement_input)
            second_csv = render_report_csv(snapshot)
            second_pdf = render_report_pdf(snapshot)
    except NetworkAttemptError:
        raise
    except Exception as exc:
        raise HarnessError("reproducibility_operation_error") from exc
    if first_result != second_result or first_csv != second_csv or first_pdf != second_pdf:
        raise HarnessError("reproducibility_mismatch")
    return {
        "input_sha256": canonical_sha256(measurement_input),
        "result_sha256": canonical_sha256(first_result),
        "csv_sha256": __import__("hashlib").sha256(first_csv).hexdigest(),
        "pdf_sha256": __import__("hashlib").sha256(first_pdf).hexdigest(),
    }


def _silent_build_runner(command: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, **kwargs)


def run_harness(*, clock: Callable[[], float] = time.perf_counter) -> dict[str, Any]:
    fixture = load_frozen_fixture()
    coverage = load_frozen_coverage()
    try:
        journey.run_build_path(runner=_silent_build_runner)
        blockers = journey.evaluate_live_boundaries({})
    except journey.JourneyError as exc:
        raise HarnessError("synthetic_journey_failed") from exc
    metrics = (
        profile_operation(
            "campaign_performance_analysis",
            lambda: calculate_measurement_result(fixture["measurement_input"]),
            clock=clock,
        ),
        profile_operation(
            "governed_heatmap_provenance",
            lambda: seal_synthetic_target_area_provenance(coverage),
            clock=clock,
        ),
        profile_operation(
            "report_worker_artifact_pair",
            lambda: (
                render_report_csv(fixture["report_snapshot"]),
                render_report_pdf(fixture["report_snapshot"]),
            ),
            clock=clock,
        ),
    )
    return {
        "schema_version": "w403b-local-load-reproducibility-v1",
        "status": "PASS",
        "synthetic": True,
        "environment": {
            "topology": "local-provider-neutral-in-process",
            "network": "blocked-for-profile-and-reproducibility-paths",
            "external_provider_actions": 0,
        },
        "cohort": fixture["profile"],
        "metrics": metrics,
        "reproducibility": verify_reproducibility(fixture),
        "live_boundaries": {"status": "BLOCKED", "ordered_blockers": blockers},
    }


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print(json.dumps({"status": "FAIL", "error": "usage"}, sort_keys=True))
        return 2
    try:
        result = run_harness()
    except HarnessError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

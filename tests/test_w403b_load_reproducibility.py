from __future__ import annotations

import copy
import json
import socket

import pytest

from scripts import run_w403b_load_reproducibility as harness


def test_confirmed_cohort_and_frozen_inputs_are_exact() -> None:
    fixture = harness.load_frozen_fixture()

    assert fixture["profile"]["city"] == "Abuja"
    assert fixture["profile"]["vehicles"] == 10
    assert fixture["profile"]["advertisers"] == 5
    assert fixture["profile"]["nominal_duration_days"] == 92
    assert fixture["measurement_input"]["sources"]["trip_analytics"].__len__() == 10


def test_nearest_rank_percentiles_and_samples_are_explicit() -> None:
    assert harness.nearest_rank_percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50) == 5
    assert harness.nearest_rank_percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10

    ticks = iter(value / 1_000 for value in range(0, 20, 1))
    result = harness.profile_operation(
        "campaign_performance_analysis", lambda: None, clock=lambda: next(ticks)
    )

    assert result["sample_count"] == 10
    assert result["percentile_method"] == "nearest-rank"
    assert result["p95_ms"] == pytest.approx(1)


@pytest.mark.parametrize(
    "ticks, code", [([0, 6], "operation_timeout"), ([0, 3], "threshold_breach")]
)
def test_timeout_and_threshold_breach_fail_closed(ticks: list[float], code: str) -> None:
    values = iter(ticks * harness.SAMPLE_COUNT)

    with pytest.raises(harness.HarnessError, match=code):
        harness.profile_operation(
            "campaign_performance_analysis", lambda: None, clock=lambda: next(values)
        )


def test_operation_errors_and_network_attempts_fail_closed() -> None:
    with pytest.raises(harness.HarnessError, match="operation_error"):
        harness.profile_operation("campaign_performance_analysis", lambda: 1 / 0)

    with pytest.raises(harness.NetworkAttemptError, match="network_attempt"):
        harness.profile_operation(
            "campaign_performance_analysis", lambda: socket.create_connection(("example.com", 443))
        )


def test_reproducibility_is_two_run_byte_stable_and_drift_rejects(tmp_path) -> None:
    fixture = harness.load_frozen_fixture()
    result = harness.verify_reproducibility(fixture)

    assert set(result) == {"input_sha256", "result_sha256", "csv_sha256", "pdf_sha256"}
    assert all(len(value) == 64 for value in result.values())

    drifted = copy.deepcopy(fixture)
    drifted["measurement_input"]["sources"]["trip_analytics"][0]["distance_m"] = "9999.00"
    drifted["frozen_authority_sha256"] = "0" * 64
    path = tmp_path / "drifted.json"
    path.write_text(json.dumps(drifted), encoding="utf-8")
    with pytest.raises(harness.HarnessError, match="input_drift"):
        harness.load_frozen_fixture(path)


def test_harness_result_is_sanitized_and_enforces_exact_live_blockers(monkeypatch) -> None:
    fixture = harness.load_frozen_fixture()
    coverage = harness.load_frozen_coverage()
    monkeypatch.setattr(harness, "load_frozen_fixture", lambda: fixture)
    monkeypatch.setattr(harness, "load_frozen_coverage", lambda: coverage)
    monkeypatch.setattr(harness.journey, "run_build_path", lambda **_kwargs: None)

    result = harness.run_harness()

    assert result["environment"]["external_provider_actions"] == 0
    assert result["live_boundaries"]["ordered_blockers"] == harness.journey.EXPECTED_BLOCKERS
    assert "latitude" not in json.dumps(result).lower()
    assert "longitude" not in json.dumps(result).lower()
    assert [item["sample_count"] for item in result["metrics"]] == [10, 10, 10]


def test_existing_synthetic_journey_failure_is_sanitized(monkeypatch) -> None:
    fixture = harness.load_frozen_fixture()
    coverage = harness.load_frozen_coverage()
    monkeypatch.setattr(harness, "load_frozen_fixture", lambda: fixture)
    monkeypatch.setattr(harness, "load_frozen_coverage", lambda: coverage)

    def fail_build(**_kwargs) -> None:
        raise harness.journey.JourneyError("untrusted internal detail")

    monkeypatch.setattr(harness.journey, "run_build_path", fail_build)

    with pytest.raises(harness.HarnessError, match="synthetic_journey_failed"):
        harness.run_harness()


def test_main_sanitizes_malformed_coverage_fixture(tmp_path, monkeypatch, capsys) -> None:
    path = tmp_path / "coverage.json"
    path.write_text("{}", encoding="utf-8")
    original_load_coverage = harness.load_frozen_coverage
    monkeypatch.setattr(harness, "load_frozen_coverage", lambda: original_load_coverage(path))

    assert harness.main() == 1
    assert json.loads(capsys.readouterr().out) == {"error": "coverage_invalid", "status": "FAIL"}


def test_main_sanitizes_reproducibility_renderer_failure(monkeypatch, capsys) -> None:
    original_csv = harness.render_report_csv
    calls = 0

    def fail_only_during_reproducibility(snapshot):
        nonlocal calls
        calls += 1
        if calls == harness.SAMPLE_COUNT + 1:
            raise ValueError("untrusted renderer detail")
        return original_csv(snapshot)

    monkeypatch.setattr(harness.journey, "run_build_path", lambda **_kwargs: None)
    monkeypatch.setattr(harness, "render_report_csv", fail_only_during_reproducibility)

    assert harness.main() == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": "reproducibility_operation_error",
        "status": "FAIL",
    }

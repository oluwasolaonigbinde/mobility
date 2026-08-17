"""Packet completeness, fail-closed validation and CLI checks."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from .evaluator import evaluate
from .model import (
    DependencyUnavailableError,
    PolicyChoice,
    UnsetPolicyError,
    fixture_by_id,
    load_fixtures,
    validate_parameters,
)
from .witness import params as _params



def test_fixture_corpus_covers_every_required_case_and_option_output() -> None:
    fixtures = load_fixtures()
    fixture_ids = {fixture.fixture_id for fixture in fixtures}
    required = {
        "slow_creeping_lagos_traffic",
        "stop_4m59_hop_repeat_two_hours",
        "single_long_parked_stay",
        "genuine_brief_stops",
        "out_of_area_parked_does_not_reset",
        "gps_gap_position_unknown",
        "signal_precedence_low_null_teleport",
        "campaign_window_boundary_no_reset",
        "africa_lagos_midnight_boundary",
        "ping_cadence_dense",
        "ping_cadence_sparse",
        "boundary_equality",
        "jitter_around_rolling_boundary",
        "mixed_partition_and_money_expression",
    }
    assert required <= fixture_ids
    for fixture in fixtures:
        assert set(fixture.expectations) == {"A", "B", "C"}
        for expectation in fixture.expectations.values():
            assert set(expectation) == {
                "payable",
                "excluded",
                "held",
                "review",
                "explanation",
            }


@pytest.mark.parametrize("choice", list(PolicyChoice))
def test_unset_policy_parameters_fail_closed(choice: PolicyChoice) -> None:
    with pytest.raises(UnsetPolicyError, match="remain unset"):
        validate_parameters(choice, {})

    params = _params(choice)
    params["effective_at"] = "[OWNER TO SELECT]"
    with pytest.raises(UnsetPolicyError, match="effective_at"):
        validate_parameters(choice, params)


def test_option_c_cannot_run_without_pkg02_hold_infrastructure() -> None:
    fixture = fixture_by_id("stop_4m59_hop_repeat_two_hours")
    params = _params(
        PolicyChoice.FRAUD_DEFERRAL_HOLD,
        hold_infrastructure_ready=False,
    )
    with pytest.raises(DependencyUnavailableError, match="MNY-08A/B"):
        evaluate(fixture, PolicyChoice.FRAUD_DEFERRAL_HOLD, params)


def test_wrong_gap_behavior_is_rejected_instead_of_silently_interpreted() -> None:
    params = _params(
        PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
        gps_gap_state="reset_budget",
    )
    with pytest.raises(ValueError, match="retain_spent_budget"):
        validate_parameters(PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET, params)


def test_cli_lists_shared_fixtures_without_policy_values() -> None:
    script = Path(__file__).with_name("run_evaluator.py")
    completed = subprocess.run(
        [sys.executable, str(script), "--list-fixtures"],
        check=True,
        capture_output=True,
        text=True,
    )
    listed = set(json.loads(completed.stdout))
    assert "stop_4m59_hop_repeat_two_hours" in listed
    assert "slow_creeping_lagos_traffic" in listed


def test_cli_refuses_an_unset_owner_parameter_file(tmp_path: Path) -> None:
    script = Path(__file__).with_name("run_evaluator.py")
    params_path = tmp_path / "unset.json"
    params_path.write_text(json.dumps({"effective_at": "UNSET"}), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--option",
            "A",
            "--params",
            str(params_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "remain unset" in completed.stderr


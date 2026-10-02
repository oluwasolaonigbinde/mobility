from __future__ import annotations

import inspect
import subprocess
import sys

import pytest
from test_measurement_runs import create_measurement_graph

from scripts import evaluate_pilot_gates
from scripts import run_w403b_synthetic_journey as journey


def reviewed_evaluator(*, environment):
    # Supply the reviewed source snapshot while preserving the command's HEAD-only
    # read contract; this verifies the integrated change before its first commit.
    def read_authority(command, **kwargs):
        assert command[:2] == ["git", "show"]
        assert command[2].startswith("HEAD:")
        path = journey.ROOT / command[2].removeprefix("HEAD:")
        return subprocess.CompletedProcess(command, 0, path.read_text(encoding="utf-8"), "")

    return evaluate_pilot_gates.main(environment=environment, runner=read_authority)


def test_stage_contract_and_reviewed_blockers_are_exact() -> None:
    assert journey.STAGES == (
        "advertiser",
        "admin",
        "PWA",
        "synthetic GPS",
        "measurement",
        "Campaign Performance Analysis",
        "qualified synthetic conditional ROI",
        "aggregate contextual activation",
        "payout instruction",
        "incident/recovery",
    )
    assert (
        journey.evaluate_live_boundaries({}, evaluator=reviewed_evaluator)
        == journey.EXPECTED_BLOCKERS
    )


def test_shared_measurement_fixture_preserves_legacy_defaults() -> None:
    parameters = inspect.signature(create_measurement_graph).parameters

    assert parameters["organization_name"].default == "Acme Ads"
    assert parameters["billing_email"].default == "billing@acme.test"
    assert parameters["campaign_name"].default == "Launch Campaign"
    assert parameters["advertiser_first"].default is False


def test_fabricated_runtime_approval_fails_the_real_command_boundary() -> None:
    with pytest.raises(journey.JourneyError):
        journey.evaluate_live_boundaries(
            {
                "INVOICE_ISSUER_EXTERNAL_INPUT_REFERENCE": "fabricated-runtime-approval",
            },
            evaluator=reviewed_evaluator,
        )


@pytest.mark.parametrize("failure", ["pass", "missing", "reordered", "malformed"])
def test_unexpected_gate_result_fails_the_command(failure: str) -> None:
    def evaluator(*, environment):
        assert environment == {}
        if failure == "malformed":
            print("pilot-gate evaluation failed: malformed", file=sys.stderr)
            return 2
        lines = list(journey.EXPECTED_BLOCKERS)
        if failure == "pass":
            lines[0] = "G-money: PASS"
            exit_code = 0
        elif failure == "missing":
            lines[0] = "G-money: BLOCKED — EXT-DISBURSEMENT-PROVIDER"
            exit_code = 1
        else:
            lines[0], lines[1] = lines[1], lines[0]
            exit_code = 1
        print("\n".join(lines))
        return exit_code

    with pytest.raises(journey.JourneyError):
        journey.evaluate_live_boundaries({}, evaluator=evaluator)


def test_build_path_propagates_the_focused_test_failure() -> None:
    def failed_runner(command, **kwargs):
        assert command[-1].endswith("test_correlated_synthetic_pilot_journey")
        assert kwargs["cwd"] == journey.ROOT
        return subprocess.CompletedProcess(command, 1)

    with pytest.raises(journey.JourneyError):
        journey.run_build_path(runner=failed_runner)

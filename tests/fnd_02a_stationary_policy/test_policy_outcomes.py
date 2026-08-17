"""Parameterized outcome and invariant checks for all three FND-02A choices."""

from __future__ import annotations

from copy import deepcopy

import pytest

from .evaluator import evaluate
from .model import fixture_by_id, load_fixtures, PolicyChoice
from .witness import params as _params


def test_stop_hop_farming_is_not_fully_releaseable_for_completed_options() -> None:
    fixture = fixture_by_id("stop_4m59_hop_repeat_two_hours")

    rolling = evaluate(
        fixture,
        PolicyChoice.ROLLING_DISPLACEMENT,
        _params(PolicyChoice.ROLLING_DISPLACEMENT),
    )
    budget = evaluate(
        fixture,
        PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
        _params(
            PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
            cumulative_budget_seconds=fixture.segments[0].seconds,
        ),
    )
    hold = evaluate(
        fixture,
        PolicyChoice.FRAUD_DEFERRAL_HOLD,
        _params(
            PolicyChoice.FRAUD_DEFERRAL_HOLD,
            hold_candidate_seconds_trigger=fixture.segments[0].seconds,
            hold_episode_count_trigger=1,
        ),
    )

    assert rolling.releaseable_seconds < fixture.total_seconds
    assert rolling.excluded_seconds_by_reason["stationary_rolling_displacement"] > 0
    assert budget.releaseable_seconds < fixture.total_seconds
    assert budget.excluded_seconds_by_reason["stationary_subwindow_budget_exceeded"] > 0
    assert hold.releaseable_seconds == 0
    assert hold.held_seconds == hold.payable_seconds
    assert hold.review_required


def test_slow_creeping_traffic_remains_payable_under_option_a() -> None:
    fixture = fixture_by_id("slow_creeping_lagos_traffic")
    outcome = evaluate(
        fixture,
        PolicyChoice.ROLLING_DISPLACEMENT,
        _params(PolicyChoice.ROLLING_DISPLACEMENT),
    )
    assert outcome.payable_seconds == fixture.total_seconds
    assert outcome.excluded_seconds_by_reason == {}
    assert outcome.payable_base_seconds > 0
    assert outcome.payable_premium_seconds > 0


def test_one_long_parked_stay_receives_one_grace_budget_for_every_option() -> None:
    fixture = fixture_by_id("single_long_parked_stay")
    grace = fixture.total_seconds // 5
    for choice in PolicyChoice:
        outcome = evaluate(fixture, choice, _params(choice, stationary_grace_seconds=grace))
        assert outcome.payable_seconds == grace
        assert outcome.excluded_seconds == fixture.total_seconds - grace
        assert outcome.held_seconds == 0


def test_genuine_brief_stops_can_remain_payable_without_a_hidden_threshold() -> None:
    fixture = fixture_by_id("genuine_brief_stops")
    rolling = evaluate(
        fixture,
        PolicyChoice.ROLLING_DISPLACEMENT,
        _params(PolicyChoice.ROLLING_DISPLACEMENT),
    )
    budget = evaluate(
        fixture,
        PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
        _params(
            PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
            cumulative_budget_seconds=fixture.total_seconds,
        ),
    )
    hold = evaluate(
        fixture,
        PolicyChoice.FRAUD_DEFERRAL_HOLD,
        _params(
            PolicyChoice.FRAUD_DEFERRAL_HOLD,
            hold_candidate_seconds_trigger=fixture.total_seconds + 1,
            hold_episode_count_trigger=len(fixture.segments) + 1,
            trigger_logic="all",
        ),
    )
    assert rolling.payable_seconds == fixture.total_seconds
    assert budget.payable_seconds == fixture.total_seconds
    assert hold.releaseable_seconds == fixture.total_seconds
    assert not hold.review_required


def test_out_of_area_slice_has_precedence_without_resetting_stationary_state() -> None:
    fixture = fixture_by_id("out_of_area_parked_does_not_reset")
    grace = fixture.segments[0].seconds // 2
    outcome = evaluate(
        fixture,
        PolicyChoice.ROLLING_DISPLACEMENT,
        _params(
            PolicyChoice.ROLLING_DISPLACEMENT,
            stationary_grace_seconds=grace,
        ),
    )
    assert outcome.payable_seconds == grace
    assert outcome.excluded_seconds_by_reason["out_of_area"] == fixture.segments[1].seconds
    assert outcome.excluded_seconds_by_reason["stationary_rolling_displacement"] == (
        fixture.total_seconds - grace - fixture.segments[1].seconds
    )


def test_gps_gap_resets_rolling_detector_but_not_spent_budget_or_hold_evidence() -> None:
    fixture = fixture_by_id("gps_gap_position_unknown")
    gap_seconds = fixture.segments[1].seconds

    rolling = evaluate(
        fixture,
        PolicyChoice.ROLLING_DISPLACEMENT,
        _params(
            PolicyChoice.ROLLING_DISPLACEMENT,
            confirmation_windows=2,
            stationary_grace_seconds=0,
        ),
    )
    assert rolling.excluded_seconds_by_reason == {"gps_gap": gap_seconds}

    budget = evaluate(
        fixture,
        PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
        _params(
            PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
            cumulative_budget_seconds=fixture.segments[0].seconds,
            stationary_grace_seconds=0,
        ),
    )
    assert budget.excluded_seconds_by_reason["gps_gap"] == gap_seconds
    assert budget.excluded_seconds_by_reason["stationary_subwindow_budget_exceeded"] == (
        fixture.segments[2].seconds
    )

    hold = evaluate(
        fixture,
        PolicyChoice.FRAUD_DEFERRAL_HOLD,
        _params(
            PolicyChoice.FRAUD_DEFERRAL_HOLD,
            hold_candidate_seconds_trigger=(
                fixture.segments[0].seconds + fixture.segments[2].seconds
            ),
            hold_episode_count_trigger=2,
            trigger_logic="all",
        ),
    )
    assert hold.excluded_seconds_by_reason == {"gps_gap": gap_seconds}
    assert hold.held_seconds == hold.payable_seconds


def test_low_null_accuracy_and_teleport_keep_existing_reason_precedence() -> None:
    fixture = fixture_by_id("signal_precedence_low_null_teleport")
    for choice in PolicyChoice:
        params = _params(choice, stationary_grace_seconds=0)
        if choice is PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET:
            params["cumulative_budget_seconds"] = 0
        if choice is PolicyChoice.FRAUD_DEFERRAL_HOLD:
            params["hold_candidate_seconds_trigger"] = fixture.total_seconds + 1
            params["hold_episode_count_trigger"] = len(fixture.segments) + 1
            params["trigger_logic"] = "all"
        outcome = evaluate(fixture, choice, params)
        assert outcome.excluded_seconds_by_reason["low_accuracy"] == 120
        assert outcome.excluded_seconds_by_reason["teleport"] == 60


def test_campaign_window_boundary_does_not_restore_allowance() -> None:
    fixture = fixture_by_id("campaign_window_boundary_no_reset")
    budget = evaluate(
        fixture,
        PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
        _params(
            PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
            cumulative_budget_seconds=fixture.segments[0].seconds,
        ),
    )
    assert budget.excluded_seconds_by_reason["out_of_window"] == fixture.segments[0].seconds
    assert budget.excluded_seconds_by_reason["stationary_subwindow_budget_exceeded"] == (
        fixture.segments[1].seconds
    )
    assert budget.payable_seconds == 0


def test_africa_lagos_midnight_reset_scope_is_explicit() -> None:
    fixture = fixture_by_id("africa_lagos_midnight_boundary")
    one_side = fixture.segments[0].seconds

    trip_budget = evaluate(
        fixture,
        PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
        _params(
            PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
            cumulative_budget_seconds=one_side,
            budget_scope="trip",
        ),
    )
    day_budget = evaluate(
        fixture,
        PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
        _params(
            PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
            cumulative_budget_seconds=one_side,
            budget_scope="lagos_day",
        ),
    )
    assert trip_budget.payable_seconds == one_side
    assert day_budget.payable_seconds == fixture.total_seconds

    trip_hold = evaluate(
        fixture,
        PolicyChoice.FRAUD_DEFERRAL_HOLD,
        _params(
            PolicyChoice.FRAUD_DEFERRAL_HOLD,
            hold_candidate_seconds_trigger=fixture.total_seconds,
            hold_episode_count_trigger=1,
            trigger_logic="all",
            hold_scope="trip",
        ),
    )
    day_hold = evaluate(
        fixture,
        PolicyChoice.FRAUD_DEFERRAL_HOLD,
        _params(
            PolicyChoice.FRAUD_DEFERRAL_HOLD,
            hold_candidate_seconds_trigger=fixture.total_seconds,
            hold_episode_count_trigger=1,
            trigger_logic="all",
            hold_scope="lagos_day",
        ),
    )
    assert trip_hold.held_seconds == fixture.total_seconds
    assert day_hold.held_seconds == 0


def test_ping_cadence_variants_produce_identical_outcomes() -> None:
    dense = fixture_by_id("ping_cadence_dense")
    sparse = fixture_by_id("ping_cadence_sparse")
    for choice in PolicyChoice:
        params = _params(choice)
        dense_outcome = evaluate(dense, choice, deepcopy(params))
        sparse_outcome = evaluate(sparse, choice, deepcopy(params))
        assert dense_outcome.payable_seconds == sparse_outcome.payable_seconds
        assert dense_outcome.held_seconds == sparse_outcome.held_seconds
        assert (
            dense_outcome.excluded_seconds_by_reason
            == sparse_outcome.excluded_seconds_by_reason
        )


def test_boundary_equality_rules_are_inclusive() -> None:
    fixture = fixture_by_id("boundary_equality")

    rolling = evaluate(
        fixture,
        PolicyChoice.ROLLING_DISPLACEMENT,
        _params(
            PolicyChoice.ROLLING_DISPLACEMENT,
            stationary_grace_seconds=0,
            confirmation_windows=1,
        ),
    )
    assert rolling.payable_seconds == 0

    budget = evaluate(
        fixture,
        PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
        _params(
            PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET,
            cumulative_budget_seconds=fixture.total_seconds,
            stationary_grace_seconds=0,
        ),
    )
    assert budget.payable_seconds == fixture.total_seconds

    hold = evaluate(
        fixture,
        PolicyChoice.FRAUD_DEFERRAL_HOLD,
        _params(
            PolicyChoice.FRAUD_DEFERRAL_HOLD,
            hold_candidate_seconds_trigger=fixture.total_seconds,
            hold_episode_count_trigger=2,
            trigger_logic="all",
        ),
    )
    assert hold.held_seconds == fixture.total_seconds


def test_rolling_jitter_obeys_owner_selected_confirmation_and_release_counts() -> None:
    fixture = fixture_by_id("jitter_around_rolling_boundary")
    slow_release = evaluate(
        fixture,
        PolicyChoice.ROLLING_DISPLACEMENT,
        _params(
            PolicyChoice.ROLLING_DISPLACEMENT,
            stationary_grace_seconds=0,
            confirmation_windows=2,
            release_windows=2,
        ),
    )
    immediate_release = evaluate(
        fixture,
        PolicyChoice.ROLLING_DISPLACEMENT,
        _params(
            PolicyChoice.ROLLING_DISPLACEMENT,
            stationary_grace_seconds=0,
            confirmation_windows=2,
            release_windows=1,
        ),
    )
    assert slow_release.excluded_seconds_by_reason["stationary_rolling_displacement"] == 180
    assert immediate_release.excluded_seconds_by_reason["stationary_rolling_displacement"] == 120


@pytest.mark.parametrize("choice", list(PolicyChoice))
def test_every_fixture_partitions_duration_and_keeps_money_symbolic(
    choice: PolicyChoice,
) -> None:
    for fixture in load_fixtures():
        params = _params(choice)
        outcome = evaluate(fixture, choice, params)
        assert outcome.payable_seconds + outcome.excluded_seconds == fixture.total_seconds
        assert 0 <= outcome.held_seconds <= outcome.payable_seconds
        assert outcome.releaseable_seconds == outcome.payable_seconds - outcome.held_seconds
        for expression in (
            outcome.gross_money_expression,
            outcome.held_money_expression,
            outcome.releaseable_money_expression,
        ):
            assert "BASE_RATE_NGN_PER_HOUR" in expression
            assert "PREMIUM_RATE_NGN_PER_HOUR" in expression
            assert "₦" not in expression

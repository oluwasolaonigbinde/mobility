"""Deterministic, test-only evaluator for the FND-02A owner decision packet."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .model import (
    SIGNAL_REASONS,
    Fixture,
    Outcome,
    PolicyChoice,
    Segment,
    validate_parameters,
)


def _scope_key(segment: Segment, scope: str) -> str:
    return "trip" if scope == "trip" else segment.lagos_day


def _rolling_stationary_flags(
    segments: tuple[Segment, ...], params: dict[str, Any]
) -> list[bool]:
    """Classify normalized rolling windows with deterministic hysteresis.

    ``below`` and ``equal`` are stationary (inclusive boundary). Confirmation
    and movement release both backdate to the beginning of their qualifying
    run. A GPS gap resets detector state; area/window exclusions do not.
    """

    flags = [False] * len(segments)
    states: dict[str, dict[str, Any]] = {}
    scope = str(params["reset_scope"])
    confirm = int(params["confirmation_windows"])
    release = int(params["release_windows"])

    def fresh() -> dict[str, Any]:
        return {"active": False, "stationary_run": [], "movement_run": []}

    for index, segment in enumerate(segments):
        key = _scope_key(segment, scope)
        state = states.setdefault(key, fresh())
        if segment.signal == "gps_gap":
            states[key] = fresh()
            continue
        if segment.signal != "valid" or segment.rolling_relation is None:
            continue

        if segment.rolling_relation in {"below", "equal"}:
            state["movement_run"] = []
            state["stationary_run"].append(index)
            if state["active"]:
                flags[index] = True
            elif len(state["stationary_run"]) >= confirm:
                state["active"] = True
                for run_index in state["stationary_run"]:
                    flags[run_index] = True
        else:
            state["stationary_run"] = []
            if not state["active"]:
                state["movement_run"] = []
                continue
            state["movement_run"].append(index)
            flags[index] = True
            if len(state["movement_run"]) >= release:
                for run_index in state["movement_run"]:
                    flags[run_index] = False
                state["active"] = False
                state["movement_run"] = []
    return flags


def _is_long_stationary(segment: Segment, params: dict[str, Any]) -> bool:
    return bool(
        segment.signal == "valid"
        and segment.stationary_candidate
        and segment.episode_duration_seconds is not None
        and segment.episode_duration_seconds >= int(params["stationary_window_seconds"])
    )


def _is_short_stationary(segment: Segment, params: dict[str, Any]) -> bool:
    return bool(
        segment.signal == "valid"
        and segment.stationary_candidate
        and segment.episode_duration_seconds is not None
        and segment.episode_duration_seconds < int(params["stationary_window_seconds"])
    )


def _grace_exclusions(stationary_flags: list[bool], seconds: list[int], grace: int) -> list[int]:
    excluded = [0] * len(stationary_flags)
    remaining = grace
    for index, flagged in enumerate(stationary_flags):
        if not flagged:
            continue
        granted = min(remaining, seconds[index])
        remaining -= granted
        excluded[index] = seconds[index] - granted
    return excluded


def _subwindow_budget_exclusions(
    segments: tuple[Segment, ...], params: dict[str, Any]
) -> list[int]:
    excluded = [0] * len(segments)
    spent: dict[str, int] = defaultdict(int)
    budget = int(params["cumulative_budget_seconds"])
    scope = str(params["budget_scope"])
    for index, segment in enumerate(segments):
        if not _is_short_stationary(segment, params):
            continue
        key = _scope_key(segment, scope)
        before = spent[key]
        after = before + segment.seconds
        # Inclusive rule: exactly-budget time remains payable; only time
        # strictly above the budget is excluded.
        excluded[index] = max(0, after - budget) - max(0, before - budget)
        spent[key] = after
    return excluded


def _hold_scopes(segments: tuple[Segment, ...], params: dict[str, Any]) -> set[str]:
    seconds_by_scope: dict[str, int] = defaultdict(int)
    episodes_by_scope: dict[str, set[str]] = defaultdict(set)
    scope = str(params["hold_scope"])
    for index, segment in enumerate(segments):
        if not _is_short_stationary(segment, params):
            continue
        key = _scope_key(segment, scope)
        seconds_by_scope[key] += segment.seconds
        episodes_by_scope[key].add(segment.episode_id or f"anonymous-{index}")

    held: set[str] = set()
    seconds_trigger = int(params["hold_candidate_seconds_trigger"])
    episode_trigger = int(params["hold_episode_count_trigger"])
    for key in set(seconds_by_scope) | set(episodes_by_scope):
        tests = (
            seconds_by_scope[key] >= seconds_trigger,
            len(episodes_by_scope[key]) >= episode_trigger,
        )
        triggered = any(tests) if params["trigger_logic"] == "any" else all(tests)
        if triggered:
            held.add(key)
    return held


def _money_expression(base_seconds: int, premium_seconds: int) -> str:
    return (
        f"({base_seconds}/3600)*BASE_RATE_NGN_PER_HOUR + "
        f"({premium_seconds}/3600)*PREMIUM_RATE_NGN_PER_HOUR"
    )


def evaluate(fixture: Fixture, choice: PolicyChoice, params: dict[str, Any]) -> Outcome:
    validate_parameters(choice, params)
    segments = fixture.segments
    seconds = [segment.seconds for segment in segments]
    long_flags = [_is_long_stationary(segment, params) for segment in segments]

    if choice is PolicyChoice.ROLLING_DISPLACEMENT:
        rolling_flags = _rolling_stationary_flags(segments, params)
        stationary_flags = [
            long_flag or rolling
            for long_flag, rolling in zip(long_flags, rolling_flags, strict=True)
        ]
        stationary_excluded = _grace_exclusions(
            stationary_flags, seconds, int(params["stationary_grace_seconds"])
        )
        stationary_reason = "stationary_rolling_displacement"
        held_scopes: set[str] = set()
        hold_scope = "trip"
    elif choice is PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET:
        stationary_excluded = _grace_exclusions(
            long_flags, seconds, int(params["stationary_grace_seconds"])
        )
        budget_excluded = _subwindow_budget_exclusions(segments, params)
        stationary_excluded = [
            long_excluded + short_excluded
            for long_excluded, short_excluded in zip(
                stationary_excluded, budget_excluded, strict=True
            )
        ]
        stationary_reason = "stationary_subwindow_budget_exceeded"
        held_scopes = set()
        hold_scope = "trip"
    else:
        stationary_excluded = _grace_exclusions(
            long_flags, seconds, int(params["stationary_grace_seconds"])
        )
        stationary_reason = "stationary"
        held_scopes = _hold_scopes(segments, params)
        hold_scope = str(params["hold_scope"])

    excluded: dict[str, int] = defaultdict(int)
    payable_by_index = [0] * len(segments)
    payable_base = 0
    payable_premium = 0
    explanation_codes: set[str] = set()

    for index, segment in enumerate(segments):
        signal_reason = SIGNAL_REASONS.get(segment.signal)
        if signal_reason:
            excluded[signal_reason] += segment.seconds
            explanation_codes.add(signal_reason)
            continue
        if not segment.in_window:
            excluded["out_of_window"] += segment.seconds
            explanation_codes.add("out_of_window")
            continue
        if not segment.in_area:
            excluded["out_of_area"] += segment.seconds
            explanation_codes.add("out_of_area")
            continue

        stationary = min(segment.seconds, stationary_excluded[index])
        if stationary:
            excluded[stationary_reason] += stationary
            explanation_codes.add(stationary_reason)
        payable = segment.seconds - stationary
        payable_by_index[index] = payable
        if segment.tier == "base":
            payable_base += payable
        else:
            payable_premium += payable

    held_base = 0
    held_premium = 0
    if choice is PolicyChoice.FRAUD_DEFERRAL_HOLD:
        for index, segment in enumerate(segments):
            if _scope_key(segment, hold_scope) not in held_scopes:
                continue
            if segment.tier == "base":
                held_base += payable_by_index[index]
            else:
                held_premium += payable_by_index[index]
        if held_base + held_premium:
            explanation_codes.add("stationary_pattern_hold_pending_review")

    payable_seconds = payable_base + payable_premium
    held_seconds = held_base + held_premium
    releaseable_seconds = payable_seconds - held_seconds
    total_seconds = fixture.total_seconds
    excluded_total = sum(excluded.values())
    if payable_seconds + excluded_total != total_seconds:
        raise AssertionError(
            f"partition invariant failed for {fixture.fixture_id}/{choice.value}: "
            f"{payable_seconds}+{excluded_total}!={total_seconds}"
        )
    if held_seconds > payable_seconds:
        raise AssertionError("hold overlay exceeds payable time")

    return Outcome(
        fixture_id=fixture.fixture_id,
        option=choice,
        total_seconds=total_seconds,
        payable_seconds=payable_seconds,
        releaseable_seconds=releaseable_seconds,
        held_seconds=held_seconds,
        excluded_seconds_by_reason=dict(sorted(excluded.items())),
        payable_base_seconds=payable_base,
        payable_premium_seconds=payable_premium,
        held_base_seconds=held_base,
        held_premium_seconds=held_premium,
        review_required=held_seconds > 0,
        explanation_codes=tuple(sorted(explanation_codes)),
        gross_money_expression=_money_expression(payable_base, payable_premium),
        held_money_expression=_money_expression(held_base, held_premium),
        releaseable_money_expression=_money_expression(
            payable_base - held_base, payable_premium - held_premium
        ),
    )

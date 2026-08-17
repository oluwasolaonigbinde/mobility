"""Algebraic test witnesses; none are policy recommendations or defaults."""

from __future__ import annotations

from .model import PolicyChoice, fixture_by_id


def params(choice: PolicyChoice, **overrides: object) -> dict[str, object]:
    stop_fixture = fixture_by_id("stop_4m59_hop_repeat_two_hours")
    stop_seconds = stop_fixture.segments[0].episode_duration_seconds
    assert stop_seconds is not None
    window_seconds = 2 * (stop_seconds + 1)
    values: dict[str, object] = {
        "effective_at": "2099-01-01T00:00:00+00:00",
        "eligibility_revision": "TEST-WITNESS-NOT-A-POLICY",
        "effective_application": "new_acceptances_only",
        "stationary_radius_m": 1,
        "stationary_window_seconds": window_seconds,
        "stationary_grace_seconds": window_seconds // 4,
        "max_accuracy_m": 1,
        "teleport_kmh": 1,
        "max_ping_gap_seconds": 1,
    }
    if choice is PolicyChoice.ROLLING_DISPLACEMENT:
        values.update(
            {
                "rolling_window_seconds": window_seconds,
                "minimum_net_displacement_m": 1,
                "confirmation_windows": 1,
                "release_windows": 1,
                "reset_scope": "trip",
                "gps_gap_state": "reset_detector",
            }
        )
    elif choice is PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET:
        values.update(
            {
                "cumulative_budget_seconds": window_seconds // 2,
                "budget_scope": "trip",
                "gps_gap_state": "retain_spent_budget",
            }
        )
    else:
        values.update(
            {
                "hold_candidate_seconds_trigger": window_seconds // 2,
                "hold_episode_count_trigger": 2,
                "trigger_logic": "any",
                "hold_scope": "trip",
                "fraud_assessment_version": "TEST-WITNESS-ASSESSMENT",
                "gps_gap_state": "retain_evidence",
                "hold_infrastructure_ready": True,
            }
        )
    values.update(overrides)
    return values

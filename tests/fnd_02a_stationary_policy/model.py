"""Data model, fixture loader and fail-closed parameter validation for FND-02A."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).with_name("fixtures")


class PolicyChoice(StrEnum):
    ROLLING_DISPLACEMENT = "A"
    CUMULATIVE_SUBWINDOW_BUDGET = "B"
    FRAUD_DEFERRAL_HOLD = "C"


class UnsetPolicyError(ValueError):
    """Raised when a decision parameter is absent or still a placeholder."""


class DependencyUnavailableError(RuntimeError):
    """Raised when option C is evaluated without the PKG-02 hold contract."""


SIGNAL_REASONS = {
    "gps_gap": "gps_gap",
    "low_accuracy": "low_accuracy",
    "null_accuracy": "low_accuracy",
    "teleport": "teleport",
}

COMMON_REQUIRED = {
    "effective_at",
    "eligibility_revision",
    "effective_application",
    "stationary_radius_m",
    "stationary_window_seconds",
    "stationary_grace_seconds",
    "max_accuracy_m",
    "teleport_kmh",
    "max_ping_gap_seconds",
}

OPTION_REQUIRED = {
    PolicyChoice.ROLLING_DISPLACEMENT: {
        "rolling_window_seconds",
        "minimum_net_displacement_m",
        "confirmation_windows",
        "release_windows",
        "reset_scope",
        "gps_gap_state",
    },
    PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET: {
        "cumulative_budget_seconds",
        "budget_scope",
        "gps_gap_state",
    },
    PolicyChoice.FRAUD_DEFERRAL_HOLD: {
        "hold_candidate_seconds_trigger",
        "hold_episode_count_trigger",
        "trigger_logic",
        "hold_scope",
        "fraud_assessment_version",
        "gps_gap_state",
        "hold_infrastructure_ready",
    },
}

PLACEHOLDERS = {"", "UNSET", "TBD", "<unset>", "[OWNER TO SELECT]"}


@dataclass(frozen=True)
class Segment:
    seconds: int
    lagos_day: str
    tier: str
    signal: str
    in_window: bool
    in_area: bool
    stationary_candidate: bool
    episode_id: str | None
    episode_duration_seconds: int | None
    rolling_relation: str | None


@dataclass(frozen=True)
class Fixture:
    fixture_id: str
    description: str
    segments: tuple[Segment, ...]
    expectations: dict[str, dict[str, Any]]
    tags: tuple[str, ...]

    @property
    def total_seconds(self) -> int:
        return sum(segment.seconds for segment in self.segments)


@dataclass(frozen=True)
class Outcome:
    fixture_id: str
    option: PolicyChoice
    total_seconds: int
    payable_seconds: int
    releaseable_seconds: int
    held_seconds: int
    excluded_seconds_by_reason: dict[str, int]
    payable_base_seconds: int
    payable_premium_seconds: int
    held_base_seconds: int
    held_premium_seconds: int
    review_required: bool
    explanation_codes: tuple[str, ...]
    gross_money_expression: str
    held_money_expression: str
    releaseable_money_expression: str

    @property
    def excluded_seconds(self) -> int:
        return sum(self.excluded_seconds_by_reason.values())


def _expand_timeline(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for item in timeline:
        if "repeat" not in item:
            expanded.append(item)
            continue
        repeat = int(item["repeat"])
        pattern = item.get("pattern")
        if repeat <= 0 or not isinstance(pattern, list):
            raise ValueError("repeat blocks require a positive repeat and a pattern list")
        for index in range(repeat):
            for raw in pattern:
                segment = dict(raw)
                episode_id = segment.get("episode_id")
                if isinstance(episode_id, str):
                    segment["episode_id"] = episode_id.format(index=index)
                expanded.append(segment)
    return expanded


def _load_fixture_file(path: Path) -> list[Fixture]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "fnd-02a-fixtures-v1":
        raise ValueError(f"unknown FND-02A fixture schema in {path.name}")
    fixtures: list[Fixture] = []
    for raw_fixture in payload["fixtures"]:
        segments = []
        for raw in _expand_timeline(raw_fixture["timeline"]):
            segment = Segment(
                seconds=int(raw["seconds"]),
                lagos_day=str(raw.get("lagos_day", "D0")),
                tier=str(raw.get("tier", "base")),
                signal=str(raw.get("signal", "valid")),
                in_window=bool(raw.get("in_window", True)),
                in_area=bool(raw.get("in_area", True)),
                stationary_candidate=bool(raw.get("stationary_candidate", False)),
                episode_id=raw.get("episode_id"),
                episode_duration_seconds=(
                    int(raw["episode_duration_seconds"])
                    if raw.get("episode_duration_seconds") is not None
                    else None
                ),
                rolling_relation=raw.get("rolling_relation"),
            )
            if segment.seconds <= 0:
                raise ValueError(f"{raw_fixture['id']}: segment seconds must be positive")
            if segment.tier not in {"base", "premium"}:
                raise ValueError(f"{raw_fixture['id']}: unknown tier {segment.tier!r}")
            if segment.signal not in {"valid", *SIGNAL_REASONS}:
                raise ValueError(f"{raw_fixture['id']}: unknown signal {segment.signal!r}")
            if segment.rolling_relation not in {None, "below", "equal", "above"}:
                raise ValueError(
                    f"{raw_fixture['id']}: unknown rolling relation "
                    f"{segment.rolling_relation!r}"
                )
            segments.append(segment)
        fixtures.append(
            Fixture(
                fixture_id=str(raw_fixture["id"]),
                description=str(raw_fixture["description"]),
                segments=tuple(segments),
                expectations=dict(raw_fixture["expected_by_option"]),
                tags=tuple(raw_fixture.get("tags", [])),
            )
        )
    return fixtures


def load_fixtures(path: Path = FIXTURE_DIR) -> tuple[Fixture, ...]:
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    if not files:
        raise ValueError("FND-02A fixture corpus is empty")
    fixtures = [fixture for file_path in files for fixture in _load_fixture_file(file_path)]
    ids = [fixture.fixture_id for fixture in fixtures]
    if len(ids) != len(set(ids)):
        raise ValueError("FND-02A fixture ids must be unique")
    return tuple(fixtures)


def fixture_by_id(fixture_id: str) -> Fixture:
    for fixture in load_fixtures():
        if fixture.fixture_id == fixture_id:
            return fixture
    raise KeyError(fixture_id)


def _is_unset(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() in PLACEHOLDERS)


def _positive_number(params: dict[str, Any], key: str, *, allow_zero: bool = False) -> None:
    value = params[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} must be numeric")
    if value < 0 or (value == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{key} must be {qualifier}")


def validate_parameters(choice: PolicyChoice, params: dict[str, Any]) -> None:
    required = COMMON_REQUIRED | OPTION_REQUIRED[choice]
    missing = sorted(key for key in required if key not in params or _is_unset(params[key]))
    if missing:
        raise UnsetPolicyError(
            f"{choice.value} policy parameters remain unset: {', '.join(missing)}"
        )

    if params["effective_application"] != "new_acceptances_only":
        raise ValueError(
            "effective_application must be new_acceptances_only to preserve frozen accepted terms"
        )

    try:
        datetime.fromisoformat(str(params["effective_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("effective_at must be an RFC3339/ISO-8601 timestamp") from exc

    for key in (
        "stationary_radius_m",
        "stationary_window_seconds",
        "max_accuracy_m",
        "teleport_kmh",
        "max_ping_gap_seconds",
    ):
        _positive_number(params, key)
    _positive_number(params, "stationary_grace_seconds", allow_zero=True)

    if choice is PolicyChoice.ROLLING_DISPLACEMENT:
        for key in (
            "rolling_window_seconds",
            "minimum_net_displacement_m",
            "confirmation_windows",
            "release_windows",
        ):
            _positive_number(params, key)
        if not isinstance(params["confirmation_windows"], int) or not isinstance(
            params["release_windows"], int
        ):
            raise ValueError("confirmation_windows and release_windows must be integers")
        if params["reset_scope"] not in {"trip", "lagos_day"}:
            raise ValueError("reset_scope must be trip or lagos_day")
        if params["gps_gap_state"] != "reset_detector":
            raise ValueError("option A requires gps_gap_state=reset_detector")
    elif choice is PolicyChoice.CUMULATIVE_SUBWINDOW_BUDGET:
        _positive_number(params, "cumulative_budget_seconds", allow_zero=True)
        if params["budget_scope"] not in {"trip", "lagos_day"}:
            raise ValueError("budget_scope must be trip or lagos_day")
        if params["gps_gap_state"] != "retain_spent_budget":
            raise ValueError("option B requires gps_gap_state=retain_spent_budget")
    else:
        _positive_number(params, "hold_candidate_seconds_trigger")
        _positive_number(params, "hold_episode_count_trigger")
        if not isinstance(params["hold_episode_count_trigger"], int):
            raise ValueError("hold_episode_count_trigger must be an integer")
        if params["trigger_logic"] not in {"any", "all"}:
            raise ValueError("trigger_logic must be any or all")
        if params["hold_scope"] not in {"trip", "lagos_day"}:
            raise ValueError("hold_scope must be trip or lagos_day")
        if params["gps_gap_state"] != "retain_evidence":
            raise ValueError("option C requires gps_gap_state=retain_evidence")
        if not isinstance(params["hold_infrastructure_ready"], bool):
            raise ValueError("hold_infrastructure_ready must be boolean")
        if not params["hold_infrastructure_ready"]:
            raise DependencyUnavailableError(
                "option C requires MNY-08A/B authoritative assessment and hold infrastructure"
            )

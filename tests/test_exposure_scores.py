from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from report_fixtures import DAY_1

from app.core.errors import AppError
from app.models.exposure_score import ExposureScore
from app.services.exposure_scores import (
    EXPOSURE_V1_FORMULA_CONTRACT,
    calculate_exposure_score_v1,
    exposure_score_reproducible,
)
from app.services.report_integrity import canonical_sha256


def score_input(routes: list[dict]) -> dict:
    return {
        "schema_version": "exposure-score-input-v1",
        "organization_id": str(uuid4()),
        "campaign_id": str(uuid4()),
        "measurement_run_id": str(uuid4()),
        "measurement_input_sha256": "a" * 64,
        "measurement_result_sha256": "b" * 64,
        "measurement_proof_sha256": "c" * 64,
        "period": {
            "start_at": DAY_1.isoformat(),
            "end_at": (DAY_1 + timedelta(days=1)).isoformat(),
        },
        "routes": routes,
    }


def route(
    *,
    status: str = "computed",
    distance_m: str = "10000",
    active_tracking_seconds: int = 3600,
    quality_score: str = "1",
) -> dict:
    return {
        "trip_analytics_id": str(uuid4()),
        "trip_session_id": str(uuid4()),
        "status": status,
        "source_formula_version": "route_analytics_v1",
        "distance_m": distance_m,
        "active_tracking_seconds": active_tracking_seconds,
        "quality_score": quality_score,
    }


def test_exposure_v1_golden_formula_boundaries_missing_data_and_uncertainty() -> None:
    result = calculate_exposure_score_v1(
        score_input(
            [
                route(),
                route(distance_m="5000", active_tracking_seconds=1800, quality_score="0.5"),
                route(status="insufficient_data", distance_m="0", active_tracking_seconds=0),
            ]
        )
    )

    assert canonical_sha256(EXPOSURE_V1_FORMULA_CONTRACT) == result["formula_fingerprint"]
    assert result["formula_version"] == "exposure_v1"
    assert result["unit"] == "points"
    assert result["range"] == {"minimum": "0.00", "maximum": "100.00"}
    assert result["status"] == "scored"
    assert result["score"] == "75.00"
    assert [item["score"] for item in result["route_scores"]] == ["100.00", "25.00"]
    assert result["route_count"] == 2
    assert result["missing_route_count"] == 1
    assert result["uncertainty"]["classification"] == "synthetic_uncalibrated_index"
    assert "not" in result["uncertainty"]["statement"].lower()

    capped = calculate_exposure_score_v1(
        score_input([route(distance_m="999999", active_tracking_seconds=999999)])
    )
    assert capped["score"] == "100.00"

    missing = calculate_exposure_score_v1(
        score_input([route(status="blocked", distance_m="0", active_tracking_seconds=0)])
    )
    assert missing["status"] == "insufficient_data"
    assert missing["score"] is None
    assert missing["route_scores"] == []


def test_unknown_formula_version_conflicts_without_touching_issued_history() -> None:
    with pytest.raises(AppError, match="not supported") as unsupported:
        calculate_exposure_score_v1(score_input([route()]), formula_version="exposure_v2")
    assert unsupported.value.code == "EXPOSURE_FORMULA_VERSION_UNSUPPORTED"


def test_later_current_formula_selection_does_not_change_v1_history(monkeypatch) -> None:
    from app.services import exposure_scores

    input_snapshot = score_input([route()])
    result_snapshot = calculate_exposure_score_v1(input_snapshot)
    score = ExposureScore(
        id=uuid4(),
        organization_id=UUID(input_snapshot["organization_id"]),
        campaign_id=UUID(input_snapshot["campaign_id"]),
        measurement_run_id=UUID(input_snapshot["measurement_run_id"]),
        issued_by_user_id=uuid4(),
        formula_version="exposure_v1",
        formula_fingerprint=result_snapshot["formula_fingerprint"],
        input_snapshot=input_snapshot,
        input_fingerprint=result_snapshot["input_fingerprint"],
        result_snapshot=result_snapshot,
        result_fingerprint=canonical_sha256(result_snapshot),
        measurement_input_sha256=input_snapshot["measurement_input_sha256"],
        measurement_result_sha256=input_snapshot["measurement_result_sha256"],
        measurement_proof_sha256=input_snapshot["measurement_proof_sha256"],
    )

    monkeypatch.setattr(exposure_scores, "EXPOSURE_FORMULA_VERSION", "exposure_v2")

    assert exposure_score_reproducible(score) is True
    assert score.result_snapshot["score"] == "100.00"

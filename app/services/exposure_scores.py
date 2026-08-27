from __future__ import annotations

import hashlib
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.exposure_score import ExposureScore
from app.models.measurement import MeasurementRun
from app.schemas.exposure_scores import (
    AdvertiserExposureScoreRead,
    AdvertiserExposureScoreResultRead,
    ExposureScoreRead,
    ExposureScoreResultRead,
)
from app.services.measurement import canonical_sha256, measurement_run_reproducible

EXPOSURE_V1_FORMULA_VERSION = "exposure_v1"
EXPOSURE_FORMULA_VERSION = EXPOSURE_V1_FORMULA_VERSION
EXPOSURE_V1_FORMULA_CONTRACT: dict[str, Any] = {
    "formula_version": EXPOSURE_V1_FORMULA_VERSION,
    "scope": "campaign_route",
    "unit": "points",
    "range": {"minimum": "0.00", "maximum": "100.00"},
    "inputs": ["distance_m", "active_tracking_seconds", "quality_score"],
    "constants": {
        "distance_cap_m": "10000",
        "active_tracking_cap_seconds": 3600,
        "distance_weight": "0.60",
        "active_tracking_weight": "0.40",
    },
    "route_calculation": (
        "100 × quality_score × (0.60 × min(distance_m / 10000, 1) + "
        "0.40 × min(active_tracking_seconds / 3600, 1))"
    ),
    "campaign_calculation": (
        "Active-tracking-seconds-weighted mean of computed route scores; a computed "
        "zero-second route has weight 1."
    ),
    "missing_data": (
        "Only route analytics with status computed are scored. Other routes are excluded "
        "and counted. With no computed routes the status is insufficient_data and score is null."
    ),
    "rounding": "ROUND_HALF_UP to 2 decimal places",
}

_HUNDRED = Decimal("100")
_DISTANCE_CAP_M = Decimal("10000")
_ACTIVE_SECONDS_CAP = Decimal("3600")
_DISTANCE_WEIGHT = Decimal("0.60")
_ACTIVE_WEIGHT = Decimal("0.40")
_SCORE_QUANTUM = Decimal("0.01")


def _invalid_input(message: str) -> AppError:
    return AppError(
        "EXPOSURE_SCORE_INPUT_INVALID",
        message,
        status_code=status.HTTP_409_CONFLICT,
    )


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise _invalid_input(f"Exposure score input {field_name} must be numeric") from exc
    if not parsed.is_finite() or parsed < 0:
        raise _invalid_input(f"Exposure score input {field_name} must be finite and non-negative")
    return parsed


def _ratio(value: Decimal, cap: Decimal) -> Decimal:
    return min(value / cap, Decimal("1"))


def calculate_exposure_score_v1(
    input_snapshot: dict[str, Any],
    *,
    formula_version: str = EXPOSURE_V1_FORMULA_VERSION,
) -> dict[str, Any]:
    if formula_version != EXPOSURE_V1_FORMULA_VERSION:
        raise AppError(
            "EXPOSURE_FORMULA_VERSION_UNSUPPORTED",
            f"Exposure formula version {formula_version} is not supported",
            status_code=status.HTTP_409_CONFLICT,
        )
    routes = input_snapshot.get("routes")
    if not isinstance(routes, list):
        raise _invalid_input("Exposure score routes must be a list")

    route_scores: list[dict[str, Any]] = []
    weighted_total = Decimal("0")
    total_weight = Decimal("0")
    for item in routes:
        if not isinstance(item, dict):
            raise _invalid_input("Every exposure score route must be an object")
        if item.get("status") != "computed":
            continue
        analytics_id = item.get("trip_analytics_id")
        trip_session_id = item.get("trip_session_id")
        if not isinstance(analytics_id, str) or not isinstance(trip_session_id, str):
            raise _invalid_input("Every computed route must retain its frozen source identity")
        distance_m = _decimal(item.get("distance_m"), "distance_m")
        active_seconds = _decimal(item.get("active_tracking_seconds"), "active_tracking_seconds")
        quality = _decimal(item.get("quality_score"), "quality_score")
        if quality > 1:
            raise _invalid_input("Exposure score input quality_score must be between 0 and 1")
        composite = _DISTANCE_WEIGHT * _ratio(
            distance_m, _DISTANCE_CAP_M
        ) + _ACTIVE_WEIGHT * _ratio(active_seconds, _ACTIVE_SECONDS_CAP)
        route_score = (_HUNDRED * quality * composite).quantize(
            _SCORE_QUANTUM, rounding=ROUND_HALF_UP
        )
        weight = max(active_seconds, Decimal("1"))
        weighted_total += route_score * weight
        total_weight += weight
        route_scores.append(
            {
                "trip_analytics_id": analytics_id,
                "trip_session_id": trip_session_id,
                "score": str(route_score),
            }
        )

    score = (
        (weighted_total / total_weight).quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP)
        if route_scores
        else None
    )
    input_fingerprint = canonical_sha256(input_snapshot)
    formula_fingerprint = canonical_sha256(EXPOSURE_V1_FORMULA_CONTRACT)
    provenance_fields = (
        "measurement_run_id",
        "measurement_input_sha256",
        "measurement_result_sha256",
        "measurement_proof_sha256",
    )
    if any(not isinstance(input_snapshot.get(field), str) for field in provenance_fields):
        raise _invalid_input("Exposure score input must retain measurement-run provenance")
    return {
        "schema_version": "exposure-score-result-v1",
        "label": "Exposure score",
        "metric_class": "operational_composite_index",
        "formula_version": EXPOSURE_V1_FORMULA_VERSION,
        "formula_fingerprint": formula_fingerprint,
        "input_fingerprint": input_fingerprint,
        "unit": "points",
        "range": {"minimum": "0.00", "maximum": "100.00"},
        "status": "scored" if score is not None else "insufficient_data",
        "score": str(score) if score is not None else None,
        "route_count": len(route_scores),
        "missing_route_count": len(routes) - len(route_scores),
        "route_scores": route_scores,
        "formula": EXPOSURE_V1_FORMULA_CONTRACT,
        "uncertainty": {
            "classification": "synthetic_uncalibrated_index",
            "statement": (
                "Synthetic provider-neutral operational index; not an impression estimate, "
                "audience count, statistical confidence interval, attribution result or ROI. "
                "Pilot calibration and live methodology approval remain absent."
            ),
        },
        "provenance": {
            "measurement_run_id": input_snapshot["measurement_run_id"],
            "measurement_input_sha256": input_snapshot["measurement_input_sha256"],
            "measurement_result_sha256": input_snapshot["measurement_result_sha256"],
            "measurement_proof_sha256": input_snapshot["measurement_proof_sha256"],
        },
    }


def build_exposure_score_input(run: MeasurementRun) -> dict[str, Any]:
    try:
        analytics = run.input_manifest["sources"]["trip_analytics"]
        period = run.input_manifest["period"]
        routes = sorted(
            (
                {
                    "trip_analytics_id": item["id"],
                    "trip_session_id": item["trip_session_id"],
                    "status": item["status"],
                    "source_formula_version": item["formula_version"],
                    "distance_m": item["distance_m"],
                    "active_tracking_seconds": item["active_tracking_seconds"],
                    "quality_score": item["quality_score"],
                }
                for item in analytics
            ),
            key=lambda item: (item["trip_session_id"], item["trip_analytics_id"]),
        )
    except (KeyError, TypeError) as exc:
        raise _invalid_input(
            "The immutable measurement run lacks required exposure score inputs"
        ) from exc
    return {
        "schema_version": "exposure-score-input-v1",
        "organization_id": str(run.organization_id),
        "campaign_id": str(run.campaign_id),
        "measurement_run_id": str(run.id),
        "measurement_input_sha256": run.input_manifest_sha256,
        "measurement_result_sha256": run.result_manifest_sha256,
        "measurement_proof_sha256": run.proof_manifest_sha256,
        "period": period,
        "routes": routes,
    }


def exposure_score_reproducible(score: ExposureScore) -> bool:
    if score.formula_version != EXPOSURE_V1_FORMULA_VERSION:
        return False
    if canonical_sha256(EXPOSURE_V1_FORMULA_CONTRACT) != score.formula_fingerprint:
        return False
    if canonical_sha256(score.input_snapshot) != score.input_fingerprint:
        return False
    if canonical_sha256(score.result_snapshot) != score.result_fingerprint:
        return False
    try:
        reproduced = calculate_exposure_score_v1(score.input_snapshot)
    except AppError:
        return False
    return reproduced == score.result_snapshot


async def exposure_score_is_stale(session: AsyncSession, score: ExposureScore) -> bool:
    run = await session.get(MeasurementRun, score.measurement_run_id)
    return (
        run is None
        or run.organization_id != score.organization_id
        or run.campaign_id != score.campaign_id
        or run.input_manifest_sha256 != score.measurement_input_sha256
        or run.result_manifest_sha256 != score.measurement_result_sha256
        or run.proof_manifest_sha256 != score.measurement_proof_sha256
        or not measurement_run_reproducible(run)
        or not exposure_score_reproducible(score)
    )


async def _score_lock(
    session: AsyncSession, measurement_run_id: UUID, formula_version: str
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    digest = hashlib.sha256(
        f"exposure-score:{measurement_run_id}:{formula_version}".encode()
    ).digest()[:8]
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(digest, "big", signed=True)},
    )


async def issue_exposure_score_for_run(session: AsyncSession, run: MeasurementRun) -> ExposureScore:
    await _score_lock(session, run.id, EXPOSURE_FORMULA_VERSION)
    existing = await session.scalar(
        select(ExposureScore).where(
            ExposureScore.measurement_run_id == run.id,
            ExposureScore.formula_version == EXPOSURE_FORMULA_VERSION,
        )
    )
    if existing is not None:
        if await exposure_score_is_stale(session, existing):
            raise AppError(
                "EXPOSURE_SCORE_INTEGRITY_FAILURE",
                "The issued exposure score no longer matches its immutable measurement run",
                status_code=status.HTTP_409_CONFLICT,
            )
        return existing
    if not measurement_run_reproducible(run):
        raise AppError(
            "EXPOSURE_SCORE_MEASUREMENT_RUN_INVALID",
            "The immutable measurement run did not reproduce",
            status_code=status.HTTP_409_CONFLICT,
        )
    input_snapshot = build_exposure_score_input(run)
    result_snapshot = calculate_exposure_score_v1(
        input_snapshot, formula_version=EXPOSURE_FORMULA_VERSION
    )
    latest = await session.scalar(
        select(ExposureScore)
        .where(
            ExposureScore.campaign_id == run.campaign_id,
            ~ExposureScore.id.in_(
                select(ExposureScore.reissue_of_score_id).where(
                    ExposureScore.reissue_of_score_id.is_not(None)
                )
            ),
        )
        .order_by(ExposureScore.created_at.desc(), ExposureScore.id.desc())
        .limit(1)
    )
    score = ExposureScore(
        organization_id=run.organization_id,
        campaign_id=run.campaign_id,
        measurement_run_id=run.id,
        issued_by_user_id=run.created_by_user_id,
        formula_version=EXPOSURE_FORMULA_VERSION,
        formula_fingerprint=result_snapshot["formula_fingerprint"],
        input_snapshot=input_snapshot,
        input_fingerprint=result_snapshot["input_fingerprint"],
        result_snapshot=result_snapshot,
        result_fingerprint=canonical_sha256(result_snapshot),
        measurement_input_sha256=run.input_manifest_sha256,
        measurement_result_sha256=run.result_manifest_sha256,
        measurement_proof_sha256=run.proof_manifest_sha256,
        reissue_of_score_id=latest.id if latest is not None else None,
    )
    session.add(score)
    await session.flush()
    return score


async def exposure_score_read(session: AsyncSession, score: ExposureScore) -> ExposureScoreRead:
    stale = await exposure_score_is_stale(session, score)
    return ExposureScoreRead(
        id=score.id,
        organization_id=score.organization_id,
        campaign_id=score.campaign_id,
        measurement_run_id=score.measurement_run_id,
        issued_by_user_id=score.issued_by_user_id,
        formula_version=score.formula_version,
        formula_fingerprint=score.formula_fingerprint,
        input_fingerprint=score.input_fingerprint,
        result_fingerprint=score.result_fingerprint,
        measurement_input_sha256=score.measurement_input_sha256,
        measurement_result_sha256=score.measurement_result_sha256,
        measurement_proof_sha256=score.measurement_proof_sha256,
        result=score.result_snapshot,
        reissue_of_score_id=score.reissue_of_score_id,
        reproducible=exposure_score_reproducible(score),
        stale=stale,
        created_at=score.created_at,
    )


async def advertiser_exposure_score_read(
    session: AsyncSession, score: ExposureScore
) -> AdvertiserExposureScoreRead:
    internal_result = ExposureScoreResultRead.model_validate(score.result_snapshot)
    return AdvertiserExposureScoreRead(
        formula_version=score.formula_version,
        formula_fingerprint=score.formula_fingerprint,
        input_fingerprint=score.input_fingerprint,
        result_fingerprint=score.result_fingerprint,
        measurement_input_sha256=score.measurement_input_sha256,
        measurement_result_sha256=score.measurement_result_sha256,
        measurement_proof_sha256=score.measurement_proof_sha256,
        result=AdvertiserExposureScoreResultRead.model_validate(
            internal_result.model_dump(exclude={"route_scores"})
        ),
        reproducible=exposure_score_reproducible(score),
        stale=await exposure_score_is_stale(session, score),
        created_at=score.created_at,
    )

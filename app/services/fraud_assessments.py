from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.integrity import is_expected_uniqueness_conflict
from app.models.fraud_assessment import (
    SUCCESSFUL_FRAUD_ASSESSMENT_STATUSES,
    FraudAssessment,
    FraudAssessmentStatus,
)
from app.models.route_replay import (
    SUCCESSFUL_ROUTE_REPLAY_STATUSES,
    RouteReplaySignature,
)
from app.models.trip_analytics import FraudFlag, TripAnalytics
from app.services.provenance import stable_source_fingerprint
from app.services.route_replay import route_replay_config_fingerprint
from app.services.trip_analytics import analytics_output_fingerprint

ASSESSMENT_ROW_CONSTRAINTS = frozenset({"uq_fraud_assessments_trip_session_id"})
ASSESSMENT_ERROR_CODE = "assessment_evaluation_failed"
UNAVAILABLE_FINGERPRINT = "0" * 64


@dataclass(frozen=True)
class FraudAssessmentResult:
    assessment: FraudAssessment
    changed: bool


@dataclass(frozen=True)
class CurrentFraudAssessment:
    assessment: FraudAssessment | None
    analytics: TripAnalytics | None
    flags: list[FraudFlag]
    current: bool


def current_flag_facts(flags: Sequence[FraudFlag]) -> list[dict[str, object]]:
    return sorted(
        (
            {
                "flag_type": flag.flag_type,
                "severity": flag.severity,
                "status": flag.status,
                "description": flag.description,
                "evidence": flag.evidence,
            }
            for flag in flags
        ),
        key=lambda item: (str(item["flag_type"]), str(item["severity"])),
    )


def assessment_inputs_fingerprint(
    *,
    analytics: TripAnalytics,
    flags: Sequence[FraudFlag],
    formula_version: str,
    upstream_facts: Mapping[str, object] | None = None,
) -> tuple[str, str]:
    source_fingerprint = analytics_output_fingerprint(analytics)
    return source_fingerprint, stable_source_fingerprint(
        {
            "formula_version": formula_version,
            "source_analytics_fingerprint": source_fingerprint,
            "flags": current_flag_facts(flags),
            "upstream": dict(upstream_facts or {}),
        }
    )


def is_current_successful_assessment(
    assessment: FraudAssessment | None,
    *,
    analytics: TripAnalytics,
    flags: Sequence[FraudFlag],
    settings: Settings,
    upstream_facts: Mapping[str, object] | None = None,
) -> bool:
    if assessment is None or assessment.status not in SUCCESSFUL_FRAUD_ASSESSMENT_STATUSES:
        return False
    source_fingerprint, inputs_fingerprint = assessment_inputs_fingerprint(
        analytics=analytics,
        flags=flags,
        formula_version=settings.fraud_assessment_formula_version,
        upstream_facts=upstream_facts,
    )
    return (
        assessment.formula_version == settings.fraud_assessment_formula_version
        and assessment.source_analytics_fingerprint == source_fingerprint
        and assessment.inputs_fingerprint == inputs_fingerprint
    )


def route_replay_assessment_facts(signature: RouteReplaySignature) -> dict[str, object]:
    return {
        "detector_version": signature.detector_version,
        "detector_config_fingerprint": signature.detector_config_fingerprint,
        "status": signature.status,
        "source_analytics_fingerprint": signature.source_analytics_fingerprint,
        "payload_fingerprint": signature.payload_fingerprint,
        "normalized_fingerprint": signature.normalized_fingerprint,
        "point_count": signature.point_count,
    }


async def load_current_successful_assessment(
    session: AsyncSession,
    *,
    trip_id: UUID,
    settings: Settings,
) -> CurrentFraudAssessment:
    """Rebuild the exact persisted assessment inputs and verify every watermark."""
    analytics = await session.scalar(
        select(TripAnalytics).where(TripAnalytics.trip_session_id == trip_id)
    )
    if analytics is None or analytics.formula_version != settings.route_analytics_formula_version:
        return CurrentFraudAssessment(None, analytics, [], False)

    assessment = await session.scalar(
        select(FraudAssessment).where(FraudAssessment.trip_session_id == trip_id)
    )
    flags = await load_current_detection_flags(session, analytics=analytics)
    signature = await session.scalar(
        select(RouteReplaySignature).where(RouteReplaySignature.trip_session_id == trip_id)
    )
    if signature is None:
        return CurrentFraudAssessment(assessment, analytics, flags, False)

    try:
        analytics_fingerprint = analytics_output_fingerprint(analytics)
    except Exception:
        return CurrentFraudAssessment(assessment, analytics, flags, False)
    replay_source_current = signature.source_analytics_fingerprint == analytics_fingerprint
    replay_current = (
        signature.trip_analytics_id == analytics.id
        and signature.detector_version == settings.route_replay_detector_version
        and signature.detector_config_fingerprint == route_replay_config_fingerprint(settings)
        and signature.status in SUCCESSFUL_ROUTE_REPLAY_STATUSES
        and replay_source_current
    )
    flags_updated_through = max(
        (flag.updated_at for flag in flags if flag.updated_at is not None),
        default=None,
    )
    current = bool(
        replay_current
        and assessment is not None
        and assessment.trip_analytics_id == analytics.id
        and assessment.flags_count == len(flags)
        and assessment.flags_updated_through == flags_updated_through
        and is_current_successful_assessment(
            assessment,
            analytics=analytics,
            flags=flags,
            settings=settings,
            upstream_facts={"route_replay": route_replay_assessment_facts(signature)},
        )
    )
    return CurrentFraudAssessment(assessment, analytics, flags, current)


async def _locked_assessment(
    session: AsyncSession,
    *,
    trip_id: UUID,
) -> FraudAssessment | None:
    return await session.scalar(
        select(FraudAssessment)
        .where(FraudAssessment.trip_session_id == trip_id)
        .with_for_update()
    )


async def load_current_detection_flags(
    session: AsyncSession,
    *,
    analytics: TripAnalytics,
) -> list[FraudFlag]:
    result = await session.execute(
        select(FraudFlag)
        .where(
            FraudFlag.trip_analytics_id == analytics.id,
            FraudFlag.detected_at == analytics.computed_at,
        )
        .order_by(FraudFlag.flag_type, FraudFlag.severity, FraudFlag.id)
    )
    return list(result.scalars().all())


async def assess_trip_fraud(
    session: AsyncSession,
    *,
    analytics: TripAnalytics,
    flags: Sequence[FraudFlag],
    settings: Settings,
    now: datetime,
    upstream_facts: Mapping[str, object] | None = None,
    upstream_error_code: str | None = None,
) -> FraudAssessmentResult:
    assessment = await _locked_assessment(session, trip_id=analytics.trip_session_id)
    flags_updated_through = max(
        (flag.updated_at for flag in flags if flag.updated_at is not None),
        default=None,
    )
    try:
        source_fingerprint, inputs_fingerprint = assessment_inputs_fingerprint(
            analytics=analytics,
            flags=flags,
            formula_version=settings.fraud_assessment_formula_version,
            upstream_facts=upstream_facts,
        )
    except Exception:
        source_fingerprint = UNAVAILABLE_FINGERPRINT
        inputs_fingerprint = UNAVAILABLE_FINGERPRINT
        evaluation_failed = True
    else:
        evaluation_failed = upstream_error_code is not None
        if (
            not evaluation_failed
            and assessment is not None
            and assessment.status in SUCCESSFUL_FRAUD_ASSESSMENT_STATUSES
            and assessment.formula_version == settings.fraud_assessment_formula_version
            and assessment.source_analytics_fingerprint == source_fingerprint
            and assessment.inputs_fingerprint == inputs_fingerprint
            and assessment.flags_count == len(flags)
            and assessment.flags_updated_through == flags_updated_through
        ):
            return FraudAssessmentResult(assessment=assessment, changed=False)

    if assessment is None:
        candidate = FraudAssessment(
            trip_session_id=analytics.trip_session_id,
            trip_analytics_id=analytics.id,
            status=FraudAssessmentStatus.PENDING.value,
            formula_version=settings.fraud_assessment_formula_version,
            source_analytics_fingerprint=source_fingerprint,
            inputs_fingerprint=inputs_fingerprint,
            flags_count=len(flags),
            flags_updated_through=flags_updated_through,
        )
        try:
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
        except IntegrityError as exc:
            if not is_expected_uniqueness_conflict(exc, constraints=ASSESSMENT_ROW_CONSTRAINTS):
                raise
            assessment = await _locked_assessment(
                session,
                trip_id=analytics.trip_session_id,
            )
            if assessment is None:
                raise
        else:
            assessment = candidate

    assessment.trip_analytics_id = analytics.id
    assessment.status = FraudAssessmentStatus.PENDING.value
    assessment.formula_version = settings.fraud_assessment_formula_version
    assessment.source_analytics_fingerprint = source_fingerprint
    assessment.inputs_fingerprint = inputs_fingerprint
    assessment.flags_count = len(flags)
    assessment.flags_updated_through = flags_updated_through
    assessment.error_code = None
    assessment.assessed_at = None
    await session.flush()

    if evaluation_failed:
        assessment.status = FraudAssessmentStatus.ERROR.value
        assessment.error_code = upstream_error_code or ASSESSMENT_ERROR_CODE
        assessment.assessed_at = now
    else:
        assessment.status = (
            FraudAssessmentStatus.FLAGGED.value
            if flags
            else FraudAssessmentStatus.CLEAN.value
        )
        assessment.error_code = None
        assessment.assessed_at = now

    await session.flush()
    await session.refresh(assessment)
    return FraudAssessmentResult(assessment=assessment, changed=True)

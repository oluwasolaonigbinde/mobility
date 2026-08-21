from collections.abc import Sequence
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
from app.models.trip_analytics import FraudFlag, TripAnalytics
from app.services.provenance import stable_source_fingerprint
from app.services.trip_analytics import analytics_output_fingerprint

ASSESSMENT_ROW_CONSTRAINTS = frozenset({"uq_fraud_assessments_trip_session_id"})
ASSESSMENT_ERROR_CODE = "assessment_evaluation_failed"
UNAVAILABLE_FINGERPRINT = "0" * 64


@dataclass(frozen=True)
class FraudAssessmentResult:
    assessment: FraudAssessment
    changed: bool


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
) -> tuple[str, str]:
    source_fingerprint = analytics_output_fingerprint(analytics)
    return source_fingerprint, stable_source_fingerprint(
        {
            "formula_version": formula_version,
            "source_analytics_fingerprint": source_fingerprint,
            "flags": current_flag_facts(flags),
        }
    )


def is_current_successful_assessment(
    assessment: FraudAssessment | None,
    *,
    analytics: TripAnalytics,
    flags: Sequence[FraudFlag],
    settings: Settings,
) -> bool:
    if assessment is None or assessment.status not in SUCCESSFUL_FRAUD_ASSESSMENT_STATUSES:
        return False
    source_fingerprint, inputs_fingerprint = assessment_inputs_fingerprint(
        analytics=analytics,
        flags=flags,
        formula_version=settings.fraud_assessment_formula_version,
    )
    return (
        assessment.formula_version == settings.fraud_assessment_formula_version
        and assessment.source_analytics_fingerprint == source_fingerprint
        and assessment.inputs_fingerprint == inputs_fingerprint
    )


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
        )
    except Exception:
        source_fingerprint = UNAVAILABLE_FINGERPRINT
        inputs_fingerprint = UNAVAILABLE_FINGERPRINT
        evaluation_failed = True
    else:
        evaluation_failed = False
        if (
            assessment is not None
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
        assessment.error_code = ASSESSMENT_ERROR_CODE
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

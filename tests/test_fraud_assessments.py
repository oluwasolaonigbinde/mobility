import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_trip_analytics,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import select

from app.models.driver import DriverOnboardingStatus
from app.models.fraud_assessment import FraudAssessment, FraudAssessmentStatus
from app.models.trip import TripSessionStatus
from app.models.trip_analytics import FraudFlag
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.services import fraud_assessments
from app.services.fraud_assessments import assess_trip_fraud, is_current_successful_assessment

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def build_graph(db_sessionmaker, tag: str) -> SimpleNamespace:
    admin = create_test_user(db_sessionmaker, email=f"admin-{tag}@example.com")
    advertiser = create_test_user(
        db_sessionmaker,
        email=f"advertiser-{tag}@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        name=f"Org {tag}",
        owner_user_id=advertiser.id,
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    driver = create_test_user(
        db_sessionmaker,
        email=f"driver-{tag}@example.com",
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number=f"FA-{tag}",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
    )
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        trip_status=TripSessionStatus.SEALED,
        started_at=NOW,
        ended_at=NOW,
    )
    analytics = create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        computed_at=NOW,
    )
    return SimpleNamespace(
        analytics=analytics,
        assignment=assignment,
        campaign=campaign,
        driver=driver,
        profile=profile,
        trip=trip,
        vehicle=vehicle,
    )


def run_assessment(db_sessionmaker, *, analytics, flags, settings):
    async def run():
        async with db_sessionmaker() as session:
            attached_analytics = await session.get(type(analytics), analytics.id)
            attached_flags = [await session.get(FraudFlag, flag.id) for flag in flags]
            result = await assess_trip_fraud(
                session,
                analytics=attached_analytics,
                flags=attached_flags,
                settings=settings,
                now=NOW,
            )
            await session.commit()
            return result.assessment.id, result.changed

    return asyncio.run(run())


def fetch_assessment(db_sessionmaker, trip_id):
    async def fetch():
        async with db_sessionmaker() as session:
            return await session.scalar(
                select(FraudAssessment).where(FraudAssessment.trip_session_id == trip_id)
            )

    return asyncio.run(fetch())


def create_flag(db_sessionmaker, graph, *, flag_type="impossible_speed") -> FraudFlag:
    async def create():
        async with db_sessionmaker() as session:
            flag = FraudFlag(
                trip_session_id=graph.trip.id,
                trip_analytics_id=graph.analytics.id,
                assignment_id=graph.assignment.id,
                campaign_id=graph.campaign.id,
                driver_profile_id=graph.profile.id,
                vehicle_id=graph.vehicle.id,
                flag_type=flag_type,
                severity="high",
                status="open",
                description="Synthetic high-speed evidence.",
                evidence={"observed_mps": 90},
                detected_at=NOW,
            )
            session.add(flag)
            await session.commit()
            await session.refresh(flag)
            return flag

    return asyncio.run(create())


def test_clean_assessment_converges_to_one_current_row(db_sessionmaker, settings) -> None:
    graph = build_graph(db_sessionmaker, "clean")

    first_id, first_changed = run_assessment(
        db_sessionmaker,
        analytics=graph.analytics,
        flags=[],
        settings=settings,
    )
    second_id, second_changed = run_assessment(
        db_sessionmaker,
        analytics=graph.analytics,
        flags=[],
        settings=settings,
    )

    assessment = fetch_assessment(db_sessionmaker, graph.trip.id)
    assert first_changed is True
    assert second_changed is False
    assert first_id == second_id == assessment.id
    assert assessment.status == FraudAssessmentStatus.CLEAN.value
    assert assessment.error_code is None
    assert is_current_successful_assessment(
        assessment,
        analytics=graph.analytics,
        flags=[],
        settings=settings,
    )


def test_changed_flag_inputs_replace_clean_with_flagged(db_sessionmaker, settings) -> None:
    graph = build_graph(db_sessionmaker, "flagged")
    assessment_id, _ = run_assessment(
        db_sessionmaker,
        analytics=graph.analytics,
        flags=[],
        settings=settings,
    )
    flag = create_flag(db_sessionmaker, graph)

    updated_id, changed = run_assessment(
        db_sessionmaker,
        analytics=graph.analytics,
        flags=[flag],
        settings=settings,
    )

    assessment = fetch_assessment(db_sessionmaker, graph.trip.id)
    assert changed is True
    assert updated_id == assessment_id
    assert assessment.status == FraudAssessmentStatus.FLAGGED.value


def test_formula_version_change_replaces_current_assessment(db_sessionmaker, settings) -> None:
    graph = build_graph(db_sessionmaker, "version")
    assessment_id, _ = run_assessment(
        db_sessionmaker,
        analytics=graph.analytics,
        flags=[],
        settings=settings,
    )
    next_settings = settings.model_copy(
        update={"fraud_assessment_formula_version": "fraud_assessment_v2"}
    )

    updated_id, changed = run_assessment(
        db_sessionmaker,
        analytics=graph.analytics,
        flags=[],
        settings=next_settings,
    )

    assessment = fetch_assessment(db_sessionmaker, graph.trip.id)
    assert changed is True
    assert updated_id == assessment_id
    assert assessment.formula_version == "fraud_assessment_v2"
    assert not is_current_successful_assessment(
        assessment,
        analytics=graph.analytics,
        flags=[],
        settings=settings,
    )
    assert is_current_successful_assessment(
        assessment,
        analytics=graph.analytics,
        flags=[],
        settings=next_settings,
    )


def test_assessment_failure_persists_error_and_never_counts_as_success(
    db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    graph = build_graph(db_sessionmaker, "error")

    def fail_fingerprint(**_kwargs):
        raise RuntimeError("sensitive internal failure")

    monkeypatch.setattr(fraud_assessments, "assessment_inputs_fingerprint", fail_fingerprint)
    run_assessment(
        db_sessionmaker,
        analytics=graph.analytics,
        flags=[],
        settings=settings,
    )

    assessment = fetch_assessment(db_sessionmaker, graph.trip.id)
    assert assessment.status == FraudAssessmentStatus.ERROR.value
    assert assessment.error_code == "assessment_evaluation_failed"
    assert "sensitive" not in assessment.error_code
    assert not is_current_successful_assessment(
        assessment,
        analytics=graph.analytics,
        flags=[],
        settings=settings,
    )


def test_source_fingerprint_failure_persists_sanitized_error(
    db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    graph = build_graph(db_sessionmaker, "source-error")

    def fail_source(_analytics):
        raise RuntimeError("sensitive source failure")

    monkeypatch.setattr(fraud_assessments, "analytics_output_fingerprint", fail_source)
    run_assessment(
        db_sessionmaker,
        analytics=graph.analytics,
        flags=[],
        settings=settings,
    )

    assessment = fetch_assessment(db_sessionmaker, graph.trip.id)
    assert assessment.status == FraudAssessmentStatus.ERROR.value
    assert assessment.error_code == "assessment_evaluation_failed"
    assert assessment.source_analytics_fingerprint == "0" * 64
    assert "sensitive" not in assessment.error_code

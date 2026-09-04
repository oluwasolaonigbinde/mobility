import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_campaign_payout_revision,
    create_test_driver_profile,
    create_test_organization,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
)

from app.db.base import Base
from app.models.assignment_activity import AssignmentActivityFlag, AssignmentActivityFlagEvent
from app.models.billing import CampaignLiabilityReservation
from app.models.campaign_assignment import (
    CampaignActivationEvent,
    CampaignAssignmentStatus,
)
from app.models.contact import (
    DriverPhoneVersion,
    ManualDriverContactTask,
    PasswordResetAttempt,
    PasswordResetToken,
    PhoneVerificationChallenge,
    WhatsappConsent,
)
from app.models.data_subject_request import DataSubjectRequestType
from app.models.driver import DriverOnboardingStatus
from app.models.payout import AssignmentRuleBinding
from app.models.trip import TripEvidenceManifestEntry, TripSessionStatus
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.services.data_subject_inventory import (
    classified_subject_tables,
    explicitly_excluded_subject_tables,
    unclassified_subject_tables,
)
from app.services.data_subject_requests import (
    SUBJECT_LINK_REGISTRY,
    create_data_subject_request,
    data_subject_inventory,
    verify_data_subject_identity,
)


def test_every_subject_reachable_model_is_registered_or_explicitly_excluded() -> None:
    exclusions = explicitly_excluded_subject_tables()
    assert all(exclusions.values())
    assert all(rule.counted_tables and rule.subject_path for rule in SUBJECT_LINK_REGISTRY)
    assert (
        unclassified_subject_tables(
            Base.metadata,
            rules=SUBJECT_LINK_REGISTRY,
            exclusions=exclusions,
        )
        == set()
    )

    without_recovery = tuple(
        rule for rule in SUBJECT_LINK_REGISTRY if rule.data_class != "authentication_recovery"
    )
    assert {
        "password_reset_attempts",
        "password_reset_tokens",
    } <= unclassified_subject_tables(
        Base.metadata,
        rules=without_recovery,
        exclusions=exclusions,
    )


def test_subject_link_registry_counts_recovery_contact_and_trip_manifest_rows(
    postgis_db_sessionmaker,
) -> None:
    db_sessionmaker = postgis_db_sessionmaker
    admin = create_test_user(
        db_sessionmaker,
        email="subject-registry-admin@example.test",
        role=UserRole.ADMIN,
    )
    subject = create_test_user(
        db_sessionmaker,
        email="subject-registry-driver@example.test",
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=subject.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        owner_user_id=admin.id,
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )
    vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number="DSR-REGISTRY",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
    )
    revision = create_test_campaign_payout_revision(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
    )
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=subject.id,
        trip_status=TripSessionStatus.ENDED,
    )

    async def run() -> dict[str, int]:
        now = datetime.now(UTC)
        async with db_sessionmaker() as session:
            attempt = PasswordResetAttempt(
                email_digest="a" * 64,
                ip_digest="b" * 64,
                issued_user_id=subject.id,
                requested_at=now,
            )
            phone = DriverPhoneVersion(
                driver_profile_id=profile.id,
                version=1,
                phone_fingerprint="c" * 64,
                masked_phone="***1234",
                recorded_by_user_id=admin.id,
                recorded_at=now,
            )
            session.add_all([attempt, phone])
            await session.flush()
            activation = CampaignActivationEvent(
                assignment_id=assignment.id,
                actor_user_id=admin.id,
                event_type="activated",
                previous_status="accepted",
                new_status="active",
                occurred_at=now,
                event_metadata={},
            )
            activity = AssignmentActivityFlag(
                assignment_id=assignment.id,
                campaign_id=campaign.id,
                driver_profile_id=profile.id,
                vehicle_id=vehicle.id,
                flag_type="inactivity",
                status="open",
                window_start=now - timedelta(hours=1),
                window_end=now,
                observed_seconds=0,
                first_detected_at=now,
                last_evaluated_at=now,
                current_evidence={},
            )
            binding = AssignmentRuleBinding(
                assignment_id=assignment.id,
                revision_id=revision.id,
                hourly_rate_naira=Decimal("1000"),
                premium_hourly_rate_naira=Decimal("1500"),
                daily_payable_hours_cap=Decimal("8"),
                currency="NGN",
                eligibility_params={},
                formula_version="payout_v3",
                premium_zone_ids=[],
                premium_zone_geometry_hash="a" * 64,
                premium_zone_geometry_wkts=[],
                exclusion_zone_ids=[],
                exclusion_zone_geometry_hash="b" * 64,
                exclusion_zone_geometry_wkts=[],
                stationary_policy_marker="synthetic-test",
                bound_at=now,
            )
            session.add_all([activation, activity, binding])
            await session.flush()
            session.add_all(
                [
                    AssignmentActivityFlagEvent(
                        flag_id=activity.id,
                        assignment_id=assignment.id,
                        sequence_number=1,
                        event_type="opened",
                        occurred_at=now,
                        observed_seconds=0,
                        evidence={},
                    ),
                    CampaignLiabilityReservation(
                        campaign_id=campaign.id,
                        assignment_id=assignment.id,
                        assignment_rule_binding_id=binding.id,
                        status="pending_funding",
                        covered_vehicle_days=1,
                        hourly_rate=Decimal("1000"),
                        daily_hours_cap=Decimal("8"),
                        requested_amount=Decimal("8000"),
                        requested_at=now,
                        formula_version="payout_v3",
                    ),
                ]
            )
            token = PasswordResetToken(
                attempt_id=attempt.id,
                user_id=subject.id,
                token_hash="d" * 64,
                session_version=1,
                created_at=now,
                expires_at=now + timedelta(hours=1),
            )
            challenge = PhoneVerificationChallenge(
                phone_version_id=phone.id,
                code_hash="e" * 64,
                status="pending_operator",
                max_attempts=3,
                created_at=now,
                expires_at=now + timedelta(hours=1),
            )
            consent = WhatsappConsent(
                driver_profile_id=profile.id,
                phone_version_id=phone.id,
                version=1,
                purpose="driver operations",
                notice_version="synthetic-v1",
                granted_by_user_id=subject.id,
                granted_at=now,
            )
            session.add_all([token, challenge, consent])
            await session.flush()
            session.add_all(
                [
                    ManualDriverContactTask(
                        driver_profile_id=profile.id,
                        phone_version_id=phone.id,
                        consent_id=consent.id,
                        event_key="registry-test",
                        purpose="driver operations",
                        status="open",
                        created_at=now,
                    ),
                    TripEvidenceManifestEntry(
                        trip_session_id=trip.id,
                        batch_sequence=0,
                        idempotency_key="registry-manifest",
                        payload_hash_version=2,
                        payload_hash="f" * 64,
                        submitted_count=1,
                    ),
                ]
            )
            case = await create_data_subject_request(
                session,
                actor_user_id=admin.id,
                subject_user_id=subject.id,
                request_type=DataSubjectRequestType.ACCESS,
                client_request_id=uuid4(),
                requested_at=now,
            )
            await verify_data_subject_identity(
                session,
                actor_user_id=admin.id,
                request_id=case.id,
            )
            await session.flush()
            result = await data_subject_inventory(
                session,
                actor_user_id=admin.id,
                request_id=case.id,
            )
            return result["database"]

    counts = asyncio.run(run())
    assert counts["authentication_recovery"] == 2
    assert counts["driver_contact_and_consent"] == 4
    assert counts["trip_evidence_manifest"] == 1
    assert counts["assignment_subject_authority"] == 6
    assert classified_subject_tables() == {
        "password_reset_attempts",
        "password_reset_tokens",
        "driver_phone_versions",
        "phone_verification_challenges",
        "whatsapp_consents",
        "manual_driver_contact_tasks",
        "trip_evidence_manifest_entries",
        "campaign_assignments",
        "campaign_activation_events",
        "assignment_activity_flags",
        "assignment_activity_flag_events",
        "assignment_rule_bindings",
        "campaign_liability_reservations",
    }

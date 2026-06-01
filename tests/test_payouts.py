import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_impression_estimate,
    create_test_organization,
    create_test_payout_rule,
    create_test_traffic_density_profile,
    create_test_trip_analytics,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
    fetch_audit_events,
    fetch_earnings_ledger_entries,
    fetch_payout_calculations,
)
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status as http_status

from app.core.errors import AppError
from app.models.campaign import CampaignStatus
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.impression import ImpressionEstimate
from app.models.payout import CampaignPayoutRule
from app.models.trip import TripSessionStatus
from app.models.trip_analytics import FraudFlag, FraudFlagStatus, TripAnalytics
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.schemas.payouts import CampaignPayoutRuleUpdate
from app.services.payouts import update_campaign_payout_rule

PASSWORD = "long-secure-password"
BASE_TIME = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
PAST = datetime(2020, 1, 1, tzinfo=UTC)
FUTURE = datetime(2099, 1, 1, tzinfo=UTC)


def admin_headers(client):
    return auth_headers(client, "admin@example.com", PASSWORD)


def payout_rule_payload(**overrides):
    payload = {
        "formula_version": "payout_v1",
        "status": "active",
        "currency": "ngn",
        "base_rate_per_km": "100.00",
        "base_rate_per_active_hour": "500.00",
        "target_zone_bonus_rate_per_km": "50.00",
        "bonus_zone_bonus_rate_per_km": "75.00",
        "estimated_impression_rate_per_1000": "25.00",
        "min_payout_per_trip": "0.00",
        "max_payout_per_trip": "10000.00",
        "low_fraud_multiplier": "0.90",
        "medium_fraud_multiplier": "0.70",
        "high_fraud_multiplier": "0.25",
        "metadata": {"source": "test"},
    }
    payload.update(overrides)
    return payload


def create_payout_graph(
    db_sessionmaker,
    *,
    admin,
    advertiser_email: str,
    driver_email: str,
    plate_number: str,
    campaign=None,
    organization_id=None,
    advertiser=None,
    trip_status: TripSessionStatus = TripSessionStatus.ENDED,
    analytics_status: str = "computed",
    estimate_status: str = "estimated",
    quality_score=Decimal("0.8000"),
    distance_m=Decimal("8500.00"),
    active_tracking_seconds: int = 1800,
    target_zone_distance_m=Decimal("2000.00"),
    bonus_zone_distance_m=Decimal("1000.00"),
    estimated_impressions=Decimal("1200.00"),
):
    if advertiser is None:
        advertiser = create_test_user(
            db_sessionmaker,
            email=advertiser_email,
            password=PASSWORD,
            role=UserRole.ADVERTISER,
        )
    if campaign is None:
        if organization_id is None:
            organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
            organization_id = organization.id
        campaign = create_test_campaign(
            db_sessionmaker,
            organization_id=organization_id,
            created_by_user_id=advertiser.id,
            campaign_status=CampaignStatus.ACTIVE,
            start_at=PAST,
            end_at=FUTURE,
        )
    driver = create_test_user(
        db_sessionmaker,
        email=driver_email,
        password=PASSWORD,
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
        plate_number=plate_number,
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
        activated_at=BASE_TIME,
    )
    ended_at = BASE_TIME + timedelta(minutes=30) if trip_status == TripSessionStatus.ENDED else None
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        trip_status=trip_status,
        started_at=BASE_TIME,
        ended_at=ended_at,
    )
    analytics = create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        status=analytics_status,
        started_at=BASE_TIME,
        ended_at=ended_at,
        first_ping_at=BASE_TIME,
        last_ping_at=ended_at,
        distance_m=distance_m,
        active_tracking_seconds=active_tracking_seconds,
        target_zone_distance_m=target_zone_distance_m,
        bonus_zone_distance_m=bonus_zone_distance_m,
        quality_score=quality_score,
    )
    density_profile = create_test_traffic_density_profile(
        db_sessionmaker,
        name=f"Traffic {plate_number}",
        is_default=False,
    )
    estimate = create_test_impression_estimate(
        db_sessionmaker,
        trip_session_id=trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        traffic_density_profile_id=density_profile.id,
        status=estimate_status,
        estimated_impressions=estimated_impressions,
    )
    return advertiser, driver, campaign, profile, vehicle, assignment, trip, analytics, estimate


def add_fraud_flag(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    trip,
    analytics,
    severity: str,
    flag_type: str,
    flag_status: str = FraudFlagStatus.OPEN.value,
) -> None:
    async def create() -> None:
        async with db_sessionmaker() as session:
            session.add(
                FraudFlag(
                    trip_session_id=trip.id,
                    trip_analytics_id=analytics.id,
                    assignment_id=trip.assignment_id,
                    campaign_id=trip.campaign_id,
                    driver_profile_id=trip.driver_profile_id,
                    vehicle_id=trip.vehicle_id,
                    flag_type=flag_type,
                    severity=severity,
                    status=flag_status,
                    description=f"{severity} test flag",
                    evidence={},
                    detected_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(create())


def delete_trip_sources(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    trip_id,
    delete_analytics: bool,
    delete_estimate: bool,
) -> None:
    async def delete_rows() -> None:
        async with db_sessionmaker() as session:
            if delete_estimate:
                await session.execute(
                    delete(ImpressionEstimate).where(ImpressionEstimate.trip_session_id == trip_id)
                )
            if delete_analytics:
                await session.execute(
                    delete(TripAnalytics).where(TripAnalytics.trip_session_id == trip_id)
                )
            await session.commit()

    asyncio.run(delete_rows())


def update_impression_estimate_campaign(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    estimate_id,
    campaign_id,
) -> None:
    async def update_row() -> None:
        async with db_sessionmaker() as session:
            await session.execute(
                update(ImpressionEstimate)
                .where(ImpressionEstimate.id == estimate_id)
                .values(campaign_id=campaign_id)
            )
            await session.commit()

    asyncio.run(update_row())


def test_admin_can_manage_campaign_payout_rules_with_supersession_and_audit(
    db_client,
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
    )
    headers = admin_headers(db_client)

    first = db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/payout-rules",
        headers=headers,
        json=payout_rule_payload(),
    )
    second = db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/payout-rules",
        headers=headers,
        json=payout_rule_payload(base_rate_per_km="120.00", metadata={"source": "new"}),
    )
    first_read = db_client.get(
        f"/api/v1/admin/campaigns/{campaign.id}/payout-rules/{first.json()['id']}",
        headers=headers,
    )
    update = db_client.patch(
        f"/api/v1/admin/campaigns/{campaign.id}/payout-rules/{first.json()['id']}",
        headers=headers,
        json={"status": "active", "currency": "usd", "metadata": {"reactivated": True}},
    )
    list_response = db_client.get(
        f"/api/v1/admin/campaigns/{campaign.id}/payout-rules?limit=10&offset=0",
        headers=headers,
    )
    second_read = db_client.get(
        f"/api/v1/admin/campaigns/{campaign.id}/payout-rules/{second.json()['id']}",
        headers=headers,
    )

    assert first.status_code == http_status.HTTP_201_CREATED
    assert first.json()["currency"] == "NGN"
    assert first.json()["base_rate_per_km"] == "100.00"
    assert first.json()["metadata"] == {"source": "test"}
    assert second.status_code == http_status.HTTP_201_CREATED
    assert first_read.json()["status"] == "inactive"
    assert update.status_code == http_status.HTTP_200_OK
    assert update.json()["status"] == "active"
    assert update.json()["currency"] == "USD"
    assert update.json()["metadata"] == {"reactivated": True}
    assert list_response.status_code == http_status.HTTP_200_OK
    assert list_response.json()["total"] == 2
    assert second_read.json()["status"] == "inactive"
    assert [event.action for event in fetch_audit_events(db_sessionmaker)] == [
        "admin.campaign_payout_rule.created",
        "admin.campaign_payout_rule.created",
        "admin.campaign_payout_rule.updated",
    ]
    assert first.json()["created_by_user_id"] == str(admin.id)


def test_payout_rule_patch_rejects_explicit_null_required_fields_and_allows_clearable_max(
    db_client,
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    rule = create_test_payout_rule(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        max_payout_per_trip=Decimal("1000.00"),
    )
    headers = admin_headers(db_client)

    required_fields = [
        "status",
        "currency",
        "base_rate_per_km",
        "base_rate_per_active_hour",
        "target_zone_bonus_rate_per_km",
        "bonus_zone_bonus_rate_per_km",
        "estimated_impression_rate_per_1000",
        "min_payout_per_trip",
        "low_fraud_multiplier",
        "medium_fraud_multiplier",
        "high_fraud_multiplier",
    ]
    for field in required_fields:
        response = db_client.patch(
            f"/api/v1/admin/campaigns/{campaign.id}/payout-rules/{rule.id}",
            headers=headers,
            json={field: None},
        )
        assert response.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    clear_max = db_client.patch(
        f"/api/v1/admin/campaigns/{campaign.id}/payout-rules/{rule.id}",
        headers=headers,
        json={"max_payout_per_trip": None},
    )

    assert clear_max.status_code == http_status.HTTP_200_OK
    assert clear_max.json()["max_payout_per_trip"] is None


def test_payout_rule_update_service_rejects_constructed_null_required_field(
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    rule = create_test_payout_rule(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        currency="NGN",
    )

    async def update_rule() -> None:
        async with db_sessionmaker() as session:
            payload = CampaignPayoutRuleUpdate.model_construct(
                currency=None,
                _fields_set={"currency"},
            )
            with pytest.raises(AppError) as exc_info:
                await update_campaign_payout_rule(
                    session,
                    campaign_id=campaign.id,
                    rule_id=rule.id,
                    updated_by_user_id=admin.id,
                    payload=payload,
                )
            persisted = await session.get(CampaignPayoutRule, rule.id)

        assert exc_info.value.code == "INVALID_PAYOUT_RULE"
        assert persisted is not None
        assert persisted.currency == "NGN"

    asyncio.run(update_rule())


def test_payout_rule_validation_and_role_boundaries(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    driver = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    headers = admin_headers(db_client)

    invalid_payloads = [
        payout_rule_payload(status="archived"),
        payout_rule_payload(currency="NAIRA"),
        payout_rule_payload(base_rate_per_km="-1"),
        payout_rule_payload(target_zone_bonus_rate_per_km="-1"),
        payout_rule_payload(estimated_impression_rate_per_1000="-1"),
        payout_rule_payload(low_fraud_multiplier="1.1"),
        payout_rule_payload(min_payout_per_trip="100", max_payout_per_trip="99"),
        payout_rule_payload(metadata=[]),
    ]
    for payload in invalid_payloads:
        response = db_client.post(
            f"/api/v1/admin/campaigns/{campaign.id}/payout-rules",
            headers=headers,
            json=payload,
        )
        assert response.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    driver_headers = auth_headers(db_client, driver.email, PASSWORD)
    for denied_headers in [advertiser_headers, driver_headers]:
        assert (
            db_client.post(
                f"/api/v1/admin/campaigns/{campaign.id}/payout-rules",
                headers=denied_headers,
                json=payout_rule_payload(),
            ).status_code
            == http_status.HTTP_403_FORBIDDEN
        )
        assert (
            db_client.get(
                f"/api/v1/admin/campaigns/{campaign.id}/payout-rules",
                headers=denied_headers,
            ).status_code
            == http_status.HTTP_403_FORBIDDEN
        )
    assert (
        db_client.post(
            f"/api/v1/admin/campaigns/{campaign.id}/payout-rules",
            json=payout_rule_payload(),
        ).status_code
        == http_status.HTTP_401_UNAUTHORIZED
    )


def test_admin_calculate_payout_formula_is_idempotent_and_creates_one_ledger_entry(
    db_client,
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    _, _, campaign, profile, vehicle, assignment, trip, analytics, estimate = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-calc@example.com",
        driver_email="driver-calc@example.com",
        plate_number="PAY-123",
    )
    rule = create_test_payout_rule(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        base_rate_per_km=Decimal("100.00"),
        base_rate_per_active_hour=Decimal("500.00"),
        target_zone_bonus_rate_per_km=Decimal("50.00"),
        bonus_zone_bonus_rate_per_km=Decimal("75.00"),
        estimated_impression_rate_per_1000=Decimal("25.00"),
    )

    first = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={"metadata": {"run": 1}},
    )
    second = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={"payout_rule_id": str(rule.id), "metadata": {"run": 2}},
    )
    listed = db_client.get(
        f"/api/v1/admin/payout-calculations?campaign_id={campaign.id}&status=calculated",
        headers=admin_headers(db_client),
    )

    assert first.status_code == http_status.HTTP_200_OK
    data = first.json()
    assert data["status"] == "calculated"
    assert data["formula_version"] == "payout_v1"
    assert data["distance_component"] == "850.00"
    assert data["active_time_component"] == "250.00"
    assert data["target_zone_bonus_component"] == "100.00"
    assert data["bonus_zone_bonus_component"] == "75.00"
    assert data["impression_component"] == "30.00"
    assert data["gross_payout"] == "1305.00"
    assert data["quality_multiplier"] == "0.8000"
    assert data["fraud_multiplier"] == "1.0000"
    assert data["final_payout"] == "1044.00"
    assert data["ledger_entry"]["status"] == "pending"
    assert data["ledger_entry"]["amount"] == "1044.00"
    assert data["metadata"]["request_metadata"] == {"run": 1}
    assert data["metadata"]["inputs"]["distance_km"] == "8.50"
    assert data["trip_analytics_id"] == str(analytics.id)
    assert data["impression_estimate_id"] == str(estimate.id)
    assert data["payout_rule_id"] == str(rule.id)
    assert data["assignment_id"] == str(assignment.id)
    assert data["campaign_id"] == str(campaign.id)
    assert data["driver_profile_id"] == str(profile.id)
    assert data["vehicle_id"] == str(vehicle.id)
    assert second.status_code == http_status.HTTP_200_OK
    assert second.json()["id"] == data["id"]
    assert second.json()["ledger_entry"]["id"] == data["ledger_entry"]["id"]
    assert listed.status_code == http_status.HTTP_200_OK
    assert listed.json()["total"] == 1
    assert len(fetch_payout_calculations(db_sessionmaker)) == 1
    assert len(fetch_earnings_ledger_entries(db_sessionmaker)) == 1
    assert [event.action for event in fetch_audit_events(db_sessionmaker)] == [
        "admin.payout_calculation.created"
    ]


def test_calculate_payout_without_explicit_rule_returns_existing_after_rule_supersession(
    db_client,
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    _, _, campaign, _, _, _, trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-superseded-calc@example.com",
        driver_email="driver-superseded-calc@example.com",
        plate_number="SUP-1",
    )
    old_rule = create_test_payout_rule(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        base_rate_per_km=Decimal("100.00"),
        base_rate_per_active_hour=Decimal("500.00"),
        target_zone_bonus_rate_per_km=Decimal("50.00"),
        bonus_zone_bonus_rate_per_km=Decimal("75.00"),
        estimated_impression_rate_per_1000=Decimal("25.00"),
    )
    headers = admin_headers(db_client)

    first = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/calculate-payout",
        headers=headers,
        json={},
    )
    replacement_rule = db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/payout-rules",
        headers=headers,
        json=payout_rule_payload(base_rate_per_km="250.00"),
    )
    repeated_without_rule = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/calculate-payout",
        headers=headers,
        json={},
    )
    explicit_old_rule = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/calculate-payout",
        headers=headers,
        json={"payout_rule_id": str(old_rule.id)},
    )

    assert first.status_code == http_status.HTTP_200_OK
    assert replacement_rule.status_code == http_status.HTTP_201_CREATED
    assert repeated_without_rule.status_code == http_status.HTTP_200_OK
    assert repeated_without_rule.json()["id"] == first.json()["id"]
    assert repeated_without_rule.json()["payout_rule_id"] == str(old_rule.id)
    assert repeated_without_rule.json()["ledger_entry"]["id"] == first.json()["ledger_entry"]["id"]
    assert explicit_old_rule.status_code == http_status.HTTP_400_BAD_REQUEST
    assert explicit_old_rule.json()["error"]["code"] == "PAYOUT_RULE_INACTIVE"
    assert len(fetch_payout_calculations(db_sessionmaker)) == 1
    assert len(fetch_earnings_ledger_entries(db_sessionmaker)) == 1


def test_fraud_flags_caps_and_floor_are_applied_deterministically(
    db_client,
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    cases = [
        ("high", "impossible_speed", "0.2500", "261.00"),
        ("medium", "poor_accuracy", "0.7000", "730.80"),
        ("low", "route_looping", "0.9000", "939.60"),
    ]
    for index, (severity, flag_type, multiplier, expected) in enumerate(cases):
        _, _, campaign, _, _, _, trip, analytics, _ = create_payout_graph(
            db_sessionmaker,
            admin=admin,
            advertiser_email=f"adv-fraud-{index}@example.com",
            driver_email=f"driver-fraud-{index}@example.com",
            plate_number=f"FRD-{index}",
        )
        create_test_payout_rule(
            db_sessionmaker,
            campaign_id=campaign.id,
            created_by_user_id=admin.id,
            base_rate_per_km=Decimal("100.00"),
            base_rate_per_active_hour=Decimal("500.00"),
            target_zone_bonus_rate_per_km=Decimal("50.00"),
            bonus_zone_bonus_rate_per_km=Decimal("75.00"),
            estimated_impression_rate_per_1000=Decimal("25.00"),
        )
        add_fraud_flag(
            db_sessionmaker,
            trip=trip,
            analytics=analytics,
            severity=severity,
            flag_type=flag_type,
        )

        response = db_client.post(
            f"/api/v1/admin/trips/{trip.id}/calculate-payout",
            headers=admin_headers(db_client),
            json={},
        )

        assert response.status_code == http_status.HTTP_200_OK
        assert response.json()["fraud_multiplier"] == multiplier
        assert response.json()["final_payout"] == expected

    _, _, capped_campaign, _, _, _, capped_trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-cap@example.com",
        driver_email="driver-cap@example.com",
        plate_number="CAP-1",
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=capped_campaign.id,
        created_by_user_id=admin.id,
        base_rate_per_km=Decimal("100.00"),
        base_rate_per_active_hour=Decimal("500.00"),
        target_zone_bonus_rate_per_km=Decimal("50.00"),
        bonus_zone_bonus_rate_per_km=Decimal("75.00"),
        estimated_impression_rate_per_1000=Decimal("25.00"),
        max_payout_per_trip=Decimal("500.00"),
    )
    capped = db_client.post(
        f"/api/v1/admin/trips/{capped_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )

    _, _, floored_campaign, _, _, _, floored_trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-floor@example.com",
        driver_email="driver-floor@example.com",
        plate_number="FLR-1",
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=floored_campaign.id,
        created_by_user_id=admin.id,
        base_rate_per_km=Decimal("1.00"),
        min_payout_per_trip=Decimal("20.00"),
    )
    floored = db_client.post(
        f"/api/v1/admin/trips/{floored_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )

    _, _, zero_campaign, _, _, _, zero_trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-zero@example.com",
        driver_email="driver-zero@example.com",
        plate_number="ZER-1",
        distance_m=Decimal("0.00"),
        active_tracking_seconds=0,
        target_zone_distance_m=Decimal("0.00"),
        bonus_zone_distance_m=Decimal("0.00"),
        estimated_impressions=Decimal("0.00"),
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=zero_campaign.id,
        created_by_user_id=admin.id,
        min_payout_per_trip=Decimal("20.00"),
    )
    zero = db_client.post(
        f"/api/v1/admin/trips/{zero_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )

    assert capped.json()["final_payout"] == "500.00"
    assert capped.json()["cap_adjustment"] == "-544.00"
    assert floored.json()["gross_payout"] == "8.50"
    assert floored.json()["final_payout"] == "20.00"
    assert zero.json()["gross_payout"] == "0.00"
    assert zero.json()["final_payout"] == "0.00"
    assert zero.json()["ledger_entry"] is None


def test_fraud_flags_ignore_closed_statuses_and_use_highest_open_severity(
    db_client,
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    _, _, closed_campaign, _, _, _, closed_trip, closed_analytics, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-fraud-closed@example.com",
        driver_email="driver-fraud-closed@example.com",
        plate_number="FCL-1",
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=closed_campaign.id,
        created_by_user_id=admin.id,
        base_rate_per_km=Decimal("100.00"),
        base_rate_per_active_hour=Decimal("500.00"),
        target_zone_bonus_rate_per_km=Decimal("50.00"),
        bonus_zone_bonus_rate_per_km=Decimal("75.00"),
        estimated_impression_rate_per_1000=Decimal("25.00"),
    )
    add_fraud_flag(
        db_sessionmaker,
        trip=closed_trip,
        analytics=closed_analytics,
        severity="high",
        flag_type="impossible_speed",
        flag_status=FraudFlagStatus.DISMISSED.value,
    )
    add_fraud_flag(
        db_sessionmaker,
        trip=closed_trip,
        analytics=closed_analytics,
        severity="medium",
        flag_type="poor_accuracy",
        flag_status=FraudFlagStatus.ACKNOWLEDGED.value,
    )

    closed_response = db_client.post(
        f"/api/v1/admin/trips/{closed_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )

    _, _, mixed_campaign, _, _, _, mixed_trip, mixed_analytics, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-fraud-mixed@example.com",
        driver_email="driver-fraud-mixed@example.com",
        plate_number="FMX-1",
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=mixed_campaign.id,
        created_by_user_id=admin.id,
        base_rate_per_km=Decimal("100.00"),
        base_rate_per_active_hour=Decimal("500.00"),
        target_zone_bonus_rate_per_km=Decimal("50.00"),
        bonus_zone_bonus_rate_per_km=Decimal("75.00"),
        estimated_impression_rate_per_1000=Decimal("25.00"),
    )
    for severity, flag_type in [
        ("low", "route_looping"),
        ("medium", "poor_accuracy"),
        ("high", "impossible_speed"),
    ]:
        add_fraud_flag(
            db_sessionmaker,
            trip=mixed_trip,
            analytics=mixed_analytics,
            severity=severity,
            flag_type=flag_type,
        )

    mixed_response = db_client.post(
        f"/api/v1/admin/trips/{mixed_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )

    assert closed_response.status_code == http_status.HTTP_200_OK
    assert closed_response.json()["fraud_multiplier"] == "1.0000"
    assert closed_response.json()["final_payout"] == "1044.00"
    assert closed_response.json()["metadata"]["fraud_flag_counts"] == {
        "low": 0,
        "medium": 0,
        "high": 0,
    }
    assert mixed_response.status_code == http_status.HTTP_200_OK
    assert mixed_response.json()["fraud_multiplier"] == "0.2500"
    assert mixed_response.json()["final_payout"] == "261.00"


def test_payout_calculation_statuses_and_expected_errors(db_client, db_sessionmaker) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    _, _, missing_rule_campaign, _, _, _, missing_rule_trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-missing-rule@example.com",
        driver_email="driver-missing-rule@example.com",
        plate_number="MRL-1",
    )
    missing_rule = db_client.post(
        f"/api/v1/admin/trips/{missing_rule_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )
    inactive_rule = create_test_payout_rule(
        db_sessionmaker,
        campaign_id=missing_rule_campaign.id,
        created_by_user_id=admin.id,
        status="inactive",
    )
    inactive = db_client.post(
        f"/api/v1/admin/trips/{missing_rule_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={"payout_rule_id": str(inactive_rule.id)},
    )

    _, _, active_campaign, _, _, _, active_trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-active-trip@example.com",
        driver_email="driver-active-trip@example.com",
        plate_number="ACT-1",
        trip_status=TripSessionStatus.ACTIVE,
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=active_campaign.id,
        created_by_user_id=admin.id,
    )
    active = db_client.post(
        f"/api/v1/admin/trips/{active_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )

    _, _, insufficient_campaign, _, _, _, insufficient_trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-insufficient@example.com",
        driver_email="driver-insufficient@example.com",
        plate_number="INS-1",
        analytics_status="insufficient_data",
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=insufficient_campaign.id,
        created_by_user_id=admin.id,
    )
    insufficient = db_client.post(
        f"/api/v1/admin/trips/{insufficient_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )

    _, _, blocked_campaign, _, _, _, blocked_trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-blocked@example.com",
        driver_email="driver-blocked@example.com",
        plate_number="BLK-1",
        estimate_status="excluded",
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=blocked_campaign.id,
        created_by_user_id=admin.id,
    )
    blocked = db_client.post(
        f"/api/v1/admin/trips/{blocked_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )

    _, _, estimate_insufficient_campaign, _, _, _, estimate_insufficient_trip, _, _ = (
        create_payout_graph(
            db_sessionmaker,
            admin=admin,
            advertiser_email="adv-estimate-insufficient@example.com",
            driver_email="driver-estimate-insufficient@example.com",
            plate_number="EIN-1",
            estimate_status="insufficient_data",
        )
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=estimate_insufficient_campaign.id,
        created_by_user_id=admin.id,
    )
    estimate_insufficient = db_client.post(
        f"/api/v1/admin/trips/{estimate_insufficient_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )

    _, _, analytics_blocked_campaign, _, _, _, analytics_blocked_trip, _, _ = (
        create_payout_graph(
            db_sessionmaker,
            admin=admin,
            advertiser_email="adv-analytics-blocked@example.com",
            driver_email="driver-analytics-blocked@example.com",
            plate_number="ABL-1",
            analytics_status="blocked",
        )
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=analytics_blocked_campaign.id,
        created_by_user_id=admin.id,
    )
    analytics_blocked = db_client.post(
        f"/api/v1/admin/trips/{analytics_blocked_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )

    assert missing_rule.status_code == http_status.HTTP_404_NOT_FOUND
    assert missing_rule.json()["error"]["code"] == "PAYOUT_RULE_NOT_FOUND"
    assert inactive.status_code == http_status.HTTP_400_BAD_REQUEST
    assert inactive.json()["error"]["code"] == "PAYOUT_RULE_INACTIVE"
    assert active.status_code == http_status.HTTP_400_BAD_REQUEST
    assert active.json()["error"]["code"] == "TRIP_NOT_ENDED"
    assert insufficient.json()["status"] == "insufficient_data"
    assert insufficient.json()["final_payout"] == "0.00"
    assert insufficient.json()["ledger_entry"] is None
    assert blocked.json()["status"] == "blocked"
    assert blocked.json()["final_payout"] == "0.00"
    assert blocked.json()["ledger_entry"] is None
    assert estimate_insufficient.json()["status"] == "insufficient_data"
    assert estimate_insufficient.json()["final_payout"] == "0.00"
    assert estimate_insufficient.json()["ledger_entry"] is None
    assert analytics_blocked.json()["status"] == "blocked"
    assert analytics_blocked.json()["final_payout"] == "0.00"
    assert analytics_blocked.json()["ledger_entry"] is None


def test_payout_calculation_reports_missing_analytics_and_estimate(
    db_client,
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    _, _, analytics_campaign, _, _, _, analytics_trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-missing-analytics@example.com",
        driver_email="driver-missing-analytics@example.com",
        plate_number="MNA-1",
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=analytics_campaign.id,
        created_by_user_id=admin.id,
    )
    delete_trip_sources(
        db_sessionmaker,
        trip_id=analytics_trip.id,
        delete_analytics=True,
        delete_estimate=True,
    )

    missing_analytics = db_client.post(
        f"/api/v1/admin/trips/{analytics_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )

    _, _, estimate_campaign, _, _, _, estimate_trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-missing-estimate@example.com",
        driver_email="driver-missing-estimate@example.com",
        plate_number="MNE-1",
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=estimate_campaign.id,
        created_by_user_id=admin.id,
    )
    delete_trip_sources(
        db_sessionmaker,
        trip_id=estimate_trip.id,
        delete_analytics=False,
        delete_estimate=True,
    )

    missing_estimate = db_client.post(
        f"/api/v1/admin/trips/{estimate_trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )

    assert missing_analytics.status_code == http_status.HTTP_404_NOT_FOUND
    assert missing_analytics.json()["error"]["code"] == "ANALYTICS_NOT_FOUND"
    assert missing_estimate.status_code == http_status.HTTP_404_NOT_FOUND
    assert missing_estimate.json()["error"]["code"] == "IMPRESSION_ESTIMATE_NOT_FOUND"


def test_payout_calculation_rejects_inconsistent_trip_analytics_estimate_sources(
    db_client,
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser, _, campaign, _, _, _, trip, _, estimate = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-source-mismatch@example.com",
        driver_email="driver-source-mismatch@example.com",
        plate_number="SRC-1",
    )
    other_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=campaign.organization_id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
    )
    update_impression_estimate_campaign(
        db_sessionmaker,
        estimate_id=estimate.id,
        campaign_id=other_campaign.id,
    )

    response = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/calculate-payout",
        headers=admin_headers(db_client),
        json={},
    )

    assert response.status_code == http_status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "PAYOUT_SOURCE_MISMATCH"
    assert response.json()["error"]["details"]["mismatches"][0]["field"] == "campaign_id"
    assert len(fetch_payout_calculations(db_sessionmaker)) == 0
    assert len(fetch_earnings_ledger_entries(db_sessionmaker)) == 0


def test_admin_payout_calculation_endpoints_enforce_rbac_and_filter_driver_profile(
    db_client,
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser, driver, campaign, profile, _, _, trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-admin-payout-rbac@example.com",
        driver_email="driver-admin-payout-rbac@example.com",
        plate_number="ARB-1",
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
    )
    _, _, other_campaign, _, _, _, other_trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-admin-payout-rbac-2@example.com",
        driver_email="driver-admin-payout-rbac-2@example.com",
        plate_number="ARB-2",
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=other_campaign.id,
        created_by_user_id=admin.id,
    )
    headers = admin_headers(db_client)

    first = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/calculate-payout",
        headers=headers,
        json={},
    )
    second = db_client.post(
        f"/api/v1/admin/trips/{other_trip.id}/calculate-payout",
        headers=headers,
        json={},
    )
    filtered = db_client.get(
        f"/api/v1/admin/payout-calculations?driver_profile_id={profile.id}",
        headers=headers,
    )
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    driver_headers = auth_headers(db_client, driver.email, PASSWORD)

    assert first.status_code == http_status.HTTP_200_OK
    assert second.status_code == http_status.HTTP_200_OK
    assert filtered.status_code == http_status.HTTP_200_OK
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == first.json()["id"]
    for denied_headers in [advertiser_headers, driver_headers]:
        assert (
            db_client.post(
                f"/api/v1/admin/trips/{trip.id}/calculate-payout",
                headers=denied_headers,
                json={},
            ).status_code
            == http_status.HTTP_403_FORBIDDEN
        )
        assert (
            db_client.get(
                "/api/v1/admin/payout-calculations",
                headers=denied_headers,
            ).status_code
            == http_status.HTTP_403_FORBIDDEN
        )
    assert (
        db_client.post(f"/api/v1/admin/trips/{trip.id}/calculate-payout", json={}).status_code
        == http_status.HTTP_401_UNAUTHORIZED
    )
    assert (
        db_client.get("/api/v1/admin/payout-calculations").status_code
        == http_status.HTTP_401_UNAUTHORIZED
    )


def test_driver_earnings_are_scoped_and_append_only(db_client, db_sessionmaker) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser, driver, campaign, _, _, _, trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-driver-ledger@example.com",
        driver_email="driver-ledger@example.com",
        plate_number="LED-1",
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        base_rate_per_km=Decimal("100.00"),
        base_rate_per_active_hour=Decimal("500.00"),
        target_zone_bonus_rate_per_km=Decimal("50.00"),
        bonus_zone_bonus_rate_per_km=Decimal("75.00"),
        estimated_impression_rate_per_1000=Decimal("25.00"),
    )
    assert (
        db_client.post(
            f"/api/v1/admin/trips/{trip.id}/calculate-payout",
            headers=admin_headers(db_client),
            json={},
        ).status_code
        == http_status.HTTP_200_OK
    )

    driver_headers = auth_headers(db_client, driver.email, PASSWORD)
    summary = db_client.get("/api/v1/driver/earnings/summary", headers=driver_headers)
    ledger = db_client.get(
        "/api/v1/driver/earnings/ledger?status=pending&entry_type=trip_payout&currency=ngn",
        headers=driver_headers,
    )
    other_driver = create_test_user(
        db_sessionmaker,
        email="other-driver-ledger@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    create_test_driver_profile(
        db_sessionmaker,
        user_id=other_driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    other_summary = db_client.get(
        "/api/v1/driver/earnings/summary",
        headers=auth_headers(db_client, other_driver.email, PASSWORD),
    )
    other_ledger = db_client.get(
        "/api/v1/driver/earnings/ledger",
        headers=auth_headers(db_client, other_driver.email, PASSWORD),
    )

    assert summary.status_code == http_status.HTTP_200_OK
    assert summary.json()["totals_by_currency"] == [
        {
            "currency": "NGN",
            "pending_amount": "1044.00",
            "available_amount": "0.00",
            "voided_amount": "0.00",
            "lifetime_earned_amount": "1044.00",
            "ledger_entry_count": 1,
        }
    ]
    assert ledger.status_code == http_status.HTTP_200_OK
    assert ledger.json()["total"] == 1
    assert "driver_user_id" not in ledger.json()["items"][0]
    assert other_summary.json()["totals_by_currency"][0]["pending_amount"] == "0.00"
    assert other_ledger.json()["total"] == 0
    assert db_client.patch(
        "/api/v1/driver/earnings/ledger/not-a-real-id",
        headers=driver_headers,
    ).status_code in {
        http_status.HTTP_404_NOT_FOUND,
        http_status.HTTP_405_METHOD_NOT_ALLOWED,
    }
    assert (
        db_client.get("/api/v1/driver/earnings/summary", headers=admin_headers(db_client))
        .status_code
        == http_status.HTTP_403_FORBIDDEN
    )
    assert (
        db_client.get("/api/v1/driver/earnings/ledger", headers=admin_headers(db_client))
        .status_code
        == http_status.HTTP_403_FORBIDDEN
    )
    assert (
        db_client.get(
            "/api/v1/driver/earnings/summary",
            headers=auth_headers(db_client, advertiser.email, PASSWORD),
        ).status_code
        == http_status.HTTP_403_FORBIDDEN
    )
    assert (
        db_client.get(
            "/api/v1/driver/earnings/ledger",
            headers=auth_headers(db_client, advertiser.email, PASSWORD),
        ).status_code
        == http_status.HTTP_403_FORBIDDEN
    )
    assert db_client.get("/api/v1/driver/earnings/summary").status_code == (
        http_status.HTTP_401_UNAUTHORIZED
    )
    assert db_client.get("/api/v1/driver/earnings/ledger").status_code == (
        http_status.HTTP_401_UNAUTHORIZED
    )


def test_advertiser_cost_summary_is_scoped_and_aggregates_stored_calculations(
    db_client,
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser, driver, campaign, _, _, _, trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-cost@example.com",
        driver_email="driver-cost@example.com",
        plate_number="CST-1",
    )
    rule = create_test_payout_rule(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        base_rate_per_km=Decimal("100.00"),
        base_rate_per_active_hour=Decimal("500.00"),
        target_zone_bonus_rate_per_km=Decimal("50.00"),
        bonus_zone_bonus_rate_per_km=Decimal("75.00"),
        estimated_impression_rate_per_1000=Decimal("25.00"),
    )
    assert (
        db_client.post(
            f"/api/v1/admin/trips/{trip.id}/calculate-payout",
            headers=admin_headers(db_client),
            json={},
        ).status_code
        == http_status.HTTP_200_OK
    )
    _, _, _, _, _, _, blocked_trip, _, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="adv-cost@example.com",
        driver_email="driver-cost-blocked@example.com",
        plate_number="CST-2",
        advertiser=advertiser,
        campaign=campaign,
        estimate_status="excluded",
    )
    assert (
        db_client.post(
            f"/api/v1/admin/trips/{blocked_trip.id}/calculate-payout",
            headers=admin_headers(db_client),
            json={"payout_rule_id": str(rule.id)},
        ).status_code
        == http_status.HTTP_200_OK
    )

    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    own = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/cost-summary",
        headers=advertiser_headers,
    )
    empty_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=campaign.organization_id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
    )
    empty = db_client.get(
        f"/api/v1/advertiser/campaigns/{empty_campaign.id}/cost-summary",
        headers=advertiser_headers,
    )
    naive_datetime = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/cost-summary"
        "?start_at=2026-01-01T00:00:00",
        headers=advertiser_headers,
    )
    other_advertiser = create_test_user(
        db_sessionmaker,
        email="other-adv-cost@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    create_test_organization(db_sessionmaker, name="Other Org", owner_user_id=other_advertiser.id)
    other = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/cost-summary",
        headers=auth_headers(db_client, other_advertiser.email, PASSWORD),
    )

    assert own.status_code == http_status.HTTP_200_OK
    own_data = own.json()
    assert own_data["formula_version"] == "payout_v1"
    assert own_data["totals_by_currency"] == [
        {
            "currency": "NGN",
            "final_payout_total": "1044.00",
            "gross_payout_total": "1305.00",
            "calculated_trip_count": 1,
            "blocked_trip_count": 1,
            "insufficient_data_trip_count": 0,
            "ledger_entry_count": 1,
        }
    ]
    assert "driver_profile_id" not in str(own_data)
    assert "trip_session_id" not in str(own_data)
    assert empty.status_code == http_status.HTTP_200_OK
    assert empty.json()["totals_by_currency"] == [
        {
            "currency": "NGN",
            "final_payout_total": "0.00",
            "gross_payout_total": "0.00",
            "calculated_trip_count": 0,
            "blocked_trip_count": 0,
            "insufficient_data_trip_count": 0,
            "ledger_entry_count": 0,
        }
    ]
    assert naive_datetime.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert naive_datetime.json()["error"]["code"] == "VALIDATION_ERROR"
    assert other.status_code == http_status.HTTP_404_NOT_FOUND
    assert (
        db_client.get(
            f"/api/v1/advertiser/campaigns/{campaign.id}/cost-summary",
            headers=admin_headers(db_client),
        ).status_code
        == http_status.HTTP_403_FORBIDDEN
    )
    assert (
        db_client.get(
            f"/api/v1/advertiser/campaigns/{campaign.id}/cost-summary",
            headers=auth_headers(db_client, driver.email, PASSWORD),
        ).status_code
        == http_status.HTTP_403_FORBIDDEN
    )
    assert (
        db_client.get(f"/api/v1/advertiser/campaigns/{campaign.id}/cost-summary").status_code
        == http_status.HTTP_401_UNAUTHORIZED
    )

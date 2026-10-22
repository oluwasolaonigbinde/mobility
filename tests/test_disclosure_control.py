from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from conftest import (
    auth_headers,
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
)
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from starlette import status
from test_heatmaps import BBOX, PASSWORD, RECORDED_AT, add_ping_batch, create_heatmap_graph

from app.core.config import Settings
from app.core.errors import AppError
from app.db.integrity import integrity_constraint_name
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.disclosure import DisclosureQueryDecision
from app.models.driver import DriverOnboardingStatus
from app.models.impression import ImpressionEstimate
from app.models.organization import (
    AdvertiserOrganization,
    MembershipStatus,
    OrganizationMembership,
    OrganizationStatus,
)
from app.models.payout import PayoutCalculation
from app.models.trip import TripSessionStatus
from app.models.trip_analytics import FraudFlag, TripAnalytics
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.services import (
    audience,
    audience_delivery,
    heatmaps,
    impressions,
    reports,
)
from app.services.disclosure import (
    DISCLOSURE_ROUTE_INVENTORY,
    DisclosureQuery,
    frozen_manifest_meets_disclosure_floor,
    record_heatmap_disclosure,
    require_governed_advertiser_output,
    trip_cohort_meets_disclosure_floor,
)


def live_test_settings(**overrides) -> Settings:
    values = {
        "environment": "test",
        "privacy_legal_approval_reference": "synthetic-legal-approval-v1",
    }
    values.update(overrides)
    return Settings(**values)


def query(*, route_id: str = "advertiser.campaign.heatmap", metric: str = "ping_count"):
    return DisclosureQuery(
        route_id=route_id,
        principal_id=uuid4(),
        tenant_id=uuid4(),
        campaign_id=uuid4(),
        start_at=datetime(2026, 8, 1, tzinfo=UTC),
        end_at=datetime(2026, 8, 8, tzinfo=UTC),
        filters={"bbox": [7.3, 9.0, 7.4, 9.1], "resolution_m": 500, "metric": metric},
    )


def test_frozen_measurement_manifest_releases_on_distinct_cars_alone() -> None:
    """D107: lopsided contributions no longer suppress; only the car count does."""
    first_vehicle, second_vehicle, third_vehicle = uuid4(), uuid4(), uuid4()

    def analytics(vehicle_id, trip_id, distance):
        return {
            "trip_session_id": str(trip_id),
            "vehicle_id": str(vehicle_id),
            "started_at": "2026-08-01T10:00:00+00:00",
            "distance_m": distance,
            "target_zone_distance_m": distance,
            "bonus_zone_distance_m": 0,
            "exclusion_zone_distance_m": 0,
            "active_tracking_seconds": 60,
            "quality_score": 1,
        }

    first_trip, second_trip = uuid4(), uuid4()
    manifest = {
        "sources": {
            "trip_analytics": [
                {**analytics(first_vehicle, first_trip, 1000), "status": "computed"},
                {**analytics(second_vehicle, second_trip, 1), "status": "computed"},
            ],
            "impression_estimates": [
                {
                    "trip_session_id": str(first_trip),
                    "status": "estimated",
                    "estimated_impressions": 1000,
                    "confidence_score": 1,
                },
                {
                    "trip_session_id": str(second_trip),
                    "status": "estimated",
                    "estimated_impressions": 1,
                    "confidence_score": 1,
                },
            ],
            "payout_calculations": [],
        }
    }
    settings = live_test_settings()
    assert frozen_manifest_meets_disclosure_floor(manifest, settings=settings) is False
    third = {**analytics(third_vehicle, uuid4(), 1), "status": "computed"}
    manifest["sources"]["trip_analytics"].append(third)
    assert frozen_manifest_meets_disclosure_floor(manifest, settings=settings) is True
    # Three cars overall cannot release a day with only one car.
    third["started_at"] = "2026-08-02T10:00:00+00:00"
    assert frozen_manifest_meets_disclosure_floor(manifest, settings=settings) is False
    third["started_at"] = "2026-08-01T10:00:00+00:00"
    # A blocked trip never counts as a car.
    manifest["sources"]["trip_analytics"][1]["status"] = "blocked"
    assert frozen_manifest_meets_disclosure_floor(manifest, settings=settings) is False
    manifest["sources"]["trip_analytics"][1]["status"] = "computed"
    # Every released estimate must belong to a trip in the same cohort.
    manifest["sources"]["impression_estimates"].append(
        {
            "trip_session_id": str(uuid4()),
            "status": "estimated",
            "estimated_impressions": 1,
            "confidence_score": 1,
        }
    )
    assert frozen_manifest_meets_disclosure_floor(manifest, settings=settings) is False


def test_frozen_report_authority_rechecks_cars_per_reported_day() -> None:
    first_vehicle, second_vehicle = str(uuid4()), str(uuid4())
    authority = {
        "schema_version": "frozen-report-disclosure-v1",
        "route_id": "advertiser.campaign.report",
        "passed": True,
        "vehicle_count": 2,
        "trip_count": 2,
        "day_count": 1,
        "report_snapshot_sha256": "a" * 64,
        "contributions": {
            "daily:trip_count:2026-08-01": {first_vehicle: "1"},
            "measurement:analytics:active_tracking_seconds": {
                first_vehicle: "1000",
                second_vehicle: "1",
            },
        },
    }
    settings = live_test_settings(privacy_min_vehicles_per_cell=2)
    manifest = {"disclosure_authority": authority}
    assert frozen_manifest_meets_disclosure_floor(manifest, settings=settings) is False
    # A lopsided measurement share no longer matters (D107); each day needs enough cars.
    authority["contributions"]["daily:trip_count:2026-08-01"][second_vehicle] = "1"
    assert frozen_manifest_meets_disclosure_floor(manifest, settings=settings) is True
    authority["vehicle_count"] = 1
    assert frozen_manifest_meets_disclosure_floor(manifest, settings=settings) is False


def test_route_inventory_covers_every_current_output_at_the_service_boundary() -> None:
    expected = {
        "advertiser.dashboard.summary",
        "advertiser.campaign.summary",
        "advertiser.campaign.daily_metrics",
        "advertiser.campaign.trips",
        "advertiser.campaign.report",
        "advertiser.campaign.performance",
        "advertiser.campaign.impressions_summary",
        "advertiser.campaign.heatmap",
        "admin.heatmap",
        "advertiser.audience.recommendations",
        "admin.audience.recommendations",
        "advertiser.audience.export",
        "admin.audience.activation",
        "advertiser.campaign.zone_insights",
        "admin.campaign.zone_insights",
    }
    assert DISCLOSURE_ROUTE_INVENTORY == expected

    sources = "\n".join(
        [
            inspect.getsource(reports.advertiser_dashboard_summary),
            inspect.getsource(reports.advertiser_campaign_summary),
            inspect.getsource(reports.daily_metrics_for_campaign),
            inspect.getsource(reports.advertiser_campaign_trips),
            inspect.getsource(reports.advertiser_campaign_report),
            inspect.getsource(reports.build_measurement_report_snapshot),
            inspect.getsource(impressions.advertiser_campaign_impression_summary),
            inspect.getsource(heatmaps.advertiser_campaign_heatmap),
            inspect.getsource(heatmaps.admin_heatmap),
            inspect.getsource(audience_delivery.recommendations_for_link),
            inspect.getsource(audience_delivery._recommendations_for_segment),
            inspect.getsource(audience_delivery.export_exposure_segment),
            inspect.getsource(audience_delivery.activate_exposure_segment),
            inspect.getsource(audience.high_exposure_zone_insights),
        ]
    )
    for route_id in expected:
        assert route_id in sources

    heatmap_source = inspect.getsource(heatmaps.aggregation_sql)
    for boundary in ("privacy_min_vehicles_per_cell", "count(DISTINCT vehicle_id)"):
        assert boundary in heatmap_source
    # D107: distinct cars are the only area rule; no trip, day or share conditions remain.
    for removed in ("privacy_min_trips", "privacy_min_days", "contributor_share"):
        assert removed not in heatmap_source


def test_governed_output_resolves_the_single_active_company_membership(
    db_sessionmaker,
) -> None:
    """D29 supersedes the former newest-membership rule: a login has one company."""
    advertiser = create_test_user(
        db_sessionmaker,
        email="disclosure-multi-membership@example.com",
        role=UserRole.ADVERTISER,
    )
    active_org, _ = create_test_organization(
        db_sessionmaker,
        name="Active disclosure org",
        owner_user_id=advertiser.id,
    )
    create_test_organization(
        db_sessionmaker,
        name="Former disclosure org",
        owner_user_id=advertiser.id,
        membership_status=MembershipStatus.DISABLED,
    )

    async def run() -> None:
        async with db_sessionmaker() as session:
            selected = await require_governed_advertiser_output(
                session,
                settings=live_test_settings(),
                route_id="advertiser.dashboard.summary",
                user_id=advertiser.id,
            )
            assert selected == active_org.id

        async with db_sessionmaker() as session:
            former = await session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.user_id == advertiser.id,
                    OrganizationMembership.status == MembershipStatus.DISABLED,
                )
            )
            assert former is not None
            former.status = MembershipStatus.ACTIVE
            with pytest.raises(IntegrityError) as conflict:
                await session.commit()
            assert (
                integrity_constraint_name(conflict.value)
                == "uq_organization_memberships_user_active"
            )

    asyncio.run(run())


def test_advertiser_reads_keep_the_disclosure_authorized_tenant(
    db_client,
    db_sessionmaker,
) -> None:
    _admin, advertiser, authorized_org, campaign, *_ = create_heatmap_graph(
        db_sessionmaker,
        advertiser_email="disclosure-authority@example.com",
        driver_email="disclosure-authority-driver@example.com",
        plate_number="DISC-AUTH",
    )
    unauthorized_org, unauthorized_membership = create_test_organization(
        db_sessionmaker,
        name="Unauthorized newer organization",
        owner_user_id=advertiser.id,
        membership_status=MembershipStatus.INVITED,
    )
    assert unauthorized_membership is not None
    headers = auth_headers(db_client, advertiser.email, PASSWORD)

    def assert_authorized_reads() -> None:
        responses = {
            "dashboard": db_client.get("/api/v1/advertiser/dashboard/summary", headers=headers),
            "summary": db_client.get(
                f"/api/v1/advertiser/campaigns/{campaign.id}/summary", headers=headers
            ),
            "daily_metrics": db_client.get(
                f"/api/v1/advertiser/campaigns/{campaign.id}/daily-metrics", headers=headers
            ),
            "trips": db_client.get(
                f"/api/v1/advertiser/campaigns/{campaign.id}/trips", headers=headers
            ),
            "report": db_client.get(
                f"/api/v1/advertiser/campaigns/{campaign.id}/report", headers=headers
            ),
            "score": db_client.get(
                f"/api/v1/advertiser/campaigns/{campaign.id}/zone-insights", headers=headers
            ),
            "impressions": db_client.get(
                f"/api/v1/advertiser/campaigns/{campaign.id}/impressions/summary",
                headers=headers,
            ),
            "heatmap": db_client.get(
                f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
                headers=headers,
                params={"bbox": BBOX},
            ),
        }
        assert {
            name: (response.status_code, response.text)
            for name, response in responses.items()
            if response.status_code != status.HTTP_200_OK
            and not (
                name == "heatmap"
                and response.status_code == status.HTTP_400_BAD_REQUEST
                and response.json()["error"]["code"] == "POSTGIS_REQUIRED"
            )
        } == {}
        # D90: before the first run the report shows current coarse totals.
        assert responses["report"].json()["campaign_id"] == str(campaign.id)
        assert responses["dashboard"].json()["organization_id"] == str(authorized_org.id)
        assert responses["summary"].json()["campaign"]["id"] == str(campaign.id)
        for name in ("daily_metrics", "trips", "score", "impressions"):
            assert responses[name].json()["campaign_id"] == str(campaign.id)

    async def set_membership_authority(
        *,
        tied: bool,
        unauthorized_membership_status: MembershipStatus,
        unauthorized_organization_status: OrganizationStatus,
    ) -> None:
        async with db_sessionmaker() as session:
            memberships = list(
                await session.scalars(
                    select(OrganizationMembership).where(
                        OrganizationMembership.user_id == advertiser.id
                    )
                )
            )
            by_organization = {row.organization_id: row for row in memberships}
            authorized = by_organization[authorized_org.id]
            unauthorized = by_organization[unauthorized_org.id]
            authorized.created_at = datetime(2026, 1, 1, tzinfo=UTC)
            unauthorized.created_at = (
                authorized.created_at if tied else datetime(2026, 1, 2, tzinfo=UTC)
            )
            authorized.status = MembershipStatus.ACTIVE
            unauthorized.status = unauthorized_membership_status
            unauthorized_db = await session.get(AdvertiserOrganization, unauthorized_org.id)
            assert unauthorized_db is not None
            unauthorized_db.status = unauthorized_organization_status
            await session.commit()

    asyncio.run(
        set_membership_authority(
            tied=False,
            unauthorized_membership_status=MembershipStatus.INVITED,
            unauthorized_organization_status=OrganizationStatus.ACTIVE,
        )
    )
    assert_authorized_reads()

    asyncio.run(
        set_membership_authority(
            tied=True,
            unauthorized_membership_status=MembershipStatus.INVITED,
            unauthorized_organization_status=OrganizationStatus.ACTIVE,
        )
    )
    assert_authorized_reads()

    # D29: a second active membership is refused even when its company is disabled.
    with pytest.raises(IntegrityError) as conflict:
        asyncio.run(
            set_membership_authority(
                tied=False,
                unauthorized_membership_status=MembershipStatus.ACTIVE,
                unauthorized_organization_status=OrganizationStatus.DISABLED,
            )
        )
    assert integrity_constraint_name(conflict.value) == "uq_organization_memberships_user_active"
    assert_authorized_reads()


def test_history_replays_exact_query_and_records_overlapping_variant(
    db_sessionmaker,
) -> None:
    initial = query()
    overlapping = DisclosureQuery(
        **{
            **initial.__dict__,
            "route_id": "admin.heatmap",
            "principal_id": uuid4(),
            "filters": {**initial.filters, "metric": "distance_m"},
        }
    )

    async def run() -> tuple[int, set[str]]:
        async with db_sessionmaker() as session:
            await record_heatmap_disclosure(
                session,
                query=initial,
                settings=live_test_settings(),
                has_releasable_cells=True,
                result_hash="a" * 64,
            )
            await record_heatmap_disclosure(
                session,
                query=initial,
                settings=live_test_settings(),
                has_releasable_cells=True,
                result_hash="a" * 64,
            )
        async with db_sessionmaker() as session:
            await record_heatmap_disclosure(
                session,
                query=overlapping,
                settings=live_test_settings(),
                has_releasable_cells=True,
                result_hash="a" * 64,
            )

        async with db_sessionmaker() as session:
            count = await session.scalar(select(func.count()).select_from(DisclosureQueryDecision))
            decisions = set(
                (
                    await session.scalars(
                        select(DisclosureQueryDecision.decision).order_by(
                            DisclosureQueryDecision.created_at,
                            DisclosureQueryDecision.id,
                        )
                    )
                ).all()
            )
            return int(count or 0), decisions

    assert asyncio.run(run()) == (2, {"served"})


def test_minimum_floor_suppression_is_sticky_on_retry(db_sessionmaker) -> None:
    suppressed_query = query()

    async def run() -> int:
        for _ in range(2):
            async with db_sessionmaker() as session:
                with pytest.raises(AppError) as suppressed:
                    await record_heatmap_disclosure(
                        session,
                        query=suppressed_query,
                        settings=live_test_settings(),
                        has_releasable_cells=False,
                        result_hash="0" * 64,
                    )
                assert suppressed.value.details == {"reason": "minimum_cars"}
        async with db_sessionmaker() as session:
            return int(
                await session.scalar(select(func.count()).select_from(DisclosureQueryDecision)) or 0
            )

    assert asyncio.run(run()) == 1


def test_same_request_with_changed_result_is_not_treated_as_an_exact_retry(
    db_sessionmaker,
) -> None:
    disclosure_query = query()

    async def run() -> int:
        async with db_sessionmaker() as session:
            await record_heatmap_disclosure(
                session,
                query=disclosure_query,
                settings=live_test_settings(),
                has_releasable_cells=True,
                result_hash="a" * 64,
            )
        async with db_sessionmaker() as session:
            await record_heatmap_disclosure(
                session,
                query=disclosure_query,
                settings=live_test_settings(),
                has_releasable_cells=True,
                result_hash="b" * 64,
            )

        async with db_sessionmaker() as session:
            return int(
                await session.scalar(select(func.count()).select_from(DisclosureQueryDecision)) or 0
            )

    assert asyncio.run(run()) == 2


@pytest.mark.parametrize("parent_kind", ["organization", "global"])
@pytest.mark.parametrize("parent_first", [True, False])
def test_parent_and_child_scopes_record_views_in_both_orders(
    db_sessionmaker,
    parent_kind: str,
    parent_first: bool,
) -> None:
    child = query()
    parent = DisclosureQuery(
        **{
            **child.__dict__,
            "route_id": "admin.heatmap",
            "principal_id": uuid4(),
            "tenant_id": child.tenant_id if parent_kind == "organization" else None,
            "campaign_id": None,
        }
    )
    first, second = (parent, child) if parent_first else (child, parent)

    async def run() -> tuple[str, str]:
        async with db_sessionmaker() as session:
            await record_heatmap_disclosure(
                session,
                query=first,
                settings=live_test_settings(),
                has_releasable_cells=True,
                result_hash="a" * 64,
            )
        async with db_sessionmaker() as session:
            await record_heatmap_disclosure(
                session,
                query=second,
                settings=live_test_settings(),
                has_releasable_cells=True,
                result_hash="a" * 64,
            )
            return "served", "served"

    assert asyncio.run(run()) == ("served", "served")


@pytest.mark.parametrize("parent_kind", ["organization", "global"])
@pytest.mark.parametrize("parent_first", [True, False])
def test_parent_child_scope_overlap_serializes_concurrently(
    postgis_db_sessionmaker,
    parent_kind: str,
    parent_first: bool,
) -> None:
    child = query()
    parent = DisclosureQuery(
        **{
            **child.__dict__,
            "route_id": "admin.heatmap",
            "principal_id": uuid4(),
            "tenant_id": child.tenant_id if parent_kind == "organization" else None,
            "campaign_id": None,
        }
    )

    async def attempt(disclosure_query: DisclosureQuery) -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await record_heatmap_disclosure(
                    session,
                    query=disclosure_query,
                    settings=live_test_settings(),
                    has_releasable_cells=True,
                    result_hash="a" * 64,
                )
            except AppError:
                return "suppressed"
            return "served"

    async def run() -> list[str]:
        ordered = (parent, child) if parent_first else (child, parent)
        return sorted(await asyncio.gather(*(attempt(item) for item in ordered)))

    assert asyncio.run(run()) == ["served", "served"]


def test_expired_history_remains_recorded_when_overlapping_views_are_served(db_sessionmaker):
    initial = query()
    overlapping = DisclosureQuery(
        **{**initial.__dict__, "principal_id": uuid4(), "filters": {"metric": "distance_m"}}
    )

    async def run():
        async with db_sessionmaker() as session:
            await record_heatmap_disclosure(
                session,
                query=initial,
                settings=live_test_settings(),
                has_releasable_cells=True,
                result_hash="a" * 64,
            )
            first = await session.scalar(select(DisclosureQueryDecision))
            first.expires_at = datetime.now(UTC) - timedelta(days=1)
            await session.commit()
        async with db_sessionmaker() as session:
            await record_heatmap_disclosure(
                session,
                query=overlapping,
                settings=live_test_settings(),
                has_releasable_cells=True,
                result_hash="b" * 64,
            )

        async with db_sessionmaker() as session:
            decisions = list(await session.scalars(select(DisclosureQueryDecision)))
            assert len(decisions) == 2
            assert {row.decision for row in decisions} == {"served"}

    asyncio.run(run())


def test_concurrent_overlapping_views_are_both_recorded(
    postgis_db_sessionmaker,
) -> None:
    initial = query()
    variant = DisclosureQuery(
        **{**initial.__dict__, "filters": {**initial.filters, "bbox": [7.31, 9.0, 7.41, 9.1]}}
    )

    async def attempt(disclosure_query: DisclosureQuery) -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await record_heatmap_disclosure(
                    session,
                    query=disclosure_query,
                    settings=live_test_settings(),
                    has_releasable_cells=True,
                    result_hash="a" * 64,
                )
            except AppError as exc:
                assert exc.code == "DISCLOSURE_SUPPRESSED"
                return "suppressed"
            return "served"

    async def run() -> list[str]:
        return sorted(await asyncio.gather(attempt(initial), attempt(variant)))

    assert asyncio.run(run()) == ["served", "served"]


def test_heatmap_area_shows_at_exactly_the_minimum_distinct_cars_on_one_day(
    postgis_db_sessionmaker,
) -> None:
    admin, _, _, campaign, *_ = create_heatmap_graph(postgis_db_sessionmaker)
    driver = create_test_user(
        postgis_db_sessionmaker,
        email="disclosure-second-driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        postgis_db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    vehicle = create_test_vehicle(
        postgis_db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number="DISC-2",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
        activated_at=RECORDED_AT,
    )
    trip = create_test_trip_session(
        postgis_db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        trip_status=TripSessionStatus.ENDED,
        started_at=RECORDED_AT,
        ended_at=RECORDED_AT.replace(hour=11),
    )
    analytics = create_test_trip_analytics(
        postgis_db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_at=RECORDED_AT,
        ended_at=RECORDED_AT.replace(hour=11),
        first_ping_at=RECORDED_AT,
        last_ping_at=RECORDED_AT.replace(minute=5),
        distance_m=Decimal("1000.00"),
    )
    density = create_test_traffic_density_profile(
        postgis_db_sessionmaker,
        name="Disclosure threshold density",
    )
    create_test_impression_estimate(
        postgis_db_sessionmaker,
        trip_session_id=trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        traffic_density_profile_id=density.id,
        estimated_impressions=Decimal("200.00"),
    )
    add_ping_batch(
        postgis_db_sessionmaker,
        trip_id=trip.id,
        idempotency_key="disclosure-threshold-second",
        points=[
            (RECORDED_AT, 6.45, 3.39),
            (RECORDED_AT.replace(minute=5), 6.45, 3.39),
        ],
    )
    heatmap_query = heatmaps.parse_heatmap_query(
        bbox=BBOX,
        resolution_m=500,
        metric="estimated_impressions",
        start_at=None,
        end_at=None,
        settings=live_test_settings(),
    )

    async def feature_count(**settings_overrides) -> int:
        settings = live_test_settings(**settings_overrides)
        async with postgis_db_sessionmaker() as session:
            result = await heatmaps.build_heatmap(
                session,
                query=heatmap_query,
                settings=settings,
                campaign_id=campaign.id,
                organization_id=None,
                vehicle_type=None,
                metadata_campaign_id=campaign.id,
                metadata_organization_id=None,
            )
            return len(result.features)

    # D107: one trip each, one day, uneven impressions: the car count alone decides.
    exact = asyncio.run(feature_count(privacy_min_vehicles_per_cell=2))
    below_vehicle = asyncio.run(feature_count(privacy_min_vehicles_per_cell=3))

    assert (exact, below_vehicle) == (1, 0)


def test_trip_cohort_releases_uneven_metrics_once_enough_cars_drove(
    postgis_db_sessionmaker,
) -> None:
    admin, _, organization, campaign, _, _, _, first_trip, first_estimate = create_heatmap_graph(
        postgis_db_sessionmaker,
        advertiser_email="disclosure-report-cap-advertiser@example.com",
        driver_email="disclosure-report-cap-driver@example.com",
        plate_number="DISC-REPORT-1",
    )
    driver = create_test_user(
        postgis_db_sessionmaker,
        email="disclosure-report-cap-second@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        postgis_db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    vehicle = create_test_vehicle(
        postgis_db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number="DISC-REPORT-2",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
        activated_at=RECORDED_AT,
    )
    trip = create_test_trip_session(
        postgis_db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        trip_status=TripSessionStatus.ENDED,
        started_at=RECORDED_AT,
        ended_at=RECORDED_AT.replace(hour=11),
    )
    analytics = create_test_trip_analytics(
        postgis_db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_at=RECORDED_AT,
        ended_at=RECORDED_AT.replace(hour=11),
        first_ping_at=RECORDED_AT,
        last_ping_at=RECORDED_AT.replace(minute=5),
        distance_m=Decimal("1.00"),
    )
    density = create_test_traffic_density_profile(
        postgis_db_sessionmaker,
        name="Report contributor cap density",
    )
    estimate = create_test_impression_estimate(
        postgis_db_sessionmaker,
        trip_session_id=trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        traffic_density_profile_id=density.id,
        estimated_impressions=Decimal("1.00"),
    )
    settings = live_test_settings(privacy_min_vehicles_per_cell=2)
    payout_rule = create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
    )

    async def evaluate() -> tuple[bool, bool, bool, bool]:
        async with postgis_db_sessionmaker() as session:
            dominated = await trip_cohort_meets_disclosure_floor(
                session,
                tenant_id=organization.id,
                campaign_id=campaign.id,
                start_at=None,
                end_at=None,
                route_id="advertiser.campaign.trips",
                settings=settings,
            )
            analytics.distance_m = Decimal("1000.00")
            estimate.estimated_impressions = Decimal("200.00")
            await session.merge(analytics)
            await session.merge(estimate)
            await session.flush()
            first_analytics = await session.scalar(
                select(TripAnalytics).where(TripAnalytics.trip_session_id == first_trip.id)
            )
            assert first_analytics is not None
            first_payout = PayoutCalculation(
                trip_session_id=first_trip.id,
                trip_analytics_id=first_analytics.id,
                impression_estimate_id=first_estimate.id,
                payout_rule_id=payout_rule.id,
                assignment_id=first_trip.assignment_id,
                campaign_id=campaign.id,
                driver_profile_id=first_trip.driver_profile_id,
                vehicle_id=first_trip.vehicle_id,
                formula_version="payout_v4",
                eligible_seconds=0,
                excluded_seconds_by_reason={},
                inputs_fingerprint="synthetic-report-fixture",
                distance_m_by_day={},
                amount_by_day={},
                status="calculated",
                currency="NGN",
                gross_payout=Decimal("1000.00"),
                final_payout=Decimal("1000.00"),
                calculated_at=RECORDED_AT,
                payout_metadata={},
            )
            second_payout = PayoutCalculation(
                trip_session_id=trip.id,
                trip_analytics_id=analytics.id,
                impression_estimate_id=estimate.id,
                payout_rule_id=payout_rule.id,
                assignment_id=trip.assignment_id,
                campaign_id=campaign.id,
                driver_profile_id=trip.driver_profile_id,
                vehicle_id=trip.vehicle_id,
                formula_version="payout_v4",
                eligible_seconds=0,
                excluded_seconds_by_reason={},
                inputs_fingerprint="synthetic-report-fixture",
                distance_m_by_day={},
                amount_by_day={},
                status="calculated",
                currency="NGN",
                gross_payout=Decimal("1.00"),
                final_payout=Decimal("1.00"),
                calculated_at=RECORDED_AT,
                payout_metadata={},
            )
            session.add_all([first_payout, second_payout])
            await session.flush()
            cost_dominated = await trip_cohort_meets_disclosure_floor(
                session,
                tenant_id=organization.id,
                campaign_id=campaign.id,
                start_at=None,
                end_at=None,
                route_id="advertiser.campaign.trips",
                settings=settings,
            )
            second_payout.gross_payout = Decimal("1000.00")
            second_payout.final_payout = Decimal("1000.00")
            await session.flush()
            balanced = await trip_cohort_meets_disclosure_floor(
                session,
                tenant_id=organization.id,
                campaign_id=campaign.id,
                start_at=None,
                end_at=None,
                route_id="advertiser.campaign.trips",
                settings=settings,
            )
            session.add(
                FraudFlag(
                    trip_session_id=first_trip.id,
                    trip_analytics_id=first_analytics.id,
                    assignment_id=first_trip.assignment_id,
                    campaign_id=campaign.id,
                    driver_profile_id=first_trip.driver_profile_id,
                    vehicle_id=first_trip.vehicle_id,
                    flag_type="excessive_ping_gap",
                    severity="low",
                    status="open",
                    description="Synthetic daily authority boundary",
                    evidence={},
                    detected_at=RECORDED_AT - timedelta(days=30),
                )
            )
            await session.flush()
            daily_out_of_detection_window = await trip_cohort_meets_disclosure_floor(
                session,
                tenant_id=organization.id,
                campaign_id=campaign.id,
                start_at=RECORDED_AT - timedelta(minutes=1),
                end_at=RECORDED_AT.replace(hour=12),
                route_id="advertiser.campaign.daily_metrics",
                settings=settings,
            )
            return dominated, cost_dominated, balanced, daily_out_of_detection_window

    # D107: uneven distance, impressions, cost and one car's open fraud flag on the day
    # no longer suppress once enough distinct cars drove; the car count alone decides.
    assert asyncio.run(evaluate()) == (True, True, True, True)


def test_heatmap_releases_a_dominated_metric_once_enough_cars_drove_there(
    postgis_db_sessionmaker,
) -> None:
    admin, _, _, campaign, *_ = create_heatmap_graph(
        postgis_db_sessionmaker,
        advertiser_email="disclosure-cross-metric-advertiser@example.com",
        driver_email="disclosure-cross-metric-driver@example.com",
        plate_number="DISC-CROSS-1",
    )
    driver = create_test_user(
        postgis_db_sessionmaker,
        email="disclosure-cross-metric-second-driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        postgis_db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    vehicle = create_test_vehicle(
        postgis_db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number="DISC-CROSS-2",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
        activated_at=RECORDED_AT,
    )
    trip = create_test_trip_session(
        postgis_db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        trip_status=TripSessionStatus.ENDED,
        started_at=RECORDED_AT,
        ended_at=RECORDED_AT.replace(hour=11),
    )
    analytics = create_test_trip_analytics(
        postgis_db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_at=RECORDED_AT,
        ended_at=RECORDED_AT.replace(hour=11),
        first_ping_at=RECORDED_AT,
        last_ping_at=RECORDED_AT.replace(minute=5),
        distance_m=Decimal("1000.00"),
    )
    density = create_test_traffic_density_profile(
        postgis_db_sessionmaker,
        name="Cross-metric disclosure density",
    )
    create_test_impression_estimate(
        postgis_db_sessionmaker,
        trip_session_id=trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        traffic_density_profile_id=density.id,
        estimated_impressions=Decimal("10000.00"),
    )
    add_ping_batch(
        postgis_db_sessionmaker,
        trip_id=trip.id,
        idempotency_key="disclosure-cross-metric-second",
        points=[
            (RECORDED_AT, 6.45, 3.39),
            (RECORDED_AT.replace(minute=5), 6.45, 3.39),
        ],
    )
    query = heatmaps.parse_heatmap_query(
        bbox=BBOX,
        resolution_m=500,
        metric="ping_count",
        start_at=None,
        end_at=None,
        settings=live_test_settings(),
    )

    async def run() -> int:
        async with postgis_db_sessionmaker() as session:
            result = await heatmaps.build_heatmap(
                session,
                query=query,
                settings=live_test_settings(privacy_min_vehicles_per_cell=2),
                campaign_id=campaign.id,
                organization_id=None,
                vehicle_type=None,
                metadata_campaign_id=campaign.id,
                metadata_organization_id=None,
            )
            return len(result.features)

    # estimated_impressions is dominated by the second car, but two cars drove there (D107).
    assert asyncio.run(run()) == 1


@pytest.mark.parametrize("snapshot_first", [True, False])
@pytest.mark.parametrize("ledger_status", [None, "available", "paid", "reconciliation"])
def test_disclosure_snapshot_and_fraud_review_share_trip_lock_order(
    postgis_db_sessionmaker,
    snapshot_first,
    ledger_status,
):
    from sqlalchemy import text
    from test_fraud_assessments import create_flag
    from test_fraud_holds import build_review_graph
    from test_mny03a_earnings_release import create_ledger

    from app.models.payout import EarningsLedgerEntry
    from app.services.disclosure import lock_trip_disclosure_snapshot
    from app.services.fraud_holds import (
        fraud_hold_counts,
        lock_fraud_hold_scope,
        lock_fraud_reconciliation_gate,
        resolve_fraud_flag,
    )

    factory = postgis_db_sessionmaker
    graph = build_review_graph(factory, "disclosure-fraud-overlap")
    flag = create_flag(factory, graph)
    confirmed = ledger_status in {"available", "paid"}
    if confirmed:
        create_ledger(factory, graph, status=ledger_status, amount="125.50")
    outcome = "confirmed" if confirmed else "dismissed"

    async def run():
        async with factory() as setup:
            pass
            await setup.commit()
        started = asyncio.Event()
        follower_pid = None

        async def snapshot(session):
            await lock_trip_disclosure_snapshot(
                session, tenant_id=graph.campaign.organization_id, campaign_id=graph.campaign.id
            )

        async def resolve(session):
            await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome=outcome,
                resolution_note="Reviewed overlapping snapshot",
            )

        async def follower():
            nonlocal follower_pid
            async with factory() as session:
                follower_pid = await session.scalar(text("SELECT pg_backend_pid()"))
                started.set()
                if snapshot_first:
                    if ledger_status == "reconciliation":
                        await lock_fraud_reconciliation_gate(session, exclusive=True)
                    await resolve(session)
                else:
                    await snapshot(session)
                    counts = await fraud_hold_counts(session, graph.trip.id)
                    assert sum(counts.values()) == (1 if confirmed else 0)
                await session.commit()

        async with factory() as leader:
            if snapshot_first:
                await snapshot(leader)
            else:
                if ledger_status == "reconciliation":
                    await lock_fraud_reconciliation_gate(leader, exclusive=True)
                await lock_fraud_hold_scope(leader, graph.trip.id)
            task = asyncio.create_task(follower())
            try:
                await asyncio.wait_for(started.wait(), 5)
                for _ in range(300):
                    blocked = await leader.scalar(
                        text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"),
                        {"pid": follower_pid},
                    )
                    if blocked:
                        break
                    await asyncio.sleep(0.01)
                assert blocked, "the real transactions must overlap"
                if snapshot_first:
                    assert sum((await fraud_hold_counts(leader, graph.trip.id)).values()) == 1
                else:
                    await resolve(leader)
                await leader.commit()
                await asyncio.wait_for(task, 10)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        async with factory() as session:
            assert sum((await fraud_hold_counts(session, graph.trip.id)).values()) == (
                1 if confirmed else 0
            )
            await resolve(session)
            await session.commit()
            reversals = list(
                await session.scalars(
                    select(EarningsLedgerEntry).where(
                        EarningsLedgerEntry.trip_session_id == graph.trip.id,
                        EarningsLedgerEntry.entry_type == "reversal",
                    )
                )
            )
            assert reversals == []
            if reversals:
                assert reversals[0].amount == Decimal("125.50")

    asyncio.run(asyncio.wait_for(run(), 20))


def _add_one_trip_car(sessionmaker, *, admin, campaign, number: int):
    driver = create_test_user(
        sessionmaker,
        email=f"three-car-driver-{number}@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        sessionmaker, user_id=driver.id, onboarding_status=DriverOnboardingStatus.ACTIVE
    )
    vehicle = create_test_vehicle(
        sessionmaker,
        driver_profile_id=profile.id,
        plate_number=f"THREE-{number}",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
        activated_at=RECORDED_AT,
    )
    trip = create_test_trip_session(
        sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        trip_status=TripSessionStatus.ENDED,
        started_at=RECORDED_AT,
        ended_at=RECORDED_AT.replace(hour=11),
    )
    analytics = create_test_trip_analytics(
        sessionmaker,
        trip_session_id=trip.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_at=RECORDED_AT,
        ended_at=RECORDED_AT.replace(hour=11),
        first_ping_at=RECORDED_AT,
        last_ping_at=RECORDED_AT.replace(minute=5),
        distance_m=Decimal("10.00") * number,
    )
    estimate = create_test_impression_estimate(
        sessionmaker,
        trip_session_id=trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        traffic_density_profile_id=create_test_traffic_density_profile(
            sessionmaker, name=f"Three-car density {number}"
        ).id,
        estimated_impressions=Decimal("5000.00") * number,
    )
    add_ping_batch(
        sessionmaker,
        trip_id=trip.id,
        idempotency_key=f"three-car-{number}",
        points=[(RECORDED_AT, 6.45, 3.39), (RECORDED_AT.replace(minute=5), 6.45, 3.39)],
    )
    return trip, analytics, estimate


def test_date_range_summaries_need_three_cars_in_each_released_set(
    postgis_db_sessionmaker,
) -> None:
    """D107: estimates, costs and fraud flags are picked by their own timestamps, so three
    cars starting trips in the range cannot release one car's figures written in it."""
    settings = live_test_settings()
    admin, _, organization, campaign, *_ = create_heatmap_graph(
        postgis_db_sessionmaker,
        advertiser_email="dated-sets-advertiser@example.com",
        driver_email="dated-sets-driver@example.com",
        plate_number="DATED-1",
    )
    trip, analytics, estimate = _add_one_trip_car(
        postgis_db_sessionmaker, admin=admin, campaign=campaign, number=21
    )
    _add_one_trip_car(postgis_db_sessionmaker, admin=admin, campaign=campaign, number=22)
    payout_rule = create_test_payout_rule(
        postgis_db_sessionmaker, campaign_id=campaign.id, created_by_user_id=admin.id
    )
    start_at, end_at = RECORDED_AT - timedelta(minutes=1), RECORDED_AT.replace(hour=12)
    outside = datetime.now(UTC)

    async def date_analytics() -> None:
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                update(TripAnalytics)
                .where(TripAnalytics.campaign_id == campaign.id)
                .values(computed_at=RECORDED_AT)
            )
            await session.commit()

    # Backdated estimates must still be newer than their source analytics.
    asyncio.run(date_analytics())

    async def floors(statement=None) -> tuple[bool, bool]:
        async with postgis_db_sessionmaker() as session:
            if statement is not None:
                await session.execute(statement)
                await session.commit()
            return tuple(
                [
                    await trip_cohort_meets_disclosure_floor(
                        session,
                        tenant_id=organization.id,
                        campaign_id=campaign.id,
                        start_at=start_at,
                        end_at=end_at,
                        route_id=route_id,
                        settings=settings,
                    )
                    for route_id in (
                        "advertiser.campaign.impressions_summary",
                        "advertiser.campaign.summary",
                    )
                ]
            )

    in_campaign = ImpressionEstimate.campaign_id == campaign.id
    assert asyncio.run(
        floors(update(ImpressionEstimate).where(in_campaign).values(estimated_at=outside))
    ) == (True, True)
    one_estimate = update(ImpressionEstimate).where(ImpressionEstimate.id == estimate.id)
    assert asyncio.run(floors(one_estimate.values(estimated_at=RECORDED_AT))) == (False, False)
    every_estimate = update(ImpressionEstimate).where(in_campaign)
    assert asyncio.run(floors(every_estimate.values(estimated_at=RECORDED_AT))) == (True, True)

    async def add(row) -> None:
        async with postgis_db_sessionmaker() as session:
            session.add(row)
            await session.commit()

    car = {
        "trip_session_id": trip.id,
        "trip_analytics_id": analytics.id,
        "assignment_id": trip.assignment_id,
        "campaign_id": campaign.id,
        "driver_profile_id": trip.driver_profile_id,
        "vehicle_id": trip.vehicle_id,
    }
    asyncio.run(
        add(
            PayoutCalculation(
                **car,
                impression_estimate_id=estimate.id,
                payout_rule_id=payout_rule.id,
                formula_version="payout_v4",
                eligible_seconds=0,
                excluded_seconds_by_reason={},
                inputs_fingerprint="synthetic-dated-sets",
                distance_m_by_day={},
                amount_by_day={},
                status="calculated",
                currency="NGN",
                gross_payout=Decimal("1000.00"),
                final_payout=Decimal("1000.00"),
                calculated_at=RECORDED_AT,
                payout_metadata={},
            )
        )
    )
    # One car's cost in the range stays hidden; the impressions summary never shows costs.
    assert asyncio.run(floors()) == (True, False)
    one_cost = update(PayoutCalculation).where(PayoutCalculation.campaign_id == campaign.id)
    assert asyncio.run(floors(one_cost.values(calculated_at=outside))) == (True, True)
    asyncio.run(
        add(
            FraudFlag(
                **car,
                flag_type="excessive_ping_gap",
                severity="low",
                status="open",
                description="Synthetic dated fraud flag",
                evidence={},
                detected_at=RECORDED_AT,
            )
        )
    )
    # Refresh the estimate's fraud authority so the last assertion isolates the
    # one-car fraud output rather than stale-estimate suppression.
    asyncio.run(
        floors(
            one_estimate.values(
                estimate_metadata={"fraud_flag_counts": {"low": 1, "medium": 0, "high": 0}}
            )
        )
    )
    assert asyncio.run(floors()) == (True, False)


@pytest.mark.parametrize("vehicle_count", [2, 3])
def test_report_area_uses_three_cars_on_one_day_despite_dominant_contributions(
    postgis_db_client, postgis_db_sessionmaker, settings, vehicle_count
) -> None:
    from test_req180_batch2_reporting_flow import three_car_run

    settings.privacy_min_vehicles_per_cell = 3
    settings.privacy_min_resolution_m = 500
    _, campaign, _, headers = three_car_run(
        postgis_db_client,
        postgis_db_sessionmaker,
        vehicle_count=vehicle_count,
        dominant=True,
    )
    response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/report",
        params={
            "start_at": "2026-06-01T10:00:00+00:00",
            "end_at": "2026-06-02T10:00:00+00:00",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["areas"]) == (1 if vehicle_count == 3 else 0)


def test_three_cars_on_one_day_show_their_area_and_trips_with_default_settings(
    postgis_db_sessionmaker,
) -> None:
    """REQ-208 / D105 / D107: three distinct cars is the whole rule, even on a single day."""
    settings = live_test_settings()
    assert settings.privacy_min_vehicles_per_cell == 3
    admin, _, organization, campaign, *_ = create_heatmap_graph(
        postgis_db_sessionmaker,
        advertiser_email="three-car-advertiser@example.com",
        driver_email="three-car-driver-1@example.com",
        plate_number="THREE-1",
    )
    _add_one_trip_car(postgis_db_sessionmaker, admin=admin, campaign=campaign, number=2)
    query = heatmaps.parse_heatmap_query(
        bbox=BBOX,
        resolution_m=500,
        metric="estimated_impressions",
        start_at=None,
        end_at=None,
        settings=settings,
    )

    async def outputs() -> tuple[int, bool, bool]:
        async with postgis_db_sessionmaker() as session:
            result = await heatmaps.build_heatmap(
                session,
                query=query,
                settings=settings,
                campaign_id=campaign.id,
                organization_id=None,
                vehicle_type=None,
                metadata_campaign_id=campaign.id,
                metadata_organization_id=None,
            )
            cohort = {
                route_id: await trip_cohort_meets_disclosure_floor(
                    session,
                    tenant_id=organization.id,
                    campaign_id=campaign.id,
                    start_at=None,
                    end_at=None,
                    route_id=route_id,
                    settings=settings,
                )
                for route_id in ("advertiser.campaign.trips", "advertiser.campaign.daily_metrics")
            }
            return len(result.features), *cohort.values()

    assert asyncio.run(outputs()) == (0, False, False)
    _add_one_trip_car(postgis_db_sessionmaker, admin=admin, campaign=campaign, number=3)
    assert asyncio.run(outputs()) == (1, True, True)

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
    create_test_traffic_density_profile,
    create_test_trip_analytics,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import func, select
from starlette import status
from test_heatmaps import BBOX, PASSWORD, RECORDED_AT, add_ping_batch, create_heatmap_graph

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.jobs.disclosure_retention import purge_expired_disclosure_query_history
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.disclosure import DisclosureQueryDecision
from app.models.driver import DriverOnboardingStatus
from app.models.organization import MembershipRole, MembershipStatus, OrganizationMembership
from app.models.trip import TripSessionStatus
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.services import heatmaps, impressions, reports
from app.services.disclosure import (
    DISCLOSURE_ROUTE_INVENTORY,
    DisclosureQuery,
    ensure_disclosure_live_gate,
    record_heatmap_disclosure,
    require_governed_advertiser_output,
)


def live_test_settings(**overrides) -> Settings:
    values = {
        "environment": "test",
        "privacy_disclosure_live_authorized": True,
        "privacy_legal_approval_reference": "synthetic-legal-approval-v1",
        "privacy_disclosure_config_reference": "synthetic-disclosure-config-v1",
        "privacy_query_history_retention_reference": "synthetic-retention-v1",
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


def test_live_gate_is_default_deny_and_thresholds_cannot_enable_it() -> None:
    with pytest.raises(AppError) as missing:
        ensure_disclosure_live_gate(Settings(), requires_measurement_run=False)
    assert missing.value.code == "PRIVACY_LIVE_USE_BLOCKED"
    assert missing.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    thresholds_only = Settings(
        privacy_min_vehicles_per_cell=100,
        privacy_min_trips_per_cell=100,
        privacy_min_days_per_cell=30,
        privacy_max_contributor_share=0.01,
    )
    with pytest.raises(AppError, match="privacy approval"):
        ensure_disclosure_live_gate(thresholds_only, requires_measurement_run=False)

    with pytest.raises(ValueError, match="environment=test"):
        Settings(
            environment="production",
            jwt_secret_key="production-test-secret-key-that-is-long-enough",
            privacy_disclosure_synthetic_test_mode=True,
        )


def test_report_outputs_remain_blocked_after_legal_gate_until_safe_runs() -> None:
    with pytest.raises(AppError) as blocked:
        ensure_disclosure_live_gate(live_test_settings(), requires_measurement_run=True)
    assert blocked.value.code == "SAFE_MEASUREMENT_RUN_REQUIRED"


def test_route_inventory_covers_every_current_output_at_the_service_boundary() -> None:
    expected = {
        "advertiser.dashboard.summary",
        "advertiser.campaign.summary",
        "advertiser.campaign.daily_metrics",
        "advertiser.campaign.trips",
        "advertiser.campaign.report",
        "advertiser.campaign.impressions_summary",
        "advertiser.campaign.heatmap",
        "admin.heatmap",
    }
    assert DISCLOSURE_ROUTE_INVENTORY == expected

    sources = "\n".join(
        [
            inspect.getsource(reports.advertiser_dashboard_summary),
            inspect.getsource(reports.advertiser_campaign_summary),
            inspect.getsource(reports.daily_metrics_for_campaign),
            inspect.getsource(reports.advertiser_campaign_trips),
            inspect.getsource(reports.advertiser_campaign_report),
            inspect.getsource(impressions.advertiser_campaign_impression_summary),
            inspect.getsource(heatmaps.advertiser_campaign_heatmap),
            inspect.getsource(heatmaps.admin_heatmap),
        ]
    )
    for route_id in expected:
        assert route_id in sources

    heatmap_source = inspect.getsource(heatmaps.aggregation_sql)
    for boundary in (
        "privacy_min_vehicles_per_cell",
        "privacy_min_trips_per_cell",
        "privacy_min_days_per_cell",
        "privacy_max_contributor_share",
        "count(DISTINCT vehicle_id)",
        "count(DISTINCT recorded_day)",
    ):
        assert boundary in heatmap_source


def test_live_gate_runs_before_advertiser_membership_read() -> None:
    class NoReadSession:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("the blocked live gate must run before database reads")

    async def run() -> None:
        with pytest.raises(AppError) as blocked:
            await require_governed_advertiser_output(
                NoReadSession(),  # type: ignore[arg-type]
                settings=Settings(),
                route_id="advertiser.dashboard.summary",
                user_id=uuid4(),
            )
        assert blocked.value.code == "PRIVACY_LIVE_USE_BLOCKED"

    asyncio.run(run())


def test_governed_output_selects_latest_active_membership_deterministically(
    db_sessionmaker,
) -> None:
    advertiser = create_test_user(
        db_sessionmaker,
        email="disclosure-multi-membership@example.com",
        role=UserRole.ADVERTISER,
    )
    first_org, _ = create_test_organization(
        db_sessionmaker,
        name="First disclosure org",
        owner_user_id=advertiser.id,
    )
    second_org, _ = create_test_organization(
        db_sessionmaker,
        name="Second disclosure org",
        owner_user_id=advertiser.id,
    )

    async def run() -> None:
        async with db_sessionmaker() as session:
            # Make the adopted deterministic rule explicit when timestamps tie.
            memberships = list(
                await session.scalars(
                    select(OrganizationMembership)
                    .where(OrganizationMembership.user_id == advertiser.id)
                    .order_by(OrganizationMembership.created_at, OrganizationMembership.id)
                )
            )
            assert {membership.organization_id for membership in memberships} == {
                first_org.id,
                second_org.id,
            }
            tied_created_at = datetime(2026, 1, 1, tzinfo=UTC)
            for membership in memberships:
                membership.created_at = tied_created_at
            expected_organization_id = max(
                memberships, key=lambda membership: membership.id
            ).organization_id
            for membership in memberships:
                membership.status = MembershipStatus.ACTIVE
                membership.role = MembershipRole.OWNER
            await session.commit()

        async with db_sessionmaker() as session:
            selected = await require_governed_advertiser_output(
                session,
                settings=live_test_settings(),
                route_id="advertiser.dashboard.summary",
                user_id=advertiser.id,
                requires_measurement_run=False,
            )
            assert selected == expected_organization_id

    asyncio.run(run())


def test_every_current_output_is_default_denied_without_history_writes(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    admin, advertiser, _, campaign, *_ = create_heatmap_graph(db_sessionmaker)
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)
    blocked_settings = settings.model_copy(
        update={"privacy_disclosure_synthetic_test_mode": False}
    )
    db_client.app.dependency_overrides[get_settings] = lambda: blocked_settings
    requests = [
        ("/api/v1/advertiser/dashboard/summary", advertiser_headers, {}),
        (f"/api/v1/advertiser/campaigns/{campaign.id}/summary", advertiser_headers, {}),
        (f"/api/v1/advertiser/campaigns/{campaign.id}/daily-metrics", advertiser_headers, {}),
        (f"/api/v1/advertiser/campaigns/{campaign.id}/trips", advertiser_headers, {}),
        (f"/api/v1/advertiser/campaigns/{campaign.id}/report", advertiser_headers, {}),
        (
            f"/api/v1/advertiser/campaigns/{campaign.id}/impressions/summary",
            advertiser_headers,
            {},
        ),
        (
            f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
            advertiser_headers,
            {"bbox": BBOX},
        ),
        ("/api/v1/admin/heatmap", admin_headers, {"bbox": BBOX}),
    ]
    responses = [
        db_client.get(path, headers=headers, params=params) for path, headers, params in requests
    ]

    assert [response.status_code for response in responses] == [
        status.HTTP_503_SERVICE_UNAVAILABLE
    ] * len(requests)
    assert {response.json()["error"]["code"] for response in responses} == {
        "PRIVACY_LIVE_USE_BLOCKED"
    }

    async def history_count() -> int:
        async with db_sessionmaker() as session:
            return int(
                await session.scalar(select(func.count()).select_from(DisclosureQueryDecision)) or 0
            )

    assert asyncio.run(history_count()) == 0


def test_history_replays_exact_query_and_suppresses_overlapping_variant(
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
            with pytest.raises(AppError) as suppressed:
                await record_heatmap_disclosure(
                    session,
                    query=overlapping,
                    settings=live_test_settings(),
                    has_releasable_cells=True,
                    result_hash="a" * 64,
                )
            assert suppressed.value.details == {"reason": "overlapping_query_differencing"}
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

    assert asyncio.run(run()) == (2, {"served", "suppressed"})


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
                assert suppressed.value.details == {
                    "reason": "minimum_counts_or_contributor_cap"
                }
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
            with pytest.raises(AppError) as suppressed:
                await record_heatmap_disclosure(
                    session,
                    query=disclosure_query,
                    settings=live_test_settings(),
                    has_releasable_cells=True,
                    result_hash="b" * 64,
                )
            assert suppressed.value.details == {"reason": "overlapping_query_differencing"}
        async with db_sessionmaker() as session:
            return int(
                await session.scalar(select(func.count()).select_from(DisclosureQueryDecision)) or 0
            )

    assert asyncio.run(run()) == 2


@pytest.mark.parametrize("parent_kind", ["organization", "global"])
@pytest.mark.parametrize("parent_first", [True, False])
def test_parent_and_child_scopes_suppress_differencing_in_both_orders(
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
            with pytest.raises(AppError) as suppressed:
                await record_heatmap_disclosure(
                    session,
                    query=second,
                    settings=live_test_settings(),
                    has_releasable_cells=True,
                    result_hash="a" * 64,
                )
            return "served", suppressed.value.details["reason"]

    assert asyncio.run(run()) == ("served", "overlapping_query_differencing")


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

    assert asyncio.run(run()) == [
        "served",
        "suppressed",
    ]


def test_scheduled_retention_purge_removes_expired_history_without_query_traffic(
    db_sessionmaker,
) -> None:
    now = datetime.now(UTC)

    async def run() -> tuple[dict[str, int], int]:
        async with db_sessionmaker() as session:
            for suffix, expires_at in (
                ("a", now - timedelta(days=1)),
                ("b", now + timedelta(days=1)),
            ):
                session.add(
                    DisclosureQueryDecision(
                        principal_hash=suffix * 64,
                        scope_hash=suffix * 64,
                        query_hash=suffix * 64,
                        result_hash=suffix * 64,
                        tenant_id=uuid4(),
                        campaign_id=uuid4(),
                        output_class="advertiser.campaign.heatmap",
                        decision="served",
                        reason="privacy_floor_passed",
                        window_start=datetime(2026, 1, 1, tzinfo=UTC),
                        window_end=datetime(2026, 1, 8, tzinfo=UTC),
                        expires_at=expires_at,
                    )
                )
            await session.commit()
        result = await purge_expired_disclosure_query_history(
            {"sessionmaker": db_sessionmaker}
        )
        async with db_sessionmaker() as session:
            remaining = int(
                await session.scalar(select(func.count()).select_from(DisclosureQueryDecision)) or 0
            )
        return result, remaining

    assert asyncio.run(run()) == ({"deleted": 1}, 1)


def test_concurrent_overlapping_queries_serialize_to_one_served_one_suppressed(
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

    assert asyncio.run(run()) == ["served", "suppressed"]


def test_heatmap_floor_enforces_exact_vehicle_trip_day_and_metric_contributor_edges(
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

    exact = asyncio.run(
        feature_count(
            privacy_min_vehicles_per_cell=2,
            privacy_min_trips_per_cell=2,
            privacy_min_days_per_cell=1,
            privacy_max_contributor_share=0.5,
        )
    )
    below_vehicle = asyncio.run(feature_count(privacy_min_vehicles_per_cell=3))
    below_trip = asyncio.run(feature_count(privacy_min_trips_per_cell=3))
    below_day = asyncio.run(feature_count(privacy_min_days_per_cell=2))
    over_cap = asyncio.run(feature_count(privacy_max_contributor_share=0.49))

    assert exact == 1
    assert (below_vehicle, below_trip, below_day, over_cap) == (0, 0, 0, 0)


def test_heatmap_suppresses_when_an_unselected_serialized_metric_is_dominated(
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
                settings=live_test_settings(
                    privacy_min_vehicles_per_cell=2,
                    privacy_min_trips_per_cell=2,
                    privacy_min_days_per_cell=1,
                    privacy_max_contributor_share=0.75,
                ),
                campaign_id=campaign.id,
                organization_id=None,
                vehicle_type=None,
                metadata_campaign_id=campaign.id,
                metadata_organization_id=None,
            )
            return len(result.features)

    # ping_count is balanced at 50/50, but estimated_impressions is dominated
    # by the second vehicle and is serialized in the same feature.
    assert asyncio.run(run()) == 0

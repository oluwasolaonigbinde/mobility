import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from test_advertiser_reports import create_report_graph

from app.core.config import Settings
from app.core.errors import AppError
from app.models.user import UserRole
from app.services import disclosure
from app.services.disclosure import DisclosureQuery
from app.services.reports import advertiser_campaign_summary


def live_settings() -> Settings:
    return Settings(
        environment="test",
        privacy_disclosure_live_authorized=True,
        privacy_legal_approval_reference="synthetic-legal-approval-v1",
        privacy_disclosure_config_reference="synthetic-disclosure-config-v1",
        privacy_query_history_retention_reference="synthetic-retention-v1",
    )


def test_three_query_cross_endpoint_and_principal_composition_is_suppressed(
    postgis_db_sessionmaker,
) -> None:
    tenant_id = uuid4()
    campaign_id = uuid4()
    start_at = datetime(2026, 8, 1, tzinfo=UTC)
    first = DisclosureQuery(
        route_id="advertiser.campaign.summary",
        principal_id=uuid4(),
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        start_at=start_at,
        end_at=start_at + timedelta(days=7),
        filters={"projection": "summary"},
    )
    overlapping = DisclosureQuery(
        route_id="advertiser.campaign.report",
        principal_id=uuid4(),
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        start_at=start_at + timedelta(days=1),
        end_at=start_at + timedelta(days=8),
        filters={"projection": "issued-report"},
    )
    non_overlapping = DisclosureQuery(
        route_id="advertiser.audience.export",
        principal_id=uuid4(),
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        start_at=start_at + timedelta(days=9),
        end_at=start_at + timedelta(days=10),
        filters={"projection": "aggregate-targets"},
    )

    async def run() -> list[str]:
        decisions: list[str] = []
        for item, result_hash in (
            (first, "a" * 64),
            (overlapping, "b" * 64),
            (non_overlapping, "c" * 64),
        ):
            async with postgis_db_sessionmaker() as session:
                try:
                    await disclosure.record_disclosure(
                        session,
                        query=item,
                        settings=live_settings(),
                        has_releasable_cells=True,
                        result_hash=result_hash,
                    )
                except AppError as exc:
                    assert exc.code == "DISCLOSURE_SUPPRESSED"
                    decisions.append(exc.details["reason"])
                else:
                    decisions.append("served")
        return decisions

    assert asyncio.run(run()) == [
        "served",
        "overlapping_query_differencing",
        "served",
    ]


def test_non_heatmap_floor_suppression_is_durable(db_sessionmaker) -> None:
    query = DisclosureQuery(
        route_id="advertiser.campaign.daily_metrics",
        principal_id=uuid4(),
        tenant_id=uuid4(),
        campaign_id=uuid4(),
        start_at=datetime(2026, 8, 1, tzinfo=UTC),
        end_at=datetime(2026, 8, 2, tzinfo=UTC),
        filters={"limit": 30, "offset": 0},
    )

    async def run() -> None:
        for _ in range(2):
            async with db_sessionmaker() as session:
                with pytest.raises(AppError) as suppressed:
                    await disclosure.record_disclosure(
                        session,
                        query=query,
                        settings=live_settings(),
                        has_releasable_cells=False,
                        result_hash="0" * 64,
                    )
                assert suppressed.value.details == {"reason": "minimum_counts_or_contributor_cap"}

    asyncio.run(run())


def test_campaign_summary_denies_a_single_contributor_before_returning_values(
    db_sessionmaker,
) -> None:
    admin = create_test_user(
        db_sessionmaker,
        email="composition-admin@example.com",
        role=UserRole.ADMIN,
    )
    advertiser = create_test_user(
        db_sessionmaker,
        email="composition-advertiser@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    create_report_graph(
        db_sessionmaker,
        admin=admin,
        advertiser=advertiser,
        campaign=campaign,
        driver_email="composition-driver@example.com",
        plate_number="COMP-001",
        started_at=datetime(2026, 8, 1, 10, tzinfo=UTC),
    )

    async def run() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as suppressed:
                await advertiser_campaign_summary(
                    session,
                    user_id=advertiser.id,
                    campaign_id=campaign.id,
                    start_at=datetime(2026, 8, 1, tzinfo=UTC),
                    end_at=datetime(2026, 8, 2, tzinfo=UTC),
                    settings=live_settings(),
                )
            assert suppressed.value.code == "DISCLOSURE_SUPPRESSED"
            assert suppressed.value.details == {"reason": "minimum_counts_or_contributor_cap"}

    asyncio.run(run())

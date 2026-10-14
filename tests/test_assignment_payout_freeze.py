"""Daily-rate acceptance identity, snapshot and concurrency authority."""

import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest
from conftest import (
    fetch_activation_events,
)
from payout_fixtures import (
    FUTURE,
    accept_assignment,
    add_target_zone,
    build_offered_graph,
    create_v4_revision,
    create_v4_rule,
    fetch_bindings,
    materialize_offer,
)
from sqlalchemy import delete, func, select

from app.core.errors import AppError
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.payout import (
    CampaignPayoutRuleRevision,
)
from app.schemas.campaign_assignments import CampaignAssignmentCreate, CampaignAssignmentTransition
from app.schemas.payouts import CampaignPayoutV4RevisionCreate
from app.services.campaign_assignments import (
    accept_driver_assignment,
    create_campaign_assignment,
    frozen_zone_geometry_hash,
)
from app.services.payout_eligibility import (
    STATIONARY_POLICY_D39,
)
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock
from app.services.payouts import (
    PAYOUT_V4,
    publish_payout_v4_revision,
)


def test_accept_freezes_effective_revision_with_zone_snapshot(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-accept")
    rule = create_v4_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        admin_id=graph.admin.id,
    )
    revision = create_v4_revision(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=rule.id,
        admin_id=graph.admin.id,
        daily_rate_naira="15000.00",
    )
    zone = add_target_zone(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        name="Premium A",
        lat_min=6.40,
        lat_max=6.52,
    )
    materialize_offer(postgis_db_sessionmaker, settings, graph)

    accepted = accept_assignment(
        postgis_db_sessionmaker,
        settings,
        user_id=graph.driver.id,
        assignment_id=graph.assignment.id,
    )
    assert accepted.status == CampaignAssignmentStatus.ACCEPTED.value
    assert accepted.offer_terms["payout"]["currency"] == "NGN"

    bindings = fetch_bindings(postgis_db_sessionmaker)
    assert len(bindings) == 1
    binding = bindings[0]
    assert binding.assignment_id == graph.assignment.id
    assert binding.revision_id == revision.id
    assert binding.currency == revision.currency == "NGN"
    assert binding.daily_rate_naira == Decimal("15000.00")
    assert binding.daily_target_miles == Decimal("8.000")
    assert binding.eligibility_params == {"stationary_window_min": 5, "stationary_grace_min": 0}
    assert binding.formula_version == PAYOUT_V4
    assert set(binding.premium_zone_ids) == {str(zone.id), str(graph.target_zone.id)}
    assert binding.stationary_policy_marker == STATIONARY_POLICY_D39
    assert binding.campaign_window_start_at == graph.campaign.start_at
    assert binding.campaign_window_end_at == graph.campaign.end_at
    assert binding.campaign_window_frozen is True
    assert binding.bound_at == accepted.accepted_at
    assert binding.resolved_eligibility_params == {
        "stationary_radius_m": 200.0,
        "stationary_window_seconds": 300,
        "stationary_grace_seconds": 0,
        "max_accuracy_m": 75.0,
        "teleport_kmh": 180.0,
        "max_ping_gap_seconds": 120,
    }

    # The geometry hash is the deterministic sha256 of the frozen target
    # zones' (id, geometry) pairs sorted by id.
    async def expected_hash() -> str:
        async with postgis_db_sessionmaker() as session:
            rows = (
                await session.execute(
                    select(CampaignZone.id, func.ST_AsText(CampaignZone.geom))
                    .where(
                        CampaignZone.campaign_id == graph.campaign.id,
                        CampaignZone.zone_type == CampaignZoneType.TARGET.value,
                    )
                    .order_by(CampaignZone.id)
                )
            ).all()
            return frozen_zone_geometry_hash(rows)

    assert binding.premium_zone_geometry_hash == asyncio.run(expected_hash())
    assert len(binding.premium_zone_geometry_hash) == 64
    int(binding.premium_zone_geometry_hash, 16)  # hex digest


def test_accept_legacy_offer_binds_its_frozen_top_level_currency(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-legacy-offer-currency")
    rule = create_v4_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        admin_id=graph.admin.id,
    )
    revision = create_v4_revision(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=rule.id,
        admin_id=graph.admin.id,
    )
    materialize_offer(
        postgis_db_sessionmaker,
        settings,
        graph,
        legacy_top_level_currency_only=True,
    )

    accepted = accept_assignment(
        postgis_db_sessionmaker,
        settings,
        user_id=graph.driver.id,
        assignment_id=graph.assignment.id,
    )

    binding = fetch_bindings(postgis_db_sessionmaker)[0]
    assert "currency" not in accepted.offer_terms["payout"]
    assert binding.currency == revision.currency == accepted.offer_terms["currency"] == "NGN"


def test_accept_rejects_explicitly_null_nested_offer_currency(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-null-offer-currency")
    rule = create_v4_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        admin_id=graph.admin.id,
    )
    create_v4_revision(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=rule.id,
        admin_id=graph.admin.id,
    )
    materialize_offer(
        postgis_db_sessionmaker,
        settings,
        graph,
        null_payout_currency=True,
    )

    with pytest.raises(AppError) as exc_info:
        accept_assignment(
            postgis_db_sessionmaker,
            settings,
            user_id=graph.driver.id,
            assignment_id=graph.assignment.id,
        )

    assert exc_info.value.code == "FROZEN_OFFER_TERMS_REQUIRED"
    assert fetch_bindings(postgis_db_sessionmaker) == []


def test_accept_rejects_nested_offer_currency_that_disagrees_with_top_level(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-nested-currency-mismatch")
    rule = create_v4_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        admin_id=graph.admin.id,
    )
    create_v4_revision(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=rule.id,
        admin_id=graph.admin.id,
    )
    materialize_offer(
        postgis_db_sessionmaker,
        settings,
        graph,
        nested_payout_currency="USD",
    )

    with pytest.raises(AppError) as exc_info:
        accept_assignment(
            postgis_db_sessionmaker,
            settings,
            user_id=graph.driver.id,
            assignment_id=graph.assignment.id,
        )

    assert exc_info.value.code == "FROZEN_OFFER_TERMS_REQUIRED"
    assert fetch_bindings(postgis_db_sessionmaker) == []


def test_accept_rejects_legacy_offer_currency_that_disagrees_with_revision(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-legacy-currency-drift")
    rule = create_v4_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        admin_id=graph.admin.id,
    )
    revision = create_v4_revision(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=rule.id,
        admin_id=graph.admin.id,
    )
    materialize_offer(
        postgis_db_sessionmaker,
        settings,
        graph,
        legacy_top_level_currency_only=True,
    )

    async def drift_revision_currency() -> None:
        async with postgis_db_sessionmaker() as session:
            stored_revision = await session.get(CampaignPayoutRuleRevision, revision.id)
            stored_revision.currency = "USD"
            await session.commit()

    asyncio.run(drift_revision_currency())

    with pytest.raises(AppError) as exc_info:
        accept_assignment(
            postgis_db_sessionmaker,
            settings,
            user_id=graph.driver.id,
            assignment_id=graph.assignment.id,
        )

    assert exc_info.value.code == "FROZEN_OFFER_TERMS_REQUIRED"
    assert fetch_bindings(postgis_db_sessionmaker) == []


def test_offer_without_frozen_terms_rejects_acceptance_without_binding(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-none")
    # Rule row inserted directly (no revision chain): legacy campaign shape.
    create_v4_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        admin_id=graph.admin.id,
    )
    with pytest.raises(AppError) as exc_info:
        accept_assignment(
            postgis_db_sessionmaker,
            settings,
            user_id=graph.driver.id,
            assignment_id=graph.assignment.id,
        )
    assert exc_info.value.code == "FROZEN_OFFER_TERMS_REQUIRED"
    assert fetch_bindings(postgis_db_sessionmaker) == []


def test_concurrent_accepts_yield_exactly_one_binding(postgis_db_sessionmaker, settings) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-race")
    rule = create_v4_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        admin_id=graph.admin.id,
    )
    create_v4_revision(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=rule.id,
        admin_id=graph.admin.id,
    )
    materialize_offer(postgis_db_sessionmaker, settings, graph)

    async def attempt():
        async with postgis_db_sessionmaker() as session:
            try:
                await accept_driver_assignment(
                    session,
                    user_id=graph.driver.id,
                    assignment_id=graph.assignment.id,
                    payload=CampaignAssignmentTransition(),
                    settings=settings,
                )
                await session.commit()
                return "accepted"
            except AppError as exc:
                await session.rollback()
                return exc

    async def race():
        return await asyncio.gather(attempt(), attempt())

    outcomes = asyncio.run(race())
    assert outcomes == ["accepted", "accepted"]
    assert len(fetch_bindings(postgis_db_sessionmaker)) == 1
    assert [event.event_type for event in fetch_activation_events(postgis_db_sessionmaker)] == [
        "accepted"
    ]


def test_revision_publication_before_accept_binds_from_shared_lock_and_db_clock(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-sup-race")
    rule = create_v4_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        admin_id=graph.admin.id,
    )
    revision1 = create_v4_revision(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=rule.id,
        admin_id=graph.admin.id,
    )
    materialize_offer(postgis_db_sessionmaker, settings, graph)

    revision_has_lock = asyncio.Event()

    async def accept():
        await revision_has_lock.wait()
        async with postgis_db_sessionmaker() as session:
            assignment = await accept_driver_assignment(
                session,
                user_id=graph.driver.id,
                assignment_id=graph.assignment.id,
                payload=CampaignAssignmentTransition(),
                settings=settings,
            )
            await session.commit()
            return assignment

    async def supersede():
        async with postgis_db_sessionmaker() as session:
            # Establish publication-first ordering while acceptance is live
            # and waiting on the exact same campaign transaction lock.
            await acquire_campaign_terms_lock(session, graph.campaign.id)
            effective_from = await database_clock(session) + timedelta(seconds=2)
            revision_has_lock.set()
            revision, previous, _ = await publish_payout_v4_revision(
                session,
                campaign_id=graph.campaign.id,
                payload=CampaignPayoutV4RevisionCreate(
                    effective_from=effective_from,
                    daily_rate_naira=Decimal("9999.00"),
                    daily_target_miles=Decimal("8.00"),
                    shortfall_strategy="proportional",
                    minimum_miles=Decimal("0"),
                    outside_area_weight=Decimal("1"),
                    reason="publication wins shared serialization",
                ),
                actor_user_id=graph.admin.id,
                settings=settings.model_copy(update={"payout_v4_publishing_enabled": True}),
            )
            # Keep the transaction lock through the effective boundary. The
            # waiting acceptance must then take a fresh database wall clock,
            # which is necessarily after this newly published revision.
            await asyncio.sleep(2.1)
            await session.commit()
            return revision, previous, effective_from

    async def race():
        published, accepted = await asyncio.gather(supersede(), accept())
        return accepted, published

    accepted, (rev2, _, effective_from) = asyncio.run(race())
    assert accepted.status == CampaignAssignmentStatus.ACCEPTED.value
    assert rev2.revision_number == 2

    bindings = fetch_bindings(postgis_db_sessionmaker)
    assert len(bindings) == 1
    # The offer was materialized from rev1 before publication.  Acceptance
    # must therefore bind that immutable displayed snapshot, even when rev2
    # publishes before the decision commits; mutable producer edits never
    # reprice an already-offered assignment.
    assert bindings[0].revision_id == revision1.id
    assert bindings[0].daily_rate_naira == revision1.daily_rate_naira
    assert bindings[0].daily_target_miles == revision1.daily_target_miles
    assert bindings[0].bound_at is not None


def test_offer_creation_after_revision_publication_freezes_new_revision_postgres(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-offer-pub-race")
    rule = create_v4_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        admin_id=graph.admin.id,
    )
    revision1 = create_v4_revision(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=rule.id,
        admin_id=graph.admin.id,
    )

    async def remove_fixture_offer() -> None:
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                delete(CampaignAssignment).where(CampaignAssignment.id == graph.assignment.id)
            )
            await session.commit()

    asyncio.run(remove_fixture_offer())
    publication_has_lock = asyncio.Event()

    async def publish():
        async with postgis_db_sessionmaker() as session:
            await acquire_campaign_terms_lock(session, graph.campaign.id)
            effective_from = await database_clock(session) + timedelta(seconds=2)
            publication_has_lock.set()
            revision2, _, _ = await publish_payout_v4_revision(
                session,
                campaign_id=graph.campaign.id,
                payload=CampaignPayoutV4RevisionCreate(
                    effective_from=effective_from,
                    daily_rate_naira=Decimal("9999.00"),
                    daily_target_miles=Decimal("8.00"),
                    shortfall_strategy="proportional",
                    minimum_miles=Decimal("0"),
                    outside_area_weight=Decimal("1"),
                    reason="offer publication race",
                ),
                actor_user_id=graph.admin.id,
                settings=settings.model_copy(update={"payout_v4_publishing_enabled": True}),
            )
            await asyncio.sleep(2.1)
            await session.commit()
            return revision2

    async def offer():
        await publication_has_lock.wait()
        async with postgis_db_sessionmaker() as session:
            assignment = await create_campaign_assignment(
                session,
                admin_user_id=graph.admin.id,
                payload=CampaignAssignmentCreate(
                    campaign_id=graph.campaign.id,
                    driver_profile_id=graph.profile.id,
                    vehicle_id=graph.vehicle.id,
                    creative_id=graph.creative.id,
                    expires_at=FUTURE - timedelta(days=1),
                ),
                settings=settings,
            )
            await session.commit()
            return assignment

    async def race():
        return await asyncio.wait_for(asyncio.gather(publish(), offer()), timeout=10)

    revision2, offered = asyncio.run(race())
    assert revision1.id != revision2.id
    assert offered.offer_terms is not None
    assert offered.offer_terms["payout"]["revision_id"] == str(revision2.id)
    assert offered.offer_terms["payout"]["daily_rate_naira"] == str(revision2.daily_rate_naira)
    assert offered.offer_terms["payout"]["daily_target_miles"] == str(revision2.daily_target_miles)

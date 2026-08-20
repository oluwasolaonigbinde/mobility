"""MNY-06A: append-only effective-dated payout-rule revisions (D18, PR1/PR3).

Covers the PR1 guards (DB-clock floor, strictly-after-latest, in-transaction
sequence numbering, fail-closed concurrent supersede), the PR3 create-rule
retirement for chained campaigns and the atomic rule+genesis create, the
retired v2 PATCH, the value-complete audit event (A3, closes RM6 for this
path), and money-neutrality: payout_v2 pricing never reads revisions (A4).
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_organization,
    create_test_payout_rule,
    create_test_user,
    fetch_audit_events,
    fetch_earnings_ledger_entries,
    fetch_payout_calculations,
)
from sqlalchemy import select
from starlette import status as http_status
from test_payouts_v2 import build_v2_graph, create_v2_rule, pipeline_to_v2, run_recompute

from app.api.v1.payouts import payout_rule_revision_response
from app.core.errors import AppError
from app.models.campaign import CampaignStatus
from app.models.payout import CampaignPayoutRuleRevision
from app.models.user import UserRole
from app.schemas.payouts import CampaignPayoutRuleRevisionCreate
from app.services.payouts import create_payout_rule_revision

PASSWORD = "long-secure-password"


def setup_v2_campaign_via_api(client, sessionmaker, *, tag: str) -> SimpleNamespace:
    admin = create_test_user(sessionmaker, email=f"{tag}-admin@example.com")
    advertiser = create_test_user(
        sessionmaker, email=f"{tag}-adv@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(
        sessionmaker, name=f"{tag} org", owner_user_id=advertiser.id
    )
    campaign = create_test_campaign(
        sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name=f"{tag} campaign",
        campaign_status=CampaignStatus.ACTIVE,
    )
    headers = auth_headers(client, admin.email, PASSWORD)
    base = f"/api/v1/admin/campaigns/{campaign.id}/payout-rules"
    created = client.post(
        base,
        headers=headers,
        json={
            "formula_version": "payout_v2",
            "hourly_rate_naira": "1200.00",
            "daily_payable_hours_cap": "8.00",
            "eligibility_params": {"stationary_grace_min": 5},
        },
    )
    assert created.status_code == http_status.HTTP_201_CREATED, created.text
    return SimpleNamespace(
        admin=admin,
        campaign=campaign,
        organization=organization,
        advertiser=advertiser,
        headers=headers,
        base=base,
        rule=created.json(),
        revisions_url=f"{base}/{created.json()['id']}/revisions",
    )


def revision_payload(**overrides) -> CampaignPayoutRuleRevisionCreate:
    values = {
        "effective_from": datetime.now(UTC) + timedelta(hours=1),
        "hourly_rate_naira": Decimal("1500.00"),
        "daily_payable_hours_cap": Decimal("8.00"),
        "reason": "test supersede",
    }
    values.update(overrides)
    return CampaignPayoutRuleRevisionCreate(**values)


def service_create_revision(sessionmaker, *, campaign_id, rule_id, actor_user_id, **overrides):
    async def run():
        async with sessionmaker() as session:
            revision, previous = await create_payout_rule_revision(
                session,
                campaign_id=campaign_id,
                rule_id=rule_id,
                payload=revision_payload(**overrides),
                actor_user_id=actor_user_id,
            )
            await session.commit()
            return revision, previous

    return asyncio.run(run())


def fetch_revisions(sessionmaker, campaign_id) -> list[CampaignPayoutRuleRevision]:
    async def run():
        async with sessionmaker() as session:
            result = await session.execute(
                select(CampaignPayoutRuleRevision)
                .where(CampaignPayoutRuleRevision.campaign_id == campaign_id)
                .order_by(CampaignPayoutRuleRevision.revision_number)
            )
            return list(result.scalars().all())

    return asyncio.run(run())


def test_revision_response_normalizes_historical_null_eligibility_params() -> None:
    revision = SimpleNamespace(
        id="0c0c0c0c-0000-4000-8000-000000000001",
        campaign_id="0c0c0c0c-0000-4000-8000-000000000002",
        payout_rule_id="0c0c0c0c-0000-4000-8000-000000000003",
        revision_number=1,
        effective_from=datetime.now(UTC),
        hourly_rate_naira=Decimal("1200.00"),
        premium_hourly_rate_naira=None,
        daily_payable_hours_cap=Decimal("8.00"),
        eligibility_params=None,
        formula_version="payout_v3",
        reason="historical genesis",
        created_by_user_id="0c0c0c0c-0000-4000-8000-000000000004",
        created_at=datetime.now(UTC),
    )

    response = payout_rule_revision_response(revision)

    assert response.eligibility_params == {}


# --- API: atomic genesis, create/supersede, list, audit ----------------------


def test_api_create_supersede_list_and_value_complete_audit(
    postgis_db_client, postgis_db_sessionmaker
) -> None:
    ctx = setup_v2_campaign_via_api(
        postgis_db_client, postgis_db_sessionmaker, tag="rev-api"
    )

    # PR3: rule creation wrote the genesis revision atomically.
    listing = postgis_db_client.get(ctx.revisions_url, headers=ctx.headers)
    assert listing.status_code == http_status.HTTP_200_OK
    body = listing.json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert body["total"] == 1
    genesis = body["items"][0]
    assert genesis["revision_number"] == 1
    assert genesis["formula_version"] == "payout_v3"
    assert genesis["hourly_rate_naira"] == "1200.00"
    assert genesis["premium_hourly_rate_naira"] is None
    assert genesis["daily_payable_hours_cap"] == "8.00"
    assert genesis["eligibility_params"] == {"stationary_grace_min": 5}

    # The rule-created audit event carries the genesis values (A3).
    created_events = [
        event
        for event in fetch_audit_events(postgis_db_sessionmaker)
        if event.action == "admin.campaign_payout_rule.created"
    ]
    assert len(created_events) == 1
    genesis_audit = created_events[0].event_metadata["genesis_revision"]
    assert genesis_audit["revision_number"] == 1
    assert genesis_audit["hourly_rate_naira"] == "1200.00"

    # Supersede via API.
    effective_from = datetime.now(UTC) + timedelta(hours=1)
    created = postgis_db_client.post(
        ctx.revisions_url,
        headers=ctx.headers,
        json={
            "effective_from": effective_from.isoformat(),
            "hourly_rate_naira": "1500.00",
            "premium_hourly_rate_naira": "1800.00",
            "daily_payable_hours_cap": "7.50",
            "eligibility_params": {"stationary_grace_min": 6},
            "reason": "rate uplift for premium zones",
        },
    )
    assert created.status_code == http_status.HTTP_201_CREATED, created.text
    revision = created.json()
    assert revision["revision_number"] == 2
    assert revision["formula_version"] == "payout_v3"
    # Decimal-as-string on the wire (X4).
    assert revision["hourly_rate_naira"] == "1500.00"
    assert revision["premium_hourly_rate_naira"] == "1800.00"
    assert revision["daily_payable_hours_cap"] == "7.50"
    assert revision["reason"] == "rate uplift for premium zones"
    assert revision["created_by_user_id"] == str(ctx.admin.id)

    # History stays readable, newest first (A2).
    listing = postgis_db_client.get(
        f"{ctx.revisions_url}?limit=10&offset=0", headers=ctx.headers
    )
    assert listing.json()["total"] == 2
    assert [item["revision_number"] for item in listing.json()["items"]] == [2, 1]

    # Value-complete audit: FULL before/after values + reason (A3, RM6).
    revision_events = [
        event
        for event in fetch_audit_events(postgis_db_sessionmaker)
        if event.action == "admin.payout_rule_revision.created"
    ]
    assert len(revision_events) == 1
    metadata = revision_events[0].event_metadata
    assert metadata["reason"] == "rate uplift for premium zones"
    assert metadata["before"]["revision_number"] == 1
    assert metadata["before"]["hourly_rate_naira"] == "1200.00"
    assert metadata["before"]["premium_hourly_rate_naira"] is None
    assert metadata["before"]["daily_payable_hours_cap"] == "8.00"
    assert metadata["after"]["revision_number"] == 2
    assert metadata["after"]["hourly_rate_naira"] == "1500.00"
    assert metadata["after"]["premium_hourly_rate_naira"] == "1800.00"
    assert metadata["after"]["daily_payable_hours_cap"] == "7.50"
    assert metadata["after"]["eligibility_params"] == {"stationary_grace_min": 6}
    assert revision_events[0].actor_user_id == ctx.admin.id


def test_api_rejects_invalid_revisions_and_retired_mutations(
    postgis_db_client, postgis_db_sessionmaker
) -> None:
    ctx = setup_v2_campaign_via_api(
        postgis_db_client, postgis_db_sessionmaker, tag="rev-guard"
    )
    future = datetime.now(UTC) + timedelta(hours=1)

    # Naive datetime -> schema validation error.
    naive = postgis_db_client.post(
        ctx.revisions_url,
        headers=ctx.headers,
        json={
            "effective_from": future.replace(tzinfo=None).isoformat(),
            "hourly_rate_naira": "1500.00",
            "daily_payable_hours_cap": "8.00",
            "reason": "naive",
        },
    )
    assert naive.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT

    # Blank reason -> schema validation error.
    blank_reason = postgis_db_client.post(
        ctx.revisions_url,
        headers=ctx.headers,
        json={
            "effective_from": future.isoformat(),
            "hourly_rate_naira": "1500.00",
            "daily_payable_hours_cap": "8.00",
            "reason": "   ",
        },
    )
    assert blank_reason.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT

    # DB-clock floor (PR1): the past is closed to revisions.
    past = postgis_db_client.post(
        ctx.revisions_url,
        headers=ctx.headers,
        json={
            "effective_from": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "hourly_rate_naira": "1500.00",
            "daily_payable_hours_cap": "8.00",
            "reason": "retroactive",
        },
    )
    assert past.status_code == http_status.HTTP_400_BAD_REQUEST
    assert past.json()["error"]["code"] == "INVALID_PAYOUT_RULE_REVISION"

    # Unknown eligibility keys are rejected by the shared overlay validator.
    bad_params = postgis_db_client.post(
        ctx.revisions_url,
        headers=ctx.headers,
        json={
            "effective_from": future.isoformat(),
            "hourly_rate_naira": "1500.00",
            "daily_payable_hours_cap": "8.00",
            "eligibility_params": {"nope": 1},
            "reason": "bad params",
        },
    )
    assert bad_params.status_code == http_status.HTTP_400_BAD_REQUEST
    assert bad_params.json()["error"]["code"] == "INVALID_PAYOUT_RULE"

    # Retired v2 PATCH: 409 directing to revisions.
    patched = postgis_db_client.patch(
        f"{ctx.base}/{ctx.rule['id']}",
        headers=ctx.headers,
        json={"hourly_rate_naira": "1300.00"},
    )
    assert patched.status_code == http_status.HTTP_409_CONFLICT
    assert patched.json()["error"]["code"] == "PAYOUT_RULE_MUTATION_RETIRED"

    # Chained campaign: rule creation is retired (PR3a).
    second_rule = postgis_db_client.post(
        ctx.base,
        headers=ctx.headers,
        json={
            "formula_version": "payout_v2",
            "hourly_rate_naira": "999.00",
            "daily_payable_hours_cap": "8.00",
        },
    )
    assert second_rule.status_code == http_status.HTTP_409_CONFLICT
    assert second_rule.json()["error"]["code"] == "PAYOUT_RULE_REVISIONS_EXIST"

    # Nothing beyond the genesis was appended by any rejected call.
    assert len(fetch_revisions(postgis_db_sessionmaker, ctx.campaign.id)) == 1


# --- Service guards (PR1) ----------------------------------------------------


def test_service_rejects_retro_insertion_and_wrong_rule_models(
    postgis_db_sessionmaker,
) -> None:
    admin = create_test_user(postgis_db_sessionmaker, email="rev-svc-admin@example.com")
    advertiser = create_test_user(
        postgis_db_sessionmaker, email="rev-svc-adv@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(
        postgis_db_sessionmaker, name="rev svc org", owner_user_id=advertiser.id
    )
    campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name="rev svc campaign",
    )
    v1_campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name="rev svc v1 campaign",
    )

    # payout_v1 rules have no hourly value chain.
    v1_rule = create_test_payout_rule(
        postgis_db_sessionmaker, campaign_id=v1_campaign.id, created_by_user_id=admin.id
    )
    try:
        service_create_revision(
            postgis_db_sessionmaker,
            campaign_id=v1_campaign.id,
            rule_id=v1_rule.id,
            actor_user_id=admin.id,
        )
        raise AssertionError("expected INVALID_PAYOUT_RULE_REVISION")
    except AppError as exc:
        assert exc.code == "INVALID_PAYOUT_RULE_REVISION"

    # Inactive rules take no revisions.
    inactive_rule = create_v2_rule(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        rule_status="inactive",
    )
    try:
        service_create_revision(
            postgis_db_sessionmaker,
            campaign_id=campaign.id,
            rule_id=inactive_rule.id,
            actor_user_id=admin.id,
        )
        raise AssertionError("expected PAYOUT_RULE_INACTIVE")
    except AppError as exc:
        assert exc.code == "PAYOUT_RULE_INACTIVE"

    # A legacy chain-less active v2 rule (pre-backfill shape) starts at 1,
    # and retro-insertion behind the latest revision is impossible (A5:
    # equal effective_from is also rejected — boundaries stay deterministic).
    rule = create_v2_rule(
        postgis_db_sessionmaker, campaign_id=campaign.id, created_by_user_id=admin.id
    )
    effective = datetime.now(UTC) + timedelta(hours=2)
    revision, previous = service_create_revision(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        rule_id=rule.id,
        actor_user_id=admin.id,
        effective_from=effective,
    )
    assert previous is None
    assert revision.revision_number == 1
    assert revision.formula_version == "payout_v3"

    for retro_effective in (effective, effective - timedelta(minutes=30)):
        try:
            service_create_revision(
                postgis_db_sessionmaker,
                campaign_id=campaign.id,
                rule_id=rule.id,
                actor_user_id=admin.id,
                effective_from=retro_effective,
            )
            raise AssertionError("expected INVALID_PAYOUT_RULE_REVISION")
        except AppError as exc:
            assert exc.code == "INVALID_PAYOUT_RULE_REVISION"

    assert [r.revision_number for r in fetch_revisions(postgis_db_sessionmaker, campaign.id)] == [1]


def test_concurrent_supersede_has_exactly_one_winner(postgis_db_sessionmaker) -> None:
    admin = create_test_user(postgis_db_sessionmaker, email="rev-race-admin@example.com")
    advertiser = create_test_user(
        postgis_db_sessionmaker, email="rev-race-adv@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(
        postgis_db_sessionmaker, name="rev race org", owner_user_id=advertiser.id
    )
    campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name="rev race campaign",
    )
    rule = create_v2_rule(
        postgis_db_sessionmaker, campaign_id=campaign.id, created_by_user_id=admin.id
    )
    service_create_revision(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        rule_id=rule.id,
        actor_user_id=admin.id,
        effective_from=datetime.now(UTC) + timedelta(hours=1),
    )

    async def attempt(offset_hours: int, rate: str):
        async with postgis_db_sessionmaker() as session:
            try:
                revision, _ = await create_payout_rule_revision(
                    session,
                    campaign_id=campaign.id,
                    rule_id=rule.id,
                    payload=revision_payload(
                        effective_from=datetime.now(UTC) + timedelta(hours=offset_hours),
                        hourly_rate_naira=Decimal(rate),
                        reason=f"race {rate}",
                    ),
                    actor_user_id=admin.id,
                )
                await session.commit()
                return revision.revision_number
            except AppError as exc:
                await session.rollback()
                return exc

    async def race():
        return await asyncio.gather(attempt(2, "1300.00"), attempt(3, "1400.00"))

    outcomes = asyncio.run(race())
    winners = [o for o in outcomes if isinstance(o, int)]
    losers = [o for o in outcomes if isinstance(o, AppError)]
    assert len(winners) == 1, outcomes
    assert winners == [2]
    assert len(losers) == 1
    # The loser gets the stable FND-07-style 409 envelope, never a 500.
    assert losers[0].code == "PAYOUT_RULE_REVISION_CONFLICT"
    assert losers[0].status_code == http_status.HTTP_409_CONFLICT
    assert [
        r.revision_number for r in fetch_revisions(postgis_db_sessionmaker, campaign.id)
    ] == [1, 2]


# --- Money-neutrality (A4) ---------------------------------------------------


def test_v2_recompute_is_identical_after_revisions_exist(
    postgis_db_sessionmaker, settings
) -> None:
    """payout_v2 prices from the frozen rule row only (PR3b): appending a
    revision with different values must not reprice or true-up anything."""
    graph = build_v2_graph(postgis_db_sessionmaker, "rev-neutral")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)

    calculations = fetch_payout_calculations(postgis_db_sessionmaker)
    assert len(calculations) == 1
    assert calculations[0].final_payout == Decimal("600.00")

    service_create_revision(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=graph.rule.id,
        actor_user_id=graph.admin.id,
        hourly_rate_naira=Decimal("9999.00"),
        daily_payable_hours_cap=Decimal("1.00"),
        reason="future v3 values; must not touch v2 money",
    )

    outcome = run_recompute(postgis_db_sessionmaker, settings, graph)
    assert outcome.adjustment_count == 0
    assert outcome.reversal_count == 0
    assert [trip.delta_amount for trip in outcome.trips] == [Decimal("0.00")]

    calculations = fetch_payout_calculations(postgis_db_sessionmaker)
    assert len(calculations) == 1
    assert calculations[0].final_payout == Decimal("600.00")
    entries = fetch_earnings_ledger_entries(postgis_db_sessionmaker)
    assert len(entries) == 1
    assert entries[0].amount == Decimal("600.00")

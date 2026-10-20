"""Daily-rate revision publication serializes and rejects backdated terms."""

import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest
from payout_fixtures import build_offered_graph, create_v4_revision, create_v4_rule
from sqlalchemy import select

from app.core.errors import AppError
from app.models.payout import CampaignPayoutRuleRevision
from app.schemas.payouts import CampaignPayoutV4RevisionCreate
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock
from app.services.payouts.common import validate_currency_code
from app.services.payouts.rules import publish_payout_v4_revision


def payload(effective_from, rate="8000"):
    return CampaignPayoutV4RevisionCreate(
        effective_from=effective_from,
        daily_rate_naira=Decimal(rate),
        daily_target_miles=Decimal("8"),
        reason="synthetic revision",
    )


def test_currency_validation_rejects_non_ascii_letters():
    with pytest.raises(AppError) as error:
        validate_currency_code("???")
    assert error.value.code == "INVALID_CURRENCY"


def test_concurrent_supersedes_serialize_in_revision_order(postgis_db_sessionmaker, settings):
    db = postgis_db_sessionmaker
    graph = build_offered_graph(db, "daily-revision-race")
    rule = create_v4_rule(db, campaign_id=graph.campaign.id, admin_id=graph.admin.id)
    create_v4_revision(db, campaign_id=graph.campaign.id, rule_id=rule.id, admin_id=graph.admin.id)

    async def race():
        locked = asyncio.Event()

        async def publish(index):
            async with db() as session:
                if index == 1:
                    await acquire_campaign_terms_lock(session, graph.campaign.id)
                    locked.set()
                else:
                    await locked.wait()
                now = await database_clock(session)
                revision, _, _ = await publish_payout_v4_revision(
                    session,
                    campaign_id=graph.campaign.id,
                    payload=payload(now + timedelta(hours=index), str(8000 + index)),
                    actor_user_id=graph.admin.id,
                )
                await session.commit()
                return revision.revision_number

        return await asyncio.wait_for(asyncio.gather(publish(1), publish(2)), timeout=15)

    assert asyncio.run(race()) == [2, 3]

    async def revisions():
        async with db() as session:
            return list(
                (
                    await session.scalars(
                        select(CampaignPayoutRuleRevision.revision_number)
                        .where(CampaignPayoutRuleRevision.campaign_id == graph.campaign.id)
                        .order_by(CampaignPayoutRuleRevision.revision_number)
                    )
                ).all()
            )

    assert asyncio.run(revisions()) == [1, 2, 3]


def test_backdated_revision_does_not_write(postgis_db_sessionmaker, settings):
    db = postgis_db_sessionmaker
    graph = build_offered_graph(db, "daily-revision-backdate")

    async def scenario():
        async with db() as session:
            now = await database_clock(session)
            with pytest.raises(AppError) as error:
                await publish_payout_v4_revision(
                    session,
                    campaign_id=graph.campaign.id,
                    payload=payload(now - timedelta(seconds=1)),
                    actor_user_id=graph.admin.id,
                )
            assert error.value.code == "INVALID_PAYOUT_RULE_REVISION"
            assert list((await session.scalars(select(CampaignPayoutRuleRevision))).all()) == []

    asyncio.run(scenario())

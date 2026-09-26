import asyncio
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)

from app.db.base import Base

PREVIOUS = "0090_single_active_advertiser_membership"
CURRENT = "0091_budget_urgent_threshold"

INSERT_EVALUATION = text(
    "INSERT INTO budget_policy_evaluations (id, campaign_id, evaluation_key, state, "
    "campaign_budget_amount, currency, policy_id, policy_revision, policy_source, "
    "budget_basis, billing_fact_source, billing_spend_amount, alert_threshold_amount, "
    "urgent_threshold_amount, pause_threshold_amount, resume_threshold_amount, "
    "alert_applied, pause_applied, resume_allowed, evaluated_at) VALUES (:id, :campaign, "
    ":key, :state, 1000, 'NGN', 'p', 'r1', 'synthetic_test', 'total', 'confirmed_funding', "
    ":spend, 800, :urgent, 1000, 700, true, false, false, now())"
)


@pytest.fixture
def setup_database(monkeypatch):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        upgrade_to(url, PREVIOUS, monkeypatch)
        yield url, engine
    finally:
        asyncio.run(engine.dispose())
        asyncio.run(drop_database(url))


async def _campaign(engine) -> str:
    user, organization, campaign = str(uuid4()), str(uuid4()), str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name, role, status) "
                "VALUES (:id, :email, 'x', 'Advertiser', 'advertiser', 'active')"
            ),
            {"id": user, "email": f"{user}@example.com"},
        )
        await connection.execute(
            text(
                "INSERT INTO advertiser_organizations (id, name, currency, status) "
                "VALUES (:id, 'Company', 'NGN', 'active')"
            ),
            {"id": organization},
        )
        await connection.execute(
            text(
                "INSERT INTO campaigns (id, organization_id, created_by_user_id, name, status, "
                "currency, metadata) VALUES (:id, :organization, :user, 'Budget', 'active', "
                "'NGN', '{}')"
            ),
            {"id": campaign, "organization": organization, "user": user},
        )
    return campaign


async def _insert(engine, campaign: str, *, state: str, spend: int, urgent) -> None:
    statement = INSERT_EVALUATION
    if urgent is None:
        # Also valid before 0091, which has no urgent column yet.
        statement = text(
            str(INSERT_EVALUATION)
            .replace("urgent_threshold_amount, ", "")
            .replace(":urgent, ", "")
        )
    async with engine.begin() as connection:
        await connection.execute(
            statement,
            {
                "id": str(uuid4()),
                "campaign": campaign,
                "key": uuid4().hex,
                "state": state,
                "spend": spend,
                "urgent": urgent,
            },
        )


def test_urgent_level_is_constrained_matches_models_and_blocks_lossy_downgrade(
    setup_database, monkeypatch
) -> None:
    url, engine = setup_database
    campaign = asyncio.run(_campaign(engine))
    # A two-level decision recorded before 0091 stays valid afterwards.
    asyncio.run(_insert(engine, campaign, state="alert_threshold", spend=850, urgent=None))
    upgrade_to(url, CURRENT, monkeypatch)

    async def inspect():
        async with engine.begin() as connection:
            return await connection.run_sync(
                lambda sync: compare_metadata(
                    MigrationContext.configure(sync, opts={"compare_type": True}), Base.metadata
                )
            )

    changes = asyncio.run(inspect())
    assert [change for change in changes if "budget_policy_evaluations" in repr(change)] == []

    invalid = (("urgent_threshold", None), ("urgent_threshold", 1000), ("alert_threshold", 700))
    for state, urgent in invalid:
        with pytest.raises(IntegrityError):
            asyncio.run(_insert(engine, campaign, state=state, spend=960, urgent=urgent))
    # Without urgent decisions the migration round-trips.
    downgrade_to(url, PREVIOUS, monkeypatch)
    upgrade_to(url, CURRENT, monkeypatch)

    # Evaluations are append-only, so a recorded urgent decision blocks the lossy downgrade.
    asyncio.run(_insert(engine, campaign, state="urgent_threshold", spend=960, urgent=950))
    with pytest.raises(RuntimeError, match="0091 downgrade blocked: 1 budget evaluation"):
        downgrade_to(url, PREVIOUS, monkeypatch)

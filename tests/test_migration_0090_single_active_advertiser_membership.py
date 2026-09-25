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

PREVIOUS = "0089_driver_account_setup"
CURRENT = "0090_single_active_advertiser_membership"


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


async def _seed_memberships(engine, statuses: tuple[str, ...]) -> str:
    user_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name, role, status) "
                "VALUES (:id, :email, 'x', 'Advertiser', 'advertiser', 'active')"
            ),
            {"id": user_id, "email": f"{user_id}@example.com"},
        )
        for status in statuses:
            organization_id = str(uuid4())
            await connection.execute(
                text(
                    "INSERT INTO advertiser_organizations (id, name, currency, status) "
                    "VALUES (:id, 'Company', 'NGN', 'active')"
                ),
                {"id": organization_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO organization_memberships (organization_id, user_id, role, status) "
                    "VALUES (:organization_id, :user_id, 'owner', :status)"
                ),
                {"organization_id": organization_id, "user_id": user_id, "status": status},
            )
    return user_id


async def _head(engine) -> str:
    async with engine.connect() as connection:
        return (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one()


def test_existing_conflicting_active_memberships_block_the_upgrade(
    setup_database, monkeypatch
) -> None:
    url, engine = setup_database
    asyncio.run(_seed_memberships(engine, ("active", "active")))

    with pytest.raises(RuntimeError, match="0090 blocked: 1 login"):
        upgrade_to(url, CURRENT, monkeypatch)

    assert asyncio.run(_head(engine)) == PREVIOUS


def test_clean_upgrade_enforces_one_active_membership_and_round_trips(
    setup_database, monkeypatch
) -> None:
    url, engine = setup_database
    user_id = asyncio.run(_seed_memberships(engine, ("active", "disabled", "invited")))
    upgrade_to(url, CURRENT, monkeypatch)

    async def inspect():
        async with engine.begin() as connection:
            changes = await connection.run_sync(
                lambda sync: compare_metadata(
                    MigrationContext.configure(sync, opts={"compare_type": True}), Base.metadata
                )
            )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE organization_memberships SET status = 'active' "
                        "WHERE user_id = :user_id AND status = 'invited'"
                    ),
                    {"user_id": user_id},
                )
        return changes

    changes = asyncio.run(inspect())
    assert [change for change in changes if "organization_memberships" in repr(change)] == []
    downgrade_to(url, PREVIOUS, monkeypatch)
    upgrade_to(url, CURRENT, monkeypatch)
    assert asyncio.run(_head(engine)) == CURRENT

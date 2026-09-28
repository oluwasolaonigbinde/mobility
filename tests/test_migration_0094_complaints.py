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

PREVIOUS = "0093_automatic_payout_approval"
CURRENT = "0094_customer_service_complaints"


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


async def _organization_complaint(engine, **overrides) -> None:
    user, organization = str(uuid4()), str(uuid4())
    values = {
        "id": str(uuid4()),
        "party": "advertiser",
        "user": user,
        "organization": organization,
        "profile": None,
        "category": "account",
        "reference_type": None,
        "status": "open",
        "resolved_at": None,
        "resolved_by": None,
        **overrides,
    }
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
                "INSERT INTO complaints (id, party, raised_by_user_id, driver_profile_id, "
                "advertiser_organization_id, category, reference_type, status, "
                "client_request_id, last_message_at, resolved_at, resolved_by_user_id) "
                "VALUES (:id, :party, :user, :profile, :organization, :category, "
                ":reference_type, :status, gen_random_uuid(), now(), :resolved_at, :resolved_by)"
            ),
            values,
        )
        await connection.execute(
            text(
                "INSERT INTO complaint_messages (complaint_id, author_user_id, author_side, "
                "body, status_after, client_request_id) VALUES (:id, :user, 'complainant', "
                "'Help', 'open', gen_random_uuid())"
            ),
            values,
        )


def test_complaints_match_models_enforce_shape_and_block_lossy_downgrade(
    setup_database, monkeypatch
) -> None:
    url, engine = setup_database
    upgrade_to(url, CURRENT, monkeypatch)

    async def inspect():
        async with engine.begin() as connection:
            return await connection.run_sync(
                lambda sync: compare_metadata(
                    MigrationContext.configure(sync, opts={"compare_type": True}), Base.metadata
                )
            )

    changes = asyncio.run(inspect())
    assert [change for change in changes if "complaint" in repr(change)] == []

    invalid = (
        {"party": "driver"},  # a driver complaint needs a driver profile, not an organization
        {"reference_type": "campaign"},  # a reference type without its record
        {"status": "resolved"},  # resolved without who and when
        {"status": "closed"},
        {"category": "   "},
        {"category": "My Account"},  # lowercase snake case only
    )
    for overrides in invalid:
        with pytest.raises(IntegrityError):
            asyncio.run(_organization_complaint(engine, **overrides))

    # Empty tables round-trip.
    downgrade_to(url, PREVIOUS, monkeypatch)
    upgrade_to(url, CURRENT, monkeypatch)

    asyncio.run(_organization_complaint(engine))
    with pytest.raises(RuntimeError, match="0094 downgrade blocked: 1 complaint rows exist"):
        downgrade_to(url, PREVIOUS, monkeypatch)

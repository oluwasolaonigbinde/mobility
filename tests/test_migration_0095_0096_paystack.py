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

PREVIOUS = "0094_customer_service_complaints"
CHECKOUT = "0095_payment_checkout_intents"
CURRENT = "0097_paystack_edge_case_evidence"


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


def test_paystack_migrations_match_models_round_trip_and_protect_provider_evidence(
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
    assert [
        change
        for change in changes
        if "payment_checkout" in repr(change) or "payout_provider" in repr(change)
    ] == []

    async def insert_provider_event(amount: str) -> None:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO payout_provider_events "
                    "(id, provider, provider_event_id, provider_transfer_reference, "
                    "provider_event_type, provider_reference, amount, currency, outcome, "
                    "provider_occurred_at, "
                    "evidence_fingerprint, received_at) VALUES "
                    "(:id, 'paystack', :event, 'TRF_test', 'transfer.success', "
                    "'cvp_test', :amount, 'NGN', "
                    "'succeeded', now(), :fingerprint, now())"
                ),
                {
                    "id": str(uuid4()),
                    "event": f"transfer.success:{uuid4()}",
                    "amount": amount,
                    "fingerprint": "a" * 64,
                },
            )

    with pytest.raises(IntegrityError):
        asyncio.run(insert_provider_event("0"))
    asyncio.run(insert_provider_event("100.00"))
    with pytest.raises(RuntimeError, match="0096 downgrade blocked: 1 payout provider event"):
        downgrade_to(url, CHECKOUT, monkeypatch)

    async def clear_provider_event() -> None:
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM payout_provider_events"))

    asyncio.run(clear_provider_event())
    downgrade_to(url, CHECKOUT, monkeypatch)
    downgrade_to(url, PREVIOUS, monkeypatch)
    upgrade_to(url, CURRENT, monkeypatch)

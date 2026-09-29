import asyncio
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
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
CURRENT = "0095_invoice_issuer_contact_and_bank"


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


async def _profile(engine, *, bank_account_number: str | None) -> None:
    user = str(uuid4())
    columns = "" if bank_account_number is None else ", bank_account_number"
    values = "" if bank_account_number is None else ", :bank"
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name, role, status) "
                "VALUES (:id, :email, 'x', 'Admin', 'admin', 'active')"
            ),
            {"id": user, "email": f"{user}@example.com"},
        )
        await connection.execute(
            text(
                "INSERT INTO invoice_issuer_profiles (id, legal_name, "
                "tax_identification_number, registered_address, country_code, "
                "invoice_wording, numbering_prefix, verification_status, "
                f"external_input_reference, recorded_by_user_id, recorded_at{columns}) "
                "VALUES (:id, 'Issuer', 'TIN', 'Address', 'NG', 'Wording', 'CV', "
                f"'synthetic', :reference, :user, now(){values})"
            ),
            {
                "id": str(uuid4()),
                "reference": uuid4().hex,
                "user": user,
                "bank": bank_account_number,
            },
        )


def test_issuer_contact_and_bank_columns_match_models_and_block_lossy_downgrade(
    setup_database, monkeypatch
) -> None:
    url, engine = setup_database
    # A profile recorded before 0095 stays valid and leaves the new facts empty.
    asyncio.run(_profile(engine, bank_account_number=None))
    upgrade_to(url, CURRENT, monkeypatch)

    async def inspect():
        async with engine.begin() as connection:
            return await connection.run_sync(
                lambda sync: compare_metadata(
                    MigrationContext.configure(sync, opts={"compare_type": True}), Base.metadata
                )
            )

    changes = asyncio.run(inspect())
    assert [change for change in changes if "invoice_issuer_profiles" in repr(change)] == []

    # Without recorded contact or bank facts the migration round-trips.
    downgrade_to(url, PREVIOUS, monkeypatch)
    upgrade_to(url, CURRENT, monkeypatch)

    # Profiles are append-only, so recorded bank details block the lossy downgrade.
    asyncio.run(_profile(engine, bank_account_number="TEST-ACCOUNT-ONLY"))
    with pytest.raises(RuntimeError, match="0095 downgrade blocked: 1 issuer profile"):
        downgrade_to(url, PREVIOUS, monkeypatch)

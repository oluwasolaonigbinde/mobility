import asyncio

import pytest
from alembic.config import Config
from database_helpers import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    fetch_all,
    upgrade_to,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command


def test_batch2_migration_matches_models_and_refuses_populated_downgrade(monkeypatch):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(url, "0107_audience_sweep_cursor", monkeypatch)
        upgrade_to(url, "head", monkeypatch)
        command.check(Config("alembic.ini"))
        assert asyncio.run(
            fetch_all(
                url,
                "SELECT email, role, status FROM users "
                "WHERE id='c37324b8-dddf-4d83-b923-4975d4569cd9'",
            )
        ) == [("report-automation@cardvert.invalid", "admin", "disabled")]
        assert asyncio.run(
            fetch_all(
                url,
                "SELECT numeric_precision, numeric_scale "
                "FROM information_schema.columns WHERE table_name='budget_policy_evaluations' "
                "AND column_name='urgent_threshold_amount'",
            )
        ) == [(16, 4)]
        command.downgrade(Config("alembic.ini"), "0107_audience_sweep_cursor")
        upgrade_to(url, "head", monkeypatch)

        async def populate():
            engine = create_async_engine(url, poolclass=NullPool)
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "INSERT INTO campaign_enquiries "
                            "(id, company, contact_name, email, phone, brief) VALUES "
                            "(gen_random_uuid(), 'Synthetic brand', 'Synthetic contact', "
                            "'test@example.invalid', '', 'Synthetic test only')"
                        )
                    )
            finally:
                await engine.dispose()

        asyncio.run(populate())
        with pytest.raises(RuntimeError, match="Cannot downgrade populated"):
            command.downgrade(Config("alembic.ini"), "0107_audience_sweep_cursor")
        assert asyncio.run(fetch_all(url, "SELECT count(*) FROM campaign_enquiries")) == [(1,)]
    finally:
        asyncio.run(drop_database(url))

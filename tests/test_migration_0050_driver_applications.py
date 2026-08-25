"""Migration 0050: public applications are additive and downgrade-safe."""

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import create_test_driver_profile, create_test_user
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)

from app.models.driver import DriverOnboardingStatus
from app.models.user import UserRole

PRE_APPLICATION_REVISION = "0049_assignment_activity_flags"
APPLICATION_REVISION = "0050_driver_applications"


def test_application_migration_static_shape_and_head_guard() -> None:
    migration = Path("alembic/versions/0050_driver_applications.py").read_text()
    assert f'revision: str = "{APPLICATION_REVISION}"' in migration
    assert f'down_revision: str | Sequence[str] | None = "{PRE_APPLICATION_REVISION}"' in migration
    assert '"driver_applications"' in migration
    assert '"status_reference_sha256"' in migration
    assert "0050 downgrade blocked: driver application evidence is authoritative" in migration
    assert "backfill" not in migration.lower()


def test_populated_upgrade_downgrade_reupgrade_preserves_application_evidence(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    engine = None
    try:
        upgrade_to(migration_url, PRE_APPLICATION_REVISION, monkeypatch)
        engine = create_async_engine(migration_url, poolclass=NullPool)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        driver = create_test_user(
            sessionmaker,
            email=f"migration-application-driver-{uuid4().hex}@example.com",
            password="migration-password",
            role=UserRole.DRIVER,
        )
        profile = create_test_driver_profile(
            sessionmaker,
            user_id=driver.id,
            onboarding_status=DriverOnboardingStatus.PENDING,
            license_number=None,
            service_city="Lagos",
            country_code="NG",
        )

        upgrade_to(migration_url, "head", monkeypatch)

        async def insert_application() -> None:
            async with sessionmaker() as session:
                await session.execute(
                    text(
                        "INSERT INTO driver_applications "
                        "(user_id,driver_profile_id,status,status_reference_sha256,email,"
                        "full_name,service_city,country_code) VALUES "
                        "(:user_id,:profile_id,'pending',:reference,:email,:full_name,:city,:country)"
                    ),
                    {
                        "user_id": driver.id,
                        "profile_id": profile.id,
                        "reference": "a" * 64,
                        "email": driver.email,
                        "full_name": driver.full_name,
                        "city": "Lagos",
                        "country": "NG",
                    },
                )
                await session.commit()

        asyncio.run(insert_application())
        with pytest.raises(RuntimeError, match="0050 downgrade blocked"):
            downgrade_to(migration_url, PRE_APPLICATION_REVISION, monkeypatch)

        async def delete_application() -> None:
            async with sessionmaker() as session:
                await session.execute(text("DELETE FROM driver_applications"))
                await session.commit()

        asyncio.run(delete_application())
        downgrade_to(migration_url, PRE_APPLICATION_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        if engine is not None:
            asyncio.run(engine.dispose())
        asyncio.run(drop_database(migration_url))

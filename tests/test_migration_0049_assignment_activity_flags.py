"""Migration 0049: activity evidence is durable and downgrade-safe."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
)
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

from app.models.campaign import CampaignStatus
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus

PRE_ACTIVITY_REVISION = "0048_campaign_assignment_offer_lifecycle"


def test_activity_migration_static_shape_and_sqlite_guards() -> None:
    migration = Path(
        "alembic/versions/0049_assignment_activity_flags.py"
    ).read_text()
    assert 'revision: str = "0049_assignment_activity_flags"' in migration
    assert f'down_revision: str | Sequence[str] | None = "{PRE_ACTIVITY_REVISION}"' in migration
    assert "assignment_activity_flags" in migration
    assert "assignment_activity_flag_events" in migration
    assert "assignment_activity_flag_events_append_only_update" in migration
    assert "0049 downgrade blocked: activity flag evidence is authoritative" in migration
    assert 'bind.dialect.name == "sqlite"' in migration


def test_populated_upgrade_downgrade_reupgrade_preserves_guard(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))

    def seed_parent_rows() -> tuple:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        admin = create_test_user(
            sessionmaker,
            email=f"migration-activity-admin-{uuid4().hex}@example.com",
            password="migration-password",
        )
        driver = create_test_user(
            sessionmaker,
            email=f"migration-activity-driver-{uuid4().hex}@example.com",
            password="migration-password",
            role=UserRole.DRIVER,
        )
        organization, _ = create_test_organization(
            sessionmaker, owner_user_id=admin.id
        )
        campaign = create_test_campaign(
            sessionmaker,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            campaign_status=CampaignStatus.DRAFT,
        )
        profile = create_test_driver_profile(
            sessionmaker,
            user_id=driver.id,
            onboarding_status=DriverOnboardingStatus.ACTIVE,
        )
        vehicle = create_test_vehicle(
            sessionmaker,
            driver_profile_id=profile.id,
            vehicle_status=VehicleStatus.ACTIVE,
            plate_number=f"ACT-{uuid4().hex[:8]}",
        )
        assignment = create_test_campaign_assignment(
            sessionmaker,
            campaign_id=campaign.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            assigned_by_user_id=admin.id,
            assignment_status=CampaignAssignmentStatus.ACTIVE,
        )
        return engine, sessionmaker, assignment, campaign, profile, vehicle

    async def insert_evidence(
        sessionmaker,
        assignment,
        campaign,
        profile,
        vehicle,
    ) -> tuple:
        flag_id = uuid4()
        event_id = uuid4()
        now = datetime(2026, 1, 12, tzinfo=UTC)
        async with sessionmaker() as session:
            await session.execute(
                text(
                    "INSERT INTO assignment_activity_flags "
                    "(id,assignment_id,campaign_id,driver_profile_id,vehicle_id,"
                    "flag_type,status,window_start,window_end,threshold_seconds,"
                    "observed_seconds,first_detected_at,last_evaluated_at,evidence) "
                    "VALUES (:id,:assignment_id,:campaign_id,:profile_id,:vehicle_id,"
                    "'inactivity','open',:window_start,:window_end,604800,0,"
                    ":now,:now,'{}'::jsonb)"
                ),
                {
                    "id": flag_id,
                    "assignment_id": assignment.id,
                    "campaign_id": campaign.id,
                    "profile_id": profile.id,
                    "vehicle_id": vehicle.id,
                    "window_start": datetime(2026, 1, 5, tzinfo=UTC),
                    "window_end": datetime(2026, 1, 12, tzinfo=UTC),
                    "now": now,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO assignment_activity_flag_events "
                    "(id,flag_id,assignment_id,sequence_number,event_type,occurred_at,"
                    "observed_seconds,evidence) VALUES "
                    "(:id,:flag_id,:assignment_id,1,'opened',:now,0,'{}'::jsonb)"
                ),
                {
                    "id": event_id,
                    "flag_id": flag_id,
                    "assignment_id": assignment.id,
                    "now": now,
                },
            )
            await session.commit()
        return flag_id, event_id

    async def delete_evidence(sessionmaker) -> None:
        async with sessionmaker() as session:
            await session.execute(
                text(
                    "TRUNCATE TABLE assignment_activity_flag_events, "
                    "assignment_activity_flags"
                )
            )
            await session.commit()

    try:
        upgrade_to(migration_url, PRE_ACTIVITY_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        engine, sessionmaker, assignment, campaign, profile, vehicle = seed_parent_rows()
        _flag_id, _ = asyncio.run(
            insert_evidence(sessionmaker, assignment, campaign, profile, vehicle)
        )

        with pytest.raises(RuntimeError, match="0049 downgrade blocked"):
            downgrade_to(migration_url, PRE_ACTIVITY_REVISION, monkeypatch)

        asyncio.run(delete_evidence(sessionmaker))
        asyncio.run(engine.dispose())
        downgrade_to(migration_url, PRE_ACTIVITY_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.audit import AuditEvent
from app.models.campaign import (
    Campaign,
    CampaignCreative,
    CampaignStatus,
    CreativePlacement,
    CreativeStatus,
    CreativeType,
)
from app.models.campaign_assignment import (
    CampaignActivationEvent,
    CampaignAssignment,
    CampaignAssignmentStatus,
)
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.organization import (
    AdvertiserOrganization,
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
    OrganizationStatus,
)
from app.models.trip import LocationPing, LocationPingBatch, TripSession, TripSessionStatus
from app.models.user import User, UserRole, UserStatus
from app.models.vehicle import Vehicle, VehicleStatus, VehicleType
from app.services.users import normalize_email
from app.services.vehicles import normalize_plate_number


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_name="mobility-adtech-api",
        environment="test",
        database_url=None,
        redis_url=None,
        backend_cors_origins=["http://localhost:3000"],
        jwt_secret_key="test-secret-key-at-least-32-bytes",
        access_token_expire_minutes=60,
    )


@pytest.fixture
def client(settings: Settings) -> Generator[TestClient, None, None]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def db_sessionmaker(tmp_path: Path) -> Generator[async_sessionmaker[AsyncSession], None, None]:
    database_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    async def setup_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def teardown_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(setup_database())
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    yield sessionmaker
    asyncio.run(teardown_database())


@pytest.fixture
def postgis_db_sessionmaker() -> Generator[async_sessionmaker[AsyncSession], None, None]:
    database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if database_url is None or not database_url.startswith("postgresql+asyncpg://"):
        pytest.skip("PostGIS test database is not configured")

    schema_name = f"test_{uuid4().hex}"
    engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": f"{schema_name},public"}},
        execution_options={"schema_translate_map": {None: schema_name}},
        poolclass=NullPool,
    )

    async def setup_database() -> None:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            await connection.execute(text(f"CREATE SCHEMA {schema_name}"))
            await connection.execute(text(f"SET search_path TO {schema_name}, public"))
            await connection.run_sync(Base.metadata.create_all)

    async def teardown_database() -> None:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
        await engine.dispose()

    asyncio.run(setup_database())
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    yield sessionmaker
    asyncio.run(teardown_database())


@pytest.fixture
def db_client(
    settings: Settings,
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> Generator[TestClient, None, None]:
    app = create_app(settings)

    async def override_get_session():
        async with db_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def postgis_db_client(
    settings: Settings,
    postgis_db_sessionmaker: async_sessionmaker[AsyncSession],
) -> Generator[TestClient, None, None]:
    app = create_app(settings)

    async def override_get_session():
        async with postgis_db_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client


def create_test_user(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    email: str,
    password: str = "long-secure-password",
    full_name: str = "Test User",
    role: UserRole = UserRole.ADMIN,
    user_status: UserStatus = UserStatus.ACTIVE,
    phone: str | None = None,
) -> User:
    async def create() -> User:
        async with db_sessionmaker() as session:
            user = User(
                email=normalize_email(email),
                password_hash=hash_password(password),
                full_name=full_name,
                phone=phone,
                role=role,
                status=user_status,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return asyncio.run(create())


def create_test_organization(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    name: str = "Acme Ads",
    billing_email: str | None = "billing@acme.test",
    country_code: str | None = "NG",
    currency: str = "NGN",
    organization_status: OrganizationStatus = OrganizationStatus.ACTIVE,
    owner_user_id: UUID | None = None,
    membership_role: MembershipRole = MembershipRole.OWNER,
    membership_status: MembershipStatus = MembershipStatus.ACTIVE,
) -> tuple[AdvertiserOrganization, OrganizationMembership | None]:
    async def create() -> tuple[AdvertiserOrganization, OrganizationMembership | None]:
        async with db_sessionmaker() as session:
            organization = AdvertiserOrganization(
                name=name,
                billing_email=billing_email,
                country_code=country_code,
                currency=currency,
                status=organization_status,
            )
            session.add(organization)
            await session.flush()

            membership = None
            if owner_user_id is not None:
                membership = OrganizationMembership(
                    organization_id=organization.id,
                    user_id=owner_user_id,
                    role=membership_role,
                    status=membership_status,
                )
                session.add(membership)

            await session.commit()
            await session.refresh(organization)
            if membership is not None:
                await session.refresh(membership)
            return organization, membership

    return asyncio.run(create())


def create_test_driver_profile(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    onboarding_status: DriverOnboardingStatus = DriverOnboardingStatus.PENDING,
    license_number: str | None = "DRV-123",
    service_city: str | None = "Lagos",
    country_code: str | None = "NG",
    metadata: dict | None = None,
) -> DriverProfile:
    async def create() -> DriverProfile:
        async with db_sessionmaker() as session:
            profile = DriverProfile(
                user_id=user_id,
                onboarding_status=onboarding_status,
                license_number=license_number,
                service_city=service_city,
                country_code=country_code,
                profile_metadata=metadata or {},
            )
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            return profile

    return asyncio.run(create())


def create_test_vehicle(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    driver_profile_id: UUID,
    plate_number: str = "ABC-123",
    plate_country_code: str = "NG",
    vehicle_type: VehicleType = VehicleType.CAR,
    make: str | None = "Toyota",
    model: str | None = "Corolla",
    year: int | None = 2018,
    color: str | None = "White",
    vehicle_status: VehicleStatus = VehicleStatus.PENDING,
    metadata: dict | None = None,
) -> Vehicle:
    async def create() -> Vehicle:
        async with db_sessionmaker() as session:
            vehicle = Vehicle(
                driver_profile_id=driver_profile_id,
                plate_number=plate_number,
                plate_number_normalized=normalize_plate_number(plate_number),
                plate_country_code=plate_country_code.upper(),
                vehicle_type=vehicle_type,
                make=make,
                model=model,
                year=year,
                color=color,
                status=vehicle_status,
                vehicle_metadata=metadata or {},
            )
            session.add(vehicle)
            await session.commit()
            await session.refresh(vehicle)
            return vehicle

    return asyncio.run(create())


def create_test_campaign(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    organization_id: UUID,
    created_by_user_id: UUID,
    name: str = "Launch Campaign",
    description: str | None = "Shared ride vehicle campaign",
    campaign_status: CampaignStatus = CampaignStatus.DRAFT,
    start_at=None,
    end_at=None,
    budget_amount=None,
    daily_budget_amount=None,
    currency: str = "NGN",
    metadata: dict | None = None,
) -> Campaign:
    async def create() -> Campaign:
        async with db_sessionmaker() as session:
            campaign = Campaign(
                organization_id=organization_id,
                created_by_user_id=created_by_user_id,
                name=name,
                description=description,
                status=campaign_status,
                start_at=start_at,
                end_at=end_at,
                budget_amount=budget_amount,
                daily_budget_amount=daily_budget_amount,
                currency=currency,
                campaign_metadata=metadata or {},
            )
            session.add(campaign)
            await session.commit()
            await session.refresh(campaign)
            return campaign

    return asyncio.run(create())


def create_test_campaign_assignment(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    campaign_id: UUID,
    driver_profile_id: UUID,
    vehicle_id: UUID,
    assigned_by_user_id: UUID,
    assignment_status: CampaignAssignmentStatus = CampaignAssignmentStatus.OFFERED,
    offered_at=None,
    accepted_at=None,
    activated_at=None,
    deactivated_at=None,
    cancelled_at=None,
    completed_at=None,
    notes: str | None = None,
    metadata: dict | None = None,
) -> CampaignAssignment:
    offered_at = offered_at or datetime.now(UTC)

    async def create() -> CampaignAssignment:
        async with db_sessionmaker() as session:
            assignment = CampaignAssignment(
                campaign_id=campaign_id,
                driver_profile_id=driver_profile_id,
                vehicle_id=vehicle_id,
                assigned_by_user_id=assigned_by_user_id,
                status=assignment_status,
                offered_at=offered_at,
                accepted_at=accepted_at,
                activated_at=activated_at,
                deactivated_at=deactivated_at,
                cancelled_at=cancelled_at,
                completed_at=completed_at,
                notes=notes,
                assignment_metadata=metadata or {},
            )
            session.add(assignment)
            await session.commit()
            await session.refresh(assignment)
            return assignment

    return asyncio.run(create())


def create_test_trip_session(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    assignment_id: UUID,
    campaign_id: UUID,
    driver_profile_id: UUID,
    vehicle_id: UUID,
    started_by_user_id: UUID,
    trip_status: TripSessionStatus = TripSessionStatus.ACTIVE,
    started_at=None,
    ended_at=None,
    end_reason: str | None = None,
    metadata: dict | None = None,
) -> TripSession:
    started_at = started_at or datetime.now(UTC)

    async def create() -> TripSession:
        async with db_sessionmaker() as session:
            trip = TripSession(
                assignment_id=assignment_id,
                campaign_id=campaign_id,
                driver_profile_id=driver_profile_id,
                vehicle_id=vehicle_id,
                started_by_user_id=started_by_user_id,
                status=trip_status,
                started_at=started_at,
                ended_at=ended_at,
                end_reason=end_reason,
                trip_metadata=metadata or {},
            )
            session.add(trip)
            await session.commit()
            await session.refresh(trip)
            return trip

    return asyncio.run(create())


def create_test_campaign_creative(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    campaign_id: UUID,
    name: str = "Exterior Wrap",
    creative_type: CreativeType = CreativeType.IMAGE,
    placement: CreativePlacement = CreativePlacement.VEHICLE_EXTERIOR,
    asset_url: str | None = "https://example.com/wrap.png",
    mime_type: str | None = "image/png",
    width_px: int | None = 1200,
    height_px: int | None = 800,
    duration_seconds: int | None = None,
    checksum: str | None = "sha256-placeholder",
    creative_status: CreativeStatus = CreativeStatus.DRAFT,
    metadata: dict | None = None,
) -> CampaignCreative:
    async def create() -> CampaignCreative:
        async with db_sessionmaker() as session:
            creative = CampaignCreative(
                campaign_id=campaign_id,
                name=name,
                creative_type=creative_type,
                placement=placement,
                asset_url=asset_url,
                mime_type=mime_type,
                width_px=width_px,
                height_px=height_px,
                duration_seconds=duration_seconds,
                checksum=checksum,
                status=creative_status,
                creative_metadata=metadata or {},
            )
            session.add(creative)
            await session.commit()
            await session.refresh(creative)
            return creative

    return asyncio.run(create())


def fetch_user_by_email(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    email: str,
) -> User | None:
    async def fetch() -> User | None:
        async with db_sessionmaker() as session:
            result = await session.execute(
                select(User).where(User.email == normalize_email(email))
            )
            return result.scalar_one_or_none()

    return asyncio.run(fetch())


def fetch_audit_events(db_sessionmaker: async_sessionmaker[AsyncSession]) -> list[AuditEvent]:
    async def fetch() -> list[AuditEvent]:
        async with db_sessionmaker() as session:
            result = await session.execute(select(AuditEvent).order_by(AuditEvent.created_at))
            return list(result.scalars().all())

    return asyncio.run(fetch())


def fetch_activation_events(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> list[CampaignActivationEvent]:
    async def fetch() -> list[CampaignActivationEvent]:
        async with db_sessionmaker() as session:
            result = await session.execute(
                select(CampaignActivationEvent).order_by(
                    CampaignActivationEvent.occurred_at,
                    CampaignActivationEvent.id,
                )
            )
            return list(result.scalars().all())

    return asyncio.run(fetch())


def fetch_trip_sessions(db_sessionmaker: async_sessionmaker[AsyncSession]) -> list[TripSession]:
    async def fetch() -> list[TripSession]:
        async with db_sessionmaker() as session:
            result = await session.execute(select(TripSession).order_by(TripSession.created_at))
            return list(result.scalars().all())

    return asyncio.run(fetch())


def fetch_location_ping_batches(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> list[LocationPingBatch]:
    async def fetch() -> list[LocationPingBatch]:
        async with db_sessionmaker() as session:
            result = await session.execute(
                select(LocationPingBatch).order_by(LocationPingBatch.created_at)
            )
            return list(result.scalars().all())

    return asyncio.run(fetch())


def fetch_location_pings(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> list[LocationPing]:
    async def fetch() -> list[LocationPing]:
        async with db_sessionmaker() as session:
            result = await session.execute(select(LocationPing).order_by(LocationPing.recorded_at))
            return list(result.scalars().all())

    return asyncio.run(fetch())


def auth_headers(
    client: TestClient,
    email: str,
    password: str = "long-secure-password",
) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

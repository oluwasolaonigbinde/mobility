import asyncio
from collections.abc import Generator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.audit import AuditEvent
from app.models.organization import (
    AdvertiserOrganization,
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
    OrganizationStatus,
)
from app.models.user import User, UserRole, UserStatus
from app.services.users import normalize_email


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


def auth_headers(
    client: TestClient,
    email: str,
    password: str = "long-secure-password",
) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

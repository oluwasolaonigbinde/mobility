import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.db.session import get_engine
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
    CampaignActivationEventType,
    CampaignAssignment,
    CampaignAssignmentStatus,
)
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.impression import (
    ImpressionEstimate,
    TrafficDensityProfile,
    TrafficDensityProfileStatus,
)
from app.models.organization import (
    AdvertiserOrganization,
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
    OrganizationStatus,
)
from app.models.payout import (
    CampaignPayoutRule,
    CampaignPayoutRuleStatus,
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    PayoutCalculation,
)
from app.models.trip import (
    LocationPing,
    LocationPingBatch,
    TripSealReason,
    TripSession,
    TripSessionStatus,
)
from app.models.trip_analytics import TripAnalytics
from app.models.user import User, UserRole, UserStatus
from app.models.vehicle import Vehicle, VehicleStatus, VehicleType
from app.schemas.impressions import TrafficDensityProfileCreate
from app.schemas.trips import LocationPingBatchCreate, LocationPingCreate
from app.seeds.rich import F7_DRIVER_PASSWORDS, F7_SEED_VERSION, RichSeedResult, build_rich_seed
from app.services.campaign_zones import geometry_expression, validate_geometry_with_postgis
from app.services.impressions import create_traffic_density_profile, estimate_trip_impressions
from app.services.payouts import calculate_trip_payout
from app.services.trip_analytics import recompute_trip_analytics
from app.services.trips import payload_hash, point_value
from app.services.users import normalize_email, validate_password_length
from app.services.vehicles import normalize_plate_number

SEED_VERSION = "slice_12_v1"
DEMO_BBOX = "3.35,6.43,3.47,6.56"
DEMO_PASSWORDS = {
    "admin@demo.mobility.local": "DemoAdmin12345!",
    "advertiser@demo.mobility.local": "DemoAdvertiser12345!",
    "viewer@demo.mobility.local": "DemoViewer12345!",
    "driver@demo.mobility.local": "DemoDriver12345!",
}
LOCAL_ENVIRONMENTS = {"local", "dev", "development", "test", "testing"}
PRODUCTION_ENVIRONMENTS = {"prod", "production", "staging"}


@dataclass(frozen=True)
class DemoGraph:
    admin: User
    advertiser: User
    viewer: User
    driver: User
    organization: AdvertiserOrganization
    driver_profile: DriverProfile
    vehicle: Vehicle
    campaign: Campaign
    creative: CampaignCreative
    assignment: CampaignAssignment
    trips: list[TripSession]
    traffic_profile: TrafficDensityProfile
    rich: RichSeedResult


def demo_metadata(**extra: Any) -> dict[str, Any]:
    return {"demo": True, "seed_version": SEED_VERSION, **extra}


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_seed_allowed(settings: Settings) -> None:
    environment = settings.environment.strip().lower()
    if environment in PRODUCTION_ENVIRONMENTS:
        raise AppError(
            "DEMO_SEED_DISALLOWED",
            "Demo seed is not allowed in production-like environments.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"environment": settings.environment},
        )
    if environment not in LOCAL_ENVIRONMENTS and not settings.allow_demo_seed:
        raise AppError(
            "DEMO_SEED_DISALLOWED",
            "Set ALLOW_DEMO_SEED=true to run demo seed outside local/test environments.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"environment": settings.environment},
        )
    if environment != "test" and not settings.allow_demo_seed:
        raise AppError(
            "DEMO_SEED_NOT_CONFIRMED",
            "Set ALLOW_DEMO_SEED=true before running the local demo seed.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"environment": settings.environment},
        )
    if not settings.database_url:
        raise AppError(
            "DATABASE_URL_REQUIRED",
            "DATABASE_URL must be configured before running the demo seed.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


async def ensure_database_ready(session: AsyncSession) -> None:
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        raise AppError(
            "POSTGIS_REQUIRED",
            "Demo seed requires PostgreSQL/PostGIS.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    version = await session.scalar(text("SELECT version_num FROM alembic_version"))
    required = required_migration_head()
    if version != required:
        raise AppError(
            "MIGRATION_HEAD_REQUIRED",
            "Run alembic upgrade head before the demo seed.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"current": version, "required": required},
        )


def required_migration_head() -> str:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError("Alembic migration head is missing or ambiguous")
    return head


async def upsert_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    role: UserRole,
    settings: Settings,
) -> User:
    validate_password_length(password, settings)
    normalized_email = normalize_email(email)
    user = await session.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        user = User(
            email=normalized_email,
            password_hash=hash_password(password),
            full_name=full_name,
            phone=None,
            role=role.value,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
    elif user.role != role.value:
        raise AppError(
            "DEMO_USER_CONFLICT",
            "Existing demo user has an incompatible role.",
            status_code=status.HTTP_409_CONFLICT,
            details={
                "email": normalized_email,
                "expected_role": role.value,
                "actual_role": user.role,
            },
        )
    else:
        user.full_name = full_name
        user.status = UserStatus.ACTIVE.value
        user.password_hash = hash_password(password)
    # Seeded credentials are documented and used by e2e; forcing their first
    # login through password rotation would make the repeatable demo unusable.
    if hasattr(User, "must_change_password"):
        user.must_change_password = False
    await session.flush()
    await session.refresh(user)
    return user


async def upsert_organization(session: AsyncSession) -> AdvertiserOrganization:
    organization = await session.scalar(
        select(AdvertiserOrganization).where(
            AdvertiserOrganization.billing_email == "billing@demo.mobility.local"
        )
    )
    if organization is None:
        organization = AdvertiserOrganization(
            name="Demo Advertiser",
            billing_email="billing@demo.mobility.local",
            country_code="NG",
            currency="NGN",
            status=OrganizationStatus.ACTIVE.value,
        )
        session.add(organization)
    else:
        organization.name = "Demo Advertiser"
        organization.billing_email = "billing@demo.mobility.local"
        organization.country_code = "NG"
        organization.currency = "NGN"
        organization.status = OrganizationStatus.ACTIVE.value
    await session.flush()
    await session.refresh(organization)
    return organization


async def upsert_membership(
    session: AsyncSession,
    *,
    organization: AdvertiserOrganization,
    user: User,
    role: MembershipRole,
) -> OrganizationMembership:
    membership = await session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == user.id,
        )
    )
    if membership is None:
        membership = OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role.value,
            status=MembershipStatus.ACTIVE.value,
        )
        session.add(membership)
    else:
        membership.role = role.value
        membership.status = MembershipStatus.ACTIVE.value
    await session.flush()
    await session.refresh(membership)
    return membership


async def upsert_driver_profile(session: AsyncSession, *, driver: User) -> DriverProfile:
    profile = await session.scalar(select(DriverProfile).where(DriverProfile.user_id == driver.id))
    if profile is None:
        profile = DriverProfile(
            user_id=driver.id,
            onboarding_status=DriverOnboardingStatus.ACTIVE.value,
            license_number="DRV-DEMO-001",
            service_city="Lagos",
            country_code="NG",
            profile_metadata=demo_metadata(persona="demo_driver"),
        )
        session.add(profile)
    else:
        profile.onboarding_status = DriverOnboardingStatus.ACTIVE.value
        profile.license_number = "DRV-DEMO-001"
        profile.service_city = "Lagos"
        profile.country_code = "NG"
        profile.profile_metadata = demo_metadata(persona="demo_driver")
    await session.flush()
    await session.refresh(profile)
    return profile


async def upsert_vehicle(session: AsyncSession, *, profile: DriverProfile) -> Vehicle:
    normalized_plate = normalize_plate_number("DEMO-001")
    vehicle = await session.scalar(
        select(Vehicle).where(
            Vehicle.plate_country_code == "NG",
            Vehicle.plate_number_normalized == normalized_plate,
        )
    )
    if vehicle is None:
        vehicle = Vehicle(
            driver_profile_id=profile.id,
            plate_number="DEMO-001",
            plate_number_normalized=normalized_plate,
            plate_country_code="NG",
            vehicle_type=VehicleType.CAR.value,
            make="Toyota",
            model="Corolla",
            year=2021,
            color="White",
            status=VehicleStatus.ACTIVE.value,
            vehicle_metadata=demo_metadata(wrap_ready=True),
        )
        session.add(vehicle)
    else:
        if vehicle.driver_profile_id != profile.id:
            raise AppError(
                "DEMO_VEHICLE_CONFLICT",
                "Existing demo vehicle belongs to another driver profile.",
                status_code=status.HTTP_409_CONFLICT,
            )
        vehicle.plate_number = "DEMO-001"
        vehicle.vehicle_type = VehicleType.CAR.value
        vehicle.make = "Toyota"
        vehicle.model = "Corolla"
        vehicle.year = 2021
        vehicle.color = "White"
        vehicle.status = VehicleStatus.ACTIVE.value
        vehicle.vehicle_metadata = demo_metadata(wrap_ready=True)
    await session.flush()
    await session.refresh(vehicle)
    return vehicle


async def upsert_campaign(
    session: AsyncSession,
    *,
    organization: AdvertiserOrganization,
    advertiser: User,
) -> Campaign:
    now = utc_now()
    campaign = await session.scalar(
        select(Campaign).where(
            Campaign.organization_id == organization.id,
            Campaign.name == "Demo Lagos Mobility Campaign",
        )
    )
    values = {
        "created_by_user_id": advertiser.id,
        "description": (
            "A citywide vehicle advertising campaign reaching commuters "
            "across high-traffic routes in Lagos."
        ),
        "status": CampaignStatus.ACTIVE.value,
        "start_at": now - timedelta(days=3650),
        "end_at": now + timedelta(days=3650),
        "budget_amount": Decimal("2500000.00"),
        "daily_budget_amount": Decimal("150000.00"),
        "currency": "NGN",
        "campaign_metadata": demo_metadata(frontend_contract="slice_12_demo"),
    }
    if campaign is None:
        campaign = Campaign(
            organization_id=organization.id,
            name="Demo Lagos Mobility Campaign",
            **values,
        )
        session.add(campaign)
    else:
        for field, value in values.items():
            setattr(campaign, field, value)
    await session.flush()
    await session.refresh(campaign)
    return campaign


async def upsert_creative(session: AsyncSession, *, campaign: Campaign) -> CampaignCreative:
    creative = await session.scalar(
        select(CampaignCreative).where(
            CampaignCreative.campaign_id == campaign.id,
            CampaignCreative.name == "Demo Exterior Wrap",
        )
    )
    values = {
        "creative_type": CreativeType.IMAGE.value,
        "placement": CreativePlacement.VEHICLE_EXTERIOR.value,
        "asset_url": "https://example.com/demo-mobility-wrap.png",
        "mime_type": "image/png",
        "width_px": 1600,
        "height_px": 900,
        "duration_seconds": None,
        "checksum": "sha256-demo-placeholder",
        "status": CreativeStatus.READY.value,
        "creative_metadata": demo_metadata(asset_note="placeholder_url_no_binary_upload"),
    }
    if creative is None:
        creative = CampaignCreative(campaign_id=campaign.id, name="Demo Exterior Wrap", **values)
        session.add(creative)
    else:
        for field, value in values.items():
            setattr(creative, field, value)
    await session.flush()
    await session.refresh(creative)
    return creative


def zone_geometries() -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (
            "Demo Lagos Target Zone",
            CampaignZoneType.TARGET.value,
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [3.365, 6.445],
                        [3.445, 6.445],
                        [3.445, 6.535],
                        [3.365, 6.535],
                        [3.365, 6.445],
                    ]
                ],
            },
        ),
        (
            "Demo Lagos Bonus Zone",
            CampaignZoneType.BONUS.value,
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [3.385, 6.465],
                        [3.425, 6.465],
                        [3.425, 6.515],
                        [3.385, 6.515],
                        [3.385, 6.465],
                    ]
                ],
            },
        ),
        (
            "Demo Lagos Exclusion Zone",
            CampaignZoneType.EXCLUSION.value,
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [3.455, 6.540],
                        [3.465, 6.540],
                        [3.465, 6.550],
                        [3.455, 6.550],
                        [3.455, 6.540],
                    ]
                ],
            },
        ),
    ]


async def upsert_zones(
    session: AsyncSession,
    *,
    campaign: Campaign,
    advertiser: User,
    settings: Settings,
    zone_specs: list[tuple[str, str, dict[str, Any]]] | None = None,
) -> list[CampaignZone]:
    zones = []
    for name, zone_type, geometry in zone_specs or zone_geometries():
        validated = await validate_geometry_with_postgis(session, geometry, settings)
        zone = await session.scalar(
            select(CampaignZone).where(
                CampaignZone.campaign_id == campaign.id,
                CampaignZone.name == name,
            )
        )
        values = {
            "created_by_user_id": advertiser.id,
            "description": f"Local demo {zone_type} zone in Lagos.",
            "zone_type": zone_type,
            "geom": geometry_expression(validated.geojson_text),
            "zone_metadata": demo_metadata(area_sq_m=str(validated.area_sq_m)),
        }
        if zone is None:
            zone = CampaignZone(campaign_id=campaign.id, name=name, **values)
            session.add(zone)
        else:
            for field, value in values.items():
                setattr(zone, field, value)
        await session.flush()
        await session.refresh(zone)
        zones.append(zone)
    return zones


async def upsert_assignment(
    session: AsyncSession,
    *,
    campaign: Campaign,
    profile: DriverProfile,
    vehicle: Vehicle,
    admin: User,
    driver: User,
) -> CampaignAssignment:
    now = utc_now()
    assignment = await session.scalar(
        select(CampaignAssignment).where(
            CampaignAssignment.campaign_id == campaign.id,
            CampaignAssignment.vehicle_id == vehicle.id,
            CampaignAssignment.driver_profile_id == profile.id,
        )
    )
    if assignment is None:
        assignment = CampaignAssignment(
            campaign_id=campaign.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            assigned_by_user_id=admin.id,
            status=CampaignAssignmentStatus.ACTIVE.value,
            offered_at=now - timedelta(days=7),
            accepted_at=now - timedelta(days=7, minutes=-5),
            activated_at=now - timedelta(days=6),
            notes="Local demo assignment.",
            assignment_metadata=demo_metadata(),
        )
        session.add(assignment)
        await session.flush()
    else:
        assignment.status = CampaignAssignmentStatus.ACTIVE.value
        assignment.assigned_by_user_id = admin.id
        assignment.offered_at = assignment.offered_at or now - timedelta(days=7)
        assignment.accepted_at = assignment.accepted_at or now - timedelta(days=7, minutes=-5)
        assignment.activated_at = assignment.activated_at or now - timedelta(days=6)
        assignment.cancelled_at = None
        assignment.completed_at = None
        assignment.notes = "Local demo assignment."
        assignment.assignment_metadata = demo_metadata()
        await session.flush()

    await ensure_activation_event(
        session,
        assignment=assignment,
        actor_user_id=admin.id,
        event_type=CampaignActivationEventType.ASSIGNED,
        previous_status=None,
        new_status=CampaignAssignmentStatus.OFFERED.value,
        occurred_at=assignment.offered_at,
    )
    await ensure_activation_event(
        session,
        assignment=assignment,
        actor_user_id=driver.id,
        event_type=CampaignActivationEventType.ACCEPTED,
        previous_status=CampaignAssignmentStatus.OFFERED.value,
        new_status=CampaignAssignmentStatus.ACCEPTED.value,
        occurred_at=assignment.accepted_at or assignment.offered_at,
    )
    await ensure_activation_event(
        session,
        assignment=assignment,
        actor_user_id=driver.id,
        event_type=CampaignActivationEventType.ACTIVATED,
        previous_status=CampaignAssignmentStatus.ACCEPTED.value,
        new_status=CampaignAssignmentStatus.ACTIVE.value,
        occurred_at=assignment.activated_at or assignment.offered_at,
    )
    await session.refresh(assignment)
    return assignment


async def ensure_activation_event(
    session: AsyncSession,
    *,
    assignment: CampaignAssignment,
    actor_user_id: UUID,
    event_type: CampaignActivationEventType,
    previous_status: str | None,
    new_status: str,
    occurred_at: datetime | None,
) -> None:
    existing = await session.scalar(
        select(CampaignActivationEvent).where(
            CampaignActivationEvent.assignment_id == assignment.id,
            CampaignActivationEvent.event_type == event_type.value,
        )
    )
    if existing is not None:
        # Lifecycle evidence is append-only after migration 0048. A seed rerun
        # recognizes the existing deterministic event and never rewrites it.
        return
    session.add(
        CampaignActivationEvent(
            assignment_id=assignment.id,
            actor_user_id=actor_user_id,
            event_type=event_type.value,
            previous_status=previous_status,
            new_status=new_status,
            occurred_at=occurred_at or utc_now(),
            event_metadata=demo_metadata(),
        )
    )
    await session.flush()


def trip_specs(now: datetime) -> list[tuple[str, datetime, list[tuple[float, float]]]]:
    return [
        (
            "demo-trip-0",
            now.replace(hour=7, minute=40, second=0, microsecond=0) - timedelta(days=6),
            [
                (6.4720, 3.3610),
                (6.4800, 3.3740),
                (6.4910, 3.3870),
                (6.5030, 3.3990),
                (6.5140, 3.4120),
                (6.5260, 3.4250),
            ],
        ),
        (
            "demo-trip-00",
            now.replace(hour=16, minute=20, second=0, microsecond=0) - timedelta(days=4),
            [
                (6.5310, 3.3710),
                (6.5200, 3.3830),
                (6.5070, 3.3950),
                (6.4930, 3.4080),
                (6.4790, 3.4210),
                (6.4640, 3.4350),
            ],
        ),
        (
            "demo-trip-1",
            now.replace(hour=8, minute=15, second=0, microsecond=0) - timedelta(days=2),
            [
                (6.4550, 3.3700),
                (6.4630, 3.3820),
                (6.4740, 3.3950),
                (6.4880, 3.4070),
                (6.5010, 3.4180),
                (6.5140, 3.4320),
            ],
        ),
        (
            "demo-trip-2",
            now.replace(hour=17, minute=30, second=0, microsecond=0) - timedelta(days=1),
            [
                (6.4480, 3.3720),
                (6.4590, 3.3860),
                (6.4710, 3.3980),
                (6.4860, 3.4100),
                (6.4980, 3.4210),
                (6.5220, 3.4380),
            ],
        ),
    ]


def palmpay_trip_specs(
    now: datetime,
) -> list[tuple[str, datetime, list[tuple[float, float]]]]:
    return [
        (
            "palmpay-wuse-trip-1",
            now.replace(hour=7, minute=45, second=0, microsecond=0) - timedelta(days=3),
            [
                (9.0465, 7.4550),
                (9.0550, 7.4620),
                (9.0645, 7.4685),
                (9.0740, 7.4740),
                (9.0830, 7.4810),
                (9.0910, 7.4880),
            ],
        ),
        (
            "palmpay-wuse-trip-2",
            now.replace(hour=13, minute=10, second=0, microsecond=0) - timedelta(days=2),
            [
                (9.0910, 7.4520),
                (9.0830, 7.4590),
                (9.0750, 7.4660),
                (9.0660, 7.4730),
                (9.0570, 7.4810),
                (9.0490, 7.4900),
            ],
        ),
        (
            "palmpay-wuse-trip-3",
            now.replace(hour=17, minute=20, second=0, microsecond=0) - timedelta(days=1),
            [
                (9.0500, 7.4900),
                (9.0580, 7.4820),
                (9.0670, 7.4750),
                (9.0760, 7.4680),
                (9.0850, 7.4610),
                (9.0930, 7.4540),
            ],
        ),
    ]


def palmpay_market_trip_specs(
    now: datetime,
) -> list[tuple[str, datetime, list[tuple[float, float]]]]:
    return [
        (
            "demo-story-palmpay-market-1",
            now.replace(hour=8, minute=20, second=0, microsecond=0) - timedelta(days=10),
            [
                (6.6010, 3.3510),
                (6.5840, 3.3660),
                (6.5670, 3.3810),
                (6.5500, 3.3970),
                (6.5330, 3.4130),
                (6.5160, 3.4290),
            ],
        ),
        (
            "demo-story-palmpay-market-2",
            now.replace(hour=13, minute=40, second=0, microsecond=0) - timedelta(days=6),
            [
                (6.5160, 3.4290),
                (6.5310, 3.4160),
                (6.5470, 3.4030),
                (6.5630, 3.3900),
                (6.5790, 3.3770),
                (6.5950, 3.3640),
            ],
        ),
        (
            "demo-story-palmpay-market-3",
            now.replace(hour=17, minute=15, second=0, microsecond=0) - timedelta(days=2),
            [
                (6.4720, 3.3610),
                (6.4800, 3.3740),
                (6.4910, 3.3870),
                (6.5030, 3.3990),
                (6.5140, 3.4120),
                (6.5260, 3.4250),
            ],
        ),
    ]


def palmpay_market_zone_specs() -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (
            "Lagos Market Corridor",
            CampaignZoneType.TARGET.value,
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [3.345, 6.460],
                        [3.440, 6.460],
                        [3.440, 6.610],
                        [3.345, 6.610],
                        [3.345, 6.460],
                    ]
                ],
            },
        ),
        (
            "Mainland Retail Bonus",
            CampaignZoneType.BONUS.value,
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [3.375, 6.490],
                        [3.420, 6.490],
                        [3.420, 6.580],
                        [3.375, 6.580],
                        [3.375, 6.490],
                    ]
                ],
            },
        ),
    ]


async def upsert_trips_and_pings(
    session: AsyncSession,
    *,
    assignment: CampaignAssignment,
    campaign: Campaign,
    profile: DriverProfile,
    vehicle: Vehicle,
    driver: User,
    specs: list[tuple[str, datetime, list[tuple[float, float]]]] | None = None,
) -> list[TripSession]:
    trips = []
    for trip_key, started_at, coordinates in specs or trip_specs(utc_now()):
        ended_at = started_at + timedelta(minutes=42)
        trip = await find_demo_trip(session, assignment_id=assignment.id, trip_key=trip_key)
        if trip is None:
            trip = TripSession(
                assignment_id=assignment.id,
                campaign_id=campaign.id,
                driver_profile_id=profile.id,
                vehicle_id=vehicle.id,
                started_by_user_id=driver.id,
                status=TripSessionStatus.SEALED.value,
                started_at=started_at,
                ended_at=ended_at,
                sealed_at=ended_at,
                seal_reason=TripSealReason.CLIENT_COMPLETE.value,
                end_reason="demo_completed",
                trip_metadata=demo_metadata(seed_trip_key=trip_key),
            )
            session.add(trip)
            await session.flush()
        else:
            started_at = trip.started_at
            ended_at = trip.ended_at or started_at + timedelta(minutes=42)
            trip.campaign_id = campaign.id
            trip.driver_profile_id = profile.id
            trip.vehicle_id = vehicle.id
            trip.started_by_user_id = driver.id
            trip.status = TripSessionStatus.SEALED.value
            trip.started_at = started_at
            trip.ended_at = ended_at
            trip.sealed_at = ended_at
            trip.seal_reason = TripSealReason.CLIENT_COMPLETE.value
            trip.end_reason = "demo_completed"
            trip.trip_metadata = demo_metadata(seed_trip_key=trip_key)
            await session.flush()
        await ensure_ping_batch(
            session,
            trip=trip,
            coordinates=coordinates,
            started_at=started_at,
            trip_key=trip_key,
        )
        await session.refresh(trip)
        trips.append(trip)
    return trips


async def upsert_driver_story_campaigns(
    session: AsyncSession,
    *,
    settings: Settings,
    organization: AdvertiserOrganization,
    advertiser: User,
    admin: User,
    driver: User,
    profile: DriverProfile,
    vehicle: Vehicle,
    traffic_profile: TrafficDensityProfile,
) -> None:
    """Add truthful lifecycle breadth to the primary driver demo persona."""

    now = utc_now()
    specs = (
        {
            "name": "Airtel Lagos Commute",
            "description": "Completed commuter campaign across Lagos mainland routes.",
            "campaign_status": CampaignStatus.COMPLETED,
            "assignment_status": CampaignAssignmentStatus.COMPLETED,
            "start_at": now - timedelta(days=120),
            "end_at": now - timedelta(days=45),
            "activity": "airtel",
        },
        {
            "name": "PalmPay Market Routes",
            "description": "Active market-district campaign with completed demo routes.",
            "campaign_status": CampaignStatus.ACTIVE,
            "assignment_status": CampaignAssignmentStatus.COMPLETED,
            "start_at": now - timedelta(days=30),
            "end_at": now + timedelta(days=60),
            "activity": "palmpay_market",
        },
    )
    for spec in specs:
        campaign = await session.scalar(
            select(Campaign).where(
                Campaign.organization_id == organization.id,
                Campaign.name == spec["name"],
            )
        )
        campaign_values = {
            "created_by_user_id": advertiser.id,
            "description": spec["description"],
            "status": spec["campaign_status"].value,
            "start_at": spec["start_at"],
            "end_at": spec["end_at"],
            "budget_amount": Decimal("1800000.00"),
            "daily_budget_amount": Decimal("90000.00"),
            "currency": "NGN",
            "campaign_metadata": demo_metadata(driver_story=True),
        }
        if campaign is None:
            campaign = Campaign(
                organization_id=organization.id,
                name=spec["name"],
                **campaign_values,
            )
            session.add(campaign)
        else:
            for field, value in campaign_values.items():
                setattr(campaign, field, value)
        await session.flush()

        assignment = await session.scalar(
            select(CampaignAssignment).where(
                CampaignAssignment.campaign_id == campaign.id,
                CampaignAssignment.driver_profile_id == profile.id,
                CampaignAssignment.vehicle_id == vehicle.id,
            )
        )
        assignment_status = spec["assignment_status"]
        assignment_values = {
            "assigned_by_user_id": admin.id,
            "status": assignment_status.value,
            "offered_at": spec["start_at"] - timedelta(days=5),
            "accepted_at": spec["start_at"] - timedelta(days=4)
            if assignment_status == CampaignAssignmentStatus.COMPLETED
            else None,
            "activated_at": spec["start_at"]
            if assignment_status == CampaignAssignmentStatus.COMPLETED
            else None,
            "deactivated_at": None,
            "cancelled_at": None,
            "completed_at": (
                spec["end_at"] if spec["activity"] == "airtel" else now - timedelta(days=1)
            ),
            "notes": (
                "Successfully completed with consistent weekly activity."
                if spec["activity"] == "airtel"
                else "Completed sample market-route activity for the client demo."
            ),
            "assignment_metadata": demo_metadata(driver_story=True),
        }
        if assignment is None:
            assignment = CampaignAssignment(
                campaign_id=campaign.id,
                driver_profile_id=profile.id,
                vehicle_id=vehicle.id,
                **assignment_values,
            )
            session.add(assignment)
        else:
            for field, value in assignment_values.items():
                setattr(assignment, field, value)
        await session.flush()

        if spec["activity"] == "palmpay_market":
            creative = await session.scalar(
                select(CampaignCreative).where(
                    CampaignCreative.campaign_id == campaign.id,
                    CampaignCreative.name == "PalmPay Market Route Wrap",
                )
            )
            creative_values = {
                "creative_type": CreativeType.IMAGE.value,
                "placement": CreativePlacement.VEHICLE_EXTERIOR.value,
                "asset_url": "https://example.com/palmpay-market-route-wrap.png",
                "mime_type": "image/png",
                "width_px": 1600,
                "height_px": 900,
                "duration_seconds": None,
                "checksum": "sha256-palmpay-market-route-demo",
                "status": CreativeStatus.READY.value,
                "creative_metadata": demo_metadata(driver_story=True),
            }
            if creative is None:
                creative = CampaignCreative(
                    campaign_id=campaign.id,
                    name="PalmPay Market Route Wrap",
                    **creative_values,
                )
                session.add(creative)
            else:
                for field, value in creative_values.items():
                    setattr(creative, field, value)
            await session.flush()
            await upsert_zones(
                session,
                campaign=campaign,
                advertiser=advertiser,
                settings=settings,
                zone_specs=palmpay_market_zone_specs(),
            )

        if assignment_status != CampaignAssignmentStatus.COMPLETED:
            continue

        story_trip_specs = (
            [
                (
                    "demo-story-airtel-1",
                    now.replace(hour=9, minute=10, second=0, microsecond=0) - timedelta(days=70),
                    [
                        (6.6010, 3.3510),
                        (6.5840, 3.3660),
                        (6.5670, 3.3810),
                        (6.5500, 3.3970),
                        (6.5330, 3.4130),
                        (6.5160, 3.4290),
                    ],
                ),
                (
                    "demo-story-airtel-2",
                    now.replace(hour=15, minute=30, second=0, microsecond=0) - timedelta(days=58),
                    [
                        (6.5160, 3.4290),
                        (6.5310, 3.4160),
                        (6.5470, 3.4030),
                        (6.5630, 3.3900),
                        (6.5790, 3.3770),
                        (6.5950, 3.3640),
                    ],
                ),
            ]
            if spec["activity"] == "airtel"
            else palmpay_market_trip_specs(now)
        )
        trips = await upsert_trips_and_pings(
            session,
            assignment=assignment,
            campaign=campaign,
            profile=profile,
            vehicle=vehicle,
            driver=driver,
            specs=story_trip_specs,
        )
        await upsert_payout_rule(session, campaign=campaign, admin=admin)
        for trip in trips:
            await recompute_trip_analytics(
                session,
                trip_id=trip.id,
                metadata=demo_metadata(seed_step="analytics", driver_story=True),
                settings=settings,
            )
            await estimate_trip_impressions(
                session,
                trip_id=trip.id,
                traffic_density_profile_id=traffic_profile.id,
                metadata=demo_metadata(seed_step="impressions", driver_story=True),
                settings=settings,
            )
            _calculation, ledger_entry, _created = await calculate_trip_payout(
                session,
                trip_id=trip.id,
                payout_rule_id=None,
                metadata=demo_metadata(seed_step="payout", driver_story=True),
                settings=settings,
            )
            if ledger_entry is not None:
                ledger_entry.status = EarningsLedgerEntryStatus.AVAILABLE.value


async def find_demo_trip(
    session: AsyncSession,
    *,
    assignment_id: UUID,
    trip_key: str,
) -> TripSession | None:
    result = await session.execute(
        select(TripSession).where(TripSession.assignment_id == assignment_id)
    )
    for trip in result.scalars().all():
        if trip.trip_metadata.get("seed_trip_key") == trip_key:
            return trip
    return None


async def ensure_ping_batch(
    session: AsyncSession,
    *,
    trip: TripSession,
    coordinates: list[tuple[float, float]],
    started_at: datetime,
    trip_key: str,
) -> None:
    pings = [
        LocationPingCreate(
            recorded_at=started_at + timedelta(minutes=index * 7),
            lat=lat,
            lon=lon,
            accuracy_m=8.0 + index,
            speed_mps=7.5 + index / 3,
            heading_degrees=65.0,
            altitude_m=35.0,
            sequence_number=index,
            metadata=demo_metadata(sequence=index),
        )
        for index, (lat, lon) in enumerate(coordinates)
    ]
    payload = LocationPingBatchCreate(
        idempotency_key=f"{SEED_VERSION}:{trip_key}:pings",
        pings=pings,
        metadata=demo_metadata(seed_trip_key=trip_key),
    )
    digest = payload_hash(payload)
    existing = await session.scalar(
        select(LocationPingBatch).where(
            LocationPingBatch.trip_session_id == trip.id,
            LocationPingBatch.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        ping_count = await session.scalar(
            select(func.count(LocationPing.id)).where(LocationPing.batch_id == existing.id)
        )
        if existing.payload_hash == digest and int(ping_count or 0) == len(pings):
            return
        await session.execute(delete(LocationPing).where(LocationPing.batch_id == existing.id))
        await session.execute(delete(LocationPingBatch).where(LocationPingBatch.id == existing.id))
        await session.flush()

    batch = LocationPingBatch(
        trip_session_id=trip.id,
        idempotency_key=payload.idempotency_key,
        payload_hash=digest,
        pings_accepted=len(pings),
        received_at=trip.ended_at or started_at,
        batch_metadata=payload.metadata,
    )
    session.add(batch)
    await session.flush()
    for ping in pings:
        session.add(
            LocationPing(
                trip_session_id=trip.id,
                batch_id=batch.id,
                recorded_at=ping.recorded_at,
                received_at=batch.received_at,
                sequence_number=ping.sequence_number,
                latitude=ping.lat,
                longitude=ping.lon,
                accuracy_m=ping.accuracy_m,
                speed_mps=ping.speed_mps,
                heading_degrees=ping.heading_degrees,
                altitude_m=ping.altitude_m,
                geom=point_value(session, lon=ping.lon, lat=ping.lat),
                ping_metadata=ping.metadata,
            )
        )
    await session.flush()


async def upsert_traffic_profile(
    session: AsyncSession,
) -> TrafficDensityProfile:
    profile = await session.scalar(
        select(TrafficDensityProfile).where(
            TrafficDensityProfile.name == "Demo Lagos Urban Density"
        )
    )
    if profile is None:
        await session.execute(
            select(TrafficDensityProfile)
            .where(
                TrafficDensityProfile.status == TrafficDensityProfileStatus.ACTIVE.value,
                TrafficDensityProfile.is_default.is_(True),
            )
            .with_for_update()
        )
        profile = await create_traffic_density_profile(
            session,
            TrafficDensityProfileCreate(
                name="Demo Lagos Urban Density",
                description="Local demo traffic density profile for Lagos routes.",
                profile_type="urban",
                traffic_density_per_km=Decimal("240.0"),
                dwell_impressions_per_minute=Decimal("5.0"),
                road_category_weight=Decimal("1.15"),
                morning_weight=Decimal("1.20"),
                midday_weight=Decimal("1.00"),
                evening_weight=Decimal("1.30"),
                night_weight=Decimal("0.70"),
                target_zone_weight=Decimal("1.20"),
                bonus_zone_weight=Decimal("1.35"),
                exclusion_zone_weight=Decimal("0.0"),
                is_default=True,
                status=TrafficDensityProfileStatus.ACTIVE,
                metadata=demo_metadata(),
            ),
        )
    else:
        profile.description = "Local demo traffic density profile for Lagos routes."
        profile.profile_type = "urban"
        profile.traffic_density_per_km = Decimal("240.0")
        profile.dwell_impressions_per_minute = Decimal("5.0")
        profile.road_category_weight = Decimal("1.15")
        profile.morning_weight = Decimal("1.20")
        profile.midday_weight = Decimal("1.00")
        profile.evening_weight = Decimal("1.30")
        profile.night_weight = Decimal("0.70")
        profile.target_zone_weight = Decimal("1.20")
        profile.bonus_zone_weight = Decimal("1.35")
        profile.exclusion_zone_weight = Decimal("0.0")
        profile.is_default = True
        profile.status = TrafficDensityProfileStatus.ACTIVE.value
        profile.profile_metadata = demo_metadata()
        await session.flush()
        await session.refresh(profile)
    return profile


async def upsert_payout_rule(
    session: AsyncSession,
    *,
    campaign: Campaign,
    admin: User,
) -> CampaignPayoutRule:
    rule = await session.scalar(
        select(CampaignPayoutRule).where(
            CampaignPayoutRule.campaign_id == campaign.id,
            CampaignPayoutRule.rule_metadata["seed_version"].as_string() == SEED_VERSION,
        )
    )
    values = {
        "created_by_user_id": admin.id,
        "updated_by_user_id": admin.id,
        "formula_version": "payout_v1",
        "status": CampaignPayoutRuleStatus.ACTIVE.value,
        "currency": "NGN",
        "base_rate_per_km": Decimal("180.00"),
        "base_rate_per_active_hour": Decimal("1200.00"),
        "target_zone_bonus_rate_per_km": Decimal("75.00"),
        "bonus_zone_bonus_rate_per_km": Decimal("125.00"),
        "estimated_impression_rate_per_1000": Decimal("250.00"),
        "min_payout_per_trip": Decimal("1500.00"),
        "max_payout_per_trip": Decimal("12000.00"),
        "low_fraud_multiplier": Decimal("0.9000"),
        "medium_fraud_multiplier": Decimal("0.7000"),
        "high_fraud_multiplier": Decimal("0.2500"),
        "rule_metadata": demo_metadata(),
    }
    if values["status"] == CampaignPayoutRuleStatus.ACTIVE.value:
        filters = [
            CampaignPayoutRule.campaign_id == campaign.id,
            CampaignPayoutRule.status == CampaignPayoutRuleStatus.ACTIVE.value,
        ]
        if rule is not None:
            filters.append(CampaignPayoutRule.id != rule.id)
        await session.execute(
            update(CampaignPayoutRule)
            .where(*filters)
            .values(status=CampaignPayoutRuleStatus.INACTIVE.value, updated_at=utc_now())
        )
    if rule is None:
        rule = CampaignPayoutRule(campaign_id=campaign.id, **values)
        session.add(rule)
    else:
        for field, value in values.items():
            setattr(rule, field, value)
    await session.flush()
    await session.refresh(rule)
    return rule


async def upsert_palmpay_graph(
    session: AsyncSession,
    *,
    settings: Settings,
    organization: AdvertiserOrganization,
    advertiser: User,
    admin: User,
    traffic_profile: TrafficDensityProfile,
) -> None:
    now = utc_now()
    campaign = await session.scalar(
        select(Campaign).where(
            Campaign.organization_id == organization.id,
            Campaign.name == "PalmPay Wuse Blitz",
        )
    )
    campaign_values = {
        "created_by_user_id": advertiser.id,
        "description": (
            "Premium door-panel advertising across high-traffic ride-hail routes in Wuse II."
        ),
        "status": CampaignStatus.ACTIVE.value,
        "start_at": now - timedelta(days=30),
        "end_at": now + timedelta(days=60),
        "budget_amount": Decimal("2500000.00"),
        "daily_budget_amount": Decimal("125000.00"),
        "currency": "NGN",
        "campaign_metadata": demo_metadata(showcase="palmpay_wuse"),
    }
    if campaign is None:
        campaign = Campaign(
            organization_id=organization.id,
            name="PalmPay Wuse Blitz",
            **campaign_values,
        )
        session.add(campaign)
    else:
        for field, value in campaign_values.items():
            setattr(campaign, field, value)
    await session.flush()

    creative = await session.scalar(
        select(CampaignCreative).where(
            CampaignCreative.campaign_id == campaign.id,
            CampaignCreative.name == "Door panel — teal",
        )
    )
    creative_values = {
        "creative_type": CreativeType.IMAGE.value,
        "placement": CreativePlacement.VEHICLE_EXTERIOR.value,
        "asset_url": "https://example.com/palmpay-wuse-door-panel.png",
        "mime_type": "image/png",
        "width_px": 1600,
        "height_px": 900,
        "duration_seconds": None,
        "checksum": "sha256-palmpay-wuse-demo",
        "status": CreativeStatus.READY.value,
        "creative_metadata": demo_metadata(showcase="palmpay_wuse"),
    }
    if creative is None:
        creative = CampaignCreative(
            campaign_id=campaign.id,
            name="Door panel — teal",
            **creative_values,
        )
        session.add(creative)
    else:
        for field, value in creative_values.items():
            setattr(creative, field, value)
    await session.flush()

    driver = await upsert_user(
        session,
        email="driver.wuse@demo.mobility.local",
        password="DemoWuseDriver12345!",
        full_name="Musa Abdullahi",
        role=UserRole.DRIVER,
        settings=settings,
    )
    profile = await session.scalar(select(DriverProfile).where(DriverProfile.user_id == driver.id))
    if profile is None:
        profile = DriverProfile(
            user_id=driver.id,
            onboarding_status=DriverOnboardingStatus.ACTIVE.value,
            license_number="DRV-DEMO-WUSE-001",
            service_city="Abuja",
            country_code="NG",
            profile_metadata=demo_metadata(service_area="Wuse II"),
        )
        session.add(profile)
    else:
        profile.onboarding_status = DriverOnboardingStatus.ACTIVE.value
        profile.license_number = "DRV-DEMO-WUSE-001"
        profile.service_city = "Abuja"
        profile.country_code = "NG"
        profile.profile_metadata = demo_metadata(service_area="Wuse II")
    await session.flush()

    normalized_plate = normalize_plate_number("ABJ-101")
    vehicle = await session.scalar(
        select(Vehicle).where(
            Vehicle.plate_country_code == "NG",
            Vehicle.plate_number_normalized == normalized_plate,
        )
    )
    if vehicle is None:
        vehicle = Vehicle(
            driver_profile_id=profile.id,
            plate_number="ABJ-101",
            plate_number_normalized=normalized_plate,
            plate_country_code="NG",
            vehicle_type=VehicleType.CAR.value,
            make="Toyota",
            model="Camry",
            year=2022,
            color="Silver",
            status=VehicleStatus.ACTIVE.value,
            vehicle_metadata=demo_metadata(wrap_ready=True, service_area="Wuse II"),
        )
        session.add(vehicle)
    else:
        vehicle.driver_profile_id = profile.id
        vehicle.plate_number = "ABJ-101"
        vehicle.vehicle_type = VehicleType.CAR.value
        vehicle.make = "Toyota"
        vehicle.model = "Camry"
        vehicle.year = 2022
        vehicle.color = "Silver"
        vehicle.status = VehicleStatus.ACTIVE.value
        vehicle.vehicle_metadata = demo_metadata(wrap_ready=True, service_area="Wuse II")
    await session.flush()

    await upsert_zones(
        session,
        campaign=campaign,
        advertiser=advertiser,
        settings=settings,
        zone_specs=[
            (
                "Wuse II Core",
                CampaignZoneType.TARGET.value,
                {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [7.44, 9.035],
                            [7.505, 9.035],
                            [7.505, 9.105],
                            [7.44, 9.105],
                            [7.44, 9.035],
                        ]
                    ],
                },
            ),
            (
                "Wuse II Retail Bonus",
                CampaignZoneType.BONUS.value,
                {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [7.455, 9.05],
                            [7.49, 9.05],
                            [7.49, 9.09],
                            [7.455, 9.09],
                            [7.455, 9.05],
                        ]
                    ],
                },
            ),
        ],
    )
    assignment = await upsert_assignment(
        session,
        campaign=campaign,
        profile=profile,
        vehicle=vehicle,
        admin=admin,
        driver=driver,
    )
    trips = await upsert_trips_and_pings(
        session,
        assignment=assignment,
        campaign=campaign,
        profile=profile,
        vehicle=vehicle,
        driver=driver,
        specs=palmpay_trip_specs(now),
    )
    await upsert_payout_rule(session, campaign=campaign, admin=admin)
    await session.flush()
    for trip in trips:
        await recompute_trip_analytics(
            session,
            trip_id=trip.id,
            metadata=demo_metadata(seed_step="analytics", showcase="palmpay_wuse"),
            settings=settings,
        )
        await estimate_trip_impressions(
            session,
            trip_id=trip.id,
            traffic_density_profile_id=traffic_profile.id,
            metadata=demo_metadata(seed_step="impressions", showcase="palmpay_wuse"),
            settings=settings,
        )
        existing_payout_id = await session.scalar(
            select(PayoutCalculation.id).where(PayoutCalculation.trip_session_id == trip.id)
        )
        if existing_payout_id is None:
            await calculate_trip_payout(
                session,
                trip_id=trip.id,
                payout_rule_id=None,
                metadata=demo_metadata(seed_step="payout", showcase="palmpay_wuse"),
                settings=settings,
            )


async def build_demo_graph(session: AsyncSession, settings: Settings) -> DemoGraph:
    admin = await upsert_user(
        session,
        email="admin@demo.mobility.local",
        password=DEMO_PASSWORDS["admin@demo.mobility.local"],
        full_name="Demo Admin",
        role=UserRole.ADMIN,
        settings=settings,
    )
    advertiser = await upsert_user(
        session,
        email="advertiser@demo.mobility.local",
        password=DEMO_PASSWORDS["advertiser@demo.mobility.local"],
        full_name="Demo Advertiser Owner",
        role=UserRole.ADVERTISER,
        settings=settings,
    )
    viewer = await upsert_user(
        session,
        email="viewer@demo.mobility.local",
        password=DEMO_PASSWORDS["viewer@demo.mobility.local"],
        full_name="Demo Advertiser Viewer",
        role=UserRole.ADVERTISER,
        settings=settings,
    )
    driver = await upsert_user(
        session,
        email="driver@demo.mobility.local",
        password=DEMO_PASSWORDS["driver@demo.mobility.local"],
        full_name="Demo Driver",
        role=UserRole.DRIVER,
        settings=settings,
    )
    organization = await upsert_organization(session)
    await upsert_membership(
        session,
        organization=organization,
        user=advertiser,
        role=MembershipRole.OWNER,
    )
    await upsert_membership(
        session,
        organization=organization,
        user=viewer,
        role=MembershipRole.VIEWER,
    )
    driver_profile = await upsert_driver_profile(session, driver=driver)
    vehicle = await upsert_vehicle(session, profile=driver_profile)
    campaign = await upsert_campaign(session, organization=organization, advertiser=advertiser)
    creative = await upsert_creative(session, campaign=campaign)
    await upsert_zones(session, campaign=campaign, advertiser=advertiser, settings=settings)
    assignment = await upsert_assignment(
        session,
        campaign=campaign,
        profile=driver_profile,
        vehicle=vehicle,
        admin=admin,
        driver=driver,
    )
    trips = await upsert_trips_and_pings(
        session,
        assignment=assignment,
        campaign=campaign,
        profile=driver_profile,
        vehicle=vehicle,
        driver=driver,
    )
    traffic_profile = await upsert_traffic_profile(session)
    await upsert_payout_rule(session, campaign=campaign, admin=admin)
    await session.flush()

    for trip in trips:
        await recompute_trip_analytics(
            session,
            trip_id=trip.id,
            metadata=demo_metadata(seed_step="analytics"),
            settings=settings,
        )
        await estimate_trip_impressions(
            session,
            trip_id=trip.id,
            traffic_density_profile_id=traffic_profile.id,
            metadata=demo_metadata(seed_step="impressions"),
            settings=settings,
        )
        existing_payout_id = await session.scalar(
            select(PayoutCalculation.id).where(PayoutCalculation.trip_session_id == trip.id)
        )
        if existing_payout_id is None:
            await calculate_trip_payout(
                session,
                trip_id=trip.id,
                payout_rule_id=None,
                metadata=demo_metadata(seed_step="payout"),
                settings=settings,
            )

    await upsert_driver_story_campaigns(
        session,
        settings=settings,
        organization=organization,
        advertiser=advertiser,
        admin=admin,
        driver=driver,
        profile=driver_profile,
        vehicle=vehicle,
        traffic_profile=traffic_profile,
    )

    await upsert_palmpay_graph(
        session,
        settings=settings,
        organization=organization,
        advertiser=advertiser,
        admin=admin,
        traffic_profile=traffic_profile,
    )

    rich = await build_rich_seed(
        session,
        settings=settings,
        admin=admin,
        advertiser=advertiser,
        organization=organization,
        traffic_profile=traffic_profile,
    )

    return DemoGraph(
        admin=admin,
        advertiser=advertiser,
        viewer=viewer,
        driver=driver,
        organization=organization,
        driver_profile=driver_profile,
        vehicle=vehicle,
        campaign=campaign,
        creative=creative,
        assignment=assignment,
        trips=trips,
        traffic_profile=traffic_profile,
        rich=rich,
    )


async def counts(session: AsyncSession, graph: DemoGraph) -> dict[str, int]:
    trip_ids = [trip.id for trip in graph.trips]
    rich_trip_count = int(
        await session.scalar(
            select(func.count(TripSession.id)).where(
                TripSession.trip_metadata["seed_version"].as_string() == F7_SEED_VERSION
            )
        )
        or 0
    )
    return {
        "users": int(
            await session.scalar(
                select(func.count(User.id)).where(
                    User.email.in_([normalize_email(email) for email in DEMO_PASSWORDS])
                )
            )
            or 0
        ),
        "campaign_zones": int(
            await session.scalar(
                select(func.count(CampaignZone.id)).where(
                    CampaignZone.campaign_id == graph.campaign.id
                )
            )
            or 0
        ),
        "trips": len(graph.trips),
        "pings": int(
            await session.scalar(
                select(func.count(LocationPing.id)).where(
                    LocationPing.trip_session_id.in_(trip_ids)
                )
            )
            or 0
        ),
        "analytics": int(
            await session.scalar(
                select(func.count(TripAnalytics.id)).where(
                    TripAnalytics.trip_session_id.in_(trip_ids)
                )
            )
            or 0
        ),
        "impression_estimates": int(
            await session.scalar(
                select(func.count(ImpressionEstimate.id)).where(
                    ImpressionEstimate.trip_session_id.in_(trip_ids)
                )
            )
            or 0
        ),
        "payout_calculations": int(
            await session.scalar(
                select(func.count(PayoutCalculation.id)).where(
                    PayoutCalculation.trip_session_id.in_(trip_ids)
                )
            )
            or 0
        ),
        "ledger_entries": int(
            await session.scalar(
                select(func.count(EarningsLedgerEntry.id)).where(
                    EarningsLedgerEntry.trip_session_id.in_(trip_ids)
                )
            )
            or 0
        ),
        "f7_drivers": len(graph.rich.drivers),
        "f7_campaigns": len(graph.rich.campaigns),
        "f7_assignments": len(graph.rich.assignments),
        "f7_trips": rich_trip_count,
        "f7_trips_added": len(graph.rich.new_trips),
        "f7_audit_events": graph.rich.audit_event_count,
    }


def print_summary(graph: DemoGraph, summary_counts: dict[str, int]) -> None:
    print("Demo seed complete.")
    print(f"Organization: {graph.organization.name} ({graph.organization.id})")
    print(f"Campaign: {graph.campaign.name} ({graph.campaign.id})")
    print(f"Assignment: {graph.assignment.id}")
    print("Trips:")
    for trip in graph.trips:
        print(f"- {trip.id} started_at={trip.started_at.isoformat()}")
    print("Counts:")
    print(json.dumps(summary_counts, indent=2, sort_keys=True))
    print("Local-only demo credentials:")
    for email, password in DEMO_PASSWORDS.items():
        print(f"- {email} / {password}")
    for email, password in F7_DRIVER_PASSWORDS.items():
        print(f"- {email} / {password}")
    print("Sample frontend endpoints:")
    print("- POST /api/v1/auth/login")
    print("- GET /api/v1/me")
    print(f"- GET /api/v1/advertiser/campaigns/{graph.campaign.id}/summary")
    print(
        f"- GET /api/v1/advertiser/campaigns/{graph.campaign.id}/heatmap"
        f"?bbox={DEMO_BBOX}&resolution_m=500&metric=estimated_impressions"
    )
    print("- GET /api/v1/driver/earnings/summary")


async def run_seed(settings: Settings | None = None) -> DemoGraph:
    settings = settings or get_settings()
    ensure_seed_allowed(settings)
    engine = get_engine(settings)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        await ensure_database_ready(session)
        graph = await build_demo_graph(session, settings)
        summary_counts = await counts(session, graph)
        await session.commit()
        print_summary(graph, summary_counts)
        return graph


def main() -> int:
    try:
        asyncio.run(run_seed())
    except AppError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        if exc.details:
            print(json.dumps(exc.details, sort_keys=True), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"DEMO_SEED_FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Append-only F7 demo data layered on top of the frozen slice-12 seed.

Every F7 trip has a stable date-based key. Existing trips, pings, analytics,
impressions, payouts, and ledger entries are never rewritten: a same-day rerun
is a no-op, while a later rerun only appends missing rolling-window dates that
still fit the campaign's stored lifecycle window.
"""

import hashlib
import os
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.models.audit import AuditEvent
from app.models.campaign import (
    Campaign,
    CampaignCreative,
    CampaignStatus,
    CreativePlacement,
    CreativeStatus,
    CreativeType,
)
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.impression import (
    TrafficDensityProfile,
    TrafficDensityProfileStatus,
    TrafficDensityProfileType,
)
from app.models.organization import AdvertiserOrganization
from app.models.payout import CampaignPayoutRule, CampaignPayoutRuleStatus
from app.models.trip import (
    LocationPing,
    LocationPingBatch,
    TripEvidenceManifestEntry,
    TripSealReason,
    TripSession,
    TripSessionStatus,
)
from app.models.trip_analytics import TripAnalytics
from app.models.user import User, UserRole, UserStatus
from app.models.vehicle import Vehicle, VehicleStatus, VehicleType
from app.schemas.trips import (
    LocationPingBatchCreate,
    LocationPingCreate,
    TripEvidenceManifestEntryCreate,
)
from app.services.campaign_zones import geometry_expression, validate_geometry_with_postgis
from app.services.impressions import estimate_trip_impressions
from app.services.payouts import calculate_trip_payout
from app.services.trip_analytics import recompute_trip_analytics
from app.services.trip_evidence import (
    batch_payload_hash,
    manifest_root,
    sign_batch_receipt,
    sign_manifest_receipt,
)
from app.services.trips import point_value
from app.services.users import normalize_email, validate_password_length
from app.services.vehicles import normalize_plate_number

F7_SEED_VERSION = "f7_rich_v1"
F7_DRIVER_PASSWORDS = {
    f"driver{index:02d}@demo.mobility.local": f"DemoDriver{index:02d}Pass!"
    for index in range(1, 10)
}

DRIVER_NAMES = (
    "Amina Bello",
    "Chinedu Okafor",
    "Tunde Adebayo",
    "Ngozi Eze",
    "Bola Adeyemi",
    "Ifeanyi Nwosu",
    "Kemi Balogun",
    "Seyi Ogunleye",
    "Zainab Musa",
)
DRIVER_AREAS = (
    "Ikeja",
    "Yaba",
    "Surulere",
    "Lekki",
    "Victoria Island",
    "Maryland",
    "Ajah",
    "Ogba",
    "Lagos Island",
)
VEHICLE_DETAILS = (
    ("Toyota", "Corolla", "White", VehicleType.CAR),
    ("Honda", "Accord", "Silver", VehicleType.CAR),
    ("Toyota", "Sienna", "Blue", VehicleType.MINIBUS),
    ("Hyundai", "Elantra", "Black", VehicleType.CAR),
    ("Kia", "Rio", "Red", VehicleType.CAR),
    ("Nissan", "Urvan", "White", VehicleType.VAN),
    ("Toyota", "Camry", "Grey", VehicleType.CAR),
    ("Honda", "Civic", "Blue", VehicleType.CAR),
    ("Suzuki", "Every", "Silver", VehicleType.MINIBUS),
)

CAMPAIGN_SPECS = (
    ("Aster Vale Foods — Mainland Deliveries", CampaignStatus.ACTIVE, "rolling"),
    ("Cedar Bay Furnishings — Ikeja Showroom", CampaignStatus.PAUSED, "paused"),
    ("Oriole Books — Island Reading Week", CampaignStatus.COMPLETED, "completed"),
    ("Sable Ridge Travel — Airport Arrivals", CampaignStatus.DRAFT, "draft"),
)

# (latitude, longitude); the final corridor is reserved for the exclusion anomaly.
CORRIDORS = (
    ((6.6018, 3.3515), (6.5880, 3.3650), (6.5730, 3.3810), (6.5580, 3.3970)),
    ((6.5244, 3.3792), (6.5100, 3.3890), (6.4950, 3.4010), (6.4790, 3.4140)),
    ((6.5059, 3.3431), (6.4930, 3.3560), (6.4800, 3.3690), (6.4660, 3.3820)),
    ((6.4541, 3.3947), (6.4450, 3.4080), (6.4370, 3.4230), (6.4290, 3.4400)),
    ((6.4698, 3.5852), (6.4560, 3.5700), (6.4430, 3.5530), (6.4320, 3.5360)),
    ((6.5480, 3.4560), (6.5490, 3.4590), (6.5510, 3.4630), (6.5530, 3.4670)),
)


@dataclass(frozen=True)
class DriverAsset:
    index: int
    user: User
    profile: DriverProfile
    vehicle: Vehicle


@dataclass(frozen=True)
class RichSeedResult:
    drivers: list[DriverAsset]
    campaigns: list[Campaign]
    assignments: list[CampaignAssignment]
    new_trips: list[TripSession]
    existing_trip_count: int
    audit_event_count: int


def utc_now() -> datetime:
    return datetime.now(UTC)


def f7_metadata(**extra: Any) -> dict[str, Any]:
    return {"demo": True, "seed_version": F7_SEED_VERSION, **extra}


def max_trips_per_day() -> int:
    raw = os.getenv("F7_SEED_MAX_TRIPS_PER_DAY", "2")
    try:
        value = int(raw)
    except ValueError as exc:
        raise AppError("INVALID_F7_SEED_DENSITY", "F7 seed density must be an integer") from exc
    if value < 0:
        raise AppError("INVALID_F7_SEED_DENSITY", "F7 seed density must not be negative")
    return value


def _set_known_credential_flag(user: User) -> None:
    # F7 credentials are intentionally documented demo credentials. This getattr
    # guard keeps the seed importable both before and after the auth migration lands.
    if hasattr(User, "must_change_password"):
        user.must_change_password = False


async def _upsert_driver(session: AsyncSession, *, index: int, settings: Settings) -> DriverAsset:
    from app.seeds.demo import DEMO_DRIVER_PHONE_NUMBERS

    email = f"driver{index:02d}@demo.mobility.local"
    password = F7_DRIVER_PASSWORDS[email]
    validate_password_length(password, settings)
    user = await session.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        user = User(
            email=normalize_email(email),
            password_hash=hash_password(password),
            full_name=DRIVER_NAMES[index - 1],
            role=UserRole.DRIVER.value,
            status=UserStatus.ACTIVE.value,
        )
        _set_known_credential_flag(user)
        session.add(user)
    else:
        if user.role != UserRole.DRIVER.value:
            raise AppError("F7_SEED_USER_CONFLICT", f"{email} is not a driver")
        user.full_name = DRIVER_NAMES[index - 1]
        user.status = UserStatus.ACTIVE.value
        _set_known_credential_flag(user)
    user.phone = DEMO_DRIVER_PHONE_NUMBERS[email]
    await session.flush()

    profile = await session.scalar(select(DriverProfile).where(DriverProfile.user_id == user.id))
    if profile is None:
        onboarding_status = (
            DriverOnboardingStatus.ACTIVE if index <= 7 else DriverOnboardingStatus.SUSPENDED
        )
        profile = DriverProfile(
            user_id=user.id,
            onboarding_status=onboarding_status.value,
            license_number=f"LAG-2024-{58300 + index}",
            service_city="Lagos",
            country_code="NG",
            profile_metadata=f7_metadata(service_area=DRIVER_AREAS[index - 1]),
        )
        session.add(profile)
        await session.flush()

    plate = (
        "LSR-219-XY",
        "KJA-637-BD",
        "FKJ-824-CN",
        "LND-315-HG",
        "EPE-926-KL",
        "AKD-458-PQ",
        "MUS-763-RS",
        "SMK-592-TV",
        "AAA-681-WZ",
    )[index - 1]
    normalized_plate = normalize_plate_number(plate)
    vehicle = await session.scalar(
        select(Vehicle).where(
            Vehicle.plate_country_code == "NG",
            Vehicle.plate_number_normalized == normalized_plate,
        )
    )
    if vehicle is None:
        make, model, color, vehicle_type = VEHICLE_DETAILS[index - 1]
        vehicle = Vehicle(
            driver_profile_id=profile.id,
            plate_number=plate,
            plate_number_normalized=normalized_plate,
            plate_country_code="NG",
            vehicle_type=vehicle_type.value,
            make=make,
            model=model,
            year=2018 + (index % 6),
            color=color,
            status=(VehicleStatus.ACTIVE.value if index <= 8 else VehicleStatus.INACTIVE.value),
            vehicle_metadata=f7_metadata(fleet_index=index, wrap_ready=index % 3 != 0),
        )
        session.add(vehicle)
        await session.flush()
    elif vehicle.driver_profile_id != profile.id:
        raise AppError("F7_SEED_VEHICLE_CONFLICT", f"{plate} belongs to another driver")
    return DriverAsset(index=index, user=user, profile=profile, vehicle=vehicle)


def _initial_campaign_window(kind: str, now: datetime) -> tuple[datetime, datetime]:
    midnight = datetime.combine(now.date(), time.min, tzinfo=UTC)
    if kind == "rolling":
        return midnight - timedelta(days=40), midnight + timedelta(days=30)
    if kind == "paused":
        return midnight - timedelta(days=45), midnight + timedelta(days=15)
    if kind == "completed":
        return midnight - timedelta(days=56), midnight - timedelta(days=29)
    return midnight + timedelta(days=7), midnight + timedelta(days=67)


async def _upsert_campaign(
    session: AsyncSession,
    *,
    organization: AdvertiserOrganization,
    advertiser: User,
    name: str,
    status_value: CampaignStatus,
    kind: str,
    now: datetime,
) -> Campaign:
    campaign = await session.scalar(
        select(Campaign).where(
            Campaign.organization_id == organization.id,
            Campaign.name == name,
        )
    )
    if campaign is None:
        start_at, end_at = _initial_campaign_window(kind, now)
        campaign = Campaign(
            organization_id=organization.id,
            created_by_user_id=advertiser.id,
            name=name,
            description=(
                "Delivery visibility around Lagos offices."
                if kind == "rolling"
                else "Visibility around shops and offices in Lagos."
            ),
            status=status_value.value,
            start_at=start_at,
            end_at=end_at,
            budget_amount=Decimal("4800000.00"),
            daily_budget_amount=Decimal("180000.00"),
            currency="NGN",
            campaign_metadata=f7_metadata(generation_class=kind),
        )
        session.add(campaign)
        await session.flush()
    # Lifecycle windows are deliberately immutable after first creation.
    return campaign


async def _ensure_creative(session: AsyncSession, campaign: Campaign, index: int) -> None:
    name = campaign.name.split(" — ")[0] + " door panel"
    creative = await session.scalar(
        select(CampaignCreative).where(
            CampaignCreative.campaign_id == campaign.id,
            CampaignCreative.name == name,
        )
    )
    if creative is None:
        session.add(
            CampaignCreative(
                campaign_id=campaign.id,
                name=name,
                creative_type=CreativeType.IMAGE.value,
                placement=CreativePlacement.VEHICLE_EXTERIOR.value,
                asset_url=None,
                mime_type="image/png",
                width_px=1600,
                height_px=900,
                checksum=None,
                status=CreativeStatus.READY.value,
                creative_metadata=f7_metadata(campaign_index=index),
            )
        )
        await session.flush()


def _zone_geometry(campaign_index: int, zone_type: CampaignZoneType) -> dict[str, Any]:
    if zone_type == CampaignZoneType.EXCLUSION:
        return {
            "type": "Polygon",
            "coordinates": [
                [
                    [3.454, 6.546],
                    [3.469, 6.546],
                    [3.469, 6.556],
                    [3.454, 6.556],
                    [3.454, 6.546],
                ]
            ],
        }
    west = 3.32 + campaign_index * 0.025
    south = 6.40 + campaign_index * 0.02
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [west, south],
                [west + 0.20, south],
                [west + 0.20, south + 0.20],
                [west, south + 0.20],
                [west, south],
            ]
        ],
    }


async def _ensure_zones(
    session: AsyncSession,
    *,
    campaign: Campaign,
    campaign_index: int,
    advertiser: User,
    settings: Settings,
) -> None:
    zone_types = [CampaignZoneType.TARGET]
    if campaign_index == 1:
        zone_types.append(CampaignZoneType.EXCLUSION)
    for zone_type in zone_types:
        name = (
            "Apapa port access"
            if zone_type == CampaignZoneType.EXCLUSION
            else ("Lagos Mainland", "Ikeja and Maryland", "Lagos Island", "Airport Road")[
                campaign_index - 1
            ]
        )
        existing = await session.scalar(
            select(CampaignZone).where(
                CampaignZone.campaign_id == campaign.id,
                CampaignZone.name == name,
            )
        )
        if existing is not None:
            continue
        geometry = _zone_geometry(campaign_index, zone_type)
        validated = await validate_geometry_with_postgis(session, geometry, settings)
        session.add(
            CampaignZone(
                campaign_id=campaign.id,
                created_by_user_id=advertiser.id,
                name=name,
                description=(
                    "Heavy industrial traffic; avoid during campaigns."
                    if zone_type == CampaignZoneType.EXCLUSION
                    else (
                        "Reach shops and offices along the Yaba and Surulere routes.",
                        "Reach furniture shoppers along Ikorodu Road and Maryland.",
                        "Promote the reading week around Lagos Island bookshops.",
                        "Reach travellers along Airport Road in Ikeja.",
                    )[campaign_index - 1]
                ),
                zone_type=zone_type.value,
                geom=geometry_expression(validated.geojson_text),
                zone_metadata=f7_metadata(area_sq_m=str(validated.area_sq_m)),
            )
        )
        await session.flush()


async def _ensure_payout_rule(
    session: AsyncSession, *, campaign: Campaign, admin: User
) -> CampaignPayoutRule:
    rule = await session.scalar(
        select(CampaignPayoutRule).where(
            CampaignPayoutRule.campaign_id == campaign.id,
            CampaignPayoutRule.rule_metadata["seed_version"].as_string() == F7_SEED_VERSION,
        )
    )
    if rule is None:
        rule = CampaignPayoutRule(
            campaign_id=campaign.id,
            created_by_user_id=admin.id,
            updated_by_user_id=admin.id,
            formula_version="payout_v4",
            status=CampaignPayoutRuleStatus.ACTIVE.value,
            currency="NGN",
            base_rate_per_km=None,
            base_rate_per_active_hour=None,
            target_zone_bonus_rate_per_km=None,
            bonus_zone_bonus_rate_per_km=None,
            estimated_impression_rate_per_1000=None,
            min_payout_per_trip=None,
            max_payout_per_trip=None,
            low_fraud_multiplier=None,
            medium_fraud_multiplier=None,
            high_fraud_multiplier=None,
            rule_metadata=f7_metadata(),
        )
        session.add(rule)
        await session.flush()
    return rule


async def _ensure_assignment(
    session: AsyncSession,
    *,
    campaign: Campaign,
    asset: DriverAsset,
    admin: User,
    status_value: CampaignAssignmentStatus,
    advertiser: User,
    settings: Settings,
) -> CampaignAssignment:
    assignment = await session.scalar(
        select(CampaignAssignment).where(
            CampaignAssignment.campaign_id == campaign.id,
            CampaignAssignment.vehicle_id == asset.vehicle.id,
            CampaignAssignment.driver_profile_id == asset.profile.id,
        )
    )
    if assignment is not None:
        return assignment
    now = utc_now()
    # Lifecycle timestamps must never sit in the future: a draft campaign's
    # start_at (offers) or a paused campaign's end_at (completions) can both
    # postdate the seed run.
    offered_at = min(campaign.start_at or now, now)
    is_offered = status_value == CampaignAssignmentStatus.OFFERED
    is_completed = status_value == CampaignAssignmentStatus.COMPLETED
    from app.seeds.demo_authority import prepare_daily_offer

    terms, digest = await prepare_daily_offer(
        session,
        campaign=campaign,
        profile=asset.profile,
        admin=admin,
        advertiser=advertiser,
        settings=settings,
        offered_at=offered_at,
    )
    assignment = CampaignAssignment(
        offer_terms=terms,
        offer_terms_sha256=digest,
        campaign_id=campaign.id,
        driver_profile_id=asset.profile.id,
        vehicle_id=asset.vehicle.id,
        assigned_by_user_id=admin.id,
        status=status_value.value,
        offered_at=offered_at,
        accepted_at=None if is_offered else offered_at + timedelta(minutes=10),
        activated_at=None if is_offered else offered_at + timedelta(minutes=20),
        completed_at=min(campaign.end_at - timedelta(minutes=1), now) if is_completed else None,
        notes="Collect the door panels at the Ikeja office.",
        assignment_metadata=f7_metadata(driver_index=asset.index),
    )
    session.add(assignment)
    await session.flush()
    return assignment


def _date_range(start: date, end: date) -> list[date]:
    if start > end:
        return []
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _candidate_dates(campaign: Campaign, kind: str, now: datetime) -> list[date]:
    assert campaign.start_at is not None and campaign.end_at is not None
    first = campaign.start_at.astimezone(UTC).date()
    last = (campaign.end_at.astimezone(UTC) - timedelta(microseconds=1)).date()
    if kind == "rolling":
        yesterday = now.astimezone(UTC).date() - timedelta(days=1)
        return _date_range(max(first, yesterday - timedelta(days=27)), min(last, yesterday))
    if kind == "paused":
        return _date_range(first + timedelta(days=2), min(first + timedelta(days=6), last))
    if kind == "completed":
        return _date_range(first, last)[::2]
    return []


def _interpolate_corridor(
    corridor: tuple[tuple[float, float], ...], count: int
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    segment_count = len(corridor) - 1
    for index in range(count):
        position = index * segment_count / (count - 1)
        segment = min(int(position), segment_count - 1)
        fraction = position - segment
        start, end = corridor[segment], corridor[segment + 1]
        points.append(
            (
                start[0] + (end[0] - start[0]) * fraction,
                start[1] + (end[1] - start[1]) * fraction,
            )
        )
    return points


def _anomaly_for(driver_index: int, day_offset: int, trip_index: int) -> str | None:
    if driver_index == 5 and day_offset == 0 and trip_index == 0:
        return "exclusion"
    if trip_index != 0 or day_offset > 2:
        return None
    anomaly_index = (driver_index - 1) * 3 + day_offset
    if anomaly_index >= 12:
        return None
    return ("stationary", "teleport", "gap", "loop", "poor_accuracy", "exclusion")[
        anomaly_index % 6
    ]


def _ping_specs(
    *,
    trip_key: str,
    driver_index: int,
    day_offset: int,
    trip_index: int,
    include_anomalies: bool = True,
    common_corridor: bool = False,
) -> tuple[list[tuple[float, float]], list[int], list[float], str | None]:
    rng = random.Random(f"{F7_SEED_VERSION}:{trip_key}")
    anomaly = _anomaly_for(driver_index, day_offset, trip_index) if include_anomalies else None
    count = 12 + rng.randrange(0, 7)
    corridor = CORRIDORS[
        1 if common_corridor or trip_index == 1 else (driver_index + trip_index) % 5
    ]
    coordinates = _interpolate_corridor(corridor, count)
    intervals = [60 + rng.randrange(0, 31) for _ in range(count - 1)]
    accuracy = [8.0 + rng.random() * 8.0 for _ in range(count)]
    if anomaly == "stationary":
        coordinates = [(6.5244, 3.3792)] * count
    elif anomaly == "teleport":
        coordinates[count // 2] = (6.7000, 3.2000)
    elif anomaly == "gap":
        intervals[count // 2] = 1200
    elif anomaly == "loop":
        coordinates = [
            (6.5100, 3.3700),
            (6.5200, 3.3800),
            (6.5300, 3.3900),
            (6.5200, 3.4000),
            (6.5100, 3.4100),
            (6.5000, 3.4000),
            (6.4900, 3.3900),
            (6.5000, 3.3800),
            (6.5100, 3.3700),
        ]
        intervals = [90] * (len(coordinates) - 1)
        accuracy = [10.0] * len(coordinates)
    elif anomaly == "poor_accuracy":
        accuracy = [180.0] * count
    elif anomaly == "exclusion":
        coordinates = _interpolate_corridor(CORRIDORS[5], count)
    else:
        coordinates = [
            (lat + rng.uniform(-0.00015, 0.00015), lon + rng.uniform(-0.00015, 0.00015))
            for lat, lon in coordinates
        ]
    return coordinates, intervals, accuracy, anomaly


def _assert_trip_lifecycle(
    trip: TripSession, campaign: Campaign, assignment: CampaignAssignment, kind: str
) -> None:
    if campaign.start_at is None or campaign.end_at is None or trip.ended_at is None:
        raise AppError("F7_SEED_INVALID_LIFECYCLE", "Campaign and trip windows must be complete")
    if not campaign.start_at <= trip.started_at <= trip.ended_at <= campaign.end_at:
        raise AppError("F7_SEED_INVALID_LIFECYCLE", "Trip falls outside its campaign window")
    allowed_campaign_statuses = {
        "rolling": {CampaignStatus.ACTIVE.value},
        "paused": {CampaignStatus.PAUSED.value},
        "completed": {CampaignStatus.COMPLETED.value},
    }
    if campaign.status not in allowed_campaign_statuses[kind]:
        raise AppError("F7_SEED_INVALID_LIFECYCLE", "Campaign status cannot own this trip class")
    if assignment.status not in {
        CampaignAssignmentStatus.ACTIVE.value,
        CampaignAssignmentStatus.COMPLETED.value,
    }:
        raise AppError("F7_SEED_INVALID_LIFECYCLE", "Assignment status cannot own trips")


async def _existing_trip_keys(session: AsyncSession, assignment_id) -> set[str]:
    result = await session.execute(
        select(TripSession).where(TripSession.assignment_id == assignment_id)
    )
    return {
        str(trip.trip_metadata["seed_trip_key"])
        for trip in result.scalars().all()
        if trip.trip_metadata.get("seed_version") == F7_SEED_VERSION
        and trip.trip_metadata.get("seed_trip_key")
    }


async def _create_trip(
    session: AsyncSession,
    *,
    campaign: Campaign,
    assignment: CampaignAssignment,
    asset: DriverAsset,
    kind: str,
    trip_day: date,
    day_offset: int,
    trip_index: int,
    existing_keys: set[str],
    settings: Settings,
) -> TripSession | None:
    trip_key = f"f7:{asset.index}:{trip_day.isoformat()}:{trip_index}"
    if trip_key in existing_keys:
        return None
    coordinates, intervals, accuracy, anomaly = _ping_specs(
        trip_key=trip_key,
        driver_index=asset.index,
        day_offset=day_offset,
        trip_index=trip_index,
        include_anomalies=kind != "completed",
        common_corridor=kind == "completed",
    )
    hour = 7 + ((asset.index + trip_index * 6) % 12)
    started_at = datetime.combine(trip_day, time(hour=hour, minute=15), tzinfo=UTC)
    offsets = [0]
    for interval in intervals:
        offsets.append(offsets[-1] + interval)
    ended_at = started_at + timedelta(seconds=offsets[-1] + 60)
    trip = TripSession(
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=asset.profile.id,
        vehicle_id=asset.vehicle.id,
        started_by_user_id=asset.user.id,
        status=TripSessionStatus.ENDED.value,
        started_at=started_at,
        ended_at=ended_at,
        end_reason="driver_finished",
        evidence_protocol_version=2,
        trip_metadata=f7_metadata(seed_trip_key=trip_key, anomaly=anomaly),
    )
    _assert_trip_lifecycle(trip, campaign, assignment, kind)
    session.add(trip)
    await session.flush()

    pings = [
        LocationPingCreate(
            recorded_at=started_at + timedelta(seconds=offsets[index]),
            lat=lat,
            lon=lon,
            accuracy_m=accuracy[index],
            speed_mps=7.0,
            heading_degrees=80.0,
            altitude_m=25.0,
            sequence_number=index,
            metadata=f7_metadata(sequence=index, anomaly=anomaly),
        )
        for index, (lat, lon) in enumerate(coordinates)
    ]
    payload = LocationPingBatchCreate(
        idempotency_key=f"{F7_SEED_VERSION}:{trip_key}:pings",
        batch_sequence=0,
        pings=pings,
        metadata=f7_metadata(seed_trip_key=trip_key),
    )
    digest = batch_payload_hash(payload)
    batch = LocationPingBatch(
        trip_session_id=trip.id,
        idempotency_key=payload.idempotency_key,
        batch_sequence=0,
        payload_hash_version=2,
        payload_hash=digest,
        pings_submitted=len(pings),
        pings_accepted=len(pings),
        pings_rejected=0,
        evidence_scope="manifest",
        received_at=ended_at,
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
                received_at=ended_at,
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
    sign_batch_receipt(batch, settings)
    await session.flush()

    entry_payload = TripEvidenceManifestEntryCreate(
        batch_sequence=0,
        idempotency_key=payload.idempotency_key,
        payload_hash_version=2,
        payload_hash=digest,
        submitted_count=len(pings),
    )
    session.add(
        TripEvidenceManifestEntry(
            trip_session_id=trip.id,
            **entry_payload.model_dump(),
        )
    )
    await session.flush()
    trip.evidence_manifest_version = 2
    trip.evidence_manifest_root_sha256 = manifest_root(
        trip_id=trip.id,
        entries=[entry_payload],
        ping_count=len(pings),
    )
    trip.evidence_manifest_batch_count = 1
    trip.evidence_manifest_ping_count = len(pings)
    trip.evidence_manifest_committed_at = ended_at
    trip.evidence_manifest_complete = True
    trip.evidence_manifest_verified_at = ended_at
    sign_manifest_receipt(trip, settings)
    trip.status = TripSessionStatus.SEALED.value
    trip.sealed_at = ended_at
    trip.seal_reason = TripSealReason.CLIENT_COMPLETE.value
    await session.flush()
    existing_keys.add(trip_key)
    return trip


async def _ensure_audit_backlog(
    session: AsyncSession,
    *,
    admin: User,
    campaigns: list[Campaign],
    assignments: list[CampaignAssignment],
) -> int:
    namespace = uuid5(NAMESPACE_URL, F7_SEED_VERSION)
    anchors: list[tuple[str, str, str]] = []
    for campaign in campaigns:
        anchors.extend(
            [
                ("campaign.created", "campaign", str(campaign.id)),
                ("campaign.updated", "campaign", str(campaign.id)),
            ]
        )
    for assignment in assignments:
        anchors.append(("campaign_assignment.created", "campaign_assignment", str(assignment.id)))
    for index, (action, entity_type, entity_id) in enumerate(anchors):
        event_id = uuid5(namespace, f"audit:{index}")
        if await session.get(AuditEvent, event_id) is not None:
            continue
        session.add(
            AuditEvent(
                id=event_id,
                actor_user_id=admin.id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                event_metadata=f7_metadata(backlog_index=index, historical=True),
                created_at=utc_now() - timedelta(days=len(anchors) - index),
            )
        )
    await session.flush()
    return len(anchors)


async def _ensure_assignment_authority(
    session, *, campaign, assignment, asset, admin, advertiser, settings, kind
):
    from app.seeds.demo_authority import (
        SeedStartAuthorityGraph,
        ensure_daily_terms,
        ensure_demo_start_authority,
    )

    if kind == "draft":
        await ensure_daily_terms(
            session,
            campaign=campaign,
            assignment=assignment,
            profile=asset.profile,
            admin=admin,
            advertiser=advertiser,
            settings=settings,
        )
    else:
        await ensure_demo_start_authority(
            session,
            graph=SeedStartAuthorityGraph(
                driver=asset.user,
                admin=admin,
                advertiser=advertiser,
                driver_profile=asset.profile,
                assignment=assignment,
                campaign=campaign,
                vehicle=asset.vehicle,
            ),
            settings=settings,
        )


async def build_rich_seed(
    session: AsyncSession,
    *,
    settings: Settings,
    admin: User,
    advertiser: User,
    organization: AdvertiserOrganization,
    traffic_profile: TrafficDensityProfile,
) -> RichSeedResult:
    now = utc_now()
    density = max_trips_per_day()
    drivers = [
        await _upsert_driver(session, index=index, settings=settings) for index in range(1, 10)
    ]
    campaigns: list[Campaign] = []
    for campaign_index, (name, status_value, kind) in enumerate(CAMPAIGN_SPECS, start=1):
        organization, advertiser = await business_owner(session, name)
        campaign = await _upsert_campaign(
            session,
            organization=organization,
            advertiser=advertiser,
            name=name,
            status_value=status_value,
            kind=kind,
            now=now,
        )
        await _ensure_creative(session, campaign, campaign_index)
        await _ensure_zones(
            session,
            campaign=campaign,
            campaign_index=campaign_index,
            advertiser=advertiser,
            settings=settings,
        )
        await _ensure_payout_rule(session, campaign=campaign, admin=admin)
        campaigns.append(campaign)

    assignment_specs = (
        (0, range(0, 5), CampaignAssignmentStatus.ACTIVE),
        (1, range(4, 7), CampaignAssignmentStatus.COMPLETED),
        (2, range(0, 3), CampaignAssignmentStatus.COMPLETED),
        (3, range(0, 2), CampaignAssignmentStatus.OFFERED),
    )
    assignments: list[CampaignAssignment] = []
    trip_inputs: list[tuple[Campaign, CampaignAssignment, DriverAsset, str]] = []
    for campaign_index, driver_indexes, assignment_status in assignment_specs:
        campaign = campaigns[campaign_index]
        kind = CAMPAIGN_SPECS[campaign_index][2]
        from app.seeds.demo_authority import require_seed_value

        advertiser = require_seed_value(
            await session.get(User, campaign.created_by_user_id), "campaign advertiser"
        )
        for driver_index in driver_indexes:
            asset = drivers[driver_index]
            assignment = await _ensure_assignment(
                session,
                campaign=campaign,
                asset=asset,
                admin=admin,
                status_value=assignment_status,
                advertiser=advertiser,
                settings=settings,
            )
            await _ensure_assignment_authority(
                session,
                campaign=campaign,
                assignment=assignment,
                asset=asset,
                admin=admin,
                advertiser=advertiser,
                settings=settings,
                kind=kind,
            )
            assignments.append(assignment)
            if kind != "draft":
                trip_inputs.append((campaign, assignment, asset, kind))

    existing_trip_count = int(
        await session.scalar(
            select(func.count(TripSession.id)).where(
                TripSession.trip_metadata["seed_version"].as_string() == F7_SEED_VERSION
            )
        )
        or 0
    )
    new_trips: list[TripSession] = []
    for campaign, assignment, asset, kind in trip_inputs:
        dates = _candidate_dates(campaign, kind, now)
        trips_per_day = density if kind == "rolling" else 2 if kind == "completed" else 1
        existing_keys = await _existing_trip_keys(session, assignment.id)
        for day_offset, trip_day in enumerate(reversed(dates)):
            for trip_index in range(trips_per_day):
                trip = await _create_trip(
                    session,
                    campaign=campaign,
                    assignment=assignment,
                    asset=asset,
                    kind=kind,
                    trip_day=trip_day,
                    day_offset=day_offset,
                    trip_index=trip_index,
                    existing_keys=existing_keys,
                    settings=settings,
                )
                if trip is None:
                    continue
                analytics_result = await recompute_trip_analytics(
                    session,
                    trip_id=trip.id,
                    metadata=f7_metadata(seed_step="analytics"),
                    settings=settings,
                )
                analytics_result.analytics.analytics_metadata = f7_metadata(
                    **analytics_result.analytics.analytics_metadata
                )
                for flag in analytics_result.fraud_flags:
                    flag.evidence = f7_metadata(**flag.evidence)
                estimate = await estimate_trip_impressions(
                    session,
                    trip_id=trip.id,
                    traffic_density_profile_id=traffic_profile.id,
                    metadata=f7_metadata(seed_step="impressions"),
                    settings=settings,
                )
                estimate.estimate_metadata = f7_metadata(**estimate.estimate_metadata)
                calculation, ledger, _ = await calculate_trip_payout(
                    session,
                    trip_id=trip.id,
                    payout_rule_id=None,
                    metadata=f7_metadata(seed_step="payout"),
                    settings=settings,
                    metadata_prefix=f7_metadata(),
                )
                await session.flush()
                new_trips.append(trip)
    audit_event_count = await _ensure_audit_backlog(
        session,
        admin=admin,
        campaigns=campaigns,
        assignments=assignments,
    )
    return RichSeedResult(
        drivers=drivers,
        campaigns=campaigns,
        assignments=assignments,
        new_trips=new_trips,
        existing_trip_count=existing_trip_count,
        audit_event_count=audit_event_count,
    )


STAFF_SPECS = (
    ("Hauwa Sani", "hauwa.sani@terraxmedia.com", "active", "Finance"),
    ("Chiamaka Obi", "chiamaka.obi@terraxmedia.com", "active", "Customer Service"),
    ("Olumide Fashola", "olumide.fashola@terraxmedia.com", "active", "Compliance"),
    ("Ibrahim Danjuma", "ibrahim.danjuma@terraxmedia.com", "active", "Operations"),
    ("Efe Okoro", "efe.okoro@terraxmedia.com", "active", "CEO"),
    ("Temitope Ojo", "temitope.ojo@terraxmedia.com", "invited", "Admin"),
    ("Aisha Garba", "aisha.garba@terraxmedia.com", "suspended", "Operations"),
)

COMPLAINT_TEXT = (
    (
        "advertiser",
        "billing_or_invoice",
        "open",
        "Could you send the invoice with our Wuse office address?",
        None,
    ),
    (
        "advertiser",
        "campaign_or_job",
        "answered",
        "Can the cars cover Aminu Kano Crescent before lunch?",
        "Yes, the morning route includes Aminu Kano Crescent.",
    ),
    (
        "advertiser",
        "other",
        "resolved",
        "The lunch menu on the back panel needs the new phone number.",
        "The corrected panel is fitted and the photos are attached.",
    ),
    (
        "driver",
        "pay_or_payout",
        "open",
        "My Tuesday trip ended near Yaba but the earnings are still pending.",
        None,
    ),
    (
        "driver",
        "campaign_or_job",
        "answered",
        "The rear sticker is lifting at the left corner.",
        "Please visit the Ikeja office tomorrow morning for a replacement.",
    ),
    (
        "driver",
        "trip_or_tracking",
        "resolved",
        "The app stopped recording after I left the fuel station.",
        "Your route has been checked and the missing section has been corrected.",
    ),
)


async def ensure_staff(session, *, settings):
    from app.seeds.demo import upsert_user

    staff = []
    for name, email, state, _department in STAFF_SPECS:
        person = await upsert_user(
            session,
            email=email,
            password="TerraxRoutes2026!",
            full_name=name,
            role=UserRole.ADMIN,
            settings=settings,
            status_value=state,
        )
        staff.append(person)
    await session.flush()
    return staff


async def ensure_portal_people(session, *, graph, settings):
    from app.models.complaint import Complaint, ComplaintMessage
    from app.models.driver_application import DriverApplication
    from app.seeds.demo import upsert_user

    staff = await ensure_staff(session, settings=settings)
    await _ensure_advertiser_directory(session, settings=settings)
    for name, email, stage in (
        ("Abdulrahman Yusuf", "abdulrahman.yusuf@mail.ng", "not_submitted"),
        ("Nneka Umeh", "nneka.umeh@mail.ng", "pending_review"),
        ("Ayodele Bakare", "ayodele.bakare@mail.ng", "approved"),
        ("Suleiman Idris", "suleiman.idris@mail.ng", "rejected"),
    ):
        existing_person = await session.scalar(select(User).where(User.email == email))
        person = await upsert_user(
            session,
            email=email,
            password="LagosRoutes2026!",
            full_name=name,
            role=UserRole.DRIVER,
            settings=settings,
            status_value=(
                existing_person.status
                if stage == "rejected" and existing_person is not None
                else "invited"
            ),
        )
        profile = await session.scalar(
            select(DriverProfile).where(DriverProfile.user_id == person.id)
        )
        if profile is None:
            profile = DriverProfile(
                user_id=person.id,
                onboarding_status="pending",
                service_city="Abuja",
                country_code="NG",
            )
            session.add(profile)
            await session.flush()
        application = await session.scalar(
            select(DriverApplication).where(DriverApplication.user_id == person.id)
        )
        if application is None:
            application = DriverApplication(
                user_id=person.id,
                driver_profile_id=profile.id,
                status="pending",
                status_reference_sha256=hashlib.sha256(email.encode()).hexdigest(),
                email=email,
                full_name=name,
                service_city="Abuja",
                country_code="NG",
            )
            session.add(application)
            await session.flush()
        from app.seeds.demo_authority import ensure_applicant_review

        await ensure_applicant_review(
            session,
            application=application,
            person=person,
            stage=stage,
            staff=staff,
            settings=settings,
        )
        if application.status == "rejected":
            person.status = "disabled"
            profile.onboarding_status = "rejected"
    now = utc_now()
    for i, (party, category, state, message, reply) in enumerate(COMPLAINT_TEXT):
        key = uuid5(NAMESPACE_URL, f"cardvert-preview:complaint:{i}")
        if await session.get(Complaint, key):
            continue
        owner = graph.advertiser if party == "advertiser" else graph.driver
        opened_at = now - timedelta(days=1 + i * 3, hours=i * 2)
        answered_at = opened_at + timedelta(hours=4 + i)
        complaint = Complaint(
            id=key,
            party=party,
            raised_by_user_id=owner.id,
            driver_profile_id=graph.driver_profile.id if party == "driver" else None,
            advertiser_organization_id=graph.organization.id if party == "advertiser" else None,
            category=category,
            status=state,
            assigned_to_user_id=staff[1].id,
            client_request_id=key,
            last_message_at=answered_at if reply else opened_at,
            resolved_at=answered_at if state == "resolved" else None,
            created_at=opened_at,
            updated_at=answered_at if reply else opened_at,
            resolved_by_user_id=staff[1].id if state == "resolved" else None,
        )
        session.add(complaint)
        await session.flush()
        session.add(
            ComplaintMessage(
                complaint_id=key,
                author_user_id=owner.id,
                author_side="complainant",
                body=message,
                created_at=opened_at,
                status_after="open",
                client_request_id=key,
            )
        )
        if reply:
            session.add(
                ComplaintMessage(
                    complaint_id=key,
                    author_user_id=staff[1].id,
                    author_side="staff",
                    body=reply,
                    created_at=answered_at,
                    status_after=state,
                    client_request_id=uuid5(key, "reply"),
                )
            )
    await session.flush()
    await _ensure_contact_work(session, graph=graph, staff=staff, settings=settings)
    await _ensure_reach_profiles(session)
    return staff


BUSINESS_CONTACTS = (
    ("Copper Finch Bakery", "Adesola Aderemi", "adesola.aderemi@copperfinch.ng"),
    ("Juniper Court Pharmacy", "Ijeoma Nwachukwu", "ijeoma.nwachukwu@junipercourt.ng"),
    ("Mango Grove Interiors", "Kabir Usman", "kabir.usman@mangogrove.ng"),
    ("Dove Crescent Laundry", "Ejiro Oghene", "ejiro.oghene@dovecrescent.ng"),
    ("Aster Vale Foods", "Yetunde Akinyemi", "yetunde.akinyemi@astervale.ng"),
    ("Cedar Bay Furnishings", "Uche Nnaji", "uche.nnaji@cedarbay.ng"),
    ("Oriole Books", "Halima Mohammed", "halima.mohammed@oriolebooks.ng"),
    ("Sable Ridge Travel", "Osahon Igbinosa", "osahon.igbinosa@sableridge.ng"),
    ("Linden Harbour Clothing", "Funmilayo Ajayi", "funmilayo.ajayi@lindenharbour.ng"),
    ("Beryl Lane Grocers", "Tamuno Briggs", "tamuno.briggs@beryllane.ng"),
)


async def _ensure_advertiser_directory(session, *, settings):
    from app.models.organization import MembershipRole
    from app.seeds.demo import upsert_membership, upsert_user

    for company, name, email in BUSINESS_CONTACTS:
        person = await upsert_user(
            session,
            email=email,
            password="AbujaBusiness2026!",
            full_name=name,
            role=UserRole.ADVERTISER,
            settings=settings,
        )
        organization = await session.scalar(
            select(AdvertiserOrganization).where(AdvertiserOrganization.name == company)
        )
        if organization is None:
            organization = AdvertiserOrganization(
                name=company,
                billing_email=email,
                country_code="NG",
                status="active",
                operational_contact_name=name,
                operational_contact_email=email,
                billing_contact_name=name,
            )
            session.add(organization)
            await session.flush()
        await upsert_membership(
            session,
            organization=organization,
            user=person,
            role=MembershipRole.OWNER,
        )
    await session.flush()


async def business_owner(session, campaign_name):
    company = campaign_name.split(" — ")[0]
    organization = await session.scalar(
        select(AdvertiserOrganization).where(AdvertiserOrganization.name == company)
    )
    from app.models.organization import OrganizationMembership

    person = await session.scalar(
        select(User)
        .join(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.role == "owner",
            OrganizationMembership.status == "active",
        )
    )
    if person is None:
        raise ValueError(f"Missing business contact for {company}")
    return organization, person


async def _ensure_contact_work(session, *, graph, staff, settings):
    from app.models.contact import DriverPhoneVersion, ManualDriverContactTask, WhatsappConsent
    from app.services.contacts import mask_phone, phone_fingerprint

    people = [graph.driver_profile, graph.rich.drivers[0].profile, graph.rich.drivers[1].profile]
    notes = (
        None,
        "Amina can visit the Ikeja office on Thursday.",
        "Chinedu was driving; call again after six.",
    )
    for index, (profile, note) in enumerate(zip(people, notes, strict=True)):
        key = uuid5(NAMESPACE_URL, f"cardvert-preview:contact:{profile.id}")
        if await session.get(ManualDriverContactTask, key):
            continue
        now = utc_now() - timedelta(days=3 - index)
        user = await session.get(User, profile.user_id)
        if user is None or user.phone is None:
            raise ValueError("Demo driver has no fictional saved phone")
        phone = DriverPhoneVersion(
            driver_profile_id=profile.id,
            version=1,
            phone_fingerprint=phone_fingerprint(user.phone, settings),
            masked_phone=mask_phone(user.phone),
            recorded_by_user_id=profile.user_id,
            recorded_at=now,
            verified_at=now,
        )
        session.add(phone)
        await session.flush()
        consent = WhatsappConsent(
            driver_profile_id=profile.id,
            phone_version_id=phone.id,
            version=1,
            purpose="Installation and trip updates",
            notice_version="contact-v1",
            granted_by_user_id=profile.user_id,
            granted_at=now,
        )
        session.add(consent)
        await session.flush()
        session.add(
            ManualDriverContactTask(
                id=key,
                driver_profile_id=profile.id,
                phone_version_id=phone.id,
                consent_id=consent.id,
                event_key=str(key),
                purpose="Arrange an installation visit",
                status="completed" if note else "open",
                created_at=now,
                completed_by_user_id=staff[1].id if note else None,
                completed_at=now + timedelta(hours=2) if note else None,
                completion_outcome=("reached" if index == 1 else "attempted") if note else None,
                completion_note=note,
            )
        )
    await session.flush()


async def _ensure_reach_profiles(session):
    from app.schemas.impressions import TrafficDensityProfileCreate
    from app.services.impressions import create_traffic_density_profile

    for name, description, state, density in (
        ("Abuja office traffic", "Weekday traffic around Wuse and Garki offices.", "active", "180"),
        (
            "Lagos weekend traffic",
            "Weekend traffic around Lagos shopping streets.",
            "inactive",
            "140",
        ),
    ):
        if await session.scalar(
            select(TrafficDensityProfile.id).where(TrafficDensityProfile.name == name)
        ):
            continue
        await create_traffic_density_profile(
            session,
            TrafficDensityProfileCreate(
                name=name,
                description=description,
                profile_type=TrafficDensityProfileType.URBAN,
                status=TrafficDensityProfileStatus(state),
                traffic_density_per_km=Decimal(density),
                dwell_impressions_per_minute=Decimal("4"),
                road_category_weight=Decimal("1"),
                morning_weight=Decimal("1.2"),
                midday_weight=Decimal("1"),
                evening_weight=Decimal("1.3"),
                night_weight=Decimal("0.7"),
                target_zone_weight=Decimal("1.2"),
                bonus_zone_weight=Decimal("1.35"),
                exclusion_zone_weight=Decimal("0"),
                is_default=False,
            ),
        )


async def ensure_golden_contributors(session, *, graph, settings):
    from app.seeds.demo import (
        trip_specs,
        upsert_assignment,
        upsert_payout_rule,
        upsert_trips_and_pings,
        upsert_user,
    )

    people = (
        ("Yewande Afolabi", "yewande.afolabi@mail.ng", "KRD-347-JM"),
        ("Obinna Onyekachi", "obinna.onyekachi@mail.ng", "LSR-528-HP"),
        ("Fatima Adamu", "fatima.adamu@mail.ng", "KJA-916-NB"),
        ("Chukwudi Agu", "chukwudi.agu@mail.ng", "FKJ-204-NP"),
    )
    for person_index, (name, email, plate) in enumerate(people, start=1):
        driver = await upsert_user(
            session,
            email=email,
            password="LagosRoutes2026!",
            full_name=name,
            role=UserRole.DRIVER,
            settings=settings,
        )
        profile = await session.scalar(
            select(DriverProfile).where(DriverProfile.user_id == driver.id)
        )
        if profile is None:
            profile = DriverProfile(
                user_id=driver.id,
                onboarding_status="active",
                service_city="Lagos",
                country_code="NG",
            )
            session.add(profile)
            await session.flush()
        vehicle = await session.scalar(
            select(Vehicle).where(Vehicle.driver_profile_id == profile.id)
        )
        if vehicle is None:
            vehicle = Vehicle(
                driver_profile_id=profile.id,
                plate_number=plate,
                plate_number_normalized=normalize_plate_number(plate),
                plate_country_code="NG",
                vehicle_type="car",
                make="Toyota",
                model="Corolla",
                color="White",
                year=2020,
                status="active",
            )
            session.add(vehicle)
            await session.flush()
        assignment = await upsert_assignment(
            session,
            campaign=graph.campaign,
            profile=profile,
            vehicle=vehicle,
            admin=graph.admin,
            driver=driver,
            settings=settings,
        )
        trips = await upsert_trips_and_pings(
            session,
            assignment=assignment,
            campaign=graph.campaign,
            profile=profile,
            vehicle=vehicle,
            driver=driver,
            settings=settings,
            specs=[
                (
                    key,
                    at + timedelta(minutes=person_index * 9),
                    [
                        (lat + person_index * 0.00009, lon - person_index * 0.00009)
                        for lat, lon in coordinates
                    ],
                )
                for key, at, coordinates in trip_specs(utc_now())
            ],
        )
        await upsert_payout_rule(session, campaign=graph.campaign, admin=graph.admin)
        for trip in trips:
            if await session.scalar(
                select(TripAnalytics.id).where(TripAnalytics.trip_session_id == trip.id)
            ):
                continue
            await recompute_trip_analytics(
                session, trip_id=trip.id, metadata=f7_metadata(), settings=settings
            )
            await estimate_trip_impressions(
                session,
                trip_id=trip.id,
                traffic_density_profile_id=graph.traffic_profile.id,
                metadata=f7_metadata(),
                settings=settings,
            )
            await calculate_trip_payout(
                session,
                trip_id=trip.id,
                payout_rule_id=None,
                metadata=f7_metadata(),
                settings=settings,
            )


async def _seed_cancelled_campaign(session, *, graph, staff, campaign, state):
    if state != "cancelled":
        return
    name = campaign.name
    from app.models.billing import CommercialTerms, PaymentReceipt, ReceiptAllocation
    from app.schemas.campaign_cancellations import CampaignCancellationCreate
    from app.services.billing import record_refund_settlement, reverse_payment_receipt
    from app.services.campaign_cancellations import request_campaign_cancellation

    reason = (
        "Please cancel the collection campaign; the van delivery has been delayed."
        if "Home" in name
        else "Please cancel the Island launch until the new branch is ready."
    )
    cancellation = await request_campaign_cancellation(
        session,
        actor_user_id=campaign.created_by_user_id,
        campaign_id=campaign.id,
        payload=CampaignCancellationCreate(
            client_request_id=uuid5(campaign.id, "cancellation"), reason=reason
        ),
    )
    assert cancellation.disposition == "cash_refund_due"
    terms = await session.scalar(
        select(CommercialTerms).where(CommercialTerms.campaign_id == campaign.id)
    )
    receipt = await session.scalar(
        select(PaymentReceipt)
        .join(ReceiptAllocation, ReceiptAllocation.receipt_id == PaymentReceipt.id)
        .where(ReceiptAllocation.commercial_terms_id == terms.id)
    )
    await reverse_payment_receipt(
        session,
        receipt_id=receipt.id,
        actor_user_id=staff[0].id,
        reason="Return the campaign payment after the advertiser's cancellation.",
    )
    await record_refund_settlement(
        session,
        commercial_terms_id=terms.id,
        receipt_id=receipt.id,
        actor_user_id=staff[0].id,
        amount=cancellation.refundable_amount,
        settlement_provider="bank_transfer",
        external_reference=f"RF-{campaign.id.hex[:12].upper()}",
        reason="Returned the full payment before printing began.",
    )


async def ensure_portal_campaigns(session, *, graph, staff, settings):
    from app.models.notification import NotificationType
    from app.seeds.demo import upsert_creative, upsert_zones
    from app.services.notifications import create_notification

    names = (
        (
            "Oriole Books — Yaba Book Fair",
            "draft",
            "Invite readers to the weekend book fair around Yaba.",
        ),
        (
            "Juniper Court Pharmacy — Garki Opening",
            "pending_review",
            "Visibility around Garki offices before the shop opens.",
        ),
        (
            "Copper Finch Bakery — Weekend Orders",
            "approved",
            "Promote weekend bread orders around Wuse II.",
        ),
        (
            "Marula Kitchens — Garki Office Lunch",
            "approved",
            "Bring weekday lunch deliveries to offices around Garki.",
        ),
        (
            "Mango Grove Interiors — Maitama Collection",
            "rejected",
            "Introduce the new furniture collection around Maitama.",
        ),
        (
            "Dove Crescent Laundry — Home Collection",
            "cancelled",
            "Reach households along the Lekki collection route.",
        ),
        (
            "Dove Crescent Laundry — Island Collection",
            "cancelled",
            "Introduce doorstep laundry collection around Victoria Island.",
        ),
    )
    names += (
        (
            "Marula Kitchens — Yaba Weekend Lunch",
            "draft",
            "Offer weekend lunch deliveries around Yaba homes.",
        ),
        (
            "Marula Kitchens — Maitama Office Lunch",
            "pending_review",
            "Bring weekday lunches to offices around Maitama.",
        ),
        (
            "Marula Kitchens — Wuse Weekend Catering",
            "approved",
            "Promote weekend catering orders around Wuse II.",
        ),
        (
            "Marula Kitchens — Lekki Lunch Collection",
            "cancelled",
            "Introduce a lunch collection point for Lekki residents.",
        ),
    )
    now = utc_now()
    for name, state, description in names:
        organization, advertiser = await business_owner(session, name)
        key = uuid5(NAMESPACE_URL, f"cardvert-preview:campaign:{name}")
        campaign = await session.get(Campaign, key)
        if campaign is None:
            campaign = Campaign(
                id=key,
                organization_id=organization.id,
                created_by_user_id=advertiser.id,
                name=name,
                description=description,
                status="approved" if state == "cancelled" else state,
                start_at=now + timedelta(days=7),
                end_at=now + timedelta(days=21),
                budget_amount=Decimal("1000000.00"),
                daily_budget_amount=Decimal("50000.00"),
                currency="NGN",
            )
            session.add(campaign)
            await session.flush()
            creative = await upsert_creative(session, campaign=campaign)
            from app.models.campaign import CreativeStatus
            from app.models.stored_file import FilePurpose
            from app.seeds.demo_authority import managed_seed_image, seed_campaign_financials
            from app.services.campaigns import decide_creative_review, submit_creative_for_review

            stored = await managed_seed_image(
                session,
                settings=settings,
                subject=advertiser,
                label=name.split(" — ")[0].lower().replace(" ", "-"),
                identity=str(creative.id),
                purpose=FilePurpose.CREATIVE.value,
                organization_id=campaign.organization_id,
                at=campaign.created_at + timedelta(minutes=90),
            )
            creative.stored_file_id = stored.id
            creative.asset_url = None
            creative.checksum = stored.checksum_sha256
            creative.status = "draft"
            await session.flush()
            from app.seeds.history import initial_action_history

            with initial_action_history(session, campaign.created_at + timedelta(hours=2)) as clock:
                if state != "draft":
                    await submit_creative_for_review(
                        session,
                        user_id=advertiser.id,
                        campaign_id=campaign.id,
                        creative_id=creative.id,
                    )
                if state in {"approved", "rejected", "cancelled"}:
                    clock[0] += timedelta(hours=1)
                    await decide_creative_review(
                        session,
                        admin_user_id=staff[2].id,
                        creative_id=creative.id,
                        target_status=CreativeStatus.APPROVED
                        if state == "cancelled"
                        else CreativeStatus(state),
                        rejection_reason="Please enlarge the phone number before printing."
                        if state == "rejected"
                        else None,
                    )
            if state == "draft":
                from app.models.billing import QuoteRequestSource
                from app.services.billing import request_custom_quote

                await request_custom_quote(
                    session,
                    actor_user_id=advertiser.id,
                    campaign_id=campaign.id,
                    source=QuoteRequestSource.IN_PLATFORM,
                    request_details={
                        "notes": "Please quote for weekend lunch deliveries around Yaba."
                        if "Marula" in name
                        else "Please quote for the Yaba book fair weekend."
                    },
                )
            else:
                await seed_campaign_financials(
                    session,
                    campaign=campaign,
                    admin=staff[0],
                    advertiser=advertiser,
                    production=False,
                    funding_fraction=Decimal("1")
                    if state == "cancelled"
                    else Decimal("0.5")
                    if state == "approved"
                    else Decimal("0"),
                    financial_at=now - timedelta(hours=12)
                    if state == "cancelled"
                    else campaign.created_at + timedelta(hours=6),
                    invoice_status={
                        "pending_review": "draft",
                        "approved": "issued",
                        "rejected": "void",
                        "cancelled": "issued",
                    }[state],
                )
            await upsert_zones(
                session,
                campaign=campaign,
                advertiser=advertiser,
                settings=settings,
                zone_specs=[
                    (
                        "Garki offices"
                        if "Garki Office Lunch" in name
                        else {
                            "draft": "Yaba bookshops",
                            "pending_review": "Garki offices",
                            "approved": "Wuse II shops",
                            "rejected": "Maitama homes",
                        }[state],
                        "target",
                        {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [3.36, 6.48] if state == "draft" else [7.43, 9.02],
                                    [3.40, 6.48] if state == "draft" else [7.51, 9.02],
                                    [3.40, 6.53] if state == "draft" else [7.51, 9.11],
                                    [3.36, 6.53] if state == "draft" else [7.43, 9.11],
                                    [3.36, 6.48] if state == "draft" else [7.43, 9.02],
                                ]
                            ],
                        },
                    )
                ]
                if state != "cancelled"
                else None,
            )
            await _seed_cancelled_campaign(
                session, graph=graph, staff=staff, campaign=campaign, state=state
            )
    from app.seeds.demo_authority import seed_campaign_financials

    unaccepted = graph.rich.campaigns[3]
    advertiser = await session.get(User, unaccepted.created_by_user_id)
    await seed_campaign_financials(
        session,
        campaign=unaccepted,
        admin=staff[0],
        advertiser=advertiser,
        production=False,
        accept_terms=False,
        financial_at=now - timedelta(hours=12),
    )
    for i, person in enumerate([graph.admin, graph.advertiser, graph.driver, *staff[:5]]):
        for j, kind in enumerate(
            (
                NotificationType.EVIDENCE_VERIFIED,
                NotificationType.COMPLAINT_REPLIED,
                NotificationType.PAYOUT_RELEASED,
            )
            if person.role == UserRole.DRIVER
            else (
                NotificationType.QUOTATION_READY,
                NotificationType.COMPLAINT_REPLIED,
                NotificationType.FUNDING_CONFIRMED,
            )
        ):
            await create_notification(
                session,
                recipient_user_id=person.id,
                type_key=kind,
                payload={
                    "campaign_id": str(graph.campaign.id),
                    "campaign_name": graph.campaign.name,
                },
                dedupe_key=f"cardvert-preview:notice:{i}:{j}",
            )
    for paused in await session.scalars(select(Campaign).where(Campaign.status == "paused")):
        key = uuid5(NAMESPACE_URL, f"cardvert-preview:pause:{paused.id}")
        if not await session.get(AuditEvent, key):
            session.add(
                AuditEvent(
                    id=key,
                    actor_user_id=staff[3].id,
                    action="admin.campaign.paused",
                    entity_type="campaign",
                    entity_id=str(paused.id),
                    event_metadata={
                        "reason": (
                            "Please hold lunch deliveries while the Ikeja kitchen is renovated."
                            if paused.name.startswith("Marula Kitchens")
                            else "Please hold deliveries while the Ikeja showroom is repainted."
                        ),
                        "pause_reason_kind": "operational",
                        "status_after": "paused",
                        "pause_version": paused.updated_at.isoformat(),
                        "previous_status": "active",
                        "new_status": "paused",
                    },
                )
            )
    await session.flush()


async def ensure_offer_review_work(session, *, graph, staff, settings):
    from app.models.installation_evidence import InstallationEvidenceSubmission
    from app.models.stored_file import FilePurpose
    from app.schemas.campaign_assignments import (
        CampaignAssignmentCreate,
        CampaignAssignmentTransition,
    )
    from app.schemas.installation_evidence import (
        InstallationEvidenceCreate,
        InstallationPhotoCreate,
    )
    from app.seeds.demo_authority import managed_seed_image, prepare_daily_offer
    from app.services.campaign_assignments import (
        accept_driver_assignment,
        create_campaign_assignment,
    )
    from app.services.installation_evidence import submit_installation_evidence

    campaign = await session.scalar(
        select(Campaign).where(Campaign.name == "Marula Kitchens — Wuse Weekend Catering")
    )
    seed_settings = settings.model_copy(
        update={
            "installation_evidence_uploader_roles": "driver,admin",
            "installation_evidence_required_views": "front,back,left,right,close_up",
            "installation_evidence_validity_hours": 168,
        }
    )
    for email, accept in (
        ("driver@demo.mobility.local", False),
        ("driver01@demo.mobility.local", False),
        ("driver02@demo.mobility.local", False),
        ("yewande.afolabi@mail.ng", True),
        ("obinna.onyekachi@mail.ng", True),
    ):
        person = await session.scalar(select(User).where(User.email == email))
        profile = await session.scalar(
            select(DriverProfile).where(DriverProfile.user_id == person.id)
        )
        vehicle = await session.scalar(
            select(Vehicle).where(Vehicle.driver_profile_id == profile.id)
        )
        assignment = await session.scalar(
            select(CampaignAssignment).where(
                CampaignAssignment.campaign_id == campaign.id,
                CampaignAssignment.driver_profile_id == profile.id,
            )
        )
        if assignment is None:
            offered_at = datetime.now(UTC)
            await prepare_daily_offer(
                session,
                campaign=campaign,
                profile=profile,
                admin=staff[3],
                advertiser=await session.get(User, campaign.created_by_user_id),
                settings=seed_settings,
                offered_at=offered_at,
            )
            creative = await session.scalar(
                select(CampaignCreative).where(CampaignCreative.campaign_id == campaign.id)
            )
            assignment = await create_campaign_assignment(
                session,
                admin_user_id=staff[3].id,
                settings=seed_settings,
                payload=CampaignAssignmentCreate(
                    campaign_id=campaign.id,
                    driver_profile_id=profile.id,
                    vehicle_id=vehicle.id,
                    creative_id=creative.id,
                    expires_at=offered_at + timedelta(days=1),
                    notes="Collect the catering panels at the Wuse office on Friday.",
                ),
            )
            if accept:
                await accept_driver_assignment(
                    session,
                    user_id=person.id,
                    assignment_id=assignment.id,
                    settings=seed_settings,
                    payload=CampaignAssignmentTransition(),
                )
        if not accept or await session.scalar(
            select(InstallationEvidenceSubmission.id).where(
                InstallationEvidenceSubmission.assignment_id == assignment.id
            )
        ):
            continue
        captured_at = datetime.now(UTC)
        photos = []
        for view in seed_settings.installation_evidence_views:
            stored = await managed_seed_image(
                session,
                settings=seed_settings,
                subject=person,
                label=view,
                purpose=FilePurpose.INSTALLATION_EVIDENCE.value,
                identity=str(assignment.id),
            )
            photos.append(InstallationPhotoCreate(view=view, stored_file_id=stored.id))
        await submit_installation_evidence(
            session,
            actor_user_id=person.id,
            actor_role="driver",
            assignment_id=assignment.id,
            settings=seed_settings,
            payload=InstallationEvidenceCreate(
                client_request_id=uuid5(assignment.id, "installation"),
                device_id=uuid5(assignment.id, "phone"),
                captured_at=captured_at,
                photos=photos,
            ),
        )

    from app.models.campaign_change import CampaignChangeRequest
    from app.schemas.campaign_changes import CampaignChangeCreate, CampaignChangePreviewCreate
    from app.services.campaign_changes import preview_campaign_change, request_campaign_change

    for subject, reason in (
        (graph.campaign, "Please extend the lunch deliveries for another week."),
        (graph.rich.campaigns[0], "Please cover the next week of office deliveries."),
    ):
        key = uuid5(subject.id, "extra-week")
        if await session.scalar(
            select(CampaignChangeRequest.id).where(CampaignChangeRequest.client_request_id == key)
        ):
            continue
        proposal = CampaignChangePreviewCreate(
            end_at=subject.end_at + timedelta(days=7), reason=reason
        )
        preview = await preview_campaign_change(
            session,
            actor_user_id=subject.created_by_user_id,
            campaign_id=subject.id,
            payload=proposal,
        )
        assert preview.outcome == "await_review"
        await request_campaign_change(
            session,
            actor_user_id=subject.created_by_user_id,
            campaign_id=subject.id,
            payload=CampaignChangeCreate(
                **proposal.model_dump(exclude_unset=True),
                client_request_id=key,
                source_sha256=preview.source_sha256,
                preview_sha256=preview.preview_sha256,
            ),
        )


async def ensure_completed_report_contributors(session, *, graph, settings):
    from app.seeds.demo import demo_metadata, upsert_trips_and_pings

    campaigns = await session.scalars(
        select(Campaign).where(
            Campaign.campaign_metadata["driver_story"].as_boolean() == True,  # noqa: E712
            Campaign.status.in_(("completed", "active")),
        )
    )
    for campaign in campaigns:
        advertiser = await session.get(User, campaign.created_by_user_id)
        originals = list(
            await session.scalars(
                select(TripSession)
                .where(
                    TripSession.campaign_id == campaign.id,
                    TripSession.driver_profile_id == graph.driver_profile.id,
                )
                .order_by(TripSession.started_at)
            )
        )
        routes = []
        for trip in originals:
            points = list(
                await session.execute(
                    select(func.ST_Y(LocationPing.geom), func.ST_X(LocationPing.geom))
                    .where(
                        LocationPing.trip_session_id == trip.id,
                    )
                    .order_by(LocationPing.recorded_at)
                )
            )
            routes.append((trip, [(lat, lon) for lat, lon in points]))
        for asset in graph.rich.drivers[:2]:
            assignment = await _ensure_assignment(
                session,
                campaign=campaign,
                asset=asset,
                admin=graph.admin,
                advertiser=advertiser,
                settings=settings,
                status_value=CampaignAssignmentStatus.COMPLETED,
            )
            await _ensure_assignment_authority(
                session,
                campaign=campaign,
                assignment=assignment,
                asset=asset,
                admin=graph.admin,
                advertiser=advertiser,
                settings=settings,
                kind="completed",
            )
            specs = [
                (
                    f"report-route:{trip.id}:{asset.index}:{leg}",
                    trip.started_at.replace(hour=6 if leg == 0 else 20, minute=asset.index * 10),
                    points,
                )
                for trip, points in routes
                for leg in range(2)
            ]
            trips = await upsert_trips_and_pings(
                session,
                campaign=campaign,
                assignment=assignment,
                profile=asset.profile,
                vehicle=asset.vehicle,
                driver=asset.user,
                specs=specs,
                settings=settings,
            )
            for trip in trips:
                await recompute_trip_analytics(
                    session,
                    trip_id=trip.id,
                    metadata=demo_metadata(driver_story=True),
                    settings=settings,
                )
                await estimate_trip_impressions(
                    session,
                    trip_id=trip.id,
                    traffic_density_profile_id=graph.traffic_profile.id,
                    metadata=demo_metadata(driver_story=True),
                    settings=settings,
                )
                await calculate_trip_payout(
                    session,
                    trip_id=trip.id,
                    payout_rule_id=None,
                    metadata=demo_metadata(driver_story=True),
                    settings=settings,
                )


async def ensure_portal_reports(session, *, graph, settings):
    from app.models.measurement import MeasurementRun
    from app.models.payout import EarningsLedgerEntry, PayoutCalculation
    from app.schemas.measurement import MeasurementRunCreate
    from app.schemas.report_issuances import ReportIssuanceCreate
    from app.services.measurement import issue_measurement_run
    from app.services.report_issuances import request_report_issuance

    campaigns = list(await session.scalars(select(Campaign).where(Campaign.status == "completed")))
    campaigns += [graph.campaign, graph.rich.campaigns[0]]
    campaigns += list(
        await session.scalars(
            select(Campaign).where(Campaign.name == "Beryl Lane Grocers — Market Routes")
        )
    )
    for campaign in campaigns:
        # Zero-pay trips have no ordinary payment entry, but frozen reports
        # require a durable zero-cost fact as well as positive-cost authority.
        calculations = (
            await session.scalars(
                select(PayoutCalculation).where(
                    PayoutCalculation.campaign_id == campaign.id,
                    PayoutCalculation.status == "calculated",
                    PayoutCalculation.final_payout == 0,
                )
            )
        ).all()
        for calculation in calculations:
            if await session.scalar(
                select(EarningsLedgerEntry.id).where(
                    EarningsLedgerEntry.payout_calculation_id == calculation.id
                )
            ):
                continue
            profile = await session.get(DriverProfile, calculation.driver_profile_id)
            session.add(
                EarningsLedgerEntry(
                    payout_calculation_id=calculation.id,
                    driver_profile_id=profile.id,
                    driver_user_id=profile.user_id,
                    campaign_id=campaign.id,
                    trip_session_id=calculation.trip_session_id,
                    vehicle_id=calculation.vehicle_id,
                    entry_type="trip_payout",
                    status="pending",
                    amount=Decimal("0.00"),
                    currency="NGN",
                    description="No earnings for this route",
                    occurred_at=calculation.calculated_at,
                    ledger_metadata=f7_metadata(formula_version="payout_v4"),
                )
            )
        await session.flush()
        if not await session.scalar(
            select(TripSession.id).where(TripSession.campaign_id == campaign.id).limit(1)
        ):
            continue
        key = uuid5(NAMESPACE_URL, f"cardvert-preview:measurement:{campaign.id}")
        run = await session.scalar(
            select(MeasurementRun).where(MeasurementRun.client_request_id == key)
        )
        if run is None:
            period_start = campaign.start_at
            period_end = min(utc_now(), campaign.end_at)
            if campaign.status != "completed":
                # Live audience exports require aligned whole UTC hours.
                aligned_start = period_start.replace(minute=0, second=0, microsecond=0)
                period_start = aligned_start + timedelta(hours=period_start != aligned_start)
                period_end = period_end.replace(minute=0, second=0, microsecond=0)
            run = await issue_measurement_run(
                session,
                actor_user_id=graph.admin.id,
                settings=settings,
                payload=MeasurementRunCreate(
                    campaign_id=campaign.id,
                    client_request_id=key,
                    period_start_at=period_start,
                    period_end_at=period_end,
                    test_only=False,
                ),
            )
        await request_report_issuance(
            session,
            actor_user_id=graph.admin.id,
            measurement_run_id=run.id,
            payload=ReportIssuanceCreate(client_request_id=uuid5(key, "publication")),
            settings=settings,
            admin=True,
        )


async def ensure_portal_audiences(session, *, graph, settings):
    from app.models.measurement import MeasurementRun
    from app.models.retargeting_source_link import RetargetingSourceLink
    from app.schemas.retargeting_source_links import RetargetingSourceLinkCreate
    from app.schemas.retargeting_sources import ManualInsightSourceCreate
    from app.services.audience import (
        create_retargeting_source,
        create_retargeting_source_link,
        materialize_exposure_segment,
    )
    from app.services.audience_delivery import export_exposure_segment

    for campaign in (graph.campaign, graph.rich.campaigns[0]):
        run = await session.scalar(
            select(MeasurementRun)
            .where(MeasurementRun.campaign_id == campaign.id)
            .order_by(MeasurementRun.created_at.desc())
            .limit(1)
        )
        if run is None:
            continue
        zone = await session.scalar(
            select(CampaignZone).where(
                CampaignZone.campaign_id == campaign.id, CampaignZone.zone_type == "target"
            )
        )
        insights: tuple[
            tuple[
                Literal["area-demand", "time-pattern", "contextual-affinity"],
                Literal["low", "medium", "high"],
            ],
            ...,
        ] = (
            ("area-demand", "high"),
            ("time-pattern", "medium"),
            ("contextual-affinity", "low"),
        )
        for category, confidence in insights:
            source = await create_retargeting_source(
                session,
                settings=settings,
                actor_user_id=campaign.created_by_user_id,
                idempotency_key=f"cardvert-preview:audience:{campaign.id}:{category}",
                payload=ManualInsightSourceCreate(
                    source_type="manual-insight",
                    provenance="advertiser-declared",
                    lawful_basis_reference="candidate-legitimate-interest",
                    lawful_basis_status="unapproved",
                    consent_disclaimer_status="not-reviewed",
                    expires_at=campaign.end_at,
                    dsr_owner_role="compliance-owner",
                    dsr_status="pending",
                    insight_category=category,
                    confidence_band=confidence,
                ),
            )
            existing = await session.scalar(
                select(RetargetingSourceLink).where(
                    RetargetingSourceLink.source_id == source.id,
                    RetargetingSourceLink.campaign_id == campaign.id,
                )
            )
            link = existing or await create_retargeting_source_link(
                session,
                settings=settings,
                actor_user_id=campaign.created_by_user_id,
                idempotency_key=f"cardvert-preview:link:{campaign.id}:{category}",
                payload=RetargetingSourceLinkCreate(
                    source_id=source.id,
                    campaign_id=campaign.id,
                    zone_id=zone.id,
                    start_at=run.period_start_at,
                    end_at=run.period_end_at,
                ),
            )
            segment = await materialize_exposure_segment(
                session, settings=settings, source_link_id=link.id, measurement_run_id=run.id
            )
            if category == "area-demand":
                await export_exposure_segment(
                    session,
                    settings=settings,
                    actor_user_id=campaign.created_by_user_id,
                    segment_id=segment.id,
                    idempotency_key=f"cardvert-preview:aggregate-export:{campaign.id}",
                )
    from app.schemas.retargeting_sources import WebsiteTrafficSourceCreate
    from app.services.audience import deactivate_retargeting_source

    for category in ("site-visitor", "content-interest"):
        source = await create_retargeting_source(
            session,
            settings=settings,
            actor_user_id=graph.advertiser.id,
            idempotency_key=f"cardvert-preview:website:{category}",
            payload=WebsiteTrafficSourceCreate(
                source_type="website-traffic",
                provenance="advertiser-declared",
                lawful_basis_reference="candidate-consent",
                lawful_basis_status="unapproved",
                consent_disclaimer_status="not-reviewed",
                expires_at=graph.campaign.end_at,
                dsr_owner_role="privacy-officer",
                dsr_status="pending",
                audience_category=category,
                aggregation_window_days=30,
            ),
        )
        if category == "content-interest":
            await deactivate_retargeting_source(
                session,
                settings=settings,
                actor_user_id=graph.advertiser.id,
                source_id=source.id,
                idempotency_key="cardvert-preview:website:deactivate",
            )


async def _prepare_portal_earnings(session, entries, settings):
    from app.services.earnings_release import release_pending_earnings_for_trip

    for entry in entries:
        await release_pending_earnings_for_trip(
            session, trip_id=entry.trip_session_id, settings=settings
        )
    await session.flush()


async def _review_seed_fraud_flags(session, *, campaign_id, actor_user_id):
    from app.models.trip_analytics import FraudFlag
    from app.services.fraud_holds import acknowledge_fraud_flag, resolve_fraud_flag

    flags = list(
        (
            await session.scalars(
                select(FraudFlag)
                .where(
                    FraudFlag.campaign_id == campaign_id,
                    FraudFlag.flag_type != "physical_spot_check_failed",
                )
                .order_by(FraudFlag.vehicle_id, FraudFlag.flag_type, FraudFlag.trip_session_id)
            )
        ).all()
    )
    by_vehicle = {}
    for flag in flags:
        by_vehicle.setdefault(flag.vehicle_id, []).append(flag)
    review_groups = [items[:3] for items in by_vehicle.values() if len(items) >= 3][:2]
    assert len(review_groups) == 2
    for vehicle_flags in review_groups:
        for flag, outcome, note in zip(
            vehicle_flags,
            ("acknowledged", "confirmed", "dismissed"),
            (
                None,
                "The car remained at the depot during the recorded trip.",
                "The driver was waiting at the market entrance; the route checks out.",
            ),
            strict=True,
        ):
            if flag.status != "open":
                continue
            await acknowledge_fraud_flag(session, flag_id=flag.id, actor_user_id=actor_user_id)
            if outcome != "acknowledged":
                if note is None:
                    raise ValueError("Expected demo fraud resolution note is missing")
                await resolve_fraud_flag(
                    session,
                    flag_id=flag.id,
                    actor_user_id=actor_user_id,
                    outcome=outcome,
                    resolution_note=note,
                )


async def ensure_trip_review_work(session, *, graph, staff, settings):
    from app.services.evidence_verification import (
        queue_physical_spot_check,
        resolve_physical_spot_check,
    )
    from app.services.trips import (
        apply_quarantined_ping_batch,
        discard_quarantined_ping_batch,
        payload_hash,
        quarantine_ping_batch,
    )

    if max_trips_per_day() > 0:
        await _review_seed_fraud_flags(
            session, campaign_id=graph.rich.campaigns[0].id, actor_user_id=staff[2].id
        )
    trips = list(
        (
            await session.scalars(
                select(TripSession)
                .where(TripSession.campaign_id == graph.rich.campaigns[0].id)
                .order_by(TripSession.started_at, TripSession.id)
                .limit(7)
            )
        ).all()
    )
    for _index, (trip, outcome, note) in enumerate(
        zip(
            trips[:4],
            ("pending", "pending", "passed", "failed"),
            (
                "Please check the rear panel at the Ikeja office.",
                "Meet the driver near Yaba market after the morning route.",
                "All panels are secure and the phone number is readable.",
                "The rear panel is peeling; arrange a replacement before the next route.",
            ),
            strict=False,
        )
    ):
        check = await queue_physical_spot_check(
            session,
            actor_user_id=staff[3].id,
            assignment_id=trip.assignment_id,
            trip_session_id=trip.id,
            client_request_id=uuid5(trip.id, "spot-check"),
            note=note,
            metadata={},
        )
        if outcome != "pending" and check.status == "pending":
            await resolve_physical_spot_check(
                session,
                verification_id=check.id,
                actor_user_id=staff[3].id,
                outcome=outcome,
                note=note,
                evidence={},
            )
    for trip, state in zip(trips[4:], ("quarantined", "applied", "discarded"), strict=False):
        payload = LocationPingBatchCreate(
            idempotency_key=f"{F7_SEED_VERSION}:f7:late:{trip.id}",
            batch_sequence=1 if trip.evidence_protocol_version == 2 else None,
            metadata=f7_metadata(),
            pings=[
                LocationPingCreate(
                    recorded_at=trip.started_at + timedelta(minutes=1),
                    lat=6.5100,
                    lon=3.3890,
                    accuracy_m=10.0,
                    sequence_number=0,
                )
            ],
        )
        result = await quarantine_ping_batch(
            session,
            trip=trip,
            payload=payload,
            digest=batch_payload_hash(payload)
            if trip.evidence_protocol_version == 2
            else payload_hash(payload),
            received_at=utc_now(),
            settings=settings,
            hash_version=2 if trip.evidence_protocol_version == 2 else 1,
        )
        late = result.quarantine
        if late is None:
            raise ValueError("Expected demo quarantined upload is missing")
        if late.status != "quarantined":
            continue
        if state == "applied":
            await apply_quarantined_ping_batch(
                session,
                trip_id=trip.id,
                quarantine_id=late.id,
                admin_user_id=staff[3].id,
                note="The upload matches the route recorded that morning.",
                settings=settings,
            )
        if state == "discarded":
            await discard_quarantined_ping_batch(
                session,
                trip_id=trip.id,
                quarantine_id=late.id,
                admin_user_id=staff[2].id,
                note="The upload repeats a point already recorded on this route.",
            )


async def ensure_portal_payouts(session, *, graph, staff, settings):
    from app.models.disbursement import (
        PayoutAutomaticAlert,
        PayoutAutomaticRun,
        PayoutBatch,
        PayoutLineReconciliationEvent,
    )
    from app.models.payee import Payee, PayeeBankAccount, PayeeBankAccountVersion, PayeeVersion
    from app.models.payout import EarningsLedgerEntry
    from app.services.disbursements import build_frozen_payout_line, freeze_batch_instruction_set

    entries = list(
        (
            await session.scalars(
                select(EarningsLedgerEntry)
                .where(
                    EarningsLedgerEntry.driver_profile_id == graph.driver_profile.id,
                    EarningsLedgerEntry.campaign_id == graph.campaign.id,
                    EarningsLedgerEntry.amount > 0,
                )
                .order_by(EarningsLedgerEntry.occurred_at)
            )
        ).all()
    )
    if len(entries) < 3:
        raise ValueError("The lunch-route driver needs three payable trips")
    payee = await session.scalar(select(Payee).where(Payee.subject_id == graph.driver_profile.id))
    version = await session.scalar(select(PayeeVersion).where(PayeeVersion.payee_id == payee.id))
    account = await session.scalar(
        select(PayeeBankAccountVersion)
        .join(PayeeBankAccount)
        .where(PayeeBankAccount.payee_id == payee.id)
    )
    await _prepare_portal_earnings(session, entries, settings)
    now = datetime.now(UTC)
    for index, state in ((0, "completed"), (2, "reserved")):
        key = uuid5(NAMESPACE_URL, f"cardvert-preview:payout:{index}")
        if await session.get(PayoutBatch, key):
            continue
        entry = entries[index]
        if entry.status != "available":
            raise ValueError("The lunch-route payment must pass the release checks")
        batch = PayoutBatch(
            id=key,
            status=state,
            currency="NGN",
            total_amount=entry.amount,
            created_by_user_id=staff[0].id,
            approved_by_user_id=staff[4].id if state == "completed" else None,
            approved_at=now if state == "completed" else None,
            created_at=now,
            submitted_at=now if state == "completed" else None,
            approval_mode="maker_checker",
        )
        line = build_frozen_payout_line(
            batch_id=key, entry=entry, payee_version=version, account_version=account
        )
        line.created_at = now
        if state == "completed":
            line.status = "succeeded"
            line.reservation_active = False
            line.provider_transfer_reference = f"TRF-{key.hex[:12].upper()}"
            line.reconciled_by_user_id = staff[0].id
            line.reconciled_at = now
            line.last_provider_evidence_at = line.reconciled_at
            entry.status = "paid"
        else:
            entry.status = "available"
        freeze_batch_instruction_set(batch, [line])
        session.add(batch)
        await session.flush()
        session.add(line)
        await session.flush()
        if state == "completed":
            session.add(
                PayoutLineReconciliationEvent(
                    line_id=line.id,
                    provider_event_id=f"TRX-{key.hex[:12].upper()}",
                    source="poll",
                    outcome="succeeded",
                    evidence_fingerprint=hashlib.sha256(key.bytes).hexdigest(),
                    provider_occurred_at=line.reconciled_at,
                    created_at=line.reconciled_at,
                    applied=True,
                    reconciled_by_user_id=staff[0].id,
                )
            )
    from app.models.disbursement import PayoutBatchLine

    existing_run = await session.scalar(
        select(PayoutAutomaticRun.id)
        .join(PayoutBatch, PayoutBatch.automatic_run_id == PayoutAutomaticRun.id)
        .join(PayoutBatchLine, PayoutBatchLine.batch_id == PayoutBatch.id)
        .where(PayoutBatchLine.bank_account_version_id == account.id)
        .limit(1)
    )
    if existing_run is None:
        await _prepare_automatic_batch(session, settings=settings)
    alert_key = uuid5(NAMESPACE_URL, "cardvert-preview:provider-alert")
    if not await session.get(PayoutAutomaticAlert, alert_key):
        _require_unavailable_payout_provider()
        session.add(
            PayoutAutomaticAlert(
                id=alert_key,
                kind="submission_blocked",
                dedupe_key=hashlib.sha256(alert_key.bytes).hexdigest(),
                driver_profile_id=graph.driver_profile.id,
                batch_id=uuid5(NAMESPACE_URL, "cardvert-preview:payout:2"),
                detail={"reason": "provider_unavailable"},
            )
        )
    await session.flush()

    await _ensure_payout_review_history(session, graph=graph, staff=staff, settings=settings)


def _require_unavailable_payout_provider():
    from app.jobs.disbursements import _adapter
    from app.services.disbursements import _submission_capabilities

    try:
        _submission_capabilities(_adapter({}))
    except AppError as exc:
        if exc.code != "DISBURSEMENT_PROVIDER_UNAVAILABLE":
            raise
    else:
        raise ValueError("The payment problem needs an unavailable worker provider")


async def _ensure_payout_review_history(session, *, graph, staff, settings):
    from app.models.payout import PayoutCorrectionOrder
    from app.services.automatic_payouts import set_automatic_payouts_paused
    from app.services.payout_corrections import (
        approve_correction_order,
        create_correction_order,
        submit_correction_order,
    )

    for trip, state, reason in zip(
        graph.trips,
        ("draft", "pending_approval", "approved", "rejected"),
        (
            "Please check the Yaba distance after the route was corrected.",
            "The Surulere return leg needs a second review.",
            "The route review is complete; please confirm the earnings.",
            "Please recheck the distance recorded near the fuel station.",
        ),
        strict=True,
    ):
        if await session.scalar(
            select(PayoutCorrectionOrder.id).where(
                PayoutCorrectionOrder.campaign_id == graph.campaign.id,
                PayoutCorrectionOrder.reason == reason,
            )
        ):
            continue
        order = await create_correction_order(
            session,
            campaign_id=graph.campaign.id,
            lagos_day=(trip.started_at + timedelta(hours=1)).date(),
            reason=reason,
            created_by_user_id=staff[0].id,
            settings=settings,
        )
        if state != "draft":
            await submit_correction_order(session, order_id=order.id, actor_user_id=staff[0].id)
        if state == "approved":
            await approve_correction_order(
                session,
                order_id=order.id,
                actor_user_id=staff[4].id,
                settings=settings,
            )
        if state == "rejected":
            from app.services.payout_corrections import reject_correction_order

            await reject_correction_order(session, order_id=order.id, actor_user_id=staff[4].id)
    recorded = await session.scalar(
        select(AuditEvent.id)
        .where(
            AuditEvent.action == "admin.payout_automatic.resumed",
            AuditEvent.actor_user_id == staff[4].id,
        )
        .limit(1)
    )
    if not recorded:
        await set_automatic_payouts_paused(
            session,
            paused=True,
            reason="Hold transfers while Finance checks today's bank advice.",
            actor_user_id=staff[0].id,
        )
        await set_automatic_payouts_paused(
            session,
            paused=False,
            reason="Finance has checked the bank advice; transfers can continue.",
            actor_user_id=staff[4].id,
        )


async def _prepare_automatic_batch(session, *, settings):
    from sqlalchemy import event

    from app.adapters.disbursement import FakeDisbursementAdapter
    from app.models.disbursement import (
        PayoutAutomaticRun,
        PayoutBatch,
        PayoutBatchLine,
        PayoutSubmissionIntent,
    )
    from app.services.automatic_payouts import run_automatic_payouts

    moment = utc_now()

    models = (PayoutAutomaticRun, PayoutBatch, PayoutBatchLine, PayoutSubmissionIntent, AuditEvent)

    def record_creation_time(seed_session, _flush_context, _instances):
        for target in seed_session.new:
            if isinstance(target, models):
                target.created_at = moment

    event.listen(session.sync_session, "before_flush", record_creation_time)
    adapter = FakeDisbursementAdapter()
    try:
        result = await run_automatic_payouts(
            session,
            settings=settings.model_copy(
                update={
                    "payout_automatic_approval_enabled": True,
                    "payout_automatic_frequency": "daily",
                    "payout_automatic_batch_limit_ngn": Decimal("250000.00"),
                }
            ),
            adapter=adapter,
            now=moment,
        )
    finally:
        event.remove(session.sync_session, "before_flush", record_creation_time)
    assert not adapter.calls
    if result["outcome"] != "completed" or not result.get("batch_count"):
        raise ValueError(f"The lunch-route automatic payout did not prepare: {result['outcome']}")

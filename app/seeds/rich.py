"""Append-only F7 demo data layered on top of the frozen slice-12 seed.

Every F7 trip has a stable date-based key. Existing trips, pings, analytics,
impressions, payouts, and ledger entries are never rewritten: a same-day rerun
is a no-op, while a later rerun only appends missing rolling-window dates that
still fit the campaign's stored lifecycle window.
"""

import os
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
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
from app.models.impression import TrafficDensityProfile
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
    ("F7 Lagos Commuter Reach", CampaignStatus.ACTIVE, "rolling"),
    ("F7 Mainland Retail Pause", CampaignStatus.PAUSED, "paused"),
    ("F7 Festive Island Wrap", CampaignStatus.COMPLETED, "completed"),
    ("F7 Airport Launch Draft", CampaignStatus.DRAFT, "draft"),
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
    await session.flush()

    profile = await session.scalar(select(DriverProfile).where(DriverProfile.user_id == user.id))
    if profile is None:
        onboarding_status = (
            DriverOnboardingStatus.ACTIVE if index <= 7 else DriverOnboardingStatus.SUSPENDED
        )
        profile = DriverProfile(
            user_id=user.id,
            onboarding_status=onboarding_status.value,
            license_number=f"DRV-F7-{index:03d}",
            service_city="Lagos",
            country_code="NG",
            profile_metadata=f7_metadata(service_area=DRIVER_AREAS[index - 1]),
        )
        session.add(profile)
        await session.flush()

    plate = f"DEMO-{100 + index}"
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
        return midnight - timedelta(days=40), midnight + timedelta(days=365)
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
            description=f"F7 rich demo {kind} campaign across Lagos.",
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
    name = f"F7 Campaign {index} Vehicle Creative"
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
                asset_url=f"https://example.com/f7-campaign-{index}.png",
                mime_type="image/png",
                width_px=1600,
                height_px=900,
                checksum=f"f7-demo-creative-{index}",
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
        name = f"F7 Campaign {campaign_index} {zone_type.value.title()} Zone"
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
                description=f"F7 Lagos {zone_type.value} zone.",
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
            formula_version="payout_v1",
            status=CampaignPayoutRuleStatus.ACTIVE.value,
            currency="NGN",
            base_rate_per_km=Decimal("165.00"),
            base_rate_per_active_hour=Decimal("1100.00"),
            target_zone_bonus_rate_per_km=Decimal("60.00"),
            bonus_zone_bonus_rate_per_km=Decimal("100.00"),
            estimated_impression_rate_per_1000=Decimal("225.00"),
            min_payout_per_trip=Decimal("1200.00"),
            max_payout_per_trip=Decimal("10000.00"),
            low_fraud_multiplier=Decimal("0.9000"),
            medium_fraud_multiplier=Decimal("0.7000"),
            high_fraud_multiplier=Decimal("0.2500"),
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
    assignment = CampaignAssignment(
        campaign_id=campaign.id,
        driver_profile_id=asset.profile.id,
        vehicle_id=asset.vehicle.id,
        assigned_by_user_id=admin.id,
        status=status_value.value,
        offered_at=offered_at,
        accepted_at=None if is_offered else offered_at + timedelta(minutes=10),
        activated_at=None if is_offered else offered_at + timedelta(minutes=20),
        completed_at=min(campaign.end_at - timedelta(minutes=1), now) if is_completed else None,
        notes="F7 deterministic demo assignment.",
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
    if trip_index != 0 or day_offset > 2:
        return None
    anomaly_index = (driver_index - 1) * 3 + day_offset
    if anomaly_index >= 12:
        return None
    return ("stationary", "teleport", "gap", "loop", "poor_accuracy", "exclusion")[
        anomaly_index % 6
    ]


def _ping_specs(
    *, trip_key: str, driver_index: int, day_offset: int, trip_index: int
) -> tuple[list[tuple[float, float]], list[int], list[float], str | None]:
    rng = random.Random(f"{F7_SEED_VERSION}:{trip_key}")
    anomaly = _anomaly_for(driver_index, day_offset, trip_index)
    count = 12 + rng.randrange(0, 7)
    corridor = CORRIDORS[(driver_index + trip_index) % 5]
    coordinates = _interpolate_corridor(corridor, count)
    intervals = [60 + rng.randrange(0, 31) for _ in range(count - 1)]
    accuracy = [8.0 + rng.random() * 8.0 for _ in range(count)]
    if anomaly == "stationary":
        coordinates = [(6.5244, 3.3792)] * count
    elif anomaly == "teleport":
        coordinates[count // 2] = (6.7000, 3.6000)
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
        end_reason="f7_demo_completed",
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
    while len(anchors) < 30:
        campaign = campaigns[len(anchors) % len(campaigns)]
        anchors.append(("payout.pipeline.reviewed", "campaign", str(campaign.id)))
    for index, (action, entity_type, entity_id) in enumerate(anchors[:30]):
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
                created_at=utc_now() - timedelta(days=29 - index),
            )
        )
    await session.flush()
    return 30


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
        (1, range(5, 7), CampaignAssignmentStatus.COMPLETED),
        (2, range(7, 9), CampaignAssignmentStatus.COMPLETED),
        (3, range(0, 2), CampaignAssignmentStatus.OFFERED),
    )
    assignments: list[CampaignAssignment] = []
    trip_inputs: list[tuple[Campaign, CampaignAssignment, DriverAsset, str]] = []
    for campaign_index, driver_indexes, assignment_status in assignment_specs:
        campaign = campaigns[campaign_index]
        kind = CAMPAIGN_SPECS[campaign_index][2]
        for driver_index in driver_indexes:
            asset = drivers[driver_index]
            assignment = await _ensure_assignment(
                session,
                campaign=campaign,
                asset=asset,
                admin=admin,
                status_value=assignment_status,
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
        trips_per_day = density if kind == "rolling" else 1
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
                )
                calculation.payout_metadata = f7_metadata(**calculation.payout_metadata)
                if ledger is not None:
                    ledger.ledger_metadata = f7_metadata(**ledger.ledger_metadata)
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

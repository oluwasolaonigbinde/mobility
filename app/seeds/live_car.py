"""REQ-312: keep the seeded demo live cars moving on a local demo stack.

The seed lays down 40 minutes of staggered history for each ``demo-live-v1``
trip. A five-minute worker job then submits one deterministic batch per missed
slot through the driver ingest path, so the advertiser's delayed live map keeps
showing both cars for up to 12 hours per trip. It runs only when
``DEMO_LIVE_CAR_REFRESH`` is set (the local compose worker) and never in
production. Privacy rules are untouched: the map still applies its delay,
bucket, window, rounding and parked checks to these points.
"""

import hashlib
import logging
import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.models.driver import DriverProfile
from app.models.trip import LocationPing, LocationPingBatch, TripSession
from app.schemas.trips import LocationPingBatchCreate, LocationPingCreate

logger = logging.getLogger(__name__)

LIVE_CAR_VERSION = "demo-live-v1"
LIVE_CAR_SLOT = timedelta(minutes=5)
LIVE_CAR_CAP = timedelta(hours=12)
LIVE_CAR_HISTORY = timedelta(minutes=40)
PINGS_PER_SLOT = 5
_PING_EVERY = LIVE_CAR_SLOT / PINGS_PER_SLOT
# One 4.7 km road inside both seeded target zones (Central Business District and
# Wuse II offices), well clear of the Three Arms exclusion. A car drives it out
# and back every 20 minutes, so it always moves more than 200 m in 30 minutes.
_ROAD = ((9.045, 7.455), (9.060, 7.495))
_LAP_SECONDS = 20 * 60
# Each trip keeps its own lane (about 440 m apart) and phase, plus a few metres of
# trip-specific jitter, so two cars never share a fix or a whole route.
_LANE_DEGREES = 0.004
_PHASE_SECONDS = 7 * 60
_JITTER_DEGREES = 0.00003


def _road_metres() -> float:
    (lat_a, lon_a), (lat_b, lon_b) = _ROAD
    middle = math.radians((lat_a + lat_b) / 2)
    return math.hypot((lat_b - lat_a) * 111_320, (lon_b - lon_a) * 111_320 * math.cos(middle))


LIVE_CAR_SPEED_MPS = round(_road_metres() / (_LAP_SECONDS / 2), 2)


def live_car_slot(at: datetime) -> datetime:
    return at.replace(minute=at.minute // 5 * 5, second=0, microsecond=0)


def _jitter(trip_id: UUID, at: datetime, axis: str) -> float:
    digest = hashlib.sha256(f"{trip_id}:{int(at.timestamp())}:{axis}".encode()).digest()
    return (digest[0] / 255 * 2 - 1) * _JITTER_DEGREES


def live_car_position(trip_id: UUID, path_offset: int, at: datetime) -> tuple[float, float]:
    phase = (at.timestamp() + path_offset * _PHASE_SECONDS) % _LAP_SECONDS / _LAP_SECONDS
    along = 1 - abs(2 * phase - 1)
    (lat_a, lon_a), (lat_b, lon_b) = _ROAD
    lat = lat_a + along * (lat_b - lat_a) + path_offset * _LANE_DEGREES
    lon = lon_a + along * (lon_b - lon_a)
    return (
        round(lat + _jitter(trip_id, at, "lat"), 6),
        round(lon + _jitter(trip_id, at, "lon"), 6),
    )


def live_car_key(trip_id: UUID, slot: datetime) -> str:
    return f"{LIVE_CAR_VERSION}:{trip_id}:{slot.astimezone(UTC):%Y%m%dT%H%MZ}"


def live_car_batch(
    *,
    trip_id: UUID,
    started_at: datetime,
    path_offset: int,
    slot: datetime,
    batch_sequence: int,
) -> LocationPingBatchCreate:
    """The batch for one five-minute slot: a pure function of the trip and the slot."""
    pings = []
    for index in range(PINGS_PER_SLOT):
        at = slot + index * _PING_EVERY
        lat, lon = live_car_position(trip_id, path_offset, at)
        pings.append(
            LocationPingCreate(
                recorded_at=at,
                lat=lat,
                lon=lon,
                accuracy_m=8,
                speed_mps=LIVE_CAR_SPEED_MPS,
                sequence_number=(at - started_at) // _PING_EVERY,
                metadata={"seed_version": LIVE_CAR_VERSION},
            )
        )
    return LocationPingBatchCreate(
        idempotency_key=live_car_key(trip_id, slot),
        batch_sequence=batch_sequence,
        pings=pings,
        metadata={"seed_version": LIVE_CAR_VERSION},
    )


async def end_capped_live_car(
    session: AsyncSession, *, trip: TripSession, settings: Settings
) -> None:
    """End a trip past the cap as its driver, sealing it on the evidence the server holds.

    A capped trip stays active until auto-end (2 hours without a receipt), and one
    active trip per vehicle blocks a fresh one, so the reseed ends it first through
    the driver End service with a complete manifest of the held batches.
    """
    from app.schemas.trips import (
        TripEndRequest,
        TripEvidenceManifestCreate,
        TripEvidenceManifestEntryCreate,
    )
    from app.services.trip_evidence import manifest_root
    from app.services.trips import end_driver_trip

    batches = await session.scalars(
        select(LocationPingBatch)
        .where(
            LocationPingBatch.trip_session_id == trip.id,
            LocationPingBatch.evidence_scope == "manifest",
        )
        .order_by(LocationPingBatch.batch_sequence)
    )
    entries = [
        TripEvidenceManifestEntryCreate.model_validate(
            {
                "batch_sequence": batch.batch_sequence,
                "idempotency_key": batch.idempotency_key,
                "payload_hash_version": batch.payload_hash_version,
                "payload_hash": batch.payload_hash,
                "submitted_count": batch.pings_submitted,
            }
        )
        for batch in batches
    ]
    ping_count = sum(entry.submitted_count for entry in entries)
    profile = await session.get(DriverProfile, trip.driver_profile_id)
    if profile is None:
        raise RuntimeError(f"demo live car {trip.id} has no driver profile")
    await end_driver_trip(
        session,
        user_id=profile.user_id,
        trip_id=trip.id,
        payload=TripEndRequest(
            end_reason="driver_finished",
            evidence_manifest=TripEvidenceManifestCreate(
                root_sha256=manifest_root(trip_id=trip.id, entries=entries, ping_count=ping_count),
                ping_count=ping_count,
                complete=True,
                entries=entries,
            ),
        ),
        settings=settings,
    )


def live_car_refresh_enabled(settings: Settings) -> bool:
    if not settings.demo_live_car_refresh:
        return False
    from app.seeds.demo import PRODUCTION_ENVIRONMENTS

    return settings.environment.strip().lower() not in PRODUCTION_ENVIRONMENTS


async def _catch_up(
    session: AsyncSession, *, trip_id: UUID, settings: Settings, now: datetime
) -> tuple[int, int]:
    from app.services.trips import ingest_location_ping_batch

    trip = await session.get(TripSession, trip_id)
    profile = await session.get(DriverProfile, trip.driver_profile_id) if trip else None
    if trip is None or profile is None:
        return 0, 0
    started = trip.started_at
    end = min(now, started + LIVE_CAR_CAP)
    last = await session.scalar(
        select(func.max(LocationPing.recorded_at)).where(LocationPing.trip_session_id == trip.id)
    )
    # Re-offer the last ping's slot (a duplicate), then every slot missed since.
    slot = max(live_car_slot(last), started) if last is not None else started
    accepted = duplicates = 0
    while slot + LIVE_CAR_SLOT <= end:
        sequence = await session.scalar(
            select(LocationPingBatch.batch_sequence).where(
                LocationPingBatch.trip_session_id == trip.id,
                LocationPingBatch.idempotency_key == live_car_key(trip.id, slot),
            )
        )
        if sequence is None:
            highest = await session.scalar(
                select(func.max(LocationPingBatch.batch_sequence)).where(
                    LocationPingBatch.trip_session_id == trip.id,
                    LocationPingBatch.evidence_scope == "manifest",
                )
            )
            sequence = 0 if highest is None else highest + 1
        result = await ingest_location_ping_batch(
            session,
            user_id=profile.user_id,
            trip_id=trip.id,
            payload=live_car_batch(
                trip_id=trip.id,
                started_at=started,
                path_offset=int(trip.trip_metadata.get("path_offset", 0)),
                slot=slot,
                batch_sequence=sequence,
            ),
            settings=settings,
        )
        if result.duplicate:
            duplicates += 1
        else:
            accepted += 1
        slot += LIVE_CAR_SLOT
    return accepted, duplicates


async def refresh_demo_live_cars(
    sessionmaker: async_sessionmaker[AsyncSession], *, settings: Settings, now: datetime
) -> dict[str, int]:
    """Feed every active ``demo-live-v1`` trip under the 12-hour cap up to ``now``."""
    summary = {"trips": 0, "accepted": 0, "duplicates": 0}
    if not live_car_refresh_enabled(settings):
        return summary
    async with sessionmaker() as session:
        trip_ids = list(
            await session.scalars(
                select(TripSession.id)
                .where(
                    TripSession.trip_metadata["seed_version"].as_string() == LIVE_CAR_VERSION,
                    TripSession.status == "active",
                    TripSession.started_at > now - LIVE_CAR_CAP,
                )
                .order_by(TripSession.id)
            )
        )
    for trip_id in trip_ids:
        try:
            async with sessionmaker() as session:
                accepted, duplicates = await _catch_up(
                    session, trip_id=trip_id, settings=settings, now=now
                )
                await session.commit()
        except AppError as exc:
            # A trip auto-ended or sealed meanwhile simply stops; reseeding starts a new one.
            logger.warning("demo live car %s not refreshed: %s", trip_id, exc.code)
            continue
        summary["trips"] += 1
        summary["accepted"] += accepted
        summary["duplicates"] += duplicates
    return summary

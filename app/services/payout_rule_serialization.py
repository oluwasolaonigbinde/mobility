import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def campaign_terms_lock_key(campaign_id: UUID) -> int:
    """Stable signed 64-bit key for the campaign's accepted payout terms."""
    digest = hashlib.sha256(f"payout-terms:campaign:{campaign_id}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


async def acquire_campaign_terms_lock(session: AsyncSession, campaign_id: UUID) -> None:
    """Serialize acceptance and revision publication for one campaign."""
    await session.execute(select(func.pg_advisory_xact_lock(campaign_terms_lock_key(campaign_id))))


async def acquire_campaign_terms_shared_lock(session: AsyncSession, campaign_id: UUID) -> None:
    """Allow concurrent evidence readers while excluding terms/cancellation writers.

    Acquire before any trip row lock; callers must never upgrade to exclusive.
    """
    await session.execute(
        select(func.pg_advisory_xact_lock_shared(campaign_terms_lock_key(campaign_id)))
    )


async def database_clock(session: AsyncSession) -> datetime:
    """Return wall-clock database time, with an aware UTC local fallback."""
    value = await session.scalar(select(func.clock_timestamp()))
    if value is None:
        raise RuntimeError("database clock returned no value")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

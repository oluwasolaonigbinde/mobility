"""Data lifecycle for location_pings: partition premake, coverage, retention.

All logic lives here per architecture §14.3.3 — the arq jobs in
app/jobs/data_lifecycle.py are thin wrappers, and the partition-coverage
health endpoint reuses the same coverage query. Every entry point accepts
an injectable ``now`` (defaulting to the database clock) per §14.3.5 so the
frozen-clock tests can drive month boundaries deterministically.

Partition bounds are UTC month boundaries. Bounds are always read from
pg_inherits + pg_get_expr — partition names are labels, never parsed.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.observability import capture_exception
from app.models.data_purge import DataPurgeAudit, DataPurgeEvent

logger = logging.getLogger(__name__)

PARENT_TABLE = "location_pings"
PARTITION_NAME_PATTERN = re.compile(r"^location_pings_p\d{4}_\d{2}$|^location_pings_legacy$")

# Session-scoped advisory lock key: same derivation scheme as the S1 paycap
# helper (sha256 -> first 8 bytes -> signed bigint), distinct namespace.
# Session-scoped (not pg_advisory_xact_lock) because DETACH ... CONCURRENTLY
# cannot run inside a transaction block — the lock must live on a dedicated
# autocommit connection for the whole retention run.
RETENTION_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"datalifecycle:ping-retention").digest()[:8],
    byteorder="big",
    signed=True,
)

# Premake runs entirely inside one transaction, so a transaction-scoped
# advisory lock is sufficient. Concurrent workers wait here, then refresh
# catalog coverage after the winning transaction commits.
PREMAKE_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"datalifecycle:partition-premake").digest()[:8],
    byteorder="big",
    signed=True,
)

BOUND_SQL = text(
    """
    SELECT
        child.relname AS name,
        pg_get_expr(child.relpartbound, child.oid) AS bound_expr,
        inh.inhdetachpending AS detach_pending
    FROM pg_inherits inh
    JOIN pg_class child ON child.oid = inh.inhrelid
    JOIN pg_class parent ON parent.oid = inh.inhparent
    JOIN pg_namespace ns ON ns.oid = parent.relnamespace
    WHERE parent.relname = :parent AND ns.nspname = current_schema()
    ORDER BY child.relname
    """
)

BOUND_EXPR_PATTERN = re.compile(
    r"FOR VALUES FROM \('(?P<lower>[^']+)'\) TO \('(?P<upper>[^']+)'\)"
)


@dataclass(frozen=True)
class PartitionInfo:
    name: str
    lower: datetime
    upper: datetime
    detach_pending: bool


def month_start(moment: datetime) -> datetime:
    moment = moment.astimezone(UTC)
    return datetime(moment.year, moment.month, 1, tzinfo=UTC)


def add_months(start: datetime, months: int) -> datetime:
    total = start.year * 12 + (start.month - 1) + months
    return datetime(total // 12, total % 12 + 1, 1, tzinfo=UTC)


def subtract_calendar_months(moment: datetime, months: int) -> datetime:
    anchor = month_start(moment)
    shifted = add_months(anchor, -months)
    # Preserve the intra-month offset so the cutoff is a plain instant, not
    # a month boundary; whole-partition comparison happens against upper
    # bounds anyway.
    return shifted + (moment.astimezone(UTC) - anchor)


def partition_name_for(start: datetime) -> str:
    return f"location_pings_p{start.strftime('%Y_%m')}"


def bound_literal(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("'%Y-%m-%d %H:%M:%S+00'")


def _parse_bound(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


async def db_now(executor: AsyncSession | AsyncConnection) -> datetime:
    result = await executor.execute(text("SELECT now()"))
    moment = result.scalar_one()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


async def list_partitions(executor: AsyncSession | AsyncConnection) -> list[PartitionInfo]:
    result = await executor.execute(BOUND_SQL, {"parent": PARENT_TABLE})
    partitions: list[PartitionInfo] = []
    for name, bound_expr, detach_pending in result.all():
        match = BOUND_EXPR_PATTERN.search(bound_expr or "")
        if match is None:
            # DEFAULT partitions are forbidden by design; surface loudly.
            raise RuntimeError(
                f"Unparseable partition bound for {name!r}: {bound_expr!r}"
            )
        partitions.append(
            PartitionInfo(
                name=name,
                lower=_parse_bound(match.group("lower")),
                upper=_parse_bound(match.group("upper")),
                detach_pending=bool(detach_pending),
            )
        )
    return sorted(partitions, key=lambda p: p.lower)


def covered_until(partitions: list[PartitionInfo], moment: datetime) -> datetime | None:
    """Upper bound of contiguous coverage containing ``moment`` (None if
    no partition covers it)."""
    upper = None
    for partition in partitions:
        if partition.detach_pending:
            continue
        if upper is None:
            if partition.lower <= moment < partition.upper:
                upper = partition.upper
        elif partition.lower <= upper:
            upper = max(upper, partition.upper)
    return upper


async def is_partitioned(executor: AsyncSession | AsyncConnection) -> bool:
    result = await executor.execute(
        text(
            "SELECT relkind::text FROM pg_class c"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE c.relname = :parent AND n.nspname = current_schema()"
        ),
        {"parent": PARENT_TABLE},
    )
    relkind = result.scalar_one_or_none()
    return relkind == "p"


async def premake_partitions(
    session: AsyncSession,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> dict[str, object]:
    """Idempotently ensure partitions cover the current UTC month through
    now + PARTITION_PREMAKE_MONTHS. Coverage-based, never name-based: the
    legacy partition covers the current month until it rolls over."""
    now = now or await db_now(session)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": PREMAKE_LOCK_KEY}
    )
    partitions = await list_partitions(session)
    created: list[str] = []
    current = month_start(now)
    for offset in range(settings.partition_premake_months + 1):
        start = add_months(current, offset)
        upper = add_months(start, 1)
        covered = any(
            p.lower <= start and upper <= p.upper and not p.detach_pending
            for p in partitions
        )
        if covered:
            continue
        name = partition_name_for(start)
        await session.execute(
            text(
                f"CREATE TABLE {name} PARTITION OF {PARENT_TABLE}"
                f" FOR VALUES FROM ({bound_literal(start)}) TO ({bound_literal(upper)})"
            )
        )
        created.append(name)
    await session.commit()
    return {"created": created, "existing": len(partitions)}


async def check_partition_coverage(
    executor: AsyncSession | AsyncConnection,
    *,
    now: datetime | None = None,
) -> tuple[bool, datetime | None]:
    """True iff a partition covers now + 1 month (the alarm horizon)."""
    now = now or await db_now(executor)
    partitions = await list_partitions(executor)
    horizon = add_months(month_start(now), 1) + (now - month_start(now))
    upper = covered_until(partitions, now)
    return (upper is not None and upper >= horizon), upper


async def _record_purge_event(
    session: AsyncSession,
    *,
    partition: PartitionInfo | None,
    event: DataPurgeEvent,
    row_count: int | None,
    retention_months: int,
    job_run_id: str,
) -> None:
    session.add(
        DataPurgeAudit(
            partition_name=partition.name if partition else None,
            range_from=partition.lower if partition else None,
            range_to=partition.upper if partition else None,
            event=event,
            row_count=row_count,
            retention_months=retention_months,
            job_run_id=job_run_id,
        )
    )
    await session.commit()


async def _has_purge_trail(session: AsyncSession, name: str) -> bool:
    result = await session.execute(
        text(
            "SELECT 1 FROM data_purge_audit trail"
            " WHERE trail.partition_name = :name"
            " AND trail.event IN ('purge_started', 'detach_finalized')"
            " AND trail.range_from IS NOT NULL AND trail.range_to IS NOT NULL"
            " AND EXISTS (SELECT 1 FROM data_purge_audit started"
            "             WHERE started.partition_name = trail.partition_name"
            "             AND started.event = 'purge_started'"
            "             AND started.range_from = trail.range_from"
            "             AND started.range_to = trail.range_to"
            "             AND started.row_count IS NOT NULL) LIMIT 1"
        ),
        {"name": name},
    )
    return result.scalar_one_or_none() is not None


async def _has_matching_started_event(
    session: AsyncSession, partition: PartitionInfo
) -> bool:
    result = await session.execute(
        text(
            "SELECT 1 FROM data_purge_audit started"
            " WHERE started.partition_name = :name"
            " AND started.event = 'purge_started'"
            " AND started.range_from = :range_from"
            " AND started.range_to = :range_to"
            " AND started.row_count IS NOT NULL"
            " AND NOT EXISTS (SELECT 1 FROM data_purge_audit dropped"
            "                 WHERE dropped.partition_name = started.partition_name"
            "                 AND dropped.event = 'dropped') LIMIT 1"
        ),
        {
            "name": partition.name,
            "range_from": partition.lower,
            "range_to": partition.upper,
        },
    )
    return result.scalar_one_or_none() is not None


async def _detached_orphans(session: AsyncSession) -> list[str]:
    """Standalone tables matching the partition naming pattern that are no
    longer in the partition tree (detached but not dropped)."""
    result = await session.execute(
        text(
            "SELECT c.relname FROM pg_class c"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = current_schema() AND c.relkind = 'r'"
            " AND (c.relname ~ '^location_pings_p\\d{4}_\\d{2}$'"
            "      OR c.relname = 'location_pings_legacy')"
            " AND NOT EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid)"
        )
    )
    return [row[0] for row in result.all()]


async def run_ping_retention(
    engine: AsyncEngine,
    session_factory,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> dict[str, object]:
    """Purge fully-expired partitions with append-only evidence.

    Holds a session-scoped advisory lock on a dedicated AUTOCOMMIT
    connection for the entire run; DETACH ... CONCURRENTLY executes on that
    same connection. A concurrent run exits as a no-op (try-lock).
    """
    job_run_id = uuid4().hex
    dropped: list[str] = []
    finalized: list[str] = []
    batches_purged = 0

    lock_conn = await engine.connect()
    try:
        autocommit = await lock_conn.execution_options(isolation_level="AUTOCOMMIT")
        acquired = (
            await autocommit.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": RETENTION_LOCK_KEY}
            )
        ).scalar_one()
        if not acquired:
            logger.info("job=ping_retention outcome=skipped reason=lock_held")
            return {"skipped": "lock_held"}

        try:
            async with session_factory() as session:
                now = now or await db_now(session)
                cutoff = subtract_calendar_months(now, settings.ping_retention_months)

                # Recovery first: a pending detach may be FINALIZEd (an
                # irreversible step toward destruction) only when this job's
                # own evidence trail claims it — a pre-existing
                # `purge_started` row — AND it is still retention-expired
                # under the current settings. Anything else (a manual detach,
                # a retention window that has since widened) is not ours to
                # destroy: log, alert, and leave it untouched.
                pending = [p for p in await list_partitions(session) if p.detach_pending]
                authorized: list[PartitionInfo] = []
                refused: list[tuple[PartitionInfo, bool, bool]] = []
                for partition in pending:
                    started = await _has_matching_started_event(session, partition)
                    expired = partition.upper <= cutoff
                    if started and expired:
                        authorized.append(partition)
                    else:
                        refused.append((partition, started, expired))
                # Release the session's read snapshot before DDL on the
                # autocommit connection.
                await session.rollback()
                for partition, started, expired in refused:
                    logger.error(
                        "job=ping_retention pending_detach=%s outcome=refused"
                        " purge_started=%s expired=%s",
                        partition.name,
                        started,
                        expired,
                    )
                if refused:
                    capture_exception(
                        RuntimeError(
                            "ping_retention refused to finalize pending detach(es)"
                            " without purge evidence and retention eligibility: "
                            + ", ".join(p.name for p, _, _ in refused)
                        )
                    )
                for partition in authorized:
                    await autocommit.execute(
                        text(
                            f"ALTER TABLE {PARENT_TABLE} DETACH PARTITION"
                            f" {partition.name} FINALIZE"
                        )
                    )
                    await _record_purge_event(
                        session,
                        partition=partition,
                        event=DataPurgeEvent.DETACH_FINALIZED,
                        row_count=None,
                        retention_months=settings.ping_retention_months,
                        job_run_id=job_run_id,
                    )
                    finalized.append(partition.name)

                # Recovery: drop detached-but-not-dropped orphans, but only
                # ones the evidence trail claims — never a table we cannot
                # account for.
                for name in await _detached_orphans(session):
                    if not await _has_purge_trail(session, name):
                        logger.error(
                            "job=ping_retention orphan=%s outcome=unclaimed_table", name
                        )
                        continue
                    await _drop_with_evidence(
                        session,
                        name=name,
                        partition=None,
                        retention_months=settings.ping_retention_months,
                        job_run_id=job_run_id,
                    )
                    dropped.append(name)

                # Main sweep: fully-expired partitions, oldest first. A
                # refused pending detach blocks any new DETACH CONCURRENTLY
                # on the parent, so skip the destructive sweep entirely
                # until an operator resolves it (the refusal above already
                # logged and alerted); the batch purge below stays safe.
                expired_partitions = (
                    []
                    if refused
                    else [
                        p
                        for p in await list_partitions(session)
                        if p.upper <= cutoff
                    ]
                )
                if refused:
                    logger.error(
                        "job=ping_retention outcome=sweep_skipped"
                        " reason=refused_pending_detach"
                    )
                for partition in expired_partitions:
                    row_count = (
                        await session.execute(
                            text(f"SELECT count(*) FROM {partition.name}")
                        )
                    ).scalar_one()
                    # Evidence strictly precedes destruction.
                    await _record_purge_event(
                        session,
                        partition=partition,
                        event=DataPurgeEvent.PURGE_STARTED,
                        row_count=row_count,
                        retention_months=settings.ping_retention_months,
                        job_run_id=job_run_id,
                    )
                    await autocommit.execute(
                        text(
                            f"ALTER TABLE {PARENT_TABLE} DETACH PARTITION"
                            f" {partition.name} CONCURRENTLY"
                        )
                    )
                    await _drop_with_evidence(
                        session,
                        name=partition.name,
                        partition=partition,
                        retention_months=settings.ping_retention_months,
                        job_run_id=job_run_id,
                    )
                    dropped.append(partition.name)

                # Batch purge: only batches with zero remaining pings (the
                # straddling-batch guarantee — pings.batch_id is ON DELETE
                # CASCADE, so a time-window predicate would delete retained
                # pings) that are also older than the retention window (a
                # recent zero-ping batch must keep serving idempotent
                # replays). Skipped entirely while a refused pending detach
                # exists: a detach-pending partition is invisible to new
                # queries through the parent, so NOT EXISTS would wrongly
                # see its batches as empty and the FK cascade would destroy
                # the very pings the refusal left untouched.
                if refused:
                    logger.error(
                        "job=ping_retention outcome=batch_purge_skipped"
                        " reason=refused_pending_detach"
                    )
                    await session.commit()
                    logger.info(
                        "job=ping_retention run_id=%s outcome=blocked"
                        " refused=%d",
                        job_run_id,
                        len(refused),
                    )
                    return {
                        "job_run_id": job_run_id,
                        "finalized": finalized,
                        "dropped": dropped,
                        "batches_purged": 0,
                        "refused_pending": [p.name for p, _, _ in refused],
                    }
                result = await session.execute(
                    text(
                        "DELETE FROM location_ping_batches b"
                        " WHERE NOT EXISTS (SELECT 1 FROM location_pings p"
                        "                   WHERE p.batch_id = b.id)"
                        " AND b.received_at < :cutoff"
                    ),
                    {"cutoff": cutoff},
                )
                batches_purged = result.rowcount or 0
                if batches_purged:
                    await _record_purge_event(
                        session,
                        partition=None,
                        event=DataPurgeEvent.BATCHES_PURGED,
                        row_count=batches_purged,
                        retention_months=settings.ping_retention_months,
                        job_run_id=job_run_id,
                    )
                else:
                    await session.commit()
        finally:
            await autocommit.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": RETENTION_LOCK_KEY}
            )
    finally:
        await lock_conn.close()

    logger.info(
        "job=ping_retention run_id=%s finalized=%d dropped=%d batches_purged=%d",
        job_run_id,
        len(finalized),
        len(dropped),
        batches_purged,
    )
    return {
        "job_run_id": job_run_id,
        "finalized": finalized,
        "dropped": dropped,
        "batches_purged": batches_purged,
    }


async def _drop_with_evidence(
    session: AsyncSession,
    *,
    name: str,
    partition: PartitionInfo | None,
    retention_months: int,
    job_run_id: str,
) -> None:
    """Atomically record 'dropped' evidence and drop the table in one
    transaction (DROP TABLE is transactional). The partial unique index
    allows exactly one 'dropped' row per partition; if the insert conflicts
    (evidence already claims this name was destroyed), something is wrong —
    roll back and fail closed rather than destroy a table the evidence
    cannot account for."""
    inserted = (
        await session.execute(
            text(
                "INSERT INTO data_purge_audit"
                " (partition_name, range_from, range_to, event, retention_months,"
                "  initiated_by, job_run_id)"
                " VALUES (:name, :range_from, :range_to, 'dropped', :retention_months,"
                "         'system', :job_run_id)"
                " ON CONFLICT (partition_name) WHERE event = 'dropped' DO NOTHING"
                " RETURNING id"
            ),
            {
                "name": name,
                "range_from": partition.lower if partition else None,
                "range_to": partition.upper if partition else None,
                "retention_months": retention_months,
                "job_run_id": job_run_id,
            },
        )
    ).scalar_one_or_none()
    if inserted is None:
        await session.rollback()
        logger.error(
            "job=ping_retention partition=%s outcome=drop_refused"
            " reason=dropped_evidence_conflict",
            name,
        )
        raise RuntimeError(
            f"Refusing to drop {name}: a 'dropped' evidence row already exists"
            " for this partition name — manual investigation required"
        )
    await session.execute(text(f"DROP TABLE {name}"))
    await session.commit()

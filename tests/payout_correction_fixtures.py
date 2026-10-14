import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from conftest import (
    create_test_user,
    fetch_earnings_ledger_entries,
)
from payout_fixtures import moving_points
from sqlalchemy import select
from test_trip_processing import add_pings

from app.models.payout import (
    AssignmentRuleBinding,
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCorrectionOrder,
)
from app.services.payout_corrections import (
    approve_correction_order,
    create_correction_order,
    execute_correction_order,
    submit_correction_order,
)
from app.services.payouts.common import lagos_day_for

RELEASE_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def service(db_sessionmaker, coro_factory):
    async def run():
        async with db_sessionmaker() as session:
            result = await coro_factory(session)
            await session.commit()
            return result

    return asyncio.run(run())


def create_order(db_sessionmaker, settings, graph, *, reason="test correction"):
    return service(
        db_sessionmaker,
        lambda session: create_correction_order(
            session,
            campaign_id=graph.campaign.id,
            lagos_day=lagos_day_for(graph.trip.started_at),
            reason=reason,
            created_by_user_id=graph.admin.id,
            settings=settings,
        ),
    )


def submit(db_sessionmaker, order_id, actor_id):
    return service(
        db_sessionmaker,
        lambda session: submit_correction_order(session, order_id=order_id, actor_user_id=actor_id),
    )


def approve(db_sessionmaker, settings, order_id, actor_id):
    return service(
        db_sessionmaker,
        lambda session: approve_correction_order(
            session, order_id=order_id, actor_user_id=actor_id, settings=settings
        ),
    )


def execute(db_sessionmaker, settings, order_id, actor_id, *, release_at=RELEASE_AT):
    return service(
        db_sessionmaker,
        lambda session: execute_correction_order(
            session,
            order_id=order_id,
            actor_user_id=actor_id,
            release_at=release_at,
            request_metadata={"source": "test"},
            settings=settings,
        ),
    )


def second_admin(db_sessionmaker, tag):
    return create_test_user(db_sessionmaker, email=f"approver-{tag}@example.com")


def submitted_order(db_sessionmaker, settings, graph, tag):
    """create -> submit, plus a second admin to approve (maker-checker)."""
    approver = second_admin(db_sessionmaker, tag)
    order = create_order(db_sessionmaker, settings, graph)
    submit(db_sessionmaker, order.id, graph.admin.id)
    return order, approver


def approved_order(db_sessionmaker, settings, graph, tag):
    order, approver = submitted_order(db_sessionmaker, settings, graph, tag)
    approve(db_sessionmaker, settings, order.id, approver.id)
    return order, approver


def reload_order(db_sessionmaker, order_id) -> PayoutCorrectionOrder:
    async def fetch():
        async with db_sessionmaker() as session:
            return await session.get(PayoutCorrectionOrder, order_id)

    return asyncio.run(fetch())


def void_trip_payout(db_sessionmaker, trip_id) -> None:
    async def run() -> None:
        async with db_sessionmaker() as session:
            entry = await session.scalar(
                select(EarningsLedgerEntry).where(
                    EarningsLedgerEntry.trip_session_id == trip_id,
                    EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value,
                )
            )
            entry.status = EarningsLedgerEntryStatus.VOIDED.value
            await session.commit()

    asyncio.run(run())


def set_trip_payout_status(db_sessionmaker, trip_id, status_value: str) -> None:
    async def run() -> None:
        async with db_sessionmaker() as session:
            entry = await session.scalar(
                select(EarningsLedgerEntry).where(
                    EarningsLedgerEntry.trip_session_id == trip_id,
                    EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value,
                )
            )
            entry.status = status_value
            await session.commit()

    asyncio.run(run())


def drift_inputs(db_sessionmaker, graph) -> None:
    """Cheapest real input drift (PR12): a new ping batch on the day's trip
    changes the trip's current ping-set fingerprint."""
    add_pings(
        db_sessionmaker,
        trip_id=graph.trip.id,
        points=moving_points(graph.trip.started_at + timedelta(minutes=5), minutes=5),
        idempotency_key=f"drift-{uuid4()}",
    )


def correction_entries(db_sessionmaker) -> list[EarningsLedgerEntry]:
    return [
        entry
        for entry in fetch_earnings_ledger_entries(db_sessionmaker)
        if (entry.ledger_metadata or {}).get("correction_order_id")
    ]


def mark_binding_unresolved(db_sessionmaker, assignment_id) -> None:
    async def run() -> None:
        async with db_sessionmaker() as session:
            binding = await session.scalar(
                select(AssignmentRuleBinding).where(
                    AssignmentRuleBinding.assignment_id == assignment_id
                )
            )
            binding.stationary_policy_marker = "ext-rm2-fail-closed"
            await session.commit()

    asyncio.run(run())

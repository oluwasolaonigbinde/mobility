"""Batched, staff-only list context. No route points or command authority."""

from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.driver import DriverProfile
from app.models.driver_application import DriverApplication
from app.models.payout import EarningsLedgerEntry
from app.models.trip import TripSession
from app.models.trip_analytics import FraudFlag
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.fraud_holds import fraud_hold_active_clause
from app.services.operator_search import operator_search


async def trip_contexts(session: AsyncSession, ids: set[UUID]) -> dict[UUID, dict[str, Any]]:
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(TripSession, User.full_name, Campaign.name, Vehicle.plate_number)
            .join(DriverProfile, TripSession.driver_profile_id == DriverProfile.id)
            .join(User, DriverProfile.user_id == User.id)
            .join(Campaign, TripSession.campaign_id == Campaign.id)
            .join(Vehicle, TripSession.vehicle_id == Vehicle.id)
            .where(TripSession.id.in_(ids))
        )
    ).all()
    return {
        trip.id: {
            "driver_name": driver,
            "campaign_name": campaign,
            "vehicle_plate": plate,
            "trip_started_at": trip.started_at,
            "driver_profile_id": trip.driver_profile_id,
            "campaign_id": trip.campaign_id,
            "assignment_id": trip.assignment_id,
        }
        for trip, driver, campaign, plate in rows
    }


async def staff_names(
    session: AsyncSession, driver_ids: set[UUID], campaign_ids: set[UUID]
) -> tuple[dict[UUID, str], dict[UUID, str]]:
    drivers = (
        {
            driver_id: name
            for driver_id, name in (
                await session.execute(
                    select(DriverProfile.id, User.full_name)
                    .join(User, DriverProfile.user_id == User.id)
                    .where(DriverProfile.id.in_(driver_ids))
                )
            ).all()
        }
        if driver_ids
        else {}
    )
    campaigns = (
        {
            campaign_id: name
            for campaign_id, name in (
                await session.execute(
                    select(Campaign.id, Campaign.name).where(Campaign.id.in_(campaign_ids))
                )
            ).all()
        }
        if campaign_ids
        else {}
    )
    return drivers, campaigns


async def flag_list_money(
    session: AsyncSession, flags: list[FraudFlag]
) -> dict[UUID, dict[str, Any]]:
    """Same existing ledger facts, fetched once for all visible trips."""
    ids = {flag.trip_session_id for flag in flags}
    if not ids:
        return {}
    active = (
        select(FraudFlag.id)
        .where(
            FraudFlag.trip_session_id == EarningsLedgerEntry.trip_session_id,
            fraud_hold_active_clause(),
        )
        .correlate(EarningsLedgerEntry)
        .exists()
    )
    rows = list(
        (
            await session.scalars(
                select(EarningsLedgerEntry)
                .where(
                    EarningsLedgerEntry.trip_session_id.in_(ids),
                    (EarningsLedgerEntry.status.in_(("available", "paid")))
                    | ((EarningsLedgerEntry.status == "pending") & active),
                )
                .order_by(EarningsLedgerEntry.id)
            )
        ).all()
    )
    by_trip: dict[UUID, list[EarningsLedgerEntry]] = defaultdict(list)
    for row in rows:
        if row.trip_session_id is not None:
            by_trip[row.trip_session_id].append(row)
    result: dict[UUID, dict[str, Any]] = {}
    for flag in flags:
        entries = by_trip[flag.trip_session_id]
        available = [e for e in entries if e.status in {"available", "paid"}]
        pending = [e for e in entries if e.status == "pending"]

        def net(items: list[EarningsLedgerEntry]) -> Decimal:
            return sum(
                (-e.amount if e.entry_type == "reversal" else e.amount for e in items), Decimal("0")
            )

        currencies = {e.currency for e in available}
        held_currencies = {e.currency for e in pending}
        if len(currencies) > 1 or len(held_currencies) > 1:
            raise RuntimeError("Trip pay has conflicting currencies")
        amount = net(available)
        held = max(net(pending), Decimal("0"))
        reversal = next((e for e in available if e.source_fraud_flag_id == flag.id), None)
        result[flag.id] = {
            "available_net": amount,
            "currency": next(iter(currencies), None),
            "reversal_entry_id": reversal.id if reversal else None,
            "reversal_recommended": flag.status != "dismissed" and reversal is None and amount > 0,
            "held_pending_net": held,
            "held_currency": next(iter(held_currencies), None) if held else None,
        }
    return result


async def applicants(
    session: AsyncSession, *, q: str | None, limit: int, offset: int, oldest_first: bool = False
) -> tuple[list[dict[str, Any]], int]:
    """One SQL population; linked pending profiles are represented by their application."""

    def columns(
        model: type[DriverApplication] | type[DriverProfile], kind: str, application: Any
    ) -> tuple[Any, ...]:
        return (
            literal(kind).label("kind"),
            model.id.label("id"),
            application.label("application_id"),
            (model.driver_profile_id if model is DriverApplication else model.id).label(
                "driver_profile_id"
            ),
            model.user_id,
            (model.full_name if model is DriverApplication else User.full_name).label("full_name"),
            (model.phone if model is DriverApplication else User.phone).label("phone"),
            (model.email if model is DriverApplication else User.email).label("email"),
            model.service_city,
            model.created_at,
        )

    submitted = select(*columns(DriverApplication, "application", DriverApplication.id)).where(
        DriverApplication.status == "pending"
    )
    no_application = (
        ~select(DriverApplication.id)
        .where(DriverApplication.driver_profile_id == DriverProfile.id)
        .correlate(DriverProfile)
        .exists()
    )
    added = (
        select(*columns(DriverProfile, "staff_added", literal(None)))
        .join(User, DriverProfile.user_id == User.id)
        .where(DriverProfile.onboarding_status == "pending", no_application)
    )
    if q and q.strip():
        submitted = submitted.where(
            operator_search(
                q,
                DriverApplication.full_name,
                DriverApplication.email,
                DriverApplication.phone,
                DriverApplication.service_city,
            )
        )
        added = added.where(
            operator_search(q, User.full_name, User.email, User.phone, DriverProfile.service_city)
        )
    population = union_all(submitted, added).subquery()
    total = int(await session.scalar(select(func.count()).select_from(population)) or 0)
    rows = (
        (
            await session.execute(
                select(population)
                .order_by(
                    population.c.created_at.asc()
                    if oldest_first
                    else population.c.created_at.desc(),
                    population.c.kind,
                    population.c.id,
                )
                .limit(limit)
                .offset(offset)
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows], total

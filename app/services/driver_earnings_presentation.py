"""Read-only driver presentation of persisted work and settlement evidence."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from starlette import status

from app.adapters.disbursement.paystack import build_disbursement_adapter
from app.core.errors import AppError
from app.models.disbursement import PayoutAutomaticRun, PayoutBatch, PayoutBatchLine
from app.models.payee import Payee
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip_analytics import FraudFlag
from app.schemas.payouts import EarningsWorkDayRead
from app.services.automatic_payouts import _clean_reason, automatic_payout_status
from app.services.drivers import get_required_driver_profile_with_user_by_user_id
from app.services.payout_debt import driver_money_balance
from app.services.payouts.read import driver_earnings_summary


def work_days(entry, calculation):
    if entry.entry_type == "trip_payout" and calculation is not None:
        amounts = calculation.amount_by_day or {}
    elif entry.entry_type in {"adjustment", "reversal", "debt_remainder"}:
        day = (entry.ledger_metadata or {}).get("lagos_day")
        amounts = {day: entry.amount} if day else {}
    else:
        amounts = {}
    if not amounts or sum((Decimal(str(v)) for v in amounts.values()), Decimal(0)) != entry.amount:
        return []
    return [EarningsWorkDayRead(day=day, amount=amount) for day, amount in amounts.items()]


async def enrich_driver_ledger(session, entries, responses, settings):
    ids = [entry.id for entry in entries]
    if not ids:
        return responses
    lines = (
        await session.execute(
            select(PayoutBatchLine, PayoutBatch, PayoutAutomaticRun)
            .join(PayoutBatch, PayoutBatch.id == PayoutBatchLine.batch_id)
            .outerjoin(PayoutAutomaticRun, PayoutAutomaticRun.id == PayoutBatch.automatic_run_id)
            .where(PayoutBatchLine.ledger_entry_id.in_(ids))
        )
    ).all()
    calculations = {
        row.id: row
        for row in (
            await session.scalars(
                select(PayoutCalculation).where(
                    PayoutCalculation.id.in_(
                        [
                            entry.payout_calculation_id
                            for entry in entries
                            if entry.payout_calculation_id
                        ]
                    )
                )
            )
        ).all()
    }
    runtime = await automatic_payout_status(session, adapter=build_disbursement_adapter(settings))
    today = datetime.now(UTC).astimezone(ZoneInfo("Africa/Lagos")).date().isoformat()
    balances = {
        currency: await driver_money_balance(
            session, driver_profile_id=entries[0].driver_profile_id, currency=currency
        )
        for currency in {entry.currency for entry in entries}
    }
    histories: dict = {}
    for row in lines:
        histories.setdefault(row[0].ledger_entry_id, []).append(row)
    for entry, response in zip(entries, responses, strict=True):
        response.work_days = work_days(entry, calculations.get(entry.payout_calculation_id))
        history = histories.get(entry.id, [])
        succeeded = [
            line for line, _, _ in history if line.status == "succeeded" and line.reconciled_at
        ]
        if entry.status == "paid" and len(succeeded) == 1 and succeeded[0].amount == entry.amount:
            response.paid_at = succeeded[0].reconciled_at
        response.payment_on_hold = (
            any(line.status == "failed" for line, _, _ in history) and not succeeded
        ) or balances[entry.currency].carry_forward_debt > 0
        response.paying_tonight = bool(
            entry.status == "available"
            and not response.payment_on_hold
            and runtime["runnable"]
            and runtime["frequency"] == "daily"
            and any(
                batch.approval_mode == "automatic"
                and batch.approved_at
                and batch.status in {"reserved", "submitted"}
                and line.status in {"reserved", "submitted"}
                and line.reservation_active
                and run is not None
                and run.period_key == today
                for line, batch, run in history
            )
        )
        if response.paying_tonight:
            payee = await session.scalar(
                select(Payee).where(
                    Payee.subject_id == entry.driver_profile_id, Payee.payee_type == "driver"
                )
            )
            reason, _, _ = await _clean_reason(session, entry=entry, payee=payee, settings=settings)
            response.paying_tonight = reason is None and bool(response.work_days)
    return responses


ACTIVE_HOLD_FLAG_STATUSES = ("open", "acknowledged", "confirmed")
LAGOS = ZoneInfo("Africa/Lagos")


def earnings_unavailable() -> AppError:
    return AppError(
        "EARNINGS_DAYS_UNAVAILABLE",
        "Your complete earnings history could not be verified",
        status_code=status.HTTP_409_CONFLICT,
    )


def group_earnings_days(entries, responses, held_trips: set[UUID]) -> list[dict]:
    """Daily totals from persisted work-day allocations (REQ-208; was daily-earnings.ts)."""
    groups: dict[tuple, dict] = {}
    for entry, response in zip(entries, responses, strict=True):
        # Debt remainders record settlement provenance, not another earning. A reversed
        # original remains economic until its reversal entry nets it.
        if entry.status == "voided" or entry.entry_type == "debt_remainder":
            continue
        if not response.work_days:
            raise earnings_unavailable()
        sign = -1 if entry.entry_type == "reversal" else 1
        for allocation in response.work_days:
            group = groups.setdefault(
                (allocation.day, entry.currency),
                {"amount": Decimal(0), "unpaid": Decimal(0), "members": []},
            )
            group["amount"] += sign * allocation.amount
            if entry.status != "paid":
                group["unpaid"] += sign * allocation.amount
            if allocation.amount != 0:
                group["members"].append((entry, response))
    days = []
    for (day, currency), group in sorted(groups.items(), key=lambda item: item[0][1]):
        members = group["members"]
        held = group["amount"] < 0 or any(
            response.payment_on_hold
            or entry.status == "reversed"
            or (entry.status == "paid" and not response.paid_at)
            or (entry.status != "paid" and entry.trip_session_id in held_trips)
            for entry, response in members
        )
        paid = bool(members) and all(
            entry.status == "paid" and response.paid_at for entry, response in members
        )
        tonight = bool(members) and all(
            entry.status == "available" and response.paying_tonight for entry, response in members
        )
        days.append(
            {
                "day": day,
                "currency": currency,
                "amount": group["amount"],
                "unpaid": group["unpaid"],
                "status": "on_hold"
                if held
                else "paid"
                if paid
                else "paying_tonight"
                if tonight
                else "being_checked",
                "paid_at": max(response.paid_at for _, response in members)
                if paid and not held
                else None,
                "trip_ids": list(
                    dict.fromkeys(
                        entry.trip_session_id for entry, _ in members if entry.trip_session_id
                    )
                ),
            }
        )
    days.sort(key=lambda row: row["day"], reverse=True)
    return days


def earnings_totals(days: list[dict], lifetime: dict[str, Decimal], today: date) -> list[dict]:
    """Today, this Monday-to-Sunday Lagos week, all time, and unpaid money on hold."""
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    totals = []
    for currency in sorted(lifetime):
        rows = [row for row in days if row["currency"] == currency]
        totals.append(
            {
                "currency": currency,
                "today": sum((row["amount"] for row in rows if row["day"] == today), Decimal(0)),
                "this_week": sum(
                    (row["amount"] for row in rows if week_start <= row["day"] <= week_end),
                    Decimal(0),
                ),
                "total": lifetime[currency],
                # Only unpaid money counts: a driver with debt sees every day on hold,
                # but money already paid is never "on hold".
                "on_hold": sum(
                    (max(row["unpaid"], Decimal(0)) for row in rows if row["status"] == "on_hold"),
                    Decimal(0),
                ),
            }
        )
    return totals


async def driver_earnings_days(session, *, user_id: UUID, settings, respond) -> dict:
    """One read for driver Home and Earnings: every day plus the headline totals."""
    profile, _ = await get_required_driver_profile_with_user_by_user_id(session, user_id)
    entries = list(
        await session.scalars(
            select(EarningsLedgerEntry)
            .where(
                EarningsLedgerEntry.driver_profile_id == profile.id,
                EarningsLedgerEntry.driver_user_id == user_id,
            )
            .order_by(EarningsLedgerEntry.occurred_at.desc(), EarningsLedgerEntry.id)
        )
    )
    responses = await enrich_driver_ledger(
        session, entries, [respond(entry) for entry in entries], settings
    )
    held_trips = set(
        await session.scalars(
            select(FraudFlag.trip_session_id).where(
                FraudFlag.driver_profile_id == profile.id,
                FraudFlag.status.in_(ACTIVE_HOLD_FLAG_STATUSES),
            )
        )
    )
    days = group_earnings_days(entries, responses, held_trips)
    summary = await driver_earnings_summary(
        session, user_id=user_id, currency=None, settings=settings
    )
    # The summary adds a zero row in the default currency for a driver with no entries.

    lifetime = {
        row.currency: row.lifetime_earned_amount
        for row in summary.totals_by_currency
        if row.ledger_entry_count
    }
    for row in days:
        lifetime.setdefault(row["currency"], Decimal(0))
    today = datetime.now(UTC).astimezone(LAGOS).date()
    return {"totals": earnings_totals(days, lifetime, today), "days": days}

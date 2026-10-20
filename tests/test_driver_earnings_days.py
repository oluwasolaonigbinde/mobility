"""REQ-208: driver daily earnings and headline totals come from one server read.

The grouping cases are the former frontend daily-earnings.ts cases, ported unchanged.
"""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from conftest import auth_headers, create_test_driver_profile, create_test_user
from payout_fixtures import PASSWORD, build_v4_graph, drive

from app.core.errors import AppError
from app.models.payout import EarningsLedgerEntry
from app.models.user import UserRole
from app.schemas.payouts import EarningsWorkDayRead
from app.services.driver_earnings_presentation import earnings_totals, group_earnings_days

TRIP = uuid4()


def row(
    *,
    amount="10.01",
    currency="NGN",
    entry_type="trip_payout",
    status="available",
    trip=TRIP,
    work_days=(("2026-10-09", "10.01"),),
    paid_at=None,
    paying_tonight=False,
    payment_on_hold=False,
):
    entry = SimpleNamespace(
        amount=Decimal(amount),
        currency=currency,
        entry_type=entry_type,
        status=status,
        trip_session_id=trip,
    )
    response = SimpleNamespace(
        work_days=[
            EarningsWorkDayRead(day=date.fromisoformat(day), amount=Decimal(value))
            for day, value in work_days
        ],
        paid_at=paid_at,
        paying_tonight=paying_tonight,
        payment_on_hold=payment_on_hold,
    )
    return entry, response


def show(*rows, held=frozenset()):
    return group_earnings_days([e for e, _ in rows], [r for _, r in rows], set(held))


def test_nets_exact_decimals_on_persisted_work_days():
    [day] = show(
        row(), row(amount="0.02", entry_type="reversal", work_days=[("2026-10-09", "0.02")])
    )
    assert (day["day"], day["amount"], day["status"]) == (
        date(2026, 10, 9),
        Decimal("9.99"),
        "being_checked",
    )


def test_splits_midnight_and_separates_currencies():
    days = show(
        row(work_days=[("2026-10-09", "5.00"), ("2026-10-10", "5.01")]),
        row(currency="USD"),
    )
    assert [(d["day"].isoformat(), d["currency"], str(d["amount"])) for d in days] == [
        ("2026-10-10", "NGN", "5.01"),
        ("2026-10-09", "NGN", "5.00"),
        ("2026-10-09", "USD", "10.01"),
    ]


def test_paid_needs_a_confirmed_transfer_date():
    paid_at = datetime(2026, 10, 10, 23, 30, tzinfo=UTC)
    assert show(row(status="paid"))[0]["status"] == "on_hold"
    [day] = show(row(status="paid", paid_at=paid_at))
    assert (day["status"], day["paid_at"]) == ("paid", paid_at)


def test_latest_payment_date_only_when_every_contribution_is_paid():
    first = datetime(2026, 10, 9, 20, tzinfo=UTC)
    second = datetime(2026, 10, 10, 20, tzinfo=UTC)
    paid = row(status="paid", paid_at=first)
    assert show(paid, row(entry_type="adjustment"))[0]["status"] == "being_checked"
    [day] = show(paid, row(status="paid", paid_at=second))
    assert (day["status"], day["paid_at"]) == ("paid", second)


def test_paying_tonight_needs_every_contribution_scheduled():
    assert show(row(paying_tonight=True))[0]["status"] == "paying_tonight"
    assert show(row(paying_tonight=True), row())[0]["status"] == "being_checked"


@pytest.mark.parametrize("status", ["pending", "available", "paid"])
def test_payment_hold_overrides_every_label(status):
    [day] = show(
        row(
            status=status,
            paying_tonight=True,
            payment_on_hold=True,
            paid_at=datetime(2026, 10, 9, 20, tzinfo=UTC),
        )
    )
    assert (day["status"], day["paid_at"]) == ("on_hold", None)


def test_public_trip_holds_hold_unpaid_earnings():
    assert show(row(status="pending"), held={TRIP})[0]["status"] == "on_hold"
    assert show(row(), held={TRIP})[0]["status"] == "on_hold"


def test_missing_allocations_withhold_every_figure():
    with pytest.raises(AppError) as caught:
        show(row(work_days=[]))
    assert caught.value.code == "EARNINGS_DAYS_UNAVAILABLE"


def test_reversed_original_nets_with_its_reversal_and_debt_provenance_is_ignored():
    [day] = show(
        row(amount="100.00", status="reversed", work_days=[("2026-10-09", "100.00")]),
        row(amount="20.00", entry_type="reversal", work_days=[("2026-10-09", "20.00")]),
        row(amount="20.00", entry_type="debt_remainder", work_days=[]),
    )
    assert (day["amount"], day["status"]) == (Decimal("80.00"), "on_hold")
    assert show(row(status="voided")) == []


def test_totals_use_the_lagos_monday_week_lifetime_and_unpaid_held_money():
    # Wednesday 14 October 2026: the week started on Monday 12 October.
    today = date(2026, 10, 14)
    paid_at = datetime(2026, 10, 13, 1, tzinfo=UTC)
    days = show(
        row(amount="5.00", work_days=[("2026-10-14", "5.00")]),
        row(amount="6.00", work_days=[("2026-10-18", "6.00")]),
        row(amount="7.00", status="paid", paid_at=paid_at, work_days=[("2026-10-12", "7.00")]),
        row(amount="11.00", work_days=[("2026-10-11", "11.00")]),
        # On hold: 3.00 unpaid plus 4.00 already paid; only the unpaid part is held.
        row(amount="3.00", payment_on_hold=True, work_days=[("2026-10-10", "3.00")]),
        row(amount="4.00", status="paid", paid_at=paid_at, work_days=[("2026-10-10", "4.00")]),
        # A held day that only nets money back never shows a negative hold.
        row(amount="2.00", entry_type="reversal", work_days=[("2026-10-09", "2.00")]),
    )
    [totals] = earnings_totals(days, {"NGN": Decimal("34.00")}, today)
    assert totals == {
        "currency": "NGN",
        "today": Decimal("5.00"),
        "this_week": Decimal("18.00"),
        "total": Decimal("34.00"),
        "on_hold": Decimal("3.00"),
    }


def test_endpoint_matches_the_ledger_and_summary(db_client, db_sessionmaker, settings):
    graph = build_v4_graph(
        db_sessionmaker, settings, "earnings-days", daily_rate_naira="600", daily_target_miles="1"
    )
    drive(db_sessionmaker, settings, graph.trip)
    admin = auth_headers(db_client, graph.admin.email, PASSWORD)
    calculated = db_client.post(
        f"/api/v1/admin/trips/{graph.trip.id}/calculate-payout", headers=admin, json={}
    )
    assert calculated.status_code == 200, calculated.text
    today = datetime.now(UTC).astimezone(ZoneInfo("Africa/Lagos")).date()

    async def seed(**metadata):
        async with db_sessionmaker() as session:
            session.add(
                EarningsLedgerEntry(
                    driver_profile_id=graph.profile.id,
                    driver_user_id=graph.driver.id,
                    campaign_id=graph.campaign.id,
                    vehicle_id=graph.vehicle.id,
                    entry_type="adjustment",
                    status="available",
                    amount=Decimal("12.34"),
                    currency="NGN",
                    description="Synthetic adjustment",
                    occurred_at=datetime.now(UTC),
                    ledger_metadata=metadata,
                )
            )
            await session.commit()

    asyncio.run(seed(lagos_day=today.isoformat()))
    driver = auth_headers(db_client, graph.driver.email, PASSWORD)
    response = db_client.get("/api/v1/driver/earnings/days", headers=driver)
    assert response.status_code == 200, response.text
    body = response.json()
    summary = db_client.get("/api/v1/driver/earnings/summary", headers=driver).json()
    [lifetime] = summary["totals_by_currency"]
    [totals] = body["totals"]
    assert totals["total"] == lifetime["lifetime_earned_amount"] == "612.34"
    assert sum(Decimal(day["amount"]) for day in body["days"]) == Decimal("612.34")
    assert totals["today"] == next(
        day["amount"] for day in body["days"] if day["day"] == today.isoformat()
    )
    assert Decimal(totals["this_week"]) >= Decimal("12.34")
    assert all(day["trip_ids"] in ([], [str(graph.trip.id)]) for day in body["days"])

    other = create_test_user(
        db_sessionmaker,
        email="earnings-days-other@example.com",
        role=UserRole.DRIVER,
        password=PASSWORD,
    )
    create_test_driver_profile(db_sessionmaker, user_id=other.id)
    stranger = db_client.get(
        "/api/v1/driver/earnings/days", headers=auth_headers(db_client, other.email, PASSWORD)
    )
    assert stranger.json() == {"totals": [], "days": []}
    assert db_client.get("/api/v1/driver/earnings/days", headers=admin).status_code == 403

    # An entry without a work day withholds every figure rather than inventing totals.
    asyncio.run(seed())
    broken = db_client.get("/api/v1/driver/earnings/days", headers=driver)
    assert broken.status_code == 409
    assert broken.json()["error"]["code"] == "EARNINGS_DAYS_UNAVAILABLE"

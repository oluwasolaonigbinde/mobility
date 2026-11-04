"""Historical money parity, reconciled with REQ-251's explicit seed removals.

The original frozen baseline had 300 calculations and ledger rows. Trip
identity uses campaign, driver, dates and seed key; report-route keys omit their
random source UUID. Hashes cover each exact amount and ledger-to-trip identity.
Storage/scanning are synthetic; no payment provider is contacted.

REQ-251 removes driver05's duplicate Cedar Bay assignment (five trips), and
omits seven zero-pay ledger entries. Reconstructing only those historical rows
must recover the ORIGINAL hashes, protecting all unchanged values independently
of today's calculation and ledger implementations.
REQ-295 also replaces four synthetic email domains; only those identity labels
are restored for this historical comparison, never their money values.
"""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from test_seed_demo import seed_demo_graph
from test_seed_demo import seed_private_storage as seed_private_storage

from app.models.campaign import Campaign
from app.models.driver import DriverProfile
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip import TripSession
from app.models.user import User
from app.seeds import demo, rich


def _digest(rows: list) -> str:
    return hashlib.sha256(
        json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _stable_trip_identity(name, email, start, end, metadata) -> list[str]:
    # REQ-295 / 10e006fb moved these synthetic identities off real-looking domains.
    # Reconstruct only their historical labels; amounts and all other facts stay pinned.
    historical_emails = {
        f"{name}@demo.mobility.local": f"{name}@mail.ng"
        for name in ("yewande.afolabi", "obinna.onyekachi", "fatima.adamu", "chukwudi.agu")
    }
    email = historical_emails.get(email, email)
    key = metadata["seed_trip_key"]
    if key.startswith("report-route:"):
        prefix, _random_source_trip_id, driver_index, leg = key.split(":")
        key = f"{prefix}:{driver_index}:{leg}"
    return [name, email, start.isoformat(), end.isoformat(), key]


def _removed_duplicate_calculations() -> list[list[str]]:
    # Exact historical rows, independently reproduced from be1fc9de. The seed's
    # campaign-1 range changed from range(4, 7) to range(5, 7), retaining driver05
    # on campaign 0 only. No other trip or price is allowed to change.
    return [
        [
            "Cedar Bay Furnishings — Jabi Showroom",
            "driver05@demo.mobility.local",
            f"2026-09-{day}T12:15:00+00:00",
            f"2026-09-{day}T{end}+00:00",
            f"f7:5:2026-09-{day}:0",
            amount,
            amount,
            "NGN",
        ]
        for day, end, amount in (
            ("07", "12:34:49", "344.86"),
            ("08", "12:29:08", "353.74"),
            ("09", "12:36:53", "322.67"),
            ("10", "12:34:58", "344.95"),
            ("11", "12:29:39", "118.15"),
        )
    ]


def _removed_zero_ledger() -> list[list[str]]:
    return [
        [
            "Aster Vale Foods — Garki Deliveries",
            f"driver0{driver}@demo.mobility.local",
            f"2026-10-{day}T{start}+00:00",
            f"2026-10-{day}T{end}+00:00",
            f"f7:{driver}:2026-10-{day}:0",
            "trip_payout",
            "pending",
            "0.00",
            "NGN",
        ]
        for driver, day, start, end in (
            (1, "19", "08:15:00", "08:30:57"),
            (2, "17", "09:15:00", "09:29:58"),
            (2, "18", "09:15:00", "09:36:17"),
            (3, "19", "10:15:00", "10:35:38"),
            (4, "17", "11:15:00", "11:35:15"),
            (4, "18", "11:15:00", "11:33:03"),
            (5, "19", "12:15:00", "12:31:58"),
        )
    ]


def test_seed_pay_and_ledger_match_before_slimdown(
    postgis_db_sessionmaker, settings, monkeypatch
) -> None:
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "1")
    monkeypatch.setattr(demo, "utc_now", lambda: now)
    monkeypatch.setattr(rich, "utc_now", lambda: now)

    async def fixed_cancellation_clock(_session):
        return now

    # Refund seed facts are also dated by the frozen seed clock. Otherwise this
    # exact historical baseline ages out of its 24-hour window on a later day.
    monkeypatch.setattr(
        "app.services.campaign_cancellations.database_clock", fixed_cancellation_clock
    )
    seed_demo_graph(postgis_db_sessionmaker, settings)

    async def read_money():
        async with postgis_db_sessionmaker() as session:
            trips = (
                await session.execute(
                    select(
                        TripSession.id,
                        Campaign.name,
                        User.email,
                        TripSession.started_at,
                        TripSession.ended_at,
                        TripSession.trip_metadata,
                    )
                    .join(Campaign, Campaign.id == TripSession.campaign_id)
                    .join(DriverProfile, DriverProfile.id == TripSession.driver_profile_id)
                    .join(User, User.id == DriverProfile.user_id)
                    .where(TripSession.id.in_(select(PayoutCalculation.trip_session_id)))
                )
            ).all()
            identities = {
                trip_id: _stable_trip_identity(name, email, start, end, metadata)
                for trip_id, name, email, start, end, metadata in trips
            }
            calculations = sorted(
                [
                    *identities[row.trip_session_id],
                    str(row.gross_payout),
                    str(row.final_payout),
                    row.currency,
                ]
                for row in (await session.scalars(select(PayoutCalculation))).all()
            )
            ledger = sorted(
                [
                    *identities[row.trip_session_id],
                    row.entry_type,
                    row.status,
                    str(row.amount),
                    row.currency,
                ]
                for row in (await session.scalars(select(EarningsLedgerEntry))).all()
            )
            return calculations, ledger

    calculations, ledger = asyncio.run(read_money())
    removed = _removed_duplicate_calculations()
    zero_ledger = _removed_zero_ledger()
    calculation_by_trip = {tuple(row[:5]): row for row in calculations}
    ledger_by_trip = {tuple(row[:5]): row for row in ledger}
    assert len(calculations) == len(calculation_by_trip) == 295
    assert len(ledger) == len(ledger_by_trip) == 288
    assert not {tuple(row[:5]) for row in removed} & calculation_by_trip.keys()
    assert calculation_by_trip.keys() - ledger_by_trip.keys() == {
        tuple(row[:5]) for row in zero_ledger
    }
    for row in zero_ledger:
        assert calculation_by_trip[tuple(row[:5])][5:] == ["0.00", "0.00", "NGN"]
    historical_calculations = sorted(calculations + removed)
    historical_ledger = sorted(
        ledger
        + zero_ledger
        + [[*row[:5], "trip_payout", "pending", row[6], row[7]] for row in removed]
    )
    assert (
        _digest(historical_calculations)
        == "5e4c7a9579c53e9f7fd6b05cdf000ccacb721a0d7968926b279bcc0c6eb51814"
    )
    assert (
        _digest(historical_ledger)
        == "54daf385b28af837ef7350f604d064ba392b4bd75abe9842c561d1bcc3dc6f57"
    )
    assert sum(Decimal(row[7]) for row in ledger) == (
        Decimal("497627.06") - sum(Decimal(row[6]) for row in removed)
    )

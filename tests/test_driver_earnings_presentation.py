from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.payouts import EarningsLedgerEntryRead
from app.services import driver_earnings_presentation as presentation


def test_work_days_use_persisted_allocation_and_reject_partial_totals():
    entry = SimpleNamespace(entry_type="trip_payout", amount=Decimal("10.01"))
    calculation = SimpleNamespace(amount_by_day={"2026-10-09": "5.00", "2026-10-10": "5.01"})
    assert [(str(day.day), day.amount) for day in presentation.work_days(entry, calculation)] == [
        ("2026-10-09", Decimal("5.00")),
        ("2026-10-10", Decimal("5.01")),
    ]
    entry.amount = Decimal("11.00")
    assert presentation.work_days(entry, calculation) == []


def test_correction_uses_its_recorded_lagos_day_not_creation_time():
    entry = SimpleNamespace(
        entry_type="reversal", amount=Decimal("2.00"), ledger_metadata={"lagos_day": "2026-10-08"}
    )
    assert str(presentation.work_days(entry, None)[0].day) == "2026-10-08"
    entry.ledger_metadata = {}
    assert presentation.work_days(entry, None) == []


@pytest.mark.parametrize(
    "state,paid_at,expected_paid",
    [
        ("succeeded", datetime(2026, 10, 9, 20, tzinfo=UTC), True),
        ("reserved", None, False),
        ("failed", None, False),
        ("submitted", None, False),
    ],
)
def test_payment_date_requires_succeeded_line_evidence(monkeypatch, state, paid_at, expected_paid):
    import asyncio
    from uuid import uuid4

    entry = SimpleNamespace(
        id=uuid4(),
        payout_calculation_id=uuid4(),
        driver_profile_id=uuid4(),
        currency="NGN",
        status="paid",
        amount=Decimal("10.00"),
        entry_type="trip_payout",
    )
    response = EarningsLedgerEntryRead.model_construct(
        work_days=[], paid_at=None, paying_tonight=False, payment_on_hold=False
    )
    line = SimpleNamespace(
        ledger_entry_id=entry.id, status=state, reconciled_at=paid_at, amount=entry.amount
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(line, None, None)])),
        scalars=AsyncMock(
            return_value=SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(
                        id=entry.payout_calculation_id, amount_by_day={"2026-10-09": "10.00"}
                    )
                ]
            )
        ),
    )
    monkeypatch.setattr(
        presentation,
        "automatic_payout_status",
        AsyncMock(return_value={"runnable": False, "frequency": "daily"}),
    )
    monkeypatch.setattr(presentation, "build_disbursement_adapter", lambda settings: None)
    asyncio.run(presentation.enrich_driver_ledger(session, [entry], [response], None))
    assert bool(response.paid_at) is expected_paid
    assert response.paying_tonight is False


@pytest.mark.parametrize(
    "runnable,frequency,line_status,batch_mode,period,tonight",
    [
        (True, "daily", "reserved", "automatic", "today", True),
        (False, "daily", "reserved", "automatic", "today", False),
        (True, "weekly", "reserved", "automatic", "today", False),
        (True, "daily", "failed", "automatic", "today", False),
        (True, "daily", "reserved", "manual", "today", False),
        (True, "daily", "reserved", "automatic", "yesterday", False),
    ],
)
def test_tonight_requires_current_automatic_schedule_and_runtime(
    monkeypatch,
    runnable,
    frequency,
    line_status,
    batch_mode,
    period,
    tonight,
    clean_reason=None,
):
    import asyncio
    from uuid import uuid4
    from zoneinfo import ZoneInfo

    entry = SimpleNamespace(
        id=uuid4(),
        payout_calculation_id=uuid4(),
        driver_profile_id=uuid4(),
        currency="NGN",
        status="available",
        amount=Decimal("10.00"),
        entry_type="trip_payout",
    )
    line = SimpleNamespace(
        ledger_entry_id=entry.id,
        status=line_status,
        reconciled_at=None,
        amount=entry.amount,
        reservation_active=True,
    )
    batch = SimpleNamespace(
        approval_mode=batch_mode, approved_at=datetime.now(UTC), status="reserved"
    )
    run = SimpleNamespace(
        period_key=datetime.now(UTC).astimezone(ZoneInfo("Africa/Lagos")).date().isoformat()
        if period == "today"
        else "2000-01-01"
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(line, batch, run)])),
        scalars=AsyncMock(
            return_value=SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(
                        id=entry.payout_calculation_id, amount_by_day={"2026-10-09": "10.00"}
                    )
                ]
            )
        ),
        scalar=AsyncMock(return_value=None),
    )
    response = EarningsLedgerEntryRead.model_construct(
        work_days=[], paid_at=None, paying_tonight=False, payment_on_hold=False
    )
    monkeypatch.setattr(
        presentation,
        "automatic_payout_status",
        AsyncMock(return_value={"runnable": runnable, "frequency": frequency}),
    )
    monkeypatch.setattr(presentation, "build_disbursement_adapter", lambda settings: None)
    monkeypatch.setattr(
        presentation, "_clean_reason", AsyncMock(return_value=(clean_reason, {}, None))
    )
    asyncio.run(presentation.enrich_driver_ledger(session, [entry], [response], None))
    assert response.paying_tonight is tonight


@pytest.mark.parametrize("reason", ["new_bank_destination", "fraud_hold", "assessment_not_current"])
def test_new_clean_check_can_withhold_tonight(monkeypatch, reason):
    test_tonight_requires_current_automatic_schedule_and_runtime(
        monkeypatch, True, "daily", "reserved", "automatic", "today", False, reason
    )

"""REQ-310: fresh reporting fixtures cover complete Nigeria days at every seed hour."""

import asyncio
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.seeds import demo

LAGOS = ZoneInfo("Africa/Lagos")


@pytest.mark.parametrize("hour", range(24))
def test_reporting_window_at_every_seed_hour(monkeypatch, hour):
    now = datetime(2026, 11, 9, hour, 30, tzinfo=UTC)
    monkeypatch.setattr(demo, "utc_now", lambda: now)
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=None), add=Mock(), flush=AsyncMock(), refresh=AsyncMock()
    )
    campaign = asyncio.run(
        demo.upsert_campaign(
            session,
            organization=SimpleNamespace(id=uuid4()),
            advertiser=SimpleNamespace(id=uuid4()),
        )
    )
    today = now.astimezone(LAGOS).date()
    expected = {today - timedelta(days=offset) for offset in range(1, 15)}
    for balanced, start, end in (
        (True, campaign.start_at, campaign.end_at),
        (False, now - timedelta(days=30), now + timedelta(days=60)),
    ):
        specs = demo.reporting_trip_specs(now, balance_paid_workdays=balanced)
        assert len(specs) == 14
        for car in range(3):
            observed = set()
            for _, at, coordinates in specs:
                started = at + timedelta(minutes=car * 5)
                ended = started + timedelta(
                    minutes=(len(coordinates) - 1) * demo.REPORTING_PING_MINUTES
                )
                assert start <= started <= ended <= end, (hour, balanced, started, start)
                day = started.astimezone(LAGOS).date()
                assert ended.astimezone(LAGOS).date() == day
                assert ended < datetime.combine(day + timedelta(days=1), time.min, LAGOS)
                observed.add(day)
            assert observed == expected, (hour, balanced, observed, expected)

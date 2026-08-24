import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.jobs import earnings_release as jobs


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeSessionmaker:
    def __init__(self) -> None:
        self.sessions: list[FakeSession] = []

    def __call__(self) -> FakeSession:
        session = FakeSession()
        self.sessions.append(session)
        return session


def test_release_review_sweep_pages_all_candidates_and_isolates_failures(monkeypatch) -> None:
    first_trip, second_trip = uuid4(), uuid4()
    first_flag, second_flag = uuid4(), uuid4()
    released_id = uuid4()
    pages = {None: [first_trip], first_trip: [second_trip], second_trip: []}
    release_calls = []
    escalation_calls = []
    captured = []

    async def find_trips(_session, *, limit, after=None):
        assert limit == 1
        return pages[after]

    async def find_flags(_session, *, review_sla_days, limit):
        assert review_sla_days == 7
        assert limit == 1
        return [first_flag, second_flag]

    async def release(_session, *, trip_id, settings):
        assert settings.fraud_review_sla_days == 7
        release_calls.append(trip_id)
        if trip_id == first_trip:
            raise RuntimeError("synthetic release failure")
        return SimpleNamespace(released_entry_ids=(released_id,))

    async def escalate(_session, *, flag_id, review_sla_days):
        assert review_sla_days == 7
        escalation_calls.append(flag_id)
        return flag_id == first_flag

    monkeypatch.setattr(jobs, "find_pending_release_trip_ids", find_trips)
    monkeypatch.setattr(jobs, "find_due_fraud_flag_ids", find_flags)
    monkeypatch.setattr(jobs, "release_pending_earnings_for_trip", release)
    monkeypatch.setattr(jobs, "escalate_fraud_flag_if_due", escalate)
    monkeypatch.setattr(jobs, "capture_exception", captured.append)
    sessionmaker = FakeSessionmaker()

    result = asyncio.run(
        jobs.sweep_earnings_release_reviews(
            {
                "settings": SimpleNamespace(
                    worker_sweep_batch_size=1,
                    fraud_review_sla_days=7,
                ),
                "sessionmaker": sessionmaker,
            }
        )
    )

    assert release_calls == [first_trip, second_trip]
    assert escalation_calls == [first_flag, second_flag]
    duration_ms = result.pop("duration_ms")
    assert duration_ms >= 0
    assert result == {
        "release_candidates": 2,
        "released_entries": 1,
        "release_failed": 1,
        "escalation_candidates": 2,
        "escalated_flags": 1,
        "escalation_failed": 0,
    }
    assert len(captured) == 1
    assert len(sessionmaker.sessions) == 5
    assert sessionmaker.sessions[1].rollbacks == 1
    assert all(session.commits == 1 for session in sessionmaker.sessions[2:])

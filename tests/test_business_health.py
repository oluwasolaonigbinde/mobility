import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from conftest import create_test_user
from sqlalchemy import select
from test_campaign_ingestion_locks import setup_trip

from app.core.gps_health import gps_window, minute_key, record_attempt
from app.jobs import monitoring
from app.models.billing import PaymentGatewayEvent, PaymentGatewayProcessingAttempt
from app.models.disbursement import (
    PayoutAutomaticAlert,
    PayoutProviderEvent,
    PayoutProviderEventProcessingAttempt,
)
from app.models.notification import Notification
from app.models.trip import TripSession
from app.models.user import User
from app.services import business_health as health

NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)


class FakeRedis:
    def __init__(self, broken=False):
        self.values = {}
        self.expiries = {}
        self.commands = []
        self.broken = broken

    def pipeline(self, **kwargs):
        self.commands = []
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def hincrby(self, key, field, value):
        self.commands.append(("increment", key, field, value))
        return self

    def expire(self, key, value):
        self.commands.append(("expire", key, value))
        return self

    def hmget(self, key, *fields):
        self.commands.append(("get", key, fields))
        return self

    async def execute(self):
        if self.broken:
            raise ConnectionError("synthetic redis failure")
        result = []
        for command in self.commands:
            if command[0] == "increment":
                _, key, field, value = command
                bucket = self.values.setdefault(key, {})
                bucket[field] = bucket.get(field, 0) + value
            elif command[0] == "expire":
                self.expiries[command[1]] = command[2]
            else:
                result.append([self.values.get(command[1], {}).get(f) for f in command[2]])
        return result


def test_gps_window_counts_only_complete_minutes_without_personal_data():
    async def run():
        redis = FakeRedis()
        for offset, rejected in [(0, True), (1, True), (15, False), (16, True)]:
            await record_attempt(redis, rejected=rejected, now=NOW - timedelta(minutes=offset))
        assert await gps_window(redis, now=NOW) == (2, 1)
        assert set(redis.expiries.values()) == {3600}
        assert all(set(bucket) == {"attempts", "rejected"} for bucket in redis.values.values())
        assert all(key.startswith("cardvert:health:gps:20261014") for key in redis.values)
        assert await gps_window(FakeRedis(), now=NOW) is None
        assert await gps_window(FakeRedis(broken=True), now=NOW) is None
        assert await gps_window(None, now=NOW) is None
        redis.values[minute_key(NOW - timedelta(minutes=1))]["rejected"] = 100
        assert await gps_window(redis, now=NOW) is None

    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["ok", "error", "cancel"])
def test_cron_records_terminal_status_and_preserves_result_or_failure(monkeypatch, outcome):
    checkins = []

    def capture(**values):
        checkins.append(values)
        return "synthetic-check-in"

    monkeypatch.setattr(monitoring, "capture_checkin", capture)

    async def scheduled_job(ctx):
        assert ctx == {"marker": True}
        if outcome == "error":
            raise ValueError("synthetic job failure")
        if outcome == "cancel":
            raise asyncio.CancelledError()
        return {"done": 1}

    job = monitoring.monitored_cron(scheduled_job, minute={0, 5}, unique=True)
    if outcome == "ok":
        assert asyncio.run(job.coroutine({"marker": True})) == {"done": 1}
    else:
        with pytest.raises(ValueError if outcome == "error" else asyncio.CancelledError):
            asyncio.run(job.coroutine({"marker": True}))
    assert [item["status"] for item in checkins] == [
        "in_progress",
        "ok" if outcome == "ok" else "error",
    ]
    assert {item["monitor_slug"] for item in checkins} == {"cardvert-scheduled-job"}
    assert checkins[0]["monitor_config"]["schedule"]["value"] == "0,5 * * * *"
    assert checkins[1]["check_in_id"] == "synthetic-check-in"
    assert set(checkins[1]) == {"monitor_slug", "check_in_id", "status"}


def test_every_registered_cron_is_monitored_and_telemetry_failure_is_fail_open(monkeypatch):
    from app.jobs.worker import WorkerSettings

    jobs = WorkerSettings.cron_jobs
    assert len({job.name for job in jobs}) == len(jobs)
    assert all(hasattr(job.coroutine, "__wrapped__") for job in jobs)
    sweep = next(job for job in jobs if job.coroutine.__name__ == "sweep_business_health")
    assert sweep.minute == set(range(0, 60, 5))

    def fail(**kwargs):
        raise RuntimeError("synthetic SDK failure")

    monkeypatch.setattr(monitoring, "capture_checkin", fail)

    async def succeeds(ctx):
        return 7

    assert asyncio.run(monitoring.monitored_cron(succeeds).coroutine({})) == 7


def test_stale_trip_boundaries_and_terminal_adjudication_never_realert(db_sessionmaker, settings):
    _, _, trip, _ = setup_trip(db_sessionmaker)

    async def run():
        async with db_sessionmaker() as session:
            row = await session.get(TripSession, trip.id)
            row.started_at = NOW - timedelta(minutes=30)
            await session.flush()
            assert await health.stale_trips(session, NOW, settings) == 0
            assert await health.stale_trips(session, NOW + timedelta(microseconds=1), settings) == 1
            row.status = "ended"
            row.ended_at = NOW - timedelta(seconds=settings.trip_seal_grace_seconds)
            await session.flush()
            assert await health.stale_trips(session, NOW, settings) == 0
            later = NOW + timedelta(seconds=1)
            assert await health.stale_trips(session, later, settings) == 1
            assert (
                await health.publish_health_alerts(session, now=later, counts={"stale_trips": 1})
                == 1
            )
            row.evidence_adjudicated_at = NOW
            row.evidence_adjudication_outcome = "incomplete_grace_expired"
            row.evidence_adjudication_receipt_format_version = 2
            row.evidence_adjudication_receipt_key_version = 1
            row.evidence_adjudication_receipt_signature = "a" * 64
            await session.flush()
            for moment in (later, NOW + timedelta(days=1)):
                count = await health.stale_trips(session, moment, settings)
                assert count == 0
                assert (
                    await health.publish_health_alerts(
                        session, now=moment, counts={"stale_trips": count}
                    )
                    == 0
                )
            alert = await session.scalar(select(PayoutAutomaticAlert))
            assert alert.resolved_at is None

    asyncio.run(run())


def test_finance_daily_deduplication_is_concurrent_and_not_auto_resolved(db_sessionmaker):
    active = create_test_user(db_sessionmaker, email="health-active@example.com", role="admin")
    disabled = create_test_user(db_sessionmaker, email="health-disabled@example.com", role="admin")

    async def disable():
        async with db_sessionmaker() as session:
            row = await session.get(User, disabled.id)
            row.status = "disabled"
            await session.commit()

    asyncio.run(disable())

    async def publish():
        async with db_sessionmaker() as session:
            result = await health.publish_health_alerts(
                session, now=NOW, counts={"stuck_payouts": 2}
            )
            await session.commit()
            return result

    async def run():
        assert sorted(await asyncio.gather(publish(), publish())) == [0, 1]
        async with db_sessionmaker() as session:
            notices = list((await session.scalars(select(Notification))).all())
            assert {notice.recipient_user_id for notice in notices} == {active.id}
            assert disabled.id not in {notice.recipient_user_id for notice in notices}
            assert (
                await health.publish_health_alerts(session, now=NOW, counts={"stuck_payouts": 0})
                == 0
            )
            assert (
                await health.publish_health_alerts(
                    session, now=NOW + timedelta(days=1), counts={"stuck_payouts": 1}
                )
                == 1
            )
            alerts = list((await session.scalars(select(PayoutAutomaticAlert))).all())
            assert len(alerts) == 2 and all(a.resolved_at is None for a in alerts)
            assert all(set(a.detail) == {"check", "count"} for a in alerts)
            with pytest.raises(ValueError):
                await health.publish_health_alerts(session, now=NOW, counts={"private-trip-id": 1})

    asyncio.run(run())


def test_webhook_retry_failure_stays_unprocessed_and_boundary_is_strict(db_sessionmaker):
    async def run():
        async with db_sessionmaker() as session:
            payment = PaymentGatewayEvent(
                id=uuid4(),
                provider="synthetic",
                provider_event_id="health-payment",
                external_transaction_id="health-payment",
                event_type="payment_failed",
                commercial_terms_reference="synthetic",
                amount=Decimal("1"),
                currency="NGN",
                payer_name="Synthetic",
                occurred_at=NOW,
                evidence_fingerprint="a" * 64,
                payload={},
                received_at=NOW - timedelta(minutes=15),
            )
            payout = PayoutProviderEvent(
                id=uuid4(),
                provider="synthetic",
                provider_event_id="health-payout",
                provider_event_type="transfer.failed",
                provider_transfer_reference="synthetic",
                provider_reference="synthetic",
                amount=Decimal("1"),
                currency="NGN",
                outcome="failed",
                provider_occurred_at=NOW,
                evidence_fingerprint="b" * 64,
                received_at=NOW - timedelta(minutes=15),
            )
            session.add_all([payment, payout])
            await session.flush()
            assert await health.unprocessed_webhooks(session, NOW) == 0
            later = NOW + timedelta(seconds=1)
            assert await health.unprocessed_webhooks(session, later) == 2
            session.add_all(
                [
                    PaymentGatewayProcessingAttempt(
                        gateway_event_id=payment.id,
                        attempt_number=1,
                        outcome="failed",
                        error_code="synthetic",
                        processed_at=NOW,
                    ),
                    PayoutProviderEventProcessingAttempt(
                        provider_event_id=payout.id,
                        attempt_number=1,
                        outcome="failed",
                        error_code="synthetic",
                        processed_at=NOW,
                    ),
                ]
            )
            await session.flush()
            assert await health.unprocessed_webhooks(session, later) == 2
            session.add(
                PaymentGatewayProcessingAttempt(
                    gateway_event_id=payment.id,
                    attempt_number=2,
                    outcome="ignored_failed",
                    processed_at=NOW,
                )
            )
            await session.flush()
            assert await health.unprocessed_webhooks(session, later) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "attempts,rejected,expected", [(19, 19, 0), (20, 4, 0), (20, 5, 5), (100, 25, 25)]
)
def test_gps_alert_threshold_and_healthy_durable_predicates(
    db_sessionmaker, settings, monkeypatch, attempts, rejected, expected
):
    async def covered(*args, **kwargs):
        return True, NOW + timedelta(days=60)

    monkeypatch.setattr(health, "check_partition_coverage", covered)

    async def run():
        redis = FakeRedis()
        redis.values[minute_key(NOW - timedelta(minutes=1))] = {
            "attempts": attempts,
            "rejected": rejected,
        }
        async with db_sessionmaker() as session:
            result = await health.health_counts(session, now=NOW, settings=settings, redis=redis)
            assert result.pop("gps_rejections") == expected
            assert set(result.values()) == {0}

    asyncio.run(run())


def test_pause_email_partition_and_unavailable_boundaries(db_sessionmaker, settings, monkeypatch):
    from app.models.disbursement import PayoutAutomaticControl

    admin = create_test_user(db_sessionmaker, email="health-boundaries@example.com", role="admin")
    covered_state = [True]

    async def coverage(*args, **kwargs):
        return covered_state[0], None

    monkeypatch.setattr(health, "check_partition_coverage", coverage)

    async def run():
        async with db_sessionmaker() as session:
            session.add(
                PayoutAutomaticControl(
                    id=1,
                    paused=True,
                    reason="Synthetic pause",
                    changed_by_user_id=admin.id,
                    changed_at=NOW - timedelta(days=1),
                    actor_password_fingerprint="a" * 64,
                )
            )
            for status, created, failed in [
                ("pending", NOW - timedelta(minutes=15), None),
                ("failed", NOW - timedelta(days=5), NOW - timedelta(days=1)),
                ("failed", NOW - timedelta(days=5), NOW - timedelta(days=1, seconds=1)),
            ]:
                session.add(
                    Notification(
                        recipient_user_id=admin.id,
                        type_key="synthetic",
                        channel="transactional_email",
                        status=status,
                        created_at=created,
                        failed_at=failed,
                        payload={},
                        dedupe_fingerprint=uuid4().hex,
                    )
                )
            await session.flush()
            result = await health.health_counts(session, now=NOW, settings=settings, redis=None)
            assert result["paused_payouts"] == 0
            assert result["email_failures"] == 1
            assert result["partition_coverage"] == 0
            assert result["gps_telemetry_unavailable"] == 1
            covered_state[0] = False
            result = await health.health_counts(
                session, now=NOW + timedelta(seconds=1), settings=settings, redis=None
            )
            assert result["paused_payouts"] == 1
            assert result["email_failures"] == 1  # pending now overdue, oldest failure aged out
            assert result["partition_coverage"] == 1

    asyncio.run(run())


def test_stuck_payouts_use_latest_progress_and_ignore_terminal_intents(db_sessionmaker):
    from test_mny03a_earnings_release import build_graph
    from test_payout_batches import _seed_authority

    from app.models.disbursement import PayoutSubmissionIntent
    from app.services.disbursements import create_payout_batch_draft, reserve_payout_batch

    graph = build_graph(db_sessionmaker, "health-stuck")

    async def run():
        async with db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            _, lines = await reserve_payout_batch(
                session,
                batch_id=batch.id,
                ledger_entry_ids=(entry.id,),
                actor_user_id=graph.admin.id,
            )
            line = lines[0]
            line.created_at = NOW - timedelta(hours=1)
            line.status = "submitted"
            line.provider_transfer_reference = "synthetic-health-transfer"
            await session.flush()
            assert await health.stuck_payouts(session, NOW) == 0
            assert await health.stuck_payouts(session, NOW + timedelta(seconds=1)) == 1
            line.last_provider_evidence_at = NOW
            intent = PayoutSubmissionIntent(
                payout_batch_line_id=line.id,
                provider_name="synthetic",
                instruction_fingerprint=line.instruction_fingerprint,
                instruction=line.instruction,
                idempotency_key=line.idempotency_key,
                requested_by_user_id=graph.admin.id,
                state="pending",
                updated_at=NOW - timedelta(hours=2),
            )
            session.add(intent)
            await session.flush()
            assert await health.stuck_payouts(session, NOW) == 1
            intent.state = "cancelled"
            intent.resolved_at = NOW
            intent.updated_at = NOW
            await session.flush()
            assert await health.stuck_payouts(session, NOW) == 0

    asyncio.run(run())


def test_api_records_partial_and_replayed_gps_rejection(db_client, db_sessionmaker, monkeypatch):
    from test_trips import create_trip_ready_graph, driver_headers, ping_payload, start_trip

    from app.api.v1 import trips as api

    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    recorded = []

    async def record(_settings, attempt):
        recorded.append(attempt.rejected)

    monkeypatch.setattr(api, "record_gps_attempt", record)
    payload = ping_payload()
    valid = payload["pings"][0]
    payload["pings"] = [
        valid,
        valid | {"sequence_number": valid["sequence_number"] + 1, "speed_mps": 121},
    ]
    for _ in range(2):
        response = db_client.post(
            f"/api/v1/driver/trips/{trip_id}/pings", headers=driver_headers(db_client), json=payload
        )
        assert response.status_code == 200, response.text
        assert response.json()["accepted_count"] == 1
        assert response.json()["rejected_count"] == 1
    assert recorded == [True, True]


def test_gps_recording_uses_fake_redis_and_never_leaks_exception(settings, monkeypatch, caplog):
    from app.core import gps_health

    redis = FakeRedis()

    class Client:
        @staticmethod
        def from_url(url):
            assert url == "redis://synthetic"
            return redis

    monkeypatch.setattr(gps_health, "Redis", Client)

    async def run():
        await gps_health.record_gps_attempt(
            settings.model_copy(update={"redis_url": None}), gps_health.GPSAttempt()
        )
        configured = settings.model_copy(update={"redis_url": "redis://synthetic"})
        await gps_health.record_gps_attempt(configured, gps_health.GPSAttempt(rejected=True))
        assert sum(v["attempts"] for v in redis.values.values()) == 1
        redis.broken = True
        await gps_health.record_gps_attempt(configured, gps_health.GPSAttempt())

    asyncio.run(run())
    assert "telemetry_unavailable" in caplog.text
    assert "synthetic redis failure" not in caplog.text

"""Automatic payout approval with safeguards (D39(c), Batch C).

Every setting value here (frequency, run limit, day rates) is an explicit
SYNTHETIC test value; the client has not supplied the real ones and the code
never assumes them. v4 earnings come from the real payout_v4 pipeline.
"""

import asyncio
import hashlib
import json
import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_user,
)
from sqlalchemy import select, update
from test_mny03a_earnings_release import build_graph as build_manual_graph
from test_payout_batches import _seed_authority
from test_payouts_v3 import add_target_zone
from test_payouts_v4 import (
    TRIP_START,
    add_trip,
    build_v4_graph,
    create_v4_revision,
    create_v4_rule,
    drive,
    insert_v4_binding,
)

from app.adapters.crypto import EnvelopeCryptoProvider
from app.adapters.disbursement import DisabledDisbursementAdapter, FakeDisbursementAdapter
from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.models.audit import AuditEvent
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.disbursement import (
    CARDVERT_AUTOMATIC_PAYOUT_ACTOR_EMAIL,
    CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID,
    PayoutAutomaticAlert,
    PayoutAutomaticControl,
    PayoutAutomaticRun,
    PayoutBatch,
    PayoutBatchLine,
    PayoutRecoveryIncident,
    PayoutSubmissionAttempt,
    PayoutSubmissionIntent,
    PayoutSubmissionObservation,
)
from app.models.fraud_dispute import FraudDispute
from app.models.notification import Notification
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip_analytics import FraudFlag, TripAnalytics
from app.models.user import User
from app.services import automatic_payouts as automatic
from app.services.disbursements import (
    approve_payout_batch,
    claim_payout_submission_intent,
    create_payout_batch_draft,
    find_due_payout_submission_intent_ids,
    process_payout_submission_intent,
    reconcile_payout_webhook,
    reserve_payout_batch,
    submit_payout_batch,
)
from app.services.payees import (
    VerifiedBankAccountDetails,
    add_verified_bank_account_version,
    create_pilot_payee,
)

RUN_AT = datetime(2026, 7, 21, 1, 0, tzinfo=UTC)
DAY = date(2026, 7, 20)
SYNTHETIC = {
    "payout_automatic_approval_enabled": True,
    "payout_automatic_frequency": "daily",
    "payout_automatic_batch_limit_ngn": Decimal("20000.00"),
}


def auto(settings: Settings, **overrides) -> Settings:
    return settings.model_copy(update={**SYNTHETIC, **overrides})


def install_automatic(db, *, actor_status: str = "disabled") -> None:
    async def create():
        async with db() as session:
            password_hash = hash_password(secrets.token_urlsafe(48))
            session.add(
                User(
                    id=CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID,
                    email=CARDVERT_AUTOMATIC_PAYOUT_ACTOR_EMAIL,
                    password_hash=password_hash,
                    full_name="Cardvert (automatic payouts)",
                    role="admin",
                    status=actor_status,
                )
            )
            await session.flush()
            session.add(
                PayoutAutomaticControl(
                    id=1,
                    paused=False,
                    actor_password_fingerprint=hashlib.sha256(password_hash.encode()).hexdigest(),
                )
            )
            await session.commit()

    asyncio.run(create())


REAL_BANK_ACCOUNT_PAID_BEFORE = automatic.bank_account_paid_before


@pytest.fixture(autouse=True)
def accounts_paid_before(monkeypatch):
    """Treat every bank account as already paid by a person, so tests exercise the
    other rules; the first-payment tests restore the real check."""

    async def paid_before(session, bank_account_version_id) -> bool:
        return True

    monkeypatch.setattr(automatic, "bank_account_paid_before", paid_before)


def add_payee(db, graph) -> None:
    async def create():
        async with db() as session:
            payee, _ = await create_pilot_payee(
                session, driver_profile_id=graph.profile.id, actor_user_id=graph.admin.id
            )
            await add_verified_bank_account_version(
                session,
                payee_id=payee.id,
                details=VerifiedBankAccountDetails(
                    account_name="Ada Automatic", account_number="0123456789", bank_code="058"
                ),
                verification_reference=f"auto-provider-evidence-{uuid4().hex}",
                actor_user_id=graph.admin.id,
                crypto=EnvelopeCryptoProvider(keys={1: b"e" * 32}, active_key_version=1),
            )
            await session.commit()

    asyncio.run(create())


def release_all(db) -> None:
    async def change():
        async with db() as session:
            await session.execute(
                update(EarningsLedgerEntry)
                .where(EarningsLedgerEntry.status == "pending")
                .values(status="available")
            )
            await session.commit()

    asyncio.run(change())


def clean_graph(db, settings, tag, *, payee=True, **terms):
    graph = build_v4_graph(db, settings, tag, **terms)
    drive(db, settings, graph.trip)
    release_all(db)
    if payee:
        add_payee(db, graph)
    return graph


def run(db, settings, *, adapter=None, now=RUN_AT):
    async def go():
        async with db() as session:
            result = await automatic.run_automatic_payouts(
                session,
                settings=settings,
                adapter=adapter or FakeDisbursementAdapter(),
                now=now,
            )
            await session.commit()
            return result

    return asyncio.run(go())


def fetch(db, model, *where):
    async def go():
        async with db() as session:
            return list((await session.scalars(select(model).where(*where))).all())

    return asyncio.run(go())


def entry_for(db, trip_id) -> EarningsLedgerEntry:
    (entry,) = fetch(
        db,
        EarningsLedgerEntry,
        EarningsLedgerEntry.trip_session_id == trip_id,
        EarningsLedgerEntry.entry_type == "trip_payout",
    )
    return entry


def execute(db, statement) -> None:
    async def go():
        async with db() as session:
            await session.execute(statement)
            await session.commit()

    asyncio.run(go())


def add_flag(db, graph, *, flag_status="dismissed"):
    async def go():
        async with db() as session:
            analytics = await session.scalar(
                select(TripAnalytics).where(TripAnalytics.trip_session_id == graph.trip.id)
            )
            flag = FraudFlag(
                trip_session_id=graph.trip.id,
                trip_analytics_id=analytics.id,
                assignment_id=graph.assignment.id,
                campaign_id=graph.campaign.id,
                driver_profile_id=graph.profile.id,
                vehicle_id=graph.vehicle.id,
                flag_type="impossible_speed",
                severity="low",
                status="open",
                description="Synthetic review evidence.",
                evidence={"test": True},
                detected_at=TRIP_START,
            )
            session.add(flag)
            await session.flush()
            if flag_status != "open":
                flag.status = flag_status
                flag.reviewed_by_user_id = graph.admin.id
                flag.reviewed_at = TRIP_START + timedelta(hours=2)
                flag.resolution_note = "Synthetic review."
            await session.commit()
            return flag

    return asyncio.run(go())


# --- fail-closed settings and switch -------------------------------------------


def test_settings_fail_closed_and_validate(settings) -> None:
    assert automatic.missing_automatic_settings(settings) == [
        "PAYOUT_AUTOMATIC_APPROVAL_ENABLED",
        "PAYOUT_AUTOMATIC_FREQUENCY",
        "PAYOUT_AUTOMATIC_BATCH_LIMIT_NGN",
    ]
    base = settings.model_dump()
    configured = Settings(
        **{**base, **SYNTHETIC, "payout_automatic_frequency": " Weekly "},
    )
    assert configured.payout_automatic_frequency == "weekly"
    assert automatic.missing_automatic_settings(configured) == []
    blank = Settings(
        **{**base, "payout_automatic_frequency": "", "payout_automatic_batch_limit_ngn": " "}
    )
    assert blank.payout_automatic_frequency is None
    assert blank.payout_automatic_batch_limit_ngn is None
    for bad in (
        {"payout_automatic_approval_enabled": True},
        {"payout_automatic_frequency": "monthly"},
        {"payout_automatic_batch_limit_ngn": "-1"},
        {"payout_automatic_batch_limit_ngn": "0"},
        {"payout_automatic_batch_limit_ngn": "10.001"},
        {"payout_automatic_batch_limit_ngn": "NaN"},
        {"payout_automatic_batch_limit_ngn": "1000000000000"},
    ):
        with pytest.raises(ValueError):
            Settings(**{**base, **bad})
    largest = Settings(**{**base, "payout_automatic_batch_limit_ngn": "999999999999.99"})
    assert largest.payout_automatic_batch_limit_ngn == Decimal("999999999999.99")


def test_period_keys_follow_nigeria_time() -> None:
    late_utc = datetime(2026, 9, 27, 23, 30, tzinfo=UTC)  # 00:30 WAT on 28 Sep
    assert automatic.period_key_for(late_utc, "daily") == "2026-09-28"
    assert automatic.period_key_for(late_utc, "weekly") == "2026-W40"


def test_nothing_runs_until_configured_installed_and_unpaused(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-closed")
    assert run(db, settings) == {
        "outcome": "not_set_up",
        "missing_settings": [
            "PAYOUT_AUTOMATIC_APPROVAL_ENABLED",
            "PAYOUT_AUTOMATIC_FREQUENCY",
            "PAYOUT_AUTOMATIC_BATCH_LIMIT_NGN",
        ],
    }
    # Switched on but the seed rows are missing: never auto-created (R8).
    result = run(db, auto(settings))
    assert result == {"outcome": "actor_invalid", "reason": "control_missing"}
    install_automatic(db)
    execute(
        db,
        update(PayoutAutomaticControl).values(
            paused=True,
            reason="Synthetic pause",
            changed_by_user_id=graph.admin.id,
            changed_at=RUN_AT,
        ),
    )
    assert run(db, auto(settings)) == {"outcome": "paused"}
    execute(db, update(PayoutAutomaticControl).values(paused=False, reason="Synthetic resume"))
    assert run(db, auto(settings), adapter=DisabledDisbursementAdapter())["outcome"] == (
        "provider_unavailable"
    )
    assert fetch(db, PayoutBatch) == []
    assert fetch(db, PayoutAutomaticRun) == []
    kinds = sorted(alert.detail["reason"] for alert in fetch(db, PayoutAutomaticAlert))
    assert kinds == ["control_missing", "provider_unavailable"]


# --- the happy path ---------------------------------------------------------------


def test_clean_v4_earning_is_approved_by_cardvert_and_submitted(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-happy")
    install_automatic(db)
    entry = entry_for(db, graph.trip.id)
    fake = FakeDisbursementAdapter()
    result = run(db, auto(settings), adapter=fake)
    assert result["outcome"] == "completed"
    assert (result["batch_count"], result["line_count"]) == (1, 1)
    (batch,) = fetch(db, PayoutBatch)
    assert batch.approval_mode == "automatic"
    assert batch.created_by_user_id == CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID
    assert batch.approved_by_user_id is None and batch.approved_at is not None
    assert batch.status == "reserved" and batch.total_amount == entry.amount
    (line,) = fetch(db, PayoutBatchLine)
    assert line.ledger_entry_id == entry.id and line.amount == entry.amount
    (intent,) = fetch(db, PayoutSubmissionIntent)
    assert intent.requested_by_user_id == CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID
    (run_row,) = fetch(db, PayoutAutomaticRun)
    assert run_row.period_key == "2026-07-21" and run_row.total_amount == entry.amount

    # Idempotent: the same period never runs twice.
    assert run(db, auto(settings), adapter=fake)["outcome"] == "already_ran"
    assert len(fetch(db, PayoutBatch)) == 1

    # The unchanged submission sweep sends it through the same port.
    outcome = asyncio.run(
        process_payout_submission_intent(
            db, intent_id=intent.id, adapter=fake, settings=auto(settings)
        )
    )
    assert outcome == "resolved"
    assert len(fake.calls) == 1
    assert Decimal(fake.calls[0][1][0].instruction["amount"]) == entry.amount
    (line,) = fetch(db, PayoutBatchLine)
    assert line.status == "submitted"

    # Verified provider evidence pays it through the unchanged reconciliation.
    payload = json.dumps(
        {
            "provider_transfer_reference": line.provider_transfer_reference,
            "provider_event_id": "evt-auto-1",
            "outcome": "succeeded",
            "occurred_at": "2026-07-21T02:00:00Z",
        }
    ).encode()

    async def webhook():
        async with db() as session:
            await reconcile_payout_webhook(
                session, payload=payload, signature=fake.sign_webhook(payload), adapter=fake
            )
            await session.commit()

    asyncio.run(webhook())
    assert entry_for(db, graph.trip.id).status == "paid"
    assert entry_for(db, graph.trip.id).amount == entry.amount
    audits = fetch(
        db,
        AuditEvent,
        AuditEvent.action.in_(
            (
                "system.payout_batch.automatically_approved",
                "system.payout_automatic_run.completed",
                "worker.payout_submission.authorized",
            )
        ),
    )
    assert {audit.actor_user_id for audit in audits} == {CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID}
    authorized = next(a for a in audits if a.action == "worker.payout_submission.authorized")
    assert authorized.event_metadata["approval_mode"] == "automatic"
    # No person is named anywhere as the approver.
    assert batch.approved_by_user_id is None


def test_human_cannot_approve_or_submit_an_automatic_batch(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-human")
    install_automatic(db)
    run(db, auto(settings))
    (batch,) = fetch(db, PayoutBatch)

    async def attempt():
        codes = []
        async with db() as session:
            for action in (approve_payout_batch, submit_payout_batch):
                kwargs = (
                    {"adapter": FakeDisbursementAdapter()} if action is submit_payout_batch else {}
                )
                try:
                    await action(session, batch_id=batch.id, actor_user_id=graph.admin.id, **kwargs)
                except AppError as error:
                    codes.append((error.code, error.status_code))
            await session.rollback()
        return codes

    assert asyncio.run(attempt()) == [("PAYOUT_BATCH_AUTOMATIC", 409)] * 2
    (after,) = fetch(db, PayoutBatch)
    assert after.approved_by_user_id is None


# --- what is not clean stays manual -----------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "open_hold",
        "dismissed_flag",
        "open_dispute",
        "no_payee",
        "never_paid_account",
        "debt",
        "adjusted",
        "already_reserved",
        "stale_assessment",
        "earlier_automatic",
    ],
)
def test_unclean_earnings_stay_on_the_maker_checker_path(
    postgis_db_sessionmaker, settings, case, monkeypatch
) -> None:
    db = postgis_db_sessionmaker
    if case == "never_paid_account":
        monkeypatch.setattr(automatic, "bank_account_paid_before", REAL_BANK_ACCOUNT_PAID_BEFORE)
    graph = clean_graph(db, settings, f"auto-{case[:10]}", payee=case != "no_payee")
    install_automatic(db)
    entry = entry_for(db, graph.trip.id)
    # A flagged trip (any status, so also the disputed one) and a trip with another
    # non-voided entry are permanently unclean: the candidate query leaves them out,
    # so they take no scan place and are not counted as exclusions (money review #2).
    expected_reason = {
        "no_payee": "payee_unverified",
        # One admin can add and verify an account (D29); its first payment needs a person.
        "never_paid_account": "new_bank_destination",
        "debt": "debt_outstanding",
        "stale_assessment": "assessment_not_current",
    }.get(case)
    if case == "open_hold":
        add_flag(db, graph, flag_status="open")
    elif case == "dismissed_flag":
        add_flag(db, graph)
    elif case == "open_dispute":
        flag = add_flag(db, graph)

        async def dispute():
            async with db() as session:
                session.add(
                    FraudDispute(
                        fraud_flag_id=flag.id,
                        driver_profile_id=graph.profile.id,
                        submitted_by_user_id=graph.driver.id,
                        message="Synthetic dispute.",
                    )
                )
                await session.commit()

        asyncio.run(dispute())
        # test_open_dispute_alone_keeps_the_driver_manual covers a dispute on
        # another trip keeping a clean trip manual.
    elif case == "debt":
        from app.models.disbursement import DriverCurrencyDebtAccount

        async def debt():
            async with db() as session:
                session.add(
                    DriverCurrencyDebtAccount(
                        driver_profile_id=graph.profile.id,
                        driver_user_id=graph.driver.id,
                        currency="NGN",
                        outstanding_amount=Decimal("10.00"),
                        lifetime_incurred_amount=Decimal("10.00"),
                        lifetime_allocated_amount=Decimal("0.00"),
                    )
                )
                await session.commit()

        asyncio.run(debt())
    elif case == "adjusted":

        async def adjust():
            async with db() as session:
                session.add(
                    EarningsLedgerEntry(
                        driver_profile_id=entry.driver_profile_id,
                        driver_user_id=entry.driver_user_id,
                        campaign_id=entry.campaign_id,
                        trip_session_id=entry.trip_session_id,
                        vehicle_id=entry.vehicle_id,
                        entry_type="adjustment",
                        status="available",
                        amount=Decimal("5.00"),
                        currency="NGN",
                        occurred_at=entry.occurred_at,
                        ledger_metadata={},
                    )
                )
                await session.commit()

        asyncio.run(adjust())
    elif case == "already_reserved":

        async def reserve():
            async with db() as session:
                batch = await create_payout_batch_draft(
                    session, currency="NGN", actor_user_id=graph.admin.id
                )
                await reserve_payout_batch(
                    session,
                    batch_id=batch.id,
                    ledger_entry_ids=(entry.id,),
                    actor_user_id=graph.admin.id,
                )
                await session.commit()

        asyncio.run(reserve())
    elif case == "stale_assessment":
        execute(
            db,
            update(TripAnalytics)
            .where(TripAnalytics.trip_session_id == graph.trip.id)
            .values(formula_version="route_analytics_v0"),
        )
    elif case == "earlier_automatic":
        run(db, auto(settings))
        (batch,) = fetch(db, PayoutBatch)

        async def release():
            async with db() as session:
                control = await session.get(PayoutAutomaticControl, 1)
                control.paused = True
                control.reason = "Synthetic pause"
                control.changed_by_user_id = graph.admin.id
                control.changed_at = RUN_AT
                await session.flush()
                result = await automatic.release_unsent_automatic_payments(
                    session,
                    reason="Move to manual",
                    actor_user_id=graph.admin.id,
                    settings=auto(settings),
                )
                control.paused = False
                await session.commit()
                return result

        assert asyncio.run(release())["released_count"] == 1
        assert entry_for(db, graph.trip.id).status == "available"
    result = run(db, auto(settings), now=RUN_AT + timedelta(days=1))
    assert result["outcome"] == "completed"
    assert result["line_count"] == 0
    automatic_lines = fetch(
        db,
        PayoutBatchLine,
        PayoutBatchLine.ledger_entry_id == entry.id,
        PayoutBatchLine.reservation_active.is_(True),
        PayoutBatchLine.batch_id.in_(
            select(PayoutBatch.id).where(PayoutBatch.approval_mode == "automatic")
        ),
    )
    assert automatic_lines == []
    assert entry_for(db, graph.trip.id).status != "paid"
    (run_row,) = [row for row in fetch(db, PayoutAutomaticRun) if row.period_key == "2026-07-22"]
    if expected_reason is not None:
        assert run_row.exclusions == {
            expected_reason: {"count": 1, "amount": f"{entry.amount:.2f}"}
        }
    else:
        assert run_row.exclusions == {}


def test_open_dispute_alone_keeps_the_driver_manual(postgis_db_sessionmaker, settings) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-dispute")
    install_automatic(db)
    # A dispute on a different trip's flag, whose trip is already paid out.
    other = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(days=1))
    drive(db, settings, other, key="auto-dispute-other")

    async def dispute():
        async with db() as session:
            analytics = await session.scalar(
                select(TripAnalytics).where(TripAnalytics.trip_session_id == other.id)
            )
            flag = FraudFlag(
                trip_session_id=other.id,
                trip_analytics_id=analytics.id,
                assignment_id=graph.assignment.id,
                campaign_id=graph.campaign.id,
                driver_profile_id=graph.profile.id,
                vehicle_id=graph.vehicle.id,
                flag_type="impossible_speed",
                severity="low",
                status="open",
                description="Synthetic review evidence.",
                evidence={},
                detected_at=TRIP_START,
            )
            session.add(flag)
            await session.flush()
            session.add(
                FraudDispute(
                    fraud_flag_id=flag.id,
                    driver_profile_id=graph.profile.id,
                    submitted_by_user_id=graph.driver.id,
                    message="Synthetic dispute.",
                )
            )
            await session.commit()

    asyncio.run(dispute())
    result = run(db, auto(settings))
    assert result["line_count"] == 0
    (run_row,) = fetch(db, PayoutAutomaticRun)
    # The open-driver dispute is filtered before the bounded candidate window.
    assert run_row.exclusions == {}
    assert entry_for(db, graph.trip.id).status == "available"


def test_first_payment_to_an_account_needs_a_person_then_later_ones_are_automatic(
    postgis_db_sessionmaker, settings, monkeypatch
) -> None:
    monkeypatch.setattr(automatic, "bank_account_paid_before", REAL_BANK_ACCOUNT_PAID_BEFORE)
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-firstpay")
    install_automatic(db)
    first = entry_for(db, graph.trip.id)
    assert run(db, auto(settings))["line_count"] == 0
    (run_row,) = fetch(db, PayoutAutomaticRun)
    assert run_row.exclusions == {
        "new_bank_destination": {"count": 1, "amount": f"{first.amount:.2f}"}
    }

    async def person_reserves_first():
        async with db() as session:
            draft = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            _, (line,) = await reserve_payout_batch(
                session,
                batch_id=draft.id,
                ledger_entry_ids=(first.id,),
                actor_user_id=graph.admin.id,
            )
            await session.commit()
            return line

    manual_line = asyncio.run(person_reserves_first())
    execute(
        db,
        update(PayoutBatchLine)
        .where(PayoutBatchLine.id == manual_line.id)
        .values(
            status="succeeded",
            reservation_active=False,
            provider_transfer_reference="manual-synthetic-first",
        ),
    )
    execute(
        db,
        update(EarningsLedgerEntry).where(EarningsLedgerEntry.id == first.id).values(status="paid"),
    )
    second = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(days=1), minutes=120)
    drive(db, settings, second, minutes=120, key="auto-firstpay-2")
    release_all(db)
    assert run(db, auto(settings), now=RUN_AT + timedelta(days=1))["line_count"] == 1
    (automatic_line,) = fetch(
        db, PayoutBatchLine, PayoutBatchLine.ledger_entry_id == entry_for(db, second.id).id
    )
    assert automatic_line.bank_account_version_id == manual_line.bank_account_version_id


# --- the cross-campaign day ceiling -----------------------------------------------


def second_campaign_trip(db, settings, graph, *, rate="8000.00", started_at, key, minutes=120):
    """The same driver works a second daily-rate campaign later the same day."""
    execute(
        db,
        update(CampaignAssignment)
        .where(CampaignAssignment.id == graph.assignment.id)
        .values(status=CampaignAssignmentStatus.COMPLETED.value),
    )
    campaign = create_test_campaign(
        db,
        organization_id=graph.campaign.organization_id,
        created_by_user_id=graph.admin.id,
        campaign_status="active",
        start_at=graph.campaign.start_at,
        end_at=graph.campaign.end_at,
    )
    rule = create_v4_rule(db, campaign_id=campaign.id, admin_id=graph.admin.id)
    zone = add_target_zone(
        db,
        campaign_id=campaign.id,
        created_by_user_id=graph.admin.id,
        name="Target 2",
        lat_min=6.40,
        lat_max=6.60,
    )
    revision = create_v4_revision(
        db,
        campaign_id=campaign.id,
        rule_id=rule.id,
        admin_id=graph.admin.id,
        daily_rate_naira=rate,
    )
    assignment = create_test_campaign_assignment(
        db,
        campaign_id=campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        assigned_by_user_id=graph.admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
        activated_at=started_at - timedelta(hours=1),
    )
    insert_v4_binding(
        db, settings, assignment_id=assignment.id, revision=revision, zone_ids=[zone.id]
    )
    graph.campaign, graph.assignment = campaign, assignment
    trip = add_trip(db, settings, graph, started_at=started_at, minutes=minutes)
    drive(db, settings, trip, minutes=minutes, key=key)
    release_all(db)
    return trip


def test_cross_campaign_day_above_one_day_rate_stays_manual(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-cross")
    install_automatic(db)
    first = graph.trip
    # Long first trip reaches the synthetic ₦8,000 day on its own campaign.
    long_trip = add_trip(
        db, settings, graph, started_at=TRIP_START + timedelta(hours=1), minutes=120
    )
    drive(db, settings, long_trip, minutes=120, key="auto-cross-long")
    release_all(db)
    second = second_campaign_trip(
        db, settings, graph, started_at=TRIP_START + timedelta(hours=5), key="auto-cross-2"
    )
    earned = sum(
        (entry_for(db, trip.id).amount for trip in (first, long_trip, second)), Decimal("0")
    )
    assert earned > Decimal("8000.00")
    result = run(db, auto(settings))
    assert result["line_count"] == 0
    (run_row,) = fetch(db, PayoutAutomaticRun)
    assert run_row.exclusions["daily_limit"]["count"] == 3
    (alert,) = fetch(db, PayoutAutomaticAlert, PayoutAutomaticAlert.kind == "daily_limit")
    assert alert.lagos_day == DAY and alert.detail["ceiling"] == "8000.00"
    assert alert.detail["earned"] == f"{earned:.2f}"
    notices = fetch(db, Notification, Notification.type_key == "payout_automatic_alert")
    assert {notice.recipient_user_id for notice in notices} >= {graph.admin.id}
    assert CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID not in {n.recipient_user_id for n in notices}
    # A second pass on another period does not duplicate the same alert.
    run(db, auto(settings), now=RUN_AT + timedelta(days=1))
    assert len(fetch(db, PayoutAutomaticAlert, PayoutAutomaticAlert.kind == "daily_limit")) == 1


def test_cross_campaign_day_within_one_rate_is_paid(postgis_db_sessionmaker, settings) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-within")
    install_automatic(db)
    first = graph.trip
    second = second_campaign_trip(
        db,
        settings,
        graph,
        started_at=TRIP_START + timedelta(hours=3),
        key="auto-within-2",
        minutes=30,
    )
    total = entry_for(db, first.id).amount + entry_for(db, second.id).amount
    assert total <= Decimal("8000.00")
    result = run(db, auto(settings))
    assert (result["batch_count"], result["line_count"]) == (1, 2)
    (run_row,) = fetch(db, PayoutAutomaticRun)
    assert run_row.total_amount == total and run_row.exclusions == {}
    assert fetch(db, PayoutAutomaticAlert) == []


def test_cross_campaign_day_with_different_rates_stays_manual(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-rates")
    install_automatic(db)
    second_campaign_trip(
        db,
        settings,
        graph,
        rate="9000.00",
        started_at=TRIP_START + timedelta(hours=3),
        key="auto-rates-2",
        minutes=30,
    )
    result = run(db, auto(settings))
    assert result["line_count"] == 0
    (run_row,) = fetch(db, PayoutAutomaticRun)
    assert run_row.exclusions["daily_limit"]["count"] == 2
    (alert,) = fetch(db, PayoutAutomaticAlert, PayoutAutomaticAlert.kind == "daily_limit")
    assert alert.detail["rates_differ"] is True and alert.detail["ceiling"] is None


def test_cash_guard_counts_automatic_lines_already_sent(postgis_db_sessionmaker, settings) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-cash")
    install_automatic(db)
    run(db, auto(settings))  # pays the first trip automatically
    first_line = fetch(db, PayoutBatchLine)[0]
    # A later recompute lowers the day's earnings, then a new trip arrives: the
    # already-sent automatic cash still counts against the day rate.
    second = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(hours=2), minutes=120)
    drive(db, settings, second, minutes=120, key="auto-cash-2")
    release_all(db)
    second_entry = entry_for(db, second.id)
    execute(
        db,
        update(PayoutBatchLine)
        .where(PayoutBatchLine.id == first_line.id)
        .values(amount=Decimal("8000.00") - second_entry.amount + Decimal("0.01")),
    )
    result = run(db, auto(settings), now=RUN_AT + timedelta(days=1))
    assert result["line_count"] == 0
    alerts = fetch(db, PayoutAutomaticAlert, PayoutAutomaticAlert.kind == "daily_limit")
    assert alerts and alerts[0].ledger_entry_id == second_entry.id


def test_cash_guard_counts_manual_lines_paid_the_same_day(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-mcash")
    install_automatic(db)
    first = entry_for(db, graph.trip.id)

    async def manual_reserve():
        async with db() as session:
            draft = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            _, lines = await reserve_payout_batch(
                session,
                batch_id=draft.id,
                ledger_entry_ids=(first.id,),
                actor_user_id=graph.admin.id,
            )
            await session.commit()
            return lines[0]

    manual_line = asyncio.run(manual_reserve())
    second = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(hours=2), minutes=120)
    drive(db, settings, second, minutes=120, key="auto-mcash-2")
    release_all(db)
    second_entry = entry_for(db, second.id)
    # The first trip was paid by hand; a later recompute lowered the day, so the
    # cash already paid plus the new trip now exceeds one day rate.
    execute(
        db,
        update(PayoutBatchLine)
        .where(PayoutBatchLine.id == manual_line.id)
        .values(
            status="succeeded",
            reservation_active=False,
            provider_transfer_reference="manual-synthetic-ref",
            amount=Decimal("8000.00") - second_entry.amount + Decimal("0.01"),
        ),
    )
    execute(
        db,
        update(EarningsLedgerEntry).where(EarningsLedgerEntry.id == first.id).values(status="paid"),
    )
    result = run(db, auto(settings))
    assert result["line_count"] == 0
    (run_row,) = fetch(db, PayoutAutomaticRun)
    assert run_row.exclusions["daily_limit"]["count"] == 1
    (alert,) = fetch(db, PayoutAutomaticAlert, PayoutAutomaticAlert.kind == "daily_limit")
    assert alert.ledger_entry_id == second_entry.id
    assert alert.detail["already_paid_or_sending"] == (
        f"{Decimal('8000.00') - second_entry.amount + Decimal('0.01'):.2f}"
    )


# --- run limit -------------------------------------------------------------------------


def test_run_limit_stops_at_first_miss_and_never_pays_an_entry_above_it(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-limit")
    install_automatic(db)
    extra = [
        add_trip(db, settings, graph, started_at=TRIP_START + timedelta(days=offset))
        for offset in (1, 2)
    ]
    for index, trip in enumerate(extra):
        drive(db, settings, trip, key=f"auto-limit-{index}")
    release_all(db)
    amounts = [entry_for(db, trip.id).amount for trip in (graph.trip, *extra)]
    limit = amounts[0] + amounts[1] + Decimal("0.01") - Decimal("0.02")  # fits one only
    result = run(db, auto(settings, payout_automatic_batch_limit_ngn=limit))
    assert result["line_count"] == 1
    (run_row,) = fetch(db, PayoutAutomaticRun)
    assert run_row.total_amount == amounts[0] <= limit
    (alert,) = fetch(db, PayoutAutomaticAlert, PayoutAutomaticAlert.kind == "batch_limit")
    assert alert.detail["reason"] == "run_limit_reached"
    assert alert.detail["waiting_candidates"] == 2
    # An entry larger than the whole limit is never automatic.
    tiny = Decimal("1.00")
    result = run(
        db,
        auto(settings, payout_automatic_batch_limit_ngn=tiny),
        now=RUN_AT + timedelta(days=1),
    )
    assert result["line_count"] == 0
    over = [
        alert
        for alert in fetch(db, PayoutAutomaticAlert, PayoutAutomaticAlert.kind == "batch_limit")
        if alert.detail["reason"] == "above_run_limit"
    ]
    assert len(over) == 2


# --- pause, release, claim authority --------------------------------------------------


def test_pause_blocks_submission_but_not_lookups_and_is_audited(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-pause")
    install_automatic(db)
    fake = FakeDisbursementAdapter()
    run(db, auto(settings), adapter=fake)
    (intent,) = fetch(db, PayoutSubmissionIntent)

    async def pause(paused: bool, reason: str):
        async with db() as session:
            await automatic.set_automatic_payouts_paused(
                session, paused=paused, reason=reason, actor_user_id=graph.admin.id
            )
            await session.commit()

    asyncio.run(pause(True, "Bank holiday check"))
    with pytest.raises(AppError) as twice:
        asyncio.run(pause(True, "Again"))
    assert twice.value.code == "PAYOUT_AUTOMATIC_ALREADY_PAUSED"
    with pytest.raises(AppError) as short:
        asyncio.run(pause(False, "  "))
    assert short.value.code == "PAYOUT_AUTOMATIC_REASON_INVALID"
    # Paused: the SUBMIT claim is skipped with no provider effect.
    assert (
        asyncio.run(
            process_payout_submission_intent(
                db, intent_id=intent.id, adapter=fake, settings=auto(settings)
            )
        )
        == "skipped"
    )
    assert fake.calls == []
    # A claimed-but-expired intent is still looked up while paused.
    execute(
        db,
        update(PayoutSubmissionIntent)
        .where(PayoutSubmissionIntent.id == intent.id)
        .values(state="query_only"),
    )
    assert (
        asyncio.run(
            process_payout_submission_intent(
                db, intent_id=intent.id, adapter=fake, settings=auto(settings)
            )
        )
        == "pending"
    )
    asyncio.run(pause(False, "Checked with the bank"))
    assert (
        asyncio.run(
            process_payout_submission_intent(
                db, intent_id=intent.id, adapter=fake, settings=auto(settings)
            )
        )
        == "resolved"
    )
    audits = fetch(
        db,
        AuditEvent,
        AuditEvent.action.in_(("admin.payout_automatic.paused", "admin.payout_automatic.resumed")),
    )
    assert [
        (a.actor_user_id, a.event_metadata["reason"])
        for a in sorted(audits, key=lambda a: a.created_at)
    ] == [
        (graph.admin.id, "Bank holiday check"),
        (graph.admin.id, "Checked with the bank"),
    ]
    (control,) = fetch(db, PayoutAutomaticControl)
    assert control.changed_by_user_id == graph.admin.id and not control.paused


def test_paused_automatic_intents_do_not_starve_the_send_queue(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-qa")
    install_automatic(db)
    fake = FakeDisbursementAdapter()
    run(db, auto(settings), adapter=fake)
    (automatic_intent,) = fetch(db, PayoutSubmissionIntent)
    # Another driver's earning goes through the normal maker-checker path.
    other = build_manual_graph(db, "auto-qb")

    async def manual_submit():
        async with db() as session:
            other_entry_id = (await _seed_authority(session, other)).id
            checker = User(
                email=f"starve-checker-{uuid4().hex}@example.com",
                password_hash=other.admin.password_hash,
                full_name="Starve Checker",
                role="admin",
                status="active",
            )
            session.add(checker)
            await session.flush()
            draft = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=other.admin.id
            )
            await reserve_payout_batch(
                session,
                batch_id=draft.id,
                ledger_entry_ids=(other_entry_id,),
                actor_user_id=other.admin.id,
            )
            await approve_payout_batch(session, batch_id=draft.id, actor_user_id=checker.id)
            await submit_payout_batch(
                session, batch_id=draft.id, actor_user_id=other.admin.id, adapter=fake
            )
            await session.commit()

    asyncio.run(manual_submit())
    (manual_intent,) = [
        intent for intent in fetch(db, PayoutSubmissionIntent) if intent.id != automatic_intent.id
    ]

    def due(configured: Settings, limit: int = 100) -> tuple:
        async def go():
            async with db() as session:
                return await find_due_payout_submission_intent_ids(
                    session, limit=limit, settings=configured
                )

        return asyncio.run(go())

    # Running normally, both are due.
    assert set(due(auto(settings))) == {automatic_intent.id, manual_intent.id}
    execute(
        db,
        update(PayoutAutomaticControl).values(
            paused=True,
            reason="Synthetic pause",
            changed_by_user_id=graph.admin.id,
            changed_at=RUN_AT,
        ),
    )
    # Paused: the unsendable automatic intent never takes the only place.
    assert due(auto(settings), limit=1) == (manual_intent.id,)
    assert due(auto(settings)) == (manual_intent.id,)
    # Switched off in settings behaves the same.
    execute(db, update(PayoutAutomaticControl).values(paused=False, reason="Synthetic resume"))
    assert due(settings) == (manual_intent.id,)
    # A lookup on an automatic intent stays due while blocked.
    execute(
        db,
        update(PayoutSubmissionIntent)
        .where(PayoutSubmissionIntent.id == automatic_intent.id)
        .values(state="query_only"),
    )
    assert set(due(settings)) == {automatic_intent.id, manual_intent.id}


def test_changed_actor_name_blocks_the_run(postgis_db_sessionmaker, settings) -> None:
    db = postgis_db_sessionmaker
    clean_graph(db, settings, "auto-rename")
    install_automatic(db)
    execute(
        db,
        update(User)
        .where(User.id == CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID)
        .values(full_name="Terrax Media Finance"),
    )
    assert run(db, auto(settings)) == {"outcome": "actor_invalid", "reason": "actor_changed"}
    assert fetch(db, PayoutBatch) == []
    (alert,) = fetch(db, PayoutAutomaticAlert)
    assert alert.kind == "run_failed" and alert.detail["reason"] == "actor_changed"


def test_release_requires_pause_and_only_cancels_untried_payments(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-release")
    install_automatic(db)
    run(db, auto(settings))

    async def release(configured: Settings):
        async with db() as session:
            result = await automatic.release_unsent_automatic_payments(
                session,
                reason="Moving to manual",
                actor_user_id=graph.admin.id,
                settings=configured,
            )
            await session.commit()
            return result

    with pytest.raises(AppError) as running:
        asyncio.run(release(auto(settings)))
    assert running.value.code == "PAYOUT_AUTOMATIC_RELEASE_REQUIRES_PAUSE"
    # Switched off in settings is enough to release (R3).
    result = asyncio.run(release(settings))
    assert result["released_count"] == 1
    (line,) = fetch(db, PayoutBatchLine)
    assert line.status == "void" and line.reservation_active is False
    (batch,) = fetch(db, PayoutBatch)
    assert batch.status == "void"
    (intent,) = fetch(db, PayoutSubmissionIntent)
    assert intent.state == "cancelled"
    (audit,) = fetch(
        db, AuditEvent, AuditEvent.action == "admin.payout_automatic.released_to_manual"
    )
    assert audit.event_metadata == {"reason": "Moving to manual", "line_ids": [str(line.id)]}

    # The released earning is now a normal manual candidate.
    async def manual():
        async with db() as session:
            draft = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            _, lines = await reserve_payout_batch(
                session,
                batch_id=draft.id,
                ledger_entry_ids=(line.ledger_entry_id,),
                actor_user_id=graph.admin.id,
            )
            await session.commit()
            return lines

    assert len(asyncio.run(manual())) == 1


def test_tampered_actor_blocks_runs_and_submission_but_not_lookups(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-tamper")
    install_automatic(db)
    fake = FakeDisbursementAdapter()
    run(db, auto(settings), adapter=fake)
    (intent,) = fetch(db, PayoutSubmissionIntent)
    execute(
        db,
        update(User).where(User.id == CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID).values(status="active"),
    )
    with pytest.raises(AppError) as refused:
        asyncio.run(
            process_payout_submission_intent(
                db, intent_id=intent.id, adapter=fake, settings=auto(settings)
            )
        )
    assert refused.value.code == "PAYOUT_AUTOMATIC_ACTOR_INVALID"
    assert fake.calls == []
    assert run(db, auto(settings), now=RUN_AT + timedelta(days=1)) == {
        "outcome": "actor_invalid",
        "reason": "actor_changed",
    }
    execute(
        db,
        update(PayoutSubmissionIntent)
        .where(PayoutSubmissionIntent.id == intent.id)
        .values(state="query_only"),
    )
    claim = asyncio.run(
        claim_payout_submission_intent(
            db, intent_id=intent.id, adapter=fake, settings=auto(settings)
        )
    )
    assert claim is not None and claim.action.value == "query"
    del graph


def test_final_gate_refuses_when_a_flag_appears_after_batching(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-late")
    install_automatic(db)
    fake = FakeDisbursementAdapter()
    run(db, auto(settings), adapter=fake)
    (intent,) = fetch(db, PayoutSubmissionIntent)
    add_flag(db, graph)
    with pytest.raises(AppError) as refused:
        asyncio.run(
            process_payout_submission_intent(
                db, intent_id=intent.id, adapter=fake, settings=auto(settings)
            )
        )
    assert refused.value.code == "PAYOUT_AUTOMATIC_NOT_CLEAN"
    assert fake.calls == []


# --- alerts ---------------------------------------------------------------------------------


def test_scanner_alerts_failures_duplicates_and_blocked_submissions_once(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-scan")
    install_automatic(db)
    fake = FakeDisbursementAdapter()
    run(db, auto(settings), adapter=fake)
    (intent,) = fetch(db, PayoutSubmissionIntent)
    asyncio.run(
        process_payout_submission_intent(
            db, intent_id=intent.id, adapter=fake, settings=auto(settings)
        )
    )
    (line,) = fetch(db, PayoutBatchLine)
    payload = json.dumps(
        {
            "provider_transfer_reference": line.provider_transfer_reference,
            "provider_event_id": "evt-auto-failed",
            "outcome": "failed",
            "occurred_at": "2026-07-21T02:00:00Z",
        }
    ).encode()

    async def fail_and_scan():
        async with db() as session:
            await reconcile_payout_webhook(
                session, payload=payload, signature=fake.sign_webhook(payload), adapter=fake
            )
            await session.commit()
        async with db() as session:
            attempt = PayoutSubmissionAttempt(
                intent_id=intent.id,
                generation=7,
                claim_token=uuid4(),
                action="query",
                idempotency_key=intent.idempotency_key,
                instruction_fingerprint=intent.instruction_fingerprint,
            )
            session.add(attempt)
            await session.flush()
            session.add(
                PayoutSubmissionObservation(
                    attempt_id=attempt.id,
                    intent_id=intent.id,
                    generation=attempt.generation,
                    idempotency_key=intent.idempotency_key,
                    instruction_fingerprint=intent.instruction_fingerprint,
                    outcome="submitted",
                    provider_submission_reference="dup-sub",
                    provider_transfer_reference="dup-ref",
                    evidence_fingerprint="f" * 64,
                    error_code="provider_transfer_reference_duplicate",
                    observed_at=RUN_AT,
                )
            )
            session.add(
                PayoutRecoveryIncident(
                    ledger_entry_id=line.ledger_entry_id,
                    chain_root_line_id=line.id,
                    exposure_line_id=line.id,
                    created_by_user_id=CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID,
                    kind="duplicate_cash",
                    status="contingent",
                    amount=line.amount,
                    currency="NGN",
                    dedupe_key=uuid4().hex + uuid4().hex,
                )
            )
            session.add(
                AuditEvent(
                    actor_user_id=None,
                    action="worker.payout_submission.failed",
                    entity_type="payout_submission_intent",
                    entity_id=str(intent.id),
                    event_metadata={"error_code": "PAYOUT_AUTOMATIC_NOT_CLEAN"},
                )
            )
            await session.commit()
        created = []
        for _ in range(2):
            async with db() as session:
                created.append(await automatic.scan_automatic_payout_alerts(session))
                await session.commit()
        return created

    assert asyncio.run(fail_and_scan())[1] == 0
    kinds = sorted(alert.kind for alert in fetch(db, PayoutAutomaticAlert))
    assert kinds == ["duplicate_payment", "duplicate_payment", "failed_payment"]
    # The worker audit was on a resolved intent, so no blocked alert; resolve one.
    alert = fetch(db, PayoutAutomaticAlert, PayoutAutomaticAlert.kind == "failed_payment")[0]

    async def resolve():
        async with db() as session:
            await automatic.resolve_automatic_payout_alert(
                session,
                alert_id=alert.id,
                note="Driver's bank details corrected",
                actor_user_id=graph.admin.id,
            )
            await session.commit()

    asyncio.run(resolve())
    (resolved,) = fetch(db, PayoutAutomaticAlert, PayoutAutomaticAlert.id == alert.id)
    assert resolved.resolved_by_user_id == graph.admin.id
    with pytest.raises(AppError) as again:
        asyncio.run(resolve())
    assert again.value.code == "PAYOUT_AUTOMATIC_ALERT_RESOLVED"


def test_new_duplicate_payment_is_alerted_past_the_scan_limit(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    clean_graph(db, settings, "auto-dupes")
    install_automatic(db)
    run(db, auto(settings))
    (line,) = fetch(db, PayoutBatchLine)

    async def incident_then_scan(number: int):
        async with db() as session:
            session.add(
                PayoutRecoveryIncident(
                    # Ascending ids: an id-ordered scan would always reread the oldest.
                    id=UUID(int=number),
                    ledger_entry_id=line.ledger_entry_id,
                    chain_root_line_id=line.id,
                    exposure_line_id=line.id,
                    created_by_user_id=CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID,
                    kind="duplicate_cash",
                    status="contingent",
                    amount=line.amount,
                    currency="NGN",
                    dedupe_key=uuid4().hex + uuid4().hex,
                )
            )
            await session.commit()
        async with db() as session:
            created = await automatic.scan_automatic_payout_alerts(session, limit=1)
            await session.commit()
            return created

    # Each scan reads one incident; the newer one is never hidden by the older.
    assert [asyncio.run(incident_then_scan(number)) for number in (1, 2, 3)] == [1, 1, 1]
    assert len(fetch(db, PayoutAutomaticAlert)) == 3


def test_blocked_submission_raises_one_alert(postgis_db_sessionmaker, settings) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-blocked")
    install_automatic(db)
    run(db, auto(settings))
    (intent,) = fetch(db, PayoutSubmissionIntent)

    other = build_manual_graph(db, "auto-manual-failure")

    async def audit_and_scan():
        async with db() as session:
            other_entry = await _seed_authority(session, other)
            checker = User(
                email=f"manual-failure-{uuid4().hex}@example.com",
                password_hash=other.admin.password_hash,
                full_name="Checker",
                role="admin",
                status="active",
            )
            session.add(checker)
            await session.flush()
            draft = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=other.admin.id
            )
            await reserve_payout_batch(
                session,
                batch_id=draft.id,
                ledger_entry_ids=(other_entry.id,),
                actor_user_id=other.admin.id,
            )
            await approve_payout_batch(session, batch_id=draft.id, actor_user_id=checker.id)
            await submit_payout_batch(
                session,
                batch_id=draft.id,
                actor_user_id=other.admin.id,
                adapter=FakeDisbursementAdapter(),
            )
            manual_intent = await session.scalar(
                select(PayoutSubmissionIntent).where(
                    PayoutSubmissionIntent.requested_by_user_id == other.admin.id
                )
            )
            for _ in range(7):
                session.add(
                    AuditEvent(
                        actor_user_id=None,
                        action="worker.payout_submission.failed",
                        entity_type="payout_submission_intent",
                        entity_id=str(manual_intent.id),
                        event_metadata={"error_code": "MANUAL_FAILURE"},
                    )
                )
            for _ in range(2):
                session.add(
                    AuditEvent(
                        actor_user_id=None,
                        action="worker.payout_submission.failed",
                        entity_type="payout_submission_intent",
                        entity_id=str(intent.id),
                        event_metadata={"error_code": "PAYOUT_AUTOMATIC_NOT_CLEAN"},
                        created_at=RUN_AT,
                    )
                )
            session.add(
                AuditEvent(
                    actor_user_id=None,
                    action="worker.payout_submission.failed",
                    entity_type="payout_submission_intent",
                    entity_id="not-a-uuid",
                    event_metadata={},
                )
            )
            await session.commit()
        async with db() as session:
            await automatic.scan_automatic_payout_alerts(session, limit=1)
            await session.commit()

    asyncio.run(audit_and_scan())
    (alert,) = fetch(db, PayoutAutomaticAlert)
    assert alert.kind == "submission_blocked"
    assert alert.detail["error_code"] == "PAYOUT_AUTOMATIC_NOT_CLEAN"
    del graph


# --- API -------------------------------------------------------------------------------------


def test_finance_api_status_pause_alerts_and_reconciliation(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-api")
    install_automatic(db)
    fake = FakeDisbursementAdapter()
    run(db, auto(settings), adapter=fake)
    (intent,) = fetch(db, PayoutSubmissionIntent)
    asyncio.run(
        process_payout_submission_intent(
            db, intent_id=intent.id, adapter=fake, settings=auto(settings)
        )
    )
    headers = auth_headers(postgis_db_client, graph.admin.email)
    status = postgis_db_client.get("/api/v1/admin/payouts/automatic/status", headers=headers)
    assert status.status_code == 200
    body = status.json()
    # The app's own settings are unset: automatic payouts are "not set up".
    assert body["switched_on"] is False and body["runnable"] is False
    assert "PAYOUT_AUTOMATIC_FREQUENCY" in body["missing_settings"]
    assert body["identity_ready"] is True and body["provider_ready"] is False
    assert body["last_run"]["line_count"] == 1
    paused = postgis_db_client.post(
        "/api/v1/admin/payouts/automatic/pause", headers=headers, json={"reason": "Month-end check"}
    )
    assert paused.status_code == 200 and paused.json()["paused"] is True
    assert paused.json()["pause_changed_by_name"] == graph.admin.full_name
    bad = postgis_db_client.post(
        "/api/v1/admin/payouts/automatic/resume", headers=headers, json={"reason": "x"}
    )
    assert bad.status_code == 422
    resumed = postgis_db_client.post(
        "/api/v1/admin/payouts/automatic/resume", headers=headers, json={"reason": "Done"}
    )
    assert resumed.status_code == 200 and resumed.json()["paused"] is False
    released = postgis_db_client.post(
        "/api/v1/admin/payouts/automatic/release-unsent", headers=headers, json={"reason": "None"}
    )
    # Settings are unset in the app, so release is allowed; the only line is already sent.
    assert released.status_code == 200 and released.json() == {
        "released_count": 0,
        "released_amount": "0.00",
    }
    alerts = postgis_db_client.get("/api/v1/admin/payouts/automatic/alerts", headers=headers)
    assert alerts.status_code == 200 and alerts.json()["total"] == 0
    today = automatic.lagos_day_for(datetime.now(UTC)).isoformat()
    recon = postgis_db_client.get(
        "/api/v1/admin/payouts/automatic/reconciliation",
        headers=headers,
        params={"day": today},
    )
    assert recon.status_code == 200
    data = recon.json()
    assert data["day"] == today
    assert [run_["line_count"] for run_ in data["runs"]] == [1]
    entry = entry_for(db, graph.trip.id)
    assert data["outcomes"] == [
        {"outcome": "submitted", "count": 1, "amount": f"{entry.amount:.2f}"}
    ]
    assert data["awaiting_provider_count"] == 1
    assert data["lines"][0]["driver_name"] == graph.driver.full_name
    summaries = postgis_db_client.get(
        "/api/v1/admin/payout-batches/summaries", headers=headers
    ).json()["items"]
    assert summaries[0]["approval_mode"] == "automatic"
    assert summaries[0]["checker_name"] is None
    assert summaries[0]["maker_name"] == "Cardvert (automatic payouts)"
    manual_only = postgis_db_client.get(
        "/api/v1/admin/payout-batches/summaries",
        headers=headers,
        params={"approval_mode": "maker_checker", "batch_status": "submitted"},
    ).json()
    assert manual_only["total"] == 0
    automatic_only = postgis_db_client.get(
        "/api/v1/admin/payout-batches/summaries",
        headers=headers,
        params={"approval_mode": "automatic"},
    ).json()
    assert automatic_only["total"] == 1
    empty = postgis_db_client.get(
        "/api/v1/admin/payouts/automatic/reconciliation",
        headers=headers,
        params={"day": "2026-01-01"},
    )
    assert empty.status_code == 200 and empty.json()["lines"] == []
    driver_headers = auth_headers(postgis_db_client, graph.driver.email)
    for path in ("status", "alerts", "reconciliation"):
        assert (
            postgis_db_client.get(
                f"/api/v1/admin/payouts/automatic/{path}", headers=driver_headers
            ).status_code
            == 403
        )


def test_automatic_audit_targets_resolve_to_the_driver(postgis_db_sessionmaker, settings) -> None:
    from app.services.audit_subjects import resolve_audit_subjects

    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-subject")
    install_automatic(db)
    run(db, auto(settings))
    (run_row,) = fetch(db, PayoutAutomaticRun)
    (line,) = fetch(db, PayoutBatchLine)
    alerts = {}

    async def go():
        async with db() as session:
            for key, values in {
                "by_profile": {"driver_profile_id": graph.profile.id},
                "by_line": {"line_id": line.id},
            }.items():
                alert = PayoutAutomaticAlert(
                    kind="failed_payment", dedupe_key=f"subject-{key}", detail={}, **values
                )
                session.add(alert)
                await session.flush()
                alerts[key] = alert.id
            connection = await session.connection()
            results = {}
            for name, entity_type, entity_id in (
                ("run", "payout_automatic_run", run_row.id),
                ("alert_profile", "payout_automatic_alert", alerts["by_profile"]),
                ("alert_line", "payout_automatic_alert", alerts["by_line"]),
                ("control", "payout_automatic_control", 1),
            ):
                results[name] = await connection.run_sync(
                    lambda sync, entity_type=entity_type, entity_id=entity_id: (
                        resolve_audit_subjects(
                            sync,
                            actor_user_id=graph.admin.id,
                            entity_type=entity_type,
                            entity_id=str(entity_id),
                            action="synthetic.subject",
                            metadata={},
                        )
                    )
                )
            await session.rollback()
            return results

    results = asyncio.run(go())
    driver_target = [("actor", graph.admin.id, "resolved"), ("target", graph.driver.id, "resolved")]
    assert results["run"] == [("actor", graph.admin.id, "resolved")]
    assert results["alert_profile"] == driver_target
    assert results["alert_line"] == driver_target
    # The pause switch holds no personal data: only the actor is recorded.
    assert results["control"] == [("actor", graph.admin.id, "resolved")]


def test_actor_cannot_sign_in(postgis_db_client, postgis_db_sessionmaker) -> None:
    install_automatic(postgis_db_sessionmaker)
    response = postgis_db_client.post(
        "/api/v1/auth/login",
        json={"email": CARDVERT_AUTOMATIC_PAYOUT_ACTOR_EMAIL, "password": "long-secure-password"},
    )
    assert response.status_code in {401, 403}


@pytest.mark.parametrize(
    "payload",
    [
        {"full_name": "Renamed"},
        {"status": "active", "current_password": "long-secure-password"},
    ],
)
def test_staff_cannot_edit_the_actor(postgis_db_client, postgis_db_sessionmaker, payload) -> None:
    install_automatic(postgis_db_sessionmaker)
    admin = create_test_user(
        postgis_db_sessionmaker, email="actor-editor@example.com", password="long-secure-password"
    )
    headers = auth_headers(postgis_db_client, admin.email, "long-secure-password")
    response = postgis_db_client.patch(
        f"/api/v1/admin/users/{CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID}", headers=headers, json=payload
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SYSTEM_ACCOUNT_READ_ONLY"
    users = fetch(postgis_db_sessionmaker, User)
    actor = next(u for u in users if u.id == CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID)
    assert (actor.full_name, actor.status) == ("Cardvert (automatic payouts)", "disabled")


def test_no_pay_calculation_changed_by_a_run(postgis_db_sessionmaker, settings) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-nopay")
    install_automatic(db)
    before = [(c.id, c.final_payout, c.amount_by_day) for c in fetch(db, PayoutCalculation)]
    run(db, auto(settings))
    after = [(c.id, c.final_payout, c.amount_by_day) for c in fetch(db, PayoutCalculation)]
    assert before == after
    assert entry_for(db, graph.trip.id).amount == before[0][1]


# --- PostgreSQL concurrency (plan review R2/AC6) ------------------------------------------


def test_postgres_concurrent_runs_pause_and_manual_reservation_serialize(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-race")
    install_automatic(db)
    entry = entry_for(db, graph.trip.id)
    configured = auto(settings)

    async def one_run():
        async with db() as session:
            result = await automatic.run_automatic_payouts(
                session, settings=configured, adapter=FakeDisbursementAdapter(), now=RUN_AT
            )
            await session.commit()
            return result["outcome"]

    async def pause():
        async with db() as session:
            await automatic.set_automatic_payouts_paused(
                session, paused=True, reason="Race pause", actor_user_id=graph.admin.id
            )
            await session.commit()
            return "paused"

    async def manual():
        async with db() as session:
            draft = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            try:
                await reserve_payout_batch(
                    session,
                    batch_id=draft.id,
                    ledger_entry_ids=(entry.id,),
                    actor_user_id=graph.admin.id,
                )
                await session.commit()
                return "reserved"
            except AppError as error:
                await session.rollback()
                return error.code

    async def race():
        return await asyncio.wait_for(
            asyncio.gather(one_run(), one_run(), manual(), pause()), timeout=60
        )

    outcomes = asyncio.run(race())
    # No deadlock; exactly one active reservation for the entry, whoever won.
    active = fetch(
        db,
        PayoutBatchLine,
        PayoutBatchLine.ledger_entry_id == entry.id,
        PayoutBatchLine.reservation_active.is_(True),
    )
    assert len(active) == 1
    assert len(fetch(db, PayoutAutomaticRun)) <= 1
    assert outcomes[3] == "paused"
    assert set(outcomes[:2]) <= {"completed", "already_ran", "paused", "conflict"}


def test_postgres_claim_run_and_pause_do_not_deadlock(postgis_db_sessionmaker, settings) -> None:
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "auto-race2")
    install_automatic(db)
    configured = auto(settings)
    fake = FakeDisbursementAdapter()
    run(db, configured, adapter=fake)
    (intent,) = fetch(db, PayoutSubmissionIntent)
    later = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(days=1))
    drive(db, settings, later, key="auto-race2-later")
    release_all(db)

    async def claim():
        return await process_payout_submission_intent(
            db, intent_id=intent.id, adapter=fake, settings=configured
        )

    async def next_run():
        async with db() as session:
            result = await automatic.run_automatic_payouts(
                session, settings=configured, adapter=fake, now=RUN_AT + timedelta(days=1)
            )
            await session.commit()
            return result["outcome"]

    async def pause():
        async with db() as session:
            await automatic.set_automatic_payouts_paused(
                session, paused=True, reason="Race pause", actor_user_id=graph.admin.id
            )
            await session.commit()
            return "paused"

    async def race():
        return await asyncio.wait_for(asyncio.gather(claim(), next_run(), pause()), timeout=60)

    claimed, ran, paused = asyncio.run(race())
    assert paused == "paused"
    assert claimed in {"resolved", "skipped"}
    assert ran in {"completed", "paused"}
    assert len(fake.calls) == (1 if claimed == "resolved" else 0)


def test_worker_job_scans_then_runs_with_the_context_adapter(
    postgis_db_sessionmaker, settings
) -> None:
    from app.jobs.automatic_payouts import sweep_automatic_payouts

    db = postgis_db_sessionmaker
    clean_graph(db, settings, "auto-job")
    install_automatic(db)
    configured = auto(settings)
    # The worker's default adapter is the disabled port: nothing is created.
    result = asyncio.run(sweep_automatic_payouts({"sessionmaker": db, "settings": configured}))
    assert result["outcome"] == "provider_unavailable" and result["alerts_created"] == 0
    assert fetch(db, PayoutBatch) == []
    result = asyncio.run(
        sweep_automatic_payouts(
            {
                "sessionmaker": db,
                "settings": configured,
                "disbursement_adapter": FakeDisbursementAdapter(),
            }
        )
    )
    assert result["outcome"] == "completed" and result["line_count"] == 1


def test_every_template_and_compose_file_leaves_automatic_payouts_off() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    expected = {
        "PAYOUT_AUTOMATIC_APPROVAL_ENABLED": "false",
        "PAYOUT_AUTOMATIC_FREQUENCY": "",
        "PAYOUT_AUTOMATIC_BATCH_LIMIT_NGN": "",
    }
    for name in (".env.example", "production.env.example", "staging.env.example"):
        lines = dict(
            line.split("=", 1)
            for line in (root / name).read_text().splitlines()
            if line and not line.startswith("#") and "=" in line
        )
        assert {key: lines[key] for key in expected} == expected, name
    for name in ("docker-compose.yml", "docker-compose.production.yml"):
        text = (root / name).read_text()
        for key, value in expected.items():
            assert f"  {key}: ${{{key}:-{value}}}\n" in text, (name, key)


# --- W1-P: full earnings, day attribution, audit and fairness ------------------


def test_w1p_cross_midnight_cash_is_attributed_by_saved_day(postgis_db_sessionmaker, settings):
    db = postgis_db_sessionmaker
    start = datetime(2026, 7, 20, 22, 45, tzinfo=UTC)
    graph = clean_graph(
        db, settings, "w1p-midnight", started_at=start, ended_at=start + timedelta(minutes=30)
    )
    install_automatic(db)
    result = run(db, auto(settings))
    assert result["line_count"] == 1
    entry = entry_for(db, graph.trip.id)
    calc = fetch(db, PayoutCalculation, PayoutCalculation.id == entry.payout_calculation_id)[0]
    expected = {
        date.fromisoformat(day): Decimal(amount)
        for day, amount in calc.amount_by_day.items()
        if Decimal(amount) > 0
    }
    assert len(expected) == 2
    assert sum(expected.values()) == entry.amount

    async def cash():
        async with db() as session:
            return await automatic._cash_by_day(session, driver_profile_id=graph.profile.id)

    assert asyncio.run(cash()) == expected


def test_w1p_alert_creation_audited_once_with_direct_subject(postgis_db_sessionmaker, settings):
    from app.models.audit import AuditEventSubjectResolution

    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "w1p-audit")
    install_automatic(db)

    async def create():
        async with db() as session:
            for _ in range(2):
                await automatic.raise_alert(
                    session,
                    kind=automatic.PayoutAutomaticAlertKind.DAILY_LIMIT,
                    dedupe=("w1p-audit",),
                    detail={"secret": "untrusted text"},
                    driver_profile_id=graph.profile.id,
                    amount=Decimal("8000.00"),
                )
            await session.commit()

    asyncio.run(create())
    (audit,) = fetch(db, AuditEvent, AuditEvent.action == "system.payout_automatic_alert.created")
    assert audit.event_metadata == {"kind": "daily_limit"}
    subjects = fetch(
        db, AuditEventSubjectResolution, AuditEventSubjectResolution.audit_event_id == audit.id
    )
    assert {(row.role, row.subject_user_id) for row in subjects} == {
        ("actor", CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID),
        ("target", graph.driver.id),
    }


def test_w1p_excluded_prefix_does_not_starve_later_candidate(
    postgis_db_sessionmaker, settings, monkeypatch
):
    db = postgis_db_sessionmaker
    old = clean_graph(db, settings, "w1p-excluded", payee=False)
    new = clean_graph(db, settings, "w1p-later")
    execute(
        db,
        update(EarningsLedgerEntry)
        .where(EarningsLedgerEntry.id == entry_for(db, old.trip.id).id)
        .values(occurred_at=TRIP_START - timedelta(days=1)),
    )
    install_automatic(db)
    monkeypatch.setattr(automatic, "MAX_CANDIDATES_PER_RUN", 1)
    # One admitted candidate place is independent of the scan-work bound.
    result = run(db, auto(settings))
    assert result["line_count"] == 1
    (line,) = fetch(db, PayoutBatchLine)
    assert line.ledger_entry_id == entry_for(db, new.trip.id).id
    assert entry_for(db, old.trip.id).status == "available"


def test_w1p_cursor_progress_wrap_ties_and_rollback(postgis_db_sessionmaker, settings, monkeypatch):
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "w1p-cursor", payee=False)
    later = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(days=1))
    drive(db, settings, later, key="w1p-cursor-later")
    release_all(db)
    install_automatic(db)
    monkeypatch.setattr(automatic, "MAX_ENTRIES_SCANNED_PER_RUN", 1)
    entries = [entry_for(db, trip.id) for trip in (graph.trip, later)]
    # Equal timestamps force the id tie-break; an all-excluded run still moves.
    execute(db, update(EarningsLedgerEntry).values(occurred_at=TRIP_START))
    ordered = sorted(entries, key=lambda row: row.id)
    assert run(db, auto(settings))["line_count"] == 0
    assert fetch(db, PayoutAutomaticControl)[0].candidate_cursor_id == ordered[0].id
    assert run(db, auto(settings), now=RUN_AT + timedelta(days=1))["line_count"] == 0
    assert fetch(db, PayoutAutomaticControl)[0].candidate_cursor_id == ordered[1].id
    add_payee(db, graph)

    async def rollback():
        async with db() as session:
            result = await automatic.run_automatic_payouts(
                session,
                settings=auto(settings),
                adapter=FakeDisbursementAdapter(),
                now=RUN_AT + timedelta(days=2),
            )
            assert result["line_count"] == 1
            await session.rollback()

    asyncio.run(rollback())
    assert fetch(db, PayoutAutomaticControl)[0].candidate_cursor_id == ordered[1].id
    assert fetch(db, PayoutBatchLine) == []
    assert run(db, auto(settings), now=RUN_AT + timedelta(days=2))["line_count"] == 1
    assert fetch(db, PayoutBatchLine)[0].ledger_entry_id == ordered[0].id
    assert run(db, auto(settings), now=RUN_AT + timedelta(days=3))["line_count"] == 1
    assert {line.ledger_entry_id for line in fetch(db, PayoutBatchLine)} == {
        row.id for row in entries
    }


@pytest.mark.parametrize("target,expected", [("1.000", "10000.00"), ("8.000", None)])
def test_w1p_full_and_short_day_send_exact_earnings_without_fee_setup(
    postgis_db_sessionmaker, settings, target, expected
):
    db = postgis_db_sessionmaker
    graph = clean_graph(
        db, settings, "w1p-full", daily_rate_naira="10000.00", daily_target_miles=target
    )
    install_automatic(db)
    entry = entry_for(db, graph.trip.id)
    calc = fetch(db, PayoutCalculation)[0]
    binding = fetch(db, automatic.AssignmentRuleBinding)[0]
    frozen = (
        calc.final_payout,
        calc.inputs_fingerprint,
        calc.amount_by_day,
        binding.daily_rate_naira,
        binding.daily_target_miles,
    )
    if expected:
        assert entry.amount == Decimal(expected)
    else:
        assert 0 < entry.amount < Decimal("10000.00")
    fake = FakeDisbursementAdapter()
    run(db, auto(settings), adapter=fake)
    intent = fetch(db, PayoutSubmissionIntent)[0]
    asyncio.run(
        process_payout_submission_intent(
            db, intent_id=intent.id, adapter=fake, settings=auto(settings)
        )
    )
    assert Decimal(fake.calls[0][1][0].instruction["amount"]) == entry.amount
    assert (
        asyncio.run(
            process_payout_submission_intent(
                db, intent_id=intent.id, adapter=fake, settings=auto(settings)
            )
        )
        == "skipped"
    )
    line = fetch(db, PayoutBatchLine)[0]
    payload = json.dumps(
        {
            "provider_transfer_reference": line.provider_transfer_reference,
            "provider_event_id": "w1p-full-paid",
            "outcome": "succeeded",
            "occurred_at": "2026-07-21T02:00:00Z",
        }
    ).encode()

    async def reconcile():
        async with db() as session:
            for _ in range(2):
                await reconcile_payout_webhook(
                    session, payload=payload, signature=fake.sign_webhook(payload), adapter=fake
                )
            await session.commit()

    asyncio.run(reconcile())
    paid = entry_for(db, graph.trip.id)
    assert (paid.status, paid.amount) == ("paid", entry.amount)
    assert fetch(db, PayoutBatchLine)[0].amount == entry.amount
    calc_after = fetch(db, PayoutCalculation)[0]
    binding_after = fetch(db, automatic.AssignmentRuleBinding)[0]
    assert (
        calc_after.final_payout,
        calc_after.inputs_fingerprint,
        calc_after.amount_by_day,
        binding_after.daily_rate_naira,
        binding_after.daily_target_miles,
    ) == frozen


def test_w1p_multiple_cross_midnight_entries_use_daily_shares(postgis_db_sessionmaker, settings):
    db = postgis_db_sessionmaker
    start = datetime(2026, 7, 20, 22, 40, tzinfo=UTC)
    graph = clean_graph(
        db,
        settings,
        "w1p-two-days",
        started_at=start,
        ended_at=start + timedelta(minutes=30),
        daily_target_miles="5.000",
    )
    later = add_trip(db, settings, graph, started_at=start + timedelta(days=1), minutes=30)
    drive(db, settings, later, key="w1p-two-days-later")
    release_all(db)
    install_automatic(db)
    result = run(db, auto(settings))
    assert result["line_count"] == 2
    assert sum(row.amount for row in fetch(db, PayoutBatchLine)) > Decimal("8000.00")
    # Both trips touch 21 July but each allocates only its actual share to it.
    expected = {}
    for calc in fetch(db, PayoutCalculation):
        for day, amount in calc.amount_by_day.items():
            if Decimal(amount) > 0:
                expected[date.fromisoformat(day)] = expected.get(
                    date.fromisoformat(day), 0
                ) + Decimal(amount)

    async def cash():
        async with db() as session:
            return await automatic._cash_by_day(session, driver_profile_id=graph.profile.id)

    assert asyncio.run(cash()) == expected


@pytest.mark.parametrize(
    "bad_map",
    [{}, {"invalid-day": "1.00"}, {"2026-07-20": "not-money"}, {"2026-07-20": "-1.00"}],
)
def test_w1p_unknown_cash_allocation_keeps_later_earning_manual(
    postgis_db_sessionmaker, settings, bad_map
):
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "w1p-bad-cash")
    install_automatic(db)
    run(db, auto(settings))
    first = entry_for(db, graph.trip.id)
    execute(
        db,
        update(PayoutCalculation)
        .where(PayoutCalculation.id == first.payout_calculation_id)
        .values(amount_by_day=bad_map),
    )
    later = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(days=1))
    drive(db, settings, later, key="w1p-bad-cash-later")
    release_all(db)
    result = run(db, auto(settings), now=RUN_AT + timedelta(days=1))
    assert result["line_count"] == 0
    (run_row,) = fetch(db, PayoutAutomaticRun, PayoutAutomaticRun.period_key == "2026-07-22")
    assert run_row.exclusions["cash_position_unavailable"]["count"] == 1
    assert entry_for(db, later.id).status == "available"
    (alert,) = fetch(db, PayoutAutomaticAlert, PayoutAutomaticAlert.kind == "daily_limit")
    assert alert.driver_profile_id == graph.profile.id
    assert alert.detail["reason"] == "cash_position_unavailable"
    assert any(row.payload.get("alert_id") == str(alert.id) for row in fetch(db, Notification))


def test_w1p_reconciliation_excludes_another_days_submitted_line(postgis_db_sessionmaker, settings):
    db = postgis_db_sessionmaker
    clean_graph(db, settings, "w1p-reconcile")
    install_automatic(db)
    fake = FakeDisbursementAdapter()
    run(db, auto(settings), adapter=fake)
    intent = fetch(db, PayoutSubmissionIntent)[0]
    asyncio.run(
        process_payout_submission_intent(
            db, intent_id=intent.id, adapter=fake, settings=auto(settings)
        )
    )
    batch = fetch(db, PayoutBatch)[0]
    execute(
        db,
        update(PayoutBatch)
        .where(PayoutBatch.id == batch.id)
        .values(created_at=RUN_AT - timedelta(days=1)),
    )

    async def reconciliation(day):
        async with db() as session:
            return await automatic.automatic_reconciliation_day(session, day=day)

    assert asyncio.run(reconciliation(DAY))["awaiting_provider_count"] == 1
    assert asyncio.run(reconciliation(DAY + timedelta(days=1)))["awaiting_provider_count"] == 0


def test_w1p_invalid_identity_alerts_progress_past_already_alerted_intents(
    postgis_db_sessionmaker, settings
):
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "w1p-invalid")
    later = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(days=1))
    drive(db, settings, later, key="w1p-invalid-later")
    release_all(db)
    install_automatic(db)
    run(db, auto(settings))
    execute(
        db,
        update(User)
        .where(User.id == CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID)
        .values(full_name="Changed identity"),
    )

    async def scan():
        async with db() as session:
            assert (
                await find_due_payout_submission_intent_ids(session, settings=auto(settings)) == ()
            )
            created = await automatic.scan_automatic_payout_alerts(session, limit=1)
            await session.commit()
            return created

    assert [asyncio.run(scan()) for _ in range(3)] == [1, 1, 0]
    assert (
        len(fetch(db, PayoutAutomaticAlert, PayoutAutomaticAlert.kind == "submission_blocked")) == 2
    )
    assert fetch(db, PayoutSubmissionAttempt) == []
    execute(db, update(PayoutSubmissionIntent).values(state="query_only"))

    async def due():
        async with db() as session:
            return await find_due_payout_submission_intent_ids(session, settings=auto(settings))

    assert len(asyncio.run(due())) == 2


def test_w1p_alert_transaction_rollback_and_missing_actor(postgis_db_sessionmaker, monkeypatch):
    db = postgis_db_sessionmaker

    async def failing_notice(*args, **kwargs):
        raise RuntimeError("synthetic notice failure")

    async def attempt(fail):
        async with db() as session:
            try:
                await automatic.raise_alert(
                    session,
                    kind=automatic.PayoutAutomaticAlertKind.RUN_FAILED,
                    dedupe=("w1p-rollback",),
                    detail={"reason": "control_missing"},
                )
                if fail:
                    raise AssertionError("notice should fail")
                await session.commit()
            except RuntimeError:
                await session.rollback()
                if not fail:
                    raise

    with monkeypatch.context() as patch:
        patch.setattr(automatic, "create_active_admin_notices", failing_notice)
        asyncio.run(attempt(True))
    assert fetch(db, PayoutAutomaticAlert) == []
    assert fetch(db, AuditEvent) == []
    asyncio.run(attempt(False))
    audit = fetch(db, AuditEvent)[0]
    assert audit.actor_user_id is None
    assert audit.event_metadata == {"kind": "run_failed"}


def test_w1p_run_audit_stored_subject_is_actor_only(postgis_db_sessionmaker, settings):
    from app.models.audit import AuditEventSubjectResolution

    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "w1p-run-subject")
    install_automatic(db)
    run(db, auto(settings))
    (audit,) = fetch(db, AuditEvent, AuditEvent.action == "system.payout_automatic_run.completed")
    (subject,) = fetch(
        db, AuditEventSubjectResolution, AuditEventSubjectResolution.audit_event_id == audit.id
    )
    assert (subject.role, subject.subject_user_id, subject.outcome) == (
        "actor",
        CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID,
        "resolved",
    )
    assert subject.subject_user_id != graph.driver.id


def test_w1p_concurrent_alert_attempts_create_one_audit(postgis_db_sessionmaker, settings):
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "w1p-alert-race")
    install_automatic(db)

    async def create():
        async with db() as session:
            result = await automatic.raise_alert(
                session,
                kind=automatic.PayoutAutomaticAlertKind.DAILY_LIMIT,
                dedupe=("w1p-concurrent",),
                detail={},
                driver_profile_id=graph.profile.id,
            )
            await session.commit()
            return result is not None

    async def race():
        return await asyncio.wait_for(asyncio.gather(create(), create()), timeout=20)

    assert sorted(asyncio.run(race())) == [False, True]
    assert len(fetch(db, PayoutAutomaticAlert)) == 1
    assert (
        len(fetch(db, AuditEvent, AuditEvent.action == "system.payout_automatic_alert.created"))
        == 1
    )


@pytest.mark.parametrize("phase", ["run", "claim"])
@pytest.mark.parametrize("winner", ["dispute", "payout"])
def test_w1p_dispute_and_automatic_authorization_serialize_on_postgres(
    postgis_db_sessionmaker, settings, monkeypatch, phase, winner
):
    from sqlalchemy import text

    from app.services import disbursements, fraud_disputes
    from app.services.fraud_holds import lock_fraud_reconciliation_gate

    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "w1p-dispute-race")
    other = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(days=1))
    drive(db, settings, other, key="w1p-dispute-other")
    original_trip = graph.trip
    graph.trip = other
    flag = add_flag(db, graph, flag_status="open")
    graph.trip = original_trip
    install_automatic(db)
    fake = FakeDisbursementAdapter()
    if phase == "claim":
        assert run(db, auto(settings), adapter=fake)["line_count"] == 1
        intent_id = fetch(db, PayoutSubmissionIntent)[0].id

    async def scenario():
        waiting = asyncio.Event()
        ready = asyncio.Event()
        release = asyncio.Event()
        wait_pid = None

        async def observed_gate(session, *, exclusive):
            nonlocal wait_pid
            if exclusive == (winner == "dispute"):
                wait_pid = await session.scalar(text("SELECT pg_backend_pid()"))
                waiting.set()
            await lock_fraud_reconciliation_gate(session, exclusive=exclusive)

        # The real advisory locks remain; hooks only expose the barrier and pid.
        monkeypatch.setattr(automatic, "lock_fraud_reconciliation_gate", observed_gate)
        monkeypatch.setattr(disbursements, "lock_fraud_reconciliation_gate", observed_gate)
        monkeypatch.setattr(fraud_disputes, "lock_fraud_reconciliation_gate", observed_gate)

        async def assert_blocked(holder_pid, task):
            await asyncio.wait_for(waiting.wait(), timeout=10)
            async with db() as monitor:
                for _ in range(100):
                    blockers = await monitor.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": wait_pid}
                    )
                    if holder_pid in blockers:
                        assert not task.done()
                        return
                    await asyncio.sleep(0.01)
            raise AssertionError("Expected a real PostgreSQL advisory-lock wait")

        async def create_dispute():
            async with db() as session:
                result = await fraud_disputes.create_driver_dispute(
                    session,
                    flag_id=flag.id,
                    user_id=graph.driver.id,
                    message="Please review the other trip",
                )
                await session.commit()
                return result.dispute.id

        async def payout():
            if phase == "claim":
                try:
                    return await claim_payout_submission_intent(
                        db, intent_id=intent_id, adapter=fake, settings=auto(settings)
                    )
                except AppError as exc:
                    return exc.code
            async with db() as session:
                result = await automatic.run_automatic_payouts(
                    session, settings=auto(settings), adapter=fake, now=RUN_AT
                )
                await session.commit()
                return result

        if winner == "dispute":
            async with db() as holder:
                await fraud_disputes.create_driver_dispute(
                    holder,
                    flag_id=flag.id,
                    user_id=graph.driver.id,
                    message="Please review the other trip",
                )
                holder_pid = await holder.scalar(text("SELECT pg_backend_pid()"))
                task = asyncio.create_task(payout())
                await assert_blocked(holder_pid, task)
                await holder.commit()
            result = await asyncio.wait_for(task, timeout=20)
            if phase == "run":
                assert result["line_count"] == 0
            else:
                assert result == "PAYOUT_AUTOMATIC_NOT_CLEAN"
            assert fake.calls == []
        elif phase == "run":
            async with db() as holder:
                result = await automatic.run_automatic_payouts(
                    holder, settings=auto(settings), adapter=fake, now=RUN_AT
                )
                holder_pid = await holder.scalar(text("SELECT pg_backend_pid()"))
                task = asyncio.create_task(create_dispute())
                await assert_blocked(holder_pid, task)
                await holder.commit()
            assert result["line_count"] == 1
            await asyncio.wait_for(task, timeout=20)
            intent = await _w1p_intent_in_loop(db)
            assert intent is not None and intent.state == "pending"
            assert (
                await payout_claim_code(db, intent.id, fake, auto(settings))
                == "PAYOUT_AUTOMATIC_NOT_CLEAN"
            )
        else:
            authority = automatic.automatic_final_clean_authority
            holder_pid = None

            async def authorization_barrier(session, **kwargs):
                nonlocal holder_pid
                result = await authority(session, **kwargs)
                holder_pid = await session.scalar(text("SELECT pg_backend_pid()"))
                ready.set()
                await asyncio.wait_for(release.wait(), timeout=20)
                return result

            monkeypatch.setattr(automatic, "automatic_final_clean_authority", authorization_barrier)
            payout_task = asyncio.create_task(payout())
            await asyncio.wait_for(ready.wait(), timeout=10)
            dispute_task = asyncio.create_task(create_dispute())
            await assert_blocked(holder_pid, dispute_task)
            release.set()
            claim = await asyncio.wait_for(payout_task, timeout=20)
            assert claim.action.value == "submit"
            await asyncio.wait_for(dispute_task, timeout=20)
            # A dispute after committed claim is outside this authorization boundary.
            assert fake.calls == []

    asyncio.run(scenario())


async def _w1p_intent_in_loop(db):
    async with db() as session:
        return await session.scalar(select(PayoutSubmissionIntent))


async def payout_claim_code(db, intent_id, fake, settings):
    try:
        await claim_payout_submission_intent(
            db, intent_id=intent_id, adapter=fake, settings=settings
        )
    except AppError as exc:
        return exc.code
    raise AssertionError("Submission should be refused")


@pytest.mark.parametrize(
    "over_ceiling,zero_pay_day", [(False, False), (True, False), (False, True)]
)
def test_w1p_paid_manual_correction_uses_trip_days_and_respects_ceiling(
    postgis_db_sessionmaker, settings, monkeypatch, over_ceiling, zero_pay_day
):
    db = postgis_db_sessionmaker
    monkeypatch.setattr(automatic, "bank_account_paid_before", REAL_BANK_ACCOUNT_PAID_BEFORE)
    start = datetime(2026, 7, 20, 22, 45, tzinfo=UTC)
    graph = clean_graph(
        db,
        settings,
        "w1p-manual-correction",
        started_at=start,
        ended_at=start + timedelta(minutes=30),
        daily_target_miles="70.000",
    )
    install_automatic(db)
    later = add_trip(db, settings, graph, started_at=start + timedelta(hours=3))
    drive(db, settings, later, key="w1p-manual-correction-later")
    release_all(db)
    later_entry = entry_for(db, later.id)
    correction_amount = Decimal("8000.00") - later_entry.amount
    correction_amount += Decimal("0.01") if over_ceiling else Decimal("-0.01")
    assert correction_amount > 0
    calculation = fetch(
        db, PayoutCalculation, PayoutCalculation.trip_session_id == graph.trip.id
    )[0]
    assert len(calculation.amount_by_day) == 2
    fake = FakeDisbursementAdapter()

    async def submit_correction():
        async with db() as session:
            correction = await _seed_authority(session, graph, amount=str(correction_amount))
            assert correction.payout_calculation_id is None
            checker = User(
                email=f"correction-checker-{uuid4().hex}@example.com",
                password_hash=graph.admin.password_hash,
                full_name="Correction Checker",
                role="admin",
                status="active",
            )
            session.add(checker)
            await session.flush()
            draft = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            _, lines = await reserve_payout_batch(
                session,
                batch_id=draft.id,
                ledger_entry_ids=(correction.id,),
                actor_user_id=graph.admin.id,
            )
            await approve_payout_batch(session, batch_id=draft.id, actor_user_id=checker.id)
            await submit_payout_batch(
                session, batch_id=draft.id, actor_user_id=graph.admin.id, adapter=fake
            )
            intent_id = await session.scalar(
                select(PayoutSubmissionIntent.id).where(
                    PayoutSubmissionIntent.payout_batch_line_id == lines[0].id
                )
            )
            await session.commit()
            return correction.id, intent_id

    correction_id, manual_intent_id = asyncio.run(submit_correction())
    _w1p_pay_intent(db, manual_intent_id, fake, auto(settings), "manual-correction")
    correction = fetch(db, EarningsLedgerEntry, EarningsLedgerEntry.id == correction_id)[0]
    assert correction.status == "paid"
    if zero_pay_day:
        # A saved zero-pay day is still a known correction exposure day.
        allocation = dict(calculation.amount_by_day)
        allocation[min(allocation)] = "0.00"
        execute(
            db,
            update(PayoutCalculation)
            .where(PayoutCalculation.id == calculation.id)
            .values(amount_by_day=allocation),
        )

    async def cash():
        async with db() as session:
            return await automatic._cash_by_day(session, driver_profile_id=graph.profile.id)

    # Full correction on both original trip days, even though trip B uses one.
    assert asyncio.run(cash()) == {
        date.fromisoformat(day): correction_amount for day in calculation.amount_by_day
    }
    result = run(db, auto(settings), adapter=fake)
    if over_ceiling:
        assert result["line_count"] == 0
        assert entry_for(db, later.id).status == "available"
        (run_row,) = fetch(db, PayoutAutomaticRun)
        assert run_row.exclusions["daily_limit"]["count"] == 1
        (alert,) = fetch(db, PayoutAutomaticAlert, PayoutAutomaticAlert.kind == "daily_limit")
        assert alert.detail["already_paid_or_sending"] == str(correction_amount)
        assert len(fake.calls) == 1
    else:
        assert result["line_count"] == 1
        automatic_intent = fetch(
            db, PayoutSubmissionIntent, PayoutSubmissionIntent.id != manual_intent_id
        )[0]
        _w1p_pay_intent(db, automatic_intent.id, fake, auto(settings), "later-automatic")
        assert entry_for(db, later.id).status == "paid"
        assert Decimal(fake.calls[-1][1][0].instruction["amount"]) == later_entry.amount
        assert fetch(db, PayoutAutomaticAlert) == []


def _w1p_pay_intent(db, intent_id, fake, settings, event_id):
    async def pay():
        await process_payout_submission_intent(
            db, intent_id=intent_id, adapter=fake, settings=settings
        )
        async with db() as session:
            intent = await session.get(PayoutSubmissionIntent, intent_id)
            line = await session.get(PayoutBatchLine, intent.payout_batch_line_id)
            payload = json.dumps(
                {
                    "provider_transfer_reference": line.provider_transfer_reference,
                    "provider_event_id": event_id,
                    "outcome": "succeeded",
                    "occurred_at": "2026-07-21T06:00:00Z",
                }
            ).encode()
            await reconcile_payout_webhook(
                session, payload=payload, signature=fake.sign_webhook(payload), adapter=fake
            )
            await session.commit()

    asyncio.run(pay())


def test_w1p_run_limit_defers_next_entry_at_same_limit_after_wrap(
    postgis_db_sessionmaker, settings
):
    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "w1p-limit-wrap")
    later = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(days=1))
    drive(db, settings, later, key="w1p-limit-wrap-later")
    release_all(db)
    install_automatic(db)
    entries = [entry_for(db, trip.id) for trip in (graph.trip, later)]
    limit = max(entry.amount for entry in entries)
    assert sum(entry.amount for entry in entries) > limit
    # Start after both entries, so the first pass must wrap into the prefix.
    execute(
        db,
        update(PayoutAutomaticControl).values(
            candidate_cursor_at=RUN_AT + timedelta(days=10), candidate_cursor_id=uuid4()
        ),
    )
    configured = auto(settings, payout_automatic_batch_limit_ngn=limit)
    assert run(db, configured)["line_count"] == 1
    (line,) = fetch(db, PayoutBatchLine)
    deferred = next(entry for entry in entries if entry.id != line.ledger_entry_id)
    assert fetch(db, PayoutAutomaticControl)[0].candidate_cursor_id == line.ledger_entry_id
    assert run(db, configured, now=RUN_AT + timedelta(days=1))["line_count"] == 1
    assert {line.ledger_entry_id for line in fetch(db, PayoutBatchLine)} == {
        line.ledger_entry_id,
        deferred.id,
    }


@pytest.mark.parametrize("phase", ["run", "claim"])
def test_w1p_dispute_reply_serializes_before_payout_check(
    postgis_db_sessionmaker, settings, monkeypatch, phase
):
    from sqlalchemy import text

    from app.services import disbursements, fraud_disputes
    from app.services.fraud_holds import lock_fraud_reconciliation_gate

    db = postgis_db_sessionmaker
    graph = clean_graph(db, settings, "w1p-reply")
    other = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(days=1))
    drive(db, settings, other, key="w1p-reply-other")
    original_trip = graph.trip
    graph.trip = other
    flag = add_flag(db, graph, flag_status="open")
    graph.trip = original_trip
    install_automatic(db)
    fake = FakeDisbursementAdapter()
    if phase == "claim":
        run(db, auto(settings))
        intent = fetch(db, PayoutSubmissionIntent)[0]

    async def scenario():
        async with db() as session:
            created = await fraud_disputes.create_driver_dispute(
                session, flag_id=flag.id, user_id=graph.driver.id, message="Please check"
            )
            dispute_id = created.dispute.id
            await session.commit()
        entered = asyncio.Event()
        payout_pid = None

        async def observed(session, *, exclusive):
            nonlocal payout_pid
            if exclusive:
                payout_pid = await session.scalar(text("SELECT pg_backend_pid()"))
                entered.set()
            await lock_fraud_reconciliation_gate(session, exclusive=exclusive)

        monkeypatch.setattr(automatic, "lock_fraud_reconciliation_gate", observed)
        monkeypatch.setattr(disbursements, "lock_fraud_reconciliation_gate", observed)

        async def payout():
            if phase == "claim":
                return await claim_payout_submission_intent(
                    db, intent_id=intent.id, adapter=fake, settings=auto(settings)
                )
            async with db() as session:
                result = await automatic.run_automatic_payouts(
                    session, settings=auto(settings), adapter=fake, now=RUN_AT
                )
                await session.commit()
                return result

        async with db() as holder:
            await fraud_disputes.reply_to_dispute(
                holder,
                dispute_id=dispute_id,
                actor_user_id=graph.admin.id,
                reply="Reviewed the other trip",
            )
            holder_pid = await holder.scalar(text("SELECT pg_backend_pid()"))
            task = asyncio.create_task(payout())
            await asyncio.wait_for(entered.wait(), timeout=10)
            async with db() as monitor:
                for _ in range(100):
                    blockers = await monitor.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": payout_pid}
                    )
                    if holder_pid in blockers:
                        assert not task.done()
                        break
                    await asyncio.sleep(0.01)
                else:
                    raise AssertionError("Payout did not wait for the real reply lock")
            await holder.commit()
        result = await asyncio.wait_for(task, timeout=20)
        if phase == "run":
            assert result["line_count"] == 1
        else:
            assert result.action.value == "submit"
        assert fake.calls == []

    asyncio.run(scenario())

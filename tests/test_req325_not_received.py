"""REQ-325: payments refused after no-payment cancellations, and "payment not received"."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from conftest import auth_headers, create_test_campaign, fetch_audit_events
from database_helpers import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    upgrade_to,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_billing_corrections import _cancel_for_refund, _fixture
from test_financial_authority import _funded_terms
from test_receipt_allocations import _accepted_terms
from test_req314_money_fixes import _pay

from app.adapters.payments import FakePaymentGatewayAdapter
from app.core.errors import AppError
from app.models.billing import (
    Invoice,
    InvoiceCorrectionType,
    PaymentCheckoutIntent,
    PaymentClass,
    PaymentReceipt,
    ReceiptAllocation,
    ReceiptMethod,
    ReceiptNonReceipt,
    ReceiptReversalKind,
)
from app.models.campaign_cancellation import (
    CampaignCancellation,
    CampaignCancellationSettlementRevision,
)
from app.services.billing.checkout import prepare_invoice_payment_checkout
from app.services.billing.gateway import (
    ingest_payment_gateway_webhook,
    process_payment_gateway_event,
)
from app.services.billing.queries import cancellation_refund_position
from app.services.billing.receipts import (
    allocate_payment_receipt,
    confirm_payment_receipt,
    record_payment_receipt,
    record_receipt_not_received,
    reverse_payment_receipt,
)
from app.services.billing.settlements import record_invoice_correction, record_refund_settlement
from app.services.campaign_cancellations import _digest
from app.services.payout_rule_serialization import acquire_campaign_terms_lock

REFUND = ReceiptReversalKind.REFUND
NOT_RECEIVED = ReceiptReversalKind.NOT_RECEIVED
PAYSTACK = SimpleNamespace(provider_name="paystack")


def _cutoff() -> datetime:
    return datetime.now(UTC) + timedelta(hours=1)


async def _reverse(session, admin, receipt_id, kind, reason="synthetic reversal"):
    return await reverse_payment_receipt(
        session, receipt_id=receipt_id, actor_user_id=admin.id, kind=kind, reason=reason
    )


async def _refund(session, admin, terms, receipt_id, amount, reference):
    return await record_refund_settlement(
        session,
        commercial_terms_id=terms.id,
        receipt_id=receipt_id,
        actor_user_id=admin.id,
        amount=amount,
        settlement_provider="bank",
        external_reference=reference,
        reason="return cancelled campaign cash",
    )


async def _position(session, cancellation_id) -> dict:
    cancellation = await session.get(CampaignCancellation, cancellation_id)
    return await cancellation_refund_position(session, cancellation)


async def _split_funded_cancellation(session, *, admin, owner, organization, campaign, monkeypatch):
    """Terms 100 funded by R1 = 60 and R2 = 40, then cancelled inside the refund window."""
    terms = await _accepted_terms(
        session,
        campaign=campaign,
        admin=admin,
        owner=owner,
        reference=f"SPLIT-{campaign.id.hex[:8]}",
        amount="100.00",
        issued=True,
    )
    now = datetime.now(UTC)
    r1 = await _pay(
        session,
        organization=organization,
        admin=admin,
        terms=terms,
        reference=f"R1-{campaign.id.hex[:8]}",
        amount="60.00",
        observed_at=now,
    )
    r2 = await _pay(
        session,
        organization=organization,
        admin=admin,
        terms=terms,
        reference=f"R2-{campaign.id.hex[:8]}",
        amount="40.00",
        observed_at=now,
    )
    cancellation = await _cancel_for_refund(
        session,
        campaign=campaign,
        admin=admin,
        cutoff=_cutoff(),
        monkeypatch=monkeypatch,
        reason="advertiser asked to cancel",
    )
    assert cancellation.disposition == "cash_refund_due"
    assert cancellation.refundable_amount == Decimal("100.00")
    return terms, r1, r2, cancellation


# --- A6 (a) -------------------------------------------------------------------


def test_a6a_not_received_after_cancellation_leaves_no_refund_due(db_sessionmaker, monkeypatch):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "r325-a")

    async def scenario():
        async with db_sessionmaker() as session:
            terms, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="R325-A",
            )
            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                admin=admin,
                cutoff=_cutoff(),
                monkeypatch=monkeypatch,
                reason="cancel then bounce",
            )
            assert (await _position(session, cancellation.id))["refund_still_due"] == Decimal(
                "100.00"
            )
            await _reverse(session, admin, allocation.receipt_id, NOT_RECEIVED, "transfer bounced")
            # An exact replay is a no-op.
            await _reverse(session, admin, allocation.receipt_id, NOT_RECEIVED, "transfer bounced")
            assert (await session.scalar(select(func.count()).select_from(ReceiptNonReceipt))) == 1
            position = await _position(session, cancellation.id)
            assert position["refund_still_due"] == Decimal("0.00")
            assert position["not_received_counted"] == Decimal("100.00")
            assert position["owed_back"] == Decimal("0.00")
            with pytest.raises(AppError) as refused:
                await _refund(session, admin, terms, allocation.receipt_id, "100.00", "R325-A-RF")
            assert refused.value.code == "REFUND_PAYMENT_NOT_RECEIVED"
            assert refused.value.status_code == 409
            await session.commit()

    asyncio.run(scenario())
    reversed_events = [
        event
        for event in fetch_audit_events(db_sessionmaker)
        if event.action == "billing.receipt.reversed"
    ]
    assert [event.event_metadata["kind"] for event in reversed_events] == ["not_received"]


# --- A6 (b) and the frozen membership snapshot -----------------------------------


def test_a6b_one_of_two_receipts_not_received_keeps_the_other_refundable(
    db_sessionmaker, monkeypatch
):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "r325-b")

    async def scenario():
        async with db_sessionmaker() as session:
            terms, r1, r2, cancellation = await _split_funded_cancellation(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                monkeypatch=monkeypatch,
            )
            revision = await session.scalar(
                select(CampaignCancellationSettlementRevision).where(
                    CampaignCancellationSettlementRevision.cancellation_id == cancellation.id
                )
            )
            assert sorted(
                revision.snapshot["counted_allocations"], key=lambda item: item["amount"]
            ) == [
                {"allocation_id": str(r2.id), "receipt_id": str(r2.receipt_id), "amount": "40.00"},
                {"allocation_id": str(r1.id), "receipt_id": str(r1.receipt_id), "amount": "60.00"},
            ]
            assert revision.snapshot_sha256 == _digest(revision.snapshot)

            await _reverse(session, admin, r1.receipt_id, NOT_RECEIVED, "R1 bounced")
            assert (await _position(session, cancellation.id))["refund_still_due"] == Decimal(
                "40.00"
            )
            await _reverse(session, admin, r2.receipt_id, REFUND)
            with pytest.raises(AppError) as over:
                await _refund(session, admin, terms, r2.receipt_id, "40.01", "R325-B-OVER")
            assert over.value.code == "REFUND_EXCEEDS_CASH_AUTHORITY"
            await _refund(session, admin, terms, r2.receipt_id, "40.00", "R325-B-RF")
            position = await _position(session, cancellation.id)
            assert position["refund_still_due"] == Decimal("0.00")
            assert position["owed_back"] == Decimal("0.00")

    asyncio.run(scenario())


# --- A6 (c) -------------------------------------------------------------------


def test_a6c_refund_then_not_received_becomes_owed_back(db_client, db_sessionmaker, monkeypatch):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "r325-c")

    async def arrange():
        async with db_sessionmaker() as session:
            terms, r1, r2, cancellation = await _split_funded_cancellation(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                monkeypatch=monkeypatch,
            )
            await _reverse(session, admin, r1.receipt_id, REFUND)
            await _refund(session, admin, terms, r1.receipt_id, "60.00", "R325-C-R1")
            position = await _position(session, cancellation.id)
            assert position["refund_still_due"] == Decimal("40.00")
            await session.commit()
            return terms, r1, r2, cancellation

    terms, r1, r2, cancellation = asyncio.run(arrange())
    admin_headers = auth_headers(db_client, admin.email)
    marked = db_client.post(
        f"/api/v1/admin/receipts/{r1.receipt_id}/not-received",
        headers=admin_headers,
        json={"reason": "Chargeback after the refund was paid"},
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["receipt_id"] == str(r1.receipt_id)

    read = db_client.get(
        f"/api/v1/admin/payout-batches/campaigns/{campaign.id}/position", headers=admin_headers
    )
    assert read.status_code == 200, read.text
    closeout = read.json()["cancellation"]
    assert closeout["refundable_amount"] == "100.00"
    assert closeout["owed_back"] == "60.00"
    assert closeout["refund_still_due"] == "40.00"

    async def refund_r2():
        async with db_sessionmaker() as session:
            await _reverse(session, admin, r2.receipt_id, REFUND)
            await _refund(session, admin, terms, r2.receipt_id, "40.00", "R325-C-R2")
            position = await _position(session, cancellation.id)
            assert position == {
                "refundable_amount": Decimal("100.00"),
                "not_received_counted": Decimal("60.00"),
                "refunded_received": Decimal("40.00"),
                "refund_still_due": Decimal("0.00"),
                "owed_back": Decimal("60.00"),
            }
            await session.commit()

    asyncio.run(refund_r2())
    history = db_client.get(
        "/api/v1/advertiser/billing", headers=auth_headers(db_client, owner.email)
    )
    assert history.status_code == 200, history.text
    by_receipt = {row["receipt"]["id"]: row for row in history.json()}
    assert by_receipt[str(r1.receipt_id)]["not_received"] is True
    assert by_receipt[str(r1.receipt_id)]["owed_back_amount"] == "60.00"
    assert by_receipt[str(r2.receipt_id)]["not_received"] is False
    assert by_receipt[str(r2.receipt_id)]["owed_back_amount"] == "0.00"


# --- A6 (d) -------------------------------------------------------------------


def test_a6d_receipt_reversed_before_cancellation_does_not_move_the_authority(
    db_sessionmaker, monkeypatch
):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "r325-d")

    async def scenario():
        async with db_sessionmaker() as session:
            terms, first, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="R325-D",
            )
            await _reverse(session, admin, first.receipt_id, REFUND, "first transfer returned")
            replacement = await _pay(
                session,
                organization=organization,
                admin=admin,
                terms=terms,
                reference="R325-D-2",
                amount="100.00",
                observed_at=datetime.now(UTC),
            )
            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                admin=admin,
                cutoff=_cutoff(),
                monkeypatch=monkeypatch,
                reason="cancel after a replacement payment",
            )
            assert cancellation.refundable_amount == Decimal("100.00")
            await _reverse(session, admin, replacement.receipt_id, NOT_RECEIVED, "bounced")
            before = await _position(session, cancellation.id)
            assert before["refund_still_due"] == Decimal("0.00")
            # Existing caps alone would allow this; the refund still due refuses it.
            with pytest.raises(AppError) as capped:
                await _refund(session, admin, terms, first.receipt_id, "100.00", "R325-D-RF")
            assert capped.value.code == "REFUND_EXCEEDS_REFUND_STILL_DUE"
            await record_receipt_not_received(
                session,
                receipt_id=first.receipt_id,
                actor_user_id=admin.id,
                reason="the pre-cancellation transfer was never received either",
            )
            assert await _position(session, cancellation.id) == before

    asyncio.run(scenario())


# --- A6 (e) and A5 manual allocation ----------------------------------------------


def test_a6e_allocation_after_cancellation_is_not_in_the_frozen_membership(
    db_sessionmaker, monkeypatch
):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "r325-e")

    async def scenario():
        async with db_sessionmaker() as session:
            terms, _, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="R325-E",
            )
            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                admin=admin,
                cutoff=_cutoff(),
                monkeypatch=monkeypatch,
                reason="cancel before a late payment",
            )
            late = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank-transfer",
                external_transaction_id="R325-E-LATE",
                amount="50.00",
                currency="NGN",
                payer_name="Advertiser",
                evidence_reference="R325-E-LATE-EVIDENCE",
                observed_at=datetime.now(UTC),
            )
            await confirm_payment_receipt(
                session,
                receipt_id=late.id,
                actor_user_id=admin.id,
                expected_amount="50.00",
                expected_currency="NGN",
            )
            # A5: manual allocation is refused after a cash-refund-due cancellation.
            with pytest.raises(AppError) as refused:
                await allocate_payment_receipt(
                    session,
                    receipt_id=late.id,
                    commercial_terms_id=terms.id,
                    actor_user_id=admin.id,
                    amount="50.00",
                )
            assert refused.value.code == "CAMPAIGN_CANCELLED_NO_PAYMENT"
            assert refused.value.status_code == 409
            # Any allocation that still lands after the cutoff stays outside the freeze.
            session.add(
                ReceiptAllocation(
                    receipt_id=late.id,
                    commercial_terms_id=terms.id,
                    amount=Decimal("50.00"),
                    currency="NGN",
                    allocated_by_user_id=admin.id,
                    allocation_source="manual",
                    allocated_at=cancellation.cutoff_at + timedelta(minutes=5),
                )
            )
            await session.flush()
            before = await _position(session, cancellation.id)
            await _reverse(session, admin, late.id, NOT_RECEIVED, "late transfer bounced")
            assert await _position(session, cancellation.id) == before
            assert before["refund_still_due"] == Decimal("100.00")

    asyncio.run(scenario())


# --- A6 (f) -------------------------------------------------------------------


def test_a6f_not_received_is_idempotent_and_needs_a_reversed_receipt(db_sessionmaker, monkeypatch):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "r325-f")

    async def scenario():
        async with db_sessionmaker() as session:
            _, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="R325-F",
            )
            receipt_id = allocation.receipt_id
            with pytest.raises(AppError) as confirmed:
                await record_receipt_not_received(
                    session, receipt_id=receipt_id, actor_user_id=admin.id, reason="too early"
                )
            assert confirmed.value.code == "RECEIPT_NOT_REVERSED"
            assert confirmed.value.status_code == 409
            await _reverse(session, admin, receipt_id, REFUND)
            with pytest.raises(AppError) as converted:
                await _reverse(session, admin, receipt_id, NOT_RECEIVED)
            assert converted.value.code == "RECEIPT_ALREADY_REVERSED"
            with pytest.raises(AppError) as blank:
                await record_receipt_not_received(
                    session, receipt_id=receipt_id, actor_user_id=admin.id, reason=" "
                )
            assert blank.value.code == "NOT_RECEIVED_REASON_REQUIRED"
            first = await record_receipt_not_received(
                session, receipt_id=receipt_id, actor_user_id=admin.id, reason="chargeback"
            )
            again = await record_receipt_not_received(
                session, receipt_id=receipt_id, actor_user_id=admin.id, reason="chargeback again"
            )
            assert again.id == first.id and again.reason == "chargeback"
            # Reversal replays stay no-ops once the receipt is marked.
            assert (await _reverse(session, admin, receipt_id, NOT_RECEIVED)).id == receipt_id
            assert (await _reverse(session, admin, receipt_id, REFUND)).id == receipt_id
            assert (await session.scalar(select(func.count()).select_from(ReceiptNonReceipt))) == 1
            await session.commit()

    asyncio.run(scenario())
    actions = [event.action for event in fetch_audit_events(db_sessionmaker)]
    assert actions.count("billing.receipt.not_received") == 1
    assert actions.count("billing.receipt.reversed") == 1


# --- A6 (g) -------------------------------------------------------------------


def test_a6g_not_received_and_a_concurrent_refund_serialize_under_one_cancellation(
    postgis_db_sessionmaker, monkeypatch
):
    maker = postgis_db_sessionmaker
    admin, owner, organization, campaign = _fixture(maker, "r325-g")

    async def arrange():
        async with maker() as session:
            terms, r1, r2, cancellation = await _split_funded_cancellation(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                monkeypatch=monkeypatch,
            )
            await _reverse(session, admin, r1.receipt_id, REFUND)
            await _reverse(session, admin, r2.receipt_id, REFUND)
            await _refund(session, admin, terms, r1.receipt_id, "30.00", "R325-G-R1")
            await session.commit()
            return terms, r1, r2, cancellation

    terms, r1, r2, cancellation = asyncio.run(arrange())

    async def mark_r1():
        async with maker() as session:
            await record_receipt_not_received(
                session, receipt_id=r1.receipt_id, actor_user_id=admin.id, reason="chargeback"
            )
            await session.commit()
            return "marked"

    async def refund_r2():
        async with maker() as session:
            try:
                await _refund(session, admin, terms, r2.receipt_id, "40.00", "R325-G-R2")
                await session.commit()
                return "refunded"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def race():
        async with maker() as blocker:
            await acquire_campaign_terms_lock(blocker, campaign.id)
            tasks = [asyncio.create_task(mark_r1()), asyncio.create_task(refund_r2())]
            await asyncio.sleep(0.5)
            # Both writers hold their own receipt row and wait on the campaign lock.
            assert not any(task.done() for task in tasks)
            await blocker.commit()
            return await asyncio.wait_for(asyncio.gather(*tasks), timeout=15)

    outcomes = asyncio.run(race())
    assert outcomes == ["marked", "refunded"]

    async def inspect():
        async with maker() as session:
            return await _position(session, cancellation.id)

    position = asyncio.run(inspect())
    assert position["refunded_received"] <= (
        position["refundable_amount"] - position["not_received_counted"]
    )
    assert position == {
        "refundable_amount": Decimal("100.00"),
        "not_received_counted": Decimal("60.00"),
        "refunded_received": Decimal("40.00"),
        "refund_still_due": Decimal("0.00"),
        "owed_back": Decimal("30.00"),
    }


# --- A6 (h) -------------------------------------------------------------------


def test_a6h_receipt_non_receipts_are_append_only(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    row = "'32500000-0000-0000-0000-000000000001'"

    async def seed_and_mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO receipt_non_receipts "
                        "(id, receipt_id, reason, actor_user_id, recorded_at) VALUES "
                        f"({row}, '32500000-0000-0000-0000-000000000002', 'bounced', "
                        "'32500000-0000-0000-0000-000000000003', now())"
                    )
                )
            for statement in (
                f"UPDATE receipt_non_receipts SET reason = 'changed' WHERE id = {row}",
                f"DELETE FROM receipt_non_receipts WHERE id = {row}",
            ):
                async with engine.begin() as connection:
                    with pytest.raises(DBAPIError, match="append-only"):
                        await connection.execute(text(statement))
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
    finally:
        asyncio.run(drop_database(migration_url))


# --- A6 (i) -------------------------------------------------------------------


def test_a6i_credit_terms_not_received_is_a_plain_reversal(db_sessionmaker, monkeypatch):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "r325-i")

    async def scenario():
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="R325-I",
                payment_class=PaymentClass.APPROVED_CORPORATE_CREDIT,
                issued=True,
            )
            payment = await _pay(
                session,
                organization=organization,
                admin=admin,
                terms=terms,
                reference="R325-I-PAY",
                amount="100.00",
                observed_at=datetime.now(UTC),
            )
            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                admin=admin,
                cutoff=_cutoff(),
                monkeypatch=monkeypatch,
                reason="cancel a credit campaign",
            )
            assert cancellation.disposition == "credit_settlement_due"
            await _reverse(session, admin, payment.receipt_id, NOT_RECEIVED, "cheque bounced")
            position = await _position(session, cancellation.id)
            assert position["refund_still_due"] == Decimal("0.00")
            assert position["owed_back"] == Decimal("0.00")
            with pytest.raises(AppError) as refund:
                await _refund(session, admin, terms, payment.receipt_id, "100.00", "R325-I-RF")
            assert refund.value.code == "CASH_REFUND_NOT_APPLICABLE"

    asyncio.run(scenario())


# --- A6 (j) -------------------------------------------------------------------


def test_a6j_only_admins_record_and_advertisers_see_their_own_without_actor(
    db_client, db_sessionmaker, monkeypatch
):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "r325-j")
    _, other_owner, _, _ = _fixture(db_sessionmaker, "r325-j-other")

    async def arrange():
        async with db_sessionmaker() as session:
            _, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="R325-J",
            )
            await session.commit()
            return allocation.receipt_id

    receipt_id = asyncio.run(arrange())
    admin_headers = auth_headers(db_client, admin.email)
    owner_headers = auth_headers(db_client, owner.email)
    reverse = f"/api/v1/admin/receipts/{receipt_id}/reverse"
    missing_kind = db_client.post(reverse, headers=admin_headers, json={"reason": "bounced"})
    assert missing_kind.status_code == 422, missing_kind.text
    for path, body in (
        (reverse, {"kind": "not_received", "reason": "bounced"}),
        (f"/api/v1/admin/receipts/{receipt_id}/not-received", {"reason": "bounced"}),
    ):
        denied = db_client.post(path, headers=owner_headers, json=body)
        assert denied.status_code == 403, denied.text
    reversed_ = db_client.post(
        reverse, headers=admin_headers, json={"kind": "not_received", "reason": "Bank returned it"}
    )
    assert reversed_.status_code == 200, reversed_.text

    history = db_client.get("/api/v1/advertiser/billing", headers=owner_headers)
    assert history.status_code == 200, history.text
    [row] = history.json()
    assert row["not_received"] is True
    assert row["not_received_reason"] == "Bank returned it"
    assert row["owed_back_amount"] == "0.00"
    assert "actor" not in history.text and str(admin.id) not in history.text
    foreign = db_client.get(
        "/api/v1/advertiser/billing", headers=auth_headers(db_client, other_owner.email)
    )
    assert foreign.status_code == 200 and str(receipt_id) not in foreign.text


# --- A6 (k) -------------------------------------------------------------------


def test_a6k_owed_back_is_scoped_to_each_cancellation(db_client, db_sessionmaker, monkeypatch):
    admin, owner, organization, campaign_a = _fixture(db_sessionmaker, "r325-k")
    campaign_b = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        name="REQ-325 second campaign",
    )

    async def scenario():
        async with db_sessionmaker() as session:
            terms = {}
            for label, campaign in (("A", campaign_a), ("B", campaign_b)):
                terms[label] = await _accepted_terms(
                    session,
                    campaign=campaign,
                    admin=admin,
                    owner=owner,
                    reference=f"R325-K-{label}",
                    amount="100.00",
                    issued=True,
                )
            receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank-transfer",
                external_transaction_id="R325-K-PAY",
                amount="200.00",
                currency="NGN",
                payer_name="Advertiser",
                evidence_reference="R325-K-EVIDENCE",
                observed_at=datetime.now(UTC),
            )
            await confirm_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                expected_amount="200.00",
                expected_currency="NGN",
            )
            for label in ("A", "B"):
                await allocate_payment_receipt(
                    session,
                    receipt_id=receipt.id,
                    commercial_terms_id=terms[label].id,
                    actor_user_id=admin.id,
                    amount="100.00",
                )
            cancellations = {}
            for label, campaign in (("A", campaign_a), ("B", campaign_b)):
                cancellations[label] = await _cancel_for_refund(
                    session,
                    campaign=campaign,
                    admin=admin,
                    cutoff=_cutoff(),
                    monkeypatch=monkeypatch,
                    reason=f"cancel campaign {label}",
                )
                assert cancellations[label].refundable_amount == Decimal("100.00")
            await _reverse(session, admin, receipt.id, REFUND)
            await _refund(session, admin, terms["A"], receipt.id, "100.00", "R325-K-A")
            await _refund(session, admin, terms["B"], receipt.id, "50.00", "R325-K-B")
            await record_receipt_not_received(
                session, receipt_id=receipt.id, actor_user_id=admin.id, reason="chargeback"
            )
            a = await _position(session, cancellations["A"].id)
            b = await _position(session, cancellations["B"].id)
            assert (a["owed_back"], a["refund_still_due"]) == (Decimal("100.00"), Decimal("0.00"))
            assert (b["owed_back"], b["refund_still_due"]) == (Decimal("50.00"), Decimal("0.00"))
            await session.commit()
            return receipt.id

    receipt_id = asyncio.run(scenario())
    history = db_client.get(
        "/api/v1/advertiser/billing", headers=auth_headers(db_client, owner.email)
    )
    [row] = [item for item in history.json() if item["receipt"]["id"] == str(receipt_id)]
    assert row["owed_back_amount"] == "150.00"


# --- A5 -----------------------------------------------------------------------


def _gateway_payload(terms_id, organization_id, *, event_id: str) -> bytes:
    return json.dumps(
        {
            "provider_event_id": event_id,
            "external_transaction_id": event_id,
            "event_type": "payment_confirmed",
            "commercial_terms_id": str(terms_id),
            "organization_id": str(organization_id),
            "amount": "25.00",
            "currency": "NGN",
            "payer_name": "Gateway Advertiser",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        sort_keys=True,
    ).encode()


def test_a5_cash_refund_due_cancellation_refuses_checkout_and_parks_gateway_cash(
    db_client, db_sessionmaker, monkeypatch
):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "r325-a5")
    fake = FakePaymentGatewayAdapter()

    async def scenario():
        async with db_sessionmaker() as session:
            terms, _, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="R325-A5",
            )
            invoice = await session.scalar(
                select(Invoice).where(Invoice.commercial_terms_id == terms.id)
            )
            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                admin=admin,
                cutoff=_cutoff(),
                monkeypatch=monkeypatch,
                reason="cancel a fully paid campaign",
            )
            # A balance exists, but nothing more can be owed after this cancellation.
            await record_invoice_correction(
                session,
                invoice_id=invoice.id,
                actor_user_id=admin.id,
                correction_reference="r325-a5-debit",
                correction_type=InvoiceCorrectionType.DEBIT_NOTE,
                net_amount="25.00",
                reason="late extra",
            )
            with pytest.raises(AppError) as checkout:
                await prepare_invoice_payment_checkout(
                    session, invoice_id=invoice.id, actor_user_id=owner.id, adapter=PAYSTACK
                )
            assert checkout.value.code == "CAMPAIGN_CANCELLED_NO_PAYMENT"
            assert checkout.value.status_code == 409
            assert await session.scalar(select(func.count(PaymentCheckoutIntent.id))) == 0

            body = _gateway_payload(terms.id, organization.id, event_id="r325-a5-late")
            event, _ = await ingest_payment_gateway_webhook(
                session, adapter=fake, payload=body, signature=fake.sign_webhook(body)
            )
            attempt = await process_payment_gateway_event(session, event_id=event.id)
            assert attempt.outcome == "confirmed_unallocated"
            assert attempt.receipt_id is not None and attempt.allocation_id is None
            assert (
                await session.scalar(
                    select(func.count(ReceiptAllocation.id)).where(
                        ReceiptAllocation.receipt_id == attempt.receipt_id
                    )
                )
                == 0
            )
            assert (await _position(session, cancellation.id))["refund_still_due"] == Decimal(
                "100.00"
            )
            await session.commit()
            return attempt.receipt_id

    receipt_id = asyncio.run(scenario())
    [audit] = [
        event
        for event in fetch_audit_events(db_sessionmaker)
        if event.action == "billing.gateway_payment_after_cancellation.recorded"
    ]
    assert audit.entity_id == str(receipt_id)
    assert audit.event_metadata["unallocated_amount"] == "25.00"
    assert audit.event_metadata["cancellation_disposition"] == "cash_refund_due"
    commercial = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/commercial",
        headers=auth_headers(db_client, owner.email),
    )
    assert commercial.status_code == 200, commercial.text
    assert commercial.json()["accepts_payments"] is False


def test_a5_no_settlement_cancellation_accepts_no_payment(db_client, db_sessionmaker, monkeypatch):
    admin, owner, _organization, campaign = _fixture(db_sessionmaker, "r325-a5-none")

    async def cancel():
        async with db_sessionmaker() as session:
            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                admin=admin,
                cutoff=_cutoff(),
                monkeypatch=monkeypatch,
                reason="cancel before any terms",
            )
            assert cancellation.disposition == "no_settlement"
            await session.commit()

    asyncio.run(cancel())
    commercial = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/commercial",
        headers=auth_headers(db_client, owner.email),
    )
    assert commercial.status_code == 200, commercial.text
    assert commercial.json()["accepts_payments"] is False


# --- A5b ----------------------------------------------------------------------


def test_a5b_cash_refund_not_due_cancellation_stays_payable(
    db_client, db_sessionmaker, monkeypatch
):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "r325-a5b")

    async def scenario():
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="R325-A5B",
                amount="100.00",
                issued=True,
            )
            await _pay(
                session,
                organization=organization,
                admin=admin,
                terms=terms,
                reference="R325-A5B-PART",
                amount="60.00",
                observed_at=datetime.now(UTC),
            )
            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                admin=admin,
                cutoff=_cutoff(),
                monkeypatch=monkeypatch,
                reason="cancel a part-paid campaign",
            )
            assert cancellation.disposition == "cash_refund_not_due"
            invoice = await session.scalar(
                select(Invoice).where(Invoice.commercial_terms_id == terms.id)
            )
            checkout = await prepare_invoice_payment_checkout(
                session, invoice_id=invoice.id, actor_user_id=owner.id, adapter=PAYSTACK
            )
            assert checkout.amount == Decimal("40.00")
            await session.commit()

    asyncio.run(scenario())
    commercial = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/commercial",
        headers=auth_headers(db_client, owner.email),
    )
    assert commercial.status_code == 200, commercial.text
    body = commercial.json()
    assert body["accepts_payments"] is True
    [invoice] = body["invoices"]
    assert (invoice["effective_obligation_amount"], invoice["funded_amount"]) == (
        "100.00",
        "60.00",
    )
    assert invoice["payment_status"] != "paid"


# --- A7 -----------------------------------------------------------------------


def test_a7_cancel_reverse_refund_works_as_before(db_client, db_sessionmaker, monkeypatch):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "r325-a7")

    async def arrange():
        async with db_sessionmaker() as session:
            terms, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="R325-A7",
            )
            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                admin=admin,
                cutoff=_cutoff(),
                monkeypatch=monkeypatch,
                reason="ordinary cancellation",
            )
            await session.commit()
            return terms, allocation.receipt_id, cancellation.id

    terms, receipt_id, cancellation_id = asyncio.run(arrange())
    headers = auth_headers(db_client, admin.email)
    reversed_ = db_client.post(
        f"/api/v1/admin/receipts/{receipt_id}/reverse",
        headers=headers,
        json={"kind": "refund", "reason": "return the payment"},
    )
    assert reversed_.status_code == 200, reversed_.text
    refund = db_client.post(
        "/api/v1/admin/refunds",
        headers=headers,
        json={
            "commercial_terms_id": str(terms.id),
            "receipt_id": str(receipt_id),
            "amount": "100.00",
            "settlement_provider": "bank",
            "external_reference": "R325-A7-RF",
            "reason": "returned in full",
        },
    )
    assert refund.status_code == 200, refund.text
    assert refund.json()["cancellation_id"] == str(cancellation_id)

    async def inspect():
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(ReceiptNonReceipt)) == 0
            receipt = await session.get(PaymentReceipt, receipt_id)
            assert receipt is not None
            return await _position(session, cancellation_id)

    position = asyncio.run(inspect())
    assert (position["refund_still_due"], position["owed_back"]) == (
        Decimal("0.00"),
        Decimal("0.00"),
    )

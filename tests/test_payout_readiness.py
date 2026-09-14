import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from conftest import create_test_frozen_payout_binding
from sqlalchemy import event, func, select
from test_financial_authority import _funded_terms
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority

from app.models.audit import AuditEvent
from app.models.billing import CampaignLiabilityReservation
from app.services import billing
from app.services.payout_operations import campaign_money_position, preview_payment_selection


def test_phase_one_public_recovery_inventory_keeps_admin_initiation_protected():
    from authorization_matrix import Principal, authorization_inventory

    inventory = {row.key: row.principal for row in authorization_inventory()}
    assert inventory[("POST", "/api/v1/auth/driver-onboarding-access/request")] == Principal.PUBLIC
    assert inventory[("POST", "/api/v1/auth/driver-account-setup/complete")] == Principal.PUBLIC
    initiation = [
        row
        for row in authorization_inventory()
        if "account-setup" in row.path and row.path.startswith("/api/v1/admin/")
    ]
    assert initiation and all(row.principal == Principal.ADMIN for row in initiation)


def _freeze_window(sessions, graph):
    graph.campaign.start_at = datetime.now(UTC)
    graph.campaign.end_at = graph.campaign.start_at + timedelta(days=2)

    async def update_window():
        async with sessions() as session:
            await session.merge(graph.campaign)
            await session.commit()

    asyncio.run(update_window())
    create_test_frozen_payout_binding(
        sessions, campaign=graph.campaign, assignment=graph.assignment, admin=graph.admin
    )


@pytest.mark.parametrize("fixture_name", ["db_sessionmaker", "postgis_db_sessionmaker"])
def test_funded_readiness_matches_new_reservation_without_writes(
    request, fixture_name, monkeypatch
):
    sessions = request.getfixturevalue(fixture_name)
    graph = build_graph(sessions, f"liability-ready-{uuid4().hex[:8]}")
    _freeze_window(sessions, graph)

    async def exercise():
        async with sessions() as session:
            _, allocation, _ = await _funded_terms(
                session,
                admin=graph.admin,
                owner=graph.advertiser,
                organization=graph.organization,
                campaign=graph.campaign,
                reference=f"readiness-{uuid4().hex[:8]}",
            )

            async def clock(_session):
                return allocation.allocated_at + timedelta(hours=24)

            monkeypatch.setattr(billing, "database_clock", clock)
            await billing.record_production_start(
                session, campaign_id=graph.campaign.id, actor_user_id=graph.admin.id
            )
            await session.commit()
            audits = await session.scalar(select(func.count(AuditEvent.id)))

            def reject_writes(_connection, _cursor, statement, _parameters, _context, _many):
                assert statement.lstrip().split()[0].upper() not in {
                    "INSERT",
                    "UPDATE",
                    "DELETE",
                    "MERGE",
                }, "Readiness must not write business or audit state"

            engine = sessions.kw["bind"].sync_engine
            event.listen(engine, "before_cursor_execute", reject_writes)
            try:
                readiness = await billing.assignment_liability_readiness(
                    session, assignment_id=graph.assignment.id
                )
            finally:
                event.remove(engine, "before_cursor_execute", reject_writes)
            assert readiness.eligible is True
            assert readiness.existing_reservation_id is None
            assert readiness.reason is None
            assert await session.scalar(select(func.count(CampaignLiabilityReservation.id))) == 0
            assert await session.scalar(select(func.count(AuditEvent.id))) == audits
            reservation = await billing.reserve_assignment_liability(
                session, assignment_id=graph.assignment.id, actor_user_id=graph.admin.id
            )
            assert reservation.status == "reserved"
            existing = await billing.assignment_liability_readiness(
                session, assignment_id=graph.assignment.id
            )
            assert existing.eligible is True
            assert existing.existing_reservation_id == reservation.id
            await billing.assert_new_work_authorized(
                session, campaign_id=graph.campaign.id, assignment_id=graph.assignment.id
            )

    asyncio.run(exercise())


@pytest.mark.parametrize("fixture_name", ["db_sessionmaker", "postgis_db_sessionmaker"])
def test_unfunded_readiness_and_exact_selection_preview_fail_closed(request, fixture_name):
    sessions = request.getfixturevalue(fixture_name)
    graph = build_graph(sessions, f"unfunded-ready-{uuid4().hex[:8]}")
    _freeze_window(sessions, graph)

    async def exercise():
        async with sessions() as session:
            readiness = await billing.assignment_liability_readiness(
                session, assignment_id=graph.assignment.id
            )
            assert readiness.eligible is False
            assert "funding" in readiness.reason
            assert await session.scalar(select(func.count(CampaignLiabilityReservation.id))) == 0
            entry = await _seed_authority(session, graph, amount="100.07")
            await session.commit()
            audits = await session.scalar(select(func.count(AuditEvent.id)))
            preview = await preview_payment_selection(
                session, currency="NGN", ledger_entry_ids=(entry.id,)
            )
            assert preview["total_amount"] == Decimal("100.07")
            assert await session.scalar(select(func.count(AuditEvent.id))) == audits
            position = await campaign_money_position(session, campaign_id=graph.campaign.id)
            assert position["items"][0]["unbatched_available"] == Decimal("100.07")
            assert position["items"][0]["cash_paid"] == Decimal("0.00")
            assert position["cancellation"] is None
            assert position["external_blockers"]
            from app.core.errors import AppError

            for ids, currency in [
                ((entry.id,), "USD"),
                ((uuid4(),), "NGN"),
                ((entry.id, entry.id), "NGN"),
            ]:
                with pytest.raises(AppError):
                    await preview_payment_selection(
                        session, currency=currency, ledger_entry_ids=ids
                    )

    asyncio.run(exercise())

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from conftest import auth_headers
from sqlalchemy import select
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority

from app.models.disbursement import PayoutAutomaticAlert
from app.models.user import User
from app.services.automatic_payouts import list_automatic_payout_alerts
from app.services.disbursements import create_payout_batch_draft, reserve_payout_batch


def test_sparse_blocked_alerts_identify_actual_payment_without_changing_records(
    db_client, db_sessionmaker
):
    db = db_sessionmaker
    graphs = [build_graph(db, f"alert-context-{uuid4().hex[:8]}") for _ in range(2)]

    async def exercise():
        async with db() as session:
            expected = []
            for index, graph in enumerate(graphs):
                driver = await session.get(User, graph.driver.id)
                driver.full_name = f"Context driver {index + 1}"
                graph.driver.full_name = driver.full_name
                entry = await _seed_authority(session, graph, amount=f"{125 + index}.07")
                batch = await create_payout_batch_draft(
                    session, currency="NGN", actor_user_id=graph.admin.id, reason="Context test"
                )
                _, lines = await reserve_payout_batch(
                    session,
                    batch_id=batch.id,
                    ledger_entry_ids=(entry.id,),
                    actor_user_id=graph.admin.id,
                    reason="Context test",
                )
                alert = PayoutAutomaticAlert(
                    kind="submission_blocked",
                    dedupe_key=uuid4().hex,
                    detail={},
                    line_id=lines[0].id,
                    created_at=datetime(2026, 11, 2, tzinfo=UTC) + timedelta(minutes=index),
                )
                session.add(alert)
                await session.flush()
                expected.append(
                    (alert.id, graph.driver.full_name, entry.amount, batch.id, lines[0].id)
                )
            # Recorded context takes precedence, including an explicit zero amount.
            recorded = PayoutAutomaticAlert(
                kind="submission_blocked",
                dedupe_key=uuid4().hex,
                detail={},
                line_id=expected[0][4],
                driver_profile_id=graphs[1].profile.id,
                amount=Decimal("0.00"),
                currency="USD",
                batch_id=expected[1][3],
            )
            missing = PayoutAutomaticAlert(
                kind="submission_blocked", dedupe_key=uuid4().hex, detail={}
            )
            unrelated = PayoutAutomaticAlert(
                kind="business_health",
                dedupe_key=uuid4().hex,
                detail={},
                line_id=expected[0][4],
            )
            session.add_all([recorded, missing, unrelated])
            await session.commit()
            return expected, recorded.id, missing.id, unrelated.id

    expected, recorded_id, missing_id, unrelated_id = asyncio.run(exercise())

    async def read():
        async with db() as session:
            before = (await session.execute(select(PayoutAutomaticAlert.__table__))).all()
            for alert_id, driver, amount, batch_id, line_id in expected:
                result = await list_automatic_payout_alerts(
                    session, alert_status="open", alert_id=alert_id
                )
                assert result["total"] == 1
                row = result["items"][0]
                assert (
                    row["driver_name"],
                    row["amount"],
                    row["currency"],
                    row["batch_id"],
                    row["line_id"],
                ) == (driver, amount, "NGN", batch_id, line_id)
            result = await list_automatic_payout_alerts(
                session, alert_status="open", alert_id=recorded_id
            )
            row = result["items"][0]
            assert (row["driver_name"], row["amount"], row["currency"], row["batch_id"]) == (
                graphs[1].driver.full_name,
                Decimal("0.00"),
                "USD",
                expected[1][3],
            )
            for alert_id in (missing_id, unrelated_id):
                row = (
                    await list_automatic_payout_alerts(
                        session, alert_status="open", alert_id=alert_id
                    )
                )["items"][0]
                assert all(
                    row[key] is None for key in ("driver_name", "amount", "currency", "batch_id")
                )
            full = await list_automatic_payout_alerts(
                session, alert_status="open", oldest_first=True
            )
            assert full["total"] == 5
            assert [row["id"] for row in full["items"][:2]] == [item[0] for item in expected]
            page = await list_automatic_payout_alerts(
                session, alert_status="open", oldest_first=True, limit=1, offset=1
            )
            assert page["total"] == 5 and page["items"] == [full["items"][1]]
            resolved = await list_automatic_payout_alerts(session, alert_status="resolved")
            assert resolved["total"] == 0 and resolved["items"] == []
            await session.flush()
            assert (await session.execute(select(PayoutAutomaticAlert.__table__))).all() == before

    asyncio.run(read())
    response = db_client.get(
        "/api/v1/admin/payouts/automatic/alerts?oldest_first=true&limit=1",
        headers=auth_headers(db_client, graphs[0].admin.email),
    )
    assert response.status_code == 200, response.text
    row = response.json()["items"][0]
    assert row["amount"] == "125.07" and row["driver_name"] == graphs[0].driver.full_name
    assert row["batch_id"] == str(expected[0][3])
    assert "account_number" not in response.text and "0123456789" not in response.text
    for graph in graphs:
        response = db_client.get(
            "/api/v1/admin/payouts/automatic/alerts",
            headers=auth_headers(db_client, graph.driver.email),
        )
        assert response.status_code == 403


def test_finance_demo_alert_references_its_actual_reserved_payment(
    db_sessionmaker, settings, monkeypatch
):
    from app.models.disbursement import PayoutBatchLine
    from app.seeds import rich

    graph = build_graph(db_sessionmaker, f"seed-alert-{uuid4().hex[:8]}")
    graph.rich = SimpleNamespace(
        drivers=[SimpleNamespace(profile=graph.profile)], campaigns=[graph.campaign]
    )

    async def prepared(_session, entries, _settings):
        return entries

    async def unrelated(*args, **kwargs):
        return None

    monkeypatch.setattr(rich, "_prepare_portal_earnings", prepared)
    monkeypatch.setattr(rich, "_ensure_payout_review_history", unrelated)

    async def exercise():
        async with db_sessionmaker() as session:
            for _ in range(3):
                await _seed_authority(session, graph, amount="100.07")
            await rich.ensure_portal_payouts(
                session, graph=graph, staff=[graph.admin] * 5, settings=settings
            )
            alert = await session.scalar(select(PayoutAutomaticAlert))
            assert alert.line_id is not None
            line = await session.get(PayoutBatchLine, alert.line_id)
            assert line.reservation_active
            assert (alert.batch_id, alert.ledger_entry_id, alert.amount, alert.currency) == (
                line.batch_id,
                line.ledger_entry_id,
                line.amount,
                line.currency,
            )
            await rich.ensure_portal_payouts(
                session, graph=graph, staff=[graph.admin] * 5, settings=settings
            )
            result = await list_automatic_payout_alerts(session, alert_status="open")
            assert result["total"] == 1
            assert result["items"][0]["amount"] == Decimal("100.07")

    asyncio.run(exercise())

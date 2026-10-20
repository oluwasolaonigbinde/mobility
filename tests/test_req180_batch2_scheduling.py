import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from conftest import auth_headers, create_test_campaign
from sqlalchemy import func, select
from test_advertiser_reports import PASSWORD
from test_measurement_runs import create_measurement_graph
from test_report_issuances import ReportStorage

from app.core.errors import AppError
from app.core.security import create_access_token, hash_password
from app.models.campaign import Campaign, CampaignStatus
from app.models.measurement import MeasurementRun
from app.models.report_issuance import ReportIssuance
from app.models.report_schedule import ReportSchedule
from app.models.user import User
from app.services import report_scheduling
from app.services.admin_authorization import require_active_admin
from app.services.report_authorization import REPORT_ACTOR_ID
from app.services.report_issuances import sweep_report_issuances
from app.services.report_scheduling import (
    WEEK,
    discover_report_obligations,
    next_due_window,
    sweep_scheduled_reports,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "days,now_days,known,expected",
    [
        (14, 6, [], None),
        (14, 7, [], (7, "weekly")),
        (14, 14, [7], (14, "final")),
        (16, 16, [7], (14, "weekly")),
        (16, 16, [7, 14], (16, "final")),
        (16, 20, [7, 14, 16], None),
        (0, 20, [], None),
    ],
)
def test_weekly_and_end_boundaries(days, now_days, known, expected):
    result = next_due_window(
        START,
        START + timedelta(days=days),
        START + timedelta(days=now_days),
        {START + timedelta(days=value) for value in known},
    )
    assert result == ((START + timedelta(days=expected[0]), expected[1]) if expected else None)


def install_report_actor(maker):
    async def install():
        async with maker() as session:
            session.add(
                User(
                    id=REPORT_ACTOR_ID,
                    email="report-automation@cardvert.invalid",
                    full_name="Cardvert report automation",
                    password_hash="!report-automation-disabled",
                    role="admin",
                    status="disabled",
                )
            )
            await session.commit()

    asyncio.run(install())


def test_automatic_catchup_failure_retry_publication_and_manual_rerun(
    db_client,
    db_sessionmaker,
    settings,
    monkeypatch,
):
    admin, advertiser, campaign = create_measurement_graph(db_sessionmaker)
    install_report_actor(db_sessionmaker)
    ctx = {"settings": settings, "sessionmaker": db_sessionmaker}
    real_prepare = report_scheduling.prepare_report
    failed_once = False

    async def fail_after_run(*args, **kwargs):
        nonlocal failed_once
        result = await real_prepare(*args, **kwargs)
        if not failed_once:
            failed_once = True
            raise AppError(
                "SYNTHETIC_REPORT_RETRY",
                "Synthetic failure after both pipeline stages",
                status_code=409,
            )
        return result

    monkeypatch.setattr(report_scheduling, "prepare_report", fail_after_run)

    async def exercise():
        assert (await sweep_scheduled_reports(ctx))["failed"] == 1
        async with db_sessionmaker() as session:
            obligation = await session.scalar(select(ReportSchedule))
            stable_ids = obligation.measurement_request_id, obligation.issuance_request_id
            assert obligation.state == "error" and obligation.error_code == "SYNTHETIC_REPORT_RETRY"
            assert await session.scalar(select(func.count()).select_from(MeasurementRun)) == 0
            assert await session.scalar(select(func.count()).select_from(ReportIssuance)) == 0
            obligation.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
        # Discovery adds the final obligation while the oldest failed weekly one retries.
        result = await sweep_scheduled_reports(ctx)
        assert result["queued"] == 2 and result["failed"] == 0
        assert (await sweep_scheduled_reports(ctx))["queued"] == 0
        async with db_sessionmaker() as session:
            obligations = list(
                await session.scalars(select(ReportSchedule).order_by(ReportSchedule.period_end_at))
            )
            assert [row.kind for row in obligations] == ["weekly", "final"]
            assert all(row.state == "complete" for row in obligations)
            assert (
                obligations[0].measurement_request_id,
                obligations[0].issuance_request_id,
            ) == stable_ids
            assert obligations[0].period_end_at == campaign.start_at + WEEK
            assert obligations[1].period_end_at == campaign.end_at
            assert await session.scalar(select(func.count()).select_from(MeasurementRun)) == 2
            actor = await session.get(User, REPORT_ACTOR_ID)
            assert actor.status == "disabled"
            with pytest.raises(AppError):
                await require_active_admin(session, REPORT_ACTOR_ID)
        storage = ReportStorage()
        assert await sweep_report_issuances({**ctx, "storage": storage}) == 2
        async with db_sessionmaker() as session:
            issuances = list(await session.scalars(select(ReportIssuance)))
            assert all(row.status == "ready" for row in issuances)
            assert all(row.requested_by_user_id == REPORT_ACTOR_ID for row in issuances)
            assert all(
                row.snapshot["creation_authority"] == "report_automation" for row in issuances
            )
            assert len(storage.contents) == 4

    asyncio.run(exercise())
    path = f"/api/v1/admin/campaigns/{campaign.id}/reports/re-run"
    assert (
        db_client.post(
            path, headers=auth_headers(db_client, advertiser.email, PASSWORD)
        ).status_code
        == 403
    )
    first = db_client.post(path, headers=auth_headers(db_client, admin.email, PASSWORD))
    second = db_client.post(path, headers=auth_headers(db_client, admin.email, PASSWORD))
    assert first.status_code == second.status_code == 202, (first.text, second.text)
    assert UUID(first.json()["id"]) != UUID(second.json()["id"])
    login = db_client.post(
        "/api/v1/auth/login",
        json={
            "email": "report-automation@cardvert.invalid",
            "password": "!report-automation-disabled",
        },
    )
    assert login.status_code in {401, 403}


def test_report_actor_is_protected_and_publication_rechecks_exact_identity(
    db_client,
    db_sessionmaker,
    settings,
):
    admin, _, campaign = create_measurement_graph(db_sessionmaker)
    install_report_actor(db_sessionmaker)
    token, _ = create_access_token(REPORT_ACTOR_ID, settings, session_version=1)
    headers = {"Authorization": f"Bearer {token}"}
    for method, path, payload in [
        ("GET", "/api/v1/admin/users", None),
        (
            "POST",
            f"/api/v1/admin/campaigns/{campaign.id}/budget-policy-resume",
            {"reason": "Forbidden automation"},
        ),
    ]:
        response = db_client.request(method, path, headers=headers, json=payload)
        assert response.status_code == 403
    human_headers = auth_headers(db_client, admin.email, PASSWORD)
    assert (
        db_client.get(
            "/api/v1/admin/users", params={"q": "report-automation"}, headers=human_headers
        ).json()["total"]
        == 0
    )
    edit = db_client.patch(
        f"/api/v1/admin/users/{REPORT_ACTOR_ID}", headers=human_headers, json={"status": "active"}
    )
    assert edit.status_code == 409 and edit.json()["error"]["code"] == "SYSTEM_ACCOUNT_READ_ONLY"

    async def exercise():
        ctx = {"sessionmaker": db_sessionmaker, "settings": settings}
        assert (await sweep_scheduled_reports(ctx))["queued"] == 1
        async with db_sessionmaker() as session:
            actor = await session.get(User, REPORT_ACTOR_ID)
            actor.status = "active"  # Simulate a direct database integrity violation.
            actor.password_hash = hash_password("Synthetic report actor password")
            await session.commit()
        storage = ReportStorage()
        assert await sweep_report_issuances({**ctx, "storage": storage}) == 1
        assert storage.contents == {}
        async with db_sessionmaker() as session:
            issuance = await session.scalar(select(ReportIssuance))
            assert issuance.status != "ready"
            assert issuance.last_error_code == "REPORT_ISSUANCE_NOT_FOUND"

    asyncio.run(exercise())
    login = db_client.post(
        "/api/v1/auth/login",
        json={
            "email": "report-automation@cardvert.invalid",
            "password": "Synthetic report actor password",
        },
    )
    assert login.status_code == 401


def test_bounded_discovery_visits_all_campaigns_and_honours_cancellation_cutoff(
    db_sessionmaker,
    monkeypatch,
):
    admin, advertiser, first = create_measurement_graph(db_sessionmaker)
    campaigns = [first]
    for index in range(2):
        campaigns.append(
            create_test_campaign(
                db_sessionmaker,
                organization_id=first.organization_id,
                created_by_user_id=advertiser.id,
                campaign_status=CampaignStatus.ACTIVE,
                name=f"Fair reporting {index}",
                start_at=START,
                end_at=START + timedelta(days=16),
            )
        )

    async def fixed_clock(_session):
        return START + timedelta(days=20)

    monkeypatch.setattr(report_scheduling, "database_clock", fixed_clock)

    async def exercise():
        from app.schemas.campaign_cancellations import CampaignCancellationCreate
        from app.services import campaign_cancellations

        async with db_sessionmaker() as session:
            campaign = await session.get(Campaign, first.id)
            campaign.start_at, campaign.end_at = START, START + timedelta(days=16)
            await session.commit()

        async def cancellation_clock(_session):
            return START + timedelta(days=10)

        monkeypatch.setattr(campaign_cancellations, "database_clock", cancellation_clock)
        async with db_sessionmaker() as session:
            await campaign_cancellations.request_campaign_cancellation(
                session,
                actor_user_id=admin.id,
                actor_session_version=admin.session_version,
                campaign_id=campaigns[-1].id,
                payload=CampaignCancellationCreate(
                    reason="Synthetic reporting cutoff", client_request_id=UUID(int=123)
                ),
            )
            await session.commit()
        # New sessions exercise the durable cursor rather than an in-memory iterator.
        for _ in range(3):
            async with db_sessionmaker() as session:
                assert await discover_report_obligations(session, limit=1) == 1
                await session.commit()
        async with db_sessionmaker() as session:
            first_pass = list(await session.scalars(select(ReportSchedule)))
            assert {row.campaign_id for row in first_pass} == {row.id for row in campaigns}
            assert all(row.period_end_at == START + WEEK for row in first_pass)
        for _ in range(6):
            async with db_sessionmaker() as session:
                await discover_report_obligations(session, limit=1)
                await session.commit()
        async with db_sessionmaker() as session:
            rows = list(await session.scalars(select(ReportSchedule)))
            for campaign in campaigns:
                periods = sorted(
                    (row.period_end_at, row.kind) for row in rows if row.campaign_id == campaign.id
                )
                assert periods == (
                    [(START + WEEK, "weekly"), (START + timedelta(days=10), "final")]
                    if campaign.id == campaigns[-1].id
                    else [
                        (START + WEEK, "weekly"),
                        (START + WEEK * 2, "weekly"),
                        (START + timedelta(days=16), "final"),
                    ]
                )

    asyncio.run(exercise())


def test_overlapping_sweeps_prepare_one_obligation_once(
    db_sessionmaker,
    settings,
    monkeypatch,
):
    _, _, campaign = create_measurement_graph(db_sessionmaker)
    install_report_actor(db_sessionmaker)
    original = report_scheduling.prepare_report

    async def exercise():
        async with db_sessionmaker() as session:
            current = await session.get(Campaign, campaign.id)
            current.end_at = current.start_at + WEEK
            await session.commit()
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def held_prepare(*args, **kwargs):
            nonlocal calls
            calls += 1
            entered.set()
            await asyncio.wait_for(release.wait(), timeout=10)
            return await original(*args, **kwargs)

        monkeypatch.setattr(report_scheduling, "prepare_report", held_prepare)
        context = {"settings": settings, "sessionmaker": db_sessionmaker}
        first = asyncio.create_task(sweep_scheduled_reports(context))
        try:
            await asyncio.wait_for(entered.wait(), timeout=10)
            second = await asyncio.wait_for(sweep_scheduled_reports(context), timeout=10)
            assert second["queued"] == 0 and second["failed"] == 0
        finally:
            release.set()
            completed = await asyncio.wait_for(first, timeout=20)
        assert completed["queued"] == 1 and calls == 1
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(ReportSchedule)) == 1
            assert await session.scalar(select(func.count()).select_from(MeasurementRun)) == 1
            assert await session.scalar(select(func.count()).select_from(ReportIssuance)) == 1

    asyncio.run(exercise())

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from test_complaints import body, build_graph, headers
from test_req180_batch2_cancellation_support import economic_snapshot

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.campaign import Campaign
from app.models.campaign_cancellation import CampaignCancellation
from app.models.complaint import Complaint, ComplaintMessage
from app.models.notification import Notification
from app.models.user import User
from app.schemas.campaign_cancellations import CampaignCancellationCreate
from app.services import campaign_cancellations, complaints


def graph_and_request(client, maker, settings, *, category="campaign_cancellation"):
    graph = build_graph(maker)

    async def make_active():
        async with maker() as session:
            (await session.get(Campaign, graph.campaign.id)).status = "active"
            await session.commit()

    asyncio.run(make_active())
    response = client.post(
        "/api/v1/advertiser/complaints",
        headers=headers(graph.advertiser, settings),
        json=body(category, reference_type="campaign", reference_id=str(graph.campaign.id)),
    )
    assert response.status_code == 200, response.text
    return graph, UUID(response.json()["id"])


def cancel_path(graph):
    return f"/api/v1/admin/campaigns/{graph.campaign.id}/cancel"


def cancel_body(complaint_id=None):
    return {
        "reason": "  Staff accepted the cancellation request.  ",
        "client_request_id": str(uuid4()),
        "complaint_id": str(complaint_id) if complaint_id else None,
    }


async def invoke(session, graph, payload):
    result = await campaign_cancellations.request_campaign_cancellation(
        session,
        actor_user_id=graph.admin.id,
        actor_session_version=graph.admin.session_version,
        campaign_id=graph.campaign.id,
        complaint_id=UUID(payload["complaint_id"]) if payload.get("complaint_id") else None,
        payload=CampaignCancellationCreate.model_validate(
            {key: payload[key] for key in ("reason", "client_request_id")}
        ),
    )
    await session.commit()
    return result


def test_staff_cancel_replays_before_mutable_thread_checks_and_records_actor(
    db_client,
    db_sessionmaker,
    settings,
):
    graph, complaint_id = graph_and_request(db_client, db_sessionmaker, settings)
    payload = cancel_body(complaint_id)
    # Ordinary replies already use this actor/request UUID namespace.
    prior = db_client.post(
        f"/api/v1/admin/complaints/{complaint_id}/messages",
        headers=headers(graph.admin, settings),
        json={
            "message": "We are reviewing your request.",
            "client_request_id": payload["client_request_id"],
        },
    )
    assert prior.status_code == 200, prior.text
    response = db_client.post(
        cancel_path(graph), headers=headers(graph.admin, settings), json=payload
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["requested_by_user_id"] == str(graph.admin.id)
    assert result["reason"] == payload["reason"].strip()
    assert result["disposition"] == "no_settlement"
    detail = db_client.get(
        f"/api/v1/advertiser/complaints/{complaint_id}", headers=headers(graph.advertiser, settings)
    ).json()
    assert detail["messages"][-1]["body"] == "The campaign has been cancelled."
    assert detail["status"] == "answered"

    async def make_full():
        async with db_sessionmaker() as session:
            complaint = await session.get(Complaint, complaint_id)
            complaint.status = "resolved"
            complaint.resolved_at = datetime.now(UTC)
            complaint.resolved_by_user_id = graph.admin.id
            for _ in range(97):
                session.add(
                    ComplaintMessage(
                        complaint_id=complaint_id,
                        author_user_id=graph.admin.id,
                        author_side="staff",
                        body="Synthetic history",
                        status_after="answered",
                        client_request_id=uuid4(),
                    )
                )
            await session.commit()

    asyncio.run(make_full())
    replay = db_client.post(
        cancel_path(graph), headers=headers(graph.admin, settings), json=payload
    )
    assert replay.status_code == 201 and replay.json() == result
    for change in (
        {"reason": "Changed reason"},
        {"complaint_id": None},
        {"complaint_id": str(uuid4())},
        {"client_request_id": str(uuid4())},
    ):
        changed = db_client.post(
            cancel_path(graph), headers=headers(graph.admin, settings), json={**payload, **change}
        )
        assert (
            changed.status_code == 409
            and changed.json()["error"]["code"] == "CAMPAIGN_CANCELLATION_CONFLICT"
        )
    assert (
        db_client.post(
            cancel_path(graph), headers=headers(graph.admin2, settings), json=payload
        ).status_code
        == 409
    )

    async def inspect():
        async with db_sessionmaker() as session:
            assert (await session.get(Campaign, graph.campaign.id)).status == "cancelled"
            assert await session.scalar(select(func.count()).select_from(CampaignCancellation)) == 1
            assert await session.scalar(select(func.count()).select_from(ComplaintMessage)) == 100
            audit = (
                await session.scalars(
                    select(AuditEvent).where(AuditEvent.action == "admin.campaign.cancelled")
                )
            ).one()
            assert audit.actor_user_id == graph.admin.id

    asyncio.run(inspect())


def test_staff_cancel_requires_active_admin_and_valid_same_campaign_request(
    db_client,
    db_sessionmaker,
    settings,
):
    graph, wrong_category = graph_and_request(
        db_client, db_sessionmaker, settings, category="other"
    )
    before = economic_snapshot(db_sessionmaker)
    for user in (graph.advertiser, graph.viewer, graph.driver):
        assert (
            db_client.post(
                cancel_path(graph), headers=headers(user, settings), json=cancel_body()
            ).status_code
            == 403
        )
    assert db_client.post(cancel_path(graph), json=cancel_body()).status_code == 401
    for reason in (" ", "x" * 1001, "invalid\x00reason"):
        assert (
            db_client.post(
                cancel_path(graph),
                headers=headers(graph.admin, settings),
                json={**cancel_body(), "reason": reason},
            ).status_code
            == 422
        )
    for complaint_id in (wrong_category, uuid4()):
        response = db_client.post(
            cancel_path(graph),
            headers=headers(graph.admin, settings),
            json=cancel_body(complaint_id),
        )
        assert (
            response.status_code == 404
            and response.json()["error"]["code"] == "CAMPAIGN_CANCELLATION_REQUEST_NOT_FOUND"
        )
    other = db_client.post(
        "/api/v1/advertiser/complaints",
        headers=headers(graph.other_advertiser, settings),
        json=body(
            "campaign_cancellation",
            reference_type="campaign",
            reference_id=str(graph.other_campaign.id),
        ),
    )
    assert other.status_code == 200
    foreign = db_client.post(
        cancel_path(graph),
        headers=headers(graph.admin, settings),
        json=cancel_body(UUID(other.json()["id"])),
    )
    assert foreign.status_code == 404
    same_org_other_campaign = db_client.post(
        "/api/v1/advertiser/complaints",
        headers=headers(graph.advertiser, settings),
        json=body(
            "campaign_cancellation",
            reference_type="campaign",
            reference_id=str(graph.declined_campaign.id),
        ),
    )
    assert same_org_other_campaign.status_code == 200
    mismatched = db_client.post(
        cancel_path(graph),
        headers=headers(graph.admin, settings),
        json=cancel_body(UUID(same_org_other_campaign.json()["id"])),
    )
    assert mismatched.status_code == 404
    missing = db_client.post(
        f"/api/v1/admin/campaigns/{uuid4()}/cancel",
        headers=headers(graph.admin, settings),
        json=cancel_body(),
    )
    assert missing.status_code == 404
    assert economic_snapshot(db_sessionmaker) == before
    unlinked_payload = cancel_body()
    unlinked = db_client.post(
        cancel_path(graph), headers=headers(graph.admin, settings), json=unlinked_payload
    )
    assert unlinked.status_code == 201, unlinked.text
    without_link = {key: value for key, value in unlinked_payload.items() if key != "complaint_id"}
    replay = db_client.post(
        cancel_path(graph), headers=headers(graph.admin, settings), json=without_link
    )
    assert replay.status_code == 201 and replay.json()["id"] == unlinked.json()["id"]
    thread = db_client.get(
        f"/api/v1/admin/complaints/{wrong_category}", headers=headers(graph.admin, settings)
    ).json()
    assert len(thread["messages"]) == 1


@pytest.mark.parametrize("failure", ["reply", "notification"])
def test_linked_staff_cancel_rolls_back_all_economics_on_reply_failure(
    db_client,
    db_sessionmaker,
    settings,
    monkeypatch,
    failure,
):
    graph, complaint_id = graph_and_request(db_client, db_sessionmaker, settings)
    before = economic_snapshot(db_sessionmaker)

    async def fail(*args, **kwargs):
        raise AppError("SYNTHETIC_REPLY_FAILED", "Synthetic failure", status_code=409)

    monkeypatch.setattr(
        complaints, "reply_as_staff" if failure == "reply" else "_notify_complainant", fail
    )
    response = db_client.post(
        cancel_path(graph), headers=headers(graph.admin, settings), json=cancel_body(complaint_id)
    )
    assert response.status_code == 409
    assert economic_snapshot(db_sessionmaker) == before

    async def inspect():
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(ComplaintMessage)) == 1
            assert await session.scalar(select(func.count()).select_from(Notification)) == 2
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "admin.campaign.cancelled")
                )
                == 0
            )

    asyncio.run(inspect())


@pytest.mark.parametrize("ordinary_first", [True, False])
def test_staff_cancel_and_ordinary_same_actor_reply_do_not_deadlock(
    db_client,
    db_sessionmaker,
    settings,
    monkeypatch,
    ordinary_first,
):
    graph, complaint_id = graph_and_request(db_client, db_sessionmaker, settings)
    payload = cancel_body(complaint_id)

    async def exercise():
        reached, release = asyncio.Event(), asyncio.Event()
        original = campaign_cancellations._validate_cancellation_complaint

        async def observe(*args, **kwargs):
            if ordinary_first:
                reached.set()
                return await original(*args, **kwargs)
            await original(*args, **kwargs)
            reached.set()
            await release.wait()

        monkeypatch.setattr(campaign_cancellations, "_validate_cancellation_complaint", observe)

        async with db_sessionmaker() as cancellation, db_sessionmaker() as ordinary:

            async def reply():
                await complaints.reply_as_staff(
                    ordinary,
                    actor_user_id=graph.admin.id,
                    complaint_id=complaint_id,
                    message="Staff follow-up",
                    resolve=False,
                    client_request_id=uuid4(),
                )
                await ordinary.commit()

            if ordinary_first:
                await ordinary.scalar(
                    select(Complaint).where(Complaint.id == complaint_id).with_for_update()
                )
            cancel = asyncio.create_task(invoke(cancellation, graph, payload))
            try:
                await asyncio.wait_for(reached.wait(), 10)
                if ordinary_first:
                    await asyncio.wait_for(reply(), 10)
                else:
                    reply_task = asyncio.create_task(reply())
                    release.set()
                    await asyncio.wait_for(reply_task, 10)
                await asyncio.wait_for(cancel, 10)
            finally:
                release.set()
                if not cancel.done():
                    cancel.cancel()
                    await asyncio.gather(cancel, return_exceptions=True)

    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["disable", "revoke"])
def test_cancellation_first_blocks_account_changes_and_concurrent_retries_converge(
    db_client,
    db_sessionmaker,
    settings,
    monkeypatch,
    change,
):
    graph, complaint_id = graph_and_request(db_client, db_sessionmaker, settings)
    payload = cancel_body(complaint_id)

    async def exercise():
        reached, release = asyncio.Event(), asyncio.Event()
        original = campaign_cancellations._validate_cancellation_complaint

        async def hold(*args, **kwargs):
            await original(*args, **kwargs)
            reached.set()
            await release.wait()

        monkeypatch.setattr(campaign_cancellations, "_validate_cancellation_complaint", hold)
        async with db_sessionmaker() as cancellation, db_sessionmaker() as replay:
            first = asyncio.create_task(invoke(cancellation, graph, payload))
            repeat = None
            try:
                await asyncio.wait_for(reached.wait(), 10)
                update = (
                    "UPDATE users SET status='disabled' WHERE id=:id"
                    if change == "disable"
                    else "UPDATE users SET session_version=session_version+1 WHERE id=:id"
                )
                async with db_sessionmaker() as writer:
                    await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    with pytest.raises(DBAPIError):
                        await writer.execute(text(update), {"id": graph.admin.id})
                    await writer.rollback()
                    repeat = asyncio.create_task(invoke(replay, graph, payload))
                    release.set()
                    result, retried = await asyncio.wait_for(asyncio.gather(first, repeat), 15)
                    assert result.id == retried.id
                    await writer.execute(text(update), {"id": graph.admin.id})
                    await writer.commit()
                async with db_sessionmaker() as session:
                    assert (
                        await session.scalar(select(func.count()).select_from(CampaignCancellation))
                        == 1
                    )
                    assert (
                        await session.scalar(select(func.count()).select_from(ComplaintMessage))
                        == 2
                    )
            finally:
                release.set()
                for task in (first, repeat):
                    if task is not None and not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["disable", "revoke"])
def test_staff_cancellation_rechecks_account_and_session_after_wait(
    db_client,
    db_sessionmaker,
    settings,
    monkeypatch,
    change,
):
    graph, complaint_id = graph_and_request(db_client, db_sessionmaker, settings)
    payload = cancel_body(complaint_id)

    async def exercise():
        from app.services import admin_authorization

        reached = asyncio.Event()
        original = admin_authorization.require_active_admin

        async def observe(*args, **kwargs):
            reached.set()
            return await original(*args, **kwargs)

        monkeypatch.setattr(admin_authorization, "require_active_admin", observe)
        async with db_sessionmaker() as writer, db_sessionmaker() as cancellation:
            actor = await writer.scalar(
                select(User).where(User.id == graph.admin.id).with_for_update()
            )
            if change == "disable":
                actor.status = "disabled"
            else:
                actor.session_version += 1
            await writer.flush()
            task = asyncio.create_task(invoke(cancellation, graph, payload))
            try:
                await asyncio.wait_for(reached.wait(), 10)
                assert not task.done()
                await writer.commit()
                with pytest.raises(AppError) as denied:
                    await asyncio.wait_for(task, 10)
                assert denied.value.status_code == 403
                await cancellation.rollback()
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())

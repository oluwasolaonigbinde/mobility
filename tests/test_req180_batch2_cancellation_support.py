import asyncio
from uuid import uuid4

from sqlalchemy import func, select
from test_complaints import body, build_graph, headers

from app.models.billing import (
    CampaignLiabilityReservation,
    CommercialTerms,
    Invoice,
    PaymentReceipt,
    ReceiptAllocation,
)
from app.models.campaign import Campaign
from app.models.campaign_assignment import CampaignAssignment
from app.models.campaign_cancellation import (
    CampaignCancellation,
    CampaignCancellationSettlementRevision,
)
from app.models.complaint import Complaint, ComplaintMessage, ComplaintReferenceType
from app.models.notification import Notification
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip import TripSession
from app.schemas.complaints import ComplaintCategory
from app.services.complaints import advertiser_owner, raise_complaint

CATEGORY = "campaign_cancellation"
PATH = "/api/v1/advertiser/complaints"


def economic_snapshot(maker):
    async def snapshot():
        async with maker() as session:
            result = {}
            for model in (
                Campaign,
                CampaignAssignment,
                CampaignCancellation,
                CampaignCancellationSettlementRevision,
                CampaignLiabilityReservation,
                CommercialTerms,
                Invoice,
                PaymentReceipt,
                ReceiptAllocation,
                EarningsLedgerEntry,
                PayoutCalculation,
                TripSession,
            ):
                table = model.__table__
                result[table.name] = list(
                    await session.execute(
                        select(*table.columns).order_by(*table.primary_key.columns)
                    )
                )
            return result

    return asyncio.run(snapshot())


def test_cancellation_request_is_a_visible_idempotent_support_thread_only(
    db_client,
    db_sessionmaker,
    settings,
):
    graph = build_graph(db_sessionmaker)

    async def running():
        async with db_sessionmaker() as session:
            (await session.get(Campaign, graph.campaign.id)).status = "active"
            (await session.get(CampaignAssignment, graph.trip.assignment_id)).status = "active"
            await session.commit()

    asyncio.run(running())
    before = economic_snapshot(db_sessionmaker)
    payload = body(
        CATEGORY,
        message="  Please cancel this campaign and discuss the next steps.  ",
        reference_type="campaign",
        reference_id=str(graph.campaign.id),
    )
    viewer = headers(graph.viewer, settings)
    created = db_client.post(PATH, headers=viewer, json=payload)
    assert created.status_code == 200, created.text
    result = created.json()
    identity = result["id"]
    assert set(result) == {
        "id",
        "category",
        "status",
        "reference_type",
        "reference_label",
        "created_at",
        "last_message_at",
        "waiting_on_you",
        "messages",
    }
    assert result["category"] == CATEGORY and result["status"] == "open"
    assert (
        result["reference_type"] == "campaign" and result["reference_label"] == graph.campaign.name
    )
    assert result["messages"][0]["body"] == payload["message"].strip()
    assert result["messages"][0]["sender"] == "you"
    replay = db_client.post(PATH, headers=viewer, json=payload)
    assert replay.status_code == 200 and replay.json()["id"] == identity
    for change in (
        {"message": "A different reason"},
        {"category": "campaign_or_job"},
        {"reference_id": str(graph.declined_campaign.id)},
    ):
        conflict = db_client.post(PATH, headers=viewer, json={**payload, **change})
        assert (
            conflict.status_code == 409
            and conflict.json()["error"]["code"] == "COMPLAINT_REPLAY_CONFLICT"
        )
    for route, who in (
        (PATH, graph.advertiser),
        (f"{PATH}/{identity}", graph.viewer),
        ("/api/v1/admin/complaints", graph.admin),
        (f"/api/v1/admin/complaints/{identity}", graph.admin),
    ):
        response = db_client.get(route, headers=headers(who, settings))
        assert response.status_code == 200, response.text
        item = response.json()["items"][0] if "items" in response.json() else response.json()
        assert item["category"] == CATEGORY and item["reference_type"] == "campaign"
        if route.startswith("/api/v1/admin/"):
            assert item["reference_id"] == str(graph.campaign.id)
    assert economic_snapshot(db_sessionmaker) == before

    async def counts():
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(Complaint)) == 1
            assert await session.scalar(select(func.count()).select_from(ComplaintMessage)) == 1
            notices = list(await session.scalars(select(Notification)))
            assert len(notices) == 2
            assert all(notice.payload == {"complaint_id": identity} for notice in notices)

    asyncio.run(counts())


def test_cancellation_support_denials_and_retired_self_service_do_not_change_campaign(
    db_client,
    db_sessionmaker,
    settings,
):
    graph = build_graph(db_sessionmaker)
    before = economic_snapshot(db_sessionmaker)
    valid = body(
        CATEGORY,
        message="Please cancel this campaign",
        reference_type="campaign",
        reference_id=str(graph.campaign.id),
    )
    cases = [
        ({"reference_type": None, "reference_id": None}, 422, "COMPLAINT_CAMPAIGN_REQUIRED"),
        ({"reference_id": None}, 422, "COMPLAINT_REFERENCE_INCOMPLETE"),
        ({"reference_type": None}, 422, "COMPLAINT_REFERENCE_INCOMPLETE"),
        (
            {"reference_type": "trip", "reference_id": str(graph.trip.id)},
            422,
            "COMPLAINT_CAMPAIGN_REQUIRED",
        ),
        ({"reference_id": str(graph.other_campaign.id)}, 404, "COMPLAINT_REFERENCE_NOT_FOUND"),
        ({"reference_id": str(uuid4())}, 404, "COMPLAINT_REFERENCE_NOT_FOUND"),
        ({"message": " \t "}, 422, "VALIDATION_ERROR"),
        ({"message": "x" * 2001}, 422, "VALIDATION_ERROR"),
    ]
    for change, code, error in cases:
        response = db_client.post(
            PATH, headers=headers(graph.advertiser, settings), json={**valid, **change}
        )
        assert response.status_code == code and response.json()["error"]["code"] == error, (
            response.text
        )
    driver = db_client.post(
        "/api/v1/driver/complaints", headers=headers(graph.driver, settings), json=valid
    )
    assert (
        driver.status_code == 422
        and driver.json()["error"]["code"] == "COMPLAINT_CATEGORY_NOT_ALLOWED"
    )
    assert db_client.post(PATH, json=valid).status_code == 401
    old = db_client.post(
        f"/api/v1/advertiser/campaigns/{graph.campaign.id}/cancel",
        headers=headers(graph.advertiser, settings),
        json={"reason": "Old command", "client_request_id": str(uuid4())},
    )
    assert old.status_code == 404
    schema = db_client.get("/openapi.json").json()
    assert "/api/v1/advertiser/campaigns/{campaign_id}/cancel" not in schema["paths"]
    assert "/api/v1/admin/campaign-assignments/{assignment_id}/cancel" in schema["paths"]
    assert economic_snapshot(db_sessionmaker) == before

    async def no_thread():
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(Complaint)) == 0
            assert await session.scalar(select(func.count()).select_from(ComplaintMessage)) == 0

    asyncio.run(no_thread())


def test_concurrent_cancellation_support_retries_keep_existing_per_raiser_identity(
    db_sessionmaker,
):
    graph = build_graph(db_sessionmaker)
    request_id = uuid4()

    async def exercise():
        async def create(user):
            async with db_sessionmaker() as session:
                result = await raise_complaint(
                    session,
                    owner=await advertiser_owner(session, user),
                    category=ComplaintCategory.CAMPAIGN_CANCELLATION,
                    message="Please discuss cancellation",
                    reference_type=ComplaintReferenceType.CAMPAIGN,
                    reference_id=graph.campaign.id,
                    client_request_id=request_id,
                )
                await session.commit()
                return result.complaint.id

        first, repeated = await asyncio.gather(create(graph.advertiser), create(graph.advertiser))
        assert first == repeated
        assert await create(graph.viewer) != first
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(Complaint)) == 2
            assert await session.scalar(select(func.count()).select_from(ComplaintMessage)) == 2
            assert await session.scalar(select(func.count()).select_from(CampaignCancellation)) == 0

    asyncio.run(exercise())

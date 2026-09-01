import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_campaign_assignment,
    fetch_audit_events,
    fetch_location_ping_batches,
    fetch_payout_calculations,
)
from sqlalchemy import func, select
from test_campaign_assignments import create_assignment_ready_graph
from test_financial_authority import _fixture, _funded_terms
from test_payouts_v2 import build_v2_graph, moving_points, pipeline_to_v2
from test_payouts_v3 import bind_v2_graph
from test_trip_analytics import BASE_TIME, add_pings, create_analytics_graph
from test_trips import create_trip_ready_graph, ping_payload

from app.core.errors import AppError
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_assignment import CampaignActivationEvent, CampaignAssignment
from app.models.campaign_cancellation import (
    CampaignCancellation,
    CampaignCancellationSettlementRevision,
)
from app.models.trip import TripSession
from app.schemas.campaign_cancellations import CampaignCancellationCreate
from app.schemas.trips import TripStartRequest
from app.services import campaign_cancellations
from app.services.billing import reverse_payment_receipt
from app.services.campaign_cancellations import request_campaign_cancellation
from app.services.trips import start_driver_trip


def test_advertiser_cancellation_is_tenant_scoped_idempotent_and_stops_assignments(
    db_client,
    db_sessionmaker,
) -> None:
    admin, campaign, _, profile, vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        admin_email="cancel-admin@example.com",
        advertiser_email="cancel-owner@example.com",
        driver_email="cancel-driver@example.com",
        plate_number="CAN-001",
    )
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
    )
    request_id = uuid4()
    payload = {
        "client_request_id": str(request_id),
        "reason": "Advertiser ended the campaign",
    }
    headers = auth_headers(db_client, "cancel-owner@example.com")

    created = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/cancel",
        headers=headers,
        json=payload,
    )
    replay = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/cancel",
        headers=headers,
        json=payload,
    )
    conflict = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/cancel",
        headers=headers,
        json={**payload, "reason": "Changed retry"},
    )

    assert created.status_code == 201, created.text
    assert replay.status_code == 201
    assert replay.json()["id"] == created.json()["id"]
    assert created.json()["disposition"] == "no_settlement"
    assert created.json()["cancelled_assignment_count"] == 1
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CAMPAIGN_CANCELLATION_CONFLICT"

    async def inspect() -> tuple[str, str, int, int, int]:
        async with db_sessionmaker() as session:
            current_campaign = await session.get(Campaign, campaign.id)
            current_assignment = await session.get(CampaignAssignment, assignment.id)
            cancellation_count = await session.scalar(
                select(func.count()).select_from(CampaignCancellation)
            )
            revision_count = await session.scalar(
                select(func.count()).select_from(CampaignCancellationSettlementRevision)
            )
            event_count = await session.scalar(
                select(func.count())
                .select_from(CampaignActivationEvent)
                .where(CampaignActivationEvent.assignment_id == assignment.id)
            )
            return (
                current_campaign.status,
                current_assignment.status,
                int(cancellation_count or 0),
                int(revision_count or 0),
                int(event_count or 0),
            )

    assert asyncio.run(inspect()) == ("cancelled", "cancelled", 1, 1, 1)
    assert [event.action for event in fetch_audit_events(db_sessionmaker)].count(
        "advertiser.campaign.cancelled"
    ) == 1


def test_cash_cancellation_freezes_refund_due_before_exact_boundary(
    db_client,
    db_sessionmaker,
    monkeypatch,
) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "campaign-cancel")

    async def fund_and_activate() -> object:
        async with db_sessionmaker() as session:
            terms, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="CAMPAIGN-CANCEL",
            )
            current = await session.get(Campaign, campaign.id)
            current.status = CampaignStatus.ACTIVE.value
            await session.commit()
            return terms, allocation

    terms, allocation = asyncio.run(fund_and_activate())

    async def before_boundary(_session):
        return allocation.allocated_at + timedelta(hours=23)

    monkeypatch.setattr(campaign_cancellations, "database_clock", before_boundary)
    response = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/cancel",
        headers=auth_headers(db_client, owner.email),
        json={
            "client_request_id": str(uuid4()),
            "reason": "Cancel inside the standard refund window",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["commercial_terms_id"] == str(terms.id)
    assert response.json()["disposition"] == "cash_refund_due"
    assert response.json()["refundable_amount"] == "100.00"
    assert response.json()["cutoff_at"] == (
        allocation.allocated_at + timedelta(hours=23)
    ).isoformat().replace("+00:00", "Z")

    async def reverse_authoritative_receipt() -> None:
        async with db_sessionmaker() as session:
            await reverse_payment_receipt(
                session,
                receipt_id=allocation.receipt_id,
                actor_user_id=admin.id,
                reason="settle the frozen cancellation",
            )
            await session.commit()

    asyncio.run(reverse_authoritative_receipt())
    settlement = db_client.post(
        "/api/v1/admin/refunds",
        headers=auth_headers(db_client, admin.email),
        json={
            "commercial_terms_id": str(terms.id),
            "receipt_id": str(allocation.receipt_id),
            "amount": "100.00",
            "settlement_provider": "bank",
            "external_reference": "CAMPAIGN-CANCEL-REFUND",
            "reason": "book frozen cancellation after the request",
        },
    )
    assert settlement.status_code == 200, settlement.text
    assert settlement.json()["cancellation_id"] == response.json()["id"]
    assert settlement.json()["eligibility_evaluated_at"] == response.json()["cutoff_at"]


def test_cash_cancellation_at_exact_standard_boundary_records_no_refund_due(
    db_client,
    db_sessionmaker,
    monkeypatch,
) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "campaign-cancel-boundary")

    async def fund_and_activate():
        async with db_sessionmaker() as session:
            terms, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="CAMPAIGN-CANCEL-BOUNDARY",
            )
            current = await session.get(Campaign, campaign.id)
            current.status = CampaignStatus.ACTIVE.value
            await session.commit()
            return terms, allocation

    terms, allocation = asyncio.run(fund_and_activate())

    async def at_boundary(_session):
        return allocation.allocated_at + timedelta(hours=24)

    monkeypatch.setattr(campaign_cancellations, "database_clock", at_boundary)
    response = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/cancel",
        headers=auth_headers(db_client, owner.email),
        json={
            "client_request_id": str(uuid4()),
            "reason": "Cancel at the exact standard boundary",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["commercial_terms_id"] == str(terms.id)
    assert response.json()["disposition"] == "cash_refund_not_due"
    assert response.json()["refundable_amount"] == "0.00"


def test_post_cutoff_tracking_is_retained_as_non_economic_evidence(
    db_client,
    db_sessionmaker,
) -> None:
    _, campaign, _, _, _, assignment = create_trip_ready_graph(
        db_sessionmaker,
        admin_email="cancel-track-admin@example.com",
        advertiser_email="cancel-track-owner@example.com",
        driver_email="cancel-track-driver@example.com",
        plate_number="CAN-TRK",
    )
    started = db_client.post(
        "/api/v1/driver/trips/start",
        headers=auth_headers(db_client, "cancel-track-driver@example.com"),
        json={"assignment_id": str(assignment.id), "metadata": {}},
    )
    assert started.status_code == 201, started.text

    cancelled = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/cancel",
        headers=auth_headers(db_client, "cancel-track-owner@example.com"),
        json={
            "client_request_id": str(uuid4()),
            "reason": "Stop new work but retain tracking evidence",
        },
    )
    assert cancelled.status_code == 201, cancelled.text
    cutoff = datetime.fromisoformat(cancelled.json()["cutoff_at"].replace("Z", "+00:00"))

    batch = db_client.post(
        f"/api/v1/driver/trips/{started.json()['id']}/pings",
        headers=auth_headers(db_client, "cancel-track-driver@example.com"),
        json=ping_payload(
            recorded_at=cutoff + timedelta(microseconds=1),
            idempotency_key="post-cancellation-evidence",
        ),
    )

    assert batch.status_code == 200, batch.text
    assert batch.json()["accepted_count"] == 1
    stored = fetch_location_ping_batches(db_sessionmaker)
    assert stored[0].batch_metadata["financial_cutoff_at"] == cutoff.isoformat()
    assert stored[0].batch_metadata["post_cutoff_ping_count"] == 1


def test_analytics_recompute_clips_at_the_same_immutable_cutoff(
    postgis_db_client,
    postgis_db_sessionmaker,
    monkeypatch,
) -> None:
    admin, _, _, campaign, _, _, _, trip = create_analytics_graph(
        postgis_db_sessionmaker,
        admin_email="cancel-analytics-admin@example.com",
        advertiser_email="cancel-analytics-owner@example.com",
        driver_email="cancel-analytics-driver@example.com",
        plate_number="CAN-ANA",
    )
    cutoff = BASE_TIME + timedelta(minutes=10)
    add_pings(
        postgis_db_sessionmaker,
        trip_id=trip.id,
        points=[
            (BASE_TIME, 6.45, 3.39, 10),
            (BASE_TIME + timedelta(minutes=5), 6.45, 3.40, 10),
            (cutoff, 6.45, 3.41, 10),
            (BASE_TIME + timedelta(minutes=15), 6.45, 3.42, 10),
        ],
        idempotency_key="cancel-analytics",
    )

    async def fixed_cutoff(_session):
        return cutoff

    monkeypatch.setattr(campaign_cancellations, "database_clock", fixed_cutoff)
    cancelled = postgis_db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/cancel",
        headers=auth_headers(postgis_db_client, "cancel-analytics-owner@example.com"),
        json={"client_request_id": str(uuid4()), "reason": "Clip route analytics"},
    )
    recomputed = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=auth_headers(postgis_db_client, admin.email),
        json={"metadata": {"source": "cancellation-regression"}},
    )

    assert cancelled.status_code == 201, cancelled.text
    assert recomputed.status_code == 200, recomputed.text
    assert recomputed.json()["ping_count"] == 3
    assert recomputed.json()["duration_seconds"] == 600
    assert datetime.fromisoformat(recomputed.json()["ended_at"].replace("Z", "+00:00")) == cutoff
    assert recomputed.json()["metadata"]["financial_cutoff_at"] == cutoff.isoformat()


@pytest.mark.parametrize(
    ("bound_v3", "formula_version", "expected_amount"),
    [(False, "payout_v2", Decimal("300.00")), (True, "payout_v3", Decimal("250.00"))],
)
def test_pre_cutoff_time_pays_and_post_cutoff_time_never_enters_payout(
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
    bound_v3,
    formula_version,
    expected_amount,
) -> None:
    graph = build_v2_graph(
        postgis_db_sessionmaker,
        f"cancel-{formula_version}",
    )
    if bound_v3:
        bind_v2_graph(
            postgis_db_sessionmaker,
            settings,
            graph,
            base="1000.00",
            premium="2000.00",
        )
    cutoff = graph.trip.started_at + timedelta(minutes=15)

    async def fixed_cutoff(_session):
        return cutoff

    async def cancel() -> None:
        async with postgis_db_sessionmaker() as session:
            await request_campaign_cancellation(
                session,
                actor_user_id=graph.campaign.created_by_user_id,
                campaign_id=graph.campaign.id,
                payload=CampaignCancellationCreate(
                    client_request_id=uuid4(),
                    reason="Freeze the payable interval",
                ),
            )
            await session.commit()

    monkeypatch.setattr(campaign_cancellations, "database_clock", fixed_cutoff)
    asyncio.run(cancel())
    result = pipeline_to_v2(
        postgis_db_sessionmaker,
        settings,
        graph,
        points=moving_points(graph.trip.started_at),
        idempotency_key=f"cancel-{formula_version}-pings",
    )

    assert result.overall == "completed"
    calculation = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    assert calculation.formula_version == formula_version
    assert calculation.eligible_seconds == 900
    assert calculation.payable_seconds == 900
    assert calculation.final_payout == expected_amount
    assert calculation.payout_metadata["financial_cutoff_at"] == cutoff.isoformat()
    assert calculation.payout_metadata["recorded_trip_end_at"] == graph.trip.ended_at.isoformat()


def test_cancellation_and_trip_start_race_never_creates_post_cutoff_work(
    postgis_db_sessionmaker,
    settings,
) -> None:
    _, campaign, driver, _, _, assignment = create_trip_ready_graph(
        postgis_db_sessionmaker,
        admin_email="cancel-race-admin@example.com",
        advertiser_email="cancel-race-owner@example.com",
        driver_email="cancel-race-driver@example.com",
        plate_number="CAN-RACE",
    )

    async def cancel() -> str:
        async with postgis_db_sessionmaker() as session:
            await request_campaign_cancellation(
                session,
                actor_user_id=campaign.created_by_user_id,
                campaign_id=campaign.id,
                payload=CampaignCancellationCreate(
                    client_request_id=uuid4(),
                    reason="Race cancellation against trip start",
                ),
            )
            await session.commit()
            return "cancelled"

    async def start() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await start_driver_trip(
                    session,
                    user_id=driver.id,
                    payload=TripStartRequest(assignment_id=assignment.id),
                    settings=settings,
                )
                await session.commit()
                return "started"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def race_and_inspect():
        outcomes = await asyncio.wait_for(asyncio.gather(cancel(), start()), timeout=10)
        async with postgis_db_sessionmaker() as session:
            cancellation = await session.scalar(
                select(CampaignCancellation).where(
                    CampaignCancellation.campaign_id == campaign.id
                )
            )
            trips = list(
                await session.scalars(
                    select(TripSession).where(TripSession.campaign_id == campaign.id)
                )
            )
            return outcomes, cancellation, trips

    outcomes, cancellation, trips = asyncio.run(race_and_inspect())
    assert outcomes[0] == "cancelled"
    assert outcomes[1] in {"started", "CAMPAIGN_ASSIGNMENT_NOT_ACTIVE"}
    assert len(trips) <= 1
    assert all(trip.started_at <= cancellation.cutoff_at for trip in trips)

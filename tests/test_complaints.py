"""In-app complaints and the Customer Service inbox (D39(d), Batch E)."""

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.audit import AuditEvent
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.complaint import Complaint, ComplaintMessage
from app.models.notification import Notification, NotificationType
from app.models.organization import (
    AdvertiserOrganizationNotificationPreference,
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
    OrganizationStatus,
)
from app.models.payout import EarningsLedgerEntry, EarningsLedgerEntryStatus
from app.models.user import UserRole, UserStatus
from app.services import complaints as complaint_service
from app.services.email_templates import render_email_template

SECRET_TEXT = "My phone is 08011112222 and the sticker peeled off"


@dataclass
class Graph:
    admin: object
    admin2: object
    driver: object
    profile: object
    other_driver: object
    other_profile: object
    advertiser: object
    viewer: object
    org: object
    other_advertiser: object
    campaign: object
    other_campaign: object
    trip: object
    other_trip: object
    entry: UUID
    other_entry: UUID
    declined_campaign: object


def _entry(sessionmaker, *, profile, user, campaign, entry_type="adjustment", amount="2678.94"):
    async def create() -> UUID:
        async with sessionmaker() as session:
            entry = EarningsLedgerEntry(
                driver_profile_id=profile.id,
                driver_user_id=user.id,
                campaign_id=campaign.id,
                entry_type=entry_type,
                status=EarningsLedgerEntryStatus.AVAILABLE.value,
                amount=Decimal(amount),
                currency="NGN",
                description="Synthetic",
                occurred_at=datetime(2026, 9, 3, 9, 0, tzinfo=UTC),
                ledger_metadata={},
            )
            session.add(entry)
            await session.commit()
            return entry.id

    return asyncio.run(create())


def _add_member(sessionmaker, *, org_id, user_id, role, member_status=MembershipStatus.ACTIVE):
    async def create() -> None:
        async with sessionmaker() as session:
            session.add(
                OrganizationMembership(
                    organization_id=org_id, user_id=user_id, role=role, status=member_status
                )
            )
            await session.commit()

    asyncio.run(create())


def build_graph(sm) -> Graph:
    admin = create_test_user(sm, email="cs-admin@example.com", full_name="Ada Staff")
    admin2 = create_test_user(sm, email="cs-admin2@example.com", full_name="Bola Staff")
    driver = create_test_user(
        sm, email="cs-driver@example.com", role=UserRole.DRIVER, full_name="Dayo Driver"
    )
    other_driver = create_test_user(
        sm, email="cs-driver2@example.com", role=UserRole.DRIVER, full_name="Other Driver"
    )
    advertiser = create_test_user(
        sm, email="cs-adv@example.com", role=UserRole.ADVERTISER, full_name="Ade Owner"
    )
    viewer = create_test_user(
        sm, email="cs-viewer@example.com", role=UserRole.ADVERTISER, full_name="Vic Viewer"
    )
    other_advertiser = create_test_user(
        sm, email="cs-adv2@example.com", role=UserRole.ADVERTISER, full_name="Other Owner"
    )
    org, _ = create_test_organization(sm, name="Acme Ads", owner_user_id=advertiser.id)
    _add_member(sm, org_id=org.id, user_id=viewer.id, role=MembershipRole.VIEWER)
    other_org, _ = create_test_organization(sm, name="Other Ads", owner_user_id=other_advertiser.id)
    profile = create_test_driver_profile(sm, user_id=driver.id)
    other_profile = create_test_driver_profile(sm, user_id=other_driver.id)
    vehicle = create_test_vehicle(sm, driver_profile_id=profile.id)
    other_vehicle = create_test_vehicle(
        sm, driver_profile_id=other_profile.id, plate_number="XYZ-987"
    )
    campaign = create_test_campaign(
        sm, organization_id=org.id, created_by_user_id=advertiser.id, name="Lagos Launch"
    )
    other_campaign = create_test_campaign(
        sm, organization_id=other_org.id, created_by_user_id=other_advertiser.id, name="Rival"
    )
    declined_campaign = create_test_campaign(
        sm, organization_id=org.id, created_by_user_id=advertiser.id, name="Declined job"
    )
    assignment = create_test_campaign_assignment(
        sm,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACCEPTED,
        accepted_at=datetime.now(UTC),
    )
    create_test_campaign_assignment(
        sm,
        campaign_id=declined_campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.OFFERED,
    )
    other_assignment = create_test_campaign_assignment(
        sm,
        campaign_id=other_campaign.id,
        driver_profile_id=other_profile.id,
        vehicle_id=other_vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACCEPTED,
        accepted_at=datetime.now(UTC),
    )
    trip = create_test_trip_session(
        sm,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        started_at=datetime(2026, 9, 3, 7, 15, tzinfo=UTC),
    )
    other_trip = create_test_trip_session(
        sm,
        assignment_id=other_assignment.id,
        campaign_id=other_campaign.id,
        driver_profile_id=other_profile.id,
        vehicle_id=other_vehicle.id,
        started_by_user_id=other_driver.id,
    )
    entry = _entry(sm, profile=profile, user=driver, campaign=campaign)
    other_entry = _entry(sm, profile=other_profile, user=other_driver, campaign=other_campaign)
    return Graph(
        admin,
        admin2,
        driver,
        profile,
        other_driver,
        other_profile,
        advertiser,
        viewer,
        org,
        other_advertiser,
        campaign,
        other_campaign,
        trip,
        other_trip,
        entry,
        other_entry,
        declined_campaign,
    )


def headers(user, settings) -> dict[str, str]:
    token = create_access_token(user.id, settings, session_version=user.session_version)[0]
    return {"Authorization": f"Bearer {token}"}


def rows(sm, model):
    async def read():
        async with sm() as session:
            return list(await session.scalars(select(model)))

    return asyncio.run(read())


def count(sm, model) -> int:
    async def read() -> int:
        async with sm() as session:
            return int(await session.scalar(select(func.count()).select_from(model)) or 0)

    return asyncio.run(read())


def body(category="trip_or_tracking", message=SECRET_TEXT, **extra):
    return {"category": category, "message": message, "client_request_id": str(uuid4()), **extra}


@pytest.fixture
def world(postgis_db_client, postgis_db_sessionmaker, settings):
    graph = build_graph(postgis_db_sessionmaker)
    return postgis_db_client, postgis_db_sessionmaker, settings, graph


def test_driver_raises_with_own_trip_and_staff_are_told(world) -> None:
    client, sm, settings, g = world
    payload = body(reference_type="trip", reference_id=str(g.trip.id))

    response = client.post(
        "/api/v1/driver/complaints", json=payload, headers=headers(g.driver, settings)
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "open"
    assert data["reference_type"] == "trip"
    assert data["reference_label"] == "Trip on 3 Sep 2026, 08:15 (Nigeria time, WAT)"
    assert data["messages"] == [
        {"sender": "you", "body": SECRET_TEXT, "sent_at": data["messages"][0]["sent_at"]}
    ]
    # No identifiers beyond the complaint's own id reach the driver.
    assert str(g.trip.id) not in response.text
    assert str(g.driver.id) not in response.text
    [complaint] = rows(sm, Complaint)
    assert (complaint.party, complaint.trip_session_id) == ("driver", g.trip.id)
    [audit] = [e for e in rows(sm, AuditEvent) if e.entity_type == "complaint"]
    assert audit.action == "driver.complaint.created"
    notices = rows(sm, Notification)
    assert {n.recipient_user_id for n in notices} == {g.admin.id, g.admin2.id}
    assert {n.type_key for n in notices} == {NotificationType.COMPLAINT_RECEIVED.value}
    assert all(n.payload == {"complaint_id": str(complaint.id)} for n in notices)

    # An exact retry converges without a second audit or notice; changed reuse is 409.
    again = client.post(
        "/api/v1/driver/complaints", json=payload, headers=headers(g.driver, settings)
    )
    assert again.status_code == 200 and again.json()["id"] == data["id"]
    changed = client.post(
        "/api/v1/driver/complaints",
        json={**payload, "message": "Different"},
        headers=headers(g.driver, settings),
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "COMPLAINT_REPLAY_CONFLICT"
    assert count(sm, Complaint) == 1 and count(sm, Notification) == 2
    assert len([e for e in rows(sm, AuditEvent) if e.entity_type == "complaint"]) == 1


@pytest.mark.parametrize(
    ("reference_type", "attr"),
    [
        ("trip", "other_trip"),
        ("payout", "other_entry"),
        ("campaign", "other_campaign"),
        ("campaign", "declined_campaign"),
        ("trip", None),
    ],
)
def test_foreign_or_unknown_driver_reference_is_404_and_writes_nothing(
    world, reference_type, attr
) -> None:
    client, sm, settings, g = world
    target = getattr(g, attr) if attr else None
    reference_id = (
        str(target if isinstance(target, UUID) else target.id) if target else str(uuid4())
    )

    response = client.post(
        "/api/v1/driver/complaints",
        json=body(reference_type=reference_type, reference_id=reference_id),
        headers=headers(g.driver, settings),
    )

    assert response.status_code == 404
    assert response.json()["error"] == {
        **response.json()["error"],
        "code": "COMPLAINT_REFERENCE_NOT_FOUND",
        "message": "The campaign, trip or payout was not found",
    }
    assert count(sm, Complaint) == 0 and count(sm, Notification) == 0
    assert count(sm, AuditEvent) == 0


def test_driver_own_payout_and_campaign_references(world) -> None:
    client, sm, settings, g = world
    for reference_type, reference_id, label in (
        ("payout", g.entry, "Pay adjustment ₦2,678.94 · 3 Sep 2026"),
        ("campaign", g.campaign.id, "Lagos Launch"),
    ):
        response = client.post(
            "/api/v1/driver/complaints",
            json=body(
                "pay_or_payout", reference_type=reference_type, reference_id=str(reference_id)
            ),
            headers=headers(g.driver, settings),
        )
        assert response.status_code == 200, response.text
        assert response.json()["reference_label"] == label

    options = client.get(
        "/api/v1/driver/complaints/reference-options", headers=headers(g.driver, settings)
    )
    assert options.status_code == 200
    data = options.json()
    assert [item["label"] for item in data["campaigns"]] == ["Lagos Launch"]
    assert [item["id"] for item in data["trips"]] == [str(g.trip.id)]
    assert [item["id"] for item in data["payouts"]] == [str(g.entry)]


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (body("billing_or_invoice"), "COMPLAINT_CATEGORY_NOT_ALLOWED"),
        (body(reference_type="trip"), "COMPLAINT_REFERENCE_INCOMPLETE"),
        (body(reference_id=str(uuid4())), "COMPLAINT_REFERENCE_INCOMPLETE"),
    ],
)
def test_driver_invalid_requests_are_422(world, payload, code) -> None:
    client, sm, settings, g = world
    response = client.post(
        "/api/v1/driver/complaints", json=payload, headers=headers(g.driver, settings)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
    assert count(sm, Complaint) == 0


@pytest.mark.parametrize("message", ["   ", "before\x00after"])
def test_blank_or_nul_message_is_rejected_by_the_schema(world, message) -> None:
    client, sm, settings, g = world
    response = client.post(
        "/api/v1/driver/complaints", json=body(message=message), headers=headers(g.driver, settings)
    )
    assert response.status_code == 422
    assert count(sm, Complaint) == 0

    complaint_id = client.post(
        "/api/v1/driver/complaints", json=body(), headers=headers(g.driver, settings)
    ).json()["id"]
    for url, user in (
        (f"/api/v1/driver/complaints/{complaint_id}/messages", g.driver),
        (f"/api/v1/admin/complaints/{complaint_id}/messages", g.admin),
    ):
        refused = client.post(
            url,
            json={"message": message, "client_request_id": str(uuid4())},
            headers=headers(user, settings),
        )
        assert refused.status_code == 422
    assert count(sm, ComplaintMessage) == 1


def test_driver_without_profile_is_404(world) -> None:
    client, sm, settings, _g = world
    lone = create_test_user(sm, email="cs-lone@example.com", role=UserRole.DRIVER)
    response = client.get("/api/v1/driver/complaints", headers=headers(lone, settings))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DRIVER_PROFILE_NOT_FOUND"


def test_advertiser_scope_viewer_team_and_foreign_campaign(world) -> None:
    client, sm, settings, g = world
    for reference_type, code in (("trip", 422), ("payout", 422)):
        denied = client.post(
            "/api/v1/advertiser/complaints",
            json=body("campaign_or_job", reference_type=reference_type, reference_id=str(uuid4())),
            headers=headers(g.advertiser, settings),
        )
        assert denied.status_code == code
        assert denied.json()["error"]["code"] == "COMPLAINT_REFERENCE_NOT_ALLOWED"
    foreign = client.post(
        "/api/v1/advertiser/complaints",
        json=body(
            "campaign_or_job", reference_type="campaign", reference_id=str(g.other_campaign.id)
        ),
        headers=headers(g.advertiser, settings),
    )
    assert foreign.status_code == 404
    assert (
        client.post(
            "/api/v1/advertiser/complaints",
            json=body("trip_or_tracking"),
            headers=headers(g.advertiser, settings),
        ).json()["error"]["code"]
        == "COMPLAINT_CATEGORY_NOT_ALLOWED"
    )

    # A viewer can raise a complaint (support is not a campaign write).
    raised = client.post(
        "/api/v1/advertiser/complaints",
        json=body("campaign_or_job", reference_type="campaign", reference_id=str(g.campaign.id)),
        headers=headers(g.viewer, settings),
    )
    assert raised.status_code == 200, raised.text
    complaint_id = raised.json()["id"]
    options = client.get(
        "/api/v1/advertiser/complaints/reference-options", headers=headers(g.viewer, settings)
    ).json()
    assert {item["label"] for item in options["campaigns"]} == {"Lagos Launch", "Declined job"}
    assert options["trips"] == [] and options["payouts"] == []

    # The owner sees the same organization complaint; the viewer's message reads "your_team".
    listed = client.get("/api/v1/advertiser/complaints", headers=headers(g.advertiser, settings))
    assert [item["id"] for item in listed.json()["items"]] == [complaint_id]
    detail = client.get(
        f"/api/v1/advertiser/complaints/{complaint_id}", headers=headers(g.advertiser, settings)
    )
    assert [m["sender"] for m in detail.json()["messages"]] == ["your_team"]

    # Another organization and the driver cannot see it.
    assert (
        client.get(
            f"/api/v1/advertiser/complaints/{complaint_id}",
            headers=headers(g.other_advertiser, settings),
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/driver/complaints/{complaint_id}", headers=headers(g.driver, settings)
        ).status_code
        == 404
    )
    other_follow_up = client.post(
        f"/api/v1/advertiser/complaints/{complaint_id}/messages",
        json={"message": "hi", "client_request_id": str(uuid4())},
        headers=headers(g.other_advertiser, settings),
    )
    assert other_follow_up.status_code == 404
    assert other_follow_up.json()["error"]["code"] == "COMPLAINT_NOT_FOUND"


def test_revoked_membership_loses_access(world) -> None:
    client, sm, settings, g = world
    raised = client.post(
        "/api/v1/advertiser/complaints",
        json=body("account"),
        headers=headers(g.viewer, settings),
    )
    complaint_id = raised.json()["id"]

    async def revoke() -> None:
        async with sm() as session:
            membership = await session.scalar(
                select(OrganizationMembership).where(OrganizationMembership.user_id == g.viewer.id)
            )
            membership.status = MembershipStatus.DISABLED
            await session.commit()

    asyncio.run(revoke())

    def denied(user) -> list:
        auth = headers(user, settings)
        return [
            client.get(f"/api/v1/advertiser/complaints/{complaint_id}", headers=auth),
            client.get("/api/v1/advertiser/complaints", headers=auth),
            client.get("/api/v1/advertiser/complaints/reference-options", headers=auth),
            client.post("/api/v1/advertiser/complaints", json=body("account"), headers=auth),
            client.post(
                f"/api/v1/advertiser/complaints/{complaint_id}/messages",
                json={"message": "hi", "client_request_id": str(uuid4())},
                headers=auth,
            ),
        ]

    for response in denied(g.viewer):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ADVERTISER_ORGANIZATION_NOT_FOUND"

    # An inactive organization locks out its still-active owner the same way.
    async def suspend() -> None:
        async with sm() as session:
            organization = await session.get(type(g.org), g.org.id)
            organization.status = OrganizationStatus.SUSPENDED
            await session.commit()

    asyncio.run(suspend())
    for response in denied(g.advertiser):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ADVERTISER_ORGANIZATION_NOT_FOUND"
    assert count(sm, Complaint) == 1 and count(sm, ComplaintMessage) == 1


def test_foreign_and_unknown_complaints_look_identical(world) -> None:
    client, sm, settings, g = world
    driver_complaint = client.post(
        "/api/v1/driver/complaints", json=body(), headers=headers(g.other_driver, settings)
    ).json()["id"]
    advertiser_complaint = client.post(
        "/api/v1/advertiser/complaints",
        json=body("account"),
        headers=headers(g.other_advertiser, settings),
    ).json()["id"]
    before = count(sm, ComplaintMessage)

    for party, user, foreign in (
        ("driver", g.driver, driver_complaint),
        ("advertiser", g.advertiser, advertiser_complaint),
    ):
        auth = headers(user, settings)
        for complaint_id in (foreign, str(uuid4())):
            responses = [
                client.get(f"/api/v1/{party}/complaints/{complaint_id}", headers=auth),
                client.post(
                    f"/api/v1/{party}/complaints/{complaint_id}/messages",
                    json={"message": "hi", "client_request_id": str(uuid4())},
                    headers=auth,
                ),
            ]
            for response in responses:
                assert response.status_code == 404
                error = response.json()["error"]
                assert (error["code"], error["message"]) == (
                    "COMPLAINT_NOT_FOUND",
                    "Complaint was not found",
                )
    assert count(sm, ComplaintMessage) == before


def test_staff_reply_resolve_follow_up_and_notifications(world) -> None:
    client, sm, settings, g = world
    raised = client.post(
        "/api/v1/advertiser/complaints",
        json=body("billing_or_invoice"),
        headers=headers(g.advertiser, settings),
    )
    complaint_id = raised.json()["id"]
    staff = headers(g.admin, settings)

    inbox = client.get("/api/v1/admin/complaints", params={"status": "open"}, headers=staff)
    assert inbox.json()["total"] == 1
    item = inbox.json()["items"][0]
    assert (item["party_name"], item["raised_by_name"]) == ("Acme Ads", "Ade Owner")

    reply = {"message": "We are checking your invoice.", "client_request_id": str(uuid4())}
    replied = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/messages", json=reply, headers=staff
    )
    assert replied.status_code == 200, replied.text
    assert replied.json()["status"] == "answered"
    assert [m["author_name"] for m in replied.json()["messages"]] == ["Ade Owner", "Ada Staff"]
    # Replay converges; the same request with resolve flipped is a conflict.
    assert (
        client.post(
            f"/api/v1/admin/complaints/{complaint_id}/messages", json=reply, headers=staff
        ).status_code
        == 200
    )
    flipped = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/messages",
        json={**reply, "resolve": True},
        headers=staff,
    )
    assert flipped.status_code == 409

    detail = client.get(
        f"/api/v1/advertiser/complaints/{complaint_id}", headers=headers(g.viewer, settings)
    ).json()
    assert [m["sender"] for m in detail["messages"]] == ["your_team", "terrax_media"]
    assert detail["waiting_on_you"] is True
    assert "Ada Staff" not in json.dumps(detail)

    advertiser_notices = [
        n for n in rows(sm, Notification) if n.type_key == NotificationType.COMPLAINT_REPLIED.value
    ]
    # In the app for both active members, plus the preference-governed email rows.
    assert sorted((n.recipient_user_id, n.channel) for n in advertiser_notices) == sorted(
        [
            (g.advertiser.id, "in_app"),
            (g.advertiser.id, "transactional_email"),
            (g.viewer.id, "in_app"),
            (g.viewer.id, "transactional_email"),
        ]
    )
    email = render_email_template("complaint_replied", "v1", advertiser_notices[0].payload)
    assert "Terrax Media" in email.subject and "invoice" not in email.text_body

    follow = client.post(
        f"/api/v1/advertiser/complaints/{complaint_id}/messages",
        json={"message": "Thanks, still waiting", "client_request_id": str(uuid4())},
        headers=headers(g.advertiser, settings),
    )
    assert follow.status_code == 200 and follow.json()["status"] == "open"

    resolved = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/messages",
        json={"message": "Invoice corrected.", "client_request_id": str(uuid4()), "resolve": True},
        headers=staff,
    )
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolved_at"] is not None
    assert any(n.type_key == "complaint_resolved" for n in rows(sm, Notification))

    # A complainant message reopens a resolved complaint.
    reopened = client.post(
        f"/api/v1/advertiser/complaints/{complaint_id}/messages",
        json={"message": "Not fixed", "client_request_id": str(uuid4())},
        headers=headers(g.advertiser, settings),
    )
    assert reopened.json()["status"] == "open"
    actions = [e.action for e in rows(sm, AuditEvent) if e.entity_type == "complaint"]
    assert sorted(actions) == sorted(
        [
            "advertiser.complaint.created",
            "admin.complaint.replied",
            "advertiser.complaint.message_added",
            "admin.complaint.replied",
            "advertiser.complaint.message_added",
        ]
    )


def test_email_preference_off_keeps_in_app_only(world) -> None:
    client, sm, settings, g = world

    async def opt_out() -> None:
        async with sm() as session:
            session.add(
                AdvertiserOrganizationNotificationPreference(
                    advertiser_organization_id=g.org.id, transactional_email_enabled=False
                )
            )
            await session.commit()

    asyncio.run(opt_out())
    complaint_id = client.post(
        "/api/v1/advertiser/complaints",
        json=body("account"),
        headers=headers(g.advertiser, settings),
    ).json()["id"]
    client.post(
        f"/api/v1/admin/complaints/{complaint_id}/messages",
        json={"message": "Done", "client_request_id": str(uuid4())},
        headers=headers(g.admin, settings),
    )
    channels = {n.channel for n in rows(sm, Notification) if n.type_key == "complaint_replied"}
    assert channels == {"in_app"}


def test_driver_reply_is_in_app_only_and_driver_follow_up_goes_to_assignee(world) -> None:
    client, sm, settings, g = world
    complaint_id = client.post(
        "/api/v1/driver/complaints", json=body(), headers=headers(g.driver, settings)
    ).json()["id"]
    staff = headers(g.admin, settings)

    assigned = client.patch(
        f"/api/v1/admin/complaints/{complaint_id}",
        json={"assigned_to_user_id": str(g.admin2.id)},
        headers=staff,
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assigned_to_name"] == "Bola Staff"
    assigned_notices = [n for n in rows(sm, Notification) if n.type_key == "complaint_assigned"]
    assert [n.recipient_user_id for n in assigned_notices] == [g.admin2.id]

    client.post(
        f"/api/v1/admin/complaints/{complaint_id}/messages",
        json={"message": "Looking into it", "client_request_id": str(uuid4())},
        headers=staff,
    )
    replied = [n for n in rows(sm, Notification) if n.type_key == "complaint_replied"]
    assert [(n.recipient_user_id, n.channel) for n in replied] == [(g.driver.id, "in_app")]

    before = len([n for n in rows(sm, Notification) if n.type_key == "complaint_received"])
    client.post(
        f"/api/v1/driver/complaints/{complaint_id}/messages",
        json={"message": "Any news?", "client_request_id": str(uuid4())},
        headers=headers(g.driver, settings),
    )
    received = [n for n in rows(sm, Notification) if n.type_key == "complaint_received"]
    assert len(received) == before + 1
    assert received[-1].recipient_user_id == g.admin2.id or any(
        n.recipient_user_id == g.admin2.id for n in received[before:]
    )
    assert {n.recipient_user_id for n in received[before:]} == {g.admin2.id}

    mine = client.get(
        "/api/v1/admin/complaints",
        params={"assigned_to_me": "true", "party": "driver"},
        headers=headers(g.admin2, settings),
    )
    assert mine.json()["total"] == 1


def test_staff_patch_status_assignment_noop_and_invalid_assignee(world) -> None:
    client, sm, settings, g = world
    complaint_id = client.post(
        "/api/v1/driver/complaints", json=body(), headers=headers(g.driver, settings)
    ).json()["id"]
    staff = headers(g.admin, settings)
    audits = lambda: len([e for e in rows(sm, AuditEvent) if e.entity_type == "complaint"])  # noqa: E731
    base = audits()

    noop = client.patch(f"/api/v1/admin/complaints/{complaint_id}", json={}, headers=staff)
    assert noop.status_code == 200 and audits() == base
    same = client.patch(
        f"/api/v1/admin/complaints/{complaint_id}", json={"status": "open"}, headers=staff
    )
    assert same.status_code == 200 and audits() == base

    for bad in (g.driver.id, uuid4()):
        invalid = client.patch(
            f"/api/v1/admin/complaints/{complaint_id}",
            json={"assigned_to_user_id": str(bad)},
            headers=staff,
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "COMPLAINT_ASSIGNEE_INVALID"

    # Self-assignment writes an audit but no assignment notice to the actor.
    mine = client.patch(
        f"/api/v1/admin/complaints/{complaint_id}",
        json={"assigned_to_user_id": str(g.admin.id)},
        headers=staff,
    )
    assert mine.json()["assigned_to_user_id"] == str(g.admin.id)
    assert not [n for n in rows(sm, Notification) if n.type_key == "complaint_assigned"]

    resolved = client.patch(
        f"/api/v1/admin/complaints/{complaint_id}", json={"status": "resolved"}, headers=staff
    )
    assert resolved.json()["status"] == "resolved"
    assert [
        n.recipient_user_id for n in rows(sm, Notification) if n.type_key == "complaint_resolved"
    ] == [g.driver.id]
    cleared = client.patch(
        f"/api/v1/admin/complaints/{complaint_id}",
        json={"status": "open", "assigned_to_user_id": None},
        headers=staff,
    )
    assert cleared.json()["status"] == "open"
    assert cleared.json()["assigned_to_user_id"] is None
    assert cleared.json()["resolved_at"] is None
    updated = [e for e in rows(sm, AuditEvent) if e.action == "admin.complaint.updated"]
    assert len(updated) == 3
    assert all("body" not in json.dumps(e.event_metadata) for e in updated)


def test_unknown_complaint_ids_are_404_everywhere(world) -> None:
    client, sm, settings, g = world
    missing = uuid4()
    staff = headers(g.admin, settings)
    calls = [
        client.patch(f"/api/v1/admin/complaints/{missing}", json={}, headers=staff),
        client.patch(
            f"/api/v1/admin/complaints/{missing}",
            json={"assigned_to_user_id": str(uuid4())},
            headers=staff,
        ),
        client.get(f"/api/v1/admin/complaints/{missing}", headers=staff),
        client.post(
            f"/api/v1/admin/complaints/{missing}/messages",
            json={"message": "x", "client_request_id": str(uuid4())},
            headers=staff,
        ),
        client.get(f"/api/v1/driver/complaints/{missing}", headers=headers(g.driver, settings)),
    ]
    assert [c.status_code for c in calls] == [404] * len(calls)
    assert {c.json()["error"]["code"] for c in calls} == {"COMPLAINT_NOT_FOUND"}


def test_message_limit_and_follow_up_replay(world, monkeypatch) -> None:
    client, sm, settings, g = world
    monkeypatch.setattr(complaint_service, "MESSAGE_LIMIT", 3)
    complaint_id = client.post(
        "/api/v1/driver/complaints", json=body(), headers=headers(g.driver, settings)
    ).json()["id"]
    follow = {"message": "second", "client_request_id": str(uuid4())}
    url = f"/api/v1/driver/complaints/{complaint_id}/messages"
    assert client.post(url, json=follow, headers=headers(g.driver, settings)).status_code == 200
    assert client.post(url, json=follow, headers=headers(g.driver, settings)).status_code == 200
    conflict = client.post(
        url, json={**follow, "message": "changed"}, headers=headers(g.driver, settings)
    )
    assert conflict.json()["error"]["code"] == "COMPLAINT_MESSAGE_REPLAY_CONFLICT"
    staff_reply = client.post(
        f"/api/v1/admin/complaints/{complaint_id}/messages",
        json={"message": "third", "client_request_id": str(uuid4())},
        headers=headers(g.admin, settings),
    )
    assert staff_reply.status_code == 200
    for response in (
        client.post(
            url,
            json={"message": "fourth", "client_request_id": str(uuid4())},
            headers=headers(g.driver, settings),
        ),
        client.post(
            f"/api/v1/admin/complaints/{complaint_id}/messages",
            json={"message": "fourth", "client_request_id": str(uuid4())},
            headers=headers(g.admin, settings),
        ),
    ):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "COMPLAINT_MESSAGE_LIMIT"
    assert count(sm, ComplaintMessage) == 3


def test_message_text_never_reaches_audit_or_notification_payloads(world) -> None:
    client, sm, settings, g = world
    complaint_id = client.post(
        "/api/v1/driver/complaints", json=body(), headers=headers(g.driver, settings)
    ).json()["id"]
    client.post(
        f"/api/v1/admin/complaints/{complaint_id}/messages",
        json={"message": SECRET_TEXT, "client_request_id": str(uuid4()), "resolve": True},
        headers=headers(g.admin, settings),
    )
    # The advertiser path adds the organization id and preference-governed email rows.
    advertiser_complaint = client.post(
        "/api/v1/advertiser/complaints",
        json=body("account"),
        headers=headers(g.advertiser, settings),
    ).json()["id"]
    client.post(
        f"/api/v1/admin/complaints/{advertiser_complaint}/messages",
        json={"message": SECRET_TEXT, "client_request_id": str(uuid4()), "resolve": True},
        headers=headers(g.admin, settings),
    )
    emails = [n for n in rows(sm, Notification) if n.channel == "transactional_email"]
    assert {n.type_key for n in emails} == {"complaint_resolved"}
    for notice in emails:
        rendered = render_email_template(notice.type_key, "v1", notice.payload)
        assert "08011112222" not in rendered.subject + rendered.text_body + rendered.html_body
    for event in rows(sm, AuditEvent):
        assert "08011112222" not in json.dumps(event.event_metadata)
    for notice in rows(sm, Notification):
        assert "08011112222" not in json.dumps(notice.payload)
    for type_key in ("complaint_replied", "complaint_resolved"):
        email = render_email_template(type_key, "v1", {"complaint_id": complaint_id})
        assert "08011112222" not in email.text_body + email.html_body


def test_messages_are_append_only(world) -> None:
    client, sm, settings, g = world
    client.post("/api/v1/driver/complaints", json=body(), headers=headers(g.driver, settings))

    async def tamper(action) -> None:
        async with sm() as session:
            message = await session.scalar(select(ComplaintMessage))
            if action == "update":
                message.body = "rewritten"
            else:
                await session.delete(message)
            await session.flush()

    for action in ("update", "delete"):
        with pytest.raises(ValueError):
            asyncio.run(tamper(action))


def test_suspended_advertiser_user_is_denied(world) -> None:
    client, sm, settings, g = world
    suspended = create_test_user(
        sm,
        email="cs-suspended@example.com",
        role=UserRole.ADVERTISER,
        user_status=UserStatus.SUSPENDED,
    )
    response = client.get("/api/v1/advertiser/complaints", headers=headers(suspended, settings))
    assert response.status_code == 403


def test_feed_renders_complaint_notices_in_plain_words(world) -> None:
    client, sm, settings, g = world
    complaint_id = client.post(
        "/api/v1/driver/complaints", json=body(), headers=headers(g.driver, settings)
    ).json()["id"]
    client.post(
        f"/api/v1/admin/complaints/{complaint_id}/messages",
        json={"message": "Reply", "client_request_id": str(uuid4())},
        headers=headers(g.admin, settings),
    )
    feed = client.get("/api/v1/notifications", headers=headers(g.driver, settings)).json()
    assert [(i["title"], i["body"]) for i in feed["items"]] == [
        ("Reply to your complaint", "Terrax Media replied to your complaint. Open Help to read it.")
    ]
    staff_feed = client.get("/api/v1/notifications", headers=headers(g.admin, settings)).json()
    assert staff_feed["items"][0]["title"] == "Complaint waiting"


def test_data_subject_inventory_counts_complaints_and_messages(world) -> None:
    from sqlalchemy import text

    from app.services.data_subject_inventory import ADDITIONAL_SUBJECT_LINK_RULES

    client, sm, settings, g = world
    complaint_id = client.post(
        "/api/v1/driver/complaints", json=body(), headers=headers(g.driver, settings)
    ).json()["id"]
    client.post(
        f"/api/v1/admin/complaints/{complaint_id}/messages",
        json={"message": "Reply", "client_request_id": str(uuid4())},
        headers=headers(g.admin, settings),
    )
    [rule] = [
        r for r in ADDITIONAL_SUBJECT_LINK_RULES if r.data_class == "customer_service_complaints"
    ]

    async def counted(user_id) -> int:
        async with sm() as session:
            return int(await session.scalar(text(rule.count_query), {"subject_user_id": user_id}))

    assert asyncio.run(counted(g.driver.id)) == 2  # the complaint and its first message
    assert asyncio.run(counted(g.admin.id)) == 1  # the reply the staff member wrote

"""Approved L2-1b admin projections retain identity and existing visibility."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from authorization_matrix import Action, Principal, authorization_inventory
from conftest import (
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
    fetch_audit_events,
)

from app.core.security import create_access_token
from app.models.complaint import Complaint
from app.models.contact import ManualDriverContactTask
from app.models.driver_application import DriverApplication
from app.models.organization import OrganizationMembership
from app.models.user import UserRole, UserStatus
from app.services.contacts import (
    grant_whatsapp_consent,
    set_driver_phone,
    withdraw_whatsapp_consent,
)

PREFIX = "/api/v1/admin"
MEMBERS = PREFIX + "/advertiser-organizations/{organization_id}/members"
READS = [
    MEMBERS,
    PREFIX + "/complaints",
    PREFIX + "/driver-applications",
    PREFIX + "/manual-driver-contact-tasks",
]


def bearer(user, settings):
    token = create_access_token(user.id, settings, session_version=user.session_version)[0]
    return {"Authorization": "Bearer " + token}


def test_members_are_scoped_paged_stably_and_sanitized(db_client, db_sessionmaker, settings):
    admin = create_test_user(db_sessionmaker, email="member-admin@example.com")
    users = [
        create_test_user(
            db_sessionmaker,
            email=f"owner{i}@example.com",
            role=UserRole.ADVERTISER,
            full_name="Same name",
        )
        for i in range(3)
    ]
    org, _ = create_test_organization(db_sessionmaker, name="First company")
    other, _ = create_test_organization(
        db_sessionmaker, name="Other company", owner_user_id=users[2].id
    )

    async def setup():
        async with db_sessionmaker() as session:
            session.add_all(
                [
                    OrganizationMembership(
                        organization_id=org.id, user_id=user.id, role="owner", status=state
                    )
                    for user, state in zip(users[:2], ["active", "disabled"], strict=True)
                ]
            )
            await session.commit()

    asyncio.run(setup())
    headers = bearer(admin, settings)
    before = len(fetch_audit_events(db_sessionmaker))
    response = db_client.get(
        MEMBERS.format(organization_id=org.id), headers=headers, params={"limit": 1, "offset": 1}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2 and data["offset"] == 1 and data["limit"] == 1
    assert data["items"][0]["user"]["id"] == str(sorted(users[:2], key=lambda u: u.id)[1].id)
    assert set(data["items"][0]["user"]) == {
        "id",
        "email",
        "full_name",
        "phone",
        "role",
        "status",
        "must_change_password",
    }
    assert set(data["items"][0]["membership"]) == {"role", "status"}
    all_members = db_client.get(MEMBERS.format(organization_id=org.id), headers=headers).json()[
        "items"
    ]
    assert {m["membership"]["status"] for m in all_members} == {"active", "disabled"}
    assert all(m["user"]["status"] == "active" for m in all_members)
    assert (
        db_client.get(MEMBERS.format(organization_id=other.id), headers=headers).json()["total"]
        == 1
    )
    empty, _ = create_test_organization(db_sessionmaker, name="Empty company")
    assert (
        db_client.get(MEMBERS.format(organization_id=empty.id), headers=headers).json()["items"]
        == []
    )
    assert (
        db_client.get(MEMBERS.format(organization_id=uuid4()), headers=headers).status_code == 404
    )
    assert len(fetch_audit_events(db_sessionmaker)) == before


def test_complaint_filters_combine_before_counts_and_pages(db_client, db_sessionmaker, settings):
    admin = create_test_user(db_sessionmaker, email="complaint-admin@example.com")
    users = [
        create_test_user(
            db_sessionmaker, email=f"complainant{i}@example.com", role=UserRole.ADVERTISER
        )
        for i in range(2)
    ]
    orgs = [create_test_organization(db_sessionmaker, owner_user_id=u.id)[0] for u in users]

    async def setup():
        async with db_sessionmaker() as session:
            session.add_all(
                [
                    Complaint(
                        party="advertiser",
                        raised_by_user_id=users[i].id,
                        advertiser_organization_id=orgs[i].id,
                        category="billing_or_invoice",
                        status="open",
                        client_request_id=uuid4(),
                        last_message_at=datetime.now(UTC),
                    )
                    for i in [0, 0, 1]
                ]
            )
            await session.commit()

    asyncio.run(setup())
    headers = bearer(admin, settings)
    path = PREFIX + "/complaints"
    before = len(fetch_audit_events(db_sessionmaker))
    result = db_client.get(
        path,
        headers=headers,
        params={
            "user_id": str(users[0].id),
            "organization_id": str(orgs[0].id),
            "limit": 1,
            "offset": 1,
            "status": "open",
        },
    ).json()
    assert result["total"] == 2 and len(result["items"]) == 1
    assert result["items"][0]["advertiser_organization_id"] == str(orgs[0].id)
    assert (
        db_client.get(
            path,
            headers=headers,
            params={"user_id": str(users[0].id), "organization_id": str(orgs[1].id)},
        ).json()["total"]
        == 0
    )
    assert (
        db_client.get(path, headers=headers, params={"organization_id": str(orgs[1].id)}).json()[
            "total"
        ]
        == 1
    )
    assert (
        db_client.get(
            path, headers=headers, params={"user_id": str(users[0].id), "status": "answered"}
        ).json()["total"]
        == 0
    )
    assert len(fetch_audit_events(db_sessionmaker)) == before


def test_application_filters_retain_history_search_and_exact_identity(
    db_client, db_sessionmaker, settings
):
    admin = create_test_user(db_sessionmaker, email="application-admin@example.com")
    users = [
        create_test_user(db_sessionmaker, email=f"applicant{i}@example.com", role=UserRole.DRIVER)
        for i in range(2)
    ]
    profiles = [create_test_driver_profile(db_sessionmaker, user_id=u.id) for u in users]

    async def setup():
        async with db_sessionmaker() as session:
            session.add_all(
                [
                    DriverApplication(
                        user_id=u.id,
                        driver_profile_id=p.id,
                        email=u.email,
                        full_name=f"Applicant {i}",
                        status=state,
                        status_reference_sha256=str(i) * 64,
                    )
                    for i, (u, p, state) in enumerate(
                        zip(users, profiles, ["pending", "rejected"], strict=True)
                    )
                ]
            )
            await session.commit()

    asyncio.run(setup())
    headers = bearer(admin, settings)
    path = PREFIX + "/driver-applications"
    before = len(fetch_audit_events(db_sessionmaker))
    result = db_client.get(
        path,
        headers=headers,
        params={
            "user_id": str(users[0].id),
            "driver_profile_id": str(profiles[0].id),
            "q": "Applicant",
        },
    ).json()
    assert result["total"] == 1 and result["items"][0]["user_id"] == str(users[0].id)
    assert "status_reference_sha256" not in str(result)
    assert (
        db_client.get(
            path,
            headers=headers,
            params={"user_id": str(users[0].id), "driver_profile_id": str(profiles[1].id)},
        ).json()["total"]
        == 0
    )
    assert (
        db_client.get(
            path, headers=headers, params={"driver_profile_id": str(profiles[1].id)}
        ).json()["total"]
        == 0
    )
    assert (
        db_client.get(
            path,
            headers=headers,
            params={"driver_profile_id": str(profiles[1].id), "history": "true"},
        ).json()["total"]
        == 1
    )
    assert (
        db_client.get(
            path, headers=headers, params={"user_id": str(users[0].id), "offset": 1}
        ).json()["items"]
        == []
    )
    assert len(fetch_audit_events(db_sessionmaker)) == before


def test_contact_filter_preserves_current_authority_and_completed_history(
    db_client, db_sessionmaker, settings
):
    admin = create_test_user(db_sessionmaker, email="contact-admin@example.com")
    users = [
        create_test_user(
            db_sessionmaker, email=f"contact-driver{i}@example.com", role=UserRole.DRIVER
        )
        for i in range(2)
    ]
    profiles = [create_test_driver_profile(db_sessionmaker, user_id=u.id) for u in users]

    async def setup():
        async with db_sessionmaker() as session:
            for i, (user, profile) in enumerate(zip(users, profiles, strict=True)):
                phone = await set_driver_phone(
                    session, user_id=user.id, phone=f"+234803123456{i}", settings=settings
                )
                phone.verified_at = datetime.now(UTC)
                await session.flush()
                consent = await grant_whatsapp_consent(
                    session,
                    user_id=user.id,
                    purpose="campaign_assignment_offer",
                    notice_version="synthetic-notice-v1",
                )
                for suffix, state in [("open", "open"), ("done", "completed")]:
                    task = ManualDriverContactTask(
                        driver_profile_id=profile.id,
                        phone_version_id=phone.id,
                        consent_id=consent.id,
                        purpose=consent.purpose,
                        event_key=f"synthetic:{i}:{suffix}",
                        status=state,
                        created_at=datetime.now(UTC),
                    )
                    if state == "completed":
                        task.completed_by_user_id = admin.id
                        task.completed_at = datetime.now(UTC)
                        task.completion_outcome = "reached"
                        task.completion_note = "Synthetic completed contact"
                    session.add(task)
                if i == 0:
                    await withdraw_whatsapp_consent(session, user_id=user.id)
            await session.commit()

    asyncio.run(setup())
    headers = bearer(admin, settings)
    path = PREFIX + "/manual-driver-contact-tasks"
    before = len(fetch_audit_events(db_sessionmaker))
    result = db_client.get(
        path, headers=headers, params={"driver_profile_id": str(profiles[0].id)}
    ).json()
    assert result["total"] == 1 and result["items"][0]["status"] == "completed"
    assert (
        db_client.get(
            path,
            headers=headers,
            params={"driver_profile_id": str(profiles[0].id), "history": "true"},
        ).json()["total"]
        == 2
    )
    other = db_client.get(
        path,
        headers=headers,
        params={"driver_profile_id": str(profiles[1].id), "limit": 1, "offset": 1},
    ).json()
    assert other["total"] == 2 and len(other["items"]) == 1
    assert other["items"][0]["driver_profile_id"] == str(profiles[1].id)
    assert (
        db_client.get(path, headers=headers, params={"driver_profile_id": str(uuid4())}).json()[
            "total"
        ]
        == 0
    )
    assert len(fetch_audit_events(db_sessionmaker)) == before


@pytest.mark.parametrize(
    "role,state",
    [
        (UserRole.DRIVER, UserStatus.ACTIVE),
        (UserRole.ADVERTISER, UserStatus.ACTIVE),
        (UserRole.ADMIN, UserStatus.DISABLED),
    ],
)
def test_hub_reads_deny_other_roles_disabled_staff_and_anonymous(
    db_client, db_sessionmaker, settings, role, state
):
    user = create_test_user(
        db_sessionmaker, email="denied@example.com", role=role, user_status=state
    )
    before = len(fetch_audit_events(db_sessionmaker))
    for path in READS:
        concrete = path.replace("{organization_id}", str(uuid4()))
        assert db_client.get(concrete, headers=bearer(user, settings)).status_code == 403
        assert db_client.get(concrete).status_code == 401
    assert len(fetch_audit_events(db_sessionmaker)) == before


def test_hub_read_uuid_bounds_and_generated_authorization(db_client, db_sessionmaker, settings):
    admin = create_test_user(db_sessionmaker, email="bounds@example.com")
    headers = bearer(admin, settings)
    for path, query in [
        (MEMBERS.replace("{organization_id}", "invalid"), {}),
        (PREFIX + "/complaints", {"user_id": "invalid"}),
        (PREFIX + "/complaints", {"organization_id": "invalid"}),
        (PREFIX + "/driver-applications", {"user_id": "invalid"}),
        (PREFIX + "/driver-applications", {"driver_profile_id": "invalid"}),
        (PREFIX + "/manual-driver-contact-tasks", {"driver_profile_id": "invalid"}),
    ]:
        assert db_client.get(path, headers=headers, params=query).status_code == 422
    for query in [{"limit": 0}, {"limit": 101}, {"offset": -1}]:
        assert (
            db_client.get(
                MEMBERS.format(organization_id=uuid4()), headers=headers, params=query
            ).status_code
            == 422
        )
    inventory = {r.path: r for r in authorization_inventory() if r.method == "GET"}
    for path in READS:
        assert (
            inventory[path].principal == Principal.ADMIN and inventory[path].action == Action.READ
        )
        assert "require_admin_user" in inventory[path].dependency_names

"""A identity-filter regression tests; B work-list reads are separately tested."""

import asyncio
from uuid import uuid4

import pytest
from authorization_matrix import Action, Principal, authorization_inventory
from conftest import create_test_driver_profile, create_test_user, fetch_audit_events

from app.core.security import create_access_token
from app.models.driver_application import DriverApplication
from app.models.user import UserRole, UserStatus

PREFIX = "/api/v1/admin"
READS = [PREFIX + "/driver-applications"]


def bearer(user, settings):
    token = create_access_token(user.id, settings, session_version=user.session_version)[0]
    return {"Authorization": "Bearer " + token}


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
        (PREFIX + "/driver-applications", {"user_id": "invalid"}),
        (PREFIX + "/driver-applications", {"driver_profile_id": "invalid"}),
    ]:
        assert db_client.get(path, headers=headers, params=query).status_code == 422
    inventory = {r.path: r for r in authorization_inventory() if r.method == "GET"}
    for path in READS:
        assert (
            inventory[path].principal == Principal.ADMIN and inventory[path].action == Action.READ
        )
        assert "require_admin_user" in inventory[path].dependency_names

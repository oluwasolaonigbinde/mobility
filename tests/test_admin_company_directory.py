"""L2-1a's sole new endpoint: a bounded staff-only company directory."""

import pytest
from authorization_matrix import Action, Principal, authorization_inventory
from conftest import auth_headers, create_test_organization, create_test_user, fetch_audit_events

from app.core.security import create_access_token
from app.models.user import UserRole, UserStatus

PATH = "/api/v1/admin/advertiser-organizations"
PASSWORD = "long-secure-password"


def test_directory_search_pagination_projection_and_read_only(db_client, db_sessionmaker):
    create_test_user(db_sessionmaker, email="staff@example.com", password=PASSWORD)
    organizations = [
        create_test_organization(db_sessionmaker, name=name)[0]
        for name in ["Alpha", "Beta", "Beta % media"]
    ]
    headers = auth_headers(db_client, "staff@example.com", PASSWORD)
    before = len(fetch_audit_events(db_sessionmaker))
    response = db_client.get(PATH, headers=headers, params={"q": "beta", "limit": 1, "offset": 1})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["limit"] == 1 and data["offset"] == 1
    assert data["items"][0]["id"] == str(organizations[2].id)
    assert set(data["items"][0]) == {
        "id",
        "name",
        "billing_email",
        "country_code",
        "currency",
        "status",
    }
    assert len(fetch_audit_events(db_sessionmaker)) == before
    literal = db_client.get(PATH, headers=headers, params={"q": "%"}).json()
    assert literal["total"] == 1 and literal["items"][0]["name"] == "Beta % media"
    assert db_client.get(PATH, headers=headers, params={"q": "absent"}).json()["total"] == 0
    assert db_client.get(PATH, headers=headers, params={"offset": 100}).json()["items"] == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"q": "x" * 121}])
def test_directory_rejects_unbounded_queries(db_client, db_sessionmaker, params):
    create_test_user(db_sessionmaker, email="staff@example.com", password=PASSWORD)
    assert (
        db_client.get(
            PATH, headers=auth_headers(db_client, "staff@example.com", PASSWORD), params=params
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "role,status,expected",
    [
        (UserRole.DRIVER, UserStatus.ACTIVE, 403),
        (UserRole.ADVERTISER, UserStatus.ACTIVE, 403),
        (UserRole.ADMIN, UserStatus.DISABLED, 403),
    ],
)
def test_directory_denies_wrong_role_or_disabled_staff(
    db_client, db_sessionmaker, settings, role, status, expected
):
    user = create_test_user(
        db_sessionmaker, email="denied@example.com", role=role, user_status=status
    )
    token = create_access_token(user.id, settings, session_version=user.session_version)[0]
    before = len(fetch_audit_events(db_sessionmaker))
    response = db_client.get(PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == expected
    assert len(fetch_audit_events(db_sessionmaker)) == before


def test_directory_anonymous_denial_and_generated_matrix(db_client):
    assert db_client.get(PATH).status_code == 401
    route = next(r for r in authorization_inventory() if r.key == ("GET", PATH))
    assert route.principal == Principal.ADMIN and route.action == Action.READ
    assert "require_admin_user" in route.dependency_names

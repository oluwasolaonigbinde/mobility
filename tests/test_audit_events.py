from conftest import auth_headers, create_test_user, fetch_auth_audit_events

from app.models.user import UserRole


def test_login_success_and_failure_audit_rows_survive_session_close(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="audit-login@example.com", role=UserRole.ADMIN)
    failed = db_client.post(
        "/api/v1/auth/login",
        json={"email": "audit-login@example.com", "password": "wrong"},
    )
    assert failed.status_code == 401
    headers = auth_headers(db_client, "audit-login@example.com")

    events = fetch_auth_audit_events(db_sessionmaker)
    assert sorted(event.action for event in events) == [
        "auth.login.failed",
        "auth.login.succeeded",
    ]

    listed = db_client.get(
        "/api/v1/admin/audit-events?action=auth.login.succeeded",
        headers=headers,
    )
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1
    assert listed.json()["items"][0]["actor_email"] == "audit-login@example.com"


def test_audit_event_list_is_admin_only(db_client, db_sessionmaker) -> None:
    create_test_user(
        db_sessionmaker,
        email="audit-advertiser@example.com",
        role=UserRole.ADVERTISER,
    )
    response = db_client.get(
        "/api/v1/admin/audit-events",
        headers=auth_headers(db_client, "audit-advertiser@example.com"),
    )
    assert response.status_code == 403

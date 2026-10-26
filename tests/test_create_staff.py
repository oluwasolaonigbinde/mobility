"""REQ-208: the first staff account is created from the server shell."""

from conftest import create_test_user, fetch_audit_events, fetch_user_by_email

from app.models.user import UserRole, UserStatus
from app.operations.create_staff import main


def test_creates_an_active_admin_with_a_one_time_password(
    db_client, db_sessionmaker, settings, capsys
):
    code = main(
        ["--email", "First.Staff@Terrax.example", "--name", "  Ada Obi "],
        sessionmaker=db_sessionmaker,
        settings=settings,
    )
    assert code == 0
    printed = capsys.readouterr().out
    password = printed.split("Temporary password (shown once): ")[1].splitlines()[0]
    assert len(password) >= settings.password_min_length

    user = fetch_user_by_email(db_sessionmaker, "first.staff@terrax.example")
    assert user is not None
    assert (user.role, user.status, user.full_name) == (
        UserRole.ADMIN,
        UserStatus.ACTIVE,
        "Ada Obi",
    )
    assert user.must_change_password is True
    assert password not in user.password_hash
    [event] = [e for e in fetch_audit_events(db_sessionmaker) if e.action == "admin.user.created"]
    assert event.actor_user_id is None
    assert event.event_metadata["source"] == "cli"
    assert password not in str(event.event_metadata)

    login = db_client.post(
        "/api/v1/auth/login",
        json={"email": "first.staff@terrax.example", "password": password},
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["must_change_password"] is True


def test_refuses_an_email_that_already_has_an_account(db_sessionmaker, settings, capsys):
    existing = create_test_user(db_sessionmaker, email="taken@terrax.example")
    before = existing.password_hash

    code = main(
        ["--email", "TAKEN@terrax.example", "--name", "Someone Else"],
        sessionmaker=db_sessionmaker,
        settings=settings,
    )

    assert code == 1
    output = capsys.readouterr()
    assert "Not created" in output.err
    assert "Temporary password" not in output.out
    assert fetch_user_by_email(db_sessionmaker, "taken@terrax.example").password_hash == before
    assert not [e for e in fetch_audit_events(db_sessionmaker) if e.action == "admin.user.created"]


def test_refuses_an_invalid_email(db_sessionmaker, settings, capsys):
    assert (
        main(
            ["--email", "not-an-email", "--name", "Ada"],
            sessionmaker=db_sessionmaker,
            settings=settings,
        )
        == 1
    )
    assert "Not created" in capsys.readouterr().err

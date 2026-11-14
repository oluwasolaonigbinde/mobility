"""REQ-315: active-only sign-in (F4), no public status route (F5), driver-safe reads (N5)."""

import asyncio

import pytest
from conftest import auth_headers, create_test_user
from pydantic import ValidationError
from test_trip_processing import PASSWORD, build_graph

from app.models.campaign_assignment import CampaignAssignment
from app.models.user import User, UserRole, UserStatus
from app.schemas.users import UserCreate

STAFF_ONLY = {"notes", "metadata", "assigned_by_user_id", "activity_flags"}
STAFF_EVENT_ONLY = {"actor_user_id", "metadata"}


def _set_status(db, user_id, value):
    async def run():
        async with db() as session:
            (await session.get(User, user_id)).status = value
            await session.commit()

    asyncio.run(run())


# --- F4 ---------------------------------------------------------------------


@pytest.mark.parametrize("role", [UserRole.DRIVER, UserRole.ADVERTISER])
def test_f4_invited_accounts_cannot_sign_in(db_client, db_sessionmaker, role):
    user = create_test_user(
        db_sessionmaker,
        email=f"f4-invited-{role.value}@example.com",
        role=role,
        user_status=UserStatus.INVITED,
    )
    response = db_client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "long-secure-password"}
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "USER_NOT_ACTIVE"


@pytest.mark.parametrize("role", [UserRole.DRIVER, UserRole.ADVERTISER])
def test_f4_a_session_stops_working_once_the_account_is_not_active(
    db_client, db_sessionmaker, role
):
    user = create_test_user(
        db_sessionmaker, email=f"f4-session-{role.value}@example.com", role=role
    )
    headers = auth_headers(db_client, user.email)
    assert db_client.get("/api/v1/me", headers=headers).status_code == 200
    _set_status(db_sessionmaker, user.id, UserStatus.INVITED.value)
    response = db_client.get("/api/v1/me", headers=headers)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "USER_NOT_ACTIVE"


@pytest.mark.parametrize("status", ["invited", "suspended", "disabled"])
def test_f4_staff_create_a_driver_only_as_active(status):
    base = dict(email="new-driver@example.com", password="x" * 12, full_name="New Driver")
    with pytest.raises(ValidationError):
        UserCreate(**base, role=UserRole.DRIVER, status=status)
    assert UserCreate(**base, role=UserRole.DRIVER, status="active").status == "active"


# --- F5 ---------------------------------------------------------------------


def test_f5_public_application_status_route_is_gone(client):
    response = client.get("/api/v1/auth/driver-application-status/CV-ABCDEF")
    assert response.status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert not [path for path in paths if "driver-application-status" in path]


# --- N5 ---------------------------------------------------------------------


DRIVER_ASSIGNMENT_ROUTES = [
    ("get", "/api/v1/driver/campaign-assignments", "DriverCampaignAssignmentListResponse"),
    ("get", "/api/v1/driver/campaign-assignments/active", "DriverActiveCampaignAssignment"),
    ("get", "/api/v1/driver/campaign-assignments/{assignment_id}", "DriverCampaignAssignmentRead"),
    (
        "post",
        "/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        "DriverCampaignAssignmentRead",
    ),
    (
        "post",
        "/api/v1/driver/campaign-assignments/{assignment_id}/decline",
        "DriverCampaignAssignmentRead",
    ),
    (
        "post",
        "/api/v1/driver/campaign-assignments/{assignment_id}/deactivate",
        "DriverCampaignAssignmentRead",
    ),
    (
        "get",
        "/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence",
        "DriverInstallationEvidenceList",
    ),
    (
        "post",
        "/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence",
        "DriverInstallationEvidenceRead",
    ),
]


def _ref(operation):
    for code in ("200", "201"):
        if code in operation["responses"]:
            schema = operation["responses"][code]["content"]["application/json"]["schema"]
            return schema["$ref"].rsplit("/", 1)[-1]
    raise AssertionError(operation["responses"])


@pytest.mark.parametrize("method, path, expected", DRIVER_ASSIGNMENT_ROUTES)
def test_n5_every_driver_assignment_response_uses_the_driver_model(client, method, path, expected):
    document = client.get("/openapi.json").json()
    assert _ref(document["paths"][path][method]) == expected


def test_n5_driver_models_carry_no_staff_fields(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert not STAFF_ONLY & set(schemas["DriverCampaignAssignmentRead"]["properties"])
    assert not STAFF_EVENT_ONLY & set(schemas["DriverCampaignActivationEventRead"]["properties"])
    assert "reviewed_by_user_id" not in schemas["DriverInstallationEvidenceRead"]["properties"]
    # The navigation current-job summary carries the same driver model.
    current_job = str(schemas["DriverCurrentJob"]["properties"]["assignment"])
    assert "#/components/schemas/DriverCampaignAssignmentRead" in current_job
    # Staff reads are unchanged.
    assert STAFF_ONLY <= set(schemas["CampaignAssignmentRead"]["properties"])
    assert STAFF_EVENT_ONLY <= set(schemas["CampaignActivationEventRead"]["properties"])
    assert "reviewed_by_user_id" in schemas["InstallationEvidenceRead"]["properties"]


def test_n5_driver_reads_omit_staff_notes_and_actor_ids(db_client, db_sessionmaker):
    graph = build_graph(db_sessionmaker, "n5-driver")

    async def annotate():
        from app.models.campaign_assignment import CampaignActivationEventType
        from app.services.campaign_assignments import create_activation_event

        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, graph.assignment.id)
            assignment.notes = "staff only: check the wrap edge"
            assignment.assignment_metadata = {"ops": "internal"}
            await create_activation_event(
                session,
                assignment=assignment,
                actor_user_id=graph.admin.id,
                event_type=CampaignActivationEventType.ACTIVATED,
                previous_status="accepted",
                metadata={"staff": "internal"},
                occurred_at=assignment.activated_at,
            )
            await session.commit()

    asyncio.run(annotate())
    driver = auth_headers(db_client, graph.driver.email, PASSWORD)
    admin = auth_headers(db_client, graph.admin.email, PASSWORD)
    one = db_client.get(
        f"/api/v1/driver/campaign-assignments/{graph.assignment.id}", headers=driver
    )
    listed = db_client.get("/api/v1/driver/campaign-assignments", headers=driver)
    active = db_client.get("/api/v1/driver/campaign-assignments/active", headers=driver)
    current = db_client.get("/api/v1/driver/current-job", headers=driver)
    assert {one.status_code, listed.status_code, active.status_code, current.status_code} == {200}
    for body in (
        one.json(),
        listed.json()["items"][0],
        active.json()["assignment"],
        current.json()["assignment"],
    ):
        assert not STAFF_ONLY & set(body), body
        for event in body.get("events") or []:
            assert not STAFF_EVENT_ONLY & set(event), event
        assert "staff only" not in str(body) and "internal" not in str(body)
    assert one.json()["events"], "the staff event is still listed for the driver"
    staff = db_client.get(
        f"/api/v1/admin/campaign-assignments/{graph.assignment.id}", headers=admin
    )
    assert staff.status_code == 200
    assert staff.json()["notes"] == "staff only: check the wrap edge"
    assert staff.json()["events"][-1]["actor_user_id"] == str(graph.admin.id)

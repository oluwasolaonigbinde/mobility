"""Route-generated authentication and authorization denial matrix (TST-005)."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from authorization_matrix import (
    APPLICANT_ROUTES,
    MACHINE_ROUTES,
    PUBLIC_ROUTES,
    Action,
    Principal,
    authorization_inventory,
    concrete_path,
    request_payload,
)
from conftest import (
    create_test_campaign,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
)
from pydantic import SecretStr
from sqlalchemy import func, select

from app.adapters.disbursement import FakeDisbursementAdapter
from app.adapters.payments import FakePaymentGatewayAdapter
from app.api.v1.billing import get_payment_gateway_adapter
from app.api.v1.dependencies import get_payment_event_enqueuer, get_storage_provider
from app.api.v1.disbursements import get_disbursement_adapter
from app.core.security import create_access_token
from app.db.base import Base
from app.models.audit import AuditEvent
from app.models.organization import MembershipRole, MembershipStatus, OrganizationMembership
from app.models.user import UserRole, UserStatus

PASSWORD = "long-secure-password"
OPAQUE_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(user, settings, **kwargs) -> str:
    return create_access_token(
        user.id,
        settings,
        session_version=kwargs.pop("session_version", user.session_version),
        **kwargs,
    )[0]


def _audit_count(db_sessionmaker) -> int:
    async def count() -> int:
        async with db_sessionmaker() as session:
            return int(await session.scalar(select(func.count()).select_from(AuditEvent)) or 0)

    return asyncio.run(count())


def _database_fingerprint(db_sessionmaker) -> dict[str, int]:
    async def fingerprint() -> dict[str, int]:
        async with db_sessionmaker() as session:
            return {
                table.name: int(await session.scalar(select(func.count()).select_from(table)) or 0)
                for table in Base.metadata.sorted_tables
            }

    return asyncio.run(fingerprint())


def _request(client, route, headers):
    return client.request(
        route.method,
        concrete_path(route.path, opaque_id=OPAQUE_ID),
        headers={
            **headers,
            "Idempotency-Key": "ffffffff-ffff-4fff-8fff-ffffffffffff",
            "If-Match": "1",
        },
        json=request_payload(route),
    )


def test_every_api_route_has_a_principal_tenant_resource_and_action_classification() -> None:
    inventory = authorization_inventory()
    keys = {route.key for route in inventory}

    assert len(keys) == len(inventory)
    assert PUBLIC_ROUTES <= keys
    assert APPLICANT_ROUTES <= keys
    assert MACHINE_ROUTES <= keys
    assert {route.principal for route in inventory} == set(Principal)
    assert {route.action for route in inventory} == set(Action)
    assert all(route.tenant_scope and route.resource for route in inventory)


def test_generated_bearer_denial_matrix_has_no_misleading_audit_effects(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    db_client = postgis_db_client
    db_sessionmaker = postgis_db_sessionmaker
    users = {
        Principal.ADMIN: create_test_user(
            db_sessionmaker, email="matrix-admin@example.com", role=UserRole.ADMIN
        ),
        Principal.ADVERTISER: create_test_user(
            db_sessionmaker, email="matrix-advertiser@example.com", role=UserRole.ADVERTISER
        ),
        Principal.DRIVER: create_test_user(
            db_sessionmaker, email="matrix-driver@example.com", role=UserRole.DRIVER
        ),
    }
    disabled = create_test_user(
        db_sessionmaker,
        email="matrix-disabled@example.com",
        role=UserRole.ADMIN,
        user_status=UserStatus.DISABLED,
    )
    active_tokens = {principal: _token(user, settings) for principal, user in users.items()}
    disabled_token = _token(disabled, settings)
    revoked_token = _token(users[Principal.ADMIN], settings, session_version=999)
    expired_token = _token(
        users[Principal.ADMIN],
        settings,
        auth_time=datetime.now(UTC) - timedelta(hours=2),
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    protected = [
        route
        for route in authorization_inventory()
        if route.principal
        in {Principal.ADMIN, Principal.ADVERTISER, Principal.DRIVER, Principal.AUTHENTICATED}
    ]
    before = _database_fingerprint(db_sessionmaker)

    for route in protected:
        absent = _request(db_client, route, {})
        invalid = _request(db_client, route, _bearer("not-a-jwt"))
        revoked = _request(db_client, route, _bearer(revoked_token))
        expired = _request(db_client, route, _bearer(expired_token))
        contained = _request(db_client, route, _bearer(disabled_token))

        assert (absent.status_code, absent.json()["error"]["code"]) == (
            401,
            "AUTHENTICATION_REQUIRED",
        ), route.key
        assert (invalid.status_code, invalid.json()["error"]["code"]) == (
            401,
            "INVALID_TOKEN",
        ), route.key
        assert (revoked.status_code, revoked.json()["error"]["code"]) == (
            401,
            "SESSION_REVOKED",
        ), route.key
        assert (expired.status_code, expired.json()["error"]["code"]) == (
            401,
            "INVALID_TOKEN",
        ), route.key
        assert (contained.status_code, contained.json()["error"]["code"]) == (
            403,
            "USER_NOT_ACTIVE",
        ), route.key

        if route.principal is not Principal.AUTHENTICATED:
            for wrong_principal in (
                principal
                for principal in (Principal.ADMIN, Principal.ADVERTISER, Principal.DRIVER)
                if principal is not route.principal
            ):
                wrong_role = _request(
                    db_client,
                    route,
                    _bearer(active_tokens[wrong_principal]),
                )
                assert (wrong_role.status_code, wrong_role.json()["error"]["code"]) == (
                    403,
                    "FORBIDDEN_ROLE",
                ), (route.key, wrong_principal)

    assert _database_fingerprint(db_sessionmaker) == before


def test_generated_right_role_guessed_read_matrix_hides_every_parameterized_resource(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    db_client = postgis_db_client
    db_sessionmaker = postgis_db_sessionmaker
    users = {
        Principal.ADMIN: create_test_user(
            db_sessionmaker, email="resource-admin@example.com", role=UserRole.ADMIN
        ),
        Principal.ADVERTISER: create_test_user(
            db_sessionmaker,
            email="resource-advertiser@example.com",
            role=UserRole.ADVERTISER,
        ),
        Principal.DRIVER: create_test_user(
            db_sessionmaker, email="resource-driver@example.com", role=UserRole.DRIVER
        ),
    }
    users[Principal.AUTHENTICATED] = users[Principal.ADMIN]
    create_test_organization(
        db_sessionmaker,
        name="Resource matrix advertiser",
        owner_user_id=users[Principal.ADVERTISER].id,
    )
    create_test_driver_profile(db_sessionmaker, user_id=users[Principal.DRIVER].id)
    tokens = {principal: _token(user, settings) for principal, user in users.items()}
    routes = [
        route
        for route in authorization_inventory()
        if route.method == "GET" and "{" in route.path and route.principal in users
    ]
    assert routes
    query = {
        "bbox": "3.35,6.43,3.47,6.56",
        "currency": "NGN",
        "start_date": "2026-01-01",
        "end_date": "2026-01-02",
        "start_at": "2026-01-01T00:00:00Z",
        "end_at": "2026-01-02T00:00:00Z",
        "limit": "25",
        "offset": "0",
    }
    before = _database_fingerprint(db_sessionmaker)

    for route in routes:
        response = db_client.get(
            concrete_path(route.path, opaque_id=OPAQUE_ID),
            headers=_bearer(tokens[route.principal]),
            params=query,
        )
        assert response.status_code == 404, (route.key, response.status_code, response.text)

    assert _database_fingerprint(db_sessionmaker) == before


def test_generated_right_role_guessed_mutation_matrix_hides_every_parameterized_resource(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    db_client = postgis_db_client
    db_sessionmaker = postgis_db_sessionmaker
    users = {
        Principal.ADMIN: create_test_user(
            db_sessionmaker, email="mutation-admin@example.com", role=UserRole.ADMIN
        ),
        Principal.ADVERTISER: create_test_user(
            db_sessionmaker,
            email="mutation-advertiser@example.com",
            role=UserRole.ADVERTISER,
        ),
        Principal.DRIVER: create_test_user(
            db_sessionmaker, email="mutation-driver@example.com", role=UserRole.DRIVER
        ),
    }
    users[Principal.AUTHENTICATED] = users[Principal.ADMIN]
    create_test_organization(
        db_sessionmaker,
        name="Mutation matrix advertiser",
        owner_user_id=users[Principal.ADVERTISER].id,
    )
    create_test_driver_profile(db_sessionmaker, user_id=users[Principal.DRIVER].id)
    settings.phone_operator_external_approved = True
    tokens = {principal: _token(user, settings) for principal, user in users.items()}
    routes = [
        route
        for route in authorization_inventory()
        if route.method != "GET" and "{" in route.path and route.principal in users
    ]
    assert routes
    before = _database_fingerprint(db_sessionmaker)

    for route in routes:
        response = _request(db_client, route, _bearer(tokens[route.principal]))
        assert response.status_code == 404, (route.key, response.status_code, response.text)

    assert _database_fingerprint(db_sessionmaker) == before


def test_machine_callbacks_reject_forged_authority_without_effects(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    db_client = postgis_db_client
    db_sessionmaker = postgis_db_sessionmaker
    payment = FakePaymentGatewayAdapter()
    disbursement = FakeDisbursementAdapter()

    class ForbiddenEnqueuer:
        async def enqueue_payment_event(self, _event_id) -> None:
            raise AssertionError("denied callback reached the payment job boundary")

    db_client.app.dependency_overrides[get_payment_gateway_adapter] = lambda: payment
    db_client.app.dependency_overrides[get_disbursement_adapter] = lambda: disbursement
    db_client.app.dependency_overrides[get_payment_event_enqueuer] = ForbiddenEnqueuer
    settings.email_receipt_signing_secret = SecretStr("matrix-email-secret")
    settings.email_receipt_key_id = "matrix-v1"
    callback_payload = {
        "provider_event_id": "matrix-event",
        "provider_message_id": "matrix-message",
        "outcome": "delivered",
        "occurred_at": "2026-09-02T12:00:00Z",
    }
    before = _database_fingerprint(db_sessionmaker)

    responses = {
        ("POST", "/api/v1/webhooks/payments"): db_client.post(
            "/api/v1/webhooks/payments",
            content=b"{}",
            headers={"X-Payment-Signature": "forged"},
        ),
        ("POST", "/api/v1/notifications/email/delivery-receipts"): db_client.post(
            "/api/v1/notifications/email/delivery-receipts",
            json=callback_payload,
            headers={
                "X-Email-Receipt-Signature": "forged",
                "X-Email-Receipt-Key-Id": "matrix-v1",
            },
        ),
        ("POST", "/api/v1/admin/payout-batches/provider-webhook"): db_client.post(
            "/api/v1/admin/payout-batches/provider-webhook",
            content=b"{}",
            headers={"X-Provider-Signature": "forged"},
        ),
    }

    assert set(responses) == MACHINE_ROUTES
    assert all(response.status_code == 401 for response in responses.values()), {
        key: (response.status_code, response.text) for key, response in responses.items()
    }
    assert payment.checkout_calls == []
    assert disbursement.calls == []
    assert disbursement.poll_calls == []
    assert _database_fingerprint(db_sessionmaker) == before


def test_generated_advertiser_campaign_reads_hide_foreign_guessed_and_stale_membership(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    db_client = postgis_db_client
    db_sessionmaker = postgis_db_sessionmaker
    owner = create_test_user(
        db_sessionmaker,
        email="matrix-tenant-owner@example.com",
        role=UserRole.ADVERTISER,
    )
    own_organization, membership = create_test_organization(
        db_sessionmaker,
        name="Matrix own tenant",
        owner_user_id=owner.id,
    )
    foreign_organization, _ = create_test_organization(
        db_sessionmaker,
        name="Matrix foreign tenant",
    )
    own_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=own_organization.id,
        created_by_user_id=owner.id,
    )
    foreign_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=foreign_organization.id,
        created_by_user_id=owner.id,
        name="Foreign campaign",
    )
    routes = [
        route
        for route in authorization_inventory()
        if route.method == "GET"
        and route.principal is Principal.ADVERTISER
        and "{campaign_id}" in route.path
        and route.path.count("{") == 1
    ]
    assert routes
    headers = _bearer(_token(owner, settings))
    query = {
        "bbox": "3.35,6.43,3.47,6.56",
        "currency": "NGN",
        "start_date": "2026-01-01",
        "end_date": "2026-01-02",
        "start_at": "2026-01-01T00:00:00Z",
        "end_at": "2026-01-02T00:00:00Z",
        "limit": "25",
        "offset": "0",
    }
    before = _audit_count(db_sessionmaker)

    for route in routes:
        foreign = db_client.get(
            route.path.replace("{campaign_id}", str(foreign_campaign.id)),
            headers=headers,
            params=query,
        )
        guessed = db_client.get(
            route.path.replace("{campaign_id}", OPAQUE_ID),
            headers=headers,
            params=query,
        )
        assert foreign.status_code == 404, (route.key, foreign.text)
        assert guessed.status_code == 404, (route.key, guessed.text)

    async def disable_membership() -> None:
        async with db_sessionmaker() as session:
            stored = await session.get(OrganizationMembership, membership.id)
            assert stored is not None
            stored.status = MembershipStatus.DISABLED
            await session.commit()

    asyncio.run(disable_membership())
    for route in routes:
        stale = db_client.get(
            route.path.replace("{campaign_id}", str(own_campaign.id)),
            headers=headers,
            params=query,
        )
        assert stale.status_code == 404, (route.key, stale.text)

    assert _audit_count(db_sessionmaker) == before


@pytest.mark.parametrize(
    ("membership_role", "membership_status", "expected_status"),
    [
        (MembershipRole.OWNER, MembershipStatus.ACTIVE, 201),
        (MembershipRole.MANAGER, MembershipStatus.ACTIVE, 201),
        (MembershipRole.VIEWER, MembershipStatus.ACTIVE, 403),
        (MembershipRole.MANAGER, MembershipStatus.DISABLED, 404),
    ],
)
def test_advertiser_write_capability_matrix(
    membership_role,
    membership_status,
    expected_status,
    postgis_db_client,
    postgis_db_sessionmaker,
    settings,
) -> None:
    db_client = postgis_db_client
    db_sessionmaker = postgis_db_sessionmaker
    actor = create_test_user(
        db_sessionmaker,
        email=f"matrix-{membership_role}-{membership_status}@example.com",
        role=UserRole.ADVERTISER,
    )
    create_test_organization(
        db_sessionmaker,
        name=f"Matrix {membership_role} {membership_status}",
        owner_user_id=actor.id,
        membership_role=membership_role,
        membership_status=membership_status,
    )
    before = _audit_count(db_sessionmaker)
    response = db_client.post(
        "/api/v1/advertiser/campaigns",
        headers=_bearer(_token(actor, settings)),
        json={
            "name": "Authorization matrix campaign",
            "description": "Capability boundary",
            "start_at": "2026-10-01T00:00:00Z",
            "end_at": "2026-10-31T00:00:00Z",
            "budget_amount": "1000.00",
            "currency": "NGN",
        },
    )

    assert response.status_code == expected_status, response.text
    if expected_status == 403:
        assert response.json()["error"]["code"] == "ADVERTISER_MEMBERSHIP_WRITE_FORBIDDEN"
    if expected_status == 404:
        assert response.json()["error"]["code"] == "ADVERTISER_ORGANIZATION_NOT_FOUND"
    expected_audit_delta = 1 if expected_status == 201 else 0
    assert _audit_count(db_sessionmaker) == before + expected_audit_delta


@pytest.mark.parametrize("route_key", sorted(APPLICANT_ROUTES))
def test_applicant_capability_routes_reject_invalid_capability_without_audit_effect(
    route_key, postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    db_client = postgis_db_client
    db_sessionmaker = postgis_db_sessionmaker
    settings.driver_registration_enabled = True
    route = next(route for route in authorization_inventory() if route.key == route_key)
    payloads = {
        "/api/v1/auth/driver-onboarding/files/uploads": {
            "application_access_token": "invalid-capability",
            "upload": {
                "client_request_id": str(uuid4()),
                "purpose": "driver_kyc",
                "filename": "photo.png",
                "content_type": "image/png",
                "size_bytes": 4,
                "sha256": "0" * 64,
            },
        },
        "/api/v1/auth/driver-onboarding/files/uploads/{upload_id}/confirm": {
            "application_access_token": "invalid-capability"
        },
        "/api/v1/auth/driver-onboarding/files/{file_id}/status": {
            "application_access_token": "invalid-capability"
        },
        "/api/v1/auth/driver-onboarding/person-payee": {
            "application_access_token": "invalid-capability",
            "client_request_id": str(uuid4()),
            "nin": "12345678901",
            "account_name": "Applicant",
            "account_number": "0123456789",
            "bank_code": "999",
            "driver_license_file_id": str(uuid4()),
            "driver_photo_file_id": str(uuid4()),
            "signed_agreement_file_id": str(uuid4()),
        },
        "/api/v1/auth/driver-onboarding/vehicle": {
            "application_access_token": "invalid-capability",
            "client_request_id": str(uuid4()),
            "plate_number": "ABC-123",
            "plate_country_code": "NG",
            "vehicle_type": "car",
            "registration_file_id": str(uuid4()),
            "insurance_file_id": str(uuid4()),
            "vehicle_photo_file_id": str(uuid4()),
        },
    }

    class ForbiddenStorage:
        def __getattr__(self, name):
            raise AssertionError(f"denied applicant capability reached storage method {name}")

    db_client.app.dependency_overrides[get_storage_provider] = ForbiddenStorage
    before = _database_fingerprint(db_sessionmaker)
    response = db_client.request(
        route.method,
        concrete_path(route.path, opaque_id=OPAQUE_ID),
        json=payloads[route.path],
    )

    assert (response.status_code, response.json()["error"]["code"]) == (
        404,
        "ONBOARDING_ACCESS_INVALID",
    )
    assert _database_fingerprint(db_sessionmaker) == before

import asyncio
from uuid import UUID, uuid4

from conftest import (
    auth_headers,
    create_test_driver_profile,
    create_test_user,
)
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.models.audit import AuditEvent
from app.models.driver import DriverOnboardingStatus
from app.models.payee import PayeeBankAccountVersion
from app.models.user import UserRole


def _graph(db_sessionmaker):
    admin = create_test_user(
        db_sessionmaker,
        email=f"payee-api-admin-{uuid4().hex}@example.com",
        role=UserRole.ADMIN,
    )
    driver = create_test_user(
        db_sessionmaker,
        email=f"payee-api-driver-{uuid4().hex}@example.com",
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    return admin, driver, profile


def test_admin_payee_api_encrypts_reveals_with_no_store_and_audits(
    db_client,
    db_sessionmaker,
) -> None:
    admin, _, profile = _graph(db_sessionmaker)
    headers = auth_headers(db_client, admin.email)

    created = db_client.post(
        f"/api/v1/admin/payees/drivers/{profile.id}",
        headers=headers,
    )
    assert created.status_code == 201
    payee = created.json()
    assert payee["payee_type"] == "driver"
    assert payee["subject_id"] == str(profile.id)

    plaintext = {
        "account_name": "Ada Protected",
        "account_number": "0123456789",
        "bank_code": "058",
        "verification_reference": "provider-evidence-api-00000000000000000001",
        "ignored_secret": "must-not-be-reflected",
    }
    verified = db_client.post(
        f"/api/v1/admin/payees/{payee['id']}/bank-account-versions",
        headers=headers,
        json=plaintext,
    )
    assert verified.status_code == 201
    verified_text = verified.text
    assert plaintext["account_name"] not in verified_text
    assert plaintext["account_number"] not in verified_text
    assert plaintext["verification_reference"] not in verified_text
    assert "ignored_secret" not in verified_text

    revealed = db_client.post(
        f"/api/v1/admin/payees/bank-account-versions/{verified.json()['id']}/reveal",
        headers=headers,
        json={"purpose": "payout_operations"},
    )
    assert revealed.status_code == 200
    assert revealed.headers["cache-control"] == "no-store"
    assert revealed.json() == {
        "account_name": plaintext["account_name"],
        "account_number": plaintext["account_number"],
        "bank_code": plaintext["bank_code"],
    }

    async def inspect() -> tuple[dict, list[AuditEvent]]:
        async with db_sessionmaker() as session:
            stored = await session.get(
                PayeeBankAccountVersion,
                UUID(verified.json()["id"]),
            )
            audits = list(
                (
                    await session.scalars(
                        select(AuditEvent).where(
                            AuditEvent.action.in_(
                                (
                                    "admin.payee.created",
                                    "admin.bank_account.verified",
                                    "admin.bank_account.read",
                                )
                            )
                        )
                    )
                ).all()
            )
            assert stored is not None
            return stored.encrypted_details, audits

    ciphertext, audits = asyncio.run(inspect())
    evidence = str(ciphertext) + str([audit.event_metadata for audit in audits])
    assert plaintext["account_name"] not in evidence
    assert plaintext["account_number"] not in evidence
    assert plaintext["verification_reference"] not in evidence
    assert {audit.action for audit in audits} == {
        "admin.payee.created",
        "admin.bank_account.verified",
        "admin.bank_account.read",
    }
    read_audit = next(audit for audit in audits if audit.action == "admin.bank_account.read")
    assert read_audit.event_metadata["purpose"] == "payout_operations"


def test_payee_api_is_admin_only_and_errors_do_not_reflect_plaintext(
    db_client,
    db_sessionmaker,
) -> None:
    admin, driver, profile = _graph(db_sessionmaker)
    driver_headers = auth_headers(db_client, driver.email)
    denied = db_client.post(
        f"/api/v1/admin/payees/drivers/{profile.id}",
        headers=driver_headers,
    )
    assert denied.status_code == 403

    admin_headers = auth_headers(db_client, admin.email)
    payee = db_client.post(
        f"/api/v1/admin/payees/drivers/{profile.id}",
        headers=admin_headers,
    ).json()
    invalid_number = "sensitive-invalid-account"
    rejected = db_client.post(
        f"/api/v1/admin/payees/{payee['id']}/bank-account-versions",
        headers=admin_headers,
        json={
            "account_name": "Ada Protected",
            "account_number": invalid_number,
            "bank_code": "058",
            "verification_reference": "provider-evidence-api-00000000000000000002",
        },
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "BANK_ACCOUNT_DETAILS_INVALID"
    assert invalid_number not in rejected.text

    nested_secret = "must-not-appear-in-validation-error"
    malformed = db_client.post(
        f"/api/v1/admin/payees/{payee['id']}/bank-account-versions",
        headers=admin_headers,
        json={
            "account_name": "Ada Protected",
            "account_number": {"secret": nested_secret},
            "bank_code": "058",
            "verification_reference": "provider-evidence-api-00000000000000000003",
        },
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "VALIDATION_ERROR"
    assert nested_secret not in malformed.text


def test_payee_api_rewrap_uses_retained_keyring_and_appends_version(
    db_client,
    db_sessionmaker,
) -> None:
    admin, _, profile = _graph(db_sessionmaker)
    headers = auth_headers(db_client, admin.email)
    payee = db_client.post(
        f"/api/v1/admin/payees/drivers/{profile.id}",
        headers=headers,
    ).json()
    verified = db_client.post(
        f"/api/v1/admin/payees/{payee['id']}/bank-account-versions",
        headers=headers,
        json={
            "account_name": "Ada Rotation",
            "account_number": "0123456789",
            "bank_code": "058",
            "verification_reference": "provider-evidence-api-rotation-000000000001",
        },
    )
    assert verified.status_code == 201
    assert verified.json()["encryption_key_version"] == 1

    rotated_settings = Settings(
        environment="test",
        database_url=None,
        redis_url=None,
        backend_cors_origins=["http://localhost:3000"],
        jwt_secret_key="test-secret-key-at-least-32-bytes",
        payout_crypto_keyring_b64=(
            '{"1":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",'
            '"2":"Hh8cHRobGBkWFxQVEhMQEQ4PDA0KCwgJBgcEBQIDAQA="}'
        ),
        payout_crypto_key_version=2,
    )
    db_client.app.dependency_overrides[get_settings] = lambda: rotated_settings

    rotated = db_client.post(
        f"/api/v1/admin/payees/bank-accounts/{verified.json()['bank_account_id']}/rewrap",
        headers=headers,
    )
    assert rotated.status_code == 200
    assert rotated.json()["version"] == 2
    assert rotated.json()["encryption_key_version"] == 2

    revealed = db_client.post(
        f"/api/v1/admin/payees/bank-account-versions/{rotated.json()['id']}/reveal",
        headers=headers,
        json={"purpose": "key_rotation_verification"},
    )
    assert revealed.status_code == 200
    assert revealed.json()["account_number"] == "0123456789"

    async def inspect_versions() -> list[PayeeBankAccountVersion]:
        async with db_sessionmaker() as session:
            return list(
                (
                    await session.scalars(
                        select(PayeeBankAccountVersion)
                        .where(
                            PayeeBankAccountVersion.bank_account_id
                            == UUID(verified.json()["bank_account_id"])
                        )
                        .order_by(PayeeBankAccountVersion.version)
                    )
                ).all()
            )

    versions = asyncio.run(inspect_versions())
    assert [version.version for version in versions] == [1, 2]
    assert [version.encryption_key_version for version in versions] == [1, 2]
    assert (
        versions[1].encrypted_details["ciphertext_b64"]
        == versions[0].encrypted_details["ciphertext_b64"]
    )

import asyncio
from collections import Counter
from uuid import uuid4

import pytest
from conftest import create_test_driver_profile, create_test_user
from sqlalchemy import func, select

from app.adapters.crypto import EnvelopeCryptoProvider
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.driver import DriverOnboardingStatus
from app.models.payee import (
    Payee,
    PayeeBankAccount,
    PayeeBankAccountVersion,
    PayeeType,
    PayeeVersion,
)
from app.models.user import UserRole
from app.services.payees import (
    VerifiedBankAccountDetails,
    add_verified_bank_account_version,
    create_pilot_payee,
    read_verified_bank_account,
    rewrap_bank_account,
)

DETAILS = VerifiedBankAccountDetails(
    account_name="Ada Driver",
    account_number="0123456789",
    bank_code="058",
)
VERIFICATION_REFERENCE = "provider-evidence-00000000000000000001"


def _seed_actor_and_driver(db_sessionmaker):
    admin = create_test_user(
        db_sessionmaker,
        email=f"payee-admin-{uuid4().hex}@example.com",
        role=UserRole.ADMIN,
    )
    driver = create_test_user(
        db_sessionmaker,
        email=f"payee-driver-{uuid4().hex}@example.com",
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    return admin, driver, profile


def test_synthetic_driver_payee_flow_is_versioned_encrypted_and_audited(db_sessionmaker) -> None:
    admin, driver, profile = _seed_actor_and_driver(db_sessionmaker)
    crypto = EnvelopeCryptoProvider(keys={1: b"e" * 32}, active_key_version=1)

    async def exercise():
        async with db_sessionmaker() as session:
            payee, payee_version = await create_pilot_payee(
                session,
                driver_profile_id=profile.id,
                actor_user_id=admin.id,
            )
            first = await add_verified_bank_account_version(
                session,
                payee_id=payee.id,
                details=DETAILS,
                verification_reference=VERIFICATION_REFERENCE,
                actor_user_id=admin.id,
                crypto=crypto,
            )
            second = await add_verified_bank_account_version(
                session,
                payee_id=payee.id,
                details=VerifiedBankAccountDetails(
                    account_name="Ada Driver Updated",
                    account_number="9876543210",
                    bank_code="044",
                ),
                verification_reference="provider-evidence-00000000000000000002",
                actor_user_id=admin.id,
                crypto=crypto,
            )
            await session.commit()

        async with db_sessionmaker() as session:
            plaintext = await read_verified_bank_account(
                session,
                bank_account_version_id=first.id,
                actor_user_id=admin.id,
                crypto=crypto,
                purpose="payout_operations",
            )
            await session.commit()
            stored = list(
                (
                    await session.scalars(
                        select(PayeeBankAccountVersion).order_by(PayeeBankAccountVersion.version)
                    )
                ).all()
            )
            audits = list(
                (
                    await session.scalars(
                        select(AuditEvent)
                        .where(AuditEvent.entity_type.in_(("payee", "payee_bank_account")))
                        .order_by(AuditEvent.created_at, AuditEvent.id)
                    )
                ).all()
            )
            return payee, payee_version, first, second, plaintext, stored, audits

    payee, payee_version, first, second, plaintext, stored, audits = asyncio.run(exercise())

    assert payee.tenant_id == driver.id
    assert payee.subject_id == profile.id
    assert payee.payee_type == PayeeType.DRIVER
    assert payee_version.version == 1
    assert [first.version, second.version] == [1, 2]
    assert plaintext == DETAILS
    assert "0123456789" not in str(stored[0].encrypted_details)
    assert "Ada Driver" not in str(stored[0].encrypted_details)
    assert len(stored[0].verification_reference_sha256) == 64
    assert VERIFICATION_REFERENCE not in str(stored[0].__dict__)
    assert "0123456789" not in repr(DETAILS)
    assert Counter(audit.action for audit in audits) == Counter(
        {
            "admin.payee.created": 1,
            "admin.bank_account.verified": 2,
            "admin.bank_account.read": 1,
        }
    )
    audit_text = str([audit.event_metadata for audit in audits])
    assert VERIFICATION_REFERENCE not in audit_text
    assert "0123456789" not in audit_text
    assert "ciphertext" not in audit_text


def test_service_enforces_admin_and_rejects_fleet_behavior(db_sessionmaker) -> None:
    admin, driver, profile = _seed_actor_and_driver(db_sessionmaker)

    async def exercise() -> tuple[str, str]:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as fleet_error:
                await create_pilot_payee(
                    session,
                    driver_profile_id=profile.id,
                    actor_user_id=admin.id,
                    payee_type="fleet_owner",  # type: ignore[arg-type]
                )
            with pytest.raises(AppError) as role_error:
                await create_pilot_payee(
                    session,
                    driver_profile_id=profile.id,
                    actor_user_id=driver.id,
                )
            return fleet_error.value.code, role_error.value.code

    assert asyncio.run(exercise()) == ("PAYEE_TYPE_NOT_SUPPORTED", "PAYEE_ACCESS_FORBIDDEN")


def test_cross_tenant_ciphertext_substitution_fails_and_read_is_not_audited(
    db_sessionmaker,
) -> None:
    admin, _, first_profile = _seed_actor_and_driver(db_sessionmaker)
    other_driver = create_test_user(
        db_sessionmaker,
        email=f"payee-other-{uuid4().hex}@example.com",
        role=UserRole.DRIVER,
    )
    other_profile = create_test_driver_profile(db_sessionmaker, user_id=other_driver.id)
    crypto = EnvelopeCryptoProvider(keys={1: b"f" * 32}, active_key_version=1)

    async def exercise() -> tuple[str, int]:
        async with db_sessionmaker() as session:
            first_payee, _ = await create_pilot_payee(
                session, driver_profile_id=first_profile.id, actor_user_id=admin.id
            )
            second_payee, _ = await create_pilot_payee(
                session, driver_profile_id=other_profile.id, actor_user_id=admin.id
            )
            first = await add_verified_bank_account_version(
                session,
                payee_id=first_payee.id,
                details=DETAILS,
                verification_reference=VERIFICATION_REFERENCE,
                actor_user_id=admin.id,
                crypto=crypto,
            )
            second = await add_verified_bank_account_version(
                session,
                payee_id=second_payee.id,
                details=DETAILS,
                verification_reference="provider-evidence-00000000000000000003",
                actor_user_id=admin.id,
                crypto=crypto,
            )
            second.encrypted_details = first.encrypted_details
            await session.commit()

        async with db_sessionmaker() as session:
            before = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.bank_account.read"
                    )
                )
                or 0
            )
            with pytest.raises(AppError) as caught:
                await read_verified_bank_account(
                    session,
                    bank_account_version_id=second.id,
                    actor_user_id=admin.id,
                    crypto=crypto,
                    purpose="payout_operations",
                )
            after = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.bank_account.read"
                    )
                )
                or 0
            )
            return caught.value.code, after - before

    assert asyncio.run(exercise()) == ("BANK_ACCOUNT_DECRYPTION_FAILED", 0)


def test_rewrap_is_append_only_and_exact_retry_converges(db_sessionmaker) -> None:
    admin, _, profile = _seed_actor_and_driver(db_sessionmaker)
    old_crypto = EnvelopeCryptoProvider(keys={1: b"g" * 32}, active_key_version=1)
    rotating_crypto = EnvelopeCryptoProvider(
        keys={1: b"g" * 32, 2: b"h" * 32}, active_key_version=2
    )

    async def exercise():
        async with db_sessionmaker() as session:
            payee, _ = await create_pilot_payee(
                session, driver_profile_id=profile.id, actor_user_id=admin.id
            )
            original = await add_verified_bank_account_version(
                session,
                payee_id=payee.id,
                details=DETAILS,
                verification_reference=VERIFICATION_REFERENCE,
                actor_user_id=admin.id,
                crypto=old_crypto,
            )
            account_id = original.bank_account_id
            await session.commit()

        async with db_sessionmaker() as session:
            rotated = await rewrap_bank_account(
                session,
                bank_account_id=account_id,
                actor_user_id=admin.id,
                crypto=rotating_crypto,
            )
            retried = await rewrap_bank_account(
                session,
                bank_account_id=account_id,
                actor_user_id=admin.id,
                crypto=rotating_crypto,
            )
            await session.commit()
            versions = list(
                (
                    await session.scalars(
                        select(PayeeBankAccountVersion)
                        .where(PayeeBankAccountVersion.bank_account_id == account_id)
                        .order_by(PayeeBankAccountVersion.version)
                    )
                ).all()
            )
            rewrap_audits = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.bank_account.rewrapped"
                    )
                )
                or 0
            )
            return original, rotated, retried, versions, rewrap_audits

    original, rotated, retried, versions, rewrap_audits = asyncio.run(exercise())

    assert [version.version for version in versions] == [1, 2]
    assert rotated.id == retried.id
    assert rotated.encryption_key_version == 2
    assert versions[0].encrypted_details["nonce_b64"] == versions[1].encrypted_details["nonce_b64"]
    assert (
        versions[0].encrypted_details["ciphertext_b64"]
        == versions[1].encrypted_details["ciphertext_b64"]
    )
    assert (
        versions[0].encrypted_details["wrapped_key_b64"]
        != versions[1].encrypted_details["wrapped_key_b64"]
    )
    assert rewrap_audits == 1


def test_create_and_audit_roll_back_together(db_sessionmaker) -> None:
    admin, _, profile = _seed_actor_and_driver(db_sessionmaker)

    async def exercise() -> tuple[int, int]:
        async with db_sessionmaker() as session:
            await create_pilot_payee(session, driver_profile_id=profile.id, actor_user_id=admin.id)
            await session.rollback()
        async with db_sessionmaker() as session:
            payees = int(await session.scalar(select(func.count(Payee.id))) or 0)
            audits = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.payee.created"
                    )
                )
                or 0
            )
            return payees, audits

    assert asyncio.run(exercise()) == (0, 0)


def test_postgres_concurrent_first_and_later_versions_serialize(postgis_db_sessionmaker) -> None:
    admin, _, profile = _seed_actor_and_driver(postgis_db_sessionmaker)
    crypto = EnvelopeCryptoProvider(keys={1: b"i" * 32}, active_key_version=1)

    async def setup() -> tuple:
        async with postgis_db_sessionmaker() as session:
            payee, _ = await create_pilot_payee(
                session, driver_profile_id=profile.id, actor_user_id=admin.id
            )
            await session.commit()
            return payee.id

    payee_id = asyncio.run(setup())

    async def add(suffix: int) -> int:
        async with postgis_db_sessionmaker() as session:
            version = await add_verified_bank_account_version(
                session,
                payee_id=payee_id,
                details=VerifiedBankAccountDetails(
                    account_name=f"Concurrent Driver {suffix}",
                    account_number=f"{suffix:010d}"[-10:],
                    bank_code="058",
                ),
                verification_reference=f"provider-evidence-concurrent-{suffix:032d}",
                actor_user_id=admin.id,
                crypto=crypto,
            )
            await session.commit()
            return version.version

    async def run_pair(start: int) -> list[int]:
        return sorted(await asyncio.gather(add(start), add(start + 1)))

    assert asyncio.run(run_pair(1)) == [1, 2]
    assert asyncio.run(run_pair(3)) == [3, 4]

    async def counts() -> tuple[int, list[int]]:
        async with postgis_db_sessionmaker() as session:
            account_count = int(await session.scalar(select(func.count(PayeeBankAccount.id))) or 0)
            versions = list(
                (
                    await session.scalars(
                        select(PayeeBankAccountVersion.version).order_by(
                            PayeeBankAccountVersion.version
                        )
                    )
                ).all()
            )
            return account_count, versions

    assert asyncio.run(counts()) == (1, [1, 2, 3, 4])


def test_models_have_no_plaintext_bank_columns() -> None:
    columns = set(PayeeBankAccountVersion.__table__.columns.keys())
    assert not {"account_name", "account_number", "bank_code", "verification_reference"} & columns
    assert {"encrypted_details", "encryption_algorithm", "encryption_key_version"} <= columns
    assert Payee.__table__.c.payee_type.type.length == 32
    assert PayeeVersion.__table__.c.version.nullable is False

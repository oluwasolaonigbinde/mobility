import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import NoReturn
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.adapters.crypto import (
    AssociatedData,
    CiphertextEnvelope,
    CryptoOperationError,
    CryptoProvider,
)
from app.core.errors import AppError
from app.models.driver import DriverProfile
from app.models.payee import (
    Payee,
    PayeeBankAccount,
    PayeeBankAccountVersion,
    PayeeType,
    PayeeVersion,
)
from app.models.user import User, UserRole, UserStatus
from app.services.audit import create_audit_event

BANK_ACCOUNT_DETAILS_FIELD = "bank_account.details"
PURPOSE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


@dataclass(frozen=True, slots=True)
class VerifiedBankAccountDetails:
    account_name: str = field(repr=False)
    account_number: str = field(repr=False)
    bank_code: str = field(repr=False)

    def __repr__(self) -> str:
        return "VerifiedBankAccountDetails(<redacted>)"


async def create_pilot_payee(
    session: AsyncSession,
    *,
    driver_profile_id: UUID,
    actor_user_id: UUID,
    payee_type: PayeeType = PayeeType.DRIVER,
) -> tuple[Payee, PayeeVersion]:
    """Create or return the immutable pilot driver payee and its first version."""

    await _require_active_admin(session, actor_user_id)
    if payee_type != PayeeType.DRIVER:
        raise AppError(
            "PAYEE_TYPE_NOT_SUPPORTED",
            "Only driver payees are supported during the pilot",
            status_code=status.HTTP_409_CONFLICT,
        )
    profile = await session.scalar(
        select(DriverProfile).where(DriverProfile.id == driver_profile_id).with_for_update()
    )
    if profile is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    driver_user = await session.scalar(select(User).where(User.id == profile.user_id))
    if driver_user is None or driver_user.role != UserRole.DRIVER:
        raise AppError(
            "PAYEE_SUBJECT_INVALID",
            "Pilot payees require a driver profile owned by a driver user",
            status_code=status.HTTP_409_CONFLICT,
        )

    return await _create_driver_payee_locked(
        session,
        profile=profile,
        driver_user=driver_user,
        actor_user_id=actor_user_id,
        audit_action="admin.payee.created",
    )


async def create_applicant_payee(
    session: AsyncSession,
    *,
    driver_profile_id: UUID,
    actor_user_id: UUID,
) -> tuple[Payee, PayeeVersion]:
    """Create the same pilot payee after a public-application capability check."""

    profile = await session.scalar(
        select(DriverProfile).where(DriverProfile.id == driver_profile_id).with_for_update()
    )
    driver_user = await session.scalar(
        select(User).where(User.id == actor_user_id).with_for_update()
    )
    if (
        profile is None
        or profile.user_id != actor_user_id
        or driver_user is None
        or driver_user.role != UserRole.DRIVER
        or driver_user.status not in {UserStatus.INVITED, UserStatus.ACTIVE}
    ):
        raise AppError(
            "PAYEE_SUBJECT_INVALID",
            "Pilot payees require the referenced driver application",
            status_code=status.HTTP_409_CONFLICT,
        )
    return await _create_driver_payee_locked(
        session,
        profile=profile,
        driver_user=driver_user,
        actor_user_id=actor_user_id,
        audit_action="driver_application.payee.created",
    )


async def _create_driver_payee_locked(
    session: AsyncSession,
    *,
    profile: DriverProfile,
    driver_user: User,
    actor_user_id: UUID,
    audit_action: str,
) -> tuple[Payee, PayeeVersion]:

    payee = await session.scalar(
        select(Payee).where(
            Payee.tenant_id == driver_user.id,
            Payee.payee_type == PayeeType.DRIVER,
            Payee.subject_id == profile.id,
        )
    )
    if payee is not None:
        version = await _current_payee_version(session, payee.id)
        return payee, version

    payee = Payee(
        tenant_id=driver_user.id,
        payee_type=PayeeType.DRIVER,
        subject_id=profile.id,
        created_by_user_id=actor_user_id,
    )
    session.add(payee)
    await session.flush()
    version = PayeeVersion(
        payee_id=payee.id,
        version=1,
        payee_type=payee.payee_type,
        subject_id=payee.subject_id,
        created_by_user_id=actor_user_id,
    )
    session.add(version)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action=audit_action,
        entity_type="payee",
        entity_id=str(payee.id),
        metadata={"payee_type": PayeeType.DRIVER, "payee_version": 1},
    )
    return payee, version


async def add_verified_bank_account_version(
    session: AsyncSession,
    *,
    payee_id: UUID,
    details: VerifiedBankAccountDetails,
    verification_reference: str,
    actor_user_id: UUID,
    crypto: CryptoProvider,
) -> PayeeBankAccountVersion:
    """Append an encrypted verified account version under the stable payee lock."""

    await _require_active_admin(session, actor_user_id)
    return await _add_verified_bank_account_version_authorized(
        session,
        payee_id=payee_id,
        details=details,
        verification_reference=verification_reference,
        actor_user_id=actor_user_id,
        crypto=crypto,
        audit_action="admin.bank_account.verified",
    )


async def add_applicant_verified_bank_account_version(
    session: AsyncSession,
    *,
    payee_id: UUID,
    details: VerifiedBankAccountDetails,
    verification_reference: str,
    actor_user_id: UUID,
    crypto: CryptoProvider,
) -> PayeeBankAccountVersion:
    """Append a verified account only for its capability-authorized driver."""

    actor = await session.scalar(select(User).where(User.id == actor_user_id).with_for_update())
    payee = await session.scalar(select(Payee).where(Payee.id == payee_id).with_for_update())
    if (
        actor is None
        or actor.role != UserRole.DRIVER
        or actor.status not in {UserStatus.INVITED, UserStatus.ACTIVE}
        or payee is None
        or payee.tenant_id != actor_user_id
        or payee.payee_type != PayeeType.DRIVER
    ):
        raise AppError(
            "PAYEE_ACCESS_FORBIDDEN",
            "The referenced application does not own this payee",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return await _add_verified_bank_account_version_authorized(
        session,
        payee_id=payee_id,
        details=details,
        verification_reference=verification_reference,
        actor_user_id=actor_user_id,
        crypto=crypto,
        audit_action="driver_application.bank_account.verified",
        locked_payee=payee,
    )


async def _add_verified_bank_account_version_authorized(
    session: AsyncSession,
    *,
    payee_id: UUID,
    details: VerifiedBankAccountDetails,
    verification_reference: str,
    actor_user_id: UUID,
    crypto: CryptoProvider,
    audit_action: str,
    locked_payee: Payee | None = None,
) -> PayeeBankAccountVersion:
    normalized_details = _validate_details(details)
    verification_hash = verification_reference_hash(verification_reference)
    payee = locked_payee or await session.scalar(
        select(Payee).where(Payee.id == payee_id).with_for_update()
    )
    if payee is None:
        raise AppError(
            "PAYEE_NOT_FOUND", "Payee was not found", status_code=status.HTTP_404_NOT_FOUND
        )
    if payee.payee_type != PayeeType.DRIVER:
        raise AppError(
            "PAYEE_TYPE_NOT_SUPPORTED",
            "Only driver payees are supported during the pilot",
            status_code=status.HTTP_409_CONFLICT,
        )
    payee_version = await _current_payee_version(session, payee.id)

    account = await session.scalar(
        select(PayeeBankAccount).where(PayeeBankAccount.payee_id == payee.id)
    )
    if account is None:
        account = PayeeBankAccount(payee_id=payee.id, created_by_user_id=actor_user_id)
        session.add(account)
        await session.flush()
        next_version = 1
    else:
        account = await session.scalar(
            select(PayeeBankAccount).where(PayeeBankAccount.id == account.id).with_for_update()
        )
        if account is None:  # pragma: no cover - protected by the payee lock and FK
            raise RuntimeError("Bank-account authority disappeared while locked")
        current = await _current_bank_account_version(session, account.id)
        next_version = current.version + 1

    plaintext = json.dumps(
        {
            "account_name": normalized_details.account_name,
            "account_number": normalized_details.account_number,
            "bank_code": normalized_details.bank_code,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    aad = AssociatedData(
        tenant_id=payee.tenant_id,
        record_id=account.id,
        field_name=BANK_ACCOUNT_DETAILS_FIELD,
    )
    envelope = crypto.encrypt(plaintext, aad)
    account_version = PayeeBankAccountVersion(
        id=uuid4(),
        bank_account_id=account.id,
        payee_version_id=payee_version.id,
        version=next_version,
        encrypted_details=envelope.to_mapping(),
        encryption_algorithm=envelope.data_algorithm,
        encryption_key_version=envelope.key_version,
        verification_reference_sha256=verification_hash,
        verified_by_user_id=actor_user_id,
    )
    session.add(account_version)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action=audit_action,
        entity_type="payee_bank_account",
        entity_id=str(account.id),
        metadata={
            "payee_id": str(payee.id),
            "payee_version": payee_version.version,
            "bank_account_version": next_version,
            "key_version": envelope.key_version,
        },
    )
    return account_version


async def read_verified_bank_account(
    session: AsyncSession,
    *,
    bank_account_version_id: UUID,
    actor_user_id: UUID,
    crypto: CryptoProvider,
    purpose: str,
) -> VerifiedBankAccountDetails:
    """Return plaintext only after service-level RBAC and stage a redacted audit."""

    await _require_active_admin(session, actor_user_id)
    return await _read_verified_bank_account_authorized(
        session,
        bank_account_version_id=bank_account_version_id,
        actor_user_id=actor_user_id,
        crypto=crypto,
        purpose=purpose,
        audit_action="admin.bank_account.read",
    )


async def read_applicant_verified_bank_account(
    session: AsyncSession,
    *,
    bank_account_version_id: UUID,
    actor_user_id: UUID,
    crypto: CryptoProvider,
    purpose: str,
) -> VerifiedBankAccountDetails:
    actor = await session.scalar(select(User).where(User.id == actor_user_id))
    owned = await session.scalar(
        select(PayeeBankAccountVersion.id)
        .join(
            PayeeBankAccount,
            PayeeBankAccount.id == PayeeBankAccountVersion.bank_account_id,
        )
        .join(Payee, Payee.id == PayeeBankAccount.payee_id)
        .where(
            PayeeBankAccountVersion.id == bank_account_version_id,
            Payee.tenant_id == actor_user_id,
        )
    )
    if (
        actor is None
        or actor.role != UserRole.DRIVER
        or actor.status not in {UserStatus.INVITED, UserStatus.ACTIVE}
        or owned is None
    ):
        raise AppError(
            "PAYEE_ACCESS_FORBIDDEN",
            "The referenced application does not own this bank account",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return await _read_verified_bank_account_authorized(
        session,
        bank_account_version_id=bank_account_version_id,
        actor_user_id=actor_user_id,
        crypto=crypto,
        purpose=purpose,
        audit_action="driver_application.bank_account.retry_read",
    )


async def _read_verified_bank_account_authorized(
    session: AsyncSession,
    *,
    bank_account_version_id: UUID,
    actor_user_id: UUID,
    crypto: CryptoProvider,
    purpose: str,
    audit_action: str,
) -> VerifiedBankAccountDetails:
    purpose = _normalize_purpose(purpose)
    result = await session.execute(
        select(PayeeBankAccountVersion, PayeeBankAccount, Payee)
        .join(
            PayeeBankAccount,
            PayeeBankAccount.id == PayeeBankAccountVersion.bank_account_id,
        )
        .join(Payee, Payee.id == PayeeBankAccount.payee_id)
        .where(PayeeBankAccountVersion.id == bank_account_version_id)
    )
    row = result.one_or_none()
    if row is None:
        raise AppError(
            "BANK_ACCOUNT_VERSION_NOT_FOUND",
            "Bank-account version was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    account_version, account, payee = row
    envelope = _parse_envelope(account_version.encrypted_details)
    aad = AssociatedData(
        tenant_id=payee.tenant_id,
        record_id=account.id,
        field_name=BANK_ACCOUNT_DETAILS_FIELD,
    )
    try:
        plaintext = crypto.decrypt(envelope, aad)
        decoded = json.loads(plaintext)
        details = VerifiedBankAccountDetails(
            account_name=decoded["account_name"],
            account_number=decoded["account_number"],
            bank_code=decoded["bank_code"],
        )
        details = _validate_details(details)
    except (CryptoOperationError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise AppError(
            "BANK_ACCOUNT_DECRYPTION_FAILED",
            "Bank-account details could not be authenticated",
            status_code=status.HTTP_409_CONFLICT,
        ) from None
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action=audit_action,
        entity_type="payee_bank_account",
        entity_id=str(account.id),
        metadata={
            "bank_account_version": account_version.version,
            "purpose": purpose,
        },
    )
    return details


async def rewrap_bank_account(
    session: AsyncSession,
    *,
    bank_account_id: UUID,
    actor_user_id: UUID,
    crypto: CryptoProvider,
) -> PayeeBankAccountVersion:
    """Append one rewrapped version; exact retries converge on the active key."""

    await _require_active_admin(session, actor_user_id)
    account_probe = await session.scalar(
        select(PayeeBankAccount).where(PayeeBankAccount.id == bank_account_id)
    )
    if account_probe is None:
        raise AppError(
            "BANK_ACCOUNT_NOT_FOUND",
            "Bank account was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    payee = await session.scalar(
        select(Payee).where(Payee.id == account_probe.payee_id).with_for_update()
    )
    account = await session.scalar(
        select(PayeeBankAccount)
        .where(
            PayeeBankAccount.id == bank_account_id,
            PayeeBankAccount.payee_id == payee.id,
        )
        .with_for_update()
    )
    if account is None:  # pragma: no cover - stable FK and locked payee make this unreachable
        raise RuntimeError("Bank-account authority disappeared while locked")
    current = await _current_bank_account_version(session, account.id)
    if current.encryption_key_version == crypto.active_key_version:
        return current

    envelope = _parse_envelope(current.encrypted_details)
    aad = AssociatedData(
        tenant_id=payee.tenant_id,
        record_id=account.id,
        field_name=BANK_ACCOUNT_DETAILS_FIELD,
    )
    try:
        rotated = crypto.rotate(envelope, aad)
    except CryptoOperationError:
        raise AppError(
            "BANK_ACCOUNT_REWRAP_FAILED",
            "Bank-account encryption could not be rotated",
            status_code=status.HTTP_409_CONFLICT,
        ) from None
    new_version = PayeeBankAccountVersion(
        id=uuid4(),
        bank_account_id=account.id,
        payee_version_id=current.payee_version_id,
        version=current.version + 1,
        encrypted_details=rotated.to_mapping(),
        encryption_algorithm=rotated.data_algorithm,
        encryption_key_version=rotated.key_version,
        verification_reference_sha256=current.verification_reference_sha256,
        verified_at=current.verified_at,
        verified_by_user_id=current.verified_by_user_id,
    )
    session.add(new_version)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.bank_account.rewrapped",
        entity_type="payee_bank_account",
        entity_id=str(account.id),
        metadata={
            "bank_account_version": new_version.version,
            "from_key_version": current.encryption_key_version,
            "to_key_version": new_version.encryption_key_version,
        },
    )
    return new_version


async def _require_active_admin(session: AsyncSession, actor_user_id: UUID) -> User:
    actor = await session.scalar(select(User).where(User.id == actor_user_id))
    if actor is None or actor.role != UserRole.ADMIN or actor.status != UserStatus.ACTIVE:
        raise AppError(
            "PAYEE_ACCESS_FORBIDDEN",
            "Payee bank-account access requires an active administrator",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return actor


async def _current_payee_version(session: AsyncSession, payee_id: UUID) -> PayeeVersion:
    version = await session.scalar(
        select(PayeeVersion)
        .where(PayeeVersion.payee_id == payee_id)
        .order_by(PayeeVersion.version.desc())
        .limit(1)
    )
    if version is None:
        _broken_authority("Payee has no immutable version")
    return version


async def _current_bank_account_version(
    session: AsyncSession, bank_account_id: UUID
) -> PayeeBankAccountVersion:
    version = await session.scalar(
        select(PayeeBankAccountVersion)
        .where(PayeeBankAccountVersion.bank_account_id == bank_account_id)
        .order_by(PayeeBankAccountVersion.version.desc())
        .limit(1)
    )
    if version is None:
        _broken_authority("Bank account has no immutable version")
    return version


def _validate_details(details: VerifiedBankAccountDetails) -> VerifiedBankAccountDetails:
    account_name = details.account_name.strip()
    if not 2 <= len(account_name) <= 160:
        _invalid_details()
    if len(details.account_number) != 10 or not details.account_number.isascii():
        _invalid_details()
    if not details.account_number.isdigit():
        _invalid_details()
    if len(details.bank_code) != 3 or not details.bank_code.isascii():
        _invalid_details()
    if not details.bank_code.isdigit():
        _invalid_details()
    return VerifiedBankAccountDetails(
        account_name=account_name,
        account_number=details.account_number,
        bank_code=details.bank_code,
    )


def verification_reference_hash(reference: str) -> str:
    try:
        encoded = reference.encode("utf-8")
    except (AttributeError, UnicodeError):
        encoded = b""
    if not 32 <= len(encoded) <= 512 or any(character.isspace() for character in reference):
        raise AppError(
            "VERIFICATION_REFERENCE_INVALID",
            "Verification evidence must be an opaque high-entropy reference",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return hashlib.sha256(encoded).hexdigest()


def _normalize_purpose(purpose: str) -> str:
    normalized = purpose.strip()
    if PURPOSE_PATTERN.fullmatch(normalized) is None:
        raise AppError(
            "BANK_ACCOUNT_READ_PURPOSE_INVALID",
            "A valid bank-account access purpose is required",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return normalized


def _parse_envelope(value: dict[str, object]) -> CiphertextEnvelope:
    try:
        return CiphertextEnvelope.from_mapping(value)
    except CryptoOperationError:
        raise AppError(
            "BANK_ACCOUNT_DECRYPTION_FAILED",
            "Bank-account details could not be authenticated",
            status_code=status.HTTP_409_CONFLICT,
        ) from None


def _invalid_details() -> NoReturn:
    raise AppError(
        "BANK_ACCOUNT_DETAILS_INVALID",
        "Bank-account details are invalid",
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


def _broken_authority(message: str) -> NoReturn:
    raise RuntimeError(message)

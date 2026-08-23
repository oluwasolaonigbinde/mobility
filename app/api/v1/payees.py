from uuid import UUID

from fastapi import APIRouter, Response, status

from app.adapters.crypto import EnvelopeCryptoProvider
from app.api.v1.dependencies import AdminUserDependency, SessionDependency, SettingsDependency
from app.schemas.payees import (
    BankAccountRevealRead,
    BankAccountRevealRequest,
    BankAccountVersionRead,
    PayeeRead,
    VerifiedBankAccountCreate,
)
from app.services.payees import (
    VerifiedBankAccountDetails,
    add_verified_bank_account_version,
    create_pilot_payee,
    read_verified_bank_account,
    rewrap_bank_account,
)

router = APIRouter(prefix="/admin/payees", tags=["Admin payees"])


def _crypto(settings: SettingsDependency) -> EnvelopeCryptoProvider:
    return EnvelopeCryptoProvider(
        keys=settings.payout_crypto_keys,
        active_key_version=settings.payout_crypto_key_version,
    )


def _payee_response(payee, version) -> PayeeRead:
    return PayeeRead(
        id=payee.id,
        tenant_id=payee.tenant_id,
        payee_type=payee.payee_type,
        subject_id=payee.subject_id,
        version_id=version.id,
        version=version.version,
        created_at=payee.created_at,
    )


def _account_response(version) -> BankAccountVersionRead:
    return BankAccountVersionRead(
        id=version.id,
        bank_account_id=version.bank_account_id,
        payee_version_id=version.payee_version_id,
        version=version.version,
        encryption_algorithm=version.encryption_algorithm,
        encryption_key_version=version.encryption_key_version,
        verified_at=version.verified_at,
        created_at=version.created_at,
    )


@router.post(
    "/drivers/{driver_profile_id}",
    response_model=PayeeRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_driver_payee(
    driver_profile_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> PayeeRead:
    payee, version = await create_pilot_payee(
        session,
        driver_profile_id=driver_profile_id,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return _payee_response(payee, version)


@router.post(
    "/{payee_id}/bank-account-versions",
    response_model=BankAccountVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_add_verified_bank_account(
    payee_id: UUID,
    payload: VerifiedBankAccountCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> BankAccountVersionRead:
    version = await add_verified_bank_account_version(
        session,
        payee_id=payee_id,
        details=VerifiedBankAccountDetails(
            account_name=payload.account_name.get_secret_value(),
            account_number=payload.account_number.get_secret_value(),
            bank_code=payload.bank_code.get_secret_value(),
        ),
        verification_reference=payload.verification_reference.get_secret_value(),
        actor_user_id=current_user.id,
        crypto=_crypto(settings),
    )
    await session.commit()
    return _account_response(version)


@router.post(
    "/bank-account-versions/{version_id}/reveal",
    response_model=BankAccountRevealRead,
)
async def admin_reveal_bank_account(
    version_id: UUID,
    payload: BankAccountRevealRequest,
    response: Response,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> BankAccountRevealRead:
    details = await read_verified_bank_account(
        session,
        bank_account_version_id=version_id,
        actor_user_id=current_user.id,
        crypto=_crypto(settings),
        purpose=payload.purpose,
    )
    await session.commit()
    response.headers["Cache-Control"] = "no-store"
    return BankAccountRevealRead(
        account_name=details.account_name,
        account_number=details.account_number,
        bank_code=details.bank_code,
    )


@router.post(
    "/bank-accounts/{bank_account_id}/rewrap",
    response_model=BankAccountVersionRead,
)
async def admin_rewrap_bank_account(
    bank_account_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> BankAccountVersionRead:
    version = await rewrap_bank_account(
        session,
        bank_account_id=bank_account_id,
        actor_user_id=current_user.id,
        crypto=_crypto(settings),
    )
    await session.commit()
    return _account_response(version)

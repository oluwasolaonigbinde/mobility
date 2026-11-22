import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from app.adapters.banks import BankAdapter, BankLookupInvalid, BankLookupRefused
from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.banks import AccountNameCheckRead


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _invalid() -> AppError:
    return AppError(
        "BANK_CHECK_INVALID", "Check your bank and account details again", status_code=422
    )


async def check_account_name(
    *, user_id: UUID, bank_code: str, account_number: str, adapter: BankAdapter, settings: Settings
) -> AccountNameCheckRead:
    if not account_number.isascii() or not account_number.isdigit() or len(account_number) != 10:
        raise _invalid()
    if bank_code not in {bank.code for bank in await adapter.banks()}:
        raise _invalid()
    try:
        name = await adapter.resolve(bank_code, account_number)
        outcome = "resolved" if name else "unavailable"
    except BankLookupRefused:
        name = None
        outcome = "refused"
    except BankLookupInvalid:
        raise _invalid() from None
    now = datetime.now(UTC)
    receipt = jwt.encode(
        {
            "kind": "driver-bank-check-v1",
            "sub": str(user_id),
            "bank_code": bank_code,
            "account_digest": digest(account_number),
            "name_digest": digest(name) if name else None,
            "outcome": outcome,
            "iat": now,
            "jti": str(uuid4()),
            "exp": now + timedelta(minutes=15),
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )
    return AccountNameCheckRead(outcome=outcome, account_name=name, bank_check_receipt=receipt)


def _verified_bank_check(receipt, *, user_id: UUID, settings: Settings, replay: bool):
    if receipt is None:
        raise _invalid()
    raw = receipt.get_secret_value()
    try:
        claims = jwt.decode(
            raw,
            settings.jwt_secret_key,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub", "jti"], "verify_exp": not replay},
        )
        receipt_id = UUID(claims["jti"])
    except (jwt.PyJWTError, ValueError, TypeError, AttributeError):
        raise _invalid() from None
    if claims.get("kind") != "driver-bank-check-v1" or claims.get("sub") != str(user_id):
        raise _invalid()
    return digest(str(receipt_id)), claims


def require_bank_check(payload, *, user_id: UUID, settings: Settings) -> tuple[str, str]:
    identity, claims = _verified_bank_check(
        payload.bank_check_receipt, user_id=user_id, settings=settings, replay=False
    )
    if claims.get("bank_code") != payload.bank_code.get_secret_value() or claims.get(
        "account_digest"
    ) != digest(payload.account_number.get_secret_value()):
        raise _invalid()
    outcome = claims.get("outcome")
    if outcome == "resolved":
        if not payload.account_name_confirmed or claims.get("name_digest") != digest(
            payload.account_name.get_secret_value().strip()
        ):
            raise _invalid()
    elif outcome not in ("unavailable", "refused") or payload.account_name_confirmed:
        raise _invalid()
    return identity, outcome


def matches_prior_bank_check(payload, *, user_id: UUID, settings: Settings, receipt_sha256) -> bool:
    try:
        identity, _ = _verified_bank_check(
            payload.bank_check_receipt, user_id=user_id, settings=settings, replay=True
        )
    except AppError:
        return False
    return identity == receipt_sha256

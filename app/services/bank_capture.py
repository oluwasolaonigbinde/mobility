import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.adapters.banks import BankAdapter, BankLookupInvalid
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
    except BankLookupInvalid:
        raise _invalid() from None
    outcome = "resolved" if name else "unavailable"
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
            "exp": now + timedelta(minutes=15),
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )
    return AccountNameCheckRead(outcome=outcome, account_name=name, bank_check_receipt=receipt)


def require_bank_check(payload, *, user_id: UUID, settings: Settings) -> str:
    receipt = payload.bank_check_receipt
    if receipt is None:
        raise _invalid()
    raw = receipt.get_secret_value()
    try:
        claims = jwt.decode(
            raw,
            settings.jwt_secret_key,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError:
        raise _invalid() from None
    if (
        claims.get("kind") != "driver-bank-check-v1"
        or claims.get("sub") != str(user_id)
        or claims.get("bank_code") != payload.bank_code.get_secret_value()
        or claims.get("account_digest") != digest(payload.account_number.get_secret_value())
    ):
        raise _invalid()
    if claims.get("outcome") == "resolved":
        if not payload.account_name_confirmed or claims.get("name_digest") != digest(
            payload.account_name.get_secret_value().strip()
        ):
            raise _invalid()
    elif claims.get("outcome") != "unavailable":
        raise _invalid()
    return digest(raw)

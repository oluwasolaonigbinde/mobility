"""Read-only Nigerian bank discovery and account-name resolution.

Reuses the Paystack JSON client. No recipient or payment authority is created.
"""

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass

import httpx

from app.adapters.payments.paystack import (
    PaystackClient,
    PaystackError,
    PaystackMalformedResponseError,
    PaystackOutcomeUnknownError,
    PaystackRejectedError,
)
from app.core.config import Settings


class _AccountLookupLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                value.copy_with(query=None)
                if isinstance(value, httpx.URL) and value.path == "/bank/resolve"
                else value
                for value in record.args
            )
        return True


logging.getLogger("httpx").addFilter(_AccountLookupLogFilter())
logger = logging.getLogger(__name__)
_PROVIDER_RESTRICTION = re.compile(
    r"\b(?:quota\s+(?:exceeded|exhausted|reached)|(?:exceeded|exhausted|reached)\s+(?:the\s+)?quota"
    r"|rate[ -]limit(?:ed|ing)?|too many requests|test[ -]mode)\b",
    re.IGNORECASE,
)
_PROVIDER_RESOLVE_REFUSAL = re.compile(
    r"\b(?:could(?: not|n't)|cannot|can(?: not|'t)|unable to|failed to)\s+resolve\b",
    re.IGNORECASE,
)

# Extracted from the renewal picker; digital-bank additions support Apply too.
FALLBACK_BANKS = (
    ("999992", "OPay"),
    ("50515", "Moniepoint"),
    ("999991", "PalmPay"),
    ("50211", "Kuda Bank"),
    ("058", "GTBank"),
    ("044", "Access Bank"),
    ("011", "First Bank of Nigeria"),
    ("033", "UBA"),
    ("057", "Zenith Bank"),
    ("023", "Citibank Nigeria"),
    ("050", "Ecobank Nigeria"),
    ("070", "Fidelity Bank"),
    ("214", "First City Monument Bank"),
    ("00103", "Globus Bank"),
    ("301", "Jaiz Bank"),
    ("082", "Keystone Bank"),
    ("076", "Polaris Bank"),
    ("105", "PremiumTrust Bank"),
    ("101", "Providus Bank"),
    ("221", "Stanbic IBTC Bank"),
    ("068", "Standard Chartered Bank"),
    ("232", "Sterling Bank"),
    ("100", "Suntrust Bank"),
    ("102", "Titan Bank"),
    ("032", "Union Bank"),
    ("215", "Unity Bank"),
    ("035", "Wema Bank"),
)
_POPULAR = (
    "opay",
    "moniepoint",
    "palmpay",
    "kuda",
    "gtbank",
    "access",
    "first bank",
    "uba",
    "zenith",
)


class BankLookupInvalid(ValueError):
    """Unusable bank/account response; never grants manual fallback."""


class BankLookupRefused(ValueError):
    """Provider refused lookup for a locally valid bank and account."""


@dataclass(frozen=True)
class Bank:
    code: str
    name: str


def bank_order(bank: Bank) -> tuple[int, str]:
    name = bank.name.casefold()
    if "guaranty trust" in name:
        name = "gtbank"
    if "united bank for africa" in name:
        name = "uba"
    rank = next((i for i, term in enumerate(_POPULAR) if term in name), len(_POPULAR))
    return rank, bank.name.casefold()


class BankAdapter:
    def __init__(self, client: PaystackClient | None = None):
        self.client = client
        self._catalog: list[Bank] | None = None
        self._catalog_until = 0.0
        self._catalog_lock = asyncio.Lock()

    async def banks(self) -> list[Bank]:
        if self.client is None:
            return sorted([Bank(*row) for row in FALLBACK_BANKS], key=bank_order)
        async with self._catalog_lock:
            if self._catalog is not None and time.monotonic() < self._catalog_until:
                return list(self._catalog)
            try:
                self._catalog = await self._provider_banks()
                self._catalog_until = time.monotonic() + 600
            except (PaystackError, BankLookupInvalid):
                self._catalog = sorted([Bank(*row) for row in FALLBACK_BANKS], key=bank_order)
                self._catalog_until = time.monotonic() + 30
            return list(self._catalog)

    async def _provider_banks(self) -> list[Bank]:
        client = self.client
        if client is None:
            raise BankLookupInvalid("Provider is unavailable")
        banks: dict[str, Bank] = {}
        params = {"country": "nigeria", "currency": "NGN", "perPage": "100", "use_cursor": "true"}
        cursors: set[str] = set()
        for _ in range(20):
            body = await client.request("GET", "/bank", params=params, include_meta=True)
            if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                raise BankLookupInvalid("Invalid bank list")
            for row in body["data"]:
                bank = _bank(row)
                if bank:
                    banks[bank.code] = bank
            meta = body.get("meta", {})
            if not isinstance(meta, dict):
                raise BankLookupInvalid("Invalid bank pagination")
            cursor = meta.get("next")
            if cursor is None:
                if not banks:
                    raise BankLookupInvalid("Empty bank list")
                return sorted(banks.values(), key=bank_order)
            if not isinstance(cursor, str) or not cursor or cursor in cursors:
                raise BankLookupInvalid("Invalid bank cursor")
            cursors.add(cursor)
            params["next"] = cursor
        raise BankLookupInvalid("Bank pagination exceeded")

    async def resolve(self, bank_code: str, account_number: str) -> str | None:
        if self.client is None:
            return None
        try:
            data = await self.client.request(
                "GET",
                "/bank/resolve",
                params={"bank_code": bank_code, "account_number": account_number},
            )
        except PaystackMalformedResponseError:
            raise BankLookupInvalid("Invalid account response") from None
        except (PaystackRejectedError, PaystackOutcomeUnknownError) as exc:
            if exc.status_code is not None:
                logger.warning(
                    "Paystack bank resolve failed: status=%s bank_code=%s message=%s",
                    exc.status_code,
                    bank_code,
                    exc.message,
                )
            if (
                (isinstance(exc, PaystackOutcomeUnknownError) and exc.status_code != 429)
                or exc.status_code in (401, 403)
                or _PROVIDER_RESTRICTION.search(exc.message)
            ):
                return None
            if exc.status_code in (400, 404, 422) and _PROVIDER_RESOLVE_REFUSAL.search(exc.message):
                raise BankLookupRefused("Account could not be resolved") from None
            raise BankLookupInvalid("Invalid account response") from None
        if (
            not isinstance(data, dict)
            or data.get("account_number") != account_number
            or not isinstance(data.get("account_name"), str)
            or not 2 <= len(data["account_name"].strip()) <= 160
        ):
            raise BankLookupInvalid("Invalid account response")
        return data["account_name"].strip()


def _bank(row: object) -> Bank | None:
    if not isinstance(row, dict):
        raise BankLookupInvalid("Invalid bank row")
    if row.get("active") is False or row.get("is_deleted") is True:
        return None
    code, name = row.get("code"), row.get("name")
    if not isinstance(code, str) or not re.fullmatch(r"[0-9]{3,10}", code):
        raise BankLookupInvalid("Invalid bank code")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 160:
        raise BankLookupInvalid("Invalid bank name")
    return Bank(code, name.strip())


_configured_adapter: tuple[str, BankAdapter] | None = None


def build_bank_adapter(settings: Settings) -> BankAdapter:
    global _configured_adapter
    key = settings.paystack_secret_key
    fingerprint = hashlib.sha256(key.get_secret_value().encode()).hexdigest() if key else "disabled"
    if _configured_adapter is None or _configured_adapter[0] != fingerprint:
        _configured_adapter = (
            fingerprint,
            BankAdapter(PaystackClient(key.get_secret_value()) if key else None),
        )
    return _configured_adapter[1]

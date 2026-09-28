"""Paystack payment adapter built from Paystack's public API documentation.

Nothing here is reachable without ``PAYSTACK_SECRET_KEY``: the factory returns the
disabled adapter while the key is blank. Tests inject an ``httpx`` transport and
never touch the network.
"""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

import httpx

from app.adapters.payments.provider import (
    CheckoutRequest,
    CheckoutSession,
    DisabledPaymentGatewayAdapter,
    PaymentWebhookAuthenticationError,
    PaymentWebhookPayloadError,
    VerifiedPaymentEvent,
)
from app.core.config import Settings

PAYSTACK_API_BASE_URL = "https://api.paystack.co"
PAYSTACK_TIMEOUT = httpx.Timeout(20.0)
PAYSTACK_PROVIDER_NAME = "paystack"

_SIGNATURE_RE = re.compile(r"[0-9a-f]{128}")
_SUBUNITS_RE = re.compile(r"[0-9]+")
_TRANSACTION_REFERENCE_RE = re.compile(r"[A-Za-z0-9.=-]{1,100}")
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_CENT = Decimal("0.01")


class PaystackError(ValueError):
    """A Paystack call did not produce a usable, verified result."""


class PaystackOutcomeUnknownError(PaystackError):
    """Timeout, transport failure, 5xx, 429 or a non-final status: reconcile later."""


class PaystackNotFoundError(PaystackError):
    """Paystack answered 404 for the requested object."""


class PaystackRejectedError(PaystackError):
    """Paystack definitively refused the request, or its answer failed our checks."""


def paystack_key_mode(secret_key: str) -> str:
    if secret_key.startswith("sk_live_"):
        return "live"
    if secret_key.startswith("sk_test_"):
        return "test"
    raise ValueError("Paystack secret key has an unknown prefix")


def to_subunits(amount: Decimal | str) -> int:
    try:
        value = Decimal(str(amount))
    except InvalidOperation as exc:
        raise ValueError("Amount is not a decimal") from exc
    if not value.is_finite() or value <= 0 or value != value.quantize(_CENT):
        raise ValueError("Amount must be positive with at most two decimal places")
    return int(value * 100)


def from_subunits(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Subunit amount is invalid")
    if isinstance(value, int):
        subunits = value
    elif isinstance(value, str) and _SUBUNITS_RE.fullmatch(value):
        subunits = int(value)
    else:
        raise ValueError("Subunit amount is invalid")
    if subunits <= 0:
        raise ValueError("Subunit amount must be positive")
    return (Decimal(subunits) / 100).quantize(_CENT)


def parse_paystack_time(*values: object) -> datetime:
    for value in values:
        if isinstance(value, str) and value.strip():
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
    raise ValueError("Paystack timestamp is missing")


def canonical_fingerprint(canonical: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def paystack_currency(value: object) -> str:
    currency = str(value).strip().upper()
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise ValueError("Currency is invalid")
    return currency


def _metadata_terms_id(metadata: object) -> str | None:
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata) if metadata.strip() else None
        except json.JSONDecodeError:
            return None
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("commercial_terms_id")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


class PaystackClient:
    """Bearer-authenticated JSON client; the secret never leaves the request header."""

    def __init__(
        self,
        secret_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = PAYSTACK_API_BASE_URL,
    ) -> None:
        self.mode = paystack_key_mode(secret_key)
        self._secret_key = secret_key
        self._transport = transport
        self._base_url = base_url

    def __repr__(self) -> str:
        return f"PaystackClient(mode={self.mode!r}, secret=<redacted>)"

    def verify_signature(self, payload: bytes, signature: str | None) -> bool:
        if not signature or not _SIGNATURE_RE.fullmatch(signature):
            return False
        expected = hmac.new(self._secret_key.encode(), payload, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, signature)

    def require_domain(self, data: dict[str, Any]) -> None:
        if data.get("domain") != self.mode:
            raise PaystackRejectedError("Paystack object belongs to the other key mode")

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                transport=self._transport,
                timeout=PAYSTACK_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self._secret_key}",
                    "Accept": "application/json",
                },
            ) as client:
                response = await client.request(method, path, json=json_body, params=params)
        except httpx.HTTPError as exc:
            raise PaystackOutcomeUnknownError("Paystack request outcome is unknown") from exc
        status_code = response.status_code
        if status_code >= 500 or status_code == 429:
            raise PaystackOutcomeUnknownError("Paystack request outcome is unknown")
        if status_code == 404:
            raise PaystackNotFoundError("Paystack object was not found")
        if status_code >= 400:
            raise PaystackRejectedError(f"Paystack rejected the request ({status_code})")
        try:
            body = response.json()
        except ValueError as exc:
            raise PaystackOutcomeUnknownError("Paystack response is not JSON") from exc
        if not isinstance(body, dict) or body.get("status") not in {True, False}:
            raise PaystackOutcomeUnknownError("Paystack response envelope is malformed")
        if body["status"] is False:
            raise PaystackRejectedError("Paystack rejected the request")
        return body.get("data")


@dataclass(frozen=True, slots=True)
class PaystackRefund:
    refund_id: str
    status: str
    amount: Decimal
    currency: str


def _refund(data: object, client: PaystackClient) -> PaystackRefund:
    if not isinstance(data, dict):
        raise PaystackOutcomeUnknownError("Paystack refund response is malformed")
    try:
        client.require_domain(data)
        refund_id = str(data["id"])
        status = str(data["status"])
        if not refund_id or not status:
            raise ValueError
        return PaystackRefund(
            refund_id=refund_id,
            status=status,
            amount=from_subunits(data["amount"]),
            currency=paystack_currency(data["currency"]),
        )
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise PaystackOutcomeUnknownError("Paystack refund response is malformed") from exc


class PaystackPaymentGatewayAdapter:
    provider_name = PAYSTACK_PROVIDER_NAME

    def __init__(self, client: PaystackClient) -> None:
        self.client = client

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        reference = request.idempotency_key
        if not _TRANSACTION_REFERENCE_RE.fullmatch(reference):
            raise ValueError("Checkout reference has characters Paystack does not allow")
        if not _EMAIL_RE.fullmatch(request.customer_reference):
            raise ValueError("Paystack checkout needs the customer's email address")
        if not request.commercial_terms_id.strip() or not request.organization_id.strip():
            raise ValueError("Checkout needs commercial terms and organization references")
        body = {
            "email": request.customer_reference,
            "amount": str(to_subunits(request.amount)),
            "currency": paystack_currency(request.currency),
            "reference": reference,
            "callback_url": request.return_url,
            "metadata": json.dumps(
                {
                    "commercial_terms_id": request.commercial_terms_id.strip(),
                    "organization_id": request.organization_id.strip(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        data = await self.client.request("POST", "/transaction/initialize", json_body=body)
        if (
            not isinstance(data, dict)
            or data.get("reference") != reference
            or not isinstance(data.get("authorization_url"), str)
            or not data["authorization_url"].startswith("https://")
        ):
            raise PaystackOutcomeUnknownError("Paystack checkout response is malformed")
        return CheckoutSession(
            provider_checkout_id=reference, checkout_url=data["authorization_url"]
        )

    def classify_webhook(self, payload: bytes, signature: str | None) -> tuple[str, bool]:
        """Authenticate, then report the event name and whether it is a Cardvert payment."""
        if not self.client.verify_signature(payload, signature):
            raise PaymentWebhookAuthenticationError("Payment webhook signature is invalid")
        try:
            body = json.loads(payload)
            event = body["event"]
            data = body["data"]
            if not isinstance(event, str) or not event or not isinstance(data, dict):
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise PaymentWebhookPayloadError("Payment webhook payload is invalid") from exc
        is_payment = event == "charge.success" and _metadata_terms_id(data.get("metadata"))
        return event, bool(is_payment)

    async def parse_webhook(self, payload: bytes, signature: str) -> VerifiedPaymentEvent:
        if not self.client.verify_signature(payload, signature):
            raise PaymentWebhookAuthenticationError("Payment webhook signature is invalid")
        try:
            body = json.loads(payload)
            data = body["data"]
            if (
                body["event"] != "charge.success"
                or not isinstance(data, dict)
                or data.get("status") != "success"
            ):
                raise ValueError
            return self._transaction_event(data)
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise PaymentWebhookPayloadError("Payment webhook payload is invalid") from exc

    async def verify_transaction(self, transaction_id: str) -> VerifiedPaymentEvent:
        data = await self.client.request(
            "GET", f"/transaction/verify/{quote(transaction_id, safe='')}"
        )
        if not isinstance(data, dict) or data.get("reference") != transaction_id:
            raise PaystackOutcomeUnknownError("Paystack verification response is malformed")
        if data.get("status") not in {"success", "failed"}:
            raise PaystackOutcomeUnknownError("Paystack transaction is not final")
        try:
            return self._transaction_event(data)
        except PaystackError:
            raise
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise PaystackOutcomeUnknownError(
                "Paystack verification response is malformed"
            ) from exc

    def _transaction_event(self, data: dict[str, Any]) -> VerifiedPaymentEvent:
        self.client.require_domain(data)
        succeeded = data["status"] == "success"
        event_name = "charge.success" if succeeded else "charge.failed"
        reference = data["reference"]
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError("Paystack reference is missing")
        terms_id = _metadata_terms_id(data.get("metadata"))
        if terms_id is None:
            raise ValueError("Paystack transaction carries no Cardvert terms reference")
        amount = from_subunits(data["amount"])
        currency = paystack_currency(data["currency"])
        occurred_at = parse_paystack_time(
            data.get("paid_at"),
            data.get("paidAt"),
            data.get("transaction_date"),
            data.get("created_at"),
            data.get("createdAt"),
        )
        customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
        authorization = (
            data.get("authorization") if isinstance(data.get("authorization"), dict) else {}
        )
        full_name = " ".join(
            str(part).strip()
            for part in (customer.get("first_name"), customer.get("last_name"))
            if part and str(part).strip()
        )
        payer_name = (
            full_name
            or str(authorization.get("account_name") or "").strip()
            or str(customer.get("customer_code") or "").strip()
        )
        if not payer_name:
            raise ValueError("Paystack payer is missing")
        canonical = {
            "provider_event_id": f"{event_name}:{reference}",
            "external_transaction_id": reference,
            "event_type": "payment_confirmed" if succeeded else "payment_failed",
            "commercial_terms_id": terms_id,
            "amount": f"{amount:.2f}",
            "currency": currency,
            "payer_name": payer_name,
            "occurred_at": occurred_at.isoformat(),
        }
        return VerifiedPaymentEvent(
            provider_event_id=canonical["provider_event_id"],
            external_transaction_id=reference,
            event_type=canonical["event_type"],
            commercial_terms_id=terms_id,
            amount=amount,
            currency=currency,
            payer_name=payer_name,
            occurred_at=occurred_at,
            evidence_fingerprint=canonical_fingerprint(canonical),
            canonical_payload=canonical,
        )

    async def create_refund(
        self,
        *,
        transaction_reference: str,
        amount: Decimal,
        currency: str,
        merchant_note: str,
    ) -> PaystackRefund:
        """Queue a refund. Paystack has no idempotency key for refunds: after an
        unknown outcome, reconcile with ``list_refunds`` before any retry."""
        if not _TRANSACTION_REFERENCE_RE.fullmatch(transaction_reference):
            raise ValueError("Refund transaction reference is invalid")
        body = {
            "transaction": transaction_reference,
            "amount": to_subunits(amount),
            "currency": paystack_currency(currency),
            "merchant_note": merchant_note,
        }
        return _refund(await self.client.request("POST", "/refund", json_body=body), self.client)

    async def list_refunds(self, transaction_id: str) -> tuple[PaystackRefund, ...]:
        data = await self.client.request("GET", "/refund", params={"transaction": transaction_id})
        if not isinstance(data, list):
            raise PaystackOutcomeUnknownError("Paystack refund list is malformed")
        return tuple(_refund(item, self.client) for item in data)


def build_payment_gateway_adapter(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> PaystackPaymentGatewayAdapter | DisabledPaymentGatewayAdapter:
    if settings.paystack_secret_key is None:
        return DisabledPaymentGatewayAdapter()
    return PaystackPaymentGatewayAdapter(
        PaystackClient(settings.paystack_secret_key.get_secret_value(), transport=transport)
    )

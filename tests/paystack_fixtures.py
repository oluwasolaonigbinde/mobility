"""SYNTHETIC Paystack fixtures.

Hand-built on 26 Sep 2026 from the shapes in Paystack's public API documentation
(transaction, refund, transfer, transfer-recipient and webhook pages). Every
value is invented for tests: no account, key, customer or transfer is real, and
none of these objects were fetched from Paystack.
"""

import copy
import hashlib
import hmac
import json
from typing import Any

import httpx

SYNTHETIC_TEST_KEY = "sk_test_synthetic0000000000000000000000000000"
SYNTHETIC_LIVE_KEY = "sk_live_synthetic0000000000000000000000000000"


def sign(payload: bytes, secret: str = SYNTHETIC_TEST_KEY) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()


def envelope(data: Any, *, status: bool = True, message: str = "ok") -> dict[str, Any]:
    return {"status": status, "message": message, "data": data}


def transaction(
    *,
    reference: str = "cv-synthetic-checkout-0001",
    terms_id: str = "00000000-0000-4000-8000-000000000001",
    organization_id: str = "00000000-0000-4000-8000-000000000002",
    amount: int = 10000,
    status: str = "success",
    domain: str = "test",
    metadata: Any = None,
) -> dict[str, Any]:
    return {
        "id": 900000001,
        "domain": domain,
        "status": status,
        "reference": reference,
        "amount": amount,
        "message": None,
        "gateway_response": "Successful",
        "paid_at": "2026-09-26T09:15:02.000Z" if status == "success" else None,
        "created_at": "2026-09-26T09:14:24.000Z",
        "channel": "card",
        "currency": "NGN",
        "metadata": (
            metadata
            if metadata is not None
            else json.dumps(
                {"commercial_terms_id": terms_id, "organization_id": organization_id}
            )
        ),
        "customer": {
            "id": 1,
            "first_name": "Synthetic",
            "last_name": "Payer",
            "email": "payer@example.invalid",
            "customer_code": "CUS_synthetic0001",
        },
        "authorization": {"account_name": None},
        "transaction_date": "2026-09-26T09:14:24.000Z",
    }


def charge_success(**kwargs: Any) -> dict[str, Any]:
    return {"event": "charge.success", "data": transaction(**kwargs)}


def recipient(
    *,
    account_number: str = "0000000001",
    bank_code: str = "999",
    currency: str = "NGN",
    active: bool = True,
    domain: str = "test",
) -> dict[str, Any]:
    return {
        "active": active,
        "createdAt": "2026-09-26T08:00:00.000Z",
        "currency": currency,
        "domain": domain,
        "id": 700000001,
        "name": "Synthetic Driver",
        "recipient_code": "RCP_synthetic0001",
        "type": "nuban",
        "updatedAt": "2026-09-26T08:00:00.000Z",
        "is_deleted": False,
        "details": {
            "authorization_code": None,
            "account_number": account_number,
            "account_name": "Synthetic Driver",
            "bank_code": bank_code,
            "bank_name": "Synthetic Bank",
        },
    }


def transfer(
    *,
    reference: str,
    amount: int = 10000,
    status: str = "pending",
    transfer_code: str = "TRF_synthetic0001",
    domain: str = "test",
    updated_at: str = "2026-09-26T10:32:40.000Z",
    updated_key: str = "updatedAt",
) -> dict[str, Any]:
    return {
        "amount": amount,
        "createdAt": "2026-09-26T10:32:40.000Z",
        "currency": "NGN",
        "domain": domain,
        "failures": None,
        "id": 800000001,
        "reason": "Cardvert driver payout",
        "reference": reference,
        "source": "balance",
        "source_details": None,
        "status": status,
        "titan_code": None,
        "transfer_code": transfer_code,
        "transferred_at": None,
        updated_key: updated_at,
        "recipient": recipient(),
    }


def transfer_event(event: str, **kwargs: Any) -> dict[str, Any]:
    status = {"transfer.success": "success", "transfer.failed": "failed"}.get(event, "reversed")
    return {"event": event, "data": transfer(status=status, **kwargs)}


def refund(*, status: str = "pending", amount: int = 10000, domain: str = "test") -> dict:
    return {
        "transaction": {"id": 900000001, "reference": "cv-synthetic-checkout-0001"},
        "integration": 1,
        "deducted_amount": 0,
        "merchant_note": "Synthetic refund",
        "status": status,
        "currency": "NGN",
        "domain": domain,
        "amount": amount,
        "id": 600000001,
        "createdAt": "2026-09-26T11:00:00.000Z",
    }


def payload(body: dict[str, Any]) -> bytes:
    return json.dumps(body, separators=(",", ":")).encode()


class RecordingTransport(httpx.AsyncBaseTransport):
    """Replays queued synthetic responses and records every request."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def queue(self, *responses: httpx.Response | Exception) -> None:
        self.responses.extend(responses)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        self.requests.append(request)
        if not self.responses:
            raise AssertionError(f"unexpected Paystack request {request.method} {request.url}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def json_bodies(self) -> list[Any]:
        return [json.loads(item.content) if item.content else None for item in self.requests]


def ok(data: Any) -> httpx.Response:
    return httpx.Response(200, json=envelope(copy.deepcopy(data)))

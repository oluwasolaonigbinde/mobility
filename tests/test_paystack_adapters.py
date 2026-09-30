"""Paystack adapters against SYNTHETIC recorded fixtures; no network is used."""

import asyncio
import json
from decimal import Decimal

import httpx
import pytest
from paystack_fixtures import (
    SYNTHETIC_LIVE_KEY,
    SYNTHETIC_TEST_KEY,
    RecordingTransport,
    charge_success,
    ok,
    payload,
    recipient,
    refund,
    sign,
    transaction,
    transfer,
    transfer_event,
)
from pydantic import ValidationError

from app.adapters.disbursement import (
    DisabledDisbursementAdapter,
    DisbursementInstruction,
    ProviderLookupStatus,
)
from app.adapters.disbursement.paystack import (
    PaystackDisbursementAdapter,
    TransferDestination,
    build_disbursement_adapter,
    paystack_transfer_reference,
)
from app.adapters.disbursement.provider import DisbursementUnavailableError
from app.adapters.payments import (
    CheckoutRequest,
    DisabledPaymentGatewayAdapter,
    PaymentWebhookAuthenticationError,
    PaymentWebhookPayloadError,
)
from app.adapters.payments.paystack import (
    PaystackClient,
    PaystackNotFoundError,
    PaystackOutcomeUnknownError,
    PaystackPaymentGatewayAdapter,
    PaystackRejectedError,
    build_payment_gateway_adapter,
    from_subunits,
    paystack_key_mode,
    to_subunits,
)
from app.core.config import Settings

KEY = "a" * 64
DESTINATION = TransferDestination(
    account_name="Synthetic Driver", account_number="0000000001", bank_code="999"
)
UNKNOWN_RESPONSES = [
    httpx.ReadTimeout("synthetic timeout"),
    httpx.ConnectError("synthetic connect failure"),
    httpx.Response(500, json={"status": False}),
    httpx.Response(503, text="unavailable"),
    httpx.Response(429, json={"status": False}),
    httpx.Response(200, text="not json"),
    httpx.Response(200, json={"message": "no status"}),
]


def payments(transport: RecordingTransport, key: str = SYNTHETIC_TEST_KEY):
    return PaystackPaymentGatewayAdapter(PaystackClient(key, transport=transport))


def instruction(amount: str = "100.00") -> DisbursementInstruction:
    return DisbursementInstruction(
        line_id="line-1",
        idempotency_key=KEY,
        instruction={
            "ledger_entry_id": "ledger-1",
            "payee_version_id": "payee-v1",
            "bank_account_version_id": "account-v1",
            "amount": amount,
            "currency": "NGN",
        },
        instruction_fingerprint="f" * 64,
    )


def transfers(transport: RecordingTransport, *, resolver=True, key=SYNTHETIC_TEST_KEY):
    seen: list[DisbursementInstruction] = []

    async def resolve(item: DisbursementInstruction) -> TransferDestination:
        seen.append(item)
        return DESTINATION

    adapter = PaystackDisbursementAdapter(
        PaystackClient(key, transport=transport),
        destination_resolver=resolve if resolver else None,
    )
    return adapter, seen


# --- signature (AC1) ---------------------------------------------------------------


def test_webhook_signature_is_hmac_sha512_of_exact_bytes_with_the_secret() -> None:
    adapter = payments(RecordingTransport())
    body = payload(charge_success())
    good = sign(body)
    for bad in (
        "",
        "not-hex",
        good.upper(),
        good[:-1],
        sign(body, "sk_test_another_secret"),
        sign(body + b" "),
    ):
        with pytest.raises(PaymentWebhookAuthenticationError):
            asyncio.run(adapter.parse_webhook(body, bad))
    with pytest.raises(PaymentWebhookAuthenticationError):
        asyncio.run(adapter.parse_webhook(body[:-1] + b"]", good))
    assert asyncio.run(adapter.parse_webhook(body, good)).event_type == "payment_confirmed"


def test_client_repr_and_errors_never_contain_the_secret() -> None:
    transport = RecordingTransport(httpx.Response(400, json={"status": False}))
    client = PaystackClient(SYNTHETIC_TEST_KEY, transport=transport)
    assert SYNTHETIC_TEST_KEY not in repr(client)
    with pytest.raises(PaystackRejectedError) as error:
        asyncio.run(client.request("GET", "/transfer/TRF_x"))
    assert SYNTHETIC_TEST_KEY not in str(error.value)
    assert transport.requests[0].headers["Authorization"] == f"Bearer {SYNTHETIC_TEST_KEY}"
    assert repr(DESTINATION) == "TransferDestination(<redacted>)"


# --- payment webhook and verification (AC2, AC3) ------------------------------------


def test_charge_success_webhook_maps_to_canonical_confirmed_event() -> None:
    adapter = payments(RecordingTransport())
    body = payload(charge_success(amount=12345))
    event = asyncio.run(adapter.parse_webhook(body, sign(body)))
    assert event.provider_event_id == "charge.success:cv-synthetic-checkout-0001"
    assert event.external_transaction_id == "cv-synthetic-checkout-0001"
    assert event.amount == Decimal("123.45")
    assert event.currency == "NGN"
    assert event.commercial_terms_id == "00000000-0000-4000-8000-000000000001"
    assert event.payer_name == "Synthetic Payer"
    assert event.occurred_at.isoformat() == "2026-09-26T09:15:02+00:00"
    reserialized = json.dumps(json.loads(body), indent=2, sort_keys=True).encode()
    again = asyncio.run(adapter.parse_webhook(reserialized, sign(reserialized)))
    assert again.canonical_payload == event.canonical_payload
    assert again.evidence_fingerprint == event.evidence_fingerprint


@pytest.mark.parametrize(
    "body",
    [
        {"event": "transfer.success", "data": transaction()},
        {"event": "charge.success", "data": transaction(status="failed")},
        charge_success(metadata={"other": "value"}),
        charge_success(metadata="{broken json"),
        charge_success(domain="live"),
        charge_success(amount=0),
        {"event": "charge.success"},
        {"event": "charge.success", "data": "not an object"},
        {"event": "charge.success", "data": []},
        [],
    ],
)
def test_charge_webhook_payload_refusals(body) -> None:
    adapter = payments(RecordingTransport())
    raw = payload(body) if isinstance(body, dict) else b"[]"
    with pytest.raises(PaymentWebhookPayloadError):
        asyncio.run(adapter.parse_webhook(raw, sign(raw)))


def test_payer_name_falls_back_to_account_name_then_customer_code() -> None:
    adapter = payments(RecordingTransport())
    body = charge_success(
        metadata={"commercial_terms_id": "terms-1", "organization_id": "org-1"}
    )
    body["data"]["customer"].update(first_name=None, last_name=" ")
    body["data"]["authorization"]["account_name"] = "Synthetic Account"
    raw = payload(body)
    assert asyncio.run(adapter.parse_webhook(raw, sign(raw))).payer_name == "Synthetic Account"
    body["data"]["authorization"]["account_name"] = None
    raw = payload(body)
    assert asyncio.run(adapter.parse_webhook(raw, sign(raw))).payer_name == "CUS_synthetic0001"
    body["data"]["customer"]["customer_code"] = ""
    raw = payload(body)
    with pytest.raises(PaymentWebhookPayloadError):
        asyncio.run(adapter.parse_webhook(raw, sign(raw)))


def test_classify_webhook_separates_cardvert_charges_from_other_signed_events() -> None:
    adapter = payments(RecordingTransport())
    cases = {
        payload(charge_success()): ("charge.success", True),
        payload(charge_success(metadata="")): ("charge.success", False),
        payload(transfer_event("transfer.success", reference="cvp_x")): (
            "transfer.success",
            False,
        ),
        payload({"event": "refund.processed", "data": {"status": "processed"}}): (
            "refund.processed",
            False,
        ),
    }
    for raw, expected in cases.items():
        assert adapter.classify_webhook(raw, sign(raw)) == expected
    with pytest.raises(PaymentWebhookAuthenticationError):
        adapter.classify_webhook(b"{}", "0" * 128)
    for raw in (b"not json", payload({"event": 7, "data": {}}), payload({"event": "x"})):
        with pytest.raises(PaymentWebhookPayloadError):
            adapter.classify_webhook(raw, sign(raw))


def test_verify_transaction_matches_webhook_identity_and_maps_failure() -> None:
    reference = "cv-synthetic-checkout-0001"
    transport = RecordingTransport(ok(transaction()), ok(transaction(status="failed")))
    adapter = payments(transport)
    webhook_body = payload(charge_success())
    webhook = asyncio.run(adapter.parse_webhook(webhook_body, sign(webhook_body)))
    verified = asyncio.run(adapter.verify_transaction(reference))
    assert verified.provider_event_id == webhook.provider_event_id
    assert verified.canonical_payload == webhook.canonical_payload
    assert verified.evidence_fingerprint == webhook.evidence_fingerprint
    failed = asyncio.run(adapter.verify_transaction(reference))
    assert failed.event_type == "payment_failed"
    assert failed.provider_event_id == f"charge.failed:{reference}"
    assert transport.requests[0].method == "GET"
    assert transport.requests[0].url.path == f"/transaction/verify/{reference}"


@pytest.mark.parametrize(
    "response",
    [
        *UNKNOWN_RESPONSES,
        ok(transaction(status="pending")),
        ok(transaction(status="abandoned")),
        ok(transaction(status="ongoing")),
        ok(transaction(reference="someone-else")),
        ok(transaction(amount=-5)),
        ok(None),
    ],
)
def test_verify_transaction_uncertainty_is_never_paid_or_failed(response) -> None:
    adapter = payments(RecordingTransport(response))
    with pytest.raises(PaystackOutcomeUnknownError):
        asyncio.run(adapter.verify_transaction("cv-synthetic-checkout-0001"))


def test_verify_transaction_rejects_the_other_key_mode_and_missing_objects() -> None:
    adapter = payments(RecordingTransport(ok(transaction(domain="live"))))
    with pytest.raises(PaystackRejectedError):
        asyncio.run(adapter.verify_transaction("cv-synthetic-checkout-0001"))
    adapter = payments(RecordingTransport(httpx.Response(404, json={"status": False})))
    with pytest.raises(PaystackNotFoundError):
        asyncio.run(adapter.verify_transaction("cv-synthetic-checkout-0001"))


# --- checkout (AC4) ----------------------------------------------------------------


def checkout(**overrides) -> CheckoutRequest:
    values = {
        "idempotency_key": "cv-synthetic-checkout-0001",
        "commercial_terms_id": "terms-1",
        "organization_id": "org-1",
        "amount": Decimal("150.50"),
        "currency": "ngn",
        "customer_reference": "payer@example.invalid",
        "return_url": "https://app.example.invalid/billing/return",
    }
    values.update(overrides)
    return CheckoutRequest(**values)


def test_create_checkout_sends_the_documented_initialize_request() -> None:
    transport = RecordingTransport(
        ok(
            {
                "authorization_url": "https://checkout.paystack.com/synthetic",
                "access_code": "synthetic",
                "reference": "cv-synthetic-checkout-0001",
            }
        )
    )
    session = asyncio.run(payments(transport).create_checkout(checkout()))
    assert session.checkout_url == "https://checkout.paystack.com/synthetic"
    assert session.provider_checkout_id == "cv-synthetic-checkout-0001"
    request = transport.requests[0]
    assert (request.method, request.url.path) == ("POST", "/transaction/initialize")
    assert request.url.host == "api.paystack.co"
    assert request.headers["Authorization"] == f"Bearer {SYNTHETIC_TEST_KEY}"
    body = transport.json_bodies()[0]
    assert body == {
        "email": "payer@example.invalid",
        "amount": "15050",
        "currency": "NGN",
        "reference": "cv-synthetic-checkout-0001",
        "callback_url": "https://app.example.invalid/billing/return",
        "metadata": '{"commercial_terms_id":"terms-1","organization_id":"org-1"}',
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"idempotency_key": "bad reference!"},
        {"customer_reference": "not-an-email"},
        {"amount": Decimal("1.005")},
        {"amount": Decimal("0")},
        {"commercial_terms_id": " "},
        {"currency": "N1"},
    ],
)
def test_create_checkout_refuses_invalid_input_before_any_request(overrides) -> None:
    transport = RecordingTransport()
    with pytest.raises(ValueError):
        asyncio.run(payments(transport).create_checkout(checkout(**overrides)))
    assert transport.requests == []


@pytest.mark.parametrize(
    "authorization_url",
    [
        "http://checkout.paystack.com/insecure",
        "https://evil.example/redirect",
        "https://user@checkout.paystack.com/credentialed",
        "https://checkout.paystack.com:444/nonstandard-port",
    ],
)
def test_create_checkout_malformed_answer_is_unknown(authorization_url: str) -> None:
    transport = RecordingTransport(
        ok({"authorization_url": authorization_url, "reference": "cv-synthetic-checkout-0001"})
    )
    with pytest.raises(PaystackOutcomeUnknownError):
        asyncio.run(payments(transport).create_checkout(checkout()))


# --- refunds (AC5) -----------------------------------------------------------------


def test_refund_request_and_list_parse_and_uncertainty_is_unknown() -> None:
    transport = RecordingTransport(
        ok(refund()),
        ok([refund(status="processed"), refund(status="failed", amount=500)]),
        httpx.ReadTimeout("synthetic timeout"),
        ok(refund(domain="live")),
        ok({"id": 1}),
        ok({"not": "a list"}),
    )
    adapter = payments(transport)
    created = asyncio.run(
        adapter.create_refund(
            transaction_reference="cv-synthetic-checkout-0001",
            amount=Decimal("100.00"),
            currency="NGN",
            merchant_note="Synthetic refund",
        )
    )
    assert (created.refund_id, created.status, created.amount) == (
        "600000001",
        "pending",
        Decimal("100.00"),
    )
    assert transport.json_bodies()[0] == {
        "transaction": "cv-synthetic-checkout-0001",
        "amount": 10000,
        "currency": "NGN",
        "merchant_note": "Synthetic refund",
    }
    listed = asyncio.run(adapter.list_refunds("900000001"))
    assert [item.status for item in listed] == ["processed", "failed"]
    assert listed[1].amount == Decimal("5.00")
    assert transport.requests[1].url.params["transaction"] == "900000001"
    refund_args = {
        "transaction_reference": "cv-synthetic-checkout-0001",
        "amount": Decimal("1.00"),
        "currency": "NGN",
        "merchant_note": "x",
    }
    for _ in range(3):  # timeout, other key mode, malformed: money may have moved
        with pytest.raises(PaystackOutcomeUnknownError):
            asyncio.run(adapter.create_refund(**refund_args))
    with pytest.raises(PaystackOutcomeUnknownError):
        asyncio.run(adapter.list_refunds("900000001"))
    with pytest.raises(ValueError):
        asyncio.run(adapter.create_refund(**{**refund_args, "transaction_reference": "a b"}))


# --- transfers (AC6, AC7, AC9) ------------------------------------------------------


def test_transfer_reference_is_deterministic_and_within_paystack_limits() -> None:
    reference = paystack_transfer_reference(KEY)
    assert reference == paystack_transfer_reference(KEY)
    assert reference != paystack_transfer_reference("b" * 64)
    assert 16 <= len(reference) <= 50
    assert all(char in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in reference)
    with pytest.raises(ValueError):
        paystack_transfer_reference("")


def test_submit_creates_verified_recipient_then_transfer_from_frozen_instruction() -> None:
    reference = paystack_transfer_reference(KEY)
    transport = RecordingTransport(ok(recipient()), ok(transfer(reference=reference)))
    adapter, seen = transfers(transport)
    item = instruction()
    submission = asyncio.run(adapter.submit_batch(batch_id="batch-1", instructions=(item,)))
    assert submission.provider_reference == "TRF_synthetic0001"
    assert submission.line_references == {"line-1": "TRF_synthetic0001"}
    assert seen == [item]
    assert [(r.method, r.url.path) for r in transport.requests] == [
        ("POST", "/transferrecipient"),
        ("POST", "/transfer"),
    ]
    recipient_body, transfer_body = transport.json_bodies()
    assert recipient_body == {
        "type": "nuban",
        "name": "Synthetic Driver",
        "account_number": "0000000001",
        "bank_code": "999",
        "currency": "NGN",
    }
    assert transfer_body == {
        "source": "balance",
        "amount": 10000,
        "recipient": "RCP_synthetic0001",
        "reference": reference,
        "reason": "Cardvert driver payout",
        "currency": "NGN",
    }


@pytest.mark.parametrize(
    "returned",
    [
        recipient(account_number="0000000002"),
        recipient(bank_code="058"),
        recipient(currency="GHS"),
        recipient(active=False),
        recipient(domain="live"),
        {"recipient_code": "RCP_x"},
        None,
    ],
)
def test_submit_never_transfers_to_a_mismatched_recipient(returned) -> None:
    transport = RecordingTransport(ok(returned))
    adapter, _ = transfers(transport)
    with pytest.raises(PaystackRejectedError):
        asyncio.run(adapter.submit_batch(batch_id="b", instructions=(instruction(),)))
    assert [r.url.path for r in transport.requests] == ["/transferrecipient"]


def test_submit_duplicate_reference_and_uncertainty_raise_without_a_second_transfer() -> None:
    reference = paystack_transfer_reference(KEY)
    for second in (
        httpx.Response(400, json={"status": False, "message": "Duplicate Transfer Reference"}),
        httpx.ReadTimeout("synthetic timeout"),
        httpx.Response(502, text="bad gateway"),
        ok(transfer(reference=reference, amount=999)),
        ok(transfer(reference="cvp_other")),
        ok(transfer(reference=reference, transfer_code="")),
    ):
        transport = RecordingTransport(ok(recipient()), second)
        adapter, _ = transfers(transport)
        with pytest.raises(
            PaystackRejectedError
            if isinstance(second, httpx.Response) and second.status_code == 400
            else PaystackOutcomeUnknownError
        ):
            asyncio.run(adapter.submit_batch(batch_id="b", instructions=(instruction(),)))
        assert [r.url.path for r in transport.requests].count("/transfer") == 1


def test_submit_without_resolver_fails_closed_and_refuses_multi_line_batches() -> None:
    adapter, _ = transfers(RecordingTransport(), resolver=False)
    assert adapter.capabilities.provider_name == "paystack"
    assert adapter.capabilities.lookup_by_idempotency_key is False
    assert adapter.capabilities.semantic_same_key_idempotency is False
    with pytest.raises(DisbursementUnavailableError):
        asyncio.run(adapter.submit_batch(batch_id="b", instructions=(instruction(),)))
    wired, _ = transfers(RecordingTransport())
    assert wired.capabilities.lookup_by_idempotency_key is True
    assert wired.capabilities.semantic_same_key_idempotency is True
    with pytest.raises(ValueError):
        asyncio.run(wired.submit_batch(batch_id="b", instructions=(instruction(),) * 2))
    with pytest.raises(ValueError):
        asyncio.run(wired.submit_batch(batch_id="b", instructions=(instruction("0.001"),)))


def test_lookup_maps_found_not_found_and_unknown() -> None:
    reference = paystack_transfer_reference(KEY)

    def lookup(response):
        adapter, _ = transfers(RecordingTransport(response))
        return asyncio.run(
            adapter.lookup_line(idempotency_key=KEY, instruction_fingerprint="f" * 64)
        )

    found = lookup(ok(transfer(reference=reference, status="success")))
    assert found.status == ProviderLookupStatus.FOUND
    assert found.provider_transfer_reference == "TRF_synthetic0001"
    assert found.provider_submission_reference == "TRF_synthetic0001"
    assert lookup(httpx.Response(404, json={"status": False})).status == (
        ProviderLookupStatus.NOT_FOUND
    )
    for response in (
        *UNKNOWN_RESPONSES,
        httpx.Response(400, json={"status": False}),
        ok(transfer(reference=reference, domain="live")),
        ok(transfer(reference="cvp_other")),
        ok(transfer(reference=reference, transfer_code="")),
        ok(None),
    ):
        assert lookup(response).status == ProviderLookupStatus.UNKNOWN


def test_transfer_webhooks_map_outcomes_with_stable_event_identity() -> None:
    adapter, _ = transfers(RecordingTransport())
    outcomes = {}
    for event in ("transfer.success", "transfer.failed", "transfer.reversed"):
        raw = payload(transfer_event(event, reference="cvp_ref"))
        evidence = asyncio.run(adapter.verify_webhook(payload=raw, signature=sign(raw)))
        assert evidence.provider_transfer_reference == "TRF_synthetic0001"
        assert evidence.provider_event_id == f"{event}:TRF_synthetic0001"
        assert evidence.occurred_at.isoformat() == "2026-09-26T10:32:40+00:00"
        outcomes[event] = evidence.outcome
    assert outcomes == {
        "transfer.success": "succeeded",
        "transfer.failed": "failed",
        "transfer.reversed": "failed",
    }
    body = transfer_event(
        "transfer.failed",
        reference="cvp_ref",
        updated_key="updated_at",
        updated_at="2026-09-26T11:00:00.000Z",
    )
    raw = payload(body)
    evidence = asyncio.run(adapter.verify_webhook(payload=raw, signature=sign(raw)))
    assert evidence.occurred_at.isoformat() == "2026-09-26T11:00:00+00:00"


def test_transfer_webhook_refusals_are_value_errors() -> None:
    adapter, _ = transfers(RecordingTransport())
    good = payload(transfer_event("transfer.success", reference="cvp_ref"))
    with pytest.raises(ValueError, match="signature"):
        asyncio.run(adapter.verify_webhook(payload=good, signature=sign(good, "sk_test_other")))
    mismatched = transfer_event("transfer.success", reference="cvp_ref")
    mismatched["data"]["status"] = "failed"
    for body in (
        {"event": "charge.success", "data": transaction()},
        transfer_event("transfer.success", reference="cvp_ref", domain="live"),
        transfer_event("transfer.success", reference="cvp_ref", transfer_code=""),
        transfer_event("transfer.success", reference="", transfer_code="TRF_x"),
        transfer_event("transfer.success", reference="cvp_ref", amount=0),
        mismatched,
        {"event": "transfer.success", "data": "not an object"},
        {"event": "transfer.success", "data": []},
    ):
        raw = payload(body)
        with pytest.raises(ValueError, match="payload"):
            asyncio.run(adapter.verify_webhook(payload=raw, signature=sign(raw)))


def test_poll_matches_webhook_evidence_and_non_final_states_raise() -> None:
    adapter, _ = transfers(RecordingTransport())
    raw = payload(transfer_event("transfer.success", reference="cvp_ref"))
    webhook = asyncio.run(adapter.verify_webhook(payload=raw, signature=sign(raw)))
    transport = RecordingTransport(ok(transfer(reference="cvp_ref", status="success")))
    polled = asyncio.run(
        transfers(transport)[0].poll_line(provider_transfer_reference="TRF_synthetic0001")
    )
    assert transport.requests[0].url.path == "/transfer/TRF_synthetic0001"
    assert polled.provider_event_id == webhook.provider_event_id
    assert polled.evidence_fingerprint == webhook.evidence_fingerprint
    assert polled.outcome == "succeeded"
    for response in (
        *UNKNOWN_RESPONSES,
        ok(transfer(reference="cvp_ref", status="pending")),
        ok(transfer(reference="cvp_ref", status="otp")),
        ok(transfer(reference="cvp_ref", status="success", transfer_code="TRF_other")),
        ok(transfer(reference="cvp_ref", status="success", domain="live")),
        ok(transfer(reference="cvp_ref", status="success", amount=0)),
    ):
        poller, _ = transfers(RecordingTransport(response))
        with pytest.raises(ValueError):
            asyncio.run(poller.poll_line(provider_transfer_reference="TRF_synthetic0001"))


# --- settings, factories and money (AC10, AC11, AC12) ------------------------------


def settings_with(key: str | None, environment: str = "test") -> Settings:
    values: dict[str, object] = {"environment": environment, "paystack_secret_key": key}
    if environment not in {"test", "local"}:
        values.update(
            jwt_secret_key="production-secret-with-at-least-32-characters",
            database_url=(
                "postgresql+asyncpg://mobility:synthetic-db-secret@db:5432/mobility?ssl=require"
            ),
            redis_url="rediss://:synthetic-redis-secret@redis:6379/0",
        )
    return Settings(_env_file=None, **values)


def test_blank_key_keeps_both_factories_disabled() -> None:
    for blank in (None, "", "   "):
        built = settings_with(blank)
        assert built.paystack_secret_key is None
        assert isinstance(build_payment_gateway_adapter(built), DisabledPaymentGatewayAdapter)
        assert isinstance(build_disbursement_adapter(built), DisabledDisbursementAdapter)
    configured = settings_with(SYNTHETIC_TEST_KEY)
    assert isinstance(build_payment_gateway_adapter(configured), PaystackPaymentGatewayAdapter)
    assert isinstance(build_disbursement_adapter(configured), PaystackDisbursementAdapter)
    assert SYNTHETIC_TEST_KEY not in repr(configured)


@pytest.mark.parametrize(
    ("key", "environment"),
    [
        ("pk_test_public_key", "test"),
        ("sk_test_", "test"),
        ("sk_test_has space", "staging"),
        ("sk_other_value", "staging"),
        (SYNTHETIC_LIVE_KEY, "test"),
        (SYNTHETIC_LIVE_KEY, "local"),
        (SYNTHETIC_LIVE_KEY, "staging"),
        (SYNTHETIC_TEST_KEY, "production"),
    ],
)
def test_paystack_key_validation_refusals(key: str, environment: str) -> None:
    with pytest.raises(ValidationError) as error:
        settings_with(key, environment)
    if key != "sk_test_":  # the bare prefix is part of the error text itself
        assert key not in str(error.value)


def test_paystack_key_modes_allowed_per_environment() -> None:
    assert settings_with(SYNTHETIC_TEST_KEY, "staging").paystack_secret_key is not None
    assert settings_with(SYNTHETIC_LIVE_KEY, "production").paystack_secret_key is not None
    assert paystack_key_mode(SYNTHETIC_LIVE_KEY) == "live"
    assert paystack_key_mode(SYNTHETIC_TEST_KEY) == "test"
    with pytest.raises(ValueError):
        paystack_key_mode("pk_test_x")


def test_nonlocal_checkout_return_must_match_public_origin() -> None:
    base = {
        "environment": "staging",
        "paystack_secret_key": SYNTHETIC_TEST_KEY,
        "jwt_secret_key": "production-secret-with-at-least-32-characters",
        "database_url": (
            "postgresql+asyncpg://mobility:synthetic-db-secret@db:5432/mobility?ssl=require"
        ),
        "redis_url": "rediss://:synthetic-redis-secret@redis:6379/0",
        "public_origin": "https://cardvert.example-client.com",
    }
    accepted = Settings(
        _env_file=None,
        **base,
        paystack_checkout_return_url=(
            "https://cardvert.example-client.com/advertiser/billing/paystack/return"
        ),
    )
    assert accepted.paystack_checkout_return_url.endswith("/paystack/return")
    with pytest.raises(ValidationError, match="PUBLIC_ORIGIN"):
        Settings(
            _env_file=None,
            **base,
            paystack_checkout_return_url=(
                "https://offsite.example-client.com/advertiser/billing/paystack/return"
            ),
        )


def test_subunit_conversion_is_exact_and_refuses_ambiguity() -> None:
    assert to_subunits(Decimal("0.01")) == 1
    assert to_subunits("1234567.89") == 123456789
    assert to_subunits(Decimal("10")) == 1000
    for bad in (Decimal("0"), Decimal("-1"), Decimal("0.001"), "NaN", "Infinity", "abc"):
        with pytest.raises(ValueError):
            to_subunits(bad)
    assert from_subunits(1) == Decimal("0.01")
    assert from_subunits("5000") == Decimal("50.00")
    for bad in (0, -1, True, 1.5, "1.5", "", "٣", None):
        with pytest.raises(ValueError):
            from_subunits(bad)

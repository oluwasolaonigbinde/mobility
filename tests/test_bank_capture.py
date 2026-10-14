import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt
import pytest

from app.adapters.banks import BankAdapter, BankLookupInvalid
from app.adapters.payments.paystack import PaystackClient
from app.core.errors import AppError
from app.schemas.driver_onboarding import PersonPayeeSubmissionCreate
from app.services.bank_capture import check_account_name, require_bank_check


def adapter(handler):
    return BankAdapter(PaystackClient("sk_test_synthetic", transport=httpx.MockTransport(handler)))


def test_bank_catalog_orders_popular_names_and_follows_all_cursor_pages():
    seen = []

    def response(request):
        seen.append(request.url.params.get("next"))
        rows = (
            [{"code": "058", "name": "Guaranty Trust Bank"}, {"code": "999992", "name": "OPay"}]
            if len(seen) == 1
            else [{"code": "50515", "name": "Moniepoint MFB"}]
        )
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": rows,
                "meta": {"next": "page2" if len(seen) == 1 else None},
            },
        )

    banks = asyncio.run(adapter(response).banks())
    assert seen == [None, "page2"]
    assert [b.code for b in banks] == ["999992", "50515", "058"]
    fallback = asyncio.run(BankAdapter().banks())
    assert [b.name for b in fallback[:9]] == [
        "OPay",
        "Moniepoint",
        "PalmPay",
        "Kuda Bank",
        "GTBank",
        "Access Bank",
        "First Bank of Nigeria",
        "UBA",
        "Zenith Bank",
    ]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_provider_outage_permits_manual_name_fallback(status):
    checked = adapter(lambda _: httpx.Response(status, json={"status": False}))
    assert asyncio.run(checked.resolve("058", "0123456789")) is None


def test_network_timeout_and_unconfigured_provider_permit_fallback():
    def timeout(request):
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    assert asyncio.run(adapter(timeout).resolve("058", "0123456789")) is None
    assert asyncio.run(BankAdapter().resolve("058", "0123456789")) is None


@pytest.mark.parametrize(
    "status,data",
    [
        (400, {"status": False}),
        (404, {"status": False}),
        (200, {"status": True, "data": {"account_number": "1111111111", "account_name": "Wrong"}}),
        (200, {"status": True, "data": {"account_number": "0123456789", "account_name": ""}}),
        (200, {"unexpected": True}),
    ],
)
def test_invalid_provider_responses_never_grant_fallback(status, data):
    with pytest.raises(BankLookupInvalid):
        asyncio.run(
            adapter(lambda _: httpx.Response(status, json=data)).resolve("058", "0123456789")
        )


def payload(receipt, **changes):
    return PersonPayeeSubmissionCreate.model_validate(
        {
            "application_access_token": "synthetic-capability",
            "client_request_id": str(uuid4()),
            "nin": "12345678901",
            "bank_code": "058",
            "account_number": "0123456789",
            "account_name": "TEST DRIVER",
            "driver_license_file_id": str(uuid4()),
            "driver_photo_file_id": str(uuid4()),
            "agreement_version": "1",
            "agreement_accepted": True,
            "bank_check_receipt": receipt,
            "account_name_confirmed": True,
            **changes,
        }
    )


def test_resolved_name_requires_confirmed_exact_identity_account_and_name(settings):
    user_id = uuid4()
    fake = adapter(
        lambda request: httpx.Response(
            200,
            json={
                "status": True,
                "data": [{"code": "058", "name": "GTBank"}]
                if request.url.path == "/bank"
                else {"account_number": "0123456789", "account_name": "TEST DRIVER"},
            },
        )
    )
    result = asyncio.run(
        check_account_name(
            user_id=user_id,
            bank_code="058",
            account_number="0123456789",
            adapter=fake,
            settings=settings,
        )
    )
    assert result.outcome == "resolved" and result.account_name == "TEST DRIVER"
    assert require_bank_check(
        payload(result.bank_check_receipt), user_id=user_id, settings=settings
    )
    for changes in (
        {"account_name_confirmed": False},
        {"account_name": "OTHER DRIVER"},
        {"account_number": "1111111111"},
        {"bank_code": "044"},
        {"bank_check_receipt": "forged"},
    ):
        with pytest.raises(AppError, match="Check your bank"):
            require_bank_check(
                payload(result.bank_check_receipt, **changes), user_id=user_id, settings=settings
            )
    with pytest.raises(AppError):
        require_bank_check(payload(result.bank_check_receipt), user_id=uuid4(), settings=settings)
    claims = jwt.decode(result.bank_check_receipt, settings.jwt_secret_key, algorithms=["HS256"])
    claims["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    expired = jwt.encode(claims, settings.jwt_secret_key, algorithm="HS256")
    with pytest.raises(AppError):
        require_bank_check(payload(expired), user_id=user_id, settings=settings)


def test_unavailable_receipt_binds_fallback_without_confirmation(settings):
    user_id = uuid4()
    result = asyncio.run(
        check_account_name(
            user_id=user_id,
            bank_code="058",
            account_number="0123456789",
            adapter=BankAdapter(),
            settings=settings,
        )
    )
    assert result.outcome == "unavailable" and result.account_name is None
    assert require_bank_check(
        payload(result.bank_check_receipt, account_name_confirmed=False),
        user_id=user_id,
        settings=settings,
    )
    assert "0123456789" not in result.bank_check_receipt
    assert "TEST DRIVER" not in result.bank_check_receipt


@pytest.mark.parametrize(
    "bank,account", [("058", "123"), ("058", "٠١٢٣٤٥٦٧٨٩"), ("999", "0123456789")]
)
def test_invalid_input_never_grants_fallback(settings, bank, account):
    with pytest.raises(AppError):
        asyncio.run(
            check_account_name(
                user_id=uuid4(),
                bank_code=bank,
                account_number=account,
                adapter=BankAdapter(),
                settings=settings,
            )
        )


@pytest.mark.parametrize("status", [0, 1, {}, []])
def test_non_boolean_provider_status_never_authorizes_name_or_fallback(status):
    fake = adapter(
        lambda _: httpx.Response(
            200,
            json={
                "status": status,
                "data": {"account_number": "0123456789", "account_name": "TEST DRIVER"},
            },
        )
    )
    with pytest.raises(BankLookupInvalid):
        asyncio.run(fake.resolve("058", "0123456789"))


def test_provider_http_logs_never_include_account_query_or_returned_name(caplog):
    import logging

    caplog.set_level(logging.INFO, logger="httpx")
    fake = adapter(
        lambda _: httpx.Response(
            200,
            json={
                "status": True,
                "data": {"account_number": "0123456789", "account_name": "PRIVATE DRIVER"},
            },
        )
    )
    assert asyncio.run(fake.resolve("058", "0123456789")) == "PRIVATE DRIVER"
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "bank/resolve" in messages
    assert not any(value in messages for value in ("0123456789", "058", "PRIVATE DRIVER"))


def test_invalid_resolution_never_mints_a_bank_check_receipt(settings):
    class RejectedAccount(BankAdapter):
        async def resolve(self, bank_code, account_number):
            raise BankLookupInvalid("synthetic rejected account")

    with pytest.raises(AppError) as caught:
        asyncio.run(
            check_account_name(
                user_id=uuid4(),
                bank_code="058",
                account_number="0123456789",
                adapter=RejectedAccount(),
                settings=settings,
            )
        )
    assert caught.value.code == "BANK_CHECK_INVALID"


@pytest.mark.parametrize("receipt_kind", ["missing", "unknown_outcome"])
def test_bank_capture_requires_an_explicit_recognized_receipt(settings, receipt_kind):
    user_id = uuid4()
    now = datetime.now(UTC)
    receipt = (
        None
        if receipt_kind == "missing"
        else jwt.encode(
            {
                "kind": "driver-bank-check-v1",
                "sub": str(user_id),
                "bank_code": "058",
                "account_digest": hashlib.sha256(b"0123456789").hexdigest(),
                "outcome": "pending",
                "iat": now,
                "exp": now + timedelta(minutes=15),
            },
            settings.jwt_secret_key,
            algorithm="HS256",
        )
    )
    with pytest.raises(AppError) as caught:
        require_bank_check(payload(receipt), user_id=user_id, settings=settings)
    assert caught.value.code == "BANK_CHECK_INVALID"

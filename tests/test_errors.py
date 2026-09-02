import json
import logging
import time
import tracemalloc

from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.core.observability import (
    JsonLogFormatter,
    redact_log_message,
    scrub_observability_value,
)
from app.main import create_app


def test_app_error_uses_standard_envelope() -> None:
    app = create_app()

    @app.get("/test-error")
    async def test_error() -> None:
        raise AppError("TEST_ERROR", "Test error", status_code=status.HTTP_409_CONFLICT)

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/test-error", headers={"X-Request-ID": "req-test"})

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "error": {
            "code": "TEST_ERROR",
            "message": "Test error",
            "details": {},
            "request_id": "req-test",
        }
    }


def test_unhandled_exception_uses_standard_envelope(monkeypatch) -> None:
    captured: list[Exception] = []
    monkeypatch.setattr("app.core.observability.sentry_sdk.capture_exception", captured.append)
    app = create_app()

    @app.get("/test-unhandled-error")
    async def test_unhandled_error() -> None:
        raise RuntimeError("sensitive internal detail")

    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-unhandled-error", headers={"X-Request-ID": "req-unhandled"})

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "details": {},
            "request_id": "req-unhandled",
        }
    }
    assert len(captured) == 1
    assert isinstance(captured[0], RuntimeError)


def test_error_tracking_is_inert_without_dsn(monkeypatch) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )

    create_app(Settings(sentry_dsn=""))

    assert init_calls == []


def test_error_tracking_uses_privacy_safe_defaults(monkeypatch) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )

    create_app(Settings(sentry_dsn="https://public@example.invalid/1"))

    assert len(init_calls) == 1
    before_send = init_calls[0].pop("before_send")
    assert callable(before_send)
    assert init_calls == [
        {
            "dsn": "https://public@example.invalid/1",
            "release": None,
            "traces_sample_rate": 0.0,
            "send_default_pii": False,
            "include_local_variables": False,
            "max_request_body_size": "never",
        }
    ]

    event = before_send(
        {
            "user": {
                "fullName": "Ada Lovelace",
                "username": "ada.lovelace",
                "email": "ada@example.test",
                "phone_number": "+234 801 234 5678",
                "ip_address": "203.0.113.42",
                "status": "active",
            },
            "extra": {
                "organization_name": "Acme Ads",
                "entity_id": "campaign-123",
                "numeric_entity_id": "0123456789",
                "external_transaction_id": "02079460958",
                "message": (
                    "full_name=Ada\nLovelace status=active "
                    "driver_address=Flat 2, 10 Main Street status=verified "
                    "entity_id=0123456789 external_transaction_id=02079460958 "
                    "phone=02079460958"
                ),
            },
        },
        None,
    )

    assert event["user"] == {
        "fullName": "[REDACTED]",
        "username": "[REDACTED]",
        "email": "[REDACTED]",
        "phone_number": "[REDACTED]",
        "ip_address": "[REDACTED]",
        "status": "active",
    }
    assert event["extra"]["organization_name"] == "Acme Ads"
    assert event["extra"]["entity_id"] == "campaign-123"
    assert event["extra"]["numeric_entity_id"] == "0123456789"
    assert event["extra"]["external_transaction_id"] == "02079460958"
    assert event["extra"]["message"] == (
        "full_name=[REDACTED] status=active "
        "driver_address=[REDACTED] status=verified "
        "entity_id=0123456789 external_transaction_id=02079460958 "
        "phone=[REDACTED]"
    )


def test_observability_scrubs_nested_and_free_form_person_contact_pii() -> None:
    payload = {
        "contact": {
            "name": "Ada Lovelace",
            "emailAddress": "ada@example.test",
            "mobile": "+234 801 234 5678",
            "address": {
                "street": "1 Privacy Lane",
                "postalCode": "900001",
                "city": "Abuja",
                "country_code": "NG",
            },
            "status": "verified",
        },
        "recipients": [
            {
                "first_name": "Grace",
                "last-name": "Hopper",
                "diagnostic_status": "queued",
            }
        ],
        "organization": {
            "name": "Acme Ads",
            "campaign_name": "September Launch",
            "registration_id": "RC-123",
        },
        "entity_id": "campaign-123",
        "driver_address": "14 Driver Close",
        "company_owner_name": "Ada Lovelace",
        "email_hash": "sha256:email-abc123",
        "payload_hash": "sha256:abc123",
        "notes": (
            'full_name="Ada Lovelace" email=ada@example.test '
            "phone=+234-801-234-5678 client_ip=203.0.113.42"
        ),
    }

    scrubbed = scrub_observability_value(payload)

    assert scrubbed["contact"] == {
        "name": "[REDACTED]",
        "emailAddress": "[REDACTED]",
        "mobile": "[REDACTED]",
        "address": {
            "street": "[REDACTED]",
            "postalCode": "[REDACTED]",
            "city": "Abuja",
            "country_code": "NG",
        },
        "status": "verified",
    }
    assert scrubbed["recipients"][0] == {
        "first_name": "[REDACTED]",
        "last-name": "[REDACTED]",
        "diagnostic_status": "queued",
    }
    assert scrubbed["organization"] == {
        "name": "Acme Ads",
        "campaign_name": "September Launch",
        "registration_id": "RC-123",
    }
    assert scrubbed["entity_id"] == "campaign-123"
    assert scrubbed["driver_address"] == "[REDACTED]"
    assert scrubbed["company_owner_name"] == "[REDACTED]"
    assert scrubbed["email_hash"] == "sha256:email-abc123"
    assert scrubbed["payload_hash"] == "sha256:abc123"
    assert scrub_observability_value(
        {"name": "Ada Lovelace", "status": "active"},
        semantic_context="user",
    ) == {"name": "[REDACTED]", "status": "active"}
    assert scrub_observability_value(
        {"name": "Acme Ads", "status": "active"},
        semantic_context="advertiser_organization",
    ) == {"name": "Acme Ads", "status": "active"}

    for sensitive_value in (
        "Ada Lovelace",
        "ada@example.test",
        "+234-801-234-5678",
        "203.0.113.42",
    ):
        assert sensitive_value not in scrubbed["notes"]

    formatter = JsonLogFormatter(service="api", release_revision="revision-123")
    record = logging.LogRecord(
        "app.r13",
        logging.INFO,
        __file__,
        1,
        "payload=%r free=%s",
        (
            payload,
            "contact_email=grace@example.test raw_ip=2001:db8::7",
        ),
        None,
    )
    formatted = json.loads(formatter.format(record))

    for sensitive_value in (
        "Ada Lovelace",
        "ada@example.test",
        "Grace",
        "Hopper",
        "grace@example.test",
        "2001:db8::7",
    ):
        assert sensitive_value not in formatted["message"]
    assert "Acme Ads" in formatted["message"]
    assert "campaign-123" in formatted["message"]
    assert "sha256:email-abc123" in formatted["message"]
    assert "sha256:abc123" in formatted["message"]


def test_r13_correction_handles_adversarial_contexts_and_unquoted_values() -> None:
    mixed_input = {
        "driver_address": "14 Driver Close",
        "company_owner_name": "Ada Lovelace",
        "contact": {
            "organization": {
                "name": "Acme Ads",
                "full_name": "Acme Advertising Limited",
                "owner_name": "Ada Lovelace",
                "reviewer_name": "Grace Hopper",
                "contact_email": "owner@acme.example",
                "status": "active",
            }
        },
        "organization": {
            "contact": {
                "name": "Ada Lovelace",
                "full_name": "Ada Lovelace",
            }
        },
    }
    scrubbed = scrub_observability_value(mixed_input)
    business_full_name = scrub_observability_value(
        {"full_name": "Acme Advertising Limited", "status": "active"},
        semantic_context="advertiser_organization",
    )
    actual = {
        "unquoted_name": redact_log_message("full_name=Ada Lovelace status=active"),
        "local_phone": redact_log_message("phone=020 7946 0958 status=active"),
        "international_phone": redact_log_message("phone=+44 20 7946 0958 status=active"),
        "mixed_context": scrubbed,
        "business_full_name": business_full_name,
        "double_scrub_stable": scrub_observability_value(scrubbed) == scrubbed,
        "semantic_double_scrub_stable": (
            scrub_observability_value(
                business_full_name,
                semantic_context="advertiser_organization",
            )
            == business_full_name
        ),
    }

    assert actual == {
        "unquoted_name": "full_name=[REDACTED] status=active",
        "local_phone": "phone=[REDACTED] status=active",
        "international_phone": "phone=[REDACTED] status=active",
        "mixed_context": {
            "driver_address": "[REDACTED]",
            "company_owner_name": "[REDACTED]",
            "contact": {
                "organization": {
                    "name": "Acme Ads",
                    "full_name": "Acme Advertising Limited",
                    "owner_name": "[REDACTED]",
                    "reviewer_name": "[REDACTED]",
                    "contact_email": "[REDACTED]",
                    "status": "active",
                }
            },
            "organization": {
                "contact": {
                    "name": "[REDACTED]",
                    "full_name": "[REDACTED]",
                }
            },
        },
        "business_full_name": {
            "full_name": "Acme Advertising Limited",
            "status": "active",
        },
        "double_scrub_stable": True,
        "semantic_double_scrub_stable": True,
    }


def test_r13_multiline_and_punctuation_assignment_boundaries() -> None:
    free_text = (
        "full_name=Ada\nLovelace status=active "
        "full_name=Smith, John status=reviewed "
        "driver_address=Flat 2,\n10 Main Street status=verified "
        "contact_address=Unit 3; 5 Privacy Lane status=mailed "
        "entity_id=0123456789 external_transaction_id=02079460958 "
        "phone=02079460958"
    )
    expected_text = (
        "full_name=[REDACTED] status=active "
        "full_name=[REDACTED] status=reviewed "
        "driver_address=[REDACTED] status=verified "
        "contact_address=[REDACTED] status=mailed "
        "entity_id=0123456789 external_transaction_id=02079460958 "
        "phone=[REDACTED]"
    )
    formatter = JsonLogFormatter(service="api", release_revision="revision-123")
    record = logging.LogRecord(
        "app.r13",
        logging.INFO,
        __file__,
        1,
        "%s",
        (free_text,),
        None,
    )

    assert redact_log_message(free_text) == expected_text
    assert json.loads(formatter.format(record))["message"] == expected_text
    assert redact_log_message(expected_text) == expected_text


def test_r13_numeric_identifiers_survive_while_explicit_phone_is_scrubbed() -> None:
    structured = scrub_observability_value(
        {
            "entity_id": "0123456789",
            "external_transaction_id": "02079460958",
            "phone": "02079460958",
            "status": "active",
        }
    )

    assert structured == {
        "entity_id": "0123456789",
        "external_transaction_id": "02079460958",
        "phone": "[REDACTED]",
        "status": "active",
    }
    assert redact_log_message("callback 020 7946 0958 pending") == ("callback [REDACTED] pending")


def test_r13_nested_serialized_structures_scrub_all_observability_sinks(monkeypatch) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )
    create_app(Settings(sentry_dsn="https://public@example.invalid/1"))
    before_send = init_calls[0]["before_send"]
    assert callable(before_send)

    cases = (
        (
            "json",
            '{"user":{"full_name":"Ada Lovelace","status":"active"},'
            '"extra":{"driver_address":"1 Privacy Lane"}}',
            '{"user":{"full_name":[REDACTED],"status":"active"},'
            '"extra":{"driver_address":[REDACTED]}}',
        ),
        (
            "python",
            "{'user': {'full_name': 'Grace Hopper', 'status': 'reviewed'}, "
            "'extra': {'driver_address': '2 Privacy Road'}}",
            "{'user': {'full_name': [REDACTED], 'status': 'reviewed'}, "
            "'extra': {'driver_address': [REDACTED]}}",
        ),
        (
            "json_sensitive_container",
            '{"payload":{"full_name":{"first":"Ada","last":"Lovelace"},'
            '"status":"active"},"entity_id":"0123456789"}',
            '{"payload":{"full_name":[REDACTED],"status":"active"},"entity_id":"0123456789"}',
        ),
        (
            "python_sensitive_container",
            "{'payload': {'driver_address': {'line1': '1 Privacy Lane', "
            "'city': 'Abuja'}, 'status': 'active'}, 'entity_id': '0123456789'}",
            "{'payload': {'driver_address': [REDACTED], 'status': 'active'}, "
            "'entity_id': '0123456789'}",
        ),
        (
            "comma_colon_scalar",
            "full_name=Smith, John: Director status=active",
            "full_name=[REDACTED] status=active",
        ),
        (
            "semicolon_colon_scalar",
            "driver_address=Flat 2; Unit: 4 status=verified",
            "driver_address=[REDACTED] status=verified",
        ),
        (
            "colon_comma_scalar",
            "full_name=Smith: John, Director status=active",
            "full_name=[REDACTED] status=active",
        ),
    )
    formatter = JsonLogFormatter(service="api", release_revision="revision-123")
    actual = {}
    expected_outputs = {}

    for case_name, serialized, expected in cases:
        record = logging.LogRecord(
            "app.r13",
            logging.INFO,
            __file__,
            1,
            "%s",
            (serialized,),
            None,
        )

        actual[(case_name, "direct")] = redact_log_message(serialized)
        actual[(case_name, "formatter")] = json.loads(formatter.format(record))["message"]
        event = before_send({"extra": {"message": serialized}}, None)
        actual[(case_name, "sentry")] = event["extra"]["message"]
        actual[(case_name, "double_scrub")] = redact_log_message(expected)
        for sink in ("direct", "formatter", "sentry", "double_scrub"):
            expected_outputs[(case_name, sink)] = expected

    assert actual == expected_outputs


def test_r13_assignment_traversal_is_bounded_across_observability_sinks(monkeypatch) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )
    create_app(Settings(sentry_dsn="https://public@example.invalid/1"))
    before_send = init_calls[0]["before_send"]
    assert callable(before_send)

    nested_assignments = "x=" * 512 + "full_name=Ada Lovelace status=active"
    formatter = JsonLogFormatter(service="api", release_revision="revision-123")
    record = logging.LogRecord(
        "app.r13",
        logging.INFO,
        __file__,
        1,
        "%s",
        (nested_assignments,),
        None,
    )
    outputs = {}
    for sink, callback in (
        ("direct", lambda: redact_log_message(nested_assignments)),
        ("formatter", lambda: json.loads(formatter.format(record))["message"]),
        (
            "sentry",
            lambda: before_send({"extra": {"message": nested_assignments}}, None)["extra"][
                "message"
            ],
        ),
    ):
        try:
            outputs[sink] = callback()
        except RecursionError:
            outputs[sink] = "RecursionError"

    assert set(outputs) == {"direct", "formatter", "sentry"}
    for output in outputs.values():
        assert output != "RecursionError"
        assert "Ada Lovelace" not in output
        assert "[REDACTED]" in output

    oversized_assignments = "x=" * 2048 + "full_name=Grace Hopper"
    try:
        fail_closed = redact_log_message(oversized_assignments)
    except RecursionError:
        fail_closed = "RecursionError"
    assert fail_closed != "RecursionError"
    assert "Grace Hopper" not in fail_closed
    assert fail_closed.endswith("[REDACTED]")


def test_r13_compound_sensitive_key_families_scrub_every_observability_sink(monkeypatch) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )
    create_app(Settings(sentry_dsn="https://public@example.invalid/1"))
    before_send = init_calls[0]["before_send"]
    assert callable(before_send)

    sensitive = {
        "access_token": "access-value",
        "refresh_token": "refresh-value",
        "client_secret": "client-secret-value",
        "password_hash": "password-hash-value",
        "nin_number": "nin-value",
        "bvn_number": "bvn-value",
        "bank_account_number": "bank-value",
        "bank_account_details": "bank-details-value",
        "date_of_birth": "1990-01-02",
        "passport_number": "passport-value",
    }
    payload = {
        **sensitive,
        "bank_account_version": 7,
        "bank_account_version_id": "version-123",
        "bank_account_match_confirmed": True,
        "entity_id": "0123456789",
        "status": "active",
        "payload_hash": "sha256:payload-safe",
        "source_fingerprint": "source-fingerprint-safe",
    }
    free_text = " ".join(f"{key}={value}" for key, value in payload.items())
    formatter = JsonLogFormatter(service="api", release_revision="revision-123")
    record = logging.LogRecord(
        "app.r13",
        logging.INFO,
        __file__,
        1,
        "structured=%r free=%s",
        (payload, free_text),
        None,
    )

    scrubbed = scrub_observability_value(payload)
    sentry_event = before_send({"extra": {"payload": payload, "message": free_text}}, None)
    formatted = json.loads(formatter.format(record))["message"]

    for key, value in sensitive.items():
        assert scrubbed[key] == "[REDACTED]"
        assert sentry_event["extra"]["payload"][key] == "[REDACTED]"
        assert value not in sentry_event["extra"]["message"]
        assert value not in formatted
    for result in (scrubbed, sentry_event["extra"]["payload"]):
        assert result["bank_account_version"] == 7
        assert result["bank_account_version_id"] == "version-123"
        assert result["bank_account_match_confirmed"] is True
        assert result["entity_id"] == "0123456789"
        assert result["status"] == "active"
        assert result["payload_hash"] == "sha256:payload-safe"
        assert result["source_fingerprint"] == "source-fingerprint-safe"

    for safe_assignment in (
        "bank_account_version=7",
        "bank_account_version_id=version-123",
        "bank_account_match_confirmed=True",
    ):
        assert safe_assignment in sentry_event["extra"]["message"]
        assert safe_assignment in formatted


def test_r13_assignment_scan_is_linear_at_the_candidate_budget() -> None:
    value = "x" * 512
    fields = [f'"field_{index}":"{value}"' for index in range(1023)]
    fields.append('"full_name":"Ada Lovelace"')
    message = "{" + ",".join(fields) + "}"

    started = time.perf_counter()
    redacted = redact_log_message(message)
    elapsed = time.perf_counter() - started

    assert len(message) > 500_000
    assert redacted.endswith('"full_name":[REDACTED]}')
    assert "Ada Lovelace" not in redacted
    assert elapsed < 3.0, f"bounded assignment scan took {elapsed:.3f}s"


def test_r13_nested_assignment_scan_is_linear_at_the_candidate_budget() -> None:
    blob = "x" * 500_000
    nesting = "".join(f'"layer_{index}":{{' for index in range(1022))
    message = "{" + nesting + f'"blob":"{blob}","full_name":"Ada Lovelace"' + "}" * 1023

    started = time.perf_counter()
    redacted = redact_log_message(message)
    nested_elapsed = time.perf_counter() - started

    sensitive_container = f"driver_address={{'blob': '{blob}'}} status=active"
    started = time.perf_counter()
    sensitive_redacted = redact_log_message(sensitive_container)
    sensitive_elapsed = time.perf_counter() - started

    assert len(message) > 500_000
    assert redacted.endswith('"full_name":[REDACTED]' + "}" * 1023)
    assert "Ada Lovelace" not in redacted
    assert sensitive_redacted == "driver_address=[REDACTED] status=active"
    assert nested_elapsed < 3.0, f"nested assignment scan took {nested_elapsed:.3f}s"
    assert sensitive_elapsed < 3.0, (
        f"sensitive nested assignment scan took {sensitive_elapsed:.3f}s"
    )


def test_r13_malformed_quotes_and_brackets_fail_closed_across_observability_sinks(
    monkeypatch,
) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )
    create_app(Settings(sentry_dsn="https://public@example.invalid/1"))
    before_send = init_calls[0]["before_send"]
    assert callable(before_send)

    cases = (
        (
            "ordinary_apostrophe",
            'note=it\'s okay contact_organization={"name":"Acme Ads"} '
            "full_name=Ada Lovelace status=active",
            'note=it\'s okay contact_organization={"name":"Acme Ads"} '
            "full_name=[REDACTED] status=active",
        ),
        (
            "escaped_apostrophe",
            'note=it\\\'s okay contact_organization={"name":"Acme Ads"} '
            "full_name=Ada Lovelace status=active",
            'note=it\\\'s okay contact_organization={"name":"Acme Ads"} '
            "full_name=[REDACTED] status=active",
        ),
        (
            "unmatched_quote",
            'note=\'unknown contact_organization={"name":"Acme Ads"} '
            "full_name=Ada Lovelace status=active",
            "note=[REDACTED]",
        ),
        (
            "unmatched_bracket",
            'note=unknown payload={contact_organization={"name":"Acme Ads"} '
            "full_name=Ada Lovelace status=active",
            "note=unknown payload=[REDACTED]",
        ),
    )
    formatter = JsonLogFormatter(service="api", release_revision="revision-123")

    for case_name, message, expected in cases:
        record = logging.LogRecord(
            "app.r13",
            logging.INFO,
            __file__,
            1,
            "%s",
            (message,),
            None,
        )
        event = before_send({"extra": {"message": message}}, None)
        actual = {
            "direct": redact_log_message(message),
            "structured": scrub_observability_value({"message": message})["message"],
            "formatter": json.loads(formatter.format(record))["message"],
            "sentry": event["extra"]["message"],
            "double_scrub": redact_log_message(redact_log_message(message)),
        }

        assert actual == dict.fromkeys(actual, expected), case_name


def test_r13_malformed_structure_has_bounded_work_and_memory_before_candidates() -> None:
    malformed_brackets = ("([{\n" * 125_000)[:500_000]
    malformed_quote = "note='" + "x" * 500_000

    for case_name, message, expected in (
        ("brackets", malformed_brackets, "[REDACTED]"),
        ("quote", malformed_quote, "note=[REDACTED]"),
    ):
        tracemalloc.start()
        started = time.perf_counter()
        redacted = redact_log_message(message)
        elapsed = time.perf_counter() - started
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert redacted == expected
        assert peak < 8_000_000, f"{case_name} scan peaked at {peak} bytes"
        assert elapsed < 3.0, f"{case_name} scan took {elapsed:.3f}s"


def test_r13_unicode_quote_and_separator_equivalents_scrub_every_observability_sink(
    monkeypatch,
) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )
    create_app(Settings(sentry_dsn="https://public@example.invalid/1"))
    before_send = init_calls[0]["before_send"]
    assert callable(before_send)

    cases = (
        (
            "smart_double",
            "payload={“user”:{“full_name”:“Ada Lovelace”}}",
            "payload={“user”:{“full_name”:[REDACTED]}}",
        ),
        (
            "smart_single",
            "payload={‘user’:{‘full_name’:‘Grace Hopper’}}",
            "payload={‘user’:{‘full_name’:[REDACTED]}}",
        ),
        (
            "quoted_ascii_mixed_separator",
            '"full_name"："Mary Jackson" status=active',
            '"full_name"：[REDACTED] status=active',
        ),
        (
            "full_width_colon",
            "full_name：Mary Jackson status=active",
            "full_name：[REDACTED] status=active",
        ),
        (
            "full_width_equals",
            "full_name＝Katherine Johnson status=active",
            "full_name＝[REDACTED] status=active",
        ),
        (
            "unicode_apostrophe",
            "note=it’s okay contact_organization={“name”:“Acme Ads”} "
            "full_name=Ada Lovelace status=active",
            "note=it’s okay contact_organization={“name”:“Acme Ads”} "
            "full_name=[REDACTED] status=active",
        ),
    )
    formatter = JsonLogFormatter(service="api", release_revision="revision-123")

    for case_name, message, expected in cases:
        record = logging.LogRecord(
            "app.r13",
            logging.INFO,
            __file__,
            1,
            "%s",
            (message,),
            None,
        )
        event = before_send({"extra": {"message": message}}, None)
        actual = {
            "direct": redact_log_message(message),
            "structured": scrub_observability_value({"message": message})["message"],
            "formatter": json.loads(formatter.format(record))["message"],
            "sentry": event["extra"]["message"],
        }

        assert actual == dict.fromkeys(actual, expected), case_name


def test_r13_mismatched_admitted_key_quotes_fail_closed_every_observability_sink(
    monkeypatch,
) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )
    create_app(Settings(sentry_dsn="https://public@example.invalid/1"))
    before_send = init_calls[0]["before_send"]
    assert callable(before_send)

    cases = (
        (
            "ascii_to_smart_double",
            'status=active payload={"full_name”:"Ada Lovelace","status":"active"}',
            "status=active payload={[REDACTED]",
        ),
        (
            "smart_to_ascii_double",
            'status=active payload={“full_name":“Grace Hopper”,"status":"active"}',
            "status=active payload={[REDACTED]",
        ),
        (
            "ascii_to_smart_single",
            "status=active payload={'full_name’:‘Mary Jackson’, 'status':'active'}",
            "status=active payload={[REDACTED]",
        ),
        (
            "smart_to_ascii_single",
            "status=active payload={‘full_name':‘Katherine Johnson’, 'status':'active'}",
            "status=active payload={[REDACTED]",
        ),
    )
    formatter = JsonLogFormatter(service="api", release_revision="revision-123")

    for case_name, message, expected in cases:
        record = logging.LogRecord(
            "app.r13",
            logging.INFO,
            __file__,
            1,
            "%s",
            (message,),
            None,
        )
        event = before_send({"extra": {"message": message}}, None)
        actual = {
            "direct": redact_log_message(message),
            "structured": scrub_observability_value({"message": message})["message"],
            "formatter": json.loads(formatter.format(record))["message"],
            "sentry": event["extra"]["message"],
            "double_scrub": redact_log_message(redact_log_message(message)),
        }

        assert actual == dict.fromkeys(actual, expected), case_name

    quote_symbols = ("'", '"', "‘", "’", "“", "”")
    approved_pairs = {("'", "'"), ('"', '"'), ("‘", "’"), ("“", "”")}
    for opening in quote_symbols:
        for closing in quote_symbols:
            message = f"status=active {opening}full_name{closing}=Ada Lovelace status=reviewed"
            expected = (
                f"status=active {opening}full_name{closing}=[REDACTED] status=reviewed"
                if (opening, closing) in approved_pairs
                else "status=active [REDACTED]"
            )
            record = logging.LogRecord(
                "app.r13",
                logging.INFO,
                __file__,
                1,
                "%s",
                (message,),
                None,
            )
            event = before_send({"extra": {"message": message}}, None)
            actual = {
                "direct": redact_log_message(message),
                "structured": scrub_observability_value({"message": message})["message"],
                "formatter": json.loads(formatter.format(record))["message"],
                "sentry": event["extra"]["message"],
                "double_scrub": redact_log_message(redact_log_message(message)),
            }

            assert actual == dict.fromkeys(actual, expected), (opening, closing)


def test_r13_complete_dotted_keys_scrub_sensitive_families_across_observability_sinks(
    monkeypatch,
) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )
    create_app(Settings(sentry_dsn="https://public@example.invalid/1"))
    before_send = init_calls[0]["before_send"]
    assert callable(before_send)

    large_leading_dots = "." * 4096
    cases = (
        (
            "leading_unquoted_name",
            "status=active .full_name=Ada Lovelace",
            "status=active [REDACTED]",
        ),
        (
            "leading_quoted_password",
            'status=active "..password"=Hidden123',
            "status=active [REDACTED]",
        ),
        (
            "leading_smart_quoted_passport",
            "status=active “...passport.number”：A1234567",
            "status=active [REDACTED]",
        ),
        (
            "large_leading_quoted_safe_bank_path",
            f"status=active '{large_leading_dots}bank_account.version'=7",
            "status=active [REDACTED]",
        ),
        (
            "repeated_leading_mismatched_quote",
            'status=active ”...bank_account.version"=7',
            "status=active [REDACTED]",
        ),
        (
            "repeated_leading_assignment_boundary",
            "full_name=Ada Lovelace ..password=Hidden123 status=active",
            "full_name=[REDACTED] [REDACTED]",
        ),
        (
            "empty_component",
            "status=active full_name.=Ada Lovelace",
            "status=active [REDACTED]",
        ),
        (
            "credential_families",
            "password.value=Hidden123 access_token.value=access-value status=active",
            "password.value=[REDACTED] access_token.value=[REDACTED] status=active",
        ),
        (
            "financial_identity_families",
            "bank_account.details=account-value passport.number=A1234567 status=active",
            "bank_account.details=[REDACTED] passport.number=[REDACTED] status=active",
        ),
        (
            "non_authoritative_bank_paths",
            "bank.account.version=secret bank_account.version.id=secret status=active",
            "bank.account.version=[REDACTED] bank_account.version.id=[REDACTED] status=active",
        ),
        (
            "safe_bank_authority",
            "bank_account.version=7 bank_account.version_id=version-123 "
            "bank_account.match_confirmed=True bank_account_version=8 "
            "bank_account_version_id=version-456 bank_account_match_confirmed=False",
            "bank_account.version=7 bank_account.version_id=version-123 "
            "bank_account.match_confirmed=True bank_account_version=8 "
            "bank_account_version_id=version-456 bank_account_match_confirmed=False",
        ),
    )
    formatter = JsonLogFormatter(service="api", release_revision="revision-123")

    for case_name, message, expected in cases:
        record = logging.LogRecord(
            "app.r13",
            logging.INFO,
            __file__,
            1,
            "%s",
            (message,),
            None,
        )
        event = before_send({"extra": {"message": message}}, None)
        actual = {
            "direct": redact_log_message(message),
            "structured": scrub_observability_value({"message": message})["message"],
            "formatter": json.loads(formatter.format(record))["message"],
            "sentry": event["extra"]["message"],
            "double_scrub": redact_log_message(redact_log_message(message)),
        }

        assert actual == dict.fromkeys(actual, expected), case_name


def test_r13_dotted_path_components_are_exactly_bounded_before_normalization() -> None:
    boundary_key = ".".join(["context"] * 1023 + ["full_name"])
    boundary_message = f"{boundary_key}=Ada Lovelace status=active"
    overflow_key = ".".join(["context"] * 1024 + ["full_name"])
    overflow_message = f"status=active {overflow_key}=Grace Hopper"

    assert redact_log_message(boundary_message) == (f"{boundary_key}=[REDACTED] status=active")
    assert redact_log_message(overflow_message) == "status=active [REDACTED]"

    large_key = "part." * 100_000 + "full_name"
    large_message = f"status=active {large_key}=Mary Jackson"
    tracemalloc.start()
    redacted = redact_log_message(large_message)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(large_message) > 500_000
    assert redacted == "status=active [REDACTED]"
    assert peak < 8_000_000, f"dotted path scan peaked at {peak} bytes"

    leading_dot_message = f"status=active {'.' * 500_000}full_name=Grace Hopper"
    tracemalloc.start()
    leading_dot_redacted = redact_log_message(leading_dot_message)
    _current, leading_dot_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(leading_dot_message) > 500_000
    assert leading_dot_redacted == "status=active [REDACTED]"
    assert leading_dot_peak < 8_000_000, f"leading-dot scan peaked at {leading_dot_peak} bytes"


def test_r13_deep_and_cyclic_structures_terminate_across_observability_sinks(monkeypatch) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.core.observability.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )
    create_app(Settings(sentry_dsn="https://public@example.invalid/1"))
    before_send = init_calls[0]["before_send"]
    assert callable(before_send)

    deep = {"status": "active"}
    cursor = deep
    for _ in range(1500):
        child = {}
        cursor["next"] = child
        cursor = child
    cursor["full_name"] = "Ada Lovelace"
    cyclic = {"status": "queued"}
    cyclic["self"] = cyclic
    payload = {"deep": deep, "cyclic": cyclic, "entity_id": "0123456789"}
    formatter = JsonLogFormatter(service="api", release_revision="revision-123")
    record = logging.LogRecord(
        "app.r13",
        logging.INFO,
        __file__,
        1,
        "%r",
        (payload,),
        None,
    )

    try:
        scrubbed = scrub_observability_value(payload)
        formatted = json.loads(formatter.format(record))["message"]
        sentry_event = before_send({"extra": payload}, None)
    except RecursionError:
        scrubbed = formatted = sentry_event = "RecursionError"

    assert scrubbed != "RecursionError"
    assert formatted != "RecursionError"
    assert sentry_event != "RecursionError"
    assert scrubbed["deep"]["status"] == "active"
    assert scrubbed["cyclic"] == {"status": "queued", "self": "[REDACTED]"}
    assert scrubbed["entity_id"] == "0123456789"
    assert "Ada Lovelace" not in formatted
    assert "[REDACTED]" in formatted
    assert sentry_event["extra"]["cyclic"]["self"] == "[REDACTED]"


def test_r13_ordered_person_business_contexts_cover_structured_and_serialized_values() -> None:
    structured = {
        "contact_organization": {
            "name": "Acme Ads",
            "full_name": "Acme Advertising Limited",
            "owner_name": "Ada Lovelace",
        },
        "company_owner": {
            "name": "Grace Hopper",
            "organization_name": "Acme Ads",
        },
    }
    serialized = (
        '{"user":{"name":"Ada Lovelace","status":"active"},'
        '"contact_organization":{"name":"Acme Ads","owner_name":"Ada Lovelace"},'
        '"company_owner":{"name":"Grace Hopper","organization_name":"Acme Ads"}}'
    )

    assert scrub_observability_value(structured) == {
        "contact_organization": {
            "name": "Acme Ads",
            "full_name": "Acme Advertising Limited",
            "owner_name": "[REDACTED]",
        },
        "company_owner": {
            "name": "[REDACTED]",
            "organization_name": "Acme Ads",
        },
    }
    assert redact_log_message(serialized) == (
        '{"user":{"name":[REDACTED],"status":"active"},'
        '"contact_organization":{"name":"Acme Ads","owner_name":[REDACTED]},'
        '"company_owner":{"name":[REDACTED],"organization_name":"Acme Ads"}}'
    )

import io
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import AppError
from app.core.observability import capture_exception, configure_logging
from app.main import create_app

SECRET = "synthetic-sensitive-value-never-log"


@pytest.mark.parametrize("mode", ["json", "text"])
@pytest.mark.parametrize("service", ["api", "worker"])
def test_database_failure_records_trusted_code_without_sql_or_values(mode, service, logging_state):
    import asyncio

    from asyncpg.exceptions import DeadlockDetectedError
    from sqlalchemy.exc import DBAPIError

    from app.core.observability import begin_job_logging, end_job_logging

    configure_logging(Settings(environment="test", log_format=mode), service=service)
    stream = io.StringIO()
    logging.getLogger().handlers[0].setStream(stream)

    async def emit():
        await begin_job_logging({"job_id": "job-database-safe"})
        try:
            try:
                raise DBAPIError(
                    f"SELECT '{SECRET}'",
                    {"bank_account": SECRET},
                    DeadlockDetectedError(SECRET),
                    connection_invalidated=True,
                )
            except DBAPIError as exc:
                exc.__dict__["_cardvert_request_id"] = "request-database-safe"
                logging.getLogger("arq.worker").exception("database failure %s", SECRET)
        finally:
            await end_job_logging({})

    asyncio.run(emit())
    output = stream.getvalue()
    assert '"sqlstate":"40P01"' in output
    assert '"connection_invalidated":true' in output
    assert "job-database-safe" in output
    assert "request-database-safe" in output
    assert '"function":"emit"' in output
    assert SECRET not in output
    assert "SELECT" not in output
    assert "bank_account" not in output


def test_database_diagnostic_rejects_untrusted_or_malformed_code():
    from asyncpg.exceptions import DeadlockDetectedError
    from sqlalchemy.exc import DBAPIError

    from app.core.observability import exception_diagnostic

    untrusted = RuntimeError(SECRET)
    untrusted.sqlstate = "40P01"
    malformed = DeadlockDetectedError(SECRET)
    malformed.sqlstate = SECRET
    for original in (untrusted, malformed):
        diagnostic = exception_diagnostic(DBAPIError(SECRET, {"secret": SECRET}, original))
        assert "sqlstate" not in diagnostic
        assert SECRET not in json.dumps(diagnostic)


def test_sentry_suppresses_scan_breadcrumbs_and_queued_scan_errors():
    from app.core.observability import _before_breadcrumb, _before_send

    for path in ("/q/private-token", "/api/v1/qr/private-token"):
        scan = {"message": f"GET {path}", "data": {"ip": "203.0.113.42", "user_agent": SECRET}}
        assert _before_breadcrumb(scan, None) is None
        assert _before_send({"request": {"url": f"https://cardvert.invalid{path}"}}, None) is None
        later = _before_send({"breadcrumbs": {"values": [scan, {"message": "ordinary job"}]}}, None)
        assert later["breadcrumbs"]["values"] == [{"message": "event=breadcrumb", "data": {}}]


def test_sentry_formatted_exception_text_and_parameters_are_not_exported():
    from app.core.observability import _before_breadcrumb, _before_send

    breadcrumb = {
        "message": SECRET,
        "params": [SECRET],
        "level": "error",
        "data": {"exception": SECRET, "request_id": "request-safe"},
    }
    assert SECRET not in json.dumps(_before_breadcrumb(breadcrumb, None))
    event = _before_send(
        {
            "logentry": {"formatted": SECRET, "message": "%s", "params": [SECRET]},
            "message": SECRET,
            "extra": {"exception_text": SECRET, "request_id": "request-safe"},
            "breadcrumbs": {"values": [breadcrumb]},
            "exception": {
                "values": [
                    {
                        "type": "RuntimeError",
                        "value": SECRET,
                        "other": SECRET,
                        "stacktrace": {
                            "frames": [
                                {
                                    "module": "app.service",
                                    "function": "run",
                                    "lineno": 42,
                                    "context_line": SECRET,
                                    "vars": {"secret": SECRET},
                                }
                            ]
                        },
                    }
                ]
            },
        },
        None,
    )
    assert SECRET not in json.dumps(event)
    assert event["extra"]["request_id"] == "request-safe"
    assert event["exception"]["values"][0]["stacktrace"]["frames"] == [
        {"module": "app.service", "function": "run", "lineno": 42}
    ]


def test_escaped_error_record_uses_exception_request_correlation(logging_state):
    configure_logging(Settings(environment="test", log_format="json"), service="api")
    stream = io.StringIO()
    logging.getLogger().handlers[0].setStream(stream)
    try:
        raise RuntimeError(SECRET)
    except RuntimeError as exc:
        exc.__dict__["_cardvert_request_id"] = "request-escaped-safe"
        logging.getLogger("uvicorn.error").exception("failed %s", str(exc))
    record = json.loads(stream.getvalue())
    assert record["request_id"] == "request-escaped-safe"
    assert SECRET not in stream.getvalue()


def test_sentry_keeps_escaped_request_and_worker_correlation():
    import asyncio

    from app.core.observability import _before_send, begin_job_logging, end_job_logging

    try:
        raise RuntimeError(SECRET)
    except RuntimeError as exc:
        exc.__dict__["_cardvert_request_id"] = "request-escaped-safe"
        event = _before_send(
            {"exception": {"values": [{"type": "RuntimeError", "value": SECRET}]}},
            {"exc_info": (type(exc), exc, exc.__traceback__)},
        )
    assert event["extra"]["request_id"] == "request-escaped-safe"

    async def job():
        await begin_job_logging({"job_id": "job-safe-1"})
        try:
            event = _before_send({"logentry": {"formatted": SECRET}}, None)
            assert event["extra"]["job_id"] == "job-safe-1"
            assert SECRET not in json.dumps(event)
        finally:
            await end_job_logging({})

    asyncio.run(job())


@pytest.fixture
def logging_state():
    names = (
        "",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "arq",
        "arq.worker",
        "app.core.observability",
    )
    states = [
        (
            logging.getLogger(name),
            logging.getLogger(name).handlers[:],
            logging.getLogger(name).level,
            logging.getLogger(name).propagate,
            logging.getLogger(name).disabled,
        )
        for name in names
    ]
    # In-process Alembic fileConfig disables existing application loggers. Model
    # a fresh API/worker process here and restore the inherited test state after.
    logging.getLogger("app.core.observability").disabled = False
    yield
    for logger, handlers, level, propagate, disabled in states:
        logger.handlers[:] = handlers
        logger.setLevel(level)
        logger.propagate = propagate
        logger.disabled = disabled


@pytest.mark.parametrize("mode", ["json", "text"])
@pytest.mark.parametrize("service", ["api", "worker"])
def test_exception_chain_has_safe_frames_without_sentry(mode, service, logging_state, monkeypatch):
    configure_logging(Settings(environment="test", sentry_dsn="", log_format=mode), service=service)
    stream = io.StringIO()
    handler = logging.getLogger().handlers[0]
    handler.setStream(stream)
    monkeypatch.setattr("app.core.observability.sentry_sdk.capture_exception", lambda exc: None)
    try:
        raise RuntimeError(f"{SECRET} https://private.invalid/bank nin=12345678901")
    except RuntimeError as exc:
        capture_exception(exc)
        logging.getLogger("uvicorn.error").exception("Exception in ASGI application")
        logging.getLogger("arq.worker").exception(
            "job failed", extra={"job_id": "job-safe-1", "unsafe": SECRET}
        )
    result = stream.getvalue()
    assert "RuntimeError" in result
    assert "test_exception_chain_has_safe_frames_without_sentry" in result
    assert "job-safe-1" in result
    assert SECRET not in result
    assert "https://private.invalid" not in result
    assert "12345678901" not in result
    assert "raise RuntimeError" not in result
    if mode == "json":
        assert all(json.loads(line)["service"] == service for line in result.splitlines())


@pytest.mark.parametrize("path", ["/q/scan-token", "/api/v1/qr/scan-token"])
def test_real_scan_failure_suppresses_api_uvicorn_and_telemetry(path, logging_state, monkeypatch):
    settings = Settings(environment="test", sentry_dsn="", log_format="json")
    app = create_app(settings)
    captured = []
    monkeypatch.setattr("app.core.observability.sentry_sdk.capture_exception", captured.append)

    @app.get(path)
    def fail_scan():
        raise RuntimeError(f"{SECRET} destination=https://private.invalid")

    stream = io.StringIO()
    logging.getLogger().handlers[0].setStream(stream)
    response = TestClient(app, raise_server_exceptions=False).get(
        path, headers={"user-agent": "private-scan-agent", "x-forwarded-for": "203.0.113.42"}
    )
    assert response.status_code == 500
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d',
        "203.0.113.42:8000",
        "GET",
        path,
        "1.1",
        500,
    )
    assert captured == []
    assert stream.getvalue() == ""


def test_handled_server_error_keeps_request_correlation(logging_state):
    app = create_app(Settings(environment="test", log_format="json"))

    @app.get("/test-handled-failure")
    def fail():
        raise AppError("TEST_UNAVAILABLE", SECRET, status_code=503)

    stream = io.StringIO()
    logging.getLogger().handlers[0].setStream(stream)
    response = TestClient(app).get(
        "/test-handled-failure", headers={"X-Request-ID": "request-safe-1"}
    )
    assert response.status_code == 503
    result = stream.getvalue()
    assert "request-safe-1" in result
    assert "AppError" in result
    assert SECRET not in result


def test_unhandled_error_keeps_correlation_when_tracking_is_unavailable(logging_state, monkeypatch):
    app = create_app(Settings(environment="test", log_format="json"))

    @app.get("/test-unhandled-failure")
    def fail():
        raise RuntimeError(SECRET)

    def unavailable(exc):
        raise OSError(SECRET)

    monkeypatch.setattr("app.core.observability.sentry_sdk.capture_exception", unavailable)
    stream = io.StringIO()
    logging.getLogger().handlers[0].setStream(stream)
    response = TestClient(app, raise_server_exceptions=False).get(
        "/test-unhandled-failure", headers={"X-Request-ID": "request-safe-2"}
    )
    assert response.status_code == 500
    result = stream.getvalue()
    assert "request-safe-2" in result
    assert "RuntimeError" in result
    diagnostic = next(
        json.loads(line)["exception"] for line in result.splitlines() if '"exception"' in line
    )
    assert any(frame["function"] == "fail" for frame in diagnostic["frames"])
    assert all(set(frame) == {"module", "function", "line"} for frame in diagnostic["frames"])
    assert "error_tracking_unavailable" in result
    assert SECRET not in result

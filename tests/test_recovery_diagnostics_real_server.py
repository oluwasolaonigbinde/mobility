"""Exercise the real Uvicorn access/error chain on loopback, without telemetry I/O."""

import io
import json
import logging
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from app.core.config import Settings
from app.main import create_app


@pytest.mark.parametrize(
    "path", ["/test-escaped-error", "/q/private-scan-token", "/api/v1/qr/private-scan-token"]
)
def test_actual_uvicorn_escape_correlation_and_scan_privacy(path, monkeypatch):
    names = ("", "uvicorn", "uvicorn.error", "uvicorn.access", "arq", "arq.worker")
    saved = [
        (
            logging.getLogger(name),
            logging.getLogger(name).handlers[:],
            logging.getLogger(name).level,
            logging.getLogger(name).propagate,
        )
        for name in names
    ]
    app = create_app(Settings(environment="test", sentry_dsn="", log_format="json"))
    stream = io.StringIO()
    logging.getLogger().handlers[0].setStream(stream)
    captured = []
    monkeypatch.setattr("app.core.observability.sentry_sdk.capture_exception", captured.append)

    @app.get(path)
    async def fail():
        raise RuntimeError(
            "private-exception-value destination=https://private.invalid bank=0123456789"
        )

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                log_config=None,
                access_log=True,
                lifespan="off",
                host="127.0.0.1",
                port=port,
            )
        )
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        try:
            thread.start()
            deadline = time.monotonic() + 5
            while not server.started and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started
            response = httpx.get(
                f"http://127.0.0.1:{port}{path}",
                headers={
                    "X-Request-ID": "request-uvicorn-safe",
                    "User-Agent": "private-scan-agent",
                    "X-Forwarded-For": "203.0.113.42",
                },
            )
            assert response.status_code == 500
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive()
            for logger, handlers, level, propagate in saved:
                logger.handlers[:] = handlers
                logger.setLevel(level)
                logger.propagate = propagate
    output = stream.getvalue()
    for private in (
        "private-exception-value",
        "private-scan-agent",
        "private-scan-token",
        "203.0.113.42",
        "https://private.invalid",
        "0123456789",
    ):
        assert private not in output
    records = [json.loads(line) for line in output.splitlines()]
    if path.startswith("/test-"):
        errors = [
            record
            for record in records
            if record["logger"] == "uvicorn.error" and "exception" in record
        ]
        assert len(errors) == 1
        assert errors[0]["request_id"] == "request-uvicorn-safe"
        assert errors[0]["exception"]["type"] == "RuntimeError"
        assert errors[0]["exception"]["frames"]
        assert len(captured) == 1
    else:
        assert not any("exception" in record for record in records)
        assert not any(record["logger"] == "uvicorn.access" for record in records)
        assert captured == []

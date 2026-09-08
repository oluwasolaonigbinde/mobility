import json
import subprocess
import threading
import time
from contextlib import contextmanager
from http.client import RemoteDisconnected
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def live_caddy(tmp_path, endpoint):
    config = (ROOT / "Caddyfile").read_text().replace("{$EDGE_HOSTNAME}", ":8080", 1)
    config = config.replace(
        "\n\t@public_api",
        '\n\thandle /csp-probe {\n\t\trespond "CSP probe" 200\n\t}\n\n\t@public_api',
        1,
    )
    path = tmp_path / "Caddyfile"
    path.write_text(config)
    container = subprocess.check_output(
        [
            "docker",
            "run",
            "--pull=never",
            "--detach",
            "--rm",
            "--publish",
            "127.0.0.1::8080",
            "--env",
            f"OBJECT_STORAGE_PUBLIC_ENDPOINT_URL={endpoint}",
            "--volume",
            f"{path}:/etc/caddy/Caddyfile:ro",
            "caddy:2.8-alpine",
        ],
        text=True,
    ).strip()
    try:
        details = json.loads(subprocess.check_output(["docker", "inspect", container], text=True))[
            0
        ]
        port = details["NetworkSettings"]["Ports"]["8080/tcp"][0]["HostPort"]
        for attempt in range(40):
            try:
                with urlopen(f"http://127.0.0.1:{port}/csp-probe", timeout=1) as response:
                    policy = response.headers["Content-Security-Policy"]
                break
            except (URLError, RemoteDisconnected):
                if attempt == 39:
                    raise
                time.sleep(0.1)
        yield f"http://127.0.0.1:{port}/csp-probe", policy
    finally:
        subprocess.run(
            ["docker", "stop", "--time", "1", container], check=True, capture_output=True
        )


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("https://objects.example.com", "https://objects.example.com"),
        ("https://objects.example.com:9443/bucket/path", "https://objects.example.com:9443"),
        ("http://[::1]:9000/bucket", "http://[::1]:9000"),
        ("https://*.example.com", ""),
        ("https://objects.example.com; connect-src *", ""),
        ("https://user:password@objects.example.com", ""),
        ("", ""),
    ],
)
def test_live_caddy_csp_uses_only_the_exact_storage_origin(tmp_path, endpoint, expected):
    with live_caddy(tmp_path, endpoint) as (_, policy):
        directives = {parts[0]: parts[1:] for part in policy.split(";") if (parts := part.split())}
        assert directives["connect-src"] == ["'self'", *([expected] if expected else [])]
        assert directives["default-src"] == ["'self'"]
        assert directives["frame-ancestors"] == ["'none'"]
        assert "*" not in policy


def test_browser_upload_accepts_configured_origin_and_blocks_another(tmp_path):
    received = []
    app_origin = ""

    class Storage(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(self.server.server_port)
            self.rfile.read(int(self.headers.get("content-length", "0")))
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", app_origin)
            self.end_headers()

        def log_message(self, *_args):
            pass

    allowed = ThreadingHTTPServer(("127.0.0.1", 0), Storage)
    hostile = ThreadingHTTPServer(("127.0.0.1", 0), Storage)
    for server in (allowed, hostile):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{allowed.server_port}"
    try:
        with live_caddy(tmp_path, endpoint) as (url, _):
            app_origin = url.removesuffix("/csp-probe")
            source = """
                import { chromium } from '@playwright/test';
                import assert from 'node:assert/strict';
                let input = ''; for await (const chunk of process.stdin) input += chunk;
                const args = JSON.parse(input);
                const browser = await chromium.launch({headless: true});
                try {
                    const page = await browser.newPage();
                    await page.goto(args.url);
                    const results = await page.evaluate(async ({allowed, hostile}) => {
                        const upload = async (url) => {
                            const form = new FormData();
                            form.append('file', new Blob(['synthetic upload']), 'test.txt');
                            try { return (await fetch(url, {method:'POST', body:form})).ok; }
                            catch { return false; }
                        };
                        return [await upload(allowed), await upload(hostile)];
                    }, args);
                    assert.deepEqual(results, [true, false]);
                } finally { await browser.close(); }
            """
            browser_result = subprocess.run(
                ["node", "--input-type=module", "-e", source],
                cwd=ROOT / "frontend",
                input=json.dumps(
                    {
                        "url": url,
                        "allowed": endpoint,
                        "hostile": f"http://127.0.0.1:{hostile.server_port}",
                    }
                ),
                text=True,
                capture_output=True,
                timeout=30,
            )
            assert browser_result.returncode == 0, browser_result.stderr
            assert received == [allowed.server_port]
    finally:
        for server in (allowed, hostile):
            server.shutdown()
            server.server_close()

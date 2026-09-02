from pathlib import Path

from fastapi import Request

from app.core.config import Settings
from app.core.rate_limit import login_client_ip

ROOT = Path(__file__).resolve().parents[1]


def test_edge_policy_preserves_required_capabilities_and_denies_framing() -> None:
    caddyfile = (ROOT / "Caddyfile").read_text()

    assert 'Content-Security-Policy "' in caddyfile
    for directive in (
        "default-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "worker-src 'self' blob:",
        "manifest-src 'self'",
    ):
        assert directive in caddyfile
    assert 'X-Frame-Options "DENY"' in caddyfile
    assert "geolocation=(self)" in caddyfile
    assert "screen-wake-lock=(self)" in caddyfile
    assert "clipboard-write=(self)" in caddyfile
    for denied in (
        "accelerometer=()",
        "autoplay=()",
        "display-capture=()",
        "encrypted-media=()",
        "gyroscope=()",
        "magnetometer=()",
        "xr-spatial-tracking=()",
    ):
        assert denied in caddyfile


def test_edge_replaces_every_supported_forwarding_identity() -> None:
    caddyfile = (ROOT / "Caddyfile").read_text()

    for header in (
        "Forwarded",
        "X-Forwarded-For",
        "X-Forwarded-Host",
        "X-Forwarded-Proto",
        "X-Real-IP",
        "CF-Connecting-IP",
        "True-Client-IP",
        "Fly-Client-IP",
        "X-Azure-ClientIP",
        "X-Envoy-External-Address",
    ):
        assert caddyfile.count(f"header_up -{header}") == 2
    assert "header_up -X-Client-IP" not in caddyfile
    assert "header_up -X-Request-ID" not in caddyfile
    assert caddyfile.count("header_up X-Client-IP {http.request.remote.host}") == 2
    assert caddyfile.count("header_up X-Request-ID {http.request.uuid}") == 2


def test_bundled_data_services_are_tls_only_and_materialize_private_keys() -> None:
    compose = (ROOT / "docker-compose.production.yml").read_text()

    assert "hostnossl all all 0.0.0.0/0 reject" in compose
    assert "hostssl all all 0.0.0.0/0 scram-sha-256" in compose
    assert "sslmode=verify-full" in compose
    assert "sslrootcert=/run/secrets/postgres_tls_ca" in compose
    assert "--port 0" in compose
    assert "--tls-port 6379" in compose
    assert "redis-cli --no-auth-warning --tls" in compose
    assert "chmod 0600" in compose
    assert "postgres_tls_key" in compose
    assert "redis_tls_key" in compose


def test_example_environment_requires_external_tls_material_and_no_global_registration_limit(
) -> None:
    example = (ROOT / "production.env.example").read_text()

    for name in (
        "POSTGRES_TLS_CA_FILE",
        "POSTGRES_TLS_CERT_FILE",
        "POSTGRES_TLS_KEY_FILE",
        "REDIS_TLS_CA_FILE",
        "REDIS_TLS_CERT_FILE",
        "REDIS_TLS_KEY_FILE",
    ):
        assert f"{name}=" in example
    assert "ssl=verify-full" in example
    assert "ssl_cert_reqs=required" in example
    assert "DRIVER_REGISTRATION_RATE_LIMIT_GLOBAL" not in example


def test_exact_frontend_peer_relays_distinct_edge_ips_and_rejects_forgery() -> None:
    settings = Settings(
        login_rate_limit_trust_client_ip_header=True,
        login_rate_limit_trusted_proxy_cidrs="10.255.254.10/32",
    )

    def request(peer: str, client_ip: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/auth/login",
                "headers": [(b"x-client-ip", client_ip.encode())],
                "client": (peer, 1234),
                "server": ("api", 8000),
                "scheme": "http",
                "query_string": b"",
            }
        )

    assert login_client_ip(request("10.255.254.10", "198.51.100.8"), settings) == "198.51.100.8"
    assert login_client_ip(request("10.255.254.10", "203.0.113.9"), settings) == "203.0.113.9"
    assert login_client_ip(request("10.255.254.11", "198.51.100.8"), settings) == "10.255.254.11"

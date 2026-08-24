from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_COMPOSE = ROOT / "docker-compose.yml"
PRODUCTION_COMPOSE = ROOT / "docker-compose.production.yml"
STAGING_ENV = ROOT / "staging.env.example"


def compose_config(
    *, profiles: tuple[str, ...] = (), environment: dict[str, str] | None = None
) -> dict:
    command = [
        "docker",
        "compose",
        "-f",
        str(DEVELOPMENT_COMPOSE),
        "-f",
        str(PRODUCTION_COMPOSE),
    ]
    for profile in profiles:
        command.extend(("--profile", profile))
    command.extend(("--env-file", str(STAGING_ENV), "config", "--format", "json"))
    process_environment = os.environ.copy()
    if environment:
        process_environment.update(environment)
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=process_environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_production_render_has_one_public_edge_and_no_development_mounts() -> None:
    model = compose_config()
    services = model["services"]

    assert set(services) == {"api", "db", "edge", "frontend", "redis"}
    assert [port["published"] for port in services["edge"]["ports"]] == ["80", "443", "443"]
    assert all(not service.get("ports") for name, service in services.items() if name != "edge")
    assert services["api"]["command"] == [
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    assert services["api"].get("volumes") is None
    assert all(service["restart"] == "unless-stopped" for service in services.values())
    assert services["frontend"]["environment"]["LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER"] == "false"
    assert services["api"]["environment"]["LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER"] == "false"
    assert services["api"]["environment"]["LOGIN_RATE_LIMIT_TRUSTED_PROXY_CIDRS"] == ""
    assert services["api"]["environment"]["ALLOW_DEMO_SEED"] == "false"
    assert services["api"]["environment"]["PRIVACY_DISCLOSURE_LIVE_AUTHORIZED"] == "false"
    assert services["api"]["environment"]["PRIVACY_LEGAL_APPROVAL_REFERENCE"] == ""
    assert model["networks"]["app"]["internal"] is True
    assert model["networks"]["data"]["internal"] is True
    assert model["networks"]["edge"].get("internal", False) is False
    assert model["networks"]["egress"].get("internal", False) is False
    assert "egress" in services["api"]["networks"]
    assert "egress" in services["frontend"]["networks"]
    assert services["api"]["networks"]["egress"]["gw_priority"] == 1
    assert services["frontend"]["networks"]["egress"]["gw_priority"] == 1
    assert "egress" not in services["db"]["networks"]
    assert "egress" not in services["redis"]["networks"]


def test_trusted_client_ip_requires_explicit_three_setting_opt_in() -> None:
    services = compose_config(
        environment={
            "LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER": "true",
            "LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER": "true",
            "LOGIN_RATE_LIMIT_TRUSTED_PROXY_CIDRS": "172.30.0.0/24",
        }
    )["services"]

    assert services["frontend"]["environment"]["LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER"] == "true"
    assert services["api"]["environment"]["LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER"] == "true"
    assert (
        services["api"]["environment"]["LOGIN_RATE_LIMIT_TRUSTED_PROXY_CIDRS"]
        == "172.30.0.0/24"
    )


def test_profiles_keep_worker_default_off_and_migration_explicit() -> None:
    model = compose_config(profiles=("worker", "release"))

    assert model["services"]["worker"]["profiles"] == ["worker"]
    assert model["services"]["worker"]["image"] == model["services"]["api"]["image"]
    assert model["services"]["migrate"]["image"] == model["services"]["api"]["image"]
    assert model["services"]["worker"].get("ports") is None
    assert model["services"]["worker"].get("volumes") is None
    assert model["services"]["migrate"]["profiles"] == ["release"]
    assert model["services"]["migrate"]["command"] == ["alembic", "upgrade", "head"]
    assert model["services"]["migrate"]["restart"] == "no"
    assert "egress" in model["services"]["worker"]["networks"]
    assert "egress" in model["services"]["migrate"]["networks"]


def test_healthchecks_and_dependencies_are_rendered() -> None:
    services = compose_config()["services"]

    assert "pg_isready" in services["db"]["healthcheck"]["test"][1]
    assert "redis-cli" in services["redis"]["healthcheck"]["test"][1]
    assert "/api/v1/health/ready" in services["api"]["healthcheck"]["test"][-1]
    assert "/login" in services["frontend"]["healthcheck"]["test"][-1]
    assert services["frontend"]["depends_on"]["api"]["condition"] == "service_healthy"
    assert services["edge"]["depends_on"]["frontend"]["condition"] == "service_healthy"


def test_development_compose_preserves_reload_mounts_profiles_and_ports() -> None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "--profile",
            "full",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    services = json.loads(result.stdout)["services"]

    assert "--reload" in services["api"]["command"]
    assert any(volume["target"] == "/app" for volume in services["api"]["volumes"])
    assert services["api"]["ports"][0]["published"] == "8000"
    assert services["frontend"]["ports"][0]["published"] == "3100"
    assert services["db"]["ports"][0]["published"] == "5433"
    assert services["redis"]["ports"][0]["published"] == "6379"


@pytest.mark.parametrize(
    "missing",
    [
        "EDGE_HOSTNAME",
        "POSTGRES_PASSWORD",
        "DATABASE_URL",
        "REDIS_PASSWORD",
        "REDIS_URL",
        "JWT_SECRET_KEY",
        "PAYOUT_CRYPTO_KEYRING_B64",
    ],
)
def test_production_render_fails_clearly_when_required_value_is_missing(
    tmp_path: Path, missing: str
) -> None:
    lines = [
        line for line in STAGING_ENV.read_text().splitlines() if not line.startswith(f"{missing}=")
    ]
    env_file = tmp_path / "missing.env"
    env_file.write_text("\n".join(lines))
    clean_environment = {"PATH": os.environ["PATH"], missing: ""}

    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(DEVELOPMENT_COMPOSE),
            "-f",
            str(PRODUCTION_COMPOSE),
            "--env-file",
            str(env_file),
            "config",
        ],
        cwd=ROOT,
        env=clean_environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert f"{missing} is required" in result.stderr


def _write_executable(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _smoke_environment(tmp_path: Path, *, failure: str = "") -> tuple[dict[str, str], Path]:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _write_executable(
        binaries / "curl",
        """#!/usr/bin/env bash
[[ "${SMOKE_FAILURE:-}" != frontend ]] || exit 22
exit 0
""",
    )
    _write_executable(
        binaries / "docker",
        """#!/usr/bin/env bash
case "$*" in
  *"alembic heads"*)
    echo "0012_head (head)"
    [[ "${SMOKE_FAILURE:-}" != multihead ]] || echo "other_head (head)"
    ;;
  *"alembic current"*)
    [[ "${SMOKE_FAILURE:-}" != revision ]] && echo "0012_head (head)" || echo "0011_old"
    ;;
  *"redis-cli"*)
    [[ "${SMOKE_FAILURE:-}" != redis ]] && echo "PONG" || exit 1
    ;;
  *"/api/v1/health/ready"*)
    [[ "${SMOKE_FAILURE:-}" != api ]] || exit 1
    ;;
  *"/api/v1/auth/login"*)
    request="$(cat)"
    [[ "${SMOKE_FAILURE:-}" != login ]] || {
      echo "ERROR: login failed with HTTP 401" >&2
      exit 1
    }
    ;;
esac
""",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{binaries}:{environment['PATH']}",
            "COMPOSE_ENV_FILE": str(STAGING_ENV),
            "SMOKE_BASE_URL": "https://staging.invalid",
            "SMOKE_FAILURE": failure,
            "TMPDIR": str(tmp_path / "tmp"),
        }
    )
    Path(environment["TMPDIR"]).mkdir()
    return environment, Path(environment["TMPDIR"])


def _run_smoke(
    tmp_path: Path, *, failure: str = "", password: str = "NeverPrintThis123!"
) -> subprocess.CompletedProcess:
    environment, _ = _smoke_environment(tmp_path, failure=failure)
    return subprocess.run(
        [
            str(ROOT / "scripts/release_smoke.sh"),
            "--email",
            "smoke@example.invalid",
            "--password-stdin",
        ],
        cwd=ROOT,
        env=environment,
        input=f"{password}\n",
        capture_output=True,
        text=True,
    )


def test_smoke_success_redacts_secrets_and_cleans_temporary_files(tmp_path: Path) -> None:
    password = "NeverPrintThis123!"
    result = _run_smoke(tmp_path, password=password)

    assert result.returncode == 0, result.stderr
    assert "Release smoke passed." in result.stdout
    assert password not in result.stdout + result.stderr
    assert not any((tmp_path / "tmp").iterdir())


def test_smoke_uses_the_base_and_production_compose_files() -> None:
    smoke = (ROOT / "scripts/release_smoke.sh").read_text()

    assert '-f "${COMPOSE_BASE_FILE}" -f "${COMPOSE_PRODUCTION_FILE}"' in smoke


def test_backup_directory_can_be_isolated_for_restore_rehearsals() -> None:
    backup = (ROOT / "scripts/db_backup.sh").read_text()
    runbook = (ROOT / "docs/runbook.md").read_text()

    assert 'BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups}"' in backup
    assert 'BACKUP_DIR="$(mktemp -d /tmp/mobility-restore-drill-backups.' in runbook
    assert 'export BACKUP_DIR' in runbook
    assert 'down -v --remove-orphans' in runbook
    assert 'awk \'NF {count++} END {print count+0}\'' in runbook
    assert '"$CODE_HEADS"' in runbook
    assert '"$DB_CURRENTS"' in runbook


@pytest.mark.parametrize("failure", ["frontend", "api", "revision", "redis", "login", "multihead"])
def test_smoke_failure_is_clear_redacted_and_cleans_up(tmp_path: Path, failure: str) -> None:
    password = "FailureSecret456!"
    result = _run_smoke(tmp_path, failure=failure, password=password)

    assert result.returncode != 0
    assert password not in result.stdout + result.stderr
    assert not any((tmp_path / "tmp").iterdir())


def test_smoke_copies_password_file_and_leaves_the_source_untouched(tmp_path: Path) -> None:
    environment, temp_directory = _smoke_environment(tmp_path)
    password_file = tmp_path / "operator-password"
    password_file.write_text("ProtectedSource789!")
    password_file.chmod(0o400)

    result = subprocess.run(
        [
            str(ROOT / "scripts/release_smoke.sh"),
            "--email",
            "smoke@example.invalid",
            "--password-file",
            str(password_file),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(password_file.stat().st_mode) == 0o400
    assert "ProtectedSource789!" not in result.stdout + result.stderr
    assert not any(temp_directory.iterdir())


def test_smoke_rejects_missing_credentials_without_starting_checks(tmp_path: Path) -> None:
    environment, temp_directory = _smoke_environment(tmp_path)
    result = subprocess.run(
        [str(ROOT / "scripts/release_smoke.sh"), "--email", "smoke@example.invalid"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "password input method is required" in result.stderr
    assert not any(temp_directory.iterdir())


def test_caddy_replaces_forwarding_headers_from_the_socket_peer() -> None:
    caddyfile = (ROOT / "Caddyfile").read_text()

    assert "header_up -X-Forwarded-For" in caddyfile
    assert "header_up X-Client-IP {http.request.remote.host}" in caddyfile
    assert "reverse_proxy frontend:3000" in caddyfile


def test_caddy_adapt_does_not_generate_literal_off_issuer_email() -> None:
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-e",
            "EDGE_HOSTNAME=staging.example.invalid",
            "-v",
            f"{ROOT / 'Caddyfile'}:/etc/caddy/Caddyfile:ro",
            "caddy:2.8-alpine",
            "caddy",
            "adapt",
            "--config",
            "/etc/caddy/Caddyfile",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    adapted = json.loads(result.stdout)
    server = adapted["apps"]["http"]["servers"]["srv0"]
    assert server["listen"] == [":443"]
    assert server["routes"][0]["match"][0]["host"] == ["staging.example.invalid"]

    def email_values(value: object) -> list[object]:
        if isinstance(value, dict):
            return [
                *([value["email"]] if "email" in value else []),
                *(email for nested in value.values() for email in email_values(nested)),
            ]
        if isinstance(value, list):
            return [email for nested in value for email in email_values(nested)]
        return []

    assert "off" not in email_values(adapted)


def test_restore_quiesces_and_conditionally_restarts_worker() -> None:
    restore = (ROOT / "scripts/db_restore.sh").read_text()

    assert 'readonly WORKER_SERVICE="worker"' in restore
    assert 'if compose_ps_running "${WORKER_SERVICE}"' in restore
    assert "if (( WORKER_WAS_RUNNING == 1 ))" in restore
    assert '--profile worker up -d "${WORKER_SERVICE}"' in restore
    assert 'up -d "${WORKER_SERVICE}" >/dev/null || return' in restore
    assert '"${API_SERVICE}" "${FRONTEND_SERVICE}" "${WORKER_SERVICE}"' in restore

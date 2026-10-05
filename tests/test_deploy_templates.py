"""W1B replacement templates are private, secret-free and inert (REQ-049/108)."""

import json
from pathlib import Path

import pytest
from test_w403a_release_preparation import production_model

from scripts.release_contract import ContractError, read_env_file, validate_compose_model

ROOT = Path(__file__).resolve().parents[1]
SECRET_NAMES = {
    "DATABASE_URL",
    "REDIS_URL",
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "JWT_SECRET_KEY",
    "PAYOUT_CRYPTO_KEYRING_B64",
    "TRIP_EVIDENCE_SIGNING_KEYRING_B64",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    "EMAIL_SMTP_USERNAME",
    "EMAIL_SMTP_PASSWORD",
    "EMAIL_RECEIPT_SIGNING_SECRET",
    "PAYSTACK_SECRET_KEY",
    "SENTRY_DSN",
    "NEXT_PUBLIC_SENTRY_DSN",
    "RELEASE_EVIDENCE_SIGNING_SECRET",
    "NEXT_PUBLIC_MAP_STYLE_URL",
}


@pytest.mark.parametrize("name", ["production.env.example", "staging.env.example"])
def test_secrets_are_blank_and_unapproved_policies_stay_unset(name: str) -> None:
    environment = read_env_file(ROOT / name)
    assert {key: environment[key] for key in SECRET_NAMES} == dict.fromkeys(SECRET_NAMES, "")
    for key in (
        "BUDGET_ALERT_RATIO",
        "BUDGET_URGENT_RATIO",
        "BUDGET_PAUSE_RATIO",
        "BUDGET_RESUME_RATIO",
        "FILE_KYC_RETENTION_DAYS",
        "INVOICE_ISSUER_EXTERNAL_INPUT_REFERENCE",
    ):
        assert environment[key] == ""
    for key in (
        "ALLOW_DEMO_SEED",
        "DEMO_LOGIN_ENABLED",
        "BUDGET_POLICY_EXTERNAL_APPROVED",
        "PAYOUT_V4_PUBLISHING_ENABLED",
        "PAYOUT_AUTOMATIC_APPROVAL_ENABLED",
    ):
        assert environment[key] == "false"
    assert environment["MALWARE_SCANNER_HOST"] == "clamav"
    assert environment["WEB_CONCURRENCY"] == "2"
    model = production_model(env_file=ROOT / name, profiles=("release",))
    validate_compose_model(model)


def test_hetzner_cors_replaces_obsolete_provider_artifacts() -> None:
    assert not list((ROOT / "deploy/render").glob("*"))
    assert not list((ROOT / "deploy/aws").glob("*"))
    cors = json.loads((ROOT / "deploy/hetzner/s3-cors.json").read_text())
    (rule,) = cors["CORSRules"]
    assert rule["AllowedMethods"] == ["GET", "POST"]
    assert rule["AllowedOrigins"] == ["https://REPLACE-WITH-APPROVED-APP-ORIGIN.invalid"]
    assert rule["ExposeHeaders"] == ["ETag"]
    assert "*" not in rule["AllowedOrigins"]


def test_maptiler_csp_is_limited_to_api_fetches_and_images() -> None:
    policy = (ROOT / "Caddyfile").read_text().split('Content-Security-Policy "')[1].split('"')[0]
    directives = dict(
        item.strip().split(" ", 1) for item in policy.split(";") if " " in item.strip()
    )
    assert "https://api.maptiler.com" in directives["connect-src"].split()
    assert "https://api.maptiler.com" in directives["img-src"].split()
    for key in ("script-src", "style-src", "font-src", "frame-src"):
        assert "maptiler" not in directives[key]
    assert "https:" not in directives["connect-src"].split()
    assert "*" not in policy


def test_scanner_topology_and_configurable_workers() -> None:
    model = production_model(profiles=("release",))
    validate_compose_model(model)
    scanner = model["services"]["clamav"]
    assert set(scanner["networks"]) == {"data", "egress"}
    assert not scanner.get("ports")
    assert scanner["healthcheck"]["start_period"] == "6m0s"
    assert scanner["restart"] == "unless-stopped"
    assert int(scanner["mem_limit"]) == 4 * 1024**3
    assert model["services"]["api"]["environment"]["WEB_CONCURRENCY"] == "2"
    assert "--workers" not in model["services"]["api"]["command"]
    assert "ENV WEB_CONCURRENCY=2" in (ROOT / "Dockerfile").read_text()
    changed = production_model(overrides={"WEB_CONCURRENCY": "3"})
    assert changed["services"]["api"]["environment"]["WEB_CONCURRENCY"] == "3"


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "public",
        "network",
        "image",
        "health",
        "disabled",
        "memory",
        "confinement",
        "volume_missing",
        "volume_type",
        "volume_source",
        "volume_target",
        "volume_readonly",
        "api_host",
        "worker_host",
        "api_port",
        "worker_port",
        "api_dependency",
        "worker_dependency",
    ],
)
def test_release_rejects_unsafe_scanner(fault: str) -> None:
    model = production_model(profiles=("release",))
    scanner = model["services"]["clamav"]
    if fault == "missing":
        del model["services"]["clamav"]
    elif fault == "public":
        scanner["ports"] = [{"published": "3310", "target": 3310}]
    elif fault == "network":
        scanner["networks"] = {"edge": {}}
    elif fault == "image":
        scanner["image"] = "clamav/clamav:latest"
    elif fault == "health":
        scanner["healthcheck"]["test"] = ["CMD", "true"]
    elif fault == "disabled":
        scanner["healthcheck"]["disable"] = True
    elif fault == "memory":
        scanner["mem_limit"] = 1024**3
    elif fault == "confinement":
        scanner["security_opt"] = []
    elif fault == "volume_missing":
        scanner["volumes"] = []
    elif fault.startswith("volume_"):
        key = fault.removeprefix("volume_").replace("readonly", "read_only")
        scanner["volumes"][0][key] = True if key == "read_only" else "incorrect"
    else:
        name, field = fault.split("_")
        service = model["services"][name]
        if field == "host":
            service["environment"]["MALWARE_SCANNER_HOST"] = "external.invalid"
        elif field == "port":
            service["environment"]["MALWARE_SCANNER_PORT"] = "9999"
        else:
            service["depends_on"]["clamav"]["condition"] = "service_started"
    with pytest.raises(ContractError):
        validate_compose_model(model)

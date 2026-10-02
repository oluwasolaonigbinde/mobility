"""The Render and AWS templates (REQ-010) stay valid, secret-free and switched off."""

import json
from pathlib import Path

import yaml

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = yaml.safe_load((ROOT / "deploy/render/render.yaml").read_text(encoding="utf-8"))

SECRETS = {
    "DATABASE_URL",
    "REDIS_URL",
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
    "NEXT_PUBLIC_MAP_STYLE_URL",
}
# Words that mark a value which must never be committed, whatever the key is called.
SECRET_WORDS = ("SECRET", "PASSWORD", "KEYRING", "TOKEN", "DSN", "ACCESS_KEY", "_URL")
SWITCHED_OFF = {
    "PAYOUT_V4_PUBLISHING_ENABLED": "false",
    "PAYOUT_AUTOMATIC_APPROVAL_ENABLED": "false",
    "PAYOUT_AUTOMATIC_FREQUENCY": "",
    "PAYOUT_AUTOMATIC_BATCH_LIMIT_NGN": "",
    "INVOICE_ISSUER_EXTERNAL_INPUT_REFERENCE": "",
    "BUDGET_POLICY_EXTERNAL_APPROVED": "false",
    "PHONE_OPERATOR_EXTERNAL_APPROVED": "false",
    "DRIVER_REGISTRATION_ENABLED": "false",
    "ALLOW_DEMO_SEED": "false",
    "DEMO_LOGIN_ENABLED": "false",
    "LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER": "false",
    "LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER": "false",
    "DRIVER_REGISTRATION_RATE_LIMIT_TRUST_CLIENT_IP_HEADER": "false",
}
NOT_SECRET = {"PASSWORD_MIN_LENGTH", *SWITCHED_OFF}
FRONTEND_KEYS = {
    "NODE_ENV",
    "API_BASE_URL",
    "PUBLIC_ORIGIN",
    "SESSION_COOKIE_NAME",
    "LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER",
    "DEMO_LOGIN_ENABLED",
    "NEXT_PUBLIC_MAP_STYLE_URL",
    "NEXT_PUBLIC_SENTRY_DSN",
}
# What app/adapters/storage/s3.py calls: get/put/copy/delete objects and versions,
# list versions, and presigned POST/GET under SSE-KMS default encryption.
S3_ACTIONS = {
    "s3:ListBucket",
    "s3:ListBucketVersions",
    "s3:GetObject",
    "s3:PutObject",
    "s3:DeleteObject",
    "s3:DeleteObjectVersion",
}
KMS_ACTIONS = {"kms:Decrypt", "kms:GenerateDataKey"}


def _group_vars() -> list[dict]:
    (group,) = BLUEPRINT["envVarGroups"]
    return group["envVars"]


def _service(name: str) -> dict:
    (service,) = [s for s in BLUEPRINT["services"] if s["name"] == name]
    return service


def _service_vars(name: str) -> list[dict]:
    return [item for item in _service(name).get("envVars", []) if "key" in item]


def _all_vars() -> list[dict]:
    variables = list(_group_vars())
    for service in BLUEPRINT["services"]:
        variables += [item for item in service.get("envVars", []) if "key" in item]
    return variables


def test_backend_keys_are_settings_fields_and_frontend_keys_are_known() -> None:
    fields = {name.upper() for name in Settings.model_fields}
    backend = _group_vars() + _service_vars("cardvert-api") + _service_vars("cardvert-worker")
    assert [item["key"] for item in backend if item["key"] not in fields] == []
    assert {item["key"] for item in _service_vars("cardvert-frontend")} <= FRONTEND_KEYS
    # Environment groups take plain values or sync: false only.
    assert all(set(item) <= {"key", "value", "sync"} for item in _group_vars())


def test_committed_backend_values_pass_settings_validation(monkeypatch) -> None:
    # Render passes the values as environment variables, so validate them the same way.
    for item in _group_vars():
        if "value" in item:
            monkeypatch.setenv(item["key"], item["value"])
    # Stand-ins only for what the template leaves to be entered by hand.
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv(
        "PAYOUT_CRYPTO_KEYRING_B64", '{"1":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="}'
    )
    settings = Settings(_env_file=None)
    assert settings.payout_automatic_approval_enabled is False
    assert not settings.invoice_issuer_external_input_reference
    assert settings.installation_evidence_validity_hours == 168


def test_no_secret_is_committed_and_client_switches_stay_off() -> None:
    variables = {item["key"]: item for item in _all_vars()}
    for key in SECRETS:
        assert variables[key].get("sync") is False, key
        assert "value" not in variables[key], key
    for key, item in variables.items():
        if any(word in key for word in SECRET_WORDS) and key not in NOT_SECRET:
            assert "value" not in item, f"{key} looks secret-shaped and carries a value"
    # Render's generated URLs fail the asyncpg+TLS and rediss checks, so both are hand-entered.
    for key in ("DATABASE_URL", "REDIS_URL"):
        assert set(variables[key]) == {"key", "sync"}
    for key, expected in SWITCHED_OFF.items():
        assert variables[key].get("value") == expected, key
    assert variables["ENVIRONMENT"]["value"] == "staging"


def test_aws_templates_parse_and_grant_only_what_the_storage_adapter_uses() -> None:
    policy = json.loads((ROOT / "deploy/aws/s3-kms-iam-policy.json").read_text(encoding="utf-8"))
    actions = [action for statement in policy["Statement"] for action in statement["Action"]]
    assert sorted(actions) == sorted(S3_ACTIONS | KMS_ACTIONS)
    assert all(statement["Effect"] == "Allow" for statement in policy["Statement"])
    # Scoped to one bucket and one key, never every resource.
    assert all(statement["Resource"] != "*" for statement in policy["Statement"])
    (kms,) = [s for s in policy["Statement"] if s["Action"][0].startswith("kms:")]
    # The key is usable only through S3, not directly with the access key.
    assert set(kms["Condition"]["StringEquals"]) == {"kms:ViaService"}
    cors = json.loads((ROOT / "deploy/aws/s3-cors.json").read_text(encoding="utf-8"))
    (rule,) = cors["CORSRules"]
    assert set(rule["AllowedMethods"]) == {"GET", "POST"}
    assert "*" not in rule["AllowedOrigins"]

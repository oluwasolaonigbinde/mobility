import asyncio
import base64
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from test_w403a_release_preparation import (
    RELEASE_EVIDENCE_KEY_ID,
    RELEASE_EVIDENCE_SECRET,
    compatibility_receipt,
)

from app.operations import readiness
from app.operations.recovery_authority import CAPABILITY, validate_authority
from scripts import recovery_authority as host
from scripts.release_contract import (
    ContractError,
    compatibility_acceptance_hmac,
    compatibility_receipt_sha256,
)


def test_unsigned_database_ahead_switch_is_not_an_operator_authority(monkeypatch):
    async def unsafe_probe(**kwargs):
        return {"status": "ready"}

    monkeypatch.setattr(readiness, "run_probe", unsafe_probe)
    with pytest.raises(SystemExit) as rejected:
        readiness.main(["--write-canary", "--allow-database-ahead"])
    assert rejected.value.code == 2


NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def environments():
    receipt = compatibility_receipt()
    current = {
        "RELEASE_ID": receipt["target_release_id"],
        "RELEASE_REVISION": receipt["target_revision"],
        "BACKEND_IMAGE": receipt["target_backend_image"],
        "PREVIOUS_RELEASE_ID": receipt["previous_release_id"],
        "RELEASE_EVIDENCE_SIGNING_SECRET": RELEASE_EVIDENCE_SECRET,
        "RELEASE_EVIDENCE_KEY_ID": RELEASE_EVIDENCE_KEY_ID,
        "PAYOUT_CRYPTO_KEYRING_B64": json.dumps({"1": base64.b64encode(b"p" * 32).decode()}),
        "PAYOUT_CRYPTO_KEY_VERSION": "1",
        "TRIP_EVIDENCE_SIGNING_KEYRING_B64": json.dumps(
            {"1": base64.b64encode(b"s" * 32).decode()}
        ),
        "TRIP_EVIDENCE_SIGNING_KEY_VERSION": "1",
    }
    previous = {
        "RELEASE_ID": receipt["previous_release_id"],
        "RELEASE_REVISION": receipt["previous_revision"],
        "BACKEND_IMAGE": receipt["previous_backend_image"],
    }
    digest = compatibility_receipt_sha256(receipt)
    acceptance = compatibility_acceptance_hmac(
        receipt_sha256=digest,
        target_release_id=current["RELEASE_ID"],
        target_revision=current["RELEASE_REVISION"],
        target_backend_image=current["BACKEND_IMAGE"],
        key_id=RELEASE_EVIDENCE_KEY_ID,
        signing_secret=RELEASE_EVIDENCE_SECRET,
    )
    state = {
        "release_id": current["RELEASE_ID"],
        "revision": current["RELEASE_REVISION"],
        "backend_image": current["BACKEND_IMAGE"],
        "previous_release_id": previous["RELEASE_ID"],
        "stages": ["migration", "compatibility"],
        "events": [{"stage": "compatibility", "outcome": f"passed:{digest}:{acceptance}"}],
    }
    return current, previous, receipt, state


def overlay(scope="qualification", **changes):
    current, previous, receipt, state = environments()
    params = dict(
        current=current,
        previous=previous,
        capability={"capability": CAPABILITY, "alembic_revision": "0081_example"},
        forward=receipt["forward_alembic_revision"],
        scope=scope,
        now=NOW,
    )
    if scope == "recovery":
        params.update(evidence=receipt, state=state)
    params.update(changes)
    return host.build_overlay(**params)


def unpack(override):
    return {
        key: value.replace("$$", "$")
        for key, value in override["services"]["api"]["environment"].items()
    }


def validate(token, scope="qualification", **changes):
    _, previous, _, _ = environments()
    params = dict(
        secret=RELEASE_EVIDENCE_SECRET,
        scope=scope,
        release_id=previous["RELEASE_ID"],
        revision=previous["RELEASE_REVISION"],
        image=previous["BACKEND_IMAGE"],
        code_head="0081_example",
        now=NOW,
    )
    params.update(changes)
    return validate_authority(token, **params)


@pytest.mark.parametrize("scope", ["qualification", "recovery"])
def test_host_issues_only_scoped_operator_overlay(scope):
    result = overlay(scope)
    assert set(result["services"]) == {"api"}
    token = json.loads(unpack(result)["RELEASE_COMPATIBILITY_AUTHORITY"])
    assert validate(token, scope) == token
    health = result["services"]["api"].get("healthcheck")
    if scope == "qualification":
        assert health is None
        assert token["accepted_receipt_sha256"] is None
    else:
        assert health["test"][-2:] == ["--compatibility", "recovery"]
        assert token["accepted_receipt_sha256"] == compatibility_receipt_sha256(environments()[2])
        assert validate(token, scope, now=NOW + timedelta(days=100)) == token


@pytest.mark.parametrize(
    "field",
    [
        "scope",
        "previous_revision",
        "previous_backend_image",
        "previous_alembic_revision",
        "forward_alembic_revision",
        "accepted_receipt_sha256",
        "signature",
        "key_id",
        "target_revision",
        "target_backend_image",
        "issued_at",
        "expires_at",
    ],
)
def test_every_tampered_authority_field_is_rejected(field):
    token = json.loads(unpack(overlay())["RELEASE_COMPATIBILITY_AUTHORITY"])
    token[field] = "tampered"
    with pytest.raises(ValueError):
        validate(token)


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "recovery"},
        {"revision": "f" * 40},
        {"image": "sha256:" + "f" * 64},
        {"code_head": "0080_wrong"},
        {"release_id": "different"},
        {"secret": "f" * 40},
        {"now": NOW + timedelta(minutes=30)},
        {"now": NOW - timedelta(seconds=1)},
    ],
)
def test_signed_authority_cannot_be_replayed_in_another_context(changes):
    token = json.loads(unpack(overlay())["RELEASE_COMPATIBILITY_AUTHORITY"])
    with pytest.raises(ValueError):
        validate(token, **changes)


@pytest.mark.parametrize("mutation", ["state", "acceptance", "receipt", "unaccepted", "capability"])
def test_host_recovery_cannot_issue_from_unaccepted_or_incapable_predecessor(mutation):
    current, previous, receipt, state = environments()
    capability = {"capability": CAPABILITY, "alembic_revision": "0081_example"}
    if mutation == "state":
        state["backend_image"] = previous["BACKEND_IMAGE"]
    elif mutation == "acceptance":
        state["events"][0]["outcome"] = "passed:" + "a" * 64 + ":" + "b" * 64
    elif mutation == "receipt":
        receipt["forward_alembic_revision"] = "0080_stale"
    elif mutation == "unaccepted":
        state["stages"] = []
    else:
        capability["capability"] = "historical-image-without-capability"
    with pytest.raises((ContractError, ValueError)):
        overlay(
            "recovery",
            current=current,
            previous=previous,
            evidence=receipt,
            state=state,
            capability=capability,
        )


@pytest.mark.parametrize(
    "component", ["api", "broker", "scanner", "trip_evidence_signing", "storage", "worker"]
)
def test_receipt_signer_rejects_missing_qualification_component(component):
    from scripts.release_contract import build_compatibility_receipt

    _, _, receipt, _ = environments()
    output = deepcopy(receipt["probes"]["readiness"]["output"])
    del output["checks"][component]
    identities = {
        name: receipt[name]
        for name in (
            "target_release_id",
            "target_revision",
            "target_backend_image",
            "previous_release_id",
            "previous_revision",
            "previous_backend_image",
            "forward_alembic_revision",
        )
    }
    with pytest.raises(ContractError):
        build_compatibility_receipt(
            **identities,
            readiness_output=output,
            report_schema_output=receipt["probes"]["report_schema"]["output"],
            generated_at=NOW,
            key_id=RELEASE_EVIDENCE_KEY_ID,
            signing_secret=RELEASE_EVIDENCE_SECRET,
        )


@pytest.mark.parametrize("scope", [None, "qualification", "recovery"])
def test_probe_scopes_preserve_worker_and_exact_database_authority(monkeypatch, scope):
    calls = []
    observed_revision = environments()[2]["forward_alembic_revision"]
    for key, value in unpack(overlay(scope or "qualification")).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        readiness,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="local-db",
            redis_url="local-redis",
            release_revision="3" * 40,
        ),
    )
    monkeypatch.setattr(readiness, "code_migration_head", lambda: "0081_example")
    real_validate = readiness.validate_authority
    monkeypatch.setattr(
        readiness,
        "validate_authority",
        lambda *a, **kw: real_validate(
            *a,
            **kw,
            now=NOW,
        ),
    )

    async def database(_url, *, expected_revision=None):
        calls.append(("database", expected_revision))
        if observed_revision != (expected_revision or "0081_example"):
            raise RuntimeError("wrong database")
        return {"alembic_revision": observed_revision, "postgis_version": "3.4"}

    def checker(name):
        async def check(*args, **kwargs):
            calls.append(name)
            if name == "worker":
                raise RuntimeError("worker missing")
            return {"status": "ok"}

        return check

    monkeypatch.setattr(readiness, "_database_check", database)
    for name in ("broker", "storage", "worker", "scanner", "signing"):
        monkeypatch.setattr(readiness, f"_{name}_check", checker(name))

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(readiness, "urlopen", lambda *a, **kw: Response())
    if scope == "qualification":
        result = asyncio.run(readiness.run_probe(write_canary=True, compatibility_scope=scope))
        assert result["checks"]["worker"]["status"] == "quiesced_for_qualification"
        assert "worker" not in calls
        assert "signing" in calls
    else:
        with pytest.raises(
            RuntimeError, match="wrong database" if scope is None else "worker missing"
        ):
            asyncio.run(readiness.run_probe(write_canary=True, compatibility_scope=scope))
        if scope == "recovery":
            assert "worker" in calls
    assert calls[0] == ("database", observed_revision if scope else None)


@pytest.mark.parametrize("head", ["0084_current", "0088_report_publication_writes", "future_0099"])
def test_image_head_is_derived_from_exact_identified_image(monkeypatch, head):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return "3" * 40 if command[1] == "image" else head + " (head)\n"

    monkeypatch.setattr(host.subprocess, "check_output", run)
    image = "sha256:" + "4" * 64
    assert host.image_head(image, "3" * 40) == head
    assert calls[0][1:4] == ["image", "inspect", image]
    assert calls[1][1:7] == ["run", "--rm", "--pull=never", "--network", "none", "--entrypoint"]
    assert calls[1][-3:] == ["alembic", image, "heads"]


@pytest.mark.parametrize(
    "output", ["", "0082_old (head)\n0088_new (head)", "0082_old", "not a head"]
)
def test_missing_multiple_or_malformed_image_heads_fail_closed(monkeypatch, output):
    monkeypatch.setattr(host, "image_command", lambda *args: output)
    with pytest.raises(ContractError):
        host.image_head("sha256:" + "4" * 64, "3" * 40)


def test_image_label_mismatch_blocks_execution(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return "f" * 40

    monkeypatch.setattr(host.subprocess, "check_output", run)
    with pytest.raises(ContractError):
        host.image_head("sha256:" + "4" * 64, "3" * 40)
    assert len(calls) == 1


def test_actual_forward_database_is_exact_and_public_readiness_stays_closed(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import create_async_engine
    from test_migration_0014_partitioning import (
        configured_postgres_url,
        create_database_from_url,
        drop_database,
    )

    from app.core.config import Settings

    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    head = readiness.code_migration_head()

    async def exercise():
        engine = create_async_engine(url)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
                await connection.execute(text("CREATE TABLE alembic_version (version_num text)"))
                await connection.execute(
                    text("INSERT INTO alembic_version VALUES (:head)"), {"head": head}
                )
            monkeypatch.setattr(
                readiness, "code_migration_head", lambda: "0084_payout_conservation"
            )
            with pytest.raises(RuntimeError, match="database migration"):
                await readiness._database_check(url)
            assert (await readiness._database_check(url, expected_revision=head))[
                "alembic_revision"
            ] == head
            with pytest.raises(RuntimeError, match="database migration"):
                await readiness._database_check(
                    url, expected_revision="0082_report_publication_intents"
                )
            for key, value in unpack(overlay("recovery")).items():
                monkeypatch.setenv(key, value)
            settings = Settings(database_url=url)
            result = await readiness._run_component_checks(settings)
            assert not result.ready
            assert result.components["database"] == "unavailable"
            async with engine.begin() as connection:
                await connection.execute(text("INSERT INTO alembic_version VALUES ('divergent')"))
            with pytest.raises(DBAPIError):
                await readiness._database_check(url, expected_revision=head)
        finally:
            await engine.dispose()

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(drop_database(url))


def test_rehearsal_uses_both_image_heads_without_obsolete_revision_constant():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "scripts/rehearse_w403a.sh").read_text()
    assert 'FORWARD_ALEMBIC_REVISION="0082_report_publication_intents"' not in source
    for name, image, revision in (
        ("PREVIOUS", "previous_backend_image", "PREVIOUS_REVISION"),
        ("FORWARD", "backend_image", "REVISION"),
    ):
        declaration = source.split(f'{name}_ALEMBIC_REVISION="$(')[1].split(')"')[0]
        assert "scripts/recovery_authority.py --image-head" in declaration
        assert f'--image "${{{image}}}" --revision "${{{revision}}}"' in declaration
    assert '"${db_revision_after_recovery}" == "${FORWARD_ALEMBIC_REVISION}"' in source


def test_recovery_overlay_is_private_and_compose_interpolation_preserves_signature(tmp_path):
    import subprocess

    from scripts.release_contract import _write_private_json

    current, previous, _, _ = environments()
    secret = "Signed$Operator${Missing}-authority-" + "9" * 48
    current["RELEASE_EVIDENCE_SIGNING_SECRET"] = secret
    result = overlay(current=current)
    path = tmp_path / "authority.json"
    _write_private_json(path, result)
    assert path.stat().st_mode & 0o777 == 0o600
    base = tmp_path / "base.json"
    base.write_text(
        json.dumps(
            {"services": {"api": {"image": "postgis/postgis:16-3.4", "network_mode": "none"}}}
        )
    )
    merged = json.loads(
        subprocess.check_output(
            [
                "docker",
                "compose",
                "-p",
                "correction-authority-test",
                "-f",
                str(base),
                "-f",
                str(path),
                "config",
                "--format",
                "json",
            ],
            text=True,
        )
    )
    env = merged["services"]["api"]["environment"]
    # Compose's rendered model escapes dollars again for safe round-tripping.
    assert env["RELEASE_COMPATIBILITY_KEY"] == secret.replace("$", "$$")
    actual = subprocess.check_output(
        [
            "docker",
            "compose",
            "-p",
            "correction-authority-test",
            "-f",
            str(base),
            "-f",
            str(path),
            "run",
            "--rm",
            "-T",
            "--no-deps",
            "--pull",
            "never",
            "api",
            "printenv",
            "RELEASE_COMPATIBILITY_KEY",
            "RELEASE_COMPATIBILITY_AUTHORITY",
        ],
        text=True,
    ).splitlines()
    assert actual[0] == secret
    token = json.loads(actual[1])
    assert validate(token, secret=secret)["previous_revision"] == previous["RELEASE_REVISION"]


def test_wrong_authority_is_rejected_before_any_dependency_probe(monkeypatch):
    monkeypatch.setattr(
        readiness,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="local-db",
            redis_url="local-redis",
            release_revision="3" * 40,
        ),
    )
    monkeypatch.setattr(readiness, "code_migration_head", lambda: "0081_example")
    for key, value in unpack(overlay("recovery")).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("RELEASE_COMPATIBILITY_KEY", "wrong" * 20)
    calls = []

    async def forbidden(*a, **kw):
        calls.append("dependency")

    monkeypatch.setattr(readiness, "_database_check", forbidden)
    with pytest.raises(ValueError):
        asyncio.run(readiness.run_probe(write_canary=True, compatibility_scope="recovery"))
    assert calls == []


def test_historical_predecessor_rehearsal_fails_before_build_or_infrastructure(tmp_path):
    import os
    import subprocess

    from scripts.release_contract import ROOT

    trace = tmp_path / "unexpected-execution"
    fake = tmp_path / "bin"
    fake.mkdir()
    for name in ("docker", "gpg", "jq", "openssl", "sha256sum", "tar"):
        executable = fake / name
        executable.write_text(f'#!/bin/sh\necho invoked >> "{trace}"\nexit 99\n')
        executable.chmod(0o700)
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/rehearse_w403a.sh")],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": str(fake) + os.pathsep + os.environ["PATH"],
            "REHEARSAL_PREVIOUS_REVISION": "26f5e2217302b60df472788c277d34977915f184",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "predecessor lacks signed recovery capability" in result.stderr
    assert not trace.exists()


def test_obsolete_signed_receipt_cannot_authorize_new_operator_path():
    from scripts.release_contract import _compatibility_signature, validate_compatibility_evidence

    _, _, receipt, _ = environments()
    receipt["schema_version"] = 2
    receipt["hmac_sha256"] = _compatibility_signature(receipt, RELEASE_EVIDENCE_SECRET)
    identities = {
        name: receipt[name]
        for name in (
            "target_release_id",
            "target_revision",
            "target_backend_image",
            "previous_release_id",
            "previous_revision",
            "previous_backend_image",
            "forward_alembic_revision",
        )
    }
    with pytest.raises(ContractError, match="schema_version"):
        validate_compatibility_evidence(
            receipt,
            **identities,
            signing_secret=RELEASE_EVIDENCE_SECRET,
            key_id=RELEASE_EVIDENCE_KEY_ID,
            now=NOW,
        )


@pytest.mark.parametrize("scope", [None, "qualification", "recovery"])
def test_operator_cli_success_checks_all_dependencies_in_its_scope(monkeypatch, capsys, scope):
    settings = SimpleNamespace(
        database_url="local-db", redis_url="local-redis", release_revision="3" * 40
    )
    monkeypatch.setattr(readiness, "get_settings", lambda: settings)
    monkeypatch.setattr(readiness, "code_migration_head", lambda: "0081_example")
    for key, value in unpack(overlay(scope or "qualification")).items():
        monkeypatch.setenv(key, value)
    real_validate = readiness.validate_authority
    monkeypatch.setattr(
        readiness,
        "validate_authority",
        lambda *args, **kwargs: real_validate(
            *args,
            **kwargs,
            now=NOW,
        ),
    )
    calls = []

    async def database(url, *, expected_revision=None):
        assert url == "local-db"
        assert expected_revision == ("0082_report_publication_intents" if scope else None)
        calls.append("database")
        return {"alembic_revision": expected_revision or "0081_example", "postgis_version": "3.4"}

    monkeypatch.setattr(readiness, "_database_check", database)

    def checker(name):
        async def check(*args, **kwargs):
            calls.append(name)
            if name == "storage":
                assert kwargs["write_canary"] is True
            return {"status": "ok"}

        return check

    for name in ("broker", "storage", "worker", "scanner", "signing"):
        monkeypatch.setattr(readiness, f"_{name}_check", checker(name))

    class Response:
        status = 200

        def __enter__(self):
            calls.append("api")
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(readiness, "urlopen", lambda *args, **kwargs: Response())
    args = ["--write-canary"] + (["--compatibility", scope] if scope else [])
    assert readiness.main(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "ready"
    expected = {"database", "broker", "storage", "scanner", "signing"}
    if scope != "qualification":
        expected.add("worker")
    if scope:
        expected.add("api")
        assert output["compatibility_scope"] == scope
        assert len(output["authority_sha256"]) == 64
    else:
        assert "compatibility_scope" not in output
    assert set(calls) == expected


def test_operator_cli_failure_redacts_details_and_capability_needs_no_runtime_services(
    monkeypatch, capsys
):
    async def fail(**kwargs):
        raise RuntimeError("private credential and topology detail")

    monkeypatch.setattr(readiness, "run_probe", fail)
    assert readiness.main(["--write-canary"]) == 1
    result = capsys.readouterr()
    assert not result.out
    assert json.loads(result.err) == {
        "event": "release_readiness",
        "status": "failed",
        "reason": "RuntimeError",
    }
    monkeypatch.setattr(readiness, "code_migration_head", lambda: "0088_report_publication_writes")
    assert readiness.main(["--capability"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "capability": CAPABILITY,
        "alembic_revision": "0088_report_publication_writes",
    }


@pytest.mark.parametrize(
    "mutation", ["extra", "short-key", "same-image", "same-revision", "expiry"]
)
def test_signed_but_invalid_scope_shape_is_not_authority(mutation):
    from app.operations.recovery_authority import authority_signature

    token = json.loads(unpack(overlay())["RELEASE_COMPATIBILITY_AUTHORITY"])
    secret = RELEASE_EVIDENCE_SECRET
    if mutation == "extra":
        token["allow_any_schema"] = True
    elif mutation == "short-key":
        secret = "short"
    elif mutation == "same-image":
        token["target_backend_image"] = token["previous_backend_image"]
    elif mutation == "same-revision":
        token["target_revision"] = token["previous_revision"]
    else:
        token["expires_at"] = (NOW + timedelta(days=1)).isoformat()
    token["signature"] = authority_signature(token, secret)
    with pytest.raises(ValueError):
        validate(token, secret=secret)

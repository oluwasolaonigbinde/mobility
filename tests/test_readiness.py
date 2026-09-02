import asyncio
import base64
import json
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from app.core.config import Settings
from app.operations import readiness


def test_readiness_single_flight_and_success_cache(monkeypatch) -> None:
    calls = 0

    async def probe(_settings):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return readiness.PublicReadiness(ready=True, components={"database": "ok"})

    monkeypatch.setattr(readiness, "_run_component_checks", probe)
    coordinator = readiness.ReadinessCoordinator()
    settings = Settings()

    async def exercise() -> None:
        results = await asyncio.gather(*(coordinator.get(settings) for _ in range(20)))
        assert all(result.ready for result in results)
        assert (await coordinator.get(settings)).ready

    asyncio.run(exercise())
    assert calls == 1


def test_readiness_failure_cache_expires_after_five_seconds(monkeypatch) -> None:
    calls = 0
    now = 100.0

    async def probe(_settings):
        nonlocal calls
        calls += 1
        return readiness.PublicReadiness(ready=False, components={"redis": "unavailable"})

    monkeypatch.setattr(readiness, "_run_component_checks", probe)
    monkeypatch.setattr(readiness.time, "monotonic", lambda: now)
    coordinator = readiness.ReadinessCoordinator()
    settings = Settings()

    async def exercise() -> None:
        nonlocal now
        assert not (await coordinator.get(settings)).ready
        now += 4.9
        assert not (await coordinator.get(settings)).ready
        now += 0.2
        assert not (await coordinator.get(settings)).ready

    asyncio.run(exercise())
    assert calls == 2


def test_readiness_success_cache_expires_after_thirty_seconds(monkeypatch) -> None:
    calls = 0
    now = 100.0

    async def probe(_settings):
        nonlocal calls
        calls += 1
        return readiness.PublicReadiness(ready=True, components={"database": "ok"})

    monkeypatch.setattr(readiness, "_run_component_checks", probe)
    monkeypatch.setattr(readiness.time, "monotonic", lambda: now)
    coordinator = readiness.ReadinessCoordinator()
    settings = Settings()

    async def exercise() -> None:
        nonlocal now
        assert (await coordinator.get(settings)).ready
        now += 29.9
        assert (await coordinator.get(settings)).ready
        now += 0.2
        assert (await coordinator.get(settings)).ready

    asyncio.run(exercise())
    assert calls == 2


def test_cancelled_waiter_does_not_cancel_shared_probe(monkeypatch) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def probe(_settings):
        started.set()
        await release.wait()
        return readiness.PublicReadiness(ready=True, components={"worker": "ok"})

    monkeypatch.setattr(readiness, "_run_component_checks", probe)
    coordinator = readiness.ReadinessCoordinator()
    settings = Settings()

    async def exercise() -> None:
        first = asyncio.create_task(coordinator.get(settings))
        await started.wait()
        first.cancel()
        try:
            await first
        except asyncio.CancelledError:
            pass
        second = asyncio.create_task(coordinator.get(settings))
        release.set()
        assert (await second).ready

    asyncio.run(exercise())


def _fully_configured_settings() -> Settings:
    signing_key = base64.b64encode(b"s" * 32).decode()
    return Settings(
        database_url="postgresql+asyncpg://local",
        redis_url="redis://local",
        object_storage_endpoint_url="http://storage",
        object_storage_public_endpoint_url="http://public-storage",
        object_storage_bucket="private",
        object_storage_access_key_id="access",
        object_storage_secret_access_key="secret",
        malware_scanner_host="scanner",
        trip_evidence_signing_keyring_b64=json.dumps({"1": signing_key}),
    )


@pytest.mark.parametrize(
    ("failed_probe", "component"),
    [
        ("_database_check", "database"),
        ("_broker_check", "redis"),
        ("_worker_check", "worker"),
        ("_storage_check", "storage"),
        ("_scanner_check", "scanner"),
        ("_signing_check", "trip_evidence_signing"),
    ],
)
def test_readiness_component_failure_matrix(
    monkeypatch, failed_probe: str, component: str
) -> None:
    async def passing(*_args, **_kwargs):
        return {"status": "ok"}

    async def failing(*_args, **_kwargs):
        raise RuntimeError("synthetic component failure")

    probe_names = (
        "_database_check",
        "_broker_check",
        "_worker_check",
        "_storage_check",
        "_scanner_check",
        "_signing_check",
    )
    for probe_name in probe_names:
        monkeypatch.setattr(readiness, probe_name, passing)
    monkeypatch.setattr(readiness, failed_probe, failing)

    result = asyncio.run(readiness._run_component_checks(_fully_configured_settings()))

    assert not result.ready
    assert result.components[component] == "unavailable"
    assert all(
        state == "ok" for name, state in result.components.items() if name != component
    )


def test_readiness_component_and_overall_hung_deadlines(monkeypatch) -> None:
    async def hung(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(readiness, "COMPONENT_TIMEOUT_SECONDS", 0.01)
    assert asyncio.run(readiness._component_state(True, hung)) == "unavailable"

    for probe_name in (
        "_database_check",
        "_broker_check",
        "_worker_check",
        "_storage_check",
        "_scanner_check",
        "_signing_check",
    ):
        monkeypatch.setattr(readiness, probe_name, hung)
    monkeypatch.setattr(readiness, "COMPONENT_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(readiness, "OVERALL_TIMEOUT_SECONDS", 0.01)
    result = asyncio.run(readiness._run_component_checks(_fully_configured_settings()))
    assert not result.ready
    assert set(result.components.values()) == {"unavailable"}


class _StorageCanaryFake:
    def __init__(self, failure: str) -> None:
        self.failure = failure
        self.deleted: list[str] = []

    async def put(self, **kwargs):
        if self.failure == "put":
            raise RuntimeError("synthetic put failure")
        return SimpleNamespace(checksum_sha256=kwargs["checksum_sha256"])

    async def stream(self, _object_key: str):
        if self.failure == "read":
            raise RuntimeError("synthetic read failure")
        if self.failure == "timeout":
            await asyncio.Event().wait()
        yield b"cardvert-private-storage-readiness-v1"

    async def delete(self, object_key: str) -> None:
        self.deleted.append(object_key)
        if self.failure == "delete":
            raise RuntimeError("synthetic delete failure")


@pytest.mark.parametrize("failure", ["put", "read", "delete"])
def test_storage_canary_attempts_cleanup_for_every_failure(
    monkeypatch, failure: str
) -> None:
    storage = _StorageCanaryFake(failure)
    monkeypatch.setattr(readiness, "build_storage_provider", lambda _settings: storage)

    def private_denial(*_args, **_kwargs):
        raise HTTPError("http://storage", 403, "denied", None, None)

    monkeypatch.setattr(readiness, "urlopen", private_denial)
    with pytest.raises(RuntimeError):
        asyncio.run(
            readiness._storage_check(
                write_canary=True, settings=_fully_configured_settings()
            )
        )
    assert len(storage.deleted) == 1


def test_storage_canary_timeout_still_cleans_up(monkeypatch) -> None:
    storage = _StorageCanaryFake("timeout")
    monkeypatch.setattr(readiness, "build_storage_provider", lambda _settings: storage)
    monkeypatch.setattr(readiness, "COMPONENT_TIMEOUT_SECONDS", 0.01)
    state = asyncio.run(
        readiness._component_state(
            True,
            lambda: readiness._storage_check(
                write_canary=True, settings=_fully_configured_settings()
            ),
        )
    )
    assert state == "unavailable"
    assert len(storage.deleted) == 1

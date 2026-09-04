from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from arq.connections import RedisSettings, create_pool
from arq.constants import (
    in_progress_key_prefix,
    job_key_prefix,
    result_key_prefix,
    retry_key_prefix,
)
from arq.worker import Worker, func
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.disbursement import (
    DisbursementInstruction,
    DisbursementProviderCapabilities,
    ProviderLookup,
    ProviderLookupStatus,
    ProviderSubmission,
)
from app.adapters.storage import (
    ObjectMetadata,
    PresignedGet,
    PresignedPost,
    StorageObjectConflict,
    StorageObjectNotFound,
)
from app.core.config import Settings
from app.jobs import file_lifecycle as file_lifecycle_jobs
from app.jobs.disbursements import process_disbursement_intent_job
from app.jobs.earnings_release import sweep_earnings_release_reviews
from app.jobs.file_lifecycle import recover_stored_object_deletions
from app.jobs.trip_processing import process_unprocessed_trips
from app.jobs.worker import WorkerSettings as ProductionWorkerSettings
from app.services.report_issuances import sweep_report_issuances

PROCESS_TIMEOUT_SECONDS = 30

RECOVERY_JOB_TARGETS: Mapping[str, str] = {
    "r58_earnings_release": "sweep_earnings_release_reviews",
    "r58_payout_submission": "process_disbursement_intent",
    "r58_object_deletion": "recover_stored_object_deletions",
    "r58_report_publication": "sweep_report_issuances",
    "r58_cursor_sweep": "process_unprocessed_trips",
}

REQUIRED_PRODUCT_REGISTRATIONS: Mapping[str, str] = {
    "sweep_earnings_release_reviews": "cron",
    "process_disbursement_intent": "function",
    "sweep_disbursement_intents": "cron",
    "recover_stored_object_deletions": "cron",
    "sweep_report_issuances": "cron",
    "process_unprocessed_trips": "cron",
}


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(document, stream, sort_keys=True, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _read_json(path: Path, default: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    return json.loads(path.read_text(encoding="utf-8"))


class DurableEffectStore:
    """Process-independent synthetic provider state with fsync-backed receipts."""

    def __init__(self, root: Path):
        self.root = root
        self.state_path = root / "effects.json"
        self.objects_path = root / "objects"
        self.objects_path.mkdir(parents=True, exist_ok=True)

    def read(self) -> dict[str, Any]:
        return _read_json(
            self.state_path,
            {
                "payout_effects": {},
                "payout_submit_requests": 0,
                "payout_lookup_requests": 0,
                "objects": {},
                "put_requests": 0,
                "delete_requests": 0,
                "delete_effects": 0,
            },
        )

    def write(self, state: Mapping[str, Any]) -> None:
        _atomic_json(self.state_path, state)

    def object_path(self, object_key: str) -> Path:
        return self.objects_path / hashlib.sha256(object_key.encode()).hexdigest()


async def _barrier(
    config: Mapping[str, Any], point: str, *, detail: Mapping[str, Any] | None = None
) -> None:
    if config.get("barrier_point") != point:
        return
    redis = AsyncRedis.from_url(str(config["redis_url"]), decode_responses=True)
    try:
        event = {
            "pid": os.getpid(),
            "point": point,
            "detail": dict(detail or {}),
        }
        await redis.rpush(str(config["event_key"]), json.dumps(event, sort_keys=True))
        await redis.blpop(str(config["release_key"]), timeout=PROCESS_TIMEOUT_SECONDS)
    finally:
        await redis.aclose()


class DurableDisbursementAdapter:
    capabilities = DisbursementProviderCapabilities(
        provider_name="fake",
        lookup_by_idempotency_key=True,
        semantic_same_key_idempotency=True,
    )

    def __init__(self, config: Mapping[str, Any]):
        self.config = config
        self.store = DurableEffectStore(Path(str(config["effect_root"])))

    async def submit_batch(
        self,
        *,
        batch_id: str,
        instructions: tuple[DisbursementInstruction, ...],
    ) -> ProviderSubmission:
        state = self.store.read()
        state["payout_submit_requests"] += 1
        references: dict[str, str] = {}
        submissions: set[str] = set()
        for instruction in instructions:
            effect = state["payout_effects"].get(instruction.idempotency_key)
            if effect is None:
                effect = {
                    "instruction_fingerprint": instruction.instruction_fingerprint,
                    "provider_submission_reference": f"r58-batch-{batch_id}",
                    "provider_transfer_reference": f"r58-line-{instruction.line_id}",
                }
                state["payout_effects"][instruction.idempotency_key] = effect
            elif effect["instruction_fingerprint"] != instruction.instruction_fingerprint:
                raise ValueError("idempotency key reused for different payout instructions")
            references[instruction.line_id] = effect["provider_transfer_reference"]
            submissions.add(effect["provider_submission_reference"])
        self.store.write(state)
        await _barrier(
            self.config,
            "payout_after_provider_acceptance",
            detail={"idempotency_keys": [item.idempotency_key for item in instructions]},
        )
        return ProviderSubmission(
            provider_reference=next(iter(submissions)),
            line_references=references,
        )

    async def lookup_line(
        self, *, idempotency_key: str, instruction_fingerprint: str
    ) -> ProviderLookup:
        state = self.store.read()
        state["payout_lookup_requests"] += 1
        effect = state["payout_effects"].get(idempotency_key)
        self.store.write(state)
        if effect is None:
            return ProviderLookup(status=ProviderLookupStatus.NOT_FOUND)
        if effect["instruction_fingerprint"] != instruction_fingerprint:
            return ProviderLookup(status=ProviderLookupStatus.UNKNOWN)
        return ProviderLookup(
            status=ProviderLookupStatus.FOUND,
            provider_submission_reference=effect["provider_submission_reference"],
            provider_transfer_reference=effect["provider_transfer_reference"],
        )


class DurableStorageProvider:
    def __init__(self, config: Mapping[str, Any]):
        self.config = config
        self.store = DurableEffectStore(Path(str(config["effect_root"])))
        self.put_count = 0
        self.delete_count = 0

    async def put(
        self,
        *,
        object_key: str,
        content_type: str,
        data: bytes,
        checksum_sha256: str,
    ) -> ObjectMetadata:
        observed_hash = hashlib.sha256(data).hexdigest()
        if observed_hash != checksum_sha256:
            raise StorageObjectConflict("checksum mismatch")
        state = self.store.read()
        state["put_requests"] += 1
        existing = state["objects"].get(object_key)
        metadata = {
            "object_key": object_key,
            "content_type": content_type,
            "size_bytes": len(data),
            "checksum_sha256": checksum_sha256,
        }
        if existing is not None and existing != metadata:
            raise StorageObjectConflict("immutable object mismatch")
        object_path = self.store.object_path(object_key)
        if object_path.exists() and object_path.read_bytes() != data:
            raise StorageObjectConflict("immutable object bytes mismatch")
        if not object_path.exists():
            with object_path.open("wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        state["objects"][object_key] = metadata
        self.store.write(state)
        self.put_count += 1
        if self.put_count == 1:
            await _barrier(
                self.config,
                "report_after_first_artifact",
                detail={"object_key": object_key},
            )
        return ObjectMetadata(**metadata)

    async def stat(self, object_key: str) -> ObjectMetadata:
        state = self.store.read()
        metadata = state["objects"].get(object_key)
        if metadata is None or not self.store.object_path(object_key).exists():
            raise StorageObjectNotFound(object_key)
        return ObjectMetadata(**metadata)

    async def delete(self, object_key: str) -> None:
        state = self.store.read()
        state["delete_requests"] += 1
        object_path = self.store.object_path(object_key)
        existed = object_key in state["objects"] or object_path.exists()
        state["objects"].pop(object_key, None)
        object_path.unlink(missing_ok=True)
        if existed:
            state["delete_effects"] += 1
        self.store.write(state)
        self.delete_count += 1
        point = str(self.config.get("barrier_point") or "")
        if self.delete_count == 1 and point in {
            "deletion_after_object_delete",
            "report_during_cleanup",
        }:
            await _barrier(
                self.config,
                point,
                detail={"object_key": object_key, "existed": existed},
            )

    async def stream(self, object_key: str) -> AsyncIterator[bytes]:
        await self.stat(object_key)
        yield self.store.object_path(object_key).read_bytes()

    async def presign_get(self, *, object_key: str, expires_in_seconds: int) -> PresignedGet:
        await self.stat(object_key)
        return PresignedGet(
            url=f"https://r58.invalid/{hashlib.sha256(object_key.encode()).hexdigest()}",
            expires_in_seconds=expires_in_seconds,
        )

    async def presign_post(self, **_kwargs: object) -> PresignedPost:
        raise NotImplementedError("R58 recovery workers never presign uploads")

    async def promote(self, *, source_key: str, destination_key: str) -> ObjectMetadata:
        source = await self.stat(source_key)
        data = self.store.object_path(source_key).read_bytes()
        promoted = await self.put(
            object_key=destination_key,
            content_type=source.content_type,
            data=data,
            checksum_sha256=source.checksum_sha256,
        )
        await self.delete(source_key)
        return promoted


async def r58_earnings_release(ctx: dict[str, Any]) -> dict[str, int]:
    await _barrier(ctx["recovery_config"], "earnings_after_claim")
    return await sweep_earnings_release_reviews(ctx)


async def r58_payout_submission(ctx: dict[str, Any], intent_id: str) -> dict[str, str]:
    result = await process_disbursement_intent_job(ctx, intent_id)
    await _barrier(
        ctx["recovery_config"],
        "payout_after_local_commit",
        detail={"intent_id": intent_id, "outcome": result["outcome"]},
    )
    return result


async def r58_object_deletion(ctx: dict[str, Any]) -> dict[str, int]:
    completed = await recover_stored_object_deletions(ctx)
    return completed


async def r58_report_publication(ctx: dict[str, Any]) -> int:
    result = await sweep_report_issuances(ctx)
    await _barrier(
        ctx["recovery_config"],
        "report_after_publication_commit",
        detail={"claims": result},
    )
    return result


async def r58_cursor_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    result = await process_unprocessed_trips(ctx)
    await _barrier(
        ctx["recovery_config"],
        "cursor_after_persist",
        detail={"selected": result["selected"], "processed": result["processed"]},
    )
    return result


R58_FUNCTIONS = (
    func(r58_earnings_release, name="r58_earnings_release", keep_result=0),
    func(r58_payout_submission, name="r58_payout_submission", keep_result=0),
    func(r58_object_deletion, name="r58_object_deletion", keep_result=0),
    func(r58_report_publication, name="r58_report_publication", keep_result=0),
    func(r58_cursor_sweep, name="r58_cursor_sweep", keep_result=0),
)


async def _run_worker(config_path: Path) -> None:
    config = _read_json(config_path)
    settings_document = dict(config["settings"])
    settings_document.update(
        database_url=config["database_url"],
        redis_url=config["redis_url"],
    )
    settings = Settings(**settings_document)
    engine = create_async_engine(
        str(config["database_url"]),
        connect_args={"server_settings": {"search_path": f"{config['schema_name']},public"}},
        execution_options={"schema_translate_map": {None: config["schema_name"]}},
        poolclass=NullPool,
    )
    storage = DurableStorageProvider(config)
    file_lifecycle_jobs.build_storage_provider = lambda _settings: storage
    ctx = {
        "settings": settings,
        "engine": engine,
        "sessionmaker": async_sessionmaker(engine, expire_on_commit=False),
        "storage": storage,
        "disbursement_adapter": DurableDisbursementAdapter(config),
        "recovery_config": config,
    }

    async def on_job_start(job_ctx: dict[str, Any]) -> None:
        event = {
            "pid": os.getpid(),
            "point": "broker_claimed",
            "detail": {"job_id": job_ctx["job_id"], "job_try": job_ctx["job_try"]},
        }
        redis = AsyncRedis.from_url(str(config["redis_url"]), decode_responses=True)
        try:
            await redis.rpush(str(config["event_key"]), json.dumps(event, sort_keys=True))
        finally:
            await redis.aclose()

    worker = Worker(
        functions=(*ProductionWorkerSettings.functions, *R58_FUNCTIONS),
        queue_name=str(config["queue_name"]),
        redis_settings=RedisSettings.from_dsn(str(config["redis_url"])),
        burst=True,
        max_jobs=1,
        max_tries=5,
        poll_delay=0,
        keep_result=0,
        health_check_interval=3600,
        on_job_start=on_job_start,
        ctx=ctx,
    )
    try:
        await worker.run_check()
    finally:
        await worker.close()
        await engine.dispose()


@dataclass(frozen=True)
class QueueState:
    queued: bool
    in_progress: bool
    payload_present: bool
    retry_count: int
    result_present: bool


@dataclass(frozen=True)
class RecoveryReceipt:
    scenario: str
    pid: int
    signal: str
    job: str
    idempotency_key: str
    queue_state: Mapping[str, Any]
    db_state: Mapping[str, Any]
    external_effect_state: Mapping[str, Any]
    cursor_deadletter_state: Mapping[str, Any]
    terminal_convergence: Mapping[str, Any]

    def persist(self, path: Path) -> dict[str, Any]:
        document = asdict(self)
        _atomic_json(path, document)
        return _read_json(path)


class WorkerProcessHarness:
    def __init__(
        self,
        *,
        tmp_path: Path,
        redis_url: str,
        database_url: str,
        schema_name: str,
        settings: Settings,
        scenario: str,
    ) -> None:
        self.tmp_path = tmp_path
        self.redis_url = redis_url
        self.database_url = database_url
        self.schema_name = schema_name
        self.settings = settings
        self.scenario = scenario
        self.identity = hashlib.sha256(f"{scenario}:{tmp_path}".encode()).hexdigest()[:20]
        self.queue_name = f"arq:r58:{self.identity}"
        self.event_key = f"r58:{self.identity}:events"
        self.release_key = f"r58:{self.identity}:release"
        self.effect_root = tmp_path / "provider-state"
        self.config_path = tmp_path / "worker-config.json"
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.process: subprocess.Popen[str] | None = None
        self.job_id: str | None = None
        self.function_name: str | None = None

    def enqueue(self, function: str, *args: Any, job_id: str) -> None:
        async def enqueue_job() -> None:
            pool = await create_pool(
                RedisSettings.from_dsn(self.redis_url),
                default_queue_name=self.queue_name,
            )
            try:
                job = await pool.enqueue_job(
                    function,
                    *args,
                    _job_id=job_id,
                    _queue_name=self.queue_name,
                )
                if job is None:
                    raise AssertionError(f"ARQ refused recovery job {job_id}")
            finally:
                await pool.aclose()

        asyncio.run(enqueue_job())
        self.job_id = job_id
        self.function_name = function

    def start(self, *, barrier_point: str | None) -> subprocess.Popen[str]:
        if self.job_id is None:
            raise AssertionError("enqueue a recovery job before starting its worker")
        settings_document = self.settings.model_dump(mode="json")
        for field_name in type(self.settings).model_fields:
            value = getattr(self.settings, field_name)
            if hasattr(value, "get_secret_value"):
                settings_document[field_name] = value.get_secret_value()
        config = {
            "scenario": self.scenario,
            "barrier_point": barrier_point,
            "redis_url": self.redis_url,
            "database_url": self.database_url,
            "schema_name": self.schema_name,
            "settings": settings_document,
            "queue_name": self.queue_name,
            "event_key": self.event_key,
            "release_key": self.release_key,
            "effect_root": str(self.effect_root),
        }
        _atomic_json(self.config_path, config)
        environment = os.environ.copy()
        repository_root = str(Path(__file__).resolve().parents[1])
        existing_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = f"{repository_root}:{repository_root}/tests" + (
            f":{existing_pythonpath}" if existing_pythonpath else ""
        )
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--worker", str(self.config_path)],
            cwd=repository_root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return self.process

    def wait_for(self, point: str) -> dict[str, Any]:
        deadline = time.monotonic() + PROCESS_TIMEOUT_SECONDS
        observed: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            item = self.redis.blpop(self.event_key, timeout=1)
            if item is not None:
                event = json.loads(item[1])
                observed.append(event)
                if event["point"] == point:
                    return event
            if self.process is not None and self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                raise AssertionError(
                    f"worker exited before {point}; events={observed}; "
                    f"stdout={stdout!r}; stderr={stderr!r}"
                )
        raise AssertionError(f"worker did not reach {point}; events={observed}")

    def kill(self) -> int:
        if self.process is None or self.process.poll() is not None:
            raise AssertionError("worker is not running at the requested crash point")
        pid = self.process.pid
        os.kill(pid, signal.SIGKILL)
        returncode = self.process.wait(timeout=PROCESS_TIMEOUT_SECONDS)
        if returncode != -signal.SIGKILL:
            raise AssertionError(f"worker exit {returncode} was not SIGKILL")
        return pid

    def queue_state(self) -> QueueState:
        if self.job_id is None:
            raise AssertionError("recovery job id is unavailable")
        retry = self.redis.get(f"{retry_key_prefix}{self.job_id}")
        return QueueState(
            queued=self.redis.zscore(self.queue_name, self.job_id) is not None,
            in_progress=bool(self.redis.exists(f"{in_progress_key_prefix}{self.job_id}")),
            payload_present=bool(self.redis.exists(f"{job_key_prefix}{self.job_id}")),
            retry_count=int(retry or 0),
            result_present=bool(self.redis.exists(f"{result_key_prefix}{self.job_id}")),
        )

    def unlock_dead_worker(self) -> None:
        if self.job_id is None:
            raise AssertionError("recovery job id is unavailable")
        if self.process is None or self.process.returncode != -signal.SIGKILL:
            raise AssertionError("only a confirmed SIGKILLed worker lock may be reclaimed")
        # ARQ keeps the orphaned in-progress key until its job-timeout TTL. The
        # queued payload is the broker authority, so reclaim only that stale key
        # after proving the owning OS process is dead, then exercise a real restart.
        self.redis.delete(f"{in_progress_key_prefix}{self.job_id}")

    def finish(self, *, barrier_point: str | None = None) -> None:
        process = self.start(barrier_point=barrier_point)
        stdout, stderr = process.communicate(timeout=PROCESS_TIMEOUT_SECONDS)
        if process.returncode != 0:
            raise AssertionError(
                f"recovery worker failed with {process.returncode}; "
                f"stdout={stdout!r}; stderr={stderr!r}"
            )

    def effects(self) -> dict[str, Any]:
        return DurableEffectStore(self.effect_root).read()

    def persist_receipt(
        self,
        *,
        name: str,
        pid: int,
        idempotency_key: str,
        queue_state: Mapping[str, Any],
        db_state: Mapping[str, Any],
        cursor_deadletter_state: Mapping[str, Any],
        terminal_convergence: Mapping[str, Any],
    ) -> dict[str, Any]:
        receipt = RecoveryReceipt(
            scenario=name,
            pid=pid,
            signal="SIGKILL",
            job=self.function_name or "",
            idempotency_key=idempotency_key,
            queue_state=queue_state,
            db_state=db_state,
            external_effect_state=self.effects(),
            cursor_deadletter_state=cursor_deadletter_state,
            terminal_convergence=terminal_convergence,
        )
        return receipt.persist(self.tmp_path / f"{name}.receipt.json")

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=PROCESS_TIMEOUT_SECONDS)
        keys = [self.queue_name, self.event_key, self.release_key]
        if self.job_id is not None:
            keys.extend(
                [
                    f"{job_key_prefix}{self.job_id}",
                    f"{in_progress_key_prefix}{self.job_id}",
                    f"{retry_key_prefix}{self.job_id}",
                    f"{result_key_prefix}{self.job_id}",
                ]
            )
        self.redis.delete(*keys)
        self.redis.close()


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(_run_worker(args.worker))


if __name__ == "__main__":
    _main()

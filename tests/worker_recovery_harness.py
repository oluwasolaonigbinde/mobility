from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arq.connections import RedisSettings
from arq.worker import Worker, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.disbursement import (
    DisbursementInstruction,
    DisbursementProviderCapabilities,
    ProviderLookup,
    ProviderLookupStatus,
    ProviderSubmission,
    VerifiedLineEvidence,
)
from app.adapters.storage import (
    ObjectMetadata,
    PresignedGet,
    PresignedPost,
    StorageObjectConflict,
    StorageObjectNotFound,
)
from app.core.config import Settings
from app.jobs import file_lifecycle
from app.jobs.disbursements import process_disbursement_intent_job
from app.jobs.earnings_release import sweep_earnings_release_reviews
from app.jobs.file_lifecycle import recover_stored_object_deletions
from app.jobs.trip_processing import process_unprocessed_trips
from app.jobs.worker import WorkerSettings
from app.services.report_issuances import sweep_report_issuances


@dataclass(frozen=True, slots=True)
class RecoveryJobRegistration:
    name: str
    coroutine: Any
    max_tries: int | None


RECOVERY_JOB_REGISTRATIONS = (
    RecoveryJobRegistration(
        "cron:sweep_earnings_release_reviews", sweep_earnings_release_reviews, 1
    ),
    RecoveryJobRegistration("process_disbursement_intent", process_disbursement_intent_job, None),
    RecoveryJobRegistration(
        "cron:recover_stored_object_deletions", recover_stored_object_deletions, 1
    ),
    RecoveryJobRegistration("cron:sweep_report_issuances", sweep_report_issuances, 1),
    RecoveryJobRegistration("cron:process_unprocessed_trips", process_unprocessed_trips, 1),
)


@dataclass(frozen=True, slots=True)
class RecoveryReceipt:
    cut_point: str
    process_pid: int
    exit_signal: int
    job_id: str
    idempotency_key: str
    queue_state: dict[str, Any]
    database_state: dict[str, Any]
    provider_effect_count: int
    cursor_state: dict[str, Any]
    dead_letter_state: dict[str, Any]
    post_restart_convergence: dict[str, Any]

    def write(self, path: Path) -> None:
        _atomic_json(path, asdict(self))


def registered_recovery_jobs() -> dict[str, Any]:
    functions = {registered.name: registered for registered in WorkerSettings.functions}
    functions.update({registered.name: registered for registered in WorkerSettings.cron_jobs})
    return functions


def _recovery_function(name: str, coroutine: Any) -> Any:
    registered = registered_recovery_jobs()[name]
    return func(
        coroutine,
        name=registered.name,
        keep_result=registered.keep_result_s,
        timeout=registered.timeout_s,
        keep_result_forever=registered.keep_result_forever,
        max_tries=registered.max_tries,
    )


def _state_root() -> Path:
    return Path(os.environ["R58_STATE_ROOT"])


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _append_event(event: str, *, state_root: Path | None = None, **payload: Any) -> None:
    path = (state_root or _state_root()) / "provider-events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "event": event,
        "pid": os.getpid(),
        "recorded_at": datetime.now(UTC).isoformat(),
        **payload,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(document, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


async def _checkpoint(label: str) -> None:
    if os.environ.get("R58_CUT_POINT") != label:
        return
    marker = _state_root() / "markers" / f"{label}.json"
    _atomic_json(
        marker,
        {
            "label": label,
            "pid": os.getpid(),
            "recorded_at": datetime.now(UTC).isoformat(),
        },
    )
    release = _state_root() / "releases" / label
    while not release.exists():
        await asyncio.sleep(0.02)


class PersistentDisbursementAdapter:
    capabilities = DisbursementProviderCapabilities(
        provider_name="fake",
        lookup_by_idempotency_key=True,
        semantic_same_key_idempotency=True,
    )

    @property
    def _effects_path(self) -> Path:
        return _state_root() / "disbursement-effects.json"

    def _effects(self) -> dict[str, Any]:
        return _load_json(self._effects_path, {})

    async def submit_batch(
        self,
        *,
        batch_id: str,
        instructions: tuple[DisbursementInstruction, ...],
    ) -> ProviderSubmission:
        effects = self._effects()
        line_references: dict[str, str] = {}
        submission_references: set[str] = set()
        for instruction in instructions:
            effect = effects.get(instruction.idempotency_key)
            if effect is None:
                effect = {
                    "batch_reference": f"r58-batch-{batch_id}",
                    "transfer_reference": f"r58-line-{instruction.line_id}",
                    "instruction_fingerprint": instruction.instruction_fingerprint,
                }
                effects[instruction.idempotency_key] = effect
                _atomic_json(self._effects_path, effects)
                _append_event(
                    "disbursement_accepted",
                    idempotency_key=instruction.idempotency_key,
                    line_id=instruction.line_id,
                )
            elif effect["instruction_fingerprint"] != instruction.instruction_fingerprint:
                raise ValueError("An idempotency key was reused for a different instruction")
            line_references[instruction.line_id] = effect["transfer_reference"]
            submission_references.add(effect["batch_reference"])
        await _checkpoint("payout_after_provider_acceptance")
        if len(submission_references) != 1:
            raise ValueError("A batch resolved to conflicting provider submissions")
        return ProviderSubmission(
            provider_reference=next(iter(submission_references)),
            line_references=line_references,
        )

    async def lookup_line(
        self,
        *,
        idempotency_key: str,
        instruction_fingerprint: str,
    ) -> ProviderLookup:
        effect = self._effects().get(idempotency_key)
        if effect is None:
            return ProviderLookup(status=ProviderLookupStatus.NOT_FOUND)
        if effect["instruction_fingerprint"] != instruction_fingerprint:
            return ProviderLookup(status=ProviderLookupStatus.UNKNOWN)
        _append_event("disbursement_lookup_found", idempotency_key=idempotency_key)
        return ProviderLookup(
            status=ProviderLookupStatus.FOUND,
            provider_submission_reference=effect["batch_reference"],
            provider_transfer_reference=effect["transfer_reference"],
        )

    async def verify_webhook(self, *, payload: bytes, signature: str) -> VerifiedLineEvidence:
        del payload, signature
        raise NotImplementedError

    async def poll_line(self, *, provider_transfer_reference: str) -> VerifiedLineEvidence:
        del provider_transfer_reference
        raise NotImplementedError


class PersistentStorageProvider:
    def __init__(self, root: Path | None = None) -> None:
        self.state_root = root.parent if root is not None else _state_root()
        self.root = root or (self.state_root / "storage")
        self.root.mkdir(parents=True, exist_ok=True)

    def _paths(self, object_key: str) -> tuple[Path, Path]:
        identity = hashlib.sha256(object_key.encode()).hexdigest()
        return self.root / f"{identity}.json", self.root / f"{identity}.bin"

    async def presign_post(
        self,
        *,
        object_key: str,
        content_type: str,
        size_bytes: int,
        checksum_sha256: str,
        expires_in_seconds: int,
    ) -> PresignedPost:
        del object_key, content_type, size_bytes, checksum_sha256, expires_in_seconds
        raise NotImplementedError

    async def stat(self, object_key: str) -> ObjectMetadata:
        metadata_path, content_path = self._paths(object_key)
        try:
            document = json.loads(metadata_path.read_text(encoding="utf-8"))
            content = content_path.read_bytes()
        except FileNotFoundError:
            raise StorageObjectNotFound(object_key) from None
        checksum = hashlib.sha256(content).hexdigest()
        if checksum != document["checksum_sha256"] or len(content) != document["size_bytes"]:
            raise StorageObjectConflict("Persistent test object metadata does not match its bytes")
        return ObjectMetadata(
            object_key=object_key,
            size_bytes=len(content),
            content_type=document["content_type"],
            checksum_sha256=checksum,
        )

    async def put(
        self,
        *,
        object_key: str,
        content_type: str,
        data: bytes,
        checksum_sha256: str,
    ) -> ObjectMetadata:
        if hashlib.sha256(data).hexdigest() != checksum_sha256:
            raise StorageObjectConflict("Persistent test object checksum mismatch")
        metadata_path, content_path = self._paths(object_key)
        if metadata_path.exists() or content_path.exists():
            existing = await self.stat(object_key)
            if (
                existing.content_type != content_type
                or existing.size_bytes != len(data)
                or existing.checksum_sha256 != checksum_sha256
            ):
                raise StorageObjectConflict("Persistent test object already exists")
            return existing
        with content_path.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _atomic_json(
            metadata_path,
            {
                "object_key": object_key,
                "content_type": content_type,
                "size_bytes": len(data),
                "checksum_sha256": checksum_sha256,
            },
        )
        _append_event("object_put", state_root=self.state_root, object_key=object_key)
        report_puts = [
            event
            for event in read_provider_events(self.state_root)
            if event["event"] == "object_put" and "/reports/" in event["object_key"]
        ]
        if len(report_puts) == 1:
            await _checkpoint("report_after_first_artifact")
        return await self.stat(object_key)

    async def stream(self, object_key: str) -> AsyncIterator[bytes]:
        _, content_path = self._paths(object_key)
        try:
            yield content_path.read_bytes()
        except FileNotFoundError:
            raise StorageObjectNotFound(object_key) from None

    async def presign_get(self, *, object_key: str, expires_in_seconds: int) -> PresignedGet:
        del object_key, expires_in_seconds
        raise NotImplementedError

    async def promote(self, *, source_key: str, destination_key: str) -> ObjectMetadata:
        del source_key, destination_key
        raise NotImplementedError

    async def delete(self, object_key: str) -> None:
        metadata_path, content_path = self._paths(object_key)
        exists = metadata_path.exists() and content_path.exists()
        if not exists:
            _append_event(
                "object_delete_not_found", state_root=self.state_root, object_key=object_key
            )
            if object_key.startswith("r58/deletion/"):
                raise StorageObjectNotFound(object_key)
            return
        metadata_path.unlink()
        content_path.unlink()
        _append_event("object_deleted", state_root=self.state_root, object_key=object_key)
        if object_key.startswith("r58/deletion/"):
            await _checkpoint("deletion_after_provider_delete")

    def keys(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                json.loads(path.read_text(encoding="utf-8"))["object_key"]
                for path in self.root.glob("*.json")
            )
        )


def read_provider_events(root: Path) -> list[dict[str, Any]]:
    path = root / "provider-events.jsonl"
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except FileNotFoundError:
        return []


def _record_job_start(ctx: dict[str, Any], function: str) -> None:
    _append_event(
        "job_started",
        function=function,
        job_id=ctx["job_id"],
        job_try=ctx["job_try"],
    )


async def _earnings_job(ctx: dict[str, Any]) -> dict[str, int]:
    _record_job_start(ctx, "cron:sweep_earnings_release_reviews")
    await _checkpoint("earnings_after_claim")
    return await sweep_earnings_release_reviews(ctx)


async def _disbursement_job(ctx: dict[str, Any], intent_id: str) -> dict[str, str]:
    _record_job_start(ctx, "process_disbursement_intent")
    result = await process_disbursement_intent_job(ctx, intent_id)
    await _checkpoint("payout_after_commit")
    return result


async def _deletion_job(ctx: dict[str, Any]) -> dict[str, int]:
    _record_job_start(ctx, "cron:recover_stored_object_deletions")
    return await recover_stored_object_deletions(ctx)


async def _report_job(ctx: dict[str, Any]) -> int:
    _record_job_start(ctx, "cron:sweep_report_issuances")
    result = await sweep_report_issuances(ctx)
    await _checkpoint("report_after_publication_commit")
    await _checkpoint("report_after_dead_letter")
    return result


async def _cursor_job(ctx: dict[str, Any]) -> dict[str, Any]:
    _record_job_start(ctx, "cron:process_unprocessed_trips")
    result = await process_unprocessed_trips(ctx)
    await _checkpoint("cursor_after_write")
    return result


async def _startup(ctx: dict[str, Any]) -> None:
    settings = Settings(
        environment="test",
        database_url=os.environ["R58_DATABASE_URL"],
        redis_url=os.environ["R58_REDIS_URL"],
        payout_crypto_keyring_b64=('{"1":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="}'),
        privacy_disclosure_synthetic_test_mode=True,
        privacy_collection_synthetic_test_mode=True,
        privacy_min_vehicles_per_cell=1,
        privacy_min_trips_per_cell=1,
        privacy_min_days_per_cell=1,
        privacy_max_contributor_share=1.0,
        privacy_min_resolution_m=50,
        installation_evidence_uploader_roles="driver,admin",
        installation_evidence_required_views="front,close_up",
        installation_evidence_validity_hours=24,
        display_proof_challenge_ttl_seconds=120,
        display_proof_validity_seconds=3600,
        worker_sweep_batch_size=int(os.environ.get("R58_SWEEP_BATCH_SIZE", "25")),
    )
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    storage = PersistentStorageProvider()
    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["sessionmaker"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["storage"] = storage
    ctx["disbursement_adapter"] = PersistentDisbursementAdapter()
    file_lifecycle.build_storage_provider = lambda _settings: storage


async def _shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()


async def _run_worker() -> None:
    worker = Worker(
        functions=(
            _recovery_function(
                "cron:sweep_earnings_release_reviews",
                _earnings_job,
            ),
            _recovery_function(
                "process_disbursement_intent",
                _disbursement_job,
            ),
            _recovery_function(
                "cron:recover_stored_object_deletions",
                _deletion_job,
            ),
            _recovery_function("cron:sweep_report_issuances", _report_job),
            _recovery_function("cron:process_unprocessed_trips", _cursor_job),
        ),
        redis_settings=RedisSettings.from_dsn(os.environ["R58_REDIS_URL"]),
        queue_name=os.environ["R58_QUEUE_NAME"],
        poll_delay=0.02,
        max_jobs=1,
        keep_result=0,
        on_startup=_startup,
        on_shutdown=_shutdown,
    )
    worker.in_progress_timeout_s = float(os.environ.get("R58_IN_PROGRESS_SECONDS", "1"))
    await worker.async_run()


if __name__ == "__main__":
    asyncio.run(_run_worker())

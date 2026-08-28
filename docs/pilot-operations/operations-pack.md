# Provider-neutral controlled-pilot operations pack

All records below are blank preparation templates. Complete them only in an
approved protected evidence store after the missing authority exists. Keep
repository copies placeholder-only. Every observation must be labelled
`SYNTHETIC_LOCAL` or `LIVE_APPROVED`; this checkpoint permits only
`SYNTHETIC_LOCAL`.

Existing categorical fail-closed rules are authoritative. Provider-specific
numeric alert values are not: leave value, comparator, unit, window, and source
as `<PLACEHOLDER — APPROVAL REQUIRED>`. A local regression ceiling from the
[Package 8 load harness](../pkg-08-w4-03b-load-reproducibility.md) must be
recorded as `SYNTHETIC_TEST_ONLY`, never as a production SLO.

## Domain: telemetry-readiness

Authoritative sources:
[release observability and alerts](../w4-03a-release-operations.md),
[worker and lifecycle runbook](../runbook.md), and the database/release state
they identify.

Authoritative state:
The readiness endpoint, release state, database Alembic revision, worker job
state, private-storage canary, report issuance rows, and W4-03C gate registry
remain the truth. This template records an observation; it cannot override any
of them.

Roles:
- observer: `<OPERATIONS_OWNER_ROLE>`
- stop-decision owner: `<INCIDENT_COMMANDER_ROLE>`
- domain responder: `<SERVICE_SUPPORT_COORDINATOR_ROLE>`

Stop criteria:
Stop or keep the affected path closed on any non-ready response, image/database
migration mismatch, missing or stale worker heartbeat, growing queue with no
convergence, failed/retry-exhausted job, failed storage write/read/delete
canary, incomplete or mismatched report pair, or unexplained gate-state drift.
Numeric alert threshold value/comparator/unit/window/source:
`<PLACEHOLDER — APPROVAL REQUIRED>`.

Evidence fields:
`scenario_id`, `classification`, `observed_at_utc`, `environment_label`,
`release_id`, `release_revision`, `config_sha256`, `alembic_revision`,
`edge_request_id`, `request_id`, `job_id`, `readiness_status`,
`worker_heartbeat_age`, `queue_depth`, `oldest_job_id`, `failed_job_count`,
`storage_canary_status`, `report_pair_status`, `gate_snapshot_reference`,
`threshold_value`, `threshold_comparator`, `threshold_unit`, `threshold_window`,
`threshold_source`, `stop_decision`, `decision_actor`, and
`protected_evidence_pointer`.

Ordered preparation procedure:
1. Assign a synthetic scenario ID and record the exact local command/test node.
2. Capture only redacted status, counts, revisions, hashes, and correlation IDs.
3. Compare observations with the categorical stops above; never infer success
   from one green signal while another required signal is absent.
4. Record `STOP` or `CONTINUE_SYNTHETIC_ONLY`, the reason, actor placeholder,
   and protected-store pointer.
5. Reobserve through the same integrated entry point after recovery; retain the
   before/after evidence chain.

Do not:
Do not add a real DSN, query a provider dashboard, copy raw request/job payloads,
precise GPS, private URLs, secrets, or reinterpret a synthetic ceiling as a
production threshold.

## Domain: rollback-recovery

Authoritative sources:
[release recovery](../w4-03a-release-operations.md) and the existing
[recovery script](../../scripts/recover_release.sh). The script is an
authority-only future entry point, not a synthetic exercise command.

Authoritative state:
The protected release state, exact current/previous immutable images, forward
database revision, compatibility evidence, readiness result, and traffic state
govern recovery. Application recovery never means schema downgrade. Data
restore is a separately approved disaster-recovery action.

Roles:
- incident commander: `<INCIDENT_COMMANDER_ROLE>`
- recovery operator: `<RELEASE_OPERATOR_ROLE>`
- compatibility checker: `<EVIDENCE_CHECKER_ROLE>`
- data-restore security authority: `<SECURITY_OWNER_ROLE>`

Stop criteria:
Keep traffic stopped if release identity/config/revision differs, previous-image
compatibility is absent or mismatched, state is stale/conflicting, readiness or
authenticated smoke fails, migration heads differ, or evidence is incomplete.
There is no numeric override for these categorical stops.

Evidence fields:
`incident_id`, `decision_time_utc`, `release_id`, `current_revision`,
`previous_revision`, `current_image_digests`, `previous_image_digests`,
`config_sha256`, `alembic_revision`, `compatibility_evidence_pointer`,
`release_state_pointer`, `traffic_state_before`, `decision`, `decision_reason`,
`incident_commander`, `recovery_operator`, `checker`, `execution_started_at`,
`execution_finished_at`, `readiness_result`, `smoke_result`,
`traffic_state_after`, `rollback_outcome`, and `protected_evidence_pointer`.

Ordered preparation procedure:
1. Record `HOLD_TRAFFIC`, `CONTINUE_CURRENT`, or `RECOVER_PREVIOUS_IMAGE`; leave
   all actors and protected inputs as placeholders in this repository.
2. Validate the decision template using the local static tests in the exercise
   matrix. Do not run `release.sh`, `recover_release.sh`, or
   `rehearse_w403a.sh` for this checkpoint.
3. For a future approved incident only, follow the release runbook exactly with
   its protected inputs; do not hand-compose a substitute command.
4. Preserve failure output, keep the edge closed on any failed stage, and record
   readiness/smoke plus the exact before/after traffic state.
5. Escalate rather than downgrade, restore populated data, or reopen traffic
   when compatibility/recovery proof is incomplete.

Do not:
Do not execute a release/recovery script as a local documentation exercise,
invent compatibility evidence, run Alembic downgrade, replace populated data,
or treat rollback preparation as rollback execution.

## Domain: payout-replay

Authoritative sources:
[synthetic journey payout boundary](../pkg-08-w4-03b-synthetic-journey.md),
[payout reconciliation tests](../../tests/test_payout_reconciliation.py), and
[provider-disabled tests](../../tests/test_payout_batches.py). Persisted payout
batch, line, instruction, ledger, and reconciliation-event rows remain the
money authority.

Authoritative state:
Replay uses the existing batch/line idempotency and provider-reference identity.
It may converge an identical retry; it may not recalculate, edit, or manufacture
money. The exercise uses only the in-process fake adapter and performs zero
external provider actions.

Roles:
- maker: `<MONEY_MAKER_ROLE>`
- checker: `<MONEY_CHECKER_ROLE>`
- reconciler: `<MONEY_RECONCILER_ROLE>`
- incident commander: `<INCIDENT_COMMANDER_ROLE>`

Stop criteria:
Stop before submission/replay on an unavailable approved provider, missing
maker-checker-reconciler separation, changed idempotency key, provider reference
or instruction hash, amount/currency drift, forged or reordered conflicting
evidence, unresolved line, active hold, or any attempt to mark paid without
provider finality.

Evidence fields:
`scenario_id`, `batch_id`, `batch_status_before`, `batch_status_after`,
`line_id`, `line_status_before`, `line_status_after`, `idempotency_key`,
`provider_transfer_reference`, `provider_event_id`, `instruction_sha256`,
`amount`, `currency`, `ledger_entry_id`, `ledger_finality_before`,
`ledger_finality_after`, `maker_id`, `checker_id`, `reconciler_id`,
`adapter_classification`, `external_provider_actions`, `retry_count`,
`stop_reason`, `reconciliation_event_ids`, and `protected_evidence_pointer`.

Ordered preparation procedure:
1. Freeze the persisted batch/line identity, instruction hash, amount, currency,
   roles, and ledger status before retry.
2. Verify maker, checker, and reconciler are distinct; otherwise stop.
3. Replay only the existing idempotent path with the identical identity; changed
   facts conflict and require incident handling, not a new reference.
4. Reconcile each line through existing verified webhook/poll authority; a
   partial failure cannot mark the batch complete or the unresolved ledger paid.
5. Compare before/after line, batch, ledger, and reconciliation-event evidence;
   escalate any conservation mismatch.

Do not:
Do not supply credentials, contact a provider, submit a financially effective
transfer, edit ledger/history, reuse one operator across separated roles, or
convert a synthetic fake-adapter result into payment evidence.

## Domain: report-replay

Authoritative sources:
[bounded issuance contract](../pkg-08-w4-02b-bounded-issuance.md),
[report issuance tests](../../tests/test_report_issuances.py), and persisted
measurement run, issuance, artifact, stored-file, and worker lease rows.

Authoritative state:
An identical accepted request identity returns its frozen issuance. A changed
retry conflicts. CSV and PDF remain an atomic pair; terminal recovery creates
an append-only reissue version rather than rewriting history.

Roles:
- request owner: `<BUSINESS_ACCOUNTABLE_ROLE>`
- report operator: `<OPERATIONS_OWNER_ROLE>`
- evidence checker: `<EVIDENCE_CHECKER_ROLE>`
- privacy authority: `<PRIVACY_DECISION_ROLE>`
- method authority: `<REPORT_METHOD_AUTHORITY_ROLE>`

Stop criteria:
Withhold status/download on request identity or fingerprint conflict, source/run
drift, revoked role/privacy/method authority, partial CSV/PDF publication,
artifact/file hash or metadata mismatch, stale unreconciled lease, or storage
failure. A terminal failure requires append-only reissue, never mutation.

Evidence fields:
`scenario_id`, `request_id`, `request_fingerprint`, `measurement_run_id`,
`measurement_input_sha256`, `measurement_result_sha256`, `issuance_id`,
`issuance_version`, `reissue_of_id`, `worker_lease_id`, `worker_attempts`,
`status_before`, `status_after`, `csv_artifact_id`, `csv_sha256`,
`pdf_artifact_id`, `pdf_sha256`, `stored_file_ids`, `authority_snapshot`,
`pair_publication_state`, `stop_reason`, `checker_id`, and
`protected_evidence_pointer`.

Ordered preparation procedure:
1. Capture the accepted request ID/fingerprint, frozen run/proof hashes,
   issuance/version lineage, and empty-or-complete artifact-pair state.
2. Replay only the exact request identity; reject changed reuse.
3. Let the existing database-derived worker retry its due job; do not fabricate
   lease completion or write artifacts outside shared private storage.
4. Require both immutable artifact rows, stored-file rows, exact hashes, and
   current authority before access.
5. On terminal failure, request an explicit append-only reissue and retain the
   failed version plus lineage evidence.

Do not:
Do not enable live issuance flags, invent privacy/method approval, expose one
artifact of a partial pair, overwrite an object, publish a raw route/person
identifier, or claim synthetic output as a real campaign result.

## Domain: incident-escalation

Authoritative sources:
[incident playbooks](../w4-03a-release-operations.md),
[privacy breach register rules](../privacy-operating-model.md), and the owning
database/audit/release/job state for the affected domain.

Authoritative state:
Every suspected confidentiality, integrity, availability, misdirection, or
unauthorized-processing event receives a protected incident/breach record.
The missing privacy/legal decision-maker decides notification with qualified
advice; this pack invents neither that actor nor a deadline.

Roles:
- incident commander: `<INCIDENT_COMMANDER_ROLE>`
- privacy/legal decision-maker: `<PRIVACY_DECISION_ROLE>`
- security responder: `<SECURITY_OWNER_ROLE>`
- money checker: `<MONEY_CHECKER_ROLE>`
- report-method authority: `<REPORT_METHOD_AUTHORITY_ROLE>`
- service coordinator: `<SERVICE_SUPPORT_COORDINATOR_ROLE>`

Stop criteria:
Contain the affected path and escalate when scope/authority is uncertain,
sensitive exposure may continue, money/report finality disagrees, evidence is
missing, a required owner is unnamed, or recovery cannot be proved through the
existing authority. Absence of a named decision-maker never permits silent
closure.

Evidence fields:
`incident_id`, `discovery_time_utc`, `discovery_source`, `first_event_time_utc`,
`last_event_time_utc`, `systems`, `purposes`, `data_classes`, `subject_estimate`,
`regions_processors`, `sanitized_correlation_ids`, `impact`, `containment`,
`decisions`, `decision_actors`, `notifications_considered`,
`notifications_authorized`, `recovery_evidence`, `closure_decision`,
`closure_actor`, `follow_up_owner`, `protected_store_pointer`, and
`redaction_review`.

Ordered preparation procedure:
1. Assign an incident ID, contain the affected path, and preserve immutable
   source pointers before diagnosis changes state.
2. Record discovery/source, systems, purposes, data classes, subject estimate,
   regions/processors, impact, and sanitized correlations.
3. Escalate to the placeholder owners; record decisions and actors without
   inventing legal notification deadlines or approvals.
4. Link recovery evidence produced by the affected domain's existing path.
5. Close only with an authorized closure decision, follow-up owner, protected
   evidence pointer, and redaction review.

Do not:
Do not place people names/contacts, precise GPS, bank or KYC values, secrets,
credentials, private or presigned URLs, raw payloads, fraud evidence, filenames,
object keys, ciphertext, or scanned content in this template.

## Domain: evidence-chain

Authoritative sources:
[DSR evidence rules](../data-subject-request-runbook.md),
[privacy operating model](../privacy-operating-model.md), and each affected
domain's immutable database/audit/release authority.

Authoritative state:
This template is an index of protected evidence pointers. It does not become a
ledger, report, release, audit, DSR, or provider receipt. Exact retries converge;
changed evidence conflicts. Missing required locations or fields block closure.

Roles:
- evidence recorder: `<EVIDENCE_RECORDER_ROLE>`
- independent checker: `<EVIDENCE_CHECKER_ROLE>`
- retention/privacy authority: `<PRIVACY_DECISION_ROLE>`

Stop criteria:
Stop evidence capture/closure when classification is not synthetic, a source
cannot be resolved, timestamps or hashes are missing, before/after facts do not
conserve, required stores are not assessed, sensitive material is embedded
instead of referenced, or recorder/checker separation is absent.

Evidence fields:
`evidence_id`, `scenario_id`, `domain`, `classification`, `captured_at_utc`,
`source_authority`, `source_revision`, `command_or_entry_point`, `exit_code`,
`expected_result`, `observed_result`, `before_sha256`, `after_sha256`,
`correlation_ids`, `stop_decision`, `incident_id`, `external_gate_snapshot`,
`recorder_id`, `checker_id`, `protected_store_pointer`, `retention_authority`,
`redaction_review`, and `closure_state`.

Ordered preparation procedure:
1. Create an evidence ID before the exercise and bind it to scenario/domain,
   source revision, exact command/test node, and gate snapshot.
2. Record exit code, expected/observed result, sanitized correlation IDs, and
   before/after hashes or immutable row pointers.
3. Store protected material outside Git; put only the non-sensitive pointer in
   the template.
4. Have a distinct checker verify completeness, conservation, classification,
   and redaction.
5. Leave closure blocked while any required field/store/owner/authority is
   missing; changed retries become a conflict record, never overwritten facts.

Do not:
Do not paste identity evidence, raw logs/payloads, credentials, bank/KYC data,
precise GPS, private URLs, object keys, or generated report contents into Git;
do not edit immutable history to make the chain agree.

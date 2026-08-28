# W4-03C-P1 deterministic synthetic exercise matrix

Run from the repository root with the repository Python environment active.
These exact nodes use local fixtures/in-process adapters only. They require no
provider credentials or external network. Each result is repository regression
evidence, not a deployment, rehearsal, user acceptance, real observation, or
controlled-pilot receipt.

## Domain: telemetry-readiness

Authoritative source/state: readiness response and worker/database state via
[runbook](../runbook.md) and [release observability](../w4-03a-release-operations.md).

Happy command:

```sh
python3 -m pytest -q tests/test_health.py::test_api_ready_without_database_url_is_deterministic
```

Expected evidence: the local readiness response is deterministic and explicitly
labels the database as not configured.

Stop/failure command:

```sh
python3 -m pytest -q tests/test_worker_jobs.py::test_sweep_isolates_per_trip_failures_and_continues
```

Expected evidence: one failed job stays visible while independent work continues;
the failure is not converted to success.

## Domain: rollback-recovery

Authoritative source/state: protected release/compatibility/traffic state in
[release recovery](../w4-03a-release-operations.md). No release/recovery shell
script is executed by these tests.

Happy command:

```sh
python3 -m pytest -q tests/test_w403a_release_preparation.py::test_compatibility_evidence_binds_previous_image_and_forward_schema
```

Expected evidence: compatibility proof binds the previous image to the exact
forward schema before recovery is considered.

Stop/failure command:

```sh
python3 -m pytest -q tests/test_w403a_release_preparation.py::test_failure_cleanup_stops_an_open_edge tests/test_w403a_release_preparation.py::test_release_scripts_never_run_alembic_downgrade
```

Expected evidence: a failed stage closes traffic and the operational scripts
contain no schema-downgrade path.

## Domain: payout-replay

Authoritative source/state: persisted batch/line/instruction/ledger and
reconciliation-event rows exercised with the in-process fake adapter.

Happy command:

```sh
python3 -m pytest -q tests/test_payout_reconciliation.py::test_line_level_partial_reconciliation_retry_and_paid_finality
```

Expected evidence: an identical failed-line retry preserves identity, reconciles
line by line, and reaches paid finality only after verified success; external
provider actions remain zero.

Stop/failure command:

```sh
python3 -m pytest -q tests/test_payout_batches.py::test_submission_fails_closed_without_approved_provider
```

Expected evidence: submission is refused without approved provider authority;
no financially effective action occurs.

## Domain: report-replay

Authoritative source/state: frozen request/fingerprint/run/version and immutable
issuance/artifact/stored-file rows under the
[bounded issuance contract](../pkg-08-w4-02b-bounded-issuance.md).

Happy command:

```sh
python3 -m pytest -q tests/test_report_issuances.py::test_lost_response_replay_does_not_recompose_mutable_latest_projection
```

Expected evidence: identical request replay converges on the frozen issuance and
changed reuse conflicts.

Stop/failure command:

```sh
python3 -m pytest -q tests/test_report_issuances.py::test_partial_storage_failure_exposes_no_artifact_and_retry_recovers_pair
```

Expected evidence: a partial CSV/PDF write exposes neither artifact; the same
database-derived job retry publishes only a verified complete pair.

## Domain: incident-escalation

Authoritative source/state: privacy register and operating-model gates in the
[privacy operating model](../privacy-operating-model.md).

Happy command:

```sh
python3 -m pytest -q tests/test_privacy_operating_model.py::test_privacy_register_is_fail_closed_and_complete
```

Expected evidence: the synthetic register contains the required incident/privacy
categories and remains fail closed.

Stop/failure command:

```sh
python3 -m pytest -q tests/test_privacy_operating_model.py::test_provider_notice_breach_and_dpia_registers_do_not_claim_approval
```

Expected evidence: missing provider/legal approval and open residual risk cannot
be represented as approved or closed.

## Domain: evidence-chain

Authoritative source/state: immutable request/location assessments and protected
store pointers under the [DSR runbook](../data-subject-request-runbook.md).

Happy command:

```sh
python3 -m pytest -q tests/test_data_subject_requests.py::test_admin_access_request_inventories_and_closes_all_locations
```

Expected evidence: a local synthetic request inventories and accounts for every
required store through explicit evidence pointers.

Stop/failure command:

```sh
python3 -m pytest -q tests/test_data_subject_requests.py::test_completion_requires_every_store
```

Expected evidence: closure is rejected while any required store lacks evidence.

---
source_surface: ChatGPT
project: TSS
conversation_id: 6a969279-48a8-83ea-8b2f-e2cceef24a75
displayed_title: Audit Database Concurrency
displayed_model: GPT-5.6 Pro
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete owner-supplied response
redactions: none
audited_ref: 637841d95493bcc24334356da42097fa53a5d16f
---

# Audit Database Concurrency

> Complete response supplied directly by the project owner on 1 September 2026. It is source evidence, not an accepted finding or remediation decision.

# Verdict

**FAIL for production payout execution and unrestricted production rollback at commit `637841d95493bcc24334356da42097fa53a5d16f`.**

The immutable commit was verified directly and was not substituted with `master`.

The database design is substantially stronger than a typical build-stage system: there are real PostgreSQL-specific migration tests, stable advisory-lock derivation, partial unique indexes, row-lock ordering, immutable authority tables, worker leases, and a carefully recoverable partition-retention protocol. However, four issues prevent an unconditional production approval:

1. **Payout submission has an unavoidable ambiguous-success window:** the external provider is called while database locks and the transaction remain open, and the local provider receipt is written only afterward.
2. **Several historical downgrades can destroy financial, privacy, or finality evidence.**
3. **The repository knowingly quarantines model/migration drift affecting eleven indexes and two unique constraints.**
4. **Some reusable services issue a full session rollback while translating expected uniqueness races, potentially discarding unrelated caller work.**

A non-money pilot is conditionally supportable only if the disbursement adapter remains disabled, migrations are operated as forward-only, and the focused PostgreSQL/PostGIS checks below are passed against the exact artifact. No PostgreSQL execution or full-suite result is claimed in this audit.

---

# Migration-chain risk summary

The exact tree contains a linear Alembic chain from `0001_enable_extensions` through `0071_report_issuances`. Alembic uses the shared ORM metadata and wraps online migrations transactionally; ordinary service tests, however, generally create current metadata in SQLite rather than replaying the migration chain. PostgreSQL/PostGIS fixtures and selected migration tests exist, but require a configured database. `app/alembic/env.py:1-120`, `tests/conftest.py:1-300`, `.github/workflows/ci.yml:1-320`.

|  # | Area                                      | Assessment                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| -: | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
|  1 | Clean base-to-head upgrade                | **Designed but unproved for this SHA.** `test_migration_0014_partitioning.py` creates a disposable PostgreSQL database and runs the real chain to `head`; the E2E workflow also declares `alembic upgrade head`. Those sources are good evidence of intent, not an execution result for this review. `tests/test_migration_0014_partitioning.py:1-190`.                                                                                                                                |
|  2 | Upgrade/downgrade/re-upgrade              | **Partial.** Empty down/up cycles are tested around revisions 0014, 0018, and 0071, but there is no safe whole-chain rollback contract for populated production data. `tests/test_migration_0071_report_issuances.py:1-160`, `tests/test_migration_payout_downgrade_guards.py:1-190`.                                                                                                                                                                                                  |
|  3 | Data-preserving backfills                 | **Generally careful, with one semantic assumption.** Revision 0014 uses rename-and-attach and has a seeded row/FK preservation test. Revision 0016 converts every pre-protocol `ended` trip to `sealed`, assuming those trips were already economically processed. That assumption needs production-data verification. `alembic/versions/0014_location_pings_partitioning.py:1-250`, `alembic/versions/0016_trip_seal_protocol.py:1-90`.                                               |
|  4 | Model/migration drift                     | **Confirmed failure.** The head drift test explicitly quarantines eleven migration-only indexes and two migration-only unique constraints rather than making the metadata clean. `tests/test_migration_0014_partitioning.py:500-580`.                                                                                                                                                                                                                                                  |
|  5 | Defaults and nullable transitions         | **Static shape is mostly sound, but verification is incomplete.** For example, 0038 backfills source columns with `manual` defaults before allowing nullable actors, and 0071 makes generated report files nullable only with an XOR check. However, drift comparisons deliberately disable type and server-default comparison. `alembic/versions/0038_payment_gateway_events.py:30-140`, `tests/test_migration_0071_report_issuances.py:130-180`.                                     |
|  6 | Append-only trigger coverage              | **Partial.** Payment events, financial-authority records, report issuances and artifacts have PostgreSQL immutability triggers. `data_purge_audit` is called append-only but its creation and current model contain checks/indexes without an update/delete trigger. `alembic/versions/0014_location_pings_partitioning.py:230-320`, `app/models/data_purge.py:1-120`, `alembic/versions/0038_payment_gateway_events.py:130-220`, `alembic/versions/0071_report_issuances.py:160-280`. |
|  7 | Constraint names used by translation      | **Reviewed names align, but driver-level proof is incomplete.** The translator only recognizes a fixed whitelist and rejects unrelated FK/check failures. Its unit tests use synthetic exception objects; several real PostgreSQL race tests indirectly exercise named conflicts. `app/db/integrity.py:1-150`, `tests/test_integrity.py:1-100`.                                                                                                                                        |
|  8 | Advisory-lock stability                   | **Pass statically.** Reviewed locks derive signed 64-bit keys from SHA-256, not Python’s process-random `hash()`. `app/services/payout_rule_serialization.py:1-25`, `app/services/report_issuances.py:190-215`.                                                                                                                                                                                                                                                                        |
|  9 | Lock ordering and deadlocks               | **No static cycle confirmed.** Campaign, assignment, profile, vehicle, receipt and ledger paths show deliberate ordering and sorted multi-row acquisition. PostgreSQL overlap tests cover several important pairs. The payout provider call nevertheless holds locks for an uncontrolled network duration. `app/services/trips.py:160-320`, `tests/test_billing_concurrency.py:1-220`.                                                                                                 |
| 10 | Read-check-write races                    | **Mostly database-backed.** Active-trip, payout reservation, report lineage, payment event and invoice-number races are protected by partial uniqueness, row locks or advisory locks. The primary weakness is full-session rollback during some expected-conflict translations.                                                                                                                                                                                                        |
| 11 | Same-key convergence                      | **Pass for gateway events and report objects; unproved for live disbursement.** Gateway events compare immutable payloads, and report storage uses deterministic keys plus checksum/`If-None-Match` semantics. Payout retries call the provider again with the same key, leaving final convergence to an external contract.                                                                                                                                                            |
| 12 | Changed-payload conflicts                 | **Pass internally, unproved externally.** Payment gateway and report creation paths reject identity reuse with changed evidence. The disbursement protocol does not itself guarantee that a live provider rejects the same idempotency key with a different instruction fingerprint.                                                                                                                                                                                                   |
| 13 | Provider calls inside transactions        | **Confirmed failure.** `submit_payout_batch` locks the batch and its lines, calls `adapter.submit_batch`, and only then records the provider result. `app/services/disbursements.py:380-570`.                                                                                                                                                                                                                                                                                          |
| 14 | Crash between provider effect and receipt | **Confirmed exposure.** A successful provider transfer followed by process death, timeout, cancellation, connection loss or commit failure leaves no durable local submission receipt.                                                                                                                                                                                                                                                                                                 |
| 15 | Partial migration recovery                | **Generally transactional, but operationally unproved.** Revision 0014 explicitly runs as one blocking transaction with fast lock timeout and a ten-minute statement timeout. An aborted transaction should roll back, but production-sized lock, WAL, disk and replica effects have not been demonstrated. `alembic/versions/0014_location_pings_partitioning.py:1-190`.                                                                                                              |
| 16 | Partition detach/finalize recovery        | **Strong.** The lifecycle service persists pre-destruction evidence, supports evidence-gated pending-detach recovery, refuses conflicting or no-longer-expired detaches, and writes final drop evidence transactionally. PostgreSQL tests cover those paths. `app/services/data_lifecycle.py:420-900`, `tests/test_data_lifecycle_jobs.py:300-780`.                                                                                                                                    |
| 17 | SQLite masking PostgreSQL behaviour       | **Material risk.** Most ordinary tests build current metadata in SQLite. PostgreSQL-only triggers, `SKIP LOCKED`, advisory locks, partial-index conflict diagnostics, partitioning, JSONB and PostGIS are therefore exercised only by explicitly configured fixtures.                                                                                                                                                                                                                  |
| 18 | Realistic-table-size migration risk       | **High for 0014; moderate for 0016.** Revision 0014 deliberately takes a blocking lock and validates historical bounds; its downgrade performs a full table copy. Revision 0016 performs a potentially broad `ended`-trip update. Existing tests use small fixtures.                                                                                                                                                                                                                   |
| 19 | Contract/schema drift                     | **Confirmed internally and unproved externally.** ORM metadata omits known database objects, while the live disbursement provider’s idempotency/reconciliation contract is not represented as an enforceable local state machine.                                                                                                                                                                                                                                                      |
| 20 | Rollback destroying evidence              | **Confirmed failure.** Revisions 0010, 0014 and 0016 have downgrade paths that can drop or erase economic, purge, quarantine or trip-finality evidence. Later revisions are substantially better and commonly block populated downgrades.                                                                                                                                                                                                                                              |

## Known metadata drift

The explicit quarantine contains:

* Indexes: `ix_campaign_creatives_campaign_status`, `ix_campaign_creatives_creative_type`, `ix_campaign_zones_campaign_zone_type`, `ix_campaign_zones_geom`, `ix_campaigns_organization_status`, `ix_campaigns_start_end`, `ix_driver_profiles_country_city`, `ix_driver_profiles_onboarding_status`, `ix_driver_profiles_user_id`, `ix_vehicles_plate_country_normalized`, and `ix_vehicles_status`.
* Unique constraints: `uq_driver_profiles_user_id` and `uq_users_email`.

This does not mean those protections are absent from the live migrated schema. It means the ORM and migration authorities disagree, so an unreviewed autogenerate can propose removing real production indexes or uniqueness protection. `tests/test_migration_0014_partitioning.py:500-580`.

---

# Confirmed race and recovery defects

## DB-01 — Provider success can outlive a rolled-back payout transaction

**Severity: Critical / release blocker for live disbursement**

`submit_payout_batch` holds a `FOR UPDATE` lock on the batch and lines, invokes `adapter.submit_batch`, and only afterward assigns the provider submission reference, changes status to submitted and records the audit event. `app/services/disbursements.py:380-570`.

### Transaction timeline

| Time | Database                                                                | Provider                                                                  |
| ---- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| T1   | Transaction begins; payout batch row is locked.                         | No effect.                                                                |
| T2   | Batch lines are locked and frozen instructions are revalidated.         | No effect.                                                                |
| T3   | Transaction remains uncommitted.                                        | `submit_batch` is called.                                                 |
| T4   | No local provider receipt yet exists.                                   | Provider accepts one or more transfers.                                   |
| T5   | Process dies, request is cancelled, connection fails, or commit aborts. | Transfer remains externally effective.                                    |
| T6   | Database transaction rolls back to `reserved`.                          | Provider effect cannot be rolled back.                                    |
| T7   | Retry calls the provider again using the same key.                      | Safety depends entirely on provider-side durability and lookup semantics. |

The adapter protocol carries idempotency keys but does not establish an enforceable requirement that:

* same key plus same fingerprint always returns the original result;
* same key plus changed fingerprint always hard-fails;
* an ambiguous request can be looked up by key before resubmission;
* the provider retains idempotency state for at least Cardvert’s legal and operational retry horizon.

`app/adapters/disbursement/provider.py:1-260`.

The current test deliberately submits the fake adapter twice and observes two calls with the same frozen keys. That proves local retry stability, but not exactly-once provider effect. No test kills the process after provider acceptance and before database commit. `tests/test_payout_batches.py:1-130`.

### Consequence

A duplicate transfer is possible unless the eventual production provider independently supplies durable idempotency and query-by-key reconciliation. Conversely, automatically marking the batch submitted after an ambiguous timeout could produce a missed transfer. The system currently cannot distinguish those two outcomes from local data alone.

---

## DB-02 — Expected race translation can roll back unrelated caller work

**Severity: High**

The reviewed payout reservation/submission and trip-start paths call `session.rollback()` after certain expected uniqueness failures. For example, trip creation catches an active-trip index race, rolls back the entire session, and then returns the stable domain conflict. `app/services/trips.py:250-330`.

### Transaction timeline

1. The caller writes or updates object **A** in the supplied session.
2. The caller invokes the service.
3. The service inserts object **B** and loses an expected uniqueness race.
4. The service calls `session.rollback()`.
5. Both **B** and unrelated object **A** are rolled back.
6. The caller receives only the expected domain-level `409`, which does not reveal that preceding work was discarded.

This is particularly risky because these functions accept a caller-provided `AsyncSession`; their signatures do not establish exclusive transaction ownership. The billing paths demonstrate the safer pattern: wrap the race-prone insert in `session.begin_nested()`, then re-read the winning row after savepoint rollback. `app/services/billing.py:500-700`, `app/services/billing.py:2180-2390`.

---

## DB-03 — Historical downgrades can destroy governed evidence

**Severity: Critical operational defect**

### Revision 0010

The downgrade unconditionally drops `earnings_ledger_entries`, `payout_calculations`, and `campaign_payout_rules`. It has no populated-data refusal. `alembic/versions/0010_payouts_and_earnings.py:430-510`.

A downgrade can therefore erase:

* driver economic entries;
* calculated payment authority;
* the rule source used for those calculations.

Later payout migrations have substantially better populated downgrade guards, but those do not make revision 0010 safe when only the older tables contain data. `tests/test_migration_payout_downgrade_guards.py:1-190`.

### Revision 0014

The migration itself documents that downgrade drops `data_purge_audit`, cannot recreate already purged partitions, and performs a full table rewrite. The code then unconditionally drops the audit table before rebuilding `location_pings`. `alembic/versions/0014_location_pings_partitioning.py:1-35,270-350`.

### Revision 0016

The downgrade:

* drops `quarantined_ping_batches`;
* maps all `sealed` trips back to `ended`;
* removes seal reason/time and client watermark fields;
* contracts the purge-event check again.

There is no populated-data refusal. `alembic/versions/0016_trip_seal_protocol.py:130-225`.

That can destroy raw-location quarantine evidence and the finality state used to decide when the money chain may run.

---

## DB-04 — Purge evidence is described as append-only but not database-protected

**Severity: High**

Revision 0014 calls `data_purge_audit` an append-only compliance artifact, but creates only checks and indexes. The current ORM model likewise has no before-update or before-delete guard. Revision 0016 only widens its event constraints. `alembic/versions/0014_location_pings_partitioning.py:230-320`, `app/models/data_purge.py:1-120`, `alembic/versions/0016_trip_seal_protocol.py:120-170`.

The lifecycle service itself only appends, but direct SQL, an administrative script or a future ORM path could update or delete evidence without the database rejecting it. A PostgreSQL catalog check is still required to exclude an indirect trigger added by another revision, but no such protection exists in the creation, extension or current-model paths reviewed here.

---

# Confirmed recovery strengths

## Partition detach and destruction state machine

No defect was found in the reviewed detach/finalize sequence.

The service:

1. acquires a stable retention advisory lock;
2. records `purge_started` and commits it before destructive DDL;
3. performs concurrent detach;
4. detects and finalizes a previously interrupted detach only when the evidence is valid and the partition remains expired;
5. refuses pending detaches when evidence conflicts or the retention window was widened;
6. records `dropped` in the same transaction as `DROP TABLE`;
7. blocks all other destruction when an unsafe pending state exists.

`app/services/data_lifecycle.py:420-900`.

Focused PostgreSQL tests cover evidence-before-destruction, rerun idempotency, interrupted-detach recovery, conflicting dropped evidence, changed-retention refusal, and lock release after failure. `tests/test_data_lifecycle_jobs.py:300-780`.

## Billing and inbound payment convergence

The inbound gateway path is materially safer than outbound disbursement:

* signed provider evidence is verified before persistence;
* event identity is unique by provider plus provider event ID;
* an identical replay returns the existing event;
* changed evidence under the same identity returns a conflict;
* processing locks the event;
* completed processing converges to one receipt, reconciliation, allocation and completed attempt.

`app/services/billing.py:2180-2690`, `alembic/versions/0038_payment_gateway_events.py:20-220`.

The focused PostgreSQL test runs two gateway workers concurrently and expects exactly one receipt, one allocation and one attempt. `tests/test_payment_gateway.py:180-300`.

## Report object convergence

Report publication also avoids overwriting existing objects. The S3 implementation:

* calculates the content checksum locally;
* returns an existing object only if key, content type, byte length and checksum all match;
* uses `IfNoneMatch="*"` when creating;
* treats an existing different object as a conflict;
* re-reads and validates the object after a conditional-write race.

`app/adapters/storage/s3.py:90-195`.

A crash after object upload but before artifact-row commit can leave an unreferenced object, but an identical retry should converge instead of overwriting or duplicating the canonical object. The remaining requirement is an orphan-reconciliation policy.

---

# Checks requiring PostgreSQL/PostGIS

These claims must not be closed from SQLite or static inspection.

## 1. Exact-revision migration execution

Against a disposable PostgreSQL 16/PostGIS database built from the exact artifact:

```bash
alembic upgrade head
alembic current
alembic heads
```

Verify:

* one head: `0071_report_issuances`;
* all required extensions exist;
* no migration warning or uncommitted DDL remains;
* repeated `alembic upgrade head` is a no-op.

Run only the focused migration tests:

```bash
pytest -q \
  tests/test_migration_0014_partitioning.py \
  tests/test_migration_0071_report_issuances.py \
  tests/test_migration_payout_downgrade_guards.py
```

## 2. Full catalog drift, including types and defaults

The committed comparison tests disable `compare_type` and `compare_server_default`. Run an additional head comparison with both enabled and inspect every difference.

Verify at minimum:

* column types and precision;
* server defaults;
* nullability;
* check and FK definitions;
* partial-index predicates;
* expression and PostGIS indexes;
* trigger names and trigger functions;
* generated/default UUID behaviour.

The thirteen known metadata differences must be eliminated or accepted through one explicit, reviewed source-of-truth policy rather than a growing test quarantine.

## 3. Raw-SQL immutability probes

On a disposable database, attempt direct `UPDATE` and `DELETE` against every governed table, bypassing ORM listeners.

Expected failures should be proved for:

* payment gateway events and attempts;
* financial authorizations and allocations;
* report issuances and artifacts;
* immutable stored report files;
* commercial terms and invoice authority;
* payout rule revisions and frozen assignment bindings;
* purge evidence.

The last item is expected to fail today because the reviewed purge-audit paths do not install a rejection trigger.

For `earnings_ledger_entries`, verify that database-level policy allows only required status/release transitions while rejecting changes to economic identity: amount, currency, entry type, payout source, trip/campaign/driver provenance and occurrence time.

## 4. Real asyncpg constraint diagnostics

Cause each translated uniqueness conflict through the real asyncpg/SQLAlchemy stack and verify that the exposed constraint name equals the names in `EXPECTED_UNIQUE_CONSTRAINTS`.

This is especially important for:

* active driver trip;
* active vehicle trip;
* payout calculation convergence;
* active payout-line reservation;
* nonterminal fraud flag;
* installation evidence idempotency.

The current pure unit test proves parser logic, not every deployed driver exception shape.

## 5. Focused race and deadlock run

Run only the PostgreSQL concurrency tests:

```bash
pytest -q \
  tests/test_payout_batches.py \
  tests/test_payment_gateway.py::test_concurrent_gateway_workers_create_one_receipt_and_allocation \
  tests/test_billing_concurrency.py \
  tests/test_data_lifecycle_jobs.py
```

Add concurrent scenarios for:

* trip start versus assignment terminal transition;
* payout reservation versus fraud hold creation;
* receipt allocation versus reversal;
* prepaid authorization versus receipt reversal;
* report initial issuance versus reissue;
* correction execution versus payout release;
* retention versus partition premake.

Set a short test `deadlock_timeout`, retain PostgreSQL deadlock logs, and inspect `pg_locks` rather than treating a client timeout as proof of correct serialization.

## 6. Disbursement crash injection

A provider simulator must support durable state independent of the application process. Exercise these exact cut points:

1. immediately before provider call;
2. provider accepted, before response reaches Cardvert;
3. response returned, before local flush;
4. local flush completed, before commit;
5. commit response lost;
6. worker restarts and retries.

Required outcomes:

* same key plus same fingerprint produces one provider effect and one stable provider reference;
* same key plus different fingerprint produces a hard conflict;
* an ambiguous timeout is resolved by provider lookup before resubmission;
* no batch is marked submitted without durable evidence;
* no provider success remains permanently undiscoverable.

## 7. Realistic-volume migration rehearsal

Use an anonymized production-sized clone or generated data at the expected 12–18 month volume.

For revision 0014 measure:

* time waiting for the initial lock;
* duration of bound validation;
* peak WAL;
* temporary and final disk use;
* replica lag;
* transaction age;
* application writer interruption;
* rollback time after forced statement timeout.

For revision 0016 measure the row count and WAL generated by the `ended` to `sealed` backfill.

## 8. Partition recovery cut points

On PostgreSQL/PostGIS, terminate the lifecycle worker after:

* `purge_started` commit;
* detach command issued;
* detach pending;
* detach finalized;
* immediately before table drop;
* immediately after table drop but before client acknowledgement.

On restart, prove one final state, no duplicate `dropped` evidence, no unsafe quarantine purge, and no attached partition left outside the retention authority.

---

# Data-loss or duplication exposure

| Exposure                                   | Current risk              | Mechanism                                                                                                                                               |
| ------------------------------------------ | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Duplicate driver transfer                  | **Critical**              | Provider succeeds, local transaction rolls back, retry submits again.                                                                                   |
| Missed driver transfer                     | **Critical**              | An ambiguous provider timeout is treated as failure and never reconciled, or a batch is manually advanced without provider proof.                       |
| Long-held payout locks                     | **High**                  | Network call occurs while batch and line rows remain locked. Slow provider behaviour increases contention and transaction-failure probability.          |
| Loss of economic evidence                  | **Critical on downgrade** | Revision 0010 can drop ledger, calculations and payout rules.                                                                                           |
| Loss of privacy evidence                   | **Critical on downgrade** | Revision 0014 drops `data_purge_audit`; revision 0016 drops quarantined payload evidence.                                                               |
| Loss of trip finality                      | **High on downgrade**     | Revision 0016 converts `sealed` to `ended` and removes seal fields.                                                                                     |
| Silent purge-evidence alteration           | **High**                  | No reviewed DB trigger prevents update/delete of `data_purge_audit`.                                                                                    |
| Unrelated work rolled back                 | **High**                  | Service-level full `session.rollback()` after an expected uniqueness race.                                                                              |
| Destructive autogenerate                   | **High**                  | ORM metadata does not declare thirteen live migration-owned objects.                                                                                    |
| Unreferenced report objects                | **Moderate**              | Storage write succeeds before artifact-row commit. Deterministic keys prevent normal duplicate canonical objects, but orphan cleanup is still required. |
| Migration outage                           | **High at scale**         | Revision 0014 is intentionally blocking and holds its lock to transaction commit.                                                                       |
| Partition-row loss during normal retention | **No defect confirmed**   | Evidence-gated detach/finalize/drop implementation and focused tests are strong.                                                                        |

---

# Smallest remediation

## 1. Introduce a durable payout submission attempt/outbox

Do not redesign the complete payout domain. Add one durable state machine around the existing frozen batch:

1. In a short database transaction, create an immutable `payout_submission_attempt` containing:

   * batch ID;
   * attempt number;
   * provider name;
   * complete instruction-set fingerprint;
   * each provider idempotency key;
   * status `pending`;
   * created timestamp.
2. Commit before contacting the provider.
3. A worker claims the attempt using `FOR UPDATE SKIP LOCKED` plus a lease/token.
4. Call the provider outside the business transaction.
5. In a new short transaction, persist:

   * provider reference;
   * immutable response fingerprint/evidence;
   * outcome;
   * submission timestamp;
   * final batch transition using compare-and-set.
6. After any ambiguous exception, query the provider by key before another submit.
7. Never permit a new attempt with the same key and a different frozen fingerprint.

Keep the current batch and line freezing; replace only the unsafe dispatch boundary.

## 2. Make evidence-bearing downgrades fail closed

Add populated-data guards, or unconditionally refuse downgrade, for:

* `0010_payouts_and_earnings`;
* `0014_location_pings_partitioning`;
* `0016_trip_seal_protocol`.

Minimum guard conditions:

* 0010: any payout rule, calculation or ledger entry;
* 0014: any purge-audit row, any detached/purged partition history, or any partition state that cannot be reconstructed losslessly;
* 0016: any sealed trip, quarantined batch, or downstream calculation tied to sealed finality.

Operationally designate those revisions as **forward-only once populated**.

## 3. Close the thirteen metadata differences

Declare the existing indexes and unique constraints in ORM metadata with their exact names and predicates. Then remove the quarantine from `test_migration_0014_partitioning.py` and require a clean head comparison.

Also turn on type and server-default comparison in a dedicated PostgreSQL drift gate.

## 4. Protect purge evidence at the database layer

Install a PostgreSQL trigger that rejects `UPDATE` and `DELETE` on `data_purge_audit`. Add a populated downgrade refusal and a raw-SQL trigger test.

## 5. Replace service-wide rollback with savepoints

For race-prone inserts:

```python
try:
    async with session.begin_nested():
        session.add(candidate)
        await session.flush()
except IntegrityError as exc:
    # Re-read winner and translate only the expected named constraint.
    ...
```

Do not call `session.rollback()` inside a reusable service unless the function explicitly owns the entire transaction and its interface says so.

## 6. Make the provider contract executable

The production adapter acceptance gate must include contract tests for:

* idempotency retention duration;
* same-key/same-payload convergence;
* same-key/changed-payload rejection;
* query by idempotency key;
* immutable provider reference;
* status polling;
* ambiguous timeout recovery;
* webhook or reconciliation authenticity.

Configuration should remain fail-closed until those tests and provider evidence pass.

---

# Operational migration precautions

## Before deployment

1. Pin the application image, migration code and runbook to commit `637841d95493bcc24334356da42097fa53a5d16f`; verify the SHA from inside the deployed artifact.
2. Confirm exactly one Alembic head and record the current `alembic_version`.
3. Take a PostgreSQL backup suitable for point-in-time recovery and prove restoration into an isolated environment.
4. Capture pre-migration counts and checksums for:

   * `location_pings`;
   * `location_ping_batches`;
   * trips by status;
   * payout calculations;
   * ledger entries;
   * purge evidence;
   * quarantined batches.
5. Confirm sufficient free disk and WAL capacity, replication health, and no long-running transactions touching migration tables.
6. Rehearse the exact migration on a production-sized clone.
7. Keep the payout provider adapter disabled until DB-01 is closed and provider behaviour is certified.

## During revision 0014 or similarly blocking DDL

1. Use a maintenance window and stop location-ping writers.
2. Preserve the migration’s fail-fast lock timeout; do not repeatedly retry while long transactions remain active.
3. Monitor:

   * `pg_stat_activity`;
   * `pg_locks`;
   * transaction age;
   * WAL rate;
   * disk;
   * replica lag;
   * blocked application sessions.
4. Do not terminate the migration after it has acquired locks unless the rollback duration and storage headroom are understood.
5. Do not run concurrent retention or partition-premake jobs during schema conversion.

## After migration

Verify before reopening writes:

* migrated row count equals the pre-migration count;
* no orphaned batch or trip foreign keys;
* expected partition bounds are continuous and non-overlapping;
* there is no default partition;
* the composite location-ping primary key is present;
* all expected PostGIS and secondary indexes exist and are valid;
* all required checks, FKs and triggers exist;
* writes at current and next-month boundaries route to the expected partition;
* Alembic reports the exact head;
* focused application smoke transactions commit under PostgreSQL.

## Rollback policy

Do not treat `alembic downgrade` as the primary production rollback mechanism after governed data exists. Roll application code forward or deploy a corrective migration. Any exceptional schema rollback must first prove that its target revision preserves every financial, privacy, audit, receipt, quarantine and finality artifact.

## Ambiguous payout operations

Do not retry a timed-out payout based only on local batch status. Freeze the batch, query the provider by idempotency key or provider reference, reconcile the result, and only then decide whether submission is safe. Until that capability exists, an ambiguous payout attempt requires manual financial reconciliation rather than automatic resubmission.

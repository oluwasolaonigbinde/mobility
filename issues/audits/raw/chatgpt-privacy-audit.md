---
source_surface: ChatGPT
project: TSS
conversation_id: 6a967dcf-177c-83ea-8592-a923fd93b507
displayed_title: Privacy Audit Verification
displayed_model: GPT-5.6 Pro
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete owner-supplied response
redactions: none
audited_ref: 637841d95493bcc24334356da42097fa53a5d16f
---

# Privacy Audit Verification

> Complete response supplied directly by the project owner on 1 September 2026. It is source evidence, not an accepted finding or remediation decision.

# Verdict

**FAIL — release-blocking privacy defects are present at commit `637841d95493bcc24334356da42097fa53a5d16f`.**

The branch `feat/pkg-04-build-first` resolved to the requested SHA before review. Repository access was read-only and every source read was pinned to that immutable commit.

I could not create the requested local isolated checkout because this execution environment could not resolve GitHub for `git clone`. Consequently, this is a **SHA-pinned static audit**: focused test source was reviewed, but no tests were executed. No repository state was changed.

The implementation contains substantial privacy engineering—especially encrypted KYC/payee data, tenant scoping, heatmap suppression, partition-retention recovery, parent-staleness checks and default-deny advertiser outputs—but the controls are not consistently centralized or truthful:

* Real GPS and plaintext KYC can enter the system without the documented legal/privacy live-use gate.
* Advertiser trip reporting is row-level and contradicts the declared aggregate/no-trip-ID boundary.
* Audience materialization/export enforces only one of the configured disclosure controls.
* DSR inventory is incomplete and an erasure case can be completed with externally reported records still remaining.
* Object deletion happens before durable destruction evidence.

The repository’s own operating model says no real GPS, live KYC, advertiser reporting or retargeting may proceed while `EXT-LEGAL-PRIVACY` is missing. That is documented at `docs/privacy-operating-model.md:3-29`, but only the advertiser-output and retargeting paths substantially enforce it.

---

# Sensitive-data flow map

## 1. Precise location

```text
Driver client
  → POST /driver/trips/start
  → POST /driver/trips/{trip_id}/pings
  → canonical payload containing lat/lon
  → trip ownership, timing, assignment and idempotency checks
  → location_ping_batches
  → location_pings(latitude, longitude, geom, accuracy, speed, metadata)
  ├─→ route analytics / fraud / payout processing
  ├─→ grandfathered heatmap aggregation
  └─→ partition retention and quarantine retention
```

Evidence:

* The driver routes call trip start and ping ingestion directly, with no privacy/legal-live dependency: `app/api/v1/trips.py:62-145`.
* The canonical payload includes latitude and longitude: `app/services/trips.py:516-538`.
* Exact coordinates and PostGIS geometry are persisted: `app/services/trips.py:604-730`.
* Driver read responses expose trip identifiers, counts and timestamps but not coordinate rows: `app/api/v1/trips.py:40-60`, `app/schemas/trips.py:10-125`.

I found no current staff or advertiser API serializing raw ping coordinates. The principal defect is **unauthorized live collection**, not a confirmed direct raw-coordinate read leak.

## 2. KYC and financial identifiers

```text
Driver client supplies plaintext NIN
  → KYC route
  → driver/file/bank ownership checks
  → AES-256-GCM envelope with tenant/record/field AAD
  → driver_kyc_submissions(encrypted_nin, key version, last four)
  → private managed-file references
  → masked normal responses
  → purpose-gated administrative reveal

Driver/payee bank details
  → payee service
  → equivalent envelope encryption
  → masked account metadata
  → purpose-gated reveal and audit
```

Evidence:

* The route extracts plaintext NIN and calls the service without a live-use gate: `app/api/v1/kyc.py:80-107`.
* The service validates the NIN, files and bank relationship, then encrypts it: `app/services/kyc.py:199-340`.
* The migration requires encrypted NIN, AES-256-GCM and a positive key version: `alembic/versions/0055_kyc_key_custody.py:52-127`.
* The common cryptographic boundary uses authenticated encryption and associated data: `app/adapters/crypto/envelope.py:1-420`.
* The audit event records only version and key version, not NIN: `app/services/kyc.py:322-340`.

The storage encryption is sound at the code level. The missing control is the documented authorization **before collection**.

## 3. Advertiser analytics

```text
Advertiser request
  → disclosure live/config/reference gate
  → active membership and organization selection
  → tenant-scoped campaign lookup
  ├─→ heatmap: vehicle/trip/day floors + contributor cap + query history
  ├─→ campaign summaries/daily metrics
  └─→ campaign trips: one row per trip with stable identifiers
```

The gate is correctly placed before membership and data reads at `app/services/disclosure.py:48-111`. Statistical disclosure enforcement is not consistently applied after that gate.

## 4. Audience and retargeting

```text
Immutable measurement run + source link + worker-supplied cells
  → privacy live gate
  → tenant/campaign/link/run and parent-integrity checks
  → cell filtering by distinct-vehicle count only
  → immutable exposure segment and cells
  ├─→ advertiser recommendations
  ├─→ advertiser CSV export
  └─→ admin activation adapter
       └─ currently synthetic-test-only
```

Evidence:

* Materialization receives cell facts as an argument and binds their serialized values to run hashes, but does not derive or validate them against the run output: `app/services/audience.py:913-1075`.
* Release filtering checks only `distinct_vehicle_count`: `app/services/audience.py:1076-1143`, `app/services/disclosure.py:140-145`.
* Output revalidation repeats only that one check: `app/services/audience_delivery.py:154-245`.
* Live platform submission is correctly rejected unless the adapter is enabled, synthetic, in a test environment and synthetic mode is active: `app/services/audience_delivery.py:565-640`.

## 5. DSR and destruction

```text
Admin opens case
  → identity verification
  → automated database inventory
  → managed-object enumeration and optional object stat/checksum verification
  → manual evidence for device queues, logs, backups and processors
  → one immutable assessment per six named locations
  → completion when all six rows exist
```

Completion does not currently prove that every erasure assessment is semantically compatible with the reported remaining count.

---

# Confirmed privacy defects

## P1 — Real GPS intake bypasses the legal/privacy live-use gate

The privacy operating model explicitly says that no real-driver GPS may be collected until legal review approves the relevant rows: `docs/privacy-operating-model.md:13-27`.

Neither trip start nor ping ingestion invokes `ensure_disclosure_live_gate` or an equivalent collection gate:

* `app/api/v1/trips.py:62-145`
* `app/services/trips.py:604-730`

An authenticated driver can therefore persist exact coordinates under ordinary application configuration even while `live_use_authorized=false`.

**Impact:** the system can begin processing a prohibited sensitive data class before lawful basis, notice, purpose, retention and processor approvals exist.

**Exploitability:** directly reachable by a legitimate driver account; no administrator or privacy configuration change is required.

---

## P1 — Live KYC intake has the same gate bypass

The KYC endpoint accepts plaintext NIN and immediately enters the KYC service:

* `app/api/v1/kyc.py:80-107`
* `app/services/kyc.py:199-340`

Encryption happens correctly, but there is no check against `EXT-LEGAL-PRIVACY`, an approved notice, a lawful-basis reference or a KYC-specific live-use authorization.

**Impact:** encrypted storage reduces breach impact but does not make unauthorized collection lawful or policy-compliant.

**Exploitability:** directly reachable by a driver who has the required managed files and bank-account version.

---

## P1 — The advertiser campaign-trip contract is row-level, not aggregate

The route describes its output as “privacy-safe”:

* `app/api/v1/advertiser_reports.py:136-175`

Its implementation applies only the live/config gate and tenant lookup, then lists individual trips:

* Gate and query start: `app/services/reports.py:841-925`
* Row serialization: `app/services/reports.py:1008-1060`

Each item includes:

* `trip_id`
* `assignment_id`
* exact `started_at` and `ended_at`
* trip status and vehicle type
* distance and moving/stationary time
* quality score
* estimated impressions and confidence
* payout values
* fraud-count breakdown

The schema makes those fields part of the public contract at `app/schemas/reports.py:195-242`.

This contradicts the architecture’s binding audience rule that advertiser-visible output must not contain a trip ID or precise timestamp: `docs/architecture.md:1867-1890`. It also allows one-trip filtering and pagination without a contributor floor.

The route is **currently masked by fail-closed live behavior**: it uses the default `requires_measurement_run=True`, which causes production live mode to reject it. Synthetic test mode demonstrates the actual response contract. This is therefore not evidence of a current default-production disclosure, but it is a confirmed release blocker for enabling the route.

---

## P1 — Audience materialization and export do not enforce the declared disclosure policy

The general settings contain vehicle, trip and day floors plus a maximum contributor share. Heatmaps use them. Audience segments do not.

The audience helper checks only:

```text
distinct_vehicle_count >= privacy_min_vehicles_per_cell
```

Evidence:

* `app/services/disclosure.py:140-145`
* `app/services/audience.py:1076-1143`
* `app/services/audience_delivery.py:222-245`

Missing from materialization and output revalidation:

* `privacy_min_trips_per_cell`
* `privacy_min_days_per_cell`
* `privacy_max_contributor_share`
* contributor distribution facts needed to calculate that cap
* complementary suppression
* query-history/differencing checks
* policy fingerprinting and staleness on privacy-policy changes

The persisted cell model does not contain a distinct-day count or contributor distribution:

* `alembic/versions/0065_exposure_segments.py:101-145`
* `app/schemas/exposure_segments.py:1-30`

The focused tests encode the weakness: a cell with three vehicles and three trips is treated as releasable while only the vehicle threshold is overridden, despite the normal trip floor being five:

* `tests/test_exposure_segments.py:27-54`
* `tests/test_exposure_segments.py:135-225`

The cell facts are also supplied in the worker payload. Measurement-run hashes are included in the segment fingerprint, but there is no proof that the supplied counts were produced by those immutable manifests:

* `app/jobs/exposure_segments.py:1-25`
* `app/services/audience.py:913-1075`

**Impact:** once the legal/config gate is enabled, an aggregate can be exported with too few trips/days or one dominant contributor, and overlapping exports can be used for differencing.

---

## P1 — The DSR database inventory omits subject-linked tables

The inventory is a manually maintained dictionary of SQL statements: `app/services/data_subject_requests.py:28-199`.

Its `authentication_security` class counts only the `users` row. Representative subject-linked tables omitted from the inventory include:

* `password_reset_attempts.issued_user_id`
* `password_reset_tokens.user_id`
* `driver_phone_versions.driver_profile_id`
* `phone_verification_challenges.phone_version_id`
* `whatsapp_consents.driver_profile_id`
* `manual_driver_contact_tasks.driver_profile_id`

Those relationships are defined at `app/models/contact.py:34-245`.

The audit inventory also counts only `audit_events.actor_user_id`; it does not account for a subject represented through entity identifiers or metadata.

**Impact:** database inventory can undercount a subject’s records and support a false zero-record or incomplete access/erasure response.

**Root cause:** there is no model-to-DSR registry, migration-time coverage assertion or test that fails when a new subject-linked table is not classified.

---

## P1 — External-location erasure can be completed while records remain

For database and object storage, the service refuses `erased` when the computed count is non-zero. The condition is expressly limited to those two locations:

* `app/services/data_subject_requests.py:421-512`

For `device_queue`, `operational_logs`, `backups` and `processors`, an operator may submit:

```text
disposition = erased
external_record_count > 0
```

The assessment is accepted and made immutable.

Completion then verifies only that all six location names have assessment rows:

* `app/services/data_subject_requests.py:584-632`

It does not revalidate disposition/count semantics.

The database migration likewise permits any nonnegative count with an `erased` disposition:

* `alembic/versions/0062_data_subject_requests.py:107-156`

**Impact:** an erasure case can become permanently “completed” while its own immutable evidence says records remain in a device queue, log store, backup or processor.

---

## P1 — File destruction is not evidence-before-destruction

For an unreferenced managed file, the order is:

1. delete the storage object;
2. create the audit event;
3. delete the database row;
4. return to the job;
5. commit the transaction.

Evidence:

* Object deletion then audit/row deletion: `app/services/file_kyc_lifecycle.py:105-153`
* Commit occurs only after the purge service returns: `app/jobs/file_lifecycle.py:41-59`

The orphan-upload path has the same external-object-before-durable-database ordering: `app/services/stored_files.py:740-825`.

If the process crashes, the database fails or a later object in the same transaction raises after step 1, the object may be gone while:

* the database still says it exists;
* no committed audit event exists;
* no committed deletion intent identifies what happened.

Focused tests demonstrate that a later retry can reconcile a mid-batch outage, but eventual reconciliation is not the same as durable evidence before irreversible destruction: `tests/test_file_kyc_lifecycle.py:90-165`.

The reference check itself is valuable—`app/services/file_kyc_lifecycle.py:94-120`—and purpose scoping prevents unrelated file classes from being reused casually. The defect is the irreversible side-effect ordering.

---

## P2 — Audit redaction is convention-based, not centrally enforced

No concrete raw NIN, bank-account number or GPS-coordinate leak was found in the reviewed audit calls. KYC, payee, contact and ping paths generally record IDs, counts, masks, booleans and key versions.

However, the central helper accepts arbitrary metadata and persists it verbatim:

* `app/services/audit.py:12-27`

Operational logging has a scrubber, but audit metadata has no equivalent schema, denylist or sensitive-value detector. This makes the “never put sensitive data in audit metadata” rule dependent on every caller continuing to behave correctly.

This is a confirmed centralization weakness, though not a confirmed current plaintext exposure.

---

# DSR and retention coverage matrix

| Location/data class      | Current implementation                                                                                                                | Result                                                                                                                                          |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Database                 | Automated counts across many identity, location, evidence, payout and measurement tables                                              | **Fail/partial.** Material subject-linked contact and recovery tables are omitted.                                                              |
| Managed object storage   | Enumerates subject `stored_files` and upload intents; optionally verifies object existence, size and checksum                         | **Partial pass.** Storage outage/mismatch fails closed, but this covers only managed objects known to the database.                             |
| Device queues            | Database-resident ping batches and quarantines are counted under database inventory; the named external location is operator-attested | **Partial.** No queue/device adapter or machine-verifiable erase result.                                                                        |
| Operational logs         | Manual immutable assessment with external count/evidence reference                                                                    | **Manual only.** No log-store search, retention or deletion adapter.                                                                            |
| Backups                  | Manual immutable assessment                                                                                                           | **Manual only.** No backup catalog, expiry verification or restore-and-search evidence in the DSR service.                                      |
| Processors               | Manual immutable assessment                                                                                                           | **Manual only.** No processor callback, ticket state, API receipt or subprocessor evidence verification.                                        |
| GPS partitions           | PostgreSQL partition catalog, advisory lock, evidence rows, detach recovery and refusal rules                                         | **Pass statically.** Strong fail-closed design.                                                                                                 |
| Quarantined ping batches | Age-based deletion in the location-retention job                                                                                      | **Pass statically**, subject to correct production scheduling.                                                                                  |
| KYC/file objects         | Terminal-state and age policy plus reference checks                                                                                   | **Fail on destruction ordering.** External deletion precedes committed evidence.                                                                |
| Disclosure query history | Scheduled expiry purge independent of later query traffic                                                                             | **Pass statically.**                                                                                                                            |
| Audience aggregates      | Immutable and append-only; no subject erasure route                                                                                   | **Legal classification unresolved.** The operating model says treat aggregate location as personal until approved re-identification assessment. |

## Strong retention behavior

The location-partition subsystem is substantially stronger than the file lifecycle:

* It records `purge_started` before detach/destruction.
* It uses PostgreSQL catalog bounds rather than trusting partition names.
* It finalizes an interrupted detach only when matching evidence, bounds, count and current expiry policy agree.
* It refuses unattributed, non-expired, mismatched or already-terminal pending detaches.
* A refused pending detach blocks all other destruction in that run.
* Dropped evidence and the table drop occur within the database-controlled workflow.

Implementation: `app/services/data_lifecycle.py:1-760`.

Focused PostgreSQL tests cover:

* normal evidence ordering and idempotent replay: `tests/test_data_lifecycle_jobs.py:268-416`;
* actual interrupted `DETACH ... CONCURRENTLY` recovery: `tests/test_data_lifecycle_jobs.py:468-619`;
* unattributed, mismatched, terminal and no-longer-expired refusal cases: `tests/test_data_lifecycle_jobs.py:621-755`.

These tests were inspected, not executed in this review.

---

# Disclosure-bypass analysis

## What is centralized correctly

`require_governed_advertiser_output`:

1. checks that the route is registered;
2. runs the legal/config/reference gate;
3. only then reads active advertiser membership and organization state.

Evidence: `app/services/disclosure.py:18-111`.

Placeholder, blank and unresolved `EXT-*` references do not open the gate. Default production settings deny access. Focused tests assert that the gate runs before database reads and that all registered output routes return `PRIVACY_LIVE_USE_BLOCKED`: `tests/test_disclosure_control.py:64-163`, `tests/test_disclosure_control.py:339-411`.

## Where centralization stops

The service is a centralized **authorization gate**, not a centralized disclosure decision:

* Only heatmaps call `record_heatmap_disclosure`.
* That function expressly rejects non-heatmap routes: `app/services/disclosure.py:147-160`.
* Campaign summaries, daily metrics and campaign-trip rows do not apply minimum counts, contributor caps or query-history analysis.
* Audience output uses a separate helper that checks only vehicle count.

Therefore an endpoint’s presence in `DISCLOSURE_ROUTE_INVENTORY` proves that it is disabled until approval; it does **not** prove that its eventual response is privacy-safe.

## Heatmap status

Heatmaps are the strongest implemented output class:

* legal gate before raw-ping reads;
* fixed/coarse cells;
* minimum distinct vehicles;
* minimum trips;
* minimum days;
* requested-metric contributor-share cap;
* sticky suppression;
* principal/tenant/campaign/window/filter/result binding;
* overlap comparison across global, organization and campaign scopes;
* transaction-level serialization against concurrent differencing;
* bounded history retention.

Implementation: `app/services/heatmaps.py:251-341`, `app/services/heatmaps.py:520-680`, `app/services/disclosure.py:147-330`.

Focused adversarial coverage exists at `tests/test_disclosure_control.py:413-720`.

## Complementary suppression and differencing

| Output class                 |                                           Count floors |                       Contributor cap | Complementary/differencing history |
| ---------------------------- | -----------------------------------------------------: | ------------------------------------: | ---------------------------------: |
| Heatmap                      |                                     Vehicle, trip, day |                                   Yes |                                Yes |
| Campaign summary             |                                                     No |                                    No |                                 No |
| Daily metrics                |                                                     No |                                    No |                                 No |
| Campaign trips               |                                          No; row-level |                                    No |                                 No |
| Issued campaign report       | Depends on immutable report producer; not this service | Not demonstrated at response boundary |   No shared query-history decision |
| Audience recommendations/CSV |                                           Vehicle only |                                    No |                                 No |

The campaign and audience paths can therefore permit differencing or single-contributor inference once their present live blocks are lifted.

---

# Verified fail-closed controls

The following controls are supported by direct code evidence, with focused tests present where noted:

1. **Advertiser output defaults deny.** Blank, placeholder and unresolved `EXT-*` references cannot activate disclosure output. `app/services/disclosure.py:35-76`.

2. **Advertiser gate precedes sensitive reads.** Membership and campaign/report data are not read before the live gate. `app/services/disclosure.py:78-111`; focused trap-session test at `tests/test_disclosure_control.py:142-163`.

3. **Tenant isolation is consistently applied in reviewed report, heatmap and audience paths.** Campaigns are selected with advertiser-organization authority and foreign tenant objects return not-found responses. `app/services/campaigns.py:33-60`, `app/services/campaigns.py:153-180`, `app/services/audience_delivery.py:154-217`.

4. **KYC and bank plaintext are encrypted before persistence.** AES-256-GCM envelopes bind tenant, record and field through associated data; normal responses are masked. `app/adapters/crypto/envelope.py:1-420`, `app/services/kyc.py:199-340`, `app/services/payees.py:390-760`.

5. **Sensitive reveal is purpose-scoped and audited.** Invalid reveal purposes fail; audit metadata records purpose or version rather than the plaintext.

6. **Raw coordinates are not serialized by the driver trip-read schema or reviewed advertiser routes.** Raw-ping access remains internal to the established processing chain and the heatmap aggregator.

7. **Heatmap suppression and differencing controls are transactionally serialized.** Exact retries converge; changed-result and overlapping variants suppress. `app/services/disclosure.py:147-330`.

8. **Ambiguous partition-retention recovery fails closed.** An unattributed or policy-incompatible pending detach is left untouched and blocks further destruction. `app/services/data_lifecycle.py:360-760`.

9. **Audience parent staleness is rechecked before output.** Removed source links, deactivated sources, campaign changes, zone revisions and measurement-manifest changes redact recommendations and block export/activation. `app/services/audience.py:1145-1230`, `tests/test_audience_delivery.py:167-237`.

10. **Synthetic disclosure mode is configuration-restricted to test/testing environments.** Production synthetic configuration is rejected; live and synthetic modes cannot be combined. `app/core/config.py:540-650`.

11. **Ad-platform submission is not live-reachable.** Only an enabled synthetic adapter in a test environment can receive a payload. `app/services/audience_delivery.py:565-640`.

---

# Remaining legal and live gates

The repository truthfully records that the following inputs are absent:

* `EXT-LEGAL-PRIVACY`
* approved lawful-basis decisions
* approved notices and consent/objection wording
* named privacy owner and legal/compliance approver
* approved retention and DSR dispositions
* approved processor identities, regions and transfer arrangements
* `EXT-REPORT-METHOD`
* `EXT-AD-PLATFORM`

Evidence: `docs/privacy-operating-model.md:3-43`.

The advertiser gate additionally requires non-placeholder values for:

* `privacy_legal_approval_reference`
* `privacy_disclosure_config_reference`
* `privacy_query_history_retention_reference`
* `privacy_disclosure_live_authorized=true`

Reports relying on issued measurement facts also require approved live measurement configuration and reproducible immutable runs.

Those gates are meaningful for advertiser output and retargeting. They are **not wired into GPS or KYC collection**, so the documentation’s assertion that those data classes remain build-only is not a runtime truth.

Production key custody, actual object-store configuration, scheduler execution, log retention, backup expiry, processor deletion and legal approval cannot be established from source alone and require live evidence.

---

# Smallest remediation

## 1. Put one live-personal-data gate at the intake boundary

Add one purpose-aware service such as:

```text
require_live_personal_data_use(
    settings,
    purpose="precise_location_collection" | "driver_kyc_collection",
)
```

Call it inside `start_driver_trip`, `ingest_location_ping_batch` and `submit_driver_kyc` **before their first database or storage read**. Synthetic use should remain possible only under the existing test-environment invariant.

Focused regressions should use a trap session that raises if any query occurs before the gate.

## 2. Keep campaign-trip reporting disabled until the response contract is replaced

The smallest safe correction is to remove `trip_id` and `assignment_id` from the advertiser schema and replace one-trip rows with time-bucketed aggregates subject to the shared disclosure decision. Merely hashing the UUIDs would still provide stable linkage and is not sufficient.

Until then, preserve the current fail-closed live block.

## 3. Generalize the disclosure decision rather than adding another audience helper

Make one service consume trusted aggregate evidence containing:

* distinct vehicles;
* distinct trips;
* distinct days;
* total metric;
* largest-contributor metric;
* cell/window/context identity;
* source measurement-run and policy fingerprints.

Use it for heatmaps, audience recommendations/exports and any future low-cardinality report. Persist served and suppressed audience/report decisions in the existing history family or an equivalent shared authority.

Materialization should derive cells from the immutable measurement result or verify a signed/hash-bound manifest entry; it should not trust free worker arguments merely because the surrounding run hashes are recorded.

## 4. Make DSR inventory registry-driven

Create one explicit subject-data registry used by:

* the DSR inventory;
* retention ownership;
* access/export classification;
* erasure/exception classification;
* a test that enumerates all models containing `user_id`, `driver_profile_id`, phone-version or equivalent subject links.

Add the currently omitted contact and recovery tables.

For every location, enforce:

```text
disposition == erased  ⇒  record_count == 0
```

in both service validation and a database check constraint. Completion should load the six assessments and validate their disposition/count semantics, not just their names.

## 5. Commit a destruction intent before deleting an object

Use a minimal state record:

```text
planned → object_deleted → database_finalized
```

The `planned` row, object key/checksum, reason, subject/purpose and job identity must commit before `storage.delete`. A retry/reconciler can then safely finish either side after a crash. The terminal audit evidence should identify the committed intent.

Apply the same ordering to orphan-upload cleanup.

## 6. Add audit-metadata enforcement

Place a recursive sensitive-key/value validator or per-action metadata schema in `create_audit_event`. At minimum reject coordinate, NIN/BVN, bank/account, phone, token, password, secret and signed-URL fields. This turns the existing caller convention into a centralized invariant.

---

# Live-gate status

| Capability                                     | Current status                                                                                                                                        | Correctly gated?                                                                   |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| **Live GPS collection**                        | Authenticated driver can persist exact GPS without privacy approval                                                                                   | **No**                                                                             |
| **Live KYC collection**                        | Authenticated driver can submit NIN and KYC documents without privacy approval; data is encrypted afterward                                           | **No**                                                                             |
| **Advertiser reporting**                       | Default production configuration denies output before reads; campaign-trip endpoint remains blocked in live mode but has an unsafe row-level contract | **Partly. Fail-closed today, not safe or truthful for enablement**                 |
| **Heatmaps**                                   | Default denied; strong floors, contributor cap and differencing controls when enabled                                                                 | **Yes at the software boundary, pending legal/live approval and runtime evidence** |
| **Retargeting materialization and CSV export** | Default denied; parent/run checks present; vehicle floor only                                                                                         | **No for live enablement**                                                         |
| **Ad-platform activation**                     | Synthetic test adapter only; live adapter rejected                                                                                                    | **Yes, correctly gated off**                                                       |

**Bottom line:** live GPS, live KYC, overall advertiser reporting and overall retargeting do **not** all remain correctly gated. Only advertiser-output default denial, heatmap disclosure controls and ad-platform activation are credibly fail-closed. The GPS/KYC collection bypasses and the unsafe eventual report/audience contracts make the current privacy `DONE` claims materially untrue at this commit.

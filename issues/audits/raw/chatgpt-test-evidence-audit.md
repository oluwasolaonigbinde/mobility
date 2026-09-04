---
source_surface: ChatGPT
project: TSS
conversation_id: 6a9692e5-f738-83e9-a454-e79d97a25369
displayed_title: Audit test evidence
displayed_model: Claude Opus 5 via ChatGPT
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete owner-supplied response
redactions: none
audited_ref: 637841d95493bcc24334356da42097fa53a5d16f
---

# Audit test evidence

> Complete response supplied directly by the project owner on 1 September 2026. It is source evidence, not an accepted finding or remediation decision.

# Verdict

**AMBER — the suite provides credible application-level, database, migration, privacy, retry, and offline-state evidence, but it is not yet sufficient as launch evidence.**

At commit `637841d95493bcc24334356da42097fa53a5d16f`, the test corpus is materially stronger than a typical mock-heavy pre-launch suite. It includes genuine PostgreSQL concurrency tests, executable Alembic migration cycles, adversarial privacy-differencing cases, durable-queue recovery scenarios, and browser checks against a Dockerized API/PostGIS stack.

Its central weakness is not lack of test quantity. It is **evidence-boundary ambiguity**:

* many ordinary backend tests still run against SQLite schemas created directly from current ORM metadata;
* important provider and infrastructure integrations are optional or synthetic;
* the richer browser “release rehearsal” and pilot suites use handcrafted mock APIs;
* real bank, payment, messaging, device, storage, network, and operating-system behavior remain unproven;
* no GitHub status or workflow run is attached to the exact audited SHA, so the repository’s green-count claims cannot be independently tied to this immutable revision.

The requested branch resolves exactly to the requested commit. The branch is unprotected, and GitHub reports no commit statuses or workflow runs for this SHA.

Terminal networking could not resolve GitHub, so I could not execute targeted tests locally. The conclusions below distinguish:

1. what test source structure proves;
2. what `docs/progress.md` reports was previously run;
3. what is externally verifiable as green at this exact SHA—which is currently nothing.

This is an **evidence audit**, not a finding that the corresponding product behavior is defective.

---

# Evidence-confidence matrix

| Domain                                 | What the suite credibly proves                                                                                                         |                                     Confidence | Principal boundary                                                                                           |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------: | ------------------------------------------------------------------------------------------------------------ |
| Exact-revision red/green provenance    | Commit and branch identity are exact                                                                                                   |                 **Low for execution evidence** | No status checks or Actions runs attached to the SHA                                                         |
| Backend unit/service behavior          | Broad happy-path, failure-path, lifecycle, and authorization coverage                                                                  |                                     **Medium** | Shared default database fixture is SQLite and builds from ORM metadata                                       |
| PostgreSQL concurrency                 | Real two-session races for billing, payout, privacy, and recovery invariants                                                           |                     **High for sampled paths** | Not every service with a race-sensitive invariant has an equivalent PG test                                  |
| Alembic migrations                     | Sampled invoice-authority migration performs executable PostgreSQL upgrade, downgrade, re-upgrade, data backfill, and invariant checks | **High for sampled migration; medium overall** | Cannot infer equal rigor for every migration without an exact-SHA migration gate                             |
| Authentication/session                 | Disabled/suspended users, forced reset, session invalidation, refresh limits, organization context, recovery throttling                |                                **Medium–high** | Some assertions prove internal calls or generated tokens rather than deployed proxy/cookie/provider behavior |
| Tenant isolation and RBAC              | Cross-organization report denial, role restrictions, sensitive-field absence, maker/checker separation                                 |                                     **Medium** | Strong point tests, but no generated role × tenant × resource × action denial matrix                         |
| Geospatial/tracking                    | Deterministic route, distance, stationary, proof-of-play, and ingestion semantics                                                      |                     **Medium–high internally** | No physical-route, GPS chipset, background execution, spoofing, or urban-canyon evidence                     |
| Billing and collections                | Invoice, receipt, allocation, funding, idempotency, reversal, and concurrent reservation behavior                                      |                            **High internally** | Payment-provider boundary is fake or disabled                                                                |
| Payout/disbursement                    | Frozen instructions, append-only state, holds, reconciliation, idempotency, provider-event convergence, race serialization             |                            **High internally** | No bank/provider settlement finality or live statement reconciliation                                        |
| Privacy disclosure controls            | Thresholds, default deny, sticky decisions, overlap and parent/child differencing, retry behavior, concurrent serialization            |                   **High for modeled attacks** | No broad multi-query composition, colluding-principal, longitudinal, or auxiliary-data attack campaign       |
| Files, malware scanning, and KYC       | File lifecycle, scanner protocol, quarantine/purge logic, retries, KYC workflow                                                        |                                     **Medium** | Most lifecycle tests use in-memory doubles; MinIO+ClamAV integration is opt-in                               |
| Workers and retries                    | Rollback, bounded cursors, re-enqueue sweeps, duplicate convergence, email claim serialization, real Redis/ARQ in CI design            |                     **Medium–high internally** | Few true process-kill tests; external-side-effect-before-local-commit window remains assumed                 |
| Frontend unit/component tests          | UI state machines, validation, fail-closed behavior, offline queue handling                                                            |                                     **Medium** | `server-only` is replaced by a no-op; jsdom and mocked server actions alter authority boundaries             |
| Browser tests against real backend     | Page access, seeded sessions, navigation, role views, some stack-level smoke behavior                                                  |                                     **Medium** | Driver suite deliberately avoids mutations and is principally read-only smoke                                |
| Synthetic release/pilot browser suites | UI contract rehearsal, manifest/cache behavior, offline views, session-revocation presentation, role redirects                         |    **Medium for UI; low for system authority** | Business state and authority come from handcrafted Node mock servers                                         |
| PWA/offline queue                      | Reload recovery, reconnect drains, lost response, ACK discipline, dead letters, encrypted storage, lock failure                        |             **High for modeled state machine** | `fake-indexeddb`, synthetic browser APIs, and no real mobile lifecycle/eviction evidence                     |
| Provider delivery                      | Adapter request formation and response handling                                                                                        |                                 **Low–medium** | No live payment, bank, email, SMS, or identity provider acceptance/failure evidence                          |
| Coverage completeness                  | Large and domain-spanning suite                                                                                                        |                **Low as a completeness claim** | No enforced backend or frontend coverage threshold                                                           |
| Documentation `DONE` claims            | Package evidence is detailed and often appropriately scoped                                                                            |                                     **Medium** | Counts and “green” statements are not attached to the immutable SHA                                          |

CI is designed around PostGIS 16, Redis, Alembic, and a Dockerized API for ordinary browser tests, which is a material strength. It nevertheless applies primarily on `master`/pull-request workflows, has path filters, and supplies no run for this exact commit.

The backend fixture explains much of the confidence split: its normal session uses SQLite plus `Base.metadata.create_all`, while PostgreSQL/PostGIS is an explicit, skippable fixture and likewise constructs current metadata unless a test deliberately invokes Alembic.

---

# High-confidence areas

## 1. Several concurrency tests are genuine database races

The suite should not be dismissed as using “fake concurrency” globally. Important tests open independent PostgreSQL sessions and deliberately overlap operations.

Examples include:

* concurrent receipt creation and invoice numbering;
* allocation, reversal, and funding races;
* payout reservation;
* submit-versus-void serialization;
* webhook-versus-poll payout convergence;
* password-recovery rate-limit races;
* privacy disclosure serialization.

The billing concurrency tests are explicit PostgreSQL tests rather than multiple coroutines sharing a SQLite connection.

Payout tests similarly exercise independent-session races around batch reservation and conflicting lifecycle operations.

The reconciliation suite checks idempotent provider evidence, terminal-state monotonicity, and concurrent webhook/poll finalization.

These tests provide strong evidence for the exact raced operations they cover. They do not automatically prove every service that uses a uniqueness constraint, advisory lock, state transition, or retry loop.

## 2. Privacy includes real adversarial differencing cases

The concern “privacy tests only check a minimum threshold” is not borne out by the inspected suite.

The disclosure-control tests include:

* default-deny and production/synthetic-mode separation;
* overlapping-query differencing;
* parent-versus-child organizational scope attacks in both orders;
* sticky suppression and retry decisions;
* changed-result handling;
* threshold-boundary cases;
* cross-metric domination;
* concurrent PostgreSQL serialization in which overlapping requests cannot both escape control.

That is substantive adversarial evidence, not merely response-schema validation.

The remaining gap is attack breadth: sequences involving more than two queries, colluding authorized users, alternating dimensions and time windows, state expiry, external auxiliary data, and repeated low-volume probing.

## 3. Offline queue semantics are thoughtfully tested

The queue tests cover more than “enqueue then dequeue”:

* monotonic sequence generation;

* concurrent producers;

* cut-versus-add serialization;

* stable retry identity;

* explicit ACK before deletion;

* no-ACK retention;

* terminal dead letters;

* per-driver isolation;

* encrypted persistence and tamper failure;

* missing-key failure;

* interrupted migration and resume;

* Web Lock requirements;

* close/reopen recovery of pending events, batches, and sequence state.

The trip-tracker component tests also model:

* reload during an active trip;

* reconnect-triggered drains;

* stranded batches;

* lost Start and End responses;

* server reconciliation;

* missing storage or lock;

* wake-lock and visibility transitions;

* incomplete end watermarks;

* terminally rejected batches;

* revoked sessions.

This refutes a blanket finding that reload and network-loss cases are absent. The qualification is that these tests use jsdom, `fake-indexeddb`, mocked server actions, and synthetic browser APIs.

## 4. Money-state invariants are unusually well represented

Within the application/database boundary, the payout suite exercises:

* frozen payout instructions;

* append-only economic records;

* sensitive-data separation;

* maker/checker authorization;

* authoritative holds;

* retry-safe transitions;

* idempotent evidence processing;

* terminal state monotonicity;

* concurrent reservation and finalization.

The suite therefore does provide money evidence. What it does **not** provide is real settlement finality: the provider implementations available in the inspected code are disabled or fake.

## 5. At least the sampled migration test is executable, not textual

The invoice-authority hardening migration test executes:

* an Alembic upgrade;
* a downgrade;
* a re-upgrade;
* a data-bearing transition from the prior revision;
* legacy data backfill;
* post-transition invariants.

That is credible migration evidence. The audit did not establish that every migration receives the same treatment, so the finding is “strong sampled evidence, incomplete chain-level proof,” not “all migration tests are text-only.”

## 6. Worker recovery is stronger than ordinary mocked-job coverage

The worker suite tests:

* failed-attempt rollback;

* bounded and resumable cursors;

* cursor write/delete failure;

* recovery after database commit but before Redis enqueue;

* bulk re-enqueue sweeps;

* uniqueness convergence;

* a real Redis/ARQ burst worker requirement in CI.

Email delivery adds idempotency, retry, backoff, dead-letter, redaction, escaping, and PostgreSQL claim serialization.

---

# False-confidence risks

## 1. Exact-SHA “green” status is absent

This is the most important evidence-governance weakness.

`docs/progress.md` records substantial pass counts and green claims, including PostgreSQL, frontend, browser, and focused-package results. Those statements may be accurate, but GitHub exposes no check status and no workflow run associated with commit `637841d…`.

A reviewer cannot answer:

* whether those commands ran against this exact tree;
* whether skipped tests matched the documented list;
* whether the test image and dependency lockfiles were the same;
* whether retries converted an initial failure to a pass;
* whether artifacts, logs, and migration output were retained.

**Risk:** “DONE” becomes a prose assertion instead of immutable red/green evidence.

## 2. SQLite is the ordinary backend reality

The shared test session defaults to SQLite and builds tables from current ORM definitions.

This can miss or distort:

* transaction isolation and lock behavior;
* advisory locks;
* deferred constraints;
* partial and expression indexes;
* exclusion constraints;
* PostgreSQL enum and JSON behavior;
* server defaults and generated values;
* timezone coercion;
* statement-level failures;
* PostGIS operators and indexing;
* migration-versus-model drift.

The presence of excellent PostgreSQL tests in selected areas mitigates but does not remove this risk.

**False-confidence pattern:** a service passes dozens of SQLite lifecycle tests and one developer assumes its database invariants are therefore production-proven.

## 3. Current ORM metadata can bypass migration truth

`Base.metadata.create_all` shows that today’s model can construct a compatible schema. It does not prove that a deployed database can reach that schema through every historical migration, with existing data, transaction boundaries, locks, extensions, and downgrade expectations intact.

The sampled migration `0036` is a good counterexample because it deliberately uses Alembic and legacy data.

**Risk:** migration omissions are hidden by tests that start from the final ORM state.

## 4. Important integrations are optional skips

The PostGIS fixture skips when its environment is unavailable. Local MinIO+ClamAV integration requires an explicit flag.

The progress document also distinguishes expected PostgreSQL skips and external pilot/device evidence that has not run.

An optional integration test is useful for development, but it is not release evidence unless the release gate fails when the dependency is unavailable or the test skips unexpectedly.

## 5. Rich browser rehearsals use synthetic authority

The named release/pilot modes start bespoke mock APIs. The `w401d` server hardcodes sessions, user states, billing states, fraud states, payout states, and endpoint responses.

The associated Playwright suite provides useful evidence for:

* page rendering;
* browser routing;
* manifest/service-worker integration;
* offline presentation;
* reload behavior;
* session-revocation UI;
* role-specific navigation;
* mobile WebKit rendering.

It does not prove that the production API, authorization middleware, database, workers, and service worker produce those states together.

The ordinary seeded-stack driver suite does use the Docker API, but explicitly behaves as read-only smoke coverage.

**Risk:** “release rehearsal passed” can be misread as an end-to-end business-authority test.

## 6. Synthetic providers bypass settlement and delivery reality

Payment and disbursement provider implementations inspected are disabled/fake.

Email/provider tests mock HTTP or use adapters/doubles. File scanning has a good local TCP contract test, but not normal-CI evidence against real ClamAV; storage lifecycle commonly uses in-memory storage or SDK stubs.

These tests can prove:

* request shape;
* signature and idempotency logic;
* local status transitions;
* response parsing;
* retry classification.

They cannot prove:

* the provider accepted and durably recorded the operation;
* duplicate suppression at the provider;
* delayed or reordered webhooks;
* provider-specific timeout and ambiguous-response behavior;
* bank-side finality;
* reconciliation against an independently sourced statement;
* sender reputation and actual email/SMS delivery;
* identity-provider production policy.

## 7. The external-side-effect crash window is not closed by local retries

The suite handles many internal crash and retry windows well. The hardest window remains:

1. Cardvert submits an external operation;
2. the provider accepts it;
3. Cardvert crashes or loses the response before recording acceptance;
4. retry occurs.

The application supplies idempotency identities, but live provider behavior under that exact sequence is not demonstrated. The same issue applies to disbursement, payment, email, SMS, and possibly KYC.

This is missing evidence, not proof that duplicate payment or delivery will occur.

## 8. Some tests are implementation-coupled

Examples include:

* monkeypatching password verification and asserting call sequences to infer enumeration resistance;

* comparing worker configuration object identity;

* inspecting Compose YAML text;

* scanning source or SQL text for expected route/control tokens;

* replacing `server-only` with a no-op in Vitest.

These checks can be valuable guards. They should not be treated as equivalent to measuring observable behavior at the trust boundary.

For example, equal password-verifier call counts do not establish equal externally visible response timing across the deployed proxy, database, hash cache, and network.

## 9. Tenant/RBAC negatives are strong but not systematic

There are good exact examples:

* cross-organization report access yields non-disclosing failure;

* sensitive fields are absent from report output;

* drivers cannot be assigned advertiser-owner roles;

* unauthorized roles cannot perform organization or money operations;

* payout maker/checker separation is tested.

The gap is a systematic denial matrix across every externally addressable resource and action, including stale and removed memberships, guessed UUIDs, exports, map tiles, files, job-status endpoints, nested resources, and asynchronous result retrieval.

Point negatives prove those points; they do not prove complete tenant isolation.

## 10. PWA evidence uses emulation at the hardest boundaries

`fake-indexeddb`, jsdom, mocked Web Locks, mocked wake locks, synthetic geolocation, and browser emulation are appropriate for deterministic state-machine testing. They do not reproduce:

* mobile OS process termination;
* IndexedDB quota pressure or eviction;
* Safari background throttling;
* service-worker replacement during an active trip;
* network handoff between Wi‑Fi and cellular;
* captive portals;
* device clock jumps;
* permissions revoked in system settings;
* battery saver behavior;
* GPS stalls or stale positions;
* storage corruption after abrupt termination.

The component logic is well covered. The operational environment is not.

## 11. No enforced coverage threshold

The backend configuration does not establish a coverage floor. The frontend Vitest configuration has exclusions but no minimum line, branch, function, or statement threshold.

Coverage percentage would not prove correctness, but an enforced changed-code or critical-module floor would expose accidental disappearance of test reach. Today, a meaningful test file can be removed without necessarily causing a coverage gate to fail.

## 12. Timing and timezone evidence is uneven

Positive evidence exists where the code uses UTC-aware timestamps and tests fixed business periods. However, some tests rely on wall-clock behavior, including a recovery-token expiry test using an approximately 1.1-second sleep.

That pattern is vulnerable to scheduler jitter and can test only one side of a boundary.

Missing or insufficiently evidenced edge classes include:

* exact expiry instant versus one microsecond before/after;
* Lagos midnight across UTC dates;
* long-running jobs crossing local-day boundaries;
* client device clock changes;
* DST behavior in external systems, even though Lagos itself does not currently use DST;
* database clock versus application clock divergence;
* webhook timestamps that are late, future-dated, or replayed.

## 13. Snapshot masking is not the dominant risk

I found no evidence in the sampled files that broad visual or object snapshots are the principal assertion style. The more material concerns are:

* scripted mock-server responses;
* implementation-level assertions;
* current-ORM schema creation;
* absence of immutable run artifacts.

Any existing snapshots should still be constrained to stable presentation fragments and paired with semantic assertions, but snapshot overuse did not emerge as a leading audit finding.

---

# Missing tests ranked by launch impact

## P0 — required before money-moving or public-driver staging

### 1. Real provider idempotency and ambiguous-response certification

For each payment and disbursement provider, exercise in its sandbox or certification environment:

* accepted request with response forcibly dropped;
* same idempotency key retried;
* different key with same business reference;
* timeout before provider receipt;
* timeout after provider acceptance;
* delayed, duplicate, reordered, and contradictory webhooks;
* poll/webhook races;
* terminal reversal or rejection;
* provider-side duplicate search;
* reconciliation to an independently downloaded provider report.

**Launch impact:** duplicate charge, duplicate payout, false “paid,” or unreconciled funds.

### 2. Real bank settlement-finality reconciliation

Build a controlled low-value batch and show that:

* submitted instructions match provider/bank records;
* accepted is distinct from settled;
* failed and returned transfers re-enter the correct authoritative state;
* final local amounts and beneficiary identities match an independent settlement artifact;
* one missing or duplicated provider line fails reconciliation;
* maker/checker and evidence provenance survive export/import.

**Launch impact:** financial loss and incorrect driver balances.

### 3. Physical-device offline trip interruption matrix

On at least a low-end Android device and an iPhone:

* begin a trip online;
* lose network before request headers, mid-upload, and after server commit;
* force-close the browser/PWA;
* reboot the phone;
* leave it backgrounded long enough for OS suspension;
* switch Wi‑Fi/cellular;
* revoke location permission;
* exhaust or pressure storage;
* reload during active capture;
* deploy a service-worker update;
* restore network and verify exactly-once server evidence and honest completion status.

**Launch impact:** lost evidence, duplicate evidence, false completed trips, or unsafe driver instructions.

### 4. Exact-SHA mandatory release workflow

The exact candidate SHA must produce a non-skippable workflow containing:

* dependency lockfile hashes;
* migration head;
* PostgreSQL/PostGIS versions;
* Redis version;
* all selected commands and exit codes;
* test and skip manifests;
* JUnit reports;
* Playwright traces/screenshots for failures;
* container digests;
* generated contract-diff artifact;
* a signed summary or attestation.

No required job may report success when its dependency is absent.

**Launch impact:** inability to establish what was actually tested.

### 5. End-to-end mutation journeys against the real API

Move the highest-risk mocked release-rehearsal scenarios onto the Dockerized backend:

* session revocation during a mutation;
* cross-role mutation attempts;
* driver Start → ping upload → End → backend reconciliation;
* billing authorization change;
* fraud hold and release;
* payout review and approval;
* offline replay after server-side state change.

Retain the mock suite for deterministic UI permutations, but do not count it as the release authority gate.

**Launch impact:** frontend and backend can each pass while their authority contract is wrong.

## P1 — required before expanding pilot volume

### 6. Full migration-chain test from realistic predecessor snapshots

For every release:

* upgrade an empty database to head;
* upgrade representative predecessor snapshots containing realistic data;
* run invariants and application smoke;
* test permitted downgrade boundaries;
* re-upgrade;
* compare Alembic head to ORM metadata;
* verify extensions, indexes, partial indexes, exclusion constraints, checks, triggers, and server defaults through PostgreSQL catalog queries.

**Launch impact:** deployment failure or silent invariant loss.

### 7. Generated tenant/RBAC negative matrix

Enumerate:

* principals: anonymous, driver, advertiser member, advertiser admin/owner, platform roles, suspended/removed/stale memberships;
* tenants: own, other, deleted/inactive;
* resources: path UUIDs, nested resources, reports, maps, exports, files, jobs, audit records, payout and KYC records;
* actions: list, get, create, update, delete, approve, download, poll.

Assert status code, non-disclosure, absence of side effects, and audit behavior.

**Launch impact:** cross-tenant data disclosure or privilege escalation.

### 8. Multi-step privacy attack campaign

Extend the current strong pairwise differencing tests to:

* three or more overlapping time windows;
* alternating dimensions and aggregation levels;
* multiple authorized accounts under one organization;
* cross-organization collusion;
* repeated queries around threshold transitions;
* removal/addition of one vehicle or trip;
* delayed retries after sticky-decision expiry;
* composition across map, report, export, and measurement endpoints;
* auxiliary knowledge about one known contributor.

Assert an explicit privacy budget or conservative suppression policy across the sequence.

**Launch impact:** reconstruction of driver or route information despite each single response looking safe.

### 9. True worker termination tests

Use a real broker and database, then kill the worker process at controlled points:

* after claiming but before side effect;
* after external side effect but before local commit;
* after local commit but before broker ACK;
* during cursor persistence;
* during dead-letter transition;
* during recovery sweep.

Restart and verify eventual, idempotent convergence.

**Launch impact:** stuck jobs, duplicates, or missing notifications/payments.

### 10. Always-on MinIO/ClamAV integration

Promote the existing upload → scan → KYC → purge journey from opt-in local execution to a required release job, using pinned container images and fail-on-skip semantics.

Add abrupt scanner termination, object-store timeout, stale multipart upload, quarantine-read denial, and shared-object/orphan cleanup.

**Launch impact:** unsafe files becoming visible or regulated documents not being deleted correctly.

## P2 — important hardening

### 11. Clock-injected boundary and Lagos-day property tests

Replace wall-clock sleeps with an injected clock and test:

* exact expiry boundaries;
* Lagos 23:59:59.999999 → 00:00;
* events around UTC date changes;
* long job crossing midnight;
* future/past provider timestamps;
* monotonic versus wall-clock behavior;
* generated random intervals and allocation conservation.

### 12. Changed-code coverage and mutation testing on critical modules

Set thresholds specifically for:

* authentication/session invalidation;
* tenant-scope dependencies;
* disclosure controls;
* money-state transitions;
* payout reconciliation;
* offline queue;
* worker recovery;
* retention/purge.

Apply mutation testing selectively to verify tests fail when authorization predicates, comparison operators, idempotency keys, terminal-state guards, or amount signs are altered.

### 13. Contract tests for real browser security boundaries

Run production builds with:

* real `server-only` enforcement;
* cookie flags;
* CSRF and origin checking;
* proxy/header normalization;
* cache-control;
* service-worker scope;
* cross-origin mutation attempts;
* direct browser requests that bypass server actions.

---

# Tests to strengthen rather than duplicate

## `tests/conftest.py`

Keep SQLite for fast pure-domain feedback, but introduce explicit markers:

* `unit_sqlite`;
* `postgres`;
* `postgis`;
* `alembic`;
* `redis`;
* `external_contract`;
* `browser_real_api`;
* `browser_mock_api`;
* `physical_device`.

In CI, fail when a required marker selects zero tests or skips due to missing infrastructure. Do not silently let `TEST_DATABASE_URL` coexist with a suite that mostly remains SQLite without making that split visible.

## `tests/test_auth.py`

Retain the verifier-call assertion as a structural guard, but add:

* observable latency-distribution comparison for unknown versus known accounts over many requests;
* deployed cookie/security-header assertions;
* reset and forced-password-change behavior through the browser/API boundary;
* concurrent session invalidation;
* stale refresh-token use after rotation;
* proxy-normalized origin and CSRF cases.

## `tests/test_contacts_and_recovery.py`

Replace the `sleep(1.1)` expiry test with a controllable clock and exact boundary assertions. Preserve the existing PostgreSQL race test, then add a real delivery sandbox contract for token non-disclosure, duplicate suppression, and delayed delivery.

## `tests/test_advertiser_reports.py`

Keep the precise sensitive-field and cross-tenant assertions. Add one real pipeline test that starts from accepted tracking evidence and reaches:

* aggregation;
* privacy disclosure decision;
* report generation;
* advertiser retrieval.

Do not seed the final aggregate/report rows in this test. That will prove the integration contract rather than merely the presentation of already trusted records.

## `tests/test_disclosure_control.py`

The current adversarial cases are valuable and should remain. Strengthen them with generated query sequences, colluding principals, multiple endpoints, decision expiry, and cross-release regression corpora. Avoid relying on source-string inspection where an executable unauthorized request can establish the same invariant.

## `tests/test_billing_concurrency.py`

Preserve the real PostgreSQL races. Add process separation and fault injection around transaction commit, connection loss, serialization failures, lock timeouts, and retry exhaustion. Validate persisted business invariants after every interleaving, not merely returned status codes.

## `tests/test_payout_batches.py` and `tests/test_payout_reconciliation.py`

Connect the existing strong state-machine tests to a provider certification stub that behaves like the selected provider, then to a real sandbox.

Add:

* provider accepted/local commit lost;

* webhook before submit response;

* webhook after local timeout;

* duplicate provider reference;

* provider status regression;

* returned transfer after initial settlement;

* independent statement mismatch.

## `tests/test_worker_jobs.py`

Do not duplicate the existing cursor and recovery cases. Add a harness that terminates a worker container at named fault points and restarts it. Record an immutable operation ID and verify database, broker, audit, and provider state after convergence.

## `frontend/src/lib/trips/ping-queue.test.ts`

Retain the detailed fake-indexeddb suite as fast deterministic proof. Add Playwright tests in real Chromium/WebKit that use actual IndexedDB, service workers, reloads, browser-context termination, offline toggling, and quota pressure.

## `frontend/src/app/driver/(portal)/track/trip-tracker.test.tsx`

The mocked state-machine suite is already broad. Its next value comes from moving a small set of the hardest scenarios to real API/browser tests:

* lost Start response;
* reload while active;
* lost End response;
* server says active after local uncertainty;
* revoked session during drain;
* terminally rejected batch;
* storage failure before completion watermark.

## `frontend/e2e/w401d-release-rehearsal.spec.ts`

Retain this as **synthetic UI rehearsal** and rename/report it accordingly. Create a separate real-authority suite with the same scenario names against the Dockerized backend so reports cannot conflate them.

## `tests/test_migration_0036_invoice_authority_hardening.py`

Use this test as the minimum migration pattern for other high-risk migrations:

* predecessor revision;
* realistic legacy rows;
* upgrade;
* data and catalog invariants;
* downgrade where supported;
* re-upgrade;
* application read/write smoke.

---

# Minimal pre-staging suite

This should be a risk gate, not a full-suite total hunt.

## Gate 1 — provenance and static consistency

* Verify checked-out SHA equals `637841d95493bcc24334356da42097fa53a5d16f`.
* Install strictly from lockfiles.
* Validate `docs/progress.md`.
* Lint and type-check backend/frontend.
* Generate API contracts and require a clean diff.
* Record dependency versions and container digests.
* Fail on unexpected skips.

## Gate 2 — database and migrations

Against PostgreSQL/PostGIS:

* empty database → Alembic head;
* selected predecessor database snapshots → head;
* schema/catalog assertions;
* sampled downgrade/re-upgrade where supported;
* high-risk constraint tests;
* all true concurrency tests for billing, payout, privacy, recovery, uniqueness, and append-only behavior.

No SQLite substitution is acceptable in this gate.

## Gate 3 — security and tenancy

Run focused tests for:

* authentication and session rotation/invalidation;
* reset replay and expiry;
* forced-password-change enforcement;
* CSRF/origin behavior;
* role denials;
* removed/stale memberships;
* cross-tenant reports, maps, files, exports, jobs, and UUID access;
* sensitive-field non-disclosure;
* maker/checker separation.

## Gate 4 — money authority

Run:

* billing and payment idempotency;
* invoice/receipt/allocation races;
* payout calculation and frozen instructions;
* holds and release;
* batch reservation and submit/void race;
* webhook/poll convergence;
* reconciliation mismatch tests;
* provider sandbox ambiguous-response scenario;
* independent settlement artifact comparison.

## Gate 5 — privacy

Run the existing disclosure suite, including PostgreSQL concurrency and differencing, plus:

* multi-query campaign;
* colluding-principal case;
* cross-endpoint composition;
* threshold boundary;
* sticky-decision expiry;
* one realistic report-generation pipeline.

## Gate 6 — workers, files, and retry recovery

Run:

* Redis/ARQ worker integration;
* database-commit-before-enqueue recovery;
* cursor interruption;
* email claim concurrency;
* one process-kill/restart scenario;
* mandatory MinIO+ClamAV lifecycle;
* purge and orphan/shared-object deletion.

## Gate 7 — browser against real API

Use production frontend build plus Dockerized API/PostGIS/Redis:

* login and session revocation;
* representative admin, advertiser, and driver role journey;
* one unauthorized cross-role mutation;
* driver Start → pings → offline → reconnect → End;
* billing/fraud/payout authoritative-state display;
* service worker and offline fail-closed behavior;
* Chromium and WebKit at minimum.

Keep synthetic mock-server suites as an additional gate, clearly labeled “UI contract rehearsal.”

## Gate 8 — evidence publication

Publish against the exact SHA:

* JUnit/XML;
* skip and xfail report;
* migration logs;
* PostgreSQL and extension versions;
* Playwright reports/traces;
* provider sandbox request IDs with secrets removed;
* device/build identifiers;
* test command manifest;
* final signed red/green summary.

A required test that did not execute must make the gate red, not green-with-skip.

---

# Real-device and live-provider evidence plan

## Physical device matrix

Use at minimum:

* one current and one older Android device, including a resource-constrained model;
* one current iPhone and one older supported iPhone;
* installed PWA and browser-tab modes where both are supported;
* cellular and Wi‑Fi networks;
* production frontend build pointed at a controlled staging environment.

For every run, record:

* app commit SHA;
* frontend build identifier;
* device model and OS version;
* browser/PWA version;
* permission state;
* network transitions;
* server correlation IDs;
* local queue counts before and after recovery;
* battery level and relevant power mode;
* final database evidence counts and sequence range.

Core scenarios:

1. online clean trip;
2. start response lost after server acceptance;
3. ten minutes offline with multiple queued batches;
4. browser force-close while offline;
5. device reboot while trip is active;
6. reconnect followed by duplicate retry;
7. network switch during upload;
8. location permission revoked mid-trip;
9. background suspension;
10. service-worker update during an active trip;
11. logout/session revocation with pending evidence;
12. storage pressure or write failure;
13. End response lost;
14. one terminally invalid batch among valid later batches.

Acceptance should be based on server and device evidence together, not screenshots alone.

## Payment and disbursement provider certification

For each live-selected provider:

* verify credential scopes and sandbox/production separation;
* document the provider’s idempotency contract;
* submit a low-value controlled operation;
* drop responses intentionally at the test proxy;
* replay the exact idempotency key;
* send duplicate and reordered webhook fixtures through the real signature-verification path;
* poll concurrently with webhook delivery;
* download an independent provider report;
* reconcile amount, currency, beneficiary, provider reference, timestamps, fees, and terminal status;
* test return/reversal where the provider supports it.

No real customer or driver funds should be involved in certification; use controlled accounts and approved low-value transactions.

## Email and SMS delivery

Use controlled test recipients on multiple networks/providers and verify:

* accepted versus delivered distinction;
* duplicate suppression;
* delayed delivery;
* provider outage and timeout;
* callback replay;
* unsubscribed or invalid destination handling;
* reset-token secrecy in logs and telemetry;
* expiration by the time a delayed message arrives;
* application recovery after provider acceptance but local response loss.

## Storage and malware scanning

Against staging-equivalent object storage and scanner:

* clean file;
* standard harmless malware test signature;
* scanner unavailable;
* timeout during scan;
* object missing after metadata commit;
* duplicate upload;
* quarantined-object access denial;
* object-store outage during purge;
* shared-object reference protection;
* orphan sweep;
* interrupted multipart upload;
* retention expiration and deletion evidence.

## KYC or identity provider

Where a provider is selected, verify:

* request signing and callback verification;
* pending, approved, rejected, expired, and manual-review states;
* duplicate callbacks;
* callback before initial response;
* provider reference reuse;
* redaction in logs;
* deletion/retention behavior;
* sandbox-to-production configuration divergence.

## Evidence handling

For every live-provider test, preserve:

* Cardvert correlation and idempotency IDs;
* provider request/reference IDs;
* sanitized request/response metadata;
* webhook receipt times and signatures’ verification result;
* local database state transitions;
* independent provider report or dashboard export;
* reviewer identity and timestamp;
* exact commit and deployment image digest.

Secrets, full identity documents, raw GPS, and banking details should not enter general CI artifacts.

---

# Assessment against the 18 requested concerns

1. **Mocks proving mocks:** present, especially release/pilot browser suites and external adapters; well-written but must be labeled correctly.
2. **SQLite for PostgreSQL/PostGIS:** a material systemic risk in the default fixture; mitigated by genuine targeted PG tests.
3. **Critical optional skips:** present for PostGIS locally and MinIO/ClamAV; unacceptable as the sole launch gate.
4. **Unrealistic browser/server authority:** present in synthetic rehearsal modes; ordinary Docker E2E is real-stack but comparatively shallow.
5. **Synthetic adapters:** material for payment, disbursement, messaging, and much file lifecycle work.
6. **Text-only migration tests:** not a fair suite-wide finding; sampled `0036` is fully executable. Chain-level consistency remains unproven.
7. **Fake concurrency:** not a fair suite-wide finding; important money/privacy/recovery races are genuine PostgreSQL concurrency.
8. **Implementation-coupled assertions:** present in auth timing proxies, configuration identity, YAML/source inspection, and frontend server-only substitution.
9. **Missing tenant/RBAC negatives:** not absent, but incomplete and not systematically generated across the full API surface.
10. **Missing crash/retry windows:** strong local retry evidence; real process-kill and external-side-effect ambiguity still missing.
11. **Money without settlement finality:** yes. Internal money authority is strong; bank/provider finality is not evidenced.
12. **Privacy without adversarial differencing:** no. Meaningful adversarial differencing tests exist; broader composition attacks remain.
13. **PWA without reload/network loss:** no. Those scenarios are extensively modeled; real-device and operating-system evidence remains.
14. **Snapshots masking drift:** not a leading observed risk. Synthetic authority and implementation coupling are more significant.
15. **Timing/timezone assumptions:** some fragile wall-clock testing exists; exact Lagos-day and clock-skew evidence should be strengthened.
16. **DONE supported by narrow checks:** partially. Documentation often scopes external gaps honestly, but immutable exact-SHA proof is absent.
17. **High-risk behavior without executable evidence:** real provider finality, physical-device behavior, broad privacy composition, and some deployment/runtime boundaries.
18. **Red/green evidence quality:** structurally promising, but weak at the audited-revision level because no GitHub run/status is attached.

---

# Final audit judgment

The suite is credible evidence that Cardvert’s authors have implemented and tested many difficult invariants deliberately. In particular, its PostgreSQL race tests, privacy differencing controls, payout state machine, offline queue semantics, and sampled migration procedure deserve substantial weight.

It should **not** yet be represented as proving production readiness or financial settlement safety. The minimum conditions for raising the verdict are:

1. an immutable, exact-SHA release workflow with fail-on-skip semantics;
2. critical tests run against Alembic-created PostgreSQL/PostGIS schemas;
3. mutation-capable browser journeys against the real API rather than only mock authority;
4. provider certification for ambiguous-response and idempotency windows;
5. independent settlement reconciliation;
6. physical-device offline/reload/process-death evidence;
7. systematic tenant/RBAC negatives;
8. expanded multi-query privacy attack testing.

Until those exist, the accurate claim is:

> **Strong provider-neutral and application-invariant evidence, with material staging and live-boundary evidence still outstanding.**

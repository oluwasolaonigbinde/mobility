# Dependency-safe remediation order

## Status and authority

This is a planning artifact derived only from the admitted
`consolidated-findings.md`, `high-risk-verification.md`, and
`product-release-verification.md` registers. All 14 audit sources are complete.
The raw allegations remain historical source-snapshot claims; the truth and
action fields below are current-source conclusions pinned to
`38094d605830ccce111bcb0773ec1a249fed2d58` and must be drift-checked before
later implementation.

The register contains 86 executable `FIX` candidates and 29 deliberately
non-executable candidates: 9 `DEFER`, 12 `OWNER DECISION`, and 8 `EXTERNAL
INPUT`. Repository implementation remains subject to the executable package
queue in `docs/progress.md`; this file neither authorizes work nor changes that
queue. Each admitted slice must use `$verified-feature-delivery`, unless a
later reviewed amendment establishes an isolated subprogram suitable for
`$orchestrated-feature-delivery`.

## Execution and review contract

Every executable slice has three mandatory gates:

- **P** — independent plan review of the exact slice contract, paths, risk, and
  verification before editing.
- **M** — clean-context minimal-change review of the integrated diff and its
  evidence before the slice is admitted.
- **CP-…** — consolidated post-build review at the named domain checkpoint;
  downstream cross-domain dependants remain closed until that checkpoint
  passes.

Model gates are **T/H** (GPT-5.6 Terra/high for ordinary bounded work), **S/H**
(GPT-5.6 Sol/high for security, privacy, money, migrations, concurrency,
native/offline, or deployment), and **S/XH** (GPT-5.6 Sol/xhigh for critical
cross-boundary cash or authority state machines). Specialist codes are **DB**,
**MNY**, **SEC**, **PRV**, **OFF**, **DEP**, and **CONTRACT**. A specialist review
supplements P/M and the consolidated checkpoint only when it examines a
distinct risk. A plan or integrated-diff review may satisfy an equivalent
package or selected-delivery gate when it covers the same unchanged contract
or diff, evidence set, and risk class. `CP-*` is one consolidated
domain/integration checkpoint, not a repeat of every slice review. This does
not collapse the distinct pre-edit plan review, integrated-diff review, or a
genuinely broader money, privacy, security, migration, concurrency, offline,
or deployment checkpoint.

For every verification contract below, **I** is intended behavior, **B** is a
break case that must fail safely, and **U** is behavior that must remain
unchanged. Behavioral test changes require red/green evidence. PostgreSQL,
provider, deployed-interface, physical-device, and live-system claims require
the named environment; a mock or static check cannot substitute for it.

## Primary disposition register — FIX

This is the authoritative one-to-one assignment of every `FIX` candidate to
exactly one cohesive implementation slice.

| Slice | Candidate IDs | Cohesive outcome |
| --- | --- | --- |
| R01 | GOV-001 | Truthful controller terminal state |
| R02 | GOV-003, TST-001, DB-005 | Mandatory CI selection and real integration authority |
| R03 | GOV-004 | Runtime-to-snapshot OpenAPI authority |
| R04 | DB-004 | Clean ORM/migration schema authority |
| R05 | DB-001, TST-012, ONB-010 | Savepoint-safe real-driver conflict translation |
| R06 | DB-002 | Governed downgrade refusal |
| R07 | DB-003 | Database-enforced purge-audit immutability |
| R08 | GOV-005 | Canonical locked active-admin authority |
| R09 | GOV-007, AUT-001, AUT-002 | Reusable authentication commands and containment races |
| R10 | AUT-005 | Strict bearer claim contract |
| R11 | AUT-004 | Durable logout and refresh fencing |
| R12 | AUT-003, REL-003 | Fail-closed rate limiting and dependency readiness |
| R13 | SEC-001, PRV-008 | Central sensitive-data redaction before logs/audit persistence |
| R14 | SEC-002, TST-004 | Deployed edge and browser trust-boundary proof |
| R15 | GOV-006 | Service-owned email delivery state machine |
| R16 | GOV-008 | Ad-platform port/adapter boundary |
| R17 | TST-007 | Enforced backend/frontend coverage floors |
| R18 | MON-005, MON-006 | Frozen currency and schema-immutable money authority |
| R19 | MON-002 | Canonical chronological daily-cap allocation |
| R20 | MON-001, DB-007, MON-008 | Durable per-line payout submission without lock-held I/O or resolved-line replay |
| R21 | MON-003 | Final fraud/assessment gate before provider invocation |
| R22 | MON-004, MON-007, MON-009 | Coherent failure, reservation, fraud-resolution, debt, and balance states |
| R23 | COM-001, COM-004 | Frozen refund eligibility and settlement |
| R24 | COM-002 | Resume-epoch budget evaluation |
| R25 | COM-003, COM-005 | Canonical commercial acceptance evidence |
| R26 | COM-006 | Invoice correction lock authority |
| R27 | COM-007 | Lagos-year invoice numbering |
| R28 | CAM-001 | Reachable campaign schedule/activation lifecycle |
| R29 | CAM-002 | One active assignment per driver |
| R30 | CAM-003 | Challenge finality across assignment deactivation |
| R31 | CAM-004 | Frozen assignment window aligned with trip start and payout |
| R32 | ONB-002 | Terminal driver-application lifecycle |
| R33 | ONB-006 | Bounded approval-evidence queries |
| R34 | OFF-001 | Content-bound offline upload/seal manifest |
| R35 | OFF-002, OFF-003 | Durable queue recovery and truthful capture acknowledgement |
| R36 | OFF-005 | Partial acceptance for mixed-validity ping batches |
| R37 | OFF-006 | Final evidence drain after assignment deactivation |
| R38 | PRV-001, PRV-002 | Legal/privacy gate before GPS and KYC collection |
| R39 | PRV-003 | Aggregate-only advertiser trip reporting |
| R40 | PRV-004, AUD-001, AUD-002 | Governed audience buckets, approvals, and immutable delivery inputs |
| R41 | PRV-009, AUD-004, TST-010 | Cross-output disclosure history and composition resistance |
| R42 | PRV-005, PRV-006 | Complete DSR inventory and truthful external-erasure semantics |
| R43 | PRV-007 | Durable external-object deletion authority |
| R44 | AUD-005 | Stable browser operation keys for planning-source mutations |
| R45 | MET-003 | Versioned traffic-density provenance |
| R46 | REP-001 | One frozen cohort/time-boundary authority |
| R47 | MET-001, MET-002, MET-004, REP-002 | Frozen methodology, caveat, completeness, and ROI disclosure |
| R48 | REP-003 | One cross-format report projection |
| R49 | REP-004 | Bounded report-worker lease attempts |
| R50 | REP-005 | Reachable report reissue lineage |
| R51 | REP-006 | Atomic or recoverable report-artifact publication |
| R52 | MET-006 | Contract-derived advertiser copy guard |
| R53 | REL-005 | Immutable frontend basemap build contract |
| R54 | REL-006 | Complete fail-closed environment templates |
| R55 | REL-004 | Mechanically generated rollback/report compatibility evidence |
| R56 | TST-005 | Generated RBAC/tenant denial matrix |
| R57 | TST-008 | Injected-clock boundary evidence |
| R58 | TST-011 | Real worker termination and convergence harness |
| R59 | TST-002 | Mutating real-stack browser release journey |
| R60 | GOV-009 | Final architecture, route, and migration current-state sync |

## Dependency graph and parallel-safe scheduling

The graph is authoritative; the numbered slices are stable identifiers, not a
license to execute in numeric order. Same-lane arrows below are serialization
edges for shared write surfaces. A ready slice may run with one ready slice from
each other lane unless a cross-lane edge below applies. Repository policy still
defaults to at most two active writers; more requires a recorded disjoint-work
justification.

| Lane | Required serial order |
| --- | --- |
| Control/contract | R01 → R02 → R03 → R17 → R60 |
| Database/money schema | R04 → R05 → R06 → R07 → R18 → R19 |
| Authentication/security | R08 → R10 → R09 → R11 → R12 → R14 → R56 |
| Sensitive metadata | R13 |
| Worker architecture/evidence | R15 → R58 |
| Provider boundary | R16 → R44 |
| Payout execution | R20 → R21 → R22 |
| Commercial money | R23 → R24 → R25 → R26 → R27 |
| Campaign lifecycle | R28 → R29 → R30 → R31 |
| Onboarding | R32 → R33 |
| Offline protocol | R34 → R35 → R36 → R37 |
| Privacy/audience | R38 → R39 → R40 → R41 → R42 → R43 |
| Measurement/reporting | R45 → R46 → R47 → R48 → R49 → R50 → R51 → R52 |
| Release/integration evidence | R53 → R54 → R55 → R57 → R59 |

Cross-lane dependency edges are:

| Dependant | Must follow | Reason |
| --- | --- | --- |
| R02 | R04 | The mandatory migrated-schema/ORM CI authority consumes the clean canonical exact-head result and shared real-database fixture owned by R04. |
| R05–R07 | R02, R04 | Real migrated PostgreSQL authority precedes driver/downgrade/trigger proof. |
| R33 | R05 | Vehicle-onboarding conflict translation and evidence-query work share onboarding service surfaces. |
| R17 | R02, R03 | Coverage is added only after CI and contract job selection are authoritative. |
| R18 | R04, R06, R07 | Money-schema changes build on clean metadata and evidence-preserving migrations. |
| R20 | R05, R18 | Submission redesign uses safe conflict translation and settled money schema. |
| R21 | R20 | The final fraud gate attaches to the durable submission boundary. |
| R22 | R20, R21 | Failure/reservation/debt states follow stable submission and fraud transitions. |
| R23–R27 | R08 | Billing writes use the canonical locked active-admin authority first. |
| R29 | R04, R08, R28 | Driver uniqueness needs schema authority, canonical admin checks, and reachable lifecycle. |
| R30 | R29 | Challenge/deactivation semantics follow the final active-assignment invariant. |
| R31 | R18, R19, R30 | Work-window alignment uses frozen money terms and canonical cap ordering. |
| R34 | R04 | Manifest schema begins from clean migration authority. |
| R38 | R13 | New collection gates must not persist sensitive audit/log metadata. |
| R40 | R16, R39 | Governed delivery follows adapter separation and aggregate advertiser output. |
| R41 | R40 | Composition history covers the final audience/disclosure contract. |
| R43 | R42 | Destruction uses the complete DSR location/inventory model. |
| R44 | R40 | Browser idempotency targets the settled planning-source/delivery contract. |
| R45 | R04, R41 | Versioned measurement provenance follows schema and privacy authority. |
| R46 | R45 | Cohort snapshots bind the final provenance identity. |
| R47 | R41, R46 | Method disclosure uses privacy-safe, cohort-consistent frozen inputs. |
| R49–R50 | R47 | Worker/reissue states use the final issuance snapshot contract. |
| R51 | R43, R49 | Report publication follows durable object lifecycle and bounded claims. |
| R54 | R12, R16, R53 | Templates express settled readiness, adapter, and frontend build contracts. |
| R55 | R03, R18, R48, R51, R54 | Compatibility proof consumes final API, schema, report, artifact, and config contracts. |
| R56 | R09, R11, R40 | Denial matrix targets final auth/session/tenant-aware audience behavior. |
| R57 | R19, R27, R49, R55 | Clock tests cover final Lagos, worker, provider, and release boundaries. |
| R58 | R20, R21, R43, R49, R51 | Kill/restart proof targets the final external-effect worker state machines. |
| R59 | R22, R31, R33, R37, R41, R44, R48, R50, R51, R56–R58 | Real-stack journey is the integrated behavioral gate, not an early scaffold. |
| R60 | R03, R18, R22, R27, R31, R33, R37, R43, R44, R52, R55, R56, R59 | Current-state documentation follows every route/schema/placement-affecting slice. |

Parallel-safe launch groups, subject to the two-writer cap and the edges above,
are:

1. Initial independent fronts: `R01`, `R04`, `R08`, `R13`, `R15`, `R16`,
   `R28`, `R32`, and `R53`.
2. After the relevant initial front clears: `R02`, `R10`, `R23`, `R29`,
   `R34`, and `R38`.
3. Middle independent fronts: one ready slice from each of the database,
   authentication, payout, commercial, campaign, onboarding, offline,
   privacy, measurement, and release lanes.
4. Convergence group: `R52` and `R58` may run together after their own edges;
   `R55`, `R57`, `R59`, and `R60` then close sequentially as specified.

The scheduler must backfill a released slot with the highest-priority ready,
non-conflicting slice; these groups are compatibility explanations, not batch
barriers. Any discovered shared migration, generated contract, route registry,
central fixture, or package-manifest write adds an exclusive lease and requires
a reviewed graph amendment before editing.

## Executable slice contracts

### Control, database, authentication, and security

| Slice | Candidate write surfaces grounded in verification | Focused verification contract | Gate and reviews |
| --- | --- | --- | --- |
| R01 | `docs/progress.md`; `scripts/validate_progress.py`; validator tests | I: `COMPLETE` means all packages/items complete. B: blocked or external-gated state cannot pass as complete. U: registered paused/external states remain representable. | T/H; P/M; CP-CONTROL |
| R02 | `.github/workflows/ci.yml`; `tests/conftest.py`; `tests/test_kyc_local_integration.py`; migration/integration job config | I: every relevant branch/path runs required PostgreSQL/PostGIS, Redis, MinIO/ClamAV jobs. B: omitted root paths or unexpected skips fail exact-SHA evidence. U: fast local tests remain available but non-authoritative. | S/H; P/M; DB+DEP; CP-CONTROL |
| R03 | `.github/workflows/ci.yml`; `tests/test_openapi.py`; `scripts/update_openapi_snapshot.py`; OpenAPI snapshots; `frontend/package.json` | I: runtime FastAPI schema, both JSON snapshots, and TypeScript agree. B: runtime-only schema change fails. U: deterministic regeneration still produces stable artifacts. | T/H; P/M; CONTRACT; CP-CONTROL |
| R04 | ORM models; Alembic revisions; `tests/test_migration_0014_partitioning.py` | I: exact-head autogenerate diff is empty with types/defaults enabled. B: any unowned index/constraint/type/default drift fails without allowlist. U: intentional partition ownership remains explicit. | S/H; P/M; DB; CP-DB |
| R05 | `app/services/trips.py`; `app/services/disbursements.py`; `app/services/vehicle_onboarding.py`; `app/db/integrity.py`; integrity/concurrency tests | I: expected conflicts roll back only a savepoint and translate real asyncpg names, including concurrent applicant plate submission. B: losing races preserve outer writes; unexpected constraints escape. U: public conflict envelopes remain stable. | S/XH; P/M; DB+MNY; CP-DB |
| R06 | Alembic revisions `0010`, `0014`, `0016`; payout downgrade-guard tests | I: populated governed evidence refuses exact destructive downgrades transactionally. B: rows/head survive every refusal. U: empty-database downgrade/re-upgrade remains possible. | S/XH; P/M; DB+MNY+PRV; CP-DB |
| R07 | purge model/migration, especially revision `0014`; PostgreSQL catalog tests | I: database rejects purge-audit update/delete/truncate paths. B: privileged raw mutations fail. U: valid append inserts and reads remain supported. | S/H; P/M; DB+PRV; CP-DB |
| R08 | `app/services/admin_authorization.py`; `billing.py`; `campaign_assignments.py`; `heatmaps.py`; audience services | I: all active-admin writes share one locked authority and error envelope. B: concurrent disable always wins safely. U: authorized active-admin outcomes stay unchanged. | S/H; P/M; SEC; CP-SECURITY |
| R09 | `app/services/auth.py`; `app/api/v1/auth.py`; `app/services/account_recovery.py`; `app/services/users.py` | I: reusable commands own login/password/reset/containment rules under row/version fencing. B: change-vs-reset and suspend-vs-reset races permit no stale credential win. U: valid login/reset responses and audit semantics remain stable. | S/XH; P/M; SEC+DB; CP-SECURITY |
| R10 | `app/core/security.py`; `app/api/v1/dependencies.py`; auth tests | I: protected routes require well-formed expiry, issued/auth times, and session version. B: missing/null/malformed/boundary claims deny. U: valid current tokens continue to authenticate. | S/H; P/M; SEC; CP-SECURITY |
| R11 | frontend auth actions/session/proxy; backend auth refresh/revoke command | I: logout durably revokes and late refresh cannot restore a session. B: copied bearer and ordered refresh/logout race deny. U: ordinary refresh and multi-tab sign-out remain usable. | S/XH; P/M; SEC; CP-SECURITY |
| R12 | `app/core/rate_limit.py`; `app/api/v1/health.py`; configuration/Compose and readiness tests | I: production throttling and every mandatory dependency participate in readiness. B: missing/malformed Redis, wrong schema, worker/storage/scanner failure degrades before login admission. U: healthy development/test profiles retain declared optionality. | S/H; P/M; SEC+DEP; CP-SECURITY |
| R13 | `app/core/observability.py`; `app/services/audit.py`; audit callers including `app/api/v1/admin.py` | I: common and nested PII is rejected/redacted before logs, Sentry, DB, API, or export. B: sensitive-key/value corpus cannot persist. U: non-sensitive diagnostic metadata remains searchable. | S/H; P/M; SEC+PRV; CP-PRIVACY |
| R14 | `Caddyfile`; `frontend/next.config.ts`; `frontend/vitest.config.ts`; deployed-interface security tests | I: built edge enforces CSP, framing, permissions, origin/host, cookie, and server-only boundaries. B: forged host/origin/trusted-IP and framing attempts fail. U: valid API/frontend/redirect/error responses remain reachable. | S/H; P/M; SEC+DEP; CP-SECURITY |
| R15 | `app/jobs/email_delivery.py`; `app/jobs/worker.py`; messaging services/adapters; worker tests | I: service owns eligibility, secrets, retry, and terminal transitions; job selects IDs and delegates. B: crash/retry cannot duplicate or bypass eligibility. U: current successful delivery state and templates remain equivalent. | T/H; P/M; CP-WORKERS |
| R16 | `app/services/audience_delivery.py`; `app/api/v1/dependencies.py`; `app/adapters/ad_platforms/` boundary/tests | I: domain depends on a port and composition selects disabled/fake adapters outside the service. B: forbidden inward imports fail. U: disabled and synthetic behavior remains unchanged. | T/H; P/M; CONTRACT; CP-CONTROL |
| R17 | `.github/workflows/ci.yml`; backend coverage config; `frontend/vitest.config.ts`; coverage tests | I: agreed critical-module and changed-code floors are enforced. B: deliberate coverage removal fails. U: exclusions remain explicit and generated/vendor code is not mis-scored. | T/H; P/M; CP-CONTROL |

### Money, commercial, campaign, onboarding, and offline

| Slice | Candidate write surfaces grounded in verification | Focused verification contract | Gate and reviews |
| --- | --- | --- | --- |
| R18 | payout models/services; payout migrations including `0010`; correction/ledger tests | I: currency is frozen in revision/offer/binding and economic authority is schema-immutable. B: privileged mutation, parent delete, or currency drift cannot reprice history. U: enumerated status transitions and append-only corrections still work. | S/XH; P/M; DB+MNY; CP-MONEY |
| R19 | `app/services/payouts.py`; `app/services/trip_processing.py`; payout-v3 concurrency tests | I: shared day cap always follows `(started_at, id)`. B: later higher/lower-rate trip entering first cannot win economically. U: cap ceiling, Lagos split, rounding, and exact retry remain unchanged. | S/XH; P/M; DB+MNY; CP-MONEY |
| R20 | `app/services/disbursements.py`; disbursement models/migrations; adapter/outbox worker; payout reconciliation tests | I: immutable per-line intent precedes external I/O, locks are released, ambiguous outcomes query before resend, and only unresolved lines submit. B: kill after acceptance, partial replay, timeout, and duplicate key converge to one effect. U: frozen instruction/idempotency and succeeded finality remain intact. | S/XH; P/M; DB+MNY; CP-MONEY |
| R21 | disbursement submission/approval; fraud holds; earnings release; final-gate tests | I: current assessment and hold state are rechecked under stable locks immediately before provider claim/invocation. B: intervening hold or fingerprint drift causes zero adapter calls. U: unaffected frozen batches still submit once. | S/XH; P/M; DB+MNY+SEC; CP-MONEY |
| R22 | disbursement model/service; `app/services/payout_debt.py`; fraud confirmation; balance schemas | I: terminal, unknown, reserved, paid, debt, and replacement states reconcile truthfully. B: failure cannot strand credit, abort authoritative fraud, inflate batch-payable, or turn late success into an ordinary second payment. U: paid finality and conservation remain unchanged. | S/XH; P/M; DB+MNY; CP-MONEY |
| R23 | `app/services/billing.py`; refund/cancellation tests | I: refund cutoff freezes at the authoritative obligation/cancellation event. B: later debit note, production start, or wall-clock expiry cannot reopen/erase entitlement. U: exact settlement retry remains idempotent. | S/H; P/M; MNY; CP-COMMERCIAL |
| R24 | `app/services/billing.py`; budget transition/notification tests | I: resume creates a new evaluation epoch. B: old idempotency key cannot mask a new threshold breach. U: exact retry within one epoch converges without duplicate notification. | S/H; P/M; MNY; CP-COMMERCIAL |
| R25 | `app/services/billing.py`; canonical waiver registry/UI contract; quotation/waiver tests | I: only latest quotation and approved versioned waiver copy can bind. B: superseded quote or caller-mutated text/hash conflicts. U: latest/exact retry preserves immutable evidence. | S/H; P/M; MNY+CONTRACT; CP-COMMERCIAL |
| R26 | `app/services/billing.py`; invoice allocation/correction concurrency tests | I: correction and allocation share campaign/invoice lock order. B: PostgreSQL overlap cannot overfund or deadlock. U: non-overlapping correction results remain unchanged. | S/XH; P/M; DB+MNY; CP-COMMERCIAL |
| R27 | `app/services/billing.py`; invoice sequencing tests | I: invoice year uses Lagos civil time. B: 31-Dec 23:00 UTC boundary cannot enter the wrong sequence. U: numbering uniqueness and ordinary dates remain stable. | S/H; P/M; MNY; CP-COMMERCIAL |
| R28 | `app/services/campaigns.py`; campaign API/status tests | I: API-created campaign can schedule and activate through governed transitions. B: invalid/out-of-order transitions deny. U: review approval/rejection semantics remain stable. | T/H; P/M; CP-CAMPAIGN |
| R29 | assignment models/migrations; `app/services/campaign_assignments.py`; `app/db/integrity.py` | I: one active assignment per driver is database/service enforced. B: two-vehicle concurrent activation yields one stable conflict, never later 500. U: sequential deactivate/reactivate remains supported. | S/H; P/M; DB; CP-CAMPAIGN |
| R30 | campaign assignments; evidence-verification job/service; earnings release tests | I: outstanding challenge survives self-deactivation to expiry and hold. B: deactivate-before-sweep cannot evade fraud consequence. U: satisfied/cancelled challenge rules stay intact. | S/H; P/M; SEC+MNY; CP-CAMPAIGN |
| R31 | `app/services/trips.py`; payout binding/calculation services; campaign-change tests | I: post-binding-end work is rejected or explicitly rebound before capture. B: campaign extension cannot create zero-value accepted work. U: valid in-window trips and approved rebinds remain payable. | S/XH; P/M; MNY; CP-CAMPAIGN |
| R32 | driver-application model/migration/service; admin queue; access-token tests | I: complete review reaches terminal state, leaves queue, and invalidates mutation tokens. B: rejected/approved applicant cannot renew or mutate. U: pending applicant workflow remains functional. | S/H; P/M; SEC+DB; CP-ONBOARDING |
| R33 | driver/vehicle onboarding services; audit indexes/migrations; query-plan tests | I: approvals use bounded indexed evidence lookup. B: large actor history cannot create unbounded load. U: evidence selection and approval decisions remain identical. | T/H; P/M; DB; CP-ONBOARDING |
| R34 | trip models/migrations; `app/services/trips.py`; `app/services/trip_processing.py`; client protocol | I: signed/content-bound manifest governs completeness and sealing. B: under/over-count, omission, reorder, duplicate, false complete, and grace expiry cannot make unresolved evidence payable. U: valid complete trips still seal. | S/XH; P/M; DB+OFF+MNY; CP-OFFLINE |
| R35 | `frontend/src/lib/trips/ping-queue.ts`; trip tracker; queue/recovery tests | I: deadletter-only trips recover visibly and UI acknowledges only durable capture. B: key loss, quota, corruption, abort, and abrupt close expose gaps without blind resend. U: healthy encrypted queue/reload behavior remains intact. | S/H; P/M; OFF+SEC; CP-OFFLINE |
| R36 | `app/services/trips.py`; trip tracker response classification; API/queue tests | I: valid pings in a mixed batch commit while rejected identities/reasons remain durable. B: one skewed sample cannot deadletter valid peers. U: fully valid and fully invalid batch semantics stay deterministic. | S/H; P/M; DB+OFF; CP-OFFLINE |
| R37 | trip ingest/end service; trip tracker drain/end flow; deactivation tests | I: already captured evidence remains uploadable after assignment deactivation under ended-policy authority. B: reconnect/deactivate/end cannot terminally deadletter valid queued evidence. U: new capture still respects active-assignment eligibility. | S/H; P/M; OFF+MNY; CP-OFFLINE |

### Privacy, audience, measurement, reporting, and release

| Slice | Candidate write surfaces grounded in verification | Focused verification contract | Gate and reviews |
| --- | --- | --- | --- |
| R38 | trip/ping and KYC services/routes; privacy configuration/gate; audit tests | I: legal/privacy authority is checked before real GPS or KYC side effects. B: disabled gate produces no DB, object, encryption, or audit write. U: explicitly synthetic test authority remains available. | S/XH; P/M; PRV+SEC; CP-PRIVACY |
| R39 | report schemas/service and advertiser campaign-trip route/UI | I: advertiser output is approved aggregate only. B: one/small cohort cannot expose stable row IDs or exact event timestamps. U: authorized aggregate analytics remain usable. | S/H; P/M; PRV; CP-PRIVACY |
| R40 | exposure/delivery schemas; audience delivery/disclosure services; approval models; adapter composition | I: canonical spatial/time buckets and complete purpose/legal approval bind authoritative recomputation and immutable delivery. B: micro-buckets, stale/tampered counts, wrong/expired approval, provider/segment mismatch deny. U: valid synthetic/disabled flows remain deterministic. | S/XH; P/M; PRV+SEC+CONTRACT; CP-PRIVACY |
| R41 | disclosure, audience, reports and measurement services; disclosure-history schema; generated attack tests | I: every governed output shares floors/caps/history across principals, tenants, endpoints, and time. B: overlapping/complementary multi-query campaigns cannot reconstruct suppressed cohorts. U: non-overlapping sufficiently large outputs remain available. | S/XH; P/M; PRV+DB; CP-PRIVACY |
| R42 | `app/services/data_subject_requests.py`; subject-link registry/model tests | I: all subject-linked data is inventoried and nonzero external erasure cannot be called erased. B: omitted recovery/contact rows or false completion fail. U: `not_found` and approved retention exceptions remain explicit. | S/H; P/M; PRV; CP-PRIVACY |
| R43 | `app/services/file_kyc_lifecycle.py`; `app/services/stored_files.py`; durable deletion intent/receipt model/worker | I: external deletion is recoverable from durable authority. B: kill after delete/before commit cannot leave DB falsely claiming presence or completion. U: successful purge evidence and idempotent cleanup remain intact. | S/XH; P/M; PRV+DB; CP-PRIVACY |
| R44 | planning-source frontend actions and related API idempotency tests | I: one user operation retains one key across response-loss retries. B: commit/response loss cannot create a second mutation. U: distinct user actions receive distinct keys. | T/H; P/M; CP-PRIVACY |
| R45 | traffic-density model/migration; impression/measurement services; provenance tests | I: density values are versioned/effective and fingerprints bind the value/version. B: profile edit stales dependants without rewriting old output. U: historical frozen output remains reproducible. | S/H; P/M; DB+PRV; CP-REPORTING |
| R46 | measurement/report services; report snapshot schemas/tests | I: screen and frozen outputs share one cohort and half-open time authority. B: delayed impression, replacement payout, or end-boundary event cannot diverge. U: existing valid period semantics remain stable. | S/H; P/M; MNY+PRV; CP-REPORTING |
| R47 | methodology JSON; measurement/reports/issuance services and schemas; advertiser UI | I: frozen outputs carry caveats, completeness/denominator, parameter provenance, and full ROI method. B: insufficient data or absent authority suppresses headline/ROI consistently. U: qualified values and exact wording remain unchanged. | S/H; P/M; PRV+CONTRACT; CP-REPORTING |
| R48 | report projection/rendering and advertiser report UI | I: screen, CSV, and PDF render one typed projection with Unicode, timezone, rounding, hash, uncertainty, and currency parity. B: field-by-field diff catches omission/substitution. U: valid downloads and deterministic hashes remain stable. | T/H; P/M; CONTRACT; CP-REPORTING |
| R49 | report issuance claim/reclaim/failure service and worker tests | I: attempt ceiling includes expired leases. B: crash on final claim terminalizes rather than creating attempt four. U: earlier retryable claims and successful completion remain unchanged. | S/H; P/M; DB; CP-REPORTING |
| R50 | report issuance request/status service and panel | I: changed authority/requester exposes an unambiguous permitted parent and reissue path. B: hidden latest issuance cannot strand reissue. U: unchanged-authority exact replay remains idempotent. | S/H; P/M; PRV; CP-REPORTING |
| R51 | report issuance/rendering/storage; artifact model; orphan cleanup/recovery tests | I: CSV/PDF publication is atomic or durably recoverable. B: first-write failure or DB rollback leaves no unregistered private object. U: deterministic keys, private access, and successful issuance remain stable. | S/XH; P/M; DB+PRV; CP-REPORTING |
| R52 | `tests/test_measurement_methodology.py`; methodology JSON; advertiser/shared frontend sources | I: guard derives prohibited vocabulary from the contract across all reachable sources. B: case/word variants in shared components fail. U: approved caveated terminology passes. | T/H; P/M; CONTRACT; CP-REPORTING |
| R53 | `frontend/Dockerfile`; frontend map config; image provenance checks | I: configured basemap and provenance survive immutable image build. B: missing/changed build input fails inspection. U: default/test map behavior remains supported where declared. | T/H; P/M; DEP; CP-RELEASE |
| R54 | `staging.env.example`; `production.env.example`; Compose/config preflight | I: every live-critical setting is explicit and fail-closed. B: omission or placeholder cannot pass production preflight. U: documented local/test defaults remain separate. | S/H; P/M; DEP+SEC+PRV; CP-RELEASE |
| R55 | `scripts/release_contract.py`; rehearsal/recovery scripts; compatibility receipts | I: previous-image/forward-schema and report canaries generate signed/hash-bound evidence. B: hand-authored booleans or stale receipts fail. U: valid mechanically generated evidence remains reusable for its exact SHA. | S/XH; P/M; DEP+DB+CONTRACT; CP-RELEASE |
| R56 | generated authorization-denial tests; route/audit inventory; tenant/resource fixtures | I: every role × tenant × resource × action has classified allow/deny evidence. B: guessed/nested IDs, files/jobs/exports, stale membership cannot cross scope. U: intended role capabilities remain allowed. | S/H; P/M; SEC; CP-SECURITY |
| R57 | injected clock utilities; auth/job/payment/report tests | I: exact expiry, Lagos midnight, clock jumps, and provider timestamps are deterministic. B: ±1 microsecond, late/future/replayed events fail correctly without sleeps. U: ordinary time behavior remains unchanged. | S/H; P/M; MNY+SEC+DEP; CP-RELEASE |
| R58 | real Redis/broker/PostgreSQL worker harness; earnings, payout, deletion, and report job tests | I: kill/restart at claim, effect, commit, ACK, cursor, dead-letter, and sweep converges. B: no cut point duplicates an effect or strands work. U: normal workers retain throughput/idempotency. | S/XH; P/M; DB+MNY+PRV; CP-WORKERS |
| R59 | Playwright real-stack config/journeys; seeded API/DB/workers | I: a mutating browser journey proves persisted outcomes across reload and worker processing. B: injected API/worker failure recovers without mock authority. U: mock rehearsals remain clearly labelled UI-only. | S/XH; P/M; SEC+DB+DEP; CP-RELEASE |
| R60 | `docs/architecture.md`; routed operation inventory; Alembic head/count evidence | I: current-state maps match final routes, feature placement, and migration head. B: generated inventory drift fails validation. U: historical/design sections remain unchanged unless genuinely amended. | T/H; P/M; CONTRACT; CP-CONTROL |

## Primary disposition register — DEFER

These rows are non-executable. A trigger creates a newly reviewed slice; it
does not silently promote the row into the FIX graph.

| ID | Why deferred | Evidence/activation trigger |
| --- | --- | --- |
| AUD-003 | Live ad-platform construction is disabled, so the provider-call durability gap is latent. | Before any live adapter: approved prepared/unknown state plus kill-after-acceptance and semantic-idempotency evidence. |
| CAM-005 | Locked campaign state currently makes the selector asymmetry unreachable. | Reproduce a double bind or change review-state reachability; then add undecided-event proof. |
| MET-005 | Defaults keep live report issuance off. | Before enabling both live flags, prove one shared approval predicate rejects `EXT-*` and mismatches everywhere. |
| MET-007 | Parent selection is inconsistent but no current harmful outcome is established. | Demonstrate consecutive-period lineage harm or approve lineage hardening, then verify same-period-only parentage. |
| OFF-004 | Safe behavior depends on the supported browser/device contract. | Approve the support matrix or reproduce lock loss on a supported target; define recovery/end behavior. |
| OFF-007 | Late quarantine creates an operational correction obligation, not an automatic defect under the current contract. | Approve automatic correction or an enforceable SLA/alert, then prove no silent omitted recompute. |
| OFF-009 | Background continuity is explicitly out of web-PWA scope. | Approve native/background authority and obtain physical-device battery/permission/eviction evidence. |
| ONB-001 | Timing asymmetry is plausible but was not measured. | Supply deployed warm-cache latency distributions establishing distinguishability before padding/fixed work. |
| ONB-007 | Candidate-list staleness is presentation-only because the write gate rejects expired approval. | Reproduce a bypass or approve stale-list hardening; retain write-gate denial evidence. |

## Primary disposition register — OWNER DECISION

These rows are non-executable until the named owner policy is recorded. The
decision must define behavior, migration/legacy treatment, and verification.

| ID | Required owner decision |
| --- | --- |
| AUD-006 | Which campaign lifecycle states may be linked to planning sources, including historical analysis. |
| AUT-006 | Whether privilege elevation requires reauthentication, session rotation, or immediate live-role adoption. |
| AUT-007 | Whether multi-tenant users select an explicit tenant or are limited to one active membership. |
| COM-008 | Whether corporate-credit and driver-liability authority may exceed accepted campaign obligation only under a separately approved facility; whether recorder and approver may be the same administrator; and the legacy, retry, concurrency, and immutable-audit rules. |
| OFF-008 | Whether ambiguous End favors duplicate-safe resend or continued capture, and how sequence gaps are represented. |
| ONB-003 | Whether duplicate NIN, normalized phone, or bank account is forbidden, review-only, or exception-based. |
| ONB-004 | Maximum vehicle-approval horizon and its relationship to document expiry and renewal. |
| ONB-005 | Maker-checker separation across payee verification, person approval, and vehicle approval. |
| ONB-008 | Global registration abuse threshold, availability tradeoff, and alerting policy. |
| ONB-009 | Who activates an approved user's account and how the initial credential/session is issued. |
| REL-007 | Bundled-only versus managed database/Redis topology, including TLS/auth/hostname rules. |
| REP-007 | Lawful report retention, withdrawal/tombstone, backup treatment, and presigned-link TTL/revocation. |

## Primary disposition register — EXTERNAL INPUT

These rows are non-executable external gates. No live enablement or release
claim may infer the missing value or substitute a fake/local result.

| ID | Required external input/evidence |
| --- | --- |
| DB-006 | Production-version PostgreSQL/PostGIS target and representative size distribution for chain, lock, disk, and plan evidence. |
| GOV-002 | Immutable exact-SHA green CI/check evidence after the executable graph and required external jobs complete. |
| REL-001 | Selected payment, disbursement, and ad-platform providers/accounts/specifications plus sandbox contracts. |
| REL-002 | Selected production KMS/vault and custody/rotation/permission specification. |
| REL-008 | Approved backup owner, scope, cadence, protected destination, RPO/RTO, and isolated restore evidence. |
| TST-003 | Real provider sandbox/live-contract evidence for idempotency, ambiguous outcomes, callbacks, and reconciliation. |
| TST-006 | Physical Android/iPhone evidence for storage, lifecycle, permission, battery, network, and GPS boundaries. |
| TST-009 | Controlled low-value provider/bank settlement artifact proving accepted-versus-settled reconciliation. |

## Admission and closure rules

1. Verify each candidate against the then-current tree before implementing its
   slice. If a claim is false, record evidence and amend the disposition rather
   than implementing the audit's suggested fix.
2. Admit a slice only after its exact dependency and same-lane predecessors
   pass integration verification and the named domain checkpoint.
3. Serialize migrations, generated contracts, central route registries,
   package manifests, shared fixtures, and other newly discovered hot surfaces.
4. External and owner-decision rows never satisfy a live-enablement gate by
   omission. They remain visible release conditions even when all FIX slices
   pass.
5. Final closure requires all admitted FIX slices integrated, every P/M and
   specialist receipt present, all domain checkpoints green, `R59` and `R60`
   complete, the exact-SHA gate supplied, and one consolidated independent
   whole-program minimal-change review of integration seams.

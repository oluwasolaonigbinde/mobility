# Delivery Control — Intended MVP, Delivered Work, and Ordered Queue

**Start here before every task.** This is the operational control document for
delivery: it shows the endpoint, what exists, the sole authorised package, and
the ordered remainder. Agents update it in the same change as every landed
package. The proposal owns scope, architecture owns design, decisions-log owns
product decisions, and Git/test evidence proves delivery; **this file alone
controls which package may be executed next**. It replaces the status-summary
role of `project-reconciliation.md` (4 Aug 2026) and the work-selection role
previously implied by `next-steps.md` (10 Aug 2026).

The endpoint is the D11 proposal scope **as superseded by the direct client
answers and approvals in D18–D20**, designed in `docs/architecture.md`.
Somto's Q1–Q34 list and the client's later three-point clarification are the
newest product authority. Architecture §31 is roadmap context;
execution order and authorization live exclusively in this document.

**Package:** one owner-facing delivery/review cycle. **Checklist item:** one of
the 71 mandatory implementation obligations inside a package; it is never an
authorization unit. **Parent:** one of the 22 architecture traceability groups;
it is never executable. **Active slot:** the single package marked `NEXT`,
`IN PROGRESS`, or `REVIEW`.

## Execution lock

Package status is `QUEUED | NEXT | IN PROGRESS | REVIEW | DONE | BLOCKED`.
Checklist status is `TODO | DONE | BLOCKED — EXT-ID`; checklist items never use
package-active vocabulary. A package is `DONE` only when all its checklist items
are `DONE`. It is `BLOCKED` only when every non-DONE item is externally blocked
or transitively depends on blocked work and no runnable `TODO` remains.

The active package moves through `NEXT → IN PROGRESS → REVIEW → DONE`. Its
controller selects the current runnable checklist checkpoint, honors the
checklist dependency graph, and may use staged commits and parallel agents with
explicit disjoint ownership. Money, privacy, security, client-device, deployment and
other high-risk checkpoints receive specialist review before integration; one
consolidated independent package review closes the owner-facing cycle.

After all nine packages and all 71 checklist items are `DONE`, set
`Controller state` to `COMPLETE`, retain `PKG-09` as the final control package,
and retain `PKG-09 / W4-04B` as the terminal evidence pointer. This is the only
valid zero-active state other than an explicit external pause.

At promotion, scan packages in order. A blocked earlier package does not freeze
the program: promote the first later package containing a runnable checklist
item whose transitive checklist dependencies are `DONE`. Never use invented or
placeholder external values. Only an owner-recorded decision clears a checklist
external block. If the active package has no runnable item, mark it `BLOCKED`,
report every blocking `EXT-ID`, and either promote a dependency-safe later
package or set the controller `PAUSED — EXT-ID` only when no runnable `TODO`
exists anywhere. A pause ID must be registered `MISSING` and must directly or
transitively block the pointed package/checkpoint.

External prerequisites distinguish build-entry inputs from live-use gates in
their “exact effect” text. Only an external ID named in a checklist item's
prerequisite cell blocks building that item; launch facts and legal approvals
that gate live use do not prevent provider-neutral or synthetic implementation.

### Current control pointer

**Controller state:** `ACTIVE`
**Control package:** `PKG-06` — W3-03A is verified on the adopted corrected
Package 5 history and Package 6 remains in progress. Package 5 remains BLOCKED
only on its registered dependency/external gates.
**Current checkpoint:** `PKG-06 / W3-03B` — W3-03A is DONE. W3-03B is the next
dependency-safe pointer; it has not been admitted or started in this checkpoint.

## Executable package queue

| # | Package | Status | Outcome | Package prerequisites |
| ---: | --- | --- | --- | --- |
| 1 | **PKG-01 — foundations and empirical risk proof** | DONE | Resolve remaining foundations, production-PWA/staging risk and correction authority. | none |
| 2 | **PKG-02 — money integrity and payout operations** | DONE | Corrected release, pre-existing-reversal backfill and debt-aware economic/settlement authority agree. | none — checklist DAG gates entry |
| 3 | **PKG-03 — commercial contracts and billing** | BLOCKED | Synthetic/provider-neutral commercial flow is verified; live provider checkout and budget enforcement await their recorded external inputs. | none — checklist DAG gates entry |
| 4 | **PKG-04 — secure evidence, activation and communications** | **BLOCKED** | Campaign review and the shared in-app notification core are complete; storage/KYC/activation/provider communications await recorded external inputs and their transitive dependencies. | none — checklist DAG gates entry |
| 5 | **PKG-05 — privacy, measurement and retargeting** | **BLOCKED** | Privacy controls and reproducible measurement govern retargeting and advertiser insights. | none — checklist DAG gates entry |
| 6 | **PKG-06 — matching and driver onboarding** | **IN PROGRESS** | Recommendations, offers, activity and approved driver/vehicle onboarding work together. | none — checklist DAG gates entry |
| 7 | **PKG-07 — production driver PWA** | QUEUED | The pilot PWA safely tracks, syncs, explains earnings and supports release across the device matrix. | none — checklist DAG gates entry |
| 8 | **PKG-08 — governed reporting and pilot readiness** | QUEUED | Safe reports, release infrastructure and one complete pilot acceptance gate are ready. | none — checklist DAG gates entry |
| 9 | **PKG-09 — controlled pilot, training and handover** | QUEUED | Run the pilot, stabilize it, train roles and close operational handover. | none — checklist DAG gates entry |

## Executable package contracts

### PKG-01 — foundations and empirical risk proof

- **Owns:** checklist 1–9. D23 separates runnable build evidence from later
  real-world validation without weakening any real-GPS, release or pilot gate.
- **Closure:** production-PWA protocol and interrupted synthetic-flow build proof,
  provider-neutral production-like release/recovery proof, RM2/RM6/RM7
  corrections, required reviews and exact CI agree. Physical-device/route/
  battery and external-staging evidence remain explicitly incomplete post-build
  validation until their registered inputs and later pilot/release gates exist.
- **Package plan (activated 16 Aug 2026, canonical branch `feat/pkg-01`):**
  internal checkpoints under the controller's disjoint-ownership rule.
  Canonical/controller work: **FND-07** (first runnable checkpoint — integrity
  409 envelopes, RM7), R14-B device evidence after R14-A integrates, aggregate
  verification and every control/authority-document update. Delegated
  contributor branches (integrated only by the controller, never self-merged):
  `feat/pkg-01-pro-pwa-contract` → R14-A ADR/capability contract;
  `feat/pkg-01-pro-money` → MNY-06A/B/C chain. FND-02A is a prepared decision
  packet (parameterized options + executable fixtures + independent
  product/money review) resolved by D22's owner-selected synthetic Option A;
  `EXT-RM2-POLICY` is present and FND-02B implements it on the MNY-06 binding.
  R14-A/B and R17-A close only on their automated/synthetic build contracts;
  D23 records physical-device and external-staging execution as deferred,
  incomplete validation rather than fabricated evidence or a build blocker.
- **FND-07 evidence (DONE 16 Aug 2026):** candidate `58794a4` on
  `feat/pkg-01` (collateral model-drift fix `139bfcb`). Four exclusivity
  constraint names registered in the `app/db/integrity.py` classifier; lost
  races at assignment create/activate and trip start translate to the same
  stable 409 codes as their pre-checks; unrelated integrity failures re-raise.
  Verified: `tests/test_integrity.py` + `tests/test_exclusivity_conflicts.py`
  (pre-check-defeated API envelopes, PostGIS two-transaction races), full
  suite 501 passed on PostGIS, regenerated contract artifacts byte-identical
  (no §9 movement), CI green (backend, contract-drift, e2e). Independent plan
  review PASS and independent API/concurrency checkpoint review PASS against
  the exact candidate. Architecture v1.25; §35.1 RM7 closed.
- **MNY-06A/B/C evidence (DONE 20 Aug 2026):** Fable/Codex recovery lane
  `feat/pkg-01-fable-money` integrated at reviewed tip `25fdd52`. Migrations
  `0018`–`0021` add append-only effective-dated payout revisions, acceptance-time
  bindings with frozen rates/cap/eligibility and premium/exclusion geometries,
  and maker-checker correction orders. `payout_v3` pays valid outside-premium
  time at base and inside-premium time at premium, preserves the shared
  chronological Lagos-day cap, persists exact tier components, and never
  reprices accepted work from later rule/zone/settings changes. Direct
  recompute is retired behind projected orders; creator self-approval fails,
  positive deltas require their own release time, and execution/replay is
  idempotent. Admin revision/correction screens and driver tier explanations
  shipped with all three §9 baselines. Verified: PostGIS backend 562 passed
  (3 expected skips), migration up/down/re-upgrade + autogenerate-empty,
  frontend 155 tests/typecheck/lint/build, live-stack Playwright 22 passed,
  and a two-admin synthetic maker-checker journey. Exact-candidate
  money/security, architecture/concurrency/frozen-terms, and minimal-change
  reviews all PASS with no remaining P0–P2 findings. Architecture v1.28;
  §35.1 RM6 closed.
- **FND-02A/B evidence (DONE 20 Aug 2026):** D22 records the reviewed,
  provisional 120-second/25-metre/2-confirm/1-release per-trip policy for new
  acceptances. The classifier combines deterministic rolling displacement with
  the existing long-stay path before one shared grace allocation; complete
  common and rolling terms plus `stationary-rd-v1` freeze into payout-v3
  bindings/fingerprints, while payout-v2 metadata/fingerprints remain exact.
  Payout and correction evidence persist the stationary reason/detector proof,
  and driver/admin surfaces explain it. Focused PostGIS classifier, binding,
  payout and correction suites passed; historical NULL revision overlays are
  read compatibly as `{}`; frontend explanations and the live desktop/mobile
  payout-rule journey passed. Architecture v1.30; §35.1 RM2 closed.
- **R14-A build evidence (DONE 20 Aug 2026):** Pro
  contribution `bc64707` (parent `e74412c`, six new files) verified
  (merge-base, manifest, 123-test/typecheck/lint/build preflight reproduced)
  and squash-integrated with two review-driven corrections in the canonical
  commit: capture/`health=active` requires a valid session or explicit
  `activeTrip` continuation, and probe evidence is labelled and documented as
  capability-only, never runtime lock ownership. Independent
  PWA/security/architecture review corrections and the D23 deferred-gate
  specialist corrections are integrated. ADR 014; architecture v1.30.
- **R14-B/R17-A build evidence (DONE 20 Aug 2026):** deterministic queue,
  tracker, seal and capability checks passed; the complete live browser suite
  passed across desktop/mobile profiles (55 passed, 3 intentional skips).
  Production Compose/edge configuration, release/recovery contracts and Caddy
  validation passed provider-neutrally with synthetic data. The three deferred
  rows below remain `NOT RUN`; no physical-device, route/battery or external
  staging evidence is claimed, and their later real-use gates are enforced by
  the progress validator.
- **Control-plane remediation (16 Aug 2026, task-master correction):** the
  queue validator now rejects six independently reproduced bypass classes
  (hidden/fenced decoys, shadow documents, REVIEW pause-avoidance, frontier/
  QUEUED-DONE drift, Owns drift, external-id erasure) and `EXT-REPORT-METHOD`
  moved from W4-02B's build prerequisite to W4-03B's live pilot gate to match
  the register's recorded semantics. Closes no checklist item; validator +
  33 tests green; architecture v1.26.

### PKG-02 — money integrity and payout operations

- **Owns:** checklist 10–18. One plan integrates assessment/hold, release,
  protected payee, reservation/reconciliation and post-payment debt semantics.
- **Package plan (activated 21 Aug 2026, canonical branch `feat/pkg-02`):**
  controller Lane A owns MNY-08A → MNY-09A → MNY-08B, then MNY-08C and
  MNY-03A. The separately commissioned GPT-5.6 Pro Lane B attempt produced no
  durable files, migrations, tests or commits because its execution surface was
  read-only. On 23 Aug 2026 the owner directed the controller to continue here;
  the controller therefore owns MNY-10A → MNY-10B → MNY-10C → MNY-11A under
  the same already-reviewed contract, consuming Lane A's exact authoritative
  hold-contract SHA. This edge deliberately prevents a second hold predicate
  even though MNY-10A has no checklist prerequisite. Migration,
  payout-model/service, worker registry, API baseline, balance and authority-doc
  edits are controller-serialized with exact leases and disjoint manifests.
  Public endpoint/schema changes and all three §9 baselines land together once
  during controlled integration. Independent package-plan review found no
  critical issue; its material invariant, ownership, contract-boundary and risk
  corrections are reconciled in the uncommitted controller ledger at
  `.codex/delivery/cardvert-pkg02/plan-ledger.md`.
- **Audit-reconciliation correction checkpoints (owner handoff, 21 Aug 2026):**
  these are controller-owned prerequisites inside the existing program, not
  new approvals or permission to reorder the queue. **PKG02-C0 (DONE with
  MNY-08C):** corrected driver explanations use corrected excluded-reason
  provenance, never original-calculation metadata. **PKG02-C1 (DONE before
  MNY-03A, MNY-10B and PKG-02 closure):** unify the DB/application clock and shared
  acceptance-versus-revision serialization; freeze the accepted campaign
  payment window in payout-v3 bindings; make populated downgrades `0018`–`0021`
  fail closed; and lock every overlapping trip row in stable order for
  adjacent-day correction projection/execution. **PKG02-C2 (before any real
  GPS/PWA authority):** enforce ADR 014 capability/session gates in the real
  tracker, recover stale writer-lock state, and retain terminal ping rejections
  as dead-letter evidence. It is registered here as a mandatory PKG-07 entry
  correction, not MNY-08C scope. **PKG02-C3 (evidence/operations):** R17-A
  proves local configuration, smoke and database restore contracts only;
  frontend-image rollback remains unexecuted and must be parameterized and
  exercised before W4-03A authority. Whole-entry payout reservation remains
  the adopted design; no broader Pro schema is admitted.
- **Closure:** every money invariant passes concurrency/property/e2e testing and
  independent money/security review.
- **MNY-08A evidence (DONE 21 Aug 2026):** migration `0022` adds exactly one
  current assessment row per sealed trip with `pending | clean | flagged |
  error`, formula/source/input fingerprints and a current-flag provenance
  watermark. The DB-derived sweep rejects stale formulas, analytics, flag sets,
  pending and error states; retry and two-worker creation converge, while
  evaluation failures persist only `assessment_evaluation_failed`. Verified:
  empty upgrade plus downgrade/re-upgrade at the single `0022` head; 60 focused
  Postgres tests including pre-existing-analytics concurrency and flag-change
  reselection; 118 focused SQLite tests (11 expected Postgres skips); ruff and
  diff checks clean. The independent money/concurrency specialist's two high
  and one medium findings were corrected in one round and rechecked RESOLVED.
- **MNY-09A evidence (DONE 21 Aug 2026):** migration `0023` adds one current,
  versioned route-replay signature per trip. Canonical absolute-payload and
  time-shift-normalized hashes detect copied routes without storing raw
  coordinates/timestamps in review evidence; same-trip retries converge and
  same-driver repetition alone does not flag. Normalized groups retain one
  latest cross-account candidate, reconcile departures and old/new transitions
  under sorted advisory locks, and use DB-side counts/latest selection,
  bounded samples and set-based cleanup. The worker sweep reselects detector,
  configuration and analytics drift; failures stay due. Verified: 165 focused
  SQLite tests (23 expected Postgres skips), 189 focused Postgres tests,
  property/scale and real pipeline coverage, concurrent reverse-order and
  old-to-new group tests, seeded-data downgrade, empty
  `0022 → 0023 → 0022 → 0023`, filtered autogenerate-empty, and ruff/diff
  clean. The independent fraud/privacy specialist's three high and three
  medium findings were corrected once and rechecked RESOLVED. Derived hashes
  are pseudonymous trip-linked location data covered by the later RM15
  retention/DSR operating model; no real-device, real-route, staging, pilot or
  user-feedback evidence is claimed.
- **MNY-08B evidence (DONE 21 Aug 2026):** migration `0024` adds the exact
  `open → acknowledged → confirmed | dismissed` staff-review lifecycle with
  coherent reviewer/time/note evidence and non-terminal per-trip/type dedup.
  One shared predicate holds `open`, `acknowledged` and `confirmed`; only
  `dismissed` releases. Review, detection, impression and payout consumers
  serialize on the same trip scope; cross-trip replay reconciliation takes an
  exclusive reader/writer gate, locks all affected trips in deterministic
  order, then takes route-fingerprint and flag-row locks. This closes the
  reviewed cross-trip stale-money race without duplicating a hold rule. Direct
  resolve and mismatched retries fail 409, exact retries converge, reviews and
  audits commit atomically, and the payout-v1 minimum floor cannot restore held
  pay. The admin console now acknowledges and resolves bounded evidence with
  terminal reviewer context. Verified: 133 focused SQLite tests (28 expected
  Postgres skips), 164 focused Postgres tests plus the corrected
  detection-versus-money and detector concurrency races, empty
  `0023 → 0024 → 0023 → 0024`, legacy fail-closed migration and conservative
  downgrade fixtures, filtered autogenerate-empty, the cross-trip
  detection-versus-money and admin-recompute-versus-worker races, 166 frontend
  tests, typecheck/lint/production build, two-project live seeded admin-review
  Playwright, API/TypeScript contract synchronization, ruff and diff checks.
  The money/concurrency specialist's sole high finding and the broader lock-order
  regression were corrected in one combined round and rechecked RESOLVED.
  Evidence is synthetic/automated;
  no real-device, real-route, staging, pilot or user-feedback claim is made.
- **MNY-08C evidence (DONE 21 Aug 2026):** migration `0025` adds one owner-only,
  idempotent dispute per fraud flag plus typed, deduplicated in-app notices.
  Driver projections expose only allowlisted reason/status/outcome fields;
  internal evidence, matched identities and review notes remain private.
  Admin replies stay separate from internal review notes, and confirmed or
  dismissed outcomes remain visible. Corrected earnings explanations take the
  eligible/excluded pair from the same newest authoritative recompute and fail
  closed on malformed provenance. Verified with focused PostgreSQL role,
  privacy, retry, atomicity and concurrent-terminal tests; 25 focused frontend
  tests; type/lint; contract drift checks; and a two-profile desktop/mobile live
  dispute→reply→reload journey. The privacy/security recheck resolved one
  combined correction round. No real-device, route, staging, pilot or
  user-feedback validation is claimed.
- **PKG02-C1 evidence (DONE 21 Aug 2026):** migration `0026` freezes nullable
  accepted campaign windows on new payout-v3 bindings; legacy provenance fails
  closed. Assignment acceptance and revision publication share one
  campaign-scoped transaction lock and PostgreSQL wall clock. Payout-v3
  calculation, staleness, correction fingerprints and persisted money metadata
  consume the frozen window, while mixed v2 corrections retain live-window
  sensitivity. Populated downgrades `0018`–`0021` and authoritative `0026`
  data fail before destructive DDL. Correction projection locks every
  overlapping trip in stable UUID order before the selected-day cap lock, then
  allocates cap chronologically. Verified: 13 focused historical migration
  cases, 11 focused terms/window cases, 8 controller-rerun migration cases,
  5 combined clock/window/race cases, nullable metadata and v3-correction
  regressions, and adjacent-day opposing-order half-cent/deadlock/stale/retry
  coverage. One specialist review's two medium evidence gaps were corrected in
  one round and rechecked RESOLVED. No API baseline or external/live claim
  changed.
- **MNY-03A evidence (DONE 21 Aug 2026, code `1f0b1f4`):** migration `0027`
  persists one review-escalation timestamp and one unique fraud-flag source for
  an available reversal. A DB-derived, starvation-safe worker sweep takes the
  existing fraud trip scope, then the post-wait database clock, and releases
  due `pending` rows only when the exact assessment inputs are
  successful-current and the imported authoritative hold predicate is false.
  Dismissal invalidates the old assessment; reassessment is required before
  release. Open/acknowledged cases escalate once at the configurable deadline
  without changing money or auto-releasing. A named confirmation after release
  posts one positive subtract-by-type reversal; retry and multiple flags cannot
  over-reverse. Verified: 21 focused PostgreSQL core cases including
  two-worker and dismissal/release races, 3 migration cycle/populated-guard
  cases, autogenerate-empty, a controller rerun of 30 integrated backend
  cases, 11 focused admin UI cases, type/lint, synchronized §9 artifacts, and
  live synthetic desktop/mobile deadline/recommendation plus named
  confirm-to-one-reversal evidence (`available_net = 0.00`, one linked ledger
  row and one audit per action). The money/concurrency specialist found one
  medium configurable-SLA UI wording defect; the single correction round was
  rechecked RESOLVED. No real-device, real-route, external-staging, pilot or
  user-feedback validation is claimed.
- **MNY-10A/B/C + MNY-11A evidence (DONE 23 Aug 2026):** migrations
  `0028`–`0031` form one linear, downgrade-guarded chain for protected payees,
  batch reservation, provider reconciliation and carry-forward debt.
  AES-256-GCM account ciphertext binds tenant/record/field AAD to a required
  versioned KEK keyring; list/error/audit/log surfaces remain redacted, while
  privileged reveal and append-only rewrap are audited. Whole-entry batch
  reservation freezes verified payee/account/amount/instruction hashes under
  maker-checker approval and one active-line constraint, consuming the imported
  fraud-hold contract. Fake-provider submission is idempotent; signed webhook
  or verified poll evidence resolves each line before `paid`, including partial
  failure and retry. Post-payment corrections and confirmed fraud append
  currency-scoped debt linked to immutable paid sources; future credit clears
  debt first and emits one exact residual. Live submission remains disabled
  until `EXT-DISBURSEMENT-PROVIDER` exists. Controlled integration regenerated
  all three §9 baselines once. Non-repeated aggregate verification recorded
  541 backend passes and one intentional skip, 187 frontend tests, typecheck,
  lint, production build, migration/autogenerate, crypto/property/concurrency
  and synthetic payee→batch→reconciliation→debt journeys. The consolidated
  review found one provider-finality/confirmed-fraud lock inversion and two
  paid-state UI color gaps; the single correction round added one shared lock
  order plus a forced-overlap PostgreSQL regression and focused UI assertions,
  then rechecked both findings RESOLVED. No live provider, physical-device,
  real-route, external-staging, pilot or user-feedback validation is claimed.
- **PKG-02 prior closure (23 Aug 2026, candidate `e3a505e`; reopened for
  correction review 24 Aug 2026):** all checklist
  items 10–18 are done; RM8/RM10/RM11 are resolved and RM9's copied-route
  software control is delivered with its physical-proof residual preserved.
  The advisory Pro register remains revalidation input at
  `docs/pro-review-register.md`, not a queue or adopted architecture. PKG-03
  had been promoted to `NEXT`; it was paused pending the correction round.
  Its controller must consume the corrected final D17 crypto seam and money
  authority without adding plaintext fallback, a second crypto subsystem or a
  second fraud-hold predicate.
- **PKG-02 correction round (DONE 24 Aug 2026, base `e8fafb4`):** one bounded
  money-authority correction now creates due reversal obligations after the
  release flush and before audit/commit in deterministic driver/currency/entry
  order; any active reservation aborts the complete release transaction.
  Undeployed migration `0031` backfills all eligible available reversals into
  one driver/currency account and obligation, links same-trip paid provenance,
  conserves totals, replays idempotently and fails before unsafe active
  reservations or populated downgrade destruction. Economic projections keep
  non-voided sources, subtract reversals and exclude `debt_remainder`; separate
  settlement fields expose released credit, cash paid, carried debt and
  batch-payable amount in both driver views and the public API. Evidence:
  focused release/idempotency/whole-entry/residual/two-trip API and PostgreSQL
  reservation-race tests; five populated migration/backfill/downgrade tests;
  contract baselines moved together; frontend 191 tests, typecheck, lint
  (one pre-existing warning) and production build; full backend aggregate
  `793 passed, 3 skipped` before 13 documentation-contract fixture failures,
  all repaired and rechecked by `41 passed`; final clean-context
  minimal-change review PASS (one packaging reminder satisfied). No live
  provider, physical-device, real-route, external-staging, pilot or
  user-feedback validation is claimed. PKG-03 is promoted but not started.
- **Closure-CI fixture correction (24 Aug 2026):** the first closure run passed
  797 backend tests before six production-Compose missing-secret assertions all
  stopped at the newly required payout keyring. `staging.env.example` now
  supplies an explicit synthetic render-only keyring and the missing-value
  matrix covers it; the static verifier also supplies that explicit env file to
  both Compose renders. All 26 pre-production operations tests pass. This adds
  no runtime fallback and changes no Package 2 behavior.

### PKG-03 — commercial contracts and billing

- **Owns:** checklist 19–27. Commercial terms, receipts, invoices, funding,
  payment adapters, corrections and budgets share one canonical money model.
- **Package plan (activated 24 Aug 2026, canonical branch `feat/pkg-03`):**
  the controller serializes W2-00A → W2-00D → W2-00B → W2-01A → W2-01B →
  W2-00C → W2-01C → W2-01D → W2-01E under one campaign/commercial lock
  order and a migration chain beginning after `0031`. Domain work stays behind
  one controlled public-contract integration that moves all three §9 baselines
  in the same commit and reruns the required R14-B fixtures. The controller is
  the only implementation, migration, contract and authority-document writer;
  read-only specialists review the money/tax/concurrency/provider checkpoints.
  Provider-neutral W2-01C and policy-neutral W2-01E seams may build, but the
  checklist rows remain externally blocked from `DONE` while
  `EXT-PAYMENT-PROVIDER` and `EXT-BUDGET-POLICY` are missing. The complete plan
  received one clean-context plan review; all material post-build corrections
  are committed in `f347b37` and `8272b32`, with deterministic browser evidence
  finalized in `86d9934` and a final no-history consolidated review PASS. The
  later Extended-Pro correction range from `a8fa4e0` was implemented in
  `d146140`: receipt/start chronology, allocation-scoped refund conservation,
  correction retry identity, rendered-prefix invoice numbering and
  campaign/terms currency serialization received one consolidated no-history
  review, one focused race correction and final PASS.
- **Closure (24 Aug 2026):** migration head
  `0042_invoice_number_prefix_sequence`; the original 874-backend/193-frontend
  package baseline plus focused PostgreSQL reversal/start, refund, retry,
  numbering, migration and currency-race evidence pass. The single correction
  aggregate exposed only three historical migration/seed harness expectations;
  those were isolated at their owning revisions, corrected and rerun green.
  Ruff, contract drift, lint/typecheck, 193 frontend tests, production build and
  8 fresh-head isolated desktop/mobile billing journeys pass; the final
  independent review verdict is PASS. W2-01C remains
  `BLOCKED — EXT-PAYMENT-PROVIDER` and W2-01E remains
  `BLOCKED — EXT-BUDGET-POLICY`; issuer and real commercial values remain
  fail-closed live-use gates. Package 4 is IN PROGRESS with its W2-03A
  checkpoint preserved on top of this corrected authority.

### PKG-04 — secure evidence, activation and communications

- **Owns:** checklist 28–43, with internal checkpoints for storage/security,
  KYC lifecycle, approvals/activation/cancellation, then communications.
- **Package plan (activated 24 Aug 2026, canonical branch `feat/pkg-04`):**
  adopt verified shared CI repair `a8fa4e0`, then serialize Package 4 behind one
  controller-owned migration/contract/authority boundary. W2-03A is the sole
  admitted first slice: dedicated submit/approve/reject/resubmit transitions
  bind immutable reviewed campaign snapshots and cannot schedule or activate.
  One no-history Terra worker owns bounded domain/API/UI/test implementation;
  the controller owns migrations, all three §9 baselines and authority docs,
  with one independent plan review PASS before implementation. Focused tests
  only at that checkpoint. Corrected Package 3 tip `878be3a` was integrated by
  merge commit `5866dca`, preserving both histories; governance commit
  `e4533a9` was then adopted. W2-04A was admitted next and is now complete.
- **W2-03A checkpoint evidence (24 Aug 2026):** migration `0043` extends the campaign
  lifecycle and adds append-only, exact-submission-bound review evidence.
  Dedicated row-locked advertiser/admin actions enforce submit, approve,
  reasoned reject and resubmit; generic creation/update cannot bypass review,
  and approval cannot schedule or activate. Advertiser detail/history and the
  typed `/admin/approvals` queue expose the same snapshot digest and immutable
  transition history. Focused evidence: 19 backend passes plus 13 expected
  SQLite skips, 5 PostgreSQL lifecycle/race/migration passes, filtered
  autogenerate-empty, 4 OpenAPI/migration-chain passes, 18 frontend tests,
  55 R14-B fixtures, typecheck and lint (one existing compiler warning), and
  the isolated real-stack submit→approve→history journey in desktop/mobile
  Chromium (2 passes). All three §9 baselines moved together. No provider,
  scheduling, activation, physical-device, real-route, staging, pilot or
  user-feedback validation is claimed.
- **Corrected-authority seam evidence (24 Aug 2026):** Package 4 migration
  `0043` now descends from Package 3 head `0042`. The adopted Package 3
  campaign/terms currency lock initially exposed one stale-update ordering
  against review submission; the tenant campaign row is now locked before the
  review-state check while retaining advisory-lock-first currency ordering.
  The barrier proves the stale loser returns
  `CAMPAIGN_REVIEW_STATE_CONFLICT` and live/snapshotted currency remain equal.
  Six focused PostgreSQL authority/review cases, six migration/OpenAPI checks,
  filtered autogenerate, 40 delivery-control cases, Ruff and 55 R14-B fixtures
  pass. W2-03A remains complete; no Package 3 full-suite rerun was performed.
- **W2-04A checkpoint evidence (24 Aug 2026):** migration `0044` converts the
  MNY-08C fraud-notice foundation into a recipient/channel-scoped outbox with
  exact retry fingerprints, unique provider receipt identity, immutable
  evidence, delivery/read state, an unread index and lossless legacy backfill.
  Current-user APIs and same-origin BFF routes expose sanitized list/unread/
  read operations; one root TanStack Query provider mounts a visible-only
  45-second polled centre for admin, advertiser and driver. D24's default-on
  advertiser-organization email preference is shared, manager-controlled and
  audited; in-app remains mandatory. All three §9 baselines moved together.
  Focused evidence: 22 backend passes with 5 expected environment skips; 6
  real-PostgreSQL feed/migration/autogenerate passes; 4 OpenAPI/contract passes;
  62 frontend and preserved R14-B fixtures; typecheck, scoped lint and Ruff;
  and 8 isolated real-stack desktop/mobile three-role Playwright passes.
  Consolidated independent review passed after correcting fresh in-app `sent`
  semantics and provider-ID uniqueness. No email provider, driver WhatsApp/
  SMS, push, external/live-provider, physical-device, staging, pilot or user-
  feedback validation is claimed. Remaining Package 4 work is dependency-
  blocked, so the executable frontier advances to PKG-05/W3-00A without
  starting it in this checkpoint.
- **Package 4 post-review correction evidence (24 Aug 2026):** Extended Pro's
  exact-head review found three uncovered authority defects plus stale PR
  controls. Generic campaign PATCH now treats only an identical status as a
  no-op and rejects every lifecycle change; campaign-zone create/update/delete
  lock the campaign before mutability checks and writes; external-channel
  notification rows start `pending` with no sent timestamp while in-app rows
  start `sent`. Audit, migration/seed-head and Package 3 fixtures now follow the
  governed review path, and notification E2E creates idempotent per-role data
  with one serialized preference mutation. Focused evidence: 83 backend passes,
  including six PostgreSQL submission-versus-zone races; a controller rerun of
  the affected controls passed 64 with 25 environment skips; Ruff, frontend
  lint/type and diff checks pass; the corrected real-stack desktop/mobile
  notification journey passes 7 with one intentional mobile preference skip.
  External provider deferrals remain unchanged and no live delivery is claimed.
- **Closure:** migrations/contracts integrate once; security and communications
  receive separate specialist verification before consolidated package review.

### PKG-05 — privacy, measurement and retargeting

- **Owns:** checklist 44–54. The privacy operating model, disclosure service,
  measurement runs, sources, segments, recommendations and scores are one chain.
- **Package plan (activated 24 Aug 2026, canonical branch `feat/pkg-05`):**
  the controller serializes the dependency-safe frontier W3-00A → W3-00D →
  W3-00C → W3-01A → W3-01B and owns all authority, migration, disclosure,
  public-contract and control-plane surfaces. W3-00B remains transitively
  blocked by W2-02E; W3-00E by W2-03C/D; W3-01C/D and W3-02A/B therefore
  remain transitively blocked. The client input document proves the legal,
  report-method and ad-platform facts were requested, not supplied, so
  `EXT-LEGAL-PRIVACY`, `EXT-REPORT-METHOD` and `EXT-AD-PLATFORM` remain
  MISSING and live use defaults denied. One clean-context Terra plan review
  returned FIX; its full endpoint-inventory/live-gate, atomic differencing,
  synthetic-ROI, source/link history/concurrency and migration corrections
  were reconciled, and the same reviewer returned PASS. The bounded plan and
  review record live at `.codex/delivery/cardvert-pkg05/plan-ledger.md`.
- **W3-00A checkpoint evidence (24 Aug 2026):** a machine-checkable privacy
  register and operating model now cover nine purposes/data classes with
  organizational ownership, explicitly unapproved candidate lawful bases,
  retention dispositions, recipients, controller/processor allocation,
  notice/withdrawal rules, subprocessors/regions, breach responsibilities and
  seven DPIA risk classes. Every named owner, legal basis, notice, retention/
  DSR decision, provider, region and notification rule remains MISSING;
  `live_use_authorized=false`. A deterministic synthetic withdrawal and raw-
  route-breach tabletop stops at the exact W3-00B, Package 4 and legal gates.
  Focused evidence: 43 privacy/control tests, progress validation, JSON parse,
  Ruff and diff checks pass. The independent privacy specialist's sole finding
  removed staff from raw-location recipients; the corrected service-only
  analytics/fraud/payout plus grandfathered-heatmap boundary is test-pinned and
  rechecked PASS. No real person, GPS, KYC, provider, notification, legal
  approval, DSR execution, advertiser output or live-use evidence is claimed.
- **W3-00D checkpoint evidence (24 Aug 2026):** the machine-checkable
  measurement contract now maps every current advertiser-visible measure to
  its class, unit, provenance, vintage, missing-data rule and uncertainty
  treatment. The internal `estimated_impressions` field is presented as
  **Modelled potential contacts**; the default title is **Campaign Performance
  Analysis**; attribution/view/reach/exposure overclaims were removed from the
  current advertiser copy. Target-area coverage has a visibly synthetic-only
  candidate numerator/denominator and keeps its live qualifying rule MISSING.
  Production ROI defaults omitted and requires all advertiser conversion/
  revenue, approved method, attribution, cost, currency, time, exclusion,
  correction, provenance and immutable-manifest prerequisites. Its sole
  enabled golden is `test_only` synthetic evidence, not approval;
  `EXT-REPORT-METHOD` remains MISSING. Focused evidence: four methodology/
  copy tests, frontend typecheck, 210 frontend tests, formatting and diff
  checks pass. Independent measurement/legal/commercial review found one
  unlabeled confidence diagnostic; all visible instances now disclaim
  statistical-interval meaning and the reviewer rechecked PASS. No report was
  issued and no live or client methodology fact is claimed.
- **W3-00C checkpoint evidence (24 Aug 2026):** migration `0045` and the
  central service boundary now cover all eight current advertiser/report/
  heatmap outputs. The production gate runs before membership, data or history
  reads and requires non-placeholder legal, disclosure-configuration and
  retention references; numeric thresholds alone cannot enable it. Reports
  remain additionally denied until W3-00E safe runs. The grandfathered
  heatmap reader now releases only coarse cells meeting distinct vehicle,
  trip and day floors plus one contributor cap applied to every serialized
  ping, trip, distance and impression metric. Atomic history
  binds principal, tenant, campaign, endpoint, window, filters and result
  fingerprint; one global spatial-history lock plus hierarchical global/org/
  campaign overlap checks prevents cross-endpoint, cross-principal,
  complementary and changed-result differencing. A daily DB-time worker purge
  physically enforces configured history expiry, and populated downgrade
  refuses destructive loss. Synthetic-only settings are impossible outside
  `environment=test`; all live flags/references remain false/blank while
  `EXT-LEGAL-PRIVACY` is MISSING. Focused PostgreSQL evidence covers exact/
  below thresholds, ties, empty/sticky suppression, sequential and concurrent
  overlap in both parent/child orders, all-route no-read/no-write denial,
  tenant/RBAC, migration round-trip/downgrade and autogenerate-empty. Existing
  report/impression/heatmap and Compose checks pass. Independent privacy/
  security/architecture review found and rechecked fixes for hierarchical
  overlap and guaranteed no-traffic retention, returning PASS. No new raw-
  ping reader, report issuance, real data, approved threshold or live output
  is claimed.
- **W3-01A checkpoint evidence (24 Aug 2026):** migration `0046` adds an
  advertiser-organization source projection, append-only lifecycle evidence
  and actor/operation-scoped retry authority for exactly the five D11 planning
  source kinds. Positive discriminated schemas expose only aggregate category,
  channel, stage, bounded-window/count-band and confidence-band facts plus
  candidate provenance, unapproved basis/notice state, expiry and DSR role/
  status; identifiers, URLs, uploads, notes, opaque metadata and unknown/nested
  fields reject. The central privacy gate runs before every advertiser/admin
  read or mutation, active organization membership is service-enforced, and
  corrections are deactivate-plus-new rather than mutable updates. Exact and
  concurrent same-key retries converge under an advisory transaction lock;
  changed payload reuse conflicts. Source/event snapshots share one closed
  public contract, history is trigger-protected, expiry is DB-time derived,
  and populated downgrade refuses loss. Advertiser management and read-only
  admin monitoring role surfaces move with all three §9 baselines. Focused
  API/RBAC/lifecycle/expiry/retry/contract tests, frontend type/lint, Ruff and
  generated-contract checks pass; the PostgreSQL race/migration tests are
  present and skip only when the optional test database is unavailable.
  Independent privacy/security review found the initially open response
  dictionary and missing concurrent proof; both were corrected and rechecked
  PASS. `EXT-LEGAL-PRIVACY` remains MISSING; no approved lawful basis, real
  audience, upload, identity, raw-ping join or live source use is claimed.
- **W3-01B checkpoint evidence (25 Aug 2026):** migration `0047` adds one
  advertiser-organization source/campaign/target-zone/time linkage projection,
  append-only create/remove evidence and actor/operation-scoped retry records.
  The service locks source → campaign → zone → link, rechecks active tenant,
  source expiry, campaign bounds and zone ownership, freezes typed snapshots
  and parent fingerprints, and reports later parent changes as stale without
  rewriting history. The privacy gate precedes advertiser and service-enforced
  active-admin access; cross-tenant, inactive, expired and changed-payload
  operations fail closed. Advertiser setup/removal and read-only admin
  monitoring is service-authorized for active admins and moves with all three
  §9 baselines. Focused API/RBAC/lifecycle/
  retry/audit/migration/frontend checks pass; five real-PostgreSQL migration/
  concurrency cases cover 0045–0047, same- and distinct-key retries plus
  source-deactivation and campaign/zone races.
  The independent privacy/authorization review's service-admin and parent-race
  findings were corrected and rechecked PASS. Aggregate evidence: 722 backend
  passes with 244 environment skips after three stale Package 5 expectations
  were corrected and focused-rechecked; 212 frontend tests, typecheck, lint
  (one pre-existing warning) and a successful webpack production build.
  `EXT-LEGAL-PRIVACY`, `EXT-REPORT-METHOD` and
  `EXT-AD-PLATFORM` remain MISSING; no raw-ping join, person-level audience,
  report issuance, export, live source use or platform activation is claimed.
- **Package 5 frontier closure (25 Aug 2026):** the consolidated privacy,
  authorization and minimal-change review returned PASS after real-PostgreSQL
  evidence, control-state timing and unrelated formatting were reconciled.
  W3-00A/D/C and W3-01A/B are complete. W3-00B remains transitively blocked by
  W2-02E through `EXT-STORAGE-PROVIDER`, `EXT-MALWARE-SCANNER` and
  `EXT-KMS-CUSTODY`; W3-00E remains blocked by W2-03C/D and their evidence/
  creative/activation chain. W3-01C/D and W3-02A/B therefore remain dependency-
  blocked. Package 5 is BLOCKED, not DONE; the controller advances to
  dependency-free PKG-06/W3-03A without starting it.
- **Extended Pro correction pass (25 Aug 2026):** four validated defects were
  repaired on the published Package 5 head without reopening Packages 1–4:
  migration `0047`'s PostgreSQL partial active-link index is now declared in
  ORM metadata with a SQLite partial predicate and an autogenerate regression;
  heatmap contributor suppression now covers every serialized metric rather
  than only the selected weight; source monitoring and admin heatmap services
  now require an active admin before domain reads; and governed advertiser
  output deterministically selects the newest active organization membership
  after the live gate. Focused red/green regressions pass, followed by the
  impacted Package 5 backend/migration subset (42 passed, 2 warnings). The
  post-repair aggregate backend gate is 968 passed, 3 skipped; frontend lint,
  typecheck, 212 unit tests, contract drift and the webpack build pass, and
  pre-production verification is 26 passed. The local Playwright attempt
  reached 63 passed and 6 skipped but had 9 environment-only failures because
  the running API is mounted from another worktree with stale seeded state and
  the cleanup path lacked `PAYOUT_CRYPTO_KEYRING_B64`; it is not attributed to
  these repairs and was not rerun. No external gate changed, and Package 6's
  separate W3-03A checkpoint was not touched.
- **Closure:** privacy/measurement review proves suppression, reproducibility,
  provenance and safe claims before any advertiser live-use gate opens.

### PKG-06 — matching and driver onboarding

- **Owns:** checklist 55–60. Matching/offers/activity and public application,
  KYC/payee and vehicle approval become one governed eligibility journey.
- **W3-03A evidence (25 Aug 2026):** `matching_v1` adds an admin-only,
  non-persistent cars-only recommender over current assignment readiness. It
  ranks lower vehicle/driver load, then computed-only activity and stable UUID
  ties; the admin must explicitly select a candidate. A typed fingerprint is
  rechecked under stable parent and aggregate-contributor row locks before the
  existing assignment command writes, while context-free manual clients remain
  compatible. Evidence includes observed red/green, 35 focused backend passes
  plus 10 real-PostgreSQL concurrency/exclusivity passes, 56 frontend/R14-B
  passes, type/lint/build, byte-stable regenerated §9 artifacts, an isolated
  admin recommendation→offer journey, and consolidated review RESOLVED. No
  migration, automatic assignment, person/payee/KYC eligibility claim, provider
  input or live-use authorization was added. W3-03B–W3-04C were not started;
  the corrected Package 5 history is adopted beneath this checkpoint and its
  external legal/reporting/ad-platform gates remain unchanged.
- **Closure:** security/privacy/money and lifecycle races pass, including the
  complete accept/decline/expiry flow and non-work-eligible pending states.

### PKG-07 — production driver PWA

- **Owns:** checklist 61–64. Installability/session safety, screen-on tracking,
  durable sync, onboarding/campaign use, earnings/disputes and release evidence
  ship together.
- **Entry correction:** PKG02-C2 is mandatory before W4-01A becomes
  authoritative or any real GPS is collected: the tracker enforces ADR 014
  capability/session gates, stale writer-lock state is recoverable, and
  terminal ping failures remain as dead-letter evidence.
- **Closure:** Android/iOS browser/device matrix, permission/visibility,
  battery/data-loss/security and full journey tests pass against the frozen
  backend contracts.

### PKG-08 — governed reporting and pilot readiness

- **Owns:** checklist 65–68. Governed map/report output, bounded exports,
  client-owned environment and the full acceptance suite form the launch gate.
- **Closure:** every §35 gate is evidenced; restore, security, load, report
  reproducibility and end-to-end pilot simulation pass.

### PKG-09 — controlled pilot, training and handover

- **Owns:** checklist 69–71. Training is rehearsed before a controlled pilot;
  stabilization evidence then closes support, ownership and roadmap handover.
- **Closure:** accepted operating materials, monitored pilot evidence, known
  risks/deferments and named owners agree with repository truth.

## Architecture traceability — non-executable parent groups

These 22 historical architecture groups are traceability only. They are not
packages, statuses, or review cycles and can never be promoted.

RM17's production-PWA/staging parallel intent is handled as disjoint internal work in
PKG-01 under its package plan; there are never two active packages.

| Order | Parent outcome | Type | Outcome and architectural authority | Prerequisites | Gate impact | Completion evidence required |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | **RISK-01 — production-PWA real-device proof** | PARENT | Android/iOS installable-PWA ADR and real-device proof for screen-on enforcement, permissions, visibility degradation, durable queue, tracking health, battery, reload/offline and session safety (§23, D18/RM17). Synthetic routes only. | Stable D15/D16 ping/seal contract **[BUILT]** | Produces early D18/RM17 evidence for **G-pilot**; authorises no real GPS | Browser/device matrix, measured SLO evidence, live synthetic-trip simulation, and independent review. |
| 2 | **RISK-02 — synthetic staging** | PARENT | Exercise the production-like topology with synthetic data before W2 grows it (§25, RM17). | Owner approval before external spend; Q32 blocks production, not preproduction work | Produces early RM17 evidence for **G-pilot**; authorises no live data | Deployment/recovery/smoke evidence or an explicit `BLOCKED` row naming the missing approval. |
| 3 | **W0-01 — stationary-time policy** | PARENT | Decide and implement RM2's sub-window rule (§16.1, §35 RM2; D2/D4/Q5). | Record the owner-approved money policy before code; obtaining it is part of this slice | Closes RM2's remaining contribution to **G-GPS** | Decision row; adversarial cases; payout integration + regression tests; independent money review. |
| 4 | **W0-02 — integrity conflict mapping** | PARENT | Map the four exclusivity constraint races to stable 409 envelopes (§6.4, §35 RM7). | W0-01 | Closes RM7 before pilot | Constraint tests and API envelopes; no unhandled `IntegrityError`. |
| 5 | **W0-03 — correction authority** | PARENT | Effective-dated immutable payout rules, correction orders, value-complete audit, and maker-checker approval (§16, §35 RM6). | W0-02 | Closes RM6's contribution to **G-money** | Migration/model/API/UI tests; historical-pricing and creator≠approver proofs; independent money/security review. |
| 6 | **W1-02 — fraud assessment, holds, disputes** | PARENT | Current per-trip assessment, authoritative non-terminal hold invariant, serialised review transitions, driver reasons/dispute, and minimal in-app notification (§17/§20, RM8; software controls from RM9). | W0-03; must precede S3 | Closes RM8's contribution to **G-money** and part of RM9 for **G-GPS** | State-transition, race, release-predicate, worker, API/UI, e2e, and independent money/concurrency review. |
| 7 | **W1-03A — release scheduling** | PARENT | Clean earnings release without a blanket delay; flagged earnings remain held under one RM8 predicate with a seven-day review SLA and no auto-release (§16.2, D18/Q22). | W1-02 | Satisfies the release-scheduling part of **G-money** | Time-boundary, escalation, no-auto-release, concurrency, retry, balance, worker, ops-UI tests, and independent money review. |
| 8 | **W1-03B — payout batches and reconciliation** | PARENT | Reservation/frozen payee/provider submission/line reconciliation plus carry-forward post-payment debt (§16.3, RM10/RM11, D18/Q27). | W1-03A + W0-03 | Closes RM10/RM11's contributions to **G-money** | Batch state-machine, uniqueness, instruction hash/idempotency, maker-checker, provider reconciliation, debt property tests, e2e, and independent money review. |
| 9 | **W2-00 — commercial money contracts** | PARENT | Advertiser company/profile management plus funded driver-liability authorization, effective-dated commercial terms, canonical receipt/allocation identity, audited production authority, cancellation cutoff/settlement, and atomic activation contracts (§15/§18/§21/§27, RM12/RM13, D20). | W1 complete | Defines how W2 closes RM12/RM13 for **G-commercial** | Reconciled design/invariants, migration plan, RBAC, concurrency/financial property tests, and independent architecture/money review. |
| 10 | **W2-01 — billing, invoices, payments** | PARENT | Per-campaign custom accepted terms, VAT-inclusive/itemised invoices, standard full-prepay plus approved-corporate credit, bank/gateway receipts, standard 24-hour production wait, audited expedited waiver, refunds and budgets (§15, D18/D20), built on W2-00. | W2-00; statutory company facts gate real issuance only | Partially closes **G-commercial**; real invoices remain blocked until company facts | Receipt dedup, amount/currency, webhook idempotency, invoice, production-authority/refund boundaries, budget, API/UI, e2e, and independent money review. |
| 11 | **W2-02 — secure files and KYC controls** | PARENT | Presigned storage, mandatory type/size/malware checks, purpose-scoped reads, encryption/key governance, and privileged-read audit (§12/§19, RM18). | Record storage/vendor decision before implementation | Closes RM18 for KYC/PWA pilot and contributes to **G-GPS/G-pilot** | Upload/download/security tests, audit evidence, retention/DSR coverage, and independent threat review. |
| 12 | **W2-03 — approvals, evidence, activation, cancellation** | PARENT | Campaign/creative/installation review; proof-of-display, device/vehicle binding, atomic activation, change requests, cancellation cutoff and settlement (§18/§19/§21, RM9/RM13). | W2-00/01/02 | Closes RM13 for **G-commercial** and remaining RM9 controls for **G-GPS** | Lifecycle/race tests, evidence review, cutoff clipping, settlement, API/UI, ops e2e, and independent review. |
| 13 | **W2-04 — notification and account-contact channels** | PARENT | Outbox-backed advertiser email and in-app triggers, password recovery, verified driver phone/consent; operations-run driver WhatsApp remains manual (§20/§23, Q34). | W1 notification core + W2 event sources | No independent gate; required MVP communication and recovery path | Retry/dedup/provider-receipt, token security, preference/consent, redaction, and user-flow tests. |
| 14 | **W3-00 — privacy and measurement foundation** | PARENT | DPIA/ROPA/roles/retention/DSR controls; central disclosure control; measurement methodology, immutable runs, uncertainty, proof-of-performance and the performance-report/conditional-ROI contract (§22/§24/§27, RM15/RM16, D20). | Qualified Nigerian legal/privacy review is required before live use, not before building controls | Closes RM15/RM16 contributions to **G-GPS/G-advertiser/G-moduleG** | Approved artefacts/runbooks, disclosure/differencing tests, reproducible performance and conditional-ROI fixtures, and independent privacy/measurement review. |
| 15 | **W3-01 — retargeting sources, segments, insights** | PARENT | Typed aggregate sources, campaign/zone linkage, exposure segments, controlled insights, export and gated geography/time/context activation with person-level payload rejection (§22, D6/D11/D18/D20/Q11). | W3-00; legal artifacts gate export and EXT-AD-PLATFORM gates live aggregate contextual activation | Implements **G-moduleG** subject to live-use gates | Privacy-boundary, provenance, suppression, schema rejection, export/activation approval, API/UI, e2e, and independent privacy review. |
| 16 | **W3-02 — exposure score and high zones** | PARENT | Versioned exposure metric and high-exposure zone views over reproducible measurement runs (§22.4/§27). | W3-00/01 | Implements the governed advertiser outputs behind **G-advertiser** | Formula fixtures, disclosure controls, reproducibility, report/UI tests, and independent measurement review. |
| 17 | **W3-03 — matching, offers, activity** | PARENT | Eligibility/scoring recommendations, admin assignment, driver offer response, inactive sweeps and flags (§21, Q7/Q20). | W2-03 activation/evidence | Required assignment/operations capability; no independent gate | Deterministic scoring, exclusivity/race, sweep, API/UI, and driver/admin e2e tests. |
| 18 | **W3-04 — driver self-registration and vehicle onboarding** | PARENT | Public application, secure document upload, bank/KYC and driver-owned vehicle-profile review before work (§23, Q13/Q23/Q26; proposal Module C). | W2-02 + W3-03 | Must preserve RM18 controls before KYC/vehicle use | Abuse/security, review-state, KYC/vehicle audit, API/UI, onboarding e2e, and independent security/privacy review. |
| 19 | **W4-01 — production driver PWA** | PARENT | Installable screen-on pilot client with fail-closed permissions/visibility, durable offline/retry sync, session safety, tracking health and the frozen backend contract (§23, D18). | RISK-01 + W1–W3 | Supplies the D18 PWA replacement for RM14's former native **G-pilot** gate and closes relevant RM15/RM18 contributions | Full Android/iOS browser/device matrix, battery/completeness SLOs, security review, and journey e2e. |
| 20 | **W4-02 — exports and issued reports** | PARENT | Remaining bounded CSV/PDF Campaign Performance Analysis package, with true ROI only behind the D20 data-and-method gate (§27/§30, D11/D20). | W3-00/01/02 | Governed by **G-advertiser/G-moduleG** | Performance/ROI golden files, access/privacy controls, reproducibility, load, UI tests, and independent privacy/measurement review. |
| 21 | **W4-03 — pilot deployment and readiness** | PARENT | Cardvert client-owned deployment, observability, restore/recovery, incident rehearsal, provider/permit gates and Abuja pilot acceptance (§25/§26, D18–D20/RM17). | All prior slices; registered external gates | Closes **G-pilot** only when every §35.3 gate passes | Staging burn-in, backup/restore, smoke/load/security evidence, provider/permit/legal approvals, and independent launch review. |
| 22 | **W4-04 — onboarding, training, handover** | PARENT | Role-based training, operator runbooks, support/handover and post-MVP roadmap promised by D11. | W4-03 release candidate | Final MVP delivery evidence, not a technical gate | Accepted materials, rehearsed operating flows, known-risk/deferment register. |

## Mandatory checklist item register

This register preserves the complete implementation detail from the reviewed
71-item decomposition. Each item belongs to exactly one package and remains a
binding acceptance obligation, but no row here is independently promoted or
requires a separate owner-facing review cycle. A checklist specification may
be refined inside its package without weakening its outcome, acceptance,
verification, gates or required specialist review.

| # | Checklist item | Package | Status | Observable outcome | Prerequisites |
| ---: | --- | --- | --- | --- | --- |
| 1 | **R14-A — production-PWA direction and protocol ADR** | PKG-01 | DONE | Executable evidence freezes installability, screen-on, permission, visibility, session, queue and seal semantics for the pilot PWA. | none |
| 2 | **R14-B — cross-profile interrupted-trip build proof** | PKG-01 | DONE | Desktop and mobile browser profiles prove the complete interrupted synthetic-trip contract; physical Android/iPhone route and battery runs remain deferred validation. | leaf: R14-A |
| 3 | **R17-A — production-like release/recovery build proof** | PKG-01 | DONE | Provider-neutral production-like topology, release smoke and recovery controls verify locally with synthetic data; external deployment remains deferred validation. | none |
| 4 | **FND-02A — stationary-time policy decision** | PKG-01 | DONE | Owner records a versionable rule separating traffic exposure from parked-time farming. | none |
| 5 | **FND-02B — stationary policy implementation** | PKG-01 | DONE | Classifier, fingerprints and earnings explanations implement the recorded rule. | leaf: FND-02A; external: EXT-RM2-POLICY |
| 6 | **FND-07 — exclusivity conflict envelopes** | PKG-01 | DONE | Four known assignment/trip races return stable 409 errors, not 500s. | none |
| 7 | **MNY-06A — immutable payout-rule revisions** | PKG-01 | DONE | Financial rule history becomes effective-dated, immutable and value-audited. | none |
| 8 | **MNY-06B — assignment/trip rule binding and payout_v3** | PKG-01 | DONE | Accepted driver terms freeze base/premium rates, zone/eligibility revisions and the `payout_v3` rule used by each interval/trip. | leaf: MNY-06A |
| 9 | **MNY-06C — maker-checker correction orders** | PKG-01 | DONE | Retroactive recompute requires a projected order and separate approver. | leaf: MNY-06B |
| 10 | **MNY-08A — current fraud assessments** | PKG-02 | DONE | Every sealed trip has one current pending/clean/flagged/error assessment. | none |
| 11 | **MNY-09A — cross-trip/account replay detection** | PKG-02 | DONE | Identical and time-shifted route replay becomes reviewable evidence. | leaf: MNY-08A |
| 12 | **MNY-08B — review states and hold invariant** | PKG-02 | DONE | One serialized transition table and hold predicate controls all money consumers. | leaf: MNY-08A, MNY-09A |
| 13 | **MNY-08C — driver reasons, disputes and in-app notice** | PKG-02 | DONE | Drivers can see holds, dispute them and receive sanitized outcomes. | leaf: MNY-08B |
| 14 | **MNY-03A — clean release and flagged review SLA** | PKG-02 | DONE | Clean entries release idempotently; flagged entries remain held for approve/decline with seven-day escalation and no auto-release. | leaf: MNY-08B |
| 15 | **MNY-10A — protected payee/account foundation** | PKG-02 | DONE | Payouts target an immutable payee and verified bank-account version safely. | none |
| 16 | **MNY-10B — batch reservation and provider submission** | PKG-02 | DONE | Available entries are atomically reserved into frozen, idempotent provider instructions and submitted only after maker-checker approval. | leaf: MNY-10A |
| 17 | **MNY-10C — provider line reconciliation and paid finality** | PKG-02 | DONE | Each automated transfer line reconciles from signed webhook/verified poll evidence before cash-paid finality. | leaf: MNY-10B |
| 18 | **MNY-11A — carry-forward post-payment debt** | PKG-02 | DONE | Later corrections reduce future pay without rewriting paid history. | leaf: MNY-10C, MNY-06C |
| 19 | **W2-00A — packages, custom quotes and accepted terms** | PKG-03 | DONE | A versioned custom quotation for every campaign—including an externally prepared quote recorded afterward—creates one immutable accepted snapshot; the legacy title does not authorize a launch package catalogue. | leaf: MNY-11A |
| 20 | **W2-00D — advertiser company profile management** | PKG-03 | DONE | Advertiser and admin manage tenant-safe company/contact details used by commercial surfaces. | none |
| 21 | **W2-00B — canonical receipts and allocations** | PKG-03 | DONE | One immutable external receipt can fund obligations once, within its amount. | leaf: W2-00A |
| 22 | **W2-01A — VAT-itemised invoices** | PKG-03 | DONE | Admin issues numbered immutable invoices; advertiser sees VAT-inclusive pricing with included net, VAT line and gross balance. | leaf: W2-00A, W2-00D |
| 23 | **W2-01B — manual bank-transfer confirmation** | PKG-03 | DONE | Ops reconciles transfers into the shared receipt/allocation/payment history. | leaf: W2-00B, W2-01A |
| 24 | **W2-00C — funded/approved-credit liability authorization** | PKG-03 | DONE | Standard work is fully prepaid and waits 24 hours before production; approved corporate credit remains bounded, while any expedited start requires an immutable advertiser waiver and audited actual start. | leaf: W2-01B, MNY-11A |
| 25 | **W2-01C — gateway adapter and webhook ingestion** | PKG-03 | BLOCKED — EXT-PAYMENT-PROVIDER | One-off Q3 checkout and signed provider events converge into canonical receipts. | leaf: W2-00B, W2-01A; external: EXT-PAYMENT-PROVIDER |
| 26 | **W2-01D — credits, reversals and 24-hour refund registry** | PKG-03 | DONE | Standard refund eligibility lasts to the 24-hour boundary; expedited eligibility ends only when production actually begins under an immutable advertiser-requested waiver. | leaf: W2-01A, W2-01B |
| 27 | **W2-01E — advertiser-spend budget enforcement** | PKG-03 | BLOCKED — EXT-BUDGET-POLICY | Spend facts drive persisted alerts/pauses without using driver payout cost as a proxy. | leaf: W2-01A, W2-01B; external: EXT-BUDGET-POLICY |
| 28 | **W2-02A — private object-storage foundation** | PKG-04 | BLOCKED — EXT-STORAGE-PROVIDER | Direct private uploads produce managed stored-file records. | external: EXT-STORAGE-PROVIDER |
| 29 | **W2-02B — malware scanning and purpose-scoped reads** | PKG-04 | BLOCKED — EXT-MALWARE-SCANNER | Unsafe files fail closed; privileged downloads are short-lived and audited. | leaf: W2-02A; external: EXT-MALWARE-SCANNER |
| 30 | **W2-02C — advertiser creative upload** | PKG-04 | TODO | Campaign flows use managed scanned assets instead of arbitrary URLs. | leaf: W2-02B |
| 31 | **W2-02D — encrypted KYC and financial identifiers** | PKG-04 | BLOCKED — EXT-KMS-CUSTODY | Required documents/NIN/bank data reuse the crypto port and are protected and version-reviewed. | leaf: W2-02B, MNY-10A; external: EXT-KMS-CUSTODY |
| 32 | **W2-02E — file/KYC lifecycle and incident operations** | PKG-04 | TODO | File/KYC purge plus scanner/key/vendor failures are tested and audited. | leaf: W2-02B, W2-02D |
| 33 | **W2-03A — campaign submission and approval** | PKG-04 | DONE | Advertiser submits; admin approves/rejects; unapproved campaigns cannot schedule. | none |
| 34 | **W2-03B — creative review gate** | PKG-04 | TODO | Only admin-approved, scan-cleared creative can satisfy campaign launch. | leaf: W2-02C |
| 35 | **W2-03C — installation evidence and proof-of-display** | PKG-04 | TODO | Assignment-bound evidence and nonce proof gate earning eligibility. | leaf: W2-02B |
| 36 | **W2-03D — atomic activation** | PKG-04 | TODO | One admin command locks/rechecks every commercial and operational prerequisite, including valid standard-wait or expedited-waiver production authority. | leaf: W2-00C, W2-01A, W2-01B, W2-03A, W2-03B, W2-03C |
| 37 | **W2-03E — governed mid-flight changes** | PKG-04 | TODO | Expansions honor funded headroom; reductions need approval and effective revisions. | leaf: W2-00A, W2-00C, W2-03D |
| 38 | **W2-03F — cancellation cutoff and settlement** | PKG-04 | TODO | One idempotent cutoff stops new work, clips pay and applies the standard-boundary or actual-waived-start refund rule. | leaf: W2-01D, W2-03D, MNY-11A |
| 39 | **W2-03G — proof challenges and spot checks** | PKG-04 | TODO | Missed challenges and physical verification feed the authoritative fraud hold. | leaf: MNY-09A, W2-03C, W2-03D |
| 40 | **W2-04A — notification core and role surfaces** | PKG-04 | DONE | W1 in-app notices become the shared outbox/list/unread-preference system. | leaf: MNY-08C |
| 41 | **W2-04B — advertiser email delivery** | PKG-04 | BLOCKED — EXT-EMAIL-PROVIDER | Worker-dispatched email and signed receipts update one logical notification. | leaf: W2-04A; external: EXT-EMAIL-PROVIDER |
| 42 | **W2-04C — business triggers and manual driver contact** | PKG-04 | TODO | Stable event keys notify users; driver WhatsApp remains an audited ops task. | leaf: W2-04A, W2-04B, W2-01E, W2-03F, W2-03G, MNY-10C |
| 43 | **W2-04D — account recovery and verified contact preferences** | PKG-04 | BLOCKED — EXT-PHONE-OPERATOR | Advertiser/admin password reset and driver verified-phone/WhatsApp consent are explicit. | leaf: W2-04B, W2-04C; external: EXT-PHONE-OPERATOR |
| 44 | **W3-00A — privacy operating model** | PKG-05 | DONE | DPIA/ROPA/roles/lawful bases/consent/vendor/breach responsibilities are explicit. | none |
| 45 | **W3-00B — end-to-end retention and DSR** | PKG-05 | TODO | Synthetic DSR spans DB, objects, devices, logs, backups and processors. | leaf: W3-00A, W2-02E |
| 46 | **W3-00C — central disclosure-control service** | PKG-05 | DONE | Every advertiser heatmap/report/audience query enforces one privacy floor. | leaf: W3-00A |
| 47 | **W3-00D — measurement methodology contract** | PKG-05 | DONE | Product defines modelled potential contacts, provenance, uncertainty and claims; Campaign Performance Analysis is standard and true ROI requires approved inputs and method. | none |
| 48 | **W3-00E — immutable measurement runs and proof manifests** | PKG-05 | TODO | Issued results bind frozen inputs to creative/evidence/assignment/period and reproduce whether the ROI gate passed or failed closed. | leaf: W3-00D, W2-03C, W2-03D |
| 49 | **W3-01A — typed retargeting source registry** | PKG-05 | DONE | Advertiser/admin manage allowlisted aggregate planning sources without identifiers. | leaf: W3-00A, W3-00D |
| 50 | **W3-01B — source/campaign/zone linkage** | PKG-05 | DONE | Owned sources link safely to campaigns, zones and time windows. | leaf: W3-01A |
| 51 | **W3-01C — governed exposure segments** | PKG-05 | TODO | Worker materializes versioned, suppressed coverage-cell/time aggregates. | leaf: W3-00C, W3-00D, W3-00E, W3-01B |
| 52 | **W3-01D — recommendations, export and gated activation** | PKG-05 | TODO | Safe geography/time/context recommendations, controlled export and activation use one governed aggregate; identifiers/person-level payloads reject and live push fails closed without EXT-AD-PLATFORM. | leaf: W3-01C, W3-00D, W3-00E |
| 53 | **W3-02A — exposure score v1** | PKG-05 | TODO | Formula-versioned score is reproducible and distinct from impressions. | leaf: W3-00D, W3-00E |
| 54 | **W3-02B — high-exposure zone insights** | PKG-05 | TODO | Governed ranked zones appear in admin/advertiser maps and reports. | leaf: W3-00C, W3-00E |
| 55 | **W3-03A — matching recommendations** | PKG-06 | DONE | Admin receives deterministic eligible driver/vehicle rankings. | none |
| 56 | **W3-03B — complete offer lifecycle** | PKG-06 | TODO | Terms-complete expiring offers support accept/decline and immutable evidence. | leaf: W3-03A, W2-00A, MNY-06B |
| 57 | **W3-03C — activity floor and inactivity handling** | PKG-06 | TODO | Verified-hours/inactivity sweeps create reviewable ops flags and notices. | leaf: W3-03B, W2-04A |
| 58 | **W3-04A — public driver application** | PKG-06 | TODO | Abuse-resistant registration creates a pending, non-work-eligible application. | none |
| 59 | **W3-04B — KYC/bank onboarding approval** | PKG-06 | TODO | Person/payee KYC is approved but remains non-work-eligible pending W3-04C vehicle approval. | leaf: W3-04A, W2-02D, MNY-10A |
| 60 | **W3-04C — driver vehicle profile and approval** | PKG-06 | TODO | Identity/KYC-approved applicants add vehicle evidence; admin approval grants work eligibility. | leaf: W3-04B, W2-02B, W2-02D |
| 61 | **W4-01A — PWA foundation and session security** | PKG-07 | TODO | The installable production client uses the BFF session safely and fails closed on unsupported permission/storage/lock states. | leaf: R14-A, R14-B |
| 62 | **W4-01B — screen-on tracking and durable sync** | PKG-07 | TODO | Explicit Start/End tracking survives reload/network interruption, reports visibility degradation and never claims unsupported background capture. | leaf: W4-01A, R14-B |
| 63 | **W4-01C — PWA onboarding and campaign journey** | PKG-07 | TODO | Onboarding, vehicle, offers, activation and tracking integrate through governed BFF/API contracts. | leaf: W4-01B, W3-04C, W3-03B, W2-03D |
| 64 | **W4-01D — PWA earnings, disputes and release rehearsal** | PKG-07 | TODO | History, earnings, disputes, notifications, installability and production-PWA release evidence are complete. | leaf: W4-01C, MNY-08C, MNY-11A, W2-04A, W2-04C |
| 65 | **W4-02A — governed maps and report experience** | PKG-08 | TODO | Existing maps/reports consume safe runs; performance analysis is standard and ROI is absent unless its data/method gate passes. | leaf: W3-00C, W3-00D, W3-00E, W3-01D, W3-02A, W3-02B; external: EXT-BASEMAP |
| 66 | **W4-02B — bounded CSV/PDF issuance** | PKG-08 | TODO | Async hashed exports reproduce the frozen performance/conditional-ROI decision and honor privacy/legal gates. | leaf: W4-02A |
| 67 | **W4-03A — client-owned release environment** | PKG-08 | TODO | Approved account/domain hosts a hardened release candidate with recovery. | leaf: R17-A, W4-01D, W4-02B; external: EXT-RELEASE-ENV |
| 68 | **W4-03B — Cardvert pilot gate and acceptance suite** | PKG-08 | TODO | One suite proves every §35 gate and the Abuja journey, including contextual activation, performance/conditional-ROI reporting, automated transfer and permit evidence. | all-prior; external: EXT-PILOT-FACTS, EXT-REPORT-METHOD, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-DISBURSEMENT-PROVIDER, EXT-PILOT-PERMITS |
| 69 | **W4-04A — role-based onboarding and training** | PKG-09 | TODO | Admin, advertiser and driver materials are rehearsed against the release candidate. | leaf: W4-03A, W4-03B |
| 70 | **W4-03C — controlled pilot and stabilization** | PKG-09 | TODO | Approved users run a monitored pilot with payout/report replay and rollback criteria. | leaf: W4-03B, W4-04A |
| 71 | **W4-04B — handover, support and roadmap closure** | PKG-09 | TODO | Owners accept deployment/system/support docs, known risks and post-MVP roadmap. | leaf: W4-04A, W4-03C |

## Checklist item specifications

Every card below is binding at outcome level. Before implementation, the active
agent expands the card into the delivery contract required by root AGENTS.md
and obtains the named independent reviews. Shared public contracts, schemas,
migrations, auth, money state, privacy controls and global lifecycle changes
remain single-owner and serialized.

Legacy names are aliases only: **S2** ≈ MNY-08A/B/C + MNY-09A; **S3** ≈
MNY-03A + MNY-10A/B/C + MNY-11A; **S5** ≈ the W2-01A billing opener. These
names never authorize work or replace the package queue.

### Early risk, W0 and W1

#### R14-A — production-PWA direction and protocol ADR

- **Scope / authority:** define the supported Android/iOS browser/device matrix,
  installability, screen-on/visibility contract, staged geolocation permission,
  BFF session posture, D15/D16 IndexedDB/Web Locks queue/seal compatibility and
  visible `active/degraded/stopped` health (§23, D18/RM17, Q10). Native
  background execution, native secure credentials and store release are Phase 2.
- **Acceptance:** ADR freezes the PWA threat/protocol/test matrix, names
  supported/rejected browser states and introduces no silent API/auth break.
- **Verify / review:** OpenAPI/BFF contract fixtures plus deterministic browser
  capability, denial and revocation probes and independent PWA/security/
  architecture review. Representative Android/iPhone execution is a D23
  post-build validation gate and is never claimed by this build proof.

#### R14-B — cross-profile interrupted-trip build proof

- **Scope / authority:** the installable PWA proves explicit Start/End,
  screen-on enforcement, permission and visibility degradation, durable
  IndexedDB queue, Web Locks single-writer, stable retry keys, seal watermark
  and BFF session recovery (§23, D18/RM17, D15/D16). Synthetic routes only.
- **Acceptance:** no acknowledged batch is lost/duplicated; desktop and mobile
  browser profiles show that reload, offline,
  permission revocation, storage/lock failure or screen/background transition
  recovers or fails closed visibly through trip→seal→worker payout. Physical
  device/browser completeness, latency, route accuracy and four-hour battery
  measurements remain incomplete post-build validation.
- **Verify / review:** deterministic capability/queue/tracker tests, desktop and
  mobile browser-profile synthetic journey, backend seal/payout integration and
  independent PWA/security/data-loss review. D23 defers, but does not waive,
  the representative physical-device matrix before real pilot use.

#### R17-A — production-like release/recovery build proof

- **Scope / authority:** verify the existing edge/API/frontend/PostGIS/Redis/
  worker topology, typed secret contract, migrations, queue-loss recovery,
  rollback design, observability, release smoke and database restore controls
  in a provider-neutral production-like build (§25, §31, RM17, Q32). Do not
  deploy externally or invent account/spend approval. The completed build proof
  did not execute a frontend-image rollback.
- **Acceptance:** production compose and edge configuration resolve, release and
  backup/restore safety contracts pass with synthetic data, and the sealed-trip
  worker path remains covered; no personal data or external environment claim.
- **Verify / review:** deterministic pre-production configuration, smoke,
  migration, worker-recovery and restore tests plus deployment/security review;
  frontend-image rollback is `NOT RUN — PKG02-C3` until its image reference is
  parameterized and the rollback is exercised before W4-03A.
  Approved-environment deployment, public-edge evidence and a live restore drill
  remain explicit D23 post-build validation before W4 release/pilot.

#### FND-02A — stationary-time policy decision

- **Scope / authority:** owner selects rolling displacement, cumulative
  sub-window budget or explicit fraud deferral; records parameters, effective
  timing, traffic/farming examples and D14 version consequence (§16.1, RM2,
  D2/D4/D9/D14, Q5). No code or invented thresholds.
- **Acceptance:** a decision-log row and executable fixture table fully define
  both honest congestion and stop-hop farming behavior.
- **Verify / review:** independent product/money review of the fixture table.

#### FND-02B — stationary policy implementation

- **Scope / authority:** implement FND-02A in eligibility classification,
  typed settings/rule overlays, money fingerprints and relevant admin/driver
  explanations. Excludes other fraud rules and production-PWA tracking.
- **Acceptance:** the known stop-4:59/hop pattern cannot farm pay; honest
  traffic matches the decision; eligible + excluded equals session duration;
  historical money remains reproducible.
- **Verify / review:** property/unit, PostGIS payout/recompute, driver UI/e2e
  tests; independent money review.

#### FND-07 — exclusivity conflict envelopes

- **Scope / authority:** map the four built vehicle/assignment/driver/trip
  exclusivity constraints to service-specific standard 409 envelopes (§6.4,
  RM7, D13, Q16). Do not redesign exclusivity.
- **Acceptance:** every losing race returns a stable code/message/request ID;
  unrelated integrity failures remain unexpected.
- **Verify / review:** classifier, concurrent assignment/trip and HTTP tests;
  API/concurrency review.

#### MNY-06A — immutable payout-rule revisions

- **Scope / authority:** replace in-place financial mutation with immutable
  effective-dated revisions, create/supersede APIs/UI and value-complete audit
  (§16.1, RM6, D9/D14, Q4/Q5/Q22).
- **Acceptance:** issued revisions cannot edit or overlap; history stays
  readable; every change records before/after values and reason.
- **Verify / review:** migration/model/API/UI/effectiveness/concurrency tests;
  independent money/security review.

#### MNY-06B — assignment/trip rule binding and `payout_v3`

- **Scope / authority:** add `payout_v3`; freeze accepted base/premium rates,
  cap, zone and eligibility revisions on assignment; each interval resolves
  base outside the premium target zone, premium inside, or a configured unpaid
  exclusion/invalid reason (§16.1/§21, RM6, D18/Q4/Q5). `payout_v1/v2` history
  stays immutable. W3 recommendation/offer redesign remains later.
- **Acceptance:** later revision never reprices accepted work; accept-vs-revise
  races are deterministic; payout fingerprint records all bindings; reports
  explain tier/reason and formula version; the D22 stationary marker and
  complete resolved values freeze at acceptance and unknown markers fail closed.
- **Verify / review:** acceptance→trip→payout integration, race and driver e2e;
  money/architecture/concurrency review.

#### MNY-06C — maker-checker correction orders

- **Scope / authority:** named adjuster creates projected correction order;
  separate approver submits/rejects/executes it; positive deltas remain pending
  with their own release date (§16.1/16.2, RM6, Q22).
- **Acceptance:** creator cannot approve; stale projection re-reviews;
  execution is idempotent; old/new values, reason and actors are audited.
- **Verify / review:** permission, delta, DB constraint, concurrency/retry and
  admin e2e; independent money/security review.

#### MNY-08A — current fraud assessments

- **Scope / authority:** add per-sealed-trip pending/clean/flagged/error
  assessment with version/fingerprint/currentness and convergent worker retry
  (§14/§17, RM8, Q21). Excludes UI/release.
- **Acceptance:** exactly one current successful assessment is required;
  changed inputs make it stale; failure stays error, never silently clean.
- **Verify / review:** migration, fingerprint/state and worker error/idempotency
  tests; money/concurrency review.

#### MNY-09A — cross-trip/account replay detection

- **Scope / authority:** canonical route/payload fingerprints detect identical
  and time-shifted replays across trips/accounts with configurable tolerance
  (§17, RM9, D13). Excludes device proof and physical spot checks.
- **Acceptance:** known replay fixtures flag explainably; legitimate distinct
  routes do not; same-trip idempotent replay is excluded.
- **Verify / review:** deterministic/property/PostGIS/scale tests; independent
  fraud/privacy review.

#### MNY-08B — review states and hold invariant

- **Scope / authority:** serialized acknowledge/confirm/dismiss lifecycle,
  reviewer evidence and one shared hold_active predicate for every money
  consumer (§16.2/§17, RM8, Q21/Q22).
- **Acceptance:** open/acknowledged/unresolved-confirmed stay held; only
  dismissed releases; illegal transitions and review/release races fail safely;
  a minimum-payout floor or second consumer predicate cannot restore held pay.
- **Verify / review:** transition, DB-race, payout/impression/release and admin
  e2e tests; independent money/concurrency review.

#### MNY-08C — driver reasons, disputes and in-app notice

- **Scope / authority:** sanitized hold reasons/status, dispute/reply lifecycle
  and transactional deduped in-app notifications (§17/§20, Q21/Q34). Excludes
  email, automated WhatsApp/SMS and push.
- **Acceptance:** only the owning driver accesses/disputes; internal evidence
  remains private; retry creates one dispute/notice; resolution notifies.
- **Verify / review:** authorization/redaction/API/worker and driver/admin e2e;
  privacy/security review.

#### MNY-03A — clean release and flagged review SLA

- **Scope / authority:** DB-derived idempotent sweep makes current-clean,
  unheld pending entries available without a blanket delay; suspected/flagged
  entries remain pending for named-admin approve/decline with a seven-day SLA
  and escalation (§14.3/§16.2, RM8, D18/Q22). Weekly cadence batches transfers;
  no hard-coded weekday and no timed auto-release.
- **Acceptance:** clean, held, dismissed and exact seven-day boundaries are
  deterministic; retry/concurrency move once; stale/error or active hold blocks;
  unresolved day-seven entries remain held and visibly escalated; corrections
  honor their own review state.
- **Verify / review:** frozen-time, balance, worker-twice, concurrency and ops
  UI e2e; independent money review.

#### MNY-10A — protected payee/account foundation

- **Scope / authority:** versioned payee abstraction with driver as pilot
  default, verified bank-account snapshot, privileged-read audit, and D17's
  shared crypto-provider port (`encrypt/decrypt/rotate`, key-version stamped per
  encrypted value) (§16.3, RM10/RM18, Q23/Q26/Q27). Pilot key custody is a
  required typed-Settings KEK with no default; excludes fleet behavior, full
  KYC and live verification provider.
- **Acceptance:** payout line freezes payee/account version; authenticated
  per-record envelope encryption records algorithm/key version and binds
  tenant/record/field as associated data; plaintext never reaches DB, list APIs,
  logs, audit payloads, exports, or errors; future fleet payee is data-only.
- **Verify / review:** ciphertext inspection, wrong-associated-data/failure,
  redaction/RBAC/migration/rotation/rewrap tests and synthetic driver flow;
  independent money/security review.

#### MNY-10B — batch reservation and provider submission

- **Scope / authority:** draft→reserved→submitted batch, atomic one-active-line
  reservation, frozen payee/account/amount/instruction hash, stable idempotency
  key, approved disbursement adapter and maker-checker before submission
  (§16.3, RM10, D18/Q22/Q23/Q27). Provider-neutral tests do not require live
  credentials.
- **Acceptance:** concurrent runs cannot double-reserve; total equals lines;
  exported snapshot is immutable and any prior change invalidates its hash.
- **Verify / review:** uniqueness/concurrency/property/instruction-hash,
  retry-idempotency, fake-provider/API/UI tests; independent money/security review.

#### MNY-10C — provider line reconciliation and paid finality

- **Scope / authority:** submitted→reconciled/completed|failed|void with unique
  provider line reference, signed webhook or verified polling, partial
  failure/idempotent retry and separate reconciler (§16.3, RM10, D18/Q27).
  `EXT-DISBURSEMENT-PROVIDER` gates financially effective submission.
- **Acceptance:** no batch-level assertion marks cash paid; failed lines stay
  unpaid/retryable; completion requires every line resolved; void safely
  releases reservations.
- **Verify / review:** state, duplicate reference, partial failure, retry and
  pilot-form e2e; independent money/security review.

#### MNY-11A — carry-forward post-payment debt

- **Scope / authority:** explicit earned-net/released/cash-paid/debt/
  batch-payable balances allocate later reversals against future credit
  (§16.2/16.3, RM11, Q22/Q27). No collections or negative transfer.
- **Acceptance:** reversal never increases balance; paid history is immutable;
  future credit clears debt before becoming batchable; currencies never mix.
- **Projection boundary:** economic/provenance totals retain every non-voided
  source and subtract reversals, while `debt_remainder` contributes zero.
  Settlement totals separately report released credit, cash paid, carried debt
  and debt-aware batch-payable amount; status changes made for allocation do
  not rewrite economics.
- **Verify / review:** cross-payment-boundary property and multi-period
  recompute→debt→batch e2e; independent money review.

### W2 commercial and operations

#### W2-00A — packages, custom quotes and accepted terms

- **Scope / authority:** versioned custom-quote request/record/accept path for
  every campaign and immutable accepted campaign snapshot with
  line/tax/production-cost/payment-class terms (§15.1/15.2, D18/Q1/Q2/Q14/Q25).
  An externally agreed quote/deal is recorded afterward as the same accepted
  terms, never as an unstructured note. A package catalogue is not launch
  scope. Excludes generated quote PDFs and public advertiser self-registration.
- **Acceptance:** every campaign has one accepted custom-quotation revision;
  accepted terms never mutate; advertiser ownership/RBAC and effective dates hold.
- **Verify / review:** migration/effective-date/mutation/cross-org tests and
  admin→advertiser acceptance e2e; architecture/money review.

#### W2-00D — advertiser company profile management

- **Scope / authority:** advertiser-owned company name, address, industry and
  operational/billing contacts are viewable/editable through tenant-safe
  advertiser and admin surfaces (proposal Module B/Month 2, §27). Separate
  these tenant facts from the platform issuer facts supplied under Q28.
- **Acceptance:** permitted fields and admin-only fields are explicit; cross-org
  reads/writes fail; changes audit before/after values; billing/campaign views
  consume the canonical organization record rather than copy it.
- **Verify / review:** schema/API/RBAC/audit/form-validation and advertiser↔admin
  e2e; authorization/privacy/commercial review.

#### W2-00B — canonical receipts and allocations

- **Scope / authority:** immutable receipt identity/evidence with unique
  external transaction ID, amount/currency/payer, observed→reconciled→
  confirmed|reversed lifecycle and separate allocation rows (§15.2–15.4,
  RM13a, Q2/Q3).
- **Acceptance:** one receipt cannot overfund or double-fund; mismatch cannot
  confirm; only confirmed allocations grant authority; reversal records cutoff.
- **Verify / review:** uniqueness/allocation-sum/row-lock/reversal property and
  admin reconciliation e2e; independent money/fraud/concurrency review.

#### W2-01A — VAT-itemised invoices

- **Scope / authority:** per-scope numbering, VAT-inclusive customer display
  with itemised included net, VAT amount and gross total, standard
  full-prepayment or immutable approved
  corporate-credit obligations, immutable issuance/correction rule, admin and
  advertiser billing surfaces (§15.1/15.2, D18/Q2/Q14/Q28).
- **Acceptance:** decimal/currency invariants; issued rows do not mutate;
  numbering is concurrency-safe; status derives from confirmed allocations;
  placeholder company facts cannot issue a real invoice.
- **Verify / review:** numbering/migration/VAT golden/RBAC/API and draft→issue→
  view e2e; independent money/accounting review.

#### W2-01B — manual bank-transfer confirmation

- **Scope / authority:** ops records/reconciles bank transfer, evidence and
  allocation; both parties see auditable payment history (§15.2/15.3, RM13a,
  D18/Q2/Q3). Standard production requires full confirmed funding; partial
  allocations remain visible but unauthorised. No bank API.
- **Acceptance:** over/under/partial cases are explicit; confirmation is
  idempotent; funding changes only from confirmed allocations; tenant isolation.
- **Verify / review:** invoice/allocation state, duplicate/mismatch adversarial
  tests and admin→advertiser e2e; independent money/permissions review.

#### W2-00C — funded liability authorization

- **Scope / authority:** immutable funded amount or approved-corporate credit
  authorization, subsidy, maximum driver liability and rate×cap×vehicle-day
  reserve/headroom with pending_funding state (§15/§16.1/§21, RM12,
  D18/D20/Q2/Q4/Q9/Q24). Credit approval snapshots limit, due date, approver
  and terms. Standard-prepaid production authority starts only at the exact
  24-hour boundary; expedited authority requires an immutable, versioned and
  audited advertiser-requested waiver, with actual production start recorded
  separately.
- **Acceptance:** liability differs from advertiser spend; concurrent activation
  cannot over-reserve; valid work remains payable after exhaustion; interval
  resolves then-effective terms; no production begins before valid authority.
- **Verify / review:** concurrency/property/effective-date/recompute/API/UI and
  exact-boundary/waiver/actual-start activation rejection e2e; independent
  money/architecture review.

#### W2-01C — gateway adapter and webhook ingestion

- **Scope / authority:** payment provider port, fake/manual adapter, selected
  provider checkout/verify, signed public webhook event log and async worker
  (§13–15.4, Q3, RM13a). Live adapter awaits provider/account decision.
- **Acceptance:** bad signature rejects; duplicate event is a no-op; request
  path only records/enqueues; retry converges to one receipt/allocation.
- **Verify / review:** signature/replay/enqueue/worker idempotency and sandbox
  simulation when credentials exist; security/money/deployment review.

#### W2-01D — credits, reversals and 24-hour refund registry

- **Scope / authority:** append-only invoice correction, receipt reversal and
  refund/settlement reference with adjusted advertiser balance. Eligibility
  normally runs to the exact 24-hour boundary from the first confirmed cash
  allocation authorising production. An expedited advertiser-requested waiver
  ends eligibility only when production actually begins; waiver acceptance
  alone does not. Corporate credit with no cash uses contract settlement, not
  a refund (§15.2/15.6, RM13a/b, D18/D20/Q24). Automatic execution is out.
- **Acceptance:** reversal never increases funding; original invoice/receipt
  remains; external refund reference is unique; refund cannot exceed authority;
  exact-before/at/after-24-hour, waiver-before-start, waived-start and
  no-cash-credit boundaries are deterministic.
- **Verify / review:** issue/pay/reverse/refund balance properties, duplicate
  races and API/UI e2e; independent money/accounting review.

#### W2-01E — advertiser-spend budget enforcement

- **Scope / authority:** billing-derived spend, configured threshold evaluation,
  persisted admin-visible threshold state, pause via the campaign service,
  idempotent worker and admin override/audit (§15.5, Q1/Q9). W2-04C alone owns
  alert delivery. Exact thresholds/timing need the recorded external policy;
  no predictive optimization.
- **Acceptance:** spend never proxies driver liability; retry does not duplicate
  threshold state or transitions; pause uses the campaign service; no hard
  delete or direct notification send.
- **Verify / review:** frozen-time/threshold/concurrent-payment tests and
  campaign e2e; money/worker/user-messaging review.

#### W2-02A — private object-storage foundation

- **Scope / authority:** storage port, local MinIO/provider adapter, presigned
  POST conditions, checksum/existence confirmation, private stored-file record
  and orphan lifecycle (§19/§25, RM18, Q18/Q26/Q32).
- **Acceptance:** no DB blobs/container files/public objects; expired,
  wrong-type, oversize or checksum-mismatch confirmation fails; tenants isolate.
- **Verify / review:** adapter/policy/CORS/confirm/replay/cleanup and upload
  simulation; independent threat/deployment/data-loss review.

#### W2-02B — malware scanning and purpose-scoped reads

- **Scope / authority:** server MIME/size validation, mandatory malware scan,
  quarantine/clear lifecycle, fail-closed review gates, short-lived purpose/
  reason GET and privileged-read audit (§12/§19, RM18).
- **Acceptance:** unscanned/infected/spoofed files cannot approve/download;
  URL expires; every privileged read records actor/subject/purpose/request.
- **Verify / review:** malware/MIME/oversize/retry/dedupe/URL/RBAC/audit tests;
  independent security/privacy/incident review.

#### W2-02C — advertiser creative upload

- **Scope / authority:** existing campaign wizard/detail uses managed scanned
  stored files with progress/retry and safe legacy-read compatibility
  (§19.2/19.3, Q18, D7/D11). Approval remains W2-03B.
- **Acceptance:** advertiser cannot claim ready/approved; scan failure is
  actionable; cross-org access fails; legacy URL cannot bypass launch gates.
- **Verify / review:** schema/actions/failure/retry/browser e2e; security/UX/
  backward-compatibility review.

#### W2-02D — encrypted KYC and financial identifiers

- **Scope / authority:** licence/registration/insurance/NIN/photos/agreement/
  bank linkage, versioned review, masking and purpose-authorized reveal using
  the same D17 crypto port/ciphertext schema introduced by MNY-10A (§19.3,
  RM18, Q26/Q27). Add the chosen KMS/vault-backed key-custody provider; do not
  create a second crypto mechanism.
- **Acceptance:** sensitive data is never plaintext in DB/API/logs; every value
  retains algorithm/key version/associated-data binding; KMS/vault migration
  changes key custody, not ciphertext schema, and includes a safe rewrap/
  re-encryption path; rejected/expired docs block approval; reads are audited.
- **Verify / review:** ciphertext compatibility, pilot-key→KMS rewrap and
  recovery, rotation/masked serialization/RBAC/read-audit/document-state e2e;
  independent privacy/KMS review.

#### W2-02E — file/KYC lifecycle and incident operations

- **Scope / authority:** file/KYC-specific retention and object/link purge;
  key-loss, scan-outage and storage-vendor failure handling; and closure of the
  D10(g) auth/profile/assignment audit gaps (§12/§19, RM18, D10). Whole-platform
  ROPA, breach register and end-to-end DSR belong only to W3-00A/B.
- **Acceptance:** purge leaves no public/orphaned object; KYC/financial retention
  exceptions are explicit; unsafe scanner/key/provider states fail closed;
  every named privileged mutation/read is audited.
- **Verify / review:** file/KYC retention dry run, key-loss/scan/vendor outage
  simulation and route-audit coverage; independent privacy/security/operations
  review.

#### W2-03A — campaign submission and approval

- **Scope / authority:** guarded draft→pending_review→approved path, reasoned
  rejection, admin queue and advertiser history (§18, Q6). Replace direct
  advertiser scheduling/activation; no parallel approval flag.
- **Acceptance:** advertiser cannot self-approve/launch; rejection is an action
  with reason; all transitions audit and serialize.
- **Verify / review:** enum/migration/state/race/RBAC and submit→review e2e;
  authorization/lifecycle review.

#### W2-03B — creative review gate

- **Scope / authority:** scanned creative pending_review→approved|rejected,
  revision/resubmission and admin queue (§18/§19, RM13c, Q18).
- **Acceptance:** advertiser cannot set review state; history remains; unsafe,
  rejected or replaced asset cannot satisfy launch.
- **Verify / review:** transition/RBAC/race and upload→scan→submit→review e2e;
  security/lifecycle/audit review.

#### W2-03C — installation evidence and proof-of-display

- **Scope / authority:** assignment-bound installation revisions, admin review,
  vehicle/device metadata and server-nonce start-of-shift proof with expiry/
  renewal (§18/§19/§21, RM9/RM13c, Q15/Q17).
- **Acceptance:** evidence binds exact assignment/vehicle; stale/rejected/
  missed proof blocks activation/earning; nonce cannot replay; reads audit.
- **Verify / review:** binding/replay/expiry/race and driver→admin e2e;
  independent fraud/security/privacy review.

#### W2-03D — atomic activation

- **Scope / authority:** named admin command locks/rechecks funding, liability,
  accepted terms, standard-wait or expedited-waiver production authority,
  creative, assignment, vehicle, evidence and exclusivity; stores immutable
  snapshot; trip start rechecks it (RM12/RM13c, D20/Q15–Q17/Q24).
- **Acceptance:** no TOCTOU race or driver self-activation bypass; failed-gate
  checklist is explicit; reversal/cutoff invalidates authority correctly.
- **Verify / review:** full gate matrix, activation-vs-funding races, snapshot
  immutability and admin→driver trip e2e; money/architecture/fraud review.

#### W2-03E — governed mid-flight changes

- **Scope / authority:** effective-dated change request, impact preview and
  classification; expansions consume funded headroom or wait; reductions/
  removals/date changes need admin reason (§15.5/§18/§21, RM12, Q9).
- **Acceptance:** accepted history stays immutable; concurrent funding/change
  cannot overauthorize; interval resolves the revision then in force.
- **Verify / review:** expansion/reduction/date/headroom/recompute and UI e2e;
  independent money/architecture/concurrency review.

#### W2-03F — cancellation cutoff and settlement

- **Scope / authority:** idempotent campaign lock sets immutable financial
  cutoff, stops assignments/new work, clips payable intervals, releases
  liability and appends settlement/refund revisions under W2-01D's standard
  boundary or actual-waived-production-start rule (§15/§18/§21, RM13b,
  D18/D20/Q24).
- **Acceptance:** every ingestion/classification/recompute/release path honors
  one cutoff; pre-cutoff hours pay; repeated command converges; refund ref is
  unique and never created after the applicable eligibility cutoff.
- **Verify / review:** boundary/property/cancel-vs-trip/release races and full
  cancellation e2e; independent money/concurrency/data-loss review.

#### W2-03G — proof challenges and spot checks

- **Scope / authority:** configurable high-earner evidence renewal, missed
  challenge/concurrent-session day hold, physical spot-check queue/result and
  audit, consuming MNY-09A evidence (§17/§19/§21, RM9).
- **Acceptance:** hold uses MNY-08B state machine; dismissal/release is
  authoritative; no claim that phone GPS proves the branded vehicle moved.
- **Verify / review:** synthetic challenge/false-positive/worker/hold-release
  and ops e2e; independent fraud/money/privacy review.

#### W2-04A — notification core and role surfaces

- **Scope / authority:** extend MNY-08C into shared outbox with status/attempt/
  provider IDs, transactional typed creator, list/read/preferences and polled
  unread badge for all roles (§20/§27, Q34). No WebSocket/SSE/push.
- **Acceptance:** business mutation and row are atomic; dedupe works; tenant/
  RBAC isolation holds; frontend uses BFF polling.
- **Verify / review:** rollback/dedupe/read/polling and role e2e; privacy/
  concurrency/frontend-architecture review.

#### W2-04B — advertiser email delivery

- **Scope / authority:** email port/adapter, typed templates, worker retry/
  backoff, sender configuration and signed delivery receipt (§15.4/§20, Q34).
  Live provider awaits account/domain; no marketing email.
- **Acceptance:** no inline provider call; one logical send across retries;
  provider ID unique; receipt cannot mutate another message; payload redacts.
- **Verify / review:** adapter/retry/dedupe/signature/replay and sandbox send
  where possible; security/privacy/delivery review.

#### W2-04C — business triggers and manual driver contact

- **Scope / authority:** assignment, approval, funding, budget, cancellation,
  evidence, fraud and payout events create typed deduped notifications; driver
  WhatsApp becomes an auditable manual ops task (§20.2, Q34, RM18).
- **Acceptance:** retry cannot double-notify; failure is visible; manual contact
  completion is recorded; no KYC/bank/raw-route data enters message/log.
- **Verify / review:** per-trigger transaction/redaction/failure/retry/manual
  completion e2e; privacy/operations/money-event review.

#### W2-04D — account recovery and verified contact preferences

- **Scope / authority:** advertiser/admin password reset uses single-use,
  expiring, rate-limited email tokens. Driver phone verification follows the
  §20.3 pilot flow: server creates a hashed short-lived challenge and ops work
  item; ops manually sends the code to the claimed number; the driver enters it
  in-product. Versioned WhatsApp opt-in/withdrawal then authorizes manual contact
  (§20/§23/§30, Q34). Automated WhatsApp/SMS remains post-MVP.
- **Acceptance:** tokens are hashed, one-use and non-enumerating; password reset
  revokes existing sessions; phone challenges are rate/attempt limited, expire,
  record sender/channel/timestamps without storing plaintext codes, and verify
  only the claimed phone version; unverified or withdrawn numbers cannot create
  a normal manual-contact task; consent history is auditable and purpose-limited.
- **Verify / review:** expiry/replay/enumeration/rate-limit/session-revocation,
  phone/consent transitions and role e2e; independent auth/security/privacy
  review.

### W3 reach and measurement

#### W3-00A — privacy operating model

- **Scope / authority:** DPIA, ROPA, controller/processor allocation,
  purpose/lawful-basis matrix, subprocessor/region and breach registers,
  consent/notice versioning and withdrawal procedure (§22/§24, RM15, Q31).
  Final client legal wording and live data remain out.
- **Acceptance:** every purpose/data class has owner, basis, retention and
  recipients; withdrawal and breach escalation are rehearsed.
- **Verify / review:** document cross-check and tabletop; qualified Nigerian
  privacy/legal review required before live use.

#### W3-00B — end-to-end retention and DSR

- **Scope / authority:** per-class retention and tested access/rectification/
  erasure process spanning DB, object storage, device queue, logs, backups and
  processors (§24.2, RM15/RM18, Q31). No automated DSR portal.
- **Acceptance:** synthetic request leaves traceable evidence without deleting
  required ledger/audit facts; every exception/location is documented.
- **Verify / review:** DSR dry run plus backup/object/device/provider checks;
  independent privacy/data-loss/operations review.

#### W3-00C — central disclosure-control service

- **Scope / authority:** one service gates existing heatmap, future audience
  queries, reports and exports with coarse buckets, minimum vehicles/trips/
  days, contributor caps, complementary suppression, restricted filters,
  query history and differencing defense (§22.2, RM15).
- **Acceptance:** no caller bypass; current advertiser heatmap remains disabled
  until migrated; thresholds remain config pending pilot-density evidence.
- **Verify / review:** adversarial suppression/complementary/differencing
  fixtures across all endpoints; independent privacy/security/architecture review.

#### W3-00D — measurement methodology contract

- **Scope / authority:** define modelled potential contacts, measured-vs-
  modelled hierarchy, units, provenance/vintage, missing-data rules,
  uncertainty, correction/reissue and prohibited view/reach/attribution claims
  (§22.4/§27, RM16, Q12/Q30, D20). Define Campaign Performance Analysis as
  the standard deliverable. Define true ROI only when advertiser conversion
  and revenue inputs plus an approved reproducible ROI method are all present;
  otherwise the ROI section and claim are omitted.
- **Acceptance:** every visible metric/label maps to a definition and
  uncertainty treatment; the ROI gate fails closed; terminology audit finds no
  overclaim.
- **Verify / review:** golden performance-only and true-ROI methodology
  fixtures, missing-input/method cases and copy audit; independent measurement/
  legal/commercial review.

#### W3-00E — immutable measurement runs and proof manifests

- **Scope / authority:** immutable formula-versioned run plus proof manifest
  linking creative, approved installation evidence, assignment, period,
  inputs/provenance and correction lineage (§22/§27, RM16, D20). The frozen
  input manifest records whether the report is performance-only or ROI-enabled
  and the approved method revision when enabled.
- **Acceptance:** frozen input reproduces result; changed input creates new
  run/reissue; missing proof or ROI prerequisite fails closed without silently
  relabelling performance as ROI.
- **Verify / review:** migration/reproducibility/fingerprint/lineage and report
  integration tests; independent measurement/architecture/audit review.

#### W3-01A — typed retargeting source registry

- **Scope / authority:** advertiser manages five D11 planning-source types;
  admin monitors; metadata is typed/allowlisted with provenance, basis, expiry
  and DSR fields; identifiers/uploads/free text are rejected (§22.4, RM16,
  D11/Q11).
- **Acceptance:** all types and lifecycle work; organization isolation holds;
  identity-like/free-text input fails clearly.
- **Verify / review:** API/UI/validation/expiry/provenance and admin-advertiser
  e2e; independent privacy/security review.

#### W3-01B — source/campaign/zone linkage

- **Scope / authority:** owned planning sources link to campaigns, target zones
  and time windows without raw-ping access (§22.4, D11/Q11).
- **Acceptance:** ownership/date/zone compatibility is server-enforced;
  cross-org and raw-data joins reject; link history is auditable.
- **Verify / review:** authorization/compatibility/lifecycle and advertiser
  setup e2e; privacy/authorization review.

#### W3-01C — governed exposure segments

- **Scope / authority:** worker materializes versioned campaign coverage-cell/
  time-window aggregates from approved analytics and applies disclosure
  suppression; no export activation (§22.1–22.3, Q11).
- **Acceptance:** retries converge; provenance/fingerprint drift makes stale;
  below-threshold cells suppress; organizations isolate.
- **Verify / review:** frozen-time/worker/idempotency/provenance/suppression
  tests; independent privacy/measurement/concurrency review.

#### W3-01D — recommendations, export and gated activation

- **Scope / authority:** advertiser reports/dashboard and admin monitoring show
  contextual geography/time recommendations derived from governed segments,
  with provenance/disclaimer/uncertainty; the same approved aggregate supports
  controlled export and an auditable ad-platform activation adapter
  (§22.3/22.4, D11/D18/D20/Q11). The outbound schema allowlists only aggregate
  geography/cell, time-window and contextual campaign fields; identifiers,
  raw routes and person-level payloads reject. No identity resolution. Live
  push fails closed
  until `EXT-AD-PLATFORM` supplies accounts, legal approval, API access,
  credentials and budget.
- **Acceptance:** no driver/trip/precise timestamp or person identifier is
  exposed; rejected payloads never reach the adapter; suppressed/empty states
  and access boundaries are correct.
- **Verify / review:** API/UI/report/export, fake-adapter approval/idempotency
  and fail-closed gate e2e plus terminology audit; independent privacy/
  measurement/security/claims review.

#### W3-02A — exposure score v1

- **Scope / authority:** formula-versioned campaign/route exposure score with
  documented inputs, missing-data and uncertainty behavior beside—not inside—
  impression estimates (§22.4/§30).
- **Acceptance:** frozen formula is reproducible; history never rescores;
  UI distinguishes score, impressions and contacts.
- **Verify / review:** golden formula/version-freeze/reproducibility and UI
  tests; independent measurement/architecture review.

#### W3-02B — high-exposure zone insights

- **Scope / authority:** governed ranked campaign/city cells or zones appear
  in advertiser/admin dashboards, maps and report sections (§22.4, D11).
- **Acceptance:** ranking/ties/empty/suppressed cases reproduce from the
  measurement run and always pass disclosure control.
- **Verify / review:** ranking/access/map/report/browser e2e; independent
  privacy/measurement/maps review.

#### W3-03A — matching recommendations

- **Scope / authority:** deterministic eligibility/scoring ranks driver/vehicle
  candidates; admin explicitly chooses, never automatic assignment (§21,
  RM9, Q7/Q16/Q19).
- **Acceptance:** stale candidate is rechecked; city/type/current-load and
  exclusivity rules hold; lost race fails safely.
- **Verify / review:** scoring/eligibility/race/query and admin e2e; fairness/
  concurrency/operations review.

#### W3-03B — complete offer lifecycle

- **Scope / authority:** terms-complete expiring offer supports driver accept/
  decline; accepted terms are immutable dispute evidence; admin final
  assignment/activation remains (§21, Q7/Q8).
- **Acceptance:** rate/dates/area/branding display; accept/decline/expiry races
  converge; no activation without accepted frozen terms and W2 gates.
- **Verify / review:** state/race/API and driver-admin e2e; independent money/
  audit/concurrency review.

#### W3-03C — activity floor and inactivity handling

- **Scope / authority:** configurable verified-hours/week and seven-day
  inactivity sweep create operations flag/notification without silently
  terminating assignment or earnings (§21, Q20).
- **Acceptance:** exact boundaries, retry and missing-analytics behavior hold;
  resumed activity recovers as designed.
- **Verify / review:** frozen-time/idempotent-worker/admin UI/e2e; money/
  operations review.

#### W3-04A — public driver application

- **Scope / authority:** abuse-resistant public registration creates pending
  application/user/profile and visible status; invite/referral stays a gate
  (§23, D1/D8, Q13). No work access or KYC approval yet.
- **Acceptance:** duplicate/enumeration abuse resists; pending user cannot enter
  work flows; admin sees queue.
- **Verify / review:** rate-limit/duplicate/auth-state/public→admin e2e;
  independent auth/security/privacy review.

#### W3-04B — KYC/bank onboarding approval

- **Scope / authority:** public applicant reuses W2 secure document, encrypted
  driver-identity/licence/agreement and MNY-10A payee/account flows; admin
  approves only the complete person/payee stage (§19/§23, RM18, Q23/Q26/Q27).
  Vehicle registration/insurance/photos and work eligibility belong to W3-04C.
- **Acceptance:** missing/rejected/expired/unsafe item blocks; resubmission and
  audit work; this approval remains **non-work-eligible** until W3-04C approves
  an active vehicle. Legal wording gates go-live.
- **Verify / review:** complete application→KYC→approval e2e plus security/
  encryption/read-audit tests; independent threat/privacy/money review.

#### W3-04C — driver vehicle profile and approval

- **Scope / authority:** an identity/KYC-approved but non-work-eligible driver
  creates and maintains the proposal Module C vehicle profile (type, plate,
  registration, insurance and vehicle photos) through explicit
  pending-review/approved/rejected/expired revisions; admin owns approval.
  Reuse W2 stored-file/KYC controls and existing vehicle/assignment invariants.
- **Acceptance:** a driver cannot edit another vehicle or self-approve; a
  material change invalidates the prior approval/evidence without rewriting
  history; work eligibility is granted only when driver KYC/payee and at least
  one active vehicle are approved; only such a vehicle may receive/activate an
  assignment.
- **Verify / review:** ownership/RBAC/revision/expiry/exclusivity/API and
  driver→admin→approved-vehicle e2e; security/fraud/operations review.

### W4 production PWA, launch and handover

#### W4-01A — PWA foundation and session security

- **Scope / authority:** production manifest/service-worker/installability,
  BFF-cookie session renewal/logout/revocation, staged geolocation permission,
  fail-closed IndexedDB/Web Locks capability checks and redacted logs (§23,
  D18/RM17/RM18). Native credentials/push/store assets are Phase 2.
- **Acceptance:** install/reinstall, session expiry/revocation, permission
  denial/revocation, missing storage/lock and unsupported browser states behave
  safely on representative Android/iOS devices.
- **Verify / review:** BFF/auth, installability, storage/lock and real-device
  tests; independent PWA/security/privacy review.

#### W4-01B — screen-on tracking and durable sync

- **Scope / authority:** production explicit Start/End, mounted-phone screen-on
  enforcement, visibility/background degradation, durable queue, stable
  idempotency, offline/retry and `active/degraded/stopped` health using D15/D16
  (§23, D18/Q10).
- **Acceptance:** no acknowledged loss/duplicate under reload, airplane/offline,
  low-power, permission, storage/lock or visibility transitions; unsupported
  background capture is never claimed; completeness/latency/accuracy/battery
  SLOs pass.
- **Verify / review:** Android/iOS browser/device matrix and live synthetic
  API/worker/seal journey; independent PWA/architecture/security/data-loss review.

#### W4-01C — PWA onboarding and campaign journey

- **Scope / authority:** integrate the governed application/onboarding, vehicle
  profile, recommendations/offers, activation and explicit Start/End tracking
  into the installable PWA through the BFF (proposal Module C as superseded by
  D18). This leaf owns client integration only; W3-04C owns vehicle backend/
  review behavior.
- **Acceptance:** supported Android/iOS combinations complete onboarding→
  approved vehicle→offer→activation→tracking with correct permission,
  screen/visibility degraded states and role access; the client cannot bypass
  server approval or activation gates.
- **Verify / review:** device/browser journey e2e across approval and tracking
  failure states; PWA/UX/security/fraud review.

#### W4-01D — PWA earnings, disputes and release rehearsal

- **Scope / authority:** complete campaign/trip history, `payout_v3` earnings
  breakdown, hold reasons/disputes, in-app notification integration,
  installability/offline shell and pilot distribution rehearsal (§23,
  D18/Q10/Q34). Store signing/listing and native push are Phase 2.
- **Acceptance:** money/history agrees with canonical backend balances; no
  sensitive location/KYC data enters notification/cache/log payloads; supported
  devices install and complete history→hold→dispute→outcome after reload/offline
  recovery.
- **Verify / review:** device/browser e2e, cache/redaction/session and install
  rehearsal; independent PWA/UX/security/money review.

#### W4-02A — governed maps and report experience

- **Scope / authority:** existing admin/advertiser maps and reports consume
  measurement runs, disclosure controls, safe labels, high zones, exposure
  score and contextual follow-up; admin raw route remains purpose-scoped
  (§27, RM15/RM16, D20). The standard title is Campaign Performance Analysis;
  ROI appears only when the frozen run records all required inputs and an
  approved method revision.
- **Acceptance:** no raw advertiser bypass or attribution/view/ROI overclaim;
  missing ROI prerequisites omit ROI; correct suppression/empty/access states
  and acceptable map latency.
- **Verify / review:** browser, performance-only and true-ROI golden fixtures,
  permission/load/terminology tests;
  independent privacy/measurement/maps review.

#### W4-02B — bounded CSV/PDF issuance

- **Scope / authority:** worker-generated basic CSV/PDF from frozen measurement
  run with hash/version/access/suppression/reissue; segment export remains
  disabled until Q31 (§27/§30, D11/D20/Q11/Q12/Q27/Q30/Q31). Issuance uses the
  Campaign Performance Analysis title by default and reproduces the frozen ROI
  gate decision. Build/test is synthetic performance-only per the register:
  `EXT-REPORT-METHOD` gates first live issuance at the W4-03B pilot gate, not
  this item's build entry.
- **Acceptance:** file reproduces source run, cannot leak suppressed data,
  authorization holds, legal switch fails closed and ROI is absent unless both
  required data and approved method are present.
- **Verify / review:** performance-only/true-ROI golden files, missing-input/
  method, hash/tamper/RBAC/worker retry/load/browser download tests; independent
  privacy/measurement/security review.

#### W4-03A — client-owned release environment

- **Scope / authority:** approved client account/domain gets hardened release
  candidate with secrets, object storage, managed PostGIS verification, TLS,
  observability and rollback/recovery (§25/§26, RM17, Q29/Q32).
- **Acceptance:** config/secrets/edge exposure pass; migrations roll; encrypted
  off-host backup restores; release smoke/load/security checks pass.
- **Verify / review:** deployment, rollback, restore, exposure scan and full
  smoke; independent deployment/security/data-loss review.

#### W4-03B — pilot gate and acceptance suite

- **Scope / authority:** one launch checklist mechanically proves G-money,
  G-GPS, G-commercial, G-advertiser, G-moduleG and G-pilot; records the real
  company/commercial facts, evidence policy, the approved measurement/ROI
  methodology (`EXT-REPORT-METHOD` — the live-issuance gate W4-02B builds
  against synthetically), Q26/Q31 legal/privacy approval,
  automated-disbursement provider readiness, D19 permit evidence and D18/D20
  Cardvert/Abuja pilot facts, reporting rule and owners (§35.3).
- **Acceptance:** full advertiser→admin→PWA→GPS→measurement→retargeting/export
  or aggregate contextual gated activation→Campaign Performance Analysis
  (plus ROI only when its gate passes)→automated payout→incident/recovery
  simulation passes or
  reports an explicit blocker. The planned cohort is Abuja, 10 vehicles, five
  paying advertisers and three months; coverage target is at least 60% of the
  target area.
- **Verify / review:** whole-system acceptance suite and independent launch
  review spanning privacy, money, security, architecture and operations.

#### W4-04A — role-based onboarding and training

- **Scope / authority:** admin, advertiser and driver materials cover real
  release-candidate flows; operator rehearses privacy, KYC, fraud, payout,
  reporting and incident procedures (D11, proposal Month 5).
- **Acceptance:** fresh users complete role tasks; every link/command/
  escalation path works and acceptance is recorded.
- **Verify / review:** facilitated usability and operator rehearsal;
  operations/privacy/money review.

#### W4-03C — controlled pilot and stabilization

- **Scope / authority:** only after W4-03B and W4-04A, approved pilot users run
  the D18 three-month Abuja cohort with GPS/battery/queue/report/payout/support
  telemetry, incident and rollback criteria. Developer supports initial pilot
  operations while training Somto's team (Q30/Q31/Q33).
- **Acceptance:** sampled reports reproduce; payouts reconcile; problems do
  not silently change policies/formulas; acceptance/deferment register signed.
- **Verify / review:** burn-in, incident/support records, report replay,
  payout reconciliation and rollback drill; operations/privacy/money review.

#### W4-04B — handover, support and roadmap closure

- **Scope / authority:** system/deployment docs, RACI, credential handover,
  backup schedule, support SLAs/escalation, known risks/deferments and
  evidence-linked post-MVP roadmap (D11, proposal final outcome).
- **Acceptance:** named owners accept artifacts; restore/incident handover is
  rehearsed; proposal/architecture/decisions/progress/repository agree.
- **Verify / review:** documentation link/command audit, ownership sign-off
  and independent architecture/operations closure review.

## Coverage proof

| Source requirement | Complete owning path |
| --- | --- |
| RM1, RM3, RM4, RM5 | Already built; preserved and inherited by R14-B/W4-01B |
| RM2 | FND-02A/B |
| RM6 | MNY-06A/B/C |
| RM7 | FND-07 |
| RM8 | MNY-08A/B/C + MNY-03A |
| RM9 | MNY-09A + W2-03C/D/G + W3-03 + W4-01 |
| RM10 | MNY-10A/B/C |
| RM11 | MNY-11A |
| RM12 | W2-00A/C + W2-03D/E |
| RM13 | W2-00B + W2-01B/C/D + W2-03D/F |
| RM14 | Native requirement deferred to Phase 2 by D18; R14-A/B + W4-01A/B/C/D now own the replacement production-PWA proof |
| RM15 | W3-00A/B/C + W4-02A/B |
| RM16 | W3-00D/E + W3-01/02 + W4-02A/B |
| RM17 | R14-A/B + R17-A + W4-03A/B/C |
| RM18 | MNY-10A + W2-02A/B/D/E + W3-04B/C + W4-01/03 |
| Proposal A — admin | W1 money operations + W2 admin queues + W3 monitoring + W4 reports/training |
| Proposal B — advertiser | W2-00D company profile + W2 commercial/creative/campaign flows + W3 retargeting/analytics + W4 reports |
| Proposal B advertiser registration exclusion | Operator-led advertiser/org onboarding per D1; public advertiser self-serve is proposal §8 post-MVP |
| Proposal C — driver pilot client (D18 override) | W3-03/04A/B/C + W4-01A/B/C/D production PWA; native background client is Phase 2 |
| Proposal D — analytics/impressions | Built engine + W3-00D/E + W3-01C/D + W3-02 |
| Proposal E — driver payouts | Built payout v2 history + MNY-06 (`payout_v3`)/08/03/10/11 + W2 earning gates |
| Proposal F — heatmaps/reporting | W3-00C/D/E + W3-02B + W4-02A/B |
| Proposal G — retargeting | W3-01A/B/C/D + W3-02B + W4-02A/B |
| §30 advertiser/admin password reset | W2-04D |
| §30 WhatsApp opt-in / phone verification | W2-04D; W2-04C consumes only verified active consent |
| §30 driver vehicle-profile ownership | W3-04C backend/review + W4-01C PWA integration |
| Pilot and handover | R17-A + W4-03A/B/C + W4-04A/B |

## External prerequisite register

These stable IDs never disappear from the queue. `PRESENT` requires evidence;
`MISSING` blocks any checklist item that references the ID. Missing live-use
facts that are not build-entry prerequisites remain gates but do not block an
otherwise synthetic/provider-neutral checklist item or its package.

| ID | State | Input | Evidence | Needed by / exact effect |
| --- | --- | --- | --- | --- |
| **EXT-STAGING-APPROVAL** | MISSING | External staging provider/account/spend approval | — | Deferred external staging deployment/restore validation and later W4 release/pilot; D23 says it does not block R17-A's provider-neutral build proof |
| **EXT-RM2-POLICY** | PRESENT | Owner-approved RM2 stationary policy and parameters | `docs/decisions-log.md` D22; reviewed synthetic Option A | FND-02B implementation binds 120s/25m/2-confirm/1-release/per-trip values for new acceptances |
| **EXT-PAYMENT-PROVIDER** | MISSING | Payment provider/sandbox/signing secrets | — | Live W2-01C adapter and provider refunds |
| **EXT-STORAGE-PROVIDER** | MISSING | Production object-storage provider, account and region | — | W2-02A production adoption |
| **EXT-MALWARE-SCANNER** | MISSING | Malware scanner/provider | — | W2-02B fail-closed scan integration |
| **EXT-KMS-CUSTODY** | MISSING | KMS/vault and production key custodian | — | Production W2-02 controls; pilot interim is D17's typed-Settings-key envelope encryption through the shared crypto port |
| **EXT-EMAIL-PROVIDER** | MISSING | Email provider and verified sending identity | — | Live W2-04B delivery |
| **EXT-BUDGET-POLICY** | MISSING | Budget alert/pause/resume policy | — | W2-01E enforcement |
| **EXT-PHONE-OPERATOR** | MISSING | Named phone-verification operator and approved manual WhatsApp/voice account | — | W2-04D pilot sends; generic challenge/consent tests remain synthetic |
| **EXT-BASEMAP** | MISSING | Production basemap provider/licence/account/API key | — | W4-02A map release and W4-03B; public CARTO defaults remain development-only |
| **EXT-STORE-ASSETS** | MISSING | App Store and Play accounts/assets | — | Phase 2 native signing/listing only; not a PWA-pilot prerequisite |
| **EXT-RELEASE-ENV** | MISSING | Q32 client-owned account/domain, provider, budget and access action for Cardvert | — | W4-03A release environment; ownership direction and brand are confirmed, actual environment is absent |
| **EXT-PILOT-FACTS** | PRESENT | Abuja; 10 vehicles; 5 paying advertisers; 3 months; Campaign Performance Analysis, offline-to-online targeting and at least 60% target-area coverage; developer supports the initial pilot while training Somto operations | `docs/decisions-log.md` D18/D20, Q30/Q33 | W4-03B uses the confirmed cohort and performance-report goal; true ROI remains conditional on `EXT-REPORT-METHOD` inputs/method |
| **EXT-REPORT-METHOD** | MISSING | Client approval of impression-estimation methodology/labels and, for any true ROI output, the required conversion/revenue input schema plus reproducible attribution, cost-basis, time-window, exclusion and correction method | — | Performance-only contracts can build/test; first live issued report needs approved measurement method, and ROI remains omitted until its additional inputs/method are approved |
| **EXT-Q28-COMPANY** | MISSING | Terrax Media registered issuer name, TIN, address, invoice wording and accountant confirmation | — | VAT-inclusive display with itemised net/VAT/gross is confirmed; real W2-01A invoice issuance waits for these statutory facts |
| **EXT-COMMERCIAL-VALUES** | MISSING | Custom-quotation values/components, commissions, base/premium payout rates and production/vendor values | — | Real W2-00A/MNY-06 commercial use; schema remains configurable |
| **EXT-EVIDENCE-POLICY** | MISSING | Evidence uploader/views/renewal and RM9 challenge/spot-check thresholds | — | Pilot W2-03C/G enforcement |
| **EXT-LEGAL-PRIVACY** | MISSING | Q26/Q31 wording, privacy owner and retention/DSR decisions | — | KYC/live GPS/retargeting go-live |
| **EXT-DISBURSEMENT-PROVIDER** | MISSING | Approved automated bank-transfer provider, account, sandbox, signing/webhook credentials and production approval | — | Provider-neutral MNY-10B/C can build/test; financially effective submission and W4-03B cannot proceed |
| **EXT-AD-PLATFORM** | MISSING | Named ad-platform accounts, legal approval, API access/credentials and activation budget for aggregate geography/time/context activation | — | W3-01D can build/test provider-neutrally; any live aggregate contextual push remains disabled; person-level activation is outside the pilot |
| **EXT-PILOT-PERMITS** | MISSING | Abuja permit/authority evidence for the selected vehicles/campaigns | — | D19 assigns Terrax ownership and vendor coordination; W4-03B/launch remains blocked until evidence is approved |
| **EXT-RM2-CALIBRATION-DATA** | MISSING | P1 parked-jitter and P2 Abuja-congestion field corpora (devices, participants, locations) per the owner-authorized 19 Aug 2026 Option-A collection program | — | Optional post-build calibration for a later effective revision; D22's reviewed synthetic selection is build-authoritative and this input blocks no checklist item |

### Deferred post-build validation register

D23 keeps the following evidence visibly incomplete. These rows are not claims
that physical or external validation ran; they preserve the later gate and the
owner/action needed to run it.

| Validation | State | Deferred evidence | Required before |
| --- | --- | --- | --- |
| **DV-PWA-PHYSICAL-MATRIX** | NOT RUN — DEVICE ACCESS REQUIRED | Representative Android/iPhone installability, grant/denial/revocation, reload/offline/visibility/storage/lock behavior and completeness/sync-latency measurements | W4 production-PWA pilot acceptance / any real driver GPS |
| **DV-PWA-ROUTE-BATTERY** | NOT RUN — DEVICE/ROUTE ACCESS REQUIRED | Controlled real-route accuracy and four-hour battery measurement on the supported physical matrix | W4 production-PWA pilot acceptance |
| **DV-STAGING-LIVE** | NOT RUN — EXT-STAGING-APPROVAL | Deploy provider-neutral topology to an approved external environment; capture public-edge smoke, worker recovery, exact backup marker/revision restore and rollback evidence | W4 client-owned release and pilot gates |

Post-pilot work remains explicitly deferred: the native background driver app
and store distribution, expanded recurring billing, edge-AI vehicle/pedestrian
counting and multi-city optimisation (architecture §31). Automated driver
transfers are pilot scope. Aggregate geography/time/context ad-platform
activation is D18/D20 scope but stays fail-closed until `EXT-AD-PLATFORM` is
present; person-level activation is outside the pilot.

## Canonical repository

`/Users/oluwasolaonigbinde/Projects/mobility-pkg01` on `feat/pkg-01`. The former
`mobility-master` directory was an obsolete Slice-0-only copy — never use it
to determine delivery status. When documentation conflicts, committed source
and Git history win.

## Delivered so far

| Stream | Status | Evidence |
| --- | --- | --- |
| Backend slices 0–13 (closed loop) | Complete | `docs/build-loop/slice-log.md`; closure commit `0dfb284` |
| Frontend F0–F6 (advertiser/driver/admin surfaces) | Complete as built demo/synthetic surfaces; the later RM4/RM5 PWA defects were closed by W0-F (D15/D16). Live authorization remains governed below. | Git `9189fe4`…`a5bcbb6`; `docs/archive/fablev1-work.md` journal |
| F7 auth/session hardening + audit + CI + backups | Complete, merged | Git `f40e0c4`…`236c2e4` (PR #1); architecture changelog v1.4 |
| Automated post-trip pipeline (arq worker) | Complete, merged | Git `159b0b1`, `4f69ef6`; architecture v1.5–v1.6 |
| S1 — payout engine v2 (hourly pay + daily caps, D2/D4/D9) | Complete, merged — RM1 fixed and the original whole-trip stationary grace retained for immutable payout-v2 history | Git `f9cd8ca`; architecture v1.8/v1.15, §16.1 [BUILT] |
| PKG-01 — foundations and empirical risk proof | Complete — RM2/RM6/RM7 closed; payout-v3 frozen parked-time behavior, PWA protocol/interrupted-flow build proof and provider-neutral release/recovery proof delivered; physical/live validation remains explicitly deferred | Git `d2cd424`…`be726a2` plus the package closure commit; architecture v1.30; D22/D23; automated/PostGIS/frontend/browser/recovery evidence |
| PKG-02 — money integrity and payout operations | Complete — RM8/RM10/RM11 closed; copied-route control, authoritative holds, clean release, encrypted payees, frozen provider instructions, line finality and carry-forward debt delivered provider-neutrally | Git through `e3a505e`; migrations `0022`–`0031`; architecture v1.37; Postgres/frontend/contract/synthetic end-to-end evidence and consolidated review resolved |
| PKG-06 / W3-03A — matching recommendations | Complete checkpoint — advisory cars-only ranking, explicit admin choice and concurrency-safe stale selection; later Package 6 items not started | `4cf15cd` plus corrected Package 5 adoption merge; architecture v1.48; focused PostgreSQL/backend/frontend/contract/live-stack evidence and consolidated review resolved |
| S4 — data lifecycle (ping partitions, retention purge, audit backfill, D10) | Complete, merged | Git `a879a3d`…`4f487e7`; architecture v1.9, §24.2 [BUILT] |
| W0-F — trip finality protocol + durable client queue (RM3/RM4/RM5, D15) | Complete — sealed-only money chain, post-seal quarantine, IndexedDB queue with stable retry keys; independently reviewed and hardened (D16: apply-after-initial-payout, pre-seal analytics recompute, fail-closed client) | Migrations `0016`+`0017`; architecture v1.16/v1.17; `tests/test_trip_seal.py`; live compose e2e |
| Pre-production ops (production Compose overlay, release smoke, backup/restore rehearsal) | Complete locally, **not deployed** | Git from `006d94e`; `docker-compose.production.yml`, `docs/runbook.md` |
| Current API contract | 31 migrations; controlled public baseline integration completed at PKG-02 closure | Payee/account, payout-batch, line-reconciliation, paid-balance and debt APIs are synchronized with the existing fraud/dispute/release contract across `docs/api/openapi.snapshot.json`, `openapi.json` and `schema.d.ts`. Later public endpoint/schema work must move all three artifacts together. |

**Nothing is deployed.** Staging/production remain research-only
(`docs/staging-options.md`) pending provider, budget, and operator approval
(Q32).

### Built does not mean live-authorized

Several useful interfaces predate the independent-review gates and may be used
only with demo/synthetic data until their owning checklist items land:

- Existing advertiser heatmaps/reports are **not live-authorized** under
  G-advertiser. W3-00D has supplied the safe build-time labels and methodology
  contract; W3-00C/E and W4-02A/B must still add disclosure control,
  reproducible measurement runs and governed issuance.
- PWA trip tracking and its durable queue are a tested protocol baseline, but
  **real-driver tracking is blocked** by G-GPS until RM2/RM9/RM15/RM18 close;
  W4-01 turns this surface into the D18 production screen-on pilot client.
- Payout rules, fraud review, release, encrypted payees, batch and reconciliation
  screens are provider-neutral synthetic foundations. The software G-money
  defects are closed, but **no real transfer is authorized** until
  `EXT-DISBURSEMENT-PROVIDER` supplies the approved provider and credentials.
- Current advertiser scheduling and driver activation flows are foundations,
  not the target commercial authority: G-commercial and W2-03A/D replace
  direct self-scheduling/activation before any live campaign.

## Where we are in the roadmap (architecture §31)

- **W0 — review remediation (new, 6 Aug 2026, D13):** **complete for PKG-01's
  built-code defects** — RM1
  fixed and RM2's renewable-grace half fixed 6 Aug 2026 (migration `0015`);
  **RM3/RM4/RM5 (trip seal protocol, stable retry keys, durable client queue)
  fixed 9 Aug 2026** (migration `0016`, D15, 465 tests green on PostGIS). It
  leads the remaining work. An independent code-verified review originally
  found seven defects in already-built code (architecture §35.1) plus eleven
  specification rows for unbuilt domains. RM1/RM3/RM4/RM5 are now closed,
  RM7 closed 16 Aug 2026 (PKG-01 FND-07, architecture v1.25); RM6 closed with
  payout-v3 revision/binding/correction authority, and RM2 closed under D22's
  acceptance-frozen rolling-displacement rule (architecture v1.30). Later
  tuning from real-route data creates a new revision and never rewrites history.
- **W1 — money correctness:** complete provider-neutrally. Worker, immutable
  payout history/corrections, data lifecycle, current fraud assessment and
  copied-route control, one hold predicate, clean/SLA release, encrypted payee
  versions, reconciled payout batches and carry-forward debt are built. Live
  transfer remains gated only by `EXT-DISBURSEMENT-PROVIDER`.
- **W2 — commercial layer:** not started. Billing/invoices (§15; W2-01A),
  file storage (§19), campaign/creative approval + installation evidence
  (§18), notification channels (§20).
- **W3 — reach:** not started. Retargeting at full Module G scope (§22),
  matching recommender + activity sweeps (§21), driver self-registration
  (§23).
- **W4 — production PWA + pilot readiness (D18):** not started. Installable
  screen-on PWA hardening/device proof, remaining CSV/PDF exports, Cardvert
  client-owned deployment, Abuja pilot and onboarding/training materials.

## Promise vs. delivery, by proposal module

| Proposal module | Built/demo-capable today (not necessarily live-authorized) | Outstanding / live-enablement owner |
| --- | --- | --- |
| A. Admin platform | Login/RBAC, user+org onboarding, drivers/vehicles, assignments, fraud review/disputes, payout rules/corrections, release SLA, payees, payout batches/reconciliation, traffic profiles and audit UI | Campaign/creative approval queues (W2), installation evidence (W2), retargeting monitoring (W3), exports (W4); live transfer provider input remains external |
| B. Advertiser dashboard | Campaigns CRUD, zones editor, analytics, demo heatmaps/reports/charts and payout-derived cost summaries | Company profile (W2-00D), creative *upload* (W2 — metadata-only today), billing/invoices (W2), governed approval/activation (W2), retargeting setup + insights, exposure score + high-exposure zone views (W3), disclosure-safe reports + CSV/PDF export (W4) |
| C. Driver app | Installable PWA: jobs, synthetic/demo trip tracking (idempotent ping batches), earnings + S1 trip breakdown, basic profile, durable offline ping queue + trip seal protocol (D15) | Offer accept/decline, self-registration, KYC and driver-owned vehicle lifecycle (W3); verified contact/notifications (W2); **production screen-on PWA/device proof** (W4). Native background app is Phase 2 |
| D. Analytics & impression engine | Route analytics, fraud flags, impression estimates, exposure/heatmap aggregation, payout eligibility classifier | Exposure score metric (`exposure_v1`) + high-exposure zone identification + retargeting insight capture (W3) |
| E. Dynamic driver payouts | Payout-v2/v3 immutable history, acceptance-frozen terms, maker-checker corrections, authoritative fraud holds, clean/SLA release, encrypted payees, frozen batches, line-level paid finality and carry-forward debt | Financially effective automated transfer remains disabled until `EXT-DISBURSEMENT-PROVIDER`; later KYC/provider approval lives in its owning packages |
| F. Heatmaps & reporting | Demo heatmap/route/report screens and daily metrics | Central disclosure/methodology/runs (W3), high-exposure zone + follow-up-targeting sections (W3), governed UI + CSV/PDF (W4); G-advertiser controls live use |
| G. Online-to-offline retargeting | — (privacy boundary designed, §22) | Entire module (W3): sources, segments, linkage, insights, controlled export and gated aggregate geography/time/context activation; identifiers/person-level payloads reject and live actions require legal/`EXT-AD-PLATFORM` inputs |

## Documentation authority

| Question | Source of truth |
| --- | --- |
| What the MVP must deliver | Direct client answers and approvals in `docs/decisions-log.md` D18–D20 override conflicting D11 proposal/default wording; the proposal remains scope context |
| How it is designed (current + target) | `docs/architecture.md` |
| Product decisions + Q1–Q34 statuses | `docs/decisions-log.md` (Part 1 history, Part 2 statuses) |
| What is authorised next and in what order | this file's package execution lock; checklist dependencies control internal checkpoints |
| What has been delivered so far | this file (control summary) → architecture changelog + Git/test evidence for detail |
| How to operate it | `docs/runbook.md` |
| Historical evidence | `docs/build-loop/` (closed backend ledger), `docs/archive/` |

## Update rules

1. A landed package updates this file in the same change: checklist evidence,
   package `DONE` status, ordered promotion/BLOCKED markings, both top control
   pointer/controller state, delivered-so-far row, wave position, and the
   module table. Exactly one package is active unless explicitly paused.
2. Client answers land in `decisions-log.md` first; if they change scope or
   design, `architecture.md` amends in the same commit — this file only
   records resulting *delivered* changes.
3. A future idea or owner request enters the relevant package/checklist before code is
   written. Only the project owner may intentionally reorder it; record why.
4. A package `DONE` claim requires every owned checklist item `DONE`, plus
   implementation, deterministic verification, a live
   simulation proportional to risk, required independent review, docs, and
   concrete evidence. Code alone is not completion.
5. `docs/next-steps.md` and `docs/build-loop/` may inform a plan but never
   authorise a package or override current architecture §35.

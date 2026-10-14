# Final in-house fixes — approved 14 October 2026

Owner authorizes implementation, ordered separate commits, branch push,
end-of-batch full CI (D33 measurement/receipt/verification if required), and
non-squash master merge only after green branch CI. Work stays in the clean
`final/inhouse-fixes` checkout, initially identical to fetched master
`966abd3a`. The outside-repository triage report is read-only context.
Requests are REQ-171–179. This is owner work, not package-queue promotion.

## Contract and sequence

1. **A09 / REQ-171, security:** cap the public webhook body at 1 MiB in Caddy
   and count streaming app bytes before appending or signature verification.
   Declared oversized bodies fail before reading; chunked/false-length bodies
   cannot bypass the cap. Authenticate the exact original bytes. Preserve
   signature/configuration refusals and durable payment/transfer replay behavior.
   Entry points: `Caddyfile`, `app/api/v1/webhooks.py`; focused fake-only
   `tests/test_paystack_webhook_api.py` regressions.
2. **A01 / REQ-172, trip evidence/money:** isolate remote server-action errors
   from queue operations in `trip-tracker.tsx`. A rejected Flush promise retains
   batches/keys and healthy queue state and captures only while existing
   session/offline authority allows. End transport uncertainty reconciles saved
   manifest/server state rather than declaring IndexedDB failed. Genuine queue
   errors still stop capture and fail closed. Verify Flush and End rejection,
   actual storage failure, retry identities and recovery in tracker tests.
3. **A02 / REQ-173, money:** serialize initialization/reconciliation per saved
   checkout, including across the pre-I/O commit. Reconcile unknown references
   through existing adapter verification and canonical event ingestion; retain
   immutable invoice/tenant/terms/amount/currency binding and audit recovery.
   If absent, retry only the SAME saved idempotency reference, never create a
   replacement. Ambiguous, duplicate-reference or failed recovery responses keep
   uncertainty; no cash authority comes from initialization. Verify process
   death before dispatch and provider acceptance followed by failed local save,
   concurrency/replay and unchanged binding using fake I/O in checkout tests.
   Prefer existing PostgreSQL locking and audit patterns; add schema only if
   code review proves durable recovery needs it.
4. **A03/A10/A11 / REQ-174–176, privacy/measurement:** make issued measurements
   plus active current source links durable discoverable work. Add a bounded
   monitored catch-up sweep using the existing materializer and its deterministic
   replay/facts identity; creation order and lost immediate enqueue must recover.
   Reject obsolete measurement/score and stale source/campaign/zone/link parents
   at worker execution. No raw-ping reader or new aggregation/disclosure authority.
   Prove an unseeded source→link→measurement→worker→ready/suppressed journey
   without materializing in fixture setup, plus duplicate catch-up and stale work.
   Planning shows named governed geography/coarse cell, Nigeria-time hours,
   rationale, uncertainty, human-readable provenance and existing disclaimer;
   preserve ready/suppressed/stale/unavailable views and no advertiser hashes.
   Freeze linked-source contextual recommendations from the SAME issuance run
   through existing access/disclosure checks; deterministic CSV/PDF rendering
   includes their names/time/rationale/provenance/uncertainty/disclaimer, with
   snapshot hashes and artifact integrity retained. Existing issued snapshots
   remain immutable; any actual API change moves all §9 baselines together and
   reruns R14-B native fixtures. Planning instant formatters use Africa/Lagos;
   date-only values retain their date. Test midnight under UTC and non-UTC hosts.
   Entry points: audience/materializer/delivery, measurement and worker jobs,
   report issuance/rendering, planning page and formatting; only affected tests.
5. **A04 / REQ-177, privacy/security:** keep per-file in-memory progress bound
   to exact File object, access/session context, purpose and stable request ID.
   Retain intent, storage-upload completion, confirmed ID and clean-scan stage
   independently. Resume unfinished upload/confirmation/polling and reuse clean
   siblings; no sensitive state in persistent browser storage. Apply person/car
   and driver renewal callers retain generation fencing, owned clean-file
   authority and existing scan refusals. Test polling failure and one-of-two
   failure/retry plus file/access edits and late responses in helper/caller tests.
6. **REQ-178, docs only:** close REQ-036/040/045/047/059/060/061/063/067/068/
   071/075/118 using integrated evidence from the triage; REQ-044/055 become
   SUPERSEDED with their replacement reason per the owner's explicit convention.
   Preserve all other rows, including unanswered and external dependencies.
7. **A06 / REQ-179, later owner decision, docs only:** the pilot is car-only;
   motorcycles are deferred until the owner or client raises them again. Record
   D88/Q19 and architecture v1.143, move the previous motorcycle-permitted rule
   into dated history, and retain all vehicle_type plumbing and code unchanged.
   This unambiguous record aligns docs with existing car-only Apply/matching
   behavior and follows the delivery skill's direct path. The tidy-up had already
   been committed and pushed before this decision arrived, so A06 is a separate
   later commit preserving published history and the no-force-push boundary.

## Boundaries, records and gates

Reverify every defect against current master before fixing and skip already-fixed
items. No legacy payout/evidence/SQLite/migration restoration, A06 code, G04, coverage
padding, new commercial/legal/eligibility values, account-access or tmp reads,
provider calls, deployment, client demo (3100), main checkout changes or force push.
Allocate D84+, architecture v1.139+ and migration 0107+ only for genuine changes.
Update genuine design/product decisions and operational instructions alongside
their implementation, preserving existing client rules and live-use gates.

One independent plan reviewer, then one consolidated post-build reviewer applying
minimal-change-review through PASS; separate money, privacy and security reviews
cover their named items. Owner-selected reviewers: provider
`codex-fresh-20261012`, `gpt-6.1-sol`, high, serviceTier priority; propagate these
settings to any delegation. Fresh delegate_task/full packet for every round;
prior objections and corrections accompany reassessments. At most parent plus
one reviewer/worker active. Provider context/handoff error stops with a report.

Local tests run only touched test files, with no coverage and at most two named
batch-owned containers; remove those at completion. Establish defect regressions
before correction when feasible. Record criterion verdicts and actual evidence
once final implementation/verification stabilize. Full CI is an end-of-batch gate;
do not weaken coverage, inventory or checker. If master advances, merge it into
the branch preserving both request sets, reverify affected criteria and obtain
green integrated branch CI. Commits use configured identity and explicit paths,
normal hooks. After authorized green merge, close new requests with implementing
SHAs and send final report to the owner's specified T3 thread.

## Plan review

Independent plan review (gpt-6.1-sol high/priority, requested provider), round 1:
FIX. All five findings are accepted and amend the contract as follows; no scope
increase or unresolved product decision is needed.

- A09 applies the same bounded reader to both public payment webhook routes.
  Verify Caddy configuration with the deployed version without another test
  container (binary in the runner), and test exact-cap/cap+1, absent/false length,
  pre-auth/persistence refusal and unchanged-byte signatures.
- A02 uses a PostgreSQL session advisory lock on a separately owned connection
  with a recovery session bound to that same connection across commits and
  provider I/O, with guaranteed unlock or
  connection invalidation on failure. Initializer and explicit verification use
  that same saved-checkout lock before checkout row locking; prepare's invoice
  lock ends before acquiring it. Webhook confirmation remains an independently
  serialized canonical event and must win over any later URL save. Verify
  barrier-controlled separate-session initialize/recover/verify, release after
  failure and intervening webhook confirmation. Recovery duplicate/malformed or
  ambiguous replies never set FAILED or permit a new reference.
  The caller's read transaction ends before waiting; owners need no second
  pooled connection to publish, avoiding pool starvation from blocked waiters.
- A03 selects non-superseded reproducible runs and checks supersession at BOTH
  worker and recommendation-reader boundaries. Delayed older jobs cannot make
  old output current. Durable discovery/dispatch isolates each pair's failures
  and guarantees progress beyond a stale/incompatible prefix, with empty-cell
  suppression counting as completed work. Use existing immutable run/link facts
  as durable work wherever sufficient; add a small durable work/cursor record
  only if needed for fair bounded catch-up. Test both creation orders, missed
  dispatch, more candidates than the scan bound and reissue before catch-up.
- A10 selects recommendations by the exact issuance run, orders them
  deterministically and freezes governed source/zone labels and human context.
  Missing/suppressed/stale recommendations have explicit state and no released
  targets. Parent checks must stay stable during composition using existing
  source→campaign→zone→link order; never acquire campaign then source. New export
  snapshots are versioned. Verify real local fake-storage issuance→publication→
  download, denial/tamper, and immutable historical bytes after parent edits.
- A04 adds (rather than claiming existing) renewal context/unmount fencing,
  scoped to driver identity, current submission and vehicle; preserves Apply
  fencing. Coalesce running same-identity uploads so an early Promise.all
  rejection cannot duplicate its continuing sibling. New same-content File
  objects create distinct state, unchanged siblings remain reused, and token/
  context edits fence old results. Test those races and lost confirmation
  response using idempotent confirmation, without restarting a closed intent.

The amended contract implements the owner's already-approved behavior and scope;
implementation proceeds under that approval. Consolidated post-build and named
specialist reviews remain pending, with every criterion still requiring evidence.

Temporary writer capacity is three (controller plus audience worker plus upload
worker) while audience verification runs. Disjoint ownership: controller owns
webhooks/tracker/billing and all delivery/product docs; audience worker owns only
audience/measurement/report/worker/migration0107 and their named tests; upload
worker owns only onboarding-upload helper, Apply person/vehicle forms and upload
retry tests, renewal form and renewal tests. Only audience owns the DB test window;
controller/upload frontend runs use separate local source copies with read-only
shared dependencies. No concurrent writes to any file or shared verification
source tree, no worker commits. Controller preserves the ordered commits.
Capacity returns to controller plus one reviewer after implementations complete.

## Post-build checkpoint

Final source through `dfa5f1c3` implements all approved code items; the original
defects were reverified on master before correction. Money PASS, privacy PASS
after correcting both disclosure transaction boundaries, security PASS, and
consolidated minimal-change-review round 1 PASS. Criterion evidence is recorded
in `issues/testing/final-inhouse-fixes-2026-10-14.md`. No scope increase, unanswered
product choice or provider context/handoff failure occurred. Full branch CI,
any required reviewed D33 receipt, green non-squash merge and new-request closure
remain pending. The owner-approved historical request tidy-up is committed;
REQ-171–178 remain IN PROGRESS until delivery reaches master.

The later docs-only A06 decision is `e2fdef5b` (REQ-179/D88/v1.143). Initial
full CI on `2ee9c585` surfaced one missed current-head assertion in the existing
agreement-retirement test: it expected baseline 0106 after upgrading to head,
while A03 adds 0107. The narrow expectation correction passes both tests in that
touched file and preserves their agreement/retirement checks. Consolidated
reassessment PASS covers the docs-only A06 decision and this expectation fix.
Successful complete CI remains required; failed-run artifacts cannot
qualify a D33 receipt.

## Behavior-test continuation after D33 measurement

The owner resumed the D33 block on 14 October: test this batch's own uncovered
behavior, retain the adopted exact ratios and unchanged checker, then perform
measurement, reviewed receipt, verification and final consolidated reassessment.
No new product rule, D-row, version or migration is needed. This continuation
refines verification of REQ-171�177; all additions belong in one test commit.

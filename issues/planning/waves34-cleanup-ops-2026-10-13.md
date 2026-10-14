# Waves 3 and 4: preparation and delivery boundary

Owner authorization: 13 October 2026, current worktree and
`w3/cleanup-refactor-ops`. Initial fetch succeeded; HEAD and origin/master
both equal `870740531a8625b9350b030fe05107276e0f345a`. Working tree was clean.
Scope source: only Wave 3, Wave 4 and the must-not-forget list in the owner's
5 October batch plan, amended by the current instructions.

## Request mapping

Plan REQ-115/116/117/118/119 map by subject to newly registered
REQ-161/162/163/164/165. Existing rows with the old numbers concern different
work and remain intact. REQ-166 covers obsolete hosting files, REQ-168 the
integrated delivery. Report wording and demo phones already map to
REQ-141/145; the shared bank picker remains REQ-159. REQ-167 records the
owner's answered squash question; REQ-169 records its implementation.
W3a allocates D80, architecture v1.135 and migration 0103. Later waves and the squash allocate fresh numbers in their own commits.

## Proposed contract and order

1. W3a: remove old payout engines and evidence-v1 runtime paths and consumers;
   retain v4 daily-rate/correction/financial integrity and exact signed v2
   evidence. Remove SQLite application branches and use PostgreSQL tests.
   Record the live-data-only accepted-work preservation decision; there is
   no live data. Update the three API baselines and R14-B fixtures together
   when contracts change. Retain meaningful financial and evidence regressions
   when replacing old fixtures.
2. W3b: split payout and billing services by domain, update actual callers,
   refactor measured hotspots, and replace application file-wide C901 ignores
   with exceptions on existing offenders. Preserve the shared bank picker.
   Ping ingestion uses a shared campaign lock in campaign-before-trip order;
   cancellation and terms mutation retain exclusive authority. Deterministic
   PostgreSQL tests must cover different-trip readers, same-trip serialization,
   waiting writers and both cancellation/ingestion orderings without upgrades.
3. Coverage: require 85% branches separately for the combined money group and
   the combined privacy group (not 85% per individual file). Money includes
   `services/payouts/`, `services/billing/`, `payout_corrections.py`,
   `payout_debt.py`, `payout_eligibility.py`, `payout_operations.py`,
   `payout_rule_serialization.py`, `automatic_payouts.py`, `disbursements.py`,
   `paystack_disbursements.py`, `earnings_release.py`, `payees.py`,
   `campaign_cancellations.py`, and all Python modules under
   `adapters/payments/`, `adapters/disbursement/`, `adapters/budget/`.
   Privacy includes `services/disclosure.py`, `data_subject_inventory.py`,
   `data_subject_requests.py`, `data_lifecycle.py`, `file_kyc_lifecycle.py`,
   `stored_files.py`, `stored_object_deletions.py`, `kyc.py`,
   `core/observability.py` and `adapters/crypto/`. Paths are beneath `app/`.
   The checker enumerates tracked source under these directories; absent
   expected modules and missing executable coverage fail closed. Empty package
   files contribute no executable branches. Preserve existing D32/D36/D41
   ratchets and frontend eligibility; optional narrowing is declined because
   frontend account, evidence, authorization and queue logic is consequential.
   Add unconditional deterministic tests for the reservation refusal and trip
   rejection path identified in prior CI. No local coverage measurement.
4. W4: monitor every scheduled job using Sentry Cron check-ins; add the
   five-minute seven-condition business-health sweep and runbook. Use the
   concrete operational predicates below, active-admin notifications and the
   existing Finance alert surface. No local external delivery/provider calls.
5. Trim: inventory every proposed deletion, preserve validator-consumed
   progress state and meaningful behavioral tests, archive completed history,
   delete proven unused scripts and replaced Render/AWS/Mapbox assets.
   REQ-049 is already on master. Keep Hetzner's S3-compatible integration.
6. Squash LAST in a separate commit, as explicitly approved by the owner
   ("squash yes"). First upgrade a clean PostgreSQL database through the
   completed W3/W4 chain and dump its full schema. Compare a fresh upgrade
   from the single baseline using the same dump procedure: identical except
   alembic_version value. Preserve tables, types, defaults, constraints,
   indexes, sequences, enums, functions/triggers, partitions and management
   objects, extensions, grants and RLS. Preserve bootstrap data too, including
   0093's disabled automatic-payout actor and matching fingerprint. Retain
   current DB-behavior tests in baseline-focused tests before deleting old
   per-migration tests. Exactly one head/root, update operational revision
   references, and run the existing demo seed once. Security/privacy review
   explicitly verifies no protection was lost.
7. Only touched tests locally, at most two test containers; no changes to the
   port-3100 demo, account-access document or tmp. Sequential reviewable commits
   under configured identity, explicit path staging and normal hooks. Named
   money/privacy/security reviews plus consolidated minimal-change PASS on the
   final implementation; final full CI covers squash and D79 agreement/bank
   integration. Nontrivial agreement/bank defects are reported; small fixes get
   their own REQ-158/159 commit. Merge only green without squashing, then close
   requests; preserve both request sets if newer master must be merged.

## Alert predicates and verification

Operational defaults are monitoring sensitivity, not client money, eligibility,
retention or GPS acceptance rules. Each query uses an injected UTC clock and
bounded/indexed counts; the sweep never mutates payments or trip authority.

| Check | Unhealthy predicate |
| --- | --- |
| Stuck payouts | Nonterminal submitted/submitting payout lines or unresolved submission intents older than 60 minutes; use latest durable progress timestamp where present. |
| Unprocessed webhooks | Unprocessed payment or payout provider events older than 15 minutes, including failed retryable events. |
| Paused payouts | Control is paused and its recorded changed_at is strictly older than 24 hours. |
| GPS rejection spike | At least 20 authenticated ingestion attempts during the preceding 15 complete UTC minutes, with at least 25% wholly or partially rejected for GPS validation. |
| Stale trips | Active trips with no accepted ping/start activity for 30 minutes, or ended unsealed trips past the configured evidence grace whose evidence_adjudicated_at is null. Terminally adjudicated incomplete trips are settled evidence outcomes, never stale. |
| Partitions | Existing partition-coverage service reports less than its required now-plus-one-month coverage. |
| Email failures | Terminal failed deliveries in the last 24 hours or pending deliveries older than 15 minutes. |

GPS metrics use aggregate minute counters with a one-hour TTL in the existing
Redis substrate, recorded independently from the ingestion transaction so an
all-rejected batch remains observable. Store no driver, trip, IP, coordinates,
payload or free text. Count attempts (including rejected retries), not unique
trips. Partial and full GPS rejection use the same denominator; idempotent
successful retries do not create new evidence. Counter failure is logged safely,
does not change ingestion authority, and the sweep must report unavailable
telemetry rather than a healthy GPS result. Test with fake Redis; real PostgreSQL
tests cover durable predicates and concurrent deduplication.

Extend the existing Finance alert kind with a business-health kind and allowlist
the check key/count in detail. Reuse `raise_alert` and `create_active_admin_notices`:
all active admins are Finance recipients under D38e/REQ-030 (no separate roles).
One alert/notification per unhealthy check per UTC date, transactionally deduped.
Persistent failures may recur on the next date; recovery emits no new alert and
never silently resolves a human-owned Finance item. Finance explicitly follows
up existing items. Boundary, healthy, unhealthy, repeat and missing-telemetry
tests are required; Cron tests cover success, exception and cancellation without
external calls. Sentry telemetry contains only stable monitor slug/status.
Stale-trip tests must prove overdue unresolved evidence alerts and terminally
adjudicated trips do not, including on the next UTC date; existing Finance items
remain manually resolved.

## Independent plan review and reconciled findings

Reviewer: `codex-fresh-20261012`, `gpt-6.1-sol`, high reasoning, priority.
Task: `node:delegated-task:command%3Amcp%3Ab10cc452-1217-49d9-b8c0-380e2a77edda%3Adelegate-task%3Aw34-plan-review-20261013-r1`.
Verdict: FIX. Accepted findings: preserve bootstrap data and migration-defined
protections; require concrete alert predicates, lock interleavings and explicit
85% scope; incorporate the approved squash parity requirements. Those details
must be completed and reviewed before implementation, not claimed passed here.

The original blocking finding was procedural: `check_changed_coverage.py:839` rejects
changed inventory/policy without D33 refresh. Final CI measurement produces
the input to the reviewed receipt; committing that receipt creates a different
candidate that D41 requires full CI to verify. Exactly one run cannot satisfy
both. The orchestrator continuation now directs two end-of-batch runs under
REQ-170: final-source measurement, independently reviewed canonical D33 receipt
commit, full verification of that commit, then green-only non-squash merge.
No per-wave CI, waiver, CI-generated receipt or local measurement is assumed.
The owner approved this sequence on 13 October, as relayed by the orchestrator.
The measurement and reviewed receipt also cover REQ-158/159 changed code;
any additional agreement/bank tests have their own labelled commit. Their
previous coverage-policy-only CI failure is superseded by final green batch CI. A fresh
independent plan review must return PASS before application changes.

Round 3 (`w34-plan-review-20261013-r3`) returned independent **PASS** on the
complete revised plan, including the terminal-adjudication exclusion. Existing
owner implementation approval covers this unchanged scope; implementation may
proceed. This plan verdict does not claim implementation or final-review PASS.

Round 2 (`w34-plan-review-20261013-r2`) accepted the prior refinements and
returned FIX only for terminally adjudicated trips being included in the
stale-trip predicate. Accepted and corrected above; round 3 reassessment returned PASS.

## Actual preparation evidence

- Master run 38390542839 completed: all six backend shards, e2e, R59, static checks and frontend lint/types/unit/contract/build passed; only changed-code coverage policy failed. Runs 38390436639 and 38390315083 also concluded failure. The orchestrator confirms the repair run was coverage-policy-only; the owner-approved batch D33 refresh/final verification supersedes that failure. Master run:
  https://github.com/oluwasolaonigbinde/mobility/actions/runs/38390542839.
- Radon 6.0.1, `radon cc app -a`: 3,299 blocks; mean complexity
  3.7356774780236437 (A). Raw pre-change JSON is ignored local evidence at
  `coverage/w34/radon-before.json`. No after measurement yet. jscpd 4.0.8 on a pristine HEAD archive, `app frontend/src --ignore "**/*.test.*,**/schema.d.ts" --format python,typescript,tsx`: 788 sources, 110,697 lines, 245 clones, 2,861 duplicated lines (2.58%), 30,683 duplicated tokens (2.86%). Raw report: ignored `coverage/w34/jscpd-pristine-before/jscpd-report.json`.
- W3a implementation is in progress. Schema parity, seed run, commits, push and merge remain outstanding. Squash: approved, not done. Deletions are listed below.
- Two isolated containers are retained during the task and their removal at
  completion is now explicitly authorized: `cardvert-w34-postgres` (localhost
  55434) and `cardvert-w34-runner`. Existing containers/demo remain untouched.

## Deleted inventory

Obsolete hourly/distance rule editors and their dedicated test (daily-rate editor retained):
- `frontend/src/app/admin/payouts/rules/rule-form.tsx`
- `frontend/src/app/admin/payouts/rules/revisions-panel.tsx`
- `frontend/src/app/admin/payouts/rules/revisions-panel.test.tsx`

Retired payout engine suites (current acceptance, correction, daily-cap ordering and API boundaries transferred to daily-rate tests):
- `tests/test_payouts_v2.py`
- `tests/test_payouts_v3.py`

W3a fresh database `w34_validate`: complete chain to 0103 upgraded successfully and `alembic check` reported no new upgrade operations. This is migration/model alignment evidence, not the final squash parity comparison.

W3a checkpoint (14 October): legacy runtime/schema/API/editor removal and
PostgreSQL fixture conversion are implemented. Ruff and diff whitespace pass;
API snapshots and TypeScript schema regenerated. The focused daily payout, debt,
frozen acceptance, publication, ordering and API batch passed 67 tests. Four
payout UI files passed 14 tests. Additional worker/trip/privacy/seed verification
is still running after fixture corrections; this is not final verification or
review acceptance. No coverage measurement, branch CI, push or merge has run.

W3b planned source-file replacements (functions move into domain packages):
- `app/services/payouts.py`
- `app/services/billing.py`

W3b checkpoint (14 October): payout and billing domain packages replace the
monoliths; application C901 exceptions are per-function. Shared-reader and
exclusive-cancellation interleavings pass, including different and same trips.
The 37 coverage-policy tests pass without measuring local coverage. The focused
refinement batch passed seven checks, and its remaining exact-millisecond
fixture correction passed separately. Evidence UI: 100/100 tests across the
three touched actions/tracker/queue files. Fresh database upgraded to 0104;
Alembic reports no model differences. Ruff and formatting pass. Final integrated
CI and reviews remain required. The evidence-v1 follow-up removes driver legacy
end/ACK branches and unused trip watermark columns; signed v2 recovery and
encrypted queue ownership protection remain.

# Package 5 audit correction lane

- Base: `a9d0eb3e9e8700892bb64353ef1bd6ff5eca19e3`; branch:
  `feat/pkg-05-audit-corrections`.
- Scope: canonical impression authority, heatmap slice conservation, active-admin
  service enforcement outside assignment ownership, truthful notifications/shell
  metadata, and bounded real-stack E2E diagnosis.
- Constraints: no queue-state edits, no Package 6 files/worktree, no merge,
  and no duplicate audit/review. Correction attempt 2 used the one authorized
  no-history Luna read-only scout solely for E2E launch diagnosis; all
  measurement, migration, and concurrency work remained with the Sol High
  controller.
- External or Package 6-dependent failures remain explicit; no policy or client
  facts are invented.

## Checkpoint evidence

- A — canonical impression authority: focused profile-order and stale-source
  regressions pass (`tests/test_impression_estimates.py`, 4 tests); migration
  backfill/SQLite partial-index and 0047 autogenerate checks pass. Scenario rows
  remain inspectable but are excluded from economic summaries. Heatmap SQL now
  also requires the current active-fraud severity counts before using an
  authoritative estimate.
- B — heatmap slice conservation: focused PostGIS regression passes; allocation
  uses the full scoped trip ping denominator before time/bounds presentation
  filters, then applies privacy floors.
- C — active-admin service enforcement: direct denied/authorized service tests
  pass for payout corrections and campaign review; assignment service remains
  untouched.
- D — frontend truthfulness and mutation feedback: notification retry/error and
  shell-placement tests pass. Product copy now names Cardvert/Terrax and uses
  aggregate-measurement/hourly-earnings language; runtime status is no longer
  asserted as unconditional “Live”.
- E — real-stack diagnosis: Playwright did not reach a test; Next/Turbopack
  aborts because this worktree's `frontend/node_modules` symlink resolves
  outside the filesystem root. The same local constraint blocks `next build`.
  No E2E root-cause code change was made.

## Correction attempt 2 — pinned authority

- Candidate parent: `52ec56857788a4617388d5bcea6538b779ca2fd4`.
- An existing authoritative trip/formula row now pins its exact traffic-density
  profile across default changes and scenario reruns. An omitted-profile
  recomputation refreshes that same row after current analytics and fraud inputs
  are locked and refreshed. A different explicit active profile remains a
  non-economic scenario.
- With no existing authority, only an estimate for the active default profile
  may become authoritative. Scenario-only evidence remains inspectable while
  advertiser reporting, payout, and heatmap consumers publish no result.
- Red/green evidence: five focused runtime/backfill regressions failed on the
  pre-fix behavior and passed after the repair. The full impression estimate
  file plus the SQLite migration regression passed (18 passed, one configured-
  PostgreSQL concurrency test skipped in that SQLite run). Focused report and
  payout seams passed (2 tests); focused PostGIS heatmap seams passed (3 tests).
- Disposable PostgreSQL evidence passed for concurrent pinned-profile
  recomputation/scenario execution (1 test) and for active-default-only
  backfill, zero scenario-only authority, partial-index shape, and unique-index
  enforcement (1 test). Each throwaway database and its isolated container were
  removed after the run.
- Migration integration remains intentionally unresolved: this isolated branch
  still names the authority migration `0048`, while Package 6 currently owns
  `0048_campaign_assignment_offer_lifecycle`,
  `0049_assignment_activity_flags`, and `0050_driver_applications`. Renumber and
  set `down_revision` only when adopting onto Package 6's clean W3-04A head;
  do not merge this migration unchanged.
- Minimal E2E launch: use an isolated Compose project for DB/Redis/API, migrate
  and demo-seed it, then run host Playwright with `API_BASE_URL` pointing to the
  isolated API. Before `npm ci`, remove `frontend/node_modules` only after
  verifying it is the known symlink to the separate main checkout; never delete
  that external target. No E2E suite was run in correction attempt 2.

## Aggregate verification

- Frontend lint, typecheck, and Vitest aggregate: PASS (41 files, 214 tests;
  one pre-existing React Compiler warning). Contract snapshot/type generation:
  PASS (only the authority field changed).
- Backend focused aggregate covering A–D, migrations 0047/0048, OpenAPI, and
  hardening: all behavioral checks passed; the first run exposed the expected
  migration-head assertion, which was updated to 0048 and then passed in its
  targeted rerun. A full 989-node backend run was started once but was
  terminated by the local runner at 65% (SIGTERM); it was not claimed as a
  pass.

## Delivery receipt

- Parent: `a9d0eb3e9e8700892bb64353ef1bd6ff5eca19e3`; implementation tip:
  `c63e38d`.
- Ordered correction commits: `0f915d0`, `69f1402`, `d7a9337`, `5d0c27b`,
  `1caf4a1`, `1d686a0`, `c63e38d`, `d97f3df`.
- The final frontend copy touch `c63e38d` changes the remaining visible
  Vantage monogram to Cardvert's `C`; frontend lint remained green.
- The branch was pushed after the implementation and receipt commits. The
  only remaining dirty path is the preserved untracked Pro artifact under
  `.codex/delivery/cardvert-pkg05/`.

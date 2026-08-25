# Package 5 audit correction lane

- Base: `a9d0eb3e9e8700892bb64353ef1bd6ff5eca19e3`; branch:
  `feat/pkg-05-audit-corrections`.
- Scope: canonical impression authority, heatmap slice conservation, active-admin
  service enforcement outside assignment ownership, truthful notifications/shell
  metadata, and bounded real-stack E2E diagnosis.
- Constraints: no queue-state edits, no Package 6 files/worktree, no merge,
  no subagents or duplicate audit/review.
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

The current worktree has no `TEST_DATABASE_URL`; the newly added PostGIS fraud
staleness regression and the inherited PostGIS seam rerun therefore report
`skipped: PostGIS test database is not configured` locally. The earlier
configured-environment slice evidence remains the B regression basis.

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

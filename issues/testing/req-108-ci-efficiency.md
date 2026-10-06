# REQ-108 CI verification and timing report

6 October 2026 update. Change on `codex/req-108-ci-efficiency`, isolated from
REQ-106's audit work. Initially allocated REQ-107; renumbered to REQ-108 after
the concurrent audit request took REQ-107. Owner authorization verified in the integration chat: once master is green, REQ-108 may rebase and push its branch. No master merge, deployment, account or cleanup authorization is included.
Contract: `issues/planning/req-108-ci-efficiency.md`.

## Real before measurements

Wall time is run `createdAt` to completed `updatedAt`, including queueing.
Runner minutes sum each non-skipped job's `completedAt - startedAt`; these are
elapsed runner minutes, not rounded billing minutes. Matrix jobs count separately.

| Run | Outcome | Wall minutes | Runner minutes | Backend job range |
| --- | --- | ---: | ---: | --- |
| [37433319087](https://github.com/oluwasolaonigbinde/mobility/actions/runs/37433319087), `b77945d7` | Green; comparable pre-change baseline and refreshed timing source | 23.98 | 124.33 | 4.45–23.32 min |
| [36516619520](https://github.com/oluwasolaonigbinde/mobility/actions/runs/36516619520), `83444dc` | Green; original timing source | 20.98 | 100.15 | 5.02–20.23 min |
| [37240242051](https://github.com/oluwasolaonigbinde/mobility/actions/runs/37240242051), `7bee4ae` | Failed; owner's 9–29 min example | 30.37 | 108.03 | 9.12–29.12 min |
| [37271345370](https://github.com/oluwasolaonigbinde/mobility/actions/runs/37271345370), `750edbb` | Failed; only four shard artifacts | 21.92 | 98.62 | 6.43–21.27 min |

The two failed runs skipped E2E, R59 and coverage, so their totals cannot be
compared as full successful-suite costs. The original green source has 3,154 tests in 257 files. Refreshed green master has 3,316 tests in 272 files. The branch consolidates redundant path-filter parameter rows into trigger assertions and adds scheduler checks; report its actual testcase count with the after run.

| Gate/job | Green master 37433319087 elapsed minutes | REQ-108 real after |
| --- | ---: | --- |
| backend static | 1.03 | Pending |
| backend shard 0 | 4.45 | Pending |
| backend shard 1 | 18.32 | Pending |
| backend shard 2 | 17.33 | Pending |
| backend shard 3 | 22.48 | Pending |
| backend shard 4 | 19.37 | Pending |
| backend shard 5 | 23.32 | Pending |
| backend aggregate | 0.25 | Pending |
| quality: lint/types/unit/contract/build/audit | 3.05 | Pending |
| changed-code coverage/D33 | 0.18 | Pending |
| ordinary E2E | 9.58 | Pending |
| R59 journey | 4.97 | Pending |

**Prediction only:** refreshed green master's measured JUnit testcase sums by
old shard are 3.04, 16.74, 15.60, 19.79, 17.79, 21.55 minutes. Replanning those same recorded
files yields 15.75 minutes per shard (rounded). This excludes service setup,
collection and browser provisioning and is not an executed after result.
No after wall time, runner total or D41 acceptance is claimed yet.

## Criterion evidence

1. **Local PASS:** parsed push selection excludes only `dependabot/**`; PR has
   no filters. Neither event has path filters; master cancellation is false.
   Updated authority, progress and coverage-selection contract tests.
2. **Local PASS:** all seven job definitions have explicit 45/30/20/15/10-minute
   bounds; E2E/R59 have no `needs`. Backend aggregate still requires both
   prerequisites and fails closed; coverage still needs backend and quality.
3. **Local PASS:** all seven jobs invoke the workspace-root composite after
   candidate checkout. Executed its actual Bash script in `cardvert-dev:py312`
   against the repository Git tree: correct full SHA exits 0; wrong full SHA
   and malformed SHA exit 1 with explicit error. No expression enters shell
   source through the candidate input.
4. **Local PASS:** imported all six green-source artifacts through unchanged
   `verify`, including full inventory, zero unsuccessful tests, SHA/runtime,
   coverage hashes and execution identity/hash checks. Snapshot stores source
   run/SHA and six report hashes. Tests exercise duration skew, unseen-file
   fallback, zero durations, invalid timing data, class/parameter identities,
   snapshot-backed plan and tampering, plus existing strict verifier failures.
   Rebased Linux CLI collection/assignment covers all 3,291 tests in 272 files
   exactly once with six nonempty assignments (42/47/49/46/45/43 files). Every
   file has refreshed timing history; fallback remains exercised by tests.
5. **Local PASS:** only the two actual `LOCAL_CLAMAV_HOST` consumers select
   ClamAV; startup and bounded readiness use the same planned output. The
   rebased collection assigns both scanner consumers to shard 3. Real-integration
   flags, MinIO provisioning, browser/Caddy selection and zero-skip verification
   remain. CI must still prove real scanner execution after reallocation.
6. **Local PASS:** pip/npm ignore semver-major and group minor/patch; Actions
   grouping and both Docker update entries remain. Digest lists compare exactly
   with branch base: no image change. Original pre-pin Dockerfile history uses
   `python:3.12-slim` and `node:22-alpine`; those tags are restored alongside the
   unchanged digests. Protected frontend audit step compares equal to branch base.
7. **OPEN:** before measurements above are real; after measurements require the
   authorized feature-branch push and completed CI. Predictions are separate.
8. **OPEN:** plan review completed; valid zero-duration/incomplete-source FIX
   findings corrected. Final consolidated review and focused check results are
   recorded below once stable. Green-master rebase and owner feature-push
   authorization are complete. Own full exact-SHA green CI, final review PASS,
   master merge approval and request closure remain gates.

## Repeatable timing refresh

Download `r17-backend-shard-*` from one complete green run to a scratch directory,
then run `python scripts/pytest_shard.py import-timings --candidate-sha <full SHA>
--shard-count 6 --artifacts-dir <directory> --source-run <run URL>
--output scripts/pytest_shard_durations.json`. Review and commit the resulting
snapshot with the change; each CI shard reads that identical committed file.
Import rejects incomplete, mixed-SHA, overlapping or tampered sources.

## Checks and review

- First focused Linux six-file run: 609 passed, one optional PostgreSQL probe
  skipped; 12 release-file failures exposed missing Docker Compose and Windows
  CRLF shell checkout bytes in the temporary runner. That file was rerun
  with the existing Compose-equipped runtime and LF shell files in scratch,
  matching Linux Git checkout; source repository shell files are unchanged.
- Release-file rerun: all 456 passed in 28.24s with Compose and LF scratch
  checkout. Combined distinct focused results: **621 passed, one optional
  PostgreSQL fixture probe skipped locally**. CI's real-integration/zero-skip
  mode remains required and unchanged; local results are not its replacement.
- Duration/planner/verifier file: 39 passed on the final source.
- Ruff on modified Python files: PASS. `git diff --check`: PASS.
- Consolidated reviewer: no actionable source findings; independently verified
  all historical timing totals and all 272 refreshed manifest-mapped snapshot entries.
  Rebased source review has no actionable findings. Full minimal-change PASS
  is withheld pending own green CI and the real after report. No gate is waived.
- No product/API/schema/coverage-baseline or launch-programme change, no specialist
  product-domain review or deployment introduced by this CI scheduling change.

## Rebase checkpoint — 6 October 2026

Rebased onto green `b77945d7be368fbce4d575bcd16bb308b91e1746`. Resolved two documentation conflicts by retaining every master record and adding only REQ-108; its changelog row is now v1.121. The protected frontend audit step and adopted baseline content match that master exactly. Refreshed all 272 file timings from its six artifacts using unchanged authoritative verify. Owner-authorized feature push follows focused rebased checks and reviewer reassessment; merge remains unauthorized.

## Rebased focused checks

The six touched files yielded 605 passes and one optional PostgreSQL probe skip; 16 failures were confined to the temporary Compose runtime lacking the installed coverage package (the repository coverage directory became a namespace import). Reran both affected coverage/sharding files in the existing Python 3.12 runtime with coverage 7.16.0: all 73 passed in 81.17s. Combined distinct rebased result: 621 passed, one optional local probe skip. No source correction was required. Full Linux CLI planning collected 3,291 tests in 272 files, all assigned exactly once. Ruff and whitespace checks pass.

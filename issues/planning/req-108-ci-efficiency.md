# REQ-108 CI efficiency delivery contract

Owner request, 5 October 2026. Review required under verified-feature-delivery.
Branch: `codex/req-108-ci-efficiency`, from current master `750edbb`.

Outcome: reduce duplicate runs and backend imbalance while preserving all CI
authority, exact-source evidence, inventory, coverage and integration gates.

Scope: `.github/workflows/ci.yml`, `.github/dependabot.yml`, one local composite
SHA action, `scripts/pytest_shard.py` and a committed timing snapshot, both
Dockerfiles, affected CI/sharding contract tests, architecture §10.3, requests
and final evidence.
Do not change the Frontend dependency vulnerability audit step owned by REQ-106,
product code, dependencies, image digests, coverage policy or launch programme.

Acceptance and verification:

1. Push selects every branch except `dependabot/**`; PR selects all changes.
   Neither event has path filters. Master never cancels earlier runs. Assert
   parsed triggers and concurrency in the existing workflow contract tests.
2. Every job has a bounded timeout: backend shards 45 minutes, E2E/R59 30,
   quality 20, backend static 15, aggregate and coverage 10. E2E/R59 have no
   quality dependency; backend and coverage prerequisites retain fail-closed
   authority. Verify every job and dependency in contract tests.
3. Every job checks out the candidate and invokes the same local composite SHA
   guard, with explicit workspace directory and input passed via environment.
   Verify mismatch fails, match passes, and all jobs use it after checkout.
4. Plan uses deterministic longest-duration-first whole-file assignment from
   a checked-in snapshot derived from a real run's uploaded execution.xml and
   manifests. This avoids six shards selecting different mutable caches/runs.
   Sum JUnit testcase times (including setup/teardown); map identities through
   manifests, never guess a class path. Unknown files use collected test count
   times the median recorded per-test duration; no history falls back to counts.
   Reject malformed/nonfinite/negative data. Break equal-load ties by assigned
   file count then shard index so all-zero durations cannot create empty shards.
   Add a repeatable snapshot import
   command and source run/SHA/report hashes. Historical timings are scheduling
   hints only. Import complete six-shard sources through existing verify first,
   checking SHA, complete/disjoint inventories, execution identities and hashes.
   Keep existing manifest/finalize/verify strictness unchanged.
   Test skewed timings, missing files, determinism, invalid data and all existing
   missing/overlap/skip/hash/inventory failure paths.
5. Start and wait for ClamAV only for planned files that use the real scanner
   (`test_kyc_local_integration.py`,
   `test_campaign_managed_creatives_local_integration.py`). Preserve MinIO,
   browser and Caddy provisioning and zero-skip integration authority. Test
   conditional startup/readiness and compare the selectors to actual consumers.
6. Pip/npm ignore semver-major and group minor/patch per ecosystem; GitHub
   Actions grouping stays. Docker FROM adds the verified original image tag
   while keeping each digest byte-identical. Verify configuration and pins.
7. Report actual job-duration range, run wall clock (created to final completion)
   and summed active job runner minutes from baseline and branch real runs,
   including skipped/failed gates and suite differences. Predictions are labelled
   separately; no local simulation substitutes for the real after run.
8. Rebase onto the REQ-106 agent's green master, preserve its audit change, then
   obtain this branch's own full green exact-SHA CI before merge (D41).
   Independent plan review and final minimal-change PASS are required. Owner
   approval is required before commit/push/merge; no deployment is included.

Checkpoints: independent plan review; implement approved scope and focused
tests; criterion evidence and consolidated review; owner-authorized commit/push
after green REQ-106 master/rebase; own full CI and measured report; explicit
master merge approval. No new product rule or package status is introduced.

Risks: timings age and cannot split a single slow file; service setup costs are
outside testcase durations; starting E2E on lint failures can increase minutes;
failed historical runs can omit artifacts. Use complete green run 36516619520
initially, then refresh from REQ-106 green master before branch push if available.
Run 37271345370 has only artifacts 0, 2, 3, 5 and cannot be imported. The earlier
37240242051 reproduces the stated 9–29 minute
job spread but cannot provide all JUnit artifacts because failed shards did not
upload them. Neither historical run is D41 acceptance.

Independent plan review returned FIX for zero-duration empty shards and the
incomplete snapshot source assumption. Both findings are accepted above.

# REQ-249–271 delivery acceptance

The implemented build and reviewed coverage receipt are on `master`.
[Full CI 41547600461](https://github.com/oluwasolaonigbinde/mobility/actions/runs/41547600461)
passed all 12 jobs on exact candidate
`1a6d563ff578a4cef23a33b33c13e2757d2c1f92`. This includes six backend shards,
their aggregate, backend static checks, frontend lint/types/unit/contract/build,
desktop/mobile E2E, the real-stack release journey and coverage policy.

This closes implementation and CI acceptance. Payment-provider keys and live
provider evidence, verified production issuer facts, physical-device evidence,
release/pilot and handover obligations remain governed by their existing launch
gates. No deployment or live payment-provider call was performed.

## Contract and verification

The owner authorized bounded repairs and direct `master` pushes until the exact
pushed SHA passed full CI. Preserve product rules, payment/privacy/security
authority, independent monetary expectations, coverage floors and provenance;
create no branch or worktree. Independent plan review passed after strengthening
the historical money oracle and correction-order verification.

| Criterion | Verdict and evidence |
| --- | --- |
| C1: Diagnose failures and make bounded repairs | PASS. First run `41512675786` on `dcd123eb` exposed a missing audit classification, aged campaign fixtures, a retired direct-recompute expectation, stale historical seed expectations, old payment wording and a disabled test logger. Repair commit `70fbb439` preserves the underlying rules. Local focused checks passed 51 cases plus the historical parity test; pinned typecheck reported zero errors. The complete suite subsequently passed. |
| C2: Attribute recovery audits to the correct person | PASS. `payout_recovery_offset` follows its explicit `driver_profile_id` through the existing typed-table pattern. Real database audit tests assert the exact target and actor sets; the existing missing-target parameterization includes this entity type. No actor, disclosure or payment authority changed. Privacy/security specialist review passed. |
| C3: Keep approval and browser assertions meaningful | PASS. Both review journeys use a coherent future campaign window; the resubmission PATCH date changes with it. Existing approval/history/ownership/notification assertions remain. Driver E2E requires the exact amount-first ₦10,000 paid wording. Clean-seed desktop and Pixel-7-emulated CI passed. An older local server with a modified ₦91.08 seed was explicitly not counted as fresh browser success. |
| C4: Verify supported correction execution | PASS. The direct call rejects the changed zero-delta position without new ledger entries. An approved correction order matches projected deltas and the independently calculated final trip amount. Repeating the order preserves its result and ledger-entry IDs; a new projection has zero deltas. Money specialist review passed. |
| C5: Preserve the independent historical amount oracle | PASS. Frozen source `be1fc9de` reproduced the original 300 calculations, 300 ledger rows, both original hashes and ₦497,627.06 total. Approved REQ-251 seed changes remove exactly five duplicate-assignment trips and seven zero-valued ledger rows. Every remaining identity, amount, status and currency is unchanged. The test reconstructs only those explicit historical rows to retain both original hashes, verifies each retained zero calculation, and asserts the adjusted ₦496,142.69 total. Independent source and money-specialist reviews passed. |
| C6: Refresh the receipt without weakening policy | PASS. Complete same-candidate CI artifacts, strict whole-delivery qualification, independent source/report/lineage/inventory review and unchanged-checker receipt admission all passed; details below. No checker, exclusion, numeric floor or instrumentation change accompanied the refresh. |
| C7: Pass full CI on the exact pushed master candidate | PASS. Run `41547600461` is successful on `1a6d563ff578a4cef23a33b33c13e2757d2c1f92`, with all 12 jobs successful. Earlier failed verdicts remain recorded. |

The reserved-row amount and payment-alert context fixes are built in
`dcd123eb`; their API-to-React, real-reservation, authorization and source
evidence is in [the Money receipt](req266-267-money-presentation-2026-11-02.md).
Artwork expiry and type-conformance evidence is in
[the pre-push sweep](prepush-sweep-2026-11-02.md). All are included in the
successful integrated CI candidate. This CI repair changed no API schema, so
no additional API/native contract baseline regeneration was needed.

## Controlled D33 receipt

Run [41542780344](https://github.com/oluwasolaonigbinde/mobility/actions/runs/41542780344)
on `70fbb439cab8bd31d1a571fdc81675ebd0068281` passed every noncoverage job.
Coverage alone failed with the explicit stale inventory/policy receipt guard.
Its complete artifacts produced the reviewed receipt committed in `1a6d563f`.
That commit changes only `coverage/baseline.json`.

- Backend producer: CPython 3.12, coverage.py 7.16.0; all six shards have matching
  assigned/executed counts, totalling 3,611 node IDs.
- Backend LCOV SHA256:
  `de7ba5649515e368e4882ae46330a305cb5c5993560ad2dedca91ddfad76afda`.
- Frontend LCOV SHA256:
  `4e93cb8476169122292a4b1e71b9b8f0c9db1e74e9e53e37cda72b29e92e4501`.
- Receipt origin: `55122b9baea94c915839ef9fbac7dacd66161b83`, covering the whole
  delivery rather than only the final repair commit.
- Eligible-source SHA256:
  `7ba8beeae3d78272f97f92de82bfa1e1886594e51c5da00d72d0ebda798fe261`.
- Measurement-policy SHA256:
  `f4346d9fa3f4116f842cd17d853cd0ad0079121d9ffac691da19a93e8ef5ec33`.
- Eligible inventory is unchanged: no added or removed eligible files. The
  independent reviewer hashed all 702 eligible files directly from Git blobs,
  avoiding Windows working-copy line-ending differences.

| Measured scope | Lines | Branches |
| --- | ---: | ---: |
| Changed code, full delivery | 95.3704% | 89.0909% |
| Global | 92.6979% | 81.5900% |
| Backend | 94.3661% | 83.5718% |
| Frontend | 86.4938% | 80.0483% |
| Money | 93.7705% | 86.0537% |
| Privacy | 93.8350% | 86.4721% |

Strict qualification used the unchanged `scripts/check_changed_coverage.py`
with the explicit full-delivery base, both LCOV files, backend producer
provenance, `--verify-baseline-provenance`, `--sensitive-branches` and a reasoned
`--refresh-baseline`. The 90%/80% changed-code and 85% sensitive-branch floors
remain intact. All global/backend/frontend adopted percentages increase;
the previous-baseline hash matches its originating ancestor exactly.

The unchanged checker also admitted the refreshed receipt against parent
`70fbb439cab8bd31d1a571fdc81675ebd0068281` with the same measured artifacts.
The final full CI then independently passed on the receipt commit itself.
No local full coverage collection or runtime reconciliation was used.

Repeatable local diagnostic artifacts and commands are retained outside Git in
`C:\Users\Dell\.t3\worktrees\mobility\live-e2e-20261026-tools\ci-repair`
(`refresh.sh`, `admission.sh`, complete report/provenance artifacts, strict JSON
results, historical row exports and focused-test logs). This is a tools/artifact
directory, not a registered Git worktree. Source archives used for receipt
qualification were exported with `core.autocrlf=false` to match CI bytes.

## Git and account records

The existing checkout remains on `master`; no replacement branch or worktree was
created. Unrelated changes and unique historical evidence were preserved before
the earlier local cleanup in
`C:\Users\Dell\Documents\Projects\mobility-preserved-20261102-1930`.
Seven additional GitHub branch pointers were removed only after proving every
commit was already reachable from `master`; unmerged history was not rewritten.
The current second-advertiser demo login was recorded in the ignored local
account-access directory, without adding credentials to Git.

# Final in-house D33 coverage receipt

REQ-171–179; coverage-bearing behavior belongs to REQ-171–177. The owner approved
measurement → independently reviewed receipt → full verification → final
consolidated reassessment → non-squash merge. This receipt qualifies measurement;
verification of its own commit and the final reassessment remain merge gates.
No coverage was measured locally. No checker, eligibility, threshold, runtime
policy or workflow change is included.

## Complete source-bound measurement

Candidate: `4f41e8958c1f769fe5aafbc7e1949a0cb5a73183`.
[Measurement run 38566895593](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38566895593)
passed all six backend shards (3,447 tests in 226 files), aggregate verification,
backend static, complete frontend checks/build, R59 and desktop/mobile browser
journeys. Its only failure was the expected policy refusal:
`inventory or policy changed; controlled baseline refresh required`.
The aggregate checks candidate identity, assigned/executed inventories and
coverage artifact hashes. Producer: CPython 3.12.14, coverage.py 7.16.0.

| Artifact | SHA-256 |
| --- | --- |
| `backend.lcov` | `414c3d8557afe854f74f46c6d84fd74dbac50952381799b6eb1e43db2bbafb9e` |
| `backend-provenance.json` | `2cb84ba5c93097c3b77247cb930ab8b408a523044c99c56ef38978f0598ff75d` |
| `backend-shards.json` | `a92c6266c35c27e236529d3d56cb0b9261edaf2f253460478dcc5b26d2632023` |
| Frontend `lcov.info` | `f162c024ca201c4763b92306e398e1d595f96a7b7c8f89ea306def67032674d5` |
| Canonical `coverage/baseline.json` | `f83e0e1d17572fea2a83915fef577837d0abad4416be74ed7c3ad441dcaec0b4` |
| Full-range qualification JSON | `1f24baeb363f95c51005962771c0e86b59991f5e7298a3228a7d3aa026e813c6` |

## Exact adopted floors retained

The previous measurement, [38557836646](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38557836646),
had 31,892/33,914 backend lines. The unchanged checker refused refresh below the
adopted exact 31,688/33,692 ratio. The orchestrator authorized real behavior tests
of this batch's uncovered code, without lowering/rebaselining that figure,
changing the checker or adding unrelated coverage. One test commit, `4f41e895`,
contains those tests and their uncovered-path audit; application code is unchanged.

The new measurement has 31,907/33,914 backend lines (15 more covered lines), ten
above the minimum qualifying 31,897. No old floor was waived or lowered.
The unchanged checker passed full-range qualification from
`966abd3a97873ed741f2cd714e5a8a928c5c2905`, with producer verification, separate
sensitive gates and controlled refresh. Exact prior global/backend/frontend line
and branch ratios passed before the generated receipt adopted these ratios.

| Scope | Lines | Branches |
| --- | --- | --- |
| Full changed range | 436/443 (98.4199%) | 207/232 (89.2241%) |
| Global | 38,668/41,798 (92.5116%) | 13,627/17,064 (79.8582%) |
| Backend | 31,907/33,914 (94.0821%) | 6,666/8,058 (82.7252%) |
| Frontend | 6,761/7,884 (85.7560%) | 6,961/9,006 (77.2929%) |
| Money | 5,550/5,923 (93.7025%) | 1,703/1,982 (85.9233%) |
| Privacy | 2,122/2,284 (92.9072%) | 744/870 (85.5172%) |

Changed code exceeds 90% lines/80% branches; money and privacy independently
exceed their 85% branch floors. The approved tests prove malformed-length cap and
original-byte authentication, failed lock cleanup preserving same-reference
retry, shortened-window and policy-drift refusal, concurrent-source report
refusal/retry, export integrity refusal, retained frozen End evidence, upload
identity/context changes and post-logout refusal. Local checks were 25 focused
backend cases sequentially and all 84 cases in the three touched frontend files;
Ruff, whitespace, frontend ESLint/Prettier and integrated TypeScript passed.
No execution-only tests or unrelated old-code tests were added. The detailed
line/branch inventory and defensive exclusions are in
`issues/testing/final-inhouse-fixes-2026-10-14.md`.

## Reproducible canonical generation

The reports were evaluated against a byte-exact `git -c core.autocrlf=false
archive` export of the measured candidate, with detached Git metadata. The
export matched HEAD before qualification. Windows checkout conversion therefore
did not change source hashes or changed-line selection.

The unchanged `scripts/check_changed_coverage.py` ran with the CI backend LCOV,
backend provenance and frontend LCOV, `--verify-baseline-provenance`,
`--sensitive-branches` and `--refresh-baseline` with the recorded reason. First,
base `966abd3a97873ed741f2cd714e5a8a928c5c2905` qualified the whole batch. Then the
committed old baseline bytes were restored and base equal to the measured
candidate generated the canonical receipt. Canonical refresh and ordinary
verification both passed on the same reports. The generated baseline was copied
byte-for-byte; no receipt values were hand-edited.

- Source parent: `4f41e8958c1f769fe5aafbc7e1949a0cb5a73183`.
- Previous receipt: `4d5a9d8f8ceb86ad931fabcee098677d8778c4ad16cd008ac91ba7d5b468e3ff`.
- Source hash: `ad87ca9fdd6ad817e523e41bdbde165a2b7ba1fde53a00e0fb7744cff71108b9`.
- Unchanged policy hash: `3dc2898f7e7a09232866464ca276146711f5cd72d626e869f1e829ce79c64f95`.
- Eligible inventory: `d8cc9556ea948b76b4b3227223248c969e5dbb0e628031af9010fca244389828`.

Inventory additions are only `app/core/webhook_body.py`,
`app/models/audience_work.py` and `frontend/src/lib/files/use-document-uploads.ts`;
there are no removals. Baseline version 3 and CPython 3.12/coverage 7.16.0 producer
identity remain unchanged. Artifact and qualification copies are retained outside
the repository under `C:/Users/Dell/.codex/final-inhouse-ci/38566895593`.

Independent `final-inhouse-d33-receipt-r1-20261014` returned PASS after
recomputing hashes, exact ratios, full-range metrics and separate sensitive
floors, reviewing the behavior tests and running the read-only ordinary checker.
This receipt commit must receive full green CI and final consolidated/minimal-
change PASS before merge and closure.

# W1B local delivery evidence — 5 October 2026

Branch `w1/budget-hosting`, isolated worktree `mobility-w1b`, base master
`750edbb`. Authority and acceptance criteria: [delivery contract](w1b-budget-hosting-contract-2026-10-05.md).
REQ-037/049/108 remain IN PROGRESS until approved CI and master integration.
No provider API, account, deployment, push or master merge. Account-access and
tmp were not read. Provider documentation was read to substantiate templates.
No payout/dependency/CI/type/coverage baseline edits; no migration or API change.

## Criterion evidence

| Criterion | Verdict | Actual evidence |
| --- | --- | --- |
| A1 — fixed costs count once | PASS | `tests/test_budget_enforcement_w2_01e.py`: independently net1000/gross1075 at VAT7.5%, media400, printing2x100 and installation/permit/design/arbitrary-other100 each. Confirmed funding reaches warning860, urgent1021.25, pause1075; reversal removes funding and retries reuse rows. Three production cases reach all thresholds with gross1075, Lagos-midnight daily attribution, issued credit100+VAT7.50 gives967.50 once, new evaluation/retry convergence, accepted lines/gross unchanged. Existing two-level key example and urgent policy/recipient tests remain. No budget production code changed: the existing allocation/full-obligation computation already includes fixed costs. |
| A2 — provider replacement/inert templates | PASS | Deleted deploy/render/render.yaml and both deploy/aws JSON files. Hetzner README and exact-origin GET/POST CORS replace them. Both examples have blank secret values, blank map URL and budget ratios, publishing/approval off. `test_deploy_templates.py` parses and checks them; residency/retention remain unset. |
| A3 — MapTiler map/CSP | PASS for template scope | Frontend map config test uses the exact MapTiler HTTPS URL form and preserves local schematic when blank: 2 passed. CSP regression permits only api.maptiler.com in connect/img, none in script/style/font/frame, no broad https/wildcard source. No browser/provider rendering claim; existing MapLibre receives the URL unchanged, with no new executable frontend logic. |
| A4 — production scanner/workers/release contract | PASS for template scope | Real Docker Compose config renders staging/production and release profile without starting stacks. 24 template cases cover healthy scanner dependencies, private data+egress networks, signature volume, mem4GiB, unpinned/public/missing/unsafe scanner rejection, exact host/port, WEB_CONCURRENCY2 and override3. Locally inspected official ClamAV1.4 metadata supports clamdcheck.sh and360s warm-up. Existing release-preparation file passes its bundled TLS, key/image/environment and shell/state/recovery contracts. |
| A5 — records/gap dispositions | PASS | Request statuses, client histories, D62/Q32, architecturev1.117 §15.5/25/30/changelog, current deployment notes and historical staging banner updated. No new budget decision because billing behavior is unchanged. Historical Batch F gaps1/2/3/4/6/11/13 fall away; gap5 template/CSP mismatch closes, gap8 AWS-specific issue falls away with Hetzner credential duty retained, gap10 partially addressed;7/9/12 remain. No progress/launch gate changed. |
| A6 — verification/review | PASS | Commands/results below. Plan PASS before implementation; money FIX corrected and reassessed PASS; deployment/security PASS. Consolidated minimal-change review returned PASS on the integrated diff and criterion evidence. |

## Repeatable checks

- `python -m coverage run --source=scripts.release_contract --data-file=coverage/.coverage-w1b-linux -m pytest tests/test_w403a_release_preparation.py tests/test_deploy_templates.py -q --tb=short`: **482 passed**, no skips,76.51s, Linux.
- `TEST_DATABASE_URL=postgresql+asyncpg://mobility:mobility@db:5432/mobility python -m pytest tests/test_budget_enforcement_w2_01e.py -q --tb=short`: **13 passed**, no skips,114.16s. Ordinary cases use the repository SQLite fixture; two PostgreSQL race cases use randomized test schemas on the existing local development server and clean up only those schemas. This is local synthetic evidence, not migration-based release authority.
- Focused production/correction cases: **3 passed**,32.42s, Linux.
- `vitest run src/lib/map/config.test.ts`: **2 passed**,6.10s.
- Ruff check and format checks for the four touched Python files: PASS. `git diff --check`: PASS.
- Coverage JSON from the successful482-case run intersected with Git's final zero-context diff against750edbb: **9/9 changed executable lines (100%)**, **8/8 changed branch arcs (100%)** in scripts/release_contract.py. Raw reports remain ignored under coverage/. No executable budget or frontend lines changed, so no new money/UI coverage claim is made.

The Linux test container reused installed tooling/images; no downloads or
production stacks. Host release checks initially failed because OpenSSL/POSIX
tools/permissions were absent. The first Linux attempt found copied Windows
shell line endings and missing local tools; worktree shell files were
normalized to their existing Git LF content (no source diff), tooling was
copied from existing local Docker resources/images, and the complete touched
release files then passed. One running test container for this lane; other
lanes' containers were untouched. The test warning is the existing Starlette
httpx deprecation; dependency work is outside this lane.

## Independent reviews

- Plan: **PASS**, gpt-6.1-sol, medium reasoning, clean context. Confirmed reuse avoids fixed-cost double counting; required scanner rejection/coverage details incorporated.
- Money: initial **FIX** for missing correction proof; corrected test added, same reviewer reassessed **PASS**, gpt-6.1-sol.
- Deployment: **PASS**, reviewer reports GPT-6-based Codex (exact runtime ID not exposed).
- Security: **PASS**, same bounded specialist reviewer and reported model; separate scoped verdict.
- Consolidated minimal-change review: **PASS**, configured gpt-6.1-sol with medium reasoning and clean context; reviewer reports GPT-6-based Codex (exact runtime ID not exposed). Every criterion A1–A6 passed with no actionable findings.

## Remaining integration and operational gates

Local commit authorized by the executed brief; Claude owner review remains
before merging. Main CI-fix checkout is untouched. Before any request to push,
wait for CI-green master, merge that latest master into this branch, rerun
touched checks and obtain explicit push approval; full branch CI precedes
approved non-squash master integration. No readiness or launch claim.

Hetzner account/private bucket/S3 checksum/versioned behavior/restore, MapTiler
licence/key/actual rendering, public edge/webhooks, ClamAV image/host sizing,
cold initialization/reload/update availability/outage/EICAR, off-host backups,
key custodian and legal residency/retention remain unexercised. Release and
recovery now allow 900 seconds for scanner/application health; an unhealthy
scanner still prevents readiness and public-edge startup.
All external payment/device/pilot gates remain unchanged.

## Claude correction evidence — 5 October 2026

Owner review of `308f04a` identified the 120-second release wait as insufficient
for ClamAV's 360-second start period. A Linux regression reproduced that failure
with a simulated healthy scanner needing 420 seconds (healthy case failed,
unhealthy case stopped as expected). The host Windows attempt could not run
Bash; only the Linux result establishes the reproduction.

Release and recovery now explicitly include ClamAV in a 900-second health wait.
The deployment reviewer identified recovery's matching 120-second defect; its
correction was accepted and the same reviewer reassessed deployment and security
to PASS. The final four-case simulation executes both source startup commands
with healthy cold initialization and persistent unhealthy outcomes; shell syntax
is checked too: **5 passed**, 457 deselected. Readiness is reached only on success.
This is a deterministic command simulation, not a real scanner/provider startup.

The touched release/template files passed **484 tests** before the recovery
parameterization (482 existing cases plus two release simulations). The focused
five-case run then verified the final recovery command and test parameterization.
Frontend map rerun: **2 passed**. Ruff check/format and diff whitespace checks
passed. Regenerated Python coverage against `750edbb` remains **9/9 executable
lines and 8/8 branch arcs**, with no missing changed lines/arcs. Both changed shell
startup commands execute in the healthy and unhealthy simulations; this shell
execution evidence is separate from the Python coverage report.

Budget current rule/history now use plain words and state that fixed costs count
with media at all three levels, this already worked, and accepted prices never
change. Deployment docs and architecture require **at least 8 GB host RAM**
because ClamAV alone is capped at 4 GB. No capacity/provisioning claim is made.

Integration is **NOT COMPLETE**: latest local/remote master `f943daf` has failed
[CI run 37287602662](https://github.com/oluwasolaonigbinde/mobility/actions/runs/37287602662).
No master merge occurred. REQ-108/D62/v1.117 and correction REQ-111–114 remain
provisional: take next-free identifiers and add "renumbered at merge" when
CI-green master can be merged, after W1-P if it lands first. Resolve the shared
release-test conflict and rerun touched tests then. No push or deployment.
Budget rerun with the same synthetic SQLite/PostgreSQL setup: **13 passed**,
no skips, 227.03 seconds. The correction consolidated reviewer returned
**source-review PASS**, with no actionable findings, explicitly retaining the
incomplete integration gate. Configured gpt-6.1-sol, medium reasoning; reported
GPT-6-based Codex, exact runtime model ID not exposed. Deployment and security
correction reviews also PASS and report GPT-6-based Codex, exact ID not exposed.

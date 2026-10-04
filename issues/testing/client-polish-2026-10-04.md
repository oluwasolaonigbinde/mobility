# Client polish and direct document review evidence — 4 October 2026

> Renumbered at merge into `master` (REQ-106): the identifiers below as committed
> in `6eb5ab9` collided with `codex/dev-preview-unlock`. Read REQ-090 as REQ-104,
> REQ-091 as REQ-105, D57 as D58 and architecture v1.114 as v1.115.

Authority: REQ-090 original client polish brief, Claude's conditional PASS and
numbered corrections; REQ-091 / D57 owner decision replacing the staff need
checkbox with direct audited View. Worktree `codex/client-polish`, base `5fdf6ec`.
Pre-commit verification receipt. Owner authorizes the verified local commit; no full CI, merge or deployment claimed.

## Contract verification

| Criterion | Verdict and actual evidence |
|---|---|
| C1 / F1 — report accuracy and units | PASS. `app/services/audience.py:1048` counts distinct trips per mapped cell/time window; 1592–1619 deduplicates cell/window/context identities then sums their counts. The owner-approved label is **107 area visits**; the calculation details explain that a trip contributes in each mapped section/time window and can count more than once. The 20 completed-trip report cohort stays unchanged. Human units, Nigeria dates, zero/missing/suppressed values, ROI gate, matching report/score/zone lineage and detailed downloads retain existing authority. Settled browser captures show Version 1 ready and both CSV/PDF links, without creating an issuance. |
| F2 — each campaign figure once | PASS. Single results panel for estimated exposure, driver cost and activity score. Duplicate headline cards/component/test removed; report ranking no longer repeats the campaign score. Daily charts/table and per-area exposure are distinct breakdowns. Tests cover missing/zero/invalid score and frozen cost/ROI/lineage constraints. |
| C2 — useful authorized map | PASS. Ready, matched authorized zones only; Polygon/MultiPolygon/holes tested. Live no-key map fills/outlines/names Lagos Mainland. A browser hydration mismatch was reproduced by a failing SSR/hydrate test, fixed by making the SVG tooltip one text string, and the entire map file passes 10/10; original geometry is retained during hydration. Existing configured provider branch tested with mocked MapLibre, including attribution and failure/timeout handling; no provider key exists. |
| C3 — overview and account context | PASS. Staff fraud card/column removed from advertiser pages; four useful overview cards and meaningful account context. Overview, shell and report page tests plus browser captures. |
| C4 / F3 / F5 — documents and decisions | PASS deterministic checks and read-only browser layout. Five truthful named rows, direct audited View, separate Show NIN. Missing rows disabled. No need checkbox or automatic read. Each explicit read uses current IDs and the existing purpose/reason payload. Reopening/retrying invokes a fresh read. Hiding clears links/values/errors; 60-second timer restarts per attempt. Manual hide, pagehide, hidden visibility, refreshed records and older reads resolving after newer reads tested. Bank reference password/min16/max512/required/current-version constraints retained. Rejection initially empty; Reject requires a selected reason; Approve/Expire retain existing validation. |
| C5 — next step | PASS. Suspended first, then documents, bank, car, sign-in. Known document blocker survives optional account lookup failure. Hub tests. |
| C6 / F4 — copy and tracker money | PASS. Neutral verified-campaign-driving wording, recent amounts consistently two decimals through existing exact-money formatter. No pay recalculation. Driver/advertiser copy tests and complete outside-repository wording inventory. Method labels remain neutral pending REQ-018 / EXT-REPORT-METHOD. |
| C7 / F6 — verification | PASS. 204/204 tests across 20 touched test files. Final owner wording change: entire insight test file rechecked, 3/3 pass. Final map hydration correction: entire map file rechecked, 10/10 pass, including one new regression; latest typecheck/lint/format pass. Typecheck, scoped ESLint/Prettier pass; final label files additionally formatted/linted successfully. No full suite or test containers. Browser captures all seven states at 1366×695 and 375×695, with no horizontal overflow. |
| C8 / F6 — handover and reviews | Diff includes new files; exact selectors, receipts, wording and desktop/mobile captures are in the local handover folder. Consolidated minimal-change and separately bounded implemented D57 privacy/security reviews PASS from /root/post_review on final source and evidence. Owner approved the integrated commit after the vehicle extension; final extension consolidated minimal-change and implemented privacy/security reviews PASS. |

## Privacy/security assessment receipt

D57 removes only the driver-application staff need checkbox. View is the
acknowledgment for that individual read. The frontend continues using
`person_payee_approval` for NIN/bank and `kyc_review` with
`person_payee_approval:<submission_id>` for document files. These existing fixed
purposes describe driver application review; no unsupported enum is introduced.

Action tests verify the automatic payload on every click, current IDs and fresh
repeat reads. Read-only source inspection confirms `FileDownloadRequest` requires
purpose/reason, without a separate acknowledgment field
(`app/schemas/stored_files.py:100–113`). The unchanged stored-file read service
audits actor, file, purpose and reason (`app/services/stored_files.py:922–936`);
`AuditEvent.created_at` supplies when. Existing NIN/bank reveal actions and audits
remain separate. Backend authorization and access rules are unchanged.

Sensitive evidence stays hidden after at most one minute or when leaving/hiding
the page. Remounting the read state also discards delayed responses and refreshed
record state. The owner subsequently extended D57 to vehicle documents as detailed below; vehicle approval/expiry/rejection decisions remain unchanged. Tests cover
failure/retry, timer restart, old/new response ordering, record changes and bank
decision constraints. Nneka and Abdulrahman's real review layouts were checked.
No protected evidence reads, bank checks, reviews or trip-start forms were
submitted against the read-only review backend. There was no observed backend
refusal and no backend change; live audited-read behavior was established from
existing source and deterministic action tests, not a newly performed live read.

Independent plan review: `/root/followup_plan`, `gpt-6.1-sol`, medium, PASS with a
separately labelled privacy/security plan PASS. The owner approved the concrete
numbered scope and then the final area-visits wording. Final consolidated minimal-change and separately bounded D57 implemented privacy/security reviews PASS from `/root/post_review` on final source and evidence. The earlier pre-correction PASS is historical.

## Repeatable checks and screen selection

From `frontend`, run `node node_modules/vitest/vitest.mjs run <selectors>
--maxWorkers=2 --reporter=json`. Exact 20-file selectors and JSON receipts are at
`C:/Users/Dell/.codex/worktrees/client-polish/final-test-selectors.json`,
`final-focused-tests.json`, and `area-label-tests.json`. Typecheck:
`node node_modules/typescript/bin/tsc --noEmit`. Scoped lint:
`node node_modules/eslint/bin/eslint.js <36 touched TSX files plus actions.test.ts>
--max-warnings=0`. Scoped format uses Prettier on those same files. No manifest,
lockfile, backend, seed, theme, design or native/API baseline changes.

Only frontend `http://127.0.0.1:3345` runs, against the existing backend
`http://127.0.0.1:3336`. Screens: overview; issued Marula Kitchens — Lagos Lunch
Routes report; pending Marula Kitchens — Wuse Lunch Rush report; Lagos coverage
map; Nneka Umeh documents; Abdulrahman Yusuf documents; driver tracker. The
refreshed backend had reports for all completed campaigns; the owner approved
the active pending campaign on 4 October. Seed data was untouched.

Local handover: `C:/Users/Dell/.codex/worktrees/client-polish/handover.md`.
Screenshots and browser observations are in its `evidence` folder, including
an expanded mobile method capture and scrolled mobile tracker action. No
containing-commit SHA is embedded in this receipt.

## Owner-approved vehicle extension (V1–V5)

On 4 October, the owner explicitly extended D57/REQ-091 to car documents on the
same driver page and approved committing the verified integrated change on
codex/client-polish. Earlier person-only scope is superseded.

| Criterion | Actual evidence / verdict |
|---|---|
| V1 — direct vehicle View | PASS deterministic checks. Labelled car registration/insurance/photo rows have View and Purpose: Vehicle review, without need tick or purpose selection. Mount/empty collections do not read. First click reads once; retries/reopening read afresh. Unchanged action sends kyc_review + vehicle_approval:<submission_id> with current file ID, retaining existing individual actor/file/time/reason audit. No new acknowledgment or backend enum. |
| V2 — privacy lifecycle and decisions | PASS. Each row has independent state/timer, with a key containing name/vehicle/submission/file. Manual/60-second/pagehide/hidden-visibility clearing, independently timed rows, errors/retries and old response arriving after new read are tested. Separate file-only, submission-only and vehicle-only refreshes discard prior state. Approval expiry requirement, decision confirmations, Reject/Expire form validation and approved-car branch remain. |
| V3 — shared reuse | PASS. Repo-wide search found only person/payee and vehicle consumers. Obsolete confirmation branch and compact prop removed; both use the same direct lifecycle. Shared lifecycle, person reads, bank constraints and separate Show NIN regression files pass. |
| V4 — current decision records | D57/REQ-091 extended as owner requested; Q13/Q26, admin/privacy current rules/history and architecture/changelog updated. No committed earlier D-row, package queue, API baseline, backend, seed or theme changed. Request remains IN PROGRESS until merge as requests.md requires; local commit is explicitly authorized. |
| V5 — verification/review | Focused six-file run 72/72 passed; final whole vehicle file 15/15 passed after adding independent-timer regression. Typecheck, scoped ESLint, Prettier and diff checks pass. Independent extension plan and privacy/security plan PASS; final integrated extension consolidated minimal-change and separately bounded implemented D57 person+vehicle privacy/security reviews PASS from /root/post_review (gpt-6.1-sol, medium). Final typecheck also passed after the independent-timer test. |

Verification receipts outside repository: vehicle-test-selectors.json,
vehicle-tests.json, vehicle-final-file-tests.json, vehicle-typecheck.txt,
vehicle-lint.txt, vehicle-prettier.txt under
C:/Users/Dell/.codex/worktrees/client-polish. Before implementation,
vehicle-direct-red.json established the failing direct labelled car View case.

Read-only browser inventory currently contains three applications with vehicle
not_submitted and Ayodele Bakare with approved vehicle ABJ-603-MR. It contains
no pending vehicle-document review. Desktop/mobile captures verify that actual
approved-car branch only, not the new pending View flow. Integrated component and
action tests establish the direct View behavior and its privacy lifecycle.
The independent plan reviewer accepted this proportional factual V5 adjustment.
No pending state was fabricated, seed data edited, protected read/decision
submitted or seed session awaited. Vehicle browser observations have no
horizontal overflow or page errors; artifacts vehicle-browser-results.json and
vehicle-documents-section-{1366,375}.png are in the handover evidence folder.

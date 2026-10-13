# Waves/master integration — verification checkpoint

## Current source checkpoint — 13 October 2026

REQ-151–155 remain IN PROGRESS. The real merge is committed locally as
`21239a6d`; the verified expiry and MapTiler corrections are committed and pushed
as Q `7f374c39b2130f354338ad23b939515f54a93d51`. Fresh Q behavior and measurement
pass as detailed below; exact R `3a9f8b64` full branch CI and final integrated
reviews pass. Authorized remote master advancement to R is complete. Its sole
CI failure is the parent-provenance mismatch; the owner-approved REQ-155
metadata correction is generated and verified, with corrected branch/master CI
and request closure pending. The owner asked this chat to take over the stalled worker.
Its original T3 run was interrupted through the supported orchestration RPC
and its queue held before any takeover edit. Existing checkout/branch and all
review, CI, D33 and conditional master-push gates remain binding.

The verified application/test/deployment source set has 1,410 tracked paths:
SHA256 `99ea5bf9313f27cfcd4667f72e1c12806cef75bbcf1be19b362a7d58cace5d6c`
over sorted path-to-Git-blob hashes. The repeatable manifest and named XML/JSON
receipts are outside Git in Windows Temp `mobility-integration-20261012`.
This fingerprint excludes this receipt and tracking documents; it is not a
containing-commit SHA or coverage receipt.

| Criterion | Current verdict and concrete evidence |
| --- | --- |
| I1 | PASS: parsed TOML for `1b951cc9` versus its parent differs only by the approved thread/greenlet concurrency option; its six paths match the reviewed amendment. Floors/checker remain unchanged. |
| I2 | PASS source/graph: `21239a6d` has parents `4e696b9c` and master `b644025d`; all 155 request and 76 decision IDs are unique. The garbled greenlet mapping is corrected to source REQ-137 → REQ-150. Architecture inventory and single-head checks pass in the fresh contract run. Shared migrations/decisions retain the earlier byte-equality evidence. |
| I3 | PASS bounded integration: all 12 protected master controls/projections/history paths compare equal to `b644025d`; 277 current locked-runtime frontend tests in 30 touched/caller files pass. Real current staff hub and expiry flow pass at 1280 and 375 px. Full ordinary browser/build acceptance remains in I9. |
| I4 / F1–F4 | PASS: public applicant red matrix reproduced both same-expired-file bypasses (201 rather than 422), with both undated aggregate-only controls passing. Final complete renewal run: 34 passed, one fixture failure; corrected staff-created clean replacement fixture then passed in isolation. All 35 cases now have passing evidence, including both staff expiry/forged-facts cases and all four public cases. Fresh 14-case affected-review/money batch covers exact reads, historical retry, eligibility/expiry, terminal-application locking, payout cursor/dispute races and the shared trip golden vector. Privacy/security source and corrected-fixture reassessment PASS. |
| I5 | PASS source/bounded UI: integrated money specialist PASS; 277 frontend tests include current notification/preview/report/grouped-money callers. Frozen amounts, VAT helper reuse, historical report paths and master daily-payment projections are preserved. Exact full browser/report CI remains pending under I9. |
| I6 | PASS bounded runtime: 17 seed/API/architecture/document-outcome checks pass. The primary driver starts/ends via production API authority; seed rerun preserves exact scanned file/review/document facts and returns to idle. Damilola renewal seed is scanned, fictional and idempotent. Master reconciled history/source remains equal. |
| I7 | PASS: runtime OpenAPI snapshot check and all OpenAPI/architecture tests pass; both JSONs match and generated TypeScript is LF-normalized byte-equal (`ab7062e910cfd85d3620ce538d52ab0793ed722b1ba7beb7cc43fa8f8415736b`). Current locked-runtime TypeScript check, 132 preserved PWA/queue/tracker/capability fixtures and shared Python golden vector pass. No baseline/API redesign or physical-device claim. |
| I8 | PASS bounded pre-push source checkpoint: Ruff all 121 touched Python paths and scoped changed-file formatting pass; basedpyright three corrected services returns zero errors/warnings. Scoped frontend ESLint/Prettier pass. Plan reviews, privacy/security, hosting reassessment and money source reviews PASS. Consolidated independent minimal-change reassessment PASS for I1–I8/F1–F4; final CI/provenance reassessment remains pending. Hosting positive red reproduction is retained; release-environment subset 122 passes. Broader Linux runtime rerun has 531 passes, three explicit environment failures and one excluded live-Caddy case, as detailed below. Deterministic/live API and current browser simulation evidence is proportional to the corrections; full Linux/build/E2E acceptance remains in I9. |
| I9 / A3–A6 | PASS at R: full exact branch CI 38334710143, complete six-shard/runtime/raw/export evidence, both whole-change 90/80 comparisons, original trusted floors, normal Q→R provenance and final specialist/consolidated A6 PASS. First-master R repeats passing behavior/measurement but fails parent provenance as documented below. REQ-155 canonical preview/generation/normal verification PASS, preserving every adopted value; corrected candidate's full branch CI and final reassessment remain pending. |
| I10 | PARTIAL: fresh ancestor recheck confirmed `b644025d` remained an ancestor of R; authorized non-force push advanced remote master to R. Master run 38338124582 has all 11 application/static/build/browser/shard/aggregate jobs green and only parent-provenance policy failure. REQ-155 correction, green corrected master CI and the one closure-docs commit/CI remain required. Main checkout is untouched; no requests are closed yet. |

### Final R and one-time parent-provenance correction — 13 October 2026

Exact R `3a9f8b64cb6d78c371ecb147955123a4c8a80d11`
[branch CI 38334710143](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38334710143)
passes all 12 jobs. Independent measurement/provenance supplement and final
consolidated A6/minimal-change review PASS before the authorized master push.
Fresh fetch confirmed master `b644025d` remained an ancestor; non-force push
advanced origin/master to R without changing the main checkout.
[First-master CI 38338124582](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38338124582)
passes its other 11 jobs but fails `baseline refresh receipt differs from
trusted/current evidence`: actual push base is `b644025d`, while the branch
receipt points to Q. This failed pipeline is not a green-master claim.

Fresh R branch and master reports independently verify eight archive digests,
all extracted bytes, six complete disjoint shards, 3,490 successful tests / 278
files, CPython 3.12.14 / coverage 7.16.0, mandatory normalized raw/export
statements and 17 arcs, and no corruption across 39 changed backend files.
Both whole-change gates remain exactly 954/987 lines and 529/610 branches
versus integration master, and 1,568/1,663 and 1,171/1,395 versus fixed M.
Original exact trusted floors pass; normal Q→R verification passes.

The sole Q-to-R hit variation is `app/services/disbursements.py:557`, the
`PAYOUT_BATCH_NOT_RESERVED` refusal in `submit_payout_batch`, and arc
`556→557`: Q has one hit; branch-R and master-R have zero. This unchanged
line is outside changed hunks. Global measured counts are 38,652/42,051 lines
and 13,707/17,438 branches; backend 32,033/34,247 and 6,786/8,374; frontend
6,619/7,804 and 6,921/9,064. Exact adopted-Q refresh floors therefore fail,
while ordinary D41 run tolerance passes. Empty contexts establish no per-test
attribution or causal explanation. Wave 3 should make coverage of this refusal
deterministic; no application/test change or coverage resampling is made here.

The owner explicitly approved REQ-155: normal tolerance for this metadata-only
refresh ONLY, keeping 90/80 and every adopted floor unchanged, recording the
exact variation, and finishing master CI/closure. Independent plan/procedure
and preview review PASS. The unchanged checker generates the R-anchored receipt
from accepted fresh master-R reports; normal verification against R passes.
Every adopted global/critical count, ratio and path list, and source/policy/
inventory/runtime identity, equals R exactly. Only natural parent provenance
changes: `source_parent_sha`, previous-receipt hash, inventory delta relative to
R (empty, with actual inventory unchanged), and the REQ-155 reason. No standing
exception, lowered floor or checker/workflow change. The external
`S-canonical-preview` and `S-canonical-generation` journals in the named Temp
directory record complete original-source restoration without conflicts and
preserve the first-edited request registration. Corrected branch/master CI,
final reassessment and closure remain pending. CI repair rounds: 2 of 3;
behavioral repair rounds after corrected attribution: 0 of 2.

### Fresh Q measurement and canonical receipt — 13 October 2026

[Run 38331361701](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38331361701)
is exactly Q. All six backend groups, backend static/aggregate, frontend,
ordinary real-stack E2E and R59 release jobs succeed. Frontend CI uses Node
26.3.0 and Next.js 16.4.0: 221 files / 1,554 tests pass, contract drift and
production build pass. The full backend inventory is 3,490 passing tests in
278 files; the unchanged shard verifier proves complete disjoint assignments,
successful exact JUnit identities and manifest/raw/JUnit hashes. All producers
use CPython 3.12.14 and coverage 7.16.0. Eight GitHub archive digests and every
extracted member were independently verified against the immutable downloads.

The sole failed job is the unchanged coverage-policy check against push base
`b0da8ae3`: `invalid adopted coverage metrics: global.line` from the inherited
old receipt. This is a failed Q pipeline, with passing fresh behavioral and
measurement evidence; final R must make every job green.

| Fresh report scope | Covered / total lines | Covered / total branches |
| --- | --- | --- |
| Whole Q versus current master `b644025d1f964f5efff7733106b4af4c4a56b968` | 954 / 987 (96.6565%) | 529 / 610 (86.7213%) |
| Whole Q versus fixed M `e6adcc4639f1fba345a3bb44059beb45ad76ea59` | 1,568 / 1,663 (94.2874%) | 1,171 / 1,395 (83.9427%) |
| Global current inventory | 38,653 / 42,051 (91.9193%) | 13,708 / 17,438 (78.6099%) |
| Current backend group | 32,034 / 34,247 (93.5381%) | 6,787 / 8,374 (81.0485%) |
| Current frontend group | 6,619 / 7,804 (84.8155%) | 6,921 / 9,064 (76.3570%) |

Both whole-change comparisons meet 90/80 without tolerance. The current
groups and each base's exact trusted named-path groups meet their existing
global/backend/frontend floors without tolerance or floor reduction. The
expanded fixed-M comparison includes later master portal/read/earnings/seed/
billing changes: 140 changed source files versus 63 against current master;
77 master-only source files contribute 569 statement lines and 639 branches,
with additional differences in shared-file hunks. Old 981/608 denominators
belong to the earlier source candidate; the unchanged checker selects the
complete current diff. No latest-increment substitution or denominator trimming.

Read-only immutable SQLite inspection finds no foreign SQLAlchemy sequences
or out-of-file events across all 39 changed backend sources. All required
normalized statements and 17 reachable arcs in driver_documents/notifications
are present in raw unions and their exact coverage-7.16 LCOV export records.
Driver statement 83 correctly normalizes raw 84–86. Raw contexts are empty;
this evidence makes no per-test arc claim. Measurement/provenance specialist
independently recomputed the complete report and returned PASS at Q.

The unchanged checker evaluated both whole-change bases and Q inside the
reviewed exclusive LF byte window. The Q preview was independently approved;
the generation window reproduced it exactly, generated coverage/baseline.json
through the unchanged CLI, and passed normal provenance verification against Q.
Every source/policy original byte was restored with no conflicts. The receipt
adds 13 eligible paths, removes none, and adopts the verified measured ratios.
Baseline source parent is Q; hashes arise naturally from Git LF source bytes:
source `d508ce634222089f4e8e2ed872fd9bdb6442cac47e6fe1c06ce701d52b6deb22`,
policy `3e71886a0b80c9919cdfac82314c6e35214f607732f7a72247c90e676d64e8e7`,
inventory `873f54e77427dc52bb2cd773ff983def3bac44159aa7e9010cef04a3952b9e1b`.
Backend LCOV SHA256 is
`000f72420a9df9fa5f36170c4ddc79ced3d361abf45c55e2c239c8f6cf4289cc`;
frontend LCOV is
`4ece2b4c3f9434e2958c60a2f652cca791c9ae66e657fe5bc372ba4610fa82b4`.
Immutable archives, Q-run/policy logs, Q-shards-verified.json, Q-measurement.json,
and both canonical-window journals/restore receipts remain in the named
external Temp directory. The prior provisional proposal remains untouched.

Read-only plan reassessment confirmed the first master push uses a different
explicit parent than branch R. If actual master CI confirms that receipt
mismatch after fully green/reviewed R, one bounded CI repair may rebind from
accepted fresh R evidence through the unchanged checker, with independent
receipt review, full branch CI/final review, then full master CI. This consumes
one of the three authorized small CI-repair rounds. Adopted floors, sources,
policy, runtime and original Q→R evidence must be preserved; closure still
waits for green master CI. No such repair or master action has occurred yet.

### Browser and runtime boundaries

The real current Next.js 16.4.0 login/BFF/staff Mark expired action was exercised
against real FastAPI services and isolated PostgreSQL, using synthetic test
storage adapters and no provider calls. Before/after DB observations prove the
original approval is unchanged and the appended expiry retains its document
outcomes, insurance date and validity. Reload no longer labels the car currently
approved. Screenshots and `takeover-browser-evidence.json` retain desktop/mobile
evidence. The initial reload assertion incorrectly assumed expired forms have
no Mark expired button; it was corrected to the actual current-approval label,
without weakening DB/history assertions. Cold local dev attempts encountered
Turbopack root and a Webpack startup syntax error; the completed browser flow
uses supported Webpack dev mode after compilation. This is functional simulation
evidence, not proof of cold-start reliability or a production build.

The existing frontend dependency junction used the main checkout's Next 16.3.6.
It and its old cache were preserved outside the frontend tree in the named Temp
directory. A separate exact-lock installation now uses Next 16.4.0; no manifest,
lock or main-checkout dependency change. Frontend checks were rerun on that
installation: 277 touched/caller cases, 132 preserved fixtures and typecheck pass.
Host Node is 24.19.0; Q's exact CI Node 26.3.0 and production build now pass.
The one heading change in frontend/AGENTS.md is generated by the locked Next
runtime; the instruction text and repository policy are unchanged.

Linux test copies initially retained Windows CRLF/non-executable shell modes.
Only `/integration-source/scripts/*.sh` copies were normalized to LF/executable,
not repository files. The resulting hosting receipt records 531 passes and
three failures caused by missing Docker socket or jq. Live Caddy/CSP tests
require additional containers outside the owner’s two-test-container cap;
they remain unverified locally. Q's complete Linux backend, build and browser
jobs now pass their unchanged gates; exact final R repeats them.
Do not describe the entire hosting suite as locally passing.

All heavy checks ran sequentially; existing cv-w2c-db/cv-w2c-tests each retain
their one-CPU cap. Temporary loopback browser servers are stopped. No local
coverage/full backend suite, shared-service restart, provider/account change,
preview rehost, deployment, cleanup of unrelated files or package-queue change.

## Historical stop checkpoint — 12 October, before corrective continuation

REQ-151 remains IN PROGRESS. The resolved real merge is retained in
`mobility-w2c` / `w2/renewals-phone`; no merge commit, push, master advancement
or request closure occurred. Owner's stop rule applies to the confirmed
review/eligibility defect below. This receipt makes no delivery PASS claim.

## Concrete blocker

Privacy/security specialist review returned FIX. Staff Mark expired on an
approved car has no document fields, but its action submits all outcomes as
`on_file` with null dates. The service saves those fabricated facts as the
latest decision, and renewal derives replacements from it: a known insurance
expiry disappears. The same source is present in wave `4e696b9c`; the merge
did not introduce it. The expiry worker already preserves previous facts.

Relevant locations: frontend driver-applications/vehicle-decision-actions.tsx
line70; actions.ts lines359/375; app/services/vehicle_onboarding.py
lines809/856 and worker983-985; app/services/kyc.py lines577-581.
Forwarding previous accepted facts alone is insufficient: document_reviews.py
lines93-111 requires reads by the current staff actor for new acceptance.
A reliable fix must distinguish preservation from a new review, under the
locked approved-to-expired transition, and preserve actor/audit/retry authority.
This changes review/eligibility semantics beyond a test or fixture correction.

Missing regressions: approved-to-expired staff action retains a recorded
insurance date; later expiry requires replacement; genuinely undated documents
retain the legitimate zero-upload renewal. Existing tests bypass that path or
exercise natural expiry with no document dates. No correction was made.

## Criterion evidence

| Criterion | Verdict at stop | Actual evidence / remaining work |
| --- | --- | --- |
| I1 | PASS source/commit | Separate six-path greenlet commit `1b951cc9`; parsed TOML equality after removing exactly thread/greenlet concurrency. Configured Git identity; no hook bypass. Fresh attribution still belongs to I9. |
| I2 | PASS resolution source; merge commit pending | Real merge of `b644025d` underway; request registration `4e696b9c`. Unique sorted151 requests, unique75 D rows, unique architecture versions. Master119-133 rows retain identifiers/content except authorized125 detail fold. Shared D60-63 and migrations95-98 byte-identical. Single head0101 verified by Alembic. Moved rows have source notes. |
| I3 | PASS source; live flow pending | Protected master UI tabs/field/page-header, globals, driver status, advertiser billing/planning, admin trip/fraud and driver money projection compare equal to master. Master driver surfaces retained; focused UI tests exercised them. |
| I4 | FIX | Privacy/security review found the documented staff-expiry preservation defect. Other reviewed secret/isolation/consent/current-file/revision/offline/account gates are sound in source; fresh PostgreSQL/race/live evidence not run. |
| I5 | PARTIAL | Notification Open/current-access, preview invalidation/races, terminal quote gating and money/report behavior retained. Money-source review PASS after replacing raw VAT multiplication with existing formatVatRate; independent Node reproduction showed the binary tail. New exact quotation VAT assertion is added but not yet executed. Historical report and live-flow integrated verification remains pending. |
| I6 | PASS source; runtime pending | Master demo/rich/history/driver_story geography and daily reconciliation preserved; demo/rich differ only for synthetic phone assignments and Damilola orchestration. Primary current-document wave authority retained. Nigerian phones and names documented, including existing Wuse driver. Fresh seed/rerun/Start-End not executed. |
| I7 | PARTIAL | All three artifacts regenerated from merged app using Python3.12.14/Pydantic2.13.4;282 paths/315 operations. JSON parity, architecture inventory and single migration head pass. Generated-schema typecheck and R14-B fixtures pending. |
| I8 | PARTIAL | Independent revised plan PASS; money-source PASS; privacy/security FIX.65 frontend files/523 cases had520 passes and3 failures; focused8-file58-pass recheck cleared those failures without increased timeouts/retries. Initial tsc and scoped ESLint184 changed source/test files plus final8 corrected files passed. Eight host backend files completed68 passed/17 existing service-gated skips,0 failed: not acceptance evidence.121 changed Python files compile; whitespace checks pass. PostgreSQL/native/build/E2E/template supplement and consolidated minimal-change review not completed. |
| I9 | NOT RUN | No new push/CI, attribution evidence or D33 refresh. Baseline/checker/floors unchanged. CI repair rounds0. Whole integration vs current master, historical fixed-M and Q-to-R provenance remain separate required gates. |
| I10 | NOT RUN | Master not advanced; no requests closed. WhatsApp successor REQ-143 remains NEEDS ANSWER. |

## Maps and conflict decisions

Wave REQ119-124 ->137-142;126-132 ->143-149; greenlet137 ->150;
integration151. Seed125 is master's row with wave detail.116/117/134-136 stay.
Wave D64-72 ->67-75; shared60-63 stay. Wave versions122-127 ->125-130;
master120-124 stay. Migrations95-98 identical;99->100->101 follows98 unchanged.

Master governs Home/Jobs/Track/Earnings/Help/Profile/bell, all named shared
controls/status/billing/planning/trip/fraud screens and canonical Abuja seed.
Profile receives wave renewal/phone inside FreshDriverAuthority. Notifications
retain authorized named Open links. Selected Job lookup and unset-rate sentinel
remain. Master seed replaces the unused wave geography utility. E2E fixtures
retain master's names/geometry and real-stack assertions. No tests weakened,
baseline entries/waivers/retries added, or money authority changed.

## Runtime and retained work

Only cv-w2c-db and cv-w2c-tests were restarted, capped at1 CPU each. Runner
dependencies aligned to Python3.12.14/Pydantic2.13.4/FastAPI0.143.0/Starlette1.7.0.
No database rehearsal, API server or browser suite started. Both containers are
stopped again with their data/volume preserved; no shared service was stopped.
The host backend check completed before the stop command; no benchmark ran.
Docker recovered centrally with4 VM CPUs; owner SOCA DB cap2 is not used by
this task. No performance comparison or claim is made. Heavy tests were
sequential, one worker; no local coverage or full backend suite ran.

Repeatable detailed evidence is outside the repo in the owner's Windows Temp
directory `mobility-integration-20261012`: frontend-integration-evidence.json,
source-verification.json and backend-focused.xml. The isolated venv is there.
Owner .w2c/ and root node_modules/ remain untracked and untouched. No reads of
docs/account-access.md or repository tmp/ occurred. No deployment, provider
call, force push or preview rehost occurred. Final acceptance is unresolved.

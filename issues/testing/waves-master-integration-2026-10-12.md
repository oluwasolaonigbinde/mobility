# Waves/master integration - stopped checkpoint, 12 October 2026

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

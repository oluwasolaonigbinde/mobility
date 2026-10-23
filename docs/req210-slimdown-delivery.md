# REQ-210 Lane A delivery contract — 20 October 2026

Approved scope: owner/orchestrator handoff, inventory at base `1a7b5757`, with
explicit overrides in D108–D119. Implement on current `slim/req210-slimdown`.
No real data/users; remove obsolete development code and update all callers.
One contract, one independent plan review and one consolidated final review.
All reviewers gpt-6.1-sol/high as explicitly requested, overriding skill medium.
Owner already approved concrete behavior and commits. No additional permission
step for this scope. No push/deploy/provider calls or account-access/tmp reads.

## Checkpoints and entry points

| Order | Scope | Entry points / files to verify before editing |
| --- | --- | --- |
| B1a (early S1 commit) | Daily display-proof removal plus coupled S5 automatic challenges | installation_evidence service/model/API/schema, trips service/model/API/schema, assignment eligibility, driver Jobs controls/API routes, files, evidence challenge dependency, fraud flag, seeds/fixtures, config/templates and migration guards |
| B1b | S5/S32/S15/S33/S31/S8/S29/S30/S38 and S57 | evidence_verification, assignment_activity, complaints, privacy_dsr/data_subject services/models, disclosure_retention, worker, file_lifecycle; their admin controls, notifications, seeds/tests and docs |
| B6 | S2/S13/S7/S11 money/S22 subsidy | payouts/rules, payout eligibility/automatic payouts, funding, config/templates, pay terms form, schemas/DB constraints/fixtures |
| B7 | S4/S19/S18/S20/S14/S16/S17 | disbursements, payout corrections/debt/recovery, billing receipts/budget adapter, trips/evidence ingest, fraud, admin payout/trip-check/billing controls, ledger guards |
| B2 | S3/S28 | audience/audience_delivery/exposure_segments, retargeting routes/models/ad adapter/privacy cells, report recommendation and ROI consumers, nav/screens, worker/seeds |
| B4 | S12/S21/S22 non-money/S24/S6 | zones, campaign/artwork/vehicle/assignment enums (artwork image/pdf only; PNG/JPEG/WebP/application/pdf), organization authorization, installation approval and locked activation, admin activation/checklist/work queue |
| B5 | S35/S27/S34/S36 | core config, each numeric-setting consumer, email queue/receipt lifecycle, contacts, settings pages/templates, review SLA |
| B3 | S9/S10/S11 non-money/S23 plus new reports | measurement/report issuance/scheduling/rendering, impressions profiles, campaign/assignment status, advertiser report pages/new reports/nav, admin measurement forms, stored artifact authorization |

Batch boundaries are internal checkpoints, not independent contracts. S1 gets an
early commit for Lane B. That independently bootable/migratable commit also removes
S5 automatic challenge machinery, worker registration, FK and check dependencies;
retain inspector spot checks for B1b simplification. Each batch stages explicit paths, runs hooks, commits
as configured identity and appends `<batch> <SHA> <summary>` plus API changes to
external `lane-contracts/laneA.md`. Final line FINAL only after all reviews PASS.
No parallel writers; read-only specialist review may overlap final local checks.
Keep at most two active Lane A workers unless a disjoint review justification
is recorded. Lane B owns all other visuals; do not restyle.

## Acceptance and evidence plan

| ID | Acceptance | Required independent evidence |
| --- | --- | --- |
| A1 | No daily proof code/surfaces/settings/fields/tables/flag; weekly photos gate trips | Removed-token/caller audit excluding historical migrations/receipts; fresh migration schema/model parity; trip begins after approved current five views with default configuration; expired/rejected/missing photos still deny |
| A2 | Driver side simpler, inspector failures still hold, inactivity still seven days | Spot passed/failed note tests including authorization and hold; inactivity close/dedup tests; old challenge/floor/assignee/DSR routes absent; worker boot and kept notices; deletion-safety regressions |
| A3 | KYC purge runs after six months safely | Boundary tests for chosen calendar six-month semantics, current references and deletion audit; no legal/provider approval claim |
| A4 | Pay formula and seed/test amounts identical; terms publish without switch | Before/after golden exact-decimal trip amounts and ledger sums; proportional/zero/outside/over-target fixtures; immutable acceptance and five-minute stop tests; day/date/reason/rate/miles validation |
| A5 | Automatic pay daily/no run cap under Pause | Clean-only/new-bank-version/manual/hold/pause/provider-unconfigured regression; daily dedup and one-day cap |
| A6 | One-admin manual payout/corrections safe | Same-actor preparation/approval/reconciliation and correction tests; required reasons/audit; stale/race/retry/add-only tests; per-line confirmed provider cash; ledger totals equal except explicit adjustments |
| A7 | Manual negative adjustments replace debt | Reason/audit/authorization/currency/idempotency ledger tests; no carried-forward recovery/incident paths; paid history immutable; adjustment cannot silently trigger cash or bypass holds |
| A8 | Receipt/budget/late-data/flags simpler, financial authority intact | Confirmed-only funding; D104 accepted-price/no-shrink/80/95/>100/resume dedup tests; late admission checks every affected Africa/Lagos day against existing calculation authority using the same driver/campaign/day lock ordering, including another calculated trip on that day, cross-midnight uploads and concurrent upload/calculation; preserve signed batches, stable retry IDs and payload conflicts, and deduplicate repeated audited dropped delivery; no silent repricing; retained flags hold until explicit dismissal/decision |
| A9 | No audience/ROI pilot feature; reports survive removal | Routes/nav/jobs/services/schema references removed; worker starts; existing campaign summaries/CSV/PDF function without recommendations; tenant and three-car regressions |
| A10 | Automatic activation keeps every existing prerequisite | Approve photos activates eligible job/campaign; individual missing funding/window/waiver/artwork/frozen terms/person/car/exclusivity checks block activation and expose missing reason; concurrent/repeated approval safe |
| A11 | Enum/role simplification end to end | Fresh schema, seeds and validation reject removed values; callers updated; advertiser cross-company denials/one-login ownership retained; current campaign cancellation/funding/trip rules pass. Client 20 Oct B4 addition D116/REQ-215: shared creative create/update guard under production-authority lock rejects when the existing ProductionStart record exists or status is running/paused-after-production/later. Keep the existing commercial.production_start.started_at API shape; no new projection. Direct API create/update denial, pre-production unchanged and both production-start race orders tested; replacements via Terrax. Money/security review and Lane B code/message/SHA handoff required |
| A12 | Fixed settings preserve exact defaults/security | Before/after value inventory; relevant rate/expiry/attempt/scanner/trip limit tests; removed env keys ignored/absent; true site secrets/URLs/proxy values remain configurable; phone support-only flow expiry/attempt/audit |
| A13 | Queued email retries and opt-out work, no signed receipt dependency | Queue send/success/failure/retry/concurrency and opt-out tests, worker boot; no signing secret prerequisite |
| A14 | Weekly/final report and Re-run, issued bytes immutable | Scheduler weekly/final dedup/retry/time boundaries; one staff action; rerun creates new artifact identity, old CSV/PDF hashes/download bytes unchanged; storage failure never exposes partial report |
| A15 | Advertiser chosen-period one/all own campaigns CSV/PDF with charts | Authorized Nigeria calendar-date filtering maps start through day-after-end to half-open [00:00 Africa/Lagos start, 00:00 Africa/Lagos end+1). Reuse terminal-trip end-time cohort semantics consistently for totals, chart bins and CSV/PDF, clip campaign overlap for metadata, and test midnight/cross-period trips and differing campaign dates. Reuse daily metrics grouped by Nigeria calendar day for reports and an advertiser-owned campaign last-seven-days distance/car read: exactly seven entries including partial today and zero empty days. Keep three-car checks for each disclosed campaign/area/day slice; pooling all campaigns never unlocks an under-floor slice. Test pooled totals versus suppressed slices and invalid/empty/no-data/mixed campaign cases; unauthorized IDs deny without leaking; files contain dates/three-car areas/cars/distance/days/trips/time/estimated views/creative/status; measured vs estimate separation; no money/budget/CTR/ROI |
| A16 | Fixed estimates and derived Finished | Known-input formula parity; no editable profiles/settings; end-date boundary in UI/API/exports/seeds, no stored completed values; trip end-date gate retained |
| A17 | Integrated contract/docs/verification | Every changed API updates openapi.json, docs/api/openapi.snapshot.json and generated TS schema, then R14-B. Focused touched backend/frontend tests, lint/typecheck/build, schema migration/seed/empty-db API simulation. Final receipt lists each criterion verdict/evidence, reviewer verdicts/model and all gaps |
| A18 | Core platform kept (owner, 23 Oct) | Final receipt and consolidated review explicitly evidence sign-in/session/origin/rate/lockout security; advertiser company isolation; scan-before-open; decimal money/ledger/invoices/receipts/refunds/Paystack verification; human first-bank payout and never auto-paying held pay; staff money/privacy audit; weekly installation gate; spot checks; seven-day inactivity; pay-changing trip checks; D104 alerts; offer/vehicle expiry; location/KYC retention; three-car areas; staff phone tasks; Ask Terrax to cancel; single staff work queue. Restore the short interim D110 manual runbook, with safe existing export paths and an explicit gap where no safe erasure tool exists. No unapproved feature removals. |

Reports must not expose routes/driver identities or cross-company data. Keep
three-car boundaries on area/daily outputs and existing legal/method controls
unless explicitly superseded. Preserve issued legacy files, not old development
interfaces. PDF charts/previews need visual inspection, CSV needs content checks.
No new dependency unless existing rendering capabilities cannot meet the request.
UI actions retain loading/empty/error/retry and accessible labels; uncertain
outcomes are inspected rather than automatically repeated.

## Runtime and review gates

Use only `cv-req210a` (3 GB) and database `cardvert_req210a` in existing
`cv-req139-db`. Atomically create the shared docker lock only when absent; stop
the container/release the lock within about 45 minutes. If busy, code first.
No other DB/container/port 3100/main checkout/branch/worktree changes. Remove
own container/database at finish. Host lacks Python/Node; Docker supplies them.
Run touched test files only, no full suite. Full CI/merge remains controller work.

Plan reviewer challenges completeness, overreach and weak verification before
implementation. Final money review covers B6/B7/S6; privacy B1/B2/B3/S57;
security B5/S24/S34. Consolidated minimal-change review follows final integrated
diff and criterion receipt; valid FIX findings corrected and reassessed until
PASS. Final source changes reverify affected criteria and reviewers.

Do not mark requests DONE until master merge. No progress edit. Record controller
launch-wording changes separately. No evidence-only commits: final receipt joins
the final substantive batch after verification stabilizes. No self-referential SHA.

## Independent plan review disposition

2026-10-20 gpt-6.1-sol/high: FIX, three valid findings accepted and incorporated
above (B1a dependency cut, A8 pay-day locks/evidence, A15 Nigeria period/cohorts/
per-slice floor). No finding rejected. Creative production guard accepted; both
race orders required. Preserve CSV escaping/input bounds and fixed estimate defaults.
Revised contract presented in chat; proceed under the existing explicit owner approval.

Reassessment: independent plan reviewer gpt-6.1-sol/high returned PASS on the revised
contract, with no further necessary corrections. Implementation/review gates remain open.

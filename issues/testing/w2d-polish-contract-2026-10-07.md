# W2-D polish delivery contract

Owner authority: `Cardvert_W2D_Polish_Brief_2026-10-07.md`, REQ-121–124.
Worktree: `mobility-w2d`, branch `w2/polish`, base `ec267529`.
The brief approves this concrete scope, local verification and a local commit.
No push, merge, GitHub CI, external accounts/providers, migration or deployment.
One reviewer at a time, read-only ownership; only the implementing agent writes.

## Existing work

Unread filtering/read-all, panel close/focus and company email-preference copy
already exist (REQ-073–076). Shared campaign-change waiting labels are done
(REQ-113). Report screens already say Not enough data (REQ-104). Wave 1 payout
semantics and full driver earnings amounts remain unchanged. Do not rebuild these.

## Outcome and scope

1. Notification API projects current authorized campaign context, with a nullable
   `campaign_name` and nullable internal `action_url`. Resolve typed campaign,
   assignment, trip and activity references from stored business rows, never
   trust payload display strings or URLs. Advertisers use their current active
   membership/organization and campaign ownership. Drivers link only to their
   own assignment selected through the existing Jobs page and detail API;
   admins to canonical campaign hubs. A small notification consumer amendment
   makes Jobs honor `assignment_id` instead of relying on its first 50 results.
   This is within notification link scope and touches no onboarding/contact flow.
   Unresolvable,
   malformed or unauthorized context yields generic copy and no name/link.
   Only campaign-related notification types may resolve references; account-only
   or unknown types cannot gain context from a campaign ID. When multiple typed
   references are present they must resolve and agree on campaign and assignment;
   contradictions fail closed. Test feed and mark-read for these boundaries.
   No historical notification payload, fingerprint, delivery or read-state edit.
   Feed and mark-read use the same projection. Frontend shows accessible Open
   links, closes panel on navigation, preserves polling, retry and offline states.
2. Every user edit to change-form budget, dates or reason invalidates the displayed
   preview immediately. A response for a request sent before an edit cannot
   restore a confirmable preview. Bind the preview to a local form revision/
   request identity, require a fresh preview, and preserve confirmation dedupe,
   backend digest checks, funding and independent approval. Test all five fields,
   delayed responses and fresh-preview recovery, as well as confirmed resets.
3. Newly frozen export issuance snapshots use Not enough data for suppressed
   metrics and an incremented export schema version. Leave measurement formula,
   measurement snapshots, historical issuance snapshots and the deterministic
   renderer unchanged if inspection confirms wording is frozen into the export.
   Existing v1 issuance retries/downloads must reproduce original bytes/hashes;
   new v2 issuance of an old reproducible measurement run uses the new text.
   Anchor the old fixture to independently captured pre-change CSV/PDF hashes;
   replaying its original issuance request keeps its v1 snapshot/version.
   Tests prove CSV and PDF labels, old/new hashes, worker retry and measurement
   reproducibility. No migration or mutable replacement of an issued artifact.
4. Shared money display uses two decimal places and grouping (₦1,234,567.00).
   Advertiser campaign quotation and change preview raw currency/decimal displays
   use it; VAT shows its stored rate as a percentage (VAT 7.5% · ₦…). Inspect
   shared advertiser/driver display consumers for raw values. Inputs remain exact
   editable decimal values; monetary calculations and stored values are untouched.
   Completed/cancelled campaigns pass an explicit presentation flag disabling
   Request custom quotation, while preserving historical terms. Landing copy
   describes campaign-area daily miles and proportional short-day pay without
   promising a rate. Earnings page uses plain titles and status explanations,
   distinguishes actual cash Paid from bookkeeping statuses, explains waiting
   earnings and reviews, and uses a neutral colour for zero holds. Keep every
   amount source, debt/correction semantics, pagination, trip link and offline
   fail-closed display; improve narrow-width wrapping where needed.

## Entry points and records

Existing notification schema/API/service/component and their focused tests;
report issuance snapshot builder and report rendering/issuance tests; shared
`lib/format.ts` and tests; advertiser campaign commercial/change panels and page;
marketing driver component; driver earnings presentation and touched tests.
All three baselines in architecture §9 are regenerated from the actual API:
`openapi.json`, `frontend/src/lib/api/schema.d.ts`, `docs/api/openapi.snapshot.json`.
Run existing R14-B native contract fixtures. No hand-merge of generated files.
Update requests first (done), relevant client topics, D68 and affected Q rows,
architecture v1.125, and QA-08/QA-14 with truthful local evidence. Requests stay
IN PROGRESS until master integration; package queue remains unchanged.

## Acceptance and verification

| ID | Criterion | Required evidence |
| --- | --- | --- |
| C1 | Campaign names/links are accurate and scoped for all three roles | Focused feed API tests including other tenant/driver, revoked membership, inactive organization, missing/malformed refs, no untrusted payload URL/name disclosure; browser Open navigation |
| C2 | Edited or late preview cannot be confirmed; fresh preview works | Meaningful failing UI reproduction, five-field and delayed-response tests, real preview/edit/repreview/confirm at both widths |
| C3 | New CSV/PDF use new text; old issuance integrity survives | Old/new snapshot and byte hash regression, existing measurement reproducibility and issuance retry/download tests; inspect a report download |
| C4 | Money/VAT, terminal quote, landing and earnings presentation meet brief | Focused formatting/panel/page tests, unchanged amount sources and payout logic, browser campaign/earnings/landing at both widths |
| C5 | Contract/quality baselines are aligned | OpenAPI/snapshot parity, generated types, native fixtures, touched tests, lint/type checks; changed-source coverage ≥90% lines and ≥80% branches |
| C6 | Real layouts remain usable | Before/after screenshots: notification panel, change preview, earnings, report download at desktop and 375px; review overflow and loading/empty/error/accessibility where applicable |
| C7 | Required independent reviews accept final state | Clean-context plan review; notification security review; report-integrity review; consolidated minimal-change-review PASS after corrections |

Run only touched test files, one lane test container at a time; inspect `cv-`
containers first, never stop pre-existing containers. Backend and Vitest coverage
are sequential. Use existing seed unchanged for local UI; explicitly report any
missing demo state rather than editing seed. Record evidence once after stable
verification, with no containing-commit SHA. Owner/Claude integration review and
combined CI remain external finishing obligations, not locally claimed passes.

## Owner Claude review corrections — 7 October 2026

The owner approved the code and requested amendment of the unpushed commit:
remove committed LCOV, logs, PDFs and excess screenshots; retain at most eight
375px earnings/notification/preview/cleared-preview images and report hashes.
Earnings card/detail/badge state names use Ready to pay, Waiting for review and
Paid consistently; remove the repeated On this page count summary and retain one
short explanation. Notification panel content uses sentence case and the body
font; only small labels remain uppercase. This is correction of C4/C6 and
proportionate evidence, not a new authority/data/API scope. Rerun touched frontend
tests and refresh screenshots/receipt; same consolidated reviewer must reassess
until PASS before the authorized local amend. No push.

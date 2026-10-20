# REQ-180 Worker A Batch 2 delivery contract

Owner authorization: implement audit recommendations D1, D2, D3, D4 and D8 on
`fix/req180-batch1-backend` after Batch 1's reviewed local commit `f10ad19`.
REQ-188–192 and decisions D90–94 belong to Worker A; architecture stays v1.144.
No screen/component edits, push, provider calls, deployment or launch closure.
Docker was returned to Worker A on 2026-10-19; one capped container, serial checks.

## D4/D2 subject-inventory integration amendment

The existing DSR registry requires every user-reachable model to be classified.
New `campaign_enquiries` carries contact PII and conversion-owner linkage;
`report_schedules` carries operational report lineage. Register enquiries as an
inventory data class. Count each enquiry row once (one OR predicate) when its
contact email, trimmed and lower-cased, matches the subject user's email,
normalised the same way, OR when its explicit converted owner is that user.
Treat email as a candidate contact linkage, not proof of who submitted the public
form (D93: no inferred email ownership). A disclosure must not include the
content of an email-matched enquiry without staff verification; existing
disclosure/erasure review remains. Known gap: enquirers who never became users
are not discoverable, because the inventory is keyed by user.
Do not expose enquiry content through a new public/advertiser endpoint, introduce
an erasure command, invent retention duration or claim automatic deletion. Existing
DSR completion fails closed while linked records remain without approved evidence.

Classify report schedules alongside existing report issuances as shared/operator
business authority, whose actor linkage is covered by immutable audit. The cursor
has no subject FK and holds only a campaign traversal position. Add focused real
DB inventory tests for case-normalized contact matching, explicit converted owner,
foreign/unrelated contacts and exclusion of staff-only conversion attribution;
rerun the touched registry's coverage test so no new reachable table is unclassified.
Implemented 19 October after the privacy review found it missing:
`campaign_enquiry_contact` rule plus `report_schedules` operator exclusion, with
`test_enquiry_contact_counts_matching_email_and_converted_owner_once`.
This integrates D93/D91 with existing privacy authority; no new product value or
decision row. Privacy and consolidated reviewers cover the final integrated diff.

## Orchestrator additions amendment (19 October, Claude Worker A)

Worker A moved from the Codex thread to a Claude agent in the same worktree.
The five queued orchestrator messages were read and cancelled. Everything above
stands for unchanged scope. The additions below, and the D4/D2 subject-inventory
amendment above, need one plan-amendment review.

1. **Budget used (owner's option A, 19 October; D103 / REQ-193).** The
   80/95/100 alerts measure advertiser billing commitment, not metered spend.
   Before production starts, that is the confirmed funding allocated to the
   campaign. From production start, it is the effective invoice obligation:
   gross after corrections, with fixed costs included. Expose that figure
   read-only, with no new money rule and no alert change.

   The field is `budget_used:{amount,budget_amount,currency,basis:"funding"|"invoice",as_of}`
   (orchestrator simplification, 19 October: `period` dropped).
   - `amount` is always the booked total, whatever the budget type. The display
     never shows a daily figure, because the daily figure is the whole
     obligation on the production-start date and `0.00` on every later day.
   - `budget_amount` is the positive total budget, or null when there is none.
     Daily-only campaigns cannot pass submission (D38d), and the seed has none.
   - **Alert defect found and fixed (D104, owner's choices of 19 October):**
     quotes were never checked against the budget, so a funded normal campaign
     reached 100% (gross = budget) or more (VAT/fixed lines on a media budget)
     and paused. Full prepayment on one day also crossed any daily budget. The
     owner chose fix option 1 with the daily add-on, then rule a, then the
     max() correction:
     - accepting a quote (accepted once) sets the budget to
       max(current budget, accepted gross); a higher budget is never shrunk;
     - **rule a:** while booked ≤ the accepted gross the state is
       `within_budget`; beyond it, 80/95 alert on `>=` and the pause fires on
       booked strictly above 100%; resume is allowed at booked ≤ the resume
       limit;
     - only the total budget is enforced; a stored daily budget no longer
       pauses, and the sweep skips campaigns without a positive total budget.
     Funding is capped at the accepted obligation and campaign expansions move
     driver-liability headroom, not the invoice, so only extra charges (debit
     notes after production) reach the warnings. 80/95 cannot track campaign
     progress; that is REQ-196 (NEEDS ANSWER: a client spend-accrual rule plus
     expansion re-quoting or a delivery meter), not built.
   - **Daily-only budgets:** unreachable. Submission requires a positive total
     budget (D38d) and the seed has none.

   `amount` comes from the same `_campaign_billing_spend`. Its new `lock=False`
   read mode affects only the terms read, so the GET never takes FOR UPDATE; the
   alert path keeps its locks. Under READ COMMITTED an unlocked read shows only
   the state before or after a commit.
   - `currency` is the campaign currency.
   - `as_of` is one database clock reading per response.
   - The amount is `0.00` when there are no terms or funding.
   - The object is never null. A corrupt campaign makes the read fail, as it
     already does elsewhere.
   - Amounts are decimal strings, never summed across campaigns or currencies.

   The field is added to `CampaignListItemRead`. A new `AdvertiserCampaignRead`
   is used by the advertiser GET detail and by advertiser create, PATCH and
   submit, so every advertiser campaign response carries it. Each campaign costs
   about 3–4 queries; that is acceptable at limit ≤ 100, and there is no batched
   copy of the money logic. Tenant rules are the existing list/detail rules.

   A deterministic seed test asserts that every seeded running campaign has
   `0 < amount <= budget_amount` through real funding or production records, and
   that a budget sweep over the seed changes nothing. The one-day daily-ratio
   pause was the defect fixed by D104.
2. **Pending cancellation read (D7 / REQ-194).** There's no new endpoint. Add an
   optional `campaign_id` query to the existing `GET /advertiser/complaints`.
   It is applied in SQL inside `_owned` before the list limit. An unknown or
   foreign campaign returns an empty list, so there is no existence oracle.
   Summaries still carry no reference ID.

   A cancellation is **pending** when an item has category
   `campaign_cancellation` and status `open` or `answered`, and the campaign is
   neither `cancelled` nor `completed`. Operational note: staff who decline a
   cancellation must resolve the thread. The client is
   `readCampaignCancellationRequests(api, campaignId)`.
3. **D8 applicant state (D94 / REQ-195).** Extend the existing continue
   response with `state` and `changes_reason`, reusing the step predicate.

   **Details step** (the latest person/payee submission):
   - none → `details_needed`;
   - pending review → `details_in_review`;
   - approved with no expired document outcome (only the payout verification
     outstanding) → `details_in_review`;
   - rejected → `details_changes_needed`;
   - expired, or approved with an expired document outcome →
     `details_changes_needed`.

   **Car step** (the car chosen by the existing `application_vehicle_view`):
   - no car or submission → `car_needed`;
   - pending → `car_in_review`;
   - approved and still current by `_vehicle_approved` (while the application is
     still pending) → `car_in_review`;
   - rejected → `car_changes_needed`;
   - expired, or approved but no longer current → `car_changes_needed`.

   `changes_reason` is the existing applicant-safe sentence from
   `driver_review_notifications.REASONS` for a rejection. Expiry or out-of-date
   evidence uses the expired-evidence sentence, and an unknown code uses the
   existing fallback. It is null in other states. There are no IDs, internal
   statuses or codes.

   **Cut (orchestrator acknowledged, 19 October):** `approved`. Final approval
   terminalises the application and revokes the capability, so the link gives
   the generic 404. The applicant then waits for Terrax's account-setup email,
   which is sent once staff issue setup. Worker B's expired/used-link copy must
   tell an approved applicant to check their email for that link.
4. **Simplicity and the live system.** The advertiser cancellation route was
   removed, so the service's advertiser mode was used only by the seed and
   tests. **Cut it**: the engine becomes staff-only. This supersedes "Keep
   existing internal advertiser callers" in the staff amendment below.

   The rich seed now follows the production flow:
   - the advertiser raises a `campaign_cancellation` request through
     `raise_complaint`;
   - `staff[0]` cancels with that complaint linked, passing their
     `session_version`;
   - both request IDs are deterministic uuid5 values, so reruns replay;
   - the `cash_refund_due` assert stays, because the outcome comes from the
     refund window and remaining cash, not from who acts;
   - the thread ends `answered` on a cancelled campaign, so it is not pending.

   Converted lock-order and race tests (ingestion locks, billing concurrency,
   corrections, PKG-03 corrections) keep proving the same race under staff
   mode; the money specialist rechecks them. `docs/demo-data.md` is updated if
   it describes advertiser self-cancel. Batch 2 adds no demo-only app behaviour.

   Each new item is justified:
   - `budget_used`: the screen's only truthful money figure;
   - the complaint filter: the only tenant-safe way to find the request;
   - the two D8 fields: one screen state.

   There is no new state, status, job or endpoint.
5. **Edge tests to add.** These close gaps in the existing inventory.
   - **Budget alerts:**
     - full payment, and a staged deposit plus balance, never warn or pause;
     - extra charges beyond the agreed total warn at 80/95 and pause above
       100% (₦1.5m budget, ₦1m quote: ₦1.4m alert, ₦1.43m urgent,
       ₦1,500,000.01 pause);
     - a stored daily budget is ignored;
     - after a cancel, later sweeps add no pause transition and do not repeat
       an already-sent notice. This is current behaviour and is not changed;
     - an alert fires again after a budget increase.
   - **`budget_used`:**
     - `0.00` with no terms;
     - funding basis, invoice basis and over 100%;
     - a campaign with a daily budget still shows the booked total;
     - each amount equals the locked `_campaign_billing_spend` total, and the
       latest evaluation's `billing_spend_amount` while the facts are unchanged
       and that evaluation's `budget_basis` is `total`;
     - after a mid-run cancel, the value equals the engine's post-settlement
       obligation and does not grow later with no further billing facts;
     - a pre-production cancel with its receipt reversed reads `0.00`;
     - NGN and USD campaigns in one organisation each show their own currency;
     - a foreign campaign returns 404;
     - the seed test above.
   - **Enquiry:** converting when the enquiry email already belongs to a user
     creates the company without linking or changing that user.
   - **D8:**
     - 404 after final approval;
     - every state above, including the expired and out-of-date cases, with
       its reason.
   - **Staff cancel:** a completed campaign keeps the existing ineligible-state
     error.
   - **Pending read:** tenant scoping; an old request beyond the 100 most
     recent complaints is still found.

   Already covered: zero spend, single-fire thresholds, results with 0/1/2/3
   cars, overlapping sweeps, a mid-week cancel report, double enquiry
   conversion, expired/reused/rejected links, staff double/concurrent/foreign/
   already-cancelled cases, and artwork cancel races in both lock orders.

6. **D1 area-contact fix found by the seed run (19 October).** Area contacts
   reused the audience-export cell model, which requires whole-hour windows,
   so a measurement run for a completed or cancelled campaign whose period ends
   mid-hour failed. Area contacts now sum the same per-cell ping allocation
   (quantized per cell, as before) directly; audience exports keep their rule.
   Regression: `test_area_contacts_allow_a_period_that_ends_mid_hour`.
7. **D105 / REQ-197: three-car areas only (owner decision, 19 October).** With
   the crash gone, the seed showed the D90 composition rule: once a report
   released areas, the tenant's dashboard summary, campaign summaries, trips,
   heatmaps and audience exports returned 409 for good. The owner removed the
   cross-output rule and kept the three-car minimum per area.
   - Removed: `campaign_performance_disclosure.py` (area reservation, history
     conflict check, export re-verification), the
     `advertiser.campaign.performance.area` disclosure route, the
     `campaign_area_composition_protected` handling, the snapshot
     `area_release_fingerprint`, and the report's own composition gates
     (complete coverage, nonoverlap, small residual, all-trips-estimated).
   - Kept: three distinct cars per area row; inconsistent frozen authority
     fails closed; area contacts are null unless every trip in the area has an
     estimate; every other fine-output floor and legal/method/source rule.
   - No migration: the generic disclosure history table predates D90.
   - Tests: the pinning cross-clock and reservation tests are replaced by
     three-car rule tests and an HTTP regression in which, after a report
     releases an area, the dashboard summary, campaign summary, trips, heatmap
     and audience export all answer. The seed's export workaround is undone;
     the seed test confirms the Marula Kitchens dashboard loads.
   - This supersedes the "Specialist corrections" composition paragraph below.. **Consolidated review corrections (19 October).**
   - Stale advertiser `/report` tests now read the coarse projection; score,
     title and ROI checks moved to the admin measurement-run read.
   - The export disclosure re-check was deleted: export bytes are frozen from
     the already-coarse run, and `record_disclosure` again commits a suppressed
     decision as before.
   - Daily-budget leftovers removed: the policy context has no daily fields,
     evaluation and notice identities carry no Nigeria date, and a daily budget
     change alone no longer counts as a changed fact for resume.
   - The retired `blocked_external_policy` state and the `external_gate`
     column are gone (migration 0108 drops never-acted-on blocked rows); every
     evaluation has basis `total`.
   - Stale budget-policy env comments removed; `PERFORMANCE_POLICY` is used
     instead of copied strings; unexpected report-schedule failures log the
     schedule ID and error class.

**Records:**
- REQ-193–197 rows (REQ-196 NEEDS ANSWER); D105 for the three-car area rule.
- D103 (budget-used display, owner's option A) and D104 (budget alert fix),
  both 19 October, with the Q15 row; Q13 notes REQ-195.
- Client-decision topic history for budgets and D8.
- The architecture v1.144 entry.
- Every contract change regenerates all three architecture §9 baselines, the
  generated TypeScript and the R14-B native fixtures.

**Reviews:** money (items 1 and 4), privacy (item 2) and security (items 2 and
3) specialists, plus the consolidated review, cover these additions.

## Staff whole-campaign cancellation amendment

The controller explicitly adds the missing D7 staff action. Proposed
`POST /api/v1/admin/campaigns/{campaign_id}/cancel` accepts
`{reason:string,client_request_id:UUID,complaint_id?:UUID|null}` and returns 201
existing `CampaignCancellationRead`, including original cutoff, settlement and
state results. Reason keeps the existing trimmed nonempty 1000-character bound.
Use the SAME `request_campaign_cancellation` engine, adding an explicit internal
admin mode rather than impersonating an advertiser or duplicating economics.
Keep all financial rules/tests. (Superseded 19 Oct: the advertiser mode is
removed and its seed/test callers now use staff mode.)

Lock campaign terms then require/lock the current active admin with `FOR SHARE`,
compatible with message actor-FK key-share while blocking account/session changes;
preserve `require_active_admin`'s default exclusive lock for other callers. Recheck
the HTTP dependency's captured session version under that shared lock. Lock/refresh the
campaign and derive its organization from that row. Staff authority is global as
in existing admin actions; never accept a caller-supplied organization. A missing
campaign returns 404. If supplied, lock the complaint and validate advertiser
party, exact `campaign_cancellation` category, campaign reference and same
campaign/organization before any new financial write; foreign/missing/wrong-category
links share 404 `CAMPAIGN_CANCELLATION_REQUEST_NOT_FOUND`. No complaint link is
required. Preserve the campaign's immutable cancellation retry identity, adding
the optional complaint ID to admin request fingerprinting so changed linkage
conflicts rather than silently producing a second reply.

After actor/campaign authority, check cancellation replay/fingerprint BEFORE any
mutable complaint validation: exact replay returns the original; changed reason,
actor, request UUID or link (including missing/foreign links) gives 409. Normalize
omitted/null complaint IDs equally. Only a new cancellation validates the link.

For a new successful linked cancellation, reuse `reply_as_staff` with the fixed
plain text `The campaign has been cancelled.`, existing notification/audit rules
and a server-owned UUID derived from the new cancellation ID and a fixed namespace,
separate from caller message IDs. Mark the reply answered rather than inventing an
automatic complaint-resolution rule. Cancellation, reply, settlement, audit and
notices commit atomically; a full/invalid complaint or reply failure rolls back
everything. Exact retries return the original cancellation without new messages,
audit or notices; changed reason, link, request ID or actor conflicts. Audit
`admin.campaign.cancelled` and the cancellation's requested_by identify the staff
actor; no provider transfer is performed. Existing staff assignment cancel stays
untouched. No migration/new decision row unless the plan reviewer identifies one.

API client `cancelCampaignAsStaff(api,campaignId,{reason,clientRequestId,
complaintId?})` maps to snake_case JSON. Add real API/DB tests for active admin,
role/disabled denials, missing campaign, same-tenant complaint binding, trimmed
reason/replay/conflicts, unchanged unlinked support, atomic linked reply failure,
concurrent retries, named audit and the existing financial cutoff/refund outcomes.
Also test same-admin ordinary replies in both lock acquisition orders, disable/
session-revocation races, caller UUID collision with an ordinary reply, exact
replay after thread-full/status changes and injected reply/notification rollback.
Regenerate all three baselines and native fixtures; money and security specialists
and consolidated review cover the integrated addition. This replaces the earlier
reported gap; the prior source-only D7 verdicts predate this amendment.
Amended plan PASS: `mcp:bb4b731b-918c-48c0-abce-2a31de70cef3`, actual
gpt-6.1-sol/high on codex-fresh-20261012. All three lock/reply/replay refinements
above were accepted before implementation. No additional D-row or migration.

## D7 cancellation-support amendment

The controller assigns backend-only support for Worker B's recorded D7 decision:
replace advertiser self-service cancel with Ask Terrax to cancel. Add exact
`campaign_cancellation` to existing ComplaintCategory. It is advertiser-only and
requires `reference_type:"campaign"` plus an owned `reference_id`. The existing
`message` is the reason/first thread message (trimmed, nonempty, max 2000) and
`client_request_id` keeps existing idempotency/replay-conflict behavior. Reject
missing/wrong-kind references, other-tenant/missing campaigns and driver use
without creating anything. Existing active organization membership, auth and
support permissions apply; do not turn a support request into a campaign write.

Create through existing `POST /api/v1/advertiser/complaints`; existing advertiser
and staff list/detail `category` fields carry the new enum unchanged. No projection
field or second support channel is added. No campaign, assignment, financial
cutoff, liability, payment/refund, payout or tracking state changes on submission.
Remove `/api/v1/advertiser/campaigns/{campaign_id}/cancel` and its dedicated router;
no alias/shim. Preserve the internal financial cutoff/settlement engine and
existing staff cancellation behavior. Do not rewrite cancellation economics.

Initial source discovery found staff assignment cancellation but no staff
whole-campaign cancellation route. The controller has now explicitly added the
missing action through the SAME existing financial engine, as pinned in the
staff amendment above. Worker B owns D7 decision rows and screen/BFF changes.

Plan: extend schema enum and existing category/reference service validation;
remove obsolete advertiser router registration/file and audit-route entry; update
affected API tests to preserve internal financial/cutoff tests independently of
the removed public route. Add real tenant-scoped API/service regressions for
required reference, category permissions, reason, replay/concurrency, summaries/
details and no campaign/economic changes; assert the old route is absent. All
three baselines/native fixtures move with Batch 2. Money/privacy/security and
consolidated reviewers cover the bounded change; no new decision row from A.

Amended plan review PASS, `mcp:bb4b731b-918c-48c0-abce-2a31de70cef3`, reported
gpt-6.1-sol/high on codex-fresh-20261012. The reviewer confirmed that no migration
or new projection field is needed, driver categories must explicitly exclude the
new value, and existing per-raiser retry identity must remain unchanged. The
initially missing staff action is now covered by the separately reviewed staff amendment.
D7 security/privacy source review PASS
(`mcp:d5fde1f9-0353-4c53-9df2-acb20816518f`, reported gpt-6.1-sol/high on
codex-fresh-20261012). No source findings; execution, synchronized baselines and
final integrated specialist approval remain pending.
D7 money source review PASS (`mcp:83f673a3-292c-415b-a943-67aa7daea9d1`,
reported gpt-6.1-sol/high), with no source findings. The preserved financial
engine and staff assignment path were checked; this does not close D3's pending
runtime reassessment or approve the later staff amendment, which has its own plan PASS.

## Owner-added job-artwork contract amendment

The orchestrator adds a read-only driver view of the advert attached to a job,
under REQ-180 Batch 2, reusing existing managed-file preview authority. No new
decision row is requested: this exposes the approved artwork already frozen in
the driver's offered terms, without broadening advertiser/campaign discovery.

Proposed `POST /api/v1/driver/campaign-assignments/{assignment_id}/artwork/download`
has no body and returns existing `FileDownloadRead:{url,expires_in_seconds}`.
POST follows existing signed-preview issuance/audit conventions; no job, file or
review state changes. Typed wrapper: `readDriverJobArtwork(api,assignmentId)`.
Worker B uses existing frozen creative MIME/type from the offer for presentation.

Authorization is scoped to the currently authenticated active driver, exact
assigned profile and live job. Offered work must be unexpired; accepted work
awaiting installation retains its offered artwork; active work retains it until
the campaign/job ends. Declined/expired/cancelled/completed/deactivated work,
suspended or rejected driver profiles (security review note, 19 October) and
other drivers deny with a generic 404. Accepted/active jobs may outlive the offer
acceptance deadline and may be viewed before campaign start or while paused; no
installation/trip eligibility is needed for this read. Terminal campaigns deny
even if assignment state is stale. The lifetime is the earlier frozen/current
campaign end, additionally capped by offer expiry only while offered. Locks and
fresh role/status/session checks serialize new issuance against cancellation or
revocation and prevent cached-authority bypass. Already returned URLs remain
usable only until their bounded expiry; immediate URL revocation is out of scope.

Read the exact frozen creative/file identity and validate its hashes, campaign and
tenant binding. The corresponding creative must still be approved and match that
frozen file/content identity; never substitute newly uploaded artwork. Require a
clean creative-purpose file, then reuse private object stat/checksum/MIME/size
verification and signed GET/audit. Add an optional absolute deadline to the
existing helper, leaving other callers unchanged. After storage verification,
compute positive whole-second TTL as min(60, configured TTL, remaining lifetime).
After awaited signing, discard the URL if completion time plus that TTL exceeds
the deadline. A
missing, replaced, revoked, quarantined or mismatched file fails closed. Return
no creative metadata, advertiser details, separate object-key field or other campaign fields.
Private preview responses are non-cacheable. No file-ID input or generic driver
access to advertiser storage is added.

Add focused tests for owned live offer/accepted/active success; wrong-driver and
role/terminal/expiry denials; frozen identity/tamper/replacement/scan/object checks;
safe two-field response/audit/TTL; and deterministic cancellation or revocation
overlap in both lock orders, accepted/active after offer expiry, delayed stat and
sign expiry, and unchanged TTL behavior for existing helper callers. Campaign
terms lock precedes fresh locked user/session and campaign/assignment/profile
ownership, then creative and file locks; refresh ORM state and hold all locks
through verification/signing/audit commit. Recompute nested creative content
identity, without requiring unrelated metadata/version equality or committing
inside service helpers. Update all three API baselines and native fixtures with Batch 2.
Amended plan review PASS, `mcp:bb4b731b-918c-48c0-abce-2a31de70cef3`, reported
gpt-6.1-sol/high. Privacy/security specialists cover the amendment; the consolidated final review
covers the integrated diff. Docker execution is now in progress after handoff.
Artwork source security/privacy review PASS (`mcp:d5fde1f9-0353-4c53-9df2-acb20816518f`,
gpt-6.1-sol/high); this is source-only evidence, not final runtime/specialist approval.

## Outcome and plan

1. **D1 / D90:** a campaign owner can read campaign-wide distance, completed
   trips, driving days and clearly estimated views with one or two cars. An area
   breakdown includes only areas with at least three distinct cars. Empty data
   returns zero operations and unavailable modelled results when provenance is
   absent, never invented estimates. Expose only these coarse totals and safe
   area rows; no driver/trip identifiers, timestamps, daily rows or contribution
   counts that identify a suppressed area. Reuse authoritative analytics,
   impression, terminal-cohort and frozen measurement machinery. Replace the
   blanket campaign-total floor in the current reporting projection, preserving
   tenant authority, current-source checks, method/legal gates, the audience and
   heatmap boundary, and existing protection for all other fine breakdowns.
   Freeze this explicit policy in new report snapshots; never rewrite an issued
   immutable artifact. Privacy review must cover differencing and partial areas.
2. **D2 / D91:** a bounded recurring worker creates reproducible measurement runs
   and CSV/PDF issuance jobs weekly and at campaign end. Weeks are seven-day
   campaign-relative windows; weekly reports are cumulative from campaign start
   to each completed weekly boundary, final reports cover campaign start to end.
   Coincident weekly/end boundaries yield one final report. Missed periods catch
   up durably without duplicate runs/artifacts; each campaign failure is isolated.
   Existing claim/lease/write-receipt/private-file publication remains authority.
   A dedicated disabled, non-login report-automation identity supplies durable
   attribution; only internal report/measurement authority may recognize it.
   It cannot access ordinary admin APIs or money operations. A simple staff
   re-run command generates a fresh request server-side and uses the same
   pipeline, without date/UTC/request-ID entry. Preserve legal/method/source
   failures as explicit retriable operational state, not successful reports.
3. **D3 / D92:** use the owner's fixed 80/95/100 percent budget thresholds for
   every campaign by default, reusing billing-spend facts, idempotent notices,
   pause serialization and existing guarded staff resume. Eliminate obsolete
   configuration/external-policy blocking and remove the staff policy-evaluation
   command/DTO surface that exists only for its panel. Keep the normal
   commercial summary and budget-resume command. No driver-pay basis, new fee,
   threshold customization, or relaxation of funding/payout authority.
4. **D4 / D93:** persist accepted website enquiries before returning success,
   independent of email availability. Retain byte limit, schema, feature switch
   and fail-closed rate limiter. Remove the obsolete email-only send path. Add
   active-admin paginated/searchable New enquiries list and detail, with a
   row-locked idempotent create-advertiser action. Reuse company creation and
   existing advertiser-account constraints; never auto-activate a login, grant
   membership to another company's login or expose enquiries publicly.
5. **D8 / D94:** reuse hashed capability-scoped application access, replacing
   pasted-code email copy with a 24-hour continuation link. Put the capability
   in a URL fragment so servers/referrers do not receive it. Email chooses the
   current details/car step; a body-only continuation read revalidates authority
   and returns the current step/expiry. Existing upload/submission bodies keep
   `application_access_token`; Worker B consumes/clears the fragment and holds
   the capability in the existing page session. Preserve non-enumerating public
   responses, expiry/revocation/terminal locking and no log/payload token leak.
   No account activation, password-reset/setup TTL change, SMS or provider call.

## Intended entry points and Worker B contracts

- Current advertiser campaign report/results projection and frozen exports gain
  `totals` (distance_m as decimal string, trip_count and driving_days integers,
  estimated_views decimal string or null) and `areas` (area_id, name, trip_count
  and modelled_potential_contacts only for safe areas with 3+ distinct cars).
  The precise reviewed DTO is pinned in the Worker B contract below.
- POST `/api/v1/admin/campaigns/{campaign_id}/reports/re-run`, active admin,
  no body → 202 current `ReportIssuanceRead`; backend selects the latest completed
  weekly/final window, or campaign start to now for an ongoing first partial
  period. This is an explicit manual new run, not an accidental same-page retry.
- GET `/api/v1/admin/campaign-enquiries?status=new|converted&q=&limit=&offset=`
  → `{items,total,limit,offset}`; detail read by ID; POST
  `/api/v1/admin/campaign-enquiries/{id}/create-advertiser` accepts only existing
  company/account setup choices required by the reused creation service and
  returns its organization ID plus enquiry state. Exact body pinned at review.
  Public POST `/api/v1/campaign-enquiries` keeps its non-sensitive submitted reply.
- POST `/api/v1/auth/driver-onboarding/continue`, JSON
  `{application_access_token}` → `{step:details|car, expires_at}`. Invalid,
  expired or revoked tokens return the same generic 404. Email URL is
  `/apply?step=details|car#application_access_token=…`; token never in path/query.
- Add typed API-client functions for all new commands/reads. Baseline changes
  update root OpenAPI, docs snapshot and generated TS together, then rerun R14-B.

## Acceptance and verification

- W1: real one/two-car and empty campaigns show correct four totals; a mixed
  two-car/three-car area cohort suppresses only the former. Wrong tenant/role,
  stale estimates and absent methodology remain denied or explicitly unavailable.
  New live/frozen/CSV/PDF projections agree and expose no fine-grained identifiers.
- W2: weekly, exact-end, partial-end, overdue catch-up, concurrent retries and
  failure/recovery create the correct immutable lineage once. Automation cannot
  log in or gain admin authority. A manual rerun creates a fresh authorized
  report without user date/request-ID entry.
- W3: default campaign spend crossing 80,95,100 creates correct deduplicated
  notifications/pause; existing money authority remains; removed panel route is
  absent from OpenAPI and API-client callers are updated within owned scope.
- W4: accepted public enquiries survive disabled email, throttled/invalid bodies
  never persist, staff listing/search/pagination is exact, conversion retries and
  concurrent conversions converge, unauthorized/tenant-account conflicts deny.
- W5: registration and renewal email links target the current step, work through
  24 hours and fail at expiry/revocation/terminal state, never disclose capability
  in response/log/URL query. Link continuation and existing mutations retain
  ownership and replay behavior; code wording and obsolete code-only helpers go.
- W6: focused tests only in touched files, provider-free live integration in one
  capped owned container when Docker is returned; contract drift and native
  fixtures; exact screen handoff, operational/decision records and cleanup.
- W7: separate plan review before build; privacy (D1), security (D8 plus automation)
  and money/budget specialist reviews; consolidated minimal-change-review PASS
  on the final integrated diff and evidence before commit. No push or full local
  backend suite, and no reviews deferred until after CI.
- W8: the assigned driver can obtain only the exact frozen approved/clean artwork
  for a live offer or job, with the ownership, lifetime, storage, locking and
  minimal-response checks in the artwork amendment.
- W9: advertiser cancellation requests use the existing complaint channel with
  an owned campaign and reason, appear in both parties' existing category fields,
  preserve retry/tenant authority and change no campaign or economic facts. The
  advertiser cancellation route is absent; internal settlement/cutoff behavior
  and staff assignment cancellation remain unchanged.

Primary risks: area/whole-total differencing, immutable provenance, automation
attribution versus human authorization, weekly catch-up fairness, manual rerun
identity, budget notice epochs, enquiry PII/duplicate conversion, URL fragments
and capability leakage, existing terminal/review locks. Reuse existing code and
remove superseded behavior within scope; no compatibility shims for demo data.

## Accepted plan-review refinements

Round 1 FIX (gpt-6.1-sol/high) identified valid specifics, adopted here:

- Public `CampaignPerformanceRead` replaces the rich response on the existing
  `/advertiser/campaigns/{campaign_id}/report` route: `campaign_id,start_at,end_at`,
  `totals:{distance_m:string,trip_count:int,driving_days:int,estimated_views:string|null}`,
  `areas:[{area_id:UUID,name:string,trip_count:int,modelled_potential_contacts:string|null}]`,
  coarse `completeness` and `uncertainty` text only. No raw/daily/contributor facts.
  Driving days count distinct **Africa/Lagos terminal dates**; trip_count counts
  qualifying completed trips, independently of analytics coverage. Distance uses
  computed authoritative analytics; views retain null for absent provenance.
  Internal measurement snapshots/admin reads stay rich, private and reproducible.
  Before the first issued weekly run, the same public projection can use the
  current authoritative terminal cohort for campaign totals; area detail stays
  empty until frozen area authority is available. This avoids “no report yet”
  hiding otherwise available totals. No ad-hoc fine time-window fallback.
- Freeze the coarse projection, area labels and `campaign-performance-d90-v1`
  disclosure policy in new run snapshots. Derive area contacts by the existing
  frozen cell allocation, with per-zone trip deduplication; no invented area
  distance. (Superseded by D105: only the three-car minimum applies; the
  complementary-suppression sentences below no longer hold.) Three cars is necessary for each released area. If two-car residuals,
  partial coverage, overlapping areas or comparison with existing released detail
  allow reconstruction of a protected cohort, suppress complementary area detail,
  retaining totals. W1 does not promise the three-car row will always be released.
  Preserve all fine-output/audience/heatmap protections. New export v4 uses the
  same coarse projection and existing renderer structure; unavailable optional
  scores/segments cannot block totals. Ready governed linked recommendations
  remain; source corruption and applicable ROI authority remain fatal.
- Persist one scheduled obligation per `(campaign_id,period_start_at,period_end_at)`
  with stable measurement/issuance request UUIDs, resulting IDs, attempts, next
  retry and safe error code. Generate due windows for active/paused/completed and
  cancelled campaigns; cancellation's immutable cutoff replaces planned end.
  No report for an invalid/empty date interval. Weekly/end coincidence shares
  the same identity. Persist obligations before processing; row locks exclude
  concurrent processors. Atomic run/issuance work and stable retries recover
  crashes before or after either durable boundary. A durable campaign cursor
  visits bounded pages fairly, adding the oldest missing window per campaign;
  each failed obligation backs off without blocking later work. Manual reruns
  use fresh server UUIDs and do not alter scheduled identities.
- The disabled reserved report identity is created by migration and checked by
  report-only service authorization through measurement, composition and later
  publication rechecks. Ordinary `require_active_admin`, JWT APIs and money
  authority remain unchanged. User editing/activation and human-user lists
  protect/exclude that identity. Test ordinary denial plus actual publication.
- Budget resume uses no fourth ratio: an active admin supplies a reason after
  confirmed changed funding/budget facts, and a fresh serialized evaluation must
  show spend strictly below **every** applicable 100% limit. Unchanged/stale facts
  deny; there is no auto-resume. (Superseded by D104: resume is allowed at spend
  at or below 100%.) Retain `BudgetEvaluationRead`
  because commercial summaries embed it; remove only the obsolete panel command
  and deployment-policy blocking/settings. Test jumps/epochs and 80–100% headroom.
- Enquiry conversion body is exactly `{owner_user_id?:UUID|null}`, extras denied.
  Prefill company name/billing email from saved enquiry, use existing defaults;
  preserve staff-only contact/brief. Return `{organization_id,status:"converted"}`.
  Save company+conversion atomically under the enquiry lock; identical owner
  choice replays and a different choice conflicts. Existing advertiser/unique
  membership rules apply. No login creation or inferred ownership by email.
- Share the existing current person/payee approval predicate between email step
  and continuation; a stale step hint has no authority. Continuation neither
  consumes nor extends capability. Defaults, `.env.example`, production Compose
  and both deployment env examples become 86400;
  setup/reset TTLs stay unchanged. URL generation happens only at email runtime,
  persisted payload remains access-row reference/hash. Preserve existing renewal
  behavior (prior unexpired capability remains valid); remove pasted-code copy
  and “request a new code” review wording. Verify full URL/body log redaction,
  exact expiry, terminal/invalidation races and stale step hints.

These refinements supersede the earlier draft's open DTO/conversion choices,
per-area four-measure promise and unconditional mixed-area-release assertion.

## Specialist corrections and controller delegation

(Superseded by D105 on 19 October: only the three-car area minimum remains.)
Privacy source review requires one shared transactional release decision across
HTTP, export, publication and download. Fine outputs use different event clocks,
so disjoint date windows do not prove disjoint contributors. Conservatively
withhold incomparable area detail in the relevant campaign/organization/global
history. Partial estimate coverage also withholds areas. Compose ready governed
recommendations first; an existing conflicting area reservation suppresses those
optional targets, preserving usable totals. Corruption/ROI errors remain fatal.

(The daily identity below is superseded by D104: only the total budget is evaluated.)
Money source review requires a persisted confirmed-funding fingerprint independent
of daily clock/basis, daily decision identity with Nigeria date, and decision
identity that distinguishes newly pause-eligible scheduled work. Sweep savepoints
isolate incomplete drafts. Exact percentage thresholds use four decimals so a
valid one-cent budget does not collapse the warning/urgent/pause ordering.

The controller explicitly delegates obsolete external budget-policy cleanup
under D92 / REQ-190: its specific progress-register row/blocker entries, pilot
evaluator/tests and current gate references. All other gates/package statuses and
controller pointers stay unchanged. Seven policy/ratio settings and their
forwarders/documentation are removed. Historical dated delivery evidence remains
historical; it is not a current prerequisite or compatibility mechanism.

## Operational behavior

`sweep_scheduled_reports` discovers bounded pages with a durable campaign cursor,
then retries due `report_schedules` independently. State `complete` means the run
and issuance are durably queued; artifact readiness remains the issuance's state.
Failures retain attempts, next retry time and a safe error code. Restarting the
worker preserves obligations and stable IDs; do not delete rows to retry. Staff
can use the authorized rerun command for a fresh analysis, without entering UUIDs
or UTC periods. Cancellation uses the existing immutable cutoff. Report automation
is a migrated disabled reserved identity, absent from human-user choices.

Staff enquiry conversion uses the saved company/email and optional existing owner
UUID. Identical owner choice replays the organization; changing it after conversion
returns a conflict. No email service is needed for public submission persistence.

The continuation endpoint returns only current step/expiry. Worker B must consume
and clear the fragment before other requests, retain the capability in the existing
page session, and send it only in the existing JSON bodies. A new link does not
revoke an earlier unexpired capability; expiry/terminal revocation still wins.

## Verification ledger

Plan review PASS: `mcp:bb4b731b-918c-48c0-abce-2a31de70cef3`, reported
gpt-6.1-sol/high, codex-fresh-20261012. Specialist reviews (each reported
Opus 5.5): security PASS; money PASS, re-reviewed PASS after the daily/blocked
clean-up; privacy FIX then PASS, with D105 briefed as an owner decision. The
consolidated review (Opus 5.5) found 9 items, all corrected (item 8 above). All
checks ran 19–20 October in one 1200 MB container, one test file at a time. No
push is claimed; full CI is the merge gate.

| Criterion | Verdict | Evidence |
| --- | --- | --- |
| W1 coarse results (D105) | PASS | performance 12, reporting_flow 1 (every output answers after area release), disclosure_control 31, zone_insights 2, exposure_scores 6, report_issuances 54, advertiser_reports 4, measurement_runs 20, report_rendering 20, heatmaps 10, development_preview 2. |
| W2 automated reporting | PASS | req180_batch2_scheduling 11, report_issuances 54. |
| W3 fixed budgets (D103/D104) | PASS | budget_enforcement_w2_01e 11, budget_enforcement 4, req180_batch2_budget 6, budget_used 4, money_adapter_boundaries 12, campaign_resume 11, billing_api 5, notifications 1, schema_budget_notifications_recovery 1, req180_batch2_schema 1 (0107↔head round trip). |
| W4 enquiries | PASS | campaign_enquiries, req180_batch2_enquiries, DSR registry 3. |
| W5 continuation (D8) | PASS | req180_batch2_continuation 4, applicant_state 3, driver_applications, onboarding query plans. |
| W6 integration/contracts | PASS | openapi.json, the snapshot and schema.d.ts regenerated; openapi 4; architecture_current_state 4; R14-B native fixtures 4 files / 129 tests; seed_smoke 2; seed_demo 40 of 41 in one run, and the 41st passed on its own (see below); ruff and `git diff --check` clean. |
| W7 reviews | PASS | As above. |
| W8 job artwork | PASS | req180_batch2_artwork 34. |
| W9 cancellation support | PASS | cancellation_support, staff_cancel 10, campaign_cancellations 7, complaints, complaints_service, billing_corrections 15, billing_concurrency 3, pkg03 11, ingestion_locks 4. |

Seed clock fixes: the primary demo driver's licence and car insurance expiries
are now recorded as Nigeria dates. Before, a seed run between 23:00 and 24:00 UTC failed
`DOCUMENT_EXPIRY_INVALID`. The idempotency test fails only if its two seeds
cross UTC midnight, because the second seed adds the new day's rolling trips;
that test was rerun on its own. `test_w403b_synthetic_path` stops at its
Playwright step, which is not installed in the offline container; CI runs it.
## Worker B contracts (implemented and verified)

All paths below are under `/api/v1`. Existing auth/error envelope applies.

- `POST /admin/campaigns/{campaign_id}/cancel`: active admin only; JSON
  `{reason:string,client_request_id:UUID,complaint_id?:UUID|null}` with extras
  denied. Reason is trimmed, nonempty and at most 1000 characters. Returns 201
  existing `CampaignCancellationRead`: `{id,campaign_id,organization_id,
  requested_by_user_id,client_request_id,reason,prior_status,cutoff_at,
  commercial_terms_id,production_start_id,funding_authorized_at,
  refund_eligibility_ends_at,disposition,refundable_amount,currency,
  released_liability_amount,cancelled_assignment_count,created_at}`; monetary
  values are decimal strings, timestamps ISO, authority IDs/times may be null.
  It uses the existing whole-campaign cutoff/settlement engine, which is now
  staff-only, and identifies the staff actor. Optional complaint must be that organization's same-campaign
  advertiser cancellation request; new invalid links return 404
  `CAMPAIGN_CANCELLATION_REQUEST_NOT_FOUND`. Successful linked cancellation adds
  `The campaign has been cancelled.` through the ordinary staff reply path
  atomically, leaving it answered. Exact retries return the same result and no
  duplicate effects; changed actor/reason/request/link returns 409
  `CAMPAIGN_CANCELLATION_CONFLICT` before complaint validation. Missing campaign
  returns 404 `CAMPAIGN_NOT_FOUND`; existing ineligible-state/economic errors
  remain. Client `cancelCampaignAsStaff(api,campaignId,{reason,clientRequestId,
  complaintId?})` maps to snake_case. Staff assignment cancel is unchanged.

- `POST /advertiser/complaints`: existing active advertiser organization members,
  including viewers, submit `{category:"campaign_cancellation",message:string,
  reference_type:"campaign",reference_id:UUID,client_request_id:UUID}`. The reason
  is trimmed, nonempty and at most 2000 characters; it becomes the first message.
  Returns 200 existing `ComplaintDetailRead`:
  `{id,category,status,reference_type,reference_label,created_at,last_message_at,
  waiting_on_you,messages:[{sender,body,sent_at}]}`. A fresh request is `open`,
  `waiting_on_you:false`, with sender `you`. Advertiser responses intentionally
  omit `reference_id`; they show the campaign's plain reference label. Its list
  remains `{items:ComplaintSummaryRead[]}`, the same fields without `messages`.
  Staff list remains `{items,total,limit,offset}` and detail retains existing
  identity, organization, assignment, revision and message fields, including
  `category` and `reference_id`; there is no new projection field. Missing or
  wrong-kind campaign reference returns 422 `COMPLAINT_CAMPAIGN_REQUIRED`;
  incomplete reference pairs retain 422 `COMPLAINT_REFERENCE_INCOMPLETE`;
  unknown/foreign campaigns both return 404 `COMPLAINT_REFERENCE_NOT_FOUND`.
  Driver use returns 422 `COMPLAINT_CATEGORY_NOT_ALLOWED`. Existing exact retries
  return the same thread; changed valid payload under that raiser's request UUID
  returns 409 `COMPLAINT_REPLAY_CONFLICT`. No campaign state or money changes.
  Remove the old advertiser `POST /advertiser/campaigns/{campaign_id}/cancel`
  screen/BFF action; it returns 404. Existing staff assignment cancellation stays
  available; use the new staff whole-campaign endpoint above to stop the campaign.

- `POST /driver/campaign-assignments/{assignment_id}/artwork/download`: assigned
  active-account driver, no body, 200 `{url:string,expires_in_seconds:int}` with
  `Cache-Control: private, no-store`. The live offered/accepted/active job rules
  and frozen/current approval/file checks above apply. Generic absent/unowned/
  inactive/ended job: 404 `ASSIGNMENT_ARTWORK_NOT_FOUND`; unavailable changed
  artwork authority: 409 `ASSIGNMENT_ARTWORK_UNAVAILABLE`; deadline crossed during
  verification/signing: 404 `FILE_ACCESS_EXPIRED`. Existing clean-file/object/
  unavailable-storage errors remain. Use the offer's existing frozen MIME/type
  to choose image/video/PDF presentation, request URLs on demand and do not
  persist them. No extra advertiser/campaign facts are returned.

- `GET /advertiser/campaigns/{campaign_id}/report` replaces its former rich
  response with `{campaign_id,start_at,end_at,totals,areas,completeness,uncertainty,
  measurement_run_id,report_issuance_id,report_status}`. The last three fields are
  nullable report handles for polling/download; do not display internal IDs.
  Times are nullable ISO timestamps. Totals are
  `{distance_m:string,trip_count:int,driving_days:int,estimated_views:string|null}`.
  Areas are `{area_id:UUID,name:string,trip_count:int,
  modelled_potential_contacts:string|null}[]`; an empty array means no safe area
  detail. Preserve uncertainty copy. Optional exact `start_at,end_at` query selects
  a frozen period; without it the latest run or pre-first-run coarse live totals
  are returned. Explicit unavailable periods return 409 `CAMPAIGN_REPORT_PENDING`.
  Existing tenant/advertiser role authority still applies.
- `POST /admin/campaigns/{campaign_id}/reports/re-run`: active admin, no body,
  202 `ReportIssuanceRead` (`id,measurement_run_id,campaign_id,version,reissue_of_id,
  status,synthetic,schema_version,renderer_version,worker_attempts,error_code,
  artifacts,created_at,ready_at`). Existing issuance poll/download routes stay.
  No completed interval returns 409 `REPORT_PERIOD_UNAVAILABLE`. A click creates
  a fresh run; show pending state and prevent accidental repeated clicks.
- `GET /admin/campaign-enquiries`: active admin, `status=new|converted` (default
  new), optional `q` up to 128 characters, `limit=1..100` (default 50),
  `offset>=0` (default 0). Returns `{items,total,limit,offset}`. Each item is
  `{id,company,contact_name,email,phone,brief,created_at,status,organization_id,
  converted_at}`; organization and converted time are nullable. Search matches
  company/contact/email as literal case-insensitive substrings. Detail is
  `GET /admin/campaign-enquiries/{enquiry_id}` with the same item or 404
  `ENQUIRY_NOT_FOUND`.
- `POST /admin/campaign-enquiries/{enquiry_id}/create-advertiser`: active admin,
  JSON `{owner_user_id?:UUID|null}`, extras denied. Returns 200
  `{organization_id:UUID,status:"converted"}`. Saved company/email supply the
  company defaults; no password/login fields. Same owner replays; a changed owner
  returns 409 `ENQUIRY_CONVERSION_CONFLICT`. Existing owner/account constraints
  can also deny conversion. Public POST keeps 200 `{status:"submitted"}`.
- `POST /auth/driver-onboarding/continue`: public registration feature enabled,
  JSON `{application_access_token:string}`, returns 200
  `{step:"details"|"car",state,changes_reason:string|null,expires_at:ISOtimestamp}`.
  `state` is one of `details_needed`, `details_in_review`,
  `details_changes_needed`, `car_needed`, `car_in_review`,
  `car_changes_needed` (REQ-195). `changes_reason` is a plain applicant
  sentence, only for the `*_changes_needed` states (for example "Your ID details
  do not match. Please check them."); show it as given. Invalid, revoked, expired
  or terminal capability returns generic 404 `ONBOARDING_ACCESS_INVALID`. Final
  approval also ends the link, so the expired/used-link copy must tell an
  approved applicant to check their email for Terrax's account-setup link.
  Email href is `/apply?step=details|car#application_access_token=...`.
- `GET /advertiser/complaints?campaign_id=UUID` (REQ-194): the existing list
  `{items:ComplaintSummaryRead[]}`, filtered to that campaign before the list
  limit. Unknown or foreign campaigns return an empty list. A cancellation is
  **pending** when an item has `category:"campaign_cancellation"` and status
  `open` or `answered`, and the campaign is neither `cancelled` nor `completed`.
  Client: `readCampaignCancellationRequests(api,campaignId)`.
- `budget_used` (D103 / REQ-193) on every advertiser campaign response (list
  items, detail, create, PATCH, submit):
  `{amount:string,budget_amount:string|null,currency,basis:"funding"|"invoice",as_of}`.
  `amount` is the booked total (confirmed funding before production, the invoice
  with corrections after); `budget_amount` is the total budget. Show it as
  "Booked: ₦1,128,750 of your ₦1,128,750 budget" for a normal campaign, using the
  campaign currency; never add amounts across campaigns or currencies, and show
  no daily figure. Acceptance raises the budget to at least the agreed price, so
  a normal campaign reads at most 100% and warnings appear only for extra
  charges (D104). Types: `BudgetUsed`, `ApplicationContinuation`.
- Removed `POST /admin/campaigns/{campaign_id}/budget-policy-evaluation`.
  Remove its staff panel/action. Normal commercial summary and reasoned
  `budget-policy-resume` command remain; percentages are automatic defaults.
- Budget evaluation reads no longer carry `external_gate`, and the
  `blocked_external_policy` state no longer exists. Remove the "Not set up yet"
  label for it in the commercial panel and the `EXT-BUDGET-POLICY` copy on the
  staff billing page.

Typed wrappers live in `frontend/src/lib/api/audit-batch2.ts`:
`readCampaignPerformance`, `rerunCampaignReport`, `readStaffEnquiries`,
`readStaffEnquiry`, `createAdvertiserFromEnquiry`, `continueDriverApplication`,
`readDriverJobArtwork`, `askTerraxToCancelCampaign`,
`readCampaignCancellationRequests`, `cancelCampaignAsStaff`.
Worker B owns the results/map adaptations to the new coarse response, staff
rerun and New enquiries screens/BFF actions, removal of budget-policy controls,
Apply fragment consumption/current-step continuation, and the job artwork
preview/BFF action, plus the cancellation-request form/category and replacement
of the obsolete advertiser cancel BFF/action. Keep a request UUID for retries of
one submission. No screens were edited.

Controller-delegated files: `docs/progress.md`,
`scripts/evaluate_pilot_gates.py`, `tests/test_pilot_gate_evaluator.py`,
`docs/pkg-08-w4-03b-synthetic-journey.md`, `docs/product-requirements.md`,
`docs/pro-review-register.md`, `docs/pilot-operations/README.md`,
`docs/handover/external-and-deferred-risks.md`.
Knob forwarders/docs: `.env.example`, `docker-compose.yml`,
`docker-compose.production.yml`, `production.env.example`, `staging.env.example`,
`frontend/e2e/support/docker-compose.r59.yml`, `docs/deployment-templates.md`,
and the current budget wording in `docs/demo-data.md`/`docs/client-decisions.md`.

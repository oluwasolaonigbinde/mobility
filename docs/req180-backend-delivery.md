# REQ-180 batch 1 — backend delivery and Worker B handoff

Owner-authorized scope: audit §7 Worker A, including reinstated B2/D9 (owner amendment). Work stays on
`fix/req180-batch1-backend`; local commits are authorized, pushes are prohibited.
REQ-180 already records the audit work; REQ-187/D89 records the reinstated bank
decision. Worker A owns only those amended records; the controller owns closure.
No package queue or production/live-use claim changes.

## Contract and implementation plan

1. B1: enqueue one-file scanning after successful upload confirmation commits,
   covering applicant, artwork, driver and staff installation uploads. Reuse
   `scan_stored_file`, its locking/retry/quarantine predicates and scanner adapter;
   retain the sweep. Queue failure must not undo confirmation or authorize use.
   Add optional progress callbacks/Checking file wording in owned upload helpers;
   screens remain Worker B's work.
2. B4: reproduce direct and empty JSON/chunked proxy framing before changing the
   boundary. Accept exactly zero actual bytes for the existing bodyless commands,
   irrespective of framing/type; reject nonempty/unreadable streams. Preserve
   Origin/Fetch Metadata checks and JSON requirements on other commands.
3. B5: transactional, event-deduplicated in-app/email notices for identity/bank
   approved/rejected and car approved/rejected, plus offered-job email. Use
   identifier-only persisted payloads and resolve authorized context at delivery.
   Never infer account activation or alter approval/eligibility/bank authority.
4. B6: enqueue pending transactional email IDs after commit, reusing worker claims,
   idempotency, recipient reauthorization, retries and sweep catch-up. No inline
   provider calls, precommit delivery, or fire-and-forget API background tasks.
   A small shared enqueue port/session commit integration may be used so all
   existing code/link and business notification producers receive this behavior.
5. U24–26/B21: plain text and escaped clickable HTML links; real Apply-step links
   with the existing separate code and 30-minute expiry (D8 token continuation is
   deferred). Campaign messages resolve name/internal destination from existing
   recipient-scoped context. Configure account setup URL in compose/.env.example;
   never email a bare setup token if URL is absent. No new expiry/client policy.
6. U7/B20: plain wording for the audit's surfaced backend messages; apply D89 trimmed 1–512-character reference validation without entropy syntax. Require nonblank service_city for new public
   applications, and return a distinct missing-service-area offer error with
   actionable wording. Do not invent a new supported-city policy.
7. Speed: add an active-admin badge summary using precisely the existing queue
   source predicates, and an own-driver current-job summary with all assignment
   status counts/current assignment, replacing repeated reads. Add bounded
   grouped list-row counts for advertiser company/campaign/retargeting fan-out
   where applicable, without tenant leaks or treating failed reads as zero.
   Add typed API-client functions; Worker B owns all screen wiring.
8. Move all three architecture §9 baselines together, rerun R14-B fixtures and
   focused changed-file checks. Amend architecture/decision/operational records
   for the actual changed design; controller handles its owned product records.

Non-goals: D8 capability/expiry redesign, other audit batches, screen edits,
provider/network account calls, deployment, branch/worktree/master changes, push,
full local backend suite, coverage-policy changes and launch-gate closure.

## Verification gates

- V1: confirmation queues only committed authorized file IDs; clean, infected,
  retryable failure, concurrent/replayed scans and queue outage preserve safety.
- V2: direct/proxy empty requests pass; actual bodies/unreadable streams fail;
  hostile origins and ordinary mutation media checks remain enforced.
- V3: all four review outcomes and job offers create exact deduplicated notices;
  rejection/context content is recipient-scoped, stale authority is suppressed,
  delivery escapes user-controlled strings and never exposes raw setup tokens.
- V4: email/scan jobs run promptly without sweeps; rollback and broker outage
  preserve durable catch-up; existing delivery claims/retry rules still hold.
- V5: readable emails have valid application/reset/setup/campaign links and
  expected expiry text; local compose and env template supply setup URL.
- V6: city missing/blank is refused for new applications; missing service area
  has a distinct offer code; U7 wording changes preserve D89 exact-bank-version verification authority.
- V7: badge counts match existing filtered lists, own-driver status totals match
  lists, row counts are correct across paging and tenant boundaries; wrong roles
  are refused. API client functions and all baselines agree.
- V8: only touched test files run locally, plus focused lint/typecheck/contracts,
  R14-B fixtures and provider-free live simulation in one owned Docker container
  using own database on cv-req139; container/database/image removed at completion.
- V9: independent plan review, implemented security review (B1/B4 plus sensitive
  notification flows), and consolidated minimal-change-review all PASS before
  local final commit; no push or full CI is authorized here.

Review risks: nested transaction/rollback notification enqueue, Redis loss,
scan replay/backoff, immutable notice/event identities, invitation versus active
recipient states, capability/token leakage, grouped-count query scope and exact
existing queue predicates. Verification evidence and final endpoint details are
recorded below after implementation stabilizes.

## Plan-review corrections

The owner's explicit reviewer configuration (gpt-6.1-sol high, priority,
codex-fresh-20261012, separate T3 thread) overrides the skill's medium-effort
default. Plan review round 1 FIX identified the following valid refinements:

- Use an `AsyncSession` subclass only at the API and worker session factories.
  Services record typed file/email IDs in session.info; overridden outer commit
  flushes and filters those IDs against rows still present inside the transaction,
  commits, clears pending state, then awaits one bounded fail-open enqueue batch.
  Savepoint commits never invoke the outer commit override. Outer rollback clears
  state; inner rollback filtering retains earlier valid IDs. No generic callbacks
  or asynchronous event-listener tasks. Test nested rollback/commit, dedupe
  recovery, session reuse, API/worker factory adoption and broker outage.
- The shared scan service checks next_scan_at under its row lock, including
  immediate jobs; deterministic scan/email jobs use keep_result=0. Test early
  error replay, concurrent lock exclusion and due sweep recovery.
- Four review notices use immutable decision IDs and identifier-only payloads.
  Invitees (current application owner) and active drivers are eligible; suspended
  users are not. Delivery resolves the exact current submission/last decision,
  suppresses stale decisions and uses an allowlisted plain reason. ID approval
  opens /apply?step=car, ID rejection /apply?step=details, car outcomes
  /apply?step=car; active-driver renewals open /driver/profile. Invited applicants
  are told to request a new code on Apply when needed, using the unchanged
  email/code renewal flow. No token in Apply URLs, TTL change or automatic code
  consumption. Job-offer email requires an active driver and owned assignment,
  names its campaign and opens the existing driver assignments destination.
- GET /api/v1/admin/badge-summary: nonnegative integer fields total, drivers,
  campaigns, trips, money, support and source_counts keyed by the existing 17
  work-queue source IDs. All predicates match work-queue.ts, including grouped
  unresolved trips and payout needs_attention, without failed-to-zero fallback.
- GET /api/v1/driver/current-job: counts for all eight assignment statuses,
  assignment (the same current active assignment as the existing /active read,
  nullable) and photo_status using that read's existing semantics. No missing
  profile becomes another driver's record. Counts include zero statuses and the
  same expired-offer treatment as current list reads.
- Existing admin organization list rows gain member_count and
  live_campaign_count (active or paused), plus operational/billing contact fields
  already available to admin company reads. Existing admin/advertiser campaign
  list rows gain assignment_count and target_zone_count. Existing retargeting
  source list rows gain link_count (nonremoved links). Aggregate only page IDs
  using grouped queries with a constant query count as the page grows; retain
  each list's authorization and total/pagination. Financial outstanding amounts
  stay on current invoice authority; this is explicitly counts work.
- Owned client module exports readAdminBadgeSummary, readDriverCurrentJob,
  readAdminAdvertiserOrganizations, readAdminCampaigns, readAdvertiserCampaigns
  and readAdvertiserRetargetingSources using the existing ApiClient. No screen
  or driver loader changes. Verify exact predicates, all statuses, grouped-trip
  counts, payout attention, role/tenant isolation and paging/query-count bounds.

## Owner amendment — D9 (18 October)

B2 is reinstated under REQ-187/D89. The plan reviewer independently PASSED this
amendment (same gpt-6.1-sol high reviewer). Normalize by trimming, accept 1–512
characters with spaces/Unicode, refuse control characters and retain only SHA-256.
Schema and Worker B form contract agree on required/min 1/max 512. Preserve bank
version binding, active-admin review/audit, applicant-capture separation and first
manual payout. Add money/eligibility specialist PASS as V9 gate. Batch 2 D1–D4/D8
is separately authorized only after Batch 1 reviews and commit; it has its own
contract. This amendment supersedes the earlier B2 exclusion throughout.

## Worker B integration contract

Use `frontend/src/lib/api/navigation.ts` with the existing authenticated
`ApiClient`. These functions return the usual openapi-fetch response; failures
propagate through existing middleware and must not become zero badges.

- `readAdminBadgeSummary(api)` → GET `/api/v1/admin/badge-summary`, active admin,
  no query/body. HTTP 200 contains required nonnegative integer `total`,
  `drivers`, `campaigns`, `trips`, `money`, `support`, and `source_counts` with
  `applications,cars,jobs,trips,late,campaigns,artwork,photos,checks,batches,alerts,
  corrections,complaints,contacts,disputes,changes,paused`. Area values sum their
  existing work-queue sources; `total` sums all 17. Replace badge fan-out with
  this one read; retain the destination-specific queue reads when opened.
- `readDriverCurrentJob(api)` → GET `/api/v1/driver/current-job`, active driver,
  no query/body. HTTP 200: `assignment: CampaignAssignmentRead | null`,
  `photo_status: ready | display_required | installation_required | unavailable`,
  `counts` containing all eight integer keys `offered,accepted,active,declined,
  expired,deactivated,cancelled,completed`, including zeros. Current assignment
  and photo status use existing `/active` authority. Missing driver profile
  remains 404; wrong role is 403. Replace the seven summary reads in the driver
  loader with this read.
- GET `/api/v1/admin/advertiser-organizations` retains its query/pagination and
  `{items,total,limit,offset}` envelope. Each item adds `member_count` (all
  memberships), `live_campaign_count` (active/paused), nullable
  `billing_contact_name`, `operational_contact_name`, `operational_contact_email`.
  Client: `readAdminAdvertiserOrganizations(api, query?)`.
- GET `/api/v1/admin/campaigns` and `/api/v1/advertiser/campaigns` retain current
  authorization/query/pagination and `{items,total,limit,offset}`. Each row adds
  `assignment_count` (all statuses), `target_zone_count` (target zones only).
  Clients: `readAdminCampaigns(api, query?)`, `readAdvertiserCampaigns(api, query?)`.
- GET `/api/v1/admin/retargeting-sources` and
  `/api/v1/advertiser/retargeting-sources` retain `{items,total}` and authorization;
  each row adds `link_count` excluding removed links. Advertiser client:
  `readAdvertiserRetargetingSources(api)`. Use row counts instead of per-row calls.
- POST `/api/v1/auth/register-driver` now requires nonblank `service_city`
  (trimmed, maximum 128), alongside existing fields. Missing/blank is 422 using
  the existing validation envelope. Worker B must make the Apply city field and
  action schema required; the unmodified `frontend/src/app/apply/actions.ts:81`
  currently fails full TypeScript checking because its city is optional.
- Offering a driver with no service city returns HTTP 409,
  `error.code = DRIVER_SERVICE_AREA_REQUIRED`, message
  `Add the driver's city before sending a job offer`. Show this actionable error.
- D89 bank verification: existing command/body shape, trimmed required
  `verification_reference` of 1–512 characters, spaces/Unicode accepted, controls
  rejected. Worker B must replace the form's 32-character/high-entropy constraint
  and wording with a required bank test-transfer reference (maximum 512).
- Upload helper callbacks expose `Checking file…`: Apply progress accepts
  `onStatus`, installation uploader options accept `onStatus`, and creative
  phases use exported `CREATIVE_UPLOAD_PHASE_LABELS`. Wire these into the owned
  screens; helper polling/retry/scan safety remains unchanged.

No screens or components were edited. Review emails open Apply's existing step
query or `/driver/profile`; job offers open `/driver/assignments?assignment_id=…`.
D8's secure continuation redesign belongs to Batch 2.

## Verification receipt — 18 October 2026

All execution used one owned container at a time, capped at 1200 MB / one CPU,
with an isolated database. The existing actual network is `cv-req139-probe`;
`cv-req139-edge` supplied package-download access. No host port was published,
no provider was called, and no shared container was stopped or removed by this
worker. Docker Desktop recovery was performed by the orchestrator.

| Criterion | Verdict and evidence |
| --- | --- |
| V1 | PASS. `test_req180_backend.py` covers successful committed confirmation, outer/savepoint rollback, replay, row-lock exclusion, early retry backoff and due recovery; `test_file_scanning.py` covers clean/infected/error/quarantine behavior and missing queued IDs. Real API uploads of artwork, installation and applicant KYC became clean; an antivirus test file became infected. Private download was refused before scanning. |
| V2 | PASS. Before the boundary correction, 10 JSON/chunked empty cases failed while direct empty cases passed. Final boundary file has 23 passing tests including unreadable/locked bodies, nonempty data, origin protection and unchanged JSON routes. A raw TCP HTTP simulation passed 20 cases across all five command patterns: direct CL0, JSON CL0 and zero-chunked accepted; actual `{}` refused with 415. |
| V3 | PASS. Six real decision cases cover four outcomes plus independently expired ID/car authority. Exact decision retries leave one notice per channel; email resolves the owned recipient and safe copy. Rejected ID replacement/car purge disappear before counting/paging; hidden rows remain unread after read-all; valid individual reads are idempotent. Active ID/car renewal projections and actual delivery use profile wording. Job-offer delivery tests recipient ownership and duplicate delivery suppression. HTML escaping and no-bare-setup-token checks pass. |
| V4 | PASS. Real ASGI API → private local MinIO → committed confirmation → Redis/arq → existing shared ClamAV ran with no sweep: three clean files, one infected file and one locally captured onboarding email; five jobs completed in 1.96 seconds. Existing email claim/retry regressions pass. The broker-timeout test preserves pending durable work; savepoint/rollback tests prove no uncommitted ID escapes. |
| V5 | PASS. Email delivery/template tests cover code/reset/setup behavior, safe links, escaping and absent setup URL. Compose and `.env.example` supply application origin, password-reset and account-setup links. Real local-sink email contains the clickable Apply link. D8's capability replacement remains deferred to Batch 2. |
| V6 | PASS. Required/missing/blank/trimmed city schema cases pass; existing application API fixtures pass with required city. Real offer construction without city returns `DRIVER_SERVICE_AREA_REQUIRED`/409 and actionable wording. Bank tests accept short/spaced/Unicode/private-use/max512 references and reject empty/control/oversize; short `TX 1` passes actual verification and ID review APIs while their existing authority checks remain. |
| V7 | PASS. Own-driver counts equal all eight filtered lists; current assignment is the owned active assignment. Badge checks include grouped unresolved trips and payout attention equality. Campaign/organization counts are tenant/page scoped; campaign grouped reads remain two SELECTs for one or eight rows. Source counts exclude removed links and another tenant's sources. Role/zero-state tests pass. All three §9 baselines regenerate without drift. |
| V8 | PASS for owned scope, with the explicit Worker B integration limitation below. Focused results and cleanup are recorded below. No full local backend suite or full CI was run. |
| V9 | PASS. Independent plan, money/eligibility, security and final consolidated minimal-change reviews all PASS. Each valid FIX was corrected and reassessed before local commit. |

Completed serial backend invocations (overlapping tests are not unique totals):

- **75 PASS**, 637.57 seconds: `test_req180_backend`,
  `test_req180_review_notifications`, `test_req180_navigation`,
  `test_file_scanning`, `test_email_delivery`, `test_driver_applications`,
  `test_payees_api`.
- **36 PASS**, 267.90 seconds: expanded review matrix; missing-city offer;
  job-offer email; payees API; grouped worklist; payout operations API;
  retargeting-link lifecycle/counts; three public-applicant account controls;
  two person/payee enumeration/access cases; complete vehicle approval;
  application-history serialization; four R32 terminal/concurrency entry points.
  Only touched files supplied these selected cases.
- **10 PASS**, 62.60 seconds, after the final active-renewal correction:
  six review matrix cases plus four `test_openapi.py` cases.

Frontend verification after the baseline update: **183 PASS in nine files**:
mutation-boundary (23), onboarding-upload (17), creative-upload (5),
installation-evidence-upload (6), ping-queue (28), trip-evidence (3),
capability-contract (38), driver pwa-contract (5), trip-tracker (58).
The unchanged native queue/tracker/capability fixtures were rerun as expressly
required by §9/R14-B. Existing React act warnings did not fail tests.

Focused Ruff, ESLint, Prettier and `git diff --check` pass. Both JSON baselines
match runtime OpenAPI; regenerated `schema.d.ts` is byte-identical. Full frontend
TypeScript checking completed with one error: the untouched Apply action's
optional city at `frontend/src/app/apply/actions.ts:81`. No owned API-client error
was reported. Worker B has the required-city screen/action handoff above; this
receipt does not claim the combined frontend typecheck is green.

Independent reviews use the requested gpt-6.1-sol/high configuration on
`codex-fresh-20261012`, with priority requested in the launch settings:

- Plan and D9 amendment: PASS, thread
  `mcp:c4b9476c-495b-4cc6-995c-7a05efc64c32`.
- Money/eligibility: final PASS, thread
  `mcp:1828df42-ae38-4d00-af7b-e988c3e20ef5`; private-use Unicode FIX corrected.
- Security: final PASS, thread
  `mcp:9922c947-9f2c-4fb4-8358-403f3eeffac3`; expiry and stale-feed FIXes corrected.
- Consolidated minimal-change review: thread
  `mcp:312444eb-8b22-41ed-9dca-ba5fc86a14cc`; active-renewal copy FIX corrected;
  final integrated source and evidence reassessment PASS.

Cleanup completed before Docker handoff: `cv-req180a` removed,
`cardvert_req180a` dropped, `cardvert-req180a:local` tag removed. The reused base
image remains owned by the existing environment. Private disposable local
harness files were removed. No push, merge, deployment or request closure is
claimed; REQ-187 remains IN PROGRESS until the controller merges it.

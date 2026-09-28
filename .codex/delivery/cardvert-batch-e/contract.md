# Batch E contract — in-app complaints with a Customer Service inbox

Base: `origin/master` 4f318e3 (Batches A, B, D). Branch `batch-e`. Parallel Batch C
(automatic payouts) owns migration 0093 and payout/disbursement files.
Authority: D39(d) (complaints raised in the app, handled by Customer Service);
D38(a) copy (Terrax Media for person actions, Cardvert for automatic ones,
"Nigeria time (WAT)"); D38(c) no hashes/IDs on driver or advertiser screens;
D38(e) departments are work-queue sections, not roles; §20 notification rules
(advertiser = in-app + preference-governed email; driver = in-app; no inline
provider calls); client-answers register ("Customer Service: driver contact,
payout issues and complaints").

## 1. Outcome
A driver or advertiser raises a complaint in the app, with a category and an
optional reference to one of their own campaigns, trips or payouts, and follows
a conversation with Customer Service. Terrax Media staff (any active admin —
no new role) answer from a Customer Service inbox, set status and assignment,
and see open complaints counted in "Waiting for you" → Customer Service.
Every mutation is audited; complaints and replies create notifications.

## 2. Assumptions (stated, not invented client values)
- A1. Category list is a neutral, clearly labelled default (open client question):
  `pay_or_payout` "Pay or payouts", `trip_or_tracking` "Trips and tracking",
  `campaign_or_job` "A campaign or job", `billing_or_invoice` "Billing or invoices",
  `account` "My account", `other` "Something else". Drivers may use all but
  `billing_or_invoice`; advertisers may use all but `pay_or_payout` and
  `trip_or_tracking`. Validated in code (Pydantic enum + service party check);
  the DB stores a bounded string (length/format check only) so a client change
  is a code change, not a migration.
- A2. No response-time target is shown or enforced (client decision; open question).
- A3. Staff = any active admin (D38(e)). Assignment picks an active admin.
- A4. Advertiser complaints belong to the advertiser organization: every active
  member of that organization can read and follow up (like campaigns); the
  raising person is recorded. Driver complaints belong to the driver profile.
- A5. Driver "payout" reference = the driver's own earnings entry
  (`earnings_ledger_entries`, the driver-visible payout unit; each payout line
  maps 1:1 to one). No payout/disbursement file is modified.
- A6. Email: advertisers get the existing preference-governed transactional email
  for staff replies and resolution (static templates, identifiers only in payload).
  Drivers and staff get in-app only, because §20/D18 gives drivers no automated
  email and admins no business email; the dispatcher (`email_delivery.py`) is not
  changed. Driver manual-contact tasks are not created (open question).

## 3. Scope
Backend
- Models `app/models/complaint.py`: `complaints` and `complaint_messages`.
  - `complaints`: id; `party` ('driver'|'advertiser'); `raised_by_user_id` FK users;
    `driver_profile_id` FK (driver party only) / `advertiser_organization_id` FK
    (advertiser party only) — exactly-one check per party; `category` varchar(32)
    (non-blank, lowercase-snake check); `reference_type` ('campaign'|'trip'|'payout'|NULL)
    with `campaign_id`/`trip_session_id`/`earnings_ledger_entry_id` nullable FKs and a
    check that exactly the matching column is set (none when NULL); `status`
    ('open'|'answered'|'resolved'); `assigned_to_user_id` FK users NULL;
    `revision` int ≥ 1 (bumped on every mutation; used in notification dedupe keys);
    `client_request_id` uuid, unique per (`raised_by_user_id`, `client_request_id`);
    `created_at`, `updated_at`, `last_message_at`, `resolved_at`, `resolved_by_user_id`
    with a check tying resolved fields to status 'resolved'. Indexes on status,
    party owner columns, assigned_to, last_message_at.
  - `complaint_messages`: id; `complaint_id` FK; `author_user_id` FK users;
    `author_side` ('complainant'|'staff'); `body` text 1..2000 trimmed-nonblank check;
    `client_request_id` uuid, unique per (`complaint_id`, `author_user_id`,
    `client_request_id`); `created_at`. Append-only (ORM before_update/before_delete
    raise). The first message is the complaint text.
- Migration `alembic/versions/0094_customer_service_complaints.py`,
  `down_revision = "0092_payout_v4_daily_rate"` (re-pointed to C's 0093 at
  integration). Downgrade drops both tables but refuses while any complaint row
  exists (same pattern as 0092). Head tests updated to 0094.
- Service `app/services/complaints.py`:
  - raise (driver/advertiser): resolve owner (driver profile / active membership,
    else 404 as existing codes), validate category for party (422
    `COMPLAINT_CATEGORY_NOT_ALLOWED`), resolve reference under ownership: advertiser
    campaign must be in their org; driver campaign must have one of the driver's
    campaign assignments; trip must be the driver's trip session; payout must be the
    driver's earnings entry; anything else (unknown, foreign, type not allowed for
    party e.g. advertiser trip/payout → 422 at schema? no: advertiser may only send
    'campaign'; other types 422 `COMPLAINT_REFERENCE_NOT_ALLOWED`) → unknown/foreign
    id is 404 `COMPLAINT_REFERENCE_NOT_FOUND` with the same body whether unknown or
    foreign. Exact retry (same user + client_request_id + identical facts) returns
    the original (200, no second audit/notification); changed reuse → 409
    `COMPLAINT_REPLAY_CONFLICT`. Writes complaint + first message + audit
    `{party}.complaint.created` + in-app notice `complaint_received` to every active
    admin (dedupe `complaint:received:v1:{message_id}:in_app`).
  - follow-up by complainant: complaint must belong to the caller's scope (driver
    profile / active org) else 404 `COMPLAINT_NOT_FOUND`; appends a message; status
    becomes 'open' (reopens 'answered' or 'resolved'; resolved fields cleared);
    revision bump; audit `{party}.complaint.message_added` with before/after status;
    in-app `complaint_received` to the assignee if any, else every active admin.
    Idempotent by client_request_id.
  - staff reply: complaint row locked `FOR UPDATE`; appends staff message; status →
    'answered', or 'resolved' when `resolve=true`; audit `admin.complaint.replied`;
    notifies complainant side: driver → in-app `complaint_replied` (or
    `complaint_resolved`); advertiser → `create_advertiser_business_notifications`
    (in-app + preference-governed email) for the org. Idempotent by client_request_id.
  - staff update (PATCH): optional `status` ('open'|'resolved') and optional
    `assigned_to_user_id` (null clears; must be an active admin, else 422
    `COMPLAINT_ASSIGNEE_INVALID`); no-op when nothing changes (no audit, no notice);
    otherwise audit `admin.complaint.updated` with before/after status and assignee;
    resolving notifies the complainant (`complaint_resolved`); assigning notifies the
    new assignee in-app (`complaint_assigned`) unless it is the actor.
  - reads: complainant list/detail scoped to owner; staff list with filters
    (status, party, assigned_to_me) + total, detail with messages.
  - reference options: bounded (most recent 50 each) plain-label lists of the
    caller's own campaigns (advertiser: org campaigns by name; driver: campaigns
    they have an assignment on), trips (driver: "Trip on 3 Sep 2026, 08:15 WAT"
    label built from started_at) and payouts (driver: "₦2,678.94 · 3 Sep 2026"
    from amount/currency/occurred_at). Labels are computed server-side in WAT.
- Notification enum members only: `complaint_received`, `complaint_replied`,
  `complaint_resolved`, `complaint_assigned`. Feed renderer rows (plain copy:
  "Terrax Media replied to your complaint." / "Terrax Media marked your complaint
  as resolved." / "A driver or advertiser raised or followed up a complaint." /
  "A complaint was assigned to you."). Email templates for `complaint_replied`
  and `complaint_resolved` (static, no message body in email).
  Payloads carry identifiers only (`complaint_id`, and org id added by helper).
- Registries: `audit_subjects.py` SUBJECT_QUERIES `complaint` →
  `SELECT raised_by_user_id FROM complaints WHERE id=:entity_id`;
  `data_subject_inventory.py` a `customer_service_complaints` rule counting
  complaints raised by the subject plus messages authored by the subject.
- Routes `app/api/v1/complaints.py` (router registered in `router.py`):
  - `GET/POST /api/v1/driver/complaints`, `GET /api/v1/driver/complaints/reference-options`,
    `GET /api/v1/driver/complaints/{complaint_id}`, `POST /api/v1/driver/complaints/{complaint_id}/messages`
  - same five under `/api/v1/advertiser/complaints`
  - `GET /api/v1/admin/complaints`, `GET /api/v1/admin/complaints/{complaint_id}`,
    `POST /api/v1/admin/complaints/{complaint_id}/messages`, `PATCH /api/v1/admin/complaints/{complaint_id}`
  - Complainant DTOs contain no user IDs, author names or reference IDs: messages
    carry `from` ('you'|'terrax_media'), body, sent_at; the reference is a plain
    label. Complaint `id` is present (needed for the URL) but never rendered.
  - Staff DTOs include party, driver name / organization name, raiser name,
    reference type + id + label, assignee id + name, author names per message.
Frontend
- Driver `/driver/help` (list + "Raise a complaint" form; empty, error+retry,
  loading) and `/driver/help/[complaintId]` (thread, follow-up form); linked from
  the driver Profile page and Home (no sixth tab).
- Advertiser nav "Help" → `/advertiser/help` and `/advertiser/help/[complaintId]`.
- Staff nav "Customer Service" → `/admin/complaints` (filter by status, pagination,
  "Couldn't load" + retry, empty state) and `/admin/complaints/[complaintId]`
  (thread with names, reply form with "Mark as resolved", status and assignment form).
- "Waiting for you" Customer Service gains "Complaints to answer" →
  `/admin/complaints?status=open`, counted from `GET /api/v1/admin/complaints?status=open&limit=1`.
- Copy: plain sentences; staff shown as "Terrax Media"; times "… (Nigeria time, WAT)"
  via a complaint-local formatter with `timeZone: "Africa/Lagos"`; no IDs or hashes on
  driver/advertiser screens.
- Server actions validate with zod, map 401/403/404/409/422 to plain messages.
Docs
- progress.md "Batch E record" under the Batches A–F entry; architecture §20 new
  §20.4 [BUILT] + §30 row + changelog v1.101 + inventory regeneration; decisions
  unchanged (no product change beyond D39(d)).

## 4. Non-goals
No new staff role or permission; no response-time/SLA timer; no attachments; no
email/WhatsApp to drivers; no manual-contact tasks; no change to fraud disputes,
payouts, disbursement, email dispatcher, or Batch C files; no deletion/editing of
messages; no search across complaint text.

## 5. Acceptance criteria
- AC1 Driver and advertiser can raise a complaint with an allowed category and an
  optional own reference; the first message is stored; 201/200 response.
- AC2 Unknown or foreign reference → 404 `COMPLAINT_REFERENCE_NOT_FOUND`, identical
  for unknown vs another party's record, nothing written; disallowed reference type
  or category for the party → 422, nothing written.
- AC3 A complainant can list/read/follow up only their own (driver) or their org's
  (advertiser) complaints; another party's complaint id → 404 `COMPLAINT_NOT_FOUND`.
- AC4 Staff list (filters, total), detail, reply (with optional resolve), status change
  and assignment (active admin only) work; no-op PATCH writes nothing.
- AC5 Every mutating route writes exactly one audit event with the registered action in
  the same transaction; exact retries converge without a second audit/notification;
  changed reuse → 409.
- AC6 Notifications: new complaint/follow-up → staff in-app; staff reply/resolve →
  complainant in-app, plus preference-governed email rows for advertiser members;
  assignment → assignee in-app. Email renders from templates; payloads hold IDs only.
- AC7 Complainant responses expose no user IDs, names of staff, reference IDs or
  hashes; staff actions read "Terrax Media".
- AC8 "Waiting for you" Customer Service shows "Complaints to answer" with the open
  count, "Nothing waiting" at zero, "Couldn't check" on error.
- AC9 Screens: loading, empty, error-with-retry states; forms show pending, success
  and plain errors; times labelled Nigeria time (WAT).
- AC10 Migration 0094 upgrades/downgrades cleanly and refuses downgrade with rows;
  authorization inventory classifies all new routes; denial matrix and audit-route
  coverage pass; audit-subject and DSR registries classify the new tables/entity.
- AC11 OpenAPI trio + architecture inventory regenerated; full Vitest passes (R14-B).
- AC12 D32 changed-line coverage vs 4f318e3: ≥90 % lines, ≥80 % branches (backend
  and frontend).

## 6. Verification
Backend on local PostgreSQL 16 + PostGIS 3.4 + Redis 7 (installed in this container):
new `tests/test_complaints.py` (service+API), `tests/test_migration_0094_complaints.py`,
plus under coverage: denial matrix, audit-route coverage, audit subjects, DSR inventory
registry, notifications/email template tests, openapi, architecture current-state,
mvp_hardening, architecture inventory. ruff check/format. Frontend: tsc, eslint,
prettier on changed files, new Vitest tests for pages/actions, full Vitest. D32 from
LCOV via the repo's changed-line tool if present, else a diff-vs-LCOV script.
Live/E2E proportional to risk: run the API against a scratch database (uvicorn) and
exercise raise → foreign reference 404 → staff reply → notifications/email rows →
follow-up reopen → resolve with real HTTP calls; screens proven by Vitest (Next dev
server optional if resources allow). Full suite left to GitHub CI after an approved push.

## 7. Entry points
`app/api/v1/complaints.py`, `app/services/complaints.py`, `app/models/complaint.py`,
`app/schemas/complaints.py`, `alembic/versions/0094_customer_service_complaints.py`,
`frontend/src/app/{driver/(portal)/help,advertiser/help,admin/complaints}/`,
`frontend/src/lib/complaints/`, `frontend/src/app/admin/page.tsx`.

## 8. Review factors / risks
Tenant isolation and non-enumeration (reference and complaint 404s, org scoping for
advertisers, membership revocation); PII in message text (never in audit metadata,
notification payloads, email, logs); idempotency races (unique constraints + nested
savepoint retry); notification dedupe fingerprint conflicts on retries; concurrent
staff replies (row lock); admin assignment to inactive/non-admin users; shared-file
merge with Batch C (enum members appended at end, router line, admin page section).

## 9. Internal checkpoints
E1 contract + plan review → E2 model/migration/service/routes + backend tests →
E3 frontend + regenerated baselines → E4 evidence (coverage, live API run) →
E5 security/privacy specialist review → E6 post-build change review to PASS →
E7 docs record.

## 10. Plan-review addendum (Opus 5.5 vfd-plan-reviewer: PASS WITH CHANGES, 5 material + 9 minor, all adopted)
- R1 Every complaint-scoped route loads and scopes the complaint first (404
  `COMPLAINT_NOT_FOUND`) before any validation of assignee, category or no-op. PATCH `{}`
  is schema-valid and a no-op on an existing complaint; tested on an unknown id.
- R2 Follow-up, reply and PATCH all lock the complaint row `FOR UPDATE`; replay lookup
  by client_request_id happens after the lock.
- R3 `complaint_messages.status_after` stores the resulting status; replay compares body
  and status_after (so a flipped `resolve` retry is 409).
- R4 Any active member of the active organization, including viewers, may raise and
  follow up (support is not a campaign write; stated assumption). Inactive/revoked
  membership → 404 `ADVERTISER_ORGANIZATION_NOT_FOUND`. Tested.
- R5 Dedupe keys: received `complaint:received:v1:{message_id}:in_app`; reply
  `complaint:replied:v1:{message_id}` / `complaint:resolved:v1:{message_id}` (event key; the
  advertiser helper appends `:in_app`/`:transactional_email`, the driver helper `:in_app`);
  PATCH resolve `complaint:resolved:v1:{id}:{revision}`; assign
  `complaint:assigned:v1:{id}:{revision}:in_app`.
- R6 `reference-options` declared before `{complaint_id}`; tested.
- R7 Complainant message sender is `you | your_team | terrax_media` (no names).
- R8 Driver campaign references: campaigns with an assignment of this driver in
  accepted/active/deactivated/cancelled/completed (jobs the driver took).
- R9 Driver payout references: own `trip_payout` and `adjustment` earnings entries matched
  on `driver_profile_id`, labelled in plain words ("Trip pay ₦… · date" / "Pay adjustment ₦… · date").
- R10 Registries shaped as `(table, sql)` and a `SubjectLinkRule` with counted_tables
  {complaints, complaint_messages} and path_tables.
- R11 §20.4 states that complaint text is kept as the customer-service record, counted in
  the DSR inventory, and any erasure is a manual staff decision (open question); tests assert
  message text never reaches audit metadata, notification payloads or email.
- R12 §20.4 records the driver manual-contact-task exception explicitly.
- R13 Technical cap: 100 messages per complaint (409 `COMPLAINT_MESSAGE_LIMIT`), labelled a
  technical bound, not a client value. Transitions: raise→open; complainant message→open
  (from any status, clears resolved fields); staff reply→answered, or resolved with
  resolve=true (from any status); PATCH status open|resolved from any status.
- R14 Integration with Batch C: re-point 0094 to 0093 and re-run migration/head tests.

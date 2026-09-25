# Current-state issue reconciliation — 23 September 2026

## Purpose, baseline and method

This register answers the owner's post-theft recovery request (recorded in
`docs/progress.md`, "Direct owner requests outside the package queue",
23 Sep 2026). It reconciles every local issue source and the four
21 September Cardvert review leads against current `master`. It is a
coverage and disposition record, not a work authorization; the admitted
work for this request is the bounded batch named in `docs/progress.md`.

- **Baseline:** `master` = `origin/master` =
  `21a5981d631c1ae1667993381a1d4fda350e29cf` (committed 16 Sep 2026 18:32 +0100).
- **Sources reconciled:** `issues/planning/consolidated-findings.md` (115),
  `issues/planning/remediation-order.md`, `issues/findings/high-risk-verification.md`,
  `issues/findings/product-release-verification.md`,
  `issues/product-ui-review/{README,outcomes,reconciliation,packets}.md` (42 outcomes,
  NX-01–NX-23, PB-12/PB-13), `docs/pro-review-register.md`, `to-do.md`,
  `.codex/delivery/cardvert-audit-remediation/plan-ledger.md` and `docs/progress.md`.
- **Method:** each row cites the current source that decides it. "Ledger" means
  the claim rests on an accepted review receipt in `docs/progress.md` and was
  not independently re-executed here; "source" means current code was read.
  An old `OBSERVED` label is never carried forward without re-reading source.
- **The former personal skills** `verified-feature-delivery` and
  `minimal-change-review` were not recovered. Repository references to them are
  treated as names of review gates only; their full instructions are not claimed.

### Disposition legend

| Disposition | Meaning |
| --- | --- |
| FIXED | Current source (or an accepted ledger receipt, stated as such) satisfies the claim. |
| CONFIRMED OPEN | Current source still exhibits the defect or unmet adopted decision. |
| NEEDS REPRODUCTION | Plausible, but a measurement or runtime reproduction is required before changing code. |
| OWNER DECISION | Product, legal or policy authority is missing; no value may be invented. |
| EXTERNAL PREREQUISITE | Blocked by a registered external input (`EXT-*`) or real-world evidence. |
| NOT A DEFECT | Reviewed recommendation; current behavior is correct or already bounded. |

Priority: **P1** money/access/pilot-blocking journey, **P2** misleading
operator or user outcome, **P3** efficiency, ergonomics or copy, **P4** hygiene.
"This pass" marks the fixes admitted in the 23 Sep batch (IDs `CV-01…`).

## A. First-pass audit corpus — 115 candidates

### A1. 86 FIX candidates (R01–R60)

All 60 slices are `COMPLETE` in the PKG-10 register with P/M/CP receipts
(terminal R60 `fc0cb3a`, controller state unchanged at
`PAUSED — EXT-PAYMENT-PROVIDER`). Disposition: **FIXED (ledger)**. A source
sample was re-read on 23 Sep and agrees: final disbursement authority before
provider claim (R20/R21, `app/services/disbursements.py:615`), per-line durable
intents (R20), one active assignment per driver index (R29,
`app/models/campaign_assignment.py`), Lagos invoice year (R27,
`app/services/billing.py`), collection-privacy authority (R38,
`app/services/privacy_authority.py`), terminal driver applications (R32,
`app/services/driver_applications.py:206`), identical End retry after an
ambiguous response (R34–R37 and D27(b), `trip-tracker.tsx:1044`).

| Slices | Candidates |
| --- | --- |
| R01–R07 | GOV-001; GOV-003, TST-001, DB-005; GOV-004; DB-004; DB-001, TST-012, ONB-010; DB-002; DB-003 |
| R08–R17 | GOV-005; GOV-007, AUT-001, AUT-002; AUT-005; AUT-004; AUT-003, REL-003; SEC-001, PRV-008; SEC-002, TST-004; GOV-006; GOV-008; TST-007 |
| R18–R27 | MON-005, MON-006; MON-002; MON-001, DB-007, MON-008; MON-003; MON-004, MON-007, MON-009; COM-001, COM-004; COM-002; COM-003, COM-005; COM-006; COM-007 |
| R28–R37 | CAM-001; CAM-002; CAM-003; CAM-004; ONB-002; ONB-006; OFF-001; OFF-002, OFF-003; OFF-005; OFF-006 |
| R38–R52 | PRV-001, PRV-002; PRV-003; PRV-004, AUD-001, AUD-002; PRV-009, AUD-004, TST-010; PRV-005, PRV-006; PRV-007; AUD-005; MET-003; REP-001; MET-001, MET-002, MET-004, REP-002; REP-003; REP-004; REP-005; REP-006; MET-006 |
| R53–R60 | REL-005; REL-006; REL-004; TST-005; TST-008; TST-011; TST-002; GOV-009 |

### A2. 29 non-executable candidates — current disposition

| ID | Original class | Current evidence | Disposition | Pri |
| --- | --- | --- | --- | --- |
| AUT-006 | Owner decision | D27(a); accepted at `a4c9de2` | FIXED (ledger) | — |
| AUT-007 | Owner decision | D29 requires one active advertiser membership. `create_advertiser_organization` (`app/services/organizations.py:194`) inserts an owner membership without checking other organizations; only `(organization_id, user_id)` is unique; `get_advertiser_organization_for_user` (`:239`) silently picks the newest active membership. No commit implements D29. | CONFIRMED OPEN — **this pass CV-02** | P1 |
| ONB-003 | Owner decision | D30 requires rejecting a new application whose NIN, normalized phone or payout bank account matches an existing driver. No cross-driver comparison exists in `app/` (NIN/bank are envelope-encrypted per record with no keyed lookup digest). | CONFIRMED OPEN — needs a dedicated privacy/migration packet: keyed comparison-digest custody, backfill of encrypted history, DSR/KYC purge alignment, database race authority, and a transaction boundary spanning application creation and the later person/payee capture where NIN and bank details first arrive (architecture §23 D30 target). Public responses must stay non-revealing, as that target already requires. | P1 |
| ONB-004 | Owner decision | D31: admin-entered `valid_until` required and future, no cap (`app/services/vehicle_onboarding.py:575`). | FIXED (source) | — |
| ONB-005 | Owner decision | D29: one admin may decide all checks; each decision is attributable (`require_active_admin` + audit events). | FIXED (source; matches decision) | — |
| ONB-008 | Owner decision | D27(c): IP and normalized-email buckets only, fail closed (`app/core/rate_limit.py:229`). `docker-compose.yml` still sets unused `DRIVER_REGISTRATION_RATE_LIMIT_GLOBAL_*` variables (dead configuration). | FIXED (source); dead config P4 hygiene | P4 |
| ONB-009 | Owner decision | D28 setup authority built (migration `0089`, `/driver-account-setup`). | FIXED (source) | — |
| AUD-006 | Owner decision | D30: planning links allowed draft→paused only (`app/services/audience.py:103`). | FIXED (source) | — |
| OFF-008 | Owner decision | D27(b) identical End retry, capture stopped. | FIXED (source) | — |
| REL-007 | Owner decision | D27(d): release contract requires authenticated TLS DSN (`scripts/release_contract.py:368`). | FIXED (source) | — |
| COM-008 | Owner decision | No decision recorded. | OWNER DECISION | P2 |
| REP-007 | Owner decision | D34 covers disclosure-protection retention only; report retention/withdrawal/presign TTL undecided. | OWNER DECISION | P3 |
| AUD-003, CAM-005, MET-005, MET-007, OFF-004, OFF-007, OFF-009, ONB-001, ONB-007 | Defer | Triggers unchanged (`to-do.md`). | DEFERRED (trigger-based) | — |
| DB-006, GOV-002, REL-001, REL-002, REL-008, TST-003, TST-006, TST-009 | External input | Registered `EXT-*` / device / provider evidence still missing. GOV-002: exact-SHA CI passed for `21a5981` per owner; later changes need their own run. | EXTERNAL PREREQUISITE | — |

## B. 21 September review leads

| Lead | Current evidence | Disposition | Pri | Overlap |
| --- | --- | --- | --- | --- |
| Disbursement claims require historical actors to be active admins | `claim_payout_submission_intent` locks and `require_active_admin`s the batch maker, approver and every requester before deciding the action (`disbursements.py:940-944`). A lookup-only `QUERY` (expired claim, `QUERY_ONLY`, or recovery-incident `provider_lookup_only`) therefore raises `FORBIDDEN_ROLE` forever once any of them is disabled, leaving an ambiguous provider outcome unreconcilable except by webhook. `NOT_FOUND` returns the intent to `PENDING`, and a later `SUBMIT` still rechecks active authority, so the lookup exemption cannot create a provider effect. No test covers disabled historical actors. | CONFIRMED OPEN — **this pass CV-01** | P1 | R20–R22; architecture §16.3 catch-up fairness |
| Second active advertiser membership / newest-wins lookup | See AUT-007. | CONFIRMED OPEN — **CV-02** | P1 | AUT-007, D29 |
| Duplicate NIN/phone/bank (D30) | See ONB-003. Decided, not implemented. | CONFIRMED OPEN (separate packet) | P1 | ONB-003 |
| Rejected campaign copy but no PATCH consumer | `StatusActions` says "Update the requested details, then resubmit"; `PATCH /advertiser/campaigns/{id}` (draft/rejected only, `campaigns.py:241`) has no frontend caller. Accepted commercial terms freeze currency only, which PATCH already guards. | CONFIRMED OPEN — **CV-07** | P1 | ADV-001 |
| Overlapping creative replacement uploads | `uploadReplacement` writes shared state from every in-flight upload; the last upload to *finish* wins, so "Replace and submit" can submit an earlier file than the one last selected. | CONFIRMED OPEN — **CV-06** | P2 | ADV-002 |
| Driver renewal sent to `/driver/profile` | Journey steps for rejected/expired person-payee and vehicle evidence say "Submit a new governed revision" and link to `/driver/profile`, which has no submission. `POST /driver/kyc/submissions` and `POST /driver/vehicles/{id}/evidence-submissions` have no frontend consumer. | CONFIRMED OPEN — separate privacy-reviewed packet (NIN/bank entry and document upload for active drivers) | P1 | NX-05 |
| Creative rejection history, phone verification, WhatsApp consent lack UI | Creative review history: advertiser endpoint exists, tenant-scoped via `get_advertiser_campaign`, no consumer → **CV-08**. Phone verification: driver endpoints and the admin challenge worklist (`/admin/phone-verification-challenges`) have no consumer, so manual-contact tasks can never become actionable from the UI (NX-11). WhatsApp consent requires an approved notice version and wording. | Creative history: CONFIRMED OPEN — **CV-08**. Phone verification: CONFIRMED OPEN (separate packet). WhatsApp consent: EXTERNAL PREREQUISITE (`EXT-MESSAGE-COPY`, `EXT-LEGAL-PRIVACY`) | P1/P2 | ADV-003, NX-11, W2-04D |
| Raw JSON in driver offers / advertiser quotation | Driver offers render base/premium/cap/window/area/creative/zones; raw JSON only inside an optional "complete frozen snapshot" disclosure — acceptable evidence. Advertiser quotation renders line items and totals, but the free-form `production_scope` and `payment_terms` objects appear as raw JSON before immutable acceptance. | Driver: FIXED. Quotation: CONFIRMED OPEN — **CV-11** (complete readable rendering of every key and value) | P2 | ADV-006 |
| Advertiser report date span | All report reads are campaign/organization scoped; an absent range already means all history, so a span cap would not bound work; daily metrics are paginated (≤366). | NOT A DEFECT | — | — |
| `report_cohorts` ledger scan per payout | `ReportCohort.final_cost` rescans the full cohort ledger for each payout (O(payouts×ledger)); semantics are exact. | CONFIRMED (efficiency) — **CV-04** | P3 | R46/R47 |
| `ping-queue.ts` full scan per ping | Each `addPing` reads every encrypted record for the driver to find one meta record. Pending records are cut at ≤40 per batch; real cost depends on device and trip length. The queue is R14-B/R34–R37 authority. | NEEDS REPRODUCTION (physical-device measurement before touching evidence storage) | P3 | TST-006 |
| Admin fraud page after 100-row cap | `list_admin_verifications` returns the newest 100 pending verifications of all types; the page filters physical spot checks client-side, so automatically issued high-earner renewals can hide queued physical checks with no total or pagination. | CONFIRMED OPEN — **CV-03** | P2 | — |
| Driver profile totals from limited arrays | `/driver/profile` shows "Campaigns" (limit 50), "Trip payouts" (filtered ledger limit 50) and "Vehicles" (limit 20) as array lengths; the responses already carry `total`, and the ledger supports `entry_type`. | CONFIRMED OPEN — **CV-09** | P2 | FUX-012 |
| `contacts.py` driver name per task | One `SELECT` per task on a page of up to 100. | CONFIRMED (N+1) — **CV-05** | P3 | — |
| Synchronous Argon2 in async auth | `PasswordHasher(time_cost=2, memory_cost=19456)` runs on the event loop for login, reset, setup and registration. Throughput is bounded by rate limits; impact is per-worker latency during bursts. | NEEDS REPRODUCTION (measure per-call cost and loop stall before changing auth; recorded in §F) | P3 | ONB-001 |
| `tests/conftest.py` DATABASE_URL fallback | `postgis_db_sessionmaker` and seven migration helpers fall back to `DATABASE_URL` (the app's runtime variable, and the README-documented dev database). Data is isolated in random schemas/databases, but tests run `CREATE EXTENSION`, create schemas and create/drop databases on that server. CI uses `TEST_DATABASE_URL` only. | CONFIRMED OPEN — **CV-10** | P2 | R02 |
| `scripts/pytest_shard.py` count-based assignment | No per-shard timing is available on this machine; the last ledger measurement was an 18m08s aggregate. | NEEDS REPRODUCTION (per-shard durations from exact-SHA runs); no change | P4 | — |
| Rejection / creative review / quotation notifications | Only `campaign_approved` and `funding_confirmed` cover the advertiser review/commercial path; `decide_campaign_review` notifies on approval only; creative decisions and new quotation revisions emit nothing. W2-04C names approval events as in scope. | CONFIRMED OPEN — **CV-12** | P2 | ADV-004 |
| Admin audit page vocabulary | Filters now have labels and an exact-match hint; values are raw action/entity vocabulary; metadata is raw JSON behind "View". Forensic audit output is arguably correct as raw evidence. | PARTLY FIXED; remainder OWNER DECISION (FOD-002 evidence presentation) | P3 | FUX-010 |
| Theme picker height | 11 options open upward from a fixed pill with no max-height or scroll; on short desktop viewports the upper options are off-screen and unreachable. | CONFIRMED OPEN — **CV-13** | P3 | — |
| Dispatch sidebar / hover contrast | Measured in §F: sidebar body tokens pass; the sign-out hover uses the un-overridden light-theme coral on the dark forest shell. | CONFIRMED OPEN (hover) — **CV-14** | P3 | FUX-011 |

## C. UI/product-review outcomes (42) and later groups

| ID | Current evidence | Disposition | Pri |
| --- | --- | --- | --- |
| FUX-001 | Approvals queues paginated (`admin/approvals/page.tsx:265,334`). | FIXED (source) | — |
| FUX-002 | Evidence rendered inline via audited signed read; retrieval errors shown. | FIXED (source) | — |
| FUX-003 | Not reproduced this pass. | NEEDS REPRODUCTION | P3 |
| FUX-004 | Payout table now in `overflow-x-auto`. | FIXED (source) | — |
| FUX-005 | Named search/identity added in Phase II; 12 `id.slice(0, 8)` renderers remain (fraud, late data, corrections, rules, payouts, queue options). | PARTLY FIXED; remainder CONFIRMED OPEN | P3 |
| FUX-006 | Assignment/user/driver/vehicle native prompts removed; payout batch forms still use anonymous `window.confirm`. | PARTLY FIXED; remainder CONFIRMED OPEN | P3 |
| FUX-007 | Delivered `a73556c`. | FIXED | — |
| FUX-008 | Per-assignment installation-history requests; one failure replaces the page (fail-closed choice for job actions). | CONFIRMED OPEN (efficiency/resilience) | P3 |
| FUX-009 | `notification-center.tsx:185-191` blanks the badge/list on every background refetch (45 s poll). Destinations still absent. | Flicker: CONFIRMED OPEN — **CV-15**; destinations: OPEN with CV-12 follow-up | P3 |
| FUX-010 | See §B audit page. | PARTLY FIXED | P3 |
| FUX-011 | Re-measure per theme required. | NEEDS REPRODUCTION (Dispatch hover handled by CV-14) | P3 |
| FUX-012 | Driver home "Trip entries" counts a 6-row ledger page. | CONFIRMED OPEN — **CV-09** | P2 |
| FUX-013 | Dedicated `DecisionButtons` component now owns pending state. | FIXED (source; not re-run) | — |
| FUX-014 | Server-side named search added (Phase II `operator_search`). | FIXED (ledger + source) | — |
| ADV-001 | See §B. | CONFIRMED OPEN — **CV-07** | P1 |
| ADV-002 | "Add missing creatives" and "Replace artwork" exist (P1). Race remains. | FIXED except race — **CV-06** | P2 |
| ADV-003 | Campaign rejection reason shown; creative reason not. | CONFIRMED OPEN — **CV-08** | P2 |
| ADV-004 | See §B notifications. | CONFIRMED OPEN — **CV-12** | P2 |
| ADV-005 | Commercial actions now return inline state. | FIXED (source) | — |
| ADV-006 | Line items/totals shown; scope/terms raw JSON. | PARTLY FIXED — **CV-11** | P2 |
| ADV-007 | Preview-then-confirm (C03). | FIXED (source) | — |
| ADV-008 | Map heading "Where campaign vehicles moved" over a target-zone map. | CONFIRMED OPEN — **CV-16** (truthful heading) | P2 |
| ADV-009 | `CampaignPreparationSummary` (P1). | FIXED (source) | — |
| ADV-010 | Reports still require a frozen run; live progress needs measurement/method authority. | OWNER DECISION / EXTERNAL (`EXT-REPORT-METHOD`) | P3 |
| ADV-011 | No completed-campaign closeout transition is authorized (Phase-II V03 rule). | OWNER DECISION | P3 |
| CPY-001 | Naming authority. | OWNER DECISION (FOD-008) | — |
| CPY-002 | 36 raw `replaceAll("_", " ")` enum renderers and other internal vocabulary remain. | CONFIRMED OPEN; wording authority FOD-001/FOD-008 | P3 |
| CPY-003 | Not reproduced. | NEEDS REPRODUCTION | P3 |
| FUD-001…FUD-006 | Usability research backlog. | DEFERRED | — |
| FOD-001…FOD-008 | Owner/legal/external. | OWNER DECISION / EXTERNAL | — |
| PB-12 | Page-critical privacy denials — resilience work in P0/P1 (`loadAdvertiserPageData`, `DataUnavailable`). | FIXED (ledger + source) | — |
| PB-13 | Duplicate of CPY-002. | See CPY-002 | — |
| NX-01 | C06 setup/renewal/reset (`0089`). | FIXED (ledger + source) | — |
| NX-02, NX-03, NX-04 | P2 tracking recovery/earnings clarity claimed; not re-run. | FIXED (ledger, not reproduced) | — |
| NX-05 | See §B renewal. | CONFIRMED OPEN (separate packet) | P1 |
| NX-06 | `admin/late-data` worklist. | FIXED (source) | — |
| NX-07 | `admin/measurement` discovery. | FIXED (source) | — |
| NX-08 | Lifecycle completion not authorized. | OWNER DECISION | P3 |
| NX-09, NX-10, NX-12 | Phase II assignment preparation, payout selection and readiness. | FIXED (ledger + source) | — |
| NX-11 | Contact queue exists; phone-challenge worklist and driver verification UI absent. | CONFIRMED OPEN (separate packet) | P1 |
| NX-13 | `admin/users/actions.ts:90-105`: organization failure after user creation says "Create it again from this page"; retry re-creates the user and fails on duplicate email; no admin screen attaches an organization to an existing advertiser. | CONFIRMED OPEN (separate packet; interacts with CV-02) | P2 |
| NX-14 | (a) Campaign creation converts `datetime-local` window inputs with `new Date(value)` inside a server action (`lib/campaigns/schema.ts:77`, `campaigns/new/actions.ts:54`), i.e. in the frontend server's zone (UTC in the container), while the mid-flight change panel pins Lagos `+01:00` (`[campaignId]/actions.ts:95-98`): the same 09:00 input is stored an hour apart. (b) Invoice correction key minted per render (`admin/billing/[campaignId]/page.tsx:282`); the unsubmitted form keeps its key across a lost response, but a reload mints a new one. (c) Credit due-at `datetime-local` conversion not re-verified. | (a) CONFIRMED OPEN — **CV-17**; (b)(c) NEEDS REPRODUCTION (money specialist) | P2 |
| TZ-DISPLAY (new) | `lib/format.ts` formats instants in the runtime zone (UTC when server-rendered in the container), so Lagos-entered times display an hour early on server-rendered pages. | CONFIRMED OPEN — separate timezone-presentation packet (not in this pass) | P2 |
| REVIEW-HISTORY-SCHEMA (new, found in the CV-08 privacy review) | The advertiser campaign and creative review-history responses reuse the admin event schema, so the owning advertiser receives `actor_user_id` (the reviewing admin's ID) and the full `reviewed_snapshot`. This behaviour existed before this pass; CV-08 only reads `rejection_reason` from it. | CONFIRMED OPEN — separate privacy/contract packet (advertiser-scoped schema plus the §9 baselines) | P2 |
| NX-15 | Purpose-selected, audited, auto-hiding reveal (Phase II). | FIXED (ledger) | — |
| NX-16, NX-17, NX-18 | Shared public action errors; section resilience; generic commercial error text. | FIXED/PARTLY FIXED (source) | P3 |
| NX-19 | Earnings clarity (P2); payout timing/destination policy is external. | PARTLY FIXED; remainder OWNER/EXTERNAL | P3 |
| NX-20, NX-23 | Support destination, disclosures, role policy. | OWNER DECISION / EXTERNAL | — |
| NX-21, NX-22 | Reuse FUX-003–006/010/014 and CPY-002/003. | See those rows | — |

## D. Advisory Pro register

Package 1 findings 1, 2, 5, 6 and 7 are resolved in PKG-02. Findings 3, 4 and
8 were deferred to PKG-07/PKG-08, both closed (PKG-08 `BLOCKED` only on
external evidence). The package guidance sections are advisory and create no
open work. Disposition: **FIXED (ledger)** or **EXTERNAL PREREQUISITE**
(rollback/restore and live evidence).

## E. Evidence about code newer than `21a5981`

- The local repository is a fresh clone made 22 Sep 2026 18:59 +0100
  (`git reflog`); it has no stashes, no dangling objects and no local branches
  other than `master`.
- After `git fetch --all --prune` on 23 Sep, the newest remote ref is
  `origin/master` at `21a5981`; every other remote branch is older
  (latest `feat/post-remediation-audit-baseline`, 5 Sep).
- Every commit that `docs/progress.md` cites as a "local candidate"
  (`1da0aee`, `533f62d`, `f56d7fb`, `024a312`, `8e3ce9d`, `a73556c`, `fc0cb3a`)
  is an ancestor of `master`.
- No file in the repository refers to work after 16 Sep 2026.

Conclusion: nothing in the repository or on GitHub indicates newer code. Work
that existed only on the stolen laptop cannot be detected from here and is
neither confirmed nor ruled out.

## F. Measurements and notes supporting this pass

The full execution record, with reviews and verification, is the 23 Sep
post-build paragraph in `docs/progress.md`. The measurements that decided the
leads are:

- **Dispatch contrast (CV-14).** The sign-out hover `#a8232e` on the forest
  shell measured 2.05:1, which fails WCAG AA. The Dispatch-scoped
  `#ff6b7a` measures 5.32:1. The other sidebar text/background pairs measure
  6.5–13.4:1 and were left alone.
- **Argon2 (lead).** Verify takes about 21 ms median (25 ms p95) at the current
  parameters. `asyncio.to_thread` gave no measurable loop-stall improvement in
  a local probe, so nothing changed; the lead stays NEEDS REPRODUCTION under
  real concurrent load.
- **D32 changed-line coverage against `21a5981`.** 96.05% of lines (243/253)
  and 81.17% of branches (181/223), from local LCOV. The CI receipt and the
  controlled D33 baseline refresh follow the first exact-SHA run after an
  owner-approved push.
- **Ping queue and shard balance.** Not measured in this pass; they remain
  NEEDS REPRODUCTION.
- **Superseded tracking.** The `.codex/delivery/*/plan-ledger.md` decision
  states are historical; this matrix supersedes them.

# Mobility AdTech Platform — System Architecture

**Version 1.35 — 2026-08-21. Canonical source of truth: current state AND target state.**

> **Read §35 before building anything.** An independent review (6 Aug 2026,
> code-verified) produced a remediation register with gates. Seven rows
> originally described defects in already-built code; RM1/RM3/RM4/RM5/RM7 are
> closed and RM2/RM6 are now closed. The other rows are
> requirements the owning slice must honour. Gates in §35.3 block named live
> actions while permitting their owning slices to build and test synthetically
> in the dependency order controlled by `docs/progress.md`.

> **Scope baseline and translation contract:** the client-facing proposal
> `docs/Mobility_AdTech_MVP_Proposal_5_Month_Retargeting.docx` (D11) is the
> requirements baseline **as superseded by later direct client decisions,
> currently D18–D23**. The later row wins wherever Somto's final questionnaire answer
> conflicts with the proposal or an older D-row. **This
> doc is its architectural translation**: it converts those requirements into
> system design using best-practice decisions, and agents build from this doc,
> not from proposal literalism. Where the proposal's wording and this doc
> differ, the resolution is recorded in `docs/decisions-log.md` (e.g. D12:
> hourly pay supersedes Module E's "mileage-based" phrasing) — never silently
> diverge in either direction. Narrower scope claims in older docs (notably
> `docs/build-loop/`) are historical.

This document defines both **what exists** (Part II, verified against commit
**`301519d`** on branch `f7-hardening`) and **the architecture the
finished product should have**. Future development — human or AI agent —
conforms to Part III (target) while respecting Part II (current) as the
verified starting point.

> **F7 hardening is committed.** The former [PLANNED-F7] layer (sliding session
> via `POST /api/v1/auth/refresh` with `sv`/`iat`/`auth_time` claims,
> `must_change_password`, Redis rate limiting, audit API + UI, migrations
> `0011`/`0012`, rich seed, backup/restore scripts, Sentry hooks, backend CI)
> is now [BUILT] and verified. Staging remains **research only** — nothing is
> deployed (`docs/staging-options.md`).

---

## 1. How to use this doc

Read this document **before designing or building any feature**. It exists so that
implementations conform to one architecture instead of drifting apart, agent by
agent, PR by PR.

### The conformance rule

> If your design contradicts this document, **stop and flag it**. Either the doc is
> stale (fix the doc first, in its own change) or your design is wrong (fix the
> design). Never silently diverge.

### The four tags — four layers of truth

Every architectural claim below is tagged:

| Tag | Meaning | What you may do |
|-----|---------|-----------------|
| **[BUILT]** | Verified against commit `301519d` (the Part II pin). | Rely on it. If the code no longer matches, the doc is stale — flag it. |
| **[PLANNED-F7]** | Historical tag for the F7 hardening plan. F7 is delivered — remaining occurrences mark F7 items that deliberately did **not** ship (e.g. staging deploy, which stayed research-only). | Treat like [TARGET]: do not build ad hoc. |
| **[TARGET]** | The designed end-state architecture for functionality not yet built. Structure is decided; some parameters may still be [OPEN]. | Build **toward** it. New features must fit these boundaries. Do not implement a [TARGET] component ad hoc — it gets its own planned build phase. |
| **[OPEN]** | An execution parameter/artifact the client or an external owner has not yet supplied. **Since D18–D20 (14 Aug 2026), Q1–Q34 product directions and the three implementation clarifications are client-confirmed in `docs/decisions-log.md` Part 2**; older Q-referencing `[OPEN]`/“Blocked-by” prose has no force where those rows answer it. | Do not invent missing provider credentials, legal wording, statutory facts, permit evidence, policy thresholds or commercial values. Build provider-neutrally where the registered live-use gate permits. |

**[TARGET] vs [OPEN]:** a [TARGET] section fixes the *shape* (which component, which
boundary, which tables/ports) even when a business *parameter* inside it is [OPEN]
(which payment provider, what the hourly rate is). The point: open questions must
not block architectural direction, and architectural direction must not foreclose
open questions.

### Where a new feature goes

Before implementing anything, find your feature in the **Feature placement map
(§30)**. It tells you where the code lives, what it may touch, which invariants
apply, and what it is blocked by. If your feature has no row, add one in the same
PR — that is an architecture change and follows the amendment rule.

### Amendment rule

Any PR that changes the architecture (new endpoint group, new table, new surface,
changed convention, implemented F7/[TARGET] item, answered questionnaire item)
**must update this document in the same commit** — including moving claims between
tags ([PLANNED-F7]/[TARGET] → [BUILT], [OPEN] → decided) and appending to the
changelog (§34).

### Reading paths

- **"Where does feature X go?"** → §30 placement map, then the referenced section.
- **"What exists today?"** → Part II (§5–§12); delivered-work summary vs. the
  client promise → `docs/progress.md`.
- **"How should I build the next phase?"** → `docs/progress.md`, whose package
  queue exclusively controls execution order and authorization; its 71-item
  checklist controls internal completeness, while §31 is roadmap
  context, then the relevant Part III section supplies design context.
- **"What external evidence is still missing?"** → §33 routing and `docs/progress.md` external register.

---

# PART I — PRODUCT INTENT

## 2. Purpose, scope, and end state

### 2.1 What the product is (from the client brief)

A mobility advertising platform for the Nigerian market: business **Terrax
Media**, product/app **Cardvert** (Q29/D18). Advertisers run geo-targeted ad campaigns on shared-ride
vehicles; drivers carry the branding, drive with GPS trip tracking, and earn
payouts; operators (admins) onboard everyone, approve what goes live, review
fraud, and move the money. The engine computes route analytics, impression
estimates, fraud flags, and payouts from GPS data over PostGIS.

### 2.2 The intended end state

From the developer brief + decisions D1–D7 + the D18/D20 client direction, the finished
product is:

1. **Advertiser side** — self-serve portal: campaigns with zone targeting,
   creative upload with ops approval, attribution reports, exposure heatmaps,
   quotes/invoices, prepaid funding (gateway later), budget enforcement.
2. **Driver side** — a production-hardened **screen-on installable PWA** for
   the pilot (D18/Q10, superseding D11's native timing), using the built durable
   offline/retry and trip-seal contract; the native background client follows
   after the pilot. It provides campaign offers with transparent zone-tiered hourly
   pay + daily payable-hours cap, trip tracking, earnings ledger with
   release-schedule payouts, dispute channel.
3. **Operator side** — the control plane: the Q26-confirmed onboarding checklist
   (exact legal wording and renewal intervals remain external),
   campaign/creative approval queues, installation photo verification,
   assignment with competitor separation, fraud hold-and-review, payout release +
   disbursement, audit trail.
4. **Platform layer** — notifications (in-app + advertiser email + ops WhatsApp;
   automated WhatsApp/SMS post-pilot), payment collection
   and payment/disbursement integrations behind provider adapters (Q3/Q27),
   NDPR-compliant data retention, and **online-to-offline retargeting** at
   full proposal Module G scope (D6/D11): retargeting source records +
   campaign/zone linkage + follow-up-targeting insights, on top of Q11's
   anonymised exposure aggregates (§22).
5. **Future layers** (post-pilot, explicitly out of current scope): native
   background-tracking driver app (same Start/End and backend contract), edge-AI
   vehicle/pedestrian counting, multi-city scale-out and audience attribution
   network.

### 2.3 Scale honesty

Confirmed pilot shape (Q30/D18): **Abuja, 10 vehicles, 5 paying advertisers,
3 months.** Every sizing decision in this doc is made for that scale with a
stated path to ~10× (500 vehicles, multi-city), and **no further**. We do not
design for imaginary web scale (see P1, §4).

---

## 3. Product decisions & constraints

Confirmed decisions live in **`docs/decisions-log.md`** (Part 1: append-only
D-rows, supersede-never-edit; Part 2: per-Q statuses — D18 records the direct
client answer, while D20 records the later three-point implementation
clarification). Summary with build status:

| # | Decision | Status vs code |
|---|----------|----------------|
| D1 | **Operator-led onboarding** — no self-serve signup; admin creates users/orgs. *Narrowed by Q13: applies to advertisers/orgs; drivers get self-registration ([TARGET] §23)* | [BUILT] matches (§6.3); driver self-registration is CONFIRMED, unbuilt |
| D2 | **Driver pay = fixed hourly rate** (naira/hour × verified payable time; D18 adds base/premium zone tiers) | [BUILT] §16.1 `payout_v2` history; [TARGET] `payout_v3` under D18. v1/v2 history is frozen; never extend v1's per-km components or reprice old work |
| D3 | **Screen-on pilot tracking** — installable PWA, phone mounted; native app later, identical backend contract. D18/Q10 reconfirms D3 and supersedes D11's native-in-MVP timing. | [BUILT] interim PWA contract matches (§8.6); production PWA hardening is [TARGET] W4; native client is post-pilot (§23/§31) |
| D4 | **Payable-hours cap** per campaign/driver/day, shown in driver's offer | [BUILT] in v2 and preserved in target v3 (§16) |
| D5 | **Hold-and-review fraud posture** — flags hold earnings for admin review; multipliers become secondary | Flags + multipliers are [BUILT]; the hold/review/dispute workflow is [TARGET] §17 |
| D6 | **Retargeting is in the MVP** (shape confirmed by D18/Q11, scope extended by D11) | [TARGET] §22; privacy boundary fixed now |
| D7 | **In-platform creative upload** (Q18 confirmed) | [TARGET] §19; creatives stay metadata-only until built |
| D11 | **The 5-month client MVP proposal established the scope baseline** — retargeting at full Module G scope, CSV/PDF export and pilot deployment remain in scope; D18/D20 later supersede its native-app timing and any other conflict. | [TARGET] §22/§31; interpreted through D18/D20 |
| D17 | **One encryption-provider boundary and ciphertext schema** spans pilot bank data and later KYC/national identifiers; W2-02D upgrades custody, not the data shape | [TARGET] §16.3/§19.3; MNY-10A then W2-02D |
| D18 | **Somto's final Q1-Q34 answer is the direct client authority, later clarified for Q11/Q24/Q30 by D20** — production screen-on PWA for the pilot, `payout_v3` base/premium zone pricing, clean-immediate/flagged-seven-day review, automated pilot transfers, 24-hour refund eligibility, Cardvert/Terrax Media and the Abuja pilot shape | [TARGET] amendments across §15–§25/§31/§35; Part 2 of the decision log is binding |
| D20 | **The client approved the three implementation clarifications** — Q11 activation uses geography/time/context only and never person-level route retargeting; Q24 standard production waits 24 hours unless an advertiser requests expedited production and accepts an immutable refund waiver; Q30 defaults to Campaign Performance Analysis and includes true ROI only with conversion/revenue inputs plus an approved reproducible method | [TARGET] §15/§22/§27/§32/§35; existing slice contracts only, with no package or dependency expansion |

Hard constraints (violating any of these is an architecture change, not a feature):

- **No realtime web push** — no WebSockets/SSE ([BUILT] §6.5; reaffirmed for
  target, §14.4). The MVP PWA polls; any later native push adapter does not
  relax this constraint.
- **No file upload/storage pipeline** until §19 is built as a phase (Q18 is confirmed; the pipeline still arrives only as its planned phase).
- **Operator-led** — no self-serve registration of any kind today (driver self-registration is confirmed by Q13 but arrives only as its planned §23 phase).
- **Browser never calls FastAPI** (§8.2). Native apps will (§23) — browsers never.
- **Raw location data never leaves the analytics domain** (§22.2) — new, binding now.
- Every build phase implementing a decision references its D-number in the commit
  message (per decisions-log usage rules).

---

## 4. Architectural principles

These govern every design choice below and every future one. When two rules seem
to conflict, the earlier-numbered principle wins.

- **P1 — Modular monolith, one deployable per tier.** One FastAPI app + one worker
  process + one Next.js app. No microservices, no service mesh at this scale.
  Modularity lives in the service layer, not the network. Split a service out only
  when a measured constraint (load, team, deploy cadence) demands it.
- **P2 — The database is the only source of truth.** Postgres holds all facts.
  Redis is disposable infrastructure (rate limits, queue transport, cache): losing
  Redis may degrade behaviour but must never lose data. Scheduled jobs derive
  their work-lists from DB state, not from queue contents.
- **P3 — Contract-first.** `openapi.json` is the API's identity; the three
  baselines (§9) move together; frontend types are generated, never written.
- **P4 — Thin routers, fat services, reusable everywhere.** Routers
  validate/authorize/delegate. Business logic lives in `app/services/*` and is the
  same code whether invoked by a request, a worker job, or a CLI.
- **P5 — Ports and adapters for every external vendor.** Payments, disbursement,
  messaging, object storage, map tiles, encryption/key custody: services depend on a small interface;
  vendor SDK code lives in `app/adapters/*`. Vendor choice ([OPEN] in several
  places) must never block or leak into domain design.
- **P6 — Money is boring.** Decimals as strings on the wire; append-only ledger;
  every computation stamped with a `formula_version`; every mutation audited;
  corrections are new entries, never edits.
- **P7 — Privacy by architecture.** GPS traces are personal data (NDPR).
  Trip-scoped tracking only; retention enforced by a job, not by promise; raw
  pings readable only by the analytics/fraud domain; everything advertiser-facing
  or exported is aggregated above a k-threshold.
- **P8 — Async means jobs, not push.** Background work = queued/scheduled jobs
  that are idempotent and re-runnable. Client "liveness" = polling. No
  WebSockets/SSE in the MVP target.
- **P9 — Idempotency at every retry boundary.** Ping batches (built), webhook
  events, job executions, notification sends: all carry a natural or explicit
  idempotency key and tolerate replay.
- **P10 — Smallest thing under all open options.** Where a question is [OPEN],
  build the smallest design that works under every still-open answer, and say so
  in the PR.
- **P11 — Every claim verifiable.** Architecture claims cite code or an executed
  check. Counts, behaviours and invariants in this doc carry verification
  comments where practical.
- **P12 — Agent-legible structure.** Follow the placement map (§30), the naming
  conventions (§29), and the amendment rule (§1). A feature an agent cannot
  place from this doc is a doc bug — fix the doc.

---

# PART II — CURRENT STATE (verified)

## 5. System overview **[BUILT]**

```
        ┌─────────────────────────── Browser ───────────────────────────┐
        │  Advertiser portal      Admin console      Vantage Driver PWA │
        │  /advertiser/*          /admin/*           /driver/* (install-│
        │                                            able, GPS tracking)│
        └───────────────┬────────────────────────────────────────────---┘
                        │  HTTPS — session = JWT in httpOnly cookie
                        │  (browser NEVER calls FastAPI directly)
        ┌───────────────▼───────────────┐
        │  Next.js 16 App Router (BFF)  │  frontend/
        │  Server Components / Actions  │  typed client (openapi-fetch)
        │  proxy.ts fast-path redirects │  requireRole in server layouts
        └───────────────┬───────────────┘
                        │  Authorization: Bearer <JWT>, internal network
        ┌───────────────▼───────────────┐
        │  FastAPI  (app/)              │  /api/v1 — 81 operations
        │  SQLAlchemy 2 async + Alembic │  request/response + worker
        │  services layer, audit trail  │  enqueue (§6.5); no WebSockets
        └───────┬───────────────┬───────┘
                │               │
   ┌────────────▼─────────┐   ┌─▼──────────────────────────┐
   │ PostgreSQL 16 +      │   │ Redis 7                    │
   │ PostGIS 3.4          │   │ [BUILT] login rate-limit   │
   │ 21 tables, geometry  │   │ counters (F7) + arq queue  │
   │ (Point/MultiPolygon) │   │ (§6.5); both fail-open /   │
   └──────────────────────┘   │ disposable                 │
                              └────────────────────────────┘
```

Not boxed above: the arq `worker` container (§6.5, §14) shares the FastAPI
codebase/image and sits on the same Redis + Postgres. The target-state version
of this diagram is §13.

## 6. Backend architecture

### 6.1 Module layout **[BUILT]**

```
app/
├── main.py            # create_app(): middleware, CORS, error handlers, routers, root /health
├── api/v1/            # one router module per domain area + dependencies.py + router.py
├── core/              # config.py (pydantic-settings), security.py (JWT/argon2),
│                      # errors.py (AppError + envelope), middleware.py (request-ID)
├── db/                # base.py (DeclarativeBase), session.py (async engine/session)
├── models/            # SQLAlchemy models — 21 tables (see §7)
├── schemas/           # Pydantic request/response models, incl. pagination + decimal mixins
├── services/          # all business logic; routers stay thin
└── seeds/demo.py      # demo seed CLI (python -m app.seeds.demo) — NOT an endpoint
```

**Invariant:** routers validate/authorize and delegate; business logic lives in
`app/services/*`. Follow this split for new endpoints. (Target-state additions to
this tree: §29.1.)

### 6.2 API surface **[BUILT]**

82 operations total: **81 under `/api/v1`** plus a root `/health` liveness check.
<!-- verified 2026-07-20: grep -Eh "@router\.(get|post|put|patch|delete)" app/api/v1/*.py | wc -l → 81;
     openapi.json paths walk → 82 ops / 66 paths incl. root /health -->

Grouped by URL prefix (operation counts from `openapi.json`):

| Prefix | Ops | Domain areas (router modules) |
|--------|-----|-------------------------------|
| `/api/v1/admin/*` | 35 | users, advertiser-organizations, drivers (profiles + onboarding), vehicles, campaigns (read), campaign-assignments (+cancel), payout-rules, payout-calculations, trips (analytics / recompute / estimate-impressions / calculate-payout), fraud-flags, traffic-density-profiles, impression-estimates, heatmap, audit-events (F7) |
| `/api/v1/advertiser/*` | 22 | organization, dashboard summary, campaigns CRUD (+status), creatives, zones CRUD, campaign heatmap, reports (summary, daily-metrics, trips, report, impressions summary, cost summary) |
| `/api/v1/driver/*` | 18 | profile, vehicles (read), campaign-assignments (accept/activate/deactivate), trips (start/end/current/pings), analytics summary, earnings (summary + ledger) |
| `/api/v1/auth/*` | 3 | login, refresh (sliding session), change-password — no logout endpoint (the BFF deletes its cookie), no register |
| `/api/v1/me` | 1 | current user + advertiser-organization context; the route-guard endpoint |
| `/api/v1/health`, `/api/v1/health/ready` | 2 | liveness + readiness |
| `/health` (root) | 1 | container liveness |

The role split **is** the URL split: every business endpoint lives under exactly
one of `/admin`, `/advertiser`, `/driver` and is guarded by the matching role
dependency (`AdminUserDependency`, `AdvertiserUserDependency`,
`DriverUserDependency` in `app/api/v1/dependencies.py`). **Invariant:** new
endpoints follow this prefix-per-role pattern; no mixed-role endpoints outside
`/me`. **[TARGET] planned exception:** `/api/v1/webhooks/*` (§15.4) — machine
callers authenticated by signature, not JWT; nothing else may join that namespace.

**There is no seed endpoint.** Demo data is seeded by CLI only
(`python -m app.seeds.demo`), gated by `ALLOW_DEMO_SEED` (default `false`).

### 6.3 Auth model **[BUILT]**

- `POST /api/v1/auth/login` exchanges email+password for a bearer JWT.
- JWT: HS256, payload **`{sub, exp, iat, auth_time, sv}`**
  (`app/core/security.py`), default lifetime 60 min
  (`ACCESS_TOKEN_EXPIRE_MINUTES`).
- **Sliding session with a 12h absolute cap (F7):** `POST /api/v1/auth/refresh`
  rotates the JWT while `auth_time` is within
  `SESSION_ABSOLUTE_LIFETIME_MINUTES` (default 720); the cap is also enforced on
  every authenticated request (`app/api/v1/dependencies.py`). The driver
  tracking surface additionally rotates its cookie via `GET /driver/keepalive`.
- **Revocation (F7):** `sv` (session_version) is compared against the DB on
  every request; a password change increments it, invalidating all outstanding
  tokens except the fresh one returned by the change-password flow
  (`SESSION_REVOKED` / `SESSION_EXPIRED` error codes).
- **`POST /api/v1/auth/change-password` (F7):** requires the current password,
  refuses reuse, enforces min length, bumps `sv`, returns a fresh token.
  Current-password guesses share the login rate-limit buckets (refunded once
  the password is proven) and failures are audited
  (`auth.password.change_failed`).
- **`must_change_password` (F7):** set on admin-created users; every endpoint
  outside `{/me, /auth/change-password, /auth/refresh}` returns 403
  `PASSWORD_CHANGE_REQUIRED` until the password is replaced.
- **Legacy-token handling (F7, deliberate):** pre-F7 tokens without `sv`/
  `auth_time` still authenticate until their own `exp` (≤60 min), but are
  refused by `/auth/refresh` and are not revocable by password change —
  accepted residual risk bounded by the old token lifetime; `JWT_SECRET_KEY`
  rotation is the break-glass (runbook).
- **Login rate limiting (F7):** Redis-backed, per-account 5/15 min, per-IP
  150/5 min, global 250/5 min, atomic Lua reserve/refund, **fail-open** when
  Redis is down; trusted-client-IP header honored only behind the documented
  edge preconditions (§12, runbook).
- Passwords: argon2 (`argon2-cffi`), enforced minimum length 12
  (`PASSWORD_MIN_LENGTH`, validator refuses lower).
- Roles: exactly **`admin`, `advertiser`, `driver`** — `UserRole` StrEnum plus a
  DB check constraint `ck_users_role`. <!-- verified: app/models/user.py -->
- User lifecycle: suspended and disabled users are rejected at login **and** on
  every authenticated request.
- **No self-registration.** Users are created by admins (`POST /api/v1/admin/users`).
  Config guards: JWT secret must be changed and ≥32 chars outside local/test
  environments; wildcard CORS origins refused outside local/test.
- Do not add other claims named `sv`. MVP auth evolution beyond F7 is password
  reset and production-PWA hardening (§23); native refresh grants are Phase 2.

### 6.4 Cross-cutting API conventions — INVARIANTS **[BUILT]**

Every new endpoint must obey all of these:

1. **Error envelope.** All errors — `AppError`, HTTP exceptions, validation — are
   rendered by the handlers in `app/core/errors.py` as:
   ```json
   { "error": { "code": "...", "message": "...", "details": {}, "request_id": "..." } }
   ```
   Raise `AppError(code, message, status_code=..., details=...)` in services;
   never hand-roll error JSON. Validation failures return 422 with code
   `VALIDATION_ERROR`. **[BUILT] FND-07 (RM7):** the four
   vehicle/assignment/driver/trip exclusivity constraints are registered in
   `app/db/integrity.py`, and a lost DB race at assignment create/activate or
   trip start returns the same stable 409 code as its guarding pre-check —
   unrelated integrity failures stay unexpected 500s.
2. **Request IDs.** `RequestIdMiddleware` accepts or generates `X-Request-ID`,
   echoes it on the response, and injects it into every error envelope.
3. **Pagination.** Every list endpoint returns `{items, total, limit, offset}`.
   No cursors, no bare arrays.
4. **Decimals cross the wire as strings.** Money and rates are `Decimal` in
   Pydantic and serialized via `DecimalStringMixin` (`app/schemas/payouts.py`).
   Never emit floats for money.
5. **Geo data is GeoJSON.** Campaign zones accept/return GeoJSON geometry dicts
   (MultiPolygon, SRID 4326, PostGIS-validated with an area cap); heatmaps return
   a GeoJSON `FeatureCollection` (`HeatmapFeatureCollection`).
6. **Idempotency where writes can retry.** Ping ingestion
   (`POST /driver/trips/{id}/pings`) carries a client `idempotency_key`, unique
   per `(trip_session_id, idempotency_key)` (DB constraint
   `uq_location_ping_batches_trip_idempotency_key`); replays return the recorded
   batch instead of double-counting. Apply the same pattern to any future
   retry-prone write (P9).
7. **Creatives are metadata-only.** `campaign_creatives` stores `asset_url`,
   mime type, dimensions, checksum — **no upload pipeline, no file storage**
   until §19 is built (D7).
8. **Computation is versioned.** Analytics/impressions/payouts stamp a
   `formula_version` (`route_analytics_v1`, `impressions_v1`, `payout_v1`) from
   settings. Changing a formula means bumping its version, not silently changing
   outputs.
9. **Audit trail.** Mutating flows write `audit_events` via
   `app/services/audit.create_audit_event` — **mandatory for all new
   mutations.** F7 added authentication events (`auth.login.succeeded/failed/
   rate_limited`, `auth.password.changed/change_failed/change_rate_limited`),
   the admin-only filterable
   `GET /api/v1/admin/audit-events` API, the `/admin/audit` UI, and query
   indexes (migration `0012`). **[BUILT] S4 backfill:** trip start/end
   (`driver.trip.started/ended`), analytics recompute
   (`admin.trip_analytics.recomputed`), traffic-density profile create/update
   and impression estimation (`admin.traffic_density_profile.*`,
   `admin.impression_estimate.computed`) now write audit events atomically
   with their mutation, and the route-table-driven regression test
   (`tests/test_audit_route_coverage.py`) fails on any future unregistered
   mutating route.
   **Approved exception (S4, orchestrator-approved):** ping-batch ingestion
   (`POST /driver/trips/{id}/pings`) writes NO audit event — at ~1 batch per
   10–15 s per active vehicle it would make this append-only, indefinitely
   retained table >90% telemetry noise. The immutable, idempotency-keyed,
   payload-hashed `location_ping_batches` row is the compensating ingestion
   evidence, and its destruction is itself evidenced in `data_purge_audit`
   (§24.2.4). Idempotent replays perform no mutation and create no audit
   event.
   Residual honesty note (discovered by the S4 coverage test, outside its
   approved scope): `POST /auth/refresh`, `PATCH /driver/profile`, and the
   driver assignment accept/activate/deactivate routes still write no audit
   events — registered as KNOWN_UNAUDITED in the coverage test; closing them
   is follow-up work, not license to copy.

### 6.5 Background / async story **[BUILT]**

**One arq worker — everything else strictly request/response.** No Celery, no
`BackgroundTasks`, no schedulers in the web process, no WebSockets, no SSE.
<!-- verified: grep BackgroundTasks|celery|websocket app/ → 0 hits -->
Until this change the story was "none — strictly request/response"; the §14
trip-processing pipeline is now **[BUILT]**: one arq worker (`app/jobs/*`,
compose service `worker`) completes missing rows for **sealed** trips (RM3: the
seal, not the end, is the money-chain trigger) and refreshes
an impression estimate when its analytics or open-fraud inputs are stale. It is
fed by a fail-open enqueue-after-commit on trip seal
(`app/core/trip_enqueue.py`) and backstopped by a Postgres-derived cron sweep,
plus a seal sweep that force-seals ended trips past the recovery grace.
Admin recompute endpoints remain the synchronous recompute/override tools.
Redis's consumers: **[BUILT] F7 login rate limiting** (`app/core/rate_limit.py`
— disposable counters, fail-open per P2) and **[BUILT]** the arq queue (also
disposable — the sweep re-derives work from Postgres). Do not introduce
queues/realtime ad hoc — §14 remains the one sanctioned design.

## 7. Data model

### 7.1 Entities **[BUILT]** — 28 tables

<!-- verified 2026-08-21: rg -o "__tablename__" app/models/*.py | wc -l → 28 -->

Identity & orgs:

| Table | Purpose / key relationships |
|-------|------------------------------|
| `users` | All humans; `role` ∈ admin/advertiser/driver (check constraint); argon2 hash; status lifecycle; F7 adds `must_change_password` + `session_version` (migration `0011`) |
| `advertiser_organizations` | Advertiser tenant; currency; status |
| `organization_memberships` | user ↔ advertiser_organization, with membership role/status |
| `audit_events` | Append-only audit trail; `actor_user_id → users` (SET NULL); F7 adds created_at/action/entity query indexes (migration `0012`) |
| `data_purge_audit` | Append-only purge-evidence lifecycle events (S4, §24.2.4 — NDPA compliance artifact; partial unique `dropped` per partition; migration `0014`) |

Supply side (drivers/vehicles):

| Table | Purpose / key relationships |
|-------|------------------------------|
| `driver_profiles` | 1:1 extension of a driver `user`; onboarding status |
| `vehicles` | Owned by `driver_profiles`; type/status enums |

Demand side (campaigns):

| Table | Purpose / key relationships |
|-------|------------------------------|
| `campaigns` | Owned by `advertiser_organizations`; budgets, dates, status; `created_by_user_id` |
| `campaign_creatives` | Metadata-only creative records per campaign (see §6.4.7) |
| `campaign_zones` | Geo targeting per campaign; **PostGIS `geometry(MultiPolygon,4326)`**; zone type (target/bonus/exclusion-style) |
| `campaign_payout_rules` | Per-campaign payout rates (per-km, per-active-hour, zone bonuses, impression rate, fraud multipliers, min/max) |

Matching & execution:

| Table | Purpose / key relationships |
|-------|------------------------------|
| `campaign_assignments` | campaign ↔ driver_profile ↔ vehicle; status lifecycle; `assigned_by_user_id` |
| `campaign_activation_events` | Assignment lifecycle event log |
| `trip_sessions` | A tracked drive under an assignment; denormalized FKs to campaign/driver/vehicle; timestamps only — **no geometry columns** (stale pre-S4 claim corrected; only `location_pings.geom` carries coordinates) |
| `location_ping_batches` | Idempotent ingestion envelope (unique trip+key, payload hash, accepted count); purged by retention only when zero pings remain (§24.2.1) |
| `quarantined_ping_batches` | Post-seal ping batches held for serialized admin apply/discard without automatic money recomputation (RM3/D15) |
| `location_pings` | Individual GPS points per trip/batch; **monthly range-partitioned by `recorded_at`** with composite PK `(id, recorded_at)` (S4, migration `0014`, §24.2.2) |

Derived (analytics → money):

| Table | Purpose / key relationships |
|-------|------------------------------|
| `trip_analytics` | Per-trip route metrics (distance, active time, zone overlap), `formula_version` |
| `fraud_flags` | Typed/severity-classed flags against trips; links to trip_analytics. Serialized lifecycle `open → acknowledged → confirmed \| dismissed` carries coherent reviewer/time/note evidence; partial unique index `uq_fraud_flags_trip_nonterminal_flag_type` dedupes each trip/type while the hold remains active (`open \| acknowledged \| confirmed`) |
| `fraud_assessments` | One current attempt per sealed trip (`pending \| clean \| flagged \| error`) with formula, analytics/input fingerprints and current-flag provenance; pending/error never count as successful-current |
| `route_replay_signatures` | One current detector/config/analytics-bound signature per trip; indexed absolute-payload and time-shift-normalized hashes support bounded cross-trip/account replay reconciliation without persisting raw route facts in review evidence |
| `traffic_density_profiles` | Admin-managed density inputs for impression math |
| `impression_estimates` | Per-trip estimated impressions + confidence, links density profile |
| `campaign_payout_rule_revisions` | Append-only effective-dated payout-v3 rule revisions (MNY-06A) |
| `assignment_rule_bindings` | Acceptance-time frozen payout terms and eligibility/geography fingerprints (MNY-06B) |
| `payout_correction_orders` | Maker-checker projected correction lifecycle with value-complete evidence (MNY-06C) |
| `payout_calculations` | Per-trip payout math snapshot (rule inputs + fraud multipliers) |
| `earnings_ledger_entries` | Driver earnings ledger (typed, statused entries) |

Notes:
- PostGIS columns use **hand-rolled `UserDefinedType`s** (`PostGISPoint`,
  `PostGISMultiPolygon`) that compile to `TEXT` on SQLite for unit tests — the
  project deliberately does **not** use GeoAlchemy2. Follow the same pattern for
  new geometry columns.
- All PKs are UUIDs with `gen_random_uuid()` server defaults (exception:
  partitioned `location_pings` uses composite `(id, recorded_at)` because
  PostgreSQL requires the partition key in unique constraints — S4);
  timestamps are timezone-aware with `func.now()` defaults; enums are Python
  `StrEnum` + DB check constraints (not native PG enums).
- The derived chain is **trip_sessions → trip_analytics → (route_replay_signatures
  → fraud_flags → fraud_assessments, impression_estimates) → payout_calculations →
  earnings_ledger_entries**; each step stores enough context to be queried
  independently.
- Target-state table additions (billing, notifications, files, audience, jobs)
  are specified in their Part III sections and indexed in §30.

### 7.2 Migration policy **[BUILT]**

- Alembic, 24 linear migrations `0001`–`0024` (extensions → identity/orgs →
  drivers/vehicles → campaigns/creatives → zones → assignments → trip tracking →
  analytics/fraud → impressions → payouts → F7 password management → F7 audit
  indexes → S1 payout v2 → S4 ping partitioning + purge evidence → RM1 payout-day
  allocation → RM3 trip seal protocol + quarantine → seal review hardening →
  immutable payout revisions/bindings/corrections → current fraud assessments →
  indexed route-replay signatures).
  <!-- verified 2026-08-21: ls alembic/versions → 24; alembic heads → single head 0024_fraud_review_holds -->
  (Pre-existing doc drift note: this row still said "12" after S1 shipped
  0013 — corrected here in the S4 commit.)
- `0001` enables `pgcrypto` + `postgis`.
- Shipped migrations are frozen history: schema changes come as **new**
  migrations, never edits to existing ones (per-slice migration tests
  `tests/test_migration_slice*.py` pin the existing chain;
  `tests/test_mvp_hardening.py` pins the single head).
- **[BUILT]** Revision-gated restore: `scripts/db_restore.sh` restores into a
  temporary database, validates the dump's Alembic revision against the
  checked-out head (refusing unknown revisions; older ones need `--upgrade`),
  and only then swaps it into place. API, frontend, and the worker (required
  since S4; its profile exists for quiescing like this) are
  quiesced during the swap; frontend/worker running state is preserved.
  Exercised by a local drill — it is **not** a CI job.

## 8. Frontend architecture

### 8.1 Stack **[BUILT]**

`frontend/` — Next.js **16.2.10** App Router, React 19, TypeScript `strict: true`,
Tailwind **v4** (CSS-first `@theme`), zod, react-hook-form, MapLibre GL +
terra-draw (zone drawing), openapi-fetch + openapi-typescript. Vitest (unit) +
Playwright (e2e). <!-- verified: frontend/package.json, tsconfig.json -->
(`@tanstack/react-query` is declared in package.json but currently unused in
`src/` — its sanctioned adoption path is §27.2.)

### 8.2 BFF pattern — THE invariant **[BUILT]**

**The browser never calls FastAPI directly.** All backend access happens on the
Next.js server. Request flow:

```
1. Browser submits <form> / navigates
2. proxy.ts (src/proxy.ts) — fast-path only: no session cookie on /advertiser|/driver|/admin → redirect /login
   (exception: /driver/manifest.webmanifest stays public — browsers fetch manifests without cookies)
3. Server layout calls requireRole(role) (src/lib/auth/current-user.ts)
   → getCurrentUser() → GET /api/v1/me with the JWT from the httpOnly cookie
   → wrong role redirects to that role's home; no user redirects to /login
4. Server Component / Server Action creates createApiClient(token) (src/lib/api/client.ts)
   → openapi-fetch typed client, baseUrl = API_BASE_URL, cache: "no-store"
   → Authorization: Bearer <token> over the internal network
5. Non-OK responses throw a typed ApiError (src/lib/api/errors.ts) mapped from the
   backend error envelope; auth errors (401/403) route the user back to login
```

Session handling (`src/lib/auth/session.ts`): the backend JWT is stored in an
**httpOnly, sameSite=lax, secure-in-prod cookie** (`mobility_session`), `maxAge`
equal to the JWT's `expires_in`. No localStorage, no client-readable token.
**Sliding session (F7):** the middleware rotates a near-expiry cookie on GET
navigation via `POST /api/v1/auth/refresh` (non-verifying JWT peek in
`src/lib/auth/token.ts`); the driver tracker pings `/driver/keepalive` every
10 minutes while tracking (fail-open). The 12-hour absolute cap is enforced by
the backend; when it lapses, the next `/me` call 401s and the user lands on
`/login` with no redirect loop. Forced password change (`must_change_password`)
is enforced per-request by `requireRole` in every protected server layout.

Rules for agents:
- Backend truth is authoritative: `proxy.ts` and `requireRole` are UX
  conveniences; every proxied call is re-authorized by FastAPI. Never treat a
  frontend check as the security boundary.
- `server-only` imports guard `env.ts`, `client.ts`, `session.ts`,
  `current-user.ts` — keep it that way. Client components receive data via props
  or call Server Actions; they never import the API client.
- Server env (`src/lib/env.ts`, zod-validated): `API_BASE_URL`,
  `SESSION_COOKIE_NAME`, `NODE_ENV`. Nothing backend-related is `NEXT_PUBLIC_`.

### 8.3 Directory layout **[BUILT]**

```
frontend/src/
├── proxy.ts                    # Next middleware (fast-path auth redirects)
├── app/
│   ├── layout.tsx, page.tsx, login/, error.tsx, not-found.tsx
│   ├── change-password/        # forced password change (advertiser/admin) (F7)
│   ├── advertiser/             # portal: layout (requireRole("advertiser")), dashboard,
│   │                           # campaigns list/new-wizard/detail/zones editor/map+heatmap/report
│   ├── admin/                  # console: layout (requireRole("admin")), users, drivers,
│   │                           # vehicles, assignments, fraud, payouts(+rules), traffic,
│   │                           # audit (F7 audit-trail viewer)
│   └── driver/                 # Vantage Driver PWA
│       ├── (portal)/           # guarded route group: layout (requireRole("driver")),
│       │                       # home, assignments, track (GPS tracker), earnings, profile
│       ├── change-password/    # forced driver password change, inside PWA scope (F7)
│       ├── keepalive/          # cookie-rotation GET for the tracking surface (F7)
│       └── manifest.webmanifest/route.ts   # scoped PWA manifest (route handler)
├── components/  (shell/ app chrome, ui/ primitives, charts/, driver/ tab-bar + sw-register)
└── lib/         (api/ client+errors+schema.d.ts, auth/, campaigns/, zones/, map/, fonts, format)
```

Per-surface server actions live next to their routes (`actions.ts` files) —
follow that colocation for new features.

### 8.4 Typed client generation **[BUILT]**

`src/lib/api/schema.d.ts` is **generated, never hand-edited**, from the repo-root
`openapi.json` via `npm run api:types` (openapi-typescript). `npm run api:sync`
pulls a fresh `openapi.json` from a running backend (`localhost:8000`) then
regenerates. See §9 for the drift gate.

### 8.5 Design system **[BUILT]**

- Tokens are Tailwind v4 `@theme` variables in `src/app/globals.css` — "city at
  night" palette (bg `#0a0b0e`, panel/raised/edge surfaces, amber/cyan/green/coral
  signals), panel shadows/glows, `rise`/`pulse-dot` animations. **Single dark
  theme by design** (ops surface). Use tokens, never raw hex in components.
- Fonts (`src/lib/fonts.ts`): **Clash Display** (display) and **Satoshi**
  (UI/body) self-hosted as woff2 in `src/fonts/`; **IBM Plex Mono**
  (data/telemetry) loaded via `next/font/google` — not self-hosted.

### 8.6 Vantage Driver PWA **[BUILT]**

- Installable **scoped** to `/driver`: manifest route handler (name "Vantage
  Driver", `standalone`, portrait, `scope: /driver`) so the driver surface
  installs as its own app while advertiser/admin stay regular web.
- Service worker `public/driver-sw.js`, registered production-only with scope
  `/driver`: cache-first for hashed `/_next/static/` assets, **network-only for
  all navigations and API calls** (authenticated data must never be SW-cached),
  inline offline fallback page. Keep the SW auth-safe — never add API caching.
- Trip tracking (`app/driver/track/trip-tracker.tsx`): geolocation watch buffers
  pings client-side and flushes **idempotent batches** (fresh
  `crypto.randomUUID()` key per batch, every 15s or 20 pings) through a server
  action to `POST /driver/trips/{id}/pings`; failed flushes are re-buffered.
  Screen-on tracking posture per D3/D18 (no native app or background tracking
  in the pilot MVP).

## 9. API contract discipline

**[BUILT]** Three baselines exist and must move together on any contract change:

1. `openapi.json` (repo root) — the committed contract, source for type generation.
2. `frontend/src/lib/api/schema.d.ts` — generated types (`npm run api:types`).
3. `docs/api/openapi.snapshot.json` — pretty-printed, key-sorted snapshot
   (regeneration snippet in README §"MVP Contract Baseline"). Currently
   semantically identical to `openapi.json` (formatting differs by design).

**CI drift gate [BUILT]:** the frontend workflow regenerates `schema.d.ts` from
the committed `openapi.json` and fails on any diff ("Contract drift check" step
in `.github/workflows/ci.yml`). Backend contract tests
(`tests/test_openapi.py`) assert the schema generates with expected paths.

**Rules for agents:**
- A contract change is its own commit that moves **all three baselines** plus the
  backend change that caused it. Never regenerate `schema.d.ts` from anything but
  the committed `openapi.json`.
- Flow: change backend → run backend → `npm run api:sync` (refreshes
  `openapi.json` + `schema.d.ts`) → regenerate the snapshot → commit together.
- Nothing outside `docs/api/` and `openapi.json` is a contract artifact; don't
  invent new baselines.

## 10. Environments & infra

### 10.1 Docker compose topology **[BUILT]**

`docker-compose.yml` services:

| Service | Image/build | Host port | Notes |
|---------|-------------|-----------|-------|
| `api` | repo `Dockerfile` (python:3.12-slim), uvicorn `--reload`, source bind-mounted | **8000** | shared `x-backend-env` anchor; depends on db, redis |
| `worker` | repo `Dockerfile`, `arq app.jobs.worker_entry.WorkerSettings`, source bind-mounted | — (none) | shared `x-backend-env` anchor; depends on db, redis; strict pre-socket Redis config boundary; post-trip pipeline + sweep (§6.5, §14) |
| `db` | `postgis/postgis:16-3.4` | **5433** (compose) → **5434 on this machine** via gitignored `docker-compose.override.yml` (5433 taken by another project) | volume `postgres_data` |
| `redis` | `redis:7-alpine` | 6379 | login-rate-limit counters + arq queue, both disposable (§6.5) |
| `frontend` | `frontend/Dockerfile` (multi-stage node:22-alpine, standalone build, non-root user) | **3100**→3000, **profile `full` only** | `docker compose --profile full up`; local dev normally runs `npm run dev` on 3000 instead |

Local quirks: the db override file is **gitignored** — fresh clones get 5433;
this machine uses 5434. Frontend dev on 3000 can collide with other local
projects (Next will auto-pick another port; the compose profile avoids it by
mapping 3100).

### 10.2 Configuration **[BUILT]**

- Backend: pydantic-settings (`app/core/config.py`) reading env/`.env`;
  `.env.example` at repo root enumerates every knob (JWT, tracking-validation,
  route-analytics, impression, payout, heatmap tunables, `ALLOW_DEMO_SEED`).
  Settings are validated aggressively at startup (positive ranges, ratio bounds,
  env-gated secret/CORS guards). New tunables go through Settings +
  `.env.example` + compose env, not hard-coded constants.
- Frontend: three server-only vars via zod (`API_BASE_URL`,
  `SESSION_COOKIE_NAME`, `NODE_ENV`); local values in gitignored
  `frontend/.env.local`.

### 10.3 CI **[BUILT]**

One workflow: `.github/workflows/ci.yml` (push triggers on every branch subject
to path filters; paths include product code, tests, contracts, deployment and
delivery-control files; matching pull requests use the same path filters).

- Job `backend` (F7): **postgis/postgis:16-3.4 + redis:7-alpine service
  containers**, `pip install -e ".[dev]"` → `ruff check .` → full `pytest` with
  `TEST_DATABASE_URL` and `RATE_LIMIT_TEST_REDIS_URL` set, so the
  service-gated PostGIS and Redis tests actually execute.
- Job `quality`: `npm ci` → lint → typecheck → vitest → **contract-drift gate** →
  build.
- Job `e2e`: boots the **real stack** (compose `api`+`db`+`redis` from
  `.env.example` with `ALLOW_DEMO_SEED=true`, relaxed login rate-limit
  thresholds, `F7_SEED_MAX_TRIPS_PER_DAY=1`, waits for `/api/v1/health`,
  `alembic upgrade head`, `python -m app.seeds.demo`), then Playwright against
  it in two projects (`chromium` desktop + `mobile-chrome` Pixel 7).

### 10.4 Deploy **[BUILT / deferred staging]**

- **[BUILT]** Production images exist for both tiers (root `Dockerfile`;
  `frontend/Dockerfile` standalone output, non-root). No deployment target is
  wired up.
- **[BUILT]** `docker-compose.production.yml` overlays `docker-compose.yml` to
  provide a provider-neutral production-style topology: only Caddy publishes
  80/443, data services stay on an internal network, application containers
  have a separate non-published egress bridge and health-gated startup,
  migrations are an explicit one-shot profile, and
  the mandatory worker uses a profile only for deliberate operational
  quiescing. `staging.env.example`,
  `Caddyfile`, and `scripts/release_smoke.sh` define the operator boundary.
- **[BUILT] (F7)** Database backups (`scripts/db_backup.sh`, custom-format
  dumps, 14-dump retention) and temp-DB restore verification with an Alembic
  revision gate (`scripts/db_restore.sh`); Sentry browser DSN passed as a
  Docker build arg (`NEXT_PUBLIC_SENTRY_DSN`); backend/frontend `SENTRY_DSN`
  runtime knobs, inert when empty.
- **[PLANNED-F7 → deferred]** Staging deploy did **not** ship: staging is
  research only (`docs/staging-options.md`), gated on an explicit project-owner go-ahead (deploys are never autonomous).
- Target production topology: §25.

## 11. Testing strategy (current)

**[BUILT]**

| Suite | Where | Count (verified 2026-07-20) | Gate |
|-------|-------|--------------|------|
| Backend pytest | `tests/` (35 files) | 209 test functions <!-- verified: grep -ch "def test_" tests/*.py summed → 209 --> | CI `backend` job (postgis+redis services) + local |
| Frontend unit (vitest) | `src/**/*.test.ts(x)` | 32 cases in 7 files | CI `quality` job |
| Frontend e2e (Playwright) | `frontend/e2e/` (6 specs) | 48 project-expanded tests (2 projects; a few are project-scoped) <!-- verified: npx playwright test --list → 48 in 6 files --> | CI `e2e` job, real seeded stack |

- **Postgres-gated skips:** backend tests requiring PostGIS skip unless
  `DATABASE_URL` starts with `postgresql+asyncpg://` (`tests/conftest.py`); the
  rest run on SQLite via the geometry `TEXT` compilation shim (§7.1). Don't write
  PostGIS-dependent assertions in un-gated tests.
- Migration-slice tests pin the frozen migration chain (§7.2).
- e2e runs against demo-seeded data — keep the demo seed deterministic; e2e
  fixtures depend on it. (F7 froze this as `SEED_VERSION=slice_12_v1` legacy
  objects plus the `f7_rich_v1` namespace with lifecycle-classed, append-only
  trips; `F7_SEED_MAX_TRIPS_PER_DAY` density defaults to 2 locally, 1 in CI as
  a strict key subset.)
- The contract-drift gate (§9) is a test in spirit: contract moves fail CI.
- Target-state testing additions: §28.

## 12. Security architecture (current)

### As built **[BUILT]** (includes the F7 hardening layer)

- Bearer JWT (HS256, `{sub, exp, iat, auth_time, sv}`), 60-min sliding lifetime
  under a **12h absolute cap**, argon2 passwords, min length 12 — full detail
  in §6.3.
- **Revocation:** password change bumps `session_version`, rejecting every
  outstanding token for that user on the next request. Legacy sv-less tokens
  remain valid until their own `exp` (deliberate, bounded — §6.3).
- **Forced password change:** admin-created users are 403-gated to the
  change-password flow (`/change-password`, `/driver/change-password`).
- **Login rate limiting:** Redis Lua reserve/refund — per-account 5/15 min
  (primary control), per-IP 150/5 min, global 250/5 min, **fail-open** if Redis
  is down (R3). With header trust off, FastAPI buckets by its socket peer, so
  all BFF-relayed logins share one IP bucket — the runbook documents the
  resulting flood-lockout trade-off and the trusted-edge preconditions
  (`LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER` + relay + CIDR allowlist) that
  must ALL hold before honoring `X-Client-IP`.
- Browser token handling: httpOnly/sameSite=lax/secure-in-prod cookie; JWT never
  readable by client JS; BFF keeps FastAPI off the public internet (§8.2).
- Role enforcement server-side on every request via dependency guards; frontend
  role checks are UX only.
- Suspended/disabled users blocked at login and per-request.
- Startup guards: non-local envs must override the default JWT secret; wildcard
  CORS refused outside local/test.
- Audit trail on mutating flows + auth events + admin audit API/UI (§6.4.9).
- **Error tracking:** Sentry hooks on FastAPI (`app/core/observability.py`) and
  Next.js (server `instrumentation.ts`, browser `instrumentation-client.ts`) —
  inert without a DSN, `send_default_pii=False`/`sendDefaultPii:false`, tracing
  off. Browser DSN is build-time (`NEXT_PUBLIC_SENTRY_DSN`); servers are
  runtime.

Security architecture beyond F7 (webhooks, uploads, production PWA, later native apps, privacy,
password reset): the relevant Part III sections.

---

# PART III — TARGET ARCHITECTURE

Everything in this part is **[TARGET]** unless tagged otherwise. Shapes are
decided; parameters marked [OPEN] await client answers (§33). Nothing here is
built ad hoc — each numbered area becomes one or more planned build phases (§31),
each of which goes through the plan → adversarial review → reconcile SOP
(independent fresh-context review, findings reconciled by the orchestrator
before implementation).

## 13. Target system overview

```
   Advertiser browser        Admin browser          Driver phone
        │                        │                 ┌───────────────────────┐
        │                        │                 │ Cardvert PWA          │
        │                        │                 │ screen-on pilot       │
        │                        │                 │ standalone install    │
        └───────────┬────────────┘                 └───────────┬───────────┘
                    │ HTTPS (cookie session)                   │ cookie
        ┌───────────▼─────────────────────────────────────────▼──────┐
        │            Next.js BFF (unchanged pattern)                  │
        └───────────┬─────────────────────────────────────────────────┘
                    │ bearer, internal
   ┌────────────────▼────────────────────────────────────────────────────────┐
   │                         FastAPI modular monolith                         │
   │  /api/v1/{admin,advertiser,driver,auth,me,health}   (existing)          │
   │  /api/v1/webhooks/*  ← signature-auth, payment/messaging callbacks §15.4│
   │  services/  ← same business logic serves API, worker, CLI (P4)          │
   │  adapters/  ← payments · disbursement · messaging · storage  (P5)       │
   └───────┬──────────────────────┬──────────────────────────────┬───────────┘
           │                      │ enqueue / cron               │ port calls
   ┌───────▼────────┐   ┌─────────▼─────────┐   ┌────────────────▼────────────────┐
   │ PostgreSQL 16  │   │ Worker (arq) §14  │   │ External services               │
   │ + PostGIS      │◄──┤ TRIP PIPELINE     │   │ • Paystack/Flutterwave [OPEN Q3]│
   │ source of      │   │ (analytics→fraud→ │   │ • WhatsApp/SMS/email providers  │
   │ truth (P2)     │   │  impress.→payout) │   │ • S3-compatible object storage  │
   │ + new domains: │   │ payout release    │   │   (creatives, KYC docs, photos) │
   │ billing, files,│   │ retention purge   │   │ • Map tiles (MapTiler [OPEN])   │
   │ notifications, │   │ notification send │   │ • Sentry (both tiers)           │
   │ audience       │   │ budget/activity   │   └─────────────────────────────────┘
   └────────────────┘   │ sweeps, webhooks  │
                        └─────────┬─────────┘
                          ┌───────▼────────┐
                          │ Redis 7        │  rate limits (F7) + queue transport
                          │ disposable (P2)│  cache only — never a source of truth
                          └────────────────┘
```

What changes vs today: **one new runtime component** (the worker), **one new
endpoint namespace** (`/webhooks`), **four new domain areas in Postgres**
(billing, files, notifications, audience), and **adapters** for external
vendors. Everything else — BFF, contract discipline, services layer, role-prefix
API, PostGIS analytics chain — is preserved as built.

## 14. Background processing substrate

### 14.1 Decision

Add **one worker process** running **[arq](https://arq-docs.helpmanual.io/)**
(async Redis job queue with built-in cron) as a new compose service/container,
executing jobs defined in `app/jobs/*` that call the existing service layer.

### 14.2 Why (and why not the alternatives)

The target product cannot remain request/response-only. First and most
load-bearing: **post-trip computation**. Today analytics → fraud → impressions →
payout are synchronous **admin-triggered POSTs, per trip** (§6.5) — workable for
demos, impossible at pilot scale (hundreds of trips/day would each need three
manual admin actions before any downstream sweep can see them). The worker's
first job is the **trip-processing pipeline**: on trip **seal** (RM3 — end alone
never triggers money), enqueue
compute-analytics → detect-fraud → estimate-impressions → calculate-payout for
that trip, backstopped by a DB-derived sweep for sealed-but-uncomputed trips
(rule 2 below). The existing admin endpoints remain as recompute/override
tools. Every other automated consumer (release sweeps, holds, strikes, budget,
activity) reads facts this pipeline produces — without it they are blind.

Also time-driven or must-not-block-a-request: payout release schedules
(Q22), NDPR retention deletion (Q31), minimum-activity sweeps (Q20), budget
alerts, notification dispatch (Q34), webhook processing (§15.4), and
virus scanning (§19).

| Option | Verdict |
|--------|---------|
| **arq** | **Chosen.** Async-native (matches SQLAlchemy-async codebase — jobs reuse services without sync bridges), Redis-backed (already provisioned), has cron, tiny API surface, no new infra. |
| Celery + Redis | Mature but sync-first (async services would need wrappers), heavy config surface, larger operational footprint than the pilot needs. |
| APScheduler in-process | No isolation — scheduler dies with the web process, doubles on 2 replicas, ties job load to API latency. Rejected. |
| Postgres-only cron (pg_cron / external cron hitting endpoints) | Keeps logic out of the service layer or turns endpoints into job runners; poor retry/observability story. Rejected. |

### 14.3 Rules (binding on every job)

1. **Jobs are idempotent and re-runnable** (P9). A job killed mid-run and retried
   must not double-move money or double-send messages — use DB state transitions
   (`WHERE status = 'pending'` guards) and unique keys.
2. **Scheduled sweeps derive work from Postgres, not Redis** (P2). Cron fires
   "find all ledger entries due for release and release them" — if Redis loses
   the queue, the next sweep catches up. Enqueued one-off jobs are allowed only
   as latency optimizations on top of a sweep that would eventually do the work.
3. **Jobs contain no business logic.** `app/jobs/*` files are thin: fetch due
   work, call `app/services/*`, record the outcome. Same logic must be callable
   from a request or CLI.
4. **Every job run is observable**: structured log line with job name, duration,
   items processed, and errors to Sentry. Long-term job history lives in logs,
   not a DB table (avoid unbounded `job_runs` growth at this scale).
5. **Time comes from the DB clock or an injected `now`** — jobs must be testable
   with frozen time.

### 14.4 What this does NOT change

No WebSockets/SSE (P8). Frontend "liveness" (notification badge, fraud queue
counts) is polling — TanStack Query with modest intervals (§27.2). The no-realtime
constraint (§3) stands in the target state; revisit only post-pilot with a
measured need.

### Relation to current code

Purely additive: new `worker` compose service, `app/jobs/` package, arq
dependency. The substrate and its first consumer, the trip-processing pipeline
(§14.2), are now **[BUILT]** with each §14.3 rule implemented explicitly:
named unique constraints, savepoint convergence, source fingerprints, and
ledger repair make reruns idempotent (rule 1); Postgres alone defines due work,
while Redis stores only a disposable traversal cursor and the trip-end enqueue
remains a latency optimization (rule 2); wrappers delegate business work to
services (rule 3); structured per-run logs, stackful failures, and explicit
Sentry capture cover rule 4; and one DB-clock timestamp is injected through the
three processing stages for rule 5. Its
payout stage dispatches per the governing rule row's model — `payout_v2`
(D2 hourly pay, §16.1 [BUILT] S1) or frozen `payout_v1` history. §24's data
lifecycle is **[BUILT]** (S4): three daily crons — partition premake,
coverage alarm, retention purge — with logic in
`app/services/data_lifecycle.py` per rule 3. Remaining consumers — §15
(webhooks), §16.2/16.3 (release/disbursement), §20 (notifications) — remain
[TARGET]. Redis remains disposable.

## 15. Money in — billing, payments, invoicing

Q1–Q3, Q14, Q24 and Q28 are client-confirmed by D18/D20. The domain is buildable:
Cardvert prepares a custom quotation for every campaign; a package catalogue is
not launch scope. Standard
customers pay in full before production while specifically approved corporate
customers may use recorded credit terms; bank transfer and online checkout are
both supported; invoices are generated in-platform; customer prices are
VAT-inclusive with the included net and VAT itemised. The registered-company TIN/address/invoice
wording and the selected online-payment provider remain external live-use
inputs, not product questions.

### 15.1 Domain boundary

New service module `app/services/billing.py` + models in
`app/models/billing.py`. Nothing outside this module computes what an advertiser
owes. Campaign "cost summary" reporting (built, presentation-side) stays
presentation-side and reads billing facts once they exist — the current reports
must not grow invoicing logic.

### 15.2 Data model (shape)

| Table | Purpose |
|-------|---------|
| `commercial_terms` | Immutable accepted custom-quotation snapshot: quote reference, versioned line items, production scope, payment class (`standard_prepaid` \| `approved_corporate_credit`), due dates/credit approval, accepted-by and accepted-at. External quotes/deals are entered after acceptance rather than silently inferred; a launch package catalogue is not assumed |
| `invoices` | What an org owes for a campaign/period: line items (JSONB), currency, explicit net, VAT rate/amount and gross totals, status `draft → issued → partially_paid → paid → void`, issued/paid timestamps, human-readable invoice number, and the accepted commercial-terms revision. Customer surfaces default to the VAT-inclusive gross while itemising the included net and VAT; totals become immutable when issued |
| `payments` | Money received against an invoice — **N payments per invoice**: amount, method (`manual_transfer` \| `gateway`), provider + provider reference, status, `recorded_by_user_id` for manual entries. Standard production authority requires confirmed allocations covering the full required amount; an approved corporate-credit snapshot may instead authorise production under its recorded terms |
| `payment_events` | Raw webhook/event log from gateways: provider event id (**unique** — replay protection), payload, processing status |

The accepted-terms snapshot fixes the standard 24-hour production wait. A
separate append-only production-authority event chain records either
`standard_window_elapsed` or `advertiser_expedited_waiver`, the advertiser's
request and waiver acceptance timestamps, the actor and accepted wording
version, and the actual `production_started_at`. The waiver evidence is
immutable and auditable; authorisation and production start are distinct facts.

Rules: amounts are `Decimal` (strings on the wire, P6); invoices are immutable
once issued (corrections = credit-note-style new rows); every state change
audited (§6.4.9).

### 15.3 Provider adapter (P5)

`app/adapters/payments/` defines one interface (`create_checkout`,
`verify_transaction`, `parse_webhook(payload, signature) → event`) with
implementations per provider (Q3 adopts gateway + manual; Paystack vs
Flutterwave remains a provider/account parameter) plus a `manual` no-op used
at pilot. Services import the interface, never a vendor SDK. Provider selection
via Settings.

**Pilot contract (Q2/Q3):** manual bank transfer and online checkout use the
same canonical receipt/allocation contract. Funding derives only from confirmed
allocations. Standard customers must be fully funded before production starts,
and production must also have authority under §15.6's standard-wait or
expedited-waiver rule;
the approved-corporate exception requires an immutable credit approval, limit,
due date and accepted terms and remains bounded by RM12. Live checkout waits for
the client-selected provider account, credentials and budget.

### 15.4 Webhooks — new endpoint namespace

`/api/v1/webhooks/{provider}` (POST): the only **machine-caller** endpoints
(the JWT-less surface otherwise remains `/auth/*` and the health checks).
Rules, binding for any future webhook (payments, messaging delivery receipts):

1. Authenticate by **provider signature verification** in the adapter; reject
   unsigned/invalid immediately (401, no envelope leakage of internals).
2. Handler does exactly: verify → insert an event row in the **owning domain's
   event table** (payments → `payment_events`; messaging delivery receipts →
   delivery-status updates on `notifications` keyed by provider message id) —
   idempotent on the provider's event id; duplicate → 200 no-op → enqueue
   processing job → 200. **No business logic in the webhook request path** —
   processing happens in the worker (§14) so provider retries and our
   processing are decoupled.
3. Webhook endpoints are excluded from the role-prefix invariant (§6.2) but
   inherit every other convention (error envelope, request IDs).
4. These endpoints must be reachable from the public internet in production —
   the deploy topology (§25) exposes exactly `/api/v1/webhooks/*` through the
   edge, nothing else of FastAPI. <!-- BFF invariant is about browsers; machine callbacks are a distinct, signature-authed channel -->

### 15.5 Budget enforcement

Today budgets are recorded, never enforced. Target: a worker sweep applies the
policy — auto-pause at 100% / alert at 80% is the proposed default. **The
final rule is [OPEN] but maps to no numbered v2 question** (Q9's mid-flight
change rules are adjacent) — confirm it with Somto directly and record it in
`decisions-log.md`. **"Spend" is a billing computation** (§15.1's
boundary applies: driver payout facts are *cost* in driver naira, not the
advertiser's price — under D2 + Q1 they diverge) — the sweep calls
`services/billing.py` for spend-vs-budget; until billing exists, any pilot
proxy (e.g. payout-cost sums) must be labelled as such in the UI. Enforcement =
a status transition through the existing campaign status machinery +
notification, never a hard delete.

### 15.6 Cancellation and refund eligibility (Q24)

The refund-eligibility clock starts at the **first confirmed cash allocation
that authorises production**. Standard production waits until the exact
24-hour boundary has elapsed. Before that boundary, production may start only
when the advertiser explicitly requests expedited production and accepts an
immutable, versioned and audited refund waiver. Refund eligibility then ends
when expedited production **actually begins**, not merely when the waiver is
accepted. Without a waiver, a cancellation before production authority may
create an append-only settlement/refund; after the standard boundary or actual
waived production start, no customer refund is due. Corporate-credit work with
no cash allocation has no refund event: its termination is settled under the
accepted credit terms. One idempotent command sets the immutable financial
cutoff and every ingestion, classification, recompute, release and settlement
path honours it (RM13). Provider fees, statutory treatment and any exceptional
admin correction remain explicit settlement lines, never edits to an issued
invoice or receipt.

### Relation to current code

Additive domain. Preserve: campaigns, reports, cost summaries as built. The
campaign creation wizard gains one custom-quotation and accepted-terms step
and records externally agreed deals before activation — extend the wizard,
don't fork it.

## 16. Money out — versioned payout, release, disbursement

Q4, Q5, Q22 and Q27 are client-confirmed by D18. D4's daily cap remains. D18
changes the zone treatment and therefore requires a new immutable formula
version; it does not rewrite calculations already stamped `payout_v1` or
`payout_v2`.

### 16.1 Payout engine v2 (D2, D4) **[BUILT]**

Delivered in S1 (D8 defaults; Q4/Q5 adopted): migration `0013`, eligibility
classifier (`app/services/payout_eligibility.py` — pure interval timeline:
`moving | stationary(+grace) | gps_gap | out_of_area | out_of_window |
teleport | low_accuracy`, invariant Σ(eligible+excluded) == session duration),
`payout_v2` computation in `services/payouts.py` (integer payable seconds,
cap-before-price, one `ROUND_HALF_UP` 2dp quantization per ledger amount),
per-rule formula dispatch, transaction-scoped `pg_advisory_xact_lock` cap
concurrency, inputs fingerprint (rate, cap, eligibility params, ping set,
campaign-zone state), admin recompute-day true-up, driver trip-breakdown
endpoint + PWA screen, and reversal/adjustment netting in every summary
(§16.2's same-change mandate). payout_v2 calculations are **write-once per
trip**: input drift never auto-recomputes money — the admin endpoint flags it
(409 stale) and the audited recompute-day true-up is the only corrective path.

- New formula version **`payout_v2`** computing: `hourly_rate × verified_payable_hours`,
  where payable hours are derived from GPS-verified classified intervals under
  the Q5 eligibility rules (movement, geofence, campaign window, signal
  hygiene) and capped per campaign/driver/day (D4).
- **Trigger:** v2 calculations are produced by the worker's trip-processing
  pipeline (§14.2) automatically on trip end — not by admin action. The admin
  "process trip" endpoints stay as recompute/override tools.
- **Cap concurrency:** the daily cap is a cross-trip invariant, and §25.3
  sanctions concurrent workers — two same-driver trips computed concurrently
  must not jointly exceed the cap. Rule: payout computation for a trip takes a
  **Postgres advisory lock on (driver_profile_id, campaign_id, Lagos-day)** for
  the read-remaining-cap → write-calculation critical section. **A trip
  spanning Lagos midnight bills each day separately** *(amended 6 Aug 2026 —
  RM1/D14; it previously billed the whole trip to the day it started, which
  contradicted D4's calendar-day cap)*: `classify_session` cuts the timeline at
  every Africa/Lagos midnight and returns `eligible_seconds_by_day`, the
  calculation takes **one lock per touched day in sorted order** (deterministic
  ordering is what keeps concurrent workers deadlock-free), caps each day
  against its own allowance, and persists the split in
  `payout_calculations.payable_seconds_by_day` — which is what cap accounting
  and recompute-day read back, so a trip's consumption is reproducible rather
  than re-derived. Recomputing an
  earlier trip never **automatically** reallocates cap already consumed by
  later immutable calculations (P6) — input drift is flagged for admin review
  (409 on the admin recompute surface); the **audited admin recompute-day
  true-up** (`POST /admin/payouts/recompute-day`, S1) is the sanctioned
  reallocation path: it re-runs the day's allocation under the same advisory
  lock and posts append-only differential entries (`adjustment` up, positive
  `reversal` down) — never edits.
- `campaign_payout_rules` gains nullable v2 fields (`hourly_rate_naira`,
  `daily_payable_hours_cap`, verification parameters); a rule row is valid for
  exactly one model (v1 fields XOR v2 fields — DB check constraint). The v1
  rate columns are currently `NOT NULL`, so the v2 migration **relaxes their
  nullability** (values on existing rows are frozen, never rewritten) — history
  must stay reproducible.
- **Day boundary:** the D4 daily cap is computed over the **Africa/Lagos
  calendar day** (the operating market's day, and what a driver's offer screen
  shows) — not UTC, not a rolling 24h window. Pin this in code and tests.
- `payout_calculations` rows stamp `payout_v2`; v1 rows are immutable history
  (P6). Reports render whichever version a row carries — no UI may assume one
  model (D2 build implication). **Migration scope note:** `payout_calculations`
  itself needs relaxing too — its v1 component columns are `NOT NULL` with
  non-negativity checks, and `impression_estimate_id`/`trip_analytics_id` are
  `NOT NULL` (v2 rows can still link an estimate — the §14.2 pipeline produces
  one before the payout step — but the v1 component columns must go nullable).
- The daily cap check needs per-driver-per-campaign-per-day aggregation — this
  is a service-layer computation over `trip_sessions`/`trip_analytics`, not a
  new table, until measured cost says otherwise (P10).
- Fraud interaction: under D5, severity multipliers become secondary; the
  primary control is **holds** (§17). v2 computes gross pay; holds gate its
  release.

**Preserve / replace:** v1 and v2 stay as immutable history. D18 supersedes
v2's `out_of_area = unpaid` product rule for new accepted terms; it does not
reprice old work. The admin payout-rules editor UI ([BUILT], F6) is refactored
to edit the formula version selected by an effective-dated rule row.

#### Built formula: `payout_v3` (D18/Q4/Q5)

`payout_v3` keeps fixed hourly pricing, verified time, the Africa/Lagos daily
cap, write-once calculations, concurrency locks, fingerprints and audited
true-ups from v2. It changes the rate resolved for each valid interval:

- valid campaign time outside the primary/premium targeting zone earns the
  accepted **base hourly rate**;
- valid time inside the primary/premium zone earns the accepted **premium
  hourly rate**;
- time outside the campaign window, inside an explicit exclusion/no-service
  area, or invalidated by signal, teleport, fraud, stationary or other
  configured eligibility rules remains unpaid. D22 supplies the versioned
  stationary sub-window policy for new payout-v3 acceptances.

Each accepted offer snapshots the effective-dated base rate, premium rate,
zone revision, eligibility revision and cap. Each classified interval stores
its resolved tier/reason, and the inputs fingerprint includes those revisions.
The calculation and ledger rows stamp `payout_v3`; recomputation never applies
new commercial terms retrospectively. **[BUILT — MNY-06A/B/C]:** immutable
effective-dated revisions replace in-place rule mutation; assignment acceptance
persists the complete resolved eligibility values and frozen premium/exclusion
geometries alongside rates and cap. Valid time outside the premium geometry is
base-tier time, premium geometry is premium-tier time, and exclusions/invalid
time remain unpaid. The shared Lagos-day cap fills chronologically across v2/v3,
and persisted base/premium components reconcile exactly to the once-quantized
ledger amount. Retroactive changes run only through a projected correction
order with a separate approver, stale-fingerprint recheck, mandatory release
time for positive deltas and idempotent execution. The driver breakdown reads
the latest valid non-voided authoritative correction and explains formula,
tier, seconds, frozen effective rates and amounts.

**[BUILT — PKG02-C1]:** migration `0026` extends the immutable payout-v3
binding with the nullable campaign payment window accepted by that assignment.
Acceptance and revision publication share one campaign-scoped transaction lock
and PostgreSQL wall clock, so the effective revision/window boundary cannot
split across application and database time. Calculation, staleness, correction
fingerprints and persisted payout/differential metadata consume the frozen
window; legacy bindings without truthful window provenance fail closed. Live
window edits still affect payout-v2 only. Populated financial authority in
`0018`–`0021` and accepted `0026` windows blocks destructive downgrade.
Adjacent-day corrections lock all overlapping trips in stable UUID order before
their distinct day-cap locks, then restore chronological cap allocation.

**[BUILT — FND-02A/B, D22]:** the `stationary-rd-v1` detector evaluates
contiguous 120-second elapsed windows using deterministic endpoint
interpolation inside valid GPS segments. Net displacement at or below 25 metres
is stationary; two adjacent stationary windows confirm and backdate, one
above-threshold window releases and backdates, and a GPS gap resets/re-anchors
the detector. Contaminated windows cannot confirm or release. Its ranges union
with the legacy 200-metre/300-second long-stay detector before the existing
240-second whole-trip grace is consumed once. New assignment acceptances freeze
the complete common and rolling parameters plus detector marker into the
payout-v3 binding and fingerprint; unknown markers fail closed. Payout-v1/v2
metadata and fingerprints remain immutable. Calculations/corrections persist
the stationary reason and compact detector evidence, and driver/admin views
explain the exclusion. D22's values are provisional: later calibration may
create a new effective revision for future acceptances only.

### 16.2 Release scheduling (Q22)

Ledger entries post as `pending` (built). The D18 release policy makes a
current, successfully assessed **clean** earning available without a blanket
seven-day delay; the configured weekly cadence controls disbursement batching,
not earned-status approval. A suspected or flagged earning remains `pending`
for admin approve/decline, with a seven-day review SLA and escalation. Reaching
day seven never auto-releases an unresolved earning. One worker sweep (§14.3.2)
applies RM8's authoritative assessment/hold predicate, the review transitions
serialize with release, and the cadence/SLA live in Settings with no hard-coded
weekday.

**Post-release flags:** analytics can be recomputed at any time (built admin
endpoints), so a flag can be raised **after** its trip's earnings are
`available` or `paid`. The hold predicate can no longer act; the rule is:
the flag-review sweep detects flags on already-released entries and surfaces a
**reversal recommendation** in the admin fraud queue (no new table: the flag
row itself is the recommendation — the affected released entries are derivable
from its trip). A named admin confirms, which posts a typed `reversal` ledger
entry. **Build honesty:** only the enum value `reversal` exists at the pin —
no code creates or handles it, `ck_earnings_ledger_entries_amount_non_negative`
forbids negative amounts, and `driver_earnings_summary` sums amounts with no
netting by type (a naive positive reversal row would *increase* the balance).
The sanctioned design: keep amounts non-negative — reversal entries carry
**positive amounts with subtract-by-type semantics**, and every balance/summary
computation (`driver_earnings_summary`, campaign cost summaries) **nets
reversal-typed entries as negative**, shipped together with tests in the same
change. **[BUILT] (S1):** the netting shipped with the first reversal-creating
code (recompute-day) per this section's same-change mandate — sign convention
applies per balance: a differential entry inherits the corrected trip's
trip_payout entry status, pending/available buckets net reversals negative,
`voided` stays an unsigned informational sum, and campaign summaries carry a
separate `ledger_net_total` aggregate (differential entries have no
`payout_calculation_id`, so calc-joined sums can never see them). A netted
balance may go negative; it offsets against future earnings — never a
collections flow. Q22 authorises named-admin audited corrections, not automatic
clawback; once cash has been paid, RM11's carry-forward debt contract applies.
The release sweep itself remains [TARGET] (MNY-03A).

### 16.3 Disbursement (Q27)

- **Sensitive payee data (D17):** MNY-10A introduces one
  `app/adapters/crypto/` provider boundary (`encrypt`, `decrypt`, `rotate`) for
  verified bank-account values and later KYC/national identifiers. The pilot
  provider uses authenticated per-record envelope encryption with a required,
  env-supplied typed-Settings KEK and no default. Ciphertext records algorithm
  and key version and authenticates tenant, record and field identity as
  associated data. W2-02D adopts the selected KMS/vault custody through this
  same port and supplies rewrap/re-encryption; it must not introduce a second
  ciphertext schema. Plaintext values are excluded from list APIs, logs, audit
  payloads, exports, errors and fallback storage.
- Pilot (Q27/D18): **automated bank transfers through an approved provider**,
  behind `app/adapters/disbursement/`. RM10's finality contract is binding:
  `draft → reserved → submitted → reconciled/completed | failed | void`;
  reservation is atomic; each line freezes the payee/account/amount and
  instruction fingerprint, carries a unique idempotency key/provider transfer
  reference, and reconciles individually from a signed webhook or verified
  poll before any paid finality. Maker-checker approval is required before
  provider submission, retries reuse the same idempotency key, and a batch-level
  assertion never marks cash paid. `EXT-DISBURSEMENT-PROVIDER` (provider,
  account, sandbox, signing/webhook credentials and production approval) blocks
  financially effective submission, not provider-neutral development/tests.
- **Payee abstraction (Q23):** the questionnaire promises the client that fleet
  ownership (vehicle owner ≠ driver) can be added later **without rework**.
  Honouring that: batch line items and bank/BVN details attach to a **payee**
  reference that at pilot is always the driver profile — so a later
  `fleet_owner` payee type extends the enum instead of reworking the money-out
  path. Do not scatter `driver_profile_id` assumptions through disbursement
  code.
- Q26/Q27 require verified bank-account capture for the pilot. The concrete
  bank-verification provider may share the approved provider contract or use a
  separate adapter, but it may not bypass the encrypted payee snapshot or
  reconciliation rules.
- Ledger corrections (Q22): adjustments/reversals are **new typed ledger
  entries**, never edits (P6). RM6 requires a projected correction order,
  named adjuster, separate approver, mandatory reason and complete old/new
  audit; post-payment corrections follow RM11.

## 17. Fraud review & trust workflow (D5)

Q21 and Q22 are confirmed by D18. Shape fixed by D5 and RM8:
**hold-and-review**. Automatic strike/suspension policy remains outside the
adopted MVP rule unless separately recorded.

**[BUILT — MNY-08A]:** every sealed trip now converges on one persisted current
assessment attempt (`pending | clean | flagged | error`). Formula, analytics and
canonical current-flag inputs are fingerprinted; the sweep also compares a
flag-count/update watermark so later detection or review-state changes make an
assessment due again. Only matching `clean`/`flagged` results are
successful-current; `pending`, `error`, stale inputs and evaluation failures
  remain fail-closed. MNY-08B supplies the authoritative hold below; MNY-03A
  still owns release.

**[BUILT — MNY-09A]:** canonical absolute-payload and time-shift-normalized
route hashes now produce explainable cross-trip/account replay evidence without
putting raw coordinates or timestamps in flags. Same-trip retries converge;
same-driver repeats alone do not flag. Each normalized group keeps one latest
cross-account review candidate, including mixed exact/time-shift matches and
member departures. Old/new group transitions use sorted transaction advisory
locks, while counts/latest selection, bounded evidence samples and cleanup stay
database-side. Detector/config/analytics drift makes the assessment due again,
  and evaluation failure remains fail-closed. This detector does not create an
  independent money rule.

**[BUILT — MNY-08B]:** migration `0024` implements the exact serialized
`open → acknowledged → confirmed | dismissed` lifecycle on `fraud_flags` with
reviewer, review-time and bounded mandatory terminal-note evidence. The
non-terminal unique index covers `open`, `acknowledged` and `confirmed`, so
re-detection cannot fork a reviewed hold. One shared `hold_active` predicate
holds those same three states; only `dismissed` releases, and every impression,
payout and later release consumer imports that contract. Ordinary review/money
operations take a shared reconciliation gate and the trip scope; cross-trip
replay reconciliation takes the exclusive gate, locks every affected trip in
sorted order, then locks fingerprints and flag rows. Thus review, detection and
money snapshots cannot race across group members. Exact transition retries are
idempotent, conflicting retries and direct open-to-terminal resolution fail,
and the state change plus audit event is atomic. The acknowledge/resolve admin
endpoints and typed console expose bounded evidence and terminal reviewer
context. The payout-v1 minimum floor is gated off whenever any active hold
exists. Release still additionally requires a current successful assessment
and remains MNY-03A work: seven-day expiry will escalate but never auto-release.

**[BUILT — MNY-08C]:** migration `0025` adds an owner-only, one-per-flag
dispute record and typed, transactionally deduplicated in-app notices for hold
raised, review resolved and staff reply events. Driver projections expose only
allowlisted reason/status/outcome fields; raw detector evidence, matched
identities and internal review notes remain private. Exact create/reply retries
converge, conflicting retries fail, and review resolution writes at most one
notice and audit event under the existing authoritative flag lock. Confirmed
and dismissed outcomes remain visible, staff replies are distinct from review
notes, and disputed flags retain identity/evidence through detector
reconciliation. Corrected driver explanations source eligible seconds and
excluded reasons from the same newest authoritative recompute; malformed newest
provenance does not fall through to stale history. Q34 keeps driver WhatsApp as
a manual operations channel, not the authoritative dispute record.
- Strikes/escalation (auto-suspension after N high-severity flags) is **not**
  part of the adopted Q21 MVP rule. If later approved, start with reviewable
  recommendations; never infer automatic suspension from hold-and-review.
- Severity multipliers (0.9/0.7/0.25) remain configurable but secondary (D5).
  The prior minimum-payout-floor loophole is closed: a floor applies only when
  the authoritative active-hold count is zero.

**Preserve:** detection engine (`trip_analytics` → `fraud_flags`) as built.
**Extend:** flag model + admin endpoints + release predicate. **Replace:**
nothing.

## 18. Approval workflows

Q6, Q15, Q17 and Q18 are client-confirmed. Implementation remains [TARGET] and must
honour RM12/RM13's funded-liability, evidence and atomic-activation contracts.

- **Campaign approval:** insert `pending_review → approved` **between `draft`
  and `scheduled`** in the existing campaign status enum
  (`draft | scheduled | active | paused | completed | cancelled`) + transition
  maps (backend enum & checks; frontend `src/lib/campaigns/status.ts`) — a
  campaign is approved first, then scheduled/activated; nothing unapproved may
  reach `scheduled`. Advertiser submits; admin approves/rejects with reason;
  every transition audited. Extend the enum — **never** a parallel
  `is_approved` flag.
- **Creative approval:** same pattern on `campaign_creatives.status`
  (`pending_review → approved | rejected`), tied to upload (§19) — an
  unapproved creative blocks scheduling/activation per Q6/Q18 and RM13.
- **Activation gate (Q15/Q17):** a campaign-assignment may require evidence
  before the vehicle starts earning — installation photo(s) uploaded by the
  configured pilot operator/driver role, reviewed by admin, recorded against
  the assignment (§19.3). Exact uploader/views/renewal values are settings/
  operations inputs, not a different lifecycle.
  Gate = predicate on the existing assignment activation transition, not a new
  state machine.
- Admin UI: one **approvals queue** section listing pending campaigns,
  creatives, and activation evidence (§27).

## 19. Files — storage, creative pipeline, evidence, KYC docs

Q18 and Q26 adopt in-platform creative upload and the pilot KYC checklist.
Q32 adopts client-owned infrastructure but the concrete account/provider
action remains external. The provider-neutral file architecture builds now;
live use waits for storage/KMS/scanner choices and required legal wording.

### 19.1 Storage adapter

`app/adapters/storage/` — S3-compatible interface (`put/get/delete/presign`),
backed by MinIO in local compose and the client account's selected object store
in staging/production (Q32; S3, GCS-compatible, or R2). **No files on
container filesystems, no files in Postgres.**

### 19.2 Upload flow (one pattern for all file kinds)

1. Client asks its server action → backend `POST .../uploads` for a **presigned
   POST** (not PUT: only POST policy conditions enforce
   `content-length-range` and content-type server-side; presigned PUTs cannot
   cap size), short TTL. Browser uploads **directly to object storage** —
   file bytes never transit FastAPI or the BFF. The bucket needs a CORS policy
   for the app origins, and a **lifecycle rule that deletes unconfirmed
   objects** (uploaded but never confirmed in step 2) after ~24h.
   <!-- This is a sanctioned exception to "browser only talks to the BFF": presigned object-storage URLs are scoped, expiring, and carry no session. -->
2. Client confirms completion → backend verifies object existence, size, and
   checksum (rejecting anything outside the declared caps), creates a
   `stored_files` row (storage key, mime, size, checksum, uploader,
   scan status), and links it to its domain object.
3. A worker job validates the server-observed MIME and size, then performs a
   **mandatory malware scan**. Files remain quarantined and cannot be reviewed,
   approved, or served until the scan clears. The scanner/provider is an
   external deployment choice; admin review is never a substitute for this
   fail-closed gate (RM18).
4. Serving: **time-limited signed GET URLs** issued by the backend; nothing in
   the bucket is public. `campaign_creatives.asset_url` remains and now points
   at (or is derived from) the managed object — external-URL creatives keep
   working for backward compatibility.

### 19.3 Consumers of the same pattern

| File kind | Linked to | Reviewer |
|-----------|-----------|----------|
| Creative assets (D7/Q18) | `campaign_creatives` | Admin approval (§18) |
| Installation evidence photos (Q17) | `campaign_assignments` | Admin activation gate (§18) |
| Driver identity/KYC documents (Q26 — licence, NIN, driver photo) | versioned driver-KYC record linked to `driver_profiles` | Admin person/payee approval; does not by itself grant work eligibility |
| Vehicle onboarding evidence (Q26 — registration, insurance, vehicle photos) | versioned vehicle-evidence record linked to `vehicles` | Admin vehicle approval; active driver KYC/payee + one approved vehicle grant work eligibility |
| Signed driver agreement (Q26) | `driver_profiles` | Acceptance recorded, doc stored |

One `stored_files` table + per-domain link columns/tables; one adapter; one
upload flow. Do not build per-feature upload paths.

National identifiers and bank values are not file-storage payloads and do not
get a second encryption design here. They reuse D17's crypto port and
ciphertext schema from §16.3. W2-02D adds production KMS/vault custody and the
audited rewrap/re-encryption path while preserving that schema.

## 20. Notifications

Q34 is client-confirmed by D18: launch = in-app + **automated email for advertisers** +
ops-run WhatsApp for drivers; automated WhatsApp/SMS is post-MVP. Email is a
first-class transactional channel adapter; its concrete provider/account
remains an external parameter.

### 20.1 Outbox pattern

- `notifications` table: recipient user, type/template key, payload (JSONB),
  channel (`in_app | whatsapp | sms | email`), status
  (`pending → sent → delivered | failed` — `delivered` set only by provider
  receipts), attempts, `created_at/sent_at`, a **`dedupe_key`** (unique,
  nullable) so retried triggers can't double-notify, and a
  **`provider_message_id`** (nullable, unique when present) so §15.4 delivery
  receipts can idempotently key back to the row.
- **Created transactionally** with the business mutation that triggers them
  (same DB transaction — a payout release that commits also commits its
  notification row; no lost or phantom sends).
- A worker job (§14) dispatches pending rows through channel adapters
  (`app/adapters/messaging/` — provider [OPEN]; in-app "dispatch" is a no-op,
  the row itself is the notification).
- In-app UI: notification list + unread badge, **polled** (P8) via TanStack
  Query (§27.2). Web surfaces stay poll-only (no WebSockets/SSE); mobile-app
  push (FCM) is a post-pilot native-client channel adapter (§23, D18) and does
  not change the schema.

### 20.2 Rules

- Services **never call a messaging provider inline** — they insert notification
  rows. Only the worker talks to providers.
- Templates are code (typed builders per notification type), not a CMS — at
  this scale a template table is over-engineering (P10).
- First triggers (when built): assignment offered/accepted, payout released,
  fraud flag raised/resolved, campaign approved/paused, budget alerts.

### 20.3 Pilot phone verification and WhatsApp consent

Automated WhatsApp/SMS delivery is post-MVP, so the pilot verifies a driver's
claimed phone through a bounded manual-send/system-verify flow:

1. The driver requests verification; the server creates a rate-limited,
   attempt-limited, short-lived challenge, stores only its hash, and creates an
   operations work item for the claimed phone version.
2. A named operator sends the code manually to that number by the approved
   WhatsApp/voice channel and records `sent_by`, channel, and `sent_at`; the code
   itself is never copied into audit/log records.
3. The driver enters the code in-product. A valid one-use challenge marks only
   that phone version verified; expiry, number change, too many attempts, or
   withdrawal fail closed and require a new challenge.
4. WhatsApp opt-in is a separate versioned consent record (purpose, notice
   version, `granted_at`, `withdrawn_at`). Normal manual-contact tasks require a
   currently verified phone and active consent; privacy/security incident
   escalation follows its separate authorised runbook rather than pretending
   consent exists.

## 21. Matching & assignment evolution

Q7, Q8 and Q16 are client-confirmed by D18. Competitor-separation remains a tunable business
policy; it does not block the recommendation/offer/assignment architecture.

- **Preserve:** admin-driven assignment through
  `app/services/campaign_assignments.py`. The existing `/accept` path covers
  only acceptance; decline and expiry do not yet exist in the assignment
  model/API/service. W3-03B owns the complete `offered → accepted | declined |
  expired` evidence and races before activation (Q8).
- **Target:** matching intelligence is a **recommender inside the existing
  service**, not an auto-assigner: rank eligible driver+vehicle pairs (city,
  vehicle type, activity history, current load) for the admin to confirm.
  Admin final approval is mandatory.
- **Constraint checks live in the service layer** so they hold no matter who
  creates the assignment (admin UI, recommender, future API): one-campaign-per-
  vehicle (Q16, confirmed pilot rule) and competitor-category separation
  (needs a campaign category field — added when the policy lands, [OPEN]) are
  validation rules in `create_assignment`, not UI logic.
- D18 confirms only one active campaign/brand placement per vehicle for the
  pilot. The product and documentation do not promise later overlapping or
  multiple-brand compatibility; any such future change requires a new client
  decision and explicit compatibility rules.
- Activity floor (Q20): worker sweep flags assignments below minimum tracked
  km/hours per week to ops (notification, §20) — data already exists in
  `trip_analytics`.

## 22. Retargeting & the audience privacy boundary (D6, D11, D20)

Q11 is client-confirmed by D18/D20 as one governed model supporting anonymised
exposure segments, controlled export **and direct ad-platform activation**.
Pilot activation is strictly geographic, time-based and contextual. Route data
must never become person-level retargeting data, and the activation contract
rejects identifiers or person-level payloads.
D11's full Module G scope ("Online-to-Offline Retargeting & Location-Based
Follow-Up Targeting") remains except where D18 overrides it. The MVP
retargeting workstream therefore has two data halves and one gated delivery
boundary:

1. **Inbound (online → offline planning):** advertiser-created **retargeting
   source records** — website traffic, digital campaign audiences, CRM/upload
   references, UTM campaign sources, or manually supplied audience/location
   insights — linked to campaigns and target-zone planning, storing segment
   *metadata only* (never raw personal identity data).
2. **Outbound (exposure → follow-up insight):** Q11's anonymised
   exposure-segment aggregation (§22.3) feeding follow-up-targeting insights in
   advertiser reports/dashboards and admin retargeting monitoring, with
   consent/estimated-attribution disclaimers in the product structure.

3. **Delivery:** controlled export and an activation adapter consume the same
   approved aggregate of geography/cell, time window and contextual campaign
   fields only. Provider-neutral activation workflows may be built and
   tested, but no Meta/Google/TikTok/programmatic data is pushed until
   `EXT-AD-PLATFORM` supplies the named accounts, legal approval, API access,
   credentials and budget. The adapter is fail-closed and every export/push is
   purpose-scoped, approved and audited. Any later person-level audience use
   requires a separately approved identity/location-data partner, lawful basis,
   data contract and client decision; it is outside the pilot and creates no
   MVP dependency.

### 22.1 What the data actually is

We do not observe audiences; we observe **vehicle routes**. "Audience" data is
derived: exposure cells (geo × time buckets a branded vehicle transited, with
estimated impressions). Under Q11/D20, the platform's audience product is
**aggregated exposure geography**, never individual traces.

### 22.2 The privacy boundary — binding NOW

1. Raw `location_pings` / `trip_sessions` are readable **only** by the
   analytics/fraud/payout services (the existing derived chain, §7.1) **plus
   one grandfathered reader**: the heatmap service
   (`app/services/heatmaps.py`) aggregates raw pings per request today
   ([BUILT]) and stays sanctioned until it moves to precomputed cells
   (§24.2.2). No **new** feature may query raw pings directly — new consumers
   read `trip_analytics`, `impression_estimates`, or the audience tables below.
2. Everything advertiser-visible or exportable is **aggregated with a minimum
   count threshold** — k counts **distinct vehicles per cell** (vehicles are
   the data subjects; a ping-count floor protects no one), configurable, cells
   below k suppressed. Applies to audience outputs from day one; the existing
   heatmap (which already aggregates, without a k-floor) must gain the same
   floor **in the same release** that ships any retargeting/export surface
   ([OPEN] parameter value only).
3. No driver identity, trip id, or precise timestamp ever appears in audience
   outputs.
4. Retention rules (§24) apply upstream: purged pings are simply gone; audience
   aggregates (which carry no personal data) persist.

### 22.3 Shape (Q11 confirmed by D18/D20; scope per D11)

New domain `app/services/audience.py` + `audience_segments` table (segment
definition: zones/cells × time window × campaign scope; materialised counts;
version stamp per P6). Worker jobs materialise segments from analytics
aggregates. Export/activation (CSV of cells, or platform integrations) is an
adapter decision downstream of the same aggregation model. Its schema
allowlists aggregate geography/cell, time-window and contextual campaign
fields and rejects identity fields, free-form person-level data and raw route
coordinates. Export ships disabled until Q31 legal sign-off.

### 22.4 Retargeting sources & follow-up insights (D11) [TARGET]

The inbound half of Module G: a `retargeting_sources` table (advertiser-scoped;
type ∈ website-traffic / digital-campaign-audience / CRM-upload-reference /
UTM-source / manual-insight; typed allowlisted aggregate planning fields with
provenance, legal basis, expiry and consent/disclaimer status) with linkage to
campaigns and target zones, plus
follow-up-targeting insight surfaces (report sections + dashboard views built
from §22.3 aggregates filtered through the linked sources' zones/time windows).
Privacy boundary §22.2 applies unchanged: source records hold planning
metadata, never identity data, and never join to raw pings. Admin gets a
retargeting source/insight monitoring view. Placement: same audience domain
(`services/audience.py`), advertiser + admin API surfaces, frontend under the
existing role IA.

Two proposal-promised metrics are the named product faces of these same
aggregates (they are analytics surfaces, not new data): **high-exposure zone
insights** (top-ranked exposure cells/zones per campaign and city — advertiser
+ admin dashboard views and report sections, feeding the follow-up-targeting
recommendations) and the **exposure score** (a formula-versioned composite per
campaign/route — `exposure_v1` per P6 — surfaced beside estimated impressions
in dashboards and reports). Both read `trip_analytics`/`impression_estimates`
aggregates only, k-floor rules of §22.2 apply to any zone-level display.

## 23. Identity evolution & production-PWA readiness

- **F7 is built** (§12): sliding session, `sv` revocation, forced password
  change, rate limiting. Everything below builds on it.
- **Driver self-registration (Q13 confirmed):** public
  `POST /api/v1/auth/register-driver` gated by feature flag, creating an
  `invited/pending`-state user + driver profile that enters the existing admin
  onboarding queue (KYC docs per Q26 through §19). The service layer already
  separates user creation from admin UI, so this is additive. Operator-led
  onboarding remains available; public applicants cannot work before approval.
- **Pilot driver client (Q10/D18):** a production-hardened installable PWA with
  explicit Start/End and screen-on enforcement. It stays behind the Next.js
  BFF-cookie boundary, reuses F7's capped sliding session, and inherits the
  built D15/D16 durable queue and trip-seal protocol. **[BUILT] R14-A
  contract:** ADR 014 (`docs/adr/014-production-pwa-capability-contract.md`)
  freezes the `r14-a-v1` capability contract, candidate device matrix,
  fail-closed Start/capture/End gates and `active|degraded|stopped`
  vocabulary, with the executable authenticated `/driver/capabilities` probe;
  probe evidence is capability-only (`activeTrip`/held-lock state gate any
  runtime claim). D23 separates this executable build contract from still-unrun
  real-world validation: R14-A closes only when its automated capability,
  denial/revocation and contract evidence passes, while representative
  Android/iPhone execution remains explicitly incomplete and gates W4/real GPS.
  W4 must prove standalone
  Android and iOS browser/device behaviour: permission grant/denial/revocation,
  visibility/background degradation, reload, offline/retry, IndexedDB and Web
  Locks failure, seal recovery, accuracy/completeness/sync latency, battery and
  the complete driver journey. Tracking pauses/fails closed whenever storage,
  single-writer ownership, permission or screen-visible guarantees cannot be
  upheld; health is visible as `active | degraded | stopped`.
- **Native driver app follows the pilot (D18 superseding D11 timing):** it must
  consume the identical ping/auth/seal contract. Native background execution,
  secure credential/storage, foreground/background location modes, OS
  kill/reboot/low-power/OEM behaviour, push (FCM), attestation and store review
  are Phase 2 requirements, not pilot prerequisites.
- **Advertiser/admin remain BFF-cookie web clients.** Keep the backend domain
  APIs free of UI assumptions, but do not expose a new public bearer surface
  merely for the PWA.

## 24. Data lifecycle — retention, volume, partitioning

### 24.1 Volume reality check

Pings arrive ~1/second while tracking (geolocation watch, §8.6). Pilot math:
50 vehicles × ~4 tracked h/day ≈ **0.7M pings/day ≈ 21M rows/month**. At the
proposed 12-month retention that is a ~250M-row steady state — too big for a
single unpartitioned table to purge with `DELETE`s, but entirely fine for
Postgres with partitioning. At 10× (500 vehicles) it is ~2.5B rows/year —
still Postgres territory with partitions + retention, not a new datastore.

### 24.2 Design **[BUILT]** (S4, 2026-08-03)

1. **Retention job** **[BUILT]** (§14): `purge_expired_ping_partitions` (arq
   cron, daily, advisory-locked) drops fully-expired `location_pings`
   partitions past ⚙ `PING_RETENTION_MONTHS` (default 12, Q31 param) and
   purges `location_ping_batches` rows only when **zero pings remain** for
   the batch (`NOT EXISTS`, plus a received_at guard so recent zero-ping
   batches keep serving idempotent replays) — never by time window, because
   `location_pings.batch_id` is `ON DELETE CASCADE` and a straddling batch
   must keep its newer pings. The lock is **session-scoped**
   (`pg_try_advisory_lock` on a dedicated AUTOCOMMIT connection held for the
   whole run) because `DETACH … CONCURRENTLY` cannot run in a transaction
   block; a concurrent run is a logged no-op. *Amendment (S4):* the original
   "null `trip_sessions` coordinate columns" step is deleted — `trip_sessions`
   has **no coordinate/geometry columns** (only `location_pings.geom` exists;
   §7.1's and §22.2.1's contrary claims were stale). `started_at`/`ended_at`
   are timestamps, not location data, and stay. Aggregates (`trip_analytics`,
   `impression_estimates`, heatmap-feeding data) and MNY-09A's deterministic
   route-replay hashes are retained with their owning trip today. The hashes
   contain no raw coordinates/timestamps but remain pseudonymous derived
   location-linkage data, may outlive raw pings, and must be included explicitly
   in RM15's retention schedule and tested DSR runbook before real-driver GPS.
2. **Monthly range partitioning** **[BUILT]** of `location_pings` by
   **`recorded_at`** (*amendment: the previously-named `captured_at` column
   never existed*) so purge = `DROP PARTITION` (instant, no bloat).
   Migration `0014` converts by **rename-and-attach**: the pre-existing
   table becomes the bounded partition `location_pings_legacy` covering
   `[first month, next month boundary)` — no row rewritten, ids preserved
   (payout input fingerprints embed ping ids). The parent recreates the 0007
   schema exactly with composite PK `(id, recorded_at)`; all bounds are UTC
   month boundaries. The ORM model carries the composite PK but deliberately
   NOT `postgresql_partition_by` (metadata.create_all test schemas must stay
   insertable; autogenerate cannot diff partitioning). `alembic/env.py`
   filters runtime partitions (`location_pings_pYYYY_MM`, `…_legacy`) from
   autogenerate. **No default partition exists** — it would forbid
   `DETACH CONCURRENTLY` and tax every ATTACH; instead the daily
   `premake_ping_partitions` cron idempotently keeps coverage through now +
   ⚙ `PARTITION_PREMAKE_MONTHS` (default 4; the migration premakes with a
   frozen constant 4), and the coverage alarm is two independent detectors:
   the worker's daily `check_ping_partition_coverage` (raises through Sentry
   when no partition covers now + 1 month) and the API's
   `GET /api/v1/health/partitions` (503 `degraded` on the same condition —
   catches a dead worker; deliberately not part of `/ready`). The
   live-aggregation heatmap is unchanged and partition-safe (its
   `recorded_at` filters prune); if it degrades, the sanctioned fix remains
   **precomputed heatmap cells materialised by a worker job**, not caching
   hacks.
3. **Consent & policy (NDPR):** trip-scoped tracking is already the built
   posture (tracking only between explicit start/end — Q10-area, keep it);
   consent wording + privacy policy are client deliverables ([OPEN] Q31); the
   driver app surfaces consent at onboarding (§19.3 agreement flow).
4. **Purge evidence** **[BUILT]** — *amendment (S4): a dedicated
   `data_purge_audit` table supersedes the earlier "an audit event records
   the purge run" sketch* (the compliance artifact must not couple to the
   operational audit trail's shape/retention). Append-only lifecycle-EVENT
   rows (`purge_started` → [`detach_finalized`] → `dropped` →
   `batches_purged`), never updated; a partial unique index allows exactly
   one `dropped` row per partition; the `dropped` row commits **in the same
   transaction as `DROP TABLE`**, so evidence and destruction are atomic and
   `purge_started` (with row count, range, retention config, run id) always
   precedes destruction. Interrupted runs recover under evidence gating: a
   pending detach is FINALIZEd only with a matching `purge_started` row AND
   current retention-expiry (otherwise refused — logged, Sentry-alerted, and
   all destruction including the batch purge is skipped for that run);
   evidenced orphans are dropped unless `dropped` evidence already exists
   for the name (conflict ⇒ fail closed, table retained); unclaimed tables
   are never touched.
5. **Backups respect retention:** database backups (§25.2) resurrect purged
   pings unless they expire — backup retention must be **shorter than or equal
   to** a bounded rotation window (e.g. 35 days), so purged personal data ages
   out of backups automatically. Stated in the backup runbook (the local
   14-dump rotation complies at any realistic cadence).
6. **Data-subject rights (NDPR):** access/rectification/erasure requests have
   no automated pipeline at pilot scale — the sanctioned shape is a **manual
   SQL runbook** (P10) executed by a named admin and recorded in the audit
   trail. Known design tension to resolve with counsel ([OPEN] Q31): an
   erasure request vs the append-only ledger/audit history — the expected
   answer is anonymisation of the user row while preserving financial records,
   but that is a legal call, not ours.

## 25. Deployment & infrastructure target

Q29/Q30 and the client-ownership direction in Q32 are confirmed by D18:
Cardvert/Terrax Media, Abuja, 10 vehicles, 5 paying advertisers, three months,
client-owned cloud/domain. The actual account/domain/provider/budget/access
remain `EXT-RELEASE-ENV`. Posture: containerised and cloud-portable — nothing
below assumes a specific vendor.

### 25.1 Environments

| Env | Purpose | Shape |
|-----|---------|-------|
| **Local** | dev | compose as today (§10.1) + `worker` + MinIO when §14/§19 land |
| **Staging** [BUILT topology / not deployed] | client review, e2e against prod-like stack | provider-neutral Compose + Caddy artifacts; demo seed prohibited; no provider/account selected |
| **Production** | pilot launch | see below |

### 25.2 Production topology (pilot-sized)

- **Managed Postgres with PostGIS** (the one component worth paying a provider
  for: backups, PITR, failover). Everything else runs as containers on **one or
  two VMs** (or the cloud's container service if Q32 lands on GCP/AWS —
  equivalent shape): `frontend`, `api`, `worker`, `redis`, edge proxy.
- **Edge exposure:** the reverse proxy routes the public domain to `frontend`
  (all browser traffic) and exposes exactly `/api/v1/webhooks/*` and the
  health endpoints (`/health`, `/api/v1/health*` — so external uptime monitors
  can reach them, §26) to the internet; the pilot PWA talks through the
  frontend/BFF like every other browser surface. FastAPI is otherwise
  internal-only (§8.2). A later native bearer surface requires its own Phase 2
  edge/auth review. TLS terminates at the proxy.
- **Object storage:** provider bucket (§19), private, presigned access only.
- **Secrets:** injected env from the platform's secret store; never in images
  or the repo ([BUILT] posture: `.env` gitignored, `.env.example` documents).
- **Backups [BUILT scripts, F7]:** dumps + the revision-gated restore check
  (`scripts/db_backup.sh` / `db_restore.sh`); daily scheduling is an ops task at
  deploy time.
- Deploys are image-tag rollouts (build in CI, pull + restart on host);
  rollback = previous tag. Alembic migrations run as a pre-deploy step, and
  must stay backward-compatible one release back (additive first, destructive
  later) once real users exist.
- **Explicitly not now:** Kubernetes, autoscaling, multi-region, IaC frameworks.
  One pilot city does not need them (P1/P10); revisit at multi-city scale.

### 25.3 Scaling path (when measured need arrives)

API and frontend are stateless → add replicas behind the proxy. Worker scales by
process count (arq supports multiple workers; jobs are idempotent by rule).
Postgres scales up (managed tiers), then read replicas for reporting. The
monolith split point, if ever, is the analytics/impression computation — it is
already service-isolated behind `formula_version`ed interfaces.

## 26. Observability target

- **Structured JSON logs** on both tiers with `request_id` correlation (backend
  middleware exists [BUILT]; formalise the JSON format when staging lands),
  job-run lines from the worker (§14.3.4).
- **Sentry** on backend and browser [BUILT hooks, F7 — inert without a DSN;
  worker joins when §14 lands] —
  errors with request ids, release tags from image tags.
- **Uptime checks** on `/health` (root), `/api/v1/health/ready`, and the
  frontend, from any external monitor.
- **Postgres**: slow-query logging on; the heatmap latency trigger (§24.2.2) is
  watched via these logs — no APM product at pilot scale.
- **Explicitly not now:** Prometheus/Grafana, OpenTelemetry tracing, log
  aggregation infra (P10). The trigger to revisit: >1 VM of app containers or
  the first incident that logs + Sentry couldn't diagnose.

## 27. Frontend evolution

The BFF pattern, typed-client discipline, design system, and per-surface
colocation (§8) are **preserved unchanged** — every new surface below follows
them.

### 27.1 New surfaces (mapped to their backend sections)

| Surface | Where | Backend |
|---------|-------|---------|
| Admin approvals queue (campaigns, creatives, activation evidence) | `app/admin/approvals/` | §18 |
| Fraud review queue (upgrade of read-only console) | `app/admin/fraud/` (existing route, new actions) | §17 |
| Payout runs & disbursement | `app/admin/payouts/` (extend) | §16 |
| Billing: invoices, record-payment (admin) + invoice view (advertiser) | `app/admin/billing/`, `app/advertiser/billing/` | §15 |
| Audit-trail viewer | `app/admin/audit/` | [BUILT] (F7) |
| Notification bell + list (all three surfaces) | `components/` + per-surface | §20 |
| Creative upload in the campaign wizard | extend `app/advertiser/campaigns/new/` | §19 |
| Driver: flagged-trip detail + dispute, onboarding docs, vehicle profile/evidence, payout history | `app/driver/*` (extend) | §17/§19/§16/§21 |

### 27.2 TanStack Query — sanctioned adoption

Already a dependency, deliberately unused. It enters **only** for polling
surfaces (notification badge, fraud queue counts, live-ish dashboards) as a
client-side layer over data fetched through server actions/route handlers —
never as a bypass of the BFF (§8.2). One shared provider + conventions
established in its first PR; ad-hoc `useEffect` polling is not acceptable.

### 27.3 Explicitly unchanged

Single dark theme; no client-side API client; zod duplication
(browser UX + server authority); decimal-strings parsed only at display
boundary (`src/lib/format.ts`).

### 27.4 Report naming and ROI gate (Q30/D20)

The standard advertiser deliverable is **Campaign Performance Analysis**. It
may present the approved operational and modelled measures from immutable
`measurement_run` inputs, with measured/modelled labels, provenance,
uncertainty and a reproducible proof manifest. It must not imply financial ROI.

A true ROI section is optional and appears only when the advertiser supplies
the defined conversion and revenue inputs **and** `EXT-REPORT-METHOD` contains
an approved, reproducible ROI method covering attribution, cost basis, time
window, exclusions and corrections. Missing either prerequisite fails closed:
the report remains Campaign Performance Analysis and omits the ROI metric and
ROI claim rather than estimating or relabelling one. CSV/PDF issuance, the UI
and the pilot acceptance suite must reproduce that same choice from the frozen
run and input manifest.

## 28. Testing strategy — target

Current gates (§11) stay. Additions, each landing **with** the feature that
needs it:

1. **Backend CI job** [BUILT] (F7) — pytest + ruff with postgis+redis services;
   postgres-gated tests actually run in CI.
2. **Worker/job tests:** every job gets (a) an idempotency test — run twice,
   assert single effect; (b) a frozen-time test of its due-work query. Jobs are
   testable because they're thin wrappers over services (§14.3.3).
3. **Webhook tests:** signature verification (valid/invalid/replayed event id),
   and the enqueue-only contract of the request path.
4. **Money invariants:** property-style tests on payout v2 (cap never exceeded,
   held entries never released, ledger sums = calculation sums) — the payout
   engine is the highest-stakes code in the product.
5. **Contract discipline extends unchanged** to every new endpoint (§9) —
   webhooks and uploads included.
6. **e2e per new admin surface** against the seeded stack, following the F7
   seed-namespace rules (§11).

---

# PART IV — RULES FOR BUILDERS

## 29. Code organisation & dependency rules

### 29.1 Backend tree — current + target additions

```
app/
├── api/v1/            # routers only. [TARGET] + webhooks.py
├── core/              # config, security, errors, middleware
├── db/                # engine/session/base
├── models/            # SQLAlchemy. [TARGET] + billing.py, files.py, notifications.py, audience.py
├── schemas/           # Pydantic
├── services/          # ALL business logic. [TARGET] + billing.py, audience.py, notifications.py, files.py
├── adapters/          # [TARGET] vendor code behind interfaces:
│   ├── payments/      #   paystack.py / flutterwave.py / manual.py  (§15)
│   ├── disbursement/  #   (§16.3)
│   ├── messaging/     #   whatsapp/sms/email provider(s)  (§20)
│   └── storage/       #   s3.py (+ minio local)  (§19)
├── jobs/              # [TARGET] arq task defs — thin wrappers over services (§14)
└── seeds/             # demo seed CLI
```

### 29.2 Dependency rules (import direction)

```
api/ ──────► services/ ──────► models/, schemas/, core/, db/
jobs/ ─────► services/                (never api/)
services/ ─► adapters/ (interfaces)   (never api/, never jobs/)
adapters/ ─► vendor SDKs, core/       (never services/, never models/)
```

- Nothing imports `api/` except `main.py`.
- `services/` never import each other's routers, never touch HTTP concepts
  (no status codes — raise `AppError`).
- `adapters/` are stateless translators; retries/orchestration live in
  services or jobs.
- Frontend: `components/ → lib/`; generated `schema.d.ts` is never edited;
  `server-only` modules stay server-only (§8.2).

### 29.3 Naming conventions

- Tables: snake_case plural; link tables `x_y`; event/log tables suffixed
  `_events`/`_entries`. Enums: Python `StrEnum` + DB check constraint (§7.1).
- Endpoints: role prefix + plural resource + verb-free paths; lifecycle
  transitions as sub-resources (`.../{id}/approve`), matching the existing
  assignment endpoints.
- Migrations: sequential `00NN_description.py`, frozen once shipped (§7.2).
- Frontend routes mirror the role IA (`app/{role}/{section}/...`); server
  actions in colocated `actions.ts`; shared domain logic in `src/lib/{domain}/`.
- Formula versions: `{domain}_v{n}` (§6.4.8). Settings keys:
  SCREAMING_SNAKE in `.env`, typed in `Settings`.

## 30. Feature placement map

The pre-flight table for any new work. **If your feature isn't here, add it
(amendment rule, §1).**

| Feature | Section | Code home | May touch | Must not touch | Blocked by |
|---------|---------|-----------|-----------|----------------|------------|
| Any auth change | §6.3/§12/§23 | `core/security.py`, `services/auth.py` | users | — | — (F7 landed; extend, don't fork) |
| Rate limiting | §12 F7 | `core/rate_limit.py` + Redis | — | — | [BUILT] for login; new buckets extend the same module |
| Payout engine v2 history + `payout_v3` target | §16.1 | `services/payouts.py` + `services/payout_eligibility.py` + `jobs/` (trip pipeline, §14.2) | payout_rules, payout_calculations, ledger | v1/v2 history rows | v2 [BUILT] S1; v3 D18/MNY-06B |
| Payout recompute-day true-up | §16.1 | `services/payouts.py` + `api/v1/payouts.py` | ledger (append-only adjustment/reversal) | calculation edits, v1 days | [BUILT] S1 |
| Driver trip earnings breakdown | §16.1 | `api/v1/payouts.py` + driver PWA `(portal)/earnings/trips/` | — | trip_analytics as driver-facing verified time | [BUILT] S1 |
| Trip seal protocol + post-seal quarantine | §14.2/§35 RM3 | `services/trips.py` + `services/trip_processing.py` (seal sweep) + `api/v1/trips.py` (admin quarantine review) | trip_sessions (seal fields), quarantined_ping_batches | payout recompute (apply never recomputes money) | [BUILT] 9 Aug 2026 (D15) |
| Durable client ping queue | §35 RM4/RM5 | `frontend/src/lib/trips/ping-queue.ts` + `(portal)/track/trip-tracker.tsx` | IndexedDB stores | server contract beyond §9 baselines | [BUILT] 9 Aug 2026 (D15) |
| Release scheduling | §16.2 | `jobs/` + `services/payouts.py` | ledger statuses | ledger edits (append-only) | Q22 confirmed; RM8 before release |
| Automated disbursement | §16.3 | `adapters/disbursement/`, `services/payouts.py` | payout_batches (new) | direct vendor calls from services | Q27 confirmed; RM10/RM11; `EXT-DISBURSEMENT-PROVIDER` for live submission |
| Fraud review workflow | §17 | `services/` + `api/v1/` fraud modules | fraud_flags lifecycle | detection engine internals | Q21 confirmed; RM8 |
| Campaign/creative approval | §18 | status enums + services | campaign/creative status | parallel approval flags | Q6/Q18 confirmed; RM13 |
| File upload (any kind) | §19 | `adapters/storage/`, `services/files.py` | stored_files (new) | container FS, DB blobs | Q18/Q26 + provider |
| Notifications | §20 | `services/notifications.py`, `jobs/`, `adapters/messaging/` | notifications (new) | inline provider calls | Q34 confirmed; provider is parameter |
| Billing / accepted terms / invoices / payments | §15 | `services/billing.py`, `adapters/payments/` | commercial_terms, invoices, payments (new) | report/cost-summary logic | Q1–Q3, Q14, Q28 confirmed; external provider/company facts for live use |
| Payment webhooks | §15.4 | `api/v1/webhooks.py` | payment_events (new) | business logic in handler | provider choice |
| Budget enforcement | §15.5 | `jobs/` + `services/billing.py` + campaign status | campaign status | hard deletes | policy confirmation (Q9-adjacent, via decisions-log) |
| Matching/recommender | §21 | `services/campaign_assignments.py` | — | UI-layer constraint checks | Q7/Q16 confirmed |
| Activity-floor sweep | §21 | `jobs/` | notifications | — | Q20 confirmed; worker |
| Retargeting/audience/export/activation | §22 | `services/audience.py`, `jobs/`, `adapters/ad_platforms/` | audience_segments, retargeting_sources (new) | raw pings from any new code; identifiers/person-level activation payloads; live push without gate | Q11/D18/D20; legal export approval and `EXT-AD-PLATFORM` gate live aggregate contextual actions |
| High-exposure zone insights | §22.4 | `services/audience.py` + report/dashboard surfaces | — | raw pings; zone display below the k-floor (§22.2) | W3 (D11) |
| Exposure score (campaign/route metric) | §22.4 | `services/route_analytics.py`/`services/impressions.py` (`exposure_v1`, P6-versioned) | impression_estimates or a derived column | rescoring frozen formula versions | W3 (D11) |
| CSV/PDF report export | §27 report surfaces + §16.3 payout report | report/payout endpoints + frontend download actions | — | heavy generation inline in the request path (use the worker, §14); ROI without required inputs and approved method | W4 (D11; Q12 labels and D20's report/ROI gate apply) |
| Retention purge | §24 | `services/data_lifecycle.py` + `jobs/data_lifecycle.py` | location_pings partitions (drop), location_ping_batches (zero-ping delete), data_purge_audit (append) | aggregates, trip_sessions | [BUILT] S4 (Q31 param ⚙ PING_RETENTION_MONTHS) |
| Ping partitioning | §24.2 | migration `0014` + premake/coverage jobs + `/health/partitions` | location_pings | frozen migrations, default partitions | [BUILT] S4 |
| Purge evidence (data_purge_audit) | §24.2.4 | `models/data_purge.py` + `services/data_lifecycle.py` | data_purge_audit (append-only) | updates to existing rows | [BUILT] S4 |
| Data-subject requests (NDPR) | §24.2.6 | ops runbook (no code at pilot) | — | ledger/audit deletes | Q31, counsel |
| Per-campaign custom quotation / accepted external deal record | §15 | `services/billing.py` | commercial_terms, invoices | launch package catalogue; report logic | Q1/Q14 confirmed |
| Advertiser company profile | §6/§15/§27 | advertiser organization service + advertiser/admin pages | advertiser_organizations | invoice-company identity, tenant ownership | D11 proposal Module B |
| Campaign cancellation / refunds and production authority | §15 | `services/billing.py` + campaign status | commercial terms, production-authority events, invoices, payments | mutable waivers; production before authority; ledger edits | Q24/D20 |
| Driver bank account / BVN capture | §16.3 | `driver_profiles` + KYC flow (§19.3) | driver_profiles | plaintext storage of BVN — treat as sensitive PII (P7) | Q26, Q27 |
| Password reset (advertiser/admin) | §23 | `services/auth.py` | users | — | post-F7; needs email channel (§20) |
| WhatsApp opt-in / phone verification | §20 | `services/notifications.py` | users/driver_profiles phone fields | — | Q34 |
| Driver self-registration | §23 | `services/users.py` + new auth endpoint | users, driver_profiles | approval-before-work invariant | Q13 confirmed |
| Driver vehicle profile / evidence review | §19/§21/§23 | driver/vehicle service + driver/admin APIs | vehicles, versioned vehicle evidence, stored_files | self-approval, mutable approved evidence, assignment bypass | Q26 + proposal Module C; W3-04C |
| Production driver PWA | §23 | existing Next.js driver surface + trip queue/seal/auth | IndexedDB/Web Locks, PWA manifest/service worker | public bearer API; native-only assumptions | D18: W4 pilot client |
| Driver mobile app (native) | §23 | React Native/Flutter client + auth + notifications | refresh tokens/secure storage (new) | driver API contract breaks | D18: Phase 2 after pilot |
| New admin/advertiser/driver page | §27 | `frontend/src/app/{role}/` | — | BFF invariant, raw hex | backend feature |
| Polling/live UI | §27.2 | TanStack Query layer | — | WebSockets/SSE | — |

## 31. Roadmap — gaps & sequencing

The gap between Part II and Part III at roadmap granularity. **Execution order
and authorization live exclusively in `docs/progress.md`; this section is
context and cannot authorize a wave, package or checklist item.** Waves after F7 assume the
blocking answers have landed.

| Wave | Contents | Depends on |
|------|----------|------------|
| **F7 (done, 2026-07-20)** [BUILT] | Auth hardening (sliding session, `sv`, forced change, rate limiting), backend CI, audit API/UI, rich seed, backups/restore, Sentry hooks. Staging deploy deliberately deferred — research only (`docs/staging-options.md`), awaiting an explicit project-owner go-ahead | — |
| **W0 — review remediation (§35)** *(new, 6 Aug 2026, D13)* | **PKG-01 built-code defects complete.** Cap-day allocation RM1, stationary farming RM2, trip seal + client queue RM3/RM4/RM5, admin correction authority RM6 and integrity mapping RM7 are closed. The specification rows each owning slice must honour (RM8–RM18) remain. Production-PWA and provider-neutral release/recovery foundations are built; physical-device and live-staging validation remain deferred under D23. | D22 supplies the versioned stationary policy; no build prerequisite remains for W0 |
| **W1 — money correctness** | Worker substrate + trip-processing pipeline (§14) **[BUILT]** → immutable payout v2 history plus D18/D22 `payout_v3` base/premium zone and stationary rules (§16.1) **[BUILT]** → fraud review + authoritative holds (§17/RM8) → clean-immediate and flagged-seven-day-SLA release (§16.2) → automated provider submission/reconciliation (§16.3/RM10/RM11). Plus pre-pilot data-infra chores: retention/partitioning and audit backfill | Q4/Q5/Q21/Q22/Q27 confirmed; only the named later live/provider inputs remain gates |
| **W2 — the commercial layer** | Accepted per-campaign custom-quotation terms, VAT-inclusive/itemised billing/invoices/payments, the standard 24-hour production wait and audited expedited-waiver path (§15) → file storage (§19) → approval workflows (§18) → notification channel adapters + triggers (§20) | Product choices confirmed by D18/D20; company/provider/legal artifacts gate live use |
| **W3 — reach** | Retargeting per Q11/D18/D20 + D11 Module G scope (§22: exposure segments + source records + campaign linkage + follow-up insights + governed aggregate contextual export/activation) → exposure score + high-exposure zone views (§22.4) → matching recommender + activity sweeps (§21) → driver self-reg (§23) | Q7/Q11/Q13/Q20 confirmed; legal approval gates export and `EXT-AD-PLATFORM` gates live aggregate contextual push |
| **W4 — production PWA + pilot readiness (D18)** | Harden the installable screen-on driver PWA on real Android/iOS devices (§23) → basic CSV/PDF export where still missing → client-owned pilot deployment (§25) → automated disbursement readiness → onboarding/training with Somto's operations team → Abuja pilot acceptance and post-pilot roadmap | W1–W3; client cloud/domain, provider, permit, legal/privacy and other external launch gates |
| **Phase 2 (post-pilot)** | Native driver app with background GPS, secure native credentials/storage, push and store review; edge-AI counting; multi-city optimisation; expanded recurring billing. Aggregate contextual ad-platform activation is pilot-capable when its gate is satisfied; any person-level activation requires a separately approved identity/location-data partner and lawful contract. Automated payouts are pilot scope, not Phase 2 | Pilot results and separate approval |

Sequencing rationale: W1 first because D2/D4/D5 change **how money is
computed** — every week built on `payout_v1` deepens the rework; W2 second
because it's what sales/ops need to run real campaigns; W3 third because it
extends reach rather than correctness; W4 integrates the production PWA and
pilot deployment around contracts the earlier waves have proven. RM17 starts
synthetic staging and real-device PWA checks earlier so W4 is hardening, not
first discovery. The worker (§14) leads W1 because every later wave consumes
it.

## 32. Risks, assumptions & client dependencies

| # | Risk / assumption | Mitigation / owner |
|---|-------------------|--------------------|
| R1 | **Hourly pay invites time-farming**, and D18 now pays valid base time outside the premium zone. App-open time alone is never payable: campaign window, exclusions, movement/stationary policy, signal quality and fraud controls still apply. | D22's acceptance-frozen rolling detector is built in `payout_v3`; tune only through a later effective revision after real-route evidence. |
| R2 | **Resolved authority risk:** Somto's Q1–Q34 list is the direct client answer and D20 is the later approved implementation clarification; together they supersede older conflicting defaults/proposal wording. | Affected slices cite D18/D20 and preserve immutable historic formula/data rows. |
| R3 | **Redis fail-open** (F7 rate limiting) + queue-loss tolerance (§14.3.2) are deliberate availability-over-strictness choices. | Documented here; revisit post-pilot. |
| R4 | **Prototype promised "live" surfaces**; MVP is polling. Client expectations managed via demo framing. | §14.4; OJ handles comms. |
| R5 | **Single-operator bus factor** (OJ + agents). This doc + SOP + memory files are the mitigation. | Keep doc current (amendment rule). |
| R6 | **NDPR compliance depends on client deliverables** (policy, consent wording, DPO contact — Q31). Retention tech (§24) is ours; the words are theirs. | Flag at every review until landed. |
| R7 | **Vendor accounts remain unprovided** (client cloud/domain, money-in, automated disbursement, messaging, ad platforms, storage/scanning, tiles). | Adapters (P5) keep them swappable; the external register gates only the affected live action. |
| R8 | **Volume math (§24.1) is estimated**, not measured (ping rate assumed ~1/s tracked). Validate against real pilot telemetry in month 1; retune partitioning trigger. | First staging review. |
| R9 | **Resolved (D12, 4 Aug 2026).** Hourly model confirmed: earnings = hourly rate × verified payable hours; proposal Module E's "mileage-based" phrasing is superseded requirement-era wording (mileage/zones/quality are verification + analytics inputs, not rate components). | Closed — decisions-log D12. Residual: OJ aligns the client-facing proposal wording at its next revision (comms, not code). |
| A1 | **Confirmed pilot:** Abuja, 10 vehicles, 5 paying advertisers, three months; success includes Campaign Performance Analysis, offline-to-online targeting and at least 60% target-area coverage. True ROI is included only when advertiser conversion/revenue inputs and an approved reproducible method are present. | Size W4 to these facts; D19/`EXT-PILOT-PERMITS` gates permit evidence and D20/`EXT-REPORT-METHOD` governs the optional ROI path. |
| A2 | Advertiser/admin remain web-only; the driver uses a production screen-on PWA for the pilot. A native background app is Phase 2. | D18/Q10; verify the §23 PWA device matrix before launch. |

## 33. Questionnaire routing and remaining external inputs

**Status authority moved again (D18–D20, 14 Aug 2026):** Somto supplied the
direct client answer to all Q1–Q34 and the client then approved the three-point
implementation clarification. These are the newest authority and override
prior adopted defaults and conflicting proposal wording. Part 2 of
`docs/decisions-log.md` records the confirmed interpretation. The table below
is a routing map, not a list of unanswered product questions. Remaining work is
external execution evidence: provider accounts/credentials, registered-company
facts, legal/privacy artifacts, stationary-policy parameters, cloud/domain
action and pilot permit evidence. Historical client-facing artefact:
`docs/Mobility_Working_Decisions_and_Open_Items.docx` (superseded by the
questionnaire). Answers still flow client → `decisions-log.md` (new Part 1
row + Part 2 status flip) → this doc (amendment rule).

The table below remains the routing map from each Q to the section it feeds:

| Q | Topic | Feeds section |
|---|-------|---------------|
| Q1–Q3 | Pricing structure, payment timing, methods | §15 |
| Q4–Q5 | Hourly rate uniformity; payable-hour definition | §16.1 |
| Q6 | Campaign creation & approval flow | §18 |
| Q7–Q8 | Matching model; driver acceptance | §21 |
| Q9 | Mid-flight campaign changes | §18/§15.5 |
| Q10 | Session start/end model | §8.6 (confirm as built) |
| Q11 | Retargeting MVP shape | §22 |
| Q12 | Advertiser results/reporting expectations | §27 (report surfaces) |
| Q13 | Driver joining model | §23 |
| Q14 | Quotes/invoices in-platform? | §15 |
| Q15–Q17 | Activation requirements; one-campaign-per-vehicle; installation evidence | §18/§19/§21 |
| Q18 | Creative upload & approval | §19/§18 |
| Q19–Q20 | Vehicle eligibility; minimum activity | §21 |
| Q21 | Fraud review & flagged earnings | §17 |
| Q22 | Earnings release & corrections | §16.2 |
| Q23 | Owner-drivers only for the pilot | §16.3 (payee abstraction) |
| Q24 | Cancellations/refunds | §15 |
| Q25 | Printing/installation/permits ownership | ops (no code) |
| Q26 | Driver onboarding requirements (KYC, agreement) | §19.3/§23 |
| Q27 | Payout channel for pilot | §16.3 |
| Q28 | VAT & invoice presentation | §15.2 |
| Q29 | Product name & brand | rename sweep (manifest, fonts OK) |
| Q30 | Pilot shape | §2.3/§25 sizing |
| Q31 | Privacy/consent/retention sign-off | §24 |
| Q32 | Cloud/domain/infra ownership | §25 |
| Q33 | Day-to-day operations owner | ops (no code) |
| Q34 | Launch notification channels | §20 |

**Rule:** if a feature touches one of these areas, implement the D18-confirmed
direction and fail closed only on the named missing external artifact (P10).

## 35. Remediation register (independent review, 6 Aug 2026) **[TARGET]**

Two independent reviews (broad architecture + money-path red team) were run on
the doc packet, then **every code-checkable claim was verified against the
implementation** before acceptance. This register is the authoritative
remediation list: agents fix from here, and each row's gate says when. Origin
IDs (F##/G##/H##) are the reviewers' numbering, kept for traceability. Full
reconciliation, including rejected findings, is decisions-log **D13**.

Legacy slice names are aliases only: S2 ≈ MNY-08A/B/C + MNY-09A; S3 ≈
MNY-03A + MNY-10A/B/C + MNY-11A; S5 ≈ the W2-01A opener. They never authorize
work; only the active package in `docs/progress.md` does. The mapped checklist
items remain mandatory obligations inside that package, not separate cycles.

**Verification status legend:** `CODE-CONFIRMED` = verified against the
implementation. `DESIGN-GAP` = about an unbuilt ([TARGET]) domain, so it is a
specification requirement, not a live defect. `WORSE` = the code is worse than
the reviewer described.

### 35.1 Live defects in built code (fix before real-driver GPS or any release)

| ID | Origin | Status | Defect (verified location) | Required correction | Gate |
|----|--------|--------|---------------------------|---------------------|------|
| **RM1** ✅ **[FIXED 6 Aug 2026]** | G8/F03 | RESOLVED — migration `0015`, `payout_v2` per D14 | **Cross-midnight cap allocation is wrong.** The cap lock and day attribution derive from `trip.started_at` (`services/payouts.py:1460`, key at `:137-141`; day-consumption query filters trips by `started_at`, `:977-978`) and no interval splitting at Lagos midnight exists (`payout_eligibility.py:213-218` slices only on session/ping/window/stay edges). D4 is a **calendar-day** cap, so a 23:59 start charges post-midnight hours to the wrong day and the next day's full cap remains available. | **Done.** `classify_session` now cuts the timeline at every Africa/Lagos midnight and returns `eligible_seconds_by_day`; `calculate_trip_payout_v2` locks every touched day in sorted order (deadlock-free) and caps each day against its own allowance; the allocation persists in `payout_calculations.payable_seconds_by_day` (migration `0015`, backfilled to the old start-day attribution for existing rows). `day_consumed_payable_seconds` now counts trips that *overlap* the day, charging each only its stored day allocation. Recompute-day re-allocates only the day under its lock, preserving each trip's other-day allocations. Fixed inside `payout_v2` per **D14**. Remaining follow-up: mirror the split in the driver-facing cap-progress UI. | Before any earnings release |
| **RM2** ✅ **[FIXED 20 Aug 2026]** | H3 | RESOLVED — D22, `stationary-rd-v1` | **Stationary time was farmable.** The original detector excluded only stays reaching 300 seconds, so repeated stop-4:59/hop cycles remained payable even after the whole-trip grace fix. | **Done for new payout-v3 acceptances.** D22's contiguous 120-second net-displacement detector confirms at ≤25 metres after two adjacent windows, releases after one above-threshold window, resets on trip/GPS gaps, rejects contaminated evidence, and unions with the legacy long-stay path before one shared 240-second grace allocation. Complete terms and marker freeze at acceptance; calculations and corrections persist reason/evidence; driver/admin views explain the result; payout-v1/v2 history and fingerprints stay unchanged. Deterministic congestion, stop-hop, boundary, invalid-evidence, frozen-binding and correction tests plus live synthetic flows pass. Real-route calibration remains optional post-build tuning through a later revision only. | ~~Before pilot launch~~ Closed for build; later real-route calibration remains deferred validation |
| **RM3** ✅ **[FIXED 9 Aug 2026]** | F01 | RESOLVED — migration `0016`, seal protocol (D15) | **No trip-finality protocol, and late data is unrecoverable.** Trip end committed and enqueued the write-once money chain immediately; `TripEndRequest` carried no completeness signal; a post-end batch was rejected 400 outright; the PWA ended trips without checking its buffer. | **Done.** Lifecycle is now `active → ended → sealed` and **sealed is the sole money-chain trigger**: `process_ended_trip` blocks (`trip_not_sealed`) and the sweep selects `status='sealed'`; `get_trip_for_payout` requires sealed (analytics/impressions accept ended|sealed — diagnostics, not money). `/end` carries the client finalization watermark (`client_batch_count`/`client_ping_count`/`client_complete`); the trip fast-seals in the same transaction when the server holds ≥ `client_batch_count` batches, otherwise it seals on the late batch that completes the count (`late_data_complete`) or via the worker seal sweep after ⚙ `TRIP_SEAL_GRACE_SECONDS` (600). Every seal path is a guarded `UPDATE … WHERE status='ended'` (winner-only, audited `trip.sealed`); ingest re-reads the trip `FOR UPDATE` so a batch can never land mid-seal. Ended trips accept late batches (assignment-active gate deliberately skipped; `recorded_at ≤ ended_at +` ⚙ `LOCATION_PING_END_SKEW_SECONDS` (300)); post-seal batches are preserved in `quarantined_ping_batches` (never 400), with audited admin apply/discard — apply inserts the pings, names the affected Lagos days, and **never auto-recomputes money** (recompute-day is the corrective path). Quarantine payloads purge on the §24.2 retention window (`quarantined_batches_purged` evidence rows). **Review-hardened (9 Aug 2026 second pass, independent post-implementation review):** apply is allowed only after the trip's initial payout calculation exists (`QUARANTINE_APPLY_BLOCKED` otherwise) so post-seal evidence can affect money solely through recompute-day regardless of worker timing; a same-version analytics row computed before `sealed_at` is recomputed by the pipeline, never reused for money; `active → ended` is a guarded UPDATE (a losing concurrent end maps to `TRIP_ALREADY_ENDED`, never a constraint 500); apply/discard serialize on the quarantine row (`FOR UPDATE`) with resolution CHECKs (migration `0017`); 0016's backfilled seals gained their `trip.sealed` audit events (0017). | ~~Before real-driver GPS~~ Closed |
| **RM4** ✅ **[FIXED 9 Aug 2026]** | *(new — found in verification)* | RESOLVED — durable queue (D15) | **Ping-batch retries could double-insert.** The client minted a fresh `crypto.randomUUID()` per flush attempt while server dedup is exactly `(trip_session_id, idempotency_key)`. | **Done.** The idempotency key is minted **once at batch-cut time inside a single IndexedDB transaction** and persisted with the batch (`frontend/src/lib/trips/ping-queue.ts`); every retry reuses it verbatim, so a persisted-but-unacknowledged batch dedupes (`duplicate: true`) instead of double-inserting — including replays across the seal boundary, which return the original live ACK. Server-side payload-hash conflict check kept. Terminal rejections (400/409/422) drop the batch (dead-letter) so one poison batch can never jam the queue. Vitest-proven. | ~~Before real-driver GPS~~ Closed |
| **RM5** ✅ **[FIXED 9 Aug 2026]** | *(new — found in verification)* | RESOLVED — durable queue (D15) | **PWA lost unsent pings on reload.** The buffer was an in-memory ref; a reload remounted with an empty buffer and the sequence restarting at 0. | **Done.** Pings persist to IndexedDB **the moment they are recorded** (`pending` store), batches are cut atomically across `[pending, batches, meta]`, the per-trip sequence and cumulative watermark counters (`batchesCut`, `pingsRecorded`) survive reload, and the tracker drains leftovers on mount — into the ended-trip recovery window or server-side quarantine, both ACKed. A Web Locks single-writer guard stops a second tab from double-cutting the same pings. The driver ends an incomplete trip only through an explicit warning, and the end request records `client_complete: false` (RM3's incompleteness marker). **Review-hardened (9 Aug 2026 second pass):** storage and the cross-tab lock now fail CLOSED — no IndexedDB (or a mid-trip write failure) blocks starting/pauses tracking and the end watermark never claims completeness a healthy queue can't vouch for; missing or denied Web Locks disables both tracking and the End action in that tab; stranded previous-session data retries on a 60 s recovery loop and on browser `online`, not once per mount. Component-tested (storage failure, lock absence/denial, watermark honesty, recovery retries). This is now part of the D18 pilot PWA's production baseline. | ~~Before real-driver GPS~~ Closed |
| **RM6** ✅ **[FIXED 20 Aug 2026; HARDENED 21 Aug 2026]** | G1 | RESOLVED — PKG-01 MNY-06A/B/C + PKG02-C1 | **Former defect:** one admin could mutate a rule and recompute historical earnings without immutable terms, a separate approver or value-complete evidence. | **Done.** Migrations `0018`–`0021` add append-only effective-dated revisions, acceptance-time bindings with frozen rates/cap/resolved eligibility and premium/exclusion geometries, and maker-checker correction orders. PKG02-C1 adds one DB clock/shared acceptance-publication lock, freezes nullable accepted campaign windows in `0026`, makes populated financial downgrades fail closed and serializes adjacent-day cross-midnight corrections through stable trip locks. Direct recompute is retired; creator self-approval is rejected below the API, stale projections re-review, positive deltas require their own release time, execution is idempotent, and driver/admin explanations use persisted tier components that reconcile to the authoritative ledger amount. | ~~Before pilot launch~~ Closed |
| **RM7** ✅ **[FIXED 16 Aug 2026]** | H2 (partial) | RESOLVED — PKG-01 FND-07 | **Exclusivity races surface as 500s.** The four exclusivity indexes exist and hold (see D13 rejected list), but their names were absent from `EXPECTED_UNIQUE_CONSTRAINTS` (`db/integrity.py`), so a lost race raised an unhandled `IntegrityError` instead of a clean 409. | **Done.** The four constraint names are registered in the integrity classifier (Postgres constraint-name and SQLite column-tuple paths) and the exact write sites that can enter an exclusivity index domain translate a lost race to the same stable 409 code as its guarding pre-check: assignment create → `DUPLICATE_CAMPAIGN_VEHICLE_ASSIGNMENT`, assignment activate → `ACTIVE_ASSIGNMENT_EXISTS_FOR_VEHICLE`, trip start → `ACTIVE_TRIP_EXISTS_FOR_DRIVER`/`ACTIVE_TRIP_EXISTS_FOR_VEHICLE` (accept/deactivate/cancel cannot enter a new index domain). Any other integrity failure re-raises untouched. Evidence: `tests/test_integrity.py` classifier coverage plus `tests/test_exclusivity_conflicts.py` — pre-check-defeated API lost-race envelopes and PostGIS two-transaction `asyncio.gather` races (one winner, coded 409 loser); no contract change (regenerated `openapi.json` byte-identical). | ~~Before pilot launch~~ Closed |

### 35.2 Specification requirements for unbuilt domains (fix in the owning slice)

| ID | Origin | Status | Requirement | Owning section / slice |
|----|--------|--------|-------------|------------------------|
| **RM8** | F02/G4 | PARTIAL — MNY-08A/B/C assessment, review, hold and driver dispute flow delivered; release remains | One versioned/fingerprinted `fraud_assessments` row distinguishes successful-current clean/flagged results from pending/error/stale attempts. MNY-08B adds serialized `open → acknowledged → confirmed \| dismissed`, coherent reviewer evidence, non-terminal dedup and one shared `hold_active` predicate for every money consumer. Shared/exclusive reconciliation gating closes cross-trip detection-versus-money races; only dismissal removes the hold. MNY-08C adds sanitized owner-only reasons/disputes and deduped transactional outcomes without exposing internal evidence. | MNY-03A must consume the same successful-current assessment plus `hold_active` contract for idempotent clean release, seven-day escalation without auto-release and post-release recommendations. | §17, **MNY-03A — before money release** |
| **RM9** ⚠ **[PARTIALLY RESOLVED — MNY-09A 21 Aug 2026]** | G2 + F17 | DESIGN-GAP (irreducible); copied-route software control delivered | GPS proves a *driver-controlled phone* moved, never that the *approved branded vehicle* moved. MNY-09A now detects identical-payload and time-shifted cross-trip/account route replay as bounded, reviewable evidence, with same-trip retry and same-driver-repeat guards. This does not prove vehicle/display identity. | **Done in MNY-09A:** indexed/versioned copied-route detection feeding the existing assessment contract, never a second hold predicate. **Remaining:** bind assignment → one device + one vehicle; server-nonce start-of-shift proof-of-display; periodic evidence renewal for high earners; randomized physical spot checks; hold the day on a missed challenge or concurrent session. Native attestation improves signal quality only — never treat it as proof the advertised vehicle moved. | §17/§19/§21, before pilot |
| **RM10** | F05/G3 | DESIGN-GAP | Payout batches have no finality contract: no reserved state, no one-active-line-per-entry constraint, no frozen payee/amount snapshot/instruction fingerprint, no provider idempotency/reference, no per-line bank outcome, no reconciliation-before-`paid`. | `draft → reserved → submitted → reconciled/completed | failed | void`; atomic reservation with a DB constraint of one non-void line per ledger entry; snapshot verified bank-account version + beneficiary + amount; freeze/hash the provider instruction; unique idempotency key and external transfer reference per line; submit behind the approved adapter; mark paid **only** from signed-webhook or verified-poll line-level evidence; maker ≠ approver/reconciler. | §16.3, **S3** |
| **RM11** | F04 | DESIGN-GAP (**downgraded** from BLOCKER) | The reviewers' "paid reversal is never recovered" scenario is **not current code**: statuses are `pending/available/voided/reversed` with **no `paid`**, no payout run exists, and `AVAILABLE` is set only by the demo seed. The status-inheritance mechanism is real (`services/payouts.py:2326-2331`) and correctly nets reversals within their bucket. It becomes a genuine defect only when S3 introduces cash payment. | When S3 lands: define `earned_net`, `released_available`, `cash_paid`, `carry_forward_debt`, `batch_payable`; post post-payment corrections to a carry-forward debit bucket and allocate future available credits against it; property-test "posting a reversal never increases any balance" across the payment boundary. Never model a new cash obligation as already paid. | §16.2/§16.3, **S3** |
| **RM12** | G5/F08 | DESIGN-GAP | Nothing bounds driver liability by confirmed funding: invoice status proves an advertiser price was paid, §15.5 separates spend from driver cost, D4 caps per driver-day but not per campaign, and Q9 expansions apply immediately. Commercial terms are also not effective-dated, so recompute can price past work under never-accepted terms (compounding RM6). | Immutable campaign financial authorization (funded amount, approved subsidy, max driver liability); reserve `rate × cap × covered vehicle-days` at offer/assignment activation; Q9 expansions apply immediately only inside pre-funded headroom, else `pending_funding`; block new sessions past the reserve while honouring hours already validly performed. Add effective-dated snapshots for offers, payout rules, zones, eligibility params, and tax/billing config; each eligible interval resolves the revision then in force. Keep the liability reserve distinct from advertiser budget/spend. | §15/§16.1/§21, **W2 entry** |
| **RM13** | G6, G7/F07, F06 | DESIGN-GAP | Three commercial-lifecycle contracts are missing: (a) **receipt identity** — no canonical external cash-receipt uniqueness, currency/amount match, or reconciled state, so one transfer can fund two obligations; (b) **cancellation** — no `financial_cutoff_at` that ingestion/classification/recompute/release all honour, and no settlement entity; (c) **activation** — campaign/assignment/installation/trip gates are described separately, not as one atomic invariant. | (a) One receipt = one immutable row (unique bank/provider transaction id, amount, currency, payer, evidence) with separate allocation rows; `observed → reconciled → confirmed | reversed`; activation counts only confirmed allocations; a reversal withdraws funding authority at a recorded cutoff. (b) One idempotent cancellation command under a campaign lock setting an immutable cutoff; clip payable intervals at it; append-only settlement revisions with unique external refund reference. (c) One atomic activation service that locks and re-reads every prerequisite and stores an activation snapshot; trip start rechecks campaign + assignment + approved evidence. | §15/§18/§21, **W2** |
| **RM14** | F16 | **SCOPE SUPERSEDED / DEFERRED BY D18** | This row was raised against D11's former native-in-MVP promise. D18 now makes the production screen-on PWA the pilot client and moves native background execution, native credentials/storage, OS termination, push and store-review evidence to Phase 2. The risk is deferred, not falsely closed. | Preserve RM14 as the Phase 2 native acceptance contract. Pilot readiness instead proves the D15/D16 PWA queue/seal, explicit Start/End and screen-on fail-closed behaviour across the §23 Android/iOS browser/device matrix, including permission/revocation, reload/offline/retry, storage/lock failure, visibility degradation, battery, accuracy, completeness and sync latency. | §23; D18; R14/W4 IDs repurposed to production-PWA proof |
| **RM15** | F09/F10/F11 | DESIGN-GAP | Privacy is treated as consent wording, not an operating model: no DPIA, ROPA, controller/processor allocation, or purpose-by-purpose lawful-basis matrix; **`k` counts distinct vehicles, which is not a valid anonymity claim** (a vehicle is a proxy for an owner-driver, not a data subject); the existing advertiser heatmap is exempt from the floor until a later release; retention beyond ping partitions is unscheduled and DSR/vendor/cross-border handling is incomplete. | Before any real-driver GPS: name controller/processor/privacy owner, complete a DPIA + ROPA, assign lawful basis per purpose, record notice/consent version + withdrawal. Before any advertiser heatmap: one central disclosure-control service on every query — coarse fixed cells/buckets, minimum vehicles **and** trips **and** days, contributor caps, complementary suppression, restricted filters, query-history limits, differencing tests; thresholds chosen from real pilot density; treat outputs as personal until a documented re-identification test says otherwise. Add a retention schedule per data class and a tested manual DSR runbook spanning DB, object store, device, logs, backups, and processors; keep a subprocessor/region register. | §22.2/§24, **before real GPS / before heatmap** |
| **RM16** | F12/F14/F15 | DESIGN-GAP | The sellable metric has a `formula_version` but no metric class, methodology, provenance, uncertainty, or reproducibility contract, and no proof-of-performance binding creative + installation + assignment + measured period. Module G's free-form source metadata would admit personal identifiers, and "audience/attribution" overclaims what route aggregates establish. | Publish a Measurement Methodology Contract: label MVP output **modelled potential contacts** (not verified views, reach, audience, or attribution); define the metric hierarchy, units, source provenance and vintage, missing-data rules, uncertainty, and correction/reissue policy; immutable `measurement_run` per issued report; proof-of-performance manifest. The default deliverable is **Campaign Performance Analysis**. A true ROI section fails closed unless advertiser conversion/revenue inputs and an approved reproducible ROI method are both present; otherwise omit ROI entirely. Constrain Module G to typed allowlisted aggregate planning fields with provenance/basis/expiry/DSR metadata; reject identifiers and free text; rename outputs to planning source / coverage cell / contextual follow-up recommendation. | §22.4/§27, D20, **before first issued report** |
| **RM17** | F18 | DESIGN-GAP — build foundation delivered; real-world validation deferred by D23 | W4 would otherwise defer the first production-like environment and physical-device PWA proof until the end, leaving no stabilisation runway. Store-review/background-native discovery is no longer a pilot risk. | PKG-01 verifies the provider-neutral edge/API/frontend/PostGIS/Redis/worker topology, release smoke, migrations and recovery contracts with synthetic data, and freezes the PWA ping/auth/seal/capability contract across deterministic desktop/mobile browser profiles. D23 keeps external staging deployment/restore and the representative Android/iPhone route/battery matrix explicitly NOT RUN until access exists; both still gate W4 release/pilot and real GPS. W4 becomes integration, physical validation, hardening, training and pilot, not first system build. Neither lane authorises real-data collection. | §23/§25/§31, D23; build now, physical/external validation before W4 pilot |
| **RM18** | F17 | DESIGN-GAP | KYC/financial/location controls are incomplete: malware scanning optional, NIN/BVN/bank fields unencrypted at field level with no key governance, raw-route/KYC reads unaudited, no breach workflow, and known audit gaps (auth.refresh, driver profile/assignment routes) remain open from D10(g). | Managed KMS + field encryption or vaulting for national/financial identifiers; mandatory type/size/malware checks on driver uploads; short-lived purpose-scoped GETs with privileged-read audit for raw routes and KYC; encrypted browser/PWA storage where sensitive state exists; log/notification redaction; close the D10(g) audit gaps; add incident contacts, breach register, and one tabletop drill. Native secure-store/push-specific controls remain Phase 2. | §12/§19/§23, **before KYC/PWA pilot** |

### 35.3 Live-use and dependent-action gates

These gates block the named **live or financially effective action**, not local
implementation or synthetic verification of the owning remediation slices.
For example, MNY-03A may build and test release scheduling after RM8, but no
real earnings may become available, be exported, or be transferred until the
whole G-money row is closed. W2 may build invoice and activation contracts with
synthetic/placeholding data, but cannot issue a real invoice, recognize
production spend, or activate a real campaign until G-commercial is closed.
The explicit dependencies in `docs/progress.md` still control build order.

| Gate | Blocks | Rows |
|------|--------|------|
| **G-money** | Any real earnings release, export, or transfer; owning slices may implement/test synthetically in dependency order | RM1, RM6, RM8, RM10, RM11 |
| **G-GPS** | Any real-driver tracking, PWA or native | ~~RM2~~ ~~RM3~~ ~~RM4~~ ~~RM5~~ (fixed), RM9, RM15 (privacy artifacts), RM18 |
| **G-commercial** | Real invoice issuance, production spend, or live campaign activation; owning slices may implement/test synthetically | RM12, RM13 |
| **G-advertiser** | Any live advertiser heatmap (**including the existing one**) or issued report | RM15 (disclosure control), RM16 |
| **G-moduleG** | Any live retargeting ingestion, display, or export | RM15, RM16 |
| **G-pilot** | Production pilot | all of the above + RM17 + the D18 production-PWA acceptance replacing RM14's former native gate |

## 34. Doc changelog

| Version | Date | Change |
|---------|------|--------|
| v1.35 | 2026-08-21 | **PKG02-C1 financial-authority hardening delivered.** Migration `0026` freezes nullable campaign payment windows on new payout-v3 bindings; legacy provenance fails closed. Assignment acceptance and payout-rule publication share a campaign transaction lock and PostgreSQL wall clock. Calculation, staleness, correction fingerprints and persisted money metadata use frozen windows, while v2 retains live-window sensitivity. Populated downgrades `0018`–`0021`/authoritative `0026` fail closed. Adjacent-day correction projection locks overlapping trips in stable UUID order before day-cap locks, then allocates chronologically. Focused migration, clock/window, nullable-metadata and opposing-order cross-midnight race evidence passed; one money/concurrency review's two medium findings were corrected once and rechecked RESOLVED. No API or external/live contract changed. |
| v1.34 | 2026-08-21 | **MNY-08C driver reasons, disputes and in-app outcomes delivered.** Migration `0025` adds owner-only one-per-flag disputes and typed transactional notices. Sanitized projections keep detector evidence, matched identities and internal review notes private; exact retries converge; confirmed/dismissed outcomes remain visible; replies remain separate from review notes; disputed flag provenance survives reconciliation. Corrected earnings explanations source the eligible/excluded pair from the same newest authoritative recompute and do not fall through on malformed newest provenance. Evidence: focused PostgreSQL privacy/idempotency/atomicity/concurrency tests, 25 focused frontend tests, type/lint, synchronized §9 artifacts, two-profile desktop/mobile live dispute→reply→reload, and privacy/security recheck RESOLVED after one combined correction round. No physical-device, route, staging, pilot or user-feedback validation is claimed. |
| v1.33 | 2026-08-21 | **MNY-08B serialized review and authoritative holds delivered; RM8 narrowed to release.** Migration `0024` adds coherent reviewer/time/note evidence, terminal `confirmed`, and non-terminal trip/type dedup for the exact `open → acknowledged → confirmed \| dismissed` graph. One shared predicate holds open, acknowledged and confirmed flags across impression, payout and later release consumers; only dismissal releases, and the payout-v1 floor cannot restore held pay. A shared/exclusive PostgreSQL reconciliation gate plus sorted affected-trip/fingerprint/row locks closes cross-trip detection-versus-money races; analytics recomputation enters the same scope before any write, closing the broader admin-versus-worker lock cycle. Exact retries converge, illegal/conflicting transitions fail, and review plus audit is atomic. The typed admin queue now acknowledges/resolves bounded evidence. Evidence: focused SQLite/Postgres suites including detector, money-holder and admin/worker races, migration fail-closed/downgrade and empty-cycle checks, 166 frontend tests, type/lint/build, two-project live seeded Playwright, synchronized §9 artifacts, and independent money/concurrency recheck RESOLVED after one combined correction round. No real-device, route, staging, pilot or user-feedback validation is claimed. |
| v1.32 | 2026-08-21 | **MNY-09A copied-route detection delivered; RM9 partially resolved.** Migration `0023` adds one current detector/config/analytics-bound replay signature per trip with indexed absolute-payload and time-shift-normalized fingerprints. One latest cross-account candidate per normalized group becomes privacy-bounded review evidence; same-trip retries and same-driver repeats alone do not flag. Sorted old/new group locks and DB-bounded reconciliation cover reverse processing, membership departure, scale and concurrent transitions. Failures remain due and no new hold predicate is introduced. Evidence: 165 focused SQLite and 189 focused Postgres tests, property/scale and pipeline coverage, seeded-data downgrade, empty migration cycle, filtered autogenerate-empty, ruff/diff clean, and independent fraud/privacy review RESOLVED after one correction round. The staged public enum movement was integrated with MNY-08B at v1.33. Derived replay hashes are classified as pseudonymous trip-linked location data for RM15 retention/DSR handling. |
| v1.31 | 2026-08-21 | **MNY-08A current fraud assessments delivered; RM8 partially closed.** Migration `0022` adds one versioned/fingerprinted current assessment attempt per sealed trip with explicit pending/clean/flagged/error states and current-flag count/update provenance. The DB-derived worker sweep reselects stale formula, analytics and flag inputs; only successful-current clean/flagged states qualify for the later release contract, while sanitized evaluation errors remain due. Named uniqueness convergence handles simultaneous workers. Evidence: empty migration upgrade and downgrade/re-upgrade at one head; 60 focused Postgres and 118 focused SQLite tests; ruff/diff clean; independent money/concurrency review findings corrected once and rechecked RESOLVED. No public API or §9 baseline change. MNY-08B/MNY-03A still own the serialized hold/release contract. |
| v1.30 | 2026-08-20 | **PKG-01 closed: parked-time payout and build-risk foundations delivered (D22/D23).** `stationary-rd-v1` freezes the reviewed 120-second/25-metre/2-confirm/1-release rule and complete common values for new payout-v3 acceptances, persists classifier/payout/correction evidence and driver/admin explanations, fails closed on unknown markers, and preserves payout-v1/v2 fingerprints. RM2 is closed. Deterministic PostGIS/frontend/build checks and the production-like desktop/mobile browser flow pass; API baselines did not move. R14-A/B and R17-A automated/synthetic build proofs are complete. Representative Android/iPhone physical/route/battery and approved external-staging validation remain explicitly NOT RUN and continue to gate later W4 real use. |
| v1.29 | 2026-08-20 | **Build-first versus real-world validation contract recorded (D23).** R14-A/R14-B close on deterministic capability, denial/revocation, queue/tracker, interrupted synthetic-flow and desktop/mobile browser-profile evidence; R17-A closes on provider-neutral production-compose, edge, smoke, migration and recovery-contract evidence. Representative Android/iPhone route/battery runs and external staging deployment/public-edge/restore evidence remain explicitly NOT RUN in `docs/progress.md` and still gate W4 real GPS, release and pilot acceptance. `EXT-STAGING-APPROVAL` remains missing; no device or deployment evidence is invented. The progress validator pins R17-A's build prerequisite as `none` while preserving the stable external ID and later live gate. |
| v1.28 | 2026-08-20 | **MNY-06A/B/C delivered; RM6 closed.** Effective-dated immutable payout revisions, acceptance-time `payout_v3` bindings with fully frozen rates/cap/eligibility and premium/exclusion geometries, shared chronological Lagos-day cap allocation, exact persisted tier components, and maker-checker correction orders replace mutable rule/recompute authority. Admin revision/correction UI and driver tier explanations shipped with migrations `0018`–`0021` and all three §9 baselines. Evidence on reviewed candidate `25fdd52`: PostGIS 562 passed (3 expected skips), migration up/down/re-upgrade + autogenerate-empty, frontend 155 tests/typecheck/lint/build, live-stack Playwright 22 passed, two-admin correction journey, and independent money/security, architecture/concurrency/frozen-terms and minimal-change reviews PASS. |
| v1.27 | 2026-08-16 | **R14-A production-PWA capability contract integrated (ADR 014, Pro contribution `bc64707` + review corrections).** New `r14-a-v1` contract module, authenticated `/driver/capabilities` probe surface and Playwright/vitest coverage freeze installability, screen-on, visibility, staged foreground location, IndexedDB/Web-Locks, BFF-session posture and the D15/D16 protocol constants (verified against the built queue — no drift, no API/schema movement). Independent PWA/security/architecture review drove two corrections integrated in the same commit: capture/`health=active` now requires a valid session or an explicit `activeTrip` continuation state (a fresh offline probe can never show capture-allowed/active), and probe-only wake-lock/Web-Locks "pass" is documented and displayed as capability evidence, never runtime lock ownership; ADR vocabulary split accordingly and a negative unauthenticated session-probe e2e added. §23 annotated. R14-A remains open pending representative Android/iPhone capability, denial and revocation evidence. |
| v1.26 | 2026-08-16 | **Delivery-control validator hardened; EXT-REPORT-METHOD moved to the live pilot gate (task-master correction, independently reproduced).** Six accepted bypass classes now reject mechanically: authoritative parsing runs on a sanitized view that blanks HTML comments and fenced code (unterminated comment or unclosed fence is itself an error); every authoritative section heading, boundary and controller field must occur exactly once at any heading level with exactly one table header per section; REVIEW packages need a runnable checkpoint and runnable work unless every owned item is DONE (consolidated closure review); packages after the active/paused frontier must be QUEUED or BLOCKED and QUEUED packages contain no DONE items; each package card's Owns range must equal its canonical checklist membership; the external register's 21 ids are pinned as ordered `CANONICAL_EXTERNAL_IDS`; a BLOCKED item must name exactly its missing direct external inputs. Gate correction per the register's own semantics: `EXT-REPORT-METHOD` is removed from W4-02B's build prerequisite (performance-only synthetic build/test was always permitted) and added to W4-03B's live pilot/issuance gate — first live issued methodology and conditional ROI remain fail-closed. No package status, pointer, or product checklist state changed. |
| v1.25 | 2026-08-16 | **RM7 closed (PKG-01 / FND-07): exclusivity races now return stable 409 envelopes.** The four vehicle/assignment/driver/trip exclusivity constraint names are registered in the `app/db/integrity.py` classifier (Postgres constraint-name and SQLite column-tuple paths), and the only write sites that can enter an exclusivity index domain — assignment create, assignment activate, trip start — translate a lost DB race to the same stable 409 code its pre-check uses (`DUPLICATE_CAMPAIGN_VEHICLE_ASSIGNMENT`, `ACTIVE_ASSIGNMENT_EXISTS_FOR_VEHICLE`, `ACTIVE_TRIP_EXISTS_FOR_DRIVER`, `ACTIVE_TRIP_EXISTS_FOR_VEHICLE`); every other integrity failure re-raises unhandled by design. Evidence: classifier unit coverage, pre-check-defeated API lost-race tests, and PostGIS two-transaction races (`tests/test_exclusivity_conflicts.py`); regenerated contract artifacts are byte-identical (no §9 baseline movement). §6.4 invariant 1 and the §35.1 RM7 row updated; header banner now lists RM6 as the last open live-code defect beside RM2's sub-window half. |
| v1.24 | 2026-08-14 | **Client-approved implementation clarification (D20) and direct-answer transcription correction.** Existing contracts now fix aggregate geography/time/context-only ad activation with identifier/person-level payload rejection; a standard exact 24-hour production wait with an immutable advertiser-requested expedited waiver whose refund effect begins only when production actually starts; and Campaign Performance Analysis as the standard report, with true ROI omitted unless conversion/revenue inputs and an approved reproducible method are present. Q1/Q28 current-state wording is corrected to the already-authoritative direct answers: one custom quotation per campaign and VAT-inclusive customer display with itemised net/VAT/gross. The existing W2/W3/W4 checklist items absorb the detail; no package, checklist identity, dependency, active status or external-register identity was added or reordered. |
| v1.23 | 2026-08-14 | **Direct client questionnaire reconciliation (D18/D19).** Somto's Q1–Q34 answer is the newest authority and supersedes conflicting defaults/proposal wording. The architecture now specifies `payout_v3` base/premium zone pricing, clean-immediate and flagged-seven-day-SLA release with no auto-release, automated provider disbursement, package/custom accepted terms, a 24-hour cash-allocation refund anchor, governed export/direct activation, Cardvert by Terrax Media, the Abuja 10-vehicle/5-advertiser/3-month pilot and client permit ownership. D18 moves native background tracking to Phase 2 and makes the production screen-on PWA plus real-device evidence the W4 pilot client; the nine-package/71-item control structure is retained. |
| v1.22 | 2026-08-12 | **Delivery-control integrity hardening.** The validator now pins all 71 checklist identities, package mappings and exact dependency contracts; zero-active pause requires a real missing blocker and no runnable work anywhere; and the pre-pilot acceptance gate now owns the four previously build-neutral but live-critical company, commercial, evidence-policy and legal/privacy inputs. CI push validation covers every branch. Synthetic/provider-neutral build entry remains unchanged. No product code, client UI/design or MVP scope change. |
| v1.21 | 2026-08-12 | **Owner-facing workflow simplified from 71 cycles to nine packages.** `docs/progress.md` now authorizes and reviews one of nine delivery packages at a time; the reviewed 71-item decomposition remains intact as a mandatory, dependency-aware acceptance checklist mapped exactly once across those packages. Package-safe blocker bypass, an internal checkpoint pointer and specialist high-risk checkpoint reviews preserve correctness without asking the owner to execute/review each microscopic item. Root `AGENTS.md` and the mechanical validator enforce package containment, promotion and closure. No product code, client UI/design or MVP scope change. |
| v1.20 | 2026-08-12 | **Delivery-control audit corrections.** Made `docs/progress.md` the exclusive execution authority; replaced serialization residue with canonical leaf/external prerequisites and explicit blocked/promotion/paused semantics; retained a disabled, owner-approvable disjoint second lane; recorded D17's one crypto-provider/ciphertext seam across MNY-10A and W2-02D; corrected the existing assignment-acceptance claim; and added mechanical queue validation to CI/pre-commit. Parent/leaf vocabulary, legacy aliases, coverage exclusions, external prerequisites and control-pointer rules are now explicit. No product code, client UI/design or MVP scope change. |
| v1.19 | 2026-08-10 | **Whole-catalogue review corrections.** Clarified §35.3 as live-action gates so owning money/commercial slices can be implemented and tested synthetically; made upload malware scanning mandatory/fail-closed; distinguished Q3's one-off online checkout from post-MVP recurring/automatic collection; added advertiser-company-profile placement. Delivery control expands from 67 to 71 leaves to own advertiser company details, account recovery/verified contact consent, driver vehicle-profile governance and a separately reviewable native release journey; file/KYC incident work is narrowed so W3 alone owns whole-platform privacy/DSR. Existing demo surfaces and the basemap licence prerequisite are explicitly live-gated. No product code or client visual-design change. |
| v1.18 | 2026-08-10 | **Complete delivery-control decomposition and adopted-decision reconciliation.** `docs/progress.md` now contains one 67-leaf executable path from the current repository to the full D11 MVP, with separate parent navigation, per-leaf outcome/dependency/acceptance/verification/review contracts, §35/proposal coverage proof, external prerequisites and one active leaf. Root `AGENTS.md` enforces leaf-only execution and reviewed promotion. Architecture wording is reconciled to already-adopted Q6–Q8/Q13/Q15–Q18/Q20–Q22/Q26/Q27/Q34: T+7 plus configurable weekly cadence (no invented Friday), manual reconciled pilot transfers per RM10/RM11, RM8 hold predicate, adopted approval/notification/matching/self-registration directions, and D15/D16 as the native client's built queue/seal baseline. No product scope or code change. |
| v0.1 | 2026-07-12 | Initial document: current state verified against branch `f7-hardening`. |
| v1.0 | 2026-07-12 | Target-state architecture added: Parts I–IV, principles P1–P12, target domains (worker, billing, payouts v2, fraud review, approvals, files, notifications, matching, audience, identity, data lifecycle, deploy, observability), placement map, roadmap waves, risk register, Q1–Q34 impact map. Current-state sections renumbered (old §2–§9 → §5–§12). |
| v1.1 | 2026-07-13 | Adversarial review round 1 (18 findings) applied: Part II pinned to commit `d9a989c` + F7-in-flight notice; F7 sliding session documented as `POST /auth/refresh`; fraud lifecycle reconciled with built statuses + dedup-index trap; heatmap grandfathered in privacy boundary; k = distinct vehicles; post-release flag reversal policy; Africa/Lagos cap day; N payments per invoice + `partially_paid`; presigned POST (not PUT) + CORS + lifecycle cleanup; partitioning moved to W1 pre-pilot; backup-retention + NDPR DSR runbook; health endpoints at edge; audit-invariant honesty note + W1 backfill; v1-questionnaire residue swept; placement-map rows added (DSR, quotes, refunds, BVN, password reset, WhatsApp opt-in). |
| v1.2 | 2026-07-13 | Adversarial review round 2 (12 findings, fresh reviewer) applied. Load-bearing fix: **automated trip-processing pipeline** added as the worker's first job (§14.2 — analytics→fraud→impressions→payout on trip end + uncomputed-trip sweep; previously the target automated only consumers of facts nothing produced). Also: daily-cap concurrency rule (advisory lock per driver/campaign/Lagos-day, midnight + recompute policy); ledger `paid` status flagged as a check-constraint migration; payee abstraction honouring Q23's no-rework promise; `trip_sessions` coordinates added to retention purge; W1/W2 ordering fixed (in-app notification slice into W1; files before creative approval in W2; stale W3 retention row removed); budget "spend" defined as a billing computation; webhook event-row rule generalised per domain; email restored as a first-class channel; campaign approval placed relative to `scheduled`; reversal-recommendation home + negative-balance rule; test count corrected to 190. |
| v1.3 | 2026-07-13 | Adversarial review round 3 (convergence gate; 4 blockers + 4 rideable) applied: reversal semantics reconciled with the built ledger (positive amounts, subtract-by-type netting in every summary — the naive design would have *added* money); §19 blocked-by corrected Q31→Q32; budget-rule and payout-floor [OPEN]s re-anchored (no numbered v2 question exists — confirm via decisions-log); `notifications` gains `provider_message_id` + `delivered` so §15.4 receipts are satisfiable; trip pipeline added to the §13 diagram; W1 retention-window dependency noted; `payout_calculations` v2 migration scope; changelog reordered. |
| v1.4 | 2026-07-20 | **F7 reconciliation.** Part II re-verified against the committed F7 delivery and the pin moved from `d9a989c` to `301519d`. Promoted to [BUILT]: sliding session + 12h cap + `sv` revocation + `must_change_password` + change-password endpoint (§6.3), Redis login rate limiting with trusted-edge gating (§6.3/§12), auth audit events + admin audit API/UI + `0012` indexes (§6.4.9), migrations `0011`/`0012` (§7.2), revision-gated backup/restore scripts (§7.2/§10.4), Sentry hooks both tiers (§10.4/§12), backend CI job with PostGIS+Redis services (§10.3), rich `f7_rich_v1` seed namespace (§11), driver `(portal)` route group + change-password/keepalive routes + `/admin/audit` (§8.3). Counts updated by command: 82 ops / 66 paths (was 79/63), 12 migrations, 209 backend test functions in 35 files, 32 vitest cases, 48 Playwright project-expanded tests in 6 specs. Staging deploy explicitly deferred (research only). Legacy sv-less-token residual risk documented (§6.3). |
| v1.5 | 2026-07-21 | **Worker substrate + automated post-trip processing [BUILT].** One arq worker (`app/jobs/worker.py`, new compose `worker` service, no host port) runs the §14.2 pipeline complete-missing-only — analytics→fraud→impressions→payout(+ledger, audited) for ended trips — via fail-open enqueue-after-commit on trip end (`app/core/trip_enqueue.py`) backstopped by a Postgres-derived cron sweep. New Settings: `WORKER_SWEEP_INTERVAL_MINUTES` (divisor of 60) and `WORKER_SWEEP_BATCH_SIZE`. No HTTP contract, schema, or migration change; admin endpoints unchanged as recompute tools. §6.5, §10.1, §14, §31 amended. Payout automation runs `payout_v1` as transitional infrastructure only — D2 (hourly pay) still pending Q4/Q5; not for production enablement. |
| v1.6 | 2026-07-22 | **Worker correctness repair.** Added all-current-calculation ledger healing, resumable keyset sweep traversal, named-constraint race convergence, stale-formula/source-fingerprint blocking, DB-clock injection, strict pre-socket Redis configuration, CI ARQ Redis coverage, Compose sweep-variable passthrough, and stackful Sentry reporting. No HTTP contract, schema, formula, or migration change. |
| v1.8 | 2026-07-30 | **S1 — Payout engine v2 [BUILT] (D2/D4/D8; Q4/Q5).** Migration `0013`: v2 rule fields (`hourly_rate_naira`, `daily_payable_hours_cap`, `eligibility_params`) + model XOR check, v1 columns relaxed nullable (history frozen), calculation `eligible_seconds`/`payable_seconds`/`excluded_seconds_by_reason`/`inputs_fingerprint`, one-trip_payout-per-trip partial unique index. Pure interval classifier (`payout_eligibility.py`, PAYOUT_ELIGIBILITY_* Settings, stay-point grace, target-zone-only geofence, null-accuracy excluded). Integer-seconds cap-before-price, single HALF_UP 2dp quantization (v1 stays HALF_EVEN, frozen); `pg_advisory_xact_lock` per driver/campaign/Lagos-day (zoneinfo). Per-rule formula dispatch; v2 write-once (drift → 409 flag, never auto-recompute; sweep/repair derive expected formula from the governing rule row). Recompute-day true-up (append-only adjustment/positive-reversal differentials) + §16.2 summary netting shipped same-change. Driver trip-breakdown endpoint + PWA screen; admin rule editor edits both models; reports formula-agnostic (latest calc per trip). §16.1→[BUILT], §16.2 netting [BUILT], §30 rows added, §16.1 recompute wording amended (day true-up is the sanctioned reallocation). Part II pin unchanged; Part III [BUILT] promotions are pinned by their changelog row. |
| v1.9 | 2026-08-03 | **S4 — Data lifecycle [BUILT] (Q31-param; §24.2, §6.4.9).** Migration `0014`: `location_pings` → monthly range partitions by `recorded_at` via rename-and-attach (legacy partition `[first month, next boundary)`, no row rewrites, composite PK `(id, recorded_at)`, full 0007 schema fidelity, frozen 4-month in-migration premake, no default partition) + append-only `data_purge_audit`. Daily worker crons: coverage-based idempotent premake (⚙ `PARTITION_PREMAKE_MONTHS` 4), coverage alarm (Sentry capture + re-raise), advisory-locked retention purge (⚙ `PING_RETENTION_MONTHS` 12; session lock on dedicated AUTOCOMMIT connection across `DETACH … CONCURRENTLY`; evidence-gated FINALIZE/orphan recovery; evidence-before-destruction; zero-remaining-pings batch purge). New `GET /api/v1/health/partitions` (503 when coverage < now+1 month; contract baselines moved). §6.4.9 audit backfill: trip start/end, analytics recompute, traffic profiles, impression estimates — atomic with mutation; ping-batch ingestion is an approved documented exception (`location_ping_batches` is the compensating evidence); route-table-driven coverage test added (residual gaps registered: auth.refresh, driver profile/assignment routes). Amendments: §24.2.2 `captured_at`→`recorded_at`; §24.2.1 trip_sessions-coordinate step deleted (no such columns); §24.2.4 dedicated purge table; §7.1 22 tables; §7.2 14 migrations (also corrects S1's missed 12→13 bump); §30 rows. ORM keeps composite PK without `postgresql_partition_by` (create_all test schemas); `env.py` filters runtime partitions from autogenerate. Known pre-existing model↔migration index drift outside S4 quarantined by name in the autogenerate gate. |
| v1.10 | 2026-08-04 | **D11 — realignment to the client-facing 5-month MVP proposal** (`docs/Mobility_AdTech_MVP_Proposal_5_Month_Retargeting.docx`, now the binding scope baseline). No code change; scope/roadmap amendments only. Driver mobile app (React Native/Flutter, background GPS, offline sync, push) moved from "Phase 2 (commissioned separately)" into the MVP window as new wave **W4** (§31) — D3's screen-on PWA remains the interim surface and its identical-backend-contract promise stands (§23 reworded). Retargeting scope extended to full proposal Module G (§22 intro rewritten; new §22.4 retargeting sources + follow-up insights; `retargeting_sources` added to §30; Q11's exposure-segment model and §22.2 privacy boundary unchanged; export still Q31-gated; no automated ad-platform push without client accounts/legal/budget). §2.2 end-state, §3 decision table (D3 annotated, D11 row), §30 rows, §31 W3/W4/Phase-2 split, A2 updated. Companion changes: `decisions-log.md` D11, `adopted-decisions.md` Q11, historical banners on `docs/build-loop/README.md` + `product-brief.md`, `project-reconciliation.md` authority row, root `README.md` doc map. |
| v1.17 | 2026-08-09 | **Independent post-implementation review of the v1.16 slice reconciled — 10 findings fixed (D16), RM3/RM5 re-closed.** Backend: pipeline recomputes same-version analytics that predate `sealed_at` (stale pre-seal results can no longer flow into write-once money); quarantine apply gated on the initial payout calculation existing (post-seal evidence affects money only via recompute-day, independent of worker timing); quarantine apply/discard serialize under `FOR UPDATE` with new resolution CHECK constraints; `active → ended` is a guarded UPDATE; migration `0017_seal_review_hardening` also inserts the missing `trip.sealed` audit events for 0016-backfilled trips; retention reports `quarantines_purged` explicitly on blocked runs. PWA: storage and Web Locks fail closed (no tracking without durable storage; End gated on lock ownership; mid-trip storage failure pauses tracking and forces an incomplete watermark); stranded data retries on a recovery loop + `online` events. Tests: +2 backend (stale-analytics recompute on PostGIS, apply-blocked), extended lifecycle purge/blocked-path coverage, migration-0017 upgrade test, 7 tracker component tests. Verified: full backend suite on PostGIS+Redis, 86 vitest, Playwright 49 green. |
| v1.16 | 2026-08-09 | **RM3/RM4/RM5 fixed — trip finality protocol + durable client queue (D15).** Migration `0016_trip_seal_protocol`: `trip_sessions` gains `sealed` status (+ `sealed_at`, `seal_reason`, client watermark columns; existing `ended` rows backfilled to `sealed`), new `quarantined_ping_batches` table, `data_purge_audit` event set extended with `quarantined_batches_purged`. Sealed is the sole money-chain trigger; `/end` carries the client finalization watermark and fast-seals when satisfied; late batches are accepted while `ended` and quarantined after sealing; worker seal sweep (`TRIP_SEAL_GRACE_SECONDS` ⚙ 600) force-seals expired ends; audited admin quarantine apply/discard endpoints (no auto-recompute); reports fold `sealed` into `ended` for consumers. PWA: IndexedDB durable queue with once-minted stable idempotency keys, atomic cuts, reload recovery, dead-letter classification, Web Locks single-tab guard, incomplete-end warning. Contract: three baselines moved. Verified: 465 backend tests green on PostGIS+Redis (incl. new `test_trip_seal.py`), 79 vitest, Playwright 49 green, live compose e2e (trip → watermark seal → worker payout → post-seal quarantine → admin apply) plus a browser-driven PWA trip. §14/§30/§35 amended. |
| v1.15 | 2026-08-06 | **RM1 fixed; RM2 half fixed (D14).** Migration `0015_payout_day_allocation` adds `payout_calculations.payable_seconds_by_day` (backfilled to the pre-fix start-day attribution). `classify_session` cuts the timeline at Africa/Lagos midnight and returns `eligible_seconds_by_day`; `calculate_trip_payout_v2` takes one advisory lock per touched day in sorted order and caps each day independently; `day_consumed_payable_seconds` counts overlapping trips by stored day allocation; recompute-day re-allocates only its own day. Stationary grace became a whole-session budget (RM2's renewable-exemption half). Fixed inside `payout_v2`, not `payout_v3`, per **D14** — no real payout has ever been computed, so the D9(a) freeze has nothing to protect yet. §16.1 amended; §35 RM1/RM2 rows updated. Verified: 455 backend tests green against PostGIS + Redis (8 new: 6 classifier property tests, 2 end-to-end cross-midnight cap tests), ruff clean. RM2's sub-window aggregation stays open as a money-policy decision (parked vs Lagos traffic). |
| v1.14 | 2026-08-06 | **D13 — independent review reconciled; §35 remediation register added.** Two external reviews (broad architecture + money-path red team) run on the doc packet, every code-checkable claim then verified against the implementation. New **§35** is the authoritative remediation list: §35.1 seven live defects in built code (RM1 cross-midnight cap allocation; RM2 stationary farming, worse than reported — sub-window stays never excluded; RM3 no trip seal, late batches rejected outright; **RM4 client regenerates the idempotency key per retry → double-insert**, found in verification, invalidates the red team's "replay prevented by design" row; **RM5 in-memory ping buffer loses points on reload**, found in verification; RM6 single-admin retroactive repricing with value-less rule audit; RM7 missing IntegrityError→409 mapping), §35.2 eleven specification rows for unbuilt domains (RM8–RM18), §35.3 six gates blocking dependent slices. New wave **W0** in §31 sequences the corrective work. Four findings rejected with recorded reasons (client-timestamp manipulation, assignment exclusivity, trip exclusivity — all already handled in code; post-payment reversal downgraded to an S3 requirement) — see decisions-log D13. No scope change. |
| v1.13 | 2026-08-04 | **D12 — hourly pay reconfirmed; translation contract stated.** Header banner now defines this doc as the binding architectural *translation* of the proposal's requirements — agents build from this doc; proposal-vs-architecture wording differences resolve only via decisions-log rows. R9 closed by D12 (earnings = hourly rate × verified payable hours; Module E's "mileage-based" phrasing is superseded requirement-era wording; client-comms residual with OJ). Also corrected the §3 D2 row's stale status cell, which still claimed `payout_v1` per-km was the built engine — `payout_v2` has been [BUILT] since S1 (v1.8). |
| v1.12 | 2026-08-04 | **Proposal coverage audit (D11 follow-through).** Feature-by-feature check of the proposal against this doc found two promised surfaces with no architecture home and one wording conflict. Added: §22.4 names **high-exposure zone insights** and the **exposure score** (`exposure_v1`, P6-versioned) as analytics surfaces over existing aggregates (k-floor applies); §30 rows for both + **CSV/PDF report export** (W4, worker-generated); §31 W3 contents updated. New risk **R9**: proposal Module E says "mileage-based earnings" while the pay model is hourly per client-sourced D2 (delivered `payout_v2`) — D2 stands; OJ reconfirms wording with the client; a reversal would be a new D-row + `payout_v3`. |
| v1.11 | 2026-08-04 | **Doc-system consolidation (no scope or design change).** Four-doc model adopted: proposal docx (scope) → this doc (design) → agent work → `docs/progress.md` (delivered summary), with `docs/decisions-log.md` as the decisions input. Concretely: `adopted-decisions.md` merged into `decisions-log.md` as its Part 2 (Q-status references here updated; historical changelog rows below keep the old filename); `project-reconciliation.md` replaced by `docs/progress.md` (delivered-vs-promise summary incl. proposal module A–G mapping); `fablev1-work.md` journal and the v1 questionnaire moved to `docs/archive/`; README doc map rewritten around the model. Older rows citing the pre-merge filenames describe the state at their date. |
| v1.7 | 2026-07-27 | **D8 — questionnaire resolved by adopted defaults.** Client unresponsive; best-practice defaults adopted for Q1–Q34 where a defensible standard exists (source of truth: new `docs/adopted-decisions.md`; client-facing `docs/Mobility_Working_Decisions_and_Open_Items.docx` supersedes the questionnaire). [OPEN] tag definition and §33 preamble now defer per-question status to that file, including this doc's "Blocked-by: Q…" headers and "until answers land" prose (§15's block amended directly); the §33 table is retained as the Q→section routing map. Q23 (owner-drivers) is CONFIRM-PENDING — §16.3 payee abstraction stays mandatory. Q11/Q34/Q13 adopted directions match the doc's existing proposed defaults (anonymised segments with export gated on Q31; in-app + advertiser email + ops WhatsApp; driver self-registration narrowing D1 to advertisers/orgs — §3 D1 row annotated). No tag promotions in the body: adopted ≠ built; [TARGET] sections build in their planned phases. Pre-existing "OJ approval" SOP references corrected to the actual flow (plan → adversarial review → reconcile — no human gate; §13 intro, §10.4, §31). |

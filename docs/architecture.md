# Mobility AdTech Platform — System Architecture

**Version 1.4 — 2026-07-20. Canonical source of truth: current state AND target state.**

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
| **[OPEN]** | Awaiting client (Somto) answers to `docs/Mobility_Product_Direction_Questionnaire_v2.docx` (Q1–Q34), or otherwise undecided. | Do not hard-code assumptions. Flag any design that would foreclose the open options. |

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
- **"What exists today?"** → Part II (§5–§12).
- **"How should I build the next phase?"** → §31 roadmap, then the relevant Part III section.
- **"What can't be decided yet?"** → §33 open questions.

---

# PART I — PRODUCT INTENT

## 2. Purpose, scope, and end state

### 2.1 What the product is (from the client brief)

A mobility advertising platform for the Nigerian market (working name **Vantage**;
real brand [OPEN] Q29): advertisers run geo-targeted ad campaigns on shared-ride
vehicles; drivers carry the branding, drive with GPS trip tracking, and earn
payouts; operators (admins) onboard everyone, approve what goes live, review
fraud, and move the money. The engine computes route analytics, impression
estimates, fraud flags, and payouts from GPS data over PostGIS.

### 2.2 The intended end state

From the developer brief + decisions D1–D7 + questionnaire v2, the finished
product is:

1. **Advertiser side** — self-serve portal: campaigns with zone targeting,
   creative upload with ops approval, attribution reports, exposure heatmaps,
   quotes/invoices, prepaid funding (gateway later), budget enforcement.
2. **Driver side** — installable app (PWA now, **native app phase 2** with
   background GPS — same API contract), campaign offers with transparent hourly
   pay + daily payable-hours cap, trip tracking, earnings ledger with
   release-schedule payouts, dispute channel.
3. **Operator side** — the control plane: onboarding (KYC depth [OPEN] Q26),
   campaign/creative approval queues, installation photo verification,
   assignment with competitor separation, fraud hold-and-review, payout release +
   disbursement, audit trail.
4. **Platform layer** — notifications (in-app + WhatsApp/SMS), payment collection
   and disbursement integrations (Paystack/Flutterwave family, [OPEN] Q3/Q27),
   NDPR-compliant data retention, offline-to-online **retargeting** on anonymised
   exposure aggregates (D6, shape [OPEN] Q11).
5. **Future layers** (post-MVP, explicitly out of current scope): edge-AI
   vehicle/pedestrian counting; multi-city scale-out; audience attribution
   network.

### 2.3 Scale honesty

Pilot shape ([OPEN] Q30, proposed): **one city, 25–50 vehicles, 2–3 advertisers,
8–12 weeks.** Every sizing decision in this doc is made for that scale with a
stated path to ~10× (500 vehicles, multi-city), and **no further**. We do not
design for imaginary web scale (see P1, §4).

---

## 3. Product decisions & constraints

Confirmed decisions live in **`docs/decisions-log.md`** (D1–D7, append-only,
supersede-never-edit). Summary with build status:

| # | Decision | Status vs code |
|---|----------|----------------|
| D1 | **Operator-led onboarding** — no self-serve signup; admin creates users/orgs | [BUILT] matches (§6.3). Driver self-registration remains [OPEN] (Q13) |
| D2 | **Driver pay = fixed hourly rate** (naira/hour × verified payable time) | [TARGET] §16 — the built engine (`payout_v1`) is still per-km + bonuses. Don't extend v1's rate components; don't hard-code either model into new surfaces |
| D3 | **Screen-on MVP tracking** — installable PWA, phone mounted; native app phase 2, identical backend contract | [BUILT] matches (§8.6); native-app readiness rules in §23 |
| D4 | **Payable-hours cap** per campaign/driver/day, shown in driver's offer | [TARGET] §16, part of the payout v2 rework |
| D5 | **Hold-and-review fraud posture** — flags hold earnings for admin review; multipliers become secondary | Flags + multipliers are [BUILT]; the hold/review/dispute workflow is [TARGET] §17 |
| D6 | **Retargeting is in the MVP** (shape open → Q11) | [TARGET] §22; privacy boundary fixed now, product shape open |
| D7 | **In-platform creative upload** (pending approval, Q18) | [TARGET] §19; creatives stay metadata-only until built |

Hard constraints (violating any of these is an architecture change, not a feature):

- **No realtime push** — no WebSockets/SSE ([BUILT] §6.5; reaffirmed for target, §14.4).
- **No file upload/storage pipeline** until §19 is built as a phase (D7 pending).
- **Operator-led** — no self-serve registration of any kind today.
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
  messaging, object storage, map tiles: services depend on a small interface;
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
- Do not add other claims named `sv`. Auth evolution beyond F7 (native-app
  refresh grants, password reset): §23.

### 6.4 Cross-cutting API conventions — INVARIANTS **[BUILT]**

Every new endpoint must obey all of these:

1. **Error envelope.** All errors — `AppError`, HTTP exceptions, validation — are
   rendered by the handlers in `app/core/errors.py` as:
   ```json
   { "error": { "code": "...", "message": "...", "details": {}, "request_id": "..." } }
   ```
   Raise `AppError(code, message, status_code=..., details=...)` in services;
   never hand-roll error JSON. Validation failures return 422 with code
   `VALIDATION_ERROR`.
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
   indexes (migration `0012`). Honesty note: the invariant still does not hold
   everywhere — trip start/end (`api/v1/trips.py`), analytics recompute
   (`api/v1/trip_analytics.py`), and traffic-density/impression flows
   (`api/v1/impressions.py`) write no audit events. Backfilling these is a W1
   chore (§31); do not copy their omission.

### 6.5 Background / async story **[BUILT]**

**One arq worker — everything else strictly request/response.** No Celery, no
`BackgroundTasks`, no schedulers in the web process, no WebSockets, no SSE.
<!-- verified: grep BackgroundTasks|celery|websocket app/ → 0 hits -->
Until this change the story was "none — strictly request/response"; the §14
trip-processing pipeline is now **[BUILT]**: one arq worker (`app/jobs/*`,
compose service `worker`) completes missing analytics/fraud/impression/payout
rows for ended trips, fed by a fail-open enqueue-after-commit on trip end
(`app/core/trip_enqueue.py`) and backstopped by a Postgres-derived cron sweep.
Admin recompute endpoints remain the synchronous recompute/override tools.
Redis's consumers: **[BUILT] F7 login rate limiting** (`app/core/rate_limit.py`
— disposable counters, fail-open per P2) and **[BUILT]** the arq queue (also
disposable — the sweep re-derives work from Postgres). Do not introduce
queues/realtime ad hoc — §14 remains the one sanctioned design.

## 7. Data model

### 7.1 Entities **[BUILT]** — 21 tables

<!-- verified: grep -h "__tablename__" app/models/*.py | wc -l → 21 -->

Identity & orgs:

| Table | Purpose / key relationships |
|-------|------------------------------|
| `users` | All humans; `role` ∈ admin/advertiser/driver (check constraint); argon2 hash; status lifecycle; F7 adds `must_change_password` + `session_version` (migration `0011`) |
| `advertiser_organizations` | Advertiser tenant; currency; status |
| `organization_memberships` | user ↔ advertiser_organization, with membership role/status |
| `audit_events` | Append-only audit trail; `actor_user_id → users` (SET NULL); F7 adds created_at/action/entity query indexes (migration `0012`) |

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
| `trip_sessions` | A tracked drive under an assignment; denormalized FKs to campaign/driver/vehicle; **PostGIS `geometry(Point,4326)`** columns |
| `location_ping_batches` | Idempotent ingestion envelope (unique trip+key, payload hash, accepted count) |
| `location_pings` | Individual GPS points per trip/batch |

Derived (analytics → money):

| Table | Purpose / key relationships |
|-------|------------------------------|
| `trip_analytics` | Per-trip route metrics (distance, active time, zone overlap), `formula_version` |
| `fraud_flags` | Typed/severity-classed flags against trips; links to trip_analytics. Status lifecycle `open \| acknowledged \| dismissed` (`ck_fraud_flags_status`); partial unique index `uq_fraud_flags_trip_open_flag_type` dedupes per flag type **only while `status='open'`** |
| `traffic_density_profiles` | Admin-managed density inputs for impression math |
| `impression_estimates` | Per-trip estimated impressions + confidence, links density profile |
| `payout_calculations` | Per-trip payout math snapshot (rule inputs + fraud multipliers) |
| `earnings_ledger_entries` | Driver earnings ledger (typed, statused entries) |

Notes:
- PostGIS columns use **hand-rolled `UserDefinedType`s** (`PostGISPoint`,
  `PostGISMultiPolygon`) that compile to `TEXT` on SQLite for unit tests — the
  project deliberately does **not** use GeoAlchemy2. Follow the same pattern for
  new geometry columns.
- All PKs are UUIDs with `gen_random_uuid()` server defaults; timestamps are
  timezone-aware with `func.now()` defaults; enums are Python `StrEnum` + DB
  check constraints (not native PG enums).
- The derived chain is **trip_sessions → trip_analytics → (fraud_flags,
  impression_estimates) → payout_calculations → earnings_ledger_entries**; each
  step stores enough FK context (campaign, driver, vehicle) to be queried
  independently.
- Target-state table additions (billing, notifications, files, audience, jobs)
  are specified in their Part III sections and indexed in §30.

### 7.2 Migration policy **[BUILT]**

- Alembic, 12 linear migrations `0001`–`0012` (extensions → identity/orgs →
  drivers/vehicles → campaigns/creatives → zones → assignments → trip tracking →
  analytics/fraud → impressions → payouts → F7 password management → F7 audit
  indexes). <!-- verified 2026-07-20: ls alembic/versions → 12; alembic heads → single head 0012 -->
- `0001` enables `pgcrypto` + `postgis`.
- Shipped migrations are frozen history: schema changes come as **new**
  migrations, never edits to existing ones (per-slice migration tests
  `tests/test_migration_slice*.py` pin the existing chain;
  `tests/test_mvp_hardening.py` pins the single head).
- **[BUILT]** Revision-gated restore: `scripts/db_restore.sh` restores into a
  temporary database, validates the dump's Alembic revision against the
  checked-out head (refusing unknown revisions; older ones need `--upgrade`),
  and only then swaps it into place. Exercised by a local drill — it is **not**
  a CI job.

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
  Screen-on tracking posture per decision D3 (no native app, no background
  tracking in MVP).

## 9. API contract discipline

**[BUILT]** Three baselines exist and must move together on any contract change:

1. `openapi.json` (repo root) — the committed contract, source for type generation.
2. `frontend/src/lib/api/schema.d.ts` — generated types (`npm run api:types`).
3. `docs/api/openapi.snapshot.json` — pretty-printed, key-sorted snapshot
   (regeneration snippet in README §"MVP Contract Baseline"). Currently
   semantically identical to `openapi.json` (formatting differs by design).

**CI drift gate [BUILT]:** the frontend workflow regenerates `schema.d.ts` from
the committed `openapi.json` and fails on any diff ("Contract drift check" step
in `.github/workflows/frontend.yml`). Backend contract tests
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
| `worker` | repo `Dockerfile`, `arq app.jobs.worker.WorkerSettings`, source bind-mounted | — (none) | shared `x-backend-env` anchor; depends on db, redis; post-trip pipeline + sweep (§6.5, §14) |
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

One workflow: `.github/workflows/frontend.yml` (push triggers on `master`,
`main`, `frontend-*`, `f7-*`; paths include `frontend/**`, `app/**`,
`alembic/**`, `tests/**`, `openapi.json`, `pyproject.toml`,
`docker-compose.yml`, and the workflow itself; plus all pull requests).

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
- **[BUILT] (F7)** Database backups (`scripts/db_backup.sh`, custom-format
  dumps, 14-dump retention) and temp-DB restore verification with an Alembic
  revision gate (`scripts/db_restore.sh`); Sentry browser DSN passed as a
  Docker build arg (`NEXT_PUBLIC_SENTRY_DSN`); backend/frontend `SENTRY_DSN`
  runtime knobs, inert when empty.
- **[PLANNED-F7 → deferred]** Staging deploy did **not** ship: staging is
  research only (`docs/staging-options.md`), gated on OJ's written approval.
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

Security architecture beyond F7 (webhooks, uploads, native apps, privacy,
password reset): the relevant Part III sections.

---

# PART III — TARGET ARCHITECTURE

Everything in this part is **[TARGET]** unless tagged otherwise. Shapes are
decided; parameters marked [OPEN] await client answers (§33). Nothing here is
built ad hoc — each numbered area becomes one or more planned build phases (§31),
each of which goes through the plan → adversarial review → OJ approval SOP.

## 13. Target system overview

```
   Advertiser browser        Admin browser          Driver phone
        │                        │                 ┌───────────────────────┐
        │                        │                 │ PWA (now)             │
        │                        │                 │ Native app (phase 2,  │
        │                        │                 │ background GPS)       │
        └───────────┬────────────┘                 └───┬───────────────┬───┘
                    │ HTTPS (cookie session)           │ PWA: cookie   │ native: bearer
        ┌───────────▼───────────────────────────────── ▼──────┐        │ + refresh (§23)
        │            Next.js BFF (unchanged pattern)          │        │
        └───────────┬─────────────────────────────────────────┘        │
                    │ bearer, internal                                  │
   ┌────────────────▼──────────────────────────────────────────────────▼─────┐
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
first job is the **trip-processing pipeline**: on trip end, enqueue
compute-analytics → detect-fraud → estimate-impressions → calculate-payout for
that trip, backstopped by a DB-derived sweep for ended-but-uncomputed trips
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
(§14.2), are now **[BUILT]** per the §14.3 rules — idempotent
complete-missing-only stages (`app/services/trip_processing.py`), a
Postgres-derived sweep with the trip-end enqueue as latency optimization only
(rule 2; `app/core/trip_enqueue.py`), thin job wrappers (rule 3;
`app/jobs/trip_processing.py`), structured per-run logs + Sentry (rule 4). Its
payout stage runs `payout_v1` as transitional orchestration only — not the
approved payment model (D2 hourly pay, Q4/Q5 pending). All other consumers —
§15 (webhooks), §16 (payout release), §20 (notifications), §24 (retention) —
remain [TARGET]. Redis remains disposable.

## 15. Money in — billing, payments, invoicing

Blocked-by: Q1 (pricing structure), Q2 (when advertisers pay), Q3 (payment
methods), Q14 (quotes/invoices in-platform?), Q28 (VAT/invoice details), Q24
(cancellations/refunds). The **shape** below is fixed; the parameters are not.
**Do not build this domain until Section A answers land** — but no new feature
may conflict with it.

### 15.1 Domain boundary

New service module `app/services/billing.py` + models in
`app/models/billing.py`. Nothing outside this module computes what an advertiser
owes. Campaign "cost summary" reporting (built, presentation-side) stays
presentation-side and reads billing facts once they exist — the current reports
must not grow invoicing logic.

### 15.2 Data model (shape)

| Table | Purpose |
|-------|---------|
| `invoices` | What an org owes for a campaign/period: line items (JSONB), currency, VAT treatment ([OPEN] Q28), status `draft → issued → partially_paid → paid → void`, issued/paid timestamps, human-readable invoice number (sequential per org, format [OPEN] Q28) |
| `payments` | Money received against an invoice — **N payments per invoice** (deposits and balance payments are the likely Q2 answer; the model must not assume one-shot payment): amount, method (`manual_transfer` \| `gateway`), provider + provider reference, status, `recorded_by_user_id` for manual entries. An invoice's paid state derives from the sum of its confirmed payments |
| `payment_events` | Raw webhook/event log from gateways: provider event id (**unique** — replay protection), payload, processing status |

Rules: amounts are `Decimal` (strings on the wire, P6); invoices are immutable
once issued (corrections = credit-note-style new rows); every state change
audited (§6.4.9).

### 15.3 Provider adapter (P5)

`app/adapters/payments/` defines one interface (`create_checkout`,
`verify_transaction`, `parse_webhook(payload, signature) → event`) with
implementations per provider (Paystack and/or Flutterwave — [OPEN] Q3) plus a
`manual` no-op used at pilot. Services import the interface, never a vendor SDK.
Provider selection via Settings.

**Pilot reality (per proposed defaults):** launch is manual bank transfer — an
admin records a `payments` row against an issued invoice; campaign funding
status derives from `invoices.status`. The gateway adapter is a fast-follow that
slots behind the same interface with zero service-layer change.

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

### Relation to current code

Additive domain. Preserve: campaigns, reports, cost summaries as built. Refactor
trigger: when Q1/Q14 land, the campaign creation wizard gains a
pricing/package step — extend the wizard, don't fork it.

## 16. Money out — payout engine v2, release, disbursement

Blocked-by: Q4 (uniform vs per-campaign hourly rate), Q5 (what counts as a
payable hour), Q22 (release schedule + corrections), Q27 (disbursement channel),
D2/D4 (decided: hourly × verified payable time, daily cap).

### 16.1 Payout engine v2 (D2, D4)

- New formula version **`payout_v2`** computing: `hourly_rate × verified_payable_hours`,
  where payable hours are derived from trip analytics active time under
  verification rules ([OPEN] Q5 — e.g. movement thresholds, zone requirements)
  and capped per campaign/driver/day (D4).
- **Trigger:** v2 calculations are produced by the worker's trip-processing
  pipeline (§14.2) automatically on trip end — not by admin action. The admin
  "process trip" endpoints stay as recompute/override tools.
- **Cap concurrency:** the daily cap is a cross-trip invariant, and §25.3
  sanctions concurrent workers — two same-driver trips computed concurrently
  must not jointly exceed the cap. Rule: payout computation for a trip takes a
  **Postgres advisory lock on (driver_profile_id, campaign_id, Lagos-day)** for
  the read-remaining-cap → write-calculation critical section. A trip spanning
  Lagos midnight bills against the day its trip **started**. Recomputing an
  earlier trip never retroactively reallocates cap already consumed by later
  immutable calculations (P6) — the recompute uses the cap remaining at
  recompute time and flags any discrepancy for admin review.
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

**Preserve / replace:** the v1 engine code stays (history, and Q4/Q5 could still
surprise); v2 is a parallel code path selected by the rule row's model. The
admin payout-rules editor UI ([BUILT], F6) is **refactored** to edit either
model.

### 16.2 Release scheduling (Q22)

Ledger entries post as `pending` (built). Target adds a **release policy**
(proposed default: weekly, T+7 after trip, Fridays — [OPEN] Q22) executed by a
worker sweep (§14.3.2): move `pending → available` for entries past the window
**with no open fraud flags/holds** (§17). Policy parameters live in Settings
until the client wants per-campaign overrides (P10).

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
change. A netted balance may go negative; it offsets against future earnings —
never a collections flow. Money is never clawed back automatically
([OPEN] Q21/Q22 whether the client wants auto-reversal later).

### 16.3 Disbursement (Q27)

- Pilot (proposed default): **ops-run weekly bank transfers** — admin generates a
  payout run from available balances, exports it, marks entries `paid` with a
  reference. This needs: a `payout_batches` table (run id, period, totals,
  status, `created_by`) + batch line items referencing ledger entries + an admin
  UI. **Schema note:** `paid` is a new ledger status — the current check
  constraint allows exactly `pending | available | voided | reversed`
  (`ck_earnings_ledger_entries_status`), so this ships with a migration
  extending it; an entry is `paid` iff it belongs to a completed
  `payout_batches` line item carrying the transfer reference. No provider
  integration required to launch.
- **Payee abstraction (Q23):** the questionnaire promises the client that fleet
  ownership (vehicle owner ≠ driver) can be added later **without rework**.
  Honouring that: batch line items and bank/BVN details attach to a **payee**
  reference that at pilot is always the driver profile — so a later
  `fleet_owner` payee type extends the enum instead of reworking the money-out
  path. Do not scatter `driver_profile_id` assumptions through disbursement
  code.
- Fast-follow: **Paystack Transfers** (or equivalent, [OPEN] Q27) behind
  `app/adapters/disbursement/` implementing `initiate_transfer` /
  `verify_transfer` — slots into the same batch flow; bank-account +
  BVN collection on the driver profile becomes a prerequisite ([OPEN] Q26 KYC
  scope).
- Ledger corrections (Q22): adjustments/reversals as **new typed ledger entries**
  by named admins with mandatory reason + audit — never edits (P6). This is
  mostly built; the policy (who, SLA) is [OPEN].

## 17. Fraud review & trust workflow (D5)

Blocked-by: Q21 (consequences/strikes policy), Q22 (interaction with release).
Shape fixed by D5: **hold-and-review**.

- `fraud_flags` review lifecycle built on the **existing** statuses
  (`open | acknowledged | dismissed`, §7.1): `acknowledged` becomes the
  "under review" state, and a migration extends `ck_fraud_flags_status` with a
  terminal `confirmed`; add `reviewed_by_user_id`, `reviewed_at`,
  `resolution_note`. Extend the existing status/severity fields — no parallel
  flag tables. **Dedup trap:** the unique index only guards `status='open'`
  rows — moving a flag out of `open` lets re-detection insert a duplicate of
  the same type; the review migration must extend the index predicate (or the
  detection service must check non-open flags) in the same change.
- **Holds:** a trip with open flags above a severity threshold ([OPEN] Q21)
  holds its ledger entries (`pending` entries excluded from release, §16.2) —
  implemented as a release-sweep predicate, not a new ledger state, until the
  client asks for an explicit `held` display state.
- New `/api/v1/admin/fraud-flags/{id}/review` endpoints (acknowledge, resolve);
  the read-only admin fraud console ([BUILT], F5) becomes a working queue.
- Driver-facing: flagged trips show reason + status in the driver app; dispute
  channel = notification + free-text driver response recorded against the flag
  ([OPEN] Q21 whether WhatsApp supplements this).
- Strikes/escalation (auto-suspension after N high-severity flags): policy
  [OPEN] Q21 — implement as a worker sweep producing **recommendations for admin
  review** first; automatic suspension only if the client confirms it.
- Severity multipliers (0.9/0.7/0.25) remain configurable but secondary (D5);
  the minimum-payout-floor loophole (floor paid even on fully-discounted trips
  — real at the pin: `payouts.py` lifts `final_payout` to the floor whenever
  gross > 0) is closed as part of v2: floor applies only to trips with no
  confirmed/open flags ([OPEN] — maps to no numbered v2 question; confirm with
  Somto and record in `decisions-log.md`).

**Preserve:** detection engine (`trip_analytics` → `fraud_flags`) as built.
**Extend:** flag model + admin endpoints + release predicate. **Replace:**
nothing.

## 18. Approval workflows

Blocked-by: Q6 (campaign creation/approval flow), Q18 (creative approval), Q15
(activation requirements), Q17 (installation evidence).

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
  unapproved creative blocks campaign approval ([OPEN] exact gating, Q6/Q18).
- **Activation gate (Q15/Q17):** a campaign-assignment may require evidence
  before the vehicle starts earning — installation photo(s) uploaded (ops or
  driver, [OPEN]), reviewed by admin, recorded against the assignment (§19.3).
  Gate = predicate on the existing assignment activation transition, not a new
  state machine.
- Admin UI: one **approvals queue** section listing pending campaigns,
  creatives, and activation evidence (§27).

## 19. Files — storage, creative pipeline, evidence, KYC docs

Blocked-by: Q18 (upload+approval confirmed?), Q26 (KYC document set), Q32
(cloud account → storage provider). D7 says in-platform upload is an MVP rule
pending approval.

### 19.1 Storage adapter

`app/adapters/storage/` — S3-compatible interface (`put/get/delete/presign`),
backed by MinIO in local compose and the cloud provider's object store in
staging/production ([OPEN] Q32 → S3, GCS-S3-compat, or R2). **No files on
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
3. A worker job scans/validates (mime sniff + size + optional AV scan — pilot
   posture [OPEN]: admin review may be the only gate at 2–3 advertisers, P10).
4. Serving: **time-limited signed GET URLs** issued by the backend; nothing in
   the bucket is public. `campaign_creatives.asset_url` remains and now points
   at (or is derived from) the managed object — external-URL creatives keep
   working for backward compatibility.

### 19.3 Consumers of the same pattern

| File kind | Linked to | Reviewer |
|-----------|-----------|----------|
| Creative assets (D7/Q18) | `campaign_creatives` | Admin approval (§18) |
| Installation evidence photos (Q17) | `campaign_assignments` | Admin activation gate (§18) |
| Driver KYC documents (Q26 — licence, registration, insurance, photo) | `driver_profiles` | Admin onboarding flow |
| Signed driver agreement (Q26) | `driver_profiles` | Acceptance recorded, doc stored |

One `stored_files` table + per-domain link columns/tables; one adapter; one
upload flow. Do not build per-feature upload paths.

## 20. Notifications

Blocked-by: Q34 (channels at launch; driver comms). Proposed default (matching
the questionnaire's recommendation): launch = in-app + **automated email for
advertisers** + ops-run WhatsApp for drivers; automated WhatsApp/SMS as fast
follow. Email is a first-class channel adapter (transactional provider, [OPEN])
— the §30 password-reset row depends on it.

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
  Query (§27.2). No push infrastructure in the MVP target; native-app push
  (FCM) becomes a new channel adapter in phase 2 (§23) without schema change.

### 20.2 Rules

- Services **never call a messaging provider inline** — they insert notification
  rows. Only the worker talks to providers.
- Templates are code (typed builders per notification type), not a CMS — at
  this scale a template table is over-engineering (P10).
- First triggers (when built): assignment offered/accepted, payout released,
  fraud flag raised/resolved, campaign approved/paused, budget alerts.

## 21. Matching & assignment evolution

Blocked-by: Q7 (matching model), Q8 (driver acceptance), Q16 (one campaign per
vehicle), competitor-separation policy.

- **Preserve:** admin-driven assignment through
  `app/services/campaign_assignments.py` and the offered → accepted → active
  lifecycle (driver acceptance already exists and matches Q8's proposed
  default).
- **Target:** matching intelligence is a **recommender inside the existing
  service**, not an auto-assigner: rank eligible driver+vehicle pairs (city,
  vehicle type, activity history, current load) for the admin to confirm.
  Auto-assignment only if Q7 lands there.
- **Constraint checks live in the service layer** so they hold no matter who
  creates the assignment (admin UI, recommender, future API): one-campaign-per-
  vehicle (Q16, proposed pilot rule) and competitor-category separation
  (needs a campaign category field — added when the policy lands, [OPEN]) are
  validation rules in `create_assignment`, not UI logic.
- Activity floor (Q20): worker sweep flags assignments below minimum tracked
  km/hours per week to ops (notification, §20) — data already exists in
  `trip_analytics`.

## 22. Retargeting & the audience privacy boundary (D6)

Blocked-by: Q11 (dashboard-only insights vs anonymised exportable segments vs
platform integrations). D6 fixes that *something* ships in the MVP.

### 22.1 What the data actually is

We do not observe audiences; we observe **vehicle routes**. "Audience" data is
derived: exposure cells (geo × time buckets a branded vehicle transited, with
estimated impressions). Whatever Q11 chooses, the platform's audience product is
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

### 22.3 Shape (finalised when Q11 lands)

New domain `app/services/audience.py` + `audience_segments` table (segment
definition: zones/cells × time window × campaign scope; materialised counts;
version stamp per P6). Worker jobs materialise segments from analytics
aggregates. Export/activation (CSV of cells, or platform integrations) is an
adapter decision downstream of Q11 — the aggregation model is the same for all
three shapes, which is why this can be designed now (P10).

## 23. Identity evolution & native-app readiness

- **F7 is built** (§12): sliding session, `sv` revocation, forced password
  change, rate limiting. Everything below builds on it.
- **Driver self-registration ([OPEN] Q13):** if approved — public
  `POST /api/v1/auth/register-driver` gated by feature flag, creating an
  `invited/pending`-state user + driver profile that enters the existing admin
  onboarding queue (KYC docs per Q26 through §19). The service layer already
  separates user creation from admin UI, so this is additive. Until then:
  operator-led only (D1).
- **Native driver app (phase 2, D3):** consumes the **same** `/api/v1/driver/*`
  contract (already cookie-free bearer — verified posture). Two additions when
  commissioned, [TARGET] not yet designed in detail:
  1. **Long-lived refresh credential** for native clients — designed as an
     extension of F7's `POST /api/v1/auth/refresh` sliding-session endpoint
     (§6.3), not a parallel mechanism: native clients get a longer-lived
     refresh grant where the BFF gets the 12h-capped rotation; both honour the
     `sv` claim. The BFF cookie flow is unaffected.
  2. **Push channel** (FCM) as a new notification adapter (§20).
  Binding now: keep the driver API free of browser-cookie assumptions (true
  today — keep it that way), and keep ping ingestion contract stable (D3:
  "identical backend contract" is a client promise).
- **Advertiser/admin stay BFF-cookie** — no native clients planned for them.

## 24. Data lifecycle — retention, volume, partitioning

### 24.1 Volume reality check

Pings arrive ~1/second while tracking (geolocation watch, §8.6). Pilot math:
50 vehicles × ~4 tracked h/day ≈ **0.7M pings/day ≈ 21M rows/month**. At the
proposed 12-month retention that is a ~250M-row steady state — too big for a
single unpartitioned table to purge with `DELETE`s, but entirely fine for
Postgres with partitioning. At 10× (500 vehicles) it is ~2.5B rows/year —
still Postgres territory with partitions + retention, not a new datastore.

### 24.2 Design

1. **Retention job** (§14): purge raw `location_pings` (and `location_ping_batches`)
   older than the retention window (proposed 12 months, [OPEN] Q31;
   config `PING_RETENTION_MONTHS`). `trip_sessions` is raw location data too
   (§22.2.1 — precise start/end Point geometry + timestamps): the same job
   **nulls its coordinate columns** past the window, keeping the row
   (durations, FKs, statuses) because the ledger and analytics reference it.
   Aggregates (`trip_analytics`, `impression_estimates`, heatmap-feeding data)
   are retained indefinitely — they carry the business value and no raw traces.
2. **Monthly range partitioning** of `location_pings` (by `captured_at`) so
   purge = `DROP PARTITION` (instant, no bloat). By the volume math above the
   table passes 20M rows **within the first pilot month** — so partitioning is
   **W1 pre-pilot work alongside the retention job (§31), not a deferred
   trigger**. (Only if Q30 lands materially smaller than 50 vehicles may it
   slip, and then the trigger is: table > 20M rows or p95 heatmap latency
   > 2s.) The current live-aggregation heatmap (`app/services/heatmaps.py`
   scans raw pings per request
   <!-- verified: aggregation_sql() joins location_pings -->) is acceptable at
   pilot scale; if it degrades, the sanctioned fix is **precomputed heatmap
   cells materialised by a worker job**, not caching hacks.
3. **Consent & policy (NDPR):** trip-scoped tracking is already the built
   posture (tracking only between explicit start/end — Q10-area, keep it);
   consent wording + privacy policy are client deliverables ([OPEN] Q31); the
   driver app surfaces consent at onboarding (§19.3 agreement flow).
4. Deletion is audited (an audit event records the purge run + row counts).
5. **Backups respect retention:** database backups (§25.2) resurrect purged
   pings unless they expire — backup retention must be **shorter than or equal
   to** a bounded rotation window (e.g. 35 days), so purged personal data ages
   out of backups automatically. State this in the backup runbook.
6. **Data-subject rights (NDPR):** access/rectification/erasure requests have
   no automated pipeline at pilot scale — the sanctioned shape is a **manual
   SQL runbook** (P10) executed by a named admin and recorded in the audit
   trail. Known design tension to resolve with counsel ([OPEN] Q31): an
   erasure request vs the append-only ledger/audit history — the expected
   answer is anonymisation of the user row while preserving financial records,
   but that is a legal call, not ours.

## 25. Deployment & infrastructure target

Blocked-by: Q32 (cloud account ownership, budget), Q29 (domain/brand), Q30
(pilot shape). Posture: containerised and cloud-portable — nothing below
assumes a specific vendor.

### 25.1 Environments

| Env | Purpose | Shape |
|-----|---------|-------|
| **Local** | dev | compose as today (§10.1) + `worker` + MinIO when §14/§19 land |
| **Staging** [PLANNED-F7] | client review, e2e against prod-like stack | single VM under OJ's account (swaps to client cloud when Q32 lands), compose-managed, seeded demo data, HTTPS via Caddy/Traefik with auto-certs |
| **Production** | pilot launch | see below |

### 25.2 Production topology (pilot-sized)

- **Managed Postgres with PostGIS** (the one component worth paying a provider
  for: backups, PITR, failover). Everything else runs as containers on **one or
  two VMs** (or the cloud's container service if Q32 lands on GCP/AWS —
  equivalent shape): `frontend`, `api`, `worker`, `redis`, edge proxy.
- **Edge exposure:** the reverse proxy routes the public domain to `frontend`
  (all browser traffic) and exposes exactly `/api/v1/webhooks/*` and the
  health endpoints (`/health`, `/api/v1/health*` — so external uptime monitors
  can reach them, §26) + (when native app ships) `/api/v1/{auth,driver,me}/*`
  to the internet; FastAPI is otherwise internal-only (§8.2). TLS terminated
  at the proxy.
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
| Driver: flagged-trip detail + dispute, onboarding docs, payout history | `app/driver/*` (extend) | §17/§19/§16 |

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
| Payout engine v2 | §16.1 | `services/payouts.py` + `jobs/` (trip pipeline, §14.2) | payout_rules, payout_calculations, ledger | v1 history rows | Q4, Q5 |
| Release scheduling | §16.2 | `jobs/` + `services/payouts.py` | ledger statuses | ledger edits (append-only) | Q22, worker (§14) |
| Disbursement | §16.3 | `adapters/disbursement/`, `services/payouts.py` | payout_batches (new) | — | Q27 |
| Fraud review workflow | §17 | `services/` + `api/v1/` fraud modules | fraud_flags lifecycle | detection engine internals | Q21 |
| Campaign/creative approval | §18 | status enums + services | campaign/creative status | parallel approval flags | Q6, Q18 |
| File upload (any kind) | §19 | `adapters/storage/`, `services/files.py` | stored_files (new) | container FS, DB blobs | Q18/Q26 + provider |
| Notifications | §20 | `services/notifications.py`, `jobs/`, `adapters/messaging/` | notifications (new) | inline provider calls | Q34 |
| Billing / invoices / payments | §15 | `services/billing.py`, `adapters/payments/` | invoices, payments (new) | report/cost-summary logic | Q1–Q3, Q14, Q28 |
| Payment webhooks | §15.4 | `api/v1/webhooks.py` | payment_events (new) | business logic in handler | provider choice |
| Budget enforcement | §15.5 | `jobs/` + `services/billing.py` + campaign status | campaign status | hard deletes | policy confirmation (Q9-adjacent, via decisions-log) |
| Matching/recommender | §21 | `services/campaign_assignments.py` | — | UI-layer constraint checks | Q7, Q16 |
| Activity-floor sweep | §21 | `jobs/` | notifications | — | Q20, worker |
| Retargeting/audience | §22 | `services/audience.py`, `jobs/` | audience_segments (new) | raw pings from any new code | Q11 |
| Retention purge | §24 | `jobs/` | location_pings (delete) | aggregates | Q31 param, worker |
| Ping partitioning | §24.2 | migration | location_pings | frozen migrations | W1 (pre-pilot, §24.2.2) |
| Data-subject requests (NDPR) | §24.2.6 | ops runbook (no code at pilot) | — | ledger/audit deletes | Q31, counsel |
| Quotes / packages | §15 | `services/billing.py` | invoices | report logic | Q1, Q14 |
| Campaign cancellation / refunds | §15 | `services/billing.py` + campaign status | invoices, payments | ledger edits | Q24 |
| Driver bank account / BVN capture | §16.3 | `driver_profiles` + KYC flow (§19.3) | driver_profiles | plaintext storage of BVN — treat as sensitive PII (P7) | Q26, Q27 |
| Password reset (advertiser/admin) | §23 | `services/auth.py` | users | — | post-F7; needs email channel (§20) |
| WhatsApp opt-in / phone verification | §20 | `services/notifications.py` | users/driver_profiles phone fields | — | Q34 |
| Driver self-registration | §23 | `services/users.py` + new auth endpoint | users, driver_profiles | operator-led invariant until Q13 | Q13 |
| Native app support | §23 | auth + notifications | refresh tokens (new) | driver API contract breaks | phase-2 commission |
| New admin/advertiser/driver page | §27 | `frontend/src/app/{role}/` | — | BFF invariant, raw hex | backend feature |
| Polling/live UI | §27.2 | TanStack Query layer | — | WebSockets/SSE | — |

## 31. Roadmap — gaps & sequencing

The gap between Part II and Part III, ordered. Waves after F7 assume the
blocking answers have landed; within a wave, order is dependency-driven.

| Wave | Contents | Depends on |
|------|----------|------------|
| **F7 (done, 2026-07-20)** [BUILT] | Auth hardening (sliding session, `sv`, forced change, rate limiting), backend CI, audit API/UI, rich seed, backups/restore, Sentry hooks. Staging deploy deliberately deferred — research only (`docs/staging-options.md`), awaiting OJ approval | — |
| **W1 — money correctness** | Worker substrate + trip-processing pipeline (§14) **[BUILT] (delivered 2026-07-21; payout stage transitional `payout_v1`, not D2)** → payout v2 + caps (§16.1) → fraud review + holds (§17; the driver-facing dispute channel needs notifications — ship a minimal **in-app-only** notification slice here, §20, channel adapters wait for W2) → release scheduling (§16.2) → payout runs UI (§16.3 pilot form). Plus pre-pilot data-infra chores: retention job + ping partitioning (§24.2), audit backfill for unaudited flows (§6.4.9) | Q4, Q5, Q21, Q22 (retention window Q31 — ships with the 12-month config default if unanswered) |
| **W2 — the commercial layer** | Billing/invoices (§15) → file storage (§19) → approval workflows (§18 — campaign approval may precede files, but creative approval and activation evidence consume §19) → notification channel adapters + triggers (§20) | Q1–Q3, Q6, Q14, Q17, Q18, Q28, Q34 |
| **W3 — reach** | Retargeting v1 per Q11 (§22) → matching recommender + activity sweeps (§21) → driver self-reg if Q13 says so (§23) | Q7, Q11, Q13, Q20 |
| **Phase 2 (commissioned separately)** | Native driver app + refresh tokens + push (§23); gateway auto-collection (§15.3); Paystack Transfers (§16.3); edge-AI counting (out of scope here) | Pilot results |

Sequencing rationale: W1 first because D2/D4/D5 change **how money is
computed** — every week built on `payout_v1` deepens the rework; W2 second
because it's what sales/ops need to run real campaigns; W3 third because it
extends reach rather than correctness. The worker (§14) leads W1 because W1–W3
all consume it.

## 32. Risks, assumptions & client dependencies

| # | Risk / assumption | Mitigation / owner |
|---|-------------------|--------------------|
| R1 | **Hourly pay invites time-farming** (park with screen on). Payable-time verification rules (Q5) are the control — they must require movement/zone presence, not app-open time. | Design §16.1 verification params with fraud engine input; pilot data tunes them. |
| R2 | **Questionnaire answers may contradict proposed shapes** (e.g. Q14 says no in-platform invoicing). Shapes here are deliberately minimal; if an answer removes a domain, we delete the section, not rework it. | P10; amendment rule. |
| R3 | **Redis fail-open** (F7 rate limiting) + queue-loss tolerance (§14.3.2) are deliberate availability-over-strictness choices. | Documented here; revisit post-pilot. |
| R4 | **Prototype promised "live" surfaces**; MVP is polling. Client expectations managed via demo framing. | §14.4; OJ handles comms. |
| R5 | **Single-operator bus factor** (OJ + agents). This doc + SOP + memory files are the mitigation. | Keep doc current (amendment rule). |
| R6 | **NDPR compliance depends on client deliverables** (policy, consent wording, DPO contact — Q31). Retention tech (§24) is ours; the words are theirs. | Flag at every review until landed. |
| R7 | **Vendor choices unowned** (cloud Q32, payments Q3/Q27, messaging Q34, tiles). Adapters (P5) keep them swappable; but contracts/accounts gate launch dates. | Track in §33; escalate at pilot planning. |
| R8 | **Volume math (§24.1) is estimated**, not measured (ping rate assumed ~1/s tracked). Validate against real pilot telemetry in month 1; retune partitioning trigger. | First staging review. |
| A1 | Assumption: pilot ≤50 vehicles, ≤3 advertisers, one city (Q30 default). All sizing flows from it. | Re-run sizing if Q30 answers bigger. |
| A2 | Assumption: advertiser/admin remain web-only; only drivers get a native app. | Q-check at phase-2 commissioning. |

## 33. Open questions **[OPEN]**

Source: `docs/Mobility_Product_Direction_Questionnaire_v2.docx` — 34 questions:
**A. Core product decisions Q1–Q14 · B. Recommended MVP rules Q15–Q24 ·
C. Pilot & launch Q25–Q34.** Answers flow into `docs/decisions-log.md` and then
into this doc (amendment rule). Architecture impact map:

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

**Rule:** if your feature touches one of these areas, design the smallest thing
that works under *all* still-open options, and say so in the PR (P10).

## 34. Doc changelog

| Version | Date | Change |
|---------|------|--------|
| v0.1 | 2026-07-12 | Initial document: current state verified against branch `f7-hardening`. |
| v1.0 | 2026-07-12 | Target-state architecture added: Parts I–IV, principles P1–P12, target domains (worker, billing, payouts v2, fraud review, approvals, files, notifications, matching, audience, identity, data lifecycle, deploy, observability), placement map, roadmap waves, risk register, Q1–Q34 impact map. Current-state sections renumbered (old §2–§9 → §5–§12). |
| v1.1 | 2026-07-13 | Adversarial review round 1 (18 findings) applied: Part II pinned to commit `d9a989c` + F7-in-flight notice; F7 sliding session documented as `POST /auth/refresh`; fraud lifecycle reconciled with built statuses + dedup-index trap; heatmap grandfathered in privacy boundary; k = distinct vehicles; post-release flag reversal policy; Africa/Lagos cap day; N payments per invoice + `partially_paid`; presigned POST (not PUT) + CORS + lifecycle cleanup; partitioning moved to W1 pre-pilot; backup-retention + NDPR DSR runbook; health endpoints at edge; audit-invariant honesty note + W1 backfill; v1-questionnaire residue swept; placement-map rows added (DSR, quotes, refunds, BVN, password reset, WhatsApp opt-in). |
| v1.2 | 2026-07-13 | Adversarial review round 2 (12 findings, fresh reviewer) applied. Load-bearing fix: **automated trip-processing pipeline** added as the worker's first job (§14.2 — analytics→fraud→impressions→payout on trip end + uncomputed-trip sweep; previously the target automated only consumers of facts nothing produced). Also: daily-cap concurrency rule (advisory lock per driver/campaign/Lagos-day, midnight + recompute policy); ledger `paid` status flagged as a check-constraint migration; payee abstraction honouring Q23's no-rework promise; `trip_sessions` coordinates added to retention purge; W1/W2 ordering fixed (in-app notification slice into W1; files before creative approval in W2; stale W3 retention row removed); budget "spend" defined as a billing computation; webhook event-row rule generalised per domain; email restored as a first-class channel; campaign approval placed relative to `scheduled`; reversal-recommendation home + negative-balance rule; test count corrected to 190. |
| v1.3 | 2026-07-13 | Adversarial review round 3 (convergence gate; 4 blockers + 4 rideable) applied: reversal semantics reconciled with the built ledger (positive amounts, subtract-by-type netting in every summary — the naive design would have *added* money); §19 blocked-by corrected Q31→Q32; budget-rule and payout-floor [OPEN]s re-anchored (no numbered v2 question exists — confirm via decisions-log); `notifications` gains `provider_message_id` + `delivered` so §15.4 receipts are satisfiable; trip pipeline added to the §13 diagram; W1 retention-window dependency noted; `payout_calculations` v2 migration scope; changelog reordered. |
| v1.4 | 2026-07-20 | **F7 reconciliation.** Part II re-verified against the committed F7 delivery and the pin moved from `d9a989c` to `301519d`. Promoted to [BUILT]: sliding session + 12h cap + `sv` revocation + `must_change_password` + change-password endpoint (§6.3), Redis login rate limiting with trusted-edge gating (§6.3/§12), auth audit events + admin audit API/UI + `0012` indexes (§6.4.9), migrations `0011`/`0012` (§7.2), revision-gated backup/restore scripts (§7.2/§10.4), Sentry hooks both tiers (§10.4/§12), backend CI job with PostGIS+Redis services (§10.3), rich `f7_rich_v1` seed namespace (§11), driver `(portal)` route group + change-password/keepalive routes + `/admin/audit` (§8.3). Counts updated by command: 82 ops / 66 paths (was 79/63), 12 migrations, 209 backend test functions in 35 files, 32 vitest cases, 48 Playwright project-expanded tests in 6 specs. Staging deploy explicitly deferred (research only). Legacy sv-less-token residual risk documented (§6.3). |
| v1.5 | 2026-07-21 | **Worker substrate + automated post-trip processing [BUILT].** One arq worker (`app/jobs/worker.py`, new compose `worker` service, no host port) runs the §14.2 pipeline complete-missing-only — analytics→fraud→impressions→payout(+ledger, audited) for ended trips — via fail-open enqueue-after-commit on trip end (`app/core/trip_enqueue.py`) backstopped by a Postgres-derived cron sweep. New Settings: `WORKER_SWEEP_INTERVAL_MINUTES` (divisor of 60) and `WORKER_SWEEP_BATCH_SIZE`. No HTTP contract, schema, or migration change; admin endpoints unchanged as recompute tools. §6.5, §10.1, §14, §31 amended. Payout automation runs `payout_v1` as transitional infrastructure only — D2 (hourly pay) still pending Q4/Q5; not for production enablement. |

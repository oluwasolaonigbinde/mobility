# Mobility AdTech Platform

Monorepo for the Mobility AdTech & Audience Attribution Platform: a FastAPI/PostGIS
backend and a Next.js frontend for advertiser, driver, and operator workflows.

## Project Status

Delivery status lives in **one place**: `docs/progress.md` — what has been
delivered vs. the client-promised MVP scope, current roadmap wave, and what is
outstanding. Read it (plus `docs/architecture.md`) before planning any work.
Summary as of Aug 2026: backend slices 0–13 closed; frontend F0–F7 merged;
worker pipeline, payout v2 (S1), and data lifecycle (S4) delivered; nothing
deployed yet.

## Stack

- Python 3.12
- FastAPI
- Pydantic v2 and pydantic-settings
- SQLAlchemy 2.x async with asyncpg
- Alembic
- PostgreSQL with PostGIS
- Redis
- arq (background worker)
- pytest and ruff
- Docker Compose

## Delivered Backend Baseline (closed slices 0–13)

Full MVP scope is defined by the client proposal
(`docs/Mobility_AdTech_MVP_Proposal_5_Month_Retargeting.docx`, D11) and
sequenced in `docs/architecture.md` §31; the exclusions below describe only
what the *closed backend slice loop* did not build, not the project's scope.

The closed backend MVP contains Slice 13: project foundation, request IDs, expected error
envelope, SQLAlchemy/Alembic foundation, JWT login, current-user context, RBAC, admin
user management, advertiser organizations, organization memberships, audit events,
driver profiles, vehicle profiles, advertiser campaign metadata, campaign creative
metadata, advertiser campaign zones/geofences, campaign assignment and driver
activation lifecycle, driver trip/session tracking, batched GPS location ping
ingestion, deterministic route analytics, basic fraud/anomaly flags, traffic density
profiles, deterministic impression estimates, campaign payout rules, deterministic
payout calculations, driver earnings ledger reads, advertiser campaign cost summaries,
advertiser dashboard summary, campaign summaries, campaign daily metrics, campaign
trip reporting, bundled campaign JSON reports, bounded PostGIS heatmap aggregation,
idempotent local/demo seed data, OpenAPI docs hardening, Docker Compose, tests, and
linting. Slice 13 freezes the MVP frontend contract in
`docs/api/openapi.snapshot.json` and adds hardening guardrails without adding product
tables or product features.

The closed backend MVP excludes settlement, withdrawals, advertiser billing, CSV/PDF
exports, map tiles, heatmap cache tables, and production seed automation. The frontend
is present in `frontend/` as a separate, committed delivery stream (F0–F6 plus
the F7 hardening layer described above); `frontend/README.md` documents the BFF
architecture, local setup, and testing.

## Documentation Map

Four living docs, one loop: client decisions change → architecture amends →
agents build → progress records it. Scope is fixed by the client proposal.

1. `docs/Mobility_AdTech_MVP_Proposal_5_Month_Retargeting.docx` — **scope**:
   the binding client-facing MVP promise (decisions-log D11). Never edited by
   agents.
2. `docs/architecture.md` — **design**: verified current state and the target
   architecture that fulfils the proposal, with the §31 wave roadmap.
3. `docs/decisions-log.md` — **decisions**: Part 1 append-only D-row history,
   Part 2 current Q1–Q34 statuses + divergence guards.
4. `docs/progress.md` — **delivered so far**: evolving summary of work done
   vs. the promise; updated with every landed slice.

Supporting reference: `docs/runbook.md` (operations), `docs/next-steps.md`
(current slice plan, retired when its slices ship), `docs/staging-options.md`
(hosting research), `docs/api/openapi.snapshot.json` (frozen contract).
History: `docs/build-loop/` (closed backend ledger), `docs/archive/`
(superseded artefacts and journals).

## Local Prerequisites

- Python 3.12
- Docker and Docker Compose

## Environment

Create a local environment file from the example:

```powershell
Copy-Item .env.example .env
```

The example is safe for local Docker Compose development. Do not commit real secrets.

## Install

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run The API

```powershell
uvicorn app.main:app --reload
```

Health endpoints:

- `GET /health`
- `GET /api/v1/health`
- `GET /api/v1/health/ready`

Readiness checks the database only when `DATABASE_URL` is configured. Without a configured database URL, it returns `database: not_configured`.

Slice 1 auth and organization endpoints:

- `POST /api/v1/auth/login`
- `GET /api/v1/me`
- `POST /api/v1/admin/users`
- `GET /api/v1/admin/users`
- `PATCH /api/v1/admin/users/{user_id}`
- `POST /api/v1/admin/advertiser-organizations`
- `GET /api/v1/advertiser/organization`

Slice 2 driver and vehicle endpoints:

- `GET /api/v1/driver/profile`
- `PATCH /api/v1/driver/profile`
- `GET /api/v1/driver/vehicles`
- `GET /api/v1/driver/vehicles/{vehicle_id}`
- `POST /api/v1/admin/drivers/{user_id}/profile`
- `GET /api/v1/admin/drivers`
- `GET /api/v1/admin/drivers/{driver_profile_id}`
- `PATCH /api/v1/admin/drivers/{driver_profile_id}`
- `POST /api/v1/admin/drivers/{user_id}/vehicles`
- `GET /api/v1/admin/vehicles`
- `GET /api/v1/admin/vehicles/{vehicle_id}`
- `PATCH /api/v1/admin/vehicles/{vehicle_id}`

Slice 3 campaign and creative metadata endpoints:

- `POST /api/v1/advertiser/campaigns`
- `GET /api/v1/advertiser/campaigns`
- `GET /api/v1/advertiser/campaigns/{campaign_id}`
- `PATCH /api/v1/advertiser/campaigns/{campaign_id}`
- `POST /api/v1/advertiser/campaigns/{campaign_id}/creatives`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/creatives`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}`
- `PATCH /api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}`
- `GET /api/v1/admin/campaigns`
- `GET /api/v1/admin/campaigns/{campaign_id}`

Slice 4 campaign zone endpoints:

- `POST /api/v1/advertiser/campaigns/{campaign_id}/zones`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/zones`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}`
- `PATCH /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}`
- `DELETE /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}`

Slice 5 campaign assignment endpoints:

- `POST /api/v1/admin/campaign-assignments`
- `GET /api/v1/admin/campaign-assignments`
- `GET /api/v1/admin/campaign-assignments/{assignment_id}`
- `POST /api/v1/admin/campaign-assignments/{assignment_id}/cancel`
- `GET /api/v1/driver/campaign-assignments`
- `GET /api/v1/driver/campaign-assignments/active`
- `GET /api/v1/driver/campaign-assignments/{assignment_id}`
- `POST /api/v1/driver/campaign-assignments/{assignment_id}/accept`
- `POST /api/v1/driver/campaign-assignments/{assignment_id}/activate`
- `POST /api/v1/driver/campaign-assignments/{assignment_id}/deactivate`

Slice 6 driver trip tracking endpoints:

- `POST /api/v1/driver/trips/start`
- `GET /api/v1/driver/trips/current`
- `POST /api/v1/driver/trips/{trip_id}/pings`
- `POST /api/v1/driver/trips/{trip_id}/end`
- `GET /api/v1/driver/trips/{trip_id}`

Slice 7 route analytics and fraud flag endpoints:

- `POST /api/v1/admin/trips/{trip_id}/recompute-analytics`
- `GET /api/v1/admin/trips/{trip_id}/analytics`
- `GET /api/v1/admin/fraud-flags`
- `GET /api/v1/driver/trips/{trip_id}/analytics-summary`

Slice 8 impression estimation endpoints:

- `POST /api/v1/admin/traffic-density-profiles`
- `GET /api/v1/admin/traffic-density-profiles`
- `GET /api/v1/admin/traffic-density-profiles/{profile_id}`
- `PATCH /api/v1/admin/traffic-density-profiles/{profile_id}`
- `POST /api/v1/admin/trips/{trip_id}/estimate-impressions`
- `GET /api/v1/admin/impression-estimates`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/impressions/summary`

Slice 9 payout calculation and earnings endpoints:

- `POST /api/v1/admin/campaigns/{campaign_id}/payout-rules`
- `GET /api/v1/admin/campaigns/{campaign_id}/payout-rules`
- `GET /api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}`
- `PATCH /api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}`
- `POST /api/v1/admin/trips/{trip_id}/calculate-payout`
- `GET /api/v1/admin/payout-calculations`
- `GET /api/v1/driver/earnings/summary`
- `GET /api/v1/driver/earnings/ledger`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/cost-summary`

Slice 10 advertiser reporting endpoints:

- `GET /api/v1/advertiser/dashboard/summary`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/summary`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/daily-metrics`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/trips`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/report`

Slice 11 heatmap endpoints:

- `GET /api/v1/advertiser/campaigns/{campaign_id}/heatmap`
- `GET /api/v1/admin/heatmap`

Slice 12 local/demo seed command:

```powershell
docker compose up -d db redis
$env:DATABASE_URL = "postgresql+asyncpg://mobility:mobility@localhost:5433/mobility"
python -m alembic upgrade head
$env:ALLOW_DEMO_SEED = "true"
python -m app.seeds.demo
```

The demo seed is local/development only. It refuses production-like environments,
does not run during application startup, does not run automatically in Docker
Compose, and uses existing tables only. Demo credentials are for local demos only
and must never be used in production:

- `admin@demo.mobility.local` / `DemoAdmin12345!`
- `advertiser@demo.mobility.local` / `DemoAdvertiser12345!`
- `viewer@demo.mobility.local` / `DemoViewer12345!`
- `driver@demo.mobility.local` / `DemoDriver12345!`

Suggested frontend smoke workflow after seeding:

1. Start the API with `uvicorn app.main:app --reload`.
2. Log in with `POST /api/v1/auth/login` as `advertiser@demo.mobility.local`.
3. Call `GET /api/v1/me`.
4. Call `GET /api/v1/advertiser/dashboard/summary`.
5. Call `GET /api/v1/advertiser/campaigns` and use the demo campaign id.
6. Call `GET /api/v1/advertiser/campaigns/{campaign_id}/summary`.
7. Call `GET /api/v1/advertiser/campaigns/{campaign_id}/daily-metrics`.
8. Call `GET /api/v1/advertiser/campaigns/{campaign_id}/trips`.
9. Call `GET /api/v1/advertiser/campaigns/{campaign_id}/report`.
10. Call `GET /api/v1/advertiser/campaigns/{campaign_id}/impressions/summary`.
11. Call `GET /api/v1/advertiser/campaigns/{campaign_id}/cost-summary`.
12. Call `GET /api/v1/advertiser/campaigns/{campaign_id}/heatmap?bbox=3.35,6.43,3.47,6.56&resolution_m=500&metric=estimated_impressions`.
13. Log in as `driver@demo.mobility.local`.
14. Call `GET /api/v1/driver/earnings/summary`.
15. Call `GET /api/v1/driver/earnings/ledger`.

## MVP Contract Baseline

Frontend integration should use `/api/v1` as the API base and `POST
/api/v1/auth/login` followed by bearer auth for protected routes. `GET /api/v1/me`
is the route-guard endpoint for the current user and advertiser organization context.

The checked-in OpenAPI baseline is:

- `docs/api/openapi.snapshot.json`

Live local docs remain available at:

- `/docs`
- `/openapi.json`

Regenerate the snapshot only as part of an intentional contract update:

```powershell
@'
import json
from pathlib import Path
from app.main import create_app

Path("docs/api/openapi.snapshot.json").write_text(
    json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
'@ | python -
```

Protected endpoints use bearer auth:

```http
Authorization: Bearer <access_token>
```

Admin-created users require passwords at least `PASSWORD_MIN_LENGTH` characters long.
Emails are normalized to lowercase before storage and login lookup. JWT signing uses
`JWT_SECRET_KEY`, `JWT_ALGORITHM`, and `ACCESS_TOKEN_EXPIRE_MINUTES`. The local
placeholder `JWT_SECRET_KEY` is rejected outside local/test-like environments, and
wildcard CORS origins are rejected outside local/test-like environments.
Driver profile country codes and vehicle plate country codes are normalized to
uppercase. Vehicle plate uniqueness uses `plate_number_normalized`, generated by
uppercasing `plate_number` and removing whitespace and hyphens.
Campaign currency codes are normalized to uppercase. Campaign and creative
metadata are JSON objects only; creative binary uploads and asset processing are
not part of Slice 3. Campaign zones accept GeoJSON Polygon or MultiPolygon geometry
using `[longitude, latitude]` coordinate order, store it in PostGIS as SRID 4326,
and return GeoJSON plus calculated area. Zone area is capped by
`MAX_CAMPAIGN_ZONE_AREA_SQ_KM`, defaulting to `5000`. Campaign assignments can be
created by admins for eligible scheduled, active, or paused campaigns, active driver
profiles, and active vehicles. Drivers can accept, activate, and deactivate only
their own assignments; activation requires an active campaign inside its date window.
Driver trips can be started only for active assignments with active campaigns,
drivers, and vehicles. Location pings are accepted in idempotent batches with
server-side timestamp, coordinate, accuracy, speed, heading, altitude, and batch-size
validation, and are stored as PostGIS `geometry(Point,4326)`. Route analytics,
can be recomputed by admins only for ended trips and use PostGIS geography-safe
distance plus whole-segment campaign-zone intersection attribution. Drivers can read
only their own trip analytics summaries. Fraud flags are deterministic anomaly
records only. Impression estimates use stored trip analytics, an active traffic
density profile, UTC time-of-day weights, dwell exposure, zone exposure, quality
score, and open fraud flag severity multipliers. If no active default profile exists
when estimating without a profile id, a settings-backed default profile is created.
Advertiser impression summaries aggregate stored estimates for campaigns in the
current advertiser organization using `estimated_at` for date filters. Payout rules
are explicit admin-managed campaign configuration and are not silently created at
runtime. Payout calculations use stored trip analytics, stored impression estimates,
open fraud flag severity, trip quality score, and the active campaign payout rule.
Successful positive calculated payouts create one pending immutable trip payout
ledger entry. Driver earnings endpoints expose only the current driver's aggregate
summary and ledger entries. Advertiser cost summaries aggregate stored payout
calculations for the current advertiser organization using `calculated_at` for date
filters. Advertiser reporting endpoints are read-only and aggregate existing stored
campaign, creative, zone, assignment, trip, analytics, fraud, impression, payout, and
ledger records only. Date filters use `trip_sessions.started_at` for trip and route
analytics counts, `impression_estimates.estimated_at` for impressions,
`payout_calculations.calculated_at` for costs, and `fraud_flags.detected_at` for fraud
counts. Daily metrics group by UTC calendar day from `trip_sessions.started_at` and do
not use a materialized daily-metrics table. Reporting responses do not expose driver
PII, vehicle plate numbers, raw GPS pings, idempotency keys, ledger details, payment
data, or password hashes. Settlement, withdrawal, payment provider, invoice, tax,
advertiser charging, CSV/PDF export, map tiles, heatmap cache tables, production seed
automation, and frontend work are not part of Slice 12. Heatmap endpoints are read-only and aggregate
stored location pings into GeoJSON polygon cells using a required bounded `bbox`.
Supported metrics are `ping_count`, `trip_count`, `distance_m`, and
`estimated_impressions`. Distance and impression values use stored trip analytics and
stored impression estimates, allocated to cells by trip ping share in the requested
bbox/date window. Heatmap responses do not expose driver PII, driver profile ids,
vehicle plate numbers, raw GPS point rows, ping ids, idempotency keys, ledger details,
payment data, or password hashes.
The Slice 12 demo seed creates local-only admin, advertiser, viewer, and driver
users; one advertiser organization; one active driver profile and vehicle; one active
campaign and ready creative; Lagos target, bonus, and exclusion zones; an active
assignment; two ended trips with PostGIS pings; route analytics, impression estimates,
payout calculations, and pending driver earnings ledger rows. It is idempotent and
reuses deterministic natural keys on repeated runs.

## Tests

```powershell
python -m pytest
```

Plain host tests use SQLite for speed and may skip PostGIS-specific checks unless a
PostGIS database URL is configured. To run the PostGIS-backed trip and analytics
verification:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://mobility:mobility@localhost:5433/mobility"
python -m pytest tests/test_trips.py tests/test_trip_analytics.py tests/test_impression_estimates.py tests/test_heatmaps.py -q
```

## Lint

```powershell
ruff check .
```

## Migrations

Run PostGIS locally before applying migrations:

```powershell
docker compose up -d db
$env:DATABASE_URL = "postgresql+asyncpg://mobility:mobility@localhost:5433/mobility"
alembic upgrade head
```

The initial migration enables `pgcrypto` and `postgis`. Slice 1 adds only the approved
identity and tenancy tables: `users`, `advertiser_organizations`,
`organization_memberships`, and `audit_events`. Slice 2 adds only
`driver_profiles` and `vehicles`. Slice 3 adds only `campaigns` and
`campaign_creatives`. Slice 4 adds only `campaign_zones` with a PostGIS
`geometry(MultiPolygon,4326)` column and GiST index. Slice 5 adds only
`campaign_assignments` and `campaign_activation_events`. Slice 6 adds only
`trip_sessions`, `location_ping_batches`, and `location_pings` with a PostGIS
`geometry(Point,4326)` point column and GiST index. Slice 7 adds only
`trip_analytics` and `fraud_flags`. Slice 8 adds only `traffic_density_profiles`
and `impression_estimates`. Slice 9 adds only `campaign_payout_rules`,
`payout_calculations`, and `earnings_ledger_entries`. Slice 10 adds no migration and
no tables; advertiser reporting is on-demand aggregation over existing stored data.
Slice 11 adds no migration and no tables; heatmaps are bounded on-demand PostGIS
aggregation over existing stored pings, trips, analytics, and estimates.
Slice 12 adds no migration and no tables; demo data is inserted by explicit local
command only.
Slice 13 adds no migration and no tables; MVP hardening is implemented through
settings validation, API validation, contract snapshotting, README/runbook notes, and
tests.

## Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Compose starts the API, the arq worker, PostgreSQL/PostGIS, and Redis. The
`worker` service (no published port) automates post-trip processing — analytics,
fraud flags, impression estimate, and payout calculation for ended trips — via an
enqueue on trip end plus a Postgres-derived sweep; see "Post-trip processing
worker" in `docs/runbook.md`. Its payout stage uses the approved `payout_v2`
hourly-pay and daily-cap model. Since S4, this worker is also responsible for
partition premaking, coverage monitoring, and retention, so it is mandatory in
production.

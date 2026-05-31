# Mobility AdTech API

Backend foundation for the Mobility AdTech & Audience Attribution Platform.

## Stack

- Python 3.12
- FastAPI
- Pydantic v2 and pydantic-settings
- SQLAlchemy 2.x async with asyncpg
- Alembic
- PostgreSQL with PostGIS
- Redis
- pytest and ruff
- Docker Compose

## Current Scope

This repo currently contains Slice 8: project foundation, request IDs, expected error
envelope, SQLAlchemy/Alembic foundation, JWT login, current-user context, RBAC, admin
user management, advertiser organizations, organization memberships, audit events,
driver profiles, vehicle profiles, advertiser campaign metadata, campaign creative
metadata, advertiser campaign zones/geofences, campaign assignment and driver
activation lifecycle, driver trip/session tracking, batched GPS location ping
ingestion, deterministic route analytics, basic fraud/anomaly flags, traffic density
profiles, deterministic impression estimates, Docker Compose, tests, and linting.

Business features such as payouts, reports beyond the campaign impression summary,
heatmaps, and seed data begin in later approved slices.

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

Protected endpoints use bearer auth:

```http
Authorization: Bearer <access_token>
```

Admin-created users require passwords at least `PASSWORD_MIN_LENGTH` characters long.
Emails are normalized to lowercase before storage and login lookup. JWT signing uses
`JWT_SECRET_KEY`, `JWT_ALGORITHM`, and `ACCESS_TOKEN_EXPIRE_MINUTES`.
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
current advertiser organization using `estimated_at` for date filters. Payouts,
earnings, cost summaries, dashboard reporting beyond this summary, and heatmaps are
not part of Slice 8.

## Tests

```powershell
python -m pytest
```

Plain host tests use SQLite for speed and may skip PostGIS-specific checks unless a
PostGIS database URL is configured. To run the PostGIS-backed trip and analytics
verification:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://mobility:mobility@localhost:5433/mobility"
python -m pytest tests/test_trips.py tests/test_trip_analytics.py tests/test_impression_estimates.py -q
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
and `impression_estimates`.

## Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Compose starts the API, PostgreSQL/PostGIS, and Redis.

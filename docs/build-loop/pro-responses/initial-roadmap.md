1. Recommended backend stack

The brief’s backend needs are geospatial, analytics-heavy, API-first, and dashboard/mobile-client friendly: campaign management, driver GPS tracking, route analytics, impression estimation, dynamic payouts, fraud checks, advertiser reports, and heatmaps are all explicitly part of the MVP direction. Retargeting and AI/computer-vision counting are future layers, not MVP layers. 

Developer_Product_Brief_Mobilit…

Layer	Decision	Why
Backend framework	Python 3.12 + FastAPI	FastAPI is a strong fit because it is API-first, type-hint driven, produces OpenAPI docs automatically, and has built-in patterns for validation, security, dependency injection, and testing. 
FastAPI
+2
FastAPI
+2

API style	REST JSON API, versioned under /api/v1	Best fit for admin dashboard, advertiser dashboard, and driver/mobile clients. Avoid GraphQL until frontend proves complex cross-resource query needs.
Database	PostgreSQL + PostGIS	Campaigns, users, organizations, assignments, ledgers, and reports are relational; pings, routes, campaign zones, and heatmaps are spatial. PostGIS extends PostgreSQL with storage, indexing, and querying for geospatial data, including lat/lon geography support. 
PostGIS
+1

ORM / migrations	SQLAlchemy 2.x async + Alembic	SQLAlchemy supports async Core/ORM usage, and Alembic is the standard migration tool for SQLAlchemy-backed relational schemas. 
SQLAlchemy Documentation
+1

Geospatial ORM helper	GeoAlchemy2	Lets the API use SQLAlchemy models while still relying on PostGIS for real spatial operations.
Cache / jobs	Redis + Celery	Redis is useful for rate limits, idempotency, short-lived caches, and Celery job transport; Celery supports Redis as a broker/backend. 
Redis
+1

Auth	First-party email/password auth, JWT bearer tokens, RBAC	The product needs admin, advertiser, and driver access boundaries. FastAPI has standard JWT/OAuth2 bearer-token security patterns. 
FastAPI
+1

Testing	pytest + FastAPI TestClient/httpx + DB integration tests	FastAPI’s testing path uses TestClient/httpx; pytest fixtures will support repeatable service and database tests. 
FastAPI
+1

Local dev	Docker Compose	Run API, Postgres/PostGIS, Redis, and later worker locally.
Deployment	Not now	Production AWS/GCP deployment is deferred unless explicitly requested. The backend should be deployment-ready, not cloud-deployed.
Frontend/mobile	Not now	Backend exposes stable contracts for future Next.js and mobile apps.

Primary architectural decision: build a modular monolith, not microservices. This keeps delivery fast while still separating domains cleanly enough to extract workers/services later.

2. Backend architecture overview
Runtime components
clients
  ├── admin dashboard
  ├── advertiser dashboard
  └── driver mobile app
        │
        ▼
FastAPI backend
  ├── API routers
  ├── auth/RBAC dependencies
  ├── domain services
  ├── analytics services
  ├── payout services
  └── repository/data access layer
        │
        ├── PostgreSQL + PostGIS
        └── Redis
              └── Celery worker, later slices
Code organization
app/
  main.py
  api/
    v1/
      router.py
      auth.py
      users.py
      organizations.py
      drivers.py
      vehicles.py
      campaigns.py
      creatives.py
      zones.py
      assignments.py
      tracking.py
      analytics.py
      payouts.py
      reports.py
      heatmaps.py
  core/
    config.py
    security.py
    errors.py
    logging.py
    pagination.py
  db/
    session.py
    base.py
  models/
  schemas/
  services/
  repositories/
  workers/
  seeds/
alembic/
tests/
Backend design rules

Use thin API routers, service-layer business logic, SQLAlchemy models for persistence, Pydantic schemas for request/response contracts, and formula-versioned analytics/payout calculations.

All APIs should use UUID resource IDs, UTC timestamptz, explicit pagination, standard error responses, and role-aware authorization. Geospatial payloads should accept and return GeoJSON where useful, but storage and spatial computation should live in PostGIS.

Standard API response conventions

Errors:

JSON
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable message",
    "details": {},
    "request_id": "..."
  }
}

Paginated lists:

JSON
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

Geo endpoints should return either GeoJSON FeatureCollection objects or JSON summaries with geometry encoded as GeoJSON.

3. Build-now MVP scope

Build now:

Project foundation.

Auth and role-based access control.

Admin, advertiser, and driver user foundations.

Advertiser organizations/accounts.

Driver profiles.

Vehicle profiles.

Campaign management.

Campaign creative metadata.

Campaign target zones/geofences.

Campaign assignment and activation for drivers/vehicles.

GPS/location ping ingestion.

Trip/session tracking.

Route analytics v1.

Impression estimation v1.

Payout calculation v1.

Driver earnings ledger.

Advertiser dashboard summary APIs.

Campaign report APIs.

Heatmap/geospatial aggregation APIs.

Basic fraud/anomaly flags.

Seed/demo data.

API documentation through OpenAPI.

Automated tests/checks.

The MVP should be useful before frontend work starts: a frontend team should be able to log in, create campaigns, onboard drivers/vehicles, activate campaigns, send location pings, and retrieve campaign analytics, reports, heatmaps, and driver earnings.

4. Deferred/future scope

Defer:

Offline-to-online retargeting.

Anonymous audience pooling.

Device identity graphs.

Pixel integrations.

AI/computer-vision counting.

Advanced ML fraud detection.

Automated bank/mobile-money settlement.

Full ad creative binary storage pipeline unless needed by frontend.

Real external traffic-density provider integrations.

Mobile app implementation.

Frontend implementation.

Production cloud deployment.

Microservices/event streaming/Kafka.

Advanced billing/invoicing/tax.

Real-time WebSocket dashboard updates.

Driver document verification/KYC.

Multi-currency settlement complexity beyond storing campaign currency and amount fields.

5. Full backend slice roadmap
Slice 0 — Project foundation
Field	Definition
Business goal	Create a backend repo that boots, documents itself, connects to infrastructure, and can safely receive future domain work.
Backend scope	FastAPI app, /health, /api/v1/health, app config, logging, error format, Dockerfile, Docker Compose with Postgres/PostGIS and Redis, SQLAlchemy async session, Alembic configured, initial migration enabling postgis and pgcrypto, test setup.
Out of scope	Auth, users, campaigns, tracking, analytics, payouts, seed data.
Data models/tables	No business tables. Alembic only; DB extensions enabled.
API endpoints	GET /health, GET /api/v1/health, optionally GET /api/v1/health/ready for DB readiness.
Validation/security rules	Environment-based settings; no hardcoded secrets; CORS allowlist config; standard error envelope.
Test/check requirements	pytest, health endpoint tests, OpenAPI generation test, config import test, ruff check ..
Frontend contract notes	API base path is /api/v1; docs available at /docs; errors use the standard envelope.
Exit criteria	App runs locally, tests pass, migrations run, Docker Compose starts Postgres/PostGIS and Redis, no business scope added.
Slice 1 — Auth, users, roles, advertiser organizations
Field	Definition
Business goal	Establish identity, admin control, advertiser tenancy, and role separation.
Backend scope	User accounts, password hashing, JWT login, current-user endpoint, admin user creation, advertiser organization creation, org membership.
Out of scope	Driver profiles, vehicle profiles, campaigns, location tracking.
Data models/tables	users, advertiser_organizations, organization_memberships, audit_events.
API endpoints	POST /api/v1/auth/login, GET /api/v1/me, POST /api/v1/admin/users, GET /api/v1/admin/users, PATCH /api/v1/admin/users/{user_id}, POST /api/v1/admin/advertiser-organizations, GET /api/v1/advertiser/organization.
Validation/security rules	Lowercase unique email; password minimum length; hashed passwords only; JWT secret from env; roles: admin, advertiser, driver; advertiser users must be scoped to their org; inactive users cannot log in.
Test/check requirements	Login success/failure, password hash not stored as plaintext, admin-only route protection, advertiser org scoping, /me response.
Frontend contract notes	Login returns bearer token and user role; dashboard routing can key off user.role; advertiser users receive org context.
Exit criteria	Authenticated API calls work; RBAC tests pass; org scoping exists; no campaign or driver profile work added.
Slice 2 — Driver and vehicle foundations
Field	Definition
Business goal	Model the supply side: drivers and vehicles that can later carry campaigns.
Backend scope	Driver profile creation/update, vehicle creation/update, driver-owned vehicle listing, admin visibility.
Out of scope	Campaign activation, GPS tracking, earnings.
Data models/tables	driver_profiles, vehicles.
API endpoints	GET /api/v1/driver/profile, PATCH /api/v1/driver/profile, GET /api/v1/driver/vehicles, POST /api/v1/admin/drivers/{user_id}/vehicles, GET /api/v1/admin/drivers, GET /api/v1/admin/vehicles, PATCH /api/v1/admin/vehicles/{vehicle_id}.
Validation/security rules	Only driver users can own driver profiles; vehicle plate unique per country/city scope; active vehicles require plate_number, vehicle_type, and owner driver.
Test/check requirements	Driver cannot see another driver’s vehicle; admin can list all; invalid vehicle payload rejected.
Frontend contract notes	Driver app can call /driver/profile and /driver/vehicles after login.
Exit criteria	Drivers and vehicles are onboardable and queryable with correct access boundaries.
Slice 3 — Campaign management and creative metadata
Field	Definition
Business goal	Let advertisers/admins create campaigns before geofencing and driver assignment.
Backend scope	Campaign CRUD, campaign statuses, campaign budget/date fields, creative metadata CRUD.
Out of scope	File upload storage, geofences, activation, analytics.
Data models/tables	campaigns, campaign_creatives.
API endpoints	POST /api/v1/advertiser/campaigns, GET /api/v1/advertiser/campaigns, GET /api/v1/advertiser/campaigns/{campaign_id}, PATCH /api/v1/advertiser/campaigns/{campaign_id}, POST /api/v1/advertiser/campaigns/{campaign_id}/creatives, GET /api/v1/advertiser/campaigns/{campaign_id}/creatives, PATCH /api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}.
Validation/security rules	Advertisers only access campaigns in their org; start date before end date; budget nonnegative; currency ISO-like uppercase; cannot activate campaign yet.
Test/check requirements	Org isolation, campaign validation, creative metadata validation.
Frontend contract notes	Creative payload stores asset_url, mime_type, dimensions, duration, checksum; binary upload is deferred.
Exit criteria	Campaigns and creatives can be managed in draft/paused states.
Slice 4 — Campaign target zones/geofences
Field	Definition
Business goal	Enable geospatial targeting and future geozone-aware payout logic.
Backend scope	CRUD for campaign target, exclusion, and bonus zones using GeoJSON polygons/multipolygons.
Out of scope	Heatmap aggregation, routing analytics, automatic map tile generation.
Data models/tables	campaign_zones.
API endpoints	POST /api/v1/advertiser/campaigns/{campaign_id}/zones, GET /api/v1/advertiser/campaigns/{campaign_id}/zones, GET /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}, PATCH /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}, DELETE /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}.
Validation/security rules	Valid GeoJSON only; coordinate ranges enforced; polygon area capped; advertiser org scoping; zone type enum: target, exclusion, bonus.
Test/check requirements	Invalid geometry rejected; persisted geometry can be read back as GeoJSON; org isolation.
Frontend contract notes	Frontend map editor can submit GeoJSON; API returns GeoJSON.
Exit criteria	Campaigns can have usable spatial targeting data in PostGIS.
Slice 5 — Campaign assignment and activation
Field	Definition
Business goal	Connect campaigns to eligible drivers/vehicles and support driver activation.
Backend scope	Assignment creation, driver acceptance, activation/deactivation, assignment lifecycle events.
Out of scope	GPS ping ingestion, analytics, payout calculation.
Data models/tables	campaign_assignments, campaign_activation_events.
API endpoints	POST /api/v1/admin/campaign-assignments, GET /api/v1/admin/campaign-assignments, GET /api/v1/driver/campaign-assignments, POST /api/v1/driver/campaign-assignments/{assignment_id}/accept, POST /api/v1/driver/campaign-assignments/{assignment_id}/activate, POST /api/v1/driver/campaign-assignments/{assignment_id}/deactivate, GET /api/v1/driver/campaign-assignments/active.
Validation/security rules	Driver can only accept own assignments; vehicle must belong to driver; no overlapping active campaign per vehicle unless explicitly allowed later; campaign must be active and within dates.
Test/check requirements	Assignment lifecycle transitions; invalid transitions rejected; no unauthorized activation.
Frontend contract notes	Driver app can show available assignments and one active assignment/vehicle state.
Exit criteria	Driver/vehicle can activate a campaign, creating the prerequisite for tracking.
Slice 6 — GPS ingestion and trip/session tracking
Field	Definition
Business goal	Collect movement data tied to an active campaign assignment.
Backend scope	Trip start/end, batch GPS ping ingestion, current trip lookup, basic idempotency for ping batches.
Out of scope	Full analytics, fraud scoring, impressions, payouts.
Data models/tables	trip_sessions, location_pings, location_ping_batches or idempotency_keys.
API endpoints	POST /api/v1/driver/trips/start, GET /api/v1/driver/trips/current, POST /api/v1/driver/trips/{trip_id}/pings, POST /api/v1/driver/trips/{trip_id}/end, GET /api/v1/driver/trips/{trip_id}.
Validation/security rules	Driver-only; active assignment required; lat/lon bounds; timestamp skew limits; accuracy threshold captured; batch size limit; sequence/idempotency support; cannot write to ended trip.
Test/check requirements	Valid batch creates pings; duplicate idempotency key does not double-insert; invalid coordinates rejected; ended trip blocks pings.
Frontend contract notes	Mobile app should send batched pings with recorded_at, lat, lon, accuracy_m, optional speed/heading, and idempotency key.
Exit criteria	Driver app can record campaign movement sessions.
Slice 7 — Route analytics v1 and basic fraud/anomaly flags
Field	Definition
Business goal	Convert raw pings into trip-level movement metrics and basic trust signals.
Backend scope	Distance, duration, moving time, dwell time, ping quality, zone overlap metrics, anomaly flag generation.
Out of scope	ML fraud detection, external map matching, real traffic feeds.
Data models/tables	trip_analytics, fraud_flags.
API endpoints	POST /api/v1/admin/trips/{trip_id}/recompute-analytics, GET /api/v1/admin/trips/{trip_id}/analytics, GET /api/v1/admin/fraud-flags, GET /api/v1/driver/trips/{trip_id}/analytics-summary.
Validation/security rules	Only admin can force recompute; advertiser does not see raw driver-sensitive details yet; impossible speed, repetitive points, low accuracy, future timestamps, and route looping create flags.
Test/check requirements	Deterministic sample-route tests; impossible-speed flag test; stationary/dwell test; target-zone overlap test.
Frontend contract notes	Admin/debug tools can show trip quality; driver app can show simple trip summary.
Exit criteria	Each ended trip can produce deterministic analytics and fraud flags.
Slice 8 — Impression estimation v1
Field	Definition
Business goal	Estimate campaign exposure from routes using a transparent, versioned formula.
Backend scope	Impression formula, traffic density profile defaults, per-trip impression estimates, campaign rollups.
Out of scope	Real-world audited impression guarantees, audience identity, retargeting, external mobility datasets.
Data models/tables	traffic_density_profiles, impression_estimates.
API endpoints	POST /api/v1/admin/trips/{trip_id}/estimate-impressions, GET /api/v1/advertiser/campaigns/{campaign_id}/impressions/summary, GET /api/v1/admin/impression-estimates.
Validation/security rules	Estimates only for completed trips with analytics; flagged trips can be excluded or discounted; formula version stored; no personal audience identifiers.
Test/check requirements	Formula unit tests; flagged-trip discount/exclusion test; campaign summary aggregation test.
Frontend contract notes	Advertiser dashboard receives estimated impressions, confidence score, formula version, and date range.
Exit criteria	Campaigns have deterministic impression estimates from completed trips.

Recommended v1 formula shape:

estimated_impressions =
  distance_km
  × traffic_density_per_km
  × road_category_weight
  × time_of_day_weight
  × zone_weight
  × quality_score
+
  dwell_minutes
  × dwell_impressions_per_minute
  × zone_weight

Store every estimate with formula_version = "impressions_v1".

Slice 9 — Payout calculation v1 and driver earnings ledger
Field	Definition
Business goal	Translate validated movement/exposure into driver earnings without real payment settlement.
Backend scope	Campaign payout rules, trip payout calculations, immutable earnings ledger entries, driver earnings summary.
Out of scope	Bank/mobile-money settlement, tax, invoicing, chargebacks.
Data models/tables	campaign_payout_rules, payout_calculations, earnings_ledger_entries.
API endpoints	POST /api/v1/admin/trips/{trip_id}/calculate-payout, GET /api/v1/driver/earnings/summary, GET /api/v1/driver/earnings/ledger, GET /api/v1/admin/payout-calculations, GET /api/v1/advertiser/campaigns/{campaign_id}/cost-summary.
Validation/security rules	Idempotent payout calculation per trip/formula version; ledger entries immutable except reversal entries; currency consistent with campaign; fraud flags reduce or block payout according to rule.
Test/check requirements	Payout formula unit tests; no duplicate ledger entries; driver can only see own ledger; advertiser sees aggregate campaign cost only.
Frontend contract notes	Driver earnings screen can show pending/available/voided amounts; no “withdraw” API yet.
Exit criteria	Completed trips can generate driver earnings and advertiser campaign cost summaries.

Recommended v1 payout formula shape:

gross_payout =
  distance_km × base_rate_per_km
  + active_hours × base_rate_per_hour
  + target_zone_distance_km × zone_bonus_rate_per_km

quality_adjusted_payout =
  gross_payout × quality_multiplier

final_payout =
  max(0, min(quality_adjusted_payout, configured_cap))

Store every calculation with formula_version = "payout_v1".

Slice 10 — Advertiser dashboard and campaign reporting APIs
Field	Definition
Business goal	Give the future advertiser frontend useful dashboard data.
Backend scope	Dashboard summary, campaign summary, daily metrics, campaign trips, campaign creative/zone summary.
Out of scope	Frontend charts, PDF exports, billing invoices.
Data models/tables	campaign_daily_metrics table or materialized rollup service.
API endpoints	GET /api/v1/advertiser/dashboard/summary, GET /api/v1/advertiser/campaigns/{campaign_id}/summary, GET /api/v1/advertiser/campaigns/{campaign_id}/daily-metrics, GET /api/v1/advertiser/campaigns/{campaign_id}/trips, GET /api/v1/advertiser/campaigns/{campaign_id}/report.
Validation/security rules	Strict org scoping; advertiser sees campaign-level/aggregate driver data, not private raw driver tracking unless explicitly allowed later; date range required or defaulted.
Test/check requirements	Aggregation tests; org isolation; date range filtering; empty campaign response shape.
Frontend contract notes	Dashboard can be built from stable summary cards, time series, and campaign report endpoints.
Exit criteria	Advertiser dashboard can render MVP campaign performance without custom backend queries.
Slice 11 — Heatmap/geospatial aggregation APIs
Field	Definition
Business goal	Support map heatmaps for routes, exposure, and campaign concentration.
Backend scope	Bounded geospatial aggregation over pings/trips/impression estimates; return GeoJSON heatmap cells.
Out of scope	Mapbox integration, custom tile server, realtime maps.
Data models/tables	Optional heatmap_cache; otherwise compute on demand from location_pings, trip_analytics, and impression_estimates.
API endpoints	GET /api/v1/advertiser/campaigns/{campaign_id}/heatmap?bbox=&resolution=&metric=, GET /api/v1/admin/heatmap?bbox=&resolution=&metric=.
Validation/security rules	bbox required; resolution clamped; max date range; org scoping; advertiser receives aggregated cells only.
Test/check requirements	Bbox filtering; resolution clamp; GeoJSON response validation; org isolation.
Frontend contract notes	Response is a GeoJSON FeatureCollection with properties like ping_count, distance_m, estimated_impressions, weight.
Exit criteria	Dashboard map can render campaign heatmaps from backend data.
Slice 12 — Seed/demo data and API documentation hardening
Field	Definition
Business goal	Make the backend immediately usable by frontend teams and demos.
Backend scope	Seed script creating admin, advertiser org, advertiser user, driver user, vehicle, campaign, creative, zones, assignment, sample trip pings, analytics, impressions, payout, ledger. OpenAPI tags/examples.
Out of scope	Production data import, live traffic data, cloud deployment.
Data models/tables	No new required tables.
API endpoints	No new required endpoints; improve examples and docs.
Validation/security rules	Seed credentials only in local/dev; production refuses default seed secrets.
Test/check requirements	End-to-end smoke test from login to dashboard summary; OpenAPI schema generation test.
Frontend contract notes	Frontend can run against seeded data immediately.
Exit criteria	A new developer can start the stack, seed data, log in, and see realistic dashboard/tracking/reporting responses.
Slice 13 — MVP hardening and contract freeze
Field	Definition
Business goal	Prepare the backend MVP for frontend integration without changing product scope.
Backend scope	Pagination consistency, audit logging review, indexes, idempotency review, rate limits on ingestion/auth, API contract snapshot, README.
Out of scope	New features, production cloud deployment, advanced fraud/ML.
Data models/tables	Possible api_rate_limit_events only if needed; otherwise no new product tables.
API endpoints	No new product endpoints; may add GET /api/v1/meta for version/build info.
Validation/security rules	Ensure no wildcard CORS in non-dev, no default secrets, role checks on every route, privacy boundaries for advertiser reports.
Test/check requirements	Full test suite, lint, migration test, API contract snapshot, basic load-ish test for ping ingestion service.
Frontend contract notes	Mark MVP API response shapes stable.
Exit criteria	Backend MVP is ready for frontend implementation.
6. Data model roadmap
Foundation
alembic_version
Postgres extensions: postgis, pgcrypto
Identity and tenancy
users
  id uuid pk
  email citext/unique normalized
  password_hash text
  full_name text
  phone text nullable
  role enum: admin, advertiser, driver
  status enum: active, invited, suspended, disabled
  created_at timestamptz
  updated_at timestamptz

advertiser_organizations
  id uuid pk
  name text
  billing_email text nullable
  country_code text nullable
  currency text
  status enum
  created_at timestamptz
  updated_at timestamptz

organization_memberships
  id uuid pk
  organization_id fk
  user_id fk
  role enum: owner, manager, viewer
  status enum
  created_at timestamptz

audit_events
  id uuid pk
  actor_user_id fk nullable
  action text
  entity_type text
  entity_id uuid/text nullable
  metadata jsonb
  created_at timestamptz
Drivers and vehicles
driver_profiles
vehicles
Campaigns
campaigns
campaign_creatives
campaign_zones
campaign_assignments
campaign_activation_events
Tracking
trip_sessions
location_ping_batches / idempotency_keys
location_pings
Analytics and fraud
trip_analytics
fraud_flags
traffic_density_profiles
impression_estimates
Payouts and reporting
campaign_payout_rules
payout_calculations
earnings_ledger_entries
campaign_daily_metrics
optional heatmap_cache
Key database rules

Use UUID primary keys, UTC timestamps, soft status fields instead of hard deletes for business entities, immutable ledger entries, and GiST indexes on geospatial columns.

Important indexes:

users(email)
organization_memberships(user_id, organization_id)
campaigns(organization_id, status, start_date, end_date)
campaign_zones USING gist(geom)
campaign_assignments(driver_id, vehicle_id, status)
trip_sessions(driver_id, assignment_id, status, started_at)
location_pings(trip_session_id, recorded_at)
location_pings(driver_id, recorded_at)
location_pings USING gist(geom)
impression_estimates(campaign_id, trip_session_id)
earnings_ledger_entries(driver_id, occurred_at)
campaign_daily_metrics(campaign_id, metric_date)
7. API roadmap
System
http
GET /health
GET /api/v1/health
GET /api/v1/health/ready
GET /api/v1/meta
Auth and current user
http
POST /api/v1/auth/login
GET  /api/v1/me
Admin users and organizations
http
POST  /api/v1/admin/users
GET   /api/v1/admin/users
PATCH /api/v1/admin/users/{user_id}

POST  /api/v1/admin/advertiser-organizations
GET   /api/v1/admin/advertiser-organizations
PATCH /api/v1/admin/advertiser-organizations/{organization_id}
Advertiser organization
http
GET /api/v1/advertiser/organization
Driver and vehicle
http
GET   /api/v1/driver/profile
PATCH /api/v1/driver/profile
GET   /api/v1/driver/vehicles

GET   /api/v1/admin/drivers
GET   /api/v1/admin/vehicles
POST  /api/v1/admin/drivers/{user_id}/vehicles
PATCH /api/v1/admin/vehicles/{vehicle_id}
Campaigns, creatives, zones
http
POST  /api/v1/advertiser/campaigns
GET   /api/v1/advertiser/campaigns
GET   /api/v1/advertiser/campaigns/{campaign_id}
PATCH /api/v1/advertiser/campaigns/{campaign_id}

POST  /api/v1/advertiser/campaigns/{campaign_id}/creatives
GET   /api/v1/advertiser/campaigns/{campaign_id}/creatives
PATCH /api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}

POST   /api/v1/advertiser/campaigns/{campaign_id}/zones
GET    /api/v1/advertiser/campaigns/{campaign_id}/zones
GET    /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}
PATCH  /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}
DELETE /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}
Assignments and activation
http
POST /api/v1/admin/campaign-assignments
GET  /api/v1/admin/campaign-assignments

GET  /api/v1/driver/campaign-assignments
POST /api/v1/driver/campaign-assignments/{assignment_id}/accept
POST /api/v1/driver/campaign-assignments/{assignment_id}/activate
POST /api/v1/driver/campaign-assignments/{assignment_id}/deactivate
GET  /api/v1/driver/campaign-assignments/active
Tracking
http
POST /api/v1/driver/trips/start
GET  /api/v1/driver/trips/current
POST /api/v1/driver/trips/{trip_id}/pings
POST /api/v1/driver/trips/{trip_id}/end
GET  /api/v1/driver/trips/{trip_id}
Analytics, impressions, fraud
http
POST /api/v1/admin/trips/{trip_id}/recompute-analytics
GET  /api/v1/admin/trips/{trip_id}/analytics
GET  /api/v1/driver/trips/{trip_id}/analytics-summary
GET  /api/v1/admin/fraud-flags

POST /api/v1/admin/trips/{trip_id}/estimate-impressions
GET  /api/v1/advertiser/campaigns/{campaign_id}/impressions/summary
GET  /api/v1/admin/impression-estimates
Payouts and earnings
http
POST /api/v1/admin/trips/{trip_id}/calculate-payout
GET  /api/v1/driver/earnings/summary
GET  /api/v1/driver/earnings/ledger
GET  /api/v1/admin/payout-calculations
GET  /api/v1/advertiser/campaigns/{campaign_id}/cost-summary
Advertiser dashboard and reports
http
GET /api/v1/advertiser/dashboard/summary
GET /api/v1/advertiser/campaigns/{campaign_id}/summary
GET /api/v1/advertiser/campaigns/{campaign_id}/daily-metrics
GET /api/v1/advertiser/campaigns/{campaign_id}/trips
GET /api/v1/advertiser/campaigns/{campaign_id}/report
Heatmaps
http
GET /api/v1/advertiser/campaigns/{campaign_id}/heatmap
GET /api/v1/admin/heatmap
8. Slice dependency order
Slice 0 Foundation
  ↓
Slice 1 Auth, users, roles, orgs
  ↓
Slice 2 Drivers and vehicles
  ↓
Slice 3 Campaigns and creatives
  ↓
Slice 4 Campaign zones/geofences
  ↓
Slice 5 Assignments and activation
  ↓
Slice 6 GPS ingestion and trip sessions
  ↓
Slice 7 Route analytics and fraud flags
  ↓
Slice 8 Impression estimation
  ↓
Slice 9 Payouts and earnings ledger
  ↓
Slice 10 Advertiser dashboard/reporting
  ↓
Slice 11 Heatmaps
  ↓
Slice 12 Seed/demo data and API docs
  ↓
Slice 13 MVP hardening and contract freeze

Parallelism should be avoided until Slice 6 is complete because many later features depend on shared assumptions around assignment, trip, and ping data.

9. Codex-ready prompt — Slice 0 only

Send this prompt to Codex first. Do not let Codex implement Slice 1 yet.

You are implementing Slice 0 of a greenfield Mobility AdTech & Audience Attribution backend.

You must implement only the approved Slice 0 foundation. Do not implement users, auth, campaigns, drivers, vehicles, GPS tracking, analytics, payouts, reports, seed data, frontend code, cloud deployment, retargeting, AI, or payment settlement.

STACK — fixed, do not change:
- Python 3.12
- FastAPI
- Pydantic v2 + pydantic-settings
- SQLAlchemy 2.x async
- asyncpg for app DB access
- Alembic for migrations
- PostgreSQL + PostGIS
- Redis in Docker Compose, even if unused in Slice 0
- pytest
- httpx/FastAPI TestClient
- ruff
- Docker Compose for local infrastructure

Business goal:
Create a clean backend foundation that boots, documents itself, connects to infrastructure, supports future Alembic migrations, and has basic tests.

Required implementation scope:
1. Create the backend project structure.
2. Create a FastAPI app with:
   - `GET /health`
   - `GET /api/v1/health`
   - optional `GET /api/v1/health/ready` that checks DB connectivity if DATABASE_URL is configured.
3. Configure app settings from environment variables.
4. Add standard JSON error envelope support for expected app errors.
5. Add request ID middleware or equivalent request ID propagation.
6. Configure CORS from environment allowlist. Do not hardcode permissive production CORS.
7. Configure SQLAlchemy async database session infrastructure.
8. Configure Alembic.
9. Add an initial Alembic migration that enables:
   - `pgcrypto`
   - `postgis`
   No business tables yet.
10. Add Dockerfile.
11. Add docker-compose.yml with:
   - API service
   - PostgreSQL/PostGIS service
   - Redis service
12. Add `.env.example`.
13. Add README with local setup commands.
14. Add pytest tests for:
   - `/health`
   - `/api/v1/health`
   - OpenAPI schema generation
   - settings import/initialization
15. Add ruff configuration.

Expected directory shape:
- app/main.py
- app/api/v1/router.py
- app/api/v1/health.py
- app/core/config.py
- app/core/errors.py
- app/core/logging.py or equivalent
- app/core/middleware.py or equivalent
- app/db/session.py
- app/db/base.py
- alembic/
- tests/

Required conventions:
- API version prefix must be `/api/v1`.
- Service name should be `mobility-adtech-api`.
- Use UUID-friendly/Postgres-ready defaults for future models, but create no business models now.
- Use UTC timestamps where timestamps appear.
- Use environment variables for all secrets/config.
- Do not commit real secrets.
- Keep routers thin and structure ready for future domain routers.
- Do not add unnecessary frameworks or services.

Stop conditions:
- Stop after Slice 0.
- Do not add auth, user tables, campaign tables, driver tables, tracking tables, or analytics tables.
- Do not add frontend assets.
- Do not add production cloud deployment.
- Do not add speculative features.

Commands/checks you must support:
- `python -m pytest`
- `ruff check .`
- `alembic upgrade head`
- `docker compose up --build`

Before coding, output a CODEX PLAN using the required report format.
After coding, output a CODEX BUILD REPORT using the required report format.
10. Reserved Codex-ready prompt — Slice 1 only

Use this only after Slice 0 receives PASS. Do not send it before Slice 0 is accepted.

You are implementing Slice 1 of the Mobility AdTech & Audience Attribution backend.

Slice 0 foundation is assumed complete and accepted. You must build on it without changing the approved stack or introducing speculative scope.

You must implement only Slice 1: auth, users, roles, advertiser organizations, organization memberships, and audit events.

Do not implement driver profiles, vehicle profiles, campaigns, creatives, geofences, campaign assignments, GPS tracking, analytics, impressions, payouts, heatmaps, seed/demo trip data, frontend code, cloud deployment, retargeting, AI, or payment settlement.

STACK — fixed, do not change:
- Python 3.12
- FastAPI
- Pydantic v2 + pydantic-settings
- SQLAlchemy 2.x async
- Alembic
- PostgreSQL + PostGIS
- JWT bearer auth
- Secure password hashing
- pytest
- ruff

Business goal:
Establish identity, role-based access, admin user management, advertiser organization tenancy, and current-user context for future frontend/mobile work.

Required data models/tables:
1. `users`
   - id uuid primary key
   - email unique, normalized lowercase
   - password_hash
   - full_name
   - phone nullable
   - role enum/string constrained to: `admin`, `advertiser`, `driver`
   - status enum/string constrained to: `active`, `invited`, `suspended`, `disabled`
   - created_at timestamptz
   - updated_at timestamptz
2. `advertiser_organizations`
   - id uuid primary key
   - name
   - billing_email nullable
   - country_code nullable
   - currency default `NGN` unless config says otherwise
   - status enum/string constrained to: `active`, `suspended`, `disabled`
   - created_at timestamptz
   - updated_at timestamptz
3. `organization_memberships`
   - id uuid primary key
   - organization_id foreign key
   - user_id foreign key
   - role enum/string constrained to: `owner`, `manager`, `viewer`
   - status enum/string constrained to: `active`, `invited`, `disabled`
   - created_at timestamptz
   - unique constraint on `(organization_id, user_id)`
4. `audit_events`
   - id uuid primary key
   - actor_user_id nullable foreign key to users
   - action text
   - entity_type text
   - entity_id text nullable
   - metadata json/jsonb
   - created_at timestamptz

Required API endpoints:
1. `POST /api/v1/auth/login`
   - Input: email, password
   - Output: bearer access token, token type, user summary
2. `GET /api/v1/me`
   - Requires auth
   - Output: current user summary and advertiser organization context if applicable
3. `POST /api/v1/admin/users`
   - Admin-only
   - Creates user with role/status/password
4. `GET /api/v1/admin/users`
   - Admin-only
   - Paginated
5. `PATCH /api/v1/admin/users/{user_id}`
   - Admin-only
   - Update full_name, phone, status, role where safe
6. `POST /api/v1/admin/advertiser-organizations`
   - Admin-only
   - Creates advertiser organization
   - Optionally attaches an existing advertiser user as owner if supplied
7. `GET /api/v1/advertiser/organization`
   - Advertiser-only
   - Returns the advertiser’s organization and membership

Validation/security rules:
- Email must be normalized lowercase and unique.
- Passwords must never be stored plaintext.
- Minimum password length: 12 characters.
- Disabled/suspended users cannot log in.
- JWT secret must come from environment.
- JWT expiry must be configurable.
- Admin-only endpoints must reject advertiser/driver users.
- Advertiser organization endpoint must reject admin/driver users unless admin endpoint is used.
- Advertiser users must only see their own organization context.
- Use standard error envelope from Slice 0.
- Add audit events for admin-created users and organizations.

Testing requirements:
- Login succeeds with correct credentials.
- Login fails with bad password.
- Login fails for disabled/suspended user.
- Password hash is not plaintext.
- `/api/v1/me` requires auth.
- Admin endpoint rejects non-admin users.
- Admin can create/list/update users.
- Admin can create advertiser organization.
- Advertiser user can retrieve only own organization context.
- Duplicate email is rejected.
- Migration applies cleanly.

Frontend contract notes:
- Login response must include:
  - `access_token`
  - `token_type`
  - `user.id`
  - `user.email`
  - `user.role`
  - `user.status`
- `/api/v1/me` must be enough for frontend route guards.
- Advertiser org context must include organization id/name/currency and membership role.

Stop conditions:
- Stop after Slice 1.
- Do not implement driver profile/vehicle/campaign/tracking/analytics/payout models.
- Do not implement refresh tokens unless already trivially supported by the existing foundation; access token is enough for this slice.
- Do not add public self-registration yet.
- Do not add OAuth/social login.
- Do not add frontend or cloud deployment.

Commands/checks you must support:
- `python -m pytest`
- `ruff check .`
- `alembic upgrade head`

Before coding, output a CODEX PLAN using the required report format.
After coding, output a CODEX BUILD REPORT using the required report format.
11. Exact report format Codex must use
Codex planning report format
CODEX PLAN

Slice:
Scope understood:
Files to create/change:
Database migrations:
API endpoints:
Tests to add/update:
Security/validation checks:
Explicitly out of scope:
Assumptions:
Risks or blockers:
Codex build report format
CODEX BUILD REPORT

Slice:
Status: PASS_CANDIDATE | PARTIAL | BLOCKED

Summary:
Files changed:
Database migrations:
API endpoints implemented:
Security/validation implemented:
Tests added/updated:
Commands run:
Command results:
Known issues:
Out-of-scope compliance:
Manual verification steps:
Questions for architect:
My review classification after each Codex report

PASS means the slice meets scope, tests/checks pass, no stack drift, no speculative features, and the frontend contract is stable enough for that slice.

FIX means the implementation is directionally correct but has missing tests, small contract issues, incomplete validation, weak error handling, migration issues, or minor scope mistakes. I will issue a deterministic amendment prompt.

REJECT means Codex chose a different stack, implemented the wrong slice, skipped core requirements, introduced unsafe security shortcuts, or overbuilt major deferred features. I will issue a replacement prompt or rollback instruction.
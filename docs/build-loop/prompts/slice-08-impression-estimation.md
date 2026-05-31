You are implementing Slice 8 of the Mobility AdTech & Audience Attribution backend.

Slice 0 project foundation, Slice 1 auth/users/advertiser organizations, Slice 2 driver/vehicle foundations, Slice 3 campaign/creative metadata, Slice 4 campaign zones/geofences, Slice 5 campaign assignment/activation, Slice 6 trip tracking/GPS ping ingestion, and Slice 7 route analytics/fraud flags have been accepted by Pro review. Build on the existing repo foundation. Do not replace the stack, restructure the project unnecessarily, or introduce speculative scope.

Before starting implementation, confirm Slice 7 has been committed or that the working tree contains only the accepted Slice 7 state. If the repo has uncommitted unrelated changes, stop and report them.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, GPS movement data is ingested, and analytics support route analytics, impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

Slice 8 goal:
Implement deterministic impression estimation v1 from completed trip analytics. This slice converts accepted route analytics into transparent, formula-versioned estimated campaign impressions using configurable traffic-density profiles, zone exposure metrics, time-of-day weighting, dwell/stationary exposure, and quality/fraud adjustments. Later slices will use these impression estimates for payout calculation, advertiser dashboard reporting, campaign reports, and heatmap aggregation.

FIXED STACK — DO NOT CHANGE

- Python 3.12
- FastAPI
- Pydantic v2
- pydantic-settings
- SQLAlchemy 2.x async
- asyncpg
- Alembic
- PostgreSQL + PostGIS
- Redis in Docker Compose
- JWT bearer auth
- Existing password hashing/JWT/RBAC from Slice 1
- Existing driver/vehicle foundation from Slice 2
- Existing campaign/creative foundation from Slice 3
- Existing campaign zone/geofence foundation from Slice 4
- Existing campaign assignment/activation foundation from Slice 5
- Existing trip/session/location ping foundation from Slice 6
- Existing route analytics/fraud flag foundation from Slice 7
- pytest
- ruff
- Docker Compose

IMPORTANT LOCAL NOTE

The local coding-guidelines file is named `agent.md`, even if other instructions mention `AGENTS.md`. Read and follow `agent.md`.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the current repo state.
2. Read `agent.md`.
3. Read the accepted Slice 0 through Slice 7 implementation reports under `docs/build-loop/reports/`.
4. Inspect existing app structure, routers, settings, error handling, request ID middleware, DB session setup, Alembic setup, auth dependencies, RBAC patterns, models, schemas, services, and tests.
5. Inspect existing trip analytics, fraud flag, campaign, campaign zone, trip, assignment, driver profile, and vehicle models/services.
6. Confirm the existing API prefix is `/api/v1`.
7. Confirm the existing standard error envelope and reuse it.
8. Confirm the current Alembic head is `0008_route_analytics_and_fraud_flags`.
9. Confirm no Slice 8 traffic density profile or impression estimate tables already exist.
10. Determine existing Decimal serialization conventions and reuse them.
11. Determine existing Postgres/PostGIS test strategy and preserve it.
12. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement only Slice 8:

1. Traffic density profile model, schema, service, and admin API support.
2. Impression estimate model, schema, service, and API support.
3. Deterministic impression estimation v1 from existing `trip_analytics`.
4. Admin endpoint to create/list/read/update traffic density profiles.
5. Admin endpoint to estimate impressions for one ended/analyzed trip.
6. Admin endpoint to list impression estimates.
7. Advertiser endpoint to read campaign impression summary for campaigns in their own organization.
8. Formula-versioned estimate storage.
9. Fraud/quality adjustment using Slice 7 analytics and fraud flags.
10. Alembic migration for exactly the Slice 8 traffic density and impression estimate tables, constraints, and indexes.
11. Tests for formula behavior, idempotent recompute behavior, fraud/quality adjustments, campaign/org scoping, RBAC, migration behavior, and out-of-scope guardrails.
12. README/OpenAPI documentation updates only where needed for Slice 8 usage.

DO NOT IMPLEMENT

- Payout calculation
- Campaign payout rules
- Driver earnings ledger
- Driver earnings APIs
- Advertiser cost summary APIs
- Advertiser dashboard/reporting APIs beyond the specific campaign impression summary endpoint
- Campaign daily metrics
- Heatmap APIs
- Heatmap cache tables
- Billing/invoicing
- Settlement/payment APIs
- Automated payout blocking
- Advanced ML impression models
- External traffic provider integrations
- Real audited impression guarantees
- Device identity, retargeting, or audience pooling
- Background jobs/Celery workers
- Automated estimate scheduling
- Seed/demo trip data
- Map tiles
- Mapbox integration
- Geocoding/reverse-geocoding
- External map matching
- Creative binary upload/storage pipeline
- Public self-registration
- OAuth/social login
- Refresh-token flow
- Frontend/mobile implementation
- GitHub remote/PR setup
- Production cloud deployment
- AI/computer vision
- Real payment settlement

DATA MODEL REQUIREMENTS

Create a new Alembic migration after the Slice 7 migration.

Expected migration name:
`0009_impression_estimation`

Expected down revision:
`0008_route_analytics_and_fraud_flags`

Use UUID primary keys. Prefer database-side UUID generation using `gen_random_uuid()`.

Use timezone-aware timestamps.

Use numeric/decimal columns where precision matters. Match existing project conventions for Decimal serialization.

Use either PostgreSQL enums or string columns with database check constraints. Match the existing repo style unless there is a strong local reason not to.

Create exactly these new business tables:

1. `traffic_density_profiles`

Required columns:

- `id` UUID primary key
- `name` text not null
- `description` text nullable
- `profile_type` constrained to:
  - `default`
  - `urban`
  - `suburban`
  - `highway`
  - `custom`
- `traffic_density_per_km` numeric not null
- `dwell_impressions_per_minute` numeric not null
- `road_category_weight` numeric not null, default `1.0`
- `morning_weight` numeric not null, default `1.0`
- `midday_weight` numeric not null, default `1.0`
- `evening_weight` numeric not null, default `1.0`
- `night_weight` numeric not null, default `0.7`
- `target_zone_weight` numeric not null, default `1.0`
- `bonus_zone_weight` numeric not null, default `1.25`
- `exclusion_zone_weight` numeric not null, default `0.0`
- `is_default` boolean not null, default false
- `status` constrained to:
  - `active`
  - `inactive`
- `metadata` JSON/JSONB not null, default empty object
- `created_at` timezone-aware timestamp not null
- `updated_at` timezone-aware timestamp not null

Rules:

- Traffic density profiles are admin-managed.
- At least one active default profile should be creatable and usable.
- Only one active `is_default = true` profile should exist if feasible with a partial unique index. If cross-DB test compatibility makes that difficult, enforce in service and create the partial index in PostgreSQL migration where feasible.
- Numeric weights and densities must be nonnegative.
- `name` must be trimmed and non-empty.
- `description`, if supplied, should be trimmed.
- `metadata` must be an object.
- This table represents internal estimation assumptions, not external provider integrations.

Suggested constraints/indexes:

- Check constraint for `profile_type`.
- Check constraint for `status`.
- Check constraints for nonnegative numeric values.
- Index on `status`.
- Index on `profile_type`.
- Partial unique index for one active default profile where feasible.

2. `impression_estimates`

Required columns:

- `id` UUID primary key
- `trip_session_id` UUID foreign key to `trip_sessions.id`, not null
- `trip_analytics_id` UUID foreign key to `trip_analytics.id`, not null
- `assignment_id` UUID foreign key to `campaign_assignments.id`, not null
- `campaign_id` UUID foreign key to `campaigns.id`, not null
- `driver_profile_id` UUID foreign key to `driver_profiles.id`, not null
- `vehicle_id` UUID foreign key to `vehicles.id`, not null
- `traffic_density_profile_id` UUID foreign key to `traffic_density_profiles.id`, not null
- `formula_version` text not null, default `impressions_v1`
- `status` constrained to:
  - `estimated`
  - `insufficient_data`
  - `excluded`
- `estimated_impressions` numeric not null, default 0
- `base_distance_impressions` numeric not null, default 0
- `dwell_impressions` numeric not null, default 0
- `target_zone_impressions` numeric not null, default 0
- `bonus_zone_impressions` numeric not null, default 0
- `exclusion_zone_adjustment` numeric not null, default 0
- `quality_multiplier` numeric not null
- `fraud_adjustment_multiplier` numeric not null
- `confidence_score` numeric not null
- `started_at` timezone-aware timestamp nullable
- `ended_at` timezone-aware timestamp nullable
- `estimated_at` timezone-aware timestamp not null
- `metadata` JSON/JSONB not null, default empty object
- `created_at` timezone-aware timestamp not null
- `updated_at` timezone-aware timestamp not null

Rules:

- Exactly one current impression estimate per trip/formula version/profile is acceptable for v1.
- Re-estimating for the same trip/formula version/profile should update the existing row, not create duplicates.
- Impression estimates may be created only from existing trip analytics.
- Trip analytics must be for an ended trip.
- `trip_analytics.status = computed` produces a normal estimate.
- `trip_analytics.status = insufficient_data` produces `status = insufficient_data` and zero or near-zero estimate.
- High-severity open fraud flags should strongly reduce or exclude estimate according to deterministic rules below.
- Store formula version as `impressions_v1`.
- Store campaign/assignment/driver/vehicle foreign keys copied from analytics for efficient later reporting.
- Store transparent formula inputs/outputs in `metadata`.
- Do not compute payouts or cost in this table.
- Do not store audience/device identity data.

Suggested constraints/indexes:

- Unique index on `(trip_session_id, formula_version, traffic_density_profile_id)`.
- Index on `trip_analytics_id`.
- Index on `campaign_id`.
- Index on `assignment_id`.
- Index on `driver_profile_id`.
- Index on `vehicle_id`.
- Index on `(campaign_id, estimated_at)`.
- Index on `(campaign_id, status)`.
- Check constraints for nonnegative impression components.
- Check constraints for `quality_multiplier`, `fraud_adjustment_multiplier`, and `confidence_score` between 0 and 1 if cleanly supported.

Do not create payout, earnings, campaign daily metrics, advertiser reports, heatmap, billing, settlement, ledger, audience, retargeting, or seed tables.

CONFIGURATION REQUIREMENTS

Extend existing settings only as needed.

Add settings such as:

- `IMPRESSION_FORMULA_VERSION`, default `impressions_v1`
- `IMPRESSION_DEFAULT_TRAFFIC_DENSITY_PER_KM`, default `120`
- `IMPRESSION_DEFAULT_DWELL_IMPRESSIONS_PER_MINUTE`, default `3`
- `IMPRESSION_HIGH_FRAUD_MULTIPLIER`, default `0.25`
- `IMPRESSION_MEDIUM_FRAUD_MULTIPLIER`, default `0.70`
- `IMPRESSION_LOW_FRAUD_MULTIPLIER`, default `0.90`
- `IMPRESSION_INSUFFICIENT_DATA_CONFIDENCE`, default `0.10`
- `IMPRESSION_MIN_CONFIDENCE`, default `0.0`
- `IMPRESSION_MAX_CONFIDENCE`, default `1.0`

Update `.env.example` and Docker Compose only if needed.

Validate settings for nonnegative numeric values and multipliers/confidence values between 0 and 1 where applicable.

IMPRESSION FORMULA V1 REQUIREMENTS

Implement a deterministic transparent formula.

Recommended formula:

```text
base_distance_impressions =
  total_distance_km
  × traffic_density_per_km
  × road_category_weight
  × time_of_day_weight
  × quality_multiplier

target_zone_impressions =
  target_zone_distance_km
  × traffic_density_per_km
  × target_zone_weight
  × quality_multiplier

bonus_zone_impressions =
  bonus_zone_distance_km
  × traffic_density_per_km
  × bonus_zone_weight
  × quality_multiplier

dwell_impressions =
  stationary_minutes
  × dwell_impressions_per_minute
  × time_of_day_weight
  × quality_multiplier

exclusion_zone_adjustment =
  exclusion_zone_distance_km
  × traffic_density_per_km
  × exclusion_zone_weight

pre_fraud_estimate =
  base_distance_impressions
  + target_zone_impressions
  + bonus_zone_impressions
  + dwell_impressions
  - exclusion_zone_adjustment

estimated_impressions =
  max(0, pre_fraud_estimate × fraud_adjustment_multiplier)

Rules:

Use trip_analytics.distance_m for total distance.

Use trip_analytics.target_zone_distance_m, bonus_zone_distance_m, and exclusion_zone_distance_m for zone components.

Use trip_analytics.stationary_seconds for dwell/stationary exposure.

Use trip_analytics.quality_score as the base quality_multiplier.

Clamp quality_multiplier to [0, 1].

Determine time_of_day_weight from trip_analytics.started_at or first_ping_at.

Time buckets:

morning: 05:00 through 10:59

midday: 11:00 through 15:59

evening: 16:00 through 20:59

night: 21:00 through 04:59

Use UTC unless the project already has a local timezone convention. Document this in metadata.

For road_category_weight, use the selected traffic density profile’s configured value. Do not integrate road classification yet.

For fraud_adjustment_multiplier:

If any open high-severity fraud flag exists for the trip, use IMPRESSION_HIGH_FRAUD_MULTIPLIER.

Else if any open medium-severity fraud flag exists, use IMPRESSION_MEDIUM_FRAUD_MULTIPLIER.

Else if any open low-severity fraud flag exists, use IMPRESSION_LOW_FRAUD_MULTIPLIER.

Else use 1.0.

If trip_analytics.status = insufficient_data, use status = insufficient_data, estimated impressions 0, and low confidence.

If high-severity flags should make the estimate unusable, keep it as estimated with a strong multiplier unless the implementation clearly chooses excluded. If choosing excluded, document the deterministic rule and test it.

Compute confidence_score deterministically from quality and fraud:

Suggested v1: confidence_score = clamp(quality_multiplier × fraud_adjustment_multiplier, 0, 1)

For insufficient data, use IMPRESSION_INSUFFICIENT_DATA_CONFIDENCE.

Store metadata with:

formula version

traffic density profile values used

time bucket

time of day weight

road category method

fraud flag counts by severity

source analytics id

all major component values

any request metadata

Do not implement external traffic feeds, audited impression guarantees, audience identity, retargeting, or payout logic.

DEFAULT TRAFFIC DENSITY PROFILE BEHAVIOR

Because seed/demo data is a later slice, do not add a broad seed system.

However, Slice 8 needs a usable default profile. Implement one of these safe approaches:

Preferred:

On first estimate, if no active default profile exists, create a default profile using configured settings inside the same service transaction.

Acceptable:

Provide an admin endpoint to create a profile and require a profile id for estimation, but also provide a documented fallback to settings if no profile id is supplied.

Endpoint behavior should be deterministic:

POST /api/v1/admin/trips/{trip_id}/estimate-impressions may accept optional traffic_density_profile_id.

If supplied, use that active profile.

If omitted, use the active default profile.

If no active default exists, create or use a settings-backed default consistently.

Do not add full seed/demo data in this slice.

API ENDPOINTS

Implement these endpoints under /api/v1.

Admin traffic density profile endpoints:

POST /api/v1/admin/traffic-density-profiles

Admin-only.

Input:

JSON
{
  "name": "Default Urban Profile",
  "description": "Default v1 profile for urban routes.",
  "profile_type": "default",
  "traffic_density_per_km": "120",
  "dwell_impressions_per_minute": "3",
  "road_category_weight": "1.0",
  "morning_weight": "1.1",
  "midday_weight": "1.0",
  "evening_weight": "1.2",
  "night_weight": "0.7",
  "target_zone_weight": "1.0",
  "bonus_zone_weight": "1.25",
  "exclusion_zone_weight": "1.0",
  "is_default": true,
  "status": "active",
  "metadata": {}
}

Output: created profile.

Rules:

Admin-only.

If is_default = true, ensure only one active default profile remains.

Validate all numeric values.

Do not call external traffic services.

GET /api/v1/admin/traffic-density-profiles

Admin-only.

Query parameters:

limit, default 50, max 100

offset, default 0

optional status

optional profile_type

optional is_default

Output shape:

JSON
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

GET /api/v1/admin/traffic-density-profiles/{profile_id}

Admin-only.

Returns one traffic density profile.

PATCH /api/v1/admin/traffic-density-profiles/{profile_id}

Admin-only.

Allowed update fields:

JSON
{
  "name": "Updated Profile",
  "description": "Updated description",
  "profile_type": "urban",
  "traffic_density_per_km": "140",
  "dwell_impressions_per_minute": "4",
  "road_category_weight": "1.0",
  "morning_weight": "1.1",
  "midday_weight": "1.0",
  "evening_weight": "1.2",
  "night_weight": "0.7",
  "target_zone_weight": "1.0",
  "bonus_zone_weight": "1.25",
  "exclusion_zone_weight": "1.0",
  "is_default": true,
  "status": "active",
  "metadata": {}
}

Rules:

Admin-only.

If setting this profile as active default, clear active default from others or otherwise enforce uniqueness.

Do not mutate existing impression estimates when profile changes.

Admin impression estimate endpoints:

POST /api/v1/admin/trips/{trip_id}/estimate-impressions

Admin-only.

Input body optional. If implemented, use:

JSON
{
  "traffic_density_profile_id": "optional-profile-uuid",
  "metadata": {}
}

Output: impression estimate response.

Rules:

Admin-only.

Trip must exist.

Trip analytics must exist.

Trip analytics must belong to the requested trip.

Trip must be ended.

If analytics is missing, return clear ANALYTICS_NOT_FOUND or equivalent standard error.

If analytics exists but is insufficient data, create/update an insufficient_data estimate.

Use active traffic density profile.

Recompute must be idempotent for the same trip/formula/profile.

Do not compute payouts.

Do not mutate trip, assignment, campaign, analytics, or fraud flags.

GET /api/v1/admin/impression-estimates

Admin-only.

Query parameters:

limit, default 50, max 100

offset, default 0

optional campaign_id

optional trip_session_id

optional driver_profile_id

optional vehicle_id

optional status

optional traffic_density_profile_id

Output shape:

JSON
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

Advertiser impression summary endpoint:

GET /api/v1/advertiser/campaigns/{campaign_id}/impressions/summary

Advertiser-only.

Query parameters:

optional start_at

optional end_at

Output shape:

JSON
{
  "campaign_id": "uuid",
  "formula_version": "impressions_v1",
  "estimated_impressions": "12345.67",
  "trip_count": 10,
  "estimated_trip_count": 8,
  "insufficient_data_trip_count": 2,
  "excluded_trip_count": 0,
  "average_confidence_score": "0.82",
  "start_at": "2026-05-01T00:00:00Z",
  "end_at": "2026-05-31T23:59:59Z"
}

Rules:

Advertiser-only.

Campaign must belong to the current advertiser organization.

Cross-organization campaign access must not leak data. Prefer 404.

Summary uses stored impression_estimates.

Date filtering should use estimated_at unless a better existing convention is obvious; document the choice.

Do not generate estimates automatically in this summary endpoint.

If no estimates exist, return zeros with stable shape.

Do not expose driver identities or raw trip pings.

Admin should use admin endpoints, not advertiser endpoint.

RESPONSE SHAPE GUIDANCE

Traffic density profile response should include at minimum:

JSON
{
  "id": "uuid",
  "name": "Default Urban Profile",
  "description": "Default v1 profile for urban routes.",
  "profile_type": "default",
  "traffic_density_per_km": "120.0000",
  "dwell_impressions_per_minute": "3.0000",
  "road_category_weight": "1.0000",
  "morning_weight": "1.1000",
  "midday_weight": "1.0000",
  "evening_weight": "1.2000",
  "night_weight": "0.7000",
  "target_zone_weight": "1.0000",
  "bonus_zone_weight": "1.2500",
  "exclusion_zone_weight": "1.0000",
  "is_default": true,
  "status": "active",
  "metadata": {},
  "created_at": "2026-05-31T00:00:00Z",
  "updated_at": "2026-05-31T00:00:00Z"
}

Impression estimate response should include at minimum:

JSON
{
  "id": "uuid",
  "trip_session_id": "uuid",
  "trip_analytics_id": "uuid",
  "assignment_id": "uuid",
  "campaign_id": "uuid",
  "driver_profile_id": "uuid",
  "vehicle_id": "uuid",
  "traffic_density_profile_id": "uuid",
  "formula_version": "impressions_v1",
  "status": "estimated",
  "estimated_impressions": "1234.56",
  "base_distance_impressions": "900.00",
  "dwell_impressions": "120.00",
  "target_zone_impressions": "150.00",
  "bonus_zone_impressions": "100.00",
  "exclusion_zone_adjustment": "35.44",
  "quality_multiplier": "0.9500",
  "fraud_adjustment_multiplier": "1.0000",
  "confidence_score": "0.9500",
  "started_at": "2026-05-31T12:00:00Z",
  "ended_at": "2026-05-31T12:30:00Z",
  "estimated_at": "2026-05-31T12:35:00Z",
  "metadata": {},
  "created_at": "2026-05-31T12:35:00Z",
  "updated_at": "2026-05-31T12:35:00Z"
}

For Decimal values, use the existing project convention. If no convention exists, return Decimal values as strings to avoid JSON float precision ambiguity.

LIKELY FILES/AREAS TO CREATE OR CHANGE

Use existing Slice 0-Slice 7 conventions. Likely create/change:

app/api/v1/router.py

app/api/v1/impressions.py or similar

app/models/impression.py

app/models/__init__.py

app/schemas/impressions.py

app/services/impressions.py

app/core/config.py

app/api/v1/dependencies.py only if needed to reuse admin/advertiser helpers

app/db/base.py only if model imports require update

alembic/versions/0009_impression_estimation.py

.env.example

README.md

tests/test_impression_estimates.py

tests/test_traffic_density_profiles.py

tests/test_migration_slice8.py

Possibly fixture updates in tests/conftest.py

docs/build-loop/reports/slice-08-impression-estimation.md

Keep code simple. Avoid unnecessary abstractions.

TEST REQUIREMENTS

Add/extend tests for:

Traffic density profiles:

Admin can create a traffic density profile.

Admin can list traffic density profiles with pagination response shape.

Admin can read a traffic density profile.

Admin can update a traffic density profile.

Setting one active profile as default clears or otherwise supersedes prior active default.

Invalid profile type is rejected.

Invalid status is rejected.

Blank profile name is rejected.

Negative traffic density is rejected.

Negative dwell impressions per minute is rejected.

Negative weights are rejected.

Metadata must be an object.

Advertiser, driver, and unauthenticated users are rejected from profile endpoints.

Impression estimation:

Admin can estimate impressions for a trip with computed analytics.

Estimate uses stored trip analytics values.

Estimate creates an impression_estimates row.

Re-estimating the same trip/formula/profile updates existing row instead of creating duplicates.

Estimate copies campaign, assignment, driver profile, and vehicle ids from analytics.

Estimate stores formula version impressions_v1.

Estimate stores transparent formula metadata.

Insufficient-data analytics produces status = insufficient_data and low/zero estimate.

Missing analytics returns standard analytics-not-found error.

Active/non-ended trip is rejected.

High-severity open fraud flag applies high fraud multiplier.

Medium-severity open fraud flag applies medium fraud multiplier when no high flag exists.

Low-severity open fraud flag applies low fraud multiplier when no high/medium flag exists.

Quality score affects quality multiplier.

Confidence score is clamped between 0 and 1.

Time-of-day bucket affects selected weight.

Target zone distance contributes target zone impressions.

Bonus zone distance contributes bonus zone impressions.

Exclusion zone distance contributes exclusion adjustment.

Stationary seconds contribute dwell impressions.

Estimated impressions never go below zero.

Optional traffic density profile id selects that active profile.

Inactive traffic density profile cannot be used for estimation.

Admin can list impression estimates with pagination response shape.

Admin can filter estimates by campaign id.

Admin can filter estimates by status.

Advertiser, driver, and unauthenticated users are rejected from admin estimate endpoints.

Advertiser campaign summary:

Advertiser can read impression summary for own campaign.

Advertiser cannot read impression summary for another organization’s campaign.

Advertiser summary returns zero stable shape when no estimates exist.

Advertiser summary aggregates estimated impressions.

Advertiser summary counts estimated, insufficient-data, and excluded estimates.

Advertiser summary computes average confidence score.

Advertiser summary date filters work using documented date field.

Driver and unauthenticated users are rejected from advertiser summary endpoint.

Admin is rejected from advertiser summary endpoint unless existing project pattern explicitly allows admin on advertiser routes; prefer rejection.

Migration and scope:

Alembic migration creates exactly traffic_density_profiles and impression_estimates as new Slice 8 tables.

Migration creates expected constraints and indexes.

Migration does not create payout, earnings, campaign daily metrics, reporting, heatmap, ledger, audience, retargeting, billing, settlement, or seed tables.

Existing Slice 0-Slice 7 tests continue to pass.

API responses do not expose password hashes, raw pings, or unrelated sensitive data.

Testing implementation guidance:

Reuse existing test fixtures and auth helpers from prior slices.

Reuse existing trip analytics factories/helpers where available.

Do not require external network access.

If existing tests use SQLite for speed, maintain compatibility where practical.

Migration verification against Postgres/PostGIS remains required.

Keep tests deterministic.

Avoid making summary endpoint perform automatic estimation; it should aggregate stored estimates only.

CHECKS THAT MUST WORK

The final implementation should support:

python -m pytest
python -m ruff check .
alembic upgrade head

Also verify Python 3.12 through Docker as in prior slices:

docker compose run --rm api python --version
docker compose run --rm api python -m pytest
docker compose run --rm api python -m ruff check .

Postgres/PostGIS migration verification is required:

$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest

If any command cannot be run locally due to missing external runtime or local environment issues, report that honestly with exact evidence.

FRONTEND CONTRACT NOTES

Admin tools can use:

http
POST  /api/v1/admin/traffic-density-profiles
GET   /api/v1/admin/traffic-density-profiles
GET   /api/v1/admin/traffic-density-profiles/{profile_id}
PATCH /api/v1/admin/traffic-density-profiles/{profile_id}

POST /api/v1/admin/trips/{trip_id}/estimate-impressions
GET  /api/v1/admin/impression-estimates

Advertiser dashboard can use:

http
GET /api/v1/advertiser/campaigns/{campaign_id}/impressions/summary

All protected endpoints must use bearer token auth:

http
Authorization: Bearer <token>

After this slice, impression estimates exist as stored records and advertiser campaign impression summaries can be rendered. Payouts, driver earnings, campaign cost summaries, full advertiser dashboard cards, campaign daily metrics, and heatmaps are not available yet.

STANDARD ERROR BEHAVIOR

Use the existing Slice 0-Slice 7 error envelope for expected errors.

Expected examples:

Missing token

Invalid token

Forbidden role

Traffic density profile not found

Traffic density profile inactive

Invalid profile values

Trip not found

Trip not ended

Analytics not found

Impression estimate not found

Campaign not found

Campaign belongs to another organization

Invalid metadata

Invalid pagination/filter values

Do not return raw stack traces.

ACCEPTANCE CRITERIA

Slice 8 is acceptable only if:

Alembic migration creates exactly the approved traffic_density_profiles and impression_estimates tables, constraints, and indexes.

No Slice 9+ payout/earnings/reporting/heatmap/ledger/seed/audience tables are added.

Admin can create/list/read/update traffic density profiles.

One active default profile is enforced or deterministically resolved.

Admin can estimate impressions for trips with existing computed analytics.

Estimation is idempotent for the same trip/formula/profile.

Impression formula uses trip analytics distance, zone metrics, stationary seconds, quality score, time-of-day weights, traffic density profile values, and fraud adjustment.

Insufficient-data analytics is handled deterministically.

Open fraud flags reduce confidence/estimate according to deterministic severity rules.

Estimate metadata explains formula inputs, weights, and adjustments.

Admin can list/filter impression estimates.

Advertiser can read only own campaign impression summary.

Advertiser summary aggregates stored estimates and returns stable zero shape when empty.

Admin/advertiser/driver/unauthenticated access boundaries are enforced.

API responses do not expose password hashes, raw pings, or unrelated sensitive data.

Tests pass.

Ruff passes.

Alembic upgrade head passes against Postgres/PostGIS.

Python 3.12 verification is performed through Docker or explicitly reported if impossible.

No deferred/future scope is implemented.

STOP CONDITIONS

Stop and report instead of implementing if:

Slice 7 accepted foundation is missing or materially different from the packet.

The existing project uses a materially different stack than the approved stack.

agent.md conflicts with this prompt.

The DB/migration setup cannot support Slice 8 tables without reworking previous slices.

Existing trip analytics or fraud flag models make impression estimation ambiguous in a way that requires a product decision.

Existing advertiser campaign tenancy behavior makes summary scoping ambiguous in a way that requires a product decision.

Implementing impression estimates would require external traffic-provider integration.

You are tempted to add payouts, earnings ledger, cost summaries, advertiser dashboards, campaign daily metrics, heatmaps, billing, settlements, audience identity, retargeting, external traffic feeds, background jobs, or seed/demo data.

Otherwise, stop after Slice 8. Do not continue to Slice 9.

REQUIRED CODEX PLAN FORMAT BEFORE CODING

Before coding, output:

CODEX PLAN

Slice:
Scope understood:
Local investigation findings:
Files to create/change:
Database migrations:
API endpoints:
Tests to add/update:
Security/validation checks:
Impression formula approach:
Traffic density profile approach:
Fraud/quality adjustment approach:
Advertiser summary aggregation approach:
Explicitly out of scope:
Assumptions:
Risks or blockers:

REQUIRED CODEX BUILD REPORT FORMAT AFTER CODING

After coding, output:

CODEX BUILD REPORT

Slice:
Status: PASS_CANDIDATE | PARTIAL | BLOCKED

Summary:
Local investigation performed:
Files changed:
Database migrations:
API endpoints implemented:
Security/validation implemented:
Impression formula implemented:
Traffic density profile handling implemented:
Fraud/quality adjustment implemented:
Advertiser summary aggregation implemented:
Tests added/updated:
Commands run:
Command results:
Known issues:
Out-of-scope compliance:
Acceptance criteria checklist:
Manual verification steps:
Questions for Pro reviewer:

REQUIRED PRO REVIEW PACKET FORMAT

The orchestrator must send the Pro reviewer a packet with:

PRO REVIEW PACKET

Slice:
Repo state summary:
Commit status:
Files changed:
Diff summary:
Database migrations:
API endpoints:
Security/validation implemented:
Impression formula implemented:
Traffic density profile handling implemented:
Fraud/quality adjustment implemented:
Advertiser summary aggregation implemented:
Tests/checks run:
Exact command outputs or concise failure excerpts:
Known issues:
Out-of-scope confirmation:
Acceptance criteria checklist:
Codex questions:
Orchestrator recommendation: PASS_CANDIDATE | NEEDS_FIX | BLOCKED

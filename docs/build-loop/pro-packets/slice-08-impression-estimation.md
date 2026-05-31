PRO REVIEW PACKET

Slice:
Slice 8 - Impression estimation v1

Review request:
Please review this Slice 8 implementation for ship readiness. Respond with `PASS`, `FIX REQUIRED`, or `BLOCKED`. If this passes, please say it is safe to commit and provide a recommended commit message plus the full Slice 9 implementation prompt.

Repo state summary:
- Branch: `slice-08-impression-estimation`
- Base accepted state: Slice 7 recorded at `5715e6e docs: record slice 7 commit`
- Slice 7 feature commit: `c696555 feat: add route analytics and fraud flags`
- Current status: uncommitted Slice 8 PASS_CANDIDATE
- Current Alembic head after Slice 8: `0009_impression_estimation`
- API prefix remains `/api/v1`
- Fixed stack preserved: FastAPI, Pydantic v2, SQLAlchemy async, asyncpg, Alembic, PostgreSQL/PostGIS, Redis, JWT, pytest, ruff, Docker Compose.

Commit status:
- No Slice 8 commit has been created yet.
- Working tree contains only the Slice 8 implementation/report/ledger changes listed below plus one Slice 7 migration-test maintenance change needed because Slice 8 is now head.
- Intended commit only after Pro PASS and local reconciliation.

Approved Slice 8 prompt summary:
- Implement only deterministic impression estimation v1 from completed trip analytics.
- Add migration `0009_impression_estimation` after `0008_route_analytics_and_fraud_flags`.
- Create exactly two new business tables: `traffic_density_profiles` and `impression_estimates`.
- Add admin traffic density profile create/list/read/update endpoints.
- Add admin estimate endpoint for one ended/analyzed trip.
- Add admin list impression estimates endpoint.
- Add advertiser campaign impression summary endpoint scoped to the advertiser organization.
- Use stored trip analytics, zone metrics, stationary exposure, quality score, profile values, time-of-day weights, open fraud flag severity multipliers, and transparent formula metadata.
- Do not implement payouts, earnings ledger, campaign cost summaries, dashboard reporting beyond the approved summary endpoint, campaign daily metrics, heatmaps, billing/settlement, external traffic providers, background jobs, seed data, audience identity, retargeting, frontend/mobile, or later-slice scope.

Files changed:
- `.env.example`
- `README.md`
- `alembic/versions/0009_impression_estimation.py`
- `app/api/v1/impressions.py`
- `app/api/v1/router.py`
- `app/core/config.py`
- `app/db/base.py`
- `app/models/impression.py`
- `app/schemas/impressions.py`
- `app/services/impressions.py`
- `docs/build-loop/pro-packets/slice-08-impression-estimation.md`
- `docs/build-loop/reports/slice-08-impression-estimation.md`
- `docs/build-loop/slice-log.md`
- `tests/conftest.py`
- `tests/test_config.py`
- `tests/test_impression_estimates.py`
- `tests/test_migration_slice7.py`
- `tests/test_migration_slice8.py`
- `tests/test_traffic_density_profiles.py`

Diff summary:
- Adds traffic density and impression estimate ORM models with constraints, metadata JSON, timestamps, indexes, active-default uniqueness, and estimate idempotency uniqueness.
- Adds Slice 8 Alembic migration `0009_impression_estimation` after `0008_route_analytics_and_fraud_flags`.
- Adds an impressions router mounted under `/api/v1`.
- Adds admin traffic density profile CRUD/list endpoints, admin impression estimate/list endpoints, and advertiser campaign impression summary endpoint.
- Adds service logic for profile defaults, active profile resolution, ended-trip and analytics checks, deterministic impression components, fraud/quality multipliers, blocked/insufficient handling, idempotent estimate upsert, estimate listing, and advertiser summary aggregation.
- Adds schemas with Decimal-as-string serialization and object metadata validation.
- Adds settings/env docs, README notes, migration guardrails, formula tests, profile tests, RBAC tests, summary tests, and DB-backed migration tests.
- Updates Slice 7 migration test to upgrade to the Slice 7 revision explicitly instead of `head`, preserving older-slice evidence after Slice 8 becomes head.

Database migrations:
- New migration: `alembic/versions/0009_impression_estimation.py`
- Down revision: `0008_route_analytics_and_fraud_flags`
- Creates exactly two Slice 8 business tables:
  - `traffic_density_profiles`
  - `impression_estimates`
- `traffic_density_profiles`:
  - UUID PK with `gen_random_uuid()`
  - name, description, profile type, traffic density, dwell rate, road/time/zone weights, default flag, status, metadata JSONB, created/updated timestamps
  - check constraints for profile type, status, and nonnegative numeric values
  - indexes on status and profile type
  - partial unique index `uq_traffic_density_profiles_active_default` where `is_default = true AND status = 'active'`
- `impression_estimates`:
  - UUID PK with `gen_random_uuid()`
  - FKs to `trip_sessions`, `trip_analytics`, `campaign_assignments`, `campaigns`, `driver_profiles`, `vehicles`, and `traffic_density_profiles`
  - formula version default `impressions_v1`
  - status constrained to `estimated`, `insufficient_data`, `excluded`
  - estimated impression components, quality multiplier, fraud multiplier, confidence score, lifecycle timestamps, estimated timestamp, metadata JSONB, created/updated timestamps
  - nonnegative component checks and multiplier/confidence range checks
  - unique `(trip_session_id, formula_version, traffic_density_profile_id)`
  - indexes on analytics, campaign, assignment, driver, vehicle, profile, `(campaign_id, estimated_at)`, and `(campaign_id, status)`
- DB-backed migration test upgrades to Slice 7, captures base tables, upgrades to head, and asserts the new-table delta is exactly `traffic_density_profiles` and `impression_estimates`.
- DB-backed migration test verifies the Slice 7 long Alembic `version_num` column-width fix remains preserved.
- Does not add payout, earnings, reporting, heatmap, billing, settlement, ledger, audience, retargeting, or seed tables.

API endpoints:
- `POST /api/v1/admin/traffic-density-profiles`
- `GET /api/v1/admin/traffic-density-profiles`
- `GET /api/v1/admin/traffic-density-profiles/{profile_id}`
- `PATCH /api/v1/admin/traffic-density-profiles/{profile_id}`
- `POST /api/v1/admin/trips/{trip_id}/estimate-impressions`
- `GET /api/v1/admin/impression-estimates`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/impressions/summary`

Security/validation implemented:
- Admin endpoints use existing `AdminUserDependency`.
- Advertiser summary uses existing `AdvertiserUserDependency`.
- Advertiser summary scopes campaign ownership through existing org-scoped campaign lookup and returns 404 for cross-org campaigns.
- Admin is rejected from advertiser summary.
- Advertiser/driver/unauthenticated requests are rejected from admin surfaces.
- Driver/unauthenticated requests are rejected from advertiser summary.
- Profile create/update validates name, enum/status values, nonnegative numerics, and object metadata.
- PATCH `metadata: null` or list metadata is rejected by schema validation.
- Estimation requires an existing ended trip and existing trip analytics.
- Missing analytics uses the existing `ANALYTICS_NOT_FOUND` error.
- Inactive profile selection returns `TRAFFIC_DENSITY_PROFILE_INACTIVE`.
- Responses do not expose password hashes, raw pings, driver identities in advertiser summaries, payout data, or unrelated sensitive data.

Impression formula implemented:
- Formula version: `impressions_v1`.
- Components:
  - `base_distance_impressions = total_distance_km * traffic_density_per_km * road_category_weight * time_of_day_weight * quality_multiplier`
  - `target_zone_impressions = target_zone_distance_km * traffic_density_per_km * target_zone_weight * quality_multiplier`
  - `bonus_zone_impressions = bonus_zone_distance_km * traffic_density_per_km * bonus_zone_weight * quality_multiplier`
  - `dwell_impressions = stationary_minutes * dwell_impressions_per_minute * time_of_day_weight * quality_multiplier`
  - `exclusion_zone_adjustment = exclusion_zone_distance_km * traffic_density_per_km * exclusion_zone_weight`
  - pre-fraud estimate is sum of positives minus exclusion adjustment
  - estimated impressions are clamped to >= 0 after applying fraud multiplier
- Uses `TripAnalytics.distance_m`, target/bonus/exclusion distances, stationary seconds, quality score, `started_at` or `first_ping_at`, and UTC time buckets.
- Stores formula metadata with profile values, time bucket, UTC convention, road category method, fraud counts, analytics id, inputs, components, and request metadata.
- Decimal API values are serialized as strings.

Traffic density profile handling implemented:
- Admin can create/list/read/update profiles.
- Active default supersession clears other active defaults.
- PostgreSQL partial unique index enforces one active default.
- Estimation without explicit profile uses the active default profile.
- If no active default exists, the service creates a settings-backed default profile.
- Default-profile creation uses a nested transaction and `IntegrityError` re-read to recover from the partial-unique race.
- Profile changes do not mutate existing estimates.

Fraud/quality adjustment implemented:
- Quality multiplier clamps analytics quality score to `[0, 1]`.
- Open high-severity flag wins, then medium, then low.
- Dismissed/acknowledged fraud flags do not affect multiplier.
- Confidence score is clamped `quality_multiplier * fraud_adjustment_multiplier`.
- Insufficient-data analytics produces `status=insufficient_data`, zero impressions, and configured low confidence.
- Blocked analytics produces `status=excluded`, zero impressions, configured minimum confidence, and `blocked_analytics` metadata.

Advertiser summary aggregation implemented:
- Aggregates stored `impression_estimates` only.
- Does not auto-generate estimates.
- Filters by current formula version before returning a summary labeled `impressions_v1`.
- Uses `estimated_at` for optional date filters.
- Returns stable zero shape when no estimates exist.
- Aggregates estimated impressions, trip count, status counts, and average confidence score.
- Does not expose driver identities, vehicle details, raw pings, payout/cost data, or other later-slice fields.

Tests/checks run:
- `python -m ruff check .`
- `python -m pytest tests/test_config.py tests/test_migration_slice8.py -q`
- `python -m pytest tests/test_impression_estimates.py tests/test_traffic_density_profiles.py -q`
- `python -m alembic upgrade head` with Postgres/PostGIS `DATABASE_URL`
- `python -m alembic current` with Postgres/PostGIS `DATABASE_URL`
- `python -m pytest tests/test_impression_estimates.py tests/test_traffic_density_profiles.py tests/test_migration_slice8.py -q` with Postgres/PostGIS `DATABASE_URL`
- `python -m pytest`
- `python -m pytest` with Postgres/PostGIS `DATABASE_URL`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m pytest`
- `docker compose run --rm api python -m ruff check .`

Exact command outputs or concise results:
- Host ruff:
  - `All checks passed!`
- Host targeted migration/config:
  - `50 passed, 1 skipped, 1 warning in 0.99s`
  - The skip is the DB-backed migration test when no PostGIS URL is configured.
- Host targeted profile/estimate:
  - `15 passed, 1 warning in 29.10s`
- Host Alembic with `DATABASE_URL=postgresql+asyncpg://mobility:mobility@localhost:5433/mobility`:
  - current: `0009_impression_estimation (head)`
- Host targeted PostGIS Slice 8:
  - `17 passed, 1 warning in 41.45s`
- Host full tests without `DATABASE_URL`:
  - `159 passed, 20 skipped, 1 warning in 194.12s`
- Host full tests with same PostGIS `DATABASE_URL`:
  - `179 passed, 1 warning in 287.38s`
- Docker build:
  - image `mobility-api:latest` built successfully
- Docker Python:
  - `Python 3.12.13`
- Docker full tests:
  - `179 passed, 1 warning in 732.94s`
- Docker ruff:
  - `All checks passed!`

Audit/fix reconciliation:
- Sagan checklist covered service/API risks before implementation review.
- Turing checklist covered migration/test risks before implementation review.
- Darwin found blocked analytics, formula-version summary mixing, metadata-null, and default-profile race risks.
- Lagrange found blocked analytics plus DB-backed migration evidence gaps.
- Harvey fixed blocked analytics handling, metadata null/list validation, formula-version summary filtering, default-profile race recovery, and Slice 8 migration evidence.
- Heisenberg fixed the prior Slice 7 migration test to target the Slice 7 revision explicitly now that Slice 8 is head.
- Orchestrator reran full host/PostGIS/Docker checks after those fixes.

Known issues:
- Host Python is 3.14.4, while the fixed stack is Python 3.12. Docker verified Python 3.12.13 successfully.
- Existing FastAPI/TestClient stack emits a deprecation warning about `httpx`; tests pass.
- PostGIS-specific tests intentionally skip on host when no `DATABASE_URL` or `TEST_DATABASE_URL` is configured. They pass with a real PostGIS URL and in Docker.
- The default-profile race recovery is implemented with nested transaction plus re-read on `IntegrityError`; no true concurrent race simulation was added.

Out-of-scope confirmation:
- No payout calculation.
- No campaign payout rules.
- No driver earnings ledger or driver earnings APIs.
- No advertiser cost summaries or dashboard/reporting APIs beyond the approved campaign impression summary endpoint.
- No campaign daily metrics.
- No heatmap APIs or heatmap cache tables.
- No billing, invoicing, settlement, payment, or payout blocking.
- No automated estimate scheduling or background jobs.
- No seed/demo data.
- No external traffic provider integration.
- No map providers, map matching, tiles, geocoding, or reverse geocoding.
- No audience identity, retargeting, or device pooling.
- No frontend/mobile implementation.
- No OAuth, refresh tokens, GitHub/PR setup, or deployment.

Acceptance criteria checklist:
- Alembic migration creates exactly `traffic_density_profiles` and `impression_estimates`: yes.
- No Slice 9+ payout/earnings/reporting/heatmap/ledger/seed/audience tables added: yes.
- Admin can create/list/read/update traffic density profiles: yes.
- One active default profile is enforced/resolved: yes.
- Admin can estimate impressions for trips with existing computed analytics: yes.
- Estimation is idempotent for the same trip/formula/profile: yes.
- Formula uses analytics distance, zone metrics, stationary seconds, quality score, time-of-day weights, traffic density profile values, and fraud adjustment: yes.
- Insufficient-data analytics is handled deterministically: yes.
- Blocked analytics is handled deterministically as excluded: yes.
- Open fraud flags reduce confidence/estimate by deterministic severity rules: yes.
- Estimate metadata explains formula inputs, weights, and adjustments: yes.
- Admin can list/filter impression estimates: yes.
- Advertiser can read only own campaign impression summary: yes.
- Advertiser summary aggregates stored estimates and returns stable zero shape when empty: yes.
- Advertiser summary filters by current formula version: yes.
- Admin/advertiser/driver/unauthenticated access boundaries are enforced: yes.
- API responses do not expose password hashes, raw pings, or unrelated sensitive data: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, via Docker.
- No deferred/future scope implemented: yes.

Codex questions:
- Please review whether the nested-transaction default-profile race recovery is sufficient without a true concurrent race simulation test.

Orchestrator recommendation:
PASS_CANDIDATE

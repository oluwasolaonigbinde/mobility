CODEX BUILD REPORT

Slice:
Slice 8 - Impression estimation v1

Status: PASS_CANDIDATE

Summary:
Implemented the approved Slice 8 backend scope only: admin-managed traffic density profiles, deterministic `impressions_v1` estimates from existing trip analytics, idempotent stored estimate recomputation, fraud and quality multipliers, settings-backed default profile creation, admin estimate listing, advertiser campaign impression summary, settings/docs updates, Alembic migration, and focused/full verification.

Local investigation performed:
- Read `docs/build-loop/prompts/slice-08-impression-estimation.md`.
- Read `agent.md`.
- Read accepted Slice 0 through Slice 7 reports under `docs/build-loop/reports/`.
- Confirmed branch `slice-08-impression-estimation`.
- Confirmed current base includes `5715e6e docs: record slice 7 commit` and `c696555 feat: add route analytics and fraud flags`.
- Confirmed only pre-existing dirty file was `docs/build-loop/slice-log.md`, already marking Slice 8 in progress.
- Inspected existing `/api/v1` router, error envelope, auth/RBAC dependencies, settings validation, DB base imports, Decimal response serialization, Alembic style, trip sessions, trip analytics, fraud flags, advertiser campaign tenancy, and test fixtures.
- Confirmed current Alembic head was `0008_route_analytics_and_fraud_flags`.
- Confirmed no existing Slice 8 impression or traffic density tables/models existed.

Implementation flow:
- Clean implementation worker Mendel implemented the main Slice 8 candidate and wrote the initial report.
- Clean read-only auditors Sagan and Turing prepared service/API and migration/test risk checklists before implementation review.
- Clean read-only auditors Darwin and Lagrange reviewed the actual Slice 8 candidate and found blocking/Pro-review issues.
- Clean fix worker Harvey addressed blocked analytics, profile metadata validation, formula-version summary filtering, default-profile race recovery, and migration-test evidence gaps.
- Clean fix worker Heisenberg updated the Slice 7 DB-backed migration test so it verifies the Slice 7 revision explicitly now that Slice 8 is the repo head.
- Orchestrator reran full host, PostGIS, Alembic, Docker, and ruff verification after the fix passes.

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

Database migrations:
- Added `0009_impression_estimation`, down revision `0008_route_analytics_and_fraud_flags`.
- Creates exactly:
  - `traffic_density_profiles`
  - `impression_estimates`
- Adds profile status/type checks, nonnegative numeric checks, active-default partial unique index, estimate status check, estimate component nonnegative checks, multiplier/confidence range checks, idempotency unique constraint on `(trip_session_id, formula_version, traffic_density_profile_id)`, and required reporting/filter indexes.
- DB-backed migration test upgrades a temporary Postgres/PostGIS database to Slice 7 first, captures base tables, upgrades to head, and asserts the new-table delta is exactly the two Slice 8 tables.
- DB-backed migration test also verifies the Slice 7 long Alembic revision column-width fix remains preserved.
- Adds no payout, earnings, campaign daily metrics, advertiser reports, heatmap, ledger, billing, settlement, audience, retargeting, or seed tables.

API endpoints implemented:
- `POST /api/v1/admin/traffic-density-profiles`
- `GET /api/v1/admin/traffic-density-profiles`
- `GET /api/v1/admin/traffic-density-profiles/{profile_id}`
- `PATCH /api/v1/admin/traffic-density-profiles/{profile_id}`
- `POST /api/v1/admin/trips/{trip_id}/estimate-impressions`
- `GET /api/v1/admin/impression-estimates`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/impressions/summary`

Security/validation implemented:
- Admin-only enforcement for profile and estimate endpoints.
- Advertiser-only enforcement for campaign impression summary.
- Advertiser summary uses existing organization-scoped campaign lookup and returns non-leaking 404 for cross-organization campaigns.
- Admin, driver, advertiser, and unauthenticated boundaries are tested across Slice 8 surfaces.
- Profile names are trimmed and non-empty; descriptions are trimmed.
- Profile enum, status, nonnegative numeric values, and object metadata are validated.
- Profile PATCH `metadata: null` or list metadata is rejected with validation error instead of reaching the DB.
- Only active profiles can be used for estimation.
- Trip must exist, be ended, and have existing analytics before estimation.
- API responses do not expose password hashes, raw pings, driver identities in advertiser summaries, payout data, or unrelated sensitive data.

Impression formula implemented:
- Formula version: `impressions_v1`.
- Uses analytics distance, target/bonus/exclusion zone distances, stationary seconds, analytics quality score, traffic density profile values, UTC time-of-day bucket, profile road category weight, fraud severity multiplier, and confidence score.
- Uses meters-to-kilometers and seconds-to-minutes conversions.
- Stores component values and transparent metadata including profile values, time bucket, UTC convention, road category method, fraud counts, source analytics id, inputs, component outputs, and request metadata.
- Estimated impressions are clamped at zero.
- Decimal API responses serialize as strings, matching Slice 7 convention.

Traffic density profile handling implemented:
- Admin create/list/read/update.
- Setting an active profile as default clears other active defaults.
- Partial unique index enforces one active default in PostgreSQL and SQLite metadata.
- Estimation without a profile id uses the active default profile.
- If no active default exists, the service creates a settings-backed active default profile in the same transaction.
- The default-profile insert uses a nested transaction and catches `IntegrityError` to re-read an active default if another concurrent request created it.
- Profile changes do not mutate existing estimates.

Fraud/quality adjustment implemented:
- Quality multiplier clamps `trip_analytics.quality_score` to `[0, 1]`.
- Open high-severity fraud flags use `IMPRESSION_HIGH_FRAUD_MULTIPLIER`.
- Else open medium-severity flags use `IMPRESSION_MEDIUM_FRAUD_MULTIPLIER`.
- Else open low-severity flags use `IMPRESSION_LOW_FRAUD_MULTIPLIER`.
- Else fraud multiplier is `1.0`.
- Only open fraud flags affect estimates; acknowledged/dismissed flags do not.
- Confidence score is `quality_multiplier * fraud_adjustment_multiplier`, clamped by configured min/max confidence.
- Insufficient-data analytics creates/updates `status=insufficient_data`, zero impressions, and configured low confidence.
- Blocked analytics creates/updates `status=excluded`, zero impressions, confidence at configured minimum, and `blocked_analytics` metadata.

Advertiser summary aggregation implemented:
- Aggregates stored `impression_estimates` only.
- Filters stored estimates by current `settings.impression_formula_version`.
- Uses `estimated_at` for optional `start_at` and `end_at` filters.
- Returns stable zero shape when no estimates exist.
- Returns estimated impressions, total trip count, status counts, and average confidence score.
- Does not generate estimates automatically.

Tests added/updated:
- Added profile API validation, CRUD, default superseding, metadata-object validation, and RBAC tests.
- Added estimate formula component, idempotency, copied foreign keys, metadata, settings-backed default profile, insufficient data, blocked analytics, fraud severity multiplier, inactive profile, active trip, missing analytics, listing/filtering, RBAC, and advertiser summary scoping/aggregation tests.
- Added formula-version filtering test for advertiser summaries.
- Added Slice 8 migration guard and Postgres schema verification tests.
- Updated Slice 7 migration test to target the Slice 7 revision explicitly instead of `head`, preserving older-slice evidence once Slice 8 exists.
- Extended settings tests for Slice 8 defaults and validation.
- Extended fixtures for trip analytics, traffic density profiles, and estimate reads.

Commands run:
- `python -m ruff check .`
- `python -m pytest tests/test_config.py tests/test_migration_slice8.py -q`
- `python -m pytest tests/test_impression_estimates.py tests/test_traffic_density_profiles.py -q`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head; python -m alembic current`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest tests/test_impression_estimates.py tests/test_traffic_density_profiles.py tests/test_migration_slice8.py -q`
- `python -m pytest`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m pytest`
- `docker compose run --rm api python -m ruff check .`

Command results:
- Host `python -m ruff check .`: all checks passed.
- Host `python -m pytest tests/test_config.py tests/test_migration_slice8.py -q`: 50 passed, 1 skipped, 1 existing FastAPI/TestClient warning.
- Host `python -m pytest tests/test_impression_estimates.py tests/test_traffic_density_profiles.py -q`: 15 passed, 1 existing FastAPI/TestClient warning.
- Host Alembic with local PostGIS URL: upgrade passed; current reported `0009_impression_estimation (head)`.
- Host PostGIS targeted Slice 8 tests: 17 passed, 1 existing FastAPI/TestClient warning.
- Host full `python -m pytest` without `DATABASE_URL`: 159 passed, 20 skipped, 1 existing FastAPI/TestClient warning.
- Host full `python -m pytest` with `DATABASE_URL`: 179 passed, 1 existing FastAPI/TestClient warning.
- `docker compose build api`: succeeded.
- Docker Python version: Python 3.12.13.
- Docker `python -m pytest`: 179 passed, 1 existing FastAPI/TestClient warning.
- Docker `python -m ruff check .`: all checks passed.

Known issues:
- Host Python is 3.14.4, while the fixed stack is Python 3.12. Docker verified Python 3.12.13 successfully.
- Existing FastAPI/TestClient stack emits a deprecation warning about `httpx`; tests pass.
- PostGIS-specific tests intentionally skip on host when no `DATABASE_URL` or `TEST_DATABASE_URL` is configured. They pass with a real PostGIS URL and in Docker.
- The default-profile race recovery is implemented structurally with a nested transaction plus re-read on `IntegrityError`; no true concurrent race simulation test was added.

Out-of-scope compliance:
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
- No frontend/mobile, OAuth, refresh tokens, GitHub/PR setup, or deployment.
- No commit was created.

Acceptance criteria checklist:
- Migration creates approved `traffic_density_profiles` and `impression_estimates`: yes.
- Migration down revision is `0008_route_analytics_and_fraud_flags`: yes.
- No Slice 9+ payout/reporting/heatmap/ledger/seed/audience tables added: yes.
- Admin can create/list/read/update profiles: yes.
- One active default profile is enforced/resolved: yes.
- Admin can estimate impressions for ended trips with existing analytics: yes.
- Re-estimation is idempotent for trip/formula/profile: yes.
- Formula uses analytics distance, zones, stationary seconds, quality score, time weights, profile values, and fraud adjustment: yes.
- Insufficient-data analytics is deterministic: yes.
- Blocked analytics is deterministic and excluded: yes.
- Open fraud flags reduce estimate/confidence by severity: yes.
- Estimate metadata explains formula inputs, weights, and adjustments: yes.
- Admin can list/filter estimates: yes.
- Advertiser can read only own campaign summary: yes.
- Advertiser summary aggregates stored estimates and returns zero shape when empty: yes.
- Advertiser summary filters by current formula version: yes.
- Admin/advertiser/driver/unauthenticated access boundaries are enforced: yes.
- API responses avoid password hashes, raw pings, and unrelated sensitive data: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, via Docker.
- No deferred/future scope implemented: yes.

Manual verification steps:
- Use an admin bearer token to create an active default profile via `POST /api/v1/admin/traffic-density-profiles`.
- Recompute route analytics for an ended trip if needed, then call `POST /api/v1/admin/trips/{trip_id}/estimate-impressions`.
- Re-call the estimate endpoint with the same profile and confirm the same estimate row id is returned.
- Use `GET /api/v1/admin/impression-estimates` with filters to inspect stored rows.
- Use an advertiser bearer token for the campaign organization to call `GET /api/v1/advertiser/campaigns/{campaign_id}/impressions/summary`.
- Use a different advertiser organization token to confirm cross-org campaign access returns 404.

Questions for Pro reviewer:
- Please review the nested-transaction default-profile race recovery approach. It is intentionally simple and backed by the partial unique index, but not covered by a true concurrent simulation test.

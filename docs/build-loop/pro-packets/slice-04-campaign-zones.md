PRO REVIEW PACKET

Slice:
Slice 4 - Campaign zones/geofences

Repo state summary:
- Branch: `slice-04-campaign-zones`
- Base accepted state: Slice 3 recorded at `53fdd0a docs: record slice 3 commit`
- Current status: uncommitted Slice 4 PASS_CANDIDATE
- Current Alembic head after Slice 4: `0005_campaign_zones`
- API prefix remains `/api/v1`
- Fixed stack preserved: FastAPI, Pydantic v2, SQLAlchemy async, asyncpg, Alembic, PostgreSQL/PostGIS, Redis, pytest, ruff, Docker Compose.

Commit status:
- No Slice 4 commit has been created yet.
- Working tree contains only the Slice 4 implementation/report/ledger changes listed below.
- Intended commit only after Pro PASS and local reconciliation.

Files changed:
- `.env.example`
- `README.md`
- `alembic/versions/0005_campaign_zones.py`
- `app/api/v1/campaign_zones.py`
- `app/api/v1/router.py`
- `app/core/config.py`
- `app/db/base.py`
- `app/models/campaign_zone.py`
- `app/schemas/campaign_zones.py`
- `app/services/campaign_zones.py`
- `docker-compose.yml`
- `docs/build-loop/reports/slice-04-campaign-zones.md`
- `docs/build-loop/slice-log.md`
- `tests/conftest.py`
- `tests/test_campaign_zones.py`
- `tests/test_migration_slice4.py`

Diff summary:
- Adds the `campaign_zones` model using a custom SQLAlchemy `UserDefinedType` for `geometry(MultiPolygon,4326)` with a SQLite compile fallback for metadata compatibility.
- Adds advertiser campaign-zone CRUD router and mounts it in `app/api/v1/router.py`.
- Adds Pydantic create/update/read/list schemas with forbidden extra fields so clients cannot body-set `campaign_id` or `created_by_user_id`.
- Adds campaign-zone service logic for tenant-scoped campaign lookup, owner/manager write checks, viewer read behavior, campaign lifecycle mutation checks, GeoJSON normalization, PostGIS validity checks, geography-safe area computation, and delete.
- Adds `MAX_CAMPAIGN_ZONE_AREA_SQ_KM`, default `5000`, in settings, `.env.example`, and Docker Compose.
- Adds isolated PostGIS test fixtures that create a per-test schema against `DATABASE_URL` or `TEST_DATABASE_URL`.
- Adds PostGIS-backed API tests plus a static migration guard test.
- Updates README and build-loop ledger/report for Slice 4.

Database migrations:
- New migration: `alembic/versions/0005_campaign_zones.py`
- Down revision: `0004_campaigns_and_creatives`
- Creates exactly one new Slice 4 business table: `campaign_zones`
- Columns:
  - `id` UUID primary key, `gen_random_uuid()`
  - `campaign_id` UUID FK to `campaigns.id`, not null, cascade delete
  - `created_by_user_id` UUID FK to `users.id`, not null
  - `name` text, not null
  - `description` text, nullable
  - `zone_type` text, not null, constrained to `target`, `exclusion`, `bonus`
  - `geom` `geometry(MultiPolygon,4326)`, not null
  - `metadata` JSONB, not null, default `'{}'::jsonb`
  - `created_at` and `updated_at` timezone-aware timestamps, not null
- Indexes:
  - `ix_campaign_zones_campaign_id`
  - `ix_campaign_zones_campaign_zone_type`
  - `ix_campaign_zones_created_by_user_id`
  - `ix_campaign_zones_geom` using GiST
- Does not add assignment, GPS, trip, analytics, impression, payout, report, heatmap, or seed tables.

API endpoints:
- `POST /api/v1/advertiser/campaigns/{campaign_id}/zones`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/zones`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}`
- `PATCH /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}`
- `DELETE /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}`

Security/validation implemented:
- Uses existing advertiser-user dependency, so unauthenticated/admin/driver users are rejected by existing Slice 1 patterns.
- Uses existing campaign lookup through current advertiser organization membership and campaign ownership.
- Owner and manager memberships can create/update/delete.
- Viewer memberships can list/read but cannot create/update/delete.
- Advertisers without organization membership receive existing non-leaking errors.
- Cross-organization and cross-campaign access uses campaign/zone lookups that return 404 where practical.
- Create/update/delete call `ensure_mutable_campaign`; only `draft`, `scheduled`, `active`, and `paused` mutate.
- `completed` and `cancelled` campaigns remain readable but cannot be mutated.
- Request schemas forbid extra fields, including client-supplied `campaign_id` and `created_by_user_id`.
- Audit events:
  - `advertiser.campaign_zone.created`
  - `advertiser.campaign_zone.updated`
  - `advertiser.campaign_zone.deleted`

Geospatial validation/storage implemented:
- Accepts GeoJSON `Polygon` and `MultiPolygon` only.
- Normalizes `Polygon` to `MultiPolygon`.
- Enforces finite numeric `[longitude, latitude]` pairs.
- Enforces longitude in `[-180, 180]` and latitude in `[-90, 90]`.
- Enforces non-empty polygons, minimum four-position rings, and closed rings in Python before PostGIS.
- Uses PostGIS as authority:
  - `ST_GeomFromGeoJSON`
  - `ST_SetSRID`
  - `ST_Multi`
  - `ST_IsValid`
  - `ST_IsValidReason`
  - `ST_GeometryType`
  - `ST_SRID`
- Computes area with `ST_Area(geom::geography)`.
- Enforces configured max area in square kilometers.
- Stores geometry in PostGIS and returns GeoJSON using `ST_AsGeoJSON`.
- Does not return raw WKT/WKB.

Tests/checks run:
- Worker and orchestrator both verified the slice. Orchestrator reran the key host/PostGIS, Alembic, Docker build, Docker Python, Docker pytest, and Docker ruff checks after the worker report.

Exact command outputs or concise failure excerpts:
- `python -m pytest` with `DATABASE_URL=postgresql+asyncpg://mobility:mobility@localhost:5433/mobility`
  - Result: `79 passed, 1 warning in 82.63s`
- `python -m pytest tests/test_campaign_zones.py -q` with same `DATABASE_URL`
  - Result: `8 passed, 1 warning in 38.39s`
- `python -m ruff check .`
  - Result: `All checks passed!`
- `python -m alembic upgrade head` with same `DATABASE_URL`
  - Result: passed; PostgresqlImpl transactional DDL
- `python -m alembic current` with same `DATABASE_URL`
  - Result: `0005_campaign_zones (head)`
- `docker compose build api`
  - Result: image `mobility-api:latest` built successfully
- `docker compose run --rm api python --version`
  - Result: `Python 3.12.13`
- `docker compose run --rm api python -m pytest`
  - Result: `79 passed, 1 warning in 80.94s`
- `docker compose run --rm api python -m ruff check .`
  - Result: `All checks passed!`

Known issues:
- Host Python is 3.14.4, while the fixed stack is Python 3.12. Docker verified Python 3.12.13 successfully.
- Existing FastAPI/TestClient stack emits a deprecation warning about `httpx`; tests pass.
- PostGIS API tests intentionally skip when no `DATABASE_URL` or `TEST_DATABASE_URL` is configured. They were run and passed with a real PostGIS URL and inside Docker.
- Existing Slice 1/Slice 3 advertiser org scoping chooses one active/invited membership ordered by latest membership. Slice 4 reuses that accepted pattern rather than redesigning tenancy in this slice.
- Existing read-scope helper includes `MembershipStatus.INVITED`; write paths require active owner/manager. Slice 4 preserves that existing helper behavior.

Out-of-scope confirmation:
- No campaign assignment.
- No campaign activation by drivers/vehicles.
- No driver campaign availability.
- No GPS pings.
- No trip sessions.
- No route analytics or zone-overlap analytics.
- No fraud flags.
- No impression estimation.
- No payout calculation or earnings ledger.
- No advertiser dashboard/reporting APIs.
- No heatmap APIs.
- No map tiles, map SDKs, map providers, geocoding, or route matching.
- No creative binary upload/storage pipeline.
- No seed/demo trip data.
- No background jobs.
- No frontend/mobile implementation.
- No GitHub remote/PR setup or production deployment.

Acceptance criteria checklist:
- Alembic migration creates exactly the approved `campaign_zones` table: yes.
- `campaign_zones.geom` is real PostGIS geometry with SRID 4326: yes.
- GiST index exists on geometry: yes.
- No Slice 5+ domain tables were added: yes.
- Campaign zones belong to campaigns: yes.
- Zones inherit advertiser organization access through campaigns: yes.
- Advertisers can access only own-organization campaign zones under existing org-selection rules: yes.
- Owner/manager write permissions are enforced: yes.
- Viewer list/read-only behavior is enforced: yes.
- Driver/admin/unauthenticated boundaries are enforced: yes.
- Completed/cancelled mutation restrictions are enforced: yes.
- GeoJSON validation covers type, coordinate bounds, closed rings, minimum ring size, metadata, and invalid geometry: yes.
- PostGIS validity and geography area cap checks are enforced: yes.
- Responses return GeoJSON geometry and calculated area: yes.
- Audit events are written for create/update/delete: yes.
- Responses do not expose password hashes or unrelated driver/vehicle/tracking data: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, via Docker.
- No deferred/future scope implemented: yes.

Codex questions:
- None. Please call out any blocker if the existing membership helper behavior should be changed in Slice 4 rather than treated as accepted prior-slice tenancy behavior.

Orchestrator recommendation: PASS_CANDIDATE
